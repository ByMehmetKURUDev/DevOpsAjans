"""Ödeme bağlantısı üretir, tahsilatı kaydeder.

Akış
----
Panelde fatura var. "Ödeme bağlantısı üret" denince burada bir
`payments` satırı açılıyor (durum `bekliyor`) ve satıra rastgele bir
jeton yazılıyor. Müşteriye giden adres `mehmetkuru.dev/ode/<jeton>`.

Müşteri o adresi açınca `GET /api/v1/odeme/<jeton>` çağrılıyor ve
yalnızca ödemek için gereken alanlar dönüyor: tutar, para birimi,
açıklama, fatura numarası, son tarih. Müşteri adı ve e-postası
dönmüyor — bağlantı elden ele gidebilir, kimin faturası olduğu
bilgisi bağlantıyı açan herkese gösterilmemeli.

Sağlayıcı henüz yok
-------------------
Bu ilk adımda kart tahsilatı bağlı değil. `POST .../webhook/<saglayici>`
ucu duruyor ama sağlayıcı ayarlanmadan **hiçbir faturayı ödendi
işaretlemiyor**: imzası doğrulanamayan bir çağrının faturayı kapatması,
adresi bilen herkesin borcu silebilmesi demek olurdu.

Elden/havale tahsilatı bugünden çalışıyor: yönetici `POST
/api/v1/odeme/elle` ile "şu fatura şu kadar, havaleyle geldi"
diyebiliyor. Kayıt aynı tabloya düşüyor, rapor aynı yerden çıkıyor.
"""

import json
import logging
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core import lemonsqueezy, shopier
from core.database import get_db
from dependencies.entity_guard import entity_guard
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Request, status
from fastapi import Depends as _Depends
from models.invoices import Invoices
from models.payments import Payments
from models.site_settings import Site_settings
from pydantic import BaseModel
from services.musteri_sitesi import siteyi_hazirla
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Sağlayıcıyı ayarlayana kadar açık olan tek tahsilat yolu.
ELLE_KANALLAR = {"elden", "havale", "eft", "diger"}

DURUMLAR = {"bekliyor", "odendi", "basarisiz", "iade", "iptal"}


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class BaglantiIstegi(BaseModel):
    invoice_id: int


class BaglantiYaniti(BaseModel):
    jeton: str
    adres: str
    payment_id: int


class AcikOdemeYaniti(BaseModel):
    """Müşterinin ödeme sayfasında gördüğü alanlar. Kişisel bilgi yok."""

    jeton: str
    invoice_no: Optional[str] = None
    aciklama: Optional[str] = None
    tutar: Optional[float] = None
    para_birimi: Optional[str] = None
    son_tarih: Optional[str] = None
    durum: Optional[str] = None
    saglayici_hazir: bool = False


class ElleTahsilat(BaseModel):
    invoice_id: int
    tutar: Optional[float] = None
    kanal: str = "havale"
    not_: Optional[str] = None


class OdemeSatiri(BaseModel):
    id: int
    invoice_id: Optional[int] = None
    invoice_no: Optional[str] = None
    client_email: Optional[str] = None
    jeton: Optional[str] = None
    saglayici: Optional[str] = None
    saglayici_ref: Optional[str] = None
    tutar: Optional[float] = None
    para_birimi: Optional[str] = None
    komisyon: Optional[float] = None
    durum: Optional[str] = None
    hata_mesaji: Optional[str] = None
    odendi_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OdemeListesi(BaseModel):
    items: List[OdemeSatiri]
    ozet: Dict[str, Any]


class ShopierBaglantisi(BaseModel):
    """Müşterinin yönlendirileceği Shopier adresi.

    Eski sürümde burada imzalı form alanları dönüyordu; Shopier API
    V1'i kaldırdığı için artık tek bir link dönüyor. Kart bilgisi yine
    Shopier'in kendi sayfasında giriliyor, bize hiç uğramıyor.
    """

    adres: str


class LemonBaglantisi(BaseModel):
    """Lemon Squeezy ödeme sayfasının adresi.

    Shopier'den farkı: bu adres gerçek bir ödeme sayfası, ürün sayfası
    değil. Sepet adımı yok ve ödeme bitince müşteri bizim sayfamıza
    geri dönüyor.
    """

    adres: str


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _yeni_jeton() -> str:
    """Tahmin edilemez, kısa, adres çubuğunda okunabilir."""
    return secrets.token_urlsafe(9)


