"""Faz 6E — Etkinlik ve bilet: veritabanı düzeyindeki işler (router, ödeme webhook'u ve zamanlı görev ortak).

* `kayit_olustur`: KİLİTLİ yer ayırma. Okuma işlemi kapatılır, etkinlik satırı
  `UPDATE … SET kilit = kilit + 1` ile kilitlenir (PostgreSQL'de satır kilidi; SQLite'ta
  yazma kilidi — eşzamanlı ikinci istek bekler), süresi dolan ödeme tutmaları ve davetler
  bırakılır, doluluk kilit içinde yeniden sayılır, boş koltuk numaraları verilir. Son
  güvence `(etkinlik_id, koltuk)` / `(tur_id, tur_koltuk)` benzersizliği (IntegrityError →
  409 `dolu`). İndirim kodu kullanımı koşullu UPDATE ile artar (sınır aşılamaz).
* Ücretli kayıt (yalnız ajans etkinliği): `payments` satırı açılır (fatura yok,
  `invoice_no = ETK-<kod>`), ziyaretçi mevcut `/ode/<jeton>` sayfasına gider; Shopier /
  Lemon Squeezy webhook'u `routers/odemeler.py` üzerinden `odeme_tamamlandi`'yı çağırır →
  biletler "geçerli". Müşteri etkinliğinde para toplanmaz (ücretli tür oluşturulamaz).
* Bekleme listesi: yer açılınca (iptal, süresi dolan ödeme, kapasite artışı, zamanlı tur)
  sıradakine 24 saat geçerli davet; davetli kişi o süre yerini tutar.
* Kapıda okutma: `giris_at` koşullu UPDATE (`… WHERE giris_at IS NULL`) — idempotent,
  çevrimdışı kuyruktan gelen tekrar "zaten girdi" olur.
* Olaylar: `etkinlik.kayit` (kayıt onaylandı), `etkinlik.giris`, `etkinlik.iptal` —
  `services/webhook.olay_yayinla` ile (webhook + otomasyon aboneleri; kişisel veri yok).
* Bildirimler: katılımcıya 7 dilde e-posta (bilet PDF'i + .ics ekli; panel içi kopya yok,
  bilet bağlantısı kalıcı kayıttan silinir), sahibine `etkinlik_kayit` / `etkinlik_iptal`.
* CRM: YALNIZ ajans etkinliğine kayıt aday + not olur; müşteri etkinlikleri CRM'e karışmaz.
"""

import hmac
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.etkinlik import (
    EtkinlikBekleme,
    EtkinlikBiletleri,
    EtkinlikBiletTurleri,
    EtkinlikIndirimKodlari,
    Etkinlikler,
    EtkinlikOkutmalar,
    EtkinlikSiparisleri,
)
from services import etkinlik as s
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Katılımcı e-postaları (katalog dışı: yalnız e-posta, matris yok, push yok).
KATILIMCI_OLAYI = "etkinlik_katilimci"
SAHIP_KAYIT = "etkinlik_kayit"
SAHIP_IPTAL = "etkinlik_iptal"
AKTIF_BILET = ("gecerli", "odeme_bekliyor")
ODEME_ONEKI = "ETK-"
#: Zamanlı turda en çok bu kadar teşekkür e-postası.
TESEKKUR_TUR_SINIRI = 100


# ---------------------------------------------------------------------------
# Okuma yardımcıları
# ---------------------------------------------------------------------------
async def tur_listesi(db: AsyncSession, etkinlik_id: int) -> List[EtkinlikBiletTurleri]:
    return list((await db.execute(
        select(EtkinlikBiletTurleri).where(EtkinlikBiletTurleri.etkinlik_id == etkinlik_id)
        .order_by(EtkinlikBiletTurleri.sira, EtkinlikBiletTurleri.id)
    )).scalars().all())


async def siparis_biletleri(db: AsyncSession, siparis_id: int) -> List[EtkinlikBiletleri]:
    return list((await db.execute(
        select(EtkinlikBiletleri).where(EtkinlikBiletleri.siparis_id == siparis_id).order_by(EtkinlikBiletleri.id)
    )).scalars().all())


