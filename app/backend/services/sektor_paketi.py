"""Faz 6R — sektör paketini bir müşteriye tek tıkla açma: önizleme, atomik uygulama, geri alma.

Akış (Yönetici › Sistem › Modüller → müşteri seçili → "Sektör paketi uygula")
-----------------------------------------------------------------------------
1. **Önizleme** (`onizle`): paketin modülleri bağımlılıklarıyla, bağımlılık
   sırasıyla (`core.moduller.sirali`): hangileri açılacak, hangileri zaten açık;
   her modülün plan etkisi (Modüller ekranıyla aynı mantık: müşterinin ölçek
   paketine dahil mi, ayrı satılan mı, kredi kullanıyor mu) ve uygulanacak hazır
   ayarlar (`services/sektor_ayarlari.py` kuru kip: ne oluşturulacak, ne neden atlanacak).
2. **Uygula** (`uygula`): modül satırları (`workspace_modules`, elle açık) + hazır
   ayarlar + günlük satırı + denetim kaydı TEK işlemde; herhangi bir adım hata
   verirse `rollback` → hiçbiri yazılmaz. Commit'ten sonra: AI asistan SSS
   kaynağı dizine işlenir; istenirse müşteriye TEK özet bildirimi (`modul_acildi`).
3. **Paketi kaldır** (`kaldir`): yalnız paketin AÇTIĞI ve sonradan elle
   değiştirilmemiş (hâlâ açık, açılış anı aynı) modüller eski haline döner
   (`onceki_elle`: yok → varsayılana, false → kapalı). Veri silinmez (modül
   kapatmanın mevcut davranışı). Açık kalan başka bir modül hâlâ bağlıysa o
   bağımlılık korunur (`bagimli_acik`). İsteğe bağlı: hazır ayarları da geri al.
4. **Hazır ayarları geri al** (`hazir_geri_al`): yalnız el değmemiş hazır kayıtlar.

Hazır ayarlar ayrıca paketten bağımsız da uygulanabiliyor (`hazir_uygula`):
yalnız müşteride AÇIK modüllere yazılır.

Otomasyon önerileri kurulmaz: `onerilen_sablonlar(hesap)` müşterinin Otomasyon ›
Hazır şablonlar sekmesinde "sektörünüz için önerilen" işaretini besler.
"""

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Set

from core import moduller as manifest
from core import sektor_ayarlari as sa
from core import sektor_paketleri as sp
from models.sektor_paketi import SektorPaketiUygulamalari
from models.workspace_modules import WorkspaceModules
from services import moduller as ms
from services import sektor_ayarlari as hazir
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PANEL_BAGLANTISI = "/client?sekme=profile"
ALAN_SINIRI = {"isletme_adi": 100, "adres": 300}


class PaketHatasi(Exception):
    def __init__(self, kod: str, durum: int = 400, **ek: Any):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def simdi() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(an: Optional[datetime]) -> Optional[str]:
    if an is None:
        return None
    if an.tzinfo is None:
        an = an.replace(tzinfo=timezone.utc)
    return an.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _j(ham: Any, varsayilan: Any) -> Any:
    return hazir.json_oku(ham, varsayilan)


def _metin(ham: Any, alan: str) -> str:
    if ham is None:
        return ""
    if not isinstance(ham, str):
        raise PaketHatasi("gecersiz", alan=alan)
    deger = " ".join(ham.split())
    if len(deger) > ALAN_SINIRI[alan]:
        raise PaketHatasi("cok_uzun", alan=alan, en_cok=ALAN_SINIRI[alan])
    return deger


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------
def katalog() -> Dict[str, Any]:
    return {
        "paketler": [
            {**p.sozluk(), "ad": dict(p.ad_varsayilan), "setler": sa.paket_setleri(p.anahtar),
             "acilacak": sp.acilacak_moduller(p.anahtar)}
            for p in sp.SEKTOR_PAKETLERI
        ],
        "setler": [s.sozluk() for s in sa.HAZIR_SETLER],
        "diller": list(sa.DILLER),
        "icerik_dilleri": list(sa.ICERIK_DILLERI),
    }


