"""Faz 4M — QR menü ve WhatsApp katalog mağazası (tek motor, iki düzen).

Herkese açık:
  GET    /api/v1/menu/{slug}               menü verisi (görünür kategori/ürünler, diller, açık/kapalı,
                                            sipariş ayarları). Pasif → 410, yok → 404. Görüntülenme
                                            yanıttan sonra arka planda yazılır (bot sayılmaz).
  GET    /api/v1/menu/{slug}/ozet?urun=    paylaşım önizlemesi için kısa özet (Pages Function
                                            `functions/menu/[slug].js`); analitiğe yazılmaz.
  POST   /api/v1/menu/{slug}/olay          {tur: urun|sepet, urun_id} analitik
  POST   /api/v1/menu/{slug}/hesapla       sepet + kupon + teslimat → tutarlar (SUNUCU hesaplar)
  POST   /api/v1/menu/{slug}/siparis       WhatsApp siparişi: kaydeder, `wa.me` bağlantısı döndürür.
                                            Hız sınırı + bal küpü (`web_adresi`).
  GET    /api/v1/menu-gorsel/{anahtar}?b=k|b   WebP görsel (değişmez, uzun önbellek)

Yönetici (`/api/v1/qr-menu/yonetim`) — ajansın kendi mağazaları + bütün müşterilerinki.
Müşteri (`/api/v1/menulerim`; modül `qr_menu` YA DA `whatsapp_katalog` açık + hesap izni `menu`):
  GET    /meta                            düzenler (açık modüllere göre), sınırlar, alerjen/etiket
                                            listeleri, AI çeviri açık mı
  GET    /siparis-ozeti                   yeni sipariş sayıları (panel sayacı)
  GET|POST ""                             mağazalar / yeni mağaza
  GET|PUT|DELETE /{mid}                   ayrıntı / güncelle / sil (çöp kutusuna)
  GET    /{mid}/icerik                    kategoriler + ürünler (gizliler dahil)
  POST   /{mid}/kategoriler (+ /sirala), PUT|DELETE /{mid}/kategoriler/{kid}
  POST   /{mid}/urunler (+ /sirala),     PUT|DELETE /{mid}/urunler/{uid}
  POST   /{mid}/gorsel                    görsel yükle (JPEG/PNG/WebP ≤ 5 MB → iki boy WebP)
  POST   /{mid}/ceviri                    "AI ile çevir" (mağaza / kategori / ürün)
  GET|POST /{mid}/kuponlar, PUT|DELETE /{mid}/kuponlar/{cid}
  GET    /{mid}/siparisler                liste (+ saklama süresi dolan kişisel alanları anonimleştirir)
  GET|PUT /{mid}/siparisler/{sid}         ayrıntı (fiş) / durum
  GET    /{mid}/analiz?gun=30             görüntülenme, tekil, en çok bakılan ürünler, sepet, sipariş
  GET    /{mid}/qr?bicim=png|svg&masa=    menünün QR'ı
  POST   /{mid}/masa-qr                   {bas, bit, bicim} → masa numaralı QR'lar (ZIP)
  POST   /{mid}/ice-aktar/onizleme        CSV (çok parçalı `dosya`) → satır satır doğrulama
  POST   /{mid}/ice-aktar                 {satirlar} → kategoriler + ürünler

Kurallar: müşteri yalnız etkin hesabın mağazalarını/siparişlerini görür. Düzen modülü kapalıysa o
düzende mağaza açamaz/değiştiremez (403 `duzen_kapali`); mağaza sınırı (`magaza_siniri`, varsayılan
1) ve ürün sınırı (`urun_siniri`, varsayılan 300) düzenin modül ayarından. Sahibinin modülü kapanan
mağazanın herkese açık sayfası 410.
"""

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.database import db_manager, get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from models.qr_menu import (
    MenuGorselleri,
    MenuKategorileri,
    MenuKuponlari,
    MenuMagazalari,
    MenuOlaylari,
    MenuSiparisleri,
    MenuUrunleri,
)
from services import dinamik_qr as qr
from services import qr_menu as s
from services.dosya_deposu import icerik_konumu
from sqlalchemy import delete, desc, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

IZIN = "menu"
VARSAYILAN_MAGAZA_SINIRI = 1
VARSAYILAN_URUN_SINIRI = 300
EN_COK_MASA = 200
AI_BUTCE_AYARI = "ai_menu_gunluk_butce"
AI_VARSAYILAN_BUTCE = 300
AI_KREDI_AYARI = "menu_ceviri_kredi"
AI_KAPSAM = "menu"


async def _menu_modulu_bekcisi(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """İki modülden biri açıksa geçer (tek motor). Yönetici ve oturumsuz istek etkilenmez."""
    kullanici, yonetici = _yonetici_mi(request)
    if kullanici is None or yonetici:
        return
    from dependencies.hesap_baglami import hesap_baglami
    from services import moduller as modul_servisi

    baglam = hesap_baglami(request)
    if baglam is None or not baglam.hesap_email:
        return
    for anahtar in s.MODULLER:
        if await modul_servisi.modul_acik_mi(db, baglam.hesap_email, anahtar):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"kod": "modul_kapali", "modul": s.MODULLER[0]})


acik_router = APIRouter(prefix="/api/v1/menu", tags=["qr_menu"])
gorsel_router = APIRouter(prefix="/api/v1/menu-gorsel", tags=["qr_menu"])
yonetici_router = APIRouter(
    prefix="/api/v1/qr-menu/yonetim",
    tags=["qr_menu"],
    dependencies=[Depends(yonetici_gerekli)],
)
musteri_router = APIRouter(
    prefix="/api/v1/menulerim",
    tags=["qr_menu"],
    dependencies=[Depends(_menu_modulu_bekcisi), Depends(izin_gerekli(IZIN))],
)

#: Kişi başı (panel): dakikada 60 yazma, 30 görsel, 5 toplu işlem, 20 çeviri.
_yazma_hizi = HizSiniri(60, 60.0)
_gorsel_hizi = HizSiniri(30, 60.0)
_toplu_hizi = HizSiniri(5, 60.0)
_ceviri_hizi = HizSiniri(20, 60.0)
_qr_hizi = HizSiniri(20, 60.0)
#: Ziyaretçi (IP özeti + mağaza): 10 dakikada 5 sipariş; dakikada 60 hesap; dakikada 120 olay.
#: Faz 7H: sipariş sayaçları veritabanında; sepet hesabı / olay sayımı bellekte (sık, düşük riskli).
_siparis_hizi = KaliciHizSiniri("menu-siparis", 5, 600.0)
_hesap_hizi = HizSiniri(60, 60.0)
_olay_hizi = HizSiniri(120, 60.0)
#: Mağaza başına: dakikada 30 sipariş (aynı anda çok IP'den gelen saldırıya karşı).
_magaza_siparis_hizi = KaliciHizSiniri("menu-magaza-siparis", 30, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _gorsel_hizi, _toplu_hizi, _ceviri_hizi, _qr_hizi, _siparis_hizi, _hesap_hizi, _olay_hizi,
              _magaza_siparis_hizi):
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


def _yonetici_kapsami(request: Request) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    return Kapsam(True, None, (getattr(kullanici, "email", "") or "").strip().lower())


def _musteri_kapsami(request: Request) -> Kapsam:
    baglam = izin_iste(request, IZIN)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _menu_hatasi(h: s.MenuHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _an(an: Optional[datetime]) -> Optional[str]:
    if an is None:
        return None
    return (an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)).isoformat()


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    """Faz 7H: herkese açık uçların veritabanı destekli sayacı ((sınırlayıcı, anahtar) çiftleri)."""
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


async def _izinli_duzenler(db: AsyncSession, kapsam: Kapsam) -> List[str]:
    if kapsam.yonetici:
        return list(s.DUZENLER)
    from services import moduller as modul_servisi

    return [d for d in s.DUZENLER if await modul_servisi.modul_acik_mi(db, kapsam.hesap or "", s.DUZEN_MODULU[d])]


async def _modul_ayari(db: AsyncSession, hesap: str, duzen: str, alan: str, varsayilan: int) -> int:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, s.DUZEN_MODULU[duzen], alan)
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else varsayilan


async def _magaza_siniri(db: AsyncSession, kapsam: Kapsam, duzen: str) -> Optional[int]:
    if kapsam.yonetici:
        return None
    return await _modul_ayari(db, kapsam.hesap or "", duzen, "magaza_siniri", VARSAYILAN_MAGAZA_SINIRI)


async def _urun_siniri(db: AsyncSession, kapsam: Kapsam, m: MenuMagazalari) -> Optional[int]:
    if kapsam.yonetici or not m.hesap_email:
        return None
    return await _modul_ayari(db, m.hesap_email, m.duzen, "urun_siniri", VARSAYILAN_URUN_SINIRI)


async def _magaza_sayisi(db: AsyncSession, hesap: Optional[str], duzen: str) -> int:
    sorgu = select(func.count(MenuMagazalari.id)).where(MenuMagazalari.duzen == duzen)
    sorgu = sorgu.where(MenuMagazalari.hesap_email.is_(None)) if hesap is None else sorgu.where(MenuMagazalari.hesap_email == hesap)
    return int((await db.execute(sorgu)).scalar() or 0)


async def _urun_sayisi(db: AsyncSession, mid: int) -> int:
    return int((await db.execute(select(func.count(MenuUrunleri.id)).where(MenuUrunleri.magaza_id == mid))).scalar() or 0)


async def _magaza(db: AsyncSession, mid: int, kapsam: Kapsam) -> MenuMagazalari:
    sorgu = select(MenuMagazalari).where(MenuMagazalari.id == mid)
    if not kapsam.yonetici:
        sorgu = sorgu.where(MenuMagazalari.hesap_email == kapsam.hesap)
    m = (await db.execute(sorgu)).scalars().first()
    if m is None:
        raise _hata(404, "bulunamadi")
    return m


async def _yazilabilir_magaza(db: AsyncSession, mid: int, kapsam: Kapsam) -> MenuMagazalari:
    """Değiştirme işlemleri: müşteride mağazanın düzen modülü açık olmalı."""
    m = await _magaza(db, mid, kapsam)
    if not kapsam.yonetici and m.duzen not in await _izinli_duzenler(db, kapsam):
        raise _hata(403, "duzen_kapali", duzen=m.duzen)
    return m


def _diller(m: MenuMagazalari) -> List[str]:
    return [m.varsayilan_dil] + [d for d in s.json_yukle(m.ek_diller, []) if d != m.varsayilan_dil]


def _saatler(m: MenuMagazalari) -> Dict[str, Any]:
    return s.json_yukle(m.calisma_saatleri, {}) or {}


def _siparis_ayarlari(m: MenuMagazalari) -> Dict[str, Any]:
    return {**s.VARSAYILAN_SIPARIS_AYARLARI, **(s.json_yukle(m.siparis_ayarlari, {}) or {})}


def _para_ayarlari(a: Dict[str, Any]) -> Dict[str, Any]:
    """Kuruş alanlarını JSON çıktısı için ondalığa çevirir."""
    return {**a, "en_dusuk_tutar": s.tl(a.get("en_dusuk_tutar") or 0), "paket_ucreti": s.tl(a.get("paket_ucreti") or 0)}


async def _gorseller(db: AsyncSession, anahtarlar: List[Optional[str]]) -> Dict[str, MenuGorselleri]:
    temiz = sorted({a for a in anahtarlar if a})
    if not temiz:
        return {}
    satirlar = (await db.execute(select(MenuGorselleri).where(MenuGorselleri.anahtar.in_(temiz)))).scalars().all()
    return {g.anahtar: g for g in satirlar}


