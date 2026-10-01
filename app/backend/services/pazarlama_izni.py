"""Faz 4G — isteğe bağlı pazarlama (ticari elektronik ileti) izni.

KVKK açısından iki ayrı şey var ve birbirine bağlanmamalı:

* **Aydınlatma** — talebi yanıtlamak için gereken işleme (KVKK m.5/2-c, f)
  rızaya dayanmıyor; ziyaretçi yalnız bilgilendiriliyor (gönder düğmesinin
  altındaki satır + /gizlilik bağlantısı). Onay kutusu YOK.
* **Açık rıza** — kampanya/duyuru e-postası göndermek bunun dışında bir amaç.
  Ayrı, isteğe bağlı, varsayılan işaretsiz bir kutuyla soruluyor; kutu
  işaretlenmese de form gönderilir. Kutu yalnız ayarı açıkken görünüyor:
  CRM formunda formun kendi `pazarlama_izni_sor` seçeneği, site analizinde
  site ayarı `SITE_ANALIZI_AYARI`.

İşaretlenirse kayda izin + zaman + gösterilen metnin sürümü yazılıyor
(`surum_etiketi`: "<METIN_SURUMU>/<dil>"). Metin değişirse METIN_SURUMU
artırılmalı; site analizi sayfasındaki ön yüz metni (`src/i18n/ek/siteAnalizi`
→ `siteAnalizi.tamRapor.pazarlama`) burada tutulan metinle AYNI olmalı —
`tests/backend/test_kvkk_riza.py` ikisini karşılaştırıyor.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

#: Metin her değiştiğinde artırılır (eski izinler hangi metne verildiğini korur).
METIN_SURUMU = "1"

#: Site analizi sayfasında kutunun görünmesi için site ayarı ("1" = sor).
SITE_ANALIZI_AYARI = "site_analizi_pazarlama_izni"

METINLER = {
    "tr": "Kampanya ve duyurulardan e-posta ile haberdar olmak istiyorum.",
    "en": "I would like to hear about campaigns and announcements by email.",
    "de": "Ich möchte per E-Mail über Aktionen und Neuigkeiten informiert werden.",
    "ru": "Я хочу получать по электронной почте информацию об акциях и новостях.",
    "zh": "我希望通过电子邮件接收优惠活动和公告。",
    "hi": "मैं अभियानों और घोषणाओं की जानकारी ईमेल से पाना चाहता/चाहती हूँ।",
    "ar": "أرغب في معرفة العروض والإعلانات عبر البريد الإلكتروني.",
}


def dil_sec(ham: Optional[str]) -> str:
    d = (ham or "").strip().lower()[:2]
    return d if d in METINLER else "tr"


def metin(dil: Optional[str]) -> str:
    return METINLER[dil_sec(dil)]


def surum_etiketi(dil: Optional[str]) -> str:
    """Kayda yazılan sürüm: hangi metin sürümü, hangi dilde gösterildi."""
    return f"{METIN_SURUMU}/{dil_sec(dil)}"


def izin_verildi_mi(ham: Any) -> bool:
    """Yalnız JSON `true` izin sayılır ("true", 1 gibi değerler sayılmaz)."""
    return ham is True


def ayar_acik_mi(deger: Optional[str]) -> bool:
    return (deger or "").strip().lower() in ("1", "true", "evet", "acik", "on")


async def site_analizi_soruyor_mu(db: AsyncSession) -> bool:
    from models.site_settings import Site_settings

    deger = (
        await db.execute(select(Site_settings.setting_value).where(Site_settings.setting_key == SITE_ANALIZI_AYARI).limit(1))
    ).scalar()
    return ayar_acik_mi(deger)


async def adaya_isle(db: AsyncSession, aday_id: Optional[int], an: datetime, kaynak: str, surum: str) -> bool:
    """Adayın pazarlama iznini (en son verilen) günceller. Commit çağırana."""
    if not aday_id:
        return False
    from models.crm import CrmAdaylari

    sonuc = await db.execute(
        update(CrmAdaylari)
        .where(CrmAdaylari.id == int(aday_id))
        .values(pazarlama_izni_at=an, pazarlama_izni_kaynak=kaynak[:80], pazarlama_metin_surumu=surum[:40])
    )
    return bool(sonuc.rowcount)


async def bagli_adayi_bul(db: AsyncSession, tablo: str, kayit_id: Optional[int]) -> Optional[int]:
    """Kaynak kaydın (ör. `inquiries`) bağlı olduğu aday — CRM kancası flush'ta bağlıyor."""
    if kayit_id is None:
        return None
    from models.crm import CrmBagliKayitlar

    return (
        await db.execute(
            select(CrmBagliKayitlar.aday_id)
            .where(CrmBagliKayitlar.tablo == tablo, CrmBagliKayitlar.kayit_id == int(kayit_id))
            .order_by(CrmBagliKayitlar.id.desc())
            .limit(1)
        )
    ).scalar()


__all__ = [
    "METIN_SURUMU", "SITE_ANALIZI_AYARI", "METINLER", "metin", "surum_etiketi", "izin_verildi_mi",
    "ayar_acik_mi", "site_analizi_soruyor_mu", "adaya_isle", "bagli_adayi_bul",
]
