"""Faz 6O — Hedefler ve OKR: dönem, hedef, anahtar sonuç (KR), check-in, otomatik kaynaklar, kapanış, paylaşım.

Müşteri (`/api/v1/okr`; modül `hedefler` açık + hesap ekibi izni `hedefler`) — etkin hesabın OKR'ları. `hedefler_okur`
YALNIZ okur (meta, dönemler, özet, ağaç, ayrıntı, check-in geçmişi, rapor); her yazma 403 `hesap_izni_yok`.
Yönetici (`/api/v1/okr-yonetim`) — ajansın KENDİ OKR'ları (kapsam `@ajans`); hedef bir müşteri hesabına bağlanıp
"müşteriyle paylaş" denebilir. `GET /musteri-hesaplari` bağlanacak hesap listesi.
Paylaşılan kart (`GET /api/v1/okr-paylasilan`; modül GEREKMEZ — portal parçası; izin `projeler` / `hedefler` /
`hedefler_okur`): ajansın bu hesaba bağlayıp PAYLAŞTIĞI, ekip görünürlüklü, taslak olmayan hedefleri ve KR ilerlemesi
(salt okunur; check-in notu, sahip, güven, kaynak YOK). Ekip içi / özel / paylaşılmamış hedef hiçbir uçtan sızmaz.

Ortak uçlar (iki panelde aynı gövdeler):
  GET  /meta
  GET|POST /donemler · PUT|DELETE /donemler/{id} · GET /donemler/{id}/ozet · POST /donemler/{id}/yenile
  GET /donemler/{id}/kapanis · POST /donemler/{id}/kapat · GET /donemler/{id}/rapor.pdf · GET /donemler/{id}/rapor.csv
  GET /agac?donem_id=
  POST /hedefler · GET|PUT|DELETE /hedefler/{id}
  POST /hedefler/{id}/krler · PUT|DELETE /krler/{id} · POST /krler/{id}/checkin · GET /krler/{id}/checkinler
  POST /krler/{id}/yenile · POST /krler/{id}/odak
  POST /ai/kr-oner (öneriler KAYDEDİLMEZ; AI yapılandırılmamışsa 503 `ai_kapali`)

Silme: dönem (hedefi yoksa), hedef (KR'leri ve check-in'leriyle birlikte — çöp kutusunda birlikte geri gelir) ve KR
çöp kutusuna düşer; denetim kaydı otomatik (flush kancası).
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Set

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from models.okr import OkrAnahtarSonuclar, OkrCheckinler, OkrDonemler, OkrHedefler
from services import okr as s
from services import okr_kayit as k
from services import okr_kaynak as kaynaklar
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN
IZIN_OKUR = s.IZIN_OKUR
KR = OkrAnahtarSonuclar

yonetici_router = APIRouter(prefix="/api/v1/okr-yonetim", tags=["okr"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/okr",
    tags=["okr"],
    # Router bekçisi: iki izinden biri. Yazma uçları ayrıca `hedefler` ister.
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN, IZIN_OKUR))],
)
paylasim_router = APIRouter(prefix="/api/v1/okr-paylasilan", tags=["okr"])

#: Kişi başı: dakikada 120 yazma, 20 PDF/CSV, 10 AI önerisi.
_yazma_hizi = HizSiniri(120, 60.0)
_dosya_hizi = HizSiniri(20, 60.0)
_ai_hizi = HizSiniri(10, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _dosya_hizi, _ai_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    yonetici: bool
    #: Kayıtların hesabı: müşteride etkin hesap; yöneticide None (ajansın kendi OKR'ları).
    hesap: Optional[str]
    kisi: str
    #: `hedefler_okur`: yalnız okuma.
    okur: bool = False
    baglam: Any = None

    @property
    def anahtar(self) -> str:
        return s.kapsam_anahtari(self.hesap)


def _musteri_kapsami(request: Request, yaz: bool = False) -> Kapsam:
    if yaz:
        b = izin_iste(request, IZIN)
        return Kapsam(False, b.hesap_email, b.kisi_email, baglam=b)
    b = izin_iste(request, IZIN, IZIN_OKUR)
    return Kapsam(False, b.hesap_email, b.kisi_email, okur=not b.izin_var(IZIN), baglam=b)


def _yonetici_kapsami(request: Request, yaz: bool = False) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    kisi = (getattr(kullanici, "email", "") or "").strip().lower()
    return Kapsam(True, None, kisi)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _e(h: s.TemelHata) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _yaz(kapsam: Kapsam) -> None:
    if not _yazma_hizi.izin_var_mi(kapsam.kisi or "anonim"):
        raise _hata(429, "cok_hizli")


async def _govde(request: Request, sinir: int = 128 * 1024) -> Dict[str, Any]:
    import json

    ham = await request.body()
    if len(ham) > sinir:
        raise _hata(413, "govde_buyuk")
    if not ham:
        return {}
    try:
        g = json.loads(ham.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(g, dict):
        raise _hata(400, "govde_gecersiz")
    return g


def _dosya_yaniti(veri: bytes, tur: str, ad: str) -> Response:
    return Response(veri, media_type=tur, headers={"Content-Disposition": f'attachment; filename="{ad}"',
                                                   "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


async def _donem(db: AsyncSession, kapsam: Kapsam, did: Optional[int], alan: Optional[str] = None) -> OkrDonemler:
    d = None
    if did:
        d = (await db.execute(select(OkrDonemler).where(OkrDonemler.id == did, OkrDonemler.kapsam == kapsam.anahtar))).scalars().first()
    if d is None:
        raise _hata(404 if alan is None else 400, "donem_bulunamadi", **({"alan": alan} if alan else {}))
    return d


async def _hedef(db: AsyncSession, kapsam: Kapsam, hid: Optional[int], alan: Optional[str] = None) -> OkrHedefler:
    h = None
    if hid:
        h = (await db.execute(select(OkrHedefler).where(OkrHedefler.id == hid, OkrHedefler.kapsam == kapsam.anahtar,
                                                        k.gorunur_kosul(kapsam.kisi)))).scalars().first()
    if h is None:
        raise _hata(404 if alan is None else 400, "hedef_bulunamadi", **({"alan": alan} if alan else {}))
    return h


async def _kr(db: AsyncSession, kapsam: Kapsam, kid: int):
    kr = (await db.execute(select(KR).where(KR.id == kid, KR.kapsam == kapsam.anahtar))).scalars().first()
    if kr is None:
        raise _hata(404, "kr_bulunamadi")
    h = (await db.execute(select(OkrHedefler).where(OkrHedefler.id == kr.hedef_id, OkrHedefler.kapsam == kapsam.anahtar,
                                                    k.gorunur_kosul(kapsam.kisi)))).scalars().first()
    if h is None:  # özel hedefin KR'si başkasına "yok"
        raise _hata(404, "kr_bulunamadi")
    d = (await db.execute(select(OkrDonemler).where(OkrDonemler.id == h.donem_id))).scalars().first()
    return kr, h, d


def _acik_mi(d: Optional[OkrDonemler], h: Optional[OkrHedefler] = None) -> None:
    if d is not None and d.durum == "kapandi":
        raise _hata(409, "donem_kapali")
    if h is not None and h.durum == "kapandi":
        raise _hata(409, "hedef_kapali")


async def _ekip(db: AsyncSession, kapsam: Kapsam) -> List[Dict[str, Any]]:
    """Sahip seçenekleri. Ajans: yöneticiler (ayar + yönetici kullanıcılar) ve aktif personel. Müşteri: hesap sahibi +
    aktif üyeler. İsteği yapan kişi her zaman listede."""
    kisiler: Dict[str, Optional[str]] = {}
    if kapsam.hesap is None:
        from models.auth import User
        from models.staff import Staff
        from services.notify import admin_recipients

        for a in await admin_recipients(db):
            kisiler.setdefault((a.get("email") or "").strip().lower(), None)
        for e, ad in (await db.execute(select(User.email, User.name).where(User.role == "admin"))).all():
            if e:
                kisiler[e.strip().lower()] = ad or kisiler.get(e.strip().lower())
        for e, ad in (await db.execute(select(Staff.email, Staff.ad).where(Staff.aktif.isnot(False)))).all():
            if e:
                kisiler[e.strip().lower()] = ad or kisiler.get(e.strip().lower())
    else:
        from services.hesap_ekibi import hesap_adlari, uyeler

        kisiler[kapsam.hesap] = (await hesap_adlari(db, [kapsam.hesap])).get(kapsam.hesap)
        for u in await uyeler(db, kapsam.hesap):
            if u.durum == "aktif" and u.uye_email:
                kisiler.setdefault(u.uye_email.strip().lower(), None)
    if kapsam.kisi:
        kisiler.setdefault(kapsam.kisi, None)
    return [{"email": e, "ad": ad} for e, ad in sorted(kisiler.items()) if e and "@" in e]


async def _sahip(db: AsyncSession, kapsam: Kapsam, ham: Any, alan: str, mevcut: Optional[str] = None) -> Optional[str]:
    e = s.eposta_duzelt(ham, alan)
    if not e:
        return None
    if e == (mevcut or "") or e == kapsam.kisi:
        return e
    if e not in {x["email"] for x in await _ekip(db, kapsam)}:
        raise s.OkrHatasi("sahip_ekipte_yok", alan)
    return e


async def _hedef_siniri(db: AsyncSession, kapsam: Kapsam) -> Optional[int]:
    if not kapsam.hesap:
        return None
    from services.moduller import musteri_ayari

    d = await musteri_ayari(db, kapsam.hesap, MODUL, "hedef_siniri")
    return s.VARSAYILAN_HEDEF_SINIRI if d is None else int(d)


async def _musteri_hesabi(ham: Any) -> Optional[str]:
    e = s.eposta_duzelt(ham, "musteri_email")
    return e or None


def _ai_hazir() -> bool:
    from services.icerik_studyosu import ai_hazir

    return ai_hazir()


# ---------------------------------------------------------------------------
# Gövde uygulayıcıları
# ---------------------------------------------------------------------------
async def _hedef_uygula(db: AsyncSession, kapsam: Kapsam, h: OkrHedefler, g: Dict[str, Any], yeni: bool) -> None:
    if yeni or "baslik" in g:
        h.baslik = s.metin(g.get("baslik"), "baslik", 200, zorunlu=True)
    if "aciklama" in g:
        h.aciklama = s.bos_ya_da(g.get("aciklama"), "aciklama", 4000, cok_satir=True)
    if yeni or "sahip" in g:
        h.sahip = await _sahip(db, kapsam, g.get("sahip"), "sahip", h.sahip) or (kapsam.kisi if yeni else None)
    if yeni or "gorunurluk" in g:
        h.gorunurluk = s.secim(g.get("gorunurluk"), "gorunurluk", s.GORUNURLUKLER, "ekip")
    if yeni or "durum" in g:
        durum = s.secim(g.get("durum"), "durum", ("taslak", "etkin"), "etkin")
        if not yeni and h.durum == "kapandi":
            raise s.OkrHatasi("hedef_kapali", "durum", durum=409)
        h.durum = durum
    if "ust_id" in g:
        ust = s.kimlik(g.get("ust_id"), "ust_id")
        if ust is not None:
            await _hedef(db, kapsam, ust, alan="ust_id")
            if s.dongu_var_mi(await k.ust_haritasi(db, kapsam.anahtar), None if yeni else h.id, ust):
                raise s.OkrHatasi("hizalama_dongusu", "ust_id")
        h.ust_id = ust
    if kapsam.hesap is None:
        if "musteri_email" in g:
            h.musteri_email = await _musteri_hesabi(g.get("musteri_email"))
        if "musteri_paylasim" in g:
            h.musteri_paylasim = s.bool_duzelt(g.get("musteri_paylasim"), "musteri_paylasim")
        if h.musteri_paylasim and (not h.musteri_email or h.gorunurluk != "ekip"):
            raise s.OkrHatasi("paylasim_kosulu", "musteri_paylasim")
    elif "musteri_email" in g or "musteri_paylasim" in g:
        raise s.OkrHatasi("yalniz_ajans", "musteri_paylasim")


async def _kr_uygula(db: AsyncSession, kapsam: Kapsam, kr: KR, g: Dict[str, Any], yeni: bool) -> None:
    if yeni or "baslik" in g:
        kr.baslik = s.metin(g.get("baslik"), "baslik", 200, zorunlu=True)
    if "sahip" in g:
        kr.sahip = await _sahip(db, kapsam, g.get("sahip"), "sahip", kr.sahip)
    if yeni or "agirlik" in g:
        kr.agirlik = s.tam_sayi(g.get("agirlik", 1), "agirlik", 1, s.EN_COK_AGIRLIK) if g.get("agirlik") not in (None, "") else 1
    # --- Kaynak (otomatik) ---
    if yeni or "kaynak" in g:
        anahtar = g.get("kaynak") or None
        if anahtar is not None:
            kay = kaynaklar.KAYNAK_SOZLUGU.get(anahtar)
            if kay is None or kay not in kaynaklar.taraf_kaynaklari(kapsam.hesap is None):
                raise s.OkrHatasi("kaynak_gecersiz", "kaynak")
            if not await kaynaklar.kaynak_kullanilabilir_mi(db, anahtar, kapsam.hesap, kapsam.baglam):
                raise s.OkrHatasi("kaynak_kapali", "kaynak", durum=403)
            proje_idleri = None
            if kay.proje:
                proje_idleri = [p["id"] for p in await kaynaklar.proje_listesi(db)]
            ayar = kaynaklar.ayar_duzelt(kay, g.get("kaynak_ayar"), proje_idleri)
            if kr.kaynak != anahtar or s.json_yukle(kr.kaynak_ayar, {}) != ayar:
                kr.kaynak_son_yenileme = None
            kr.kaynak, kr.kaynak_ayar, kr.tur = anahtar, s.json_yaz(ayar), kay.tur
            kr.para_birimi = ayar.get("para_birimi")
            kr.kilometre_taslari = None
        else:
            kr.kaynak = kr.kaynak_ayar = kr.kaynak_hata = None
    if kr.kaynak is None and (yeni or "tur" in g):
        kr.tur = s.secim(g.get("tur"), "tur", s.KR_TURLERI, "sayi")
    tur = kr.tur
    if tur == "para" and kr.kaynak is None and (yeni or "para_birimi" in g or "tur" in g):
        kr.para_birimi = s.para_birimi_duzelt(g.get("para_birimi"))
    elif tur != "para":
        kr.para_birimi = None
    if "birim" in g or yeni:
        kr.birim = s.bos_ya_da(g.get("birim"), "birim", 20) if tur == "sayi" else None
    # --- Değerler ---
    if tur == "kilometre":
        if yeni or "kilometre_taslari" in g or "tur" in g:
            liste = s.kilometre_duzelt(g.get("kilometre_taslari"), onceki=k.kilometre_listesi(kr))
            kr.kilometre_taslari = s.json_yaz(liste)
        tamam, toplam = s.kilometre_sayilari(k.kilometre_listesi(kr))
        kr.baslangic_deger, kr.hedef_deger, kr.mevcut_deger, kr.yon = 0.0, float(toplam), float(tamam), "artir"
        return
    kr.kilometre_taslari = None
    if tur == "evet_hayir":
        kr.baslangic_deger, kr.hedef_deger, kr.yon = 0.0, 1.0, "artir"
        if "mevcut" in g and kr.kaynak is None:
            kr.mevcut_deger = s.deger_coz(g.get("mevcut"), tur, "mevcut")
        elif yeni:
            kr.mevcut_deger = 0.0
        return
    if yeni or "yon" in g:
        kr.yon = s.secim(g.get("yon"), "yon", s.YONLER, "artir")
    if yeni or "baslangic" in g:
        kr.baslangic_deger = s.deger_coz(g.get("baslangic", 0), tur, "baslangic")
    if yeni or "hedef" in g:
        kr.hedef_deger = s.deger_coz(g.get("hedef"), tur, "hedef")
    if kr.kaynak is None:
        if "mevcut" in g and g.get("mevcut") not in (None, ""):
            kr.mevcut_deger = s.deger_coz(g.get("mevcut"), tur, "mevcut")
        elif yeni:
            kr.mevcut_deger = kr.baslangic_deger
    s.yon_denetle(kr.yon, float(kr.baslangic_deger), float(kr.hedef_deger))


# ---------------------------------------------------------------------------
# Uçlar
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[..., Kapsam]) -> None:  # noqa: C901
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        ds = await k.donemler(db, kapsam.anahtar)
        bugun = s.bugun()
        etkin = next((d.id for d in ds if d.etkin), None)
        if etkin is None:  # etkin seçilmemişse bugünü kapsayan açık dönem, o da yoksa en yenisi
            etkin = next((d.id for d in ds if d.durum == "acik" and d.baslangic <= bugun <= d.bitis), ds[0].id if ds else None)
        musteri_hesaplari: List[Dict[str, Any]] = []
        projeler: List[Dict[str, Any]] = []
        if kapsam.hesap is None:
            from services.moduller import musteri_listesi

            musteri_hesaplari = await musteri_listesi(db)
            projeler = await kaynaklar.proje_listesi(db)
        return {
            "yonetici": kapsam.yonetici, "ajans": kapsam.hesap is None, "hesap": kapsam.hesap, "kisi": kapsam.kisi,
            "okur": kapsam.okur, "bugun": bugun.isoformat(), "ai_hazir": (not kapsam.okur) and _ai_hazir(),
            "hedef_siniri": await _hedef_siniri(db, kapsam),
            "kaynaklar": [x.sozluk() for x in await kaynaklar.kaynak_listesi(db, kapsam.hesap, kapsam.baglam)],
            "projeler": projeler, "musteri_hesaplari": musteri_hesaplari, "ekip": await _ekip(db, kapsam),
            "donemler": [k.donem_sozlugu(d, bugun) for d in ds], "etkin_donem_id": etkin,
            "sabitler": {"donem_turleri": list(s.DONEM_TURLERI), "kr_turleri": list(s.KR_TURLERI), "yonler": list(s.YONLER),
                         "guvenler": list(s.GUVENLER), "gorunurlukler": list(s.GORUNURLUKLER),
                         "para_birimleri": list(s.PARA_BIRIMLERI), "en_cok_kr": s.EN_COK_KR, "en_cok_agirlik": s.EN_COK_AGIRLIK,
                         "hatirlatma_gun": s.HATIRLATMA_GUN, "odak_dk": s.ODAK_DK, "mola_dk": s.MOLA_DK},
        }

    # ------------------------------------------------------------- dönemler
    @router.get("/donemler")
    async def donem_listesi(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        bugun = s.bugun()
        return {"items": [k.donem_sozlugu(d, bugun) for d in await k.donemler(db, kapsam.anahtar)]}

    @router.post("/donemler")
    async def donem_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        g = await _govde(request)
        try:
            v = s.donem_coz(g)
            etkin = s.bool_duzelt(g["etkin"], "etkin") if "etkin" in g else False
        except s.TemelHata as h:
            raise _e(h)
        sayi = int((await db.execute(select(func.count(OkrDonemler.id)).where(OkrDonemler.kapsam == kapsam.anahtar))).scalar() or 0)
        if sayi >= 200:
            raise _hata(409, "donem_siniri", en_cok=200)
        d = OkrDonemler(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, olusturan=kapsam.kisi, durum="acik", **v)
        db.add(d)
        await db.flush()
        if etkin or sayi == 0:
            await _etkin_yap(db, kapsam, d)
        await db.commit()
        await db.refresh(d)
        return k.donem_sozlugu(d)

    async def _etkin_yap(db: AsyncSession, kapsam: Kapsam, d: OkrDonemler) -> None:
        for x in (await db.execute(select(OkrDonemler).where(OkrDonemler.kapsam == kapsam.anahtar, OkrDonemler.etkin.is_(True),
                                                             OkrDonemler.id != d.id))).scalars().all():
            x.etkin = False
        d.etkin = True

    @router.put("/donemler/{did}")
    async def donem_guncelle(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        d = await _donem(db, kapsam, did)
        g = await _govde(request)
        try:
            if "ad" in g:
                d.ad = s.bos_ya_da(g.get("ad"), "ad", 80)
            if any(a in g for a in ("tur", "yil", "ceyrek", "baslangic", "bitis")):
                _acik_mi(d)
                v = s.donem_coz({"tur": d.tur, "yil": d.yil, "ceyrek": d.ceyrek, "baslangic": d.baslangic.isoformat(),
                                 "bitis": d.bitis.isoformat(), **{a: g[a] for a in ("tur", "yil", "ceyrek", "baslangic", "bitis") if a in g}})
                for a in ("tur", "yil", "ceyrek", "baslangic", "bitis"):
                    setattr(d, a, v[a])
            if "etkin" in g and s.bool_duzelt(g.get("etkin"), "etkin"):
                await _etkin_yap(db, kapsam, d)
        except s.TemelHata as h:
            raise _e(h)
        d.updated_at = s.simdi()
        await db.commit()
        await db.refresh(d)
        return k.donem_sozlugu(d)

    @router.delete("/donemler/{did}")
    async def donem_sil(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        d = await _donem(db, kapsam, did)
        sayi = int((await db.execute(select(func.count(OkrHedefler.id)).where(OkrHedefler.donem_id == d.id))).scalar() or 0)
        if sayi:
            raise _hata(409, "donem_dolu", sayi=sayi)
        await db.delete(d)
        await db.commit()
        return {"ok": True}

    @router.get("/donemler/{did}/ozet")
    async def donem_ozeti(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        d = await _donem(db, kapsam, did)
        return await k.donem_ozeti(db, kapsam.anahtar, d, kapsam.kisi)

    @router.post("/donemler/{did}/yenile")
    async def donem_yenile(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Dönemin bütün otomatik KR'lerini şimdi yeniler (panel açılışında da çağrılır)."""
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        d = await _donem(db, kapsam, did)
        return await k.donemi_yenile(db, kapsam.anahtar, kapsam.hesap, d)

    # ------------------------------------------------------------- kapanış
    @router.get("/donemler/{did}/kapanis")
    async def kapanis_bilgisi(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Kapanış ekranı: hedefler + KR'ler, önerilen puan (ilerleme, 0,1 adım), açık KR'ler ve taşınabilecek dönemler."""
        kapsam = kapsam_al(request)
        d = await _donem(db, kapsam, did)
        oz = await k.donem_ozeti(db, kapsam.anahtar, d, kapsam.kisi)
        for h in oz["hedefler"]:
            for x in h["krler"]:
                x["onerilen_puan"] = round(round(x["ilerleme"] * 10) / 10, 1)
                x["acik"] = x["ilerleme"] < 1.0
        hedef_donemler = [k.donem_sozlugu(x) for x in await k.donemler(db, kapsam.anahtar)
                          if x.id != d.id and x.durum == "acik" and x.baslangic >= d.baslangic]
        return {**oz, "hedef_donemler": hedef_donemler}

    @router.post("/donemler/{did}/kapat")
    async def donem_kapat(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        """{puanlar: {kr_id: 0–1}, kapanis_notu, tasi: bool, hedef_donem_id, tasinacaklar?: [kr_id]} — KR puanları, not,
        açık KR'lerin (ilerleme < 1) seçili döneme KOPYASI (hedef başına bir kopya hedef; `tasindi_kaynak_id` bağı).
        Puanı verilmeyen KR'ye ilerlemesi (0,1'e yuvarlı) yazılır."""
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        d = await _donem(db, kapsam, did)
        _acik_mi(d)
        g = await _govde(request)
        try:
            ham_puan = g.get("puanlar") or {}
            if not isinstance(ham_puan, dict):
                raise s.OkrHatasi("puan_gecersiz", "puanlar")
            puanlar = {int(a): s.puan_duzelt(b, f"puanlar.{a}") for a, b in ham_puan.items() if str(a).isdigit()}
            notu = s.bos_ya_da(g.get("kapanis_notu"), "kapanis_notu", 4000, cok_satir=True)
            tasi = s.bool_duzelt(g["tasi"], "tasi") if "tasi" in g else False
            hedef_donem = None
            if tasi:
                hedef_donem = await _donem(db, kapsam, s.kimlik(g.get("hedef_donem_id"), "hedef_donem_id"), alan="hedef_donem_id")
                if hedef_donem.id == d.id or hedef_donem.durum == "kapandi":
                    raise s.OkrHatasi("hedef_donem_gecersiz", "hedef_donem_id")
            secili: Optional[Set[int]] = None
            if isinstance(g.get("tasinacaklar"), list):
                secili = {int(x) for x in g["tasinacaklar"] if isinstance(x, int) or str(x).isdigit()}
        except s.TemelHata as h:
            raise _e(h)
        # Önce otomatik KR'ler son değerleriyle (puan önerisi güncel olsun). Kapanış bütün kapsamı kapsar (özel hedefler
        # dahil): dönem tek bir kez kapanır.
        await k.donemi_yenile(db, kapsam.anahtar, kapsam.hesap, d)
        hs = await k.hedefler(db, kapsam.anahtar, None, d.id)
        harita = await k.krler_haritasi(db, [h.id for h in hs])
        tasinan_hedef = tasinan_kr = 0
        for h in hs:
            acik_krler = []
            for kr in harita.get(h.id, []):
                ilerleme = k.kr_ilerlemesi(kr)
                kr.kapanis_puani = puanlar.get(kr.id, round(round(ilerleme * 10) / 10, 1))
                if ilerleme < 1.0 and (secili is None or kr.id in secili):
                    acik_krler.append(kr)
            if tasi and hedef_donem is not None and acik_krler and h.durum != "taslak":
                await k.kopyala(db, h, acik_krler, hedef_donem, kapsam.kisi)
                tasinan_hedef += 1
                tasinan_kr += len(acik_krler)
            h.durum = "kapandi"
        d.durum = "kapandi"
        d.kapanis_notu = notu
        d.kapandi_at = s.simdi()
        d.kapatan = kapsam.kisi
        if d.etkin and hedef_donem is not None:
            d.etkin = False
            hedef_donem.etkin = True
        await db.commit()
        return {"ok": True, "tasinan_hedef": tasinan_hedef, "tasinan_kr": tasinan_kr,
                "hedef_donem_id": hedef_donem.id if hedef_donem else None}

    # ------------------------------------------------------------- rapor
    async def _rapor_verisi(db: AsyncSession, kapsam: Kapsam, d: OkrDonemler) -> Dict[str, Any]:
        oz = await k.donem_ozeti(db, kapsam.anahtar, d, kapsam.kisi)
        firma = "By Mehmet KURU Dev"
        if kapsam.hesap:
            from services.hesap_ekibi import hesap_adlari

            firma = (await hesap_adlari(db, [kapsam.hesap])).get(kapsam.hesap) or kapsam.hesap
        return {"firma": firma, "olusturma": s.bugun(), "ilerleme": oz["ilerleme"], "beklenen": oz["donem"]["beklenen"],
                "donem": {"ad": oz["donem"]["etiket"], "bas": d.baslangic, "bit": d.bitis, "durum": d.durum,
                          "kapanis_notu": d.kapanis_notu},
                "hedefler": [{"baslik": h["baslik"], "sahip": h["sahip"], "durum": h["durum"], "ilerleme": h["ilerleme"],
                              "krler": [{"baslik": x["baslik"], "tur": x["tur"], "baslangic": x["baslangic"], "hedef": x["hedef"],
                                         "mevcut": x["mevcut"], "para_birimi": x["para_birimi"], "birim": x["birim"],
                                         "ilerleme": x["ilerleme"], "guven": x["guven"], "puan": x["kapanis_puani"],
                                         "kaynak": x["kaynak"], "tamam": x["kilometre_tamam"], "toplam": x["kilometre_toplam"],
                                         "yon": x["yon"], "agirlik": x["agirlik"], "sahip": x["sahip"]}
                                        for x in h["krler"]]} for h in oz["hedefler"]]}

    @router.get("/donemler/{did}/rapor.pdf")
    async def rapor_pdf(did: int, request: Request, dil: str = Query("tr", max_length=5), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if not _dosya_hizi.izin_var_mi(kapsam.kisi or "anonim"):
            raise _hata(429, "cok_hizli")
        d = await _donem(db, kapsam, did)
        veri = s.rapor_pdf(await _rapor_verisi(db, kapsam, d), dil)
        return _dosya_yaniti(veri, "application/pdf", f"okr-{d.id}.pdf")

    @router.get("/donemler/{did}/rapor.csv")
    async def rapor_csv(did: int, request: Request, dil: str = Query("tr", max_length=5), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if not _dosya_hizi.izin_var_mi(kapsam.kisi or "anonim"):
            raise _hata(429, "cok_hizli")
        d = await _donem(db, kapsam, did)
        v = await _rapor_verisi(db, kapsam, d)
        dil_ = "tr" if (dil or "tr")[:2] == "tr" else "en"
        satirlar = []
        for h in v["hedefler"]:
            hy = "" if h["ilerleme"] is None else round(h["ilerleme"] * 100, 1)
            if not h["krler"]:
                satirlar.append([h["baslik"], h["sahip"], h["durum"], hy] + [""] * 13)
            for x in h["krler"]:
                if x["tur"] == "kilometre":
                    bas, hed, mev = 0, x["toplam"], x["tamam"]
                elif x["tur"] == "para":
                    bas, hed, mev = (s.m.kurus_metni(int(x[a] or 0)) for a in ("baslangic", "hedef", "mevcut"))
                else:
                    bas, hed, mev = x["baslangic"], x["hedef"], x["mevcut"]
                satirlar.append([h["baslik"], h["sahip"], h["durum"], hy, x["baslik"], x["tur"], x["yon"], bas, hed, mev,
                                 x["para_birimi"] or "", x["agirlik"], round(x["ilerleme"] * 100, 1), x["guven"] or "",
                                 x["kaynak"] or "", "" if x["puan"] is None else x["puan"], x["sahip"] or ""])
        metin_ = s.csv_metni(s.CSV_BASLIKLARI[dil_], satirlar)
        return _dosya_yaniti(metin_.encode("utf-8"), "text/csv; charset=utf-8", f"okr-{d.id}.csv")

    # ------------------------------------------------------------- hizalama ağacı
    @router.get("/agac")
    async def agac(request: Request, donem_id: Optional[int] = Query(None), db: AsyncSession = Depends(get_db)):
        """Seçili dönemin görünür hedefleri + üst zincirleri (başka dönemde olsa da, görünürse). Düğüm: id, başlık,
        üst, dönem, ilerleme, renk, sahip, durum."""
        kapsam = kapsam_al(request)
        hepsi = await k.hedefler(db, kapsam.anahtar, kapsam.kisi)
        if donem_id is not None:
            await _donem(db, kapsam, donem_id)
        sozluk = {h.id: h for h in hepsi}
        secili = [h for h in hepsi if donem_id is None or h.donem_id == donem_id]
        dahil: Set[int] = set()
        for h in secili:
            x: Optional[OkrHedefler] = h
            while x is not None and x.id not in dahil:
                dahil.add(x.id)
                x = sozluk.get(x.ust_id) if x.ust_id else None
        dugumler = [sozluk[i] for i in sorted(dahil)]
        harita = await k.krler_haritasi(db, list(dahil))
        ds = {d.id: d for d in await k.donemler(db, kapsam.anahtar)}
        bugun = s.bugun()
        sonuc = []
        for h in dugumler:
            d = ds.get(h.donem_id)
            beklenen = s.beklenen_ilerleme(d.baslangic, d.bitis, bugun) if d else 0.0
            ilerleme = s.hedef_ilerleme((k.kr_ilerlemesi(x), int(x.agirlik or 1)) for x in harita.get(h.id, []))
            sonuc.append({"id": h.id, "baslik": h.baslik, "ust_id": h.ust_id if h.ust_id in dahil else None,
                          "donem_id": h.donem_id, "donem": k.donem_sozlugu(d, bugun)["etiket"] if d else None,
                          "ilerleme": None if ilerleme is None else round(ilerleme, 4),
                          "durum_rengi": s.ilerleme_durumu(ilerleme, beklenen), "sahip": h.sahip or "", "durum": h.durum,
                          "gorunurluk": h.gorunurluk, "kr_sayisi": len(harita.get(h.id, [])),
                          "secili_donemde": donem_id is None or h.donem_id == donem_id})
        return {"items": sonuc}

    # ------------------------------------------------------------- hedefler
    @router.post("/hedefler")
    async def hedef_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        g = await _govde(request)
        try:
            d = await _donem(db, kapsam, s.kimlik(g.get("donem_id"), "donem_id"), alan="donem_id")
            _acik_mi(d)
            sinir = await _hedef_siniri(db, kapsam)
            if sinir is not None:
                sayi = int((await db.execute(select(func.count(OkrHedefler.id)).where(
                    OkrHedefler.kapsam == kapsam.anahtar, OkrHedefler.donem_id == d.id))).scalar() or 0)
                if sayi >= sinir:
                    raise s.OkrHatasi("hedef_siniri", "donem_id", durum=409, en_cok=sinir)
            h = OkrHedefler(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, donem_id=d.id, olusturan=kapsam.kisi,
                            musteri_paylasim=False)
            await _hedef_uygula(db, kapsam, h, g, True)
        except s.TemelHata as hata:
            raise _e(hata)
        db.add(h)
        await db.commit()
        await db.refresh(h)
        return k.hedef_sozlugu(h, [], s.beklenen_ilerleme(d.baslangic, d.bitis, s.bugun()))

    @router.get("/hedefler/{hid}")
    async def hedef_ayrinti(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Hedef + KR'ler + her KR'nin check-in geçmişi (son 60) + taşıma geçmişi + üst / alt hedefler."""
        kapsam = kapsam_al(request)
        h = await _hedef(db, kapsam, hid)
        d = await _donem(db, kapsam, h.donem_id)
        krler = (await k.krler_haritasi(db, [h.id])).get(h.id, [])
        bugun = s.bugun()
        sonuc = k.hedef_sozlugu(h, krler, s.beklenen_ilerleme(d.baslangic, d.bitis, bugun))
        gecmis: Dict[int, List[Dict[str, Any]]] = {x.id: [] for x in krler}
        if krler:
            for c in (await db.execute(select(OkrCheckinler).where(OkrCheckinler.kr_id.in_(list(gecmis)))
                                       .order_by(OkrCheckinler.tarih.desc(), OkrCheckinler.id.desc()).limit(60 * len(krler)))).scalars().all():
                if len(gecmis[c.kr_id]) < 60:
                    gecmis[c.kr_id].append(k.checkin_sozlugu(c))
        for x, kr in zip(sonuc["krler"], krler):
            x["checkinler"] = gecmis.get(kr.id, [])
            x["tasima_gecmisi"] = await k.tasima_gecmisi(db, kr) if kr.tasindi_kaynak_id else []
        ust = await _hedef(db, kapsam, h.ust_id) if h.ust_id else None
        altlar = (await db.execute(select(OkrHedefler.id, OkrHedefler.baslik).where(
            OkrHedefler.kapsam == kapsam.anahtar, OkrHedefler.ust_id == h.id, k.gorunur_kosul(kapsam.kisi)))).all()
        sonuc.update({"donem": k.donem_sozlugu(d, bugun), "ust": {"id": ust.id, "baslik": ust.baslik} if ust else None,
                      "altlar": [{"id": i, "baslik": b} for i, b in altlar]})
        return sonuc

    @router.put("/hedefler/{hid}")
    async def hedef_guncelle(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        h = await _hedef(db, kapsam, hid)
        d = await _donem(db, kapsam, h.donem_id)
        _acik_mi(d)
        g = await _govde(request)
        try:
            await _hedef_uygula(db, kapsam, h, g, False)
        except s.TemelHata as hata:
            raise _e(hata)
        h.updated_at = s.simdi()
        krler = (await k.krler_haritasi(db, [h.id])).get(h.id, [])
        await k.hedef_denetle(db, h, kapsam.hesap, krler)
        await db.commit()
        await db.refresh(h)
        return k.hedef_sozlugu(h, krler, s.beklenen_ilerleme(d.baslangic, d.bitis, s.bugun()))

    @router.delete("/hedefler/{hid}")
    async def hedef_sil(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        h = await _hedef(db, kapsam, hid)
        await k.kapsam_temizle(db, h)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- anahtar sonuçlar
    @router.post("/hedefler/{hid}/krler")
    async def kr_ekle(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        h = await _hedef(db, kapsam, hid)
        d = await _donem(db, kapsam, h.donem_id)
        _acik_mi(d, h)
        sayi = int((await db.execute(select(func.count(KR.id)).where(KR.hedef_id == h.id))).scalar() or 0)
        if sayi >= s.EN_COK_KR:
            raise _hata(409, "kr_siniri", en_cok=s.EN_COK_KR)
        g = await _govde(request)
        kr = KR(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, hedef_id=h.id, sira=sayi)
        try:
            await _kr_uygula(db, kapsam, kr, g, True)
        except s.TemelHata as hata:
            raise _e(hata)
        db.add(kr)
        await db.flush()
        if kr.kaynak:
            await k.kr_yenile(db, kr, h, d, kapsam.hesap)
        await k.hedef_denetle(db, h, kapsam.hesap)
        await db.commit()
        await db.refresh(kr)
        return k.kr_sozlugu(kr)

    @router.put("/krler/{kid}")
    async def kr_guncelle(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        kr, h, d = await _kr(db, kapsam, kid)
        _acik_mi(d, h)
        g = await _govde(request)
        try:
            await _kr_uygula(db, kapsam, kr, g, False)
        except s.TemelHata as hata:
            raise _e(hata)
        kr.updated_at = s.simdi()
        await db.flush()
        if kr.kaynak and kr.kaynak_son_yenileme is None:
            await k.kr_yenile(db, kr, h, d, kapsam.hesap)
        await k.hedef_denetle(db, h, kapsam.hesap)
        await db.commit()
        await db.refresh(kr)
        return k.kr_sozlugu(kr)

    @router.delete("/krler/{kid}")
    async def kr_sil(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        kr, h, _d = await _kr(db, kapsam, kid)
        for c in (await db.execute(select(OkrCheckinler).where(OkrCheckinler.kr_id == kr.id))).scalars().all():
            await db.delete(c)
        await db.delete(kr)
        await db.flush()
        await k.hedef_denetle(db, h, kapsam.hesap)
        await db.commit()
        return {"ok": True}

    @router.post("/krler/{kid}/checkin")
    async def checkin(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """{deger, guven, notlar, tarih?} — kilometre taşında {kilometre: [{id, tamam}]}; otomatik kaynaklı KR'de değer
        hesaplanır (gövdedeki değer yok sayılır), check-in yalnız güven + not taşır."""
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        kr, h, d = await _kr(db, kapsam, kid)
        _acik_mi(d, h)
        g = await _govde(request)
        try:
            guven = s.secim(g.get("guven"), "guven", s.GUVENLER) if g.get("guven") not in (None, "") else None
            notlar = s.bos_ya_da(g.get("notlar"), "notlar", 2000, cok_satir=True)
            tarih = s.tarih_duzelt(g.get("tarih"), "tarih") if g.get("tarih") else s.bugun()
            if tarih > s.bugun():
                raise s.OkrHatasi("tarih_ileride", "tarih")
            if kr.kaynak:
                deger = float(kr.mevcut_deger or 0)
            elif kr.tur == "kilometre":
                liste = k.kilometre_listesi(kr)
                isaret = g.get("kilometre")
                if isinstance(isaret, list):
                    durumlar = {str(x.get("id")): bool(x.get("tamam")) for x in isaret if isinstance(x, dict)}
                    for x in liste:
                        if x["id"] in durumlar:
                            x["tamam"] = durumlar[x["id"]]
                    kr.kilometre_taslari = s.json_yaz(liste)
                deger = float(s.kilometre_sayilari(liste)[0])
            else:
                if g.get("deger") in (None, ""):
                    raise s.OkrHatasi("zorunlu", "deger")
                deger = s.deger_coz(g.get("deger"), kr.tur, "deger")
        except s.TemelHata as hata:
            raise _e(hata)
        c = await k.checkin_yaz(db, kr, h, kapsam.hesap, deger=deger, guven=guven, notlar=notlar, tarih=tarih, yazan=kapsam.kisi)
        await k.hedef_denetle(db, h, kapsam.hesap)
        await db.commit()
        await db.refresh(kr)
        return {"kr": k.kr_sozlugu(kr), "checkin": k.checkin_sozlugu(c)}

    @router.get("/krler/{kid}/checkinler")
    async def checkinler(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        kr, _h, _d = await _kr(db, kapsam, kid)
        satirlar = (await db.execute(select(OkrCheckinler).where(OkrCheckinler.kr_id == kr.id)
                                     .order_by(OkrCheckinler.tarih.desc(), OkrCheckinler.id.desc()).limit(500))).scalars().all()
        return {"items": [k.checkin_sozlugu(c) for c in satirlar], "tasima_gecmisi": await k.tasima_gecmisi(db, kr)}

    @router.post("/krler/{kid}/yenile")
    async def kr_yenile(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """"Şimdi yenile": otomatik kaynaklı KR'nin değerini hemen hesaplar."""
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        kr, h, d = await _kr(db, kapsam, kid)
        _acik_mi(d)
        if not kr.kaynak:
            raise _hata(409, "kaynak_yok")
        r = await k.kr_yenile(db, kr, h, d, kapsam.hesap)
        await k.hedef_denetle(db, h, kapsam.hesap)
        await db.commit()
        await db.refresh(kr)
        return {"kr": k.kr_sozlugu(kr), "degisti": r["degisti"], "hata": r["hata"]}

    @router.post("/krler/{kid}/odak")
    async def odak(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Odak sayacı (25/5) oturumu bitti: KR'ye not (değer değişmez; `tur=odak`, süre dakika)."""
        kapsam = kapsam_al(request, yaz=True)
        _yaz(kapsam)
        kr, h, d = await _kr(db, kapsam, kid)
        _acik_mi(d, h)
        g = await _govde(request)
        try:
            sure = s.tam_sayi(g.get("sure_dk", s.ODAK_DK), "sure_dk", 1, s.EN_COK_ODAK_DK)
            notlar = s.bos_ya_da(g.get("notlar"), "notlar", 2000, cok_satir=True)
        except s.TemelHata as hata:
            raise _e(hata)
        c = await k.checkin_yaz(db, kr, h, kapsam.hesap, deger=float(kr.mevcut_deger or 0), guven=None, notlar=notlar,
                                tarih=s.bugun(), yazan=kapsam.kisi, tur="odak", sure_dk=sure)
        await db.commit()
        return {"checkin": k.checkin_sozlugu(c)}

    # ------------------------------------------------------------- AI ile KR öner
    @router.post("/ai/kr-oner")
    async def ai_kr_oner(request: Request, db: AsyncSession = Depends(get_db)):
        """{hedef_id? | baslik, aciklama?, sayi?} → {oneriler: [...]} — KAYDEDİLMEZ (kullanıcı seçip ekler)."""
        from services import yapay_zeka as ai

        kapsam = kapsam_al(request, yaz=True)
        if not _ai_hizi.izin_var_mi(kapsam.kisi or "anonim"):
            raise _hata(429, "cok_hizli")
        if not _ai_hazir():
            raise _hata(503, "ai_kapali")
        g = await _govde(request)
        try:
            mevcut: List[str] = []
            if g.get("hedef_id"):
                h = await _hedef(db, kapsam, s.kimlik(g.get("hedef_id"), "hedef_id"), alan="hedef_id")
                baslik, aciklama = h.baslik, h.aciklama or ""
                mevcut = [x.baslik for x in (await k.krler_haritasi(db, [h.id])).get(h.id, [])]
            else:
                baslik = s.metin(g.get("baslik"), "baslik", 200, zorunlu=True)
                aciklama = s.metin(g.get("aciklama"), "aciklama", 2000, cok_satir=True)
            sayi = s.tam_sayi(g.get("sayi", 3), "sayi", 1, s.EN_COK_ONERI)
        except s.TemelHata as hata:
            raise _e(hata)
        if not await ai.sayac_artir(db, s.AI_KAPSAM, s.AI_GUNLUK_BUTCE):
            raise _hata(429, "ai_butce")
        dil = ai.dil_coz(g.get("dil"))
        try:
            yanit = await ai.metin_uret(s.ai_mesajlari(dil=dil, hedef=baslik, aciklama=aciklama, mevcut=mevcut, sayi=sayi),
                                        model=ai.varsayilan_model(), max_tokens=1200, temperature=0.4, amac="okr_kr")
        except ai.YapayZekaHatasi as h:
            raise _hata(h.durum, h.kod)
        try:
            oneriler = s.ai_yanitini_coz(yanit.icerik, sayi)
        except s.TemelHata:
            if not yanit.sahte:
                raise _hata(502, "ai_bicim")
            # Test ortamı (ENVIRONMENT=test): sahte model JSON vermiyor → belirlenimci öneriler.
            oneriler = s.sahte_oneriler(baslik, sayi)
        await ai.token_ekle(db, s.AI_KAPSAM, yanit)
        return {"oneriler": oneriler}


_uclari_kur(musteri_router, _musteri_kapsami)
_uclari_kur(yonetici_router, _yonetici_kapsami)


@yonetici_router.get("/musteri-hesaplari")
async def yonetici_musteri_hesaplari(db: AsyncSession = Depends(get_db)):
    """Hedefe bağlanabilecek müşteri hesapları + o hesapla paylaşılan hedef sayısı."""
    from services.moduller import musteri_listesi

    paylasilan = dict((await db.execute(select(OkrHedefler.musteri_email, func.count(OkrHedefler.id)).where(
        OkrHedefler.kapsam == s.AJANS_KAPSAMI, OkrHedefler.musteri_paylasim.is_(True)).group_by(OkrHedefler.musteri_email))).all())
    return {"items": [{**x, "paylasilan": int(paylasilan.get(x["eposta"], 0))} for x in await musteri_listesi(db)]}


@paylasim_router.get("")
async def paylasilan_hedefler(request: Request, db: AsyncSession = Depends(get_db)):
    """Ajansın bu hesaba bağlayıp PAYLAŞTIĞI hedefler (salt okunur). Modül gerekmez; etkin hesap jetondan/başlıktan."""
    b = izin_iste(request, "projeler", IZIN, IZIN_OKUR)
    hesap = b.hesap_email
    hs = (await db.execute(select(OkrHedefler).where(
        OkrHedefler.kapsam == s.AJANS_KAPSAMI, OkrHedefler.musteri_email == hesap, OkrHedefler.musteri_paylasim.is_(True),
        OkrHedefler.gorunurluk == "ekip", OkrHedefler.durum.in_(("etkin", "kapandi")))
        .order_by(OkrHedefler.donem_id.desc(), OkrHedefler.sira, OkrHedefler.id).limit(50))).scalars().all()
    if not hs:
        return {"items": []}
    harita = await k.krler_haritasi(db, [h.id for h in hs])
    ds = {d.id: d for d in (await db.execute(select(OkrDonemler).where(
        OkrDonemler.id.in_({h.donem_id for h in hs}), OkrDonemler.kapsam == s.AJANS_KAPSAMI))).scalars().all()}
    bugun = s.bugun()
    sonuc = []
    for h in hs:
        d = ds.get(h.donem_id)
        if d is None:
            continue
        beklenen = s.beklenen_ilerleme(d.baslangic, d.bitis, bugun)
        x = k.hedef_sozlugu(h, harita.get(h.id, []), beklenen, paylasim=True)
        x["donem"] = {"etiket": k.donem_sozlugu(d, bugun)["etiket"], "tur": d.tur, "yil": d.yil, "ceyrek": d.ceyrek,
                      "ad": d.ad or "", "baslangic": d.baslangic.isoformat(), "bitis": d.bitis.isoformat(),
                      "beklenen": round(beklenen, 4), "durum": d.durum}
        x["kapandi"] = h.durum == "kapandi"
        sonuc.append(x)
    return {"items": sonuc}


router = (yonetici_router, musteri_router, paylasim_router)