def _gorsel_sozlugu(anahtar: Optional[str], gorseller: Dict[str, MenuGorselleri]) -> Optional[Dict[str, Any]]:
    if not anahtar:
        return None
    g = gorseller.get(anahtar)
    return {
        "anahtar": anahtar,
        "k": s.gorsel_adresi(anahtar, "k"),
        "b": s.gorsel_adresi(anahtar, "b"),
        "genislik": g.genislik if g else None,
        "yukseklik": g.yukseklik if g else None,
    }


def _magaza_sozlugu(m: MenuMagazalari, gorseller: Dict[str, MenuGorselleri], **ek: Any) -> Dict[str, Any]:
    ayarlar = _siparis_ayarlari(m)
    return {
        "id": m.id,
        "hesap_email": m.hesap_email,
        "slug": m.slug,
        "adres_url": s.menu_adresi(m.slug),
        "duzen": m.duzen,
        "ad": m.ad,
        "aciklama": m.aciklama or "",
        "ceviriler": s.json_yukle(m.ceviriler, {}) or {},
        "logo": _gorsel_sozlugu(m.logo, gorseller),
        "kapak": _gorsel_sozlugu(m.kapak, gorseller),
        "tema_rengi": m.tema_rengi,
        "adres": m.adres or "",
        "telefon": m.telefon or "",
        "whatsapp": m.whatsapp or "",
        "calisma_saatleri": _saatler(m),
        "saat_dilimi": m.saat_dilimi,
        "acik": s.acik_mi(_saatler(m), m.saat_dilimi),
        "para_birimi": m.para_birimi,
        "varsayilan_dil": m.varsayilan_dil,
        "ek_diller": [d for d in _diller(m) if d != m.varsayilan_dil],
        "siparis_ayarlari": _para_ayarlari(ayarlar),
        "saklama_gun": int(m.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN),
        "arama_motoru": bool(m.arama_motoru),
        "aktif": bool(m.aktif),
        "created_at": _an(m.created_at),
        "updated_at": _an(m.updated_at),
        **ek,
    }


def _urun_sozlugu(u: MenuUrunleri, gorseller: Dict[str, MenuGorselleri]) -> Dict[str, Any]:
    gruplar = s.json_yukle(u.secenek_gruplari, []) or []
    return {
        "id": u.id,
        "kategori_id": u.kategori_id,
        "ad": u.ad,
        "aciklama": u.aciklama or "",
        "fiyat": s.tl(u.fiyat),
        "indirimli_fiyat": s.tl(u.indirimli_fiyat) if u.indirimli_fiyat is not None else None,
        "gorsel": _gorsel_sozlugu(u.gorsel, gorseller),
        "secenek_gruplari": [
            {**g, "secenekler": [{**x, "fiyat_farki": s.tl(x.get("fiyat_farki") or 0)} for x in g.get("secenekler", [])]}
            for g in gruplar
        ],
        "etiketler": s.json_yukle(u.etiketler, []) or [],
        "alerjenler": s.json_yukle(u.alerjenler, []) or [],
        "kalori": u.kalori,
        "stokta_yok": bool(u.stokta_yok),
        "gizli": bool(u.gizli),
        "sira": u.sira,
        "ceviriler": s.json_yukle(u.ceviriler, {}) or {},
    }


def _kategori_sozlugu(k: MenuKategorileri, gorseller: Dict[str, MenuGorselleri]) -> Dict[str, Any]:
    return {
        "id": k.id,
        "ad": k.ad,
        "ceviriler": s.json_yukle(k.ceviriler, {}) or {},
        "gorsel": _gorsel_sozlugu(k.gorsel, gorseller),
        "sira": k.sira,
        "gizli": bool(k.gizli),
    }


def _kupon_sozlugu(c: MenuKuponlari, simdi: Optional[datetime] = None) -> Dict[str, Any]:
    _, hata = s.kupon_durumu(c, 10**12, simdi)
    return {
        "id": c.id,
        "kod": c.kod,
        "tur": c.tur,
        "deger": int(c.deger) if c.tur == "yuzde" else s.tl(c.deger),
        "en_dusuk_tutar": s.tl(c.en_dusuk_tutar) if c.en_dusuk_tutar else None,
        "baslangic": _an(c.baslangic),
        "bitis": _an(c.bitis),
        "kullanim_siniri": c.kullanim_siniri,
        "kullanim_sayisi": int(c.kullanim_sayisi or 0),
        "aktif": bool(c.aktif),
        "durum": "gecerli" if hata is None else hata,
    }


def _siparis_sozlugu(o: MenuSiparisleri) -> Dict[str, Any]:
    kalemler = s.json_yukle(o.kalemler, []) or []
    return {
        "id": o.id,
        "siparis_no": o.siparis_no,
        "durum": o.durum,
        "teslimat": o.teslimat,
        "masa": o.masa,
        "musteri_ad": o.musteri_ad,
        "adres": o.adres,
        "siparis_notu": o.siparis_notu,
        "anonim": bool(o.anonim),
        "kalemler": [
            {**k, "birim_fiyat": s.tl(k.get("birim_fiyat") or 0), "tutar": s.tl(k.get("tutar") or 0),
             "secenekler": [{**x, "fiyat_farki": s.tl(x.get("fiyat_farki") or 0)} for x in k.get("secenekler", [])]}
            for k in kalemler
        ],
        "ara_toplam": s.tl(o.ara_toplam),
        "indirim": s.tl(o.indirim),
        "kupon_kodu": o.kupon_kodu,
        "paket_ucreti": s.tl(o.paket_ucreti),
        "toplam": s.tl(o.toplam),
        "para_birimi": o.para_birimi,
        "dil": o.dil,
        "created_at": _an(o.created_at),
        "updated_at": _an(o.updated_at),
    }


async def _gorsel_dogrula(db: AsyncSession, m: MenuMagazalari, anahtar: Any, alan: str) -> Optional[str]:
    """Kayda bağlanacak görsel bu mağazaya yüklenmiş olmalı."""
    if anahtar in (None, ""):
        return None
    if isinstance(anahtar, dict):
        anahtar = anahtar.get("anahtar")
    if not isinstance(anahtar, str):
        raise s.MenuHatasi("gorsel_gecersiz", alan)
    g = (
        await db.execute(
            select(MenuGorselleri.id).where(MenuGorselleri.anahtar == anahtar, MenuGorselleri.magaza_id == m.id)
        )
    ).first()
    if g is None:
        raise s.MenuHatasi("gorsel_gecersiz", alan)
    return anahtar


async def _gorseli_birak(db: AsyncSession, mid: int, anahtar: Optional[str]) -> None:
    """Mağazada hiçbir kayıt kullanmıyorsa görseli (iki boyuyla) siler. Commit ETMEZ."""
    if not anahtar:
        return
    kullanim = 0
    for sutun, model in (
        (MenuMagazalari.logo, MenuMagazalari), (MenuMagazalari.kapak, MenuMagazalari),
        (MenuKategorileri.gorsel, MenuKategorileri), (MenuUrunleri.gorsel, MenuUrunleri),
    ):
        kullanim += int((await db.execute(select(func.count()).select_from(model).where(sutun == anahtar))).scalar() or 0)
    if kullanim:
        return
    g = (await db.execute(select(MenuGorselleri).where(MenuGorselleri.anahtar == anahtar, MenuGorselleri.magaza_id == mid))).scalars().first()
    if g is None:
        return
    from services import dosya_deposu

    for boy in ("k", "b"):
        try:
            await dosya_deposu.sil(db, g.depo, f"menu/{g.anahtar}-{boy}.webp")
        except Exception:  # noqa: BLE001 - içerik silinemese de kayıt düşsün
            logger.warning("Menü görseli silinemedi: %s", g.anahtar)
    await db.delete(g)


# ---------------------------------------------------------------------------
# Kişisel verinin anonimleştirilmesi (istekle tetiklenir — zamanlanmış görev yok)
# ---------------------------------------------------------------------------
async def anonimlestir(db: AsyncSession, m: MenuMagazalari, simdi: Optional[datetime] = None) -> int:
    """Saklama süresi dolan siparişlerin ad/adres/notunu siler. Commit ETMEZ; etkilenen satır sayısı."""
    simdi = simdi or _simdi()
    sinir = simdi - timedelta(days=max(1, int(m.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN)))
    sonuc = await db.execute(
        update(MenuSiparisleri)
        .where(MenuSiparisleri.magaza_id == m.id, MenuSiparisleri.anonim.is_(False), MenuSiparisleri.created_at < sinir)
        .values(musteri_ad=None, adres=None, siparis_notu=None, anonim=True)
        .execution_options(synchronize_session=False)
    )
    return int(sonuc.rowcount or 0)


# ---------------------------------------------------------------------------
# Mağaza
# ---------------------------------------------------------------------------
async def _slug_bos_mu(db: AsyncSession, slug: str, haric: Optional[int] = None) -> bool:
    sorgu = select(MenuMagazalari.id).where(MenuMagazalari.slug == slug)
    if haric is not None:
        sorgu = sorgu.where(MenuMagazalari.id != haric)
    return (await db.execute(sorgu.limit(1))).first() is None


async def _bos_slug(db: AsyncSession, oneri: str) -> str:
    aday = oneri
    for i in range(2, 60):
        if await _slug_bos_mu(db, aday):
            return aday
        aday = f"{oneri[:44]}-{i}"
    return f"{oneri[:40]}-{s.gorsel_anahtari()[:6].lower()}"


async def _magaza_alanlarini_uygula(db: AsyncSession, m: MenuMagazalari, g: Dict[str, Any], yeni: bool) -> List[str]:
    """Gövdedeki alanları doğrulayıp uygular; bırakılan eski görselleri döndürür."""
    birakilan: List[str] = []
    if "ad" in g or yeni:
        m.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
    if "aciklama" in g:
        m.aciklama = s.metin(g.get("aciklama"), "aciklama", 1000, cok_satir=True) or None
    if "slug" in g and not yeni:
        slug = s.slug_duzelt(g.get("slug"))
        if slug != m.slug and not await _slug_bos_mu(db, slug, m.id):
            raise _hata(409, "slug_kullaniliyor", alan="slug")
        m.slug = slug
    if "varsayilan_dil" in g:
        m.varsayilan_dil = s.dil_duzelt(g.get("varsayilan_dil"))
    if "ek_diller" in g or "varsayilan_dil" in g:
        ek = g.get("ek_diller") if "ek_diller" in g else s.json_yukle(m.ek_diller, [])
        m.ek_diller = s.json_yaz(s.ek_diller_duzelt(ek, m.varsayilan_dil or "tr"))
    if "ceviriler" in g:
        m.ceviriler = s.json_yaz(s.ceviriler_duzelt(g.get("ceviriler"), {"ad": 120, "aciklama": 1000}))
    for alan in ("logo", "kapak"):
        if alan in g:
            yeni_anahtar = await _gorsel_dogrula(db, m, g.get(alan), alan)
            eski = getattr(m, alan)
            setattr(m, alan, yeni_anahtar)
            if eski and eski != yeni_anahtar:
                birakilan.append(eski)
    if "tema_rengi" in g:
        m.tema_rengi = s.renk_duzelt(g.get("tema_rengi"))
    if "adres" in g:
        m.adres = s.metin(g.get("adres"), "adres", 300) or None
    if "telefon" in g:
        m.telefon = s.telefon_duzelt(g.get("telefon"), "telefon")
    if "whatsapp" in g:
        m.whatsapp = s.telefon_duzelt(g.get("whatsapp"), "whatsapp")
    if "calisma_saatleri" in g:
        m.calisma_saatleri = s.json_yaz(s.calisma_saatleri_duzelt(g.get("calisma_saatleri")))
    if "saat_dilimi" in g:
        m.saat_dilimi = s.saat_dilimi_duzelt(g.get("saat_dilimi"))
    if "para_birimi" in g:
        m.para_birimi = s.para_birimi_duzelt(g.get("para_birimi"))
    if "siparis_ayarlari" in g:
        m.siparis_ayarlari = s.json_yaz(s.siparis_ayarlari_duzelt(g.get("siparis_ayarlari"), s.json_yukle(m.siparis_ayarlari, {})))
    if "saklama_gun" in g:
        m.saklama_gun = s.tam_sayi(g.get("saklama_gun"), "saklama_gun", 1, 3650, bos_olabilir=False)
    if "arama_motoru" in g:
        m.arama_motoru = bool(g.get("arama_motoru"))
    if "aktif" in g:
        m.aktif = bool(g.get("aktif"))
    return birakilan


