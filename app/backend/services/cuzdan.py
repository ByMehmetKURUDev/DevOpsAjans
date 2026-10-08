"""Faz 5C — Cüzdan ve bakiye (müşteri avansı): iş kuralları.

Model ve kavramlar `models/cuzdan.py`'de; uçlar `routers/cuzdan.py`'de, ekstre PDF'i `services/cuzdan_pdf.py`'de.

Hukuki çerçeve (arayüzde 7 dilde kısa not)
------------------------------------------
Bakiye yalnız ajansın KENDİ hizmetlerinin bedeli için verilmiş avanstır; üçüncü kişilere ödeme aracı ya da
elektronik para değildir (6493 sayılı Kanun kapsamında bir ödeme hizmeti sunulmuyor: para yalnız ajansın kendi
alacağına mahsup ediliyor), faiz işlemez, devredilemez; kullanılmayan bakiye talep üzerine ajans tarafından ELLE iade
edilir. Bilgilendirme amaçlıdır, hukuki danışmanlık değildir.

Para
----
Cüzdan tutarları KURUŞ (int; ön muhasebe ile aynı), fatura tarafı Decimal (`services/faturalar.py`). Dönüşüm YALNIZ
burada: `kurusa` (TL → kuruş, yarım yukarı) / `ondaliga` (kuruş → Decimal). Para birimi dönüşümü yok; fatura
yalnız aynı para birimindeki bakiyeden ödenir.

Eşzamanlılık ve tekillik
------------------------
* Bakiye düşüşü KOŞULLU güncelleme: `UPDATE ... SET bakiye = bakiye - x WHERE id = ? AND bakiye >= x`. Postgres'te
  satır kilidi, SQLite'ta yazma kilidi: aynı bakiyeyi kullanan iki istekten ikincisi güncel bakiyeyi görür → 409
  `bakiye_yetersiz`. Ayrıca tabloda `CHECK (bakiye >= 0)`.
* Defter satırı `tekil` benzersiz: aynı fatura için aynı istek anahtarı (`harcama:<fatura>:<anahtar>`), talep onayı
  (`talep:<id>`), ters kayıt (`ters:<id>`), silinen ödemenin defterdeki aslı (`odeme_sil:<hareket>`) iki kez
  yazılamaz. Aynı istek ikinci kez gelirse ilk sonucun kendisi döner (yeni harcama yok).

Tahsilat yolu TEK
-----------------
Bakiyeden ödeme ikinci bir ödeme sistemi değil: `faturalar.odeme_ekle(..., yontem="bakiye")` bir `payments`
satırı yazar → fatura durumu (kısmi/ödendi), `fatura.odendi` olayı (webhook + otomasyon + ortaklık komisyonu), kredi
paketi, müşteri sitesi, makbuz/PDF ve denetim bugünkü gibi çalışır. Ödeme satırı silinirse (`faturalar.odeme_sil`)
ya da iade faturası fazla ödeme doğurursa (`faturalar.iade_faturasi_kes`) bakiyeye ters kayıt yazılır.

Genişleme noktası (çevrim içi yükleme)
--------------------------------------
Bugün yükleme yalnız elle (yönetici) ya da müşteri bildirimi + yönetici onayı ile. iyzico / PayTR bağlandığında
sağlayıcının DOĞRULANMIŞ bildirimi `yukle(..., yontem="iyzico", kaynak="cevrimici", tekil="saglayici:<ref>")`
çağırmalı — defter, olay, bildirim ve ön muhasebe yansıması (`çevrim içi` hesabına tahsilat) aynı kalır.
"""

import csv
import io
import logging
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.cuzdan import (
    CuzdanAyarlari,
    CuzdanHareketleri,
    CuzdanHesaplari,
    CuzdanOtomatikIzleri,
    CuzdanYuklemeTalepleri,
)
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")
YUKLEME_YONTEMLERI: Tuple[str, ...] = ("havale", "eft", "nakit", "diger")
#: `payments.saglayici` ve harcama satırının yöntemi.
BAKIYE_YONTEMI = "bakiye"
#: Tek işlemde en çok (kuruş): 10 milyon.
EN_COK_TUTAR = 1_000_000_000
EN_COK_BEKLEYEN_TALEP = 5
NOT_SINIRI = 1000
GEREKCE_SINIRI = 500
SAYFA_ADET = 50
#: Otomatik ödeme açılırken gösterilen onay metninin sürümü (metin değişirse artır).
ONAY_METNI_SURUMU = "2026-10"
OTOMATIK_ZAMANLAR: Tuple[str, ...] = ("kesilince", "vadesinde")
REFERANS_ALFABESI = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MUSTERI_BAGLANTISI = "/client?sekme=invoices&bolum=bakiye"
YONETICI_BAGLANTISI = "/admin?sekme=odeme&bolum=bakiyeler"
#: Otomasyon / webhook olayları.
OLAY_YUKLENDI = "bakiye.yuklendi"
OLAY_HARCANDI = "bakiye.harcandi"
#: Bildirim olayları (`services/bildirim_tercih.py`).
BILDIRIM_TALEP = "bakiye_talebi"
BILDIRIM_YUKLEME = "bakiye_yukleme"
BILDIRIM_HARCAMA = "bakiye_harcama"
BILDIRIM_DUSUK = "bakiye_dusuk"
BILDIRIM_IADE = "bakiye_iade"
#: Yönetici ayarları (site_settings) — müşteriye gösterilen havale bilgisi. Boşsa fatura ayarlarındaki unvan/IBAN.
BANKA_ANAHTARLARI = {
    "banka_adi": ("cuzdan_banka_adi", "Bakiye: banka adı"),
    "hesap_sahibi": ("cuzdan_hesap_sahibi", "Bakiye: hesap sahibi"),
    "iban": ("cuzdan_iban", "Bakiye: IBAN"),
    "aciklama": ("cuzdan_havale_notu", "Bakiye: havale notu"),
}
ACIK_FATURA_DISI = ("paid", "cancelled", "iade", "draft", "taslak", "iptal")


class CuzdanHatasi(Exception):
    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


# ---------------------------------------------------------------------------
# Yardımcılar ve dönüşüm (tek yer)
# ---------------------------------------------------------------------------
def simdi() -> datetime:
    return datetime.now(timezone.utc)


def bugun() -> date:
    from services.faturalar import tr_bugun

    return tr_bugun()


def eposta_duzelt(e: Any) -> str:
    return str(e or "").strip().lower()


def kurusa(deger: Any, kod: str = "tutar_gecersiz") -> int:
    """TL (Decimal / metin / sayı) → kuruş, yarım yukarı. Fatura ↔ cüzdan dönüşümünün TEK yeri."""
    from services.belge_hesap import HesapHatasi, ondalik

    try:
        d = ondalik(deger, kod)
    except HesapHatasi:
        raise CuzdanHatasi(400, kod)
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def ondaliga(kurus: Any) -> Decimal:
    """Kuruş → TL (Decimal, 2 hane)."""
    return (Decimal(int(kurus or 0)) / Decimal(100)).quantize(Decimal("0.01"))


def tl(kurus: Any) -> float:
    return float(ondaliga(kurus))


def tutar_al(deger: Any, *, isaretli: bool = False) -> int:
    k = kurusa(deger)
    if isaretli:
        if k == 0 or abs(k) > EN_COK_TUTAR:
            raise CuzdanHatasi(400, "tutar_gecersiz")
    elif k <= 0 or k > EN_COK_TUTAR:
        raise CuzdanHatasi(400, "tutar_gecersiz")
    return k


def para_birimi_al(deger: Any) -> str:
    pb = str(deger or "TRY").strip().upper()
    if pb not in PARA_BIRIMLERI:
        raise CuzdanHatasi(400, "para_birimi_gecersiz")
    return pb


def yontem_al(deger: Any) -> str:
    y = str(deger or "havale").strip().lower()
    if y == "elden":
        y = "nakit"
    if y not in YUKLEME_YONTEMLERI:
        raise CuzdanHatasi(400, "yontem_gecersiz")
    return y


def tarih_al(deger: Any, kod: str = "tarih_gecersiz") -> date:
    if deger in (None, ""):
        return bugun()
    if isinstance(deger, date):
        g = deger
    else:
        try:
            g = date.fromisoformat(str(deger).strip()[:10])
        except ValueError:
            raise CuzdanHatasi(400, kod)
    if g > bugun() + timedelta(days=1):
        raise CuzdanHatasi(400, "tarih_gelecekte")
    if g < bugun() - timedelta(days=3 * 366):
        raise CuzdanHatasi(400, kod)
    return g


def metin_al(deger: Any, sinir: int = NOT_SINIRI) -> Optional[str]:
    m = str(deger or "").strip()
    return m[:sinir] or None


