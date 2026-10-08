"""Ücretsiz SEO araçları (Faz 4S) — herkese açık uçlar + yönetici özeti.

`POST /api/v1/seo-araclari/{arac}` — girişsiz; e-posta İSTEMİYOR. Gövde
`{url, ajan?, kelime?}` (ajan yalnız robots.txt, kelime yalnız kelime yoğunluğu
aracında). Motor `services/seo_araclari.py` (site analizinin SSRF korumalı istemcisi).

`POST /api/v1/seo-araclari/{arac}/eposta` — isteğe bağlı "Sonucu e-postayla gönder".
Gövde `{jeton, eposta, ad?, pazarlama_izni?, dil?}`. Sonuç istemciden ALINMIYOR:
çalıştırma yanıtındaki jetonla bellekteki kısa ömürlü kopyası (30 dk, tek kullanım)
bulunuyor. Ziyaretçi CRM'e aday olarak yazılıyor (kaynak `seo_araci`, ayrıntı
`seo_araci:<arac>`); `inquiries`'e yazılmadığı için Gelen kutusuna DÜŞMÜYOR.
Pazarlama izni ayrı ve isteğe bağlı (`services/pazarlama_izni.py`; kutu, site
analiziyle aynı site ayarı açıkken görünüyor). E-posta kanalı yoksa (RESEND_API_KEY
ya da SMTP_HOST tanımlı değil, ya da panelde e-posta kanalı kapalı) çalıştırma
yanıtında `eposta.acik=false` döner, ön yüz seçeneği hiç göstermez; uç 503 verir.

Hız sınırı (kalıcı sayaç, `hiz_sayaclari`; anahtar tuzlu IP özeti / e-posta özeti):
* araç × IP özeti: dakikada 5, günde 50,
* IP özeti (bütün araçlar): dakikada 15,
* bütün site (bütün IP'ler): dakikada 120 — ücretsiz sunucu tek bir kaynaktan kilitlenmesin,
* e-posta: IP özeti başına saatte 5, alıcı adresi başına günde 3 (başkasının kutusu doldurulamasın).
Aşımda 429 + `Retry-After` + `{"kod": "sinir_dakika" | "sinir_gun" | "sinir_eposta"}`.

Gizlilik: sorgulanan adres saklanmıyor ve listelenmiyor ("son analizler" YOK).
Kalıcı olan araç × gün sayaçları (`seo_arac_istatistikleri`) ve — yalnız e-posta
isteyen ziyaretçi için — CRM adayı.

`GET /api/v1/seo-araclari/yonetim/ozet?gun=30` — yalnız yönetici: araç başına
günlük kullanım, e-posta ve aday dönüşümü, araçlardan başlatılan tam analizler
(`site_analyses.arac`) ve bunlardan e-posta bırakılanlar.
"""

import logging
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

from core.database import get_db
from dependencies.kayit_sahipligi import _yonetici_mi
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi import Depends as _Depends
from models.seo_arac_istatistikleri import SeoAracIstatistikleri
from models.site_analyses import Site_analyses
from pydantic import BaseModel
from services import crm, pazarlama_izni
from services import seo_araclari as araclar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

acik_router = APIRouter(prefix="/api/v1/seo-araclari", tags=["seo-araclari"])
yonetici_router = APIRouter(prefix="/api/v1/seo-araclari/yonetim", tags=["seo-araclari"])

ARAC_DAKIKA = 5
ARAC_GUN = 50
IP_DAKIKA = 15
GENEL_DAKIKA = 120
EPOSTA_IP_SAAT = 5
EPOSTA_ALICI_GUN = 3

_arac_dakika = KaliciHizSiniri("seo-arac-dk", ARAC_DAKIKA, 60.0)
_arac_gun = KaliciHizSiniri("seo-arac-gun", ARAC_GUN, 86_400.0)
_ip_dakika = KaliciHizSiniri("seo-arac-ip-dk", IP_DAKIKA, 60.0)
_genel_dakika = KaliciHizSiniri("seo-arac-genel", GENEL_DAKIKA, 60.0)
_eposta_ip = KaliciHizSiniri("seo-arac-eposta-ip", EPOSTA_IP_SAAT, 3600.0)
_eposta_alici = KaliciHizSiniri("seo-arac-eposta-alici", EPOSTA_ALICI_GUN, 86_400.0)

#: Bal küpü: insan görmüyor, bot dolduruyor (modül vitriniyle aynı ad).
BAL_KUPU = "web_sitesi"

