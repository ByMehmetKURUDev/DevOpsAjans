"""Ücretsiz Site Analiz Raporu.

Ziyaretçi alan adını yazıyor, sunucu siteyi dışarıdan inceleyip altı
bölümde puanlıyor (hız, SEO, içerik, teknik, güvenlik, yapay zekâ
görünürlüğü). Motor `services/site_analizi.py`'de; burası kayıt, sınır,
yetki ve aday (lead) akışı.

Akış
----
1. `POST /api/v1/site-analizi` — herkese açık. Yalnızca ÖZET döner: bölüm
   puanları ve bölüm başına en çok 3 bulgu. Tam ayrıntı bilerek yok.
2. `POST /api/v1/site-analizi/{id}/tam-rapor` — e-posta (Faz 4G: onay
   kutusu yok; talep aydınlatmayla işleniyor, isteğe bağlı pazarlama izni
   site ayarı açıksa ayrıca soruluyor). Kayda e-posta yazılıyor, `inquiries` tablosuna aday düşüyor, müşteriye
   rapor bağlantısı e-postayla gidiyor. Jeton yanıtta DÖNMÜYOR: bağlantıya
   yalnızca e-postanın sahibi ulaşıyor, yani e-posta doğrulaması gibi
   çalışıyor.
3. `GET /api/v1/site-analizi/rapor/{jeton}` — tam rapor; 30 gün geçerli.

Sınırlar (yalnızca herkese açık uç): aynı alan adı günde 3, aynı IP saatte
5. Müşteri günde 10, yönetici sınırsız. Sayaç ayrı bir tablo değil, analiz
kayıtlarının kendisi; analiz başlamadan "calisiyor" satırı yazıldığı için
aynı anda gelen istekler de sayılıyor.

Ham IP saklanmıyor; yalnız sha256 özeti.
"""

import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.hesap_baglami import izin_gerekli, musteri_eposta
from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from fastapi import Depends as _Depends
from models.inquiries import Inquiries
from models.site_analyses import Site_analyses
from pydantic import BaseModel
from services import pazarlama_izni
from services import site_analizi as motor
from services.notify import admin_recipients, dispatch, render
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/site-analizi", tags=["site-analizi"])
yonetici_router = APIRouter(prefix="/api/v1/site-analizi/yonetim", tags=["site-analizi"])
# Faz 1F: müşterinin bu modülü kapalıysa 403 `modul_kapali` (yönetici etkilenmez).
# Faz 2E: ekip üyesinde `siteler` izni.
musteri_router = APIRouter(
    prefix="/api/v1/site-analizi/benim",
    tags=["site-analizi"],
    dependencies=[_Depends(izin_gerekli("siteler")), _Depends(modul_gerekli("site_analizi"))],
)

ALAN_GUNLUK_SINIR = 3
IP_SAATLIK_SINIR = 5
MUSTERI_GUNLUK_SINIR = 10
JETON_GUN = 30
#: Aynı analiz için rapor e-postası en fazla bu aralıkla yeniden gider;
#: formu tekrar tekrar gönderen biri bir adrese e-posta yağdıramasın.
YENIDEN_GONDERIM_DK = 10

_EPOSTA = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]{2,}$")

#: Analiz hiç yapılamadığında dönen HTTP kodları.
_HATA_KODLARI = {
    "adres_gecersiz": 400,
    "adres_yasak": 400,
    "cozumlenemedi": 422,
    "ulasilamadi": 422,
    "cok_yonlendirme": 422,
}


# --------------------------------------------------------------------------
# Şemalar
# --------------------------------------------------------------------------
class AnalizGirdisi(BaseModel):
    url: str
    #: Faz 4S — ücretsiz SEO aracının "Sitenin tam analizini al" düğmesi: aracın kısa adı
    #: (ör. "meta-etiketleri"). Bilinmeyen değer yok sayılır; yalnız herkese açık uçta.
    arac: Optional[str] = None


