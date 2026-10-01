"""Faz 4Q — Dinamik QR stüdyosu ve kısa link.

Herkese açık (`/api/v1/q`):
  GET|HEAD "/{kod}"            kısa adres: 302 (no-store) / .vcf / .ics; pasif, süresi ya da
                               tarama limiti dolmuş → 410, bilinmeyen → 404 (7 dilli, noindex
                               HTML). Site tarafında `functions/q/[kod].js` buraya vekilliyor
                               (`/q/<kod>` → `/api/v1/q/<kod>`; IP, ülke, UA, Referer iletiliyor).

Yönetici (`/api/v1/dinamik-qr/yonetim`) — ajansın kendi kayıtları + bütün müşterilerinki:
Müşteri (`/api/v1/qr-kodlarim`; modül `dinamik_qr` açık + hesap izni `qr`) — yalnız etkin hesabın kayıtları:
  GET    "/meta"                türler, sınırlar, kayıt hakkı
  GET    ""                     liste (?tur=&kisa=&durum=&ara=&hesap=[yalnız yönetici])
  POST   ""                     oluştur {ad, tur, alanlar, tasarim, kisa_link, takma_ad, aktif,
                                bitis, tarama_limiti, logo (base64 / data URL)}
  POST   "/onizleme"            canlı önizleme (SVG metni + okunabilirlik uyarıları); kaydetmez
  POST   "/toplu/onizleme"      CSV (çok parçalı `dosya`) → satır satır doğrulama
  POST   "/toplu/olustur"       {satirlar: [...], tasarim?} → toplu oluştur
  POST   "/zip"                 {idler, bicim: png|svg} → ZIP
  GET    "/{id}"                ayrıntı (Wi-Fi parolası dahil — yalnız sahibine)
  PUT    "/{id}"                kısmi güncelle (logo / logo_kaldir dahil)
  DELETE "/{id}"                sil (çöp kutusuna; logo birlikte)
  GET    "/{id}/analiz?gun=30"  toplam/tekil, günlük seri, ülke/cihaz/işletim/yönlendiren dağılımı
  GET    "/{id}/gorsel?bicim=png|svg&boyut="   indir
Yalnız yönetici:
  POST   "/{id}/engelle"        {engelli} — kötüye kullanımda kapatır; sahibi açamaz

Kötüye kullanım: oluşturma/önizleme/toplu işlemde kişi başı hız sınırı, müşteri
hesabı başına kayıt sınırı (modül ayarı `kayit_siniri`, varsayılan 100),
yönetici engeli, hedef şema beyaz listesi (taramada yeniden doğrulanır).

Tarama kaydı yanıtı geciktirmiyor: yanıt döndükten sonra arka plan görevi tek
INSERT (+ bot değilse sayaç UPDATE'i) yapıyor. Ham IP ve tam User-Agent
saklanmıyor; IP'nin gün ve tuzla alınmış özeti (tekil sayım) tutuluyor.
"""

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.database import db_manager, get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from models.dinamik_qr import DinamikQr, DinamikQrLogolari, DinamikQrTaramalari
from services import dinamik_qr as s
from services.dosya_deposu import icerik_konumu
from sqlalchemy import desc, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

MODUL = "dinamik_qr"
IZIN = "qr"
VARSAYILAN_KAYIT_SINIRI = 100
LISTE_SINIRI = 500
TARAMA_LIMITI_EN_COK = 10_000_000

acik_router = APIRouter(prefix="/api/v1/q", tags=["dinamik_qr"])
yonetici_router = APIRouter(
    prefix="/api/v1/dinamik-qr/yonetim",
    tags=["dinamik_qr"],
    dependencies=[Depends(yonetici_gerekli)],
)
musteri_router = APIRouter(
    prefix="/api/v1/qr-kodlarim",
    tags=["dinamik_qr"],
    dependencies=[Depends(modul_gerekli(MODUL)), Depends(izin_gerekli(IZIN))],
)

#: Kişi başı: dakikada 30 oluşturma/güncelleme, 120 önizleme, 5 toplu işlem.
_olusturma_hizi = HizSiniri(30, 60.0)
_onizleme_hizi = HizSiniri(120, 60.0)
_toplu_hizi = HizSiniri(5, 60.0)
#: Aynı IP + aynı QR: dakikada 30'dan fazla tarama kaydedilmez (yönlendirme yine çalışır).
_tarama_hizi = HizSiniri(30, 60.0)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_olusturma_hizi, _onizleme_hizi, _toplu_hizi, _tarama_hizi):
        h.temizle()


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


def _qr_hatasi(h: s.QrHatasi) -> HTTPException:
    return HTTPException(status_code=h.durum, detail=h.detay())


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _an(an: Optional[datetime]) -> Optional[str]:
    u = _utc(an)
    return u.isoformat() if u else None


