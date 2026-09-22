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

    baslik, govde = await render(
        db,
        "client_invite",
        "Projeniz açıldı",
        (
            "Merhaba {ad},\n\n"
            "{proje} için proje kaydınız açıldı. Aşamaları takip etmek, "
            "dosyalara ulaşmak ve soru sormak için panelinize kaydolabilirsiniz.\n\n"
            "ÖNEMLİ: Kaydolurken şu e-posta adresini kullanın:\n"
            "{eposta}\n\n"
            "Projeniz bu adrese bağlı. Başka bir adresle kaydolursanız "
            "panelinizde projeyi göremezsiniz."
        ),
        {
            "ad": payload.name or eposta,
            "proje": payload.project_title or "Projeniz",
            "eposta": eposta,
        },
    )

    await dispatch(
        db,
        event_type="client_invite",
        title=baslik,
        body=govde,
        recipients=[{"email": eposta, "role": "client", "phone": ""}],
        link=yol,
    )

    return InviteResponse(ok=True, link=yol)
