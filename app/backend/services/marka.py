"""Faz 4L — Marka teması (white-label): doğrulama, kontrast denetimi, logo, herkese açık özet.

Ne yapıyor?
-----------
Müşteri hesabı başına tek kayıt (`models/marka.py`). Modül `marka_temasi`
(`core/moduller.py`) açıksa kaydın renkleri/logosu müşterinin herkese açık
sayfalarına VARSAYILAN tema olarak uygulanıyor. Sayfanın kendi açık teması
(kartvizitin `tema`sı, QR menünün `tema_rengi`, randevu/etkinlik/kurs/asistan
`renk`i — modülün varsayılanından farklıysa) ÖNCELİKLİ; marka teması yalnız
sayfa kendi rengini seçmediyse devreye giriyor (`acik_marka(..., sayfa_ozel=)`).

Rozet ("mehmetkuru.dev ile hazırlandı"): müşteri sayfalarının altında görünür.
Modül açık VE modül ayarı `rozet_gizle` (yalnız yönetici değiştirir) True ise
gizlenir.

Güvenlik
--------
* Renkler yalnız `#rrggbb`; zemin/köşe/yazı tipi sabit listelerden. Herkese açık
  yanıttaki değerler bu listelerden geldiği için sayfalar onları satır içi stile
  (ve Pages Function'lar `<style>` bloğuna) doğrudan yazabiliyor; yine de
  Function'lar kendi tarafında da biçimi denetliyor.
* Logo: PNG / JPEG / WebP (en çok 2 MB, 16–4096 px). Sunucuda Pillow ile açılıp
  512 px'e küçültülüyor ve WebP'ye çevriliyor (EXIF / gömülü her şey atılıyor).
  SVG REDDEDİLİYOR (`svg_desteklenmiyor`): SVG betik/olay öznitelikleri ve dış
  kaynak taşıyabildiği için (XSS) temizlemek yerine kabul etmiyoruz.
* Yazı tipleri yalnız sitede zaten yüklü olanlar (Plus Jakarta Sans, JetBrains
  Mono) ya da sistem yığınları — yeni font dosyası ya da dış font YOK (CSP + hız).

Kontrast (WCAG 2.x)
-------------------
Göreli parlaklık ve kontrast oranı WCAG 2.1 tanımıyla (1.4.3 "Contrast
(Minimum)", AA: normal metin için en az 4.5:1). Ana rengin üstündeki yazı
rengi otomatik seçiliyor (beyaz `#ffffff` ya da koyu `#111111` — oranı yüksek
olan). Oran 4.5'in altında kalırsa uyarı + öneri (rengin tonunu koruyup
açıklığını değiştirerek eşiği geçen en yakın renk). Vurgu rengi zeminde metin
/ bağlantı rengi olarak kullanıldığı için zeminle oranı da aynı eşikle
denetleniyor. Uyarı kaydı ENGELLEMİYOR (bilgilendirme).
"""

import colorsys
import html
import io
import logging
import re
import secrets
from typing import Any, Dict, Optional, Tuple

from models.marka import HesapMarkalari
from services import dosya_deposu
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODUL = "marka_temasi"

RENK_DESENI = re.compile(r"^#[0-9a-f]{6}$")
ZEMINLER: Tuple[str, ...] = ("koyu", "acik")
KOSELER: Tuple[str, ...] = ("keskin", "yumusak", "yuvarlak")
YAZI_TIPLERI: Tuple[str, ...] = ("jakarta", "sistem_sans", "sistem_serif", "mono")
AD_SINIRI = 80

VARSAYILAN: Dict[str, Any] = {
    "ad": "",
    "ana_renk": "#7c3aed",
    "vurgu_rengi": "#f59e0b",
    "zemin": "acik",
    "kose": "yumusak",
    "yazi_tipi": "jakarta",
}

