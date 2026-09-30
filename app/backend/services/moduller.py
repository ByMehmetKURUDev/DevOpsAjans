"""Müşteri başına modül durumu: hesaplama, açma/kapama, özet.

Öncelik kuralı
--------------
Her müşteri × modül için "açık mı?" şu sırayla belirleniyor:

1. **elle** — `workspace_modules` satırında `acik` dolu ise o.
2. **paket** — müşterinin paketi (bkz. `musteri_paketi`) modülün
   `paketler` listesindeyse açık.
3. **varsayilan** — manifestteki `varsayilan_acik`.

Çekirdek modüller her zaman açık (satır ne derse desin). Yalnız yönetici
modülleri müşteri başına değişmiyor. Sonra bağımlılıklar uygulanıyor: bir
bağımlılığı kapalı olan modül de kapalı sayılıyor (`engelleyen` listesiyle).
Bu durum ancak paket sonradan değişirse oluşabiliyor; elle açma/kapama
bağımlılık kuralına takılıyor (409).

Paket kaynağı
-------------
`service_subscriptions` ölçek bilgisi taşımıyor (yalnız hizmet türü), bu
yüzden en güvenilir kaynak müşterinin fiyat teklifleri: `pricing_inquiries`
içinde müşterinin KABUL ettiği (1E) ya da faturası ÖDENMİŞ en son teklifin
`scale_kod`u. Hiçbiri yoksa paket yok → yalnız `varsayilan_acik`.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core import moduller as manifest
from core.moduller import Modul
from models.workspace_modules import WorkspaceModules
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

KAYNAKLAR = ("varsayilan", "paket", "elle")
PANEL_BAGLANTISI = "/client?sekme=profile"


class ModulHatasi(Exception):
    """Uca çevrilecek hata: HTTP durumu, kod ve (varsa) ilgili modüller."""

    def __init__(self, durum: int, kod: str, moduller: Optional[List[str]] = None, alan: Optional[str] = None):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.moduller = moduller or []
        self.alan = alan

    def detay(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"kod": self.kod}
        if self.moduller:
            d["moduller"] = self.moduller
        if self.alan:
            d["alan"] = self.alan
        return d


@dataclass
class ModulDurumu:
    modul: Modul
    #: Bağımlılıklar dahil, geçerli durum (bekçi bunu kullanıyor).
    acik: bool
    #: varsayilan | paket | elle
    kaynak: str
    #: Bağımlılıklar hesaba katılmadan.
    acik_ham: bool
    #: Açık olması gerekirken kapalı sayılmasına yol açan bağımlılıklar.
    engelleyen: List[str] = field(default_factory=list)
    ayarlar: Dict[str, Any] = field(default_factory=dict)
    #: Satırdaki elle değer (yoksa None).
    elle: Optional[bool] = None
    #: Paket/varsayılana göre olacak değer (elle satır olmasaydı).
    varsayilan_deger: bool = False

    @property
    def gorunum(self) -> str:
        """Müşteri kartı: acik | yakinda | eklenebilir."""
        if self.modul.durum == "yakinda":
            return "yakinda"
        return "acik" if self.acik else "eklenebilir"


@dataclass
class MusteriModulleri:
    eposta: str
    paket: Optional[str]
    durumlar: Dict[str, ModulDurumu]

    def sirali(self, yalniz_musteri: bool = False) -> List[ModulDurumu]:
        return [
            self.durumlar[m.anahtar]
            for m in manifest.MODULLER
            if m.anahtar in self.durumlar and (not yalniz_musteri or m.musteriye_gorunur)
        ]


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------


def _ayar_oku(modul: Modul, ham: Optional[str]) -> Dict[str, Any]:
    """Varsayılanlar + kayıtlı geçerli değerler (bozuk/eski alanlar atlanır)."""
    sonuc = modul.varsayilan_ayarlar()
    if not ham:
        return sonuc
    try:
        kayitli = json.loads(ham)
    except (TypeError, ValueError):
        return sonuc
    if not isinstance(kayitli, dict):
        return sonuc
    for alan in modul.ayarlar:
        if alan.anahtar in kayitli:
            try:
                sonuc[alan.anahtar] = alan.dogrula(kayitli[alan.anahtar])
            except ValueError:
                pass
    return sonuc


def ayarlari_dogrula(modul: Modul, ham: Any) -> Dict[str, Any]:
    """Gönderilen ayarları doğrular; bilinmeyen ya da geçersiz alan 400."""
    if not isinstance(ham, dict):
        raise ModulHatasi(400, "gecersiz_ayar")
    tanimlar = {a.anahtar: a for a in modul.ayarlar}
    temiz: Dict[str, Any] = {}
    for anahtar, deger in ham.items():
        tanim = tanimlar.get(anahtar)
        if tanim is None:
            raise ModulHatasi(400, "bilinmeyen_ayar", alan=str(anahtar)[:64])
        try:
            temiz[anahtar] = tanim.dogrula(deger)
        except ValueError:
            raise ModulHatasi(400, "gecersiz_ayar", alan=anahtar)
    return temiz


# ---------------------------------------------------------------------------
# Hesaplama (saf)
# ---------------------------------------------------------------------------


def durumlari_hesapla(
    paket: Optional[str], satirlar: Dict[str, WorkspaceModules]
) -> Dict[str, ModulDurumu]:
    """Paket + satırlardan bütün modüllerin durumu (veritabanına dokunmaz)."""
    paket = (paket or "").upper() or None
    durumlar: Dict[str, ModulDurumu] = {}
    for m in manifest.sirali():  # bağımlılıklar önce
        satir = satirlar.get(m.anahtar) if m.musteriye_gorunur else None
        if m.paketler and paket and paket in m.paketler and not m.varsayilan_acik:
            varsayilan_deger, kaynak = True, "paket"
        else:
            varsayilan_deger, kaynak = m.varsayilan_acik, "varsayilan"

        elle = satir.acik if satir is not None else None
        if m.cekirdek or not m.musteriye_gorunur:
            # Çekirdek kapatılamaz; yönetici modülü müşteri başına değişmez.
            acik_ham = True if m.cekirdek else m.varsayilan_acik
            elle = None
        elif elle is not None:
            acik_ham, kaynak = bool(elle), "elle"
        else:
            acik_ham = varsayilan_deger

        engelleyen = [
            b for b in m.bagimliliklar if b in durumlar and not durumlar[b].acik
        ] if acik_ham else []
        durumlar[m.anahtar] = ModulDurumu(
            modul=m,
            acik=acik_ham and not engelleyen,
            kaynak=kaynak,
            acik_ham=acik_ham,
            engelleyen=engelleyen,
            ayarlar=_ayar_oku(m, satir.ayarlar_json if satir is not None else None),
            elle=elle,
            varsayilan_deger=True if m.cekirdek else varsayilan_deger,
        )
    return durumlar


# ---------------------------------------------------------------------------
# Veritabanı
# ---------------------------------------------------------------------------


def _paket_sorgusu():
    from models.invoices import Invoices
    from models.pricing import Pricing_inquiries

    odenmis = select(Invoices.id).where(func.lower(Invoices.status) == "paid")
    return (
        select(Pricing_inquiries.musteri_eposta, Pricing_inquiries.scale_kod)
        .where(Pricing_inquiries.scale_kod.isnot(None))
        .where(or_(Pricing_inquiries.durum == "kabul", Pricing_inquiries.invoice_id.in_(odenmis)))
        .order_by(
            func.coalesce(Pricing_inquiries.durum_at, Pricing_inquiries.created_at).desc(),
            Pricing_inquiries.id.desc(),
        )
    )


def _paket_duzelt(kod: Any) -> Optional[str]:
    kod = str(kod or "").strip().upper()
    return kod if kod in manifest.PAKETLER else None


async def musteri_paketi(db: AsyncSession, eposta: str) -> Optional[str]:
    """Müşterinin son kabul ettiği / ödediği fiyat teklifinin ölçeği."""
    from models.pricing import Pricing_inquiries

    try:
        sonuc = await db.execute(
            _paket_sorgusu().where(func.lower(Pricing_inquiries.musteri_eposta) == eposta_duzelt(eposta)).limit(5)
        )
    except Exception:  # noqa: BLE001 - tablo yoksa paket de yok
        logger.exception("Müşteri paketi okunamadı")
        return None
    for _, kod in sonuc.all():
        paket = _paket_duzelt(kod)
        if paket:
            return paket
    return None


async def _satirlar(db: AsyncSession, eposta: str) -> Dict[str, WorkspaceModules]:
    sonuc = await db.execute(select(WorkspaceModules).where(WorkspaceModules.musteri_eposta == eposta))
    return {s.modul_anahtari: s for s in sonuc.scalars().all()}


async def musteri_modulleri(db: AsyncSession, eposta: str) -> MusteriModulleri:
    """Bir müşterinin bütün modülleri: geçerli durum + kaynak + ayarlar."""
    eposta = eposta_duzelt(eposta)
    paket = await musteri_paketi(db, eposta)
    satirlar = await _satirlar(db, eposta)
    return MusteriModulleri(eposta=eposta, paket=paket, durumlar=durumlari_hesapla(paket, satirlar))


async def musteri_ayari(db: AsyncSession, eposta: str, anahtar: str, alan: str) -> Any:
    """Müşterinin bir modül ayarı (kayıtlı değer ya da manifest varsayılanı).

    Modüllerin davranışı bu değeri okuyor (ör. kredi eşiği, günlük analiz
    sınırı). Tek satır okunuyor; bilinmeyen modül/alan ya da okuma hatası
    None döndürür — çağıran kendi varsayılanına düşer.
    """
    m = manifest.modul(anahtar)
    if m is None or alan not in {a.anahtar for a in m.ayarlar}:
        return None
    try:
        satir = (
            await db.execute(
                select(WorkspaceModules)
                .where(WorkspaceModules.musteri_eposta == eposta_duzelt(eposta))
                .where(WorkspaceModules.modul_anahtari == anahtar)
            )
        ).scalars().first()
    except Exception:  # noqa: BLE001
        return m.varsayilan_ayarlar().get(alan)
    return _ayar_oku(m, satir.ayarlar_json if satir is not None else None).get(alan)


async def modul_acik_mi(db: AsyncSession, eposta: str, anahtar: str) -> bool:
    m = manifest.modul(anahtar)
    if m is None:
        return False
    if m.cekirdek:
        return True
    durumlar = await musteri_modulleri(db, eposta)
    d = durumlar.durumlar.get(anahtar)
    return bool(d and d.acik)


@dataclass
class Degisiklik:
    onceki: MusteriModulleri
    sonraki: MusteriModulleri
    anahtar: str

    @property
    def durum_degisti(self) -> bool:
        return self.onceki.durumlar[self.anahtar].acik != self.sonraki.durumlar[self.anahtar].acik

    def degisen_moduller(self) -> List[Tuple[str, bool]]:
        """Geçerli durumu değişen bütün modüller (bağımlılık etkisi dahil)."""
        sonuc = []
        for k, d in self.sonraki.durumlar.items():
            o = self.onceki.durumlar.get(k)
            if o is not None and o.acik != d.acik and d.modul.musteriye_gorunur:
                sonuc.append((k, d.acik))
        return sonuc


def _yeni_deger_denetle(onceki: MusteriModulleri, anahtar: str, yeni_acik: bool) -> None:
    """Bağımlılık kuralları: açarken bağımlılıklar, kapatırken bağımlılar."""
    m = manifest.MODUL_SOZLUGU[anahtar]
    if yeni_acik:
        kapali = [b for b in m.bagimliliklar if not onceki.durumlar[b].acik]
        if kapali:
            raise ModulHatasi(409, "bagimlilik_kapali", kapali)
    else:
        acik_bagimlilar = [
            b.anahtar for b in manifest.bagimli_olanlar(anahtar)
            if b.musteriye_gorunur and onceki.durumlar[b.anahtar].acik
        ]
        if acik_bagimlilar:
            raise ModulHatasi(409, "bagimli_acik", acik_bagimlilar)


async def modul_ayarla(
    db: AsyncSession,
    eposta: str,
    anahtar: str,
    *,
    acik: Optional[bool] = None,
    ayarlar: Optional[Dict[str, Any]] = None,
    varsayilana_don: bool = False,
    yonetici: Optional[str] = None,
) -> Degisiklik:
    """Bir müşteride bir modülü açar/kapatır, ayarlarını yazar ya da varsayılana döndürür."""
    eposta = eposta_duzelt(eposta)
    m = manifest.modul(anahtar)
    if m is None:
        raise ModulHatasi(404, "modul_yok")
    if not m.musteriye_gorunur:
        raise ModulHatasi(400, "yalniz_yonetici_modulu")
    if acik is False and m.cekirdek:
        raise ModulHatasi(400, "cekirdek_kapatilamaz")
    if acik is None and ayarlar is None and not varsayilana_don:
        raise ModulHatasi(400, "degisiklik_yok")
    temiz_ayarlar = ayarlari_dogrula(m, ayarlar) if ayarlar is not None else None

    onceki = await musteri_modulleri(db, eposta)
    simdiki = onceki.durumlar[anahtar]
    mevcut_satir = (await _satirlar(db, eposta)).get(anahtar)
    if temiz_ayarlar is None and (m.cekirdek or (varsayilana_don and mevcut_satir is None)):
        # Çekirdeği "aç" ya da satırı olmayanı "varsayılana döndür": yazılacak bir şey yok.
        return Degisiklik(onceki=onceki, sonraki=onceki, anahtar=anahtar)

    # Değişiklikten sonra geçerli olacak ham değer; bağımlılık kuralı buna göre.
    if m.cekirdek:
        hedef = True
    elif varsayilana_don:
        hedef = simdiki.varsayilan_deger
    elif acik is not None:
        hedef = acik
    else:
        hedef = simdiki.acik_ham
    if hedef != simdiki.acik:
        _yeni_deger_denetle(onceki, anahtar, hedef)
    elif hedef and simdiki.engelleyen:
        # Açık kalması istenen ama bağımlılığı kapalı olduğu için kapalı sayılan modül.
        _yeni_deger_denetle(onceki, anahtar, True)

    for deneme in range(2):
        satir = (await _satirlar(db, eposta)).get(anahtar)
        if satir is None:
            satir = WorkspaceModules(musteri_eposta=eposta, modul_anahtari=anahtar)
            db.add(satir)
        simdi = _simdi()
        if varsayilana_don:
            satir.acik = None
        elif acik is not None and not m.cekirdek:
            if satir.acik is not acik:
                if acik:
                    satir.acilis_at = simdi
                else:
                    satir.kapanis_at = simdi
            satir.acik = bool(acik)
        if temiz_ayarlar is not None:
            birlesik = _ayar_oku(m, satir.ayarlar_json)
            birlesik.update(temiz_ayarlar)
            # Yalnız varsayılandan farklı olanlar saklanıyor.
            farkli = {k: v for k, v in birlesik.items() if m.varsayilan_ayarlar().get(k) != v}
            satir.ayarlar_json = json.dumps(farkli, ensure_ascii=False) if farkli else None
        satir.acan_eposta = eposta_duzelt(yonetici) or None
        try:
            await db.commit()
            break
        except IntegrityError:
            # Aynı anda iki istek satırı yaratmaya çalıştı: yeniden oku, güncelle.
            await db.rollback()
            if deneme:
                raise

    sonraki = await musteri_modulleri(db, eposta)
    return Degisiklik(onceki=onceki, sonraki=sonraki, anahtar=anahtar)


async def degisiklikleri_bildir(db: AsyncSession, degisiklik: Degisiklik) -> None:
    """Geçerli durumu değişen her modül için müşteriye bildirim (hata yutar)."""
    try:
        from services.notify import dispatch, render
    except Exception:  # noqa: BLE001
        return
    for anahtar, acik in degisiklik.degisen_moduller():
        m = manifest.MODUL_SOZLUGU[anahtar]
        ad_tr, ad_en = m.ad_varsayilan["tr"], m.ad_varsayilan["en"]
        olay = "modul_acildi" if acik else "modul_kapandi"
        if acik:
            varsayilan_baslik = f"Yeni modül açıldı: {ad_tr} / Module enabled: {ad_en}"
            varsayilan_govde = (
                f"Panelinizde \"{ad_tr}\" modülü açıldı. Müşteri panelinizden kullanabilirsiniz.\n\n"
                f"The \"{ad_en}\" module is now enabled in your client panel."
            )
        else:
            varsayilan_baslik = f"Modül kapatıldı: {ad_tr} / Module disabled: {ad_en}"
            varsayilan_govde = (
                f"Panelinizdeki \"{ad_tr}\" modülü kapatıldı. Yeniden açmak için bizimle iletişime geçebilirsiniz.\n\n"
                f"The \"{ad_en}\" module has been disabled in your client panel. Contact us to enable it again."
            )
        try:
            baslik, govde = await render(
                db, olay, varsayilan_baslik, varsayilan_govde, {"modul": ad_tr, "modul_en": ad_en}
            )
            await dispatch(
                db,
                event_type=olay,
                title=baslik,
                body=govde,
                recipients=[{"email": degisiklik.sonraki.eposta, "role": "client"}],
                link=PANEL_BAGLANTISI,
                ref_type="workspace_module",
            )
        except Exception:  # noqa: BLE001 - bildirim asıl işi bozmamalı
            logger.exception("Modül bildirimi gönderilemedi")


# ---------------------------------------------------------------------------
# Yönetici: müşteri listesi ve özet
# ---------------------------------------------------------------------------


async def musteri_listesi(db: AsyncSession) -> List[Dict[str, Optional[str]]]:
    """Modül yönetilebilecek müşteriler: kullanıcılar + kayıtlarda geçen adresler."""
    from models.auth import User
    from models.invoices import Invoices
    from models.projects import Projects
    from models.support_tickets import Support_tickets

    adlar: Dict[str, Optional[str]] = {}
    yoneticiler: set = set()

    async def ekle(sorgu) -> None:
        try:
            for eposta, ad in (await db.execute(sorgu)).all():
                e = eposta_duzelt(eposta)
                if e and "@" in e:
                    if not adlar.get(e):
                        adlar[e] = (ad or None)
        except Exception:  # noqa: BLE001
            logger.exception("Müşteri listesi kaynağı okunamadı")

    try:
        for eposta, rol in (await db.execute(select(User.email, User.role))).all():
            if rol == "admin":
                yoneticiler.add(eposta_duzelt(eposta))
    except Exception:  # noqa: BLE001
        logger.exception("Kullanıcılar okunamadı")

    await ekle(select(User.email, User.name).where(User.role != "admin"))
    await ekle(select(Projects.client_email, Projects.client_name).where(Projects.client_email.isnot(None)))
    await ekle(select(Invoices.client_email, Invoices.client_name).where(Invoices.client_email.isnot(None)))
    await ekle(
        select(Support_tickets.client_email, Support_tickets.client_name).where(
            Support_tickets.client_email.isnot(None)
        )
    )
    try:
        for (eposta,) in (await db.execute(select(WorkspaceModules.musteri_eposta).distinct())).all():
            e = eposta_duzelt(eposta)
            if e and e not in adlar:
                adlar[e] = None
    except Exception:  # noqa: BLE001
        logger.exception("Modül satırları okunamadı")

    return [
        {"eposta": e, "ad": adlar[e]}
        for e in sorted(adlar)
        if e not in yoneticiler
    ]


async def toplu_durumlar(db: AsyncSession, epostalar: Iterable[str]) -> Dict[str, MusteriModulleri]:
    """Birçok müşterinin durumu, iki sorguyla."""
    epostalar = sorted({eposta_duzelt(e) for e in epostalar if eposta_duzelt(e)})
    if not epostalar:
        return {}
    paketler: Dict[str, Optional[str]] = {}
    try:
        for eposta, kod in (await db.execute(_paket_sorgusu())).all():
            # Sorgu en yeniden eskiye sıralı: ilk geçerli ölçek geçerli paket.
            e, paket = eposta_duzelt(eposta), _paket_duzelt(kod)
            if paket and e not in paketler:
                paketler[e] = paket
    except Exception:  # noqa: BLE001
        logger.exception("Paketler okunamadı")
    satirlar: Dict[str, Dict[str, WorkspaceModules]] = {}
    for s in (await db.execute(select(WorkspaceModules))).scalars().all():
        satirlar.setdefault(eposta_duzelt(s.musteri_eposta), {})[s.modul_anahtari] = s
    return {
        e: MusteriModulleri(eposta=e, paket=paketler.get(e), durumlar=durumlari_hesapla(paketler.get(e), satirlar.get(e, {})))
        for e in epostalar
    }


async def ozet(db: AsyncSession) -> Dict[str, Any]:
    """Modül başına açık müşteri sayısı."""
    musteriler = await musteri_listesi(db)
    durumlar = await toplu_durumlar(db, [m["eposta"] for m in musteriler])
    toplam = len(durumlar)
    satirlar = []
    for m in manifest.MODULLER:
        if not m.musteriye_gorunur:
            satirlar.append({"anahtar": m.anahtar, "acik_musteri": None, "elle_acik": None, "elle_kapali": None})
            continue
        acik = sum(1 for d in durumlar.values() if d.durumlar[m.anahtar].acik)
        elle_acik = sum(1 for d in durumlar.values() if d.durumlar[m.anahtar].elle is True)
        elle_kapali = sum(1 for d in durumlar.values() if d.durumlar[m.anahtar].elle is False)
        satirlar.append({"anahtar": m.anahtar, "acik_musteri": acik, "elle_acik": elle_acik, "elle_kapali": elle_kapali})
    return {"toplam_musteri": toplam, "moduller": satirlar}
