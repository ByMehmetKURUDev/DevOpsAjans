"""Faz 6P — Stok ve satış noktası (POS): ürün, barkod, stok hareketi, sayım, kasa, fiş, rapor.

Müşteri (`/api/v1/stok-pos`; modül `stok_pos` açık + hesap ekibi izni `stok` YA DA `kasa`) — etkin hesap =
işletme. `stok`: yönetim (ürün, hareket, sayım, tedarikçi, rapor, ayar); `kasa`: YALNIZ satış ekranı
(ürün arama/okutma, sepet, ödeme, fiş, kasa aç/kapa, kendi kasasının özeti; iade/iptal ve indirim
ayardaki sınırla). Sahip bütün izinlere sahip.
  GET  /meta                                yetkiler, ayarlar, konumlar, KDV oranları, sınırlar, açık kasalar
  GET|PUT /ayarlar                          firma künyesi, KDV oranları, eksi stok, kasiyer yetkileri      [stok]
  POST /konumlar, PUT|DELETE /konumlar/{konum_id}   depo/şube (`sube_siniri`)                          [stok]
  GET  /urunler?ara=&kategori=&kritik=&aktif=&konum_id=   (kasa da: maliyet gizli)
  GET  /urunler/kod/{kod}                   barkod/SKU ile ürün (okutma)
  GET  /urunler/{urun_id}                   ürün + varyantlar + son hareketler
  POST /urunler, PUT|DELETE /urunler/{urun_id}, POST /urunler/{urun_id}/varyant                       [stok]
  POST /barkod-uret                         boş iç EAN-13                                                [stok]
  GET  /urunler.csv, POST /urunler/ice-aktar (multipart `dosya`)                                         [stok]
  GET  /menu-kaynaklari, POST /menuden-aktar {magaza_id}   QR menü/katalog ürünlerini bağlı aktar      [stok]
  GET|POST /tedarikciler, PUT|DELETE /tedarikciler/{tedarikci_id}                                          [stok]
  GET  /hareketler, POST /hareketler (giris/cikis/fire/duzeltme), POST /transfer                          [stok]
  GET|POST /sayimlar, GET /sayimlar/{sayim_id}, POST /sayimlar/{sayim_id}/okut|onayla|iptal                [stok]
  GET  /kasa, POST /kasa/ac, GET /kasa/{oturum_id}, POST /kasa/{oturum_id}/kapat    (kasa)
  GET  /kasa-oturumlari?bas=&bit=                                                                          [stok]
  POST /satislar/onizle, POST /satislar, GET /satislar, GET /satislar/{satis_id}, GET /satislar/{satis_id}/fis.pdf
  POST /satislar/{satis_id}/iade|iptal      [stok ya da kasa + ayar `kasa_iade`]
  POST /satislar/{satis_id}/fatura, GET /satislar/{satis_id}/fatura.pdf   (bilgi amaçlı PDF fatura)
  GET|POST /alicilar (kasa), PUT|DELETE /alicilar/{alici_id}                                               [stok]
  GET  /raporlar/gun|donem|kar|stok-degeri|hareketsiz (?bicim=csv)                                         [stok]

Yönetici (`/api/v1/stok-pos-yonetim`, ajans): `GET /hesaplar` + okuma uçlarının aynısı `?hesap=` ile —
SALT OKUNUR (destek amaçlı; alıcı listesi yok).
"""

import logging
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from models.stok_pos import (
    PosAlicilari,
    PosIadeler,
    PosKasaOturumlari,
    PosSatisKalemleri,
    PosSatislari,
    StokAyarlari,
    StokHareketleri,
    StokKonumlari,
    StokSayimKalemleri,
    StokSayimlari,
    StokSeviyeleri,
    StokTedarikcileri,
    StokUrunleri,
)
from services import stok_kayit as sk
from services import stok_pos as s
from services.stok_kayit import Yetki
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

MODUL = s.MODUL

yonetici_router = APIRouter(prefix="/api/v1/stok-pos-yonetim", tags=["stok_pos"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/stok-pos",
    tags=["stok_pos"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(s.IZIN_STOK, s.IZIN_KASA))],
)

