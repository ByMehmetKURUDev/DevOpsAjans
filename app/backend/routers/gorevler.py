"""Faz 2B — proje görevleri (Kanban), kontrol listesi, bağımlılık, saat, revizyon sayacı.

Yönetici  /api/v1/gorevler/...     (tam yetki; projeyi müşteriden bağımsız yönetir)
Müşteri   /api/v1/gorevlerim/...   (yalnız KENDİ projesinin `musteriye_gorunur`
                                    görevleri, salt okunur; e-posta JETONDAN)

Kurallar ve revizyon sayacının tanımı `services/gorevler.py` başında.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.proje_gorevleri import (
    GOREV_DURUMLARI,
    ONCELIKLER,
    ProjectTasks,
    TaskChecklist,
    TaskDependencies,
    TaskTimeEntries,
)
from models.staff import Staff
from pydantic import BaseModel
from services import gorevler as gs
from services.gorevler import GorevHatasi
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(
    prefix="/api/v1/gorevler", tags=["gorevler"], dependencies=[_Depends(yonetici_gerekli)]
)
musteri_router = APIRouter(
    prefix="/api/v1/gorevlerim",
    tags=["gorevler"],
    dependencies=[_Depends(modul_gerekli("gorevler"))],
)

BASLIK_SINIRI = 200
ACIKLAMA_SINIRI = 4000
KONTROL_SINIRI = 50
KONTROL_METNI = 300
GOREV_PROJE_BASINA = 500


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class GorevGirdisi(BaseModel):
    baslik: str
    aciklama: Optional[str] = None
    durum: Optional[str] = "yapilacak"
    oncelik: Optional[str] = "normal"
    atanan: Optional[str] = None
    bitis_tarihi: Optional[str] = None
    musteriye_gorunur: Optional[bool] = False
    ust_gorev_id: Optional[int] = None
    kilometre_tasi: Optional[bool] = False
    tahmini_saat: Optional[float] = None
    etiketler: Optional[Any] = None


class GorevGuncelleme(BaseModel):
    baslik: Optional[str] = None
    aciklama: Optional[str] = None
    durum: Optional[str] = None
    oncelik: Optional[str] = None
    atanan: Optional[str] = None
    bitis_tarihi: Optional[str] = None
    musteriye_gorunur: Optional[bool] = None
    ust_gorev_id: Optional[int] = None
    kilometre_tasi: Optional[bool] = None
    tahmini_saat: Optional[float] = None
    etiketler: Optional[Any] = None


class SiraOgesi(BaseModel):
    id: int
    durum: str
    sira: int


class SiraGirdisi(BaseModel):
    gorevler: List[SiraOgesi]


class KontrolGirdisi(BaseModel):
    metin: str


class KontrolGuncelleme(BaseModel):
    metin: Optional[str] = None
    tamam: Optional[bool] = None
    sira: Optional[int] = None


class BagimlilikGirdisi(BaseModel):
    bagli_oldugu_id: int


class SaatGirdisi(BaseModel):
    saat: float
    tarih: Optional[str] = None
    aciklama: Optional[str] = None
    #: Proje müşterisinin kredisinden düş (1C `harca`; kredi modülü açıksa).
    krediden_dus: Optional[bool] = False
    #: Krediden düşülecek saat (varsayılan: girilen saatin tamamı).
    kredi_saat: Optional[float] = None


class KrediGirdisi(BaseModel):
    saat: Optional[float] = None


class RevizyonHakkiGirdisi(BaseModel):
    aylik_revizyon_saati: Optional[float] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return gs.eposta_duzelt(kullanici.email)


def _musteri_iste(request: Request) -> str:
    kullanici, _ = _yonetici_mi(request)
    eposta = gs.eposta_duzelt(getattr(kullanici, "email", None))
    if not eposta:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum gerekli")
    return eposta


def _metin(deger: Optional[str], sinir: int, *, zorunlu: bool = False, kod: str = "baslik_gerekli") -> Optional[str]:
    d = (deger or "").strip()
    if zorunlu and not d:
        raise GorevHatasi(400, kod)
    return d[:sinir] or None


def _secim(deger: Optional[str], secenekler, kod: str) -> str:
    if deger not in secenekler:
        raise GorevHatasi(400, kod)
    return deger


async def _atanan_dogrula(db: AsyncSession, ham: Optional[str]) -> Optional[str]:
    eposta = gs.eposta_duzelt(ham)
    if not eposta:
        return None
    var = (
        await db.execute(select(Staff.id).where(func.lower(Staff.email) == eposta).where(Staff.aktif.isnot(False)))
    ).first()
    if var is None:
        raise GorevHatasi(400, "atanan_gecersiz")
    return eposta


async def _sonraki_sira(db: AsyncSession, proje_id: int, durum: str) -> int:
    en = (
        await db.execute(
            select(func.coalesce(func.max(ProjectTasks.sira), -1))
            .where(ProjectTasks.proje_id == proje_id)
            .where(ProjectTasks.durum == durum)
        )
    ).scalar()
    return int(en if en is not None else -1) + 1


async def _kredi_modulu_acik(db: AsyncSession, eposta: Optional[str]) -> bool:
    if not eposta:
        return False
    from services.moduller import modul_acik_mi

    return await modul_acik_mi(db, eposta, "krediler")


async def _ekip(db: AsyncSession) -> List[Dict[str, Any]]:
    satirlar = (await db.execute(select(Staff).where(Staff.aktif.isnot(False)).order_by(Staff.ad))).scalars().all()
    return [{"ad": s.ad, "email": gs.eposta_duzelt(s.email)} for s in satirlar]


async def _proje_yaniti(db: AsyncSession, proje) -> Dict[str, Any]:
    from services.geri_bildirim import proje_acik_geri_bildirimleri

    musteri = gs.eposta_duzelt(proje.client_email)
    return {
        "proje": {
            "id": proje.id,
            "baslik": proje.title,
            "client_email": musteri or None,
            "aylik_revizyon_saati": proje.aylik_revizyon_saati,
        },
        "gorevler": await gs.yonetici_listesi(db, proje.id),
        "geri_bildirimler": await proje_acik_geri_bildirimleri(db, proje.id),
        "revizyon": await gs.revizyon_sayaci(db, musteri) if musteri else None,
        "kredi_modulu": await _kredi_modulu_acik(db, musteri),
        "ekip": await _ekip(db),
        "durumlar": list(GOREV_DURUMLARI),
        "oncelikler": list(ONCELIKLER),
    }


async def _durum_sonrasi(db: AsyncSession, proje, gorev: ProjectTasks) -> None:
    await gs.gorev_bildir(db, proje, gorev)
    await gs.geri_bildirimi_esle(db, gorev)


# --------------------------------------------------------------------------
# Yönetici — proje
# --------------------------------------------------------------------------
@yonetici_router.get("/proje/{proje_id}")
async def proje_gorevleri(proje_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    proje = await gs.proje_bul(db, proje_id)
    return await _proje_yaniti(db, proje)


@yonetici_router.post("/proje/{proje_id}")
async def gorev_ekle(proje_id: int, request: Request, govde: GorevGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    proje = await gs.proje_bul(db, proje_id)
    adet = (await db.execute(select(func.count(ProjectTasks.id)).where(ProjectTasks.proje_id == proje.id))).scalar()
    if int(adet or 0) >= GOREV_PROJE_BASINA:
        raise GorevHatasi(409, "gorev_siniri")
    durum = _secim(govde.durum or "yapilacak", GOREV_DURUMLARI, "durum_gecersiz")
    g = ProjectTasks(
        proje_id=proje.id,
        baslik=_metin(govde.baslik, BASLIK_SINIRI, zorunlu=True),
        aciklama=_metin(govde.aciklama, ACIKLAMA_SINIRI),
        durum=durum,
        oncelik=_secim(govde.oncelik or "normal", ONCELIKLER, "oncelik_gecersiz"),
        atanan=await _atanan_dogrula(db, govde.atanan),
        bitis_tarihi=gs.tarih_coz(govde.bitis_tarihi),
        sira=await _sonraki_sira(db, proje.id, durum),
        musteriye_gorunur=bool(govde.musteriye_gorunur),
        kilometre_tasi=bool(govde.kilometre_tasi),
        tahmini_saat=gs.saat_dogrula(govde.tahmini_saat, sifir_olabilir=True),
        harcanan_saat=0.0,
        etiketler=json.dumps(gs.etiketleri_duzelt(govde.etiketler)),
        olusturan_eposta=ben,
    )
    if durum == "tamam":
        from datetime import datetime, timezone

        g.tamamlandi_at = datetime.now(timezone.utc)
    await gs.ust_denetle(db, g, govde.ust_gorev_id)
    g.ust_gorev_id = govde.ust_gorev_id
    db.add(g)
    await db.commit()
    await db.refresh(g)
    if durum in gs.BILDIRIMLI_DURUMLAR:
        await gs.gorev_bildir(db, proje, g)
    return await gs.tek_gorev(db, g)


@yonetici_router.put("/proje/{proje_id}/sira")
async def toplu_sira(proje_id: int, request: Request, govde: SiraGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    """Kanban: sütun + sıra toplu güncelleme. Bağımlılık kuralı son duruma göre; hep ya da hiç."""
    _yonetici_iste(request)
    proje = await gs.proje_bul(db, proje_id)
    gorevler = {g.id: g for g in await gs.proje_gorevleri(db, proje.id)}
    if len(govde.gorevler) > GOREV_PROJE_BASINA:
        raise GorevHatasi(400, "cok_fazla")
    yeni: Dict[int, SiraOgesi] = {}
    for o in govde.gorevler:
        if o.id not in gorevler:
            raise GorevHatasi(404, "gorev_yok", gorev=o.id)
        _secim(o.durum, GOREV_DURUMLARI, "durum_gecersiz")
        if o.sira < 0 or o.sira > 100000:
            raise GorevHatasi(400, "sira_gecersiz")
        yeni[o.id] = o
    son_durumlar = {gid: (yeni[gid].durum if gid in yeni else g.durum) for gid, g in gorevler.items()}
    kenarlar = await gs.bagimlilik_kenarlari(db, list(gorevler))
    for gid, o in yeni.items():
        if o.durum == "tamam" and gorevler[gid].durum != "tamam":
            bekleyen = gs.bekleyen_bagimliliklar(gid, kenarlar, son_durumlar)
            if bekleyen:
                raise GorevHatasi(409, "bagimlilik_bitmedi", gorev=gid, gorevler=bekleyen)
    degisenler: List[ProjectTasks] = []
    for gid, o in yeni.items():
        g = gorevler[gid]
        if gs.durum_ata(g, o.durum):
            degisenler.append(g)
        g.sira = o.sira
    await db.commit()
    for g in degisenler:
        await _durum_sonrasi(db, proje, g)
    return {"gorevler": await gs.yonetici_listesi(db, proje.id)}


@yonetici_router.put("/proje/{proje_id}/revizyon")
async def revizyon_hakki_ayarla(
    proje_id: int, request: Request, govde: RevizyonHakkiGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    """Paketten revizyon hakkı bulunamayan müşteri için projeye elle aylık saat."""
    _yonetici_iste(request)
    proje = await gs.proje_bul(db, proje_id)
    proje.aylik_revizyon_saati = gs.saat_dogrula(govde.aylik_revizyon_saati, sifir_olabilir=True)
    await db.commit()
    musteri = gs.eposta_duzelt(proje.client_email)
    return {
        "aylik_revizyon_saati": proje.aylik_revizyon_saati,
        "revizyon": await gs.revizyon_sayaci(db, musteri) if musteri else None,
    }


# --------------------------------------------------------------------------
# Yönetici — görev
# --------------------------------------------------------------------------
@yonetici_router.patch("/{gorev_id}")
async def gorev_guncelle(gorev_id: int, request: Request, govde: GorevGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    proje = await gs.proje_bul(db, g.proje_id)
    alanlar = govde.model_fields_set
    durum_degisti = False
    if "baslik" in alanlar:
        g.baslik = _metin(govde.baslik, BASLIK_SINIRI, zorunlu=True)
    if "aciklama" in alanlar:
        g.aciklama = _metin(govde.aciklama, ACIKLAMA_SINIRI)
    if "oncelik" in alanlar:
        g.oncelik = _secim(govde.oncelik, ONCELIKLER, "oncelik_gecersiz")
    if "atanan" in alanlar:
        g.atanan = await _atanan_dogrula(db, govde.atanan)
    if "bitis_tarihi" in alanlar:
        g.bitis_tarihi = gs.tarih_coz(govde.bitis_tarihi)
    if "musteriye_gorunur" in alanlar and govde.musteriye_gorunur is not None:
        g.musteriye_gorunur = bool(govde.musteriye_gorunur)
    if "kilometre_tasi" in alanlar and govde.kilometre_tasi is not None:
        g.kilometre_tasi = bool(govde.kilometre_tasi)
    if "tahmini_saat" in alanlar:
        g.tahmini_saat = gs.saat_dogrula(govde.tahmini_saat, sifir_olabilir=True)
    if "ust_gorev_id" in alanlar:
        await gs.ust_denetle(db, g, govde.ust_gorev_id)
        g.ust_gorev_id = govde.ust_gorev_id
    if "etiketler" in alanlar:
        etiketler = gs.etiketleri_duzelt(govde.etiketler)
        eski_revizyon = gs.revizyon_mu(g)
        g.etiketler = json.dumps(etiketler)
        yeni_revizyon = gs.REVIZYON_ETIKETI in etiketler
        if eski_revizyon != yeni_revizyon:
            await db.execute(
                update(TaskTimeEntries).where(TaskTimeEntries.gorev_id == g.id).values(revizyon=yeni_revizyon)
            )
    if "durum" in alanlar and govde.durum is not None:
        yeni = _secim(govde.durum, GOREV_DURUMLARI, "durum_gecersiz")
        if yeni == "tamam" and g.durum != "tamam":
            await gs.tamam_denetle(db, g)
        if yeni != g.durum:
            g.sira = await _sonraki_sira(db, g.proje_id, yeni)
        durum_degisti = gs.durum_ata(g, yeni)
    await db.commit()
    await db.refresh(g)
    if durum_degisti:
        await _durum_sonrasi(db, proje, g)
    return await gs.tek_gorev(db, g)


@yonetici_router.delete("/{gorev_id}")
async def gorev_sil(gorev_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Görevi siler: kontrol listesi ve bağımlılıkları da gider, alt görevler üstsüz
    kalır. Saat girişleri revizyon sayacı bozulmasın diye kalıyor."""
    _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    for k in (await db.execute(select(TaskChecklist).where(TaskChecklist.gorev_id == g.id))).scalars().all():
        await db.delete(k)
    for d in (
        await db.execute(
            select(TaskDependencies).where(
                (TaskDependencies.gorev_id == g.id) | (TaskDependencies.bagli_oldugu_id == g.id)
            )
        )
    ).scalars().all():
        await db.delete(d)
    for alt in (await db.execute(select(ProjectTasks).where(ProjectTasks.ust_gorev_id == g.id))).scalars().all():
        alt.ust_gorev_id = None
    try:
        from models.geri_bildirim import FeedbackItems

        for fb in (await db.execute(select(FeedbackItems).where(FeedbackItems.gorev_id == g.id))).scalars().all():
            fb.gorev_id = None
            if fb.durum == "gorev":
                fb.durum = "inceleniyor"
    except Exception:  # noqa: BLE001
        logger.exception("Geri bildirim bağı çözülemedi")
    await db.delete(g)
    await db.commit()
    return {"silindi": gorev_id}


