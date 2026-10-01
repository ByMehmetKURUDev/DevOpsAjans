"""Faz 2H — müşteri siteleri için teknik SEO + Core Web Vitals izleme (modül #31).

Ölçüm motoru YOK: her ölçüm `services/site_analizi.analiz_et` (ücretsiz site
analizinin aynısı — SSRF korumalı istemci, PageSpeed, 45 sn tavan). Burada
yalnız şu işler var:

* **Seçim** — site başına `site_izleme.seo_tarama_gun` günde bir (boş = 7,
  0 = kapalı). Zamanlı görev her turda en çok `TUR_SINIRI` (3) site ölçüyor,
  en uzun süredir ölçülmeyenden (hiç ölçülmemiş önce) başlayarak. Üç ölçüm
  PARALEL koşuyor (her biri ≤45 sn): tur süresi tek analize yakın kalıyor,
  GitHub Actions'ın 60 sn'lik isteği ve 10 dk'lık kilit aşılmıyor; PageSpeed
  kotası turda en çok 6 çağrı.
* **Kayıt** — `site_seo_gecmisi`: genel/bölüm puanları, mobil/masaüstü,
  LCP/CLS/TBT ve bulgu KODLARI (+seviye, bölüm, sayısal/kısa değer). Ham sayfa
  içeriği yok. PageSpeed başarısızsa hız bölümü "ölçülemedi" (null) olur, diğer
  bölümler ve genel puan yine yazılır (motorun davranışı). Site hiç açılamazsa
  satır `durum=hata` + kısa kod: sıradaki tur aynı siteye takılıp kalmasın.
* **Uyarı** (`seo_dususu`) — bir önceki BAŞARILI ölçüme göre:
  - karşılaştırılabilir puan 10+ düştüyse (iki ölçümde de ölçülmüş bölümlerin
    ortalaması: PageSpeed bir kez düşünce sahte "düşüş" olmasın),
  - yeni bir KRİTİK bulgu çıktıysa (noindex, robots engeli, sitemap yok, SSL
    geçersiz/süresi geçmiş, HTTPS yok, ana sayfa hata kodu),
  - kırık iç bağlantı sayısı arttıysa.
  İlk ölçüm taban: kıyas yok, uyarı yok. Aynı (site, sorun) için 7 günde bir
  (`site_seo_uyarilari`). Yöneticiye her zaman; müşteriye `sitem` modülü
  açıksa — hesap üyelerinden `siteler` izni olanlara `dispatch` kendisi
  genişletiyor (`OLAY_IZNI`).
* **Elle tarama** — müşteri site başına 24 saatte 1 (`kaynak=elle`), yönetici
  sınırsız. Ölçüm sürerken aynı siteye ikinci tarama 409 (çift tıklama /
  zamanlı turla çakışma): önce `durum=calisiyor` satırı açılıyor.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.client_sites import Client_sites
from models.site_izleme import SiteIzleme
from models.site_seo import SiteSeoGecmisi, SiteSeoUyarisi
from services import site_analizi as motor
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TR = timezone(timedelta(hours=3))

VARSAYILAN_GUN = 7
EN_COK_GUN = 90
TUR_SINIRI = 3
DUSUS_ESIGI = 10
UYARI_ARALIGI = timedelta(days=7)
ELLE_ARALIK = timedelta(hours=24)
#: Bundan eski "calisiyor" satırı yarıda kalmış sayılır (süreç ölçüm ortasında öldü).
CALISIYOR_TAVAN = timedelta(minutes=10)
#: Cron kayması: "7 günde bir" 6 gün 23 saatte de dolmuş sayılsın.
ZAMAN_PAYI = timedelta(hours=1)
#: Tek ölçümün tavanı (motorun kendi 45 sn'sine pay).
OLCUM_TAVANI = motor.TOPLAM_TAVAN + 15
GECMIS_EN_COK_SATIR = 400
ONEMLI_BULGU = 5
BULGU_TAVANI = 80
DEGER_UZUNLUK = 60
SITE_SINIRI = 500

TAMAM, HATA, CALISIYOR = "tamam", "hata", "calisiyor"
KAYNAKLAR = ("zamanli", "elle", "yonetici")
OLAY = "seo_dususu"

#: Yeni çıktığında uyarı gönderilen bulgular (site arama motorundan düşebilir
#: ya da ziyaretçi uyarı görür). Kırık bağlantı ayrıca: sayı arttıysa.
KRITIK_KODLAR = frozenset({
    "noindex", "robots_engelli", "sitemap_yok", "ssl_gecersiz",
    "ssl_suresi_gecmis", "https_yok", "ana_sayfa_durum",
})
KRITIK_METINLERI: Dict[str, Tuple[str, str]] = {
    "noindex": ("Ana sayfa arama motorlarına kapatılmış (noindex).", "The home page is hidden from search engines (noindex)."),
    "robots_engelli": ("robots.txt siteyi arama motorlarına kapatıyor.", "robots.txt blocks search engines from the whole site."),
    "sitemap_yok": ("Site haritası (sitemap.xml) bulunamadı.", "No sitemap (sitemap.xml) was found."),
    "ssl_gecersiz": ("SSL sertifikası geçersiz.", "The SSL certificate is invalid."),
    "ssl_suresi_gecmis": ("SSL sertifikasının süresi dolmuş.", "The SSL certificate has expired."),
    "https_yok": ("Site HTTPS kullanmıyor.", "The site is not served over HTTPS."),
    "ana_sayfa_durum": ("Ana sayfa hata kodu döndürüyor.", "The home page returns an error status."),
}
SEVIYE_SIRASI = {"hata": 0, "uyari": 1, "bilgi": 2, "iyi": 3}

MUSTERI_BAGLANTISI = "/client?sekme=sitem"
YONETICI_BAGLANTISI = "/admin"


class SeoHatasi(Exception):
    """Uca çevrilecek hata: HTTP durumu + kod (+ isteğe bağlı ek alanlar)."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek


