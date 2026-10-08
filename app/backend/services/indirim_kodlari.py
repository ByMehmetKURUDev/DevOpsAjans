"""Faz 5K — indirim kodları: doğrulama, belgeye uygulama, kullanım sayımı, yönetim.

Kod biçimi
----------
Harf (Türkçe dâhil), rakam, `-` ve `_`; 3–32 karakter. Karşılaştırma
`kod_anahtari` ile: büyük/küçük harf duyarsız VE Türkçe İ/ı farkı katlanmış
(`kış2026`, `KIŞ2026`, `KİŞ2026`, `kis2026` değil — ş/s ayrı harf). Türk
klavyesinde küçük `i` (büyüğü İ) ile İngiliz klavyesinde `I` aynı kodu bulur.
Görünen biçim Türkçe büyük harf (`indirim` → `İNDİRİM`). Ortak referans
kodları aynı ad alanında: formdaki tek "indirim / referans kodu" alanı ikisini
de kabul ediyor, o yüzden bir anahtar ya indirim kodudur ya ortak kodu.

Uygulama (teklif / fatura)
--------------------------
`belgeye_uygula`: istemcinin gönderdiği işaretli satırlar ATILIR, kod
sunucuda doğrulanır ve KDV oranı başına "İndirim (KOD)" satırı(ları) eklenir
(`services/belge_hesap.py` işaretli satır). Yüzde: oran başına matrahın
yüzdesi. Sabit: tutar (KDV HARİÇ) en çok ara toplam kadar, oranlara matrah
payıyla bölünür (son orana kalan kuruş). En az tutar KDV hariç ara toplamla
karşılaştırılır. Kod zaten belgede varsa ve yeniden gönderilmediyse (kalemler
düzenlendi) yeniden doğrulanmadan yeni kalemlere uygulanır — kullanım zaten
sayılmıştı; boş metin kodu kaldırır.

Kullanım sınırları "canlı" belgeden sayılır: reddedilmiş / süresi dolmuş /
revize edilmiş teklif ve iptal edilmiş fatura saymaz (tekliften açılan
fatura ayrı kullanım değildir — kullanım teklifte). Kişi başı = belge
alıcısının e-postası.

Geçerli paketler (isteğe bağlı): fiyatlandırma ölçek kodları (ALFA, BETA…),
`KREDI` (Kullandıkça Öde kredi paketi) ve `AI_PM`. Doluysa kod yalnız o paketin
"Teklif al" talebinden açılan teklife (ve o talebin faturasına) uygulanır;
elle açılan belgede paket bilinmediği için uygulanmaz (`kod_paket_disi`).

Lemon Squeezy / Shopier ödeme sayfasına indirim AKTARILMIYOR (sağlayıcı
panelinde ayrı kupon gerekir) — kapsamdaki `paket` sitedeki "Teklif al"
formunda girilen kodu CRM'e ve tekliften çevrilen teklife taşıyor; "Satın al"
penceresinde alan yalnız referans kodu (indirim için "Teklif al"a yönlendirir).
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models.ortaklik import AJANS, IndirimKodlari, IndirimKoduKullanimlari, Ortaklar
from services.belge_hesap import HesapHatasi, KURUS, YUZ, belge_hesapla, kurus, ondalik
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TURLER = ("yuzde", "sabit")
KAPSAMLAR = ("teklif", "fatura", "paket")
BELGE_TURLERI = ("teklif", "fatura")
PARA_BIRIMLERI = ("TRY", "USD", "EUR", "GBP")
EN_KISA, EN_UZUN = 3, 32
ACIKLAMA_SINIRI = 300
#: Sayımda "canlı" olmayan belge durumları.
OLU_TEKLIF = ("ret", "suresi_doldu", "revize")
OLU_FATURA = ("cancelled", "iptal")

_IZINLI = re.compile(r"^[A-Z0-9ÇĞÖŞÜ_-]+$")
_PAKET = re.compile(r"^[A-Z0-9_-]{2,20}$")
#: Ölçek dışındaki paket kimlikleri.
OZEL_PAKETLER = ("KREDI", "AI_PM")


class KodHatasi(Exception):
    """Ön yüzün yedi dilde metin kurduğu hata: `kod` (+ ek bilgi)."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