def durum_hesapla(k: DinamikQr, simdi: Optional[datetime] = None) -> str:
    simdi = simdi or _simdi()
    if k.engelli:
        return "engelli"
    if not k.aktif:
        return "pasif"
    bitis = _utc(k.bitis)
    if bitis is not None and bitis <= simdi:
        return "suresi_doldu"
    if k.tarama_limiti and (k.tarama_sayisi or 0) >= k.tarama_limiti:
        return "limit_doldu"
    return "aktif"


def _sozluk(k: DinamikQr, ayrinti: bool = False) -> Dict[str, Any]:
    a = s.json_yukle(k.alanlar)
    statik = k.tur in s.STATIK_TURLER
    d: Dict[str, Any] = {
        "id": k.id,
        "kod": k.kod,
        "takma_ad": k.takma_ad,
        "ad": k.ad,
        "tur": k.tur,
        "kisa_link": bool(k.kisa_link),
        "statik": statik,
        "alanlar": a,
        "hedef_ozet": s.ozet_hedef(k.tur, a, k.hedef),
        "tasarim": {**s.VARSAYILAN_TASARIM, **s.json_yukle(k.tasarim)},
        "logo_var": bool(k.logo_var),
        "aktif": bool(k.aktif),
        "engelli": bool(k.engelli),
        "durum": durum_hesapla(k),
        "bitis": _an(k.bitis),
        "tarama_limiti": k.tarama_limiti,
        "tarama_sayisi": int(k.tarama_sayisi or 0),
        "son_tarama_at": _an(k.son_tarama_at),
        "kisa_adres": None if statik else s.kisa_adres(k.takma_ad or k.kod),
        "qr_adresi": None if statik else s.kisa_adres(k.kod),
        "hesap_email": k.hesap_email,
        "created_at": _an(k.created_at),
        "updated_at": _an(k.updated_at),
    }
    if ayrinti and k.tur == "wifi":
        d["alanlar"] = {**a, "sifre": k.wifi_sifre or ""}
    return d


async def _kayit(db: AsyncSession, qr_id: int, kapsam: Kapsam) -> DinamikQr:
    sorgu = select(DinamikQr).where(DinamikQr.id == qr_id)
    if not kapsam.yonetici:
        sorgu = sorgu.where(DinamikQr.hesap_email == kapsam.hesap)
    k = (await db.execute(sorgu)).scalars().first()
    if k is None:
        raise _hata(404, "bulunamadi")
    return k


async def _logo(db: AsyncSession, qr_id: int) -> Optional[DinamikQrLogolari]:
    return (await db.execute(select(DinamikQrLogolari).where(DinamikQrLogolari.qr_id == qr_id))).scalars().first()


async def _kayit_siniri(db: AsyncSession, kapsam: Kapsam) -> Optional[int]:
    if kapsam.yonetici:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, kapsam.hesap or "", MODUL, "kayit_siniri")
    return int(deger) if isinstance(deger, int) else VARSAYILAN_KAYIT_SINIRI


async def _kayit_sayisi(db: AsyncSession, hesap: Optional[str]) -> int:
    sorgu = select(func.count(DinamikQr.id))
    sorgu = sorgu.where(DinamikQr.hesap_email.is_(None)) if hesap is None else sorgu.where(DinamikQr.hesap_email == hesap)
    return int((await db.execute(sorgu)).scalar() or 0)


async def _takma_ad_bos_mu(db: AsyncSession, takma: str, haric_id: Optional[int] = None) -> bool:
    sorgu = select(DinamikQr.id).where(or_(DinamikQr.takma_ad == takma, func.lower(DinamikQr.kod) == takma))
    if haric_id is not None:
        sorgu = sorgu.where(DinamikQr.id != haric_id)
    return (await db.execute(sorgu.limit(1))).first() is None


async def _benzersiz_kodlar(db: AsyncSession, adet: int) -> List[str]:
    """`adet` yeni kod: mevcut kodlarla ve (küçük harfle) takma adlarla çakışmaz."""
    sonuc: List[str] = []
    for _ in range(20):
        eksik = adet - len(sonuc)
        if eksik <= 0:
            break
        adaylar = {s.kod_uret() for _ in range(eksik)} - set(sonuc)
        dolu = set(
            (await db.execute(select(DinamikQr.kod).where(DinamikQr.kod.in_(adaylar)))).scalars().all()
        )
        dolu_kucuk = set(
            (await db.execute(select(DinamikQr.takma_ad).where(DinamikQr.takma_ad.in_([a.lower() for a in adaylar]))))
            .scalars()
            .all()
        )
        sonuc.extend(a for a in adaylar if a not in dolu and a.lower() not in dolu_kucuk)
    if len(sonuc) < adet:
        raise _hata(503, "kod_uretilemedi")
    return sonuc[:adet]


