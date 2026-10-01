"""Faz 3Z — proje şablonları: görev listesi + göreli tarihler → Kanban'a hazır proje.

Şablon görevi
-------------
    {baslik, aciklama, asama, baslangic_gun, sure_gun, kontrol_listesi: [str],
     atanan_eposta, atanan_rol, musteriye_gorunur, kilometre_tasi, oncelik, tahmini_saat}

* `baslangic_gun` projenin başlangıcından itibaren gün (0 = ilk gün),
  `sure_gun` en az 1. Görevin başlangıcı = proje başlangıcı + baslangic_gun,
  bitişi = başlangıç + sure_gun − 1 (bir günlük görev aynı gün biter).
* `asama` görev etiketine dönüşür (Kanban'da aşamaya göre süzülebilsin).
* Atanan: önce `atanan_eposta` (aktif ekip üyesiyse), yoksa `atanan_rol` —
  ekip listesinde rolü (`yonetici`/`calisan`) ya da hizmetlerinden biri
  (seo, website…) bu değer olan ilk aktif kişi. Bulunamazsa atanmamış.
* Görevler "Yapılacak" sütununa, şablondaki sırayla düşer.

Tohum
-----
Tablo boşsa ilk listelemede üç hazır örnek yazılır ("Kurumsal web sitesi",
"SEO bakım (aylık)", "E-ticaret kurulumu"). Yazıldığı site ayarına
(`proje_sablonlari_tohum`) işleniyor: yönetici hepsini silerse geri gelmez.
"""

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from models.proje_gorevleri import ONCELIKLER, ProjectTasks, TaskChecklist
from models.projects import Projects
from models.staff import Staff
from models.zaman_takibi import ProjeSablonlari
from services.gorevler import GorevHatasi as SablonHatasi
from services.gorevler import eposta_duzelt, iso
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AD_SINIRI = 200
ACIKLAMA_SINIRI = 4000
GOREV_SINIRI = 200
KONTROL_SINIRI = 50
KONTROL_METNI = 300
EN_COK_GUN = 3650
TOHUM_AYARI = "proje_sablonlari_tohum"


def _metin(deger: Any, sinir: int) -> Optional[str]:
    temiz = str(deger or "").strip()
    return temiz[:sinir] or None


def _tamsayi(deger: Any, kod: str, *, en_az: int, en_cok: int, varsayilan: int) -> int:
    if deger in (None, ""):
        return varsayilan
    try:
        sayi = int(deger)
    except (TypeError, ValueError) as exc:
        raise SablonHatasi(400, kod) from exc
    if isinstance(deger, bool) or sayi < en_az or sayi > en_cok:
        raise SablonHatasi(400, kod)
    return sayi


def _saat(deger: Any, kod: str = "saat_gecersiz") -> Optional[float]:
    if deger in (None, ""):
        return None
    try:
        s = float(deger)
    except (TypeError, ValueError) as exc:
        raise SablonHatasi(400, kod) from exc
    if s != s or s < 0 or s > 100000:
        raise SablonHatasi(400, kod)
    return round(s, 2)


def gorev_dogrula(ham: Any, sira: int) -> Dict[str, Any]:
    if not isinstance(ham, dict):
        raise SablonHatasi(400, "gorev_gecersiz", sira=sira)
    baslik = _metin(ham.get("baslik"), 200)
    if not baslik:
        raise SablonHatasi(400, "gorev_basligi_gerekli", sira=sira)
    kontrol = ham.get("kontrol_listesi") or []
    if isinstance(kontrol, str):
        kontrol = [s for s in kontrol.splitlines()]
    if not isinstance(kontrol, list):
        raise SablonHatasi(400, "kontrol_gecersiz", sira=sira)
    kontrol = [m for m in (_metin(x, KONTROL_METNI) for x in kontrol) if m][:KONTROL_SINIRI]
    oncelik = ham.get("oncelik") or "normal"
    if oncelik not in ONCELIKLER:
        raise SablonHatasi(400, "oncelik_gecersiz", sira=sira)
    atanan = eposta_duzelt(ham.get("atanan_eposta"))
    if atanan and ("@" not in atanan or len(atanan) > 254):
        raise SablonHatasi(400, "atanan_gecersiz", sira=sira)
    return {
        "baslik": baslik,
        "aciklama": _metin(ham.get("aciklama"), ACIKLAMA_SINIRI),
        "asama": _metin(ham.get("asama"), 30),
        "baslangic_gun": _tamsayi(ham.get("baslangic_gun"), "gun_gecersiz", en_az=0, en_cok=EN_COK_GUN, varsayilan=0),
        "sure_gun": _tamsayi(ham.get("sure_gun"), "sure_gecersiz", en_az=1, en_cok=EN_COK_GUN, varsayilan=1),
        "kontrol_listesi": kontrol,
        "atanan_eposta": atanan or None,
        "atanan_rol": _metin(ham.get("atanan_rol"), 40),
        "musteriye_gorunur": bool(ham.get("musteriye_gorunur")),
        "kilometre_tasi": bool(ham.get("kilometre_tasi")),
        "oncelik": oncelik,
        "tahmini_saat": _saat(ham.get("tahmini_saat")),
    }


