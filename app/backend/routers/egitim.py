"""Faz 6K — Eğitim modülü: kurs/okul + LMS (ders, öğrenci, yoklama, quiz/ödev, sertifika).

Herkese açık (oturumsuz):
  GET  /api/v1/egitim/kurs/{slug}                     kurs sayfası (kayıt formu bilgisi, program özeti, doluluk)
  GET  /api/v1/egitim/kurs/{slug}/ozet                paylaşım önizlemesi + schema.org Course (yalnız
                                                       "arama motorlarında görünsün" seçiliyken) — Pages Function
  POST /api/v1/egitim/kurs/{slug}/kayit               kayıt: kilitli koltuk, doluysa bekleme listesi; KVKK aydınlatma
                                                       (onay kutusu yok) + isteğe bağlı pazarlama izni (18 yaş altına yok);
                                                       18 yaş altında veli adı/e-postası zorunlu; hız sınırı + bal küpü
  GET  /api/v1/egitim/kurum/{slug}                    hesabın herkese açık kurs listesi (isteğe bağlı)
  GET  /api/v1/egitim/ogrenci/{jeton}                 öğrenci portalı (imzalı, girişsiz): derslerim, programım, ödevlerim,
                                                       quiz, yoklama durumum, sertifikalarım, duyurular
  GET  /api/v1/egitim/ogrenci/{jeton}/takvim.ics      programım (ICS)
  GET  /api/v1/egitim/ogrenci/{jeton}/qr.svg          öğrencinin yoklama QR'ı (içerik: yalnız kod + imza)
  GET  /api/v1/egitim/ogrenci/{jeton}/ders/{did}      ders içeriği (+ ekler, video bağlantısı)
  POST /api/v1/egitim/ogrenci/{jeton}/ders/{did}/tamamla   ilerleme işareti (`{"tamamlandi": true|false}`)
  GET  /api/v1/egitim/ogrenci/{jeton}/dosya/{fid}     ders eki / kendi teslim dosyası
  POST /api/v1/egitim/ogrenci/{jeton}/quiz/{qid}/basla     deneme başlat (sorular cevapsız; süre sunucuda)
  POST /api/v1/egitim/ogrenci/{jeton}/quiz/{qid}/gonder    yanıtlar → otomatik puan (süre aşımı → 0)
  POST /api/v1/egitim/ogrenci/{jeton}/odev/{qid}           ödev teslimi (metin + dosya; notlanana kadar yeniden)
  POST /api/v1/egitim/ogrenci/{jeton}/yoklama              tahtadaki 6 haneli oturum koduyla "buradayım"
  GET  /api/v1/egitim/ogrenci/{jeton}/sertifika.pdf        sertifika PDF'i
  GET  /api/v1/egitim/yoklama/{jeton}                 oturum QR'ının açtığı sayfa (kurs + saat; kişisel veri yok)
  POST /api/v1/egitim/yoklama/{jeton}                 bu cihazdaki öğrenci bağlantısıyla "buradayım"
  GET  /api/v1/egitim/sertifika/{kod}                 sertifika doğrulama (kişisel veri en az: maskeli ad)

Yönetici (`/api/v1/egitim/yonetim`) — ajansın kendi kursları (+ müşterilerinkini destek için görür).
Müşteri (`/api/v1/egitimim`; modül `egitim` açık; ekip izni `egitim` = yönetim, `egitim_egitmen` = YALNIZ
e-postası kursun eğitmen listesinde geçen kurslar ve yalnız yoklama + not (ders/öğrenci listesi okuma)):
  GET /meta · GET|PUT /ayarlar · GET|POST "" · GET|PUT|DELETE /{kid} · GET /{kid}/qr · GET /{kid}/takvim.ics
  GET|POST /{kid}/oturumlar · POST /{kid}/oturumlar/uret · PUT|DELETE /{kid}/oturumlar/{oid}
  GET /{kid}/oturumlar/{oid}/yoklama · PUT /{kid}/oturumlar/{oid}/yoklama/{ogid} · POST /{kid}/oturumlar/{oid}/yoklama-kapat
  GET /{kid}/oturumlar/{oid}/qr · POST /{kid}/oturumlar/{oid}/qr-yenile · GET /{kid}/oturumlar/{oid}/okutucu
  GET /{kid}/oturumlar/{oid}/sayac · POST /{kid}/oturumlar/{oid}/okut
  GET|POST /{kid}/ogrenciler · POST /{kid}/ogrenciler/csv · GET /{kid}/ogrenciler.csv
  PUT|DELETE /{kid}/ogrenciler/{ogid} · POST /{kid}/ogrenciler/{ogid}/baglanti · GET /{kid}/ilerleme
  GET|POST /{kid}/dersler · PUT /{kid}/dersler-sira · PUT|DELETE /{kid}/dersler/{did} · POST /{kid}/dersler/{did}/dosyalar
  GET|DELETE /{kid}/dosyalar/{fid}
  GET|POST /{kid}/quizler · POST /{kid}/quizler/ai · PUT|DELETE /{kid}/quizler/{qid} · GET /{kid}/quizler/{qid}/sonuclar
  PUT /{kid}/teslimler/{tid}
  GET|POST /{kid}/sertifikalar · POST /{kid}/sertifikalar/toplu · DELETE /{kid}/sertifikalar/{sid} · GET /{kid}/sertifikalar/{sid}/pdf
  GET /{kid}/duyurular · POST /{kid}/duyuru

Kurallar: müşteri yalnız etkin hesabın kurslarını görür; modül kapalıysa 403 `modul_kapali`; sahibinin
modülü kapanan kursun herkese açık sayfası ve öğrenci bağlantısı 410. Ücretli tahsilat YOK (fiyat yalnız
metin; ödeme sağlayıcısı entegrasyonu gelince ayrı iş).
"""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from models.egitim import (
    EgitimAyarlari,
    EgitimDenemeleri,
    EgitimDersleri,
    EgitimDosyalari,
    EgitimDuyurulari,
    EgitimIlerleme,
    EgitimKurslari,
    EgitimOgrencileri,
    EgitimOturumlari,
    EgitimQuizleri,
    EgitimSertifikalari,
    EgitimTeslimleri,
    EgitimYoklama,
)
from services import dinamik_qr as qr
from services import egitim as s
from services import egitim_kayit as k
from services.dosya_deposu import icerik_konumu
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN
IZIN_EGITMEN = s.IZIN_EGITMEN

acik_router = APIRouter(prefix="/api/v1/egitim", tags=["egitim"])
yonetici_router = APIRouter(prefix="/api/v1/egitim/yonetim", tags=["egitim"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/egitimim",
    tags=["egitim"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN, IZIN_EGITMEN))],
)

#: Panel (kişi başı): dakikada 60 yazma, 20 görsel/CSV/PDF; saatte 5 duyuru (kurs başı).
_yazma_hizi = HizSiniri(60, 60.0)
_gorsel_hizi = HizSiniri(30, 60.0)
_duyuru_hizi = HizSiniri(5, 3600.0)
_okut_hizi = HizSiniri(240, 60.0)
_ai_hizi = HizSiniri(10, 60.0)
#: Ziyaretçi: 10 dakikada 6 kayıt (IP özeti + kurs), kurs başına dakikada 60.
_kayit_hizi = KaliciHizSiniri("egitim-kayit", 6, 600.0)
_kurs_kayit_hizi = KaliciHizSiniri("egitim-kurs", 60, 60.0)
#: Öğrenci bağlantısı / doğrulama sayfası (IP özeti): dakikada 120 / 60.
_portal_hizi = KaliciHizSiniri("egitim-portal", 120, 60.0)
_dogrulama_hizi = KaliciHizSiniri("egitim-sertifika", 60, 60.0)
#: Öğrenci yazmaları (öğrenci başı): dakikada 30.
_ogrenci_yazma_hizi = HizSiniri(30, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _gorsel_hizi, _duyuru_hizi, _okut_hizi, _ai_hizi, _kayit_hizi, _kurs_kayit_hizi, _portal_hizi,
              _dogrulama_hizi, _ogrenci_yazma_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    yonetici: bool
    #: Müşteride etkin hesap; yöneticide None (bütün kayıtlar).
    hesap: Optional[str]
    kisi: str
    #: Tam yönetim (`egitim` izni, hesap sahibi ya da ajans yöneticisi).
    yonetim: bool
    #: `egitim_egitmen`: yalnız eğitmeni olduğu kurslar (yoklama + not).
    egitmen: bool


def _yonetici_kapsami(request: Request) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    return Kapsam(True, None, (getattr(kullanici, "email", "") or "").strip().lower(), True, False)


def _musteri_kapsami(request: Request) -> Kapsam:
    b = izin_iste(request, IZIN, IZIN_EGITMEN)
    return Kapsam(False, b.hesap_email, b.kisi_email, b.izin_var(IZIN), b.izin_var(IZIN_EGITMEN))


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _e_hatasi(h: s.TemelHata) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _yonetim_iste(kapsam: Kapsam) -> None:
    if not kapsam.yonetim:
        raise _hata(403, "hesap_izni_yok", izin=IZIN)


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


def _ziyaretci(request: Request, ek: Any = "") -> str:
    return f"{ek}|{ip_ozeti('egitim-hiz|' + istemci_ip(request))}"


async def _govde_oku(request: Request, sinir: int = 32768) -> Dict[str, Any]:
    ham = await request.body()
    if len(ham) > sinir:
        raise _hata(413, "govde_buyuk")
    try:
        govde = json.loads(ham.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(govde, dict):
        raise _hata(400, "govde_gecersiz")
    return govde


ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
GIZLI_BASLIKLAR = {**ACIK_BASLIKLAR, "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"}


def _qr_gorsel(icerik: str, bicim: str, renk: Optional[str] = None) -> qr.Gorsel:
    tasarim = dict(qr.VARSAYILAN_TASARIM)
    if renk and qr.kontrast_orani(renk, "#ffffff") >= 4.5:
        tasarim["on_renk"] = renk
    tasarim = qr.tasarim_duzelt(tasarim)
    return (qr.png_ciz if bicim == "png" else qr.svg_ciz)(icerik, tasarim, None)


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _kurs_sozlugu(x: EgitimKurslari, **ek: Any) -> Dict[str, Any]:
    return {
        "id": x.id, "hesap_email": x.hesap_email, "ajans": x.hesap_email is None, "slug": x.slug,
        "adres_url": s.kurs_adresi(x.slug), "ad": x.ad, "ozet": x.ozet or "", "aciklama": x.aciklama or "",
        "renk": x.renk, "egitmenler": s.json_yukle(x.egitmenler, []) or [], "bicim": x.bicim, "mekan": x.mekan or "",
        "adres": x.adres or "", "online_baglanti": x.online_baglanti or "", "saat_dilimi": x.saat_dilimi,
        "baslangic_tarihi": x.baslangic_tarihi.isoformat() if x.baslangic_tarihi else None,
        "bitis_tarihi": x.bitis_tarihi.isoformat() if x.bitis_tarihi else None, "kapasite": x.kapasite,
        "fiyat_metni": x.fiyat_metni or "", "durum": x.durum, "kayit_acik": bool(x.kayit_acik),
        "bekleme_listesi": bool(x.bekleme_listesi), "hedef_kitle": x.hedef_kitle, "telefon": x.telefon, "dil": x.dil,
        "kvkk_metni": x.kvkk_metni or "", "arama_motoru": bool(x.arama_motoru), "listede_goster": bool(x.listede_goster),
        "devamsizlik_esik": int(x.devamsizlik_esik or 0), "hatirlatma_saat": int(x.hatirlatma_saat or 0),
        "sertifika_aktif": bool(x.sertifika_aktif), "otomatik_sertifika": bool(x.otomatik_sertifika),
        "kosul_ilerleme": int(x.kosul_ilerleme), "kosul_quiz": int(x.kosul_quiz), "kosul_yoklama": int(x.kosul_yoklama),
        "sertifika_sablon": x.sertifika_sablon, "sertifika_saat": x.sertifika_saat, "saklama_gun": int(x.saklama_gun),
        "created_at": s.iso(x.created_at), "updated_at": s.iso(x.updated_at), **ek,
    }


def _oturum_sozlugu(o: EgitimOturumlari, **ek: Any) -> Dict[str, Any]:
    return {"id": o.id, "kurs_id": o.kurs_id, "baslangic": s.iso(o.baslangic), "bitis": s.iso(o.bitis), "konu": o.konu or "",
            "durum": o.durum, "yoklama_acik": s.yoklama_acik_mi(o), **ek}


def _ogrenci_sozlugu(o: EgitimOgrencileri, yonetim: bool, ist: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {"id": o.id, "kod": o.kod, "ad": o.ad or "—", "durum": o.durum, "cocuk": bool(o.cocuk),
                         "anonim": bool(o.anonim), "created_at": s.iso(o.created_at)}
    if yonetim:
        # Eğitmene (yalnız `egitim_egitmen`) iletişim ve veli bilgisi GİTMEZ (en az veri).
        d.update({"eposta": o.eposta or "", "telefon": o.telefon or "", "veli_ad": o.veli_ad or "",
                  "veli_telefon": o.veli_telefon or "", "veli_eposta": o.veli_eposta or "", "kaynak": o.kaynak,
                  "notlar": o.notlar or "", "dil": o.dil, "pazarlama_izni": o.pazarlama_izni_at is not None,
                  "portal_son_at": s.iso(o.portal_son_at), "devamsizlik_uyari_at": s.iso(o.devamsizlik_uyari_at)})
    if ist is not None:
        d["istatistik"] = ist
    return d


def _dosya_sozlugu(d: EgitimDosyalari) -> Dict[str, Any]:
    return {"id": d.id, "ad": d.ad, "tur": d.tur, "boyut": int(d.boyut or 0), "created_at": s.iso(d.created_at)}


def _ders_sozlugu(d: EgitimDersleri, dosyalar: Optional[List[EgitimDosyalari]] = None) -> Dict[str, Any]:
    return {"id": d.id, "kurs_id": d.kurs_id, "bolum": d.bolum or "", "sira": int(d.sira or 0), "baslik": d.baslik,
            "icerik": d.icerik or "", "video_url": d.video_url or "", "video": s.video_bilgisi(d.video_url),
            "sure_dk": d.sure_dk, "yayinda": bool(d.yayinda), "dosyalar": [_dosya_sozlugu(x) for x in (dosyalar or [])]}


def _quiz_sozlugu(q: EgitimQuizleri, cevapli: bool = True) -> Dict[str, Any]:
    sorular = s.json_yukle(q.sorular, []) or []
    return {"id": q.id, "kurs_id": q.kurs_id, "ders_id": q.ders_id, "tur": q.tur, "baslik": q.baslik,
            "aciklama": q.aciklama or "", "sorular": sorular if cevapli else s.sorular_ogrenciye(sorular),
            "soru_sayisi": len(sorular), "sure_dk": q.sure_dk, "gecme_puani": int(q.gecme_puani),
            "deneme_hakki": int(q.deneme_hakki), "son_tarih": s.iso(q.son_tarih), "yayinda": bool(q.yayinda),
            "sira": int(q.sira or 0), "ai_uretildi": bool(q.ai_uretildi)}


def _sertifika_sozlugu(x: EgitimSertifikalari, ad: Optional[str] = None) -> Dict[str, Any]:
    return {"id": x.id, "kod": x.kod, "kod_yazi": s.sertifika_kodu_yaz(x.kod), "ogrenci_id": x.ogrenci_id,
            "ad": ad, "ad_maskeli": x.ad_maskeli, "verilme_at": s.iso(x.verilme_at), "iptal_at": s.iso(x.iptal_at),
            "kaynak": x.kaynak, "dogrulama_adresi": s.sertifika_adresi(x.kod)}


def _ayar_sozlugu(a: Optional[EgitimAyarlari], kapsam_: str) -> Dict[str, Any]:
    return {
        "kapsam": kapsam_, "kurum_adi": (a.kurum_adi if a else "") or "", "imza_adi": (a.imza_adi if a else "") or "",
        "imza_unvan": (a.imza_unvan if a else "") or "", "liste_slug": (a.liste_slug if a else "") or "",
        "liste_baslik": (a.liste_baslik if a else "") or "", "liste_aciklama": (a.liste_aciklama if a else "") or "",
        "liste_acik": bool(a.liste_acik) if a else False,
        "liste_adresi": s.kurum_adresi(a.liste_slug) if a and a.liste_slug else None,
    }


# ---------------------------------------------------------------------------
# Kayıt bulucular
# ---------------------------------------------------------------------------
async def _kurs(db: AsyncSession, kid: int, kapsam: Kapsam, yonetim: bool = False) -> EgitimKurslari:
    sorgu = select(EgitimKurslari).where(EgitimKurslari.id == kid)
    if not kapsam.yonetici:
        sorgu = sorgu.where(EgitimKurslari.hesap_email == kapsam.hesap)
    x = (await db.execute(sorgu)).scalars().first()
    if x is None:
        raise _hata(404, "bulunamadi")
    if yonetim:
        _yonetim_iste(kapsam)
    elif not kapsam.yonetim and not s.egitmen_mi(x, kapsam.kisi):
        # Eğitmen yalnız kendi kursunu görür; başkasınınki "yok" (varlığı sızmasın).
        raise _hata(404, "bulunamadi")
    return x


async def _oturum(db: AsyncSession, x: EgitimKurslari, oid: int) -> EgitimOturumlari:
    o = (await db.execute(select(EgitimOturumlari).where(EgitimOturumlari.id == oid,
                                                         EgitimOturumlari.kurs_id == x.id))).scalars().first()
    if o is None:
        raise _hata(404, "bulunamadi")
    return o


async def _ogrenci(db: AsyncSession, x: EgitimKurslari, ogid: int) -> EgitimOgrencileri:
    o = (await db.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == ogid,
                                                          EgitimOgrencileri.kurs_id == x.id))).scalars().first()
    if o is None:
        raise _hata(404, "bulunamadi")
    return o


async def _ders(db: AsyncSession, x: EgitimKurslari, did: int) -> EgitimDersleri:
    d = (await db.execute(select(EgitimDersleri).where(EgitimDersleri.id == did, EgitimDersleri.kurs_id == x.id))).scalars().first()
    if d is None:
        raise _hata(404, "bulunamadi")
    return d


async def _quiz(db: AsyncSession, x: EgitimKurslari, qid: int) -> EgitimQuizleri:
    q = (await db.execute(select(EgitimQuizleri).where(EgitimQuizleri.id == qid, EgitimQuizleri.kurs_id == x.id))).scalars().first()
    if q is None:
        raise _hata(404, "bulunamadi")
    return q


async def _slug_bos_mu(db: AsyncSession, slug: str, haric: Optional[int] = None) -> bool:
    sorgu = select(EgitimKurslari.id).where(EgitimKurslari.slug == slug)
    if haric is not None:
        sorgu = sorgu.where(EgitimKurslari.id != haric)
    return (await db.execute(sorgu.limit(1))).first() is None


async def _bos_slug(db: AsyncSession, oneri: str) -> str:
    aday = oneri
    for i in range(2, 60):
        if await _slug_bos_mu(db, aday):
            return aday
        aday = f"{oneri[:44]}-{i}"
    import uuid

    return f"{oneri[:40]}-{uuid.uuid4().hex[:6]}"


async def _dosyalar(db: AsyncSession, ders_idleri: List[int]) -> Dict[int, List[EgitimDosyalari]]:
    sonuc: Dict[int, List[EgitimDosyalari]] = {}
    if not ders_idleri:
        return sonuc
    for d in (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.ders_id.in_(ders_idleri))
                               .order_by(EgitimDosyalari.id))).scalars().all():
        sonuc.setdefault(d.ders_id, []).append(d)
    return sonuc