# ---------------------------------------------------------------------------
# Biçim
# ---------------------------------------------------------------------------
def _sade(ham: Any) -> str:
    metin = unicodedata.normalize("NFC", str(ham or ""))
    # Boşluk ve görünmez karakterler kodun parçası değil ("YAZ 2026" = "YAZ2026").
    metin = "".join(c for c in metin if not c.isspace() and unicodedata.category(c) not in ("Cf", "Cc"))
    # "İ".lower() → "i̇" (birleşik nokta): noktayı at.
    return metin.replace("̇", "")


def kod_gorunen(ham: Any) -> str:
    """Türkçe büyük harf: i → İ, ı → I (Python'un `upper()`ı i'yi I yapardı)."""
    s = _sade(ham)
    return s.replace("i", "İ").replace("ı", "I").upper()[:40]


def kod_anahtari(ham: Any) -> str:
    """Karşılaştırma anahtarı: büyük harf + İ/ı/i/I katlanmış (hepsi I)."""
    s = _sade(ham)
    s = s.replace("İ", "I").replace("ı", "I").replace("i", "I")
    return s.upper()[:40]


def bicim_gecerli(ham: Any) -> bool:
    a = kod_anahtari(ham)
    return EN_KISA <= len(a) <= EN_UZUN and bool(_IZINLI.match(a))


def _bugun() -> date:
    from services.faturalar import tr_bugun

    return tr_bugun()


def _tarih(deger: Any) -> Optional[date]:
    if not deger:
        return None
    try:
        return date.fromisoformat(str(deger).strip()[:10])
    except ValueError:
        return None


def _liste(metin: Any) -> List[str]:
    if isinstance(metin, list):
        return [str(x) for x in metin]
    try:
        d = json.loads(metin or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in d] if isinstance(d, list) else []


def kapsam(k: IndirimKodlari) -> List[str]:
    return [x for x in _liste(k.kapsam) if x in KAPSAMLAR] or list(KAPSAMLAR)


def paketler(k: IndirimKodlari) -> List[str]:
    """Geçerli paketler (boş = hepsi)."""
    return [x for x in _liste(k.paketler) if _PAKET.match(x)]


def talep_paketi(scale_kod: Optional[str], ai_pm_kod: Optional[str], period: Optional[str]) -> Optional[str]:
    """Fiyat talebinin (Teklif al / Satın al) paket kimliği."""
    if scale_kod:
        return str(scale_kod).strip().upper()[:20] or None
    if ai_pm_kod:
        return "AI_PM"
    # Ölçeksiz ve AI/PM'siz talep: Kullandıkça Öde kredi paketi (`period` = kullandikca_ode).
    return "KREDI"


async def belge_paketi(db: AsyncSession, *, pricing_inquiry_id: Optional[int] = None,
                       fatura_id: Optional[int] = None) -> Optional[str]:
    """Belgenin bağlı olduğu fiyat talebinin paketi (teklifte `pricing_inquiry_id`, faturada talebin `invoice_id`si)."""
    from models.pricing import Pricing_inquiries as P

    if pricing_inquiry_id:
        s = select(P.scale_kod, P.ai_pm_tier_kod, P.period).where(P.id == int(pricing_inquiry_id))
    elif fatura_id:
        s = select(P.scale_kod, P.ai_pm_tier_kod, P.period).where(P.invoice_id == int(fatura_id)).order_by(P.id.desc())
    else:
        return None
    satir = (await db.execute(s.limit(1))).first()
    return talep_paketi(*satir) if satir else None


