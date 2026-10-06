"""Faz 7O — yöneticiye haftalık özet ("bu hafta neye bakmalıyım?").

Ne zaman
--------
Zamanlı iş `haftalik_ozet` (`services/zamanli.py`, 30 dakikada bir denetlenir). Gönderim Europe/Istanbul
saatiyle PAZARTESİ 08:00'den sonraki ilk turda; ISO hafta başına BİR kez. Kilit `hatirlatma_izleri`
(tur=`haftalik_ozet`, ref=YYYYHH, eşik 0) benzersiz satırı: aynı hafta ikinci tur (ya da yöneticinin
"Şimdi çalıştır"ı) yeniden göndermez. Sunucu Pazartesi hiç uyanmadıysa haftanın ilk turunda gider.

* Bütün sayılar sıfırsa GÖNDERİLMEZ (hafta yine "yapıldı" işaretlenir: hafta ortasında bir şey çıktı
  diye özet Perşembe gelmesin).
* Açık/kapalı TEK kaynak: bildirim matrisi, yönetici satırı `haftalik_ozet` × e-posta hücresi
  (`services/bildirim_tercih.py`). Kapalıysa hiç dağıtılmaz (panel içi de yok) ve hafta işaretlenmez:
  yönetici hafta içinde açarsa o haftanın özeti bir sonraki turda gelir. Otomasyon › Sistem kartındaki
  düğme de aynı hücreyi değiştirir.
* Kişi kendi bildirim tercihinden e-postayı kapatabilir (dağıtıcının olağan kuralı).

İçerik (bölüm başına sayı + en çok 5 örnek satır): vadesi geçmiş faturalar (para birimine göre kalan),
açık destek talepleri ve SLA ihlalleri, gelen kutusunda yanıt bekleyenler (Faz 5G; destek talepleri ve
CRM bölümündeki adayların talepleri hariç — çift sayım yok, bkz. `_gelen_kutusu`), sonraki adımı gelmiş / 7+ gündür hareketsiz CRM adayları, 3+
gündür yanıtsız teklifler, müşteri onayı bekleyen içerikler, bekleyen belge talepleri, 14 gün içinde
yenilenecek alan adı / SSL (elle yenilenen) / hosting, şu an erişilemeyen siteler.

Dil: diğer yönetici bildirimleri gibi Türkçe; başlık/gövde panelden `notify_tpl_haftalik_ozet_*`
ile değiştirilebilir (`render`). Önizleme (`ozet_hazirla`) yapılandırılmış veri döner; panel kendi
dilinde biçimler.
"""

import html
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

OLAY = "haftalik_ozet"
IZ_TURU = "haftalik_ozet"
SAAT_DILIMI = "Europe/Istanbul"
BASLANGIC_SAATI = 8
ORNEK_SINIRI = 5
YANITSIZ_GUN = 3
HAREKETSIZ_GUN = 7
YENILEME_GUN = 14
#: Süresi bu kadar günden önce dolmuş kalem "yenilenecek" listesinde gösterilmez (çoktan bırakılmış).
YENILEME_GECMIS_GUN = 30
PANEL_BAGLANTISI = "/admin?sekme=otomasyon&bolum=sistem"

AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Any) -> Optional[datetime]:
    if not isinstance(an, datetime):
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def _iso(an: Any) -> Optional[str]:
    u = _utc(an)
    return u.isoformat().replace("+00:00", "Z") if u else None


