"""Faz 2C — Aylık müşteri raporu (modül `aylik_rapor`).

Tek rapor, müşteri başına ay başına: `service_reports` tablosunda
`tur="aylik"` satırı (abonelik raporlarıyla aynı taslak/yayında akışı;
ayrı tablo açılmadı, çiftleme yok).

Bölümler (veri JSON'u `service_reports.veri`)
    ozet         yapılan işler (proje olayları), tamamlanan projeler, harcanan/
                 yüklenen kredi, açılan/çözülen talepler + SLA uyumu
    site_sagligi site başına ay içi uptime %, kesintiler, alan/SSL/hosting bitişi
    seo          son site analizi puanı ve bir öncekine göre değişim
    plan         gelecek ay: açık projeler, açık talepler, bekleyen belgeler
    Yönetici notu ayrı alanda (`yonetici_notu`).

Akış: zamanlı görev ayın 1–5'inde bir önceki ayın taslaklarını açar (modülü
açık her müşteri için, varsa dokunmaz) ya da yönetici "şimdi oluştur" der
→ yönetici önizler, not yazar → yayınlar → müşteriye e-posta BİR KEZ
(`eposta_gonderildi_at` koşullu UPDATE).

Görünüm: `/rapor-aylik/<jeton>` yazdırmaya uygun HTML (tarayıcıdan PDF).
Jeton imzalı ve durumsuz: `<id>-<HMAC(id, dönem, müşteri)[:32]>`; veritabanında
jeton yok, tahmin edilemez, müşteri değişirse eski jeton geçersizleşir.
Yalnız YAYINDAKİ rapor jetonla açılır; taslak yalnız yöneticiye.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TR = timezone(timedelta(hours=3))
TUR = "aylik"
HIZMET = "aylik_rapor"
LISTE_SINIRI = 25
AYLIK_ANALIZ_GUN = 25
ANALIZ_TUR_SINIRI = 1
AY_ADLARI = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


class RaporHatasi(Exception):
    def __init__(self, durum: int, kod: str):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def eposta_duzelt(e: Optional[str]) -> str:
    return (e or "").strip().lower()


# ---------------------------------------------------------------------------
# Dönem
# ---------------------------------------------------------------------------
def donem_dogrula(donem: Optional[str]) -> str:
    try:
        yil, ay = str(donem or "").strip().split("-")
        y, a = int(yil), int(ay)
    except (ValueError, AttributeError):
        raise RaporHatasi(400, "gecersiz_donem")
    if not (2000 <= y <= 2100 and 1 <= a <= 12):
        raise RaporHatasi(400, "gecersiz_donem")
    return f"{y:04d}-{a:02d}"


def onceki_donem(an: Optional[datetime] = None) -> str:
    bugun = utc(an or simdi()).astimezone(TR).date()  # type: ignore[union-attr]
    ilk = bugun.replace(day=1) - timedelta(days=1)
    return f"{ilk.year:04d}-{ilk.month:02d}"


def bu_donem(an: Optional[datetime] = None) -> str:
    bugun = utc(an or simdi()).astimezone(TR).date()  # type: ignore[union-attr]
    return f"{bugun.year:04d}-{bugun.month:02d}"


def donem_sinirlari(donem: str) -> Tuple[datetime, datetime, date, date]:
    """(başlangıç_utc, bitiş_utc [hariç], ilk_gün, son_gün) — Türkiye saatine göre ay."""
    y, a = (int(x) for x in donem.split("-"))
    ilk = date(y, a, 1)
    sonraki = date(y + 1, 1, 1) if a == 12 else date(y, a + 1, 1)
    bas = datetime(ilk.year, ilk.month, 1, tzinfo=TR).astimezone(timezone.utc)
    bit = datetime(sonraki.year, sonraki.month, 1, tzinfo=TR).astimezone(timezone.utc)
    return bas, bit, ilk, sonraki - timedelta(days=1)


def donem_adi(donem: str) -> str:
    y, a = donem.split("-")
    return f"{AY_ADLARI[int(a) - 1]} {y}"


# ---------------------------------------------------------------------------
# Jeton (HMAC, durumsuz)
# ---------------------------------------------------------------------------
_YEDEK: Optional[bytes] = None


def _anahtar() -> bytes:
    global _YEDEK
    gizli = os.environ.get("JWT_SECRET_KEY") or ""
    if not gizli:
        if _YEDEK is None:
            _YEDEK = secrets.token_bytes(32)
        return _YEDEK
    return hashlib.sha256(("aylik-rapor:" + gizli).encode()).digest()


def jeton_uret(rapor: Any) -> str:
    mesaj = f"{int(rapor.id)}|{rapor.donem}|{eposta_duzelt(rapor.client_email)}"
    imza = hmac.new(_anahtar(), mesaj.encode(), hashlib.sha256).hexdigest()[:32]
    # Ayırıcı "-": noktalı yol bazı statik sunucularda dosya uzantısı sanılıyor.
    return f"{int(rapor.id)}-{imza}"


def jeton_id(jeton: str) -> Optional[int]:
    try:
        parca, imza = str(jeton).split("-", 1)
        kimlik = int(parca)
    except (ValueError, AttributeError):
        return None
    if kimlik <= 0 or len(imza) != 32:
        return None
    return kimlik


def jeton_dogru_mu(rapor: Any, jeton: str) -> bool:
    return hmac.compare_digest(jeton_uret(rapor), str(jeton))


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


# ---------------------------------------------------------------------------
# Veri toplama
# ---------------------------------------------------------------------------
def _icinde(an: Optional[datetime], bas: datetime, bit: datetime) -> bool:
    a = utc(an)
    return a is not None and bas <= a < bit


async def _musteri_adi(db: AsyncSession, eposta: str) -> Optional[str]:
    from models.projects import Projects
    from models.support_tickets import Support_tickets

    for model in (Projects, Support_tickets):
        ad = (
            await db.execute(
                select(model.client_name).where(func.lower(model.client_email) == eposta, model.client_name.isnot(None)).limit(1)
            )
        ).scalar()
        if ad and "@" not in str(ad):
            return str(ad)
    return None


async def _ozet_bolumu(db: AsyncSession, eposta: str, bas: datetime, bit: datetime) -> Dict[str, Any]:
    from models.credit_ledger import CreditLedger
    from models.destek_sla import TalepSla
    from models.project_events import Project_events
    from models.projects import Projects
    from models.support_tickets import Support_tickets
    from services import sla

    projeler = (await db.execute(select(Projects).where(func.lower(Projects.client_email) == eposta))).scalars().all()
    proje_adi = {p.id: p.title for p in projeler}
    isler: List[Dict[str, Any]] = []
    if proje_adi:
        olaylar = (
            await db.execute(
                select(Project_events)
                .where(Project_events.project_id.in_(list(proje_adi)))
                .order_by(Project_events.created_at.asc(), Project_events.id.asc())
            )
        ).scalars().all()
        for o in olaylar:
            if str(o.visible_to_client or "1") in ("0", "false", "False"):
                continue  # iç not müşteri raporuna girmez
            if not _icinde(o.created_at, bas, bit):
                continue
            isler.append({"tarih": iso(o.created_at), "proje": proje_adi.get(o.project_id), "baslik": o.title, "tur": o.event_type})
    tamamlanan = [
        {"id": p.id, "baslik": p.title}
        for p in projeler
        if (p.status or "") == "completed" and _icinde(p.updated_at, bas, bit)
    ]

    harcanan = yuklenen = 0.0
    for satir in (await db.execute(select(CreditLedger).where(CreditLedger.musteri_eposta == eposta))).scalars().all():
        if not _icinde(satir.created_at, bas, bit):
            continue
        if satir.tur == "harcama":
            harcanan += -float(satir.miktar or 0)
        elif float(satir.miktar or 0) > 0 and satir.tur in ("satin_alma", "bonus", "hediye", "iade"):
            yuklenen += float(satir.miktar or 0)
    try:
        from services.kredi import bakiye

        kredi_bakiye: Optional[float] = round(await bakiye(db, eposta), 2)
    except Exception:  # noqa: BLE001
        kredi_bakiye = None

    talepler = (await db.execute(select(Support_tickets).where(func.lower(Support_tickets.client_email) == eposta))).scalars().all()
    acilan = [t for t in talepler if _icinde(t.created_at, bas, bit)]
    ayar = await sla.ayarlari_oku(db)
    satirlar = await sla.senkronla(db, talepler, ayar) if talepler else {}
    cozulen = 0
    uyumlu = ihlal = 0
    for t in talepler:
        s = satirlar.get(t.id)
        if s is None:
            continue
        if _icinde(s.cozum_at, bas, bit):
            cozulen += 1
        # SLA uyumu: ilk yanıt hedefi bu aya düşen ya da bu ay açılan talepler.
        if not (_icinde(s.ilk_yanit_hedef, bas, bit) or _icinde(t.created_at, bas, bit)):
            continue
        durum = sla.durum_sozlugu(s, ayar, min(simdi(), bit))["ilk_yanit"]["durum"]
        if durum == "karsilandi":
            uyumlu += 1
        elif durum in ("gecikti", "asildi"):
            ihlal += 1
    uyum = round(100.0 * uyumlu / (uyumlu + ihlal), 1) if (uyumlu + ihlal) else None
    return {
        "is_sayisi": len(isler),
        "isler": isler[-LISTE_SINIRI:],
        "tamamlanan_projeler": tamamlanan,
        "harcanan_kredi": round(harcanan, 2),
        "yuklenen_kredi": round(yuklenen, 2),
        "kredi_bakiye": kredi_bakiye,
        "acilan_talep": len(acilan),
        "cozulen_talep": cozulen,
        "sla_uyumlu": uyumlu,
        "sla_ihlal": ihlal,
        "sla_uyum_yuzde": uyum,
    }


async def _site_bolumu(db: AsyncSession, eposta: str, bas: datetime, bit: datetime, ilk: date, son: date) -> List[Dict[str, Any]]:
    from models.client_sites import Client_sites
    from models.site_izleme import SiteIzleme, UptimeGunluk, UptimeKesintisi
    from services.site_izleme import kalan_gun

    siteler = (await db.execute(select(Client_sites).where(func.lower(Client_sites.client_email) == eposta).order_by(Client_sites.id))).scalars().all()
    sonuc = []
    for site in siteler:
        gunluk = (
            await db.execute(
                select(func.coalesce(func.sum(UptimeGunluk.basarili), 0), func.coalesce(func.sum(UptimeGunluk.toplam), 0)).where(
                    UptimeGunluk.site_id == site.id,
                    UptimeGunluk.gun >= ilk.isoformat(),
                    UptimeGunluk.gun <= son.isoformat(),
                )
            )
        ).first()
        basarili, toplam = int(gunluk[0] or 0), int(gunluk[1] or 0)
        kesintiler = []
        toplam_dk = 0
        for k in (
            await db.execute(select(UptimeKesintisi).where(UptimeKesintisi.site_id == site.id).order_by(UptimeKesintisi.baslangic.asc()))
        ).scalars().all():
            k_bas, k_bit = utc(k.baslangic), utc(k.bitis)
            if k_bas is None or k_bas >= bit or (k_bit is not None and k_bit < bas):
                continue
            son_an = min(k_bit or simdi(), bit)
            dk = max(1, int(((son_an - max(k_bas, bas)).total_seconds() + 59) // 60))
            toplam_dk += dk
            kesintiler.append({"baslangic": iso(k_bas), "bitis": iso(k_bit), "sure_dk": dk})
        iz = (await db.execute(select(SiteIzleme).where(SiteIzleme.site_id == site.id))).scalars().first()
        sonuc.append(
            {
                "site_id": site.id,
                "ad": site.ad,
                "adres": site.adres,
                "uptime_yuzde": round(100.0 * basarili / toplam, 2) if toplam else None,
                "olcum": toplam,
                "kesinti_sayisi": len(kesintiler),
                "kesinti_dk": toplam_dk,
                "kesintiler": kesintiler[:10],
                "alan_bitis": iso(iz.alan_bitis) if iz else None,
                "alan_kalan": kalan_gun(iz.alan_bitis) if iz else None,
                "ssl_bitis": iso(iz.ssl_bitis) if iz else None,
                "ssl_kalan": kalan_gun(iz.ssl_bitis) if iz else None,
                "hosting_bitis": iso(iz.hosting_bitis) if iz else None,
                "hosting_kalan": kalan_gun(iz.hosting_bitis) if iz else None,
            }
        )
    return sonuc


def _alan_adi(adres: Optional[str]) -> Optional[str]:
    if not adres:
        return None
    try:
        from services.site_analizi import adresi_normalize

        return adresi_normalize(adres)[2]
    except Exception:  # noqa: BLE001
        return None


async def _seo_bolumu(db: AsyncSession, eposta: str, bit: datetime) -> List[Dict[str, Any]]:
    from models.client_sites import Client_sites
    from models.site_analyses import Site_analyses

    siteler = (await db.execute(select(Client_sites).where(func.lower(Client_sites.client_email) == eposta).order_by(Client_sites.id))).scalars().all()
    sonuc = []
    gorulen = set()
    for site in siteler:
        alan = _alan_adi(site.adres)
        if not alan or alan in gorulen:
            continue
        gorulen.add(alan)
        analizler = (
            await db.execute(
                select(Site_analyses)
                .where(Site_analyses.alan_adi == alan, Site_analyses.durum == "tamam", Site_analyses.puan.isnot(None))
                .order_by(Site_analyses.created_at.desc(), Site_analyses.id.desc())
                .limit(20)
            )
        ).scalars().all()
        analizler = [a for a in analizler if utc(a.created_at) is not None and utc(a.created_at) < bit]
        son = analizler[0] if analizler else None
        onceki = analizler[1] if len(analizler) > 1 else None
        bolumler = []
        if son is not None and son.ozet_json:
            try:
                for b in (json.loads(son.ozet_json) or {}).get("bolumler", []):
                    bolumler.append({"anahtar": b.get("anahtar"), "puan": b.get("puan")})
            except (ValueError, AttributeError):
                bolumler = []
        sonuc.append(
            {
                "site": site.ad,
                "alan_adi": alan,
                "puan": son.puan if son else None,
                "tarih": iso(son.created_at) if son else None,
                "onceki_puan": onceki.puan if onceki else None,
                "degisim": (son.puan - onceki.puan) if (son and onceki) else None,
                "bolumler": bolumler,
            }
        )
    return sonuc


async def _plan_bolumu(db: AsyncSession, eposta: str) -> Dict[str, Any]:
    from models.dosyalar import BelgeTalepleri
    from models.projects import Projects
    from models.support_tickets import Support_tickets

    projeler = (
        await db.execute(
            select(Projects).where(func.lower(Projects.client_email) == eposta, func.coalesce(Projects.status, "") != "completed").order_by(Projects.id)
        )
    ).scalars().all()
    talepler = (
        await db.execute(
            select(Support_tickets)
            .where(func.lower(Support_tickets.client_email) == eposta, func.coalesce(Support_tickets.status, "open") != "closed")
            .order_by(Support_tickets.id)
        )
    ).scalars().all()
    belgeler = (
        await db.execute(select(BelgeTalepleri).where(BelgeTalepleri.client_email == eposta, BelgeTalepleri.durum == "bekliyor"))
    ).scalars().all()
    return {
        "acik_projeler": [
            {"baslik": p.title, "asama": p.stage, "ilerleme": p.progress, "durum": p.status} for p in projeler[:LISTE_SINIRI]
        ],
        "acik_talepler": [{"no": t.id, "konu": t.subject, "durum": t.status} for t in talepler[:LISTE_SINIRI]],
        "bekleyen_belgeler": [{"baslik": b.baslik, "son_tarih": b.son_tarih} for b in belgeler[:LISTE_SINIRI]],
    }


async def veri_topla(db: AsyncSession, eposta: str, donem: str) -> Dict[str, Any]:
    eposta = eposta_duzelt(eposta)
    bas, bit, ilk, son = donem_sinirlari(donem)
    return {
        "surum": 1,
        "donem": donem,
        "baslangic": ilk.isoformat(),
        "bitis": son.isoformat(),
        "olusturma": simdi().isoformat(),
        "musteri_adi": await _musteri_adi(db, eposta),
        "ozet": await _ozet_bolumu(db, eposta, bas, bit),
        "site_sagligi": await _site_bolumu(db, eposta, bas, bit, ilk, son),
        "seo": await _seo_bolumu(db, eposta, bit),
        "plan": await _plan_bolumu(db, eposta),
    }


def ozet_metni(veri: Dict[str, Any]) -> str:
    """Rapor listesinde ve e-postada görünen kısa Türkçe özet."""
    o = veri.get("ozet") or {}
    parcalar = [
        f"{o.get('is_sayisi', 0)} iş kaydı",
        f"{o.get('harcanan_kredi', 0):g} saat kredi harcandı",
        f"{o.get('acilan_talep', 0)} talep açıldı, {o.get('cozulen_talep', 0)} çözüldü",
    ]
    if o.get("sla_uyum_yuzde") is not None:
        parcalar.append(f"SLA uyumu %{o['sla_uyum_yuzde']:g}")
    oranlar = [s["uptime_yuzde"] for s in veri.get("site_sagligi") or [] if s.get("uptime_yuzde") is not None]
    if oranlar:
        parcalar.append(f"uptime %{min(oranlar):g}")
    puanlar = [s["puan"] for s in veri.get("seo") or [] if s.get("puan") is not None]
    if puanlar:
        parcalar.append(f"site analizi puanı {puanlar[0]}")
    return f"{donem_adi(veri['donem'])}: " + "; ".join(parcalar) + "."


# ---------------------------------------------------------------------------
# Oluştur / yayınla
# ---------------------------------------------------------------------------
async def rapor_bul(db: AsyncSession, eposta: str, donem: str):
    from models.service_subscriptions import Service_reports

    return (
        await db.execute(
            select(Service_reports).where(
                Service_reports.tur == TUR, Service_reports.client_email == eposta, Service_reports.donem == donem
            )
        )
    ).scalars().first()


async def olustur(db: AsyncSession, eposta: str, donem: str):
    """Taslağı açar ya da taslağın verisini yeniler (not korunur). Yayındaysa 409."""
    from models.service_subscriptions import Service_reports

    eposta = eposta_duzelt(eposta)
    if "@" not in eposta:
        raise RaporHatasi(400, "gecersiz_eposta")
    donem = donem_dogrula(donem)
    mevcut = await rapor_bul(db, eposta, donem)
    if mevcut is not None and mevcut.durum == "yayinlandi":
        raise RaporHatasi(409, "yayinlandi")
    veri = await veri_topla(db, eposta, donem)
    if mevcut is None:
        mevcut = Service_reports(
            subscription_id=None, client_email=eposta, hizmet=HIZMET, donem=donem, durum="taslak", tur=TUR,
        )
        db.add(mevcut)
    mevcut.baslik = f"Aylık rapor — {donem_adi(donem)}"
    mevcut.veri = json.dumps(veri, ensure_ascii=False)
    mevcut.ozet = ozet_metni(veri)
    await db.commit()
    await db.refresh(mevcut)
    return mevcut


def veri_coz(rapor: Any) -> Dict[str, Any]:
    try:
        v = json.loads(rapor.veri or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def rapor_sozlugu(rapor: Any, *, yonetici: bool = False) -> Dict[str, Any]:
    d = {
        "id": rapor.id,
        "donem": rapor.donem,
        "baslik": rapor.baslik,
        "ozet": rapor.ozet,
        "durum": rapor.durum,
        "yayin_at": iso(rapor.yayin_at),
        "yonetici_notu": rapor.yonetici_notu,
        "veri": veri_coz(rapor),
        "jeton": jeton_uret(rapor),
    }
    if yonetici:
        d["client_email"] = rapor.client_email
        d["eposta_gonderildi_at"] = iso(rapor.eposta_gonderildi_at)
    return d


async def yayinla(db: AsyncSession, rapor: Any) -> bool:
    """Yayınlar; e-postayı yalnız ilk yayında gönderir. Gönderildiyse True."""
    from models.service_subscriptions import Service_reports
    from services.notify import dispatch

    if rapor.durum != "yayinlandi":
        rapor.durum = "yayinlandi"
        rapor.yayin_at = simdi()
        await db.commit()
    sonuc = await db.execute(
        update(Service_reports)
        .where(Service_reports.id == rapor.id, Service_reports.eposta_gonderildi_at.is_(None))
        .values(eposta_gonderildi_at=simdi())
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if int(sonuc.rowcount or 0) != 1:
        return False
    await db.refresh(rapor)
    yol = f"/rapor-aylik/{jeton_uret(rapor)}"
    await dispatch(
        db,
        event_type="aylik_rapor",
        title=f"Aylık raporunuz hazır: {donem_adi(rapor.donem)}",
        body=f"{rapor.ozet or ''}\n\nRaporu görüntüleyin ve PDF olarak kaydedin: {site_adresi()}{yol}",
        recipients=[{"email": rapor.client_email, "role": "client"}],
        link=yol,
        ref_type="aylik_rapor",
        ref_id=rapor.id,
    )
    return True


# ---------------------------------------------------------------------------
# Zamanlı görevler
# ---------------------------------------------------------------------------
async def _modulu_acik_musteriler(db: AsyncSession) -> List[str]:
    from services.moduller import musteri_listesi, toplu_durumlar

    musteriler = await musteri_listesi(db)
    durumlar = await toplu_durumlar(db, [m["eposta"] for m in musteriler if m.get("eposta")])
    return sorted(e for e, d in durumlar.items() if d.durumlar.get(HIZMET) is not None and d.durumlar[HIZMET].acik)


async def aylik_taslaklar(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """Ayın 1–5'inde: modülü açık her müşteri için bir önceki ayın taslağı (varsa dokunmaz)."""
    from services.notify import admin_recipients, dispatch

    an = an or simdi()
    gun = utc(an).astimezone(TR).day  # type: ignore[union-attr]
    if gun > 5:
        return {"atlandi": "ay_basi_degil"}
    donem = onceki_donem(an)
    acilan = 0
    for eposta in await _modulu_acik_musteriler(db):
        if await rapor_bul(db, eposta, donem) is not None:
            continue
        try:
            await olustur(db, eposta, donem)
            acilan += 1
        except Exception:  # noqa: BLE001 - bir müşteri diğerlerini durdurmasın
            logger.exception("Aylık rapor taslağı açılamadı: %s", eposta)
            await db.rollback()
    if acilan:
        await dispatch(
            db,
            event_type="aylik_rapor_taslak",
            title=f"{donem_adi(donem)} aylık raporları hazır ({acilan} taslak)",
            body="Taslakları önizleyip notunuzu ekleyin; yayınladığınızda müşteriye e-posta gider.",
            recipients=await admin_recipients(db),
            link="/admin",
            ref_type="aylik_rapor",
        )
    return {"donem": donem, "acilan": acilan}