# ---------------------------------------------------------------------------
# Bulma
# ---------------------------------------------------------------------------
async def kod_bul(db: AsyncSession, ham: Any) -> Optional[IndirimKodlari]:
    anahtar = kod_anahtari(ham)
    if not anahtar:
        return None
    return (await db.execute(select(IndirimKodlari).where(IndirimKodlari.hesap == AJANS,
                                                          IndirimKodlari.kod_anahtar == anahtar))).scalars().first()


async def ortak_kodu_bul(db: AsyncSession, ham: Any, *, yalniz_onayli: bool = True) -> Optional[Ortaklar]:
    anahtar = kod_anahtari(ham)
    if not anahtar:
        return None
    s = select(Ortaklar).where(Ortaklar.hesap == AJANS, Ortaklar.kod_anahtar == anahtar)
    if yalniz_onayli:
        s = s.where(Ortaklar.durum == "onaylandi")
    return (await db.execute(s)).scalars().first()


async def ad_alani_bos_mu(db: AsyncSession, anahtar: str, *, haric_kod: Optional[int] = None,
                          haric_ortak: Optional[int] = None) -> bool:
    """Anahtar (ajans programında) ne bir indirim kodunda ne bir ortakta kullanılıyor mu?"""
    s1 = select(IndirimKodlari.id).where(IndirimKodlari.hesap == AJANS, IndirimKodlari.kod_anahtar == anahtar)
    if haric_kod:
        s1 = s1.where(IndirimKodlari.id != haric_kod)
    s2 = select(Ortaklar.id).where(Ortaklar.hesap == AJANS, Ortaklar.kod_anahtar == anahtar)
    if haric_ortak:
        s2 = s2.where(Ortaklar.id != haric_ortak)
    return (await db.execute(s1.limit(1))).scalar() is None and (await db.execute(s2.limit(1))).scalar() is None


# ---------------------------------------------------------------------------
# Kullanım sayımı
# ---------------------------------------------------------------------------
async def canli_kullanim(db: AsyncSession, kod_id: int, *, eposta: Optional[str] = None,
                         haric: Optional[Tuple[str, int]] = None) -> int:
    from models.invoices import Invoices
    from models.teklifler import Teklifler

    K = IndirimKoduKullanimlari
    toplam = 0
    for tur, model, durum_alani, olu in (
        ("teklif", Teklifler, Teklifler.durum, OLU_TEKLIF),
        ("fatura", Invoices, Invoices.status, OLU_FATURA),
    ):
        s = (
            select(func.count(K.id))
            .select_from(K.__table__.join(model.__table__, and_(model.id == K.belge_id, K.belge_turu == tur)))
            .where(K.kod_id == kod_id, func.coalesce(durum_alani, "").notin_(olu))
        )
        if eposta:
            s = s.where(K.eposta == eposta.strip().lower())
        if haric and haric[0] == tur:
            s = s.where(K.belge_id != int(haric[1]))
        toplam += int((await db.execute(s)).scalar() or 0)
    return toplam


async def kullanim_yaz(db: AsyncSession, kod: IndirimKodlari, belge_turu: str, belge_id: int, eposta: Optional[str],
                       tutar: Decimal, para_birimi: Optional[str]) -> None:
    """Belge başına tek satır (varsa güncellenir). Commit ETMEZ."""
    K = IndirimKoduKullanimlari
    satir = (await db.execute(select(K).where(K.belge_turu == belge_turu, K.belge_id == int(belge_id)))).scalars().first()
    if satir is None:
        db.add(K(kod_id=kod.id, belge_turu=belge_turu, belge_id=int(belge_id), eposta=(eposta or "").strip().lower() or None,
                 tutar=float(tutar), para_birimi=para_birimi))
    else:
        satir.kod_id = kod.id
        satir.eposta = (eposta or "").strip().lower() or None
        satir.tutar = float(tutar)
        satir.para_birimi = para_birimi
    await db.flush()


async def kullanim_sil(db: AsyncSession, belge_turu: str, belge_id: int) -> None:
    K = IndirimKoduKullanimlari
    await db.execute(delete(K).where(K.belge_turu == belge_turu, K.belge_id == int(belge_id)))


