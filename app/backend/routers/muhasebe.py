"""Faz 6M — Ön muhasebe: kasa/banka/kredi kartı hesapları, gelir-gider, cari hesap, bütçe, nakit akışı.

e-Fatura / e-Arşiv ve banka entegrasyonu YOK (hesap gerektirir; sonraki faz). Tutarlar kuruş; para birimleri
arasında DÖNÜŞÜM yok, raporlar para birimine göre ayrı.

Müşteri (`/api/v1/muhasebe`; modül `on_muhasebe` açık + hesap ekibi izni `muhasebe`) — etkin hesabın defteri.
`muhasebe_okur` (örn. mali müşavir) YALNIZ rapor uçlarını okur: meta, özet (son hareketler olmadan), bütçe durumu,
yaşlandırma, raporlar ve CSV'leri; hareket/cari/hesap ayrıntısı ve her yazma 403 `hesap_izni_yok`.
Yönetici (`/api/v1/muhasebe-yonetim`, ajans): `?hesap=` YOKSA ajansın KENDİ muhasebesi (tam yönetim);
`?hesap=<e-posta>` ile müşteri hesabının SALT OKUNUR destek görünümü (yazma 403 `salt_okunur`).
`GET /musteri-hesaplari` destek listesi (yalnız yönetici).

Ortak uçlar (iki panelde aynı gövdeler):
  GET  /meta · GET /ozet · GET|PUT /ayarlar · POST /esitle (tekrarlar + otomatik aktarma + bütçe denetimi)
  GET|POST /hesaplar · PUT|DELETE /hesaplar/{id} · POST /virman
  GET|POST /kategoriler · PUT|DELETE /kategoriler/{id} · POST /kategoriler/varsayilanlar
  GET|POST /hareketler · GET|PUT|DELETE /hareketler/{id} · GET /hareketler.csv · GET /hareketler.pdf
  POST /hareketler/{id}/ekler (multipart `dosya`) · GET|DELETE /ekler/{id}
  POST /ice-aktar/onizle · POST /ice-aktar (banka ekstresi CSV'si: sütun eşleme, deneme modu)
  GET|POST /tekrarlar · PUT|DELETE /tekrarlar/{id}
  GET|POST /cariler · GET /cariler/baglanti-adaylari · GET|PUT|DELETE /cariler/{id}
  GET /cariler/{id}/ekstre · GET /cariler/{id}/ekstre.pdf · GET /cariler/{id}/ekstre.csv · GET /yaslandirma
  GET|PUT /butceler
  GET /raporlar/aylik · GET /raporlar/kategori · GET /raporlar/kar-zarar · GET /raporlar/nakit-akisi · GET /raporlar/kdv ·
  GET /raporlar.csv
  GET /oneriler · POST /oneriler/{id}/onayla · POST /oneriler/{id}/yoksay · POST /oneriler/{id}/geri-al ·
  POST /oneriler/toplu (onay bekleyen otomatik yansımalar)

Silme: hesap / kategori / cari kullanılıyorsa 409 (arşive alınır); hareket, tekrar, cari, hesap ve ek çöp kutusuna
düşer. Otomatik yansıma ve ters kayıtlar elle düzenlenmez/silinmez (409 `otomatik_kayit`): aktarım kapatılır ya da
kaynak düzeltilir — eşitleme ters kaydı kendisi yazar.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from models.muhasebe import (
    MuhasebeAyarlari,
    MuhasebeButceler,
    MuhasebeCariler,
    MuhasebeEkleri,
    MuhasebeHareketleri,
    MuhasebeHesaplari,
    MuhasebeKategorileri,
    MuhasebeOneriler,
    MuhasebeTekrarlar,
)
from services import muhasebe as s
from services import muhasebe_kayit as k
from services.dosya_deposu import icerik_konumu
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN
IZIN_OKUR = s.IZIN_OKUR
H = MuhasebeHareketleri

yonetici_router = APIRouter(prefix="/api/v1/muhasebe-yonetim", tags=["muhasebe"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/muhasebe",
    tags=["muhasebe"],
    # Router bekçisi: iki izinden biri. Uçlar ayrıca daraltır (rapor dışı uçlar yalnız `muhasebe`).
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN, IZIN_OKUR))],
)

#: Kişi başı: dakikada 120 yazma, 20 dosya/CSV/PDF.
_yazma_hizi = HizSiniri(120, 60.0)
_dosya_hizi = HizSiniri(20, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _dosya_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    yonetici: bool
    #: Kayıtların hesabı: müşteride etkin hesap; yöneticide None (ajansın kendi defteri) ya da `?hesap=`.
    hesap: Optional[str]
    kisi: str
    salt_okunur: bool = False
    baglam: Any = None
    #: `muhasebe_okur`: yalnız rapor uçları (salt okunur).
    okur: bool = False

    @property
    def anahtar(self) -> str:
        return s.kapsam_anahtari(self.hesap)

    def izinli(self, izin: str) -> bool:
        """Başka modülün kişisel verisine (bağlantı adayları) erişim: yönetici ya da o izni de olan üye."""
        if self.yonetici:
            return True
        try:
            return bool(self.baglam and self.baglam.izin_var(izin))
        except Exception:  # noqa: BLE001
            return False


def _musteri_kapsami(request: Request, rapor: bool = False) -> Kapsam:
    """`rapor=True` uçlarında `muhasebe_okur` da yeter (salt okunur); diğerlerinde yalnız `muhasebe`."""
    if not rapor:
        b = izin_iste(request, IZIN)
        return Kapsam(False, b.hesap_email, b.kisi_email, baglam=b)
    b = izin_iste(request, IZIN, IZIN_OKUR)
    okur = not b.izin_var(IZIN)
    return Kapsam(False, b.hesap_email, b.kisi_email, salt_okunur=okur, baglam=b, okur=okur)


def _yonetici_kapsami(request: Request, rapor: bool = False) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    kisi = (getattr(kullanici, "email", "") or "").strip().lower()
    ham = (request.query_params.get("hesap") or "").strip().lower()
    if not ham or ham == "ajans":
        return Kapsam(True, None, kisi)
    if "@" not in ham or len(ham) > 254:
        raise _hata(400, "hesap_gecersiz", alan="hesap")
    return Kapsam(True, ham, kisi, salt_okunur=True)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _e(h: s.TemelHata) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _yaz(kapsam: Kapsam) -> None:
    if kapsam.salt_okunur:
        raise _hata(403, "salt_okunur")
    if not _yazma_hizi.izin_var_mi(kapsam.kisi or "anonim"):
        raise _hata(429, "cok_hizli")


def _dosya(kapsam: Kapsam) -> None:
    if not _dosya_hizi.izin_var_mi(kapsam.kisi or "anonim"):
        raise _hata(429, "cok_hizli")


async def _govde(request: Request, sinir: int = 256 * 1024) -> Dict[str, Any]:
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


def _tarih_q(ham: Optional[str], alan: str, varsayilan: Optional[date] = None) -> date:
    if not ham:
        if varsayilan is None:
            raise _hata(400, "zorunlu", alan=alan)
        return varsayilan
    try:
        return s.tarih_duzelt(ham, alan)
    except s.TemelHata as h:
        raise _e(h)


def _dosya_yaniti(veri: bytes, tur: str, ad: str) -> Response:
    return Response(veri, media_type=tur, headers={"Content-Disposition": f'attachment; filename="{ad}"',
                                                   "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


def _csv_yaniti(metin: str, ad: str) -> Response:
    return _dosya_yaniti(metin.encode("utf-8"), "text/csv; charset=utf-8", ad)


async def _hesap_siniri(db: AsyncSession, kapsam: Kapsam) -> Optional[int]:
    if not kapsam.hesap:
        return None
    from services.moduller import musteri_ayari

    d = await musteri_ayari(db, kapsam.hesap, MODUL, "hesap_siniri")
    return s.VARSAYILAN_HESAP_SINIRI if d is None else int(d)


async def _ayar(db: AsyncSession, kapsam: Kapsam) -> Optional[MuhasebeAyarlari]:
    return await k.ayar_satiri(db, kapsam.anahtar)


async def _firma(db: AsyncSession, kapsam: Kapsam) -> str:
    a = await _ayar(db, kapsam)
    if a and a.firma_adi:
        return a.firma_adi
    if kapsam.hesap:
        try:
            from services.hesap_ekibi import hesap_adlari

            return (await hesap_adlari(db, [kapsam.hesap])).get(kapsam.hesap) or kapsam.hesap
        except Exception:  # noqa: BLE001
            return kapsam.hesap
    return "By Mehmet KURU Dev"


# ---------------------------------------------------------------------------
# Kayıt bulucular (kapsama bağlı)
# ---------------------------------------------------------------------------
async def _bul(db: AsyncSession, model: Any, kapsam: Kapsam, kid: Optional[int], kod: str = "bulunamadi", alan: Optional[str] = None):
    if not kid:
        raise _hata(404 if alan is None else 400, kod, **({"alan": alan} if alan else {}))
    x = (await db.execute(select(model).where(model.id == kid, model.kapsam == kapsam.anahtar))).scalars().first()
    if x is None:
        raise _hata(404 if alan is None else 400, kod, **({"alan": alan} if alan else {}))
    return x


async def _adlar(db: AsyncSession, kapsam: Kapsam) -> Dict[str, Dict[int, Any]]:
    kat = {x.id: x for x in (await db.execute(select(MuhasebeKategorileri).where(MuhasebeKategorileri.kapsam == kapsam.anahtar))).scalars().all()}
    hes = {x.id: x for x in (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam.anahtar))).scalars().all()}
    return {"kategori": kat, "hesap": hes}


async def _cari_adlari(db: AsyncSession, idler: List[int]) -> Dict[int, str]:
    idler = [i for i in set(idler) if i]
    if not idler:
        return {}
    return dict((await db.execute(select(MuhasebeCariler.id, MuhasebeCariler.ad).where(MuhasebeCariler.id.in_(idler)))).all())


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _hesap_sozlugu(h: MuhasebeHesaplari, etki: int = 0, sayi: int = 0) -> Dict[str, Any]:
    # Tam IBAN hiçbir uçta dönmez: yalnız son 4 hane (maskeli). Değiştirmek için yenisi yazılır.
    return {
        "id": h.id, "tur": h.tur, "ad": h.ad, "banka_adi": h.banka_adi or "", "iban_var": bool(h.iban), "iban_maske": s.iban_maskele(h.iban),
        "son4": h.son4 or "", "para_birimi": h.para_birimi, "acilis_bakiyesi": int(h.acilis_bakiyesi or 0),
        "acilis_tarihi": s.gun_iso(h.acilis_tarihi), "arsiv": bool(h.arsiv), "notlar": h.notlar or "", "sira": int(h.sira or 0),
        "bakiye": int(h.acilis_bakiyesi or 0) + int(etki or 0), "hareket_sayisi": int(sayi or 0),
    }


def _kategori_sozlugu(x: MuhasebeKategorileri, sayi: int = 0) -> Dict[str, Any]:
    return {"id": x.id, "tur": x.tur, "ad": x.ad, "anahtar": x.anahtar, "ad_degisti": k._ad_degisti(x), "renk": x.renk or "#9ca3af",  # noqa: SLF001
            "arsiv": bool(x.arsiv), "sira": int(x.sira or 0), "kullanim": int(sayi or 0)}


def _cari_sozlugu(c: MuhasebeCariler, etki: int = 0, tam: bool = True) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": c.id, "tur": c.tur, "ad": c.ad, "para_birimi": c.para_birimi, "arsiv": bool(c.arsiv),
        "bakiye": int(c.acilis_bakiyesi or 0) + int(etki or 0), "bagli_tur": c.bagli_tur, "bagli_id": c.bagli_id,
    }
    if tam:
        d.update({"vergi_dairesi": c.vergi_dairesi or "", "vergi_no": c.vergi_no or "", "eposta": c.eposta or "",
                  "telefon": c.telefon or "", "adres": c.adres or "", "notlar": c.notlar or "",
                  "acilis_bakiyesi": int(c.acilis_bakiyesi or 0), "acilis_tarihi": s.gun_iso(c.acilis_tarihi)})
    return d


def _hareket_sozlugu(h: H, adlar: Dict[str, Dict[int, Any]], cariler: Dict[int, str], ek_sayisi: int = 0) -> Dict[str, Any]:
    kat = adlar["kategori"].get(h.kategori_id) if h.kategori_id else None
    hes = adlar["hesap"].get(h.hesap_id) if h.hesap_id else None
    hed = adlar["hesap"].get(h.hedef_hesap_id) if h.hedef_hesap_id else None
    return {
        "id": h.id, "tur": h.tur, "tarih": h.tarih.isoformat(), "tutar": int(h.tutar), "para_birimi": h.para_birimi,
        "kdv_orani": h.kdv_orani, "kdv_tutari": int(h.kdv_tutari or 0),
        "kategori_id": h.kategori_id, "kategori": ({"ad": kat.ad, "anahtar": kat.anahtar, "ad_degisti": k._ad_degisti(kat),  # noqa: SLF001
                                                    "renk": kat.renk} if kat else None),
        "hesap_id": h.hesap_id, "hesap": hes.ad if hes else None, "hedef_hesap_id": h.hedef_hesap_id, "hedef_hesap": hed.ad if hed else None,
        "hedef_tutar": h.hedef_tutar, "hedef_para_birimi": hed.para_birimi if hed else None,
        "cari_id": h.cari_id, "cari": cariler.get(h.cari_id) if h.cari_id else None, "vade_tarihi": s.gun_iso(h.vade_tarihi),
        "aciklama": h.aciklama or "", "belge_no": h.belge_no or "", "etiketler": s.json_yukle(h.etiketler, []) or [],
        "kaynak": h.kaynak, "otomatik": h.kaynak in s.OTOMATIK_KAYNAKLAR, "ters": h.ters_edilen_id is not None,
        "ters_edildi": h.ters_kayit_id is not None, "tekrar_id": h.tekrar_id, "ek_sayisi": int(ek_sayisi or 0),
        "duzenlenebilir": h.kaynak in s.ELLE_KAYNAKLAR and h.ters_edilen_id is None, "created_at": s.iso(h.created_at),
    }


def _tekrar_sozlugu(t: MuhasebeTekrarlar) -> Dict[str, Any]:
    return {"id": t.id, "tur": t.tur, "aciklama": t.aciklama, "tutar": int(t.tutar), "para_birimi": t.para_birimi,
            "kdv_orani": t.kdv_orani, "kategori_id": t.kategori_id, "hesap_id": t.hesap_id, "cari_id": t.cari_id,
            "periyot": t.periyot, "baslangic": t.baslangic.isoformat(), "bitis": s.gun_iso(t.bitis),
            "sonraki": s.gun_iso(t.sonraki), "son_uretilen": s.gun_iso(t.son_uretilen), "aktif": bool(t.aktif),
            "etiketler": s.json_yukle(t.etiketler, []) or []}


def _ayar_sozlugu(a: Optional[MuhasebeAyarlari], kapsam: Kapsam) -> Dict[str, Any]:
    return {
        "kapsam": kapsam.anahtar, "firma_adi": (a.firma_adi if a else "") or "", "para_birimi": (a.para_birimi if a else None) or "TRY",
        "uyari_yuzde": int(a.uyari_yuzde if a and a.uyari_yuzde is not None else 80),
        "aktarim": k.aktarim_ayarlari(a, kapsam.anahtar),
        "son_esitleme": s.json_yukle(a.son_esitleme, None) if a else None, "son_esitleme_at": s.iso(a.son_esitleme_at) if a else None,
    }


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------
async def _hareket_girdisi(db: AsyncSession, kapsam: Kapsam, g: Dict[str, Any], mevcut: Optional[H] = None) -> Dict[str, Any]:
    """Doğrulanmış alanlar (kayda yazılacak). Kısmi güncellemede eksik alan mevcut kayıttan."""
    def al(alan: str, varsayilan: Any = None) -> Any:
        if alan in g:
            return g.get(alan)
        if mevcut is not None:
            return getattr(mevcut, alan, varsayilan)
        return varsayilan

    try:
        tur = s.secim(al("tur"), "tur", s.HAREKET_TURLERI)
        if mevcut is not None and (mevcut.tur == "virman") != (tur == "virman"):
            raise s.MuhasebeHatasi("tur_degistirilemez", "tur")
        tarih = s.tarih_duzelt(al("tarih") or s.bugun().isoformat(), "tarih")
        if "tutar" in g or mevcut is None:
            ham_tutar = s.kurus_coz(g.get("tutar"), "tutar")
        else:
            ham_tutar = int(mevcut.tutar)
        hesap_id = s.kimlik(al("hesap_id"), "hesap_id")
        cari_id = s.kimlik(al("cari_id"), "cari_id")
        aciklama = s.bos_ya_da(al("aciklama"), "aciklama", 300)
        belge_no = s.bos_ya_da(al("belge_no"), "belge_no", 60)
        etiketler = s.etiketler_duzelt(g["etiketler"]) if "etiketler" in g else (s.json_yukle(mevcut.etiketler, []) if mevcut else [])
    except s.TemelHata as h:
        raise _e(h)
    hesap = await _bul(db, MuhasebeHesaplari, kapsam, hesap_id, "hesap_bulunamadi", "hesap_id") if hesap_id else None
    cari = await _bul(db, MuhasebeCariler, kapsam, cari_id, "cari_bulunamadi", "cari_id") if cari_id else None
    if hesap is not None and hesap.arsiv and not (mevcut and mevcut.hesap_id == hesap.id):
        raise _hata(400, "hesap_arsivde", alan="hesap_id")
    if cari is not None and cari.arsiv and not (mevcut and mevcut.cari_id == cari.id):
        raise _hata(400, "cari_arsivde", alan="cari_id")
    sonuc: Dict[str, Any] = {"tur": tur, "tarih": tarih, "hesap_id": hesap_id, "cari_id": cari_id, "aciklama": aciklama,
                             "belge_no": belge_no, "etiketler": s.json_yaz(etiketler) if etiketler else None}
    if tur == "virman":
        try:
            hedef_id = s.kimlik(al("hedef_hesap_id"), "hedef_hesap_id")
        except s.TemelHata as h:
            raise _e(h)
        if hesap is None:
            raise _hata(400, "hesap_gerekli", alan="hesap_id")
        hedef = await _bul(db, MuhasebeHesaplari, kapsam, hedef_id, "hesap_bulunamadi", "hedef_hesap_id") if hedef_id else None
        if hedef is None:
            raise _hata(400, "hesap_gerekli", alan="hedef_hesap_id")
        if hedef.id == hesap.id:
            raise _hata(400, "ayni_hesap", alan="hedef_hesap_id")
        if hedef.arsiv and not (mevcut and mevcut.hedef_hesap_id == hedef.id):
            raise _hata(400, "hesap_arsivde", alan="hedef_hesap_id")
        hedef_tutar = None
        if hedef.para_birimi != hesap.para_birimi:
            ham = g.get("hedef_tutar") if "hedef_tutar" in g else (mevcut.hedef_tutar if mevcut else None)
            if ham in (None, ""):
                raise _hata(400, "hedef_tutar_gerekli", alan="hedef_tutar")
            try:
                hedef_tutar = ham if isinstance(ham, int) and "hedef_tutar" not in g else s.kurus_coz(ham, "hedef_tutar")
            except s.TemelHata as h:
                raise _e(h)
        sonuc.update({"tutar": ham_tutar, "para_birimi": hesap.para_birimi, "kdv_orani": None, "kdv_tutari": 0, "kategori_id": None,
                      "cari_id": None, "hedef_hesap_id": hedef.id, "hedef_tutar": hedef_tutar, "vade_tarihi": None})
        return sonuc
    if tur in ("tahsilat", "odeme"):
        if hesap is None:
            raise _hata(400, "hesap_gerekli", alan="hesap_id")
        if cari is None:
            raise _hata(400, "cari_gerekli", alan="cari_id")
    elif hesap is None and cari is None:
        raise _hata(400, "hesap_ya_da_cari_gerekli", alan="hesap_id")
    if hesap is not None and cari is not None and hesap.para_birimi != cari.para_birimi:
        raise _hata(400, "para_birimi_uyusmuyor", alan="cari_id")
    try:
        istenen_pb = s.para_birimi_duzelt(al("para_birimi"), varsayilan="") if al("para_birimi") else None
    except s.TemelHata as h:
        raise _e(h)
    pb = hesap.para_birimi if hesap else (cari.para_birimi if cari else (istenen_pb or "TRY"))
    if istenen_pb and istenen_pb != pb and ("para_birimi" in g):
        raise _hata(400, "para_birimi_uyusmuyor", alan="para_birimi")
    kdv_orani: Optional[int] = None
    kdv = 0
    tutar = ham_tutar
    kategori_id: Optional[int] = None
    if tur in ("gelir", "gider"):
        try:
            kdv_orani = s.kdv_orani_duzelt(al("kdv_orani"))
            kdv_dahil = g.get("kdv_dahil", True)
            if not isinstance(kdv_dahil, bool):
                raise s.MuhasebeHatasi("evet_hayir_gecersiz", "kdv_dahil")
            if not kdv_dahil and "tutar" in g:
                kdv = s.kdv_haricten(ham_tutar, kdv_orani)
                tutar = ham_tutar + kdv
            else:
                kdv = s.kdv_dahilden(tutar, kdv_orani)
            if g.get("kdv_tutari") not in (None, ""):
                kdv = s.kurus_coz(g.get("kdv_tutari"), "kdv_tutari", sifir_olabilir=True)
                if kdv > tutar:
                    raise s.MuhasebeHatasi("kdv_tutari_buyuk", "kdv_tutari")
            elif mevcut is not None and "tutar" not in g and "kdv_orani" not in g:
                kdv = int(mevcut.kdv_tutari or 0)
            kategori_id = s.kimlik(al("kategori_id"), "kategori_id")
        except s.TemelHata as h:
            raise _e(h)
        if kategori_id:
            kat = await _bul(db, MuhasebeKategorileri, kapsam, kategori_id, "kategori_bulunamadi", "kategori_id")
            if kat.tur != tur:
                raise _hata(400, "kategori_turu_uyusmuyor", alan="kategori_id")
    vade = None
    if tur in ("gelir", "gider") and hesap is None and cari is not None:
        try:
            vade = s.bos_tarih(al("vade_tarihi"), "vade_tarihi") or tarih
        except s.TemelHata as h:
            raise _e(h)
        if vade < tarih:
            raise _hata(400, "vade_once", alan="vade_tarihi")
    sonuc.update({"tutar": tutar, "para_birimi": pb, "kdv_orani": kdv_orani, "kdv_tutari": kdv, "kategori_id": kategori_id,
                  "hedef_hesap_id": None, "hedef_tutar": None, "vade_tarihi": vade})
    return sonuc


def _hareket_otomatik_mi(h: H) -> bool:
    return h.kaynak not in s.ELLE_KAYNAKLAR or h.ters_edilen_id is not None


async def _tekrar_girdisi(db: AsyncSession, kapsam: Kapsam, g: Dict[str, Any], mevcut: Optional[MuhasebeTekrarlar] = None) -> Dict[str, Any]:
    def al(alan: str, varsayilan: Any = None) -> Any:
        if alan in g:
            return g.get(alan)
        return getattr(mevcut, alan, varsayilan) if mevcut is not None else varsayilan

    try:
        tur = s.secim(al("tur"), "tur", s.KATEGORI_TURLERI)
        aciklama = s.metin(al("aciklama"), "aciklama", 300, zorunlu=True)
        tutar = s.kurus_coz(g.get("tutar"), "tutar") if ("tutar" in g or mevcut is None) else int(mevcut.tutar)
        kdv_orani = s.kdv_orani_duzelt(al("kdv_orani"))
        periyot = s.secim(al("periyot"), "periyot", s.PERIYOTLAR, "aylik")
        baslangic = s.tarih_duzelt(al("baslangic") or s.bugun().isoformat(), "baslangic")
        bitis = s.bos_tarih(al("bitis"), "bitis")
        if bitis and bitis < baslangic:
            raise s.MuhasebeHatasi("bitis_once", "bitis")
        hesap_id = s.kimlik(al("hesap_id"), "hesap_id")
        cari_id = s.kimlik(al("cari_id"), "cari_id")
        kategori_id = s.kimlik(al("kategori_id"), "kategori_id")
        aktif = s.bool_duzelt(al("aktif", True), "aktif")
        etiketler = s.etiketler_duzelt(g["etiketler"]) if "etiketler" in g else (s.json_yukle(mevcut.etiketler, []) if mevcut else [])
    except s.TemelHata as h:
        raise _e(h)
    hesap = await _bul(db, MuhasebeHesaplari, kapsam, hesap_id, "hesap_bulunamadi", "hesap_id") if hesap_id else None
    cari = await _bul(db, MuhasebeCariler, kapsam, cari_id, "cari_bulunamadi", "cari_id") if cari_id else None
    if hesap is None and cari is None:
        raise _hata(400, "hesap_ya_da_cari_gerekli", alan="hesap_id")
    if hesap is not None and cari is not None and hesap.para_birimi != cari.para_birimi:
        raise _hata(400, "para_birimi_uyusmuyor", alan="cari_id")
    if kategori_id:
        kat = await _bul(db, MuhasebeKategorileri, kapsam, kategori_id, "kategori_bulunamadi", "kategori_id")
        if kat.tur != tur:
            raise _hata(400, "kategori_turu_uyusmuyor", alan="kategori_id")
    pb = hesap.para_birimi if hesap else cari.para_birimi  # type: ignore[union-attr]
    return {"tur": tur, "aciklama": aciklama, "tutar": tutar, "kdv_orani": kdv_orani, "periyot": periyot, "baslangic": baslangic,
            "bitis": bitis, "hesap_id": hesap_id, "cari_id": cari_id, "kategori_id": kategori_id, "aktif": aktif,
            "para_birimi": pb, "etiketler": s.json_yaz(etiketler) if etiketler else None}


def _ilk_donem(baslangic: date, periyot: str, gecmisi_de: bool, son: Optional[date] = None) -> date:
    """Bir sonraki üretilecek dönem: geçmiş istenmediyse bugün ya da sonrası; son üretilenden sonra."""
    esik = s.bugun()
    if gecmisi_de:
        esik = baslangic
    if son is not None:
        esik = max(esik, son + timedelta(days=1))
    if baslangic >= esik:
        return baslangic
    return s.sonraki_donem(baslangic, periyot, esik - timedelta(days=1))


# ---------------------------------------------------------------------------
# Uçlar
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[..., Kapsam]) -> None:  # noqa: C901
    # ------------------------------------------------------------- meta / ayarlar
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        if not kapsam.salt_okunur:
            a = await k.ayar_al(db, kapsam.anahtar, kapsam.hesap)
            if not a.kategoriler_tohumlandi:
                await k.kategorileri_tohumla(db, kapsam.anahtar, kapsam.hesap)
                await db.commit()
        a = await _ayar(db, kapsam)
        etki = await k.hesap_bakiyeleri(db, kapsam.anahtar)
        sayilar = dict((await db.execute(k.hareket_sayilari_sorgusu(kapsam.anahtar, H.hesap_id))).all())
        hesaplar = (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam.anahtar)
                                     .order_by(MuhasebeHesaplari.arsiv, MuhasebeHesaplari.sira, MuhasebeHesaplari.id))).scalars().all()
        kategoriler = (await db.execute(select(MuhasebeKategorileri).where(MuhasebeKategorileri.kapsam == kapsam.anahtar)
                                        .order_by(MuhasebeKategorileri.tur, MuhasebeKategorileri.sira, MuhasebeKategorileri.id))).scalars().all()
        moduller: Dict[str, bool] = {}
        if kapsam.hesap:
            from services.moduller import modul_acik_mi

            for kaynak, modul in s.AKTARIM_MODULU.items():
                moduller[kaynak] = await modul_acik_mi(db, kapsam.hesap, modul)
        cari_sayisi = int((await db.execute(select(func.count(MuhasebeCariler.id)).where(MuhasebeCariler.kapsam == kapsam.anahtar))).scalar() or 0)
        return {
            "yonetici": kapsam.yonetici, "hesap": kapsam.hesap, "ajans": kapsam.hesap is None, "salt_okunur": kapsam.salt_okunur,
            "okur": kapsam.okur, "oneri_sayisi": 0 if kapsam.okur else await k.oneri_sayisi(db, kapsam.anahtar),
            "kisi": kapsam.kisi, "bugun": s.bugun().isoformat(), "hesap_siniri": await _hesap_siniri(db, kapsam),
            "ayarlar": _ayar_sozlugu(a, kapsam),
            "hesaplar": [_hesap_sozlugu(h, etki.get(h.id, 0), sayilar.get(h.id, 0)) for h in hesaplar],
            "kategoriler": [_kategori_sozlugu(x) for x in kategoriler], "cari_sayisi": cari_sayisi,
            "aktarim_kaynaklari": list(s.AJANS_AKTARIMLARI if kapsam.hesap is None else s.MUSTERI_AKTARIMLARI),
            "aktarim_modulleri": moduller,
            "sabitler": {"hesap_turleri": list(s.HESAP_TURLERI), "hareket_turleri": list(s.HAREKET_TURLERI),
                         "para_birimleri": list(s.PARA_BIRIMLERI), "kdv_oranlari": list(s.KDV_ORANLARI),
                         "periyotlar": list(s.PERIYOTLAR), "cari_turleri": list(s.CARI_TURLERI), "kovalar": list(s.KOVALAR),
                         "tarih_bicimleri": list(s.TARIH_BICIMLERI), "en_cok_csv": s.EN_COK_CSV_SATIR,
                         "bagli_turler": [t for t in s.BAGLI_TURLER if (t in ("crm_aday", "musteri_hesabi")) == (kapsam.hesap is None)]},
        }

    @router.get("/ozet")
    async def ozet(request: Request, db: AsyncSession = Depends(get_db)):
        """Panel özeti: bakiyeler (para birimine göre), bu ay gelir/gider, bütçe durumu, vadesi geçen alacak, son hareketler
        (okurda yok), onay bekleyen öneri sayısı."""
        kapsam = kapsam_al(request, rapor=True)
        bugun = s.bugun()
        ay = s.ay_anahtari(bugun)
        a = await _ayar(db, kapsam)
        etki = await k.hesap_bakiyeleri(db, kapsam.anahtar)
        bakiyeler: Dict[str, int] = {}
        for h in (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam.anahtar,
                                                                   MuhasebeHesaplari.arsiv.is_(False)))).scalars().all():
            bakiyeler[h.para_birimi] = bakiyeler.get(h.para_birimi, 0) + int(h.acilis_bakiyesi or 0) + etki.get(h.id, 0)
        bas, bit = s.ay_araligi(ay)
        bu_ay: Dict[str, Dict[str, int]] = {}
        for tur, pb, toplam in (await db.execute(select(H.tur, H.para_birimi, func.sum(H.tutar)).where(
                H.kapsam == kapsam.anahtar, H.tur.in_(("gelir", "gider")), H.tarih >= bas, H.tarih <= bit).group_by(H.tur, H.para_birimi))).all():
            bu_ay.setdefault(pb, {"gelir": 0, "gider": 0})[tur] = int(toplam or 0)
        butce = await k.butce_durumu(db, kapsam.anahtar, ay, a.uyari_yuzde if a else 80)
        cariler = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam.anahtar,
                                                                  MuhasebeCariler.arsiv.is_(False)).limit(2000))).scalars().all()
        yas = await k.cari_yaslandirma(db, kapsam.anahtar, cariler, bugun, "alacak")
        gecikmis: Dict[str, int] = {}
        gecikmis_cari = 0
        for c in cariler:
            y = yas.get(c.id)
            tutar = sum(x.kalan for x in (y.kalemler if y else []) if (bugun - x.vade).days > 0)
            if tutar > 0:
                gecikmis[c.para_birimi] = gecikmis.get(c.para_birimi, 0) + tutar
                gecikmis_cari += 1
        adlar = await _adlar(db, kapsam)
        son = [] if kapsam.okur else (await db.execute(select(H).where(H.kapsam == kapsam.anahtar)
                                                       .order_by(H.tarih.desc(), H.id.desc()).limit(8))).scalars().all()
        cari_ad = await _cari_adlari(db, [x.cari_id for x in son])
        return {
            "ay": ay, "bakiyeler": [{"para_birimi": pb, "bakiye": v} for pb, v in sorted(bakiyeler.items())],
            "bu_ay": [{"para_birimi": pb, **v, "net": v["gelir"] - v["gider"]} for pb, v in sorted(bu_ay.items())],
            "butce": {"asim_sayisi": butce["asim_sayisi"],
                      "uyarilar": [x for x in butce["kalemler"] if x["durum"] in ("asildi", "yaklasti")]},
            "gecikmis_alacak": [{"para_birimi": pb, "tutar": v} for pb, v in sorted(gecikmis.items())], "gecikmis_cari": gecikmis_cari,
            "son_hareketler": [_hareket_sozlugu(x, adlar, cari_ad) for x in son],
            "oneri_sayisi": 0 if kapsam.okur else await k.oneri_sayisi(db, kapsam.anahtar),
        }

    @router.get("/ayarlar")
    async def ayarlar(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return _ayar_sozlugu(await _ayar(db, kapsam), kapsam)

    @router.put("/ayarlar")
    async def ayarlar_yaz(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        a = await k.ayar_al(db, kapsam.anahtar, kapsam.hesap)
        try:
            if "firma_adi" in g:
                a.firma_adi = s.metin(g.get("firma_adi"), "firma_adi", 160) or None
            if "para_birimi" in g:
                a.para_birimi = s.para_birimi_duzelt(g.get("para_birimi"))
            if "uyari_yuzde" in g:
                a.uyari_yuzde = s.tam_sayi(g.get("uyari_yuzde"), "uyari_yuzde", 1, 100)
            if "aktarim" in g:
                a.aktarim = s.json_yaz(await _aktarim_duzelt(db, kapsam, a, g.get("aktarim")))
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)
        a.updated_at = s.simdi()
        await db.commit()
        await db.refresh(a)
        return _ayar_sozlugu(a, kapsam)

    @router.post("/esitle")
    async def esitle(request: Request, db: AsyncSession = Depends(get_db)):
        """Tekrarlayan kayıtların vadesi gelenleri + açık otomatik aktarmalar + bütçe aşım denetimi."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        return await k.esitle(db, kapsam.anahtar, kapsam.hesap)

    # ------------------------------------------------------------- hesaplar
    @router.get("/hesaplar")
    async def hesap_listesi(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        etki = await k.hesap_bakiyeleri(db, kapsam.anahtar)
        sayilar = dict((await db.execute(k.hareket_sayilari_sorgusu(kapsam.anahtar, H.hesap_id))).all())
        hesaplar = (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam.anahtar)
                                     .order_by(MuhasebeHesaplari.arsiv, MuhasebeHesaplari.sira, MuhasebeHesaplari.id))).scalars().all()
        items = [_hesap_sozlugu(h, etki.get(h.id, 0), sayilar.get(h.id, 0)) for h in hesaplar]
        toplamlar: Dict[str, int] = {}
        for x in items:
            if not x["arsiv"]:
                toplamlar[x["para_birimi"]] = toplamlar.get(x["para_birimi"], 0) + x["bakiye"]
        return {"items": items, "toplamlar": [{"para_birimi": pb, "bakiye": v} for pb, v in sorted(toplamlar.items())]}

    async def _hesap_uygula(h: MuhasebeHesaplari, g: Dict[str, Any], yeni: bool) -> None:
        try:
            if yeni or "tur" in g:
                if not yeni and g.get("tur") != h.tur:
                    raise s.MuhasebeHatasi("tur_degistirilemez", "tur")
                h.tur = s.secim(g.get("tur"), "tur", s.HESAP_TURLERI)
            if yeni or "ad" in g:
                h.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
            if yeni or "para_birimi" in g:
                pb = s.para_birimi_duzelt(g.get("para_birimi"))
                if not yeni and pb != h.para_birimi and await k.kullanimda_mi(db, h.kapsam, hesap_id=h.id):
                    raise s.MuhasebeHatasi("para_birimi_kilitli", "para_birimi")
                h.para_birimi = pb
            if yeni or "acilis_bakiyesi" in g:
                h.acilis_bakiyesi = s.kurus_coz(g.get("acilis_bakiyesi"), "acilis_bakiyesi", eksi_olabilir=True, sifir_olabilir=True,
                                                bos_olabilir=True) or 0
            if yeni or "acilis_tarihi" in g:
                h.acilis_tarihi = s.bos_tarih(g.get("acilis_tarihi"), "acilis_tarihi") or (h.acilis_tarihi if not yeni else s.bugun())
            if "notlar" in g:
                h.notlar = s.bos_ya_da(g.get("notlar"), "notlar", 1000, cok_satir=True)
            if "arsiv" in g:
                h.arsiv = s.bool_duzelt(g.get("arsiv"), "arsiv")
            if "sira" in g:
                h.sira = s.tam_sayi(g.get("sira"), "sira", 0, 1000)
            # Türüne göre bilgiler: bankada IBAN (yalnız biçim), kartta yalnız son 4 hane. Hesap/kart numarası YOK.
            if h.tur == "banka":
                if "iban" in g or yeni:
                    h.iban = s.iban_duzelt(g.get("iban"))
                if "banka_adi" in g or yeni:
                    h.banka_adi = s.bos_ya_da(g.get("banka_adi"), "banka_adi", 120)
                h.son4 = None
            elif h.tur == "kredi_karti":
                if "son4" in g or yeni:
                    h.son4 = s.son4_duzelt(g.get("son4"))
                if "banka_adi" in g or yeni:
                    h.banka_adi = s.bos_ya_da(g.get("banka_adi"), "banka_adi", 120)
                h.iban = None
            elif h.tur == "pos":
                # POS / sanal POS: yalnız sağlayıcı adı (`banka_adi`: iyzico, PayTR, Lemon Squeezy…); üye işyeri no tutulmaz.
                if "banka_adi" in g or yeni:
                    h.banka_adi = s.bos_ya_da(g.get("banka_adi"), "banka_adi", 120)
                h.iban = h.son4 = None
            else:
                h.iban = h.son4 = None
                if "banka_adi" in g:
                    h.banka_adi = None
        except s.TemelHata as hata:
            raise _e(hata)

    def _numara_yok(g: Dict[str, Any]) -> None:
        """Hesap / kart numarası alınmaz ve saklanmaz (bankada yalnız IBAN metni, kartta son 4 hane)."""
        for yasak in ("hesap_no", "hesap_numarasi", "kart_no", "kart_numarasi"):
            if g.get(yasak):
                raise _hata(400, "numara_saklanmaz", alan=yasak)

    @router.post("/hesaplar")
    async def hesap_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        _numara_yok(g)
        h = MuhasebeHesaplari(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, created_at=s.simdi())
        await _hesap_uygula(h, g, True)
        sinir = await _hesap_siniri(db, kapsam)
        if sinir is not None and not h.arsiv:
            n = int((await db.execute(select(func.count(MuhasebeHesaplari.id)).where(
                MuhasebeHesaplari.kapsam == kapsam.anahtar, MuhasebeHesaplari.arsiv.is_(False)))).scalar() or 0)
            if n >= sinir:
                raise _hata(409, "hesap_siniri", en_cok=sinir)
        db.add(h)
        await db.commit()
        await db.refresh(h)
        return _hesap_sozlugu(h)

    @router.put("/hesaplar/{hid}")
    async def hesap_guncelle(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        _numara_yok(g)
        h = await _bul(db, MuhasebeHesaplari, kapsam, hid)
        arsivdeydi = bool(h.arsiv)
        await _hesap_uygula(h, g, False)
        sinir = await _hesap_siniri(db, kapsam)
        if arsivdeydi and not h.arsiv and sinir is not None:
            n = int((await db.execute(select(func.count(MuhasebeHesaplari.id)).where(
                MuhasebeHesaplari.kapsam == kapsam.anahtar, MuhasebeHesaplari.arsiv.is_(False), MuhasebeHesaplari.id != h.id))).scalar() or 0)
            if n >= sinir:
                await db.rollback()
                raise _hata(409, "hesap_siniri", en_cok=sinir)
        h.updated_at = s.simdi()
        await db.commit()
        await db.refresh(h)
        etki = await k.hesap_bakiyeleri(db, kapsam.anahtar)
        return _hesap_sozlugu(h, etki.get(h.id, 0))

    @router.delete("/hesaplar/{hid}")
    async def hesap_sil(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Hareketi / tekrarı / aktarım ayarı olan hesap silinmez (arşive alınır) → 409. Boş hesap çöp kutusuna."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        h = await _bul(db, MuhasebeHesaplari, kapsam, hid)
        a = await _ayar(db, kapsam)
        aktarimda = any(h.id in [v.get(x) for x in s.AKTARIM_HESAPLARI[kk]] for kk, v in k.aktarim_ayarlari(a, kapsam.anahtar).items())
        if aktarimda or await k.kullanimda_mi(db, kapsam.anahtar, hesap_id=h.id):
            raise _hata(409, "hesap_kullaniliyor")
        await db.delete(h)
        await db.commit()
        return {"ok": True}

    @router.post("/virman")
    async def virman(request: Request, db: AsyncSession = Depends(get_db)):
        """Hesaplar arası virman: {kaynak_hesap_id, hedef_hesap_id, tutar, hedef_tutar?, tarih?, aciklama?}. Para birimleri
        farklıysa giriş tutarı (`hedef_tutar`) kullanıcıdan — dönüşüm yapılmaz."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        govde = {"tur": "virman", "hesap_id": g.get("kaynak_hesap_id", g.get("hesap_id")), "hedef_hesap_id": g.get("hedef_hesap_id"),
                 "tutar": g.get("tutar"), "hedef_tutar": g.get("hedef_tutar"), "tarih": g.get("tarih"), "aciklama": g.get("aciklama"),
                 "belge_no": g.get("belge_no")}
        alanlar = await _hareket_girdisi(db, kapsam, govde)
        h = H(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, kaynak="manuel", olusturan=kapsam.kisi, created_at=s.simdi(), **alanlar)
        db.add(h)
        await db.commit()
        await db.refresh(h)
        return _hareket_sozlugu(h, await _adlar(db, kapsam), {})

    # ------------------------------------------------------------- kategoriler
    @router.get("/kategoriler")
    async def kategori_listesi(request: Request, tur: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(MuhasebeKategorileri).where(MuhasebeKategorileri.kapsam == kapsam.anahtar)
        if tur in s.KATEGORI_TURLERI:
            sorgu = sorgu.where(MuhasebeKategorileri.tur == tur)
        sayilar = dict((await db.execute(k.hareket_sayilari_sorgusu(kapsam.anahtar, H.kategori_id))).all())
        items = (await db.execute(sorgu.order_by(MuhasebeKategorileri.tur, MuhasebeKategorileri.sira, MuhasebeKategorileri.id))).scalars().all()
        return {"items": [_kategori_sozlugu(x, sayilar.get(x.id, 0)) for x in items]}

    @router.post("/kategoriler")
    async def kategori_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        try:
            x = MuhasebeKategorileri(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, tur=s.secim(g.get("tur"), "tur", s.KATEGORI_TURLERI),
                                     ad=s.metin(g.get("ad"), "ad", 80, zorunlu=True), renk=s.renk_duzelt(g.get("renk")),
                                     sira=s.tam_sayi(g.get("sira", 50), "sira", 0, 1000), created_at=s.simdi())
        except s.TemelHata as h:
            raise _e(h)
        db.add(x)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kategori_var", alan="ad")
        await db.refresh(x)
        return _kategori_sozlugu(x)

    @router.put("/kategoriler/{kid}")
    async def kategori_guncelle(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        x = await _bul(db, MuhasebeKategorileri, kapsam, kid)
        try:
            if "ad" in g:
                x.ad = s.metin(g.get("ad"), "ad", 80, zorunlu=True)
            if "renk" in g:
                x.renk = s.renk_duzelt(g.get("renk"))
            if "arsiv" in g:
                x.arsiv = s.bool_duzelt(g.get("arsiv"), "arsiv")
            if "sira" in g:
                x.sira = s.tam_sayi(g.get("sira"), "sira", 0, 1000)
            if "tur" in g and g.get("tur") != x.tur:
                raise s.MuhasebeHatasi("tur_degistirilemez", "tur")
        except s.TemelHata as h:
            raise _e(h)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kategori_var", alan="ad")
        await db.refresh(x)
        return _kategori_sozlugu(x)

    @router.delete("/kategoriler/{kid}")
    async def kategori_sil(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        x = await _bul(db, MuhasebeKategorileri, kapsam, kid)
        if await k.kullanimda_mi(db, kapsam.anahtar, kategori_id=x.id):
            raise _hata(409, "kategori_kullaniliyor")
        await db.delete(x)
        await db.commit()
        return {"ok": True}

    @router.post("/kategoriler/varsayilanlar")
    async def kategori_varsayilanlari(request: Request, db: AsyncSession = Depends(get_db)):
        """Silinen varsayılan kategorileri geri ekler (var olanlara dokunmaz)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        await k.ayar_al(db, kapsam.anahtar, kapsam.hesap)
        n = await k.varsayilanlari_ekle(db, kapsam.anahtar, kapsam.hesap)
        await db.commit()
        return {"eklenen": n}

    # ------------------------------------------------------------- hareketler
    def _hareket_suzgeci(kapsam: Kapsam, q: Dict[str, Any]):
        kosul = [H.kapsam == kapsam.anahtar]
        try:
            if q.get("bas"):
                kosul.append(H.tarih >= s.tarih_duzelt(q["bas"], "bas"))
            if q.get("bit"):
                kosul.append(H.tarih <= s.tarih_duzelt(q["bit"], "bit"))
        except s.TemelHata as h:
            raise _e(h)
        if q.get("tur") in s.HAREKET_TURLERI:
            kosul.append(H.tur == q["tur"])
        if q.get("hesap_id"):
            kosul.append(or_(H.hesap_id == q["hesap_id"], H.hedef_hesap_id == q["hesap_id"]))
        if q.get("kategori_id"):
            kosul.append(H.kategori_id == q["kategori_id"])
        if q.get("cari_id"):
            kosul.append(H.cari_id == q["cari_id"])
        if q.get("kaynak") in s.KAYNAKLAR:
            kosul.append(H.kaynak == q["kaynak"])
        if q.get("etiket"):
            kosul.append(H.etiketler.like(f'%"{str(q["etiket"]).strip().lower()[:30]}"%'))
        if q.get("ara"):
            ara = f"%{str(q['ara']).strip()[:80]}%"
            kosul.append(or_(H.aciklama.ilike(ara), H.belge_no.ilike(ara)))
        return kosul

    def _q(bas, bit, tur, hesap_id, kategori_id, cari_id, kaynak, etiket, ara) -> Dict[str, Any]:
        return {"bas": bas, "bit": bit, "tur": tur, "hesap_id": hesap_id, "kategori_id": kategori_id, "cari_id": cari_id,
                "kaynak": kaynak, "etiket": etiket, "ara": ara}

    @router.get("/hareketler")
    async def hareket_listesi(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                              tur: Optional[str] = Query(None), hesap_id: Optional[int] = Query(None),
                              kategori_id: Optional[int] = Query(None), cari_id: Optional[int] = Query(None),
                              kaynak: Optional[str] = Query(None), etiket: Optional[str] = Query(None), ara: Optional[str] = Query(None),
                              sayfa: int = Query(1, ge=1, le=10000), adet: int = Query(50, ge=1, le=200),
                              db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        kosul = _hareket_suzgeci(kapsam, _q(bas, bit, tur, hesap_id, kategori_id, cari_id, kaynak, etiket, ara))
        toplam = int((await db.execute(select(func.count(H.id)).where(*kosul))).scalar() or 0)
        satirlar = (await db.execute(select(H).where(*kosul).order_by(H.tarih.desc(), H.id.desc())
                                     .offset((sayfa - 1) * adet).limit(adet))).scalars().all()
        toplamlar: Dict[str, Dict[str, int]] = {}
        for t, pb, top in (await db.execute(select(H.tur, H.para_birimi, func.sum(H.tutar)).where(*kosul).group_by(H.tur, H.para_birimi))).all():
            d = toplamlar.setdefault(pb, {"gelir": 0, "gider": 0, "tahsilat": 0, "odeme": 0, "virman": 0})
            d[t] = int(top or 0)
        ekler = dict((await db.execute(select(MuhasebeEkleri.hareket_id, func.count(MuhasebeEkleri.id)).where(
            MuhasebeEkleri.hareket_id.in_([x.id for x in satirlar] or [0])).group_by(MuhasebeEkleri.hareket_id))).all())
        adlar = await _adlar(db, kapsam)
        cari_ad = await _cari_adlari(db, [x.cari_id for x in satirlar])
        return {"items": [_hareket_sozlugu(x, adlar, cari_ad, ekler.get(x.id, 0)) for x in satirlar], "toplam": toplam,
                "sayfa": sayfa, "adet": adet,
                "toplamlar": [{"para_birimi": pb, **v, "net": v["gelir"] - v["gider"]} for pb, v in sorted(toplamlar.items())]}

    @router.post("/hareketler")
    async def hareket_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        alanlar = await _hareket_girdisi(db, kapsam, g)
        h = H(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, kaynak="manuel", olusturan=kapsam.kisi, created_at=s.simdi(), **alanlar)
        db.add(h)
        await db.commit()
        await db.refresh(h)
        uyari = 0
        if h.tur == "gider":
            uyari = await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, [s.ay_anahtari(h.tarih)])
            await db.commit()
        d = _hareket_sozlugu(h, await _adlar(db, kapsam), await _cari_adlari(db, [h.cari_id or 0]))
        d["butce_asimi"] = uyari
        return d

    @router.get("/hareketler.csv")
    async def hareket_csv(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                          tur: Optional[str] = Query(None), hesap_id: Optional[int] = Query(None),
                          kategori_id: Optional[int] = Query(None), cari_id: Optional[int] = Query(None),
                          kaynak: Optional[str] = Query(None), etiket: Optional[str] = Query(None), ara: Optional[str] = Query(None),
                          db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _dosya(kapsam)
        kosul = _hareket_suzgeci(kapsam, _q(bas, bit, tur, hesap_id, kategori_id, cari_id, kaynak, etiket, ara))
        satirlar = (await db.execute(select(H).where(*kosul).order_by(H.tarih, H.id).limit(20000))).scalars().all()
        adlar = await _adlar(db, kapsam)
        cari_ad = await _cari_adlari(db, [x.cari_id for x in satirlar])
        basliklar = ["tarih", "tur", "tutar", "para_birimi", "kdv_orani", "kdv_tutari", "kategori", "hesap", "hedef_hesap", "hedef_tutar",
                     "cari", "vade_tarihi", "aciklama", "belge_no", "etiketler", "kaynak", "ters_kayit"]
        veri = []
        for x in satirlar:
            kat = adlar["kategori"].get(x.kategori_id) if x.kategori_id else None
            hes = adlar["hesap"].get(x.hesap_id) if x.hesap_id else None
            hed = adlar["hesap"].get(x.hedef_hesap_id) if x.hedef_hesap_id else None
            veri.append([x.tarih.isoformat(), x.tur, s.kurus_metni(x.tutar), x.para_birimi, x.kdv_orani if x.kdv_orani is not None else "",
                         s.kurus_metni(x.kdv_tutari or 0), kat.ad if kat else "", hes.ad if hes else "", hed.ad if hed else "",
                         s.kurus_metni(x.hedef_tutar) if x.hedef_tutar is not None else "", cari_ad.get(x.cari_id, "") if x.cari_id else "",
                         s.gun_iso(x.vade_tarihi) or "", x.aciklama or "", x.belge_no or "",
                         ", ".join(s.json_yukle(x.etiketler, []) or []), x.kaynak, "evet" if x.ters_edilen_id else ""])
        return _csv_yaniti(s.csv_metni(basliklar, veri), "hareketler.csv")

    @router.get("/hareketler.pdf")
    async def hareket_pdf(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                          tur: Optional[str] = Query(None), hesap_id: Optional[int] = Query(None),
                          kategori_id: Optional[int] = Query(None), cari_id: Optional[int] = Query(None),
                          kaynak: Optional[str] = Query(None), etiket: Optional[str] = Query(None), ara: Optional[str] = Query(None),
                          dil: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _dosya(kapsam)
        q = _q(bas, bit, tur, hesap_id, kategori_id, cari_id, kaynak, etiket, ara)
        kosul = _hareket_suzgeci(kapsam, q)
        satirlar = (await db.execute(select(H).where(*kosul).order_by(H.tarih, H.id).limit(2000))).scalars().all()
        adlar = await _adlar(db, kapsam)
        toplamlar: Dict[str, Dict[str, int]] = {}
        veri = []
        for x in satirlar:
            kat = adlar["kategori"].get(x.kategori_id) if x.kategori_id else None
            hes = adlar["hesap"].get(x.hesap_id) if x.hesap_id else None
            veri.append({"tarih": x.tarih, "tur": x.tur, "aciklama": x.aciklama, "kategori": kat.ad if kat else "", "hesap": hes.ad if hes else "",
                         "tutar": int(x.tutar), "kdv": int(x.kdv_tutari or 0), "para_birimi": x.para_birimi, "ters": x.ters_edilen_id is not None})
            if x.tur in ("gelir", "gider"):
                d = toplamlar.setdefault(x.para_birimi, {"gelir": 0, "gider": 0})
                d[x.tur] += int(x.tutar)
        pdf = s.hareketler_pdf({"firma": await _firma(db, kapsam), "bas": s.bos_tarih(bas, "bas") if bas else None,
                                "bit": s.bos_tarih(bit, "bit") if bit else None, "satirlar": veri,
                                "toplamlar": [{"para_birimi": pb, **v, "net": v["gelir"] - v["gider"]} for pb, v in sorted(toplamlar.items())]},
                               dil or "tr")
        return _dosya_yaniti(pdf, "application/pdf", "hareketler.pdf")

    @router.get("/hareketler/{hid}")
    async def hareket_ayrinti(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        h = await _bul(db, H, kapsam, hid)
        ekler = (await db.execute(select(MuhasebeEkleri).where(MuhasebeEkleri.hareket_id == h.id, MuhasebeEkleri.kapsam == kapsam.anahtar)
                                  .order_by(MuhasebeEkleri.id))).scalars().all()
        d = _hareket_sozlugu(h, await _adlar(db, kapsam), await _cari_adlari(db, [h.cari_id or 0]), len(ekler))
        d["ekler"] = [{"id": e.id, "ad": e.ad, "tur": e.tur, "boyut": e.boyut, "created_at": s.iso(e.created_at)} for e in ekler]
        return d

    @router.put("/hareketler/{hid}")
    async def hareket_guncelle(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        h = await _bul(db, H, kapsam, hid)
        if _hareket_otomatik_mi(h):
            raise _hata(409, "otomatik_kayit")
        g.setdefault("tur", h.tur)
        eski_ay = s.ay_anahtari(h.tarih)
        alanlar = await _hareket_girdisi(db, kapsam, g, mevcut=h)
        for alan, deger in alanlar.items():
            setattr(h, alan, deger)
        h.updated_at = s.simdi()
        await db.commit()
        await db.refresh(h)
        if h.tur == "gider":
            await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, {eski_ay, s.ay_anahtari(h.tarih)})
            await db.commit()
        return _hareket_sozlugu(h, await _adlar(db, kapsam), await _cari_adlari(db, [h.cari_id or 0]))

    @router.delete("/hareketler/{hid}")
    async def hareket_sil(hid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Çöp kutusuna (ekleriyle birlikte). Otomatik yansıma / ters kayıt silinmez."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        h = await _bul(db, H, kapsam, hid)
        if _hareket_otomatik_mi(h):
            raise _hata(409, "otomatik_kayit")
        for e in (await db.execute(select(MuhasebeEkleri).where(MuhasebeEkleri.hareket_id == h.id))).scalars().all():
            await db.delete(e)
        await db.delete(h)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- ekler
    @router.post("/hareketler/{hid}/ekler")
    async def ek_ekle(hid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        _dosya(kapsam)
        h = await _bul(db, H, kapsam, hid)
        from services import dosyalar

        try:
            sinir = min(await dosyalar.boyut_siniri_bayt(db), s.DOSYA_EN_COK_MB * 1024 * 1024)
            veri = await dosyalar.akistan_oku(dosya, sinir)
        except dosyalar.DosyaHatasi as hata:
            raise _hata(hata.durum, hata.kod, **hata.ek)
        try:
            e = await k.ek_kaydet(db, h, ad_ham=dosya.filename or "belge", veri=veri, yukleyen=kapsam.kisi)
        except s.TemelHata as hata:
            await db.rollback()
            raise _e(hata)
        await db.commit()
        await db.refresh(e)
        return {"id": e.id, "ad": e.ad, "tur": e.tur, "boyut": e.boyut, "created_at": s.iso(e.created_at)}

    @router.get("/ekler/{eid}")
    async def ek_indir(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        e = await _bul(db, MuhasebeEkleri, kapsam, eid)
        from services import dosya_deposu

        adres = dosya_deposu.dogrudan_adres(e.depo, e.depolama_anahtari, e.ad, e.tur)
        if adres:
            return RedirectResponse(adres, status_code=302, headers={"Cache-Control": "no-store"})
        try:
            veri = await dosya_deposu.oku(db, e.depo, e.depolama_anahtari)
        except dosya_deposu.DepoHatasi:
            raise _hata(502, "depo_hatasi")
        return Response(veri, media_type=e.tur, headers={"Content-Disposition": icerik_konumu(e.ad), "Cache-Control": "private, no-store",
                                                         "X-Content-Type-Options": "nosniff"})

    @router.delete("/ekler/{eid}")
    async def ek_sil(eid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        e = await _bul(db, MuhasebeEkleri, kapsam, eid)
        await db.delete(e)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- CSV içe aktarma
    @router.post("/ice-aktar/onizle")
    async def ice_aktar_onizle(request: Request, db: AsyncSession = Depends(get_db)):
        """{"csv", "ayirici"?} → başlıklar, ilk 10 satır, tahmini sütun eşlemesi (son kullanılan eşleme aynı başlıklara
        uyuyorsa o)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        _dosya(kapsam)
        g = await _govde(request, s.EN_COK_CSV_BAYT + 64 * 1024)
        try:
            basliklar, satirlar = s.csv_ayristir(str(g.get("csv") or ""), g.get("ayirici"))
        except s.TemelHata as h:
            raise _e(h)
        esleme = s.tahmini_esleme(basliklar)
        a = await _ayar(db, kapsam)
        son = s.json_yukle(a.csv_esleme if a else None, None)
        if isinstance(son, dict) and son.get("basliklar") == basliklar and isinstance(son.get("esleme"), dict):
            esleme = son["esleme"]
        return {"basliklar": basliklar, "ornek": satirlar[:10], "satir_sayisi": len(satirlar), "esleme": esleme,
                "tarih_bicimi": (son or {}).get("tarih_bicimi", "otomatik") if isinstance(son, dict) else "otomatik",
                "ondalik": (son or {}).get("ondalik", "otomatik") if isinstance(son, dict) else "otomatik"}

    @router.post("/ice-aktar")
    async def ice_aktar(request: Request, db: AsyncSession = Depends(get_db)):
        """Banka ekstresi: {"csv", "hesap_id", "esleme": {tarih, aciklama, tutar | giris + cikis, belge_no}, "tarih_bicimi",
        "ondalik", "gelir_kategori_id"?, "gider_kategori_id"?, "dene"?}. Artı tutar gelir, eksi gider; hatalı satır
        atlanır ve bildirilir; aynı satır ikinci kez yüklenirse atlanır (`tekrar`)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        _dosya(kapsam)
        g = await _govde(request, s.EN_COK_CSV_BAYT + 64 * 1024)
        try:
            basliklar, satirlar = s.csv_ayristir(str(g.get("csv") or ""), g.get("ayirici"))
            esleme = s.esleme_duzelt(g.get("esleme"), len(basliklar))
            tarih_bicimi = s.secim(g.get("tarih_bicimi"), "tarih_bicimi", s.TARIH_BICIMLERI, "otomatik")
            ondalik = s.secim(g.get("ondalik"), "ondalik", s.ONDALIKLAR, "otomatik")
            hesap_id = s.kimlik(g.get("hesap_id"), "hesap_id", bos_olabilir=False)
            gelir_k = s.kimlik(g.get("gelir_kategori_id"), "gelir_kategori_id")
            gider_k = s.kimlik(g.get("gider_kategori_id"), "gider_kategori_id")
            dene = g.get("dene") is True
        except s.TemelHata as h:
            raise _e(h)
        hesap = await _bul(db, MuhasebeHesaplari, kapsam, hesap_id, "hesap_bulunamadi", "hesap_id")
        if hesap.arsiv:
            raise _hata(400, "hesap_arsivde", alan="hesap_id")
        for kid, tur in ((gelir_k, "gelir"), (gider_k, "gider")):
            if kid:
                kat = await _bul(db, MuhasebeKategorileri, kapsam, kid, "kategori_bulunamadi", f"{tur}_kategori_id")
                if kat.tur != tur:
                    raise _hata(400, "kategori_turu_uyusmuyor", alan=f"{tur}_kategori_id")
        hatalar: List[Dict[str, Any]] = []
        gecerli: List[s.CsvSatiri] = []
        for i, satir in enumerate(satirlar):
            try:
                gecerli.append(s.csv_satiri_coz(i + 2, satir, esleme, tarih_bicimi, ondalik))
            except s.TemelHata as h:
                hatalar.append({"satir": i + 2, "kod": h.kod, "alan": h.alan})
        sayac: Dict[Tuple[Any, ...], int] = {}
        onceki = set((await db.execute(select(H.kaynak_id).where(H.kapsam == kapsam.anahtar, H.kaynak == "csv",
                                                                 H.kaynak_ref == str(hesap.id)))).scalars().all())
        eklenen = tekrar = 0
        aylar = set()
        onizleme = []
        for x in gecerli:
            anahtar = (x.tarih, x.tutar, x.aciklama, x.belge_no)
            sayac[anahtar] = sayac.get(anahtar, 0) + 1
            kimlik = s.csv_kimligi(hesap.id, x, sayac[anahtar])
            tur = "gelir" if x.tutar > 0 else "gider"
            if len(onizleme) < 10:
                onizleme.append({"satir": x.satir, "tarih": x.tarih.isoformat(), "tur": tur, "tutar": abs(x.tutar), "aciklama": x.aciklama})
            if kimlik in onceki:
                tekrar += 1
                continue
            if dene:
                eklenen += 1
                continue
            h = H(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, tur=tur, tarih=x.tarih, tutar=abs(x.tutar), para_birimi=hesap.para_birimi,
                  kdv_orani=None, kdv_tutari=0, kategori_id=gelir_k if tur == "gelir" else gider_k, hesap_id=hesap.id,
                  aciklama=x.aciklama or None, belge_no=x.belge_no, kaynak="csv", kaynak_ref=str(hesap.id), kaynak_id=kimlik,
                  olusturan=kapsam.kisi, created_at=s.simdi())
            try:
                async with db.begin_nested():
                    db.add(h)
                eklenen += 1
                aylar.add(s.ay_anahtari(x.tarih))
            except IntegrityError:
                tekrar += 1
        if not dene:
            a = await k.ayar_al(db, kapsam.anahtar, kapsam.hesap)
            a.csv_esleme = s.json_yaz({"basliklar": basliklar, "esleme": esleme, "tarih_bicimi": tarih_bicimi, "ondalik": ondalik})
            await db.commit()
            if aylar:
                await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, aylar)
                await db.commit()
        return {"dene": dene, "satir_sayisi": len(satirlar), "eklenen": eklenen, "tekrar": tekrar, "hata_sayisi": len(hatalar),
                "hatalar": hatalar[:100], "onizleme": onizleme}

    # ------------------------------------------------------------- tekrarlar
    @router.get("/tekrarlar")
    async def tekrar_listesi(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        items = (await db.execute(select(MuhasebeTekrarlar).where(MuhasebeTekrarlar.kapsam == kapsam.anahtar)
                                  .order_by(MuhasebeTekrarlar.aktif.desc(), MuhasebeTekrarlar.sonraki, MuhasebeTekrarlar.id))).scalars().all()
        return {"items": [_tekrar_sozlugu(t) for t in items]}

    @router.post("/tekrarlar")
    async def tekrar_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        """{tur, aciklama, tutar, periyot, baslangic, bitis?, hesap_id | cari_id, kategori_id?, kdv_orani?, gecmisi_de?}.
        `gecmisi_de` yoksa geçmiş dönemler üretilmez (ilk dönem bugün ya da sonrası)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        alanlar = await _tekrar_girdisi(db, kapsam, g)
        t = MuhasebeTekrarlar(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, olusturan=kapsam.kisi, created_at=s.simdi(), **alanlar)
        t.sonraki = _ilk_donem(t.baslangic, t.periyot, g.get("gecmisi_de") is True)
        if t.bitis and t.sonraki and t.sonraki > t.bitis:
            t.sonraki = None
        db.add(t)
        await db.flush()
        _, aylar = await k.tekrarlari_uret(db, kapsam.anahtar, kapsam.hesap)
        await db.commit()
        if aylar:
            await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, aylar)
            await db.commit()
        await db.refresh(t)
        return _tekrar_sozlugu(t)

    @router.put("/tekrarlar/{tid}")
    async def tekrar_guncelle(tid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        t = await _bul(db, MuhasebeTekrarlar, kapsam, tid)
        alanlar = await _tekrar_girdisi(db, kapsam, g, mevcut=t)
        takvim_degisti = alanlar["periyot"] != t.periyot or alanlar["baslangic"] != t.baslangic or alanlar["bitis"] != t.bitis or (
            alanlar["aktif"] and not t.aktif)
        for alan, deger in alanlar.items():
            setattr(t, alan, deger)
        if takvim_degisti:
            t.sonraki = _ilk_donem(t.baslangic, t.periyot, False, t.son_uretilen)
            if t.bitis and t.sonraki and t.sonraki > t.bitis:
                t.sonraki = None
        t.updated_at = s.simdi()
        await db.flush()
        _, aylar = await k.tekrarlari_uret(db, kapsam.anahtar, kapsam.hesap)
        await db.commit()
        if aylar:
            await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, aylar)
            await db.commit()
        await db.refresh(t)
        return _tekrar_sozlugu(t)

    @router.delete("/tekrarlar/{tid}")
    async def tekrar_sil(tid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Çöp kutusuna. Üretilmiş hareketler kalır."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        t = await _bul(db, MuhasebeTekrarlar, kapsam, tid)
        await db.delete(t)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- cariler
    @router.get("/cariler")
    async def cari_listesi(request: Request, ara: Optional[str] = Query(None), tur: Optional[str] = Query(None),
                           arsiv: bool = Query(False), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam.anahtar)
        if not arsiv:
            sorgu = sorgu.where(MuhasebeCariler.arsiv.is_(False))
        if tur in s.CARI_TURLERI:
            sorgu = sorgu.where(MuhasebeCariler.tur.in_((tur, "her_ikisi")))
        if ara:
            a = f"%{ara.strip()[:80]}%"
            sorgu = sorgu.where(or_(MuhasebeCariler.ad.ilike(a), MuhasebeCariler.eposta.ilike(a), MuhasebeCariler.vergi_no.ilike(a)))
        cariler = (await db.execute(sorgu.order_by(MuhasebeCariler.ad).limit(1000))).scalars().all()
        etki = await k.cari_bakiyeleri(db, kapsam.anahtar, [c.id for c in cariler])
        items = [_cari_sozlugu(c, etki.get(c.id, 0), tam=False) for c in cariler]
        toplamlar: Dict[str, Dict[str, int]] = {}
        for x in items:
            d = toplamlar.setdefault(x["para_birimi"], {"alacak": 0, "borc": 0})
            if x["bakiye"] > 0:
                d["alacak"] += x["bakiye"]
            elif x["bakiye"] < 0:
                d["borc"] += -x["bakiye"]
        return {"items": items, "toplamlar": [{"para_birimi": pb, **v} for pb, v in sorted(toplamlar.items())]}

    async def _bagli_dogrula(db: AsyncSession, kapsam: Kapsam, tur: Optional[str], bid: Optional[str], haric: Optional[int] = None) -> None:
        if not tur and not bid:
            return
        if tur not in s.BAGLI_TURLER or not bid:
            raise _hata(400, "baglanti_gecersiz", alan="bagli_tur")
        adaylar = await _baglanti_adaylari(db, kapsam, None, tur, bid)
        if not adaylar:
            raise _hata(400, "baglanti_gecersiz", alan="bagli_id")
        var = (await db.execute(select(MuhasebeCariler.id).where(MuhasebeCariler.kapsam == kapsam.anahtar, MuhasebeCariler.bagli_tur == tur,
                                                                MuhasebeCariler.bagli_id == bid))).scalars().all()
        if any(x != haric for x in var):
            raise _hata(409, "baglanti_kullaniliyor", alan="bagli_id")

    async def _cari_uygula(c: MuhasebeCariler, g: Dict[str, Any], yeni: bool) -> None:
        try:
            if yeni or "tur" in g:
                c.tur = s.secim(g.get("tur"), "tur", s.CARI_TURLERI, "musteri")
            if yeni or "ad" in g:
                c.ad = s.metin(g.get("ad"), "ad", 160, zorunlu=True)
            if yeni or "para_birimi" in g:
                pb = s.para_birimi_duzelt(g.get("para_birimi"))
                if not yeni and pb != c.para_birimi and await k.kullanimda_mi(db, c.kapsam, cari_id=c.id):
                    raise s.MuhasebeHatasi("para_birimi_kilitli", "para_birimi")
                c.para_birimi = pb
            for alan, sinir in (("vergi_dairesi", 80), ("adres", 500), ("notlar", 1000)):
                if yeni or alan in g:
                    setattr(c, alan, s.bos_ya_da(g.get(alan), alan, sinir, cok_satir=alan in ("adres", "notlar")))
            if yeni or "vergi_no" in g:
                c.vergi_no = s.vergi_no_duzelt(g.get("vergi_no"))
            if yeni or "eposta" in g:
                c.eposta = s.eposta_duzelt(g.get("eposta"))
            if yeni or "telefon" in g:
                c.telefon = s.telefon_duzelt(g.get("telefon"))
            if yeni or "acilis_bakiyesi" in g:
                c.acilis_bakiyesi = s.kurus_coz(g.get("acilis_bakiyesi"), "acilis_bakiyesi", eksi_olabilir=True, sifir_olabilir=True,
                                                bos_olabilir=True) or 0
            if yeni or "acilis_tarihi" in g:
                c.acilis_tarihi = s.bos_tarih(g.get("acilis_tarihi"), "acilis_tarihi") or (c.acilis_tarihi if not yeni else s.bugun())
            if "arsiv" in g:
                c.arsiv = s.bool_duzelt(g.get("arsiv"), "arsiv")
        except s.TemelHata as h:
            raise _e(h)

    @router.post("/cariler")
    async def cari_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        c = MuhasebeCariler(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, created_at=s.simdi())
        await _cari_uygula(c, g, True)
        bagli_tur, bagli_id = g.get("bagli_tur") or None, (str(g.get("bagli_id")).strip()[:254] if g.get("bagli_id") not in (None, "") else None)
        await _bagli_dogrula(db, kapsam, bagli_tur, bagli_id)
        c.bagli_tur, c.bagli_id = bagli_tur, bagli_id
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return _cari_sozlugu(c)

    @router.get("/cariler/baglanti-adaylari")
    async def baglanti_adaylari(request: Request, ara: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        """Cari kartın bağlanabileceği mevcut kayıtlar (ajans: CRM adayı / müşteri hesabı; müşteri: saha müşterisi /
        POS alıcısı — o modülün izni de gerekir)."""
        kapsam = kapsam_al(request)
        return {"items": await _baglanti_adaylari(db, kapsam, ara)}

    @router.get("/cariler/{cid}")
    async def cari_ayrinti(cid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        c = await _bul(db, MuhasebeCariler, kapsam, cid)
        etki = await k.cari_bakiyeleri(db, kapsam.anahtar, [c.id])
        d = _cari_sozlugu(c, etki.get(c.id, 0))
        bugun = s.bugun()
        for yon in ("alacak", "borc"):
            y = (await k.cari_yaslandirma(db, kapsam.anahtar, [c], bugun, yon))[c.id]
            d[f"yaslandirma_{yon}"] = {"kovalar": y.kovalar, "acik": y.acik, "fazla": y.fazla, "en_eski_gun": y.en_eski_gun}
        son = (await db.execute(select(H).where(H.kapsam == kapsam.anahtar, H.cari_id == c.id).order_by(H.tarih.desc(), H.id.desc()).limit(20))).scalars().all()
        adlar = await _adlar(db, kapsam)
        d["son_hareketler"] = [_hareket_sozlugu(x, adlar, {c.id: c.ad}) for x in son]
        if c.bagli_tur and c.bagli_id:
            aday = await _baglanti_adaylari(db, kapsam, None, c.bagli_tur, c.bagli_id)
            d["bagli"] = aday[0] if aday else {"tur": c.bagli_tur, "id": c.bagli_id, "ad": None, "ayrinti": None}
        return d

    @router.put("/cariler/{cid}")
    async def cari_guncelle(cid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        c = await _bul(db, MuhasebeCariler, kapsam, cid)
        await _cari_uygula(c, g, False)
        if "bagli_tur" in g or "bagli_id" in g:
            bagli_tur = g.get("bagli_tur") or None
            bagli_id = str(g.get("bagli_id")).strip()[:254] if g.get("bagli_id") not in (None, "") else None
            if (bagli_tur, bagli_id) != (c.bagli_tur, c.bagli_id):
                await _bagli_dogrula(db, kapsam, bagli_tur, bagli_id, haric=c.id)
                c.bagli_tur, c.bagli_id = bagli_tur, bagli_id
        c.updated_at = s.simdi()
        await db.commit()
        await db.refresh(c)
        etki = await k.cari_bakiyeleri(db, kapsam.anahtar, [c.id])
        return _cari_sozlugu(c, etki.get(c.id, 0))

    @router.delete("/cariler/{cid}")
    async def cari_sil(cid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        c = await _bul(db, MuhasebeCariler, kapsam, cid)
        if await k.kullanimda_mi(db, kapsam.anahtar, cari_id=c.id):
            raise _hata(409, "cari_kullaniliyor")
        await db.delete(c)
        await db.commit()
        return {"ok": True}

    async def _ekstre(db: AsyncSession, kapsam: Kapsam, cid: int, bas: Optional[str], bit: Optional[str]) -> Tuple[MuhasebeCariler, Dict[str, Any], date, date]:
        c = await _bul(db, MuhasebeCariler, kapsam, cid)
        bugun = s.bugun()
        b = _tarih_q(bas, "bas", date(bugun.year, 1, 1))
        e = _tarih_q(bit, "bit", bugun)
        if e < b or (e - b).days > 3700:
            raise _hata(400, "aralik_gecersiz", alan="bit")
        return c, await k.cari_ekstre(db, kapsam.anahtar, c, b, e), b, e

    @router.get("/cariler/{cid}/ekstre")
    async def cari_ekstre(cid: int, request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                          db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        c, v, b, e = await _ekstre(db, kapsam, cid, bas, bit)
        return {"cari": _cari_sozlugu(c, tam=False), "bas": b.isoformat(), "bit": e.isoformat(), "devreden": v["devreden"],
                "satirlar": [{**x, "tarih": s.gun_iso(x["tarih"]), "vade": s.gun_iso(x.get("vade"))} for x in v["satirlar"]],
                "toplam_borc": v["toplam_borc"], "toplam_alacak": v["toplam_alacak"], "kapanis": v["kapanis"]}

    @router.get("/cariler/{cid}/ekstre.pdf")
    async def cari_ekstre_pdf(cid: int, request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                              dil: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _dosya(kapsam)
        c, v, b, e = await _ekstre(db, kapsam, cid, bas, bit)
        pdf = s.ekstre_pdf({"firma": await _firma(db, kapsam), "cari": _cari_sozlugu(c), "bas": b, "bit": e, "olusturma": s.bugun(),
                            "para_birimi": c.para_birimi, **v}, dil or "tr")
        return _dosya_yaniti(pdf, "application/pdf", f"cari-ekstre-{c.id}-{b.isoformat()}-{e.isoformat()}.pdf")

    @router.get("/cariler/{cid}/ekstre.csv")
    async def cari_ekstre_csv(cid: int, request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                              db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _dosya(kapsam)
        c, v, b, e = await _ekstre(db, kapsam, cid, bas, bit)
        veri = [[b.isoformat(), "devreden", "", "", "", "", s.kurus_metni(v["devreden"])]]
        for x in v["satirlar"]:
            veri.append([s.gun_iso(x["tarih"]), x["tur"] + (" (ters)" if x.get("ters") else ""), x.get("aciklama") or "",
                         x.get("belge_no") or "", s.kurus_metni(x["borc"]) if x["borc"] else "",
                         s.kurus_metni(x["alacak"]) if x["alacak"] else "", s.kurus_metni(x["bakiye"])])
        veri.append([e.isoformat(), "kapanis", "", "", s.kurus_metni(v["toplam_borc"]), s.kurus_metni(v["toplam_alacak"]),
                     s.kurus_metni(v["kapanis"])])
        metin = s.csv_metni(["tarih", "tur", "aciklama", "belge_no", f"borc_{c.para_birimi}", f"alacak_{c.para_birimi}",
                             f"bakiye_{c.para_birimi}"], veri)
        return _csv_yaniti(metin, f"cari-ekstre-{c.id}-{b.isoformat()}-{e.isoformat()}.csv")

    @router.get("/yaslandirma")
    async def yaslandirma(request: Request, yon: str = Query("alacak"), tarih: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        if yon not in ("alacak", "borc"):
            raise _hata(400, "secim_gecersiz", alan="yon")
        t = _tarih_q(tarih, "tarih", s.bugun())
        cariler = (await db.execute(select(MuhasebeCariler).where(MuhasebeCariler.kapsam == kapsam.anahtar).order_by(MuhasebeCariler.ad)
                                    .limit(2000))).scalars().all()
        sonuc = await k.cari_yaslandirma(db, kapsam.anahtar, cariler, t, yon)
        satirlar = []
        toplamlar: Dict[str, Dict[str, Any]] = {}
        for c in cariler:
            y = sonuc[c.id]
            if y.acik <= 0:
                continue
            satirlar.append({"cari_id": c.id, "ad": c.ad, "para_birimi": c.para_birimi, "kovalar": y.kovalar, "acik": y.acik,
                             "en_eski_gun": y.en_eski_gun})
            tp = toplamlar.setdefault(c.para_birimi, {"kovalar": {kv: 0 for kv in s.KOVALAR}, "acik": 0})
            tp["acik"] += y.acik
            for kv, v in y.kovalar.items():
                tp["kovalar"][kv] += v
        satirlar.sort(key=lambda x: (-(x["en_eski_gun"] or -1), -x["acik"]))
        return {"tarih": t.isoformat(), "yon": yon, "satirlar": satirlar,
                "toplamlar": [{"para_birimi": pb, **v} for pb, v in sorted(toplamlar.items())]}

    # ------------------------------------------------------------- bütçe
    @router.get("/butceler")
    async def butceler(request: Request, ay: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        try:
            a_ = s.ay_duzelt(ay) if ay else s.ay_anahtari(s.bugun())
        except s.TemelHata as h:
            raise _e(h)
        a = await _ayar(db, kapsam)
        durum = await k.butce_durumu(db, kapsam.anahtar, a_, a.uyari_yuzde if a else 80)
        tanimlar = (await db.execute(select(MuhasebeButceler).where(MuhasebeButceler.kapsam == kapsam.anahtar,
                                                                    MuhasebeButceler.ay.in_((a_, "*"))))).scalars().all()
        durum["tanimlar"] = [{"id": b.id, "kategori_id": b.kategori_id, "ay": b.ay, "tutar": int(b.tutar), "para_birimi": b.para_birimi}
                             for b in tanimlar]
        return durum

    @router.put("/butceler")
    async def butce_yaz(request: Request, db: AsyncSession = Depends(get_db)):
        """{kategori_id, ay: "YYYY-AA" | "*", tutar (boş/0 → bütçe kaldırılır), para_birimi?}."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        try:
            kid = s.kimlik(g.get("kategori_id"), "kategori_id", bos_olabilir=False)
            ay = s.ay_duzelt(g.get("ay") or "*", yildiz=True)
            pb = s.para_birimi_duzelt(g.get("para_birimi"))
            tutar = s.kurus_coz(g.get("tutar"), "tutar", bos_olabilir=True, sifir_olabilir=True)
        except s.TemelHata as h:
            raise _e(h)
        kat = await _bul(db, MuhasebeKategorileri, kapsam, kid, "kategori_bulunamadi", "kategori_id")
        if kat.tur != "gider":
            raise _hata(400, "kategori_turu_uyusmuyor", alan="kategori_id")
        b = (await db.execute(select(MuhasebeButceler).where(MuhasebeButceler.kapsam == kapsam.anahtar, MuhasebeButceler.kategori_id == kid,
                                                             MuhasebeButceler.ay == ay, MuhasebeButceler.para_birimi == pb))).scalars().first()
        if not tutar:
            if b is not None:
                await db.delete(b)
            await db.commit()
            return {"ok": True, "silindi": True}
        if b is None:
            b = MuhasebeButceler(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, kategori_id=kid, ay=ay, para_birimi=pb, tutar=tutar,
                                 created_at=s.simdi())
            db.add(b)
        else:
            b.tutar, b.updated_at = tutar, s.simdi()
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "eszamanli")
        asim = await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, [s.ay_anahtari(s.bugun()) if ay == "*" else ay])
        await db.commit()
        return {"ok": True, "id": b.id, "kategori_id": kid, "ay": ay, "para_birimi": pb, "tutar": tutar, "butce_asimi": asim}

    # ------------------------------------------------------------- raporlar
    @router.get("/raporlar/aylik")
    async def rapor_aylik(request: Request, yil: Optional[int] = Query(None, ge=2000, le=2100), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        return await k.aylik_rapor(db, kapsam.anahtar, yil or s.bugun().year)

    @router.get("/raporlar/kategori")
    async def rapor_kategori(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                             tur: str = Query("gider"), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        if tur not in s.KATEGORI_TURLERI:
            raise _hata(400, "secim_gecersiz", alan="tur")
        bugun = s.bugun()
        b = _tarih_q(bas, "bas", date(bugun.year, bugun.month, 1))
        e = _tarih_q(bit, "bit", bugun)
        if e < b:
            raise _hata(400, "aralik_gecersiz", alan="bit")
        return await k.kategori_raporu(db, kapsam.anahtar, b, e, tur)

    @router.get("/raporlar/kar-zarar")
    async def rapor_kar_zarar(request: Request, bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                              db: AsyncSession = Depends(get_db)):
        """Kâr-zarar özeti (KDV hariç; varsayılan: bu yılın başından bugüne)."""
        kapsam = kapsam_al(request, rapor=True)
        bugun = s.bugun()
        b = _tarih_q(bas, "bas", date(bugun.year, 1, 1))
        e = _tarih_q(bit, "bit", bugun)
        if e < b:
            raise _hata(400, "aralik_gecersiz", alan="bit")
        return await k.kar_zarar(db, kapsam.anahtar, b, e)

    @router.get("/raporlar/nakit-akisi")
    async def rapor_nakit(request: Request, ay: int = Query(6, ge=1, le=24), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        return await k.nakit_akisi(db, kapsam.anahtar, ay)

    @router.get("/raporlar/kdv")
    async def rapor_kdv(request: Request, yil: Optional[int] = Query(None, ge=2000, le=2100), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        return await k.kdv_raporu(db, kapsam.anahtar, yil or s.bugun().year)

    @router.get("/raporlar.csv")
    async def rapor_csv(request: Request, tur: str = Query(...), yil: Optional[int] = Query(None, ge=2000, le=2100),
                        bas: Optional[str] = Query(None), bit: Optional[str] = Query(None), kategori_turu: str = Query("gider"),
                        db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request, rapor=True)
        _dosya(kapsam)
        bugun = s.bugun()
        if tur == "aylik":
            r = await k.aylik_rapor(db, kapsam.anahtar, yil or bugun.year)
            veri = [[a["ay"], p["para_birimi"], s.kurus_metni(a["gelir"]), s.kurus_metni(a["gider"]), s.kurus_metni(a["net"])]
                    for p in r["para_birimleri"] for a in p["aylar"]]
            return _csv_yaniti(s.csv_metni(["ay", "para_birimi", "gelir", "gider", "net"], veri), f"aylik-{r['yil']}.csv")
        if tur == "kdv":
            r = await k.kdv_raporu(db, kapsam.anahtar, yil or bugun.year)
            veri = [[a["ay"], p["para_birimi"], s.kurus_metni(a["matrah_satis"]), s.kurus_metni(a["hesaplanan"]),
                     s.kurus_metni(a["matrah_alis"]), s.kurus_metni(a["indirilecek"]), s.kurus_metni(a["fark"])]
                    for p in r["para_birimleri"] for a in p["aylar"]]
            return _csv_yaniti(s.csv_metni(["ay", "para_birimi", "satis_matrahi", "hesaplanan_kdv", "alis_matrahi", "indirilecek_kdv",
                                            "fark"], veri), f"kdv-{r['yil']}.csv")
        if tur == "kategori":
            if kategori_turu not in s.KATEGORI_TURLERI:
                raise _hata(400, "secim_gecersiz", alan="kategori_turu")
            b = _tarih_q(bas, "bas", date(bugun.year, bugun.month, 1))
            e = _tarih_q(bit, "bit", bugun)
            r = await k.kategori_raporu(db, kapsam.anahtar, b, e, kategori_turu)
            veri = [[p["para_birimi"], x["ad"] or "-", s.kurus_metni(x["tutar"]), str(x["oran"]).replace(".", ",")]
                    for p in r["para_birimleri"] for x in p["kalemler"]]
            return _csv_yaniti(s.csv_metni(["para_birimi", "kategori", "tutar", "oran_yuzde"], veri), f"kategori-{b}-{e}.csv")
        if tur == "kar_zarar":
            b = _tarih_q(bas, "bas", date(bugun.year, 1, 1))
            e = _tarih_q(bit, "bit", bugun)
            r = await k.kar_zarar(db, kapsam.anahtar, b, e)
            veri = [[p["para_birimi"], t, x["ad"] or "-", s.kurus_metni(x["tutar"]), s.kurus_metni(x["kdv"])]
                    for p in r["para_birimleri"] for t, liste in (("gelir", p["gelirler"]), ("gider", p["giderler"])) for x in liste]
            veri += [[p["para_birimi"], "sonuc", "", s.kurus_metni(p["sonuc"]), ""] for p in r["para_birimleri"]]
            return _csv_yaniti(s.csv_metni(["para_birimi", "tur", "kategori", "kdv_haric_tutar", "kdv"], veri), f"kar-zarar-{b}-{e}.csv")
        if tur == "nakit":
            r = await k.nakit_akisi(db, kapsam.anahtar)
            veri = [[a["ay"], p["para_birimi"], s.kurus_metni(a["giris"]), s.kurus_metni(a["cikis"]), s.kurus_metni(a["net"]),
                     s.kurus_metni(a["bakiye"]), "evet" if a.get("tahmin") else ""]
                    for p in r["para_birimleri"] for a in p["gecmis"] + p["tahmin"]]
            return _csv_yaniti(s.csv_metni(["ay", "para_birimi", "giris", "cikis", "net", "ay_sonu_bakiye", "tahmin"], veri), "nakit-akisi.csv")
        raise _hata(400, "secim_gecersiz", alan="tur")

    # ------------------------------------------------------------- öneriler (onay bekleyen yansımalar)
    @router.get("/oneriler")
    async def oneri_listesi(request: Request, durum: str = Query("bekliyor"), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        if durum not in s.ONERI_DURUMLARI:
            raise _hata(400, "secim_gecersiz", alan="durum")
        satirlar = (await db.execute(select(MuhasebeOneriler).where(MuhasebeOneriler.kapsam == kapsam.anahtar, MuhasebeOneriler.durum == durum)
                                     .order_by(MuhasebeOneriler.tarih.desc(), MuhasebeOneriler.id.desc()).limit(500))).scalars().all()
        sayilar = dict((await db.execute(select(MuhasebeOneriler.durum, func.count(MuhasebeOneriler.id)).where(
            MuhasebeOneriler.kapsam == kapsam.anahtar).group_by(MuhasebeOneriler.durum))).all())
        adlar = await _adlar(db, kapsam)
        veriler = [(o, s.json_yukle(o.veri, {}) or {}) for o in satirlar]
        cari_ad = await _cari_adlari(db, [v.get("cari_id") or 0 for _, v in veriler])
        return {"items": [_oneri_sozlugu(o, v, adlar, cari_ad) for o, v in veriler],
                "sayilar": {d: int(sayilar.get(d, 0)) for d in s.ONERI_DURUMLARI}}

    async def _onayla(db: AsyncSession, kapsam: Kapsam, o: MuhasebeOneriler, g: Dict[str, Any]) -> H:
        try:
            hesap_id = s.kimlik(g.get("hesap_id"), "hesap_id") if "hesap_id" in g else None
            kategori_id = s.kimlik(g.get("kategori_id"), "kategori_id") if "kategori_id" in g else None
            aciklama = s.bos_ya_da(g.get("aciklama"), "aciklama", 300) if "aciklama" in g else None
            return await k.oneri_onayla(db, kapsam.anahtar, kapsam.hesap, o, hesap_id=hesap_id, kategori_id=kategori_id,
                                        aciklama=aciklama, kisi=kapsam.kisi)
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)

    @router.post("/oneriler/toplu")
    async def oneri_toplu(request: Request, db: AsyncSession = Depends(get_db)):
        """{idler: [...], islem: "onayla" | "yoksay"} — en çok 200. Hatalı olan atlanır ve bildirilir."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        islem = g.get("islem")
        idler = g.get("idler")
        if islem not in ("onayla", "yoksay"):
            raise _hata(400, "secim_gecersiz", alan="islem")
        if not isinstance(idler, list) or not idler or len(idler) > 200 or not all(isinstance(x, int) and not isinstance(x, bool) for x in idler):
            raise _hata(400, "kimlik_gecersiz", alan="idler")
        satirlar = (await db.execute(select(MuhasebeOneriler).where(MuhasebeOneriler.kapsam == kapsam.anahtar,
                                                                    MuhasebeOneriler.id.in_(idler)))).scalars().all()
        bulunan = {o.id: o for o in satirlar}
        tamam = 0
        hatalar: List[Dict[str, Any]] = []
        aylar = set()
        for oid in idler:
            o = bulunan.get(oid)
            if o is None:
                hatalar.append({"id": oid, "kod": "bulunamadi"})
                continue
            if islem == "yoksay":
                o.durum, o.karar_veren, o.updated_at = "yoksayildi", kapsam.kisi, s.simdi()
                tamam += 1
                continue
            try:
                async with db.begin_nested():
                    h = await k.oneri_onayla(db, kapsam.anahtar, kapsam.hesap, o, kisi=kapsam.kisi)
                tamam += 1
                if h.tur == "gider":
                    aylar.add(s.ay_anahtari(h.tarih))
            except s.TemelHata as hata:
                hatalar.append({"id": oid, "kod": hata.kod})
        await db.commit()
        if aylar:
            await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, aylar)
            await db.commit()
        return {"islem": islem, "tamam": tamam, "hatalar": hatalar, "bekleyen": await k.oneri_sayisi(db, kapsam.anahtar)}

    @router.post("/oneriler/{oid}/onayla")
    async def oneri_onayla(oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Deftere yazar: {hesap_id?, kategori_id?, aciklama?} önerilenin yerine. Aynı kaynak kimliği → iki kez sayılmaz."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        o = await _bul(db, MuhasebeOneriler, kapsam, oid)
        h = await _onayla(db, kapsam, o, g)
        await db.commit()
        await db.refresh(h)
        uyari = 0
        if h.tur == "gider":
            uyari = await k.butce_denetle(db, kapsam.anahtar, kapsam.hesap, [s.ay_anahtari(h.tarih)])
            await db.commit()
        d = _hareket_sozlugu(h, await _adlar(db, kapsam), await _cari_adlari(db, [h.cari_id or 0]))
        d["butce_asimi"] = uyari
        return d

    @router.post("/oneriler/{oid}/yoksay")
    async def oneri_yoksay(oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Deftere yazılmaz; kaynağı değişmedikçe yeniden önerilmez (örn. ekstreden zaten içe aktarıldıysa)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        o = await _bul(db, MuhasebeOneriler, kapsam, oid)
        o.durum, o.karar_veren, o.updated_at = "yoksayildi", kapsam.kisi, s.simdi()
        await db.commit()
        return {"ok": True, "bekleyen": await k.oneri_sayisi(db, kapsam.anahtar)}

    @router.post("/oneriler/{oid}/geri-al")
    async def oneri_geri_al(oid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Yok sayılan öneri yeniden onay bekler."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        o = await _bul(db, MuhasebeOneriler, kapsam, oid)
        o.durum, o.karar_veren, o.updated_at = "bekliyor", None, s.simdi()
        await db.commit()
        return {"ok": True, "bekleyen": await k.oneri_sayisi(db, kapsam.anahtar)}


def _oneri_sozlugu(o: MuhasebeOneriler, v: Dict[str, Any], adlar: Dict[str, Dict[int, Any]], cariler: Dict[int, str]) -> Dict[str, Any]:
    hes = adlar["hesap"].get(v.get("hesap_id")) if v.get("hesap_id") else None
    bagli = v.get("bagli") if isinstance(v.get("bagli"), list) and len(v.get("bagli")) == 3 else None
    anahtar = v.get("kategori")
    return {
        "id": o.id, "kaynak": o.kaynak, "kaynak_ref": o.kaynak_ref, "durum": o.durum, "tur": v.get("tur"), "tarih": o.tarih.isoformat(),
        "tutar": int(o.tutar), "para_birimi": o.para_birimi, "kdv_orani": v.get("kdv_orani"), "kdv_tutari": int(v.get("kdv_tutari") or 0),
        "hesap_id": v.get("hesap_id"), "hesap": hes.ad if hes else None,
        "cari_id": v.get("cari_id"), "cari": cariler.get(v.get("cari_id")) if v.get("cari_id") else (bagli[2] if bagli else None),
        "kategori": ({"ad": s.KATEGORI_ADLARI.get(anahtar), "anahtar": anahtar, "ad_degisti": False, "renk": s.KATEGORI_RENGI.get(anahtar)}
                     if anahtar else None),
        "aciklama": v.get("aciklama") or "", "belge_no": v.get("belge_no") or "", "vade_tarihi": v.get("vade"),
        "created_at": s.iso(o.created_at), "updated_at": s.iso(o.updated_at),
    }


async def _aktarim_duzelt(db: AsyncSession, kapsam: Kapsam, a: MuhasebeAyarlari, ham: Any) -> Dict[str, Any]:
    """Aktarım ayarı: kapsamın kaynakları; hedef hesaplar kapsamda ve arşivde değil; açılırken zorunlu hesaplar."""
    if not isinstance(ham, dict):
        raise s.MuhasebeHatasi("aktarim_gecersiz", "aktarim")
    mevcut = k.aktarim_ayarlari(a, kapsam.anahtar)
    hesaplar = {h.id: h for h in (await db.execute(select(MuhasebeHesaplari).where(MuhasebeHesaplari.kapsam == kapsam.anahtar))).scalars().all()}
    for kaynak, d in ham.items():
        if kaynak not in mevcut:
            raise s.MuhasebeHatasi("aktarim_kaynagi_gecersiz", f"aktarim.{kaynak}")
        if not isinstance(d, dict):
            raise s.MuhasebeHatasi("aktarim_gecersiz", f"aktarim.{kaynak}")
        satir = dict(mevcut[kaynak])
        if "acik" in d:
            satir["acik"] = s.bool_duzelt(d.get("acik"), f"aktarim.{kaynak}.acik")
        if "onay" in d:
            satir["onay"] = s.bool_duzelt(d.get("onay"), f"aktarim.{kaynak}.onay")
        for alan in s.AKTARIM_HESAPLARI[kaynak]:
            if alan in d:
                hid = s.kimlik(d.get(alan), f"aktarim.{kaynak}.{alan}")
                if hid is not None and (hid not in hesaplar or hesaplar[hid].arsiv):
                    raise s.MuhasebeHatasi("hesap_bulunamadi", f"aktarim.{kaynak}.{alan}")
                satir[alan] = hid
        if "baslangic" in d and d.get("baslangic"):
            g = s.tarih_duzelt(d.get("baslangic"), f"aktarim.{kaynak}.baslangic")
            if g < s.bugun() - timedelta(days=s.EN_COK_GERIYE_GUN):
                raise s.MuhasebeHatasi("baslangic_cok_eski", f"aktarim.{kaynak}.baslangic", en_cok=s.EN_COK_GERIYE_GUN)
            satir["baslangic"] = g.isoformat()
        if satir["acik"]:
            for alan in s.AKTARIM_ZORUNLU[kaynak]:
                if not satir.get(alan):
                    raise s.MuhasebeHatasi("hedef_hesap_gerekli", f"aktarim.{kaynak}.{alan}")
            if not satir.get("baslangic"):
                satir["baslangic"] = s.bugun().isoformat()
        mevcut[kaynak] = satir
    return mevcut


async def _baglanti_adaylari(db: AsyncSession, kapsam: Kapsam, ara: Optional[str], tur: Optional[str] = None,
                             bid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ajans: CRM adayı + müşteri hesabı (fatura e-postaları). Müşteri: saha müşterisi (`saha_yonetim` izni) + POS alıcısı
    ve stok tedarikçisi (`stok` izni). `tur` + `bid` verilirse yalnız o kayıt (doğrulama)."""
    a = f"%{(ara or '').strip()[:80]}%"
    sonuc: List[Dict[str, Any]] = []
    if kapsam.hesap is None:
        if tur in (None, "crm_aday"):
            from models.crm import CrmAdaylari

            sorgu = select(CrmAdaylari)
            if bid is not None:
                sorgu = sorgu.where(CrmAdaylari.id == (int(bid) if str(bid).isdigit() else -1))
            elif ara:
                sorgu = sorgu.where(or_(CrmAdaylari.ad.ilike(a), CrmAdaylari.firma.ilike(a), CrmAdaylari.email.ilike(a)))
            for x in (await db.execute(sorgu.order_by(CrmAdaylari.id.desc()).limit(15))).scalars().all():
                sonuc.append({"tur": "crm_aday", "id": str(x.id), "ad": x.firma or x.ad, "ayrinti": x.email or x.ad})
        if tur in (None, "musteri_hesabi"):
            from models.invoices import Invoices

            sorgu = select(Invoices.client_email, func.max(Invoices.client_name)).where(Invoices.client_email.isnot(None), Invoices.client_email != "")
            if bid is not None:
                sorgu = sorgu.where(func.lower(Invoices.client_email) == bid.lower())
            elif ara:
                sorgu = sorgu.where(or_(Invoices.client_email.ilike(a), Invoices.client_name.ilike(a)))
            for e, ad in (await db.execute(sorgu.group_by(Invoices.client_email).limit(15))).all():
                sonuc.append({"tur": "musteri_hesabi", "id": (e or "").strip().lower(), "ad": ad or e, "ayrinti": e})
        return sonuc
    if tur in (None, "saha_musteri") and kapsam.izinli("saha_yonetim"):
        from models.saha_servisi import SahaMusterileri

        sorgu = select(SahaMusterileri).where(SahaMusterileri.hesap_email == kapsam.hesap, SahaMusterileri.anonim.is_(False))
        if bid is not None:
            sorgu = sorgu.where(SahaMusterileri.id == (int(bid) if str(bid).isdigit() else -1))
        elif ara:
            sorgu = sorgu.where(or_(SahaMusterileri.ad.ilike(a), SahaMusterileri.firma.ilike(a)))
        for x in (await db.execute(sorgu.order_by(SahaMusterileri.id.desc()).limit(15))).scalars().all():
            sonuc.append({"tur": "saha_musteri", "id": str(x.id), "ad": x.firma or x.ad, "ayrinti": x.ad if x.firma else None})
    if tur in (None, "pos_alici") and kapsam.izinli("stok"):
        from models.stok_pos import PosAlicilari

        sorgu = select(PosAlicilari).where(PosAlicilari.hesap_email == kapsam.hesap)
        if bid is not None:
            sorgu = sorgu.where(PosAlicilari.id == (int(bid) if str(bid).isdigit() else -1))
        elif ara:
            sorgu = sorgu.where(PosAlicilari.ad.ilike(a))
        for x in (await db.execute(sorgu.order_by(PosAlicilari.id.desc()).limit(15))).scalars().all():
            sonuc.append({"tur": "pos_alici", "id": str(x.id), "ad": x.ad, "ayrinti": x.vergi_dairesi})
    if tur in (None, "stok_tedarikci") and kapsam.izinli("stok"):
        from models.stok_pos import StokTedarikcileri

        sorgu = select(StokTedarikcileri).where(StokTedarikcileri.hesap_email == kapsam.hesap)
        if bid is not None:
            sorgu = sorgu.where(StokTedarikcileri.id == (int(bid) if str(bid).isdigit() else -1))
        elif ara:
            sorgu = sorgu.where(or_(StokTedarikcileri.ad.ilike(a), StokTedarikcileri.yetkili.ilike(a), StokTedarikcileri.eposta.ilike(a)))
        for x in (await db.execute(sorgu.order_by(StokTedarikcileri.id.desc()).limit(15))).scalars().all():
            sonuc.append({"tur": "stok_tedarikci", "id": str(x.id), "ad": x.ad, "ayrinti": x.yetkili or x.eposta})
    return sonuc


_uclari_kur(musteri_router, _musteri_kapsami)
_uclari_kur(yonetici_router, _yonetici_kapsami)


@yonetici_router.get("/musteri-hesaplari")
async def yonetici_musteri_hesaplari(db: AsyncSession = Depends(get_db)):
    """Ön muhasebe kaydı olan ya da modülü açık müşteri hesapları (salt okunur destek görünümü için)."""
    from models.workspace_modules import WorkspaceModules

    hesaplar = {h for (h,) in (await db.execute(select(MuhasebeAyarlari.hesap_email).where(MuhasebeAyarlari.hesap_email.isnot(None)))).all()}
    hesaplar |= set((await db.execute(select(WorkspaceModules.musteri_eposta).where(
        WorkspaceModules.modul_anahtari == MODUL, WorkspaceModules.acik.is_(True)))).scalars().all())
    hareket = dict((await db.execute(select(H.hesap_email, func.count(H.id)).where(H.hesap_email.isnot(None)).group_by(H.hesap_email))).all())
    hesap_sayisi = dict((await db.execute(select(MuhasebeHesaplari.hesap_email, func.count(MuhasebeHesaplari.id)).where(
        MuhasebeHesaplari.hesap_email.isnot(None)).group_by(MuhasebeHesaplari.hesap_email))).all())
    adlar = dict((await db.execute(select(MuhasebeAyarlari.hesap_email, MuhasebeAyarlari.firma_adi).where(MuhasebeAyarlari.hesap_email.isnot(None)))).all())
    return {"items": [{"hesap_email": h, "firma_adi": adlar.get(h), "hesap_sayisi": int(hesap_sayisi.get(h, 0)),
                       "hareket_sayisi": int(hareket.get(h, 0))} for h in sorted(x for x in hesaplar if x)]}


router = (yonetici_router, musteri_router)
