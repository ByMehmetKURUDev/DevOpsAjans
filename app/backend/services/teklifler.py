"""Faz 3T — teklif (öneri): kalemler, gönderim, görüntülenme, kabul/ret, otomatik kayıtlar.

Akış
----
1. Yönetici teklifi hazırlar (taslak): kalemler sunucuda hesaplanır
   (services/belge_hesap.py). Fiyat sihirbazı kaydından (`pricing_inquiries`)
   "teklife çevir" ile de başlatılabilir.
2. "Gönder": `signed_actions`'a `teklif_onay` türünde bağlantı açılır
   (`/teklif/<jeton>`; ham jeton yalnız bu yanıtta, bir kez). Son kullanma =
   teklifin geçerlilik gününün sonu (en çok 90 gün).
3. Müşteri bağlantıyı açar: her açılış görüntülenme sayacını artırır (ilk/son
   görüntülenme zamanı yazılır); bağlantı TÜKENMEZ. Karar (kabul — ad soyad
   yazarak — ya da gerekçeli ret) TEK: `imzali_islem` koşullu UPDATE'i.
   Geçerlilik geçmişse karar verilemez (410 `suresi_doldu`).
4. Kabulde, aynı işlemde (biri patlarsa hepsi geri alınır, bağlantı yeniden
   denenebilir): yöneticinin seçtiği otomatik kayıtlar — sözleşme TASLAĞI
   (şablondan), ilk fatura (peşinat yüzdesi; KDV oranı başına satır) + ödeme
   bağlantısı, proje. Teklif sihirbaz kaydından geldiyse onun durumu da
   "kabul" olur ve faturası yeniden kullanılır (ikinci fatura açılmaz).

Revizyon: gönderilmiş teklif düzenlenmiyor; "revize et" yeni sürüm açar
(`TKL-YYYY-NNNN-R2`, taslak), eskisi `revize` olur ve bağlantısı iptal edilir.
"""

import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models.signed_actions import SignedActions
from models.teklifler import Teklifler
from services import belge_ortak as bo
from services.belge_hesap import (
    HesapHatasi,
    belge_hesapla,
    kayitli_kalemler,
    ondalik,
    oranla_bol,
    para_birimi_duzelt,
)
from services.imzali_islem import IslemHatasi
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TUR = "teklif_onay"
DURUMLAR = ("taslak", "gonderildi", "goruntulendi", "kabul", "ret", "suresi_doldu", "revize")
#: Müşterinin görebildiği durumlar (taslak görünmez).
MUSTERI_DURUMLARI = ("gonderildi", "goruntulendi", "kabul", "ret", "suresi_doldu", "revize")
#: Karar verilebilir durumlar.
ACIK_DURUMLAR = ("gonderildi", "goruntulendi")
METIN_SINIRI = 5000
BASLIK_SINIRI = 200
VARSAYILAN_GECERLILIK_GUN = 30


class TeklifHatasi(Exception):
    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def _metin(deger: Any, sinir: int = METIN_SINIRI) -> Optional[str]:
    temiz = str(deger or "").strip()
    return temiz[:sinir] or None


def _bool(deger: Any) -> bool:
    return bool(deger) and deger not in ("0", "false", "False")


def _decimal_float(d: Any) -> Optional[float]:
    if d is None:
        return None
    return float(Decimal(str(d)))


# ---------------------------------------------------------------------------
# Doğrulama ve yazma
# ---------------------------------------------------------------------------
async def _sablon_var_mi(db: AsyncSession, sablon_id: Optional[int]) -> bool:
    if not sablon_id:
        return True
    from models.sozlesmeler import SozlesmeSablonlari

    return (await db.execute(select(SozlesmeSablonlari.id).where(SozlesmeSablonlari.id == sablon_id))).scalar() is not None


