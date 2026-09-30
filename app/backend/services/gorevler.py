"""Faz 2B — proje görevleri: kurallar, revizyon sayacı, bildirimler.

Kurallar
--------
* Bağımlılık: `A → B` = "A, B bitmeden tamama geçemez". Kenar eklenirken
  döngü aranıyor (B'den bağımlılıklar izlenerek A'ya varılabiliyorsa 409).
  Aynı projedeki görevler arasında; kendine bağımlılık yok.
* Üst görev: aynı projede, zincirde kendisi olamaz (döngü 409).
* "tamam"a geçiş (tekil güncelleme ya da Kanban toplu sıra) bitmemiş
  bağımlılık varsa 409 `bagimlilik_bitmedi` + bekleyen görevlerin listesi.
  Toplu güncellemede kural SON duruma göre bakılıyor ve hiçbir satır
  değişmiyor (hep ya da hiç).

Revizyon sayacı
---------------
Müşteri başına, takvim ayı (Türkiye saati). Kullanılan = o ayın tarihli
"revizyon" saat girişleri (etiketi "revizyon" olan görevlere girilen
saatler; 1E'deki revizyon isteği otomatik olarak böyle bir görev açıyor).
Hak = müşterinin paketindeki (`pricing_scales.revizyon_saat`, ör. "8s")
değer; paket yoksa ya da sayı içermiyorsa ("Kullandıkça Öde") müşterinin
projelerine elle girilmiş `aylik_revizyon_saati` toplamı; o da yoksa hak
yok (sayaç yalnız kullanılanı gösterir). Hak aşılınca yöneticiye ayda bir
kez `revizyon_asildi` bildirimi gidiyor; arayüz aşan kısmı krediden düşmeyi
öneriyor.
"""

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import HTTPException
from models.proje_gorevleri import (
    GOREV_DURUMLARI,
    ProjectTasks,
    RevizyonUyarilari,
    TaskChecklist,
    TaskDependencies,
    TaskTimeEntries,
)
from models.projects import Projects
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

REVIZYON_ETIKETI = "revizyon"
ETIKET_SINIRI = 10
ETIKET_UZUNLUGU = 30
#: Müşteriye bildirim giden durumlar (matris: `gorev_guncellendi`).
BILDIRIMLI_DURUMLAR = ("incelemede", "tamam")
DURUM_ADLARI = {
    "yapilacak": ("Yapılacak", "To do"),
    "suruyor": ("Sürüyor", "In progress"),
    "incelemede": ("İncelemede", "In review"),
    "tamam": ("Tamamlandı", "Done"),
}


class GorevHatasi(HTTPException):
    """Uca olduğu gibi çıkan hata: `detail = {"kod": ..., **ek}`."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(status_code=durum, detail={"kod": kod, **ek})
        self.durum = durum
        self.kod = kod
        self.ek = ek


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def _bugun() -> date:
    """Türkiye saatine göre bugün (testler monkeypatch ile kaydırıyor)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except Exception:  # noqa: BLE001
        return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def bugun() -> date:
    return _bugun()


def ay_araligi(gun: date) -> Tuple[date, date]:
    """[ayın ilk günü, sonraki ayın ilk günü)"""
    bas = gun.replace(day=1)
    bit = (bas.replace(year=bas.year + 1, month=1) if bas.month == 12 else bas.replace(month=bas.month + 1))
    return bas, bit


def _yerel_gun(an: Optional[datetime]) -> Optional[date]:
    if an is None:
        return None
    if an.tzinfo is None:
        an = an.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return an.astimezone(ZoneInfo("Europe/Istanbul")).date()
    except Exception:  # noqa: BLE001
        return (an.astimezone(timezone.utc) + timedelta(hours=3)).date()


def iso(an: Any) -> Optional[str]:
    if an is None:
        return None
    if isinstance(an, datetime):
        if an.tzinfo is None:
            an = an.replace(tzinfo=timezone.utc)
        return an.isoformat()
    if isinstance(an, date):
        return an.isoformat()
    return str(an)


