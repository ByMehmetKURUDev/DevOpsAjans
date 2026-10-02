"""Faz 5M — E-posta pazarlama: bülten, kampanya ve damla dizileri.

Panel (aynı uçlar iki önekte):
  Yönetici  /api/v1/eposta-pazarlama/yonetim   — ajansın kendi hesabı (+ yalnız yönetici: hesaplar, CRM aktarımı, sahte kutu)
  Müşteri   /api/v1/eposta-pazarlamam           — etkin hesap; modül `eposta_pazarlama` açık + hesap ekibi izni `pazarlama`

  GET  /meta · GET /ozet · GET|PUT /ayarlar
  GET|POST /kisiler · GET|PUT|DELETE /kisiler/{id} · POST /kisiler/{id}/ret
  POST /kisiler/ice-aktar/onizleme · POST /kisiler/ice-aktar          (CSV: izin kaynağı + tarihi zorunlu sütun)
  GET|POST /bastirma · DELETE /bastirma/{id}                          (yalnız elle eklenen kaldırılabilir)
  GET|POST /listeler · PUT|DELETE /listeler/{id} · POST /listeler/{id}/uyeler · DELETE /listeler/{id}/uyeler/{kisi_id}
  GET|POST /formlar · PUT|DELETE /formlar/{id}
  GET|POST /segmentler · PUT|DELETE /segmentler/{id} · POST /segmentler/onizleme
  POST /gorseller · POST /onizleme
  GET|POST /kampanyalar · GET|PUT|DELETE /kampanyalar/{id}
  POST /kampanyalar/{id}/onizleme|kitle|test|gonder|durdur|devam|kopyala · GET /kampanyalar/{id}/rapor
  GET|POST /diziler · GET|PUT|DELETE /diziler/{id} · GET /diziler/{id}/rapor
  Yalnız yönetici: POST /kisiler/crm-aktar · GET /hesaplar · PUT /hesaplar/{kapsam} · GET /sahte-kutu (ENVIRONMENT=test)

Herkese açık (/api/v1/bulten):
  GET|POST /form/{anahtar}       abonelik formu (süre jetonu, bal küpü, köken, hız sınırı) → onay e-postası
  GET|POST /onay/{jeton}         çift onay (72 saat, tek kullanımlık)
  GET|POST /tercih/{jeton}       ret ve liste tercihleri (imzalı, süresiz jeton)
  GET|POST /ret/{jeton}          RFC 8058 tek tık: POST → anında ret; GET → tercih sayfasına yönlendirme
  GET  /a/{jeton}.gif            açılma pikseli (yalnız takip açıkken iletide)
  GET  /t/{jeton}/{i}            tıklama yönlendirmesi (yalnız iletideki bağlantılara)
  GET  /gorsel/{anahtar}         e-posta görseli
  POST /resend-webhook           Resend teslimat olayları (Svix imzası, `RESEND_PAZARLAMA_IMZA_ANAHTARI`)
"""

import io
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from models.eposta_pazarlama import (
    EpAyarlar,
    EpBastirma,
    EpDiziAdimlari,
    EpDiziKayitlari,
    EpDiziler,
    EpFormlar,
    EpGonderimler,
    EpGorseller,
    EpKampanyalar,
    EpKisiler,
    EpListeler,
    EpListeUyelikleri,
    EpSegmentler,
    EpTiklamalar,
    EpWebhookOlaylari,
)
from services import eposta_gonderim as eg
from services import eposta_icerik as ic
from services import eposta_pazarlama as ep
from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = ep.MODUL
IZIN = ep.IZIN
WEBHOOK_ANAHTARI = "RESEND_PAZARLAMA_IMZA_ANAHTARI"
EN_COK_LISTE = 100
EN_COK_FORM = 50
EN_COK_SEGMENT = 50
EN_COK_DIZI = 30
EN_COK_ADIM = 20
EN_COK_GORSEL = 300
GORSEL_EN_COK_BAYT = 5 * 1024 * 1024
GORSEL_KENAR = 1200

