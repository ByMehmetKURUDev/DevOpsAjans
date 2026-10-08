"""Faz 11B — Müşteri paneli "Genel bakış" özeti: tek istekte, yalnız etkin hesabın gerçek verisinden.

Uç: `GET /api/v1/musteri-ozeti` (routers/musteri_ozeti.py). Etkin hesap `dependencies/hesap_baglami`
deseniyle (jeton + `X-MK-Hesap`); müşteri e-postası asla sorgu parametresinden alınmaz.

Kural
-----
* Her kalem kendi `try` bloğunda: hata veren YALNIZ o kalem `null` olur (uydurma/örnek değer yok).
* Ekip üyesinde izni olmayan kalem `null` (ör. `faturalar` izni yoksa `bakiye` ve `faturalar`).
* Modülü kapalı kalem `null` (görev verisi `gorevler`, mesaj süresi `mesajlar`, kendi hedefi `hedefler`,
  imzalı onaylar `islem`, biçimli teklif `teklifler`, sözleşme `sozlesmeler` modülüne bağlı).
* Yalnız müşteriye görünür veri: proje görevlerinden yalnız `musteriye_gorunur` olanlar; toplantıdan not/karar
  YOK; hedeflerden yalnız ajansın PAYLAŞTIĞI (ekip görünürlüklü) ya da hesabın kendi ekip görünürlüklü hedefi —
  özel hedef hiçbir zaman; ekip üyeleri yalnız kısaltılmış ad + baş harf + rol (e-posta YOK).
* Yönetici bu uca kendi adına gelirse (başlık yok sayılır) kendi e-postasının hesabı okunur: müşteri kaydı
  yoksa kalemler boş/null döner — diğer müşteri uçlarının davranışı (403 değil).

Tanımlar
--------
karsilama      hitap (isteği yapan kişinin adı; son kelime soyadı sayılıp atılır), hesap adı, etkin ana proje
               (tamamlanmamış projelerden en son güncellenen) + hazır yüzdesi (projenin `progress` alanı —
               aşama değişince `routers/project_events.py` ile güncellenen mevcut ilerleme; boşsa null),
               sıradaki teslim (ana projede müşteriye görünür, açık, son tarihi olan en yakın görev / kilometre
               taşı), onay bekleyen öğe sayısı.
projeIlerleme  En çok 3 halka. Ana projede müşteriye görünür görev grubu (alt görevi olan görev) varsa her grup
               için alt görevlerin tamamlanma oranı (`gorevler.musteri_gorunumu` ile aynı: tamam / toplam);
               yoksa kilometre taşları (kontrol listesi doluluğu; listesi yoksa tamamsa %100, değilse %0);
               ikisi de yoksa en çok 3 etkin projenin `progress` değeri. Son teslim: en son tamamlanan görünür
               görev; sıradaki: yukarıdaki sıradaki teslim.
kalanIs        Ana projenin açık (müşteriye görünür) görev sayısının son 14 günü (gün sonu; oluşturma ve
               tamamlanma zamanlarından). Plan: proje açılışından en son görev son tarihine doğrusal (kapsam =
               bugünkü görünür görev sayısı → 0); son tarih yoksa plan yok. "Planın N gün önünde/gerisinde":
               bugünkü açık sayıya planın hangi gün ulaştığı ile bugün arasındaki fark (+ önde, − geride).
ekip           Ana projede görev atanmış etkin ekip üyeleri (en çok 4): "Ad S." + baş harfler + hizmet/rol
               anahtarı. Ortalama yanıt süresi: son 90 günde hesabın konuşmalarında müşteri mesajından sonraki
               ilk ajans yanıtına geçen sürenin ortalaması (dakika; mesajlar modülü ve izni varsa; çift yoksa null).
onayBekleyen   Müşteri kararı bekleyen GERÇEK öğeler, mevcut akışlardan: teslim onayı (imzalı işlem
               `teslimat_onay`), fiyat teklifi kabulü (`teklif_kabul`), içerik onayı (İçerik stüdyosu
               `icerik_onay`), biçimli teklif kararı (Faturalar › Teklifler), sözleşme imzası (Faturalar ›
               Sözleşmeler), paylaşılan belge "okudum" onayı. Eylemler mevcut uçları çağırır (ön yüz).
               Revizyon hakkı: `gorevler.revizyon_sayaci` (saat; hak tanımlıysa).
toplanti       En yakın gelecek (ya da sürmekte olan) planlanmış toplantı; katılımcı baş harfleri (dış
               katılımcılar yalnız kişi katılımcıysa — `toplantilar.musteri_sozlugu` kuralı), yanıtım; katıl
               bağlantısı yalnız çevrim içi toplantıda ve başlangıca 15 dk kala → bitişe kadar.
hedef          Ajansın bu hesapla PAYLAŞTIĞI etkin hedef (modül gerekmez — 6O); yoksa hedefler modülü açıksa
               hesabın kendi etkin, ekip görünürlüklü hedefi. Dönemi bugünü kapsayan önce. En çok 3 KR.
bakiye         Cüzdan bakiyeleri (para birimine göre), otomatik ödeme açık mı, bekleyen yükleme bildirimi sayısı.
               Hiç cüzdanı/talebi yoksa null.
faturalar      Kalanı olan açık faturalar (en çok 3, vadesi yakın önce): kod, kalan, vade, durum; o para
               biriminde bakiye kalanı karşılıyorsa `bakiyeden` (Bakiyeden öde), bekleyen ödeme bağlantısı varsa
               adresi.
destek         Açık talepler (en çok 3): ajansın yanıtladığı ve müşteriyi bekleyenler önce.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services import sla
from services.hesap_ekibi import HesapBaglami
from services.yonetim_ozeti import PROJE_KAPALI, eposta, gun_basi, iso, son_gunler, tr_gun, utc

logger = logging.getLogger(__name__)

GUN_SAYISI = 14
HALKA_SAYISI = 3
EKIP_SAYISI = 4
ONAY_SAYISI = 5
FATURA_SAYISI = 3
DESTEK_SAYISI = 3
KR_SAYISI = 3
MESAJ_GUN = 90
#: Çevrim içi toplantıda "Katıl" bağlantısı başlangıçtan bu kadar önce görünür.
KATIL_ONCE = timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
async def _kalem(ad: str, fn: Callable[[], Awaitable[Any]], db: AsyncSession) -> Any:
    """Kalem hesaplanamazsa `None`; hata günlüğe yazılır, yarım işlem geri alınır."""
    try:
        return await fn()
    except Exception:  # noqa: BLE001
        logger.exception("musteri_ozeti: %s hesaplanamadı", ad)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("musteri_ozeti: geri alma başarısız", exc_info=True)
        return None


def hitap(ad: Optional[str]) -> Optional[str]:
    """"Dr. Ayşe Demir" → "Dr. Ayşe"; tek kelimeyse kendisi."""
    kelimeler = (ad or "").strip().split()
    if not kelimeler:
        return None
    if len(kelimeler) >= 2:
        kelimeler = kelimeler[:-1]
    return " ".join(kelimeler)[:60]


def kisa_ad(ad: Optional[str]) -> str:
    """"Selin Kaya" → "Selin K." (soyadı baş harf)."""
    kelimeler = (ad or "").strip().split()
    if not kelimeler:
        return ""
    if len(kelimeler) == 1:
        return kelimeler[0][:40]
    return f"{' '.join(kelimeler[:-1])[:40]} {kelimeler[-1][0].upper()}."


def bas_harf(ad: Optional[str], yedek: str = "") -> str:
    """"Selin Kaya" → "SK"; unvan ("Dr.", "Av.") atlanır; ad yoksa e-postanın ilk iki harfi."""
    kelimeler = [k for k in (ad or "").strip().split() if k[:1].isalnum()]
    adlar = [k for k in kelimeler if not k.endswith(".")]
    if adlar:
        kelimeler = adlar
    if len(kelimeler) >= 2:
        return (kelimeler[0][0] + kelimeler[-1][0]).upper()
    kaynak = kelimeler[0] if kelimeler else (yedek.split("@")[0] if yedek else "?")
    return kaynak[:2].upper()


def _gun(deger: Any) -> Optional[date]:
    if deger is None:
        return None
    if isinstance(deger, datetime):
        return tr_gun(deger)
    if isinstance(deger, date):
        return deger
    try:
        return date.fromisoformat(str(deger).strip()[:10])
    except ValueError:
        return None


def _proje_acik(p: Any) -> bool:
    return (p.status or "").strip().lower() not in PROJE_KAPALI


def _proje_sira_anahtari(p: Any) -> Tuple[datetime, int]:
    an = utc(p.updated_at) or utc(p.created_at) or datetime(1970, 1, 1, tzinfo=sla.TR)
    return an, int(p.id or 0)


class Baglam:
    """Bir istekte bir kez okunan ortak veri (hesap, modüller, projeler, görevler)."""

    def __init__(self, db: AsyncSession, b: HesapBaglami, an: datetime):
        self.db = db
        self.b = b
        self.hesap = eposta(b.hesap_email)
        self.kisi = eposta(b.kisi_email)
        self.an = an
        self.bugun = tr_gun(an)
        self.moduller: Dict[str, bool] = {}
        self.projeler: List[Any] = []
        self.ana_proje: Optional[Any] = None
        self.gorevler: List[Any] = []  # ana projenin bütün görevleri
        self.kontroller: Dict[int, List[Any]] = {}

    def izin(self, *izinler: str) -> bool:
        return any(self.b.izin_var(i) for i in izinler)

    def acik(self, modul: str) -> bool:
        return bool(self.moduller.get(modul))

    @property
    def gorev_okunur(self) -> bool:
        """Görev verisi müşteriye açık mı (`/gorevlerim` ile aynı kapı: modül + izin)."""
        return self.acik("gorevler") and self.izin("gorevler")

    @property
    def gorunur_gorevler(self) -> List[Any]:
        return [g for g in self.gorevler if g.musteriye_gorunur]

    async def hazirla(self) -> None:
        from core import moduller as manifest
        from services.moduller import musteri_modulleri

        try:
            durumlar = (await musteri_modulleri(self.db, self.hesap)).durumlar
        except Exception:  # noqa: BLE001
            logger.exception("musteri_ozeti: modül durumları okunamadı")
            await self.db.rollback()
            durumlar = {}
        for m in manifest.MODULLER:
            d = durumlar.get(m.anahtar)
            self.moduller[m.anahtar] = bool(m.cekirdek or (d is not None and d.acik))

        if not self.hesap or not self.izin("projeler"):
            return
        from models.projects import Projects

        self.projeler = list((await self.db.execute(
            select(Projects).where(func.lower(Projects.client_email) == self.hesap).order_by(Projects.id.desc()).limit(200)
        )).scalars().all())
        etkin = sorted((p for p in self.projeler if _proje_acik(p)), key=_proje_sira_anahtari, reverse=True)
        self.ana_proje = etkin[0] if etkin else None
        if self.ana_proje is None:
            return
        from models.proje_gorevleri import ProjectTasks, TaskChecklist

        self.gorevler = list((await self.db.execute(
            select(ProjectTasks).where(ProjectTasks.proje_id == self.ana_proje.id).order_by(ProjectTasks.sira, ProjectTasks.id)
        )).scalars().all())
        idler = [g.id for g in self.gorevler if g.musteriye_gorunur]
        if idler:
            for k in (await self.db.execute(select(TaskChecklist).where(TaskChecklist.gorev_id.in_(idler)))).scalars().all():
                self.kontroller.setdefault(k.gorev_id, []).append(k)

    @property
    def etkin_projeler(self) -> List[Any]:
        return sorted((p for p in self.projeler if _proje_acik(p)), key=_proje_sira_anahtari, reverse=True)


def _yuzde(p: Any) -> Optional[int]:
    if p.progress is None:
        return None
    try:
        return max(0, min(100, int(p.progress)))
    except (TypeError, ValueError):
        return None


def _tamam(g: Any) -> bool:
    return (g.durum or "") == "tamam"


def _kapanis(g: Any) -> Optional[datetime]:
    """Görevin tamamlandığı an (tamamsa); tamamlanma zamanı yazılmamışsa son güncelleme."""
    if not _tamam(g):
        return None
    return utc(g.tamamlandi_at) or utc(g.updated_at) or utc(g.created_at)


def _gorev_ozeti(g: Any) -> Dict[str, Any]:
    return {"id": g.id, "baslik": g.baslik, "tarih": _gun(g.bitis_tarihi).isoformat() if g.bitis_tarihi else None,
            "kilometre_tasi": bool(g.kilometre_tasi)}


def siradaki_teslim(c: Baglam) -> Optional[Dict[str, Any]]:
    if not c.gorev_okunur:
        return None
    adaylar = [g for g in c.gorunur_gorevler if not _tamam(g) and g.bitis_tarihi]
    if not adaylar:
        return None
    g = min(adaylar, key=lambda x: (_gun(x.bitis_tarihi), x.sira or 0, x.id))
    return _gorev_ozeti(g)


def son_teslim(c: Baglam) -> Optional[Dict[str, Any]]:
    if not c.gorev_okunur:
        return None
    biten = [(k, g) for g in c.gorunur_gorevler if (k := _kapanis(g)) is not None]
    if not biten:
        return None
    k, g = max(biten, key=lambda x: (x[0], x[1].id))
    return {"id": g.id, "baslik": g.baslik, "tarih": tr_gun(k).isoformat(), "kilometre_tasi": bool(g.kilometre_tasi)}


# ---------------------------------------------------------------------------
# Kalemler
# ---------------------------------------------------------------------------
async def karsilama_hesapla(c: Baglam, onay_sayisi: Optional[int]) -> Dict[str, Any]:
    from models.auth import User
    from services.hesap_ekibi import hesap_adlari

    ad = (await c.db.execute(select(User.name).where(func.lower(User.email) == c.kisi).limit(1))).scalar() if c.kisi else None
    hesap_adi = (await hesap_adlari(c.db, [c.hesap])).get(c.hesap) if c.hesap else None
    p = c.ana_proje
    return {
        "hitap": hitap(ad),
        "hesap_adi": hesap_adi,
        "proje": {"id": p.id, "baslik": p.title, "yuzde": _yuzde(p), "kategori": p.category or None} if p is not None else None,
        "siradaki": siradaki_teslim(c),
        "onay_sayisi": onay_sayisi,
    }


def _grup_halkalari(c: Baglam) -> Tuple[str, List[Dict[str, Any]], int]:
    gorunur = c.gorunur_gorevler
    idler = {g.id for g in gorunur}
    altlar: Dict[int, List[Any]] = {}
    for g in gorunur:
        if g.ust_gorev_id in idler:
            altlar.setdefault(g.ust_gorev_id, []).append(g)
    gruplar = [g for g in gorunur if g.id in altlar]
    if gruplar:
        halkalar = []
        for g in gruplar:
            cocuk = altlar[g.id]
            tamam = sum(1 for x in cocuk if _tamam(x))
            halkalar.append({"id": g.id, "ad": g.baslik, "tamam": tamam, "toplam": len(cocuk),
                             "yuzde": round(tamam * 100 / len(cocuk))})
        return "grup", halkalar[:HALKA_SAYISI], len(gruplar)
    tas = sorted((g for g in gorunur if g.kilometre_tasi), key=lambda g: (_gun(g.bitis_tarihi) or date.max, g.sira or 0, g.id))
    if tas:
        halkalar = []
        for g in tas:
            liste = c.kontroller.get(g.id, [])
            if liste:
                tamam, toplam = sum(1 for k in liste if k.tamam), len(liste)
            else:
                tamam, toplam = (1 if _tamam(g) else 0), 1
            halkalar.append({"id": g.id, "ad": g.baslik, "tamam": tamam, "toplam": toplam,
                             "yuzde": round(tamam * 100 / toplam) if toplam else 0,
                             "tarih": _gun(g.bitis_tarihi).isoformat() if g.bitis_tarihi else None})
        return "kilometre", halkalar[:HALKA_SAYISI], len(tas)
    return "", [], 0


async def proje_ilerleme_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    if not c.izin("projeler"):
        return None
    etkin = c.etkin_projeler
    if not etkin:
        return None
    tur, halkalar, sayi = _grup_halkalari(c) if c.gorev_okunur else ("", [], 0)
    if not halkalar:
        tur = "proje"
        halkalar = [{"id": p.id, "ad": p.title, "yuzde": _yuzde(p), "tamam": None, "toplam": None} for p in etkin[:HALKA_SAYISI]]
        sayi = len(etkin)
    p = c.ana_proje
    return {
        "tur": tur,
        "proje": {"id": p.id, "baslik": p.title} if p is not None and tur != "proje" else None,
        "halkalar": halkalar,
        "kalem_sayisi": sayi,
        "son_teslim": son_teslim(c),
        "siradaki": siradaki_teslim(c),
    }


def acik_sayisi(gorevler: Sequence[Any], an: datetime) -> int:
    """`an` anında açık (oluşmuş, henüz tamamlanmamış) görev sayısı."""
    n = 0
    for g in gorevler:
        bas = utc(g.created_at)
        if bas is None or bas > an:
            continue
        k = _kapanis(g)
        if k is None or k > an:
            n += 1
    return n


async def kalan_is_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    if c.ana_proje is None or not c.gorev_okunur:
        return None
    gorevler = c.gorunur_gorevler
    if not gorevler:
        return None
    gunler = son_gunler(c.bugun, GUN_SAYISI)
    sonlar = [min(c.an, gun_basi(g + timedelta(days=1)) - timedelta(microseconds=1)) for g in gunler]
    gercek = [acik_sayisi(gorevler, s) for s in sonlar]
    kalan = gercek[-1]

    plan: Optional[List[Optional[float]]] = None
    fark: Optional[int] = None
    bitisler = [d for g in gorevler if (d := _gun(g.bitis_tarihi)) is not None]
    bas_an = utc(c.ana_proje.created_at) or min((utc(g.created_at) for g in gorevler if g.created_at), default=None)
    baslangic = tr_gun(bas_an) if bas_an is not None else None
    bitis = max(bitisler) if bitisler else None
    kapsam = len(gorevler)
    if baslangic is not None and bitis is not None and bitis > baslangic and kapsam > 0:
        sure = (bitis - baslangic).days

        def plan_degeri(gun: date) -> Optional[float]:
            if gun < baslangic:
                return None
            oran = max(0.0, min(1.0, (bitis - gun).days / sure))
            return round(kapsam * oran, 2)

        plan = [plan_degeri(g) for g in gunler]
        # Planın bugünkü açık sayıya ulaştığı gün (doğrusal: bitiş − kalan × süre / kapsam) − bugün:
        # + önde (o seviyeye plandan önce gelindi), − geride.
        fark = round((bitis - c.bugun).days - sure * kalan / kapsam)
    return {
        "proje_id": c.ana_proje.id,
        "gunler": [g.isoformat() for g in gunler],
        "gercek": gercek,
        "plan": plan,
        "kalan": kalan,
        "toplam": kapsam,
        "plan_baslangic": baslangic.isoformat() if plan is not None and baslangic else None,
        "plan_bitis": bitis.isoformat() if plan is not None and bitis else None,
        "plan_farki_gun": fark,
    }


async def ort_yanit_dk(c: Baglam) -> Optional[int]:
    """Son 90 günde müşteri mesajından sonraki ilk ajans yanıtına geçen ortalama süre (dakika)."""
    from models.mesajlar import KonusmaMesajlari, Konusmalar

    konusmalar = [k for (k,) in (await c.db.execute(select(Konusmalar.id).where(Konusmalar.hesap_email == c.hesap))).all()]
    if not konusmalar:
        return None
    sinir = c.an - timedelta(days=MESAJ_GUN)
    satirlar = (await c.db.execute(
        select(KonusmaMesajlari.konusma_id, KonusmaMesajlari.yazan_rol, KonusmaMesajlari.created_at)
        .where(KonusmaMesajlari.konusma_id.in_(konusmalar), KonusmaMesajlari.created_at >= sinir - timedelta(days=1))
        .order_by(KonusmaMesajlari.konusma_id, KonusmaMesajlari.id)
    )).all()
    sureler: List[float] = []
    bekleyen: Dict[int, datetime] = {}
    for kid, rol, an in satirlar:
        an = utc(an)
        if an is None or an < sinir:
            continue
        if rol == "client":
            bekleyen.setdefault(kid, an)
        elif rol == "admin" and kid in bekleyen:
            sureler.append((an - bekleyen.pop(kid)).total_seconds() / 60)
    if not sureler:
        return None
    return max(1, round(sum(sureler) / len(sureler)))


async def ekip_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    from models.staff import Staff

    if c.ana_proje is None or not c.izin("projeler"):
        return None
    sayac: Dict[str, int] = {}
    for g in c.gorevler:
        e = eposta(g.atanan)
        if e:
            sayac[e] = sayac.get(e, 0) + (0 if _tamam(g) else 1) + 1
    if not sayac:
        return None
    kisiler = (await c.db.execute(select(Staff).where(func.lower(Staff.email).in_(list(sayac))))).scalars().all()
    liste = []
    for s in kisiler:
        if s.aktif is False:
            continue
        hizmetler = [h.strip() for h in (s.hizmetler or "").split(",") if h.strip()]
        liste.append((sayac.get(eposta(s.email), 0), {
            "ad": kisa_ad(s.ad) or bas_harf(s.ad, s.email),
            "bas_harf": bas_harf(s.ad, s.email),
            "hizmet": hizmetler[0] if hizmetler else None,
            "rol": (s.rol or "calisan") if (s.rol or "calisan") in ("yonetici", "calisan") else "calisan",
        }))
    if not liste:
        return None
    liste.sort(key=lambda x: (-x[0], x[1]["ad"]))
    mesaj = c.acik("mesajlar") and c.izin("mesajlar")
    return {
        "kisiler": [x[1] for x in liste[:EKIP_SAYISI]],
        "ort_yanit_dk": await ort_yanit_dk(c) if mesaj else None,
    }


# ---------------------------------------------------------------------------
# Onay bekleyenler
# ---------------------------------------------------------------------------
def _oge(tur: str, kimlik: int, baslik: str, tarih: Any, eylemler: Iterable[str], **ek: Any) -> Dict[str, Any]:
    return {"tur": tur, "id": kimlik, "baslik": baslik, "tarih": iso(tarih) if isinstance(tarih, datetime) else tarih,
            "eylemler": list(eylemler), **ek}


async def _imzali_islemler(c: Baglam) -> List[Dict[str, Any]]:
    from models.signed_actions import SignedActions
    from services import imzali_islem as ii

    if not c.acik("islem"):
        return []
    turler = [t for t, izin in (("teslimat_onay", "projeler"), ("teklif_kabul", "faturalar")) if c.izin(izin)]
    if not turler:
        return []
    satirlar = (await c.db.execute(select(SignedActions).where(
        SignedActions.alici_eposta == c.hesap, SignedActions.durum == "bekliyor", SignedActions.son_kullanma > c.an,
        SignedActions.tur.in_(turler)).order_by(SignedActions.son_kullanma.asc()).limit(20))).scalars().all()
    sonuc = []
    for k in satirlar:
        a = ii.ayrinti(k)
        if k.tur == "teslimat_onay":
            sonuc.append(_oge("teslimat", k.id, a.get("proje") or k.baslik, utc(k.created_at), ("onay", "revizyon"),
                              asama=a.get("asama"), son_kullanma=iso(k.son_kullanma), **{"not": a.get("not")}))
        else:
            sonuc.append(_oge("teklif_kabul", k.id, k.baslik, utc(k.created_at), ("kabul", "red"),
                              tutar=a.get("tutar"), para_birimi=a.get("para_birimi"), son_kullanma=iso(k.son_kullanma)))
    return sonuc


async def _icerik_onaylari(c: Baglam) -> List[Dict[str, Any]]:
    from models.content_posts import Content_posts
    from models.signed_actions import SignedActions
    from services import icerik_planlayici as pl

    if not c.izin("icerik"):
        return []
    kayitlar = (await c.db.execute(
        select(Content_posts, SignedActions).join(SignedActions, SignedActions.id == Content_posts.onay_islem_id).where(
            Content_posts.hesap_email == c.hesap, Content_posts.status == "musteri_onayi",
            SignedActions.durum == "bekliyor", SignedActions.son_kullanma > c.an, SignedActions.tur == "icerik_onay",
        ).order_by(SignedActions.son_kullanma.asc()).limit(20))).all()
    sonuc = []
    for g, k in kayitlar:
        try:
            gorsel = len(pl._gorsel_listesi(g))  # noqa: SLF001 - aynı önizleme kuralı
        except Exception:  # noqa: BLE001
            gorsel = 0
        try:
            kanallar = pl.kanal_listesi(g)
        except Exception:  # noqa: BLE001
            kanallar = []
        kelime = len((g.body or "").split())
        sonuc.append(_oge("icerik", g.id, g.title, utc(k.created_at), ("onay", "revizyon"), gorsel=gorsel,
                          kelime=kelime or None, kanallar=list(kanallar)[:4], son_kullanma=iso(k.son_kullanma)))
    return sonuc


async def _teklif_kararlari(c: Baglam) -> List[Dict[str, Any]]:
    from models.teklifler import Teklifler
    from services import teklifler as ts
    from sqlalchemy import and_, or_

    if not (c.izin("faturalar") and c.acik("teklifler")):
        return []
    satirlar = (await c.db.execute(select(Teklifler).where(
        or_(Teklifler.hesap_email == c.hesap, and_(Teklifler.hesap_email.is_(None), Teklifler.aday_eposta == c.hesap)),
        Teklifler.durum.in_(ts.ACIK_DURUMLAR)).order_by(Teklifler.id.desc()).limit(20))).scalars().all()
    sonuc = []
    for t in satirlar:
        if not t.islem_id or ts.suresi_gecti_mi(t, c.bugun):
            continue
        sonuc.append(_oge("teklif", t.id, t.baslik, utc(t.gonderildi_at) or utc(t.created_at), ("incele",),
                          kod=t.no, tutar=float(t.genel_toplam or 0), para_birimi=t.para_birimi or "TRY",
                          gecerlilik=t.gecerlilik or None))
    return sonuc


async def _sozlesme_imzalari(c: Baglam) -> List[Dict[str, Any]]:
    from models.sozlesmeler import Sozlesmeler
    from sqlalchemy import and_, or_

    if not (c.izin("faturalar") and c.acik("sozlesmeler")):
        return []
    satirlar = (await c.db.execute(select(Sozlesmeler).where(
        or_(Sozlesmeler.hesap_email == c.hesap, and_(Sozlesmeler.hesap_email.is_(None), Sozlesmeler.taraf_eposta == c.hesap)),
        Sozlesmeler.durum == "gonderildi").order_by(Sozlesmeler.id.desc()).limit(20))).scalars().all()
    return [_oge("sozlesme", s.id, s.baslik, utc(getattr(s, "gonderildi_at", None)) or utc(s.created_at), ("incele",),
                 kod=s.no) for s in satirlar]


async def _belge_onaylari(c: Baglam) -> List[Dict[str, Any]]:
    from models.belgeler import Belgeler

    if not c.izin("belgeler", "dosyalar"):
        return []
    satirlar = (await c.db.execute(select(Belgeler).where(
        func.coalesce(Belgeler.sahip_hesap, "") == "", Belgeler.gorunurluk == "paylasilan", Belgeler.musteri_email == c.hesap,
    ).order_by(Belgeler.id.desc()).limit(50))).scalars().all()
    sonuc = []
    for b in satirlar:
        if b.okundu_surum is not None and int(b.okundu_surum) == int(b.surum or 1):
            continue
        sonuc.append(_oge("belge", b.id, b.baslik, utc(b.paylasildi_at) or utc(b.updated_at) or utc(b.created_at),
                          ("okundu",), belge_turu=b.tur, surum=int(b.surum or 1)))
    return sonuc


async def onay_bekleyen_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    if not c.izin("projeler", "faturalar", "icerik", "belgeler", "dosyalar"):
        return None
    ogeler: List[Dict[str, Any]] = []
    for kaynak in (_imzali_islemler, _icerik_onaylari, _teklif_kararlari, _sozlesme_imzalari, _belge_onaylari):
        bulunan = await _kalem(kaynak.__name__, lambda k=kaynak: k(c), c.db)
        ogeler.extend(bulunan or [])
    # Önce en yeni; sonra (kararlı sıralama) süresi yaklaşan önce — süresizler sonda.
    ogeler.sort(key=lambda o: o.get("tarih") or "", reverse=True)
    ogeler.sort(key=lambda o: o.get("son_kullanma") or "9999")
    revizyon = None
    if c.gorev_okunur and any(o["tur"] in ("teslimat", "icerik") for o in ogeler):
        revizyon = await _kalem("revizyon", lambda: _revizyon(c), c.db)
    return {"toplam": len(ogeler), "ogeler": ogeler[:ONAY_SAYISI], "revizyon": revizyon}


async def _revizyon(c: Baglam) -> Optional[Dict[str, Any]]:
    from services.gorevler import revizyon_sayaci

    s = await revizyon_sayaci(c.db, c.hesap)
    if s.get("hak") is None:
        return None
    return {"hak": s["hak"], "kalan": s["kalan"], "kullanilan": s["kullanilan"], "asildi": bool(s.get("asildi"))}


# ---------------------------------------------------------------------------
# Toplantı, hedef, bakiye, faturalar, destek
# ---------------------------------------------------------------------------
async def toplanti_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    from models.toplantilar import Toplantilar
    from services import toplantilar as ts

    if not c.izin("projeler"):
        return None
    adaylar = (await c.db.execute(select(Toplantilar).where(
        Toplantilar.hesap_email == c.hesap, Toplantilar.durum.in_(("planlandi", "ertelendi")),
        Toplantilar.baslangic >= c.an - timedelta(days=1)).order_by(Toplantilar.baslangic.asc()).limit(10))).scalars().all()
    t = next((x for x in adaylar if ts.bitis(x) > c.an), None)
    if t is None:
        return None
    ks = (await ts.toplu_katilimcilar(c.db, [t.id])).get(int(t.id), [])
    ben = next((k for k in ks if k.eposta == c.kisi), None)
    gorunen = [k for k in ks if k.tur == "ekip" or ben is not None]
    bas = utc(t.baslangic)
    bit = ts.bitis(t)
    katil = None
    if t.yer_turu == "cevrimici" and t.baglanti and bas is not None and bas - KATIL_ONCE <= c.an <= bit:
        katil = t.baglanti
    return {
        "id": t.id,
        "baslik": t.baslik,
        "baslangic": iso(bas),
        "bitis": iso(bit),
        "sure_dk": t.sure_dk,
        "yer_turu": t.yer_turu,
        "durum": t.durum,
        "katilimcilar": [{"bas_harf": bas_harf(k.ad, k.eposta), "tur": k.tur, "ben": k.eposta == c.kisi} for k in gorunen][:6],
        "katilimci_sayisi": len(gorunen),
        "katilimci_miyim": ben is not None,
        "yanitim": ben.yanit if ben is not None else None,
        "katil_baglantisi": katil,
        "katil_yakinda": t.yer_turu == "cevrimici" and bool(t.baglanti) and katil is None,
    }


def _donem(d: Any) -> Dict[str, Any]:
    return {"ad": d.ad or "", "tur": d.tur, "yil": d.yil, "ceyrek": d.ceyrek, "baslangic": d.baslangic.isoformat(),
            "bitis": d.bitis.isoformat()}


async def _hedef_sec(c: Baglam, hedefler: Sequence[Any], kaynak: str) -> Optional[Dict[str, Any]]:
    from models.okr import OkrDonemler
    from services import okr as s
    from services import okr_kayit as k

    if not hedefler:
        return None
    donemler = {d.id: d for d in (await c.db.execute(select(OkrDonemler).where(
        OkrDonemler.id.in_({h.donem_id for h in hedefler})))).scalars().all()}
    aday = []
    for h in hedefler:
        d = donemler.get(h.donem_id)
        if d is None or d.kapsam != h.kapsam:
            continue
        kapsiyor = d.baslangic <= c.bugun <= d.bitis
        aday.append((0 if kapsiyor else 1, -(d.baslangic.toordinal()), int(h.sira or 0), h.id, h, d))
    if not aday:
        return None
    aday.sort(key=lambda x: x[:4])
    _, _, _, _, h, d = aday[0]
    krler = (await k.krler_haritasi(c.db, [h.id])).get(h.id, [])
    beklenen = s.beklenen_ilerleme(d.baslangic, d.bitis, c.bugun)
    x = k.hedef_sozlugu(h, krler, beklenen, paylasim=True)
    return {
        "kaynak": kaynak,
        "id": h.id,
        "baslik": h.baslik,
        "donem": _donem(d),
        "beklenen": round(beklenen, 4),
        "ilerleme": x["ilerleme"],
        "durum": x["durum_rengi"],
        "krler": [{"id": kr["id"], "baslik": kr["baslik"], "ilerleme": kr["ilerleme"]} for kr in x["krler"][:KR_SAYISI]],
        "kr_sayisi": len(x["krler"]),
        "toplam": len(aday),
    }


async def hedef_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    from models.okr import OkrHedefler
    from services import okr as s

    # 1) Ajansın bu hesapla PAYLAŞTIĞI etkin hedef (6O: modül gerekmez; izin projeler / hedefler / hedefler_okur).
    if c.izin("projeler", s.IZIN, s.IZIN_OKUR):
        paylasilan = (await c.db.execute(select(OkrHedefler).where(
            OkrHedefler.kapsam == s.AJANS_KAPSAMI, OkrHedefler.musteri_email == c.hesap,
            OkrHedefler.musteri_paylasim.is_(True), OkrHedefler.gorunurluk == "ekip", OkrHedefler.durum == "etkin",
        ).limit(50))).scalars().all()
        sonuc = await _hedef_sec(c, paylasilan, "ajans")
        if sonuc is not None:
            return sonuc
    # 2) Hesabın kendi etkin hedefi — modül açık + izin; YALNIZ ekip görünürlüklü (özel hedef asla).
    if c.acik(s.MODUL) and c.izin(s.IZIN, s.IZIN_OKUR) and c.hesap:
        kendi = (await c.db.execute(select(OkrHedefler).where(
            OkrHedefler.kapsam == s.kapsam_anahtari(c.hesap), OkrHedefler.gorunurluk == "ekip", OkrHedefler.durum == "etkin",
        ).limit(50))).scalars().all()
        return await _hedef_sec(c, kendi, "kendi")
    return None


async def bakiye_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    from models.cuzdan import CuzdanHesaplari, CuzdanYuklemeTalepleri
    from services import cuzdan as cz

    if not c.izin("faturalar") or not c.hesap:
        return None
    cuzdanlar = (await c.db.execute(select(CuzdanHesaplari).where(CuzdanHesaplari.hesap_email == c.hesap)
                                    .order_by(CuzdanHesaplari.para_birimi))).scalars().all()
    bekleyen = int((await c.db.execute(select(func.count(CuzdanYuklemeTalepleri.id)).where(
        CuzdanYuklemeTalepleri.hesap_email == c.hesap, CuzdanYuklemeTalepleri.durum == "beklemede"))).scalar() or 0)
    ayar = await cz.ayar_al(c.db, c.hesap, olustur=False)
    otomatik = bool(ayar.otomatik_odeme) if ayar is not None else False
    if not cuzdanlar and not bekleyen and not otomatik:
        return None
    return {
        "bakiyeler": [{"para_birimi": x.para_birimi, "bakiye": cz.tl(x.bakiye)} for x in cuzdanlar],
        "otomatik_odeme": otomatik,
        "bekleyen_yukleme": bekleyen,
    }


async def faturalar_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    from models.cuzdan import CuzdanHesaplari
    from models.invoices import Invoices
    from models.payments import Payments
    from services import cuzdan as cz
    from services import faturalar as fs
    from sqlalchemy import or_

    if not c.izin("faturalar") or not c.hesap:
        return {"acik_sayisi": 0, "ogeler": []} if c.izin("faturalar") else None
    satirlar = (await c.db.execute(select(Invoices).where(
        func.lower(Invoices.client_email) == c.hesap,
        or_(Invoices.status.is_(None), Invoices.status.notin_(fs.KAPALI_DURUMLAR)),
        or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
    ).order_by(Invoices.id.desc()).limit(50))).scalars().all()
    if not satirlar:
        return {"acik_sayisi": 0, "ogeler": []}
    idler = [f.id for f in satirlar]
    odemeler: Dict[int, List[Any]] = {}
    for o in (await c.db.execute(select(Payments).where(Payments.invoice_id.in_(idler)))).scalars().all():
        odemeler.setdefault(o.invoice_id, []).append(o)
    iadeler: Dict[int, List[Any]] = {}
    for f in (await c.db.execute(select(Invoices).where(Invoices.bagli_fatura_id.in_(idler), Invoices.tur == "iade"))).scalars().all():
        iadeler.setdefault(f.bagli_fatura_id, []).append(f)
    bakiyeler = {x.para_birimi: int(x.bakiye or 0) for x in (await c.db.execute(
        select(CuzdanHesaplari).where(CuzdanHesaplari.hesap_email == c.hesap))).scalars().all()}
    acik = []
    for f in satirlar:
        b = fs.bakiye_hesapla(f, odemeler.get(f.id, []), iadeler.get(f.id, []))
        if b.kalan <= fs.EPS:
            continue
        pb = (f.currency or "TRY").upper()
        kalan_kurus = cz.kurusa(b.kalan)
        bekleyen = next((o for o in reversed(odemeler.get(f.id, [])) if o.durum == "bekliyor" and o.jeton), None)
        vade = _gun(f.due_date)
        acik.append({
            "id": f.id,
            "kod": f.invoice_no,
            "kalan": float(b.kalan),
            "toplam": float(fs.D(f.amount)),
            "para_birimi": pb,
            "vade": vade.isoformat() if vade else None,
            "durum": f.status or "unpaid",
            "gecikmis": bool(vade and vade < c.bugun),
            "bakiyeden": bakiyeler.get(pb, 0) >= kalan_kurus > 0,
            "odeme_adresi": f"/ode/{bekleyen.jeton}" if bekleyen is not None else None,
        })
    acik.sort(key=lambda x: (x["vade"] or "9999-12-31", x["id"]))
    return {"acik_sayisi": len(acik), "ogeler": acik[:FATURA_SAYISI]}


async def destek_hesapla(c: Baglam) -> Optional[Dict[str, Any]]:
    from models.support_tickets import Support_tickets
    from models.ticket_replies import Ticket_replies

    if not c.izin("destek"):
        return None
    if not c.hesap:
        return {"acik_sayisi": 0, "ogeler": []}
    talepler = (await c.db.execute(select(Support_tickets).where(
        func.lower(Support_tickets.client_email) == c.hesap,
        func.coalesce(Support_tickets.status, "open").notin_(list(sla.KAPALI_DURUMLAR)),
    ).order_by(Support_tickets.id.desc()).limit(50))).scalars().all()
    if not talepler:
        return {"acik_sayisi": 0, "ogeler": []}
    son_yazan: Dict[int, str] = {}
    for tid, yazan in (await c.db.execute(select(Ticket_replies.ticket_id, Ticket_replies.yazan).where(
            Ticket_replies.ticket_id.in_([t.id for t in talepler])).order_by(Ticket_replies.ticket_id, Ticket_replies.id))).all():
        son_yazan[tid] = yazan
    liste = []
    for t in talepler:
        durum = (t.status or "open").strip().lower()
        bekliyor = durum == "answered" or son_yazan.get(t.id) == "ajans"
        an = utc(t.son_mesaj_at) or utc(t.updated_at) or utc(t.created_at)
        liste.append((0 if bekliyor else 1, -(an.timestamp() if an else 0), {
            "id": t.id, "kod": f"D-{t.id}", "baslik": t.subject, "durum": durum, "yanit_bekliyor": bekliyor,
            "tarih": iso(an),
        }))
    liste.sort(key=lambda x: x[:2])
    return {"acik_sayisi": len(liste), "ogeler": [x[2] for x in liste[:DESTEK_SAYISI]]}


# ---------------------------------------------------------------------------
# Hepsi
# ---------------------------------------------------------------------------
async def musteri_ozeti(db: AsyncSession, baglam: HesapBaglami, an: Optional[datetime] = None) -> Dict[str, Any]:
    an = utc(an) or sla.simdi()
    c = Baglam(db, baglam, an)
    await c.hazirla()
    onay = await _kalem("onayBekleyen", lambda: onay_bekleyen_hesapla(c), db)
    return {
        "olusturma": an.isoformat(),
        "hesap": {"kendi": baglam.kendi_hesabi, "rol": baglam.rol},
        "karsilama": await _kalem("karsilama", lambda: karsilama_hesapla(c, onay["toplam"] if onay else None), db),
        "projeIlerleme": await _kalem("projeIlerleme", lambda: proje_ilerleme_hesapla(c), db),
        "kalanIs": await _kalem("kalanIs", lambda: kalan_is_hesapla(c), db),
        "ekip": await _kalem("ekip", lambda: ekip_hesapla(c), db),
        "onayBekleyen": onay,
        "toplanti": await _kalem("toplanti", lambda: toplanti_hesapla(c), db),
        "hedef": await _kalem("hedef", lambda: hedef_hesapla(c), db),
        "bakiye": await _kalem("bakiye", lambda: bakiye_hesapla(c), db),
        "faturalar": await _kalem("faturalar", lambda: faturalar_hesapla(c), db),
        "destek": await _kalem("destek", lambda: destek_hesapla(c), db),
    }
