"""Faz 6R — hazır sektör ayarlarını uygulama (yalnız boş yerlere) ve geri alma.

Set tanımları `core/sektor_ayarlari.py`'de; burası onları müşterinin modüllerine
yazıyor. Her modül için bir "uygulayıcı" var; hepsi aynı iki kipte çalışıyor:

* **kuru** (önizleme): veritabanına yazmaz, "ne oluşturulacak / neden atlanacak"
  listesini üretir (yönetim ekranındaki önizleme).
* **gerçek**: kayıtları oturuma ekler ve `flush` eder, COMMIT ETMEZ — çağıran
  (`services/sektor_paketi.py`) modül açma + hazır ayar + günlük + denetimi TEK
  işlemde onaylar; bir şey patlarsa hepsi geri alınır.

Kurallar
--------
* Var olan veri ASLA ezilmez. Hesabın randevu sayfası varsa sayfaya/saatlere
  dokunulmaz; sayfada tür varsa tür eklenmez; asistan/kartvizit/dizi/mağaza
  varsa yenisi açılmaz; yorum sayfasının teşekkür metni yalnız BOŞSA doldurulur.
* Uydurma yok: kişi/işletme adı ve adres yalnız yöneticinin önizlemede yazdığı
  değerden (`isletme_adi`, `adres`); yoksa ad isteyen kayıt (kartvizit) atlanır,
  adres isteyen yüz yüze randevu türü PASİF oluşturulur (adres girilince açılır).
  Google yorum sayfası Place ID istediği için oluşturulmaz; teşekkür metni önerisi
  önizlemede görünür.
* Yayına çıkmayan taslaklar: AI asistan pasif (müşteri SSS'yi gözden geçirip
  açar), kartvizit pasif, QR menü mağazası pasif, e-posta dizisi pasif (gönderilmez).
* Modül kapalıysa o modüle yazılmaz (`modul_kapali`).

Günlük ve geri alma
-------------------
Oluşturulan her kayıt `{modul, tablo, id, iz, etiket}` olarak günlüğe yazılıyor;
`iz` içeriğin özeti (tarih alanları ve sistemin kendi değiştirdiği sayaçlar
hariç). `geri_al` kayıtları TERS sırayla dolaşır: içerik aynıysa (el değmemiş)
ve kayda bağlı başka veri yoksa (rezervasyon, sohbet, mesaj, ürün, abone…)
siler; değiştiyse ya da kullanılıyorsa korur ve nedenini yazar. Doldurulan
alan aynı değerdeyse boşaltılır.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core import sektor_ayarlari as sa
from sqlalchemy import Date, DateTime, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Parmak izine girmeyen sütunlar (tablo → ad kümesi): sistemin kendi güncellediği sayaç/durumlar.
_IZ_HARIC: Dict[str, Set[str]] = {
    "*": {"id", "updated_at", "created_at"},
    "ai_asistanlar": {"dizin_surumu"},
    "ai_asistan_kaynaklari": {"durum", "hata", "parca_sayisi", "karakter", "sayfa_sayisi"},
    "randevu_kisileri": {"kilit"},
}


class HazirAyarHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def json_yaz(d: Any) -> str:
    return json.dumps(d, ensure_ascii=False)


def json_oku(ham: Any, varsayilan: Any) -> Any:
    try:
        d = json.loads(ham) if ham else varsayilan
    except (TypeError, ValueError):
        return varsayilan
    return d if d is not None else varsayilan


def parmak_izi(nesne: Any) -> str:
    """Kaydın içerik özeti (oluşturma anı ile geri alma anını karşılaştırmak için)."""
    tablo = nesne.__table__
    haric = _IZ_HARIC["*"] | _IZ_HARIC.get(tablo.name, set())
    veri: Dict[str, Any] = {}
    for sutun in tablo.columns:
        if sutun.name in haric or isinstance(sutun.type, (DateTime, Date)):
            continue
        veri[sutun.name] = getattr(nesne, sutun.key)
    return hashlib.sha256(json.dumps(veri, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:32]


def deger_izi(deger: Any) -> str:
    return hashlib.sha256(json.dumps(deger, default=str, ensure_ascii=False).encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Bağlam
# ---------------------------------------------------------------------------
@dataclass
class Baglam:
    db: AsyncSession
    hesap: str
    set: sa.HazirSet
    #: Hesabın dili (kayıtların dil alanı) ve başlangıç içeriğinin dili (tr | en).
    dil: str
    idil: str
    #: Uygulayan (yönetici e-postası) — `olusturan` alanları.
    kisi: str
    #: Veri yazılabilecek (açık / açılacak) modüller.
    acik: Set[str]
    kuru: bool
    isletme_adi: str = ""
    adres: str = ""
    an: datetime = field(default_factory=simdi)
    #: Oluşturulan kayıtlar ve doldurulan alanlar (günlük).
    kayitlar: List[Dict[str, Any]] = field(default_factory=list)
    #: Önizleme / sonuç: modül başına öğeler.
    plan: List[Dict[str, Any]] = field(default_factory=list)
    uyarilar: List[str] = field(default_factory=list)
    #: Uygulayıcılar arası paylaşım (randevu sayfası adresi → kartvizit bağlantısı).
    paylasim: Dict[str, Any] = field(default_factory=dict)
    #: Commit'ten SONRA yapılacaklar (AI kaynağını dizine işleme).
    sonradan: List[Tuple[str, int]] = field(default_factory=list)

    def metin(self, m: sa.Metin) -> str:
        return m[self.idil]

    def bolum(self, modul: str) -> Dict[str, Any]:
        b = {"modul": modul, "ogeler": [], "atlanan": []}
        self.plan.append(b)
        return b

    def uyar(self, kod: str) -> None:
        if kod not in self.uyarilar:
            self.uyarilar.append(kod)

    async def kaydet(self, bolum: Dict[str, Any], nesne: Any, tur: str, ad: str, **ek: Any) -> Any:
        """Kuru kipte yalnız öğe ekler; gerçek kipte oturuma ekler, flush + refresh, günlüğe yazar."""
        oge = {"tur": tur, "ad": ad, **ek}
        bolum["ogeler"].append(oge)
        if self.kuru:
            return None
        self.db.add(nesne)
        await self.db.flush()
        await self.db.refresh(nesne)
        self.kayitlar.append({
            "modul": bolum["modul"], "tablo": nesne.__tablename__, "id": int(nesne.id), "iz": parmak_izi(nesne),
            "etiket": f"{tur}: {ad}"[:160],
        })
        return nesne

    def alan_doldur(self, bolum: Dict[str, Any], nesne: Any, alan: str, deger: Any, tur: str, ad: str) -> None:
        bolum["ogeler"].append({"tur": tur, "ad": ad})
        if self.kuru:
            return
        setattr(nesne, alan, deger)
        self.kayitlar.append({
            "tur": "alan", "modul": bolum["modul"], "tablo": nesne.__tablename__, "id": int(nesne.id), "alan": alan,
            "iz": deger_izi(deger), "etiket": f"{tur}: {ad}"[:160],
        })


def _atla(bolum: Dict[str, Any], neden: str, **ek: Any) -> None:
    bolum["atlanan"].append({"neden": neden, **ek})


async def _modul_ayari(db: AsyncSession, hesap: str, modul: str, alan: str, varsayilan: int) -> int:
    from services.moduller import musteri_ayari

    d = await musteri_ayari(db, hesap, modul, alan)
    return int(d) if isinstance(d, int) and not isinstance(d, bool) else varsayilan


def _gun_ozeti(haftalik: Dict[str, List[List[str]]]) -> str:
    """Önizleme için kısa saat özeti: `0-4 09:00–18:00; 5 09:00–13:00` (gün numaraları ön yüzde adlandırılır)."""
    parcalar = []
    for g in sorted(haftalik, key=int):
        parcalar.append(f"{g}:" + ",".join(f"{a[0]}-{a[1]}" for a in haftalik[g]))
    return ";".join(parcalar)


# ---------------------------------------------------------------------------
# Uygulayıcılar
# ---------------------------------------------------------------------------
async def _randevu(b: Baglam) -> None:
    from models.randevu import RandevuKisileri, RandevuSayfalari, RandevuTurleri
    from services import randevu as rv

    r = b.set.randevu
    bolum = b.bolum("randevu")
    if "randevu" not in b.acik:
        return _atla(bolum, "modul_kapali")
    db = b.db
    sayfa = (await db.execute(select(RandevuSayfalari).where(RandevuSayfalari.hesap_email == b.hesap)
                              .order_by(RandevuSayfalari.id).limit(1))).scalars().first()
    kisi_id: Optional[int] = None
    haftalik = rv.haftalik_duzelt(r.haftalik_sozluk())
    if sayfa is None:
        baslik = (b.isletme_adi or b.metin(sa._m("Online randevu", "Online booking")))[:120]
        oneri = rv.slug_oner(baslik)
        slug = oneri
        for i in range(2, 60):
            if (await db.execute(select(RandevuSayfalari.id).where(RandevuSayfalari.slug == slug).limit(1))).first() is None:
                break
            slug = f"{oneri[:44]}-{i}"
        yeni = RandevuSayfalari(
            hesap_email=b.hesap, olusturan_email=b.kisi, slug=slug, baslik=baslik, karsilama=b.metin(r.karsilama),
            saat_dilimi=rv.VARSAYILAN_SAAT_DILIMI, dil=b.dil if b.dil in rv.DILLER else "tr",
            hatirlatmalar=rv.json_yaz(list(rv.VARSAYILAN_HATIRLATMALAR)), created_at=b.an,
        )
        sayfa = await b.kaydet(bolum, yeni, "sayfa", baslik)
        b.paylasim["randevu_slug"] = slug
        kisi = RandevuKisileri(sayfa_id=sayfa.id if sayfa else 0, eposta=b.hesap,
                               ad=(b.isletme_adi or b.hesap.split("@", 1)[0])[:120],
                               haftalik=rv.json_yaz(haftalik), sira=0, created_at=b.an)
        kisi = await b.kaydet(bolum, kisi, "saatler", _gun_ozeti(haftalik))
        kisi_id = kisi.id if kisi else None
        tur_sayisi = 0
    else:
        _atla(bolum, "sayfa_var", ad=sayfa.baslik)
        b.paylasim["randevu_slug"] = sayfa.slug
        tur_sayisi = int((await db.execute(select(func.count(RandevuTurleri.id)).where(RandevuTurleri.sayfa_id == sayfa.id))).scalar() or 0)
        kisiler = (await db.execute(select(RandevuKisileri).where(RandevuKisileri.sayfa_id == sayfa.id)
                                    .order_by(RandevuKisileri.sira, RandevuKisileri.id))).scalars().all()
        etkin = [k for k in kisiler if k.aktif] or list(kisiler)
        kisi_id = etkin[0].id if etkin else None
    if tur_sayisi:
        return _atla(bolum, "turler_var", sayi=tur_sayisi)
    if sayfa is not None and kisi_id is None and not b.kuru:
        return _atla(bolum, "kisi_yok")
    sinir = await _modul_ayari(db, b.hesap, "randevu", "tur_siniri", 5)
    turler = r.turler[:max(0, sinir)]
    if len(turler) < len(r.turler):
        _atla(bolum, "tur_siniri", sinir=sinir)
    for sira, t in enumerate(turler):
        aktif = True
        konum_degeri: Optional[str] = None
        if t.konum_turu == "yuz_yuze":
            if b.adres:
                konum_degeri = b.adres[:300]
            else:
                aktif = False
                b.uyar("adres_gerekli")
        sorular = rv.sorular_duzelt([q.sozluk(b.idil) for q in t.sorular])
        telefon = "zorunlu" if t.konum_turu == "telefon" else t.telefon
        nesne = RandevuTurleri(
            sayfa_id=sayfa.id if sayfa is not None else 0, slug=t.anahtar, ad=b.metin(t.ad), aciklama=b.metin(t.aciklama),
            sure_dk=t.sure_dk, adim_dk=t.adim_dk, konum_turu=t.konum_turu, konum_degeri=konum_degeri,
            tampon_once_dk=t.tampon_once_dk, tampon_sonra_dk=t.tampon_sonra_dk, en_erken_dk=240, en_gec_gun=60,
            kapasite=t.kapasite, telefon=telefon, sorular=rv.json_yaz(sorular), renk=t.renk, atama="kisi",
            kisiler=rv.json_yaz([kisi_id] if kisi_id else []), aktif=aktif, sira=sira, created_at=b.an,
        )
        await b.kaydet(bolum, nesne, "randevu_turu", b.metin(t.ad), sure_dk=t.sure_dk, tampon_dk=t.tampon_sonra_dk,
                       kapasite=t.kapasite, konum=t.konum_turu, aktif=aktif, soru_sayisi=len(sorular))


async def _ai_asistan(b: Baglam) -> None:
    from models.ai_asistan import AiAsistanKaynaklari, AiAsistanlar
    from services import ai_asistan as ai

    a_set = b.set.asistan
    bolum = b.bolum("ai_asistan")
    if "ai_asistan" not in b.acik:
        return _atla(bolum, "modul_kapali")
    db = b.db
    asistan = (await db.execute(select(AiAsistanlar).where(AiAsistanlar.hesap_email == b.hesap)
                                .order_by(AiAsistanlar.id).limit(1))).scalars().first()
    if asistan is None:
        alanlar = ai.ayarlari_dogrula({
            "ad": b.metin(a_set.ad), "karsilama": b.metin(a_set.karsilama), "ton": "samimi",
            "onerilen_sorular": [b.metin(x.soru) for x in a_set.sss[:a_set.onerilen_sayisi]],
            "yasakli_konular": [b.metin(x) for x in a_set.yasakli_konular], "aktif": False,
        }, yeni=True)
        nesne = AiAsistanlar(hesap_email=b.hesap, anahtar=ai.yeni_anahtar(), olusturan=b.kisi, dizin_surumu=0,
                             mesai=json_yaz(ai.mesai_dogrula(None)), **alanlar)
        asistan = await b.kaydet(bolum, nesne, "asistan", b.metin(a_set.ad), taslak=True)
        b.uyar("asistan_taslak")
        kaynak_sayisi = 0
    else:
        _atla(bolum, "asistan_var", ad=asistan.ad)
        kaynak_sayisi = int((await db.execute(select(func.count(AiAsistanKaynaklari.id))
                                              .where(AiAsistanKaynaklari.asistan_id == asistan.id))).scalar() or 0)
    if kaynak_sayisi:
        return _atla(bolum, "kaynak_var", sayi=kaynak_sayisi)
    sinirlar = await ai.hesap_sinirlari(db, b.hesap)
    if await ai.kaynak_sayisi(db, b.hesap) >= int(sinirlar["kaynak_siniri"]):
        return _atla(bolum, "kaynak_siniri", sinir=sinirlar["kaynak_siniri"])
    sss = ai.sss_dogrula([{"soru": b.metin(x.soru), "cevap": b.metin(x.cevap)} for x in a_set.sss])
    nesne = AiAsistanKaynaklari(asistan_id=asistan.id if asistan is not None else 0, hesap_email=b.hesap, tur="sss",
                                baslik=b.metin(a_set.sss_baslik), metin=json_yaz(sss), durum="isleniyor", olusturan=b.kisi)
    k = await b.kaydet(bolum, nesne, "sss", b.metin(a_set.sss_baslik), sayi=len(sss))
    if k is not None:
        b.sonradan.append(("ai_kaynak", int(k.id)))


async def _kartvizit(b: Baglam) -> None:
    from models.kartvizit import Kartvizitler
    from services import kartvizit as kv
    from services import kartvizit_kayit as kk
    from services import randevu as rv

    k_set = b.set.kartvizit
    bolum = b.bolum("dijital_kartvizit")
    if "dijital_kartvizit" not in b.acik:
        return _atla(bolum, "modul_kapali")
    db = b.db
    sayi = int((await db.execute(select(func.count(Kartvizitler.id)).where(Kartvizitler.hesap_email == b.hesap))).scalar() or 0)
    if sayi:
        return _atla(bolum, "kart_var", sayi=sayi)
    if not b.isletme_adi:
        return _atla(bolum, "ad_gerekli")
    if await _modul_ayari(db, b.hesap, "dijital_kartvizit", "kart_siniri", 5) < 1:
        return _atla(bolum, "kart_siniri")
    icerik: Dict[str, Any] = {"ad_soyad": b.isletme_adi[:100], "adres": b.adres[:300]}
    r = b.set.randevu
    if k_set.hizmetler_randevudan and r:
        birim = "dk" if b.idil == "tr" else "min"
        icerik["hizmetler"] = [{"baslik": b.metin(t.ad)[:80], "aciklama": f"{t.sure_dk} {birim}"} for t in r.turler]
    slug_r = b.paylasim.get("randevu_slug")
    if k_set.randevu_baglantisi and (slug_r or b.kuru):
        icerik["baglantilar"] = [{
            "baslik": b.metin(sa._m("Online randevu", "Book online")),
            "url": rv.sayfa_adresi(slug_r) if slug_r else "https://mehmetkuru.dev/randevu/",
            "simge": "calendar",
        }]
    if k_set.calisma_saatleri and r:
        haftalik = r.haftalik_sozluk()
        icerik["calisma_saatleri"] = {"goster": True, "not": "", "gunler": [
            {"gun": g, "acik": str(i) in haftalik,
             "acilis": haftalik[str(i)][0][0] if str(i) in haftalik else "",
             "kapanis": haftalik[str(i)][-1][1] if str(i) in haftalik else ""}
            for i, g in enumerate(kv.GUNLER)
        ]}
    try:
        temiz = kv.icerik_dogrula(icerik)
    except kv.KartHatasi:
        # Bağlantı adresi (ör. yerel ortamda http) geçmezse bağlantısız dene.
        icerik.pop("baglantilar", None)
        temiz = kv.icerik_dogrula(icerik)
    tema = kv.tema_dogrula({"sablon": k_set.sablon})
    b.uyar("kartvizit_taslak")
    if b.kuru:
        await b.kaydet(bolum, None, "kartvizit", b.isletme_adi, taslak=True, hizmet_sayisi=len(temiz["hizmetler"]))
        return
    slug = await kk.slug_onerisi(db, "kart", b.isletme_adi)
    kod = await kk.benzersiz_kod(db, "kart")
    nesne = Kartvizitler(
        hesap_email=b.hesap, olusturan_email=b.kisi, kod=kod, slug=slug, duzen="kartvizit", dil=kv.dil_duzelt(b.dil),
        ad_soyad=temiz["ad_soyad"], unvan=None, sirket=None, icerik=kv.json_dok(temiz), tema=kv.json_dok(tema),
        aktif=False, form_acik=True, index_acik=False,
    )
    await b.kaydet(bolum, nesne, "kartvizit", b.isletme_adi, taslak=True, hizmet_sayisi=len(temiz["hizmetler"]))


async def _google_yorum(b: Baglam) -> None:
    from models.kartvizit import YorumSayfalari

    bolum = b.bolum("google_yorum_sayfasi")
    metin = b.metin(b.set.yorum_tesekkur)
    if "google_yorum_sayfasi" not in b.acik:
        return _atla(bolum, "modul_kapali", oneri=metin)
    sayfalar = (await b.db.execute(select(YorumSayfalari).where(YorumSayfalari.hesap_email == b.hesap)
                                   .order_by(YorumSayfalari.id))).scalars().all()
    if not sayfalar:
        return _atla(bolum, "place_id_gerekli", oneri=metin)
    hedef = next((s for s in sayfalar if not (s.tesekkur or "").strip()), None)
    if hedef is None:
        return _atla(bolum, "metin_var")
    b.alan_doldur(bolum, hedef, "tesekkur", metin, "tesekkur_metni", hedef.isletme_adi)


async def _qr_menu(b: Baglam) -> None:
    from models.qr_menu import MenuKategorileri, MenuMagazalari
    from services import dinamik_qr as qr
    from services import qr_menu as qm

    m_set = b.set.menu
    bolum = b.bolum("qr_menu")
    if "qr_menu" not in b.acik:
        return _atla(bolum, "modul_kapali")
    db = b.db
    magaza = (await db.execute(select(MenuMagazalari).where(MenuMagazalari.hesap_email == b.hesap, MenuMagazalari.duzen == "menu")
                               .order_by(MenuMagazalari.id).limit(1))).scalars().first()
    if magaza is None:
        if await _modul_ayari(db, b.hesap, "qr_menu", "magaza_siniri", 1) < 1:
            return _atla(bolum, "magaza_siniri")
        ad = (b.isletme_adi or b.metin(sa._m("Menü", "Menu")))[:120]
        oneri = qm.slug_oner(ad)
        slug = oneri
        for i in range(2, 60):
            if (await db.execute(select(MenuMagazalari.id).where(MenuMagazalari.slug == slug).limit(1))).first() is None:
                break
            slug = f"{oneri[:44]}-{i}"
        nesne = MenuMagazalari(
            hesap_email=b.hesap, olusturan_email=b.kisi, slug=slug, duzen="menu", ad=ad, tema_rengi="#7c3aed",
            saat_dilimi=qr.VARSAYILAN_SAAT_DILIMI, para_birimi="TRY", varsayilan_dil=b.dil if b.dil in qm.DILLER else "tr",
            ek_diller="[]", siparis_ayarlari=qm.json_yaz(dict(qm.VARSAYILAN_SIPARIS_AYARLARI)),
            saklama_gun=qm.VARSAYILAN_SAKLAMA_GUN, arama_motoru=False, aktif=False, adres=(b.adres or None) and b.adres[:300],
        )
        magaza = await b.kaydet(bolum, nesne, "magaza", ad, taslak=True)
        b.uyar("menu_taslak")
    else:
        _atla(bolum, "magaza_var", ad=magaza.ad)
        sayi = int((await db.execute(select(func.count(MenuKategorileri.id)).where(MenuKategorileri.magaza_id == magaza.id))).scalar() or 0)
        if sayi:
            return _atla(bolum, "kategori_var", sayi=sayi)
    for sira, k in enumerate(m_set.kategoriler):
        ad = b.metin(k)[:80]
        nesne = MenuKategorileri(magaza_id=magaza.id if magaza is not None else 0, ad=ad, sira=sira, gizli=False)
        await b.kaydet(bolum, nesne, "kategori", ad)


async def _saha(b: Baglam) -> None:
    from models.saha_servisi import SahaAyarlari, SahaSablonlari
    from services import saha_servisi as ss

    s_set = b.set.saha
    bolum = b.bolum("saha_servisi")
    if "saha_servisi" not in b.acik:
        return _atla(bolum, "modul_kapali")
    db = b.db
    ayar = (await db.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email == b.hesap))).scalars().first()
    if ayar is None:
        nesne = SahaAyarlari(hesap_email=b.hesap, firma_adi=(b.isletme_adi or None) and b.isletme_adi[:160],
                             adres=b.adres or None, varsayilan_dil=b.dil if b.dil in ss.DILLER else "tr",
                             randevu_kancasi=s_set.randevu_kancasi, randevu_is_turu=s_set.randevu_is_turu, created_at=b.an)
        await b.kaydet(bolum, nesne, "saha_ayari", "randevu_kancasi" if s_set.randevu_kancasi else "ayar")
    else:
        _atla(bolum, "ayar_var")
    mevcut = (await db.execute(select(SahaSablonlari.is_turu, SahaSablonlari.hazir).where(SahaSablonlari.hesap_email == b.hesap))).all()
    turler = {t for t, _ in mevcut if t}
    hazirlar = {h for _, h in mevcut if h}
    for sb in s_set.sablonlar:
        if sb.anahtar in hazirlar or sb.is_turu in turler:
            _atla(bolum, "sablon_var", ad=b.metin(sb.ad))
            continue
        maddeler = ss.maddeleri_duzelt([{"id": m.kimlik, "metin": b.metin(m.metin), "tur": m.tur, "zorunlu": m.zorunlu}
                                        for m in sb.maddeler])
        nesne = SahaSablonlari(hesap_email=b.hesap, ad=b.metin(sb.ad), is_turu=sb.is_turu, maddeler=ss.json_yaz(maddeler),
                               aktif=True, hazir=sb.anahtar, created_at=b.an)
        await b.kaydet(bolum, nesne, "kontrol_listesi", b.metin(sb.ad), madde_sayisi=len(maddeler))


async def _eposta(b: Baglam) -> None:
    from models.eposta_pazarlama import EpDiziAdimlari, EpDiziler, EpListeler
    from services import eposta_icerik as ic
    from services import eposta_pazarlama as ep

    e_set = b.set.eposta
    bolum = b.bolum("eposta_pazarlama")
    if "eposta_pazarlama" not in b.acik:
        return _atla(bolum, "modul_kapali")
    db = b.db
    sayi = int((await db.execute(select(func.count(EpDiziler.id)).where(EpDiziler.hesap_email == b.hesap))).scalar() or 0)
    if sayi:
        return _atla(bolum, "dizi_var", sayi=sayi)
    liste = (await db.execute(select(EpListeler).where(EpListeler.hesap_email == b.hesap).order_by(EpListeler.id).limit(1))).scalars().first()
    if liste is None:
        nesne = EpListeler(hesap_email=b.hesap, ad=b.metin(e_set.liste_adi), aciklama=b.metin(e_set.liste_aciklama), created_at=b.an)
        liste = await b.kaydet(bolum, nesne, "liste", b.metin(e_set.liste_adi))
    else:
        _atla(bolum, "liste_var", ad=liste.ad)
    dizi = EpDiziler(hesap_email=b.hesap, ad=b.metin(e_set.dizi_adi)[:120], tetik="abonelik_onaylandi",
                     liste_id=liste.id if liste is not None else None, aktif=False,
                     cikis=ep.json_yaz({"hedef": None}), dil=ep.dil_sec(b.dil), created_at=b.an)
    dizi = await b.kaydet(bolum, dizi, "dizi", b.metin(e_set.dizi_adi), taslak=True, adim_sayisi=len(e_set.adimlar))
    b.uyar("eposta_taslak")
    for sira, a in enumerate(e_set.adimlar):
        bloklar = ic.bloklari_dogrula([{"tur": "baslik", "metin": b.metin(a.baslik), "seviye": 1},
                                       {"tur": "metin", "metin": b.metin(a.metin)}])
        nesne = EpDiziAdimlari(dizi_id=dizi.id if dizi is not None else 0, sira=sira, bekle_gun=a.bekle_gun, bekle_saat=0,
                               konu=ic.konu_duzelt(b.metin(a.konu)), onizleme_metni=b.metin(a.onizleme)[:200],
                               bloklar=ep.json_yaz(bloklar), created_at=b.an)
        await b.kaydet(bolum, nesne, "dizi_adimi", b.metin(a.konu), bekle_gun=a.bekle_gun)


async def _otomasyon(b: Baglam) -> None:
    """Kural KURULMAZ: öneriler günlükte; müşterinin Otomasyon › Hazır şablonlar'ında işaretli görünür."""
    bolum = b.bolum("otomasyon")
    for k in b.set.otomasyon:
        bolum["ogeler"].append({"tur": "oneri", "ad": k})
    if "otomasyon" not in b.acik:
        _atla(bolum, "modul_kapali_oneri")