def _bitis_coz(ham: Any) -> Optional[datetime]:
    if ham in (None, ""):
        return None
    if not isinstance(ham, str):
        raise s.QrHatasi("tarih_gecersiz", "bitis")
    try:
        an = datetime.fromisoformat(ham.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise s.QrHatasi("tarih_gecersiz", "bitis") from exc
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _limit_coz(ham: Any) -> Optional[int]:
    if ham in (None, "", 0):
        return None
    if isinstance(ham, bool):
        raise s.QrHatasi("sayi_gecersiz", "tarama_limiti")
    try:
        deger = int(ham)
    except (TypeError, ValueError) as exc:
        raise s.QrHatasi("sayi_gecersiz", "tarama_limiti") from exc
    if not 1 <= deger <= TARAMA_LIMITI_EN_COK:
        raise s.QrHatasi("aralik_disi", "tarama_limiti", en_az=1, en_cok=TARAMA_LIMITI_EN_COK)
    return deger


def _ad_coz(ham: Any) -> str:
    deger = " ".join(str(ham or "").split())
    if not deger:
        raise s.QrHatasi("zorunlu", "ad")
    if len(deger) > 120:
        raise s.QrHatasi("cok_uzun", "ad", sinir=120)
    return deger


@dataclass
class Hazir:
    """Doğrulanmış oluşturma girdisi (veritabanına yazılmaya hazır)."""

    ad: str
    tur: str
    alanlar: Dict[str, Any]
    sifre: Optional[str]
    hedef: Optional[str]
    kisa_link: bool
    takma_ad: Optional[str]


def _girdiyi_hazirla(govde: Dict[str, Any]) -> Hazir:
    ad = _ad_coz(govde.get("ad"))
    tur = govde.get("tur")
    alanlar, sifre = s.dogrula(tur, govde.get("alanlar"))
    kisa = bool(govde.get("kisa_link"))
    if kisa and tur != "url":
        raise s.QrHatasi("kisa_link_yalniz_url", "kisa_link")
    return Hazir(
        ad=ad, tur=tur, alanlar=alanlar, sifre=sifre, hedef=s.hedef_uret(tur, alanlar),
        kisa_link=kisa, takma_ad=s.takma_ad_duzelt(govde.get("takma_ad")),
    )


def _hiz(sinir: HizSiniri, kapsam: Kapsam) -> None:
    if not sinir.izin_var_mi(kapsam.kisi or "anonim"):
        raise _hata(429, "cok_hizli")


async def _hedef_hesap(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Optional[str]:
    """Kaydın sahibi: müşteride etkin hesap; yöneticide isteğe bağlı müşteri e-postası (boş = ajans)."""
    if not kapsam.yonetici:
        return kapsam.hesap
    ham = (govde.get("hesap_email") or "").strip().lower()
    if not ham:
        return None
    if not s.eposta_dogru_mu(ham):
        raise s.QrHatasi("eposta_gecersiz", "hesap_email")
    return ham


async def _olustur(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_olusturma_hizi, kapsam)
    try:
        h = _girdiyi_hazirla(govde)
        tasarim = s.tasarim_duzelt(govde.get("tasarim"))
        bitis = _bitis_coz(govde.get("bitis"))
        limit = _limit_coz(govde.get("tarama_limiti"))
        logo = s.logo_hazirla(govde["logo"]) if govde.get("logo") and not h.kisa_link else None
        hesap = await _hedef_hesap(db, kapsam, govde)
    except s.QrHatasi as e:
        raise _qr_hatasi(e)
    sinir = await _kayit_siniri(db, kapsam)
    if sinir is not None and await _kayit_sayisi(db, hesap) >= sinir:
        raise _hata(409, "kayit_siniri", sinir=sinir)
    if h.takma_ad and not await _takma_ad_bos_mu(db, h.takma_ad):
        raise _hata(409, "takma_ad_kullaniliyor", alan="takma_ad")
    kod = (await _benzersiz_kodlar(db, 1))[0]
    k = DinamikQr(
        hesap_email=hesap,
        olusturan_email=kapsam.kisi or None,
        kod=kod,
        takma_ad=h.takma_ad,
        ad=h.ad,
        tur=h.tur,
        kisa_link=h.kisa_link,
        alanlar=json.dumps(h.alanlar, ensure_ascii=False),
        wifi_sifre=h.sifre,
        hedef=h.hedef,
        tasarim=json.dumps(tasarim),
        logo_var=bool(logo),
        aktif=govde.get("aktif") is not False,
        engelli=False,
        bitis=bitis,
        tarama_limiti=limit,
        tarama_sayisi=0,
    )
    db.add(k)
    try:
        await db.flush()
        if logo:
            db.add(DinamikQrLogolari(qr_id=k.id, veri=logo))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "takma_ad_kullaniliyor", alan="takma_ad")
    await db.refresh(k)
    return _sozluk(k, ayrinti=True)


async def _guncelle(db: AsyncSession, kapsam: Kapsam, k: DinamikQr, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_olusturma_hizi, kapsam)
    try:
        if "ad" in govde:
            k.ad = _ad_coz(govde.get("ad"))
        if "tur" in govde or "alanlar" in govde or "kisa_link" in govde:
            tur = govde.get("tur", k.tur)
            girdi = govde.get("alanlar") if "alanlar" in govde else s.json_yukle(k.alanlar)
            girdi = dict(girdi) if isinstance(girdi, dict) else {}
            # Wi-Fi parolası gönderilmediyse kayıtlı olan korunur (arayüz parolayı yeniden istemez).
            if tur == "wifi" and "sifre" not in girdi and k.wifi_sifre:
                girdi["sifre"] = k.wifi_sifre
            alanlar, sifre = s.dogrula(tur, girdi)
            kisa = bool(govde.get("kisa_link", k.kisa_link))
            if kisa and tur != "url":
                raise s.QrHatasi("kisa_link_yalniz_url", "kisa_link")
            k.tur, k.kisa_link = tur, kisa
            k.alanlar = json.dumps(alanlar, ensure_ascii=False)
            k.wifi_sifre = sifre
            k.hedef = s.hedef_uret(tur, alanlar)
        if "takma_ad" in govde:
            takma = s.takma_ad_duzelt(govde.get("takma_ad"))
            if takma and takma != k.takma_ad and not await _takma_ad_bos_mu(db, takma, haric_id=k.id):
                raise _hata(409, "takma_ad_kullaniliyor", alan="takma_ad")
            k.takma_ad = takma
        if "tasarim" in govde:
            k.tasarim = json.dumps(s.tasarim_duzelt(govde.get("tasarim")))
        if "aktif" in govde:
            k.aktif = bool(govde.get("aktif"))
        if "bitis" in govde:
            k.bitis = _bitis_coz(govde.get("bitis"))
        if "tarama_limiti" in govde:
            k.tarama_limiti = _limit_coz(govde.get("tarama_limiti"))
        mevcut_logo = await _logo(db, k.id)
        if govde.get("logo_kaldir") or (k.kisa_link and mevcut_logo is not None):
            if mevcut_logo is not None:
                await db.delete(mevcut_logo)
            k.logo_var = False
        elif govde.get("logo"):
            veri = s.logo_hazirla(govde["logo"])
            if mevcut_logo is not None:
                mevcut_logo.veri = veri
            else:
                db.add(DinamikQrLogolari(qr_id=k.id, veri=veri))
            k.logo_var = True
    except s.QrHatasi as e:
        await db.rollback()
        raise _qr_hatasi(e)
    except HTTPException:
        await db.rollback()
        raise
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "takma_ad_kullaniliyor", alan="takma_ad")
    await db.refresh(k)
    return _sozluk(k, ayrinti=True)


