"""Modül kaydı uçları (Faz 1F).

Kim ne görüyor
--------------
* Müşteri (`/api/v1/modullerim`): manifestin müşteriye görünen kısmı ve her
  modülün kendisi için geçerli durumu (açık / yakında / paketinize
  eklenebilir). E-posta jetondan alınıyor, sorgudan değil. Müşteri paneli
  sekme çubuğunu ve genel görünüm kartlarını bu yanıttan çiziyor.
* Yönetici (`/api/v1/moduller`): manifest, modül başına açık müşteri sayısı,
  bir müşterinin modülleri; açma/kapama, ayar, varsayılana dönme.

Açma/kapama müşteriye bildirim (`modul_acildi` / `modul_kapandi`) olarak
gidiyor; tablo yazımı denetim kaydına kendiliğinden düşüyor (1B).
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core import moduller as manifest
from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.hesap_baglami import musteri_eposta
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.workspace_modules import WorkspaceModules  # noqa: F401 - tablo oluşsun
from pydantic import BaseModel
from services import moduller as servis
from services.moduller import ModulDurumu, ModulHatasi, MusteriModulleri
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

musteri_router = APIRouter(prefix="/api/v1/modullerim", tags=["moduller"])
yonetici_router = APIRouter(prefix="/api/v1/moduller", tags=["moduller"])

_EPOSTA = re.compile(r"^[^@\s<>,;/]+@[^@\s<>,;/]+\.[^@\s<>,;/]{2,}$")

for _hata in manifest.manifest_hatalari():  # açılışta görünür olsun (testler de yakalıyor)
    logger.error("Modül manifesti tutarsız: %s", _hata)


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return (kullanici.email or "").strip().lower()


def _musteri_iste(request: Request) -> str:
    """Etkin hesap (Faz 2E): modüller hesaba ait; her aktif üye görebilir."""
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not (kullanici.email or "").strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi yok")
    return musteri_eposta(request)


def _eposta_dogrula(eposta: str) -> str:
    e = servis.eposta_duzelt(eposta)
    if len(e) > 254 or not _EPOSTA.match(e):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"kod": "gecersiz_eposta"})
    return e


def _hata(h: ModulHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _musteri_satiri(d: ModulDurumu) -> Dict[str, Any]:
    m = d.modul
    return {
        "anahtar": m.anahtar,
        "ad_anahtari": m.ad_anahtari,
        "aciklama_anahtari": m.aciklama_anahtari,
        "ikon": m.ikon,
        "kategori": m.kategori,
        "musteri_sekmesi": m.musteri_sekmesi,
        "yerlesim": list(m.yerlesim),
        "durum": m.durum,
        "cekirdek": m.cekirdek,
        "paketler": list(m.paketler),
        "bagimliliklar": list(m.bagimliliklar),
        "acik": d.acik,
        "kaynak": d.kaynak,
        "gorunum": d.gorunum,
        "ayarlar": dict(d.ayarlar),
    }


def _yonetici_satiri(d: ModulDurumu) -> Dict[str, Any]:
    satir = _musteri_satiri(d)
    satir.update(
        {
            "yonetici_sekmesi": d.modul.yonetici_sekmesi,
            "gerekli_rol": d.modul.gerekli_rol,
            "varsayilan_acik": d.modul.varsayilan_acik,
            "acik_ham": d.acik_ham,
            "elle": d.elle,
            "varsayilan_deger": d.varsayilan_deger,
            "engelleyen": list(d.engelleyen),
            "ayar_alanlari": [a.sozluk() for a in d.modul.ayarlar],
        }
    )
    return satir


def _musteri_yaniti(mm: MusteriModulleri) -> Dict[str, Any]:
    return {
        "eposta": mm.eposta,
        "paket": mm.paket,
        "moduller": [_yonetici_satiri(d) for d in mm.sirali(yalniz_musteri=True)],
    }


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("")
async def modullerim(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin modülleri (sekme çubuğu, genel görünüm kartları, Modüllerim)."""
    eposta = _musteri_iste(request)
    mm = await servis.musteri_modulleri(db, eposta)
    return {"paket": mm.paket, "moduller": [_musteri_satiri(d) for d in mm.sirali(yalniz_musteri=True)]}


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
class ModulGirdisi(BaseModel):
    acik: Optional[bool] = None
    ayarlar: Optional[Dict[str, Any]] = None


@yonetici_router.get("")
async def manifest_listesi(request: Request):
    _yonetici_iste(request)
    return {
        "moduller": [m.sozluk() for m in manifest.MODULLER],
        "kategoriler": list(manifest.KATEGORILER),
        "paketler": list(manifest.PAKETLER),
        "durumlar": list(manifest.DURUMLAR),
    }


@yonetici_router.get("/ozet")
async def modul_ozeti(request: Request, db: AsyncSession = _Depends(get_db)):
    """Modül başına açık müşteri sayısı."""
    _yonetici_iste(request)
    return await servis.ozet(db)


@yonetici_router.get("/musteriler")
async def musteriler(request: Request, db: AsyncSession = _Depends(get_db)) -> List[Dict[str, Optional[str]]]:
    """Modül yönetilebilecek müşteriler (kullanıcılar + kayıtlardaki adresler)."""
    _yonetici_iste(request)
    return await servis.musteri_listesi(db)


@yonetici_router.get("/musteri/{eposta}")
async def musteri_modulleri(eposta: str, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    return _musteri_yaniti(await servis.musteri_modulleri(db, _eposta_dogrula(eposta)))


@yonetici_router.put("/musteri/{eposta}/{anahtar}")
async def modul_ayarla(
    eposta: str,
    anahtar: str,
    request: Request,
    govde: ModulGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Aç/kapat (`acik`) ve/veya müşteriye özel ayarlar (`ayarlar`)."""
    yonetici = _yonetici_iste(request)
    e = _eposta_dogrula(eposta)
    try:
        degisiklik = await servis.modul_ayarla(
            db, e, anahtar, acik=govde.acik, ayarlar=govde.ayarlar, yonetici=yonetici
        )
    except ModulHatasi as h:
        raise _hata(h)
    await servis.degisiklikleri_bildir(db, degisiklik)
    return _musteri_yaniti(degisiklik.sonraki)


@yonetici_router.delete("/musteri/{eposta}/{anahtar}")
async def varsayilana_don(eposta: str, anahtar: str, request: Request, db: AsyncSession = _Depends(get_db)):
    """Elle açma/kapamayı kaldırır: modül paket/varsayılana göre hesaplanır (ayarlar korunur)."""
    yonetici = _yonetici_iste(request)
    e = _eposta_dogrula(eposta)
    try:
        degisiklik = await servis.modul_ayarla(db, e, anahtar, varsayilana_don=True, yonetici=yonetici)
    except ModulHatasi as h:
        raise _hata(h)
    await servis.degisiklikleri_bildir(db, degisiklik)
    return _musteri_yaniti(degisiklik.sonraki)


router = (musteri_router, yonetici_router)
