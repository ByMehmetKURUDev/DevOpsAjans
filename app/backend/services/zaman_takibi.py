"""Faz 3Z — zaman takibi: sayaç, elle kayıt, çizelge onayı, iş yükü, faturaya aktarım.

Kim ne yapabilir
----------------
* Yönetici (`role=admin`): her kaydı görür, düzenler, onaylar/reddeder,
  faturaya aktarır, CSV alır; başkası adına kayıt girebilir.
* Personel (`staff` tablosunda AKTİF satırı olan, yönetici olmayan kullanıcı):
  yalnız KENDİ kayıtlarını görür/girer/düzenler/siler ve kendi sayacını
  yönetir. Onay, faturalama, iş yükü ve ayarlar kapalı.
* Müşteri: yalnız kendi projesinin ONAYLI süre özetini, proje ayarı
  (`sure_musteriye_gorunur`) açıksa görür.

Sayaç
-----
Başlangıç anı veritabanında: sayfa kapansa da süre işler. Kişi başına tek
açık sayaç (kısmi benzersiz indeks); yeni sayaç başlatılınca açık olan
durdurulur. 12 saati aşmış (unutulmuş) sayaç kendiliğinden durdurulmaz:
durdurma/başlatma 409 `uzun_sayac` döner, kişi süreyi düzeltip
(`sure_dk`) durdurur. Zamanlanmış görev yok — her şey istekle.

Kilit
-----
`onaylandi` ve `faturalandi` kayıt düzenlenemez/silinemez. Onayı geri almak
(yönetici) kaydı `taslak`a döndürür. Faturalanmış kaydın kilidi yalnız
faturası iptal edilince ya da silinince açılır (bu dosyanın sonundaki flush
kancası — fatura hangi yoldan değişirse değişsin).

Revizyon sayacı (Faz 2B) ile bağ
--------------------------------
Görevli kayıt onaylanınca `task_time_entries` tablosuna ayna satır yazılır
(revizyon = tür revizyon). Böylece görevin harcanan saati ve aylık revizyon
sayacı/aşım bildirimi/krediden düşme olduğu gibi çalışır. Görevsiz revizyon
kaydı sayaca `gorevsiz_revizyon_saati` ile eklenir.
"""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.invoices import Invoices
from models.proje_gorevleri import ProjectTasks, TaskTimeEntries
from models.projects import Projects
from models.staff import Staff
from models.zaman_takibi import (
    DURUMLAR,
    KILITLI_DURUMLAR,
    TURLER,
    ZamanFaturaBaglari,
    ZamanKayitlari,
)
from services.gorevler import GorevHatasi as ZamanHatasi
from services.gorevler import eposta_duzelt
from sqlalchemy import delete, event, func, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: 12 saati aşan açık sayaç "unutulmuş" sayılır.
UZUN_SAYAC_DK = 12 * 60
#: Tek kaydın en uzun süresi.
EN_COK_SURE_DK = 24 * 60
ACIKLAMA_SINIRI = 1000
RET_NOTU_SINIRI = 1000
TOPLU_SINIR = 500
LISTE_SINIRI = 1000
GRUPLAMALAR = ("tek", "kisi", "gorev")
VARSAYILAN_KDV = 20
#: Site ayarları (gizli: herkese açık ayar listesinde görünmez).
AYAR_UCRET = "zaman_saatlik_ucret"
AYAR_PARA_BIRIMI = "zaman_para_birimi"
#: Müşteriye görünen (onaylı) durumlar.
ONAYLI_DURUMLAR = ("onaylandi", "faturalandi")


# ---------------------------------------------------------------------------
# Zaman yardımcıları — saklanan her an UTC; "gün" Türkiye saatine göre
# ---------------------------------------------------------------------------
def _tr():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Istanbul")
    except Exception:  # noqa: BLE001
        return timezone(timedelta(hours=3))