def kayit_acik_mi(e: Etkinlikler, an: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
    """(açık mı, kapalıysa neden)."""
    an = an or s.simdi()
    if e.durum == "iptal":
        return False, "etkinlik_iptal"
    if e.durum != "yayinda":
        return False, "kayit_kapali"
    if e.kayit_acilis and an < s.utc(e.kayit_acilis):
        return False, "kayit_baslamadi"
    kapanis = s.utc(e.kayit_kapanis) if e.kayit_kapanis else s.utc(e.baslangic)
    if an > kapanis:
        return False, "kayit_bitti"
    return True, None


@dataclass
class Doluluk:
    koltuklar: Set[int] = field(default_factory=set)
    tur_koltuklari: Dict[int, Set[int]] = field(default_factory=dict)
    #: Kapasitesiz etkinlikte de sayım için: aktif (geçerli + ödeme bekleyen) bilet sayıları.
    aktif: int = 0
    tur_aktif: Dict[int, int] = field(default_factory=dict)
    davet: int = 0
    tur_davet: Dict[int, int] = field(default_factory=dict)

    def kalan(self, e: Etkinlikler) -> Optional[int]:
        if e.kapasite is None:
            return None
        return max(0, int(e.kapasite) - len(self.koltuklar) - self.davet)

    def tur_kalan(self, t: EtkinlikBiletTurleri) -> Optional[int]:
        if t.kontenjan is None:
            return None
        return max(0, int(t.kontenjan) - len(self.tur_koltuklari.get(t.id, set())) - self.tur_davet.get(t.id, 0))

    def musait(self, e: Etkinlikler, t: EtkinlikBiletTurleri) -> Optional[int]:
        degerler = [x for x in (self.kalan(e), self.tur_kalan(t)) if x is not None]
        return min(degerler) if degerler else None


async def doluluk(db: AsyncSession, e: Etkinlikler, haric_davet_id: Optional[int] = None) -> Doluluk:
    d = Doluluk()
    satirlar = (await db.execute(
        select(EtkinlikBiletleri.tur_id, EtkinlikBiletleri.koltuk, EtkinlikBiletleri.tur_koltuk)
        .where(EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.durum.in_(AKTIF_BILET))
    )).all()
    for tid, koltuk, tur_koltuk in satirlar:
        d.aktif += 1
        d.tur_aktif[tid] = d.tur_aktif.get(tid, 0) + 1
        if koltuk is not None:
            d.koltuklar.add(int(koltuk))
        if tur_koltuk is not None:
            d.tur_koltuklari.setdefault(tid, set()).add(int(tur_koltuk))
    sorgu = select(EtkinlikBekleme.tur_id, EtkinlikBekleme.adet).where(
        EtkinlikBekleme.etkinlik_id == e.id, EtkinlikBekleme.durum == "davet", EtkinlikBekleme.davet_son > s.simdi())
    if haric_davet_id is not None:
        sorgu = sorgu.where(EtkinlikBekleme.id != haric_davet_id)
    for tid, adet in (await db.execute(sorgu)).all():
        d.davet += int(adet or 0)
        if tid is not None:
            d.tur_davet[tid] = d.tur_davet.get(tid, 0) + int(adet or 0)
    return d


def bos_koltuklar(kapasite: int, dolu: Set[int], sayi: int) -> List[int]:
    sonuc: List[int] = []
    for i in range(int(kapasite)):
        if i not in dolu:
            sonuc.append(i)
            if len(sonuc) == sayi:
                break
    return sonuc


async def kilitle(db: AsyncSession, e: Etkinlikler) -> None:
    """Okuma işlemini kapat, etkinlik satırını kilitle (kilit UPDATE'i yeni işlemin İLK ifadesi)."""
    await db.commit()
    await db.execute(
        update(Etkinlikler).where(Etkinlikler.id == e.id).values(kilit=Etkinlikler.kilit + 1)
        .execution_options(synchronize_session=False)
    )


# ---------------------------------------------------------------------------
# Süresi dolan tutmalar ve davetler
# ---------------------------------------------------------------------------
async def suresi_dolanlari_birak(db: AsyncSession, etkinlik_id: Optional[int] = None) -> Set[int]:
    """Ödemesi gelmeyen kayıtların yerleri ve süresi geçen davetler bırakılır. Commit ETMEZ.

    Döner: yeri boşalan etkinliklerin kimlikleri.
    """
    an = s.simdi()
    etkilenen: Set[int] = set()
    sorgu = select(EtkinlikSiparisleri.id, EtkinlikSiparisleri.etkinlik_id).where(
        EtkinlikSiparisleri.durum == "odeme_bekliyor", EtkinlikSiparisleri.odeme_son < an)
    if etkinlik_id is not None:
        sorgu = sorgu.where(EtkinlikSiparisleri.etkinlik_id == etkinlik_id)
    satirlar = (await db.execute(sorgu.limit(500))).all()
    if satirlar:
        idler = [i for i, _ in satirlar]
        etkilenen |= {eid for _, eid in satirlar}
        await db.execute(update(EtkinlikSiparisleri).where(EtkinlikSiparisleri.id.in_(idler))
                         .values(durum="suresi_doldu", updated_at=an).execution_options(synchronize_session=False))
        await db.execute(update(EtkinlikBiletleri).where(EtkinlikBiletleri.siparis_id.in_(idler),
                                                         EtkinlikBiletleri.durum == "odeme_bekliyor")
                         .values(durum="iptal", koltuk=None, tur_koltuk=None, iptal_at=an, iptal_eden="sistem",
                                 updated_at=an).execution_options(synchronize_session=False))
        # Bekleyen ödeme bağlantıları kapanır (geç gelen ödeme yine işlenir: `odeme_tamamlandi`).
        from models.payments import Payments

        jetonlar = [j for (j,) in (await db.execute(select(EtkinlikSiparisleri.odeme_jeton)
                                                    .where(EtkinlikSiparisleri.id.in_(idler)))).all() if j]
        if jetonlar:
            await db.execute(update(Payments).where(Payments.jeton.in_(jetonlar), Payments.durum == "bekliyor")
                             .values(durum="iptal").execution_options(synchronize_session=False))
    dsorgu = select(EtkinlikBekleme.id, EtkinlikBekleme.etkinlik_id).where(
        EtkinlikBekleme.durum == "davet", EtkinlikBekleme.davet_son <= an)
    if etkinlik_id is not None:
        dsorgu = dsorgu.where(EtkinlikBekleme.etkinlik_id == etkinlik_id)
    davetler = (await db.execute(dsorgu.limit(500))).all()
    if davetler:
        etkilenen |= {eid for _, eid in davetler}
        await db.execute(update(EtkinlikBekleme).where(EtkinlikBekleme.id.in_([i for i, _ in davetler]))
                         .values(durum="suresi_doldu").execution_options(synchronize_session=False))
    return etkilenen


# ---------------------------------------------------------------------------
# İndirim kodu
# ---------------------------------------------------------------------------
async def indirim_bul(db: AsyncSession, e: Etkinlikler, ham_kod: str, tur_idleri: Iterable[int]) -> EtkinlikIndirimKodlari:
    kod = s.indirim_kodu_duzelt(ham_kod, "indirim_kodu")
    k = (await db.execute(select(EtkinlikIndirimKodlari).where(
        EtkinlikIndirimKodlari.etkinlik_id == e.id, EtkinlikIndirimKodlari.kod == kod))).scalars().first()
    if k is None or not k.aktif:
        raise s.EtkinlikHatasi("indirim_gecersiz", "indirim_kodu")
    if k.son_tarih and s.simdi() > s.utc(k.son_tarih):
        raise s.EtkinlikHatasi("indirim_suresi_doldu", "indirim_kodu")
    if k.kullanim_siniri is not None and int(k.kullanilan or 0) >= int(k.kullanim_siniri):
        raise s.EtkinlikHatasi("indirim_tukendi", "indirim_kodu", durum=409)
    gecerli = s.json_yukle(k.bilet_turleri, None)
    if gecerli and not set(gecerli) & set(tur_idleri):
        raise s.EtkinlikHatasi("indirim_bu_ture_gecmez", "indirim_kodu")
    return k


def indirim_kurali(k: Optional[EtkinlikIndirimKodlari]) -> Optional[s.IndirimKurali]:
    if k is None:
        return None
    turler = s.json_yukle(k.bilet_turleri, None)
    return s.IndirimKurali(id=k.id, tur=k.tur, deger=int(k.deger or 0), turler=[int(x) for x in turler] if turler else None)


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
@dataclass
class KayitGirdisi:
    kalemler: List[Tuple[int, int]]
    ad: str
    eposta: str
    telefon: Optional[str] = None
    yanitlar: Optional[Dict[str, Any]] = None
    katilimcilar: List[str] = field(default_factory=list)
    indirim_kodu: Optional[str] = None
    gizli_kod: Optional[str] = None
    davet: Optional[EtkinlikBekleme] = None
    pazarlama_izni: bool = False
    dil: str = "tr"
    #: form | panel | davet
    kaynak: str = "form"


def _gizli_kod_tutuyor_mu(t: EtkinlikBiletTurleri, kod: Optional[str]) -> bool:
    if not t.gizli:
        return True
    if not kod or not t.gizli_kod:
        return False
    return hmac.compare_digest(kod.strip().upper(), t.gizli_kod.strip().upper())


async def kayit_olustur(db: AsyncSession, e: Etkinlikler, g: KayitGirdisi) -> Tuple[EtkinlikSiparisleri, List[EtkinlikBiletleri]]:
    """Siparişi ve biletleri yazar ve COMMIT eder. Hata: EtkinlikHatasi (dolu → 409)."""
    panel = g.kaynak == "panel"
    an = s.simdi()
    turler = {t.id: t for t in await tur_listesi(db, e.id)}
    secili: List[Tuple[EtkinlikBiletTurleri, int]] = []
    for tid, adet in g.kalemler:
        t = turler.get(tid)
        if t is None or not t.aktif or (not panel and not _gizli_kod_tutuyor_mu(t, g.gizli_kod)):
            raise s.EtkinlikHatasi("tur_yok", "kalemler", durum=404)
        if not panel:
            if t.satis_bas and an < s.utc(t.satis_bas):
                raise s.EtkinlikHatasi("satis_baslamadi", "kalemler", durum=409, tur_id=t.id)
            if t.satis_bit and an > s.utc(t.satis_bit):
                raise s.EtkinlikHatasi("satis_bitti", "kalemler", durum=409, tur_id=t.id)
            if adet > int(t.kisi_basi_en_cok or 1):
                raise s.EtkinlikHatasi("kisi_basi_siniri", "kalemler", tur_id=t.id, en_cok=int(t.kisi_basi_en_cok or 1))
        if int(t.fiyat or 0) > 0 and e.hesap_email:
            raise s.EtkinlikHatasi("ucretli_bilet_yalniz_ajans", "kalemler", durum=409)
        if g.davet is not None and g.davet.tur_id and g.davet.tur_id != t.id:
            raise s.EtkinlikHatasi("davet_turu", "kalemler")
        secili.append((t, adet))
    toplam_adet = sum(a for _, a in secili)
    if g.davet is not None and toplam_adet > int(g.davet.adet or 1):
        raise s.EtkinlikHatasi("davet_adedi", "kalemler", en_cok=int(g.davet.adet or 1))
    if e.katilimci_adlari and toplam_adet > 1 and len([x for x in g.katilimcilar if x]) < toplam_adet:
        raise s.EtkinlikHatasi("katilimci_adi_gerekli", "katilimcilar")
    indirim = await indirim_bul(db, e, g.indirim_kodu, [t.id for t, _ in secili]) if g.indirim_kodu else None
    hesap = s.fiyat_hesapla([s.Kalem(t.id, a, int(t.fiyat or 0), t.para_birimi) for t, a in secili], indirim_kurali(indirim))
    ucretli = hesap["toplam"] > 0 and not panel
    indirim_id = indirim.id if indirim is not None else None

    await kilitle(db, e)
    try:
        await suresi_dolanlari_birak(db, e.id)
        d = await doluluk(db, e, haric_davet_id=g.davet.id if g.davet is not None else None)
        kalan = d.kalan(e)
        if kalan is not None and toplam_adet > kalan:
            raise s.EtkinlikHatasi("dolu", "kalemler", durum=409, kalan=kalan)
        for t, a in secili:
            tk = d.tur_kalan(t)
            if tk is not None and a > tk:
                raise s.EtkinlikHatasi("tur_dolu", "kalemler", durum=409, tur_id=t.id, kalan=tk)
        if indirim_id is not None:
            sonuc = await db.execute(
                update(EtkinlikIndirimKodlari)
                .where(EtkinlikIndirimKodlari.id == indirim_id, EtkinlikIndirimKodlari.aktif.is_(True),
                       or_(EtkinlikIndirimKodlari.kullanim_siniri.is_(None),
                           EtkinlikIndirimKodlari.kullanilan < EtkinlikIndirimKodlari.kullanim_siniri))
                .values(kullanilan=EtkinlikIndirimKodlari.kullanilan + 1).execution_options(synchronize_session=False)
            )
            if not sonuc.rowcount:
                raise s.EtkinlikHatasi("indirim_tukendi", "indirim_kodu", durum=409)
        siparis = EtkinlikSiparisleri(
            etkinlik_id=e.id, hesap_email=e.hesap_email, kod=s.kod_uret(s.SIPARIS_KODU_UZUNLUGU), ad=g.ad,
            eposta=g.eposta, telefon=g.telefon, yanitlar=s.json_yaz(g.yanitlar) if g.yanitlar else None, dil=g.dil,
            durum="odeme_bekliyor" if ucretli else "onayli", kaynak=g.kaynak, ara_toplam=hesap["ara_toplam"],
            indirim=hesap["indirim"], toplam=hesap["toplam"], para_birimi=hesap["para_birimi"], indirim_kodu_id=indirim_id,
            odeme_son=an + timedelta(minutes=s.ODEME_SURESI_DK) if ucretli else None,
            odendi_at=None, aydinlatma_at=an if not panel else None,
            pazarlama_izni_at=an if g.pazarlama_izni else None,
            pazarlama_metin_surumu=_pazarlama_surumu(g.dil) if g.pazarlama_izni else None,
            bekleme_id=g.davet.id if g.davet is not None else None, anonim=False, created_at=an, updated_at=an,
        )
        db.add(siparis)
        await db.flush()
        koltuklar = bos_koltuklar(int(e.kapasite), d.koltuklar, toplam_adet) if e.kapasite is not None else []
        biletler: List[EtkinlikBiletleri] = []
        adlar = [x for x in g.katilimcilar if x]
        sira = 0
        for t, a in secili:
            tur_koltuklari = (bos_koltuklar(int(t.kontenjan), d.tur_koltuklari.get(t.id, set()), a)
                              if t.kontenjan is not None else [])
            for j in range(a):
                b = EtkinlikBiletleri(
                    etkinlik_id=e.id, siparis_id=siparis.id, tur_id=t.id, kod=s.kod_uret(),
                    katilimci_ad=(adlar[sira] if sira < len(adlar) else (g.ad if sira == 0 else None)),
                    durum="odeme_bekliyor" if ucretli else "gecerli",
                    koltuk=koltuklar[sira] if koltuklar else None,
                    tur_koltuk=tur_koltuklari[j] if tur_koltuklari else None,
                    fiyat=int(t.fiyat or 0), iade="yok", sira_no=0, created_at=an, updated_at=an,
                )
                db.add(b)
                biletler.append(b)
                sira += 1
        if g.davet is not None:
            g.davet.durum = "kullanildi"
            g.davet.siparis_id = siparis.id
        if ucretli:
            siparis.odeme_jeton = await _odeme_ac(db, siparis)
        await db.commit()  # olay (etkinlik.kayit): webhook flush kancası, geçerli bilet satırlarından
    except s.TemelHata:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        raise s.EtkinlikHatasi("dolu", "kalemler", durum=409)
    await db.refresh(siparis)
    return siparis, biletler


def _pazarlama_surumu(dil: str) -> str:
    from services import pazarlama_izni

    return pazarlama_izni.surum_etiketi(dil)


async def _odeme_ac(db: AsyncSession, siparis: EtkinlikSiparisleri) -> str:
    """Ajansın ödeme hesabına `payments` satırı (fatura yok). `/ode/<jeton>` sayfası bunu gösterir."""
    from models.payments import Payments

    jeton = secrets.token_urlsafe(9)
    db.add(Payments(
        invoice_id=None, invoice_no=f"{ODEME_ONEKI}{siparis.kod}", client_email=siparis.eposta, jeton=jeton,
        tutar=round(int(siparis.toplam) / 100, 2), para_birimi=siparis.para_birimi, durum="bekliyor",
        created_at=datetime.now(),
    ))
    return jeton


def odeme_mi(kayit: Any) -> bool:
    """`payments` satırı bir etkinlik kaydının mı? (faturasız + `ETK-` öneki)."""
    return not getattr(kayit, "invoice_id", None) and str(getattr(kayit, "invoice_no", "") or "").startswith(ODEME_ONEKI)


async def odeme_tamamlandi(db: AsyncSession, kayit: Any) -> Optional[int]:
    """Ödeme sağlayıcısı "ödendi" dedi: sipariş onaylanır, biletler geçerli olur. Commit ÇAĞIRANA.

    Tutma süresi dolup yerleri bırakılmışsa yeniden yer aranır; yer yoksa sipariş
    `iade_gerekli` olur (sahibine bildirim). Döner: sipariş kimliği (e-posta için).
    """
    siparis = (await db.execute(select(EtkinlikSiparisleri).where(
        EtkinlikSiparisleri.odeme_jeton == kayit.jeton))).scalars().first()
    if siparis is None:
        return None
    if siparis.durum == "onayli":
        return None  # aynı bildirim ikinci kez
    an = s.simdi()
    e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == siparis.etkinlik_id))).scalars().first()
    biletler = await siparis_biletleri(db, siparis.id)
    if siparis.durum != "odeme_bekliyor" and e is not None:
        # Tutma süresi dolmuş: yerleri yeniden ayır (kilit çağıranın işleminde tutmuyor; benzersizlik güvence).
        d = await doluluk(db, e)
        turler = {t.id: t for t in await tur_listesi(db, e.id)}
        kalan = d.kalan(e)
        yeter = kalan is None or len(biletler) <= kalan
        for tid in {b.tur_id for b in biletler}:
            tk = d.tur_kalan(turler[tid]) if tid in turler else None
            if tk is not None and len([b for b in biletler if b.tur_id == tid]) > tk:
                yeter = False
        if not yeter:
            siparis.durum = "iade_gerekli"
            siparis.odendi_at = an
            for b in biletler:
                b.iade = "bekliyor"
            return siparis.id
        koltuklar = bos_koltuklar(int(e.kapasite), d.koltuklar, len(biletler)) if e.kapasite is not None else []
        for i, b in enumerate(biletler):
            t = turler.get(b.tur_id)
            b.koltuk = koltuklar[i] if koltuklar else None
            if t is not None and t.kontenjan is not None:
                bos = bos_koltuklar(int(t.kontenjan), d.tur_koltuklari.get(t.id, set()), 1)
                b.tur_koltuk = bos[0] if bos else None
                d.tur_koltuklari.setdefault(t.id, set()).update(bos)
            b.iptal_at = None
            b.iptal_eden = None
    siparis.durum = "onayli"
    siparis.odendi_at = an
    siparis.updated_at = an
    for b in biletler:
        b.durum = "gecerli"
        b.updated_at = an
    await db.flush()  # olay (etkinlik.kayit + bilet_satildi): webhook flush kancası, bilet durum geçişinden
    return siparis.id