UYGULAYICILAR: Dict[str, Callable[[Baglam], Any]] = {
    "randevu": _randevu,
    "ai_asistan": _ai_asistan,
    "dijital_kartvizit": _kartvizit,
    "google_yorum_sayfasi": _google_yorum,
    "qr_menu": _qr_menu,
    "saha_servisi": _saha,
    "eposta_pazarlama": _eposta,
    "otomasyon": _otomasyon,
}


async def uygula(b: Baglam) -> Baglam:
    """Setin bütün uygulayıcıları sırayla (kuru ya da gerçek). Commit ETMEZ."""
    if b.set.kvkk_ozel:
        b.uyar("kvkk_ozel")
    for modul in b.set.moduller():
        await UYGULAYICILAR[modul](b)
    return b


async def sonradan_isle(db: AsyncSession, isler: List[Tuple[str, int]]) -> None:
    """Commit'ten sonra: AI asistan SSS kaynaklarını dizine işle (hata yutulur; kaynak 'hata' durumunda kalır)."""
    from models.ai_asistan import AiAsistanKaynaklari, AiAsistanlar
    from services import ai_asistan as ai

    for tur, kimlik in isler:
        if tur != "ai_kaynak":
            continue
        try:
            k = await db.get(AiAsistanKaynaklari, kimlik)
            a = await db.get(AiAsistanlar, k.asistan_id) if k is not None else None
            if k is not None and a is not None:
                await ai.kaynak_isle(db, a, k)
        except Exception:  # noqa: BLE001 - kaynak sonra panelden yeniden işlenebilir
            logger.exception("Hazır SSS kaynağı işlenemedi (%s)", kimlik)
            await db.rollback()


