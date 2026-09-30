"""
Bildirim tercihleri: olay × kanal matrisi ve kişisel tercih.

KURAL (üç katman, hepsi "evet" demeli)
-------------------------------------
1. Kanalın kendisi açık mı? — e-posta/SMS/WhatsApp için panelin mevcut ana
   anahtarları (`notify_email`, `notify_sms`, `notify_whatsapp`). Push'un
   ana anahtarı yok; VAPID anahtarları tanımlı değilse satır `skipped`.
2. Yönetici matrisi o olay × kanala izin veriyor mu? — site_settings
   `bildirim_matrisi`, alıcı rolüne göre (admin / client) ayrı tablo.
3. Kişi kapatmış mı? — `notification_prefs.tercih_json`. Kişi yalnız
   kapatabilir: matris "hayır" diyorsa kişinin "evet"i bir şey değiştirmez.

Panel içi (inapp) her zaman açık; ne matriste ne kişisel tercihte
kapatılabiliyor. Çan, "ne oldu?" sorusunun tek güvenilir cevabı.

Katalogda olmayan olaylar (davet e-postası, test) matrise tabi değil:
eski davranış sürüyor (ana anahtarlar), push gönderilmiyor.
"""

import json
import logging
import os
from datetime import datetime, time, timezone
from typing import Any, Dict, Iterable, List, Optional

from models.bildirim import NotificationPrefs
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MATRIS_ANAHTARI = "bildirim_matrisi"

KANALLAR = ("inapp", "email", "push", "sms", "whatsapp")
#: Sessiz saatlerde gönderilmeyen, anlık dikkat isteyen kanallar.
ANLIK_KANALLAR = frozenset({"push", "sms", "whatsapp"})
ROLLER = ("admin", "client")

#: Olay kataloğu: olay → hangi roldeki alıcıya gidiyor. Arayüz yalnız ilgili
#: satırları gösteriyor; matris yine de iki rol için de tutuluyor.
#: `tetikleniyor=False` olanlar için matris hazır, henüz dağıtan kod yok.
OLAYLAR: Dict[str, Dict[str, Any]] = {
    "inquiry": {"roller": ("admin",), "tetikleniyor": True},
    "ticket": {"roller": ("admin",), "tetikleniyor": True},
    "ticket_reply": {"roller": ("client",), "tetikleniyor": False},
    "project_stage": {"roller": ("admin", "client"), "tetikleniyor": True},
    "project_note": {"roller": ("client",), "tetikleniyor": True},
    "project_delivery": {"roller": ("client",), "tetikleniyor": False},
    "invoice": {"roller": ("client",), "tetikleniyor": False},
    "invoice_paid": {"roller": ("admin", "client"), "tetikleniyor": False},
    "kredi_yuklendi": {"roller": ("client",), "tetikleniyor": True},
    "kredi_azaldi": {"roller": ("admin", "client"), "tetikleniyor": True},
    "site_analizi_rapor": {"roller": ("client",), "tetikleniyor": True},
    "site_analizi_aday": {"roller": ("admin",), "tetikleniyor": True},
    "bekleme_listesi": {"roller": ("admin", "client"), "tetikleniyor": False},
    "content_overdue": {"roller": ("admin",), "tetikleniyor": True},
    # Faz 1F — yönetici müşteride bir modülü açtı/kapattı.
    "modul_acildi": {"roller": ("client",), "tetikleniyor": True},
    "modul_kapandi": {"roller": ("client",), "tetikleniyor": True},
    # Faz 2A — site bakımı: uptime kesintisi, bitiş hatırlatması, yenileme faturası.
    "site_coktu": {"roller": ("admin", "client"), "tetikleniyor": True},
    "site_duzeldi": {"roller": ("admin", "client"), "tetikleniyor": True},
    "bitis_yaklasiyor": {"roller": ("admin", "client"), "tetikleniyor": True},
    "yenileme_faturasi": {"roller": ("client",), "tetikleniyor": True},
}


def _varsayilan_hucre() -> Dict[str, bool]:
    # Önceki davranış korunuyor: ana anahtarı açık kanal her olaya gidiyordu.
    return {k: True for k in KANALLAR}


def varsayilan_matris() -> Dict[str, Dict[str, Dict[str, bool]]]:
    return {rol: {olay: _varsayilan_hucre() for olay in OLAYLAR} for rol in ROLLER}


def _bool(deger: Any, varsayilan: bool) -> bool:
    if isinstance(deger, bool):
        return deger
    return varsayilan


