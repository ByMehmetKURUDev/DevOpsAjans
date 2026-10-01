"""Faz 3T — fatura geliştirmeleri: bakiye, kısmi ödeme, iade, tekrarlayan, vade hatırlatma, yaşlandırma.

Var olanın üstüne
-----------------
* Fatura `invoices`, tahsilat `payments` (ikinci bir ödeme tablosu AÇILMADI:
  `payments` baştan "kısmi ödeme, iade, başarısız deneme" için ayrı tutulmuştu;
  elle girilen ödemenin tarihi/notu/dekontu yeni sütunlar). Kart tahsilatı
  (Shopier, Lemon Squeezy) ve `/ode/<jeton>` bağlantısı olduğu gibi çalışıyor;
  bu modül yalnız faturanın durumunu ödemelerden yeniden hesaplıyor.
* Kalemli fatura: `amount` sunucunun hesapladığı genel toplam
  (services/belge_hesap.py). Eski tek tutarlı faturalarda `kalemler` boş;
  her hesap yine `amount` üzerinden.

Bakiye
------
    net borç = tutar − iade faturaları toplamı
    ödenen   = Σ ödendi − Σ geri ödeme (payments.durum = "iade")
    kalan    = net borç − ödenen         (eksi ise müşteriye iade edilecek)

Durum (yalnız ödeme/iade olaylarında yeniden hesaplanır; yöneticinin elle
yazdığı durum bunların dışında değişmez):
    net ≤ 0 ve ödeme yok → cancelled  ·  kalan ≤ 0 → paid
    0 < ödenen < net      → kismi_odendi
    ödeme yok             → (paid/kismi_odendi/cancelled idiyse) unpaid, yoksa dokunulmaz

Zamanlı görevler (services/zamanli.py): tekrarlayan fatura üretimi (dönem
kilidi benzersiz → aynı dönem iki kez kesilmez), vade hatırlatması (vade +1/+7/
+14 gün, eşik başına bir kez → `hatirlatma_izleri` benzersiz).
"""

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.invoices import Invoices
from models.payments import Payments
from models.sozlesmeler import HatirlatmaIzleri, TekrarlayanFaturaKayitlari
from services.belge_hesap import HesapHatasi, belge_hesapla, kayitli_kalemler, kurus, ondalik
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

EPS = Decimal("0.005")
SIFIR = Decimal("0")

#: Elle girilen ödemenin yöntemi → `payments.saglayici`.
YONTEMLER: Dict[str, str] = {
    "havale": "havale",
    "eft": "eft",
    "nakit": "elden",
    "elden": "elden",
    "shopier": "shopier",
    "lemon": "lemonsqueezy",
    "lemonsqueezy": "lemonsqueezy",
    "diger": "diger",
}
#: Kapalı (bakiye/yaşlandırma/hatırlatma dışı) durumlar.
KAPALI_DURUMLAR = ("paid", "cancelled", "iade", "draft", "taslak")
VADE_ESIKLERI = (1, 7, 14)
VARSAYILAN_VADE_GUN = 7
DEKONT_KLASORU = "Dekontlar"
DEKONT_TURLERI = ("pdf", "png", "jpg", "jpeg", "webp")
EN_COK_DONEM = 3  # tur başına abonelik başına en çok bu kadar geriye dönük dönem
MUSTERI_FATURA_BAGLANTISI = "/client?sekme=invoices"


class FaturaHatasi(Exception):
    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def D(deger: Any) -> Decimal:
    if deger is None or deger == "":
        return SIFIR
    if isinstance(deger, Decimal):
        return kurus(deger)
    return kurus(Decimal(str(deger)))


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def tr_bugun() -> date:
    from services.site_izleme import tr_gunu

    return tr_gunu(simdi())


def tarih_coz(metin: Optional[str]) -> Optional[date]:
    if not metin:
        return None
    try:
        return date.fromisoformat(str(metin).strip()[:10])
    except ValueError:
        return None


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def yeni_fatura_no(onek: str = "FTR") -> str:
    return f"{onek}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:5].upper()}"


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------
async def fatura_getir(db: AsyncSession, fatura_id: int) -> Invoices:
    fatura = (await db.execute(select(Invoices).where(Invoices.id == fatura_id))).scalar_one_or_none()
    if fatura is None:
        raise FaturaHatasi(404, "fatura_yok")
    return fatura


async def odeme_satirlari(db: AsyncSession, fatura_id: int) -> List[Payments]:
    return list(
        (await db.execute(select(Payments).where(Payments.invoice_id == fatura_id).order_by(Payments.id))).scalars().all()
    )


async def iade_faturalari(db: AsyncSession, fatura_id: int) -> List[Invoices]:
    return list(
        (
            await db.execute(
                select(Invoices)
                .where(Invoices.bagli_fatura_id == fatura_id, Invoices.tur == "iade")
                .order_by(Invoices.id)
            )
        ).scalars().all()
    )


@dataclass
class Bakiye:
    toplam: Decimal
    iade_toplam: Decimal
    net: Decimal
    odenen: Decimal
    kalan: Decimal

    def sozluk(self) -> Dict[str, Any]:
        return {
            "toplam": float(self.toplam),
            "iade_toplam": float(self.iade_toplam),
            "net": float(self.net),
            "odenen": float(self.odenen),
            "kalan": float(self.kalan),
            # Eksi kalan: müşteriye geri ödenecek tutar.
            "fazla": float(-self.kalan) if self.kalan < -EPS else 0.0,
        }


def bakiye_hesapla(fatura: Invoices, odemeler: Iterable[Payments], iadeler: Iterable[Invoices]) -> Bakiye:
    toplam = D(fatura.amount)
    iade_toplam = sum((abs(D(i.amount)) for i in iadeler), SIFIR)
    odenen = SIFIR
    for o in odemeler:
        if o.durum == "odendi":
            odenen += D(o.tutar)
        elif o.durum == "iade":
            odenen -= D(o.tutar)
    net = toplam - iade_toplam
    return Bakiye(toplam=toplam, iade_toplam=iade_toplam, net=net, odenen=odenen, kalan=net - odenen)


