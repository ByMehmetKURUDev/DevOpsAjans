"""Faz 3K — Kaynaklar: doğrulama, dil çözümü, tohumlama.

Bir kaynağın üç görünümü var:

* **Özet** (liste kartı): slug, kategori, başlık, özet, etiketler, rozetler.
  Herkese açık liste yalnız bunu döndürüyor — liste sayfası açıklama
  paragraflarını ve adımları indirmesin.
* **Ayrıntı**: özet + açıklama, adımlar, bağlantı, lisans, doğrulama günü.
* **Tam** (tohum biçimi): metin alanları 7 dilde sözlük
  (``{"tr": .., "en": ..}``). Derlemede prerender bu biçimi okuyor; tohum
  dosyası da aynı biçimde (bkz. `data/kaynaklar_tohum.json`).

Dil çözümü: istenen dilde alan doluysa o, değilse Türkçesi. Aynı kural ön
yüzde `prerender/kaynaklar-veri.js` içinde (derleme verisi için) yazılı;
ikisi ayrışırsa Google'ın gördüğü sayfa ile ziyaretçinin gördüğü ayrışır.
"""

import json
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from models.kaynaklar import BAGLANTI_TURLERI, Kaynaklar, KaynakTohumIzi
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
CEVIRI_DILLERI = DILLER[1:]
METIN_ALANLARI = ("baslik", "ozet", "aciklama")

TOHUM_YOLU = Path(__file__).resolve().parent.parent / "data" / "kaynaklar_tohum.json"

#: Tohum dosyası okunamazsa kategoriler bunlar (SEMA.md'deki sabit anahtarlar).
VARSAYILAN_KATEGORILER = (
    "claude-beceri",
    "mcp-eklenti",
    "ajan",
    "video-ses",
    "gorsel-tasarim",
    "model-api",
    "veri-otomasyon",
    "reklam-pazarlama",
    "rehber",
)

#: Uç yollarıyla çakışan, slug olamayacak adlar (`/api/v1/kaynaklar/yonetim`).
AYRILMIS_SLUGLAR = frozenset({"yonetim"})

SLUG_DESENI = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SINIR = {
    "slug": 80,
    "baslik": 200,
    "ozet": 300,
    "aciklama": 20_000,
    "adim": 500,
    "adim_sayisi": 12,
    "etiket": 40,
    "etiket_sayisi": 20,
    "baglanti": 500,
    "lisans": 80,
}
YOUTUBE_SUNUCULARI = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})


class KaynakHatasi(Exception):
    """Doğrulama hatası: `kod` ön yüzde yedi dilde metne çevriliyor."""

    def __init__(self, kod: str, alan: Optional[str] = None):
        self.kod = kod
        self.alan = alan
        super().__init__(kod)


# ---------------------------------------------------------------------------
# Tohum dosyası ve kategoriler
# ---------------------------------------------------------------------------
_tohum_onbellegi: Dict[str, Any] = {}


def tohum_oku(yol: Optional[Path] = None) -> Dict[str, Any]:
    """Tohum dosyasını okur (değişiklik zamanına göre önbellekli). Bozuksa boş."""
    yol = Path(yol or TOHUM_YOLU)
    try:
        damga = yol.stat().st_mtime_ns
    except OSError:
        logger.warning("Kaynak tohum dosyası yok: %s", yol)
        return {"kategoriler": [], "kaynaklar": []}
    anahtar = str(yol)
    kayit = _tohum_onbellegi.get(anahtar)
    if kayit and kayit[0] == damga:
        return kayit[1]
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        if not isinstance(veri, dict):
            raise ValueError("kök nesne değil")
    except (OSError, ValueError) as hata:
        logger.error("Kaynak tohum dosyası okunamadı (%s): %s", yol, hata)
        return {"kategoriler": [], "kaynaklar": []}
    veri.setdefault("kategoriler", [])
    veri.setdefault("kaynaklar", [])
    _tohum_onbellegi[anahtar] = (damga, veri)
    return veri