class TamRaporGirdisi(BaseModel):
    eposta: str
    ad: Optional[str] = None
    #: Eski istemci (Faz 4G öncesi zorunlu kutu) gönderebilir; artık şart değil.
    kvkk_onay: bool = False
    #: İsteğe bağlı pazarlama izni — yalnız JSON true sayılır (dönüştürme yok).
    pazarlama_izni: Any = None
    #: Sayfanın dili: izin metninin hangi dilde gösterildiği kayda yazılıyor.
    dil: Optional[str] = None
    #: Faz 5K: ortaklık bağlantısından (`?ref=`) gelen kod — gizli alan; CRM adayına ve ortak atfına işlenir.
    referans_kodu: Optional[str] = None


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini düşürüyor; kayıtların hepsi UTC yazılıyor."""
    if an is None:
        return None
    return an if an.tzinfo else an.replace(tzinfo=timezone.utc)


def _iso(an: Optional[datetime]) -> Optional[str]:
    an = _utc(an)
    return an.isoformat() if an else None


def _hata(kod: int, anahtar: str) -> HTTPException:
    # Ön yüz metni yedi dilde kendisi kuruyor; burası yalnız anahtar döndürüyor.
    return HTTPException(status_code=kod, detail={"kod": anahtar})


# IP yardımcıları ortak modülde (denetim kaydı da aynısını kullanıyor);
# eski adlar testler ve bu dosyanın geri kalanı için korunuyor.
_istemci_ip = istemci_ip
_ip_ozeti = ip_ozeti


def _eposta(kullanici: Any) -> str:
    return (getattr(kullanici, "email", "") or "").strip().lower()


def _yonetici_iste(request: Request) -> str:
    kullanici, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem yönetici yetkisi istiyor")
    return _eposta(kullanici)


def _oturum_iste(request: Request):
    kullanici, yonetici = _yonetici_mi(request)
    eposta = _eposta(kullanici)
    if kullanici is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapmanız gerekiyor")
    if not eposta:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hesabınızda e-posta adresi yok")
    # Faz 2E: analizler etkin hesaba ait (ekip üyesi sahibin hesabında).
    return musteri_eposta(request), yonetici


def _site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


def _json(metin: Optional[str], varsayilan: Any) -> Any:
    if not metin:
        return varsayilan
    try:
        return json.loads(metin)
    except (TypeError, ValueError):
        return varsayilan


async def _say(db: AsyncSession, *kosullar) -> int:
    sonuc = await db.execute(select(func.count(Site_analyses.id)).where(*kosullar))
    return int(sonuc.scalar() or 0)


async def _kayit_bul(db: AsyncSession, analiz_id: int) -> Site_analyses:
    sonuc = await db.execute(select(Site_analyses).where(Site_analyses.id == analiz_id))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise _hata(404, "bulunamadi")
    return kayit


async def _calistir(db: AsyncSession, kayit: Site_analyses) -> Dict[str, Any]:
    """Analizi çalıştırıp kayda yazar. Yapılamazsa kaydı "hata" yapıp fırlatır."""
    try:
        sonuc = await motor.analiz_et(kayit.url)
    except motor.AnalizHatasi as exc:
        kayit.durum = "hata"
        kayit.hata_kodu = exc.kod
        await db.commit()
        raise _hata(_HATA_KODLARI.get(exc.kod, 422), exc.kod)
    except Exception:
        logger.exception("Site analizi beklenmedik biçimde düştü: %s", kayit.alan_adi)
        kayit.durum = "hata"
        kayit.hata_kodu = "beklenmedik"
        await db.commit()
        raise _hata(500, "beklenmedik")

    kayit.durum = "tamam"
    kayit.puan = sonuc["puan"]
    kayit.ozet_json = json.dumps(
        {"bolumler": motor.ozetle(sonuc["bolumler"])}, ensure_ascii=False
    )
    kayit.rapor_json = json.dumps(
        {"bolumler": sonuc["bolumler"], "ayrinti": sonuc["ayrinti"]}, ensure_ascii=False
    )
    await db.commit()
    await db.refresh(kayit)
    return sonuc


def _ozet_yaniti(kayit: Site_analyses) -> Dict[str, Any]:
    ozet = _json(kayit.ozet_json, {})
    return {
        "id": kayit.id,
        "alan_adi": kayit.alan_adi,
        "url": kayit.url,
        "puan": kayit.puan,
        "durum": kayit.durum,
        "bolumler": ozet.get("bolumler", []),
        "tam_rapor_icin_eposta": True,
        "created_at": _iso(kayit.created_at),
    }


def _tam_rapor(kayit: Site_analyses, *, yonetici: bool = False, sahip: bool = False) -> Dict[str, Any]:
    rapor = _json(kayit.rapor_json, {})
    govde: Dict[str, Any] = {
        "id": kayit.id,
        "alan_adi": kayit.alan_adi,
        "url": kayit.url,
        "puan": kayit.puan,
        "durum": kayit.durum,
        "hata_kodu": kayit.hata_kodu,
        "bolumler": rapor.get("bolumler", []),
        "ayrinti": rapor.get("ayrinti", {}),
        "created_at": _iso(kayit.created_at),
        "jeton_son": _iso(kayit.jeton_son),
    }
    if sahip or yonetici:
        govde["jeton"] = kayit.jeton
    if yonetici:
        govde.update(
            {
                "eposta": kayit.eposta,
                "ad": kayit.ad,
                "kvkk_onay": bool(kayit.kvkk_onay),
                "pazarlama_izni": bool(kayit.pazarlama_izni),
                "pazarlama_izni_at": _iso(kayit.pazarlama_izni_at),
                "pazarlama_metin_surumu": kayit.pazarlama_metin_surumu,
                "inquiry_id": kayit.inquiry_id,
                "kaynak": kayit.kaynak,
                "arac": kayit.arac,
                "gonderildi_at": _iso(kayit.gonderildi_at),
            }
        )
    return govde


def _liste_satiri(kayit: Site_analyses, *, yonetici: bool = False) -> Dict[str, Any]:
    satir = {
        "id": kayit.id,
        "alan_adi": kayit.alan_adi,
        "url": kayit.url,
        "puan": kayit.puan,
        "durum": kayit.durum,
        "hata_kodu": kayit.hata_kodu,
        "created_at": _iso(kayit.created_at),
    }
    if yonetici:
        satir.update(
            {
                "eposta": kayit.eposta,
                "ad": kayit.ad,
                "inquiry_id": kayit.inquiry_id,
                "kaynak": kayit.kaynak,
                "arac": kayit.arac,
            }
        )
    return satir


def _yeni_jeton(kayit: Site_analyses) -> None:
    if not kayit.jeton:
        kayit.jeton = secrets.token_urlsafe(16)
    kayit.jeton_son = _simdi() + timedelta(days=JETON_GUN)


# --------------------------------------------------------------------------
# Herkese açık uçlar
# --------------------------------------------------------------------------
@acik_router.post("")
async def analiz_baslat(
    request: Request,
    govde: AnalizGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    try:
        url, _host, alan = motor.adresi_normalize(govde.url)
    except motor.AnalizHatasi as exc:
        raise _hata(400, exc.kod)

    ip_ozeti = _ip_ozeti(_istemci_ip(request))
    simdi = _simdi()
    if await _say(
        db,
        Site_analyses.kaynak == "acik",
        Site_analyses.alan_adi == alan,
        Site_analyses.created_at >= simdi - timedelta(days=1),
    ) >= ALAN_GUNLUK_SINIR:
        raise _hata(429, "sinir_alan")
    if await _say(
        db,
        Site_analyses.kaynak == "acik",
        Site_analyses.ip_ozeti == ip_ozeti,
        Site_analyses.created_at >= simdi - timedelta(hours=1),
    ) >= IP_SAATLIK_SINIR:
        raise _hata(429, "sinir_ip")

    from services.seo_araclari import ARACLAR

    kayit = Site_analyses(
        alan_adi=alan, url=url, ip_ozeti=ip_ozeti, durum="calisiyor",
        kaynak="acik", kvkk_onay=False, created_at=simdi,
        arac=govde.arac if govde.arac in ARACLAR else None,
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)

    await _calistir(db, kayit)
    yanit = _ozet_yaniti(kayit)
    # Faz 4G: tam rapor formunda pazarlama izni kutusu gösterilsin mi (site ayarı).
    yanit["pazarlama_izni_sor"] = await pazarlama_izni.site_analizi_soruyor_mu(db)
    return yanit


@acik_router.post("/{analiz_id}/tam-rapor")
async def tam_rapor_iste(
    analiz_id: int,
    govde: TamRaporGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Tam raporu e-postayla gönderir ve adayı kaydeder.

    Aynı analiz için ikinci çağrı yeni aday açmıyor, aynı jetonu (aynı
    bağlantıyı) kullanıyor. Farklı bir adres verilirse reddediliyor:
    başkasının bıraktığı adrese giden raporu biri kendi adresine
    çeviremesin.
    """
    eposta = (govde.eposta or "").strip().lower()
    if len(eposta) > 254 or not _EPOSTA.match(eposta):
        raise _hata(400, "eposta_gecersiz")
    ad = (govde.ad or "").strip()[:120] or None

    kayit = await _kayit_bul(db, analiz_id)
    if kayit.durum != "tamam":
        raise _hata(409, "analiz_tamamlanmadi")
    if kayit.eposta and kayit.eposta != eposta:
        raise _hata(409, "eposta_farkli")

    simdi = _simdi()
    ilk_kez = kayit.inquiry_id is None
    # Faz 4G: pazarlama izni ayrı ve isteğe bağlı; yalnız site ayarı açıksa kaydedilir.
    pazarlama = pazarlama_izni.izin_verildi_mi(govde.pazarlama_izni) and await pazarlama_izni.site_analizi_soruyor_mu(db)
    surum = pazarlama_izni.surum_etiketi(govde.dil) if pazarlama else None
    if pazarlama:
        kayit.pazarlama_izni = True
        kayit.pazarlama_izni_at = simdi
        kayit.pazarlama_metin_surumu = surum
    son_gonderim = _utc(kayit.gonderildi_at)
    if not ilk_kez and son_gonderim and simdi - son_gonderim < timedelta(minutes=YENIDEN_GONDERIM_DK):
        # Az önce gönderildi; yeniden e-posta atmadan aynı yanıt (izin verildiyse yine kaydedilir).
        if pazarlama:
            aday_id = await pazarlama_izni.bagli_adayi_bul(db, "inquiries", kayit.inquiry_id)
            await pazarlama_izni.adaya_isle(db, aday_id, simdi, f"site_analizi:{kayit.id}", surum)
            await db.commit()
        return {"gonderildi": True}

    kayit.eposta = eposta
    kayit.ad = ad or kayit.ad
    # Eski istemcinin onay işareti korunuyor; yenisi göndermiyor (onay şart değil).
    kayit.kvkk_onay = bool(govde.kvkk_onay or kayit.kvkk_onay)
    _yeni_jeton(kayit)

    ozet = _json(kayit.ozet_json, {}).get("bolumler", [])
    bolum_satiri = ", ".join(
        f"{b.get('anahtar')}: {b.get('puan') if b.get('puan') is not None else '—'}" for b in ozet
    )

    if ilk_kez:
        aday = Inquiries(
            name=ad or eposta.split("@")[0],
            email=eposta,
            subject=f"Site analizi: {kayit.alan_adi}",
            message=(
                f"Ücretsiz site analizi tam raporu istendi.\n"
                f"Site: {kayit.url}\n"
                f"Genel puan: {kayit.puan if kayit.puan is not None else '—'}/100\n"
                f"Bölümler: {bolum_satiri}\n"
                f"Analiz no: {kayit.id}"
                + (f"\nKaynak: ücretsiz SEO aracı ({kayit.arac})" if kayit.arac else "")
            ),
            status="new",
            source="site_analizi",
        )
        db.add(aday)
        await db.flush()
        kayit.inquiry_id = aday.id

    if pazarlama:
        # CRM kancası talebi flush'ta adaya bağladı; izni adayda da göster.
        aday_id = await pazarlama_izni.bagli_adayi_bul(db, "inquiries", kayit.inquiry_id)
        await pazarlama_izni.adaya_isle(db, aday_id, simdi, f"site_analizi:{kayit.id}", surum)

    kayit.gonderildi_at = simdi
    await db.commit()
    await db.refresh(kayit)
    if govde.referans_kodu and kayit.inquiry_id:
        # Faz 5K: kod adaya + ortak atfına (hata yutulur; rapor isteği zaten kaydedildi).
        from services import ortaklik

        await ortaklik.formdan_isle(db, tablo="inquiries", kayit_id=kayit.inquiry_id, eposta=eposta,
                                    ham_kod=str(govde.referans_kodu)[:64])
        await db.refresh(kayit)

    baglanti = f"{_site_adresi()}/rapor/{kayit.jeton}"
    selam = f"Merhaba {ad}," if ad else "Merhaba,"
    try:
        baslik, metin = await render(
            db,
            "site_analizi_rapor",
            f"Tam raporunuz hazır — {kayit.alan_adi}",
            (
                f"{selam}\n\n"
                f"{kayit.alan_adi} için ücretsiz site analizinin tam raporu hazır:\n"
                f"{baglanti}\n\n"
                f"Genel puan: {kayit.puan if kayit.puan is not None else '—'}/100\n"
                f"Bağlantı {JETON_GUN} gün geçerlidir.\n\n"
                f"Your full site analysis report is ready: {baglanti}\n\n"
                f"— By Mehmet KURU Dev"
            ),
            {"alan": kayit.alan_adi, "baglanti": baglanti, "puan": kayit.puan, "ad": ad or ""},
        )
        await dispatch(
            db,
            event_type="site_analizi_rapor",
            title=baslik,
            body=metin,
            recipients=[{"email": eposta, "role": "client"}],
            link=baglanti,
            ref_type="site_analysis",
            ref_id=kayit.id,
        )
        if ilk_kez:
            await dispatch(
                db,
                event_type="site_analizi_aday",
                title=f"Yeni site analizi adayı: {kayit.alan_adi} ({kayit.puan if kayit.puan is not None else '—'}/100)",
                body=(
                    f"E-posta: {eposta}\nAd: {ad or '—'}\nSite: {kayit.url}\n"
                    f"Bölümler: {bolum_satiri}"
                ),
                recipients=await admin_recipients(db),
                link="/admin",
                ref_type="inquiry",
                ref_id=kayit.inquiry_id,
            )
    except Exception as exc:  # bildirim düşse de aday kaydı durmalı
        logger.error("Site analizi bildirimi gönderilemedi: %s", exc)

    # Jeton bilerek dönmüyor: bağlantı yalnız e-postada.
    return {"gonderildi": True}