async def _dosya_yaniti(db: AsyncSession, d: EgitimDosyalari) -> Response:
    from services import dosya_deposu

    adres = dosya_deposu.dogrudan_adres(d.depo, d.anahtar, d.ad, d.tur)
    if adres:
        return RedirectResponse(adres, status_code=302, headers={"Cache-Control": "no-store"})
    try:
        veri = await dosya_deposu.oku(db, d.depo, d.anahtar)
    except dosya_deposu.DepoHatasi:
        raise _hata(502, "depo_hatasi")
    return Response(veri, media_type=d.tur, headers={"Content-Disposition": icerik_konumu(d.ad), "Cache-Control": "no-store",
                                                     "X-Content-Type-Options": "nosniff"})


async def _dosya_oku(dosya: UploadFile, db: AsyncSession) -> bytes:
    from services import dosyalar

    try:
        sinir = min(await dosyalar.boyut_siniri_bayt(db), s.DOSYA_EN_COK_MB * 1024 * 1024)
        return await dosyalar.akistan_oku(dosya, sinir)
    except dosyalar.DosyaHatasi as h:
        raise _hata(h.durum, h.kod, **h.ek)


# ---------------------------------------------------------------------------
# Kurs: uygula / oluştur / liste / meta
# ---------------------------------------------------------------------------
async def _kurs_uygula(db: AsyncSession, x: EgitimKurslari, g: Dict[str, Any], yeni: bool) -> None:
    if "ad" in g or yeni:
        x.ad = s.metin(g.get("ad"), "ad", 160, zorunlu=True)
    if "slug" in g and g.get("slug"):
        slug = s.slug_duzelt(g.get("slug"))
        if slug != x.slug and not await _slug_bos_mu(db, slug, None if yeni else x.id):
            raise s.EgitimHatasi("slug_dolu", "slug", durum=409)
        x.slug = slug
    elif yeni:
        x.slug = await _bos_slug(db, s.slug_oner(x.ad))
    for alan, sinir, cok in (("ozet", 300, False), ("aciklama", 20000, True), ("mekan", 160, False), ("adres", 500, True),
                             ("fiyat_metni", 300, False), ("kvkk_metni", 3000, True)):
        if alan in g:
            setattr(x, alan, s.metin(g.get(alan), alan, sinir, cok_satir=cok) or None)
    if "online_baglanti" in g:
        x.online_baglanti = s.https_duzelt(g.get("online_baglanti"), "online_baglanti")
    if "renk" in g:
        x.renk = s.renk_duzelt(g.get("renk"))
    if "egitmenler" in g:
        x.egitmenler = s.json_yaz(s.egitmenler_duzelt(g.get("egitmenler"))) if g.get("egitmenler") else None
    for alan, secenekler in (("bicim", s.BICIMLER), ("hedef_kitle", s.HEDEF_KITLELER), ("telefon", s.TELEFON_SECENEKLERI),
                             ("sertifika_sablon", s.SABLONLAR)):
        if alan in g:
            setattr(x, alan, s.secim(g.get(alan), secenekler, alan))
    if "saat_dilimi" in g or yeni:
        x.saat_dilimi = s.saat_dilimi_duzelt(g.get("saat_dilimi") or x.saat_dilimi or s.VARSAYILAN_SAAT_DILIMI)
    if "dil" in g or yeni:
        x.dil = s.dil_duzelt(g.get("dil") or x.dil or "tr")
    if "baslangic_tarihi" in g:
        x.baslangic_tarihi = s.tarih_duzelt(g.get("baslangic_tarihi"), "baslangic_tarihi")
    if "bitis_tarihi" in g:
        x.bitis_tarihi = s.tarih_duzelt(g.get("bitis_tarihi"), "bitis_tarihi")
    if x.baslangic_tarihi and x.bitis_tarihi and x.bitis_tarihi < x.baslangic_tarihi:
        raise s.EgitimHatasi("bitis_once", "bitis_tarihi")
    if "kapasite" in g:
        x.kapasite = s.tam_sayi(g.get("kapasite"), "kapasite", 1, s.KAPASITE_EN_COK, bos_olabilir=True)
    for alan in ("kayit_acik", "bekleme_listesi", "arama_motoru", "listede_goster", "sertifika_aktif", "otomatik_sertifika"):
        if alan in g:
            setattr(x, alan, s.bool_duzelt(g.get(alan), alan))
    for alan, en_az, en_cok in (("devamsizlik_esik", 0, 100), ("hatirlatma_saat", 0, 72), ("kosul_ilerleme", 0, 100),
                                ("kosul_quiz", 0, 100), ("kosul_yoklama", 0, 100),
                                ("saklama_gun", s.SAKLAMA_EN_AZ, s.SAKLAMA_EN_COK)):
        if alan in g:
            setattr(x, alan, s.tam_sayi(g.get(alan), alan, en_az, en_cok))
    if "sertifika_saat" in g:
        x.sertifika_saat = s.tam_sayi(g.get("sertifika_saat"), "sertifika_saat", 1, 10000, bos_olabilir=True)
    if "durum" in g:
        durum = s.secim(g.get("durum"), s.DURUMLAR, "durum")
        if durum == "yayinda" and x.bicim in ("online", "karma") and not x.online_baglanti:
            raise s.EgitimHatasi("online_baglanti_gerekli", "online_baglanti")
        x.durum = durum


async def _kurs_sayisi(db: AsyncSession, hesap: str) -> int:
    return int((await db.execute(select(func.count(EgitimKurslari.id)).where(
        EgitimKurslari.hesap_email == hesap, EgitimKurslari.durum != "arsiv"))).scalar() or 0)


async def _olustur(db: AsyncSession, kapsam: Kapsam, g: Dict[str, Any]) -> Dict[str, Any]:
    _yonetim_iste(kapsam)
    try:
        if kapsam.yonetici:
            ham = str(g.get("hesap_email") or "").strip()
            hesap = s.eposta_duzelt(ham, "hesap_email") if ham else None
        else:
            hesap = kapsam.hesap
        if hesap and not kapsam.yonetici:
            sinir = await k.modul_ayari(db, hesap, "kurs_siniri", k.VARSAYILAN_KURS_SINIRI)
            if sinir is not None and await _kurs_sayisi(db, hesap) >= int(sinir):
                raise s.EgitimHatasi("kurs_siniri", durum=409, sinir=int(sinir))
        x = EgitimKurslari(hesap_email=hesap, olusturan_email=kapsam.kisi, durum="taslak", renk="#2563eb",
                           bicim="yuz_yuze", hedef_kitle="yetiskin", telefon="istege_bagli", kayit_acik=True,
                           bekleme_listesi=True, listede_goster=True, arama_motoru=False, devamsizlik_esik=3,
                           hatirlatma_saat=0, sertifika_aktif=True, otomatik_sertifika=False, kosul_ilerleme=80,
                           kosul_quiz=60, kosul_yoklama=70, sertifika_sablon="klasik", saklama_gun=s.VARSAYILAN_SAKLAMA_GUN,
                           kilit=0, created_at=s.simdi())
        g = dict(g)
        g.pop("durum", None)  # yeni kurs taslak
        await _kurs_uygula(db, x, g, yeni=True)
    except s.TemelHata as h:
        raise _e_hatasi(h)
    db.add(x)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_dolu", alan="slug")
    await db.refresh(x)
    return _kurs_sozlugu(x)