async def kullanim_tasi(db: AsyncSession, belge_turu: str, eski_id: int, yeni_id: int) -> None:
    """Revizyon: kullanım yeni sürüme geçer (eski sürüm sayımda zaten ölü)."""
    K = IndirimKoduKullanimlari
    await db.execute(update(K).where(K.belge_turu == belge_turu, K.belge_id == int(eski_id)).values(belge_id=int(yeni_id)))


# ---------------------------------------------------------------------------
# Doğrulama ve hesap
# ---------------------------------------------------------------------------
def isaretlileri_at(kalemler: Any) -> List[Any]:
    if not isinstance(kalemler, list):
        return kalemler
    return [k for k in kalemler if not (isinstance(k, dict) and k.get("indirim_kodu"))]


def tarih_durumu(k: IndirimKodlari, bugun: Optional[date] = None) -> Optional[str]:
    bugun = bugun or _bugun()
    bas, bit = _tarih(k.baslangic), _tarih(k.bitis)
    if bas and bugun < bas:
        return "kod_baslamadi"
    if bit and bugun > bit:
        return "kod_suresi_doldu"
    return None


async def dogrula(
    db: AsyncSession,
    k: Optional[IndirimKodlari],
    *,
    belge_turu: str,
    para_birimi: Optional[str],
    ara_toplam: Optional[Decimal],
    eposta: Optional[str],
    haric: Optional[Tuple[str, int]] = None,
    bugun: Optional[date] = None,
    ek_kapsam: Tuple[str, ...] = (),
    paket: Optional[str] = None,
) -> IndirimKodlari:
    """Kod bu belgeye uygulanabilir mi? Değilse KodHatasi (sıra: var mı, aktif, tarih, kapsam, paket, para, en az,
    sınırlar).

    `ek_kapsam`: belge başka bir kapsamın da karşılığıysa (fiyat sihirbazından çevrilen teklif = hizmet paketi).
    `paket`: belgenin fiyat talebindeki paket (yoksa None — paketle sınırlı kod uygulanmaz)."""
    if k is None:
        raise KodHatasi(404, "kod_yok")
    if not k.aktif:
        raise KodHatasi(409, "kod_pasif")
    td = tarih_durumu(k, bugun)
    if td:
        raise KodHatasi(409, td, baslangic=k.baslangic, bitis=k.bitis)
    if not ({belge_turu, *ek_kapsam} & set(kapsam(k))):
        raise KodHatasi(409, "kod_kapsam_disi")
    pk = paketler(k)
    if pk and (paket or "").upper() not in pk:
        raise KodHatasi(409, "kod_paket_disi")
    pb = (para_birimi or "").upper() or None
    if k.para_birimi and pb and pb != k.para_birimi and (k.tur == "sabit" or k.en_az_tutar):
        raise KodHatasi(409, "kod_para_birimi", para_birimi=k.para_birimi)
    if k.en_az_tutar and ara_toplam is not None and ara_toplam < Decimal(str(k.en_az_tutar)):
        raise KodHatasi(409, "kod_en_az_tutar", en_az=float(k.en_az_tutar), para_birimi=k.para_birimi or pb)
    if k.toplam_sinir is not None and await canli_kullanim(db, k.id, haric=haric) >= int(k.toplam_sinir):
        raise KodHatasi(409, "kod_tukendi")
    e = (eposta or "").strip().lower()
    if k.kisi_basi_sinir is not None and e and await canli_kullanim(db, k.id, eposta=e, haric=haric) >= int(k.kisi_basi_sinir):
        raise KodHatasi(409, "kod_kisi_siniri")
    if k.ortak_id and e:
        o = (await db.execute(select(Ortaklar).where(Ortaklar.id == k.ortak_id))).scalars().first()
        if o is not None:
            from services import ortaklik

            if await ortaklik.kendi_mi(db, o, e):
                raise KodHatasi(409, "kendi_referansi")
    return k


