"""Faz 2C — dosya kuralları: tür/boyut doğrulama, ad temizleme, imzalı
indirme adresi, paylaşım bağlantısı, belge talebi hatırlatmaları.

Güvenlik kararları
------------------
* **Tür sunucuda içerikten doğrulanıyor.** İstemcinin gönderdiği
  `Content-Type` hiç kullanılmıyor; uzantı izinli listede olmalı VE ilk
  baytlar o türün imzasını taşımalı (PDF `%PDF-`, PNG, JPEG, GIF, WEBP,
  Office/ZIP `PK\\x03\\x04`, eski Office OLE). Metin dosyası UTF-8 olmalı ve
  NUL içermemeli. SVG/HTML izinli DEĞİL (tarayıcıda betik çalıştırır).
  Kaydedilen MIME türü uzantıdan, bizim tablomuzdan geliyor.
* **Ad temizleniyor**: yol ayırıcıları, denetim karakterleri, baştaki
  noktalar atılıyor; Unicode NFC; 120 karakter. Depodaki anahtar addan
  türemiyor (rastgele), yani ad ne olursa olsun yol kaçışı yok.
* **İndirme yalnız imzalı, süreli adresle**: `HMAC-SHA256(dosya_id.son)`
  (anahtar JWT gizlisinden türetilmiş, amaca bağlı). 15 dakika. Doğrudan
  herkese açık yol yok; adres yalnız yetkili uçtan alınıyor.
* **Paylaşım bağlantısı**: 192 bit rastgele jeton, veritabanında sha256
  özeti; parola pbkdf2-sha256 (200k tur, 16 bayt tuz); indirme sayısı
  koşullu UPDATE ile artıyor (iki eş zamanlı istek sınırı aşamaz); 10
  yanlış parolada bağlantı kilitleniyor.
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TR = timezone(timedelta(hours=3))

VARSAYILAN_SINIR_MB = 20
EN_COK_SINIR_MB = 100
BOYUT_AYARI = "dosya_boyut_siniri_mb"
IMZA_SURESI_SN = 15 * 60
PAYLASIM_INDIRME_SURESI_SN = 120
AD_SINIRI = 120
KLASOR_SINIRI = 60
EN_AZ_GUN, EN_COK_GUN = 1, 30
KILIT_DENEME = 10
PBKDF2_TUR = 200_000
VARSAYILAN_KLASOR = "Genel"
MUSTERI_KLASORU = "Yüklemelerim"
BELGE_KLASORU = "İstenen belgeler"
HATIRLATMA_GUN = 2

#: uzantı → (MIME, içerik imzası denetçisi adı)
IZINLI_TURLER: Dict[str, Tuple[str, str]] = {
    "pdf": ("application/pdf", "pdf"),
    "png": ("image/png", "png"),
    "jpg": ("image/jpeg", "jpeg"),
    "jpeg": ("image/jpeg", "jpeg"),
    "gif": ("image/gif", "gif"),
    "webp": ("image/webp", "webp"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "zip"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "zip"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "zip"),
    "odt": ("application/vnd.oasis.opendocument.text", "zip"),
    "ods": ("application/vnd.oasis.opendocument.spreadsheet", "zip"),
    "doc": ("application/msword", "ole"),
    "xls": ("application/vnd.ms-excel", "ole"),
    "ppt": ("application/vnd.ms-powerpoint", "ole"),
    "zip": ("application/zip", "zip"),
    "txt": ("text/plain; charset=utf-8", "metin"),
    "csv": ("text/csv; charset=utf-8", "metin"),
}


class DosyaHatasi(Exception):
    """Ön yüzün yedi dilde metnini kurduğu hata: kod + HTTP durumu."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def bugun_tr(an: Optional[datetime] = None) -> date:
    return utc(an or simdi()).astimezone(TR).date()  # type: ignore[union-attr]


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


# ---------------------------------------------------------------------------
# Ad ve tür
# ---------------------------------------------------------------------------
_YASAK_KARAKTER = re.compile(r"[\x00-\x1f\x7f<>:\"|?*\\/]")
_BOSLUK = re.compile(r"\s+")