async def _liste(db: AsyncSession, kapsam: Kapsam, hesap: Optional[str]) -> Dict[str, Any]:
    sorgu = select(EgitimKurslari)
    if not kapsam.yonetici:
        sorgu = sorgu.where(EgitimKurslari.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(EgitimKurslari.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(EgitimKurslari.hesap_email == hesap.strip().lower())
    kayitlar = (await db.execute(sorgu.order_by(EgitimKurslari.id.desc()).limit(500))).scalars().all()
    if not kapsam.yonetim:
        kayitlar = [x for x in kayitlar if s.egitmen_mi(x, kapsam.kisi)]
    idler = [x.id for x in kayitlar]
    sayilar: Dict[int, Dict[str, int]] = {}
    if idler:
        for kid, durum, n in (await db.execute(select(EgitimOgrencileri.kurs_id, EgitimOgrencileri.durum,
                                                      func.count(EgitimOgrencileri.id))
                                               .where(EgitimOgrencileri.kurs_id.in_(idler))
                                               .group_by(EgitimOgrencileri.kurs_id, EgitimOgrencileri.durum))).all():
            sayilar.setdefault(kid, {})[durum] = int(n)
        sonraki: Dict[int, datetime] = {}
        # func.min SQLite'ta metin döndürüyor: sıralı satırlar (sütun türüyle), kurs başına ilki.
        for kid, an in (await db.execute(select(EgitimOturumlari.kurs_id, EgitimOturumlari.baslangic).where(
                EgitimOturumlari.kurs_id.in_(idler), EgitimOturumlari.durum == "planli",
                EgitimOturumlari.baslangic > s.simdi()).order_by(EgitimOturumlari.baslangic).limit(5000))).all():
            sonraki.setdefault(kid, an)
    else:
        sonraki = {}
    return {"items": [_kurs_sozlugu(x, ogrenci=sayilar.get(x.id, {}).get("aktif", 0),
                                    bekleme=sayilar.get(x.id, {}).get("bekleme", 0),
                                    sonraki_ders=s.iso(sonraki.get(x.id))) for x in kayitlar], "toplam": len(kayitlar)}


async def _meta(db: AsyncSession, kapsam: Kapsam) -> Dict[str, Any]:
    hesap = None if kapsam.yonetici else kapsam.hesap
    kurs_siniri = ogrenci_siniri = None
    kurs_sayisi = ogrenci_sayisi = None
    if hesap:
        kurs_siniri = await k.modul_ayari(db, hesap, "kurs_siniri", k.VARSAYILAN_KURS_SINIRI)
        ogrenci_siniri = await k.modul_ayari(db, hesap, "ogrenci_siniri", k.VARSAYILAN_OGRENCI_SINIRI)
        kurs_sayisi = await _kurs_sayisi(db, hesap)
        ogrenci_sayisi = int((await db.execute(select(func.count(EgitimOgrencileri.id)).where(
            EgitimOgrencileri.hesap_email == hesap, EgitimOgrencileri.durum.in_(("aktif", "bekleme")),
            EgitimOgrencileri.anonim.is_(False)))).scalar() or 0)
    return {
        "yonetici": kapsam.yonetici, "yonetim": kapsam.yonetim, "egitmen": kapsam.egitmen and not kapsam.yonetim,
        "kisi": kapsam.kisi, "kurs_siniri": kurs_siniri, "kurs_sayisi": kurs_sayisi, "ogrenci_siniri": ogrenci_siniri,
        "ogrenci_sayisi": ogrenci_sayisi, "ai": await k.ai_ozeti(db, hesap) if kapsam.yonetim else None,
        "bicimler": list(s.BICIMLER), "durumlar": list(s.DURUMLAR), "hedef_kitleler": list(s.HEDEF_KITLELER),
        "telefon_secenekleri": list(s.TELEFON_SECENEKLERI), "ogrenci_durumlari": list(s.OGRENCI_DURUMLARI),
        "yoklama_durumlari": list(s.YOKLAMA_DURUMLARI), "soru_turleri": list(s.SORU_TURLERI),
        "sablonlar": list(s.SABLONLAR), "diller": list(s.DILLER), "adres_tabani": f"{s.site_adresi()}/egitim/",
        "varsayilan_saat_dilimi": s.VARSAYILAN_SAAT_DILIMI, "en_cok_csv": s.EN_COK_CSV,
        "saklama": {"en_az": s.SAKLAMA_EN_AZ, "en_cok": s.SAKLAMA_EN_COK, "varsayilan": s.VARSAYILAN_SAKLAMA_GUN},
        # Ücretli tahsilat yok: fiyat yalnız metin (ödeme sağlayıcısı entegrasyonu ayrı iş).
        "ucretli_kayit": False,
    }


def _kayit_girdisi(x: EgitimKurslari, g: Dict[str, Any], kaynak: str) -> k.KayitGirdisi:
    """Form / elle / CSV satırı → doğrulanmış girdi. 18 yaş altı (çocuk kursu ya da karma kursta işaretli)
    için veli adı + e-postası zorunlu, öğrencinin e-postası isteğe bağlı; yetişkinde öğrenci e-postası zorunlu."""
    from services import pazarlama_izni

    if x.hedef_kitle == "cocuk":
        cocuk = True
    elif x.hedef_kitle == "yetiskin":
        cocuk = False
    else:
        cocuk = g.get("cocuk") is True or (isinstance(g.get("cocuk"), str) and s.evet_mi(g.get("cocuk")))
    telefon_kurali = x.telefon or "istege_bagli"
    girdi = k.KayitGirdisi(
        ad=s.metin(g.get("ad"), "ad", 120, zorunlu=True),
        eposta=s.eposta_duzelt(g.get("eposta"), "eposta", zorunlu=not cocuk) or None,
        telefon=None if telefon_kurali == "gizli" else s.telefon_duzelt(
            g.get("telefon"), "telefon", zorunlu=telefon_kurali == "zorunlu" and kaynak == "form" and not cocuk),
        cocuk=cocuk, dil=g.get("dil") if g.get("dil") in s.DILLER else x.dil, kaynak=kaynak,
        pazarlama_izni=(not cocuk) and pazarlama_izni.izin_verildi_mi(g.get("pazarlama_izni")) and kaynak == "form",
    )
    if cocuk:
        girdi.veli_ad = s.metin(g.get("veli_ad"), "veli_ad", 120, zorunlu=True)
        girdi.veli_eposta = s.eposta_duzelt(g.get("veli_eposta"), "veli_eposta", zorunlu=True)
        girdi.veli_telefon = s.telefon_duzelt(g.get("veli_telefon"), "veli_telefon",
                                              zorunlu=telefon_kurali == "zorunlu" and kaynak == "form")
    return girdi


# ---------------------------------------------------------------------------
# Uçlar (yönetici ve müşteri için aynı gövdeler)
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        return await _meta(db, kapsam_al(request))

    # --- Hesap ayarları (kurum adı, sertifika imzası, kurs listesi sayfası) ---
    def _ayar_hesabi(kapsam: Kapsam, hesap: Optional[str]) -> Optional[str]:
        if kapsam.yonetici:
            return (hesap.strip().lower() or None) if hesap and hesap != "ajans" else None
        return kapsam.hesap

    @router.get("/ayarlar")
    async def ayarlar(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yonetim_iste(kapsam)
        h = _ayar_hesabi(kapsam, hesap)
        return _ayar_sozlugu(await k.hesap_ayarlari(db, h), k.kapsam_anahtari(h))

    @router.put("/ayarlar")
    async def ayarlar_yaz(request: Request, govde: Dict[str, Any] = Body(...), hesap: Optional[str] = Query(None),
                          db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yonetim_iste(kapsam)
        _hiz(_yazma_hizi, kapsam.kisi)
        h = _ayar_hesabi(kapsam, hesap)
        a = await k.hesap_ayarlari(db, h)
        if a is None:
            a = EgitimAyarlari(kapsam=k.kapsam_anahtari(h), hesap_email=h, liste_acik=False, created_at=s.simdi())
            db.add(a)
        try:
            for alan, sinir in (("kurum_adi", 160), ("imza_adi", 120), ("imza_unvan", 120), ("liste_baslik", 160)):
                if alan in govde:
                    setattr(a, alan, s.metin(govde.get(alan), alan, sinir) or None)
            if "liste_aciklama" in govde:
                a.liste_aciklama = s.metin(govde.get("liste_aciklama"), "liste_aciklama", 1000, cok_satir=True) or None
            if "liste_slug" in govde:
                a.liste_slug = s.slug_duzelt(govde.get("liste_slug"), "liste_slug") if govde.get("liste_slug") else None
            if "liste_acik" in govde:
                a.liste_acik = s.bool_duzelt(govde.get("liste_acik"), "liste_acik")
            if a.liste_acik and not a.liste_slug:
                raise s.EgitimHatasi("zorunlu", "liste_slug")
        except s.TemelHata as hata:
            await db.rollback()
            raise _e_hatasi(hata)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "slug_dolu", alan="liste_slug")
        await db.refresh(a)
        return _ayar_sozlugu(a, a.kapsam)

    # --- Kurslar ---
    @router.get("")
    async def liste(request: Request, hesap: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, hesap if kapsam.yonetici else None)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        return await _olustur(db, kapsam, govde)

    @router.get("/{kid}")
    async def ayrinti(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam)
        return _kurs_sozlugu(x, ogrenci=await k.aktif_sayisi(db, x.id), yonetim=kapsam.yonetim)

    @router.put("/{kid}")
    async def guncelle(kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                       db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        eski_kapasite = x.kapasite
        try:
            await _kurs_uygula(db, x, govde, yeni=False)
            if "kapasite" in govde and x.kapasite is not None:
                aktif = await k.aktif_sayisi(db, x.id)
                if aktif > int(x.kapasite):
                    raise s.EgitimHatasi("kapasite_az", "kapasite", durum=409, en_az=aktif)
                # Sonradan kapasite kondu: koltuğu olmayan aktif öğrencilere koltuk.
                dolu = await k.dolu_koltuklar(db, x.id)
                for o in (await db.execute(select(EgitimOgrencileri).where(
                        EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "aktif",
                        EgitimOgrencileri.koltuk.is_(None)))).scalars().all():
                    o.koltuk = k.bos_koltuk(int(x.kapasite), dolu)
                    dolu.add(o.koltuk)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        alinan: List[int] = []
        if "kapasite" in govde and (x.kapasite is None or (eski_kapasite is not None and x.kapasite > eski_kapasite)):
            await db.flush()
            alinan = await k.bekleyenleri_al(db, x)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "slug_dolu", alan="slug")
        await db.refresh(x)
        if alinan:
            arka.add_task(k.ogrenci_epostalari, alinan, "yer")
        return _kurs_sozlugu(x, ogrenci=await k.aktif_sayisi(db, x.id), yonetim=True)

    @router.delete("/{kid}")
    async def sil(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Kurs çöp kutusuna (oturum, ders, quiz birlikte); öğrencilerin kişisel alanları HEMEN anonimleşir."""
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        await k.anonimlestir(db, x, hemen=True)
        await db.execute(update(EgitimOgrencileri).where(EgitimOgrencileri.kurs_id == x.id)
                         .values(durum="ayrildi", koltuk=None).execution_options(synchronize_session=False))
        cocuklar: List[Any] = []
        for model in (EgitimOturumlari, EgitimDersleri, EgitimQuizleri):
            cocuklar += list((await db.execute(select(model).where(model.kurs_id == x.id))).scalars().all())
        for kayit in cocuklar:
            await db.delete(kayit)
        await db.delete(x)
        await db.commit()
        return {"ok": True}

    @router.get("/{kid}/qr")
    async def kurs_qr(kid: int, request: Request, bicim: str = Query("png"), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        _hiz(_gorsel_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        g = _qr_gorsel(s.kurs_adresi(x.slug), bicim, x.renk)
        return Response(g.veri, media_type=g.tur, headers={"Content-Disposition": icerik_konumu(f"kurs-{x.slug}-qr.{bicim}"),
                                                           "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @router.get("/{kid}/takvim.ics")
    async def kurs_takvimi(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam)
        metin_ = s.ics_uret(x, await k.oturumlar(db, x.id), x.dil, ogrenciye=True, adres=s.kurs_adresi(x.slug))
        return Response(metin_, media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": icerik_konumu(f"{x.slug}.ics"), "Cache-Control": "no-store"})

    # --- Oturumlar (program) ---
    @router.get("/{kid}/oturumlar")
    async def oturum_listesi(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request))
        liste_ = await k.oturumlar(db, x.id)
        sayilar: Dict[int, int] = {}
        if liste_:
            for oid, n in (await db.execute(select(EgitimYoklama.oturum_id, func.count(EgitimYoklama.id)).where(
                    EgitimYoklama.kurs_id == x.id, EgitimYoklama.durum.in_(s.KATILDI)).group_by(EgitimYoklama.oturum_id))).all():
                sayilar[int(oid)] = int(n)
        return {"items": [_oturum_sozlugu(o, katilan=sayilar.get(o.id, 0)) for o in liste_],
                "aktif_ogrenci": await k.aktif_sayisi(db, x.id), "saat_dilimi": x.saat_dilimi}

    async def _oturum_sinir(db: AsyncSession, x: EgitimKurslari, ek: int) -> None:
        sayi = int((await db.execute(select(func.count(EgitimOturumlari.id)).where(EgitimOturumlari.kurs_id == x.id))).scalar() or 0)
        if sayi + ek > s.EN_COK_OTURUM:
            raise _hata(409, "oturum_siniri", sinir=s.EN_COK_OTURUM)

    def _oturum_araligi(g: Dict[str, Any]) -> tuple:
        bas = s.zaman_coz(g.get("baslangic"), "baslangic")
        bit = s.zaman_coz(g.get("bitis"), "bitis")
        if bit <= bas:
            raise s.EgitimHatasi("bitis_once", "bitis")
        if bit - bas > timedelta(hours=12):
            raise s.EgitimHatasi("sure_uzun", "bitis")
        return bas, bit

    @router.post("/{kid}/oturumlar")
    async def oturum_ekle(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        await _oturum_sinir(db, x, 1)
        try:
            bas, bit = _oturum_araligi(govde)
            konu = s.metin(govde.get("konu"), "konu", 160) or None
        except s.TemelHata as h:
            raise _e_hatasi(h)
        o = EgitimOturumlari(kurs_id=x.id, baslangic=bas, bitis=bit, konu=konu, durum="planli", yoklama_surumu=1,
                             created_at=s.simdi())
        db.add(o)
        await db.commit()
        await db.refresh(o)
        return _oturum_sozlugu(o)

    @router.post("/{kid}/oturumlar/uret")
    async def oturum_uret(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        """Tekrarlayan program: `{bas_tarih, bit_tarih, gunler: [0..6] (0 = Pazartesi), saat: "19:00", sure_dk, konu?}`."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        try:
            bas_t = s.tarih_duzelt(govde.get("bas_tarih"), "bas_tarih", bos_olabilir=False)
            bit_t = s.tarih_duzelt(govde.get("bit_tarih"), "bit_tarih", bos_olabilir=False)
            sure = int(s.tam_sayi(govde.get("sure_dk"), "sure_dk", 10, 720))
            araliklar = s.oturumlari_uret(bas_t, bit_t, govde.get("gunler"), govde.get("saat"), sure, x.saat_dilimi)
            konu = s.metin(govde.get("konu"), "konu", 160) or None
        except s.TemelHata as h:
            raise _e_hatasi(h)
        if not araliklar:
            raise _hata(400, "oturum_yok", alan="gunler")
        await _oturum_sinir(db, x, len(araliklar))
        mevcut = {s.utc(o.baslangic) for o in await k.oturumlar(db, x.id)}
        eklenen = 0
        for bas, bit in araliklar:
            if bas in mevcut:
                continue
            db.add(EgitimOturumlari(kurs_id=x.id, baslangic=bas, bitis=bit, konu=konu, durum="planli", yoklama_surumu=1,
                                    created_at=s.simdi()))
            eklenen += 1
        # Kursun tarih aralığı boşsa programdan doldur (sayfada ve saklama süresinde kullanılıyor).
        if not x.baslangic_tarihi:
            x.baslangic_tarihi = bas_t
        if not x.bitis_tarihi or x.bitis_tarihi < bit_t:
            x.bitis_tarihi = bit_t
        await db.commit()
        return {"eklenen": eklenen, "atlanan": len(araliklar) - eklenen}

    @router.put("/{kid}/oturumlar/{oid}")
    async def oturum_guncelle(kid: int, oid: int, request: Request, govde: Dict[str, Any] = Body(...),
                              db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        o = await _oturum(db, x, oid)
        try:
            if "baslangic" in govde or "bitis" in govde:
                o.baslangic, o.bitis = _oturum_araligi({"baslangic": govde.get("baslangic", s.iso(o.baslangic)),
                                                        "bitis": govde.get("bitis", s.iso(o.bitis))})
                o.hatirlatma_at = None
            if "konu" in govde:
                o.konu = s.metin(govde.get("konu"), "konu", 160) or None
            if "durum" in govde:
                o.durum = s.secim(govde.get("durum"), ("planli", "iptal"), "durum")
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        await db.commit()
        await db.refresh(o)
        return _oturum_sozlugu(o)

    @router.delete("/{kid}/oturumlar/{oid}")
    async def oturum_sil(kid: int, oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request), yonetim=True)
        o = await _oturum(db, x, oid)
        for y in (await db.execute(select(EgitimYoklama).where(EgitimYoklama.oturum_id == o.id))).scalars().all():
            await db.delete(y)
        await db.delete(o)
        await db.commit()
        return {"ok": True}

    def _yoklama_bilgisi(o: EgitimOturumlari) -> Dict[str, Any]:
        jeton = s.oturum_jetonu(o.id, int(o.yoklama_surumu or 1))
        bas, bit = s.yoklama_penceresi(o)
        return {"adres": s.yoklama_adresi(jeton), "kod": s.oturum_kodu(o.id, int(o.yoklama_surumu or 1)),
                "acik": s.yoklama_acik_mi(o), "pencere_bas": s.iso(bas), "pencere_bit": s.iso(bit)}

    @router.get("/{kid}/oturumlar/{oid}/yoklama")
    async def yoklama_listesi(kid: int, oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam)
        o = await _oturum(db, x, oid)
        ogrenciler = (await db.execute(select(EgitimOgrencileri).where(
            EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False))
            .order_by(EgitimOgrencileri.ad, EgitimOgrencileri.id))).scalars().all()
        kayitlar = {y.ogrenci_id: y for y in (await db.execute(select(EgitimYoklama).where(EgitimYoklama.oturum_id == o.id))).scalars().all()}
        return {
            "oturum": _oturum_sozlugu(o), "yoklama": _yoklama_bilgisi(o), "kurs": {"id": x.id, "ad": x.ad, "saat_dilimi": x.saat_dilimi},
            "items": [{"id": g.id, "ad": g.ad or "—", "kod": g.kod, "durum": kayitlar[g.id].durum if g.id in kayitlar else None,
                       "kaynak": kayitlar[g.id].kaynak if g.id in kayitlar else None,
                       "zaman": s.iso(kayitlar[g.id].zaman) if g.id in kayitlar else None} for g in ogrenciler],
        }

    @router.put("/{kid}/oturumlar/{oid}/yoklama/{ogid}")
    async def yoklama_duzelt(kid: int, oid: int, ogid: int, request: Request, arka: BackgroundTasks,
                             govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        """Elle düzeltme: `{"durum": "var"|"gec"|"yok"|"izinli"|null}` (null = kaydı sil)."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        o = await _oturum(db, x, oid)
        g = await _ogrenci(db, x, ogid)
        if g.anonim:
            raise _hata(404, "bulunamadi")
        durum = govde.get("durum")
        if durum is None:
            y = (await db.execute(select(EgitimYoklama).where(EgitimYoklama.oturum_id == o.id,
                                                              EgitimYoklama.ogrenci_id == g.id))).scalars().first()
            if y is not None:
                await db.delete(y)
        else:
            if durum not in s.YOKLAMA_DURUMLARI:
                raise _hata(400, "secim_gecersiz", alan="durum")
            await k.yoklama_yaz(db, x, o, g, durum, "elle", kapsam.kisi, ust_yaz=True)
        await db.flush()
        uyarilacak = await k.devamsizlik_denetle(db, x)
        await db.commit()
        if uyarilacak:
            arka.add_task(k.devamsizlik_epostalari, uyarilacak)
        return {"ok": True, "durum": durum}

    @router.post("/{kid}/oturumlar/{oid}/yoklama-kapat")
    async def yoklama_kapat(kid: int, oid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Kaydı olmayan aktif öğrencileri "yok" işaretler (ders bitince)."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        o = await _oturum(db, x, oid)
        var = {i for (i,) in (await db.execute(select(EgitimYoklama.ogrenci_id).where(EgitimYoklama.oturum_id == o.id))).all()}
        n = 0
        for g in (await db.execute(select(EgitimOgrencileri).where(
                EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False)))).scalars().all():
            if g.id not in var:
                db.add(EgitimYoklama(kurs_id=x.id, oturum_id=o.id, ogrenci_id=g.id, durum="yok", kaynak="elle",
                                     zaman=s.simdi(), yapan=kapsam.kisi[:254] or None))
                n += 1
        await db.flush()
        uyarilacak = await k.devamsizlik_denetle(db, x)
        await db.commit()
        if uyarilacak:
            arka.add_task(k.devamsizlik_epostalari, uyarilacak)
        return {"ok": True, "yok": n}

    @router.get("/{kid}/oturumlar/{oid}/qr")
    async def oturum_qr(kid: int, oid: int, request: Request, bicim: str = Query("svg"), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        _hiz(_gorsel_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        o = await _oturum(db, x, oid)
        g = _qr_gorsel(_yoklama_bilgisi(o)["adres"], bicim)
        return Response(g.veri, media_type=g.tur, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @router.post("/{kid}/oturumlar/{oid}/qr-yenile")
    async def oturum_qr_yenile(kid: int, oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """QR bağlantısı ve kısa kod değişir; eskisi (ör. sınıf dışına paylaşılan) geçersiz."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        o = await _oturum(db, x, oid)
        o.yoklama_surumu = int(o.yoklama_surumu or 1) + 1
        await db.commit()
        await db.refresh(o)
        return _yoklama_bilgisi(o)

    @router.get("/{kid}/oturumlar/{oid}/okutucu")
    async def okutucu_ozeti(kid: int, oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Panel okutucusunun açılış bilgisi (etkinlik okutucusuyla aynı biçim)."""
        x = await _kurs(db, kid, kapsam_al(request))
        o = await _oturum(db, x, oid)
        baslik = f"{x.ad} — {o.konu}" if o.konu else x.ad
        return {"baslik": baslik, "baslangic": s.iso(o.baslangic), "bitis": s.iso(o.bitis), "saat_dilimi": x.saat_dilimi,
                "sayac": await k.sayac(db, x, o)}

    @router.get("/{kid}/oturumlar/{oid}/sayac")
    async def oturum_sayac(kid: int, oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request))
        return await k.sayac(db, x, await _oturum(db, x, oid))

    @router.post("/{kid}/oturumlar/{oid}/okut")
    async def oturum_okut(kid: int, oid: int, request: Request, govde: Dict[str, Any] = Body(...),
                          db: AsyncSession = Depends(get_db)):
        """Eğitmen öğrencinin QR'ını / kodunu okutur (idempotent: ikinci okutma "zaten_girdi")."""
        kapsam = kapsam_al(request)
        _hiz(_okut_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        o = await _oturum(db, x, oid)
        return await k.okut(db, x, o, govde.get("kod"), kapsam.kisi)

    # --- Öğrenciler ---
    @router.get("/{kid}/ogrenciler")
    async def ogrenci_listesi(kid: int, request: Request, durum: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam)
        sorgu = select(EgitimOgrencileri).where(EgitimOgrencileri.kurs_id == x.id)
        if durum in s.OGRENCI_DURUMLARI:
            sorgu = sorgu.where(EgitimOgrencileri.durum == durum)
        if not kapsam.yonetim:
            sorgu = sorgu.where(EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False))
        kayitlar = (await db.execute(sorgu.order_by(EgitimOgrencileri.id).limit(3000))).scalars().all()
        ist = await k.istatistik(db, x, kayitlar)
        return {"items": [_ogrenci_sozlugu(o, kapsam.yonetim, ist.get(o.id)) for o in kayitlar], "toplam": len(kayitlar),
                "kapasite": x.kapasite}

    @router.post("/{kid}/ogrenciler")
    async def ogrenci_ekle(kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                           db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        try:
            g = _kayit_girdisi(x, govde, "elle")
            g.notlar = s.metin(govde.get("notlar"), "notlar", 1000, cok_satir=True) or None
            if govde.get("durum") == "bekleme":
                g.durum = "bekleme"
            o = await k.kayit_olustur(db, x, g)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        if govde.get("bildir") is not False:
            arka.add_task(k.ogrenci_epostasi, o.id, "kayit" if o.durum == "aktif" else "bekleme")
        return _ogrenci_sozlugu(o, True)

    @router.post("/{kid}/ogrenciler/csv")
    async def ogrenci_csv(kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                          db: AsyncSession = Depends(get_db)):
        """`{"csv": "ad,eposta,telefon,veli_ad,veli_eposta,veli_telefon,cocuk\\n…", "bildir": false}` — en çok 500 satır."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        try:
            satirlar = s.csv_coz(govde.get("csv"))
        except s.TemelHata as h:
            raise _e_hatasi(h)
        sayac_ = {"aktif": 0, "bekleme": 0, "atlanan": 0}
        hatalar: List[Dict[str, Any]] = []
        eklenenler: List[tuple] = []
        for i, satir in enumerate(satirlar, start=2):
            try:
                g = _kayit_girdisi(x, satir, "csv")
                o = await k.kayit_olustur(db, x, g)
            except s.TemelHata as h:
                if h.kod == "zaten_kayitli":
                    sayac_["atlanan"] += 1
                    continue
                hatalar.append({"satir": i, "kod": h.kod, "alan": h.alan})
                if h.kod == "ogrenci_siniri":
                    break
                continue
            sayac_[o.durum] = sayac_.get(o.durum, 0) + 1
            eklenenler.append((o.id, o.durum))
        if govde.get("bildir") is True:
            for oid, durum in eklenenler:
                arka.add_task(k.ogrenci_epostasi, oid, "kayit" if durum == "aktif" else "bekleme")
        return {**sayac_, "hatalar": hatalar[:50], "hata_sayisi": len(hatalar)}

    @router.get("/{kid}/ogrenciler.csv")
    async def ogrenci_csv_indir(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_gorsel_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        kayitlar = (await db.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.kurs_id == x.id)
                                     .order_by(EgitimOgrencileri.id))).scalars().all()
        ist = await k.istatistik(db, x, kayitlar)
        tampon = io.StringIO()
        yaz = csv.writer(tampon)
        yaz.writerow(["kod", "ad", "eposta", "telefon", "cocuk", "veli_ad", "veli_eposta", "veli_telefon", "durum", "kaynak",
                      "kayit_tarihi", "ilerleme", "quiz_ortalama", "yoklama", "devamsizlik", "sertifika"])
        for o in kayitlar:
            i = ist.get(o.id, {})
            yaz.writerow([s.csv_hucre(v) for v in (
                o.kod, o.ad or "", o.eposta or "", o.telefon or "", "evet" if o.cocuk else "", o.veli_ad or "",
                o.veli_eposta or "", o.veli_telefon or "", o.durum, o.kaynak, s.iso(o.created_at),
                i.get("ilerleme", ""), "" if i.get("quiz_ortalama") is None else i.get("quiz_ortalama"),
                "" if i.get("yoklama") is None else i.get("yoklama"), i.get("devamsizlik", ""), i.get("sertifika") or "")])
        return Response("﻿" + tampon.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": icerik_konumu(f"{x.slug}-ogrenciler.csv"), "Cache-Control": "no-store"})

    @router.put("/{kid}/ogrenciler/{ogid}")
    async def ogrenci_guncelle(kid: int, ogid: int, request: Request, arka: BackgroundTasks,
                               govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        o = await _ogrenci(db, x, ogid)
        if o.anonim:
            raise _hata(409, "anonim")
        alinan: List[int] = []
        try:
            if "ad" in govde:
                o.ad = s.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "eposta" in govde:
                o.eposta = s.eposta_duzelt(govde.get("eposta"), "eposta", zorunlu=not o.cocuk) or None
            if "telefon" in govde:
                o.telefon = s.telefon_duzelt(govde.get("telefon"), "telefon")
            if "cocuk" in govde:
                o.cocuk = s.bool_duzelt(govde.get("cocuk"), "cocuk")
                if o.cocuk:
                    o.pazarlama_izni_at, o.pazarlama_metin_surumu = None, None
            for alan in ("veli_ad",):
                if alan in govde:
                    setattr(o, alan, s.metin(govde.get(alan), alan, 120) or None)
            if "veli_eposta" in govde:
                o.veli_eposta = s.eposta_duzelt(govde.get("veli_eposta"), "veli_eposta", zorunlu=False) or None
            if "veli_telefon" in govde:
                o.veli_telefon = s.telefon_duzelt(govde.get("veli_telefon"), "veli_telefon")
            if o.cocuk and not (o.veli_ad and o.veli_eposta):
                raise s.EgitimHatasi("zorunlu", "veli_eposta" if o.veli_ad else "veli_ad")
            if not o.cocuk:
                o.veli_ad = o.veli_eposta = o.veli_telefon = None
                if not o.eposta:
                    raise s.EgitimHatasi("zorunlu", "eposta")
            if "notlar" in govde:
                o.notlar = s.metin(govde.get("notlar"), "notlar", 1000, cok_satir=True) or None
            if "durum" in govde:
                alinan = await k.durum_degistir(db, x, o, s.secim(govde.get("durum"), s.OGRENCI_DURUMLARI, "durum"))
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "dolu")
        await db.refresh(o)
        if alinan:
            arka.add_task(k.ogrenci_epostalari, alinan, "yer")
        return _ogrenci_sozlugu(o, True)

    @router.delete("/{kid}/ogrenciler/{ogid}")
    async def ogrenci_sil(kid: int, ogid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """KVKK silme talebi: öğrencinin bütün eğitim kayıtları kalıcı silinir."""
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        o = await _ogrenci(db, x, ogid)
        alinan = await k.ogrenci_sil(db, x, o)
        if alinan:
            arka.add_task(k.ogrenci_epostalari, alinan, "yer")
        return {"ok": True}

    @router.post("/{kid}/ogrenciler/{ogid}/baglanti")
    async def ogrenci_baglantisi(kid: int, ogid: int, request: Request, arka: BackgroundTasks,
                                 govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        """Öğrenci bağlantısı: `{"yenile": true}` eskilerin hepsini geçersiz kılar; `{"gonder": true}` e-postayla yollar."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        o = await _ogrenci(db, x, ogid)
        if o.anonim:
            raise _hata(409, "anonim")
        if govde.get("yenile") is True:
            o.portal_surumu = int(o.portal_surumu or 1) + 1
            await db.commit()
            await db.refresh(o)
        if govde.get("gonder") is True:
            arka.add_task(k.ogrenci_epostasi, o.id, "portal")
        return {"adres": s.portal_adresi(s.ogrenci_jetonu(o.id, int(o.portal_surumu or 1), o.kod)),
                "surum": int(o.portal_surumu or 1), "gonderildi": govde.get("gonder") is True}

    @router.get("/{kid}/ilerleme")
    async def ilerleme(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam)
        kayitlar = (await db.execute(select(EgitimOgrencileri).where(
            EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False))
            .order_by(EgitimOgrencileri.ad, EgitimOgrencileri.id))).scalars().all()
        ist = await k.istatistik(db, x, kayitlar)
        return {"items": [{"id": o.id, "ad": o.ad or "—", "kod": o.kod, **ist.get(o.id, {})} for o in kayitlar],
                "kosullar": {"ilerleme": int(x.kosul_ilerleme), "quiz": int(x.kosul_quiz), "yoklama": int(x.kosul_yoklama)}}

    # --- Dersler (LMS) ---
    @router.get("/{kid}/dersler")
    async def ders_listesi(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request))
        liste_ = await k.dersler(db, x.id)
        ekler = await _dosyalar(db, [d.id for d in liste_])
        return {"items": [_ders_sozlugu(d, ekler.get(d.id)) for d in liste_]}

    def _ders_uygula(d: EgitimDersleri, g: Dict[str, Any], yeni: bool) -> None:
        if "baslik" in g or yeni:
            d.baslik = s.metin(g.get("baslik"), "baslik", 160, zorunlu=True)
        if "bolum" in g:
            d.bolum = s.metin(g.get("bolum"), "bolum", 120) or None
        if "icerik" in g:
            d.icerik = s.metin(g.get("icerik"), "icerik", 50000, cok_satir=True) or None
        if "video_url" in g:
            d.video_url = s.https_duzelt(g.get("video_url"), "video_url")
        if "sure_dk" in g:
            d.sure_dk = s.tam_sayi(g.get("sure_dk"), "sure_dk", 1, 1000, bos_olabilir=True)
        if "yayinda" in g:
            d.yayinda = s.bool_duzelt(g.get("yayinda"), "yayinda")
        if "sira" in g:
            d.sira = int(s.tam_sayi(g.get("sira"), "sira", 0, 10000))

    @router.post("/{kid}/dersler")
    async def ders_ekle(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        mevcut = await k.dersler(db, x.id)
        if len(mevcut) >= s.EN_COK_DERS:
            raise _hata(409, "ders_siniri", sinir=s.EN_COK_DERS)
        d = EgitimDersleri(kurs_id=x.id, sira=(max([m.sira for m in mevcut], default=-1) + 1), yayinda=True,
                           created_at=s.simdi())
        try:
            _ders_uygula(d, govde, yeni=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        db.add(d)
        await db.commit()
        await db.refresh(d)
        return _ders_sozlugu(d)

    @router.put("/{kid}/dersler-sira")
    async def ders_sirasi(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        """`{"sira": [ders kimlikleri]}` — verilen sırayla 0..n."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        sira = govde.get("sira")
        if not isinstance(sira, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in sira):
            raise _hata(400, "sira_gecersiz", alan="sira")
        dersler_ = {d.id: d for d in await k.dersler(db, x.id)}
        for i, did in enumerate(sira):
            if did in dersler_:
                dersler_[did].sira = i
        await db.commit()
        return {"ok": True}

    @router.put("/{kid}/dersler/{did}")
    async def ders_guncelle(kid: int, did: int, request: Request, govde: Dict[str, Any] = Body(...),
                            db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        d = await _ders(db, x, did)
        try:
            _ders_uygula(d, govde, yeni=False)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        await db.commit()
        await db.refresh(d)
        return _ders_sozlugu(d, (await _dosyalar(db, [d.id])).get(d.id))

    @router.delete("/{kid}/dersler/{did}")
    async def ders_sil(kid: int, did: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request), yonetim=True)
        d = await _ders(db, x, did)
        await k.dosyalari_sil(db, (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.ders_id == d.id))).scalars().all())
        for i in (await db.execute(select(EgitimIlerleme).where(EgitimIlerleme.ders_id == d.id))).scalars().all():
            await db.delete(i)
        await db.delete(d)
        await db.commit()
        return {"ok": True}

    @router.post("/{kid}/dersler/{did}/dosyalar")
    async def ders_dosyasi(kid: int, did: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_gorsel_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        d = await _ders(db, x, did)
        if int((await db.execute(select(func.count(EgitimDosyalari.id)).where(EgitimDosyalari.ders_id == d.id))).scalar() or 0) >= 20:
            raise _hata(409, "dosya_siniri", sinir=20)
        veri = await _dosya_oku(dosya, db)
        try:
            kayit = await k.dosya_kaydet(db, x, ad_ham=dosya.filename or "dosya", veri=veri, yukleyen=kapsam.kisi, ders_id=d.id)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        await db.commit()
        return _dosya_sozlugu(kayit)

    @router.get("/{kid}/dosyalar/{fid}")
    async def dosya_indir(kid: int, fid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_gorsel_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        d = (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.id == fid, EgitimDosyalari.kurs_id == x.id))).scalars().first()
        if d is None:
            raise _hata(404, "bulunamadi")
        return await _dosya_yaniti(db, d)

    @router.delete("/{kid}/dosyalar/{fid}")
    async def dosya_sil(kid: int, fid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request), yonetim=True)
        d = (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.id == fid, EgitimDosyalari.kurs_id == x.id,
                                                            EgitimDosyalari.ders_id.isnot(None)))).scalars().first()
        if d is None:
            raise _hata(404, "bulunamadi")
        await k.dosyalari_sil(db, [d])
        await db.commit()
        return {"ok": True}

    # --- Quiz / ödev ---
    def _quiz_uygula(q: EgitimQuizleri, g: Dict[str, Any], yeni: bool, ders_idleri: set) -> None:
        if "tur" in g and yeni:
            q.tur = s.secim(g.get("tur"), s.QUIZ_TURLERI, "tur")
        if "baslik" in g or yeni:
            q.baslik = s.metin(g.get("baslik"), "baslik", 160, zorunlu=True)
        if "aciklama" in g:
            q.aciklama = s.metin(g.get("aciklama"), "aciklama", 5000, cok_satir=True) or None
        if "ders_id" in g:
            did = g.get("ders_id")
            if did is not None and (isinstance(did, bool) or did not in ders_idleri):
                raise s.EgitimHatasi("ders_yok", "ders_id", durum=404)
            q.ders_id = did
        if "sorular" in g:
            q.sorular = s.json_yaz(s.sorular_duzelt(g.get("sorular"))) if g.get("sorular") else None
        if "sure_dk" in g:
            q.sure_dk = s.tam_sayi(g.get("sure_dk"), "sure_dk", 1, 600, bos_olabilir=True)
        if "gecme_puani" in g:
            q.gecme_puani = int(s.tam_sayi(g.get("gecme_puani"), "gecme_puani", 0, 100))
        if "deneme_hakki" in g:
            q.deneme_hakki = int(s.tam_sayi(g.get("deneme_hakki"), "deneme_hakki", 1, 20))
        if "son_tarih" in g:
            q.son_tarih = s.zaman_coz(g.get("son_tarih"), "son_tarih", bos_olabilir=True)
        if "ai_uretildi" in g:
            q.ai_uretildi = g.get("ai_uretildi") is True
        if "yayinda" in g:
            q.yayinda = s.bool_duzelt(g.get("yayinda"), "yayinda")
        if q.yayinda and q.tur == "quiz" and not (s.json_yukle(q.sorular, []) or []):
            raise s.EgitimHatasi("soru_yok", "sorular", durum=409)

    @router.get("/{kid}/quizler")
    async def quiz_listesi(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request))
        liste_ = await k.quizler(db, x.id)
        bekleyen: Dict[int, int] = {}
        for qid, n in (await db.execute(select(EgitimTeslimleri.quiz_id, func.count(EgitimTeslimleri.id)).where(
                EgitimTeslimleri.kurs_id == x.id, EgitimTeslimleri.notlandi_at.is_(None)).group_by(EgitimTeslimleri.quiz_id))).all():
            bekleyen[int(qid)] = int(n)
        return {"items": [{**_quiz_sozlugu(q), "notlanmayan": bekleyen.get(q.id, 0)} for q in liste_]}

    @router.post("/{kid}/quizler")
    async def quiz_ekle(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        mevcut = await k.quizler(db, x.id)
        if len(mevcut) >= s.EN_COK_QUIZ:
            raise _hata(409, "quiz_siniri", sinir=s.EN_COK_QUIZ)
        q = EgitimQuizleri(kurs_id=x.id, tur="quiz", gecme_puani=60, deneme_hakki=1, yayinda=False,
                           sira=len(mevcut), ai_uretildi=False, created_at=s.simdi())
        try:
            _quiz_uygula(q, govde, True, {d.id for d in await k.dersler(db, x.id)})
        except s.TemelHata as h:
            raise _e_hatasi(h)
        db.add(q)
        await db.commit()
        await db.refresh(q)
        return _quiz_sozlugu(q)

    @router.post("/{kid}/quizler/ai")
    async def quiz_ai(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        """Dersin içeriğinden soru ÖNERİSİ (kaydedilmez — kullanıcı gözden geçirip quize ekler).
        Sağlayıcı anahtarı yoksa 503 `ai_kapali` (sayaç düşmeden)."""
        from services import yapay_zeka as ai

        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        _hiz(_ai_hizi, kapsam.kisi)
        if not s.ai_hazir():
            raise _hata(503, "ai_kapali")
        did = govde.get("ders_id")
        if isinstance(did, bool) or not isinstance(did, int):
            raise _hata(400, "ders_yok", alan="ders_id")
        d = await _ders(db, x, did)
        icerik = (d.icerik or "").strip()
        if len(icerik) < 40:
            raise _hata(409, "icerik_kisa", alan="ders_id")
        try:
            sayi = int(s.tam_sayi(govde.get("sayi", 5), "sayi", 1, 10))
            turler = govde.get("turler") or list(s.SORU_TURLERI)
            if not isinstance(turler, list) or not turler or any(t not in s.SORU_TURLERI for t in turler):
                raise s.EgitimHatasi("soru_turu", "turler")
            hak = await k.ai_hak_ayir(db, x.hesap_email, kapsam.kisi)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        try:
            yanit = await ai.metin_uret(s.ai_mesajlari(dil=x.dil, ders_baslik=d.baslik, icerik=icerik, sayi=sayi, turler=turler),
                                        model=ai.varsayilan_model(), max_tokens=2500, temperature=0.4, amac="egitim_quiz")
        except ai.YapayZekaHatasi as h:
            await k.ai_hak_iade(db, hak)
            raise _hata(h.durum, h.kod)
        try:
            sorular = s.ai_yanitini_coz(yanit.icerik, sayi)
        except s.TemelHata:
            if not yanit.sahte:
                await k.ai_hak_iade(db, hak)
                raise _hata(502, "ai_bicim")
            # Test ortamı (ENVIRONMENT=test): sahte model JSON vermiyor → dersin cümlelerinden belirlenimci soru.
            sorular = s.sahte_sorular(d.baslik, icerik, sayi, turler)
        await ai.token_ekle(db, s.AI_KAPSAM, yanit)
        return {"sorular": sorular, "ai": await k.ai_ozeti(db, x.hesap_email)}

    @router.put("/{kid}/quizler/{qid}")
    async def quiz_guncelle(kid: int, qid: int, request: Request, govde: Dict[str, Any] = Body(...),
                            db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        q = await _quiz(db, x, qid)
        try:
            _quiz_uygula(q, govde, False, {d.id for d in await k.dersler(db, x.id)})
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        await db.commit()
        await db.refresh(q)
        return _quiz_sozlugu(q)

    @router.delete("/{kid}/quizler/{qid}")
    async def quiz_sil(kid: int, qid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request), yonetim=True)
        q = await _quiz(db, x, qid)
        teslimler = [t.id for t in (await db.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.quiz_id == q.id))).scalars().all()]
        if teslimler:
            await k.dosyalari_sil(db, (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.teslim_id.in_(teslimler)))).scalars().all())
        for model in (EgitimDenemeleri, EgitimTeslimleri):
            for satir in (await db.execute(select(model).where(model.quiz_id == q.id))).scalars().all():
                await db.delete(satir)
        await db.delete(q)
        await db.commit()
        return {"ok": True}

    @router.get("/{kid}/quizler/{qid}/sonuclar")
    async def quiz_sonuclari(kid: int, qid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam)
        q = await _quiz(db, x, qid)
        adlar = {o.id: (o.ad or "—", o.kod) for o in (await db.execute(select(EgitimOgrencileri).where(
            EgitimOgrencileri.kurs_id == x.id))).scalars().all()}
        if q.tur == "odev":
            teslimler = (await db.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.quiz_id == q.id)
                                          .order_by(EgitimTeslimleri.teslim_at.desc()))).scalars().all()
            dosyalar = {}
            if teslimler:
                for d in (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.teslim_id.in_([t.id for t in teslimler])))).scalars().all():
                    dosyalar.setdefault(d.teslim_id, []).append(_dosya_sozlugu(d))
            return {"tur": "odev", "items": [{
                "id": t.id, "ogrenci_id": t.ogrenci_id, "ad": adlar.get(t.ogrenci_id, ("—", ""))[0], "metin": t.metin or "",
                "teslim_at": s.iso(t.teslim_at), "gec": bool(q.son_tarih and s.utc(t.teslim_at) > s.utc(q.son_tarih)),
                "puan": t.puan, "geri_bildirim": t.geri_bildirim or "", "notlandi_at": s.iso(t.notlandi_at),
                "dosyalar": dosyalar.get(t.id, [])} for t in teslimler]}
        denemeler = (await db.execute(select(EgitimDenemeleri).where(EgitimDenemeleri.quiz_id == q.id,
                                                                     EgitimDenemeleri.durum != "devam")
                                       .order_by(EgitimDenemeleri.id))).scalars().all()
        en_iyi: Dict[int, EgitimDenemeleri] = {}
        sayi: Dict[int, int] = {}
        for dn in denemeler:
            sayi[dn.ogrenci_id] = sayi.get(dn.ogrenci_id, 0) + 1
            if dn.ogrenci_id not in en_iyi or int(dn.puan or 0) > int(en_iyi[dn.ogrenci_id].puan or 0):
                en_iyi[dn.ogrenci_id] = dn
        return {"tur": "quiz", "items": [{
            "ogrenci_id": oid, "ad": adlar.get(oid, ("—", ""))[0], "puan": int(dn.puan or 0), "dogru": int(dn.dogru or 0),
            "toplam": int(dn.toplam or 0), "deneme": sayi.get(oid, 0), "durum": dn.durum, "gecti": int(dn.puan or 0) >= int(q.gecme_puani),
            "gonderim_at": s.iso(dn.gonderim_at)} for oid, dn in en_iyi.items()]}

    @router.put("/{kid}/teslimler/{tid}")
    async def teslim_notla(kid: int, tid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                           db: AsyncSession = Depends(get_db)):
        """Eğitmen notu: `{"puan": 0..100 | null, "geri_bildirim": "...", "bildir": true}`."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam)
        t = (await db.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.id == tid, EgitimTeslimleri.kurs_id == x.id))).scalars().first()
        if t is None:
            raise _hata(404, "bulunamadi")
        try:
            t.puan = s.tam_sayi(govde.get("puan"), "puan", 0, 100, bos_olabilir=True)
            t.geri_bildirim = s.metin(govde.get("geri_bildirim"), "geri_bildirim", 5000, cok_satir=True) or None
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        t.notlandi_at, t.notlayan = s.simdi(), kapsam.kisi[:254] or None
        await db.commit()
        if govde.get("bildir") is not False:
            arka.add_task(k.not_epostasi, t.id)
        return {"ok": True, "puan": t.puan, "notlandi_at": s.iso(t.notlandi_at)}

    # --- Sertifikalar ---
    @router.get("/{kid}/sertifikalar")
    async def sertifika_listesi(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        adlar = {o.id: o.ad for o in (await db.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.kurs_id == x.id))).scalars().all()}
        kayitlar = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.kurs_id == x.id)
                                     .order_by(EgitimSertifikalari.id.desc()))).scalars().all()
        return {"items": [_sertifika_sozlugu(c, adlar.get(c.ogrenci_id)) for c in kayitlar]}

    @router.post("/{kid}/sertifikalar")
    async def sertifika_ver(kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                            db: AsyncSession = Depends(get_db)):
        """`{"ogrenci_id", "zorla"?}` — koşul sağlanmadıysa 409 `kosul_saglanmadi` (+ koşul ayrıntısı)."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        ogid = govde.get("ogrenci_id")
        if isinstance(ogid, bool) or not isinstance(ogid, int):
            raise _hata(400, "ogrenci_yok", alan="ogrenci_id")
        o = await _ogrenci(db, x, ogid)
        try:
            sert, yeni = await k.sertifika_ver(db, x, o, kaynak="elle", zorla=govde.get("zorla") is True)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
        await db.commit()
        await db.refresh(sert)
        if govde.get("bildir") is not False:
            arka.add_task(k.sertifika_epostasi, sert.id)
        return {**_sertifika_sozlugu(sert, o.ad), "yeni": yeni}

    @router.post("/{kid}/sertifikalar/toplu")
    async def sertifika_toplu(kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(default={}),
                              db: AsyncSession = Depends(get_db)):
        """Koşulu sağlayan bütün aktif öğrencilere (sertifikası olmayan) sertifika."""
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        if not x.sertifika_aktif:
            raise _hata(409, "sertifika_kapali")
        ogrenciler = (await db.execute(select(EgitimOgrencileri).where(
            EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False)))).scalars().all()
        ist = await k.istatistik(db, x, ogrenciler)
        yeni_idler: List[int] = []
        for o in ogrenciler:
            if not ist.get(o.id, {}).get("uygun"):
                continue
            sert, yeni = await k.sertifika_ver(db, x, o, kaynak="toplu", ist=ist.get(o.id))
            if yeni:
                yeni_idler.append(sert.id)
        await db.commit()
        if govde.get("bildir") is not False:
            for sid in yeni_idler:
                arka.add_task(k.sertifika_epostasi, sid)
        return {"verilen": len(yeni_idler), "uygun_olmayan": sum(1 for o in ogrenciler if not ist.get(o.id, {}).get("uygun"))}

    @router.delete("/{kid}/sertifikalar/{sid}")
    async def sertifika_iptal(kid: int, sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request), yonetim=True)
        c = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.id == sid,
                                                                EgitimSertifikalari.kurs_id == x.id))).scalars().first()
        if c is None:
            raise _hata(404, "bulunamadi")
        c.iptal_at = s.simdi()
        await db.commit()
        return {"ok": True}

    @router.get("/{kid}/sertifikalar/{sid}/pdf")
    async def sertifika_pdf_panel(kid: int, sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_gorsel_hizi, kapsam.kisi)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        c = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.id == sid,
                                                                EgitimSertifikalari.kurs_id == x.id))).scalars().first()
        o = await _ogrenci(db, x, c.ogrenci_id) if c is not None else None
        if c is None or o is None or o.anonim:
            raise _hata(404, "bulunamadi")
        return await _sertifika_pdf_yaniti(db, x, o, c)

    # --- Duyurular (bilgilendirme e-postası; pazarlama değil) ---
    @router.get("/{kid}/duyurular")
    async def duyuru_listesi(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        x = await _kurs(db, kid, kapsam_al(request), yonetim=True)
        kayitlar = (await db.execute(select(EgitimDuyurulari).where(EgitimDuyurulari.kurs_id == x.id)
                                     .order_by(EgitimDuyurulari.id.desc()).limit(100))).scalars().all()
        return {"items": [{"id": d.id, "konu": d.konu, "metin": d.metin, "alici": d.alici, "created_at": s.iso(d.created_at)}
                          for d in kayitlar]}

    @router.post("/{kid}/duyuru")
    async def duyuru(kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                     db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        x = await _kurs(db, kid, kapsam, yonetim=True)
        try:
            konu = s.metin(govde.get("konu"), "konu", 150, zorunlu=True)
            metin_ = s.metin(govde.get("metin"), "metin", 5000, zorunlu=True, cok_satir=True)
        except s.TemelHata as h:
            raise _e_hatasi(h)
        _hiz(_duyuru_hizi, f"egitim-{x.id}")
        alici = await k.aktif_sayisi(db, x.id)
        if not alici:
            raise _hata(409, "alici_yok")
        d = EgitimDuyurulari(kurs_id=x.id, konu=konu, metin=metin_, alici=alici, gonderen=kapsam.kisi[:254] or None,
                             created_at=s.simdi())
        db.add(d)
        await db.commit()
        await db.refresh(d)
        arka.add_task(k.duyuru_gonder, d.id)
        return {"ok": True, "alici": alici, "id": d.id}


async def _sertifika_pdf_yaniti(db: AsyncSession, x: EgitimKurslari, o: EgitimOgrencileri, c: EgitimSertifikalari) -> Response:
    ayar = await k.hesap_ayarlari(db, x.hesap_email)
    tarih = None
    if x.baslangic_tarihi and x.bitis_tarihi:
        tarih = f"{s.tarih_yaz(x.baslangic_tarihi, x.dil)} – {s.tarih_yaz(x.bitis_tarihi, x.dil)}"
    pdf = s.sertifika_pdf(ad=o.ad or "—", kurs_adi=c.kurs_adi, kurum=(ayar.kurum_adi if ayar else None) or c.kurum_adi,
                          kod=c.kod, verilme=s.utc(c.verilme_at), sablon=x.sertifika_sablon, renk=x.renk, dil=x.dil,
                          saat=x.sertifika_saat, egitmenler=s.egitmen_adlari(x), imza_adi=ayar.imza_adi if ayar else None,
                          imza_unvan=ayar.imza_unvan if ayar else None, tarih_araligi=tarih)
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": icerik_konumu(f"sertifika-{s.sertifika_kodu_yaz(c.kod)}.pdf"), "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"})


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık: kurs sayfası ve kayıt
# ---------------------------------------------------------------------------
async def _yayinda_mi(db: AsyncSession, x: EgitimKurslari) -> bool:
    if x.hesap_email:
        from services import moduller as modul_servisi

        return await modul_servisi.modul_acik_mi(db, x.hesap_email, MODUL)
    return True


async def _acik_kurs(db: AsyncSession, slug: str) -> EgitimKurslari:
    """Slug'a göre: yok/taslak/arşiv → 404, sahibinin modülü kapalı → 410."""
    temiz = (slug or "").strip().lower()
    if not s.SLUG_DESENI.match(temiz):
        raise _hata(404, "kurs_yok")
    x = (await db.execute(select(EgitimKurslari).where(EgitimKurslari.slug == temiz))).scalars().first()
    if x is None or x.durum in ("taslak", "arsiv"):
        raise _hata(404, "kurs_yok")
    if not await _yayinda_mi(db, x):
        raise _hata(410, "kurs_pasif")
    return x


def _robots(x: EgitimKurslari) -> Dict[str, str]:
    return {} if x.arama_motoru else {"X-Robots-Tag": "noindex"}


def _kayit_durumu(x: EgitimKurslari, aktif: int) -> Dict[str, Any]:
    kalan = None if x.kapasite is None else max(0, int(x.kapasite) - aktif)
    acik = x.durum == "yayinda" and bool(x.kayit_acik)
    neden = None if acik else ("kurs_tamamlandi" if x.durum == "tamamlandi" else "kayit_kapali")
    return {"kayit_acik": acik, "kayit_neden": neden, "kalan": kalan, "dolu": kalan is not None and kalan <= 0,
            "bekleme_listesi": bool(x.bekleme_listesi)}


def _acik_kurs_ozeti(x: EgitimKurslari, oturumlar_: List[EgitimOturumlari], aktif: int) -> Dict[str, Any]:
    an = s.simdi()
    planli = [o for o in oturumlar_ if o.durum == "planli"]
    yaklasan = [o for o in planli if s.utc(o.bitis) > an][:12]
    from services import pazarlama_izni

    return {
        "slug": x.slug, "ad": x.ad, "ozet": x.ozet or "", "aciklama": x.aciklama or "", "renk": x.renk,
        "egitmenler": s.egitmen_adlari(x), "bicim": x.bicim, "mekan": x.mekan or "", "adres": x.adres or "",
        "saat_dilimi": x.saat_dilimi, "baslangic_tarihi": x.baslangic_tarihi.isoformat() if x.baslangic_tarihi else None,
        "bitis_tarihi": x.bitis_tarihi.isoformat() if x.bitis_tarihi else None, "kapasite": x.kapasite,
        "fiyat_metni": x.fiyat_metni or "", "durum": x.durum, "hedef_kitle": x.hedef_kitle, "telefon": x.telefon,
        "dil": x.dil, "kvkk_metni": x.kvkk_metni or "", "ders_sayisi": len(planli),
        "program": [{"baslangic": s.iso(o.baslangic), "bitis": s.iso(o.bitis), "konu": o.konu or ""} for o in yaklasan],
        "sertifika": bool(x.sertifika_aktif), "indekslenebilir": bool(x.arama_motoru), "ajans": x.hesap_email is None,
        "adres_url": s.kurs_adresi(x.slug), "pazarlama_metinleri": dict(pazarlama_izni.METINLER),
        **_kayit_durumu(x, aktif),
    }


async def _marka(db: AsyncSession, hesap: Optional[str], renk: Optional[str] = None) -> Dict[str, Any]:
    """Faz 4L: marka teması (kursun kendi rengi varsayılandan farklıysa o öncelikli)."""
    from services.marka import acik_marka, renk_ozel_mi

    return await acik_marka(db, hesap, sayfa_ozel=renk_ozel_mi(renk, "#2563eb") if renk is not None else False)


@acik_router.api_route("/kurs/{slug}", methods=["GET", "HEAD"])
async def acik_kurs(slug: str, db: AsyncSession = Depends(get_db)):
    x = await _acik_kurs(db, slug)
    return JSONResponse({**_acik_kurs_ozeti(x, await k.oturumlar(db, x.id), await k.aktif_sayisi(db, x.id)),
                         "marka": await _marka(db, x.hesap_email, x.renk)},
                        headers={**ACIK_BASLIKLAR, "Cache-Control": "no-cache", **_robots(x)})


@acik_router.get("/kurs/{slug}/ozet")
async def acik_kurs_ozet(slug: str, db: AsyncSession = Depends(get_db)):
    """Pages Function'ın paylaşım önizlemesi ve (yalnız "arama motorlarında görünsün" seçiliyse) Course JSON-LD'si."""
    x = await _acik_kurs(db, slug)
    veri: Dict[str, Any] = {"slug": x.slug, "baslik": x.ad, "aciklama": (x.ozet or (x.aciklama or "")[:300])[:300],
                            "dil": x.dil, "renk": x.renk, "indekslenebilir": bool(x.arama_motoru),
                            "adres_url": s.kurs_adresi(x.slug), "jsonld": None, "marka": await _marka(db, x.hesap_email, x.renk)}
    if x.arama_motoru:
        ayar = await k.hesap_ayarlari(db, x.hesap_email)
        saglayici = (ayar.kurum_adi if ayar else None) or ("By Mehmet KURU Dev" if x.hesap_email is None else None)
        jsonld: Dict[str, Any] = {"@context": "https://schema.org", "@type": "Course", "name": x.ad,
                                  "description": (x.ozet or (x.aciklama or "")[:300] or x.ad)[:300], "url": s.kurs_adresi(x.slug),
                                  "inLanguage": x.dil}
        if saglayici:
            jsonld["provider"] = {"@type": "Organization", "name": saglayici}
        veri["jsonld"] = jsonld
    return JSONResponse(veri, headers={"Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff"})


@acik_router.post("/kurs/{slug}/kayit")
async def acik_kayit(slug: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 16384)
    x = await _acik_kurs(db, slug)
    await _kalici_hiz((_kayit_hizi, _ziyaretci(request, x.id)), (_kurs_kayit_hizi, str(x.id)))
    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get("web_adresi") or "").strip():
        logger.info("Eğitim: bal küpü dolu, yok sayıldı (kurs %s)", x.id)
        return JSONResponse({"ok": True, "durum": None}, headers=ACIK_BASLIKLAR)
    durum = _kayit_durumu(x, await k.aktif_sayisi(db, x.id))
    try:
        if not durum["kayit_acik"]:
            raise s.EgitimHatasi(durum["kayit_neden"] or "kayit_kapali", durum=409)
        g = _kayit_girdisi(x, govde, "form")
        o = await k.kayit_olustur(db, x, g)
    except s.TemelHata as h:
        raise _e_hatasi(h)
    jeton = s.ogrenci_jetonu(o.id, int(o.portal_surumu or 1), o.kod)
    yanit: Dict[str, Any] = {"ok": True, "durum": o.durum, "portal_adresi": f"/egitim/ogrenci/{jeton}", "cocuk": bool(o.cocuk)}
    if o.durum == "bekleme":
        yanit["sira"] = int((await db.execute(select(func.count(EgitimOgrencileri.id)).where(
            EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "bekleme", EgitimOgrencileri.id <= o.id))).scalar() or 1)
    arka.add_task(k.ogrenci_epostasi, o.id, "kayit" if o.durum == "aktif" else "bekleme")
    arka.add_task(k.sahip_bildirimi, o.id)
    return JSONResponse(yanit, headers=GIZLI_BASLIKLAR)