TR = _tr()


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini düşürüyor: saatsiz an UTC sayılır."""
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def yerel_gun(an: Optional[datetime]) -> Optional[date]:
    a = utc(an)
    return a.astimezone(TR).date() if a else None


def bugun() -> date:
    return yerel_gun(simdi())  # type: ignore[return-value]


def yerel_gece(gun: date) -> datetime:
    """Türkiye saatiyle `gun` 00:00 → UTC an."""
    return datetime.combine(gun, time(0, 0), tzinfo=TR).astimezone(timezone.utc)


def hafta_basi(gun: date) -> date:
    return gun - timedelta(days=gun.weekday())


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def dakika(bas: datetime, bit: datetime) -> int:
    """İki an arası dakika (yuvarlanmış, en az 1)."""
    saniye = (utc(bit) - utc(bas)).total_seconds()  # type: ignore[operator]
    return max(1, int(round(saniye / 60.0)))


def tarih_coz(deger: Any, kod: str = "tarih_gecersiz") -> Optional[date]:
    if deger in (None, ""):
        return None
    if isinstance(deger, date) and not isinstance(deger, datetime):
        return deger
    try:
        gun = datetime.strptime(str(deger).strip()[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ZamanHatasi(400, kod) from exc
    if not 2000 <= gun.year <= 2100:
        raise ZamanHatasi(400, kod)
    return gun


def an_coz(deger: Any, kod: str = "baslangic_gecersiz") -> Optional[datetime]:
    """ISO tarih-saat → UTC. Saat dilimsiz değer Türkiye saati sayılır."""
    if deger in (None, ""):
        return None
    if isinstance(deger, datetime):
        an = deger
    else:
        metin = str(deger).strip().replace("Z", "+00:00")
        try:
            an = datetime.fromisoformat(metin)
        except ValueError as exc:
            raise ZamanHatasi(400, kod) from exc
    if an.tzinfo is None:
        an = an.replace(tzinfo=TR)
    an = an.astimezone(timezone.utc)
    if not 2000 <= an.year <= 2100:
        raise ZamanHatasi(400, kod)
    return an


def saat_coz(deger: Any) -> time:
    """"HH:MM" → time (Türkiye saati). Boş → 09:00."""
    if deger in (None, ""):
        return time(9, 0)
    try:
        s, d = str(deger).strip()[:5].split(":")
        return time(int(s), int(d))
    except (ValueError, TypeError) as exc:
        raise ZamanHatasi(400, "saat_gecersiz") from exc


def sure_dogrula(deger: Any, *, ust: int = EN_COK_SURE_DK) -> int:
    try:
        dk = int(deger)
    except (TypeError, ValueError) as exc:
        raise ZamanHatasi(400, "sure_gecersiz") from exc
    if isinstance(deger, bool) or dk < 1 or dk > ust:
        raise ZamanHatasi(400, "sure_gecersiz", en_cok=ust)
    return dk


def _metin(deger: Any, sinir: int) -> Optional[str]:
    temiz = str(deger or "").strip()
    return temiz[:sinir] or None


def _ondalik(deger: Any) -> Optional[Decimal]:
    if deger is None or deger == "":
        return None
    try:
        d = Decimal(str(deger).strip().replace(",", "."))
    except Exception as exc:  # noqa: BLE001
        raise ZamanHatasi(400, "ucret_gecersiz") from exc
    if not d.is_finite() or d < 0 or d > Decimal("1000000"):
        raise ZamanHatasi(400, "ucret_gecersiz")
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _para_birimi(deger: Any, varsayilan: str = "TRY") -> str:
    from services.belge_hesap import HesapHatasi, para_birimi_duzelt

    try:
        return para_birimi_duzelt(deger or None, varsayilan)
    except HesapHatasi as exc:
        raise ZamanHatasi(400, "para_birimi_gecersiz") from exc


# ---------------------------------------------------------------------------
# Kişi bağlamı
# ---------------------------------------------------------------------------
@dataclass
class Kisi:
    eposta: str
    yonetici: bool
    personel: bool
    ad: Optional[str] = None


async def personel_mi(db: AsyncSession, eposta: str) -> Optional[Staff]:
    eposta = eposta_duzelt(eposta)
    if not eposta:
        return None
    return (
        await db.execute(
            select(Staff).where(func.lower(Staff.email) == eposta).where(Staff.aktif.isnot(False)).limit(1)
        )
    ).scalars().first()


async def ekip_adlari(db: AsyncSession) -> Dict[str, str]:
    return {
        eposta_duzelt(s.email): s.ad
        for s in (await db.execute(select(Staff))).scalars().all()
        if s.email
    }


def kisi_kosulu(kisi: Kisi):
    """Personel yalnız kendi kayıtları; yönetici hepsi (None)."""
    return None if kisi.yonetici else (ZamanKayitlari.kisi_eposta == kisi.eposta)


# ---------------------------------------------------------------------------
# Ücret
# ---------------------------------------------------------------------------
async def _ayar_oku(db: AsyncSession, anahtar: str) -> Optional[str]:
    from models.site_settings import Site_settings

    try:
        satir = (
            await db.execute(select(Site_settings.setting_value).where(Site_settings.setting_key == anahtar))
        ).first()
    except Exception:  # noqa: BLE001
        return None
    return (str(satir[0]).strip() or None) if satir and satir[0] is not None else None


async def _ayar_yaz(db: AsyncSession, anahtar: str, deger: str, etiket: str) -> None:
    from models.site_settings import Site_settings

    satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == anahtar))).scalars().first()
    if satir is None:
        db.add(Site_settings(setting_key=anahtar, setting_value=deger, group_name="zaman", label=etiket))
    else:
        satir.setting_value = deger


async def varsayilan_ucret(db: AsyncSession) -> Tuple[Optional[Decimal], str]:
    try:
        ucret = _ondalik(await _ayar_oku(db, AYAR_UCRET))
    except ZamanHatasi:
        ucret = None
    try:
        pb = _para_birimi(await _ayar_oku(db, AYAR_PARA_BIRIMI))
    except ZamanHatasi:
        pb = "TRY"
    return ucret, pb


async def ayarlar(db: AsyncSession) -> Dict[str, Any]:
    ucret, pb = await varsayilan_ucret(db)
    return {"saatlik_ucret": float(ucret) if ucret is not None else None, "para_birimi": pb}


async def ayarlari_yaz(db: AsyncSession, govde: Dict[str, Any]) -> Dict[str, Any]:
    if "saatlik_ucret" in govde:
        ucret = _ondalik(govde.get("saatlik_ucret"))
        await _ayar_yaz(db, AYAR_UCRET, f"{ucret:f}" if ucret is not None else "", "Zaman: varsayılan saatlik ücret")
    if "para_birimi" in govde:
        await _ayar_yaz(db, AYAR_PARA_BIRIMI, _para_birimi(govde.get("para_birimi")), "Zaman: para birimi")
    await db.commit()
    return await ayarlar(db)


async def proje_ucreti(db: AsyncSession, proje: Projects) -> Tuple[Optional[Decimal], str, str]:
    """(ücret, para birimi, kaynak) — kaynak: proje | site | yok."""
    vars_ucret, vars_pb = await varsayilan_ucret(db)
    if proje.saatlik_ucret is not None:
        try:
            pb = _para_birimi(proje.ucret_para_birimi, vars_pb)
        except ZamanHatasi:
            pb = vars_pb
        return _ondalik(proje.saatlik_ucret), pb, "proje"
    if vars_ucret is not None:
        return vars_ucret, vars_pb, "site"
    return None, vars_pb, "yok"


def proje_ayar_sozlugu(proje: Projects) -> Dict[str, Any]:
    return {
        "proje_id": proje.id,
        "saatlik_ucret": proje.saatlik_ucret,
        "ucret_para_birimi": proje.ucret_para_birimi,
        "sure_musteriye_gorunur": bool(proje.sure_musteriye_gorunur),
        "faturalanabilir_musteriye_gorunur": bool(proje.faturalanabilir_musteriye_gorunur),
    }


async def proje_ayari_yaz(db: AsyncSession, proje: Projects, govde: Dict[str, Any]) -> Dict[str, Any]:
    if "saatlik_ucret" in govde:
        ucret = _ondalik(govde.get("saatlik_ucret"))
        proje.saatlik_ucret = float(ucret) if ucret is not None else None
    if "ucret_para_birimi" in govde:
        ham = govde.get("ucret_para_birimi")
        proje.ucret_para_birimi = _para_birimi(ham) if ham else None
    for alan in ("sure_musteriye_gorunur", "faturalanabilir_musteriye_gorunur"):
        if alan in govde and govde.get(alan) is not None:
            setattr(proje, alan, bool(govde.get(alan)))
    await db.commit()
    await db.refresh(proje)
    return await proje_ayari(db, proje)


async def proje_ayari(db: AsyncSession, proje: Projects) -> Dict[str, Any]:
    ucret, pb, kaynak = await proje_ucreti(db, proje)
    return {
        **proje_ayar_sozlugu(proje),
        "etkin_ucret": float(ucret) if ucret is not None else None,
        "etkin_para_birimi": pb,
        "ucret_kaynagi": kaynak,
    }


# ---------------------------------------------------------------------------
# Okuma ve sözlük
# ---------------------------------------------------------------------------
async def proje_bul(db: AsyncSession, proje_id: Any) -> Projects:
    try:
        pid = int(proje_id)
    except (TypeError, ValueError) as exc:
        raise ZamanHatasi(400, "proje_gerekli") from exc
    p = (await db.execute(select(Projects).where(Projects.id == pid))).scalar_one_or_none()
    if p is None:
        raise ZamanHatasi(404, "proje_yok")
    return p


async def gorev_dogrula(db: AsyncSession, proje: Projects, gorev_id: Any) -> Optional[ProjectTasks]:
    if gorev_id in (None, "", 0):
        return None
    try:
        gid = int(gorev_id)
    except (TypeError, ValueError) as exc:
        raise ZamanHatasi(400, "gorev_gecersiz") from exc
    g = (await db.execute(select(ProjectTasks).where(ProjectTasks.id == gid))).scalar_one_or_none()
    if g is None or g.proje_id != proje.id:
        raise ZamanHatasi(400, "gorev_gecersiz")
    return g


async def kayit_bul(db: AsyncSession, kayit_id: int, kisi: Kisi) -> ZamanKayitlari:
    k = (await db.execute(select(ZamanKayitlari).where(ZamanKayitlari.id == kayit_id))).scalar_one_or_none()
    # Personel başkasının kaydını "yok" görür (var olduğu da sızmasın).
    if k is None or (not kisi.yonetici and k.kisi_eposta != kisi.eposta):
        raise ZamanHatasi(404, "kayit_yok")
    return k


def tutar(k: ZamanKayitlari) -> Optional[float]:
    if k.saatlik_ucret is None or not k.sure_dk:
        return None
    d = Decimal(str(k.saatlik_ucret)) * Decimal(k.sure_dk) / Decimal(60)
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def kayit_sozlugu(
    k: ZamanKayitlari,
    *,
    projeler: Optional[Dict[int, str]] = None,
    gorevler: Optional[Dict[int, str]] = None,
    adlar: Optional[Dict[str, str]] = None,
    an: Optional[datetime] = None,
) -> Dict[str, Any]:
    calisiyor = k.bitis is None
    an = an or simdi()
    return {
        "id": k.id,
        "proje_id": k.proje_id,
        "proje_baslik": (projeler or {}).get(k.proje_id),
        "gorev_id": k.gorev_id,
        "gorev_baslik": (gorevler or {}).get(k.gorev_id) if k.gorev_id else None,
        "kisi_eposta": k.kisi_eposta,
        "kisi_ad": (adlar or {}).get(k.kisi_eposta),
        "baslangic": iso(k.baslangic),
        "bitis": iso(k.bitis),
        "gun": yerel_gun(k.baslangic).isoformat() if k.baslangic else None,
        "sure_dk": k.sure_dk,
        "calisiyor": calisiyor,
        "gecen_dk": dakika(k.baslangic, an) if calisiyor else None,
        "uzun": bool(calisiyor and dakika(k.baslangic, an) > UZUN_SAYAC_DK),
        "aciklama": k.aciklama,
        "faturalanabilir": bool(k.faturalanabilir),
        "saatlik_ucret": float(k.saatlik_ucret) if k.saatlik_ucret is not None else None,
        "para_birimi": k.para_birimi,
        "tutar": tutar(k),
        "tur": k.tur or "normal",
        "durum": k.durum,
        "kilitli": k.durum in KILITLI_DURUMLAR,
        "ret_notu": k.ret_notu,
        "onaylayan_eposta": k.onaylayan_eposta,
        "onay_at": iso(k.onay_at),
        "fatura_id": k.fatura_id,
        "created_at": iso(k.created_at),
    }


async def _adlar(db: AsyncSession, kayitlar: Sequence[ZamanKayitlari]) -> Tuple[Dict[int, str], Dict[int, str], Dict[str, str]]:
    pidler = {k.proje_id for k in kayitlar}
    gidler = {k.gorev_id for k in kayitlar if k.gorev_id}
    projeler: Dict[int, str] = {}
    gorevler: Dict[int, str] = {}
    if pidler:
        projeler = {i: t for i, t in (await db.execute(select(Projects.id, Projects.title).where(Projects.id.in_(pidler)))).all()}
    if gidler:
        gorevler = {i: b for i, b in (await db.execute(select(ProjectTasks.id, ProjectTasks.baslik).where(ProjectTasks.id.in_(gidler)))).all()}
    return projeler, gorevler, await ekip_adlari(db)


async def sozlukler(db: AsyncSession, kayitlar: Sequence[ZamanKayitlari]) -> List[Dict[str, Any]]:
    projeler, gorevler, adlar = await _adlar(db, kayitlar)
    an = simdi()
    return [kayit_sozlugu(k, projeler=projeler, gorevler=gorevler, adlar=adlar, an=an) for k in kayitlar]


async def tek_sozluk(db: AsyncSession, k: ZamanKayitlari) -> Dict[str, Any]:
    return (await sozlukler(db, [k]))[0]


async def kayitlari_listele(
    db: AsyncSession,
    kisi: Kisi,
    *,
    durum: Optional[str] = None,
    proje_id: Optional[int] = None,
    kisi_eposta: Optional[str] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    faturalanabilir: Optional[bool] = None,
    faturalanmamis: bool = False,
    sinir: int = 200,
) -> List[ZamanKayitlari]:
    sorgu = select(ZamanKayitlari)
    kosul = kisi_kosulu(kisi)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    elif kisi_eposta:
        sorgu = sorgu.where(ZamanKayitlari.kisi_eposta == eposta_duzelt(kisi_eposta))
    if durum:
        durumlar = [d for d in str(durum).split(",") if d]
        for d in durumlar:
            if d not in DURUMLAR:
                raise ZamanHatasi(400, "durum_gecersiz")
        sorgu = sorgu.where(ZamanKayitlari.durum.in_(durumlar))
    if proje_id:
        sorgu = sorgu.where(ZamanKayitlari.proje_id == int(proje_id))
    bas = tarih_coz(baslangic)
    bit = tarih_coz(bitis)
    if bas:
        sorgu = sorgu.where(ZamanKayitlari.baslangic >= yerel_gece(bas))
    if bit:
        sorgu = sorgu.where(ZamanKayitlari.baslangic < yerel_gece(bit + timedelta(days=1)))
    if faturalanabilir is not None:
        sorgu = sorgu.where(ZamanKayitlari.faturalanabilir.is_(bool(faturalanabilir)))
    if faturalanmamis:
        sorgu = sorgu.where(ZamanKayitlari.fatura_id.is_(None))
    sinir = max(1, min(int(sinir or 200), LISTE_SINIRI))
    sorgu = sorgu.order_by(ZamanKayitlari.baslangic.desc(), ZamanKayitlari.id.desc()).limit(sinir)
    return list((await db.execute(sorgu)).scalars().all())


# ---------------------------------------------------------------------------
# Seçenekler (form listeleri)
# ---------------------------------------------------------------------------
async def secenekler(db: AsyncSession, kisi: Kisi) -> Dict[str, Any]:
    """Kayıt formu için projeler ve görevler. Vaka çalışmaları (müşterisiz) dışarıda."""
    projeler = (
        await db.execute(
            select(Projects.id, Projects.title, Projects.client_email, Projects.status)
            .where(Projects.client_email.isnot(None))
            .where(Projects.client_email != "")
            .order_by(Projects.id.desc())
            .limit(500)
        )
    ).all()
    pidler = [p[0] for p in projeler]
    gorevler: List[Dict[str, Any]] = []
    if pidler:
        sorgu = (
            select(ProjectTasks.id, ProjectTasks.proje_id, ProjectTasks.baslik, ProjectTasks.etiketler, ProjectTasks.atanan)
            .where(ProjectTasks.proje_id.in_(pidler))
            .where(ProjectTasks.durum != "tamam")
            .order_by(ProjectTasks.proje_id, ProjectTasks.sira, ProjectTasks.id)
            .limit(3000)
        )
        if not kisi.yonetici:
            sorgu = sorgu.where(ProjectTasks.atanan == kisi.eposta)
        from services.gorevler import REVIZYON_ETIKETI, etiketleri_coz

        for gid, pid, baslik, etiketler, atanan in (await db.execute(sorgu)).all():
            gorevler.append({
                "id": gid, "proje_id": pid, "baslik": baslik, "atanan": atanan,
                "revizyon": REVIZYON_ETIKETI in etiketleri_coz(etiketler),
            })
    sonuc: Dict[str, Any] = {
        "projeler": [
            {"id": p[0], "baslik": p[1], **({"client_email": p[2], "durum": p[3]} if kisi.yonetici else {})}
            for p in projeler
        ],
        "gorevler": gorevler,
        "uzun_sayac_dk": UZUN_SAYAC_DK,
        "en_cok_sure_dk": EN_COK_SURE_DK,
    }
    if kisi.yonetici:
        sonuc["ekip"] = [
            {"ad": s.ad, "email": eposta_duzelt(s.email)}
            for s in (await db.execute(select(Staff).where(Staff.aktif.isnot(False)).order_by(Staff.ad))).scalars().all()
        ]
        sonuc["ayarlar"] = await ayarlar(db)
    return sonuc


# ---------------------------------------------------------------------------
# Sayaç
# ---------------------------------------------------------------------------
async def acik_sayac(db: AsyncSession, eposta: str) -> Optional[ZamanKayitlari]:
    return (
        await db.execute(
            select(ZamanKayitlari).where(ZamanKayitlari.kisi_eposta == eposta).where(ZamanKayitlari.bitis.is_(None)).limit(1)
        )
    ).scalars().first()


def _sayaci_kapat(k: ZamanKayitlari, bitis: datetime, sure_dk: Optional[int] = None) -> None:
    bas = utc(k.baslangic)
    if sure_dk is not None:
        k.sure_dk = sure_dk
        k.bitis = bas + timedelta(minutes=sure_dk)  # type: ignore[operator]
    else:
        k.bitis = bitis
        k.sure_dk = dakika(bas, bitis)  # type: ignore[arg-type]


def _tur_sec(ham: Any, gorev: Optional[ProjectTasks]) -> str:
    if ham in (None, ""):
        from services.gorevler import revizyon_mu

        return "revizyon" if gorev is not None and revizyon_mu(gorev) else "normal"
    if ham not in TURLER:
        raise ZamanHatasi(400, "tur_gecersiz")
    return str(ham)


async def _ucreti_sabitle(db: AsyncSession, k: ZamanKayitlari, proje: Projects) -> None:
    ucret, pb, _ = await proje_ucreti(db, proje)
    k.saatlik_ucret = ucret
    k.para_birimi = pb


async def _kisi_sec(db: AsyncSession, kisi: Kisi, ham: Any) -> str:
    """Kaydın sahibi. Personel her zaman kendisi; yönetici ekipten birini seçebilir."""
    hedef = eposta_duzelt(ham)
    if not hedef or hedef == kisi.eposta:
        return kisi.eposta
    if not kisi.yonetici:
        raise ZamanHatasi(403, "baskasi_adina")
    if await personel_mi(db, hedef) is None:
        raise ZamanHatasi(400, "kisi_gecersiz")
    return hedef


async def sayac_durumu(db: AsyncSession, kisi: Kisi) -> Dict[str, Any]:
    k = await acik_sayac(db, kisi.eposta)
    return {"sayac": await tek_sozluk(db, k) if k else None, "uzun_sayac_dk": UZUN_SAYAC_DK}


async def sayac_baslat(db: AsyncSession, kisi: Kisi, govde: Dict[str, Any]) -> Dict[str, Any]:
    proje = await proje_bul(db, govde.get("proje_id"))
    gorev = await gorev_dogrula(db, proje, govde.get("gorev_id"))
    an = simdi()
    durdurulan = None
    acik = await acik_sayac(db, kisi.eposta)
    if acik is not None:
        gecen = dakika(acik.baslangic, an)
        if gecen > UZUN_SAYAC_DK:
            # Unutulmuş sayaç sessizce 13+ saat yazmasın: önce kişi düzeltsin.
            raise ZamanHatasi(409, "uzun_sayac", kayit=await tek_sozluk(db, acik), gecen_dk=gecen)
        _sayaci_kapat(acik, an)
        durdurulan = acik
        await db.flush()
    yeni = ZamanKayitlari(
        proje_id=proje.id,
        gorev_id=gorev.id if gorev else None,
        kisi_eposta=kisi.eposta,
        baslangic=an,
        bitis=None,
        sure_dk=None,
        aciklama=_metin(govde.get("aciklama"), ACIKLAMA_SINIRI),
        faturalanabilir=bool(govde.get("faturalanabilir", True)),
        tur=_tur_sec(govde.get("tur"), gorev),
        durum="taslak",
        olusturan_eposta=kisi.eposta,
    )
    await _ucreti_sabitle(db, yeni, proje)
    db.add(yeni)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Aynı anda iki başlatma: kısmi benzersiz indeks ikinciyi durdurdu.
        await db.rollback()
        raise ZamanHatasi(409, "sayac_cakisti") from exc
    await db.commit()
    await db.refresh(yeni)
    sonuc = {"sayac": await tek_sozluk(db, yeni), "durdurulan": None}
    if durdurulan is not None:
        await db.refresh(durdurulan)
        sonuc["durdurulan"] = await tek_sozluk(db, durdurulan)
    return sonuc


async def sayac_durdur(db: AsyncSession, kisi: Kisi, govde: Dict[str, Any]) -> Dict[str, Any]:
    k = await acik_sayac(db, kisi.eposta)
    if k is None:
        raise ZamanHatasi(404, "sayac_yok")
    an = simdi()
    gecen = dakika(k.baslangic, an)
    sure = govde.get("sure_dk")
    if sure in (None, ""):
        if gecen > UZUN_SAYAC_DK:
            raise ZamanHatasi(409, "uzun_sayac", kayit=await tek_sozluk(db, k), gecen_dk=gecen)
        _sayaci_kapat(k, an)
    else:
        dk = sure_dogrula(sure, ust=min(EN_COK_SURE_DK, gecen + 1))
        _sayaci_kapat(k, an, dk)
    if "aciklama" in govde:
        k.aciklama = _metin(govde.get("aciklama"), ACIKLAMA_SINIRI)
    await db.commit()
    await db.refresh(k)
    return {"kayit": await tek_sozluk(db, k)}


# ---------------------------------------------------------------------------
# Elle kayıt
# ---------------------------------------------------------------------------
def _baslangic_ve_sure(govde: Dict[str, Any], mevcut: Optional[ZamanKayitlari] = None) -> Tuple[datetime, int]:
    """Gövdeden (baslangic | tarih+saat) ve (sure_dk | bitis) → (UTC başlangıç, dakika)."""
    bas = an_coz(govde.get("baslangic")) if govde.get("baslangic") else None
    if bas is None and govde.get("tarih"):
        gun = tarih_coz(govde.get("tarih"))
        bas = datetime.combine(gun, saat_coz(govde.get("saat")), tzinfo=TR).astimezone(timezone.utc)  # type: ignore[arg-type]
    if bas is None and mevcut is not None:
        bas = utc(mevcut.baslangic)
    if bas is None:
        raise ZamanHatasi(400, "baslangic_gerekli")
    if govde.get("sure_dk") not in (None, ""):
        dk = sure_dogrula(govde.get("sure_dk"))
    elif govde.get("bitis"):
        bit = an_coz(govde.get("bitis"), "bitis_gecersiz")
        if bit is None or bit <= bas:
            raise ZamanHatasi(400, "bitis_gecersiz")
        dk = sure_dogrula(dakika(bas, bit))
    elif mevcut is not None and mevcut.sure_dk:
        dk = int(mevcut.sure_dk)
    else:
        raise ZamanHatasi(400, "sure_gerekli")
    if bas > simdi() + timedelta(days=1):
        raise ZamanHatasi(400, "gelecek_tarih")
    return bas, dk


async def kayit_olustur(db: AsyncSession, kisi: Kisi, govde: Dict[str, Any]) -> Dict[str, Any]:
    proje = await proje_bul(db, govde.get("proje_id"))
    gorev = await gorev_dogrula(db, proje, govde.get("gorev_id"))
    sahip = await _kisi_sec(db, kisi, govde.get("kisi_eposta"))
    bas, dk = _baslangic_ve_sure(govde)
    k = ZamanKayitlari(
        proje_id=proje.id,
        gorev_id=gorev.id if gorev else None,
        kisi_eposta=sahip,
        baslangic=bas,
        bitis=bas + timedelta(minutes=dk),
        sure_dk=dk,
        aciklama=_metin(govde.get("aciklama"), ACIKLAMA_SINIRI),
        faturalanabilir=bool(govde.get("faturalanabilir", True)),
        tur=_tur_sec(govde.get("tur"), gorev),
        durum="taslak",
        olusturan_eposta=kisi.eposta,
    )
    await _ucreti_sabitle(db, k, proje)
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return await tek_sozluk(db, k)


def _kilit_denetle(k: ZamanKayitlari) -> None:
    if k.durum in KILITLI_DURUMLAR:
        raise ZamanHatasi(409, "kayit_kilitli", kayit_durumu=k.durum)


async def kayit_guncelle(db: AsyncSession, kisi: Kisi, kayit_id: int, govde: Dict[str, Any]) -> Dict[str, Any]:
    k = await kayit_bul(db, kayit_id, kisi)
    _kilit_denetle(k)
    proje_degisti = False
    if "proje_id" in govde and govde.get("proje_id") not in (None, "") and int(govde["proje_id"]) != k.proje_id:
        proje = await proje_bul(db, govde.get("proje_id"))
        k.proje_id = proje.id
        k.gorev_id = None
        proje_degisti = True
    else:
        proje = await proje_bul(db, k.proje_id)
    if "gorev_id" in govde:
        gorev = await gorev_dogrula(db, proje, govde.get("gorev_id"))
        k.gorev_id = gorev.id if gorev else None
    if "aciklama" in govde:
        k.aciklama = _metin(govde.get("aciklama"), ACIKLAMA_SINIRI)
    if "faturalanabilir" in govde and govde.get("faturalanabilir") is not None:
        k.faturalanabilir = bool(govde.get("faturalanabilir"))
    if "tur" in govde and govde.get("tur") not in (None, ""):
        k.tur = _tur_sec(govde.get("tur"), None)
    zaman_alanlari = {"baslangic", "tarih", "saat", "sure_dk", "bitis"} & set(govde)
    if zaman_alanlari:
        if k.bitis is None:
            # Çalışan sayacın süresi durdurulurken belirlenir.
            raise ZamanHatasi(409, "sayac_calisiyor")
        bas, dk = _baslangic_ve_sure(govde, k)
        k.baslangic = bas
        k.sure_dk = dk
        k.bitis = bas + timedelta(minutes=dk)
    if proje_degisti:
        await _ucreti_sabitle(db, k, proje)
    if k.durum == "reddedildi":
        # Düzeltilen kayıt yeniden onaya düşer.
        k.durum = "taslak"
        k.ret_notu = None
    await db.commit()
    await db.refresh(k)
    return await tek_sozluk(db, k)


async def kayit_sil(db: AsyncSession, kisi: Kisi, kayit_id: int) -> Dict[str, Any]:
    """Çöp kutusuna düşer (services/cop_kutusu.py — `zaman_kayitlari` izinli tablo)."""
    k = await kayit_bul(db, kayit_id, kisi)
    _kilit_denetle(k)
    await db.delete(k)
    await db.commit()
    return {"silindi": kayit_id}


# ---------------------------------------------------------------------------
# Onay / ret / geri alma (yönetici) + Faz 2B ayna saat girişi
# ---------------------------------------------------------------------------
async def _aynala(db: AsyncSession, k: ZamanKayitlari) -> Optional[str]:
    """Görevli kaydı `task_time_entries`'e yazar (flush). → müşteri e-postası (revizyonsa)."""
    from services.gorevler import saat_toplamini_yenile

    if not k.gorev_id or k.gorev_saat_id or not k.sure_dk:
        return None
    proje = (await db.execute(select(Projects).where(Projects.id == k.proje_id))).scalar_one_or_none()
    musteri = eposta_duzelt(proje.client_email) if proje is not None else ""
    giris = TaskTimeEntries(
        gorev_id=k.gorev_id,
        proje_id=k.proje_id,
        musteri_eposta=musteri or None,
        saat=round(k.sure_dk / 60.0, 2),
        tarih=yerel_gun(k.baslangic),
        aciklama=(f"⏱ {k.aciklama}" if k.aciklama else "⏱ Zaman kaydı")[:300],
        revizyon=(k.tur == "revizyon"),
        giren_eposta=k.kisi_eposta,
    )
    db.add(giris)
    await db.flush()
    k.gorev_saat_id = giris.id
    await saat_toplamini_yenile(db, k.gorev_id)
    return musteri if (k.tur == "revizyon" and musteri) else None


