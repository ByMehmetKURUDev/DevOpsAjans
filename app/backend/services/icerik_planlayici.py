"""Faz 5I — İçerik stüdyosu › sosyal medya planlayıcı (mevcut `content_posts` üzerinde).

Mevcut içerik takvimiyle ilişki
-------------------------------
İkinci bir gönderi sistemi KURULMADI: Faz 3'ün içerik takvimi tablosu
(`content_posts`) genişletildi ve yönetici panelindeki "İçerik" sekmesi artık
İçerik stüdyosu. Eski satırlar ilk kullanımda düzeltiliyor (`eski_kayitlari_duzelt`):
İngilizce durum → Türkçe, `channel` → `kanallar`. Eski genel varlık uçları
(`/api/v1/entities/content_posts`, yalnız yönetici) ve elle hatırlatma ucu
(`/api/v1/content-reminder`) çalışmaya devam ediyor.

Kim yönetir?
------------
* **Ajans müşteri için içerik yönetir** (`yoneten = ajans`): yönetici panelinde
  hesap seçilir; gönderi müşterinin hesabına yazılır ama müşteri onu yalnız
  onaya sunulunca görür (salt okunur) ve onaylar / revizyon ister — müşterinin
  İçerik stüdyosu modülü KAPALI olsa da (onay ekranı modülden bağımsız).
* **Müşteri kendi içeriğini yönetir** (`yoneten = musteri`): modül açık + ekip
  izni `icerik`; müşteri onayı adımı yok (kendi ekibi içinde "incelemede").

Durum akışı
-----------
taslak → incelemede → müşteri onayı bekliyor → onaylandı → yayınlandı (elle) /
reddedildi (gerekçe zorunlu). Müşteri onayına YALNIZ `onaya_gonder` ile girilir
(imzalı bağlantı, Faz 1E `signed_actions`, tür `icerik_onay`); çıkış yalnız
müşterinin kararıyla (onay → onaylandı, revizyon → taslak + not) ya da ajansın
geri çekmesiyle (→ taslak, bağlantı iptal). İçerik onaya sunulmuş/onaylanmışken
düzenlenemez (önce geri al); tarih her zaman (yayınlanmadıysa) değişebilir.

Zaman
-----
`scheduled_at` YEREL duvar saati + `saat_dilimi` (boşsa Europe/Istanbul): tek
kaynak. Takvim sorgusu SQL'de geniş aralıkla (±1 gün) daraltıp Python'da kesin
UTC karşılaştırması yapıyor; dönen `gun` istenen saat diliminde.

Hatırlatma (tek kez)
--------------------
Zamanlı uç (`services/zamanli.py` › `icerik_studyosu`) planlanan saatten 30 dk
önce sorumluya (yoksa hesaba / yöneticilere) "Paylaşıma hazır" bildirimi
gönderiyor. `hatirlatma_at` KOŞULLU UPDATE ile işaretleniyor (… WHERE
hatirlatma_at IS NULL): aynı gönderi iki kez hatırlatılmıyor; tarih değişince
sıfırlanıyor. Planlanan saat gelince onaylı gönderi için `icerik.yayin_zamani`
olayı (webhook + otomasyon) — yine tek kez.
"""

import csv
import io
import json
import logging
import os
import re
import secrets
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models.content_posts import Content_posts
from models.icerik_studyosu import IcerikGorselleri
from services import icerik_studyosu as st
from services.icerik_studyosu import StudyoHatasi
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DURUMLAR: Tuple[str, ...] = ("taslak", "incelemede", "musteri_onayi", "onaylandi", "yayinlandi", "reddedildi")
ESKI_DURUMLAR = {"draft": "taslak", "approved": "onaylandi", "published": "yayinlandi", "done": "yayinlandi"}
#: `/durum` ucuyla yapılabilen geçişler (müşteri onayına giriş/çıkış ayrı yollardan).
GECISLER: Dict[str, Tuple[str, ...]] = {
    "taslak": ("incelemede", "onaylandi", "reddedildi"),
    "incelemede": ("taslak", "onaylandi", "reddedildi"),
    "musteri_onayi": ("taslak",),
    "onaylandi": ("yayinlandi", "taslak"),
    "yayinlandi": ("onaylandi",),
    "reddedildi": ("taslak",),
}
NOT_ZORUNLU = frozenset({"reddedildi"})
#: İçeriğin kilitli olduğu durumlar (metin/kanal/görsel değişmez; önce "taslak"a geri alınır).
ICERIK_KILITLI = frozenset({"musteri_onayi", "onaylandi", "yayinlandi"})
#: Müşterinin, ajansın yönettiği gönderiyi görebildiği durumlar.
MUSTERI_GORUR = ("musteri_onayi", "onaylandi", "yayinlandi")
#: Hatırlatma/olay için "henüz paylaşılmadı" sayılan durumlar.
ACIK_DURUMLAR = ("taslak", "incelemede", "musteri_onayi", "onaylandi")

VARSAYILAN_SAAT_DILIMI = "Europe/Istanbul"
HATIRLATMA_ONCE = timedelta(minutes=30)
HATIRLATMA_GEC = timedelta(minutes=15)
YAYIN_OLAYI_GEC = timedelta(hours=6)
LISTE_SINIRI = 1000
GORSEL_SINIRI = 10
GORSEL_EN_COK_BAYT = 10 * 1024 * 1024
GORSEL_KENAR = 2160
HESAP_GORSEL_SINIRI = 500
ONAY_GUNU = 7
URL_SINIRI = 2000
_EPOSTA = re.compile(r"^[^@\s<>,;]{1,64}@[^@\s<>,;]{1,253}\.[^@\s<>,;]{2,}$")


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def gorsel_adresi(anahtar: str) -> str:
    return f"{site_adresi()}/api/v1/icerik-gorsel/{anahtar}"


def onay_adresi(jeton: str) -> str:
    return f"{site_adresi()}/icerik-onay/{jeton}"


# ---------------------------------------------------------------------------
# Saat dilimi
# ---------------------------------------------------------------------------
def tz_coz(ad: Optional[str]):
    ad = (ad or VARSAYILAN_SAAT_DILIMI).strip()
    if ad.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(ad)
    except Exception:  # noqa: BLE001
        if ad == VARSAYILAN_SAAT_DILIMI:
            return timezone(timedelta(hours=3))
        raise StudyoHatasi("saat_dilimi_gecersiz", alan="saat_dilimi")


def saat_dilimi_dogrula(ham: Any) -> str:
    ad = str(ham or "").strip() or VARSAYILAN_SAAT_DILIMI
    if len(ad) > 64 or not re.fullmatch(r"[A-Za-z0-9_+\-/]+", ad):
        raise StudyoHatasi("saat_dilimi_gecersiz", alan="saat_dilimi")
    tz_coz(ad)
    return ad


def yerelden_utc(yerel: Optional[datetime], ad: Optional[str]) -> Optional[datetime]:
    if yerel is None:
        return None
    if yerel.tzinfo is not None:
        return yerel.astimezone(timezone.utc)
    return yerel.replace(tzinfo=tz_coz(ad)).astimezone(timezone.utc)