# ---------------------------------------------------------------------------
# Geri alma
# ---------------------------------------------------------------------------
def _model(tablo: str):
    from models.ai_asistan import AiAsistanKaynaklari, AiAsistanlar
    from models.eposta_pazarlama import EpDiziAdimlari, EpDiziler, EpListeler
    from models.kartvizit import Kartvizitler, YorumSayfalari
    from models.qr_menu import MenuKategorileri, MenuMagazalari
    from models.randevu import RandevuKisileri, RandevuSayfalari, RandevuTurleri
    from models.saha_servisi import SahaAyarlari, SahaSablonlari

    return {m.__tablename__: m for m in (
        AiAsistanKaynaklari, AiAsistanlar, EpDiziAdimlari, EpDiziler, EpListeler, Kartvizitler, YorumSayfalari,
        MenuKategorileri, MenuMagazalari, RandevuKisileri, RandevuSayfalari, RandevuTurleri, SahaAyarlari, SahaSablonlari,
    )}.get(tablo)


async def _sayi(db: AsyncSession, sorgu) -> int:
    return int((await db.execute(sorgu)).scalar() or 0)


async def _kullanim_nedeni(db: AsyncSession, tablo: str, n: Any) -> Optional[str]:
    """Kayda bağlı (silinmesini engelleyen) veri varsa nedeni; yoksa None."""
    if tablo == "randevu_sayfalari":
        from models.randevu import RandevuIstisnalari, RandevuKisileri, Randevular, RandevuTurleri

        if await _sayi(db, select(func.count(Randevular.id)).where(Randevular.sayfa_id == n.id)):
            return "randevu_var"
        for model in (RandevuTurleri, RandevuKisileri, RandevuIstisnalari):
            if await _sayi(db, select(func.count(model.id)).where(model.sayfa_id == n.id)):
                return "bagli_kayit_var"
        return None
    if tablo == "randevu_turleri":
        from models.randevu import Randevular

        return "randevu_var" if await _sayi(db, select(func.count(Randevular.id)).where(Randevular.tur_id == n.id)) else None
    if tablo == "randevu_kisileri":
        from models.randevu import Randevular, RandevuTurleri

        if await _sayi(db, select(func.count(Randevular.id)).where(Randevular.kisi_id == n.id)):
            return "randevu_var"
        if await _sayi(db, select(func.count(RandevuTurleri.id)).where(RandevuTurleri.sayfa_id == n.sayfa_id)):
            return "bagli_kayit_var"
        return None
    if tablo == "ai_asistanlar":
        from models.ai_asistan import AiAsistanKaynaklari, AiAsistanSohbetleri

        if await _sayi(db, select(func.count(AiAsistanSohbetleri.id)).where(AiAsistanSohbetleri.asistan_id == n.id)):
            return "sohbet_var"
        if await _sayi(db, select(func.count(AiAsistanKaynaklari.id)).where(AiAsistanKaynaklari.asistan_id == n.id)):
            return "bagli_kayit_var"
        return None
    if tablo == "kartvizitler":
        from models.kartvizit import KartvizitGorselleri, KartvizitMesajlari

        if await _sayi(db, select(func.count(KartvizitMesajlari.id)).where(KartvizitMesajlari.sahip_tur == "kart",
                                                                           KartvizitMesajlari.sahip_id == n.id)):
            return "mesaj_var"
        if await _sayi(db, select(func.count(KartvizitGorselleri.id)).where(KartvizitGorselleri.sahip_tur == "kart",
                                                                            KartvizitGorselleri.sahip_id == n.id)):
            return "gorsel_var"
        return None
    if tablo == "menu_magazalari":
        from models.qr_menu import MenuKategorileri, MenuSiparisleri, MenuUrunleri

        if await _sayi(db, select(func.count(MenuSiparisleri.id)).where(MenuSiparisleri.magaza_id == n.id)):
            return "siparis_var"
        for model in (MenuUrunleri, MenuKategorileri):
            if await _sayi(db, select(func.count(model.id)).where(model.magaza_id == n.id)):
                return "bagli_kayit_var"
        return None
    if tablo == "menu_kategorileri":
        from models.qr_menu import MenuUrunleri

        return "urun_var" if await _sayi(db, select(func.count(MenuUrunleri.id)).where(MenuUrunleri.kategori_id == n.id)) else None
    if tablo == "saha_ayarlari":
        from models.saha_servisi import SahaIsEmirleri

        return "is_emri_var" if await _sayi(db, select(func.count(SahaIsEmirleri.id)).where(SahaIsEmirleri.hesap_email == n.hesap_email)) else None
    if tablo == "saha_sablonlari":
        from models.saha_servisi import SahaIsEmirleri

        return "is_emri_var" if await _sayi(db, select(func.count(SahaIsEmirleri.id)).where(SahaIsEmirleri.sablon_id == n.id)) else None
    if tablo == "ep_listeler":
        from models.eposta_pazarlama import EpDiziler, EpFormlar, EpListeUyelikleri

        if await _sayi(db, select(func.count(EpListeUyelikleri.id)).where(EpListeUyelikleri.liste_id == n.id)):
            return "abone_var"
        for model in (EpFormlar, EpDiziler):
            if await _sayi(db, select(func.count(model.id)).where(model.liste_id == n.id)):
                return "bagli_kayit_var"
        return None
    if tablo == "ep_diziler":
        from models.eposta_pazarlama import EpDiziAdimlari, EpDiziKayitlari

        if await _sayi(db, select(func.count(EpDiziKayitlari.id)).where(EpDiziKayitlari.dizi_id == n.id)):
            return "kayit_var"
        if await _sayi(db, select(func.count(EpDiziAdimlari.id)).where(EpDiziAdimlari.dizi_id == n.id)):
            return "bagli_kayit_var"
        return None
    if tablo == "ep_dizi_adimlari":
        from models.eposta_pazarlama import EpGonderimler

        return "gonderim_var" if await _sayi(db, select(func.count(EpGonderimler.id)).where(EpGonderimler.adim_id == n.id)) else None
    return None