async def _aynayi_sil(db: AsyncSession, k: ZamanKayitlari) -> None:
    from services.gorevler import saat_toplamini_yenile

    if not k.gorev_saat_id:
        return
    giris = (await db.execute(select(TaskTimeEntries).where(TaskTimeEntries.id == k.gorev_saat_id))).scalar_one_or_none()
    if giris is not None:
        if giris.kredi_saat:
            # Krediden düşülmüş saat silinmez (Faz 2B kuralı): önce kredi defteri.
            raise ZamanHatasi(409, "kredide_dusulmus")
        gorev_id = giris.gorev_id
        await db.delete(giris)
        await db.flush()
        await saat_toplamini_yenile(db, gorev_id)
    k.gorev_saat_id = None


def _idler(ham: Any) -> List[int]:
    if not isinstance(ham, list) or not ham:
        raise ZamanHatasi(400, "kayit_secilmedi")
    try:
        idler = sorted({int(i) for i in ham})
    except (TypeError, ValueError) as exc:
        raise ZamanHatasi(400, "kayit_secilmedi") from exc
    if len(idler) > TOPLU_SINIR:
        raise ZamanHatasi(400, "cok_fazla")
    return idler


async def onay_islemi(db: AsyncSession, yonetici: str, govde: Dict[str, Any]) -> Dict[str, Any]:
    """Toplu onay/ret. Yalnız durmuş `taslak` kayıtlar; diğerleri `atlanan`."""
    islem = govde.get("islem")
    if islem not in ("onayla", "reddet"):
        raise ZamanHatasi(400, "islem_gecersiz")
    idler = _idler(govde.get("idler"))
    not_ = _metin(govde.get("not"), RET_NOTU_SINIRI)
    if islem == "reddet" and not not_:
        raise ZamanHatasi(400, "ret_notu_gerekli")
    kayitlar = list((await db.execute(select(ZamanKayitlari).where(ZamanKayitlari.id.in_(idler)))).scalars().all())
    bulunan = {k.id for k in kayitlar}
    islenen: List[int] = []
    atlanan: List[int] = [i for i in idler if i not in bulunan]
    revizyon_musterileri: Set[str] = set()
    an = simdi()
    for k in kayitlar:
        if k.durum != "taslak" or k.bitis is None:
            atlanan.append(k.id)
            continue
        if islem == "onayla":
            k.durum = "onaylandi"
            k.ret_notu = None
            k.onaylayan_eposta = yonetici
            k.onay_at = an
            musteri = await _aynala(db, k)
            if musteri:
                revizyon_musterileri.add(musteri)
        else:
            k.durum = "reddedildi"
            k.ret_notu = not_
            k.onaylayan_eposta = yonetici
            k.onay_at = an
        islenen.append(k.id)
    await db.commit()
    # Revizyon hakkı aşıldıysa (Faz 2B) yöneticiye ayda bir uyarı.
    if revizyon_musterileri:
        from services.gorevler import revizyon_asim_bildir, revizyon_sayaci

        for musteri in revizyon_musterileri:
            try:
                await revizyon_asim_bildir(db, musteri, await revizyon_sayaci(db, musteri))
            except Exception:  # noqa: BLE001
                logger.exception("Revizyon aşım denetimi yapılamadı")
    return {"islem": islem, "islenen": sorted(islenen), "atlanan": sorted(atlanan)}