def gorevleri_dogrula(ham: Any) -> List[Dict[str, Any]]:
    if ham is None:
        return []
    if not isinstance(ham, list):
        raise SablonHatasi(400, "gorevler_gecersiz")
    if len(ham) > GOREV_SINIRI:
        raise SablonHatasi(400, "gorev_siniri")
    return [gorev_dogrula(g, i) for i, g in enumerate(ham)]


def gorevleri_coz(metin: Optional[str]) -> List[Dict[str, Any]]:
    if not metin:
        return []
    try:
        liste = json.loads(metin)
    except (TypeError, ValueError):
        return []
    return [g for g in liste if isinstance(g, dict)] if isinstance(liste, list) else []


def toplam_gun(gorevler: List[Dict[str, Any]]) -> int:
    return max([int(g.get("baslangic_gun") or 0) + int(g.get("sure_gun") or 1) for g in gorevler] or [0])


def sozluk(s: ProjeSablonlari) -> Dict[str, Any]:
    gorevler = gorevleri_coz(s.gorevler)
    return {
        "id": s.id,
        "ad": s.ad,
        "aciklama": s.aciklama,
        "kategori": s.kategori,
        "tahmini_saat": s.tahmini_saat,
        "gorevler": gorevler,
        "gorev_sayisi": len(gorevler),
        "toplam_gun": toplam_gun(gorevler),
        "hazir": bool(s.hazir),
        "created_at": iso(s.created_at),
        "updated_at": iso(s.updated_at),
    }


def alanlari_uygula(s: ProjeSablonlari, govde: Dict[str, Any], *, yeni: bool) -> None:
    if "ad" in govde or yeni:
        ad = _metin(govde.get("ad"), AD_SINIRI)
        if not ad:
            raise SablonHatasi(400, "ad_gerekli")
        s.ad = ad
    if "aciklama" in govde or yeni:
        s.aciklama = _metin(govde.get("aciklama"), ACIKLAMA_SINIRI)
    if "kategori" in govde or yeni:
        s.kategori = _metin(govde.get("kategori"), 60)
    if "gorevler" in govde or yeni:
        s.gorevler = json.dumps(gorevleri_dogrula(govde.get("gorevler")), ensure_ascii=False)
    if "tahmini_saat" in govde or yeni:
        saat = _saat(govde.get("tahmini_saat"))
        if saat is None:
            # Boşsa görevlerin tahmini saatlerinin toplamı.
            toplam = sum(float(g.get("tahmini_saat") or 0) for g in gorevleri_coz(s.gorevler))
            saat = round(toplam, 2) if toplam else None
        s.tahmini_saat = saat


async def bul(db: AsyncSession, sablon_id: Any) -> ProjeSablonlari:
    try:
        sid = int(sablon_id)
    except (TypeError, ValueError) as exc:
        raise SablonHatasi(404, "sablon_yok") from exc
    s = (await db.execute(select(ProjeSablonlari).where(ProjeSablonlari.id == sid))).scalar_one_or_none()
    if s is None:
        raise SablonHatasi(404, "sablon_yok")
    return s


