"""Kredi defteri: bakiye, hareketler, yükleme, harcama, süre dolumu.

Model (FIFO, yeniden oynatma)
-----------------------------
Defterde yalnız hareket satırları var; bakiye hiçbir yerde saklanmıyor.
Bakiye, müşterinin satırları yazılış sırasıyla (id) yeniden oynatılarak
hesaplanıyor:

* Artı satır bir "yükleme"dir: kalan = miktar, son kullanma = +365 gün.
  O an birikmiş borç varsa (yönetici eksiye izin vermişti) yeni yükleme
  önce borcu kapatıyor.
* Eksi satır (harcama, eksi düzeltme) o anda GEÇERLİ olan yüklemelerden,
  son kullanması en yakın olandan başlayarak düşülüyor (en eski yükleme
  önce tükenir). Yetmezse artan kısım borç olarak kalıyor.
* `sure_dolumu` satırı belirli bir yüklemeye bağlı (`kaynak_ref =
  sure_dolumu:<yukleme_id>`); yalnız o yüklemenin kalanını sıfırlıyor.

Bakiye = süresi geçmemiş yüklemelerin kalanı − borç.

Süresi geçmiş ama kalanı olan yükleme için `sure_dolumlarini_isle` bir
eksi satır yazıyor; `kaynak_ref` benzersiz olduğu için aynı yükleme için
ikinci kez yazılamıyor. Zamanlanmış görev yok (ücretsiz sunucu uyuyor):
dolum, müşteri kredilerini açtığında, harcamadan önce ya da yönetici
"süre dolumlarını işle" dediğinde tetikleniyor. İşlenmemiş olsa bile
bakiye doğru çıkıyor — süresi geçmiş yükleme zaten sayılmıyor; satır
yalnız hareket listesinde görünsün diye yazılıyor.

Bilinçli basitlik: harcamanın hangi yüklemeden düştüğü satırda
saklanmıyor, her okumada yeniden hesaplanıyor. Bir müşterinin defteri
birkaç yüz satırı geçmez; yeniden oynatma milisaniyeler sürüyor ve
"saklanan eşleştirme bozuldu" türünden bir hata sınıfı hiç oluşmuyor.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException, status
from models.credit_ledger import CreditLedger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TURLER = ("satin_alma", "bonus", "harcama", "iade", "hediye", "duzeltme", "sure_dolumu")
#: Yönetici panelinden "Kredi ekle" ile yazılabilen türler.
YUKLEME_TURLERI = ("hediye", "iade", "duzeltme", "satin_alma")
GECERLILIK_GUN = 365
ADIM = 0.25
UST_SINIR = 10000.0
ESIK_AYARI = "kredi_esik_saat"
VARSAYILAN_ESIK = 2.0
#: Eşik bildirimi aynı müşteri için bu süre içinde bir kez.
ESIK_ARALIGI = timedelta(hours=24)
_KUSURAT = 1e-9


def _simdi() -> datetime:
    """Testler zamanı buradan kaydırıyor (monkeypatch)."""
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini düşürüyor; saklanan her değer UTC."""
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def yuvarla(deger: float) -> float:
    return round(float(deger) + 0.0, 2)


def eposta_duzelt(eposta: Optional[str]) -> str:
    temiz = (eposta or "").strip().lower()
    if "@" not in temiz or len(temiz) > 254 or " " in temiz:
        raise HTTPException(status_code=400, detail="Geçerli bir e-posta adresi gerekli")
    return temiz


def saat_dogrula(saat: Any, *, eksi_olabilir: bool = False) -> float:
    """0.25'in katı, sıfırdan farklı, makul büyüklükte bir saat."""
    try:
        deger = float(saat)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Saat sayı olmalı")
    if deger != deger or abs(deger) > UST_SINIR:
        raise HTTPException(status_code=400, detail="Saat geçersiz")
    if abs(deger * 4 - round(deger * 4)) > 1e-6:
        raise HTTPException(status_code=400, detail="Saat 0.25'in katı olmalı")
    deger = round(deger * 4) / 4
    if deger == 0 or (deger < 0 and not eksi_olabilir):
        raise HTTPException(status_code=400, detail="Saat sıfırdan büyük olmalı")
    return deger