def ad_temizle(ham: Optional[str]) -> str:
    """Dosya adını güvenli, okunur bir ada çevirir (uzantı küçük harf)."""
    metin = unicodedata.normalize("NFC", str(ham or ""))
    # Yalnız son parça: "../../etc/passwd" ya da "C:\\a\\b.pdf" → "passwd" / "b.pdf"
    metin = re.split(r"[\\/]", metin)[-1]
    metin = _YASAK_KARAKTER.sub("", metin)
    # Unicode biçim/denetim karakterleri (sağdan-sola geçersiz kılma gibi) —
    # "fatura\u202egpj.exe" hilesi.
    metin = "".join(c for c in metin if unicodedata.category(c) not in ("Cc", "Cf"))
    metin = _BOSLUK.sub(" ", metin).strip().lstrip(".").strip()
    if "." in metin:
        govde, uzanti = metin.rsplit(".", 1)
        govde = govde.strip().rstrip(".").strip()
        uzanti = uzanti.strip().lower()
    else:
        govde, uzanti = metin, ""
    uzanti = re.sub(r"[^a-z0-9]", "", uzanti)[:8]
    if not govde:
        govde = "dosya"
    sinir = AD_SINIRI - (len(uzanti) + 1 if uzanti else 0)
    govde = govde[:sinir].rstrip()
    return f"{govde}.{uzanti}" if uzanti else govde


def uzanti_al(ad: str) -> str:
    return ad.rsplit(".", 1)[1].lower() if "." in ad else ""