def utcden_yerel(an: Optional[datetime], ad: Optional[str]) -> Optional[datetime]:
    if an is None:
        return None
    return st.utc(an).astimezone(tz_coz(ad)).replace(tzinfo=None)


def gonderi_utc(g: Content_posts) -> Optional[datetime]:
    try:
        return yerelden_utc(g.scheduled_at, g.saat_dilimi)
    except StudyoHatasi:
        return yerelden_utc(g.scheduled_at, VARSAYILAN_SAAT_DILIMI)


def zaman_coz(ham: Any, saat_dilimi: str) -> Optional[datetime]:
    """`YYYY-MM-DDTHH:MM` (saat diliminde yerel) ya da ofsetli ISO → saat diliminde YEREL (naive)."""
    if ham in (None, ""):
        return None
    if not isinstance(ham, str) or len(ham) > 40:
        raise StudyoHatasi("tarih_gecersiz", alan="planlanan")
    s = ham.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        an = datetime.fromisoformat(s)
    except ValueError:
        raise StudyoHatasi("tarih_gecersiz", alan="planlanan")
    if an.tzinfo is not None:
        an = an.astimezone(tz_coz(saat_dilimi)).replace(tzinfo=None)
    if not 2000 <= an.year <= 2100:
        raise StudyoHatasi("tarih_gecersiz", alan="planlanan")
    return an.replace(second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Eski kayıtlar (Faz 3 içerik takvimi) — bir kez
# ---------------------------------------------------------------------------
_duzeltildi: Dict[str, bool] = {"tamam": False}


async def eski_kayitlari_duzelt(db: AsyncSession, zorla: bool = False) -> int:
    """İngilizce/boş durum → Türkçe; `kanallar` boşsa `channel`dan. Süreç başına bir kez (ucuz)."""
    if _duzeltildi["tamam"] and not zorla:
        return 0
    toplam = 0
    try:
        for eski, yeni in ESKI_DURUMLAR.items():
            r = await db.execute(update(Content_posts).where(Content_posts.status == eski).values(status=yeni)
                                 .execution_options(synchronize_session=False))
            toplam += int(r.rowcount or 0)
        r = await db.execute(update(Content_posts).where(or_(Content_posts.status.is_(None), Content_posts.status == ""))
                             .values(status="taslak").execution_options(synchronize_session=False))
        toplam += int(r.rowcount or 0)
        satirlar = (await db.execute(select(Content_posts.id, Content_posts.channel).where(
            or_(Content_posts.kanallar.is_(None), Content_posts.kanallar == ""), Content_posts.channel.isnot(None)
        ).limit(2000))).all()
        for gid, kanal in satirlar:
            k = kanal if kanal in st.KANALLAR else None
            await db.execute(update(Content_posts).where(Content_posts.id == gid)
                             .values(kanallar=st.json_yaz([k] if k else [])).execution_options(synchronize_session=False))
            toplam += 1
        await db.commit()
        _duzeltildi["tamam"] = True
    except Exception:  # noqa: BLE001 - düzeltme stüdyoyu bozmasın
        logger.exception("Eski içerik kayıtları düzeltilemedi")
        await db.rollback()
    return toplam


# ---------------------------------------------------------------------------
# Görünürlük
# ---------------------------------------------------------------------------
def ajans_kosulu():
    return or_(Content_posts.hesap_email.is_(None), Content_posts.hesap_email == "")


def gorunurluk_kosulu(kapsam: st.Kapsam, hesap_filtresi: Optional[str] = None):
    """Yönetici: `hesap_filtresi` None = ajans, "*" = hepsi, e-posta = o hesap. Müşteri: kendi + onaya sunulanlar."""
    if kapsam.yonetici:
        if hesap_filtresi == "*":
            return None
        if not hesap_filtresi:
            return ajans_kosulu()
        return Content_posts.hesap_email == st.eposta_duzelt(hesap_filtresi)
    return and_(
        Content_posts.hesap_email == kapsam.hesap,
        or_(Content_posts.yoneten == "musteri", Content_posts.status.in_(MUSTERI_GORUR)),
    )


def musteri_yonetir_mi(g: Content_posts) -> bool:
    return (g.yoneten or "") == "musteri"


async def gonderi_bul(db: AsyncSession, gid: int, kapsam: st.Kapsam, *, yazma: bool = False) -> Content_posts:
    g = (await db.execute(select(Content_posts).where(Content_posts.id == gid))).scalars().first()
    if g is None:
        raise StudyoHatasi("bulunamadi", 404)
    if kapsam.yonetici:
        return g
    if st.eposta_duzelt(g.hesap_email) != kapsam.hesap:
        raise StudyoHatasi("bulunamadi", 404)
    if not musteri_yonetir_mi(g) and (g.status or "") not in MUSTERI_GORUR:
        raise StudyoHatasi("bulunamadi", 404)
    if yazma and not musteri_yonetir_mi(g):
        raise StudyoHatasi("salt_okunur", 403)
    return g


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
def _adres(ham: Any, alan: str) -> Optional[str]:
    s = st.metin(ham, alan, URL_SINIRI, tek_satir=True)
    if not s:
        return None
    parca = urlsplit(s)
    if parca.scheme not in ("http", "https") or not parca.netloc:
        raise StudyoHatasi("adres_gecersiz", alan=alan)
    return s


def _kanallar(ham: Any) -> List[str]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list):
        raise StudyoHatasi("gecersiz", alan="kanallar")
    sonuc = []
    for k in ham:
        if k not in st.KANALLAR:
            raise StudyoHatasi("gecersiz", alan="kanallar", deger=str(k)[:30])
        if k not in sonuc:
            sonuc.append(k)
    return sonuc


def _hashtag_metni(ham: Any) -> Optional[str]:
    s = st.metin(ham, "hashtagler", 1000, tek_satir=True)
    if not s:
        return None
    parcalar = []
    for p in re.split(r"[\s,]+", s):
        p = p.strip()
        if not p:
            continue
        p = "#" + p.lstrip("#")
        if not re.fullmatch(r"#[\wÀ-￿]+", p):
            raise StudyoHatasi("gecersiz", alan="hashtagler", deger=p[:40])
        if p not in parcalar:
            parcalar.append(p)
    return " ".join(parcalar) or None


async def _gorseller(db: AsyncSession, ham: Any, hesap: Optional[str]) -> List[Dict[str, Any]]:
    if ham in (None, ""):
        return []
    if not isinstance(ham, list) or len(ham) > GORSEL_SINIRI:
        raise StudyoHatasi("cok_fazla", alan="gorseller", sinir=GORSEL_SINIRI)
    anahtarlar = []
    for x in ham:
        a = x.get("anahtar") if isinstance(x, dict) else x
        if not isinstance(a, str) or not re.fullmatch(r"[A-Za-z0-9]{8,64}", a):
            raise StudyoHatasi("gecersiz", alan="gorseller")
        if a not in anahtarlar:
            anahtarlar.append(a)
    if not anahtarlar:
        return []
    kayitlar = {g.anahtar: g for g in (await db.execute(select(IcerikGorselleri).where(IcerikGorselleri.anahtar.in_(anahtarlar)))).scalars().all()}
    sonuc = []
    for a in anahtarlar:
        g = kayitlar.get(a)
        if g is None or st.eposta_duzelt(g.hesap_email) != st.eposta_duzelt(hesap):
            raise StudyoHatasi("gorsel_yok", 404, alan="gorseller")
        sonuc.append({"anahtar": a, "ad": g.ad or "", "tur": g.tur, "genislik": g.genislik, "yukseklik": g.yukseklik})
    return sonuc