@acik_router.get("/kurum/{slug}")
async def kurum_listesi(slug: str, gecmis: bool = Query(False), db: AsyncSession = Depends(get_db)):
    temiz = (slug or "").strip().lower()
    if not s.SLUG_DESENI.match(temiz):
        raise _hata(404, "liste_yok")
    a = (await db.execute(select(EgitimAyarlari).where(EgitimAyarlari.liste_slug == temiz))).scalars().first()
    if a is None or not a.liste_acik:
        raise _hata(404, "liste_yok")
    if a.hesap_email:
        from services import moduller as modul_servisi

        if not await modul_servisi.modul_acik_mi(db, a.hesap_email, MODUL):
            raise _hata(410, "liste_pasif")
    sorgu = select(EgitimKurslari).where(EgitimKurslari.listede_goster.is_(True))
    sorgu = sorgu.where(EgitimKurslari.hesap_email.is_(None) if a.hesap_email is None else EgitimKurslari.hesap_email == a.hesap_email)
    sorgu = sorgu.where(EgitimKurslari.durum.in_(("yayinda", "tamamlandi") if gecmis else ("yayinda",)))
    kurslar = (await db.execute(sorgu.order_by(EgitimKurslari.baslangic_tarihi, EgitimKurslari.id).limit(200))).scalars().all()
    return JSONResponse({
        "baslik": a.liste_baslik or a.kurum_adi or "", "aciklama": a.liste_aciklama or "", "kurum_adi": a.kurum_adi or "",
        "items": [{"slug": x.slug, "ad": x.ad, "ozet": x.ozet or "", "renk": x.renk, "bicim": x.bicim,
                   "baslangic_tarihi": x.baslangic_tarihi.isoformat() if x.baslangic_tarihi else None,
                   "bitis_tarihi": x.bitis_tarihi.isoformat() if x.bitis_tarihi else None, "fiyat_metni": x.fiyat_metni or "",
                   "durum": x.durum, "egitmenler": s.egitmen_adlari(x)} for x in kurslar],
        "marka": await _marka(db, a.hesap_email),
    }, headers={**ACIK_BASLIKLAR, "Cache-Control": "no-cache", "X-Robots-Tag": "noindex"})


