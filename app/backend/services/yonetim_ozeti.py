"""Faz 11A — Yönetici "Genel bakış" (komuta ekranı) özeti: tek istekte, gerçek veriden.

Uç: `GET /api/v1/yonetim-ozeti` (routers/yonetim_ozeti.py), yalnız yönetici.

Her kalem kendi `try` bloğunda hesaplanır: biri hata verirse YALNIZ o kalem `null` döner ve
ekran "veri yok" der — uydurma/örnek değer yok. Oran ve ortalamalar paydası sıfırsa `null`.
Sunucu önbelleği yok (ekran 60 sn'de bir yokluyor; istemcide kısa bellek var).

Zaman
-----
"Bugün", "bu ay", saat kovaları TÜRKİYE saatiyle (UTC+3, `services/sla.TR`). Veritabanındaki saat
damgalarının bir kısmı saat dilimsiz (`datetime.now`), bir kısmı UTC; dilimsiz değer UTC sayılır
(sunucu UTC'de çalışıyor — `services/sla.utc` ile aynı kural). Sorgular geniş bir pencereyle süzülür,
kesin sınır Python'da uygulanır (SQLite ve PostgreSQL aynı sonucu versin).

Tanımlar (raporda da yazılı)
----------------------------
acil          Açık destek talepleri (durumu kapalı olmayan) içinde bekleyen SLA hedefi — ilk yanıt
              verilmemişse ilk yanıt, verilmişse çözüm hedefi — EN YAKIN olan (aşılmışlar en önde).
              `kalan_sn` duvar saatiyle hedef anına kalan süre (eksi = aşıldı). `siradaki`: geri kalan
              açık taleplerden SLA'sı aşılmış ya da yaklaşan sayısı. SLA satırları `sla.senkronla`
              ile hazırlanır (destek sekmesinin yaptığı gibi; `talep_sla` denetim kaydına düşmez).
kpi.tahsilat  Bu ay `payments`: "odendi" − "iade", yalnız TRY. Gün: elle girilen ödemede
              `odeme_tarihi`, yoksa `odendi_at`, yoksa kayıt zamanı. Cüzdandan (avans) mahsup edilen
              ödeme de fatura tahsilatıdır; cüzdan yüklemesi ayrıca SAYILMAZ (çift sayım olmasın).
              Değişim: ayın bugüne kadarki kısmı ↔ geçen ayın aynı gününe kadarki kısmı.
              Seri: son 14 günün günlük tahsilatı.
kpi.acik_isler  Açık iş = açık proje görevi (durum ≠ "tamam") + açık destek talebi (durum kapalı
              değil) + açık saha iş emri (yeni | planlandı | yolda | işte | ertelendi; tüm hesaplar).
              Seri: son 14 günün gün sonundaki açık iş sayısı (oluşturma ve kapanış zamanlarından);
              değişim: 30 gün önceki açık iş sayısına göre.
kpi.tamamlanan  Bu ay tamamlanan görev (`tamamlandi_at`) + çözülen talep (SLA çözüm zamanı, yoksa
              kapalı talebin son güncellemesi) + tamamlanan iş emri (`bitir_at`). Değişim: geçen ayın
              aynı dönemi. Seri: son 14 günün günlük tamamlanan sayısı.
kpi.sla       Son 30 günde ilk yanıtı verilmiş taleplerde ilk yanıtın hedef içinde olma oranı (%) ve
              ilk yanıt süresi ortalaması (mesai dakikası). Fark: önceki 30 güne göre (puan).
hizmetHatti   yeni_talep: son 24 saatte iletişim formu / teklif isteği / CRM formu gönderimi;
              teklif: gönderilmiş ve yanıt bekleyen (gonderildi | goruntulendi) sayı + para birimine
              göre toplam; sozlesme: imza bekleyen (gonderildi); proje: etkin müşteri projesi (müşteri
              e-postalı, tamamlanmamış) + ortalama ilerleme; teslim: süresi dolmamış, bekleyen teslim
              onayı bağlantısı (`signed_actions` teslimat_onay); fatura: kalan bakiyesi olan açık
              fatura sayısı + para birimine göre kalan.
              donusum (son 90 gün): talep→teklif = talep gönderen kişilerden (e-posta) sonrasında
              teklif gönderilenlerin oranı; teklif→kabul = karar verilmiş tekliflerde kabul oranı;
              tahsilat_gun = tamamen ödenen faturalarda düzenlemeden son ödemeye ortalama gün.
aktivite      Bugün ve dün saat başına denetim kaydı (`audit_log`) satırı: bütün iş tablolarındaki
              oluşturma/güncelleme/silme, giriş, onay ve ödemeler oradan geçiyor (webhook teslimat
              tablosu yalnız uç noktası tanımlıyken dolduğu için seçilmedi). Bugünün gelmemiş saatleri null.
kategori      Müşteri projelerinin `category` alanına göre dağılım; küme = etkin (tamamlanmamış) ya da
              bu ay açılmış müşteri projeleri. `bu_ay_yeni`, `ort_sure_gun` (son 180 günde tamamlanan
              projelerde açılıştan "completed" durumuna — tamamlanma anı denetim kaydından) ve
              `en_hizli` (bu ay ↔ geçen ayın aynı dönemi, yeni proje artışı en yüksek kategori).
saha          Saha servisi modülü (bütün servis firmaları): bugün planlı ya da şu an yolda/işte olan
              iş emirleri ve atanmış teknisyenleri. İlerleme: kontrol listesi doluluk oranı (işteyse),
              yoksa duruma göre adım (planlandı %15, yolda %40, işte %70). İş emri yoksa `null`.
sonIsler      En son oluşturulan 8 kayıt: müşteri projesi, destek talebi, iş emri, teklif (karışık).
bildirimler   İsteği yapan yöneticinin son 4 panel içi bildirimi.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services import sla

logger = logging.getLogger(__name__)

TR = sla.TR
GUN_SAYISI = 14
SON_IS_SAYISI = 8
BILDIRIM_SAYISI = 4
DONUSUM_GUN = 90

#: Kapalı sayılan proje durumları (projelerin serbest metin durumları dahil).
PROJE_KAPALI = frozenset({"completed", "cancelled", "canceled", "tamamlandi", "iptal", "done"})
#: Açık iş emri durumları (tamamlandı ve iptal dışındakiler).
IS_EMRI_ACIK = frozenset({"yeni", "planlandi", "yolda", "iste", "ertelendi"})
IS_EMRI_ETKIN = frozenset({"planlandi", "yolda", "iste"})
TEKLIF_BEKLEYEN = frozenset({"gonderildi", "goruntulendi"})
TEKLIF_KARAR = frozenset({"kabul", "ret", "suresi_doldu"})
TRY_ADLARI = frozenset({"TRY", "TL", ""})


# ---------------------------------------------------------------------------
# Zaman yardımcıları
# ---------------------------------------------------------------------------
def utc(an: Optional[datetime]) -> Optional[datetime]:
    return sla.utc(an)


def tr_gun(an: datetime) -> date:
    return utc(an).astimezone(TR).date()  # type: ignore[union-attr]


def gun_basi(gun: date) -> datetime:
    """TR gününün başlangıcı (UTC)."""
    return datetime(gun.year, gun.month, gun.day, tzinfo=TR).astimezone(timezone.utc)


def ay_basi(gun: date) -> date:
    return gun.replace(day=1)


def onceki_ay_ayni_gun(gun: date) -> Tuple[date, date]:
    """Geçen ayın 1'i ve bugünün geçen aydaki karşılığı (ay kısaysa ayın son günü)."""
    ilk = (ay_basi(gun) - timedelta(days=1)).replace(day=1)
    son_gun = (ay_basi(gun) - timedelta(days=1)).day
    return ilk, ilk.replace(day=min(gun.day, son_gun))