async def _liste(
    db: AsyncSession, kapsam: Kapsam, tur: Optional[str], kisa: Optional[bool], durum: Optional[str],
    ara: Optional[str], hesap: Optional[str], sinir: int, atla: int,
) -> Dict[str, Any]:
    sorgu = select(DinamikQr)
    if not kapsam.yonetici:
        sorgu = sorgu.where(DinamikQr.hesap_email == kapsam.hesap)
    elif hesap == "ajans":
        sorgu = sorgu.where(DinamikQr.hesap_email.is_(None))
    elif hesap:
        sorgu = sorgu.where(DinamikQr.hesap_email == hesap.strip().lower())
    if tur in s.TURLER:
        sorgu = sorgu.where(DinamikQr.tur == tur)
    if kisa is not None:
        sorgu = sorgu.where(DinamikQr.kisa_link.is_(kisa))
    if ara and ara.strip():
        desen = f"%{ara.strip()[:80].lower()}%"
        sorgu = sorgu.where(
            or_(
                func.lower(DinamikQr.ad).like(desen),
                func.lower(DinamikQr.kod).like(desen),
                func.lower(DinamikQr.takma_ad).like(desen),
                func.lower(DinamikQr.hedef).like(desen),
                func.lower(DinamikQr.hesap_email).like(desen),
            )
        )
    satirlar = (await db.execute(sorgu.order_by(desc(DinamikQr.created_at), desc(DinamikQr.id)))).scalars().all()
    simdi = _simdi()
    ogeler = [k for k in satirlar if not durum or durum_hesapla(k, simdi) == durum]
    return {
        "toplam": len(ogeler),
        "items": [_sozluk(k) for k in ogeler[atla : atla + sinir]],
    }


