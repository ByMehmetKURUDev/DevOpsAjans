"""Müşteri sitesi bakımı (Faz 2A): bitiş taraması, eşik hatırlatmaları,
uptime ölçümü, kesinti olayları ve toplulaştırma.

Ağa çıkan HER istek `services/site_analizi` içindeki SSRF korumalı
istemciden (`_istemci` + `Gezgin`) ya da onun `_ssl_bitis`'inden geçiyor:
ad çözülüp bütün IP'ler genel mi bakılıyor, yönlendirmelerin her adımı
yeniden denetleniyor, doğrudan bağlantıda soket denetlenmiş IP'ye açılıyor.
Müşterinin yazdığı uptime adresi de, RDAP'ın yönlendirdiği kayıt sunucusu
da aynı kapıdan geçiyor.

Zaman: gün hesapları Türkiye saatinde (UTC+3, yaz saati yok). Durum
sayfasındaki "gün" müşterinin takvim günü olsun diye.

Burada yan etkiler (ağ, veritabanı) ile saf hesaplar (RDAP ayrıştırma, eşik
seçimi, kesinti durumu, abonelik yenileme tarihi) ayrı fonksiyonlarda;
testler saf olanları ağsız çağırıyor, ağ çağıranların yerine sahte koyuyor.
"""

import asyncio
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.client_sites import Client_sites
from models.service_subscriptions import Service_subscriptions
from models.site_izleme import (
    BitisBildirimi,
    SiteIzleme,
    UptimeGunluk,
    UptimeKesintisi,
    UptimeKontrolu,
    UptimeOlcumu,
)
from services import site_analizi as sa
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TR = timezone(timedelta(hours=3))

# --------------------------------------------------------------------------
# Tavanlar ve kurallar
# --------------------------------------------------------------------------
ESIKLER: Tuple[int, ...] = (30, 15, 7, 1)
#: Otomatik yenilenen SSL (Let's Encrypt gibi) 30 gün kala kendisi yenileniyor;
#: o noktada uyarmak gürültü. 7/1 gün kalmışsa gerçekten sorun var.
OTOMATIK_SSL_ESIKLERI: Tuple[int, ...] = (7, 1)
AYLIK_ABONELIK_ESIKLERI: Tuple[int, ...] = (7, 1)
#: Süresi geçmiş kaleme en çok bu kadar gün sonrasına kadar (bir kez) haber veriliyor.
GECIKME_TAVANI_GUN = 7

RDAP_ADRESI = "https://rdap.org/domain/{alan}"
#: RDAP sunucusu olmayan uzantılar: çağrı yapılmıyor, tarih elle giriliyor.
RDAP_DESTEKSIZ_UZANTILAR = frozenset({"tr"})
#: Alan adını kök alan adına indirirken iki seviyeli sayılan sonekler.
#: Tam kamu soneki listesi (PSL) bağımlılığı eklemiyoruz; yanlış çıkarsa
#: yönetici alan adını formdan düzeltiyor.
IKI_SEVIYELI_SONEKLER = frozenset({
    "com.tr", "net.tr", "org.tr", "gen.tr", "biz.tr", "info.tr", "web.tr", "av.tr",
    "dr.tr", "bel.tr", "tv.tr", "name.tr", "tel.tr", "k12.tr", "edu.tr", "gov.tr",
    "co.uk", "org.uk", "ac.uk", "com.au", "net.au", "co.nz", "com.br", "co.jp",
    "com.cn", "com.mx", "co.za", "com.sa", "com.eg", "co.in", "com.de",
})

TARAMA_ARALIGI = timedelta(hours=20)  # "günde bir"; cron kaymasına pay
TARAMA_PARTI = 20                     # tek çalışmada en çok bu kadar site
TARAMA_ESZAMANLILIK = 4
RDAP_ZAMAN_ASIMI = 10.0

EN_AZ_ARALIK_DK = 5
UPTIME_ESZAMANLILIK = 10
UPTIME_ZAMAN_ASIMI = 10.0
#: Tek kontrolün tavanı (yönlendirmeler dahil).
UPTIME_TEK_TAVAN = 15.0
#: Tek çalışmada en çok bu kadar kontrol; kalanı bir sonraki çalışmaya.
UPTIME_PARTI = 60
#: Cron 5-10 dakikada bir geliyor; "tam 5 dk olmadı" diye bir turu kaçırmasın.
ARALIK_TOLERANSI = timedelta(seconds=60)
KESINTI_ESIGI = 2
OLCUM_SAKLAMA_GUN = 90
GUNLUK_SAKLAMA_GUN = 400
GRAFIK_GUN = 90

UPTIME_AJAN = "MehmetKuruDevUptime/1.0 (+https://mehmetkuru.dev)"
ANAHTAR_KELIME_EN_COK = 200

MUSTERI_BAGLANTISI = "/client?sekme=sitem"
YONETICI_BAGLANTISI = "/admin"


