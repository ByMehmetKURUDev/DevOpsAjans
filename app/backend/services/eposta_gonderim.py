"""Faz 5M — e-posta pazarlama gönderim motoru.

* Resend istemcisi: toplu gönderim `POST /emails/batch` (çağrı başına ≤ 100 ileti,
  `Idempotency-Key`), tekil `POST /emails` (onay ve test e-postası). `ENVIRONMENT=test`
  iken (ve yalnız o zaman; Render'da asla) sahte servis: iletiler bellekteki
  kutuya düşer (`sahte_kutu()`), ağa çıkılmaz.
* Hız sınırı: Resend varsayılanı saniyede 2 istek (`PAZARLAMA_RESEND_RPS`).
  Sunucu uyuduğu için zamanlayıcı yok: "Gönder" isteği ilk parçayı hemen yollar,
  kalanını zamanlı görev (`services/zamanli.py` → `eposta_pazarlama`, her turda)
  tur başına süre ve ileti bütçesiyle parça parça gönderir.
* Satır yaşam döngüsü: kampanya başında kitle dondurulur (her kişi için bir
  `ep_gonderimler` satırı: `kuyrukta` ya da `atlandi` + neden). Gönderim anında
  izin/ret/bastırma/sıklık YENİDEN denetlenir (arada ret eden kişiye gitmez).
  Satırlar `parti` kimliğiyle alınır (eş zamanlı iki çalıştırma aynı satırı
  gönderemez); 15 dakikadan uzun "gonderiliyor"da kalan satır yeniden
  GÖNDERİLMEZ, `hata/yarida_kaldi` olur (bir iletinin eksik kalması, aynı iletinin
  iki kez gidip şikâyet almasından iyidir).
* Teslimat olayları (Resend webhook, Svix imzalı): teslim / geri dönüş (sert →
  bütün hesaplarda bastırma) / şikâyet (hesapta bastırma + ret) / açılma /
  tıklama. Son 30 günde şikâyet > %0,3 ya da sert geri dönüş > %5 (en az 50
  ileti) → hesap otomatik askıya alınır, yönetici bilgilendirilir.
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import random
import secrets
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from models.eposta_pazarlama import (
    EpAyarlar,
    EpBastirma,
    EpDiziAdimlari,
    EpDiziKayitlari,
    EpDiziler,
    EpGonderimler,
    EpKampanyalar,
    EpKisiler,
    EpListeler,
    EpListeUyelikleri,
    EpSegmentler,
)
from services import eposta_icerik as ic
from services import eposta_pazarlama as ep
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

RESEND_TABAN = "https://api.resend.com"
ZAMAN_ASIMI = 20.0
PARCA = 100
TUR_EN_COK = 1500
TUR_SURESI_SN = 25.0
ISTEK_ICI_EN_COK = 200
EN_COK_DENEME = 5
YARIDA_KALMA = timedelta(minutes=15)
GONDERILMIS = ("gonderildi", "teslim", "geri_dondu", "sikayet")
BEKLEYEN = ("kuyrukta", "ab_bekliyor", "gonderiliyor")


# ---------------------------------------------------------------------------
# Ortam
# ---------------------------------------------------------------------------
def _env(ad: str) -> str:
    return (os.environ.get(ad) or "").strip()


def sahte_mod() -> bool:
    """Sahte Resend YALNIZ `ENVIRONMENT=test` iken (üretimde ve Render'da asla)."""
    from services.site_analizi import uretim_mi

    if uretim_mi():
        return False
    return _env("ENVIRONMENT").lower() == "test"


def resend_kurulu() -> bool:
    return bool(_env("RESEND_API_KEY")) or sahte_mod()


def gonderen_adresi() -> str:
    """Pazarlama iletilerinin gönderen adresi (alan adı Resend'de doğrulanmış olmalı)."""
    from email.utils import parseaddr

    for ad in ("PAZARLAMA_FROM_EMAIL", "NOTIFY_FROM_EMAIL"):
        _, adres = parseaddr(_env(ad))
        if adres and "@" in adres:
            return adres.lower()
    return "bulten@mehmetkuru.dev"


def gonderen_alani(ad: str) -> str:
    temiz = " ".join(str(ad or "").replace('"', "").replace("<", "").replace(">", "").replace(",", " ").split())[:80]
    adres = gonderen_adresi()
    return f"{temiz} <{adres}>" if temiz else adres


# ---------------------------------------------------------------------------
# Sahte kutu (ENVIRONMENT=test)
# ---------------------------------------------------------------------------
_SAHTE: Deque[Dict[str, Any]] = deque(maxlen=500)


def sahte_kutu() -> List[Dict[str, Any]]:
    return list(_SAHTE)


def sahte_kutuyu_temizle() -> None:
    _SAHTE.clear()


# ---------------------------------------------------------------------------
# Hız sınırlayıcı
# ---------------------------------------------------------------------------
class AsyncHizSinirlayici:
    """Ardışık iki istek arasında en az 1/saniyede saniye (tek süreç; kilitli)."""

    def __init__(self, saniyede: float, saat=time.monotonic, uyku=asyncio.sleep):
        self.aralik = 1.0 / max(0.1, float(saniyede))
        self.saat = saat
        self.uyku = uyku
        self._son: Optional[float] = None
        self._kilit: Optional[asyncio.Lock] = None

    async def bekle(self) -> float:
        if self._kilit is None:
            self._kilit = asyncio.Lock()
        async with self._kilit:
            an = self.saat()
            beklenen = 0.0
            if self._son is not None:
                fark = self._son + self.aralik - an
                if fark > 0:
                    beklenen = fark
                    await self.uyku(fark)
                    an = self.saat()
            self._son = an
            return beklenen


def _rps() -> float:
    try:
        return float(_env("PAZARLAMA_RESEND_RPS") or 2)
    except ValueError:
        return 2.0


_HIZ = AsyncHizSinirlayici(_rps())


def hiz_sinirlayici() -> AsyncHizSinirlayici:
    return _HIZ


# ---------------------------------------------------------------------------
# Resend çağrıları
# ---------------------------------------------------------------------------
class ResendHatasi(Exception):
    def __init__(self, mesaj: str, gecici: bool, durum: int = 0):
        super().__init__(mesaj)
        self.gecici = gecici
        self.durum = durum


async def _resend_cagir(yol: str, govde: Any, basliklar: Dict[str, str]) -> Tuple[int, Any]:
    """Tek ağ noktası (testler bunu sahteliyor)."""
    anahtar = _env("RESEND_API_KEY")
    async with httpx.AsyncClient(timeout=ZAMAN_ASIMI) as istemci:
        y = await istemci.post(f"{RESEND_TABAN}{yol}", json=govde, headers={"Authorization": f"Bearer {anahtar}", **basliklar})
    try:
        veri = y.json()
    except ValueError:
        veri = {"message": y.text[:300]}
    return y.status_code, veri


def _sahte_gonder(iletiler: List[Dict[str, Any]]) -> List[Tuple[Optional[str], Optional[str]]]:
    sonuc = []
    for i in iletiler:
        kimlik = f"sahte-{uuid.uuid4().hex}"
        _SAHTE.append({**i, "id": kimlik, "zaman": ep.iso(ep.simdi())})
        sonuc.append((kimlik, None))
    return sonuc


async def resend_toplu(iletiler: List[Dict[str, Any]], anahtar: str,
                       hiz: Optional[AsyncHizSinirlayici] = None) -> List[Tuple[Optional[str], Optional[str]]]:
    """[(resend_id | None, hata | None)] — sıra iletilerle aynı. Geçici hata → ResendHatasi(gecici=True)."""
    if not iletiler:
        return []
    if not _env("RESEND_API_KEY"):
        if sahte_mod():
            return _sahte_gonder(iletiler)
        raise ResendHatasi("resend_kurulu_degil", gecici=False)
    await (hiz or _HIZ).bekle()
    try:
        durum, veri = await _resend_cagir(
            "/emails/batch", iletiler, {"Idempotency-Key": anahtar, "x-batch-validation": "permissive"}
        )
    except httpx.HTTPError as h:
        raise ResendHatasi(f"ag: {h}"[:200], gecici=True)
    if durum == 429 or durum >= 500:
        raise ResendHatasi(f"resend {durum}: {str(veri)[:200]}", gecici=True, durum=durum)
    if durum in (401, 403):
        raise ResendHatasi(f"resend {durum}: {str(veri)[:200]}", gecici=True, durum=durum)
    if durum >= 300:
        mesaj = (veri.get("message") if isinstance(veri, dict) else None) or str(veri)
        return [(None, f"resend {durum}: {mesaj}"[:300])] * len(iletiler)
    kimlikler = [d.get("id") for d in (veri.get("data") or []) if isinstance(d, dict)] if isinstance(veri, dict) else []
    hatalar = {int(e.get("index")): str(e.get("message") or "hata")[:300]
               for e in ((veri.get("errors") if isinstance(veri, dict) else None) or [])
               if isinstance(e, dict) and str(e.get("index", "")).isdigit()}
    sonuc: List[Tuple[Optional[str], Optional[str]]] = []
    sira = iter(kimlikler)
    for i in range(len(iletiler)):
        if i in hatalar:
            sonuc.append((None, hatalar[i]))
        else:
            sonuc.append((next(sira, None), None))
    return sonuc


async def resend_tekil(ileti: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Onay / test e-postası. (id, hata). Hata fırlatmaz."""
    if not _env("RESEND_API_KEY"):
        if sahte_mod():
            return _sahte_gonder([ileti])[0]
        return None, "resend_kurulu_degil"
    try:
        await _HIZ.bekle()
        durum, veri = await _resend_cagir("/emails", ileti, {})
    except httpx.HTTPError as h:
        return None, f"ag: {h}"[:200]
    if durum >= 300:
        return None, f"resend {durum}: {str(veri)[:200]}"
    return (veri.get("id") if isinstance(veri, dict) else None), None


# ---------------------------------------------------------------------------
# Hesap ayarları ve gönderen kimliği
# ---------------------------------------------------------------------------
async def ayar_getir(db: AsyncSession, hesap: Optional[str], olustur: bool = True) -> EpAyarlar:
    kapsam = ep.kapsam_anahtari(hesap)
    a = (await db.execute(select(EpAyarlar).where(EpAyarlar.kapsam == kapsam))).scalars().first()
    if a is not None or not olustur:
        return a  # type: ignore[return-value]
    a = EpAyarlar(kapsam=kapsam, hesap_email=hesap, dil="tr", iys_durumu="bilinmiyor", acilma_takibi=False,
                  tiklama_takibi=False, gunluk_kisi_siniri=ep.VARSAYILAN_GUNLUK_KISI_SINIRI, askida=False,
                  created_at=ep.simdi())
    db.add(a)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        a = (await db.execute(select(EpAyarlar).where(EpAyarlar.kapsam == kapsam))).scalars().first()
    return a  # type: ignore[return-value]


async def _site_ayarlari(db: AsyncSession, anahtarlar: Sequence[str]) -> Dict[str, str]:
    from models.site_settings import Site_settings

    satirlar = (await db.execute(select(Site_settings).where(Site_settings.setting_key.in_(list(anahtarlar))))).scalars().all()
    return {s.setting_key: str(s.setting_value or "").strip() for s in satirlar}


@dataclass
class Kimlik:
    gonderen_adi: str
    unvan: str
    adres: str
    yanit_adresi: str
    eksik: List[str] = field(default_factory=list)

    @property
    def tamam(self) -> bool:
        return not self.eksik

    def satir(self) -> str:
        return " · ".join(p for p in (self.unvan, self.adres) if p)


async def kimlik_getir(db: AsyncSession, hesap: Optional[str], ayar: Optional[EpAyarlar] = None) -> Kimlik:
    """Ajans: Site Ayarları › Yasal bilgiler (`yasal_*`); müşteri: kendi ayarındaki unvan/adres."""
    ayar = ayar or await ayar_getir(db, hesap)
    if hesap is None:
        y = await _site_ayarlari(db, ("yasal_unvan", "yasal_adres", "yasal_eposta"))
        unvan, adres = y.get("yasal_unvan", ""), y.get("yasal_adres", "")
        gonderen = (ayar.gonderen_adi or "").strip() or unvan or "mehmetkuru.dev"
        yanit = (ayar.yanit_adresi or "").strip() or y.get("yasal_eposta", "")
    else:
        unvan, adres = (ayar.unvan or "").strip(), (ayar.adres or "").strip()
        ad = (ayar.gonderen_adi or "").strip() or unvan or hesap
        # Müşteri gönderimleri ajansın doğrulanmış alan adından: "Müşteri via mehmetkuru.dev".
        gonderen = f"{ad} via mehmetkuru.dev"
        yanit = (ayar.yanit_adresi or "").strip() or hesap
    eksik = [a for a, d in (("unvan", unvan), ("adres", adres)) if not d]
    return Kimlik(gonderen_adi=gonderen, unvan=unvan, adres=adres, yanit_adresi=yanit, eksik=eksik)


def gorunen_gonderen(kimlik: Kimlik, hesap: Optional[str]) -> str:
    """Alt bilgide "{gonderen}" yerine: unvan (yoksa gönderen adı)."""
    return kimlik.unvan or kimlik.gonderen_adi


def alt_bilgi(dil: str, kimlik: Kimlik) -> Dict[str, str]:
    return {
        "kimlik": kimlik.satir(),
        "ret": ep.ileti_metni(dil, "ret"),
        "tercih": ep.ileti_metni(dil, "tercih"),
    }


# ---------------------------------------------------------------------------
# Bastırma ve kullanım
# ---------------------------------------------------------------------------
async def bastirilmis_kume(db: AsyncSession, kapsam: str, epostalar: Iterable[str]) -> set:
    liste = sorted({e for e in epostalar if e})
    sonuc: set = set()
    for i in range(0, len(liste), 500):
        parca = liste[i:i + 500]
        satirlar = (await db.execute(
            select(EpBastirma.eposta).where(EpBastirma.kapsam.in_([kapsam, ep.GENEL_KAPSAM]), EpBastirma.eposta.in_(parca))
        )).scalars().all()
        sonuc.update(satirlar)
    return sonuc


async def bastirmaya_ekle(db: AsyncSession, kapsam: str, eposta: str, neden: str, kaynak: Optional[str] = None) -> bool:
    eposta = ep.eposta_duzelt(eposta)
    if not eposta:
        return False
    var = (await db.execute(select(EpBastirma).where(EpBastirma.kapsam == kapsam, EpBastirma.eposta == eposta))).scalars().first()
    if var is not None:
        return False
    try:
        async with db.begin_nested():
            db.add(EpBastirma(kapsam=kapsam, eposta=eposta, neden=neden, kaynak=(kaynak or "")[:120] or None, created_at=ep.simdi()))
            await db.flush()
    except IntegrityError:
        return False
    return True


async def son_24_saat_sayilari(db: AsyncSession, kapsam: str, epostalar: Iterable[str]) -> Dict[str, int]:
    liste = sorted({e for e in epostalar if e})
    if not liste:
        return {}
    sinir = ep.simdi() - timedelta(hours=24)
    sonuc: Dict[str, int] = {}
    for i in range(0, len(liste), 500):
        satirlar = (await db.execute(
            select(EpGonderimler.eposta, func.count(EpGonderimler.id))
            .where(EpGonderimler.kapsam == kapsam, EpGonderimler.eposta.in_(liste[i:i + 500]),
                   EpGonderimler.durum.in_(GONDERILMIS), EpGonderimler.gonderim_at >= sinir)
            .group_by(EpGonderimler.eposta)
        )).all()
        sonuc.update({e: int(n) for e, n in satirlar})
    return sonuc


def ay_basi(an: Optional[datetime] = None) -> datetime:
    an = an or ep.simdi()
    return datetime(an.year, an.month, 1, tzinfo=timezone.utc)


async def aylik_kullanim(db: AsyncSession, kapsam: str) -> int:
    return int((await db.execute(
        select(func.count(EpGonderimler.id)).where(
            EpGonderimler.kapsam == kapsam, EpGonderimler.durum.in_(GONDERILMIS), EpGonderimler.gonderim_at >= ay_basi()
        )
    )).scalar() or 0)


async def aylik_sinir(db: AsyncSession, hesap: Optional[str]) -> Optional[int]:
    """Ajansta sınır yok (None); müşteride modül ayarı `aylik_gonderim_siniri`."""
    if hesap is None:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, ep.MODUL, "aylik_gonderim_siniri")
    return int(deger) if isinstance(deger, (int, float)) else ep.VARSAYILAN_AYLIK_SINIR


async def kisi_siniri(db: AsyncSession, hesap: Optional[str]) -> Optional[int]:
    if hesap is None:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, ep.MODUL, "kisi_siniri")
    return int(deger) if isinstance(deger, (int, float)) else ep.VARSAYILAN_KISI_SINIRI


async def modul_acik(db: AsyncSession, hesap: Optional[str]) -> bool:
    if hesap is None:
        return True
    from services import moduller

    return await moduller.modul_acik_mi(db, hesap, ep.MODUL)


# ---------------------------------------------------------------------------
# Ret (anında ve kalıcı)
# ---------------------------------------------------------------------------
async def ret_et(db: AsyncSession, kisi: EpKisiler, kaynak: str) -> bool:
    """Kişi reddetti: izin + bastırma + listeler + diziler + bekleyen iletiler. Commit çağırana."""
    an = ep.simdi()
    ilk = kisi.ret_zamani is None
    kisi.izin_durumu = "reddetti"
    kisi.ret_zamani = kisi.ret_zamani or an
    kisi.ret_kaynagi = kisi.ret_kaynagi if not ilk else kaynak
    await bastirmaya_ekle(db, kisi.kapsam, kisi.eposta, "sikayet" if kaynak == "sikayet" else "ret", kaynak)
    await db.execute(update(EpListeUyelikleri).where(EpListeUyelikleri.kisi_id == kisi.id, EpListeUyelikleri.durum != "cikti")
                     .values(durum="cikti", cikis_at=an).execution_options(synchronize_session=False))
    await db.execute(update(EpDiziKayitlari).where(EpDiziKayitlari.kisi_id == kisi.id, EpDiziKayitlari.durum == "aktif")
                     .values(durum="cikti", cikis_nedeni="ret", bitis_at=an).execution_options(synchronize_session=False))
    await db.execute(update(EpGonderimler).where(EpGonderimler.kisi_id == kisi.id, EpGonderimler.durum.in_(("kuyrukta", "ab_bekliyor")))
                     .values(durum="atlandi", neden="ret").execution_options(synchronize_session=False))
    if ilk:
        # Raporda "ret": kişinin son 30 gündeki son iletisine yazılıyor.
        son = (await db.execute(
            select(EpGonderimler).where(EpGonderimler.kisi_id == kisi.id, EpGonderimler.gonderim_at.isnot(None),
                                        EpGonderimler.gonderim_at >= an - timedelta(days=30))
            .order_by(EpGonderimler.gonderim_at.desc(), EpGonderimler.id.desc()).limit(1)
        )).scalars().first()
        if son is not None and son.ret_at is None:
            son.ret_at = an
    return ilk


# ---------------------------------------------------------------------------
# Kitle
# ---------------------------------------------------------------------------
async def hesap_kisileri(db: AsyncSession, hesap: Optional[str]) -> List[EpKisiler]:
    return list((await db.execute(select(EpKisiler).where(EpKisiler.kapsam == ep.kapsam_anahtari(hesap)))).scalars().all())


async def uyelik_haritasi(db: AsyncSession, kisi_idleri: Iterable[int]) -> Dict[int, set]:
    idler = list(kisi_idleri)
    sonuc: Dict[int, set] = {}
    for i in range(0, len(idler), 500):
        satirlar = (await db.execute(
            select(EpListeUyelikleri.kisi_id, EpListeUyelikleri.liste_id)
            .where(EpListeUyelikleri.kisi_id.in_(idler[i:i + 500]), EpListeUyelikleri.durum == "aktif")
        )).all()
        for k, l in satirlar:
            sonuc.setdefault(k, set()).add(l)
    return sonuc


async def crm_haritasi(db: AsyncSession, aday_idleri: Iterable[Optional[int]]) -> Dict[int, Dict[str, Any]]:
    idler = sorted({i for i in aday_idleri if i})
    if not idler:
        return {}
    from models.crm import CrmAdaylari

    sonuc: Dict[int, Dict[str, Any]] = {}
    for i in range(0, len(idler), 500):
        for a in (await db.execute(select(CrmAdaylari).where(CrmAdaylari.id.in_(idler[i:i + 500])))).scalars().all():
            sonuc[a.id] = {"asama": a.asama, "etiketler": [str(e).lower() for e in ep.json_yukle(a.etiketler, [])]}
    return sonuc


async def segment_kisileri(db: AsyncSession, hesap: Optional[str], kurallar: Dict[str, Any],
                           kisiler: Optional[List[EpKisiler]] = None) -> List[EpKisiler]:
    kisiler = kisiler if kisiler is not None else await hesap_kisileri(db, hesap)
    alanlar = {k.get("alan") for k in kurallar.get("kurallar") or []}
    baglam: Dict[str, Any] = {"simdi": ep.simdi()}
    if "liste" in alanlar:
        baglam["uyelikler"] = await uyelik_haritasi(db, [k.id for k in kisiler])
    if alanlar & {"crm_asama", "crm_etiket"}:
        baglam["crm"] = await crm_haritasi(db, [k.crm_aday_id for k in kisiler])
    return ep.segment_degerlendir(kurallar, kisiler, baglam)


def hedef_duzelt(ham: Any) -> Dict[str, List[int]]:
    d = ham if isinstance(ham, dict) else ep.json_yukle(ham, {})
    sonuc: Dict[str, List[int]] = {}
    for alan in ("listeler", "segmentler", "haric_listeler"):
        deger = d.get(alan) or []
        if not isinstance(deger, list) or any(isinstance(x, bool) or not isinstance(x, int) for x in deger) or len(deger) > 50:
            raise ep.PazarlamaHatasi("hedef_gecersiz", alan)
        sonuc[alan] = sorted(set(deger))
    return sonuc


async def kitle(db: AsyncSession, hesap: Optional[str], hedef: Dict[str, List[int]]) -> List[EpKisiler]:
    """Liste üyeleri (aktif) ∪ segmentler − hariç listeler; e-postaya göre tekil."""
    kapsam = ep.kapsam_anahtari(hesap)
    hesap_kosulu = EpListeler.hesap_email.is_(None) if hesap is None else EpListeler.hesap_email == hesap
    secilen: Dict[int, EpKisiler] = {}
    if hedef.get("listeler"):
        gecerli = set((await db.execute(select(EpListeler.id).where(EpListeler.id.in_(hedef["listeler"]), hesap_kosulu))).scalars().all())
        if gecerli:
            for k in (await db.execute(
                select(EpKisiler).join(EpListeUyelikleri, EpListeUyelikleri.kisi_id == EpKisiler.id)
                .where(EpListeUyelikleri.liste_id.in_(gecerli), EpListeUyelikleri.durum == "aktif", EpKisiler.kapsam == kapsam)
            )).scalars().all():
                secilen[k.id] = k
    if hedef.get("segmentler"):
        seg_kosul = EpSegmentler.hesap_email.is_(None) if hesap is None else EpSegmentler.hesap_email == hesap
        segmentler = (await db.execute(select(EpSegmentler).where(EpSegmentler.id.in_(hedef["segmentler"]), seg_kosul))).scalars().all()
        if segmentler:
            hepsi = await hesap_kisileri(db, hesap)
            for s in segmentler:
                kurallar = ep.json_yukle(s.kurallar, {})
                for k in await segment_kisileri(db, hesap, kurallar, hepsi):
                    secilen[k.id] = k
    if hedef.get("haric_listeler") and secilen:
        haric = set((await db.execute(
            select(EpListeUyelikleri.kisi_id).join(EpListeler, EpListeler.id == EpListeUyelikleri.liste_id)
            .where(EpListeUyelikleri.liste_id.in_(hedef["haric_listeler"]), EpListeUyelikleri.durum == "aktif", hesap_kosulu)
        )).scalars().all())
        for kid in haric:
            secilen.pop(kid, None)
    tekil: Dict[str, EpKisiler] = {}
    for k in sorted(secilen.values(), key=lambda x: x.id):
        tekil.setdefault(k.eposta, k)
    return list(tekil.values())


async def kitle_ozeti(db: AsyncSession, hesap: Optional[str], hedef: Dict[str, List[int]], *, siklik: bool = False) -> Dict[str, Any]:
    """Kitle sayımı. `siklik=True` (panel önizlemesi): günlük kişi sınırı ŞU AN uygulanır; gönderim
    kararında ve zamanlanmış kampanyada sınır gönderim anında yeniden değerlendirilir."""
    kisiler = await kitle(db, hesap, hedef)
    kapsam = ep.kapsam_anahtari(hesap)
    bastirilan = await bastirilmis_kume(db, kapsam, [k.eposta for k in kisiler])
    gunluk, son24 = 0, {}
    if siklik:
        ayar = await ayar_getir(db, hesap, olustur=False)
        gunluk = int(ayar.gunluk_kisi_siniri or 0) if ayar is not None else ep.VARSAYILAN_GUNLUK_KISI_SINIRI
        if gunluk:
            son24 = await son_24_saat_sayilari(db, kapsam, [k.eposta for k in kisiler])
    nedenler: Dict[str, int] = {}
    gonderilebilir = 0
    for k in kisiler:
        karar = ep.gonderim_karari(k, bastirilmis=k.eposta in bastirilan, son_24_saat=son24.get(k.eposta, 0), gunluk_sinir=gunluk)
        if karar is None:
            gonderilebilir += 1
        else:
            nedenler[karar] = nedenler.get(karar, 0) + 1
    return {"toplam": len(kisiler), "gonderilebilir": gonderilebilir, "atlanacak": nedenler}


# ---------------------------------------------------------------------------
# Kampanya başlatma (kitleyi dondur)
# ---------------------------------------------------------------------------
async def kampanya_hazirla(db: AsyncSession, k: EpKampanyalar, *, kimlik: Kimlik, ayar: EpAyarlar) -> Dict[str, Any]:
    """İçeriği dondur + kitleyi satırlara yaz. Kota ve hesap denetimi çağıranda. Commit çağırana."""
    hesap = k.hesap_email
    kapsam = ep.kapsam_anahtari(hesap)
    bloklar = ic.bloklari_dogrula(k.bloklar, izinli_onek=ep.site_adresi())
    dil = ep.dil_sec(k.dil)
    ab = alt_bilgi(dil, kimlik)
    renk = ayar.marka_rengi or ic.VARSAYILAN_RENK
    html, baglantilar = ic.html_uret(bloklar, konu=k.konu or "", onizleme=k.onizleme_metni or "", renk=renk,
                                     logo_url=ayar.logo_url, gonderen_adi=k.gonderen_adi or kimlik.gonderen_adi, dil=dil, alt_bilgi=ab)
    metin_ = ic.metin_uret(bloklar, gonderen_adi=k.gonderen_adi or kimlik.gonderen_adi, alt_bilgi=ab)
    k.html, k.metin, k.baglantilar = html, metin_, ep.json_yaz(baglantilar)
    k.takip_acilma, k.takip_tiklama = bool(ayar.acilma_takibi), bool(ayar.tiklama_takibi)

    hedef = hedef_duzelt(k.hedef)
    kisiler = await kitle(db, hesap, hedef)
    bastirilan = await bastirilmis_kume(db, kapsam, [x.eposta for x in kisiler])
    uygun: List[EpKisiler] = []
    atlananlar: List[Tuple[EpKisiler, str]] = []
    for x in kisiler:
        karar = ep.gonderim_karari(x, bastirilmis=x.eposta in bastirilan, gunluk_sinir=0)
        if karar is None:
            uygun.append(x)
        else:
            atlananlar.append((x, karar))
    ab_ayar = ep.ab_duzelt(k.ab)
    an = ep.simdi()
    satirlar: List[EpGonderimler] = []
    if ab_ayar.get("acik"):
        karisik = list(uygun)
        random.Random(k.id).shuffle(karisik)
        a_say, b_say = ep.ab_orneklem(len(karisik), ab_ayar["oran"])
        for i, x in enumerate(karisik):
            if i < a_say:
                durum, varyant = "kuyrukta", "a"
            elif i < a_say + b_say:
                durum, varyant = "kuyrukta", "b"
            else:
                durum, varyant = "ab_bekliyor", None
            satirlar.append(EpGonderimler(kapsam=kapsam, hesap_email=hesap, kampanya_id=k.id, kisi_id=x.id, eposta=x.eposta,
                                          varyant=varyant, durum=durum, created_at=an))
        k.durum = "ab_test"
        k.ab_karar_at = an + timedelta(hours=ab_ayar["bekleme_saat"])
    else:
        for x in uygun:
            satirlar.append(EpGonderimler(kapsam=kapsam, hesap_email=hesap, kampanya_id=k.id, kisi_id=x.id, eposta=x.eposta,
                                          durum="kuyrukta", created_at=an))
        k.durum = "gonderiliyor"
    for x, neden in atlananlar:
        satirlar.append(EpGonderimler(kapsam=kapsam, hesap_email=hesap, kampanya_id=k.id, kisi_id=x.id, eposta=x.eposta,
                                      durum="atlandi", neden=neden, created_at=an))
    db.add_all(satirlar)
    k.hedef_sayisi = len(kisiler)
    k.baslangic_at = an
    k.son_islem_at = an
    k.duraklatma_nedeni = None
    return {"toplam": len(kisiler), "gonderilebilir": len(uygun), "atlanan": len(atlananlar)}


# ---------------------------------------------------------------------------
# İleti kurma
# ---------------------------------------------------------------------------
@dataclass
class Icerik:
    konu: str
    konu_b: Optional[str]
    html: str
    metin: str
    baglantilar: List[str]
    gonderen: str
    yanit: str
    dil: str
    gorunen: str
    takip_acilma: bool
    takip_tiklama: bool


def ileti_kur(icerik: Icerik, g: EpGonderimler, kisi: EpKisiler) -> Dict[str, Any]:
    """Alıcıya özel ileti: işaretler (önce) → kişiselleştirme (sonra; değerler işaret üretemesin)."""
    baglantilar = icerik.baglantilar

    def bag(i: int) -> str:
        if i < 0 or i >= len(baglantilar):
            return ep.site_adresi()
        return ep.tiklama_adresi(g.id, i) if icerik.takip_tiklama else baglantilar[i]

    neden = ep.ileti_metni(icerik.dil, ep.neden_anahtari(kisi), gonderen=icerik.gorunen)
    ret = ep.tercih_adresi(kisi.id, ret=True)
    tercih = ep.tercih_adresi(kisi.id)
    piksel = ic.piksel_html(ep.piksel_adresi(g.id)) if icerik.takip_acilma else ""
    degerler = {"ad": kisi.ad or "", "firma": kisi.firma or "", "eposta": kisi.eposta}
    html = ic.isaretleri_doldur(icerik.html, html=True, baglanti=bag, ret=ret, tercih=tercih, neden=neden, piksel=piksel)
    metin_ = ic.isaretleri_doldur(icerik.metin, html=False, baglanti=bag, ret=ret, tercih=tercih, neden=neden)
    konu = icerik.konu_b if (g.varyant == "b" and icerik.konu_b) else icerik.konu
    ileti: Dict[str, Any] = {
        "from": gonderen_alani(icerik.gonderen),
        "to": [kisi.eposta],
        "subject": ic.konu_kisisellestir(konu, degerler),
        "html": ic.kisisellestir(html, degerler, html=True),
        "text": ic.kisisellestir(metin_, degerler, html=False),
        "headers": ep.ret_basliklari(kisi.id),
        "tags": [{"name": "ep", "value": str(g.id)}],
    }
    if icerik.yanit:
        ileti["reply_to"] = icerik.yanit
    return ileti


async def kampanya_icerigi(db: AsyncSession, k: EpKampanyalar) -> Icerik:
    ayar = await ayar_getir(db, k.hesap_email)
    kimlik = await kimlik_getir(db, k.hesap_email, ayar)
    ab_ayar = ep.ab_duzelt(k.ab) if k.ab else {"acik": False}
    return Icerik(
        konu=k.konu or "", konu_b=ab_ayar.get("konu_b") if ab_ayar.get("acik") else None, html=k.html or "", metin=k.metin or "",
        baglantilar=ep.json_yukle(k.baglantilar, []), gonderen=_gonderen_ad(k.gonderen_adi, k.hesap_email) or kimlik.gonderen_adi,
        yanit=(k.yanit_adresi or "").strip() or kimlik.yanit_adresi, dil=ep.dil_sec(k.dil), gorunen=gorunen_gonderen(kimlik, k.hesap_email),
        takip_acilma=bool(k.takip_acilma), takip_tiklama=bool(k.takip_tiklama),
    )


def _gonderen_ad(ad: Optional[str], hesap: Optional[str]) -> str:
    """Müşteri gönderimlerinde ad "… via mehmetkuru.dev" ile biter (ajans alan adından gidiyor)."""
    temiz = " ".join(str(ad or "").split())
    if hesap is None or not temiz:
        return temiz
    return temiz if temiz.endswith("via mehmetkuru.dev") else f"{temiz} via mehmetkuru.dev"


async def adim_icerigi(db: AsyncSession, dizi: EpDiziler, adim: EpDiziAdimlari) -> Icerik:
    ayar = await ayar_getir(db, dizi.hesap_email)
    kimlik = await kimlik_getir(db, dizi.hesap_email, ayar)
    dil = ep.dil_sec(dizi.dil)
    bloklar = ic.bloklari_dogrula(adim.bloklar, izinli_onek=ep.site_adresi())
    ab = alt_bilgi(dil, kimlik)
    gonderen = _gonderen_ad(dizi.gonderen_adi, dizi.hesap_email) or kimlik.gonderen_adi
    html, baglantilar = ic.html_uret(bloklar, konu=adim.konu, onizleme=adim.onizleme_metni or "", renk=ayar.marka_rengi or ic.VARSAYILAN_RENK,
                                     logo_url=ayar.logo_url, gonderen_adi=gonderen, dil=dil, alt_bilgi=ab)
    metin_ = ic.metin_uret(bloklar, gonderen_adi=gonderen, alt_bilgi=ab)
    return Icerik(konu=adim.konu, konu_b=None, html=html, metin=metin_, baglantilar=baglantilar, gonderen=gonderen,
                  yanit=kimlik.yanit_adresi, dil=dil, gorunen=gorunen_gonderen(kimlik, dizi.hesap_email),
                  takip_acilma=bool(ayar.acilma_takibi), takip_tiklama=bool(ayar.tiklama_takibi))


# ---------------------------------------------------------------------------
# Kuyruk işleme
# ---------------------------------------------------------------------------
@dataclass
class TurSonucu:
    gonderilen: int = 0
    atlanan: int = 0
    hata: int = 0
    durdu: Optional[str] = None
    kampanyalar: List[int] = field(default_factory=list)

    def sozluk(self) -> Dict[str, Any]:
        return {"gonderilen": self.gonderilen, "atlanan": self.atlanan, "hata": self.hata, "durdu": self.durdu}


async def _yarida_kalanlar(db: AsyncSession) -> int:
    sinir = ep.simdi() - YARIDA_KALMA
    s = await db.execute(
        update(EpGonderimler).where(EpGonderimler.durum == "gonderiliyor", EpGonderimler.alindi_at < sinir)
        .values(durum="hata", neden="yarida_kaldi").execution_options(synchronize_session=False)
    )
    return int(s.rowcount or 0)


async def _satirlari_al(db: AsyncSession, kosul: Any, sinir: int) -> Tuple[str, List[EpGonderimler]]:
    idler = list((await db.execute(
        select(EpGonderimler.id).where(EpGonderimler.durum == "kuyrukta", kosul).order_by(EpGonderimler.id).limit(sinir)
    )).scalars().all())
    if not idler:
        return "", []
    parti = secrets.token_hex(8)
    await db.execute(
        update(EpGonderimler).where(EpGonderimler.id.in_(idler), EpGonderimler.durum == "kuyrukta")
        .values(durum="gonderiliyor", parti=parti, alindi_at=ep.simdi()).execution_options(synchronize_session=False)
    )
    await db.commit()
    satirlar = list((await db.execute(
        select(EpGonderimler).where(EpGonderimler.parti == parti, EpGonderimler.durum == "gonderiliyor").order_by(EpGonderimler.id)
        .execution_options(populate_existing=True)
    )).scalars().all())
    return parti, satirlar


def _idempotency(satirlar: List[EpGonderimler]) -> str:
    return "ep-" + hashlib.sha256(",".join(str(s.id) for s in satirlar).encode()).hexdigest()[:40]


async def _parcayi_gonder(db: AsyncSession, satirlar: List[EpGonderimler], icerik_bul, gunluk_sinir: int,
                          hiz: Optional[AsyncHizSinirlayici], sonuc: TurSonucu) -> bool:
    """Alınmış satırları yeniden denetle → gönder → yaz. Geçici hatada False (tur durmalı)."""
    if not satirlar:
        return True
    kapsam = satirlar[0].kapsam
    kisiler = {k.id: k for k in (await db.execute(select(EpKisiler).where(EpKisiler.id.in_([s.kisi_id for s in satirlar if s.kisi_id])))).scalars().all()}
    bastirilan = await bastirilmis_kume(db, kapsam, [k.eposta for k in kisiler.values()])
    sayilar = await son_24_saat_sayilari(db, kapsam, [k.eposta for k in kisiler.values()])
    gidecek: List[Tuple[EpGonderimler, EpKisiler, Dict[str, Any]]] = []
    an = ep.simdi()
    for s in satirlar:
        kisi = kisiler.get(s.kisi_id or -1)
        if kisi is None:
            s.durum, s.neden = "atlandi", "kisi_silindi"
            sonuc.atlanan += 1
            continue
        karar = ep.gonderim_karari(kisi, bastirilmis=kisi.eposta in bastirilan, son_24_saat=sayilar.get(kisi.eposta, 0),
                                   gunluk_sinir=gunluk_sinir)
        if karar is not None:
            s.durum, s.neden = "atlandi", karar
            sonuc.atlanan += 1
            continue
        try:
            icerik = await icerik_bul(s)
        except Exception as h:  # noqa: BLE001 - bozuk içerik tek satırı düşürsün
            s.durum, s.neden, s.hata = "hata", "icerik", str(h)[:200]
            sonuc.hata += 1
            continue
        if icerik is None:
            s.durum, s.neden = "atlandi", "icerik_yok"
            sonuc.atlanan += 1
            continue
        sayilar[kisi.eposta] = sayilar.get(kisi.eposta, 0) + 1  # aynı partide ikinci ileti de sayılsın
        gidecek.append((s, kisi, ileti_kur(icerik, s, kisi)))
    await db.commit()
    if not gidecek:
        return True
    try:
        yanitlar = await resend_toplu([x[2] for x in gidecek], _idempotency([x[0] for x in gidecek]), hiz=hiz)
    except ResendHatasi as h:
        for s, _, _ in gidecek:
            s.deneme = int(s.deneme or 0) + 1
            if s.deneme >= EN_COK_DENEME or not h.gecici:
                s.durum, s.neden, s.hata = "hata", "resend", str(h)[:300]
                sonuc.hata += 1
            else:
                s.durum, s.parti, s.alindi_at, s.hata = "kuyrukta", None, None, str(h)[:300]
        await db.commit()
        sonuc.durdu = str(h)[:120]
        return False
    for (s, kisi, _), (kimlik, hata) in zip(gidecek, yanitlar):
        if kimlik:
            s.durum, s.resend_id, s.gonderim_at, s.hata = "gonderildi", kimlik, an, None
            kisi.son_gonderim_at = an
            sonuc.gonderilen += 1
        else:
            s.durum, s.neden, s.hata = "hata", "resend", (hata or "")[:300]
            sonuc.hata += 1
    await db.commit()
    return True


async def _kampanya_bitti_mi(db: AsyncSession, k: EpKampanyalar) -> None:
    kalan = int((await db.execute(
        select(func.count(EpGonderimler.id)).where(EpGonderimler.kampanya_id == k.id, EpGonderimler.durum.in_(BEKLEYEN))
    )).scalar() or 0)
    if kalan == 0 and k.durum in ("gonderiliyor",):
        k.durum = "tamamlandi"
        k.bitis_at = ep.simdi()
        k.son_islem_at = k.bitis_at


async def kampanya_gonder(db: AsyncSession, k: EpKampanyalar, *, en_cok: int, bitis: float,
                          hiz: Optional[AsyncHizSinirlayici] = None, sonuc: Optional[TurSonucu] = None) -> TurSonucu:
    sonuc = sonuc or TurSonucu()
    if k.durum not in ("gonderiliyor", "ab_test"):
        return sonuc
    ayar = await ayar_getir(db, k.hesap_email)
    if ayar.askida:
        k.durum, k.duraklatma_nedeni = "duraklatildi", "hesap_askida"
        await db.commit()
        return sonuc
    if not await modul_acik(db, k.hesap_email):
        k.durum, k.duraklatma_nedeni = "duraklatildi", "modul_kapali"
        await db.commit()
        return sonuc
    icerik = await kampanya_icerigi(db, k)

    async def icerik_bul(_s: EpGonderimler) -> Icerik:
        return icerik

    kapsam = ep.kapsam_anahtari(k.hesap_email)
    gonderilen = 0
    while gonderilen < en_cok and time.monotonic() < bitis:
        sinir = await aylik_sinir(db, k.hesap_email)
        parca = min(PARCA, en_cok - gonderilen)
        if sinir is not None:
            kalan = sinir - await aylik_kullanim(db, kapsam)
            if kalan <= 0:
                k.durum, k.duraklatma_nedeni = "duraklatildi", "kota"
                await db.commit()
                break
            parca = min(parca, kalan)
        _, satirlar = await _satirlari_al(db, EpGonderimler.kampanya_id == k.id, parca)
        if not satirlar:
            break
        devam = await _parcayi_gonder(db, satirlar, icerik_bul, int(ayar.gunluk_kisi_siniri or 0), hiz, sonuc)
        gonderilen += len(satirlar)
        if not devam:
            break
    await db.refresh(k)
    await _kampanya_bitti_mi(db, k)
    if k.id not in sonuc.kampanyalar:
        sonuc.kampanyalar.append(k.id)
    await db.commit()
    return sonuc


async def kampanya_istatistik(db: AsyncSession, kampanya_id: int, varyant: Optional[str] = None) -> Dict[str, int]:
    kosul = [EpGonderimler.kampanya_id == kampanya_id]
    if varyant is not None:
        kosul.append(EpGonderimler.varyant == varyant)
    satir = (await db.execute(
        select(
            func.count(EpGonderimler.id),
            func.count(EpGonderimler.gonderim_at),
            func.count(EpGonderimler.teslim_at),
            func.count(EpGonderimler.geri_donme_at),
            func.count(EpGonderimler.sikayet_at),
            func.count(EpGonderimler.ret_at),
            func.count(EpGonderimler.acilma_at),
            func.count(EpGonderimler.tiklama_at),
        ).where(*kosul)
    )).one()
    return {"satir": int(satir[0]), "gonderilen": int(satir[1]), "teslim": int(satir[2]), "geri_donen": int(satir[3]),
            "sikayet": int(satir[4]), "ret": int(satir[5]), "acilan": int(satir[6]), "tiklayan": int(satir[7])}


async def ab_kararlari(db: AsyncSession) -> int:
    an = ep.simdi()
    adaylar = (await db.execute(select(EpKampanyalar).where(EpKampanyalar.durum == "ab_test", EpKampanyalar.ab_karar_at <= an))).scalars().all()
    sayi = 0
    for k in adaylar:
        # Örneklem henüz gönderilmediyse (kota/askı) bekle.
        bekleyen = int((await db.execute(select(func.count(EpGonderimler.id)).where(
            EpGonderimler.kampanya_id == k.id, EpGonderimler.durum.in_(("kuyrukta", "gonderiliyor"))))).scalar() or 0)
        if bekleyen:
            continue
        ab_ayar = ep.ab_duzelt(k.ab)
        a = await kampanya_istatistik(db, k.id, "a")
        b = await kampanya_istatistik(db, k.id, "b")
        k.kazanan = ep.ab_kazanan(a, b, ab_ayar.get("olcut", "acilma"))
        await db.execute(update(EpGonderimler).where(EpGonderimler.kampanya_id == k.id, EpGonderimler.durum == "ab_bekliyor")
                         .values(durum="kuyrukta", varyant=k.kazanan).execution_options(synchronize_session=False))
        k.durum = "gonderiliyor"
        k.son_islem_at = an
        sayi += 1
    await db.commit()
    return sayi


async def zamanlanmislari_baslat(db: AsyncSession) -> int:
    an = ep.simdi()
    adaylar = (await db.execute(select(EpKampanyalar).where(EpKampanyalar.durum == "zamanlandi", EpKampanyalar.zamanlanan_at <= an)
                                .order_by(EpKampanyalar.zamanlanan_at).limit(20))).scalars().all()
    sayi = 0
    for k in adaylar:
        try:
            await kampanyayi_baslat(db, k)
            sayi += 1
        except (ep.PazarlamaHatasi, ic.IcerikHatasi) as h:
            k.durum, k.duraklatma_nedeni = "duraklatildi", h.kod
            k.son_islem_at = an
        await db.commit()
    return sayi


async def kampanyayi_baslat(db: AsyncSession, k: EpKampanyalar) -> Dict[str, Any]:
    """Denetimler (askı, kimlik, Resend, kota) + kitleyi dondur. Hata → PazarlamaHatasi."""
    ayar = await ayar_getir(db, k.hesap_email)
    if ayar.askida:
        raise ep.PazarlamaHatasi("hesap_askida", durum=409)
    if not resend_kurulu():
        raise ep.PazarlamaHatasi("resend_kurulu_degil", durum=409)
    kimlik = await kimlik_getir(db, k.hesap_email, ayar)
    if not kimlik.tamam:
        raise ep.PazarlamaHatasi("gonderen_kimligi_eksik", durum=409, eksik=kimlik.eksik)
    if not (k.konu or "").strip():
        raise ep.PazarlamaHatasi("metin_gerekli", "konu")
    hedef = hedef_duzelt(k.hedef)
    if not hedef["listeler"] and not hedef["segmentler"]:
        raise ep.PazarlamaHatasi("hedef_gerekli", "hedef")
    if not ic.bloklari_dogrula(k.bloklar, izinli_onek=ep.site_adresi()):
        raise ep.PazarlamaHatasi("icerik_bos", "bloklar")
    ab_ayar = ep.ab_duzelt(k.ab)
    ozet = await kitle_ozeti(db, k.hesap_email, hedef)
    if ozet["gonderilebilir"] == 0:
        raise ep.PazarlamaHatasi("kitle_bos", "hedef", durum=409, **{"atlanacak": ozet["atlanacak"]})
    if ab_ayar.get("acik") and ozet["gonderilebilir"] < 10:
        raise ep.PazarlamaHatasi("ab_kitle_kucuk", "ab", durum=409)
    sinir = await aylik_sinir(db, k.hesap_email)
    if sinir is not None:
        kalan = sinir - await aylik_kullanim(db, ep.kapsam_anahtari(k.hesap_email))
        if ozet["gonderilebilir"] > kalan:
            raise ep.PazarlamaHatasi("kota_yetersiz", durum=409, kalan=max(0, kalan), gerekli=ozet["gonderilebilir"])
    return await kampanya_hazirla(db, k, kimlik=kimlik, ayar=ayar)


# ---------------------------------------------------------------------------
# Damla dizileri
# ---------------------------------------------------------------------------
def _bekleme(adim: EpDiziAdimlari) -> timedelta:
    return timedelta(days=int(adim.bekle_gun or 0), hours=int(adim.bekle_saat or 0))


async def dizi_adimlari(db: AsyncSession, dizi_id: int) -> List[EpDiziAdimlari]:
    return list((await db.execute(select(EpDiziAdimlari).where(EpDiziAdimlari.dizi_id == dizi_id)
                                  .order_by(EpDiziAdimlari.sira, EpDiziAdimlari.id))).scalars().all())


async def diziye_kaydet(db: AsyncSession, kisi: EpKisiler, liste_id: int, tetikler: Sequence[str]) -> int:
    """Listeye katılım / abonelik onayı → o listeye bağlı aktif dizilere kayıt (bir kez). Commit çağırana."""
    diziler = (await db.execute(select(EpDiziler).where(EpDiziler.liste_id == liste_id, EpDiziler.aktif.is_(True),
                                                        EpDiziler.tetik.in_(list(tetikler))))).scalars().all()
    an = ep.simdi()
    sayi = 0
    for d in diziler:
        if (d.hesap_email or None) != (kisi.hesap_email or None):
            continue
        var = (await db.execute(select(EpDiziKayitlari.id).where(EpDiziKayitlari.dizi_id == d.id, EpDiziKayitlari.kisi_id == kisi.id))).first()
        if var is not None:
            continue
        adimlar = await dizi_adimlari(db, d.id)
        if not adimlar:
            continue
        try:
            async with db.begin_nested():
                db.add(EpDiziKayitlari(dizi_id=d.id, kisi_id=kisi.id, durum="aktif", sonraki_sira=0,
                                       sonraki_at=an + _bekleme(adimlar[0]), baslangic_at=an))
                await db.flush()
            sayi += 1
        except IntegrityError:
            continue
    return sayi


async def _hedefe_ulasti_mi(db: AsyncSession, dizi: EpDiziler, kisi: EpKisiler, kayit: EpDiziKayitlari) -> bool:
    cikis = ep.json_yukle(dizi.cikis, {})
    hedef = cikis.get("hedef") if isinstance(cikis, dict) else None
    if not isinstance(hedef, dict):
        return False
    tur = hedef.get("tur")
    if tur == "tiklama":
        return (await db.execute(select(EpGonderimler.id).where(
            EpGonderimler.dizi_id == dizi.id, EpGonderimler.kisi_id == kisi.id, EpGonderimler.tiklama_at.isnot(None)).limit(1))).first() is not None
    if tur == "etiket":
        return str(hedef.get("deger") or "").lower() in [str(e).lower() for e in ep.json_yukle(kisi.etiketler, [])]
    if tur == "liste":
        return (await db.execute(select(EpListeUyelikleri.id).where(
            EpListeUyelikleri.liste_id == hedef.get("liste_id"), EpListeUyelikleri.kisi_id == kisi.id,
            EpListeUyelikleri.durum == "aktif").limit(1))).first() is not None
    return False


async def dizileri_isle(db: AsyncSession, en_cok: int = 500) -> Dict[str, int]:
    """Zamanı gelen dizi kayıtları: çıkış koşulu → adım iletisi kuyruğa → sonraki adım."""
    an = ep.simdi()
    kayitlar = (await db.execute(select(EpDiziKayitlari).where(EpDiziKayitlari.durum == "aktif", EpDiziKayitlari.sonraki_at <= an)
                                 .order_by(EpDiziKayitlari.sonraki_at, EpDiziKayitlari.id).limit(en_cok))).scalars().all()
    ozet = {"kuyruga": 0, "cikti": 0, "tamamlandi": 0, "ertelendi": 0}
    dizi_onbellek: Dict[int, Optional[EpDiziler]] = {}
    adim_onbellek: Dict[int, List[EpDiziAdimlari]] = {}
    for kayit in kayitlar:
        if kayit.dizi_id not in dizi_onbellek:
            dizi_onbellek[kayit.dizi_id] = (await db.execute(select(EpDiziler).where(EpDiziler.id == kayit.dizi_id))).scalars().first()
            adim_onbellek[kayit.dizi_id] = await dizi_adimlari(db, kayit.dizi_id)
        dizi = dizi_onbellek[kayit.dizi_id]
        if dizi is None:
            kayit.durum, kayit.cikis_nedeni, kayit.bitis_at = "cikti", "dizi_silindi", an
            ozet["cikti"] += 1
            continue
        if not dizi.aktif or not await modul_acik(db, dizi.hesap_email):
            continue
        kisi = (await db.execute(select(EpKisiler).where(EpKisiler.id == kayit.kisi_id))).scalars().first()
        if kisi is None:
            kayit.durum, kayit.cikis_nedeni, kayit.bitis_at = "cikti", "kisi_silindi", an
            ozet["cikti"] += 1
            continue
        kapsam = kisi.kapsam
        bastirilmis = kisi.eposta in await bastirilmis_kume(db, kapsam, [kisi.eposta])
        karar = ep.gonderim_karari(kisi, bastirilmis=bastirilmis, gunluk_sinir=0)
        if karar in ("ret", "bastirildi"):
            kayit.durum, kayit.cikis_nedeni, kayit.bitis_at = "cikti", "ret", an
            ozet["cikti"] += 1
            continue
        if karar in ("izin_yok", "gecersiz_adres"):
            kayit.durum, kayit.cikis_nedeni, kayit.bitis_at = "cikti", "izin_yok", an
            ozet["cikti"] += 1
            continue
        if await _hedefe_ulasti_mi(db, dizi, kisi, kayit):
            kayit.durum, kayit.cikis_nedeni, kayit.bitis_at = "cikti", "hedef", an
            ozet["cikti"] += 1
            continue
        adimlar = adim_onbellek[kayit.dizi_id]
        if kayit.sonraki_sira >= len(adimlar):
            kayit.durum, kayit.bitis_at = "tamamlandi", an
            ozet["tamamlandi"] += 1
            continue
        ayar = await ayar_getir(db, dizi.hesap_email)
        sayi = (await son_24_saat_sayilari(db, kapsam, [kisi.eposta])).get(kisi.eposta, 0)
        sinir = await aylik_sinir(db, dizi.hesap_email)
        kota_dolu = sinir is not None and await aylik_kullanim(db, kapsam) >= sinir
        if ayar.askida or kota_dolu or (ayar.gunluk_kisi_siniri and sayi >= int(ayar.gunluk_kisi_siniri)):
            kayit.sonraki_at = an + timedelta(hours=24 if not kota_dolu else 6)
            ozet["ertelendi"] += 1
            continue
        adim = adimlar[kayit.sonraki_sira]
        try:
            async with db.begin_nested():
                db.add(EpGonderimler(kapsam=kapsam, hesap_email=dizi.hesap_email, dizi_id=dizi.id, adim_id=adim.id,
                                     kisi_id=kisi.id, eposta=kisi.eposta, durum="kuyrukta", created_at=an))
                await db.flush()
            ozet["kuyruga"] += 1
        except IntegrityError:
            pass  # bu adım bu kişiye zaten kuyruğa alınmış
        kayit.sonraki_sira += 1
        if kayit.sonraki_sira >= len(adimlar):
            kayit.durum, kayit.bitis_at = "tamamlandi", an
            ozet["tamamlandi"] += 1
        else:
            kayit.sonraki_at = an + _bekleme(adimlar[kayit.sonraki_sira])
    await db.commit()
    return ozet


async def dizi_iletilerini_gonder(db: AsyncSession, *, en_cok: int, bitis: float, hiz: Optional[AsyncHizSinirlayici] = None,
                                  sonuc: Optional[TurSonucu] = None) -> TurSonucu:
    sonuc = sonuc or TurSonucu()
    onbellek: Dict[int, Optional[Icerik]] = {}

    async def icerik_bul(s: EpGonderimler) -> Optional[Icerik]:
        if s.adim_id not in onbellek:
            adim = (await db.execute(select(EpDiziAdimlari).where(EpDiziAdimlari.id == s.adim_id))).scalars().first()
            dizi = (await db.execute(select(EpDiziler).where(EpDiziler.id == s.dizi_id))).scalars().first()
            onbellek[s.adim_id] = await adim_icerigi(db, dizi, adim) if adim and dizi else None
        return onbellek[s.adim_id]

    kapsamlar = list((await db.execute(
        select(EpGonderimler.kapsam).where(EpGonderimler.durum == "kuyrukta", EpGonderimler.dizi_id.isnot(None)).distinct()
    )).scalars().all())
    gonderilen = 0
    for kapsam in kapsamlar:
        hesap = None if kapsam == ep.AJANS_KAPSAMI else kapsam
        ayar = await ayar_getir(db, hesap)
        if ayar.askida:
            continue
        while gonderilen < en_cok and time.monotonic() < bitis:
            _, satirlar = await _satirlari_al(db, and_(EpGonderimler.kapsam == kapsam, EpGonderimler.dizi_id.isnot(None)),
                                              min(PARCA, en_cok - gonderilen))
            if not satirlar:
                break
            devam = await _parcayi_gonder(db, satirlar, icerik_bul, int(ayar.gunluk_kisi_siniri or 0), hiz, sonuc)
            gonderilen += len(satirlar)
            if not devam:
                return sonuc
    return sonuc


# ---------------------------------------------------------------------------
# Zamanlı görev girişi
# ---------------------------------------------------------------------------
async def zamanli_isle(db: AsyncSession, *, en_cok: int = TUR_EN_COK, sure_sn: float = TUR_SURESI_SN,
                       hiz: Optional[AsyncHizSinirlayici] = None) -> Dict[str, Any]:
    bitis = time.monotonic() + sure_sn
    ozet: Dict[str, Any] = {"yarida_kalan": await _yarida_kalanlar(db)}
    await db.commit()
    ozet["baslatilan"] = await zamanlanmislari_baslat(db)
    ozet["ab_karari"] = await ab_kararlari(db)
    ozet["dizi"] = await dizileri_isle(db)
    sonuc = TurSonucu()
    kampanyalar = (await db.execute(select(EpKampanyalar).where(EpKampanyalar.durum.in_(("gonderiliyor", "ab_test")))
                                    .order_by(EpKampanyalar.baslangic_at, EpKampanyalar.id))).scalars().all()
    for k in kampanyalar:
        if sonuc.durdu or time.monotonic() >= bitis or sonuc.gonderilen >= en_cok:
            break
        await kampanya_gonder(db, k, en_cok=en_cok - sonuc.gonderilen, bitis=bitis, hiz=hiz, sonuc=sonuc)
    if not sonuc.durdu and time.monotonic() < bitis and sonuc.gonderilen < en_cok:
        await dizi_iletilerini_gonder(db, en_cok=en_cok - sonuc.gonderilen, bitis=bitis, hiz=hiz, sonuc=sonuc)
    ozet.update(sonuc.sozluk())
    return ozet


# ---------------------------------------------------------------------------
# Onay (çift onay) ve test e-postası
# ---------------------------------------------------------------------------
async def onay_epostasi_gonder(db: AsyncSession, *, kisi: EpKisiler, liste: EpListeler, ham_jeton: str, dil: str) -> Tuple[Optional[str], Optional[str]]:
    import html as _html

    ayar = await ayar_getir(db, kisi.hesap_email)
    kimlik = await kimlik_getir(db, kisi.hesap_email, ayar)
    gorunen = gorunen_gonderen(kimlik, kisi.hesap_email)
    adres = ep.onay_adresi(ham_jeton)
    ad = f" {kisi.ad}" if kisi.ad else ""
    govde = ep.ileti_metni(dil, "onay_govde", ad=ad, gonderen=gorunen, liste=liste.ad)
    dugme = ep.ileti_metni(dil, "onay_dugme")
    renk = ayar.marka_rengi or ic.VARSAYILAN_RENK
    paragraflar = "".join(f'<p style="margin:0 0 14px 0;">{_html.escape(p).replace(chr(10), "<br>")}</p>' for p in govde.split("\n\n"))
    yon = "rtl" if dil == "ar" else "ltr"
    html = (
        f'<!doctype html><html lang="{dil}" dir="{yon}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:24px 12px;background:#f3f4f6;font-family:{ic.YAZI_TIPI};font-size:16px;line-height:1.6;color:#1f2937;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;">'
        f'<tr><td style="padding:28px 28px 8px 28px;"><h1 style="margin:0 0 14px 0;font-size:22px;">{_html.escape(ep.ileti_metni(dil, "onay_baslik"))}</h1>{paragraflar}'
        f'<p style="margin:18px 0 22px 0;"><a href="{_html.escape(adres, quote=True)}" style="display:inline-block;padding:12px 22px;border-radius:8px;'
        f'background:{renk};color:#fff;font-weight:700;text-decoration:none;">{_html.escape(dugme)}</a></p>'
        f'<p style="margin:0 0 18px 0;font-size:12px;color:#6b7280;word-break:break-all;">{_html.escape(adres)}</p>'
        f'<p style="margin:0 0 20px 0;font-size:12px;color:#6b7280;">{_html.escape(kimlik.satir())}</p></td></tr></table></body></html>'
    )
    metin_ = f"{ep.ileti_metni(dil, 'onay_baslik')}\n\n{govde}\n\n{dugme}: {adres}\n\n--\n{kimlik.satir()}\n"
    ileti = {
        "from": gonderen_alani(kimlik.gonderen_adi), "to": [kisi.eposta],
        "subject": ep.ileti_metni(dil, "onay_konu", liste=liste.ad), "html": html, "text": metin_,
        "tags": [{"name": "ep_onay", "value": str(kisi.id)}],
    }
    if kimlik.yanit_adresi:
        ileti["reply_to"] = kimlik.yanit_adresi
    return await resend_tekil(ileti)


async def test_gonder(db: AsyncSession, *, hesap: Optional[str], konu: str, onizleme: str, bloklar: List[Dict[str, Any]],
                      gonderen_adi: Optional[str], dil: str, adresler: List[str], ornek: Optional[EpKisiler]) -> List[Dict[str, Any]]:
    ayar = await ayar_getir(db, hesap)
    kimlik = await kimlik_getir(db, hesap, ayar)
    dil = ep.dil_sec(dil)
    ab = alt_bilgi(dil, kimlik)
    gonderen = _gonderen_ad(gonderen_adi, hesap) or kimlik.gonderen_adi
    html, baglantilar = ic.html_uret(bloklar, konu=konu, onizleme=onizleme, renk=ayar.marka_rengi or ic.VARSAYILAN_RENK,
                                     logo_url=ayar.logo_url, gonderen_adi=gonderen, dil=dil, alt_bilgi=ab)
    metin_ = ic.metin_uret(bloklar, gonderen_adi=gonderen, alt_bilgi=ab)
    test_adres = f"{ep.site_adresi()}/bulten/tercih/test"
    neden = ep.ileti_metni(dil, "neden_izinli", gonderen=gorunen_gonderen(kimlik, hesap))
    degerler = {"ad": (ornek.ad if ornek else "") or "", "firma": (ornek.firma if ornek else "") or "", "eposta": ornek.eposta if ornek else ""}

    def bag(i: int) -> str:
        return baglantilar[i] if 0 <= i < len(baglantilar) else ep.site_adresi()

    h = ic.kisisellestir(ic.isaretleri_doldur(html, html=True, baglanti=bag, ret=test_adres, tercih=test_adres, neden=neden), degerler, html=True)
    m = ic.kisisellestir(ic.isaretleri_doldur(metin_, html=False, baglanti=bag, ret=test_adres, tercih=test_adres, neden=neden), degerler, html=False)
    sonuc = []
    for adres in adresler:
        ileti = {"from": gonderen_alani(gonderen), "to": [adres],
                 "subject": f"{ep.ileti_metni(dil, 'test_onek')} {ic.konu_kisisellestir(konu, degerler)}", "html": h, "text": m,
                 "tags": [{"name": "ep_test", "value": "1"}]}
        if kimlik.yanit_adresi:
            ileti["reply_to"] = kimlik.yanit_adresi
        kimlik_, hata = await resend_tekil(ileti)
        sonuc.append({"adres": adres, "durum": "gonderildi" if kimlik_ else "hata", "hata": hata})
    return sonuc


# ---------------------------------------------------------------------------
# Teslimat olayları (Resend webhook)
# ---------------------------------------------------------------------------
def _sert_mi(veri: Dict[str, Any]) -> bool:
    b = veri.get("bounce") if isinstance(veri.get("bounce"), dict) else {}
    tur = str(b.get("type") or veri.get("bounce_type") or "").lower()
    return tur in ("permanent", "hard", "hard_bounce")


async def _gonderim_bul(db: AsyncSession, veri: Dict[str, Any]) -> Optional[EpGonderimler]:
    kimlik = str(veri.get("email_id") or veri.get("id") or "").strip()
    if kimlik:
        g = (await db.execute(select(EpGonderimler).where(EpGonderimler.resend_id == kimlik))).scalars().first()
        if g is not None:
            return g
    etiketler = veri.get("tags")
    deger = None
    if isinstance(etiketler, dict):
        deger = etiketler.get("ep")
    elif isinstance(etiketler, list):
        for e in etiketler:
            if isinstance(e, dict) and e.get("name") == "ep":
                deger = e.get("value")
    if deger is not None and str(deger).isdigit():
        return (await db.execute(select(EpGonderimler).where(EpGonderimler.id == int(deger)))).scalars().first()
    return None


async def olay_isle(db: AsyncSession, olay: Dict[str, Any]) -> Dict[str, Any]:
    """Tek Resend olayı. Commit çağırana. Dönen: {"durum": "islendi"|"yoksayildi", ...}."""
    tur = str(olay.get("type") or "")
    veri = olay.get("data") if isinstance(olay.get("data"), dict) else {}
    g = await _gonderim_bul(db, veri)
    if g is None:
        return {"durum": "yoksayildi", "neden": "gonderim_yok"}
    an = ep.simdi()
    kisi = (await db.execute(select(EpKisiler).where(EpKisiler.id == g.kisi_id))).scalars().first() if g.kisi_id else None
    if tur == "email.delivered":
        g.teslim_at = g.teslim_at or an
        if g.durum == "gonderildi":
            g.durum = "teslim"
    elif tur == "email.bounced":
        sert = _sert_mi(veri)
        g.geri_donme_at = g.geri_donme_at or an
        g.geri_donme_turu = "sert" if sert else "yumusak"
        g.durum = "geri_dondu"
        if sert and g.eposta:
            # Sert geri dönüş adres düzeyinde: bütün hesaplarda bastır (gönderen itibarı ortak).
            await bastirmaya_ekle(db, ep.GENEL_KAPSAM, g.eposta, "sert_geri_donme", f"gonderim:{g.id}")
        await askiya_alma_denetimi(db, g.kapsam)
    elif tur == "email.complained":
        g.sikayet_at = g.sikayet_at or an
        g.durum = "sikayet"
        if kisi is not None:
            await ret_et(db, kisi, "sikayet")
        elif g.eposta:
            await bastirmaya_ekle(db, g.kapsam, g.eposta, "sikayet", f"gonderim:{g.id}")
        await askiya_alma_denetimi(db, g.kapsam)
    elif tur in ("email.opened", "email.clicked"):
        # Takip kapalıysa (Resend'in alan adı takibi açık olsa bile) kaydedilmez.
        k = (await db.execute(select(EpKampanyalar).where(EpKampanyalar.id == g.kampanya_id))).scalars().first() if g.kampanya_id else None
        if k is not None:
            izinli = bool(k.takip_acilma if tur == "email.opened" else k.takip_tiklama)
        else:
            ayar = await ayar_getir(db, g.hesap_email)
            izinli = bool(ayar.acilma_takibi if tur == "email.opened" else ayar.tiklama_takibi)
        if not izinli:
            return {"durum": "yoksayildi", "neden": "takip_kapali"}
        etkilesim_yaz(g, kisi, tiklama=tur == "email.clicked")
    else:
        return {"durum": "yoksayildi", "neden": "olay_turu"}
    return {"durum": "islendi", "gonderim_id": g.id}


def etkilesim_yaz(g: EpGonderimler, kisi: Optional[EpKisiler], tiklama: bool) -> None:
    an = ep.simdi()
    g.acilma_at = g.acilma_at or an  # tıklayan açmıştır
    if tiklama:
        g.tiklama_at = g.tiklama_at or an
    if kisi is not None:
        kisi.son_etkilesim_at = an


async def askiya_alma_denetimi(db: AsyncSession, kapsam: str) -> Optional[str]:
    """Son 30 gün: şikâyet > %0,3 ya da sert geri dönüş > %5 (≥ 50 ileti) → hesap askıya. Commit çağırana."""
    sinir = ep.simdi() - timedelta(days=30)
    satir = (await db.execute(
        select(
            func.count(EpGonderimler.gonderim_at),
            func.count(EpGonderimler.sikayet_at),
            func.sum(case((EpGonderimler.geri_donme_turu == "sert", 1), else_=0)),
        ).where(EpGonderimler.kapsam == kapsam, EpGonderimler.gonderim_at >= sinir)
    )).one()
    gonderilen, sikayet, sert = int(satir[0] or 0), int(satir[1] or 0), int(satir[2] or 0)
    if gonderilen < ep.ESIK_HACIM:
        return None
    neden = None
    if sikayet / gonderilen > ep.SIKAYET_ESIGI:
        neden = "sikayet_orani"
    elif sert / gonderilen > ep.GERI_DONME_ESIGI:
        neden = "geri_donme_orani"
    if neden is None:
        return None
    hesap = None if kapsam == ep.AJANS_KAPSAMI else kapsam
    ayar = await ayar_getir(db, hesap)
    if ayar.askida:
        return None
    ayar.askida, ayar.askida_neden, ayar.askida_at = True, neden, ep.simdi()
    await db.execute(update(EpKampanyalar).where(
        (EpKampanyalar.hesap_email.is_(None) if hesap is None else EpKampanyalar.hesap_email == hesap),
        EpKampanyalar.durum.in_(("gonderiliyor", "ab_test", "zamanlandi")),
    ).values(durum="duraklatildi", duraklatma_nedeni="hesap_askida").execution_options(synchronize_session=False))
    await _askiya_bildir(db, hesap, neden, gonderilen, sikayet, sert)
    return neden


async def _askiya_bildir(db: AsyncSession, hesap: Optional[str], neden: str, gonderilen: int, sikayet: int, sert: int) -> None:
    try:
        from services import notify

        alicilar = await notify.admin_recipients(db)
        if hesap:
            alicilar = alicilar + [{"email": hesap, "role": "client"}]
        baslik = "E-posta pazarlama gönderimleri askıya alındı"
        govde = (f"Hesap: {hesap or 'ajans'} · neden: {neden} · son 30 gün: {gonderilen} ileti, {sikayet} şikâyet, "
                 f"{sert} sert geri dönüş. Kampanyalar duraklatıldı; liste temizliği sonrası yönetici askıyı kaldırabilir.")
        await notify.dispatch(db, event_type="pazarlama_askiya_alindi", title=baslik, body=govde, recipients=alicilar,
                              link="/client?sekme=epostaPazarlama" if hesap else "/admin?sekme=epostaPazarlama")
    except Exception:  # noqa: BLE001 - bildirim askıyı bozmasın
        logger.exception("Askıya alma bildirimi gönderilemedi")


__all__ = [
    "sahte_mod", "resend_kurulu", "sahte_kutu", "sahte_kutuyu_temizle", "AsyncHizSinirlayici", "resend_toplu", "resend_tekil",
    "ayar_getir", "kimlik_getir", "bastirilmis_kume", "bastirmaya_ekle", "ret_et", "kitle", "kitle_ozeti",
    "kampanyayi_baslat", "kampanya_gonder", "kampanya_istatistik", "ab_kararlari", "dizileri_isle", "diziye_kaydet",
    "zamanli_isle", "onay_epostasi_gonder", "test_gonder", "olay_isle", "etkilesim_yaz", "askiya_alma_denetimi",
]