async def bakiye(db: AsyncSession, fatura: Invoices) -> Bakiye:
    if fatura.tur == "iade":
        return Bakiye(D(fatura.amount), SIFIR, D(fatura.amount), SIFIR, SIFIR)
    return bakiye_hesapla(fatura, await odeme_satirlari(db, fatura.id), await iade_faturalari(db, fatura.id))


def yeni_durum(fatura: Invoices, b: Bakiye) -> Optional[str]:
    """Ödeme/iade olayından sonra olması gereken durum; None = dokunma."""
    if fatura.tur == "iade":
        return "iade"
    if b.net <= EPS:
        return "paid" if b.odenen > EPS else "cancelled"
    if b.kalan <= EPS:
        return "paid"
    if b.odenen > EPS:
        return "kismi_odendi"
    if (fatura.status or "") in ("paid", "kismi_odendi", "cancelled"):
        return "unpaid"
    return None


async def durumu_guncelle(db: AsyncSession, fatura: Invoices) -> Tuple[str, Bakiye]:
    """Faturanın durumunu ödemelerden/iadelerden yeniden hesaplar (commit ETMEZ)."""
    await db.flush()
    b = await bakiye(db, fatura)
    durum = yeni_durum(fatura, b)
    if durum and durum != fatura.status:
        fatura.status = durum
    return fatura.status or "", b


async def bekleyen_baglantiyi_esitle(db: AsyncSession, fatura: Invoices, b: Bakiye) -> None:
    """Bekleyen `/ode/<jeton>` bağlantısını kalan bakiyeye uydurur (commit ETMEZ).

    * Kalan yoksa bağlantı iptal (ödenmiş faturayı istemeye devam etmesin).
    * Sağlayıcıda henüz sayfa açılmamışsa tutar kalan bakiyeye çekiliyor.
    * Shopier ürünü / Lemon sayfası eski tutarla açılmışsa bağlantı iptal:
      yeni bağlantı kalan tutarla üretilir (sağlayıcıdaki tutar değişmiyor).
    """
    bekleyenler = (
        await db.execute(select(Payments).where(Payments.invoice_id == fatura.id, Payments.durum == "bekliyor"))
    ).scalars().all()
    for p in bekleyenler:
        if b.kalan <= EPS:
            p.durum = "iptal"
            p.hata_mesaji = "Fatura kapandı"
        elif D(p.tutar) != b.kalan:
            if p.shopier_url or p.lemon_url:
                p.durum = "iptal"
                p.hata_mesaji = "Kalan bakiye değişti; yeni bağlantı üretilmeli"
            else:
                p.tutar = float(b.kalan)


async def baglanti_hazirla(db: AsyncSession, fatura: Invoices) -> Payments:
    """Faturanın bekleyen ödeme bağlantısı; yoksa kalan bakiyeyle açar (commit EDER)."""
    if fatura.tur == "iade" or (fatura.status or "") in ("paid", "cancelled", "iade"):
        raise FaturaHatasi(409, "fatura_kapali")
    if (fatura.status or "") in ("draft", "taslak"):
        # Faz 3Z: taslak fatura henüz kesilmedi — ödeme istenmez.
        raise FaturaHatasi(409, "fatura_taslak")
    b = await bakiye(db, fatura)
    if b.kalan <= EPS:
        raise FaturaHatasi(409, "fatura_kapali")
    await bekleyen_baglantiyi_esitle(db, fatura, b)
    await db.flush()
    mevcut = (
        await db.execute(
            select(Payments)
            .where(Payments.invoice_id == fatura.id, Payments.durum == "bekliyor")
            .order_by(Payments.id.desc())
        )
    ).scalars().first()
    if mevcut is None:
        mevcut = Payments(
            invoice_id=fatura.id,
            invoice_no=fatura.invoice_no,
            client_email=fatura.client_email,
            jeton=secrets.token_urlsafe(9),
            tutar=float(b.kalan),
            para_birimi=fatura.currency or "TRY",
            durum="bekliyor",
        )
        db.add(mevcut)
    await db.commit()
    await db.refresh(mevcut)
    return mevcut