async def onayi_geri_al(db: AsyncSession, kayit_id: int) -> Dict[str, Any]:
    k = (await db.execute(select(ZamanKayitlari).where(ZamanKayitlari.id == kayit_id))).scalar_one_or_none()
    if k is None:
        raise ZamanHatasi(404, "kayit_yok")
    if k.durum == "faturalandi":
        raise ZamanHatasi(409, "kayit_faturalandi", fatura_id=k.fatura_id)
    if k.durum not in ("onaylandi", "reddedildi"):
        raise ZamanHatasi(409, "onayli_degil")
    await _aynayi_sil(db, k)
    k.durum = "taslak"
    k.onaylayan_eposta = None
    k.onay_at = None
    k.ret_notu = None
    await db.commit()
    await db.refresh(k)
    return await tek_sozluk(db, k)


async def gorevsiz_revizyon_saati(db: AsyncSession, proje_idler: Iterable[int], bas: date, bit: date) -> float:
    """[bas, bit) ayında görevsiz, onaylı "revizyon" kayıtlarının saati (Faz 2B sayacına ek)."""
    pidler = list(proje_idler)
    if not pidler:
        return 0.0
    satirlar = (
        await db.execute(
            select(ZamanKayitlari.sure_dk)
            .where(ZamanKayitlari.proje_id.in_(pidler))
            .where(ZamanKayitlari.tur == "revizyon")
            .where(ZamanKayitlari.gorev_id.is_(None))
            .where(ZamanKayitlari.durum.in_(ONAYLI_DURUMLAR))
            .where(ZamanKayitlari.baslangic >= yerel_gece(bas))
            .where(ZamanKayitlari.baslangic < yerel_gece(bit))
        )
    ).all()
    return round(sum(int(s[0] or 0) for s in satirlar) / 60.0, 2)


