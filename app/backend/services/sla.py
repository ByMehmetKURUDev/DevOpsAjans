"""Faz 2C — Destek SLA: mesai saatine göre hedef hesabı, durum, uyarı ve eskalasyon.

Mesai
-----
Türkiye saati (UTC+3, yaz saati yok), hafta içi 09:00–18:00, tatil günleri
listesi ayardan (`sla_ayarlari`). SLA süresi MESAİ dakikasıyla sayılıyor:
Cuma 17:00'de açılan "4 saat" hedefli talebin hedefi Pazartesi 12:00.

Hedefler (mesai dakikası, öncelik başına; ayardan değişir)
    acil     ilk yanıt 60,  çözüm 240   (4 iş saati)
    yuksek   ilk yanıt 120, çözüm 540   (1 iş günü)
    normal   ilk yanıt 240, çözüm 1620  (3 iş günü)
    dusuk    ilk yanıt 540, çözüm 2700  (5 iş günü)

Durumlar: yok | zamaninda | yaklasiyor | asildi | karsilandi | gecikti
("gecikti" = karşılandı ama hedeften sonra).

Uyarı ve eskalasyon "bir kez": `talep_sla` satırındaki zaman damgası koşullu
UPDATE ile yalnız boşken doluyor; iki eş zamanlı zamanlı-görev turu aynı
bildirimi iki kez gönderemiyor.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TR = timezone(timedelta(hours=3))
AYAR_ANAHTARI = "sla_ayarlari"
ONCELIKLER = ("acil", "yuksek", "normal", "dusuk")
KAPALI_DURUMLAR = frozenset({"closed", "kapali", "cozuldu", "resolved"})

VARSAYILAN_HEDEFLER: Dict[str, Dict[str, int]] = {
    "acil": {"ilk_yanit_dk": 60, "cozum_dk": 240},
    "yuksek": {"ilk_yanit_dk": 120, "cozum_dk": 540},
    "normal": {"ilk_yanit_dk": 240, "cozum_dk": 1620},
    "dusuk": {"ilk_yanit_dk": 540, "cozum_dk": 2700},
}

#: Resmi tatiller. Dini bayramlar her yıl kayıyor; listeyi panelden
#: güncellemek gerekiyor. "YYYY-AA-GG yarım" = arife: mesai 13:00'te biter.
#: 2026–2027 tarihleri Diyanet takvimiyle karşılaştırıldı (1 Ekim 2026):
#: Ramazan 20–22 Mart 2026 (arife 19), Kurban 27–30 Mayıs 2026 (arife 26),
#: Ramazan 9–11 Mart 2027 (arife 8), Kurban 16–19 Mayıs 2027 (arife 15).
YARIM_GUN_SONU_DK = 13 * 60
VARSAYILAN_TATILLER: Tuple[str, ...] = (
    "2026-03-19 yarım", "2026-05-26 yarım", "2026-10-28 yarım",
    "2027-03-08 yarım", "2027-05-15 yarım", "2027-10-28 yarım",
    "2026-01-01", "2026-03-20", "2026-03-21", "2026-03-22", "2026-04-23", "2026-05-01",
    "2026-05-19", "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30", "2026-07-15",
    "2026-08-30", "2026-10-29",
    "2027-01-01", "2027-03-09", "2027-03-10", "2027-03-11", "2027-04-23", "2027-05-01",
    "2027-05-16", "2027-05-17", "2027-05-18", "2027-05-19", "2027-07-15", "2027-08-30",
    "2027-10-29",
)


@dataclass(frozen=True)
class MesaiAyari:
    bas_dk: int = 9 * 60
    bit_dk: int = 18 * 60
    #: Pazartesi=0 … Pazar=6
    gunler: FrozenSet[int] = frozenset({0, 1, 2, 3, 4})
    tatiller: FrozenSet[date] = frozenset()
    #: Arife gibi yarım günler: mesai YARIM_GUN_SONU_DK'da biter.
    yarim_gunler: FrozenSet[date] = frozenset()


@dataclass
class SlaAyarlari:
    mesai: MesaiAyari = field(default_factory=MesaiAyari)
    hedefler: Dict[str, Dict[str, int]] = field(default_factory=lambda: {k: dict(v) for k, v in VARSAYILAN_HEDEFLER.items()})

    def sozluk(self) -> Dict[str, Any]:
        return {
            "mesai": {
                "bas": f"{self.mesai.bas_dk // 60:02d}:{self.mesai.bas_dk % 60:02d}",
                "bit": f"{self.mesai.bit_dk // 60:02d}:{self.mesai.bit_dk % 60:02d}",
                "gunler": sorted(self.mesai.gunler),
            },
            "tatiller": sorted(
                [d.isoformat() for d in self.mesai.tatiller]
                + [f"{d.isoformat()} yarım" for d in self.mesai.yarim_gunler if d not in self.mesai.tatiller]
            ),
            "hedefler": {k: dict(v) for k, v in self.hedefler.items()},
        }


class SlaHatasi(Exception):
    def __init__(self, kod: str):
        super().__init__(kod)
        self.kod = kod


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def oncelik_duzelt(ham: Optional[str]) -> str:
    deger = (ham or "").strip().lower()
    if deger in ("acil", "urgent", "critical", "kritik"):
        return "acil"
    if deger in ("yuksek", "yüksek", "high"):
        return "yuksek"
    if deger in ("dusuk", "düşük", "low"):
        return "dusuk"
    return "normal"


# ---------------------------------------------------------------------------
# Saf mesai hesapları (birim testli)
# ---------------------------------------------------------------------------
def _pencere(gun: date, ayar: MesaiAyari) -> Optional[Tuple[datetime, datetime]]:
    if gun.weekday() not in ayar.gunler or gun in ayar.tatiller or ayar.bit_dk <= ayar.bas_dk:
        return None
    bit_dk = ayar.bit_dk
    if gun in ayar.yarim_gunler:
        bit_dk = min(bit_dk, YARIM_GUN_SONU_DK)
        if bit_dk <= ayar.bas_dk:
            return None
    gece = datetime.combine(gun, time(0, 0), tzinfo=TR)
    return gece + timedelta(minutes=ayar.bas_dk), gece + timedelta(minutes=bit_dk)


def mesai_ekle(baslangic: datetime, dakika: int, ayar: MesaiAyari) -> datetime:
    """`baslangic`tan itibaren `dakika` mesai dakikası sonrası (UTC döner)."""
    imlec = utc(baslangic).astimezone(TR)  # type: ignore[union-attr]
    kalan = timedelta(minutes=max(0, int(dakika)))
    for _ in range(3700):  # 10 yıl — tatil listesi bozuk olsa da döngü biter
        pencere = _pencere(imlec.date(), ayar)
        if pencere is not None:
            bas, bit = pencere
            if imlec < bas:
                imlec = bas
            if imlec < bit:
                musait = bit - imlec
                if kalan <= musait:
                    return (imlec + kalan).astimezone(timezone.utc)
                kalan -= musait
        imlec = datetime.combine(imlec.date() + timedelta(days=1), time(0, 0), tzinfo=TR)
    raise SlaHatasi("mesai_yok")


def mesai_dakikasi(bas: datetime, bit: datetime, ayar: MesaiAyari) -> int:
    """İki an arasındaki mesai dakikası (bit < bas ise eksi)."""
    a, b = utc(bas), utc(bit)
    if a is None or b is None:
        return 0
    isaret = 1
    if b < a:
        a, b, isaret = b, a, -1
    a_tr, b_tr = a.astimezone(TR), b.astimezone(TR)
    toplam = timedelta(0)
    gun = a_tr.date()
    son = b_tr.date()
    sayac = 0
    while gun <= son and sayac < 3700:
        pencere = _pencere(gun, ayar)
        if pencere is not None:
            p_bas, p_bit = pencere
            kes_bas = max(p_bas, a_tr)
            kes_bit = min(p_bit, b_tr)
            if kes_bit > kes_bas:
                toplam += kes_bit - kes_bas
        gun += timedelta(days=1)
        sayac += 1
    return isaret * int(toplam.total_seconds() // 60)


def hedef_durumu(
    hedef: Optional[datetime],
    tamam: Optional[datetime],
    an: datetime,
    toplam_dk: int,
    ayar: MesaiAyari,
) -> Dict[str, Any]:
    if hedef is None:
        return {"durum": "yok", "hedef": None, "kalan_dk": None}
    hedef_u = utc(hedef)
    if tamam is not None:
        durum = "karsilandi" if utc(tamam) <= hedef_u else "gecikti"  # type: ignore[operator]
        return {"durum": durum, "hedef": hedef_u.isoformat(), "kalan_dk": None, "tamam": utc(tamam).isoformat()}  # type: ignore[union-attr]
    if utc(an) >= hedef_u:  # type: ignore[operator]
        return {"durum": "asildi", "hedef": hedef_u.isoformat(), "kalan_dk": -mesai_dakikasi(hedef_u, an, ayar)}  # type: ignore[arg-type,union-attr]
    kalan = mesai_dakikasi(an, hedef_u, ayar)  # type: ignore[arg-type]
    esik = max(30, int(toplam_dk * 0.25))
    return {
        "durum": "yaklasiyor" if kalan <= esik else "zamaninda",
        "hedef": hedef_u.isoformat(),  # type: ignore[union-attr]
        "kalan_dk": kalan,
    }


# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------
def _saat_dk(metin: Any) -> int:
    try:
        s, d = str(metin).strip().split(":")
        s_i, d_i = int(s), int(d)
    except (ValueError, AttributeError):
        raise SlaHatasi("gecersiz_saat")
    if not (0 <= s_i <= 24 and 0 <= d_i < 60) or s_i * 60 + d_i > 24 * 60:
        raise SlaHatasi("gecersiz_saat")
    return s_i * 60 + d_i


def _tatilleri_ayir(liste: Any) -> Tuple[FrozenSet[date], FrozenSet[date]]:
    """"2026-03-20" → tam gün; "2026-03-19 yarım" (ya da "yarim") → yarım gün."""
    tam, yarim = set(), set()
    for t in liste:
        metin = str(t).strip()
        try:
            gun = date.fromisoformat(metin[:10])
        except ValueError:
            raise SlaHatasi("gecersiz_tatil")
        ek = metin[10:].strip().lower()
        if ek in ("", ):
            tam.add(gun)
        elif ek in ("yarım", "yarim", "yarım gün", "yarim gun", "½", "1/2"):
            yarim.add(gun)
        else:
            raise SlaHatasi("gecersiz_tatil")
    return frozenset(tam), frozenset(yarim - tam)


def ayarlari_coz(ham: Any, sessiz: bool = True) -> SlaAyarlari:
    """Kaydedilmiş/gönderilmiş ayarı doğrular. `sessiz` ise bozuk alan varsayılana düşer."""
    tam0, yarim0 = _tatilleri_ayir(VARSAYILAN_TATILLER)
    ayar = SlaAyarlari(mesai=MesaiAyari(tatiller=tam0, yarim_gunler=yarim0))
    if not isinstance(ham, dict):
        return ayar
    try:
        mesai = ham.get("mesai") or {}
        bas = _saat_dk(mesai.get("bas", "09:00"))
        bit = _saat_dk(mesai.get("bit", "18:00"))
        if bit <= bas:
            raise SlaHatasi("gecersiz_saat")
        gunler = mesai.get("gunler", [0, 1, 2, 3, 4])
        if not isinstance(gunler, list) or not gunler or any(
            isinstance(g, bool) or not isinstance(g, int) or not 0 <= g <= 6 for g in gunler
        ):
            raise SlaHatasi("gecersiz_gunler")
        tatil_ham = ham.get("tatiller", list(VARSAYILAN_TATILLER))
        if not isinstance(tatil_ham, list):
            raise SlaHatasi("gecersiz_tatil")
        tatiller, yarim_gunler = _tatilleri_ayir(tatil_ham)
        hedefler = {k: dict(v) for k, v in VARSAYILAN_HEDEFLER.items()}
        for oncelik, deger in (ham.get("hedefler") or {}).items():
            if oncelik not in ONCELIKLER or not isinstance(deger, dict):
                raise SlaHatasi("gecersiz_hedef")
            for alan in ("ilk_yanit_dk", "cozum_dk"):
                if alan in deger:
                    v = deger[alan]
                    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 60 * 24 * 60:
                        raise SlaHatasi("gecersiz_hedef")
                    hedefler[oncelik][alan] = v
            if hedefler[oncelik]["cozum_dk"] < hedefler[oncelik]["ilk_yanit_dk"]:
                raise SlaHatasi("gecersiz_hedef")
        return SlaAyarlari(
            mesai=MesaiAyari(
                bas_dk=bas, bit_dk=bit, gunler=frozenset(gunler),
                tatiller=frozenset(tatiller), yarim_gunler=frozenset(yarim_gunler),
            ),
            hedefler=hedefler,
        )
    except SlaHatasi:
        if not sessiz:
            raise
        logger.warning("SLA ayarı bozuk, varsayılan kullanılıyor")
        return ayar


async def ayarlari_oku(db: AsyncSession) -> SlaAyarlari:
    from models.site_settings import Site_settings

    try:
        satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == AYAR_ANAHTARI))).scalars().first()
        if satir and satir.setting_value:
            return ayarlari_coz(json.loads(satir.setting_value))
    except Exception:  # noqa: BLE001
        logger.warning("SLA ayarı okunamadı", exc_info=True)
    return ayarlari_coz(None)


async def ayarlari_yaz(db: AsyncSession, ham: Any) -> SlaAyarlari:
    from models.site_settings import Site_settings

    ayar = ayarlari_coz(ham, sessiz=False)
    metin = json.dumps(ayar.sozluk(), ensure_ascii=False)
    satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == AYAR_ANAHTARI))).scalars().first()
    if satir:
        satir.setting_value = metin
    else:
        db.add(Site_settings(setting_key=AYAR_ANAHTARI, setting_value=metin, group_name="destek", label="SLA: mesai, tatiller, hedefler"))
    await db.commit()
    return ayar


# ---------------------------------------------------------------------------
# Talep başına SLA satırı
# ---------------------------------------------------------------------------
def hedefleri_hesapla(baslangic: datetime, oncelik: str, ayar: SlaAyarlari) -> Tuple[datetime, datetime]:
    h = ayar.hedefler.get(oncelik) or ayar.hedefler["normal"]
    return mesai_ekle(baslangic, h["ilk_yanit_dk"], ayar.mesai), mesai_ekle(baslangic, h["cozum_dk"], ayar.mesai)


async def talep_icin_baslat(db: AsyncSession, talep: Any, ayar: Optional[SlaAyarlari] = None) -> Any:
    """Yeni talep açıldığında SLA satırını yazar (commit eder)."""
    from models.destek_sla import TalepSla

    mevcut = (await db.execute(select(TalepSla).where(TalepSla.ticket_id == talep.id))).scalars().first()
    if mevcut is not None:
        return mevcut
    ayar = ayar or await ayarlari_oku(db)
    oncelik = oncelik_duzelt(talep.priority)
    bas = utc(talep.created_at) or simdi()
    ilk, cozum = hedefleri_hesapla(bas, oncelik, ayar)
    satir = TalepSla(ticket_id=talep.id, oncelik=oncelik, baslangic=bas, ilk_yanit_hedef=ilk, cozum_hedef=cozum)
    db.add(satir)
    await db.commit()
    return satir


async def _ilk_ajans_yanitlari(db: AsyncSession, idler: Sequence[int]) -> Dict[int, datetime]:
    from models.ticket_replies import Ticket_replies

    if not idler:
        return {}
    satirlar = await db.execute(
        select(Ticket_replies.ticket_id, func.min(Ticket_replies.created_at))
        .where(Ticket_replies.ticket_id.in_(list(idler)), Ticket_replies.yazan == "ajans")
        .group_by(Ticket_replies.ticket_id)
    )
    return {tid: utc(an) for tid, an in satirlar.all() if an is not None}  # type: ignore[misc]


async def senkronla(db: AsyncSession, talepler: Iterable[Any], ayar: Optional[SlaAyarlari] = None) -> Dict[int, Any]:
    """Talep listesi için SLA satırlarını hazırlar/günceller (commit eder); {ticket_id: satır}."""
    from models.destek_sla import TalepSla

    talepler = list(talepler)
    if not talepler:
        return {}
    ayar = ayar or await ayarlari_oku(db)
    idler = [t.id for t in talepler]
    satirlar = {s.ticket_id: s for s in (await db.execute(select(TalepSla).where(TalepSla.ticket_id.in_(idler)))).scalars().all()}
    yanitlar = await _ilk_ajans_yanitlari(db, idler)
    an = simdi()
    for t in talepler:
        s = satirlar.get(t.id)
        oncelik = oncelik_duzelt(t.priority)
        if s is None:
            bas = utc(t.created_at) or an
            ilk, cozum = hedefleri_hesapla(bas, oncelik, ayar)
            s = TalepSla(ticket_id=t.id, oncelik=oncelik, baslangic=bas, ilk_yanit_hedef=ilk, cozum_hedef=cozum)
            # Özellik açılmadan önceki talep: geçmişte kalmış hedef için
            # geriye dönük uyarı/eskalasyon yağmuru olmasın.
            if utc(ilk) <= an:  # type: ignore[operator]
                s.uyari_ilk_at = s.eskalasyon_ilk_at = an
            if utc(cozum) <= an:  # type: ignore[operator]
                s.uyari_cozum_at = s.eskalasyon_cozum_at = an
            db.add(s)
            satirlar[t.id] = s
        elif s.oncelik != oncelik:
            s.oncelik = oncelik
            s.ilk_yanit_hedef, s.cozum_hedef = hedefleri_hesapla(utc(s.baslangic), oncelik, ayar)  # type: ignore[arg-type]
        if s.ilk_yanit_at is None:
            ilk_yanit = yanitlar.get(t.id)
            if ilk_yanit is None and (t.reply or "").strip():
                ilk_yanit = utc(t.updated_at) or an  # eski tek satırlık cevap alanı
            if ilk_yanit is not None:
                s.ilk_yanit_at = ilk_yanit
        kapali = (t.status or "").strip().lower() in KAPALI_DURUMLAR
        if kapali and s.cozum_at is None:
            s.cozum_at = an
            if s.ilk_yanit_at is None:
                # Yanıtsız kapatılan talep: kapatmanın kendisi ilk temas.
                s.ilk_yanit_at = an
        elif not kapali and s.cozum_at is not None:
            s.cozum_at = None  # yeniden açıldı
    await db.commit()
    return satirlar


def durum_sozlugu(s: Any, ayar: SlaAyarlari, an: Optional[datetime] = None) -> Dict[str, Any]:
    an = an or simdi()
    h = ayar.hedefler.get(s.oncelik) or ayar.hedefler["normal"]
    return {
        "ticket_id": s.ticket_id,
        "oncelik": s.oncelik,
        "ilk_yanit": hedef_durumu(utc(s.ilk_yanit_hedef), utc(s.ilk_yanit_at), an, h["ilk_yanit_dk"], ayar.mesai),
        "cozum": hedef_durumu(utc(s.cozum_hedef), utc(s.cozum_at), an, h["cozum_dk"], ayar.mesai),
    }


def ozet_durum(d: Dict[str, Any]) -> str:
    """Rozet için tek durum: en kötü açık hedef."""
    sira = ["asildi", "yaklasiyor", "zamaninda", "gecikti", "karsilandi", "yok"]
    adaylar = [d["ilk_yanit"]["durum"], d["cozum"]["durum"]]
    return min(adaylar, key=lambda x: sira.index(x) if x in sira else len(sira))


async def _tek_sefer(db: AsyncSession, satir_id: int, alan: str) -> bool:
    from models.destek_sla import TalepSla

    kolon = getattr(TalepSla, alan)
    sonuc = await db.execute(
        update(TalepSla)
        .where(TalepSla.id == satir_id, kolon.is_(None))
        .values({alan: simdi()})
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(sonuc.rowcount or 0) == 1


async def sla_kontrolu(db: AsyncSession) -> Dict[str, Any]:
    """Zamanlı görev: açık talepleri senkronlar; yaklaşınca uyarı, aşınca eskalasyon (bir kez)."""
    from models.support_tickets import Support_tickets
    from services.notify import admin_recipients, dispatch

    ayar = await ayarlari_oku(db)
    talepler = (
        await db.execute(
            select(Support_tickets)
            .where(func.coalesce(Support_tickets.status, "open").notin_(list(KAPALI_DURUMLAR)))
            .order_by(Support_tickets.id.desc())
            .limit(500)
        )
    ).scalars().all()
    satirlar = await senkronla(db, talepler, ayar)
    an = simdi()
    uyari = eskalasyon = 0
    yoneticiler: Optional[List[Dict[str, Any]]] = None
    for t in talepler:
        s = satirlar.get(t.id)
        if s is None:
            continue
        d = durum_sozlugu(s, ayar, an)
        for hedef_adi, uyari_alani, esk_alani, etiket in (
            ("ilk_yanit", "uyari_ilk_at", "eskalasyon_ilk_at", "ilk yanıt"),
            ("cozum", "uyari_cozum_at", "eskalasyon_cozum_at", "çözüm"),
        ):
            durum = d[hedef_adi]["durum"]
            olay = None
            if durum == "asildi" and getattr(s, esk_alani) is None:
                if await _tek_sefer(db, s.id, esk_alani):
                    olay = "sla_asildi"
                    eskalasyon += 1
                    # Aşılmış hedef için ayrıca "yaklaşıyor" gitmesin.
                    if getattr(s, uyari_alani) is None:
                        await _tek_sefer(db, s.id, uyari_alani)
            elif durum == "yaklasiyor" and getattr(s, uyari_alani) is None:
                if await _tek_sefer(db, s.id, uyari_alani):
                    olay = "sla_yaklasiyor"
                    uyari += 1
            if olay is None:
                continue
            if yoneticiler is None:
                yoneticiler = await admin_recipients(db)
            alicilar = list(yoneticiler)
            atanan = (t.atanan or "").strip().lower()
            if atanan and all(a.get("email", "").lower() != atanan for a in alicilar):
                alicilar.append({"email": atanan, "role": "admin"})
            if olay == "sla_asildi":
                baslik = f"SLA aşıldı ({etiket}): #{t.id} {t.subject}"
                govde = f"#{t.id} numaralı talepte {etiket} hedefi aşıldı. Müşteri: {t.client_name or t.client_email or '—'}."
            else:
                baslik = f"SLA yaklaşıyor ({etiket}): #{t.id} {t.subject}"
                govde = f"#{t.id} numaralı talepte {etiket} hedefine {d[hedef_adi]['kalan_dk']} mesai dakikası kaldı."
            await dispatch(
                db, event_type=olay, title=baslik, body=govde, recipients=alicilar,
                link="/admin", ref_type="ticket", ref_id=t.id,
            )
    return {"acik_talep": len(talepler), "uyari": uyari, "eskalasyon": eskalasyon}