def _imza_uyuyor(denetci: str, veri: bytes) -> bool:
    if denetci == "pdf":
        return veri[:5] == b"%PDF-"
    if denetci == "png":
        return veri[:8] == b"\x89PNG\r\n\x1a\n"
    if denetci == "jpeg":
        return veri[:3] == b"\xff\xd8\xff"
    if denetci == "gif":
        return veri[:6] in (b"GIF87a", b"GIF89a")
    if denetci == "webp":
        return veri[:4] == b"RIFF" and veri[8:12] == b"WEBP"
    if denetci == "zip":
        return veri[:4] in (b"PK\x03\x04", b"PK\x05\x06")
    if denetci == "ole":
        return veri[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    if denetci == "metin":
        if b"\x00" in veri:
            return False
        try:
            veri.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


def turu_dogrula(ad: str, veri: bytes, izinli: Optional[Iterable[str]] = None) -> str:
    """İçerik türünü doğrular; kaydedilecek MIME türünü döndürür."""
    uzanti = uzanti_al(ad)
    if uzanti not in IZINLI_TURLER:
        raise DosyaHatasi(415, "tur_izinsiz", uzanti=uzanti)
    if izinli is not None:
        kume = {u.strip().lower() for u in izinli if u and u.strip()}
        # jpg ile jpeg aynı şey.
        if "jpg" in kume or "jpeg" in kume:
            kume |= {"jpg", "jpeg"}
        if kume and uzanti not in kume:
            raise DosyaHatasi(415, "tur_talepte_yok", uzanti=uzanti)
    if not veri:
        raise DosyaHatasi(400, "bos_dosya")
    mime, denetci = IZINLI_TURLER[uzanti]
    if not _imza_uyuyor(denetci, veri):
        raise DosyaHatasi(415, "icerik_uyusmuyor", uzanti=uzanti)
    return mime


def kabul_turleri_duzelt(ham: Any) -> Optional[str]:
    if ham is None:
        return None
    if isinstance(ham, str):
        parcalar = ham.split(",")
    else:
        parcalar = [str(x) for x in ham]
    temiz = []
    for p in parcalar:
        u = p.strip().lower().lstrip(".")
        if not u:
            continue
        if u not in IZINLI_TURLER:
            raise DosyaHatasi(400, "tur_izinsiz", uzanti=u)
        if u not in temiz:
            temiz.append(u)
    return ",".join(temiz) or None


def klasor_temizle(ham: Optional[str], varsayilan: str = VARSAYILAN_KLASOR) -> str:
    metin = unicodedata.normalize("NFC", str(ham or ""))
    metin = _YASAK_KARAKTER.sub("", metin)
    metin = _BOSLUK.sub(" ", metin).strip().strip(".").strip()
    return metin[:KLASOR_SINIRI] or varsayilan


async def boyut_siniri_bayt(db: AsyncSession) -> int:
    """Site ayarı `dosya_boyut_siniri_mb` (varsayılan 20, en çok 100)."""
    from models.site_settings import Site_settings

    try:
        satir = (
            await db.execute(select(Site_settings).where(Site_settings.setting_key == BOYUT_AYARI))
        ).scalars().first()
        if satir and str(satir.setting_value or "").strip():
            mb = int(float(str(satir.setting_value).strip()))
            if 1 <= mb <= EN_COK_SINIR_MB:
                return mb * 1024 * 1024
    except Exception:  # noqa: BLE001 - bozuk ayar varsayılana düşsün
        logger.warning("Dosya boyut sınırı okunamadı", exc_info=True)
    return VARSAYILAN_SINIR_MB * 1024 * 1024


async def boyut_siniri_yaz(db: AsyncSession, mb: int) -> int:
    from models.site_settings import Site_settings

    if not isinstance(mb, int) or isinstance(mb, bool) or not 1 <= mb <= EN_COK_SINIR_MB:
        raise DosyaHatasi(400, "gecersiz_sinir")
    satir = (
        await db.execute(select(Site_settings).where(Site_settings.setting_key == BOYUT_AYARI))
    ).scalars().first()
    if satir:
        satir.setting_value = str(mb)
    else:
        db.add(Site_settings(setting_key=BOYUT_AYARI, setting_value=str(mb), group_name="dosya", label="Dosya boyut sınırı (MB)"))
    await db.commit()
    return mb


async def akistan_oku(dosya: Any, sinir: int) -> bytes:
    """UploadFile'ı parça parça okur; sınırı aşınca 413 (hepsini belleğe almadan)."""
    parcalar: List[bytes] = []
    toplam = 0
    while True:
        parca = await dosya.read(1024 * 1024)
        if not parca:
            break
        toplam += len(parca)
        if toplam > sinir:
            raise DosyaHatasi(413, "boyut_asildi", sinir_mb=sinir // (1024 * 1024))
        parcalar.append(parca)
    return b"".join(parcalar)


# ---------------------------------------------------------------------------
# Klasör yetkisi
# ---------------------------------------------------------------------------
async def klasor_getir(db: AsyncSession, eposta: str, ad: str):
    from models.dosyalar import DosyaKlasorleri

    return (
        await db.execute(
            select(DosyaKlasorleri).where(DosyaKlasorleri.client_email == eposta, DosyaKlasorleri.ad == ad)
        )
    ).scalars().first()


async def klasor_hazirla(db: AsyncSession, eposta: str, ad: str, gorunurluk: Optional[str] = None):
    """Klasörü yoksa açar. Görünürlük verilmişse ve farklıysa GÜNCELLEMEZ (açık uç yapar)."""
    from models.dosyalar import DosyaKlasorleri

    mevcut = await klasor_getir(db, eposta, ad)
    if mevcut is not None:
        return mevcut
    yeni = DosyaKlasorleri(client_email=eposta, ad=ad, gorunurluk=gorunurluk if gorunurluk in ("musteri", "ekip") else "musteri")
    db.add(yeni)
    await db.flush()
    return yeni


async def musteri_klasorleri(db: AsyncSession, eposta: str) -> Dict[str, str]:
    """{klasör adı: görünürlük}. Satırı olmayan klasör "ekip" sayılır (güvenli taraf)."""
    from models.dosyalar import DosyaKlasorleri

    satirlar = (await db.execute(select(DosyaKlasorleri).where(DosyaKlasorleri.client_email == eposta))).scalars().all()
    return {k.ad: k.gorunurluk for k in satirlar}


# ---------------------------------------------------------------------------
# Kayıt ve sürüm
# ---------------------------------------------------------------------------
def yeni_anahtar() -> str:
    an = simdi()
    return f"dosyalar/{an:%Y/%m}/{secrets.token_hex(16)}"


async def dosya_kaydet(
    db: AsyncSession,
    *,
    eposta: str,
    klasor: str,
    ad_ham: str,
    veri: bytes,
    yukleyen: Optional[str],
    yukleyen_rol: str,
    proje_id: Optional[int] = None,
    belge_talebi_id: Optional[int] = None,
    izinli: Optional[Iterable[str]] = None,
):
    """Doğrular, depoya yazar, satırı açar (commit ETMEZ)."""
    from models.dosyalar import Dosyalar
    from services import dosya_deposu

    ad = ad_temizle(ad_ham)
    mime = turu_dogrula(ad, veri, izinli)
    anahtar = yeni_anahtar()
    try:
        depo = await dosya_deposu.yaz(db, anahtar, veri, mime)
    except dosya_deposu.DepoHatasi:
        raise DosyaHatasi(502, "depo_hatasi")

    onceki = (
        await db.execute(
            select(Dosyalar).where(
                Dosyalar.client_email == eposta, Dosyalar.klasor == klasor, Dosyalar.ad == ad, Dosyalar.guncel.is_(True)
            )
        )
    ).scalars().all()
    surum = 1
    for o in onceki:
        surum = max(surum, int(o.surum or 1) + 1)
        o.guncel = False
    kayit = Dosyalar(
        client_email=eposta,
        proje_id=proje_id,
        klasor=klasor,
        ad=ad,
        boyut=len(veri),
        tur=mime,
        uzanti=uzanti_al(ad),
        depolama_anahtari=anahtar,
        depo=depo,
        yukleyen=yukleyen,
        yukleyen_rol=yukleyen_rol,
        surum=surum,
        guncel=True,
        belge_talebi_id=belge_talebi_id,
        created_at=simdi(),
    )
    db.add(kayit)
    await db.flush()
    return kayit


def dosya_sozlugu(d: Any, gorunurluk: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": d.id,
        "client_email": d.client_email,
        "proje_id": d.proje_id,
        "klasor": d.klasor,
        "ad": d.ad,
        "boyut": int(d.boyut or 0),
        "tur": d.tur,
        "uzanti": d.uzanti,
        "yukleyen_rol": d.yukleyen_rol,
        "surum": int(d.surum or 1),
        "belge_talebi_id": d.belge_talebi_id,
        "created_at": (utc(d.created_at).isoformat() if d.created_at else None),  # type: ignore[union-attr]
        "gorunurluk": gorunurluk,
    }


# ---------------------------------------------------------------------------
# İmzalı indirme adresi
# ---------------------------------------------------------------------------
def _imza_anahtari() -> bytes:
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        # Anahtar yoksa süreç başına rastgele: imzalı adres yeniden başlatmada
        # geçersizleşir ama asla tahmin edilebilir olmaz.
        global _YEDEK_ANAHTAR
        if _YEDEK_ANAHTAR is None:
            _YEDEK_ANAHTAR = secrets.token_bytes(32)
        return _YEDEK_ANAHTAR
    return hashlib.sha256(("dosya-indir:" + gizli).encode()).digest()


_YEDEK_ANAHTAR: Optional[bytes] = None


def indirme_imzasi(dosya_id: int, son: int) -> str:
    return hmac.new(_imza_anahtari(), f"{int(dosya_id)}.{int(son)}".encode(), hashlib.sha256).hexdigest()


def imzali_yol(dosya_id: int, sure_sn: int = IMZA_SURESI_SN, an: Optional[float] = None) -> Tuple[str, int]:
    son = int((an if an is not None else time.time()) + sure_sn)
    return f"/api/v1/dosya-indir/{int(dosya_id)}?son={son}&imza={indirme_imzasi(dosya_id, son)}", son


def imza_gecerli_mi(dosya_id: int, son: Any, imza: Any, an: Optional[float] = None) -> bool:
    try:
        son_i = int(son)
    except (TypeError, ValueError):
        return False
    if son_i < int(an if an is not None else time.time()):
        return False
    if not isinstance(imza, str) or len(imza) != 64:
        return False
    return hmac.compare_digest(indirme_imzasi(dosya_id, son_i), imza)


# ---------------------------------------------------------------------------
# Paylaşım bağlantısı
# ---------------------------------------------------------------------------
def jeton_ozeti(jeton: str) -> str:
    return hashlib.sha256(str(jeton).encode()).hexdigest()


def sifre_ozetle(sifre: str, tuz: Optional[str] = None) -> Tuple[str, str]:
    tuz = tuz or secrets.token_hex(16)
    ozet = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), bytes.fromhex(tuz), PBKDF2_TUR).hex()
    return ozet, tuz


