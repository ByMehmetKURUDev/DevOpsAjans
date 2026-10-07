"""Faz 6Q — saha servisi malzemeleri ↔ Stok ve POS (Faz 6P) köprüsü.

Kural
-----
* Bağlantı AÇIK: hesapta `stok_pos` modülü açık VE saha ayarında "kullanılan malzemeleri stoktan düş"
  (`saha_ayarlari.stoktan_dus`, varsayılan KAPALI) açık. Kapalıyken saha eskisi gibi çalışır.
* İş emrine malzeme eklerken stok ürünü aranır (ad / barkod / SKU) ve satır ürüne bağlanır
  (`saha_malzeme_kullanimi.stok_urun_id`); serbest metin ve saha kataloğu malzemesi yine mümkün.
  Miktar ürünün biriminde (adet/paket tam sayı; `stok_miktar` binde bir). Fiyat: stoktaki satış fiyatı
  KDV DAHİL → saha formundaki birim fiyat KDV HARİÇ (`satış × 100 / (100 + KDV)`, yarım yukarı).
  Teknisyen ürün listesini görür, MALİYETİ (alış fiyatı) hiçbir saha ucunda görmez.
* Düşüm iş emri TAMAMLANINCA, durum geçişiyle AYNI işlemde: bağlı ve henüz düşülmemiş her satır için
  koşullu güncelleme (`stok_dusum_at IS NULL` → şimdi) — yalnız kazanan istek düşer, aynı iş emri için iki
  kez düşülmez. Hareket `cikis`, belge no = iş emri no, kaynak "saha", kaynak_id = iş emri, birim maliyet =
  o anki alış fiyatı (saha tüketimi raporunun maliyeti). Sahada kullanılan malzeme GERÇEKTİR: stok eksiye
  düşebilir (eksi stok ayarından bağımsız; hareketin açıklamasına "stok eksiye düştü" izi yazılır) —
  teknisyen envanter yüzünden işi bitiremez hâle gelmesin.
* Konum: işi bitiren kişi o işe atanmış ve araç/depo konumu tanımlı bir teknisyense onunki; değilse atanmış
  teknisyenlerden konumu olan ilki; o da yoksa saha ayarındaki konum; o da yoksa stoktaki varsayılan konum.
  Pasif konum atlanır. Satıra düşüldüğü konum yazılır (geri alma aynı konuma).
* Yeniden açma (`tamamlandi → iste`) ya da düşülmüş satırın silinmesi: ters hareket (`iade`, kaynak "saha"),
  `stok_dusum_at` boşalır (koşullu — iki kez geri alınmaz). Ayar sonradan kapatılmış olsa da geri alma
  yapılır (stok tutarlı kalsın).
* Kritik stok olayı (`stok.kritik`) ve QR menü eşitlemesi commit SONRASI `stok_kayit.gecisleri_isle` ile —
  POS satışındaki altyapının aynısı.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from models.saha_servisi import SahaAyarlari, SahaIsAtamalari, SahaIsEmirleri, SahaMalzemeKullanimi, SahaTeknisyenleri
from models.stok_pos import StokKonumlari, StokSeviyeleri, StokUrunleri
from services import saha_servisi as s
from services import stok_kayit as stk
from services import stok_pos as sp
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

STOK_MODUL = sp.MODUL
EKSI_NOTU = "stok eksiye düştü"


async def stok_modulu_acik(db: AsyncSession, hesap: str) -> bool:
    from services.moduller import modul_acik_mi

    return bool(await modul_acik_mi(db, hesap, STOK_MODUL))


async def baglanti_acik(db: AsyncSession, hesap: str, a: SahaAyarlari) -> bool:
    """Stoktan düşüm etkin mi: ayar açık VE Stok ve POS modülü açık."""
    return bool(a.stoktan_dus) and await stok_modulu_acik(db, hesap)


async def konumlar(db: AsyncSession, hesap: str) -> List[StokKonumlari]:
    """Hesabın AKTİF stok konumları (yazmadan — yoksa boş liste)."""
    return list((await db.execute(select(StokKonumlari).where(StokKonumlari.hesap_email == hesap, StokKonumlari.aktif.is_(True))
                                  .order_by(StokKonumlari.sira, StokKonumlari.id))).scalars().all())


def konum_sozlugu(k: StokKonumlari) -> Dict[str, Any]:
    return {"id": k.id, "ad": k.ad, "varsayilan": bool(k.varsayilan)}


async def konum_dogrula(db: AsyncSession, hesap: str, ham: Any, alan: str = "stok_konum_id") -> Optional[int]:
    """Boş → None; değilse hesabın aktif stok konumu olmalı (404 `stok_konum_yok`)."""
    if ham in (None, ""):
        return None
    kimlik = s.tam_sayi(ham, alan, 1, 2_000_000_000)
    if kimlik not in {k.id for k in await konumlar(db, hesap)}:
        raise s.SahaHatasi("stok_konum_yok", alan, durum=404)
    return kimlik


async def _varsayilan_konum_id(db: AsyncSession, hesap: str) -> int:
    """Stoktaki varsayılan konum; hiç konum yoksa "Merkez" açılır — commit ETMEDEN (çağıranın işleminde)."""
    liste = await konumlar(db, hesap)
    for k in liste:
        if k.varsayilan:
            return k.id
    if liste:
        return liste[0].id
    k = StokKonumlari(hesap_email=hesap, ad="Merkez", varsayilan=True, aktif=True, created_at=sp.simdi())
    try:
        async with db.begin_nested():
            db.add(k)
    except IntegrityError:  # pragma: no cover - konum tablosunda benzersiz kısıt yok; savunma
        pass
    await db.flush()
    return k.id


def birim_fiyat(u: StokUrunleri) -> int:
    """Stok satış fiyatı (KDV dahil) → saha formu birim fiyatı (KDV hariç, kuruş)."""
    return sp.yuvarla(int(u.satis_fiyati or 0), 100, 100 + int(u.kdv_orani or 0))


async def teknisyen_konumu(db: AsyncSession, hesap: str, kisi: str) -> Optional[int]:
    t = (await db.execute(select(SahaTeknisyenleri).where(SahaTeknisyenleri.hesap_email == hesap,
                                                          SahaTeknisyenleri.eposta == kisi))).scalars().first()
    return t.stok_konum_id if t is not None else None


async def dusum_konumu(db: AsyncSession, ie: SahaIsEmirleri, kisi: str, a: SahaAyarlari) -> int:
    """Düşülecek konum: bitiren teknisyen → atanmış teknisyenlerden ilki → saha ayarı → stoktaki varsayılan."""
    aktif = {k.id for k in await konumlar(db, ie.hesap_email)}
    atanan = (await db.execute(select(SahaTeknisyenleri).join(SahaIsAtamalari, SahaIsAtamalari.teknisyen_id == SahaTeknisyenleri.id)
                               .where(SahaIsAtamalari.is_emri_id == ie.id).order_by(SahaIsAtamalari.id))).scalars().all()
    adaylar = [t.stok_konum_id for t in atanan if t.eposta == kisi]
    adaylar += [t.stok_konum_id for t in atanan]
    adaylar.append(a.stok_konum_id)
    for kimlik in adaylar:
        if kimlik and kimlik in aktif:
            return kimlik
    return await _varsayilan_konum_id(db, ie.hesap_email)


# ---------------------------------------------------------------------------
# Ürün arama (saha ekranı; maliyet YOK)
# ---------------------------------------------------------------------------
def urun_sozlugu(u: StokUrunleri, seviye: Dict[int, int], konum_id: Optional[int]) -> Dict[str, Any]:
    """Saha ekranı için stok ürünü — alış fiyatı (maliyet) bilerek YOK."""
    toplam = sum(seviye.values())
    burada = seviye.get(konum_id, 0) if konum_id else toplam
    return {
        "id": u.id, "ad": u.ad, "barkod": u.barkod, "sku": u.sku, "birim": u.birim, "kdv_orani": u.kdv_orani,
        "birim_fiyat": birim_fiyat(u), "stok_takibi": bool(u.stok_takibi),
        "stok": sp.miktar_yaz(burada) if u.stok_takibi else None,
        "stok_toplam": sp.miktar_yaz(toplam) if u.stok_takibi else None,
        "kritik": bool(u.stok_takibi and u.kritik_esik is not None and toplam <= u.kritik_esik),
    }


async def urun_ara(db: AsyncSession, hesap: str, ara: Optional[str], konum_id: Optional[int], limit: int = 30) -> List[Dict[str, Any]]:
    kosul = [StokUrunleri.hesap_email == hesap, StokUrunleri.aktif.is_(True)]
    a = (ara or "").strip()
    if a:
        # SQLite `lower` yalnız ASCII: yazıldığı gibi de aranır (Çay / çay) — 6P ürün listesinin deseni.
        kosul.append(or_(StokUrunleri.ad.contains(a), func.lower(StokUrunleri.ad).contains(a.lower()),
                         StokUrunleri.barkod.startswith(a), StokUrunleri.sku.startswith(a)))
    liste = (await db.execute(select(StokUrunleri).where(*kosul).order_by(StokUrunleri.ad, StokUrunleri.id).limit(limit))).scalars().all()
    sev = await stk.seviyeler(db, [u.id for u in liste])
    return [urun_sozlugu(u, sev.get(u.id, {}), konum_id) for u in liste]


async def urun_bul(db: AsyncSession, hesap: str, ham: Any) -> StokUrunleri:
    kimlik = s.tam_sayi(ham, "stok_urun_id", 1, 2_000_000_000)
    u = (await db.execute(select(StokUrunleri).where(StokUrunleri.id == kimlik, StokUrunleri.hesap_email == hesap))).scalars().first()
    if u is None or not u.aktif:
        raise s.SahaHatasi("stok_urun_yok", "stok_urun_id", durum=404)
    return u


async def kullanim_satiri(db: AsyncSession, ie: SahaIsEmirleri, g: Dict[str, Any], kisi: str) -> SahaMalzemeKullanimi:
    """Stok ürününe bağlı malzeme satırı (düşüm iş emri tamamlanınca)."""
    from services import saha_kayit

    a = await saha_kayit.ayarlar(db, ie.hesap_email)
    if not await baglanti_acik(db, ie.hesap_email, a):
        raise s.SahaHatasi("stok_baglantisi_kapali", "stok_urun_id", durum=409)
    u = await urun_bul(db, ie.hesap_email, g.get("stok_urun_id"))
    try:
        binde = sp.miktar_coz(g.get("miktar"), "miktar", u.birim)
    except sp.StokHatasi as h:
        raise s.SahaHatasi(h.kod, h.alan, durum=h.durum, **h.ek)
    if binde > 100_000 * 1000:
        raise s.SahaHatasi("aralik_disi", "miktar")
    return SahaMalzemeKullanimi(is_emri_id=ie.id, hesap_email=ie.hesap_email, malzeme_id=None, ad=u.ad[:160], birim=u.birim,
                                miktar=binde / 1000, birim_fiyat=birim_fiyat(u), ekleyen=kisi, created_at=s.simdi(),
                                stok_urun_id=u.id, stok_miktar=binde)


# ---------------------------------------------------------------------------
# Düşüm ve geri alma (çağıranın işleminde; commit ÇAĞIRANDA, ardından `gecisleri_isle`)
# ---------------------------------------------------------------------------
async def is_tamamlandi(db: AsyncSession, ie: SahaIsEmirleri, kisi: str) -> List[stk.Gecis]:
    from services import saha_kayit

    a = await saha_kayit.ayarlar(db, ie.hesap_email)
    if not await baglanti_acik(db, ie.hesap_email, a):
        return []
    satirlar = (await db.execute(select(SahaMalzemeKullanimi).where(
        SahaMalzemeKullanimi.is_emri_id == ie.id, SahaMalzemeKullanimi.stok_urun_id.isnot(None),
        SahaMalzemeKullanimi.stok_dusum_at.is_(None)).order_by(SahaMalzemeKullanimi.id))).scalars().all()
    if not satirlar:
        return []
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(
        StokUrunleri.hesap_email == ie.hesap_email, StokUrunleri.id.in_({k.stok_urun_id for k in satirlar})))).scalars().all()}
    konum_id = await dusum_konumu(db, ie, kisi, a)
    an = s.simdi()
    gecisler: List[stk.Gecis] = []
    for k in satirlar:
        u = urunler.get(k.stok_urun_id)
        if u is None or not u.stok_takibi or not k.stok_miktar:
            continue  # ürün silinmiş ya da stok tutulmayan (hizmet) kalem
        r = await db.execute(update(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.id == k.id,
                                                                SahaMalzemeKullanimi.stok_dusum_at.is_(None))
                             .values(stok_dusum_at=an, stok_konum_id=konum_id).execution_options(synchronize_session=False))
        if not r.rowcount:
            continue  # eşzamanlı istek düştü
        sonra = await stk.stok_degistir(db, ie.hesap_email, u, konum_id, -int(k.stok_miktar), "cikis", kisi=kisi, eksi_izin=True,
                                        eksi_notu=EKSI_NOTU, belge_no=ie.no[:40], aciklama=f"Saha servisi {ie.no}"[:300],
                                        kaynak=sp.KAYNAK_SAHA, kaynak_id=ie.id, birim_maliyet=int(u.alis_fiyati or 0))
        gecisler.append(stk.Gecis(u.id, sonra + int(k.stok_miktar), sonra))
    return gecisler


async def geri_al(db: AsyncSession, ie: SahaIsEmirleri, satirlar: Sequence[SahaMalzemeKullanimi], kisi: str,
                  neden: str) -> List[stk.Gecis]:
    """Düşülmüş satırları stoka geri ekler (ters hareket `iade`); koşullu — iki kez geri alınmaz."""
    dusulmus = [k for k in satirlar if k.stok_urun_id and k.stok_dusum_at is not None and k.stok_miktar]
    if not dusulmus:
        return []
    urunler = {u.id: u for u in (await db.execute(select(StokUrunleri).where(
        StokUrunleri.hesap_email == ie.hesap_email, StokUrunleri.id.in_({k.stok_urun_id for k in dusulmus})))).scalars().all()}
    gecisler: List[stk.Gecis] = []
    for k in dusulmus:
        r = await db.execute(update(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.id == k.id,
                                                                SahaMalzemeKullanimi.stok_dusum_at.isnot(None))
                             .values(stok_dusum_at=None).execution_options(synchronize_session=False))
        if not r.rowcount:
            continue
        u = urunler.get(k.stok_urun_id)
        if u is None or not k.stok_konum_id:
            logger.warning("Saha stok geri alma atlandı (ürün/konum yok): iş emri %s satır %s", ie.id, k.id)
            continue
        sonra = await stk.stok_degistir(db, ie.hesap_email, u, int(k.stok_konum_id), int(k.stok_miktar), "iade", kisi=kisi,
                                        eksi_izin=True, belge_no=ie.no[:40], aciklama=f"Saha servisi {ie.no} — {neden}"[:300],
                                        kaynak=sp.KAYNAK_SAHA, kaynak_id=ie.id, birim_maliyet=int(u.alis_fiyati or 0))
        gecisler.append(stk.Gecis(u.id, sonra - int(k.stok_miktar), sonra))
    return gecisler


async def is_yeniden_acildi(db: AsyncSession, ie: SahaIsEmirleri, kisi: str) -> List[stk.Gecis]:
    satirlar = (await db.execute(select(SahaMalzemeKullanimi).where(SahaMalzemeKullanimi.is_emri_id == ie.id)
                                 .order_by(SahaMalzemeKullanimi.id))).scalars().all()
    return await geri_al(db, ie, satirlar, kisi, "yeniden açıldı")


async def satir_silindi(db: AsyncSession, ie: SahaIsEmirleri, k: SahaMalzemeKullanimi, kisi: str) -> List[stk.Gecis]:
    return await geri_al(db, ie, [k], kisi, "malzeme silindi")


async def gecisleri_isle(db: AsyncSession, hesap: str, gecisler: Sequence[stk.Gecis]) -> None:
    """Commit sonrası: kritik stok olayı (`stok.kritik`) + bildirim, QR menü eşitlemesi — hata yutulur."""
    if gecisler:
        await stk.gecisleri_isle(db, hesap, gecisler)


def satir_sozlugu(x: SahaMalzemeKullanimi) -> Dict[str, Any]:
    return {"id": x.id, "malzeme_id": x.malzeme_id, "ad": x.ad, "birim": x.birim, "miktar": x.miktar,
            "birim_fiyat": int(x.birim_fiyat or 0), "tutar": int(round((x.miktar or 0) * int(x.birim_fiyat or 0))),
            "stok_urun_id": x.stok_urun_id, "stoktan_dusuldu": x.stok_dusum_at is not None, "stok_konum_id": x.stok_konum_id}


__all__ = [n for n in dir() if not n.startswith("_")]