#: Analiz hiç yapılamadığında dönen HTTP kodları (site analiziyle aynı anahtarlar).
_HATA_KODLARI = {
    "adres_gecersiz": 400,
    "adres_yasak": 400,
    "ajan_gecersiz": 400,
    "kelime_gecersiz": 400,
    "cozumlenemedi": 422,
    "ulasilamadi": 422,
    "cok_yonlendirme": 422,
    "zaman_asimi": 422,
}

#: `ENVIRONMENT=test` (yalnız üretim dışı) sahte kanalının kutusu — testler okuyor.
_SAHTE_KUTU: Deque[Dict[str, str]] = deque(maxlen=50)


def sahte_kutu() -> List[Dict[str, str]]:
    return list(_SAHTE_KUTU)


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for s in (_arac_dakika, _arac_gun, _ip_dakika, _genel_dakika, _eposta_ip, _eposta_alici):
        s.temizle()
    _SAHTE_KUTU.clear()
    araclar.onbellek.temizle()


class AracGirdisi(BaseModel):
    url: str
    #: robots.txt aracı: kullanıcı ajanı (ör. Googlebot). Diğer araçlar yok sayar.
    ajan: Optional[str] = None
    #: Kelime yoğunluğu aracı: isteğe bağlı hedef anahtar kelime. Diğer araçlar yok sayar.
    kelime: Optional[str] = None


class EpostaGirdisi(BaseModel):
    jeton: str
    eposta: str
    ad: Optional[str] = None
    #: Yalnız JSON `true` izin sayılır (`pazarlama_izni.izin_verildi_mi`).
    pazarlama_izni: Any = None
    dil: Optional[str] = None
    web_sitesi: Optional[str] = None


def _hata(kod: int, anahtar: str, basliklar: Optional[Dict[str, str]] = None) -> HTTPException:
    return HTTPException(status_code=kod, detail={"kod": anahtar}, headers=basliklar)


