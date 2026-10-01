"""Faz 3C — CRM ve aday hunisi: servis katmanı.

Yalnız ajansın kendi satış hunisi (yönetici). Müşteri portalında karşılığı yok.

Otomatik aday oluşturma — neden flush kancası?
----------------------------------------------
Talepler tek bir kapıdan girmiyor: iletişim formu, bekleme listesi, keşif
sihirbazı ve Kaynaklar sayfası `inquiries` entity ucundan; site analizi adayı
kendi router'ından doğrudan ORM ile; "Teklif Al" / "Satın Al" fiyatlandırma
router'ından `pricing_inquiries`'e yazıyor. Denetim kaydı ve çöp kutusu gibi
burada da ortak nokta SQLAlchemy'nin iş birimi: `after_flush` olayında yeni
`inquiries` / `pricing_inquiries` satırları görülüyor ve aday işi AYNI işlemde
bir SAVEPOINT içinde yapılıyor.

* Asıl kayıt ASLA bozulmuyor: kancadaki her hata yalnız SAVEPOINT'i geri
  alıyor (ve günlüğe yazılıyor); talep yine kaydediliyor. Asıl işlem geri
  alınırsa aday da gidiyor (yarım aday kalmıyor).
* Mevcut akışların hiçbirine dokunulmadı; yeni bir talep kaynağı eklenirse
  kendiliğinden kapsanıyor.
* Tekilleştirme: aynı e-postada AÇIK (aşama türü `acik`) bir aday varsa yeni
  aday açılmıyor, talep o adayın zaman çizelgesine "yeni talep" olarak
  ekleniyor. Kazanılmış/kaybedilmiş aday kapalı sayılıyor: aynı kişi yeniden
  yazarsa yeni fırsat açılıyor.
* (tablo, kayit_id) `crm_bagli_kayitlar`da benzersiz: aynı kayıt iki kez
  işlenmiyor — "geçmiş talepleri içe aktar" bu yüzden idempotent.

Aday işinin kendisi (`kayittan_aday_sync`) Core SQL ile bir `Connection`
üzerinde çalışıyor; kanca (eşzamanlı bağlam) da, form ucu ve içe aktarma
(`AsyncSession.run_sync`) da aynı fonksiyonu kullanıyor.

Puanlama (0–100) — kurallar sabit ve testli (`puan_hesapla`)
------------------------------------------------------------
* kaynak (en çok 30): fiyat teklifi 30, keşif 25, form/iletişim 20,
  e-posta/site analizi/kaynaklar 15, elle 10, bekleme listesi 5
* bütçe (15): tahmini değer ya da belirtilmiş bütçe varsa
* kapsam (10): ilk mesaj ≥ 300 karakter 10, ≥ 100 karakter 5
* e-posta alan adı (20): kurumsal 20, ücretsiz sağlayıcı (gmail…) 5, yok 0
* etkileşim (25): elle girilen not/arama/e-posta/toplantı ve sonradan gelen
  her talep 5 puan
Ayrıntı (`puan_ayrinti`) arayüzde "neden bu puan" olarak gösteriliyor.

Bildirimler
-----------
* `crm_yeni_aday`: form gönderimi (anında) ve kendi bildirimi olmayan
  kaynaktan (fiyat teklifi) açılan yeni aday (zamanlı görev, her turda). İletişim
  formu / site analizi zaten `inquiry` / `site_analizi_aday` bildirimi
  gönderiyor; çift e-posta olmasın diye bunlar için ayrıca atılmıyor.
* `crm_hatirlatma`: sonraki adım tarihi gelmiş/geçmiş açık adaylar — günde
  bir özet (sorumluya; sorumlu yoksa yöneticilere). Aday başına
  `hatirlatma_tarihi` aynı gün ikinci kez gönderilmesini engelliyor.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.crm import CrmAdaylari, CrmAktiviteler, CrmAsamalari, CrmBagliKayitlar
from sqlalchemy import event, func, or_, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
KAYNAKLAR: Tuple[str, ...] = (
    "iletisim", "bekleme", "site_analizi", "kesif", "fiyat_teklifi", "kaynaklar", "form", "manuel", "eposta",
)
AKTIVITE_TURLERI: Tuple[str, ...] = ("not", "arama", "eposta", "toplanti", "asama", "sistem")
#: Panelden elle eklenebilen aktiviteler (etkileşim sayılanlar da bunlar).
ELLE_AKTIVITE_TURLERI: Tuple[str, ...] = ("not", "arama", "eposta", "toplanti")
ASAMA_TURLERI: Tuple[str, ...] = ("acik", "kazanildi", "kaybedildi")
RENKLER: Tuple[str, ...] = ("slate", "sky", "violet", "amber", "orange", "emerald", "rose", "pink", "teal")
PARA_BIRIMLERI: Tuple[str, ...] = ("TRY", "USD", "EUR", "GBP")
SIRALAMALAR: Tuple[str, ...] = (
    "-puan", "puan", "-created_at", "created_at", "-updated_at", "updated_at",
    "-deger_tahmini", "deger_tahmini", "ad", "-ad", "sonraki_adim_tarihi", "-sonraki_adim_tarihi",
)

#: Alan uzunluk sınırları (panel ve form aynı sınırları kullanıyor).
SINIR = {
    "ad": 120, "firma": 160, "email": 254, "telefon": 40, "notlar": 10000, "sonraki_adim": 300,
    "kaybedilme_nedeni": 1000, "butce": 120, "etiket": 40, "etiket_sayisi": 20, "metin": 4000,
    "asama_ad": 60, "kaynak_detay": 200,
}

_EPOSTA = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

VARSAYILAN_ASAMALAR: Tuple[Dict[str, Any], ...] = (
    {
        "anahtar": "yeni", "ad": "Yeni", "renk": "slate", "tur": "acik", "olasilik": 10,
        "ceviriler": {"en": {"ad": "New"}, "de": {"ad": "Neu"}, "ru": {"ad": "Новый"}, "zh": {"ad": "新线索"},
                      "hi": {"ad": "नया"}, "ar": {"ad": "جديد"}},
    },
    {
        "anahtar": "iletisim_kuruldu", "ad": "İletişim kuruldu", "renk": "sky", "tur": "acik", "olasilik": 20,
        "ceviriler": {"en": {"ad": "Contacted"}, "de": {"ad": "Kontaktiert"}, "ru": {"ad": "Связались"},
                      "zh": {"ad": "已联系"}, "hi": {"ad": "संपर्क हुआ"}, "ar": {"ad": "تم التواصل"}},
    },
    {
        "anahtar": "kesif_gorusmesi", "ad": "Keşif görüşmesi", "renk": "violet", "tur": "acik", "olasilik": 40,
        "ceviriler": {"en": {"ad": "Discovery call"}, "de": {"ad": "Erstgespräch"},
                      "ru": {"ad": "Ознакомительная встреча"}, "zh": {"ad": "需求沟通"}, "hi": {"ad": "डिस्कवरी कॉल"},
                      "ar": {"ad": "مكالمة استكشافية"}},
    },
    {
        "anahtar": "teklif_gonderildi", "ad": "Teklif gönderildi", "renk": "amber", "tur": "acik", "olasilik": 60,
        "ceviriler": {"en": {"ad": "Proposal sent"}, "de": {"ad": "Angebot gesendet"},
                      "ru": {"ad": "Предложение отправлено"}, "zh": {"ad": "已发送报价"},
                      "hi": {"ad": "प्रस्ताव भेजा गया"}, "ar": {"ad": "تم إرسال العرض"}},
    },
    {
        "anahtar": "pazarlik", "ad": "Pazarlık", "renk": "orange", "tur": "acik", "olasilik": 80,
        "ceviriler": {"en": {"ad": "Negotiation"}, "de": {"ad": "Verhandlung"}, "ru": {"ad": "Переговоры"},
                      "zh": {"ad": "谈判中"}, "hi": {"ad": "मोलभाव"}, "ar": {"ad": "التفاوض"}},
    },
    {
        "anahtar": "kazanildi", "ad": "Kazanıldı", "renk": "emerald", "tur": "kazanildi", "olasilik": 100,
        "ceviriler": {"en": {"ad": "Won"}, "de": {"ad": "Gewonnen"}, "ru": {"ad": "Выиграно"}, "zh": {"ad": "已成交"},
                      "hi": {"ad": "जीता गया"}, "ar": {"ad": "تم الفوز"}},
    },
    {
        "anahtar": "kaybedildi", "ad": "Kaybedildi", "renk": "rose", "tur": "kaybedildi", "olasilik": 0,
        "ceviriler": {"en": {"ad": "Lost"}, "de": {"ad": "Verloren"}, "ru": {"ad": "Проиграно"}, "zh": {"ad": "已流失"},
                      "hi": {"ad": "खो दिया"}, "ar": {"ad": "خسارة"}},
    },
)

# --- Puanlama ----------------------------------------------------------------
KAYNAK_PUANI: Dict[str, int] = {
    "fiyat_teklifi": 30, "kesif": 25, "form": 20, "iletisim": 20, "eposta": 15,
    "site_analizi": 15, "kaynaklar": 15, "manuel": 10, "bekleme": 5,
}
PUAN_EN_COK: Dict[str, int] = {"kaynak": 30, "butce": 15, "kapsam": 10, "alan_adi": 20, "etkilesim": 25}
KAPSAM_ESIKLERI: Tuple[Tuple[int, int], ...] = ((300, 10), (100, 5))
ETKILESIM_PUANI = 5
ALAN_ADI_PUANI = {"kurumsal": 20, "ucretsiz": 5, "yok": 0}

#: Ücretsiz/kişisel e-posta sağlayıcıları (kurumsal sayılmaz).
UCRETSIZ_ALANLAR = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "yahoo.fr", "yahoo.de", "ymail.com",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.de", "hotmail.com.tr", "outlook.com",
    "outlook.com.tr", "live.com", "live.co.uk", "msn.com", "windowslive.com", "icloud.com", "me.com",
    "mac.com", "aol.com", "yandex.com", "yandex.ru", "yandex.com.tr", "ya.ru", "mail.ru", "bk.ru",
    "inbox.ru", "list.ru", "rambler.ru", "proton.me", "protonmail.com", "pm.me", "gmx.com", "gmx.de",
    "gmx.net", "web.de", "t-online.de", "zoho.com", "qq.com", "163.com", "126.com", "sina.com",
    "yeah.net", "foxmail.com", "rediffmail.com", "mynet.com", "tutanota.com", "tuta.io", "hey.com",
    "fastmail.com", "mail.com", "email.com", "seznam.cz", "libero.it", "orange.fr", "free.fr",
})

#: Keşif özetindeki bütçe satırı (7 dilde başlık; KesifAsistani `kesif.s4Baslik`).
_BUTCE_SATIRI = re.compile(
    r"^\s*(?:Bütçe aralığı|Bütçe|Budget range|Budget|Budgetrahmen|Бюджет|预算范围|预算|बजट सीमा|बजट|نطاق الميزانية|الميزانية)"
    r"\s*[:：]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _bugun() -> date:
    """Türkiye saatine göre bugün (testler monkeypatch ile kaydırıyor)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except Exception:  # noqa: BLE001
        return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def bugun() -> date:
    return _bugun()


