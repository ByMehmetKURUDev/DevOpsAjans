"""Faz 6T — toplantılar: planlama, davet (ICS), girişsiz katılım yanıtı, hatırlatma, tutanak, takvim aboneliği.

Google'sız çalışır
------------------
Davetler e-posta + `.ics` eki (RFC 5545 METHOD:REQUEST / CANCEL) olarak gidiyor; her takvim uygulaması kendi
kaydını açıyor. Senkron için kişiye özel gizli ICS akışı var (`/api/v1/toplanti-takvimi/<jeton>.ics`): Google,
Apple ve Outlook "adresle abone ol" ile çeker. Meet bağlantısı ve çift yönlü Google Takvim senkronu YOK — tek
genişleme noktası `harici_takvim_esitle` (aşağıda): Google OAuth bağlandığında oluşturma/güncelleme/iptal oradan
Google Calendar API'ye taşınır (ve isterse Meet bağlantısı orada üretilip `baglanti` alanına yazılır).

Zaman
-----
`baslangic` UTC saklanır. Panel saat dilimi bilgisi olmayan değeri Europe/Istanbul sayar (`zaman_coz`); müşteri
talebi tarayıcıda UTC'ye çevrilip gelir. Bitiş = başlangıç + süre.

Davet ve SEQUENCE
-----------------
UID kalıcı (`toplanti-<uid>@<alan>`). Davet gönderildikten sonra saat/süre/yer değişirse (düzenleme ya da
erteleme) SEQUENCE +1 ve `guncelleme_bekliyor` işaretlenir; saat değiştiyse katılım yanıtları ve hatırlatma izleri
sıfırlanır. "Davet gönder" (ya da ertelemenin kendisi) aynı UID + yeni SEQUENCE ile METHOD:REQUEST gönderir; iptal
SEQUENCE +1 ile METHOD:CANCEL (STATUS:CANCELLED). ICS: CRLF satır sonu, 75 sekizlik katlama (UTF-8 çok baytlı
karakter bölünmeden, `services/dinamik_qr._katla` — randevu/etkinlik/eğitim ile ortak yardımcı), `\\ ; ,` ve
satır sonu kaçışı, DTSTAMP, UTC (Z).

Katılım yanıtı (girişsiz)
-------------------------
Her davet e-postası kişiye özel bağlantı taşır (`/toplanti-yanit/<jeton>`): `secrets.token_urlsafe(24)` (192 bit),
veritabanında YALNIZ sha256 özeti (`services/imzali_islem.py` deseni). Her davette yenilenir (eski e-postadaki
bağlantı geçersizleşir). Toplantı bitince ya da iptal edilince geçersiz (410). Ham jeton bildirim kayıtlarına da
yazılmaz: gönderimden sonra satırlardaki adres "…" ile değiştirilir. Yanıt POST'unda jeton GÖVDEDE (istek yolu
denetim kaydına yazılıyor).

Hatırlatma
----------
24 saat ve 1 saat önce, davet edilmiş katılımcılara, her biri BİR kez (`hatirlatma_24_at` / `hatirlatma_1_at`
koşullu UPDATE ile "ilk yazan gönderir"). Ücretsiz sunucu uyuduğu için zamanlı iş (`services/zamanli.py`
`toplanti_hatirlatmalari`, her turda; GitHub Actions 10 dk) + yönetici listesi açılınca da denetlenir.

Gizlilik (müşteri)
------------------
Müşteri yalnız etkin hesabının toplantılarını görür (`projeler` izni — toplantılar proje/hesap işinin parçası,
ayrı modül değil). Paylaşılmamış ekip notları ve kararları HİÇBİR müşteri ucunda dönmez (`musteri_sozlugu`);
paylaşılmadan önce yalnız müşteri tarafına atanmış aksiyonlar görünür. Dış katılımcıların adı/e-postası yalnız o
toplantının katılımcısı olan kişiye görünür (diğerlerine sayı).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.toplantilar import (
    AKSIYON_DURUMLARI,
    DURUMLAR,
    KATILIMCI_TURLERI,
    SORUMLU_TURLERI,
    YANITLAR,
    YER_TURLERI,
    ToplantiAksiyonlari,
    Toplantilar,
    ToplantiKatilimcilari,
    ToplantiTakvimAbonelikleri,
    ToplantiTalepleri,
)
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SAAT_DILIMI = "Europe/Istanbul"
BASLIK_SINIRI = 200
GUNDEM_EN_COK = 30
GUNDEM_MADDE_SINIRI = 300
NOT_SINIRI = 20000
KARAR_EN_COK = 50
KARAR_SINIRI = 500
AKSIYON_METNI_SINIRI = 500
AKSIYON_EN_COK = 100
EN_AZ_SURE = 5
EN_COK_SURE = 12 * 60
VARSAYILAN_SURE = 60
KATILIMCI_EN_COK = 50
YANIT_NOTU_SINIRI = 500
IPTAL_NEDENI_SINIRI = 1000
ADRES_SINIRI = 300
BAGLANTI_SINIRI = 500
TALEP_ARALIK_EN_COK = 3
TALEP_KONU_SINIRI = 200
TALEP_NOT_SINIRI = 2000
#: Müşteri başına aynı anda bekleyen en çok talep (kötüye kullanım sınırı).
TALEP_BEKLEYEN_EN_COK = 5
#: Hatırlatma eşikleri (alan, başlangıçtan önce).
HATIRLATMALAR: Tuple[Tuple[str, timedelta], ...] = (
    ("hatirlatma_24_at", timedelta(hours=24)),
    ("hatirlatma_1_at", timedelta(hours=1)),
)
#: Haftalık özet: bu kadar günden eski "notu yazılmamış" toplantı artık sayılmaz.
NOTSUZ_GUN = 30
#: Akışta (ICS aboneliği) en eski toplantı.
AKIS_GECMIS_GUN = 180
AKIS_SINIRI = 500

OLAY_DAVET = "toplanti_davet"
OLAY_IPTAL = "toplanti_iptal"
OLAY_HATIRLATMA = "toplanti_hatirlatma"
OLAY_NOTLAR = "toplanti_notlari"
OLAY_TALEP = "toplanti_talebi"

_EPOSTA = re.compile(r"^[^@\s<>\"',;:]+@[^@\s<>\"',;:]+\.[^@\s<>\"',;:]{2,}$")


class ToplantiHatasi(Exception):
    """Ön yüzün yedi dilde metin kurduğu hata: HTTP durumu + kod (+ ek alanlar)."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------
def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Any) -> Optional[datetime]:
    if not isinstance(an, datetime):
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Any) -> Optional[str]:
    if isinstance(an, datetime):
        return utc(an).isoformat().replace("+00:00", "Z")  # type: ignore[union-attr]
    if isinstance(an, date):
        return an.isoformat()
    return None


def eposta_duzelt(e: Any) -> str:
    return str(e or "").strip().lower()


def eposta_gecerli(e: str) -> bool:
    return bool(e) and len(e) <= 254 and bool(_EPOSTA.match(e))


def saat_dilimi(ad: Optional[str] = None):
    try:
        from zoneinfo import ZoneInfo

        try:
            return ZoneInfo(str(ad or SAAT_DILIMI))
        except Exception:  # noqa: BLE001 - bilinmeyen ad: İstanbul
            return ZoneInfo(SAAT_DILIMI)
    except Exception:  # noqa: BLE001 - tz veritabanı yoksa Türkiye UTC+3 (yaz saati yok)
        return timezone(timedelta(hours=3))


def yerel(an: datetime, ad: Optional[str] = None) -> datetime:
    return utc(an).astimezone(saat_dilimi(ad))  # type: ignore[union-attr]


def zaman_coz(deger: Any, tz_adi: Optional[str] = None, kod: str = "baslangic_gecersiz") -> datetime:
    """ISO metin (Z / ofsetli ya da ofsetsiz) → UTC. Ofsetsiz değer `tz_adi` (varsayılan İstanbul) saatidir."""
    if isinstance(deger, datetime):
        d = deger
    else:
        s = str(deger or "").strip()
        if not s or len(s) > 40:
            raise ToplantiHatasi(400, kod)
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            raise ToplantiHatasi(400, kod)
    if d.tzinfo is None:
        d = d.replace(tzinfo=saat_dilimi(tz_adi))
    d = d.astimezone(timezone.utc).replace(microsecond=0)
    if not (2000 <= d.year <= 2100):
        raise ToplantiHatasi(400, kod)
    return d


def bitis(t: Toplantilar) -> datetime:
    return utc(t.baslangic) + timedelta(minutes=int(t.sure_dk or VARSAYILAN_SURE))  # type: ignore[operator]


def json_liste(ham: Any) -> List[Any]:
    if not ham:
        return []
    try:
        d = json.loads(ham)
    except (TypeError, ValueError):
        return []
    return d if isinstance(d, list) else []


def jeton_ozeti(ham: str) -> str:
    return hashlib.sha256((ham or "").encode("utf-8")).hexdigest()


def jeton_uret() -> Tuple[str, str]:
    ham = secrets.token_urlsafe(24)
    return ham, jeton_ozeti(ham)


def site_adresi() -> str:
    from services.belge_ortak import site_adresi as _s

    return _s()


def yanit_adresi(ham: str) -> str:
    return f"{site_adresi()}/toplanti-yanit/{ham}"