async def _onizleme(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_onizleme_hizi, kapsam)
    mevcut: Optional[DinamikQr] = None
    if govde.get("qr_id") not in (None, ""):
        try:
            mevcut = await _kayit(db, int(govde["qr_id"]), kapsam)
        except (TypeError, ValueError):
            raise _hata(400, "gecersiz", alan="qr_id")
    try:
        tasarim = s.tasarim_duzelt(govde.get("tasarim"))
        tur = govde.get("tur") or (mevcut.tur if mevcut else "url")
        if tur not in s.TURLER:
            raise s.QrHatasi("tur_gecersiz", "tur")
        if tur in s.STATIK_TURLER:
            girdi = dict(govde.get("alanlar") or {})
            if mevcut is not None and tur == "wifi" and "sifre" not in girdi and mevcut.wifi_sifre:
                girdi["sifre"] = mevcut.wifi_sifre
            alanlar, sifre = s.dogrula(tur, girdi)
            icerik = s.statik_icerik(tur, alanlar, sifre)
        else:
            # Dinamik QR'ın içeriği alanlara bağlı değil (`/q/<kod>`); yeni kayıtta aynı
            # uzunlukta örnek kod — kaydedilince QR aynı sürümde (yoğunlukta) kalır.
            icerik = s.kisa_adres(mevcut.kod if mevcut else "Qr7Ornk")
        logo: Optional[str] = None
        if govde.get("logo"):
            logo = s.logo_hazirla(govde["logo"])
        elif mevcut is not None and mevcut.logo_var and not govde.get("logo_kaldir"):
            satir = await _logo(db, mevcut.id)
            logo = satir.veri if satir else None
        gorsel = s.svg_ciz(icerik, tasarim, logo)
    except s.QrHatasi as e:
        raise _qr_hatasi(e)
    return {
        "svg": gorsel.veri.decode("utf-8"),
        "uyarilar": s.tasarim_uyarilari(tasarim),
        "kontrast": s.kontrast_orani(tasarim["on_renk"], tasarim["arka_renk"]),
        "surum": gorsel.surum,
        "hata_duzeltme": gorsel.hata_duzeltme,
    }


async def _gorsel_uret(db: AsyncSession, k: DinamikQr, bicim: str, boyut: Optional[int]) -> s.Gorsel:
    tasarim = {**s.VARSAYILAN_TASARIM, **s.json_yukle(k.tasarim)}
    if boyut is not None:
        tasarim["boyut"] = boyut
    tasarim = s.tasarim_duzelt(tasarim)
    logo = None
    if k.logo_var:
        satir = await _logo(db, k.id)
        logo = satir.veri if satir else None
    icerik = s.qr_icerigi(k.tur, k.kod, s.json_yukle(k.alanlar), k.wifi_sifre)
    return (s.png_ciz if bicim == "png" else s.svg_ciz)(icerik, tasarim, logo)


async def _analiz(db: AsyncSession, k: DinamikQr, gun: int) -> Dict[str, Any]:
    T = DinamikQrTaramalari
    bugun = _simdi().date()
    bas = (bugun - timedelta(days=gun - 1)).isoformat()
    insan = (T.qr_id == k.id, T.bot.is_(False))
    donem = insan + (T.gun >= bas,)

    async def tek(sorgu) -> int:
        return int((await db.execute(sorgu)).scalar() or 0)

    async def dagilim(sutun, adet: int) -> List[Dict[str, Any]]:
        sayi = func.count(T.id)
        satirlar = (
            await db.execute(select(sutun, sayi).where(*donem).group_by(sutun).order_by(desc(sayi)).limit(adet))
        ).all()
        return [{"anahtar": a, "sayi": int(n)} for a, n in satirlar]

    gunluk_ham = {
        g: (int(n), int(t))
        for g, n, t in (
            await db.execute(
                select(T.gun, func.count(T.id), func.count(func.distinct(T.ip_ozeti))).where(*donem).group_by(T.gun)
            )
        ).all()
    }
    gunluk = []
    for i in range(gun):
        g = (bugun - timedelta(days=gun - 1 - i)).isoformat()
        n, t = gunluk_ham.get(g, (0, 0))
        gunluk.append({"gun": g, "tarama": n, "tekil": t})
    refererlar = [r for r in await dagilim(T.referer_alan, 11) if r["anahtar"]][:10]
    return {
        "statik": k.tur in s.STATIK_TURLER,
        "toplam": await tek(select(func.count(T.id)).where(*insan)),
        "tekil": await tek(select(func.count(func.distinct(T.ip_ozeti))).where(*insan)),
        "bot": await tek(select(func.count(T.id)).where(T.qr_id == k.id, T.bot.is_(True))),
        "donem": {
            "gun": gun,
            "tarama": sum(x["tarama"] for x in gunluk),
            "tekil": sum(x["tekil"] for x in gunluk),
        },
        "gunluk": gunluk,
        "ulkeler": await dagilim(T.ulke, 15),
        "cihazlar": await dagilim(T.cihaz, 5),
        "isletim": await dagilim(T.isletim, 8),
        "refererlar": refererlar,
        "son_tarama_at": _an(k.son_tarama_at),
    }