# ---------------------------------------------------------------------------
# Yeniden oynatma
# ---------------------------------------------------------------------------


@dataclass
class Yukleme:
    satir: CreditLedger
    kalan: float
    son_kullanma: datetime
    dolumu_yazildi: bool = False


@dataclass
class Durum:
    bakiye: float = 0.0
    borc: float = 0.0
    #: Süresi geçmemiş, kalanı olan yüklemeler; son kullanması en yakın önce.
    aktif: List[Yukleme] = field(default_factory=list)
    #: Süresi geçmiş, kalanı olan ve dolum satırı henüz yazılmamış yüklemeler.
    dolmus: List[Yukleme] = field(default_factory=list)


def _dolum_hedefi(kaynak_ref: Optional[str]) -> Optional[int]:
    if not kaynak_ref or not kaynak_ref.startswith("sure_dolumu:"):
        return None
    try:
        return int(kaynak_ref.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def durum_hesapla(satirlar: Iterable[CreditLedger], simdi: Optional[datetime] = None) -> Durum:
    """Satırları id sırasıyla oynatıp bakiyeyi ve yüklemelerin kalanını bulur."""
    simdi = simdi or _simdi()
    yuklemeler: Dict[int, Yukleme] = {}
    borc = 0.0

    for s in sorted(satirlar, key=lambda x: x.id or 0):
        miktar = float(s.miktar or 0)
        an = _utc(s.created_at) or simdi
        if miktar > 0:
            son = _utc(s.son_kullanma) or (an + timedelta(days=GECERLILIK_GUN))
            yukleme = Yukleme(satir=s, kalan=miktar, son_kullanma=son)
            if borc > _KUSURAT:
                odenen = min(borc, yukleme.kalan)
                yukleme.kalan -= odenen
                borc -= odenen
            yuklemeler[s.id] = yukleme
            continue
        if miktar >= 0:
            continue

        ihtiyac = -miktar
        hedef = _dolum_hedefi(s.kaynak_ref) if s.tur == "sure_dolumu" else None
        if hedef is not None:
            yukleme = yuklemeler.get(hedef)
            if yukleme is not None:
                yukleme.kalan = max(0.0, yukleme.kalan - ihtiyac)
                yukleme.dolumu_yazildi = True
            continue

        gecerli = sorted(
            (y for y in yuklemeler.values() if y.kalan > _KUSURAT and y.son_kullanma > an),
            key=lambda y: (y.son_kullanma, y.satir.id),
        )
        for yukleme in gecerli:
            if ihtiyac <= _KUSURAT:
                break
            dusen = min(yukleme.kalan, ihtiyac)
            yukleme.kalan -= dusen
            ihtiyac -= dusen
        if ihtiyac > _KUSURAT:
            borc += ihtiyac

    aktif = sorted(
        (y for y in yuklemeler.values() if y.kalan > _KUSURAT and y.son_kullanma > simdi),
        key=lambda y: (y.son_kullanma, y.satir.id),
    )
    dolmus = [
        y for y in yuklemeler.values()
        if y.kalan > _KUSURAT and y.son_kullanma <= simdi and not y.dolumu_yazildi
    ]
    return Durum(
        bakiye=yuvarla(sum(y.kalan for y in aktif) - borc),
        borc=yuvarla(borc),
        aktif=aktif,
        dolmus=sorted(dolmus, key=lambda y: y.satir.id),
    )


async def _satirlar(db: AsyncSession, eposta: str) -> List[CreditLedger]:
    sonuc = await db.execute(
        select(CreditLedger).where(CreditLedger.musteri_eposta == eposta).order_by(CreditLedger.id.asc())
    )
    return list(sonuc.scalars().all())


async def durum(db: AsyncSession, eposta: str) -> Durum:
    return durum_hesapla(await _satirlar(db, eposta))


async def bakiye(db: AsyncSession, eposta: str) -> float:
    return (await durum(db, eposta)).bakiye


async def hareketler(db: AsyncSession, eposta: str, limit: int = 200) -> List[CreditLedger]:
    sonuc = await db.execute(
        select(CreditLedger)
        .where(CreditLedger.musteri_eposta == eposta)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc())
        .limit(limit)
    )
    return list(sonuc.scalars().all())