# --------------------------------------------------------------------------
# Küçük yardımcılar
# --------------------------------------------------------------------------
def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def _tam(deger: Any) -> Optional[int]:
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        return None
    return int(round(float(deger)))


def _json(metin: Optional[str], varsayilan: Any) -> Any:
    if not metin:
        return varsayilan
    try:
        v = json.loads(metin)
    except (ValueError, TypeError):
        return varsayilan
    return v if isinstance(v, type(varsayilan)) else varsayilan


def tarama_gunu(iz: Optional[SiteIzleme]) -> int:
    """Site ayarı (gün). Boş → 7; 0 → otomatik tarama kapalı."""
    deger = getattr(iz, "seo_tarama_gun", None) if iz is not None else None
    if deger is None:
        return VARSAYILAN_GUN
    try:
        return max(0, min(EN_COK_GUN, int(deger)))
    except (TypeError, ValueError):
        return VARSAYILAN_GUN


# --------------------------------------------------------------------------
# Saf: motor sonucunu özetle, kıyasla
# --------------------------------------------------------------------------
def sonuc_ozeti(sonuc: Dict[str, Any]) -> Dict[str, Any]:
    """`analiz_et` çıktısından saklanacak özet. Sayfa metni/adres YOK."""
    bolumler = sonuc.get("bolumler") or []
    hiz = (sonuc.get("ayrinti") or {}).get("hiz") or {}
    mobil = hiz.get("mobil") or None
    masaustu = hiz.get("masaustu") or None
    # Motorun hız bölümüyle aynı kaynak: mobil, yoksa masaüstü.
    cwv = mobil or masaustu or {}
    bulgular: List[Dict[str, Any]] = []
    for b in bolumler:
        for f in b.get("bulgular") or []:
            satir: Dict[str, Any] = {"kod": str(f.get("kod") or ""), "seviye": str(f.get("seviye") or ""), "bolum": b.get("anahtar")}
            d = f.get("deger")
            if isinstance(d, (int, float)) and not isinstance(d, bool):
                satir["deger"] = d
            elif isinstance(d, str) and len(d) <= DEGER_UZUNLUK:
                satir["deger"] = d
            bulgular.append(satir)
    cls = cwv.get("cls")
    return {
        "genel_puan": _tam(sonuc.get("puan")),
        "bolum_puanlari": {b["anahtar"]: _tam(b.get("puan")) for b in bolumler if b.get("anahtar")},
        "mobil_puan": _tam(mobil.get("puan")) if mobil else None,
        "masaustu_puan": _tam(masaustu.get("puan")) if masaustu else None,
        "lcp_ms": _tam(cwv.get("lcp_ms")),
        "cls": round(float(cls), 3) if isinstance(cls, (int, float)) and not isinstance(cls, bool) else None,
        "tbt_ms": _tam(cwv.get("tbt_ms")),
        "bulgu_ozeti": bulgular[:BULGU_TAVANI],
    }