async def listele(db: AsyncSession) -> List[Dict[str, Any]]:
    await tohumla(db)
    satirlar = (await db.execute(select(ProjeSablonlari).order_by(ProjeSablonlari.ad, ProjeSablonlari.id))).scalars().all()
    return [sozluk(s) for s in satirlar]


async def olustur(db: AsyncSession, govde: Dict[str, Any], olusturan: Optional[str]) -> ProjeSablonlari:
    s = ProjeSablonlari(hazir=False, olusturan_eposta=eposta_duzelt(olusturan) or None)
    alanlari_uygula(s, govde, yeni=True)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def guncelle(db: AsyncSession, s: ProjeSablonlari, govde: Dict[str, Any]) -> ProjeSablonlari:
    alanlari_uygula(s, govde, yeni=False)
    await db.commit()
    await db.refresh(s)
    return s


async def sil(db: AsyncSession, s: ProjeSablonlari) -> None:
    """Çöp kutusuna düşer (`proje_sablonlari` izinli tablo)."""
    await db.delete(s)
    await db.commit()


# ---------------------------------------------------------------------------
# Uygulama: şablon → proje görevleri
# ---------------------------------------------------------------------------
def gorev_tarihleri(baslangic: date, g: Dict[str, Any]) -> Tuple[date, date]:
    bas = baslangic + timedelta(days=int(g.get("baslangic_gun") or 0))
    bit = bas + timedelta(days=max(1, int(g.get("sure_gun") or 1)) - 1)
    return bas, bit


def _etiket(asama: Optional[str]) -> List[str]:
    if not asama:
        return []
    temiz = re.sub(r"\s+", " ", asama.strip().lower())[:30]
    return [temiz] if temiz else []


async def _ekip(db: AsyncSession) -> List[Staff]:
    return list((await db.execute(select(Staff).where(Staff.aktif.isnot(False)).order_by(Staff.id))).scalars().all())


def atanan_coz(ekip: List[Staff], g: Dict[str, Any]) -> Optional[str]:
    eposta = eposta_duzelt(g.get("atanan_eposta"))
    if eposta and any(eposta_duzelt(s.email) == eposta for s in ekip):
        return eposta
    rol = (g.get("atanan_rol") or "").strip().lower()
    if rol:
        for s in ekip:
            hizmetler = {h.strip().lower() for h in (s.hizmetler or "").split(",") if h.strip()}
            if (s.rol or "").strip().lower() == rol or rol in hizmetler:
                return eposta_duzelt(s.email) or None
    return None


async def uygula(
    db: AsyncSession, s: ProjeSablonlari, proje: Projects, baslangic: date, olusturan: Optional[str] = None
) -> List[ProjectTasks]:
    """Şablon görevlerini projeye ekler (flush eder, commit ETMEZ)."""
    gorevler = gorevleri_coz(s.gorevler)
    if not gorevler:
        return []
    from routers.gorevler import GOREV_PROJE_BASINA

    mevcut = int(
        (await db.execute(select(func.count(ProjectTasks.id)).where(ProjectTasks.proje_id == proje.id))).scalar() or 0
    )
    if mevcut + len(gorevler) > GOREV_PROJE_BASINA:
        raise SablonHatasi(409, "gorev_siniri")
    en_buyuk = (
        await db.execute(
            select(func.coalesce(func.max(ProjectTasks.sira), -1))
            .where(ProjectTasks.proje_id == proje.id)
            .where(ProjectTasks.durum == "yapilacak")
        )
    ).scalar()
    sira = int(en_buyuk) if en_buyuk is not None else -1
    ekip = await _ekip(db)
    olusan: List[Tuple[ProjectTasks, List[str]]] = []
    for g in gorevler:
        bas, bit = gorev_tarihleri(baslangic, g)
        sira += 1
        gorev = ProjectTasks(
            proje_id=proje.id,
            baslik=str(g.get("baslik") or "")[:200] or "—",
            aciklama=g.get("aciklama"),
            durum="yapilacak",
            oncelik=g.get("oncelik") if g.get("oncelik") in ONCELIKLER else "normal",
            atanan=atanan_coz(ekip, g),
            baslangic_tarihi=bas,
            bitis_tarihi=bit,
            sira=sira,
            musteriye_gorunur=bool(g.get("musteriye_gorunur")),
            kilometre_tasi=bool(g.get("kilometre_tasi")),
            tahmini_saat=g.get("tahmini_saat"),
            harcanan_saat=0.0,
            etiketler=json.dumps(_etiket(g.get("asama")), ensure_ascii=False),
            olusturan_eposta=eposta_duzelt(olusturan) or None,
        )
        db.add(gorev)
        olusan.append((gorev, [m for m in (g.get("kontrol_listesi") or []) if isinstance(m, str) and m.strip()]))
    await db.flush()
    for gorev, maddeler in olusan:
        for i, metin in enumerate(maddeler[:KONTROL_SINIRI]):
            db.add(TaskChecklist(gorev_id=gorev.id, metin=metin[:KONTROL_METNI], tamam=False, sira=i))
    await db.flush()
    return [g for g, _ in olusan]


