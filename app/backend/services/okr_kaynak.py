"""Faz 6O — otomatik KR kaynakları: değer elle check-in yerine mevcut veriden HESAPLANIR.

Kaynağın dönemi = hedefin dönemi ([başlangıç, bitiş] İstanbul günleri; tarih/zaman sütunları bitiş günü dahil).

Ajans (yönetici, kapsam `@ajans`):
* `crm_aday` — dönemde oluşan CRM adayı sayısı.
* `teklif_kabul` — dönemde KABUL edilen tekliflerin genel toplamı (seçili para birimi; kuruş).
* `fatura_tahsilat` — dönemde tahsil edilen ödemeler (durum `odendi`; müşteriye geri ödenen `iade` düşülür; seçili
  para birimi). Tarih: elle girilen ödeme tarihi, yoksa ödenme anı, yoksa kayıt anı.
* `muhasebe_gelir` / `muhasebe_gider` / `muhasebe_kar` — ön muhasebe kâr-zarar raporu (`services.muhasebe_kayit.kar_zarar`,
  KDV hariç; seçili para birimi) — ajansın KENDİ defteri.
* `proje_gorev` — seçili projenin görev tamamlanma yüzdesi (anlık; `tamam` / bütün görevler × 100).

Müşteri (modül `hedefler`, kapsam = hesap e-postası) — YALNIZ o hesabın kendi verisi ve YALNIZ açık modüllerden:
* `muhasebe_gelir` / `muhasebe_gider` / `muhasebe_kar` — modül `on_muhasebe` (hesabın defteri).
* `pos_satis` — modül `stok_pos`: dönemdeki satışların toplamı (iptal hariç, iade düşülür; seçili para birimi).
* `randevu_sayisi` — modül `randevu`: dönemde başlayan onaylı randevular.
* `egitim_kayit` — modül `egitim`: dönemde açılan öğrenci kayıtları (bekleme listesi hariç).

Modül kapalıysa kaynak listede görünmez (`kaynak_listesi`), KR'ye bağlanamaz ve yenileme değeri DEĞİŞTİRMEZ
(`kaynak_hata = "modul_kapali"`). Ekip üyesi için kaynağın verisini görme izni de aranır (`IZIN`): ön muhasebe
kaynakları `muhasebe`/`muhasebe_okur`, POS `stok`/`kasa`, randevu `randevu`, eğitim `egitim` (sahip için hepsi var).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services import okr as s
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Kaynak:
    anahtar: str
    #: ajans | musteri | her_ikisi
    kapsam: str
    #: Ürettiği KR türü (sayi | yuzde | para).
    tur: str
    #: Müşteri tarafında gereken modül (ajansta yok).
    modul: Optional[str] = None
    #: Ekip üyesinin kaynak verisini görmesi için izinlerden biri (müşteri tarafı).
    izinler: Tuple[str, ...] = ()
    #: Para birimi seçimli mi?
    para: bool = False
    #: Proje seçimi gerekir mi?
    proje: bool = False

    def sozluk(self) -> Dict[str, Any]:
        return {"anahtar": self.anahtar, "tur": self.tur, "para": self.para, "proje": self.proje, "modul": self.modul}


_MUHASEBE_IZIN = ("muhasebe", "muhasebe_okur")
KAYNAKLAR: Tuple[Kaynak, ...] = (
    Kaynak("crm_aday", "ajans", "sayi"),
    Kaynak("teklif_kabul", "ajans", "para", para=True),
    Kaynak("fatura_tahsilat", "ajans", "para", para=True),
    Kaynak("muhasebe_gelir", "her_ikisi", "para", modul="on_muhasebe", izinler=_MUHASEBE_IZIN, para=True),
    Kaynak("muhasebe_gider", "her_ikisi", "para", modul="on_muhasebe", izinler=_MUHASEBE_IZIN, para=True),
    Kaynak("muhasebe_kar", "her_ikisi", "para", modul="on_muhasebe", izinler=_MUHASEBE_IZIN, para=True),
    Kaynak("proje_gorev", "ajans", "yuzde", proje=True),
    Kaynak("pos_satis", "musteri", "para", modul="stok_pos", izinler=("stok", "kasa"), para=True),
    Kaynak("randevu_sayisi", "musteri", "sayi", modul="randevu", izinler=("randevu",)),
    Kaynak("egitim_kayit", "musteri", "sayi", modul="egitim", izinler=("egitim",)),
)
KAYNAK_SOZLUGU: Dict[str, Kaynak] = {k.anahtar: k for k in KAYNAKLAR}


def taraf_kaynaklari(ajans: bool) -> List[Kaynak]:
    return [k for k in KAYNAKLAR if k.kapsam in (("ajans", "her_ikisi") if ajans else ("musteri", "her_ikisi"))]


async def kaynak_listesi(db: AsyncSession, hesap: Optional[str], baglam: Any = None) -> List[Kaynak]:
    """Kapsamda kullanılabilen kaynaklar: ajansta hepsi; müşteride yalnız modülü AÇIK ve (üyede) izni olanlar."""
    if hesap is None:
        return taraf_kaynaklari(True)
    from services.moduller import modul_acik_mi

    sonuc = []
    acik: Dict[str, bool] = {}
    for k in taraf_kaynaklari(False):
        if k.modul not in acik:
            acik[k.modul] = await modul_acik_mi(db, hesap, k.modul) if k.modul else True
        if not acik[k.modul]:
            continue
        if baglam is not None and k.izinler and not any(baglam.izin_var(i) for i in k.izinler):
            continue
        sonuc.append(k)
    return sonuc


async def kaynak_kullanilabilir_mi(db: AsyncSession, anahtar: str, hesap: Optional[str], baglam: Any = None) -> bool:
    return any(k.anahtar == anahtar for k in await kaynak_listesi(db, hesap, baglam))


async def kaynak_acik_mi(db: AsyncSession, k: Kaynak, hesap: Optional[str]) -> bool:
    """Zamanlı yenilemede: kişi bağlamı yok; yalnız taraf + modül."""
    if hesap is None:
        return k.kapsam in ("ajans", "her_ikisi")
    if k.kapsam not in ("musteri", "her_ikisi"):
        return False
    if not k.modul:
        return True
    from services.moduller import modul_acik_mi

    return await modul_acik_mi(db, hesap, k.modul)


def _kurus(deger: Any) -> int:
    if deger is None:
        return 0
    return int((Decimal(str(deger)) * 100).quantize(Decimal("1")))


async def _say(db: AsyncSession, sorgu) -> int:
    return int((await db.execute(sorgu)).scalar() or 0)


async def kaynak_degeri(db: AsyncSession, anahtar: str, hesap: Optional[str], bas: date, bit: date,
                        ayar: Dict[str, Any]) -> float:
    """Kaynağın dönem değeri (para kuruş). Bilinmeyen / taraf dışı kaynak → OkrHatasi. Müşteri kaynakları YALNIZ
    `hesap`ın satırlarını sayar (her sorguda `hesap_email == hesap`)."""
    k = KAYNAK_SOZLUGU.get(anahtar)
    if k is None:
        raise s.OkrHatasi("kaynak_gecersiz", "kaynak")
    ajans = hesap is None
    if ajans and k.kapsam == "musteri" or (not ajans and k.kapsam == "ajans"):
        raise s.OkrHatasi("kaynak_gecersiz", "kaynak")
    bas_an, bit_an = s.aralik_anlari(bas, bit)
    pb = (ayar.get("para_birimi") or "TRY") if k.para else None

    if anahtar == "crm_aday":
        from models.crm import CrmAdaylari

        return float(await _say(db, select(func.count(CrmAdaylari.id)).where(
            CrmAdaylari.created_at >= bas_an, CrmAdaylari.created_at < bit_an)))
    if anahtar == "teklif_kabul":
        from models.teklifler import Teklifler

        satirlar = (await db.execute(select(Teklifler.genel_toplam).where(
            Teklifler.durum == "kabul", Teklifler.para_birimi == pb, Teklifler.karar_at >= bas_an,
            Teklifler.karar_at < bit_an))).scalars().all()
        return float(sum(_kurus(x) for x in satirlar))
    if anahtar == "fatura_tahsilat":
        return float(await _tahsilat(db, pb or "TRY", bas, bit, bas_an, bit_an))
    if anahtar in ("muhasebe_gelir", "muhasebe_gider", "muhasebe_kar"):
        from services import muhasebe as mh
        from services.muhasebe_kayit import kar_zarar

        rapor = await kar_zarar(db, mh.kapsam_anahtari(hesap), bas, bit)
        satir = next((x for x in rapor["para_birimleri"] if x["para_birimi"] == pb), None)
        if satir is None:
            return 0.0
        alan = {"muhasebe_gelir": "toplam_gelir", "muhasebe_gider": "toplam_gider", "muhasebe_kar": "sonuc"}[anahtar]
        return float(int(satir[alan]))
    if anahtar == "proje_gorev":
        from models.proje_gorevleri import ProjectTasks

        pid = ayar.get("proje_id")
        if not pid:
            raise s.OkrHatasi("proje_gerekli", "kaynak_ayar.proje_id")
        toplam = await _say(db, select(func.count(ProjectTasks.id)).where(ProjectTasks.proje_id == int(pid)))
        if not toplam:
            return 0.0
        biten = await _say(db, select(func.count(ProjectTasks.id)).where(ProjectTasks.proje_id == int(pid),
                                                                       ProjectTasks.durum == "tamam"))
        return round(biten * 100.0 / toplam, 1)
    # --- Müşteri kaynakları: her sorgu hesabın kendi satırlarıyla sınırlı ---
    if not hesap:
        raise s.OkrHatasi("kaynak_gecersiz", "kaynak")
    if anahtar == "pos_satis":
        from models.stok_pos import PosSatislari

        toplam = (await db.execute(select(func.sum(PosSatislari.toplam - PosSatislari.iade_toplam)).where(
            PosSatislari.hesap_email == hesap, PosSatislari.durum != "iptal", PosSatislari.para_birimi == pb,
            PosSatislari.zaman >= bas_an, PosSatislari.zaman < bit_an))).scalar()
        return float(int(toplam or 0))
    if anahtar == "randevu_sayisi":
        from models.randevu import Randevular

        return float(await _say(db, select(func.count(Randevular.id)).where(
            Randevular.hesap_email == hesap, Randevular.durum == "onayli", Randevular.baslangic >= bas_an,
            Randevular.baslangic < bit_an)))
    if anahtar == "egitim_kayit":
        from models.egitim import EgitimOgrencileri

        return float(await _say(db, select(func.count(EgitimOgrencileri.id)).where(
            EgitimOgrencileri.hesap_email == hesap, EgitimOgrencileri.durum != "bekleme",
            EgitimOgrencileri.created_at >= bas_an, EgitimOgrencileri.created_at < bit_an)))
    raise s.OkrHatasi("kaynak_gecersiz", "kaynak")


async def _tahsilat(db: AsyncSession, pb: str, bas: date, bit: date, bas_an, bit_an) -> int:
    from models.payments import Payments

    adaylar = (await db.execute(select(Payments).where(
        Payments.durum.in_(("odendi", "iade")),
        or_(Payments.odeme_tarihi.between(bas.isoformat(), bit.isoformat() + "~"),
            Payments.odendi_at.between(bas_an, bit_an), Payments.created_at.between(bas_an, bit_an))))).scalars().all()
    toplam = 0
    for p in adaylar:
        if (p.para_birimi or "TRY").upper() != pb:
            continue
        gun = _odeme_gunu(p)
        if gun is None or gun < bas or gun > bit:
            continue
        tutar = abs(_kurus(p.tutar))
        toplam += -tutar if p.durum == "iade" else tutar
    return toplam


def _odeme_gunu(p: Any) -> Optional[date]:
    if p.odeme_tarihi:
        try:
            return date.fromisoformat(str(p.odeme_tarihi)[:10])
        except ValueError:
            pass
    an = s.utc(p.odendi_at) or s.utc(p.created_at)
    return an.astimezone(s.tz()).date() if an else None


async def proje_listesi(db: AsyncSession) -> List[Dict[str, Any]]:
    """Ajans `proje_gorev` kaynağı için seçilebilir projeler (son 200)."""
    from models.projects import Projects

    satirlar = (await db.execute(select(Projects.id, Projects.title, Projects.client_name).order_by(Projects.id.desc()).limit(200))).all()
    return [{"id": i, "ad": t or f"#{i}", "musteri": c} for i, t, c in satirlar]


def ayar_duzelt(k: Kaynak, ham: Any, proje_idleri: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    if ham is None:
        ham = {}
    if not isinstance(ham, dict):
        raise s.OkrHatasi("kaynak_ayar_gecersiz", "kaynak_ayar")
    ayar: Dict[str, Any] = {}
    if k.para:
        ayar["para_birimi"] = s.para_birimi_duzelt(ham.get("para_birimi"), "kaynak_ayar.para_birimi")
    if k.proje:
        pid = s.kimlik(ham.get("proje_id"), "kaynak_ayar.proje_id", bos_olabilir=False)
        if proje_idleri is not None and pid not in proje_idleri:
            raise s.OkrHatasi("proje_bulunamadi", "kaynak_ayar.proje_id")
        ayar["proje_id"] = pid
    return ayar