async def aylik_analizler(db: AsyncSession, sinir: int = ANALIZ_TUR_SINIRI) -> Dict[str, Any]:
    """Modülü açık müşterilerin sitelerine ayda bir otomatik site analizi.

    Tur başına en çok `sinir` analiz (varsayılan 1): analiz birkaç saniye ile
    yarım dakika arası sürüyor, zamanlı uçun süresini ve PageSpeed kotasını
    tüketmesin. Son `AYLIK_ANALIZ_GUN` gün içinde başarılı analizi olan alan
    atlanıyor (herkese açık formdaki alan başına günlük sınır da bu kadar
    seyrek analizle hiç dolmuyor).
    """
    from models.client_sites import Client_sites
    from models.site_analyses import Site_analyses
    from services import site_analizi as motor

    musteriler = await _modulu_acik_musteriler(db)
    if not musteriler:
        return {"calisan": 0}
    esik = simdi() - timedelta(days=AYLIK_ANALIZ_GUN)
    siteler = (
        await db.execute(
            select(Client_sites).where(func.lower(Client_sites.client_email).in_(musteriler), Client_sites.adres.isnot(None)).order_by(Client_sites.id)
        )
    ).scalars().all()
    calisan = hata = 0
    for site in siteler:
        if calisan + hata >= sinir:
            break
        try:
            url, _host, alan = motor.adresi_normalize(site.adres or "")
        except Exception:  # noqa: BLE001
            continue
        yakin = (
            await db.execute(
                select(func.count(Site_analyses.id)).where(
                    Site_analyses.alan_adi == alan,
                    Site_analyses.created_at >= esik,
                    or_(Site_analyses.durum == "tamam", and_(Site_analyses.kaynak == "aylik", Site_analyses.durum != "tamam")),
                )
            )
        ).scalar()
        if int(yakin or 0) > 0:
            continue
        kayit = Site_analyses(
            alan_adi=alan, url=url, durum="calisiyor", eposta=eposta_duzelt(site.client_email),
            kaynak="aylik", kvkk_onay=False, created_at=simdi(),
        )
        db.add(kayit)
        await db.commit()
        await db.refresh(kayit)
        try:
            sonuc = await motor.analiz_et(kayit.url)
            kayit.durum = "tamam"
            kayit.puan = sonuc["puan"]
            kayit.ozet_json = json.dumps({"bolumler": motor.ozetle(sonuc["bolumler"])}, ensure_ascii=False)
            kayit.rapor_json = json.dumps({"bolumler": sonuc["bolumler"], "ayrinti": sonuc.get("ayrinti")}, ensure_ascii=False)
            calisan += 1
        except Exception as exc:  # noqa: BLE001
            kayit.durum = "hata"
            kayit.hata_kodu = getattr(exc, "kod", None) or "beklenmedik"
            hata += 1
        await db.commit()
    return {"calisan": calisan, "hata": hata}
