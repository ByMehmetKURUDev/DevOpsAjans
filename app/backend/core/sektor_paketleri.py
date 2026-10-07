"""Sektör paketleri (Faz 4V): hazır modül demetlerinin TEK kaynağı.

Neden ayrı dosya?
-----------------
Modül kaydı (`core/moduller.py`) "bir modül nedir" sorusunun cevabı; paket ise
o modüllerden bir işletme türü için seçilmiş bir demet. Paket burada yalnız
gerçek modül anahtarlarını listeliyor — ad, ikon, kategori, durum hep kayıttan
okunuyor, ikinci bir modül listesi yok. `paket_hatalari()` her anahtarın
kayıtta olduğunu, müşteriye satılabilir olduğunu (yönetici modülü, çekirdek
ya da "yakında" değil) denetliyor; test de bunu çağırıyor.

Kim kullanıyor?
---------------
* Herkese açık modül vitrini (`/moduller`, `services/modul_vitrini.py`):
  "Sektöre göre hazır paketler" bölümü ve paket sayfaları.
* İleride Modüller panelinde "paketi aç" (bir müşteriye paketin modüllerini
  tek tıkla açma): `acilacak_moduller()` paketin modüllerini bağımlılıklarıyla
  birlikte, açılma sırasına göre veriyor — panel tarafı bu fazda yok.

Görünen metinler
----------------
Paket adı, kısa açıklaması ve "kimin için" metni ön yüz ek paketinde
(`src/i18n/ek/modulVitrini/<dil>.json` → `modulVitrini.p.<anahtar>`, 7 dil).
`ad_varsayilan` yalnız sunucunun kendi yazdığı metinler için (talep konusu);
test, ek paketteki tr/en adlarla aynı olduğunu doğruluyor.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core import moduller as manifest


@dataclass(frozen=True)
class SektorPaketi:
    anahtar: str
    ad_varsayilan: Dict[str, str]  # {"tr": ..., "en": ...} — yalnız sunucu metinleri için
    ikon: str  # lucide ikon adı (src/lib/modulIkonlari.ts'te olmalı)
    moduller: Tuple[str, ...]

    @property
    def slug(self) -> str:
        return self.anahtar.replace("_", "-")

    def sozluk(self) -> Dict[str, object]:
        return {"anahtar": self.anahtar, "slug": self.slug, "ikon": self.ikon, "moduller": list(self.moduller)}


# Sıra = vitrindeki sıra. Modüller paket içinde önem sırasıyla.
SEKTOR_PAKETLERI: Tuple[SektorPaketi, ...] = (
    SektorPaketi(
        anahtar="restoran_kafe",
        ad_varsayilan={"tr": "Restoran ve kafe", "en": "Restaurant and café"},
        ikon="UtensilsCrossed",
        moduller=("qr_menu", "whatsapp_katalog", "google_yorum_sayfasi", "dinamik_qr", "stok_pos"),
    ),
    SektorPaketi(
        anahtar="klinik_guzellik",
        ad_varsayilan={"tr": "Klinik, güzellik ve danışmanlık", "en": "Clinic, beauty and consulting"},
        ikon="CalendarCheck",
        moduller=("randevu", "dijital_kartvizit", "ai_asistan", "google_yorum_sayfasi"),
    ),
    SektorPaketi(
        anahtar="teknik_servis",
        ad_varsayilan={"tr": "Teknik servis ve bakım", "en": "Field service and maintenance"},
        ikon="Wrench",
        moduller=("saha_servisi", "randevu", "google_yorum_sayfasi"),
    ),
    SektorPaketi(
        anahtar="egitim_etkinlik",
        ad_varsayilan={"tr": "Eğitim, kurs ve etkinlik", "en": "Training, courses and events"},
        ikon="Ticket",
        # Faz 6K: eğitim modülü (kurs, ders, yoklama, quiz, sertifika) paketin başında.
        moduller=("egitim", "etkinlik_bilet", "eposta_pazarlama", "randevu"),
    ),
    SektorPaketi(
        anahtar="ajans_serbest",
        ad_varsayilan={"tr": "Ajans ve serbest çalışan", "en": "Agency and freelancer"},
        ikon="PenTool",
        moduller=("icerik_studyosu", "randevu", "dijital_kartvizit", "otomasyon"),
    ),
    SektorPaketi(
        anahtar="eticaret_kobi",
        ad_varsayilan={"tr": "E-ticaret ve KOBİ", "en": "E-commerce and SMB"},
        ikon="ShoppingBag",
        moduller=("eposta_pazarlama", "ai_asistan", "dinamik_qr", "otomasyon", "stok_pos"),
    ),
)

PAKET_SOZLUGU: Dict[str, SektorPaketi] = {p.anahtar: p for p in SEKTOR_PAKETLERI}


def paket(anahtar: str) -> Optional[SektorPaketi]:
    return PAKET_SOZLUGU.get(anahtar)


def satilabilir_mi(m: manifest.Modul) -> bool:
    """Müşteriye ayrıca açılan (satılan) modül: görünür, çekirdek değil, herkese açık değil, yayında/beta."""
    return m.musteriye_gorunur and not m.cekirdek and not m.varsayilan_acik and m.durum != "yakinda"


def iceren_paketler(modul_anahtari: str) -> List[SektorPaketi]:
    return [p for p in SEKTOR_PAKETLERI if modul_anahtari in p.moduller]


def acilacak_moduller(anahtar: str) -> List[str]:
    """Paketi bir müşteriye açarken açılması gereken modüller (bağımlılıklar önce).

    Bağımlılıklardan herkese zaten açık olanlar (çekirdek / varsayılan açık)
    listeye girmiyor: onlara dokunmaya gerek yok.
    """
    p = paket(anahtar)
    if p is None:
        return []
    gerekli: set = set()

    def ekle(k: str) -> None:
        m = manifest.modul(k)
        if m is None or k in gerekli:
            return
        if m.cekirdek or m.varsayilan_acik:
            return
        gerekli.add(k)
        for b in m.bagimliliklar:
            ekle(b)

    for k in p.moduller:
        ekle(k)
    return [m.anahtar for m in manifest.sirali() if m.anahtar in gerekli]


def paket_hatalari() -> List[str]:
    """Paket tanımlarının iç tutarlılığı (testler çağırıyor)."""
    hatalar: List[str] = []
    anahtarlar = [p.anahtar for p in SEKTOR_PAKETLERI]
    if len(set(anahtarlar)) != len(anahtarlar):
        hatalar.append("benzersiz olmayan paket anahtarı")
    for p in SEKTOR_PAKETLERI:
        if set(p.ad_varsayilan) != {"tr", "en"}:
            hatalar.append(f"{p.anahtar}: ad_varsayilan tr/en")
        if len(p.moduller) < 2:
            hatalar.append(f"{p.anahtar}: en az iki modül")
        if len(set(p.moduller)) != len(p.moduller):
            hatalar.append(f"{p.anahtar}: modül tekrarı")
        if manifest.modul(p.anahtar) is not None:
            hatalar.append(f"{p.anahtar}: modül anahtarıyla çakışıyor")
        for k in p.moduller:
            m = manifest.modul(k)
            if m is None:
                hatalar.append(f"{p.anahtar}: bilinmeyen modül {k}")
            elif not satilabilir_mi(m):
                hatalar.append(f"{p.anahtar}: {k} müşteriye satılan bir modül değil")
    return hatalar


__all__ = [
    "SektorPaketi", "SEKTOR_PAKETLERI", "PAKET_SOZLUGU", "paket", "satilabilir_mi", "iceren_paketler",
    "acilacak_moduller", "paket_hatalari",
]
