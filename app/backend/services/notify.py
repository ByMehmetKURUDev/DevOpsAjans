"""
Bildirim dağıtıcısı.

Tek giriş noktası: `dispatch(...)`. Olayın kime gideceğini, hangi
kanalların açık olduğunu ve her kanalın nasıl gönderileceğini burası bilir;
çağıran taraf (router) yalnızca "şu oldu" der.

KANALLAR
--------
inapp     her zaman açık, dışarıya bağımlılığı yok
email     RESEND_API_KEY ya da SMTP_* ayarlıysa
sms       SMS_PROVIDER + kimlik bilgileri ayarlıysa (Netgsm / Twilio)
whatsapp  WHATSAPP_TOKEN + WHATSAPP_PHONE_ID ayarlıysa (Meta Cloud API)

Kimlik bilgisi olmayan kanal SESSİZCE ATLANMIYOR: veritabanına
`delivery_status="skipped"` ve sebebiyle yazılıyor. Panelde "SMS neden
gitmedi" sorusunun cevabı böylece kayıtlı oluyor.

Gönderim hatası hiçbir zaman çağıran işlemi düşürmez: iletişim formunu
dolduran ziyaretçi, SMS sağlayıcısı çöktü diye hata görmemeli.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import httpx
from models.notifications import Notifications
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ZAMAN_ASIMI = 10.0


def _env(*adlar: str) -> Optional[str]:
    """İlk dolu ortam değişkenini döndürür."""
    for ad in adlar:
        deger = os.environ.get(ad)
        if deger and deger.strip():
            return deger.strip()
    return None


async def _ayar(db: AsyncSession, anahtar: str, varsayilan: str = "") -> str:
    """
    site_settings'ten bir değer okur.

    Kanalların açık/kapalı olması panelden yönetiliyor; kimlik bilgileri
    ise ortam değişkeninde. Bu ayrım bilinçli: anahtarlar veritabanında
    düz metin durmamalı.
    """
    try:
        from models.site_settings import Site_settings

        sonuc = await db.execute(
            select(Site_settings).where(Site_settings.setting_key == anahtar)
        )
        satir = sonuc.scalar_one_or_none()
        if satir and satir.setting_value is not None:
            return str(satir.setting_value)
    except Exception as hata:  # tablo yoksa ya da şema farklıysa
        logger.debug("Ayar okunamadı (%s): %s", anahtar, hata)
    return varsayilan


def _acik(deger: str) -> bool:
    return str(deger).strip().lower() in {"1", "true", "evet", "on", "yes"}


# --------------------------------------------------------------------------
# Kanal gönderimleri
# --------------------------------------------------------------------------


async def _eposta_gonder(alici: str, baslik: str, govde: str) -> tuple[str, str]:
    """(durum, ayrıntı) döndürür."""
    resend = _env("RESEND_API_KEY")
    gonderen = _env("NOTIFY_FROM_EMAIL") or "bildirim@mehmetkuru.dev"

    if resend:
        try:
            async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
                yanit = await istemci.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend}"},
                    json={
                        "from": gonderen,
                        "to": [alici],
                        "subject": baslik,
                        "text": govde,
                    },
                )
            if yanit.status_code < 300:
                return "sent", "resend"
            return "failed", f"resend {yanit.status_code}: {yanit.text[:200]}"
        except Exception as hata:
            return "failed", f"resend: {hata}"

    sunucu = _env("SMTP_HOST")
    if sunucu:
        # SMTP eşzamanlı bir kütüphane; olay döngüsünü kilitlememek için
        # ayrı bir iş parçacığına veriliyor.
        import asyncio
        import smtplib
        from email.message import EmailMessage

        def _gonder() -> tuple[str, str]:
            try:
                mesaj = EmailMessage()
                mesaj["From"] = gonderen
                mesaj["To"] = alici
                mesaj["Subject"] = baslik
                mesaj.set_content(govde)
                port = int(_env("SMTP_PORT") or 587)
                with smtplib.SMTP(sunucu, port, timeout=ZAMAN_ASIMI) as baglanti:
                    baglanti.starttls()
                    kullanici = _env("SMTP_USER")
                    parola = _env("SMTP_PASSWORD")
                    if kullanici and parola:
                        baglanti.login(kullanici, parola)
                    baglanti.send_message(mesaj)
                return "sent", "smtp"
            except Exception as hata:
                return "failed", f"smtp: {hata}"

        return await asyncio.to_thread(_gonder)

    return "skipped", "RESEND_API_KEY ya da SMTP_HOST tanımlı değil"


async def _sms_gonder(numara: str, metin: str) -> tuple[str, str]:
    saglayici = (_env("SMS_PROVIDER") or "").lower()

    if saglayici == "netgsm":
        kullanici = _env("NETGSM_USER")
        parola = _env("NETGSM_PASSWORD")
        baslik = _env("NETGSM_HEADER")
        if not (kullanici and parola and baslik):
            return "skipped", "NETGSM_USER / NETGSM_PASSWORD / NETGSM_HEADER eksik"
        try:
            async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
                yanit = await istemci.get(
                    "https://api.netgsm.com.tr/sms/send/get",
                    params={
                        "usercode": kullanici,
                        "password": parola,
                        "gsmno": numara,
                        "message": metin,
                        "msgheader": baslik,
                    },
                )
            # Netgsm 00/01/02 ile başlayan yanıtı başarı sayıyor.
            govde = yanit.text.strip()
            if govde.split()[0] in {"00", "01", "02"}:
                return "sent", f"netgsm: {govde}"
            return "failed", f"netgsm: {govde[:200]}"
        except Exception as hata:
            return "failed", f"netgsm: {hata}"

    if saglayici == "twilio":
        sid = _env("TWILIO_ACCOUNT_SID")
        token = _env("TWILIO_AUTH_TOKEN")
        gonderen = _env("TWILIO_FROM_NUMBER")
        if not (sid and token and gonderen):
            return "skipped", "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER eksik"
        try:
            async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
                yanit = await istemci.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, token),
                    data={"To": numara, "From": gonderen, "Body": metin},
                )
            if yanit.status_code < 300:
                return "sent", "twilio"
            return "failed", f"twilio {yanit.status_code}: {yanit.text[:200]}"
        except Exception as hata:
            return "failed", f"twilio: {hata}"

    return "skipped", "SMS_PROVIDER tanımlı değil (netgsm ya da twilio)"


async def _whatsapp_gonder(numara: str, sablon: str, degiskenler: List[str]) -> tuple[str, str]:
    """
    Meta Cloud API.

    Not: WhatsApp Business API'de serbest metin yalnızca müşteri son 24
    saatte yazdıysa gönderilebiliyor. Bildirimler için ONAYLI ŞABLON
    zorunlu; şablon adı `WHATSAPP_TEMPLATE` ile veriliyor.
    """
    token = _env("WHATSAPP_TOKEN")
    telefon_id = _env("WHATSAPP_PHONE_ID")
    if not (token and telefon_id):
        return "skipped", "WHATSAPP_TOKEN / WHATSAPP_PHONE_ID eksik"
    if not sablon:
        return "skipped", "WHATSAPP_TEMPLATE tanımlı değil (Meta onaylı şablon adı)"

    dil = _env("WHATSAPP_TEMPLATE_LANG") or "tr"
    try:
        async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
            yanit = await istemci.post(
                f"https://graph.facebook.com/v21.0/{telefon_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": numara,
                    "type": "template",
                    "template": {
                        "name": sablon,
                        "language": {"code": dil},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": d} for d in degiskenler
                                ],
                            }
                        ],
                    },
                },
            )
        if yanit.status_code < 300:
            return "sent", "whatsapp"
        return "failed", f"whatsapp {yanit.status_code}: {yanit.text[:200]}"
    except Exception as hata:
        return "failed", f"whatsapp: {hata}"


# --------------------------------------------------------------------------
# Giriş noktası
# --------------------------------------------------------------------------


async def dispatch(
    db: AsyncSession,
    *,
    event_type: str,
    title: str,
    body: str = "",
    recipients: Iterable[Dict[str, Any]],
    link: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
) -> List[Notifications]:
    """
    Bir olayı açık kanallardan dağıtır ve her kanal için kayıt yazar.

    `recipients`: [{"email": ..., "role": "admin"|"client", "phone": ...}]
    Telefon yoksa SMS ve WhatsApp o kişi için atlanır.

    Dönen liste yazılan bildirim satırları. Hata fırlatmaz.
    """
    yazilanlar: List[Notifications] = []

    eposta_acik = _acik(await _ayar(db, "notify_email", "1"))
    sms_acik = _acik(await _ayar(db, "notify_sms", "0"))
    whatsapp_acik = _acik(await _ayar(db, "notify_whatsapp", "0"))
    wa_sablon = await _ayar(db, "whatsapp_template", _env("WHATSAPP_TEMPLATE") or "")

    for alici in recipients:
        eposta = (alici.get("email") or "").strip()
        if not eposta:
            continue
        rol = alici.get("role") or "client"
        telefon = (alici.get("phone") or "").strip()

        # 1) Panel içi — her zaman.
        yazilanlar.append(
            Notifications(
                recipient_email=eposta,
                recipient_role=rol,
                event_type=event_type,
                title=title,
                body=body,
                link=link,
                channel="inapp",
                delivery_status="sent",
                ref_type=ref_type,
                ref_id=ref_id,
                created_at=datetime.now(),
            )
        )

        # 2) E-posta
        if eposta_acik:
            durum, ayrinti = await _eposta_gonder(eposta, title, body or title)
            yazilanlar.append(
                Notifications(
                    recipient_email=eposta,
                    recipient_role=rol,
                    event_type=event_type,
                    title=title,
                    body=body,
                    link=link,
                    channel="email",
                    delivery_status=durum,
                    delivery_detail=ayrinti,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    created_at=datetime.now(),
                )
            )

        # 3) SMS ve WhatsApp — telefon numarası şart.
        if sms_acik:
            if telefon:
                durum, ayrinti = await _sms_gonder(telefon, f"{title}\n{body}"[:300])
            else:
                durum, ayrinti = "skipped", "alıcının telefon numarası yok"
            yazilanlar.append(
                Notifications(
                    recipient_email=eposta,
                    recipient_role=rol,
                    event_type=event_type,
                    title=title,
                    body=body,
                    link=link,
                    channel="sms",
                    delivery_status=durum,
                    delivery_detail=ayrinti,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    created_at=datetime.now(),
                )
            )

        if whatsapp_acik:
            if telefon:
                durum, ayrinti = await _whatsapp_gonder(telefon, wa_sablon, [title, body or ""])
            else:
                durum, ayrinti = "skipped", "alıcının telefon numarası yok"
            yazilanlar.append(
                Notifications(
                    recipient_email=eposta,
                    recipient_role=rol,
                    event_type=event_type,
                    title=title,
                    body=body,
                    link=link,
                    channel="whatsapp",
                    delivery_status=durum,
                    delivery_detail=ayrinti,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    created_at=datetime.now(),
                )
            )

    if not yazilanlar:
        return []

    try:
        db.add_all(yazilanlar)
        await db.commit()
    except Exception as hata:
        # Bildirim kaydı yazılamazsa asıl işlem yine de tamamlanmalı.
        logger.error("Bildirim kaydı yazılamadı: %s", hata)
        await db.rollback()
        return []

    return yazilanlar


async def admin_recipients(db: AsyncSession) -> List[Dict[str, Any]]:
    """
    Yöneticiler.

    Adresler panelde `admin_emails` altında virgülle ayrılmış duruyor;
    telefon `notify_admin_phone` içinde. Panelde hiç adres yoksa
    NOTIFY_ADMIN_EMAIL ortam değişkenine düşülür.
    """
    ham = await _ayar(db, "admin_emails", "")
    telefon = await _ayar(db, "notify_admin_phone", "") or (_env("NOTIFY_ADMIN_PHONE") or "")
    adresler = [p.strip() for p in ham.replace(";", ",").split(",") if p.strip()]
    if not adresler:
        yedek = _env("NOTIFY_ADMIN_EMAIL")
        if yedek:
            adresler = [yedek]
    return [{"email": e, "role": "admin", "phone": telefon} for e in adresler]


__all__ = ["dispatch", "admin_recipients"]