def yaklasan_son_kullanmalar(d: Durum) -> List[Dict[str, Any]]:
    return [{"miktar": yuvarla(y.kalan), "tarih": y.son_kullanma} for y in d.aktif]


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------


async def _ref_var_mi(db: AsyncSession, kaynak_ref: str) -> bool:
    sonuc = await db.execute(select(CreditLedger.id).where(CreditLedger.kaynak_ref == kaynak_ref))
    return sonuc.first() is not None


def _satir(
    *,
    eposta: str,
    miktar: float,
    tur: str,
    aciklama: Optional[str],
    an: datetime,
    fatura_id: Optional[int] = None,
    proje_id: Optional[int] = None,
    kaynak_ref: Optional[str] = None,
    olusturan: Optional[str] = None,
) -> CreditLedger:
    if tur not in TURLER:
        raise HTTPException(status_code=400, detail=f"Bilinmeyen tür: {tur}")
    return CreditLedger(
        created_at=an,
        musteri_eposta=eposta,
        miktar=miktar,
        tur=tur,
        aciklama=(aciklama or "").strip()[:500] or None,
        fatura_id=fatura_id,
        proje_id=proje_id,
        son_kullanma=an + timedelta(days=GECERLILIK_GUN) if miktar > 0 else None,
        kaynak_ref=kaynak_ref,
        olusturan_eposta=(olusturan or "").strip().lower() or None,
    )


async def yukle(
    db: AsyncSession,
    *,
    eposta: str,
    saat: float,
    tur: str,
    aciklama: Optional[str] = None,
    fatura_id: Optional[int] = None,
    proje_id: Optional[int] = None,
    olusturan: Optional[str] = None,
    kaynak_ref: Optional[str] = None,
) -> CreditLedger:
    """Artı (ya da düzeltmede eksi) satır yazar ve commit eder."""
    eposta = eposta_duzelt(eposta)
    miktar = saat_dogrula(saat, eksi_olabilir=(tur == "duzeltme"))
    if tur in ("harcama", "sure_dolumu"):
        raise HTTPException(status_code=400, detail="Bu tür yükleme ile yazılamaz")
    if kaynak_ref and await _ref_var_mi(db, kaynak_ref):
        raise HTTPException(status_code=409, detail="Bu kaynak için kayıt zaten var")
    satir = _satir(
        eposta=eposta, miktar=miktar, tur=tur, aciklama=aciklama, an=_simdi(),
        fatura_id=fatura_id, proje_id=proje_id, kaynak_ref=kaynak_ref, olusturan=olusturan,
    )
    db.add(satir)
    await db.commit()
    await db.refresh(satir)
    return satir


async def harca(
    db: AsyncSession,
    *,
    eposta: str,
    saat: float,
    aciklama: Optional[str] = None,
    proje_id: Optional[int] = None,
    izin_eksi: bool = False,
    olusturan: Optional[str] = None,
) -> tuple[CreditLedger, float]:
    """Harcama satırı yazar; `(satir, yeni_bakiye)` döndürür.

    Bakiye yetmezse 409 `yetersiz_bakiye`. Yönetici `izin_eksi` ile
    bilerek eksiye düşürebilir (iş bitti, kredi sonra alınacak); eksi kısım
    bir sonraki yüklemeden ilk olarak düşülüyor.
    """
    eposta = eposta_duzelt(eposta)
    miktar = saat_dogrula(saat)
    await sure_dolumlarini_isle(db, eposta)

    mevcut = await bakiye(db, eposta)
    if miktar > mevcut + _KUSURAT and not izin_eksi:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="yetersiz_bakiye")

    satir = _satir(
        eposta=eposta, miktar=-miktar, tur="harcama", aciklama=aciklama, an=_simdi(),
        proje_id=proje_id, olusturan=olusturan,
    )
    db.add(satir)
    await db.commit()
    await db.refresh(satir)

    yeni = await bakiye(db, eposta)
    try:
        await esik_bildir(db, eposta, yeni)
    except Exception:  # noqa: BLE001 - bildirim harcamayı bozmamalı
        logger.exception("Kredi eşik bildirimi gönderilemedi: %s", eposta)
    return satir, yeni