async def odeme_sonrasi(siparis_id: Optional[int]) -> None:
    """Webhook commit'inden sonra: biletleri e-postala, sahibine bildir."""
    if not siparis_id:
        return
    await bilet_epostasi(siparis_id)
    await sahip_bildirimi(siparis_id, SAHIP_KAYIT)


# ---------------------------------------------------------------------------
# İptal
# ---------------------------------------------------------------------------
async def biletleri_iptal_et(db: AsyncSession, e: Etkinlikler, biletler: Sequence[EtkinlikBiletleri], eden: str,
                             iade: bool = False, neden: Optional[str] = None) -> int:
    """Biletleri iptal eder (yer boşalır). Siparişin bütün biletleri iptalse sipariş de iptal.
    Commit ÇAĞIRANA. Ücretli bilette iade "bekliyor" işaretlenir (sahip panelden "yapıldı" der)."""
    an = s.simdi()
    sayi = 0
    siparisler: Set[int] = set()
    for b in biletler:
        if b.durum == "iptal":
            continue
        b.durum = "iptal"
        b.koltuk = None
        b.tur_koltuk = None
        b.iptal_at = an
        b.iptal_eden = eden
        b.sira_no = int(b.sira_no or 0) + 1
        if int(b.fiyat or 0) > 0 and (iade or eden == "katilimci"):
            b.iade = "bekliyor"
        b.updated_at = an
        siparisler.add(b.siparis_id)
        sayi += 1
    await db.flush()
    for sid in siparisler:
        kalan = int((await db.execute(select(func.count(EtkinlikBiletleri.id)).where(
            EtkinlikBiletleri.siparis_id == sid, EtkinlikBiletleri.durum != "iptal"))).scalar() or 0)
        sp = (await db.execute(select(EtkinlikSiparisleri).where(EtkinlikSiparisleri.id == sid))).scalars().first()
        if sp is None:
            continue
        if not kalan:
            sp.durum = "iptal"
            sp.iptal_at = an
            sp.iptal_eden = eden
            sp.iptal_nedeni = (neden or None)
    return sayi  # olay (etkinlik.iptal): webhook flush kancası, gecerli → iptal geçişinden