# ---------------------------------------------------------------------------
# Öğrenci portalı (imzalı, girişsiz)
# ---------------------------------------------------------------------------
async def _portal(db: AsyncSession, request: Request, jeton: str, yazma: bool = False):
    """(öğrenci, kurs). Biçim/imza/sürüm tutmazsa 404; ayrılan/anonim/süresi dolan 410; modülü kapalı 410."""
    await _kalici_hiz((_portal_hizi, ip_ozeti("egitim-portal|" + istemci_ip(request))))
    parca = s.jeton_parcala(jeton)
    if parca is None:
        raise _hata(404, "baglanti_gecersiz")
    o = (await db.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == parca[0]))).scalars().first()
    if o is None or int(o.portal_surumu or 1) != parca[1] or not s.ogrenci_jetonu_gecerli_mi(jeton, o.id, parca[1], o.kod):
        raise _hata(404, "baglanti_gecersiz")
    x = (await db.execute(select(EgitimKurslari).where(EgitimKurslari.id == o.kurs_id))).scalars().first()
    if x is None:
        raise _hata(404, "baglanti_gecersiz")
    if o.anonim or o.durum == "ayrildi":
        raise _hata(410, "kayit_kapandi")
    if k.kurs_bitis_ani(x, await k.son_oturum_ani(db, x.id)) + timedelta(days=s.JETON_OMRU_GUN) < s.simdi():
        raise _hata(410, "baglanti_suresi_doldu")
    if x.durum == "taslak" or not await _yayinda_mi(db, x):
        raise _hata(410, "kurs_pasif")
    if yazma:
        if o.durum != "aktif":
            raise _hata(409, "bekleme_listesinde")
        _hiz(_ogrenci_yazma_hizi, f"ogrenci-{o.id}")
    return o, x