async def _magaza_olustur(db: AsyncSession, kapsam: Kapsam, g: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    duzen = g.get("duzen") or "menu"
    if duzen not in s.DUZENLER:
        raise _hata(400, "duzen_gecersiz", alan="duzen")
    if duzen not in await _izinli_duzenler(db, kapsam):
        raise _hata(403, "duzen_kapali", duzen=duzen)
    hesap: Optional[str] = kapsam.hesap
    if kapsam.yonetici:
        ham = str(g.get("hesap_email") or "").strip().lower()
        if ham and not qr.eposta_dogru_mu(ham):
            raise _hata(400, "eposta_gecersiz", alan="hesap_email")
        hesap = ham or None
    sinir = await _magaza_siniri(db, kapsam, duzen)
    if sinir is not None and await _magaza_sayisi(db, hesap, duzen) >= sinir:
        raise _hata(409, "magaza_siniri", sinir=sinir, duzen=duzen)
    try:
        ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
        if g.get("slug"):
            slug = s.slug_duzelt(g.get("slug"))
            if not await _slug_bos_mu(db, slug):
                raise _hata(409, "slug_kullaniliyor", alan="slug")
        else:
            slug = await _bos_slug(db, s.slug_oner(ad))
        m = MenuMagazalari(
            hesap_email=hesap, olusturan_email=kapsam.kisi or None, slug=slug, duzen=duzen, ad=ad,
            tema_rengi="#7c3aed" if duzen == "menu" else "#0f766e", saat_dilimi=qr.VARSAYILAN_SAAT_DILIMI,
            para_birimi="TRY", varsayilan_dil="tr", ek_diller="[]",
            siparis_ayarlari=s.json_yaz({**s.VARSAYILAN_SIPARIS_AYARLARI, **({"masada": False, "paket": True} if duzen == "katalog" else {})}),
            saklama_gun=s.VARSAYILAN_SAKLAMA_GUN, arama_motoru=False, aktif=True,
        )
        govde = {k: v for k, v in g.items() if k not in ("logo", "kapak", "slug", "duzen", "hesap_email")}
        await _magaza_alanlarini_uygula(db, m, govde, yeni=True)
    except s.MenuHatasi as h:
        raise _menu_hatasi(h)
    db.add(m)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    await db.refresh(m)
    return _magaza_sozlugu(m, {})


async def _magaza_guncelle(db: AsyncSession, kapsam: Kapsam, m: MenuMagazalari, g: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_yazma_hizi, kapsam.kisi)
    if "duzen" in g and g["duzen"] != m.duzen:
        duzen = g["duzen"]
        if duzen not in s.DUZENLER:
            raise _hata(400, "duzen_gecersiz", alan="duzen")
        if duzen not in await _izinli_duzenler(db, kapsam):
            raise _hata(403, "duzen_kapali", duzen=duzen)
        sinir = await _magaza_siniri(db, kapsam, duzen)
        if sinir is not None and await _magaza_sayisi(db, m.hesap_email, duzen) >= sinir:
            raise _hata(409, "magaza_siniri", sinir=sinir, duzen=duzen)
        m.duzen = duzen
    try:
        birakilan = await _magaza_alanlarini_uygula(db, m, g, yeni=False)
        await db.flush()
        for anahtar in birakilan:
            await _gorseli_birak(db, m.id, anahtar)
    except s.MenuHatasi as h:
        await db.rollback()
        raise _menu_hatasi(h)
    except HTTPException:
        await db.rollback()
        raise
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "slug_kullaniliyor", alan="slug")
    await db.refresh(m)
    return _magaza_sozlugu(m, await _gorseller(db, [m.logo, m.kapak]))


async def _magaza_sil(db: AsyncSession, m: MenuMagazalari) -> None:
    """Mağaza + kategoriler + ürünler + kuponlar aynı flush'ta (çöp kutusu birlikte yakalar).

    Siparişler silinmiyor (geri alınan mağaza geçmişiyle döner) ama kişisel alanları hemen
    anonimleştiriliyor; analitik satırları kişisel veri taşımıyor.
    """
    cocuklar = []
    for model in (MenuUrunleri, MenuKategorileri, MenuKuponlari):
        cocuklar += list((await db.execute(select(model).where(model.magaza_id == m.id))).scalars().all())
    await db.execute(
        update(MenuSiparisleri)
        .where(MenuSiparisleri.magaza_id == m.id, MenuSiparisleri.anonim.is_(False))
        .values(musteri_ad=None, adres=None, siparis_notu=None, anonim=True)
        .execution_options(synchronize_session=False)
    )
    # Arada sorgu yok: hepsi TEK flush'ta silinsin (çocuklar ebeveynle birlikte yakalanır).
    for kayit in cocuklar:
        await db.delete(kayit)
    await db.delete(m)
    await db.commit()


