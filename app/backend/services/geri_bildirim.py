"""Faz 2B — hata / geri bildirim: ekran görüntüsü doğrulama ve saklama, durum bildirimi.

Ekran görüntüsü
---------------
* Yalnız görsel: PNG, JPEG, WebP, GIF. Tür, tarayıcının söylediği
  `Content-Type`a ya da dosya adına göre DEĞİL, dosyanın ilk baytlarına
  (imza) bakılarak sunucuda belirleniyor. SVG kabul edilmiyor (betik
  taşıyabilir).
* En çok 5 MB; fazlası okunmadan reddediliyor (413).
* Saklama: nesne deposu (`services/storage.py`, OSS) tanımlıysa
  (`OSS_SERVICE_URL` + `OSS_API_KEY`) oraya — sunucu önceden imzalı yükleme
  adresini alıp baytları kendisi gönderiyor, böylece doğrulanmamış bir dosya
  depoya hiç ulaşmıyor. Depo tanımlı değilse (yerel geliştirme, test) ya da
  yükleme başarısızsa veritabanında (`feedback_attachments.icerik`).
* Okuma yalnız sahibine ve yöneticiye; `X-Content-Type-Options: nosniff`.
"""

import logging
import os
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.geri_bildirim import FeedbackAttachments, FeedbackItems
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

EN_BUYUK_BOYUT = 5 * 1024 * 1024
EK_SINIRI = 3
KOVA = os.environ.get("GERI_BILDIRIM_KOVASI") or "geri-bildirim"
UZANTILAR = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
DURUM_ADLARI = {
    "yeni": ("Alındı", "Received"),
    "inceleniyor": ("İnceleniyor", "Under review"),
    "gorev": ("Göreve dönüştürüldü", "Turned into a task"),
    "cozuldu": ("Çözüldü", "Resolved"),
    "kapatildi": ("Kapatıldı", "Closed"),
}
ACIK_DURUMLAR = ("yeni", "inceleniyor")


