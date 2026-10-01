"""Faz 4A — API anahtarları: üretim, saklama, doğrulama, kapsam, hız sınırı, idempotency.

Anahtar
-------
`mk_live_` + 32 bayt rastgele (base62, 43 karakter). Veritabanında yalnız
SHA-256 özeti ve rastgele kısmın ilk 8 karakteri (`onek`) var; ham anahtar
yalnız oluşturma yanıtında BİR KEZ dönüyor. Doğrulama önekle aday satırları
bulup özeti `hmac.compare_digest` ile (sabit zamanlı) karşılaştırıyor.

Kimlik doğrulama yalnız `/api/public/v1/*` uçlarında: `Authorization: Bearer
mk_live_…` ya da `X-API-Key`. Panel uçları (`/api/v1/*`) anahtarı TANIMIYOR —
JWT çözümü (`decode_access_token`) `mk_live_` metnini geçersiz jeton sayıp 401
veriyor; saldırı yüzeyi büyümüyor.

Sahip
-----
* `ajans` (yönetici): bütün müşterilerin kayıtları — kapsam seçimi zorunlu,
  son kullanma tarihi yoksa açık onay (`suresiz_onay`) isteniyor.
* `musteri`: yalnız kendi hesabı (`hesap_email`). Modül `api_erisimi` açık
  olmalı; ekip üyesi açtıysa (`olusturan` ≠ hesap) her istekte üyeliği, `api`
  izni ve kapsamın karşılığı olan modül izni yeniden doğrulanıyor — üye
  çıkarılınca/izni alınınca anahtarı da çalışmaz.

İptal anında etkili: anahtar satırı her istekte okunuyor (önbellek yok).
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, FrozenSet, Iterable, List, Optional, Tuple

from models.api_erisimi import ApiAnahtarlari, ApiIdempotency
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODUL = "api_erisimi"
IZIN = "api"
ONEK = "mk_live_"
RASTGELE_UZUNLUK = 43  # 32 bayt → base62
ONEK_UZUNLUGU = 8
_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

#: Müşteri için varsayılanlar (modül ayarı yoksa) ve ajans için sabitler.
VARSAYILAN_ANAHTAR_SINIRI = 5
VARSAYILAN_DAKIKA_SINIRI = 60
AJANS_ANAHTAR_SINIRI = 25
AJANS_DAKIKA_SINIRI = 600
EN_COK_DAKIKA_SINIRI = 6000
IP_IZNI_SINIRI = 20
AD_SINIRI = 80
#: Son kullanma en çok bu kadar ileri (ajans anahtarı için önerilen 90 gün).
EN_UZUN_SURE = timedelta(days=366)
ONERILEN_AJANS_SURESI_GUN = 90
#: Son kullanım bilgisi en çok bu aralıkla yazılıyor.
SON_KULLANIM_ARALIGI = timedelta(seconds=60)
IDEMPOTENCY_SURESI = timedelta(hours=24)
IDEM_ANAHTAR_SINIRI = 200


# ---------------------------------------------------------------------------
# Kapsamlar
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Kapsam:
    anahtar: str
    #: Müşteri tarafında gereken hesap ekibi izni (None = yok).
    izin: Optional[str]
    #: Müşteri tarafında açık olması gereken modüllerden biri (boş = çekirdek).
    moduller: Tuple[str, ...] = ()
    yalniz_ajans: bool = False
    yazma: bool = False


KAPSAMLAR: Tuple[Kapsam, ...] = (
    Kapsam("projeler:oku", "projeler"),
    Kapsam("gorevler:oku", "gorevler", ("gorevler",)),
    Kapsam("gorevler:yaz", "gorevler", ("gorevler",), yazma=True),
    Kapsam("faturalar:oku", "faturalar"),
    Kapsam("destek:oku", "destek"),
    Kapsam("destek:yaz", "destek", yazma=True),
    Kapsam("crm:oku", None, yalniz_ajans=True),
    Kapsam("crm:yaz", None, yalniz_ajans=True, yazma=True),
    Kapsam("qr:oku", "qr", ("dinamik_qr",)),
    Kapsam("menu:oku", "menu", ("qr_menu", "whatsapp_katalog")),
)
KAPSAM_SOZLUGU: Dict[str, Kapsam] = {k.anahtar: k for k in KAPSAMLAR}


class ApiHatasi(Exception):
    """Herkese açık API ve panel uçlarının ortak hatası: HTTP durumu + kod (+ ek alanlar)."""

    def __init__(self, durum: int, kod: str, mesaj: Optional[str] = None, basliklar: Optional[Dict[str, str]] = None, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.mesaj = mesaj or MESAJLAR.get(kod) or kod
        self.basliklar = basliklar or {}
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


#: Herkese açık API hata mesajları (geliştiriciye; kararlı `kod` asıl sözleşme).
MESAJLAR: Dict[str, str] = {
    "anahtar_gerekli": "API anahtarı gerekli: 'Authorization: Bearer mk_live_…' ya da 'X-API-Key' başlığı.",
    "anahtar_gecersiz": "API anahtarı geçersiz.",
    "anahtar_iptal": "API anahtarı iptal edilmiş.",
    "anahtar_suresi_doldu": "API anahtarının süresi dolmuş.",
    "anahtar_devre_disi": "Anahtarı oluşturan kişinin bu hesaptaki yetkisi kalmamış.",
    "ip_izinli_degil": "Bu IP adresinden bu anahtarla istek yapılamaz.",
    "modul_kapali": "Bu hesapta gerekli modül kapalı.",
    "kapsam_yetersiz": "Anahtarın bu işlem için kapsamı yok.",
    "hiz_siniri": "Çok fazla istek; bir süre sonra yeniden deneyin.",
    "bulunamadi": "Kayıt bulunamadı.",
    "gecersiz_istek": "İstek geçersiz.",
    "cursor_gecersiz": "cursor geçersiz.",
    "tarih_gecersiz": "Tarih ISO 8601 biçiminde olmalı.",
    "idempotency_anahtari_gecersiz": "Idempotency-Key en çok 200 karakter olmalı.",
    "idempotency_uyusmazligi": "Bu Idempotency-Key başka bir istekle kullanılmış.",
    "idempotency_isleniyor": "Aynı Idempotency-Key ile bir istek hâlâ işleniyor.",
    "sunucu_hatasi": "Beklenmeyen bir hata oluştu.",
    "yalniz_ajans": "Bu uç yalnız ajans anahtarlarıyla kullanılabilir.",
}


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Any) -> Optional[str]:
    if an is None:
        return None
    if isinstance(an, datetime):
        return utc(an).isoformat().replace("+00:00", "Z")
    return str(an)


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def json_liste(ham: Any) -> List[Any]:
    try:
        deger = json.loads(ham) if isinstance(ham, str) else ham
    except (TypeError, ValueError):
        return []
    return list(deger) if isinstance(deger, list) else []


# ---------------------------------------------------------------------------
# Anahtar üretimi
# ---------------------------------------------------------------------------
def _base62(veri: bytes, uzunluk: int) -> str:
    sayi = int.from_bytes(veri, "big")
    parcalar: List[str] = []
    while sayi:
        sayi, kalan = divmod(sayi, 62)
        parcalar.append(_BASE62[kalan])
    metin = "".join(reversed(parcalar))
    return metin.rjust(uzunluk, "0")


def anahtar_uret() -> Tuple[str, str, str]:
    """(ham anahtar, sha256 özeti, önek)."""
    rastgele = _base62(secrets.token_bytes(32), RASTGELE_UZUNLUK)
    ham = ONEK + rastgele
    return ham, ozet(ham), rastgele[:ONEK_UZUNLUGU]


def ozet(ham: str) -> str:
    return hashlib.sha256((ham or "").encode("utf-8")).hexdigest()


def bicim_gecerli_mi(ham: str) -> bool:
    if not isinstance(ham, str) or not ham.startswith(ONEK):
        return False
    rastgele = ham[len(ONEK):]
    return len(rastgele) == RASTGELE_UZUNLUK and all(c in _BASE62 for c in rastgele)


def gorunen_onek(onek: str) -> str:
    return f"{ONEK}{onek}…"


# ---------------------------------------------------------------------------
# Gizli bilgi saklama (webhook imza sırrı) — Fernet varsa şifreli
# ---------------------------------------------------------------------------
def _fernet():
    anahtar = (os.environ.get("BAGLANTI_SIFRE_ANAHTARI") or "").strip()
    if not anahtar:
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(anahtar.encode("ascii"))
    except Exception:  # noqa: BLE001 - geçersiz anahtar: düz saklamaya düş
        return None


def gizli_sakla(metin: str) -> str:
    f = _fernet()
    if f is not None:
        return "f1:" + f.encrypt(metin.encode("utf-8")).decode("ascii")
    return "d1:" + metin


def gizli_oku(saklanan: Optional[str]) -> Optional[str]:
    if not saklanan:
        return None
    if saklanan.startswith("d1:"):
        return saklanan[3:]
    if saklanan.startswith("f1:"):
        f = _fernet()
        if f is None:
            return None
        try:
            return f.decrypt(saklanan[3:].encode("ascii")).decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
    return None


# ---------------------------------------------------------------------------
# Doğrulama yardımcıları
# ---------------------------------------------------------------------------
def kapsamlari_duzelt(ham: Any, *, ajans: bool) -> List[str]:
    if not isinstance(ham, list) or not ham:
        raise ApiHatasi(400, "kapsam_gerekli")
    secili = set()
    for k in ham:
        k = str(k).strip()
        tanim = KAPSAM_SOZLUGU.get(k)
        if tanim is None:
            raise ApiHatasi(400, "kapsam_gecersiz", kapsam=k)
        if tanim.yalniz_ajans and not ajans:
            raise ApiHatasi(400, "kapsam_yalniz_ajans", kapsam=k)
        secili.add(k)
    return [k.anahtar for k in KAPSAMLAR if k.anahtar in secili]


def ip_izinlerini_duzelt(ham: Any) -> List[str]:
    if ham in (None, "", []):
        return []
    if isinstance(ham, str):
        ham = [p for p in ham.replace("\n", ",").split(",")]
    if not isinstance(ham, list):
        raise ApiHatasi(400, "ip_gecersiz")
    sonuc: List[str] = []
    for p in ham:
        p = str(p).strip()
        if not p:
            continue
        try:
            ag = ipaddress.ip_network(p, strict=False)
        except ValueError:
            raise ApiHatasi(400, "ip_gecersiz", deger=p[:60])
        if str(ag) not in sonuc:
            sonuc.append(str(ag))
    if len(sonuc) > IP_IZNI_SINIRI:
        raise ApiHatasi(400, "ip_cok_fazla", sinir=IP_IZNI_SINIRI)
    return sonuc


def ip_izinli_mi(ip: str, izinler: Iterable[str]) -> bool:
    izinler = list(izinler)
    if not izinler:
        return True
    try:
        adres = ipaddress.ip_address((ip or "").split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(adres, ipaddress.IPv6Address) and adres.ipv4_mapped is not None:
        adres = adres.ipv4_mapped
    for p in izinler:
        try:
            if adres in ipaddress.ip_network(p, strict=False):
                return True
        except (ValueError, TypeError):
            continue
    return False


def tarih_coz(ham: Any, *, alan: str = "tarih") -> Optional[datetime]:
    if ham in (None, ""):
        return None
    if not isinstance(ham, str):
        raise ApiHatasi(400, "tarih_gecersiz", alan=alan)
    metin = ham.strip().replace("Z", "+00:00")
    try:
        an = datetime.fromisoformat(metin)
    except ValueError:
        raise ApiHatasi(400, "tarih_gecersiz", alan=alan)
    return utc(an)


# ---------------------------------------------------------------------------
# Sahip (panel tarafı)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Sahip:
    """Panelden anahtar/webhook yöneten taraf."""

    yonetici: bool
    #: Müşteride etkin hesap; ajansta None.
    hesap: Optional[str]
    kisi: str
    #: Müşteri tarafında kişinin etkin hesaptaki izinleri (sahipte hepsi).
    izinler: FrozenSet[str] = field(default_factory=frozenset)
    sahip_rolu: bool = True

    @property
    def sahip_tur(self) -> str:
        return "ajans" if self.yonetici else "musteri"

    def sahip_kosulu(self, model: Any):
        if self.yonetici:
            return and_(model.sahip_tur == "ajans", model.hesap_email.is_(None))
        return and_(model.sahip_tur == "musteri", model.hesap_email == self.hesap)


async def _ayar(db: AsyncSession, hesap: str, alan: str, varsayilan: int) -> int:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, MODUL, alan)
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else varsayilan


async def anahtar_siniri(db: AsyncSession, sahip: Sahip) -> int:
    if sahip.yonetici:
        return AJANS_ANAHTAR_SINIRI
    return await _ayar(db, sahip.hesap or "", "anahtar_siniri", VARSAYILAN_ANAHTAR_SINIRI)


async def dakika_siniri_ust(db: AsyncSession, sahip: Sahip) -> int:
    if sahip.yonetici:
        return AJANS_DAKIKA_SINIRI
    return await _ayar(db, sahip.hesap or "", "dakika_siniri", VARSAYILAN_DAKIKA_SINIRI)


def kullanilabilir_kapsamlar(sahip: Sahip) -> List[str]:
    """Bu sahibin seçebileceği kapsamlar (üyede izinlerine göre)."""
    sonuc = []
    for k in KAPSAMLAR:
        if k.yalniz_ajans and not sahip.yonetici:
            continue
        if not sahip.yonetici and not sahip.sahip_rolu and k.izin and k.izin not in sahip.izinler:
            continue
        sonuc.append(k.anahtar)
    return sonuc


def anahtar_durumu(a: ApiAnahtarlari, an: Optional[datetime] = None) -> str:
    an = an or simdi()
    if a.iptal_at is not None:
        return "iptal"
    bitis = utc(a.son_kullanma)
    if bitis is not None and bitis <= an:
        return "suresi_doldu"
    return "aktif"


def anahtar_sozlugu(a: ApiAnahtarlari) -> Dict[str, Any]:
    """Panel yanıtı — özet ASLA dönmez; son IP yalnız özetin ilk 10 karakteri."""
    return {
        "id": a.id,
        "ad": a.ad,
        "onek": gorunen_onek(a.onek),
        "sahip_tur": a.sahip_tur,
        "hesap_email": a.hesap_email,
        "kapsamlar": json_liste(a.kapsamlar),
        "ip_izinleri": json_liste(a.ip_izinleri),
        "dakika_siniri": int(a.dakika_siniri or VARSAYILAN_DAKIKA_SINIRI),
        "son_kullanma": iso(a.son_kullanma),
        "olusturan": a.olusturan,
        "son_kullanim_at": iso(a.son_kullanim_at),
        "son_ip": (a.son_ip_ozeti or "")[:10] or None,
        "iptal_at": iso(a.iptal_at),
        "durum": anahtar_durumu(a),
        "olusturma": iso(a.created_at),
    }


async def anahtarlar(db: AsyncSession, sahip: Sahip, *, hepsi: bool = False) -> List[ApiAnahtarlari]:
    sorgu = select(ApiAnahtarlari)
    if not (sahip.yonetici and hepsi):
        sorgu = sorgu.where(sahip.sahip_kosulu(ApiAnahtarlari))
    return list((await db.execute(sorgu.order_by(ApiAnahtarlari.id.desc()).limit(500))).scalars().all())


async def etkin_anahtar_sayisi(db: AsyncSession, sahip: Sahip) -> int:
    sorgu = select(func.count(ApiAnahtarlari.id)).where(
        sahip.sahip_kosulu(ApiAnahtarlari),
        ApiAnahtarlari.iptal_at.is_(None),
        or_(ApiAnahtarlari.son_kullanma.is_(None), ApiAnahtarlari.son_kullanma > simdi()),
    )
    return int((await db.execute(sorgu)).scalar() or 0)


async def anahtar_olustur(db: AsyncSession, sahip: Sahip, govde: Dict[str, Any]) -> Tuple[str, ApiAnahtarlari]:
    """Yeni anahtar → (ham anahtar — yalnız bu yanıtta, satır)."""
    ad = str(govde.get("ad") or "").strip()[:AD_SINIRI]
    if not ad:
        raise ApiHatasi(400, "ad_gerekli")
    kapsamlar = kapsamlari_duzelt(govde.get("kapsamlar"), ajans=sahip.yonetici)
    izinli = set(kullanilabilir_kapsamlar(sahip))
    for k in kapsamlar:
        if k not in izinli:
            # Ekip üyesi kendinde olmayan izni anahtara veremez (yetki yükseltme yok).
            raise ApiHatasi(403, "kapsam_izni_yok", kapsam=k)
    son_kullanma = tarih_coz(govde.get("son_kullanma"), alan="son_kullanma")
    an = simdi()
    if son_kullanma is not None:
        if son_kullanma <= an:
            raise ApiHatasi(400, "son_kullanma_gecmiste")
        if son_kullanma > an + EN_UZUN_SURE:
            raise ApiHatasi(400, "son_kullanma_cok_uzak", gun=EN_UZUN_SURE.days)
    elif sahip.yonetici and govde.get("suresiz_onay") is not True:
        # Ajans anahtarı bütün müşterilere erişiyor: süresiz anahtar bilinçli bir karar olmalı.
        raise ApiHatasi(400, "ajans_son_kullanma_gerekli", onerilen_gun=ONERILEN_AJANS_SURESI_GUN)
    ip_izinleri = ip_izinlerini_duzelt(govde.get("ip_izinleri"))
    ust = await dakika_siniri_ust(db, sahip)
    dakika = govde.get("dakika_siniri")
    if dakika in (None, ""):
        dakika = ust
    if isinstance(dakika, bool) or not isinstance(dakika, int) or dakika < 1:
        raise ApiHatasi(400, "dakika_siniri_gecersiz")
    if dakika > ust:
        raise ApiHatasi(400, "dakika_siniri_ust", sinir=ust)
    sinir = await anahtar_siniri(db, sahip)
    if await etkin_anahtar_sayisi(db, sahip) >= sinir:
        raise ApiHatasi(409, "anahtar_siniri", sinir=sinir)

    for _ in range(5):
        ham, ozet_degeri, onek = anahtar_uret()
        satir = ApiAnahtarlari(
            sahip_tur=sahip.sahip_tur,
            hesap_email=None if sahip.yonetici else sahip.hesap,
            ad=ad,
            onek=onek,
            anahtar_ozeti=ozet_degeri,
            kapsamlar=json.dumps(kapsamlar),
            ip_izinleri=json.dumps(ip_izinleri) if ip_izinleri else None,
            dakika_siniri=dakika,
            son_kullanma=son_kullanma,
            olusturan=sahip.kisi or None,
            created_at=an,
        )
        db.add(satir)
        try:
            await db.commit()
        except IntegrityError:  # özet çakışması (pratikte imkânsız): yeniden üret
            await db.rollback()
            continue
        await db.refresh(satir)
        return ham, satir
    raise ApiHatasi(503, "anahtar_uretilemedi")


async def anahtar_bul(db: AsyncSession, sahip: Sahip, anahtar_id: int) -> ApiAnahtarlari:
    sorgu = select(ApiAnahtarlari).where(ApiAnahtarlari.id == anahtar_id)
    if not sahip.yonetici:
        sorgu = sorgu.where(sahip.sahip_kosulu(ApiAnahtarlari))
    satir = (await db.execute(sorgu)).scalars().first()
    if satir is None:
        raise ApiHatasi(404, "bulunamadi")
    return satir


async def anahtar_iptal(db: AsyncSession, satir: ApiAnahtarlari, eden: str) -> ApiAnahtarlari:
    if satir.iptal_at is None:
        satir.iptal_at = simdi()
        satir.iptal_eden = eden or None
        await db.commit()
        await db.refresh(satir)
    return satir


# ---------------------------------------------------------------------------
# İstek başına kimlik (herkese açık API)
# ---------------------------------------------------------------------------
@dataclass
class ApiKimlik:
    anahtar_id: int
    onek: str
    sahip_tur: str
    #: Müşteri hesabı; ajansta None (bütün hesaplar).
    hesap: Optional[str]
    kapsamlar: FrozenSet[str]
    olusturan: Optional[str]
    dakika_siniri: int

    @property
    def ajans(self) -> bool:
        return self.sahip_tur == "ajans"

    def kapsam_var(self, kapsam: str) -> bool:
        return kapsam in self.kapsamlar

    def kapsam_iste(self, kapsam: str) -> None:
        if kapsam not in self.kapsamlar:
            raise ApiHatasi(403, "kapsam_yetersiz", gereken=kapsam)


class _DakikaSiniri:
    """Anahtar başına kayan pencere; her anahtarın kendi sınırı var (süreç belleğinde)."""

    def __init__(self, pencere: float = 60.0):
        self.pencere = pencere
        self._kayitlar: Dict[int, Deque[float]] = {}
        self._kilit = threading.Lock()

    def dene(self, anahtar_id: int, sinir: int) -> Tuple[bool, int]:
        """(izin var mı, kaç saniye sonra yeniden denenebilir)."""
        an = time.monotonic()
        with self._kilit:
            kuyruk = self._kayitlar.setdefault(anahtar_id, deque())
            while kuyruk and an - kuyruk[0] > self.pencere:
                kuyruk.popleft()
            if len(kuyruk) >= max(1, sinir):
                return False, max(1, int(self.pencere - (an - kuyruk[0])) + 1)
            kuyruk.append(an)
            if len(self._kayitlar) > 5000:
                for k in [k for k, v in self._kayitlar.items() if not v]:
                    self._kayitlar.pop(k, None)
            return True, 0

    def temizle(self) -> None:
        with self._kilit:
            self._kayitlar.clear()


hiz = _DakikaSiniri()


def istekten_anahtar(request: Any) -> Optional[str]:
    """`Authorization: Bearer mk_live_…` ya da `X-API-Key`. Bearer başka bir şeyse (JWT) boş."""
    basl = (request.headers.get("authorization") or "").strip()
    if basl:
        if basl.lower().startswith("bearer "):
            deger = basl.split(" ", 1)[1].strip()
            return deger if deger.startswith(ONEK) else ""
        return ""
    return (request.headers.get("x-api-key") or "").strip() or None


async def kimlik_dogrula(db: AsyncSession, request: Any) -> ApiKimlik:
    """Anahtarı doğrular; her durumda kararlı bir `ApiHatasi` kodu."""
    from utils.istemci_ip import ip_ozeti, istemci_ip

    ham = istekten_anahtar(request)
    if ham is None:
        raise ApiHatasi(401, "anahtar_gerekli", basliklar={"WWW-Authenticate": 'Bearer realm="mehmetkuru.dev"'})
    if not bicim_gecerli_mi(ham):
        raise ApiHatasi(401, "anahtar_gecersiz", basliklar={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    onek = ham[len(ONEK): len(ONEK) + ONEK_UZUNLUGU]
    beklenen = ozet(ham)
    adaylar = (await db.execute(select(ApiAnahtarlari).where(ApiAnahtarlari.onek == onek))).scalars().all()
    satir: Optional[ApiAnahtarlari] = None
    for a in adaylar:
        # Sabit zamanlı karşılaştırma (önek çakışsa bile her aday denetlenir).
        if hmac.compare_digest(str(a.anahtar_ozeti or "").encode(), beklenen.encode()):
            satir = a
    if satir is None:
        raise ApiHatasi(401, "anahtar_gecersiz", basliklar={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    durum = anahtar_durumu(satir)
    if durum == "iptal":
        raise ApiHatasi(401, "anahtar_iptal", basliklar={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    if durum == "suresi_doldu":
        raise ApiHatasi(401, "anahtar_suresi_doldu", basliklar={"WWW-Authenticate": 'Bearer error="invalid_token"'})

    ip = istemci_ip(request)
    if not ip_izinli_mi(ip, json_liste(satir.ip_izinleri)):
        raise ApiHatasi(403, "ip_izinli_degil")

    kapsamlar = frozenset(json_liste(satir.kapsamlar))
    hesap = eposta_duzelt(satir.hesap_email) or None
    if satir.sahip_tur == "musteri":
        if not hesap:
            raise ApiHatasi(401, "anahtar_gecersiz")
        from services import moduller as _moduller

        if not await _moduller.modul_acik_mi(db, hesap, MODUL):
            raise ApiHatasi(403, "modul_kapali", modul=MODUL)
        olusturan = eposta_duzelt(satir.olusturan)
        if olusturan and olusturan != hesap:
            # Üyenin açtığı anahtar: üyelik + `api` izni + kapsamların modül izinleri hâlâ yerinde mi?
            from services.hesap_ekibi import uyelik_karari

            bilgi = await uyelik_karari(olusturan, hesap)
            izinler = set((bilgi or {}).get("izinler") or ())
            if not bilgi or IZIN not in izinler:
                raise ApiHatasi(401, "anahtar_devre_disi")
            kapsamlar = frozenset(
                k for k in kapsamlar if not KAPSAM_SOZLUGU.get(k) or not KAPSAM_SOZLUGU[k].izin or KAPSAM_SOZLUGU[k].izin in izinler
            )
    elif satir.sahip_tur != "ajans":
        raise ApiHatasi(401, "anahtar_gecersiz")

    sinir = int(satir.dakika_siniri or VARSAYILAN_DAKIKA_SINIRI)
    izin, bekle = hiz.dene(satir.id, sinir)
    if not izin:
        raise ApiHatasi(429, "hiz_siniri", basliklar={"Retry-After": str(bekle)}, sinir=sinir)

    an = simdi()
    son = utc(satir.son_kullanim_at)
    if son is None or an - son >= SON_KULLANIM_ARALIGI:
        try:
            # Core UPDATE: iş biriminden geçmiyor → denetim kaydına her istekte satır düşmüyor.
            await db.execute(
                update(ApiAnahtarlari)
                .where(ApiAnahtarlari.id == satir.id)
                .values(son_kullanim_at=an, son_ip_ozeti=ip_ozeti(ip))
                .execution_options(synchronize_session=False)
            )
            await db.commit()
        except Exception:  # noqa: BLE001 - kullanım bilgisi isteği düşürmesin
            await db.rollback()
            logger.warning("API anahtarı son kullanım bilgisi yazılamadı (id=%s)", satir.id)

    # Denetim kaydında aktör: anahtarı açan kişi (API'den yapılan yazmalar izlenebilsin).
    try:
        from services.denetim import aktor_ata

        aktor_ata(satir.olusturan or f"api:{satir.onek}", "admin" if satir.sahip_tur == "ajans" else "client")
    except Exception:  # noqa: BLE001
        pass

    return ApiKimlik(
        anahtar_id=satir.id,
        onek=satir.onek,
        sahip_tur=satir.sahip_tur,
        hesap=hesap,
        kapsamlar=kapsamlar,
        olusturan=eposta_duzelt(satir.olusturan) or None,
        dakika_siniri=sinir,
    )


async def kapsam_modulu_acik_mi(db: AsyncSession, kimlik: ApiKimlik, kapsam: str) -> bool:
    """Müşteri anahtarında kapsamın modülü (ör. qr → dinamik_qr) açık mı? Ajansta hep evet."""
    tanim = KAPSAM_SOZLUGU.get(kapsam)
    if kimlik.ajans or tanim is None or not tanim.moduller:
        return True
    from services import moduller as _moduller

    for m in tanim.moduller:
        if await _moduller.modul_acik_mi(db, kimlik.hesap or "", m):
            return True
    return False


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def govde_ozeti(govde: bytes) -> str:
    return hashlib.sha256(govde or b"").hexdigest()


async def idem_basla(
    db: AsyncSession, kimlik: ApiKimlik, idem: str, istek: str, govde: bytes
) -> Tuple[Optional[int], Optional[Tuple[int, Any]]]:
    """(yeni kayıt kimliği, önceki yanıt). Önceki yanıt varsa onu döndür; uyuşmazlıkta 422, işleniyorsa 409."""
    idem = (idem or "").strip()
    if not idem or len(idem) > IDEM_ANAHTAR_SINIRI:
        raise ApiHatasi(400, "idempotency_anahtari_gecersiz")
    an = simdi()
    # Süresi dolanları ara sıra sil (istekle tetiklenen temizlik).
    await db.execute(delete(ApiIdempotency).where(ApiIdempotency.created_at < an - IDEMPOTENCY_SURESI))
    ozet_degeri = govde_ozeti(govde)
    mevcut = (
        await db.execute(
            select(ApiIdempotency).where(ApiIdempotency.anahtar_id == kimlik.anahtar_id, ApiIdempotency.idem_anahtari == idem)
        )
    ).scalars().first()
    if mevcut is not None:
        await db.commit()
        if mevcut.istek != istek or mevcut.govde_ozeti != ozet_degeri:
            raise ApiHatasi(422, "idempotency_uyusmazligi")
        if mevcut.durum_kodu is None:
            raise ApiHatasi(409, "idempotency_isleniyor")
        try:
            yanit = json.loads(mevcut.yanit) if mevcut.yanit else None
        except ValueError:
            yanit = None
        return None, (int(mevcut.durum_kodu), yanit)
    kayit = ApiIdempotency(
        anahtar_id=kimlik.anahtar_id, idem_anahtari=idem, istek=istek[:300], govde_ozeti=ozet_degeri, created_at=an
    )
    db.add(kayit)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ApiHatasi(409, "idempotency_isleniyor")
    return kayit.id, None


async def idem_bitir(db: AsyncSession, kayit_id: Optional[int], durum: int, yanit: Any) -> None:
    if kayit_id is None:
        return
    try:
        await db.execute(
            update(ApiIdempotency)
            .where(ApiIdempotency.id == kayit_id)
            .values(durum_kodu=durum, yanit=json.dumps(yanit, ensure_ascii=False, default=str))
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.warning("Idempotency yanıtı yazılamadı (id=%s)", kayit_id)


async def idem_birak(db: AsyncSession, kayit_id: Optional[int]) -> None:
    """İşlem hata verdi (5xx / beklenmeyen): kayıt silinsin, istemci yeniden deneyebilsin."""
    if kayit_id is None:
        return
    try:
        await db.rollback()
        await db.execute(delete(ApiIdempotency).where(ApiIdempotency.id == kayit_id))
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()


# ---------------------------------------------------------------------------
# Sayfalama
# ---------------------------------------------------------------------------
VARSAYILAN_LIMIT = 25
EN_COK_LIMIT = 100


def cursor_uret(son_id: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{int(son_id)}".encode()).decode().rstrip("=")


def cursor_coz(ham: Optional[str]) -> Optional[int]:
    if ham in (None, ""):
        return None
    try:
        dolgu = "=" * (-len(ham) % 4)
        metin = base64.urlsafe_b64decode((ham + dolgu).encode()).decode()
        surum, deger = metin.split(":", 1)
        if surum != "v1":
            raise ValueError
        sayi = int(deger)
        if sayi < 0:
            raise ValueError
        return sayi
    except (ValueError, UnicodeError, TypeError):
        raise ApiHatasi(400, "cursor_gecersiz")


def guncelleme_kosulu(model: Any, an: Optional[datetime]):
    """`updated_since`: güncelleme zamanı (yoksa oluşturma) bu andan sonra/eşit."""
    if an is None:
        return None
    guncel = getattr(model, "updated_at", None)
    olusma = getattr(model, "created_at", None)
    if guncel is not None and olusma is not None:
        return or_(guncel >= an, and_(guncel.is_(None), olusma >= an))
    return (guncel if guncel is not None else olusma) >= an