async def _toplu_onizleme(db: AsyncSession, kapsam: Kapsam, dosya: UploadFile) -> Dict[str, Any]:
    _hiz(_toplu_hizi, kapsam)
    bayt = await dosya.read(s.CSV_EN_COK_BAYT + 1)
    try:
        hamlar = s.csv_coz(bayt)
    except s.QrHatasi as e:
        raise _qr_hatasi(e)
    satirlar: List[Dict[str, Any]] = []
    gorulen_takma: set = set()
    for i, ham in enumerate(hamlar, start=2):  # 1. satır başlık
        girdi = s.csv_satiri(ham)
        satir: Dict[str, Any] = {"satir": i, **girdi, "gecerli": True, "hata": None, "hedef_ozet": ""}
        try:
            h = _girdiyi_hazirla(girdi)
            satir["alanlar"] = {**h.alanlar, **({"sifre": h.sifre} if h.tur == "wifi" else {})}
            satir["takma_ad"] = h.takma_ad
            satir["hedef_ozet"] = s.ozet_hedef(h.tur, h.alanlar, h.hedef)
            if h.takma_ad:
                if h.takma_ad in gorulen_takma or not await _takma_ad_bos_mu(db, h.takma_ad):
                    raise s.QrHatasi("takma_ad_kullaniliyor", "takma_ad")
                gorulen_takma.add(h.takma_ad)
        except s.QrHatasi as e:
            satir["gecerli"] = False
            satir["hata"] = e.detay()
        satirlar.append(satir)
    sinir = await _kayit_siniri(db, kapsam)
    kalan = None if sinir is None else max(0, sinir - await _kayit_sayisi(db, kapsam.hesap))
    return {
        "satirlar": satirlar,
        "toplam": len(satirlar),
        "gecerli": sum(1 for x in satirlar if x["gecerli"]),
        "hatali": sum(1 for x in satirlar if not x["gecerli"]),
        "kalan_hak": kalan,
    }