def akis_adresi(ham: str) -> str:
    return f"{site_adresi()}/api/v1/toplanti-takvimi/{ham}.ics"


def eposta_maskele(e: Optional[str]) -> str:
    e = eposta_duzelt(e)
    if "@" not in e:
        return "***"
    yerel_, alan = e.split("@", 1)
    return f"{yerel_[:1]}***@{alan}"


def _metin(deger: Any, sinir: int, *, zorunlu: bool = False, kod: str = "metin_gecersiz") -> Optional[str]:
    d = " ".join(str(deger or "").split()) if deger is not None else ""
    if zorunlu and not d:
        raise ToplantiHatasi(400, kod)
    if len(d) > sinir:
        raise ToplantiHatasi(400, kod)
    return d or None


def _uzun_metin(deger: Any, sinir: int, kod: str) -> Optional[str]:
    d = str(deger or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(d) > sinir:
        raise ToplantiHatasi(400, kod)
    return d or None


def baglanti_dogrula(deger: Any) -> Optional[str]:
    s = str(deger or "").strip()
    if not s:
        return None
    if len(s) > BAGLANTI_SINIRI or not re.match(r"^https?://[^\s<>\"']+$", s, re.I):
        raise ToplantiHatasi(400, "baglanti_gecersiz")
    return s


def jitsi_adresi() -> str:
    """Tahmin edilemez oda adı (128 bit). YALNIZ metin bağlantı: iframe/betik yok, CSP değişmez."""
    return f"https://meet.jit.si/mk-{secrets.token_hex(16)}"


def durum_kategori(t: Toplantilar, an: Optional[datetime] = None) -> str:
    """yaklasan | gecmis | iptal (liste sekmeleri)."""
    an = an or simdi()
    if t.durum == "iptal":
        return "iptal"
    if t.durum == "yapildi" or bitis(t) < an:
        return "gecmis"
    return "yaklasan"


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------
async def toplanti_bul(db: AsyncSession, tid: int) -> Toplantilar:
    t = (await db.execute(select(Toplantilar).where(Toplantilar.id == tid))).scalars().first()
    if t is None:
        raise ToplantiHatasi(404, "bulunamadi")
    return t


async def katilimcilar(db: AsyncSession, tid: int) -> List[ToplantiKatilimcilari]:
    return list((await db.execute(
        select(ToplantiKatilimcilari).where(ToplantiKatilimcilari.toplanti_id == tid).order_by(ToplantiKatilimcilari.id)
    )).scalars().all())


async def aksiyonlar(db: AsyncSession, tid: int) -> List[ToplantiAksiyonlari]:
    return list((await db.execute(
        select(ToplantiAksiyonlari).where(ToplantiAksiyonlari.toplanti_id == tid)
        .order_by(ToplantiAksiyonlari.sira, ToplantiAksiyonlari.id)
    )).scalars().all())


async def toplu_katilimcilar(db: AsyncSession, idler: Sequence[int]) -> Dict[int, List[ToplantiKatilimcilari]]:
    sonuc: Dict[int, List[ToplantiKatilimcilari]] = {int(i): [] for i in idler}
    if not idler:
        return sonuc
    for k in (await db.execute(select(ToplantiKatilimcilari).where(ToplantiKatilimcilari.toplanti_id.in_(list(idler)))
                               .order_by(ToplantiKatilimcilari.id))).scalars().all():
        sonuc.setdefault(int(k.toplanti_id), []).append(k)
    return sonuc


async def ekip_listesi(db: AsyncSession) -> List[Dict[str, str]]:
    from models.staff import Staff

    satirlar = (await db.execute(select(Staff).where(Staff.aktif.isnot(False)).order_by(Staff.ad))).scalars().all()
    gorulen: set = set()
    sonuc = []
    for s in satirlar:
        e = eposta_duzelt(s.email)
        if e and e not in gorulen:
            gorulen.add(e)
            sonuc.append({"ad": s.ad, "email": e})
    return sonuc


async def _ekip_adlari(db: AsyncSession) -> Dict[str, str]:
    return {x["email"]: x["ad"] for x in await ekip_listesi(db)}


async def hesap_adi(db: AsyncSession, eposta: Optional[str]) -> Optional[str]:
    if not eposta:
        return None
    try:
        from services.hesap_ekibi import hesap_adlari

        return (await hesap_adlari(db, [eposta])).get(eposta_duzelt(eposta))
    except Exception:  # noqa: BLE001
        return None


def konum_metni(t: Toplantilar) -> str:
    if t.yer_turu == "yuz_yuze":
        return t.adres or ""
    if t.yer_turu == "telefon":
        return t.telefon or ""
    return t.baglanti or ""


# ---------------------------------------------------------------------------
# Doğrulama ve yazma (yönetici)
# ---------------------------------------------------------------------------
def gundem_duzelt(ham: Any) -> List[str]:
    if ham is None:
        return []
    if isinstance(ham, str):
        ham = [x for x in ham.split("\n")]
    if not isinstance(ham, list):
        raise ToplantiHatasi(400, "gundem_gecersiz")
    maddeler = []
    for m in ham:
        s = " ".join(str(m or "").split())
        if not s:
            continue
        if len(s) > GUNDEM_MADDE_SINIRI:
            raise ToplantiHatasi(400, "gundem_gecersiz")
        maddeler.append(s)
    if len(maddeler) > GUNDEM_EN_COK:
        raise ToplantiHatasi(400, "gundem_gecersiz")
    return maddeler


def kararlar_duzelt(ham: Any) -> List[str]:
    if ham is None:
        return []
    if isinstance(ham, str):
        ham = ham.split("\n")
    if not isinstance(ham, list):
        raise ToplantiHatasi(400, "kararlar_gecersiz")
    sonuc = []
    for m in ham:
        s = " ".join(str(m or "").split())
        if not s:
            continue
        if len(s) > KARAR_SINIRI:
            raise ToplantiHatasi(400, "kararlar_gecersiz")
        sonuc.append(s)
    if len(sonuc) > KARAR_EN_COK:
        raise ToplantiHatasi(400, "kararlar_gecersiz")
    return sonuc


async def _proje_ve_hesap(db: AsyncSession, hesap: str, proje_id: Any) -> Tuple[str, Optional[int]]:
    """Proje seçildiyse müşteriye ait olmalı. Müşteri boşsa projenin müşterisi alınır."""
    if proje_id in (None, "", 0):
        return hesap, None
    try:
        pid = int(proje_id)
    except (TypeError, ValueError):
        raise ToplantiHatasi(400, "proje_gecersiz")
    from models.projects import Projects

    p = (await db.execute(select(Projects).where(Projects.id == pid))).scalars().first()
    if p is None:
        raise ToplantiHatasi(400, "proje_gecersiz")
    sahip = eposta_duzelt(p.client_email)
    if not hesap:
        if not sahip:
            raise ToplantiHatasi(400, "proje_musteri_uyusmuyor")
        return sahip, pid
    if sahip != hesap:
        raise ToplantiHatasi(400, "proje_musteri_uyusmuyor")
    return hesap, pid


async def _aday_dogrula(db: AsyncSession, aday_id: Any) -> Optional[int]:
    if aday_id in (None, "", 0):
        return None
    try:
        aid = int(aday_id)
    except (TypeError, ValueError):
        raise ToplantiHatasi(400, "aday_gecersiz")
    from models.crm import CrmAdaylari

    if (await db.execute(select(CrmAdaylari.id).where(CrmAdaylari.id == aid))).first() is None:
        raise ToplantiHatasi(400, "aday_gecersiz")
    return aid


def _sure(deger: Any) -> int:
    try:
        s = int(deger if deger not in (None, "") else VARSAYILAN_SURE)
    except (TypeError, ValueError):
        raise ToplantiHatasi(400, "sure_gecersiz")
    if s < EN_AZ_SURE or s > EN_COK_SURE:
        raise ToplantiHatasi(400, "sure_gecersiz")
    return s


async def alanlari_uygula(db: AsyncSession, t: Toplantilar, g: Dict[str, Any], *, yeni: bool) -> Dict[str, bool]:
    """Gövdeyi doğrulayıp kayda yazar. Dönen: {"zaman": saat/süre değişti, "yer": yer değişti}."""
    once = (utc(t.baslangic), t.sure_dk, t.yer_turu, t.baglanti, t.adres, t.telefon)

    if yeni or "baslik" in g:
        t.baslik = _metin(g.get("baslik"), BASLIK_SINIRI, zorunlu=True, kod="baslik_gecersiz")  # type: ignore[assignment]
    if yeni or "gundem" in g:
        t.gundem = json.dumps(gundem_duzelt(g.get("gundem")), ensure_ascii=False)
    if yeni or "baslangic" in g:
        t.baslangic = zaman_coz(g.get("baslangic"), g.get("saat_dilimi"))
    if yeni or "sure_dk" in g:
        t.sure_dk = _sure(g.get("sure_dk"))
    if yeni or "yer_turu" in g:
        yt = str(g.get("yer_turu") or "cevrimici")
        if yt not in YER_TURLERI:
            raise ToplantiHatasi(400, "yer_turu_gecersiz")
        t.yer_turu = yt
    if yeni or "baglanti" in g:
        t.baglanti = baglanti_dogrula(g.get("baglanti"))
    if yeni or "adres" in g:
        t.adres = _metin(g.get("adres"), ADRES_SINIRI, kod="adres_gecersiz")
    if yeni or "telefon" in g:
        t.telefon = _metin(g.get("telefon"), 60, kod="telefon_gecersiz")
    if t.yer_turu == "yuz_yuze" and not t.adres:
        raise ToplantiHatasi(400, "adres_gerekli")
    if t.yer_turu == "telefon" and not t.telefon:
        raise ToplantiHatasi(400, "telefon_gerekli")

    if yeni or "hesap_email" in g or "proje_id" in g:
        hesap = eposta_duzelt(g.get("hesap_email") if "hesap_email" in g else t.hesap_email)
        if hesap and not eposta_gecerli(hesap):
            raise ToplantiHatasi(400, "hesap_gecersiz")
        hesap, pid = await _proje_ve_hesap(db, hesap, g.get("proje_id") if "proje_id" in g else t.proje_id)
        t.hesap_email = hesap or None
        t.proje_id = pid
    if yeni or "crm_aday_id" in g:
        t.crm_aday_id = await _aday_dogrula(db, g.get("crm_aday_id"))

    sonra = (utc(t.baslangic), t.sure_dk, t.yer_turu, t.baglanti, t.adres, t.telefon)
    return {"zaman": once[:2] != sonra[:2], "yer": once[2:] != sonra[2:]}


def _katilimci_listesi(ham: Any) -> List[Dict[str, Any]]:
    if ham is None:
        return []
    if not isinstance(ham, list):
        raise ToplantiHatasi(400, "katilimci_gecersiz")
    sonuc: Dict[str, Dict[str, Any]] = {}
    for x in ham:
        if isinstance(x, str):
            x = {"eposta": x}
        if not isinstance(x, dict):
            raise ToplantiHatasi(400, "katilimci_gecersiz")
        e = eposta_duzelt(x.get("eposta") or x.get("email"))
        if not eposta_gecerli(e):
            raise ToplantiHatasi(400, "katilimci_gecersiz", eposta=e[:120])
        tur = str(x.get("tur") or "dis")
        if tur not in KATILIMCI_TURLERI:
            raise ToplantiHatasi(400, "katilimci_gecersiz", eposta=e)
        ad = _metin(x.get("ad"), 120, kod="katilimci_gecersiz")
        sonuc[e] = {"eposta": e, "tur": tur, "ad": ad}
    if len(sonuc) > KATILIMCI_EN_COK:
        raise ToplantiHatasi(400, "katilimci_cok")
    return list(sonuc.values())


async def katilimcilari_yaz(db: AsyncSession, t: Toplantilar, ham: Any) -> List[str]:
    """Listeyi uygular (var olanın yanıtı korunur). Dönen: yeni eklenen e-postalar. Ekip üyesi aktif personel olmalı."""
    liste = _katilimci_listesi(ham)
    ekip = await _ekip_adlari(db)
    for k in liste:
        if k["tur"] == "ekip":
            if k["eposta"] not in ekip:
                raise ToplantiHatasi(400, "ekip_gecersiz", eposta=k["eposta"])
            k["ad"] = k["ad"] or ekip[k["eposta"]]
    mevcut = {k.eposta: k for k in await katilimcilar(db, t.id)} if t.id else {}
    istenen = {k["eposta"] for k in liste}
    for e, k in mevcut.items():
        if e not in istenen:
            await db.delete(k)
    yeni_eklenen = []
    for k in liste:
        var = mevcut.get(k["eposta"])
        if var is not None:
            var.tur = k["tur"]
            var.ad = k["ad"]
        else:
            db.add(ToplantiKatilimcilari(toplanti_id=t.id, tur=k["tur"], eposta=k["eposta"], ad=k["ad"], yanit="bekliyor"))
            yeni_eklenen.append(k["eposta"])
    await db.flush()
    return yeni_eklenen


def zaman_degisti_isle(t: Toplantilar, ks: Iterable[ToplantiKatilimcilari], degisim: Dict[str, bool]) -> None:
    """Davetten sonra saat/yer değişti: SEQUENCE +1, güncelleme daveti bekliyor; saat değiştiyse yanıt/hatırlatma sıfır."""
    if not (degisim.get("zaman") or degisim.get("yer")):
        return
    if t.davet_gonderildi_at is not None:
        t.sira_no = int(t.sira_no or 0) + 1
        t.guncelleme_bekliyor = True
    if degisim.get("zaman"):
        for k in ks:
            k.hatirlatma_24_at = None
            k.hatirlatma_1_at = None
            if t.davet_gonderildi_at is not None:
                k.yanit = "bekliyor"
                k.yanit_notu = None
                k.yanit_at = None
                k.yanit_kaynagi = None


async def cakismalar(db: AsyncSession, bas: datetime, sure_dk: int, ekip_epostalari: Iterable[str],
                     haric_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Aynı ekip üyesinin çakışan (iptal edilmemiş) toplantıları — uyarı, engel değil."""
    epostalar = sorted({eposta_duzelt(e) for e in ekip_epostalari if e})
    if not epostalar:
        return []
    bas = utc(bas)  # type: ignore[assignment]
    son = bas + timedelta(minutes=int(sure_dk))
    adaylar = (await db.execute(
        select(Toplantilar, ToplantiKatilimcilari.eposta)
        .join(ToplantiKatilimcilari, ToplantiKatilimcilari.toplanti_id == Toplantilar.id)
        .where(ToplantiKatilimcilari.eposta.in_(epostalar), Toplantilar.durum != "iptal",
               Toplantilar.baslangic < son, Toplantilar.baslangic > bas - timedelta(minutes=EN_COK_SURE))
    )).all()
    sonuc = []
    for t, e in adaylar:
        if haric_id is not None and int(t.id) == int(haric_id):
            continue
        if bitis(t) > bas:
            sonuc.append({"eposta": e, "toplanti_id": t.id, "baslik": t.baslik, "baslangic": iso(t.baslangic),
                          "sure_dk": t.sure_dk})
    sonuc.sort(key=lambda x: (x["baslangic"] or "", x["eposta"]))
    return sonuc


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def katilimci_sozlugu(k: ToplantiKatilimcilari) -> Dict[str, Any]:
    return {"id": k.id, "tur": k.tur, "eposta": k.eposta, "ad": k.ad, "yanit": k.yanit, "yanit_notu": k.yanit_notu,
            "yanit_at": iso(k.yanit_at), "yanit_kaynagi": k.yanit_kaynagi, "davet_at": iso(k.davet_at),
            "hatirlatma_24_at": iso(k.hatirlatma_24_at), "hatirlatma_1_at": iso(k.hatirlatma_1_at)}


def aksiyon_sozlugu(a: ToplantiAksiyonlari) -> Dict[str, Any]:
    return {"id": a.id, "metin": a.metin, "sorumlu_tur": a.sorumlu_tur, "sorumlu_eposta": a.sorumlu_eposta,
            "son_tarih": a.son_tarih.isoformat() if a.son_tarih else None, "durum": a.durum,
            "tamamlandi_at": iso(a.tamamlandi_at), "tamamlayan_eposta": a.tamamlayan_eposta, "gorev_id": a.gorev_id}


def notlar_html(t: Toplantilar) -> str:
    from services.guvenli_html import markdown_html

    return markdown_html(t.notlar or "") if t.notlar else ""


def ozet_sozlugu(t: Toplantilar, ks: Sequence[ToplantiKatilimcilari], an: Optional[datetime] = None) -> Dict[str, Any]:
    yanitlar: Dict[str, int] = {y: 0 for y in YANITLAR}
    for k in ks:
        yanitlar[k.yanit if k.yanit in yanitlar else "bekliyor"] += 1
    return {
        "id": t.id, "baslik": t.baslik, "baslangic": iso(t.baslangic), "bitis": iso(bitis(t)), "sure_dk": t.sure_dk,
        "yer_turu": t.yer_turu, "baglanti": t.baglanti, "adres": t.adres, "telefon": t.telefon,
        "hesap_email": t.hesap_email, "proje_id": t.proje_id, "crm_aday_id": t.crm_aday_id, "durum": t.durum,
        "kategori": durum_kategori(t, an), "sira_no": t.sira_no, "davet_gonderildi_at": iso(t.davet_gonderildi_at),
        "guncelleme_bekliyor": bool(t.guncelleme_bekliyor), "notlar_paylasildi": bool(t.notlar_paylasildi),
        "notlar_var": bool((t.notlar or "").strip() or json_liste(t.kararlar)), "katilimci_sayisi": len(ks),
        "yanitlar": yanitlar, "ekip": [k.eposta for k in ks if k.tur == "ekip"],
    }


async def yonetici_sozlugu(db: AsyncSession, t: Toplantilar) -> Dict[str, Any]:
    ks = await katilimcilar(db, t.id)
    ak = await aksiyonlar(db, t.id)
    d = ozet_sozlugu(t, ks)
    proje = None
    if t.proje_id:
        from models.projects import Projects

        p = (await db.execute(select(Projects.id, Projects.title).where(Projects.id == t.proje_id))).first()
        proje = {"id": p[0], "baslik": p[1]} if p else None
    aday = None
    if t.crm_aday_id:
        from models.crm import CrmAdaylari

        a = (await db.execute(select(CrmAdaylari.id, CrmAdaylari.ad, CrmAdaylari.email, CrmAdaylari.firma)
                              .where(CrmAdaylari.id == t.crm_aday_id))).first()
        aday = {"id": a[0], "ad": a[1], "email": a[2], "firma": a[3]} if a else None
    d.update({
        "gundem": json_liste(t.gundem), "iptal_nedeni": t.iptal_nedeni, "notlar": t.notlar or "",
        "notlar_html": notlar_html(t), "kararlar": json_liste(t.kararlar), "paylasildi_at": iso(t.paylasildi_at),
        "yapildi_at": iso(t.yapildi_at), "iptal_at": iso(t.iptal_at), "talep_id": t.talep_id,
        "olusturan_eposta": t.olusturan_eposta, "created_at": iso(t.created_at),
        "katilimcilar": [katilimci_sozlugu(k) for k in ks], "aksiyonlar": [aksiyon_sozlugu(a) for a in ak],
        "proje": proje, "aday": aday, "hesap_adi": await hesap_adi(db, t.hesap_email),
    })
    return d


def musteri_sozlugu(t: Toplantilar, ks: Sequence[ToplantiKatilimcilari], ak: Sequence[ToplantiAksiyonlari], kisi: str,
                    *, ayrinti: bool) -> Dict[str, Any]:
    """Müşteri görünümü. PAYLAŞILMAMIŞ NOT/KARAR YOK; dış katılımcılar yalnız katılımcıya; ekip e-postası yok."""
    kisi = eposta_duzelt(kisi)
    ben = next((k for k in ks if k.eposta == kisi), None)
    paylasildi = bool(t.notlar_paylasildi)
    d: Dict[str, Any] = {
        "id": t.id, "baslik": t.baslik, "baslangic": iso(t.baslangic), "bitis": iso(bitis(t)), "sure_dk": t.sure_dk,
        "yer_turu": t.yer_turu, "baglanti": t.baglanti if t.durum != "iptal" else None, "adres": t.adres,
        "telefon": t.telefon, "durum": t.durum, "kategori": durum_kategori(t), "iptal_nedeni": t.iptal_nedeni,
        "katilimci_miyim": ben is not None, "yanitim": ben.yanit if ben else None,
        "yanit_notum": ben.yanit_notu if ben else None, "notlar_paylasildi": paylasildi,
    }
    if not ayrinti:
        d["acik_aksiyon"] = sum(1 for a in ak if a.sorumlu_tur == "musteri" and a.durum == "acik")
        return d
    ekip = [{"ad": k.ad or eposta_maskele(k.eposta), "tur": "ekip", "yanit": k.yanit} for k in ks if k.tur == "ekip"]
    dis = [k for k in ks if k.tur == "dis"]
    if ben is not None:
        dis_liste = [{"ad": k.ad, "eposta": k.eposta, "tur": "dis", "yanit": k.yanit, "ben": k.eposta == kisi} for k in dis]
    else:
        dis_liste = []
    d.update({
        "gundem": json_liste(t.gundem),
        "katilimcilar": ekip + dis_liste,
        "dis_sayisi": len(dis),
        "notlar_html": notlar_html(t) if paylasildi else None,
        "kararlar": json_liste(t.kararlar) if paylasildi else [],
        "aksiyonlar": [
            {**aksiyon_sozlugu(a), "gorev_id": None, "tamamlayan_eposta": None,
             "sorumlu_eposta": a.sorumlu_eposta if a.sorumlu_tur == "musteri" else None,
             "isaretleyebilir": a.sorumlu_tur == "musteri"}
            for a in ak if paylasildi or a.sorumlu_tur == "musteri"
        ],
    })
    return d


# ---------------------------------------------------------------------------
# ICS (RFC 5545)
# ---------------------------------------------------------------------------
def _kacis(metin: Any) -> str:
    from services import dinamik_qr as qr

    return qr._kacis(str(metin or "").replace("\r\n", "\n").replace("\r", "\n"))  # noqa: SLF001 - ortak ICS yardımcısı


def _katla(satir: str) -> str:
    from services import dinamik_qr as qr

    return qr._katla(satir)  # noqa: SLF001 - ortak ICS yardımcısı


def _ics_an(an: datetime) -> str:
    return utc(an).strftime("%Y%m%dT%H%M%SZ")  # type: ignore[union-attr]


def _cn(ad: Any) -> str:
    return '"' + re.sub(r'["\x00-\x1f\x7f]', "", str(ad or ""))[:100] + '"'


def _alan() -> str:
    return (site_adresi().split("://", 1)[-1].split("/", 1)[0] or "mehmetkuru.dev").split(":", 1)[0]


def _duzenleyen(t: Toplantilar) -> str:
    import os

    e = eposta_duzelt(t.olusturan_eposta) or eposta_duzelt(os.environ.get("NOTIFY_FROM_EMAIL")) or "bildirim@mehmetkuru.dev"
    return e if eposta_gecerli(e) else "bildirim@mehmetkuru.dev"


PARTSTAT = {"bekliyor": "NEEDS-ACTION", "katilacak": "ACCEPTED", "katilamayacak": "DECLINED", "belki": "TENTATIVE"}


def _aciklama(t: Toplantilar) -> str:
    satirlar = []
    gundem = json_liste(t.gundem)
    if gundem:
        satirlar.append("Gündem / Agenda:")
        satirlar += [f"{i}. {m}" for i, m in enumerate(gundem, 1)]
    if t.yer_turu == "cevrimici" and t.baglanti:
        satirlar.append(f"Bağlantı / Link: {t.baglanti}")
    if t.yer_turu == "telefon" and t.telefon:
        satirlar.append(f"Telefon / Phone: {t.telefon}")
    if t.durum == "iptal" and t.iptal_nedeni:
        satirlar.append(f"İptal nedeni / Reason: {t.iptal_nedeni}")
    return "\n".join(satirlar)


def _vevent(t: Toplantilar, ks: Sequence[ToplantiKatilimcilari], an: datetime, yontem: str) -> List[str]:
    iptal = yontem == "CANCEL" or t.durum == "iptal"
    satirlar = [
        "BEGIN:VEVENT",
        f"UID:toplanti-{t.uid}@{_alan()}",
        f"SEQUENCE:{int(t.sira_no or 0)}",
        "DTSTAMP:" + _ics_an(an),
        "DTSTART:" + _ics_an(t.baslangic),
        "DTEND:" + _ics_an(bitis(t)),
        f"SUMMARY:{_kacis(t.baslik)}",
        "STATUS:" + ("CANCELLED" if iptal else "CONFIRMED"),
        "TRANSP:OPAQUE",
    ]
    aciklama = _aciklama(t)
    if aciklama:
        satirlar.append(f"DESCRIPTION:{_kacis(aciklama)}")
    konum = konum_metni(t)
    if konum:
        satirlar.append(f"LOCATION:{_kacis(konum)}")
    if t.yer_turu == "cevrimici" and t.baglanti:
        satirlar.append(f"URL:{t.baglanti}")
    if yontem != "PUBLISH":
        satirlar.append(f"ORGANIZER;CN={_cn('By Mehmet KURU Dev')}:mailto:{_duzenleyen(t)}")
        for k in ks:
            durum = PARTSTAT.get(k.yanit, "NEEDS-ACTION")
            satirlar.append(
                f"ATTENDEE;CN={_cn(k.ad or k.eposta)};CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT={durum};"
                f"RSVP=FALSE:mailto:{k.eposta}"
            )
    satirlar.append("END:VEVENT")
    return satirlar


def ics_uret(t: Toplantilar, ks: Sequence[ToplantiKatilimcilari], yontem: str = "PUBLISH",
             an: Optional[datetime] = None) -> str:
    """Tek toplantı. `yontem`: REQUEST (davet / güncelleme), CANCEL (iptal), PUBLISH (indirme)."""
    if yontem not in ("REQUEST", "CANCEL", "PUBLISH"):
        raise ValueError(yontem)
    an = an or simdi()
    satirlar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//mehmetkuru.dev//Toplanti//TR", "CALSCALE:GREGORIAN",
                f"METHOD:{yontem}"]
    satirlar += _vevent(t, ks, an, yontem)
    satirlar.append("END:VCALENDAR")
    return "\r\n".join(_katla(s) for s in satirlar) + "\r\n"


def ics_akisi(liste: Sequence[Tuple[Toplantilar, Sequence[ToplantiKatilimcilari]]], takvim_adi: str,
              an: Optional[datetime] = None) -> str:
    """Abonelik akışı (METHOD:PUBLISH, çok VEVENT; iptaller STATUS:CANCELLED ile — takvim kaydı düşer)."""
    an = an or simdi()
    satirlar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//mehmetkuru.dev//Toplanti//TR", "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH", f"X-WR-CALNAME:{_kacis(takvim_adi)}", f"X-WR-TIMEZONE:{SAAT_DILIMI}",
                "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    for t, ks in liste:
        satirlar += _vevent(t, ks, an, "PUBLISH")
    satirlar.append("END:VCALENDAR")
    return "\r\n".join(_katla(s) for s in satirlar) + "\r\n"


def ics_dosya_adi(t: Toplantilar) -> str:
    return f"toplanti-{t.id}.ics"


# ---------------------------------------------------------------------------
# Google genişleme noktası
# ---------------------------------------------------------------------------
async def harici_takvim_esitle(db: AsyncSession, t: Toplantilar, olay: str) -> None:
    """TEK genişleme noktası (Google Takvim / Meet) — bugün BİLEREK boş.

    `olay`: "olusturuldu" | "guncellendi" | "ertelendi" | "iptal" | "silindi". Google OAuth bağlandığında
    (`services/baglantilar.py` / `services/google_esitleme.py` deseni) burada Google Calendar API'de etkinlik
    oluşturulur/güncellenir/iptal edilir (aynı `uid`), istenirse `conferenceData` ile Meet bağlantısı üretilip
    `t.baglanti`'ya yazılır. Çift yönlü senkron (Google'dan gelen değişiklik) de buradan başlar. Hata FIRLATMAMALI:
    toplantı işlemi dış takvim yüzünden düşmesin.
    """
    return None


# ---------------------------------------------------------------------------
# E-postalar (davet / güncelleme / iptal / hatırlatma) — Türkçe + İngilizce
# ---------------------------------------------------------------------------
def zaman_metni(t: Toplantilar) -> str:
    y = yerel(t.baslangic)
    return f"{y:%d.%m.%Y %H:%M} ({SAAT_DILIMI}) · {int(t.sure_dk or 0)} dk/min"


def _yer_satiri(t: Toplantilar) -> str:
    if t.yer_turu == "cevrimici":
        return f"Çevrim içi / Online: {t.baglanti}" if t.baglanti else "Çevrim içi / Online"
    if t.yer_turu == "telefon":
        return f"Telefon / Phone: {t.telefon or '—'}"
    return f"Adres / Address: {t.adres or '—'}"


def _govde(t: Toplantilar, giris_tr: str, giris_en: str, *, yanit_baglantisi: Optional[str] = None,
           panel: Optional[str] = None) -> str:
    gundem = json_liste(t.gundem)
    parcalar = [f"{giris_tr}\n{giris_en}", "", f"{t.baslik}", zaman_metni(t), _yer_satiri(t)]
    if gundem:
        parcalar += ["", "Gündem / Agenda:"] + [f"{i}. {m}" for i, m in enumerate(gundem, 1)]
    if t.durum == "iptal" and t.iptal_nedeni:
        parcalar += ["", f"İptal nedeni / Reason: {t.iptal_nedeni}"]
    if yanit_baglantisi:
        parcalar += ["", "Katılım yanıtınız (giriş gerekmez) / Your RSVP (no login needed):", yanit_baglantisi]
    if panel:
        parcalar += ["", f"Panel: {panel}"]
    if t.durum != "iptal":
        parcalar += ["", "Takviminize eklemek için ekteki .ics dosyasını açın. / Open the attached .ics file to add it to your calendar."]
    parcalar += ["", "— By Mehmet KURU Dev"]
    return "\n".join(parcalar)


def _panel_baglantisi(k: ToplantiKatilimcilari, t: Toplantilar) -> str:
    if k.tur == "ekip":
        return f"/admin?sekme=toplantilar&toplanti={t.id}"
    return "/client?sekme=toplantilar"


async def _gonder(db: AsyncSession, *, olay: str, k: ToplantiKatilimcilari, t: Toplantilar, baslik: str, govde: str,
                  ics: Optional[str], yontem: str, gizli: Optional[str] = None) -> bool:
    """Tek alıcıya dağıtım. `gizli` (ham yanıt bağlantısı) dağıtımdan sonra kayıtlardan silinir."""
    from services.notify import dispatch

    ek = None
    if ics:
        ek = {"ekler": [{"dosya_adi": "toplanti.ics" if yontem != "CANCEL" else "toplanti-iptal.ics", "icerik": ics,
                         "tur": f"text/calendar; method={yontem}; charset=UTF-8"}]}
    try:
        satirlar = await dispatch(
            db, event_type=olay, title=baslik, body=govde,
            recipients=[{"email": k.eposta, "role": "admin" if k.tur == "ekip" else "client"}],
            link=_panel_baglantisi(k, t), ref_type="toplanti", ref_id=t.id, eposta_ek=ek,
        )
        if gizli and satirlar:
            for s in satirlar:
                if s.body:
                    s.body = s.body.replace(gizli, "…")
                if s.title:
                    s.title = s.title.replace(gizli, "…")
            await db.commit()
        return any(getattr(s, "channel", "") == "email" and getattr(s, "delivery_status", "") == "sent" for s in satirlar)
    except Exception:  # noqa: BLE001 - bir alıcı diğerlerini düşürmesin
        logger.exception("Toplantı bildirimi gönderilemedi")
        return False


async def davet_gonder(db: AsyncSession, t: Toplantilar, *, yalniz: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Davet (ya da SEQUENCE > 0 ise güncelleme daveti): her katılımcıya kendi yanıt bağlantısı + METHOD:REQUEST.

    Yanıt jetonları burada yenilenir (önce özetler commit edilir, sonra e-postalar). Dönen: {gonderilen, eposta}.
    """
    if t.durum == "iptal":
        raise ToplantiHatasi(409, "iptal_edildi")
    if t.durum == "yapildi":
        raise ToplantiHatasi(409, "yapildi")
    ks = await katilimcilar(db, t.id)
    hedef = {eposta_duzelt(e) for e in yalniz} if yalniz is not None else None
    secilen = [k for k in ks if hedef is None or k.eposta in hedef]
    if not secilen:
        raise ToplantiHatasi(400, "katilimci_yok")
    an = simdi()
    hamlar: Dict[int, str] = {}
    for k in secilen:
        ham, ozet = jeton_uret()
        k.yanit_jeton_ozeti = ozet
        k.davet_at = an
        hamlar[k.id] = ham
    guncelleme = t.davet_gonderildi_at is not None and int(t.sira_no or 0) > 0
    t.davet_gonderildi_at = an
    if hedef is None:
        t.guncelleme_bekliyor = False
    await db.commit()
    for k in ks:
        await db.refresh(k)
    await db.refresh(t)
    ics = ics_uret(t, ks, "REQUEST", an)
    if guncelleme:
        giris_tr, giris_en = "Toplantı güncellendi.", "The meeting has been updated."
        konu = f"Toplantı güncellendi / Meeting updated: {t.baslik} — {yerel(t.baslangic):%d.%m.%Y %H:%M}"
    else:
        giris_tr, giris_en = "Bir toplantıya davet edildiniz.", "You are invited to a meeting."
        konu = f"Toplantı daveti / Meeting invitation: {t.baslik} — {yerel(t.baslangic):%d.%m.%Y %H:%M}"
    eposta = 0
    for k in secilen:
        baglanti = yanit_adresi(hamlar[k.id])
        govde = _govde(t, giris_tr, giris_en, yanit_baglantisi=baglanti)
        if await _gonder(db, olay=OLAY_DAVET, k=k, t=t, baslik=konu, govde=govde, ics=ics, yontem="REQUEST", gizli=baglanti):
            eposta += 1
    await harici_takvim_esitle(db, t, "guncellendi" if guncelleme else "olusturuldu")
    return {"gonderilen": len(secilen), "eposta": eposta, "guncelleme": guncelleme}


async def iptal_gonder(db: AsyncSession, t: Toplantilar) -> Dict[str, Any]:
    """İptal: davet edilmiş katılımcılara METHOD:CANCEL (aynı UID, artmış SEQUENCE)."""
    ks = await katilimcilar(db, t.id)
    davetliler = [k for k in ks if k.davet_at is not None]
    if not davetliler:
        return {"gonderilen": 0, "eposta": 0}
    an = simdi()
    ics = ics_uret(t, ks, "CANCEL", an)
    konu = f"Toplantı iptal edildi / Meeting cancelled: {t.baslik} — {yerel(t.baslangic):%d.%m.%Y %H:%M}"
    govde = _govde(t, "Bu toplantı iptal edildi.", "This meeting has been cancelled.")
    eposta = 0
    for k in davetliler:
        if await _gonder(db, olay=OLAY_IPTAL, k=k, t=t, baslik=konu, govde=govde, ics=ics, yontem="CANCEL"):
            eposta += 1
    return {"gonderilen": len(davetliler), "eposta": eposta}


async def hatirlatmalari_gonder(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """24 saat ve 1 saat önce, davet edilmiş katılımcılara, her biri BİR kez (koşullu UPDATE)."""
    an = an or simdi()
    adaylar = (await db.execute(
        select(Toplantilar).where(
            Toplantilar.durum.in_(("planlandi", "ertelendi")), Toplantilar.davet_gonderildi_at.isnot(None),
            Toplantilar.baslangic > an, Toplantilar.baslangic <= an + timedelta(hours=24),
        ).order_by(Toplantilar.baslangic).limit(200)
    )).scalars().all()
    sayac = {"24": 0, "1": 0}
    for t in adaylar:
        kalan = utc(t.baslangic) - an  # type: ignore[operator]
        # Yalnız en yakın eşik: 1 saatten az kaldıysa 24 saatlik artık gönderilmez (ikisi birden gitmesin).
        alan, etiket = ("hatirlatma_1_at", "1") if kalan <= timedelta(hours=1) else ("hatirlatma_24_at", "24")
        sutun = getattr(ToplantiKatilimcilari, alan)
        ks = (await db.execute(select(ToplantiKatilimcilari).where(
            ToplantiKatilimcilari.toplanti_id == t.id, ToplantiKatilimcilari.davet_at.isnot(None), sutun.is_(None),
            ToplantiKatilimcilari.yanit != "katilamayacak",
        ))).scalars().all()
        for k in ks:
            kazandi = (await db.execute(
                update(ToplantiKatilimcilari).where(ToplantiKatilimcilari.id == k.id, sutun.is_(None))
                .values(**{alan: an}).execution_options(synchronize_session=False)
            )).rowcount
            await db.commit()
            if int(kazandi or 0) != 1:
                continue
            if etiket == "1":
                tr, en = "Toplantınız 1 saat içinde başlıyor.", "Your meeting starts within 1 hour."
            else:
                tr, en = "Toplantınız yarın bu saatlerde.", "Your meeting is about 24 hours away."
            konu = f"Hatırlatma / Reminder: {t.baslik} — {yerel(t.baslangic):%d.%m.%Y %H:%M}"
            await _gonder(db, olay=OLAY_HATIRLATMA, k=k, t=t, baslik=konu,
                          govde=_govde(t, tr, en, panel=site_adresi() + _panel_baglantisi(k, t)), ics=None, yontem="PUBLISH")
            sayac[etiket] += 1
    return {"hatirlatma_24": sayac["24"], "hatirlatma_1": sayac["1"]}


# ---------------------------------------------------------------------------
# Katılım yanıtı
# ---------------------------------------------------------------------------
async def yanit_coz(db: AsyncSession, ham: str) -> Tuple[Toplantilar, ToplantiKatilimcilari]:
    s = str(ham or "").strip()
    if not s or len(s) > 100:
        raise ToplantiHatasi(404, "gecersiz")
    k = (await db.execute(select(ToplantiKatilimcilari).where(
        ToplantiKatilimcilari.yanit_jeton_ozeti == jeton_ozeti(s)))).scalars().first()
    if k is None:
        raise ToplantiHatasi(404, "gecersiz")
    t = (await db.execute(select(Toplantilar).where(Toplantilar.id == k.toplanti_id))).scalars().first()
    if t is None:
        raise ToplantiHatasi(404, "gecersiz")
    if t.durum == "iptal":
        raise ToplantiHatasi(410, "iptal")
    if bitis(t) <= simdi() or t.durum == "yapildi":
        raise ToplantiHatasi(410, "suresi_doldu")
    return t, k


def yanit_dogrula(yanit: Any, not_: Any) -> Tuple[str, Optional[str]]:
    y = str(yanit or "")
    if y not in YANITLAR or y == "bekliyor":
        raise ToplantiHatasi(400, "yanit_gecersiz")
    n = _uzun_metin(not_, YANIT_NOTU_SINIRI, "not_uzun")
    return y, n


async def yanit_yaz(db: AsyncSession, t: Toplantilar, k: ToplantiKatilimcilari, yanit: Any, not_: Any, kaynak: str) -> None:
    y, n = yanit_dogrula(yanit, not_)
    if t.durum == "iptal":
        raise ToplantiHatasi(410, "iptal")
    if bitis(t) <= simdi() or t.durum == "yapildi":
        raise ToplantiHatasi(410, "suresi_doldu")
    k.yanit = y
    k.yanit_notu = n
    k.yanit_at = simdi()
    k.yanit_kaynagi = kaynak
    await db.commit()


def acik_sozluk(t: Toplantilar, k: ToplantiKatilimcilari) -> Dict[str, Any]:
    """Girişsiz yanıt sayfası: yalnız bu kişinin göreceği kadar (diğer katılımcılar yok)."""
    return {"baslik": t.baslik, "baslangic": iso(t.baslangic), "bitis": iso(bitis(t)), "sure_dk": t.sure_dk,
            "yer_turu": t.yer_turu, "baglanti": t.baglanti, "adres": t.adres, "telefon": t.telefon,
            "gundem": json_liste(t.gundem), "durum": t.durum, "ad": k.ad, "eposta": eposta_maskele(k.eposta),
            "yanit": k.yanit, "yanit_notu": k.yanit_notu, "yanit_at": iso(k.yanit_at), "saat_dilimi": SAAT_DILIMI}


# ---------------------------------------------------------------------------
# Durum geçişleri
# ---------------------------------------------------------------------------
async def ertele(db: AsyncSession, t: Toplantilar, g: Dict[str, Any]) -> Dict[str, bool]:
    if t.durum in ("iptal", "yapildi"):
        raise ToplantiHatasi(409, "durum_gecersiz")
    yeni_bas = zaman_coz(g.get("baslangic"), g.get("saat_dilimi"))
    yeni_sure = _sure(g.get("sure_dk")) if g.get("sure_dk") not in (None, "") else int(t.sure_dk or VARSAYILAN_SURE)
    if yeni_bas == utc(t.baslangic) and yeni_sure == t.sure_dk:
        raise ToplantiHatasi(400, "tarih_ayni")
    t.baslangic = yeni_bas
    t.sure_dk = yeni_sure
    t.durum = "ertelendi"
    ks = await katilimcilar(db, t.id)
    # Erteleme her zaman yeni SEQUENCE (davet gitmemiş olsa da: takvime indirilmiş kopya güncellensin).
    davetli = t.davet_gonderildi_at is not None
    if not davetli:
        t.sira_no = int(t.sira_no or 0) + 1
    zaman_degisti_isle(t, ks, {"zaman": True})
    return {"zaman": True}


async def iptal_et(db: AsyncSession, t: Toplantilar, neden: Any) -> None:
    if t.durum == "iptal":
        raise ToplantiHatasi(409, "iptal_edildi")
    if t.durum == "yapildi":
        raise ToplantiHatasi(409, "durum_gecersiz")
    n = _uzun_metin(neden, IPTAL_NEDENI_SINIRI, "neden_gecersiz")
    if not n:
        raise ToplantiHatasi(400, "neden_gerekli")
    t.durum = "iptal"
    t.iptal_nedeni = n
    t.iptal_at = simdi()
    t.sira_no = int(t.sira_no or 0) + 1
    t.guncelleme_bekliyor = False


async def yapildi_isaretle(db: AsyncSession, t: Toplantilar) -> None:
    if t.durum == "iptal":
        raise ToplantiHatasi(409, "iptal_edildi")
    if t.durum == "yapildi":
        return
    if utc(t.baslangic) > simdi():  # type: ignore[operator]
        raise ToplantiHatasi(409, "henuz_baslamadi")
    t.durum = "yapildi"
    t.yapildi_at = simdi()
    t.guncelleme_bekliyor = False


async def notlari_paylas(db: AsyncSession, t: Toplantilar, paylas: bool) -> bool:
    """Dönen: müşteriye bildirim gitmeli mi (ilk kez paylaşıldı)."""
    if paylas and not t.hesap_email:
        raise ToplantiHatasi(400, "musteri_yok")
    ilk = paylas and not t.notlar_paylasildi
    t.notlar_paylasildi = bool(paylas)
    if ilk:
        t.paylasildi_at = simdi()
    await db.commit()
    return ilk


async def paylasim_bildir(db: AsyncSession, t: Toplantilar) -> None:
    from services.notify import dispatch, render

    if not t.hesap_email:
        return
    try:
        baslik, govde = await render(
            db, OLAY_NOTLAR,
            f"Toplantı notları paylaşıldı / Meeting notes shared: {t.baslik}",
            (f"“{t.baslik}” ({yerel(t.baslangic):%d.%m.%Y}) toplantısının notları ve kararları panelinizde.\n\n"
             f"The notes and decisions of the meeting “{t.baslik}” are in your panel."),
            {"baslik": t.baslik, "tarih": f"{yerel(t.baslangic):%d.%m.%Y}"},
        )
        await dispatch(db, event_type=OLAY_NOTLAR, title=baslik, body=govde,
                       recipients=[{"email": t.hesap_email, "role": "client"}], link="/client?sekme=toplantilar",
                       ref_type="toplanti", ref_id=t.id)
    except Exception:  # noqa: BLE001
        logger.exception("Toplantı notu paylaşım bildirimi gönderilemedi")


# ---------------------------------------------------------------------------
# Aksiyonlar ve göreve dönüştürme
# ---------------------------------------------------------------------------
async def aksiyon_uygula(db: AsyncSession, t: Toplantilar, a: ToplantiAksiyonlari, g: Dict[str, Any], *, yeni: bool) -> None:
    if yeni or "metin" in g:
        a.metin = _metin(g.get("metin"), AKSIYON_METNI_SINIRI, zorunlu=True, kod="aksiyon_gecersiz")  # type: ignore[assignment]
    if yeni or "sorumlu_tur" in g or "sorumlu_eposta" in g:
        tur = str(g.get("sorumlu_tur") or a.sorumlu_tur or "ekip")
        if tur not in SORUMLU_TURLERI:
            raise ToplantiHatasi(400, "sorumlu_gecersiz")
        e = eposta_duzelt(g.get("sorumlu_eposta") if "sorumlu_eposta" in g else a.sorumlu_eposta)
        if tur == "ekip":
            if e and e not in await _ekip_adlari(db):
                raise ToplantiHatasi(400, "sorumlu_gecersiz")
        else:
            if not t.hesap_email:
                raise ToplantiHatasi(400, "musteri_yok")
            if e and not eposta_gecerli(e):
                raise ToplantiHatasi(400, "sorumlu_gecersiz")
        a.sorumlu_tur = tur
        a.sorumlu_eposta = e or None
    if yeni or "son_tarih" in g:
        st = g.get("son_tarih")
        if st in (None, ""):
            a.son_tarih = None
        else:
            try:
                a.son_tarih = date.fromisoformat(str(st)[:10])
            except ValueError:
                raise ToplantiHatasi(400, "tarih_gecersiz")
    if "durum" in g:
        d = str(g.get("durum") or "")
        if d not in AKSIYON_DURUMLARI:
            raise ToplantiHatasi(400, "durum_gecersiz")
        if d != a.durum:
            a.durum = d
            a.tamamlandi_at = simdi() if d == "tamamlandi" else None


async def aksiyon_bul(db: AsyncSession, aid: int) -> Tuple[ToplantiAksiyonlari, Toplantilar]:
    a = (await db.execute(select(ToplantiAksiyonlari).where(ToplantiAksiyonlari.id == aid))).scalars().first()
    if a is None:
        raise ToplantiHatasi(404, "bulunamadi")
    t = await toplanti_bul(db, a.toplanti_id)
    return a, t


async def goreve_donustur(db: AsyncSession, a: ToplantiAksiyonlari, t: Toplantilar, ben: Optional[str]) -> int:
    """Aksiyon → proje görevi (mevcut görev tablosu/servisi). Çift dönüştürme koşullu UPDATE ile engellenir."""
    from models.proje_gorevleri import ProjectTasks
    from services import gorevler as gs

    if not t.proje_id:
        raise ToplantiHatasi(400, "proje_yok")
    if a.gorev_id:
        raise ToplantiHatasi(409, "zaten_gorev", gorev_id=a.gorev_id)
    proje = await gs.proje_bul(db, t.proje_id)
    # Kilit: gorev_id'yi geçici -id ile işaretle (yalnız boşsa). Aynı anda gelen ikinci istek 0 satır görür.
    kilit = (await db.execute(
        update(ToplantiAksiyonlari).where(ToplantiAksiyonlari.id == a.id, ToplantiAksiyonlari.gorev_id.is_(None))
        .values(gorev_id=-int(a.id)).execution_options(synchronize_session=False)
    )).rowcount
    if int(kilit or 0) != 1:
        await db.rollback()
        raise ToplantiHatasi(409, "zaten_gorev")
    sira = (await db.execute(
        select(func.coalesce(func.max(ProjectTasks.sira), -1)).where(ProjectTasks.proje_id == proje.id,
                                                                  ProjectTasks.durum == "yapilacak")
    )).scalar()
    atanan = a.sorumlu_eposta if a.sorumlu_tur == "ekip" and a.sorumlu_eposta else None
    aciklama = f"Toplantı: {t.baslik} ({yerel(t.baslangic):%d.%m.%Y})"
    if a.sorumlu_tur == "musteri":
        aciklama += "\nSorumlu: müşteri" + (f" ({a.sorumlu_eposta})" if a.sorumlu_eposta else "")
    g = ProjectTasks(
        proje_id=proje.id, baslik=a.metin[:200], aciklama=aciklama, durum="yapilacak", oncelik="normal",
        atanan=atanan, bitis_tarihi=a.son_tarih, sira=int(sira if sira is not None else -1) + 1,
        musteriye_gorunur=a.sorumlu_tur == "musteri", kilometre_tasi=False, harcanan_saat=0.0,
        etiketler=json.dumps(["toplanti"]), olusturan_eposta=ben,
    )
    db.add(g)
    await db.flush()
    await db.execute(update(ToplantiAksiyonlari).where(ToplantiAksiyonlari.id == a.id)
                     .values(gorev_id=g.id).execution_options(synchronize_session=False))
    await db.commit()
    return int(g.id)


# ---------------------------------------------------------------------------
# Silme (çöp kutusu)
# ---------------------------------------------------------------------------
async def sil(db: AsyncSession, t: Toplantilar) -> None:
    """ORM silme: toplantı + katılımcılar + aksiyonlar AYNI işlemde → çöp kutusunda birlikte, birlikte geri gelir."""
    # Önce hepsi okunur (ara sorgunun autoflush'ı çocukları ebeveynden önce silip çöpe düşürmesin), ebeveyn önce.
    ks = await katilimcilar(db, t.id)
    ak = await aksiyonlar(db, t.id)
    await db.delete(t)
    for x in (*ks, *ak):
        await db.delete(x)
    await db.commit()


# ---------------------------------------------------------------------------
# Müşteri: talepler
# ---------------------------------------------------------------------------
def araliklari_duzelt(ham: Any) -> List[Dict[str, str]]:
    if not isinstance(ham, list) or not ham:
        raise ToplantiHatasi(400, "aralik_gerekli")
    if len(ham) > TALEP_ARALIK_EN_COK:
        raise ToplantiHatasi(400, "aralik_cok")
    an = simdi()
    sonuc = []
    for x in ham:
        if not isinstance(x, dict):
            raise ToplantiHatasi(400, "aralik_gecersiz")
        b = zaman_coz(x.get("bas"), "UTC", kod="aralik_gecersiz")
        s = zaman_coz(x.get("bit"), "UTC", kod="aralik_gecersiz")
        if s <= b or s - b > timedelta(hours=12):
            raise ToplantiHatasi(400, "aralik_gecersiz")
        if s <= an:
            raise ToplantiHatasi(400, "aralik_gecmis")
        sonuc.append({"bas": iso(b), "bit": iso(s)})
    return sonuc  # type: ignore[return-value]


async def talep_olustur(db: AsyncSession, hesap: str, kisi: str, g: Dict[str, Any]) -> ToplantiTalepleri:
    konu = _metin(g.get("konu"), TALEP_KONU_SINIRI, zorunlu=True, kod="konu_gecersiz")
    araliklar = araliklari_duzelt(g.get("araliklar"))
    notlar = _uzun_metin(g.get("not"), TALEP_NOT_SINIRI, "not_uzun")
    bekleyen = (await db.execute(select(func.count(ToplantiTalepleri.id)).where(
        ToplantiTalepleri.hesap_email == hesap, ToplantiTalepleri.durum == "bekliyor"))).scalar() or 0
    if int(bekleyen) >= TALEP_BEKLEYEN_EN_COK:
        raise ToplantiHatasi(429, "talep_cok")
    t = ToplantiTalepleri(hesap_email=hesap, kisi_email=kisi, konu=konu, araliklar=json.dumps(araliklar),
                          notlar=notlar, durum="bekliyor")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def talep_bildir(db: AsyncSession, t: ToplantiTalepleri) -> None:
    from services.notify import admin_recipients, dispatch, render

    try:
        baslik, govde = await render(
            db, OLAY_TALEP, f"Toplantı talebi: {t.konu}",
            f"{t.kisi_email} ({t.hesap_email}) bir toplantı istedi: {t.konu}\n\nGelen kutusunda: Toplantı planla.",
            {"konu": t.konu, "kisi": t.kisi_email, "hesap": t.hesap_email},
        )
        await dispatch(db, event_type=OLAY_TALEP, title=baslik, body=govde, recipients=await admin_recipients(db),
                       link=f"/admin?sekme=gelenKutusu&kaynak=toplanti_talebi&oge=toplanti_talebi:{t.id}", ref_type="toplanti_talebi",
                       ref_id=t.id)
    except Exception:  # noqa: BLE001
        logger.exception("Toplantı talebi bildirimi gönderilemedi")


def talep_sozlugu(t: ToplantiTalepleri) -> Dict[str, Any]:
    return {"id": t.id, "hesap_email": t.hesap_email, "kisi_email": t.kisi_email, "konu": t.konu,
            "araliklar": json_liste(t.araliklar), "not": t.notlar, "durum": t.durum, "toplanti_id": t.toplanti_id,
            "created_at": iso(t.created_at), "kapandi_at": iso(t.kapandi_at)}


async def talep_bul(db: AsyncSession, tid: int) -> ToplantiTalepleri:
    t = (await db.execute(select(ToplantiTalepleri).where(ToplantiTalepleri.id == tid))).scalars().first()
    if t is None:
        raise ToplantiHatasi(404, "bulunamadi")
    return t


async def talep_kapat(db: AsyncSession, t: ToplantiTalepleri, *, toplanti_id: Optional[int] = None) -> None:
    """Planlanınca (toplantı bağlanır) ya da elle kapatılınca. Kapalı talep elle yeniden kapatılmaz."""
    if toplanti_id is None and t.durum != "bekliyor":
        return
    t.durum = "planlandi" if toplanti_id else "kapandi"
    if toplanti_id:
        t.toplanti_id = toplanti_id
    t.kapandi_at = simdi()


# ---------------------------------------------------------------------------
# Takvim aboneliği (gizli ICS akışı)
# ---------------------------------------------------------------------------
async def abonelik_bul(db: AsyncSession, kisi: str) -> Optional[ToplantiTakvimAbonelikleri]:
    return (await db.execute(select(ToplantiTakvimAbonelikleri).where(
        ToplantiTakvimAbonelikleri.kisi_email == eposta_duzelt(kisi)))).scalars().first()


async def abonelik_uret(db: AsyncSession, kisi: str, tur: str, olusturan: Optional[str]) -> str:
    """Yeni (ya da yeniden üretilmiş) akış adresi — ham jeton YALNIZ burada döner; eski adres hemen 404."""
    kisi = eposta_duzelt(kisi)
    if not eposta_gecerli(kisi):
        raise ToplantiHatasi(400, "eposta_gecersiz")
    ham, ozet = jeton_uret()
    a = await abonelik_bul(db, kisi)
    if a is None:
        db.add(ToplantiTakvimAbonelikleri(kisi_email=kisi, tur=tur, jeton_ozeti=ozet, olusturan_eposta=olusturan))
    else:
        a.jeton_ozeti = ozet
        a.tur = tur
        a.olusturan_eposta = olusturan
        a.created_at = simdi()
        a.son_erisim_at = None
    await db.commit()
    return akis_adresi(ham)


async def abonelik_iptal(db: AsyncSession, kisi: str) -> bool:
    a = await abonelik_bul(db, kisi)
    if a is None:
        return False
    await db.delete(a)
    await db.commit()
    return True


def abonelik_sozlugu(a: Optional[ToplantiTakvimAbonelikleri]) -> Dict[str, Any]:
    if a is None:
        return {"var": False}
    return {"var": True, "tur": a.tur, "created_at": iso(a.created_at), "son_erisim_at": iso(a.son_erisim_at)}


async def kisinin_toplantilari(db: AsyncSession, kisi: str, *, gecmis_gun: int = AKIS_GECMIS_GUN,
                               sinir: int = AKIS_SINIRI) -> List[Toplantilar]:
    """Kişinin katılımcı (ya da düzenleyen) olduğu toplantılar — akış için."""
    kisi = eposta_duzelt(kisi)
    alt = select(ToplantiKatilimcilari.toplanti_id).where(ToplantiKatilimcilari.eposta == kisi)
    return list((await db.execute(
        select(Toplantilar).where(
            or_(Toplantilar.id.in_(alt), func.lower(func.coalesce(Toplantilar.olusturan_eposta, "")) == kisi),
            Toplantilar.baslangic >= simdi() - timedelta(days=gecmis_gun),
        ).order_by(Toplantilar.baslangic).limit(sinir)
    )).scalars().all())


async def akis_uret(db: AsyncSession, ham: str) -> Optional[str]:
    """Jeton geçerliyse kişinin akışı (ICS), değilse None (uç 404)."""
    s = str(ham or "").strip()
    if not s or len(s) > 100:
        return None
    a = (await db.execute(select(ToplantiTakvimAbonelikleri).where(
        ToplantiTakvimAbonelikleri.jeton_ozeti == jeton_ozeti(s)))).scalars().first()
    if a is None:
        return None
    kisi = a.kisi_email
    # Son erişim Core UPDATE ile (iş biriminden geçmez → denetim kaydında istek yolu/jeton görünmez).
    await db.execute(update(ToplantiTakvimAbonelikleri).where(ToplantiTakvimAbonelikleri.id == a.id)
                     .values(son_erisim_at=simdi()).execution_options(synchronize_session=False))
    await db.commit()
    liste = await kisinin_toplantilari(db, kisi)
    ks = await toplu_katilimcilar(db, [t.id for t in liste])
    return ics_akisi([(t, ks.get(int(t.id), [])) for t in liste], "Toplantılar — By Mehmet KURU Dev")


# ---------------------------------------------------------------------------
# Liste ve süzgeç (yönetici)
# ---------------------------------------------------------------------------
async def yonetici_listesi(db: AsyncSession, *, gorunum: str = "yaklasan", hesap: Optional[str] = None,
                           proje_id: Optional[int] = None, durum: Optional[str] = None, bas: Optional[date] = None,
                           bit: Optional[date] = None, q: Optional[str] = None, sinir: int = 300) -> List[Dict[str, Any]]:
    an = simdi()
    s = select(Toplantilar)
    if hesap:
        s = s.where(Toplantilar.hesap_email == eposta_duzelt(hesap))
    if proje_id:
        s = s.where(Toplantilar.proje_id == int(proje_id))
    if durum:
        if durum not in DURUMLAR:
            raise ToplantiHatasi(400, "durum_gecersiz")
        s = s.where(Toplantilar.durum == durum)
    tz = saat_dilimi()
    if bas:
        s = s.where(Toplantilar.baslangic >= datetime(bas.year, bas.month, bas.day, tzinfo=tz).astimezone(timezone.utc))
    if bit:
        son = datetime(bit.year, bit.month, bit.day, tzinfo=tz) + timedelta(days=1)
        s = s.where(Toplantilar.baslangic < son.astimezone(timezone.utc))
    if q:
        aranan = f"%{' '.join(q.split())[:100].lower().replace('%', '').replace('_', '')}%"
        s = s.where(func.lower(Toplantilar.baslik).like(aranan))
    if gorunum == "yaklasan":
        s = s.where(Toplantilar.durum.in_(("planlandi", "ertelendi")),
                    Toplantilar.baslangic > an - timedelta(minutes=EN_COK_SURE)).order_by(Toplantilar.baslangic.asc())
    elif gorunum == "gecmis":
        s = s.where(Toplantilar.durum != "iptal", Toplantilar.baslangic <= an).order_by(Toplantilar.baslangic.desc())
    elif gorunum == "iptal":
        s = s.where(Toplantilar.durum == "iptal").order_by(Toplantilar.baslangic.desc())
    elif gorunum != "hepsi":
        raise ToplantiHatasi(400, "gorunum_gecersiz")
    else:
        s = s.order_by(Toplantilar.baslangic.desc())
    liste = (await db.execute(s.limit(sinir))).scalars().all()
    if gorunum in ("yaklasan", "gecmis"):
        liste = [t for t in liste if durum_kategori(t, an) == gorunum]
    ks = await toplu_katilimcilar(db, [t.id for t in liste])
    adlar: Dict[str, str] = {}
    try:
        from services.hesap_ekibi import hesap_adlari

        adlar = await hesap_adlari(db, [t.hesap_email for t in liste if t.hesap_email])
    except Exception:  # noqa: BLE001
        adlar = {}
    sonuc = []
    for t in liste:
        d = ozet_sozlugu(t, ks.get(int(t.id), []), an)
        d["hesap_adi"] = adlar.get(eposta_duzelt(t.hesap_email)) if t.hesap_email else None
        d["hafta"] = hafta_anahtari(t.baslangic)
        sonuc.append(d)
    return sonuc


def hafta_anahtari(an: datetime) -> str:
    """İstanbul ISO haftası `YYYY-Www` (liste hafta gruplu)."""
    y, h, _ = yerel(an).isocalendar()
    return f"{y}-W{h:02d}"


async def notsuz_gecmis(db: AsyncSession, an: Optional[datetime] = None) -> List[Toplantilar]:
    """Haftalık özet: son NOTSUZ_GUN içinde yapılmış/geçmiş, notu ve kararı boş toplantılar."""
    an = an or simdi()
    adaylar = (await db.execute(select(Toplantilar).where(
        Toplantilar.durum != "iptal", Toplantilar.baslangic <= an, Toplantilar.baslangic >= an - timedelta(days=NOTSUZ_GUN),
        or_(Toplantilar.notlar.is_(None), Toplantilar.notlar == ""),
    ).order_by(Toplantilar.baslangic.asc()).limit(500))).scalars().all()
    return [t for t in adaylar if bitis(t) <= an and not json_liste(t.kararlar)]


# ---------------------------------------------------------------------------
# Müşteri listesi
# ---------------------------------------------------------------------------
async def musteri_toplantilari(db: AsyncSession, hesap: str, kisi: str) -> List[Dict[str, Any]]:
    liste = (await db.execute(select(Toplantilar).where(Toplantilar.hesap_email == eposta_duzelt(hesap))
                              .order_by(Toplantilar.baslangic.desc()).limit(300))).scalars().all()
    ks = await toplu_katilimcilar(db, [t.id for t in liste])
    ak: Dict[int, List[ToplantiAksiyonlari]] = {int(t.id): [] for t in liste}
    if liste:
        for a in (await db.execute(select(ToplantiAksiyonlari).where(
                ToplantiAksiyonlari.toplanti_id.in_([t.id for t in liste])))).scalars().all():
            ak.setdefault(int(a.toplanti_id), []).append(a)
    return [musteri_sozlugu(t, ks.get(int(t.id), []), ak.get(int(t.id), []), kisi, ayrinti=False) for t in liste]


async def musteri_toplantisi(db: AsyncSession, hesap: str, tid: int) -> Toplantilar:
    t = (await db.execute(select(Toplantilar).where(Toplantilar.id == tid,
                                                    Toplantilar.hesap_email == eposta_duzelt(hesap)))).scalars().first()
    if t is None:
        raise ToplantiHatasi(404, "bulunamadi")
    return t


async def musteri_ozeti(db: AsyncSession, hesap: str) -> Dict[str, int]:
    h = eposta_duzelt(hesap)
    toplanti = (await db.execute(select(func.count(Toplantilar.id)).where(Toplantilar.hesap_email == h))).scalar() or 0
    talep = (await db.execute(select(func.count(ToplantiTalepleri.id)).where(ToplantiTalepleri.hesap_email == h))).scalar() or 0
    yaklasan = (await db.execute(select(func.count(Toplantilar.id)).where(
        Toplantilar.hesap_email == h, Toplantilar.durum.in_(("planlandi", "ertelendi")),
        Toplantilar.baslangic > simdi()))).scalar() or 0
    return {"toplanti": int(toplanti), "talep": int(talep), "yaklasan": int(yaklasan)}


__all__ = [
    "ToplantiHatasi", "zaman_coz", "ics_uret", "ics_akisi", "davet_gonder", "iptal_gonder", "hatirlatmalari_gonder",
    "yanit_coz", "yanit_yaz", "harici_takvim_esitle", "goreve_donustur", "akis_uret", "abonelik_uret",
]