def indirim_satirlari(k: IndirimKodlari, kalemler: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Decimal]:
    """Normal kalemlerden KDV oranı başına indirim satırları ve toplam indirim (KDV hariç)."""
    belge = belge_hesapla(kalemler, bos_olabilir=True)
    dokum = [(ondalik(d["oran"]), ondalik(d["matrah"])) for d in belge.kdv_dokumu if ondalik(d["matrah"]) > 0]
    toplam = sum((m for _, m in dokum), Decimal("0"))
    if toplam <= 0:
        return [], Decimal("0")
    paylar: List[Tuple[Decimal, Decimal]] = []
    if k.tur == "yuzde":
        yuzde = min(max(ondalik(k.deger), Decimal("0")), YUZ)
        paylar = [(oran, min(kurus(m * yuzde / YUZ), m)) for oran, m in dokum]
    else:
        hedef = min(kurus(ondalik(k.deger)), toplam)
        kalan = hedef
        for i, (oran, m) in enumerate(dokum):
            pay = kalan if i == len(dokum) - 1 else min(kurus(hedef * m / toplam), m, kalan)
            pay = min(pay, m)
            paylar.append((oran, pay))
            kalan -= pay
    satirlar = []
    coklu = len([p for p in paylar if p[1] > 0]) > 1
    for oran, pay in paylar:
        if pay <= 0:
            continue
        aciklama = f"İndirim ({k.kod})" + (f" — KDV %{oran.normalize():f}" if coklu else "")
        satirlar.append({"aciklama": aciklama, "adet": 1, "birim_fiyat": float(-pay), "kdv_orani": float(oran),
                         "indirim": 0, "indirim_kodu": k.kod})
    return satirlar, sum((p for _, p in paylar), Decimal("0"))


@dataclass
class Uygulama:
    kalemler: List[Dict[str, Any]]
    kod: Optional[IndirimKodlari]
    indirim: Decimal
    #: True: yeni kod uygulandı (kullanım yazılmalı); False: mevcut kod yeniden uygulandı / kod yok.
    yeni: bool
    #: True: belgedeki kod kaldırıldı (kullanım silinmeli).
    kaldirildi: bool


async def belgeye_uygula(
    db: AsyncSession,
    *,
    kalemler: Any,
    ham_kod: Optional[str],
    mevcut_kod: Optional[str],
    belge_turu: str,
    belge_id: Optional[int],
    para_birimi: Optional[str],
    eposta: Optional[str],
    ek_kapsam: Tuple[str, ...] = (),
    paket: Optional[str] = None,
) -> Uygulama:
    """`ham_kod` None: istemci kod göndermedi (mevcut kod varsa yeniden uygula), "": kodu kaldır."""
    temiz = isaretlileri_at(kalemler) if isinstance(kalemler, list) else []
    hedef = mevcut_kod if ham_kod is None else ham_kod
    if not (hedef or "").strip():
        return Uygulama(temiz, None, Decimal("0"), False, bool(mevcut_kod))
    k = await kod_bul(db, hedef)
    ayni = bool(mevcut_kod) and kod_anahtari(mevcut_kod) == kod_anahtari(hedef)
    ara = belge_hesapla(temiz, bos_olabilir=True).ara_toplam  # HesapHatasi çağırana
    if ayni:
        # Kod zaten bu belgede: süre/sınır yeniden sınanmaz (kullanım sayıldı), para birimi uyumu yine şart.
        if k is None:
            return Uygulama(temiz, None, Decimal("0"), False, True)
        if k.tur == "sabit" and k.para_birimi and para_birimi and para_birimi.upper() != k.para_birimi:
            raise KodHatasi(409, "kod_para_birimi", para_birimi=k.para_birimi)
    else:
        if not bicim_gecerli(hedef):
            raise KodHatasi(400, "kod_gecersiz")
        haric = (belge_turu, int(belge_id)) if belge_id else None
        await dogrula(db, k, belge_turu=belge_turu, para_birimi=para_birimi, ara_toplam=ara, eposta=eposta, haric=haric,
                      ek_kapsam=ek_kapsam, paket=paket)
    satirlar, indirim = indirim_satirlari(k, temiz)
    return Uygulama(temiz + satirlar, k, indirim, not ayni, bool(mevcut_kod) and not ayni)