# ---------------------------------------------------------------------------
# Bekleme listesi
# ---------------------------------------------------------------------------
async def bekleme_davet_et(db: AsyncSession, e: Etkinlikler) -> List[int]:
    """Yer açıldıysa sıradakilere 24 saatlik davet. KİLİTLİ; COMMIT eder. Döner: davet edilen kimlikler."""
    acik, _ = kayit_acik_mi(e)
    if not e.bekleme_listesi or not acik:
        return []
    bekleyen = (await db.execute(select(func.count(EtkinlikBekleme.id)).where(
        EtkinlikBekleme.etkinlik_id == e.id, EtkinlikBekleme.durum == "bekliyor"))).scalar() or 0
    if not bekleyen:
        return []
    await kilitle(db, e)
    try:
        await suresi_dolanlari_birak(db, e.id)
        d = await doluluk(db, e)
        turler = {t.id: t for t in await tur_listesi(db, e.id)}
        kalan = d.kalan(e)
        an = s.simdi()
        davetliler: List[int] = []
        satirlar = (await db.execute(select(EtkinlikBekleme).where(
            EtkinlikBekleme.etkinlik_id == e.id, EtkinlikBekleme.durum == "bekliyor").order_by(EtkinlikBekleme.id)
            .limit(200))).scalars().all()
        for w in satirlar:
            gereken = int(w.adet or 1)
            if kalan is not None and gereken > kalan:
                continue
            if w.tur_id is not None:
                t = turler.get(w.tur_id)
                if t is None or not t.aktif:
                    continue
                tk = d.tur_kalan(t)
                if tk is not None and gereken > tk:
                    continue
                d.tur_davet[t.id] = d.tur_davet.get(t.id, 0) + gereken
            elif kalan is None:
                continue  # kapasitesiz etkinlikte türsüz bekleme anlamsız
            w.durum = "davet"
            w.davet_at = an.replace(microsecond=0)
            w.davet_son = an + s.DAVET_SURESI
            if kalan is not None:
                kalan -= gereken
            d.davet += gereken
            davetliler.append(w.id)
        await db.commit()
        return davetliler
    except Exception:
        await db.rollback()
        raise


async def davet_bul(db: AsyncSession, e: Etkinlikler, jeton: str) -> EtkinlikBekleme:
    kimlik = s.siparis_jetonu_kimligi(jeton)
    w = None
    if kimlik is not None:
        w = (await db.execute(select(EtkinlikBekleme).where(EtkinlikBekleme.id == kimlik,
                                                            EtkinlikBekleme.etkinlik_id == e.id))).scalars().first()
    if w is None or not s.davet_jetonu_gecerli_mi(jeton, w.id, w.davet_at):
        raise s.EtkinlikHatasi("davet_gecersiz", "davet", durum=404)
    if w.durum == "kullanildi":
        raise s.EtkinlikHatasi("davet_kullanildi", "davet", durum=409)
    if w.durum != "davet" or (w.davet_son and s.simdi() > s.utc(w.davet_son)):
        raise s.EtkinlikHatasi("davet_suresi_doldu", "davet", durum=410)
    return w


# ---------------------------------------------------------------------------
# Kapıda okutma
# ---------------------------------------------------------------------------
async def sayac(db: AsyncSession, e: Etkinlikler) -> Dict[str, Any]:
    satirlar = (await db.execute(
        select(EtkinlikBiletleri.tur_id, func.count(EtkinlikBiletleri.id), func.count(EtkinlikBiletleri.giris_at))
        .where(EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.durum == "gecerli")
        .group_by(EtkinlikBiletleri.tur_id)
    )).all()
    turler = {t.id: t for t in await tur_listesi(db, e.id)}
    toplam = sum(int(n) for _, n, _ in satirlar)
    giren = sum(int(g) for _, _, g in satirlar)
    return {
        "toplam": toplam, "giren": giren, "kalan": max(0, toplam - giren), "kapasite": e.kapasite,
        "turler": [{"id": tid, "ad": turler[tid].ad if tid in turler else "—", "toplam": int(n), "giren": int(g)}
                   for tid, n, g in satirlar],
    }