def istek_anahtari_al(deger: Any) -> Optional[str]:
    if deger in (None, ""):
        return None
    a = str(deger).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", a):
        raise CuzdanHatasi(400, "istek_anahtari_gecersiz")
    return a


def _iso(an: Any) -> Optional[str]:
    if an is None:
        return None
    if isinstance(an, datetime):
        a = an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)
        return a.isoformat().replace("+00:00", "Z")
    return an.isoformat() if hasattr(an, "isoformat") else str(an)


# ---------------------------------------------------------------------------
# Cüzdan satırı ve bakiye
# ---------------------------------------------------------------------------
async def cuzdan_satiri(db: AsyncSession, eposta: str, pb: str, *, olustur: bool = True) -> Optional[CuzdanHesaplari]:
    """(hesap, para birimi) cüzdanı; yoksa açar (eşzamanlı ilk açılışta benzersiz kısıt → var olan okunur)."""
    sorgu = select(CuzdanHesaplari).where(CuzdanHesaplari.hesap_email == eposta, CuzdanHesaplari.para_birimi == pb)
    c = (await db.execute(sorgu)).scalars().first()
    if c is not None or not olustur:
        return c
    try:
        async with db.begin_nested():
            c = CuzdanHesaplari(hesap_email=eposta, para_birimi=pb, bakiye=0, surum=0, created_at=simdi())
            db.add(c)
            await db.flush()
    except IntegrityError:
        c = (await db.execute(sorgu)).scalars().first()
    return c


async def _bakiye_sql(db: AsyncSession, cuzdan_id: int) -> int:
    return int((await db.execute(select(CuzdanHesaplari.bakiye).where(CuzdanHesaplari.id == cuzdan_id))).scalar() or 0)


async def bakiye_oku(db: AsyncSession, eposta: str, pb: str) -> int:
    v = (await db.execute(select(CuzdanHesaplari.bakiye).where(
        CuzdanHesaplari.hesap_email == eposta, CuzdanHesaplari.para_birimi == pb))).scalar()
    return int(v or 0)


async def _bakiye_degistir(db: AsyncSession, c: CuzdanHesaplari, tutar: int) -> int:
    """Koşullu güncelleme: düşüşte `bakiye >= -tutar` şartı (eksi bakiye yok, aynı bakiye iki kez harcanmaz).
    Yeni bakiyeyi döner; yetersizse 409 `bakiye_yetersiz` (çağıran geri alır)."""
    an = simdi()
    kosul = [CuzdanHesaplari.id == c.id]
    if tutar < 0:
        kosul.append(CuzdanHesaplari.bakiye >= -tutar)
    r = await db.execute(
        update(CuzdanHesaplari).where(*kosul)
        .values(bakiye=CuzdanHesaplari.bakiye + tutar, surum=CuzdanHesaplari.surum + 1, son_hareket_at=an, updated_at=an)
        .execution_options(synchronize_session=False)
    )
    if not r.rowcount:
        mevcut = await _bakiye_sql(db, c.id)
        raise CuzdanHatasi(409, "bakiye_yetersiz", bakiye=tl(mevcut), para_birimi=c.para_birimi)
    return await _bakiye_sql(db, c.id)


async def _satir_ekle(db: AsyncSession, c: CuzdanHesaplari, *, tur: str, tutar: int, sonra: int, tarih: date,
                      yazan: Optional[str], yazan_rol: str, **alanlar: Any) -> CuzdanHareketleri:
    h = CuzdanHareketleri(cuzdan_id=c.id, hesap_email=c.hesap_email, para_birimi=c.para_birimi, tur=tur, tutar=int(tutar),
                          sonra=int(sonra), tarih=tarih, yazan=eposta_duzelt(yazan) or None, yazan_rol=yazan_rol,
                          created_at=simdi(), **alanlar)
    db.add(h)
    try:
        await db.flush()
    except IntegrityError:
        # Aynı iş anahtarı (tekil) başka bir istekte yazıldı — çağıran geri alır ve ilk sonucu döner.
        raise CuzdanHatasi(409, "tekrar_istek")
    return h


async def hareket_yaz(db: AsyncSession, *, eposta: str, pb: str, tur: str, tutar: int, tarih: Optional[date] = None,
                      yazan: Optional[str], yazan_rol: str = "admin", **alanlar: Any) -> CuzdanHareketleri:
    """Bakiye değişimi + defter satırı (commit ETMEZ). `tutar` işaretli kuruş."""
    tekil = alanlar.get("tekil")
    if tekil and await tekil_bul(db, tekil) is not None:
        raise CuzdanHatasi(409, "tekrar_istek")
    c = await cuzdan_satiri(db, eposta, pb)
    sonra = await _bakiye_degistir(db, c, tutar)
    return await _satir_ekle(db, c, tur=tur, tutar=tutar, sonra=sonra, tarih=tarih or bugun(), yazan=yazan,
                             yazan_rol=yazan_rol, **alanlar)


async def tekil_bul(db: AsyncSession, tekil: str) -> Optional[CuzdanHareketleri]:
    return (await db.execute(select(CuzdanHareketleri).where(CuzdanHareketleri.tekil == tekil))).scalars().first()


async def terslenenler(db: AsyncSession, idler: Iterable[int]) -> Dict[int, int]:
    """Aslı → ters kaydı (yalnız `ters:<id>` ile tam ters çevrilenler)."""
    liste = sorted({int(i) for i in idler})
    if not liste:
        return {}
    satirlar = (await db.execute(select(CuzdanHareketleri.bagli_id, CuzdanHareketleri.id).where(
        CuzdanHareketleri.tur == "ters_kayit", CuzdanHareketleri.bagli_id.in_(liste),
        CuzdanHareketleri.tekil.like("ters:%")))).all()
    return {int(b): int(i) for b, i in satirlar}


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def hareket_sozlugu(h: CuzdanHareketleri, *, yonetici: bool, fatura_no: Optional[str] = None,
                    ters_id: Optional[int] = None) -> Dict[str, Any]:
    d = {
        "id": h.id, "tur": h.tur, "tutar": tl(h.tutar), "sonra": tl(h.sonra), "para_birimi": h.para_birimi,
        "tarih": h.tarih.isoformat() if h.tarih else None, "yontem": h.yontem, "fatura_id": h.fatura_id,
        "fatura_no": fatura_no, "talep_id": h.talep_id, "bagli_id": h.bagli_id, "notu": h.notu, "gerekce": h.gerekce,
        "yazan_rol": h.yazan_rol, "dekont_var": bool(h.dekont_dosya_id), "created_at": _iso(h.created_at),
        "ters_edildi": ters_id is not None, "ters_id": ters_id,
    }
    if yonetici:
        d.update({"yazan": h.yazan, "hesap_email": h.hesap_email, "odeme_id": h.odeme_id,
                  "ters_edilebilir": h.tur in ("yukleme", "iade", "duzeltme") and ters_id is None})
    return d


def talep_sozlugu(t: CuzdanYuklemeTalepleri, *, yonetici: bool, ad: Optional[str] = None) -> Dict[str, Any]:
    d = {
        "id": t.id, "para_birimi": t.para_birimi, "tutar": tl(t.tutar), "yontem": t.yontem,
        "odeme_tarihi": t.odeme_tarihi.isoformat() if t.odeme_tarihi else None, "referans": t.referans,
        "dekont_var": bool(t.dekont_dosya_id), "notu": t.notu, "durum": t.durum, "ret_nedeni": t.ret_nedeni,
        "karar_at": _iso(t.karar_at), "created_at": _iso(t.created_at), "hareket_id": t.hareket_id,
    }
    if yonetici:
        d.update({"hesap_email": t.hesap_email, "kisi_email": t.kisi_email, "karar_veren": t.karar_veren, "ad": ad})
    return d


def cuzdan_sozlugu(c: CuzdanHesaplari, ad: Optional[str] = None) -> Dict[str, Any]:
    return {"id": c.id, "hesap_email": c.hesap_email, "ad": ad, "para_birimi": c.para_birimi, "bakiye": tl(c.bakiye),
            "dusuk_esik": tl(c.dusuk_esik) if c.dusuk_esik is not None else None,
            "dusuk_uyari": c.dusuk_uyari_at is not None, "son_hareket_at": _iso(c.son_hareket_at)}


async def fatura_nolari(db: AsyncSession, idler: Iterable[Optional[int]]) -> Dict[int, str]:
    from models.invoices import Invoices

    liste = sorted({int(i) for i in idler if i})
    if not liste:
        return {}
    return {int(i): n for i, n in (await db.execute(select(Invoices.id, Invoices.invoice_no).where(Invoices.id.in_(liste)))).all()}


