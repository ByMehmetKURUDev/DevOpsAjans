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
    # Faz 2F — ajans yanıtı (ve kural otomatik cevabı) müşteriye yanıtlanabilir e-posta.
    "ticket_reply": {"roller": ("client",), "tetikleniyor": True},
    "project_stage": {"roller": ("admin", "client"), "tetikleniyor": True},
    "project_note": {"roller": ("client",), "tetikleniyor": True},
    "project_delivery": {"roller": ("client",), "tetikleniyor": False},
    # Faz 3T: tekrarlayan fatura ve teklif kabulündeki ilk fatura müşteriye bildiriliyor.
    "invoice": {"roller": ("client",), "tetikleniyor": True},
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
    # Faz 2C — dosyalar ve belge talebi, destek SLA, aylık rapor.
    "dosya_eklendi": {"roller": ("admin", "client"), "tetikleniyor": True},
    "belge_talebi": {"roller": ("client",), "tetikleniyor": True},
    "belge_teslim": {"roller": ("admin",), "tetikleniyor": True},
    "belge_hatirlatma": {"roller": ("client",), "tetikleniyor": True},
    "belge_gecikti": {"roller": ("admin", "client"), "tetikleniyor": True},
    "sla_yaklasiyor": {"roller": ("admin",), "tetikleniyor": True},
    "sla_asildi": {"roller": ("admin",), "tetikleniyor": True},
    "aylik_rapor": {"roller": ("client",), "tetikleniyor": True},
    "aylik_rapor_taslak": {"roller": ("admin",), "tetikleniyor": True},
    # Faz 2B — görevler, revizyon sayacı, geri bildirim, duyuru, öneri kutusu.
    "gorev_guncellendi": {"roller": ("client",), "tetikleniyor": True},
    "revizyon_asildi": {"roller": ("admin",), "tetikleniyor": True},
    "geri_bildirim_yeni": {"roller": ("admin",), "tetikleniyor": True},
    "geri_bildirim_durumu": {"roller": ("client",), "tetikleniyor": True},
    "duyuru": {"roller": ("admin", "client"), "tetikleniyor": True},
    "oneri_durumu": {"roller": ("client",), "tetikleniyor": True},
    # Faz 2D — hesaba daha önce görülmemiş bir cihaz/ağdan giriş yapıldı.
    "yeni_oturum": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 2G — karşı taraf 2 dk içinde okumadıysa (30 dk'da en çok bir, toplayarak).
    "mesaj_yeni": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 2H — müşteri sitesinin SEO/hız puanı düştü ya da yeni kritik bulgu.
    "seo_dususu": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 3B — Google bağlantısının izni geçersiz (invalid_grant): yeniden bağlanmalı.
    "baglanti_koptu": {"roller": ("admin",), "tetikleniyor": True},
    # Faz 3C — CRM: yeni aday (form / fiyat teklifi) ve günlük "sonraki adım" özeti.
    "crm_yeni_aday": {"roller": ("admin",), "tetikleniyor": True},
    "crm_hatirlatma": {"roller": ("admin",), "tetikleniyor": True},
    # Faz 3T — teklif, sözleşme + basit e-imza, vadesi geçen fatura.
    "teklif_gonderildi": {"roller": ("client",), "tetikleniyor": True},
    "teklif_karar": {"roller": ("admin",), "tetikleniyor": True},
    "sozlesme_imza_bekliyor": {"roller": ("client",), "tetikleniyor": True},
    "sozlesme_imzalandi": {"roller": ("admin", "client"), "tetikleniyor": True},
    "sozlesme_bitis": {"roller": ("admin", "client"), "tetikleniyor": True},
    "fatura_gecikti": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 4K — müşteri kartına gelen "iletişim bırak" mesajı (ajansın kendi kartı
    # CRM'e düşüyor: `crm_yeni_aday`) ve yorum sayfasının özel geri bildirimi.
    "kartvizit_mesaj": {"roller": ("client",), "tetikleniyor": True},
    "yorum_geri_bildirim": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 4M — QR menü / katalog mağazasına yeni WhatsApp siparişi (mağaza sahibine;
    # ajansın kendi mağazasında yöneticilere).
    "menu_siparis": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 4A — webhook uç noktası art arda başarısız teslimat yüzünden otomatik durduruldu.
    "webhook_pasiflesti": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 5R — randevu: yeni, yeniden planlandı, iptal (sayfa sahibine / ajans sayfasında
    # yöneticilere). Ziyaretçi e-postaları katalog dışı (`randevu_ziyaretci`: yalnız e-posta).
    "randevu_yeni": {"roller": ("admin", "client"), "tetikleniyor": True},
    "randevu_degisti": {"roller": ("admin", "client"), "tetikleniyor": True},
    "randevu_iptal": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 6E — etkinlik: yeni kayıt ve katılımcı iptali (etkinlik sahibine / ajans etkinliğinde
    # yöneticilere). Katılımcı e-postaları katalog dışı (`etkinlik_katilimci`: yalnız e-posta).
    "etkinlik_kayit": {"roller": ("admin", "client"), "tetikleniyor": True},
    "etkinlik_iptal": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 6K — eğitim: kursa yeni kayıt (kurs sahibine / ajans kursunda yöneticilere). Öğrenci/veli
    # e-postaları katalog dışı (`egitim_ogrenci`: yalnız e-posta).
    "egitim_kayit": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 6I — İK: personel portaldan izin talebi gönderdi (hesap sahibine / ajans personelinde yöneticilere).
    # Personele giden e-postalar katalog dışı (`ik_personel`: yalnız e-posta).
    "ik_izin_talebi": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 6H — hukuk bürosu: duruşma/süre hatırlatması (7/3/1 gün + aynı gün; sorumlu avukata) ve müvekkil
    # portalından mesaj (büroya; ajansın gelen kutusuna düşmez). İkisi de İÇERİKSİZ (tür + tarih).
    "hukuk_hatirlatma": {"roller": ("client",), "tetikleniyor": True},
    "hukuk_portal_mesaj": {"roller": ("client",), "tetikleniyor": True},
    # Faz 5K — ortaklık programı: yeni başvuru ve komisyon ödeme talebi (yöneticilere); başvuru kararı ve
    # ödeme yapıldı / talep geri çevrildi (ortağın kendisine — kişisel, ekip üyelerine genişlemez).
    "ortaklik_basvuru": {"roller": ("admin",), "tetikleniyor": True},
    "ortaklik_odeme_talebi": {"roller": ("admin",), "tetikleniyor": True},
    "ortaklik_durum": {"roller": ("client",), "tetikleniyor": True},
    # Faz 6T — toplantılar: davet / güncelleme (kişiye özel yanıt bağlantılı; ekip üyesine ya da dış katılımcıya),
    # iptal, 24 saat / 1 saat önce hatırlatma (katılımcıya), notların müşteriyle paylaşılması (hesaba; `projeler`
    # izinli üyelere de) ve müşterinin toplantı talebi (yöneticilere).
    "toplanti_davet": {"roller": ("admin", "client"), "tetikleniyor": True},
    "toplanti_iptal": {"roller": ("admin", "client"), "tetikleniyor": True},
    "toplanti_hatirlatma": {"roller": ("admin", "client"), "tetikleniyor": True},
    "toplanti_notlari": {"roller": ("client",), "tetikleniyor": True},
    "toplanti_talebi": {"roller": ("admin",), "tetikleniyor": True},
    # Faz 4W — otomasyon kuralının "panel bildirimi" eylemi (yöneticilere / müşteri hesabına).
    "otomasyon_bildirimi": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 5A — AI asistan ziyaretçiyi insana devretti (müşterinin asistanında hesap sahibine,
    # ajansın kendi asistanında yöneticilere).
    "asistan_devir": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 5I — içerik stüdyosu: müşteriden onay isteği (imzalı bağlantı), müşterinin kararı
    # (ajansa) ve planlanan saatten 30 dk önce "paylaşıma hazır" hatırlatması (sorumluya).
    "icerik_onay_istendi": {"roller": ("client",), "tetikleniyor": True},
    "icerik_karar": {"roller": ("admin",), "tetikleniyor": True},
    "icerik_hatirlatma": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 5B — belge paylaşıldı (ajans → müşteri; müşteri kendi belgesini ajansla paylaşınca
    # yöneticilere) ve müşteri paylaşılan belgeyi "okudum / onaylıyorum" diye işaretledi.
    "belge_paylasildi": {"roller": ("admin", "client"), "tetikleniyor": True},
    "belge_onaylandi": {"roller": ("admin",), "tetikleniyor": True},
    # Faz 5M — e-posta pazarlama gönderimleri otomatik askıya alındı (şikâyet / sert geri dönüş oranı).
    "pazarlama_askiya_alindi": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 6S — saha servisi: teknisyene yeni iş ataması (Web Push dahil) ve bakım zamanı gelen cihazlar.
    # Servis müşterisine giden e-postalar katalog dışı (`saha_musteri`: yalnız e-posta).
    "saha_is_atandi": {"roller": ("client",), "tetikleniyor": True},
    "saha_bakim_zamani": {"roller": ("client",), "tetikleniyor": True},
    # Faz 6P — stok ve POS: ürün kritik stok seviyesine indi (ürün başına tek bildirim; eşik üstüne çıkınca yeniden kurulur).
    "stok_kritik": {"roller": ("client",), "tetikleniyor": True},
    # Faz 6M — ön muhasebe: kategori bütçesi aşıldı ((kategori, ay, para birimi) başına bir kez; ajansın kendi
    # defterinde yöneticilere, müşteride hesaba).
    "muhasebe_butce": {"roller": ("admin", "client"), "tetikleniyor": True},
    # Faz 7O — Pazartesi sabahı yöneticiye haftalık özet. Bu satırın yönetici × e-posta hücresi özetin
    # açık/kapalı anahtarı (Otomasyon › Sistem kartındaki düğme de bunu değiştirir; tek kaynak).
    "haftalik_ozet": {"roller": ("admin",), "tetikleniyor": True},
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