#: Kişi başı dakikada 300 yazma (kasa yoğun saatte hızlı okutur), 10 içe aktarma.
_yazma_hizi = HizSiniri(300, 60.0)
_aktarma_hizi = HizSiniri(10, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _aktarma_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _s_hatasi(h: s.StokHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _musteri_yetkisi(request: Request) -> Yetki:
    b = izin_iste(request, s.IZIN_STOK, s.IZIN_KASA)
    stok = b.izin_var(s.IZIN_STOK)
    return Yetki(b.hesap_email, b.kisi_email, stok, stok or b.izin_var(s.IZIN_KASA))


def _yonetici_yetkisi(request: Request) -> Yetki:
    kullanici, _ = _yonetici_mi(request)
    hesap = (request.query_params.get("hesap") or "").strip().lower()
    if not hesap or "@" not in hesap or len(hesap) > 254:
        raise _hata(400, "hesap_gerekli", alan="hesap")
    return Yetki(hesap, (getattr(kullanici, "email", "") or "").strip().lower(), True, False, ajans=True)


def _stok_iste(y: Yetki) -> None:
    if not y.stok:
        raise _hata(403, "hesap_izni_yok", izin=s.IZIN_STOK)


def _kasa_iste(y: Yetki) -> None:
    if not y.kasa:
        raise _hata(403, "hesap_izni_yok", izin=s.IZIN_KASA)


def _hiz(y: Yetki, sinir: HizSiniri = _yazma_hizi) -> None:
    if not sinir.izin_var_mi(y.kisi or "anonim"):
        raise _hata(429, "cok_hizli")


async def _govde(request: Request, sinir: int = 256 * 1024) -> Dict[str, Any]:
    ham = await request.body()
    if len(ham) > sinir:
        raise _hata(413, "govde_buyuk")
    if not ham:
        return {}
    try:
        import json

        g = json.loads(ham.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _hata(400, "govde_gecersiz")
    if not isinstance(g, dict):
        raise _hata(400, "govde_gecersiz")
    return g


def _tarih(ham: Optional[str], alan: str, varsayilan: date) -> date:
    try:
        return s.tarih_coz(ham, alan, varsayilan)
    except s.StokHatasi as h:
        raise _s_hatasi(h)


def _aralik(bas: Optional[str], bit: Optional[str], gun: int = 30) -> tuple:
    bugun = s.tr_gunu()
    b = _tarih(bas, "bas", bugun - timedelta(days=gun - 1))
    e = _tarih(bit, "bit", bugun)
    if e < b:
        raise _hata(400, "aralik_gecersiz", alan="bit")
    if (e - b).days > 366:
        raise _hata(400, "aralik_cok_uzun", alan="bas", en_cok=366)
    return b, e


def _csv_yaniti(metin: str, ad: str) -> Response:
    return Response(metin.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})


def _pdf_yaniti(veri: bytes, ad: str) -> Response:
    return Response(content=veri, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})


def _tarih_metni(an: Any) -> str:
    u = s.utc(an)
    if u is None:
        return ""
    return u.astimezone(s._tz()).strftime("%d.%m.%Y %H:%M")  # noqa: SLF001


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _ayar_sozlugu(a: StokAyarlari) -> Dict[str, Any]:
    return {
        "firma_adi": a.firma_adi, "adres": a.adres, "telefon": a.telefon, "eposta": a.eposta, "vergi_dairesi": a.vergi_dairesi,
        "vergi_no": a.vergi_no, "para_birimi": a.para_birimi or "TRY", "kdv_oranlari": s.kdv_oranlari(a.kdv_oranlari),
        "kdv_varsayilan": a.kdv_oranlari in (None, ""), "varsayilan_kdv": a.varsayilan_kdv, "eksi_stok": bool(a.eksi_stok),
        "kasa_iade": bool(a.kasa_iade), "kasa_indirim_yuzde": int(a.kasa_indirim_yuzde or 0),
        "qr_stok_esitle": bool(a.qr_stok_esitle), "kritik_bildirim": bool(a.kritik_bildirim), "fis_notu": a.fis_notu,
    }


def _firma(a: StokAyarlari) -> Dict[str, Any]:
    return {"ad": a.firma_adi, "adres": a.adres, "telefon": a.telefon, "eposta": a.eposta, "vergi_dairesi": a.vergi_dairesi,
            "vergi_no": a.vergi_no, "fis_notu": a.fis_notu}


def _konum_sozlugu(k: StokKonumlari) -> Dict[str, Any]:
    return {"id": k.id, "ad": k.ad, "adres": k.adres, "varsayilan": bool(k.varsayilan), "aktif": bool(k.aktif), "sira": k.sira}


def _urun_sozlugu(u: StokUrunleri, seviye: Dict[int, int], maliyet: bool) -> Dict[str, Any]:
    toplam = sum(seviye.values())
    d = {
        "id": u.id, "ad": u.ad, "barkod": u.barkod, "barkod_turu": s.barkod_turu(u.barkod), "sku": u.sku, "kategori": u.kategori,
        "birim": u.birim, "satis_fiyati": u.satis_fiyati, "kdv_orani": u.kdv_orani, "kritik_esik": s.miktar_yaz(u.kritik_esik),
        "stok_takibi": bool(u.stok_takibi), "ana_urun_id": u.ana_urun_id, "varyant": s.json_yukle(u.varyant, None),
        "menu_urun_id": u.menu_urun_id, "aktif": bool(u.aktif), "notlar": u.notlar,
        "stok": {"toplam": s.miktar_yaz(toplam), "konumlar": {str(k): s.miktar_yaz(m) for k, m in seviye.items()}},
        "kritik": bool(u.stok_takibi and u.kritik_esik is not None and toplam <= u.kritik_esik),
    }
    if maliyet:
        d["alis_fiyati"] = u.alis_fiyati
    return d


def _tedarikci_sozlugu(t: StokTedarikcileri) -> Dict[str, Any]:
    return {"id": t.id, "ad": t.ad, "yetkili": t.yetkili, "telefon": t.telefon, "eposta": t.eposta, "vergi_no": t.vergi_no,
            "notlar": t.notlar, "aktif": bool(t.aktif)}


def _hareket_sozlugu(h: StokHareketleri, adlar: Dict[int, str]) -> Dict[str, Any]:
    return {"id": h.id, "urun_id": h.urun_id, "urun_ad": adlar.get(h.urun_id), "konum_id": h.konum_id, "tur": h.tur,
            "miktar": s.miktar_yaz(h.miktar), "sonra": s.miktar_yaz(h.sonra), "birim_maliyet": h.birim_maliyet,
            "tedarikci_id": h.tedarikci_id, "satis_id": h.satis_id, "sayim_id": h.sayim_id, "transfer_kodu": h.transfer_kodu,
            "belge_no": h.belge_no, "aciklama": h.aciklama, "kisi": h.kisi, "zaman": s.iso(h.zaman)}


def _satis_ozeti(x: PosSatislari) -> Dict[str, Any]:
    return {"id": x.id, "no": x.no, "durum": x.durum, "zaman": s.iso(x.zaman), "konum_id": x.konum_id, "oturum_id": x.oturum_id,
            "kasiyer": x.kasiyer, "musteri_ad": x.musteri_ad, "toplam": x.toplam, "iade_toplam": x.iade_toplam,
            "odeme_turu": x.odeme_turu, "fatura_no": x.fatura_no, "para_birimi": x.para_birimi}


async def _satis_ayrintisi(db: AsyncSession, x: PosSatislari) -> Dict[str, Any]:
    satirlar = await sk.kalemler(db, x.id)
    iadeler = (await db.execute(select(PosIadeler).where(PosIadeler.satis_id == x.id).order_by(PosIadeler.id))).scalars().all()
    a = await sk.ayarlar(db, x.hesap_email)
    return {
        **_satis_ozeti(x), "tarih_metni": _tarih_metni(x.zaman), "alici_id": x.alici_id,
        "ara_toplam": x.ara_toplam, "satir_indirim": x.satir_indirim, "toplam_indirim": x.toplam_indirim,
        "kdv_toplam": x.kdv_toplam, "kdv_dokumu": s.json_yukle(x.kdv_dokumu, []), "nakit": x.nakit, "kart": x.kart,
        "havale": x.havale, "nakit_alinan": x.nakit_alinan, "para_ustu": x.para_ustu, "notlar": x.notlar,
        "fatura_at": s.iso(x.fatura_at), "fatura_alici": s.json_yukle(x.fatura_alici, None),
        "kalemler": [{
            "id": k.id, "urun_id": k.urun_id, "ad": k.ad, "barkod": k.barkod, "birim": k.birim, "adet": s.miktar_yaz(k.adet),
            "adet_binde": k.adet, "birim_fiyat": k.birim_fiyat, "brut": k.tutar + k.indirim, "satir_indirim": k.satir_indirim,
            "indirim": k.indirim, "tutar": k.tutar, "kdv_orani": k.kdv_orani, "kdv": k.kdv, "iade_adet": s.miktar_yaz(k.iade_adet),
            "iade_adet_binde": k.iade_adet, "iade_tutar": k.iade_tutar,
        } for k in satirlar],
        "iadeler": [{"id": i.id, "tur": i.tur, "tutar": i.tutar, "odeme_turu": i.odeme_turu, "neden": i.neden, "kisi": i.kisi,
                     "zaman": s.iso(i.zaman), "kalemler": s.json_yukle(i.kalemler, [])} for i in iadeler],
        "firma": _firma(a),
        "mali_degil": s.FIS_NOTU_TR,
    }


def _sayim_sozlugu(x: StokSayimlari) -> Dict[str, Any]:
    return {"id": x.id, "konum_id": x.konum_id, "durum": x.durum, "aciklama": x.aciklama, "baslatan": x.baslatan,
            "onaylayan": x.onaylayan, "baslangic": s.iso(x.baslangic), "bitis": s.iso(x.bitis), "ozet": s.json_yukle(x.ozet, None)}


async def _gecisler(db: AsyncSession, y: Yetki, gecisler: List[sk.Gecis]) -> List[int]:
    return await sk.gecisleri_isle(db, y.hesap, gecisler)


async def _iade_yetkisi(db: AsyncSession, y: Yetki) -> None:
    if y.stok:
        return
    a = await sk.ayarlar(db, y.hesap)
    if not (y.kasa and a.kasa_iade):
        raise _hata(403, "iade_yetkisi_yok")


# ---------------------------------------------------------------------------
# Uçlar (okuma iki panelde; yazma yalnız müşteri panelinde)
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam: Callable[[Request], Yetki], yazma: bool) -> None:  # noqa: C901
    # ------------------------------------------------------------- meta
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        a = await sk.ayarlar(db, y.hesap)
        konumlar = await sk.konumlar(db, y.hesap, hepsi=True)
        acik = (await db.execute(select(PosKasaOturumlari).where(PosKasaOturumlari.hesap_email == y.hesap,
                                                                 PosKasaOturumlari.durum == "acik"))).scalars().all()
        kritik = int((await db.execute(select(func.count(StokUrunleri.id)).where(
            StokUrunleri.hesap_email == y.hesap, StokUrunleri.aktif.is_(True), StokUrunleri.kritik_at.isnot(None)))).scalar() or 0)
        qr = False
        if not y.ajans and y.stok:
            from services.moduller import modul_acik_mi

            qr = await modul_acik_mi(db, y.hesap, "qr_menu") or await modul_acik_mi(db, y.hesap, "whatsapp_katalog")
        return {
            "hesap": y.hesap, "ben": y.kisi, "yetki": {"stok": y.stok, "kasa": y.kasa, "ajans": y.ajans}, "salt_okunur": y.ajans,
            "ayarlar": _ayar_sozlugu(a), "varsayilan_kdv_oranlari": list(s.KDV_ORANLARI), "birimler": list(s.BIRIMLER),
            "odeme_turleri": list(s.ODEME_TURLERI), "hareket_turleri": list(s.HAREKET_TURLERI),
            "elle_hareketler": list(s.ELLE_HAREKETLER), "konumlar": [_konum_sozlugu(k) for k in konumlar],
            "sinirlar": {
                "urun": await sk.modul_ayari(db, y.hesap, "urun_siniri", s.VARSAYILAN_URUN_SINIRI),
                "sube": await sk.modul_ayari(db, y.hesap, "sube_siniri", s.VARSAYILAN_SUBE_SINIRI),
                "kasa_kullanici": await sk.modul_ayari(db, y.hesap, "kasa_kullanici_siniri", s.VARSAYILAN_KASA_KULLANICI_SINIRI),
            },
            "sayilar": {"urun": await sk.urun_sayisi(db, y.hesap), "kritik": kritik},
            "acik_oturumlar": [sk.oturum_sozlugu(o) for o in acik],
            "qr_menu": qr, "notlar": {"fis": s.FIS_NOTU_TR, "z": s.Z_NOTU_TR},
        }

    # ------------------------------------------------------------- ürünler
    @router.get("/urunler")
    async def urunler(request: Request, ara: Optional[str] = Query(None, max_length=120), kategori: Optional[str] = Query(None, max_length=80),
                      kritik: bool = Query(False), aktif: str = Query("evet"), sayfa: int = Query(1, ge=1, le=10000),
                      adet: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        kosul = [StokUrunleri.hesap_email == y.hesap]
        if aktif == "evet" or not y.stok:
            kosul.append(StokUrunleri.aktif.is_(True))
        elif aktif == "hayir":
            kosul.append(StokUrunleri.aktif.is_(False))
        if kategori:
            kosul.append(StokUrunleri.kategori == kategori)
        if kritik:
            kosul.append(StokUrunleri.kritik_at.isnot(None))
        if ara and ara.strip():
            a = ara.strip()
            # SQLite `lower` yalnız ASCII: yazıldığı gibi de aranır (Çay / çay).
            kosul.append(or_(StokUrunleri.ad.contains(a), func.lower(StokUrunleri.ad).contains(a.lower()),
                             StokUrunleri.barkod.startswith(a), StokUrunleri.sku.startswith(a)))
        toplam = int((await db.execute(select(func.count(StokUrunleri.id)).where(*kosul))).scalar() or 0)
        liste = (await db.execute(select(StokUrunleri).where(*kosul).order_by(StokUrunleri.ad, StokUrunleri.id)
                                  .offset((sayfa - 1) * adet).limit(adet))).scalars().all()
        sev = await sk.seviyeler(db, [u.id for u in liste])
        kategoriler = [k for k in (await db.execute(select(StokUrunleri.kategori).where(
            StokUrunleri.hesap_email == y.hesap, StokUrunleri.kategori.isnot(None)).distinct().order_by(StokUrunleri.kategori))).scalars().all() if k]
        return {"items": [_urun_sozlugu(u, sev.get(u.id, {}), y.stok) for u in liste], "toplam": toplam, "sayfa": sayfa,
                "kategoriler": kategoriler}

    @router.get("/urunler/kod/{kod}")
    async def urun_kodla(kod: str, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        u = await sk.kodla_bul(db, y.hesap, kod)
        if u is None:
            raise _hata(404, "urun_yok")
        return _urun_sozlugu(u, (await sk.seviyeler(db, [u.id]))[u.id], y.stok)

    @router.get("/urunler.csv")
    async def urunler_csv(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        liste = (await db.execute(select(StokUrunleri).where(StokUrunleri.hesap_email == y.hesap, StokUrunleri.aktif.is_(True))
                                  .order_by(StokUrunleri.ad))).scalars().all()
        sev = await sk.seviyeler(db, [u.id for u in liste])
        satirlar = [(u.barkod, u.sku, u.ad, u.kategori, u.birim, s.kurus_csv(u.alis_fiyati), s.kurus_csv(u.satis_fiyati), u.kdv_orani,
                     s.miktar_yaz(u.kritik_esik), s.miktar_yaz(sum(sev.get(u.id, {}).values())) if u.stok_takibi else None)
                    for u in liste]
        return _csv_yaniti(s.csv_metni(s.CSV_ALANLARI, satirlar), "urunler.csv")

    @router.get("/urunler/{urun_id}")
    async def urun(urun_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        try:
            u = await sk.urun_bul(db, y.hesap, urun_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        if not u.aktif and not y.stok:
            raise _hata(404, "urun_yok")
        varyantlar = (await db.execute(select(StokUrunleri).where(StokUrunleri.ana_urun_id == u.id, StokUrunleri.hesap_email == y.hesap)
                                       .order_by(StokUrunleri.id))).scalars().all()
        sev = await sk.seviyeler(db, [u.id] + [v.id for v in varyantlar])
        d = _urun_sozlugu(u, sev.get(u.id, {}), y.stok)
        d["varyantlar"] = [_urun_sozlugu(v, sev.get(v.id, {}), y.stok) for v in varyantlar]
        if y.stok:
            hareketler = (await db.execute(select(StokHareketleri).where(StokHareketleri.urun_id == u.id)
                                           .order_by(StokHareketleri.id.desc()).limit(20))).scalars().all()
            d["hareketler"] = [_hareket_sozlugu(h, {u.id: u.ad}) for h in hareketler]
        return d

    # ------------------------------------------------------------- tedarikçiler, hareketler
    @router.get("/tedarikciler")
    async def tedarikciler(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        liste = (await db.execute(select(StokTedarikcileri).where(StokTedarikcileri.hesap_email == y.hesap)
                                  .order_by(StokTedarikcileri.ad))).scalars().all()
        return {"items": [_tedarikci_sozlugu(t) for t in liste]}

    @router.get("/hareketler")
    async def hareketler(request: Request, urun_id: Optional[int] = Query(None), konum_id: Optional[int] = Query(None),
                         tur: Optional[str] = Query(None, max_length=16), bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                         sayfa: int = Query(1, ge=1, le=10000), adet: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        b, e = _aralik(bas, bit, 90)
        gb, ge = s.gun_araligi(b, e)
        kosul = [StokHareketleri.hesap_email == y.hesap, StokHareketleri.zaman >= gb, StokHareketleri.zaman < ge]
        if urun_id:
            kosul.append(StokHareketleri.urun_id == urun_id)
        if konum_id:
            kosul.append(StokHareketleri.konum_id == konum_id)
        if tur:
            kosul.append(StokHareketleri.tur == tur)
        toplam = int((await db.execute(select(func.count(StokHareketleri.id)).where(*kosul))).scalar() or 0)
        liste = (await db.execute(select(StokHareketleri).where(*kosul).order_by(StokHareketleri.id.desc())
                                  .offset((sayfa - 1) * adet).limit(adet))).scalars().all()
        adlar = dict((await db.execute(select(StokUrunleri.id, StokUrunleri.ad).where(
            StokUrunleri.id.in_({h.urun_id for h in liste} or {0})))).all())
        return {"items": [_hareket_sozlugu(h, adlar) for h in liste], "toplam": toplam, "sayfa": sayfa}

    # ------------------------------------------------------------- sayım
    @router.get("/sayimlar")
    async def sayimlar(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        liste = (await db.execute(select(StokSayimlari).where(StokSayimlari.hesap_email == y.hesap)
                                  .order_by(StokSayimlari.id.desc()).limit(50))).scalars().all()
        return {"items": [_sayim_sozlugu(x) for x in liste]}

    @router.get("/sayimlar/{sayim_id}")
    async def sayim(sayim_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        try:
            x = await sk.sayim_bul(db, y.hesap, sayim_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        kalemler = (await db.execute(select(StokSayimKalemleri).where(StokSayimKalemleri.sayim_id == x.id)
                                     .order_by(StokSayimKalemleri.updated_at.desc()))).scalars().all()
        urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(
            StokUrunleri.id.in_({k.urun_id for k in kalemler} or {0})))).scalars().all()}
        sev = await sk.seviyeler(db, list(urunler))
        satirlar = []
        for k in kalemler:
            u = urunler.get(k.urun_id)
            sistem = k.sistem if x.durum != "acik" else sev.get(k.urun_id, {}).get(x.konum_id, 0)
            satirlar.append({"urun_id": k.urun_id, "ad": u.ad if u else "—", "barkod": u.barkod if u else None,
                             "birim": u.birim if u else "adet", "sayilan": s.miktar_yaz(k.sayilan), "sistem": s.miktar_yaz(sistem),
                             "fark": s.miktar_yaz((k.sayilan or 0) - (sistem or 0)), "zaman": s.iso(k.updated_at)})
        return {**_sayim_sozlugu(x), "kalemler": satirlar}

    # ------------------------------------------------------------- kasa
    @router.get("/kasa")
    async def kasa(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y) if not y.ajans else None
        acik = (await db.execute(select(PosKasaOturumlari).where(PosKasaOturumlari.hesap_email == y.hesap,
                                                                 PosKasaOturumlari.durum == "acik"))).scalars().all()
        son = []
        if y.stok:
            son = (await db.execute(select(PosKasaOturumlari).where(PosKasaOturumlari.hesap_email == y.hesap,
                                                                    PosKasaOturumlari.durum == "kapali")
                                    .order_by(PosKasaOturumlari.id.desc()).limit(10))).scalars().all()
        return {"acik": [sk.oturum_sozlugu(o) for o in acik], "son": [sk.oturum_sozlugu(o) for o in son]}

    @router.get("/kasa-oturumlari")
    async def kasa_oturumlari(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                              db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        b, e = _aralik(bas, bit, 30)
        gb, ge = s.gun_araligi(b, e)
        liste = (await db.execute(select(PosKasaOturumlari).where(PosKasaOturumlari.hesap_email == y.hesap,
                                                                  PosKasaOturumlari.acilis_at >= gb, PosKasaOturumlari.acilis_at < ge)
                                  .order_by(PosKasaOturumlari.id.desc()))).scalars().all()
        return {"items": [sk.oturum_sozlugu(o) for o in liste]}

    @router.get("/kasa/{oturum_id}")
    async def kasa_ozeti(oturum_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y) if not y.ajans else None
        try:
            o = await sk.oturum_bul(db, y.hesap, oturum_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        if not y.stok and o.durum != "acik" and o.acan != y.kisi and o.kapatan != y.kisi:
            raise _hata(404, "oturum_yok")
        ozet = s.json_yukle(o.ozet, None) if o.durum == "kapali" and o.ozet else await sk.oturum_ozeti(db, o)
        return {"oturum": sk.oturum_sozlugu(o), "ozet": ozet, "not": s.Z_NOTU_TR}

    # ------------------------------------------------------------- satışlar
    @router.get("/satislar")
    async def satislar(request: Request, oturum_id: Optional[int] = Query(None), bas: Optional[str] = Query(None),
                       bit: Optional[str] = Query(None), ara: Optional[str] = Query(None, max_length=40),
                       sayfa: int = Query(1, ge=1, le=10000), adet: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y) if not y.ajans else None
        kosul = [PosSatislari.hesap_email == y.hesap]
        if oturum_id:
            kosul.append(PosSatislari.oturum_id == oturum_id)
        if not y.stok:
            # Kasiyer yalnız açık kasaların satışlarını görür.
            kosul.append(PosSatislari.oturum_id.in_(select(PosKasaOturumlari.id).where(
                PosKasaOturumlari.hesap_email == y.hesap, PosKasaOturumlari.durum == "acik")))
        elif not oturum_id:
            b, e = _aralik(bas, bit, 30)
            gb, ge = s.gun_araligi(b, e)
            kosul += [PosSatislari.zaman >= gb, PosSatislari.zaman < ge]
        if ara and ara.strip():
            a = ara.strip()
            kosul.append(or_(PosSatislari.no.contains(a), PosSatislari.fatura_no.contains(a)))
        toplam = int((await db.execute(select(func.count(PosSatislari.id)).where(*kosul))).scalar() or 0)
        liste = (await db.execute(select(PosSatislari).where(*kosul).order_by(PosSatislari.id.desc())
                                  .offset((sayfa - 1) * adet).limit(adet))).scalars().all()
        return {"items": [_satis_ozeti(x) for x in liste], "toplam": toplam, "sayfa": sayfa}

    async def _gorunur_satis(db: AsyncSession, y: Yetki, satis_id: int) -> PosSatislari:
        try:
            x = await sk.satis_bul(db, y.hesap, satis_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        if not y.stok and not y.ajans:
            o = await sk.oturum_bul(db, y.hesap, x.oturum_id)
            if o.durum != "acik":
                raise _hata(404, "satis_yok")
        return x

    @router.get("/satislar/{satis_id}")
    async def satis(satis_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y) if not y.ajans else None
        return await _satis_ayrintisi(db, await _gorunur_satis(db, y, satis_id))

    @router.get("/satislar/{satis_id}/fis.pdf")
    async def satis_fis(satis_id: int, request: Request, dil: Optional[str] = Query(None, max_length=5),
                        db: AsyncSession = Depends(get_db)):
        from services.stok_pdf import fis_pdf

        y = kapsam(request)
        _kasa_iste(y) if not y.ajans else None
        x = await _gorunur_satis(db, y, satis_id)
        return _pdf_yaniti(fis_pdf(await _satis_ayrintisi(db, x), dil or "tr"), f"fis-{x.no}.pdf")

    @router.get("/satislar/{satis_id}/fatura.pdf")
    async def satis_fatura(satis_id: int, request: Request, dil: Optional[str] = Query(None, max_length=5),
                           db: AsyncSession = Depends(get_db)):
        from services.stok_pdf import fatura_pdf

        y = kapsam(request)
        _kasa_iste(y) if not y.ajans else None
        x = await _gorunur_satis(db, y, satis_id)
        if not x.fatura_no:
            raise _hata(404, "fatura_yok")
        v = await _satis_ayrintisi(db, x)
        v["alici"] = v.pop("fatura_alici") or {}
        v["fatura_tarihi"] = _tarih_metni(x.fatura_at)
        return _pdf_yaniti(fatura_pdf(v, dil or "tr"), f"fatura-{x.fatura_no}.pdf")

    # ------------------------------------------------------------- raporlar
    @router.get("/raporlar/gun")
    async def rapor_gun(request: Request, tarih: Optional[str] = Query(None), konum_id: Optional[int] = Query(None),
                        db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        gun = _tarih(tarih, "tarih", s.tr_gunu())
        return {**await sk.gun_ozeti(db, y.hesap, gun, konum_id), "not": s.Z_NOTU_TR}

    @router.get("/raporlar/donem")
    async def rapor_donem(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                          konum_id: Optional[int] = Query(None), bicim: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        b, e = _aralik(bas, bit)
        r = await sk.donem_raporu(db, y.hesap, b, e, konum_id)
        if bicim == "csv":
            basliklar = ("tarih", "satis_sayisi", "satis", "iade", "net", "nakit", "kart", "havale", "kdv", "indirim")
            satirlar = [(g["tarih"], g["satis_sayisi"], *(s.kurus_csv(g[a]) for a in basliklar[2:])) for g in r["gunler"]]
            return _csv_yaniti(s.csv_metni(basliklar, satirlar), f"satislar-{b}-{e}.csv")
        return r

    @router.get("/raporlar/kar")
    async def rapor_kar(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                        konum_id: Optional[int] = Query(None), bicim: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        b, e = _aralik(bas, bit)
        r = await sk.kar_raporu(db, y.hesap, b, e, konum_id)
        if bicim == "csv":
            satirlar = [(u["ad"], u["adet"], u["birim"], s.kurus_csv(u["ciro"]), s.kurus_csv(u["maliyet"]), s.kurus_csv(u["kar"]),
                         u["marj"]) for u in r["urunler"]]
            return _csv_yaniti(s.csv_metni(("urun", "miktar", "birim", "ciro_kdv_haric", "maliyet", "kar", "marj_yuzde"), satirlar),
                               f"kar-{b}-{e}.csv")
        return r

    @router.get("/raporlar/stok-degeri")
    async def rapor_stok_degeri(request: Request, konum_id: Optional[int] = Query(None), bicim: Optional[str] = Query(None),
                                db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        r = await sk.stok_degeri(db, y.hesap, konum_id)
        if bicim == "csv":
            satirlar = [(u["barkod"], u["ad"], u["miktar"], u["birim"], s.kurus_csv(u["alis_fiyati"]), s.kurus_csv(u["maliyet_degeri"]),
                         s.kurus_csv(u["satis_degeri"])) for u in r["urunler"]]
            return _csv_yaniti(s.csv_metni(("barkod", "urun", "miktar", "birim", "alis_fiyati", "maliyet_degeri", "satis_degeri"), satirlar),
                               "stok-degeri.csv")
        return r

    @router.get("/raporlar/hareketsiz")
    async def rapor_hareketsiz(request: Request, gun: int = Query(s.HAREKETSIZ_GUN, ge=1, le=730), bicim: Optional[str] = Query(None),
                               db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        r = await sk.hareketsiz(db, y.hesap, gun)
        if bicim == "csv":
            satirlar = [(u["barkod"], u["ad"], u["miktar"], u["birim"], u["son_satis"], u["gun"], s.kurus_csv(u["maliyet_degeri"]))
                        for u in r["urunler"]]
            return _csv_yaniti(s.csv_metni(("barkod", "urun", "miktar", "birim", "son_satis", "gun", "maliyet_degeri"), satirlar),
                               "hareketsiz-urunler.csv")
        return r

    if not yazma:
        return

    # =================================================================== YAZMA (yalnız müşteri)
    @router.put("/ayarlar")
    async def ayarlar_kaydet(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        a = await sk.ayarlar(db, y.hesap)
        try:
            for ad, sinir in (("firma_adi", 160), ("telefon", 32), ("vergi_dairesi", 80)):
                if ad in g:
                    setattr(a, ad, s.bos_ya_da(g.get(ad), ad, sinir))
            if "adres" in g:
                a.adres = s.bos_ya_da(g.get("adres"), "adres", 500, cok_satir=True)
            if "fis_notu" in g:
                a.fis_notu = s.bos_ya_da(g.get("fis_notu"), "fis_notu", 300, cok_satir=True)
            if "eposta" in g:
                a.eposta = s.eposta(g.get("eposta"))
            if "vergi_no" in g:
                a.vergi_no = s.vergi_no_duzelt(g.get("vergi_no"))
            if "para_birimi" in g:
                if g.get("para_birimi") not in s.PARA_BIRIMLERI:
                    raise s.StokHatasi("para_birimi_gecersiz", "para_birimi")
                a.para_birimi = g["para_birimi"]
            if "kdv_oranlari" in g:
                a.kdv_oranlari = None if g.get("kdv_oranlari") in (None, []) else s.json_yaz(s.kdv_oranlari_duzelt(g.get("kdv_oranlari")))
            oranlar = s.kdv_oranlari(a.kdv_oranlari)
            if "varsayilan_kdv" in g:
                a.varsayilan_kdv = s.kdv_duzelt(g.get("varsayilan_kdv"), oranlar, "varsayilan_kdv")
            elif a.varsayilan_kdv not in oranlar:
                a.varsayilan_kdv = oranlar[-1]
            for ad in ("eksi_stok", "kasa_iade", "qr_stok_esitle", "kritik_bildirim"):
                if ad in g:
                    setattr(a, ad, s.evet_hayir(g.get(ad), ad))
            if "kasa_indirim_yuzde" in g:
                a.kasa_indirim_yuzde = s.tam_sayi(g.get("kasa_indirim_yuzde"), "kasa_indirim_yuzde", 0, 100, bos_olabilir=False)
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(a)
        return _ayar_sozlugu(a)

    # ------------------------------------------------------------- konumlar
    @router.post("/konumlar")
    async def konum_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            ad = s.metin(g.get("ad"), "ad", 80, zorunlu=True)
            adres = s.bos_ya_da(g.get("adres"), "adres", 500, cok_satir=True)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        aktifler = await sk.konumlar(db, y.hesap)
        sinir = await sk.modul_ayari(db, y.hesap, "sube_siniri", s.VARSAYILAN_SUBE_SINIRI)
        if len(aktifler) >= sinir:
            raise _hata(403, "sube_siniri", sinir=sinir)
        k = StokKonumlari(hesap_email=y.hesap, ad=ad, adres=adres, varsayilan=False, aktif=True, sira=len(aktifler),
                          created_at=s.simdi())
        db.add(k)
        await db.commit()
        await db.refresh(k)
        return _konum_sozlugu(k)

    @router.put("/konumlar/{konum_id}")
    async def konum_guncelle(konum_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        k = (await db.execute(select(StokKonumlari).where(StokKonumlari.id == konum_id, StokKonumlari.hesap_email == y.hesap))).scalars().first()
        if k is None:
            raise _hata(404, "konum_yok")
        try:
            if "ad" in g:
                k.ad = s.metin(g.get("ad"), "ad", 80, zorunlu=True)
            if "adres" in g:
                k.adres = s.bos_ya_da(g.get("adres"), "adres", 500, cok_satir=True)
            if "sira" in g:
                k.sira = s.tam_sayi(g.get("sira"), "sira", 0, 1000, bos_olabilir=False)
            if "aktif" in g:
                aktif = s.evet_hayir(g.get("aktif"), "aktif")
                if aktif and not k.aktif:
                    sinir = await sk.modul_ayari(db, y.hesap, "sube_siniri", s.VARSAYILAN_SUBE_SINIRI)
                    if len(await sk.konumlar(db, y.hesap)) >= sinir:
                        raise s.StokHatasi("sube_siniri", None, durum=403, sinir=sinir)
                if not aktif and (k.varsayilan or await sk.acik_oturum(db, y.hesap, k.id) is not None):
                    raise s.StokHatasi("konum_kapatilamaz", "aktif", durum=409)
                k.aktif = aktif
            if g.get("varsayilan") is True and k.aktif:
                from sqlalchemy import update as _update

                await db.execute(_update(StokKonumlari).where(StokKonumlari.hesap_email == y.hesap).values(varsayilan=False)
                                 .execution_options(synchronize_session=False))
                k.varsayilan = True
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(k)
        return _konum_sozlugu(k)

    @router.delete("/konumlar/{konum_id}")
    async def konum_sil(konum_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        k = (await db.execute(select(StokKonumlari).where(StokKonumlari.id == konum_id, StokKonumlari.hesap_email == y.hesap))).scalars().first()
        if k is None:
            raise _hata(404, "konum_yok")
        if k.varsayilan:
            raise _hata(409, "konum_kapatilamaz")
        kullanildi = (await db.execute(select(StokHareketleri.id).where(StokHareketleri.konum_id == k.id).limit(1))).first() is not None \
            or (await db.execute(select(PosKasaOturumlari.id).where(PosKasaOturumlari.konum_id == k.id).limit(1))).first() is not None
        if kullanildi:
            if await sk.acik_oturum(db, y.hesap, k.id) is not None:
                raise _hata(409, "konum_kapatilamaz")
            k.aktif = False
            await db.commit()
            return {"ok": True, "pasif": True}
        await db.delete(k)
        await db.commit()
        return {"ok": True, "pasif": False}

    # ------------------------------------------------------------- ürün yazma
    async def _barkod_cakisma(db: AsyncSession, hesap: str, alanlar: Dict[str, Any], haric: Optional[int] = None) -> None:
        for alan in ("barkod", "sku"):
            deger = alanlar.get(alan)
            if not deger:
                continue
            kolon = getattr(StokUrunleri, alan)
            sorgu = select(StokUrunleri.id).where(StokUrunleri.hesap_email == hesap, kolon == deger)
            if haric:
                sorgu = sorgu.where(StokUrunleri.id != haric)
            if (await db.execute(sorgu)).first() is not None:
                raise s.StokHatasi(f"{alan}_kullaniliyor", alan, durum=409)

    @router.post("/barkod-uret")
    async def barkod_uret(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        return {"barkod": await sk.benzersiz_barkod(db, y.hesap)}

    @router.post("/urunler")
    async def urun_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        a = await sk.ayarlar(db, y.hesap)
        oranlar = s.kdv_oranlari(a.kdv_oranlari)
        try:
            alanlar = sk.urun_alanlari(g, oranlar)
            sinir = await sk.modul_ayari(db, y.hesap, "urun_siniri", s.VARSAYILAN_URUN_SINIRI)
            if await sk.urun_sayisi(db, y.hesap) >= sinir:
                raise s.StokHatasi("urun_siniri", None, durum=403, sinir=sinir)
            if not alanlar.get("barkod"):
                alanlar["barkod"] = await sk.benzersiz_barkod(db, y.hesap)
            await _barkod_cakisma(db, y.hesap, alanlar)
            u = StokUrunleri(hesap_email=y.hesap, aktif=True, created_at=s.simdi(), **{**sk.urun_varsayilanlari(a, oranlar), **alanlar})
            db.add(u)
            await db.flush()
            gecis = []
            baslangic = g.get("baslangic_stok")
            if baslangic not in (None, "", 0) and u.stok_takibi:
                miktar = s.miktar_coz(baslangic, "baslangic_stok", u.birim)
                konum = await sk.konum_bul(db, y.hesap, g.get("konum_id"))
                sonra = await sk.stok_degistir(db, y.hesap, u, konum.id, miktar, "giris", kisi=y.kisi, eksi_izin=True,
                                               birim_maliyet=u.alis_fiyati or None, aciklama=None)
                gecis.append(sk.Gecis(u.id, 0, sonra))
            await db.commit()
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "barkod_kullaniliyor", alan="barkod")
        await db.refresh(u)
        await _gecisler(db, y, gecis)
        return _urun_sozlugu(u, (await sk.seviyeler(db, [u.id]))[u.id], True)

    @router.post("/urunler/{urun_id}/varyant")
    async def varyant_ekle(urun_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            ana = await sk.urun_bul(db, y.hesap, urun_id)
            if ana.ana_urun_id:
                ana = await sk.urun_bul(db, y.hesap, ana.ana_urun_id)
            varyant = s.varyant_duzelt(g.get("varyant"))
            if not varyant:
                raise s.StokHatasi("varyant_gecersiz", "varyant")
            sinir = await sk.modul_ayari(db, y.hesap, "urun_siniri", s.VARSAYILAN_URUN_SINIRI)
            if await sk.urun_sayisi(db, y.hesap) >= sinir:
                raise s.StokHatasi("urun_siniri", None, durum=403, sinir=sinir)
            alanlar = {"barkod": s.barkod_duzelt(g.get("barkod")), "sku": s.bos_ya_da(g.get("sku"), "sku", 64)}
            if not alanlar["barkod"]:
                alanlar["barkod"] = await sk.benzersiz_barkod(db, y.hesap)
            await _barkod_cakisma(db, y.hesap, alanlar)
            fiyat = s.kurus(g.get("satis_fiyati"), "satis_fiyati", bos_olabilir=True)
            u = StokUrunleri(hesap_email=y.hesap, ad=s.varyant_adi(ana.ad, varyant), barkod=alanlar["barkod"], sku=alanlar["sku"],
                             kategori=ana.kategori, birim=ana.birim, alis_fiyati=ana.alis_fiyati,
                             satis_fiyati=ana.satis_fiyati if fiyat is None else fiyat, kdv_orani=ana.kdv_orani,
                             kritik_esik=ana.kritik_esik, stok_takibi=ana.stok_takibi, ana_urun_id=ana.id,
                             varyant=s.json_yaz(varyant), aktif=True, created_at=s.simdi())
            db.add(u)
            await db.commit()
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "barkod_kullaniliyor", alan="barkod")
        await db.refresh(u)
        return _urun_sozlugu(u, {}, True)

    @router.put("/urunler/{urun_id}")
    async def urun_guncelle(urun_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        a = await sk.ayarlar(db, y.hesap)
        try:
            u = await sk.urun_bul(db, y.hesap, urun_id)
            alanlar = sk.urun_alanlari(g, s.kdv_oranlari(a.kdv_oranlari), kismi=True, birim_varsayilan=u.birim)
            if "barkod" in alanlar and not alanlar["barkod"]:
                alanlar.pop("barkod")
            await _barkod_cakisma(db, y.hesap, alanlar, haric=u.id)
            if "birim" in alanlar and alanlar["birim"] != u.birim and alanlar["birim"] in s.TAM_BIRIMLER:
                kesirli = (await db.execute(select(StokSeviyeleri.id).where(StokSeviyeleri.urun_id == u.id,
                                                                            StokSeviyeleri.miktar % 1000 != 0))).first()
                if kesirli is not None:
                    raise s.StokHatasi("birim_degismez", "birim", durum=409)
            if "varyant" in g and u.ana_urun_id:
                v = s.varyant_duzelt(g.get("varyant"))
                u.varyant = s.json_yaz(v) if v else None
            if "aktif" in g:
                u.aktif = s.evet_hayir(g.get("aktif"), "aktif")
            for k, v in alanlar.items():
                setattr(u, k, v)
            if "kritik_esik" in alanlar or "stok_takibi" in alanlar:
                u.kritik_at = None  # yeni eşikle yeniden değerlendirilsin
            await db.commit()
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "barkod_kullaniliyor", alan="barkod")
        await db.refresh(u)
        if "kritik_esik" in alanlar or "stok_takibi" in alanlar:
            toplam = await sk.toplam_stok(db, u.id)
            await _gecisler(db, y, [sk.Gecis(u.id, toplam, toplam)])
            await db.refresh(u)
        return _urun_sozlugu(u, (await sk.seviyeler(db, [u.id]))[u.id], True)

    @router.delete("/urunler/{urun_id}")
    async def urun_sil(urun_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        try:
            u = await sk.urun_bul(db, y.hesap, urun_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        kullanildi = (await db.execute(select(StokHareketleri.id).where(StokHareketleri.urun_id == u.id).limit(1))).first() is not None \
            or (await db.execute(select(PosSatisKalemleri.id).where(PosSatisKalemleri.urun_id == u.id).limit(1))).first() is not None
        if kullanildi:
            u.aktif = False
            await db.commit()
            return {"ok": True, "pasif": True}
        from sqlalchemy import delete as _delete
        from sqlalchemy import update as _update

        await db.execute(_delete(StokSeviyeleri).where(StokSeviyeleri.urun_id == u.id))
        await db.execute(_update(StokUrunleri).where(StokUrunleri.ana_urun_id == u.id).values(ana_urun_id=None)
                         .execution_options(synchronize_session=False))
        await db.delete(u)
        await db.commit()
        return {"ok": True, "pasif": False}

    @router.post("/urunler/ice-aktar")
    async def urun_ice_aktar(request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y, _aktarma_hizi)
        bayt = await dosya.read(s.CSV_EN_COK_BAYT + 1)
        try:
            return await sk.csv_ice_aktar(db, y, bayt)
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)

    @router.get("/menu-kaynaklari")
    async def menu_kaynaklari(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        return {"items": await sk.menu_kaynaklari(db, y.hesap)}

    @router.post("/menuden-aktar")
    async def menuden_aktar(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y, _aktarma_hizi)
        g = await _govde(request)
        try:
            return await sk.menuden_aktar(db, y, g.get("magaza_id"))
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)

    # ------------------------------------------------------------- tedarikçi yazma
    def _tedarikci_alanlari(g: Dict[str, Any], kismi: bool) -> Dict[str, Any]:
        alanlar: Dict[str, Any] = {}
        if not kismi or "ad" in g:
            alanlar["ad"] = s.metin(g.get("ad"), "ad", 160, zorunlu=True)
        for ad, sinir in (("yetkili", 120), ("telefon", 32)):
            if not kismi or ad in g:
                alanlar[ad] = s.bos_ya_da(g.get(ad), ad, sinir)
        if not kismi or "eposta" in g:
            alanlar["eposta"] = s.eposta(g.get("eposta"))
        if not kismi or "vergi_no" in g:
            alanlar["vergi_no"] = s.vergi_no_duzelt(g.get("vergi_no"))
        if not kismi or "notlar" in g:
            alanlar["notlar"] = s.bos_ya_da(g.get("notlar"), "notlar", 1000, cok_satir=True)
        if "aktif" in g:
            alanlar["aktif"] = s.evet_hayir(g.get("aktif"), "aktif")
        return alanlar

    @router.post("/tedarikciler")
    async def tedarikci_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            t = StokTedarikcileri(hesap_email=y.hesap, created_at=s.simdi(), **_tedarikci_alanlari(g, False))
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return _tedarikci_sozlugu(t)

    @router.put("/tedarikciler/{tedarikci_id}")
    async def tedarikci_guncelle(tedarikci_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            t = await sk.tedarikci_bul(db, y.hesap, tedarikci_id)
            for k, v in _tedarikci_alanlari(g, True).items():
                setattr(t, k, v)
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(t)
        return _tedarikci_sozlugu(t)

    @router.delete("/tedarikciler/{tedarikci_id}")
    async def tedarikci_sil(tedarikci_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        try:
            t = await sk.tedarikci_bul(db, y.hesap, tedarikci_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        if (await db.execute(select(StokHareketleri.id).where(StokHareketleri.tedarikci_id == t.id).limit(1))).first() is not None:
            t.aktif = False
            await db.commit()
            return {"ok": True, "pasif": True}
        await db.delete(t)
        await db.commit()
        return {"ok": True, "pasif": False}

    # ------------------------------------------------------------- hareket, transfer
    @router.post("/hareketler")
    async def hareket_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            gecisler = await sk.elle_hareket(db, y, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        kritik = await _gecisler(db, y, gecisler)
        return {"ok": True, "kalem": len(gecisler), "kritik": kritik}

    @router.post("/transfer")
    async def transfer(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            kod, _ = await sk.transfer(db, y, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        return {"ok": True, "transfer_kodu": kod}

    # ------------------------------------------------------------- sayım yazma
    @router.post("/sayimlar")
    async def sayim_baslat(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            x = await sk.sayim_baslat(db, y, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        return _sayim_sozlugu(x)

    @router.post("/sayimlar/{sayim_id}/okut")
    async def sayim_okut(sayim_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            x = await sk.sayim_bul(db, y.hesap, sayim_id)
            k = await sk.sayim_kalemi(db, y, x, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        u = await sk.urun_bul(db, y.hesap, k.urun_id)
        sistem = (await sk.seviyeler(db, [u.id]))[u.id].get(x.konum_id, 0)
        return {"urun_id": u.id, "ad": u.ad, "barkod": u.barkod, "birim": u.birim, "sayilan": s.miktar_yaz(k.sayilan),
                "sistem": s.miktar_yaz(sistem), "fark": s.miktar_yaz(k.sayilan - sistem)}

    @router.post("/sayimlar/{sayim_id}/onayla")
    async def sayim_onayla(sayim_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            x = await sk.sayim_bul(db, y.hesap, sayim_id)
            ozet, gecisler = await sk.sayim_onayla(db, y, x, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        await _gecisler(db, y, gecisler)
        await db.refresh(x)
        return {**_sayim_sozlugu(x), "ozet": ozet}

    @router.post("/sayimlar/{sayim_id}/iptal")
    async def sayim_iptal(sayim_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        try:
            x = await sk.sayim_bul(db, y.hesap, sayim_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        if x.durum != "acik":
            raise _hata(409, "sayim_kapali")
        x.durum, x.bitis, x.onaylayan = "iptal", s.simdi(), y.kisi
        await db.commit()
        await db.refresh(x)
        return _sayim_sozlugu(x)

    # ------------------------------------------------------------- kasa yazma
    @router.post("/kasa/ac")
    async def kasa_ac(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            o = await sk.kasa_ac(db, y, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        return sk.oturum_sozlugu(o)

    @router.post("/kasa/{oturum_id}/kapat")
    async def kasa_kapat(oturum_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            o = await sk.oturum_bul(db, y.hesap, oturum_id)
            o = await sk.kasa_kapat(db, y, o, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        return {"oturum": sk.oturum_sozlugu(o), "ozet": s.json_yukle(o.ozet, {}), "not": s.Z_NOTU_TR}

    # ------------------------------------------------------------- satış yazma
    @router.post("/satislar/onizle")
    async def satis_onizle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        g = await _govde(request)
        try:
            return (await sk.sepet_onizle(db, y.hesap, g)).sozluk()
        except s.StokHatasi as h:
            raise _s_hatasi(h)

    @router.post("/satislar")
    async def satis_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            sonuc = await sk.satis_olustur(db, y, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        kritik = await _gecisler(db, y, sonuc.gecisler)
        d = await _satis_ayrintisi(db, sonuc.satis)
        d["tekrar"] = sonuc.tekrar
        d["kritik"] = kritik
        return d

    @router.post("/satislar/{satis_id}/iade")
    async def satis_iade(satis_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        await _iade_yetkisi(db, y)
        g = await _govde(request)
        try:
            x = await _gorunur_satis(db, y, satis_id)
            _, gecisler = await sk.iade_yap(db, y, x, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        await _gecisler(db, y, gecisler)
        return await _satis_ayrintisi(db, await sk.satis_bul(db, y.hesap, satis_id))

    @router.post("/satislar/{satis_id}/iptal")
    async def satis_iptal(satis_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        await _iade_yetkisi(db, y)
        g = await _govde(request)
        try:
            x = await _gorunur_satis(db, y, satis_id)
            _, gecisler = await sk.iptal_et(db, y, x, g)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        await _gecisler(db, y, gecisler)
        return await _satis_ayrintisi(db, await sk.satis_bul(db, y.hesap, satis_id))

    @router.post("/satislar/{satis_id}/fatura")
    async def satis_fatura_kes(satis_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            x = await _gorunur_satis(db, y, satis_id)
            x = await sk.fatura_kes(db, y, x, g)
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        return await _satis_ayrintisi(db, x)

    # ------------------------------------------------------------- alıcılar (kişisel veri: yalnız müşteri paneli)
    @router.get("/alicilar")
    async def alicilar(request: Request, ara: Optional[str] = Query(None, max_length=80), db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        kosul = [PosAlicilari.hesap_email == y.hesap]
        if ara and ara.strip():
            a = ara.strip().lower()
            kosul.append(or_(func.lower(PosAlicilari.ad).contains(a), PosAlicilari.vergi_no.startswith(a),
                             func.lower(PosAlicilari.eposta).contains(a)))
        liste = (await db.execute(select(PosAlicilari).where(*kosul).order_by(PosAlicilari.ad).limit(50))).scalars().all()
        return {"items": [sk.alici_sozlugu(a) for a in liste]}

    @router.post("/alicilar")
    async def alici_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _kasa_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            a = PosAlicilari(hesap_email=y.hesap, created_at=s.simdi(), **sk.alici_alanlari(g))
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return sk.alici_sozlugu(a)

    @router.put("/alicilar/{alici_id}")
    async def alici_guncelle(alici_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        g = await _govde(request)
        try:
            a = await sk.alici_bul(db, y.hesap, alici_id)
            for k, v in sk.alici_alanlari(g, kismi=True).items():
                setattr(a, k, v)
        except s.StokHatasi as h:
            await db.rollback()
            raise _s_hatasi(h)
        await db.commit()
        await db.refresh(a)
        return sk.alici_sozlugu(a)

    @router.delete("/alicilar/{alici_id}")
    async def alici_sil(alici_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        """KVKK: alıcı kaydı silinir; geçmiş satışlarda yalnız bağ kalkar (kesilmiş faturanın alıcı bloğu belgenin parçası)."""
        y = kapsam(request)
        _stok_iste(y)
        _hiz(y)
        try:
            a = await sk.alici_bul(db, y.hesap, alici_id)
        except s.StokHatasi as h:
            raise _s_hatasi(h)
        from sqlalchemy import update as _update

        await db.execute(_update(PosSatislari).where(PosSatislari.alici_id == a.id).values(alici_id=None)
                         .execution_options(synchronize_session=False))
        await db.delete(a)
        await db.commit()
        return {"ok": True}


_uclari_kur(musteri_router, _musteri_yetkisi, yazma=True)
_uclari_kur(yonetici_router, _yonetici_yetkisi, yazma=False)


@musteri_router.get("/ayarlar")
async def ayarlar_oku(request: Request, db: AsyncSession = Depends(get_db)):
    y = _musteri_yetkisi(request)
    _stok_iste(y)
    return _ayar_sozlugu(await sk.ayarlar(db, y.hesap))


@yonetici_router.get("/hesaplar")
async def yonetici_hesaplar(db: AsyncSession = Depends(get_db)):
    """Stok/POS kaydı olan ya da modülü açık hesaplar (destek görünümü için)."""
    from models.workspace_modules import WorkspaceModules

    hesaplar = set((await db.execute(select(StokAyarlari.hesap_email))).scalars().all())
    hesaplar |= set((await db.execute(select(WorkspaceModules.musteri_eposta).where(
        WorkspaceModules.modul_anahtari == MODUL, WorkspaceModules.acik.is_(True)))).scalars().all())
    urunler = dict((await db.execute(select(StokUrunleri.hesap_email, func.count(StokUrunleri.id))
                                     .where(StokUrunleri.aktif.is_(True)).group_by(StokUrunleri.hesap_email))).all())
    satislar = dict((await db.execute(select(PosSatislari.hesap_email, func.count(PosSatislari.id))
                                      .group_by(PosSatislari.hesap_email))).all())
    adlar = dict((await db.execute(select(StokAyarlari.hesap_email, StokAyarlari.firma_adi))).all())
    return {"items": [{"hesap_email": h, "firma_adi": adlar.get(h), "urun": int(urunler.get(h, 0)), "satis": int(satislar.get(h, 0))}
                      for h in sorted(x for x in hesaplar if x)]}


router = (yonetici_router, musteri_router)