# ---------------------------------------------------------------------------
# Kısmi ödeme ve iade
# ---------------------------------------------------------------------------
async def odeme_ekle(
    db: AsyncSession,
    fatura: Invoices,
    *,
    tutar: Any,
    yontem: str,
    tarih: Optional[str] = None,
    notu: Optional[str] = None,
    dekont_dosya_id: Optional[int] = None,
    ekleyen: Optional[str] = None,
    geri_odeme: bool = False,
) -> Tuple[Payments, Optional[Dict[str, Any]]]:
    """Elle ödeme (ya da geri ödeme) kaydı. Commit ETMEZ; (satır, kredi özeti) döner."""
    from services import denetim, kredi

    if fatura.tur == "iade":
        raise FaturaHatasi(409, "iade_faturasina_odeme")
    saglayici = YONTEMLER.get((yontem or "").strip().lower())
    if saglayici is None:
        raise FaturaHatasi(400, "yontem_gecersiz")
    try:
        miktar = kurus(ondalik(tutar))
    except HesapHatasi:
        raise FaturaHatasi(400, "tutar_gecersiz")
    if miktar <= 0:
        raise FaturaHatasi(400, "tutar_gecersiz")
    gun = tarih_coz(tarih) if tarih else tr_bugun()
    if tarih and gun is None:
        raise FaturaHatasi(400, "tarih_gecersiz")
    if gun and gun > tr_bugun() + timedelta(days=1):
        raise FaturaHatasi(400, "tarih_gelecekte")

    b = await bakiye(db, fatura)
    if geri_odeme:
        if miktar > (-b.kalan) + EPS:
            raise FaturaHatasi(409, "geri_odeme_fazla", azami=float(max(-b.kalan, SIFIR)))
    elif miktar > b.kalan + EPS:
        raise FaturaHatasi(409, "tutar_kalandan_fazla", kalan=float(max(b.kalan, SIFIR)))

    satir = Payments(
        invoice_id=fatura.id,
        invoice_no=fatura.invoice_no,
        client_email=fatura.client_email,
        saglayici=saglayici,
        tutar=float(miktar),
        para_birimi=fatura.currency or "TRY",
        durum="iade" if geri_odeme else "odendi",
        odendi_at=simdi(),
        odeme_tarihi=(gun or tr_bugun()).isoformat(),
        notu=(notu or "").strip()[:1000] or None,
        dekont_dosya_id=dekont_dosya_id,
        ekleyen_eposta=eposta_duzelt(ekleyen) or None,
    )
    db.add(satir)
    durum, b = await durumu_guncelle(db, fatura)
    await bekleyen_baglantiyi_esitle(db, fatura, b)
    kredi_ozeti = None
    if durum == "paid" and not geri_odeme:
        kredi_ozeti = await kredi.odeme_kredilerini_yukle(db, fatura.id)
        try:
            from services.musteri_sitesi import siteyi_hazirla

            if fatura.client_email:
                await siteyi_hazirla(db, client_email=fatura.client_email, ad=(fatura.invoice_no or "").strip() or None,
                                     kaynak="odeme")
        except Exception:  # noqa: BLE001 - site kaydı açılamasa da tahsilat kaydedilsin
            logger.exception("Müşteri sitesi otomatik açılamadı: fatura=%s", fatura.id)
    await denetim.denetim_yaz(
        db,
        islem="odeme",
        tablo="invoices",
        kayit_id=fatura.id,
        ozet=f"{fatura.invoice_no}: {'geri ödeme' if geri_odeme else 'ödeme'} {miktar} {fatura.currency or 'TRY'} ({saglayici})",
        once=None,
        sonra={"odeme_id": satir.id, "tutar": float(miktar), "yontem": saglayici, "durum": durum, "kalan": float(b.kalan)},
    )
    return satir, kredi_ozeti


async def odeme_sil(db: AsyncSession, satir: Payments) -> Optional[Invoices]:
    """Ödeme satırını siler, faturanın durumunu yeniden hesaplar (commit ETMEZ)."""
    from services import denetim

    fatura = None
    if satir.invoice_id:
        fatura = (await db.execute(select(Invoices).where(Invoices.id == satir.invoice_id))).scalar_one_or_none()
    once = {"odeme_id": satir.id, "tutar": satir.tutar, "yontem": satir.saglayici, "durum": satir.durum}
    dekont_id = satir.dekont_dosya_id
    await db.delete(satir)
    await db.flush()
    if dekont_id:
        from models.dosyalar import Dosyalar

        dosya = (await db.execute(select(Dosyalar).where(Dosyalar.id == dekont_id))).scalar_one_or_none()
        if dosya is not None:
            # Dosya çöp kutusuna düşüyor (içerik saklama süresi dolunca silinir).
            await db.delete(dosya)
    if fatura is not None:
        durum, b = await durumu_guncelle(db, fatura)
        await bekleyen_baglantiyi_esitle(db, fatura, b)
        await denetim.denetim_yaz(
            db, islem="odeme", tablo="invoices", kayit_id=fatura.id,
            ozet=f"{fatura.invoice_no}: ödeme silindi ({once['tutar']} {fatura.currency or 'TRY'})",
            once=once, sonra={"durum": durum, "kalan": float(b.kalan)},
        )
    return fatura


async def iade_faturasi_kes(
    db: AsyncSession,
    fatura: Invoices,
    *,
    tutar: Any = None,
    kalemler: Optional[List[Dict[str, Any]]] = None,
    neden: Optional[str] = None,
    ekleyen: Optional[str] = None,
) -> Invoices:
    """İade (alacak) faturası: eksi tutarlı, asıl faturaya bağlı (commit ETMEZ).

    `kalemler` verilirse KDV'li iade (adetler eksiye çevrilir); yoksa `tutar`
    (KDV dâhil tek satır). İkisi de yoksa net borcun tamamı (tam iade / iptal).
    """
    from services import denetim

    if fatura.tur == "iade":
        raise FaturaHatasi(409, "iade_faturasinin_iadesi")
    b = await bakiye(db, fatura)
    if b.net <= EPS:
        raise FaturaHatasi(409, "iade_edilecek_tutar_yok")
    neden_temiz = (neden or "").strip()[:500] or None
    ozet_kalemler = None
    ara = kdv = None
    if kalemler:
        ters = []
        for k in kalemler:
            if not isinstance(k, dict):
                raise FaturaHatasi(400, "kalemler_gecersiz")
            try:
                adet = ondalik(k.get("adet", 1), "adet_gecersiz")
            except HesapHatasi as h:
                raise FaturaHatasi(400, h.kod)
            ters.append({**k, "adet": float(-abs(adet))})
        try:
            belge = belge_hesapla(ters, eksi_olabilir=True)
        except HesapHatasi as h:
            raise FaturaHatasi(400, h.kod, **({"sira": h.sira} if h.sira is not None else {}))
        miktar = -belge.genel_toplam
        ozet_kalemler = json.dumps(belge.kalem_listesi(), ensure_ascii=False)
        ara, kdv = float(belge.ara_toplam), float(belge.kdv_toplam)
    elif tutar is not None:
        try:
            miktar = kurus(ondalik(tutar))
        except HesapHatasi:
            raise FaturaHatasi(400, "tutar_gecersiz")
    else:
        miktar = b.net
    if miktar <= 0:
        raise FaturaHatasi(400, "tutar_gecersiz")
    if miktar > b.net + EPS:
        raise FaturaHatasi(409, "iade_tutari_fazla", azami=float(b.net))

    sira = len(await iade_faturalari(db, fatura.id)) + 1
    iade = Invoices(
        invoice_no=f"{fatura.invoice_no}-IADE{'' if sira == 1 else sira}"[:60],
        client_name=fatura.client_name,
        client_email=fatura.client_email,
        description=neden_temiz or f"İade — {fatura.invoice_no}",
        amount=float(-miktar),
        currency=fatura.currency or "TRY",
        status="iade",
        issue_date=tr_bugun().isoformat(),
        kalemler=ozet_kalemler,
        ara_toplam=ara,
        kdv_toplam=kdv,
        tur="iade",
        bagli_fatura_id=fatura.id,
        notlar=neden_temiz,
    )
    db.add(iade)
    await db.flush()
    durum, yeni_b = await durumu_guncelle(db, fatura)
    await bekleyen_baglantiyi_esitle(db, fatura, yeni_b)
    await denetim.denetim_yaz(
        db, islem="odeme", tablo="invoices", kayit_id=fatura.id,
        ozet=f"{fatura.invoice_no}: iade faturası {iade.invoice_no} ({miktar} {fatura.currency or 'TRY'})",
        sonra={"iade_fatura_id": iade.id, "tutar": float(miktar), "durum": durum, "ekleyen": eposta_duzelt(ekleyen)},
    )
    return iade