ICERIK_ALANLARI = ("baslik", "metin", "kanallar", "kanal_metinleri", "hashtagler", "ilk_yorum", "gorseller",
                   "video_url", "baglanti", "marka_id")
ZAMAN_ALANLARI = ("planlanan", "saat_dilimi")


async def proje_dogrula(db: AsyncSession, deger: Any, hesap: Optional[str]) -> Optional[int]:
    """Faz 7K — gönderinin isteğe bağlı projesi: boş → None; yoksa gönderinin HESABININ projesi olmalı
    (`projects.client_email`). Ajansın kendi içeriğinde (hesap boş) her proje seçilebilir."""
    if deger in (None, "", 0):
        return None
    if isinstance(deger, bool) or not str(deger).strip().isdigit():
        raise StudyoHatasi("gecersiz", alan="proje_id")
    from models.projects import Projects

    p = (await db.execute(select(Projects.id, Projects.client_email).where(Projects.id == int(str(deger).strip())))).first()
    if p is None or (hesap and st.eposta_duzelt(p.client_email) != st.eposta_duzelt(hesap)):
        raise StudyoHatasi("proje_yok", 404, alan="proje_id")
    return int(p.id)


#: Kapanmış proje durumları (açık proje önerisinde sayılmaz; aylık rapor da "completed"ı kapalı sayıyor).
KAPALI_PROJE_DURUMLARI = ("completed", "cancelled", "tamamlandi", "iptal")


async def projeler(db: AsyncSession, hesap: Optional[str], tum: bool = False) -> List[Dict[str, Any]]:
    """Gönderiye bağlanabilecek projeler (en yeni önce): hesabın projeleri; `tum` (ajansın kendi içeriği) → hepsi.
    `acik`: proje kapanmamış (ön yüz, hesabın TEK açık projesi varsa onu öneriyor)."""
    from models.projects import Projects

    sorgu = select(Projects.id, Projects.title, Projects.client_email, Projects.status)
    if not tum:
        if not hesap:
            return []
        sorgu = sorgu.where(func.lower(Projects.client_email) == st.eposta_duzelt(hesap))
    satirlar = (await db.execute(sorgu.order_by(Projects.id.desc()).limit(300))).all()
    return [{"id": r.id, "baslik": r.title, "hesap": r.client_email or None,
             "acik": (r.status or "").strip().lower() not in KAPALI_PROJE_DURUMLARI} for r in satirlar]


async def gonderi_dogrula(db: AsyncSession, govde: Dict[str, Any], g: Optional[Content_posts], hesap: Optional[str]) -> Dict[str, Any]:
    """API alanları → sütun değerleri (yalnız gönderilenler; yeni kayıtta zorunlular)."""
    d: Dict[str, Any] = {}
    yeni = g is None
    if "baslik" in govde or yeni:
        d["title"] = st.metin(govde.get("baslik"), "baslik", 200, zorunlu=True, tek_satir=True)
    if "metin" in govde:
        d["body"] = st.metin(govde.get("metin"), "metin", st.SINIR["metin"]) or None
    kanallar = None
    if "kanallar" in govde or yeni:
        kanallar = _kanallar(govde.get("kanallar") if "kanallar" in govde else ["instagram"])
        if not kanallar:
            raise StudyoHatasi("metin_gerekli", alan="kanallar")
        d["kanallar"] = st.json_yaz(kanallar)
        d["channel"] = kanallar[0]
    if "kanal_metinleri" in govde:
        ham = govde.get("kanal_metinleri") or {}
        if not isinstance(ham, dict):
            raise StudyoHatasi("gecersiz", alan="kanal_metinleri")
        gecerli = kanallar if kanallar is not None else kanal_listesi(g) if g else []
        km = {}
        for k, v in ham.items():
            if k not in st.KANALLAR:
                raise StudyoHatasi("gecersiz", alan="kanal_metinleri", deger=str(k)[:30])
            s = st.metin(v, f"kanal_metinleri.{k}", st.SINIR["metin"])
            if s and k in gecerli:
                km[k] = s
        d["kanal_metinleri"] = st.json_yaz(km) if km else None
    if "hashtagler" in govde:
        d["hashtags"] = _hashtag_metni(govde.get("hashtagler"))
    if "ilk_yorum" in govde:
        d["ilk_yorum"] = st.metin(govde.get("ilk_yorum"), "ilk_yorum", 2200) or None
    if "gorseller" in govde:
        liste_ = await _gorseller(db, govde.get("gorseller"), hesap)
        d["gorseller"] = st.json_yaz(liste_) if liste_ else None
        d["image_url"] = gorsel_adresi(liste_[0]["anahtar"]) if liste_ else None
    if "video_url" in govde:
        d["video_url"] = _adres(govde.get("video_url"), "video_url")
    if "baglanti" in govde:
        yeni_baglanti = _adres(govde.get("baglanti"), "baglanti")
        d["link_url"] = yeni_baglanti
        if g is not None and yeni_baglanti != g.link_url:
            d["kisa_linkler"] = None  # eski kısa linkler başka adrese gidiyordu
    if "kampanya" in govde:
        d["campaign"] = st.metin(govde.get("kampanya"), "kampanya", 100, tek_satir=True) or None
    if "notlar" in govde:
        d["notes"] = st.metin(govde.get("notlar"), "notlar", 2000) or None
    if "marka_id" in govde:
        m = await st.marka_bul(db, govde.get("marka_id"), hesap)
        d["marka_id"] = m.id if m else None
    if "proje_id" in govde:
        d["proje_id"] = await proje_dogrula(db, govde.get("proje_id"), hesap)
    if "sorumlu_eposta" in govde:
        e = st.eposta_duzelt(govde.get("sorumlu_eposta"))
        if e and not _EPOSTA.match(e):
            raise StudyoHatasi("eposta_gecersiz", alan="sorumlu_eposta")
        d["sorumlu_eposta"] = e or None
    if "saat_dilimi" in govde or "planlanan" in govde or yeni:
        tz = saat_dilimi_dogrula(govde.get("saat_dilimi") if "saat_dilimi" in govde else (g.saat_dilimi if g else None))
        d["saat_dilimi"] = tz
        # Yalnız saat dilimi değişirse yerel saat aynı kalır (kullanıcı saati o dilimde girmiş sayılır).
        if "planlanan" in govde:
            d["scheduled_at"] = zaman_coz(govde.get("planlanan"), tz)
    return d


def degisen_alanlar(govde: Dict[str, Any]) -> Tuple[bool, bool]:
    return any(a in govde for a in ICERIK_ALANLARI), any(a in govde for a in ZAMAN_ALANLARI)


def duzenleme_denetle(g: Content_posts, govde: Dict[str, Any]) -> None:
    icerik, zaman = degisen_alanlar(govde)
    durum = g.status or "taslak"
    if icerik and durum in ICERIK_KILITLI:
        raise StudyoHatasi("duzenlenemez", 409, gonderi_durumu=durum)
    if zaman and durum == "yayinlandi":
        raise StudyoHatasi("duzenlenemez", 409, gonderi_durumu=durum)