def yerel(an: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return _utc(an).astimezone(ZoneInfo(SAAT_DILIMI))  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - tz veritabanı yoksa Türkiye UTC+3 (yaz saati yok)
        return _utc(an).astimezone(timezone(timedelta(hours=3)))  # type: ignore[union-attr]


def hafta_kimligi(an: datetime) -> int:
    """ISO yıl × 100 + ISO hafta (İstanbul günü): 2026-W41 → 202641."""
    yil, hafta, _ = yerel(an).isocalendar()
    return yil * 100 + hafta


def hafta_etiketi(an: datetime) -> str:
    yil, hafta, _ = yerel(an).isocalendar()
    return f"{yil}-W{hafta:02d}"


def pencere_acik_mi(an: datetime) -> bool:
    """Bu ISO haftanın Pazartesi 08:00'i (İstanbul) geçti mi? (Pazartesi 00:00–07:59 kapalı.)"""
    y = yerel(an)
    return not (y.weekday() == 0 and y.hour < BASLANGIC_SAATI)


def _pazartesi_0800(an: datetime) -> datetime:
    y = yerel(an)
    gun = (y - timedelta(days=y.weekday())).replace(hour=BASLANGIC_SAATI, minute=0, second=0, microsecond=0)
    return gun.astimezone(timezone.utc)


def _bugun(an: datetime) -> date:
    return yerel(an).date()


def _bolum(anahtar: str, sekme: str, sayi: int, ornekler: List[Dict[str, Any]], **ek: Any) -> Dict[str, Any]:
    return {"anahtar": anahtar, "sekme": sekme, "sayi": int(sayi), "ek": ek, "ornekler": ornekler[:ORNEK_SINIRI]}


def _satir(ad: Any, *, ayrinti: Any = None, tur: Optional[str] = None, gun: Optional[int] = None,
           tutar: Optional[float] = None, para_birimi: Optional[str] = None, zaman: Any = None) -> Dict[str, Any]:
    return {"ad": str(ad or "—")[:120], "ayrinti": (str(ayrinti)[:120] if ayrinti else None), "tur": tur, "gun": gun,
            "tutar": tutar, "para_birimi": para_birimi, "zaman": _iso(zaman) if isinstance(zaman, datetime) else zaman}


# ---------------------------------------------------------------------------
# Bölümler
# ---------------------------------------------------------------------------
async def _faturalar(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.invoices import Invoices
    from services.faturalar import EPS, KAPALI_DURUMLAR, bakiye, tarih_coz

    bugun = _bugun(an)
    adaylar = (
        await db.execute(
            select(Invoices).where(
                or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
                or_(Invoices.status.is_(None), Invoices.status.notin_(KAPALI_DURUMLAR)),
                Invoices.due_date.isnot(None), Invoices.due_date != "",
            ).order_by(Invoices.id.desc()).limit(500)
        )
    ).scalars().all()
    satirlar = []
    toplamlar: Dict[str, float] = {}
    for f in adaylar:
        vade = tarih_coz(f.due_date)
        if vade is None or vade >= bugun:
            continue
        b = await bakiye(db, f)
        if b.kalan <= EPS:
            continue
        birim = (f.currency or "TRY").upper()
        kalan = float(b.kalan)
        toplamlar[birim] = round(toplamlar.get(birim, 0.0) + kalan, 2)
        satirlar.append(_satir(f.invoice_no, ayrinti=f.client_name or f.client_email, tur="gecikme",
                               gun=(bugun - vade).days, tutar=round(kalan, 2), para_birimi=birim))
    satirlar.sort(key=lambda s: -(s["gun"] or 0))
    return _bolum("faturalar", "invoices", len(satirlar), satirlar,
                  toplamlar=[{"para_birimi": k, "tutar": v} for k, v in sorted(toplamlar.items())])


async def _destek(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.destek_sla import TalepSla
    from models.support_tickets import Support_tickets
    from services import sla

    talepler = (
        await db.execute(
            select(Support_tickets)
            .where(func.coalesce(Support_tickets.status, "open").notin_(list(sla.KAPALI_DURUMLAR)))
            .order_by(Support_tickets.id.asc())
            .limit(500)
        )
    ).scalars().all()
    if not talepler:
        return _bolum("destek", "tickets", 0, [], sla_asildi=0)
    ayar = await sla.ayarlari_oku(db)
    satirlar_sla = {
        s.ticket_id: s for s in (await db.execute(
            select(TalepSla).where(TalepSla.ticket_id.in_([t.id for t in talepler]))
        )).scalars().all()
    }
    asilan, digerleri = [], []
    for t in talepler:
        s = satirlar_sla.get(t.id)
        gun = max(0, (an - (_utc(t.created_at) or an)).days)
        if s is not None and sla.ozet_durum(sla.durum_sozlugu(s, ayar, an)) == "asildi":
            asilan.append(_satir(f"#{t.id} {t.subject or ''}".strip(), ayrinti=t.client_name or t.client_email,
                                 tur="sla_asildi", gun=gun))
        else:
            digerleri.append(_satir(f"#{t.id} {t.subject or ''}".strip(), ayrinti=t.client_name or t.client_email,
                                    tur="acik", gun=gun))
    digerleri.sort(key=lambda s: -(s["gun"] or 0))
    return _bolum("destek", "tickets", len(talepler), asilan + digerleri, sla_asildi=len(asilan))


#: Faz 5G — haftalık özette gelen kutusu kaynaklarının Türkçe adları (e-posta metni).
GELEN_KAYNAK_ADLARI = {
    "iletisim": "İletişim formu", "fiyat_teklifi": "Fiyat teklifi isteği", "sohbet": "Müşteri sohbeti",
    "kartvizit": "Kartvizit mesajı", "randevu": "Randevu", "geri_bildirim": "Hata bildirimi",
    "icerik_revizyon": "İçerik revizyonu", "belge": "Yüklenen belge",
}


async def _gelen_kutusu(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    """Faz 5G — gelen kutusunda yanıt bekleyenler. ÇİFT SAYIM YOK:

    * Destek talepleri sayılmıyor: "Açık destek talepleri" bölümü onları SLA durumuyla zaten sayıyor.
    * İletişim formu / fiyat teklifi isteğinin CRM adayı "Takip bekleyen CRM adayları" bölümünde zaten
      görünüyorsa (sonraki adımı gelmiş ya da 7+ gündür hareketsiz) burada sayılmıyor.
    * Müşteri onayı bekleyen içerik / bekleyen belge talebi (top müşteride) ile gelen kutusundaki
      içerik revizyonu / yüklenen belge (top bizde) zaten ayrık kümeler.
    """
    from models.crm import CrmAdaylari
    from services import crm
    from services import gelen_kutusu as gk

    bg = gk.Baglam(kisi="", an=an)
    sz = gk.Suzgec(durum="bekleyen")
    ogeler: List[Dict[str, Any]] = []
    for kaynak in gk.KAYNAKLAR:
        if kaynak == "destek":
            continue
        ogeler += [o for o in await gk._kaynagi_yukle(db, kaynak, sz, bg) if o["durum"] in gk.BEKLEYEN]
    aday_idleri = {o["ek"].get("crm_aday_id") for o in ogeler if o["kaynak"] in ("iletisim", "fiyat_teklifi")} - {None}
    crmde: set = set()
    if aday_idleri:
        acik = await crm.acik_asama_anahtarlari(db)
        adaylar = (
            await db.execute(select(CrmAdaylari).where(CrmAdaylari.id.in_(list(aday_idleri)), CrmAdaylari.asama.in_(acik)))
        ).scalars().all() if acik else []
        sonlar = await crm.son_hareketler(db, adaylar) if adaylar else {}
        bugun = _bugun(an)
        for a in adaylar:
            tarih = crm.tarih_coz(a.sonraki_adim_tarihi)
            son = sonlar.get(int(a.id))
            if (tarih is not None and tarih <= bugun) or (son is not None and (an - son).days >= HAREKETSIZ_GUN):
                crmde.add(int(a.id))
    ogeler = [o for o in ogeler if o["ek"].get("crm_aday_id") not in crmde or o["ek"].get("crm_aday_id") is None]
    ogeler.sort(key=lambda o: o["_zaman"])  # en uzun bekleyen önce
    kaynaklar: Dict[str, int] = {}
    for o in ogeler:
        kaynaklar[o["kaynak"]] = kaynaklar.get(o["kaynak"], 0) + 1
    satirlar = [
        _satir(o.get("kisi_ad") or o.get("kisi_eposta"), ayrinti=o.get("baslik") or o.get("ozet"), tur="yanit_bekliyor",
               gun=max(0, (an - o["_zaman"]).days))
        for o in ogeler
    ]
    return _bolum("gelen_kutusu", "gelenKutusu", len(satirlar), satirlar, kaynaklar=kaynaklar)


async def _crm(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.crm import CrmAdaylari
    from services import crm

    acik = await crm.acik_asama_anahtarlari(db)
    if not acik:
        return _bolum("crm", "crm", 0, [], sonraki_adim=0, hareketsiz=0)
    bugun = _bugun(an)
    adaylar = (
        await db.execute(select(CrmAdaylari).where(CrmAdaylari.asama.in_(acik)).order_by(CrmAdaylari.id.desc()).limit(2000))
    ).scalars().all()
    sonlar = await crm.son_hareketler(db, adaylar)
    adim, hareketsiz = [], []
    for a in adaylar:
        tarih = crm.tarih_coz(a.sonraki_adim_tarihi)
        if tarih is not None and tarih <= bugun:
            adim.append(_satir(a.ad, ayrinti=a.sonraki_adim or a.firma, tur="sonraki_adim", gun=(bugun - tarih).days))
            continue
        son = sonlar.get(int(a.id))
        if son is not None and (an - son).days >= HAREKETSIZ_GUN:
            hareketsiz.append(_satir(a.ad, ayrinti=a.firma or a.email, tur="hareketsiz", gun=(an - son).days))
    adim.sort(key=lambda s: -(s["gun"] or 0))
    hareketsiz.sort(key=lambda s: -(s["gun"] or 0))
    return _bolum("crm", "crm", len(adim) + len(hareketsiz), adim + hareketsiz, sonraki_adim=len(adim),
                  hareketsiz=len(hareketsiz))


async def _teklifler(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.teklifler import Teklifler
    from services.teklifler import ACIK_DURUMLAR, suresi_gecti_mi

    liste = (
        await db.execute(
            select(Teklifler).where(
                Teklifler.durum.in_(ACIK_DURUMLAR), Teklifler.gonderildi_at.isnot(None),
                Teklifler.gonderildi_at <= an - timedelta(days=YANITSIZ_GUN),
            ).order_by(Teklifler.gonderildi_at.asc()).limit(500)
        )
    ).scalars().all()
    satirlar = []
    for t in liste:
        if suresi_gecti_mi(t, _bugun(an)):
            continue
        satirlar.append(_satir(t.no, ayrinti=t.baslik, tur="yanitsiz_goruldu" if int(t.goruntulenme_sayisi or 0) else "yanitsiz",
                               gun=(an - _utc(t.gonderildi_at)).days, tutar=float(t.genel_toplam or 0),  # type: ignore[operator]
                               para_birimi=t.para_birimi))
    return _bolum("teklifler", "teklifler", len(satirlar), satirlar)


async def _icerik(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.content_posts import Content_posts

    liste = (
        await db.execute(
            select(Content_posts).where(Content_posts.status == "musteri_onayi").order_by(Content_posts.id.asc()).limit(500)
        )
    ).scalars().all()
    satirlar = [
        _satir(g.title, ayrinti=g.hesap_email, tur="onay_bekliyor",
               gun=max(0, (an - (_utc(g.durum_at) or _utc(g.updated_at) or an)).days))
        for g in liste
    ]
    satirlar.sort(key=lambda s: -(s["gun"] or 0))
    return _bolum("icerik", "icerik", len(satirlar), satirlar)


async def _belgeler(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.dosyalar import BelgeTalepleri
    from services.faturalar import tarih_coz

    bugun = _bugun(an)
    liste = (
        await db.execute(select(BelgeTalepleri).where(BelgeTalepleri.durum == "bekliyor").order_by(BelgeTalepleri.id.asc()).limit(500))
    ).scalars().all()
    geciken, bekleyen = [], []
    for b in liste:
        son = tarih_coz(b.son_tarih)
        if son is not None and son < bugun:
            geciken.append(_satir(b.baslik, ayrinti=b.client_email, tur="gecikti", gun=(bugun - son).days))
        else:
            bekleyen.append(_satir(b.baslik, ayrinti=b.client_email, tur="bekliyor",
                                   gun=(son - bugun).days if son is not None else None))
    geciken.sort(key=lambda s: -(s["gun"] or 0))
    return _bolum("belgeler", "dosyalar", len(liste), geciken + bekleyen, geciken=len(geciken))


async def _yenilemeler(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from services.site_izleme import kalemler

    bugun = _bugun(an)
    satirlar = []
    # Otomatik yenilenen SSL (Let's Encrypt vb.) listede yok: `ssl_hepsi=False` yalnız elle yenilenenleri verir.
    for k in await kalemler(db, ssl_hepsi=False):
        if k.tur not in ("alan", "ssl", "hosting"):
            continue
        kalan = (k.bitis - bugun).days
        if -YENILEME_GECMIS_GUN <= kalan <= YENILEME_GUN:
            satirlar.append(_satir(k.baslik, ayrinti=k.client_email, tur=k.tur, gun=kalan, zaman=k.bitis.isoformat()))
    satirlar.sort(key=lambda s: s["gun"])
    return _bolum("yenilemeler", "siteler", len(satirlar), satirlar)


async def _siteler(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.client_sites import Client_sites
    from models.site_izleme import UptimeKesintisi

    kesintiler = (
        await db.execute(
            select(UptimeKesintisi, Client_sites)
            .join(Client_sites, Client_sites.id == UptimeKesintisi.site_id)
            .where(UptimeKesintisi.bitis.is_(None), func.coalesce(Client_sites.durum, "aktif") != "bitti")
            .order_by(UptimeKesintisi.baslangic.asc())
        )
    ).all()
    gorulen, satirlar = set(), []
    for k, site in kesintiler:
        if site.id in gorulen:
            continue
        gorulen.add(site.id)
        satirlar.append(_satir(site.ad, ayrinti=site.adres, tur="kapali", zaman=_utc(k.baslangic),
                               gun=max(0, (an - (_utc(k.baslangic) or an)).days)))
    return _bolum("siteler", "siteler", len(satirlar), satirlar)


BOLUMLER = (_faturalar, _destek, _gelen_kutusu, _crm, _teklifler, _icerik, _belgeler, _yenilemeler, _siteler)


async def ozet_hazirla(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """Özetin o anki içeriği (yan etki yok). Bir bölüm hata verirse boş döner, diğerleri sürer."""
    an = an or simdi()
    bolumler = []
    for fonk in BOLUMLER:
        try:
            bolumler.append(await fonk(db, an))
        except Exception:  # noqa: BLE001 - tek bölüm özeti düşürmesin
            logger.exception("Haftalık özet bölümü hazırlanamadı: %s", fonk.__name__)
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            bolumler.append(_bolum(fonk.__name__.strip("_"), "otomasyon", 0, [], hata=True))
    konu, metin, _ = eposta_icerigi(bolumler, an)
    return {
        "hafta": hafta_etiketi(an), "olusturma": _iso(an), "bos": all(b["sayi"] == 0 for b in bolumler),
        "bolumler": bolumler, "eposta": {"konu": konu, "metin": metin},
    }


# ---------------------------------------------------------------------------
# E-posta (Türkçe, sade HTML + düz metin)
# ---------------------------------------------------------------------------
BASLIKLAR = {
    "faturalar": "Vadesi geçmiş faturalar",
    "destek": "Açık destek talepleri",
    "gelen_kutusu": "Gelen kutusunda yanıt bekleyenler",
    "crm": "Takip bekleyen CRM adayları",
    "teklifler": f"{YANITSIZ_GUN}+ gündür yanıtsız teklifler",
    "icerik": "Müşteri onayı bekleyen içerikler",
    "belgeler": "Bekleyen belge talepleri",
    "yenilemeler": f"{YENILEME_GUN} gün içinde yenilenecekler (alan adı, SSL, hosting)",
    "siteler": "Şu an erişilemeyen siteler",
}
YENILEME_ADLARI = {"alan": "Alan adı", "ssl": "SSL", "hosting": "Hosting"}


def _para(tutar: Any, birim: Optional[str]) -> str:
    from services.pdf_belge import para

    return para(tutar, birim, "tr")


def _bolum_ek_metni(b: Dict[str, Any]) -> str:
    ek = b.get("ek") or {}
    if b["anahtar"] == "faturalar" and ek.get("toplamlar"):
        return "toplam kalan: " + "; ".join(_para(t["tutar"], t["para_birimi"]) for t in ek["toplamlar"])
    if b["anahtar"] == "destek" and ek.get("sla_asildi"):
        return f"{ek['sla_asildi']} talepte SLA aşıldı"
    if b["anahtar"] == "crm":
        return f"{ek.get('sonraki_adim', 0)} sonraki adımı gelmiş, {ek.get('hareketsiz', 0)} {HAREKETSIZ_GUN}+ gündür hareketsiz"
    if b["anahtar"] == "belgeler" and ek.get("geciken"):
        return f"{ek['geciken']} talebin son tarihi geçti"
    if b["anahtar"] == "gelen_kutusu" and ek.get("kaynaklar"):
        return ", ".join(f"{GELEN_KAYNAK_ADLARI.get(k, k)} {n}" for k, n in ek["kaynaklar"].items())
    return ""


def _satir_metni(s: Dict[str, Any]) -> str:
    tur, gun = s.get("tur"), s.get("gun")
    durum = {
        "gecikme": f"{gun} gün gecikti",
        "sla_asildi": "SLA aşıldı",
        "acik": f"{gun} gündür açık",
        "sonraki_adim": "sonraki adım bugün" if not gun else f"sonraki adım {gun} gün geçti",
        "hareketsiz": f"{gun} gündür hareketsiz",
        "yanitsiz": f"{gun} gündür yanıtsız, görüntülenmedi",
        "yanitsiz_goruldu": f"{gun} gündür yanıtsız, görüntülendi",
        "onay_bekliyor": f"{gun} gündür onay bekliyor",
        "gecikti": f"son tarih {gun} gün geçti",
        "bekliyor": "bekliyor" if gun is None else f"son tarihe {gun} gün",
        "kapali": f"{gun} gündür erişilemiyor" if gun else "bugün erişilemiyor",
        "yanit_bekliyor": f"{gun} gündür yanıt bekliyor" if gun else "bugün geldi",
    }.get(tur or "")
    if tur in YENILEME_ADLARI:
        durum = f"{YENILEME_ADLARI[tur]}: " + (f"{gun} gün kaldı" if (gun or 0) >= 0 else f"süresi {-(gun or 0)} gün önce doldu")
    parcalar = [s["ad"]]
    if s.get("ayrinti"):
        parcalar.append(s["ayrinti"])
    if s.get("tutar") is not None:
        parcalar.append(_para(s["tutar"], s.get("para_birimi")))
    if durum:
        parcalar.append(durum)
    return " · ".join(parcalar)


def eposta_icerigi(bolumler: List[Dict[str, Any]], an: datetime) -> tuple:
    """(konu, düz metin, HTML gövde). Yalnız sayısı sıfırdan büyük bölümler."""
    from services.belge_ortak import site_adresi

    pazartesi = yerel(_pazartesi_0800(an)).date()
    tarih = f"{pazartesi.day} {AYLAR[pazartesi.month - 1]} {pazartesi.year}"
    dolu = [b for b in bolumler if b["sayi"] > 0]
    konu = f"Haftalık özet — {tarih} haftası" + (f": {len(dolu)} başlıkta bakılacak iş" if dolu else "")
    site = site_adresi()
    metin_satirlari = [f"Bu haftanın özeti ({tarih} haftası):", ""]
    html_parcalar = [
        f'<h2 style="margin:0 0 4px;font-size:20px">Haftalık özet</h2>'
        f'<p style="margin:0 0 16px;color:#6b7280">{html.escape(tarih)} haftası</p>'
    ]
    for b in dolu:
        baslik = BASLIKLAR.get(b["anahtar"], b["anahtar"])
        ek = _bolum_ek_metni(b)
        baglanti = f"{site}/admin?sekme={b['sekme']}"
        metin_satirlari.append(f"{baslik}: {b['sayi']}" + (f" ({ek})" if ek else ""))
        satirlar = [_satir_metni(s) for s in b["ornekler"]]
        metin_satirlari += [f"  - {s}" for s in satirlar]
        if b["sayi"] > len(satirlar):
            metin_satirlari.append(f"  … ve {b['sayi'] - len(satirlar)} tane daha")
        metin_satirlari += [f"  Panelde aç: {baglanti}", ""]
        html_parcalar.append(
            '<div style="margin:0 0 16px;padding:12px 14px;border:1px solid #e5e7eb;border-radius:10px">'
            f'<p style="margin:0 0 6px;font-weight:600">{html.escape(baslik)}: {b["sayi"]}'
            + (f' <span style="font-weight:400;color:#6b7280">({html.escape(ek)})</span>' if ek else "")
            + "</p>"
            '<ul style="margin:0 0 8px;padding-inline-start:18px">'
            + "".join(f"<li>{html.escape(s)}</li>" for s in satirlar)
            + (f'<li style="color:#6b7280">… ve {b["sayi"] - len(satirlar)} tane daha</li>' if b["sayi"] > len(satirlar) else "")
            + "</ul>"
            f'<a href="{html.escape(baglanti, quote=True)}" style="color:#7c3aed">Panelde aç →</a></div>'
        )
    metin_satirlari.append("Bu özeti Otomasyon › Sistem bölümünden kapatabilir ya da önizleyebilirsiniz.")
    html_parcalar.append(
        '<p style="margin:16px 0 0;font-size:13px;color:#6b7280">Bu özeti '
        f'<a href="{html.escape(site + PANEL_BAGLANTISI, quote=True)}" style="color:#7c3aed">Otomasyon › Sistem</a>'
        " bölümünden kapatabilir ya da önizleyebilirsiniz.</p>"
    )
    from services.otomasyon_kural import html_govde

    return konu, "\n".join(metin_satirlari), html_govde("".join(html_parcalar))


# ---------------------------------------------------------------------------
# Gönderim (zamanlı iş) ve durum
# ---------------------------------------------------------------------------
async def _iz_var(db: AsyncSession, hafta: int) -> bool:
    from models.sozlesmeler import HatirlatmaIzleri

    return (
        await db.execute(select(HatirlatmaIzleri.id).where(HatirlatmaIzleri.tur == IZ_TURU, HatirlatmaIzleri.ref_id == hafta).limit(1))
    ).scalar() is not None


async def _iz_yaz(db: AsyncSession, hafta: int) -> bool:
    """Haftayı "yapıldı" işaretler; aynı hafta zaten işaretliyse False (benzersizlik kilidi)."""
    from models.sozlesmeler import HatirlatmaIzleri

    try:
        async with db.begin_nested():
            db.add(HatirlatmaIzleri(tur=IZ_TURU, ref_id=hafta, esik=0))
            await db.flush()
    except IntegrityError:
        await db.commit()
        return False
    await db.commit()
    return True


async def acik_mi(db: AsyncSession) -> bool:
    from services import bildirim_tercih as bt

    matris = await bt.matris_oku(db)
    return bool(matris.get("admin", {}).get(OLAY, {}).get("email", True))


async def gonder(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """Zamanlı iş. "Şimdi çalıştır" (`zorla`) burada etkisiz: pencere ve hafta kilidi her zaman geçerli."""
    from services.notify import admin_recipients, dispatch, render

    an = an or simdi()
    if not pencere_acik_mi(an):
        return {"atlandi": "pencere_disi"}
    hafta = hafta_kimligi(an)
    if await _iz_var(db, hafta):
        return {"atlandi": "bu_hafta_yapildi", "hafta": hafta_etiketi(an)}
    if not await acik_mi(db):
        return {"atlandi": "kapali"}
    alicilar = await admin_recipients(db)
    if not alicilar:
        return {"atlandi": "alici_yok"}
    ozet = await ozet_hazirla(db, an)
    if ozet["bos"]:
        await _iz_yaz(db, hafta)
        return {"gonderildi": False, "bos": True, "hafta": ozet["hafta"]}
    if not await _iz_yaz(db, hafta):
        return {"atlandi": "bu_hafta_yapildi", "hafta": ozet["hafta"]}
    konu, metin, html_surumu = eposta_icerigi(ozet["bolumler"], an)
    baslik, govde = await render(db, OLAY, konu, metin, {"hafta": ozet["hafta"], "liste": metin})
    # Panelden şablon değiştirildiyse HTML sürümü o metni yansıtmaz: yalnız düz metin gider.
    ek = {"html": html_surumu} if (baslik, govde) == (konu, metin) else None
    yazilan = await dispatch(db, event_type=OLAY, title=baslik[:250], body=govde, recipients=alicilar,
                             link=PANEL_BAGLANTISI, eposta_ek=ek)
    return {"gonderildi": True, "hafta": ozet["hafta"], "bolum": sum(1 for b in ozet["bolumler"] if b["sayi"]),
            "alici": len({n.recipient_email for n in yazilan})}


async def durum(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """Otomasyon › Sistem kartı: açık mı, son gönderim, bu hafta ne oldu, e-posta kanalı, sonraki gönderim."""
    from models.notifications import Notifications
    from services import bildirim_tercih as bt
    from services.notify import admin_recipients

    an = an or simdi()
    son = (
        await db.execute(
            select(Notifications.created_at).where(Notifications.event_type == OLAY, Notifications.channel == "inapp")
            .order_by(Notifications.id.desc()).limit(1)
        )
    ).scalar()
    hafta = hafta_kimligi(an)
    yapildi = await _iz_var(db, hafta)
    son_u = _utc(son)
    if yapildi:
        bu_hafta = "gonderildi" if son_u is not None and son_u >= _pazartesi_0800(an) - timedelta(hours=1) else "bos"
        sonraki = _pazartesi_0800(an) + timedelta(days=7)
    elif pencere_acik_mi(an):
        bu_hafta, sonraki = "bekliyor", None  # bir sonraki zamanlı turda
    else:
        bu_hafta, sonraki = "bekliyor", _pazartesi_0800(an)
    kanallar = await bt.kanal_durumlari(db)
    return {
        "acik": await acik_mi(db), "son_gonderim": _iso(son_u), "hafta": hafta_etiketi(an), "bu_hafta": bu_hafta,
        "sonraki": _iso(sonraki), "eposta_kanali": kanallar.get("email"), "alici_sayisi": len(await admin_recipients(db)),
    }


async def ac_kapat(db: AsyncSession, acik: bool) -> Dict[str, Any]:
    """Matristeki yönetici × `haftalik_ozet` × e-posta hücresi (tek kaynak)."""
    from services import bildirim_tercih as bt

    matris = await bt.matris_oku(db)
    matris.setdefault("admin", {}).setdefault(OLAY, {})["email"] = bool(acik)
    await bt.matris_yaz(db, matris)
    return await durum(db)


__all__ = ["OLAY", "ozet_hazirla", "gonder", "durum", "ac_kapat", "pencere_acik_mi", "hafta_kimligi", "eposta_icerigi"]
