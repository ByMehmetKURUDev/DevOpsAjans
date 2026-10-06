"""Zamanı geçmiş içerik gönderileri için hatırlatma e-postası.

Neden zamanlanmış iş değil
--------------------------
Sunucu ücretsiz katmanda ve hareketsizlikte uykuya geçiyor; saat başı
çalışması gereken bir iş tam saatinde çalışmıyor, bazen hiç çalışmıyor.
Sessizce çalışmayan bir hatırlatma, hiç olmamasından kötü: insan ona
güvenip bakmayı bırakıyor.

Bu yüzden hatırlatma İSTEK ÜZERİNE gönderiliyor: panelde gecikenleri
gösteren uyarının yanındaki düğme bu ucu çağırıyor, uç da yöneticiye
listeyi e-postayla yolluyor. Ne zaman gittiği belli, gitmediyse de
ekranda görünüyor.

Gövdeyi burada kuruyoruz, dil modeline sormuyoruz: liste zaten veriden
çıkıyor, uydurulacak bir şey yok.
"""

import logging
from datetime import datetime, timezone
from typing import List

from core.database import get_db
from dependencies.entity_guard import entity_guard
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Depends as _Depends
# DIKKAT: uretilmis modelin sinif adi alt cizgili: Content_posts.
from models.content_posts import Content_posts
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.notify import admin_recipients, dispatch

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/content-reminder",
    tags=["content_reminder"],
    dependencies=[_Depends(entity_guard)],
)

#: Paylaşılmış sayılan durumlar — bunlar gecikmiş olamaz.
BITMIS = {"published", "yayinlandi", "done", "reddedildi"}

KANAL_ADI = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "x": "X",
    "blog": "Blog",
    "youtube": "YouTube",
    "email": "E-posta",
}


class HatirlatmaYaniti(BaseModel):
    #: Kaç gönderinin zamanı geçmiş?
    geciken: int
    #: E-posta kanalı ne yaptı: sent | skipped | failed | off | unknown
    eposta_durumu: str = "unknown"
    eposta_ayrinti: str = ""
    #: Kaç yöneticiye gönderildi (panelde adres tanımlı mı)?
    alici_sayisi: int = 0
    #: Gönderilen metin — gitmediyse elden yollanabilsin.
    metin: str = ""


def _kanal(deger: str) -> str:
    return KANAL_ADI.get((deger or "").strip().lower(), deger or "—")


@router.post("", response_model=HatirlatmaYaniti)
async def hatirlatma_gonder(request: Request, db: AsyncSession = Depends(get_db)):
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici olmanız gerekiyor",
        )

    # Faz 5I: `scheduled_at` gönderinin saat dilimindeki YEREL saat (İçerik stüdyosu); geçti mi
    # sorusu UTC'de soruluyor. Eski kayıtlar (İngilizce durum, tek kanal) önce düzeltiliyor.
    from services import icerik_planlayici as ip

    await ip.eski_kayitlari_duzelt(db)
    simdi_utc = datetime.now(timezone.utc)
    sonuc = await db.execute(
        select(Content_posts).order_by(Content_posts.scheduled_at.asc())
    )
    gecikenler: List[Content_posts] = []
    for g in sonuc.scalars().all():
        an = ip.gonderi_utc(g) if g.scheduled_at else None
        if an and an < simdi_utc and (g.status or "").strip().lower() not in BITMIS:
            gecikenler.append(g)

    if not gecikenler:
        return HatirlatmaYaniti(geciken=0, eposta_durumu="off",
                                eposta_ayrinti="Geciken gönderi yok")

    satirlar = []
    for g in gecikenler:
        gun = (simdi_utc - ip.gonderi_utc(g)).days
        ne_zaman = g.scheduled_at.strftime("%d.%m.%Y %H:%M")
        gecikme = f"{gun} gün geçti" if gun >= 1 else "bugün"
        kanallar = ", ".join(_kanal(k) for k in ip.kanal_listesi(g)) or _kanal(g.channel)
        satirlar.append(f"- {kanallar} · {ne_zaman} ({gecikme}): {g.title}")

    govde = (
        f"{len(gecikenler)} içerik gönderisinin zamanı geçti ve hâlâ "
        "paylaşılmadı:\n\n"
        + "\n".join(satirlar)
        + "\n\nİçerik stüdyosunda gönderinin \"Paylaşıma hazır\" paketinden metni ve "
        "görselleri alıp kanalda paylaştıktan sonra \"Yayınlandı\" olarak işaretleyin."
    )
    baslik = f"{len(gecikenler)} içerik gönderisi gecikti"

    alicilar = await admin_recipients(db)
    if not alicilar:
        # Adres yoksa gönderim denenmiyor: "başarısız" demek yanlış olur,
        # ortada gönderilecek adres yok. Panelde ayarlanması gerekiyor.
        return HatirlatmaYaniti(
            geciken=len(gecikenler),
            eposta_durumu="off",
            eposta_ayrinti="Panelde yönetici e-posta adresi tanımlı değil",
            alici_sayisi=0,
            metin=govde,
        )

    kayitlar = await dispatch(
        db,
        event_type="content_overdue",
        title=baslik,
        body=govde,
        recipients=alicilar,
        link="/admin?sekme=icerik",
    )

    durum, ayrinti = "unknown", ""
    for k in kayitlar:
        if k.channel == "email":
            durum = k.delivery_status or "unknown"
            ayrinti = k.delivery_detail or ""
            break

    return HatirlatmaYaniti(
        geciken=len(gecikenler),
        eposta_durumu=durum,
        eposta_ayrinti=ayrinti,
        alici_sayisi=len(alicilar),
        metin=govde,
    )