def uygula(g: Content_posts, d: Dict[str, Any]) -> None:
    eski_zaman = (g.scheduled_at, g.saat_dilimi)
    for k, v in d.items():
        setattr(g, k, v)
    if (g.scheduled_at, g.saat_dilimi) != eski_zaman:
        # Yeni saat için hatırlatma ve yayın olayı yeniden.
        g.hatirlatma_at = None
        g.yayin_olayi_at = None


async def gonderi_siniri_denetle(db: AsyncSession, hesap: str) -> None:
    sinirlar = await st.hesap_sinirlari(db, hesap)
    sinir = sinirlar.get("aylik_gonderi")
    if sinir is None:
        return
    ay = st.simdi().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sayi = int((await db.execute(select(func.count(Content_posts.id)).where(
        Content_posts.hesap_email == hesap, Content_posts.yoneten == "musteri", Content_posts.created_at >= ay,
    ))).scalar() or 0)
    if sayi >= int(sinir):
        raise StudyoHatasi("gonderi_siniri", 409, sinir=int(sinir))


# ---------------------------------------------------------------------------
# Sözlük ve paylaşım metni
# ---------------------------------------------------------------------------
def kanal_listesi(g: Content_posts) -> List[str]:
    k = st.json_yukle(g.kanallar, [])
    if not k and g.channel in st.KANALLAR:
        k = [g.channel]
    return [x for x in k if x in st.KANALLAR]


def _utm_ekle(adres: str, kanal: str, kampanya: Optional[str], gid: int) -> str:
    parca = urlsplit(adres)
    ek = {"utm_source": kanal, "utm_medium": "email" if kanal == "email" else "social",
          "utm_campaign": kampanya_slug(kampanya) or f"icerik-{gid}"}
    sorgu = [(k, v) for k, v in parse_qsl(parca.query, keep_blank_values=True) if k not in ek]
    sorgu.extend(ek.items())
    return urlunsplit((parca.scheme, parca.netloc, parca.path, urlencode(sorgu), parca.fragment))


def kampanya_slug(k: Optional[str]) -> str:
    if not k:
        return ""
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = re.sub(r"[^a-z0-9]+", "-", k.translate(tablo).lower()).strip("-")
    return s[:60]


def kanal_baglantisi(g: Content_posts, kanal: str) -> Optional[str]:
    kisa = st.json_yukle(g.kisa_linkler, {}).get(kanal)
    if isinstance(kisa, dict) and kisa.get("adres"):
        return kisa["adres"]
    if g.link_url:
        return _utm_ekle(g.link_url, kanal, g.campaign, g.id)
    return None


def paylasim_metni(g: Content_posts, kanal: str) -> Tuple[str, Optional[str]]:
    """Kanalın paylaşılacak metni (kanal metni ya da ana metin + bağlantı + etiketler) ve ayrı bağlantı."""
    km = st.json_yukle(g.kanal_metinleri, {})
    govde = (km.get(kanal) or g.body or "").strip()
    baglanti = kanal_baglantisi(g, kanal)
    parcalar = [govde] if govde else []
    if baglanti and kanal not in st.BAGLANTI_AYRI and baglanti not in govde and (not g.link_url or g.link_url not in govde):
        parcalar.append(baglanti)
    if g.hashtags and kanal not in ("blog", "email", "google_isletme"):
        eksik = [h for h in g.hashtags.split() if h.lower() not in govde.lower()]
        if eksik:
            parcalar.append(" ".join(eksik))
    return "\n\n".join(parcalar), baglanti


def _gorsel_listesi(g: Content_posts) -> List[Dict[str, Any]]:
    return [{**x, "url": gorsel_adresi(x["anahtar"])} for x in st.json_yukle(g.gorseller, []) if isinstance(x, dict) and x.get("anahtar")]


def kanal_ozeti(g: Content_posts) -> List[Dict[str, Any]]:
    sonuc = []
    for k in kanal_listesi(g):
        m, baglanti = paylasim_metni(g, k)
        sonuc.append({
            "kanal": k, "metin": m, "baglanti": baglanti, "olcum": st.olc(m, k),
            "ilk_yorum": g.ilk_yorum if k in ("instagram", "linkedin", "facebook", "tiktok", "youtube_shorts") else None,
            "gorsel_onerisi": st.GORSEL_ONERILERI.get(k, []),
        })
    return sonuc


def _yerel_metin(an: Optional[datetime]) -> Optional[str]:
    return an.strftime("%Y-%m-%dT%H:%M") if an else None


def gonderi_sozlugu(g: Content_posts, *, onay: Optional[Dict[str, Any]] = None, gun_tz: Optional[str] = None,
                    marka_adi: Optional[str] = None) -> Dict[str, Any]:
    u = gonderi_utc(g)
    km = st.json_yukle(g.kanal_metinleri, {})
    kanallar = kanal_listesi(g)
    uyarilar = st.uyari_tara("\n".join([g.body or ""] + list(km.values())))
    d = {
        "id": g.id,
        "hesap_email": g.hesap_email or None,
        "yoneten": g.yoneten or "ajans",
        "baslik": g.title,
        "metin": g.body or "",
        "kanallar": kanallar,
        "kanal_metinleri": km,
        "hashtagler": g.hashtags or "",
        "ilk_yorum": g.ilk_yorum or "",
        "gorseller": _gorsel_listesi(g),
        "video_url": g.video_url or "",
        "baglanti": g.link_url or "",
        "kisa_linkler": st.json_yukle(g.kisa_linkler, {}),
        "kampanya": g.campaign or "",
        "notlar": g.notes or "",
        "marka_id": g.marka_id,
        "marka_adi": marka_adi,
        "proje_id": g.proje_id,
        "sorumlu_eposta": g.sorumlu_eposta or "",
        "olusturan_eposta": g.olusturan_eposta or "",
        "durum": g.status or "taslak",
        "durum_notu": g.durum_notu or "",
        "durum_at": st.iso(g.durum_at),
        "durum_degistiren": g.durum_degistiren or "",
        "gecisler": list(GECISLER.get(g.status or "taslak", ())),
        "saat_dilimi": g.saat_dilimi or VARSAYILAN_SAAT_DILIMI,
        "planlanan": _yerel_metin(g.scheduled_at),
        "planlanan_at": st.iso(u),
        "gun": (u.astimezone(tz_coz(gun_tz)).date().isoformat() if u and gun_tz else (g.scheduled_at.date().isoformat() if g.scheduled_at else None)),
        "onaylayan": g.onaylayan or "",
        "onay_at": st.iso(g.onay_at),
        "yayinlandi_at": st.iso(g.published_at),
        "hatirlatma_at": st.iso(g.hatirlatma_at),
        "uretim_id": g.uretim_id,
        "uyarilar": uyarilar,
        "olcumler": {k: st.olc(paylasim_metni(g, k)[0], k) for k in kanallar},
        "created_at": st.iso(g.created_at),
        "updated_at": st.iso(g.updated_at),
    }
    if onay is not None:
        d["onay"] = onay
    return d