def yerel_gun(an: Any) -> Optional[date]:
    """UTC zaman → Türkiye saatine göre gün."""
    an = utc(an)
    if an is None:
        return None
    try:
        from zoneinfo import ZoneInfo

        return an.astimezone(ZoneInfo("Europe/Istanbul")).date()
    except Exception:  # noqa: BLE001
        return (an + timedelta(hours=3)).date()


def utc(an: Any) -> Optional[datetime]:
    if an is None or not isinstance(an, datetime):
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Any) -> Optional[str]:
    if an is None:
        return None
    if isinstance(an, datetime):
        return utc(an).isoformat()  # type: ignore[union-attr]
    if isinstance(an, date):
        return an.isoformat()
    return str(an)


def tarih_coz(deger: Any) -> Optional[date]:
    if deger in (None, ""):
        return None
    if isinstance(deger, datetime):
        return deger.date()
    if isinstance(deger, date):
        return deger
    try:
        return date.fromisoformat(str(deger)[:10])
    except ValueError:
        return None


def eposta_duzelt(eposta: Any) -> str:
    return str(eposta or "").strip().lower()


def eposta_gecerli(eposta: str) -> bool:
    return bool(eposta) and len(eposta) <= SINIR["email"] and bool(_EPOSTA.match(eposta))


def json_liste(deger: Any) -> List[Any]:
    if isinstance(deger, list):
        return deger
    try:
        cozulen = json.loads(deger) if deger else []
    except (TypeError, ValueError):
        return []
    return cozulen if isinstance(cozulen, list) else []


def json_sozluk(deger: Any) -> Dict[str, Any]:
    if isinstance(deger, dict):
        return deger
    try:
        cozulen = json.loads(deger) if deger else {}
    except (TypeError, ValueError):
        return {}
    return cozulen if isinstance(cozulen, dict) else {}


def etiketleri_duzelt(ham: Any) -> List[str]:
    """Küçük harf, kırpılmış, tekrarsız; sınırı aşan ValueError."""
    if ham in (None, ""):
        return []
    if isinstance(ham, str):
        ham = [p for p in ham.split(",")]
    if not isinstance(ham, (list, tuple)):
        raise ValueError("etiketler")
    sonuc: List[str] = []
    for e in ham:
        e = " ".join(str(e or "").split()).lower()
        if not e:
            continue
        if len(e) > SINIR["etiket"]:
            raise ValueError("etiket_uzun")
        if e not in sonuc:
            sonuc.append(e)
    if len(sonuc) > SINIR["etiket_sayisi"]:
        raise ValueError("etiket_sayisi")
    return sonuc