def gorsel_turu(bayt: bytes) -> Optional[str]:
    """Dosya imzasından görsel türü; tanınmıyorsa None."""
    if len(bayt) < 12:
        return None
    if bayt[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if bayt[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if bayt[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if bayt[:4] == b"RIFF" and bayt[8:12] == b"WEBP":
        return "image/webp"
    return None


def oss_tanimli() -> bool:
    return bool(os.environ.get("OSS_SERVICE_URL") and os.environ.get("OSS_API_KEY"))


async def _oss_yukle(anahtar: str, bayt: bytes, tur: str) -> None:
    import httpx
    from schemas.storage import FileUpDownRequest
    from services.storage import StorageService

    yanit = await StorageService().create_upload_url(FileUpDownRequest(bucket_name=KOVA, object_key=anahtar))
    if not yanit.upload_url:
        raise ValueError("yükleme adresi yok")
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.put(yanit.upload_url, content=bayt, headers={"Content-Type": tur})
        r.raise_for_status()


async def _oss_oku(anahtar: str) -> bytes:
    import httpx
    from schemas.storage import FileUpDownRequest
    from services.storage import StorageService

    yanit = await StorageService().create_download_url(FileUpDownRequest(bucket_name=KOVA, object_key=anahtar))
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(yanit.download_url)
        r.raise_for_status()
        return r.content


async def ek_kaydet(
    db: AsyncSession, fb: FeedbackItems, dosya_adi: Optional[str], bayt: bytes, tur: str
) -> FeedbackAttachments:
    """Doğrulanmış görseli saklar (flush eder, commit etmez)."""
    ek = FeedbackAttachments(
        geri_bildirim_id=fb.id,
        musteri_eposta=fb.musteri_eposta,
        dosya_adi=(dosya_adi or "").strip()[:120] or None,
        icerik_turu=tur,
        boyut=len(bayt),
        depo="db",
    )
    if oss_tanimli():
        anahtar = f"geri-bildirim/{fb.id}/{uuid.uuid4().hex}.{UZANTILAR.get(tur, 'bin')}"
        try:
            await _oss_yukle(anahtar, bayt, tur)
            ek.depo = "oss"
            ek.nesne_anahtari = anahtar
        except Exception:  # noqa: BLE001 - depo erişilemiyorsa veritabanına düş
            logger.exception("Ekran görüntüsü nesne deposuna yüklenemedi; veritabanına yazılıyor")
    if ek.depo == "db":
        ek.icerik = bayt
    db.add(ek)
    await db.flush()
    return ek


async def ek_oku(ek: FeedbackAttachments) -> bytes:
    if ek.depo == "oss" and ek.nesne_anahtari:
        return await _oss_oku(ek.nesne_anahtari)
    return bytes(ek.icerik or b"")


def _iso(an: Any) -> Optional[str]:
    from services.gorevler import iso

    return iso(an)


def ek_sozlugu(ek: FeedbackAttachments) -> Dict[str, Any]:
    return {
        "id": ek.id,
        "icerik_turu": ek.icerik_turu,
        "boyut": ek.boyut,
        "dosya_adi": ek.dosya_adi,
        "adres": f"/api/v1/geri-bildirim-ek/{ek.id}",
    }


def sozluk(fb: FeedbackItems, ekler: Iterable[FeedbackAttachments] = (), *, yonetici: bool, proje_basligi: Optional[str] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": fb.id,
        "proje_id": fb.proje_id,
        "proje_basligi": proje_basligi,
        "tur": fb.tur,
        "baslik": fb.baslik,
        "aciklama": fb.aciklama,
        "sayfa_adresi": fb.sayfa_adresi,
        "durum": fb.durum,
        "ekler": [ek_sozlugu(e) for e in ekler],
        "created_at": _iso(fb.created_at),
        "updated_at": _iso(fb.updated_at),
    }
    if yonetici:
        d["musteri_eposta"] = fb.musteri_eposta
        d["tarayici"] = fb.tarayici
        d["oncelik"] = fb.oncelik
        d["gorev_id"] = fb.gorev_id
    return d


async def ekler_sozlugu(db: AsyncSession, idler: List[int]) -> Dict[int, List[FeedbackAttachments]]:
    sonuc: Dict[int, List[FeedbackAttachments]] = {}
    if not idler:
        return sonuc
    # İkili içerik yüklenmesin: yalnız üst veri sütunları.
    from sqlalchemy.orm import defer

    for e in (
        await db.execute(
            select(FeedbackAttachments)
            .options(defer(FeedbackAttachments.icerik))
            .where(FeedbackAttachments.geri_bildirim_id.in_(idler))
            .order_by(FeedbackAttachments.id)
        )
    ).scalars().all():
        sonuc.setdefault(e.geri_bildirim_id, []).append(e)
    return sonuc


async def proje_acik_geri_bildirimleri(db: AsyncSession, proje_id: int) -> List[Dict[str, Any]]:
    """Kanban'daki "Geri bildirimler" sütunu: projenin açık (yeni/inceleniyor) bildirimleri."""
    kayitlar = list(
        (
            await db.execute(
                select(FeedbackItems)
                .where(FeedbackItems.proje_id == proje_id)
                .where(FeedbackItems.durum.in_(ACIK_DURUMLAR))
                .order_by(FeedbackItems.id.desc())
                .limit(100)
            )
        ).scalars().all()
    )
    ekler = await ekler_sozlugu(db, [k.id for k in kayitlar])
    return [sozluk(k, ekler.get(k.id, []), yonetici=True) for k in kayitlar]


async def musteriye_bildir(db: AsyncSession, fb: FeedbackItems) -> None:
    """Müşteriye durum bildirimi (matris: `geri_bildirim_durumu`). Hata fırlatmaz."""
    try:
        from services.notify import dispatch, render

        tr, en = DURUM_ADLARI.get(fb.durum, (fb.durum, fb.durum))
        baslik, govde = await render(
            db,
            "geri_bildirim_durumu",
            f"Bildiriminiz: {fb.baslik} — {tr} / Your report: {en}",
            f"“{fb.baslik}” bildiriminizin durumu: {tr}.\n\nStatus of your report “{fb.baslik}”: {en}.",
            {"baslik": fb.baslik, "durum": tr},
        )
        await dispatch(
            db,
            event_type="geri_bildirim_durumu",
            title=baslik,
            body=govde,
            recipients=[{"email": fb.musteri_eposta, "role": "client"}],
            link="/client?sekme=tickets",
            ref_type="feedback",
            ref_id=fb.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Geri bildirim durum bildirimi gönderilemedi")


async def yoneticiye_bildir(db: AsyncSession, fb: FeedbackItems, proje_basligi: Optional[str]) -> None:
    try:
        from services.notify import admin_recipients, dispatch, render

        yer = f" ({proje_basligi})" if proje_basligi else ""
        baslik, govde = await render(
            db,
            "geri_bildirim_yeni",
            f"Yeni geri bildirim{yer}: {fb.baslik} / New feedback",
            f"{fb.musteri_eposta} — {fb.tur}\n{fb.aciklama or ''}\n{fb.sayfa_adresi or ''}",
            {"baslik": fb.baslik, "musteri": fb.musteri_eposta, "tur": fb.tur, "proje": proje_basligi or ""},
        )
        await dispatch(
            db,
            event_type="geri_bildirim_yeni",
            title=baslik,
            body=govde,
            recipients=await admin_recipients(db),
            link="/admin",
            ref_type="feedback",
            ref_id=fb.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Yeni geri bildirim bildirimi gönderilemedi")


async def durum_degistir(db: AsyncSession, fb_id: int, yeni: str) -> Optional[FeedbackItems]:
    """Durumu değiştirir, commit eder ve değiştiyse müşteriye bildirir."""
    fb = (await db.execute(select(FeedbackItems).where(FeedbackItems.id == fb_id))).scalar_one_or_none()
    if fb is None or fb.durum == yeni:
        return fb
    fb.durum = yeni
    await db.commit()
    await db.refresh(fb)
    await musteriye_bildir(db, fb)
    return fb


def tarayici_bilgisi(form_degeri: Optional[str], ua: Optional[str]) -> Optional[str]:
    metin = (form_degeri or "").strip() or (ua or "").strip()
    return metin[:400] or None


def sayfa_adresi_duzelt(ham: Optional[str]) -> Optional[str]:
    """Yalnız http(s) ya da site içi yol; `javascript:` gibi şemalar atılıyor."""
    d = (ham or "").strip()[:500]
    if not d:
        return None
    kucuk = d.lower()
    if kucuk.startswith(("http://", "https://")) or (d.startswith("/") and not d.startswith("//")):
        return d
    return None


def gorev_aciklamasi(fb: FeedbackItems) -> str:
    satirlar: List[str] = []
    if fb.aciklama:
        satirlar.append(fb.aciklama)
    ek: List[Tuple[str, Optional[str]]] = [
        ("Sayfa", fb.sayfa_adresi),
        ("Tarayıcı", fb.tarayici),
        ("Bildiren", fb.musteri_eposta),
        ("Geri bildirim", f"#{fb.id}"),
    ]
    satirlar.append("\n".join(f"{a}: {v}" for a, v in ek if v))
    return "\n\n".join(satirlar)[:4000]
