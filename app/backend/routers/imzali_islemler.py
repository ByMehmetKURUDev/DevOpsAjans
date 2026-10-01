"""İmzalı işlem bağlantıları — uçlar.

Üç kapı
-------
* Herkese açık (`/api/v1/islem/{jeton}`): bağlantıyı açan kişi, oturum
  açmadan özeti görür ve kararını verir. Jetonun kendisi yetki; alıcının
  e-postası maskeli döner (`a***@alan.com`) — bağlantı elden ele gidebilir.
  IP başına dakikada 20 istek (bellek içi; tek süreçli ücretsiz sunucu için
  yeterli, jeton 192 bit olduğundan tahmin zaten imkânsız — sınır yalnız
  gürültüyü kesiyor).
* Yönetici (`/api/v1/islem-yonetim`): bağlantı üretir (ham bağlantı YALNIZ
  bu yanıtta, bir kez döner), listeler, iptal eder, yeniler.
* Müşteri (`/api/v1/islemlerim`): kendi bekleyen işlemleri — bağlantı
  dönmez; aynı kararı panelden, oturumla verir. E-posta jetondan alınıyor.

Hata gövdeleri `{"detail": {"kod": "..."}}`: ön yüz metni yedi dilde
kendisi kuruyor (site analizi deseni).
"""

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.hesap_baglami import izin_gerekli, izin_hatasi, musteri_baglami
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.signed_actions import SignedActions
from pydantic import BaseModel, ConfigDict, Field
from services import imzali_islem as servis
from services.imzali_islem import IslemHatasi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/islem", tags=["imzali-islem"])
yonetici_router = APIRouter(prefix="/api/v1/islem-yonetim", tags=["imzali-islem"])
# Faz 1F: müşterinin bu modülü kapalıysa 403 `modul_kapali` (yönetici etkilenmez).
# Faz 2E: ekip üyesi yalnız izni olan türdeki işlemleri görür/karara bağlar
# (teklif → faturalar, teslim onayı → projeler); ikisi de yoksa 403.
musteri_router = APIRouter(
    prefix="/api/v1/islemlerim",
    tags=["imzali-islem"],
    dependencies=[_Depends(izin_gerekli("faturalar", "projeler", "raporlar")), _Depends(modul_gerekli("islem"))],
)

#: İşlem türü → ekip üyesinde gereken hesap izni.
TUR_IZNI = {"teklif_kabul": "faturalar", "teslimat_onay": "projeler", "rapor_goruntule": "raporlar"}

DAKIKA_SINIRI = 20
_EPOSTA = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]{2,}$")


# --------------------------------------------------------------------------
# Hız sınırı (bellek içi, IP özeti başına kayan pencere)
# --------------------------------------------------------------------------
# Faz 2D: sınıf `utils/hiz_siniri.py`ye taşındı (giriş uçları da kullanıyor).
_HizSiniri = HizSiniri


hiz_siniri = _HizSiniri(DAKIKA_SINIRI)


def _sinir_denetle(request: Request) -> str:
    ozet = ip_ozeti(istemci_ip(request))
    if not hiz_siniri.izin_var_mi(ozet):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"kod": "sinir"})
    return ozet


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class AcikIslem(BaseModel):
    """Girişsiz sayfanın gördüğü alanlar."""

    tur: str
    baslik: str
    ayrinti: Dict[str, Any]
    durum: str
    sonuc: Optional[str] = None
    sonuclar: List[str]
    not_zorunlu: List[str]
    son_kullanma: Optional[datetime] = None
    kullanildi_at: Optional[datetime] = None
    alici: str


class KararGirdisi(BaseModel):
    # Ön yüz `not` gönderiyor (Python'da ayrılmış kelime) → alias.
    model_config = ConfigDict(populate_by_name=True)

    sonuc: str
    not_: Optional[str] = Field(None, alias="not")


class KararYaniti(BaseModel):
    durum: str
    sonuc: Optional[str] = None
    kullanildi_at: Optional[datetime] = None