# ---------------------------------------------------------------------------
# Özet (ekran + PDF)
# ---------------------------------------------------------------------------
YONTEM_ETIKETI = {
    "havale": "Havale/EFT", "eft": "Havale/EFT", "elden": "Nakit", "shopier": "Shopier",
    "lemonsqueezy": "Lemon Squeezy", "diger": "Diğer", "iyzico": "iyzico", "paytr": "PayTR",
}


def _odeme_sozlugu(o: Payments, *, yonetici: bool) -> Dict[str, Any]:
    d = {
        "id": o.id,
        "tutar": float(D(o.tutar)),
        "para_birimi": o.para_birimi,
        "durum": o.durum,
        "saglayici": o.saglayici,
        "yontem_etiketi": YONTEM_ETIKETI.get(o.saglayici or "", o.saglayici or "—"),
        "odeme_tarihi": o.odeme_tarihi or (o.odendi_at.date().isoformat() if o.odendi_at else None),
        "odendi_at": o.odendi_at.isoformat() if o.odendi_at else None,
        "dekont_var": bool(o.dekont_dosya_id),
        "notu": o.notu,
    }
    if yonetici:
        d.update({"ekleyen_eposta": o.ekleyen_eposta, "saglayici_ref": o.saglayici_ref, "jeton": o.jeton,
                  "dekont_dosya_id": o.dekont_dosya_id})
    return d


async def fatura_ozeti(db: AsyncSession, fatura: Invoices, *, yonetici: bool = False) -> Dict[str, Any]:
    kalemler = kayitli_kalemler(fatura.kalemler)
    ozet = None
    if kalemler:
        try:
            ozet = belge_hesapla(kalemler, eksi_olabilir=fatura.tur == "iade").ozet()
        except HesapHatasi:
            ozet = None
    odemeler = await odeme_satirlari(db, fatura.id)
    iadeler = await iade_faturalari(db, fatura.id) if fatura.tur != "iade" else []
    b = bakiye_hesapla(fatura, odemeler, iadeler) if fatura.tur != "iade" else None
    bekleyen = next((o for o in reversed(odemeler) if o.durum == "bekliyor" and o.jeton), None)
    bagli_no = None
    if fatura.bagli_fatura_id:
        bagli = (await db.execute(select(Invoices.invoice_no).where(Invoices.id == fatura.bagli_fatura_id))).scalar()
        bagli_no = bagli
    teklif_no = None
    if fatura.teklif_id:
        from models.teklifler import Teklifler

        teklif_no = (await db.execute(select(Teklifler.no).where(Teklifler.id == fatura.teklif_id))).scalar()
    gorunur = [o for o in odemeler if o.durum in ("odendi", "iade")] if not yonetici else odemeler
    return {
        "id": fatura.id,
        "invoice_no": fatura.invoice_no,
        "client_name": fatura.client_name,
        "client_email": fatura.client_email,
        "description": fatura.description,
        "amount": float(D(fatura.amount)),
        "currency": fatura.currency or "TRY",
        "status": fatura.status,
        "issue_date": fatura.issue_date,
        "due_date": fatura.due_date,
        "tur": fatura.tur or "normal",
        "bagli_fatura_id": fatura.bagli_fatura_id,
        "bagli_fatura_no": bagli_no,
        "teklif_id": fatura.teklif_id,
        "teklif_no": teklif_no,
        "tekrarlayan_id": fatura.tekrarlayan_id,
        "donem": fatura.donem,
        "notlar": fatura.notlar,
        "kalemler": kalemler,
        "ozet": ozet,
        "bakiye": b.sozluk() if b else None,
        "odemeler": [_odeme_sozlugu(o, yonetici=yonetici) for o in gorunur],
        "iadeler": [
            {"id": i.id, "invoice_no": i.invoice_no, "amount": float(D(i.amount)), "issue_date": i.issue_date,
             "description": i.description}
            for i in iadeler
        ],
        "odeme_adresi": f"/ode/{bekleyen.jeton}" if bekleyen is not None else None,
        "created_at": fatura.created_at.isoformat() if fatura.created_at else None,
    }


AJANS_ANAHTARLARI = {
    "unvan": ("fatura_unvan",),
    "adres": ("fatura_adres", "contact_address"),
    "vergi_dairesi": ("fatura_vergi_dairesi",),
    "vergi_no": ("fatura_vergi_no",),
    "iban": ("fatura_iban",),
    "eposta": ("fatura_eposta", "contact_email"),
    "telefon": ("fatura_telefon", "contact_phone"),
}