#: Ana rengin üstündeki yazı için iki aday (oranı yüksek olan seçiliyor).
YAZI_ACIK = "#ffffff"
YAZI_KOYU = "#111111"
#: WCAG 2.1 AA, normal metin.
AA_ESIGI = 4.5

#: Zemin → sayfa renkleri (ön yüz `src/lib/marka.ts` ve `functions/_ortak/marka.js` ile aynı).
ZEMIN_RENKLERI: Dict[str, Dict[str, str]] = {
    "koyu": {"zemin": "#0b0b12", "yuzey": "#16161f", "metin": "#f4f4f7", "soluk": "#a1a1aa", "cerceve": "#2a2a36"},
    "acik": {"zemin": "#f7f7f8", "yuzey": "#ffffff", "metin": "#111827", "soluk": "#4b5563", "cerceve": "#e5e7eb"},
}
#: E-postada kullanılan yazı tipi yığınları (web güvenli yedeklerle).
YAZI_YIGINLARI: Dict[str, str] = {
    "jakarta": "'Plus Jakarta Sans', 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "sistem_sans": "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', Arial, sans-serif",
    "sistem_serif": "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif",
    "mono": "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
}

LOGO_EN_COK_BAYT = 2 * 1024 * 1024
LOGO_EN_AZ_KENAR = 16
LOGO_EN_COK_KENAR = 4096
LOGO_HEDEF = (512, 512)
LOGO_KALITE = 86
_LOGO_ANAHTAR = re.compile(r"^[A-Za-z0-9_-]{8,40}$")