async def proje_olustur(
    db: AsyncSession, s: ProjeSablonlari, govde: Dict[str, Any], olusturan: Optional[str]
) -> Tuple[Projects, List[ProjectTasks]]:
    """Şablondan yeni proje + görevler (tek işlem)."""
    from services.zaman_takibi import bugun, tarih_coz

    baslangic = tarih_coz(govde.get("baslangic_tarihi")) or bugun()
    baslik = _metin(govde.get("baslik"), 200) or s.ad
    eposta = eposta_duzelt(govde.get("client_email"))
    if eposta and ("@" not in eposta or len(eposta) > 254):
        raise SablonHatasi(400, "eposta_gecersiz")
    proje = Projects(
        title=baslik,
        description=_metin(govde.get("aciklama"), 2000) or s.aciklama or s.ad,
        category=_metin(govde.get("kategori"), 60) or s.kategori or "Website",
        client_name=_metin(govde.get("client_name"), 200),
        client_email=eposta or None,
        status="in_progress",
        stage="discovery",
        progress=0,
        published=False,
        created_at=datetime.now(),
    )
    db.add(proje)
    await db.flush()
    gorevler = await uygula(db, s, proje, baslangic, olusturan)
    await db.commit()
    await db.refresh(proje)
    return proje, gorevler


async def projeden_kaydet(db: AsyncSession, proje: Projects, govde: Dict[str, Any], olusturan: Optional[str]) -> ProjeSablonlari:
    """Projenin görevlerinden şablon. Göreli gün, en erken görev tarihinden hesaplanıyor."""
    from services.gorevler import REVIZYON_ETIKETI, etiketleri_coz, kontroller_sozlugu, proje_gorevleri

    gorevler = [g for g in await proje_gorevleri(db, proje.id) if REVIZYON_ETIKETI not in etiketleri_coz(g.etiketler)]
    if not gorevler:
        raise SablonHatasi(409, "gorev_yok")
    kontroller = await kontroller_sozlugu(db, [g.id for g in gorevler])
    tarihler = [d for g in gorevler for d in (g.baslangic_tarihi, g.bitis_tarihi) if d is not None]
    kok = min(tarihler) if tarihler else None
    liste: List[Dict[str, Any]] = []
    sirali = sorted(gorevler, key=lambda g: (g.baslangic_tarihi or g.bitis_tarihi or date.max, g.sira, g.id))
    for g in sirali:
        bas = g.baslangic_tarihi or g.bitis_tarihi
        bit = g.bitis_tarihi or g.baslangic_tarihi
        etiketler = [e for e in etiketleri_coz(g.etiketler) if e not in (REVIZYON_ETIKETI, "hata")]
        liste.append({
            "baslik": g.baslik,
            "aciklama": g.aciklama,
            "asama": etiketler[0] if etiketler else None,
            "baslangic_gun": (bas - kok).days if (bas and kok) else 0,
            "sure_gun": max(1, (bit - bas).days + 1) if (bas and bit) else 1,
            "kontrol_listesi": [k.metin for k in sorted(kontroller.get(g.id, []), key=lambda k: (k.sira, k.id))],
            "atanan_eposta": g.atanan,
            "atanan_rol": None,
            "musteriye_gorunur": bool(g.musteriye_gorunur),
            "kilometre_tasi": bool(g.kilometre_tasi),
            "oncelik": g.oncelik,
            "tahmini_saat": g.tahmini_saat,
        })
    govde = {
        "ad": _metin(govde.get("ad"), AD_SINIRI) or f"{proje.title} (şablon)",
        "aciklama": govde.get("aciklama") if govde.get("aciklama") is not None else proje.description,
        "kategori": proje.category,
        "gorevler": liste,
        "tahmini_saat": govde.get("tahmini_saat"),
    }
    return await olustur(db, govde, olusturan)