@acik_router.get("/ogrenci/{jeton}")
async def portal(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    o, x = await _portal(db, request, jeton)
    an = s.simdi()
    o.portal_son_at = an
    await db.commit()
    ist = (await k.istatistik(db, x, [o], an)).get(o.id, {})
    aktif = o.durum == "aktif"
    oturumlar_ = await k.oturumlar(db, x.id)
    yoklama = {y.oturum_id: y.durum for y in (await db.execute(select(EgitimYoklama).where(EgitimYoklama.ogrenci_id == o.id))).scalars().all()}
    dersler_ = await k.dersler(db, x.id, yalniz_yayinda=True) if aktif else []
    tamam = {i for (i,) in (await db.execute(select(EgitimIlerleme.ders_id).where(EgitimIlerleme.ogrenci_id == o.id))).all()}
    quizler_ = await k.quizler(db, x.id, yalniz_yayinda=True) if aktif else []
    denemeler: Dict[int, List[EgitimDenemeleri]] = {}
    for dn in (await db.execute(select(EgitimDenemeleri).where(EgitimDenemeleri.ogrenci_id == o.id).order_by(EgitimDenemeleri.id))).scalars().all():
        denemeler.setdefault(dn.quiz_id, []).append(dn)
    teslimler = {t.quiz_id: t for t in (await db.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.ogrenci_id == o.id))).scalars().all()}
    teslim_dosyalari: Dict[int, List[Dict[str, Any]]] = {}
    if teslimler:
        for d in (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.teslim_id.in_([t.id for t in teslimler.values()])))).scalars().all():
            teslim_dosyalari.setdefault(d.teslim_id, []).append(_dosya_sozlugu(d))
    sert = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.ogrenci_id == o.id,
                                                               EgitimSertifikalari.iptal_at.is_(None)))).scalars().first()
    duyurular = (await db.execute(select(EgitimDuyurulari).where(EgitimDuyurulari.kurs_id == x.id, EgitimDuyurulari.created_at >= o.created_at)
                                  .order_by(EgitimDuyurulari.id.desc()).limit(20))).scalars().all() if aktif else []
    quiz_listesi = []
    for q in quizler_:
        dn = [d for d in denemeler.get(q.id, []) if d.durum != "devam"]
        devam = next((d for d in denemeler.get(q.id, []) if d.durum == "devam"), None)
        en_iyi = max((int(d.puan or 0) for d in dn), default=None)
        oge = {"id": q.id, "tur": q.tur, "baslik": q.baslik, "aciklama": q.aciklama or "", "ders_id": q.ders_id,
               "soru_sayisi": len(s.json_yukle(q.sorular, []) or []), "sure_dk": q.sure_dk, "gecme_puani": int(q.gecme_puani),
               "son_tarih": s.iso(q.son_tarih)}
        if q.tur == "quiz":
            oge.update({"deneme": len(dn), "deneme_hakki": int(q.deneme_hakki), "en_iyi": en_iyi,
                        "gecti": en_iyi is not None and en_iyi >= int(q.gecme_puani), "devam_eden": devam.id if devam else None})
        else:
            t = teslimler.get(q.id)
            oge["teslim"] = ({"id": t.id, "metin": t.metin or "", "teslim_at": s.iso(t.teslim_at), "puan": t.puan,
                              "geri_bildirim": t.geri_bildirim or "", "notlandi_at": s.iso(t.notlandi_at),
                              "dosyalar": teslim_dosyalari.get(t.id, [])} if t else None)
        quiz_listesi.append(oge)
    sira = None
    if o.durum == "bekleme":
        sira = int((await db.execute(select(func.count(EgitimOgrencileri.id)).where(
            EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.durum == "bekleme", EgitimOgrencileri.id <= o.id))).scalar() or 1)
    return JSONResponse({
        "ogrenci": {"ad": o.ad or "", "kod": o.kod, "durum": o.durum, "sira": sira, "dil": o.dil,
                    "qr": f"/api/v1/egitim/ogrenci/{jeton}/qr.svg"},
        "kurs": {"ad": x.ad, "slug": x.slug, "ozet": x.ozet or "", "aciklama": x.aciklama or "", "renk": x.renk,
                 "egitmenler": s.egitmen_adlari(x), "bicim": x.bicim, "mekan": x.mekan or "", "adres": x.adres or "",
                 "online_baglanti": (x.online_baglanti or "") if aktif else "", "saat_dilimi": x.saat_dilimi, "dil": x.dil,
                 "baslangic_tarihi": x.baslangic_tarihi.isoformat() if x.baslangic_tarihi else None,
                 "bitis_tarihi": x.bitis_tarihi.isoformat() if x.bitis_tarihi else None, "fiyat_metni": x.fiyat_metni or "",
                 "sertifika": bool(x.sertifika_aktif)},
        "program": [{"id": ot.id, "baslangic": s.iso(ot.baslangic), "bitis": s.iso(ot.bitis), "konu": ot.konu or "",
                     "durum": ot.durum, "yoklama": yoklama.get(ot.id), "yoklama_acik": aktif and s.yoklama_acik_mi(ot, an)}
                    for ot in oturumlar_],
        "dersler": [{"id": d.id, "bolum": d.bolum or "", "baslik": d.baslik, "sure_dk": d.sure_dk, "tamamlandi": d.id in tamam,
                     "video": bool(d.video_url)} for d in dersler_],
        "quizler": quiz_listesi,
        "istatistik": ist,
        "sertifika": ({"kod": sert.kod, "kod_yazi": s.sertifika_kodu_yaz(sert.kod), "verilme_at": s.iso(sert.verilme_at),
                       "pdf": f"/api/v1/egitim/ogrenci/{jeton}/sertifika.pdf", "dogrulama": f"/egitim/sertifika/{sert.kod}"}
                      if sert else None),
        "duyurular": [{"konu": d.konu, "metin": d.metin, "created_at": s.iso(d.created_at)} for d in duyurular],
        "takvim": f"/api/v1/egitim/ogrenci/{jeton}/takvim.ics",
        "marka": await _marka(db, x.hesap_email, x.renk),
    }, headers=GIZLI_BASLIKLAR)