def _paket_ve_set(paket: Optional[str], set_anahtari: Optional[str], paket_zorunlu: bool = True):
    p = sp.paket(paket or "") if paket else None
    if paket_zorunlu and p is None:
        raise PaketHatasi("paket_yok", 404)
    if set_anahtari:
        s = sa.hazir_set(set_anahtari)
        if s is None or (p is not None and s.paket != p.anahtar):
            raise PaketHatasi("set_gecersiz", 400)
    elif p is not None:
        s = sa.hazir_set(sa.varsayilan_set(p.anahtar))
    else:
        raise PaketHatasi("set_gecersiz", 400)
    return p, s


# ---------------------------------------------------------------------------
# Modüller: hedef liste, plan etkisi
# ---------------------------------------------------------------------------
def _tum_bagimliliklar(anahtar: str) -> Set[str]:
    sonuc: Set[str] = set()

    def gez(k: str) -> None:
        m = manifest.modul(k)
        if m is None:
            return
        for b in m.bagimliliklar:
            if b not in sonuc:
                sonuc.add(b)
                gez(b)

    gez(anahtar)
    return sonuc


def hedef_moduller(paket: sp.SektorPaketi, durumlar: Dict[str, ms.ModulDurumu]) -> List[str]:
    """Paketin modülleri + açık olmayan bağımlılıkları (çekirdek hariç), bağımlılık sırasıyla."""
    gerekli: Set[str] = set()

    def ekle(k: str, paketten: bool) -> None:
        m = manifest.modul(k)
        if m is None or k in gerekli or m.cekirdek:
            return
        d = durumlar.get(k)
        if not paketten and d is not None and d.acik:
            return  # zaten açık bağımlılık listeye girmesin
        gerekli.add(k)
        for b in m.bagimliliklar:
            ekle(b, False)

    for k in paket.moduller:
        ekle(k, True)
    return [m.anahtar for m in manifest.sirali() if m.anahtar in gerekli]


def _plan_etkisi(m: manifest.Modul, musteri_paketi: Optional[str]) -> Dict[str, Any]:
    """Modüller ekranındaki mantık: ölçek paketine dahil mi (kaynak "paket"), değilse elle açılan
    (ayrı satılan / üst pakette), kredi ile aşım var mı."""
    if musteri_paketi and musteri_paketi in m.paketler:
        etki = "plana_dahil"
    elif m.paketler:
        etki = "ust_pakette"
    else:
        etki = "ayri_satilan"
    en_dusuk = next((k for k in manifest.PAKETLER if k in m.paketler), None)
    return {
        "etki": etki,
        "paketler": list(m.paketler),
        "en_dusuk_paket": en_dusuk,
        "kredi": any(a.anahtar == "kredi_ile_asim" for a in m.ayarlar),
        "sinirlar": {a.anahtar: a.varsayilan for a in m.ayarlar if a.tur == "int"},
    }


def _modul_satirlari(hedef: List[str], durumlar: Dict[str, ms.ModulDurumu], paket: sp.SektorPaketi,
                     musteri_paketi: Optional[str]) -> List[Dict[str, Any]]:
    satirlar = []
    for k in hedef:
        m = manifest.MODUL_SOZLUGU[k]
        d = durumlar[k]
        satirlar.append({
            "anahtar": k, "ad_anahtari": m.ad_anahtari, "ikon": m.ikon, "durum": "acik" if d.acik else "acilacak",
            "kaynak": d.kaynak, "paketten": k in paket.moduller, "bagimliliklar": list(m.bagimliliklar),
            **_plan_etkisi(m, musteri_paketi),
        })
    return satirlar


# ---------------------------------------------------------------------------
# Müşteri bilgisi (varsayılan dil, işletme adı, adres — yalnız gerçek kayıtlardan)
# ---------------------------------------------------------------------------
async def _ilk(db: AsyncSession, sorgu) -> Any:
    try:
        satir = (await db.execute(sorgu.limit(1))).first()
    except Exception:  # noqa: BLE001 - tablo yoksa bilgi yok
        logger.exception("Müşteri bilgisi okunamadı")
        return None
    return satir[0] if satir else None