# ---------------------------------------------------------------------------
# Tohum
# ---------------------------------------------------------------------------
def _g(baslik, asama, gun, sure, kontrol=(), *, gorunur=False, kilometre=False, rol=None, saat=None, aciklama=None, oncelik="normal"):
    return {
        "baslik": baslik, "aciklama": aciklama, "asama": asama, "baslangic_gun": gun, "sure_gun": sure,
        "kontrol_listesi": list(kontrol), "atanan_eposta": None, "atanan_rol": rol,
        "musteriye_gorunur": gorunur, "kilometre_tasi": kilometre, "oncelik": oncelik, "tahmini_saat": saat,
    }


HAZIR_SABLONLAR: List[Dict[str, Any]] = [
    {
        "ad": "Kurumsal web sitesi",
        "aciklama": "Keşiften canlı yayına 5–8 sayfalık kurumsal site: içerik, tasarım onayı, geliştirme, test ve teslim.",
        "kategori": "Website",
        "gorevler": [
            _g("Keşif görüşmesi ve brief", "Keşif", 0, 2,
               ["Hedefler ve hedef kitle", "Rakip siteler", "Sayfa listesi (site haritası taslağı)", "Alan adı ve barındırma bilgileri"],
               gorunur=True, rol="website", saat=3),
            _g("İçerik ve görsellerin toplanması", "Keşif", 2, 3,
               ["Kurumsal metinler", "Logo ve marka renkleri", "Fotoğraflar / görseller"], gorunur=True, saat=2),
            _g("Tasarım taslakları (ana sayfa + iç sayfa)", "Tasarım", 5, 5,
               ["Masaüstü taslak", "Mobil taslak", "Müşteriye sunum"], gorunur=True, rol="website", saat=12),
            _g("Tasarım onayı", "Tasarım", 10, 1, gorunur=True, kilometre=True, oncelik="yuksek"),
            _g("Ön yüz geliştirme", "Geliştirme", 11, 7,
               ["Sayfa şablonları", "İletişim formu", "Çoklu dil (gerekirse)"], rol="website", saat=24),
            _g("İçerik girişi ve temel SEO", "Geliştirme", 15, 3,
               ["Başlık ve açıklama etiketleri", "Site haritası ve robots.txt", "Görsel alt metinleri"], rol="seo", saat=6),
            _g("Test: mobil, tarayıcı, hız", "Test", 18, 2,
               ["Mobil görünüm", "Form gönderimi", "PageSpeed ölçümü", "Kırık bağlantı taraması"], rol="website", saat=5),
            _g("Canlı yayın ve teslim", "Yayın", 20, 1,
               ["DNS ve SSL", "Analytics / Search Console", "Yönetim eğitimi"], gorunur=True, kilometre=True, oncelik="yuksek", saat=3),
        ],
    },
    {
        "ad": "SEO bakım (aylık)",
        "aciklama": "Her ay tekrarlanan SEO bakım döngüsü: teknik tarama, sıralama takibi, içerik, hız ve aylık rapor.",
        "kategori": "SEO",
        "gorevler": [
            _g("Teknik SEO taraması", "Analiz", 0, 1,
               ["Tarama hataları (Search Console)", "Kırık bağlantılar", "Yönlendirmeler", "Yapısal veri"], rol="seo", saat=2),
            _g("Anahtar kelime sıralama kontrolü", "Analiz", 1, 1, ["Hedef kelimelerde sıra", "Yeni fırsat kelimeleri"], rol="seo", saat=1.5),
            _g("İçerik güncelleme / yeni içerik", "İçerik", 2, 10,
               ["Eskiyen sayfaları güncelle", "Ayın blog yazısı", "İç bağlantılar"], rol="seo", saat=6),
            _g("Hız ve Core Web Vitals kontrolü", "Teknik", 5, 1, ["Mobil PageSpeed", "LCP / CLS / INP"], rol="website", saat=1),
            _g("Bağlantı (backlink) kontrolü", "Analiz", 10, 2, ["Kazanılan / kaybedilen bağlantılar", "Zararlı bağlantılar"], rol="seo", saat=1.5),
            _g("Aylık rapor ve paylaşım", "Rapor", 27, 2,
               ["Trafik ve sıralama özeti", "Yapılan işler", "Gelecek ayın planı"], gorunur=True, kilometre=True, rol="seo", saat=2),
        ],
    },
    {
        "ad": "E-ticaret kurulumu",
        "aciklama": "Ürün yapısından canlı satışa e-ticaret sitesi: altyapı, tema, ürün girişi, ödeme/kargo, yasal sayfalar ve test siparişleri.",
        "kategori": "E-commerce",
        "gorevler": [
            _g("Keşif: ürün yapısı, ödeme ve kargo gereksinimleri", "Keşif", 0, 3,
               ["Ürün ve kategori yapısı", "Varyantlar (beden, renk)", "Ödeme yöntemleri", "Kargo firmaları"], gorunur=True, rol="website", saat=4),
            _g("Altyapı seçimi ve kurulum", "Kurulum", 3, 2, ["Barındırma", "Mağaza yazılımı", "Yedekleme"], rol="website", saat=4),
            _g("Tema ve tasarım uyarlama", "Tasarım", 5, 5, ["Ana sayfa", "Ürün sayfası", "Sepet ve ödeme adımı"], gorunur=True, rol="website", saat=14),
            _g("Ürün ve kategori girişi", "İçerik", 10, 5, ["Ürün açıklamaları", "Görseller", "Stok ve fiyatlar"], saat=10),
            _g("Ödeme ve kargo entegrasyonu", "Entegrasyon", 12, 3, ["Sanal POS / ödeme sağlayıcısı", "Kargo entegrasyonu", "Sipariş e-postaları"], rol="website", saat=8),
            _g("Yasal sayfalar (KVKK, mesafeli satış, iade)", "İçerik", 12, 2, ["KVKK aydınlatma metni", "Mesafeli satış sözleşmesi", "İade ve değişim"], gorunur=True, saat=2),
            _g("Test siparişleri", "Test", 16, 2, ["Kartla ödeme", "Havale/EFT", "İade akışı", "Mobil ödeme adımı"], rol="website", saat=4, oncelik="yuksek"),
            _g("Canlı yayın", "Yayın", 18, 1, ["SSL", "Analytics ve dönüşüm takibi", "Search Console"], gorunur=True, kilometre=True, oncelik="yuksek", saat=2),
            _g("Eğitim ve teslim", "Yayın", 19, 1, ["Sipariş yönetimi eğitimi", "Ürün ekleme eğitimi"], gorunur=True, saat=2),
        ],
    },
]


async def tohumla(db: AsyncSession) -> int:
    """Tablo boşsa ve daha önce tohumlanmadıysa üç hazır şablonu yazar. → yazılan sayı."""
    from models.site_settings import Site_settings

    try:
        var = (await db.execute(select(ProjeSablonlari.id).limit(1))).first()
        if var is not None:
            return 0
        isaret = (await db.execute(select(Site_settings.id).where(Site_settings.setting_key == TOHUM_AYARI))).first()
        if isaret is not None:
            return 0
        for t in HAZIR_SABLONLAR:
            s = ProjeSablonlari(hazir=True, olusturan_eposta=None)
            alanlari_uygula(s, t, yeni=True)
            db.add(s)
        db.add(Site_settings(setting_key=TOHUM_AYARI, setting_value="1", group_name="zaman", label="Proje şablonları: hazır örnekler yazıldı"))
        await db.commit()
        return len(HAZIR_SABLONLAR)
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.exception("Hazır proje şablonları yazılamadı")
        return 0