async def okut(db: AsyncSession, e: Etkinlikler, ham: Any, *, kaynak: str, yapan: Optional[str],
               cevrimdisi: bool = False, istemci_zaman: Optional[datetime] = None) -> Dict[str, Any]:
    """Okutma sonucu (kişisel veri: yalnız katılımcı adı + bilet türü; başka etkinliğin biletinde hiçbiri)."""
    kod, _ = s.okutma_coz(ham)
    an = s.simdi()
    b: Optional[EtkinlikBiletleri] = None
    if kod is not None:
        b = (await db.execute(select(EtkinlikBiletleri).where(EtkinlikBiletleri.kod == kod))).scalars().first()
    if b is None:
        sonuc = "gecersiz"
    elif b.etkinlik_id != e.id:
        sonuc = "farkli_etkinlik"
    elif e.durum == "iptal":
        sonuc = "etkinlik_iptal"
    elif b.durum == "iptal":
        sonuc = "iptal"
    elif b.durum == "odeme_bekliyor":
        sonuc = "odeme_bekliyor"
    else:
        yaz = await db.execute(
            update(EtkinlikBiletleri)
            .where(EtkinlikBiletleri.id == b.id, EtkinlikBiletleri.giris_at.is_(None), EtkinlikBiletleri.durum == "gecerli")
            .values(giris_at=an, giris_yapan=(yapan or kaynak)[:254]).execution_options(synchronize_session=False)
        )
        await db.refresh(b)
        if yaz.rowcount:
            sonuc = "gecerli"  # olay (etkinlik.giris): webhook flush kancası, aşağıdaki okutma kaydından
        else:
            sonuc = "zaten_girdi" if b.giris_at else "gecersiz"
    db.add(EtkinlikOkutmalar(
        etkinlik_id=e.id, bilet_id=b.id if b is not None and b.etkinlik_id == e.id else None, sonuc=sonuc, kaynak=kaynak,
        yapan=(yapan or None) and yapan[:254], cevrimdisi=bool(cevrimdisi), istemci_zaman=istemci_zaman, zaman=an,
    ))
    ayrinti: Optional[Dict[str, Any]] = None
    if b is not None and b.etkinlik_id == e.id:
        t = (await db.execute(select(EtkinlikBiletTurleri).where(EtkinlikBiletTurleri.id == b.tur_id))).scalars().first()
        sp = (await db.execute(select(EtkinlikSiparisleri.ad).where(EtkinlikSiparisleri.id == b.siparis_id))).scalar()
        ayrinti = {"kod": b.kod, "tur": t.ad if t else "—", "ad": b.katilimci_ad or sp or None,
                   "giris_at": s.iso(b.giris_at)}
    await db.commit()
    return {"sonuc": sonuc, "bilet": ayrinti, "sayac": await sayac(db, e), "zaman": s.iso(an)}


async def son_okutmalar(db: AsyncSession, e: Etkinlikler, sinir: int = 10) -> List[Dict[str, Any]]:
    satirlar = (await db.execute(
        select(EtkinlikOkutmalar, EtkinlikBiletleri.kod, EtkinlikBiletleri.tur_id)
        .outerjoin(EtkinlikBiletleri, EtkinlikBiletleri.id == EtkinlikOkutmalar.bilet_id)
        .where(EtkinlikOkutmalar.etkinlik_id == e.id).order_by(EtkinlikOkutmalar.id.desc()).limit(sinir)
    )).all()
    turler = {t.id: t.ad for t in await tur_listesi(db, e.id)}
    return [{"zaman": s.iso(o.zaman), "sonuc": o.sonuc, "kaynak": o.kaynak, "kod": kod, "tur": turler.get(tid) if tid else None,
             "cevrimdisi": bool(o.cevrimdisi)} for o, kod, tid in satirlar]


# ---------------------------------------------------------------------------
# E-postalar
# ---------------------------------------------------------------------------
async def _katilimciya(db: AsyncSession, alici: str, konu: str, govde: str, ref: Tuple[str, int],
                       gizliler: Sequence[str] = (), ekler: Optional[List[Dict[str, Any]]] = None) -> None:
    """Katılımcıya yalnız e-posta: panel içi kopya silinir; bilet/davet bağlantısı (yetki belgesi)
    kalıcı bildirim kaydından çıkarılır."""
    from services.notify import dispatch

    satirlar = await dispatch(db, event_type=KATILIMCI_OLAYI, title=konu, body=govde,
                              recipients=[{"email": alici, "role": "client"}], link=None, ref_type=ref[0], ref_id=ref[1],
                              eposta_ek={"ekler": ekler} if ekler else None)
    degisti = False
    for satir in list(satirlar):
        if getattr(satir, "channel", None) == "inapp":
            await db.delete(satir)
            degisti = True
            continue
        for alan in ("body", "title"):
            deger = getattr(satir, alan, None)
            if not deger:
                continue
            yeni = deger
            for g in sorted((x for x in gizliler if x), key=len, reverse=True):
                yeni = yeni.replace(g, "…")
            if yeni != deger:
                setattr(satir, alan, yeni)
                degisti = True
    if degisti:
        await db.commit()


def _oturum():
    from core.database import db_manager

    return db_manager.async_session_maker() if db_manager.async_session_maker else None


async def _yukle(db: AsyncSession, siparis_id: int):
    sp = (await db.execute(select(EtkinlikSiparisleri).where(EtkinlikSiparisleri.id == siparis_id))).scalars().first()
    if sp is None:
        return None, None, []
    e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == sp.etkinlik_id))).scalars().first()
    return sp, e, await siparis_biletleri(db, sp.id)


async def bilet_epostasi(siparis_id: int, tur: str = "onay") -> None:
    """`onay` (biletler + PDF + .ics) ya da `odeme` (ödeme bağlantısı) e-postası. Hata yutulur."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            sp, e, biletler = await _yukle(db, siparis_id)
            if sp is None or e is None or not sp.eposta:
                return
            dil = sp.dil if sp.dil in s.DILLER else e.dil
            m = s.metinler(dil)
            jeton = s.siparis_jetonu(sp.id, sp.kod)
            adres = s.bilet_adresi(e.slug, jeton)
            turler = {t.id: t for t in await tur_listesi(db, e.id)}
            satirlar: List[str] = []
            ekler: List[Dict[str, Any]] = []
            gizliler: List[str] = [adres, jeton]
            if tur == "odeme":
                odeme = f"{s.site_adresi()}/ode/{sp.odeme_jeton}"
                gizliler.append(odeme)
                satirlar += [f"{m['toplam']}: {s.para_yaz(sp.toplam, sp.para_birimi, dil)}", "", m["odeme_baglanti"], odeme,
                             "", m["bilet_sayfasi"], adres]
                konu, govde = s.eposta_govdesi("odeme", dil, ad=sp.ad or "", e=e, satirlar=satirlar,
                                               son=s.zaman_yaz(sp.odeme_son, e.saat_dilimi, dil) if sp.odeme_son else "")
            else:
                gecerli = [b for b in biletler if b.durum == "gecerli"]
                if not gecerli:
                    return
                satirlar.append(f"{m['biletler']}:")
                for b in gecerli:
                    t = turler.get(b.tur_id)
                    satirlar.append(f"• {t.ad if t else m['bilet']} — {b.kod}" + (f" ({b.katilimci_ad})" if b.katilimci_ad else ""))
                if sp.toplam:
                    satirlar.append(f"{m['toplam']}: {s.para_yaz(sp.toplam, sp.para_birimi, dil)}")
                satirlar += ["", m["bilet_sayfasi"], adres]
                if e.bicim in ("online", "karma") and e.online_baglanti:
                    satirlar += ["", m["online_baglanti"], e.online_baglanti]
                    gizliler.append(e.online_baglanti)
                harita = s.harita_adresi(e)
                if harita:
                    satirlar += ["", m["harita"], harita]
                ics_adresi = f"{s.site_adresi()}/api/v1/etkinlik/bilet/{jeton}/takvim.ics"
                takvim = s.takvim_baglantilari(e, dil, adres, ics_adresi)
                satirlar += ["", m["takvim"], f"Google: {takvim['google']}", f"Outlook: {takvim['outlook']}", m["ekler"]]
                # Takvim bağlantıları bilet adresini (ve online bağlantıyı) kodlanmış taşıyor: kalıcı kayıtta durmasın.
                gizliler += [takvim["google"], takvim["outlook"], ics_adresi]
                if e.odeme_notu:
                    satirlar += ["", f"{m['odeme_notu']}:", e.odeme_notu]
                if e.iade_politikasi:
                    satirlar += ["", f"{m['iade_politikasi']}:", e.iade_politikasi]
                konu, govde = s.eposta_govdesi("onay", dil, ad=sp.ad or "", e=e, satirlar=satirlar)
                ekler.append({"dosya_adi": "etkinlik.ics", "icerik": s.ics_uret(e, sp.kod, dil, bilet_adresi_=adres),
                              "tur": "text/calendar; method=PUBLISH; charset=UTF-8"})
                try:
                    pdf = s.bilet_pdf(e, sp, [(b, turler[b.tur_id].ad if b.tur_id in turler else "—") for b in gecerli], dil)
                    ekler.append({"dosya_adi": f"bilet-{sp.kod}.pdf", "icerik": pdf, "tur": "application/pdf"})
                except Exception:  # noqa: BLE001 - PDF olmadan da bilet gider
                    logger.exception("Bilet PDF'i üretilemedi (%s)", sp.id)
            await _katilimciya(db, sp.eposta, konu, govde, ("etkinlik_siparisleri", sp.id), gizliler, ekler)
    except Exception:  # noqa: BLE001
        logger.exception("Bilet e-postası gönderilemedi (%s)", siparis_id)


async def iptal_epostasi(siparis_id: int, etkinlik_iptal: bool = False) -> None:
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            sp, e, biletler = await _yukle(db, siparis_id)
            if sp is None or e is None or not sp.eposta:
                return
            dil = sp.dil if sp.dil in s.DILLER else e.dil
            m = s.metinler(dil)
            satirlar: List[str] = []
            if any(int(b.fiyat or 0) > 0 for b in biletler):
                satirlar += ["", m["iade_notu"]]
            if e.iade_politikasi:
                satirlar += ["", f"{m['iade_politikasi']}:", e.iade_politikasi]
            konu, govde = s.eposta_govdesi("etkinlik_iptal" if etkinlik_iptal else "iptal", dil, ad=sp.ad or "", e=e,
                                           satirlar=satirlar)
            ekler = [{"dosya_adi": "etkinlik.ics", "icerik": s.ics_uret(e, sp.kod, dil, iptal=True, sira_no=1),
                      "tur": "text/calendar; method=PUBLISH; charset=UTF-8"}]
            await _katilimciya(db, sp.eposta, konu, govde, ("etkinlik_siparisleri", sp.id), (), ekler)
    except Exception:  # noqa: BLE001
        logger.exception("İptal e-postası gönderilemedi (%s)", siparis_id)


async def bekleme_epostasi(bekleme_id: int, tur: str) -> None:
    """`bekleme` (listeye eklendiniz) ya da `davet` (yer açıldı, 24 saatlik bağlantı)."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            w = (await db.execute(select(EtkinlikBekleme).where(EtkinlikBekleme.id == bekleme_id))).scalars().first()
            if w is None or not w.eposta:
                return
            e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == w.etkinlik_id))).scalars().first()
            if e is None:
                return
            dil = w.dil if w.dil in s.DILLER else e.dil
            m = s.metinler(dil)
            satirlar: List[str] = []
            gizliler: List[str] = []
            son = None
            if tur == "davet":
                jeton = s.davet_jetonu(w.id, w.davet_at)
                adres = s.davet_adresi(e.slug, jeton)
                gizliler = [adres, jeton]
                satirlar = ["", m["davet_baglanti"], adres]
                son = s.zaman_yaz(w.davet_son, e.saat_dilimi, dil) if w.davet_son else ""
            konu, govde = s.eposta_govdesi(tur, dil, ad=w.ad or "", e=e, satirlar=satirlar, son=son)
            await _katilimciya(db, w.eposta, konu, govde, ("etkinlik_bekleme", w.id), gizliler)
    except Exception:  # noqa: BLE001
        logger.exception("Bekleme listesi e-postası gönderilemedi (%s)", bekleme_id)