# ---------------------------------------------------------------------------
# Kaynak eşlemesi ve puan
# ---------------------------------------------------------------------------
def kaynak_esle(tablo: Optional[str], ham: Optional[str]) -> str:
    """Kaynak kaydın tablosu + ham `source` değeri → CRM kaynağı."""
    if tablo == "pricing_inquiries":
        return "fiyat_teklifi"
    if tablo == "crm_form_gonderimleri":
        return "form"
    s = (ham or "").strip().lower()
    if s.startswith("bekleme"):
        return "bekleme"
    if s.startswith("site_analizi") or s.startswith("site-analizi"):
        return "site_analizi"
    if s.startswith("kesif"):
        return "kesif"
    if s.startswith("kaynaklar"):
        return "kaynaklar"
    if s.startswith("eposta") or s.startswith("e-posta") or s == "email":
        return "eposta"
    # iletisim-formu, contact, marketplace: …, modul: …, boş
    return "iletisim"


def alan_adi_turu(eposta: Optional[str]) -> str:
    """kurumsal | ucretsiz | yok"""
    e = eposta_duzelt(eposta)
    if not eposta_gecerli(e):
        return "yok"
    alan = e.rsplit("@", 1)[1].strip(".")
    if alan in UCRETSIZ_ALANLAR:
        return "ucretsiz"
    return "kurumsal"


def butceyi_bul(metin: Optional[str]) -> Optional[str]:
    """Keşif özetindeki "Bütçe aralığı: …" satırı."""
    if not metin:
        return None
    m = _BUTCE_SATIRI.search(metin)
    return m.group(1)[: SINIR["butce"]] if m else None


def puan_hesapla(
    *,
    kaynak: str,
    email: Optional[str],
    deger_tahmini: Optional[float] = None,
    butce: Optional[str] = None,
    ilk_mesaj: Optional[str] = None,
    etkilesim: int = 0,
) -> Tuple[int, List[Dict[str, Any]]]:
    """(puan, ayrıntı). Her kural `{kural, puan, en_cok, deger}` satırı."""
    ayrinti: List[Dict[str, Any]] = []

    k = KAYNAK_PUANI.get(kaynak, KAYNAK_PUANI["manuel"])
    ayrinti.append({"kural": "kaynak", "puan": k, "en_cok": PUAN_EN_COK["kaynak"], "deger": kaynak})

    butce_var = bool((deger_tahmini or 0) > 0 or (butce or "").strip())
    ayrinti.append({
        "kural": "butce", "puan": PUAN_EN_COK["butce"] if butce_var else 0,
        "en_cok": PUAN_EN_COK["butce"], "deger": butce_var,
    })

    uzunluk = len((ilk_mesaj or "").strip())
    kapsam = next((p for esik, p in KAPSAM_ESIKLERI if uzunluk >= esik), 0)
    ayrinti.append({"kural": "kapsam", "puan": kapsam, "en_cok": PUAN_EN_COK["kapsam"], "deger": uzunluk})

    alan = alan_adi_turu(email)
    ayrinti.append({"kural": "alan_adi", "puan": ALAN_ADI_PUANI[alan], "en_cok": PUAN_EN_COK["alan_adi"], "deger": alan})

    n = max(0, int(etkilesim or 0))
    ayrinti.append({
        "kural": "etkilesim", "puan": min(PUAN_EN_COK["etkilesim"], n * ETKILESIM_PUANI),
        "en_cok": PUAN_EN_COK["etkilesim"], "deger": n,
    })
    toplam = max(0, min(100, sum(a["puan"] for a in ayrinti)))
    return toplam, ayrinti


# ---------------------------------------------------------------------------
# Aşamalar
# ---------------------------------------------------------------------------
def _ascii_anahtar(metin: str) -> str:
    tablo = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c",
                           "ö": "o", "Ö": "o", "ü": "u", "Ü": "u"})
    s = unicodedata.normalize("NFKD", (metin or "").translate(tablo))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "asama"


def asamalari_tohumla_sync(c: Connection) -> bool:
    """Tablo boşsa varsayılan yedi aşamayı ekler. Eklediyse True."""
    tablo = CrmAsamalari.__table__
    sayi = c.execute(select(func.count()).select_from(tablo)).scalar() or 0
    if sayi:
        return False
    an = simdi()
    c.execute(
        tablo.insert(),
        [
            {
                "anahtar": a["anahtar"], "ad": a["ad"], "renk": a["renk"], "tur": a["tur"],
                "olasilik": a.get("olasilik"), "sira": (i + 1) * 10,
                "ceviriler": json.dumps(a["ceviriler"], ensure_ascii=False), "created_at": an, "updated_at": an,
            }
            for i, a in enumerate(VARSAYILAN_ASAMALAR)
        ],
    )
    return True


async def asamalari_hazirla(db: AsyncSession) -> None:
    """Uçların başında: aşama tablosu boşsa tohumla (açılış kancası testte çalışmıyor)."""
    var = (await db.execute(select(func.count(CrmAsamalari.id)))).scalar() or 0
    if var:
        return
    await db.run_sync(lambda s: asamalari_tohumla_sync(s.connection()))
    await db.commit()


async def acilista_tohumla() -> None:
    """Uygulama açılışı: hata açılışı düşürmez."""
    try:
        from core.database import db_manager

        if db_manager.async_session_maker is None:
            return
        async with db_manager.async_session_maker() as db:
            await asamalari_hazirla(db)
    except Exception:  # noqa: BLE001
        logger.exception("CRM aşama tohumu eklenemedi")


def _asamalar_sync(c: Connection) -> List[Dict[str, Any]]:
    t = CrmAsamalari.__table__
    return [dict(r) for r in c.execute(select(t).order_by(t.c.sira, t.c.id)).mappings().all()]


async def asamalar(db: AsyncSession) -> List[CrmAsamalari]:
    return list((await db.execute(select(CrmAsamalari).order_by(CrmAsamalari.sira, CrmAsamalari.id))).scalars().all())


def ilk_asama(liste: Sequence[Any], tur: str = "acik") -> Optional[Any]:
    for a in liste:
        if (a["tur"] if isinstance(a, dict) else a.tur) == tur:
            return a
    return None


def asama_sozlugu(a: CrmAsamalari, aday_sayisi: Optional[int] = None) -> Dict[str, Any]:
    d = {
        "anahtar": a.anahtar, "ad": a.ad, "ceviriler": json_sozluk(a.ceviriler), "sira": a.sira,
        "renk": a.renk, "tur": a.tur, "olasilik": a.olasilik,
    }
    if aday_sayisi is not None:
        d["aday_sayisi"] = aday_sayisi
    return d