def _saglayici_hazir_mi() -> bool:
    """Kart tahsilatı için anahtarlar tanımlı mı?

    Anahtarlar ortam değişkeninde duruyor, veritabanında değil. Shopier
    için ikisi de (anahtar ve gizli anahtar) gerekiyor: yalnız biri
    tanımlıysa imza üretilemez, o yüzden hazır sayılmıyor.
    """
    import os

    if shopier.hazir_mi() or lemonsqueezy.hazir_mi():
        return True
    return any(os.getenv(ad) for ad in ("IYZICO_API_KEY", "PAYTR_MERCHANT_ID"))


def _fatura_tahsilati(satirlar: List[Payments]) -> float:
    return sum(s.tutar or 0 for s in satirlar if s.durum == "odendi")


async def _faturayi_kapat(db: AsyncSession, kayit: Payments) -> bool:
    """Tahsilatlar tutarı karşılıyorsa faturayı ödendi işaretler.

    Kısmi ödeme olabildiği için tek bir tahsilat faturayı kapatmaya
    yetmiyor; o faturanın bütün ödenmiş satırları toplanıyor. Kuruş
    farkları yüzünden tam eşitlik aranmıyor.

    `commit` çağıran tarafta: tahsilat ile fatura aynı işlemde
    yazılsın, biri yazılıp diğeri yazılmadan kalmasın.
    """
    if not kayit.invoice_id:
        return False

    sonuc = await db.execute(select(Invoices).where(Invoices.id == kayit.invoice_id))
    fatura = sonuc.scalar_one_or_none()
    if fatura is None or fatura.amount is None:
        return False

    satirlar = await db.execute(
        select(Payments).where(Payments.invoice_id == fatura.id)
    )
    toplam = _fatura_tahsilati(list(satirlar.scalars().all()))
    if toplam + 0.001 >= fatura.amount:
        fatura.status = "paid"
        return True
    return False


async def _musteri_sitesini_ac(db: AsyncSession, kayit: Payments) -> Optional[int]:
    """Tahsilat gerçekleşince müşteri sitesi kaydını ve düğme jetonunu açar.

    Neden burada: gömme kodunu elle üretmek iki adım istiyordu (panele
    site ekle, sonra kodu kopyala) ve müşteri sayısı arttıkça bu adım
    atlanıyordu. Tahsilat, "bu artık gerçek bir müşteri" diyen en net
    işaret; kayıt o anda kendiliğinden açılıyor.

    `commit` çağıran tarafta: tahsilat ile site kaydı aynı işlemde
    yazılsın, biri yazılıp diğeri yazılmadan kalmasın.

    Hata yutuluyor: site kaydı açılamazsa tahsilatın kaydı yine
    tamamlanmalı. Para alındı, düğme sonra kurulur -- tersi kabul
    edilemez.
    """
    try:
        site = await siteyi_hazirla(
            db,
            client_email=kayit.client_email,
            ad=(kayit.invoice_no or "").strip() or None,
            kaynak="odeme",
        )
    except Exception:  # noqa: BLE001 - tahsilat bu yüzden düşmemeli
        logger.exception("Musteri sitesi otomatik acilamadi: odeme=%s", kayit.id)
        return None
    return site.id if site is not None else None


def _site_adresi() -> str:
    """Müşterinin gördüğü site kökü.

    Shopier'e verilen dönüş adresi ve ödeme sonrası yönlendirme buradan
    kuruluyor. İstekten türetilmiyor: gelen `Host` başlığına güvenip
    dönüş adresi kurmak, başlığı değiştiren birinin müşteriyi kendi
    sayfasına döndürebilmesi demek olurdu.
    """
    import os

    return (os.getenv("SITE_ADRESI") or "https://mehmetkuru.dev").rstrip("/")


async def _fatura_getir(db: AsyncSession, invoice_id: int) -> Invoices:
    sonuc = await db.execute(select(Invoices).where(Invoices.id == invoice_id))
    fatura = sonuc.scalar_one_or_none()
    if fatura is None:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı")
    return fatura


def _yonetici_iste(request: Request) -> None:
    _, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yönetici yetkisi istiyor",
        )


# --------------------------------------------------------------------------
# Yönetici uçları
# --------------------------------------------------------------------------
yonetici_router = APIRouter(
    prefix="/api/v1/odeme",
    tags=["odeme"],
    dependencies=[_Depends(entity_guard)],
)