def kategoriler(yol: Optional[Path] = None) -> List[Dict[str, Any]]:
    """[{anahtar, ad: {dil: ad}}] — tohum dosyasının sırasıyla."""
    sonuc: List[Dict[str, Any]] = []
    gorulen = set()
    for k in tohum_oku(yol).get("kategoriler") or []:
        if not isinstance(k, dict):
            continue
        anahtar = str(k.get("anahtar") or "").strip()
        if not anahtar or anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        ad = k.get("ad") if isinstance(k.get("ad"), dict) else {}
        sonuc.append({"anahtar": anahtar, "ad": {d: str(v) for d, v in ad.items() if d in DILLER and v}})
    if not sonuc:
        sonuc = [{"anahtar": a, "ad": {}} for a in VARSAYILAN_KATEGORILER]
    return sonuc


def kategori_anahtarlari(yol: Optional[Path] = None) -> List[str]:
    return [k["anahtar"] for k in kategoriler(yol)]


def kategori_adi(kategori: Dict[str, Any], dil: str) -> str:
    ad = kategori.get("ad") or {}
    return ad.get(dil) or ad.get("tr") or kategori["anahtar"]


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def dil_coz(ham: Optional[str]) -> str:
    d = (ham or "tr").strip().lower()[:2]
    return d if d in DILLER else "tr"


def _json(metin: Optional[str], tur: type) -> Any:
    if not metin:
        return tur()
    try:
        veri = json.loads(metin)
    except (TypeError, ValueError):
        return tur()
    return veri if isinstance(veri, tur) else tur()


def _liste(metin: Optional[str]) -> List[str]:
    return [str(x) for x in _json(metin, list) if isinstance(x, (str, int, float)) and str(x).strip()]


def ceviriler_coz(metin: Optional[str]) -> Dict[str, Dict[str, Any]]:
    sonuc: Dict[str, Dict[str, Any]] = {}
    for dil, deger in _json(metin, dict).items():
        if dil not in CEVIRI_DILLERI or not isinstance(deger, dict):
            continue
        satir: Dict[str, Any] = {a: str(deger.get(a) or "") for a in METIN_ALANLARI}
        adimlar = deger.get("adimlar")
        satir["adimlar"] = [str(x) for x in adimlar if str(x).strip()] if isinstance(adimlar, list) else []
        sonuc[dil] = satir
    return sonuc


def normalize(metin: str) -> str:
    """Arama için: küçük harf, Türkçe İ/ı, aksansız."""
    metin = (metin or "").replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")
    metin = unicodedata.normalize("NFKD", metin)
    return "".join(c for c in metin if not unicodedata.combining(c))


def siralama_anahtari(k: Kaynaklar) -> Tuple[bool, int, str]:
    """Öne çıkanlar önce, sonra el sırası, sonra slug (ön yüzde de aynısı)."""
    return (not bool(k.one_cikan), int(k.sira if k.sira is not None else 100), k.slug or "")


def _tarih(deger: Optional[date]) -> Optional[str]:
    return deger.isoformat() if deger else None


def _an(deger: Any) -> Optional[str]:
    return deger.isoformat() if deger else None


# ---------------------------------------------------------------------------
# Görünümler
# ---------------------------------------------------------------------------
def dilde(k: Kaynaklar, dil: str) -> Dict[str, Any]:
    """Metin alanları istenen dilde; boşsa Türkçe."""
    turkce = {
        "baslik": k.baslik or "",
        "ozet": k.ozet or "",
        "aciklama": k.aciklama or "",
        "adimlar": _liste(k.adimlar),
    }
    if dil == "tr":
        return turkce
    c = ceviriler_coz(k.ceviriler).get(dil) or {}
    sonuc: Dict[str, Any] = {}
    for a in METIN_ALANLARI:
        deger = c.get(a) or ""
        sonuc[a] = deger if deger.strip() else turkce[a]
    sonuc["adimlar"] = c.get("adimlar") or turkce["adimlar"]
    return sonuc