def onizleme_sozlugu(g: Content_posts, marka_adi: Optional[str] = None) -> Dict[str, Any]:
    """Müşterinin onay ekranı (panel ve imzalı bağlantı): yalnız gösterilecek alanlar."""
    return {
        "id": g.id,
        "baslik": g.title,
        "kanallar": kanal_ozeti(g),
        "gorseller": [{"url": x["url"], "ad": x.get("ad") or "", "genislik": x.get("genislik"), "yukseklik": x.get("yukseklik")}
                      for x in _gorsel_listesi(g)],
        "video_url": g.video_url or "",
        "kampanya": g.campaign or "",
        "marka_adi": marka_adi,
        "saat_dilimi": g.saat_dilimi or VARSAYILAN_SAAT_DILIMI,
        "planlanan": _yerel_metin(g.scheduled_at),
        "planlanan_at": st.iso(gonderi_utc(g)),
        "durum": g.status or "taslak",
    }


async def marka_adlari(db: AsyncSession, idler: Sequence[Optional[int]]) -> Dict[int, str]:
    from models.icerik_studyosu import IcerikMarkalari

    idler = [i for i in set(idler) if i]
    if not idler:
        return {}
    return {m.id: m.ad for m in (await db.execute(select(IcerikMarkalari).where(IcerikMarkalari.id.in_(idler)))).scalars().all()}


async def onay_bilgileri(db: AsyncSession, gonderiler: Sequence[Content_posts]) -> Dict[int, Dict[str, Any]]:
    from models.signed_actions import SignedActions
    from services import imzali_islem

    idler = [g.onay_islem_id for g in gonderiler if g.onay_islem_id]
    if not idler:
        return {}
    sonuc = {}
    for k in (await db.execute(select(SignedActions).where(SignedActions.id.in_(idler)))).scalars().all():
        sonuc[k.id] = {"islem_id": k.id, "durum": imzali_islem.gecerli_durum(k), "son_kullanma": st.iso(k.son_kullanma),
                       "alici": k.alici_eposta, "created_at": st.iso(k.created_at)}
    return sonuc


# ---------------------------------------------------------------------------
# Takvim / liste sorgusu
# ---------------------------------------------------------------------------
def _tarih(ham: Any, alan: str) -> Optional[date]:
    if ham in (None, ""):
        return None
    try:
        return date.fromisoformat(str(ham)[:10])
    except ValueError:
        raise StudyoHatasi("tarih_gecersiz", alan=alan)


async def kayitlari_getir(
    db: AsyncSession,
    kapsam: st.Kapsam,
    *,
    hesap_filtresi: Optional[str] = None,
    bas: Any = None,
    bit: Any = None,
    tz: Any = None,
    kanal: Optional[str] = None,
    kampanya: Optional[str] = None,
    durum: Optional[str] = None,
    marka_id: Optional[int] = None,
    tarihsiz: bool = True,
) -> Tuple[List[Content_posts], str, bool]:
    """Görünür gönderiler (takvim aralığı istenen saat diliminde) → (kayıtlar, saat dilimi, sınırda mı)."""
    await eski_kayitlari_duzelt(db)
    tz_adi = saat_dilimi_dogrula(tz)
    b, e = _tarih(bas, "bas"), _tarih(bit, "bit")
    if b and e and e < b:
        raise StudyoHatasi("tarih_gecersiz", alan="bit")
    if b and e and (e - b).days > 92:
        raise StudyoHatasi("aralik_buyuk", alan="bit", sinir=92)
    sorgu = select(Content_posts)
    kosul = gorunurluk_kosulu(kapsam, hesap_filtresi)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    if durum:
        if durum not in DURUMLAR:
            raise StudyoHatasi("gecersiz", alan="durum")
        sorgu = sorgu.where(Content_posts.status == durum)
    if kampanya:
        sorgu = sorgu.where(Content_posts.campaign == kampanya)
    if marka_id:
        sorgu = sorgu.where(Content_posts.marka_id == int(marka_id))
    if kanal and kanal not in st.KANALLAR:
        raise StudyoHatasi("gecersiz", alan="kanal")
    aralik = None
    if b or e:
        tzo = tz_coz(tz_adi)
        bas_utc = datetime.combine(b or date(2000, 1, 1), datetime.min.time(), tzo).astimezone(timezone.utc)
        bit_utc = datetime.combine((e or date(2100, 1, 1)) + timedelta(days=1), datetime.min.time(), tzo).astimezone(timezone.utc)
        aralik = (bas_utc, bit_utc)
        # SQL'de geniş (±1 gün: her saat dilimi kapsanır), Python'da kesin.
        genis = [Content_posts.scheduled_at >= datetime.combine((b or date(2000, 1, 2)) - timedelta(days=1), datetime.min.time()),
                 Content_posts.scheduled_at < datetime.combine((e or date(2099, 12, 30)) + timedelta(days=2), datetime.min.time())]
        if tarihsiz:
            sorgu = sorgu.where(or_(and_(*genis), Content_posts.scheduled_at.is_(None)))
        else:
            sorgu = sorgu.where(*genis)
    elif not tarihsiz:
        sorgu = sorgu.where(Content_posts.scheduled_at.isnot(None))
    kayitlar = (await db.execute(sorgu.order_by(Content_posts.scheduled_at.asc(), Content_posts.id.asc()).limit(LISTE_SINIRI))).scalars().all()
    secilen = []
    for g in kayitlar:
        if kanal and kanal not in kanal_listesi(g):
            continue
        if aralik and g.scheduled_at is not None:
            u = gonderi_utc(g)
            if not (aralik[0] <= u < aralik[1]):
                continue
        secilen.append(g)
    return secilen, tz_adi, len(kayitlar) >= LISTE_SINIRI


async def liste(db: AsyncSession, kapsam: st.Kapsam, **filtreler: Any) -> Dict[str, Any]:
    secilen, tz_adi, sinirda = await kayitlari_getir(db, kapsam, **filtreler)
    onaylar = await onay_bilgileri(db, secilen) if kapsam.yonetici else {}
    markalar = await marka_adlari(db, [g.marka_id for g in secilen])
    kampanyalar = sorted({g.campaign for g in secilen if g.campaign})
    return {
        "items": [gonderi_sozlugu(g, onay=onaylar.get(g.onay_islem_id) if g.onay_islem_id else None, gun_tz=tz_adi,
                                  marka_adi=markalar.get(g.marka_id)) for g in secilen],
        "saat_dilimi": tz_adi,
        "kampanyalar": kampanyalar,
        "sinirda": sinirda,
    }


# ---------------------------------------------------------------------------
# Durum makinesi
# ---------------------------------------------------------------------------
async def onay_bagini_iptal_et(db: AsyncSession, g: Content_posts) -> None:
    """Bekleyen onay bağlantısı varsa iptal; gönderi nesnesi tazelenir (iptal geri almada bayatlar)."""
    from services import imzali_islem

    if not g.onay_islem_id:
        return
    try:
        await imzali_islem.iptal_et(db, g.onay_islem_id)
    except imzali_islem.IslemHatasi:
        pass  # süresi dolmuş / kullanılmış: iptal edilecek bir şey yok
    await db.refresh(g)