class MarkaHatasi(Exception):
    def __init__(self, kod: str, alan: Optional[str] = None, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.alan = alan
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kod": self.kod}
        if self.alan:
            d["alan"] = self.alan
        d.update(self.ek)
        return d


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


# ---------------------------------------------------------------------------
# Renk ve kontrast (WCAG 2.1)
# ---------------------------------------------------------------------------
def _rgb(hex_renk: str) -> Tuple[float, float, float]:
    h = hex_renk.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{max(0, min(255, round(x * 255))):02x}" for x in (r, g, b))


def goreli_parlaklik(hex_renk: str) -> float:
    """WCAG 2.1 "relative luminance" (sRGB kanalları doğrusallaştırılıp ağırlıklı toplam)."""

    def kanal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(hex_renk)
    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def kontrast(a: str, b: str) -> float:
    """WCAG kontrast oranı (L1 + 0.05) / (L2 + 0.05), 1–21 arası."""
    la, lb = goreli_parlaklik(a), goreli_parlaklik(b)
    acik, koyu = max(la, lb), min(la, lb)
    return (acik + 0.05) / (koyu + 0.05)


def yazi_rengi(zemin_rengi: str) -> str:
    """Rengin üstündeki yazı: beyaz mı koyu mu (oranı yüksek olan)."""
    return YAZI_ACIK if kontrast(zemin_rengi, YAZI_ACIK) >= kontrast(zemin_rengi, YAZI_KOYU) else YAZI_KOYU


def _aciklik_ile(hex_renk: str, aciklik: float) -> str:
    r, g, b = _rgb(hex_renk)
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    return _hex(*colorsys.hls_to_rgb(h, max(0.0, min(1.0, aciklik)), s))


def renk_onerisi(hex_renk: str, yeterli) -> Optional[str]:
    """Tonu ve doygunluğu koruyup açıklığı adım adım değiştirerek `yeterli(renk)` koşulunu sağlayan
    EN YAKIN rengi bulur (koyulaştırma ya da açma — hangisi daha az değişiklikse). Yoksa None."""
    r, g, b = _rgb(hex_renk)
    _, l0, _ = colorsys.rgb_to_hls(r, g, b)
    adaylar = []
    for yon in (-1, 1):
        for adim in range(1, 101):
            l = l0 + yon * adim / 100
            if not 0 <= l <= 1:
                break
            aday = _aciklik_ile(hex_renk, l)
            if yeterli(aday):
                adaylar.append((adim, aday))
                break
    if not adaylar:
        return None
    return min(adaylar)[1]


def denetim(kayit: Dict[str, Any]) -> Dict[str, Any]:
    """Ana renk üstündeki yazı + vurgu rengi zeminde: oran, AA yeterli mi, öneri."""
    ana = kayit["ana_renk"]
    yazi = yazi_rengi(ana)
    ana_oran = kontrast(ana, yazi)
    ana_oneri = None
    if ana_oran < AA_ESIGI:
        ana_oneri = renk_onerisi(ana, lambda c: kontrast(c, yazi_rengi(c)) >= AA_ESIGI)
    zemin = ZEMIN_RENKLERI.get(kayit["zemin"], ZEMIN_RENKLERI["acik"])["zemin"]
    vurgu = kayit["vurgu_rengi"]
    vurgu_oran = kontrast(vurgu, zemin)
    vurgu_oneri = None
    if vurgu_oran < AA_ESIGI:
        vurgu_oneri = renk_onerisi(vurgu, lambda c: kontrast(c, zemin) >= AA_ESIGI)
    return {
        "esik": AA_ESIGI,
        "ana": {"yazi": yazi, "oran": round(ana_oran, 2), "yeterli": ana_oran >= AA_ESIGI, "oneri": ana_oneri},
        "vurgu": {"zemin": zemin, "oran": round(vurgu_oran, 2), "yeterli": vurgu_oran >= AA_ESIGI, "oneri": vurgu_oneri},
    }


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def renk_dogrula(ham: Any, alan: str) -> str:
    deger = str(ham or "").strip().lower()
    if len(deger) == 4 and re.fullmatch(r"#[0-9a-f]{3}", deger):
        deger = "#" + "".join(c * 2 for c in deger[1:])
    if not RENK_DESENI.match(deger):
        raise MarkaHatasi("renk_gecersiz", alan)
    return deger


def dogrula(govde: Any, mevcut: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gönderilen alanları doğrular; gönderilmeyenler `mevcut` (yoksa varsayılan) kalır."""
    if not isinstance(govde, dict):
        raise MarkaHatasi("gecersiz_govde")
    sonuc = dict(mevcut or VARSAYILAN)
    bilinen = set(VARSAYILAN)
    for anahtar in govde:
        if anahtar not in bilinen:
            raise MarkaHatasi("bilinmeyen_alan", str(anahtar)[:40])
    if "ad" in govde:
        ad = re.sub(r"\s+", " ", str(govde.get("ad") or "")).strip()
        if len(ad) > AD_SINIRI or re.search(r"[\x00-\x1f\x7f<>]", ad):
            raise MarkaHatasi("ad_gecersiz", "ad")
        sonuc["ad"] = ad
    for alan in ("ana_renk", "vurgu_rengi"):
        if alan in govde:
            sonuc[alan] = renk_dogrula(govde.get(alan), alan)
    for alan, liste in (("zemin", ZEMINLER), ("kose", KOSELER), ("yazi_tipi", YAZI_TIPLERI)):
        if alan in govde:
            deger = govde.get(alan)
            if deger not in liste:
                raise MarkaHatasi(f"{alan}_gecersiz", alan)
            sonuc[alan] = deger
    return sonuc


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
async def kayit_getir(db: AsyncSession, hesap: str) -> Optional[HesapMarkalari]:
    e = eposta_duzelt(hesap)
    if not e:
        return None
    return (await db.execute(select(HesapMarkalari).where(HesapMarkalari.hesap_email == e))).scalars().first()


def alanlar(satir: Optional[HesapMarkalari]) -> Dict[str, Any]:
    if satir is None:
        return dict(VARSAYILAN)
    return {
        "ad": satir.ad or "",
        "ana_renk": satir.ana_renk if RENK_DESENI.match(satir.ana_renk or "") else VARSAYILAN["ana_renk"],
        "vurgu_rengi": satir.vurgu_rengi if RENK_DESENI.match(satir.vurgu_rengi or "") else VARSAYILAN["vurgu_rengi"],
        "zemin": satir.zemin if satir.zemin in ZEMINLER else VARSAYILAN["zemin"],
        "kose": satir.kose if satir.kose in KOSELER else VARSAYILAN["kose"],
        "yazi_tipi": satir.yazi_tipi if satir.yazi_tipi in YAZI_TIPLERI else VARSAYILAN["yazi_tipi"],
    }


def logo_adresi(anahtar: str, uzanti: str = "webp") -> str:
    return f"/api/v1/marka/logo/{anahtar}.{uzanti}"


def logo_sozlugu(satir: Optional[HesapMarkalari]) -> Optional[Dict[str, Any]]:
    if satir is None or not satir.logo_anahtar:
        return None
    return {
        "url": logo_adresi(satir.logo_anahtar),
        "genislik": satir.logo_genislik,
        "yukseklik": satir.logo_yukseklik,
        "boyut": satir.logo_boyut,
    }


def panel_sozlugu(satir: Optional[HesapMarkalari], *, hesap: str, modul_acik: bool, rozet_gizle: bool) -> Dict[str, Any]:
    a = alanlar(satir)
    return {
        "hesap_email": eposta_duzelt(hesap),
        "kayitli": satir is not None,
        **a,
        "logo": logo_sozlugu(satir),
        "denetim": denetim(a),
        "modul_acik": modul_acik,
        "rozet_gizle": bool(rozet_gizle),
        "updated_at": satir.updated_at.isoformat() if satir is not None and satir.updated_at else None,
    }


def acik_tema(satir: HesapMarkalari) -> Dict[str, Any]:
    """Herkese açık sayfalara giden tema (sahip e-postası YOK)."""
    a = alanlar(satir)
    return {
        "ad": a["ad"],
        "ana": a["ana_renk"],
        "ana_yazi": yazi_rengi(a["ana_renk"]),
        "vurgu": a["vurgu_rengi"],
        "vurgu_yazi": yazi_rengi(a["vurgu_rengi"]),
        "zemin": a["zemin"],
        "kose": a["kose"],
        "yazi_tipi": a["yazi_tipi"],
        "logo": logo_sozlugu(satir),
    }


async def modul_durumu(db: AsyncSession, hesap: str) -> Tuple[bool, bool]:
    """(modül açık mı, rozet_gizle). Tek satır okunuyor: modül pakete ve bağımlılığa bağlı değil
    (varsayılan kapalı, ayrı satılan) — yalnız elle açılan satır açar."""
    from core import moduller as manifest
    from models.workspace_modules import WorkspaceModules
    from services.moduller import durumlari_hesapla, musteri_modulleri

    m = manifest.modul(MODUL)
    e = eposta_duzelt(hesap)
    if m is None or not e:
        return False, False
    try:
        if m.paketler or m.bagimliliklar:  # ileride pakete girerse tam hesap
            d = (await musteri_modulleri(db, e)).durumlar[MODUL]
        else:
            satir = (
                await db.execute(
                    select(WorkspaceModules)
                    .where(WorkspaceModules.musteri_eposta == e)
                    .where(WorkspaceModules.modul_anahtari == MODUL)
                )
            ).scalars().first()
            d = durumlari_hesapla(None, {MODUL: satir} if satir is not None else {})[MODUL]
    except Exception:  # noqa: BLE001 - modül okunamazsa marka uygulanmaz, rozet görünür
        logger.exception("Marka modülü durumu okunamadı")
        return False, False
    return bool(d.acik), bool(d.ayarlar.get("rozet_gizle"))


async def acik_marka(db: AsyncSession, hesap: Optional[str], *, sayfa_ozel: bool = False) -> Dict[str, Any]:
    """Herkese açık sayfa yanıtına eklenen `marka` alanı.

    * `rozet`: "mehmetkuru.dev ile hazırlandı" görünsün mü (ajansın kendi sayfasında da görünür —
      bugünkü davranış; gizleme yalnız müşteride, modül açık + `rozet_gizle`).
    * `tema`: modül açık ve kayıt varsa marka teması, yoksa None.
    * `sayfa_ozel`: sayfanın kendi açık teması var (o öncelikli; marka yalnız boş kalanları doldurur).
    """
    e = eposta_duzelt(hesap)
    if not e:
        return {"rozet": True, "tema": None, "sayfa_ozel": bool(sayfa_ozel)}
    acik, rozet_gizle = await modul_durumu(db, e)
    tema = None
    if acik:
        try:
            satir = await kayit_getir(db, e)
        except Exception:  # noqa: BLE001 - tablo okunamazsa sayfa yine açılsın
            logger.exception("Marka kaydı okunamadı")
            satir = None
        if satir is not None:
            tema = acik_tema(satir)
    return {"rozet": not (acik and rozet_gizle), "tema": tema, "sayfa_ozel": bool(sayfa_ozel)}


def renk_ozel_mi(renk: Optional[str], *varsayilanlar: str) -> bool:
    """Sayfanın kendi rengi modülün varsayılanından farklı mı (= kullanıcı seçmiş)."""
    r = (renk or "").strip().lower()
    return bool(r) and r not in {v.lower() for v in varsayilanlar}


async def kaydet(db: AsyncSession, hesap: str, govde: Any, kisi: Optional[str]) -> HesapMarkalari:
    e = eposta_duzelt(hesap)
    satir = await kayit_getir(db, e)
    yeni = dogrula(govde, alanlar(satir) if satir is not None else None)
    if satir is None:
        satir = HesapMarkalari(hesap_email=e)
        db.add(satir)
    satir.ad = yeni["ad"] or None
    satir.ana_renk = yeni["ana_renk"]
    satir.vurgu_rengi = yeni["vurgu_rengi"]
    satir.zemin = yeni["zemin"]
    satir.kose = yeni["kose"]
    satir.yazi_tipi = yeni["yazi_tipi"]
    satir.guncelleyen_email = eposta_duzelt(kisi) or None
    await db.commit()
    await db.refresh(satir)
    return satir


async def sifirla(db: AsyncSession, hesap: str) -> None:
    """Markayı tamamen kaldırır (logo içeriği dahil)."""
    satir = await kayit_getir(db, hesap)
    if satir is None:
        return
    await _logo_icerigini_sil(db, satir)
    await db.delete(satir)
    await db.commit()


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------
def _svg_mi(bayt: bytes, dosya_adi: str, tur: str) -> bool:
    bas = bayt[:512].lstrip().lower()
    return (
        (tur or "").lower().startswith("image/svg")
        or (dosya_adi or "").lower().endswith((".svg", ".svgz"))
        or bas.startswith(b"<svg")
        or (bas.startswith(b"<?xml") and b"<svg" in bayt[:4096].lower())
        or bas.startswith(b"\x1f\x8b")  # sıkıştırılmış SVG (svgz) ya da başka gzip
    )


def logo_hazirla(bayt: bytes, dosya_adi: str = "", tur: str = "") -> Tuple[bytes, int, int]:
    """Yüklenen PNG/JPEG/WebP → en çok 512 px WebP (saydamlık korunur). SVG reddedilir."""
    if not bayt:
        raise MarkaHatasi("dosya_bos", "dosya")
    if len(bayt) > LOGO_EN_COK_BAYT:
        raise MarkaHatasi("logo_buyuk", "dosya", durum=413, en_cok_mb=LOGO_EN_COK_BAYT // (1024 * 1024))
    if _svg_mi(bayt, dosya_adi, tur):
        raise MarkaHatasi("svg_desteklenmiyor", "dosya", durum=415)
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(bayt)) as ham:
            if ham.format not in ("JPEG", "PNG", "WEBP"):
                raise MarkaHatasi("logo_bicimi", "dosya", durum=415)
            if getattr(ham, "is_animated", False) and getattr(ham, "n_frames", 1) > 1:
                raise MarkaHatasi("logo_bicimi", "dosya", durum=415)
            gen, yuk = ham.size
            if min(gen, yuk) < LOGO_EN_AZ_KENAR or max(gen, yuk) > LOGO_EN_COK_KENAR:
                raise MarkaHatasi("logo_boyutu", "dosya")
            ham.load()
            gorsel = ImageOps.exif_transpose(ham)
            saydam = gorsel.mode in ("RGBA", "LA", "PA") or (gorsel.mode == "P" and "transparency" in gorsel.info)
            gorsel = gorsel.convert("RGBA" if saydam else "RGB")
    except MarkaHatasi:
        raise
    except Exception as exc:  # noqa: BLE001 - bozuk / tanınmayan dosya
        raise MarkaHatasi("logo_bicimi", "dosya", durum=415) from exc
    gorsel.thumbnail(LOGO_HEDEF, Image.LANCZOS)
    cikti = io.BytesIO()
    gorsel.save(cikti, format="WEBP", quality=LOGO_KALITE, method=4)
    return cikti.getvalue(), gorsel.width, gorsel.height


def png_uret(webp: bytes, kenar: int = 256) -> bytes:
    """E-posta istemcileri için PNG (Outlook WebP göstermiyor)."""
    from PIL import Image

    with Image.open(io.BytesIO(webp)) as ham:
        gorsel = ham.convert("RGBA")
    gorsel.thumbnail((kenar, kenar), Image.LANCZOS)
    cikti = io.BytesIO()
    gorsel.save(cikti, format="PNG", optimize=True)
    return cikti.getvalue()


async def _logo_icerigini_sil(db: AsyncSession, satir: HesapMarkalari) -> None:
    if satir.logo_yol and satir.logo_depo:
        try:
            await dosya_deposu.sil(db, satir.logo_depo, satir.logo_yol)
        except Exception:  # noqa: BLE001 - içerik silinemese de kayıt temizlensin
            logger.warning("Marka logosu içeriği silinemedi: %s", satir.id)
    satir.logo_anahtar = None
    satir.logo_depo = None
    satir.logo_yol = None
    satir.logo_genislik = None
    satir.logo_yukseklik = None
    satir.logo_boyut = None


async def logo_kaydet(db: AsyncSession, hesap: str, bayt: bytes, dosya_adi: str, tur: str, kisi: Optional[str]) -> HesapMarkalari:
    webp, gen, yuk = logo_hazirla(bayt, dosya_adi, tur)
    e = eposta_duzelt(hesap)
    satir = await kayit_getir(db, e)
    if satir is None:
        satir = HesapMarkalari(hesap_email=e, **{k: v for k, v in VARSAYILAN.items() if k != "ad"})
        db.add(satir)
        await db.flush()
    anahtar = secrets.token_urlsafe(18)
    yol = f"marka/{satir.id}/{anahtar}.webp"
    try:
        depo = await dosya_deposu.yaz(db, yol, webp, "image/webp")
    except dosya_deposu.DepoHatasi as exc:
        await db.rollback()
        raise MarkaHatasi("depo_hatasi", None, durum=503) from exc
    await _logo_icerigini_sil(db, satir)
    satir.logo_anahtar = anahtar
    satir.logo_depo = depo
    satir.logo_yol = yol
    satir.logo_genislik = gen
    satir.logo_yukseklik = yuk
    satir.logo_boyut = len(webp)
    satir.guncelleyen_email = eposta_duzelt(kisi) or None
    await db.commit()
    await db.refresh(satir)
    return satir


async def logo_kaldir(db: AsyncSession, hesap: str, kisi: Optional[str]) -> Optional[HesapMarkalari]:
    satir = await kayit_getir(db, hesap)
    if satir is None:
        return None
    await _logo_icerigini_sil(db, satir)
    satir.guncelleyen_email = eposta_duzelt(kisi) or None
    await db.commit()
    await db.refresh(satir)
    return satir


async def logo_icerigi(db: AsyncSession, anahtar: str) -> Optional[bytes]:
    if not _LOGO_ANAHTAR.match(anahtar or ""):
        return None
    satir = (await db.execute(select(HesapMarkalari).where(HesapMarkalari.logo_anahtar == anahtar))).scalars().first()
    if satir is None or not satir.logo_yol or not satir.logo_depo:
        return None
    try:
        return await dosya_deposu.oku(db, satir.logo_depo, satir.logo_yol)
    except Exception:  # noqa: BLE001 - depo okunamadı
        return None


# ---------------------------------------------------------------------------
# E-posta başlığı (müşteri adına giden e-postalar)
# ---------------------------------------------------------------------------
_ADRES = re.compile(r"https?://[^\s<>\"']+")


def eposta_html(tema: Dict[str, Any], konu: str, govde: str, site: str) -> str:
    """Metin e-postanın HTML sürümü: üstte küçük marka başlığı (logo + ad, ana renk şeridi).

    Bütün değişken metin kaçışlı; renkler/yazı tipi sabit listelerden. Bağlantılar
    kaçışlı metin içinde tıklanabilir yapılıyor (yalnız http/https).
    """
    ana = tema["ana"] if RENK_DESENI.match(tema.get("ana") or "") else VARSAYILAN["ana_renk"]
    ana_yazi = YAZI_ACIK if tema.get("ana_yazi") == YAZI_ACIK else YAZI_KOYU
    yazi = YAZI_YIGINLARI.get(tema.get("yazi_tipi") or "", YAZI_YIGINLARI["jakarta"])
    ad = html.escape(tema.get("ad") or "")
    logo = tema.get("logo") or None
    logo_html = ""
    if logo and isinstance(logo.get("url"), str) and logo["url"].startswith("/api/v1/marka/logo/"):
        png = html.escape(site.rstrip("/") + logo["url"].rsplit(".", 1)[0] + ".png", quote=True)
        logo_html = (
            f'<img src="{png}" alt="{ad}" height="36" '
            'style="display:inline-block;height:36px;width:auto;max-width:180px;vertical-align:middle;border:0;'
            'background:#ffffff;border-radius:6px;padding:2px">'
        )
    baslik_ici = logo_html + (f'<span style="vertical-align:middle;margin-left:{10 if logo_html else 0}px">{ad}</span>' if ad else "")
    if not baslik_ici:
        baslik_ici = "&nbsp;"
    metin = html.escape(govde or "")
    metin = _ADRES.sub(lambda m: f'<a href="{m.group(0)}" style="color:{ana if kontrast(ana, "#ffffff") >= 3 else "#1d4ed8"}">{m.group(0)}</a>', metin)
    metin = metin.replace("\n", "<br>\n")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(konu or "")}</title></head>'
        '<body style="margin:0;padding:0;background:#f4f4f5">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5">'
        '<tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;font-family:{yazi}">'
        f'<tr><td style="background:{ana};color:{ana_yazi};padding:14px 24px;font-size:16px;font-weight:600">{baslik_ici}</td></tr>'
        f'<tr><td style="padding:24px;color:#111827;font-size:15px;line-height:1.6">{metin}</td></tr>'
        '</table></td></tr></table></body></html>'
    )


async def eposta_eki(db: AsyncSession, hesap: Optional[str], konu: str, govde: str,
                     ek: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """`notify.dispatch(..., eposta_ek=)` için: marka açıksa `html` eklenmiş kopya; değilse `ek` aynen.
    Hata yutulur (e-posta markasız gider)."""
    try:
        m = await acik_marka(db, hesap)
        if not m.get("tema"):
            return ek
        from services.dinamik_qr import site_adresi

        return {**(ek or {}), "html": eposta_html(m["tema"], konu, govde, site_adresi())}
    except Exception:  # noqa: BLE001
        logger.exception("Marka e-posta başlığı üretilemedi")
        return ek