def ozet_satiri(k: Kaynaklar, dil: str) -> Dict[str, Any]:
    metin = dilde(k, dil)
    return {
        "slug": k.slug,
        "kategori": k.kategori,
        "baslik": metin["baslik"],
        "ozet": metin["ozet"],
        "etiketler": _liste(k.etiketler),
        "ucretsiz": bool(k.ucretsiz),
        "acik_kaynak": bool(k.acik_kaynak),
        "youtube_short": k.youtube_short or None,
        "one_cikan": bool(k.one_cikan),
        "sira": int(k.sira if k.sira is not None else 100),
        "baglanti_turu": k.baglanti_turu or "site",
    }


def ayrinti(k: Kaynaklar, dil: str, kategori_listesi: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    metin = dilde(k, dil)
    kat = next((c for c in kategori_listesi if c["anahtar"] == k.kategori), {"anahtar": k.kategori, "ad": {}})
    return {
        **ozet_satiri(k, dil),
        "aciklama": metin["aciklama"],
        "adimlar": metin["adimlar"],
        "baglanti": k.baglanti,
        "lisans": k.lisans or None,
        "kategori_adi": kategori_adi(kat, dil),
        "dogrulama_tarihi": _tarih(k.dogrulama_tarihi),
        "updated_at": _an(k.updated_at),
    }


def tam_kayit(k: Kaynaklar) -> Dict[str, Any]:
    """Tohum biçimi: metin alanları 7 dilde sözlük (yalnız dolu diller)."""
    cev = ceviriler_coz(k.ceviriler)
    alanlar: Dict[str, Dict[str, Any]] = {a: {"tr": getattr(k, a) or ""} for a in METIN_ALANLARI}
    alanlar["adimlar"] = {"tr": _liste(k.adimlar)}
    for dil, c in cev.items():
        for a in METIN_ALANLARI:
            if (c.get(a) or "").strip():
                alanlar[a][dil] = c[a]
        if c.get("adimlar"):
            alanlar["adimlar"][dil] = c["adimlar"]
    return {
        "slug": k.slug,
        "kategori": k.kategori,
        **alanlar,
        "etiketler": _liste(k.etiketler),
        "baglanti": k.baglanti,
        "baglanti_turu": k.baglanti_turu or "site",
        "lisans": k.lisans or None,
        "ucretsiz": bool(k.ucretsiz),
        "acik_kaynak": bool(k.acik_kaynak),
        "youtube_short": k.youtube_short or None,
        "one_cikan": bool(k.one_cikan),
        "sira": int(k.sira if k.sira is not None else 100),
        "dogrulama_tarihi": _tarih(k.dogrulama_tarihi),
        "updated_at": _an(k.updated_at),
    }


def yonetim_satiri(k: Kaynaklar) -> Dict[str, Any]:
    """Panel formu: Türkçe ana alanlar + `ceviriler` (ham, dil → alan)."""
    return {
        "id": k.id,
        "slug": k.slug,
        "kategori": k.kategori,
        "baslik": k.baslik,
        "ozet": k.ozet or "",
        "aciklama": k.aciklama or "",
        "adimlar": _liste(k.adimlar),
        "ceviriler": ceviriler_coz(k.ceviriler),
        "etiketler": _liste(k.etiketler),
        "baglanti": k.baglanti,
        "baglanti_turu": k.baglanti_turu or "site",
        "lisans": k.lisans or None,
        "ucretsiz": bool(k.ucretsiz),
        "acik_kaynak": bool(k.acik_kaynak),
        "youtube_short": k.youtube_short or None,
        "one_cikan": bool(k.one_cikan),
        "sira": int(k.sira if k.sira is not None else 100),
        "yayinda": bool(k.yayinda),
        "dogrulama_tarihi": _tarih(k.dogrulama_tarihi),
        "created_at": _an(k.created_at),
        "updated_at": _an(k.updated_at),
    }


def arama_eslesir(k: Kaynaklar, dil: str, kelimeler: List[str], kategori_listesi: List[Dict[str, Any]]) -> bool:
    """Her kelime başlık/özet/etiket/kategori adında (seçili dil ya da Türkçe) geçmeli."""
    if not kelimeler:
        return True
    kat = next((c for c in kategori_listesi if c["anahtar"] == k.kategori), None)
    parcalar = [k.slug or "", " ".join(_liste(k.etiketler))]
    for d in {dil, "tr"}:
        m = dilde(k, d)
        parcalar += [m["baslik"], m["ozet"]]
        if kat:
            parcalar.append(kategori_adi(kat, d))
    havuz = normalize(" ".join(parcalar))
    return all(kelime in havuz for kelime in kelimeler)


def arama_kelimeleri(q: Optional[str]) -> List[str]:
    return [w for w in normalize(q or "").split() if w][:8]


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def baglanti_dogrula(deger: Any, alan: str = "baglanti", zorunlu: bool = True) -> Optional[str]:
    """Yalnız http/https; boşluk, kullanıcı adı/parola ve sunucusuz adres yok."""
    metin = str(deger or "").strip()
    if not metin:
        if zorunlu:
            raise KaynakHatasi("baglanti_gerekli", alan)
        return None
    if len(metin) > SINIR["baglanti"] or any(c.isspace() for c in metin):
        raise KaynakHatasi("gecersiz_baglanti", alan)
    try:
        parca = urlsplit(metin)
    except ValueError as exc:
        raise KaynakHatasi("gecersiz_baglanti", alan) from exc
    if parca.scheme.lower() not in ("http", "https") or not parca.hostname or "@" in parca.netloc:
        raise KaynakHatasi("gecersiz_baglanti", alan)
    return metin


def _metin(deger: Any, alan: str, sinir: int, zorunlu: bool = False) -> str:
    metin = str(deger or "").strip()
    if zorunlu and not metin:
        raise KaynakHatasi(f"{alan}_gerekli", alan)
    if len(metin) > sinir:
        raise KaynakHatasi("cok_uzun", alan)
    return metin


def _adimlar(deger: Any) -> List[str]:
    if deger in (None, ""):
        return []
    if isinstance(deger, str):
        deger = deger.split("\n")
    if not isinstance(deger, list):
        raise KaynakHatasi("gecersiz_adimlar", "adimlar")
    adimlar = [str(x).strip() for x in deger if str(x or "").strip()]
    if len(adimlar) > SINIR["adim_sayisi"] or any(len(a) > SINIR["adim"] for a in adimlar):
        raise KaynakHatasi("cok_uzun", "adimlar")
    return adimlar


def _etiketler(deger: Any) -> List[str]:
    if deger in (None, ""):
        return []
    if isinstance(deger, str):
        deger = deger.split(",")
    if not isinstance(deger, list):
        raise KaynakHatasi("gecersiz_etiket", "etiketler")
    sonuc: List[str] = []
    for e in deger:
        metin = " ".join(str(e or "").split()).lower()
        if not metin or metin in sonuc:
            continue
        if len(metin) > SINIR["etiket"]:
            raise KaynakHatasi("cok_uzun", "etiketler")
        sonuc.append(metin)
    if len(sonuc) > SINIR["etiket_sayisi"]:
        raise KaynakHatasi("cok_uzun", "etiketler")
    return sonuc


def _bool(deger: Any, varsayilan: bool) -> bool:
    if deger is None:
        return varsayilan
    if isinstance(deger, bool):
        return deger
    if isinstance(deger, (int, float)):
        return bool(deger)
    return str(deger).strip().lower() in ("1", "true", "evet", "yes", "on")


def _tarih_coz(deger: Any) -> Optional[date]:
    if deger in (None, ""):
        return None
    if isinstance(deger, date):
        return deger
    try:
        return date.fromisoformat(str(deger).strip()[:10])
    except ValueError as exc:
        raise KaynakHatasi("gecersiz_tarih", "dogrulama_tarihi") from exc


def _youtube(deger: Any) -> Optional[str]:
    adres = baglanti_dogrula(deger, "youtube_short", zorunlu=False)
    if adres and (urlsplit(adres).hostname or "").lower() not in YOUTUBE_SUNUCULARI:
        raise KaynakHatasi("gecersiz_youtube", "youtube_short")
    return adres


def _ceviriler_dogrula(deger: Any) -> Dict[str, Dict[str, Any]]:
    if deger in (None, ""):
        return {}
    if not isinstance(deger, dict):
        raise KaynakHatasi("gecersiz_ceviri", "ceviriler")
    sonuc: Dict[str, Dict[str, Any]] = {}
    for dil, alanlar in deger.items():
        if dil not in CEVIRI_DILLERI:
            raise KaynakHatasi("gecersiz_dil", "ceviriler")
        if not isinstance(alanlar, dict):
            raise KaynakHatasi("gecersiz_ceviri", "ceviriler")
        satir: Dict[str, Any] = {}
        for a in METIN_ALANLARI:
            metin = _metin(alanlar.get(a), a, SINIR[a])
            if metin:
                satir[a] = metin
        adimlar = _adimlar(alanlar.get("adimlar"))
        if adimlar:
            satir["adimlar"] = adimlar
        if satir:
            sonuc[dil] = satir
    return sonuc


def girdiyi_dogrula(govde: Dict[str, Any], kategori_listesi: Optional[List[str]] = None) -> Dict[str, Any]:
    """Panel girdisini (Türkçe ana alanlar + `ceviriler`) sütun değerlerine çevirir."""
    slug = _metin(govde.get("slug"), "slug", SINIR["slug"], zorunlu=True).lower()
    if not SLUG_DESENI.match(slug) or slug in AYRILMIS_SLUGLAR:
        raise KaynakHatasi("gecersiz_slug", "slug")
    kategori = str(govde.get("kategori") or "").strip()
    if kategori not in (kategori_listesi if kategori_listesi is not None else kategori_anahtarlari()):
        raise KaynakHatasi("gecersiz_kategori", "kategori")
    baglanti_turu = str(govde.get("baglanti_turu") or "site").strip()
    if baglanti_turu not in BAGLANTI_TURLERI:
        raise KaynakHatasi("gecersiz_baglanti_turu", "baglanti_turu")
    try:
        sira = int(govde.get("sira") if govde.get("sira") not in (None, "") else 100)
    except (TypeError, ValueError) as exc:
        raise KaynakHatasi("gecersiz_sira", "sira") from exc
    ceviriler = _ceviriler_dogrula(govde.get("ceviriler"))
    adimlar = _adimlar(govde.get("adimlar"))
    etiketler = _etiketler(govde.get("etiketler"))
    return {
        "slug": slug,
        "kategori": kategori,
        "baslik": _metin(govde.get("baslik"), "baslik", SINIR["baslik"], zorunlu=True),
        "ozet": _metin(govde.get("ozet"), "ozet", SINIR["ozet"]) or None,
        "aciklama": _metin(govde.get("aciklama"), "aciklama", SINIR["aciklama"]) or None,
        "adimlar": json.dumps(adimlar, ensure_ascii=False) if adimlar else None,
        "ceviriler": json.dumps(ceviriler, ensure_ascii=False) if ceviriler else None,
        "etiketler": json.dumps(etiketler, ensure_ascii=False) if etiketler else None,
        "baglanti": baglanti_dogrula(govde.get("baglanti")),
        "baglanti_turu": baglanti_turu,
        "lisans": _metin(govde.get("lisans"), "lisans", SINIR["lisans"]) or None,
        "ucretsiz": _bool(govde.get("ucretsiz"), True),
        "acik_kaynak": _bool(govde.get("acik_kaynak"), False),
        "youtube_short": _youtube(govde.get("youtube_short")),
        "one_cikan": _bool(govde.get("one_cikan"), False),
        "sira": max(-100_000, min(100_000, sira)),
        "yayinda": _bool(govde.get("yayinda"), True),
        "dogrulama_tarihi": _tarih_coz(govde.get("dogrulama_tarihi")),
    }


def tohum_girdisi(kayit: Dict[str, Any]) -> Dict[str, Any]:
    """Tohum biçimini (metin alanları dil sözlüğü) panel girdisine çevirir."""

    def dil_sozlugu(alan: str) -> Dict[str, Any]:
        deger = kayit.get(alan)
        if isinstance(deger, dict):
            return deger
        return {"tr": deger} if deger not in (None, "") else {}

    metinler = {a: dil_sozlugu(a) for a in (*METIN_ALANLARI, "adimlar")}
    ceviriler: Dict[str, Dict[str, Any]] = {}
    for dil in CEVIRI_DILLERI:
        satir = {a: metinler[a][dil] for a in metinler if metinler[a].get(dil)}
        if satir:
            ceviriler[dil] = satir
    return {
        **{k: v for k, v in kayit.items() if k not in (*METIN_ALANLARI, "adimlar")},
        **{a: metinler[a].get("tr") for a in metinler},
        "ceviriler": ceviriler,
        "yayinda": kayit.get("yayinda", True),
    }


# ---------------------------------------------------------------------------
# Tohumlama
# ---------------------------------------------------------------------------
async def tohumla(db: AsyncSession, yol: Optional[Path] = None) -> Dict[str, Any]:
    """Tohum dosyasındaki, daha önce hiç eklenmemiş slug'ları ekler. İdempotent.

    * Tablo boşsa (ilk açılış) hepsi eklenir.
    * Tohumda olup izi olmayan slug eklenir; panelde aynı slug elle
      açılmışsa o kayda DOKUNULMAZ, yalnız iz yazılır.
    * İzi olan slug (eklenmiş, sonra düzenlenmiş ya da silinmiş) atlanır:
      panelde yapılan düzenleme ve silme bir sonraki açılışta ezilmez.
    * Hatalı tohum kaydı atlanıp günlüğe yazılır; açılış asla düşmez.
    """
    tohum = tohum_oku(yol)
    anahtarlar = kategori_anahtarlari(yol)
    izler = set((await db.execute(select(KaynakTohumIzi.slug))).scalars().all())
    mevcut = set((await db.execute(select(Kaynaklar.slug))).scalars().all())
    eklenen: List[str] = []
    atlanan: List[str] = []
    yeni_iz: List[str] = []
    for kayit in tohum.get("kaynaklar") or []:
        if not isinstance(kayit, dict):
            continue
        slug = str(kayit.get("slug") or "").strip().lower()
        if not slug or slug in izler or slug in yeni_iz:
            continue
        if slug in mevcut:
            yeni_iz.append(slug)
            continue
        try:
            alanlar = girdiyi_dogrula(tohum_girdisi(kayit), anahtarlar)
        except KaynakHatasi as hata:
            logger.warning("Tohum kaynağı atlandı (%s): %s/%s", slug, hata.kod, hata.alan)
            atlanan.append(slug)
            continue
        db.add(Kaynaklar(**alanlar))
        yeni_iz.append(slug)
        eklenen.append(slug)
    for slug in yeni_iz:
        db.add(KaynakTohumIzi(slug=slug))
    if not yeni_iz:
        return {"eklenen": [], "atlanan": atlanan}
    try:
        await db.commit()
    except IntegrityError:
        # Aynı anda iki süreç tohumladıysa: biri kazandı, diğeri sessizce çekiliyor.
        await db.rollback()
        logger.info("Kaynak tohumlama çakıştı; başka bir süreç tohumlamış.")
        return {"eklenen": [], "atlanan": atlanan}
    if eklenen:
        logger.info("Kaynak tohumlandı: %d yeni (%s)", len(eklenen), ", ".join(eklenen[:10]))
    return {"eklenen": eklenen, "atlanan": atlanan}


async def acilista_tohumla() -> None:
    """Uygulama açılışında çağrılıyor; hata günlüğe yazılır, açılış sürer."""
    from core.database import db_manager

    try:
        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as db:
            await tohumla(db)
    except Exception:  # noqa: BLE001 - açılış asla tohum yüzünden düşmemeli
        logger.exception("Kaynak tohumlama başarısız")