def tarih_coz(deger: Any) -> Optional[date]:
    """YYYY-MM-DD → date; boş → None; geçersiz → 400."""
    if deger is None:
        return None
    if isinstance(deger, date) and not isinstance(deger, datetime):
        return deger
    metin = str(deger).strip()
    if not metin:
        return None
    try:
        gun = datetime.strptime(metin[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise GorevHatasi(400, "tarih_gecersiz") from exc
    if not 2000 <= gun.year <= 2100:
        raise GorevHatasi(400, "tarih_gecersiz")
    return gun


def etiketleri_coz(ham: Optional[str]) -> List[str]:
    if not ham:
        return []
    try:
        liste = json.loads(ham)
    except (TypeError, ValueError):
        return []
    return [str(x) for x in liste if isinstance(x, str)] if isinstance(liste, list) else []


def etiketleri_duzelt(ham: Any) -> List[str]:
    if ham is None:
        return []
    if isinstance(ham, str):
        ham = [p for p in ham.split(",")]
    if not isinstance(ham, list):
        raise GorevHatasi(400, "etiket_gecersiz")
    sonuc: List[str] = []
    for e in ham:
        if not isinstance(e, str):
            raise GorevHatasi(400, "etiket_gecersiz")
        temiz = e.strip().lower()[:ETIKET_UZUNLUGU]
        if temiz and temiz not in sonuc:
            sonuc.append(temiz)
    if len(sonuc) > ETIKET_SINIRI:
        raise GorevHatasi(400, "etiket_siniri")
    return sonuc


def revizyon_mu(g: ProjectTasks) -> bool:
    return REVIZYON_ETIKETI in etiketleri_coz(g.etiketler)


def saat_dogrula(deger: Any, *, sifir_olabilir: bool = False, ust: float = 1000.0) -> Optional[float]:
    if deger is None or deger == "":
        return None
    try:
        s = float(deger)
    except (TypeError, ValueError) as exc:
        raise GorevHatasi(400, "saat_gecersiz") from exc
    if s != s or s < 0 or s > ust or (s == 0 and not sifir_olabilir):
        raise GorevHatasi(400, "saat_gecersiz")
    if abs(s * 4 - round(s * 4)) > 1e-6:
        raise GorevHatasi(400, "saat_ceyrek")
    return round(s * 4) / 4


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------


def kontrol_sozlugu(k: TaskChecklist) -> Dict[str, Any]:
    return {"id": k.id, "gorev_id": k.gorev_id, "metin": k.metin, "tamam": bool(k.tamam), "sira": k.sira}


def gorev_sozlugu(
    g: ProjectTasks,
    kontroller: Iterable[TaskChecklist] = (),
    bagimliliklar: Iterable[int] = (),
    bekleyenler: Iterable[int] = (),
) -> Dict[str, Any]:
    """Yöneticinin gördüğü tam görev."""
    kontroller = sorted(kontroller, key=lambda k: (k.sira, k.id))
    return {
        "id": g.id,
        "proje_id": g.proje_id,
        "baslik": g.baslik,
        "aciklama": g.aciklama,
        "durum": g.durum,
        "oncelik": g.oncelik,
        "atanan": g.atanan,
        "bitis_tarihi": iso(g.bitis_tarihi),
        "sira": g.sira,
        "musteriye_gorunur": bool(g.musteriye_gorunur),
        "ust_gorev_id": g.ust_gorev_id,
        "kilometre_tasi": bool(g.kilometre_tasi),
        "tahmini_saat": g.tahmini_saat,
        "harcanan_saat": float(g.harcanan_saat or 0),
        "etiketler": etiketleri_coz(g.etiketler),
        "geri_bildirim_id": g.geri_bildirim_id,
        "tamamlandi_at": iso(g.tamamlandi_at),
        "created_at": iso(g.created_at),
        "kontrol_listesi": [kontrol_sozlugu(k) for k in kontroller],
        "bagimliliklar": sorted(set(bagimliliklar)),
        #: Bitmemiş bağımlılıklar (arayüz "tamam" sütununa bırakırken uyarıyor).
        "bekleyen_bagimliliklar": sorted(set(bekleyenler)),
    }


def musteri_gorev_sozlugu(g: ProjectTasks, kontroller: Iterable[TaskChecklist], gorunur_idler: Set[int]) -> Dict[str, Any]:
    """Müşterinin gördüğü görev: atanan kişi, saatler, etiketler, iç kimlikler yok."""
    kontroller = list(kontroller)
    return {
        "id": g.id,
        "baslik": g.baslik,
        "aciklama": g.aciklama,
        "durum": g.durum,
        "oncelik": g.oncelik,
        "bitis_tarihi": iso(g.bitis_tarihi),
        "sira": g.sira,
        "ust_gorev_id": g.ust_gorev_id if g.ust_gorev_id in gorunur_idler else None,
        "kilometre_tasi": bool(g.kilometre_tasi),
        "kontrol": {"tamam": sum(1 for k in kontroller if k.tamam), "toplam": len(kontroller)},
        "tamamlandi_at": iso(g.tamamlandi_at),
    }


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------


async def proje_bul(db: AsyncSession, proje_id: int) -> Projects:
    p = (await db.execute(select(Projects).where(Projects.id == proje_id))).scalar_one_or_none()
    if p is None:
        raise GorevHatasi(404, "proje_yok")
    return p


async def gorev_bul(db: AsyncSession, gorev_id: int) -> ProjectTasks:
    g = (await db.execute(select(ProjectTasks).where(ProjectTasks.id == gorev_id))).scalar_one_or_none()
    if g is None:
        raise GorevHatasi(404, "gorev_yok")
    return g


async def proje_gorevleri(db: AsyncSession, proje_id: int) -> List[ProjectTasks]:
    return list(
        (
            await db.execute(
                select(ProjectTasks)
                .where(ProjectTasks.proje_id == proje_id)
                .order_by(ProjectTasks.sira, ProjectTasks.id)
            )
        ).scalars().all()
    )


async def kontroller_sozlugu(db: AsyncSession, gorev_idler: List[int]) -> Dict[int, List[TaskChecklist]]:
    sonuc: Dict[int, List[TaskChecklist]] = {}
    if not gorev_idler:
        return sonuc
    for k in (
        await db.execute(select(TaskChecklist).where(TaskChecklist.gorev_id.in_(gorev_idler)))
    ).scalars().all():
        sonuc.setdefault(k.gorev_id, []).append(k)
    return sonuc


async def bagimlilik_kenarlari(db: AsyncSession, gorev_idler: List[int]) -> Dict[int, Set[int]]:
    """gorev_id → {bagli_oldugu_id}"""
    kenarlar: Dict[int, Set[int]] = {}
    if not gorev_idler:
        return kenarlar
    for d in (
        await db.execute(select(TaskDependencies).where(TaskDependencies.gorev_id.in_(gorev_idler)))
    ).scalars().all():
        kenarlar.setdefault(d.gorev_id, set()).add(d.bagli_oldugu_id)
    return kenarlar


def bekleyen_bagimliliklar(gorev_id: int, kenarlar: Dict[int, Set[int]], durumlar: Dict[int, str]) -> List[int]:
    """Bitmemiş (durumu "tamam" olmayan) bağımlılıklar. Silinmiş görev sayılmıyor."""
    return sorted(b for b in kenarlar.get(gorev_id, set()) if b in durumlar and durumlar[b] != "tamam")


async def yonetici_listesi(db: AsyncSession, proje_id: int) -> List[Dict[str, Any]]:
    gorevler = await proje_gorevleri(db, proje_id)
    idler = [g.id for g in gorevler]
    kontroller = await kontroller_sozlugu(db, idler)
    kenarlar = await bagimlilik_kenarlari(db, idler)
    durumlar = {g.id: g.durum for g in gorevler}
    return [
        gorev_sozlugu(g, kontroller.get(g.id, []), kenarlar.get(g.id, set()), bekleyen_bagimliliklar(g.id, kenarlar, durumlar))
        for g in gorevler
    ]


async def tek_gorev(db: AsyncSession, g: ProjectTasks) -> Dict[str, Any]:
    kontroller = await kontroller_sozlugu(db, [g.id])
    kenarlar = await bagimlilik_kenarlari(db, [g.id])
    durumlar: Dict[int, str] = {}
    hedefler = list(kenarlar.get(g.id, set()))
    if hedefler:
        for gid, d in (await db.execute(select(ProjectTasks.id, ProjectTasks.durum).where(ProjectTasks.id.in_(hedefler)))).all():
            durumlar[gid] = d
    return gorev_sozlugu(g, kontroller.get(g.id, []), kenarlar.get(g.id, set()), bekleyen_bagimliliklar(g.id, kenarlar, durumlar))


async def musteri_gorunumu(db: AsyncSession, proje: Projects) -> Dict[str, Any]:
    gorevler = [g for g in await proje_gorevleri(db, proje.id) if g.musteriye_gorunur]
    gorunur = {g.id for g in gorevler}
    kontroller = await kontroller_sozlugu(db, list(gorunur))
    liste = [musteri_gorev_sozlugu(g, kontroller.get(g.id, []), gorunur) for g in gorevler]
    toplam = len(liste)
    tamam = sum(1 for g in liste if g["durum"] == "tamam")
    kilometre = sorted(
        (g for g in liste if g["kilometre_tasi"]),
        key=lambda g: (g["bitis_tarihi"] or "9999-12-31", g["sira"], g["id"]),
    )
    return {
        "proje": {"id": proje.id, "baslik": proje.title},
        "gorevler": liste,
        "ilerleme": {"toplam": toplam, "tamam": tamam, "yuzde": round(tamam * 100 / toplam) if toplam else 0},
        "kilometre_taslari": kilometre,
    }


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


def bagimlilik_dongusu(kenarlar: Dict[int, Set[int]], gorev_id: int, bagli_id: int) -> bool:
    """`gorev → bagli` eklenirse döngü olur mu? (bagli'den gorev'e yol var mı)"""
    if gorev_id == bagli_id:
        return True
    gorulen: Set[int] = set()
    yigin = [bagli_id]
    while yigin:
        d = yigin.pop()
        if d == gorev_id:
            return True
        if d in gorulen:
            continue
        gorulen.add(d)
        yigin.extend(kenarlar.get(d, ()))
    return False


def ust_dongusu(ustler: Dict[int, Optional[int]], gorev_id: int, yeni_ust: Optional[int]) -> bool:
    d = yeni_ust
    adim = 0
    while d is not None and adim < 10000:
        if d == gorev_id:
            return True
        d = ustler.get(d)
        adim += 1
    return False


async def ust_denetle(db: AsyncSession, g: ProjectTasks, yeni_ust: Optional[int]) -> None:
    if yeni_ust is None:
        return
    ust = (await db.execute(select(ProjectTasks).where(ProjectTasks.id == yeni_ust))).scalar_one_or_none()
    if ust is None or ust.proje_id != g.proje_id:
        raise GorevHatasi(400, "ust_gorev_gecersiz")
    if g.id is None:
        return
    ustler = {
        gid: u for gid, u in (
            await db.execute(select(ProjectTasks.id, ProjectTasks.ust_gorev_id).where(ProjectTasks.proje_id == g.proje_id))
        ).all()
    }
    if ust_dongusu(ustler, g.id, yeni_ust):
        raise GorevHatasi(409, "ust_gorev_dongusu")


async def tamam_denetle(db: AsyncSession, g: ProjectTasks) -> None:
    kenarlar = await bagimlilik_kenarlari(db, [g.id])
    hedefler = list(kenarlar.get(g.id, set()))
    if not hedefler:
        return
    durumlar = {
        gid: d for gid, d in (await db.execute(select(ProjectTasks.id, ProjectTasks.durum).where(ProjectTasks.id.in_(hedefler)))).all()
    }
    bekleyen = bekleyen_bagimliliklar(g.id, kenarlar, durumlar)
    if bekleyen:
        raise GorevHatasi(409, "bagimlilik_bitmedi", gorevler=bekleyen)


def durum_ata(g: ProjectTasks, yeni: str) -> bool:
    """Durumu değiştirir; değiştiyse True. Tamamlanma anını tutar."""
    if yeni not in GOREV_DURUMLARI:
        raise GorevHatasi(400, "durum_gecersiz")
    if g.durum == yeni:
        return False
    g.durum = yeni
    g.tamamlandi_at = datetime.now(timezone.utc) if yeni == "tamam" else None
    return True


async def saat_toplamini_yenile(db: AsyncSession, gorev_id: int) -> float:
    toplam = (
        await db.execute(select(func.coalesce(func.sum(TaskTimeEntries.saat), 0.0)).where(TaskTimeEntries.gorev_id == gorev_id))
    ).scalar()
    g = (await db.execute(select(ProjectTasks).where(ProjectTasks.id == gorev_id))).scalar_one_or_none()
    toplam = round(float(toplam or 0), 2)
    if g is not None:
        g.harcanan_saat = toplam
    return toplam


# ---------------------------------------------------------------------------
# Revizyon sayacı
# ---------------------------------------------------------------------------

_SAAT_DESENI = re.compile(r"(\d+(?:[.,]\d+)?)")


def revizyon_saati_coz(metin: Any) -> Optional[float]:
    """"8s" / "16 saat" / "2h" → sayı; "Kullandıkça Öde" gibi sayısız → None."""
    if metin is None:
        return None
    if isinstance(metin, (int, float)) and not isinstance(metin, bool):
        return float(metin) if metin >= 0 else None
    m = _SAAT_DESENI.search(str(metin))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


async def musteri_projeleri(db: AsyncSession, eposta: str) -> List[Projects]:
    eposta = eposta_duzelt(eposta)
    if not eposta:
        return []
    return list(
        (await db.execute(select(Projects).where(func.lower(Projects.client_email) == eposta))).scalars().all()
    )


async def revizyon_hakki(db: AsyncSession, eposta: str, projeler: Optional[List[Projects]] = None) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """(hak_saat, kaynak, paket) — kaynak: paket | proje | None"""
    from services.moduller import musteri_paketi

    paket = await musteri_paketi(db, eposta)
    if paket:
        try:
            from models.pricing import Pricing_scales

            olcek = (await db.execute(select(Pricing_scales).where(Pricing_scales.kod == paket))).scalars().first()
        except Exception:  # noqa: BLE001
            olcek = None
        hak = revizyon_saati_coz(olcek.revizyon_saat) if olcek is not None else None
        if hak is not None:
            return hak, "paket", paket
    projeler = projeler if projeler is not None else await musteri_projeleri(db, eposta)
    elle = [float(p.aylik_revizyon_saati) for p in projeler if p.aylik_revizyon_saati is not None]
    if elle:
        return round(sum(elle), 2), "proje", paket
    return None, None, paket


async def revizyon_sayaci(db: AsyncSession, eposta: str, gun: Optional[date] = None) -> Dict[str, Any]:
    eposta = eposta_duzelt(eposta)
    gun = gun or bugun()
    bas, bit = ay_araligi(gun)
    projeler = await musteri_projeleri(db, eposta)
    proje_idler = [p.id for p in projeler]
    kullanilan = 0.0
    kredi = 0.0
    if eposta:
        satir = (
            await db.execute(
                select(
                    func.coalesce(func.sum(TaskTimeEntries.saat), 0.0),
                    func.coalesce(func.sum(TaskTimeEntries.kredi_saat), 0.0),
                )
                .where(TaskTimeEntries.musteri_eposta == eposta)
                .where(TaskTimeEntries.revizyon.is_(True))
                .where(TaskTimeEntries.tarih >= bas)
                .where(TaskTimeEntries.tarih < bit)
            )
        ).one()
        kullanilan, kredi = round(float(satir[0] or 0), 2), round(float(satir[1] or 0), 2)
    istek = 0
    if proje_idler:
        from models.project_events import Project_events

        for (an,) in (
            await db.execute(
                select(Project_events.created_at)
                .where(Project_events.project_id.in_(proje_idler))
                .where(Project_events.event_type == "revision_request")
            )
        ).all():
            yerel = _yerel_gun(an)
            if yerel is not None and bas <= yerel < bit:
                istek += 1
    hak, kaynak, paket = await revizyon_hakki(db, eposta, projeler)
    # Krediden düşülmüş saatler haktan yemiyor (ayrıca ödendi).
    haktan = round(max(kullanilan - kredi, 0.0), 2)
    kalan = round(hak - haktan, 2) if hak is not None else None
    asim = round(max(haktan - hak, 0.0), 2) if hak is not None else 0.0
    return {
        "ay": bas.strftime("%Y-%m"),
        "kullanilan": kullanilan,
        "krediden": kredi,
        "hak": hak,
        "kalan": kalan,
        "asim": asim,
        "asildi": bool(hak is not None and asim > 0),
        "kaynak": kaynak,
        "paket": paket,
        "istek_sayisi": istek,
    }


async def revizyon_asim_bildir(db: AsyncSession, eposta: str, sayac: Dict[str, Any]) -> bool:
    """Hak aşıldıysa yöneticiye ayda bir kez bildirir. Hata fırlatmaz."""
    if not sayac.get("asildi"):
        return False
    try:
        async with db.begin_nested():
            db.add(RevizyonUyarilari(musteri_eposta=eposta, ay=sayac["ay"]))
            await db.flush()
    except IntegrityError:
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Revizyon uyarısı kaydedilemedi")
        return False
    await db.commit()
    try:
        from services.kredi import bakiye
        from services.notify import admin_recipients, dispatch, render

        try:
            kredi = await bakiye(db, eposta)
        except Exception:  # noqa: BLE001
            kredi = None
        kredi_metni = f"{kredi:g}" if kredi is not None else "—"
        baslik, govde = await render(
            db,
            "revizyon_asildi",
            f"Revizyon hakkı aşıldı: {eposta} ({sayac['ay']}) / Revision allowance exceeded",
            (
                f"{eposta} bu ay {sayac['kullanilan']:g} saat revizyon kullandı; hak {sayac['hak']:g} saat, "
                f"aşım {sayac['asim']:g} saat. Kredi bakiyesi: {kredi_metni} saat — aşan kısım krediden düşülebilir.\n\n"
                f"{eposta} used {sayac['kullanilan']:g} revision hours this month; allowance {sayac['hak']:g} h, "
                f"over by {sayac['asim']:g} h. Credit balance: {kredi_metni} h — the excess can be charged to credits."
            ),
            {"musteri": eposta, "ay": sayac["ay"], "kullanilan": sayac["kullanilan"], "hak": sayac["hak"], "asim": sayac["asim"]},
        )
        await dispatch(
            db,
            event_type="revizyon_asildi",
            title=baslik,
            body=govde,
            recipients=await admin_recipients(db),
            link="/admin",
            ref_type="revizyon",
            ref_id=None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Revizyon aşım bildirimi gönderilemedi")
    return True


# ---------------------------------------------------------------------------
# Bildirim
# ---------------------------------------------------------------------------


async def gorev_bildir(db: AsyncSession, proje: Projects, g: ProjectTasks) -> None:
    """Müşteriye görünen görev incelemeye ya da tamama geçti. Hata fırlatmaz."""
    if not g.musteriye_gorunur or g.durum not in BILDIRIMLI_DURUMLAR or not proje.client_email:
        return
    try:
        from services.notify import dispatch, render

        tr, en = DURUM_ADLARI[g.durum]
        baslik, govde = await render(
            db,
            "gorev_guncellendi",
            f"{proje.title}: {g.baslik} — {tr} / {en}",
            f"“{g.baslik}” görevi {tr.lower()} durumuna geçti.\n\nThe task “{g.baslik}” is now {en.lower()}.",
            {"proje": proje.title, "gorev": g.baslik, "durum": tr},
        )
        await dispatch(
            db,
            event_type="gorev_guncellendi",
            title=baslik,
            body=govde,
            recipients=[{"email": eposta_duzelt(proje.client_email), "role": "client"}],
            link="/client?sekme=projects",
            ref_type="project_task",
            ref_id=g.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Görev bildirimi gönderilemedi")


async def geri_bildirimi_esle(db: AsyncSession, g: ProjectTasks) -> None:
    """Geri bildirimden doğan görev tamamlanınca bildirim "çözüldü" olur."""
    if not g.geri_bildirim_id or g.durum != "tamam":
        return
    try:
        from services.geri_bildirim import durum_degistir

        await durum_degistir(db, g.geri_bildirim_id, "cozuldu")
    except Exception:  # noqa: BLE001
        logger.exception("Geri bildirim durumu eşlenemedi")


# ---------------------------------------------------------------------------
# 1E revizyon isteği → görev
# ---------------------------------------------------------------------------


async def revizyon_gorevi_ac(
    db: AsyncSession, *, proje_id: int, baslik: str, aciklama: Optional[str], imzali_islem_id: Optional[int]
) -> Optional[ProjectTasks]:
    """İmzalı teslim bağlantısından gelen revizyon isteği için "revizyon" etiketli,
    müşteriye görünür bir görev açar (flush eder, commit etmez)."""
    sira = (
        await db.execute(
            select(func.coalesce(func.max(ProjectTasks.sira), -1)).where(ProjectTasks.proje_id == proje_id).where(ProjectTasks.durum == "yapilacak")
        )
    ).scalar()
    g = ProjectTasks(
        proje_id=proje_id,
        baslik=baslik[:200],
        aciklama=(aciklama or "")[:4000] or None,
        durum="yapilacak",
        oncelik="yuksek",
        sira=int(sira or -1) + 1,
        musteriye_gorunur=True,
        kilometre_tasi=False,
        harcanan_saat=0.0,
        etiketler=json.dumps([REVIZYON_ETIKETI]),
        imzali_islem_id=imzali_islem_id,
        olusturan_eposta=None,
    )
    db.add(g)
    await db.flush()
    return g
