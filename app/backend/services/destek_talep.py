"""Faz 2F — Destek talebinin ortak akışı (panel, web, e-posta hepsi buradan).

Önceden talep açılışının SLA + yönetici bildirimi adımları entity router'ının
içindeydi, yazışma mesajı ekleme `routers/talep_mesajlari.py` içindeydi.
E-postadan gelen talep/mesaj da AYNI yoldan geçsin diye (kod tekrarı yok,
biri güncellenip diğeri unutulmasın) ikisi buraya taşındı:

* `talep_acildi(db, talep, kanal)` — talep satırı yazıldıktan sonra:
  otomatik kurallar → SLA saatleri → yönetici bildirimi → (kural
  istediyse) otomatik hazır cevap. Hiçbir adım talebi düşürmez.
* `mesaj_ekle(db, talep, ...)` — yazışmaya mesaj; durum ilerler (müşteri
  yazınca "open", ajans yazınca "answered", kapalı talep yeniden açılır).
  Ajans yazdıysa müşteriye yanıtlanabilir e-posta (`ticket_reply`).

Yanıtlanabilir e-posta
----------------------
Konu `[#T-<id>] ...`, `Reply-To` = site ayarı `destek_gelen_adres` (varsa),
kendi Message-ID'miz `<talep-<id>-<rastgele>@alan>` üretilip
`talep_eposta_kimlikleri`ne yazılıyor; müşteri "Yanıtla" deyince gelen
iletinin In-Reply-To'su bu tabloda bulunuyor. Sağlayıcı Message-ID'yi
değiştirse bile konudaki `[#T-<id>]` belirteci eşleşmeyi taşıyor.
"""

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

GELEN_ADRES_AYARI = "destek_gelen_adres"
OTOMATIK = "otomatik"


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def belirtec(talep_id: int) -> str:
    return f"[#T-{int(talep_id)}]"


def eposta_konusu(talep_id: int, konu: str) -> str:
    b = belirtec(talep_id)
    konu = (konu or "").strip()
    return konu if b in konu else f"{b} {konu}".strip()