async def alanlari_uygula(db: AsyncSession, teklif: Teklifler, govde: Dict[str, Any], *, yeni: bool):
    """Gövdeyi doğrular ve teklife yazar; toplamlar sunucuda (istemci toplamı yok sayılır).

    Faz 5K: indirim kodu varsa (gövdede ya da kayıtta) dönen değer `indirim_kodlari.Uygulama`
    (kullanım kaydı teklifin kimliği belli olunca `kullanimi_isle` ile yazılır); yoksa None.
    """
    from services import indirim_kodlari as ik

    if "baslik" in govde or yeni:
        baslik = _metin(govde.get("baslik"), BASLIK_SINIRI)
        if not baslik:
            raise TeklifHatasi(400, "baslik_gerekli")
        teklif.baslik = baslik
    if "kalemler" in govde or yeni:
        try:
            # İstemcinin gönderdiği "İndirim (KOD)" satırları atılır; kod aşağıda yeniden uygulanır.
            belge = belge_hesapla(ik.isaretlileri_at(govde.get("kalemler")))
        except HesapHatasi as h:
            raise TeklifHatasi(400, h.kod, **({"sira": h.sira} if h.sira is not None else {}))
        teklif.kalemler = json.dumps(belge.kalem_listesi(), ensure_ascii=False)
        teklif.ara_toplam = belge.ara_toplam
        teklif.indirim_toplam = belge.indirim_toplam
        teklif.kdv_toplam = belge.kdv_toplam
        teklif.genel_toplam = belge.genel_toplam
    if "para_birimi" in govde or yeni:
        try:
            teklif.para_birimi = para_birimi_duzelt(govde.get("para_birimi"))
        except HesapHatasi as h:
            raise TeklifHatasi(400, h.kod)
    if "hesap_email" in govde or yeni:
        hesap = bo.eposta_duzelt(govde.get("hesap_email"))
        if hesap and not bo.eposta_gecerli(hesap):
            raise TeklifHatasi(400, "eposta_gecersiz")
        teklif.hesap_email = hesap or None
    if "aday_eposta" in govde or yeni:
        aday = bo.eposta_duzelt(govde.get("aday_eposta"))
        if aday and not bo.eposta_gecerli(aday):
            raise TeklifHatasi(400, "eposta_gecersiz")
        teklif.aday_eposta = aday or None
    if "aday_ad" in govde or yeni:
        teklif.aday_ad = _metin(govde.get("aday_ad"), 200)
    if "gecerlilik" in govde or yeni:
        try:
            gecerlilik = bo.tarih_dogrula(govde.get("gecerlilik"), "gecerlilik_gecersiz")
        except ValueError:
            raise TeklifHatasi(400, "gecerlilik_gecersiz")
        teklif.gecerlilik = gecerlilik or (bo.tr_bugun() + timedelta(days=VARSAYILAN_GECERLILIK_GUN)).isoformat()
    for alan in ("notlar", "sartlar"):
        if alan in govde or yeni:
            setattr(teklif, alan, _metin(govde.get(alan)))
    for alan in ("otomatik_sozlesme", "otomatik_fatura", "otomatik_proje"):
        if alan in govde or yeni:
            setattr(teklif, alan, _bool(govde.get(alan)))
    if "sozlesme_sablon_id" in govde or yeni:
        sablon_id = govde.get("sozlesme_sablon_id") or None
        if sablon_id is not None:
            try:
                sablon_id = int(sablon_id)
            except (TypeError, ValueError):
                raise TeklifHatasi(400, "sablon_yok")
            if not await _sablon_var_mi(db, sablon_id):
                raise TeklifHatasi(400, "sablon_yok")
        teklif.sozlesme_sablon_id = sablon_id
    if "proje_sablon_id" in govde or yeni:
        # Faz 3Z: kabulde otomatik oluşan projeye uygulanacak proje şablonu.
        sablon_id = govde.get("proje_sablon_id") or None
        if sablon_id is not None:
            try:
                sablon_id = int(sablon_id)
            except (TypeError, ValueError):
                raise TeklifHatasi(400, "proje_sablonu_yok")
            from models.zaman_takibi import ProjeSablonlari

            if (await db.execute(select(ProjeSablonlari.id).where(ProjeSablonlari.id == sablon_id))).scalar() is None:
                raise TeklifHatasi(400, "proje_sablonu_yok")
        teklif.proje_sablon_id = sablon_id
    if "pesinat_yuzde" in govde or yeni:
        ham = govde.get("pesinat_yuzde")
        if ham in (None, ""):
            teklif.pesinat_yuzde = None
        else:
            try:
                yuzde = ondalik(ham, "pesinat_gecersiz")
            except HesapHatasi:
                raise TeklifHatasi(400, "pesinat_gecersiz")
            if yuzde <= 0 or yuzde > 100:
                raise TeklifHatasi(400, "pesinat_gecersiz")
            teklif.pesinat_yuzde = yuzde
    if not teklif.hesap_email and not teklif.aday_eposta:
        raise TeklifHatasi(400, "alici_gerekli")
    # Faz 5K — indirim kodu: alıcı ve para birimi belli olduktan sonra (kişi başı sınır, para birimi uyumu).
    if "indirim_kodu" not in govde and not teklif.indirim_kodu:
        return None
    temel = govde.get("kalemler") if ("kalemler" in govde or yeni) else kayitli_kalemler(teklif.kalemler)
    # "Teklif al" talebinden açılan teklif: hizmet paketi kapsamı + talebin paketi (paketle sınırlı kodlar için).
    talep_id = govde.get("pricing_inquiry_id") or teklif.pricing_inquiry_id
    ek_kapsam = tuple(govde.get("_ek_kapsam") or ()) + (("paket",) if talep_id else ())
    try:
        u = await ik.belgeye_uygula(
            db, kalemler=temel, ham_kod=govde.get("indirim_kodu") if "indirim_kodu" in govde else None,
            mevcut_kod=teklif.indirim_kodu, belge_turu="teklif", belge_id=teklif.id, para_birimi=teklif.para_birimi,
            eposta=alici(teklif), ek_kapsam=ek_kapsam,
            paket=await ik.belge_paketi(db, pricing_inquiry_id=talep_id) if talep_id else None,
        )
        belge = belge_hesapla(u.kalemler)
    except ik.KodHatasi as h:
        raise TeklifHatasi(h.durum, h.kod, **h.ek)
    except HesapHatasi as h:
        raise TeklifHatasi(400, h.kod, **({"sira": h.sira} if h.sira is not None else {}))
    teklif.kalemler = json.dumps(belge.kalem_listesi(), ensure_ascii=False)
    teklif.ara_toplam = belge.ara_toplam
    teklif.indirim_toplam = belge.indirim_toplam
    teklif.kdv_toplam = belge.kdv_toplam
    teklif.genel_toplam = belge.genel_toplam
    teklif.indirim_kodu = u.kod.kod if u.kod is not None else None
    return u