async def _liste(db: AsyncSession, kapsam: Kapsam, hesap: Optional[str], ara: Optional[str]) -> Dict[str, Any]:
    sorgu = select(MenuMagazalari)
    if not kapsam.yonetici:
        sorgu = sorgu.where(MenuMagazalari.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(MenuMagazalari.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(MenuMagazalari.hesap_email == hesap.strip().lower())
    if ara and ara.strip():
        desen = f"%{ara.strip()[:80].lower()}%"
        sorgu = sorgu.where(or_(
            func.lower(MenuMagazalari.ad).like(desen), func.lower(MenuMagazalari.slug).like(desen),
            func.lower(MenuMagazalari.hesap_email).like(desen),
        ))
    magazalar = (await db.execute(sorgu.order_by(desc(MenuMagazalari.created_at), desc(MenuMagazalari.id)).limit(500))).scalars().all()
    idler = [m.id for m in magazalar]
    urun_sayilari: Dict[int, int] = {}
    yeni_sayilari: Dict[int, int] = {}
    if idler:
        urun_sayilari = dict((await db.execute(
            select(MenuUrunleri.magaza_id, func.count(MenuUrunleri.id)).where(MenuUrunleri.magaza_id.in_(idler)).group_by(MenuUrunleri.magaza_id)
        )).all())
        yeni_sayilari = dict((await db.execute(
            select(MenuSiparisleri.magaza_id, func.count(MenuSiparisleri.id))
            .where(MenuSiparisleri.magaza_id.in_(idler), MenuSiparisleri.durum == "yeni")
            .group_by(MenuSiparisleri.magaza_id)
        )).all())
    gorseller = await _gorseller(db, [m.logo for m in magazalar])
    izinli = await _izinli_duzenler(db, kapsam)
    return {
        "items": [
            _magaza_sozlugu(m, gorseller, urun_sayisi=int(urun_sayilari.get(m.id, 0)),
                            yeni_siparis=int(yeni_sayilari.get(m.id, 0)), duzen_acik=m.duzen in izinli)
            for m in magazalar
        ],
        "toplam": len(magazalar),
    }


async def _meta(db: AsyncSession, kapsam: Kapsam) -> Dict[str, Any]:
    izinli = await _izinli_duzenler(db, kapsam)
    sinirlar: Dict[str, Any] = {}
    for d in s.DUZENLER:
        if kapsam.yonetici:
            sinirlar[d] = {"magaza_siniri": None, "magaza_sayisi": None, "urun_siniri": None}
        else:
            sinirlar[d] = {
                "magaza_siniri": await _magaza_siniri(db, kapsam, d),
                "magaza_sayisi": await _magaza_sayisi(db, kapsam.hesap, d),
                "urun_siniri": await _modul_ayari(db, kapsam.hesap or "", d, "urun_siniri", VARSAYILAN_URUN_SINIRI),
            }
    return {
        "duzenler": izinli,
        "tum_duzenler": list(s.DUZENLER),
        "diller": list(s.DILLER),
        "para_birimleri": list(s.PARA_BIRIMLERI),
        "alerjenler": list(s.ALERJENLER),
        "etiketler": list(s.ETIKETLER),
        "teslimatlar": list(s.TESLIMATLAR),
        "siparis_durumlari": list(s.SIPARIS_DURUMLARI),
        "sinirlar": sinirlar,
        "ai_ceviri": await _ai_kullanilabilir(db),
        "gorsel_en_cok_mb": s.GORSEL_EN_COK_BAYT // (1024 * 1024),
        "csv_en_cok_satir": s.CSV_EN_COK_SATIR,
        "menu_adres_tabani": s.menu_adresi(""),
        "en_cok_masa": EN_COK_MASA,
        "yonetici": kapsam.yonetici,
    }


# ---------------------------------------------------------------------------
# Kategori ve ürün
# ---------------------------------------------------------------------------
async def _kategori(db: AsyncSession, m: MenuMagazalari, kid: Any) -> MenuKategorileri:
    try:
        kid = int(kid)
    except (TypeError, ValueError):
        raise _hata(400, "kategori_gecersiz", alan="kategori_id")
    k = (await db.execute(select(MenuKategorileri).where(MenuKategorileri.id == kid, MenuKategorileri.magaza_id == m.id))).scalars().first()
    if k is None:
        raise _hata(404, "kategori_yok", alan="kategori_id")
    return k


async def _urun(db: AsyncSession, m: MenuMagazalari, uid: int) -> MenuUrunleri:
    u = (await db.execute(select(MenuUrunleri).where(MenuUrunleri.id == uid, MenuUrunleri.magaza_id == m.id))).scalars().first()
    if u is None:
        raise _hata(404, "urun_yok")
    return u


async def _sonraki_sira(db: AsyncSession, model, *kosullar) -> int:
    return int((await db.execute(select(func.max(model.sira)).where(*kosullar))).scalar() or 0) + 1


async def _kategori_uygula(db: AsyncSession, m: MenuMagazalari, k: MenuKategorileri, g: Dict[str, Any], yeni: bool) -> List[str]:
    birakilan = []
    if "ad" in g or yeni:
        k.ad = s.metin(g.get("ad"), "ad", 80, zorunlu=True)
    if "ceviriler" in g:
        k.ceviriler = s.json_yaz(s.ceviriler_duzelt(g.get("ceviriler"), {"ad": 80}))
    if "gorsel" in g:
        yeni_anahtar = await _gorsel_dogrula(db, m, g.get("gorsel"), "gorsel")
        if k.gorsel and k.gorsel != yeni_anahtar:
            birakilan.append(k.gorsel)
        k.gorsel = yeni_anahtar
    if "gizli" in g:
        k.gizli = bool(g.get("gizli"))
    return birakilan


async def _urun_uygula(db: AsyncSession, m: MenuMagazalari, u: MenuUrunleri, g: Dict[str, Any], yeni: bool) -> List[str]:
    birakilan = []
    if "kategori_id" in g or yeni:
        u.kategori_id = (await _kategori(db, m, g.get("kategori_id"))).id
    if "ad" in g or yeni:
        u.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
    if "aciklama" in g:
        u.aciklama = s.metin(g.get("aciklama"), "aciklama", 1000, cok_satir=True) or None
    if "fiyat" in g or yeni:
        u.fiyat = s.kurusa_cevir(g.get("fiyat"), "fiyat")
    if "indirimli_fiyat" in g:
        u.indirimli_fiyat = s.kurusa_cevir(g.get("indirimli_fiyat"), "indirimli_fiyat", bos_olabilir=True)
    if u.indirimli_fiyat is not None and u.indirimli_fiyat >= u.fiyat:
        raise s.MenuHatasi("indirimli_fiyat_buyuk", "indirimli_fiyat")
    if "gorsel" in g:
        yeni_anahtar = await _gorsel_dogrula(db, m, g.get("gorsel"), "gorsel")
        if u.gorsel and u.gorsel != yeni_anahtar:
            birakilan.append(u.gorsel)
        u.gorsel = yeni_anahtar
    if "secenek_gruplari" in g:
        u.secenek_gruplari = s.json_yaz(s.secenek_gruplari_duzelt(g.get("secenek_gruplari")))
    if "etiketler" in g:
        u.etiketler = s.json_yaz(s.etiketleri_coz(g.get("etiketler")))
    if "alerjenler" in g:
        u.alerjenler = s.json_yaz(s.alerjenleri_coz(g.get("alerjenler")))
    if "kalori" in g:
        u.kalori = s.tam_sayi(g.get("kalori"), "kalori", 0, 20000)
    if "stokta_yok" in g:
        u.stokta_yok = bool(g.get("stokta_yok"))
    if "gizli" in g:
        u.gizli = bool(g.get("gizli"))
    if "ceviriler" in g:
        u.ceviriler = s.json_yaz(s.ceviriler_duzelt(g.get("ceviriler"), {"ad": 120, "aciklama": 1000}))
    return birakilan


async def _icerik(db: AsyncSession, m: MenuMagazalari, kapsam: Kapsam) -> Dict[str, Any]:
    kategoriler = (await db.execute(
        select(MenuKategorileri).where(MenuKategorileri.magaza_id == m.id).order_by(MenuKategorileri.sira, MenuKategorileri.id)
    )).scalars().all()
    urunler = (await db.execute(
        select(MenuUrunleri).where(MenuUrunleri.magaza_id == m.id).order_by(MenuUrunleri.sira, MenuUrunleri.id)
    )).scalars().all()
    gorseller = await _gorseller(db, [k.gorsel for k in kategoriler] + [u.gorsel for u in urunler])
    return {
        "kategoriler": [_kategori_sozlugu(k, gorseller) for k in kategoriler],
        "urunler": [_urun_sozlugu(u, gorseller) for u in urunler],
        "urun_sayisi": len(urunler),
        "urun_siniri": await _urun_siniri(db, kapsam, m),
    }


# ---------------------------------------------------------------------------
# Yapay zekâ çevirisi
# ---------------------------------------------------------------------------
def _ai_hazir() -> bool:
    """Sağlayıcı yapılandırılmış mı (ya da test ortamının sahte yanıtı açık mı)?"""
    from services import yapay_zeka as ai

    if ai.sahte_ai_acik_mi():
        return True
    try:
        from services.aihub import AIHubService

        return AIHubService().client is not None
    except Exception:  # noqa: BLE001
        return False


async def _ai_butcesi(db: AsyncSession) -> int:
    from services import yapay_zeka as ai

    return ai.tam_sayi(await ai.ayar_oku(db, AI_BUTCE_AYARI), AI_VARSAYILAN_BUTCE, 0, 10_000_000)


async def _ai_kullanilabilir(db: AsyncSession) -> bool:
    if not _ai_hazir():
        return False
    from services import yapay_zeka as ai

    butce = await _ai_butcesi(db)
    if butce <= 0:
        return True
    try:
        satir = await ai._bugunku_satir(db, AI_KAPSAM)
    except Exception:  # noqa: BLE001
        return True
    return satir is None or int(satir.istek or 0) < butce


def _ceviri_kaynagi(tur: str, kayit: Any) -> Tuple[Dict[str, str], Dict[str, int]]:
    """Çevrilecek metinler (anahtar → metin) ve uzunluk sınırları."""
    metinler: Dict[str, str] = {}
    sinirlar: Dict[str, int] = {}
    metinler["ad"] = kayit.ad
    sinirlar["ad"] = 120 if tur != "kategori" else 80
    if tur in ("magaza", "urun") and getattr(kayit, "aciklama", None):
        metinler["aciklama"] = kayit.aciklama
        sinirlar["aciklama"] = 1000
    if tur == "urun":
        for g in s.json_yukle(kayit.secenek_gruplari, []) or []:
            metinler[f"g.{g['id']}"] = g["ad"]
            sinirlar[f"g.{g['id']}"] = 60
            for x in g.get("secenekler", []):
                metinler[f"s.{g['id']}.{x['id']}"] = x["ad"]
                sinirlar[f"s.{g['id']}.{x['id']}"] = 60
    return metinler, sinirlar


def _ceviriyi_uygula(tur: str, kayit: Any, sonuc: Dict[str, Dict[str, str]]) -> None:
    ceviriler = s.json_yukle(kayit.ceviriler, {}) or {}
    for dil, degerler in sonuc.items():
        hedef = dict(ceviriler.get(dil) or {})
        for alan in ("ad", "aciklama"):
            if degerler.get(alan):
                hedef[alan] = degerler[alan]
        if hedef:
            ceviriler[dil] = hedef
    kayit.ceviriler = s.json_yaz(ceviriler)
    if tur == "urun":
        gruplar = s.json_yukle(kayit.secenek_gruplari, []) or []
        for g in gruplar:
            for dil, degerler in sonuc.items():
                if degerler.get(f"g.{g['id']}"):
                    g.setdefault("ceviriler", {})[dil] = degerler[f"g.{g['id']}"]
                for x in g.get("secenekler", []):
                    if degerler.get(f"s.{g['id']}.{x['id']}"):
                        x.setdefault("ceviriler", {})[dil] = degerler[f"s.{g['id']}.{x['id']}"]
        kayit.secenek_gruplari = s.json_yaz(gruplar)


async def _cevir(db: AsyncSession, kapsam: Kapsam, m: MenuMagazalari, g: Dict[str, Any]) -> Dict[str, Any]:
    from services import yapay_zeka as ai

    tur = g.get("tur")
    if tur not in ("magaza", "kategori", "urun"):
        raise _hata(400, "gecersiz", alan="tur")
    ek = [d for d in _diller(m) if d != m.varsayilan_dil]
    istenen = g.get("diller") or ek
    if not isinstance(istenen, list):
        raise _hata(400, "dil_gecersiz", alan="diller")
    diller = [d for d in istenen if d in ek]
    if not diller:
        raise _hata(400, "ek_dil_yok", alan="diller")
    if tur == "magaza":
        kayit: Any = m
    elif tur == "kategori":
        kayit = await _kategori(db, m, g.get("id"))
    else:
        try:
            kayit = await _urun(db, m, int(g.get("id")))
        except (TypeError, ValueError):
            raise _hata(400, "gecersiz", alan="id")
    if not _ai_hazir():
        raise _hata(503, "ai_kapali")
    _hiz(_ceviri_hizi, kapsam.kisi)
    butce = await _ai_butcesi(db)
    if not await ai.sayac_artir(db, AI_KAPSAM, butce if butce > 0 else None):
        raise _hata(429, "gunluk_butce")

    # İsteğe bağlı kredi (site ayarı `menu_ceviri_kredi`; varsayılan 0 = ücretsiz). Önce düş, hata olursa iade.
    harcama = None
    kredi_miktari = ai.tam_sayi(await ai.ayar_oku(db, AI_KREDI_AYARI, "0"), 0, 0, 1000) if not kapsam.yonetici else 0
    hesap = m.hesap_email
    if kredi_miktari > 0 and hesap:
        from services import kredi

        try:
            harcama, _ = await kredi.harca(db, eposta=hesap, saat=kredi_miktari, aciklama=f"Menü çevirisi: {m.ad}",
                                           olusturan=kapsam.kisi)
        except HTTPException as h:
            if h.status_code == status.HTTP_409_CONFLICT:
                raise _hata(402, "kredi_yetersiz", gerekli=kredi_miktari)
            raise

    metinler, sinirlar = _ceviri_kaynagi(tur, kayit)
    try:
        yanit = await ai.metin_uret(
            s.ceviri_istemi(m.varsayilan_dil, diller, metinler),
            model=ai.varsayilan_model(), max_tokens=3000, temperature=0.2, amac="menu_ceviri",
        )
        sonuc = (
            s.sahte_ceviri(diller, metinler) if yanit.sahte
            else s.ceviri_yanitini_coz(yanit.icerik, diller, metinler.keys(), sinirlar)
        )
    except (ai.YapayZekaHatasi, s.MenuHatasi) as h:
        if harcama is not None and hesap:
            from services import kredi

            try:
                await kredi.yukle(db, eposta=hesap, saat=kredi_miktari, tur="iade", aciklama="Menü çevirisi yapılamadı — iade",
                                  kaynak_ref=f"menu_ceviri_iade:{harcama.id}", olusturan=kapsam.kisi)
            except Exception:  # noqa: BLE001
                logger.exception("Menü çevirisi kredisi iade edilemedi")
        if isinstance(h, ai.YapayZekaHatasi):
            raise _hata(h.durum, h.kod)
        raise _menu_hatasi(h)
    _ceviriyi_uygula(tur, kayit, sonuc)
    await db.commit()
    await ai.token_ekle(db, AI_KAPSAM, yanit)
    await db.refresh(kayit)
    if tur == "magaza":
        return {"tur": tur, "diller": sorted(sonuc), "kayit": _magaza_sozlugu(m, await _gorseller(db, [m.logo, m.kapak]))}
    gorseller = await _gorseller(db, [kayit.gorsel])
    return {
        "tur": tur,
        "diller": sorted(sonuc),
        "kayit": _kategori_sozlugu(kayit, gorseller) if tur == "kategori" else _urun_sozlugu(kayit, gorseller),
    }


# ---------------------------------------------------------------------------
# Kupon
# ---------------------------------------------------------------------------
def _tarih(ham: Any, alan: str) -> Optional[datetime]:
    if ham in (None, ""):
        return None
    if not isinstance(ham, str):
        raise s.MenuHatasi("tarih_gecersiz", alan)
    try:
        an = datetime.fromisoformat(ham.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise s.MenuHatasi("tarih_gecersiz", alan) from exc
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _kupon_uygula(c: MenuKuponlari, g: Dict[str, Any], yeni: bool) -> None:
    if "kod" in g or yeni:
        c.kod = s.kupon_kodu_duzelt(g.get("kod"))
    if "tur" in g or yeni:
        if g.get("tur") not in ("yuzde", "tutar"):
            raise s.MenuHatasi("kupon_turu_gecersiz", "tur")
        c.tur = g["tur"]
    if "deger" in g or yeni or "tur" in g:
        ham = g.get("deger") if "deger" in g else (c.deger if c.tur == "yuzde" else s.tl(c.deger))
        if c.tur == "yuzde":
            c.deger = s.tam_sayi(ham, "deger", 1, 100, bos_olabilir=False)
        else:
            deger = s.kurusa_cevir(ham, "deger")
            if not deger:
                raise s.MenuHatasi("aralik_disi", "deger", en_az=0.01)
            c.deger = deger
    if "en_dusuk_tutar" in g:
        c.en_dusuk_tutar = s.kurusa_cevir(g.get("en_dusuk_tutar"), "en_dusuk_tutar", bos_olabilir=True) or None
    if "baslangic" in g:
        c.baslangic = _tarih(g.get("baslangic"), "baslangic")
    if "bitis" in g:
        c.bitis = _tarih(g.get("bitis"), "bitis")
    if c.baslangic and c.bitis and c.bitis <= c.baslangic:
        raise s.MenuHatasi("bitis_once", "bitis")
    if "kullanim_siniri" in g:
        c.kullanim_siniri = s.tam_sayi(g.get("kullanim_siniri"), "kullanim_siniri", 1, 1_000_000)
    if "aktif" in g:
        c.aktif = bool(g.get("aktif"))


# ---------------------------------------------------------------------------
# Analiz
# ---------------------------------------------------------------------------
async def _analiz(db: AsyncSession, m: MenuMagazalari, gun: int) -> Dict[str, Any]:
    O = MenuOlaylari
    bugun = _simdi().date()
    bas = (bugun - timedelta(days=gun - 1)).isoformat()
    insan = (O.magaza_id == m.id, O.bot.is_(False), O.gun >= bas)

    async def say(tur: str, tekil: bool = False) -> int:
        sayac = func.count(func.distinct(O.ip_ozeti)) if tekil else func.count(O.id)
        return int((await db.execute(select(sayac).where(*insan, O.tur == tur))).scalar() or 0)

    gunluk_ham = {
        g: (int(n), int(t))
        for g, n, t in (await db.execute(
            select(O.gun, func.count(O.id), func.count(func.distinct(O.ip_ozeti)))
            .where(*insan, O.tur == "goruntuleme").group_by(O.gun)
        )).all()
    }
    gunluk = []
    for i in range(gun):
        g = (bugun - timedelta(days=gun - 1 - i)).isoformat()
        n, t = gunluk_ham.get(g, (0, 0))
        gunluk.append({"gun": g, "goruntuleme": n, "tekil": t})
    sayi = func.count(O.id)
    en_cok = (await db.execute(
        select(O.urun_id, sayi).where(*insan, O.tur == "urun", O.urun_id.is_not(None)).group_by(O.urun_id).order_by(desc(sayi)).limit(10)
    )).all()
    sepet = dict((await db.execute(
        select(O.urun_id, func.count(O.id)).where(*insan, O.tur == "sepet", O.urun_id.is_not(None)).group_by(O.urun_id)
    )).all())
    adlar = {}
    if en_cok:
        adlar = dict((await db.execute(
            select(MenuUrunleri.id, MenuUrunleri.ad).where(MenuUrunleri.id.in_([u for u, _ in en_cok]))
        )).all())
    siparis_tutari = int((await db.execute(
        select(func.coalesce(func.sum(MenuSiparisleri.toplam), 0)).where(
            MenuSiparisleri.magaza_id == m.id, MenuSiparisleri.durum != "iptal",
            MenuSiparisleri.created_at >= datetime.combine(bugun - timedelta(days=gun - 1), datetime.min.time(), tzinfo=timezone.utc),
        )
    )).scalar() or 0)
    return {
        "gun": gun,
        "goruntuleme": await say("goruntuleme"),
        "tekil": await say("goruntuleme", tekil=True),
        "urun_goruntuleme": await say("urun"),
        "sepete_ekleme": await say("sepet"),
        "siparis": await say("siparis"),
        "siparis_tutari": s.tl(siparis_tutari),
        "para_birimi": m.para_birimi,
        "bot": int((await db.execute(
            select(func.count(O.id)).where(O.magaza_id == m.id, O.bot.is_(True), O.gun >= bas)
        )).scalar() or 0),
        "gunluk": gunluk,
        "en_cok_bakilan": [
            {"urun_id": u, "ad": adlar.get(u, f"#{u}"), "goruntuleme": int(n), "sepet": int(sepet.get(u, 0))}
            for u, n in en_cok
        ],
    }


# ---------------------------------------------------------------------------
# QR (menü ve masalar) — Faz 4Q üreticisi
# ---------------------------------------------------------------------------
QR_TASARIMI = {**qr.VARSAYILAN_TASARIM, "hata_duzeltme": "M", "boyut": 768}


def _masa_adresi(m: MenuMagazalari, masa: Optional[int]) -> str:
    adres = s.menu_adresi(m.slug)
    return f"{adres}?masa={masa}" if masa is not None else adres


def _qr_gorsel(m: MenuMagazalari, masa: Optional[int], bicim: str):
    tasarim = dict(QR_TASARIMI)
    return (qr.png_ciz if bicim == "png" else qr.svg_ciz)(_masa_adresi(m, masa), tasarim, None)


# ---------------------------------------------------------------------------
# CSV içe aktarma
# ---------------------------------------------------------------------------
async def _ice_aktar_onizleme(db: AsyncSession, kapsam: Kapsam, m: MenuMagazalari, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_toplu_hizi, kapsam.kisi)
    bayt = await dosya.read(s.CSV_EN_COK_BAYT + 1)
    try:
        hamlar = s.csv_coz(bayt)
    except s.MenuHatasi as h:
        raise _menu_hatasi(h)
    mevcut = {k.ad.strip().lower() for k in (await db.execute(select(MenuKategorileri).where(MenuKategorileri.magaza_id == m.id))).scalars().all()}
    satirlar = []
    yeni_kategoriler: List[str] = []
    for i, ham in enumerate(hamlar, start=2):  # 1. satır başlık
        satir: Dict[str, Any] = {"satir": i, "gecerli": True, "hata": None, "veri": None,
                                 "ham": {k: str(v)[:200] for k, v in ham.items() if k in ("kategori", "ad", "aciklama", "fiyat", "etiketler")}}
        try:
            veri = s.csv_satiri(ham)
            satir["veri"] = {**veri, "fiyat": s.tl(veri["fiyat"]),
                             "indirimli_fiyat": s.tl(veri["indirimli_fiyat"]) if veri["indirimli_fiyat"] is not None else None}
            anahtar = veri["kategori"].strip().lower()
            if anahtar not in mevcut and veri["kategori"] not in yeni_kategoriler:
                yeni_kategoriler.append(veri["kategori"])
        except s.MenuHatasi as h:
            satir["gecerli"] = False
            satir["hata"] = h.detay()
        satirlar.append(satir)
    sinir = await _urun_siniri(db, kapsam, m)
    kalan = None if sinir is None else max(0, sinir - await _urun_sayisi(db, m.id))
    return {
        "satirlar": satirlar,
        "toplam": len(satirlar),
        "gecerli": sum(1 for x in satirlar if x["gecerli"]),
        "hatali": sum(1 for x in satirlar if not x["gecerli"]),
        "yeni_kategoriler": yeni_kategoriler,
        "kalan_hak": kalan,
    }


async def _ice_aktar(db: AsyncSession, kapsam: Kapsam, m: MenuMagazalari, g: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_toplu_hizi, kapsam.kisi)
    satirlar = g.get("satirlar")
    if not isinstance(satirlar, list) or not satirlar:
        raise _hata(400, "satir_yok")
    if len(satirlar) > s.CSV_EN_COK_SATIR:
        raise _hata(400, "cok_satir", en_cok=s.CSV_EN_COK_SATIR)
    sinir = await _urun_siniri(db, kapsam, m)
    kalan = None if sinir is None else max(0, sinir - await _urun_sayisi(db, m.id))
    kategoriler = {k.ad.strip().lower(): k for k in (await db.execute(select(MenuKategorileri).where(MenuKategorileri.magaza_id == m.id))).scalars().all()}
    kategori_sirasi = await _sonraki_sira(db, MenuKategorileri, MenuKategorileri.magaza_id == m.id)
    urun_sirasi = await _sonraki_sira(db, MenuUrunleri, MenuUrunleri.magaza_id == m.id)
    olusturulan = 0
    yeni_kategori = 0
    hatalar = []
    for i, ham in enumerate(satirlar):
        satir_no = ham.get("satir", i + 1) if isinstance(ham, dict) else i + 1
        try:
            if not isinstance(ham, dict):
                raise s.MenuHatasi("gecersiz", None)
            veri = s.csv_satiri(ham.get("veri") if isinstance(ham.get("veri"), dict) else ham)
            if kalan is not None and olusturulan >= kalan:
                raise s.MenuHatasi("urun_siniri", None, sinir=sinir)
        except s.MenuHatasi as h:
            hatalar.append({"satir": satir_no, **h.detay()})
            continue
        anahtar = veri["kategori"].strip().lower()
        k = kategoriler.get(anahtar)
        if k is None:
            k = MenuKategorileri(magaza_id=m.id, ad=veri["kategori"], sira=kategori_sirasi, gizli=False)
            kategori_sirasi += 1
            db.add(k)
            await db.flush()
            kategoriler[anahtar] = k
            yeni_kategori += 1
        db.add(MenuUrunleri(
            magaza_id=m.id, kategori_id=k.id, ad=veri["ad"], aciklama=veri["aciklama"] or None, fiyat=veri["fiyat"],
            indirimli_fiyat=veri["indirimli_fiyat"], etiketler=s.json_yaz(veri["etiketler"]),
            alerjenler=s.json_yaz(veri["alerjenler"]), kalori=veri["kalori"], secenek_gruplari="[]",
            stokta_yok=False, gizli=False, sira=urun_sirasi,
        ))
        urun_sirasi += 1
        olusturulan += 1
    await db.commit()
    return {"olusturulan": olusturulan, "yeni_kategori": yeni_kategori, "hatalar": hatalar}


# ---------------------------------------------------------------------------
# Görsel yükleme
# ---------------------------------------------------------------------------
async def _gorsel_yukle(db: AsyncSession, kapsam: Kapsam, m: MenuMagazalari, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_gorsel_hizi, kapsam.kisi)
    bayt = await dosya.read(s.GORSEL_EN_COK_BAYT + 1)
    try:
        hazir = s.gorsel_hazirla(bayt)
    except s.MenuHatasi as h:
        raise _menu_hatasi(h)
    from services import dosya_deposu

    anahtar = s.gorsel_anahtari()
    try:
        depo = await dosya_deposu.yaz(db, f"menu/{anahtar}-b.webp", hazir.buyuk, "image/webp")
        await dosya_deposu.yaz(db, f"menu/{anahtar}-k.webp", hazir.kucuk, "image/webp")
    except dosya_deposu.DepoHatasi:
        await db.rollback()
        raise _hata(502, "depo_hatasi")
    g = MenuGorselleri(magaza_id=m.id, anahtar=anahtar, depo=depo, genislik=hazir.genislik, yukseklik=hazir.yukseklik,
                       boyut=len(hazir.buyuk) + len(hazir.kucuk))
    db.add(g)
    await db.commit()
    return {**(_gorsel_sozlugu(anahtar, {anahtar: g}) or {}), "boyut": g.boyut}


# ---------------------------------------------------------------------------
# Uçlar — yönetici ve müşteri aynı işleyicileri kendi kapsamlarıyla kullanıyor.
# Sabit yollar `/{mid}`'den ÖNCE tanımlı.
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        return await _meta(db, kapsam_al(request))

    @router.get("/siparis-ozeti")
    async def siparis_ozeti(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = (
            select(MenuSiparisleri.magaza_id, func.count(MenuSiparisleri.id))
            .join(MenuMagazalari, MenuMagazalari.id == MenuSiparisleri.magaza_id)
            .where(MenuSiparisleri.durum == "yeni")
        )
        if not kapsam.yonetici:
            sorgu = sorgu.where(MenuMagazalari.hesap_email == kapsam.hesap)
        sayilar = {int(mid): int(n) for mid, n in (await db.execute(sorgu.group_by(MenuSiparisleri.magaza_id))).all()}
        return {"yeni": sum(sayilar.values()), "magazalar": sayilar}

    @router.get("")
    async def liste(request: Request, hesap: Optional[str] = Query(None), ara: Optional[str] = Query(None),
                    db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, hesap if kapsam.yonetici else None, ara)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _magaza_olustur(db, kapsam_al(request), govde)

    @router.get("/{mid}")
    async def ayrinti(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _magaza(db, mid, kapsam)
        izinli = await _izinli_duzenler(db, kapsam)
        return _magaza_sozlugu(m, await _gorseller(db, [m.logo, m.kapak]), duzen_acik=m.duzen in izinli,
                               urun_sayisi=await _urun_sayisi(db, m.id))

    @router.put("/{mid}")
    async def guncelle(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _magaza_guncelle(db, kapsam, await _yazilabilir_magaza(db, mid, kapsam), govde)

    @router.delete("/{mid}")
    async def sil(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        await _magaza_sil(db, await _magaza(db, mid, kapsam))
        return {"ok": True}

    @router.get("/{mid}/icerik")
    async def icerik(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _icerik(db, await _magaza(db, mid, kapsam), kapsam)

    # --- Kategoriler ---
    @router.post("/{mid}/kategoriler/sirala")
    async def kategori_sirala(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        idler = govde.get("idler")
        if not isinstance(idler, list) or len(idler) > 500:
            raise _hata(400, "gecersiz", alan="idler")
        kayitlar = {k.id: k for k in (await db.execute(select(MenuKategorileri).where(MenuKategorileri.magaza_id == m.id))).scalars().all()}
        for sira, kid in enumerate(idler, start=1):
            k = kayitlar.get(kid) if isinstance(kid, int) else None
            if k is not None:
                k.sira = sira
        await db.commit()
        return {"ok": True}

    @router.post("/{mid}/kategoriler")
    async def kategori_olustur(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        sayi = int((await db.execute(select(func.count(MenuKategorileri.id)).where(MenuKategorileri.magaza_id == m.id))).scalar() or 0)
        if sayi >= 100:
            raise _hata(409, "kategori_siniri", sinir=100)
        k = MenuKategorileri(magaza_id=m.id, sira=await _sonraki_sira(db, MenuKategorileri, MenuKategorileri.magaza_id == m.id), gizli=False)
        try:
            await _kategori_uygula(db, m, k, govde, yeni=True)
        except s.MenuHatasi as h:
            raise _menu_hatasi(h)
        db.add(k)
        await db.commit()
        await db.refresh(k)
        return _kategori_sozlugu(k, await _gorseller(db, [k.gorsel]))

    @router.put("/{mid}/kategoriler/{kid}")
    async def kategori_guncelle(mid: int, kid: int, request: Request, govde: Dict[str, Any] = Body(...),
                                db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        k = await _kategori(db, m, kid)
        try:
            birakilan = await _kategori_uygula(db, m, k, govde, yeni=False)
            await db.flush()
            for a in birakilan:
                await _gorseli_birak(db, m.id, a)
        except s.MenuHatasi as h:
            await db.rollback()
            raise _menu_hatasi(h)
        await db.commit()
        await db.refresh(k)
        return _kategori_sozlugu(k, await _gorseller(db, [k.gorsel]))

    @router.delete("/{mid}/kategoriler/{kid}")
    async def kategori_sil(mid: int, kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        k = await _kategori(db, m, kid)
        urun = (await db.execute(select(MenuUrunleri.id).where(MenuUrunleri.kategori_id == k.id).limit(1))).first()
        if urun is not None:
            raise _hata(409, "kategori_dolu")
        gorsel = k.gorsel
        await db.delete(k)
        await db.flush()
        await _gorseli_birak(db, m.id, gorsel)
        await db.commit()
        return {"ok": True}

    # --- Ürünler ---
    @router.post("/{mid}/urunler/sirala")
    async def urun_sirala(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        idler = govde.get("idler")
        if not isinstance(idler, list) or len(idler) > 2000:
            raise _hata(400, "gecersiz", alan="idler")
        kayitlar = {u.id: u for u in (await db.execute(select(MenuUrunleri).where(MenuUrunleri.magaza_id == m.id, MenuUrunleri.id.in_([i for i in idler if isinstance(i, int)])))).scalars().all()}
        for sira, uid in enumerate(idler, start=1):
            u = kayitlar.get(uid) if isinstance(uid, int) else None
            if u is not None:
                u.sira = sira
        await db.commit()
        return {"ok": True}

    @router.post("/{mid}/urunler")
    async def urun_olustur(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        sinir = await _urun_siniri(db, kapsam, m)
        if sinir is not None and await _urun_sayisi(db, m.id) >= sinir:
            raise _hata(409, "urun_siniri", sinir=sinir)
        u = MenuUrunleri(magaza_id=m.id, secenek_gruplari="[]", etiketler="[]", alerjenler="[]", stokta_yok=False, gizli=False)
        try:
            await _urun_uygula(db, m, u, govde, yeni=True)
        except s.MenuHatasi as h:
            raise _menu_hatasi(h)
        u.sira = await _sonraki_sira(db, MenuUrunleri, MenuUrunleri.magaza_id == m.id)
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return _urun_sozlugu(u, await _gorseller(db, [u.gorsel]))

    @router.put("/{mid}/urunler/{uid}")
    async def urun_guncelle(mid: int, uid: int, request: Request, govde: Dict[str, Any] = Body(...),
                            db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        u = await _urun(db, m, uid)
        try:
            birakilan = await _urun_uygula(db, m, u, govde, yeni=False)
            await db.flush()
            for a in birakilan:
                await _gorseli_birak(db, m.id, a)
        except s.MenuHatasi as h:
            await db.rollback()
            raise _menu_hatasi(h)
        except HTTPException:
            await db.rollback()
            raise
        await db.commit()
        await db.refresh(u)
        return _urun_sozlugu(u, await _gorseller(db, [u.gorsel]))

    @router.delete("/{mid}/urunler/{uid}")
    async def urun_sil(mid: int, uid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        u = await _urun(db, m, uid)
        gorsel = u.gorsel
        await db.delete(u)
        await db.flush()
        await _gorseli_birak(db, m.id, gorsel)
        await db.commit()
        return {"ok": True}

    @router.post("/{mid}/gorsel")
    async def gorsel_yukle(mid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _gorsel_yukle(db, kapsam, await _yazilabilir_magaza(db, mid, kapsam), dosya)

    @router.post("/{mid}/ceviri")
    async def ceviri(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _cevir(db, kapsam, await _yazilabilir_magaza(db, mid, kapsam), govde)

    # --- Kuponlar ---
    @router.get("/{mid}/kuponlar")
    async def kupon_listesi(mid: int, request: Request, db: AsyncSession = Depends(get_db)):
        m = await _magaza(db, mid, kapsam_al(request))
        kuponlar = (await db.execute(select(MenuKuponlari).where(MenuKuponlari.magaza_id == m.id).order_by(desc(MenuKuponlari.id)))).scalars().all()
        simdi = _simdi()
        return {"items": [_kupon_sozlugu(c, simdi) for c in kuponlar]}

    @router.post("/{mid}/kuponlar")
    async def kupon_olustur(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        c = MenuKuponlari(magaza_id=m.id, kullanim_sayisi=0, aktif=True)
        try:
            _kupon_uygula(c, govde, yeni=True)
        except s.MenuHatasi as h:
            raise _menu_hatasi(h)
        db.add(c)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kupon_kodu_kullaniliyor", alan="kod")
        await db.refresh(c)
        return _kupon_sozlugu(c)

    @router.put("/{mid}/kuponlar/{cid}")
    async def kupon_guncelle(mid: int, cid: int, request: Request, govde: Dict[str, Any] = Body(...),
                             db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        c = (await db.execute(select(MenuKuponlari).where(MenuKuponlari.id == cid, MenuKuponlari.magaza_id == m.id))).scalars().first()
        if c is None:
            raise _hata(404, "bulunamadi")
        try:
            _kupon_uygula(c, govde, yeni=False)
            await db.commit()
        except s.MenuHatasi as h:
            await db.rollback()
            raise _menu_hatasi(h)
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kupon_kodu_kullaniliyor", alan="kod")
        await db.refresh(c)
        return _kupon_sozlugu(c)

    @router.delete("/{mid}/kuponlar/{cid}")
    async def kupon_sil(mid: int, cid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _yazilabilir_magaza(db, mid, kapsam)
        c = (await db.execute(select(MenuKuponlari).where(MenuKuponlari.id == cid, MenuKuponlari.magaza_id == m.id))).scalars().first()
        if c is None:
            raise _hata(404, "bulunamadi")
        await db.delete(c)
        await db.commit()
        return {"ok": True}

    # --- Siparişler ---
    @router.get("/{mid}/siparisler")
    async def siparis_listesi(
        mid: int, request: Request, durum: Optional[str] = Query(None), sinir: int = Query(100, ge=1, le=500),
        atla: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    ):
        m = await _magaza(db, mid, kapsam_al(request))
        if await anonimlestir(db, m):
            await db.commit()
        sorgu = select(MenuSiparisleri).where(MenuSiparisleri.magaza_id == m.id)
        if durum in s.SIPARIS_DURUMLARI:
            sorgu = sorgu.where(MenuSiparisleri.durum == durum)
        toplam = int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)
        kayitlar = (await db.execute(sorgu.order_by(desc(MenuSiparisleri.created_at), desc(MenuSiparisleri.id)).offset(atla).limit(sinir))).scalars().all()
        yeni = int((await db.execute(select(func.count(MenuSiparisleri.id)).where(MenuSiparisleri.magaza_id == m.id, MenuSiparisleri.durum == "yeni"))).scalar() or 0)
        return {"items": [_siparis_sozlugu(o) for o in kayitlar], "toplam": toplam, "yeni_sayisi": yeni,
                "saklama_gun": int(m.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN)}

    @router.get("/{mid}/siparisler/{sid}")
    async def siparis_ayrinti(mid: int, sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        m = await _magaza(db, mid, kapsam_al(request))
        if await anonimlestir(db, m):
            await db.commit()
        o = (await db.execute(select(MenuSiparisleri).where(MenuSiparisleri.id == sid, MenuSiparisleri.magaza_id == m.id))).scalars().first()
        if o is None:
            raise _hata(404, "bulunamadi")
        return {**_siparis_sozlugu(o), "magaza": {"ad": m.ad, "adres": m.adres or "", "telefon": m.telefon or "",
                                                  "para_birimi": m.para_birimi, "varsayilan_dil": m.varsayilan_dil}}

    @router.put("/{mid}/siparisler/{sid}")
    async def siparis_durumu(mid: int, sid: int, request: Request, govde: Dict[str, Any] = Body(...),
                             db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        m = await _magaza(db, mid, kapsam)
        o = (await db.execute(select(MenuSiparisleri).where(MenuSiparisleri.id == sid, MenuSiparisleri.magaza_id == m.id))).scalars().first()
        if o is None:
            raise _hata(404, "bulunamadi")
        if govde.get("durum") not in s.SIPARIS_DURUMLARI:
            raise _hata(400, "durum_gecersiz", alan="durum")
        o.durum = govde["durum"]
        await db.commit()
        await db.refresh(o)
        return _siparis_sozlugu(o)

    # --- Analiz, QR, içe aktarma ---
    @router.get("/{mid}/analiz")
    async def analiz(mid: int, request: Request, gun: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
        return await _analiz(db, await _magaza(db, mid, kapsam_al(request)), gun)

    @router.get("/{mid}/qr")
    async def menu_qr(mid: int, request: Request, bicim: str = Query("png"), masa: Optional[int] = Query(None, ge=1, le=9999),
                      db: AsyncSession = Depends(get_db)):
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        m = await _magaza(db, mid, kapsam_al(request))
        g = _qr_gorsel(m, masa, bicim)
        ad = f"menu-{m.slug}{f'-masa-{masa}' if masa else ''}.{bicim}"
        return Response(g.veri, media_type=g.tur, headers={
            "Content-Disposition": icerik_konumu(ad), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    @router.post("/{mid}/masa-qr")
    async def masa_qr(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        m = await _magaza(db, mid, kapsam)
        bicim = govde.get("bicim", "png")
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        try:
            bas = s.tam_sayi(govde.get("bas", 1), "bas", 1, 9999, bos_olabilir=False)
            bit = s.tam_sayi(govde.get("bit"), "bit", 1, 9999, bos_olabilir=False)
        except s.MenuHatasi as h:
            raise _menu_hatasi(h)
        if bit < bas or bit - bas + 1 > EN_COK_MASA:
            raise _hata(400, "masa_araligi", en_cok=EN_COK_MASA)
        _hiz(_qr_hizi, kapsam.kisi)
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w") as arsiv:
            for n in range(bas, bit + 1):
                g = _qr_gorsel(m, n, bicim)
                arsiv.writestr(f"masa-{n:03d}.{bicim}", g.veri,
                               compress_type=zipfile.ZIP_STORED if bicim == "png" else zipfile.ZIP_DEFLATED)
        return Response(tampon.getvalue(), media_type="application/zip", headers={
            "Content-Disposition": icerik_konumu(f"menu-{m.slug}-masalar-{bas}-{bit}.zip"), "Cache-Control": "no-store",
        })

    @router.post("/{mid}/ice-aktar/onizleme")
    async def ice_aktar_onizleme(mid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _ice_aktar_onizleme(db, kapsam, await _yazilabilir_magaza(db, mid, kapsam), dosya)

    @router.post("/{mid}/ice-aktar")
    async def ice_aktar(mid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _ice_aktar(db, kapsam, await _yazilabilir_magaza(db, mid, kapsam), govde)


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


async def _yayinda_magaza(db: AsyncSession, slug: str) -> MenuMagazalari:
    """Slug'a göre yayındaki mağaza: yok → 404, pasif / sahibin modülü kapalı → 410."""
    temiz = (slug or "").strip().lower()
    if not s.SLUG_DESENI.match(temiz):
        raise _hata(404, "menu_yok")
    m = (await db.execute(select(MenuMagazalari).where(MenuMagazalari.slug == temiz))).scalars().first()
    if m is None:
        raise _hata(404, "menu_yok")
    if not m.aktif:
        raise _hata(410, "menu_pasif")
    if m.hesap_email:
        from services import moduller as modul_servisi

        if not await modul_servisi.modul_acik_mi(db, m.hesap_email, s.DUZEN_MODULU[m.duzen]):
            raise _hata(410, "menu_pasif")
    return m


def _ziyaretci_anahtari(request: Request, m: MenuMagazalari) -> str:
    return f"{m.id}|{ip_ozeti('menu-hiz|' + istemci_ip(request))}"


def _bot_mu(request: Request) -> bool:
    basliklar = {ad: request.headers.get(ad, "") for ad in ("purpose", "sec-purpose", "x-purpose", "x-moz")}
    return request.method == "HEAD" or qr.bot_mu(request.headers.get("user-agent") or "", basliklar)


def _olay_verisi(request: Request, m: MenuMagazalari, tur: str, urun_id: Optional[int]) -> Dict[str, Any]:
    simdi = _simdi()
    gun = simdi.date().isoformat()
    return {
        "magaza_id": m.id, "tur": tur, "urun_id": urun_id, "zaman": simdi, "gun": gun,
        # Gün tuzun parçası: aynı günün tekil sayımı için yeter, günler arası izleme yok.
        "ip_ozeti": ip_ozeti(f"menu|{gun}|{istemci_ip(request)}"),
        "bot": _bot_mu(request),
    }


async def _olay_yaz(veri: Dict[str, Any]) -> None:
    """Yanıt gönderildikten sonra tek INSERT. Hata yutulur (analitik menüyü asla bozmasın)."""
    try:
        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as oturum:
            await oturum.execute(insert(MenuOlaylari).values(**veri))
            await oturum.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Menü olayı kaydedilemedi")


def _olay_ekle(arka: BackgroundTasks, request: Request, m: MenuMagazalari, tur: str, urun_id: Optional[int] = None) -> None:
    if _olay_hizi.izin_var_mi(_ziyaretci_anahtari(request, m) + "|" + tur):
        arka.add_task(_olay_yaz, _olay_verisi(request, m, tur, urun_id))


def _urun_bilgisi(u: MenuUrunleri, kategori_gizli: bool) -> s.UrunBilgisi:
    return s.UrunBilgisi(
        id=u.id, ad=u.ad, fiyat=int(u.fiyat or 0), indirimli_fiyat=u.indirimli_fiyat,
        gruplar=s.json_yukle(u.secenek_gruplari, []) or [], ceviriler=s.json_yukle(u.ceviriler, {}) or {},
        satilabilir=not (u.gizli or u.stokta_yok or kategori_gizli),
    )


async def _gorunur_icerik(db: AsyncSession, m: MenuMagazalari) -> Tuple[List[MenuKategorileri], List[MenuUrunleri]]:
    kategoriler = (await db.execute(
        select(MenuKategorileri).where(MenuKategorileri.magaza_id == m.id, MenuKategorileri.gizli.is_(False))
        .order_by(MenuKategorileri.sira, MenuKategorileri.id)
    )).scalars().all()
    gorunur = {k.id for k in kategoriler}
    urunler = (await db.execute(
        select(MenuUrunleri).where(MenuUrunleri.magaza_id == m.id, MenuUrunleri.gizli.is_(False))
        .order_by(MenuUrunleri.sira, MenuUrunleri.id)
    )).scalars().all()
    return list(kategoriler), [u for u in urunler if u.kategori_id in gorunur]


def _etkin_siparis_ayarlari(m: MenuMagazalari) -> Dict[str, Any]:
    a = _siparis_ayarlari(m)
    a["whatsapp_acik"] = bool(a.get("whatsapp_acik") and m.whatsapp)
    return a


async def _sepet_hesapla(db: AsyncSession, m: MenuMagazalari, g: Dict[str, Any], dil: str) -> Tuple[Dict[str, Any], Optional[MenuKuponlari]]:
    kalemler = s.kalemleri_coz(g.get("kalemler"))
    ayarlar = _etkin_siparis_ayarlari(m)
    teslimat = g.get("teslimat") or next((t for t in s.TESLIMATLAR if ayarlar.get(t)), "gel_al")
    if teslimat not in s.TESLIMATLAR or not ayarlar.get(teslimat):
        raise s.MenuHatasi("teslimat_gecersiz", "teslimat")
    idler = sorted({k["urun_id"] for k in kalemler})
    urunler = (await db.execute(select(MenuUrunleri).where(MenuUrunleri.magaza_id == m.id, MenuUrunleri.id.in_(idler)))).scalars().all()
    gizli_kategoriler = set((await db.execute(
        select(MenuKategorileri.id).where(MenuKategorileri.magaza_id == m.id, MenuKategorileri.gizli.is_(True))
    )).scalars().all())
    bilgiler = {u.id: _urun_bilgisi(u, u.kategori_id in gizli_kategoriler) for u in urunler}
    kupon = None
    kupon_kodu = None
    if g.get("kupon"):
        try:
            kupon_kodu = s.kupon_kodu_duzelt(g.get("kupon"))
        except s.MenuHatasi:
            kupon_kodu = str(g.get("kupon"))[:32].upper()
        kupon = (await db.execute(select(MenuKuponlari).where(MenuKuponlari.magaza_id == m.id, MenuKuponlari.kod == kupon_kodu))).scalars().first()
    hesap = s.sepet_hesapla(bilgiler, kalemler, dil=dil, teslimat=teslimat, ayarlar=ayarlar, kupon=kupon, kupon_kodu=kupon_kodu)
    hesap["teslimat"] = teslimat
    return hesap, kupon


def _hesap_ciktisi(h: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **h,
        "kalemler": [
            {**k, "birim_fiyat": s.tl(k["birim_fiyat"]), "tutar": s.tl(k["tutar"]),
             "secenekler": [{**x, "fiyat_farki": s.tl(x["fiyat_farki"])} for x in k["secenekler"]]}
            for k in h["kalemler"]
        ],
        "ara_toplam": s.tl(h["ara_toplam"]),
        "indirim": s.tl(h["indirim"]),
        "paket_ucreti": s.tl(h["paket_ucreti"]),
        "toplam": s.tl(h["toplam"]),
        "en_dusuk_tutar": s.tl(h["en_dusuk_tutar"]),
        "en_dusuk_eksik": s.tl(h["en_dusuk_eksik"]),
    }


async def _marka(db: AsyncSession, m: MenuMagazalari) -> Dict[str, Any]:
    """Faz 4L: marka teması (mağazanın kendi tema rengi düzenin varsayılanından farklıysa o öncelikli)."""
    from services.marka import acik_marka, renk_ozel_mi

    varsayilan = "#7c3aed" if m.duzen == "menu" else "#0f766e"
    return await acik_marka(db, m.hesap_email, sayfa_ozel=renk_ozel_mi(m.tema_rengi, varsayilan))


def _dil(m: MenuMagazalari, ham: Any) -> str:
    d = str(ham or "").strip().lower()[:2]
    return d if d in _diller(m) else m.varsayilan_dil


@acik_router.api_route("/{slug}", methods=["GET", "HEAD"])
async def acik_menu(slug: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    m = await _yayinda_magaza(db, slug)
    kategoriler, urunler = await _gorunur_icerik(db, m)
    gorseller = await _gorseller(db, [m.logo, m.kapak] + [k.gorsel for k in kategoriler] + [u.gorsel for u in urunler])
    kupon_var = (await db.execute(select(MenuKuponlari.id).where(MenuKuponlari.magaza_id == m.id, MenuKuponlari.aktif.is_(True)).limit(1))).first() is not None
    ayarlar = _etkin_siparis_ayarlari(m)
    veri = {
        "slug": m.slug,
        "duzen": m.duzen,
        "ad": m.ad,
        "aciklama": m.aciklama or "",
        "ceviriler": s.json_yukle(m.ceviriler, {}) or {},
        "logo": _gorsel_sozlugu(m.logo, gorseller),
        "kapak": _gorsel_sozlugu(m.kapak, gorseller),
        "tema_rengi": m.tema_rengi,
        "adres": m.adres or "",
        "telefon": m.telefon or "",
        "para_birimi": m.para_birimi,
        "varsayilan_dil": m.varsayilan_dil,
        "diller": _diller(m),
        "acik": s.acik_mi(_saatler(m), m.saat_dilimi),
        "calisma_saatleri": _saatler(m),
        "saat_dilimi": m.saat_dilimi,
        "siparis": _para_ayarlari(ayarlar),
        "kupon_var": kupon_var,
        "saklama_gun": int(m.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN),
        "indekslenebilir": bool(m.arama_motoru),
        "kategoriler": [{k2: v for k2, v in _kategori_sozlugu(k, gorseller).items() if k2 not in ("gizli", "sira")} for k in kategoriler],
        "urunler": [
            {k2: v for k2, v in _urun_sozlugu(u, gorseller).items() if k2 not in ("gizli", "sira")}
            for u in urunler
        ],
        "marka": await _marka(db, m),
    }
    _olay_ekle(arka, request, m, "goruntuleme")
    return JSONResponse(veri, headers={**ACIK_BASLIKLAR, "Cache-Control": "no-cache",
                                       **({} if m.arama_motoru else {"X-Robots-Tag": "noindex"})})


@acik_router.get("/{slug}/ozet")
async def acik_ozet(slug: str, urun: Optional[str] = Query(None), dil: Optional[str] = Query(None),
                    db: AsyncSession = Depends(get_db)):
    """Pages Function'ın paylaşım önizlemesi (title/og/twitter/canonical/robots) için."""
    m = await _yayinda_magaza(db, slug)
    d = _dil(m, dil)
    ceviriler = s.json_yukle(m.ceviriler, {}) or {}
    gorsel = m.kapak or m.logo
    veri: Dict[str, Any] = {
        "slug": m.slug,
        "duzen": m.duzen,
        "ad": s.yerel(m.ad, ceviriler, d),
        "aciklama": s.yerel(m.aciklama or "", ceviriler, d, "aciklama")[:300],
        "dil": d,
        "diller": _diller(m),
        "gorsel": s.gorsel_adresi(gorsel, "b", mutlak=True),
        "tema_rengi": m.tema_rengi,
        "indekslenebilir": bool(m.arama_motoru),
        "adres_url": s.menu_adresi(m.slug),
        "urun": None,
        "marka": await _marka(db, m),
    }
    if urun and urun.isdigit():
        u = (await db.execute(select(MenuUrunleri).where(MenuUrunleri.id == int(urun), MenuUrunleri.magaza_id == m.id,
                                                         MenuUrunleri.gizli.is_(False)))).scalars().first()
        if u is not None:
            k = (await db.execute(select(MenuKategorileri.gizli).where(MenuKategorileri.id == u.kategori_id))).scalar()
            if not k:
                uc = s.json_yukle(u.ceviriler, {}) or {}
                veri["urun"] = {
                    "id": u.id,
                    "ad": s.yerel(u.ad, uc, d),
                    "aciklama": s.yerel(u.aciklama or "", uc, d, "aciklama")[:300],
                    "gorsel": s.gorsel_adresi(u.gorsel, "b", mutlak=True),
                    "fiyat": s.tutar_yaz(s.birim_fiyat(_urun_bilgisi(u, False)), m.para_birimi, d),
                }
    return JSONResponse(veri, headers={"Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff"})


@acik_router.post("/{slug}/olay")
async def acik_olay(slug: str, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                    db: AsyncSession = Depends(get_db)):
    m = await _yayinda_magaza(db, slug)
    tur = govde.get("tur")
    if tur not in s.ISTEMCI_OLAYLARI:
        raise _hata(400, "olay_gecersiz", alan="tur")
    try:
        urun_id = int(govde.get("urun_id"))
    except (TypeError, ValueError):
        raise _hata(400, "gecersiz", alan="urun_id")
    var = (await db.execute(select(MenuUrunleri.id).where(MenuUrunleri.id == urun_id, MenuUrunleri.magaza_id == m.id))).first()
    if var is None:
        raise _hata(404, "urun_yok")
    _olay_ekle(arka, request, m, tur, urun_id)
    return JSONResponse({"ok": True}, headers=ACIK_BASLIKLAR)


@acik_router.post("/{slug}/hesapla")
async def acik_hesapla(slug: str, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    m = await _yayinda_magaza(db, slug)
    _hiz(_hesap_hizi, _ziyaretci_anahtari(request, m))
    try:
        hesap, _ = await _sepet_hesapla(db, m, govde, _dil(m, govde.get("dil")))
    except s.MenuHatasi as h:
        raise _menu_hatasi(h)
    return JSONResponse(_hesap_ciktisi(hesap), headers=ACIK_BASLIKLAR)


@acik_router.post("/{slug}/siparis")
async def acik_siparis(slug: str, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                       db: AsyncSession = Depends(get_db)):
    m = await _yayinda_magaza(db, slug)
    await _kalici_hiz((_siparis_hizi, _ziyaretci_anahtari(request, m)), (_magaza_siparis_hizi, str(m.id)))
    # Bal küpü: bot "başarılı" görsün, hiçbir şey kaydedilmesin.
    if str(govde.get("web_adresi") or "").strip():
        logger.info("Menü siparişi: bal küpü dolu, yok sayıldı (mağaza %s)", m.id)
        return JSONResponse({"ok": True, "siparis_no": None, "wa_adresi": None}, headers=ACIK_BASLIKLAR)
    ayarlar = _etkin_siparis_ayarlari(m)
    if not ayarlar["whatsapp_acik"]:
        raise _hata(409, "siparis_kapali")
    if s.acik_mi(_saatler(m), m.saat_dilimi) is False and not ayarlar.get("kapaliyken_siparis"):
        raise _hata(409, "magaza_kapali")
    dil = _dil(m, govde.get("dil"))
    try:
        hesap, kupon = await _sepet_hesapla(db, m, govde, dil)
        teslimat = hesap["teslimat"]
        ad = s.metin(govde.get("ad"), "ad", 80, zorunlu=True)
        adres = s.metin(govde.get("adres"), "adres", 300, zorunlu=(teslimat == "paket"), cok_satir=True) if teslimat == "paket" else ""
        notu = s.metin(govde.get("not"), "not", 500, cok_satir=True)
        masa = s.metin(govde.get("masa"), "masa", 12) if teslimat == "masada" else ""
        if teslimat == "masada" and not masa:
            raise s.MenuHatasi("masa_gerekli", "masa")
        if masa and not all(c.isalnum() or c in " .-" for c in masa):
            raise s.MenuHatasi("masa_gecersiz", "masa")
    except s.MenuHatasi as h:
        raise _menu_hatasi(h)
    if hesap["kupon"] and not hesap["kupon"]["gecerli"]:
        raise _hata(409, hesap["kupon"]["hata"], alan="kupon")
    if hesap["en_dusuk_eksik"] > 0:
        raise _hata(409, "en_dusuk_tutar", en_dusuk=s.tl(hesap["en_dusuk_tutar"]), eksik=s.tl(hesap["en_dusuk_eksik"]))
    if kupon is not None and hesap["indirim"] > 0:
        # Kullanım sınırı tek UPDATE ile: eş zamanlı iki sipariş aynı son hakkı kullanamaz.
        sonuc = await db.execute(
            update(MenuKuponlari)
            .where(MenuKuponlari.id == kupon.id, or_(MenuKuponlari.kullanim_siniri.is_(None),
                                                       MenuKuponlari.kullanim_sayisi < MenuKuponlari.kullanim_siniri))
            .values(kullanim_sayisi=MenuKuponlari.kullanim_sayisi + 1)
            .execution_options(synchronize_session=False)
        )
        if not sonuc.rowcount:
            await db.rollback()
            raise _hata(409, "kupon_siniri", alan="kupon")
    kalemler = [
        {"urun_id": k["urun_id"], "ad": k["ad"], "ad_dil": k["ad_dil"], "adet": k["adet"], "birim_fiyat": k["birim_fiyat"],
         "tutar": k["tutar"], "secenekler": k["secenekler"]}
        for k in hesap["kalemler"]
    ]
    siparis = None
    for _ in range(6):
        siparis = MenuSiparisleri(
            magaza_id=m.id, siparis_no=s.siparis_no_uret(), durum="yeni", teslimat=teslimat, masa=masa or None,
            musteri_ad=ad, adres=adres or None, siparis_notu=notu or None, anonim=False, kalemler=s.json_yaz(kalemler),
            ara_toplam=hesap["ara_toplam"], indirim=hesap["indirim"],
            kupon_kodu=(hesap["kupon"] or {}).get("kod") if hesap["indirim"] else None,
            paket_ucreti=hesap["paket_ucreti"], toplam=hesap["toplam"], para_birimi=m.para_birimi, dil=dil,
        )
        db.add(siparis)
        try:
            await db.flush()
            break
        except IntegrityError:
            await db.rollback()
            siparis = None
    if siparis is None:
        raise _hata(503, "siparis_no_uretilemedi")
    await anonimlestir(db, m)
    await db.commit()
    await db.refresh(siparis)

    metin_ = s.wa_metni(
        siparis_no=siparis.siparis_no, magaza_adi=s.yerel(m.ad, s.json_yukle(m.ceviriler, {}), dil), hesap=hesap,
        teslimat=teslimat, masa=masa or None, ad=ad, adres=adres or None, notu=notu or None, para=m.para_birimi, dil=dil,
    )
    arka.add_task(_olay_yaz, _olay_verisi(request, m, "siparis", None))
    arka.add_task(_siparis_bildir, m.id, siparis.id)
    return JSONResponse(
        {"ok": True, "siparis_no": siparis.siparis_no, "toplam": s.tl(siparis.toplam), "para_birimi": m.para_birimi,
         "wa_adresi": s.wa_adresi(m.whatsapp or "", metin_), "metin": metin_},
        headers=ACIK_BASLIKLAR,
    )


async def _siparis_bildir(magaza_id: int, siparis_id: int) -> None:
    """Yeni sipariş olayı (`menu_siparis`): mağaza sahibine (ajans mağazasında yöneticilere)."""
    try:
        if not db_manager.async_session_maker:
            return
        from services import notify

        async with db_manager.async_session_maker() as db:
            m = (await db.execute(select(MenuMagazalari).where(MenuMagazalari.id == magaza_id))).scalars().first()
            o = (await db.execute(select(MenuSiparisleri).where(MenuSiparisleri.id == siparis_id))).scalars().first()
            if m is None or o is None:
                return
            if m.hesap_email:
                alicilar = [{"email": m.hesap_email, "role": "client"}]
                baglanti = "/client?sekme=menu"
            else:
                alicilar = await notify.admin_recipients(db)
                baglanti = "/admin?sekme=qrMenu"
            kalem = sum(int(k.get("adet") or 0) for k in (s.json_yukle(o.kalemler, []) or []))
            await notify.dispatch(
                db,
                event_type="menu_siparis",
                title=f"Yeni sipariş #{o.siparis_no} — {m.ad}",
                body=f"{kalem} ürün · {s.tutar_yaz(o.toplam, o.para_birimi, 'tr')} · {s.SIPARIS_ETIKETLERI['tr'][o.teslimat]}"
                     + (f" · Masa {o.masa}" if o.masa else ""),
                recipients=alicilar,
                link=baglanti,
                ref_type="menu_siparisleri",
                ref_id=o.id,
            )
    except Exception:  # noqa: BLE001 - bildirim siparişi bozmasın
        logger.exception("Menü siparişi bildirilemedi")


# ---------------------------------------------------------------------------
# Görsel (herkese açık, değişmez)
# ---------------------------------------------------------------------------
@gorsel_router.get("/{anahtar}")
async def gorsel(anahtar: str, b: str = Query("b"), db: AsyncSession = Depends(get_db)):
    if b not in ("k", "b") or len(anahtar) > 64:
        raise _hata(404, "bulunamadi")
    g = (await db.execute(select(MenuGorselleri).where(MenuGorselleri.anahtar == anahtar))).scalars().first()
    if g is None:
        raise _hata(404, "bulunamadi")
    from services import dosya_deposu

    try:
        veri = await dosya_deposu.oku(db, g.depo, f"menu/{g.anahtar}-{b}.webp")
    except dosya_deposu.DepoHatasi:
        raise _hata(404, "bulunamadi")
    return Response(veri, media_type="image/webp", headers={
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    })


# Yönetici ve müşteri router'ları ÖNCE; herkese açıklar en sonda.
router = (yonetici_router, musteri_router, gorsel_router, acik_router)