async def hareketler(db: AsyncSession, eposta: str, pb: Optional[str], *, yonetici: bool, sayfa: int = 1,
                     adet: int = SAYFA_ADET) -> Dict[str, Any]:
    kosul = [CuzdanHareketleri.hesap_email == eposta]
    if pb:
        kosul.append(CuzdanHareketleri.para_birimi == pb)
    toplam = int((await db.execute(select(func.count(CuzdanHareketleri.id)).where(*kosul))).scalar() or 0)
    adet = max(1, min(int(adet or SAYFA_ADET), 200))
    sayfa = max(1, int(sayfa or 1))
    satirlar = (await db.execute(select(CuzdanHareketleri).where(*kosul).order_by(CuzdanHareketleri.id.desc())
                                 .offset((sayfa - 1) * adet).limit(adet))).scalars().all()
    nolar = await fatura_nolari(db, (h.fatura_id for h in satirlar))
    ters = await terslenenler(db, (h.id for h in satirlar))
    return {"items": [hareket_sozlugu(h, yonetici=yonetici, fatura_no=nolar.get(h.fatura_id or 0), ters_id=ters.get(h.id))
                      for h in satirlar], "toplam": toplam, "sayfa": sayfa, "adet": adet}


# ---------------------------------------------------------------------------
# Ayarlar (hesap) ve banka bilgisi (ajans)
# ---------------------------------------------------------------------------
def _yeni_referans() -> str:
    return "BKY-" + "".join(secrets.choice(REFERANS_ALFABESI) for _ in range(6))


async def ayar_al(db: AsyncSession, eposta: str, *, olustur: bool = True) -> Optional[CuzdanAyarlari]:
    """Hesabın cüzdan ayarı; yoksa açar (benzersiz referans kodu ile — commit ÇAĞIRANA)."""
    sorgu = select(CuzdanAyarlari).where(CuzdanAyarlari.hesap_email == eposta)
    a = (await db.execute(sorgu)).scalars().first()
    if a is not None or not olustur:
        return a
    for _ in range(5):
        try:
            async with db.begin_nested():
                a = CuzdanAyarlari(hesap_email=eposta, referans=_yeni_referans(), otomatik_odeme=False, otomatik_kismi=False,
                                   otomatik_zaman="kesilince", created_at=simdi())
                db.add(a)
                await db.flush()
            return a
        except IntegrityError:
            a = (await db.execute(sorgu)).scalars().first()
            if a is not None:
                return a
    raise CuzdanHatasi(409, "eszamanli")


def ayar_sozlugu(a: Optional[CuzdanAyarlari]) -> Dict[str, Any]:
    return {
        "referans": a.referans if a else None,
        "otomatik_odeme": bool(a.otomatik_odeme) if a else False,
        "otomatik_kismi": bool(a.otomatik_kismi) if a else False,
        "otomatik_zaman": (a.otomatik_zaman if a else None) or "kesilince",
        "otomatik_baslangic": _iso(a.otomatik_baslangic) if a else None,
        "onay_metni_surumu": a.onay_metni_surumu if a else None,
        "guncel_onay_metni_surumu": ONAY_METNI_SURUMU,
    }


async def banka_bilgisi(db: AsyncSession) -> Dict[str, Any]:
    """Müşteriye gösterilen havale bilgisi. Cüzdan ayarı boşsa fatura ayarlarındaki unvan / IBAN (PDF'tekiyle aynı).
    Hiçbiri yoksa `var` False — arayüz "yönetici henüz banka bilgisi girmedi" der."""
    from models.site_settings import Site_settings
    from services.faturalar import ajans_bilgileri

    anahtarlar = [k for k, _ in BANKA_ANAHTARLARI.values()]
    degerler = {s.setting_key: (s.setting_value or "").strip() for s in (await db.execute(
        select(Site_settings).where(Site_settings.setting_key.in_(anahtarlar)))).scalars().all()}
    ajans = await ajans_bilgileri(db)
    sonuc = {alan: degerler.get(anahtar) or "" for alan, (anahtar, _) in BANKA_ANAHTARLARI.items()}
    if not sonuc["iban"]:
        sonuc["iban"] = ajans.get("iban") or ""
    if not sonuc["hesap_sahibi"]:
        sonuc["hesap_sahibi"] = ajans.get("unvan") or ""
    sonuc["var"] = bool(sonuc["iban"])
    return sonuc


async def banka_bilgisi_yaz(db: AsyncSession, veri: Dict[str, Any]) -> Dict[str, Any]:
    """Yönetici: cüzdana özgü havale bilgisi (boş bırakılan alan fatura ayarına düşer). Commit EDER."""
    from models.site_settings import Site_settings
    from services import muhasebe as m

    for alan, deger in veri.items():
        if alan not in BANKA_ANAHTARLARI:
            continue
        anahtar, etiket = BANKA_ANAHTARLARI[alan]
        if alan == "iban":
            try:
                temiz = m.iban_duzelt(deger) or ""
            except m.TemelHata:
                raise CuzdanHatasi(400, "iban_gecersiz")
        elif alan == "aciklama":
            temiz = str(deger or "").strip()[:500]
        else:
            temiz = " ".join(str(deger or "").split())[:160]
        satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == anahtar))).scalars().first()
        if satir is None:
            db.add(Site_settings(setting_key=anahtar, setting_value=temiz, group_name="cuzdan", label=etiket))
        else:
            satir.setting_value = temiz
    await db.commit()
    return await banka_bilgisi(db)


# ---------------------------------------------------------------------------
# Dekont (mevcut dosya deposu deseni: müşterinin "Dekontlar" klasörü)
# ---------------------------------------------------------------------------
async def dekont_kaydet(db: AsyncSession, eposta: str, dosya: Any, yukleyen: Optional[str], rol: str) -> Optional[int]:
    if dosya is None or not (getattr(dosya, "filename", "") or "").strip():
        return None
    from services import dosyalar as ds
    from services.faturalar import DEKONT_KLASORU, DEKONT_TURLERI

    try:
        veri = await ds.akistan_oku(dosya, await ds.boyut_siniri_bayt(db))
        await ds.klasor_hazirla(db, eposta, DEKONT_KLASORU, "musteri")
        kayit = await ds.dosya_kaydet(db, eposta=eposta, klasor=DEKONT_KLASORU, ad_ham=getattr(dosya, "filename", None) or "dekont.pdf",
                                      veri=veri, yukleyen=eposta_duzelt(yukleyen) or None, yukleyen_rol=rol,
                                      izinli=DEKONT_TURLERI)
    except ds.DosyaHatasi as h:
        raise CuzdanHatasi(h.durum, h.kod, **getattr(h, "ek", {}))
    return kayit.id


# ---------------------------------------------------------------------------
# Olay ve bildirim
# ---------------------------------------------------------------------------
async def _olay(db: AsyncSession, tur: str, h: CuzdanHareketleri, **ek: Any) -> None:
    from services import webhook

    veri = {"hareket_id": h.id, "tur": h.tur, "tutar": tl(abs(int(h.tutar))), "para_birimi": h.para_birimi,
            "bakiye": tl(h.sonra), **ek}
    await webhook.olay_yayinla(db, tur, h.hesap_email, veri)


def para_metni(kurus: int, pb: str, dil: str = "tr") -> str:
    """Kuruş → yerel biçimli tutar (bildirim, gelen kutusu başlığı)."""
    from services.pdf_belge import para

    return para(ondaliga(kurus), pb, dil)


_para = para_metni


async def _bildir(db: AsyncSession, olay: str, alicilar: List[Dict[str, Any]], baslik: str, govde: str, link: str,
                  degerler: Dict[str, Any], ref_type: str, ref_id: Optional[int]) -> None:
    """Commit'ten SONRA çağrılır (`dispatch` kendi commit eder). Hata yutar."""
    try:
        from services.notify import dispatch, render

        b, g = await render(db, olay, baslik, govde, degerler)
        await dispatch(db, event_type=olay, title=b, body=g, recipients=alicilar, link=link, ref_type=ref_type, ref_id=ref_id)
    except Exception:  # noqa: BLE001
        logger.exception("Cüzdan bildirimi gönderilemedi (%s)", olay)


def _musteri(eposta: str) -> List[Dict[str, Any]]:
    return [{"email": eposta, "role": "client"}]