class OlusturGirdisi(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tur: str
    hedef_id: int
    alici_eposta: Optional[str] = None
    gun: Optional[int] = None
    not_: Optional[str] = Field(None, alias="not")
    #: Teslimat için müşterinin bakacağı adres (önizleme, dosya).
    baglanti: Optional[str] = None
    #: Teslimat onayında proje bir sonraki aşamaya geçsin mi?
    ilerlet: bool = True
    eposta_gonder: bool = False


class YenileGirdisi(BaseModel):
    gun: Optional[int] = None
    eposta_gonder: bool = False


class YonetimSatiri(BaseModel):
    id: int
    tur: str
    hedef_tablo: str
    hedef_id: int
    alici_eposta: str
    baslik: str
    ayrinti: Dict[str, Any]
    durum: str
    sonuc: Optional[str] = None
    sonuc_notu: Optional[str] = None
    son_kullanma: Optional[datetime] = None
    kullanildi_at: Optional[datetime] = None
    olusturan_eposta: Optional[str] = None
    created_at: Optional[datetime] = None


class OlusturYaniti(BaseModel):
    """Bağlantı YALNIZ burada döner; bir daha gösterilmez."""

    islem: YonetimSatiri
    baglanti: str
    eposta_gonderildi: bool = False
    #: Yenilemede iptal edilen eski kaydın kimliği.
    eski_id: Optional[int] = None


class MusteriSatiri(BaseModel):
    id: int
    tur: str
    baslik: str
    ayrinti: Dict[str, Any]
    durum: str
    sonuclar: List[str]
    not_zorunlu: List[str]
    son_kullanma: Optional[datetime] = None
    created_at: Optional[datetime] = None


class Hedef(BaseModel):
    id: int
    etiket: str
    alici: Optional[str] = None
    ek: Optional[str] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _hata(h: IslemHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail={"kod": h.kod})


def _eposta(kullanici: Any) -> str:
    return (getattr(kullanici, "email", "") or "").strip().lower()


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return _eposta(kullanici)


def _musteri_iste(request: Request):
    """Etkin hesap bağlamı (Faz 2E): işlemler hesabın e-postasına (alıcı) bağlı."""
    kullanici, _ = _yonetici_mi(request)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not _eposta(kullanici):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi yok")
    return musteri_baglami(request)


def _site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def _baglanti(jeton: str) -> str:
    return f"{_site_adresi()}/islem/{jeton}"


def _tanim(kayit: SignedActions):
    return servis.TURLER.get(kayit.tur) or servis.TurTanimi(kayit.hedef_tablo, ())


def _yonetim_satiri(k: SignedActions) -> YonetimSatiri:
    return YonetimSatiri(
        id=k.id,
        tur=k.tur,
        hedef_tablo=k.hedef_tablo,
        hedef_id=k.hedef_id,
        alici_eposta=k.alici_eposta,
        baslik=k.baslik,
        ayrinti=servis.ayrinti(k),
        durum=servis.gecerli_durum(k),
        sonuc=k.sonuc,
        sonuc_notu=k.sonuc_notu,
        son_kullanma=servis._utc(k.son_kullanma),
        kullanildi_at=servis._utc(k.kullanildi_at),
        olusturan_eposta=k.olusturan_eposta,
        created_at=servis._utc(k.created_at),
    )


def _karar_yaniti(k: SignedActions) -> KararYaniti:
    return KararYaniti(durum=servis.gecerli_durum(k), sonuc=k.sonuc, kullanildi_at=servis._utc(k.kullanildi_at))


async def _eposta_gonder(db: AsyncSession, kayit: SignedActions, baglanti: str) -> bool:
    """Bağlantıyı müşteriye `dispatch` ile gönderir.

    `dispatch` gövdeyi ve bağlantıyı `notifications` tablosuna da yazıyor.
    Ham jeton hiçbir tabloda kalmasın diye gönderimden hemen sonra o
    satırlardaki bağlantı "/client" ile, gövdedeki adres "…" ile
    değiştiriliyor (müşteri panelindeki "Onay bekleyenler" aynı işi görüyor).
    """
    from services.notify import dispatch, render

    ayr = servis.ayrinti(kayit)
    gun = max(1, round(((servis._utc(kayit.son_kullanma) or servis._simdi()) - servis._simdi()).total_seconds() / 86400))
    if kayit.tur == "teklif_kabul":
        konu_tr, konu_en = "Teklifiniz onayınızı bekliyor", "Your quote is awaiting your approval"
    elif kayit.tur == "teslimat_onay":
        konu_tr, konu_en = "Teslim onayınızı bekliyor", "A delivery is awaiting your approval"
    else:
        konu_tr, konu_en = "Raporunuz hazır", "Your report is ready"
    not_satiri = f"\n\nNot / Note: {ayr.get('not')}" if ayr.get("not") else ""
    try:
        baslik, govde = await render(
            db,
            f"imzali_islem_{kayit.tur}",
            f"{konu_tr} — {kayit.baslik}",
            (
                f"Merhaba,\n\n{konu_tr}: {kayit.baslik}{not_satiri}\n\n"
                f"Giriş yapmadan tek tıkla yanıtlayabilirsiniz:\n{baglanti}\n\n"
                f"Bağlantı {gun} gün geçerlidir ve yalnız bir kez kullanılabilir.\n\n"
                f"{konu_en}: {kayit.baslik}\nRespond with one click, no login needed: {baglanti}\n\n"
                f"— By Mehmet KURU Dev"
            ),
            {"baslik": kayit.baslik, "baglanti": baglanti, "gun": gun, "not": ayr.get("not") or ""},
        )
        satirlar = await dispatch(
            db,
            event_type="imzali_islem",
            title=baslik,
            body=govde,
            recipients=[{"email": kayit.alici_eposta, "role": "client"}],
            link=baglanti,
            ref_type="signed_action",
            ref_id=kayit.id,
        )
        gitti = any(getattr(s, "channel", "") == "email" and getattr(s, "delivery_status", "") == "sent" for s in satirlar)
        # Ham jetonu kalıcı kayıttan sil.
        for s in satirlar:
            if s.body:
                s.body = s.body.replace(baglanti, "…")
            if s.title:
                s.title = s.title.replace(baglanti, "…")
            s.link = "/client"
        if satirlar:
            await db.commit()
        return gitti
    except Exception:  # noqa: BLE001 - bağlantı üretildi; e-posta düşse de yönetici kopyalayabilir
        logger.exception("İmzalı işlem e-postası gönderilemedi: id=%s", kayit.id)
        return False


# --------------------------------------------------------------------------
# Herkese açık
# --------------------------------------------------------------------------
@acik_router.get("/{jeton}", response_model=AcikIslem)
async def islem_ozeti(jeton: str, request: Request, db: AsyncSession = _Depends(get_db)):
    _sinir_denetle(request)
    kayit = await servis.coz(db, jeton)
    if kayit is None or _tanim(kayit).ozel:
        # Faz 3T: teklif/sözleşme bağlantısı kendi sayfasından (`/teklif`, `/sozlesme`).
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    tanim = _tanim(kayit)
    return AcikIslem(
        tur=kayit.tur,
        baslik=kayit.baslik,
        ayrinti=servis.ayrinti(kayit),
        durum=servis.gecerli_durum(kayit),
        sonuc=kayit.sonuc,
        sonuclar=list(tanim.sonuclar),
        not_zorunlu=list(tanim.not_zorunlu),
        son_kullanma=servis._utc(kayit.son_kullanma),
        kullanildi_at=servis._utc(kayit.kullanildi_at),
        alici=servis.eposta_maskele(kayit.alici_eposta),
    )


@acik_router.post("/{jeton}", response_model=KararYaniti)
async def islem_karari(
    jeton: str, request: Request, govde: KararGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    ip = _sinir_denetle(request)
    kayit = await servis.coz(db, jeton)
    if kayit is None or _tanim(kayit).ozel:
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    try:
        sonuc = await servis.kullan(db, jeton, govde.sonuc, govde.not_, ip_ozeti=ip)
    except IslemHatasi as h:
        raise _hata(h)
    await servis.bildirimleri_gonder(db, sonuc.bildirimler)
    return _karar_yaniti(sonuc.kayit)


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.post("/olustur", response_model=OlusturYaniti)
async def olustur(request: Request, govde: OlusturGirdisi = Body(...), db: AsyncSession = _Depends(get_db)):
    yonetici = _yonetici_iste(request)
    try:
        tablo, baslik, ayr, varsayilan_alici = await servis.hedef_ozeti_kur(
            db, govde.tur, govde.hedef_id, not_=govde.not_, baglanti=govde.baglanti, ilerlet=govde.ilerlet
        )
        alici = servis.eposta_duzelt(govde.alici_eposta) or varsayilan_alici
        if not alici or not _EPOSTA.match(alici):
            raise IslemHatasi(400, "alici_gecersiz")
        jeton, kayit = await servis.olustur(
            db, govde.tur, (tablo, govde.hedef_id), alici, baslik, ayr, govde.gun, olusturan=yonetici
        )
    except IslemHatasi as h:
        raise _hata(h)
    baglanti = _baglanti(jeton)
    gitti = await _eposta_gonder(db, kayit, baglanti) if govde.eposta_gonder else False
    return OlusturYaniti(islem=_yonetim_satiri(kayit), baglanti=baglanti, eposta_gonderildi=gitti)


@yonetici_router.get("", response_model=List[YonetimSatiri])
async def liste(
    request: Request,
    tur: Optional[str] = Query(None),
    durum: Optional[str] = Query(None),
    hedef_tablo: Optional[str] = Query(None),
    hedef_id: Optional[int] = Query(None),
    adet: int = Query(200, ge=1, le=500),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    await servis.sureleri_isle(db)
    sorgu = select(SignedActions)
    if tur:
        sorgu = sorgu.where(SignedActions.tur == tur)
    else:
        # Faz 3T: teklif/sözleşme bağlantıları kendi sekmelerinde yönetiliyor.
        ozel = [k for k, v in servis.TURLER.items() if v.ozel]
        sorgu = sorgu.where(SignedActions.tur.notin_(ozel))
    if durum:
        sorgu = sorgu.where(SignedActions.durum == durum)
    if hedef_tablo:
        sorgu = sorgu.where(SignedActions.hedef_tablo == hedef_tablo)
    if hedef_id is not None:
        sorgu = sorgu.where(SignedActions.hedef_id == hedef_id)
    sonuc = await db.execute(sorgu.order_by(SignedActions.id.desc()).limit(adet))
    return [_yonetim_satiri(k) for k in sonuc.scalars().all()]


@yonetici_router.get("/hedefler", response_model=List[Hedef])
async def hedefler(request: Request, tur: str = Query(...), db: AsyncSession = _Depends(get_db)):
    """Yeni bağlantı formundaki hedef seçicisi: son teklifler / projeler."""
    _yonetici_iste(request)
    if tur == "teklif_kabul":
        from models.pricing import Pricing_inquiries

        satirlar = (
            await db.execute(select(Pricing_inquiries).order_by(Pricing_inquiries.id.desc()).limit(100))
        ).scalars().all()
        return [
            Hedef(
                id=s.id,
                etiket=f"#{s.id} · {s.scale_kod or s.ai_pm_tier_kod or s.period or '—'} · {float(s.hesaplanan_tutar or 0):g} USD",
                alici=(s.musteri_eposta or "").strip().lower() or None,
                ek=s.durum or None,
            )
            for s in satirlar
        ]
    if tur == "teslimat_onay":
        from models.projects import Projects

        satirlar = (
            await db.execute(
                select(Projects)
                .where(Projects.client_email.isnot(None), Projects.client_email != "")
                .order_by(Projects.id.desc())
                .limit(100)
            )
        ).scalars().all()
        return [
            Hedef(
                id=s.id,
                etiket=f"#{s.id} · {s.title}",
                alici=(s.client_email or "").strip().lower() or None,
                ek=s.stage or None,
            )
            for s in satirlar
        ]
    raise HTTPException(status_code=400, detail={"kod": "tur_gecersiz"})


@yonetici_router.post("/{islem_id}/iptal", response_model=YonetimSatiri)
async def iptal(islem_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    try:
        kayit = await servis.iptal_et(db, islem_id)
    except IslemHatasi as h:
        raise _hata(h)
    return _yonetim_satiri(kayit)


@yonetici_router.post("/{islem_id}/yenile", response_model=OlusturYaniti)
async def yenile(
    islem_id: int,
    request: Request,
    govde: Optional[YenileGirdisi] = Body(None),
    db: AsyncSession = _Depends(get_db),
):
    yonetici = _yonetici_iste(request)
    govde = govde or YenileGirdisi()
    try:
        jeton, eski, yeni = await servis.yenile(db, islem_id, gun=govde.gun, olusturan=yonetici)
    except IslemHatasi as h:
        raise _hata(h)
    baglanti = _baglanti(jeton)
    gitti = await _eposta_gonder(db, yeni, baglanti) if govde.eposta_gonder else False
    return OlusturYaniti(islem=_yonetim_satiri(yeni), baglanti=baglanti, eposta_gonderildi=gitti, eski_id=eski.id)


# --------------------------------------------------------------------------
# Müşteri
# --------------------------------------------------------------------------
@musteri_router.get("", response_model=List[MusteriSatiri])
async def islemlerim(request: Request, db: AsyncSession = _Depends(get_db)):
    """Müşterinin onay bekleyen işlemleri (bağlantı DÖNMEZ)."""
    baglam = _musteri_iste(request)
    eposta = baglam.hesap_email
    izinli_turler = [tur for tur, izin in TUR_IZNI.items() if baglam.izin_var(izin)]
    simdi = servis._simdi()
    satirlar = (
        await db.execute(
            select(SignedActions)
            .where(
                SignedActions.alici_eposta == eposta,
                SignedActions.durum == "bekliyor",
                SignedActions.son_kullanma > simdi,
                SignedActions.tur.in_(izinli_turler),
            )
            .order_by(SignedActions.son_kullanma.asc())
        )
    ).scalars().all()
    liste = []
    for k in satirlar:
        tanim = _tanim(k)
        liste.append(
            MusteriSatiri(
                id=k.id,
                tur=k.tur,
                baslik=k.baslik,
                ayrinti=servis.ayrinti(k),
                durum=servis.gecerli_durum(k, simdi),
                sonuclar=list(tanim.sonuclar),
                not_zorunlu=list(tanim.not_zorunlu),
                son_kullanma=servis._utc(k.son_kullanma),
                created_at=servis._utc(k.created_at),
            )
        )
    return liste


@musteri_router.post("/{islem_id}", response_model=KararYaniti)
async def islemlerim_karar(
    islem_id: int, request: Request, govde: KararGirdisi = Body(...), db: AsyncSession = _Depends(get_db)
):
    baglam = _musteri_iste(request)
    eposta = baglam.hesap_email
    tur = (
        await db.execute(
            select(SignedActions.tur).where(SignedActions.id == islem_id, SignedActions.alici_eposta == eposta)
        )
    ).scalar_one_or_none()
    if tur is not None and tur not in TUR_IZNI:
        # Faz 3T: teklif/sözleşme kararı kendi uçlarından (`/tekliflerim`, `/sozlesmelerim`).
        raise HTTPException(status_code=404, detail={"kod": "bulunamadi"})
    if tur is not None and not baglam.izin_var(TUR_IZNI.get(tur, "faturalar")):
        raise izin_hatasi(TUR_IZNI.get(tur, "faturalar"))
    try:
        sonuc = await servis.kullan_id(
            db, islem_id, eposta, govde.sonuc, govde.not_, ip_ozeti=ip_ozeti(istemci_ip(request))
        )
    except IslemHatasi as h:
        raise _hata(h)
    await servis.bildirimleri_gonder(db, sonuc.bildirimler)
    return _karar_yaniti(sonuc.kayit)


router = (acik_router, yonetici_router, musteri_router)