async def durum_degistir(db: AsyncSession, g: Content_posts, yeni: Any, not_: Any, kapsam: st.Kapsam) -> Content_posts:
    eski = g.status or "taslak"
    if yeni not in DURUMLAR:
        raise StudyoHatasi("gecersiz", alan="durum")
    if yeni == "musteri_onayi":
        raise StudyoHatasi("onaya_gonder_kullan", 400, alan="durum")
    if yeni not in GECISLER.get(eski, ()):
        raise StudyoHatasi("gecersiz_gecis", 409, eski=eski, yeni=yeni)
    temiz_not = st.metin(not_, "not", 2000) or None
    if yeni in NOT_ZORUNLU and not temiz_not:
        raise StudyoHatasi("not_gerekli", alan="not")
    an = st.simdi()
    if eski == "musteri_onayi" and g.onay_islem_id:
        # Ajans onay isteğini geri çekti: bekleyen bağlantı iptal.
        await onay_bagini_iptal_et(db, g)
        g.onay_islem_id = None
    g.status = yeni
    g.durum_at = an
    g.durum_degistiren = kapsam.kisi or None
    g.durum_notu = temiz_not if (temiz_not or yeni in ("reddedildi", "taslak")) else g.durum_notu
    if yeni == "onaylandi" and eski != "yayinlandi":
        g.onay_at = an
        g.onaylayan = kapsam.kisi or None
    if yeni == "yayinlandi":
        g.published_at = an.replace(tzinfo=None)
    if eski == "yayinlandi":
        g.published_at = None
    await db.commit()
    await db.refresh(g)
    return g


# ---------------------------------------------------------------------------
# Müşteri onayı (Faz 1E imzalı bağlantı, tür `icerik_onay`)
# ---------------------------------------------------------------------------
async def onaya_gonder(db: AsyncSession, g: Content_posts, kisi: str, gun: Any = None, eposta_gonder: bool = False) -> Dict[str, Any]:
    from services import imzali_islem

    if not g.hesap_email or musteri_yonetir_mi(g):
        raise StudyoHatasi("onay_icin_musteri_gerekli", 409)
    # "musteri_onayi"ndayken yeniden gönderim = bağlantıyı yenile (eskisi iptal; süresi dolmuş olabilir).
    if (g.status or "taslak") not in ("taslak", "incelemede", "reddedildi", "musteri_onayi"):
        raise StudyoHatasi("gecersiz_gecis", 409, eski=g.status, yeni="musteri_onayi")
    if not (g.body or st.json_yukle(g.kanal_metinleri, {})):
        raise StudyoHatasi("metin_gerekli", alan="metin")
    if not kanal_listesi(g):
        raise StudyoHatasi("metin_gerekli", alan="kanallar")
    try:
        gun_ = imzali_islem.gun_duzelt(gun if gun not in (None, "") else ONAY_GUNU)
    except imzali_islem.IslemHatasi:
        raise StudyoHatasi("gecersiz", alan="gun")
    await onay_bagini_iptal_et(db, g)
    u = gonderi_utc(g)
    try:
        jeton, kayit = await imzali_islem.olustur(
            db, "icerik_onay", ("content_posts", g.id), g.hesap_email, g.title,
            {"gonderi_id": g.id, "kanallar": kanal_listesi(g), "planlanan_at": st.iso(u)}, gun_, olusturan=kisi,
        )
    except imzali_islem.IslemHatasi as h:
        raise StudyoHatasi(h.kod, h.durum)
    an = st.simdi()
    g.status = "musteri_onayi"
    g.onay_islem_id = kayit.id
    g.durum_at = an
    g.durum_degistiren = kisi or None
    g.durum_notu = None
    await db.commit()
    await db.refresh(g)
    baglanti = onay_adresi(jeton)
    gitti = await _onay_epostasi(db, g, kayit, baglanti) if eposta_gonder else False
    return {"baglanti": baglanti, "eposta_gonderildi": gitti, "son_kullanma": st.iso(kayit.son_kullanma), "islem_id": kayit.id}


async def _onay_epostasi(db: AsyncSession, g: Content_posts, kayit: Any, baglanti: str) -> bool:
    """Bağlantı müşteriye `dispatch` ile; ham jeton kalıcı kayıtta bırakılmaz (imzalı işlem deseni)."""
    from services.notify import dispatch, render

    zaman = gonderi_utc(g)
    yerel = g.scheduled_at.strftime("%d.%m.%Y %H:%M") if g.scheduled_at else "—"
    try:
        baslik, govde = await render(
            db, "icerik_onay_istendi", f"İçerik onayınızı bekliyor — {g.title}",
            (f"Merhaba,\n\nOnayınıza sunulan içerik: {g.title}\nKanallar: {', '.join(kanal_listesi(g))}\n"
             f"Planlanan: {yerel} ({g.saat_dilimi or VARSAYILAN_SAAT_DILIMI})\n\n"
             f"Giriş yapmadan inceleyip onaylayabilir ya da revizyon isteyebilirsiniz:\n{baglanti}\n\n"
             f"Content awaiting your approval: {g.title}\nReview it (no login needed): {baglanti}\n\n— By Mehmet KURU Dev"),
            {"baslik": g.title, "baglanti": baglanti, "planlanan": yerel, "planlanan_utc": st.iso(zaman) or ""},
        )
        satirlar = await dispatch(db, event_type="icerik_onay_istendi", title=baslik, body=govde,
                                  recipients=[{"email": g.hesap_email, "role": "client"}], link=baglanti,
                                  ref_type="content_post", ref_id=g.id)
        gitti = any(getattr(s, "channel", "") == "email" and getattr(s, "delivery_status", "") == "sent" for s in satirlar)
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
        logger.exception("İçerik onay e-postası gönderilemedi: gönderi %s", g.id)
        return False


async def onay_etkisi(db: AsyncSession, kayit: Any, sonuc: str, not_: Optional[str], ek: Dict[str, Any]) -> List[Dict[str, Any]]:
    """`imzali_islem._etkiyi_uygula` → müşterinin kararı gönderiye (commit ETMEZ). Bildirim listesi döner."""
    from services.imzali_islem import IslemHatasi

    g = (await db.execute(select(Content_posts).where(Content_posts.id == kayit.hedef_id))).scalars().first()
    if g is None:
        raise IslemHatasi(404, "hedef_yok")
    if (g.status or "") != "musteri_onayi" or g.onay_islem_id != kayit.id:
        raise IslemHatasi(409, "hedef_degisti")
    an = st.simdi()
    kisi = st.eposta_duzelt(ek.get("kisi")) or kayit.alici_eposta
    g.durum_at = an
    g.durum_degistiren = kisi
    g.durum_notu = not_
    g.onay_islem_id = None
    if sonuc == "onay":
        g.status = "onaylandi"
        g.onay_at = an
        g.onaylayan = kisi
        baslik = f"İçerik onaylandı: {g.title} — {kayit.alici_eposta}"
        govde = f"{g.title}\nMüşteri içeriği onayladı." + (f"\nNot: {not_}" if not_ else "")
    else:
        g.status = "taslak"
        # Flush kancası bu bayrakla `icerik.revizyon_istendi` olayını üretiyor (geri çekmeden ayrılsın).
        g._icerik_revizyon = True  # type: ignore[attr-defined]
        baslik = f"İçerik için revizyon istendi: {g.title} — {kayit.alici_eposta}"
        govde = f"{g.title}\nRevizyon notu:\n{not_ or ''}"
    await db.flush()
    bildirim = {
        "event_type": "icerik_karar", "title": baslik[:250], "body": govde, "yoneticiye": True,
        "link": "/admin?sekme=icerik", "ref_type": "content_post", "ref_id": g.id,
    }
    if g.sorumlu_eposta:
        bildirim["alicilar"] = [{"email": g.sorumlu_eposta, "role": "admin"}]
    return [bildirim]