# --------------------------------------------------------------------------
# Küçük yardımcılar
# --------------------------------------------------------------------------
def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini düşürüyor; saklanan her an UTC."""
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def tr_gunu(an: datetime) -> date:
    return utc(an).astimezone(TR).date()  # type: ignore[union-attr]


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def kalan_gun(bitis: Optional[datetime], bugun: Optional[date] = None) -> Optional[int]:
    if bitis is None:
        return None
    bugun = bugun or tr_gunu(simdi())
    return (tr_gunu(bitis) - bugun).days


# --------------------------------------------------------------------------
# Alan adı ve RDAP (saf)
# --------------------------------------------------------------------------
def kok_alan(host: str) -> str:
    """`www.magaza.ornek.com.tr` → `ornek.com.tr` (kaba ama bağımlılıksız)."""
    host = (host or "").strip().rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    parcalar = [p for p in host.split(".") if p]
    if len(parcalar) <= 2:
        return ".".join(parcalar)
    son_iki = ".".join(parcalar[-2:])
    if son_iki in IKI_SEVIYELI_SONEKLER:
        return ".".join(parcalar[-3:])
    return son_iki


def alan_adi_turet(adres: Optional[str]) -> Optional[str]:
    """Site adresinden kök alan adı; IP adresi ya da geçersizse None."""
    if not adres:
        return None
    try:
        _url, host, _alan = sa.adresi_normalize(adres)
    except sa.AnalizHatasi:
        return None
    if sa._ip_mi(host) is not None:
        return None
    return kok_alan(host)


def alan_adi_dogrula(ham: Optional[str]) -> Optional[str]:
    """Formdan gelen alan adı: küçük harf, şemasız, yol yok; geçersizse ValueError."""
    ham = (ham or "").strip().lower()
    if not ham:
        return None
    if "://" in ham:
        ham = ham.split("://", 1)[1]
    ham = ham.split("/", 1)[0].rstrip(".")
    if ham.startswith("www."):
        ham = ham[4:]
    try:
        ham = ham.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("alan_gecersiz") from exc
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}", ham):
        raise ValueError("alan_gecersiz")
    return ham


def _tarih_ayristir(metin: Any) -> Optional[datetime]:
    if not isinstance(metin, str) or not metin.strip():
        return None
    m = metin.strip().replace("Z", "+00:00").replace("z", "+00:00")
    # Bazı kayıt sunucuları kesirli saniyeyi 7 hane yazıyor; Python 6 istiyor.
    m = re.sub(r"(\.\d{6})\d+", r"\1", m)
    try:
        an = datetime.fromisoformat(m)
    except ValueError:
        try:
            an = datetime.strptime(m[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return utc(an)


def rdap_ayristir(veri: Any) -> Optional[datetime]:
    """RDAP yanıtından bitiş tarihi (`events[].eventAction == "expiration"`).

    Bazı sunucular olayı `registrar expiration` diye yazıyor; ikisi de kabul.
    Birden çok bitiş olayı varsa en geç olan (yenilenmiş tarih) geçerli.
    """
    if not isinstance(veri, dict):
        return None
    olaylar = veri.get("events")
    if not isinstance(olaylar, list):
        return None
    adaylar: List[datetime] = []
    for olay in olaylar:
        if not isinstance(olay, dict):
            continue
        eylem = str(olay.get("eventAction") or "").strip().lower()
        if eylem in ("expiration", "registrar expiration", "registration expiration"):
            an = _tarih_ayristir(olay.get("eventDate"))
            if an is not None:
                adaylar.append(an)
    return max(adaylar) if adaylar else None


async def rdap_sorgula(alan: str) -> Tuple[Optional[datetime], Optional[str]]:
    """(bitiş, hata). Hata: desteklenmiyor | bulunamadi | ulasilamadi | tarih_yok."""
    uzanti = alan.rsplit(".", 1)[-1]
    if uzanti in RDAP_DESTEKSIZ_UZANTILAR:
        return None, "desteklenmiyor"
    adres = RDAP_ADRESI.format(alan=alan)
    try:
        async with sa._istemci(zaman_asimi=RDAP_ZAMAN_ASIMI, eszamanlilik=2, ajan=UPTIME_AJAN) as istemci:
            gezgin = sa.Gezgin(istemci, eszamanlilik=2, zaman_asimi=RDAP_ZAMAN_ASIMI)
            yanit = await gezgin.getir(adres, "GET", govde_oku=True, izle=True)
    except Exception as exc:  # noqa: BLE001 - tarama tek site yüzünden durmasın
        logger.info("RDAP sorgusu başarısız (%s): %s", alan, type(exc).__name__)
        return None, "ulasilamadi"
    if yanit.hata:
        return None, "ulasilamadi"
    if yanit.durum == 404:
        return None, "bulunamadi"
    if yanit.durum != 200:
        return None, "ulasilamadi"
    try:
        veri = json.loads(yanit.govde or "")
    except ValueError:
        return None, "tarih_yok"
    bitis = rdap_ayristir(veri)
    return (bitis, None) if bitis else (None, "tarih_yok")


async def ssl_olc(host: str) -> Tuple[Optional[datetime], Optional[str]]:
    """Sertifika bitişi — 1A'daki SSRF korumalı ölçüm."""
    return await sa._ssl_bitis(host)


# --------------------------------------------------------------------------
# İzleme satırı
# --------------------------------------------------------------------------
def slug_uret(ad: str) -> str:
    """Okunur + tahmin edilemez: `ornek-magaza-3fa9c1`."""
    tablo = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosucgiosuaiu")
    temel = re.sub(r"[^a-z0-9]+", "-", (ad or "").translate(tablo).lower()).strip("-")[:30].strip("-")
    return f"{temel or 'site'}-{secrets.token_hex(3)}"


async def izleme_getir(db: AsyncSession, site: Client_sites, olustur: bool = True) -> Optional[SiteIzleme]:
    sonuc = await db.execute(select(SiteIzleme).where(SiteIzleme.site_id == site.id))
    kayit = sonuc.scalar_one_or_none()
    if kayit is None and olustur:
        kayit = SiteIzleme(
            site_id=site.id,
            alan_adi=alan_adi_turet(site.adres),
            ssl_elle_yenilenir=False,
            durum_sayfasi_acik=False,
            durum_index=False,
        )
        db.add(kayit)
        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError:
            # Eş zamanlı iki istek aynı anda açtıysa diğerininkini kullan.
            sonuc = await db.execute(select(SiteIzleme).where(SiteIzleme.site_id == site.id))
            kayit = sonuc.scalar_one_or_none()
    return kayit


async def izlemeler_sozlugu(db: AsyncSession, site_idleri: Iterable[int]) -> Dict[int, SiteIzleme]:
    idler = sorted(set(site_idleri))
    if not idler:
        return {}
    sonuc = await db.execute(select(SiteIzleme).where(SiteIzleme.site_id.in_(idler)))
    return {k.site_id: k for k in sonuc.scalars().all()}