async def musteri_bilgisi(db: AsyncSession, eposta: str) -> Dict[str, Any]:
    from models.auth import User
    from models.eposta_pazarlama import EpAyarlar
    from models.invoices import Invoices
    from models.kartvizit import Kartvizitler
    from models.projects import Projects
    from models.qr_menu import MenuMagazalari
    from models.randevu import RandevuSayfalari
    from models.saha_servisi import SahaAyarlari

    e = ms.eposta_duzelt(eposta)
    dil = None
    for sorgu in (
        select(RandevuSayfalari.dil).where(RandevuSayfalari.hesap_email == e),
        select(Kartvizitler.dil).where(Kartvizitler.hesap_email == e),
        select(MenuMagazalari.varsayilan_dil).where(MenuMagazalari.hesap_email == e),
        select(SahaAyarlari.varsayilan_dil).where(SahaAyarlari.hesap_email == e),
        select(EpAyarlar.dil).where(EpAyarlar.hesap_email == e),
    ):
        dil = await _ilk(db, sorgu)
        if dil:
            break
    ad = None
    for sorgu in (
        select(SahaAyarlari.firma_adi).where(SahaAyarlari.hesap_email == e, SahaAyarlari.firma_adi.isnot(None)),
        select(Projects.client_name).where(Projects.client_email == e, Projects.client_name.isnot(None)),
        select(Invoices.client_name).where(Invoices.client_email == e, Invoices.client_name.isnot(None)),
        select(User.name).where(User.email == e, User.role != "admin", User.name.isnot(None)),
    ):
        ad = await _ilk(db, sorgu)
        if ad and str(ad).strip():
            break
    adres = None
    for sorgu in (
        select(SahaAyarlari.adres).where(SahaAyarlari.hesap_email == e, SahaAyarlari.adres.isnot(None)),
        select(MenuMagazalari.adres).where(MenuMagazalari.hesap_email == e, MenuMagazalari.adres.isnot(None)),
    ):
        adres = await _ilk(db, sorgu)
        if adres and str(adres).strip():
            break
    if not adres:
        icerik = await _ilk(db, select(Kartvizitler.icerik).where(Kartvizitler.hesap_email == e))
        adres = (_j(icerik, {}) or {}).get("adres") if icerik else None
    return {
        "dil": sa.dil_duzelt(dil) if dil else "tr",
        "isletme_adi": (str(ad).strip()[:ALAN_SINIRI["isletme_adi"]] if ad else ""),
        "adres": (str(adres).strip()[:ALAN_SINIRI["adres"]] if adres else ""),
    }


# ---------------------------------------------------------------------------
# Önizleme
# ---------------------------------------------------------------------------
async def onizle(
    db: AsyncSession, eposta: str, *, paket: Optional[str], set_anahtari: Optional[str], dil: Optional[str],
    isletme_adi: Any = None, adres: Any = None, hazir_ayarlar: bool = True, kisi: str = "",
) -> Dict[str, Any]:
    p, s = _paket_ve_set(paket, set_anahtari, paket_zorunlu=bool(paket))
    eposta = ms.eposta_duzelt(eposta)
    dil = sa.dil_duzelt(dil)
    isletme = _metin(isletme_adi, "isletme_adi")
    adres_ = _metin(adres, "adres")
    mm = await ms.musteri_modulleri(db, eposta)
    acik = {k for k, d in mm.durumlar.items() if d.acik}
    moduller: List[Dict[str, Any]] = []
    if p is not None:
        hedef = hedef_moduller(p, mm.durumlar)
        moduller = _modul_satirlari(hedef, mm.durumlar, p, mm.paket)
        acik |= set(hedef)
    b = hazir.Baglam(db=db, hesap=eposta, set=s, dil=dil, idil=sa.icerik_dili(dil), kisi=kisi, acik=acik, kuru=True,
                     isletme_adi=isletme, adres=adres_)
    if hazir_ayarlar:
        await hazir.uygula(b)
    acilacak = [m for m in moduller if m["durum"] == "acilacak"]
    return {
        "eposta": eposta,
        "paket": p.anahtar if p else None,
        "set": s.anahtar,
        "dil": dil,
        "icerik_dili": b.idil,
        "musteri_paketi": mm.paket,
        "moduller": moduller,
        "ozet": {
            "acilacak": len(acilacak),
            "zaten_acik": len(moduller) - len(acilacak),
            "ayri_satilan": sum(1 for m in acilacak if m["etki"] != "plana_dahil"),
            "kredi": [m["anahtar"] for m in moduller if m["kredi"]],
            "olusturulacak": sum(len(x["ogeler"]) for x in b.plan if x["modul"] != "otomasyon"),
        },
        "hazir": b.plan,
        "uyarilar": b.uyarilar,
        "oneriler": list(s.otomasyon),
    }