@acik_router.get("/rapor/{jeton}")
async def rapor_getir(jeton: str, db: AsyncSession = _Depends(get_db)):
    jeton = (jeton or "").strip()
    if not jeton or len(jeton) > 64:
        raise _hata(404, "bulunamadi")
    sonuc = await db.execute(select(Site_analyses).where(Site_analyses.jeton == jeton))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None:
        raise _hata(404, "bulunamadi")
    son = _utc(kayit.jeton_son)
    if son is None or son < _simdi():
        raise _hata(410, "sure_doldu")
    return _tam_rapor(kayit)


# --------------------------------------------------------------------------
# Yönetici uçları
# --------------------------------------------------------------------------
@yonetici_router.get("")
async def yonetim_listesi(
    request: Request,
    sayfa: int = Query(1, ge=1),
    adet: int = Query(20, ge=1, le=100),
    eposta_var: bool = Query(False),
    db: AsyncSession = _Depends(get_db),
):
    _yonetici_iste(request)
    kosullar = []
    if eposta_var:
        kosullar.append(Site_analyses.eposta.is_not(None))
    toplam = await _say(db, *kosullar) if kosullar else int(
        (await db.execute(select(func.count(Site_analyses.id)))).scalar() or 0
    )
    sorgu = select(Site_analyses).order_by(Site_analyses.id.desc())
    if kosullar:
        sorgu = sorgu.where(*kosullar)
    sonuc = await db.execute(sorgu.offset((sayfa - 1) * adet).limit(adet))
    return {
        "items": [_liste_satiri(k, yonetici=True) for k in sonuc.scalars().all()],
        "toplam": toplam,
        "sayfa": sayfa,
        "adet": adet,
    }