async def sure_dolumlarini_isle(db: AsyncSession, eposta: Optional[str] = None) -> Dict[str, Any]:
    """Süresi geçmiş yüklemelerin kalanı için `sure_dolumu` satırı yazar.

    `eposta` verilmezse süresi geçmiş yüklemesi olan bütün müşteriler.
    Aynı yükleme için ikinci satır yazılmıyor: `kaynak_ref` benzersiz, eş
    zamanlı iki istek çakışırsa ikincisi SAVEPOINT içinde geri alınıyor.
    """
    simdi = _simdi()
    if eposta:
        epostalar = [eposta]
    else:
        sonuc = await db.execute(
            select(CreditLedger.musteri_eposta)
            .where(CreditLedger.miktar > 0)
            .where(CreditLedger.son_kullanma <= simdi)
            .distinct()
        )
        epostalar = [e for (e,) in sonuc.all() if e]

    yazilan = 0
    toplam = 0.0
    for kisi in epostalar:
        d = durum_hesapla(await _satirlar(db, kisi), simdi)
        for yukleme in d.dolmus:
            ref = f"sure_dolumu:{yukleme.satir.id}"
            kalan = yuvarla(yukleme.kalan)
            try:
                async with db.begin_nested():
                    db.add(
                        _satir(
                            eposta=kisi,
                            miktar=-kalan,
                            tur="sure_dolumu",
                            aciklama=f"#{yukleme.satir.id} yüklemesinin süresi doldu",
                            an=yukleme.son_kullanma,
                            kaynak_ref=ref,
                        )
                    )
            except IntegrityError:
                logger.info("Süre dolumu zaten yazılmış: %s", ref)
                continue
            yazilan += 1
            toplam += kalan
    if yazilan:
        await db.commit()
    return {"musteri": len(epostalar), "yazilan": yazilan, "toplam_saat": yuvarla(toplam)}


# ---------------------------------------------------------------------------
# Ödeme kancası
# ---------------------------------------------------------------------------


def _kredi_paketi_adedi(addon_ids: Optional[str]) -> Optional[int]:
    try:
        liste = json.loads(addon_ids or "[]")
    except (TypeError, ValueError):
        return None
    if not isinstance(liste, list):
        return None
    for oge in liste:
        if isinstance(oge, str) and oge.startswith("kredi_paketi:"):
            try:
                return int(oge.split(":", 1)[1])
            except ValueError:
                return None
    return None


