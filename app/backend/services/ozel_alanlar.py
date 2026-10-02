"""Faz 4W — özel alanlar: tanım doğrulama, değer doğrulama/yazma, toplu okuma.

* Tanımları yalnız ajans yapar (`ozel_alanlar`); varlık türleri: CRM adayı
  (`crm_aday`), proje (`proje`), müşteri hesabı (`hesap`, kimlik = e-posta),
  destek talebi (`destek`).
* "Müşteriye görünür" yalnız proje ve destek talebi alanlarında anlamlı:
  müşteri panelinde salt okunur gösterilir, müşteri kurallarının koşullarında
  ve yer tutucularında kullanılabilir. Aday ve hesap alanları müşteriye hiç
  gitmez.
* Değerler ayrı tabloda (`ozel_alan_degerleri`), JSON metni. Boş değer
  (``""``, ``None``, ``[]``) satırı siler. Mevcut tablolara sütun eklenmiyor.
* Tanım silinince (çöp kutusuna) değerler kalıyor: geri alınınca dönüyor;
  bu sırada tanımsız değerler hiçbir yere çıkmıyor.
"""

import json
import math
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from models.otomasyon import OzelAlanDegerleri, OzelAlanlar
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

VARLIKLAR: Tuple[str, ...] = ("crm_aday", "proje", "hesap", "destek")
#: "Müşteriye görünür" seçeneğinin anlamlı olduğu varlıklar.
GORUNUR_OLABILIR: Tuple[str, ...] = ("proje", "destek")
TURLER: Tuple[str, ...] = ("metin", "sayi", "tarih", "secim", "coklu_secim", "evet_hayir", "url")
#: CRM gömülebilir formunda sorulabilen türler (betik küçük kalsın).
FORM_TURLERI: Tuple[str, ...] = ("metin", "sayi", "url", "secim")
VARLIK_ALAN_SINIRI = 50
SECENEK_SINIRI = 30
SECENEK_UZUNLUGU = 60
METIN_SINIRI = 1000
URL_SINIRI = 500
_ANAHTAR = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OzelAlanHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def _liste(ham: Any) -> List[Any]:
    if isinstance(ham, list):
        return ham
    try:
        d = json.loads(ham) if ham else []
    except (TypeError, ValueError):
        return []
    return d if isinstance(d, list) else []


def eposta_duzelt(ham: Any) -> str:
    return str(ham or "").strip().lower()