def yeni_asama_anahtari(ad: str, mevcut: Iterable[str]) -> str:
    kok = _ascii_anahtar(ad)
    mevcut = set(mevcut)
    if kok not in mevcut:
        return kok
    i = 2
    while f"{kok}_{i}" in mevcut:
        i += 1
    return f"{kok}_{i}"


def ceviriler_duzelt(ham: Any) -> Dict[str, Dict[str, str]]:
    """{"en": {"ad": ".."}} — bilinmeyen dil/alan atılıyor, boşlar atılıyor."""
    from utils.ceviriler import CEVIRI_DILLERI

    sonuc: Dict[str, Dict[str, str]] = {}
    if not isinstance(ham, dict):
        return sonuc
    for dil in CEVIRI_DILLERI:
        girdi = ham.get(dil)
        ad = (girdi.get("ad") if isinstance(girdi, dict) else girdi) if girdi else None
        ad = " ".join(str(ad or "").split())[: SINIR["asama_ad"]]
        if ad:
            sonuc[dil] = {"ad": ad}
    return sonuc


# ---------------------------------------------------------------------------
# Aday ↔ sözlük
# ---------------------------------------------------------------------------
def aday_sozlugu(a: CrmAdaylari, ayrintili: bool = False) -> Dict[str, Any]:
    tarih = a.sonraki_adim_tarihi
    d: Dict[str, Any] = {
        "id": a.id, "ad": a.ad, "firma": a.firma, "email": a.email, "telefon": a.telefon,
        "kaynak": a.kaynak, "kaynak_detay": a.kaynak_detay, "asama": a.asama,
        "deger_tahmini": a.deger_tahmini, "para_birimi": a.para_birimi or "TRY", "olasilik": a.olasilik,
        "sorumlu": a.sorumlu, "etiketler": json_liste(a.etiketler), "sonraki_adim": a.sonraki_adim,
        "sonraki_adim_tarihi": iso(tarih), "gecikti": bool(tarih and tarih < bugun()),
        "bugun": bool(tarih and tarih == bugun()), "musteri_email": a.musteri_email, "puan": a.puan or 0,
        "created_at": iso(a.created_at), "updated_at": iso(a.updated_at), "asama_degisme_at": iso(a.asama_degisme_at),
    }
    if ayrintili:
        d.update({
            "notlar": a.notlar, "ilk_mesaj": a.ilk_mesaj, "butce": a.butce,
            "kaybedilme_nedeni": a.kaybedilme_nedeni, "puan_ayrinti": json_liste(a.puan_ayrinti),
            "kaynak_tablo": a.kaynak_tablo, "kaynak_id": a.kaynak_id,
            # Faz 4G: pazarlama (ticari ileti) izni — boşsa yok.
            "pazarlama_izni": a.pazarlama_izni_at is not None, "pazarlama_izni_at": iso(a.pazarlama_izni_at),
            "pazarlama_izni_kaynak": a.pazarlama_izni_kaynak, "pazarlama_metin_surumu": a.pazarlama_metin_surumu,
        })
    return d


def aktivite_sozlugu(k: CrmAktiviteler) -> Dict[str, Any]:
    return {
        "id": k.id, "aday_id": k.aday_id, "tur": k.tur, "olay": k.olay, "veri": json_sozluk(k.veri),
        "metin": k.metin, "yapan": k.yapan, "zaman": iso(k.zaman),
    }


# ---------------------------------------------------------------------------
# Etkileşim ve puan güncelleme
# ---------------------------------------------------------------------------
def _etkilesim_sorgulari(aday_id: int):
    akt = CrmAktiviteler.__table__
    bag = CrmBagliKayitlar.__table__
    elle = select(func.count()).select_from(akt).where(
        akt.c.aday_id == aday_id, akt.c.tur.in_(ELLE_AKTIVITE_TURLERI)
    )
    bagli = select(func.count()).select_from(bag).where(bag.c.aday_id == aday_id)
    return elle, bagli


def _puan_girdisi(satir: Any, etkilesim: int) -> Dict[str, Any]:
    al = (lambda k: satir[k]) if isinstance(satir, dict) else (lambda k: getattr(satir, k))
    return {
        "kaynak": al("kaynak"), "email": al("email"), "deger_tahmini": al("deger_tahmini"),
        "butce": al("butce"), "ilk_mesaj": al("ilk_mesaj"), "etkilesim": etkilesim,
    }


def puani_yenile_sync(c: Connection, aday_id: int) -> int:
    t = CrmAdaylari.__table__
    satir = c.execute(select(t).where(t.c.id == aday_id)).mappings().first()
    if satir is None:
        return 0
    elle_q, bagli_q = _etkilesim_sorgulari(aday_id)
    etkilesim = int(c.execute(elle_q).scalar() or 0) + max(0, int(c.execute(bagli_q).scalar() or 0) - 1)
    puan, ayrinti = puan_hesapla(**_puan_girdisi(dict(satir), etkilesim))
    c.execute(update(t).where(t.c.id == aday_id).values(puan=puan, puan_ayrinti=json.dumps(ayrinti)))
    return puan


async def puani_guncelle(db: AsyncSession, aday: CrmAdaylari) -> int:
    """ORM nesnesi üzerinde (panel uçları): puanı ve ayrıntısını yeniden yazar."""
    elle_q, bagli_q = _etkilesim_sorgulari(aday.id)
    etkilesim = int((await db.execute(elle_q)).scalar() or 0) + max(0, int((await db.execute(bagli_q)).scalar() or 0) - 1)
    puan, ayrinti = puan_hesapla(**_puan_girdisi(aday, etkilesim))
    aday.puan = puan
    aday.puan_ayrinti = json.dumps(ayrinti)
    return puan


# ---------------------------------------------------------------------------
# Kaynak kayıttan aday (çekirdek; eşzamanlı Connection üzerinde)
# ---------------------------------------------------------------------------
@dataclass
class TalepGirdisi:
    tablo: Optional[str]
    kayit_id: Optional[int]
    ad: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    firma: Optional[str] = None
    konu: Optional[str] = None
    mesaj: Optional[str] = None
    kaynak_ham: Optional[str] = None
    kaynak: Optional[str] = None
    deger_tahmini: Optional[float] = None
    para_birimi: Optional[str] = None
    butce: Optional[str] = None
    asama: Optional[str] = None
    etiketler: List[str] = field(default_factory=list)
    zaman: Optional[datetime] = None
    #: Yeni aday için `crm_yeni_aday` zamanlı görevle gönderilsin mi?
    bildirim: bool = False
    #: Aktivitedeki olay kodu ek bilgisi (içe aktarma, form adı…).
    ek_veri: Dict[str, Any] = field(default_factory=dict)
    yapan: str = "sistem"


def _kisa(metin: Optional[str], sinir: int) -> Optional[str]:
    if metin is None:
        return None
    metin = str(metin).strip()
    return metin[:sinir] if metin else None


