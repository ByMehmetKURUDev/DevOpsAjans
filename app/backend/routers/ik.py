"""Faz 6I — İnsan kaynakları: personel, izin, vardiya. Bordro / maaş / SGK / puantaj / konum YOK.

Müşteri (`/api/v1/ik`; modül `insan_kaynaklari` açık + hesap ekibi izni `ik`) — etkin hesabın personeli.
Yönetici (`/api/v1/ik-yonetim`, ajans): `?hesap=` YOKSA ajansın KENDİ personeli (tam yönetim); `?hesap=<e-posta>`
ile müşteri hesabının SALT OKUNUR destek görünümü (yazma 403 `salt_okunur`). `GET /hesaplar` destek listesi.

Ortak uçlar (iki panelde aynı gövdeler):
  GET  /meta · GET|PUT /ayarlar · GET /gun-hesapla?bas=&bit=&yarim=
  GET  /tatiller?yil= · POST /tatiller · DELETE /tatiller/{tid}
  GET|POST /personel · GET /personel.csv · POST /personel/ice-aktar
  GET|PUT|DELETE /personel/{pid}            (DELETE → çöp kutusu; izinleri, vardiyaları, dosyalarıyla birlikte)
  POST /personel/{pid}/baglanti             {"islem": "goster"|"yenile"|"iptal", "gonder": bool} — girişsiz portal
  POST /personel/{pid}/dosyalar (multipart `dosya`) · GET|DELETE /dosyalar/{did}
  GET|POST /izinler · GET /izinler/takvim?ay=YYYY-AA · GET /izinler.ics · GET /izinler.csv
  GET /izinler/{iid} · POST /izinler/{iid}/karar {"karar": "onay"|"ret", "not"} · POST /izinler/{iid}/iptal
  POST /izinler/{iid}/geri-al               (karar → beklemede)
  GET|POST /sablonlar · PUT|DELETE /sablonlar/{sid}
  GET /vardiyalar?hafta= · POST /vardiyalar · PUT|DELETE /vardiyalar/{vid}
  POST /vardiyalar/kopyala {"hafta", "uzerine_yaz"} · POST /vardiyalar/yayinla {"hafta", "bildir"}
  GET /vardiyalar.csv?hafta= · GET /vardiyalar.pdf?hafta=&dil=

Girişsiz personel portalı (`/api/v1/ik-portal/{jeton}`; imzalı, iptal/yenilenebilir, noindex):
  GET  /{jeton}                     kendi yayınlanmış vardiyaları, izin bakiyesi, izin geçmişi
  POST /{jeton}/izin                izin talebi (beklemede; rapor türünde açıklama alınmaz)
  POST /{jeton}/izin/{iid}/geri-cek bekleyen talebini geri çeker
  GET  /{jeton}/gun-hesapla         çalışma günü önizlemesi
  GET  /{jeton}/vardiyalar.ics      yayınlanmış vardiyaları takvime ekle

Uyarılar (izin çakışması, bakiye, yasal süre; vardiya: izinli kişi, çakışma, dinlenme, haftalık saat)
ENGELLEMEZ. Yasal varsayılanlar bilgilendirme amaçlıdır (`services/ik.py`).
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from models.ik import IkAyarlari, IkDosyalar, IkIzinler, IkPersonel, IkTatiller, IkVardiyalar, IkVardiyaSablonlari
from services import ik as s
from services import ik_kayit as k
from services.dosya_deposu import icerik_konumu
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = s.MODUL
IZIN = s.IZIN

acik_router = APIRouter(prefix="/api/v1/ik-portal", tags=["ik"])
yonetici_router = APIRouter(prefix="/api/v1/ik-yonetim", tags=["ik"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/ik",
    tags=["ik"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)

#: Panel (kişi başı): dakikada 120 yazma (vardiya ızgarası hızlı tıklanır), 20 dosya/CSV/PDF, saatte 30 e-posta.
_yazma_hizi = HizSiniri(120, 60.0)
_dosya_hizi = HizSiniri(20, 60.0)
_eposta_hizi = HizSiniri(30, 3600.0)
#: Portal (IP özeti): dakikada 120 okuma; personel başına dakikada 10 yazma.
_portal_hizi = KaliciHizSiniri("ik-portal", 120, 60.0)
_portal_yazma_hizi = HizSiniri(10, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _dosya_hizi, _eposta_hizi, _portal_hizi, _portal_yazma_hizi):
        h.temizle()


# ---------------------------------------------------------------------------
# Kapsam ve ortak yardımcılar
# ---------------------------------------------------------------------------
@dataclass
class Kapsam:
    yonetici: bool
    #: Kayıtların hesabı: müşteride etkin hesap; yöneticide None (ajansın kendi personeli) ya da `?hesap=`.
    hesap: Optional[str]
    kisi: str
    #: Yönetici başka hesaba bakıyor: yalnız okuma.
    salt_okunur: bool = False


def _musteri_kapsami(request: Request) -> Kapsam:
    b = izin_iste(request, IZIN)
    return Kapsam(False, b.hesap_email, b.kisi_email)


def _yonetici_kapsami(request: Request) -> Kapsam:
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


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar or "anonim"):
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


def _hk(model: Any, kapsam: Kapsam):
    return k.hesap_kosulu(model, kapsam.hesap)


def _csv_yaniti(metin: str, ad: str) -> Response:
    return Response(metin.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})


def _ics_yaniti(metin: str, ad: str, gizli: bool = False) -> Response:
    basliklar = {"Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff"}
    if gizli:
        basliklar.update({"X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})
    return Response(metin.encode("utf-8"), media_type="text/calendar; charset=utf-8", headers=basliklar)


def _tarih(ham: Optional[str], alan: str, varsayilan: Optional[date] = None) -> date:
    if not ham:
        if varsayilan is None:
            raise _hata(400, "zorunlu", alan=alan)
        return varsayilan
    try:
        return s.tarih_duzelt(ham, alan)
    except s.TemelHata as h:
        raise _e(h)


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def _ayar_sozlugu(a: Optional[IkAyarlari], kapsam_: str) -> Dict[str, Any]:
    kr = s.kurallar(a)
    return {
        "kapsam": kapsam_, "firma_adi": (a.firma_adi if a else "") or "",
        "calisma_gunleri": list(kr.calisma_gunleri),
        "kidem_kurallari": [{"yil": y, "gun": g} for y, g in kr.kidem],
        "yas_en_az_gun": kr.yas_en_az_gun, "yasal_gunler": dict(kr.yasal or s.VARSAYILAN_YASAL),
        "kapali_sabitler": list(kr.kapali_sabitler), "uyari_izinli": kr.uyari_izinli, "uyari_cakisma": kr.uyari_cakisma,
        "uyari_dinlenme": kr.uyari_dinlenme, "en_az_dinlenme_saat": kr.en_az_dinlenme_saat, "uyari_haftalik": kr.uyari_haftalik,
        "haftalik_en_cok_saat": kr.haftalik_en_cok_saat,
        "varsayilan": {"calisma_gunleri": list(s.VARSAYILAN_CALISMA_GUNLERI),
                       "kidem_kurallari": [{"yil": y, "gun": g} for y, g in s.VARSAYILAN_KIDEM],
                       "yas_en_az_gun": s.VARSAYILAN_YAS_GUN, "yasal_gunler": dict(s.VARSAYILAN_YASAL),
                       "en_az_dinlenme_saat": s.VARSAYILAN_DINLENME_SAAT, "haftalik_en_cok_saat": s.VARSAYILAN_HAFTALIK_SAAT},
    }


def _personel_sozlugu(p: IkPersonel, bakiye: Optional[Dict[str, Any]] = None, tam: bool = True) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": p.id, "hesap_email": p.hesap_email, "ad": p.ad, "gorev": p.gorev or "", "departman": p.departman or "",
        "durum": p.durum, "ise_giris": s.gun_iso(p.ise_giris), "ayrilis_tarihi": s.gun_iso(p.ayrilis_tarihi),
    }
    if tam:
        d.update({"eposta": p.eposta or "", "telefon": p.telefon or "", "yas_grubu": p.yas_grubu or "genel",
                  "devir_gun": float(p.devir_gun or 0), "devir_tarihi": s.gun_iso(p.devir_tarihi),
                  "yillik_gun_ozel": p.yillik_gun_ozel, "notlar": p.notlar or "", "dil": p.dil or "tr",
                  "portal_acik": bool(p.portal_acik), "portal_son_at": s.iso(p.portal_son_at),
                  "created_at": s.iso(p.created_at), "updated_at": s.iso(p.updated_at)})
    if bakiye is not None:
        d["bakiye"] = bakiye
    return d


def _izin_sozlugu(i: IkIzinler, ad: Optional[str] = None, **ek: Any) -> Dict[str, Any]:
    return {
        "id": i.id, "personel_id": i.personel_id, "personel_ad": ad, "tur": i.tur, "baslangic": i.baslangic.isoformat(),
        "bitis": i.bitis.isoformat(), "yarim_gun": bool(i.yarim_gun), "gun": float(i.gun or 0),
        "takvim_gunu": s.takvim_gunu(i.baslangic, i.bitis), "durum": i.durum,
        "aciklama": (i.aciklama or "") if i.tur != "rapor" else "", "karar_notu": i.karar_notu or "",
        "karar_veren": i.karar_veren, "karar_at": s.iso(i.karar_at), "kaynak": i.kaynak, "talep_eden": i.talep_eden,
        "iptal_eden": i.iptal_eden, "iptal_at": s.iso(i.iptal_at), "created_at": s.iso(i.created_at), **ek,
    }


def _sablon_sozlugu(x: IkVardiyaSablonlari) -> Dict[str, Any]:
    b, e = s.vardiya_anlari(date(2026, 1, 5), x.baslangic, x.bitis)
    return {"id": x.id, "ad": x.ad, "baslangic": x.baslangic, "bitis": x.bitis, "mola_dk": int(x.mola_dk or 0),
            "renk": x.renk, "aktif": bool(x.aktif), "sira": int(x.sira or 0), "gece": e.date() > b.date(),
            "net_dk": s.net_dakika(b, e, x.mola_dk)}


def _vardiya_sozlugu(v: IkVardiyalar) -> Dict[str, Any]:
    return {"id": v.id, "personel_id": v.personel_id, "tarih": v.tarih.isoformat(), "bas": s.yerel_iso(v.bas),
            "bit": s.yerel_iso(v.bit), "baslangic": s.saat_metni(v.bas), "bitis": s.saat_metni(v.bit),
            "mola_dk": int(v.mola_dk or 0), "net_dk": s.net_dakika(v.bas, v.bit, v.mola_dk), "sablon_id": v.sablon_id,
            "durum": v.durum, "degisti": bool(v.degisti), "notlar": v.notlar or "", "yayin_at": s.iso(v.yayin_at)}


def _dosya_sozlugu(d: IkDosyalar) -> Dict[str, Any]:
    return {"id": d.id, "personel_id": d.personel_id, "ad": d.ad, "tur": d.tur, "boyut": int(d.boyut or 0),
            "created_at": s.iso(d.created_at)}


# ---------------------------------------------------------------------------
# Kayıt bulucular
# ---------------------------------------------------------------------------
async def _personel(db: AsyncSession, kapsam: Kapsam, pid: int) -> IkPersonel:
    p = (await db.execute(select(IkPersonel).where(IkPersonel.id == pid, _hk(IkPersonel, kapsam)))).scalars().first()
    if p is None:
        raise _hata(404, "bulunamadi")
    return p


async def _izin(db: AsyncSession, kapsam: Kapsam, iid: int) -> IkIzinler:
    i = (await db.execute(select(IkIzinler).where(IkIzinler.id == iid, _hk(IkIzinler, kapsam)))).scalars().first()
    if i is None:
        raise _hata(404, "bulunamadi")
    return i


async def _sablon(db: AsyncSession, kapsam: Kapsam, sid: int) -> IkVardiyaSablonlari:
    x = (await db.execute(select(IkVardiyaSablonlari).where(IkVardiyaSablonlari.id == sid,
                                                            _hk(IkVardiyaSablonlari, kapsam)))).scalars().first()
    if x is None:
        raise _hata(404, "bulunamadi")
    return x


async def _vardiya(db: AsyncSession, kapsam: Kapsam, vid: int) -> IkVardiyalar:
    v = (await db.execute(select(IkVardiyalar).where(IkVardiyalar.id == vid, _hk(IkVardiyalar, kapsam)))).scalars().first()
    if v is None:
        raise _hata(404, "bulunamadi")
    return v


async def _personel_adlari(db: AsyncSession, idler: List[int]) -> Dict[int, str]:
    if not idler:
        return {}
    return dict((await db.execute(select(IkPersonel.id, IkPersonel.ad).where(IkPersonel.id.in_(sorted(set(idler)))))).all())


# ---------------------------------------------------------------------------
# Personel: uygula / sınır
# ---------------------------------------------------------------------------
def _personel_uygula(p: IkPersonel, g: Dict[str, Any], yeni: bool) -> None:
    if "ad" in g or yeni:
        p.ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
    if "eposta" in g:
        p.eposta = s.eposta_duzelt(g.get("eposta"), "eposta") or None
    if "telefon" in g:
        p.telefon = s.telefon_duzelt(g.get("telefon"), "telefon")
    for alan in ("gorev", "departman"):
        if alan in g:
            setattr(p, alan, s.metin(g.get(alan), alan, 120) or None)
    if "notlar" in g:
        p.notlar = s.metin(g.get("notlar"), "notlar", 4000, cok_satir=True) or None
    if "ise_giris" in g or yeni:
        p.ise_giris = s.tarih_duzelt(g.get("ise_giris"), "ise_giris")
    if "durum" in g:
        p.durum = s.secim(g.get("durum"), s.PERSONEL_DURUMLARI, "durum")
    if "ayrilis_tarihi" in g:
        p.ayrilis_tarihi = s.tarih_duzelt(g.get("ayrilis_tarihi"), "ayrilis_tarihi", bos_olabilir=True)
    if "yas_grubu" in g:
        p.yas_grubu = s.secim(g.get("yas_grubu") or "genel", s.YAS_GRUPLARI, "yas_grubu")
    if "devir_gun" in g:
        p.devir_gun = s.yarim_sayi(g.get("devir_gun"), "devir_gun", -100, 400)
    if "devir_tarihi" in g:
        p.devir_tarihi = s.tarih_duzelt(g.get("devir_tarihi"), "devir_tarihi", bos_olabilir=True)
    if "yillik_gun_ozel" in g:
        p.yillik_gun_ozel = s.tam_sayi(g.get("yillik_gun_ozel"), "yillik_gun_ozel", 1, 60, bos_olabilir=True)
    if "dil" in g:
        p.dil = s.dil_duzelt(g.get("dil"))
    if p.durum == "ayrildi" and not p.ayrilis_tarihi:
        p.ayrilis_tarihi = s.bugun()
    if p.durum == "aktif":
        p.ayrilis_tarihi = None
    if p.ayrilis_tarihi and p.ise_giris and p.ayrilis_tarihi < p.ise_giris:
        raise s.IkHatasi("ayrilis_once", "ayrilis_tarihi")
    if p.devir_tarihi and p.ise_giris and p.devir_tarihi < p.ise_giris:
        raise s.IkHatasi("devir_once", "devir_tarihi")


async def _sinir_denetle(db: AsyncSession, hesap: Optional[str], ek: int = 1) -> None:
    sinir = await k.modul_ayari(db, hesap, "personel_siniri", s.VARSAYILAN_PERSONEL_SINIRI)
    if sinir is not None and await k.aktif_personel_sayisi(db, hesap) + ek > int(sinir):
        raise s.IkHatasi("personel_siniri", durum=409, sinir=int(sinir))


# ---------------------------------------------------------------------------
# İzin: oluştur / kararlar (panel ve portal ortak)
# ---------------------------------------------------------------------------
@dataclass
class IzinGirdisi:
    tur: str
    baslangic: date
    bitis: date
    yarim_gun: bool
    aciklama: Optional[str]


def _izin_girdisi(g: Dict[str, Any], portal: bool = False) -> IzinGirdisi:
    tur = s.secim(g.get("tur"), s.IZIN_TURLERI, "tur")
    bas = s.tarih_duzelt(g.get("baslangic"), "baslangic")
    bit = s.tarih_duzelt(g.get("bitis") or g.get("baslangic"), "bitis")
    if bit < bas:
        raise s.IkHatasi("bitis_once", "bitis")
    if s.takvim_gunu(bas, bit) > s.EN_COK_IZIN_GUN:
        raise s.IkHatasi("aralik_cok_uzun", "bitis", en_cok=s.EN_COK_IZIN_GUN)
    yarim = g.get("yarim_gun") is True
    if yarim and bas != bit:
        raise s.IkHatasi("yarim_tek_gun", "yarim_gun")
    # Rapor: YALNIZ tarih aralığı — teşhis/açıklama alanı alınmaz (özel nitelikli sağlık verisi).
    aciklama = None if tur == "rapor" else (s.metin(g.get("aciklama"), "aciklama", 500, cok_satir=True) or None)
    if portal and bas < s.bugun() - timedelta(days=60):
        raise s.IkHatasi("cok_eski", "baslangic", en_cok=60)
    return IzinGirdisi(tur, bas, bit, yarim, aciklama)


async def _izin_olustur(db: AsyncSession, p: IkPersonel, girdi: IzinGirdisi, *, kaynak: str, talep_eden: Optional[str],
                        onayli: bool = False, karar_notu: Optional[str] = None, istek_kimligi: Optional[str] = None):
    kr = await k.kurallar_al(db, p.hesap_email)
    gun = await k.gun_hesapla(db, p.hesap_email, girdi.baslangic, girdi.bitis, girdi.yarim_gun, kr)
    uyarilar = await k.izin_uyarilari(db, p, girdi.tur, girdi.baslangic, girdi.bitis, gun, kr)
    an = s.simdi()
    i = IkIzinler(hesap_email=p.hesap_email, personel_id=p.id, tur=girdi.tur, baslangic=girdi.baslangic, bitis=girdi.bitis,
                  yarim_gun=girdi.yarim_gun, gun=gun, durum="onaylandi" if onayli else "beklemede", aciklama=girdi.aciklama,
                  kaynak=kaynak, talep_eden=talep_eden, istek_kimligi=istek_kimligi, created_at=an, updated_at=an)
    if onayli:
        i.karar_veren, i.karar_at, i.karar_notu = talep_eden, an, karar_notu
    db.add(i)
    await db.commit()
    await db.refresh(i)
    return i, uyarilar


# ---------------------------------------------------------------------------
# Vardiya yardımcıları
# ---------------------------------------------------------------------------
def _hafta(ham: Optional[str]) -> date:
    g = _tarih(ham, "hafta", s.bugun())
    return s.hafta_basi(g)


async def _hafta_vardiyalari(db: AsyncSession, kapsam: Kapsam, hafta_bas: date, onceki_gun: bool = False) -> List[IkVardiyalar]:
    bas = hafta_bas - timedelta(days=1 if onceki_gun else 0)
    return list((await db.execute(select(IkVardiyalar).where(
        _hk(IkVardiyalar, kapsam), IkVardiyalar.tarih >= bas, IkVardiyalar.tarih < hafta_bas + timedelta(days=7))
        .order_by(IkVardiyalar.bas, IkVardiyalar.id))).scalars().all())


async def _hafta_uyarilari(db: AsyncSession, kapsam: Kapsam, hafta_bas: date, kr: Optional[s.Kurallar] = None) -> List[Dict[str, Any]]:
    kr = kr or await k.kurallar_al(db, kapsam.hesap)
    liste = await _hafta_vardiyalari(db, kapsam, hafta_bas, onceki_gun=True)
    izinli = await k.izinli_gunler(db, kapsam.hesap, hafta_bas - timedelta(days=1), hafta_bas + timedelta(days=7))
    return s.vardiya_uyarilari([s.VardiyaOzeti(v.id, v.personel_id, v.bas, v.bit, int(v.mola_dk or 0)) for v in liste],
                               izinli, kr, hafta_bas)


async def _vardiya_uygula(db: AsyncSession, kapsam: Kapsam, v: IkVardiyalar, g: Dict[str, Any], yeni: bool) -> None:
    if "personel_id" in g or yeni:
        pid = s.tam_sayi(g.get("personel_id"), "personel_id", 1, 10**12)
        p = await _personel(db, kapsam, int(pid))
        if p.durum != "aktif":
            raise s.IkHatasi("personel_ayrildi", "personel_id", durum=409)
        v.personel_id = p.id
    tarih = s.tarih_duzelt(g.get("tarih"), "tarih") if ("tarih" in g or yeni) else v.tarih
    sablon = None
    if g.get("sablon_id"):
        sablon = await _sablon(db, kapsam, int(s.tam_sayi(g.get("sablon_id"), "sablon_id", 1, 10**12)))
    if sablon is not None and "baslangic" not in g:
        bas_s, bit_s, mola = sablon.baslangic, sablon.bitis, int(sablon.mola_dk or 0)
        v.sablon_id = sablon.id
    else:
        bas_s = s.saat_duzelt(g.get("baslangic"), "baslangic") if ("baslangic" in g or yeni) else s.saat_metni(v.bas)
        bit_s = s.saat_duzelt(g.get("bitis"), "bitis") if ("bitis" in g or yeni) else s.saat_metni(v.bit)
        mola = int(s.tam_sayi(g.get("mola_dk"), "mola_dk", 0, 600)) if "mola_dk" in g else (int(v.mola_dk or 0) if not yeni else 0)
        if "sablon_id" in g:
            v.sablon_id = sablon.id if sablon is not None else None
    if bas_s == bit_s:
        raise s.IkHatasi("sure_gecersiz", "bitis")
    v.tarih = tarih
    v.bas, v.bit = s.vardiya_anlari(tarih, bas_s, bit_s)
    v.mola_dk = mola
    if s.net_dakika(v.bas, v.bit, mola) <= 0:
        raise s.IkHatasi("mola_uzun", "mola_dk")
    if "notlar" in g:
        v.notlar = s.metin(g.get("notlar"), "notlar", 200) or None


# ---------------------------------------------------------------------------
# Uçlar (yönetici ve müşteri için aynı gövdeler)
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:  # noqa: C901
    # ------------------------------------------------------------- meta / ayarlar
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sinir = await k.modul_ayari(db, kapsam.hesap, "personel_siniri", s.VARSAYILAN_PERSONEL_SINIRI) if kapsam.hesap else None
        bekleyen = int((await db.execute(select(func.count(IkIzinler.id)).where(
            _hk(IkIzinler, kapsam), IkIzinler.durum == "beklemede"))).scalar() or 0)
        departmanlar = sorted({d for (d,) in (await db.execute(select(IkPersonel.departman).where(
            _hk(IkPersonel, kapsam), IkPersonel.departman.isnot(None)).distinct())).all() if d})
        return {
            "yonetici": kapsam.yonetici, "hesap": kapsam.hesap, "ajans": kapsam.hesap is None, "salt_okunur": kapsam.salt_okunur,
            "kisi": kapsam.kisi, "personel_siniri": sinir, "aktif_personel": await k.aktif_personel_sayisi(db, kapsam.hesap),
            "bekleyen_izin": bekleyen, "departmanlar": departmanlar, "izin_turleri": list(s.IZIN_TURLERI),
            "yasal_turler": list(s.YASAL_TURLER), "izin_durumlari": list(s.IZIN_DURUMLARI), "yas_gruplari": list(s.YAS_GRUPLARI),
            "personel_durumlari": list(s.PERSONEL_DURUMLARI), "bugun": s.bugun().isoformat(), "en_cok_csv": s.EN_COK_CSV,
            "ayarlar": _ayar_sozlugu(await k.ayar_satiri(db, kapsam.hesap), s.kapsam_anahtari(kapsam.hesap)),
            "portal_tabani": f"{s.site_adresi()}/personel/",
        }

    @router.get("/ayarlar")
    async def ayarlar(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        return _ayar_sozlugu(await k.ayar_satiri(db, kapsam.hesap), s.kapsam_anahtari(kapsam.hesap))

    @router.put("/ayarlar")
    async def ayarlar_yaz(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        a = await k.ayar_satiri(db, kapsam.hesap)
        if a is None:
            a = IkAyarlari(kapsam=s.kapsam_anahtari(kapsam.hesap), hesap_email=kapsam.hesap, created_at=s.simdi(),
                           uyari_izinli=True, uyari_cakisma=True, uyari_dinlenme=True, uyari_haftalik=True,
                           en_az_dinlenme_saat=s.VARSAYILAN_DINLENME_SAAT, haftalik_en_cok_saat=s.VARSAYILAN_HAFTALIK_SAAT)
            db.add(a)
        try:
            if "firma_adi" in g:
                a.firma_adi = s.metin(g.get("firma_adi"), "firma_adi", 160) or None
            if "calisma_gunleri" in g:
                a.calisma_gunleri = s.json_yaz(s.calisma_gunleri_duzelt(g.get("calisma_gunleri")))
            if "kidem_kurallari" in g:
                a.kidem_kurallari = s.json_yaz(s.kidem_kurallari_duzelt(g.get("kidem_kurallari")))
            if "yas_en_az_gun" in g:
                a.yas_en_az_gun = s.tam_sayi(g.get("yas_en_az_gun"), "yas_en_az_gun", 0, 60)
            if "yasal_gunler" in g:
                a.yasal_gunler = s.json_yaz(s.yasal_gunler_duzelt(g.get("yasal_gunler")))
            if "kapali_sabitler" in g:
                ham = g.get("kapali_sabitler")
                gecerli = {s.sabit_anahtari(ay, gun) for ay, gun, _, _ in s.SABIT_TATILLER}
                if not isinstance(ham, list) or any(x not in gecerli for x in ham):
                    raise s.IkHatasi("secim_gecersiz", "kapali_sabitler")
                a.kapali_sabitler = s.json_yaz(sorted(set(ham)))
            for alan in ("uyari_izinli", "uyari_cakisma", "uyari_dinlenme", "uyari_haftalik"):
                if alan in g:
                    setattr(a, alan, s.bool_duzelt(g.get(alan), alan))
            if "en_az_dinlenme_saat" in g:
                a.en_az_dinlenme_saat = s.tam_sayi(g.get("en_az_dinlenme_saat"), "en_az_dinlenme_saat", 1, 24)
            if "haftalik_en_cok_saat" in g:
                a.haftalik_en_cok_saat = s.tam_sayi(g.get("haftalik_en_cok_saat"), "haftalik_en_cok_saat", 1, 80)
            if g.get("varsayilana_don") is True:
                a.calisma_gunleri = a.kidem_kurallari = a.yasal_gunler = None
                a.yas_en_az_gun = None
                a.en_az_dinlenme_saat, a.haftalik_en_cok_saat = s.VARSAYILAN_DINLENME_SAAT, s.VARSAYILAN_HAFTALIK_SAAT
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)
        a.updated_at = s.simdi()
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "eszamanli")
        await db.refresh(a)
        return _ayar_sozlugu(a, a.kapsam)

    @router.get("/gun-hesapla")
    async def gun_hesapla(request: Request, bas: str = Query(...), bit: Optional[str] = Query(None), yarim: bool = Query(False),
                          db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        b = _tarih(bas, "bas")
        e = _tarih(bit, "bit", b)
        if e < b or s.takvim_gunu(b, e) > s.EN_COK_IZIN_GUN:
            raise _hata(400, "aralik_gecersiz", alan="bit")
        return {"gun": await k.gun_hesapla(db, kapsam.hesap, b, e, yarim and b == e), "takvim_gunu": s.takvim_gunu(b, e)}

    # ------------------------------------------------------------- tatiller
    @router.get("/tatiller")
    async def tatiller(request: Request, yil: Optional[int] = Query(None, ge=2000, le=2100), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        y = yil or s.bugun().year
        kr = await k.kurallar_al(db, kapsam.hesap)
        ek = await k.eklenen_tatiller(db, kapsam.hesap, date(y, 1, 1), date(y, 12, 31))
        return {"yil": y, "sabit": s.sabit_tatiller(y, kr.kapali_sabitler),
                "eklenen": [{"id": t.id, "tarih": t.tarih.isoformat(), "ad": t.ad, "yarim": bool(t.yarim)} for t in ek]}

    @router.post("/tatiller")
    async def tatil_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        """Tek gün ya da aralık (en çok 10 gün; dini bayram + arife). Var olan gün güncellenir."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        try:
            bas = s.tarih_duzelt(g.get("tarih"), "tarih")
            bit = s.tarih_duzelt(g.get("bitis"), "bitis") if g.get("bitis") else bas
            if bit < bas:
                raise s.IkHatasi("bitis_once", "bitis")
            if s.takvim_gunu(bas, bit) > s.EN_COK_TATIL_ARALIGI:
                raise s.IkHatasi("aralik_cok_uzun", "bitis", en_cok=s.EN_COK_TATIL_ARALIGI)
            ad = s.metin(g.get("ad"), "ad", 120, zorunlu=True)
            yarim = g.get("yarim") is True
        except s.TemelHata as h:
            raise _e(h)
        kapsam_k = s.kapsam_anahtari(kapsam.hesap)
        var = {t.tarih: t for t in await k.eklenen_tatiller(db, kapsam.hesap, bas, bit)}
        eklenen = []
        for gun in s.gunler(bas, bit):
            # Aralıkta yarım gün işareti yalnız ilk güne (arife) uygulanır.
            y = yarim and gun == bas
            t = var.get(gun)
            if t is None:
                t = IkTatiller(kapsam=kapsam_k, hesap_email=kapsam.hesap, tarih=gun, ad=ad, yarim=y, created_at=s.simdi())
                db.add(t)
            else:
                t.ad, t.yarim = ad, y
            eklenen.append(t)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise _hata(409, "eszamanli")
        return {"eklenen": [{"id": t.id, "tarih": t.tarih.isoformat(), "ad": t.ad, "yarim": bool(t.yarim)} for t in eklenen]}

    @router.delete("/tatiller/{tid}")
    async def tatil_sil(tid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        t = (await db.execute(select(IkTatiller).where(IkTatiller.id == tid, IkTatiller.kapsam == s.kapsam_anahtari(kapsam.hesap))
                              )).scalars().first()
        if t is None:
            raise _hata(404, "bulunamadi")
        await db.delete(t)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- personel
    @router.get("/personel")
    async def personel_listesi(request: Request, durum: str = Query("aktif"), ara: Optional[str] = Query(None, max_length=120),
                               departman: Optional[str] = Query(None, max_length=120), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(IkPersonel).where(_hk(IkPersonel, kapsam))
        if durum in s.PERSONEL_DURUMLARI:
            sorgu = sorgu.where(IkPersonel.durum == durum)
        if departman:
            sorgu = sorgu.where(IkPersonel.departman == departman)
        if ara and ara.strip():
            desen = f"%{ara.strip().lower().replace('%', '').replace('_', '')}%"
            sorgu = sorgu.where(or_(*[func.lower(func.coalesce(c, "")).like(desen) for c in
                                      (IkPersonel.ad, IkPersonel.eposta, IkPersonel.gorev, IkPersonel.departman)]))
        liste = (await db.execute(sorgu.order_by(IkPersonel.ad, IkPersonel.id).limit(2000))).scalars().all()
        kr = await k.kurallar_al(db, kapsam.hesap)
        bakiyeler = await k.bakiyeler(db, liste, kr)
        bekleyen: Dict[int, int] = dict((await db.execute(select(IkIzinler.personel_id, func.count(IkIzinler.id)).where(
            _hk(IkIzinler, kapsam), IkIzinler.durum == "beklemede").group_by(IkIzinler.personel_id))).all())
        return {"items": [_personel_sozlugu(p, {**bakiyeler[p.id], "hakedisler": []}) | {"bekleyen_izin": int(bekleyen.get(p.id, 0))}
                          for p in liste], "toplam": len(liste)}

    @router.post("/personel")
    async def personel_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        an = s.simdi()
        p = IkPersonel(hesap_email=kapsam.hesap, durum="aktif", yas_grubu="genel", devir_gun=0.0, dil="tr", portal_surumu=1,
                       portal_acik=True, olusturan=kapsam.kisi, created_at=an, updated_at=an)
        try:
            _personel_uygula(p, g, yeni=True)
            if p.durum == "aktif":
                await _sinir_denetle(db, kapsam.hesap)
        except s.TemelHata as h:
            raise _e(h)
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return _personel_sozlugu(p, await k.bakiye(db, p))

    @router.get("/personel.csv")
    async def personel_csv(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_dosya_hizi, kapsam.kisi)
        liste = (await db.execute(select(IkPersonel).where(_hk(IkPersonel, kapsam)).order_by(IkPersonel.ad))).scalars().all()
        bakiyeler = await k.bakiyeler(db, liste, await k.kurallar_al(db, kapsam.hesap))
        satirlar = [(p.ad, p.eposta or "", p.telefon or "", p.gorev or "", p.departman or "", s.gun_iso(p.ise_giris) or "",
                     p.durum, s.gun_iso(p.ayrilis_tarihi) or "", p.yas_grubu or "genel", s.gun_metni(float(p.devir_gun or 0)),
                     s.gun_iso(p.devir_tarihi) or "", p.notlar or "", s.gun_metni(bakiyeler[p.id]["kalan"])) for p in liste]
        return _csv_yaniti(s.csv_metni(list(s.PERSONEL_CSV_ALANLARI) + ["kalan_yillik_izin"], satirlar), "personel.csv")

    @router.post("/personel/ice-aktar")
    async def personel_ice_aktar(request: Request, db: AsyncSession = Depends(get_db)):
        """`{"csv": "..."}` — e-postası eşleşen kart güncellenir, diğerleri eklenir. Satır hataları listelenir."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        _hiz(_dosya_hizi, kapsam.kisi)
        g = await _govde(request, sinir=2 * 1024 * 1024)
        try:
            satirlar = s.csv_oku(str(g.get("csv") or ""))
        except s.TemelHata as h:
            raise _e(h)
        mevcut = {(p.eposta or "").lower(): p for p in (await db.execute(select(IkPersonel).where(
            _hk(IkPersonel, kapsam), IkPersonel.eposta.isnot(None)))).scalars().all()}
        sinir = await k.modul_ayari(db, kapsam.hesap, "personel_siniri", s.VARSAYILAN_PERSONEL_SINIRI)
        aktif = await k.aktif_personel_sayisi(db, kapsam.hesap)
        eklenen = guncellenen = 0
        hatalar: List[Dict[str, Any]] = []
        an = s.simdi()
        for no, satir in enumerate(satirlar, start=2):
            try:
                gov: Dict[str, Any] = {"ad": satir.get("ad")}
                for alan in ("eposta", "telefon", "gorev", "departman", "notlar"):
                    if satir.get(alan):
                        gov[alan] = satir[alan]
                if satir.get("ise_giris"):
                    gov["ise_giris"] = s.csv_tarih(satir["ise_giris"], "ise_giris").isoformat()
                if satir.get("ayrilis_tarihi"):
                    gov["ayrilis_tarihi"] = s.csv_tarih(satir["ayrilis_tarihi"], "ayrilis_tarihi").isoformat()
                if satir.get("devir_tarihi"):
                    gov["devir_tarihi"] = s.csv_tarih(satir["devir_tarihi"], "devir_tarihi").isoformat()
                if satir.get("devir_gun"):
                    gov["devir_gun"] = satir["devir_gun"]
                if satir.get("durum"):
                    d = satir["durum"].strip().lower()
                    gov["durum"] = "ayrildi" if d in ("ayrildi", "ayrıldı", "left", "inactive", "pasif") else "aktif"
                if satir.get("yas_grubu"):
                    gov["yas_grubu"] = satir["yas_grubu"].strip().lower()
                eposta = s.eposta_duzelt(gov.get("eposta"), "eposta") if gov.get("eposta") else ""
                p = mevcut.get(eposta) if eposta else None
                if p is None:
                    p = IkPersonel(hesap_email=kapsam.hesap, durum="aktif", yas_grubu="genel", devir_gun=0.0, dil="tr",
                                   portal_surumu=1, portal_acik=True, olusturan=kapsam.kisi, created_at=an, updated_at=an)
                    _personel_uygula(p, gov, yeni=True)
                    if p.durum == "aktif":
                        if sinir is not None and aktif + 1 > int(sinir):
                            raise s.IkHatasi("personel_siniri", sinir=int(sinir))
                        aktif += 1
                    db.add(p)
                    eklenen += 1
                    if eposta:
                        mevcut[eposta] = p
                else:
                    onceki = p.durum
                    _personel_uygula(p, gov, yeni=False)
                    if onceki != "aktif" and p.durum == "aktif":
                        if sinir is not None and aktif + 1 > int(sinir):
                            raise s.IkHatasi("personel_siniri", sinir=int(sinir))
                        aktif += 1
                    p.updated_at = an
                    guncellenen += 1
                await db.flush()
            except s.TemelHata as h:
                hatalar.append({"satir": no, **h.detay()})
        await db.commit()
        return {"eklenen": eklenen, "guncellenen": guncellenen, "hata_sayisi": len(hatalar), "hatalar": hatalar[:50]}

    @router.get("/personel/{pid}")
    async def personel_ayrinti(pid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        p = await _personel(db, kapsam, pid)
        izinler = (await db.execute(select(IkIzinler).where(IkIzinler.personel_id == p.id)
                                    .order_by(IkIzinler.baslangic.desc(), IkIzinler.id.desc()).limit(200))).scalars().all()
        return {**_personel_sozlugu(p, await k.bakiye(db, p)), "izinler": [_izin_sozlugu(i, p.ad) for i in izinler],
                "dosyalar": [_dosya_sozlugu(d) for d in await k.personel_dosyalari(db, p.id)]}

    @router.put("/personel/{pid}")
    async def personel_guncelle(pid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        p = await _personel(db, kapsam, pid)
        onceki = p.durum
        try:
            _personel_uygula(p, g, yeni=False)
            if onceki != "aktif" and p.durum == "aktif":
                await _sinir_denetle(db, kapsam.hesap)
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)
        p.updated_at = s.simdi()
        await db.commit()
        await db.refresh(p)
        return _personel_sozlugu(p, await k.bakiye(db, p))

    @router.delete("/personel/{pid}")
    async def personel_sil(pid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Çöp kutusuna: personel kartı, izin kayıtları, vardiyaları ve belge ekleriyle birlikte (birlikte geri gelir).
        Belge içerikleri çöp kaydı kalıcı silinene kadar bekletilir."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        p = await _personel(db, kapsam, pid)
        # Önce hepsi okunur, sonra tek flush'ta silinir: çocuk satırlar ebeveynle aynı işlemde çöpe düşsün.
        cocuklar: List[Any] = []
        for model in (IkIzinler, IkVardiyalar, IkDosyalar):
            cocuklar += list((await db.execute(select(model).where(model.personel_id == p.id))).scalars().all())
        await db.delete(p)
        for kayit in cocuklar:
            await db.delete(kayit)
        await db.commit()
        return {"ok": True}

    @router.post("/personel/{pid}/baglanti")
    async def personel_baglanti(pid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Girişsiz personel sayfası: `goster` (açar ve verir), `yenile` (eski bağlantı ölür), `iptal` (kapatır).
        `gonder: true` → bağlantı personele e-postayla gider."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        islem = g.get("islem") or "goster"
        if islem not in ("goster", "yenile", "iptal"):
            raise _hata(400, "secim_gecersiz", alan="islem")
        p = await _personel(db, kapsam, pid)
        if islem == "iptal":
            p.portal_acik = False
            p.portal_surumu = int(p.portal_surumu or 1) + 1
            await db.commit()
            return {"portal_acik": False, "adres": None}
        if p.durum != "aktif":
            raise _hata(409, "personel_ayrildi")
        if islem == "yenile":
            p.portal_surumu = int(p.portal_surumu or 1) + 1
        p.portal_acik = True
        await db.commit()
        await db.refresh(p)
        adres = s.portal_adresi(s.portal_jetonu(p.id, int(p.portal_surumu)))
        gonderilecek = False
        if g.get("gonder") is True:
            if not p.eposta:
                raise _hata(409, "eposta_yok", alan="eposta")
            _hiz(_eposta_hizi, kapsam.kisi)
            gonderilecek = True
            arka.add_task(k.baglanti_epostasi, p.id)
        return {"portal_acik": True, "adres": adres, "gonderildi": gonderilecek}

    # ------------------------------------------------------------- dosyalar
    @router.post("/personel/{pid}/dosyalar")
    async def dosya_ekle(pid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        _hiz(_dosya_hizi, kapsam.kisi)
        p = await _personel(db, kapsam, pid)
        from services import dosyalar

        try:
            sinir = min(await dosyalar.boyut_siniri_bayt(db), s.DOSYA_EN_COK_MB * 1024 * 1024)
            veri = await dosyalar.akistan_oku(dosya, sinir)
        except dosyalar.DosyaHatasi as h:
            raise _hata(h.durum, h.kod, **h.ek)
        try:
            d = await k.dosya_kaydet(db, p, ad_ham=dosya.filename or "belge", veri=veri, yukleyen=kapsam.kisi)
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)
        await db.commit()
        await db.refresh(d)
        return _dosya_sozlugu(d)

    @router.get("/dosyalar/{did}")
    async def dosya_indir(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        d = (await db.execute(select(IkDosyalar).where(IkDosyalar.id == did, _hk(IkDosyalar, kapsam)))).scalars().first()
        if d is None:
            raise _hata(404, "bulunamadi")
        from services import dosya_deposu

        adres = dosya_deposu.dogrudan_adres(d.depo, d.depolama_anahtari, d.ad, d.tur)
        if adres:
            return RedirectResponse(adres, status_code=302, headers={"Cache-Control": "no-store"})
        try:
            veri = await dosya_deposu.oku(db, d.depo, d.depolama_anahtari)
        except dosya_deposu.DepoHatasi:
            raise _hata(502, "depo_hatasi")
        return Response(veri, media_type=d.tur, headers={"Content-Disposition": icerik_konumu(d.ad), "Cache-Control": "private, no-store",
                                                         "X-Content-Type-Options": "nosniff"})

    @router.delete("/dosyalar/{did}")
    async def dosya_sil(did: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Çöp kutusuna (içerik kalıcı silinene kadar bekletilir)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        d = (await db.execute(select(IkDosyalar).where(IkDosyalar.id == did, _hk(IkDosyalar, kapsam)))).scalars().first()
        if d is None:
            raise _hata(404, "bulunamadi")
        await db.delete(d)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- izinler
    @router.get("/izinler")
    async def izin_listesi(request: Request, durum: Optional[str] = Query(None), personel_id: Optional[int] = Query(None),
                           tur: Optional[str] = Query(None), bas: Optional[str] = Query(None), bit: Optional[str] = Query(None),
                           db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(IkIzinler).where(_hk(IkIzinler, kapsam))
        if durum in s.IZIN_DURUMLARI:
            sorgu = sorgu.where(IkIzinler.durum == durum)
        if tur in s.IZIN_TURLERI:
            sorgu = sorgu.where(IkIzinler.tur == tur)
        if personel_id:
            sorgu = sorgu.where(IkIzinler.personel_id == personel_id)
        if bas:
            sorgu = sorgu.where(IkIzinler.bitis >= _tarih(bas, "bas"))
        if bit:
            sorgu = sorgu.where(IkIzinler.baslangic <= _tarih(bit, "bit"))
        liste = (await db.execute(sorgu.order_by(IkIzinler.created_at.desc(), IkIzinler.id.desc()).limit(500))).scalars().all()
        adlar = await _personel_adlari(db, [i.personel_id for i in liste])
        return {"items": [_izin_sozlugu(i, adlar.get(i.personel_id)) for i in liste], "toplam": len(liste)}

    @router.post("/izinler")
    async def izin_ekle(request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Panelden talep (beklemede) ya da `onayli: true` ile doğrudan onaylı kayıt. Uyarılar engellemez."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        try:
            p = await _personel(db, kapsam, int(s.tam_sayi(g.get("personel_id"), "personel_id", 1, 10**12)))
            girdi = _izin_girdisi(g)
            karar_notu = s.metin(g.get("not"), "not", 500, cok_satir=True) or None
        except s.TemelHata as h:
            raise _e(h)
        onayli = g.get("onayli") is True
        i, uyarilar = await _izin_olustur(db, p, girdi, kaynak="panel", talep_eden=kapsam.kisi, onayli=onayli, karar_notu=karar_notu)
        if onayli and g.get("bildir") is True:
            arka.add_task(k.izin_epostasi, i.id, "onay")
        return {"izin": _izin_sozlugu(i, p.ad), "uyarilar": uyarilar}

    @router.get("/izinler/takvim")
    async def izin_takvimi(request: Request, ay: Optional[str] = Query(None, max_length=7), db: AsyncSession = Depends(get_db)):
        """Ay görünümü: aya değen onaylı + bekleyen izinler ve ayın tatilleri."""
        kapsam = kapsam_al(request)
        try:
            yil, a = (int(x) for x in (ay or s.bugun().strftime("%Y-%m")).split("-"))
            ilk = date(yil, a, 1)
        except (ValueError, TypeError):
            raise _hata(400, "tarih_gecersiz", alan="ay")
        son = (ilk.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        liste = (await db.execute(select(IkIzinler).where(_hk(IkIzinler, kapsam), IkIzinler.durum.in_(s.ETKIN_DURUMLAR),
                                                          IkIzinler.baslangic <= son, IkIzinler.bitis >= ilk)
                                  .order_by(IkIzinler.baslangic))).scalars().all()
        adlar = await _personel_adlari(db, [i.personel_id for i in liste])
        kr = await k.kurallar_al(db, kapsam.hesap)
        harita = await k.tatil_haritasi(db, kapsam.hesap, ilk, son, kr)
        ek = {t.tarih: t.ad for t in await k.eklenen_tatiller(db, kapsam.hesap, ilk, son)}
        sabit = {date.fromisoformat(t["tarih"]): t["ad"] for t in s.sabit_tatiller(yil, kr.kapali_sabitler) if not t["kapali"]}
        return {"ay": ilk.strftime("%Y-%m"), "ilk": ilk.isoformat(), "son": son.isoformat(),
                "calisma_gunleri": list(kr.calisma_gunleri),
                "izinler": [_izin_sozlugu(i, adlar.get(i.personel_id)) for i in liste],
                "tatiller": [{"tarih": g.isoformat(), "ad": ek.get(g) or sabit.get(g) or "", "oran": oran}
                             for g, oran in sorted(harita.items()) if ilk <= g <= son]}

    @router.get("/izinler.ics")
    async def izin_ics(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_dosya_hizi, kapsam.kisi)
        alt = s.bugun() - timedelta(days=365)
        liste = (await db.execute(select(IkIzinler).where(_hk(IkIzinler, kapsam), IkIzinler.durum == "onaylandi",
                                                          IkIzinler.bitis >= alt).order_by(IkIzinler.baslangic).limit(5000))).scalars().all()
        adlar = await _personel_adlari(db, [i.personel_id for i in liste])
        olaylar = [(i.id, i.baslangic, i.bitis, f"{adlar.get(i.personel_id) or '—'} — {s.tur_adi(i.tur)}") for i in liste]
        return _ics_yaniti(s.izin_ics("İzin takvimi", olaylar), "izin-takvimi.ics")

    @router.get("/izinler.csv")
    async def izin_csv(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_dosya_hizi, kapsam.kisi)
        liste = (await db.execute(select(IkIzinler).where(_hk(IkIzinler, kapsam)).order_by(IkIzinler.baslangic.desc()).limit(10000)
                                  )).scalars().all()
        adlar = await _personel_adlari(db, [i.personel_id for i in liste])
        satirlar = [(adlar.get(i.personel_id) or "", i.tur, i.baslangic.isoformat(), i.bitis.isoformat(), s.gun_metni(float(i.gun or 0)),
                     i.durum, i.kaynak, (i.aciklama or "") if i.tur != "rapor" else "", i.karar_notu or "") for i in liste]
        return _csv_yaniti(s.csv_metni(["personel", "tur", "baslangic", "bitis", "gun", "durum", "kaynak", "aciklama", "karar_notu"],
                                       satirlar), "izinler.csv")

    @router.get("/izinler/{iid}")
    async def izin_ayrinti(iid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        i = await _izin(db, kapsam, iid)
        p = (await db.execute(select(IkPersonel).where(IkPersonel.id == i.personel_id))).scalars().first()
        if p is None:
            raise _hata(404, "bulunamadi")
        kr = await k.kurallar_al(db, kapsam.hesap)
        uyarilar = await k.izin_uyarilari(db, p, i.tur, i.baslangic, i.bitis, float(i.gun or 0), kr, haric=i.id,
                                          haric_bekleyen_gun=float(i.gun or 0) if (i.tur == "yillik" and i.durum == "beklemede") else 0.0)
        return {"izin": _izin_sozlugu(i, p.ad), "personel": _personel_sozlugu(p, await k.bakiye(db, p, kr), tam=False),
                "uyarilar": uyarilar, "ayni_tarihte": await k.ayni_tarihte_izinliler(db, kapsam.hesap, p.id, i.baslangic, i.bitis)}

    @router.post("/izinler/{iid}/karar")
    async def izin_karar(iid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Onay / ret (+ not). Bekleyen talepte; onayda gün yeniden hesaplanır (tatil eklendiyse güncel) ve bakiye düşer."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        karar = g.get("karar")
        if karar not in ("onay", "ret"):
            raise _hata(400, "secim_gecersiz", alan="karar")
        try:
            notu = s.metin(g.get("not"), "not", 500, cok_satir=True) or None
        except s.TemelHata as h:
            raise _e(h)
        i = await _izin(db, kapsam, iid)
        if i.durum != "beklemede":
            raise _hata(409, "karar_verilmis", mevcut=i.durum)
        an = s.simdi()
        if karar == "onay":
            i.gun = await k.gun_hesapla(db, i.hesap_email, i.baslangic, i.bitis, bool(i.yarim_gun))
        i.durum = "onaylandi" if karar == "onay" else "reddedildi"
        i.karar_notu, i.karar_veren, i.karar_at, i.updated_at = notu, kapsam.kisi, an, an
        await db.commit()
        await db.refresh(i)
        if g.get("bildir", True) is not False:
            arka.add_task(k.izin_epostasi, i.id, karar)
        return {"izin": _izin_sozlugu(i)}

    @router.post("/izinler/{iid}/iptal")
    async def izin_iptal(iid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Bekleyen ya da onaylı izni iptal eder (onaylı yıllık izinde gün bakiyeye geri döner)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        i = await _izin(db, kapsam, iid)
        if i.durum not in s.ETKIN_DURUMLAR:
            raise _hata(409, "iptal_edilemez", mevcut=i.durum)
        onayliydi = i.durum == "onaylandi"
        an = s.simdi()
        i.durum, i.iptal_eden, i.iptal_at, i.updated_at = "iptal", kapsam.kisi, an, an
        await db.commit()
        await db.refresh(i)
        if onayliydi and g.get("bildir", True) is not False:
            arka.add_task(k.izin_epostasi, i.id, "iptal")
        return {"izin": _izin_sozlugu(i)}

    @router.post("/izinler/{iid}/geri-al")
    async def izin_geri_al(iid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Kararı (onay / ret) ya da iptali geri alır: talep yeniden "beklemede"."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        i = await _izin(db, kapsam, iid)
        if i.durum == "beklemede":
            raise _hata(409, "zaten_beklemede")
        an = s.simdi()
        i.durum = "beklemede"
        i.karar_veren = i.karar_at = i.karar_notu = None
        i.iptal_eden = i.iptal_at = None
        i.updated_at = an
        await db.commit()
        await db.refresh(i)
        return {"izin": _izin_sozlugu(i)}

    # ------------------------------------------------------------- vardiya şablonları
    @router.get("/sablonlar")
    async def sablonlar(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        liste = (await db.execute(select(IkVardiyaSablonlari).where(_hk(IkVardiyaSablonlari, kapsam))
                                  .order_by(IkVardiyaSablonlari.sira, IkVardiyaSablonlari.id))).scalars().all()
        return {"items": [_sablon_sozlugu(x) for x in liste]}

    def _sablon_uygula(x: IkVardiyaSablonlari, g: Dict[str, Any], yeni: bool) -> None:
        if "ad" in g or yeni:
            x.ad = s.metin(g.get("ad"), "ad", 60, zorunlu=True)
        if "baslangic" in g or yeni:
            x.baslangic = s.saat_duzelt(g.get("baslangic"), "baslangic")
        if "bitis" in g or yeni:
            x.bitis = s.saat_duzelt(g.get("bitis"), "bitis")
        if x.baslangic == x.bitis:
            raise s.IkHatasi("sure_gecersiz", "bitis")
        if "mola_dk" in g:
            x.mola_dk = s.tam_sayi(g.get("mola_dk"), "mola_dk", 0, 600)
        if "renk" in g:
            x.renk = s.renk_duzelt(g.get("renk"))
        if "aktif" in g:
            x.aktif = s.bool_duzelt(g.get("aktif"), "aktif")
        if "sira" in g:
            x.sira = s.tam_sayi(g.get("sira"), "sira", 0, 1000)
        b, e = s.vardiya_anlari(date(2026, 1, 5), x.baslangic, x.bitis)
        if s.net_dakika(b, e, x.mola_dk) <= 0:
            raise s.IkHatasi("mola_uzun", "mola_dk")

    @router.post("/sablonlar")
    async def sablon_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        x = IkVardiyaSablonlari(hesap_email=kapsam.hesap, mola_dk=0, renk="#7c3aed", aktif=True, sira=0, created_at=s.simdi())
        try:
            _sablon_uygula(x, g, yeni=True)
        except s.TemelHata as h:
            raise _e(h)
        db.add(x)
        await db.commit()
        await db.refresh(x)
        return _sablon_sozlugu(x)

    @router.put("/sablonlar/{sid}")
    async def sablon_guncelle(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        x = await _sablon(db, kapsam, sid)
        try:
            _sablon_uygula(x, g, yeni=False)
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)
        await db.commit()
        await db.refresh(x)
        return _sablon_sozlugu(x)

    @router.delete("/sablonlar/{sid}")
    async def sablon_sil(sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        """Şablon silinir; ondan oluşturulmuş vardiyalar saatleriyle kalır (yalnız bağ kalkar)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        x = await _sablon(db, kapsam, sid)
        for v in (await db.execute(select(IkVardiyalar).where(IkVardiyalar.sablon_id == x.id))).scalars().all():
            v.sablon_id = None
        await db.delete(x)
        await db.commit()
        return {"ok": True}

    # ------------------------------------------------------------- vardiyalar
    @router.get("/vardiyalar")
    async def hafta_plani(request: Request, hafta: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        hb = _hafta(hafta)
        he = hb + timedelta(days=6)
        kr = await k.kurallar_al(db, kapsam.hesap)
        vardiyalar = await _hafta_vardiyalari(db, kapsam, hb)
        pidler = {v.personel_id for v in vardiyalar}
        personel = (await db.execute(select(IkPersonel).where(_hk(IkPersonel, kapsam), or_(
            IkPersonel.durum == "aktif", IkPersonel.id.in_(sorted(pidler) or [0]))).order_by(IkPersonel.ad))).scalars().all()
        izinli = await k.izinli_gunler(db, kapsam.hesap, hb, he)
        bekleyen = await _bekleyen_gunler(db, kapsam, hb, he)
        harita = await k.tatil_haritasi(db, kapsam.hesap, hb, he, kr)
        toplam: Dict[int, int] = {}
        for v in vardiyalar:
            toplam[v.personel_id] = toplam.get(v.personel_id, 0) + s.net_dakika(v.bas, v.bit, v.mola_dk)
        return {
            "hafta_bas": hb.isoformat(), "gunler": [(hb + timedelta(days=i)).isoformat() for i in range(7)],
            "personel": [_personel_sozlugu(p, tam=False) for p in personel],
            "vardiyalar": [_vardiya_sozlugu(v) for v in vardiyalar],
            "izinli": {str(pid): {g.isoformat(): t for g, t in gunler_.items()} for pid, gunler_ in izinli.items()},
            "bekleyen_izin": {str(pid): sorted(g.isoformat() for g in gunler_) for pid, gunler_ in bekleyen.items()},
            "tatiller": {g.isoformat(): oran for g, oran in harita.items() if hb <= g <= he},
            "uyarilar": await _hafta_uyarilari(db, kapsam, hb, kr),
            "toplam_dk": {str(pid): dk for pid, dk in toplam.items()},
            "sayilar": {"taslak": sum(1 for v in vardiyalar if v.durum == "taslak"),
                        "yayinda": sum(1 for v in vardiyalar if v.durum == "yayinda"),
                        "degisti": sum(1 for v in vardiyalar if v.durum == "yayinda" and v.degisti)},
            "sinirlar": {"haftalik_en_cok_saat": kr.haftalik_en_cok_saat, "en_az_dinlenme_saat": kr.en_az_dinlenme_saat},
        }

    @router.post("/vardiyalar")
    async def vardiya_ekle(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        an = s.simdi()
        v = IkVardiyalar(hesap_email=kapsam.hesap, durum="taslak", degisti=False, mola_dk=0, olusturan=kapsam.kisi,
                         created_at=an, updated_at=an)
        try:
            await _vardiya_uygula(db, kapsam, v, g, yeni=True)
        except s.TemelHata as h:
            raise _e(h)
        db.add(v)
        await db.commit()
        await db.refresh(v)
        hb = s.hafta_basi(v.tarih)
        uy = [u for u in await _hafta_uyarilari(db, kapsam, hb) if u.get("vardiya_id") == v.id or
              (u["tur"] == "haftalik" and u["personel_id"] == v.personel_id)]
        return {"vardiya": _vardiya_sozlugu(v), "uyarilar": uy}

    @router.put("/vardiyalar/{vid}")
    async def vardiya_guncelle(vid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        v = await _vardiya(db, kapsam, vid)
        try:
            await _vardiya_uygula(db, kapsam, v, g, yeni=False)
        except s.TemelHata as h:
            await db.rollback()
            raise _e(h)
        if v.durum == "yayinda":
            v.degisti = True
        v.updated_at = s.simdi()
        await db.commit()
        await db.refresh(v)
        uy = [u for u in await _hafta_uyarilari(db, kapsam, s.hafta_basi(v.tarih)) if u.get("vardiya_id") == v.id or
              (u["tur"] == "haftalik" and u["personel_id"] == v.personel_id)]
        return {"vardiya": _vardiya_sozlugu(v), "uyarilar": uy}

    @router.delete("/vardiyalar/{vid}")
    async def vardiya_sil(vid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        v = await _vardiya(db, kapsam, vid)
        await db.delete(v)
        await db.commit()
        return {"ok": True}

    @router.post("/vardiyalar/kopyala")
    async def vardiya_kopyala(request: Request, db: AsyncSession = Depends(get_db)):
        """Geçen haftanın planını bu haftaya TASLAK olarak kopyalar. `uzerine_yaz` yoksa o gün vardiyası olan
        kişiye o gün eklenmez; ayrılmış personelin vardiyası kopyalanmaz."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        hb = _hafta(g.get("hafta"))
        kaynak_hb = hb - timedelta(days=7)
        kaynak = await _hafta_vardiyalari(db, kapsam, kaynak_hb)
        hedef = await _hafta_vardiyalari(db, kapsam, hb)
        uzerine = g.get("uzerine_yaz") is True
        aktifler = {p for (p,) in (await db.execute(select(IkPersonel.id).where(_hk(IkPersonel, kapsam),
                                                                                IkPersonel.durum == "aktif"))).all()}
        if uzerine:
            for v in hedef:
                if v.durum == "taslak":
                    await db.delete(v)
            hedef = [v for v in hedef if v.durum != "taslak"]
        dolu = {(v.personel_id, v.tarih) for v in hedef}
        an = s.simdi()
        eklenen = atlanan = 0
        for v in kaynak[: s.EN_COK_KOPYA]:
            yeni_tarih = v.tarih + timedelta(days=7)
            if v.personel_id not in aktifler or (v.personel_id, yeni_tarih) in dolu:
                atlanan += 1
                continue
            db.add(IkVardiyalar(hesap_email=kapsam.hesap, personel_id=v.personel_id, tarih=yeni_tarih, bas=v.bas + timedelta(days=7),
                                bit=v.bit + timedelta(days=7), mola_dk=v.mola_dk, sablon_id=v.sablon_id, durum="taslak", degisti=False,
                                notlar=v.notlar, olusturan=kapsam.kisi, created_at=an, updated_at=an))
            eklenen += 1
        await db.commit()
        return {"eklenen": eklenen, "atlanan": atlanan, "kaynak_hafta": kaynak_hb.isoformat()}

    @router.post("/vardiyalar/yayinla")
    async def vardiya_yayinla(request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        """Haftanın taslaklarını yayınlar; yeni yayınlanan ya da yayındayken değişen vardiyası olan personele
        (e-postası varsa) haftalık planını gönderir (`bildir: false` ile gönderilmez)."""
        kapsam = kapsam_al(request)
        _yaz(kapsam)
        g = await _govde(request)
        hb = _hafta(g.get("hafta"))
        an = s.simdi()
        etkilenen: set = set()
        yayinlanan = 0
        for v in await _hafta_vardiyalari(db, kapsam, hb):
            if v.durum == "taslak":
                v.durum, v.yayin_at, v.degisti = "yayinda", an, False
                yayinlanan += 1
                etkilenen.add(v.personel_id)
            elif v.degisti:
                v.degisti, v.yayin_at = False, an
                etkilenen.add(v.personel_id)
        await db.commit()
        bildirilen = 0
        if etkilenen and g.get("bildir", True) is not False:
            epostali = [p for (p,) in (await db.execute(select(IkPersonel.id).where(
                IkPersonel.id.in_(sorted(etkilenen)), IkPersonel.eposta.isnot(None), IkPersonel.durum == "aktif"))).all()]
            bildirilen = len(epostali)
            if epostali:
                arka.add_task(k.vardiya_epostalari, kapsam.hesap, hb, epostali)
        return {"yayinlanan": yayinlanan, "etkilenen": len(etkilenen), "bildirilen": bildirilen}

    async def _plan_satirlari(db: AsyncSession, kapsam: Kapsam, hb: date):
        vardiyalar = await _hafta_vardiyalari(db, kapsam, hb)
        pidler = {v.personel_id for v in vardiyalar}
        personel = (await db.execute(select(IkPersonel).where(_hk(IkPersonel, kapsam), or_(
            IkPersonel.durum == "aktif", IkPersonel.id.in_(sorted(pidler) or [0]))).order_by(IkPersonel.ad))).scalars().all()
        sablon_adlari = dict((await db.execute(select(IkVardiyaSablonlari.id, IkVardiyaSablonlari.ad).where(
            _hk(IkVardiyaSablonlari, kapsam)))).all())
        izinli = await k.izinli_gunler(db, kapsam.hesap, hb, hb + timedelta(days=6))
        return vardiyalar, personel, sablon_adlari, izinli

    @router.get("/vardiyalar.csv")
    async def plan_csv(request: Request, hafta: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_dosya_hizi, kapsam.kisi)
        hb = _hafta(hafta)
        vardiyalar, personel, sablon_adlari, _ = await _plan_satirlari(db, kapsam, hb)
        adlar = {p.id: p for p in personel}
        satirlar = []
        for v in vardiyalar:
            p = adlar.get(v.personel_id)
            satirlar.append((p.ad if p else "", (p.departman or "") if p else "", v.tarih.isoformat(), s.saat_metni(v.bas),
                             s.saat_metni(v.bit), v.mola_dk, round(s.net_dakika(v.bas, v.bit, v.mola_dk) / 60, 2),
                             sablon_adlari.get(v.sablon_id, ""), v.durum, v.notlar or ""))
        return _csv_yaniti(s.csv_metni(["personel", "departman", "tarih", "baslangic", "bitis", "mola_dk", "net_saat", "sablon",
                                        "durum", "not"], satirlar), f"vardiya-{hb.isoformat()}.csv")

    @router.get("/vardiyalar.pdf")
    async def plan_pdf(request: Request, hafta: Optional[str] = Query(None), dil: Optional[str] = Query(None, max_length=5),
                       db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_dosya_hizi, kapsam.kisi)
        hb = _hafta(hafta)
        vardiyalar, personel, sablon_adlari, izinli = await _plan_satirlari(db, kapsam, hb)
        e = s.PDF_ETIKET[s.pdf_dili(dil)]
        satirlar = []
        for p in personel:
            gunler_: List[List[str]] = [[] for _ in range(7)]
            dk = 0
            for v in vardiyalar:
                if v.personel_id != p.id:
                    continue
                i = (v.tarih - hb).days
                metin = f"{s.saat_metni(v.bas)}–{s.saat_metni(v.bit)}"
                if v.sablon_id and sablon_adlari.get(v.sablon_id):
                    metin += f" {sablon_adlari[v.sablon_id]}"
                if v.durum == "taslak":
                    metin += f" ({e['taslak']})"
                if 0 <= i < 7:
                    gunler_[i].append(metin)
                dk += s.net_dakika(v.bas, v.bit, v.mola_dk)
            for g_, _tur in (izinli.get(p.id) or {}).items():
                i = (g_ - hb).days
                if 0 <= i < 7:
                    gunler_[i].append(e["izin"])
            satirlar.append({"ad": p.ad, "gunler": gunler_, "toplam_saat": round(dk / 60, 1)})
        firma = (await k.ayar_satiri(db, kapsam.hesap))
        veri = s.plan_pdf(firma=(firma.firma_adi if firma and firma.firma_adi else ""), hafta_bas=hb, satirlar=satirlar, dil=dil or "tr")
        return Response(content=veri, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="vardiya-{hb.isoformat()}.pdf"', "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff"})


async def _bekleyen_gunler(db: AsyncSession, kapsam: Kapsam, bas: date, bit: date) -> Dict[int, set]:
    sonuc: Dict[int, set] = {}
    for pid, b, e in (await db.execute(select(IkIzinler.personel_id, IkIzinler.baslangic, IkIzinler.bitis).where(
            _hk(IkIzinler, kapsam), IkIzinler.durum == "beklemede", IkIzinler.baslangic <= bit, IkIzinler.bitis >= bas))).all():
        for g in s.gunler(max(b, bas), min(e, bit)):
            sonuc.setdefault(pid, set()).add(g)
    return sonuc


_uclari_kur(musteri_router, _musteri_kapsami)
_uclari_kur(yonetici_router, _yonetici_kapsami)


@yonetici_router.get("/hesaplar")
async def yonetici_hesaplar(db: AsyncSession = Depends(get_db)):
    """İK kaydı olan ya da modülü açık müşteri hesapları (salt okunur destek görünümü için)."""
    from models.workspace_modules import WorkspaceModules

    hesaplar = {h for (h,) in (await db.execute(select(IkPersonel.hesap_email).where(IkPersonel.hesap_email.isnot(None)).distinct())).all()}
    hesaplar |= set((await db.execute(select(WorkspaceModules.musteri_eposta).where(
        WorkspaceModules.modul_anahtari == MODUL, WorkspaceModules.acik.is_(True)))).scalars().all())
    aktif = dict((await db.execute(select(IkPersonel.hesap_email, func.count(IkPersonel.id)).where(
        IkPersonel.hesap_email.isnot(None), IkPersonel.durum == "aktif").group_by(IkPersonel.hesap_email))).all())
    bekleyen = dict((await db.execute(select(IkIzinler.hesap_email, func.count(IkIzinler.id)).where(
        IkIzinler.hesap_email.isnot(None), IkIzinler.durum == "beklemede").group_by(IkIzinler.hesap_email))).all())
    adlar = dict((await db.execute(select(IkAyarlari.hesap_email, IkAyarlari.firma_adi).where(IkAyarlari.hesap_email.isnot(None)))).all())
    return {"items": [{"hesap_email": h, "firma_adi": adlar.get(h), "personel": int(aktif.get(h, 0)),
                       "bekleyen_izin": int(bekleyen.get(h, 0))} for h in sorted(x for x in hesaplar if x)]}


# ---------------------------------------------------------------------------
# Girişsiz personel portalı
# ---------------------------------------------------------------------------
GIZLI_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow",
                   "Referrer-Policy": "no-referrer"}


async def _portal_personeli(db: AsyncSession, request: Request, jeton: str, yazma: bool = False) -> IkPersonel:
    """Biçim/imza/sürüm tutmazsa 404; bağlantı iptal ya da personel ayrıldıysa 410; sahibinin modülü kapalıysa 410."""
    if not await izin_ver((_portal_hizi, ip_ozeti("ik-portal|" + istemci_ip(request)))):
        raise _hata(429, "cok_hizli")
    parca = s.jeton_parcala(jeton)
    if parca is None:
        raise _hata(404, "baglanti_gecersiz")
    p = (await db.execute(select(IkPersonel).where(IkPersonel.id == parca[0]))).scalars().first()
    if p is None or int(p.portal_surumu or 1) != parca[1] or not s.portal_jetonu_gecerli_mi(jeton, p.id, parca[1]):
        raise _hata(404, "baglanti_gecersiz")
    if not p.portal_acik:
        raise _hata(410, "baglanti_kapali")
    if p.durum != "aktif":
        raise _hata(410, "personel_ayrildi")
    if p.hesap_email:
        from services.moduller import modul_acik_mi

        if not await modul_acik_mi(db, p.hesap_email, MODUL):
            raise _hata(410, "modul_kapali")
    if yazma:
        _hiz(_portal_yazma_hizi, f"personel-{p.id}")
    return p


def _portal_cevap(veri: Dict[str, Any]) -> Response:
    return Response(json.dumps(veri, ensure_ascii=False), media_type="application/json", headers=GIZLI_BASLIKLAR)


@acik_router.get("/{jeton}")
async def portal(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    p = await _portal_personeli(db, request, jeton)
    p.portal_son_at = s.simdi()
    await db.commit()
    await db.refresh(p)
    kr = await k.kurallar_al(db, p.hesap_email)
    bugun = s.bugun()
    izinler = (await db.execute(select(IkIzinler).where(IkIzinler.personel_id == p.id)
                                .order_by(IkIzinler.baslangic.desc(), IkIzinler.id.desc()).limit(100))).scalars().all()
    vardiyalar = (await db.execute(select(IkVardiyalar).where(
        IkVardiyalar.personel_id == p.id, IkVardiyalar.durum == "yayinda", IkVardiyalar.tarih >= bugun - timedelta(days=7),
        IkVardiyalar.tarih <= bugun + timedelta(days=42)).order_by(IkVardiyalar.bas))).scalars().all()
    a = await k.ayar_satiri(db, p.hesap_email)
    firma = await k._ayar_firma(db, p.hesap_email)  # noqa: SLF001
    tatiller = await k.tatil_haritasi(db, p.hesap_email, bugun, bugun + timedelta(days=60), kr)
    return _portal_cevap({
        "firma": firma, "dil": p.dil or "tr", "bugun": bugun.isoformat(),
        "personel": {"ad": p.ad, "gorev": p.gorev or "", "departman": p.departman or "", "ise_giris": s.gun_iso(p.ise_giris)},
        "bakiye": await k.bakiye(db, p, kr),
        "izinler": [{k_: v for k_, v in _izin_sozlugu(i).items() if k_ not in ("karar_veren", "talep_eden", "iptal_eden", "personel_ad")}
                    for i in izinler],
        "vardiyalar": [{k_: v for k_, v in _vardiya_sozlugu(v).items() if k_ not in ("degisti", "yayin_at", "personel_id")}
                       for v in vardiyalar],
        "izin_turleri": list(s.IZIN_TURLERI), "yasal_gunler": dict(kr.yasal or s.VARSAYILAN_YASAL),
        "calisma_gunleri": list(kr.calisma_gunleri),
        "tatiller": {g.isoformat(): oran for g, oran in sorted(tatiller.items())},
        "ayar_var": a is not None,
    })


@acik_router.get("/{jeton}/gun-hesapla")
async def portal_gun_hesapla(jeton: str, request: Request, bas: str = Query(...), bit: Optional[str] = Query(None),
                             yarim: bool = Query(False), db: AsyncSession = Depends(get_db)):
    p = await _portal_personeli(db, request, jeton)
    b = _tarih(bas, "bas")
    e = _tarih(bit, "bit", b)
    if e < b or s.takvim_gunu(b, e) > s.EN_COK_IZIN_GUN:
        raise _hata(400, "aralik_gecersiz", alan="bit")
    return _portal_cevap({"gun": await k.gun_hesapla(db, p.hesap_email, b, e, yarim and b == e), "takvim_gunu": s.takvim_gunu(b, e)})


@acik_router.post("/{jeton}/izin")
async def portal_izin(jeton: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Personelin izin talebi (beklemede). Aynı istek kimliği ya da aynı bekleyen talep ikinci kez açılmaz."""
    p = await _portal_personeli(db, request, jeton, yazma=True)
    g = await _govde(request, sinir=16 * 1024)
    try:
        girdi = _izin_girdisi(g, portal=True)
    except s.TemelHata as h:
        raise _e(h)
    istek = str(g.get("istek_kimligi") or "").strip()[:40] or None
    onceki = None
    if istek:
        onceki = (await db.execute(select(IkIzinler).where(IkIzinler.personel_id == p.id, IkIzinler.istek_kimligi == istek))).scalars().first()
    if onceki is None:
        onceki = (await db.execute(select(IkIzinler).where(
            IkIzinler.personel_id == p.id, IkIzinler.durum == "beklemede", IkIzinler.tur == girdi.tur,
            IkIzinler.baslangic == girdi.baslangic, IkIzinler.bitis == girdi.bitis))).scalars().first()
    if onceki is not None:
        return _portal_cevap({"izin": _izin_sozlugu(onceki), "uyarilar": [], "tekrar": True})
    i, uyarilar = await _izin_olustur(db, p, girdi, kaynak="portal", talep_eden=None, istek_kimligi=istek)
    arka.add_task(k.talep_bildirimi, i.id)
    # Personele yalnız kendi bilgisini ilgilendiren uyarılar (başkasının izni gösterilmez).
    return _portal_cevap({"izin": _izin_sozlugu(i), "uyarilar": [u for u in uyarilar if u["tur"] != "personel_ayrildi"],
                          "tekrar": False})


@acik_router.post("/{jeton}/izin/{iid}/geri-cek")
async def portal_geri_cek(jeton: str, iid: int, request: Request, db: AsyncSession = Depends(get_db)):
    p = await _portal_personeli(db, request, jeton, yazma=True)
    i = (await db.execute(select(IkIzinler).where(IkIzinler.id == iid, IkIzinler.personel_id == p.id))).scalars().first()
    if i is None:
        raise _hata(404, "bulunamadi")
    if i.durum != "beklemede":
        raise _hata(409, "karar_verilmis", mevcut=i.durum)
    an = s.simdi()
    i.durum, i.iptal_eden, i.iptal_at, i.updated_at = "iptal", "personel", an, an
    await db.commit()
    await db.refresh(i)
    return _portal_cevap({"izin": _izin_sozlugu(i)})


@acik_router.get("/{jeton}/vardiyalar.ics")
async def portal_ics(jeton: str, request: Request, db: AsyncSession = Depends(get_db)):
    p = await _portal_personeli(db, request, jeton)
    bugun = s.bugun()
    vardiyalar = (await db.execute(select(IkVardiyalar).where(
        IkVardiyalar.personel_id == p.id, IkVardiyalar.durum == "yayinda", IkVardiyalar.tarih >= bugun - timedelta(days=30),
        IkVardiyalar.tarih <= bugun + timedelta(days=120)).order_by(IkVardiyalar.bas))).scalars().all()
    firma = await k._ayar_firma(db, p.hesap_email)  # noqa: SLF001
    baslik = s.metinler(p.dil or "tr")["vardiya_konu"].split(" ")[0]
    olaylar = [(v.id, v.bas, v.bit, f"{firma} — {s.saat_metni(v.bas)}–{s.saat_metni(v.bit)}") for v in vardiyalar]
    return _ics_yaniti(s.vardiya_ics(f"{firma} — {baslik}", olaylar), "vardiyalarim.ics", gizli=True)


router = (yonetici_router, musteri_router, acik_router)