yonetici_router = APIRouter(prefix="/api/v1/eposta-pazarlama/yonetim", tags=["eposta-pazarlama"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/eposta-pazarlamam",
    tags=["eposta-pazarlama"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)
acik_router = APIRouter(prefix="/api/v1/bulten", tags=["bulten"])

#: Panel (kişi başı): dakikada 60 yazma; hesap başı saatte 10 test, 10 içe aktarma, 60 görsel.
_yazma_hizi = HizSiniri(60, 60.0)
_test_hizi = HizSiniri(10, 3600.0)
_aktarma_hizi = HizSiniri(10, 3600.0)
_gorsel_hizi = HizSiniri(60, 3600.0)
#: Ziyaretçi (IP özeti): 10 dakikada 5 abonelik; form başına saatte 100; onay/tercih dakikada 30.
_form_hizi = HizSiniri(5, 600.0)
_form_genel_hizi = HizSiniri(100, 3600.0)
_onay_hizi = HizSiniri(30, 60.0)
_tercih_hizi = HizSiniri(30, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _test_hizi, _aktarma_hizi, _gorsel_hizi, _form_hizi, _form_genel_hizi, _onay_hizi, _tercih_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    yonetici: bool
    #: Müşteride etkin hesap; yöneticide None (ajansın kendi hesabı).
    hesap: Optional[str]
    kisi: str

    @property
    def anahtar(self) -> str:
        return ep.kapsam_anahtari(self.hesap)


def _yonetici_kapsami(request: Request) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    return Kapsam(True, None, (getattr(kullanici, "email", "") or "").strip().lower())


def _musteri_kapsami(request: Request) -> Kapsam:
    baglam = izin_iste(request, IZIN)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _ph(h: ep.PazarlamaHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _ih(h: ic.IcerikHatasi) -> HTTPException:
    return HTTPException(status_code=400, detail=h.detay())


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
        raise _hata(429, "cok_hizli")


def _hesap_kosulu(model: Any, hesap: Optional[str]):
    return model.hesap_email.is_(None) if hesap is None else model.hesap_email == hesap


def _bool(ham: Any, alan: str) -> bool:
    if not isinstance(ham, bool):
        raise _hata(400, "deger_gecersiz", alan=alan)
    return ham


def _tam(ham: Any, alan: str, en_az: int, en_cok: int) -> int:
    if isinstance(ham, bool) or not isinstance(ham, (int, float)) or int(ham) != ham or not (en_az <= int(ham) <= en_cok):
        raise _hata(400, "sayi_gecersiz", alan=alan, en_az=en_az, en_cok=en_cok)
    return int(ham)


def _an_coz(ham: Any, alan: str) -> datetime:
    try:
        an = datetime.fromisoformat(str(ham).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise _hata(400, "zaman_gecersiz", alan=alan)
    return ep.utc(an)  # type: ignore[return-value]


def _eposta(ham: Any, alan: str = "eposta") -> str:
    e = ep.eposta_duzelt(ham)
    if not ep.eposta_gecerli(e):
        raise _hata(400, "eposta_gecersiz", alan=alan)
    return e


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _kisi_sozlugu(k: EpKisiler, **ek: Any) -> Dict[str, Any]:
    return {
        "id": k.id, "eposta": k.eposta, "ad": k.ad, "firma": k.firma, "alici_turu": k.alici_turu, "izin_durumu": k.izin_durumu,
        "izin_kaynagi": k.izin_kaynagi, "izin_zamani": ep.iso(k.izin_zamani), "izin_metin_surumu": k.izin_metin_surumu,
        "izin_kaniti": k.izin_kaniti, "onay_zamani": ep.iso(k.onay_zamani), "ret_zamani": ep.iso(k.ret_zamani),
        "ret_kaynagi": k.ret_kaynagi, "kaynak": k.kaynak, "kaynak_detay": k.kaynak_detay, "crm_aday_id": k.crm_aday_id,
        "etiketler": ep.json_yukle(k.etiketler, []), "ozel_alanlar": ep.json_yukle(k.ozel_alanlar, {}), "dil": k.dil,
        "son_etkilesim_at": ep.iso(k.son_etkilesim_at), "son_gonderim_at": ep.iso(k.son_gonderim_at),
        "created_at": ep.iso(k.created_at), **ek,
    }


def _liste_sozlugu(l: EpListeler, sayilar: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    s = sayilar or {}
    return {"id": l.id, "ad": l.ad, "aciklama": l.aciklama or "", "aktif": int(s.get("aktif", 0)),
            "bekliyor": int(s.get("bekliyor", 0)), "cikti": int(s.get("cikti", 0)), "created_at": ep.iso(l.created_at)}


def _form_sozlugu(f: EpFormlar) -> Dict[str, Any]:
    adres = ep.form_adresi(f.genel_anahtar)
    betik = f"{ep.site_adresi()}/bulten-form.js"
    return {
        "id": f.id, "liste_id": f.liste_id, "ad": f.ad, "genel_anahtar": f.genel_anahtar, "baslik": f.baslik or "",
        "aciklama": f.aciklama or "", "dil": f.dil, "ad_sor": bool(f.ad_sor), "tur_sor": bool(f.tur_sor),
        "tesekkur_metni": f.tesekkur_metni or "", "aydinlatma_baglantisi": f.aydinlatma_baglantisi or "",
        "izinli_alanlar": ep.json_yukle(f.izinli_alanlar, []), "aktif": bool(f.aktif),
        "gonderim_sayisi": int(f.gonderim_sayisi or 0), "son_gonderim_at": ep.iso(f.son_gonderim_at), "adres": adres,
        "gomme_kodu": f'<script src="{betik}" async></script>\n<div data-mk-bulten="{f.genel_anahtar}"></div>',
        "created_at": ep.iso(f.created_at),
    }


def _segment_sozlugu(s: EpSegmentler, sayi: Optional[int] = None) -> Dict[str, Any]:
    return {"id": s.id, "ad": s.ad, "kurallar": ep.json_yukle(s.kurallar, {}), "sayi": sayi, "created_at": ep.iso(s.created_at)}


def _kampanya_sozlugu(k: EpKampanyalar, **ek: Any) -> Dict[str, Any]:
    return {
        "id": k.id, "ad": k.ad, "konu": k.konu or "", "onizleme_metni": k.onizleme_metni or "", "gonderen_adi": k.gonderen_adi or "",
        "yanit_adresi": k.yanit_adresi or "", "dil": k.dil, "bloklar": ep.json_yukle(k.bloklar, []),
        "hedef": ep.json_yukle(k.hedef, {"listeler": [], "segmentler": [], "haric_listeler": []}),
        "ab": ep.json_yukle(k.ab, {"acik": False}), "durum": k.durum, "zamanlanan_at": ep.iso(k.zamanlanan_at),
        "baslangic_at": ep.iso(k.baslangic_at), "bitis_at": ep.iso(k.bitis_at), "ab_karar_at": ep.iso(k.ab_karar_at),
        "kazanan": k.kazanan, "duraklatma_nedeni": k.duraklatma_nedeni, "hedef_sayisi": int(k.hedef_sayisi or 0),
        "takip_acilma": bool(k.takip_acilma), "takip_tiklama": bool(k.takip_tiklama), "created_at": ep.iso(k.created_at),
        "updated_at": ep.iso(k.updated_at), **ek,
    }


def _adim_sozlugu(a: EpDiziAdimlari) -> Dict[str, Any]:
    return {"id": a.id, "sira": a.sira, "bekle_gun": int(a.bekle_gun or 0), "bekle_saat": int(a.bekle_saat or 0), "konu": a.konu,
            "onizleme_metni": a.onizleme_metni or "", "bloklar": ep.json_yukle(a.bloklar, [])}


def _dizi_sozlugu(d: EpDiziler, adimlar: List[EpDiziAdimlari], **ek: Any) -> Dict[str, Any]:
    return {"id": d.id, "ad": d.ad, "tetik": d.tetik, "liste_id": d.liste_id, "aktif": bool(d.aktif),
            "cikis": ep.json_yukle(d.cikis, {"hedef": None}), "gonderen_adi": d.gonderen_adi or "", "dil": d.dil,
            "adimlar": [_adim_sozlugu(a) for a in adimlar], "created_at": ep.iso(d.created_at), **ek}


def _ayar_sozlugu(a: EpAyarlar) -> Dict[str, Any]:
    return {
        "gonderen_adi": a.gonderen_adi or "", "yanit_adresi": a.yanit_adresi or "", "unvan": a.unvan or "", "adres": a.adres or "",
        "logo_url": a.logo_url or "", "marka_rengi": a.marka_rengi or ic.VARSAYILAN_RENK, "dil": a.dil, "iys_durumu": a.iys_durumu,
        "iys_marka_kodu": a.iys_marka_kodu or "", "acilma_takibi": bool(a.acilma_takibi), "tiklama_takibi": bool(a.tiklama_takibi),
        "gunluk_kisi_siniri": int(a.gunluk_kisi_siniri or 0), "askida": bool(a.askida), "askida_neden": a.askida_neden,
        "askida_at": ep.iso(a.askida_at),
    }


# ---------------------------------------------------------------------------
# Bulucular
# ---------------------------------------------------------------------------
async def _bul(db: AsyncSession, model: Any, kimlik: int, hesap: Optional[str]) -> Any:
    k = (await db.execute(select(model).where(model.id == kimlik, _hesap_kosulu(model, hesap)))).scalars().first()
    if k is None:
        raise _hata(404, "bulunamadi")
    return k


async def _kisi(db: AsyncSession, kimlik: int, kapsam: Kapsam) -> EpKisiler:
    k = (await db.execute(select(EpKisiler).where(EpKisiler.id == kimlik, EpKisiler.kapsam == kapsam.anahtar))).scalars().first()
    if k is None:
        raise _hata(404, "bulunamadi")
    return k


async def _liste_sayilari(db: AsyncSession, liste_idleri: List[int]) -> Dict[int, Dict[str, int]]:
    if not liste_idleri:
        return {}
    satirlar = (await db.execute(
        select(EpListeUyelikleri.liste_id, EpListeUyelikleri.durum, func.count(EpListeUyelikleri.id))
        .where(EpListeUyelikleri.liste_id.in_(liste_idleri)).group_by(EpListeUyelikleri.liste_id, EpListeUyelikleri.durum)
    )).all()
    sonuc: Dict[int, Dict[str, int]] = {}
    for lid, durum, n in satirlar:
        sonuc.setdefault(lid, {})[durum] = int(n)
    return sonuc


async def _hesap_listeleri(db: AsyncSession, hesap: Optional[str], idler: List[int]) -> List[int]:
    if not idler:
        return []
    return list((await db.execute(select(EpListeler.id).where(EpListeler.id.in_(idler), _hesap_kosulu(EpListeler, hesap)))).scalars().all())


async def _uyelik_ekle(db: AsyncSession, kisi: EpKisiler, liste_id: int, kaynak: str) -> bool:
    """Listeye aktif üye yap (ret etmişse hayır). Yeni katılımda "liste_katildi" dizileri. Commit çağırana."""
    if kisi.izin_durumu == "reddetti":
        return False
    u = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.liste_id == liste_id, EpListeUyelikleri.kisi_id == kisi.id))).scalars().first()
    an = ep.simdi()
    if u is not None:
        if u.durum == "aktif":
            return False
        u.durum, u.katilma_at, u.kaynak, u.cikis_at = "aktif", an, kaynak, None
    else:
        try:
            async with db.begin_nested():
                db.add(EpListeUyelikleri(liste_id=liste_id, kisi_id=kisi.id, durum="aktif", kaynak=kaynak, katilma_at=an, created_at=an))
                await db.flush()
        except IntegrityError:
            return False
    await eg.diziye_kaydet(db, kisi, liste_id, ("liste_katildi",))
    return True


async def _kisi_sayisi(db: AsyncSession, kapsam: str) -> int:
    return int((await db.execute(select(func.count(EpKisiler.id)).where(EpKisiler.kapsam == kapsam))).scalar() or 0)


async def _kisi_siniri_denetle(db: AsyncSession, hesap: Optional[str], eklenecek: int = 1) -> None:
    sinir = await eg.kisi_siniri(db, hesap)
    if sinir is not None and await _kisi_sayisi(db, ep.kapsam_anahtari(hesap)) + eklenecek > sinir:
        raise _hata(409, "kisi_siniri", sinir=sinir)


# ---------------------------------------------------------------------------
# Görsel hazırlama (e-posta uyumlu: JPEG, saydamsa PNG; ≤ 1200 px)
# ---------------------------------------------------------------------------
def _gorsel_hazirla(bayt: bytes) -> Dict[str, Any]:
    if len(bayt) > GORSEL_EN_COK_BAYT:
        raise _hata(413, "gorsel_buyuk", en_cok_mb=GORSEL_EN_COK_BAYT // (1024 * 1024))
    if not bayt:
        raise _hata(400, "gorsel_gecersiz")
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(bayt)) as ham:
            if ham.format not in ("JPEG", "PNG", "WEBP", "GIF"):
                raise _hata(415, "gorsel_turu")
            if ham.size[0] < 8 or ham.size[1] < 8 or ham.size[0] * ham.size[1] > 40_000_000:
                raise _hata(400, "gorsel_boyutu")
            ham.load()
            g = ImageOps.exif_transpose(ham)
            saydam = g.mode in ("RGBA", "LA") or (g.mode == "P" and "transparency" in g.info)
            g = g.convert("RGBA" if saydam else "RGB")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - bozuk dosya
        raise _hata(400, "gorsel_gecersiz") from exc
    g.thumbnail((GORSEL_KENAR, GORSEL_KENAR * 4), Image.LANCZOS)
    cikti = io.BytesIO()
    if saydam:
        g.save(cikti, format="PNG", optimize=True)
        tur, uzanti = "image/png", "png"
    else:
        g.save(cikti, format="JPEG", quality=82, optimize=True, progressive=True)
        tur, uzanti = "image/jpeg", "jpg"
    return {"veri": cikti.getvalue(), "tur": tur, "uzanti": uzanti, "genislik": g.width, "yukseklik": g.height}


# ---------------------------------------------------------------------------
# Kampanya ön denetimleri
# ---------------------------------------------------------------------------
async def _on_denetim(db: AsyncSession, k: EpKampanyalar) -> Dict[str, Any]:
    """Zamanlamadan önce (gönderim anında da yeniden): askı, Resend, kimlik, konu, hedef, içerik, A/B, kota."""
    ayar = await eg.ayar_getir(db, k.hesap_email)
    if ayar.askida:
        raise _hata(409, "hesap_askida", neden=ayar.askida_neden)
    if not eg.resend_kurulu():
        raise _hata(409, "resend_kurulu_degil")
    kimlik = await eg.kimlik_getir(db, k.hesap_email, ayar)
    if not kimlik.tamam:
        raise _hata(409, "gonderen_kimligi_eksik", eksik=kimlik.eksik)
    if not (k.konu or "").strip():
        raise _hata(400, "metin_gerekli", alan="konu")
    try:
        hedef = eg.hedef_duzelt(k.hedef)
        if not ic.bloklari_dogrula(k.bloklar, izinli_onek=ep.site_adresi()):
            raise _hata(400, "icerik_bos", alan="bloklar")
        ab = ep.ab_duzelt(k.ab)
    except ep.PazarlamaHatasi as h:
        raise _ph(h)
    except ic.IcerikHatasi as h:
        raise _ih(h)
    if not hedef["listeler"] and not hedef["segmentler"]:
        raise _hata(400, "hedef_gerekli", alan="hedef")
    ozet = await eg.kitle_ozeti(db, k.hesap_email, hedef)
    if ozet["gonderilebilir"] == 0:
        raise _hata(409, "kitle_bos", atlanacak=ozet["atlanacak"])
    if ab.get("acik") and ozet["gonderilebilir"] < 10:
        raise _hata(409, "ab_kitle_kucuk")
    sinir = await eg.aylik_sinir(db, k.hesap_email)
    if sinir is not None:
        kalan = sinir - await eg.aylik_kullanim(db, ep.kapsam_anahtari(k.hesap_email))
        if ozet["gonderilebilir"] > kalan:
            raise _hata(409, "kota_yetersiz", kalan=max(0, kalan), gerekli=ozet["gonderilebilir"])
    return ozet


async def _rapor(db: AsyncSession, k: EpKampanyalar, alici_siniri: int = 100) -> Dict[str, Any]:
    genel = await eg.kampanya_istatistik(db, k.id)
    ab_acik = bool(ep.json_yukle(k.ab, {}).get("acik"))
    varyantlar = {v: await eg.kampanya_istatistik(db, k.id, v) for v in ("a", "b")} if ab_acik else {}
    nedenler = dict((await db.execute(
        select(EpGonderimler.neden, func.count(EpGonderimler.id))
        .where(EpGonderimler.kampanya_id == k.id, EpGonderimler.durum == "atlandi").group_by(EpGonderimler.neden)
    )).all())
    durumlar = dict((await db.execute(
        select(EpGonderimler.durum, func.count(EpGonderimler.id)).where(EpGonderimler.kampanya_id == k.id).group_by(EpGonderimler.durum)
    )).all())
    baglantilar = ep.json_yukle(k.baglantilar, [])
    tiklamalar = dict((await db.execute(
        select(EpTiklamalar.indeks, func.count(EpTiklamalar.id)).where(EpTiklamalar.kampanya_id == k.id).group_by(EpTiklamalar.indeks)
    )).all())
    alicilar = (await db.execute(
        select(EpGonderimler).where(EpGonderimler.kampanya_id == k.id).order_by(EpGonderimler.id).limit(alici_siniri)
    )).scalars().all()

    def oran(pay: int, payda: int) -> Optional[float]:
        return round(pay / payda, 4) if payda else None

    payda = genel["teslim"] or genel["gonderilen"]
    return {
        "kampanya": _kampanya_sozlugu(k),
        "sayilar": {**genel, "atlanan": int(durumlar.get("atlandi", 0)), "hata": int(durumlar.get("hata", 0)),
                    "bekleyen": sum(int(durumlar.get(d, 0)) for d in eg.BEKLEYEN)},
        "oranlar": {
            "teslim": oran(genel["teslim"], genel["gonderilen"]), "geri_donme": oran(genel["geri_donen"], genel["gonderilen"]),
            "sikayet": oran(genel["sikayet"], genel["gonderilen"]), "ret": oran(genel["ret"], genel["gonderilen"]),
            "acilma": oran(genel["acilan"], payda) if k.takip_acilma else None,
            "tiklama": oran(genel["tiklayan"], payda) if k.takip_tiklama else None,
        },
        "atlama_nedenleri": {str(n or "diger"): int(s) for n, s in nedenler.items()},
        "varyantlar": varyantlar,
        "baglantilar": [{"indeks": i, "url": u, "tiklama": int(tiklamalar.get(i, 0))} for i, u in enumerate(baglantilar)],
        "alicilar": [{"eposta": g.eposta, "durum": g.durum, "neden": g.neden, "varyant": g.varyant, "gonderim_at": ep.iso(g.gonderim_at),
                      "acilma_at": ep.iso(g.acilma_at), "tiklama_at": ep.iso(g.tiklama_at)} for g in alicilar],
    }


# ---------------------------------------------------------------------------
# Panel uçları (yönetici + müşteri)
# ---------------------------------------------------------------------------
IYS_BILGI = {
    "baglanti": "https://iys.org.tr",
    "not": "iys_bilgi",
}


def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    # --- Meta, özet, ayarlar ---
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        ayar = await eg.ayar_getir(db, kapsam.hesap)
        await db.commit()
        kimlik = await eg.kimlik_getir(db, kapsam.hesap, ayar)
        sinir = await eg.aylik_sinir(db, kapsam.hesap)
        kisi_siniri = await eg.kisi_siniri(db, kapsam.hesap)
        veri: Dict[str, Any] = {
            "yonetici": kapsam.yonetici,
            "hesap": kapsam.hesap,
            "resend_kurulu": eg.resend_kurulu(),
            "sahte_mod": eg.sahte_mod(),
            "kimlik": {"gonderen_adi": kimlik.gonderen_adi, "unvan": kimlik.unvan, "adres": kimlik.adres, "eksik": kimlik.eksik,
                       "yanit_adresi": kimlik.yanit_adresi, "kaynak": "yasal_ayarlar" if kapsam.hesap is None else "hesap_ayarlari"},
            "gonderen_adresi": eg.gonderen_adresi(),
            "sinirlar": {"aylik": sinir, "kullanilan": await eg.aylik_kullanim(db, kapsam.anahtar), "kisi": kisi_siniri,
                         "kisi_sayisi": await _kisi_sayisi(db, kapsam.anahtar), "gunluk_kisi": int(ayar.gunluk_kisi_siniri or 0)},
            "yer_tutucular": list(ic.YER_TUTUCULAR),
            "blok_turleri": list(ic.BLOK_TURLERI),
            "segment_alanlari": [a for a in ep.SEGMENT_ALANLARI if kapsam.hesap is None or a not in ep.YALNIZ_AJANS_ALANLARI],
            "segment_oplari": {a: list(o) for a, o in ep.SEGMENT_OPLARI.items()},
            "tetikler": list(ep.TETIKLER),
            "diller": list(ep.DILLER),
            "iys": IYS_BILGI,
            "form_betigi": f"{ep.site_adresi()}/bulten-form.js",
            "csv_sutunlari": ["eposta", "ad", "firma", "alici_turu", "izin_kaynagi", "izin_tarihi", "etiketler", "dil"],
        }
        if kapsam.yonetici:
            from routers.destek_eposta import _arka_uc_adresi

            veri["webhook"] = {"adres": f"{_arka_uc_adresi(request)}/api/v1/bulten/resend-webhook",
                               "imza_tanimli": bool((os.environ.get(WEBHOOK_ANAHTARI) or "").strip()),
                               "ortam_degiskeni": WEBHOOK_ANAHTARI}
        return veri

    @router.get("/ozet")
    async def ozet(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        izin = dict((await db.execute(select(EpKisiler.izin_durumu, func.count(EpKisiler.id)).where(EpKisiler.kapsam == kapsam.anahtar)
                                      .group_by(EpKisiler.izin_durumu))).all())
        tur = dict((await db.execute(select(EpKisiler.alici_turu, func.count(EpKisiler.id)).where(EpKisiler.kapsam == kapsam.anahtar)
                                     .group_by(EpKisiler.alici_turu))).all())
        bastirma = int((await db.execute(select(func.count(EpBastirma.id)).where(EpBastirma.kapsam == kapsam.anahtar))).scalar() or 0)
        son = (await db.execute(select(EpKampanyalar).where(_hesap_kosulu(EpKampanyalar, kapsam.hesap))
                                .order_by(desc(EpKampanyalar.id)).limit(5))).scalars().all()
        sinir30 = ep.simdi() - timedelta(days=30)
        g = (await db.execute(select(func.count(EpGonderimler.gonderim_at), func.count(EpGonderimler.sikayet_at),
                                     func.count(EpGonderimler.geri_donme_at))
                              .where(EpGonderimler.kapsam == kapsam.anahtar, EpGonderimler.gonderim_at >= sinir30))).one()
        return {
            "kisiler": {"toplam": sum(int(v) for v in izin.values()), "izin": {k: int(v) for k, v in izin.items()},
                        "tur": {k: int(v) for k, v in tur.items()}, "bastirilan": bastirma},
            "son_30_gun": {"gonderilen": int(g[0] or 0), "sikayet": int(g[1] or 0), "geri_donen": int(g[2] or 0)},
            "son_kampanyalar": [_kampanya_sozlugu(k) for k in son],
        }

    @router.get("/ayarlar")
    async def ayarlar(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        a = await eg.ayar_getir(db, kapsam.hesap)
        await db.commit()
        return _ayar_sozlugu(a)

    @router.put("/ayarlar")
    async def ayarlar_yaz(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        a = await eg.ayar_getir(db, kapsam.hesap)
        try:
            if "gonderen_adi" in govde:
                a.gonderen_adi = ep.metin(govde.get("gonderen_adi"), "gonderen_adi", 80) or None
            if "yanit_adresi" in govde:
                ham = str(govde.get("yanit_adresi") or "").strip()
                a.yanit_adresi = _eposta(ham, "yanit_adresi") if ham else None
            if "unvan" in govde:
                a.unvan = ep.metin(govde.get("unvan"), "unvan", 200) or None
            if "adres" in govde:
                a.adres = ep.metin(govde.get("adres"), "adres", 400) or None
            if "logo_url" in govde:
                ham = str(govde.get("logo_url") or "").strip()
                a.logo_url = ic.adres_dogrula(ham, "logo_url", gorsel=True, izinli_onek=ep.site_adresi()) if ham else None
            if "marka_rengi" in govde:
                a.marka_rengi = ic.renk_duzelt(govde.get("marka_rengi"))
            if "dil" in govde:
                a.dil = ep.dil_sec(govde.get("dil"))
            if "iys_durumu" in govde:
                if govde.get("iys_durumu") not in ep.IYS_DURUMLARI:
                    raise _hata(400, "secim_gecersiz", alan="iys_durumu")
                a.iys_durumu = govde["iys_durumu"]
            if "iys_marka_kodu" in govde:
                a.iys_marka_kodu = ep.metin(govde.get("iys_marka_kodu"), "iys_marka_kodu", 40) or None
            for alan in ("acilma_takibi", "tiklama_takibi"):
                if alan in govde:
                    setattr(a, alan, _bool(govde.get(alan), alan))
            if "gunluk_kisi_siniri" in govde:
                a.gunluk_kisi_siniri = _tam(govde.get("gunluk_kisi_siniri"), "gunluk_kisi_siniri", 1, 5)
        except ep.PazarlamaHatasi as h:
            await db.rollback()
            raise _ph(h)
        except ic.IcerikHatasi as h:
            await db.rollback()
            raise _ih(h)
        await db.commit()
        return _ayar_sozlugu(a)

    # --- Kişiler ---
    @router.get("/kisiler")
    async def kisiler(
        request: Request, ara: Optional[str] = Query(None), liste_id: Optional[int] = Query(None), izin: Optional[str] = Query(None),
        tur: Optional[str] = Query(None), kaynak: Optional[str] = Query(None), sinir: int = Query(50, ge=1, le=200),
        atla: int = Query(0, ge=0), db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        sorgu = select(EpKisiler).where(EpKisiler.kapsam == kapsam.anahtar)
        if ara:
            desen = f"%{ara.strip().lower()[:80]}%"
            sorgu = sorgu.where(or_(EpKisiler.eposta.like(desen), func.lower(EpKisiler.ad).like(desen), func.lower(EpKisiler.firma).like(desen)))
        if izin in ep.IZIN_DURUMLARI:
            sorgu = sorgu.where(EpKisiler.izin_durumu == izin)
        if tur in ep.ALICI_TURLERI:
            sorgu = sorgu.where(EpKisiler.alici_turu == tur)
        if kaynak in ep.KAYNAKLAR:
            sorgu = sorgu.where(EpKisiler.kaynak == kaynak)
        if liste_id is not None:
            sorgu = sorgu.join(EpListeUyelikleri, EpListeUyelikleri.kisi_id == EpKisiler.id).where(
                EpListeUyelikleri.liste_id == liste_id, EpListeUyelikleri.durum.in_(("aktif", "bekliyor")))
        toplam = int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)
        kayitlar = (await db.execute(sorgu.order_by(desc(EpKisiler.id)).offset(atla).limit(sinir))).scalars().all()
        bastirilan = await eg.bastirilmis_kume(db, kapsam.anahtar, [k.eposta for k in kayitlar])
        uyelikler = await eg.uyelik_haritasi(db, [k.id for k in kayitlar])
        return {"items": [_kisi_sozlugu(k, bastirilmis=k.eposta in bastirilan, listeler=sorted(uyelikler.get(k.id, set())))
                          for k in kayitlar], "toplam": toplam}

    @router.post("/kisiler")
    async def kisi_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        eposta = _eposta(govde.get("eposta"))
        var = (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam.anahtar, EpKisiler.eposta == eposta))).scalars().first()
        if var is not None:
            raise _hata(409, "kisi_var", id=var.id)
        await _kisi_siniri_denetle(db, kapsam.hesap)
        try:
            tur = govde.get("alici_turu") or "bireysel"
            if tur not in ep.ALICI_TURLERI:
                raise _hata(400, "secim_gecersiz", alan="alici_turu")
            k = EpKisiler(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, eposta=eposta,
                          ad=ep.metin(govde.get("ad"), "ad", 120) or None, firma=ep.metin(govde.get("firma"), "firma", 160) or None,
                          alici_turu=tur, izin_durumu="izinsiz", kaynak="manuel", kaynak_detay=kapsam.kisi[:120] or None,
                          etiketler=ep.json_yaz(ep.etiketleri_duzelt(govde.get("etiketler"))),
                          ozel_alanlar=ep.json_yaz(ep.ozel_alanlari_duzelt(govde.get("ozel_alanlar"))),
                          dil=ep.dil_sec(govde.get("dil")), created_at=ep.simdi())
            _izin_isle(k, govde.get("izin"))
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        db.add(k)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "kisi_var")
        for lid in await _hesap_listeleri(db, kapsam.hesap, [x for x in (govde.get("listeler") or []) if isinstance(x, int)]):
            await _uyelik_ekle(db, k, lid, "manuel")
        await db.commit()
        return _kisi_sozlugu(k)

    @router.get("/kisiler/{kid}")
    async def kisi_ayrinti(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _kisi(db, kid, kapsam)
        bastirilan = await eg.bastirilmis_kume(db, kapsam.anahtar, [k.eposta])
        uyelikler = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.kisi_id == k.id))).scalars().all()
        gonderimler = (await db.execute(select(EpGonderimler).where(EpGonderimler.kisi_id == k.id).order_by(desc(EpGonderimler.id)).limit(30))).scalars().all()
        return _kisi_sozlugu(
            k, bastirilmis=k.eposta in bastirilan,
            uyelikler=[{"liste_id": u.liste_id, "durum": u.durum, "kaynak": u.kaynak, "katilma_at": ep.iso(u.katilma_at),
                        "izin_metin_surumu": u.izin_metin_surumu} for u in uyelikler],
            gonderimler=[{"kampanya_id": g.kampanya_id, "dizi_id": g.dizi_id, "durum": g.durum, "neden": g.neden,
                          "gonderim_at": ep.iso(g.gonderim_at)} for g in gonderimler],
        )

    @router.put("/kisiler/{kid}")
    async def kisi_guncelle(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        k = await _kisi(db, kid, kapsam)
        try:
            if "ad" in govde:
                k.ad = ep.metin(govde.get("ad"), "ad", 120) or None
            if "firma" in govde:
                k.firma = ep.metin(govde.get("firma"), "firma", 160) or None
            if "alici_turu" in govde:
                if govde.get("alici_turu") not in ep.ALICI_TURLERI:
                    raise _hata(400, "secim_gecersiz", alan="alici_turu")
                k.alici_turu = govde["alici_turu"]
            if "etiketler" in govde:
                k.etiketler = ep.json_yaz(ep.etiketleri_duzelt(govde.get("etiketler")))
            if "ozel_alanlar" in govde:
                k.ozel_alanlar = ep.json_yaz(ep.ozel_alanlari_duzelt(govde.get("ozel_alanlar")))
            if "dil" in govde:
                k.dil = ep.dil_sec(govde.get("dil"))
            if govde.get("izin") is not None:
                if k.izin_durumu == "reddetti":
                    # Ret kalıcı: kişi ancak abonelik formundan yeniden (çift onayla) abone olabilir.
                    raise _hata(409, "ret_kalici")
                _izin_isle(k, govde.get("izin"))
        except ep.PazarlamaHatasi as h:
            await db.rollback()
            raise _ph(h)
        await db.commit()
        return _kisi_sozlugu(k)

    @router.post("/kisiler/{kid}/ret")
    async def kisi_ret(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _kisi(db, kid, kapsam)
        await eg.ret_et(db, k, "yonetici")
        await db.commit()
        return _kisi_sozlugu(k, bastirilmis=True)

    @router.delete("/kisiler/{kid}")
    async def kisi_sil(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Kalıcı silme (KVKK silme talebi). Bastırma kaydı kalır: ret etmiş kişiye bir daha gönderilmez."""
        kapsam = kapsam_al(request)
        k = await _kisi(db, kid, kapsam)
        if k.izin_durumu == "reddetti":
            await eg.bastirmaya_ekle(db, k.kapsam, k.eposta, "ret", "kisi_silindi")
        await db.execute(delete(EpListeUyelikleri).where(EpListeUyelikleri.kisi_id == k.id))
        await db.execute(update(EpDiziKayitlari).where(EpDiziKayitlari.kisi_id == k.id, EpDiziKayitlari.durum == "aktif")
                         .values(durum="cikti", cikis_nedeni="kisi_silindi", bitis_at=ep.simdi()).execution_options(synchronize_session=False))
        await db.execute(update(EpGonderimler).where(EpGonderimler.kisi_id == k.id, EpGonderimler.durum.in_(("kuyrukta", "ab_bekliyor")))
                         .values(durum="atlandi", neden="kisi_silindi").execution_options(synchronize_session=False))
        await db.execute(update(EpGonderimler).where(EpGonderimler.kisi_id == k.id).values(eposta=None).execution_options(synchronize_session=False))
        await db.delete(k)
        await db.commit()
        return {"ok": True}

    # --- CSV içe aktarma ---
    @router.post("/kisiler/ice-aktar/onizleme")
    async def ice_aktar_onizleme(request: Request, dosya: UploadFile = File(...), varsayilan_tur: str = Form("bireysel"),
                                 db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        bayt = await dosya.read(ep.CSV_EN_COK_BAYT + 1)
        try:
            sonuc = ep.csv_coz(bayt, varsayilan_tur if varsayilan_tur in ep.ALICI_TURLERI else "bireysel")
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        mevcut = set()
        epostalar = [s["eposta"] for s in sonuc["satirlar"]]
        for i in range(0, len(epostalar), 500):
            mevcut.update((await db.execute(select(EpKisiler.eposta).where(EpKisiler.kapsam == kapsam.anahtar,
                                                                           EpKisiler.eposta.in_(epostalar[i:i + 500])))).scalars().all())
        bastirilan = await eg.bastirilmis_kume(db, kapsam.anahtar, epostalar)
        return {"ozet": {**sonuc["ozet"], "mevcut": len(mevcut), "bastirilan": len(bastirilan)},
                "ornek": sonuc["satirlar"][:20], "hatalar": sonuc["hatalar"][:50]}

    @router.post("/kisiler/ice-aktar")
    async def ice_aktar(request: Request, dosya: UploadFile = File(...), liste_id: Optional[int] = Form(None),
                        varsayilan_tur: str = Form("bireysel"), kaynak_notu: str = Form(""), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_aktarma_hizi, kapsam.anahtar)
        if liste_id is not None and not await _hesap_listeleri(db, kapsam.hesap, [liste_id]):
            raise _hata(404, "liste_yok")
        bayt = await dosya.read(ep.CSV_EN_COK_BAYT + 1)
        try:
            sonuc = ep.csv_coz(bayt, varsayilan_tur if varsayilan_tur in ep.ALICI_TURLERI else "bireysel")
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        satirlar = sonuc["satirlar"]
        epostalar = [s["eposta"] for s in satirlar]
        mevcut: Dict[str, EpKisiler] = {}
        for i in range(0, len(epostalar), 500):
            for k in (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam.anahtar,
                                                               EpKisiler.eposta.in_(epostalar[i:i + 500])))).scalars().all():
                mevcut[k.eposta] = k
        yeni_sayi = sum(1 for s in satirlar if s["eposta"] not in mevcut)
        await _kisi_siniri_denetle(db, kapsam.hesap, yeni_sayi)
        dosya_adi = (dosya.filename or "csv")[:60]
        not_ = " ".join(str(kaynak_notu or "").split())[:200]
        an = ep.simdi()
        sayac = {"eklenen": 0, "guncellenen": 0, "izinli": 0, "izinsiz": 0, "ret_korundu": 0, "listeye": 0}
        for s in satirlar:
            k = mevcut.get(s["eposta"])
            if k is None:
                k = EpKisiler(kapsam=kapsam.anahtar, hesap_email=kapsam.hesap, eposta=s["eposta"], ad=s["ad"], firma=s["firma"],
                              alici_turu=s["alici_turu"], izin_durumu="izinsiz", kaynak="csv", kaynak_detay=dosya_adi,
                              etiketler=ep.json_yaz(s["etiketler"]), ozel_alanlar="{}", dil=s["dil"] or "tr", created_at=an)
                db.add(k)
                mevcut[s["eposta"]] = k
                sayac["eklenen"] += 1
            else:
                sayac["guncellenen"] += 1
                k.ad = k.ad or s["ad"]
                k.firma = k.firma or s["firma"]
                if s["etiketler"]:
                    k.etiketler = ep.json_yaz(sorted(set(ep.json_yukle(k.etiketler, [])) | set(s["etiketler"]))[:20])
            if k.izin_durumu == "reddetti":
                sayac["ret_korundu"] += 1  # ret kalıcı: CSV izni ezemez
            elif s["izinli"] and k.izin_durumu != "izinli":
                k.izin_durumu = "izinli"
                k.izin_kaynagi = f"csv:{s['izin_kaynagi']}"[:200]
                k.izin_zamani = ep.utc(datetime.fromisoformat(s["izin_zamani"].replace("Z", "+00:00")))
                k.izin_metin_surumu = "csv"
                k.izin_kaniti = ep.json_yaz({"yontem": "csv_beyani", "dosya": dosya_adi, "not": not_, "aktaran": kapsam.kisi,
                                             "aktarma": ep.iso(an)})
            sayac["izinli" if k.izin_durumu == "izinli" else "izinsiz"] += 1
        await db.flush()
        if liste_id is not None:
            for s in satirlar:
                k = mevcut.get(s["eposta"])
                if k is not None and await _uyelik_ekle(db, k, liste_id, "csv"):
                    sayac["listeye"] += 1
        await db.commit()
        return {"sayilar": sayac, "hatalar": sonuc["hatalar"][:50], "ozet": sonuc["ozet"]}

    # --- Bastırma listesi ---
    @router.get("/bastirma")
    async def bastirma(request: Request, ara: Optional[str] = Query(None), sinir: int = Query(100, ge=1, le=500),
                       atla: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(EpBastirma).where(EpBastirma.kapsam == kapsam.anahtar)
        if ara:
            sorgu = sorgu.where(EpBastirma.eposta.like(f"%{ara.strip().lower()[:80]}%"))
        toplam = int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)
        kayitlar = (await db.execute(sorgu.order_by(desc(EpBastirma.id)).offset(atla).limit(sinir))).scalars().all()
        return {"items": [{"id": b.id, "eposta": b.eposta, "neden": b.neden, "kaynak": b.kaynak, "created_at": ep.iso(b.created_at)}
                          for b in kayitlar], "toplam": toplam}

    @router.post("/bastirma")
    async def bastirma_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        eposta = _eposta(govde.get("eposta"))
        eklendi = await eg.bastirmaya_ekle(db, kapsam.anahtar, eposta, "elle", ep.metin(govde.get("not"), "not", 120) or kapsam.kisi)
        await db.commit()
        return {"ok": True, "eklendi": eklendi}

    @router.delete("/bastirma/{bid}")
    async def bastirma_sil(bid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        b = (await db.execute(select(EpBastirma).where(EpBastirma.id == bid, EpBastirma.kapsam == kapsam.anahtar))).scalars().first()
        if b is None:
            raise _hata(404, "bulunamadi")
        if b.neden != "elle":
            # Ret/şikâyet kalıcı; sert geri dönüş ortak (bütün hesaplar).
            raise _hata(409, "bastirma_kalici", neden=b.neden)
        await db.delete(b)
        await db.commit()
        return {"ok": True}

    # --- Listeler ---
    @router.get("/listeler")
    async def listeler(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        kayitlar = (await db.execute(select(EpListeler).where(_hesap_kosulu(EpListeler, kapsam.hesap)).order_by(EpListeler.id))).scalars().all()
        sayilar = await _liste_sayilari(db, [l.id for l in kayitlar])
        return {"items": [_liste_sozlugu(l, sayilar.get(l.id)) for l in kayitlar]}

    @router.post("/listeler")
    async def liste_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        sayi = int((await db.execute(select(func.count(EpListeler.id)).where(_hesap_kosulu(EpListeler, kapsam.hesap)))).scalar() or 0)
        if sayi >= EN_COK_LISTE:
            raise _hata(409, "sinir_doldu", sinir=EN_COK_LISTE)
        try:
            l = EpListeler(hesap_email=kapsam.hesap, ad=ep.metin(govde.get("ad"), "ad", 120, zorunlu=True),
                           aciklama=ep.metin(govde.get("aciklama"), "aciklama", 500, cok_satir=True) or None, created_at=ep.simdi())
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        db.add(l)
        await db.commit()
        return _liste_sozlugu(l)

    @router.put("/listeler/{lid}")
    async def liste_guncelle(lid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        l = await _bul(db, EpListeler, lid, kapsam.hesap)
        try:
            if "ad" in govde:
                l.ad = ep.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "aciklama" in govde:
                l.aciklama = ep.metin(govde.get("aciklama"), "aciklama", 500, cok_satir=True) or None
        except ep.PazarlamaHatasi as h:
            await db.rollback()
            raise _ph(h)
        await db.commit()
        return _liste_sozlugu(l, (await _liste_sayilari(db, [l.id])).get(l.id))

    @router.delete("/listeler/{lid}")
    async def liste_sil(lid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        l = await _bul(db, EpListeler, lid, kapsam.hesap)
        form = (await db.execute(select(EpFormlar.id).where(EpFormlar.liste_id == l.id).limit(1))).first()
        dizi = (await db.execute(select(EpDiziler.id).where(EpDiziler.liste_id == l.id).limit(1))).first()
        if form is not None or dizi is not None:
            raise _hata(409, "liste_kullaniliyor")
        await db.execute(delete(EpListeUyelikleri).where(EpListeUyelikleri.liste_id == l.id))
        await db.delete(l)
        await db.commit()
        return {"ok": True}

    @router.post("/listeler/{lid}/uyeler")
    async def liste_uye_ekle(lid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        l = await _bul(db, EpListeler, lid, kapsam.hesap)
        idler = [x for x in (govde.get("kisi_idleri") or []) if isinstance(x, int) and not isinstance(x, bool)][:1000]
        kisiler = (await db.execute(select(EpKisiler).where(EpKisiler.id.in_(idler), EpKisiler.kapsam == kapsam.anahtar))).scalars().all() if idler else []
        eklenen = 0
        for k in kisiler:
            if await _uyelik_ekle(db, k, l.id, "manuel"):
                eklenen += 1
        await db.commit()
        return {"eklenen": eklenen, "atlanan": len(idler) - eklenen}

    @router.delete("/listeler/{lid}/uyeler/{kid}")
    async def liste_uye_cikar(lid: int, kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        l = await _bul(db, EpListeler, lid, kapsam.hesap)
        k = await _kisi(db, kid, kapsam)
        u = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.liste_id == l.id, EpListeUyelikleri.kisi_id == k.id))).scalars().first()
        if u is None:
            raise _hata(404, "bulunamadi")
        u.durum, u.cikis_at = "cikti", ep.simdi()
        await db.commit()
        return {"ok": True}

    # --- Abonelik formları ---
    @router.get("/formlar")
    async def formlar(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        kayitlar = (await db.execute(select(EpFormlar).where(_hesap_kosulu(EpFormlar, kapsam.hesap)).order_by(EpFormlar.id))).scalars().all()
        return {"items": [_form_sozlugu(f) for f in kayitlar]}

    async def _form_alanlari(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any], f: Optional[EpFormlar]) -> Dict[str, Any]:
        from services.crm_form import FormHatasi, https_adresi, izinli_alanlari_duzelt

        d: Dict[str, Any] = {}
        try:
            if "liste_id" in govde or f is None:
                lid = govde.get("liste_id")
                if not isinstance(lid, int) or not await _hesap_listeleri(db, kapsam.hesap, [lid]):
                    raise _hata(400, "liste_yok", alan="liste_id")
                d["liste_id"] = lid
            if "ad" in govde or f is None:
                d["ad"] = ep.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "baslik" in govde:
                d["baslik"] = ep.metin(govde.get("baslik"), "baslik", 160) or None
            if "aciklama" in govde:
                d["aciklama"] = ep.metin(govde.get("aciklama"), "aciklama", 600, cok_satir=True) or None
            if "dil" in govde:
                d["dil"] = ep.dil_sec(govde.get("dil"))
            for alan in ("ad_sor", "tur_sor", "aktif"):
                if alan in govde:
                    d[alan] = _bool(govde.get(alan), alan)
            if "tesekkur_metni" in govde:
                d["tesekkur_metni"] = ep.metin(govde.get("tesekkur_metni"), "tesekkur_metni", 600, cok_satir=True) or None
            if "aydinlatma_baglantisi" in govde:
                try:
                    d["aydinlatma_baglantisi"] = https_adresi(govde.get("aydinlatma_baglantisi"), "aydinlatma_https")
                except FormHatasi as h:
                    raise _hata(400, h.kod, alan="aydinlatma_baglantisi")
            if "izinli_alanlar" in govde:
                d["izinli_alanlar"] = json.dumps(izinli_alanlari_duzelt(govde.get("izinli_alanlar")))
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        except FormHatasi as h:
            raise _hata(400, h.kod, alan="izinli_alanlar")
        return d

    @router.post("/formlar")
    async def form_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        sayi = int((await db.execute(select(func.count(EpFormlar.id)).where(_hesap_kosulu(EpFormlar, kapsam.hesap)))).scalar() or 0)
        if sayi >= EN_COK_FORM:
            raise _hata(409, "sinir_doldu", sinir=EN_COK_FORM)
        d = await _form_alanlari(db, kapsam, govde, None)
        f = EpFormlar(hesap_email=kapsam.hesap, genel_anahtar=secrets.token_urlsafe(12).replace("-", "x").replace("_", "y"),
                      dil=d.pop("dil", "tr"), ad_sor=d.pop("ad_sor", True), tur_sor=d.pop("tur_sor", False), aktif=d.pop("aktif", True),
                      created_at=ep.simdi(), **d)
        db.add(f)
        await db.commit()
        return _form_sozlugu(f)

    @router.put("/formlar/{fid}")
    async def form_guncelle(fid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        f = await _bul(db, EpFormlar, fid, kapsam.hesap)
        for k, v in (await _form_alanlari(db, kapsam, govde, f)).items():
            setattr(f, k, v)
        await db.commit()
        return _form_sozlugu(f)

    @router.delete("/formlar/{fid}")
    async def form_sil(fid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        f = await _bul(db, EpFormlar, fid, kapsam.hesap)
        await db.delete(f)
        await db.commit()
        return {"ok": True}

    # --- Segmentler ---
    @router.get("/segmentler")
    async def segmentler(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        kayitlar = (await db.execute(select(EpSegmentler).where(_hesap_kosulu(EpSegmentler, kapsam.hesap)).order_by(EpSegmentler.id))).scalars().all()
        hepsi = await eg.hesap_kisileri(db, kapsam.hesap) if kayitlar else []
        sonuc = []
        for s in kayitlar:
            sayi = len(await eg.segment_kisileri(db, kapsam.hesap, ep.json_yukle(s.kurallar, {}), hepsi))
            sonuc.append(_segment_sozlugu(s, sayi))
        return {"items": sonuc}

    @router.post("/segmentler/onizleme")
    async def segment_onizleme(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        try:
            kurallar = ep.segment_duzelt(govde.get("kurallar"), ajans=kapsam.hesap is None)
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        uyanlar = await eg.segment_kisileri(db, kapsam.hesap, kurallar)
        return {"sayi": len(uyanlar), "ornek": [{"id": k.id, "eposta": k.eposta, "ad": k.ad} for k in uyanlar[:10]]}

    @router.post("/segmentler")
    async def segment_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        sayi = int((await db.execute(select(func.count(EpSegmentler.id)).where(_hesap_kosulu(EpSegmentler, kapsam.hesap)))).scalar() or 0)
        if sayi >= EN_COK_SEGMENT:
            raise _hata(409, "sinir_doldu", sinir=EN_COK_SEGMENT)
        try:
            s = EpSegmentler(hesap_email=kapsam.hesap, ad=ep.metin(govde.get("ad"), "ad", 120, zorunlu=True),
                             kurallar=ep.json_yaz(ep.segment_duzelt(govde.get("kurallar"), ajans=kapsam.hesap is None)), created_at=ep.simdi())
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        db.add(s)
        await db.commit()
        return _segment_sozlugu(s, len(await eg.segment_kisileri(db, kapsam.hesap, ep.json_yukle(s.kurallar, {}))))

    @router.put("/segmentler/{sid}")
    async def segment_guncelle(sid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        s = await _bul(db, EpSegmentler, sid, kapsam.hesap)
        try:
            if "ad" in govde:
                s.ad = ep.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "kurallar" in govde:
                s.kurallar = ep.json_yaz(ep.segment_duzelt(govde.get("kurallar"), ajans=kapsam.hesap is None))
        except ep.PazarlamaHatasi as h:
            await db.rollback()
            raise _ph(h)
        await db.commit()
        return _segment_sozlugu(s, len(await eg.segment_kisileri(db, kapsam.hesap, ep.json_yukle(s.kurallar, {}))))

    @router.delete("/segmentler/{sid}")
    async def segment_sil(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        s = await _bul(db, EpSegmentler, sid, kapsam.hesap)
        await db.delete(s)
        await db.commit()
        return {"ok": True}

    # --- Görseller ve önizleme ---
    @router.post("/gorseller")
    async def gorsel_yukle(request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        from services import dosya_deposu

        kapsam = kapsam_al(request)
        _hiz(_gorsel_hizi, kapsam.anahtar)
        sayi = int((await db.execute(select(func.count(EpGorseller.id)).where(_hesap_kosulu(EpGorseller, kapsam.hesap)))).scalar() or 0)
        if sayi >= EN_COK_GORSEL:
            raise _hata(409, "sinir_doldu", sinir=EN_COK_GORSEL)
        hazir = _gorsel_hazirla(await dosya.read(GORSEL_EN_COK_BAYT + 1))
        anahtar = secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")
        try:
            depo = await dosya_deposu.yaz(db, f"eposta/{anahtar}.{hazir['uzanti']}", hazir["veri"], hazir["tur"])
        except Exception:  # noqa: BLE001
            logger.exception("E-posta görseli yazılamadı")
            raise _hata(503, "depo_hatasi")
        g = EpGorseller(hesap_email=kapsam.hesap, anahtar=anahtar, depo=depo, tur=hazir["tur"], genislik=hazir["genislik"],
                        yukseklik=hazir["yukseklik"], boyut=len(hazir["veri"]), created_at=ep.simdi())
        db.add(g)
        await db.commit()
        return {"url": ep.gorsel_adresi(anahtar), "genislik": g.genislik, "yukseklik": g.yukseklik, "boyut": g.boyut}

    async def _onizleme_uret(db: AsyncSession, kapsam: Kapsam, bloklar_ham: Any, konu: str, onizleme: str, dil: str,
                             gonderen_adi: Optional[str]) -> Dict[str, Any]:
        try:
            bloklar = ic.bloklari_dogrula(bloklar_ham, izinli_onek=ep.site_adresi())
            konu = ic.konu_duzelt(konu, zorunlu=False)
        except ic.IcerikHatasi as h:
            raise _ih(h)
        ayar = await eg.ayar_getir(db, kapsam.hesap)
        kimlik = await eg.kimlik_getir(db, kapsam.hesap, ayar)
        dil = ep.dil_sec(dil)
        ab = eg.alt_bilgi(dil, kimlik)
        gonderen = eg._gonderen_ad(gonderen_adi, kapsam.hesap) or kimlik.gonderen_adi
        html, baglantilar = ic.html_uret(bloklar, konu=konu, onizleme=onizleme, renk=ayar.marka_rengi or ic.VARSAYILAN_RENK,
                                         logo_url=ayar.logo_url, gonderen_adi=gonderen, dil=dil, alt_bilgi=ab)
        metin_ = ic.metin_uret(bloklar, gonderen_adi=gonderen, alt_bilgi=ab)
        neden = ep.ileti_metni(dil, "neden_izinli", gonderen=eg.gorunen_gonderen(kimlik, kapsam.hesap))

        def bag(i: int) -> str:
            return baglantilar[i] if 0 <= i < len(baglantilar) else "#"

        ornek = {"ad": "Ayşe", "firma": "Örnek Ltd.", "eposta": "ornek@ornek.com"}
        h = ic.kisisellestir(ic.isaretleri_doldur(html, html=True, baglanti=bag, ret="#", tercih="#", neden=neden), ornek, html=True)
        m = ic.kisisellestir(ic.isaretleri_doldur(metin_, html=False, baglanti=bag, ret="#", tercih="#", neden=neden), ornek, html=False)
        return {"html": h, "metin": m, "konu": ic.konu_kisisellestir(konu, ornek), "gonderen": eg.gonderen_alani(gonderen),
                "baglantilar": baglantilar, "kimlik_eksik": kimlik.eksik}

    @router.post("/onizleme")
    async def onizleme(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return await _onizleme_uret(db, kapsam, govde.get("bloklar"), str(govde.get("konu") or ""), str(govde.get("onizleme_metni") or ""),
                                    str(govde.get("dil") or "tr"), govde.get("gonderen_adi"))

    # --- Kampanyalar ---
    def _kampanya_alanlari(govde: Dict[str, Any], k: Optional[EpKampanyalar]) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        try:
            if "ad" in govde or k is None:
                d["ad"] = ep.metin(govde.get("ad"), "ad", 160, zorunlu=True)
            if "konu" in govde:
                d["konu"] = ic.konu_duzelt(govde.get("konu"), zorunlu=False) or None
            if "onizleme_metni" in govde:
                d["onizleme_metni"] = ep.metin(govde.get("onizleme_metni"), "onizleme_metni", 200) or None
            if "gonderen_adi" in govde:
                d["gonderen_adi"] = ep.metin(govde.get("gonderen_adi"), "gonderen_adi", 80) or None
            if "yanit_adresi" in govde:
                ham = str(govde.get("yanit_adresi") or "").strip()
                d["yanit_adresi"] = _eposta(ham, "yanit_adresi") if ham else None
            if "dil" in govde:
                d["dil"] = ep.dil_sec(govde.get("dil"))
            if "bloklar" in govde:
                d["bloklar"] = ep.json_yaz(ic.bloklari_dogrula(govde.get("bloklar"), izinli_onek=ep.site_adresi()))
            if "hedef" in govde:
                d["hedef"] = ep.json_yaz(eg.hedef_duzelt(govde.get("hedef")))
            if "ab" in govde:
                d["ab"] = ep.json_yaz(ep.ab_duzelt(govde.get("ab")))
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        except ic.IcerikHatasi as h:
            raise _ih(h)
        return d

    @router.get("/kampanyalar")
    async def kampanyalar(request: Request, durum: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(EpKampanyalar).where(_hesap_kosulu(EpKampanyalar, kapsam.hesap))
        if durum:
            sorgu = sorgu.where(EpKampanyalar.durum == durum)
        kayitlar = (await db.execute(sorgu.order_by(desc(EpKampanyalar.id)).limit(200))).scalars().all()
        sonuc = []
        for k in kayitlar:
            ist = await eg.kampanya_istatistik(db, k.id) if k.baslangic_at else None
            sonuc.append(_kampanya_sozlugu(k, istatistik=ist))
        return {"items": sonuc}

    @router.post("/kampanyalar")
    async def kampanya_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        d = _kampanya_alanlari(govde, None)
        k = EpKampanyalar(hesap_email=kapsam.hesap, durum="taslak", olusturan=kapsam.kisi, dil=d.pop("dil", "tr"),
                          created_at=ep.simdi(), **d)
        db.add(k)
        await db.commit()
        return _kampanya_sozlugu(k)

    @router.get("/kampanyalar/{kid}")
    async def kampanya_ayrinti(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        ist = await eg.kampanya_istatistik(db, k.id) if k.baslangic_at else None
        return _kampanya_sozlugu(k, istatistik=ist)

    @router.put("/kampanyalar/{kid}")
    async def kampanya_guncelle(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        if k.durum != "taslak":
            raise _hata(409, "duzenlenemez", kampanya_durumu=k.durum)
        for alan, deger in _kampanya_alanlari(govde, k).items():
            setattr(k, alan, deger)
        await db.commit()
        return _kampanya_sozlugu(k)

    @router.delete("/kampanyalar/{kid}")
    async def kampanya_sil(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        if k.baslangic_at is not None:
            raise _hata(409, "gonderilmis_kampanya")
        await db.delete(k)
        await db.commit()
        return {"ok": True}

    @router.post("/kampanyalar/{kid}/kopyala")
    async def kampanya_kopyala(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        yeni = EpKampanyalar(hesap_email=kapsam.hesap, ad=f"{k.ad} (2)"[:160], konu=k.konu, onizleme_metni=k.onizleme_metni,
                             gonderen_adi=k.gonderen_adi, yanit_adresi=k.yanit_adresi, dil=k.dil, bloklar=k.bloklar, hedef=k.hedef,
                             ab=k.ab, durum="taslak", olusturan=kapsam.kisi, created_at=ep.simdi())
        db.add(yeni)
        await db.commit()
        return _kampanya_sozlugu(yeni)

    @router.post("/kampanyalar/{kid}/onizleme")
    async def kampanya_onizleme(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        return await _onizleme_uret(db, kapsam, k.bloklar, k.konu or "", k.onizleme_metni or "", k.dil, k.gonderen_adi)

    @router.post("/kampanyalar/{kid}/kitle")
    async def kampanya_kitle(kid: int, request: Request, govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        try:
            hedef = eg.hedef_duzelt(govde.get("hedef") if "hedef" in govde else k.hedef)
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        # Panel önizlemesi: günlük kişi sınırı şu anki duruma göre (gönderimde yeniden değerlendirilir).
        ozet = await eg.kitle_ozeti(db, kapsam.hesap, hedef, siklik=True)
        sinir = await eg.aylik_sinir(db, kapsam.hesap)
        ozet["kota_kalan"] = None if sinir is None else max(0, sinir - await eg.aylik_kullanim(db, kapsam.anahtar))
        return ozet

    @router.post("/kampanyalar/{kid}/test")
    async def kampanya_test(kid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        adresler_ham = govde.get("adresler") or []
        if not isinstance(adresler_ham, list) or not (1 <= len(adresler_ham) <= 5):
            raise _hata(400, "adres_sayisi", alan="adresler", en_cok=5)
        adresler = [_eposta(a, "adresler") for a in adresler_ham]
        if not eg.resend_kurulu():
            raise _hata(409, "resend_kurulu_degil")
        _hiz(_test_hizi, kapsam.anahtar)
        try:
            bloklar = ic.bloklari_dogrula(k.bloklar, izinli_onek=ep.site_adresi())
            konu = ic.konu_duzelt(k.konu)
        except ic.IcerikHatasi as h:
            raise _ih(h)
        ornek = (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam.anahtar, EpKisiler.eposta.in_(adresler)).limit(1))).scalars().first()
        sonuc = await eg.test_gonder(db, hesap=kapsam.hesap, konu=konu, onizleme=k.onizleme_metni or "", bloklar=bloklar,
                                     gonderen_adi=k.gonderen_adi, dil=k.dil, adresler=adresler, ornek=ornek)
        return {"sonuc": sonuc}

    @router.post("/kampanyalar/{kid}/gonder")
    async def kampanya_gonder(kid: int, request: Request, govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        if k.durum != "taslak":
            raise _hata(409, "zaten_gonderildi", kampanya_durumu=k.durum)
        ozet = await _on_denetim(db, k)
        zaman = govde.get("zaman")
        if zaman:
            an = _an_coz(zaman, "zaman")
            if an <= ep.simdi() + timedelta(minutes=1) or an > ep.simdi() + timedelta(days=90):
                raise _hata(400, "zaman_gecersiz", alan="zaman")
            k.durum, k.zamanlanan_at, k.son_islem_at = "zamanlandi", an, ep.simdi()
            await db.commit()
            return {"kampanya": _kampanya_sozlugu(k), "kitle": ozet}
        try:
            await eg.kampanyayi_baslat(db, k)
        except ep.PazarlamaHatasi as h:
            await db.rollback()
            raise _ph(h)
        except ic.IcerikHatasi as h:
            await db.rollback()
            raise _ih(h)
        await db.commit()
        # İlk parça hemen (kısa bütçe); kalanını zamanlı görev gönderir.
        import time as _time

        await eg.kampanya_gonder(db, k, en_cok=eg.ISTEK_ICI_EN_COK, bitis=_time.monotonic() + 8.0)
        await db.refresh(k)
        return {"kampanya": _kampanya_sozlugu(k, istatistik=await eg.kampanya_istatistik(db, k.id)), "kitle": ozet}

    @router.post("/kampanyalar/{kid}/durdur")
    async def kampanya_durdur(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        if k.durum == "zamanlandi":
            k.durum, k.zamanlanan_at = "taslak", None
        elif k.durum in ("gonderiliyor", "ab_test"):
            k.durum, k.duraklatma_nedeni = "duraklatildi", "kullanici"
        else:
            raise _hata(409, "durdurulamaz", kampanya_durumu=k.durum)
        k.son_islem_at = ep.simdi()
        await db.commit()
        return _kampanya_sozlugu(k)

    @router.post("/kampanyalar/{kid}/devam")
    async def kampanya_devam(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        if k.durum != "duraklatildi":
            raise _hata(409, "devam_edilemez", kampanya_durumu=k.durum)
        if k.baslangic_at is None:
            k.durum, k.duraklatma_nedeni = "taslak", None
            await db.commit()
            return _kampanya_sozlugu(k)
        ayar = await eg.ayar_getir(db, kapsam.hesap)
        if ayar.askida:
            raise _hata(409, "hesap_askida", neden=ayar.askida_neden)
        ab = ep.json_yukle(k.ab, {})
        k.durum = "ab_test" if ab.get("acik") and not k.kazanan else "gonderiliyor"
        k.duraklatma_nedeni, k.son_islem_at = None, ep.simdi()
        await db.commit()
        return _kampanya_sozlugu(k)

    @router.get("/kampanyalar/{kid}/rapor")
    async def kampanya_rapor(kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        k = await _bul(db, EpKampanyalar, kid, kapsam.hesap)
        return await _rapor(db, k)

    # --- Damla dizileri ---
    async def _dizi_kaydet(db: AsyncSession, kapsam: Kapsam, d: EpDiziler, govde: Dict[str, Any], yeni: bool) -> List[EpDiziAdimlari]:
        try:
            if "ad" in govde or yeni:
                d.ad = ep.metin(govde.get("ad"), "ad", 120, zorunlu=True)
            if "tetik" in govde or yeni:
                tetik = govde.get("tetik") or "abonelik_onaylandi"
                if tetik not in ep.TETIKLER:
                    raise _hata(400, "secim_gecersiz", alan="tetik")
                d.tetik = tetik
            if "liste_id" in govde or yeni:
                lid = govde.get("liste_id")
                if not isinstance(lid, int) or not await _hesap_listeleri(db, kapsam.hesap, [lid]):
                    raise _hata(400, "liste_yok", alan="liste_id")
                d.liste_id = lid
            if "gonderen_adi" in govde:
                d.gonderen_adi = ep.metin(govde.get("gonderen_adi"), "gonderen_adi", 80) or None
            if "dil" in govde:
                d.dil = ep.dil_sec(govde.get("dil"))
            if "cikis" in govde:
                c = govde.get("cikis") if isinstance(govde.get("cikis"), dict) else {}
                hedef = c.get("hedef")
                temiz: Optional[Dict[str, Any]] = None
                if isinstance(hedef, dict):
                    if hedef.get("tur") == "tiklama":
                        temiz = {"tur": "tiklama"}
                    elif hedef.get("tur") == "etiket":
                        temiz = {"tur": "etiket", "deger": (ep.etiketleri_duzelt([hedef.get("deger")]) or [""])[0]}
                        if not temiz["deger"]:
                            raise _hata(400, "deger_gecersiz", alan="cikis")
                    elif hedef.get("tur") == "liste":
                        hl = hedef.get("liste_id")
                        if not isinstance(hl, int) or not await _hesap_listeleri(db, kapsam.hesap, [hl]):
                            raise _hata(400, "liste_yok", alan="cikis")
                        temiz = {"tur": "liste", "liste_id": hl}
                    elif hedef.get("tur") not in (None, "", "yok"):
                        raise _hata(400, "secim_gecersiz", alan="cikis")
                d.cikis = ep.json_yaz({"hedef": temiz})
            adimlar_ham = govde.get("adimlar")
            if adimlar_ham is not None:
                if not isinstance(adimlar_ham, list) or len(adimlar_ham) > EN_COK_ADIM:
                    raise _hata(400, "adim_sayisi", alan="adimlar", en_cok=EN_COK_ADIM)
                temiz_adimlar = []
                for i, a in enumerate(adimlar_ham):
                    if not isinstance(a, dict):
                        raise _hata(400, "adim_gecersiz", indeks=i)
                    try:
                        temiz_adimlar.append({
                            "id": a.get("id") if isinstance(a.get("id"), int) else None,
                            "bekle_gun": _tam(a.get("bekle_gun", 0), "bekle_gun", 0, 365),
                            "bekle_saat": _tam(a.get("bekle_saat", 0), "bekle_saat", 0, 23),
                            "konu": ic.konu_duzelt(a.get("konu")),
                            "onizleme_metni": ep.metin(a.get("onizleme_metni"), "onizleme_metni", 200) or None,
                            "bloklar": ep.json_yaz(ic.bloklari_dogrula(a.get("bloklar"), izinli_onek=ep.site_adresi())),
                        })
                    except ic.IcerikHatasi as h:
                        h.indeks = i
                        raise _ih(h)
            else:
                temiz_adimlar = None
        except ep.PazarlamaHatasi as h:
            raise _ph(h)
        await db.flush()
        mevcut = list((await db.execute(select(EpDiziAdimlari).where(EpDiziAdimlari.dizi_id == d.id))).scalars().all()) if not yeni else []
        if temiz_adimlar is not None:
            eski = {a.id: a for a in mevcut}
            kalan_idler = set()
            for sira, a in enumerate(temiz_adimlar):
                hedef_adim = eski.get(a.pop("id") or -1)
                if hedef_adim is None:
                    hedef_adim = EpDiziAdimlari(dizi_id=d.id, created_at=ep.simdi())
                    db.add(hedef_adim)
                for alan, deger in a.items():
                    setattr(hedef_adim, alan, deger)
                hedef_adim.sira = sira
                await db.flush()
                kalan_idler.add(hedef_adim.id)
            for a in mevcut:
                if a.id not in kalan_idler:
                    await db.delete(a)
            await db.flush()
        adimlar = await eg.dizi_adimlari(db, d.id)
        if "aktif" in govde:
            aktif = _bool(govde.get("aktif"), "aktif")
            if aktif:
                if not adimlar:
                    raise _hata(409, "adim_gerekli")
                kimlik = await eg.kimlik_getir(db, kapsam.hesap)
                if not kimlik.tamam:
                    raise _hata(409, "gonderen_kimligi_eksik", eksik=kimlik.eksik)
            d.aktif = aktif
        return adimlar

    async def _dizi_sayilari(db: AsyncSession, dizi_id: int) -> Dict[str, int]:
        return {d: int(n) for d, n in (await db.execute(
            select(EpDiziKayitlari.durum, func.count(EpDiziKayitlari.id)).where(EpDiziKayitlari.dizi_id == dizi_id)
            .group_by(EpDiziKayitlari.durum))).all()}

    @router.get("/diziler")
    async def diziler(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        kayitlar = (await db.execute(select(EpDiziler).where(_hesap_kosulu(EpDiziler, kapsam.hesap)).order_by(EpDiziler.id))).scalars().all()
        return {"items": [_dizi_sozlugu(d, await eg.dizi_adimlari(db, d.id), kayitlar=await _dizi_sayilari(db, d.id)) for d in kayitlar]}

    @router.post("/diziler")
    async def dizi_ekle(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        sayi = int((await db.execute(select(func.count(EpDiziler.id)).where(_hesap_kosulu(EpDiziler, kapsam.hesap)))).scalar() or 0)
        if sayi >= EN_COK_DIZI:
            raise _hata(409, "sinir_doldu", sinir=EN_COK_DIZI)
        d = EpDiziler(hesap_email=kapsam.hesap, ad="-", tetik="abonelik_onaylandi", aktif=False, dil=ep.dil_sec(govde.get("dil")),
                      cikis=ep.json_yaz({"hedef": None}), created_at=ep.simdi())
        db.add(d)
        try:
            adimlar = await _dizi_kaydet(db, kapsam, d, govde, yeni=True)
        except HTTPException:
            await db.rollback()
            raise
        await db.commit()
        return _dizi_sozlugu(d, adimlar, kayitlar={})

    @router.get("/diziler/{did}")
    async def dizi_ayrinti(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        d = await _bul(db, EpDiziler, did, kapsam.hesap)
        return _dizi_sozlugu(d, await eg.dizi_adimlari(db, d.id), kayitlar=await _dizi_sayilari(db, d.id))

    @router.put("/diziler/{did}")
    async def dizi_guncelle(did: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        d = await _bul(db, EpDiziler, did, kapsam.hesap)
        try:
            adimlar = await _dizi_kaydet(db, kapsam, d, govde, yeni=False)
        except HTTPException:
            await db.rollback()
            raise
        await db.commit()
        return _dizi_sozlugu(d, adimlar, kayitlar=await _dizi_sayilari(db, d.id))

    @router.delete("/diziler/{did}")
    async def dizi_sil(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        d = await _bul(db, EpDiziler, did, kapsam.hesap)
        await db.execute(update(EpDiziKayitlari).where(EpDiziKayitlari.dizi_id == d.id, EpDiziKayitlari.durum == "aktif")
                         .values(durum="cikti", cikis_nedeni="dizi_silindi", bitis_at=ep.simdi()).execution_options(synchronize_session=False))
        for a in await eg.dizi_adimlari(db, d.id):
            await db.delete(a)
        await db.delete(d)
        await db.commit()
        return {"ok": True}

    @router.get("/diziler/{did}/rapor")
    async def dizi_rapor(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        d = await _bul(db, EpDiziler, did, kapsam.hesap)
        adimlar = await eg.dizi_adimlari(db, d.id)
        adim_rapor = []
        for a in adimlar:
            s = (await db.execute(select(func.count(EpGonderimler.gonderim_at), func.count(EpGonderimler.acilma_at),
                                         func.count(EpGonderimler.tiklama_at),
                                         func.count(EpGonderimler.id))
                                  .where(EpGonderimler.adim_id == a.id))).one()
            adim_rapor.append({"id": a.id, "sira": a.sira, "konu": a.konu, "gonderilen": int(s[0]), "acilan": int(s[1]),
                               "tiklayan": int(s[2]), "satir": int(s[3])})
        cikis = {str(n or "-"): int(c) for n, c in (await db.execute(
            select(EpDiziKayitlari.cikis_nedeni, func.count(EpDiziKayitlari.id)).where(EpDiziKayitlari.dizi_id == d.id,
                                                                                       EpDiziKayitlari.durum == "cikti")
            .group_by(EpDiziKayitlari.cikis_nedeni))).all()}
        return {"dizi": _dizi_sozlugu(d, adimlar), "kayitlar": await _dizi_sayilari(db, d.id), "adimlar": adim_rapor, "cikis": cikis}


def _izin_isle(k: EpKisiler, izin: Any) -> None:
    """Panelden izin beyanı: yalnız "izinli" + kaynak + zaman (kanıt) ile yükseltme."""
    if izin in (None, "", {}):
        return
    if not isinstance(izin, dict):
        raise ep.PazarlamaHatasi("izin_gecersiz", "izin")
    durum = izin.get("durum")
    if durum == "izinsiz":
        if k.izin_durumu == "izinli":
            raise ep.PazarlamaHatasi("izin_geri_alma_ret_ile", "izin")
        return
    if durum != "izinli":
        raise ep.PazarlamaHatasi("izin_gecersiz", "izin")
    kaynak = ep.metin(izin.get("kaynak"), "izin_kaynagi", 160)
    if len(kaynak) < 3:
        raise ep.PazarlamaHatasi("izin_kaynagi_gerekli", "izin_kaynagi")
    try:
        zaman = ep.utc(datetime.fromisoformat(str(izin.get("zaman") or "").replace("Z", "+00:00")))
    except ValueError:
        raise ep.PazarlamaHatasi("izin_tarihi_gerekli", "izin_zamani")
    if zaman is None or zaman > ep.simdi():
        raise ep.PazarlamaHatasi("izin_tarihi_gerekli", "izin_zamani")
    k.izin_durumu = "izinli"
    k.izin_kaynagi = f"manuel:{kaynak}"[:200]
    k.izin_zamani = zaman
    k.izin_metin_surumu = ep.metin(izin.get("metin_surumu"), "metin_surumu", 40) or "manuel"
    k.izin_kaniti = ep.metin(izin.get("kanit"), "kanit", 500, cok_satir=True) or None


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Yalnız yönetici
# ---------------------------------------------------------------------------
@yonetici_router.post("/kisiler/crm-aktar")
async def crm_aktar(request: Request, govde: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
    """CRM adayları → ajansın kişileri. İzin CRM'deki pazarlama izninden (Faz 4G); yoksa izinsiz."""
    from models.crm import CrmAdaylari

    tur = govde.get("alici_turu") or "bireysel"
    if tur not in ep.ALICI_TURLERI:
        raise _hata(400, "secim_gecersiz", alan="alici_turu")
    yalniz_izinli = govde.get("yalniz_izinli") is not False
    liste_id = govde.get("liste_id")
    if liste_id is not None and (not isinstance(liste_id, int) or not await _hesap_listeleri(db, None, [liste_id])):
        raise _hata(404, "liste_yok")
    sorgu = select(CrmAdaylari).where(CrmAdaylari.email.isnot(None))
    if yalniz_izinli:
        sorgu = sorgu.where(CrmAdaylari.pazarlama_izni_at.isnot(None))
    adaylar = (await db.execute(sorgu.order_by(CrmAdaylari.id).limit(20000))).scalars().all()
    kapsam = ep.AJANS_KAPSAMI
    mevcut = {k.eposta: k for k in (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam))).scalars().all()}
    sayac = {"eklenen": 0, "guncellenen": 0, "izinli": 0, "listeye": 0}
    an = ep.simdi()
    for a in adaylar:
        eposta = ep.eposta_duzelt(a.email)
        if not ep.eposta_gecerli(eposta):
            continue
        k = mevcut.get(eposta)
        if k is None:
            k = EpKisiler(kapsam=kapsam, hesap_email=None, eposta=eposta, ad=a.ad, firma=a.firma, alici_turu=tur, izin_durumu="izinsiz",
                          kaynak="crm", kaynak_detay=a.kaynak, crm_aday_id=a.id, etiketler=a.etiketler or "[]", ozel_alanlar="{}",
                          dil="tr", created_at=an)
            db.add(k)
            mevcut[eposta] = k
            sayac["eklenen"] += 1
        else:
            k.crm_aday_id = k.crm_aday_id or a.id
            sayac["guncellenen"] += 1
        if a.pazarlama_izni_at is not None and k.izin_durumu not in ("izinli", "reddetti"):
            k.izin_durumu = "izinli"
            k.izin_kaynagi = f"crm:{a.id}"
            k.izin_zamani = ep.utc(a.pazarlama_izni_at)
            k.izin_metin_surumu = a.pazarlama_metin_surumu
            k.izin_kaniti = ep.json_yaz({"yontem": "crm_pazarlama_izni", "kaynak": a.pazarlama_izni_kaynak})
        if k.izin_durumu == "izinli":
            sayac["izinli"] += 1
    await db.flush()
    if liste_id is not None:
        for a in adaylar:
            k = mevcut.get(ep.eposta_duzelt(a.email))
            if k is not None and await _uyelik_ekle(db, k, liste_id, "crm"):
                sayac["listeye"] += 1
    await db.commit()
    return {"sayilar": sayac}


@yonetici_router.get("/hesaplar")
async def hesaplar(db: AsyncSession = Depends(get_db)):
    """Müşteri hesaplarının gönderim sağlığı (ajans alan adından gidiyor: itibar ortak)."""
    sinir30 = ep.simdi() - timedelta(days=30)
    kisiler = dict((await db.execute(select(EpKisiler.kapsam, func.count(EpKisiler.id)).group_by(EpKisiler.kapsam))).all())
    gonderim = {r[0]: r[1:] for r in (await db.execute(
        select(EpGonderimler.kapsam, func.count(EpGonderimler.gonderim_at), func.count(EpGonderimler.sikayet_at),
               func.count(EpGonderimler.geri_donme_at))
        .where(EpGonderimler.gonderim_at >= sinir30).group_by(EpGonderimler.kapsam))).all()}
    ayarlar = {a.kapsam: a for a in (await db.execute(select(EpAyarlar))).scalars().all()}
    kapsamlar = sorted(set(kisiler) | set(gonderim) | set(ayarlar))
    sonuc = []
    for k in kapsamlar:
        g = gonderim.get(k, (0, 0, 0))
        a = ayarlar.get(k)
        sonuc.append({"kapsam": k, "hesap": None if k == ep.AJANS_KAPSAMI else k, "kisi": int(kisiler.get(k, 0)),
                      "gonderilen_30": int(g[0] or 0), "sikayet_30": int(g[1] or 0), "geri_donen_30": int(g[2] or 0),
                      "askida": bool(a.askida) if a else False, "askida_neden": a.askida_neden if a else None,
                      "aylik_kullanim": await eg.aylik_kullanim(db, k)})
    return {"items": sonuc}


@yonetici_router.put("/hesaplar/{kapsam}")
async def hesap_askiya(kapsam: str, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    hesap = None if kapsam == ep.AJANS_KAPSAMI else ep.eposta_duzelt(kapsam)
    if hesap is not None and not ep.eposta_gecerli(hesap):
        raise _hata(400, "eposta_gecersiz")
    askida = _bool(govde.get("askida"), "askida")
    a = await eg.ayar_getir(db, hesap)
    a.askida = askida
    a.askida_neden = "elle" if askida else None
    a.askida_at = ep.simdi() if askida else None
    if askida:
        await db.execute(update(EpKampanyalar).where(_hesap_kosulu(EpKampanyalar, hesap), EpKampanyalar.durum.in_(("gonderiliyor", "ab_test", "zamanlandi")))
                         .values(durum="duraklatildi", duraklatma_nedeni="hesap_askida").execution_options(synchronize_session=False))
    await db.commit()
    return _ayar_sozlugu(a)


@yonetici_router.get("/sahte-kutu")
async def sahte_kutu(eposta: Optional[str] = Query(None)):
    """Yalnız ENVIRONMENT=test: sahte Resend'e düşen iletiler (uçtan uca test onay bağlantısını buradan alır)."""
    if not eg.sahte_mod():
        raise _hata(404, "bulunamadi")
    kutu = eg.sahte_kutu()
    if eposta:
        e = ep.eposta_duzelt(eposta)
        kutu = [i for i in kutu if e in [str(x).lower() for x in (i.get("to") or [])]]
    return {"items": kutu[-50:]}


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")
GOVDE_SINIRI = 10_000


def _ziyaretci(request: Request, ek: str) -> str:
    return ip_ozeti(f"bulten|{ek}|{istemci_ip(request)}")


async def _yayinda_form(db: AsyncSession, anahtar: str) -> EpFormlar:
    temiz = (anahtar or "").strip()
    if not temiz or len(temiz) > 40:
        raise _hata(404, "form_yok")
    f = (await db.execute(select(EpFormlar).where(EpFormlar.genel_anahtar == temiz))).scalars().first()
    if f is None or not f.aktif:
        raise _hata(404, "form_yok")
    if f.hesap_email and not await eg.modul_acik(db, f.hesap_email):
        raise _hata(410, "form_yok")
    return f


def _koken_denetle(request: Request, f: EpFormlar) -> None:
    from services.crm_form import koken_izinli_mi

    if not koken_izinli_mi(request.headers.get("origin"), f.izinli_alanlar):
        raise _hata(403, "alan_adi_izinsiz")


@acik_router.get("/form/{anahtar}")
async def form_tanimi(anahtar: str, request: Request, dil: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    f = await _yayinda_form(db, anahtar)
    _koken_denetle(request, f)
    d = ep.dil_sec(dil or f.dil)
    m = ep.FORM_METINLERI[d]
    kimlik = await eg.kimlik_getir(db, f.hesap_email)
    gorunen = eg.gorunen_gonderen(kimlik, f.hesap_email)
    from services.crm_form import VARSAYILAN_AYDINLATMA

    aydinlatma = f.aydinlatma_baglantisi or (
        (VARSAYILAN_AYDINLATMA if d == "tr" else VARSAYILAN_AYDINLATMA.replace("/gizlilik", f"/{d}/gizlilik")) if f.hesap_email is None else None
    )
    veri = {
        "anahtar": f.genel_anahtar, "baslik": f.baslik or None, "aciklama": f.aciklama or None, "dil": d, "yon": "rtl" if d == "ar" else "ltr",
        "alanlar": ([{"ad": "ad", "etiket": m["ad"], "zorunlu": False, "en_cok": 120}] if f.ad_sor else [])
        + [{"ad": "eposta", "etiket": m["eposta"], "zorunlu": True, "en_cok": 254}],
        "kurumsal": m["kurumsal"] if f.tur_sor else None,
        "izin": {"metin": ep.form_izin_metni(d, gorunen), "surum": ep.form_izin_surumu(d)},
        # Müşteri formunda aydınlatma metni müşterinin (veri sorumlusu) kendi bağlantısı; ajansta sitenin /gizlilik'i.
        "aydinlatma": {"metin": m["aydinlatma"], "baglanti": aydinlatma} if aydinlatma else None,
        "metinler": {"gonder": m["gonder"], "gonderiliyor": m["gonderiliyor"], "istege_bagli": m["istege_bagli"], "hata": m["hata"]},
        "tesekkur": f.tesekkur_metni or m["tesekkur"],
        "jeton": ep.form_jetonu(f.id),
        "bal_kupu": "web_adresi",
    }
    return JSONResponse(veri, headers=ACIK_BASLIKLAR)


async def _json_govde(request: Request) -> Dict[str, Any]:
    ham = await request.body()
    if len(ham) > GOVDE_SINIRI:
        raise _hata(413, "govde_buyuk")
    try:
        govde = json.loads(ham.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        raise _hata(400, "gecersiz_json")
    if not isinstance(govde, dict):
        raise _hata(400, "gecersiz_json")
    return govde


@acik_router.post("/form/{anahtar}")
async def form_gonder(anahtar: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Abonelik: kişi + bekleyen üyelik + onay e-postası (çift onay). Yanıt adresin varlığını ele vermez."""
    f = await _yayinda_form(db, anahtar)
    _koken_denetle(request, f)
    govde = await _json_govde(request)
    _hiz(_form_hizi, _ziyaretci(request, f"form|{f.id}"))
    _hiz(_form_genel_hizi, f"form|{f.id}")
    d = ep.dil_sec(govde.get("dil") or f.dil)
    tesekkur = {"tesekkur": f.tesekkur_metni or ep.FORM_METINLERI[d]["tesekkur"]}
    try:
        ep.form_jetonu_dogrula(govde.get("jeton"), f.id)
    except ep.PazarlamaHatasi as h:
        raise _hata(400, h.kod)
    if str(govde.get("web_adresi") or "").strip():
        return JSONResponse(tesekkur, headers=ACIK_BASLIKLAR)  # bal küpü: bot anlamasın
    eposta = ep.eposta_duzelt(govde.get("eposta"))
    if not eposta:
        raise _hata(400, "alan_gerekli", alan="eposta")
    if not ep.eposta_gecerli(eposta):
        raise _hata(400, "eposta_gecersiz", alan="eposta")
    if govde.get("izin") is not True:
        raise _hata(400, "izin_gerekli", alan="izin")
    ad = " ".join(str(govde.get("ad") or "").split())[:120] if f.ad_sor else ""
    kurumsal = bool(f.tur_sor) and govde.get("kurumsal") is True
    kapsam = ep.kapsam_anahtari(f.hesap_email)
    liste = (await db.execute(select(EpListeler).where(EpListeler.id == f.liste_id))).scalars().first()
    if liste is None:
        raise _hata(404, "form_yok")
    an = ep.simdi()
    kisi = (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam, EpKisiler.eposta == eposta))).scalars().first()
    if kisi is None:
        sinir = await eg.kisi_siniri(db, f.hesap_email)
        if sinir is not None and await _kisi_sayisi(db, kapsam) >= sinir:
            raise _hata(409, "genel")
        kisi = EpKisiler(kapsam=kapsam, hesap_email=f.hesap_email, eposta=eposta, ad=ad or None, alici_turu="kurumsal" if kurumsal else "bireysel",
                         izin_durumu="bekliyor", kaynak="form", kaynak_detay=f.ad[:120], etiketler="[]", ozel_alanlar="{}", dil=d, created_at=an)
        db.add(kisi)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            kisi = (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam, EpKisiler.eposta == eposta))).scalars().first()
            if kisi is None:
                raise _hata(409, "genel")
    # Sert geri dönen adrese onay e-postası bile gitmez (adres yok).
    if (await db.execute(select(EpBastirma.id).where(EpBastirma.kapsam == ep.GENEL_KAPSAM, EpBastirma.eposta == eposta))).first() is not None:
        await db.commit()
        return JSONResponse(tesekkur, headers=ACIK_BASLIKLAR)
    u = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.liste_id == liste.id, EpListeUyelikleri.kisi_id == kisi.id))).scalars().first()
    if u is not None and u.durum == "aktif" and kisi.izin_durumu == "izinli":
        await db.commit()
        return JSONResponse(tesekkur, headers=ACIK_BASLIKLAR)
    if u is None:
        u = EpListeUyelikleri(liste_id=liste.id, kisi_id=kisi.id, durum="bekliyor", created_at=an, onay_gonderim_sayisi=0)
        db.add(u)
    son = ep.utc(u.onay_gonderim_at)
    sayi = int(u.onay_gonderim_sayisi or 0) if son and son > an - timedelta(hours=24) else 0
    if sayi >= ep.ONAY_EPOSTA_SINIRI:
        await db.commit()
        return JSONResponse(tesekkur, headers=ACIK_BASLIKLAR)
    gorunen = eg.gorunen_gonderen(await eg.kimlik_getir(db, f.hesap_email), f.hesap_email)
    izin_metni = ep.form_izin_metni(d, gorunen)
    ham, ozet = ep.onay_jetonu_uret()
    if u.durum != "aktif":
        u.durum = "bekliyor"
    u.onay_ozeti, u.onay_bitis = ozet, an + ep.ONAY_SURESI
    u.onay_gonderim_at, u.onay_gonderim_sayisi = an, sayi + 1
    u.form_id, u.kaynak = f.id, f"form:{'kurumsal' if kurumsal else 'bireysel'}"
    u.izin_metin_surumu, u.izin_metin_ozeti = ep.form_izin_surumu(d), ep.metin_ozeti(izin_metni)
    if ad and not kisi.ad:
        kisi.ad = ad
    f.gonderim_sayisi = int(f.gonderim_sayisi or 0) + 1
    f.son_gonderim_at = an
    await db.commit()
    _, hata = await eg.onay_epostasi_gonder(db, kisi=kisi, liste=liste, ham_jeton=ham, dil=d)
    if hata:
        logger.warning("Bülten onay e-postası gönderilemedi: %s", hata)
    return JSONResponse(tesekkur, headers=ACIK_BASLIKLAR)


async def _onay_kaydi(db: AsyncSession, jeton: str) -> EpListeUyelikleri:
    if not jeton or len(jeton) > 80:
        raise _hata(404, "gecersiz")
    u = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.onay_ozeti == ep.onay_ozeti(jeton)))).scalars().first()
    if u is None:
        raise _hata(404, "gecersiz")
    return u


def _onay_durumu(u: EpListeUyelikleri) -> str:
    if u.onay_bitis is None:
        return "kullanildi"
    if ep.utc(u.onay_bitis) <= ep.simdi():  # type: ignore[operator]
        return "suresi_doldu"
    return "gecerli"


@acik_router.get("/onay/{jeton}")
async def onay_bilgisi(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    _hiz(_onay_hizi, _ziyaretci(request, "onay"))
    u = await _onay_kaydi(db, jeton)
    kisi = (await db.execute(select(EpKisiler).where(EpKisiler.id == u.kisi_id))).scalars().first()
    liste = (await db.execute(select(EpListeler).where(EpListeler.id == u.liste_id))).scalars().first()
    if kisi is None or liste is None:
        raise _hata(404, "gecersiz")
    kimlik = await eg.kimlik_getir(db, kisi.hesap_email)
    return JSONResponse({"durum": _onay_durumu(u), "eposta": ep.maskeli_eposta(kisi.eposta), "liste": liste.ad,
                         "gonderen": eg.gorunen_gonderen(kimlik, kisi.hesap_email), "dil": kisi.dil}, headers=ACIK_BASLIKLAR)


@acik_router.post("/onay/{jeton}")
async def onay_ver(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    _hiz(_onay_hizi, _ziyaretci(request, "onay"))
    u = await _onay_kaydi(db, jeton)
    durum = _onay_durumu(u)
    if durum == "kullanildi":
        raise _hata(409, "kullanildi")
    if durum == "suresi_doldu":
        raise _hata(410, "suresi_doldu")
    kisi = (await db.execute(select(EpKisiler).where(EpKisiler.id == u.kisi_id))).scalars().first()
    if kisi is None:
        raise _hata(404, "gecersiz")
    an = ep.simdi()
    f = (await db.execute(select(EpFormlar).where(EpFormlar.id == u.form_id))).scalars().first() if u.form_id else None
    u.durum, u.katilma_at, u.cikis_at, u.onay_bitis = "aktif", an, None, None
    kisi.izin_durumu = "izinli"
    kisi.izin_kaynagi = f"form:{f.genel_anahtar if f else u.form_id}"
    kisi.izin_zamani = an
    kisi.izin_metin_surumu = u.izin_metin_surumu
    kisi.izin_kaniti = ep.json_yaz({"yontem": "cift_onay", "form": f.ad if f else None, "metin_ozeti": u.izin_metin_ozeti,
                                    "abonelik": ep.iso(u.onay_gonderim_at), "onay": ep.iso(an)})
    kisi.onay_zamani = an
    kisi.ret_zamani, kisi.ret_kaynagi = None, None
    kisi.son_etkilesim_at = an
    if u.kaynak == "form:kurumsal":
        kisi.alici_turu = "kurumsal"
    # Yeniden abonelik: hesaptaki ret/şikâyet bastırması kalkar (sert geri dönüş ortak, kalır).
    await db.execute(delete(EpBastirma).where(EpBastirma.kapsam == kisi.kapsam, EpBastirma.eposta == kisi.eposta,
                                              EpBastirma.neden.in_(("ret", "sikayet"))))
    await eg.diziye_kaydet(db, kisi, u.liste_id, ("abonelik_onaylandi", "liste_katildi"))
    await db.commit()
    liste = (await db.execute(select(EpListeler).where(EpListeler.id == u.liste_id))).scalars().first()
    return JSONResponse({"durum": "onaylandi", "liste": liste.ad if liste else "", "tercih": ep.tercih_adresi(kisi.id)},
                        headers=ACIK_BASLIKLAR)


async def _tercih_kisisi(db: AsyncSession, jeton: str) -> EpKisiler:
    kimlik = ep.jeton_coz("ret", jeton)
    if kimlik is None:
        raise _hata(404, "gecersiz")
    k = (await db.execute(select(EpKisiler).where(EpKisiler.id == kimlik))).scalars().first()
    if k is None:
        raise _hata(404, "gecersiz")
    return k


async def _tercih_verisi(db: AsyncSession, k: EpKisiler) -> Dict[str, Any]:
    uyelikler = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.kisi_id == k.id,
                                                                  EpListeUyelikleri.durum.in_(("aktif", "cikti"))))).scalars().all()
    listeler = {l.id: l for l in (await db.execute(select(EpListeler).where(EpListeler.id.in_([u.liste_id for u in uyelikler])))).scalars().all()} if uyelikler else {}
    kimlik = await eg.kimlik_getir(db, k.hesap_email)
    return {"eposta": ep.maskeli_eposta(k.eposta), "gonderen": eg.gorunen_gonderen(kimlik, k.hesap_email),
            "abone": k.izin_durumu != "reddetti", "dil": k.dil,
            "listeler": [{"id": u.liste_id, "ad": listeler[u.liste_id].ad, "aktif": u.durum == "aktif"} for u in uyelikler if u.liste_id in listeler]}


@acik_router.get("/tercih/{jeton}")
async def tercih(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    _hiz(_tercih_hizi, _ziyaretci(request, "tercih"))
    k = await _tercih_kisisi(db, jeton)
    return JSONResponse(await _tercih_verisi(db, k), headers=ACIK_BASLIKLAR)


@acik_router.post("/tercih/{jeton}")
async def tercih_yaz(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    _hiz(_tercih_hizi, _ziyaretci(request, "tercih"))
    k = await _tercih_kisisi(db, jeton)
    govde = await _json_govde(request)
    if govde.get("islem") == "ret":
        await eg.ret_et(db, k, "baglanti")
    elif isinstance(govde.get("listeler"), dict):
        an = ep.simdi()
        for anahtar, deger in govde["listeler"].items():
            if not str(anahtar).isdigit() or not isinstance(deger, bool):
                continue
            u = (await db.execute(select(EpListeUyelikleri).where(EpListeUyelikleri.kisi_id == k.id,
                                                                  EpListeUyelikleri.liste_id == int(anahtar)))).scalars().first()
            if u is None or u.durum == "bekliyor":
                continue
            if not deger and u.durum == "aktif":
                u.durum, u.cikis_at = "cikti", an
            elif deger and u.durum == "cikti" and k.izin_durumu != "reddetti" and (k.izin_durumu == "izinli" or k.alici_turu == "kurumsal"):
                u.durum, u.katilma_at, u.cikis_at = "aktif", an, None
    else:
        raise _hata(400, "islem_gecersiz")
    await db.commit()
    return JSONResponse(await _tercih_verisi(db, k), headers=ACIK_BASLIKLAR)


@acik_router.post("/ret/{jeton}")
async def tek_tik_ret(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    """RFC 8058: posta sağlayıcısı `List-Unsubscribe=One-Click` gövdesiyle POST eder → anında ret."""
    _hiz(_tercih_hizi, _ziyaretci(request, "ret"))
    k = await _tercih_kisisi(db, jeton)
    await eg.ret_et(db, k, "tek_tik")
    await db.commit()
    return PlainTextResponse("ok", headers=ACIK_BASLIKLAR)


@acik_router.get("/ret/{jeton}")
async def tek_tik_sayfa(jeton: str):
    """GET durum değiştirmez (bağlantı tarayıcıları); tercih sayfasına (tek tıkla ret) yönlendirir."""
    if ep.jeton_coz("ret", jeton) is None:
        raise _hata(404, "gecersiz")
    return RedirectResponse(f"{ep.site_adresi()}/bulten/tercih/{jeton}?islem=ret", status_code=303, headers=ACIK_BASLIKLAR)


async def _izlenen(db: AsyncSession, jeton: str) -> Optional[EpGonderimler]:
    kimlik = ep.jeton_coz("izle", jeton)
    if kimlik is None:
        return None
    return (await db.execute(select(EpGonderimler).where(EpGonderimler.id == kimlik))).scalars().first()


@acik_router.get("/a/{jeton}.gif")
async def acilma(jeton: str, db: AsyncSession = Depends(get_db)):
    try:
        g = await _izlenen(db, jeton)
        if g is not None and g.acilma_at is None:
            kisi = (await db.execute(select(EpKisiler).where(EpKisiler.id == g.kisi_id))).scalars().first() if g.kisi_id else None
            eg.etkilesim_yaz(g, kisi, tiklama=False)
            await db.commit()
    except Exception:  # noqa: BLE001 - piksel asla hata vermesin
        logger.exception("Açılma kaydedilemedi")
    return Response(GIF, media_type="image/gif", headers={"Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff"})


@acik_router.get("/t/{jeton}/{indeks}")
async def tiklama(jeton: str, indeks: int, db: AsyncSession = Depends(get_db)):
    g = await _izlenen(db, jeton)
    hedef: Optional[str] = None
    if g is not None:
        if g.kampanya_id:
            k = (await db.execute(select(EpKampanyalar).where(EpKampanyalar.id == g.kampanya_id))).scalars().first()
            baglantilar = ep.json_yukle(k.baglantilar, []) if k else []
        else:
            adim = (await db.execute(select(EpDiziAdimlari).where(EpDiziAdimlari.id == g.adim_id))).scalars().first()
            dizi = (await db.execute(select(EpDiziler).where(EpDiziler.id == g.dizi_id))).scalars().first()
            baglantilar = (await eg.adim_icerigi(db, dizi, adim)).baglantilar if adim and dizi else []
        if 0 <= indeks < len(baglantilar):
            hedef = baglantilar[indeks]
            kisi = (await db.execute(select(EpKisiler).where(EpKisiler.id == g.kisi_id))).scalars().first() if g.kisi_id else None
            eg.etkilesim_yaz(g, kisi, tiklama=True)
            db.add(EpTiklamalar(kampanya_id=g.kampanya_id, gonderim_id=g.id, indeks=indeks, zaman=ep.simdi()))
            await db.commit()
    return RedirectResponse(hedef or ep.site_adresi(), status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@acik_router.get("/gorsel/{anahtar}")
async def gorsel(anahtar: str, db: AsyncSession = Depends(get_db)):
    from services import dosya_deposu

    if len(anahtar) > 64:
        raise _hata(404, "bulunamadi")
    g = (await db.execute(select(EpGorseller).where(EpGorseller.anahtar == anahtar))).scalars().first()
    if g is None:
        raise _hata(404, "bulunamadi")
    uzanti = "png" if g.tur == "image/png" else "jpg"
    try:
        veri = await dosya_deposu.oku(db, g.depo, f"eposta/{g.anahtar}.{uzanti}")
    except dosya_deposu.DepoHatasi:
        raise _hata(404, "bulunamadi")
    return Response(veri, media_type=g.tur, headers={
        "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    })


@acik_router.post("/resend-webhook")
async def resend_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    from services.eposta_gelen import svix_dogrula

    gizli = (os.environ.get(WEBHOOK_ANAHTARI) or "").strip()
    if not gizli:
        raise _hata(503, "kapali")
    ham = await request.body()
    if len(ham) > 512 * 1024:
        raise _hata(413, "govde_buyuk")
    svix_id = request.headers.get("svix-id")
    if not svix_dogrula(gizli, svix_id, request.headers.get("svix-timestamp"), request.headers.get("svix-signature"), ham):
        raise _hata(401, "imza_gecersiz")
    try:
        olay = json.loads(ham.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _hata(400, "gecersiz_json")
    if not isinstance(olay, dict):
        raise _hata(400, "gecersiz_json")
    if (await db.execute(select(EpWebhookOlaylari.id).where(EpWebhookOlaylari.svix_id == svix_id))).first() is not None:
        return {"durum": "tekrar"}
    try:
        sonuc = await eg.olay_isle(db, olay)
        veri = olay.get("data") if isinstance(olay.get("data"), dict) else {}
        db.add(EpWebhookOlaylari(svix_id=str(svix_id)[:120], tur=str(olay.get("type") or "")[:60],
                                 resend_id=str(veri.get("email_id") or "")[:80] or None, created_at=ep.simdi()))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"durum": "tekrar"}
    except Exception:  # noqa: BLE001 - Svix yeniden denesin
        await db.rollback()
        logger.exception("Resend pazarlama olayı işlenemedi")
        return JSONResponse(status_code=500, content={"durum": "hata", "yeniden_dene": True})
    return sonuc


# Yönetici ve müşteri router'ları önce.
router = (yonetici_router, musteri_router, acik_router)