async def olustur(db: AsyncSession, govde: Dict[str, Any], olusturan: Optional[str]) -> Teklifler:
    teklif = Teklifler(durum="taslak", surum=1, goruntulenme_sayisi=0, olusturan_eposta=bo.eposta_duzelt(olusturan) or None)
    uygulama = await alanlari_uygula(db, teklif, govde, yeni=True)
    if govde.get("pricing_inquiry_id"):
        teklif.pricing_inquiry_id = int(govde["pricing_inquiry_id"])
    if govde.get("fatura_id"):
        teklif.fatura_id = int(govde["fatura_id"])
    for deneme in range(5):
        teklif.no = await bo.sirali_no(db, Teklifler.no, "TKL")
        try:
            async with db.begin_nested():
                db.add(teklif)
                await db.flush()
            break
        except IntegrityError:
            if deneme == 4:
                raise
    teklif.kok_id = teklif.id
    if uygulama is not None:
        from services import indirim_kodlari as ik

        await ik.kullanimi_isle(db, uygulama, "teklif", teklif.id, alici(teklif), teklif.para_birimi)
    await db.commit()
    await db.refresh(teklif)
    return teklif


async def guncelle(db: AsyncSession, teklif: Teklifler, govde: Dict[str, Any]) -> Teklifler:
    if teklif.durum != "taslak":
        # Gönderilmiş teklifin metni/tutarı değişmez: "revize et" yeni sürüm açar.
        raise TeklifHatasi(409, "revize_gerekli")
    uygulama = await alanlari_uygula(db, teklif, govde, yeni=False)
    if uygulama is not None:
        from services import indirim_kodlari as ik

        await ik.kullanimi_isle(db, uygulama, "teklif", teklif.id, alici(teklif), teklif.para_birimi)
    await db.commit()
    await db.refresh(teklif)
    return teklif


async def sil(db: AsyncSession, teklif: Teklifler) -> None:
    if teklif.durum == "kabul":
        # Kabul kaydı (ad, zaman, IP özeti) sözleşmenin dayanağı: silinmiyor.
        raise TeklifHatasi(409, "kabul_silinemez")
    await _baglantiyi_iptal_et(db, teklif)
    if teklif.indirim_kodu:
        from services import indirim_kodlari as ik

        await ik.kullanim_sil(db, "teklif", teklif.id)
    await db.delete(teklif)
    await db.commit()


async def getir(db: AsyncSession, teklif_id: int) -> Teklifler:
    teklif = (await db.execute(select(Teklifler).where(Teklifler.id == teklif_id))).scalar_one_or_none()
    if teklif is None:
        raise TeklifHatasi(404, "teklif_yok")
    return teklif


def alici(teklif: Teklifler) -> str:
    return bo.eposta_duzelt(teklif.hesap_email or teklif.aday_eposta)


# ---------------------------------------------------------------------------
# Süre
# ---------------------------------------------------------------------------
def suresi_gecti_mi(teklif: Teklifler, bugun: Optional[date] = None) -> bool:
    if not teklif.gecerlilik:
        return False
    try:
        return date.fromisoformat(teklif.gecerlilik[:10]) < (bugun or bo.tr_bugun())
    except ValueError:
        return False