async def geri_al(db: AsyncSession, kayitlar: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """El değmemiş hazır kayıtları siler / doldurulan alanları boşaltır (ters sırayla). Commit ETMEZ."""
    from models.ai_asistan import AiAsistanParcalari

    silinen: List[Dict[str, Any]] = []
    korunan: List[Dict[str, Any]] = []
    for k in reversed(kayitlar or []):
        model = _model(str(k.get("tablo")))
        etiket = {"modul": k.get("modul"), "etiket": k.get("etiket"), "tablo": k.get("tablo")}
        if model is None:
            korunan.append({**etiket, "neden": "bilinmeyen_tablo"})
            continue
        n = await db.get(model, int(k.get("id") or 0))
        if n is None:
            silinen.append({**etiket, "zaten_yok": True})
            continue
        if k.get("tur") == "alan":
            alan = str(k.get("alan"))
            if deger_izi(getattr(n, alan, None)) == k.get("iz"):
                setattr(n, alan, None)
                await db.flush()
                silinen.append(etiket)
            else:
                korunan.append({**etiket, "neden": "degistirildi"})
            continue
        if parmak_izi(n) != k.get("iz"):
            korunan.append({**etiket, "neden": "degistirildi"})
            continue
        neden = await _kullanim_nedeni(db, model.__tablename__, n)
        if neden:
            korunan.append({**etiket, "neden": neden})
            continue
        if model.__tablename__ == "ai_asistan_kaynaklari":
            await db.execute(delete(AiAsistanParcalari).where(AiAsistanParcalari.kaynak_id == n.id))
        await db.delete(n)
        await db.flush()
        silinen.append(etiket)
    return {"silinen": silinen, "korunan": korunan}


__all__ = [
    "HazirAyarHatasi", "Baglam", "parmak_izi", "deger_izi", "UYGULAYICILAR", "uygula", "sonradan_isle", "geri_al",
    "json_yaz", "json_oku",
]