async def davetleri_gonder(idler: Sequence[int]) -> None:
    for i in idler:
        await bekleme_epostasi(i, "davet")


async def toplu_eposta(etkinlik_id: int, tur: str, konu_ham: Optional[str] = None, metin_ham: Optional[str] = None) -> int:
    """`duyuru` (bilgilendirme — pazarlama değil), `etkinlik_iptal`, `tesekkur`.

    Alıcı: geçerli bileti olan siparişlerin e-postası (aynı adrese bir kez). Teşekkürde,
    etkinlikte giriş kaydı varsa yalnız giriş yapanlar. Döner: gönderilen sayısı.
    """
    oturum = _oturum()
    if oturum is None:
        return 0
    gonderilen = 0
    try:
        async with oturum as db:
            e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == etkinlik_id))).scalars().first()
            if e is None:
                return 0
            sorgu = (select(EtkinlikSiparisleri).join(EtkinlikBiletleri, EtkinlikBiletleri.siparis_id == EtkinlikSiparisleri.id)
                     .where(EtkinlikSiparisleri.etkinlik_id == e.id, EtkinlikSiparisleri.anonim.is_(False),
                            EtkinlikSiparisleri.eposta.isnot(None)))
            if tur == "etkinlik_iptal":
                sorgu = sorgu.where(EtkinlikBiletleri.durum.in_(AKTIF_BILET))
            else:
                sorgu = sorgu.where(EtkinlikBiletleri.durum == "gecerli")
            if tur == "tesekkur":
                giren_var = (await db.execute(select(EtkinlikBiletleri.id).where(
                    EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.giris_at.isnot(None)).limit(1))).first()
                if giren_var:
                    sorgu = sorgu.where(EtkinlikBiletleri.giris_at.isnot(None))
                sorgu = sorgu.where(EtkinlikSiparisleri.tesekkur_at.is_(None))
            siparisler = list({sp.id: sp for sp in (await db.execute(sorgu.order_by(EtkinlikSiparisleri.id)
                                                                         .limit(5000))).scalars().all()}.values())
            gorulen: Set[str] = set()
            for sp in siparisler:
                if tur == "tesekkur" and gonderilen >= TESEKKUR_TUR_SINIRI:
                    break
                adres_ = (sp.eposta or "").lower()
                if adres_ in gorulen:
                    if tur == "tesekkur":
                        sp.tesekkur_at = s.simdi()
                    continue
                gorulen.add(adres_)
                dil = sp.dil if sp.dil in s.DILLER else e.dil
                m = s.metinler(dil)
                if tur == "duyuru":
                    konu = f"{e.baslik}: {konu_ham}"
                    govde = "\n".join([m["merhaba"].format(ad=sp.ad or "—"), "", metin_ham or "", "",
                                       f"{m['ne_zaman']}: {s.aralik_yaz(e.baslangic, e.bitis, e.saat_dilimi, dil)}",
                                       "", m["duyuru_not"].format(etkinlik=e.baslik), f"— {e.organizator_ad or e.baslik}"])
                elif tur == "tesekkur":
                    satirlar = []
                    if e.tesekkur_metni:
                        satirlar += [e.tesekkur_metni, ""]
                    if e.anket_url:
                        satirlar += [m["anket"], e.anket_url]
                    konu, govde = s.eposta_govdesi("tesekkur", dil, ad=sp.ad or "", e=e, satirlar=satirlar)
                    sp.tesekkur_at = s.simdi()
                    await db.commit()
                else:
                    satirlar = ["", m["iade_notu"]] if int(sp.toplam or 0) > 0 else []
                    if e.iade_politikasi:
                        satirlar += ["", f"{m['iade_politikasi']}:", e.iade_politikasi]
                    konu, govde = s.eposta_govdesi("etkinlik_iptal", dil, ad=sp.ad or "", e=e, satirlar=satirlar)
                await _katilimciya(db, sp.eposta, konu, govde, ("etkinlik_siparisleri", sp.id))
                gonderilen += 1
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Toplu etkinlik e-postası başarısız (%s, %s)", etkinlik_id, tur)
    return gonderilen