# ---------------------------------------------------------------------------
# Uygulama (atomik)
# ---------------------------------------------------------------------------
def _modul_acma_denetimi(anahtar: str) -> None:
    """Açılacak her modül için son denetim (testler hata enjekte etmek için değiştiriyor)."""
    m = manifest.MODUL_SOZLUGU.get(anahtar)
    if m is None:
        raise ms.ModulHatasi(404, "modul_yok", [anahtar])
    if not m.musteriye_gorunur:
        raise ms.ModulHatasi(400, "yalniz_yonetici_modulu", [anahtar])


async def _hazir_calistir(b: hazir.Baglam) -> None:
    if b.set.reklam_yasagi:  # Faz 6H: Av. K. m.55 — tanıtım/yorum/reklam öğesi kurulmadığını panel de söylesin
        b.uyar("reklam_yasagi")
    for modul in b.set.moduller():
        try:
            await hazir.UYGULAYICILAR[modul](b)
        except PaketHatasi:
            raise
        except Exception as exc:  # noqa: BLE001 - hangi modülde patladığını söyle; işlem geri alınacak
            logger.exception("Hazır ayar uygulanamadı: %s", modul)
            raise PaketHatasi("hazir_ayar_hatasi", 409, modul=modul, neden=getattr(exc, "kod", type(exc).__name__))


async def _gunluk_yaz(db: AsyncSession, request: Any, u: SektorPaketiUygulamalari, ozet: str, islem: str = "olustur") -> None:
    from services.denetim import denetim_yaz

    await denetim_yaz(db, request=request, islem=islem, tablo="sektor_paketi_uygulamalari", kayit_id=u.id, ozet=ozet)


def _ad(anahtar: Optional[str], dil: str = "tr") -> str:
    p = sp.paket(anahtar or "")
    return p.ad_varsayilan[dil] if p else (anahtar or "")