async def dusuk_bakiye_denetle(db: AsyncSession, eposta: str, pb: str) -> bool:
    """Eşik altına inildiyse BİR kez bildirim (koşullu işaret); eşiğe ya da üstüne çıkınca işaret silinir. Commit EDER."""
    an = simdi()
    C = CuzdanHesaplari
    temel = [C.hesap_email == eposta, C.para_birimi == pb, C.dusuk_esik.isnot(None)]
    await db.execute(update(C).where(*temel, C.bakiye >= C.dusuk_esik, C.dusuk_uyari_at.isnot(None))
                     .values(dusuk_uyari_at=None).execution_options(synchronize_session=False))
    r = await db.execute(update(C).where(*temel, C.bakiye < C.dusuk_esik, C.dusuk_uyari_at.is_(None))
                         .values(dusuk_uyari_at=an).execution_options(synchronize_session=False))
    await db.commit()
    if not r.rowcount:
        return False
    satir = (await db.execute(select(C.id, C.bakiye, C.dusuk_esik).where(C.hesap_email == eposta, C.para_birimi == pb))).first()
    if satir is None:
        return False
    cid, bk, esik = satir
    await _bildir(
        db, BILDIRIM_DUSUK, _musteri(eposta),
        f"Bakiyeniz azaldı: {_para(bk, pb)} / Low balance: {_para(bk, pb, 'en')}",
        f"{pb} bakiyeniz belirlediğiniz eşiğin ({_para(esik, pb)}) altına indi: {_para(bk, pb)}.\n\n"
        f"Your {pb} balance fell below your threshold ({_para(esik, pb, 'en')}): {_para(bk, pb, 'en')}.",
        MUSTERI_BAGLANTISI, {"bakiye": _para(bk, pb), "esik": _para(esik, pb), "para_birimi": pb}, "cuzdan_hesaplari", cid,
    )
    return True


# ---------------------------------------------------------------------------
# Yükleme (yönetici elle / talep onayı / ileride çevrim içi)
# ---------------------------------------------------------------------------
async def yukle(db: AsyncSession, *, eposta: str, pb: str, tutar: int, yontem: str, tarih: date, yazan: Optional[str],
                yazan_rol: str = "admin", notu: Optional[str] = None, dekont_dosya_id: Optional[int] = None,
                talep_id: Optional[int] = None, tekil: Optional[str] = None, kaynak: str = "elle") -> CuzdanHareketleri:
    """Bakiyeye yükleme (commit ETMEZ) + `bakiye.yuklendi` olayı. GENİŞLEME NOKTASI: çevrim içi sağlayıcının doğrulanmış
    bildirimi de buradan geçmeli (`kaynak="cevrimici"`, `tekil="saglayici:<ref>"`)."""
    h = await hareket_yaz(db, eposta=eposta, pb=pb, tur="yukleme", tutar=tutar, tarih=tarih, yazan=yazan, yazan_rol=yazan_rol,
                          yontem=yontem, notu=notu, dekont_dosya_id=dekont_dosya_id, talep_id=talep_id, tekil=tekil)
    await _olay(db, OLAY_YUKLENDI, h, kaynak=kaynak, talep_id=talep_id)
    return h


async def _yukleme_bildir(db: AsyncSession, h: CuzdanHareketleri) -> None:
    pb = h.para_birimi
    await _bildir(
        db, BILDIRIM_YUKLEME, _musteri(h.hesap_email),
        f"Bakiyenize {_para(h.tutar, pb)} yüklendi / {_para(h.tutar, pb, 'en')} added to your balance",
        f"Bakiyenize {_para(h.tutar, pb)} eklendi. Güncel bakiye: {_para(h.sonra, pb)}.\n\n"
        f"{_para(h.tutar, pb, 'en')} was added to your balance. Current balance: {_para(h.sonra, pb, 'en')}.",
        MUSTERI_BAGLANTISI, {"tutar": _para(h.tutar, pb), "bakiye": _para(h.sonra, pb), "para_birimi": pb},
        "cuzdan_hareketleri", h.id,
    )