async def kullanimi_isle(db: AsyncSession, u: Uygulama, belge_turu: str, belge_id: int, eposta: Optional[str],
                         para_birimi: Optional[str]) -> None:
    """Uygulamanın kullanım kaydına etkisi (commit ETMEZ) + koda bağlı ortak atfı."""
    if u.kod is None:
        if u.kaldirildi:
            await kullanim_sil(db, belge_turu, belge_id)
        return
    if u.yeni:
        await kullanim_yaz(db, u.kod, belge_turu, belge_id, eposta, u.indirim, para_birimi)
        if u.kod.ortak_id and eposta:
            from services import ortaklik

            o = (await db.execute(select(Ortaklar).where(Ortaklar.id == u.kod.ortak_id))).scalars().first()
            await ortaklik.atif_yaz(db, musteri_eposta=eposta, ortak=o, kaynak="kod")


# ---------------------------------------------------------------------------
# Formdan gelen kod (iletişim / teklif al)
# ---------------------------------------------------------------------------
async def formdan_coz(db: AsyncSession, ham: Any) -> Dict[str, Any]:
    """Tek alan: indirim kodu mu ortak kodu mu? Geçersiz biçim ya da bilinmeyen kod → boş (sessiz).

    Dönen: {"indirim_kodu", "referans_kodu", "ortak"} — kod koda bağlı ortağı da getirir.
    """
    sonuc: Dict[str, Any] = {"indirim_kodu": None, "referans_kodu": None, "ortak": None}
    if not ham or not bicim_gecerli(ham):
        return sonuc
    k = await kod_bul(db, ham)
    if k is not None and k.aktif and tarih_durumu(k) is None:
        sonuc["indirim_kodu"] = k.kod
        if k.ortak_id:
            o = (await db.execute(select(Ortaklar).where(Ortaklar.id == k.ortak_id, Ortaklar.durum == "onaylandi"))).scalars().first()
            if o is not None:
                sonuc["ortak"] = o
                sonuc["referans_kodu"] = o.kod
        return sonuc
    o = await ortak_kodu_bul(db, ham)
    if o is not None:
        sonuc["ortak"] = o
        sonuc["referans_kodu"] = o.kod
    return sonuc


# ---------------------------------------------------------------------------
# Yönetim
# ---------------------------------------------------------------------------
def _sayi(ham: Any, kod: str) -> Optional[Decimal]:
    if ham is None or ham == "":
        return None
    try:
        d = ondalik(ham, kod)
    except HesapHatasi:
        raise KodHatasi(400, kod)
    return d


def _tam(ham: Any, kod: str) -> Optional[int]:
    if ham is None or ham == "":
        return None
    try:
        n = int(ham)
    except (TypeError, ValueError):
        raise KodHatasi(400, kod)
    if n < 1 or n > 1_000_000:
        raise KodHatasi(400, kod)
    return n