async def uygula(
    db: AsyncSession, eposta: str, *, paket: str, set_anahtari: Optional[str], dil: Optional[str],
    isletme_adi: Any = None, adres: Any = None, hazir_ayarlar: bool = True, bildirim: bool = False,
    yonetici: str = "", request: Any = None,
) -> Dict[str, Any]:
    p, s = _paket_ve_set(paket, set_anahtari)
    eposta = ms.eposta_duzelt(eposta)
    dil = sa.dil_duzelt(dil)
    isletme = _metin(isletme_adi, "isletme_adi")
    adres_ = _metin(adres, "adres")
    an = simdi()
    b: Optional[hazir.Baglam] = None
    try:
        onceki = await ms.musteri_modulleri(db, eposta)
        hedef = hedef_moduller(p, onceki.durumlar)
        acilacak = [k for k in hedef if not onceki.durumlar[k].acik]
        zaten = [k for k in hedef if onceki.durumlar[k].acik]
        satirlar = await ms._satirlar(db, eposta)
        acilan: List[Dict[str, Any]] = []
        for k in acilacak:
            _modul_acma_denetimi(k)
            satir = satirlar.get(k)
            onceki_elle = satir.acik if satir is not None else None
            if satir is None:
                satir = WorkspaceModules(musteri_eposta=eposta, modul_anahtari=k, created_at=an)
                db.add(satir)
                satirlar[k] = satir
            if satir.acik is not True:
                satir.acik = True
                satir.acilis_at = an
            satir.acan_eposta = ms.eposta_duzelt(yonetici) or None
            acilan.append({"anahtar": k, "onceki_elle": onceki_elle})
        await db.flush()
        sonraki = ms.durumlari_hesapla(onceki.paket, await ms._satirlar(db, eposta))
        kapali = [k for k in hedef if not sonraki[k].acik]
        if kapali:
            raise ms.ModulHatasi(409, "acilamadi", kapali)
        for e in acilan:
            e["acilis_at"] = _iso(satirlar[e["anahtar"]].acilis_at)
        if hazir_ayarlar:
            b = hazir.Baglam(db=db, hesap=eposta, set=s, dil=dil, idil=sa.icerik_dili(dil), kisi=yonetici,
                             acik={k for k, d in sonraki.items() if d.acik}, kuru=False, isletme_adi=isletme, adres=adres_, an=an)
            if s.kvkk_ozel:
                b.uyar("kvkk_ozel")
            await _hazir_calistir(b)
        u = SektorPaketiUygulamalari(
            musteri_eposta=eposta, tur="paket", paket=p.anahtar, set_anahtari=s.anahtar, dil=dil, icerik_dili=sa.icerik_dili(dil),
            acilan_moduller=hazir.json_yaz(acilan), zaten_acik=hazir.json_yaz(zaten),
            hazir_kayitlar=hazir.json_yaz(b.kayitlar if b else []),
            atlananlar=hazir.json_yaz(_atlanan_ozeti(b) if b else []),
            oneriler=hazir.json_yaz(list(s.otomasyon)), durum="uygulandi",
            hazir_durum="uygulandi" if b and b.kayitlar else "yok", bildirim=bool(bildirim),
            uygulayan=ms.eposta_duzelt(yonetici) or None, created_at=an,
        )
        db.add(u)
        await db.flush()
        await _gunluk_yaz(db, request, u, (
            f"Sektör paketi uygulandı: {p.ad_varsayilan['tr']} ({s.anahtar}) → {eposta}; "
            f"{len(acilan)} modül açıldı, {len(b.kayitlar) if b else 0} hazır kayıt"
        ))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    uid = u.id
    if b is not None and b.sonradan:
        await hazir.sonradan_isle(db, b.sonradan)
    if bildirim and (acilan or (b and b.kayitlar)):
        await _bildir(db, eposta, uid, "modul_acildi", p, [e["anahtar"] for e in acilan], bool(b and b.kayitlar))
    u = await db.get(SektorPaketiUygulamalari, uid)
    return {"uygulama": uygulama_sozlugu(u), "plan": b.plan if b else [], "uyarilar": b.uyarilar if b else []}


def _atlanan_ozeti(b: hazir.Baglam) -> List[Dict[str, Any]]:
    return [{"modul": x["modul"], **a} for x in b.plan for a in x["atlanan"]]


async def hazir_uygula(
    db: AsyncSession, eposta: str, *, set_anahtari: str, dil: Optional[str], isletme_adi: Any = None, adres: Any = None,
    yonetici: str = "", request: Any = None,
) -> Dict[str, Any]:
    """Paket açmadan yalnız hazır ayarlar (müşteride AÇIK modüllere)."""
    _, s = _paket_ve_set(None, set_anahtari, paket_zorunlu=False)
    eposta = ms.eposta_duzelt(eposta)
    dil = sa.dil_duzelt(dil)
    isletme = _metin(isletme_adi, "isletme_adi")
    adres_ = _metin(adres, "adres")
    an = simdi()
    try:
        mm = await ms.musteri_modulleri(db, eposta)
        b = hazir.Baglam(db=db, hesap=eposta, set=s, dil=dil, idil=sa.icerik_dili(dil), kisi=yonetici,
                         acik={k for k, d in mm.durumlar.items() if d.acik}, kuru=False, isletme_adi=isletme, adres=adres_, an=an)
        if s.kvkk_ozel:
            b.uyar("kvkk_ozel")
        await _hazir_calistir(b)
        u = None
        if b.kayitlar:
            u = SektorPaketiUygulamalari(
                musteri_eposta=eposta, tur="hazir", paket=s.paket, set_anahtari=s.anahtar, dil=dil, icerik_dili=b.idil,
                acilan_moduller="[]", zaten_acik="[]", hazir_kayitlar=hazir.json_yaz(b.kayitlar),
                atlananlar=hazir.json_yaz(_atlanan_ozeti(b)), oneriler=hazir.json_yaz(list(s.otomasyon)),
                durum="uygulandi", hazir_durum="uygulandi", uygulayan=ms.eposta_duzelt(yonetici) or None, created_at=an,
            )
            db.add(u)
            await db.flush()
            await _gunluk_yaz(db, request, u, f"Hazır sektör ayarları uygulandı: {s.anahtar} → {eposta}; {len(b.kayitlar)} kayıt")
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    if b.sonradan:
        await hazir.sonradan_isle(db, b.sonradan)
    sonuc = uygulama_sozlugu(await db.get(SektorPaketiUygulamalari, u.id)) if u is not None else None
    return {"uygulama": sonuc, "plan": b.plan, "uyarilar": b.uyarilar}