async def odeme_kredilerini_yukle(db: AsyncSession, fatura_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Faturası kapanan kredi paketinin kredilerini deftere yazar.

    Ödeme işleyicileri (Lemon, Shopier, elle tahsilat) faturayı kapattıktan
    sonra, KENDİ commit'lerinden önce çağırıyor: tahsilat ile kredi aynı
    işlemde yazılıyor. Burada commit yok.

    İdempotent: anahtar ödeme değil fatura (`fatura:<id>:kredi`). Böylece
    aynı bildirim iki kez gelse de, fatura iki parça halinde ödense de,
    kartla ödenmiş faturaya ayrıca elle tahsilat girilse de kredi bir kez
    yükleniyor. Fatura tamamen ödenmeden (status != paid) hiçbir şey
    yazılmıyor.

    Hata yutuluyor (SAVEPOINT): kredi yazılamazsa tahsilat yine kaydedilmeli.
    Bildirim için sade bir özet döndürüyor; bildirimi çağıran commit'ten
    sonra `kredi_yuklendi_bildir` ile gönderiyor.
    """
    if not fatura_id:
        return None
    try:
        from core.fiyat_hesaplama import FiyatHesaplamaHatasi, kredi_paketi
        from models.invoices import Invoices
        from models.pricing import Pricing_inquiries

        fatura = (await db.execute(select(Invoices).where(Invoices.id == fatura_id))).scalar_one_or_none()
        if fatura is None or (fatura.status or "") != "paid":
            return None

        talepler = (
            await db.execute(
                select(Pricing_inquiries)
                .where(Pricing_inquiries.invoice_id == fatura_id)
                .order_by(Pricing_inquiries.id.asc())
            )
        ).scalars().all()
        talep = next((t for t in talepler if _kredi_paketi_adedi(t.addon_ids)), None)
        if talep is None:
            return None
        try:
            paket = kredi_paketi(_kredi_paketi_adedi(talep.addon_ids) or 0)
        except FiyatHesaplamaHatasi:
            logger.warning("Faturadaki kredi paketi tanınmadı: fatura=%s", fatura_id)
            return None

        eposta = (talep.musteri_eposta or fatura.client_email or "").strip().lower()
        if "@" not in eposta:
            return None

        ref = f"fatura:{fatura_id}:kredi"
        if await _ref_var_mi(db, ref):
            return None

        an = _simdi()
        no = fatura.invoice_no or f"#{fatura_id}"
        async with db.begin_nested():
            db.add(
                _satir(
                    eposta=eposta, miktar=float(paket["kredi"]), tur="satin_alma",
                    aciklama=f"{paket['kredi']} kredi paketi — {no}", an=an,
                    fatura_id=fatura_id, kaynak_ref=ref,
                )
            )
            if paket["bonus"]:
                db.add(
                    _satir(
                        eposta=eposta, miktar=float(paket["bonus"]), tur="bonus",
                        aciklama=f"{paket['kredi']} kredi paketi bonusu — {no}", an=an,
                        fatura_id=fatura_id, kaynak_ref=f"fatura:{fatura_id}:bonus",
                    )
                )
        return {
            "eposta": eposta,
            "kredi": paket["kredi"],
            "bonus": paket["bonus"],
            "saat": paket["saat"],
            "fatura_no": no,
            "fatura_id": fatura_id,
            "son_kullanma": an + timedelta(days=GECERLILIK_GUN),
        }
    except IntegrityError:
        logger.info("Kredi yüklemesi zaten yazılmış: fatura=%s", fatura_id)
        return None
    except Exception:  # noqa: BLE001 - tahsilat bu yüzden düşmemeli
        logger.exception("Ödeme kredileri yazılamadı: fatura=%s", fatura_id)
        return None


# ---------------------------------------------------------------------------
# Bildirimler
# ---------------------------------------------------------------------------

PANEL_BAGLANTISI = "/client?sekme=krediler"


def _tarih(an: Optional[datetime]) -> str:
    return an.strftime("%Y-%m-%d") if an else "—"


def _saat_metni(deger: float) -> str:
    return f"{deger:g}"


async def kredi_yuklendi_bildir(db: AsyncSession, ozet: Optional[Dict[str, Any]]) -> None:
    """Müşteriye "krediniz yüklendi" bildirimi. Hata fırlatmaz."""
    if not ozet:
        return
    try:
        from services.notify import dispatch, render

        yeni = await bakiye(db, ozet["eposta"])
        degerler = {
            "kredi": ozet["kredi"],
            "bonus": ozet["bonus"],
            "saat": ozet["saat"],
            "bakiye": _saat_metni(yeni),
            "son_kullanma": _tarih(ozet.get("son_kullanma")),
            "fatura_no": ozet.get("fatura_no") or "",
        }
        bonus_tr = f" (+{ozet['bonus']} bonus)" if ozet["bonus"] else ""
        bonus_en = f" (+{ozet['bonus']} bonus)" if ozet["bonus"] else ""
        baslik, govde = await render(
            db,
            "kredi_yuklendi",
            "Krediniz yüklendi / Your credits have been added",
            (
                f"Hesabınıza {ozet['kredi']} kredi{bonus_tr} yüklendi. "
                f"Güncel bakiye: {degerler['bakiye']} saat. "
                f"Son kullanma: {degerler['son_kullanma']}.\n\n"
                f"{ozet['kredi']} credits{bonus_en} have been added to your account. "
                f"Current balance: {degerler['bakiye']} hours. "
                f"Expires on: {degerler['son_kullanma']}."
            ),
            degerler,
        )
        await dispatch(
            db,
            event_type="kredi_yuklendi",
            title=baslik,
            body=govde,
            recipients=[{"email": ozet["eposta"], "role": "client"}],
            link=PANEL_BAGLANTISI,
            ref_type="invoice",
            ref_id=ozet.get("fatura_id"),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Kredi yüklendi bildirimi gönderilemedi")


async def esik_degeri(db: AsyncSession, eposta: Optional[str] = None) -> float:
    """Düşük bakiye uyarı eşiği (saat).

    Öncelik: müşterinin `krediler` modül ayarı `esik_saat` (panel › Modüller)
    → site ayarı `kredi_esik_saat` → 2.
    """
    if eposta:
        try:
            from services.moduller import musteri_ayari

            ozel = await musteri_ayari(db, eposta, "krediler", "esik_saat")
            if ozel is not None:
                return float(ozel)
        except Exception:  # noqa: BLE001
            logger.debug("Müşterinin kredi eşiği okunamadı", exc_info=True)
    try:
        from models.site_settings import Site_settings

        satir = (
            await db.execute(select(Site_settings).where(Site_settings.setting_key == ESIK_AYARI))
        ).scalars().first()
        if satir and str(satir.setting_value or "").strip():
            return float(str(satir.setting_value).strip().replace(",", "."))
    except (TypeError, ValueError):
        logger.warning("kredi_esik_saat ayarı sayı değil; varsayılan kullanılıyor")
    except Exception:  # noqa: BLE001
        logger.debug("Kredi eşiği okunamadı", exc_info=True)
    return VARSAYILAN_ESIK


async def esik_bildir(db: AsyncSession, eposta: str, yeni_bakiye: float) -> bool:
    """Bakiye eşiğin altına indiyse müşteriye ve yöneticiye haber verir.

    Aynı müşteri için son 24 saatte `kredi_azaldi` bildirimi gittiyse
    tekrar gönderilmiyor: gün içinde birkaç küçük harcama yazılınca
    müşteriye art arda aynı e-posta gitmesin.
    """
    esik = await esik_degeri(db, eposta)
    if yeni_bakiye > esik + _KUSURAT:
        return False

    from models.notifications import Notifications
    from services.notify import admin_recipients, dispatch, render

    sinir = datetime.now() - ESIK_ARALIGI
    onceki = await db.execute(
        select(Notifications.id)
        .where(Notifications.event_type == "kredi_azaldi")
        .where(Notifications.recipient_email == eposta)
        .where(Notifications.created_at >= sinir)
        .limit(1)
    )
    if onceki.first() is not None:
        return False

    degerler = {"bakiye": _saat_metni(yeni_bakiye), "esik": _saat_metni(esik), "eposta": eposta}
    baslik, govde = await render(
        db,
        "kredi_azaldi",
        "Kredi bakiyeniz azaldı / Your credit balance is low",
        (
            f"Kalan kredi bakiyeniz {degerler['bakiye']} saat (uyarı eşiği: {degerler['esik']} saat). "
            "İşlerin aksamaması için panelinizden yeni kredi alabilirsiniz.\n\n"
            f"Your remaining credit balance is {degerler['bakiye']} hours (alert threshold: "
            f"{degerler['esik']} hours). You can buy more credits from your panel so work is not interrupted."
        ),
        degerler,
    )
    await dispatch(
        db,
        event_type="kredi_azaldi",
        title=baslik,
        body=govde,
        recipients=[{"email": eposta, "role": "client"}],
        link=PANEL_BAGLANTISI,
        ref_type="kredi",
    )

    yoneticiler = [a for a in await admin_recipients(db) if (a.get("email") or "").strip().lower() != eposta]
    if yoneticiler:
        y_baslik, y_govde = await render(
            db,
            "kredi_azaldi_yonetici",
            f"Kredi azaldı: {eposta} / Low credit: {eposta}",
            (
                f"{eposta} müşterisinin kredi bakiyesi {degerler['bakiye']} saate indi "
                f"(eşik {degerler['esik']} saat).\n\n"
                f"Credit balance of {eposta} dropped to {degerler['bakiye']} hours "
                f"(threshold {degerler['esik']} hours)."
            ),
            degerler,
        )
        await dispatch(
            db,
            event_type="kredi_azaldi",
            title=y_baslik,
            body=y_govde,
            recipients=yoneticiler,
            link="/admin",
            ref_type="kredi",
        )
    return True


__all__ = [
    "TURLER", "YUKLEME_TURLERI", "bakiye", "durum", "durum_hesapla", "hareketler", "yukle", "harca",
    "sure_dolumlarini_isle", "odeme_kredilerini_yukle", "kredi_yuklendi_bildir", "esik_bildir",
    "yaklasan_son_kullanmalar",
]