# ---------------------------------------------------------------------------
# Çizelge ve iş yükü
# ---------------------------------------------------------------------------
async def cizelge(
    db: AsyncSession, kisi: Kisi, *, hafta: Optional[str] = None, kisi_eposta: Optional[str] = None,
    proje_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Haftalık (Pzt–Paz) kişi × gün dakika tablosu. Reddedilen ve çalışan sayaç sayılmaz."""
    bas = hafta_basi(tarih_coz(hafta) or bugun())
    gunler = [bas + timedelta(days=i) for i in range(7)]
    sorgu = (
        select(ZamanKayitlari)
        .where(ZamanKayitlari.baslangic >= yerel_gece(bas))
        .where(ZamanKayitlari.baslangic < yerel_gece(bas + timedelta(days=7)))
        .where(ZamanKayitlari.bitis.isnot(None))
        .where(ZamanKayitlari.durum != "reddedildi")
    )
    kosul = kisi_kosulu(kisi)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    elif kisi_eposta:
        sorgu = sorgu.where(ZamanKayitlari.kisi_eposta == eposta_duzelt(kisi_eposta))
    if proje_id:
        sorgu = sorgu.where(ZamanKayitlari.proje_id == int(proje_id))
    kayitlar = (await db.execute(sorgu)).scalars().all()
    adlar = await ekip_adlari(db)
    tablo: Dict[str, Dict[str, Any]] = {}
    for k in kayitlar:
        gun = yerel_gun(k.baslangic)
        if gun is None or gun not in gunler:
            continue
        i = gunler.index(gun)
        satir = tablo.setdefault(
            k.kisi_eposta,
            {"eposta": k.kisi_eposta, "ad": adlar.get(k.kisi_eposta), "gunler": [0] * 7, "toplam_dk": 0,
             "onayli_dk": 0, "taslak_dk": 0, "faturalanabilir_dk": 0},
        )
        dk = int(k.sure_dk or 0)
        satir["gunler"][i] += dk
        satir["toplam_dk"] += dk
        if k.durum in ONAYLI_DURUMLAR:
            satir["onayli_dk"] += dk
        else:
            satir["taslak_dk"] += dk
        if k.faturalanabilir:
            satir["faturalanabilir_dk"] += dk
    kisiler = sorted(tablo.values(), key=lambda s: (-s["toplam_dk"], s["eposta"]))
    gun_toplamlari = [sum(s["gunler"][i] for s in kisiler) for i in range(7)]
    return {
        "hafta_baslangic": bas.isoformat(),
        "gunler": [g.isoformat() for g in gunler],
        "kisiler": kisiler,
        "gun_toplamlari": gun_toplamlari,
        "genel_toplam_dk": sum(gun_toplamlari),
    }


async def is_yuku(db: AsyncSession) -> Dict[str, Any]:
    """Kişi başına bu hafta / geçen hafta saat, açık ve gecikmiş görev sayısı."""
    gun = bugun()
    bu_bas = hafta_basi(gun)
    gecen_bas = bu_bas - timedelta(days=7)
    kayitlar = (
        await db.execute(
            select(ZamanKayitlari.kisi_eposta, ZamanKayitlari.baslangic, ZamanKayitlari.sure_dk)
            .where(ZamanKayitlari.baslangic >= yerel_gece(gecen_bas))
            .where(ZamanKayitlari.baslangic < yerel_gece(bu_bas + timedelta(days=7)))
            .where(ZamanKayitlari.bitis.isnot(None))
            .where(ZamanKayitlari.durum != "reddedildi")
        )
    ).all()
    kisiler: Dict[str, Dict[str, Any]] = {}

    def satir(eposta: str) -> Dict[str, Any]:
        return kisiler.setdefault(
            eposta, {"eposta": eposta, "ad": None, "bu_hafta_dk": 0, "gecen_hafta_dk": 0, "acik_gorev": 0, "geciken_gorev": 0}
        )

    for s in (await db.execute(select(Staff).where(Staff.aktif.isnot(False)))).scalars().all():
        if s.email:
            satir(eposta_duzelt(s.email))["ad"] = s.ad
    for eposta, bas, dk in kayitlar:
        g = yerel_gun(bas)
        if g is None:
            continue
        alan = "bu_hafta_dk" if g >= bu_bas else "gecen_hafta_dk"
        satir(eposta)[alan] += int(dk or 0)
    for atanan, bitis in (
        await db.execute(
            select(ProjectTasks.atanan, ProjectTasks.bitis_tarihi)
            .where(ProjectTasks.atanan.isnot(None))
            .where(ProjectTasks.durum != "tamam")
        )
    ).all():
        e = eposta_duzelt(atanan)
        if not e:
            continue
        s = satir(e)
        s["acik_gorev"] += 1
        if bitis is not None and bitis < gun:
            s["geciken_gorev"] += 1
    liste = sorted(kisiler.values(), key=lambda s: (-s["bu_hafta_dk"], -s["acik_gorev"], s["eposta"]))
    return {
        "bugun": gun.isoformat(),
        "bu_hafta_baslangic": bu_bas.isoformat(),
        "gecen_hafta_baslangic": gecen_bas.isoformat(),
        "kisiler": liste,
        "en_cok_dk": max([max(s["bu_hafta_dk"], s["gecen_hafta_dk"]) for s in liste] or [0]),
        "en_cok_gorev": max([s["acik_gorev"] for s in liste] or [0]),
    }


# ---------------------------------------------------------------------------
# Faturaya aktarım
# ---------------------------------------------------------------------------
def _uygun_mu(k: ZamanKayitlari) -> bool:
    return k.durum == "onaylandi" and bool(k.faturalanabilir) and k.fatura_id is None and bool(k.sure_dk)


async def faturalanabilir_ozet(db: AsyncSession, proje_id: int) -> Dict[str, Any]:
    proje = await proje_bul(db, proje_id)
    kayitlar = list(
        (
            await db.execute(
                select(ZamanKayitlari)
                .where(ZamanKayitlari.proje_id == proje.id)
                .where(ZamanKayitlari.durum == "onaylandi")
                .where(ZamanKayitlari.faturalanabilir.is_(True))
                .where(ZamanKayitlari.fatura_id.is_(None))
                .order_by(ZamanKayitlari.baslangic)
            )
        ).scalars().all()
    )
    ucret, pb, kaynak = await proje_ucreti(db, proje)
    return {
        "proje": {"id": proje.id, "baslik": proje.title, "client_email": proje.client_email},
        "kayitlar": await sozlukler(db, kayitlar),
        "toplam_dk": sum(int(k.sure_dk or 0) for k in kayitlar),
        "proje_ucreti": float(ucret) if ucret is not None else None,
        "para_birimi": pb,
        "ucret_kaynagi": kaynak,
    }


def _saat(dk: int) -> Decimal:
    return (Decimal(dk) / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _donem(kayitlar: Sequence[ZamanKayitlari]) -> str:
    gunler = sorted({yerel_gun(k.baslangic) for k in kayitlar if k.baslangic})
    if not gunler:
        return ""
    ilk, son = gunler[0], gunler[-1]
    return ilk.strftime("%d.%m.%Y") if ilk == son else f"{ilk.strftime('%d.%m.%Y')}–{son.strftime('%d.%m.%Y')}"


async def faturaya_aktar(db: AsyncSession, yonetici: str, govde: Dict[str, Any]) -> Dict[str, Any]:
    """Onaylı + faturalanabilir + faturalanmamış kayıtlar → taslak fatura satırları.

    Çift faturalamaya karşı üç kat koruma:
    1. Servis: her kayıt seçilirken uygunluğu (onaylı, faturasız) denetleniyor.
    2. Bağ tablosu: `zaman_fatura_baglari.zaman_kaydi_id` benzersiz (eşzamanlı
       iki aktarımdan biri IntegrityError → 409).
    3. Koşullu UPDATE: `durum='onaylandi' AND fatura_id IS NULL` — etkilenen
       satır sayısı seçilen sayıya eşit değilse işlem geri alınıyor.
    """
    from services import faturalar as fs
    from services.faturalar import FaturaHatasi

    proje = await proje_bul(db, govde.get("proje_id"))
    musteri = eposta_duzelt(proje.client_email)
    if not musteri:
        raise ZamanHatasi(409, "musteri_yok")
    gruplama = govde.get("gruplama") or "tek"
    if gruplama not in GRUPLAMALAR:
        raise ZamanHatasi(400, "gruplama_gecersiz")
    try:
        kdv = Decimal(str(govde.get("kdv_orani", VARSAYILAN_KDV)))
    except Exception as exc:  # noqa: BLE001
        raise ZamanHatasi(400, "kdv_gecersiz") from exc
    if not kdv.is_finite() or kdv < 0 or kdv > 100:
        raise ZamanHatasi(400, "kdv_gecersiz")
    ham_idler = govde.get("idler")
    sorgu = select(ZamanKayitlari).where(ZamanKayitlari.proje_id == proje.id)
    if ham_idler is not None:
        idler = _idler(ham_idler)
        kayitlar = list((await db.execute(sorgu.where(ZamanKayitlari.id.in_(idler)))).scalars().all())
        eksik = sorted(set(idler) - {k.id for k in kayitlar})
        if eksik:
            raise ZamanHatasi(404, "kayit_yok", kayitlar=eksik)
        uygunsuz = sorted(k.id for k in kayitlar if not _uygun_mu(k))
        if uygunsuz:
            zaten = sorted(k.id for k in kayitlar if k.fatura_id is not None or k.durum == "faturalandi")
            raise ZamanHatasi(409, "zaten_faturalandi" if zaten else "uygun_degil", kayitlar=uygunsuz)
    else:
        kayitlar = [k for k in (await db.execute(sorgu)).scalars().all() if _uygun_mu(k)]
    if not kayitlar:
        raise ZamanHatasi(409, "kayit_yok")
    kayitlar.sort(key=lambda k: (utc(k.baslangic), k.id))

    vars_ucret = _ondalik(govde.get("varsayilan_ucret"))
    proje_ucret, proje_pb, _ = await proje_ucreti(db, proje)
    ucretler: Dict[int, Tuple[Decimal, str]] = {}
    ucretsiz: List[int] = []
    for k in kayitlar:
        if k.saatlik_ucret is not None:
            ucretler[k.id] = (Decimal(str(k.saatlik_ucret)), (k.para_birimi or proje_pb).upper())
        elif vars_ucret is not None:
            ucretler[k.id] = (vars_ucret, proje_pb)
        else:
            ucretsiz.append(k.id)
    if ucretsiz:
        raise ZamanHatasi(409, "ucret_yok", kayitlar=ucretsiz)
    para_birimleri = {pb for _, pb in ucretler.values()}
    if len(para_birimleri) != 1:
        raise ZamanHatasi(409, "para_birimi_karisik", para_birimleri=sorted(para_birimleri))
    para = para_birimleri.pop()

    projeler, gorevler, adlar = await _adlar(db, kayitlar)
    gruplar: Dict[Tuple[Any, ...], List[ZamanKayitlari]] = {}
    for k in kayitlar:
        ucret = ucretler[k.id][0]
        if gruplama == "kisi":
            anahtar: Tuple[Any, ...] = (k.kisi_eposta, ucret)
        elif gruplama == "gorev":
            anahtar = (k.gorev_id or 0, ucret)
        else:
            anahtar = (ucret,)
        gruplar.setdefault(anahtar, []).append(k)
    kalemler: List[Dict[str, Any]] = []
    kalem_kayitlari: List[List[ZamanKayitlari]] = []
    for anahtar, liste in gruplar.items():
        dk = sum(int(k.sure_dk or 0) for k in liste)
        donem = _donem(liste)
        if gruplama == "kisi":
            etiket = adlar.get(anahtar[0]) or anahtar[0]
            aciklama = f"{proje.title} — {etiket} ({donem})"
        elif gruplama == "gorev":
            baslik = gorevler.get(anahtar[0]) if anahtar[0] else None
            aciklama = f"{proje.title} — {baslik or 'Genel çalışma'} ({donem})"
        else:
            aciklama = f"{proje.title} — çalışma saatleri ({donem})"
        kalemler.append({
            "aciklama": aciklama, "adet": float(_saat(dk)), "birim_fiyat": float(anahtar[-1]),
            "kdv_orani": float(kdv), "indirim": 0,
        })
        kalem_kayitlari.append(liste)

    hedef_fatura: Optional[int] = None
    if govde.get("fatura_id") not in (None, "", 0):
        try:
            hedef_fatura = int(govde["fatura_id"])
        except (TypeError, ValueError) as exc:
            raise ZamanHatasi(400, "fatura_gecersiz") from exc
    try:
        fatura, yeni = await fs.taslak_fatura_bul_ya_da_ac(
            db,
            client_email=musteri,
            client_name=proje.client_name,
            para_birimi=para,
            aciklama=f"{proje.title} — çalışma saatleri",
            fatura_id=hedef_fatura,
            onek="ZMN",
        )
        ilk_sira = await fs.faturaya_kalem_ekle(db, fatura, kalemler)
    except FaturaHatasi as h:
        await db.rollback()
        raise ZamanHatasi(h.durum, h.kod, **h.ek) from h

    idler = [k.id for k in kayitlar]
    try:
        for sira, liste in enumerate(kalem_kayitlari):
            for k in liste:
                db.add(ZamanFaturaBaglari(zaman_kaydi_id=k.id, fatura_id=fatura.id, kalem_sira=ilk_sira + sira,
                                          olusturan_eposta=yonetici))
        await db.flush()
        sonuc = await db.execute(
            update(ZamanKayitlari)
            .where(ZamanKayitlari.id.in_(idler))
            .where(ZamanKayitlari.durum == "onaylandi")
            .where(ZamanKayitlari.fatura_id.is_(None))
            .values(durum="faturalandi", fatura_id=fatura.id, updated_at=simdi())
            .execution_options(synchronize_session=False)
        )
        if int(sonuc.rowcount or 0) != len(idler):
            raise IntegrityError("zaman_kayitlari", None, Exception("eşzamanlı faturalama"))
    except IntegrityError as exc:
        await db.rollback()
        raise ZamanHatasi(409, "zaten_faturalandi", kayitlar=idler) from exc
    await db.commit()
    await db.refresh(fatura)
    return {
        "fatura_id": fatura.id,
        "invoice_no": fatura.invoice_no,
        "yeni_fatura": yeni,
        "durum": fatura.status,
        "tutar": float(fatura.amount or 0),
        "para_birimi": fatura.currency,
        "kalem_sayisi": len(kalemler),
        "kayit_sayisi": len(idler),
        "kayitlar": idler,
    }


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
CSV_BASLIKLARI = (
    "id", "tarih", "baslangic", "bitis", "sure_dk", "saat", "kisi", "kisi_ad", "proje_id", "proje", "gorev_id",
    "gorev", "aciklama", "tur", "faturalanabilir", "saatlik_ucret", "para_birimi", "tutar", "durum", "fatura_id",
)


def _hucre(deger: Any) -> Any:
    """Tablo programında formül olarak çalışmasın (CSV enjeksiyonu)."""
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + deger
    return deger


async def csv_metni(
    db: AsyncSession, *, baslangic: Optional[str], bitis: Optional[str], proje_id: Optional[int],
    kisi_eposta: Optional[str] = None,
) -> str:
    bas = tarih_coz(baslangic)
    bit = tarih_coz(bitis)
    if bas and bit and bit < bas:
        raise ZamanHatasi(400, "tarih_araligi")
    sorgu = select(ZamanKayitlari).where(ZamanKayitlari.bitis.isnot(None))
    if bas:
        sorgu = sorgu.where(ZamanKayitlari.baslangic >= yerel_gece(bas))
    if bit:
        sorgu = sorgu.where(ZamanKayitlari.baslangic < yerel_gece(bit + timedelta(days=1)))
    if proje_id:
        sorgu = sorgu.where(ZamanKayitlari.proje_id == int(proje_id))
    if kisi_eposta:
        sorgu = sorgu.where(ZamanKayitlari.kisi_eposta == eposta_duzelt(kisi_eposta))
    kayitlar = list((await db.execute(sorgu.order_by(ZamanKayitlari.baslangic, ZamanKayitlari.id).limit(20000))).scalars().all())
    projeler, gorevler, adlar = await _adlar(db, kayitlar)
    cikti = io.StringIO()
    yazici = csv.writer(cikti, lineterminator="\r\n")
    yazici.writerow(CSV_BASLIKLARI)
    for k in kayitlar:
        yerel_bas = utc(k.baslangic).astimezone(TR)  # type: ignore[union-attr]
        yerel_bit = utc(k.bitis).astimezone(TR) if k.bitis else None  # type: ignore[union-attr]
        yazici.writerow([_hucre(x) for x in (
            k.id, yerel_bas.date().isoformat(), yerel_bas.strftime("%H:%M"),
            yerel_bit.strftime("%H:%M") if yerel_bit else "", k.sure_dk or 0, f"{_saat(int(k.sure_dk or 0)):f}",
            k.kisi_eposta, adlar.get(k.kisi_eposta) or "", k.proje_id, projeler.get(k.proje_id) or "",
            k.gorev_id or "", gorevler.get(k.gorev_id) or "" if k.gorev_id else "", k.aciklama or "", k.tur or "normal",
            "evet" if k.faturalanabilir else "hayir",
            f"{Decimal(str(k.saatlik_ucret)):f}" if k.saatlik_ucret is not None else "", k.para_birimi or "",
            f"{tutar(k):.2f}" if tutar(k) is not None else "", k.durum, k.fatura_id or "",
        )])
    # Excel Türkçe karakterleri doğru açsın diye BOM.
    return "﻿" + cikti.getvalue()


# ---------------------------------------------------------------------------
# Müşteri görünümü
# ---------------------------------------------------------------------------
async def musteri_ozeti(db: AsyncSession, proje: Projects) -> Dict[str, Any]:
    """Yalnız onaylı (onaylandi + faturalandi) kayıtlar; kişi/ücret/tutar YOK."""
    kayitlar = (
        await db.execute(
            select(ZamanKayitlari.sure_dk, ZamanKayitlari.faturalanabilir, ZamanKayitlari.baslangic)
            .where(ZamanKayitlari.proje_id == proje.id)
            .where(ZamanKayitlari.durum.in_(ONAYLI_DURUMLAR))
        )
    ).all()
    gun = bugun()
    ay_bas = gun.replace(day=1)
    toplam = sum(int(s or 0) for s, _, _ in kayitlar)
    bu_ay = sum(int(s or 0) for s, _, b in kayitlar if (yerel_gun(b) or gun) >= ay_bas)
    sonuc: Dict[str, Any] = {
        "proje_id": proje.id,
        "toplam_dk": toplam,
        "toplam_saat": float(_saat(toplam)),
        "bu_ay_dk": bu_ay,
        "kayit_sayisi": len(kayitlar),
        "son_kayit": max((yerel_gun(b) for _, _, b in kayitlar if b), default=None),
    }
    if sonuc["son_kayit"] is not None:
        sonuc["son_kayit"] = sonuc["son_kayit"].isoformat()
    if proje.faturalanabilir_musteriye_gorunur:
        fdk = sum(int(s or 0) for s, f, _ in kayitlar if f)
        sonuc["faturalanabilir_dk"] = fdk
        sonuc["faturalanabilir_saat"] = float(_saat(fdk))
    return sonuc


# ---------------------------------------------------------------------------
# Fatura iptal/silme kancası — kayıtların kilidi açılıyor
# ---------------------------------------------------------------------------
def _iptal_edilen_faturalar(session: Session) -> Set[int]:
    from services.faturalar import IPTAL_DURUMLARI

    idler: Set[int] = set()
    for obj in list(session.deleted):
        if isinstance(obj, Invoices) and obj.id is not None:
            idler.add(obj.id)
    for obj in list(session.dirty):
        if not isinstance(obj, Invoices) or obj.id is None:
            continue
        try:
            gecmis = inspect(obj).attrs.status.history
        except Exception:  # noqa: BLE001
            continue
        if gecmis.has_changes() and (obj.status or "") in IPTAL_DURUMLARI:
            idler.add(obj.id)
    return idler


@event.listens_for(Session, "after_flush")
def _fatura_kilidini_ac(session: Session, flush_context) -> None:
    """Fatura silindi ya da iptal edildi → bağlı zaman kayıtları yeniden `onaylandi`.

    Kanca, faturanın hangi yoldan değiştiğine bakmıyor (entity uçları, iade
    faturası ile tam iptal, çöp kutusu…): iş birimi tek ortak kapı. Kendi
    SAVEPOINT'inde: yazılamazsa asıl işlem bozulmaz.
    """
    if not session.deleted and not session.dirty:
        return
    try:
        idler = _iptal_edilen_faturalar(session)
        if not idler:
            return
        baglanti = session.connection()
        with baglanti.begin_nested():
            baglanti.execute(
                update(ZamanKayitlari.__table__)
                .where(ZamanKayitlari.__table__.c.fatura_id.in_(idler))
                .values(durum="onaylandi", fatura_id=None, updated_at=simdi())
            )
            baglanti.execute(
                delete(ZamanFaturaBaglari.__table__).where(ZamanFaturaBaglari.__table__.c.fatura_id.in_(idler))
            )
    except Exception:  # noqa: BLE001 — fatura işlemi bu yüzden düşmemeli
        logger.exception("Zaman kayıtlarının fatura kilidi açılamadı")