async def alanlari_uygula(db: AsyncSession, k: IndirimKodlari, g: Dict[str, Any], *, yeni: bool) -> None:
    if "kod" in g or yeni:
        if not bicim_gecerli(g.get("kod")):
            raise KodHatasi(400, "kod_gecersiz")
        anahtar = kod_anahtari(g.get("kod"))
        if not await ad_alani_bos_mu(db, anahtar, haric_kod=k.id):
            raise KodHatasi(409, "kod_kullaniliyor")
        k.kod = kod_gorunen(g.get("kod"))
        k.kod_anahtar = anahtar
    if "aciklama" in g or yeni:
        k.aciklama = (" ".join(str(g.get("aciklama") or "").split())[:ACIKLAMA_SINIRI]) or None
    if "tur" in g or yeni:
        tur = str(g.get("tur") or "yuzde")
        if tur not in TURLER:
            raise KodHatasi(400, "tur_gecersiz")
        k.tur = tur
    if "deger" in g or yeni:
        d = _sayi(g.get("deger"), "deger_gecersiz")
        if d is None or d <= 0 or (k.tur == "yuzde" and d > 100) or d > Decimal("100000000"):
            raise KodHatasi(400, "deger_gecersiz")
        k.deger = float(kurus(d) if k.tur == "sabit" else d.quantize(Decimal("0.01")))
    elif k.tur == "yuzde" and (k.deger or 0) > 100:
        raise KodHatasi(400, "deger_gecersiz")
    if "para_birimi" in g or yeni:
        pb = (str(g.get("para_birimi") or "").strip().upper()) or None
        if pb and pb not in PARA_BIRIMLERI:
            raise KodHatasi(400, "para_birimi_gecersiz")
        k.para_birimi = pb
    for alan in ("baslangic", "bitis"):
        if alan in g or yeni:
            ham = g.get(alan)
            if ham in (None, ""):
                setattr(k, alan, None)
            else:
                t = _tarih(ham)
                if t is None:
                    raise KodHatasi(400, "tarih_gecersiz")
                setattr(k, alan, t.isoformat())
    if k.baslangic and k.bitis and k.bitis < k.baslangic:
        raise KodHatasi(400, "tarih_gecersiz")
    if "toplam_sinir" in g or yeni:
        k.toplam_sinir = _tam(g.get("toplam_sinir"), "sinir_gecersiz")
    if "kisi_basi_sinir" in g or yeni:
        k.kisi_basi_sinir = _tam(g.get("kisi_basi_sinir"), "sinir_gecersiz")
    if "en_az_tutar" in g or yeni:
        d = _sayi(g.get("en_az_tutar"), "en_az_gecersiz")
        if d is not None and d < 0:
            raise KodHatasi(400, "en_az_gecersiz")
        k.en_az_tutar = float(kurus(d)) if d else None
    if k.tur == "sabit" and not k.para_birimi:
        raise KodHatasi(400, "para_birimi_gerekli")
    if k.en_az_tutar and not k.para_birimi:
        raise KodHatasi(400, "para_birimi_gerekli")
    if "kapsam" in g or yeni:
        secili = [x for x in _liste(g.get("kapsam") or []) if x in KAPSAMLAR]
        if "kapsam" in g and not secili:
            raise KodHatasi(400, "kapsam_gerekli")
        k.kapsam = json.dumps(secili or list(KAPSAMLAR))
    if "paketler" in g or yeni:
        ham = _liste(g.get("paketler") or [])
        secili = []
        for x in ham:
            x = str(x).strip().upper()
            if not _PAKET.match(x):
                raise KodHatasi(400, "paket_gecersiz")
            if x not in secili:
                secili.append(x)
        k.paketler = json.dumps(secili[:20]) if secili else None
    if "ortak_id" in g or yeni:
        oid = g.get("ortak_id") or None
        if oid is not None:
            try:
                oid = int(oid)
            except (TypeError, ValueError):
                raise KodHatasi(400, "ortak_yok")
            if (await db.execute(select(Ortaklar.id).where(Ortaklar.id == oid, Ortaklar.hesap == AJANS))).scalar() is None:
                raise KodHatasi(400, "ortak_yok")
        k.ortak_id = oid
    if "aktif" in g or yeni:
        k.aktif = g.get("aktif") is not False