# --------------------------------------------------------------------------
# Kontrol listesi
# --------------------------------------------------------------------------
@yonetici_router.post("/{gorev_id}/kontrol")
async def kontrol_ekle(gorev_id: int, request: Request, govde: KontrolGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    adet = (await db.execute(select(func.count(TaskChecklist.id)).where(TaskChecklist.gorev_id == g.id))).scalar()
    if int(adet or 0) >= KONTROL_SINIRI:
        raise GorevHatasi(409, "kontrol_siniri")
    en = (await db.execute(select(func.coalesce(func.max(TaskChecklist.sira), -1)).where(TaskChecklist.gorev_id == g.id))).scalar()
    k = TaskChecklist(gorev_id=g.id, metin=_metin(govde.metin, KONTROL_METNI, zorunlu=True, kod="metin_gerekli"), tamam=False, sira=int(en) + 1)
    db.add(k)
    await db.commit()
    return await gs.tek_gorev(db, g)


@yonetici_router.patch("/kontrol/{kontrol_id}")
async def kontrol_guncelle(kontrol_id: int, request: Request, govde: KontrolGuncelleme = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = (await db.execute(select(TaskChecklist).where(TaskChecklist.id == kontrol_id))).scalar_one_or_none()
    if k is None:
        raise GorevHatasi(404, "kontrol_yok")
    alanlar = govde.model_fields_set
    if "metin" in alanlar:
        k.metin = _metin(govde.metin, KONTROL_METNI, zorunlu=True, kod="metin_gerekli")
    if "tamam" in alanlar and govde.tamam is not None:
        k.tamam = bool(govde.tamam)
    if "sira" in alanlar and govde.sira is not None:
        k.sira = max(0, int(govde.sira))
    await db.commit()
    return await gs.tek_gorev(db, await gs.gorev_bul(db, k.gorev_id))


@yonetici_router.delete("/kontrol/{kontrol_id}")
async def kontrol_sil(kontrol_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    k = (await db.execute(select(TaskChecklist).where(TaskChecklist.id == kontrol_id))).scalar_one_or_none()
    if k is None:
        raise GorevHatasi(404, "kontrol_yok")
    gorev_id = k.gorev_id
    await db.delete(k)
    await db.commit()
    return await gs.tek_gorev(db, await gs.gorev_bul(db, gorev_id))


# --------------------------------------------------------------------------
# Bağımlılık
# --------------------------------------------------------------------------
@yonetici_router.post("/{gorev_id}/bagimlilik")
async def bagimlilik_ekle(gorev_id: int, request: Request, govde: BagimlilikGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    hedef = (await db.execute(select(ProjectTasks).where(ProjectTasks.id == govde.bagli_oldugu_id))).scalar_one_or_none()
    if hedef is None or hedef.proje_id != g.proje_id:
        raise GorevHatasi(400, "bagimlilik_gecersiz")
    if hedef.id == g.id:
        raise GorevHatasi(409, "bagimlilik_dongusu")
    idler = [x.id for x in await gs.proje_gorevleri(db, g.proje_id)]
    kenarlar = await gs.bagimlilik_kenarlari(db, idler)
    if hedef.id in kenarlar.get(g.id, set()):
        return await gs.tek_gorev(db, g)
    if gs.bagimlilik_dongusu(kenarlar, g.id, hedef.id):
        raise GorevHatasi(409, "bagimlilik_dongusu")
    db.add(TaskDependencies(gorev_id=g.id, bagli_oldugu_id=hedef.id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return await gs.tek_gorev(db, g)


@yonetici_router.delete("/{gorev_id}/bagimlilik/{bagli_id}")
async def bagimlilik_sil(gorev_id: int, bagli_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    for d in (
        await db.execute(
            select(TaskDependencies).where(TaskDependencies.gorev_id == g.id).where(TaskDependencies.bagli_oldugu_id == bagli_id)
        )
    ).scalars().all():
        await db.delete(d)
    await db.commit()
    return await gs.tek_gorev(db, g)


# --------------------------------------------------------------------------
# Saat girişleri + krediden düşme
# --------------------------------------------------------------------------
def _giris_sozlugu(e: TaskTimeEntries) -> Dict[str, Any]:
    return {
        "id": e.id,
        "gorev_id": e.gorev_id,
        "saat": e.saat,
        "tarih": gs.iso(e.tarih),
        "aciklama": e.aciklama,
        "revizyon": bool(e.revizyon),
        "kredi_saat": e.kredi_saat,
        "giren_eposta": e.giren_eposta,
        "created_at": gs.iso(e.created_at),
    }


async def _krediden_harca(db: AsyncSession, *, musteri: str, saat: float, aciklama: str, proje_id: int, ben: str):
    if not musteri:
        raise GorevHatasi(409, "musteri_yok")
    if not await _kredi_modulu_acik(db, musteri):
        raise GorevHatasi(409, "kredi_modulu_kapali")
    from services import kredi

    try:
        return await kredi.harca(db, eposta=musteri, saat=saat, aciklama=aciklama, proje_id=proje_id, olusturan=ben)
    except HTTPException as h:
        if h.status_code == 409:
            raise GorevHatasi(409, "yetersiz_bakiye") from h
        raise GorevHatasi(400, "kredi_hatasi") from h


async def _saat_yaniti(db: AsyncSession, g: ProjectTasks, proje, giris: Optional[TaskTimeEntries]) -> Dict[str, Any]:
    musteri = gs.eposta_duzelt(proje.client_email)
    sayac = await gs.revizyon_sayaci(db, musteri) if musteri else None
    if sayac and giris is not None and giris.revizyon:
        await gs.revizyon_asim_bildir(db, musteri, sayac)
    kredi_bakiye = None
    if musteri and await _kredi_modulu_acik(db, musteri):
        try:
            from services.kredi import bakiye

            kredi_bakiye = await bakiye(db, musteri)
        except Exception:  # noqa: BLE001
            kredi_bakiye = None
    return {
        "giris": _giris_sozlugu(giris) if giris is not None else None,
        "gorev": await gs.tek_gorev(db, g),
        "revizyon": sayac,
        "kredi_bakiye": kredi_bakiye,
    }


@yonetici_router.get("/{gorev_id}/saat")
async def saat_listesi(gorev_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    girisler = (
        await db.execute(select(TaskTimeEntries).where(TaskTimeEntries.gorev_id == g.id).order_by(TaskTimeEntries.tarih.desc(), TaskTimeEntries.id.desc()))
    ).scalars().all()
    return {"girisler": [_giris_sozlugu(e) for e in girisler]}


@yonetici_router.post("/{gorev_id}/saat")
async def saat_gir(gorev_id: int, request: Request, govde: SaatGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    ben = _yonetici_iste(request)
    g = await gs.gorev_bul(db, gorev_id)
    proje = await gs.proje_bul(db, g.proje_id)
    musteri = gs.eposta_duzelt(proje.client_email)
    saat = gs.saat_dogrula(govde.saat)
    tarih = gs.tarih_coz(govde.tarih) or gs.bugun()
    aciklama = _metin(govde.aciklama, 300)
    kredi_saat = None
    hareket_id = None
    if govde.krediden_dus:
        kredi_saat = gs.saat_dogrula(govde.kredi_saat) if govde.kredi_saat is not None else saat
        if kredi_saat > saat:
            raise GorevHatasi(400, "kredi_saat_fazla")
        satir, _ = await _krediden_harca(
            db, musteri=musteri, saat=kredi_saat, aciklama=f"Görev #{g.id}: {g.baslik}"[:300], proje_id=proje.id, ben=ben
        )
        hareket_id = satir.id
    giris = TaskTimeEntries(
        gorev_id=g.id,
        proje_id=proje.id,
        musteri_eposta=musteri or None,
        saat=saat,
        tarih=tarih,
        aciklama=aciklama,
        revizyon=gs.revizyon_mu(g),
        kredi_saat=kredi_saat,
        kredi_hareket_id=hareket_id,
        giren_eposta=ben,
    )
    db.add(giris)
    await db.flush()
    await gs.saat_toplamini_yenile(db, g.id)
    await db.commit()
    await db.refresh(giris)
    await db.refresh(g)
    return await _saat_yaniti(db, g, proje, giris)


@yonetici_router.post("/saat/{giris_id}/kredi")
async def saati_krediden_dus(giris_id: int, request: Request, govde: KrediGirdisi = Body(default=KrediGirdisi()), db: AsyncSession = _Depends(get_db)):
    """Girilmiş saatin (ör. revizyon hakkını aşan kısmın) krediden düşülmesi."""
    ben = _yonetici_iste(request)
    giris = (await db.execute(select(TaskTimeEntries).where(TaskTimeEntries.id == giris_id))).scalar_one_or_none()
    if giris is None:
        raise GorevHatasi(404, "giris_yok")
    if giris.kredi_saat:
        raise GorevHatasi(409, "zaten_dusuldu")
    saat = gs.saat_dogrula(govde.saat) if govde.saat is not None else giris.saat
    if saat > giris.saat:
        raise GorevHatasi(400, "kredi_saat_fazla")
    g = await gs.gorev_bul(db, giris.gorev_id)
    proje = await gs.proje_bul(db, giris.proje_id)
    satir, _ = await _krediden_harca(
        db, musteri=gs.eposta_duzelt(proje.client_email), saat=saat,
        aciklama=f"Görev #{g.id}: {g.baslik}"[:300], proje_id=proje.id, ben=ben,
    )
    giris.kredi_saat = saat
    giris.kredi_hareket_id = satir.id
    await db.commit()
    await db.refresh(giris)
    return await _saat_yaniti(db, g, proje, giris)


@yonetici_router.delete("/saat/{giris_id}")
async def saat_sil(giris_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    giris = (await db.execute(select(TaskTimeEntries).where(TaskTimeEntries.id == giris_id))).scalar_one_or_none()
    if giris is None:
        raise GorevHatasi(404, "giris_yok")
    if giris.kredi_saat:
        # Krediden düşülmüş giriş silinemez: önce kredi defterinde düzeltme yapılmalı.
        raise GorevHatasi(409, "kredide_dusulmus")
    gorev_id = giris.gorev_id
    await db.delete(giris)
    await db.flush()
    await gs.saat_toplamini_yenile(db, gorev_id)
    await db.commit()
    return {"silindi": giris_id}


# --------------------------------------------------------------------------
# Müşteri (salt okunur)
# --------------------------------------------------------------------------
@musteri_router.get("/proje/{proje_id}")
async def musteri_proje_gorevleri(proje_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    """Yalnız kendi projesi; yalnız `musteriye_gorunur` görevler. Başkasının projesi 404."""
    eposta = _musteri_iste(request)
    _, yonetici = _yonetici_mi(request)
    proje = await gs.proje_bul(db, proje_id)
    if not yonetici and gs.eposta_duzelt(proje.client_email) != eposta:
        raise GorevHatasi(404, "proje_yok")
    return await gs.musteri_gorunumu(db, proje)


@musteri_router.get("/revizyon")
async def musteri_revizyon_sayaci(request: Request, db: AsyncSession = _Depends(get_db)):
    """Bu ayın revizyon sayacı ("Bu ay revizyon: 3/8 saat")."""
    eposta = _musteri_iste(request)
    sayac = await gs.revizyon_sayaci(db, eposta)
    sayac.pop("paket", None)
    return sayac


router = (yonetici_router, musteri_router)