def matrisi_duzelt(ham: Any) -> Dict[str, Dict[str, Dict[str, bool]]]:
    """Kaydedilmiş (ya da gönderilmiş) matrisi varsayılanla birleştirir.

    Bilinmeyen rol/olay/kanal atılıyor, eksik hücre varsayılanı alıyor,
    inapp her zaman `True`. Yeni bir olay kataloğa eklendiğinde eski kayıt
    bozulmadan onu da kapsıyor.
    """
    sonuc = varsayilan_matris()
    if not isinstance(ham, dict):
        return sonuc
    for rol in ROLLER:
        rol_ham = ham.get(rol)
        if not isinstance(rol_ham, dict):
            continue
        for olay in OLAYLAR:
            hucre = rol_ham.get(olay)
            if not isinstance(hucre, dict):
                continue
            for kanal in KANALLAR:
                sonuc[rol][olay][kanal] = _bool(hucre.get(kanal), sonuc[rol][olay][kanal])
            sonuc[rol][olay]["inapp"] = True
    return sonuc


async def _ayar_satiri(db: AsyncSession, anahtar: str):
    from models.site_settings import Site_settings

    sonuc = await db.execute(select(Site_settings).where(Site_settings.setting_key == anahtar))
    return sonuc.scalars().first()


async def matris_oku(db: AsyncSession) -> Dict[str, Dict[str, Dict[str, bool]]]:
    try:
        satir = await _ayar_satiri(db, MATRIS_ANAHTARI)
        if satir and satir.setting_value:
            return matrisi_duzelt(json.loads(satir.setting_value))
    except Exception as hata:  # bozuk JSON ya da tablo yok: varsayılan
        logger.warning("Bildirim matrisi okunamadı: %s", hata)
    return varsayilan_matris()


async def matris_yaz(db: AsyncSession, ham: Any) -> Dict[str, Dict[str, Dict[str, bool]]]:
    from models.site_settings import Site_settings

    temiz = matrisi_duzelt(ham)
    metin = json.dumps(temiz, ensure_ascii=False, separators=(",", ":"))
    satir = await _ayar_satiri(db, MATRIS_ANAHTARI)
    if satir:
        satir.setting_value = metin
    else:
        db.add(
            Site_settings(
                setting_key=MATRIS_ANAHTARI,
                setting_value=metin,
                group_name="notify",
                label="Bildirim olay × kanal matrisi",
            )
        )
    await db.commit()
    return temiz


# --------------------------------------------------------------------------
# Kişisel tercih
# --------------------------------------------------------------------------


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def tercihi_duzelt(ham: Any) -> Dict[str, Dict[str, bool]]:
    """Yalnız katalogdaki olaylar ve inapp dışındaki kanallar kalır."""
    sonuc: Dict[str, Dict[str, bool]] = {}
    if not isinstance(ham, dict):
        return sonuc
    for olay, hucre in ham.items():
        if olay not in OLAYLAR or not isinstance(hucre, dict):
            continue
        temiz = {k: v for k, v in hucre.items() if k in KANALLAR and k != "inapp" and isinstance(v, bool)}
        if temiz:
            sonuc[olay] = temiz
    return sonuc


def _saat(metin: Any) -> Optional[time]:
    try:
        saat, dakika = str(metin).strip().split(":")
        return time(int(saat), int(dakika))
    except Exception:
        return None


def sessiz_duzelt(ham: Any) -> Optional[Dict[str, str]]:
    if not isinstance(ham, dict):
        return None
    bas, bit = _saat(ham.get("bas")), _saat(ham.get("bit"))
    if bas is None or bit is None or bas == bit:
        return None
    return {"bas": bas.strftime("%H:%M"), "bit": bit.strftime("%H:%M")}


def _yerel_saat() -> time:
    ad = os.environ.get("BILDIRIM_SAAT_DILIMI") or "Europe/Istanbul"
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(ad)).time()
    except Exception:
        from datetime import timedelta

        return (datetime.now(timezone.utc) + timedelta(hours=3)).time()


def sessiz_saatte_mi(sessiz: Optional[Dict[str, str]], simdi: Optional[time] = None) -> bool:
    """Gece yarısını aşan aralık (22:00–08:00) da destekleniyor."""
    if not sessiz:
        return False
    bas, bit = _saat(sessiz.get("bas")), _saat(sessiz.get("bit"))
    if bas is None or bit is None:
        return False
    an = simdi or _yerel_saat()
    if bas < bit:
        return bas <= an < bit
    return an >= bas or an < bit


class KisiTercihi:
    __slots__ = ("tercih", "sessiz")

    def __init__(self, tercih: Optional[Dict[str, Dict[str, bool]]] = None, sessiz: Optional[Dict[str, str]] = None):
        self.tercih = tercih or {}
        self.sessiz = sessiz


def _satirdan(satir: Optional[NotificationPrefs]) -> KisiTercihi:
    if satir is None:
        return KisiTercihi()
    try:
        tercih = tercihi_duzelt(json.loads(satir.tercih_json or "{}"))
    except Exception:
        tercih = {}
    try:
        sessiz = sessiz_duzelt(json.loads(satir.sessiz_saatler)) if satir.sessiz_saatler else None
    except Exception:
        sessiz = None
    return KisiTercihi(tercih, sessiz)