async def ajans_bilgileri(db: AsyncSession) -> Dict[str, str]:
    """PDF başlığındaki ajans bilgileri (site ayarları). Boş olan gösterilmez."""
    from models.site_settings import Site_settings

    anahtarlar = {a for liste in AJANS_ANAHTARLARI.values() for a in liste}
    satirlar = (
        await db.execute(select(Site_settings).where(Site_settings.setting_key.in_(anahtarlar)))
    ).scalars().all()
    degerler = {s.setting_key: (s.setting_value or "").strip() for s in satirlar}
    sonuc: Dict[str, str] = {}
    for alan, adaylar in AJANS_ANAHTARLARI.items():
        for a in adaylar:
            if degerler.get(a):
                sonuc[alan] = degerler[a][:300]
                break
    return sonuc


async def fatura_pdf(db: AsyncSession, fatura: Invoices, dil: str = "tr") -> bytes:
    from services.pdf_belge import fatura_pdf as uret

    return uret(await fatura_ozeti(db, fatura), await ajans_bilgileri(db), dil)


# ---------------------------------------------------------------------------
# Alacak yaşlandırma
# ---------------------------------------------------------------------------
DILIMLER = ("vadesi_gelmemis", "g0_30", "g31_60", "g61_90", "g90_ustu")


def dilim(gecikme_gun: int) -> str:
    if gecikme_gun < 0:
        return "vadesi_gelmemis"
    if gecikme_gun <= 30:
        return "g0_30"
    if gecikme_gun <= 60:
        return "g31_60"
    if gecikme_gun <= 90:
        return "g61_90"
    return "g90_ustu"