# ---------------------------------------------------------------------------
# Geri alma
# ---------------------------------------------------------------------------
async def _uygulama(db: AsyncSession, uid: int) -> SektorPaketiUygulamalari:
    u = await db.get(SektorPaketiUygulamalari, uid)
    if u is None:
        raise PaketHatasi("bulunamadi", 404)
    return u


async def kaldir(
    db: AsyncSession, uid: int, *, hazir_da: bool = True, bildirim: bool = False, yonetici: str = "", request: Any = None,
) -> Dict[str, Any]:
    u = await _uygulama(db, uid)
    if u.tur != "paket":
        raise PaketHatasi("paket_uygulamasi_degil", 400)
    if u.durum == "kaldirildi":
        raise PaketHatasi("zaten_kaldirildi", 409)
    eposta = u.musteri_eposta
    an = simdi()
    try:
        onceki = await ms.musteri_modulleri(db, eposta)
        satirlar = await ms._satirlar(db, eposta)
        adaylar: List[Dict[str, Any]] = []
        korunan: List[Dict[str, Any]] = []
        for e in _j(u.acilan_moduller, []):
            k = e.get("anahtar")
            satir = satirlar.get(k)
            if satir is None or satir.acik is not True or _iso(satir.acilis_at) != e.get("acilis_at"):
                korunan.append({"anahtar": k, "neden": "elle_degisti"})
                continue
            adaylar.append(e)
        # Kapatınca açık kalan başka bir modülü engelleyecek bağımlılıkları koru (tekrar tekrar).
        while adaylar:
            geri = {e["anahtar"]: e.get("onceki_elle") for e in adaylar}
            benzetim = {
                k: SimpleNamespace(acik=(geri[k] if k in geri else s_.acik), ayarlar_json=s_.ayarlar_json)
                for k, s_ in satirlar.items()
            }
            sonra = ms.durumlari_hesapla(onceki.paket, benzetim)
            engellenen = [k for k, d in onceki.durumlar.items() if d.acik and k not in geri and not sonra[k].acik]
            if not engellenen:
                break
            sorumlu: Set[str] = set()
            for k in engellenen:
                sorumlu |= _tum_bagimliliklar(k)
            tutulan = [e for e in adaylar if e["anahtar"] in sorumlu]
            if not tutulan:
                break
            for e in tutulan:
                korunan.append({"anahtar": e["anahtar"], "neden": "bagimli_acik", "moduller": engellenen})
            adaylar = [e for e in adaylar if e["anahtar"] not in sorumlu]
        kapatilan = []
        for e in adaylar:
            satir = satirlar[e["anahtar"]]
            satir.acik = e.get("onceki_elle")
            satir.kapanis_at = an
            satir.acan_eposta = ms.eposta_duzelt(yonetici) or None
            kapatilan.append(e["anahtar"])
        await db.flush()
        hazir_sonuc = None
        if hazir_da and u.hazir_durum == "uygulandi":
            hazir_sonuc = await hazir.geri_al(db, _j(u.hazir_kayitlar, []))
            u.hazir_durum = "geri_alindi"
            u.hazir_geri_alma_at = an
        u.durum = "kaldirildi"
        u.kaldirma_at = an
        u.geri_alan = ms.eposta_duzelt(yonetici) or None
        u.geri_alma = hazir.json_yaz({"kapatilan": kapatilan, "korunan": korunan, "hazir": hazir_sonuc})
        await db.flush()
        await _gunluk_yaz(db, request, u, (
            f"Sektör paketi kaldırıldı: {_ad(u.paket)} → {eposta}; {len(kapatilan)} modül eski haline döndü, "
            f"{len(korunan)} korundu"
        ), islem="guncelle")
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    sonra = await ms.musteri_modulleri(db, eposta)
    gercekten_kapanan = [k for k in kapatilan if not sonra.durumlar[k].acik]
    if bildirim and gercekten_kapanan:
        await _bildir(db, eposta, uid, "modul_kapandi", sp.paket(u.paket or ""), gercekten_kapanan, False)
    u = await db.get(SektorPaketiUygulamalari, uid)
    return {"uygulama": uygulama_sozlugu(u), "kapatilan": kapatilan, "korunan": korunan, "hazir": hazir_sonuc}