async def tercih_oku(db: AsyncSession, eposta: str) -> KisiTercihi:
    sonuc = await db.execute(select(NotificationPrefs).where(NotificationPrefs.eposta == eposta_duzelt(eposta)))
    return _satirdan(sonuc.scalars().first())


async def tercihleri_oku(db: AsyncSession, epostalar: Iterable[str]) -> Dict[str, KisiTercihi]:
    """Birden çok alıcının tercihi tek sorguda."""
    adresler = sorted({eposta_duzelt(e) for e in epostalar if e})
    if not adresler:
        return {}
    try:
        sonuc = await db.execute(select(NotificationPrefs).where(func.lower(NotificationPrefs.eposta).in_(adresler)))
        return {eposta_duzelt(s.eposta): _satirdan(s) for s in sonuc.scalars().all()}
    except Exception as hata:
        logger.warning("Bildirim tercihleri okunamadı: %s", hata)
        return {}


async def tercih_yaz(
    db: AsyncSession, eposta: str, tercih: Any, sessiz: Any
) -> KisiTercihi:
    eposta = eposta_duzelt(eposta)
    temiz = tercihi_duzelt(tercih)
    sessiz_temiz = sessiz_duzelt(sessiz)
    sonuc = await db.execute(select(NotificationPrefs).where(NotificationPrefs.eposta == eposta))
    satir = sonuc.scalars().first()
    if satir is None:
        satir = NotificationPrefs(eposta=eposta)
        db.add(satir)
    satir.tercih_json = json.dumps(temiz, ensure_ascii=False, separators=(",", ":"))
    satir.sessiz_saatler = json.dumps(sessiz_temiz) if sessiz_temiz else None
    await db.commit()
    return KisiTercihi(temiz, sessiz_temiz)


# --------------------------------------------------------------------------
# Karar
# --------------------------------------------------------------------------


def rol_duzelt(rol: Optional[str]) -> str:
    return "admin" if rol == "admin" else "client"


def izinli_mi(
    matris: Dict[str, Dict[str, Dict[str, bool]]],
    kisi: Optional[KisiTercihi],
    rol: Optional[str],
    olay: str,
    kanal: str,
) -> bool:
    """Matris × kişisel tercih. Ana anahtar ve yapılandırma burada değil."""
    if kanal == "inapp":
        return True
    if olay not in OLAYLAR:
        # Katalog dışı olay: eski davranış, push yok.
        return kanal != "push"
    if not matris.get(rol_duzelt(rol), {}).get(olay, {}).get(kanal, True):
        return False
    if kisi is not None and kisi.tercih.get(olay, {}).get(kanal) is False:
        return False
    return True


# --------------------------------------------------------------------------
# Kanal durumu (arayüz için)
# --------------------------------------------------------------------------


def _env_var(*adlar: str) -> bool:
    return all((os.environ.get(a) or "").strip() for a in adlar)


def kanal_yapilandirildi(kanal: str) -> bool:
    if kanal == "inapp":
        return True
    if kanal == "email":
        return _env_var("RESEND_API_KEY") or _env_var("SMTP_HOST")
    if kanal == "sms":
        return (os.environ.get("SMS_PROVIDER") or "").strip().lower() in {"netgsm", "twilio"}
    if kanal == "whatsapp":
        return _env_var("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID")
    if kanal == "push":
        from services.web_push import push_yapilandirildi

        return push_yapilandirildi()
    return False


ANA_ANAHTARLAR = {"email": ("notify_email", "1"), "sms": ("notify_sms", "0"), "whatsapp": ("notify_whatsapp", "0")}


async def kanal_durumlari(db: AsyncSession) -> Dict[str, str]:
    """{kanal: "hazir" | "kapali" | "yapilandirilmadi"}.

    `yapilandirilmadi`: sunucuda kimlik bilgisi yok (ortam değişkeni).
    `kapali`: bilgi var ama yönetici panelde kanalı kapatmış.
    """
    from services.notify import _acik, _ayar

    durum: Dict[str, str] = {}
    for kanal in KANALLAR:
        if not kanal_yapilandirildi(kanal):
            durum[kanal] = "yapilandirilmadi"
            continue
        anahtar = ANA_ANAHTARLAR.get(kanal)
        if anahtar and not _acik(await _ayar(db, anahtar[0], anahtar[1])):
            durum[kanal] = "kapali"
            continue
        durum[kanal] = "hazir"
    return durum


def olay_listesi(rol: Optional[str] = None) -> List[str]:
    if rol is None:
        return list(OLAYLAR)
    r = rol_duzelt(rol)
    return [o for o, bilgi in OLAYLAR.items() if r in bilgi["roller"]]