async def bekleyen_onaylar(db: AsyncSession, hesap: str) -> List[Dict[str, Any]]:
    """Müşteri panelinin "Onay bekleyen içerikler" listesi (modülden bağımsız)."""
    from models.signed_actions import SignedActions

    an = st.simdi()
    kayitlar = (await db.execute(
        select(Content_posts, SignedActions).join(SignedActions, SignedActions.id == Content_posts.onay_islem_id).where(
            Content_posts.hesap_email == hesap, Content_posts.status == "musteri_onayi",
            SignedActions.durum == "bekliyor", SignedActions.son_kullanma > an, SignedActions.tur == "icerik_onay",
        ).order_by(Content_posts.scheduled_at.asc())
    )).all()
    markalar = await marka_adlari(db, [g.marka_id for g, _ in kayitlar])
    return [{"islem_id": k.id, "son_kullanma": st.iso(k.son_kullanma),
             "gonderi": onizleme_sozlugu(g, markalar.get(g.marka_id))} for g, k in kayitlar]


# ---------------------------------------------------------------------------
# UTM'li kısa linkler (Faz 4Q motoru)
# ---------------------------------------------------------------------------
async def kisa_link_uret(db: AsyncSession, g: Content_posts, kisi: str) -> Dict[str, Any]:
    from models.dinamik_qr import DinamikQr
    from routers.dinamik_qr import _benzersiz_kodlar
    from services import dinamik_qr as dq

    if not g.link_url:
        raise StudyoHatasi("metin_gerekli", alan="baglanti")
    kanallar = kanal_listesi(g)
    if not kanallar:
        raise StudyoHatasi("metin_gerekli", alan="kanallar")
    mevcut = st.json_yukle(g.kisa_linkler, {})
    eksik = [k for k in kanallar if not (isinstance(mevcut.get(k), dict) and mevcut[k].get("kod"))]
    kodlar = await _benzersiz_kodlar(db, len(eksik)) if eksik else []
    for kanal, kod in zip(eksik, kodlar):
        alanlar = {"url": g.link_url, "utm_source": kanal, "utm_medium": "email" if kanal == "email" else "social",
                   "utm_campaign": kampanya_slug(g.campaign) or f"icerik-{g.id}"}
        try:
            temiz, _ = dq.dogrula("url", alanlar)
        except dq.QrHatasi as h:
            raise StudyoHatasi(h.kod, h.durum, alan="baglanti")
        q = DinamikQr(hesap_email=g.hesap_email or None, olusturan_email=kisi or None, kod=kod, ad=f"İçerik #{g.id} · {kanal}"[:120],
                      tur="url", kisa_link=True, alanlar=json.dumps(temiz, ensure_ascii=False), hedef=dq.hedef_uret("url", temiz),
                      tasarim=json.dumps({}), logo_var=False, aktif=True, engelli=False, tarama_sayisi=0)
        db.add(q)
        await db.flush()
        mevcut[kanal] = {"qr_id": q.id, "kod": kod, "adres": dq.kisa_adres(kod)}
    g.kisa_linkler = st.json_yaz(mevcut)
    await db.commit()
    await db.refresh(g)
    return mevcut


# ---------------------------------------------------------------------------
# Paylaşım paketi, ZIP, CSV
# ---------------------------------------------------------------------------
def paylasim_paketi(g: Content_posts) -> Dict[str, Any]:
    return {"gonderi_id": g.id, "baslik": g.title, "kanallar": kanal_ozeti(g), "gorseller": _gorsel_listesi(g),
            "video_url": g.video_url or "", "planlanan": _yerel_metin(g.scheduled_at), "planlanan_at": st.iso(gonderi_utc(g)),
            "saat_dilimi": g.saat_dilimi or VARSAYILAN_SAAT_DILIMI, "durum": g.status or "taslak"}


async def gorseller_zip(db: AsyncSession, g: Content_posts) -> bytes:
    from services import dosya_deposu

    liste_ = st.json_yukle(g.gorseller, [])
    if not liste_:
        raise StudyoHatasi("gorsel_yok", 404)
    kayitlar = {x.anahtar: x for x in (await db.execute(select(IcerikGorselleri).where(
        IcerikGorselleri.anahtar.in_([y.get("anahtar") for y in liste_ if isinstance(y, dict)])
    ))).scalars().all()}
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for i, y in enumerate(liste_, 1):
            k = kayitlar.get(y.get("anahtar")) if isinstance(y, dict) else None
            if k is None:
                continue
            uz = _uzanti(k.tur)
            try:
                veri = await dosya_deposu.oku(db, k.depo, f"icerik/{k.anahtar}.{uz}")
            except Exception:  # noqa: BLE001
                logger.warning("İçerik görseli okunamadı: %s", k.anahtar)
                continue
            z.writestr(f"{g.id}-{i:02d}.{uz}", veri)
    return tampon.getvalue()


_CSV_TEHLIKE = re.compile(r"^[=+@\t\r]|^-[\d=+(]")


def _hucre(s: Any) -> str:
    s = "" if s is None else str(s)
    return "'" + s if _CSV_TEHLIKE.match(s) else s


CSV_SUTUNLARI = ("tarih", "kanal", "metin", "gorsel_url", "baglanti", "ilk_yorum", "saat_dilimi", "baslik", "kampanya", "durum")


def csv_uret(gonderiler: Sequence[Content_posts]) -> str:
    """Postiz/Buffer içe aktarma için: gönderi × kanal başına bir satır (tarih ISO 8601, ofsetli)."""
    tampon = io.StringIO()
    w = csv.writer(tampon, lineterminator="\n")
    w.writerow(CSV_SUTUNLARI)
    for g in gonderiler:
        u = gonderi_utc(g)
        tarih = u.astimezone(tz_coz(g.saat_dilimi)).isoformat(timespec="minutes") if u else ""
        gorsel = _gorsel_listesi(g)
        for k in kanal_listesi(g):
            m, baglanti = paylasim_metni(g, k)
            w.writerow([_hucre(x) for x in (tarih, k, m, gorsel[0]["url"] if gorsel else (g.image_url or ""), baglanti or "",
                                             g.ilk_yorum or "", g.saat_dilimi or VARSAYILAN_SAAT_DILIMI, g.title,
                                             g.campaign or "", g.status or "taslak")])
    return tampon.getvalue()


# ---------------------------------------------------------------------------
# Görsel yükleme
# ---------------------------------------------------------------------------
def _uzanti(tur: str) -> str:
    return {"image/png": "png", "image/webp": "webp"}.get(tur, "jpg")