@yonetici_router.get("/{analiz_id}")
async def yonetim_raporu(analiz_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    _yonetici_iste(request)
    kayit = await _kayit_bul(db, analiz_id)
    return _tam_rapor(kayit, yonetici=True)


# --------------------------------------------------------------------------
# Müşteri uçları
# --------------------------------------------------------------------------
async def _musteri_gunluk_siniri(db: AsyncSession, eposta: str) -> int:
    """Müşterinin günlük analiz sınırı: `site_analizi` modül ayarı `gunluk_sinir`.

    Panel › Modüller'den müşteri başına değişiyor; okunamazsa 10.
    """
    try:
        from services.moduller import musteri_ayari

        deger = await musteri_ayari(db, eposta, "site_analizi", "gunluk_sinir")
        if deger is not None:
            return int(deger)
    except Exception:  # noqa: BLE001
        logger.debug("Günlük analiz sınırı okunamadı", exc_info=True)
    return MUSTERI_GUNLUK_SINIR


@musteri_router.post("")
async def benim_analizim(
    request: Request,
    govde: AnalizGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    """Oturumlu analiz: tam rapor doğrudan döner, e-posta jetondan."""
    eposta, yonetici = _oturum_iste(request)
    try:
        url, _host, alan = motor.adresi_normalize(govde.url)
    except motor.AnalizHatasi as exc:
        raise _hata(400, exc.kod)

    simdi = _simdi()
    if not yonetici and await _say(
        db,
        Site_analyses.kaynak == "musteri",
        Site_analyses.eposta == eposta,
        Site_analyses.created_at >= simdi - timedelta(days=1),
    ) >= await _musteri_gunluk_siniri(db, eposta):
        raise _hata(429, "sinir_musteri")

    kayit = Site_analyses(
        alan_adi=alan, url=url, durum="calisiyor", eposta=eposta,
        kaynak="yonetici" if yonetici else "musteri", kvkk_onay=False, created_at=simdi,
    )
    _yeni_jeton(kayit)
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)

    await _calistir(db, kayit)
    return _tam_rapor(kayit, sahip=True)


@musteri_router.get("")
async def benim_listem(request: Request, db: AsyncSession = _Depends(get_db)):
    eposta, _ = _oturum_iste(request)
    sonuc = await db.execute(
        select(Site_analyses)
        .where(Site_analyses.eposta == eposta)
        .order_by(Site_analyses.id.desc())
        .limit(100)
    )
    return [_liste_satiri(k) for k in sonuc.scalars().all()]


@musteri_router.get("/{analiz_id}")
async def benim_raporum(analiz_id: int, request: Request, db: AsyncSession = _Depends(get_db)):
    eposta, _ = _oturum_iste(request)
    kayit = await _kayit_bul(db, analiz_id)
    if (kayit.eposta or "").lower() != eposta:
        # Başkasının kaydı "yok" sayılıyor; var olduğu da sızmasın.
        raise _hata(404, "bulunamadi")
    return _tam_rapor(kayit, sahip=True)


# `include_routers_from_package` demet de kabul ediyor.
router = (musteri_router, yonetici_router, acik_router)