# --------------------------------------------------------------------------
# Bitiş taraması (RDAP + SSL) — zamanlı görev, günde bir
# --------------------------------------------------------------------------
async def _site_olc(site: Client_sites, izleme: SiteIzleme) -> Dict[str, Any]:
    """Ağ kısmı; veritabanına dokunmuyor (paralel çalışabilsin)."""
    sonuc: Dict[str, Any] = {}
    alan = izleme.alan_adi or alan_adi_turet(site.adres)
    if alan and izleme.alan_bitis_kaynak != "elle":
        sonuc["rdap"] = await rdap_sorgula(alan)
    host = None
    if site.adres:
        try:
            url, host, _ = sa.adresi_normalize(site.adres)
            if not url.startswith("https://"):
                host = None
        except sa.AnalizHatasi:
            host = None
    if host:
        sonuc["ssl"] = await ssl_olc(host)
    return sonuc


def _olcumu_yaz(izleme: SiteIzleme, site: Client_sites, olcum: Dict[str, Any], an: datetime) -> None:
    if not izleme.alan_adi:
        izleme.alan_adi = alan_adi_turet(site.adres)
    if "rdap" in olcum:
        bitis, hata = olcum["rdap"]
        if bitis is not None:
            izleme.alan_bitis = bitis
            izleme.alan_bitis_kaynak = "rdap"
            izleme.alan_rdap_hata = None
        else:
            izleme.alan_rdap_hata = hata
    izleme.alan_kontrol_at = an
    if "ssl" in olcum:
        bitis, hata = olcum["ssl"]
        if bitis is not None:
            izleme.ssl_bitis = bitis
            izleme.ssl_hata = None
        else:
            izleme.ssl_hata = hata
        izleme.ssl_kontrol_at = an


async def siteyi_tara(db: AsyncSession, site: Client_sites) -> SiteIzleme:
    """Tek siteyi şimdi tarar (yönetici "şimdi tara"). Commit çağıranda."""
    izleme = await izleme_getir(db, site)
    assert izleme is not None
    olcum = await _site_olc(site, izleme)
    _olcumu_yaz(izleme, site, olcum, simdi())
    return izleme


async def bitis_taramasi(db: AsyncSession, zorla: bool = False) -> Dict[str, Any]:
    """Son taraması 20 saatten eski sitelerden en çok TARAMA_PARTI tanesi."""
    siteler = list(
        (
            await db.execute(
                select(Client_sites).where(Client_sites.adres.isnot(None)).order_by(Client_sites.id)
            )
        ).scalars().all()
    )
    siteler = [s for s in siteler if (s.durum or "aktif") != "bitti" and (s.adres or "").strip()]
    izlemeler = await izlemeler_sozlugu(db, [s.id for s in siteler])
    an = simdi()
    adaylar: List[Tuple[Client_sites, SiteIzleme]] = []
    for site in siteler:
        izleme = izlemeler.get(site.id) or await izleme_getir(db, site)
        son = utc(izleme.alan_kontrol_at)
        if zorla or son is None or an - son >= TARAMA_ARALIGI:
            adaylar.append((site, izleme))
    adaylar.sort(key=lambda c: utc(c[1].alan_kontrol_at) or datetime.min.replace(tzinfo=timezone.utc))
    secilen = adaylar[:TARAMA_PARTI]

    kilit = asyncio.Semaphore(TARAMA_ESZAMANLILIK)

    async def olc(site: Client_sites, izleme: SiteIzleme) -> Dict[str, Any]:
        async with kilit:
            try:
                return await asyncio.wait_for(_site_olc(site, izleme), RDAP_ZAMAN_ASIMI * 2 + 5)
            except Exception as exc:  # noqa: BLE001
                logger.info("Site taraması başarısız (site=%s): %s", site.id, type(exc).__name__)
                return {}

    olcumler = await asyncio.gather(*(olc(s, i) for s, i in secilen))
    alan_bulunan = ssl_bulunan = 0
    for (site, izleme), olcum in zip(secilen, olcumler):
        _olcumu_yaz(izleme, site, olcum, an)
        if olcum.get("rdap", (None,))[0] is not None:
            alan_bulunan += 1
        if olcum.get("ssl", (None,))[0] is not None:
            ssl_bulunan += 1
    await db.commit()
    return {
        "taranan": len(secilen),
        "bekleyen": max(0, len(adaylar) - len(secilen)),
        "alan_bulunan": alan_bulunan,
        "ssl_bulunan": ssl_bulunan,
    }


# --------------------------------------------------------------------------
# Eşik hatırlatmaları (saf seçim + kayıt) — günde bir
# --------------------------------------------------------------------------
def esik_sec(kalan: Optional[int], esikler: Sequence[int], gonderilmis: Iterable[int]) -> Tuple[Optional[int], List[int]]:
    """(gönderilecek eşik, işaretlenecek eşikler).

    Kalan gün hangi eşiklerin altındaysa bunlardan EN KÜÇÜĞÜ gönderiliyor ve
    daha büyük olanlar da "gönderildi" sayılıyor: 5 gün kala ilk kez görülen
    bir alan adı için 30/15/7 üç ayrı e-posta gitmesin, tek "7 gün" gitsin.
    Her eşik bir kez. Süresi GECIKME_TAVANI_GUN'den fazla geçmişse susuluyor.
    """
    if kalan is None or kalan < -GECIKME_TAVANI_GUN:
        return None, []
    gecen = sorted(e for e in esikler if kalan <= e)
    if not gecen:
        return None, []
    en_kucuk = gecen[0]
    gonderilmis = set(gonderilmis)
    if en_kucuk in gonderilmis:
        return None, []
    return en_kucuk, [e for e in gecen if e not in gonderilmis]


