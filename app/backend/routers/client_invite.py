"""
Müşteriyi panele davet eder.

Yönetici bir talebi projeye çevirdiğinde müşterinin panele kaydolması
gerekiyor; panel kayıtları `client_email` üzerinden eşleştiriyor.

Buradaki asıl mesele e-postanın AYNI olması. Müşteri kendi başına
kaydolurken farklı bir adres yazarsa panelinde hiçbir şey görünmüyor ve
bunun sebebini kimse anlamıyor — kayıt da proje de duruyor, sadece
eşleşmiyorlar.

Kayıt bu sitede değil, kimlik sağlayıcıda yapılıyor (`auth.toLogin()`
parametre almıyor), yani adresi forma önceden yazdıramıyoruz. Elimizdeki
tek koruma, adresi davet metninde açıkça söylemek — o yüzden e-posta
gövdesinde tam olarak yazıyor. İkinci koruma müşteri panelinde: eşleşme
olmayınca boş ekran yerine sebebini söyleyen bir uyarı çıkıyor.

Uç yalnızca yöneticiye açık: davet e-postası, adresin projeyle ilişkili
olduğunu ima ediyor; herkese açık olsaydı istenmeyen posta aracına
dönerdi.
"""

import logging
from typing import Optional

from core.database import get_db
from dependencies.entity_guard import entity_guard
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Depends as _Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from services.notify import dispatch, render

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/client-invite",
    tags=["client_invite"],
    dependencies=[_Depends(entity_guard)],
)


class InviteRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = ""
    project_title: Optional[str] = ""


class InviteResponse(BaseModel):
    ok: bool
    link: str
    # E-posta gerçekten gitti mi? "sent" | "skipped" | "failed" | "off"
    # Panel bunu görünce gerekirse daveti elden göndermeyi öneriyor;
    # eskiden uç her hâlükârda ok:true dönüyordu ve e-posta altyapısı
    # kurulu değilse davet sessizce kayboluyordu.
    email_status: str = "unknown"
    email_detail: str = ""
    # Panelin kopyalayıp WhatsApp'tan gönderebilmesi için metnin kendisi.
    subject: str = ""
    message: str = ""


@router.post("", response_model=InviteResponse)
async def invite_client(
    payload: InviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici olmanız gerekiyor",
        )

    eposta = str(payload.email).strip().lower()
    yol = "/client"

    ad = payload.name or eposta
    proje = payload.project_title or "Projeniz"

    # DİKKAT: varsayılan gövdenin yer tutucuları BURADA doldurulmalı.
    # `render` yalnızca panelde yazılmış şablona `{{anahtar}}` değişimi
    # uyguluyor; varsayılan metni olduğu gibi döndürüyor. Bu metin daha
    # önce "{ad}" ve "{eposta}" gibi tek süslü yer tutucularla yazılmıştı
    # ve hiçbir yerde doldurulmuyordu -- davet "Kaydolurken şu adresi
    # kullanın: {eposta}" diyerek gidiyordu. Davetin tek işi o adresi
    # söylemek olduğu için hata sessiz değil, ölümcüldü.
    varsayilan_govde = (
        f"Merhaba {ad},\n\n"
        f"{proje} için proje kaydınız açıldı. Aşamaları takip etmek, "
        "dosyalara ulaşmak ve soru sormak için panelinize kaydolabilirsiniz.\n\n"
        "ÖNEMLİ: Kaydolurken şu e-posta adresini kullanın:\n"
        f"{eposta}\n\n"
        "Projeniz bu adrese bağlı. Başka bir adresle kaydolursanız "
        "panelinizde projeyi göremezsiniz."
    )

    baslik, govde = await render(
        db,
        "client_invite",
        f"{proje} için proje kaydınız açıldı",
        varsayilan_govde,
        # Panelde şablon yazılmışsa `{{ad}}`, `{{proje}}`, `{{eposta}}`
        # bunlarla doldurulur.
        {"ad": ad, "proje": proje, "eposta": eposta},
    )

    satirlar = await dispatch(
        db,
        event_type="client_invite",
        title=baslik,
        body=govde,
        recipients=[{"email": eposta, "role": "client", "phone": ""}],
        link=yol,
    )

    # dispatch kanal başına bir satır döndürüyor. E-posta satırı hiç yoksa
    # kanal panelden kapatılmış demektir ("off"); varsa satırın kendi
    # durumu ne diyorsa o. Bu bilgi panele taşınıyor çünkü "davet gitti"
    # demek, gerçekten gittiğini bilmeden, en kötü yalan.
    eposta_durumu = "off"
    eposta_ayrinti = ""
    for satir in satirlar:
        if satir.channel == "email":
            eposta_durumu = satir.delivery_status or "unknown"
            eposta_ayrinti = satir.delivery_detail or ""
            break

    return InviteResponse(
        ok=True,
        link=yol,
        email_status=eposta_durumu,
        email_detail=eposta_ayrinti,
        subject=baslik,
        message=govde,
    )