@acik_router.get("/ogrenci/{jeton}/takvim.ics")
async def portal_takvim(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    o, x = await _portal(db, request, jeton)
    metin_ = s.ics_uret(x, await k.oturumlar(db, x.id), o.dil if o.dil in s.DILLER else x.dil, ogrenciye=o.durum == "aktif")
    return Response(metin_, media_type="text/calendar; charset=utf-8",
                    headers={**GIZLI_BASLIKLAR, "Content-Disposition": icerik_konumu(f"{x.slug}.ics")})


@acik_router.get("/ogrenci/{jeton}/qr.svg")
async def portal_qr(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    o, x = await _portal(db, request, jeton)
    g = _qr_gorsel(s.qr_icerigi(o.kod), "svg")
    return Response(g.veri, media_type=g.tur, headers={**GIZLI_BASLIKLAR, "Cache-Control": "private, max-age=3600"})


@acik_router.get("/ogrenci/{jeton}/ders/{did}")
async def portal_ders(jeton: str, did: int, request: Request, db: AsyncSession = Depends(get_db)):
    o, x = await _portal(db, request, jeton)
    if o.durum != "aktif":
        raise _hata(409, "bekleme_listesinde")
    d = (await db.execute(select(EgitimDersleri).where(EgitimDersleri.id == did, EgitimDersleri.kurs_id == x.id,
                                                       EgitimDersleri.yayinda.is_(True)))).scalars().first()
    if d is None:
        raise _hata(404, "bulunamadi")
    ekler = (await _dosyalar(db, [d.id])).get(d.id)
    tamam = (await db.execute(select(EgitimIlerleme.id).where(EgitimIlerleme.ogrenci_id == o.id, EgitimIlerleme.ders_id == d.id))).first()
    return JSONResponse({**_ders_sozlugu(d, ekler), "tamamlandi": tamam is not None}, headers=GIZLI_BASLIKLAR)


@acik_router.post("/ogrenci/{jeton}/ders/{did}/tamamla")
async def portal_tamamla(jeton: str, did: int, request: Request, db: AsyncSession = Depends(get_db)):
    govde = await _govde_oku(request, 1024)
    o, x = await _portal(db, request, jeton, yazma=True)
    d = (await db.execute(select(EgitimDersleri).where(EgitimDersleri.id == did, EgitimDersleri.kurs_id == x.id,
                                                       EgitimDersleri.yayinda.is_(True)))).scalars().first()
    if d is None:
        raise _hata(404, "bulunamadi")
    mevcut = (await db.execute(select(EgitimIlerleme).where(EgitimIlerleme.ogrenci_id == o.id, EgitimIlerleme.ders_id == d.id))).scalars().first()
    if govde.get("tamamlandi", True) is False:
        if mevcut is not None:
            await db.delete(mevcut)
    elif mevcut is None:
        try:
            async with db.begin_nested():
                db.add(EgitimIlerleme(kurs_id=x.id, ogrenci_id=o.id, ders_id=d.id, tamamlandi_at=s.simdi()))
                await db.flush()
        except IntegrityError:
            pass
    await db.commit()
    ist = (await k.istatistik(db, x, [o])).get(o.id, {})
    return JSONResponse({"ok": True, "tamamlandi": govde.get("tamamlandi", True) is not False, "istatistik": ist},
                        headers=GIZLI_BASLIKLAR)


@acik_router.get("/ogrenci/{jeton}/dosya/{fid}")
async def portal_dosya(jeton: str, fid: int, request: Request, db: AsyncSession = Depends(get_db)):
    o, x = await _portal(db, request, jeton)
    d = (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.id == fid, EgitimDosyalari.kurs_id == x.id))).scalars().first()
    if d is None:
        raise _hata(404, "bulunamadi")
    if d.ders_id is not None:
        if o.durum != "aktif":
            raise _hata(409, "bekleme_listesinde")
        ders = (await db.execute(select(EgitimDersleri.yayinda).where(EgitimDersleri.id == d.ders_id))).scalar()
        if not ders:
            raise _hata(404, "bulunamadi")
    else:
        # Teslim dosyası: yalnız kendi teslimi.
        sahibi = (await db.execute(select(EgitimTeslimleri.ogrenci_id).where(EgitimTeslimleri.id == d.teslim_id))).scalar()
        if sahibi != o.id:
            raise _hata(404, "bulunamadi")
    return await _dosya_yaniti(db, d)