async def yaslandirma(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Açık alacaklar müşteri × para birimi başına gecikme dilimlerinde.

    Gecikme = bugün − son ödeme günü (yoksa düzenleme günü). Vadesi henüz
    gelmemiş alacak ayrı sütunda. Farklı para birimleri toplanmıyor.
    """
    bugun = bugun or tr_bugun()
    faturalar = (
        await db.execute(
            select(Invoices).where(
                or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
                or_(Invoices.status.is_(None), Invoices.status.notin_(KAPALI_DURUMLAR)),
            )
        )
    ).scalars().all()
    if not faturalar:
        return {"bugun": bugun.isoformat(), "satirlar": [], "toplamlar": []}
    kimlikler = [f.id for f in faturalar]
    odemeler: Dict[int, List[Payments]] = {}
    for o in (await db.execute(select(Payments).where(Payments.invoice_id.in_(kimlikler)))).scalars().all():
        odemeler.setdefault(o.invoice_id, []).append(o)
    iadeler: Dict[int, List[Invoices]] = {}
    for i in (
        await db.execute(select(Invoices).where(Invoices.tur == "iade", Invoices.bagli_fatura_id.in_(kimlikler)))
    ).scalars().all():
        iadeler.setdefault(i.bagli_fatura_id, []).append(i)

    gruplar: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for f in faturalar:
        b = bakiye_hesapla(f, odemeler.get(f.id, []), iadeler.get(f.id, []))
        if b.kalan <= EPS:
            continue
        vade = tarih_coz(f.due_date) or tarih_coz(f.issue_date) or (f.created_at.date() if f.created_at else bugun)
        gecikme = (bugun - vade).days
        anahtar = (eposta_duzelt(f.client_email) or "—", (f.currency or "TRY").upper())
        g = gruplar.setdefault(anahtar, {
            "client_email": anahtar[0], "client_name": f.client_name, "para_birimi": anahtar[1],
            **{d: SIFIR for d in DILIMLER}, "toplam": SIFIR, "fatura_sayisi": 0, "en_eski_gecikme": None,
        })
        if not g.get("client_name") and f.client_name:
            g["client_name"] = f.client_name
        g[dilim(gecikme)] += b.kalan
        g["toplam"] += b.kalan
        g["fatura_sayisi"] += 1
        if gecikme >= 0 and (g["en_eski_gecikme"] is None or gecikme > g["en_eski_gecikme"]):
            g["en_eski_gecikme"] = gecikme

    def _cikis(g: Dict[str, Any]) -> Dict[str, Any]:
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in g.items()}

    satirlar = sorted(gruplar.values(), key=lambda g: (g["para_birimi"], -g["toplam"]))
    toplamlar: Dict[str, Dict[str, Decimal]] = {}
    for g in satirlar:
        t = toplamlar.setdefault(g["para_birimi"], {d: SIFIR for d in (*DILIMLER, "toplam")})
        for d in (*DILIMLER, "toplam"):
            t[d] += g[d]
    return {
        "bugun": bugun.isoformat(),
        "satirlar": [_cikis(g) for g in satirlar],
        "toplamlar": [{"para_birimi": pb, **{k: float(v) for k, v in t.items()}} for pb, t in sorted(toplamlar.items())],
    }


# ---------------------------------------------------------------------------
# Vade hatırlatması (zamanlı görev)
# ---------------------------------------------------------------------------
def esik_sec(gecikme: int, esikler: Tuple[int, ...], gonderilmis: Iterable[int]) -> Tuple[Optional[int], List[int]]:
    """Ulaşılan en büyük gönderilmemiş eşik + işaretlenecek (ulaşılmış) eşikler.

    Görev birkaç gün çalışmadıysa (sunucu uyudu) aradaki eşikler TEK
    bildirimde birleşiyor: +1 ve +7 aynı anda gelmişse yalnız +7 gider,
    ikisi de "gönderildi" sayılır.
    """
    gonderilmis = set(gonderilmis)
    ulasilan = [e for e in esikler if gecikme >= e]
    yeni = [e for e in ulasilan if e not in gonderilmis]
    if not yeni:
        return None, []
    return max(yeni), yeni


async def vade_hatirlatmalari(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Vadesi geçen açık faturalar için +1/+7/+14. günlerde, eşik başına BİR kez bildirim.

    Müşteriye (bildirim tercihine tabi: `fatura_gecikti` olayı, kişi kapatabilir)
    ve yöneticiye gidiyor. İlk hatırlatmada "unpaid/pending" fatura `overdue`
    oluyor. Kilit `hatirlatma_izleri` (tur=fatura_vade, ref=fatura, eşik) benzersiz.
    """
    from services.notify import admin_recipients, dispatch, render
    from services.pdf_belge import para

    bugun = bugun or tr_bugun()
    adaylar = (
        await db.execute(
            select(Invoices).where(
                or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
                or_(Invoices.status.is_(None), Invoices.status.notin_(KAPALI_DURUMLAR)),
                Invoices.due_date.isnot(None),
                Invoices.due_date != "",
            )
        )
    ).scalars().all()
    gonderilmis: Dict[int, set] = {}
    if adaylar:
        for iz in (
            await db.execute(
                select(HatirlatmaIzleri).where(
                    HatirlatmaIzleri.tur == "fatura_vade", HatirlatmaIzleri.ref_id.in_([f.id for f in adaylar])
                )
            )
        ).scalars().all():
            gonderilmis.setdefault(iz.ref_id, set()).add(iz.esik)

    gidecek: List[Tuple[Invoices, int, int, Bakiye]] = []
    for f in adaylar:
        vade = tarih_coz(f.due_date)
        if vade is None or not f.client_email:
            continue
        gecikme = (bugun - vade).days
        esik, isaretle = esik_sec(gecikme, VADE_ESIKLERI, gonderilmis.get(f.id, ()))
        if esik is None:
            continue
        b = await bakiye(db, f)
        if b.kalan <= EPS:
            continue
        try:
            async with db.begin_nested():
                for e in isaretle:
                    db.add(HatirlatmaIzleri(tur="fatura_vade", ref_id=f.id, esik=e))
                await db.flush()
        except IntegrityError:
            logger.info("Vade hatırlatması zaten yazılmış: fatura=%s", f.id)
            continue
        if (f.status or "") in ("unpaid", "pending", "", "sent"):
            f.status = "overdue"
        gidecek.append((f, esik, gecikme, b))
    await db.commit()

    if not gidecek:
        return {"aday": len(adaylar), "bildirim": 0}
    yoneticiler = await admin_recipients(db)
    gonderilen = 0
    for f, esik, gecikme, b in gidecek:
        tutar = para(b.kalan, f.currency or "TRY", "tr")
        tutar_en = para(b.kalan, f.currency or "TRY", "en")
        bekleyen = (
            await db.execute(
                select(Payments).where(Payments.invoice_id == f.id, Payments.durum == "bekliyor").order_by(Payments.id.desc())
            )
        ).scalars().first()
        odeme = f"\n\nÖdeme / Pay: /ode/{bekleyen.jeton}" if bekleyen is not None and bekleyen.jeton else ""
        try:
            baslik, govde = await render(
                db,
                "fatura_gecikti",
                f"Ödeme hatırlatması: {f.invoice_no} / Payment reminder: {f.invoice_no}",
                (
                    f"{f.invoice_no} numaralı faturanızın son ödeme tarihi {gecikme} gün önce geçti. "
                    f"Kalan tutar: {tutar}.{odeme}\n\n"
                    f"Invoice {f.invoice_no} is {gecikme} day(s) past due. Balance due: {tutar_en}."
                ),
                {"fatura_no": f.invoice_no, "gecikme": gecikme, "kalan": tutar, "esik": esik},
            )
            await dispatch(
                db, event_type="fatura_gecikti", title=baslik, body=govde,
                recipients=[{"email": eposta_duzelt(f.client_email), "role": "client"}],
                link=MUSTERI_FATURA_BAGLANTISI, ref_type="invoice", ref_id=f.id,
            )
            if yoneticiler:
                await dispatch(
                    db, event_type="fatura_gecikti", title=f"Vadesi geçti (+{esik}): {f.invoice_no} — {f.client_email}",
                    body=f"Kalan: {tutar}. Gecikme: {gecikme} gün.", recipients=yoneticiler,
                    link="/admin", ref_type="invoice", ref_id=f.id,
                )
            gonderilen += 1
        except Exception:  # noqa: BLE001 - bildirim görevi düşürmesin
            logger.exception("Vade hatırlatması gönderilemedi: fatura=%s", f.id)
    return {"aday": len(adaylar), "bildirim": gonderilen}


# ---------------------------------------------------------------------------
# Tekrarlayan fatura (abonelik = şablon)
# ---------------------------------------------------------------------------
def _ay_ekle(yil: int, ay: int, n: int) -> Tuple[int, int]:
    toplam = yil * 12 + (ay - 1) + n
    return toplam // 12, toplam % 12 + 1


def donemler(periyot: Optional[str], baslangic: Optional[str], son: Optional[str], bugun: date) -> List[str]:
    """Faturalanması gereken (henüz kesilmemiş) dönemler, eskiden yeniye.

    aylık: YYYY-MM (ayın 1'i geldiyse); yıllık: YYYY (başlangıç ayının 1'i geldiyse).
    `son` en son kesilen dönem: ondan sonrası. En çok EN_COK_DONEM tane.
    """
    try:
        yil, ay = (int(x) for x in (baslangic or "").split("-")[:2])
        date(yil, ay, 1)
    except (TypeError, ValueError):
        yil, ay = bugun.year, bugun.month
    sonuc: List[str] = []
    if (periyot or "aylik") == "yillik":
        y = yil
        while date(y, ay, 1) <= bugun:
            anahtar = f"{y:04d}"
            if not son or anahtar > son:
                sonuc.append(anahtar)
            y += 1
    else:
        y, a = yil, ay
        while date(y, a, 1) <= bugun:
            anahtar = f"{y:04d}-{a:02d}"
            if not son or anahtar > son:
                sonuc.append(anahtar)
            y, a = _ay_ekle(y, a, 1)
    return sonuc[-EN_COK_DONEM:]


def donem_etiketi(donem: str) -> str:
    if len(donem) == 4:
        return donem
    try:
        yil, ay = donem.split("-")
        return f"{ay}/{yil}"
    except ValueError:
        return donem


async def tekrarlayan_kes(db: AsyncSession, abonelik: Any, donem: str, bugun: date) -> Optional[Invoices]:
    """Aboneliğin bir dönemi için fatura keser; dönem zaten kesilmişse None (commit ETMEZ)."""
    kalemler = kayitli_kalemler(abonelik.fatura_kalemleri)
    if not kalemler and abonelik.tutar:
        kalemler = [{"aciklama": abonelik.baslik or abonelik.hizmet, "adet": 1, "birim_fiyat": abonelik.tutar,
                     "kdv_orani": 0, "indirim": 0}]
    if not kalemler:
        raise FaturaHatasi(409, "kalem_yok")
    etiket = donem_etiketi(donem)
    kalemler = [{**k, "aciklama": f"{k.get('aciklama')} ({etiket})"} for k in kalemler]
    belge = belge_hesapla(kalemler)
    try:
        async with db.begin_nested():
            kilit = TekrarlayanFaturaKayitlari(abonelik_id=abonelik.id, donem=donem)
            db.add(kilit)
            await db.flush()
    except IntegrityError:
        return None
    vade = bugun + timedelta(days=int(abonelik.vade_gun if abonelik.vade_gun is not None else VARSAYILAN_VADE_GUN))
    fatura = Invoices(
        invoice_no=yeni_fatura_no("TKR"),
        client_name=abonelik.client_name,
        client_email=eposta_duzelt(abonelik.client_email),
        description=f"{abonelik.baslik or abonelik.hizmet} — {etiket}",
        amount=float(belge.genel_toplam),
        currency=(abonelik.para_birimi or "TRY").upper(),
        status="unpaid",
        issue_date=bugun.isoformat(),
        due_date=vade.isoformat(),
        kalemler=json.dumps(belge.kalem_listesi(), ensure_ascii=False),
        ara_toplam=float(belge.ara_toplam),
        kdv_toplam=float(belge.kdv_toplam),
        tekrarlayan_id=abonelik.id,
        donem=donem,
    )
    db.add(fatura)
    await db.flush()
    kilit.invoice_id = fatura.id
    if not abonelik.son_fatura_donemi or donem > abonelik.son_fatura_donemi:
        abonelik.son_fatura_donemi = donem
    db.add(Payments(
        invoice_id=fatura.id, invoice_no=fatura.invoice_no, client_email=fatura.client_email,
        jeton=secrets.token_urlsafe(9), tutar=fatura.amount, para_birimi=fatura.currency, durum="bekliyor",
    ))
    await db.flush()
    return fatura


# ---------------------------------------------------------------------------
# Taslak fatura (Faz 3Z — zamandan faturaya aktarım)
# ---------------------------------------------------------------------------
#: Taslak durumu: müşteriye görünmüyor, bakiye/yaşlandırma/hatırlatma dışı.
TASLAK_DURUMLARI = ("draft", "taslak")
#: Bu durumlara geçen (ya da silinen) faturanın bağlı zaman kayıtları açılıyor.
IPTAL_DURUMLARI = ("cancelled", "iptal")
KALEM_ALANLARI = ("aciklama", "adet", "birim_fiyat", "kdv_orani", "indirim")


def _ham_kalemler(fatura: Invoices) -> List[Dict[str, Any]]:
    return [{k: v for k, v in kalem.items() if k in KALEM_ALANLARI} for kalem in kayitli_kalemler(fatura.kalemler)]


async def taslak_fatura_bul_ya_da_ac(
    db: AsyncSession,
    *,
    client_email: str,
    client_name: Optional[str],
    para_birimi: str,
    aciklama: str,
    fatura_id: Optional[int] = None,
    onek: str = "FTR",
) -> Tuple[Invoices, bool]:
    """Müşterinin bu para birimindeki açık TASLAK faturası; yoksa yenisi (commit ETMEZ).

    → (fatura, yeni_mi). `fatura_id` verilirse o fatura kullanılır (taslak,
    aynı müşteri ve para birimi olmalı; değilse 409). Tek tutarlı (kalemsiz,
    tutarı dolu) eski taslaklara satır eklenmiyor: kalem eklemek tutarı
    ezerdi — o durumda yeni taslak açılıyor.
    """
    eposta = eposta_duzelt(client_email)
    para = (para_birimi or "TRY").upper()
    if fatura_id:
        fatura = await fatura_getir(db, fatura_id)
        if (fatura.status or "") not in TASLAK_DURUMLARI:
            raise FaturaHatasi(409, "fatura_taslak_degil")
        if eposta_duzelt(fatura.client_email) != eposta:
            raise FaturaHatasi(409, "fatura_baska_musteri")
        if (fatura.currency or "TRY").upper() != para:
            raise FaturaHatasi(409, "para_birimi_uyusmuyor")
        if not fatura.kalemler and D(fatura.amount) != SIFIR:
            raise FaturaHatasi(409, "fatura_kalemsiz")
        return fatura, False
    adaylar = (
        await db.execute(
            select(Invoices)
            .where(Invoices.status.in_(TASLAK_DURUMLARI))
            .where(or_(Invoices.tur.is_(None), Invoices.tur == "normal"))
            .order_by(Invoices.id.desc())
        )
    ).scalars().all()
    for f in adaylar:
        if eposta_duzelt(f.client_email) != eposta or (f.currency or "TRY").upper() != para:
            continue
        if not f.kalemler and D(f.amount) != SIFIR:
            continue
        return f, False
    bugun = tr_bugun()
    fatura = Invoices(
        invoice_no=yeni_fatura_no(onek),
        client_name=client_name,
        client_email=eposta or None,
        description=(aciklama or "")[:300] or None,
        amount=0.0,
        currency=para,
        status="draft",
        issue_date=bugun.isoformat(),
        due_date=(bugun + timedelta(days=VARSAYILAN_VADE_GUN)).isoformat(),
        kalemler=json.dumps([], ensure_ascii=False),
        ara_toplam=0.0,
        kdv_toplam=0.0,
    )
    db.add(fatura)
    await db.flush()
    return fatura, True


async def faturaya_kalem_ekle(db: AsyncSession, fatura: Invoices, kalemler: List[Dict[str, Any]]) -> int:
    """Kalemleri faturanın sonuna ekler, toplamları yeniden hesaplar (commit ETMEZ).

    → eklenen ilk kalemin sırası. Yalnız taslak faturaya eklenir.
    """
    if (fatura.status or "") not in TASLAK_DURUMLARI:
        raise FaturaHatasi(409, "fatura_taslak_degil")
    mevcut = _ham_kalemler(fatura)
    ilk_sira = len(mevcut)
    try:
        belge = belge_hesapla(mevcut + [{k: v for k, v in kalem.items() if k in KALEM_ALANLARI} for kalem in kalemler])
    except HesapHatasi as h:
        raise FaturaHatasi(400, h.kod)
    fatura.kalemler = json.dumps(belge.kalem_listesi(), ensure_ascii=False)
    fatura.ara_toplam = float(belge.ara_toplam)
    fatura.kdv_toplam = float(belge.kdv_toplam)
    fatura.amount = float(belge.genel_toplam)
    await db.flush()
    return ilk_sira


async def fatura_bildir(db: AsyncSession, fatura: Invoices, neden: str = "tekrarlayan") -> None:
    """Müşteriye "yeni fatura" bildirimi (olay `invoice`). Hata fırlatmaz."""
    try:
        from services.notify import dispatch, render
        from services.pdf_belge import para

        bekleyen = (
            await db.execute(
                select(Payments).where(Payments.invoice_id == fatura.id, Payments.durum == "bekliyor").order_by(Payments.id.desc())
            )
        ).scalars().first()
        odeme = f"/ode/{bekleyen.jeton}" if bekleyen is not None and bekleyen.jeton else MUSTERI_FATURA_BAGLANTISI
        tutar = para(fatura.amount, fatura.currency or "TRY", "tr")
        baslik, govde = await render(
            db, "invoice",
            f"Yeni fatura: {fatura.invoice_no} / New invoice: {fatura.invoice_no}",
            (
                f"{fatura.description or fatura.invoice_no} için faturanız hazır: {fatura.invoice_no}, {tutar}. "
                f"Son ödeme: {fatura.due_date or '—'}. Ödeme: {odeme}\n\n"
                f"Your invoice {fatura.invoice_no} ({para(fatura.amount, fatura.currency or 'TRY', 'en')}) is ready. "
                f"Due: {fatura.due_date or '—'}. Pay: {odeme}"
            ),
            {"fatura_no": fatura.invoice_no, "tutar": tutar, "odeme": odeme, "neden": neden},
        )
        await dispatch(
            db, event_type="invoice", title=baslik, body=govde,
            recipients=[{"email": eposta_duzelt(fatura.client_email), "role": "client"}],
            link=odeme, ref_type="invoice", ref_id=fatura.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Fatura bildirimi gönderilemedi: %s", getattr(fatura, "id", None))


async def tekrarlayan_faturalari_uret(
    db: AsyncSession, bugun: Optional[date] = None, abonelik_id: Optional[int] = None
) -> Dict[str, Any]:
    """Otomatik faturası açık aktif abonelikler için zamanı gelen dönemleri keser.

    İdempotent: dönem kilidi benzersiz; aynı gün iki kez çalışsa da (ya da iki
    tur çakışsa da) aynı dönemin ikinci faturası oluşmuyor.
    """
    from models.service_subscriptions import Service_subscriptions

    bugun = bugun or tr_bugun()
    sorgu = select(Service_subscriptions).where(
        Service_subscriptions.durum == "aktif", Service_subscriptions.fatura_otomatik.is_(True)
    )
    if abonelik_id is not None:
        sorgu = sorgu.where(Service_subscriptions.id == abonelik_id)
    abonelikler = (await db.execute(sorgu)).scalars().all()
    kesilen: List[Invoices] = []
    hatalar = 0
    for a in abonelikler:
        for donem in donemler(a.periyot, a.fatura_baslangic or a.baslangic, a.son_fatura_donemi, bugun):
            try:
                fatura = await tekrarlayan_kes(db, a, donem, bugun)
            except (FaturaHatasi, HesapHatasi):
                hatalar += 1
                logger.warning("Tekrarlayan fatura kesilemedi: abonelik=%s dönem=%s", a.id, donem)
                break
            if fatura is not None:
                kesilen.append(fatura)
        await db.commit()
    for f in kesilen:
        await fatura_bildir(db, f)
    return {"abonelik": len(abonelikler), "kesilen": len(kesilen), "hata": hatalar,
            "faturalar": [f.invoice_no for f in kesilen][:20]}


# ---------------------------------------------------------------------------
# Dekont
# ---------------------------------------------------------------------------
async def dekont_kaydet(db: AsyncSession, fatura: Invoices, dosya: Any, yukleyen: Optional[str]) -> int:
    """Dekontu müşterinin "Dekontlar" klasörüne kaydeder; `files.id` döner (commit ETMEZ)."""
    from services import dosyalar as ds

    eposta = eposta_duzelt(fatura.client_email)
    if "@" not in eposta:
        raise FaturaHatasi(409, "musteri_epostasi_yok")
    try:
        veri = await ds.akistan_oku(dosya, await ds.boyut_siniri_bayt(db))
        await ds.klasor_hazirla(db, eposta, DEKONT_KLASORU, "musteri")
        kayit = await ds.dosya_kaydet(
            db, eposta=eposta, klasor=DEKONT_KLASORU, ad_ham=getattr(dosya, "filename", None) or "dekont.pdf",
            veri=veri, yukleyen=eposta_duzelt(yukleyen) or None, yukleyen_rol="admin", izinli=DEKONT_TURLERI,
        )
    except ds.DosyaHatasi as h:
        raise FaturaHatasi(h.durum, h.kod, **getattr(h, "ek", {}))
    return kayit.id
