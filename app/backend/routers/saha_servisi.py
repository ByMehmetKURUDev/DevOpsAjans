"""Faz 6S — Saha servisi: iş emri, sevk panosu, teknisyen ekranı, servis müşterisi sayfası.

Müşteri (`/api/v1/saha-servisim`; modül `saha_servisi` açık + hesap ekibi izni
`saha_yonetim` YA DA `saha_teknisyen`) — etkin hesap = servis firması:
  GET  /meta                                    seçenekler, sınırlar, kim olduğum (yönetim/teknisyen), rıza
  GET|PUT /ayarlar                              firma künyesi, KDV, saklama, bildirimler, kanca   [yönetim]
  GET|POST /teknisyenler, PUT|DELETE /teknisyenler/{tid}  dispatch satırları (`teknisyen_siniri`) [yönetim]
  GET|POST|DELETE /rizam                        kendi konum rızam (KVKK; zaman + metin sürümü)    [teknisyen]
  GET|POST /musteriler, GET|PUT|DELETE /musteriler/{mid}                                          [yönetim]
  POST /musteriler/{mid}/lokasyonlar, PUT|DELETE /lokasyonlar/{lid}                               [yönetim]
  POST /musteriler/{mid}/cihazlar, PUT|DELETE /cihazlar/{cid}, GET /cihazlar/{cid}/gecmis         [yönetim]
  POST /cihazlar/{cid}/bakim-is-emri            bakım zamanı gelen cihaz → bakım iş emri           [yönetim]
  GET|POST /sablonlar, PUT|DELETE /sablonlar/{sid}   kontrol listesi şablonları                   [yönetim]
  GET /malzemeler (teknisyen de okur), POST /malzemeler, PUT|DELETE /malzemeler/{id}             [yönetim]
  GET|POST /is-emirleri, GET|PUT|DELETE /is-emirleri/{id}  (GET: atanan teknisyen de)             [yönetim]
  PUT  /is-emirleri/{id}/plan                   sevk panosu: teknisyen + zaman (sürükle-bırak)     [yönetim]
  GET  /pano?gun=&gorunum=gun|hafta             teknisyen × saat çizelgesi + atanmamış kuyruk     [yönetim]
  GET  /islerim?gun=                            bugünkü (ve kalan açık) işlerim                    [teknisyen]
  POST /is-emirleri/{id}/durum                  durum geçişi (+ başla/bitir anında rızaya bağlı tek seferlik konum)
  PUT  /is-emirleri/{id}/kontrol                kontrol listesi yanıtları
  PUT  /is-emirleri/{id}/saha                   teknisyen notu, işçilik süresi, takip gerekli
  POST /is-emirleri/{id}/fotograflar, DELETE /is-emirleri/{id}/fotograflar/{fid}  (EXIF silinir, WebP)
  POST /is-emirleri/{id}/malzemeler, DELETE /is-emirleri/{id}/malzemeler/{kid}  (stok düşümü)
       Faz 6Q: `stok_urun_id` ile Stok ve POS ürünü (iş emri tamamlanınca stoktan `cikis`, yeniden açılınca ters)
  GET  /stok-urunleri?ara=                      stok ürünü arama (ad/barkod/SKU; MALİYET YOK) — bağlantı açıksa
  POST /is-emirleri/{id}/yeniden-ac             tamamlanmış işi yeniden aç (iste); düşülen stok geri  [yönetim]
  POST /is-emirleri/{id}/imza                   yerinde müşteri imzası (canvas PNG + ad + zaman)
  GET  /is-emirleri/{id}/pdf                    servis formu PDF'i
  POST /is-emirleri/{id}/musteri-baglantisi     servis müşterisinin imzalı sayfası (adres)         [yönetim]
  GET  /raporlar?bas=&bit=, GET /bakim?gun=     teknisyen başına rapor; bakım zamanı gelen cihazlar [yönetim]

Teknisyen (yalnız `saha_teknisyen`) yalnız KENDİNE atanan işleri görür ve değiştirir (başkasınınki 404).

Yönetici (`/api/v1/saha/yonetim`, ajans): `GET /hesaplar` + yukarıdaki okuma uçlarının aynısı
`?hesap=<servis firması>` ile — SALT OKUNUR (destek amaçlı).

Herkese açık (oturumsuz):
  GET  /api/v1/saha/servis/{jeton}              servis müşterisinin imzalı sayfası (iş durumu, aydınlatma)
  GET  /api/v1/saha/servis/{jeton}/pdf          servis formu (iş tamamlandıysa)
  POST /api/v1/saha/servis/{jeton}/memnuniyet   puan (1–5) + yorum; Google yorum bağlantısı HERKESE aynı
  GET  /api/v1/saha/gorsel/{anahtar}?b=&i=      kısa ömürlü imzalı görsel (fotoğraf/imza)
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from models.saha_servisi import (
    SahaAyarlari,
    SahaCihazlari,
    SahaDurumGecmisi,
    SahaIsAtamalari,
    SahaIsCihazlari,
    SahaIsEmirleri,
    SahaIsFotograflari,
    SahaLokasyonlari,
    SahaMalzemeKullanimi,
    SahaMalzemeleri,
    SahaMusterileri,
    SahaSablonlari,
    SahaTeknisyenleri,
)
from services import saha_kayit as sk
from services import saha_servisi as s
from services import saha_stok as sst
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = s.MODUL

acik_router = APIRouter(prefix="/api/v1/saha/servis", tags=["saha_servisi"])
gorsel_router = APIRouter(prefix="/api/v1/saha/gorsel", tags=["saha_servisi"])
yonetici_router = APIRouter(prefix="/api/v1/saha/yonetim", tags=["saha_servisi"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/saha-servisim",
    tags=["saha_servisi"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(s.IZIN_YONETIM, s.IZIN_TEKNISYEN))],
)

#: Panel (kişi başı): dakikada 120 yazma, 30 fotoğraf. Herkese açık (IP özeti): dakikada 30; puan 10 dk'da 5.
#: Faz 7H: herkese açık iki sayaç veritabanında (sunucu uyanınca sıfırlanmıyor).
_yazma_hizi = HizSiniri(120, 60.0)
_foto_hizi = HizSiniri(30, 60.0)
_acik_hizi = KaliciHizSiniri("saha-acik", 30, 60.0)
_puan_hizi = KaliciHizSiniri("saha-puan", 5, 600.0)
_gorsel_hizi = HizSiniri(240, 60.0)

ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow",
                  "Referrer-Policy": "no-referrer"}


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _foto_hizi, _acik_hizi, _puan_hizi, _gorsel_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    hesap: str
    kisi: str
    #: Yönetim yetkisi (`saha_yonetim` ya da hesap sahibi; ajans yöneticisi okumada).
    yonetim: bool
    teknisyen_izni: bool
    #: Ajans yöneticisi: salt okunur destek görünümü.
    ajans: bool = False


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _s_hatasi(h: s.SahaHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _musteri_kapsami(request: Request) -> Kapsam:
    b = izin_iste(request, s.IZIN_YONETIM, s.IZIN_TEKNISYEN)
    return Kapsam(b.hesap_email, b.kisi_email, b.izin_var(s.IZIN_YONETIM), b.izin_var(s.IZIN_TEKNISYEN))


def _yonetici_kapsami(request: Request) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    hesap = (request.query_params.get("hesap") or "").strip().lower()
    if not hesap or "@" not in hesap or len(hesap) > 254:
        raise _hata(400, "hesap_gerekli", alan="hesap")
    return Kapsam(hesap, (getattr(kullanici, "email", "") or "").strip().lower(), True, False, ajans=True)


def _yonetim_iste(k: Kapsam) -> None:
    if not k.yonetim:
        raise _hata(403, "hesap_izni_yok", izin=s.IZIN_YONETIM)


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    """Faz 7H: herkese açık uçların veritabanı destekli sayacı ((sınırlayıcı, anahtar) çiftleri)."""
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


async def _teknisyen(db: AsyncSession, k: Kapsam) -> Optional[SahaTeknisyenleri]:
    if k.ajans:
        return None
    return await sk.teknisyen_bul(db, k.hesap, k.kisi)


async def _is_emri(db: AsyncSession, k: Kapsam, is_id: int) -> SahaIsEmirleri:
    """Hesabın iş emri; yönetim yetkisi yoksa YALNIZ kişiye atanmış olan (yoksa 404 — varlığı sızmasın)."""
    ie = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == is_id, SahaIsEmirleri.hesap_email == k.hesap))).scalars().first()
    if ie is None:
        raise _hata(404, "bulunamadi")
    if not k.yonetim:
        t = await _teknisyen(db, k)
        if t is None or not k.teknisyen_izni:
            raise _hata(404, "bulunamadi")
        atanan = (await sk.atama_haritasi(db, [ie.id]))[ie.id]
        if t.id not in atanan:
            raise _hata(404, "bulunamadi")
    return ie


def _tarih_param(ham: Optional[str], alan: str, varsayilan: date) -> date:
    if not ham:
        return varsayilan
    try:
        return s.tarih_duzelt(ham, alan, bos_olabilir=False)
    except s.SahaHatasi as h:
        raise _s_hatasi(h)


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _teknisyen_sozlugu(t: SahaTeknisyenleri) -> Dict[str, Any]:
    return {
        "id": t.id, "eposta": t.eposta, "ad": t.ad, "telefon": t.telefon, "renk": t.renk, "aktif": bool(t.aktif),
        "sira": int(t.sira or 0), "stok_konum_id": t.stok_konum_id,
        "konum_rizasi": s.riza_gecerli_mi(t.konum_rizasi_at, t.konum_rizasi_surumu, t.konum_rizasi_geri_at),
        "konum_rizasi_at": s.iso(t.konum_rizasi_at), "konum_rizasi_surumu": t.konum_rizasi_surumu,
        "konum_rizasi_geri_at": s.iso(t.konum_rizasi_geri_at),
    }


def _musteri_sozlugu(m: SahaMusterileri) -> Dict[str, Any]:
    return {
        "id": m.id, "tur": m.tur, "ad": m.ad, "firma": m.firma, "eposta": m.eposta, "telefon": m.telefon,
        "vergi_no": m.vergi_no, "notlar": m.notlar or "", "dil": m.dil, "anonim": bool(m.anonim),
        "son_is_at": s.iso(m.son_is_at), "created_at": s.iso(m.created_at),
    }


def _lokasyon_sozlugu(l: SahaLokasyonlari) -> Dict[str, Any]:
    tam = ", ".join(x for x in (l.adres, " ".join(y for y in (l.posta_kodu, l.ilce) if y), l.il) if x)
    return {
        "id": l.id, "musteri_id": l.musteri_id, "ad": l.ad, "adres": l.adres or "", "ilce": l.ilce or "", "il": l.il or "",
        "posta_kodu": l.posta_kodu or "", "notlar": l.notlar or "", "tam_adres": tam,
        "harita": s.harita_baglantisi(tam) if tam else None,
    }


def _cihaz_sozlugu(c: SahaCihazlari) -> Dict[str, Any]:
    vade = s.bakim_vadesi(c.son_bakim, c.kurulum_tarihi, c.bakim_periyot_ay)
    return {
        "id": c.id, "musteri_id": c.musteri_id, "lokasyon_id": c.lokasyon_id, "tur": c.tur, "marka": c.marka or "",
        "model": c.model or "", "seri_no": c.seri_no or "", "kurulum_tarihi": s.iso(c.kurulum_tarihi),
        "garanti_bitis": s.iso(c.garanti_bitis), "son_bakim": s.iso(c.son_bakim), "bakim_periyot_ay": c.bakim_periyot_ay,
        "bakim_vadesi": s.iso(vade), "notlar": c.notlar or "", "aktif": bool(c.aktif),
        "garantide": bool(c.garanti_bitis and c.garanti_bitis >= s.tr_bugun()),
    }


def _sablon_sozlugu(t: SahaSablonlari) -> Dict[str, Any]:
    return {"id": t.id, "ad": t.ad, "is_turu": t.is_turu, "maddeler": s.json_yukle(t.maddeler, []) or [],
            "aktif": bool(t.aktif), "hazir": t.hazir}


def _malzeme_sozlugu(m: SahaMalzemeleri) -> Dict[str, Any]:
    return {"id": m.id, "ad": m.ad, "kod": m.kod or "", "birim": m.birim, "birim_fiyat": int(m.birim_fiyat or 0),
            "stok": m.stok, "kritik_stok": m.kritik_stok, "aktif": bool(m.aktif),
            "kritik": m.stok is not None and m.kritik_stok is not None and m.stok <= m.kritik_stok}


def _ayar_sozlugu(a: SahaAyarlari) -> Dict[str, Any]:
    d = {k: getattr(a, k) for k in (
        "firma_adi", "telefon", "eposta", "adres", "vergi_no", "varsayilan_dil", "para_birimi", "kdv_orani", "saklama_ay",
        "imza_zorunlu", "bildirim_planlandi", "bildirim_yolda", "bildirim_tamamlandi", "memnuniyet_acik",
        "yorum_sayfasi_id", "randevu_kancasi", "randevu_is_turu", "bakim_on_gun")}
    # Faz 6Q: NULL (eski hesap) = kapalı.
    d["stoktan_dus"] = bool(a.stoktan_dus)
    d["stok_konum_id"] = a.stok_konum_id
    return d


async def _isleri_sozlukle(db: AsyncSession, isler: List[SahaIsEmirleri]) -> List[Dict[str, Any]]:
    if not isler:
        return []
    idler = [x.id for x in isler]
    atamalar = await sk.atama_haritasi(db, idler)
    t_idler = {t for v in atamalar.values() for t in v}
    teknisyenler = {t.id: t for t in (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.id.in_(t_idler or {0})))).scalars().all()}
    musteriler = {m.id: m for m in (await db.execute(select(SahaMusterileri).where(
        SahaMusterileri.id.in_({x.musteri_id for x in isler})))).scalars().all()}
    l_idler = {x.lokasyon_id for x in isler if x.lokasyon_id}
    lokasyonlar = {l.id: l for l in (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.id.in_(l_idler or {0})))).scalars().all()}
    sonuc = []
    for ie in isler:
        m = musteriler.get(ie.musteri_id)
        l = lokasyonlar.get(ie.lokasyon_id) if ie.lokasyon_id else None
        sonuc.append({
            "id": ie.id, "no": ie.no, "tur": ie.tur, "oncelik": ie.oncelik, "durum": ie.durum, "baslik": ie.baslik,
            "musteri_id": ie.musteri_id, "musteri_ad": m.ad if m else "—", "musteri_telefon": m.telefon if m else None,
            "lokasyon_id": ie.lokasyon_id, "adres": _lokasyon_sozlugu(l)["tam_adres"] if l else None,
            "plan_bas": s.iso(ie.plan_bas), "plan_bit": s.iso(sk.plan_bitisi(ie)), "tahmini_dk": int(ie.tahmini_dk or 60),
            "teknisyenler": [{"id": tid, "ad": teknisyenler[tid].ad, "renk": teknisyenler[tid].renk}
                             for tid in atamalar.get(ie.id, []) if tid in teknisyenler],
            "basla_at": s.iso(ie.basla_at), "bitir_at": s.iso(ie.bitir_at), "memnuniyet_puan": ie.memnuniyet_puan,
            "imzali": bool(ie.imza_anahtari), "randevu_id": ie.randevu_id, "created_at": s.iso(ie.created_at),
        })
    return sonuc


async def _is_ayrintisi(db: AsyncSession, k: Kapsam, ie: SahaIsEmirleri) -> Dict[str, Any]:
    temel = (await _isleri_sozlukle(db, [ie]))[0]
    m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == ie.musteri_id))).scalars().first()
    l = (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.id == ie.lokasyon_id))).scalars().first() if ie.lokasyon_id else None
    c_idler = (await sk.cihaz_haritasi(db, [ie.id]))[ie.id]
    cihazlar = (await db.execute(select(SahaCihazlari).where(SahaCihazlari.id.in_(c_idler or [0])))).scalars().all()
    fotolar = (await db.execute(select(SahaIsFotograflari).where(SahaIsFotograflari.is_emri_id == ie.id)
                                .order_by(SahaIsFotograflari.id))).scalars().all()
    malzemeler = (await db.execute(select(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.is_emri_id == ie.id)
                                   .order_by(SahaMalzemeKullanimi.id))).scalars().all()
    gecmis = (await db.execute(select(SahaDurumGecmisi).where(SahaDurumGecmisi.is_emri_id == ie.id)
                               .order_by(SahaDurumGecmisi.id))).scalars().all()
    tek = await _teknisyen(db, k)
    atanan = [x["id"] for x in temel["teknisyenler"]]
    d = {
        **temel,
        "aciklama": ie.aciklama or "",
        "musteri": _musteri_sozlugu(m) if m else None,
        "lokasyon": _lokasyon_sozlugu(l) if l else None,
        "cihazlar": [_cihaz_sozlugu(c) for c in cihazlar],
        "sablon_id": ie.sablon_id,
        "kontrol_listesi": s.json_yukle(ie.kontrol_listesi, []) or [],
        "kontrol_yanitlari": s.json_yukle(ie.kontrol_yanitlari, {}) or {},
        "teknisyen_notu": ie.teknisyen_notu or "",
        "iscilik_dk": ie.iscilik_dk,
        "iscilik_ucreti": int(ie.iscilik_ucreti or 0),
        "takip_gerekli": bool(ie.takip_gerekli),
        "ertele_sayisi": int(ie.ertele_sayisi or 0),
        "zaman": {a: s.iso(getattr(ie, f"{a}_at")) for a in ("planlandi", "yolda", "basla", "bitir", "iptal", "ertele")},
        "fotograflar": [{"id": f.id, "tur": f.tur, "madde_id": f.madde_id, "url": s.gorsel_adresi(f.anahtar),
                         "kucuk_url": s.gorsel_adresi(f.kucuk_anahtar), "genislik": f.genislik, "yukseklik": f.yukseklik,
                         "created_at": s.iso(f.created_at)} for f in fotolar],
        "foto_siniri": s.FOTO_SINIRI,
        "malzemeler": [sst.satir_sozlugu(x) for x in malzemeler],
        "gecmis": [{"eski": g.eski, "yeni": g.yeni, "kisi": g.kisi, "neden": g.neden, "konum_alindi": bool(g.konum_alindi),
                    "zaman": s.iso(g.zaman)} for g in gecmis],
        "imza": {"ad": ie.imza_ad, "at": s.iso(ie.imza_at), "url": s.gorsel_adresi(ie.imza_anahtari)} if ie.imza_anahtari else None,
        "memnuniyet": {"puan": ie.memnuniyet_puan, "yorum": ie.memnuniyet_yorum, "at": s.iso(ie.memnuniyet_at)}
        if ie.memnuniyet_puan else None,
        "konum_alindi": {"basla": ie.basla_enlem is not None, "bitir": ie.bitir_enlem is not None,
                         "indirgendi_at": s.iso(ie.konum_indirgendi_at)},
        "benim_isim": bool(tek and tek.id in atanan),
        "anonim": bool(ie.anonim),
    }
    if k.yonetim:
        d["konum"] = {
            "basla": {"enlem": ie.basla_enlem, "boylam": ie.basla_boylam, "dogruluk": ie.basla_dogruluk} if ie.basla_enlem is not None else None,
            "bitir": {"enlem": ie.bitir_enlem, "boylam": ie.bitir_boylam, "dogruluk": ie.bitir_dogruluk} if ie.bitir_enlem is not None else None,
        }
        if not k.ajans:
            d["musteri_baglantisi"] = s.musteri_adresi(s.musteri_jetonu(ie.id, ie.uid))
    return d


# ---------------------------------------------------------------------------
# PDF verisi
# ---------------------------------------------------------------------------
async def pdf_uret(db: AsyncSession, ie: SahaIsEmirleri, dil: Optional[str] = None) -> bytes:
    from services.saha_pdf import servis_formu_pdf

    a = await sk.ayarlar(db, ie.hesap_email)
    m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == ie.musteri_id))).scalars().first()
    dil = dil or (m.dil if m else None) or a.varsayilan_dil or "tr"
    atanan = (await sk.atama_haritasi(db, [ie.id]))[ie.id]
    teknik = [t.ad for t in (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.id.in_(atanan or [0])))).scalars().all()]
    c_idler = (await sk.cihaz_haritasi(db, [ie.id]))[ie.id]
    cihazlar = (await db.execute(select(SahaCihazlari).where(SahaCihazlari.id.in_(c_idler or [0])))).scalars().all()
    yanitlar = s.json_yukle(ie.kontrol_yanitlari, {}) or {}
    fotolu = set(await sk.foto_maddeleri(db, ie.id))
    kontrol = []
    for madde in s.json_yukle(ie.kontrol_listesi, []) or []:
        deger = (madde["id"] in fotolu) if madde.get("tur") == "foto" else yanitlar.get(madde["id"])
        kontrol.append({**madde, "deger": deger})
    malzemeler = (await db.execute(select(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.is_emri_id == ie.id)
                                   .order_by(SahaMalzemeKullanimi.id))).scalars().all()
    sure = int((s.utc(ie.bitir_at) - s.utc(ie.basla_at)).total_seconds() // 60) if ie.basla_at and ie.bitir_at else None
    imza_png = await sk.gorsel_oku(db, ie.imza_depo, ie.imza_anahtari) if ie.imza_anahtari else None
    foto_sayisi = int((await db.execute(select(func.count(SahaIsFotograflari.id)).where(
        SahaIsFotograflari.is_emri_id == ie.id))).scalar() or 0)
    pdil = "tr" if dil == "tr" else "en"
    v = {
        "firma": {"ad": a.firma_adi or ie.hesap_email, "telefon": a.telefon, "eposta": a.eposta, "adres": a.adres,
                  "vergi_no": a.vergi_no},
        "is": {"no": ie.no, "tarih": s.yerel_zaman(ie.bitir_at or ie.plan_bas or ie.created_at, pdil)[:10], "durum": ie.durum,
               "tur": ie.tur, "oncelik": ie.oncelik, "baslik": ie.baslik, "aciklama": ie.aciklama,
               "plan": s.yerel_zaman(ie.plan_bas, pdil) if ie.plan_bas else None,
               "basla": s.yerel_zaman(ie.basla_at, pdil) if ie.basla_at else None,
               "bitir": s.yerel_zaman(ie.bitir_at, pdil) if ie.bitir_at else None, "sure_dk": sure},
        "musteri": {"ad": m.ad if m else None, "firma": m.firma if m else None, "telefon": m.telefon if m else None},
        "adres": await sk.adres_metni(db, ie),
        "teknisyenler": teknik,
        "cihazlar": [{"tur": c.tur, "marka": c.marka, "model": c.model, "seri_no": c.seri_no} for c in cihazlar],
        "kontrol": kontrol,
        "malzemeler": [{"ad": x.ad, "miktar": x.miktar, "birim": x.birim, "birim_fiyat": x.birim_fiyat} for x in malzemeler],
        "iscilik_ucreti": int(ie.iscilik_ucreti or 0), "iscilik_dk": ie.iscilik_dk,
        "kdv_orani": int(a.kdv_orani or 0), "para_birimi": a.para_birimi or "TRY",
        "teknisyen_notu": ie.teknisyen_notu,
        "imza_png": imza_png, "imza_ad": ie.imza_ad, "imza_at": s.yerel_zaman(ie.imza_at, pdil) if ie.imza_at else None,
        "foto_sayisi": foto_sayisi,
    }
    return servis_formu_pdf(v, dil)


def _pdf_yaniti(veri: bytes, no: str, ek: Optional[Dict[str, str]] = None) -> Response:
    from services.pdf_belge import dosya_adi

    return Response(content=veri, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{dosya_adi("servis-formu", no)}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", **(ek or {})})


# ---------------------------------------------------------------------------
# Uçlar (okuma iki panelde; yazma yalnız müşteri panelinde)
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam], yazma: bool) -> None:
    # ------------------------------------------------------------------ meta, ayarlar
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        a = await sk.ayarlar(db, k.hesap)
        if not k.ajans and k.yonetim:
            await sk.tohumla(db, a)
        t = await _teknisyen(db, k)
        stok_modulu = await sst.stok_modulu_acik(db, k.hesap)
        return {
            # Faz 6Q: Stok ve POS bağlantısı (modül açık mı, "stoktan düş" açık mı → iş emrinde stok ürünü aranır).
            "stok": {"modul": stok_modulu, "acik": bool(stok_modulu and a.stoktan_dus)},
            "hesap": k.hesap, "yonetim": k.yonetim, "teknisyen": bool(k.teknisyen_izni and t is not None and t.aktif),
            "teknisyen_izni": k.teknisyen_izni, "salt_okunur": k.ajans, "benim": _teknisyen_sozlugu(t) if t else None,
            "riza_surumu": s.RIZA_SURUMU, "konum_saklama_gun": s.KONUM_SAKLAMA_GUN,
            "teknisyen_siniri": await sk.modul_ayari(db, k.hesap, "teknisyen_siniri", s.VARSAYILAN_TEKNISYEN_SINIRI),
            "aylik_is_emri_siniri": await sk.modul_ayari(db, k.hesap, "aylik_is_emri_siniri", s.VARSAYILAN_AYLIK_SINIR),
            "bu_ay_is_emri": await sk.bu_ay_is_emri_sayisi(db, k.hesap),
            "is_turleri": list(s.IS_TURLERI), "oncelikler": list(s.ONCELIKLER), "durumlar": list(s.DURUMLAR),
            "gecisler": {d: list(v) for d, v in s.GECISLER.items()},
            "teknisyen_gecisleri": [list(x) for x in sorted(s.TEKNISYEN_GECISLERI)],
            "madde_turleri": list(s.MADDE_TURLERI), "birimler": list(s.BIRIMLER), "diller": list(s.DILLER),
            "para_birimleri": list(s.PARA_BIRIMLERI), "foto_siniri": s.FOTO_SINIRI,
            "ayarlar": {"firma_adi": a.firma_adi, "para_birimi": a.para_birimi, "kdv_orani": a.kdv_orani,
                        "imza_zorunlu": bool(a.imza_zorunlu)},
        }

    @router.get("/ayarlar")
    async def ayarlar_oku(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        a = await sk.ayarlar(db, k.hesap)
        from models.kartvizit import YorumSayfalari

        from services.moduller import modul_acik_mi
        from services.notify import _env

        sayfalar = (await db.execute(select(YorumSayfalari.id, YorumSayfalari.isletme_adi).where(
            YorumSayfalari.hesap_email == k.hesap, YorumSayfalari.aktif.is_(True)))).all()
        # Dış bağımlılıklar: ön yüz ilgili ayarı devre dışı bırakıp nedenini yazıyor.
        stok_modulu = await sst.stok_modulu_acik(db, k.hesap)
        return {**_ayar_sozlugu(a), "yorum_sayfalari": [{"id": i, "ad": ad} for i, ad in sayfalar],
                "eposta_kanali": bool(_env("RESEND_API_KEY") or _env("SMTP_HOST")),
                "randevu_modulu": await modul_acik_mi(db, k.hesap, "randevu"),
                "yorum_modulu": await modul_acik_mi(db, k.hesap, "google_yorum_sayfasi"),
                # Faz 6Q: Stok ve POS modülü kapalıysa "stoktan düş" seçeneği gösterilmez (konum listesi de yok).
                "stok_modulu": stok_modulu,
                "stok_konumlari": [sst.konum_sozlugu(x) for x in await sst.konumlar(db, k.hesap)] if stok_modulu else []}

    @router.get("/teknisyenler")
    async def teknisyenler(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        liste = (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.hesap_email == k.hesap)
                                  .order_by(SahaTeknisyenleri.sira, SahaTeknisyenleri.id))).scalars().all()
        from models.hesap_uyeleri import HesapUyeleri
        from services.hesap_ekibi import izinleri_coz

        kayitli = {t.eposta for t in liste}
        adaylar = [] if k.hesap in kayitli else [{"eposta": k.hesap, "sahip": True}]
        for u in (await db.execute(select(HesapUyeleri).where(HesapUyeleri.hesap_email == k.hesap,
                                                             HesapUyeleri.durum.in_(("aktif", "davet"))))).scalars().all():
            if u.uye_email in kayitli:
                continue
            adaylar.append({"eposta": u.uye_email, "sahip": False, "durum": u.durum,
                            "teknisyen_izni": s.IZIN_TEKNISYEN in izinleri_coz(u.izinler, u.rol)})
        return {"items": [_teknisyen_sozlugu(t) for t in liste], "adaylar": adaylar,
                "sinir": await sk.modul_ayari(db, k.hesap, "teknisyen_siniri", s.VARSAYILAN_TEKNISYEN_SINIRI)}

    # ------------------------------------------------------------------ müşteriler, cihazlar
    @router.get("/musteriler")
    async def musteriler(request: Request, ara: Optional[str] = Query(None, max_length=80), limit: int = Query(200, ge=1, le=500),
                         db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        sorgu = select(SahaMusterileri).where(SahaMusterileri.hesap_email == k.hesap, SahaMusterileri.anonim.is_(False))
        if ara and ara.strip():
            desen = f"%{ara.strip().lower()}%"
            sorgu = sorgu.where(or_(func.lower(SahaMusterileri.ad).like(desen), func.lower(SahaMusterileri.firma).like(desen),
                                    func.lower(SahaMusterileri.eposta).like(desen), SahaMusterileri.telefon.like(desen)))
        liste = (await db.execute(sorgu.order_by(SahaMusterileri.ad).limit(limit))).scalars().all()
        idler = [m.id for m in liste]
        lok = (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.musteri_id.in_(idler or [0]))
                                .order_by(SahaLokasyonlari.id))).scalars().all()
        cih = (await db.execute(select(SahaCihazlari).where(SahaCihazlari.musteri_id.in_(idler or [0]))
                                .order_by(SahaCihazlari.id))).scalars().all()
        return {"items": [{**_musteri_sozlugu(m), "lokasyonlar": [_lokasyon_sozlugu(l) for l in lok if l.musteri_id == m.id],
                           "cihazlar": [_cihaz_sozlugu(c) for c in cih if c.musteri_id == m.id]} for m in liste]}

    @router.get("/musteriler/{mid}")
    async def musteri(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        m = await _musteri_bul(db, k, mid)
        lok = (await db.execute(select(SahaLokasyonlari).where(SahaLokasyonlari.musteri_id == m.id).order_by(SahaLokasyonlari.id))).scalars().all()
        cih = (await db.execute(select(SahaCihazlari).where(SahaCihazlari.musteri_id == m.id).order_by(SahaCihazlari.id))).scalars().all()
        isler = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.musteri_id == m.id)
                                  .order_by(SahaIsEmirleri.id.desc()).limit(50))).scalars().all()
        return {**_musteri_sozlugu(m), "lokasyonlar": [_lokasyon_sozlugu(l) for l in lok],
                "cihazlar": [_cihaz_sozlugu(c) for c in cih], "isler": await _isleri_sozlukle(db, list(isler))}

    @router.get("/cihazlar/{cid}/gecmis")
    async def cihaz_gecmisi(cid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        c = await _cihaz_bul(db, k, cid)
        isler = (await db.execute(select(SahaIsEmirleri).join(SahaIsCihazlari, SahaIsCihazlari.is_emri_id == SahaIsEmirleri.id)
                                  .where(SahaIsCihazlari.cihaz_id == c.id).order_by(SahaIsEmirleri.id.desc()).limit(100))).scalars().all()
        return {"cihaz": _cihaz_sozlugu(c), "isler": await _isleri_sozlukle(db, list(isler))}

    @router.get("/sablonlar")
    async def sablonlar(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        if not k.ajans:
            await sk.tohumla(db, await sk.ayarlar(db, k.hesap))
        liste = (await db.execute(select(SahaSablonlari).where(SahaSablonlari.hesap_email == k.hesap)
                                  .order_by(SahaSablonlari.id))).scalars().all()
        return {"items": [_sablon_sozlugu(t) for t in liste]}

    @router.get("/malzemeler")
    async def malzemeler(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        liste = (await db.execute(select(SahaMalzemeleri).where(SahaMalzemeleri.hesap_email == k.hesap)
                                  .order_by(SahaMalzemeleri.ad))).scalars().all()
        if not k.yonetim:
            liste = [m for m in liste if m.aktif]
        return {"items": [_malzeme_sozlugu(m) for m in liste]}

    @router.get("/stok-urunleri")
    async def stok_urunleri(request: Request, ara: Optional[str] = Query(None, max_length=80), db: AsyncSession = Depends(get_db)):
        """Faz 6Q — iş emrine eklenecek stok ürünü (ad / barkod / SKU). Teknisyen de görür; MALİYET (alış fiyatı)
        hiçbir kapsamda dönmez. Stok, kişinin araç/depo konumunda (yoksa ayardaki konumda / toplam)."""
        k = kapsam_al(request)
        a = await sk.ayarlar(db, k.hesap)
        if not await sst.baglanti_acik(db, k.hesap, a):
            raise _hata(409, "stok_baglantisi_kapali")
        konum = (await sst.teknisyen_konumu(db, k.hesap, k.kisi)) if not k.ajans else None
        konum = konum or a.stok_konum_id
        return {"items": await sst.urun_ara(db, k.hesap, ara, konum), "konum_id": konum}

    # ------------------------------------------------------------------ iş emirleri, pano
    @router.get("/is-emirleri")
    async def is_emirleri(request: Request, durum: Optional[str] = Query(None, max_length=80),
                          teknisyen: Optional[int] = Query(None), musteri: Optional[int] = Query(None),
                          ara: Optional[str] = Query(None, max_length=80), bas: Optional[str] = Query(None),
                          bit: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=500),
                          db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        await sk.istekle_temizle(db)
        sorgu = select(SahaIsEmirleri).where(SahaIsEmirleri.hesap_email == k.hesap)
        if durum:
            secili = [d for d in durum.split(",") if d in s.DURUMLAR]
            if secili:
                sorgu = sorgu.where(SahaIsEmirleri.durum.in_(secili))
        if teknisyen:
            sorgu = sorgu.where(SahaIsEmirleri.id.in_(select(SahaIsAtamalari.is_emri_id).where(SahaIsAtamalari.teknisyen_id == teknisyen)))
        if musteri:
            sorgu = sorgu.where(SahaIsEmirleri.musteri_id == musteri)
        if ara and ara.strip():
            desen = f"%{ara.strip().lower()}%"
            sorgu = sorgu.where(or_(func.lower(SahaIsEmirleri.baslik).like(desen), func.lower(SahaIsEmirleri.no).like(desen),
                                    SahaIsEmirleri.musteri_id.in_(select(SahaMusterileri.id).where(
                                        SahaMusterileri.hesap_email == k.hesap, func.lower(SahaMusterileri.ad).like(desen)))))
        if bas:
            sorgu = sorgu.where(SahaIsEmirleri.plan_bas >= _gun_basi(_tarih_param(bas, "bas", s.tr_bugun())))
        if bit:
            sorgu = sorgu.where(SahaIsEmirleri.plan_bas < _gun_basi(_tarih_param(bit, "bit", s.tr_bugun())) + timedelta(days=1))
        liste = (await db.execute(sorgu.order_by(SahaIsEmirleri.id.desc()).limit(limit))).scalars().all()
        return {"items": await _isleri_sozlukle(db, list(liste))}

    @router.get("/is-emirleri/{is_id}")
    async def is_emri(is_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        ie = await _is_emri(db, k, is_id)
        return await _is_ayrintisi(db, k, ie)

    @router.get("/is-emirleri/{is_id}/pdf")
    async def is_emri_pdf(is_id: int, request: Request, dil: Optional[str] = Query(None, max_length=5),
                          db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        ie = await _is_emri(db, k, is_id)
        return _pdf_yaniti(await pdf_uret(db, ie, dil if dil in s.DILLER else None), ie.no)

    @router.get("/pano")
    async def pano(request: Request, gun: Optional[str] = Query(None), gorunum: str = Query("gun"),
                   db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        g = _tarih_param(gun, "gun", s.tr_bugun())
        if gorunum == "hafta":
            g = g - timedelta(days=g.weekday())
            gun_sayisi = 7
        else:
            gun_sayisi = 1
        bas = _gun_basi(g)
        bit = bas + timedelta(days=gun_sayisi)
        teknik = (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.hesap_email == k.hesap, SahaTeknisyenleri.aktif.is_(True))
                                   .order_by(SahaTeknisyenleri.sira, SahaTeknisyenleri.id))).scalars().all()
        isler = (await db.execute(select(SahaIsEmirleri).where(
            SahaIsEmirleri.hesap_email == k.hesap, SahaIsEmirleri.plan_bas.isnot(None), SahaIsEmirleri.plan_bas < bit,
            SahaIsEmirleri.durum != "iptal").order_by(SahaIsEmirleri.plan_bas))).scalars().all()
        isler = [x for x in isler if (sk.plan_bitisi(x) or bas) > bas]
        atamalar = await sk.atama_haritasi(db, [x.id for x in isler])
        kuyruk_aday = (await db.execute(select(SahaIsEmirleri).where(
            SahaIsEmirleri.hesap_email == k.hesap, SahaIsEmirleri.durum.in_(("yeni", "ertelendi", "planlandi")))
            .order_by(SahaIsEmirleri.id).limit(300))).scalars().all()
        kuyruk_atama = await sk.atama_haritasi(db, [x.id for x in kuyruk_aday])
        sira = {o: i for i, o in enumerate(reversed(s.ONCELIKLER))}  # acil önce
        kuyruk = sorted([x for x in kuyruk_aday if x.plan_bas is None or not kuyruk_atama.get(x.id)],
                        key=lambda x: (sira.get(x.oncelik, 9), x.id))[:100]
        # Çakışmalar: aynı teknisyenin örtüşen işleri (görünen aralıkta).
        cakisan: Dict[int, List[int]] = {}
        for t in teknik:
            onun = sorted([x for x in isler if t.id in atamalar.get(x.id, []) and x.durum not in s.KAPALI_DURUMLAR],
                          key=lambda x: s.utc(x.plan_bas))
            for i, a in enumerate(onun):
                for b in onun[i + 1:]:
                    if s.utc(b.plan_bas) < sk.plan_bitisi(a):
                        cakisan.setdefault(a.id, []).append(b.id)
                        cakisan.setdefault(b.id, []).append(a.id)
        return {
            "bas": s.iso(bas), "bit": s.iso(bit), "gun": g.isoformat(), "gorunum": "hafta" if gun_sayisi == 7 else "gun",
            "teknisyenler": [_teknisyen_sozlugu(t) for t in teknik],
            "isler": [{**d, "cakisan": sorted(set(cakisan.get(d["id"], [])))} for d in await _isleri_sozlukle(db, isler)],
            "kuyruk": await _isleri_sozlukle(db, kuyruk),
        }

    @router.get("/raporlar")
    async def raporlar(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                       db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        bugun = s.tr_bugun()
        b = _tarih_param(bas, "bas", bugun - timedelta(days=29))
        e = _tarih_param(bit, "bit", bugun)
        if e < b or (e - b).days > 366:
            raise _hata(400, "aralik_gecersiz", alan="bit")
        return await sk.rapor(db, k.hesap, b, e)

    @router.get("/bakim")
    async def bakim(request: Request, gun: int = Query(30, ge=0, le=365), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        return {"items": await sk.bakim_listesi(db, k.hesap, gun)}

    if not yazma:
        return

    # ================================================================== YAZMA (yalnız müşteri paneli)
    @router.get("/islerim")
    async def islerim(request: Request, gun: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        t = await _teknisyen(db, k)
        if t is None or not k.teknisyen_izni:
            return {"kayitli": False, "items": [], "bugun": [], "diger": []}
        await sk.istekle_temizle(db)
        g = _tarih_param(gun, "gun", s.tr_bugun())
        bas = _gun_basi(g)
        bit = bas + timedelta(days=1)
        idler = select(SahaIsAtamalari.is_emri_id).where(SahaIsAtamalari.teknisyen_id == t.id)
        bugunku = (await db.execute(select(SahaIsEmirleri).where(
            SahaIsEmirleri.id.in_(idler), SahaIsEmirleri.plan_bas >= bas, SahaIsEmirleri.plan_bas < bit,
            SahaIsEmirleri.durum != "iptal").order_by(SahaIsEmirleri.plan_bas))).scalars().all()
        acik = (await db.execute(select(SahaIsEmirleri).where(
            SahaIsEmirleri.id.in_(idler), SahaIsEmirleri.durum.in_(("planlandi", "yolda", "iste", "ertelendi")),
            or_(SahaIsEmirleri.plan_bas.is_(None), SahaIsEmirleri.plan_bas < bas, SahaIsEmirleri.plan_bas >= bit))
            .order_by(SahaIsEmirleri.plan_bas).limit(50))).scalars().all()
        return {"kayitli": True, "teknisyen": _teknisyen_sozlugu(t), "gun": g.isoformat(),
                "bugun": await _isleri_sozlukle(db, list(bugunku)), "diger": await _isleri_sozlukle(db, list(acik))}

    @router.put("/ayarlar")
    async def ayarlar_yaz(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        a = await sk.ayarlar(db, k.hesap)
        try:
            for alan, sinir in (("firma_adi", 160), ("vergi_no", 64)):
                if alan in govde:
                    setattr(a, alan, s.bos_ya_da(govde.get(alan), alan, sinir))
            if "adres" in govde:
                a.adres = s.bos_ya_da(govde.get("adres"), "adres", 500, cok_satir=True)
            if "telefon" in govde:
                a.telefon = s.telefon_duzelt(govde.get("telefon"))
            if "eposta" in govde:
                a.eposta = s.eposta_duzelt(govde.get("eposta"))
            if "varsayilan_dil" in govde:
                a.varsayilan_dil = s.secim(govde.get("varsayilan_dil"), "varsayilan_dil", s.DILLER)
            if "para_birimi" in govde:
                a.para_birimi = s.secim(str(govde.get("para_birimi") or "").lower(), "para_birimi",
                                        [p.lower() for p in s.PARA_BIRIMLERI]).upper()
            if "kdv_orani" in govde:
                a.kdv_orani = s.tam_sayi(govde.get("kdv_orani"), "kdv_orani", 0, 50)
            if "saklama_ay" in govde:
                a.saklama_ay = s.tam_sayi(govde.get("saklama_ay"), "saklama_ay", s.SAKLAMA_EN_AZ_AY, s.SAKLAMA_EN_COK_AY)
            if "bakim_on_gun" in govde:
                a.bakim_on_gun = s.tam_sayi(govde.get("bakim_on_gun"), "bakim_on_gun", 0, 60)
            for alan in ("imza_zorunlu", "bildirim_planlandi", "bildirim_yolda", "bildirim_tamamlandi", "memnuniyet_acik",
                         "randevu_kancasi"):
                if alan in govde:
                    setattr(a, alan, s.bool_duzelt(govde.get(alan), alan))
            if "randevu_is_turu" in govde:
                a.randevu_is_turu = s.secim(govde.get("randevu_is_turu"), "randevu_is_turu", s.IS_TURLERI)
            # Faz 6Q: stok bağlantısı yalnız Stok ve POS modülü açıkken açılabilir / konum seçilebilir.
            if "stoktan_dus" in govde:
                dus = s.bool_duzelt(govde.get("stoktan_dus"), "stoktan_dus")
                if dus and not await sst.stok_modulu_acik(db, k.hesap):
                    raise s.SahaHatasi("stok_modulu_kapali", "stoktan_dus", durum=409)
                a.stoktan_dus = dus
            if "stok_konum_id" in govde:
                if govde.get("stok_konum_id") not in (None, "") and not await sst.stok_modulu_acik(db, k.hesap):
                    raise s.SahaHatasi("stok_modulu_kapali", "stok_konum_id", durum=409)
                a.stok_konum_id = await sst.konum_dogrula(db, k.hesap, govde.get("stok_konum_id"))
            if "yorum_sayfasi_id" in govde:
                yid = s.tam_sayi(govde.get("yorum_sayfasi_id"), "yorum_sayfasi_id", 1, 2_000_000_000, bos_olabilir=True)
                if yid is not None:
                    from models.kartvizit import YorumSayfalari

                    if (await db.execute(select(YorumSayfalari.id).where(YorumSayfalari.id == yid,
                                                                          YorumSayfalari.hesap_email == k.hesap))).first() is None:
                        raise s.SahaHatasi("bulunamadi", "yorum_sayfasi_id", durum=404)
                a.yorum_sayfasi_id = yid
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        sk.kanca_onbellegi_temizle()
        await db.refresh(a)
        return _ayar_sozlugu(a)

    # ------------------------------------------------------------------ teknisyenler
    @router.post("/teknisyenler")
    async def teknisyen_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        try:
            eposta = s.eposta_duzelt(govde.get("eposta"), zorunlu=True)
            ad = s.metin(govde.get("ad"), "ad", 120) or eposta.split("@", 1)[0]
            telefon = s.telefon_duzelt(govde.get("telefon"))
            renk = s.renk_duzelt(govde.get("renk")) if govde.get("renk") else "#7c3aed"
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        if eposta != k.hesap:
            from models.hesap_uyeleri import HesapUyeleri

            uye = (await db.execute(select(HesapUyeleri.id).where(HesapUyeleri.hesap_email == k.hesap, HesapUyeleri.uye_email == eposta,
                                                                  HesapUyeleri.durum.in_(("aktif", "davet"))))).first()
            if uye is None:
                raise _hata(409, "ekip_uyesi_degil", alan="eposta")
        sinir = await sk.modul_ayari(db, k.hesap, "teknisyen_siniri", s.VARSAYILAN_TEKNISYEN_SINIRI)
        sayi = int((await db.execute(select(func.count(SahaTeknisyenleri.id)).where(
            SahaTeknisyenleri.hesap_email == k.hesap, SahaTeknisyenleri.aktif.is_(True)))).scalar() or 0)
        if sayi >= sinir:
            raise _hata(409, "teknisyen_siniri", sinir=sinir)
        t = SahaTeknisyenleri(hesap_email=k.hesap, eposta=eposta, ad=ad, telefon=telefon, renk=renk, sira=sayi, created_at=s.simdi())
        db.add(t)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "zaten_var", alan="eposta")
        await db.refresh(t)
        return _teknisyen_sozlugu(t)

    @router.put("/teknisyenler/{tid}")
    async def teknisyen_guncelle(tid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        t = await _teknisyen_bul(db, k, tid)
        try:
            if "ad" in govde:
                t.ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "telefon" in govde:
                t.telefon = s.telefon_duzelt(govde.get("telefon"))
            if "renk" in govde:
                t.renk = s.renk_duzelt(govde.get("renk"))
            if "sira" in govde:
                t.sira = s.tam_sayi(govde.get("sira"), "sira", 0, 1000)
            if "stok_konum_id" in govde:
                # Faz 6Q: teknisyenin araç/depo stok konumu (isteğe bağlı).
                if govde.get("stok_konum_id") not in (None, "") and not await sst.stok_modulu_acik(db, k.hesap):
                    raise s.SahaHatasi("stok_modulu_kapali", "stok_konum_id", durum=409)
                t.stok_konum_id = await sst.konum_dogrula(db, k.hesap, govde.get("stok_konum_id"))
            if "aktif" in govde:
                aktif = s.bool_duzelt(govde.get("aktif"), "aktif")
                if aktif and not t.aktif:
                    sinir = await sk.modul_ayari(db, k.hesap, "teknisyen_siniri", s.VARSAYILAN_TEKNISYEN_SINIRI)
                    sayi = int((await db.execute(select(func.count(SahaTeknisyenleri.id)).where(
                        SahaTeknisyenleri.hesap_email == k.hesap, SahaTeknisyenleri.aktif.is_(True)))).scalar() or 0)
                    if sayi >= sinir:
                        raise s.SahaHatasi("teknisyen_siniri", durum=409, sinir=sinir)
                t.aktif = aktif
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(t)
        return _teknisyen_sozlugu(t)

    @router.delete("/teknisyenler/{tid}")
    async def teknisyen_sil(tid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        t = await _teknisyen_bul(db, k, tid)
        acik = (await db.execute(select(func.count(SahaIsAtamalari.id)).join(
            SahaIsEmirleri, SahaIsEmirleri.id == SahaIsAtamalari.is_emri_id).where(
            SahaIsAtamalari.teknisyen_id == t.id, SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)))).scalar() or 0
        if acik:
            raise _hata(409, "acik_is_var", sayi=int(acik))
        await db.delete(t)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------------ konum rızası (kişinin kendisi)
    @router.get("/rizam")
    async def rizam(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        t = await _teknisyen(db, k)
        if t is None:
            return {"kayitli": False, "gecerli": False, "surum": s.RIZA_SURUMU}
        return {"kayitli": True, "gecerli": s.riza_gecerli_mi(t.konum_rizasi_at, t.konum_rizasi_surumu, t.konum_rizasi_geri_at),
                "surum": s.RIZA_SURUMU, "verildi_at": s.iso(t.konum_rizasi_at), "verilen_surum": t.konum_rizasi_surumu,
                "geri_alindi_at": s.iso(t.konum_rizasi_geri_at)}

    @router.post("/rizam")
    async def riza_ver(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        t = await _teknisyen(db, k)
        if t is None or not k.teknisyen_izni:
            raise _hata(409, "teknisyen_degil")
        if govde.get("surum") != s.RIZA_SURUMU or govde.get("onay") is not True:
            raise _hata(400, "riza_surumu_gecersiz", surum=s.RIZA_SURUMU)
        t.konum_rizasi_at = s.simdi()
        t.konum_rizasi_surumu = s.RIZA_SURUMU
        t.konum_rizasi_geri_at = None
        await db.commit()
        return {"gecerli": True, "surum": s.RIZA_SURUMU, "verildi_at": s.iso(t.konum_rizasi_at)}

    @router.delete("/rizam")
    async def riza_geri_al(request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        t = await _teknisyen(db, k)
        if t is None:
            raise _hata(409, "teknisyen_degil")
        t.konum_rizasi_geri_at = s.simdi()
        await db.commit()
        return {"gecerli": False, "geri_alindi_at": s.iso(t.konum_rizasi_geri_at)}

    # ------------------------------------------------------------------ müşteriler, lokasyonlar, cihazlar
    def _musteri_alanlari(m: SahaMusterileri, g: Dict[str, Any], yeni: bool) -> None:
        if yeni or "ad" in g:
            m.ad = s.metin(g.get("ad"), "ad", 160, zorunlu=True)
        if yeni or "tur" in g:
            m.tur = s.secim(g.get("tur") or "bireysel", "tur", s.MUSTERI_TURLERI)
        for alan, sinir in (("firma", 160), ("vergi_no", 64)):
            if alan in g:
                setattr(m, alan, s.bos_ya_da(g.get(alan), alan, sinir))
        if "notlar" in g:
            m.notlar = s.bos_ya_da(g.get("notlar"), "notlar", 2000, cok_satir=True)
        if "eposta" in g:
            m.eposta = s.eposta_duzelt(g.get("eposta"))
        if "telefon" in g:
            m.telefon = s.telefon_duzelt(g.get("telefon"))
        if "dil" in g:
            m.dil = s.secim(g.get("dil") or "tr", "dil", s.DILLER)

    @router.post("/musteriler")
    async def musteri_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        a = await sk.ayarlar(db, k.hesap)
        m = SahaMusterileri(hesap_email=k.hesap, dil=a.varsayilan_dil or "tr", created_at=s.simdi())
        try:
            _musteri_alanlari(m, govde, True)
            lokasyon = govde.get("lokasyon")
            db.add(m)
            await db.flush()
            if isinstance(lokasyon, dict) and (lokasyon.get("adres") or lokasyon.get("ad")):
                db.add(_lokasyon_yap(k.hesap, m.id, lokasyon))
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(m)
        return await musteri(m.id, request, db)

    @router.put("/musteriler/{mid}")
    async def musteri_guncelle(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        m = await _musteri_bul(db, k, mid)
        try:
            _musteri_alanlari(m, govde, False)
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        return await musteri(m.id, request, db)

    @router.delete("/musteriler/{mid}")
    async def musteri_sil(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """KVKK silme: iş emri varsa kayıt kalır ama kişisel veri hemen anonimleşir; yoksa kayıt çöpe gider."""
        k = kapsam_al(request)
        _yonetim_iste(k)
        m = await _musteri_bul(db, k, mid)
        acik = (await db.execute(select(SahaIsEmirleri.id).where(SahaIsEmirleri.musteri_id == m.id,
                                                                 SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)).limit(1))).first()
        if acik:
            raise _hata(409, "acik_is_var")
        is_var = (await db.execute(select(SahaIsEmirleri.id).where(SahaIsEmirleri.musteri_id == m.id).limit(1))).first()
        if is_var:
            await sk.musteri_anonimlestir(db, m)
            await db.commit()
            return {"ok": True, "anonimlesti": True}
        for model in (SahaCihazlari, SahaLokasyonlari):
            for x in (await db.execute(select(model).where(model.musteri_id == m.id))).scalars().all():
                await db.delete(x)
        await db.delete(m)
        await db.commit()
        return {"ok": True, "anonimlesti": False}

    @router.post("/musteriler/{mid}/lokasyonlar")
    async def lokasyon_ekle(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        m = await _musteri_bul(db, k, mid)
        try:
            l = _lokasyon_yap(k.hesap, m.id, govde)
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        db.add(l)
        await db.commit()
        await db.refresh(l)
        return _lokasyon_sozlugu(l)

    @router.put("/lokasyonlar/{lid}")
    async def lokasyon_guncelle(lid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        l = await _lokasyon_bul(db, k, lid)
        try:
            _lokasyon_alanlari(l, govde, False)
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(l)
        return _lokasyon_sozlugu(l)

    @router.delete("/lokasyonlar/{lid}")
    async def lokasyon_sil(lid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        l = await _lokasyon_bul(db, k, lid)
        if (await db.execute(select(SahaIsEmirleri.id).where(SahaIsEmirleri.lokasyon_id == l.id,
                                                             SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)).limit(1))).first():
            raise _hata(409, "acik_is_var")
        await db.delete(l)
        await db.commit()
        return {"ok": True}

    def _cihaz_alanlari(c: SahaCihazlari, g: Dict[str, Any], yeni: bool) -> None:
        if yeni or "tur" in g:
            c.tur = s.metin(g.get("tur"), "tur", 60, zorunlu=True)
        for alan, sinir in (("marka", 80), ("model", 80), ("seri_no", 80)):
            if alan in g:
                setattr(c, alan, s.bos_ya_da(g.get(alan), alan, sinir))
        for alan in ("kurulum_tarihi", "garanti_bitis", "son_bakim"):
            if alan in g:
                setattr(c, alan, s.tarih_duzelt(g.get(alan), alan))
        if "bakim_periyot_ay" in g:
            c.bakim_periyot_ay = s.tam_sayi(g.get("bakim_periyot_ay"), "bakim_periyot_ay", 1, 120, bos_olabilir=True)
            c.bakim_bildirim_tarihi = None
        if "son_bakim" in g:
            c.bakim_bildirim_tarihi = None
        if "notlar" in g:
            c.notlar = s.bos_ya_da(g.get("notlar"), "notlar", 2000, cok_satir=True)
        if "aktif" in g:
            c.aktif = s.bool_duzelt(g.get("aktif"), "aktif")

    @router.post("/musteriler/{mid}/cihazlar")
    async def cihaz_ekle(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        m = await _musteri_bul(db, k, mid)
        c = SahaCihazlari(hesap_email=k.hesap, musteri_id=m.id, created_at=s.simdi())
        try:
            _cihaz_alanlari(c, govde, True)
            if govde.get("lokasyon_id") not in (None, ""):
                c.lokasyon_id = (await _lokasyon_bul(db, k, s.tam_sayi(govde.get("lokasyon_id"), "lokasyon_id", 1, 2_000_000_000), m.id)).id
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return _cihaz_sozlugu(c)

    @router.put("/cihazlar/{cid}")
    async def cihaz_guncelle(cid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        c = await _cihaz_bul(db, k, cid)
        try:
            _cihaz_alanlari(c, govde, False)
            if "lokasyon_id" in govde:
                lid = s.tam_sayi(govde.get("lokasyon_id"), "lokasyon_id", 1, 2_000_000_000, bos_olabilir=True)
                c.lokasyon_id = (await _lokasyon_bul(db, k, lid, c.musteri_id)).id if lid else None
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(c)
        return _cihaz_sozlugu(c)

    @router.delete("/cihazlar/{cid}")
    async def cihaz_sil(cid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        c = await _cihaz_bul(db, k, cid)
        if (await db.execute(select(SahaIsCihazlari.id).where(SahaIsCihazlari.cihaz_id == c.id).limit(1))).first():
            # Geçmişi olan cihaz silinmez, pasifleşir (cihaz geçmişi bozulmasın).
            c.aktif = False
            await db.commit()
            return {"ok": True, "pasif": True}
        await db.delete(c)
        await db.commit()
        return {"ok": True, "pasif": False}

    @router.post("/cihazlar/{cid}/bakim-is-emri")
    async def bakim_is_emri(cid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(default={}),
                            db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        c = await _cihaz_bul(db, k, cid)
        acik = (await db.execute(select(SahaIsEmirleri.id).join(SahaIsCihazlari, SahaIsCihazlari.is_emri_id == SahaIsEmirleri.id)
                                 .where(SahaIsCihazlari.cihaz_id == c.id, SahaIsEmirleri.tur == "bakim",
                                        SahaIsEmirleri.durum.in_(s.ACIK_DURUMLAR)).limit(1))).first()
        if acik:
            raise _hata(409, "acik_bakim_var", is_emri_id=acik[0])
        g = {"musteri_id": c.musteri_id, "lokasyon_id": c.lokasyon_id, "cihazlar": [c.id], "tur": "bakim",
             "oncelik": "normal", "baslik": f"{c.tur} {c.marka or ''} {c.model or ''}".replace("  ", " ").strip()[:140] or c.tur,
             **{a: govde[a] for a in ("plan_bas", "tahmini_dk", "teknisyenler", "baslik") if a in govde}}
        return await _olustur_yaniti(db, k, g, arka)

    # ------------------------------------------------------------------ şablonlar, malzemeler
    @router.post("/sablonlar")
    async def sablon_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        try:
            t = SahaSablonlari(hesap_email=k.hesap, ad=s.metin(govde.get("ad"), "ad", 120, zorunlu=True),
                               is_turu=s.secim(govde.get("is_turu"), "is_turu", s.IS_TURLERI) if govde.get("is_turu") else None,
                               maddeler=s.json_yaz(s.maddeleri_duzelt(govde.get("maddeler") or [])), aktif=True, created_at=s.simdi())
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        if (await db.execute(select(func.count(SahaSablonlari.id)).where(SahaSablonlari.hesap_email == k.hesap))).scalar() >= 100:
            raise _hata(409, "sablon_siniri", sinir=100)
        if t.is_turu:
            await _varsayilani_birak(db, k.hesap, t.is_turu)
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return _sablon_sozlugu(t)

    @router.put("/sablonlar/{sid}")
    async def sablon_guncelle(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        t = await _sablon_bul(db, k, sid)
        try:
            if "ad" in govde:
                t.ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "maddeler" in govde:
                t.maddeler = s.json_yaz(s.maddeleri_duzelt(govde.get("maddeler")))
            if "aktif" in govde:
                t.aktif = s.bool_duzelt(govde.get("aktif"), "aktif")
            if "is_turu" in govde:
                yeni = s.secim(govde.get("is_turu"), "is_turu", s.IS_TURLERI) if govde.get("is_turu") else None
                if yeni and yeni != t.is_turu:
                    await _varsayilani_birak(db, k.hesap, yeni, haric=t.id)
                t.is_turu = yeni
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(t)
        return _sablon_sozlugu(t)

    @router.delete("/sablonlar/{sid}")
    async def sablon_sil(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        t = await _sablon_bul(db, k, sid)
        await db.delete(t)
        await db.commit()
        return {"ok": True}

    def _malzeme_alanlari(m: SahaMalzemeleri, g: Dict[str, Any], yeni: bool) -> None:
        if yeni or "ad" in g:
            m.ad = s.metin(g.get("ad"), "ad", 160, zorunlu=True)
        if "kod" in g:
            m.kod = s.bos_ya_da(g.get("kod"), "kod", 60)
        if yeni or "birim" in g:
            m.birim = s.secim(g.get("birim") or "adet", "birim", s.BIRIMLER)
        if "birim_fiyat" in g:
            m.birim_fiyat = s.kurus(g.get("birim_fiyat"), "birim_fiyat")
        if "stok" in g:
            m.stok = s.ondalik(g.get("stok"), "stok", -1_000_000, 1_000_000, bos_olabilir=True)
        if "kritik_stok" in g:
            m.kritik_stok = s.ondalik(g.get("kritik_stok"), "kritik_stok", 0, 1_000_000, bos_olabilir=True)
        if "aktif" in g:
            m.aktif = s.bool_duzelt(g.get("aktif"), "aktif")

    @router.post("/malzemeler")
    async def malzeme_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        m = SahaMalzemeleri(hesap_email=k.hesap, birim_fiyat=0, created_at=s.simdi())
        try:
            _malzeme_alanlari(m, govde, True)
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        if (await db.execute(select(func.count(SahaMalzemeleri.id)).where(SahaMalzemeleri.hesap_email == k.hesap))).scalar() >= 2000:
            raise _hata(409, "malzeme_siniri", sinir=2000)
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return _malzeme_sozlugu(m)

    @router.put("/malzemeler/{mid}")
    async def malzeme_guncelle(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        m = await _malzeme_bul(db, k, mid)
        try:
            _malzeme_alanlari(m, govde, False)
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(m)
        return _malzeme_sozlugu(m)

    @router.delete("/malzemeler/{mid}")
    async def malzeme_sil(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        m = await _malzeme_bul(db, k, mid)
        await db.delete(m)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------------ iş emri yazma
    @router.post("/is-emirleri")
    async def is_emri_ekle(request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                           db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        return await _olustur_yaniti(db, k, govde, arka)

    @router.put("/is-emirleri/{is_id}")
    async def is_emri_guncelle(is_id: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                               db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        return await _guncelle_yaniti(db, k, ie, govde, arka)

    @router.put("/is-emirleri/{is_id}/plan")
    async def is_emri_plan(is_id: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                           db: AsyncSession = Depends(get_db)):
        """Sevk panosu (sürükle-bırak): `teknisyen_id` (null → atamayı kaldır, kuyruğa döner),
        `plan_bas`; birden çok teknisyenli işte yalnız `eski_teknisyen_id` yerine geçer."""
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        g: Dict[str, Any] = {}
        if "plan_bas" in govde:
            g["plan_bas"] = govde.get("plan_bas")
            if ie.plan_bas and ie.plan_bit and govde.get("plan_bas") and "tahmini_dk" not in govde:
                g["tahmini_dk"] = max(5, int((s.utc(ie.plan_bit) - s.utc(ie.plan_bas)).total_seconds() // 60))
        if "tahmini_dk" in govde:
            g["tahmini_dk"] = govde.get("tahmini_dk")
        if "teknisyen_id" in govde:
            mevcut = (await sk.atama_haritasi(db, [ie.id]))[ie.id]
            yeni = govde.get("teknisyen_id")
            eski = govde.get("eski_teknisyen_id")
            if yeni in (None, ""):
                g["teknisyenler"] = [t for t in mevcut if eski not in (None, "") and t != eski] if eski not in (None, "") else []
            else:
                kalan = [t for t in mevcut if t != eski] if eski not in (None, "") else ([] if len(mevcut) <= 1 else mevcut)
                g["teknisyenler"] = kalan + ([yeni] if yeni not in kalan else [])
        return await _guncelle_yaniti(db, k, ie, g, arka)

    @router.delete("/is-emirleri/{is_id}")
    async def is_emri_sil(is_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        ie = await _is_emri(db, k, is_id)
        if ie.durum in ("yolda", "iste", "tamamlandi"):
            raise _hata(409, "silinemez", durum=ie.durum)
        await sk.is_emri_anonimlestir(db, ie)
        for model in (SahaIsAtamalari, SahaIsCihazlari, SahaMalzemeKullanimi, SahaDurumGecmisi):
            for x in (await db.execute(select(model).where(model.is_emri_id == ie.id))).scalars().all():
                await db.delete(x)
        await db.delete(ie)
        await db.commit()
        return {"ok": True}

    @router.post("/is-emirleri/{is_id}/durum")
    async def is_emri_durum(is_id: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                            db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        t = await _teknisyen(db, k) if k.teknisyen_izni else None
        try:
            sonuc = await sk.durum_degistir(db, ie, str(govde.get("durum") or ""), kisi=k.kisi, yonetim=k.yonetim,
                                            teknisyen=t, konum_ham=govde.get("konum"), neden=govde.get("neden"))
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        if sonuc.get("musteri_bildirimi"):
            arka.add_task(sk.musteriye_bildir, ie.id, sonuc["musteri_bildirimi"])
        await sst.gecisleri_isle(db, ie.hesap_email, sonuc.get("stok_gecisleri") or [])
        d = await _is_ayrintisi(db, k, ie)
        d["konum_kaydedildi"] = sonuc["konum_alindi"]
        return d

    @router.post("/is-emirleri/{is_id}/yeniden-ac")
    async def is_emri_yeniden_ac(is_id: int, request: Request, govde: Optional[Dict[str, Any]] = Body(None),
                                 db: AsyncSession = Depends(get_db)):
        """Faz 6Q — tamamlanmış işi yeniden açar (`iste`); stoktan düşülen malzemeler geri eklenir."""
        k = kapsam_al(request)
        _yonetim_iste(k)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        try:
            gecisler = await sk.yeniden_ac(db, ie, kisi=k.kisi, neden=(govde or {}).get("neden"))
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await sst.gecisleri_isle(db, ie.hesap_email, gecisler)
        return await _is_ayrintisi(db, k, ie)

    @router.put("/is-emirleri/{is_id}/kontrol")
    async def is_emri_kontrol(is_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        if ie.durum in s.KAPALI_DURUMLAR:
            raise _hata(409, "is_kapali")
        try:
            ie.kontrol_yanitlari = s.json_yaz(s.yanitlari_birlestir(s.json_yukle(ie.kontrol_listesi, []) or [],
                                                                    s.json_yukle(ie.kontrol_yanitlari, {}) or {}, govde.get("yanitlar")))
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        ie.updated_at = s.simdi()
        await db.commit()
        return {"kontrol_yanitlari": s.json_yukle(ie.kontrol_yanitlari, {}) or {}}

    @router.put("/is-emirleri/{is_id}/saha")
    async def is_emri_saha(is_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        if ie.durum in s.KAPALI_DURUMLAR and not k.yonetim:
            raise _hata(409, "is_kapali")
        try:
            if "teknisyen_notu" in govde:
                ie.teknisyen_notu = s.bos_ya_da(govde.get("teknisyen_notu"), "teknisyen_notu", 4000, cok_satir=True)
            if "iscilik_dk" in govde:
                ie.iscilik_dk = s.tam_sayi(govde.get("iscilik_dk"), "iscilik_dk", 0, 24 * 60 * 7, bos_olabilir=True)
            if "takip_gerekli" in govde:
                ie.takip_gerekli = s.bool_duzelt(govde.get("takip_gerekli"), "takip_gerekli")
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        ie.updated_at = s.simdi()
        await db.commit()
        return {"teknisyen_notu": ie.teknisyen_notu or "", "iscilik_dk": ie.iscilik_dk, "takip_gerekli": bool(ie.takip_gerekli)}

    @router.post("/is-emirleri/{is_id}/fotograflar")
    async def foto_ekle(is_id: int, request: Request, dosya: UploadFile = File(...), tur: str = Form("once"),
                        madde_id: Optional[str] = Form(None), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_foto_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        if ie.durum in s.KAPALI_DURUMLAR:
            raise _hata(409, "is_kapali")
        try:
            tur_ = s.secim(tur, "tur", s.FOTO_TURLERI)
            madde = None
            if tur_ == "madde":
                maddeler = {m["id"] for m in (s.json_yukle(ie.kontrol_listesi, []) or [])}
                madde = str(madde_id or "")[:16]
                if madde not in maddeler:
                    raise s.SahaHatasi("madde_yok", "madde_id", durum=404)
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        sayi = int((await db.execute(select(func.count(SahaIsFotograflari.id)).where(SahaIsFotograflari.is_emri_id == ie.id))).scalar() or 0)
        if sayi >= s.FOTO_SINIRI:
            raise _hata(409, "foto_siniri", sinir=s.FOTO_SINIRI)
        bayt = await dosya.read(s.FOTO_EN_COK_BAYT + 1)
        try:
            buyuk, kucuk, gen, yuk = s.foto_hazirla(bayt)
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        anahtar, kucuk_anahtar = s.depo_anahtari("foto"), s.depo_anahtari("fotok")
        depo = await sk.gorsel_yaz(db, anahtar, buyuk, "image/webp")
        await sk.gorsel_yaz(db, kucuk_anahtar, kucuk, "image/webp")
        f = SahaIsFotograflari(is_emri_id=ie.id, hesap_email=ie.hesap_email, anahtar=anahtar, kucuk_anahtar=kucuk_anahtar,
                               depo=depo, tur=tur_, madde_id=madde, genislik=gen, yukseklik=yuk, boyut=len(buyuk) + len(kucuk),
                               yukleyen=k.kisi, created_at=s.simdi())
        db.add(f)
        await db.commit()
        await db.refresh(f)
        return {"id": f.id, "tur": f.tur, "madde_id": f.madde_id, "url": s.gorsel_adresi(f.anahtar),
                "kucuk_url": s.gorsel_adresi(f.kucuk_anahtar), "genislik": gen, "yukseklik": yuk}

    @router.delete("/is-emirleri/{is_id}/fotograflar/{fid}")
    async def foto_sil(is_id: int, fid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        ie = await _is_emri(db, k, is_id)
        if ie.durum in s.KAPALI_DURUMLAR:
            raise _hata(409, "is_kapali")
        f = (await db.execute(select(SahaIsFotograflari).where(SahaIsFotograflari.id == fid,
                                                               SahaIsFotograflari.is_emri_id == ie.id))).scalars().first()
        if f is None:
            raise _hata(404, "bulunamadi")
        await sk.gorsel_sil(db, f.depo, f.anahtar, f.kucuk_anahtar)
        await db.delete(f)
        await db.commit()
        return {"ok": True}

    @router.post("/is-emirleri/{is_id}/malzemeler")
    async def kullanim_ekle(is_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        try:
            x = await sk.malzeme_ekle(db, ie, govde, k.kisi)
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        return sst.satir_sozlugu(x)

    @router.delete("/is-emirleri/{is_id}/malzemeler/{kid}")
    async def kullanim_sil(is_id: int, kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        ie = await _is_emri(db, k, is_id)
        try:
            gecisler = await sk.malzeme_sil(db, ie, kid, k.kisi)
        except s.SahaHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await sst.gecisleri_isle(db, ie.hesap_email, gecisler)
        return {"ok": True}

    @router.post("/is-emirleri/{is_id}/imza")
    async def imza_al(is_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _hiz(_yazma_hizi, k.kisi)
        ie = await _is_emri(db, k, is_id)
        if ie.durum not in ("iste", "tamamlandi"):
            raise _hata(409, "imza_zamani_degil")
        if ie.durum == "tamamlandi" and ie.imza_anahtari:
            raise _hata(409, "zaten_imzali")
        try:
            ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            png = s.imza_png_coz(govde.get("png"))
        except s.SahaHatasi as h:
            raise _s_hatasi(h)
        eski = (ie.imza_depo, ie.imza_anahtari)
        anahtar = s.depo_anahtari("imza")
        ie.imza_depo = await sk.gorsel_yaz(db, anahtar, png, "image/png")
        ie.imza_anahtari, ie.imza_ad, ie.imza_at = anahtar, ad, s.simdi()
        await db.commit()
        if eski[1]:
            await sk.gorsel_sil(db, eski[0], eski[1])
            await db.commit()
        return {"imza": {"ad": ie.imza_ad, "at": s.iso(ie.imza_at), "url": s.gorsel_adresi(anahtar)}}

    @router.post("/is-emirleri/{is_id}/musteri-baglantisi")
    async def musteri_baglantisi(is_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = kapsam_al(request)
        _yonetim_iste(k)
        ie = await _is_emri(db, k, is_id)
        return {"adres": s.musteri_adresi(s.musteri_jetonu(ie.id, ie.uid))}


# ---------------------------------------------------------------------------
# Router dışı yardımcılar (uçların kullandığı)
# ---------------------------------------------------------------------------
def _gun_basi(g: date) -> datetime:
    from zoneinfo import ZoneInfo

    return datetime(g.year, g.month, g.day, tzinfo=ZoneInfo("Europe/Istanbul")).astimezone(s.UTC)


async def _musteri_bul(db: AsyncSession, k: Kapsam, mid: int) -> SahaMusterileri:
    m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == mid, SahaMusterileri.hesap_email == k.hesap))).scalars().first()
    if m is None or m.anonim:
        raise _hata(404, "bulunamadi")
    return m


async def _lokasyon_bul(db: AsyncSession, k: Kapsam, lid: int, musteri_id: Optional[int] = None) -> SahaLokasyonlari:
    sorgu = select(SahaLokasyonlari).where(SahaLokasyonlari.id == lid, SahaLokasyonlari.hesap_email == k.hesap)
    if musteri_id is not None:
        sorgu = sorgu.where(SahaLokasyonlari.musteri_id == musteri_id)
    l = (await db.execute(sorgu)).scalars().first()
    if l is None:
        raise _hata(404, "bulunamadi")
    return l


async def _cihaz_bul(db: AsyncSession, k: Kapsam, cid: int) -> SahaCihazlari:
    c = (await db.execute(select(SahaCihazlari).where(SahaCihazlari.id == cid, SahaCihazlari.hesap_email == k.hesap))).scalars().first()
    if c is None:
        raise _hata(404, "bulunamadi")
    return c


async def _sablon_bul(db: AsyncSession, k: Kapsam, sid: int) -> SahaSablonlari:
    t = (await db.execute(select(SahaSablonlari).where(SahaSablonlari.id == sid, SahaSablonlari.hesap_email == k.hesap))).scalars().first()
    if t is None:
        raise _hata(404, "bulunamadi")
    return t


async def _malzeme_bul(db: AsyncSession, k: Kapsam, mid: int) -> SahaMalzemeleri:
    m = (await db.execute(select(SahaMalzemeleri).where(SahaMalzemeleri.id == mid, SahaMalzemeleri.hesap_email == k.hesap))).scalars().first()
    if m is None:
        raise _hata(404, "bulunamadi")
    return m


async def _teknisyen_bul(db: AsyncSession, k: Kapsam, tid: int) -> SahaTeknisyenleri:
    t = (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.id == tid, SahaTeknisyenleri.hesap_email == k.hesap))).scalars().first()
    if t is None:
        raise _hata(404, "bulunamadi")
    return t


async def _varsayilani_birak(db: AsyncSession, hesap: str, tur: str, haric: Optional[int] = None) -> None:
    """Bir iş türünün tek varsayılan şablonu olur: yenisi seçilince eskisinin türü boşalır."""
    sorgu = select(SahaSablonlari).where(SahaSablonlari.hesap_email == hesap, SahaSablonlari.is_turu == tur)
    if haric is not None:
        sorgu = sorgu.where(SahaSablonlari.id != haric)
    for t in (await db.execute(sorgu)).scalars().all():
        t.is_turu = None


def _lokasyon_alanlari(l: SahaLokasyonlari, g: Dict[str, Any], yeni: bool) -> None:
    if yeni or "ad" in g:
        l.ad = s.metin(g.get("ad"), "ad", 120) or "Adres"
    if "adres" in g:
        l.adres = s.bos_ya_da(g.get("adres"), "adres", 500, cok_satir=True)
    for alan, sinir in (("ilce", 80), ("il", 80), ("posta_kodu", 16)):
        if alan in g:
            setattr(l, alan, s.bos_ya_da(g.get(alan), alan, sinir))
    if "notlar" in g:
        l.notlar = s.bos_ya_da(g.get("notlar"), "notlar", 1000, cok_satir=True)


def _lokasyon_yap(hesap: str, musteri_id: int, g: Dict[str, Any]) -> SahaLokasyonlari:
    l = SahaLokasyonlari(hesap_email=hesap, musteri_id=musteri_id, created_at=s.simdi())
    _lokasyon_alanlari(l, g, True)
    return l


async def _olustur_yaniti(db: AsyncSession, k: Kapsam, g: Dict[str, Any], arka: BackgroundTasks) -> Dict[str, Any]:
    try:
        sonuc = await sk.is_emri_olustur(db, k.hesap, g, k.kisi)
    except s.SahaHatasi as h:
        await db.rollback()
        raise _s_hatasi(h)
    if sonuc.yeni_atananlar:
        arka.add_task(sk.teknisyenlere_bildir, sonuc.ie.id, sonuc.yeni_atananlar)
    if sonuc.musteri_bildirimi:
        arka.add_task(sk.musteriye_bildir, sonuc.ie.id, sonuc.musteri_bildirimi)
    return {**await _is_ayrintisi(db, k, sonuc.ie), "cakismalar": sonuc.cakismalar}


async def _guncelle_yaniti(db: AsyncSession, k: Kapsam, ie: SahaIsEmirleri, g: Dict[str, Any], arka: BackgroundTasks) -> Dict[str, Any]:
    try:
        sonuc = await sk.is_emri_guncelle(db, ie, g, k.kisi)
    except s.SahaHatasi as h:
        await db.rollback()
        raise _s_hatasi(h)
    if sonuc.yeni_atananlar:
        arka.add_task(sk.teknisyenlere_bildir, ie.id, sonuc.yeni_atananlar)
    if sonuc.musteri_bildirimi:
        arka.add_task(sk.musteriye_bildir, ie.id, sonuc.musteri_bildirimi)
    return {**await _is_ayrintisi(db, k, sonuc.ie), "cakismalar": sonuc.cakismalar}


_uclari_kur(musteri_router, _musteri_kapsami, yazma=True)
_uclari_kur(yonetici_router, _yonetici_kapsami, yazma=False)


@yonetici_router.get("/hesaplar")
async def yonetici_hesaplar(db: AsyncSession = Depends(get_db)):
    """Saha servisi kaydı olan ya da modülü açık hesaplar (destek görünümü için)."""
    from models.workspace_modules import WorkspaceModules

    hesaplar = set((await db.execute(select(SahaAyarlari.hesap_email))).scalars().all())
    hesaplar |= set((await db.execute(select(WorkspaceModules.musteri_eposta).where(
        WorkspaceModules.modul_anahtari == MODUL, WorkspaceModules.acik.is_(True)))).scalars().all())
    sayilar = dict((await db.execute(select(SahaIsEmirleri.hesap_email, func.count(SahaIsEmirleri.id))
                                     .group_by(SahaIsEmirleri.hesap_email))).all())
    adlar = dict((await db.execute(select(SahaAyarlari.hesap_email, SahaAyarlari.firma_adi))).all())
    return {"items": [{"hesap_email": h, "firma_adi": adlar.get(h), "is_emri": int(sayilar.get(h, 0))}
                      for h in sorted(x for x in hesaplar if x)]}


# ---------------------------------------------------------------------------
# Herkese açık: servis müşterisinin imzalı sayfası
# ---------------------------------------------------------------------------
async def _jetonlu(db: AsyncSession, request: Request, jeton: str) -> SahaIsEmirleri:
    await _kalici_hiz((_acik_hizi, ip_ozeti("saha-acik|" + istemci_ip(request))))
    kimlik = s.jeton_kimligi(jeton)
    if kimlik is None:
        raise _hata(404, "baglanti_gecersiz")
    ie = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.id == kimlik))).scalars().first()
    if ie is None or not s.musteri_jetonu_gecerli_mi(jeton, ie.id, ie.uid):
        raise _hata(404, "baglanti_gecersiz")
    kapanis = ie.bitir_at or ie.iptal_at
    if ie.anonim or (kapanis and s.utc(kapanis) + timedelta(days=s.JETON_OMRU_GUN) < s.simdi()):
        raise _hata(410, "baglanti_suresi_doldu")
    from services.moduller import modul_acik_mi

    if not await modul_acik_mi(db, ie.hesap_email, MODUL):
        raise _hata(410, "sayfa_pasif")
    return ie


async def _google_yorum(db: AsyncSession, ie: SahaIsEmirleri, a: SahaAyarlari) -> Optional[str]:
    """Faz 4K modülü açık ve aktif bir yorum sayfası varsa Google yorum adresi — puandan BAĞIMSIZ
    (review gating yok: herkese, her puanda aynı bağlantı)."""
    from models.kartvizit import YorumSayfalari
    from services.dinamik_qr import google_yorum_adresi
    from services.moduller import modul_acik_mi

    if not await modul_acik_mi(db, ie.hesap_email, "google_yorum_sayfasi"):
        return None
    sorgu = select(YorumSayfalari).where(YorumSayfalari.hesap_email == ie.hesap_email, YorumSayfalari.aktif.is_(True))
    if a.yorum_sayfasi_id:
        sorgu = sorgu.where(YorumSayfalari.id == a.yorum_sayfasi_id)
    y = (await db.execute(sorgu.order_by(YorumSayfalari.id))).scalars().first()
    return google_yorum_adresi(y.place_id) if y and y.place_id else None


async def _acik_sozluk(db: AsyncSession, ie: SahaIsEmirleri) -> Dict[str, Any]:
    a = await sk.ayarlar(db, ie.hesap_email)
    m = (await db.execute(select(SahaMusterileri).where(SahaMusterileri.id == ie.musteri_id))).scalars().first()
    atanan = (await sk.atama_haritasi(db, [ie.id]))[ie.id]
    teknik = [s.ilk_ad(t.ad) for t in (await db.execute(select(SahaTeknisyenleri).where(
        SahaTeknisyenleri.id.in_(atanan or [0])))).scalars().all()]
    return {
        "firma": {"ad": a.firma_adi or "—", "telefon": a.telefon, "eposta": a.eposta},
        "dil": (m.dil if m else None) or a.varsayilan_dil or "tr",
        "musteri_ad": m.ad if m else None,
        "is": {"no": ie.no, "tur": ie.tur, "durum": ie.durum, "baslik": ie.baslik, "plan_bas": s.iso(ie.plan_bas),
               "plan_bit": s.iso(sk.plan_bitisi(ie)), "yolda_at": s.iso(ie.yolda_at), "basla_at": s.iso(ie.basla_at),
               "bitir_at": s.iso(ie.bitir_at), "teknisyenler": teknik, "adres": await sk.adres_metni(db, ie)},
        "pdf_var": ie.durum == "tamamlandi",
        "memnuniyet": {"acik": bool(a.memnuniyet_acik) and ie.durum == "tamamlandi", "puan": ie.memnuniyet_puan,
                       "yorum": ie.memnuniyet_yorum, "at": s.iso(ie.memnuniyet_at)},
        "google_yorum_url": await _google_yorum(db, ie, a),
        "aydinlatma": {"firma": a.firma_adi or ie.hesap_email, "saklama_ay": int(a.saklama_ay or 60), "eposta": a.eposta},
    }


@acik_router.get("/{jeton}")
async def acik_servis(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    ie = await _jetonlu(db, request, jeton)
    from services.marka import acik_marka

    # Faz 4L: servis sayfasının kendi teması yok — marka teması varsayılan.
    return JSONResponse({**await _acik_sozluk(db, ie), "marka": await acik_marka(db, ie.hesap_email)}, headers=ACIK_BASLIKLAR)


@acik_router.get("/{jeton}/pdf")
async def acik_pdf(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    ie = await _jetonlu(db, request, jeton)
    if ie.durum != "tamamlandi":
        raise _hata(409, "henuz_tamamlanmadi")
    return _pdf_yaniti(await pdf_uret(db, ie), ie.no, {"X-Robots-Tag": "noindex, nofollow"})


@acik_router.post("/{jeton}/memnuniyet")
async def acik_memnuniyet(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    ham = await request.body()
    if len(ham) > 8192:
        raise _hata(413, "govde_buyuk")
    try:
        import json

        govde = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(govde, dict):
        raise _hata(400, "govde_gecersiz")
    ie = await _jetonlu(db, request, jeton)
    await _kalici_hiz((_puan_hizi, ip_ozeti("saha-puan|" + istemci_ip(request))))
    a = await sk.ayarlar(db, ie.hesap_email)
    if ie.durum != "tamamlandi" or not a.memnuniyet_acik:
        raise _hata(409, "puanlanamaz")
    if ie.memnuniyet_puan:
        raise _hata(409, "zaten_puanlandi")
    try:
        puan = s.tam_sayi(govde.get("puan"), "puan", 1, 5)
        yorum = s.bos_ya_da(govde.get("yorum"), "yorum", 1000, cok_satir=True)
    except s.SahaHatasi as h:
        raise _s_hatasi(h)
    ie.memnuniyet_puan, ie.memnuniyet_yorum, ie.memnuniyet_at = puan, yorum, s.simdi()
    await db.commit()
    return JSONResponse(await _acik_sozluk(db, ie), headers=ACIK_BASLIKLAR)


@gorsel_router.get("/{anahtar}")
async def gorsel(anahtar: str, request: Request, b: Optional[str] = Query(None), i: Optional[str] = Query(None),
                 db: AsyncSession = Depends(get_db)):
    if len(anahtar) > 64 or not s.gorsel_imzasi_gecerli_mi(anahtar, b, i):
        raise _hata(404, "bulunamadi")
    _hiz(_gorsel_hizi, ip_ozeti("saha-gorsel|" + istemci_ip(request)))
    f = (await db.execute(select(SahaIsFotograflari).where(or_(SahaIsFotograflari.anahtar == anahtar,
                                                               SahaIsFotograflari.kucuk_anahtar == anahtar)))).scalars().first()
    if f is not None:
        depo, tur = f.depo, "image/webp"
    else:
        ie = (await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.imza_anahtari == anahtar))).scalars().first()
        if ie is None:
            raise _hata(404, "bulunamadi")
        depo, tur = ie.imza_depo, "image/png"
    veri = await sk.gorsel_oku(db, depo, anahtar)
    if veri is None:
        raise _hata(404, "bulunamadi")
    return Response(content=veri, media_type=tur, headers={
        "Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline",
        "Cross-Origin-Resource-Policy": "same-origin", "X-Robots-Tag": "noindex"})


router = (yonetici_router, musteri_router, gorsel_router, acik_router)