def gorsel_hazirla(bayt: bytes) -> Dict[str, Any]:
    if len(bayt) > GORSEL_EN_COK_BAYT:
        raise StudyoHatasi("gorsel_buyuk", 413, en_cok_mb=GORSEL_EN_COK_BAYT // (1024 * 1024))
    if not bayt:
        raise StudyoHatasi("gorsel_gecersiz")
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(bayt)) as ham:
            if ham.format not in ("JPEG", "PNG", "WEBP"):
                raise StudyoHatasi("gorsel_turu", 415)
            if ham.size[0] < 16 or ham.size[1] < 16 or ham.size[0] * ham.size[1] > 60_000_000:
                raise StudyoHatasi("gorsel_boyutu")
            ham.load()
            g = ImageOps.exif_transpose(ham)
            saydam = g.mode in ("RGBA", "LA") or (g.mode == "P" and "transparency" in g.info)
            g = g.convert("RGBA" if saydam else "RGB")
    except StudyoHatasi:
        raise
    except Exception as exc:  # noqa: BLE001 - bozuk dosya
        raise StudyoHatasi("gorsel_gecersiz") from exc
    g.thumbnail((GORSEL_KENAR, GORSEL_KENAR), Image.LANCZOS)
    cikti = io.BytesIO()
    # EXIF/konum bilgisi yeniden kodlamada atılıyor.
    if saydam:
        g.save(cikti, format="PNG", optimize=True)
        tur = "image/png"
    else:
        g.save(cikti, format="JPEG", quality=88, optimize=True, progressive=True)
        tur = "image/jpeg"
    return {"veri": cikti.getvalue(), "tur": tur, "genislik": g.width, "yukseklik": g.height}


def gorsel_anahtari() -> str:
    return secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")


def gorsel_sozlugu(g: IcerikGorselleri) -> Dict[str, Any]:
    return {"anahtar": g.anahtar, "url": gorsel_adresi(g.anahtar), "ad": g.ad or "", "tur": g.tur,
            "genislik": g.genislik, "yukseklik": g.yukseklik, "boyut": g.boyut, "created_at": st.iso(g.created_at)}


# ---------------------------------------------------------------------------
# Zamanlı: hatırlatma (30 dk önce, tek kez) + `icerik.yayin_zamani`
# ---------------------------------------------------------------------------
async def _hatirlatma_alicilari(db: AsyncSession, g: Content_posts) -> List[Dict[str, Any]]:
    from services.notify import admin_recipients

    if g.sorumlu_eposta:
        return [{"email": g.sorumlu_eposta, "role": "client" if g.hesap_email and musteri_yonetir_mi(g) else "admin"}]
    if g.hesap_email and musteri_yonetir_mi(g):
        return [{"email": g.hesap_email, "role": "client"}]
    return await admin_recipients(db)


async def zamanli_gorev(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    from services import webhook
    from services.notify import dispatch, render

    await eski_kayitlari_duzelt(db)
    an = an or st.simdi()
    yerel_alt = (an - timedelta(days=1)).replace(tzinfo=None)
    yerel_ust = (an + timedelta(days=1)).replace(tzinfo=None)
    adaylar = (await db.execute(select(Content_posts).where(
        Content_posts.status.in_(ACIK_DURUMLAR), Content_posts.scheduled_at.isnot(None),
        Content_posts.scheduled_at >= yerel_alt, Content_posts.scheduled_at <= yerel_ust,
        or_(Content_posts.hatirlatma_at.is_(None), and_(Content_posts.status == "onaylandi", Content_posts.yayin_olayi_at.is_(None))),
    ).limit(500))).scalars().all()
    hatirlatilan = olay = 0
    for g in adaylar:
        u = gonderi_utc(g)
        if u is None:
            continue
        # 1) Hatırlatma: [planlanan − 30 dk, planlanan + 15 dk) — koşullu UPDATE ile TEK KEZ.
        if g.hatirlatma_at is None and u - HATIRLATMA_ONCE <= an < u + HATIRLATMA_GEC:
            r = await db.execute(update(Content_posts).where(Content_posts.id == g.id, Content_posts.hatirlatma_at.is_(None))
                                 .values(hatirlatma_at=an).execution_options(synchronize_session=False))
            await db.commit()
            if r.rowcount == 1:
                hatirlatilan += 1
                try:
                    yerel = g.scheduled_at.strftime("%d.%m.%Y %H:%M")
                    hazir = (g.status or "") == "onaylandi"
                    baslik, govde = await render(
                        db, "icerik_hatirlatma",
                        f"{'Paylaşıma hazır' if hazir else 'Henüz onaylanmadı'}: {g.title} ({yerel})",
                        (f"{g.title}\nKanallar: {', '.join(kanal_listesi(g))}\nPlanlanan: {yerel} ({g.saat_dilimi or VARSAYILAN_SAAT_DILIMI})\n"
                         + ("Panelden \"Paylaşıma hazır\" paketini açın: metni kopyalayın, görselleri indirin, paylaştıktan sonra "
                            "\"Yayınlandı\" olarak işaretleyin." if hazir else
                            f"Durum: {g.status}. Planlanan saat yaklaşıyor; onay sürecini tamamlayın.")),
                        {"baslik": g.title, "planlanan": yerel, "durum": g.status or ""},
                    )
                    sekme = "/client?sekme=icerik" if g.hesap_email and musteri_yonetir_mi(g) else "/admin?sekme=icerik"
                    await dispatch(db, event_type="icerik_hatirlatma", title=baslik, body=govde,
                                   recipients=await _hatirlatma_alicilari(db, g), link=f"{sekme}&gonderi={g.id}",
                                   ref_type="content_post", ref_id=g.id)
                except Exception:  # noqa: BLE001 - işaret kaldı; bir sonraki turda tekrar denenmez (tek kez)
                    logger.exception("İçerik hatırlatması gönderilemedi: %s", g.id)
        # 2) Yayın zamanı olayı (onaylı gönderi; planlanan saat geldi, 6 saatten eski değil).
        if (g.status or "") == "onaylandi" and g.yayin_olayi_at is None and u <= an < u + YAYIN_OLAYI_GEC:
            r = await db.execute(update(Content_posts).where(Content_posts.id == g.id, Content_posts.yayin_olayi_at.is_(None))
                                 .values(yayin_olayi_at=an).execution_options(synchronize_session=False))
            if r.rowcount == 1:
                veri = olay_verisi(g)
                await db.run_sync(lambda s: webhook.olaylari_yayinla_sync(
                    s.connection(), [("icerik.yayin_zamani", g.hesap_email or None, veri, True)]))
                olay += 1
            await db.commit()
    return {"hatirlatma": hatirlatilan, "yayin_olayi": olay, "aday": len(adaylar)}


def olay_verisi(g: Content_posts, ek: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Webhook/otomasyon olay verisi — metin YOK (API'den alınır), kimlik ve özet."""
    try:
        u = gonderi_utc(g)
    except Exception:  # noqa: BLE001
        u = None
    d = {"gonderi_id": g.id, "baslik": g.title, "durum": g.status, "kanallar": kanal_listesi(g),
         "planlanan_at": st.iso(u), "kampanya": g.campaign, "marka_id": g.marka_id, "yoneten": g.yoneten or "ajans",
         "proje_id": g.proje_id}
    if ek:
        d.update(ek)
    return d