async def sahip_bildirimi(siparis_id: int, olay: str) -> None:
    """Sahibine (müşteride hesap + `etkinlik` izinli ekip; ajansta yöneticiler)."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            from services import notify

            sp, e, biletler = await _yukle(db, siparis_id)
            if sp is None or e is None:
                return
            turler = {t.id: t.ad for t in await tur_listesi(db, e.id)}
            adet = len([b for b in biletler if b.durum != "iptal"]) if olay == SAHIP_KAYIT else len(biletler)
            zaman = s.aralik_yaz(e.baslangic, e.bitis, e.saat_dilimi, "tr")
            if olay == SAHIP_KAYIT:
                baslik = f"Yeni kayıt: {sp.ad or '—'} — {e.baslik} ({adet} bilet)"
            else:
                baslik = f"Bilet iptal edildi: {sp.ad or '—'} — {e.baslik}"
            satirlar = [f"Etkinlik: {e.baslik}", f"Zaman: {zaman}", f"Ad: {sp.ad or '—'}", f"E-posta: {sp.eposta or '—'}",
                        f"Telefon: {sp.telefon or '—'}", f"Kayıt kodu: {sp.kod}"]
            for b in biletler:
                satirlar.append(f"• {turler.get(b.tur_id, '—')} — {b.kod} ({b.durum})")
            if sp.toplam:
                satirlar.append(f"Tutar: {s.para_yaz(sp.toplam, sp.para_birimi, 'tr')}")
            if sp.durum == "iade_gerekli":
                satirlar.append("DİKKAT: ödeme geldi ama tutma süresi dolduğu için yer kalmadı — iade gerekli.")
            if any(b.iade == "bekliyor" for b in biletler):
                satirlar.append("Ücretli bilet: iade bekleniyor (panelden \"iade yapıldı\" işaretleyin).")
            govde = "\n".join(satirlar)
            baslik, govde = await notify.render(db, olay, baslik, govde, {"ad": sp.ad or "", "etkinlik": e.baslik})
            if e.hesap_email:
                alicilar = [{"email": e.hesap_email, "role": "client"}]
                baglanti = "/client?sekme=etkinlik"
            else:
                alicilar = await notify.admin_recipients(db)
                baglanti = "/admin?sekme=etkinlik"
            await notify.dispatch(db, event_type=olay, title=baslik, body=govde, recipients=alicilar, link=baglanti,
                                  ref_type="etkinlik_siparisleri", ref_id=sp.id)
    except Exception:  # noqa: BLE001
        logger.exception("Etkinlik sahip bildirimi gönderilemedi (%s)", siparis_id)


# ---------------------------------------------------------------------------
# CRM (yalnız ajans etkinliği) ve pazarlama izni
# ---------------------------------------------------------------------------
async def crm_isle(siparis_id: int) -> Optional[int]:
    oturum = _oturum()
    if oturum is None:
        return None
    try:
        async with oturum as db:
            sp, e, biletler = await _yukle(db, siparis_id)
            if sp is None or e is None or e.hesap_email:
                return None  # müşteri etkinlikleri CRM'e karışmaz (4K kararı)
            from models.crm import CrmAktiviteler
            from services import crm, pazarlama_izni

            sorular = {q.get("id"): q.get("etiket") for q in (s.json_yukle(e.sorular, []) or [])}
            yanitlar = s.json_yukle(sp.yanitlar, {}) or {}
            mesaj = "\n".join(f"{sorular.get(k, k)}: {'✓' if v is True else v}" for k, v in yanitlar.items()) or None
            sonuc = await crm.kayit_isle(db, crm.TalepGirdisi(
                tablo="etkinlik_siparisleri", kayit_id=sp.id, ad=sp.ad, email=sp.eposta, telefon=sp.telefon,
                konu=f"Etkinlik: {e.baslik}", mesaj=mesaj, kaynak="form", kaynak_ham=f"etkinlik:{e.slug}",
                ek_veri={"etkinlik": e.slug, "siparis": sp.kod},
            ))
            if not sonuc:
                await db.rollback()
                return None
            turler = {t.id: t.ad for t in await tur_listesi(db, e.id)}
            db.add(CrmAktiviteler(
                aday_id=sonuc["aday_id"], tur="not", olay="etkinlik",
                veri=s.json_yaz({"etkinlik_id": e.id, "siparis_id": sp.id, "bilet": len(biletler)}),
                metin=f"Etkinlik kaydı: {e.baslik} — " + ", ".join(sorted({turler.get(b.tur_id, '—') for b in biletler})),
                yapan="sistem", zaman=s.simdi(),
            ))
            if sp.pazarlama_izni_at:
                await pazarlama_izni.adaya_isle(db, sonuc["aday_id"], sp.pazarlama_izni_at, f"etkinlik:{e.slug}",
                                                sp.pazarlama_metin_surumu or pazarlama_izni.surum_etiketi(sp.dil))
            await db.flush()
            await db.run_sync(lambda ses: crm.puani_yenile_sync(ses.connection(), sonuc["aday_id"]))
            sp.crm_aday_id = sonuc["aday_id"]
            await db.commit()
            return sonuc["aday_id"]
    except Exception:  # noqa: BLE001 - CRM hatası kaydı bozmasın
        logger.exception("Etkinlik kaydı CRM'e aktarılamadı (%s)", siparis_id)
        return None


async def pazarlamaya_aktar(db: AsyncSession, e: Etkinlikler, liste_id: int) -> Dict[str, int]:
    """Pazarlama izni veren katılımcılar → e-posta pazarlama kişileri + liste (Faz 5M). İzni olmayan
    hiçbir kişi aktarılmaz; kişi daha önce reddettiyse dokunulmaz. COMMIT eder."""
    from models.eposta_pazarlama import EpKisiler, EpListeler
    from routers.eposta_pazarlama import _kisi_siniri_denetle, _uyelik_ekle
    from services import eposta_pazarlama as ep

    hesap = e.hesap_email
    liste = (await db.execute(select(EpListeler).where(
        EpListeler.id == liste_id, EpListeler.hesap_email.is_(None) if hesap is None else EpListeler.hesap_email == hesap
    ))).scalars().first()
    if liste is None:
        raise s.EtkinlikHatasi("liste_yok", "liste_id", durum=404)
    siparisler = (await db.execute(select(EtkinlikSiparisleri).where(
        EtkinlikSiparisleri.etkinlik_id == e.id, EtkinlikSiparisleri.pazarlama_izni_at.isnot(None),
        EtkinlikSiparisleri.anonim.is_(False), EtkinlikSiparisleri.durum.in_(("onayli", "iptal", "iade_gerekli")),
        EtkinlikSiparisleri.eposta.isnot(None)).order_by(EtkinlikSiparisleri.id))).scalars().all()
    kapsam = ep.kapsam_anahtari(hesap)
    mevcut = {k.eposta: k for k in (await db.execute(select(EpKisiler).where(EpKisiler.kapsam == kapsam))).scalars().all()}
    yeni_adresler = {ep.eposta_duzelt(sp.eposta) for sp in siparisler} - set(mevcut)
    if yeni_adresler:
        try:
            await _kisi_siniri_denetle(db, hesap, len(yeni_adresler))
        except Exception as h:  # HTTPException(409 kisi_siniri)
            detay = getattr(h, "detail", None) or {}
            raise s.EtkinlikHatasi("kisi_siniri", "liste_id", durum=409, sinir=detay.get("sinir") if isinstance(detay, dict) else None)
    sayac = {"aktarilan": 0, "yeni": 0, "listeye": 0, "reddetmis": 0}
    for sp in siparisler:
        eposta = ep.eposta_duzelt(sp.eposta)
        if not ep.eposta_gecerli(eposta):
            continue
        k = mevcut.get(eposta)
        if k is None:
            k = EpKisiler(kapsam=kapsam, hesap_email=hesap, eposta=eposta, ad=sp.ad, alici_turu="bireysel",
                          izin_durumu="izinsiz", kaynak="form", kaynak_detay=f"etkinlik:{e.slug}"[:120], etiketler="[]",
                          ozel_alanlar="{}", dil=sp.dil if sp.dil in s.DILLER else "tr", created_at=s.simdi())
            db.add(k)
            mevcut[eposta] = k
            sayac["yeni"] += 1
        if k.izin_durumu == "reddetti":
            sayac["reddetmis"] += 1
            continue
        if k.izin_durumu != "izinli":
            k.izin_durumu = "izinli"
            k.izin_kaynagi = f"etkinlik:{e.id}"[:200]
            k.izin_zamani = s.utc(sp.pazarlama_izni_at)
            k.izin_metin_surumu = sp.pazarlama_metin_surumu
            k.izin_kaniti = s.json_yaz({"yontem": "etkinlik_kayit_formu", "siparis": sp.kod})
        sayac["aktarilan"] += 1
        await db.flush()
        if await _uyelik_ekle(db, k, liste.id, "etkinlik"):
            sayac["listeye"] += 1
    await db.commit()
    return sayac


# ---------------------------------------------------------------------------
# Kapasite değişince koltuk ataması
# ---------------------------------------------------------------------------
async def koltuklari_esitle(db: AsyncSession, e: Etkinlikler, tur: Optional[EtkinlikBiletTurleri] = None) -> None:
    """Kapasite (ya da tür kontenjanı) sonradan konduysa koltuğu olmayan aktif biletlere koltuk verir.
    Yetmiyorsa EtkinlikHatasi(409 kapasite_az). Commit ÇAĞIRANA."""
    d = await doluluk(db, e)
    if tur is None:
        if e.kapasite is None:
            return
        if d.aktif > int(e.kapasite):
            raise s.EtkinlikHatasi("kapasite_az", "kapasite", durum=409, en_az=d.aktif)
        eksik = (await db.execute(select(EtkinlikBiletleri).where(
            EtkinlikBiletleri.etkinlik_id == e.id, EtkinlikBiletleri.durum.in_(AKTIF_BILET),
            EtkinlikBiletleri.koltuk.is_(None)))).scalars().all()
        bos = bos_koltuklar(int(e.kapasite), d.koltuklar, len(eksik))
        for b, k in zip(eksik, bos):
            b.koltuk = k
        return
    if tur.kontenjan is None:
        return
    aktif = d.tur_aktif.get(tur.id, 0)
    if aktif > int(tur.kontenjan):
        raise s.EtkinlikHatasi("kontenjan_az", "kontenjan", durum=409, en_az=aktif)
    eksik = (await db.execute(select(EtkinlikBiletleri).where(
        EtkinlikBiletleri.tur_id == tur.id, EtkinlikBiletleri.durum.in_(AKTIF_BILET),
        EtkinlikBiletleri.tur_koltuk.is_(None)))).scalars().all()
    bos = bos_koltuklar(int(tur.kontenjan), d.tur_koltuklari.get(tur.id, set()), len(eksik))
    for b, k in zip(eksik, bos):
        b.tur_koltuk = k


# ---------------------------------------------------------------------------
# Anonimleştirme
# ---------------------------------------------------------------------------
KISISEL_BOS = {"ad": None, "eposta": None, "telefon": None, "yanitlar": None, "iptal_nedeni": None, "anonim": True}


async def anonimlestir(db: AsyncSession, e: Optional[Etkinlikler] = None, hemen: bool = False) -> int:
    """Saklama süresi (etkinlik BİTİŞİNDEN) dolan kayıtların kişisel alanları silinir. Commit ETMEZ."""
    an = s.simdi()
    etkinlikler = [e] if e is not None else (await db.execute(select(Etkinlikler))).scalars().all()
    toplam = 0
    for x in etkinlikler:
        if not hemen and s.utc(x.bitis) + timedelta(days=max(1, int(x.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN))) > an:
            continue
        idler = [i for (i,) in (await db.execute(select(EtkinlikSiparisleri.id).where(
            EtkinlikSiparisleri.etkinlik_id == x.id, EtkinlikSiparisleri.anonim.is_(False)))).all()]
        if idler:
            sonuc = await db.execute(update(EtkinlikSiparisleri).where(EtkinlikSiparisleri.id.in_(idler))
                                     .values(**KISISEL_BOS).execution_options(synchronize_session=False))
            toplam += int(sonuc.rowcount or 0)
            await db.execute(update(EtkinlikBiletleri).where(EtkinlikBiletleri.siparis_id.in_(idler))
                             .values(katilimci_ad=None).execution_options(synchronize_session=False))
            await _bildirimleri_anonimlestir(db, idler)
        await db.execute(update(EtkinlikBekleme).where(EtkinlikBekleme.etkinlik_id == x.id, EtkinlikBekleme.anonim.is_(False))
                         .values(ad=None, eposta=None, telefon=None, anonim=True).execution_options(synchronize_session=False))
    return toplam


async def _bildirimleri_anonimlestir(db: AsyncSession, idler: Sequence[int]) -> None:
    from models.notifications import Notifications

    kosul = (Notifications.ref_type == "etkinlik_siparisleri", Notifications.ref_id.in_(list(idler)))
    await db.execute(delete(Notifications).where(*kosul, Notifications.event_type == KATILIMCI_OLAYI)
                     .execution_options(synchronize_session=False))
    await db.execute(update(Notifications).where(*kosul)
                     .values(title="Etkinlik kaydı (kişisel bilgiler saklama süresi dolunca silindi)", body=None)
                     .execution_options(synchronize_session=False))


# ---------------------------------------------------------------------------
# Zamanlı bakım
# ---------------------------------------------------------------------------
async def zamanli_bakim(db: AsyncSession) -> Dict[str, Any]:
    """Her tur: süresi dolan tutmalar/davetler, bekleme listesi davetleri, biten etkinlik →
    tamamlandı, teşekkür + anket e-postası, saklama süresi dolan kişisel veri."""
    an = s.simdi()
    etkilenen = await suresi_dolanlari_birak(db)
    await db.commit()
    bekleyen = {eid for (eid,) in (await db.execute(select(EtkinlikBekleme.etkinlik_id).where(
        EtkinlikBekleme.durum == "bekliyor").distinct().limit(200))).all()}
    davet_sayisi = 0
    for eid in sorted(etkilenen | bekleyen):
        e = (await db.execute(select(Etkinlikler).where(Etkinlikler.id == eid))).scalars().first()
        if e is None:
            continue
        try:
            idler = await bekleme_davet_et(db, e)
        except Exception:  # noqa: BLE001
            logger.exception("Bekleme davetleri yapılamadı (%s)", eid)
            continue
        davet_sayisi += len(idler)
        await davetleri_gonder(idler)
    biten = (await db.execute(select(Etkinlikler).where(Etkinlikler.durum == "yayinda", Etkinlikler.bitis < an))).scalars().all()
    for e in biten:
        e.durum = "tamamlandi"
    await db.commit()
    tesekkur = 0
    adaylar = (await db.execute(select(Etkinlikler.id).where(
        Etkinlikler.tesekkur_aktif.is_(True), Etkinlikler.tesekkur_at.is_(None), Etkinlikler.durum != "iptal",
        Etkinlikler.bitis <= an - s.TESEKKUR_GECIKME, Etkinlikler.bitis >= an - s.TESEKKUR_PENCERE,
    ).limit(20))).all()
    for (eid,) in adaylar:
        n = await toplu_eposta(eid, "tesekkur")
        tesekkur += n
        if n < TESEKKUR_TUR_SINIRI:
            await db.execute(update(Etkinlikler).where(Etkinlikler.id == eid).values(tesekkur_at=an)
                             .execution_options(synchronize_session=False))
            await db.commit()
    anonim = await anonimlestir(db)
    await db.commit()  # 0 satırda da: açık yazma işlemi (SQLite kilidi) kalmasın
    return {"birakilan_etkinlik": len(etkilenen), "davet": davet_sayisi, "tamamlanan": len(biten), "tesekkur": tesekkur,
            "anonimlestirilen": anonim}


__all__ = [
    "kayit_olustur", "KayitGirdisi", "odeme_mi", "odeme_tamamlandi", "odeme_sonrasi", "biletleri_iptal_et",
    "bekleme_davet_et", "okut", "sayac", "zamanli_bakim", "pazarlamaya_aktar", "crm_isle", "anonimlestir",
]