# ---------------------------------------------------------------------------
# Tanım
# ---------------------------------------------------------------------------
def anahtar_uret(ad: str) -> str:
    """Addan kalıcı anahtar önerisi (Türkçe harfler sadeleşir)."""
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")
    s = re.sub(r"[^a-z0-9]+", "_", (ad or "").translate(tablo).lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "alan_" + s
    return s[:40].rstrip("_")


def _secenekler(ham: Any) -> List[str]:
    if isinstance(ham, str):
        ham = [p for p in re.split(r"[\n,;]+", ham)]
    if not isinstance(ham, list):
        raise OzelAlanHatasi("secenek_gecersiz")
    sonuc: List[str] = []
    for s in ham:
        if not isinstance(s, (str, int, float)) or isinstance(s, bool):
            raise OzelAlanHatasi("secenek_gecersiz")
        s = " ".join(str(s).split())
        if not s:
            continue
        if len(s) > SECENEK_UZUNLUGU:
            raise OzelAlanHatasi("secenek_uzun", en_cok=SECENEK_UZUNLUGU)
        if s not in sonuc:
            sonuc.append(s)
    if len(sonuc) > SECENEK_SINIRI:
        raise OzelAlanHatasi("secenek_sayisi", en_cok=SECENEK_SINIRI)
    return sonuc


def tanim_dogrula(veri: Dict[str, Any], mevcut: Optional[OzelAlanlar] = None) -> Dict[str, Any]:
    """Panel gövdesi → sütun değerleri. Varlık ve anahtar oluşturulduktan sonra değişmez
    (koşullar ve yer tutucular anahtara bağlı)."""
    yeni = mevcut is None
    sonuc: Dict[str, Any] = {}
    if yeni:
        varlik = str(veri.get("varlik") or "")
        if varlik not in VARLIKLAR:
            raise OzelAlanHatasi("varlik_gecersiz")
        sonuc["varlik"] = varlik
    varlik = sonuc.get("varlik") or mevcut.varlik  # type: ignore[union-attr]
    if "ad" in veri or yeni:
        ad = " ".join(str(veri.get("ad") or "").split())
        if not ad:
            raise OzelAlanHatasi("ad_gerekli")
        if len(ad) > 80:
            raise OzelAlanHatasi("ad_uzun", en_cok=80)
        sonuc["ad"] = ad
    if yeni:
        anahtar = str(veri.get("anahtar") or "").strip().lower() or anahtar_uret(sonuc["ad"])
        if not _ANAHTAR.match(anahtar):
            raise OzelAlanHatasi("anahtar_gecersiz")
        sonuc["anahtar"] = anahtar
    if "tur" in veri or yeni:
        tur = str(veri.get("tur") or "metin")
        if tur not in TURLER:
            raise OzelAlanHatasi("tur_gecersiz")
        if not yeni and tur != mevcut.tur:  # type: ignore[union-attr]
            # Tür değişirse kayıtlı değerler geçersiz kalabilir: yalnız uyumlu geçişler.
            uyumlu = {("metin", "url"), ("url", "metin"), ("secim", "coklu_secim"), ("metin", "secim")}
            if (mevcut.tur, tur) not in uyumlu:  # type: ignore[union-attr]
                raise OzelAlanHatasi("tur_degistirilemez")
        sonuc["tur"] = tur
    tur = sonuc.get("tur") or mevcut.tur  # type: ignore[union-attr]
    if "secenekler" in veri or yeni or "tur" in sonuc:
        if tur in ("secim", "coklu_secim"):
            ham = veri.get("secenekler") if "secenekler" in veri else _liste(getattr(mevcut, "secenekler", None))
            secenekler = _secenekler(ham)
            if not secenekler:
                raise OzelAlanHatasi("secenek_gerekli")
            sonuc["secenekler"] = json.dumps(secenekler, ensure_ascii=False)
        else:
            sonuc["secenekler"] = None
    if "zorunlu" in veri:
        sonuc["zorunlu"] = veri.get("zorunlu") is True
    elif yeni:
        sonuc["zorunlu"] = False
    if "sira" in veri:
        s = veri.get("sira")
        if isinstance(s, bool) or not isinstance(s, (int, float)) or int(s) != s or not 0 <= int(s) <= 10000:
            raise OzelAlanHatasi("sira_gecersiz")
        sonuc["sira"] = int(s)
    if "musteriye_gorunur" in veri or yeni:
        gorunur = veri.get("musteriye_gorunur") is True
        if gorunur and varlik not in GORUNUR_OLABILIR:
            raise OzelAlanHatasi("gorunurluk_desteklenmiyor")
        sonuc["musteriye_gorunur"] = gorunur
    if "aktif" in veri:
        sonuc["aktif"] = veri.get("aktif") is not False
    return sonuc


def tanim_sozlugu(a: OzelAlanlar) -> Dict[str, Any]:
    return {
        "id": a.id,
        "varlik": a.varlik,
        "anahtar": a.anahtar,
        "ad": a.ad,
        "tur": a.tur,
        "secenekler": _liste(a.secenekler),
        "zorunlu": bool(a.zorunlu),
        "sira": int(a.sira or 0),
        "musteriye_gorunur": bool(a.musteriye_gorunur) and a.varlik in GORUNUR_OLABILIR,
        "aktif": a.aktif is not False,
    }


async def tanimlar(db: AsyncSession, varlik: Optional[str] = None, *, yalniz_gorunur: bool = False,
                   yalniz_aktif: bool = True) -> List[OzelAlanlar]:
    sorgu = select(OzelAlanlar)
    if varlik:
        sorgu = sorgu.where(OzelAlanlar.varlik == varlik)
    if yalniz_aktif:
        sorgu = sorgu.where(OzelAlanlar.aktif.is_not(False))
    if yalniz_gorunur:
        sorgu = sorgu.where(OzelAlanlar.musteriye_gorunur.is_(True), OzelAlanlar.varlik.in_(GORUNUR_OLABILIR))
    return list((await db.execute(sorgu.order_by(OzelAlanlar.varlik, OzelAlanlar.sira, OzelAlanlar.id))).scalars().all())


async def anahtar_haritasi(db: AsyncSession, *, yalniz_gorunur: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """Varlık → [{anahtar, ad, tur}] (kural şeması ve doğrulaması için)."""
    harita: Dict[str, List[Dict[str, Any]]] = {v: [] for v in VARLIKLAR}
    for a in await tanimlar(db, yalniz_gorunur=yalniz_gorunur):
        harita[a.varlik].append({"anahtar": a.anahtar, "ad": a.ad, "tur": a.tur, "secenekler": _liste(a.secenekler)})
    return harita


# ---------------------------------------------------------------------------
# Değer
# ---------------------------------------------------------------------------
def bos_mu(deger: Any) -> bool:
    return deger is None or (isinstance(deger, str) and not deger.strip()) or (isinstance(deger, list) and not deger)


def deger_dogrula(alan: OzelAlanlar, ham: Any) -> Any:
    """Geçerli (JSON'a yazılacak) değer ya da None (boş). Geçersizse OzelAlanHatasi."""
    if bos_mu(ham):
        return None

    def hata(kod: str = "deger_gecersiz", **ek: Any) -> OzelAlanHatasi:
        return OzelAlanHatasi(kod, alan=alan.anahtar, **ek)

    tur = alan.tur
    if tur == "metin":
        if not isinstance(ham, (str, int, float)) or isinstance(ham, bool):
            raise hata()
        s = str(ham).strip()
        if len(s) > METIN_SINIRI:
            raise hata("deger_uzun", en_cok=METIN_SINIRI)
        return s
    if tur == "sayi":
        if isinstance(ham, bool):
            raise hata()
        if isinstance(ham, str):
            try:
                ham = float(ham.strip().replace(",", "."))
            except ValueError:
                raise hata()
        if not isinstance(ham, (int, float)) or math.isnan(ham) or math.isinf(ham) or abs(ham) > 1e15:
            raise hata()
        return int(ham) if float(ham).is_integer() else round(float(ham), 6)
    if tur == "tarih":
        try:
            return date.fromisoformat(str(ham).strip()[:10]).isoformat()
        except ValueError:
            raise hata()
    if tur == "secim":
        s = " ".join(str(ham).split()) if isinstance(ham, (str, int, float)) and not isinstance(ham, bool) else None
        if s is None or s not in _liste(alan.secenekler):
            raise hata("secenek_disi")
        return s
    if tur == "coklu_secim":
        if isinstance(ham, str):
            ham = [ham]
        if not isinstance(ham, list):
            raise hata()
        izinli = _liste(alan.secenekler)
        sonuc: List[str] = []
        for s in ham:
            s = " ".join(str(s).split()) if isinstance(s, (str, int, float)) and not isinstance(s, bool) else None
            if s is None or s not in izinli:
                raise hata("secenek_disi")
            if s not in sonuc:
                sonuc.append(s)
        return sonuc or None
    if tur == "evet_hayir":
        if not isinstance(ham, bool):
            raise hata()
        return ham
    if tur == "url":
        s = str(ham).strip() if isinstance(ham, str) else ""
        p = urlparse(s)
        if not s or len(s) > URL_SINIRI or p.scheme not in ("http", "https") or not p.hostname or any(c.isspace() for c in s):
            raise hata()
        return s
    raise hata()


def _coz(metin: Optional[str]) -> Any:
    try:
        return json.loads(metin) if metin is not None else None
    except (TypeError, ValueError):
        return None


async def degerler(db: AsyncSession, varlik: str, varlik_id: Any, *, yalniz_gorunur: bool = False) -> Dict[str, Any]:
    """{anahtar: değer} — yalnız aktif tanımların değerleri."""
    return (await toplu_degerler(db, varlik, [varlik_id], yalniz_gorunur=yalniz_gorunur)).get(str(varlik_id), {})


async def toplu_degerler(db: AsyncSession, varlik: str, idler: Iterable[Any], *,
                         yalniz_gorunur: bool = False) -> Dict[str, Dict[str, Any]]:
    idler = [str(i) for i in idler if i is not None]
    if not idler:
        return {}
    alanlar = {a.id: a for a in await tanimlar(db, varlik, yalniz_gorunur=yalniz_gorunur)}
    if not alanlar:
        return {}
    sonuc: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(idler), 500):
        satirlar = (
            await db.execute(
                select(OzelAlanDegerleri.varlik_id, OzelAlanDegerleri.alan_id, OzelAlanDegerleri.deger).where(
                    OzelAlanDegerleri.varlik == varlik,
                    OzelAlanDegerleri.varlik_id.in_(idler[i:i + 500]),
                    OzelAlanDegerleri.alan_id.in_(list(alanlar)),
                )
            )
        ).all()
        for vid, aid, deger in satirlar:
            sonuc.setdefault(vid, {})[alanlar[aid].anahtar] = _coz(deger)
    return sonuc


async def sozluklere_ekle(db: AsyncSession, varlik: str, kayitlar: List[Dict[str, Any]], *,
                          yalniz_gorunur: bool = False, kimlik_alani: str = "id") -> List[Dict[str, Any]]:
    """Herkese açık API: her kayda `ozel_alanlar` sözlüğü (tanım yoksa boş sözlük)."""
    toplu = await toplu_degerler(db, varlik, [k.get(kimlik_alani) for k in kayitlar], yalniz_gorunur=yalniz_gorunur)
    for k in kayitlar:
        k["ozel_alanlar"] = toplu.get(str(k.get(kimlik_alani)), {})
    return kayitlar


async def degerleri_yaz(db: AsyncSession, varlik: str, varlik_id: Any, girdi: Dict[str, Any], *,
                        kisi: Optional[str] = None, tam: bool = False) -> Dict[str, Any]:
    """`girdi`: {anahtar: değer}. `tam=True` (panelde bütün bölüm kaydedildi): girdide
    olmayan zorunlu alan da denetlenir. Commit çağırana. Dönen: güncel {anahtar: değer}."""
    if not isinstance(girdi, dict):
        raise OzelAlanHatasi("govde_gecersiz")
    alanlar = {a.anahtar: a for a in await tanimlar(db, varlik)}
    for anahtar in girdi:
        if anahtar not in alanlar:
            raise OzelAlanHatasi("alan_yok", alan=str(anahtar)[:40])
    temiz = {anahtar: deger_dogrula(alanlar[anahtar], ham) for anahtar, ham in girdi.items()}
    mevcut = await degerler(db, varlik, varlik_id)
    for anahtar, alan in alanlar.items():
        if not alan.zorunlu:
            continue
        if anahtar in temiz and temiz[anahtar] is None:
            raise OzelAlanHatasi("alan_gerekli", alan=anahtar)
        if tam and anahtar not in temiz and bos_mu(mevcut.get(anahtar)):
            raise OzelAlanHatasi("alan_gerekli", alan=anahtar)
    vid = str(varlik_id)
    satirlar = {
        s.alan_id: s
        for s in (
            await db.execute(select(OzelAlanDegerleri).where(OzelAlanDegerleri.varlik == varlik, OzelAlanDegerleri.varlik_id == vid))
        ).scalars().all()
    }
    for anahtar, deger in temiz.items():
        alan = alanlar[anahtar]
        satir = satirlar.get(alan.id)
        if deger is None:
            if satir is not None:
                await db.delete(satir)
            continue
        metin = json.dumps(deger, ensure_ascii=False)
        if satir is None:
            db.add(OzelAlanDegerleri(varlik=varlik, varlik_id=vid, alan_id=alan.id, deger=metin, guncelleyen=kisi))
        elif satir.deger != metin:
            satir.deger = metin
            satir.guncelleyen = kisi
    await db.flush()
    return await degerler(db, varlik, varlik_id)


async def varlik_degerlerini_sil(db: AsyncSession, varlik: str, varlik_id: Any) -> None:
    await db.execute(delete(OzelAlanDegerleri).where(OzelAlanDegerleri.varlik == varlik, OzelAlanDegerleri.varlik_id == str(varlik_id)))


async def bolum(db: AsyncSession, varlik: str, varlik_id: Any, *, yalniz_gorunur: bool = False) -> Dict[str, Any]:
    """Ekran bölümü: tanımlar + değerler."""
    alanlar = await tanimlar(db, varlik, yalniz_gorunur=yalniz_gorunur)
    return {
        "varlik": varlik,
        "varlik_id": str(varlik_id),
        "alanlar": [tanim_sozlugu(a) for a in alanlar],
        "degerler": await degerler(db, varlik, varlik_id, yalniz_gorunur=yalniz_gorunur),
    }


def eposta_gecerli(e: str) -> bool:
    return bool(_EPOSTA.match(e or "")) and len(e) <= 254


__all__ = [
    "VARLIKLAR", "TURLER", "FORM_TURLERI", "OzelAlanHatasi", "tanim_dogrula", "tanim_sozlugu", "tanimlar",
    "anahtar_haritasi", "deger_dogrula", "degerler", "toplu_degerler", "sozluklere_ekle", "degerleri_yaz", "bolum",
]