def _acik_aday_sync(c: Connection, email: str) -> Optional[int]:
    a = CrmAdaylari.__table__
    s = CrmAsamalari.__table__
    sorgu = (
        select(a.c.id)
        .select_from(a.outerjoin(s, s.c.anahtar == a.c.asama))
        .where(a.c.email == email, or_(s.c.tur.is_(None), s.c.tur == "acik"))
        .order_by(a.c.id.desc())
        .limit(1)
    )
    return c.execute(sorgu).scalar()


def _aday_ekleme_sorgusu():
    """Ayrı fonksiyon: testler aday yazımını bilerek patlatabilsin."""
    return CrmAdaylari.__table__.insert()


def kayittan_aday_sync(c: Connection, g: TalepGirdisi) -> Optional[Dict[str, Any]]:
    """Kaynak kaydı CRM'e işler. Dönen: {"aday_id", "yeni"} ya da None (zaten işlenmiş).

    Aynı e-postada açık aday varsa ona "yeni talep" aktivitesi + bağ eklenir,
    yoksa yeni aday açılır. (tablo, kayit_id) daha önce işlendiyse hiçbir şey yapılmaz.
    """
    bag = CrmBagliKayitlar.__table__
    akt = CrmAktiviteler.__table__
    adt = CrmAdaylari.__table__
    if g.tablo and g.kayit_id is not None:
        islendi = c.execute(
            select(bag.c.id).where(bag.c.tablo == g.tablo, bag.c.kayit_id == int(g.kayit_id)).limit(1)
        ).scalar()
        if islendi:
            return None

    asamalari_tohumla_sync(c)
    an = utc(g.zaman) or simdi()
    email = eposta_duzelt(g.email)
    email = email if eposta_gecerli(email) else (email[: SINIR["email"]] or None)
    kaynak = g.kaynak if g.kaynak in KAYNAKLAR else kaynak_esle(g.tablo, g.kaynak_ham)
    mesaj = _kisa(g.mesaj, SINIR["metin"])
    butce = _kisa(g.butce, SINIR["butce"]) or butceyi_bul(mesaj)
    veri = {"kaynak": kaynak, "tablo": g.tablo, "kayit_id": g.kayit_id, "konu": _kisa(g.konu, 200), **g.ek_veri}

    mevcut = _acik_aday_sync(c, email) if email else None
    if mevcut:
        if g.tablo and g.kayit_id is not None:
            c.execute(bag.insert().values(aday_id=mevcut, tablo=g.tablo, kayit_id=int(g.kayit_id), created_at=an))
        c.execute(akt.insert().values(
            aday_id=mevcut, tur="sistem", olay="talep_eklendi", veri=json.dumps(veri, ensure_ascii=False),
            metin=mesaj, yapan=g.yapan, zaman=an,
        ))
        # Eksik alanları yeni talepten tamamla (doluysa dokunma).
        satir = c.execute(select(adt).where(adt.c.id == mevcut)).mappings().first()
        tamamla: Dict[str, Any] = {"updated_at": simdi()}
        for alan, deger in (("telefon", _kisa(g.telefon, SINIR["telefon"])), ("firma", _kisa(g.firma, SINIR["firma"])),
                            ("butce", butce), ("ilk_mesaj", mesaj)):
            if deger and not (satir or {}).get(alan):
                tamamla[alan] = deger
        if g.etiketler:
            eski_etiketler = json_liste((satir or {}).get("etiketler"))
            birlesik = eski_etiketler + [e for e in g.etiketler if e not in eski_etiketler]
            if birlesik != eski_etiketler:
                tamamla["etiketler"] = json.dumps(birlesik[: SINIR["etiket_sayisi"]], ensure_ascii=False)
        if g.deger_tahmini and not (satir or {}).get("deger_tahmini"):
            tamamla["deger_tahmini"] = float(g.deger_tahmini)
            tamamla["para_birimi"] = g.para_birimi or "USD"
        c.execute(update(adt).where(adt.c.id == mevcut).values(**tamamla))
        puani_yenile_sync(c, mevcut)
        return {"aday_id": mevcut, "yeni": False}

    liste = _asamalar_sync(c)
    hedef = next((a for a in liste if a["anahtar"] == g.asama), None) or ilk_asama(liste) or (liste[0] if liste else None)
    asama = hedef["anahtar"] if hedef else "yeni"
    ad = _kisa(g.ad, SINIR["ad"]) or (email.split("@")[0] if email else None) or "—"
    puan, ayrinti = puan_hesapla(
        kaynak=kaynak, email=email, deger_tahmini=g.deger_tahmini, butce=butce, ilk_mesaj=mesaj, etkilesim=0
    )
    sonuc = c.execute(
        _aday_ekleme_sorgusu().values(
            ad=ad, firma=_kisa(g.firma, SINIR["firma"]), email=email, telefon=_kisa(g.telefon, SINIR["telefon"]),
            kaynak=kaynak, kaynak_detay=_kisa(g.kaynak_ham, SINIR["kaynak_detay"]), kaynak_tablo=g.tablo,
            kaynak_id=g.kayit_id, asama=asama, deger_tahmini=float(g.deger_tahmini) if g.deger_tahmini else None,
            para_birimi=(g.para_birimi or ("USD" if g.deger_tahmini else "TRY")),
            olasilik=hedef.get("olasilik") if hedef else None,
            etiketler=json.dumps(g.etiketler or [], ensure_ascii=False), ilk_mesaj=mesaj, butce=butce,
            puan=puan, puan_ayrinti=json.dumps(ayrinti), bildirim_bekliyor=bool(g.bildirim),
            created_at=an, updated_at=an, asama_degisme_at=an,
        )
    )
    aday_id = int(sonuc.inserted_primary_key[0])
    if g.zaman is None:  # Faz 4A: webhook `aday.olusturuldu` (canlı kayıt; geçmiş içe aktarma değil). Hata fırlatmaz.
        from services.webhook import aday_verisi, olay_yaz_sync
        olay_yaz_sync(c, "aday.olusturuldu", None, aday_verisi(aday_id, kaynak, asama, g.deger_tahmini, g.para_birimi or ("USD" if g.deger_tahmini else "TRY")), musteri_gorur=False)
    if g.tablo and g.kayit_id is not None:
        c.execute(bag.insert().values(aday_id=aday_id, tablo=g.tablo, kayit_id=int(g.kayit_id), created_at=an))
    c.execute(akt.insert().values(
        aday_id=aday_id, tur="sistem", olay="aday_olustu", veri=json.dumps(veri, ensure_ascii=False),
        metin=mesaj, yapan=g.yapan, zaman=an,
    ))
    return {"aday_id": aday_id, "yeni": True}