async def hazir_geri_al(db: AsyncSession, uid: int, *, yonetici: str = "", request: Any = None) -> Dict[str, Any]:
    u = await _uygulama(db, uid)
    if u.hazir_durum != "uygulandi":
        raise PaketHatasi("hazir_ayar_yok", 409)
    an = simdi()
    try:
        sonuc = await hazir.geri_al(db, _j(u.hazir_kayitlar, []))
        u.hazir_durum = "geri_alindi"
        u.hazir_geri_alma_at = an
        u.geri_alan = ms.eposta_duzelt(yonetici) or None
        onceki = _j(u.geri_alma, {}) or {}
        u.geri_alma = hazir.json_yaz({**onceki, "hazir": sonuc})
        if u.tur == "hazir":
            u.durum = "kaldirildi"
            u.kaldirma_at = an
        await db.flush()
        await _gunluk_yaz(db, request, u, (
            f"Hazır sektör ayarları geri alındı: {u.set_anahtari} → {u.musteri_eposta}; {len(sonuc['silinen'])} silindi, "
            f"{len(sonuc['korunan'])} korundu"
        ), islem="guncelle")
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    u = await db.get(SektorPaketiUygulamalari, uid)
    return {"uygulama": uygulama_sozlugu(u), "hazir": sonuc}


# ---------------------------------------------------------------------------
# Bildirim, geçmiş, öneriler
# ---------------------------------------------------------------------------
def _modul_adlari(anahtarlar: Iterable[str], dil: str) -> str:
    return ", ".join(manifest.MODUL_SOZLUGU[k].ad_varsayilan[dil] for k in anahtarlar if k in manifest.MODUL_SOZLUGU)


async def _bildir(db: AsyncSession, eposta: str, uid: int, olay: str, p: Optional[sp.SektorPaketi], moduller: List[str],
                  hazir_var: bool) -> None:
    """Müşteriye TEK özet bildirimi (modül başına ayrı değil). Hata yutar."""
    try:
        from services.notify import dispatch, render
    except Exception:  # noqa: BLE001
        return
    ad_tr = p.ad_varsayilan["tr"] if p else ""
    ad_en = p.ad_varsayilan["en"] if p else ""
    liste_tr, liste_en = _modul_adlari(moduller, "tr"), _modul_adlari(moduller, "en")
    if olay == "modul_acildi":
        baslik = f"Sektör paketiniz hazır: {ad_tr} / Your industry pack is ready: {ad_en}"
        govde = (
            f"Panelinizde \"{ad_tr}\" paketi açıldı." + (f" Açılan modüller: {liste_tr}." if liste_tr else "")
            + (" Başlangıç ayarları eklendi; işletmenize göre düzenleyebilirsiniz." if hazir_var else "")
            + f"\n\nThe \"{ad_en}\" pack is now enabled in your client panel." + (f" Modules: {liste_en}." if liste_en else "")
            + (" Starter settings were added; you can edit them to suit your business." if hazir_var else "")
        )
    else:
        baslik = f"Sektör paketi kaldırıldı: {ad_tr} / Industry pack removed: {ad_en}"
        govde = (
            f"Panelinizdeki şu modüller kapatıldı: {liste_tr}. Verileriniz silinmedi."
            f"\n\nThese modules were disabled in your client panel: {liste_en}. Your data has not been deleted."
        )
    try:
        baslik, govde = await render(db, olay, baslik, govde, {"modul": liste_tr, "modul_en": liste_en})
        await dispatch(db, event_type=olay, title=baslik, body=govde, recipients=[{"email": eposta, "role": "client"}],
                       link=PANEL_BAGLANTISI, ref_type="sektor_paketi", ref_id=uid)
    except Exception:  # noqa: BLE001 - bildirim asıl işi bozmamalı
        logger.exception("Sektör paketi bildirimi gönderilemedi")