async def sureleri_isle(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Geçerliliği geçen açık teklifler `suresi_doldu` (zamanlı görev + liste açılışı)."""
    bugun = bugun or bo.tr_bugun()
    sonuc = await db.execute(
        update(Teklifler)
        .where(Teklifler.durum.in_(ACIK_DURUMLAR), Teklifler.gecerlilik.isnot(None), Teklifler.gecerlilik < bugun.isoformat())
        .values(durum="suresi_doldu")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {"suresi_dolan": int(sonuc.rowcount or 0)}


# ---------------------------------------------------------------------------
# Gönderim
# ---------------------------------------------------------------------------
async def _baglantiyi_iptal_et(db: AsyncSession, teklif: Teklifler) -> None:
    if not teklif.islem_id:
        return
    await db.execute(
        update(SignedActions)
        .where(SignedActions.id == teklif.islem_id, SignedActions.durum == "bekliyor")
        .values(durum="iptal")
        .execution_options(synchronize_session=False)
    )


def baglanti(jeton: str) -> str:
    return f"{bo.site_adresi()}/teklif/{jeton}"


async def gonder(
    db: AsyncSession, teklif: Teklifler, *, olusturan: Optional[str], eposta_gonder: bool = False
) -> Tuple[str, bool]:
    """Bağlantıyı üretir (eskisi bekliyorsa iptal) → (tam adres, e-posta gitti mi)."""
    from services import imzali_islem

    if teklif.durum not in ("taslak", "gonderildi", "goruntulendi"):
        raise TeklifHatasi(409, f"durum_{teklif.durum}")
    if suresi_gecti_mi(teklif):
        raise TeklifHatasi(409, "gecerlilik_gecti")
    hedef = alici(teklif)
    if not bo.eposta_gecerli(hedef):
        raise TeklifHatasi(400, "alici_gerekli")
    await _baglantiyi_iptal_et(db, teklif)
    await db.commit()
    bitis = bo.baglanti_bitisi(teklif.gecerlilik)
    try:
        jeton, kayit = await imzali_islem.olustur(
            db, TUR, ("teklifler", teklif.id), hedef, f"{teklif.no} · {teklif.baslik}",
            {"teklif_id": teklif.id, "no": teklif.no}, bo.baglanti_gunu(bitis), olusturan=olusturan,
        )
    except IslemHatasi as h:
        raise TeklifHatasi(h.durum, h.kod)
    kayit.son_kullanma = bitis
    teklif.islem_id = kayit.id
    if teklif.durum == "taslak":
        teklif.durum = "gonderildi"
    teklif.gonderildi_at = bo.simdi()
    await db.commit()
    await db.refresh(teklif)
    adres = baglanti(jeton)
    gitti = False
    if eposta_gonder:
        from services.pdf_belge import para

        tutar = para(teklif.genel_toplam, teklif.para_birimi, "tr")
        gitti = await bo.baglantili_bildirim(
            db,
            event_type="teklif_gonderildi",
            alici=hedef,
            baslik=f"Teklifiniz hazır: {teklif.no} / Your quote is ready: {teklif.no}",
            govde=(
                f"Merhaba,\n\n{teklif.baslik} için teklifimiz hazır ({tutar}, geçerlilik: {teklif.gecerlilik}).\n"
                f"Giriş yapmadan inceleyip kabul ya da reddedebilirsiniz:\n{adres}\n\n"
                f"Our quote for {teklif.baslik} is ready. Review and accept or decline, no login needed:\n{adres}\n\n"
                f"— By Mehmet KURU Dev"
            ),
            baglanti=adres,
            ref_type="teklif",
            ref_id=teklif.id,
            panel_linki="/client?sekme=invoices",
            degerler={"teklif_no": teklif.no, "tutar": tutar},
        )
    return adres, gitti


async def revize_et(db: AsyncSession, teklif: Teklifler, olusturan: Optional[str]) -> Teklifler:
    """Yeni sürüm (taslak) açar; eskisi `revize`, bağlantısı iptal."""
    if teklif.durum in ("taslak", "kabul", "revize"):
        raise TeklifHatasi(409, f"durum_{teklif.durum}")
    await _baglantiyi_iptal_et(db, teklif)
    kok_id = teklif.kok_id or teklif.id
    kok_no = teklif.no.split("-R")[0]
    son_surum = (
        await db.execute(select(Teklifler.surum).where(Teklifler.kok_id == kok_id).order_by(Teklifler.surum.desc()))
    ).scalars().first() or teklif.surum or 1
    yeni = Teklifler(
        no=f"{kok_no}-R{son_surum + 1}",
        hesap_email=teklif.hesap_email, aday_ad=teklif.aday_ad, aday_eposta=teklif.aday_eposta,
        baslik=teklif.baslik, kalemler=teklif.kalemler, ara_toplam=teklif.ara_toplam,
        indirim_toplam=teklif.indirim_toplam, kdv_toplam=teklif.kdv_toplam, genel_toplam=teklif.genel_toplam,
        para_birimi=teklif.para_birimi,
        gecerlilik=(bo.tr_bugun() + timedelta(days=VARSAYILAN_GECERLILIK_GUN)).isoformat()
        if suresi_gecti_mi(teklif) else teklif.gecerlilik,
        notlar=teklif.notlar, sartlar=teklif.sartlar, durum="taslak", goruntulenme_sayisi=0,
        otomatik_sozlesme=teklif.otomatik_sozlesme, sozlesme_sablon_id=teklif.sozlesme_sablon_id,
        otomatik_fatura=teklif.otomatik_fatura, pesinat_yuzde=teklif.pesinat_yuzde, otomatik_proje=teklif.otomatik_proje,
        proje_sablon_id=teklif.proje_sablon_id,
        pricing_inquiry_id=teklif.pricing_inquiry_id, fatura_id=None,
        kok_id=kok_id, onceki_id=teklif.id, surum=son_surum + 1,
        olusturan_eposta=bo.eposta_duzelt(olusturan) or None, indirim_kodu=teklif.indirim_kodu,
    )
    teklif.durum = "revize"
    db.add(yeni)
    if teklif.indirim_kodu:
        # Faz 5K: kodun kullanımı yeni sürüme geçer (eski sürüm "revize" — sayımda zaten ölü).
        from services import indirim_kodlari as ik

        await db.flush()
        await ik.kullanim_tasi(db, "teklif", teklif.id, yeni.id)
    await db.commit()
    await db.refresh(yeni)
    return yeni


# ---------------------------------------------------------------------------
# Girişsiz sayfa: görüntüleme ve karar
# ---------------------------------------------------------------------------
async def jetondan(db: AsyncSession, jeton: str) -> Tuple[Teklifler, SignedActions]:
    from services import imzali_islem

    kayit = await imzali_islem.coz(db, jeton)
    if kayit is None or kayit.tur != TUR:
        raise TeklifHatasi(404, "bulunamadi")
    teklif = (await db.execute(select(Teklifler).where(Teklifler.id == kayit.hedef_id))).scalar_one_or_none()
    if teklif is None:
        raise TeklifHatasi(404, "bulunamadi")
    return teklif, kayit


async def goruntulendi(db: AsyncSession, teklif: Teklifler) -> None:
    """Sayaç + ilk/son görüntülenme; açık teklif `goruntulendi` olur. Süresi geçen işaretlenir."""
    an = bo.simdi()
    teklif.goruntulenme_sayisi = int(teklif.goruntulenme_sayisi or 0) + 1
    teklif.ilk_goruntulenme = teklif.ilk_goruntulenme or an
    teklif.son_goruntulenme = an
    if teklif.durum in ACIK_DURUMLAR and suresi_gecti_mi(teklif):
        teklif.durum = "suresi_doldu"
    elif teklif.durum == "gonderildi":
        teklif.durum = "goruntulendi"
    await db.commit()
    await db.refresh(teklif)


def karar_on_denetim(teklif: Teklifler, sonuc: str, ad: Optional[str]) -> Dict[str, Any]:
    """Karardan ÖNCE (bağlantı tüketilmeden) — ek bilgi sözlüğü döner."""
    sonuc = (sonuc or "").strip().lower()
    if sonuc not in ("kabul", "red"):
        raise TeklifHatasi(400, "gecersiz_sonuc")
    if teklif.durum in ("kabul", "ret"):
        raise TeklifHatasi(409, "kullanildi")
    if teklif.durum == "revize":
        raise TeklifHatasi(410, "revize")
    if teklif.durum == "suresi_doldu" or suresi_gecti_mi(teklif):
        raise TeklifHatasi(410, "suresi_doldu")
    if teklif.durum not in ACIK_DURUMLAR:
        raise TeklifHatasi(409, f"durum_{teklif.durum}")
    ek: Dict[str, Any] = {}
    if sonuc == "kabul":
        try:
            ek["ad"] = bo.ad_duzelt(ad)
        except ValueError:
            raise TeklifHatasi(400, "ad_gerekli")
    elif ad:
        try:
            ek["ad"] = bo.ad_duzelt(ad)
        except ValueError:
            pass
    return ek


async def karar_ver(
    db: AsyncSession,
    *,
    jeton: Optional[str] = None,
    teklif: Optional[Teklifler] = None,
    eposta: Optional[str] = None,
    sonuc: str,
    ad: Optional[str],
    not_: Optional[str],
    ip_ozeti: Optional[str],
    kanal: str,
) -> Teklifler:
    """Bağlantıyla (jeton) ya da müşteri panelinden (teklif + oturum e-postası) karar."""
    from services import imzali_islem

    if jeton is not None:
        teklif, kayit = await jetondan(db, jeton)
    else:
        if teklif is None or not teklif.islem_id:
            raise TeklifHatasi(409, "baglanti_yok")
        kayit = (await db.execute(select(SignedActions).where(SignedActions.id == teklif.islem_id))).scalar_one_or_none()
        if kayit is None:
            raise TeklifHatasi(409, "baglanti_yok")
    if kayit.id != teklif.islem_id:
        # Eski (yenilenmiş/iptal) bağlantı: karar yalnız geçerli bağlantıdan.
        raise TeklifHatasi(410, "iptal")
    ek = karar_on_denetim(teklif, sonuc, ad)
    ek["kanal"] = kanal
    try:
        if jeton is not None:
            sonuc_ = await imzali_islem.kullan(db, jeton, sonuc, not_, ip_ozeti=ip_ozeti, ek=ek)
        else:
            sonuc_ = await imzali_islem.kullan_id(db, kayit.id, eposta or "", sonuc, not_, ip_ozeti=ip_ozeti, ek=ek)
    except IslemHatasi as h:
        raise TeklifHatasi(h.durum, h.kod)
    await imzali_islem.bildirimleri_gonder(db, sonuc_.bildirimler)
    await db.refresh(teklif)
    return teklif


async def karar_etkisi(
    db: AsyncSession, kayit: SignedActions, sonuc: str, not_: Optional[str], ek: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """`imzali_islem._etkiyi_uygula` içinden: kararı teklife ve otomatik kayıtlara işler (commit ETMEZ)."""
    teklif = (await db.execute(select(Teklifler).where(Teklifler.id == kayit.hedef_id))).scalar_one_or_none()
    if teklif is None:
        raise IslemHatasi(404, "hedef_yok")
    if teklif.durum not in ACIK_DURUMLAR:
        raise IslemHatasi(409, "kullanildi")
    if suresi_gecti_mi(teklif):
        raise IslemHatasi(410, "suresi_doldu")
    an = bo.simdi()
    teklif.karar_at = an
    teklif.karar_notu = not_
    teklif.karar_ip_ozeti = ek.get("ip_ozeti")
    teklif.karar_ad = ek.get("ad")
    olusanlar: List[str] = []
    if sonuc == "kabul":
        if not teklif.karar_ad:
            raise IslemHatasi(400, "ad_gerekli")
        teklif.durum = "kabul"
        teklif.hesap_email = alici(teklif)
        olusanlar = await _kabul_otomasyonu(db, teklif)
    else:
        teklif.durum = "ret"
    if teklif.pricing_inquiry_id:
        from models.pricing import Pricing_inquiries

        talep = (
            await db.execute(select(Pricing_inquiries).where(Pricing_inquiries.id == teklif.pricing_inquiry_id))
        ).scalar_one_or_none()
        if talep is not None:
            talep.durum = "kabul" if sonuc == "kabul" else "red"
            talep.durum_notu = not_ if sonuc == "red" else None
            talep.durum_at = an
    await db.flush()

    from services.pdf_belge import para

    tutar = para(teklif.genel_toplam, teklif.para_birimi, "tr")
    if sonuc == "kabul":
        baslik = f"Teklif kabul edildi: {teklif.no} ({tutar}) — {teklif.karar_ad}"
        govde = f"{teklif.baslik}\nKabul eden: {teklif.karar_ad} ({kayit.alici_eposta})"
        if olusanlar:
            govde += "\nOluşturulanlar: " + ", ".join(olusanlar)
    else:
        baslik = f"Teklif reddedildi: {teklif.no} ({tutar}) — {kayit.alici_eposta}"
        govde = f"{teklif.baslik}\nGerekçe: {not_ or '—'}"
    return [{
        "event_type": "teklif_karar", "title": baslik[:250], "body": govde, "yoneticiye": True,
        "link": "/admin?sekme=teklifler", "ref_type": "teklif", "ref_id": teklif.id,
    }]


async def _kabul_otomasyonu(db: AsyncSession, teklif: Teklifler) -> List[str]:
    """Seçilen otomatik kayıtlar (aynı işlem; commit ETMEZ). Oluşanların kısa listesi."""
    olusanlar: List[str] = []
    if teklif.otomatik_fatura:
        if teklif.fatura_id:
            # Faz 5K: "Teklif al" talebinin faturası teklifin indirimini taşır (ödeme alınmamışsa).
            if await _mevcut_faturaya_indirim(db, teklif):
                olusanlar.append("fatura (mevcut; indirim kodu uygulandı)")
            else:
                olusanlar.append("fatura (mevcut)")
        else:
            fatura = await _ilk_fatura(db, teklif)
            teklif.fatura_id = fatura.id
            olusanlar.append(f"fatura {fatura.invoice_no}")
    if teklif.otomatik_sozlesme and not teklif.sozlesme_id:
        from services.sozlesmeler import tekliften_olustur

        sozlesme = await tekliften_olustur(db, teklif)
        teklif.sozlesme_id = sozlesme.id
        olusanlar.append(f"sözleşme taslağı {sozlesme.no}")
    if teklif.otomatik_proje and not teklif.proje_id:
        from models.projects import Projects

        proje = Projects(
            title=teklif.baslik[:200],
            description=(teklif.notlar or f"{teklif.no} numaralı tekliften")[:2000],
            category="Teklif",
            client_name=teklif.aday_ad,
            client_email=teklif.hesap_email,
            status="planning",
            stage="discovery",
            progress=0,
            published=False,
            created_at=datetime.now(),
        )
        db.add(proje)
        await db.flush()
        teklif.proje_id = proje.id
        olusanlar.append(f"proje #{proje.id}")
        if teklif.proje_sablon_id:
            olusanlar.extend(await _sablonu_uygula(db, teklif, proje))
    return olusanlar


async def _sablonu_uygula(db: AsyncSession, teklif: Teklifler, proje) -> List[str]:
    """Faz 3Z: teklifte seçilen proje şablonunun görevleri (başlangıç = kabul günü).

    Aynı işlemde (commit ETMEZ). Şablon bu arada silinmişse kabul düşmesin:
    proje görevsiz açılır, durum kaydına yazılır.
    """
    from models.zaman_takibi import ProjeSablonlari
    from services import proje_sablonlari

    sablon = (
        await db.execute(select(ProjeSablonlari).where(ProjeSablonlari.id == teklif.proje_sablon_id))
    ).scalar_one_or_none()
    if sablon is None:
        logger.warning("Teklif %s: proje şablonu %s bulunamadı", teklif.no, teklif.proje_sablon_id)
        return []
    try:
        async with db.begin_nested():
            gorevler = await proje_sablonlari.uygula(db, sablon, proje, bo.tr_bugun(), teklif.olusturan_eposta)
    except Exception:  # noqa: BLE001
        logger.exception("Teklif %s: şablon görevleri oluşturulamadı", teklif.no)
        return []
    return [f"şablon «{sablon.ad}» ({len(gorevler)} görev)"]


async def _mevcut_faturaya_indirim(db: AsyncSession, teklif: Teklifler) -> bool:
    """Faz 5K — teklifin önceden bağlı faturası (sitedeki "Teklif al" talebinin faturası) indirim kodunu taşımıyorsa,
    faturayı teklifin indirimli kalemleriyle eşitler: kalemler, toplamlar, para birimi, kod; bekleyen ödeme
    bağlantısı yeni tutara çekilir (sağlayıcıda açılmışsa iptal → yeni bağlantı). Ödeme alınmış, iptal edilmiş ya da
    iade faturasına dokunulmaz. Kullanım teklifte sayıldı; fatura yalnız kodu taşır. Commit ETMEZ."""
    from models.invoices import Invoices
    from services import faturalar as fs

    if not teklif.indirim_kodu or not teklif.fatura_id:
        return False
    f = (await db.execute(select(Invoices).where(Invoices.id == teklif.fatura_id))).scalars().first()
    if f is None or (f.tur or "") == "iade" or (f.status or "") in ("paid", "cancelled", "iptal", "kismi_odendi"):
        return False
    if f.indirim_kodu == teklif.indirim_kodu:
        return False
    if (await fs.bakiye(db, f)).odenen > 0:
        return False
    kalemler = [{k: v for k, v in kalem.items()
                 if k in ("aciklama", "adet", "birim_fiyat", "kdv_orani", "indirim", "indirim_kodu")}
                for kalem in kayitli_kalemler(teklif.kalemler)]
    belge = belge_hesapla(kalemler)
    f.kalemler = json.dumps(belge.kalem_listesi(), ensure_ascii=False)
    f.ara_toplam = float(belge.ara_toplam)
    f.kdv_toplam = float(belge.kdv_toplam)
    f.amount = float(belge.genel_toplam)
    f.currency = teklif.para_birimi or f.currency
    f.indirim_kodu = teklif.indirim_kodu
    f.teklif_id = f.teklif_id or teklif.id
    _, b = await fs.durumu_guncelle(db, f)
    await fs.bekleyen_baglantiyi_esitle(db, f, b)
    await db.flush()
    return True


async def _ilk_fatura(db: AsyncSession, teklif: Teklifler):
    """Peşinat yüzdesi kadar ilk fatura + bekleyen ödeme bağlantısı."""
    from models.invoices import Invoices
    from models.payments import Payments
    from services.faturalar import VARSAYILAN_VADE_GUN, yeni_fatura_no

    kalemler = kayitli_kalemler(teklif.kalemler)
    yuzde = Decimal(str(teklif.pesinat_yuzde)) if teklif.pesinat_yuzde is not None else Decimal("100")
    if yuzde < 100:
        belge = belge_hesapla(kalemler)
        kalemler = oranla_bol(belge, yuzde, f"Peşinat %{yuzde.normalize():f} — {teklif.no} (KDV %{{oran}})")
        aciklama = f"{teklif.baslik} — peşinat %{yuzde.normalize():f} ({teklif.no})"
    else:
        kalemler = [{k: v for k, v in kalem.items()
                     if k in ("aciklama", "adet", "birim_fiyat", "kdv_orani", "indirim", "indirim_kodu")}
                    for kalem in kalemler]
        aciklama = f"{teklif.baslik} ({teklif.no})"
    belge = belge_hesapla(kalemler)
    bugun = bo.tr_bugun()
    fatura = Invoices(
        invoice_no=yeni_fatura_no("TKF"),
        client_name=teklif.aday_ad,
        client_email=teklif.hesap_email,
        description=aciklama[:300],
        amount=float(belge.genel_toplam),
        currency=teklif.para_birimi or "TRY",
        status="unpaid",
        issue_date=bugun.isoformat(),
        due_date=(bugun + timedelta(days=VARSAYILAN_VADE_GUN)).isoformat(),
        kalemler=json.dumps(belge.kalem_listesi(), ensure_ascii=False),
        ara_toplam=float(belge.ara_toplam),
        kdv_toplam=float(belge.kdv_toplam),
        teklif_id=teklif.id,
        # Faz 5K: kullanım teklifte sayıldı; fatura yalnız kodu taşır (komisyonda ortak bağı için).
        indirim_kodu=teklif.indirim_kodu,
    )
    db.add(fatura)
    await db.flush()
    db.add(Payments(
        invoice_id=fatura.id, invoice_no=fatura.invoice_no, client_email=fatura.client_email,
        jeton=secrets.token_urlsafe(9), tutar=fatura.amount, para_birimi=fatura.currency, durum="bekliyor",
    ))
    await db.flush()
    return fatura


# ---------------------------------------------------------------------------
# Fiyat sihirbazından
# ---------------------------------------------------------------------------
async def fiyat_talebinden(db: AsyncSession, talep_id: int, olusturan: Optional[str]) -> Teklifler:
    """`pricing_inquiries` kaydını biçimli teklife çevirir (taslak; fatura bağı korunur)."""
    from models.pricing import Ai_pm_tiers, Pricing_inquiries, Pricing_profiles, Pricing_scales

    talep = (await db.execute(select(Pricing_inquiries).where(Pricing_inquiries.id == talep_id))).scalar_one_or_none()
    if talep is None:
        raise TeklifHatasi(404, "talep_yok")
    mevcut = (
        await db.execute(select(Teklifler).where(Teklifler.pricing_inquiry_id == talep_id).order_by(Teklifler.id.desc()))
    ).scalars().first()
    if mevcut is not None and mevcut.durum != "revize":
        raise TeklifHatasi(409, "zaten_teklif", teklif_id=mevcut.id)

    async def _ad(model, kod):
        if not kod:
            return None
        satir = (await db.execute(select(model).where(model.kod == kod))).scalars().first()
        return satir.ad if satir is not None else kod

    try:
        eklentiler = [str(e) for e in json.loads(talep.addon_ids or "[]") if e]
    except (TypeError, ValueError):
        eklentiler = []
    donem = {"aylik": "aylık", "yillik": "yıllık", "kullandikca_ode": "kullandıkça öde"}.get(talep.period or "", talep.period or "")
    if talep.period == "kullandikca_ode":
        kredi = next((e.split(":", 1)[1] for e in eklentiler if e.startswith("kredi_paketi:")), "")
        aciklama = f"Kullandıkça Öde — {kredi} kredi paketi"
    else:
        parcalar = [p for p in (await _ad(Pricing_scales, talep.scale_kod), await _ad(Pricing_profiles, talep.profile_kod)) if p]
        ai_pm = await _ad(Ai_pm_tiers, talep.ai_pm_tier_kod)
        if ai_pm:
            parcalar.append(f"AI vs PM {ai_pm}")
        aciklama = " / ".join(parcalar) or "Hizmet paketi"
        if donem:
            aciklama += f" ({donem})"
        if eklentiler:
            aciklama += " + " + ", ".join(eklentiler)
    govde = {
        "baslik": aciklama[:BASLIK_SINIRI],
        "kalemler": [{"aciklama": aciklama, "adet": 1, "birim_fiyat": float(talep.hesaplanan_tutar or 0),
                      "kdv_orani": 0, "indirim": 0}],
        "para_birimi": "USD",
        "hesap_email": talep.musteri_eposta,
        "aday_ad": talep.musteri_adi,
        "notlar": "Fiyat sihirbazındaki seçiminizden hazırlanmıştır.",
        "pricing_inquiry_id": talep.id,
        # Sihirbaz zaten faturayı açmıştı: kabulde ikinci fatura açılmasın.
        "fatura_id": talep.invoice_id,
        "otomatik_fatura": bool(talep.invoice_id),
    }
    # Faz 5K: "Teklif al" formunda girilen indirim kodu (CRM adayında) — hâlâ geçerliyse uygulanır
    # (hizmet paketi kapsamı da sayılır); değilse teklif kodsuz açılır.
    from services.pazarlama_izni import bagli_adayi_bul

    aday_id = await bagli_adayi_bul(db, "pricing_inquiries", talep.id)
    if aday_id:
        from models.crm import CrmAdaylari

        kod = (await db.execute(select(CrmAdaylari.indirim_kodu).where(CrmAdaylari.id == aday_id))).scalar()
        if kod:
            try:
                return await olustur(db, {**govde, "indirim_kodu": kod, "_ek_kapsam": ("paket",)}, olusturan)
            except TeklifHatasi as h:
                if not (h.kod.startswith("kod_") or h.kod == "kendi_referansi"):
                    raise
                await db.rollback()
    return await olustur(db, govde, olusturan)


# ---------------------------------------------------------------------------
# Görünümler
# ---------------------------------------------------------------------------
def ozet(teklif: Teklifler) -> Dict[str, Any]:
    kalemler = kayitli_kalemler(teklif.kalemler)
    try:
        dokum = belge_hesapla(kalemler, bos_olabilir=True).kdv_dokumu
    except HesapHatasi:
        dokum = []
    return {
        "ara_toplam": _decimal_float(teklif.ara_toplam),
        "indirim_toplam": _decimal_float(teklif.indirim_toplam),
        "kdv_toplam": _decimal_float(teklif.kdv_toplam),
        "genel_toplam": _decimal_float(teklif.genel_toplam),
        "kdv_dokumu": dokum,
    }


def sozluk(teklif: Teklifler, *, yonetici: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": teklif.id,
        "no": teklif.no,
        "baslik": teklif.baslik,
        "kalemler": kayitli_kalemler(teklif.kalemler),
        "ozet": ozet(teklif),
        "para_birimi": teklif.para_birimi,
        "gecerlilik": teklif.gecerlilik,
        "notlar": teklif.notlar,
        "sartlar": teklif.sartlar,
        "durum": teklif.durum,
        "surum": teklif.surum or 1,
        "musteri_ad": teklif.aday_ad,
        "karar_at": bo.iso(teklif.karar_at),
        "karar_ad": teklif.karar_ad,
        "karar_notu": teklif.karar_notu,
        "fatura_id": teklif.fatura_id,
        "sozlesme_id": teklif.sozlesme_id,
        "proje_id": teklif.proje_id,
        "indirim_kodu": teklif.indirim_kodu,
        "tarih": (bo.utc(teklif.gonderildi_at) or bo.utc(teklif.created_at) or bo.simdi()).date().isoformat(),
        "created_at": bo.iso(teklif.created_at),
    }
    if yonetici:
        d.update({
            "hesap_email": teklif.hesap_email,
            "aday_eposta": teklif.aday_eposta,
            "goruntulenme_sayisi": int(teklif.goruntulenme_sayisi or 0),
            "ilk_goruntulenme": bo.iso(teklif.ilk_goruntulenme),
            "son_goruntulenme": bo.iso(teklif.son_goruntulenme),
            "gonderildi_at": bo.iso(teklif.gonderildi_at),
            "karar_ip_ozeti": (teklif.karar_ip_ozeti or "")[:16] or None,
            "otomatik_sozlesme": bool(teklif.otomatik_sozlesme),
            "sozlesme_sablon_id": teklif.sozlesme_sablon_id,
            "otomatik_fatura": bool(teklif.otomatik_fatura),
            "pesinat_yuzde": _decimal_float(teklif.pesinat_yuzde),
            "otomatik_proje": bool(teklif.otomatik_proje),
            "proje_sablon_id": teklif.proje_sablon_id,
            "pricing_inquiry_id": teklif.pricing_inquiry_id,
            "islem_id": teklif.islem_id,
            "kok_id": teklif.kok_id,
            "onceki_id": teklif.onceki_id,
            "olusturan_eposta": teklif.olusturan_eposta,
        })
    else:
        d["musteri_eposta"] = None
    return d


def pdf_verisi(teklif: Teklifler) -> Dict[str, Any]:
    d = sozluk(teklif)
    d["musteri_eposta"] = alici(teklif) or None
    return d


async def pdf(db: AsyncSession, teklif: Teklifler, dil: str = "tr") -> bytes:
    from services.faturalar import ajans_bilgileri
    from services.pdf_belge import teklif_pdf

    return teklif_pdf(pdf_verisi(teklif), await ajans_bilgileri(db), dil)