def _bugun() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _env(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


async def eposta_kanali(db: AsyncSession) -> str:
    """Sonuç e-postası hangi kanaldan gider: "resend" | "smtp" | "sahte" | "" (kapalı).

    Panelde e-posta kanalı kapatıldıysa (`notify_email`) seçenek de kapalı.
    "sahte" yalnız `ENVIRONMENT=test` iken (üretimde ve Render'da asla).
    """
    from services import eposta_gonderim, notify

    try:
        if not notify._acik(await notify._ayar(db, "notify_email", "1")):
            return ""
    except Exception:  # noqa: BLE001 - ayar okunamazsa varsayılan: açık
        pass
    if _env("RESEND_API_KEY"):
        return "resend"
    if _env("SMTP_HOST"):
        return "smtp"
    if eposta_gonderim.sahte_mod():
        return "sahte"
    return ""


async def _eposta_gonder(kanal: str, alici: str, icerik: Dict[str, str]) -> str:
    """Bildirim kaydı (`notifications`) YAZMADAN doğrudan gönderir: sonuç sunucuda kalmasın."""
    if kanal == "sahte":
        _SAHTE_KUTU.append({"alici": alici, **icerik})
        return "sent"
    from services import notify

    durum, _ayrinti = await notify._eposta_gonder(alici, icerik["konu"], icerik["metin"], {"html": icerik["html"]})
    return durum


async def istatistik_artir(arac: str, *, sayi: int = 0, hata: int = 0, eposta: int = 0, aday: int = 0) -> None:
    """Araç × gün sayaçlarını tek kısa işlemde artırır (isteğin oturumundan bağımsız; hata yutulur)."""
    from core.database import db_manager

    motor = db_manager.engine
    if motor is None:
        return
    if motor.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    t = SeoAracIstatistikleri.__table__
    ifade = (
        insert(t)
        .values(arac=arac, gun=_bugun(), sayi=sayi, hata=hata, eposta=eposta, aday=aday)
        .on_conflict_do_update(
            index_elements=[t.c.arac, t.c.gun],
            set_={
                "sayi": t.c.sayi + sayi,
                "hata": t.c.hata + hata,
                "eposta": t.c.eposta + eposta,
                "aday": t.c.aday + aday,
            },
        )
    )
    try:
        async with motor.begin() as baglanti:
            await baglanti.execute(ifade)
    except Exception as exc:  # noqa: BLE001 - sayaç yazılamadı diye araç düşmesin
        logger.warning("SEO aracı sayacı yazılamadı: %s", type(exc).__name__)


# --------------------------------------------------------------------------
# Herkese açık
# --------------------------------------------------------------------------
@acik_router.post("/{arac}")
async def arac_calistir(
    arac: str,
    request: Request,
    govde: AracGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    if arac not in araclar.ARACLAR:
        raise _hata(404, "arac_yok")
    secenek = {"ajan": govde.ajan, "kelime": govde.kelime}
    try:
        # Biçim hatası sınırdan önce: yanlış yazılan adres hakkı yemesin.
        araclar.motor.adresi_normalize(govde.url)
        araclar.secenekleri_dogrula(arac, secenek)
    except araclar.AnalizHatasi as exc:
        raise _hata(400, exc.kod)

    ip = ip_ozeti(istemci_ip(request))
    anahtar = f"{arac}|{ip}"
    if not await izin_ver((_genel_dakika, "genel"), (_ip_dakika, ip), (_arac_dakika, anahtar)):
        raise _hata(429, "sinir_dakika", {"Retry-After": "60"})
    if not await izin_ver((_arac_gun, anahtar)):
        raise _hata(429, "sinir_gun", {"Retry-After": "3600"})

    try:
        sonuc = await araclar.calistir(arac, govde.url, secenek)
    except araclar.AnalizHatasi as exc:
        await istatistik_artir(arac, sayi=1, hata=1)
        raise _hata(_HATA_KODLARI.get(exc.kod, 422), exc.kod)
    except Exception:
        # Adres bilerek günlüğe yazılmıyor (gizlilik); yalnız araç ve hata türü.
        logger.exception("SEO aracı beklenmedik biçimde düştü: %s", arac)
        await istatistik_artir(arac, sayi=1, hata=1)
        raise _hata(500, "beklenmedik")
    await istatistik_artir(arac, sayi=1)

    # "Sonucu e-postayla gönder": kanal yoksa seçenek hiç gösterilmez ve sonuç önbelleğe de girmez.
    kanal = await eposta_kanali(db)
    sonuc["eposta"] = {
        "acik": bool(kanal),
        "jeton": araclar.onbellek.koy(arac, dict(sonuc)) if kanal else None,
        "pazarlama_izni_sor": bool(kanal) and await pazarlama_izni.site_analizi_soruyor_mu(db),
    }
    return sonuc


@acik_router.post("/{arac}/eposta")
async def sonucu_epostala(
    arac: str,
    request: Request,
    govde: EpostaGirdisi = Body(...),
    db: AsyncSession = _Depends(get_db),
):
    if arac not in araclar.ARACLAR:
        raise _hata(404, "arac_yok")
    # Bal küpü: bot "başarılı" görsün, hiçbir şey gönderilmesin ve kaydedilmesin.
    if (govde.web_sitesi or "").strip():
        logger.info("SEO aracı e-postası: bal küpü dolu, yok sayıldı")
        return {"gonderildi": True}
    kanal = await eposta_kanali(db)
    if not kanal:
        raise _hata(503, "eposta_kapali")
    eposta = crm.eposta_duzelt(govde.eposta)
    if len(eposta) > 254 or not crm.eposta_gecerli(eposta):
        raise _hata(400, "eposta_gecersiz")
    ad = " ".join((govde.ad or "").split())[:120] or None

    ip = ip_ozeti(istemci_ip(request))
    if not await izin_ver((_eposta_ip, ip), (_eposta_alici, eposta)):
        raise _hata(429, "sinir_eposta", {"Retry-After": "3600"})

    sonuc = araclar.onbellek.al(govde.jeton, arac)
    if sonuc is None:
        raise _hata(410, "sonuc_suresi_doldu")

    dil = araclar.dil_sec(govde.dil)
    icerik = araclar.eposta_icerigi(sonuc, dil, ad)
    if await _eposta_gonder(kanal, eposta, icerik) != "sent":
        # Adres ve alıcı günlüğe yazılmıyor; jeton silinmiyor (yeniden denenebilir).
        logger.warning("SEO aracı sonuç e-postası gönderilemedi (%s, %s)", arac, kanal)
        raise _hata(502, "eposta_gonderilemedi")
    araclar.onbellek.sil(govde.jeton)

    # CRM adayı (yalnız CRM — `inquiries`'e yazılmıyor, Gelen kutusuna düşmüyor).
    yeni = False
    try:
        alan = araclar.alan_adi(sonuc)
        girdi = crm.TalepGirdisi(
            tablo=None,
            kayit_id=None,
            ad=ad,
            email=eposta,
            konu=f"Ücretsiz SEO aracı: {araclar.arac_adi(arac, 'tr')} — {alan}",
            mesaj=araclar.crm_ozeti(sonuc),
            kaynak="seo_araci",
            kaynak_ham=f"seo_araci:{arac}",
            bildirim=True,
            ek_veri={"arac": arac},
        )
        islem = await crm.kayit_isle(db, girdi)
        aday_id = islem["aday_id"] if islem else None
        yeni = bool(islem and islem.get("yeni"))
        # Faz 4G: pazarlama izni ayrı ve isteğe bağlı; yalnız site ayarı açıksa ve kutu işaretliyse.
        if (
            aday_id
            and pazarlama_izni.izin_verildi_mi(govde.pazarlama_izni)
            and await pazarlama_izni.site_analizi_soruyor_mu(db)
        ):
            await pazarlama_izni.adaya_isle(
                db, aday_id, datetime.now(timezone.utc), f"seo_araci:{arac}", pazarlama_izni.surum_etiketi(dil)
            )
        await db.commit()
    except Exception:  # noqa: BLE001 - e-posta gitti; aday yazılamadıysa ziyaretçiye hata gösterme
        logger.exception("SEO aracı: CRM adayı yazılamadı (%s)", arac)
        await db.rollback()
    await istatistik_artir(arac, eposta=1, aday=1 if yeni else 0)
    return {"gonderildi": True}


# --------------------------------------------------------------------------
# Yönetici
# --------------------------------------------------------------------------
@yonetici_router.get("/ozet")
async def yonetim_ozeti(
    request: Request,
    gun: int = Query(30, ge=1, le=365),
    db: AsyncSession = _Depends(get_db),
):
    _kullanici, yonetici = _yonetici_mi(request)
    if not yonetici:
        raise HTTPException(status_code=403, detail="Bu işlem yönetici yetkisi istiyor")
    simdi = datetime.now(timezone.utc)
    gunler = [(simdi - timedelta(days=gun - 1 - i)).strftime("%Y-%m-%d") for i in range(gun)]
    sira = {g: i for i, g in enumerate(gunler)}
    bas_an = simdi - timedelta(days=gun)

    satirlar: Dict[str, Dict[str, Any]] = {
        a: {
            "arac": a, "kullanim": 0, "hata": 0, "eposta": 0, "aday": 0,
            "tam_analiz": 0, "tam_analiz_aday": 0, "gunluk": [0] * gun,
        }
        for a in araclar.ARACLAR
    }
    sayaclar = await db.execute(
        select(
            SeoAracIstatistikleri.arac,
            SeoAracIstatistikleri.gun,
            SeoAracIstatistikleri.sayi,
            SeoAracIstatistikleri.hata,
            SeoAracIstatistikleri.eposta,
            SeoAracIstatistikleri.aday,
        ).where(SeoAracIstatistikleri.gun >= gunler[0])
    )
    for a, g, sayi, hata, eposta, aday in sayaclar.all():
        s = satirlar.get(a)
        if s is None:
            continue
        s["kullanim"] += int(sayi or 0)
        s["hata"] += int(hata or 0)
        s["eposta"] += int(eposta or 0)
        s["aday"] += int(aday or 0)
        if g in sira:
            s["gunluk"][sira[g]] += int(sayi or 0)

    # "Sitenin tam analizini al" → site analizi (araç adıyla) ve bunlardan e-posta bırakılanlar.
    tam = await db.execute(
        select(Site_analyses.arac, Site_analyses.inquiry_id).where(
            Site_analyses.arac.is_not(None), Site_analyses.created_at >= bas_an
        )
    )
    for a, inquiry_id in tam.all():
        s = satirlar.get(a)
        if s is None:
            continue
        s["tam_analiz"] += 1
        if inquiry_id is not None:
            s["tam_analiz_aday"] += 1

    liste = list(satirlar.values())

    def toplam(alan: str) -> int:
        return sum(int(s[alan]) for s in liste)

    return {
        "gun": gun,
        "gunler": gunler,
        "araclar": liste,
        "toplam": {
            alan: toplam(alan) for alan in ("kullanim", "hata", "eposta", "aday", "tam_analiz", "tam_analiz_aday")
        },
        "gunluk": [sum(s["gunluk"][i] for s in liste) for i in range(gun)],
    }


router = (yonetici_router, acik_router)