def tarih_coz(metin: Any) -> Optional[date]:
    if not metin:
        return None
    if isinstance(metin, datetime):
        return tr_gun(metin)
    if isinstance(metin, date):
        return metin
    try:
        return date.fromisoformat(str(metin).strip()[:10])
    except ValueError:
        return None


def yuzde_degisim(simdi: float, onceki: float) -> Optional[float]:
    if not onceki:
        return None
    return round((simdi - onceki) / abs(onceki) * 100, 1)


def para(deger: Any) -> float:
    try:
        return float(Decimal(str(deger or 0)))
    except Exception:  # noqa: BLE001
        return 0.0


def pb(deger: Optional[str]) -> str:
    """Para birimi; boş/TL → TRY."""
    d = (deger or "").strip().upper()
    return "TRY" if d in TRY_ADLARI else d


def eposta(deger: Optional[str]) -> str:
    return (deger or "").strip().lower()


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def son_gunler(bugun: date, n: int = GUN_SAYISI) -> List[date]:
    return [bugun - timedelta(days=n - 1 - i) for i in range(n)]


async def _kalem(ad: str, fn: Callable[[], Any], db: Optional[AsyncSession] = None) -> Any:
    """Kalem hesaplanamazsa `None` (ekran "veri yok" der); hata günlüğe yazılır.

    Hata bir sorgudan geldiyse oturum geri alınır: PostgreSQL'de yarım kalan işlem sonraki
    kalemlerin sorgularını da düşürmesin.
    """
    try:
        return await fn()
    except Exception:  # noqa: BLE001
        logger.exception("yonetim_ozeti: %s hesaplanamadı", ad)
        if db is not None:
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                logger.warning("yonetim_ozeti: geri alma başarısız", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Acil (SLA)
# ---------------------------------------------------------------------------
def _bekleyen_hedef(s: Any, d: Dict[str, Any]) -> Optional[Tuple[str, datetime, str]]:
    """(hedef_turu, hedef anı, durum) — ilk yanıt verilmemişse ilk yanıt, verilmişse çözüm."""
    for tur, alan in (("ilk_yanit", "ilk_yanit_hedef"), ("cozum", "cozum_hedef")):
        durum = d[tur]["durum"]
        if durum in ("zamaninda", "yaklasiyor", "asildi"):
            hedef = utc(getattr(s, alan))
            if hedef is not None:
                return tur, hedef, durum
    return None


async def acil_hesapla(db: AsyncSession, an: datetime) -> Optional[Dict[str, Any]]:
    from models.support_tickets import Support_tickets

    talepler = (
        await db.execute(
            select(Support_tickets)
            .where(func.coalesce(Support_tickets.status, "open").notin_(list(sla.KAPALI_DURUMLAR)))
            .order_by(Support_tickets.id.desc())
            .limit(500)
        )
    ).scalars().all()
    if not talepler:
        return None
    ayar = await sla.ayarlari_oku(db)
    satirlar = await sla.senkronla(db, talepler, ayar)
    adaylar = []
    for t in talepler:
        s = satirlar.get(t.id)
        if s is None:
            continue
        d = sla.durum_sozlugu(s, ayar, an)
        bekleyen = _bekleyen_hedef(s, d)
        if bekleyen is None:
            continue
        adaylar.append((bekleyen[1], t, s, bekleyen))
    if not adaylar:
        return None
    adaylar.sort(key=lambda x: (x[0], x[1].id))
    hedef, t, s, (tur, _, durum) = adaylar[0]
    risk = sum(1 for a in adaylar[1:] if a[3][2] in ("asildi", "yaklasiyor"))
    baslangic = utc(s.baslangic) or utc(t.created_at) or an
    return {
        "talep_id": t.id,
        "kod": f"D-{t.id}",
        "baslik": t.subject,
        "musteri": (t.client_name or "").strip() or eposta(t.client_email) or None,
        "musteri_eposta": eposta(t.client_email) or None,
        "oncelik": sla.oncelik_duzelt(t.priority),
        "hizmet": t.hizmet or None,
        "hedef_turu": tur,
        "hedef": hedef.isoformat(),
        "baslangic": baslangic.isoformat(),
        "kalan_sn": int((hedef - an).total_seconds()),
        "toplam_sn": max(1, int((hedef - baslangic).total_seconds())),
        "durum": durum,
        "siradaki": risk,
    }


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------
def _odeme_gunu(o: Any) -> Optional[date]:
    return tarih_coz(o.odeme_tarihi) or (tr_gun(o.odendi_at) if o.odendi_at else None) or (
        tr_gun(o.created_at) if o.created_at else None
    )


async def tahsilat_hesapla(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.payments import Payments

    bugun = tr_gun(an)
    onceki_ilk, onceki_son = onceki_ay_ayni_gun(bugun)
    gunler = son_gunler(bugun)
    pencere_bas = min(onceki_ilk, gunler[0])
    gunluk: Dict[date, float] = {}
    # Kaba süzgeç SQL'de (üç tarih alanından biri pencerede), kesin gün Python'da.
    kaba = gun_basi(pencere_bas) - timedelta(days=2)
    for o in (
        await db.execute(
            select(Payments).where(
                Payments.durum.in_(["odendi", "iade"]),
                or_(
                    Payments.odendi_at >= kaba,
                    Payments.created_at >= kaba,
                    Payments.odeme_tarihi >= (pencere_bas - timedelta(days=2)).isoformat(),
                ),
            )
        )
    ).scalars().all():
        if pb(o.para_birimi) != "TRY":
            continue
        gun = _odeme_gunu(o)
        if gun is None or gun < pencere_bas or gun > bugun:
            continue
        isaret = 1 if o.durum == "odendi" else -1
        gunluk[gun] = gunluk.get(gun, 0.0) + isaret * para(o.tutar)
    bu_ay = sum(v for g, v in gunluk.items() if g >= ay_basi(bugun))
    onceki = sum(v for g, v in gunluk.items() if onceki_ilk <= g <= onceki_son)
    return {
        "tutar": round(bu_ay, 2),
        "para_birimi": "TRY",
        "onceki": round(onceki, 2),
        "degisim_yuzde": yuzde_degisim(bu_ay, onceki),
        "seri": [round(gunluk.get(g, 0.0), 2) for g in gunler],
        "gunler": [g.isoformat() for g in gunler],
    }


async def _is_kayitlari(db: AsyncSession) -> Dict[str, List[Tuple[datetime, Optional[datetime]]]]:
    """Tür başına (açılış, kapanış) çiftleri; kapanış yoksa None (hâlâ açık)."""
    from models.destek_sla import TalepSla
    from models.proje_gorevleri import ProjectTasks
    from models.saha_servisi import SahaIsEmirleri
    from models.support_tickets import Support_tickets

    sonuc: Dict[str, List[Tuple[datetime, Optional[datetime]]]] = {"gorev": [], "destek": [], "is_emri": []}
    for olusturma, durum, tamam, guncel in (
        await db.execute(
            select(ProjectTasks.created_at, ProjectTasks.durum, ProjectTasks.tamamlandi_at, ProjectTasks.updated_at)
        )
    ).all():
        bas = utc(olusturma)
        if bas is None:
            continue
        kapanis = utc(tamam) if durum == "tamam" else None
        if durum == "tamam" and kapanis is None:
            kapanis = utc(guncel) or bas
        sonuc["gorev"].append((bas, kapanis))

    cozumler = {tid: utc(c) for tid, c in (await db.execute(select(TalepSla.ticket_id, TalepSla.cozum_at))).all()}
    for tid, olusturma, durum, guncel in (
        await db.execute(
            select(Support_tickets.id, Support_tickets.created_at, Support_tickets.status, Support_tickets.updated_at)
        )
    ).all():
        bas = utc(olusturma)
        if bas is None:
            continue
        kapali = (durum or "").strip().lower() in sla.KAPALI_DURUMLAR
        kapanis = (cozumler.get(tid) or utc(guncel) or bas) if kapali else None
        sonuc["destek"].append((bas, kapanis))

    for olusturma, durum, bitir, iptal, guncel in (
        await db.execute(
            select(
                SahaIsEmirleri.created_at, SahaIsEmirleri.durum, SahaIsEmirleri.bitir_at,
                SahaIsEmirleri.iptal_at, SahaIsEmirleri.updated_at,
            )
        )
    ).all():
        bas = utc(olusturma)
        if bas is None:
            continue
        kapanis: Optional[datetime] = None
        if durum not in IS_EMRI_ACIK:  # tamamlandı ya da iptal
            kapanis = (utc(bitir) if durum == "tamamlandi" else utc(iptal)) or utc(guncel) or bas
        sonuc["is_emri"].append((bas, kapanis))
    return sonuc


def _acik_mi(cift: Tuple[datetime, Optional[datetime]], an: datetime) -> bool:
    bas, kapanis = cift
    return bas <= an and (kapanis is None or kapanis > an)


async def isler_hesapla(db: AsyncSession, an: datetime) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(acik_isler, tamamlanan) — aynı kayıt kümesinden."""
    from models.saha_servisi import SahaIsEmirleri

    kayitlar = await _is_kayitlari(db)
    # Tamamlanan iş emri: yalnız "tamamlandi" (iptal tamamlanma sayılmaz).
    tamam_is_emri = [
        utc(b)
        for (b,) in (
            await db.execute(select(SahaIsEmirleri.bitir_at).where(SahaIsEmirleri.durum == "tamamlandi"))
        ).all()
        if b is not None
    ]

    def acik_sayisi(zaman: datetime) -> Dict[str, int]:
        return {tur: sum(1 for c in liste if _acik_mi(c, zaman)) for tur, liste in kayitlar.items()}

    bugun = tr_gun(an)
    gunler = son_gunler(bugun)
    simdi = acik_sayisi(an)
    seri = []
    for g in gunler:
        sinir = min(an, gun_basi(g + timedelta(days=1)))
        seri.append(sum(acik_sayisi(sinir).values()))
    onceki = sum(acik_sayisi(an - timedelta(days=30)).values())
    toplam = sum(simdi.values())
    acik = {
        "toplam": toplam,
        "gorev": simdi["gorev"],
        "destek": simdi["destek"],
        "is_emri": simdi["is_emri"],
        "onceki": onceki,
        "degisim_yuzde": yuzde_degisim(toplam, onceki),
        "seri": seri,
    }

    # Tamamlananlar: görev ve talep kapanışları + tamamlanan iş emirleri.
    kapanislar: Dict[str, List[date]] = {
        "gorev": [tr_gun(k) for _, k in kayitlar["gorev"] if k is not None],
        "destek": [tr_gun(k) for _, k in kayitlar["destek"] if k is not None],
        "is_emri": [tr_gun(k) for k in tamam_is_emri if k is not None],
    }
    onceki_ilk, onceki_son = onceki_ay_ayni_gun(bugun)
    bu_ay = {tur: sum(1 for g in l if ay_basi(bugun) <= g <= bugun) for tur, l in kapanislar.items()}
    gecen = sum(sum(1 for g in l if onceki_ilk <= g <= onceki_son) for l in kapanislar.values())
    bu_ay_toplam = sum(bu_ay.values())
    tum = [g for l in kapanislar.values() for g in l]
    tamamlanan = {
        "toplam": bu_ay_toplam,
        "gorev": bu_ay["gorev"],
        "destek": bu_ay["destek"],
        "is_emri": bu_ay["is_emri"],
        "onceki": gecen,
        "degisim_yuzde": yuzde_degisim(bu_ay_toplam, gecen),
        "seri": [sum(1 for x in tum if x == g) for g in gunler],
    }
    return acik, tamamlanan


async def sla_uyumu_hesapla(db: AsyncSession, an: datetime) -> Optional[Dict[str, Any]]:
    from models.destek_sla import TalepSla

    ayar = await sla.ayarlari_oku(db)
    sinir = an - timedelta(days=60)
    satirlar = (
        await db.execute(select(TalepSla).where(TalepSla.ilk_yanit_at.isnot(None), TalepSla.ilk_yanit_at >= sinir - timedelta(days=1)))
    ).scalars().all()

    def pencere(bas: datetime, bit: datetime) -> Tuple[int, int, List[int]]:
        karar = zamaninda = 0
        sureler: List[int] = []
        for s in satirlar:
            yanit, hedef, baslangic = utc(s.ilk_yanit_at), utc(s.ilk_yanit_hedef), utc(s.baslangic)
            if yanit is None or not (bas <= yanit <= bit):
                continue
            karar += 1
            if hedef is None or yanit <= hedef:
                zamaninda += 1
            if baslangic is not None:
                sureler.append(max(0, sla.mesai_dakikasi(baslangic, yanit, ayar.mesai)))
        return karar, zamaninda, sureler

    karar, zamaninda, sureler = pencere(an - timedelta(days=30), an)
    if karar == 0:
        return None
    uyum = round(zamaninda / karar * 100, 1)
    onceki_karar, onceki_zamaninda, _ = pencere(an - timedelta(days=60), an - timedelta(days=30))
    onceki_uyum = round(onceki_zamaninda / onceki_karar * 100, 1) if onceki_karar else None
    return {
        "uyum_yuzde": uyum,
        "karar_sayisi": karar,
        "ilk_yanit_ort_dk": round(sum(sureler) / len(sureler), 1) if sureler else None,
        "onceki_uyum_yuzde": onceki_uyum,
        "degisim_puan": round(uyum - onceki_uyum, 1) if onceki_uyum is not None else None,
    }


# ---------------------------------------------------------------------------
# Hizmet hattı
# ---------------------------------------------------------------------------
def _toplamlar(ciftler: Iterable[Tuple[str, float]]) -> List[Dict[str, Any]]:
    toplam: Dict[str, float] = {}
    for birim, tutar in ciftler:
        toplam[birim] = toplam.get(birim, 0.0) + tutar
    # TRY önde, sonra alfabetik.
    return [
        {"para_birimi": k, "tutar": round(v, 2)}
        for k, v in sorted(toplam.items(), key=lambda kv: (kv[0] != "TRY", kv[0]))
    ]


async def _talepler(db: AsyncSession, bas: datetime) -> List[Tuple[datetime, str]]:
    """`bas`tan beri gelen talepler: (zaman, e-posta) — iletişim, teklif isteği, CRM formu."""
    from models.crm import CrmAdaylari, CrmFormGonderimleri
    from models.inquiries import Inquiries
    from models.pricing import Pricing_inquiries

    genis = bas - timedelta(days=1)
    sonuc: List[Tuple[datetime, str]] = []
    for z, e in (await db.execute(select(Inquiries.created_at, Inquiries.email).where(Inquiries.created_at >= genis))).all():
        if utc(z) and utc(z) >= bas:  # type: ignore[operator]
            sonuc.append((utc(z), eposta(e)))  # type: ignore[arg-type]
    for z, e in (
        await db.execute(
            select(Pricing_inquiries.created_at, Pricing_inquiries.musteri_eposta).where(Pricing_inquiries.created_at >= genis)
        )
    ).all():
        if utc(z) and utc(z) >= bas:  # type: ignore[operator]
            sonuc.append((utc(z), eposta(e)))  # type: ignore[arg-type]
    for z, e in (
        await db.execute(
            select(CrmFormGonderimleri.created_at, CrmAdaylari.email)
            .select_from(CrmFormGonderimleri)
            .outerjoin(CrmAdaylari, CrmAdaylari.id == CrmFormGonderimleri.aday_id)
            .where(CrmFormGonderimleri.created_at >= genis)
        )
    ).all():
        if utc(z) and utc(z) >= bas:  # type: ignore[operator]
            sonuc.append((utc(z), eposta(e)))  # type: ignore[arg-type]
    return sonuc


async def _acik_faturalar(db: AsyncSession) -> List[Tuple[Any, Any]]:
    """(fatura, bakiye) — kalanı olan açık faturalar."""
    from models.invoices import Invoices
    from models.payments import Payments
    from services import faturalar as fs

    liste = (
        await db.execute(
            select(Invoices).where(
                or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
                or_(Invoices.status.is_(None), Invoices.status.notin_(list(fs.KAPALI_DURUMLAR))),
            )
        )
    ).scalars().all()
    if not liste:
        return []
    kimlikler = [f.id for f in liste]
    odemeler: Dict[int, List[Any]] = {}
    for o in (await db.execute(select(Payments).where(Payments.invoice_id.in_(kimlikler)))).scalars().all():
        odemeler.setdefault(o.invoice_id, []).append(o)
    iadeler: Dict[int, List[Any]] = {}
    for i in (
        await db.execute(select(Invoices).where(Invoices.tur == "iade", Invoices.bagli_fatura_id.in_(kimlikler)))
    ).scalars().all():
        iadeler.setdefault(i.bagli_fatura_id, []).append(i)
    sonuc = []
    for f in liste:
        b = fs.bakiye_hesapla(f, odemeler.get(f.id, []), iadeler.get(f.id, []))
        if b.kalan > fs.EPS:
            sonuc.append((f, b))
    return sonuc


async def _donusum(db: AsyncSession, an: datetime) -> Dict[str, Optional[float]]:
    from models.invoices import Invoices
    from models.payments import Payments
    from models.teklifler import Teklifler

    bas = an - timedelta(days=DONUSUM_GUN)
    teklifler = (await db.execute(select(Teklifler).where(Teklifler.durum != "taslak"))).scalars().all()

    # Talep → teklif: talep gönderen kişilerden sonrasında teklif gönderilenlerin oranı.
    ilk_talep: Dict[str, datetime] = {}
    for z, e in await _talepler(db, bas):
        if e and (e not in ilk_talep or z < ilk_talep[e]):
            ilk_talep[e] = z
    talep_teklif = None
    if ilk_talep:
        teklif_zamanlari: Dict[str, List[datetime]] = {}
        for tk in teklifler:
            z = utc(tk.gonderildi_at) or utc(tk.created_at)
            if z is None:
                continue
            for e in {eposta(tk.aday_eposta), eposta(tk.hesap_email)} - {""}:
                teklif_zamanlari.setdefault(e, []).append(z)
        donusen = sum(1 for e, z in ilk_talep.items() if any(x >= z for x in teklif_zamanlari.get(e, [])))
        talep_teklif = round(donusen / len(ilk_talep) * 100, 1)

    # Teklif → kabul: son 90 günde karara bağlanan (kabul/ret/süresi doldu) tekliflerde kabul oranı.
    kararlar = [
        tk for tk in teklifler
        if tk.durum in TEKLIF_KARAR and (utc(tk.karar_at) or utc(tk.updated_at) or utc(tk.created_at) or an) >= bas
    ]
    teklif_kabul = round(sum(1 for tk in kararlar if tk.durum == "kabul") / len(kararlar) * 100, 1) if kararlar else None

    # Ortalama tahsilat günü: tamamen ödenen faturalarda düzenleme → son ödeme.
    odenen = (
        await db.execute(select(Invoices).where(Invoices.status == "paid", or_(Invoices.tur.is_(None), Invoices.tur != "iade")))
    ).scalars().all()
    gunler: List[int] = []
    if odenen:
        son_odeme: Dict[int, date] = {}
        for o in (
            await db.execute(select(Payments).where(Payments.invoice_id.in_([f.id for f in odenen]), Payments.durum == "odendi"))
        ).scalars().all():
            g = _odeme_gunu(o)
            if g is not None and (o.invoice_id not in son_odeme or g > son_odeme[o.invoice_id]):
                son_odeme[o.invoice_id] = g
        sinir = tr_gun(bas)
        for f in odenen:
            son = son_odeme.get(f.id)
            duzenleme = tarih_coz(f.issue_date) or (tr_gun(f.created_at) if f.created_at else None)
            if son is None or duzenleme is None or son < sinir:
                continue
            gunler.append(max(0, (son - duzenleme).days))
    tahsilat_gun = round(sum(gunler) / len(gunler), 1) if gunler else None
    return {"talep_teklif": talep_teklif, "teklif_kabul": teklif_kabul, "tahsilat_gun": tahsilat_gun}


async def hizmet_hatti_hesapla(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.projects import Projects
    from models.signed_actions import SignedActions
    from models.sozlesmeler import Sozlesmeler
    from models.teklifler import Teklifler

    yeni_talep = len(await _talepler(db, an - timedelta(hours=24)))

    bekleyen_teklif = (
        await db.execute(select(Teklifler).where(Teklifler.durum.in_(list(TEKLIF_BEKLEYEN))))
    ).scalars().all()
    sozlesme = (
        await db.execute(select(func.count(Sozlesmeler.id)).where(Sozlesmeler.durum == "gonderildi"))
    ).scalar() or 0

    projeler = [
        p for p in (await db.execute(select(Projects))).scalars().all()
        if eposta(p.client_email) and (p.status or "").strip().lower() not in PROJE_KAPALI
    ]
    ilerlemeler = [max(0, min(100, int(p.progress or 0))) for p in projeler]

    teslim = 0
    for (son,) in (
        await db.execute(
            select(SignedActions.son_kullanma).where(
                SignedActions.tur == "teslimat_onay", SignedActions.durum == "bekliyor"
            )
        )
    ).all():
        if utc(son) is None or utc(son) > an:  # type: ignore[operator]
            teslim += 1

    faturalar = await _acik_faturalar(db)
    donusum = await _kalem("donusum", lambda: _donusum(db, an), db)
    return {
        "yeni_talep": {"sayi": yeni_talep, "bolum": "gelenKutusu"},
        "teklif": {
            "sayi": len(bekleyen_teklif),
            "toplamlar": _toplamlar((pb(tk.para_birimi), para(tk.genel_toplam)) for tk in bekleyen_teklif),
            "bolum": "teklifler",
        },
        "sozlesme": {"sayi": int(sozlesme), "bolum": "sozlesmeler"},
        "proje": {
            "sayi": len(projeler),
            "ort_ilerleme": round(sum(ilerlemeler) / len(ilerlemeler), 1) if ilerlemeler else None,
            "bolum": "projects",
        },
        "teslim": {"sayi": teslim, "bolum": "islemler"},
        "fatura": {
            "sayi": len(faturalar),
            "kalanlar": _toplamlar((pb(f.currency), float(b.kalan)) for f, b in faturalar),
            "bolum": "invoices",
        },
        "donusum": donusum or {"talep_teklif": None, "teklif_kabul": None, "tahsilat_gun": None},
    }


# ---------------------------------------------------------------------------
# Aktivite, kategori
# ---------------------------------------------------------------------------
async def aktivite_hesapla(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.audit_log import AuditLog

    bugun = tr_gun(an)
    dun = bugun - timedelta(days=1)
    bas = gun_basi(dun)
    kovalar = {bugun: [0] * 24, dun: [0] * 24}
    for (z,) in (await db.execute(select(AuditLog.created_at).where(AuditLog.created_at >= bas - timedelta(days=1)))).all():
        a = utc(z)
        if a is None or a < bas or a > an:
            continue
        yerel = a.astimezone(TR)
        if yerel.date() in kovalar:
            kovalar[yerel.date()][yerel.hour] += 1
    simdiki_saat = an.astimezone(TR).hour
    bugun_seri: List[Optional[int]] = [v if i <= simdiki_saat else None for i, v in enumerate(kovalar[bugun])]
    return {
        "bugun": bugun_seri,
        "dun": kovalar[dun],
        "toplam_bugun": sum(kovalar[bugun]),
        "toplam_dun": sum(kovalar[dun]),
        "kaynak": "audit_log",
    }


async def kategori_hesapla(db: AsyncSession, an: datetime) -> Dict[str, Any]:
    from models.audit_log import AuditLog
    from models.projects import Projects

    bugun = tr_gun(an)
    ay_ilk = ay_basi(bugun)
    onceki_ilk, onceki_son = onceki_ay_ayni_gun(bugun)
    projeler = [p for p in (await db.execute(select(Projects))).scalars().all() if eposta(p.client_email)]

    def acilis(p: Any) -> Optional[date]:
        return tr_gun(p.created_at) if p.created_at else None

    def kategori(p: Any) -> str:
        return (p.category or "").strip() or "—"

    kume = [
        p for p in projeler
        if (p.status or "").strip().lower() not in PROJE_KAPALI or (acilis(p) is not None and acilis(p) >= ay_ilk)
    ]
    sayac: Dict[str, int] = {}
    for p in kume:
        sayac[kategori(p)] = sayac.get(kategori(p), 0) + 1
    dagilim = [{"ad": k, "sayi": v} for k, v in sorted(sayac.items(), key=lambda kv: (-kv[1], kv[0]))]

    bu_ay_yeni: Dict[str, int] = {}
    gecen_ay_yeni: Dict[str, int] = {}
    for p in projeler:
        g = acilis(p)
        if g is None:
            continue
        if ay_ilk <= g <= bugun:
            bu_ay_yeni[kategori(p)] = bu_ay_yeni.get(kategori(p), 0) + 1
        elif onceki_ilk <= g <= onceki_son:
            gecen_ay_yeni[kategori(p)] = gecen_ay_yeni.get(kategori(p), 0) + 1
    en_hizli = None
    for k, v in bu_ay_yeni.items():
        onceki = gecen_ay_yeni.get(k, 0)
        if onceki and v > onceki:
            artis = round((v - onceki) / onceki * 100, 1)
            if en_hizli is None or artis > en_hizli["artis_yuzde"]:
                en_hizli = {"ad": k, "artis_yuzde": artis}

    # Ortalama süre: son 180 günde "completed"a geçen projelerde açılıştan tamamlanmaya (denetim kaydından).
    acilislar = {str(p.id): utc(p.created_at) for p in projeler if p.created_at}
    tamamlanma: Dict[str, datetime] = {}
    sinir = an - timedelta(days=180)
    for kayit_id, z, fark in (
        await db.execute(
            select(AuditLog.kayit_id, AuditLog.created_at, AuditLog.degisiklik_json).where(
                AuditLog.tablo == "projects", AuditLog.islem == "guncelle", AuditLog.created_at >= sinir - timedelta(days=1)
            )
        )
    ).all():
        if not kayit_id or kayit_id not in acilislar or not fark:
            continue
        try:
            durum = (json.loads(fark) or {}).get("status")
        except (ValueError, TypeError, AttributeError):
            continue
        if isinstance(durum, list) and len(durum) == 2 and str(durum[1] or "").lower() in ("completed", "tamamlandi"):
            a = utc(z)
            if a is not None and a >= sinir:
                tamamlanma[kayit_id] = a
    sureler = [
        max(0.0, (bitis - acilislar[k]).total_seconds() / 86400)  # type: ignore[operator]
        for k, bitis in tamamlanma.items()
        if acilislar.get(k) is not None
    ]
    return {
        "dagilim": dagilim,
        "toplam": len(kume),
        "bu_ay_yeni": sum(bu_ay_yeni.values()),
        "ort_sure_gun": round(sum(sureler) / len(sureler), 1) if sureler else None,
        "en_hizli": en_hizli,
    }


# ---------------------------------------------------------------------------
# Saha, son işler, bildirimler
# ---------------------------------------------------------------------------
DURUM_ADIMI = {"yeni": 0, "planlandi": 15, "yolda": 40, "iste": 70, "tamamlandi": 100}


def is_emri_ilerlemesi(ie: Any) -> int:
    if ie.durum == "iste" and ie.kontrol_listesi:
        try:
            maddeler = json.loads(ie.kontrol_listesi) or []
            yanitlar = json.loads(ie.kontrol_yanitlari or "{}") or {}
        except (ValueError, TypeError):
            maddeler, yanitlar = [], {}
        if isinstance(maddeler, list) and maddeler and isinstance(yanitlar, dict):
            dolu = sum(
                1 for m in maddeler
                if isinstance(m, dict) and yanitlar.get(str(m.get("id"))) not in (None, "", False)
            )
            return min(99, 50 + int(dolu / len(maddeler) * 49))
    return DURUM_ADIMI.get(ie.durum, 0)


async def saha_hesapla(db: AsyncSession, an: datetime) -> Optional[Dict[str, Any]]:
    from models.saha_servisi import (
        SahaAyarlari,
        SahaIsAtamalari,
        SahaIsEmirleri,
        SahaMusterileri,
        SahaTeknisyenleri,
    )

    bugun = tr_gun(an)
    adaylar = (
        await db.execute(select(SahaIsEmirleri).where(SahaIsEmirleri.durum.in_(list(IS_EMRI_ETKIN))))
    ).scalars().all()
    isler = [
        ie for ie in adaylar
        if ie.durum in ("yolda", "iste") or (ie.plan_bas is not None and tr_gun(ie.plan_bas) == bugun)
    ]
    if not isler:
        return None
    sira = {"iste": 0, "yolda": 1, "planlandi": 2}
    isler.sort(key=lambda ie: (sira.get(ie.durum, 9), utc(ie.plan_bas) or an, ie.id))
    kimlikler = [ie.id for ie in isler]
    atamalar: Dict[int, List[int]] = {}
    for is_id, tek_id in (
        await db.execute(select(SahaIsAtamalari.is_emri_id, SahaIsAtamalari.teknisyen_id).where(SahaIsAtamalari.is_emri_id.in_(kimlikler)))
    ).all():
        atamalar.setdefault(is_id, []).append(tek_id)
    tek_idler = sorted({t for l in atamalar.values() for t in l})
    teknisyenler = {
        t.id: t for t in (
            await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.id.in_(tek_idler)))
        ).scalars().all()
    } if tek_idler else {}
    musteriler = {
        m.id: m.ad for m in (
            await db.execute(select(SahaMusterileri).where(SahaMusterileri.id.in_([ie.musteri_id for ie in isler])))
        ).scalars().all()
    }
    firmalar = {
        a.hesap_email: a.firma_adi for a in (
            await db.execute(select(SahaAyarlari).where(SahaAyarlari.hesap_email.in_(list({ie.hesap_email for ie in isler}))))
        ).scalars().all()
    }
    is_listesi = []
    teknisyen_durumu: Dict[int, Dict[str, Any]] = {}
    for ie in isler:
        ilerleme = is_emri_ilerlemesi(ie)
        adlar = [teknisyenler[t].ad for t in atamalar.get(ie.id, []) if t in teknisyenler]
        is_listesi.append({
            "id": ie.id,
            "no": ie.no,
            "baslik": ie.baslik,
            "tur": ie.tur,
            "durum": ie.durum,
            "oncelik": ie.oncelik,
            "ilerleme": ilerleme,
            "plan_bas": iso(ie.plan_bas),
            "musteri": musteriler.get(ie.musteri_id) if not ie.anonim else None,
            "firma": firmalar.get(ie.hesap_email) or ie.hesap_email,
            "teknisyenler": adlar,
        })
        for t in atamalar.get(ie.id, []):
            if t not in teknisyenler:
                continue
            mevcut = teknisyen_durumu.get(t)
            # Teknisyenin en ileri durumdaki işi görünsün (işte > yolda > planlandı).
            if mevcut is None or sira.get(ie.durum, 9) < sira.get(mevcut["durum"], 9):
                teknisyen_durumu[t] = {
                    "id": t,
                    "ad": teknisyenler[t].ad,
                    "renk": teknisyenler[t].renk,
                    "durum": ie.durum,
                    "is_no": ie.no,
                    "is_baslik": ie.baslik,
                    "ilerleme": ilerleme,
                }
    tek_listesi = sorted(teknisyen_durumu.values(), key=lambda x: (sira.get(x["durum"], 9), x["ad"]))
    return {
        "isler": is_listesi[:6],
        "is_sayisi": len(is_listesi),
        "teknisyenler": tek_listesi[:6],
        "aktif": sum(1 for x in tek_listesi if x["durum"] in ("yolda", "iste")),
        "bolum": "sahaServisi",
    }


async def son_isler_hesapla(db: AsyncSession) -> List[Dict[str, Any]]:
    from models.projects import Projects
    from models.saha_servisi import SahaIsAtamalari, SahaIsEmirleri, SahaMusterileri, SahaTeknisyenleri
    from models.staff import Staff
    from models.support_tickets import Support_tickets
    from models.teklifler import Teklifler

    n = SON_IS_SAYISI
    adlar = {eposta(e): a for e, a in (await db.execute(select(Staff.email, Staff.ad))).all() if e}

    def kisi(e: Optional[str]) -> Optional[str]:
        e = eposta(e)
        if not e:
            return None
        return adlar.get(e) or e.split("@")[0]

    satirlar: List[Dict[str, Any]] = []
    for p in (
        await db.execute(
            select(Projects)
            .where(Projects.client_email.isnot(None), Projects.client_email != "")
            .order_by(Projects.created_at.desc(), Projects.id.desc())
            .limit(n)
        )
    ).scalars().all():
        satirlar.append({
            "tur": "proje", "id": p.id, "kod": f"PRJ-{p.id}",
            "musteri": (p.client_name or "").strip() or eposta(p.client_email),
            "hizmet": p.title, "kategori": p.category, "durum": p.status or None, "oncelik": None,
            "sorumlu": None, "tutar": None, "para_birimi": None, "zaman": iso(p.created_at), "bolum": "projects",
        })
    for t in (
        await db.execute(select(Support_tickets).order_by(Support_tickets.created_at.desc(), Support_tickets.id.desc()).limit(n))
    ).scalars().all():
        satirlar.append({
            "tur": "destek", "id": t.id, "kod": f"D-{t.id}",
            "musteri": (t.client_name or "").strip() or eposta(t.client_email),
            "hizmet": t.subject, "kategori": t.hizmet, "durum": t.status or "open",
            "oncelik": sla.oncelik_duzelt(t.priority), "sorumlu": kisi(t.atanan),
            "tutar": None, "para_birimi": None, "zaman": iso(t.created_at), "bolum": "tickets",
        })
    is_emirleri = (
        await db.execute(select(SahaIsEmirleri).order_by(SahaIsEmirleri.created_at.desc(), SahaIsEmirleri.id.desc()).limit(n))
    ).scalars().all()
    if is_emirleri:
        musteri = {
            m.id: m.ad for m in (
                await db.execute(select(SahaMusterileri).where(SahaMusterileri.id.in_([ie.musteri_id for ie in is_emirleri])))
            ).scalars().all()
        }
        ilk_teknisyen: Dict[int, str] = {}
        for is_id, ad in (
            await db.execute(
                select(SahaIsAtamalari.is_emri_id, SahaTeknisyenleri.ad)
                .join(SahaTeknisyenleri, SahaTeknisyenleri.id == SahaIsAtamalari.teknisyen_id)
                .where(SahaIsAtamalari.is_emri_id.in_([ie.id for ie in is_emirleri]))
                .order_by(SahaIsAtamalari.id)
            )
        ).all():
            ilk_teknisyen.setdefault(is_id, ad)
        for ie in is_emirleri:
            satirlar.append({
                "tur": "is_emri", "id": ie.id, "kod": ie.no,
                "musteri": None if ie.anonim else musteri.get(ie.musteri_id),
                "hizmet": ie.baslik, "kategori": ie.tur, "durum": ie.durum, "oncelik": ie.oncelik,
                "sorumlu": ilk_teknisyen.get(ie.id), "tutar": None, "para_birimi": None,
                "zaman": iso(ie.created_at), "bolum": "sahaServisi",
            })
    for tk in (
        await db.execute(select(Teklifler).order_by(Teklifler.created_at.desc(), Teklifler.id.desc()).limit(n))
    ).scalars().all():
        satirlar.append({
            "tur": "teklif", "id": tk.id, "kod": tk.no,
            "musteri": (tk.aday_ad or "").strip() or eposta(tk.hesap_email) or eposta(tk.aday_eposta) or None,
            "hizmet": tk.baslik, "kategori": None, "durum": tk.durum, "oncelik": None,
            "sorumlu": kisi(tk.olusturan_eposta), "tutar": para(tk.genel_toplam), "para_birimi": pb(tk.para_birimi),
            "zaman": iso(tk.created_at), "bolum": "teklifler",
        })
    en_eski = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def anahtar(s: Dict[str, Any]) -> Tuple[datetime, int]:
        z = datetime.fromisoformat(s["zaman"]) if s["zaman"] else en_eski
        return z, s["id"]

    satirlar.sort(key=anahtar, reverse=True)
    return satirlar[:n]


async def bildirimler_hesapla(db: AsyncSession, alici: str) -> List[Dict[str, Any]]:
    from models.notifications import Notifications

    e = eposta(alici)
    if not e:
        return []
    liste = (
        await db.execute(
            select(Notifications)
            .where(func.lower(Notifications.recipient_email) == e, Notifications.channel == "inapp")
            .order_by(Notifications.id.desc())
            .limit(BILDIRIM_SAYISI)
        )
    ).scalars().all()
    return [
        {
            "id": b.id, "tur": b.event_type, "baslik": b.title, "govde": b.body, "baglanti": b.link,
            "zaman": iso(b.created_at), "okundu": b.read_at is not None,
        }
        for b in liste
    ]


# ---------------------------------------------------------------------------
# Hepsi
# ---------------------------------------------------------------------------
async def yonetim_ozeti(db: AsyncSession, yonetici_eposta: str, an: Optional[datetime] = None) -> Dict[str, Any]:
    an = utc(an) or sla.simdi()
    acil = await _kalem("acil", lambda: acil_hesapla(db, an), db)
    tahsilat = await _kalem("tahsilat", lambda: tahsilat_hesapla(db, an), db)
    isler = await _kalem("isler", lambda: isler_hesapla(db, an), db)
    sla_uyumu = await _kalem("sla", lambda: sla_uyumu_hesapla(db, an), db)
    return {
        "olusturma": an.isoformat(),
        "acil": acil,
        "kpi": {
            "tahsilat": tahsilat,
            "acik_isler": isler[0] if isler else None,
            "tamamlanan": isler[1] if isler else None,
            "sla": sla_uyumu,
        },
        "hizmetHatti": await _kalem("hizmetHatti", lambda: hizmet_hatti_hesapla(db, an), db),
        "aktivite": await _kalem("aktivite", lambda: aktivite_hesapla(db, an), db),
        "kategori": await _kalem("kategori", lambda: kategori_hesapla(db, an), db),
        "saha": await _kalem("saha", lambda: saha_hesapla(db, an), db),
        "sonIsler": await _kalem("sonIsler", lambda: son_isler_hesapla(db), db),
        "bildirimler": await _kalem("bildirimler", lambda: bildirimler_hesapla(db, yonetici_eposta), db),
    }