def sifre_dogru_mu(sifre: str, ozet: str, tuz: str) -> bool:
    try:
        hesap, _ = sifre_ozetle(sifre, tuz)
    except ValueError:
        return False
    return hmac.compare_digest(hesap, ozet)


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


async def paylasim_olustur(
    db: AsyncSession,
    dosya_id: int,
    *,
    gun: int,
    sifre: Optional[str],
    indirme_siniri: Optional[int],
    olusturan: Optional[str],
):
    from models.dosyalar import PaylasimBaglantilari

    if isinstance(gun, bool) or not isinstance(gun, int) or not EN_AZ_GUN <= gun <= EN_COK_GUN:
        raise DosyaHatasi(400, "gecersiz_gun")
    if indirme_siniri is not None and (
        isinstance(indirme_siniri, bool) or not isinstance(indirme_siniri, int) or not 1 <= indirme_siniri <= 1000
    ):
        raise DosyaHatasi(400, "gecersiz_sinir")
    sifre = (sifre or "").strip() or None
    if sifre is not None and not 4 <= len(sifre) <= 128:
        raise DosyaHatasi(400, "gecersiz_sifre")
    jeton = secrets.token_urlsafe(24)
    ozet, tuz = (sifre_ozetle(sifre) if sifre else (None, None))
    kayit = PaylasimBaglantilari(
        dosya_id=dosya_id,
        jeton_ozeti=jeton_ozeti(jeton),
        son_kullanma=simdi() + timedelta(days=gun),
        sifre_ozeti=ozet,
        sifre_tuzu=tuz,
        indirme_siniri=indirme_siniri,
        indirme_sayisi=0,
        hatali_deneme=0,
        iptal=False,
        olusturan=olusturan,
        created_at=simdi(),
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return kayit, jeton


def paylasim_durumu(p: Any, an: Optional[datetime] = None) -> str:
    """gecerli | suresi_doldu | iptal | sinir_doldu | kilitli"""
    an = an or simdi()
    if p.iptal:
        return "iptal"
    if int(p.hatali_deneme or 0) >= KILIT_DENEME:
        return "kilitli"
    if utc(p.son_kullanma) <= an:  # type: ignore[operator]
        return "suresi_doldu"
    if p.indirme_siniri is not None and int(p.indirme_sayisi or 0) >= int(p.indirme_siniri):
        return "sinir_doldu"
    return "gecerli"


def paylasim_sozlugu(p: Any) -> Dict[str, Any]:
    return {
        "id": p.id,
        "dosya_id": p.dosya_id,
        "son_kullanma": utc(p.son_kullanma).isoformat(),  # type: ignore[union-attr]
        "sifreli": bool(p.sifre_ozeti),
        "indirme_siniri": p.indirme_siniri,
        "indirme_sayisi": int(p.indirme_sayisi or 0),
        "durum": paylasim_durumu(p),
        "created_at": utc(p.created_at).isoformat() if p.created_at else None,  # type: ignore[union-attr]
    }


async def paylasim_bul(db: AsyncSession, jeton: str):
    from models.dosyalar import PaylasimBaglantilari

    if not jeton or len(jeton) > 100:
        return None
    return (
        await db.execute(select(PaylasimBaglantilari).where(PaylasimBaglantilari.jeton_ozeti == jeton_ozeti(jeton)))
    ).scalars().first()


async def paylasimdan_indir(db: AsyncSession, jeton: str, sifre: Optional[str]) -> Tuple[Any, Any]:
    """Parolayı doğrular, sayacı koşullu artırır; (paylaşım, dosya) döndürür."""
    from models.dosyalar import Dosyalar, PaylasimBaglantilari

    p = await paylasim_bul(db, jeton)
    if p is None:
        raise DosyaHatasi(404, "bulunamadi")
    durum = paylasim_durumu(p)
    if durum != "gecerli":
        raise DosyaHatasi(410, durum)
    if p.sifre_ozeti:
        if not sifre or not sifre_dogru_mu(sifre, p.sifre_ozeti, p.sifre_tuzu or ""):
            await db.execute(
                update(PaylasimBaglantilari)
                .where(PaylasimBaglantilari.id == p.id)
                .values(hatali_deneme=PaylasimBaglantilari.hatali_deneme + 1)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            raise DosyaHatasi(403, "sifre_yanlis")
    an = simdi()
    kosullar = [
        PaylasimBaglantilari.id == p.id,
        PaylasimBaglantilari.iptal.is_(False),
        PaylasimBaglantilari.son_kullanma > an,
        PaylasimBaglantilari.hatali_deneme < KILIT_DENEME,
        or_(
            PaylasimBaglantilari.indirme_siniri.is_(None),
            PaylasimBaglantilari.indirme_sayisi < PaylasimBaglantilari.indirme_siniri,
        ),
    ]
    sonuc = await db.execute(
        update(PaylasimBaglantilari)
        .where(and_(*kosullar))
        .values(indirme_sayisi=PaylasimBaglantilari.indirme_sayisi + 1)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if int(sonuc.rowcount or 0) != 1:
        raise DosyaHatasi(410, "sinir_doldu")
    dosya = (await db.execute(select(Dosyalar).where(Dosyalar.id == p.dosya_id))).scalars().first()
    if dosya is None:
        raise DosyaHatasi(404, "bulunamadi")
    return p, dosya


# ---------------------------------------------------------------------------
# Belge talebi
# ---------------------------------------------------------------------------
def son_tarih_duzelt(ham: Optional[str]) -> Optional[str]:
    if ham is None or not str(ham).strip():
        return None
    try:
        return date.fromisoformat(str(ham).strip()[:10]).isoformat()
    except ValueError:
        raise DosyaHatasi(400, "gecersiz_tarih")


def talep_sozlugu(t: Any, dosya: Any = None) -> Dict[str, Any]:
    kalan = None
    if t.son_tarih:
        try:
            kalan = (date.fromisoformat(t.son_tarih) - bugun_tr()).days
        except ValueError:
            kalan = None
    return {
        "id": t.id,
        "client_email": t.client_email,
        "proje_id": t.proje_id,
        "baslik": t.baslik,
        "aciklama": t.aciklama,
        "son_tarih": t.son_tarih,
        "kalan_gun": kalan,
        "kabul_turleri": [u for u in (t.kabul_turleri or "").split(",") if u],
        "durum": t.durum,
        "dosya": dosya_sozlugu(dosya) if dosya is not None else None,
        "teslim_at": utc(t.teslim_at).isoformat() if t.teslim_at else None,  # type: ignore[union-attr]
        "created_at": utc(t.created_at).isoformat() if t.created_at else None,  # type: ignore[union-attr]
    }


async def belge_hatirlatmalari(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Zamanlı görev: son tarihe 2 gün kala müşteriye bir kez; geçince müşteri + yöneticiye bir kez."""
    from models.dosyalar import BelgeTalepleri
    from services.notify import admin_recipients, dispatch

    bugun = bugun or bugun_tr()
    satirlar = (
        await db.execute(
            select(BelgeTalepleri).where(BelgeTalepleri.durum == "bekliyor", BelgeTalepleri.son_tarih.isnot(None))
        )
    ).scalars().all()
    yaklasan = gecen = 0
    yoneticiler = None
    for t in satirlar:
        try:
            kalan = (date.fromisoformat(t.son_tarih) - bugun).days
        except ValueError:
            continue
        if kalan < 0:
            sonuc = await db.execute(
                update(BelgeTalepleri)
                .where(BelgeTalepleri.id == t.id, BelgeTalepleri.hatirlatma_gecti_at.is_(None), BelgeTalepleri.durum == "bekliyor")
                .values(hatirlatma_gecti_at=simdi())
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            if int(sonuc.rowcount or 0) != 1:
                continue
            gecen += 1
            if yoneticiler is None:
                yoneticiler = await admin_recipients(db)
            await dispatch(
                db,
                event_type="belge_gecikti",
                title=f"Belge teslim tarihi geçti: {t.baslik}",
                body=f"İstenen belge ({t.baslik}) {t.son_tarih} tarihine kadar yüklenmedi. Panelden yükleyebilirsiniz.",
                recipients=[{"email": t.client_email, "role": "client"}] + list(yoneticiler),
                link="/client?sekme=dosyalar",
                ref_type="belge_talebi",
                ref_id=t.id,
            )
        elif kalan <= HATIRLATMA_GUN:
            sonuc = await db.execute(
                update(BelgeTalepleri)
                .where(BelgeTalepleri.id == t.id, BelgeTalepleri.hatirlatma_yaklasti_at.is_(None), BelgeTalepleri.durum == "bekliyor")
                .values(hatirlatma_yaklasti_at=simdi())
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            if int(sonuc.rowcount or 0) != 1:
                continue
            yaklasan += 1
            await dispatch(
                db,
                event_type="belge_hatirlatma",
                title=f"Belge bekleniyor: {t.baslik}",
                body=f"{t.baslik} için son tarih {t.son_tarih}. Panelinizdeki 'İstenen belgeler' bölümünden yükleyebilirsiniz.",
                recipients=[{"email": t.client_email, "role": "client"}],
                link="/client?sekme=dosyalar",
                ref_type="belge_talebi",
                ref_id=t.id,
            )
    return {"yaklasan": yaklasan, "gecen": gecen}