async def kayit_isle(db: AsyncSession, girdi: TalepGirdisi) -> Optional[Dict[str, Any]]:
    """Async bağlam (form ucu, içe aktarma): aynı işlemde çalışır; commit çağırana kalır."""
    return await db.run_sync(lambda s: kayittan_aday_sync(s.connection(), girdi))


# --- Kaynak kayıt → girdi -----------------------------------------------------
def _alan(obj: Any, ad: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(ad)
    return getattr(obj, ad, None)


def talepten_girdi(obj: Any, **ek: Any) -> Optional[TalepGirdisi]:
    """`inquiries` satırı (ORM nesnesi ya da sözlük) → girdi."""
    kimlik = _alan(obj, "id")
    if kimlik is None:
        return None
    mesaj = _alan(obj, "message") or ""
    return TalepGirdisi(
        tablo="inquiries", kayit_id=int(kimlik), ad=_alan(obj, "name"), email=_alan(obj, "email"),
        telefon=_alan(obj, "phone"), konu=_alan(obj, "subject"), mesaj=mesaj, kaynak_ham=_alan(obj, "source"),
        zaman=_alan(obj, "created_at"), bildirim=False, **ek,
    )


def tekliften_girdi(obj: Any, **ek: Any) -> Optional[TalepGirdisi]:
    """`pricing_inquiries` satırı → girdi (tutar = tahmini değer, USD)."""
    kimlik = _alan(obj, "id")
    if kimlik is None:
        return None
    parcalar = [p for p in (_alan(obj, "scale_kod"), _alan(obj, "profile_kod"), _alan(obj, "period")) if p]
    ai_pm = _alan(obj, "ai_pm_tier_kod")
    eklentiler = json_liste(_alan(obj, "addon_ids"))
    satirlar = [" / ".join(parcalar) or "—"]
    if ai_pm:
        satirlar.append(f"AI vs PM: {ai_pm}")
    if eklentiler:
        satirlar.append("+ " + ", ".join(str(e) for e in eklentiler))
    tutar = _alan(obj, "hesaplanan_tutar")
    if tutar is not None:
        satirlar.append(f"{float(tutar):.2f} USD")
    return TalepGirdisi(
        tablo="pricing_inquiries", kayit_id=int(kimlik), ad=_alan(obj, "musteri_adi"),
        email=_alan(obj, "musteri_eposta"), konu=" / ".join(parcalar) or (ai_pm or ""),
        mesaj="\n".join(satirlar), kaynak_ham=_alan(obj, "kaynak") or "website", kaynak="fiyat_teklifi",
        deger_tahmini=float(tutar) if tutar else None, para_birimi="USD",
        butce=f"{float(tutar):.2f} USD" if tutar else None, zaman=_alan(obj, "created_at"), bildirim=True, **ek,
    )


# ---------------------------------------------------------------------------
# Flush kancası
# ---------------------------------------------------------------------------
KANCA_TABLOLARI = {"inquiries": talepten_girdi, "pricing_inquiries": tekliften_girdi}


def _tablo_adi(obj: Any) -> str:
    return getattr(type(obj), "__tablename__", "") or ""


@event.listens_for(Session, "after_flush")
def _crm_flush_sonrasi(session: Session, _flush_baglami) -> None:
    """Yeni talep/teklif → aday. Hata asıl kaydı bozmaz (SAVEPOINT)."""
    if session.info.get("crm_kanca_kapali"):
        return
    try:
        yeniler = [o for o in session.new if _tablo_adi(o) in KANCA_TABLOLARI]
    except Exception:  # noqa: BLE001
        return
    for obj in yeniler:
        try:
            girdi = KANCA_TABLOLARI[_tablo_adi(obj)](obj)
            if girdi is None:
                continue
            girdi.zaman = None  # canlı kayıt: şimdi
            baglanti = session.connection()
            with baglanti.begin_nested():
                kayittan_aday_sync(baglanti, girdi)
        except Exception:  # noqa: BLE001 - CRM asıl talebi ASLA bozmamalı
            logger.exception("CRM: talepten aday oluşturulamadı (%s)", _tablo_adi(obj))


# ---------------------------------------------------------------------------
# Geçmiş talepleri içe aktar (idempotent)
# ---------------------------------------------------------------------------
ICE_AKTARMA_SINIRI = 5000


async def gecmisi_ice_aktar(db: AsyncSession, yapan: Optional[str]) -> Dict[str, int]:
    """Henüz CRM'e işlenmemiş bütün `inquiries` ve `pricing_inquiries` kayıtları.

    Eskiden yeniye işleniyor (ilk talep adayı açıyor, sonrakiler aynı e-postada
    ona ekleniyor). Bildirim gönderilmiyor. İkinci çağrı hiçbir şey eklemez.
    """
    from models.inquiries import Inquiries
    from models.pricing import Pricing_inquiries

    await asamalari_hazirla(db)
    bag = CrmBagliKayitlar
    islenen_t = set((await db.execute(select(bag.kayit_id).where(bag.tablo == "inquiries"))).scalars().all())
    islenen_f = set((await db.execute(select(bag.kayit_id).where(bag.tablo == "pricing_inquiries"))).scalars().all())

    talepler = (await db.execute(select(Inquiries).order_by(Inquiries.id))).scalars().all()
    teklifler = (await db.execute(select(Pricing_inquiries).order_by(Pricing_inquiries.id))).scalars().all()
    girdiler: List[TalepGirdisi] = []
    ek = {"ek_veri": {"ice_aktarma": True}, "yapan": eposta_duzelt(yapan) or "sistem"}
    for t in talepler:
        if t.id not in islenen_t:
            g = talepten_girdi(t, **ek)
            if g:
                girdiler.append(g)
    for f in teklifler:
        if f.id not in islenen_f:
            g = tekliften_girdi(f, **ek)
            if g:
                g.bildirim = False
                girdiler.append(g)
    girdiler.sort(key=lambda g: (utc(g.zaman) or simdi(), g.tablo or "", g.kayit_id or 0))
    sayac = {"olusturulan": 0, "eklenen": 0, "atlanan": 0, "kalan": max(0, len(girdiler) - ICE_AKTARMA_SINIRI)}
    for g in girdiler[:ICE_AKTARMA_SINIRI]:
        sonuc = await kayit_isle(db, g)
        if sonuc is None:
            sayac["atlanan"] += 1
        elif sonuc["yeni"]:
            sayac["olusturulan"] += 1
        else:
            sayac["eklenen"] += 1
    await db.commit()
    return sayac


# ---------------------------------------------------------------------------
# Aşama taşıma
# ---------------------------------------------------------------------------
async def asama_tasi(
    db: AsyncSession,
    aday: CrmAdaylari,
    hedef: CrmAsamalari,
    *,
    yapan: str,
    kaybedilme_nedeni: Optional[str] = None,
    sebep: Optional[str] = None,
) -> bool:
    """Adayı `hedef` aşamaya taşır (aktivite + asama_degisme_at). Değiştiyse True. Commit çağırana."""
    if aday.asama == hedef.anahtar:
        if kaybedilme_nedeni is not None and hedef.tur == "kaybedildi":
            aday.kaybedilme_nedeni = kaybedilme_nedeni or None
        return False
    eski = aday.asama
    an = simdi()
    aday.asama = hedef.anahtar
    aday.asama_degisme_at = an
    if hedef.olasilik is not None:
        aday.olasilik = hedef.olasilik
    if hedef.tur == "kaybedildi" and kaybedilme_nedeni is not None:
        aday.kaybedilme_nedeni = kaybedilme_nedeni or None
    veri: Dict[str, Any] = {"eski": eski, "yeni": hedef.anahtar}
    if sebep:
        veri["sebep"] = sebep
    db.add(CrmAktiviteler(
        aday_id=aday.id, tur="asama", olay="asama_degisti", veri=json.dumps(veri, ensure_ascii=False),
        metin=(kaybedilme_nedeni or None) if hedef.tur == "kaybedildi" else None, yapan=yapan, zaman=an,
    ))
    return True


# ---------------------------------------------------------------------------
# Özet (huni, kaynaklar, aşama süreleri, bu ay kazanılan)
# ---------------------------------------------------------------------------
async def ozet(db: AsyncSession) -> Dict[str, Any]:
    liste = await asamalar(db)
    tur_haritasi = {a.anahtar: a.tur for a in liste}
    huni_asamalari = [a for a in liste if a.tur != "kaybedildi"]
    huni_indeksi = {a.anahtar: i for i, a in enumerate(huni_asamalari)}

    adaylar = (await db.execute(select(CrmAdaylari))).scalars().all()
    asama_aktiviteleri = (
        await db.execute(
            select(CrmAktiviteler).where(CrmAktiviteler.tur == "asama").order_by(CrmAktiviteler.aday_id, CrmAktiviteler.zaman, CrmAktiviteler.id)
        )
    ).scalars().all()
    gecisler: Dict[int, List[CrmAktiviteler]] = {}
    for k in asama_aktiviteleri:
        gecisler.setdefault(k.aday_id, []).append(k)

    # --- Huni: her aday ulaştığı en ileri (kaybedildi dışı) aşamaya kadar sayılıyor.
    ulasan = [0] * len(huni_asamalari)
    sure_toplam: Dict[str, float] = {}
    sure_sayi: Dict[str, int] = {}
    for a in adaylar:
        gecis = gecisler.get(a.id, [])
        ilk = json_sozluk(gecis[0].veri).get("eski") if gecis else a.asama
        gorulen = [ilk] + [json_sozluk(k.veri).get("yeni") for k in gecis]
        en_ileri = max((huni_indeksi[s] for s in gorulen if s in huni_indeksi), default=-1)
        for i in range(en_ileri + 1):
            ulasan[i] += 1
        # Aşama süresi: girişten çıkışa (tamamlanmış kalışlar).
        giris = utc(a.created_at)
        bulundugu = ilk
        for k in gecis:
            veri = json_sozluk(k.veri)
            cikis = utc(k.zaman)
            if giris and cikis and bulundugu:
                sure_toplam[bulundugu] = sure_toplam.get(bulundugu, 0.0) + max(0.0, (cikis - giris).total_seconds())
                sure_sayi[bulundugu] = sure_sayi.get(bulundugu, 0) + 1
            bulundugu, giris = veri.get("yeni"), cikis

    huni = []
    for i, a in enumerate(huni_asamalari):
        sonraki = ulasan[i + 1] if i + 1 < len(huni_asamalari) else None
        simdiki = [x for x in adaylar if x.asama == a.anahtar]
        huni.append({
            "anahtar": a.anahtar, "ulasan": ulasan[i], "simdi": len(simdiki),
            "donusum": (round(sonraki / ulasan[i], 4) if sonraki is not None and ulasan[i] else None),
        })

    # --- Kaynaklar
    kaynaklar: Dict[str, Dict[str, int]] = {}
    for a in adaylar:
        k = kaynaklar.setdefault(a.kaynak or "manuel", {"sayi": 0, "kazanilan": 0, "kaybedilen": 0})
        k["sayi"] += 1
        tur = tur_haritasi.get(a.asama)
        if tur == "kazanildi":
            k["kazanilan"] += 1
        elif tur == "kaybedildi":
            k["kaybedilen"] += 1
    kaynak_listesi = [
        {"kaynak": ad, **v, "kazanma_orani": round(v["kazanilan"] / v["sayi"], 4) if v["sayi"] else 0.0}
        for ad, v in sorted(kaynaklar.items(), key=lambda x: (-x[1]["sayi"], x[0]))
    ]

    # --- Bu ay kazanılan değer (Türkiye saatine göre ay)
    gun = bugun()
    ay_basi = gun.replace(day=1)
    kazanilan: Dict[str, float] = {}
    kazanilan_sayi = 0
    for a in adaylar:
        if tur_haritasi.get(a.asama) != "kazanildi":
            continue
        yerel = yerel_gun(a.asama_degisme_at)
        if yerel is not None and yerel >= ay_basi:
            kazanilan_sayi += 1
            if a.deger_tahmini:
                kazanilan[a.para_birimi or "TRY"] = round(kazanilan.get(a.para_birimi or "TRY", 0.0) + float(a.deger_tahmini), 2)

    acik_deger: Dict[str, float] = {}
    for a in adaylar:
        if tur_haritasi.get(a.asama, "acik") == "acik" and a.deger_tahmini:
            acik_deger[a.para_birimi or "TRY"] = round(acik_deger.get(a.para_birimi or "TRY", 0.0) + float(a.deger_tahmini), 2)

    return {
        "toplam": len(adaylar),
        "acik": sum(1 for a in adaylar if tur_haritasi.get(a.asama, "acik") == "acik"),
        "kazanilan": sum(1 for a in adaylar if tur_haritasi.get(a.asama) == "kazanildi"),
        "kaybedilen": sum(1 for a in adaylar if tur_haritasi.get(a.asama) == "kaybedildi"),
        "huni": huni,
        "kaynaklar": kaynak_listesi,
        "asama_sureleri": [
            {"anahtar": a.anahtar, "ortalama_gun": round(sure_toplam[a.anahtar] / sure_sayi[a.anahtar] / 86400, 2),
             "ornek": sure_sayi[a.anahtar]}
            for a in liste if sure_sayi.get(a.anahtar)
        ],
        "bu_ay": {"kazanilan_sayi": kazanilan_sayi, "deger": kazanilan, "ay": ay_basi.isoformat()},
        "acik_deger": acik_deger,
        "geciken": sum(
            1 for a in adaylar
            if tur_haritasi.get(a.asama, "acik") == "acik" and a.sonraki_adim_tarihi and a.sonraki_adim_tarihi < gun
        ),
    }


# ---------------------------------------------------------------------------
# Bildirimler (zamanlı görevler)
# ---------------------------------------------------------------------------
def _panel_baglantisi(aday_id: Optional[int] = None) -> str:
    return f"/admin?sekme=crm&aday={aday_id}" if aday_id else "/admin?sekme=crm"


async def _alicilar(db: AsyncSession, sorumlu: Optional[str]) -> List[Dict[str, Any]]:
    from services.notify import admin_recipients

    alicilar = list(await admin_recipients(db))
    s = eposta_duzelt(sorumlu)
    if s and s not in {eposta_duzelt(a.get("email")) for a in alicilar}:
        alicilar.append({"email": s, "role": "admin"})
    return alicilar


KAYNAK_ADI_TR = {
    "iletisim": "iletişim formu", "bekleme": "bekleme listesi", "site_analizi": "site analizi",
    "kesif": "keşif sihirbazı", "fiyat_teklifi": "fiyat teklifi", "kaynaklar": "Kaynaklar sayfası",
    "form": "gömülü form", "manuel": "elle", "eposta": "e-posta",
}


async def yeni_aday_bildir(db: AsyncSession, aday: CrmAdaylari, yeni: bool = True, form_adi: Optional[str] = None) -> None:
    """`crm_yeni_aday` — hata fırlatmaz."""
    from services.notify import dispatch, render

    try:
        kaynak = KAYNAK_ADI_TR.get(aday.kaynak, aday.kaynak)
        if form_adi:
            kaynak = f"{kaynak}: {form_adi}"
        varsayilan_baslik = (
            f"Yeni aday: {aday.ad} ({kaynak}, puan {aday.puan})" if yeni
            else f"Adaydan yeni gönderim: {aday.ad} ({kaynak})"
        )
        govde = (
            f"Ad: {aday.ad}\nFirma: {aday.firma or '—'}\nE-posta: {aday.email or '—'}\n"
            f"Telefon: {aday.telefon or '—'}\nKaynak: {kaynak}\nPuan: {aday.puan}/100\n\n{(aday.ilk_mesaj or '')[:1500]}"
        )
        baslik, metin = await render(
            db, "crm_yeni_aday", varsayilan_baslik, govde,
            {"ad": aday.ad, "firma": aday.firma or "", "eposta": aday.email or "", "kaynak": kaynak, "puan": aday.puan},
        )
        await dispatch(
            db, event_type="crm_yeni_aday", title=baslik, body=metin,
            recipients=await _alicilar(db, aday.sorumlu), link=_panel_baglantisi(aday.id),
            ref_type="crm_aday", ref_id=aday.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("CRM yeni aday bildirimi gönderilemedi")


async def bekleyen_bildirimleri_gonder(db: AsyncSession) -> Dict[str, Any]:
    """Zamanlı (her tur): kendi bildirimi olmayan kaynaktan açılan yeni adaylar."""
    adaylar = (
        await db.execute(
            select(CrmAdaylari).where(CrmAdaylari.bildirim_bekliyor.is_(True)).order_by(CrmAdaylari.id).limit(50)
        )
    ).scalars().all()
    for a in adaylar:
        a.bildirim_bekliyor = False
    await db.commit()
    for a in adaylar:
        await yeni_aday_bildir(db, a, yeni=True)
    return {"gonderilen": len(adaylar)}


async def hatirlatmalari_gonder(db: AsyncSession) -> Dict[str, Any]:
    """Zamanlı (günde bir): sonraki adım tarihi gelmiş açık adaylar — alıcı başına tek özet.

    Aday başına `hatirlatma_tarihi` = bugün yazılıyor; aynı gün ikinci tur
    (ya da "Şimdi çalıştır") aynı adayı yeniden göndermiyor.
    """
    from services.notify import admin_recipients, dispatch, render

    gun = bugun()
    acik = [a.anahtar for a in await asamalar(db) if a.tur == "acik"]
    adaylar = (
        await db.execute(
            select(CrmAdaylari)
            .where(
                CrmAdaylari.sonraki_adim_tarihi.is_not(None),
                CrmAdaylari.sonraki_adim_tarihi <= gun,
                CrmAdaylari.asama.in_(acik),
                or_(CrmAdaylari.hatirlatma_tarihi.is_(None), CrmAdaylari.hatirlatma_tarihi < gun),
            )
            .order_by(CrmAdaylari.sonraki_adim_tarihi, CrmAdaylari.id)
        )
    ).scalars().all()
    if not adaylar:
        return {"aday": 0, "alici": 0}

    yoneticiler = await admin_recipients(db)
    gruplar: Dict[str, Tuple[Dict[str, Any], List[CrmAdaylari]]] = {}
    for a in adaylar:
        s = eposta_duzelt(a.sorumlu)
        hedefler = [{"email": s, "role": "admin"}] if s else yoneticiler
        for h in hedefler:
            anahtar = eposta_duzelt(h.get("email"))
            if not anahtar:
                continue
            gruplar.setdefault(anahtar, (h, []))[1].append(a)
        a.hatirlatma_tarihi = gun
    await db.commit()

    for alici, liste in gruplar.values():
        satirlar = []
        for a in liste:
            gecikme = (gun - a.sonraki_adim_tarihi).days if a.sonraki_adim_tarihi else 0
            ek = f" (gecikme: {gecikme} gün)" if gecikme > 0 else ""
            satirlar.append(f"- {a.ad}{' / ' + a.firma if a.firma else ''}: {a.sonraki_adim or '—'} — {iso(a.sonraki_adim_tarihi)}{ek}")
        try:
            baslik, metin = await render(
                db, "crm_hatirlatma", f"CRM: {len(liste)} adayın sonraki adımı bugün",
                "Sonraki adım tarihi gelen adaylar:\n\n" + "\n".join(satirlar),
                {"sayi": len(liste), "liste": "\n".join(satirlar)},
            )
            await dispatch(
                db, event_type="crm_hatirlatma", title=baslik, body=metin, recipients=[alici],
                link=_panel_baglantisi(liste[0].id if len(liste) == 1 else None), ref_type="crm_aday",
                ref_id=liste[0].id if len(liste) == 1 else None,
            )
        except Exception:  # noqa: BLE001
            logger.exception("CRM hatırlatması gönderilemedi: %s", alici.get("email"))
    return {"aday": len(adaylar), "alici": len(gruplar)}


__all__ = [
    "KAYNAKLAR", "AKTIVITE_TURLERI", "ELLE_AKTIVITE_TURLERI", "ASAMA_TURLERI", "RENKLER", "PARA_BIRIMLERI",
    "TalepGirdisi", "kayittan_aday_sync", "kayit_isle", "puan_hesapla", "kaynak_esle", "alan_adi_turu",
    "gecmisi_ice_aktar", "asama_tasi", "ozet", "hatirlatmalari_gonder", "bekleyen_bildirimleri_gonder",
]