async def _portal_quiz(db: AsyncSession, x: EgitimKurslari, qid: int, tur: str) -> EgitimQuizleri:
    q = (await db.execute(select(EgitimQuizleri).where(EgitimQuizleri.id == qid, EgitimQuizleri.kurs_id == x.id,
                                                       EgitimQuizleri.yayinda.is_(True), EgitimQuizleri.tur == tur))).scalars().first()
    if q is None:
        raise _hata(404, "bulunamadi")
    return q


def _deneme_suresi_doldu_mu(dn: EgitimDenemeleri, an: datetime) -> bool:
    return dn.son_at is not None and an > s.utc(dn.son_at) + s.SURE_PAYI


@acik_router.post("/ogrenci/{jeton}/quiz/{qid}/basla")
async def portal_quiz_basla(jeton: str, qid: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Deneme başlatır (ya da süresi dolmamış açık denemeyi sürdürür). Sorular cevapsız; süre sunucu saatiyle."""
    o, x = await _portal(db, request, jeton, yazma=True)
    q = await _portal_quiz(db, x, qid, "quiz")
    an = s.simdi()
    if q.son_tarih and an > s.utc(q.son_tarih):
        raise _hata(409, "son_tarih_gecti")
    denemeler = (await db.execute(select(EgitimDenemeleri).where(EgitimDenemeleri.quiz_id == q.id, EgitimDenemeleri.ogrenci_id == o.id)
                                  .order_by(EgitimDenemeleri.id))).scalars().all()
    sorular = s.json_yukle(q.sorular, []) or []
    devam = next((d for d in denemeler if d.durum == "devam"), None)
    if devam is not None and _deneme_suresi_doldu_mu(devam, an):
        devam.durum, devam.puan, devam.dogru, devam.toplam, devam.gonderim_at = "suresi_doldu", 0, 0, len(sorular), an
        await db.commit()
        devam = None
    if devam is None:
        biten = sum(1 for d in denemeler if d.durum != "devam")
        if biten >= int(q.deneme_hakki):
            raise _hata(409, "deneme_hakki_doldu", sinir=int(q.deneme_hakki))
        devam = EgitimDenemeleri(kurs_id=x.id, quiz_id=q.id, ogrenci_id=o.id, baslangic_at=an,
                                 son_at=an + timedelta(minutes=int(q.sure_dk)) if q.sure_dk else None, durum="devam",
                                 dogru=0, toplam=len(sorular))
        db.add(devam)
        await db.commit()
        await db.refresh(devam)
    return JSONResponse({"deneme_id": devam.id, "baslangic_at": s.iso(devam.baslangic_at), "son_at": s.iso(devam.son_at),
                         "sunucu_saati": s.iso(an), "baslik": q.baslik, "aciklama": q.aciklama or "",
                         "sorular": s.sorular_ogrenciye(sorular)}, headers=GIZLI_BASLIKLAR)


@acik_router.post("/ogrenci/{jeton}/quiz/{qid}/gonder")
async def portal_quiz_gonder(jeton: str, qid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """`{"deneme_id", "yanitlar": {soru id: cevap}}` → otomatik puan. Süre (+30 sn pay) geçtiyse puan 0 (`suresi_doldu`)."""
    govde = await _govde_oku(request, 65536)
    o, x = await _portal(db, request, jeton, yazma=True)
    q = await _portal_quiz(db, x, qid, "quiz")
    did = govde.get("deneme_id")
    if isinstance(did, bool) or not isinstance(did, int):
        raise _hata(400, "deneme_yok", alan="deneme_id")
    dn = (await db.execute(select(EgitimDenemeleri).where(EgitimDenemeleri.id == did, EgitimDenemeleri.quiz_id == q.id,
                                                          EgitimDenemeleri.ogrenci_id == o.id))).scalars().first()
    if dn is None:
        raise _hata(404, "deneme_yok")
    if dn.durum != "devam":
        raise _hata(409, "deneme_bitti")
    an = s.simdi()
    sorular = s.json_yukle(q.sorular, []) or []
    yanitlar = s.yanitlari_temizle(sorular, govde.get("yanitlar"))
    dn.gonderim_at, dn.yanitlar, dn.toplam = an, s.json_yaz(yanitlar), len(sorular)
    if _deneme_suresi_doldu_mu(dn, an):
        dn.durum, dn.puan, dn.dogru = "suresi_doldu", 0, 0
        ayrinti: Dict[str, bool] = {}
    else:
        p = s.puanla(sorular, yanitlar)
        dn.durum, dn.puan, dn.dogru = "tamamlandi", p["puan"], p["dogru"]
        ayrinti = p["ayrinti"]
    await db.commit()
    ist = (await k.istatistik(db, x, [o])).get(o.id, {})
    return JSONResponse({"durum": dn.durum, "puan": int(dn.puan or 0), "dogru": int(dn.dogru or 0), "toplam": int(dn.toplam or 0),
                         "gecti": int(dn.puan or 0) >= int(q.gecme_puani), "ayrinti": ayrinti, "istatistik": ist},
                        headers=GIZLI_BASLIKLAR)


@acik_router.post("/ogrenci/{jeton}/odev/{qid}")
async def portal_odev(jeton: str, qid: int, request: Request, metin: str = Form(""), dosya: Optional[UploadFile] = File(None),
                      db: AsyncSession = Depends(get_db)):
    """Ödev teslimi (metin ve/veya tek dosya). Notlanana kadar yeniden teslim edilebilir (son teslim geçerli)."""
    o, x = await _portal(db, request, jeton, yazma=True)
    q = await _portal_quiz(db, x, qid, "odev")
    try:
        metin_ = s.metin(metin, "metin", 20000, cok_satir=True) or None
    except s.TemelHata as h:
        raise _e_hatasi(h)
    veri = await _dosya_oku(dosya, db) if dosya is not None and (dosya.filename or "") else None
    if not metin_ and not veri:
        raise _hata(400, "teslim_bos", alan="metin")
    t = (await db.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.quiz_id == q.id, EgitimTeslimleri.ogrenci_id == o.id))).scalars().first()
    if t is not None and t.notlandi_at is not None:
        raise _hata(409, "notlandi")
    an = s.simdi()
    if t is None:
        t = EgitimTeslimleri(kurs_id=x.id, quiz_id=q.id, ogrenci_id=o.id, teslim_at=an, created_at=an)
        db.add(t)
        await db.flush()
    t.metin, t.teslim_at = metin_, an
    if veri:
        await k.dosyalari_sil(db, (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.teslim_id == t.id))).scalars().all())
        try:
            await k.dosya_kaydet(db, x, ad_ham=dosya.filename or "odev", veri=veri, yukleyen=None, teslim_id=t.id)
        except s.TemelHata as h:
            await db.rollback()
            raise _e_hatasi(h)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "tekrar_deneyin")
    return JSONResponse({"ok": True, "teslim_at": s.iso(an), "gec": bool(q.son_tarih and an > s.utc(q.son_tarih))},
                        headers=GIZLI_BASLIKLAR)


async def _yoklama_isle(db: AsyncSession, o: EgitimOgrencileri, x: EgitimKurslari, ot: EgitimOturumlari, kaynak: str) -> Dict[str, Any]:
    an = s.simdi()
    if not s.yoklama_acik_mi(ot, an):
        raise _hata(410, "yoklama_kapali")
    ne, satir = await k.yoklama_yaz(db, x, ot, o, k.okutma_durumu(ot, an), kaynak, None)
    await db.commit()
    return {"ok": True, "sonuc": "zaten" if ne == "zaten" else "isaretlendi", "durum": satir.durum if satir else None,
            "oturum": {"baslangic": s.iso(ot.baslangic), "bitis": s.iso(ot.bitis), "konu": ot.konu or ""}, "kurs": x.ad}


@acik_router.post("/ogrenci/{jeton}/yoklama")
async def portal_yoklama(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    """`{"kod": "K7Q2M9"}` — tahtadaki 6 haneli oturum kodu (yalnız ders saati penceresinde)."""
    govde = await _govde_oku(request, 1024)
    o, x = await _portal(db, request, jeton, yazma=True)
    kod = s.kisa_kod_duzelt(govde.get("kod"))
    if kod is None:
        raise _hata(400, "kod_gecersiz", alan="kod")
    an = s.simdi()
    for ot in await k.oturumlar(db, x.id):
        if s.yoklama_acik_mi(ot, an) and s.oturum_kodu(ot.id, int(ot.yoklama_surumu or 1)) == kod:
            return JSONResponse(await _yoklama_isle(db, o, x, ot, "kod"), headers=GIZLI_BASLIKLAR)
    raise _hata(404, "kod_gecersiz", alan="kod")


@acik_router.get("/ogrenci/{jeton}/sertifika.pdf")
async def portal_sertifika(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    o, x = await _portal(db, request, jeton)
    c = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.ogrenci_id == o.id,
                                                            EgitimSertifikalari.iptal_at.is_(None)))).scalars().first()
    if c is None:
        raise _hata(404, "sertifika_yok")
    yanit = await _sertifika_pdf_yaniti(db, x, o, c)
    yanit.headers["Referrer-Policy"] = "no-referrer"
    return yanit


# ---------------------------------------------------------------------------
# Oturum QR'ı (sınıfta okutulan) ve sertifika doğrulama
# ---------------------------------------------------------------------------
async def _oturum_jetonlu(db: AsyncSession, jeton: str):
    parca = s.jeton_parcala(jeton)
    if parca is None:
        raise _hata(404, "baglanti_gecersiz")
    ot = (await db.execute(select(EgitimOturumlari).where(EgitimOturumlari.id == parca[0]))).scalars().first()
    if ot is None or int(ot.yoklama_surumu or 1) != parca[1] or not s.oturum_jetonu_gecerli_mi(jeton, ot.id, parca[1]):
        raise _hata(404, "baglanti_gecersiz")
    x = (await db.execute(select(EgitimKurslari).where(EgitimKurslari.id == ot.kurs_id))).scalars().first()
    if x is None or not await _yayinda_mi(db, x):
        raise _hata(410, "kurs_pasif")
    return ot, x


@acik_router.get("/yoklama/{jeton}")
async def yoklama_sayfasi(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _kalici_hiz((_portal_hizi, ip_ozeti("egitim-portal|" + istemci_ip(request))))
    ot, x = await _oturum_jetonlu(db, jeton)
    return JSONResponse({"kurs": x.ad, "renk": x.renk, "dil": x.dil, "saat_dilimi": x.saat_dilimi,
                         "baslangic": s.iso(ot.baslangic), "bitis": s.iso(ot.bitis), "konu": ot.konu or "",
                         "acik": s.yoklama_acik_mi(ot), "iptal": ot.durum == "iptal"}, headers=GIZLI_BASLIKLAR)


@acik_router.post("/yoklama/{jeton}")
async def yoklama_isaretle(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    """`{"ogrenci": <bu cihazdaki öğrenci bağlantısının jetonu>}` — başka kursun öğrencisi 403 `farkli_kurs`."""
    govde = await _govde_oku(request, 1024)
    ot, x = await _oturum_jetonlu(db, jeton)
    o, ox = await _portal(db, request, str(govde.get("ogrenci") or ""), yazma=True)
    if ox.id != x.id:
        raise _hata(403, "farkli_kurs")
    return JSONResponse(await _yoklama_isle(db, o, x, ot, "qr"), headers=GIZLI_BASLIKLAR)


@acik_router.get("/sertifika/{kod}")
async def sertifika_dogrula(kod: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Herkese açık doğrulama: geçerli mi, kurs, kurum, tarih ve YALNIZ maskeli ad (e-posta, telefon, veli,
    tam ad, öğrenci kodu YOK)."""
    await _kalici_hiz((_dogrulama_hizi, ip_ozeti("egitim-sertifika|" + istemci_ip(request))))
    temiz = s.sertifika_kodu_duzelt(kod)
    c = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.kod == temiz))).scalars().first() if temiz else None
    if c is None:
        raise _hata(404, "sertifika_yok")
    return JSONResponse({"gecerli": c.iptal_at is None, "kod": s.sertifika_kodu_yaz(c.kod), "ad": c.ad_maskeli or "—",
                         "kurs": c.kurs_adi, "kurum": c.kurum_adi or "", "verilme_at": s.iso(c.verilme_at),
                         "iptal_at": s.iso(c.iptal_at)}, headers={**GIZLI_BASLIKLAR, "Cache-Control": "no-cache"})


router = (yonetici_router, musteri_router, acik_router)