def _alan_adi() -> str:
    gonderen = (os.environ.get("NOTIFY_FROM_EMAIL") or "").strip()
    if "@" in gonderen:
        return gonderen.rsplit("@", 1)[1].strip(" >").lower() or "mehmetkuru.dev"
    site = (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").split("//")[-1].split("/")[0]
    return site.lower() or "mehmetkuru.dev"


def message_id_uret(talep_id: int) -> str:
    return f"<talep-{int(talep_id)}-{secrets.token_hex(8)}@{_alan_adi()}>"


def _site() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


async def gelen_adres(db: AsyncSession) -> str:
    """Site ayarı `destek_gelen_adres` (gizli değil; müşteriye de gösteriliyor)."""
    from services.notify import _ayar

    adres = (await _ayar(db, GELEN_ADRES_AYARI, "")).strip()
    return adres if "@" in adres and len(adres) <= 200 else ""


# ---------------------------------------------------------------------------
# Talep açıldı
# ---------------------------------------------------------------------------
async def talep_acildi(db: AsyncSession, talep: Any, *, kanal: str, ek_not: Optional[str] = None) -> Dict[str, Any]:
    """Talep satırı yazıldıktan (commit) sonra ortak adımlar."""
    from services.destek_kurallari import talebe_uygula

    # 1) Otomatik kurallar — öncelik/atama değişirse SLA da bildirim de onu görsün.
    kural = await talebe_uygula(db, talep, kanal=kanal)

    # 2) SLA saatleri talep açıldığı anda (mesai saatine göre).
    try:
        from services.sla import talep_icin_baslat

        await talep_icin_baslat(db, talep)
    except Exception as sla_hatasi:  # noqa: BLE001 - SLA talebi düşürmesin
        logger.error("SLA başlatılamadı: %s", sla_hatasi)

    # 3) Yönetici bildirimi
    await _yoneticiye_bildir(db, talep, ek_not=ek_not)

    # 4) Otomatik hazır cevap (en çok bir kez; tanınmayana hiç)
    cevap_gitti = False
    if kural.hazir_cevap_id is not None:
        cevap_gitti = await otomatik_cevap_gonder(db, talep, kural.hazir_cevap_id)
    return {"kurallar": kural.uygulanan, "otomatik_cevap": cevap_gitti}


async def _yoneticiye_bildir(db: AsyncSession, talep: Any, ek_not: Optional[str] = None) -> None:
    from services.notify import admin_recipients, dispatch, render

    try:
        musteri = talep.client_name or talep.client_email or "—"
        oncelik = talep.priority or "normal"
        govde = f"Müşteri: {musteri}\nÖncelik: {oncelik}\n\n{talep.message}"
        if ek_not:
            govde = f"{ek_not}\n\n{govde}"
        baslik, govde = await render(
            db,
            "ticket",
            f"Yeni destek talebi: {talep.subject}",
            govde,
            {
                "musteri": musteri,
                "eposta": talep.client_email or "—",
                "konu": talep.subject,
                "oncelik": oncelik,
                "mesaj": talep.message,
            },
        )
        alicilar = await admin_recipients(db)
        atanan = (talep.atanan or "").strip().lower()
        if atanan and all((a.get("email") or "").lower() != atanan for a in alicilar):
            alicilar.append({"email": atanan, "role": "admin"})
        await dispatch(
            db, event_type="ticket", title=baslik, body=govde, recipients=alicilar,
            link="/admin", ref_type="ticket", ref_id=talep.id,
        )
    except Exception as bildirim_hatasi:  # noqa: BLE001
        logger.error("Destek bildirimi gönderilemedi: %s", bildirim_hatasi)


async def otomatik_cevap_gonder(db: AsyncSession, talep: Any, hazir_cevap_id: int) -> bool:
    """Kuralın hazır cevabını müşteriye yollar. Talep başına en çok bir kez."""
    from models.destek_sla import HazirCevaplar
    from models.support_tickets import Support_tickets
    from routers.destek import _musteri_adi, degiskenleri_doldur

    try:
        if talep.dogrulanmadi or not (talep.client_email or "").strip():
            # Tanınmayan göndericiye otomatik yanıt yok: sahte "From" ile
            # yazan birinin kurbanına bizim adımıza e-posta yağmasın.
            return False
        hc = (await db.execute(select(HazirCevaplar).where(HazirCevaplar.id == hazir_cevap_id))).scalars().first()
        if hc is None:
            return False
        sonuc = await db.execute(
            update(Support_tickets)
            .where(Support_tickets.id == talep.id, Support_tickets.otomatik_cevap_at.is_(None))
            .values(otomatik_cevap_at=simdi())
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        if int(sonuc.rowcount or 0) != 1:
            return False
        metin = degiskenleri_doldur(
            hc.metin, {"musteri_adi": _musteri_adi(talep), "talep_no": f"#{talep.id}", "konu": talep.subject}
        )
        await mesaj_ekle(db, talep, yazan=OTOMATIK, yazan_ad=None, yazan_email=None, metin=metin)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Otomatik cevap gönderilemedi: talep %s", getattr(talep, "id", None))
        return False


# ---------------------------------------------------------------------------
# Yazışma mesajı
# ---------------------------------------------------------------------------
async def mesaj_ekle(
    db: AsyncSession,
    talep: Any,
    *,
    yazan: str,
    yazan_ad: Optional[str],
    yazan_email: Optional[str],
    metin: str,
    eposta_kimligi: Optional[str] = None,
    commit: bool = True,
) -> Any:
    """Yazışmaya mesaj ekler, talebin durumunu ilerletir.

    `yazan`: musteri | ajans | otomatik. Otomatik yanıt durumu değiştirmez
    ve SLA'nın ilk yanıtı sayılmaz (SLA yalnız "ajans" satırlarına bakıyor).
    `eposta_kimligi` gelen e-postanın Message-ID'si (zincir eşleşmesi için).
    `commit=False` ise yalnız flush — çağıran kendi işlemini bitirir ve
    ardından `mesaj_eklendi_sonrasi`nı çağırır.
    """
    from models.destek_eposta import TalepEpostaKimlikleri
    from models.ticket_replies import Ticket_replies

    kayit = Ticket_replies(
        ticket_id=talep.id,
        yazan=yazan,
        yazan_ad=yazan_ad,
        yazan_email=yazan_email or None,
        mesaj=metin,
    )
    db.add(kayit)
    talep.son_mesaj_at = datetime.now()
    # Durum, kimin yazdığına göre ilerliyor: müşteri yazınca top bizde, biz
    # yazınca müşteride. Kapanmış talep müşteri yazınca yeniden açılıyor.
    if yazan == "musteri":
        talep.status = "open"
    elif yazan == "ajans":
        talep.status = "answered"
    await db.flush()
    if eposta_kimligi:
        db.add(TalepEpostaKimlikleri(message_id=eposta_kimligi[:300], ticket_id=talep.id, reply_id=kayit.id, yon="gelen"))
        await db.flush()
    if not commit:
        return kayit
    await db.commit()
    await db.refresh(kayit)
    await mesaj_eklendi_sonrasi(db, talep, kayit)
    return kayit


async def mesaj_eklendi_sonrasi(db: AsyncSession, talep: Any, kayit: Any) -> None:
    if kayit.yazan in ("ajans", OTOMATIK):
        await yanit_epostasi_gonder(db, talep, kayit)


async def _zincir(db: AsyncSession, talep_id: int) -> List[str]:
    from models.destek_eposta import TalepEpostaKimlikleri

    satirlar = (
        await db.execute(
            select(TalepEpostaKimlikleri.message_id)
            .where(TalepEpostaKimlikleri.ticket_id == talep_id)
            .order_by(TalepEpostaKimlikleri.id.desc())
            .limit(10)
        )
    ).scalars().all()
    return list(reversed(satirlar))


async def _son_gelen(db: AsyncSession, talep_id: int) -> Optional[str]:
    from models.destek_eposta import TalepEpostaKimlikleri

    return (
        await db.execute(
            select(TalepEpostaKimlikleri.message_id)
            .where(TalepEpostaKimlikleri.ticket_id == talep_id, TalepEpostaKimlikleri.yon == "gelen")
            .order_by(TalepEpostaKimlikleri.id.desc())
            .limit(1)
        )
    ).scalars().first()


async def yanit_epostasi_gonder(db: AsyncSession, talep: Any, kayit: Any) -> None:
    """Ajans/otomatik yanıtı müşteriye bildirir (panel içi + e-posta …). Hata fırlatmaz."""
    from models.destek_eposta import TalepEpostaKimlikleri
    from services.notify import dispatch, render

    try:
        alici = (talep.client_email or "").strip().lower()
        if not alici or "@" not in alici:
            return
        adres = await gelen_adres(db)
        mid = message_id_uret(talep.id)
        zincir = await _zincir(db, talep.id)
        son_gelen = await _son_gelen(db, talep.id)
        db.add(TalepEpostaKimlikleri(message_id=mid, ticket_id=talep.id, reply_id=kayit.id, yon="giden"))
        await db.commit()

        alt = [f"Talep #{talep.id}: {talep.subject}"]
        if adres:
            alt.append("Bu e-postayı yanıtlayarak talebinize yazabilirsiniz.")
        alt.append(f"{_site()}/client?sekme=tickets")
        varsayilan_govde = f"{kayit.mesaj}\n\n—\n" + "\n".join(alt)
        baslik, govde = await render(
            db,
            "ticket_reply",
            f"Destek talebinize yanıt: {talep.subject}",
            varsayilan_govde,
            {"konu": talep.subject, "mesaj": kayit.mesaj, "talep_no": f"#{talep.id}"},
        )
        # Panelden şablon değiştirilse de belirteç kaybolmasın: e-posta
        # yanıtının hangi talebe ait olduğunu o taşıyor.
        baslik = eposta_konusu(talep.id, baslik)
        basliklar: Dict[str, str] = {"Message-ID": mid}
        if son_gelen:
            basliklar["In-Reply-To"] = son_gelen
        if zincir:
            basliklar["References"] = " ".join(zincir)
        # Otomatik yanıtın döngüye girmemesi için karşı tarafa işaret.
        if kayit.yazan == OTOMATIK:
            basliklar["Auto-Submitted"] = "auto-replied"
        await dispatch(
            db,
            event_type="ticket_reply",
            title=baslik,
            body=govde,
            recipients=[{"email": alici, "role": "client"}],
            link="/client?sekme=tickets",
            ref_type="ticket",
            ref_id=talep.id,
            eposta_ek={"basliklar": basliklar, "reply_to": adres or None},
        )
    except Exception:  # noqa: BLE001
        logger.exception("Talep yanıt e-postası gönderilemedi: talep %s", getattr(talep, "id", None))
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