def karsilastirma(onceki: Dict[str, Any], yeni: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """İki ölçümde de puanı olan bölümlerin ortalamaları (önceki, yeni)."""
    ortak = [k for k, v in (yeni or {}).items() if v is not None and (onceki or {}).get(k) is not None]
    if not ortak:
        return None
    return (
        sum(float(onceki[k]) for k in ortak) / len(ortak),
        sum(float(yeni[k]) for k in ortak) / len(ortak),
    )


def kirik_sayisi(bulgular: Iterable[Dict[str, Any]]) -> int:
    for b in bulgular or []:
        if b.get("kod") == "kirik_baglanti":
            return _tam(b.get("deger")) or 0
    return 0


def kritikler(bulgular: Iterable[Dict[str, Any]]) -> set:
    return {b.get("kod") for b in bulgular or [] if b.get("kod") in KRITIK_KODLAR}


def sorunlari_bul(onceki: Optional[Dict[str, Any]], yeni: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Önceki başarılı ölçüme göre uyarılacak sorunlar. İlk ölçümde boş."""
    if not onceki:
        return []
    sorunlar: List[Dict[str, Any]] = []
    kiyas = karsilastirma(onceki.get("bolum_puanlari") or {}, yeni.get("bolum_puanlari") or {})
    if kiyas and kiyas[0] - kiyas[1] >= DUSUS_ESIGI:
        sorunlar.append({"sorun": "puan_dususu", "onceki": int(round(kiyas[0])), "simdiki": int(round(kiyas[1]))})
    for kod in sorted(kritikler(yeni.get("bulgu_ozeti")) - kritikler(onceki.get("bulgu_ozeti"))):
        sorunlar.append({"sorun": f"kritik:{kod}", "kod": kod})
    a, b = kirik_sayisi(onceki.get("bulgu_ozeti")), kirik_sayisi(yeni.get("bulgu_ozeti"))
    if b > a:
        sorunlar.append({"sorun": "kirik_baglanti", "onceki": a, "simdiki": b})
    return sorunlar


def onemli_bulgular(bulgular: Sequence[Dict[str, Any]], n: int = ONEMLI_BULGU) -> List[Dict[str, Any]]:
    """"İyi" olmayanlar; kritikler önce, sonra hata > uyarı > bilgi."""
    adaylar = [dict(b, kritik=b.get("kod") in KRITIK_KODLAR) for b in bulgular or [] if b.get("seviye") != "iyi"]
    adaylar.sort(key=lambda b: (not b["kritik"], SEVIYE_SIRASI.get(b.get("seviye") or "", 9)))
    return adaylar[:n]


# --------------------------------------------------------------------------
# Satır → sözlük
# --------------------------------------------------------------------------
def _olcum_verisi(s: SiteSeoGecmisi) -> Dict[str, Any]:
    return {
        "bolum_puanlari": _json(s.bolum_puanlari, {}),
        "bulgu_ozeti": _json(s.bulgu_ozeti, []),
    }


def kisa_sozluk(s: SiteSeoGecmisi) -> Dict[str, Any]:
    return {
        "id": s.id,
        "olcum_at": iso(s.olcum_at),
        "kaynak": s.kaynak,
        "durum": s.durum,
        "hata_kodu": s.hata_kodu,
        "genel_puan": s.genel_puan,
        "mobil_puan": s.mobil_puan,
        "masaustu_puan": s.masaustu_puan,
        "lcp_ms": s.lcp_ms,
        "cls": s.cls,
        "tbt_ms": s.tbt_ms,
    }


def tam_sozluk(s: SiteSeoGecmisi) -> Dict[str, Any]:
    veri = _olcum_verisi(s)
    bulgular = veri["bulgu_ozeti"]
    return {
        **kisa_sozluk(s),
        "bolum_puanlari": veri["bolum_puanlari"],
        "onemli_bulgular": onemli_bulgular(bulgular),
        "kritik": sorted(kritikler(bulgular)),
        "kirik_baglanti": kirik_sayisi(bulgular),
        "bulgu_sayisi": {sev: sum(1 for b in bulgular if b.get("seviye") == sev) for sev in ("hata", "uyari", "bilgi")},
    }


# --------------------------------------------------------------------------
# Sorgular
# --------------------------------------------------------------------------
async def _son_tamamlar(db: AsyncSession, site_id: int, adet: int = 2, haric: Optional[int] = None) -> List[SiteSeoGecmisi]:
    sorgu = select(SiteSeoGecmisi).where(SiteSeoGecmisi.site_id == site_id, SiteSeoGecmisi.durum == TAMAM)
    if haric is not None:
        sorgu = sorgu.where(SiteSeoGecmisi.id != haric)
    sorgu = sorgu.order_by(SiteSeoGecmisi.olcum_at.desc(), SiteSeoGecmisi.id.desc()).limit(adet)
    return list((await db.execute(sorgu)).scalars().all())


async def _son_deneme(db: AsyncSession, site_id: int) -> Optional[SiteSeoGecmisi]:
    return (
        await db.execute(
            select(SiteSeoGecmisi)
            .where(SiteSeoGecmisi.site_id == site_id)
            .order_by(SiteSeoGecmisi.olcum_at.desc(), SiteSeoGecmisi.id.desc())
            .limit(1)
        )
    ).scalars().first()


def _suruyor_mu(s: Optional[SiteSeoGecmisi], an: Optional[datetime] = None) -> bool:
    if s is None or s.durum != CALISIYOR:
        return False
    return (an or simdi()) - (utc(s.olcum_at) or simdi()) < CALISIYOR_TAVAN


async def _elle_durumu(db: AsyncSession, site_id: int, an: Optional[datetime] = None) -> Dict[str, Any]:
    """Müşterinin elle taraması: 24 saatte 1. {kalan, sonraki_at}."""
    an = an or simdi()
    son = (
        await db.execute(
            select(func.max(SiteSeoGecmisi.olcum_at)).where(
                SiteSeoGecmisi.site_id == site_id,
                SiteSeoGecmisi.kaynak == "elle",
                SiteSeoGecmisi.olcum_at >= an - ELLE_ARALIK,
            )
        )
    ).scalar()
    if son is None:
        return {"kalan": 1, "sonraki_at": None}
    return {"kalan": 0, "sonraki_at": iso(utc(son) + ELLE_ARALIK)}


async def yarida_kalanlari_kapat(db: AsyncSession) -> int:
    """Süreç ölçüm ortasında öldüyse "calisiyor" satırı hata olarak kapanır."""
    sonuc = await db.execute(
        update(SiteSeoGecmisi)
        .where(SiteSeoGecmisi.durum == CALISIYOR, SiteSeoGecmisi.olcum_at < simdi() - CALISIYOR_TAVAN)
        .values(durum=HATA, hata_kodu="yarida_kaldi")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(sonuc.rowcount or 0)


async def tarama_sirasi(db: AsyncSession, an: Optional[datetime] = None) -> List[Tuple[Client_sites, Optional[datetime]]]:
    """Zamanı gelen siteler, en uzun süredir ölçülmeyen önce (hiç ölçülmemiş en önde).

    Adresi olmayan ve durumu `bitti` olan siteler; ayarı 0 (kapalı) olanlar atlanıyor.
    """
    from services.site_izleme import izlemeler_sozlugu

    an = an or simdi()
    siteler = list(
        (
            await db.execute(
                select(Client_sites)
                .where(
                    Client_sites.adres.isnot(None),
                    Client_sites.adres != "",
                    func.coalesce(Client_sites.durum, "aktif") != "bitti",
                )
                .order_by(Client_sites.id)
                .limit(SITE_SINIRI * 2)
            )
        ).scalars().all()
    )
    if not siteler:
        return []
    idler = [s.id for s in siteler]
    izlemeler = await izlemeler_sozlugu(db, idler)
    # Son deneme (başarılı ya da hata); yarıda kalmış eski "calisiyor" sayılmıyor.
    son_satirlar = (
        await db.execute(
            select(SiteSeoGecmisi.site_id, func.max(SiteSeoGecmisi.olcum_at))
            .where(
                SiteSeoGecmisi.site_id.in_(idler),
                or_(SiteSeoGecmisi.durum != CALISIYOR, SiteSeoGecmisi.olcum_at >= an - CALISIYOR_TAVAN),
            )
            .group_by(SiteSeoGecmisi.site_id)
        )
    ).all()
    son = {sid: utc(at) for sid, at in son_satirlar}
    zamani_gelen: List[Tuple[Client_sites, Optional[datetime]]] = []
    for s in siteler:
        gun = tarama_gunu(izlemeler.get(s.id))
        if gun <= 0:
            continue
        son_at = son.get(s.id)
        if son_at is None or an - son_at >= timedelta(days=gun) - ZAMAN_PAYI:
            zamani_gelen.append((s, son_at))
    en_eski = datetime.min.replace(tzinfo=timezone.utc)
    zamani_gelen.sort(key=lambda x: (x[1] is not None, x[1] or en_eski, x[0].id))
    return zamani_gelen


# --------------------------------------------------------------------------
# Ölçüm
# --------------------------------------------------------------------------
async def _analiz(url: str) -> Dict[str, Any]:
    """Motor çağrısı (testler bunu değil, motorun ağ katmanını sahteliyor)."""
    return await motor.analiz_et(url)


async def _olc(site: Client_sites) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """(özet, hata_kodu, süre_ms). Ağ işi; veritabanına dokunmuyor."""
    basla = time.perf_counter()
    try:
        sonuc = await asyncio.wait_for(_analiz(site.adres or ""), OLCUM_TAVANI)
        return sonuc_ozeti(sonuc), None, int((time.perf_counter() - basla) * 1000)
    except motor.AnalizHatasi as h:
        return None, h.kod, int((time.perf_counter() - basla) * 1000)
    except asyncio.TimeoutError:
        return None, "zaman_asimi", int((time.perf_counter() - basla) * 1000)
    except Exception:  # noqa: BLE001 - bir site diğerlerini durdurmasın
        logger.exception("SEO ölçümü beklenmedik hata: site=%s", site.id)
        return None, "beklenmedik", int((time.perf_counter() - basla) * 1000)


async def _yer_ac(db: AsyncSession, site: Client_sites, kaynak: str) -> SiteSeoGecmisi:
    satir = SiteSeoGecmisi(
        site_id=site.id,
        hesap_email=(site.client_email or "").strip().lower(),
        olcum_at=simdi(),
        kaynak=kaynak,
        durum=CALISIYOR,
    )
    db.add(satir)
    await db.commit()
    await db.refresh(satir)
    return satir


async def _tamamla(
    db: AsyncSession,
    site: Client_sites,
    satir: SiteSeoGecmisi,
    ozet: Optional[Dict[str, Any]],
    hata: Optional[str],
    sure_ms: int,
) -> Tuple[SiteSeoGecmisi, List[Dict[str, Any]]]:
    """Ölçüm satırını doldurur; başarılıysa öncekine göre uyarıları gönderir."""
    satir.sure_ms = sure_ms
    if ozet is None:
        satir.durum = HATA
        satir.hata_kodu = (hata or "beklenmedik")[:40]
        await db.commit()
        await db.refresh(satir)
        return satir, []
    onceki = (await _son_tamamlar(db, site.id, adet=1, haric=satir.id) or [None])[0]
    satir.durum = TAMAM
    satir.hata_kodu = None
    satir.genel_puan = ozet["genel_puan"]
    satir.bolum_puanlari = json.dumps(ozet["bolum_puanlari"], ensure_ascii=False)
    satir.mobil_puan = ozet["mobil_puan"]
    satir.masaustu_puan = ozet["masaustu_puan"]
    satir.lcp_ms = ozet["lcp_ms"]
    satir.cls = ozet["cls"]
    satir.tbt_ms = ozet["tbt_ms"]
    satir.bulgu_ozeti = json.dumps(ozet["bulgu_ozeti"], ensure_ascii=False)
    await db.commit()
    await db.refresh(satir)
    sorunlar = sorunlari_bul(_olcum_verisi(onceki) if onceki is not None else None, ozet)
    gonderilen = await uyari_gonder(db, site, satir, sorunlar) if sorunlar else []
    return satir, gonderilen


async def elle_tara(db: AsyncSession, site: Client_sites, kaynak: str = "elle") -> Tuple[SiteSeoGecmisi, List[Dict[str, Any]]]:
    """"Şimdi tara". Müşteri (`elle`) 24 saatte 1; yönetici sınırsız."""
    if kaynak not in KAYNAKLAR:
        raise ValueError(kaynak)
    if not (site.adres or "").strip():
        raise SeoHatasi(400, "adres_yok")
    if _suruyor_mu(await _son_deneme(db, site.id)):
        raise SeoHatasi(409, "tarama_suruyor")
    if kaynak == "elle":
        durum = await _elle_durumu(db, site.id)
        if durum["kalan"] <= 0:
            raise SeoHatasi(429, "gunluk_sinir", sonraki_at=durum["sonraki_at"])
    satir = await _yer_ac(db, site, kaynak)
    ozet, hata, sure = await _olc(site)
    return await _tamamla(db, site, satir, ozet, hata, sure)


async def zamanli_tarama(db: AsyncSession, sinir: int = TUR_SINIRI) -> Dict[str, Any]:
    """Zamanlı görev: zamanı gelen en çok `sinir` siteyi (en eskiden) ölçer."""
    kapanan = await yarida_kalanlari_kapat(db)
    sira = await tarama_sirasi(db)
    secilen = [s for s, _ in sira[: max(0, sinir)]]
    if not secilen:
        return {"bekleyen": 0, "olculen": 0, "hata": 0, "uyari": 0, "yarida_kalan": kapanan}
    satirlar = [await _yer_ac(db, s, "zamanli") for s in secilen]
    # Ağ işi paralel; veritabanı işi aşağıda sırayla (tek oturum).
    sonuclar = await asyncio.gather(*(_olc(s) for s in secilen))
    hata = uyari = 0
    for site, satir, (ozet, kod, sure) in zip(secilen, satirlar, sonuclar):
        try:
            _, gonderilen = await _tamamla(db, site, satir, ozet, kod, sure)
            uyari += len(gonderilen)
            if ozet is None:
                hata += 1
        except Exception:  # noqa: BLE001
            logger.exception("SEO ölçümü kaydedilemedi: site=%s", site.id)
            await db.rollback()
            hata += 1
    return {
        "bekleyen": max(0, len(sira) - len(secilen)),
        "olculen": len(secilen),
        "hata": hata,
        "uyari": uyari,
        "yarida_kalan": kapanan,
    }


# --------------------------------------------------------------------------
# Uyarı
# --------------------------------------------------------------------------
def _sorun_metni(s: Dict[str, Any]) -> Tuple[str, str]:
    if s["sorun"] == "puan_dususu":
        return (
            f"SEO/hız puanı {s['onceki']} → {s['simdiki']} düştü.",
            f"The SEO/speed score dropped from {s['onceki']} to {s['simdiki']}.",
        )
    if s["sorun"] == "kirik_baglanti":
        return (
            f"Kırık iç bağlantı sayısı {s['onceki']} → {s['simdiki']} arttı.",
            f"Broken internal links increased from {s['onceki']} to {s['simdiki']}.",
        )
    return KRITIK_METINLERI.get(s.get("kod") or "", (f"Yeni kritik bulgu: {s.get('kod')}", f"New critical finding: {s.get('kod')}"))


async def uyari_gonder(
    db: AsyncSession, site: Client_sites, olcum: SiteSeoGecmisi, sorunlar: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """7 gün içinde bildirilmemiş sorunları bildirir; gönderilenleri döndürür."""
    from services.moduller import modul_acik_mi
    from services.notify import admin_recipients, dispatch, render

    if not sorunlar:
        return []
    an = simdi()
    yakin = {
        r
        for (r,) in (
            await db.execute(
                select(SiteSeoUyarisi.sorun).where(
                    SiteSeoUyarisi.site_id == site.id,
                    SiteSeoUyarisi.sorun.in_([s["sorun"] for s in sorunlar]),
                    SiteSeoUyarisi.gonderim_at >= an - UYARI_ARALIGI,
                )
            )
        ).all()
    }
    yeni = [s for s in sorunlar if s["sorun"] not in yakin]
    if not yeni:
        return []
    for s in yeni:
        db.add(SiteSeoUyarisi(site_id=site.id, sorun=s["sorun"][:80], olcum_id=olcum.id, gonderim_at=an))
    await db.commit()

    try:
        eposta = (site.client_email or "").strip().lower()
        alicilar = await admin_recipients(db)
        if eposta and await modul_acik_mi(db, eposta, "sitem"):
            alicilar.append({"email": eposta, "role": "client"})
        if not alicilar:
            return yeni
        metinler = [_sorun_metni(s) for s in yeni]
        tr_satirlar = "\n".join(f"• {m[0]}" for m in metinler)
        en_satirlar = "\n".join(f"• {m[1]}" for m in metinler)
        varsayilan_baslik = f"SEO uyarısı: {site.ad} / SEO alert: {site.ad}"
        varsayilan_govde = (
            f"{site.ad} sitesinin son SEO ve hız ölçümünde:\n{tr_satirlar}\n\n"
            f"In the latest SEO and speed check of {site.ad}:\n{en_satirlar}"
        )
        baslik, govde = await render(
            db, OLAY, varsayilan_baslik, varsayilan_govde,
            {"site": site.ad, "puan": olcum.genel_puan, "sorunlar": tr_satirlar},
        )
        for alici in alicilar:
            await dispatch(
                db,
                event_type=OLAY,
                title=baslik,
                body=govde,
                recipients=[alici],
                link=YONETICI_BAGLANTISI if alici["role"] == "admin" else MUSTERI_BAGLANTISI,
                ref_type="site_seo",
                ref_id=olcum.id,
            )
    except Exception:  # noqa: BLE001 - bildirim ölçümü bozmasın
        logger.exception("SEO uyarısı gönderilemedi: site=%s", site.id)
    return yeni


# --------------------------------------------------------------------------
# Uçların verisi
# --------------------------------------------------------------------------
async def gecmis_sozlugu(db: AsyncSession, site: Client_sites, gun: int, *, yonetici: bool) -> Dict[str, Any]:
    """Site kartı: son ölçüm (+önemli 5 bulgu), değişim, `gun` günlük çizgi."""
    from services.site_izleme import izleme_getir

    an = simdi()
    iz = await izleme_getir(db, site, olustur=False)
    satirlar = list(
        (
            await db.execute(
                select(SiteSeoGecmisi)
                .where(
                    SiteSeoGecmisi.site_id == site.id,
                    SiteSeoGecmisi.durum.in_((TAMAM, HATA)),
                    SiteSeoGecmisi.olcum_at >= an - timedelta(days=gun),
                )
                .order_by(SiteSeoGecmisi.olcum_at.desc(), SiteSeoGecmisi.id.desc())
                .limit(GECMIS_EN_COK_SATIR)
            )
        ).scalars().all()
    )
    satirlar.reverse()
    son_iki = await _son_tamamlar(db, site.id, adet=2)
    son = son_iki[0] if son_iki else None
    onceki = son_iki[1] if len(son_iki) > 1 else None
    deneme = await _son_deneme(db, site.id)
    gun_ayari = tarama_gunu(iz)
    son_an = utc(deneme.olcum_at) if deneme is not None else None
    degisim = None
    if son is not None and onceki is not None and son.genel_puan is not None and onceki.genel_puan is not None:
        degisim = son.genel_puan - onceki.genel_puan
    return {
        "site_id": site.id,
        "ad": site.ad,
        "adres": site.adres,
        "tarama_gun": gun_ayari,
        "gun": gun,
        "son": tam_sozluk(son) if son is not None else None,
        "onceki_puan": onceki.genel_puan if onceki is not None else None,
        "degisim": degisim,
        "son_deneme": kisa_sozluk(deneme) if deneme is not None else None,
        "calisiyor": _suruyor_mu(deneme, an),
        "sonraki_tarama_at": iso(son_an + timedelta(days=gun_ayari)) if (son_an and gun_ayari > 0) else None,
        "gecmis": [kisa_sozluk(s) for s in satirlar],
        "elle": {"kalan": None, "sonraki_at": None, "sinirsiz": True} if yonetici else {**(await _elle_durumu(db, site.id, an)), "sinirsiz": False},
    }


async def ozet_listesi(db: AsyncSession) -> List[Dict[str, Any]]:
    """Yönetici: bütün sitelerin son puanı; düşüşte olanlar üstte."""
    from services.site_izleme import izlemeler_sozlugu

    siteler = list((await db.execute(select(Client_sites).order_by(Client_sites.id.desc()).limit(SITE_SINIRI))).scalars().all())
    if not siteler:
        return []
    idler = [s.id for s in siteler]
    izlemeler = await izlemeler_sozlugu(db, idler)
    sira = (
        func.row_number()
        .over(partition_by=SiteSeoGecmisi.site_id, order_by=(SiteSeoGecmisi.olcum_at.desc(), SiteSeoGecmisi.id.desc()))
        .label("sira")
    )
    alt = (
        select(SiteSeoGecmisi.id.label("id"), sira)
        .where(SiteSeoGecmisi.site_id.in_(idler), SiteSeoGecmisi.durum == TAMAM)
        .subquery()
    )
    tamamlar: Dict[int, List[SiteSeoGecmisi]] = {}
    for s in (
        await db.execute(
            select(SiteSeoGecmisi)
            .join(alt, alt.c.id == SiteSeoGecmisi.id)
            .where(alt.c.sira <= 2)
            .order_by(SiteSeoGecmisi.site_id, SiteSeoGecmisi.olcum_at.desc(), SiteSeoGecmisi.id.desc())
        )
    ).scalars().all():
        tamamlar.setdefault(s.site_id, []).append(s)
    son_id = (
        select(func.max(SiteSeoGecmisi.id).label("id"))
        .where(SiteSeoGecmisi.site_id.in_(idler))
        .group_by(SiteSeoGecmisi.site_id)
        .subquery()
    )
    denemeler = {
        s.site_id: s
        for s in (await db.execute(select(SiteSeoGecmisi).join(son_id, son_id.c.id == SiteSeoGecmisi.id))).scalars().all()
    }
    an = simdi()
    satirlar = []
    for site in siteler:
        liste = tamamlar.get(site.id, [])
        son = liste[0] if liste else None
        onceki = liste[1] if len(liste) > 1 else None
        degisim = None
        if son is not None and onceki is not None and son.genel_puan is not None and onceki.genel_puan is not None:
            degisim = son.genel_puan - onceki.genel_puan
        kritik_simdi = kritikler(_olcum_verisi(son)["bulgu_ozeti"]) if son is not None else set()
        kritik_once = kritikler(_olcum_verisi(onceki)["bulgu_ozeti"]) if onceki is not None else set()
        yeni_kritik = sorted(kritik_simdi - kritik_once) if onceki is not None else []
        deneme = denemeler.get(site.id)
        gun_ayari = tarama_gunu(izlemeler.get(site.id))
        son_an = utc(deneme.olcum_at) if deneme is not None else None
        satirlar.append({
            "site_id": site.id,
            "ad": site.ad,
            "adres": site.adres,
            "client_email": site.client_email,
            "tarama_gun": gun_ayari,
            "son": kisa_sozluk(son) if son is not None else None,
            "onceki_puan": onceki.genel_puan if onceki is not None else None,
            "degisim": degisim,
            "kritik": sorted(kritik_simdi),
            "yeni_kritik": yeni_kritik,
            "dususte": bool((degisim is not None and degisim <= -DUSUS_ESIGI) or yeni_kritik),
            "son_deneme": kisa_sozluk(deneme) if deneme is not None else None,
            "calisiyor": _suruyor_mu(deneme, an),
            "sonraki_tarama_at": iso(son_an + timedelta(days=gun_ayari)) if (son_an and gun_ayari > 0) else None,
        })

    def anahtar(r: Dict[str, Any]):
        puan = (r["son"] or {}).get("genel_puan")
        return (
            not r["dususte"],
            r["degisim"] if r["degisim"] is not None else 0,
            puan is None,
            puan if puan is not None else 0,
            -r["site_id"],
        )

    satirlar.sort(key=anahtar)
    return satirlar


async def ayar_kaydet(db: AsyncSession, site: Client_sites, gun: int) -> int:
    from services.site_izleme import izleme_getir

    if isinstance(gun, bool) or not isinstance(gun, int) or not 0 <= gun <= EN_COK_GUN:
        raise SeoHatasi(400, "gun_gecersiz")
    iz = await izleme_getir(db, site)
    assert iz is not None
    iz.seo_tarama_gun = gun
    await db.commit()
    return gun


# --------------------------------------------------------------------------
# Aylık rapor (Faz 2C) — ay içindeki ölçümlerin özeti
# --------------------------------------------------------------------------
async def aylik_ozet(db: AsyncSession, eposta: str, bas: datetime, bit: datetime) -> List[Dict[str, Any]]:
    """Ay içinde (bas ≤ an < bit) ölçülen her site için özet; ölçüm yoksa boş liste."""
    eposta = (eposta or "").strip().lower()
    satirlar = list(
        (
            await db.execute(
                select(SiteSeoGecmisi)
                .where(
                    SiteSeoGecmisi.hesap_email == eposta,
                    SiteSeoGecmisi.durum == TAMAM,
                    SiteSeoGecmisi.olcum_at >= bas,
                    SiteSeoGecmisi.olcum_at < bit,
                )
                .order_by(SiteSeoGecmisi.site_id, SiteSeoGecmisi.olcum_at.asc(), SiteSeoGecmisi.id.asc())
            )
        ).scalars().all()
    )
    if not satirlar:
        return []
    gruplar: Dict[int, List[SiteSeoGecmisi]] = {}
    for s in satirlar:
        gruplar.setdefault(s.site_id, []).append(s)
    adlar = {
        s.id: s.ad
        for s in (await db.execute(select(Client_sites).where(Client_sites.id.in_(list(gruplar))))).scalars().all()
    }
    uyari_sayilari = dict(
        (
            await db.execute(
                select(SiteSeoUyarisi.site_id, func.count(SiteSeoUyarisi.id))
                .where(
                    SiteSeoUyarisi.site_id.in_(list(gruplar)),
                    SiteSeoUyarisi.gonderim_at >= bas,
                    SiteSeoUyarisi.gonderim_at < bit,
                )
                .group_by(SiteSeoUyarisi.site_id)
            )
        ).all()
    )
    sonuc = []
    for site_id, liste in sorted(gruplar.items()):
        puanlar = [s.genel_puan for s in liste if s.genel_puan is not None]
        ilk, son = liste[0], liste[-1]
        sonuc.append({
            "site_id": site_id,
            "ad": adlar.get(site_id) or f"#{site_id}",
            "olcum_sayisi": len(liste),
            "ilk_puan": ilk.genel_puan,
            "son_puan": son.genel_puan,
            "degisim": (son.genel_puan - ilk.genel_puan) if (len(liste) > 1 and son.genel_puan is not None and ilk.genel_puan is not None) else None,
            "en_dusuk": min(puanlar) if puanlar else None,
            "en_yuksek": max(puanlar) if puanlar else None,
            "ortalama": round(sum(puanlar) / len(puanlar), 1) if puanlar else None,
            "son_tarih": iso(son.olcum_at),
            "son_mobil": son.mobil_puan,
            "son_masaustu": son.masaustu_puan,
            "son_lcp_ms": son.lcp_ms,
            "son_cls": son.cls,
            "son_tbt_ms": son.tbt_ms,
            "son_kritik": sorted(kritikler(_olcum_verisi(son)["bulgu_ozeti"])),
            "uyari_sayisi": int(uyari_sayilari.get(site_id) or 0),
        })
    return sonuc