async def _toplu_olustur(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Dict[str, Any]:
    _hiz(_toplu_hizi, kapsam)
    satirlar = govde.get("satirlar")
    if not isinstance(satirlar, list) or not satirlar:
        raise _hata(400, "satir_yok")
    if len(satirlar) > s.CSV_EN_COK_SATIR:
        raise _hata(400, "cok_satir", en_cok=s.CSV_EN_COK_SATIR)
    try:
        tasarim = s.tasarim_duzelt(govde.get("tasarim"))
    except s.QrHatasi as e:
        raise _qr_hatasi(e)
    hesap = kapsam.hesap if not kapsam.yonetici else None
    sinir = await _kayit_siniri(db, kapsam)
    kalan = None if sinir is None else max(0, sinir - await _kayit_sayisi(db, hesap))
    hazirlar: List[Any] = []
    hatalar: List[Dict[str, Any]] = []
    gorulen_takma: set = set()
    for i, girdi in enumerate(satirlar):
        satir_no = girdi.get("satir", i + 1) if isinstance(girdi, dict) else i + 1
        try:
            if not isinstance(girdi, dict):
                raise s.QrHatasi("gecersiz", None)
            h = _girdiyi_hazirla(girdi)
            if h.takma_ad and (h.takma_ad in gorulen_takma or not await _takma_ad_bos_mu(db, h.takma_ad)):
                raise s.QrHatasi("takma_ad_kullaniliyor", "takma_ad")
            if kalan is not None and len(hazirlar) >= kalan:
                raise s.QrHatasi("kayit_siniri", None, sinir=sinir)
        except s.QrHatasi as e:
            hatalar.append({"satir": satir_no, **e.detay()})
            continue
        if h.takma_ad:
            gorulen_takma.add(h.takma_ad)
        hazirlar.append(h)
    if not hazirlar:
        return {"olusturulan": [], "hatalar": hatalar}
    kodlar = await _benzersiz_kodlar(db, len(hazirlar))
    yeni: List[DinamikQr] = []
    for h, kod in zip(hazirlar, kodlar):
        k = DinamikQr(
            hesap_email=hesap, olusturan_email=kapsam.kisi or None, kod=kod, takma_ad=h.takma_ad, ad=h.ad,
            tur=h.tur, kisa_link=h.kisa_link, alanlar=json.dumps(h.alanlar, ensure_ascii=False),
            wifi_sifre=h.sifre, hedef=h.hedef, tasarim=json.dumps(tasarim), logo_var=False, aktif=True,
            engelli=False, tarama_sayisi=0,
        )
        db.add(k)
        yeni.append(k)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _hata(409, "cakisma")
    for k in yeni:
        await db.refresh(k)
    return {"olusturulan": [_sozluk(k) for k in yeni], "hatalar": hatalar}


async def _zip(db: AsyncSession, kapsam: Kapsam, govde: Dict[str, Any]) -> Response:
    _hiz(_toplu_hizi, kapsam)
    idler = govde.get("idler")
    bicim = govde.get("bicim", "png")
    if bicim not in ("png", "svg"):
        raise _hata(400, "bicim_gecersiz")
    if not isinstance(idler, list) or not idler or len(idler) > s.CSV_EN_COK_SATIR:
        raise _hata(400, "secim_gecersiz", en_cok=s.CSV_EN_COK_SATIR)
    try:
        temiz = sorted({int(x) for x in idler})
    except (TypeError, ValueError):
        raise _hata(400, "secim_gecersiz")
    sorgu = select(DinamikQr).where(DinamikQr.id.in_(temiz))
    if not kapsam.yonetici:
        sorgu = sorgu.where(DinamikQr.hesap_email == kapsam.hesap)
    kayitlar = (await db.execute(sorgu)).scalars().all()
    if not kayitlar:
        raise _hata(404, "bulunamadi")
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as arsiv:
        for k in kayitlar:
            try:
                g = await _gorsel_uret(db, k, bicim, None)
            except s.QrHatasi:
                continue
            arsiv.writestr(
                s.dosya_adi(k.kod, k.ad, bicim), g.veri,
                compress_type=zipfile.ZIP_STORED if bicim == "png" else zipfile.ZIP_DEFLATED,
            )
    return Response(
        tampon.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": icerik_konumu(f"qr-kodlari-{bicim}.zip"), "Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# Uçlar — yönetici ve müşteri aynı işleyicileri kendi kapsamlarıyla kullanıyor.
# Sabit yollar `/{qr_id}`'den ÖNCE tanımlı.
# ---------------------------------------------------------------------------
def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sinir = await _kayit_siniri(db, kapsam)
        return {
            "turler": list(s.TURLER),
            "statik_turler": sorted(s.STATIK_TURLER),
            "kisa_adres_tabani": s.kisa_adres(""),
            "tasarim": s.VARSAYILAN_TASARIM,
            "boyut": {"en_az": s.BOYUT_EN_AZ, "en_cok": s.BOYUT_EN_COK},
            "logo_en_cok_kb": s.LOGO_EN_COK_BAYT // 1024,
            "csv_en_cok_satir": s.CSV_EN_COK_SATIR,
            "csv_en_cok_kb": s.CSV_EN_COK_BAYT // 1024,
            "kayit_siniri": sinir,
            "kayit_sayisi": None if kapsam.yonetici else await _kayit_sayisi(db, kapsam.hesap),
            "yonetici": kapsam.yonetici,
        }

    @router.get("")
    async def liste(
        request: Request,
        tur: Optional[str] = Query(None),
        kisa: Optional[bool] = Query(None),
        durum: Optional[str] = Query(None),
        ara: Optional[str] = Query(None),
        hesap: Optional[str] = Query(None),
        sinir: int = Query(200, ge=1, le=LISTE_SINIRI),
        atla: int = Query(0, ge=0),
        db: AsyncSession = Depends(get_db),
    ):
        kapsam = kapsam_al(request)
        return await _liste(db, kapsam, tur, kisa, durum, ara, hesap if kapsam.yonetici else None, sinir, atla)

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _olustur(db, kapsam_al(request), govde)

    @router.post("/onizleme")
    async def onizleme(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _onizleme(db, kapsam_al(request), govde)

    @router.post("/toplu/onizleme")
    async def toplu_onizleme(request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        return await _toplu_onizleme(db, kapsam_al(request), dosya)

    @router.post("/toplu/olustur")
    async def toplu_olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _toplu_olustur(db, kapsam_al(request), govde)

    @router.post("/zip")
    async def zip_indir(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        return await _zip(db, kapsam_al(request), govde)

    @router.get("/{qr_id}")
    async def ayrinti(qr_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        return _sozluk(await _kayit(db, qr_id, kapsam_al(request)), ayrinti=True)

    @router.put("/{qr_id}")
    async def guncelle(
        qr_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)
    ):
        kapsam = kapsam_al(request)
        return await _guncelle(db, kapsam, await _kayit(db, qr_id, kapsam), govde)

    @router.delete("/{qr_id}")
    async def sil(qr_id: int, request: Request, db: AsyncSession = Depends(get_db)):
        k = await _kayit(db, qr_id, kapsam_al(request))
        logo = await _logo(db, k.id)
        # Logo ve kayıt aynı flush'ta: çöp kutusu ikisini birlikte yakalar, birlikte geri getirir.
        if logo is not None:
            await db.delete(logo)
        await db.delete(k)
        await db.commit()
        return {"ok": True}

    @router.get("/{qr_id}/analiz")
    async def analiz(qr_id: int, request: Request, gun: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
        return await _analiz(db, await _kayit(db, qr_id, kapsam_al(request)), gun)

    @router.get("/{qr_id}/gorsel")
    async def gorsel(
        qr_id: int,
        request: Request,
        bicim: str = Query("png"),
        boyut: Optional[int] = Query(None, ge=s.BOYUT_EN_AZ, le=s.BOYUT_EN_COK),
        db: AsyncSession = Depends(get_db),
    ):
        if bicim not in ("png", "svg"):
            raise _hata(400, "bicim_gecersiz")
        k = await _kayit(db, qr_id, kapsam_al(request))
        try:
            g = await _gorsel_uret(db, k, bicim, boyut)
        except s.QrHatasi as e:
            raise _qr_hatasi(e)
        return Response(
            g.veri,
            media_type=g.tur,
            headers={
                "Content-Disposition": icerik_konumu(s.dosya_adi(k.kod, k.ad, bicim)),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


@yonetici_router.post("/{qr_id}/engelle")
async def engelle(qr_id: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    k = await _kayit(db, qr_id, _yonetici_kapsami(request))
    k.engelli = bool(govde.get("engelli", True))
    await db.commit()
    await db.refresh(k)
    return _sozluk(k, ayrinti=True)


# ---------------------------------------------------------------------------
# Herkese açık kısa adres
# ---------------------------------------------------------------------------
_SAYFA_BASLIKLARI = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
}


def _sayfa(tur: str, request: Request, durum: int) -> HTMLResponse:
    dil = s.dil_sec(request.headers.get("accept-language"))
    return HTMLResponse(s.durum_sayfasi(tur, dil), status_code=durum, headers=dict(_SAYFA_BASLIKLARI))


async def _kod_bul(db: AsyncSession, kod: str) -> Optional[DinamikQr]:
    k = (await db.execute(select(DinamikQr).where(DinamikQr.kod == kod))).scalars().first()
    if k is None and s.TAKMA_AD_DESENI.match(kod.lower()):
        k = (await db.execute(select(DinamikQr).where(DinamikQr.takma_ad == kod.lower()))).scalars().first()
    return k


async def _tarama_yaz(veri: Dict[str, Any]) -> None:
    """Yanıt gönderildikten sonra: tek INSERT (+ bot değilse sayaç). Hata yutulur."""
    try:
        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as oturum:
            sayilir = not veri["bot"]
            await oturum.execute(insert(DinamikQrTaramalari).values(**veri))
            if sayilir:
                await oturum.execute(
                    update(DinamikQr)
                    .where(DinamikQr.id == veri["qr_id"])
                    .values(tarama_sayisi=DinamikQr.tarama_sayisi + 1, son_tarama_at=veri["zaman"])
                )
            await oturum.commit()
    except Exception:  # noqa: BLE001 - analitik yönlendirmeyi asla bozmasın
        logger.exception("QR taraması kaydedilemedi")


@acik_router.api_route("/{kod}", methods=["GET", "HEAD"])
async def tara(kod: str, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if not s.KOD_DESENI.match(kod or ""):
        return _sayfa("yok", request, 404)
    k = await _kod_bul(db, kod)
    if k is None or k.tur in s.STATIK_TURLER:
        return _sayfa("yok", request, 404)
    simdi = _simdi()
    if durum_hesapla(k, simdi) != "aktif":
        return _sayfa("pasif", request, 410)

    ua = request.headers.get("user-agent") or ""
    basliklar = {ad: request.headers.get(ad, "") for ad in ("purpose", "sec-purpose", "x-purpose", "x-moz")}
    bot = request.method == "HEAD" or s.bot_mu(ua, basliklar)
    isletim = s.isletim_ailesi(ua)
    alanlar = s.json_yukle(k.alanlar)

    ortak = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff"}
    if k.tur == "vcard":
        yanit: Response = Response(
            s.vcard_uret(alanlar),
            media_type="text/vcard; charset=utf-8",
            headers={**ortak, "Content-Disposition": icerik_konumu(s.dosya_adi(k.kod, k.ad, "vcf"))},
        )
    elif k.tur == "etkinlik":
        try:
            icerik = s.ics_uret(alanlar, k.kod, simdi)
        except (s.QrHatasi, ValueError, KeyError):
            return _sayfa("pasif", request, 410)
        yanit = Response(
            icerik,
            media_type="text/calendar; charset=utf-8",
            headers={**ortak, "Content-Disposition": icerik_konumu(s.dosya_adi(k.kod, k.ad, "ics"))},
        )
    else:
        hedef = s.uygulama_hedefi(alanlar, isletim) if k.tur == "uygulama" else k.hedef
        if not s.guvenli_hedef_mi(hedef):
            logger.warning("QR %s: güvensiz hedef engellendi", k.id)
            return _sayfa("pasif", request, 410)
        yanit = Response(status_code=302, headers={**ortak, "Location": hedef})

    ip = istemci_ip(request)
    gun = simdi.date().isoformat()
    if _tarama_hizi.izin_var_mi(f"{k.id}|{ip_ozeti('qr-hiz|' + ip)}"):
        arka.add_task(
            _tarama_yaz,
            {
                "qr_id": k.id,
                "zaman": simdi,
                "gun": gun,
                "ulke": s.ulke_kodu(request.headers.get("x-mk-ulke") or request.headers.get("cf-ipcountry")),
                "cihaz": s.cihaz_sinifi(ua),
                "isletim": isletim,
                "referer_alan": s.referer_alani(request.headers.get("referer")),
                # Gün tuzun parçası: aynı günün tekil sayımı için yeter, günler arası izleme yok.
                "ip_ozeti": ip_ozeti(f"qr|{gun}|{ip}"),
                "bot": bot,
            },
        )
    return yanit


# Yönetici ve müşteri router'ları ÖNCE; herkese açık kısa adres en sonda.
router = (yonetici_router, musteri_router, acik_router)