async def kod_sozlugu(db: AsyncSession, k: IndirimKodlari, ortak_adlari: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    from services.api_erisimi import iso

    return {
        "id": k.id, "kod": k.kod, "aciklama": k.aciklama, "tur": k.tur, "deger": k.deger, "para_birimi": k.para_birimi,
        "baslangic": k.baslangic, "bitis": k.bitis, "toplam_sinir": k.toplam_sinir, "kisi_basi_sinir": k.kisi_basi_sinir,
        "en_az_tutar": k.en_az_tutar, "kapsam": kapsam(k), "paketler": paketler(k), "ortak_id": k.ortak_id,
        "ortak_ad": (ortak_adlari or {}).get(k.ortak_id) if k.ortak_id else None,
        "aktif": bool(k.aktif), "kullanim": await canli_kullanim(db, k.id),
        "durum": "pasif" if not k.aktif else (tarih_durumu(k) or "gecerli"),
        "olusturan": k.olusturan, "created_at": iso(k.created_at),
    }


async def liste(db: AsyncSession) -> List[Dict[str, Any]]:
    kodlar = (await db.execute(select(IndirimKodlari).where(IndirimKodlari.hesap == AJANS)
                               .order_by(IndirimKodlari.id.desc()).limit(500))).scalars().all()
    ortak_idleri = {k.ortak_id for k in kodlar if k.ortak_id}
    adlar: Dict[int, str] = {}
    if ortak_idleri:
        adlar = {int(i): a for i, a in (await db.execute(select(Ortaklar.id, Ortaklar.ad).where(Ortaklar.id.in_(ortak_idleri)))).all()}
    return [await kod_sozlugu(db, k, adlar) for k in kodlar]


async def olustur(db: AsyncSession, g: Dict[str, Any], yapan: Optional[str]) -> IndirimKodlari:
    k = IndirimKodlari(hesap=AJANS, olusturan=(yapan or "").strip().lower() or None)
    await alanlari_uygula(db, k, g, yeni=True)
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return k


async def guncelle(db: AsyncSession, k: IndirimKodlari, g: Dict[str, Any]) -> IndirimKodlari:
    if "kod" in g and kod_anahtari(g.get("kod")) != k.kod_anahtar and await canli_kullanim(db, k.id) > 0:
        # Belgelerde "İndirim (KOD)" yazıyor: kullanılmış kodun adı değişmez (yeni kod açılır).
        raise KodHatasi(409, "kullanilmis_kod_adi")
    await alanlari_uygula(db, k, g, yeni=False)
    await db.commit()
    await db.refresh(k)
    return k


async def sil(db: AsyncSession, k: IndirimKodlari) -> None:
    if await canli_kullanim(db, k.id) > 0:
        raise KodHatasi(409, "kullanilmis_kod_silinemez")
    await db.execute(delete(IndirimKoduKullanimlari).where(IndirimKoduKullanimlari.kod_id == k.id))
    await db.delete(k)
    await db.commit()


async def getir(db: AsyncSession, kod_id: int) -> IndirimKodlari:
    k = (await db.execute(select(IndirimKodlari).where(IndirimKodlari.id == kod_id, IndirimKodlari.hesap == AJANS))).scalars().first()
    if k is None:
        raise KodHatasi(404, "kod_yok")
    return k


def herkese_acik(k: IndirimKodlari) -> Dict[str, Any]:
    """Doğrulama ucunun döndürdüğü asgari bilgi (sınırlar, kullanım, ortak YOK)."""
    return {"kod": k.kod, "tur": k.tur, "deger": k.deger, "para_birimi": k.para_birimi, "bitis": k.bitis,
            "en_az_tutar": k.en_az_tutar}


__all__ = [
    "KodHatasi", "kod_anahtari", "kod_gorunen", "bicim_gecerli", "kod_bul", "ortak_kodu_bul", "ad_alani_bos_mu",
    "canli_kullanim", "dogrula", "indirim_satirlari", "belgeye_uygula", "kullanimi_isle", "formdan_coz", "liste",
    "paketler", "talep_paketi", "belge_paketi",
    "olustur", "guncelle", "sil", "getir", "herkese_acik", "isaretlileri_at", "kullanim_tasi", "kullanim_sil",
]
