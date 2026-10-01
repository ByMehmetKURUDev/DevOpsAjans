"""Faz 3B — Google verisini `analytics_snapshots`'a eşitleme ve panonun okuma tarafı.

Ne yazılıyor?
-------------
Son 28 gün, önceki 28 günle karşılaştırılarak (değişim yüzdesi):

* GA4 (`channel=traffic`, `kaynak=google_analytics`): oturum, kullanıcı,
  sayfa görüntüleme, hemen çıkma oranı (%), ortalama etkileşim süresi (sn —
  `userEngagementDuration / activeUsers`, GA4 arayüzündeki "etkin kullanıcı
  başına ortalama etkileşim süresi"). Pencere dün biter.
* Search Console (`channel=seo`, `kaynak=search_console`): tıklama, gösterim,
  ortalama TO (%), ortalama sıra (gösterim ağırlıklı). Search Console verisi
  2–3 gün geriden geldiği için pencere 3 gün önce biter. Ayrıca en çok
  tıklanan 10 sorgu ve 10 sayfa `analitik_listeleri`ne.
* YouTube (`channel=youtube`, `kaynak=youtube`): abone (toplam; değişim =
  pencere içindeki net abone / pencere başındaki abone), görüntülenme,
  izlenme süresi (dk), yeni abone. Pencere 3 gün önce biter.

Satır anahtarı (kaynak, kanal, metrik, `snapshot_date` = eşitleme günü, UTC):
aynı gün tekrar çalışınca satır GÜNCELLENİR, çoğalmaz. Günler birikir (eğilim
için); 400 günden eski Google satırları siliniyor.

Kaynaklar bağımsız: biri hata verirse (API etkin değil, mülke erişim yok…)
diğerleri yazılır, hata kısa kodla `baglantilar.son_hata`'ya düşer.

Zaman sınırı: her Google isteği 10 sn, her kaynak en çok 20 sn (paralel).
Zamanlı tur (`services/zamanli.py`, 6 saatte bir) bu yüzden kısa kalıyor.
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from models.analytics_snapshots import Analytics_snapshots
from models.baglantilar import AnalitikListesi, Baglanti
from services import baglantilar as bg
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PENCERE_GUN = 28
#: Kaynak başına (paralel) üst sınır.
KAYNAK_ZAMAN_ASIMI = 20.0
SAKLAMA_GUN = 400
LISTE_SINIRI = 10

KAYNAK_GA = "google_analytics"
KAYNAK_SC = "search_console"
KAYNAK_YT = "youtube"
GOOGLE_KAYNAKLARI = (KAYNAK_GA, KAYNAK_SC, KAYNAK_YT)
ORNEK = "ornek"

#: Panodaki kanal sırası (bilinmeyen kanallar sona).
KANAL_SIRASI = ("traffic", "seo", "youtube", "ads", "social")

#: Kısa kaynak adı (seçim/hata anahtarı) → (snapshot kaynağı, kanal, seçim alanı)
KAYNAK_TANIMI = {
    "ga4": (KAYNAK_GA, "traffic", "ga4_mulk"),
    "sc": (KAYNAK_SC, "seo", "sc_site"),
    "yt": (KAYNAK_YT, "youtube", "yt_kanal"),
}

#: Sunucunun yazdığı Türkçe etiket (ön yüz metrik anahtarından 7 dilde çeviriyor).
ETIKETLER = {
    "sessions": "Oturum",
    "users": "Kullanıcı",
    "pageviews": "Sayfa Görüntüleme",
    "bounce_rate": "Hemen Çıkma Oranı",
    "avg_engagement_time": "Ort. Etkileşim Süresi",
    "organic_clicks": "Organik Tıklama",
    "impressions": "Gösterim",
    "ctr": "Ortalama TO",
    "avg_position": "Ortalama Sıra",
    "subscribers": "Abone",
    "views": "Görüntülenme",
    "watch_time": "İzlenme Süresi",
    "subscribers_gained": "Yeni Abone",
}


def bugun() -> date:
    return datetime.now(timezone.utc).date()


def pencereler(bit: date) -> Tuple[Tuple[str, str], Tuple[str, str]]:
    """((şimdiki başlangıç, bitiş), (önceki başlangıç, bitiş)) — ikisi de 28 gün."""
    bas = bit - timedelta(days=PENCERE_GUN - 1)
    onceki_bit = bas - timedelta(days=1)
    onceki_bas = onceki_bit - timedelta(days=PENCERE_GUN - 1)
    return (bas.isoformat(), bit.isoformat()), (onceki_bas.isoformat(), onceki_bit.isoformat())


def degisim(simdiki: Optional[float], onceki: Optional[float]) -> Optional[float]:
    if simdiki is None or onceki is None or onceki == 0:
        return None
    return round((simdiki - onceki) / abs(onceki) * 100, 1)


def _sayi(deger: Any) -> float:
    try:
        return float(deger)
    except (TypeError, ValueError):
        return 0.0


def _metrik(anahtar: str, deger: float, onceki: Optional[float], birim: str = "") -> Dict[str, Any]:
    return {
        "metric_key": anahtar,
        "metric_label": ETIKETLER.get(anahtar, anahtar),
        "metric_value": deger,
        "change_pct": degisim(deger, onceki),
        "unit": birim,
    }


# ---------------------------------------------------------------------------
# GA4
# ---------------------------------------------------------------------------
GA_METRIKLERI = ("sessions", "totalUsers", "screenPageViews", "bounceRate", "userEngagementDuration", "activeUsers")


def ga4_metrikleri_hesapla(govde: Dict[str, Any]) -> List[Dict[str, Any]]:
    """runReport yanıtı (iki adlı tarih aralığı: simdi / onceki) → metrik listesi."""
    basliklar = [str(h.get("name")) for h in govde.get("metricHeaders") or []] or list(GA_METRIKLERI)
    araliklar: Dict[str, Dict[str, float]] = {"simdi": {}, "onceki": {}}
    for satir in govde.get("rows") or []:
        boyut = ((satir.get("dimensionValues") or [{}])[0] or {}).get("value")
        # Adsız aralıklarda Google date_range_0/1 yazıyor; istekte sıra (onceki, simdi) değil (simdi, onceki).
        ad = {"date_range_0": "simdi", "date_range_1": "onceki"}.get(boyut, boyut)
        if ad not in araliklar:
            continue
        degerler = satir.get("metricValues") or []
        araliklar[ad] = {b: _sayi((degerler[i] or {}).get("value")) for i, b in enumerate(basliklar) if i < len(degerler)}

    def ortalama_sure(a: Dict[str, float]) -> Optional[float]:
        aktif = a.get("activeUsers") or 0
        return round(a.get("userEngagementDuration", 0) / aktif) if aktif else (0.0 if a else None)

    s, o = araliklar["simdi"], araliklar["onceki"]
    oncesi_var = bool(o)

    def oc(deger: Optional[float]) -> Optional[float]:
        return deger if oncesi_var else None

    return [
        _metrik("sessions", s.get("sessions", 0.0), oc(o.get("sessions", 0.0))),
        _metrik("users", s.get("totalUsers", 0.0), oc(o.get("totalUsers", 0.0))),
        _metrik("pageviews", s.get("screenPageViews", 0.0), oc(o.get("screenPageViews", 0.0))),
        _metrik("bounce_rate", round(s.get("bounceRate", 0.0) * 100, 1), oc(round(o.get("bounceRate", 0.0) * 100, 1)), "%"),
        _metrik("avg_engagement_time", float(ortalama_sure(s) or 0), oc(ortalama_sure(o)), "sn"),
    ]


async def _ga4(jeton: str, mulk: str) -> Dict[str, Any]:
    (bas, bit), (obas, obit) = pencereler(bugun() - timedelta(days=1))
    govde = await bg._api(
        "POST",
        f"{bg.GA_DATA}/{mulk}:runReport",
        jeton,
        json_govde={
            "dateRanges": [
                {"startDate": bas, "endDate": bit, "name": "simdi"},
                {"startDate": obas, "endDate": obit, "name": "onceki"},
            ],
            "metrics": [{"name": m} for m in GA_METRIKLERI],
        },
    )
    return {"metrikler": ga4_metrikleri_hesapla(govde), "donem": [bas, bit]}


# ---------------------------------------------------------------------------
# Search Console
# ---------------------------------------------------------------------------
def sc_metrikleri_hesapla(satirlar: Iterable[Dict[str, Any]], bas: str) -> List[Dict[str, Any]]:
    """Günlük satırlar (56 gün) → şimdiki/önceki pencere toplamları."""
    toplam = {"simdi": [0.0, 0.0, 0.0], "onceki": [0.0, 0.0, 0.0]}  # tıklama, gösterim, sıra×gösterim
    for r in satirlar:
        gun = str((r.get("keys") or [""])[0])
        pencere = "simdi" if gun >= bas else "onceki"
        tik, gos = _sayi(r.get("clicks")), _sayi(r.get("impressions"))
        toplam[pencere][0] += tik
        toplam[pencere][1] += gos
        toplam[pencere][2] += _sayi(r.get("position")) * gos

    def hesap(t: List[float]) -> Tuple[float, float, Optional[float], Optional[float]]:
        tik, gos, agirlikli = t
        to = round(tik / gos * 100, 2) if gos else None
        sira = round(agirlikli / gos, 1) if gos else None
        return tik, gos, to, sira

    s, o = hesap(toplam["simdi"]), hesap(toplam["onceki"])
    oncesi_var = toplam["onceki"][1] > 0 or toplam["onceki"][0] > 0
    return [
        _metrik("organic_clicks", s[0], o[0] if oncesi_var else None),
        _metrik("impressions", s[1], o[1] if oncesi_var else None),
        _metrik("ctr", s[2] or 0.0, o[2], "%"),
        _metrik("avg_position", s[3] or 0.0, o[3]),
    ]


def sc_listesi(govde: Dict[str, Any]) -> List[Dict[str, Any]]:
    liste = []
    for r in (govde.get("rows") or [])[:LISTE_SINIRI]:
        liste.append({
            "anahtar": str((r.get("keys") or [""])[0])[:300],
            "tiklama": int(_sayi(r.get("clicks"))),
            "gosterim": int(_sayi(r.get("impressions"))),
            "to": round(_sayi(r.get("ctr")) * 100, 2),
            "sira": round(_sayi(r.get("position")), 1),
        })
    return liste


async def _sc(jeton: str, site: str) -> Dict[str, Any]:
    (bas, bit), (obas, _obit) = pencereler(bugun() - timedelta(days=3))
    adres = f"{bg.SC_TABAN}/sites/{quote(site, safe='')}/searchAnalytics/query"
    gunluk, sorgular, sayfalar = await asyncio.gather(
        bg._api("POST", adres, jeton, json_govde={
            "startDate": obas, "endDate": bit, "dimensions": ["date"], "type": "web", "rowLimit": 100,
        }),
        bg._api("POST", adres, jeton, json_govde={
            "startDate": bas, "endDate": bit, "dimensions": ["query"], "type": "web", "rowLimit": LISTE_SINIRI,
        }),
        bg._api("POST", adres, jeton, json_govde={
            "startDate": bas, "endDate": bit, "dimensions": ["page"], "type": "web", "rowLimit": LISTE_SINIRI,
        }),
    )
    return {
        "metrikler": sc_metrikleri_hesapla(gunluk.get("rows") or [], bas),
        "listeler": {"sorgular": sc_listesi(sorgular), "sayfalar": sc_listesi(sayfalar)},
        "donem": [bas, bit],
    }


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------
def yt_metrikleri_hesapla(abone: Optional[float], rapor: Dict[str, Any], bas: str) -> List[Dict[str, Any]]:
    adlar = [str(h.get("name")) for h in rapor.get("columnHeaders") or []]
    toplam = {"simdi": {}, "onceki": {}}
    for satir in rapor.get("rows") or []:
        kayit = dict(zip(adlar, satir))
        pencere = "simdi" if str(kayit.get("day", "")) >= bas else "onceki"
        for ad in ("views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"):
            toplam[pencere][ad] = toplam[pencere].get(ad, 0.0) + _sayi(kayit.get(ad))
    s, o = toplam["simdi"], toplam["onceki"]
    oncesi_var = bool(o)
    net = s.get("subscribersGained", 0.0) - s.get("subscribersLost", 0.0)
    metrikler = []
    if abone is not None:
        baslangic = abone - net
        metrikler.append(_metrik("subscribers", abone, baslangic if baslangic > 0 else None))
    metrikler += [
        _metrik("views", s.get("views", 0.0), o.get("views", 0.0) if oncesi_var else None),
        _metrik("watch_time", s.get("estimatedMinutesWatched", 0.0),
                o.get("estimatedMinutesWatched", 0.0) if oncesi_var else None, "dk"),
        _metrik("subscribers_gained", s.get("subscribersGained", 0.0),
                o.get("subscribersGained", 0.0) if oncesi_var else None),
    ]
    return metrikler


async def _yt(jeton: str, kanal: str) -> Dict[str, Any]:
    (bas, bit), (obas, _obit) = pencereler(bugun() - timedelta(days=3))
    kanal_govde, rapor = await asyncio.gather(
        bg._api("GET", bg.YT_KANALLAR, jeton, parametreler={"part": "statistics", "id": kanal}),
        bg._api("GET", bg.YT_RAPOR, jeton, parametreler={
            "ids": f"channel=={kanal}", "startDate": obas, "endDate": bit,
            "metrics": "views,estimatedMinutesWatched,subscribersGained,subscribersLost",
            "dimensions": "day", "sort": "day",
        }),
    )
    abone: Optional[float] = None
    for k in kanal_govde.get("items") or []:
        if k.get("id") == kanal:
            ist = k.get("statistics") or {}
            if not ist.get("hiddenSubscriberCount"):
                abone = _sayi(ist.get("subscriberCount"))
    return {"metrikler": yt_metrikleri_hesapla(abone, rapor, bas), "donem": [bas, bit]}


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------
async def _metrikleri_yaz(db: AsyncSession, kaynak: str, kanal: str, metrikler: List[Dict[str, Any]], gun: str) -> int:
    """(kaynak, kanal, metrik, gün) başına tek satır: varsa güncelle, yoksa ekle."""
    mevcut = {
        s.metric_key: s
        for s in (
            await db.execute(
                select(Analytics_snapshots).where(
                    Analytics_snapshots.kaynak == kaynak,
                    Analytics_snapshots.channel == kanal,
                    Analytics_snapshots.snapshot_date == gun,
                )
            )
        ).scalars().all()
    }
    for m in metrikler:
        satir = mevcut.get(m["metric_key"])
        if satir is None:
            db.add(Analytics_snapshots(channel=kanal, snapshot_date=gun, kaynak=kaynak, **m))
        else:
            satir.metric_label = m["metric_label"]
            satir.metric_value = m["metric_value"]
            satir.change_pct = m["change_pct"]
            satir.unit = m["unit"]
    return len(metrikler)


async def _listeyi_yaz(db: AsyncSession, sahip: str, kaynak: str, tur: str, veri: List[Dict[str, Any]], donem: List[str]) -> None:
    satir = (
        await db.execute(
            select(AnalitikListesi).where(
                AnalitikListesi.sahip_anahtari == sahip, AnalitikListesi.kaynak == kaynak, AnalitikListesi.tur == tur
            )
        )
    ).scalar_one_or_none()
    if satir is None:
        satir = AnalitikListesi(sahip_anahtari=sahip, kaynak=kaynak, tur=tur)
        db.add(satir)
    satir.veri = json.dumps(veri, ensure_ascii=False)
    satir.donem_bas, satir.donem_bit = donem[0], donem[1]


ISLEVLER = {"ga4": _ga4, "sc": _sc, "yt": _yt}


async def esitle(db: AsyncSession, b: Baglanti) -> Dict[str, Any]:
    """Seçili kaynakları çekip yazar. Dönen özet: {"yazilan", "kaynaklar", "hatalar"}."""
    bg.kurulum_iste()
    secimler = bg.secimleri_oku(b)
    b.son_deneme = bg.simdi()
    await db.commit()
    hatalar: Dict[str, str] = {}
    try:
        jeton = await bg.erisim_jetonu(db, b)
    except bg.BaglantiHatasi as h:
        if h.kod != "yeniden_baglan":  # yeniden_baglan zaten işaretlendi
            b.son_hata = json.dumps({"genel": h.kod})
            await db.commit()
        raise

    calisacak = []
    for kisa, (_kaynak, _kanal, alan) in KAYNAK_TANIMI.items():
        secim = secimler.get(alan)
        if not secim:
            continue
        if not bg.kapsam_var(b, kisa):
            hatalar[kisa] = "kapsam_yok"
            continue
        calisacak.append((kisa, secim))
    yanitlar = await asyncio.gather(
        *(asyncio.wait_for(ISLEVLER[k](jeton, s), KAYNAK_ZAMAN_ASIMI) for k, s in calisacak), return_exceptions=True
    )
    gun = bugun().isoformat()
    yazilan = 0
    basarili: List[str] = []
    for (kisa, _secim), y in zip(calisacak, yanitlar):
        kaynak, kanal, _alan = KAYNAK_TANIMI[kisa]
        if isinstance(y, bg.BaglantiHatasi):
            hatalar[kisa] = y.kod
            if y.kod == "yetki_yok":
                bg.bellegi_temizle(b.id)
            continue
        if isinstance(y, asyncio.TimeoutError):
            hatalar[kisa] = "zaman_asimi"
            continue
        if isinstance(y, BaseException):
            logger.warning("Google eşitleme hatası (%s): %s", kisa, type(y).__name__)
            hatalar[kisa] = "google_hatasi"
            continue
        yazilan += await _metrikleri_yaz(db, kaynak, kanal, y["metrikler"], gun)
        for tur, liste in (y.get("listeler") or {}).items():
            await _listeyi_yaz(db, b.sahip_anahtari, kaynak, tur, liste, y["donem"])
        basarili.append(kisa)

    # Eski Google satırları (eğilim için 400 gün yeter).
    sinir = (bugun() - timedelta(days=SAKLAMA_GUN)).isoformat()
    await db.execute(
        delete(Analytics_snapshots).where(
            Analytics_snapshots.kaynak.in_(GOOGLE_KAYNAKLARI), Analytics_snapshots.snapshot_date < sinir
        )
    )
    if basarili:
        b.son_esitleme = bg.simdi()
    b.son_hata = json.dumps(hatalar) if hatalar else None
    await db.commit()
    return {"yazilan": yazilan, "kaynaklar": basarili, "hatalar": hatalar}


async def elle_esitle(db: AsyncSession, hesap_email: Optional[str] = None) -> Dict[str, Any]:
    bg.kurulum_iste()
    b = await bg.baglanti_getir(db, hesap_email)
    if b is None:
        raise bg.BaglantiHatasi("bagli_degil", 404)
    if b.durum != "bagli":
        raise bg.BaglantiHatasi("yeniden_baglan", 409)
    if not any(bg.secimleri_oku(b).values()):
        raise bg.BaglantiHatasi("secim_yok", 400)
    kalan = bg.elle_bekleme_sn(b)
    if kalan > 0:
        raise bg.BaglantiHatasi("cok_sik", 429, kalan_sn=kalan)
    return await esitle(db, b)


async def zamanli_esitleme(db: AsyncSession) -> Dict[str, Any]:
    """Zamanlı görev (6 saatte bir): bağlı ve seçimi olan her Google bağlantısı."""
    if not bg.kurulum_durumu()["kurulu"]:
        return {"atlandi": "kurulmadi"}
    baglantilar = (
        await db.execute(select(Baglanti).where(Baglanti.saglayici == bg.GOOGLE, Baglanti.durum == "bagli"))
    ).scalars().all()
    ozet: Dict[str, Any] = {"baglanti": 0, "yazilan": 0, "hata": 0}
    for b in baglantilar:
        if not any(bg.secimleri_oku(b).values()):
            continue
        ozet["baglanti"] += 1
        try:
            sonuc = await esitle(db, b)
            ozet["yazilan"] += sonuc["yazilan"]
            ozet["hata"] += len(sonuc["hatalar"])
        except bg.BaglantiHatasi as h:
            ozet["hata"] += 1
            ozet.setdefault("kodlar", []).append(h.kod)
    return ozet


# ---------------------------------------------------------------------------
# Pano (yönetici "Anlık Analitik")
# ---------------------------------------------------------------------------
def _satir_sozluk(s: Analytics_snapshots) -> Dict[str, Any]:
    return {
        "id": s.id,
        "channel": s.channel,
        "metric_key": s.metric_key,
        "metric_label": s.metric_label,
        "metric_value": s.metric_value,
        "change_pct": s.change_pct,
        "unit": s.unit,
        "snapshot_date": s.snapshot_date,
        "kaynak": s.kaynak,
    }


async def pano_verisi(db: AsyncSession) -> Dict[str, Any]:
    """Kanal başına gösterilecek satırlar.

    Kural: bir kanalda gerçek veri (kaynağı `ornek` olmayan — Google ya da
    elle girilmiş) varsa o kanalın örnek satırları HİÇ dönmüyor. Yalnız örnek
    varsa satırlar `ornek: true` işaretiyle dönüyor; pano şerit gösteriyor.
    Her kanalda metrik başına en güncel satır.
    """
    gercek = (
        await db.execute(
            select(Analytics_snapshots)
            .where(or_(Analytics_snapshots.kaynak.is_(None), Analytics_snapshots.kaynak != ORNEK))
            .order_by(Analytics_snapshots.id.desc())
            .limit(5000)
        )
    ).scalars().all()
    ornek = (
        await db.execute(select(Analytics_snapshots).where(Analytics_snapshots.kaynak == ORNEK))
    ).scalars().all()

    def en_guncel(satirlar: Iterable[Analytics_snapshots]) -> Dict[str, List[Dict[str, Any]]]:
        sirali = sorted(satirlar, key=lambda s: (s.snapshot_date or "", s.id or 0), reverse=True)
        harita: Dict[str, List[Dict[str, Any]]] = {}
        for s in sirali:
            liste = harita.setdefault(s.channel, [])
            if not any(m["metric_key"] == s.metric_key for m in liste):
                liste.append(_satir_sozluk(s))
        # Kart sırası yazılış sırası (oturum, kullanıcı, … — eşitleme ve mock aynı sırayla yazıyor).
        for liste in harita.values():
            liste.sort(key=lambda m: m["id"] or 0)
        return harita

    g, o = en_guncel(gercek), en_guncel(ornek)
    adlar = sorted(set(g) | set(o), key=lambda k: (KANAL_SIRASI.index(k) if k in KANAL_SIRASI else 99, k))
    kanallar = []
    for ad in adlar:
        if ad in g:
            satirlar = g[ad]
            kaynaklar = sorted({s["kaynak"] or "elle" for s in satirlar})
            kanallar.append({"kanal": ad, "ornek": False, "kaynaklar": kaynaklar, "metrikler": satirlar,
                             "tarih": max((s["snapshot_date"] or "" for s in satirlar), default="") or None})
        else:
            kanallar.append({"kanal": ad, "ornek": True, "kaynaklar": [ORNEK], "metrikler": o[ad], "tarih": None})

    listeler: Dict[str, Any] = {}
    for satir in (
        await db.execute(select(AnalitikListesi).where(AnalitikListesi.sahip_anahtari == bg.AJANS))
    ).scalars().all():
        try:
            veri = json.loads(satir.veri) if satir.veri else []
        except ValueError:
            veri = []
        listeler[satir.tur] = {"kaynak": satir.kaynak, "donem": [satir.donem_bas, satir.donem_bit], "satirlar": veri}

    return {
        "kanallar": kanallar,
        "yalniz_ornek": bool(kanallar) and all(k["ornek"] for k in kanallar),
        "listeler": listeler,
    }