def uygulama_sozlugu(u: SektorPaketiUygulamalari) -> Dict[str, Any]:
    return {
        "id": u.id, "eposta": u.musteri_eposta, "tur": u.tur, "paket": u.paket, "set": u.set_anahtari, "dil": u.dil,
        "icerik_dili": u.icerik_dili, "durum": u.durum, "hazir_durum": u.hazir_durum,
        "acilan_moduller": _j(u.acilan_moduller, []), "zaten_acik": _j(u.zaten_acik, []),
        "hazir_kayitlar": [{k: v for k, v in x.items() if k != "iz"} for x in _j(u.hazir_kayitlar, [])],
        "atlananlar": _j(u.atlananlar, []), "oneriler": _j(u.oneriler, []), "geri_alma": _j(u.geri_alma, None),
        "bildirim": bool(u.bildirim), "uygulayan": u.uygulayan, "geri_alan": u.geri_alan,
        "olusturma": _iso(u.created_at), "kaldirma": _iso(u.kaldirma_at), "hazir_geri_alma": _iso(u.hazir_geri_alma_at),
    }


async def gecmis(db: AsyncSession, eposta: str) -> List[Dict[str, Any]]:
    satirlar = (await db.execute(
        select(SektorPaketiUygulamalari).where(SektorPaketiUygulamalari.musteri_eposta == ms.eposta_duzelt(eposta))
        .order_by(SektorPaketiUygulamalari.id.desc()).limit(50)
    )).scalars().all()
    return [uygulama_sozlugu(u) for u in satirlar]


async def onerilen_sablonlar(db: AsyncSession, hesap: Optional[str]) -> List[str]:
    """Hesaba uygulanmış (geri alınmamış) setlerin otomasyon önerileri — sırası korunarak, tekrarsız."""
    if not hesap:
        return []
    try:
        satirlar = (await db.execute(
            select(SektorPaketiUygulamalari.tur, SektorPaketiUygulamalari.durum, SektorPaketiUygulamalari.hazir_durum,
                   SektorPaketiUygulamalari.oneriler)
            .where(SektorPaketiUygulamalari.musteri_eposta == ms.eposta_duzelt(hesap))
            .order_by(SektorPaketiUygulamalari.id.desc()).limit(20)
        )).all()
    except Exception:  # noqa: BLE001 - tablo yoksa öneri yok
        logger.exception("Otomasyon önerileri okunamadı")
        return []
    sonuc: List[str] = []
    for tur, durum, hazir_durum, oneriler in satirlar:
        gecerli = durum == "uygulandi" if tur == "paket" else hazir_durum == "uygulandi"
        if not gecerli:
            continue
        for k in _j(oneriler, []):
            if isinstance(k, str) and k not in sonuc:
                sonuc.append(k)
    return sonuc


async def musteri_mi(db: AsyncSession, epostalar: Iterable[str]) -> Set[str]:
    """Bu e-postalardan hangileri bir müşteri hesabı? (kullanıcı kaydı, modül satırı, proje ya da fatura)."""
    from models.auth import User
    from models.invoices import Invoices
    from models.projects import Projects
    from sqlalchemy import func

    liste = sorted({ms.eposta_duzelt(e) for e in epostalar if e})
    if not liste:
        return set()
    bulunan: Set[str] = set()
    for sorgu in (
        select(func.lower(User.email)).where(func.lower(User.email).in_(liste), User.role != "admin"),
        select(func.lower(WorkspaceModules.musteri_eposta)).where(func.lower(WorkspaceModules.musteri_eposta).in_(liste)),
        select(func.lower(Projects.client_email)).where(func.lower(Projects.client_email).in_(liste)),
        select(func.lower(Invoices.client_email)).where(func.lower(Invoices.client_email).in_(liste)),
    ):
        try:
            bulunan |= {x for x in (await db.execute(sorgu)).scalars().all() if x}
        except Exception:  # noqa: BLE001
            logger.exception("Müşteri eşleşmesi okunamadı")
    return bulunan


__all__ = [
    "PaketHatasi", "katalog", "hedef_moduller", "musteri_bilgisi", "onizle", "uygula", "hazir_uygula", "kaldir",
    "hazir_geri_al", "uygulama_sozlugu", "gecmis", "onerilen_sablonlar", "musteri_mi",
]