async def elle_yukle(db: AsyncSession, *, eposta: str, pb: str, tutar: int, yontem: str, tarih: date, yonetici: str,
                     notu: Optional[str], dekont: Any = None) -> CuzdanHareketleri:
    """Yönetici havale/EFT/nakit yüklemesini kaydeder. Commit EDER."""
    from services.belge_ortak import eposta_gecerli

    if not eposta_gecerli(eposta):
        raise CuzdanHatasi(400, "eposta_gecersiz")
    try:
        dekont_id = await dekont_kaydet(db, eposta, dekont, yonetici, "admin")
        h = await yukle(db, eposta=eposta, pb=pb, tutar=tutar, yontem=yontem, tarih=tarih, yazan=yonetici, notu=notu,
                        dekont_dosya_id=dekont_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await _yukleme_bildir(db, h)
    await dusuk_bakiye_denetle(db, eposta, pb)
    return h


# ---------------------------------------------------------------------------
# Müşterinin yükleme talebi
# ---------------------------------------------------------------------------
async def talep_olustur(db: AsyncSession, *, eposta: str, kisi: str, pb: str, tutar: int, yontem: str,
                        odeme_tarihi: date, notu: Optional[str], dekont: Any = None) -> CuzdanYuklemeTalepleri:
    """"Bakiye yükle" bildirimi → beklemede talep (gelen kutusu kaynağı `bakiye_yukleme`) + yöneticilere bildirim.
    Commit EDER."""
    bekleyen = int((await db.execute(select(func.count(CuzdanYuklemeTalepleri.id)).where(
        CuzdanYuklemeTalepleri.hesap_email == eposta, CuzdanYuklemeTalepleri.durum == "beklemede"))).scalar() or 0)
    if bekleyen >= EN_COK_BEKLEYEN_TALEP:
        raise CuzdanHatasi(409, "cok_fazla_bekleyen", sinir=EN_COK_BEKLEYEN_TALEP)
    try:
        a = await ayar_al(db, eposta)
        dekont_id = await dekont_kaydet(db, eposta, dekont, kisi, "client")
        t = CuzdanYuklemeTalepleri(hesap_email=eposta, kisi_email=eposta_duzelt(kisi) or None, para_birimi=pb, tutar=tutar,
                                   yontem=yontem, odeme_tarihi=odeme_tarihi, referans=a.referans, dekont_dosya_id=dekont_id,
                                   notu=notu, durum="beklemede", created_at=simdi())
        db.add(t)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(t)
    try:
        from services.notify import admin_recipients

        yoneticiler = await admin_recipients(db)
        if yoneticiler:
            await _bildir(
                db, BILDIRIM_TALEP, yoneticiler, f"Bakiye yükleme talebi: {_para(tutar, pb)} — {eposta}",
                f"{eposta} {_para(tutar, pb)} tutarında bakiye yüklemesi bildirdi ({yontem}, referans {t.referans}). "
                "Onay için Gelen kutusu ya da Ödemeler › Müşteri bakiyeleri.",
                f"/admin?sekme=gelenKutusu&kaynak=bakiye_yukleme&oge=bakiye_yukleme:{t.id}",
                {"tutar": _para(tutar, pb), "hesap": eposta, "referans": t.referans}, "cuzdan_yukleme_talepleri", t.id,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Bakiye talebi bildirimi gönderilemedi")
    return t


async def _talep(db: AsyncSession, talep_id: int) -> CuzdanYuklemeTalepleri:
    t = (await db.execute(select(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.id == talep_id))).scalars().first()
    if t is None:
        raise CuzdanHatasi(404, "talep_yok")
    return t


async def _talep_kapat(db: AsyncSession, talep_id: int, yeni: str, **degerler: Any) -> None:
    """Koşullu durum geçişi: yalnız `beklemede` talep (eşzamanlı iki karar → biri 409)."""
    T = CuzdanYuklemeTalepleri
    r = await db.execute(update(T).where(T.id == talep_id, T.durum == "beklemede").values(durum=yeni, **degerler)
                         .execution_options(synchronize_session=False))
    if not r.rowcount:
        raise CuzdanHatasi(409, "talep_beklemede_degil")


async def talep_onayla(db: AsyncSession, talep_id: int, *, yonetici: str, tutar: Optional[int] = None,
                       tarih: Optional[date] = None, yontem: Optional[str] = None, notu: Optional[str] = None) -> CuzdanHareketleri:
    """Talebi onaylar: bakiye artar (onaylanan tutar talepten farklı olabilir — ör. banka masrafı), müşteriye bildirim,
    `bakiye.yuklendi`. Commit EDER."""
    t = await _talep(db, talep_id)
    if t.durum != "beklemede":
        raise CuzdanHatasi(409, "talep_beklemede_degil")
    miktar = tutar if tutar is not None else int(t.tutar)
    try:
        await _talep_kapat(db, t.id, "onaylandi", karar_veren=eposta_duzelt(yonetici) or None, karar_at=simdi())
        h = await yukle(db, eposta=t.hesap_email, pb=t.para_birimi, tutar=miktar, yontem=yontem or t.yontem,
                        tarih=tarih or t.odeme_tarihi or bugun(), yazan=yonetici, notu=notu or t.notu,
                        dekont_dosya_id=t.dekont_dosya_id, talep_id=t.id, tekil=f"talep:{t.id}", kaynak="talep")
        await db.execute(update(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.id == t.id).values(hareket_id=h.id)
                         .execution_options(synchronize_session=False))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await _yukleme_bildir(db, h)
    await dusuk_bakiye_denetle(db, h.hesap_email, h.para_birimi)
    return h


async def talep_reddet(db: AsyncSession, talep_id: int, *, yonetici: str, neden: Optional[str]) -> CuzdanYuklemeTalepleri:
    t = await _talep(db, talep_id)
    if t.durum != "beklemede":
        raise CuzdanHatasi(409, "talep_beklemede_degil")
    neden_ = metin_al(neden, GEREKCE_SINIRI)
    if not neden_:
        raise CuzdanHatasi(400, "neden_gerekli")
    try:
        await _talep_kapat(db, t.id, "reddedildi", karar_veren=eposta_duzelt(yonetici) or None, karar_at=simdi(),
                           ret_nedeni=neden_)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(t)
    pb = t.para_birimi
    await _bildir(
        db, BILDIRIM_YUKLEME, _musteri(t.hesap_email),
        "Bakiye yükleme talebiniz reddedildi / Your top-up request was declined",
        f"{_para(t.tutar, pb)} tutarındaki yükleme bildiriminiz onaylanmadı. Neden: {neden_}\n\n"
        f"Your top-up notice of {_para(t.tutar, pb, 'en')} was not approved. Reason: {neden_}",
        MUSTERI_BAGLANTISI, {"tutar": _para(t.tutar, pb), "neden": neden_}, "cuzdan_yukleme_talepleri", t.id,
    )
    return t


async def talep_iptal(db: AsyncSession, talep_id: int, eposta: str) -> CuzdanYuklemeTalepleri:
    t = await _talep(db, talep_id)
    if eposta_duzelt(t.hesap_email) != eposta:
        raise CuzdanHatasi(404, "talep_yok")
    if t.durum != "beklemede":
        raise CuzdanHatasi(409, "talep_beklemede_degil")
    try:
        await _talep_kapat(db, t.id, "iptal", karar_at=simdi())
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(t)
    return t


# ---------------------------------------------------------------------------
# İade (müşteriye geri ödeme), düzeltme, ters kayıt
# ---------------------------------------------------------------------------
async def iade_et(db: AsyncSession, *, eposta: str, pb: str, tutar: int, yontem: str, tarih: date, yonetici: str,
                  notu: Optional[str]) -> CuzdanHareketleri:
    """Kullanılmayan bakiyenin müşteriye elle geri ödenmesi (havale/nakit — para ajansın hesabından çıkar; gider değil).
    Commit EDER."""
    try:
        h = await hareket_yaz(db, eposta=eposta, pb=pb, tur="iade", tutar=-tutar, tarih=tarih, yazan=yonetici, yontem=yontem,
                              notu=notu)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await _bildir(
        db, BILDIRIM_IADE, _musteri(eposta),
        f"Bakiye iadesi: {_para(tutar, pb)} / Balance refund: {_para(tutar, pb, 'en')}",
        f"Bakiyenizden {_para(tutar, pb)} size iade edildi ({yontem}). Kalan bakiye: {_para(h.sonra, pb)}.\n\n"
        f"{_para(tutar, pb, 'en')} from your balance was refunded to you. Remaining balance: {_para(h.sonra, pb, 'en')}.",
        MUSTERI_BAGLANTISI, {"tutar": _para(tutar, pb), "bakiye": _para(h.sonra, pb)}, "cuzdan_hareketleri", h.id,
    )
    await dusuk_bakiye_denetle(db, eposta, pb)
    return h


async def duzelt(db: AsyncSession, *, eposta: str, pb: str, tutar: int, gerekce: Optional[str], yonetici: str) -> CuzdanHareketleri:
    """Yönetici düzeltmesi (işaretli; gerekçe ZORUNLU; bakiye eksiye düşemez). Ön muhasebeye ÖNERİ olarak gider."""
    g = metin_al(gerekce, GEREKCE_SINIRI)
    if not g:
        raise CuzdanHatasi(400, "gerekce_gerekli")
    try:
        h = await hareket_yaz(db, eposta=eposta, pb=pb, tur="duzeltme", tutar=tutar, yazan=yonetici, gerekce=g)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await dusuk_bakiye_denetle(db, eposta, pb)
    return h


async def ters_kayit(db: AsyncSession, hareket_id: int, *, gerekce: Optional[str], yonetici: str) -> CuzdanHareketleri:
    """Yükleme / iade / düzeltme satırının tam tersi (BİR kez). Harcama ters çevrilmez: faturadaki ödeme silinir
    (o zaman ters kayıt kendiliğinden yazılır) — fatura ile defter ayrışmasın."""
    g = metin_al(gerekce, GEREKCE_SINIRI)
    if not g:
        raise CuzdanHatasi(400, "gerekce_gerekli")
    asil = (await db.execute(select(CuzdanHareketleri).where(CuzdanHareketleri.id == hareket_id))).scalars().first()
    if asil is None:
        raise CuzdanHatasi(404, "hareket_yok")
    if asil.tur == "harcama":
        raise CuzdanHatasi(409, "harcama_odeme_uzerinden")
    if asil.tur == "ters_kayit":
        raise CuzdanHatasi(409, "ters_kaydin_tersi")
    try:
        h = await hareket_yaz(db, eposta=asil.hesap_email, pb=asil.para_birimi, tur="ters_kayit", tutar=-int(asil.tutar),
                              yazan=yonetici, bagli_id=asil.id, talep_id=asil.talep_id, gerekce=g, tekil=f"ters:{asil.id}")
        await db.commit()
    except CuzdanHatasi as e:
        await db.rollback()
        if e.kod == "tekrar_istek":
            raise CuzdanHatasi(409, "zaten_ters_cevrildi")
        raise
    except Exception:
        await db.rollback()
        raise
    await dusuk_bakiye_denetle(db, asil.hesap_email, asil.para_birimi)
    return h


# ---------------------------------------------------------------------------
# Harcama: bakiyeden fatura ödemesi
# ---------------------------------------------------------------------------
def _fatura_acik_mi(fatura: Any) -> Optional[str]:
    """Ödenemiyorsa hata kodu."""
    if (fatura.tur or "") == "iade":
        return "iade_faturasi"
    durum = (fatura.status or "").lower()
    if durum in ("draft", "taslak"):
        return "fatura_taslak"
    if durum in ("paid", "cancelled", "iade", "iptal"):
        return "fatura_kapali"
    return None


async def fatura_bakiye_bilgisi(db: AsyncSession, fatura: Any) -> Dict[str, Any]:
    """Fatura ekranındaki "Bakiyeden öde / uygula" kutusu: faturanın para birimindeki bakiye ve kalan."""
    from services.faturalar import bakiye as fb

    eposta = eposta_duzelt(fatura.client_email)
    pb = (fatura.currency or "TRY").upper()
    bk = await bakiye_oku(db, eposta, pb) if eposta else 0
    kalan = 0
    hata = _fatura_acik_mi(fatura)
    if hata is None:
        b = await fb(db, fatura)
        kalan = max(kurusa(b.kalan), 0)
        if kalan <= 0:
            hata = "fatura_kapali"
    return {"fatura_id": fatura.id, "invoice_no": fatura.invoice_no, "para_birimi": pb, "bakiye": tl(bk), "kalan": tl(kalan),
            "uygulanabilir": hata is None and bk > 0, "neden": hata or (None if bk > 0 else "bakiye_yok"),
            "onerilen": tl(min(bk, kalan)) if hata is None else 0.0}


async def _harcama_sonucu(db: AsyncSession, h: CuzdanHareketleri, fatura: Any, *, yonetici: bool, tekrar: bool) -> Dict[str, Any]:
    from services.faturalar import fatura_ozeti

    await db.refresh(fatura)
    return {"tekrar": tekrar, "hareket": hareket_sozlugu(h, yonetici=yonetici, fatura_no=fatura.invoice_no),
            "bakiye": tl(await bakiye_oku(db, h.hesap_email, h.para_birimi)), "para_birimi": h.para_birimi,
            "fatura": await fatura_ozeti(db, fatura, yonetici=yonetici)}


async def faturayi_ode(db: AsyncSession, fatura: Any, *, tutar: Any = None, yazan: Optional[str], yazan_rol: str,
                       istek_anahtari: Optional[str] = None, kismi: bool = False, otomatik: bool = False) -> Dict[str, Any]:
    """Bakiyeden fatura ödemesi (tamamı ya da girilen kısım). Commit EDER.

    Sıra: (1) faturanın para birimindeki bakiyeden KOŞULLU düşüş (eşzamanlı iki istekten biri reddedilir),
    (2) `faturalar.odeme_ekle(yontem="bakiye")` — durum, `fatura.odendi`, komisyon, kredi aynı yoldan, (3) defter
    satırı (`tekil` = istek anahtarı). Aynı anahtarla ikinci istek ilk sonucu döner (`tekrar`: true).
    `tutar` verilmezse kalanın tamamı (`kismi` → bakiye yetmezse olan kadarı)."""
    from services import faturalar as fs
    from services import kredi

    yonetici = yazan_rol == "admin"
    hata = _fatura_acik_mi(fatura)
    eposta = eposta_duzelt(fatura.client_email)
    if not eposta:
        hata = hata or "musteri_yok"
    anahtar = istek_anahtari_al(istek_anahtari)
    tekil = f"harcama:{fatura.id}:{anahtar}" if anahtar else None
    if tekil:
        var = await tekil_bul(db, tekil)
        if var is not None:
            return await _harcama_sonucu(db, var, fatura, yonetici=yonetici, tekrar=True)
    if hata:
        raise CuzdanHatasi(409, hata)
    pb = (fatura.currency or "TRY").upper()
    try:
        b = await fs.bakiye(db, fatura)
        kalan = max(kurusa(b.kalan), 0)
        if kalan <= 0:
            raise CuzdanHatasi(409, "fatura_kapali")
        if await bakiye_oku(db, eposta, pb) <= 0:
            # Para birimi dönüşümü YOK: başka para biriminde bakiye varsa bunu açıkça söyle.
            diger = (await db.execute(select(CuzdanHesaplari.para_birimi).where(
                CuzdanHesaplari.hesap_email == eposta, CuzdanHesaplari.para_birimi != pb, CuzdanHesaplari.bakiye > 0))).scalars().all()
            if diger:
                raise CuzdanHatasi(409, "para_birimi_uyusmuyor", para_birimi=pb, bakiye_para_birimleri=sorted(diger))
            raise CuzdanHatasi(409, "bakiye_yetersiz", bakiye=0.0, para_birimi=pb)
        if tutar in (None, ""):
            miktar = kalan
            if kismi:
                miktar = min(kalan, await bakiye_oku(db, eposta, pb))
                if miktar <= 0:
                    raise CuzdanHatasi(409, "bakiye_yetersiz", bakiye=0.0, para_birimi=pb)
        else:
            miktar = tutar_al(tutar)
            if miktar > kalan:
                raise CuzdanHatasi(409, "tutar_kalandan_fazla", kalan=tl(kalan))
        c = await cuzdan_satiri(db, eposta, pb)
        sonra = await _bakiye_degistir(db, c, -miktar)
        try:
            satir, kredi_ozeti = await fs.odeme_ekle(
                db, fatura, tutar=ondaliga(miktar), yontem=BAKIYE_YONTEMI, ekleyen=yazan if yazan_rol != "sistem" else None,
                notu=("Otomatik ödeme — bakiyeden" if otomatik else "Bakiyeden ödeme"), cuzdan=True,
            )
        except fs.FaturaHatasi as fh:
            raise CuzdanHatasi(fh.durum, fh.kod, **fh.ek)
        h = await _satir_ekle(db, c, tur="harcama", tutar=-miktar, sonra=sonra, tarih=bugun(), yazan=yazan, yazan_rol=yazan_rol,
                              yontem=BAKIYE_YONTEMI, fatura_id=fatura.id, odeme_id=satir.id, tekil=tekil,
                              notu=fatura.invoice_no)
        await _olay(db, OLAY_HARCANDI, h, fatura_id=fatura.id, fatura_no=fatura.invoice_no, otomatik=otomatik)
        await db.commit()
    except (CuzdanHatasi, IntegrityError) as e:
        await db.rollback()
        if tekil:
            var = await tekil_bul(db, tekil)
            if var is not None:
                return await _harcama_sonucu(db, var, fatura, yonetici=yonetici, tekrar=True)
        if isinstance(e, IntegrityError):
            raise CuzdanHatasi(409, "eszamanli")
        raise
    except Exception:
        await db.rollback()
        raise
    await kredi.kredi_yuklendi_bildir(db, kredi_ozeti)
    sonuc = await _harcama_sonucu(db, h, fatura, yonetici=yonetici, tekrar=False)
    durum = sonuc["fatura"]["status"]
    await _bildir(
        db, BILDIRIM_HARCAMA, _musteri(eposta),
        f"Bakiyeden ödendi: {fatura.invoice_no} / Paid from balance: {fatura.invoice_no}",
        f"{fatura.invoice_no} numaralı faturaya bakiyenizden {_para(miktar, pb)} uygulandı"
        f"{' (otomatik ödeme)' if otomatik else ''}. Kalan bakiye: {_para(sonra, pb)}.\n\n"
        f"{_para(miktar, pb, 'en')} from your balance was applied to invoice {fatura.invoice_no}"
        f"{' (automatic payment)' if otomatik else ''}. Remaining balance: {_para(sonra, pb, 'en')}.",
        MUSTERI_BAGLANTISI, {"fatura_no": fatura.invoice_no, "tutar": _para(miktar, pb), "bakiye": _para(sonra, pb),
                             "durum": durum}, "invoice", fatura.id,
    )
    await dusuk_bakiye_denetle(db, eposta, pb)
    return sonuc


# ---------------------------------------------------------------------------
# Fatura akışı kancaları (commit ETMEZ — çağıranın işleminde)
# ---------------------------------------------------------------------------
async def odeme_silindi(db: AsyncSession, satir: Any, silen: Optional[str] = None) -> Optional[CuzdanHareketleri]:
    """`faturalar.odeme_sil`den, satır silinmeden ÖNCE: bakiyeden yapılmış ödeme silinirse tutar bakiyeye geri
    (ters kayıt); bakiyeye yapılmış iade satırı silinirse bakiyeden geri alınır (yetmezse 409 — silme olmaz)."""
    if (satir.saglayici or "") != BAKIYE_YONTEMI or satir.durum not in ("odendi", "iade"):
        return None
    eposta = eposta_duzelt(satir.client_email)
    if not eposta:
        return None
    pb = (satir.para_birimi or "TRY").upper()
    miktar = kurusa(satir.tutar)
    if miktar <= 0:
        return None
    # Ödeme satırının defterdeki aslı (harcama ya da bakiyeye iadenin ters kaydı). En yenisi: SQLite silinen en büyük
    # kimliği yeniden kullanabiliyor; tekillik anahtarı bu yüzden ödeme kimliğine değil defter satırına bağlı.
    asil = (await db.execute(select(CuzdanHareketleri).where(
        CuzdanHareketleri.odeme_id == satir.id,
        CuzdanHareketleri.tur == ("harcama" if satir.durum == "odendi" else "ters_kayit"))
        .order_by(CuzdanHareketleri.id.desc()))).scalars().first()
    isaret = 1 if satir.durum == "odendi" else -1
    return await hareket_yaz(
        db, eposta=eposta, pb=pb, tur="ters_kayit", tutar=isaret * miktar, yazan=silen, yazan_rol="admin" if silen else "sistem",
        fatura_id=satir.invoice_id, bagli_id=asil.id if asil else None,
        gerekce=f"Fatura ödemesi silindi ({satir.invoice_no or satir.invoice_id})",
        tekil=f"odeme_sil:{asil.id}" if asil else None,
    )


async def iade_faturasi_kesildi(db: AsyncSession, fatura: Any, b: Any, ekleyen: Optional[str]) -> Optional[CuzdanHareketleri]:
    """`faturalar.iade_faturasi_kes`ten: iade faturası fazla ödeme doğurduysa, faturaya BAKİYEDEN ödenmiş kısım kadarı
    bakiyeye geri yazılır (payments'a "iade" + defterde ters kayıt). Banka/kartla ödenmiş fazla kısım bugünkü gibi
    yöneticinin elle geri ödemesine kalır."""
    from services import faturalar as fs

    if b.kalan >= -fs.EPS:
        return None
    net = Decimal("0")
    for o in await fs.odeme_satirlari(db, fatura.id):
        if (o.saglayici or "") != BAKIYE_YONTEMI:
            continue
        if o.durum == "odendi":
            net += fs.D(o.tutar)
        elif o.durum == "iade":
            net -= fs.D(o.tutar)
    miktar = min(kurusa(-b.kalan), kurusa(net))
    if miktar <= 0:
        return None
    satir, _ = await fs.odeme_ekle(db, fatura, tutar=ondaliga(miktar), yontem=BAKIYE_YONTEMI, notu="İade faturası — bakiyeye iade",
                                   ekleyen=ekleyen, geri_odeme=True, cuzdan=True)
    asil = (await db.execute(select(CuzdanHareketleri).where(CuzdanHareketleri.fatura_id == fatura.id,
                                                             CuzdanHareketleri.tur == "harcama")
                             .order_by(CuzdanHareketleri.id.desc()))).scalars().first()
    return await hareket_yaz(
        db, eposta=eposta_duzelt(fatura.client_email), pb=(fatura.currency or "TRY").upper(), tur="ters_kayit", tutar=miktar,
        yazan=ekleyen, yazan_rol="admin" if ekleyen else "sistem", fatura_id=fatura.id, odeme_id=satir.id,
        bagli_id=asil.id if asil else None, gerekce=f"İade faturası ({fatura.invoice_no})",
    )


# ---------------------------------------------------------------------------
# Otomatik ödeme
# ---------------------------------------------------------------------------
async def ayarlari_yaz(db: AsyncSession, eposta: str, kisi: str, veri: Dict[str, Any]) -> Dict[str, Any]:
    """Müşteri ayarları: otomatik ödeme (açarken onay metni ZORUNLU), kısmi uygulama, zamanlama, para birimi başına
    düşük bakiye eşiği. Commit EDER."""
    a = await ayar_al(db, eposta)
    an = simdi()
    if "otomatik_odeme" in veri:
        ac = bool(veri.get("otomatik_odeme"))
        if ac and not a.otomatik_odeme:
            if veri.get("onay") is not True:
                raise CuzdanHatasi(400, "onay_gerekli")
            from models.invoices import Invoices

            a.otomatik_baslangic = an
            a.otomatik_son_fatura_id = int((await db.execute(select(func.max(Invoices.id)))).scalar() or 0)
            a.onay_metni_surumu = ONAY_METNI_SURUMU
            a.onaylayan = eposta_duzelt(kisi) or None
        a.otomatik_odeme = ac
    if "otomatik_kismi" in veri:
        a.otomatik_kismi = bool(veri.get("otomatik_kismi"))
    if "otomatik_zaman" in veri:
        z = str(veri.get("otomatik_zaman") or "").strip()
        if z not in OTOMATIK_ZAMANLAR:
            raise CuzdanHatasi(400, "zaman_gecersiz")
        a.otomatik_zaman = z
    esikler = veri.get("dusuk_esikler")
    if esikler is not None:
        if not isinstance(esikler, dict):
            raise CuzdanHatasi(400, "esik_gecersiz")
        for pb_ham, deger in esikler.items():
            pb = para_birimi_al(pb_ham)
            c = await cuzdan_satiri(db, eposta, pb)
            if deger in (None, "", 0, "0"):
                yeni = None
            else:
                yeni = kurusa(deger, "esik_gecersiz")
                if yeni <= 0 or yeni > EN_COK_TUTAR:
                    raise CuzdanHatasi(400, "esik_gecersiz")
            await db.execute(update(CuzdanHesaplari).where(CuzdanHesaplari.id == c.id)
                             .values(dusuk_esik=yeni, dusuk_uyari_at=None, updated_at=an).execution_options(synchronize_session=False))
    a.updated_at = an
    await db.commit()
    return ayar_sozlugu(a)


async def _otomatik_iz(db: AsyncSession, fatura_id: int, eposta: str) -> Optional[CuzdanOtomatikIzleri]:
    try:
        async with db.begin_nested():
            iz = CuzdanOtomatikIzleri(fatura_id=fatura_id, hesap_email=eposta, sonuc="hata", tutar=0, created_at=simdi())
            db.add(iz)
            await db.flush()
        return iz
    except IntegrityError:
        return None


def _utc(an: Any) -> Optional[datetime]:
    if not isinstance(an, datetime):
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _otomatik_uygun(fatura: Any, a: CuzdanAyarlari) -> bool:
    if not a.otomatik_odeme or _fatura_acik_mi(fatura):
        return False
    if a.otomatik_son_fatura_id is None or int(fatura.id or 0) <= int(a.otomatik_son_fatura_id):
        return False  # yalnız açıldıktan SONRA kesilen faturalar
    if a.otomatik_zaman == "vadesinde" and fatura.due_date:
        from services.faturalar import tarih_coz

        vade = tarih_coz(fatura.due_date)
        if vade is not None and vade > bugun():
            return False
    return True


async def otomatik_odeme_dene(db: AsyncSession, fatura: Any) -> Optional[Dict[str, Any]]:
    """Otomatik ödeme açık hesabın YENİ faturası: fatura başına BİR deneme (iz satırı benzersiz). Bakiye yeterse
    tamamı; yetmezse ayara göre olan kadarı ya da hiç — her iki durumda müşteriye bildirim. Hata fırlatmaz."""
    try:
        eposta = eposta_duzelt(fatura.client_email)
        if not eposta:
            return None
        a = await ayar_al(db, eposta, olustur=False)
        if a is None or not _otomatik_uygun(fatura, a):
            return None
        iz = await _otomatik_iz(db, fatura.id, eposta)
        if iz is None:
            return None
        pb = (fatura.currency or "TRY").upper()
        bk = await bakiye_oku(db, eposta, pb)
        from services.faturalar import bakiye as fb

        kalan = max(kurusa((await fb(db, fatura)).kalan), 0)
        fatura_id, no = fatura.id, fatura.invoice_no
        if kalan <= 0:
            iz.sonuc = "odendi"
            await db.commit()
            return {"sonuc": "kapali"}
        if bk < kalan and (not a.otomatik_kismi or bk <= 0):
            iz.sonuc = "yetersiz"
            await db.commit()
            await _bildir(
                db, BILDIRIM_HARCAMA, _musteri(eposta),
                f"Otomatik ödeme yapılamadı: {no} / Automatic payment not made: {no}",
                f"{no} numaralı fatura ({_para(kalan, pb)}) için bakiyeniz yetersiz: {_para(bk, pb)}. "
                "Bakiye yükleyip faturayı panelden ödeyebilirsiniz.\n\n"
                f"Your balance ({_para(bk, pb, 'en')}) is not enough for invoice {no} ({_para(kalan, pb, 'en')}). "
                "You can top up and pay the invoice from your panel.",
                MUSTERI_BAGLANTISI, {"fatura_no": no, "tutar": _para(kalan, pb), "bakiye": _para(bk, pb)}, "invoice", fatura_id,
            )
            return {"sonuc": "yetersiz"}
        await db.commit()  # iz satırı kalsın (ödeme başarısız olsa da ikinci deneme yok)
        try:
            s = await faturayi_ode(db, fatura, tutar=None, yazan=None, yazan_rol="sistem", istek_anahtari="otomatik-odeme",
                                   kismi=True, otomatik=True)
        except CuzdanHatasi as h:
            logger.info("Otomatik ödeme uygulanamadı: fatura=%s kod=%s", fatura_id, h.kod)
            return {"sonuc": "hata", "kod": h.kod}
        uygulanan = kurusa(abs(Decimal(str(s["hareket"]["tutar"]))))
        await db.execute(update(CuzdanOtomatikIzleri).where(CuzdanOtomatikIzleri.fatura_id == fatura_id)
                         .values(sonuc="odendi" if uygulanan >= kalan else "kismi", tutar=uygulanan)
                         .execution_options(synchronize_session=False))
        await db.commit()
        return {"sonuc": "odendi" if uygulanan >= kalan else "kismi", "tutar": tl(uygulanan)}
    except Exception:  # noqa: BLE001 - fatura akışı bu yüzden düşmemeli
        logger.exception("Otomatik bakiye ödemesi denenemedi: fatura=%s", getattr(fatura, "id", None))
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def otomatik_odeme_dene_id(db: AsyncSession, fatura_id: int) -> Optional[Dict[str, Any]]:
    """Kimlikle: fatura yeniden okunur (çağıranın nesneleri bir geri almadan etkilenmesin). Hata fırlatmaz."""
    try:
        from models.invoices import Invoices

        f = (await db.execute(select(Invoices).where(Invoices.id == fatura_id))).scalars().first()
    except Exception:  # noqa: BLE001
        logger.exception("Otomatik ödeme için fatura okunamadı: %s", fatura_id)
        return None
    if f is None:
        return None
    return await otomatik_odeme_dene(db, f)


async def otomatik_odemeler(db: AsyncSession) -> Dict[str, Any]:
    """Zamanlı iş `cuzdan_otomatik_odeme`: otomatik ödemesi açık hesapların denenmemiş açık faturaları (vadesinde
    seçeneğinde vadesi gelenler). Hesap başına en çok 50 fatura."""
    from models.invoices import Invoices

    ayarlar = (await db.execute(select(CuzdanAyarlari).where(CuzdanAyarlari.otomatik_odeme.is_(True)))).scalars().all()
    ozet = {"hesap": len(ayarlar), "denenen": 0, "odenen": 0, "yetersiz": 0}
    for aid in [a.id for a in ayarlar]:
        a = (await db.execute(select(CuzdanAyarlari).where(CuzdanAyarlari.id == aid))).scalars().first()
        if a is None or not a.otomatik_odeme:
            continue
        denenmis = select(CuzdanOtomatikIzleri.fatura_id).where(CuzdanOtomatikIzleri.hesap_email == a.hesap_email)
        faturalar = (await db.execute(select(Invoices).where(
            func.lower(Invoices.client_email) == a.hesap_email, Invoices.id > int(a.otomatik_son_fatura_id or 0),
            or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
            or_(Invoices.status.is_(None), func.lower(Invoices.status).notin_(ACIK_FATURA_DISI)),
            Invoices.id.notin_(denenmis),
        ).order_by(Invoices.id).limit(50))).scalars().all()
        adaylar = [f.id for f in faturalar if _otomatik_uygun(f, a)]
        for fid in adaylar:
            ozet["denenen"] += 1
            s = await otomatik_odeme_dene_id(db, fid)
            if s and s.get("sonuc") in ("odendi", "kismi"):
                ozet["odenen"] += 1
            elif s and s.get("sonuc") == "yetersiz":
                ozet["yetersiz"] += 1
    return ozet


# ---------------------------------------------------------------------------
# Özetler
# ---------------------------------------------------------------------------
async def musteri_ozeti(db: AsyncSession, eposta: str) -> Dict[str, Any]:
    a = await ayar_al(db, eposta)
    await db.commit()
    cuzdanlar = (await db.execute(select(CuzdanHesaplari).where(CuzdanHesaplari.hesap_email == eposta)
                                  .order_by(CuzdanHesaplari.para_birimi))).scalars().all()
    for c in cuzdanlar:
        await db.refresh(c)
    talepler = (await db.execute(select(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.hesap_email == eposta)
                                 .order_by(CuzdanYuklemeTalepleri.id.desc()).limit(20))).scalars().all()
    return {
        "bakiyeler": [cuzdan_sozlugu(c) for c in cuzdanlar],
        "ayarlar": ayar_sozlugu(a),
        "banka": await banka_bilgisi(db),
        "talepler": [talep_sozlugu(t, yonetici=False) for t in talepler],
        "son_hareketler": (await hareketler(db, eposta, None, yonetici=False, adet=10))["items"],
        "para_birimleri": list(PARA_BIRIMLERI),
        "yontemler": list(YUKLEME_YONTEMLERI),
    }


async def yonetici_listesi(db: AsyncSession, q: str = "") -> Dict[str, Any]:
    from services.hesap_ekibi import hesap_adlari

    sorgu = select(CuzdanHesaplari)
    aranan = " ".join((q or "").split())[:100].lower()
    if aranan:
        sorgu = sorgu.where(func.lower(CuzdanHesaplari.hesap_email).like(f"%{aranan.replace('%', '')}%"))
    cuzdanlar = (await db.execute(sorgu.order_by(CuzdanHesaplari.son_hareket_at.desc().nullslast(), CuzdanHesaplari.id.desc())
                                  .limit(500))).scalars().all()
    for c in cuzdanlar:
        await db.refresh(c)
    adlar = await hesap_adlari(db, {c.hesap_email for c in cuzdanlar})
    toplamlar: Dict[str, int] = {}
    for c in cuzdanlar:
        toplamlar[c.para_birimi] = toplamlar.get(c.para_birimi, 0) + int(c.bakiye or 0)
    bekleyen = (await db.execute(select(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.durum == "beklemede")
                                 .order_by(CuzdanYuklemeTalepleri.id))).scalars().all()
    tadlar = await hesap_adlari(db, {t.hesap_email for t in bekleyen})
    return {
        "hesaplar": [cuzdan_sozlugu(c, adlar.get(c.hesap_email)) for c in cuzdanlar],
        "toplamlar": [{"para_birimi": pb, "bakiye": tl(v)} for pb, v in sorted(toplamlar.items())],
        "bekleyen_talepler": [talep_sozlugu(t, yonetici=True, ad=tadlar.get(t.hesap_email)) for t in bekleyen],
        "para_birimleri": list(PARA_BIRIMLERI),
        "yontemler": list(YUKLEME_YONTEMLERI),
    }


async def yonetici_ayrintisi(db: AsyncSession, eposta: str, pb: Optional[str], sayfa: int = 1) -> Dict[str, Any]:
    from services.hesap_ekibi import hesap_adlari

    cuzdanlar = (await db.execute(select(CuzdanHesaplari).where(CuzdanHesaplari.hesap_email == eposta)
                                  .order_by(CuzdanHesaplari.para_birimi))).scalars().all()
    for c in cuzdanlar:
        await db.refresh(c)
    ad = (await hesap_adlari(db, [eposta])).get(eposta)
    talepler = (await db.execute(select(CuzdanYuklemeTalepleri).where(CuzdanYuklemeTalepleri.hesap_email == eposta)
                                 .order_by(CuzdanYuklemeTalepleri.id.desc()).limit(50))).scalars().all()
    a = await ayar_al(db, eposta, olustur=False)
    return {
        "hesap_email": eposta, "ad": ad, "bakiyeler": [cuzdan_sozlugu(c, ad) for c in cuzdanlar],
        "ayarlar": ayar_sozlugu(a),
        "hareketler": await hareketler(db, eposta, pb, yonetici=True, sayfa=sayfa),
        "talepler": [talep_sozlugu(t, yonetici=True, ad=ad) for t in talepler],
    }


# ---------------------------------------------------------------------------
# Ekstre (PDF / CSV)
# ---------------------------------------------------------------------------
async def ekstre_verisi(db: AsyncSession, eposta: str, pb: str, bas: date, bit: date) -> Dict[str, Any]:
    if bit < bas:
        raise CuzdanHatasi(400, "tarih_araligi_gecersiz")
    H = CuzdanHareketleri
    once = (await db.execute(select(H.sonra).where(H.hesap_email == eposta, H.para_birimi == pb, H.tarih < bas)
                             .order_by(H.tarih.desc(), H.id.desc()).limit(1))).scalar()
    satirlar = (await db.execute(select(H).where(H.hesap_email == eposta, H.para_birimi == pb, H.tarih >= bas, H.tarih <= bit)
                                 .order_by(H.tarih, H.id).limit(5000))).scalars().all()
    nolar = await fatura_nolari(db, (h.fatura_id for h in satirlar))
    devreden = int(once or 0)
    bakiye = devreden
    cikti = []
    giris = cikis = 0
    for h in satirlar:
        bakiye += int(h.tutar)
        if h.tutar > 0:
            giris += int(h.tutar)
        else:
            cikis += -int(h.tutar)
        cikti.append({"id": h.id, "tarih": h.tarih, "tur": h.tur, "tutar": int(h.tutar), "bakiye": bakiye, "yontem": h.yontem,
                      "fatura_no": nolar.get(h.fatura_id or 0), "notu": h.notu, "gerekce": h.gerekce})
    from services.hesap_ekibi import hesap_adlari

    return {"hesap_email": eposta, "ad": (await hesap_adlari(db, [eposta])).get(eposta), "para_birimi": pb, "bas": bas, "bit": bit,
            "devreden": devreden, "satirlar": cikti, "giris": giris, "cikis": cikis, "kapanis": bakiye, "olusturma": bugun()}


def ekstre_csv(v: Dict[str, Any], dil: str = "tr") -> str:
    from services.cuzdan_pdf import etiketler
    from services.muhasebe import csv_hucre

    e = etiketler(dil)
    tampon = io.StringIO()
    w = csv.writer(tampon, lineterminator="\r\n")
    w.writerow([e["tarih"], e["islem"], e["aciklama"], e["tutar"], e["bakiye"], e["para_birimi"]])
    w.writerow([v["bas"].isoformat(), e["devreden"], "", "", f"{ondaliga(v['devreden'])}", v["para_birimi"]])
    for s in v["satirlar"]:
        w.writerow([csv_hucre(s["tarih"].isoformat()), csv_hucre(e["tur"].get(s["tur"], s["tur"])),
                    csv_hucre(aciklama_metni(s, e)), f"{ondaliga(s['tutar'])}", f"{ondaliga(s['bakiye'])}", v["para_birimi"]])
    w.writerow([v["bit"].isoformat(), e["kapanis"], "", "", f"{ondaliga(v['kapanis'])}", v["para_birimi"]])
    return "﻿" + tampon.getvalue()


def aciklama_metni(s: Dict[str, Any], e: Dict[str, Any]) -> str:
    parcalar = []
    if s.get("fatura_no"):
        parcalar.append(f"{e['fatura']} {s['fatura_no']}")
    if s.get("yontem") and s["yontem"] != BAKIYE_YONTEMI:
        parcalar.append(e["yontem"].get(s["yontem"], s["yontem"]))
    for alan in ("gerekce", "notu"):
        if s.get(alan) and s[alan] != s.get("fatura_no"):
            parcalar.append(str(s[alan]))
    return " · ".join(parcalar)[:300]


__all__ = ["CuzdanHatasi", "kurusa", "ondaliga", "faturayi_ode", "yukle", "odeme_silindi", "iade_faturasi_kesildi"]
