"""Faz 4V — herkese açık modül vitrini: veri ve teklif talebi.

Veri nereden geliyor?
---------------------
Vitrinde ikinci bir modül listesi YOK. Hangi modülün vitrinde olduğu,
adı/ikonu/kategorisi/durumu modül kaydından (`core/moduller.py`) TÜRETİLİYOR:

* **Satışta (ayrıntı sayfası var):** müşteriye görünen, çekirdek olmayan,
  herkese zaten açık olmayan (`varsayilan_acik=False`) ve "yakında" olmayan
  modüller — yani müşteriye ayrıca açılan/satılan modüller
  (`core.sektor_paketleri.satilabilir_mi`).
* **Yakında:** aynı koşul, durum "yakinda" — ayrıntı sayfası yok.
* **Her portalda gelenler (temeller):** müşteriye görünen, varsayılan açık
  modüller (profil/bildirim/hesap hareketleri gibi hesap ayarları hariç) —
  yalnız ad olarak, ayrıntı sayfası yok.
* **Sektör paketleri:** `core/sektor_paketleri.py`.

Tanıtım metinleri (özet, kimin için, özellikler, SSS) ön yüz ek paketinde
(`src/i18n/ek/modulVitrini/<dil>.json`, 7 dil); modül adları ve kategori adları
mevcut modül ek paketinden (`src/i18n/ek/modul`).

Fiyat
-----
Fiyatlandırma v5 tablolarında (`pricing_*`) modül başına fiyat yok: oradaki
"28 modül" (`pricing_addons`) ölçek başına web projesi eklentileri, portal
modülleri değil. Kayıttaki bağ `Modul.paketler` → `pricing_scales.kod`
(ALFA/BETA/OMEGA/SIGMA): o pakete sahip müşteride modül açık. Bu yüzden:

* `paketler`i olan modülde "en düşük pakete dahil" + o paketin BAŞLANGIÇ
  aylık fiyatı (bütün profiller içinde en düşüğü) — Hizmetler sayfasındaki
  fiyatla aynı hesap (`core/fiyat_hesaplama.hesapla`, aylık).
* `paketler`i olmayan (ayrı satılan) modülde fiyat yok → "teklif alın".
  Kayıttaki yorumlardaki "önerilen fiyat" notları fiyat kaynağı değil.

Ön yüz derlemesi
----------------
Prerender bu yapının depodaki kopyasını (`app/frontend/prerender/
modul-vitrini-veri.json`) kullanıyor; kopya `scripts/modul_vitrini_tohum.py`
ile üretiliyor ve test kayıtla aynı olduğunu doğruluyor (fiyat yok — fiyat
canlı uçtan).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from core import moduller as manifest
from core import sektor_paketleri as paketler
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Yapı sürümü (ön yüz kopyasıyla birlikte değişir).
SURUM = 1

#: Kategori bölümlerinin vitrindeki sırası (ziyaretçi için en somut olandan).
#: Burada olmayan bir kategori (yeni eklenirse) sona eklenir.
KATEGORI_SIRASI: Tuple[str, ...] = (
    "dijital_kimlik", "is_araclari", "icerik", "sektorel", "hizmet", "analiz", "finans", "cekirdek",
)

#: "İlgili modüller" kutusunda en çok kaç modül.
ILGILI_SAYISI = 4

#: Hesap ayarı niteliğindeki temel modüller vitrinde sayılmıyor.
_HESAP_AYARI_YERLESIMI = "profil"

ALAN_SINIRI = {"ad": 120, "eposta": 254, "telefon": 40, "not": 2000, "isletme_turu": 40}

#: Aynı e-posta + aynı modül/paket bu süre içinde tekrar gelirse yeni kayıt açılmaz (çift tık).
TEKRAR_SN = 60

DIGER_ISLETME = "diger"


# ---------------------------------------------------------------------------
# Yapı (kayıttan türetilen)
# ---------------------------------------------------------------------------
def slug(anahtar: str) -> str:
    return anahtar.replace("_", "-")


def satista_mi(m: manifest.Modul) -> bool:
    return paketler.satilabilir_mi(m)


def yakinda_mi(m: manifest.Modul) -> bool:
    return m.musteriye_gorunur and not m.cekirdek and not m.varsayilan_acik and m.durum == "yakinda"


def temel_mi(m: manifest.Modul) -> bool:
    return (
        m.musteriye_gorunur
        and m.varsayilan_acik
        and m.durum != "yakinda"
        and m.musteri_sekmesi != "profile"
        and _HESAP_AYARI_YERLESIMI not in m.yerlesim
    )


def _kategori_sirasi(kategori: str) -> int:
    try:
        return KATEGORI_SIRASI.index(kategori)
    except ValueError:
        return len(KATEGORI_SIRASI) + manifest.KATEGORILER.index(kategori) if kategori in manifest.KATEGORILER else 99


def satistakiler() -> List[manifest.Modul]:
    """Satıştaki modüller: kategori sırası, kategori içinde kayıt sırası."""
    sira = {m.anahtar: i for i, m in enumerate(manifest.MODULLER)}
    return sorted((m for m in manifest.MODULLER if satista_mi(m)), key=lambda m: (_kategori_sirasi(m.kategori), sira[m.anahtar]))


def en_dusuk_paket(m: manifest.Modul) -> Optional[str]:
    """Modülün dahil olduğu en düşük ölçek (ALFA < BETA < OMEGA < SIGMA)."""
    for kod in manifest.PAKETLER:
        if kod in m.paketler:
            return kod
    return None


def ilgili_moduller(m: manifest.Modul, satistaki_anahtarlar: Optional[set] = None) -> List[str]:
    """Aynı sektör paketinde geçenler → bağımlılık ilişkisi → aynı ölçek paketine dahil olanlar →
    aynı kategori (en çok ILGILI_SAYISI)."""
    satistaki = satistaki_anahtarlar if satistaki_anahtarlar is not None else {x.anahtar for x in satistakiler()}
    aday: List[str] = []
    for p in paketler.iceren_paketler(m.anahtar):
        aday.extend(p.moduller)
    aday.extend(m.bagimliliklar)
    aday.extend(x.anahtar for x in manifest.bagimli_olanlar(m.anahtar))
    paket = en_dusuk_paket(m)
    if paket:
        aday.extend(x.anahtar for x in satistakiler() if en_dusuk_paket(x) == paket)
    aday.extend(x.anahtar for x in satistakiler() if x.kategori == m.kategori)
    sonuc: List[str] = []
    for k in aday:
        if k != m.anahtar and k in satistaki and k not in sonuc:
            sonuc.append(k)
        if len(sonuc) >= ILGILI_SAYISI:
            break
    return sonuc


def yapi() -> Dict[str, Any]:
    """Vitrinin kayıttan türetilen yapısı (fiyatsız). Ön yüzdeki kopyası bununla AYNI olmalı."""
    satistaki = satistakiler()
    anahtarlar = {m.anahtar for m in satistaki}
    kategoriler: List[str] = []
    for m in satistaki:
        if m.kategori not in kategoriler:
            kategoriler.append(m.kategori)
    return {
        "surum": SURUM,
        "olcekler": list(manifest.PAKETLER),
        "kategoriler": kategoriler,
        "moduller": [
            {
                "anahtar": m.anahtar,
                "slug": slug(m.anahtar),
                "ikon": m.ikon,
                "kategori": m.kategori,
                "durum": m.durum,
                "paket": en_dusuk_paket(m),
                "ilgili": ilgili_moduller(m, anahtarlar),
                "sektor_paketleri": [p.anahtar for p in paketler.iceren_paketler(m.anahtar)],
            }
            for m in satistaki
        ],
        "yakinda": [
            {"anahtar": m.anahtar, "ikon": m.ikon, "kategori": m.kategori}
            for m in manifest.MODULLER
            if yakinda_mi(m)
        ],
        "temeller": [{"anahtar": m.anahtar, "ikon": m.ikon} for m in manifest.MODULLER if temel_mi(m)],
        "paketler": [p.sozluk() for p in paketler.SEKTOR_PAKETLERI],
    }


def satistaki_modul(anahtar: str) -> Optional[manifest.Modul]:
    m = manifest.modul(anahtar)
    return m if m is not None and satista_mi(m) else None


# ---------------------------------------------------------------------------
# Fiyat (fiyatlandırma v5 — Hizmetler sayfasıyla aynı hesap)
# ---------------------------------------------------------------------------
def _ceviri_adlari(ham: Optional[str], tr: str) -> Dict[str, str]:
    adlar = {"tr": tr}
    try:
        veri = json.loads(ham) if ham else {}
    except (ValueError, TypeError):
        veri = {}
    if isinstance(veri, dict):
        for dil, alanlar in veri.items():
            if isinstance(alanlar, dict) and isinstance(alanlar.get("ad"), str) and alanlar["ad"].strip():
                adlar[str(dil)[:5]] = alanlar["ad"].strip()
    return adlar


async def fiyatlar(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """Ölçek kodu → {baslangic_aylik, para_birimi, ad: {dil: ad}}. Tablo yoksa/boşsa {} (fiyat gösterilmez)."""
    from core.fiyat_hesaplama import FiyatHesaplamaHatasi, hesapla
    from models.pricing import Pricing_profiles, Pricing_scales

    try:
        olcekler = (await db.execute(select(Pricing_scales))).scalars().all()
        profiller = (await db.execute(select(Pricing_profiles))).scalars().all()
    except Exception:  # noqa: BLE001 - fiyat yoksa vitrin yine çalışır ("teklif alın")
        logger.exception("Modül vitrini: fiyat tabloları okunamadı")
        return {}
    baz = {s.kod: float(s.baz_aylik_fiyat_usd) for s in olcekler if s.baz_aylik_fiyat_usd is not None}
    carpanlar = {p.kod: float(p.carpan) for p in profiller if p.carpan is not None}
    sonuc: Dict[str, Dict[str, Any]] = {}
    if not carpanlar:
        return sonuc
    for s in olcekler:
        if s.kod not in baz:
            continue
        tutarlar = []
        for profil in carpanlar:
            try:
                r = hesapla(
                    scale_kod=s.kod, profile_kod=profil, period="aylik", addon_kodlari=[],
                    scale_baz_fiyatlari=baz, profile_carpanlari=carpanlar, addon_fiyatlari={},
                )
            except FiyatHesaplamaHatasi:
                continue
            if r.paket_fiyat > 0:
                tutarlar.append(r.paket_fiyat)
        if tutarlar:
            sonuc[s.kod] = {
                "baslangic_aylik": min(tutarlar),
                "para_birimi": "USD",
                "ad": _ceviri_adlari(s.ceviriler, s.ad),
            }
    return sonuc


async def vitrin_verisi(db: AsyncSession) -> Dict[str, Any]:
    return {**yapi(), "fiyatlar": await fiyatlar(db)}


# ---------------------------------------------------------------------------
# Teklif talebi
# ---------------------------------------------------------------------------
class TalepHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek


def _metin(veri: Dict[str, Any], ad: str, sinir: int, tek_satir: bool = True) -> str:
    ham = veri.get(ad)
    if ham is None:
        return ""
    if not isinstance(ham, (str, int, float)) or isinstance(ham, bool):
        raise TalepHatasi("alan_gecersiz", alan=ad)
    s = str(ham).strip()
    if tek_satir:
        s = " ".join(s.split())
    if len(s) > sinir:
        raise TalepHatasi("alan_uzun", alan=ad, en_cok=sinir)
    return s


def isletme_turleri() -> List[str]:
    return [p.anahtar for p in paketler.SEKTOR_PAKETLERI] + [DIGER_ISLETME]


def girdiyi_dogrula(veri: Dict[str, Any]) -> Dict[str, Any]:
    """Gövdeyi doğrular; temiz alanlar ya da TalepHatasi."""
    from services.crm import eposta_duzelt, eposta_gecerli

    tur = veri.get("tur")
    if tur not in ("modul", "paket"):
        raise TalepHatasi("tur_gecersiz")
    anahtar = veri.get("anahtar")
    if not isinstance(anahtar, str):
        raise TalepHatasi("anahtar_gecersiz")
    if tur == "modul":
        hedef = satistaki_modul(anahtar)
        if hedef is None:
            raise TalepHatasi("anahtar_gecersiz")
        hedef_ad = hedef.ad_varsayilan["tr"]
        modul_listesi = [anahtar]
    else:
        p = paketler.paket(anahtar)
        if p is None:
            raise TalepHatasi("anahtar_gecersiz")
        hedef_ad = p.ad_varsayilan["tr"]
        modul_listesi = list(p.moduller)

    ad = _metin(veri, "ad", ALAN_SINIRI["ad"])
    if not ad:
        raise TalepHatasi("ad_gerekli")
    eposta = eposta_duzelt(_metin(veri, "eposta", ALAN_SINIRI["eposta"]))
    if not eposta_gecerli(eposta):
        raise TalepHatasi("eposta_gecersiz")
    telefon = _metin(veri, "telefon", ALAN_SINIRI["telefon"])
    isletme = _metin(veri, "isletme_turu", ALAN_SINIRI["isletme_turu"])
    if isletme and isletme not in isletme_turleri():
        raise TalepHatasi("isletme_turu_gecersiz")
    not_ = _metin(veri, "not", ALAN_SINIRI["not"], tek_satir=False)
    dil = str(veri.get("dil") or "tr").strip().lower()[:2]
    return {
        "tur": tur, "anahtar": anahtar, "hedef_ad": hedef_ad, "moduller": modul_listesi,
        "ad": ad, "eposta": eposta, "telefon": telefon or None, "isletme_turu": isletme or None,
        "not": not_ or None, "dil": dil,
    }


def kaynak_degeri(tur: str, anahtar: str) -> str:
    """`inquiries.source` — CRM kancası bunu `modul_vitrini` kaynağına eşliyor."""
    return f"modul_vitrini:{tur}:{anahtar}"[:120]


def konu_ve_mesaj(g: Dict[str, Any]) -> Tuple[str, str]:
    """Yönetici için (Türkçe) konu ve mesaj."""
    adlar = []
    for k in g["moduller"]:
        m = manifest.modul(k)
        adlar.append(m.ad_varsayilan["tr"] if m else k)
    if g["tur"] == "modul":
        konu = f"Modül talebi: {g['hedef_ad']}"
        satirlar = [f"Modül vitrininden teklif talebi — modül: {g['hedef_ad']} ({g['anahtar']})"]
    else:
        konu = f"Paket talebi: {g['hedef_ad']}"
        satirlar = [
            f"Modül vitrininden teklif talebi — sektör paketi: {g['hedef_ad']} ({g['anahtar']})",
            "Paketteki modüller: " + ", ".join(adlar),
        ]
    if g["isletme_turu"]:
        p = paketler.paket(g["isletme_turu"])
        satirlar.append("İşletme türü: " + (p.ad_varsayilan["tr"] if p else "Diğer"))
    satirlar.append(f"Sayfa dili: {g['dil']}")
    if g["not"]:
        satirlar.extend(["", g["not"]])
    return konu[:200], "\n".join(satirlar)


async def son_ayni_talep(db: AsyncSession, eposta: str, kaynak: str) -> bool:
    from models.inquiries import Inquiries

    esik = datetime.now(timezone.utc) - timedelta(seconds=TEKRAR_SN)
    sayi = (
        await db.execute(
            select(func.count(Inquiries.id)).where(
                func.lower(Inquiries.email) == eposta, Inquiries.source == kaynak, Inquiries.created_at >= esik
            )
        )
    ).scalar()
    return bool(sayi)


async def talep_olustur(db: AsyncSession, veri: Dict[str, Any]) -> Dict[str, Any]:
    """Doğrulanmış talebi `inquiries`e yazar (CRM kancası adayı aynı işlemde açar).

    Pazarlama izni (Faz 4G) yalnız JSON `true` ise; adaya izin + zaman + metin
    sürümü yazılır. Dönen: {"talep_id", "aday_id", "tekrar"}.
    """
    from models.inquiries import Inquiries
    from services import pazarlama_izni

    g = girdiyi_dogrula(veri)
    kaynak = kaynak_degeri(g["tur"], g["anahtar"])
    if await son_ayni_talep(db, g["eposta"], kaynak):
        return {"talep_id": None, "aday_id": None, "tekrar": True, "girdi": g}
    konu, mesaj = konu_ve_mesaj(g)
    an = datetime.now(timezone.utc)
    talep = Inquiries(
        name=g["ad"], email=g["eposta"], phone=g["telefon"], subject=konu, message=mesaj,
        status="new", source=kaynak, created_at=an,
    )
    db.add(talep)
    await db.flush()  # CRM kancası (after_flush) adayı burada açıyor/bağlıyor
    aday_id = await pazarlama_izni.bagli_adayi_bul(db, "inquiries", talep.id)
    if pazarlama_izni.izin_verildi_mi(veri.get("pazarlama_izni")) and aday_id:
        await pazarlama_izni.adaya_isle(db, aday_id, an, kaynak, pazarlama_izni.surum_etiketi(g["dil"]))
    await db.commit()
    return {"talep_id": talep.id, "aday_id": aday_id, "tekrar": False, "girdi": g, "konu": konu, "mesaj": mesaj}


__all__ = [
    "SURUM", "KATEGORI_SIRASI", "ILGILI_SAYISI", "ALAN_SINIRI", "TEKRAR_SN", "DIGER_ISLETME",
    "slug", "satista_mi", "yakinda_mi", "temel_mi", "satistakiler", "en_dusuk_paket", "ilgili_moduller",
    "yapi", "satistaki_modul", "fiyatlar", "vitrin_verisi", "TalepHatasi", "girdiyi_dogrula", "isletme_turleri",
    "kaynak_degeri", "konu_ve_mesaj", "son_ayni_talep", "talep_olustur",
]