@yonetici_router.post("/baglanti", response_model=BaglantiYaniti)
async def baglanti_uret(
    request: Request,
    govde: BaglantiIstegi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Faturaya ödeme bağlantısı açar.

    Aynı fatura için bekleyen bir bağlantı varsa yenisi üretilmiyor;
    var olan dönüyor. Yoksa müşteriye iki farklı adres gidebilir ve
    hangisinin ödendiği karışır.
    """
    _yonetici_iste(request)
    fatura = await _fatura_getir(db, govde.invoice_id)

    mevcut = await db.execute(
        select(Payments)
        .where(Payments.invoice_id == fatura.id)
        .where(Payments.durum == "bekliyor")
        .order_by(Payments.id.desc())
    )
    kayit = mevcut.scalars().first()

    if kayit is None:
        kayit = Payments(
            invoice_id=fatura.id,
            invoice_no=fatura.invoice_no,
            client_email=fatura.client_email,
            jeton=_yeni_jeton(),
            tutar=fatura.amount,
            para_birimi=fatura.currency or "TRY",
            durum="bekliyor",
        )
        db.add(kayit)
        await db.commit()
        await db.refresh(kayit)

    return BaglantiYaniti(
        jeton=kayit.jeton,
        adres=f"/ode/{kayit.jeton}",
        payment_id=kayit.id,
    )


@yonetici_router.post("/elle", response_model=OdemeSatiri)
async def elle_tahsilat(
    request: Request,
    govde: ElleTahsilat = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Elden, havale ya da EFT ile gelen tahsilatı kaydeder."""
    _yonetici_iste(request)

    kanal = (govde.kanal or "havale").strip().lower()
    if kanal not in ELLE_KANALLAR:
        raise HTTPException(
            status_code=400,
            detail=f"Kanal şunlardan biri olmalı: {', '.join(sorted(ELLE_KANALLAR))}",
        )

    fatura = await _fatura_getir(db, govde.invoice_id)
    tutar = govde.tutar if govde.tutar is not None else fatura.amount

    kayit = Payments(
        invoice_id=fatura.id,
        invoice_no=fatura.invoice_no,
        client_email=fatura.client_email,
        saglayici=kanal,
        tutar=tutar,
        para_birimi=fatura.currency or "TRY",
        durum="odendi",
        hata_mesaji=None,
        ham_yanit=json.dumps({"not": govde.not_}, ensure_ascii=False) if govde.not_ else None,
        odendi_at=datetime.now(),
    )
    db.add(kayit)

    # Tamamı tahsil edildiyse fatura kapanıyor ve bekleyen ödeme
    # bağlantısı iptal ediliyor. Yoksa iki şey bozuluyor: özet aynı
    # parayı hem "tahsil edildi" hem "bekliyor" sayıyor, ve müşteriye
    # gönderilmiş bağlantı ödenmiş bir faturayı istemeye devam ediyor.
    if fatura.amount is not None and tutar is not None and tutar + 0.001 >= fatura.amount:
        fatura.status = "paid"
        bekleyenler = await db.execute(
            select(Payments)
            .where(Payments.invoice_id == fatura.id)
            .where(Payments.durum == "bekliyor")
        )
        for eski in bekleyenler.scalars().all():
            eski.durum = "iptal"
            eski.hata_mesaji = f"{kanal} ile tahsil edildi"

    # Tahsilat alındı: müşteri sitesi kaydı ve geri bildirim düğmesinin
    # jetonu burada açılıyor. Aynı işlemde yazılıyor.
    await _musteri_sitesini_ac(db, kayit)

    await db.commit()
    await db.refresh(kayit)
    return kayit


@yonetici_router.delete("/kayit/{payment_id}")
async def kayit_sil(
    payment_id: int,
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    """Tahsilat kaydını siler.

    Silinen kayıt `odendi` idiyse faturanın durumu yeniden hesaplanıyor:
    kalan tahsilat faturayı karşılamıyorsa fatura tekrar açılıyor. Yoksa
    yanlışlıkla kaydedilmiş bir tahsilatı silmek faturayı ödenmiş
    gösterip alacağı kaybettirirdi.
    """
    _yonetici_iste(request)

    sonuc = await db.execute(select(Payments).where(Payments.id == payment_id))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")

    invoice_id = kayit.invoice_id
    odenmisti = kayit.durum == "odendi"
    await db.delete(kayit)
    await db.flush()

    if odenmisti and invoice_id:
        fatura = await db.execute(select(Invoices).where(Invoices.id == invoice_id))
        fatura = fatura.scalar_one_or_none()
        if fatura is not None and fatura.amount is not None:
            kalanlar = await db.execute(
                select(Payments).where(Payments.invoice_id == invoice_id)
            )
            toplam = _fatura_tahsilati(list(kalanlar.scalars().all()))
            if toplam + 0.001 < fatura.amount:
                fatura.status = "unpaid"

    await db.commit()
    return {"silindi": payment_id}


@yonetici_router.get("", response_model=OdemeListesi)
async def odeme_listesi(
    request: Request,
    db: AsyncSession = _Depends(get_db),
):
    """Tahsilat listesi ve panel özeti."""
    _yonetici_iste(request)

    sonuc = await db.execute(select(Payments).order_by(Payments.id.desc()).limit(200))
    satirlar = list(sonuc.scalars().all())

    tahsil = sum(s.tutar or 0 for s in satirlar if s.durum == "odendi")
    bekleyen = sum(s.tutar or 0 for s in satirlar if s.durum == "bekliyor")
    komisyon = sum(s.komisyon or 0 for s in satirlar if s.durum == "odendi")

    ozet = {
        "tahsil_edilen": round(tahsil, 2),
        "bekleyen": round(bekleyen, 2),
        "komisyon": round(komisyon, 2),
        "adet": len(satirlar),
        "saglayici_hazir": _saglayici_hazir_mi(),
        "shopier_hazir": shopier.hazir_mi(),
        # Panel iki tahsilat yolunu ayrı ayrı görüyor: TL müşteri
        # Shopier'den, döviz müşteri Lemon Squeezy'den.
        "lemon_hazir": lemonsqueezy.hazir_mi(),
    }
    return OdemeListesi(items=satirlar, ozet=ozet)


WEBHOOK_TOKEN_ANAHTARI = "shopier_webhook_token"


async def _webhook_sirri(db: AsyncSession) -> str:
    """Webhook imza sırrı.

    Önce veritabanı: abonelik panelden kurulduğunda Shopier'in döndüğü
    token oraya yazılıyor, böylece kimsenin bir yere kopyalayıp
    yapıştırması gerekmiyor. Ortam değişkeni yedek olarak duruyor.
    """
    sonuc = await db.execute(
        select(Site_settings).where(Site_settings.setting_key == WEBHOOK_TOKEN_ANAHTARI)
    )
    kayit = sonuc.scalars().first()
    if kayit and (kayit.setting_value or "").strip():
        return kayit.setting_value.strip()
    return shopier.webhook_sirri()


@yonetici_router.post("/shopier/webhook-kur")
async def shopier_webhook_kur(request: Request, db: AsyncSession = _Depends(get_db)):
    """Shopier'e "ödeme olduğunda bize haber ver" aboneliğini kurar.

    Webhook ucunu yazmak yetmiyordu: ilk canlı denemede ödeme alındı
    ama panele düşmedi, çünkü Shopier bizim adresimizi bilmiyordu.
    Burası o kaydı yapıyor.

    Aynı adres için abonelik zaten varsa yenisi açılmıyor — mükerrer
    abonelik her ödemede iki bildirim demek olurdu.

    Shopier imza token'ını yalnızca ilk cevapta veriyor; hemen
    veritabanına yazılıyor. Hata olursa Shopier'in kendi mesajı
    olduğu gibi dönüyor: bu ucu yöneticiden başkası çağıramıyor ve
    ilk kurulumda asıl zamanı yiyen şey hatanın ne olduğunu
    bilememek.
    """
    _yonetici_iste(request)

    if not shopier.hazir_mi():
        raise HTTPException(status_code=503, detail="Shopier erişim anahtarı tanımlı değil")

    adres = f"{_site_adresi()}/api/v1/odeme/shopier/webhook"

    mevcutlar = await shopier.webhook_abonelikleri()
    for abonelik in mevcutlar:
        if not isinstance(abonelik, dict):
            continue
        if (
            str(abonelik.get("url") or "").strip() == adres
            and str(abonelik.get("event") or "").strip() == shopier.ODEME_OLAYI
        ):
            return {
                "ok": True,
                "yeni": False,
                "adres": adres,
                "mesaj": "Abonelik zaten kurulu.",
            }

    try:
        cevap = await shopier.webhook_aboneligi_olustur(
            olay=shopier.ODEME_OLAYI, adres=adres
        )
    except shopier.ShopierHatasi as hata:
        logger.warning("Shopier webhook aboneligi kurulamadi: %s", hata)
        raise HTTPException(status_code=502, detail=str(hata))

    jeton = str(cevap.get("token") or "").strip()
    if jeton:
        sonuc = await db.execute(
            select(Site_settings).where(
                Site_settings.setting_key == WEBHOOK_TOKEN_ANAHTARI
            )
        )
        kayit = sonuc.scalars().first()
        if kayit is None:
            db.add(
                Site_settings(
                    setting_key=WEBHOOK_TOKEN_ANAHTARI,
                    setting_value=jeton,
                    group_name="odeme",
                    label="Shopier webhook imza token'ı",
                )
            )
        else:
            kayit.setting_value = jeton
        await db.commit()

    logger.info("Shopier webhook aboneligi kuruldu: %s", adres)
    return {
        "ok": True,
        "yeni": True,
        "adres": adres,
        "imza_saklandi": bool(jeton),
        "mesaj": "Abonelik kuruldu. Bundan sonra ödemeler kendiliğinden düşecek.",
    }


@yonetici_router.post("/shopier/mutabakat")
async def shopier_mutabakati(request: Request, db: AsyncSession = _Depends(get_db)):
    """Shopier'deki son siparişlerle kendi kayıtlarımızı karşılaştırır.

    Webhook'un yedeği. Bildirim kaybolursa (bizim sunucu uykudaysa,
    Shopier'in denemeleri tükenmişse) ödeme yapılmış ama fatura açık
    kalır. Burası o boşluğu kapatıyor: ödendiği Shopier tarafında
    görünen her sipariş bizim kayda yazılıyor.

    Webhook yerine bunu tek başına kullanmıyoruz — müşteri ödedikten
    saniyeler sonra faturasının kapandığını görmeli, elle
    çalıştırılan bir kontrolü beklememeli.
    """
    _yonetici_iste(request)

    if not shopier.hazir_mi():
        raise HTTPException(status_code=503, detail="Shopier bağlı değil")

    siparisler = await shopier.siparisleri_getir(limit=50)
    islenen = 0
    for siparis in siparisler:
        if not isinstance(siparis, dict):
            continue
        _kayit, yeni = await _odemeyi_isle(db, siparis)
        if yeni:
            islenen += 1

    return {"bakilan": len(siparisler), "islenen": islenen}


# --------------------------------------------------------------------------
# Açık uçlar — müşterinin ödeme sayfası ve sağlayıcı geri bildirimi
# --------------------------------------------------------------------------
acik_router = APIRouter(prefix="/api/v1/odeme", tags=["odeme"])


@acik_router.get("/{jeton}", response_model=AcikOdemeYaniti)
async def odeme_ozeti(jeton: str, db: AsyncSession = _Depends(get_db)):
    """Ödeme sayfasının gösterdiği özet. Kişisel bilgi dönmüyor."""
    sonuc = await db.execute(select(Payments).where(Payments.jeton == jeton))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")

    son_tarih = None
    if kayit.invoice_id:
        fatura = await db.execute(select(Invoices).where(Invoices.id == kayit.invoice_id))
        fatura = fatura.scalar_one_or_none()
        if fatura is not None:
            son_tarih = fatura.due_date
            aciklama = fatura.description
        else:
            aciklama = None
    else:
        aciklama = None

    return AcikOdemeYaniti(
        jeton=kayit.jeton,
        invoice_no=kayit.invoice_no,
        aciklama=aciklama,
        tutar=kayit.tutar,
        para_birimi=kayit.para_birimi,
        son_tarih=son_tarih,
        durum=kayit.durum,
        saglayici_hazir=_saglayici_hazir_mi(),
    )


@acik_router.post("/{jeton}/shopier", response_model=ShopierBaglantisi)
async def shopier_baglantisi(jeton: str, db: AsyncSession = _Depends(get_db)):
    """Bu fatura için Shopier ödeme linkini üretir (ya da mevcut olanı verir).

    Shopier'in yeni API'sinde "şu tutarı tahsil et" diyen bir uç yok;
    onun yerine faturaya özel gizli bir ürün açılıyor ve müşteri o
    ürünün linkine gönderiliyor. Ürün `customListing` olduğu için
    dükkânın vitrininde görünmüyor, stoğu 1 olduğu için ikinci kez
    ödenemiyor.

    Link bir kez üretilip saklanıyor. Her istekte yeni ürün açsaydık,
    sayfayı iki kez açan müşteri için Shopier'de iki ürün birikir ve
    hangisinin ödendiğini takip etmek imkânsızlaşırdı.
    """
    if not shopier.hazir_mi():
        raise HTTPException(status_code=503, detail="Kart ödemesi şu an kapalı")

    sonuc = await db.execute(select(Payments).where(Payments.jeton == jeton))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    if kayit.durum == "odendi":
        raise HTTPException(status_code=409, detail="Bu fatura zaten ödendi")
    if kayit.durum == "iptal":
        raise HTTPException(status_code=409, detail="Bu bağlantı kapatıldı")
    if not kayit.tutar or kayit.tutar <= 0:
        raise HTTPException(status_code=400, detail="Tutar geçersiz")

    if kayit.shopier_url and kayit.shopier_urun_id:
        return ShopierBaglantisi(adres=kayit.shopier_url)

    baslik = f"Hizmet bedeli — {kayit.invoice_no or kayit.jeton}"
    aciklama = (
        "By Mehmet KURU Dev hizmet bedeli. "
        f"Fatura: {kayit.invoice_no or '—'}. "
        "Bu sayfa yalnızca ilgili müşteri içindir."
    )
    try:
        urun = await shopier.odeme_urunu_olustur(
            baslik=baslik,
            aciklama=aciklama,
            tutar=float(kayit.tutar),
            para_birimi=kayit.para_birimi or "TRY",
        )
    except shopier.ShopierHatasi as hata:
        logger.warning("Shopier urunu acilamadi (jeton=%s): %s", jeton[:20], hata)
        raise HTTPException(status_code=502, detail=str(hata))

    kayit.saglayici = "shopier"
    kayit.shopier_urun_id = urun["urun_id"]
    kayit.shopier_url = urun["adres"]
    await db.commit()

    logger.info("Shopier odeme linki uretildi: jeton=%s urun=%s", jeton[:20], urun["urun_id"])
    return ShopierBaglantisi(adres=urun["adres"])


@acik_router.post("/{jeton}/lemon", response_model=LemonBaglantisi)
async def lemon_baglantisi(jeton: str, db: AsyncSession = _Depends(get_db)):
    """Bu fatura için Lemon Squeezy ödeme sayfası açar.

    Shopier'den iki farkı var. Birincisi: fatura başına ürün AÇILMIYOR,
    panelde bir kez açılmış varyantın tutarı eziliyor — dükkanda ölü
    ürün birikmiyor. İkincisi: ödeme bitince müşteri `/ode/<jeton>`
    sayfasına geri dönüyor, "para gitti ama siteye dönmedim" sorunu
    ortadan kalkıyor.

    Adres bir kez üretilip saklanıyor: sayfayı iki kez açan müşteri için
    iki ayrı ödeme sayfası açılsaydı hangisinin ödendiğini takip etmek
    zorlaşırdı.
    """
    if not lemonsqueezy.hazir_mi():
        raise HTTPException(status_code=503, detail="Bu ödeme yolu şu an kapalı")

    sonuc = await db.execute(select(Payments).where(Payments.jeton == jeton))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    if kayit.durum == "odendi":
        raise HTTPException(status_code=409, detail="Bu fatura zaten ödendi")
    if kayit.durum == "iptal":
        raise HTTPException(status_code=409, detail="Bu bağlantı kapatıldı")
    if not kayit.tutar or kayit.tutar <= 0:
        raise HTTPException(status_code=400, detail="Tutar geçersiz")

    if kayit.lemon_url:
        return LemonBaglantisi(adres=kayit.lemon_url)

    baslik = f"Hizmet bedeli — {kayit.invoice_no or kayit.jeton}"
    aciklama = (
        "By Mehmet KURU Dev hizmet bedeli. "
        f"Fatura: {kayit.invoice_no or '—'}."
    )
    try:
        sayfa = await lemonsqueezy.odeme_baglantisi_ac(
            jeton=kayit.jeton,
            baslik=baslik,
            aciklama=aciklama,
            tutar=float(kayit.tutar),
            para_birimi=kayit.para_birimi or "TRY",
            eposta=kayit.client_email,
            donus_adresi=f"{_site_adresi()}/ode/{kayit.jeton}",
        )
    except lemonsqueezy.LemonHatasi as hata:
        logger.warning("Lemon odeme sayfasi acilamadi (jeton=%s): %s", jeton[:20], hata)
        raise HTTPException(status_code=502, detail=str(hata))

    kayit.saglayici = "lemonsqueezy"
    kayit.lemon_checkout_id = sayfa.get("checkout_id") or None
    kayit.lemon_url = sayfa["adres"]
    await db.commit()

    logger.info("Lemon odeme sayfasi uretildi: jeton=%s", jeton[:20])
    return LemonBaglantisi(adres=sayfa["adres"])


async def _lemon_odemesini_isle(
    db: AsyncSession, jeton: str, siparis: Dict[str, Any]
) -> Tuple[Optional[int], bool]:
    """Ödenmiş bir Lemon Squeezy siparişini bizim kaydımıza yazar.

    Eşleştirme jetonla: ödeme sayfasını açarken `checkout_data.custom`
    içine kendi jetonumuzu koymuştuk, bildirimde geri geliyor. Tutar ya
    da e-posta ile eşleştirmek yanlış faturayı kapatabilirdi.
    """
    if not lemonsqueezy.odenmis_mi(siparis):
        return None, False

    sonuc = await db.execute(select(Payments).where(Payments.jeton == jeton))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        logger.info("Lemon siparisi bizim kayitla eslesmedi: jeton=%s", jeton[:20])
        return None, False

    if kayit.durum == "odendi":
        # Aynı bildirim iki kez geldi. Kayıt bizim ama değişen bir şey yok.
        return kayit.id, False

    kayit.durum = "odendi"
    kayit.saglayici = "lemonsqueezy"
    kayit.saglayici_ref = str(siparis.get("id") or "") or kayit.saglayici_ref
    kayit.odendi_at = datetime.now()
    kayit.hata_mesaji = None
    kayit.ham_yanit = json.dumps(siparis, ensure_ascii=False)[:4000]

    await _faturayi_kapat(db, kayit)
    await _musteri_sitesini_ac(db, kayit)
    await db.commit()

    logger.info("Lemon odemesi islendi: kayit=%s siparis=%s", kayit.id, siparis.get("id"))
    return kayit.id, True


@acik_router.post("/lemon/webhook")
async def lemon_webhook(request: Request, db: AsyncSession = _Depends(get_db)):
    """Lemon Squeezy'nin sipariş bildirimi.

    Gelen gövdeye GÜVENİLMİYOR: imza doğrulandıktan sonra bile sipariş
    Lemon Squeezy'den kendi anahtarımızla yeniden çekiliyor ve karar
    oradan veriliyor.

    Shopier ucundan bir farkı var: orada imza sırrı tanımlı değilse
    gövdeye güvenmeyip siparişi yine de çekebiliyorduk. Burada imza
    ZORUNLU — sır tanımlı değilse istek reddediliyor. Çünkü eşleştirme
    jetonu gövdeden geliyor; imzasız bir gövde, adresi bilen birinin
    istediği faturayı "ödendi" göstermesi demek olurdu.
    """
    ham = await request.body()
    imza = request.headers.get("X-Signature") or ""
    olay = request.headers.get("X-Event-Name") or ""

    if not lemonsqueezy.webhook_imzasi_gecerli_mi(ham, imza):
        logger.warning("Lemon webhook imzasi gecersiz (olay=%s)", olay)
        raise HTTPException(status_code=401, detail="İmza doğrulanamadı")

    try:
        govde = json.loads(ham.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Gövde okunamadı")

    if olay and olay != lemonsqueezy.ODEME_OLAYI:
        # Abonelik olayları da geliyor; tek seferlik satışta
        # `order_created` her durumda gönderiliyor, gerisini yok sayıyoruz.
        return {"ok": True, "islendi": False, "neden": f"ilgisiz olay: {olay}"}

    jeton = lemonsqueezy.govdedeki_jeton(govde)
    siparis_id = lemonsqueezy.govdedeki_siparis_id(govde)
    if not jeton or not siparis_id:
        return {"ok": True, "islendi": False, "neden": "jeton ya da siparis yok"}

    try:
        siparis = await lemonsqueezy.siparis_getir(siparis_id)
    except lemonsqueezy.LemonHatasi as hata:
        logger.warning("Lemon siparisi okunamadi (%s): %s", siparis_id, hata)
        return {"ok": True, "islendi": False, "neden": "siparis okunamadi"}

    kayit_id, _ = await _lemon_odemesini_isle(db, jeton, siparis)
    return {"ok": True, "islendi": kayit_id is not None}


async def _odemeyi_isle(
    db: AsyncSession, siparis: Dict[str, Any]
) -> Tuple[Optional[int], bool]:
    """Ödenmiş bir Shopier siparişini bizim kaydımıza yazar.

    `(kayit_id, yeni_mi)` döndürüyor. İki ayrı soru bunlar: webhook
    için "bu sipariş bize ait mi" yeterli (aynı bildirim iki kez
    gelirse yine başarı), mutabakat içinse "bu sefer gerçekten bir şey
    değişti mi" gerekiyor — yoksa her mutabakat aynı eski ödemeleri
    yeniden saymış gibi rapor ederdi.

    Eşleştirme sipariş satırlarındaki `productId` ile yapılıyor: o
    ürün tek bir fatura için açılmıştı. Tutar ya da e-posta ile
    eşleştirmek yanlış faturayı kapatabilirdi — aynı tutarda iki
    fatura olabilir, müşteri başka bir adresle ödeyebilir.
    """
    if not shopier.odenmis_mi(siparis):
        return None, False

    kimlikler = shopier.siparisin_urun_kimlikleri(siparis)
    if not kimlikler:
        return None, False

    sonuc = await db.execute(
        select(Payments).where(Payments.shopier_urun_id.in_(kimlikler))
    )
    kayit = sonuc.scalars().first()
    if kayit is None:
        logger.info("Shopier siparisi bizim kayitla eslesmedi: %s", siparis.get("id"))
        return None, False

    if kayit.durum == "odendi":
        # Aynı bildirim iki kez geldi ya da mutabakat eski bir ödemeye
        # denk geldi. Kayıt bizim, ama bu sefer değişen bir şey yok.
        return kayit.id, False

    kayit.durum = "odendi"
    kayit.saglayici = "shopier"
    kayit.saglayici_ref = str(siparis.get("id") or "") or kayit.saglayici_ref
    kayit.odendi_at = datetime.now()
    kayit.hata_mesaji = None
    kayit.ham_yanit = json.dumps(siparis, ensure_ascii=False)[:4000]

    await _faturayi_kapat(db, kayit)
    # Kart tahsilatında da aynı kural: ödeme düştü, müşteri sitesi
    # kaydı ve düğme jetonu kendiliğinden açılıyor.
    await _musteri_sitesini_ac(db, kayit)
    await db.commit()

    # Ödendikten sonra link ölmeli; olmazsa iş durmuyor, tahsilat alındı.
    if kayit.shopier_urun_id:
        await shopier.odeme_urununu_kapat(kayit.shopier_urun_id)

    logger.info("Shopier odemesi islendi: kayit=%s siparis=%s", kayit.id, siparis.get("id"))
    return kayit.id, True


@acik_router.post("/shopier/webhook")
async def shopier_webhook(request: Request, db: AsyncSession = _Depends(get_db)):
    """Shopier'in sipariş bildirimi.

    Gelen gövdeye GÜVENİLMİYOR. Bildirim yalnızca bir tetikleyici
    sayılıyor; sipariş Shopier'den kendi anahtarımızla yeniden
    çekiliyor ve karar oradan veriliyor. Böylece adresi bilen birinin
    uydurma bir gövdeyle fatura kapatması mümkün değil — imza sırrı
    tanımlı olmasa bile.

    İmza tanımlıysa ayrıca doğrulanıyor; geçmezse istek hiç
    işlenmiyor. İkisi birbirinin yedeği.
    """
    ham = await request.body()
    olay = (request.headers.get("Shopier-Event") or "").strip()
    imza = (request.headers.get("Shopier-Signature") or "").strip()

    sir = await _webhook_sirri(db)
    if sir and not shopier.webhook_imzasi_gecerli_mi_sirla(ham, imza, sir):
        logger.warning("Shopier webhook imzasi gecersiz (olay=%s)", olay[:40])
        raise HTTPException(status_code=400, detail="İmza doğrulanamadı")

    if olay and not olay.startswith("order."):
        return {"ok": True, "islendi": False, "neden": "ilgisiz olay"}

    try:
        govde = json.loads(ham.decode("utf-8")) if ham else {}
    except (ValueError, UnicodeDecodeError):
        govde = {}

    siparis_id = str((govde or {}).get("id") or "").strip()
    if not siparis_id:
        return {"ok": True, "islendi": False, "neden": "siparis numarasi yok"}

    # Kritik kısım: bildirimdeki alanlar değil, Shopier'den çekilen
    # siparişin kendisi kullanılıyor.
    siparis = await shopier.siparis_getir(siparis_id)
    if siparis is None:
        logger.warning("Shopier siparisi dogrulanamadi: %s", siparis_id)
        return {"ok": True, "islendi": False, "neden": "siparis okunamadi"}

    kayit_id, _yeni = await _odemeyi_isle(db, siparis)
    return {"ok": True, "islendi": kayit_id is not None}


@acik_router.post("/webhook/{saglayici}")
async def saglayici_bildirimi(saglayici: str, request: Request):
    """Sağlayıcının ödeme sonucu bildirimi.

    Şu an hiçbir sağlayıcı bağlı değil. Uç, imzayı doğrulayan kod
    yazılana kadar **hiçbir kaydı değiştirmiyor** — doğrulanmamış bir
    çağrının faturayı ödendi işaretlemesi, adresi bilen herkesin borcu
    silebilmesi demek olurdu.

    Gelen gövde yine de kayda geçiyor: entegrasyonu yazarken
    sağlayıcının gerçekte ne gönderdiğini görmek gerekiyor.
    """
    try:
        govde = await request.body()
        logger.info(
            "Odeme bildirimi alindi ama islenmedi (saglayici=%s, %d bayt)",
            saglayici,
            len(govde or b""),
        )
    except Exception:  # pragma: no cover - gövde okunamazsa da uç ayakta kalsın
        logger.warning("Odeme bildiriminin govdesi okunamadi (saglayici=%s)", saglayici)

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ödeme sağlayıcısı henüz kurulmadı",
    )


# `include_routers_from_package` liste de kabul ediyor: biri yönetici
# bekçisinin arkasında, diğeri müşteriye açık.
router = (yonetici_router, acik_router)