def _sonraki_ay(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def abonelik_yenileme_tarihi(baslangic: Optional[str], periyot: Optional[str], bugun: date) -> Optional[date]:
    """Aboneliğin bir sonraki yenileme günü (ayın 1'i; dönem YYYY-MM başlıyor).

    aylik  → bugün ya da sonraki ilk ay başı (başlangıç ayından sonra);
    yillik → başlangıç ayının bugün ya da sonraki ilk yıl dönümü.
    """
    try:
        yil, ay = (int(p) for p in (baslangic or "").split("-")[:2])
        ilk = date(yil, ay, 1)
    except (TypeError, ValueError):
        return None
    if (periyot or "aylik").strip().lower() == "yillik":
        aday = date(bugun.year, ay, 1)
        if aday < bugun:
            aday = date(bugun.year + 1, ay, 1)
        if aday <= ilk:
            aday = date(ilk.year + 1, ay, 1)
        return aday
    aday = date(bugun.year, bugun.month, 1)
    if aday < bugun:
        aday = _sonraki_ay(aday)
    while aday <= ilk:
        aday = _sonraki_ay(aday)
    return aday


@dataclass
class Kalem:
    """Yenilenecek/bitecek tek kalem (liste ve hatırlatma ortak)."""

    tur: str  # alan | ssl | hosting | abonelik
    ref_id: int
    client_email: str
    baslik: str
    bitis: date
    saglayici: Optional[str] = None
    site_id: Optional[int] = None
    abonelik_id: Optional[int] = None
    tutar: Optional[float] = None
    para_birimi: Optional[str] = None
    periyot: Optional[str] = None
    otomatik: bool = False

    def esikler(self) -> Tuple[int, ...]:
        if self.tur == "ssl" and self.otomatik:
            return OTOMATIK_SSL_ESIKLERI
        if self.tur == "abonelik" and (self.periyot or "aylik") != "yillik":
            return AYLIK_ABONELIK_ESIKLERI
        return ESIKLER


async def kalemler(db: AsyncSession, ssl_hepsi: bool = False) -> List[Kalem]:
    """Bitiş tarihi bilinen bütün kalemler (alan, SSL, hosting, abonelik).

    `ssl_hepsi=False`: yenileme listesine yalnız ELLE yenilenen SSL giriyor.
    Hatırlatmalar için otomatik SSL de gerekli (7/1 gün uyarısı).
    """
    siteler = {
        s.id: s
        for s in (await db.execute(select(Client_sites))).scalars().all()
        if (s.durum or "aktif") != "bitti"
    }
    izlemeler = await izlemeler_sozlugu(db, siteler.keys())
    sonuc: List[Kalem] = []
    for site_id, iz in izlemeler.items():
        site = siteler.get(site_id)
        if site is None:
            continue
        eposta = (site.client_email or "").strip().lower()
        if iz.alan_bitis:
            sonuc.append(Kalem("alan", site_id, eposta, iz.alan_adi or site.ad, tr_gunu(iz.alan_bitis),
                               iz.alan_saglayici, site_id=site_id))
        if iz.hosting_bitis:
            sonuc.append(Kalem("hosting", site_id, eposta, site.ad, tr_gunu(iz.hosting_bitis),
                               iz.hosting_saglayici, site_id=site_id))
        if iz.ssl_bitis and (ssl_hepsi or iz.ssl_elle_yenilenir):
            sonuc.append(Kalem("ssl", site_id, eposta, iz.alan_adi or site.ad, tr_gunu(iz.ssl_bitis),
                               None, site_id=site_id, otomatik=not bool(iz.ssl_elle_yenilenir)))
    bugun = tr_gunu(simdi())
    abonelikler = (
        await db.execute(select(Service_subscriptions).where(Service_subscriptions.durum == "aktif"))
    ).scalars().all()
    for a in abonelikler:
        tarih = abonelik_yenileme_tarihi(a.baslangic, a.periyot, bugun)
        if tarih is None:
            continue
        sonuc.append(
            Kalem("abonelik", a.id, (a.client_email or "").strip().lower(), a.baslik or a.hizmet, tarih,
                  None, abonelik_id=a.id, tutar=a.tutar, para_birimi=a.para_birimi, periyot=a.periyot)
        )
    sonuc.sort(key=lambda k: (k.bitis, k.tur, k.ref_id))
    return sonuc


TUR_ADLARI = {
    "alan": ("Alan adı", "Domain"),
    "ssl": ("SSL sertifikası", "SSL certificate"),
    "hosting": ("Hosting", "Hosting"),
    "abonelik": ("Abonelik", "Subscription"),
}


def _bitis_metni(k: Kalem, kalan: int) -> Tuple[str, str]:
    tr_ad, en_ad = TUR_ADLARI[k.tur]
    tarih = k.bitis.strftime("%d.%m.%Y")
    if kalan < 0:
        baslik = f"{tr_ad} süresi doldu: {k.baslik} / {en_ad} expired: {k.baslik}"
        govde = (
            f"{k.baslik} için {tr_ad.lower()} süresi {tarih} tarihinde doldu.\n\n"
            f"The {en_ad.lower()} for {k.baslik} expired on {tarih}."
        )
    else:
        baslik = f"{tr_ad} {kalan} gün sonra bitiyor: {k.baslik} / {en_ad} expires in {kalan} days: {k.baslik}"
        govde = (
            f"{k.baslik} için {tr_ad.lower()} {tarih} tarihinde bitiyor ({kalan} gün kaldı). "
            "Yenileme için ekibimiz sizinle iletişime geçecek.\n\n"
            f"The {en_ad.lower()} for {k.baslik} expires on {tarih} ({kalan} days left). "
            "Our team will contact you about the renewal."
        )
    return baslik, govde


async def yenileme_hatirlatmalari(db: AsyncSession) -> Dict[str, Any]:
    """30/15/7/1 gün kala müşteriye ve yöneticiye bildirim; her eşik bir kez.

    Müşteriye yalnız `yenileme` modülü açıksa (abonelik hatırlatması hiç
    müşteriye gitmiyor: faturayı biz kesiyoruz). Yöneticiye her zaman.
    """
    from services.moduller import toplu_durumlar
    from services.notify import admin_recipients, dispatch, render

    bugun = tr_gunu(simdi())
    liste = await kalemler(db, ssl_hepsi=True)
    gonderilmis: Dict[Tuple[str, int, str], set] = {}
    for b in (await db.execute(select(BitisBildirimi))).scalars().all():
        gonderilmis.setdefault((b.tur, b.ref_id, b.bitis), set()).add(b.esik)

    gidecek: List[Tuple[Kalem, int, int]] = []
    for k in liste:
        kalan = (k.bitis - bugun).days
        anahtar = (k.tur, k.ref_id, k.bitis.isoformat())
        esik, isaretle = esik_sec(kalan, k.esikler(), gonderilmis.get(anahtar, ()))
        if esik is None:
            continue
        yazildi = False
        try:
            async with db.begin_nested():
                for e in isaretle:
                    db.add(BitisBildirimi(tur=k.tur, ref_id=k.ref_id, bitis=anahtar[2], esik=e))
                await db.flush()
            yazildi = True
        except IntegrityError:
            logger.info("Bitiş bildirimi zaten gönderilmiş: %s", anahtar)
        if yazildi:
            gidecek.append((k, esik, kalan))
    await db.commit()

    if not gidecek:
        return {"kalem": len(liste), "bildirim": 0}

    musteri_durumu = await toplu_durumlar(db, [k.client_email for k, _, _ in gidecek if k.tur != "abonelik"])
    yoneticiler = await admin_recipients(db)
    gonderilen = 0
    for k, esik, kalan in gidecek:
        alicilar = list(yoneticiler)
        mm = musteri_durumu.get(k.client_email)
        if k.tur != "abonelik" and mm is not None:
            d = mm.durumlar.get("yenileme")
            if d is not None and d.acik:
                alicilar.append({"email": k.client_email, "role": "client"})
        if not alicilar:
            continue
        varsayilan_baslik, varsayilan_govde = _bitis_metni(k, kalan)
        try:
            baslik, govde = await render(
                db, "bitis_yaklasiyor", varsayilan_baslik, varsayilan_govde,
                {"kalem": k.baslik, "tur": TUR_ADLARI[k.tur][0], "kalan": kalan,
                 "tarih": k.bitis.strftime("%d.%m.%Y"), "esik": esik},
            )
            # Yönetici ve müşteri aynı olayı farklı bağlantıyla görüyor.
            for alici in alicilar:
                await dispatch(
                    db,
                    event_type="bitis_yaklasiyor",
                    title=baslik,
                    body=govde,
                    recipients=[alici],
                    link=YONETICI_BAGLANTISI if alici["role"] == "admin" else MUSTERI_BAGLANTISI,
                    ref_type="site" if k.site_id else "abonelik",
                    ref_id=k.ref_id,
                )
            gonderilen += 1
        except Exception:  # noqa: BLE001 - bildirim görevi düşürmesin
            logger.exception("Bitiş bildirimi gönderilemedi")
    return {"kalem": len(liste), "bildirim": gonderilen}


# --------------------------------------------------------------------------
# Uptime
# --------------------------------------------------------------------------
def uptime_adresi_dogrula(ham: str) -> str:
    """Biçim + şema; ağ denetimi `uptime_adresi_denetle`'de. AnalizHatasi fırlatır."""
    url, _host, _alan = sa.adresi_normalize(ham)
    return url


async def uptime_adresi_denetle(ham: str) -> str:
    """Kontrol eklenirken: biçim + ad çözülüp bütün IP'ler genel mi (SSRF)."""
    url = uptime_adresi_dogrula(ham)
    await sa.adres_dogrula(url)
    return url


@dataclass
class OlcumSonucu:
    kontrol_id: int
    site_id: int
    zaman: datetime
    durum_kodu: Optional[int]
    sure_ms: int
    basarili: bool
    hata_ozeti: Optional[str]


async def tek_olcum(gezgin: "sa.Gezgin", kontrol: UptimeKontrolu) -> OlcumSonucu:
    basla = simdi()
    anahtar = (kontrol.anahtar_kelime or "").strip()
    try:
        yanit = await asyncio.wait_for(
            gezgin.getir(kontrol.url, "GET", govde_oku=bool(anahtar), izle=True), UPTIME_TEK_TAVAN
        )
    except asyncio.TimeoutError:
        return OlcumSonucu(kontrol.id, kontrol.site_id, basla, None, int(UPTIME_TEK_TAVAN * 1000), False, "zaman_asimi")
    except Exception as exc:  # noqa: BLE001
        logger.info("Uptime ölçümü patladı (kontrol=%s): %s", kontrol.id, type(exc).__name__)
        return OlcumSonucu(kontrol.id, kontrol.site_id, basla, None, 0, False, "ulasilamadi")
    if yanit.hata:
        return OlcumSonucu(kontrol.id, kontrol.site_id, basla, None, yanit.sure_ms, False, yanit.hata)
    beklenen = int(kontrol.beklenen_kod or 200)
    if yanit.durum != beklenen:
        return OlcumSonucu(kontrol.id, kontrol.site_id, basla, yanit.durum, yanit.sure_ms, False, f"kod_{yanit.durum}")
    if anahtar and anahtar.lower() not in (yanit.govde or "").lower():
        return OlcumSonucu(kontrol.id, kontrol.site_id, basla, yanit.durum, yanit.sure_ms, False, "anahtar_kelime_yok")
    return OlcumSonucu(kontrol.id, kontrol.site_id, basla, yanit.durum, yanit.sure_ms, True, None)


def durum_gecisi(
    kontrol: UptimeKontrolu, sonuc: OlcumSonucu, acik_kesinti: Optional[UptimeKesintisi]
) -> Tuple[Optional[str], Optional[UptimeKesintisi]]:
    """Kesinti durum makinesi (veritabanına eklemiyor; yeni kesintiyi döndürüyor).

    * Başarılı ölçüm: hata sayacı sıfır; açık kesinti varsa kapanıyor → "duzeldi".
    * Başarısız: sayaç +1; KESINTI_ESIGI'ne (2) ulaşınca ve açık kesinti
      yoksa yeni kesinti, başlangıcı serinin İLK hatalı ölçümü → "coktu".
    Tek bir başarısız ölçüm kesinti sayılmıyor (ağ hıçkırığı).
    """
    kontrol.son_kontrol_at = sonuc.zaman
    if sonuc.basarili:
        kontrol.ardisik_hata = 0
        kontrol.ilk_hata_at = None
        kontrol.son_durum = "up"
        if acik_kesinti is not None:
            acik_kesinti.bitis = sonuc.zaman
            return "duzeldi", acik_kesinti
        return None, None
    if not kontrol.ardisik_hata:
        kontrol.ilk_hata_at = sonuc.zaman
    kontrol.ardisik_hata = int(kontrol.ardisik_hata or 0) + 1
    if acik_kesinti is not None:
        kontrol.son_durum = "down"
        return None, None
    if kontrol.ardisik_hata >= KESINTI_ESIGI:
        kontrol.son_durum = "down"
        yeni = UptimeKesintisi(
            kontrol_id=kontrol.id,
            site_id=kontrol.site_id,
            baslangic=kontrol.ilk_hata_at or sonuc.zaman,
            sebep=sonuc.hata_ozeti,
        )
        return "coktu", yeni
    return None, None


def gecerli_aralik(kontrol: UptimeKontrolu, modul_araligi: Optional[int]) -> int:
    return max(EN_AZ_ARALIK_DK, int(kontrol.aralik_dk or EN_AZ_ARALIK_DK), int(modul_araligi or 0))


def zamani_geldi_mi(kontrol: UptimeKontrolu, an: datetime, aralik_dk: int) -> bool:
    son = utc(kontrol.son_kontrol_at)
    return son is None or an - son >= timedelta(minutes=aralik_dk) - ARALIK_TOLERANSI


async def _gunluge_ekle(db: AsyncSession, onbellek: Dict[Tuple[int, str], UptimeGunluk], s: OlcumSonucu) -> None:
    gun = tr_gunu(s.zaman).isoformat()
    anahtar = (s.kontrol_id, gun)
    satir = onbellek.get(anahtar)
    if satir is None:
        satir = (
            await db.execute(
                select(UptimeGunluk).where(UptimeGunluk.kontrol_id == s.kontrol_id, UptimeGunluk.gun == gun)
            )
        ).scalar_one_or_none()
        if satir is None:
            satir = UptimeGunluk(kontrol_id=s.kontrol_id, site_id=s.site_id, gun=gun,
                                 toplam=0, basarili=0, toplam_sure_ms=0)
            db.add(satir)
        onbellek[anahtar] = satir
    satir.toplam = int(satir.toplam or 0) + 1
    satir.basarili = int(satir.basarili or 0) + (1 if s.basarili else 0)
    satir.toplam_sure_ms = float(satir.toplam_sure_ms or 0) + float(s.sure_ms or 0)


async def uptime_calistir(db: AsyncSession, zorla: bool = False) -> Dict[str, Any]:
    """Zamanı gelen açık kontrolleri paralel ölçer, sonuçları sırayla yazar.

    Ağ işi paralel (en çok 10 eşzamanlı, istek başına 10 sn), veritabanı işi
    tek oturumda sırayla: aynı oturuma eş zamanlı yazmak SQLAlchemy'de yasak.
    """
    from services.moduller import toplu_durumlar

    kontroller = list((await db.execute(select(UptimeKontrolu).where(UptimeKontrolu.acik.is_(True)))).scalars().all())
    if not kontroller:
        return {"kontrol": 0, "olculen": 0, "coktu": 0, "duzeldi": 0}
    siteler = {
        s.id: s
        for s in (
            await db.execute(select(Client_sites).where(Client_sites.id.in_({k.site_id for k in kontroller})))
        ).scalars().all()
    }
    mm = await toplu_durumlar(db, [s.client_email for s in siteler.values()])

    def modul_araligi(site: Client_sites) -> Optional[int]:
        m = mm.get((site.client_email or "").strip().lower())
        d = m.durumlar.get("uptime") if m else None
        try:
            return int((d.ayarlar or {}).get("kontrol_araligi_dk")) if d and d.acik else None
        except (TypeError, ValueError):
            return None

    an = simdi()
    zamani_gelen: List[UptimeKontrolu] = []
    for k in kontroller:
        site = siteler.get(k.site_id)
        if site is None:
            continue
        if zorla or zamani_geldi_mi(k, an, gecerli_aralik(k, modul_araligi(site))):
            zamani_gelen.append(k)
    zamani_gelen.sort(key=lambda k: utc(k.son_kontrol_at) or datetime.min.replace(tzinfo=timezone.utc))
    secilen = zamani_gelen[:UPTIME_PARTI]
    if not secilen:
        return {"kontrol": len(kontroller), "olculen": 0, "coktu": 0, "duzeldi": 0}

    async with sa._istemci(zaman_asimi=UPTIME_ZAMAN_ASIMI, eszamanlilik=UPTIME_ESZAMANLILIK, ajan=UPTIME_AJAN) as istemci:
        gezgin = sa.Gezgin(istemci, eszamanlilik=UPTIME_ESZAMANLILIK, zaman_asimi=UPTIME_ZAMAN_ASIMI)
        sonuclar = await asyncio.gather(*(tek_olcum(gezgin, k) for k in secilen))

    acik_kesintiler = {
        k.kontrol_id: k
        for k in (
            await db.execute(
                select(UptimeKesintisi).where(
                    UptimeKesintisi.kontrol_id.in_([k.id for k in secilen]), UptimeKesintisi.bitis.is_(None)
                )
            )
        ).scalars().all()
    }
    gunluk_onbellek: Dict[Tuple[int, str], UptimeGunluk] = {}
    olaylar: List[Tuple[str, UptimeKontrolu, UptimeKesintisi]] = []
    for kontrol, s in zip(secilen, sonuclar):
        db.add(UptimeOlcumu(
            kontrol_id=s.kontrol_id, site_id=s.site_id, zaman=s.zaman, durum_kodu=s.durum_kodu,
            sure_ms=s.sure_ms, basarili=s.basarili, hata_ozeti=s.hata_ozeti,
        ))
        await _gunluge_ekle(db, gunluk_onbellek, s)
        olay, kesinti = durum_gecisi(kontrol, s, acik_kesintiler.get(kontrol.id))
        if olay == "coktu" and kesinti is not None:
            db.add(kesinti)
        if olay and kesinti is not None:
            olaylar.append((olay, kontrol, kesinti))
    await db.commit()

    for olay, kontrol, kesinti in olaylar:
        await kesinti_bildir(db, olay, siteler[kontrol.site_id], kontrol, kesinti, mm)
    return {
        "kontrol": len(kontroller),
        "olculen": len(secilen),
        "bekleyen": max(0, len(zamani_gelen) - len(secilen)),
        "basarisiz": sum(1 for s in sonuclar if not s.basarili),
        "coktu": sum(1 for o in olaylar if o[0] == "coktu"),
        "duzeldi": sum(1 for o in olaylar if o[0] == "duzeldi"),
    }


async def kesinti_bildir(
    db: AsyncSession,
    olay: str,
    site: Client_sites,
    kontrol: UptimeKontrolu,
    kesinti: UptimeKesintisi,
    musteri_durumlari: Optional[Dict[str, Any]] = None,
) -> None:
    """`site_coktu` / `site_duzeldi` — yöneticiye her zaman, müşteriye uptime açıksa."""
    from services.notify import admin_recipients, dispatch, render

    try:
        eposta = (site.client_email or "").strip().lower()
        musteri_acik = False
        m = (musteri_durumlari or {}).get(eposta)
        if m is None:
            from services.moduller import modul_acik_mi

            musteri_acik = await modul_acik_mi(db, eposta, "uptime")
        else:
            d = m.durumlar.get("uptime")
            musteri_acik = bool(d and d.acik)
        alicilar = await admin_recipients(db)
        if musteri_acik and eposta:
            alicilar.append({"email": eposta, "role": "client"})
        if not alicilar:
            return
        basla = utc(kesinti.baslangic)
        bas_metin = basla.astimezone(TR).strftime("%d.%m.%Y %H:%M") if basla else ""
        if olay == "coktu":
            varsayilan_baslik = f"Site erişilemiyor: {site.ad} / Site is down: {site.ad}"
            varsayilan_govde = (
                f"{site.ad} ({kontrol.url}) {bas_metin} itibarıyla art arda iki kontrolde yanıt vermedi. "
                "Ekibimiz inceliyor.\n\n"
                f"{site.ad} ({kontrol.url}) has failed two consecutive checks since {bas_metin} (UTC+3). "
                "Our team is looking into it."
            )
        else:
            bitis = utc(kesinti.bitis) or simdi()
            dakika = max(1, int(((bitis - (basla or bitis)).total_seconds() + 59) // 60))
            varsayilan_baslik = f"Site yeniden erişilebilir: {site.ad} / Site is back up: {site.ad}"
            varsayilan_govde = (
                f"{site.ad} yeniden yanıt veriyor. Kesinti süresi yaklaşık {dakika} dakika.\n\n"
                f"{site.ad} is responding again. The outage lasted about {dakika} minutes."
            )
        olay_adi = "site_coktu" if olay == "coktu" else "site_duzeldi"
        baslik, govde = await render(db, olay_adi, varsayilan_baslik, varsayilan_govde,
                                     {"site": site.ad, "adres": kontrol.url, "baslangic": bas_metin})
        for alici in alicilar:
            await dispatch(
                db,
                event_type=olay_adi,
                title=baslik,
                body=govde,
                recipients=[alici],
                link=YONETICI_BAGLANTISI if alici["role"] == "admin" else MUSTERI_BAGLANTISI,
                ref_type="uptime_kesintisi",
                ref_id=kesinti.id,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Kesinti bildirimi gönderilemedi")


async def olcum_temizligi(db: AsyncSession) -> Dict[str, Any]:
    """90 günden eski ham ölçümler ve 400 günden eski günlük toplamlar."""
    an = simdi()
    s1 = await db.execute(delete(UptimeOlcumu).where(UptimeOlcumu.zaman < an - timedelta(days=OLCUM_SAKLAMA_GUN)))
    sinir_gun = tr_gunu(an - timedelta(days=GUNLUK_SAKLAMA_GUN)).isoformat()
    s2 = await db.execute(delete(UptimeGunluk).where(UptimeGunluk.gun < sinir_gun))
    await db.commit()
    return {"olcum_silinen": int(s1.rowcount or 0), "gunluk_silinen": int(s2.rowcount or 0)}


# --------------------------------------------------------------------------
# Toplulaştırma (panel kartları ve durum sayfası)
# --------------------------------------------------------------------------
def _oran(basarili: int, toplam: int) -> Optional[float]:
    return round(100.0 * basarili / toplam, 2) if toplam else None


async def uptime_ozetleri(
    db: AsyncSession, site_idleri: Sequence[int], gun_sayisi: int = GRAFIK_GUN, kesinti_sayisi: int = 5
) -> Dict[int, Dict[str, Any]]:
    """Site başına: güncel durum, 24s/7g/30g/90g %, 90 günlük çubuklar, son kesintiler."""
    idler = sorted(set(site_idleri))
    if not idler:
        return {}
    an = simdi()
    bugun = tr_gunu(an)
    ilk_gun = bugun - timedelta(days=gun_sayisi - 1)

    kontroller: Dict[int, List[UptimeKontrolu]] = {}
    for k in (await db.execute(select(UptimeKontrolu).where(UptimeKontrolu.site_id.in_(idler)))).scalars().all():
        kontroller.setdefault(k.site_id, []).append(k)

    gunler: Dict[int, Dict[str, List[int]]] = {}
    for g in (
        await db.execute(
            select(UptimeGunluk).where(UptimeGunluk.site_id.in_(idler), UptimeGunluk.gun >= ilk_gun.isoformat())
        )
    ).scalars().all():
        hucre = gunler.setdefault(g.site_id, {}).setdefault(g.gun, [0, 0])
        hucre[0] += int(g.basarili or 0)
        hucre[1] += int(g.toplam or 0)

    son24: Dict[int, Tuple[int, int]] = {}
    satirlar = await db.execute(
        select(
            UptimeOlcumu.site_id,
            func.count(UptimeOlcumu.id),
            func.sum(case((UptimeOlcumu.basarili.is_(True), 1), else_=0)),
        )
        .where(UptimeOlcumu.site_id.in_(idler), UptimeOlcumu.zaman >= an - timedelta(hours=24))
        .group_by(UptimeOlcumu.site_id)
    )
    for site_id, toplam, basarili in satirlar.all():
        son24[site_id] = (int(basarili or 0), int(toplam or 0))

    acik_kesinti: Dict[int, bool] = {}
    kesintiler: Dict[int, List[UptimeKesintisi]] = {}
    for k in (
        await db.execute(
            select(UptimeKesintisi)
            .where(UptimeKesintisi.site_id.in_(idler))
            .order_by(UptimeKesintisi.baslangic.desc(), UptimeKesintisi.id.desc())
        )
    ).scalars().all():
        if k.bitis is None:
            acik_kesinti[k.site_id] = True
        liste = kesintiler.setdefault(k.site_id, [])
        if len(liste) < kesinti_sayisi:
            liste.append(k)

    sonuc: Dict[int, Dict[str, Any]] = {}
    for site_id in idler:
        site_gunleri = gunler.get(site_id, {})
        cubuklar = []
        for i in range(gun_sayisi):
            gun = (ilk_gun + timedelta(days=i)).isoformat()
            b, t = site_gunleri.get(gun, (0, 0))
            cubuklar.append({"gun": gun, "oran": _oran(b, t), "olcum": t})

        def aralik(n: int) -> Optional[float]:
            b = t = 0
            for c in cubuklar[-n:]:
                hucre = site_gunleri.get(c["gun"], (0, 0))
                b += hucre[0]
                t += hucre[1]
            return _oran(b, t)

        ks = kontroller.get(site_id, [])
        if acik_kesinti.get(site_id):
            guncel = "kesinti"
        elif any(k.son_durum == "up" for k in ks if k.acik):
            guncel = "calisiyor"
        else:
            guncel = "bilinmiyor"
        son_kontrol = max((utc(k.son_kontrol_at) for k in ks if k.son_kontrol_at), default=None)
        b24, t24 = son24.get(site_id, (0, 0))
        sonuc[site_id] = {
            "guncel": guncel,
            "kontrol_sayisi": len(ks),
            "son_kontrol": iso(son_kontrol),
            "oran_24s": _oran(b24, t24),
            "oran_7g": aralik(7),
            "oran_30g": aralik(30),
            "oran_90g": aralik(gun_sayisi),
            "gunler": cubuklar,
            "kesintiler": [
                {
                    "id": k.id,
                    "baslangic": iso(k.baslangic),
                    "bitis": iso(k.bitis),
                    "sure_dk": (
                        max(1, int(((utc(k.bitis) - utc(k.baslangic)).total_seconds() + 59) // 60))  # type: ignore[operator]
                        if k.bitis and k.baslangic
                        else None
                    ),
                    "sebep": k.sebep,
                }
                for k in kesintiler.get(site_id, [])
            ],
        }
    return sonuc


def acik_ozet(ozet: Dict[str, Any]) -> Dict[str, Any]:
    """Herkese açık sayfa için: iç ayrıntı (sebep, ölçüm sayısı, kimlik) atılıyor."""
    return {
        "guncel": ozet["guncel"],
        "son_kontrol": ozet["son_kontrol"],
        "oran_24s": ozet["oran_24s"],
        "oran_7g": ozet["oran_7g"],
        "oran_30g": ozet["oran_30g"],
        "oran_90g": ozet["oran_90g"],
        "gunler": [{"gun": g["gun"], "oran": g["oran"]} for g in ozet["gunler"]],
        "kesintiler": [
            {"baslangic": k["baslangic"], "bitis": k["bitis"], "sure_dk": k["sure_dk"]}
            for k in ozet["kesintiler"]
        ],
    }


def izleme_sozlugu(iz: Optional[SiteIzleme], bugun: Optional[date] = None) -> Dict[str, Any]:
    """Kart için bitiş bilgileri (+ kalan gün). Müşteriye de bu gidiyor."""
    if iz is None:
        return {
            "alan_adi": None, "alan_bitis": None, "alan_kalan": None, "alan_bitis_kaynak": None,
            "alan_rdap_hata": None, "alan_saglayici": None, "ssl_bitis": None, "ssl_kalan": None,
            "ssl_hata": None, "ssl_elle_yenilenir": False, "hosting_bitis": None, "hosting_kalan": None,
            "hosting_saglayici": None, "notlar": None, "alan_kontrol_at": None,
            "durum_sayfasi_acik": False, "durum_slug": None, "durum_index": False,
        }
    return {
        "alan_adi": iz.alan_adi,
        "alan_bitis": iso(iz.alan_bitis),
        "alan_kalan": kalan_gun(iz.alan_bitis, bugun),
        "alan_bitis_kaynak": iz.alan_bitis_kaynak,
        "alan_rdap_hata": iz.alan_rdap_hata,
        "alan_saglayici": iz.alan_saglayici,
        "ssl_bitis": iso(iz.ssl_bitis),
        "ssl_kalan": kalan_gun(iz.ssl_bitis, bugun),
        "ssl_hata": iz.ssl_hata,
        "ssl_elle_yenilenir": bool(iz.ssl_elle_yenilenir),
        "hosting_bitis": iso(iz.hosting_bitis),
        "hosting_kalan": kalan_gun(iz.hosting_bitis, bugun),
        "hosting_saglayici": iz.hosting_saglayici,
        "notlar": iz.notlar,
        "alan_kontrol_at": iso(iz.alan_kontrol_at),
        "durum_sayfasi_acik": bool(iz.durum_sayfasi_acik),
        "durum_slug": iz.durum_slug,
        "durum_index": bool(iz.durum_index),
    }
