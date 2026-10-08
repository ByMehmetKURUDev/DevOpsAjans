"""Faz 11B — Müşteri paneli "Genel bakış" özeti.

Müşteri  GET /api/v1/musteri-ozeti   karşılama, proje ilerlemesi, kalan iş, ekip, onay bekleyenler, yaklaşan
                                     toplantı, hedef, bakiye, açık faturalar, destek — tek istekte

Etkin hesap `dependencies/hesap_baglami.musteri_baglami` ile (jeton + `X-MK-Hesap`; üyesi olmadığı hesap 403
`hesap_uyesi_degil`, oturumsuz 401). Ayrı bir izin istemez: her kalem kendi iznine/modülüne bakar, izni
olmayan kalem `null` döner (`services/musteri_ozeti.py`). Yönetici kendi adına gelirse kendi e-postasının
hesabı okunur (müşteri kaydı yoksa boş kalemler) — diğer müşteri uçlarıyla aynı davranış.
"""

import logging

from core.database import get_db
from dependencies.hesap_baglami import musteri_baglami
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from services import musteri_ozeti as servis
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/musteri-ozeti", tags=["musteri-ozeti"])


@router.get("")
async def musteri_ozeti(request: Request, db: AsyncSession = Depends(get_db)):
    baglam = musteri_baglami(request)
    veri = await servis.musteri_ozeti(db, baglam)
    # Kişiye/hesaba özel: ara katmanlar saklamasın (istemcide kısa bellek var).
    return JSONResponse(veri, headers={"Cache-Control": "no-store"})
