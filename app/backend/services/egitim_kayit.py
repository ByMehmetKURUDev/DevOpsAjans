"""Faz 6K — Eğitim modülü: veritabanı düzeyindeki işler (router ve zamanlı görev ortak).

* `kayit_olustur`: KİLİTLİ koltuk ayırma (etkinlik deseni): okuma işlemi kapatılır, kurs satırı
  `UPDATE … SET kilit = kilit + 1` ile kilitlenir, dolu koltuklar kilit içinde sayılır, boş koltuk
  numarası verilir; son güvence `(kurs_id, koltuk)` benzersizliği. Kurs doluysa bekleme listesi.
  Aktif öğrenci ayrılınca (ya da silinince) koltuk boşalır ve sıradaki bekleyen KENDİLİĞİNDEN aktif
  olur (bilgilendirme e-postası).
* Yoklama: `(oturum_id, ogrenci_id)` benzersiz — çift okutma ikinci satır açmaz ("zaten işaretli").
  Devamsızlık eşiğe ulaşınca `devamsizlik_uyari_at` BİR KEZ yazılır → merkezi flush kancası
  `egitim.devamsizlik` olayını üretir (`services/webhook.py`), öğrenciye/veliye bilgilendirme.
* İlerleme / quiz / yoklama yüzdeleri ve sertifika koşulları (`istatistik`), sertifika verme.
* Olaylar: `egitim.kayit` (yeni kayıt satırı), `egitim.tamamlandi` (yeni sertifika satırı),
  `egitim.devamsizlik` — hepsi `services/webhook.py` flush kancasından (ikinci kanca sistemi yok).
* E-postalar: öğrenciye (18 yaş altında veliye) 7 dilde bilgilendirme; panel içi kopya yok, öğrenci
  bağlantısı kalıcı bildirim kaydından silinir (etkinlik `_katilimciya` deseni). Sahibine `egitim_kayit`.
* KVKK: kişisel alanlar kurs bitişinden `saklama_gun` sonra anonimleşir (veli bilgisi, teslim metni ve
  dosyaları, quiz yanıtları dahil); sertifika doğrulaması yalnız maskeli adla sürer.
* "AI ile soru üret" hakkı: hesap × ay sayacı (modül ayarı `ai_hakki`), dahil hak bitince
  `kredi_ile_asim` açıksa üretim başına kredi (`services/kredi.harca`), model hata verirse iade.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.egitim import (
    EgitimAiKullanimi,
    EgitimAyarlari,
    EgitimDenemeleri,
    EgitimDersleri,
    EgitimDosyalari,
    EgitimDuyurulari,
    EgitimIlerleme,
    EgitimKurslari,
    EgitimOgrencileri,
    EgitimOturumlari,
    EgitimQuizleri,
    EgitimSertifikalari,
    EgitimTeslimleri,
    EgitimYoklama,
)
from services import egitim as s
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Öğrenci/veli e-postaları (katalog dışı: yalnız e-posta, matris yok, push yok).
OGRENCI_OLAYI = "egitim_ogrenci"
#: Sahibine (müşteride hesap + `egitim` izinli ekip; ajansta yöneticiler).
SAHIP_KAYIT = "egitim_kayit"
AJANS_KAPSAMI = "@ajans"
VARSAYILAN_OGRENCI_SINIRI = 200
VARSAYILAN_KURS_SINIRI = 10
VARSAYILAN_AI_HAKKI = 50
#: Zamanlı turda en çok bu kadar hatırlatma oturumu / sertifika.
TUR_SINIRI = 50


def kapsam_anahtari(hesap: Optional[str]) -> str:
    return (hesap or "").strip().lower() or AJANS_KAPSAMI


async def hesap_ayarlari(db: AsyncSession, hesap: Optional[str]) -> Optional[EgitimAyarlari]:
    return (await db.execute(select(EgitimAyarlari).where(EgitimAyarlari.kapsam == kapsam_anahtari(hesap)))).scalars().first()


async def modul_ayari(db: AsyncSession, hesap: Optional[str], ad: str, varsayilan: Any) -> Any:
    """Müşteride modül ayarı; ajansta (hesap yok) sınır yok → None."""
    if not hesap:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, s.MODUL, ad)
    return varsayilan if deger is None else deger


# ---------------------------------------------------------------------------
# Okuma yardımcıları
# ---------------------------------------------------------------------------
async def oturumlar(db: AsyncSession, kurs_id: int) -> List[EgitimOturumlari]:
    return list((await db.execute(select(EgitimOturumlari).where(EgitimOturumlari.kurs_id == kurs_id)
                                  .order_by(EgitimOturumlari.baslangic, EgitimOturumlari.id))).scalars().all())


async def dersler(db: AsyncSession, kurs_id: int, yalniz_yayinda: bool = False) -> List[EgitimDersleri]:
    sorgu = select(EgitimDersleri).where(EgitimDersleri.kurs_id == kurs_id)
    if yalniz_yayinda:
        sorgu = sorgu.where(EgitimDersleri.yayinda.is_(True))
    return list((await db.execute(sorgu.order_by(EgitimDersleri.sira, EgitimDersleri.id))).scalars().all())


async def quizler(db: AsyncSession, kurs_id: int, yalniz_yayinda: bool = False) -> List[EgitimQuizleri]:
    sorgu = select(EgitimQuizleri).where(EgitimQuizleri.kurs_id == kurs_id)
    if yalniz_yayinda:
        sorgu = sorgu.where(EgitimQuizleri.yayinda.is_(True))
    return list((await db.execute(sorgu.order_by(EgitimQuizleri.sira, EgitimQuizleri.id))).scalars().all())


def kurs_bitis_ani(k: EgitimKurslari, son_oturum: Optional[datetime] = None) -> datetime:
    """Saklama süresinin ve öğrenci bağlantısı ömrünün başladığı an."""
    adaylar = []
    if k.bitis_tarihi:
        adaylar.append(datetime.combine(k.bitis_tarihi, time(23, 59), tzinfo=s.UTC))
    if son_oturum:
        adaylar.append(s.utc(son_oturum))
    if not adaylar:
        adaylar.append(s.utc(k.created_at) + timedelta(days=365))
    return max(adaylar)


async def son_oturum_ani(db: AsyncSession, kurs_id: int) -> Optional[datetime]:
    # func.max SQLite'ta metin döndürüyor: sıralı tek satır (sütun türüyle) okunuyor.
    return (await db.execute(select(EgitimOturumlari.bitis).where(EgitimOturumlari.kurs_id == kurs_id)
                             .order_by(EgitimOturumlari.bitis.desc()).limit(1))).scalar()


# ---------------------------------------------------------------------------
# Kayıt ve koltuk
# ---------------------------------------------------------------------------
async def dolu_koltuklar(db: AsyncSession, kurs_id: int) -> Set[int]:
    return {int(k) for (k,) in (await db.execute(select(EgitimOgrencileri.koltuk).where(
        EgitimOgrencileri.kurs_id == kurs_id, EgitimOgrencileri.koltuk.isnot(None)))).all()}


async def aktif_sayisi(db: AsyncSession, kurs_id: int) -> int:
    return int((await db.execute(select(func.count(EgitimOgrencileri.id)).where(
        EgitimOgrencileri.kurs_id == kurs_id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False)))).scalar() or 0)


def bos_koltuk(kapasite: int, dolu: Set[int]) -> Optional[int]:
    for i in range(int(kapasite)):
        if i not in dolu:
            return i
    return None


async def kilitle(db: AsyncSession, k: EgitimKurslari) -> None:
    """Okuma işlemini kapat, kurs satırını kilitle (kilit UPDATE'i yeni işlemin İLK ifadesi)."""
    await db.commit()
    await db.execute(update(EgitimKurslari).where(EgitimKurslari.id == k.id).values(kilit=EgitimKurslari.kilit + 1)
                     .execution_options(synchronize_session=False))


async def ogrenci_siniri_denetle(db: AsyncSession, hesap: Optional[str], ek: int = 1) -> None:
    sinir = await modul_ayari(db, hesap, "ogrenci_siniri", VARSAYILAN_OGRENCI_SINIRI)
    if sinir is None:
        return
    sayi = int((await db.execute(select(func.count(EgitimOgrencileri.id)).where(
        EgitimOgrencileri.hesap_email == hesap, EgitimOgrencileri.durum.in_(("aktif", "bekleme")),
        EgitimOgrencileri.anonim.is_(False)))).scalar() or 0)
    if sayi + ek > int(sinir):
        raise s.EgitimHatasi("ogrenci_siniri", durum=409, sinir=int(sinir))


@dataclass
class KayitGirdisi:
    ad: str
    eposta: Optional[str]
    telefon: Optional[str] = None
    cocuk: bool = False
    veli_ad: Optional[str] = None
    veli_telefon: Optional[str] = None
    veli_eposta: Optional[str] = None
    dil: str = "tr"
    kaynak: str = "form"
    pazarlama_izni: bool = False
    notlar: Optional[str] = None
    #: Elle eklerken "bekleme" istenebilir; kapasite yoksa da bekleme.
    durum: Optional[str] = None


async def _yinelenen_mi(db: AsyncSession, k: EgitimKurslari, g: KayitGirdisi) -> bool:
    kosul = [EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum.in_(("aktif", "bekleme")),
             EgitimOgrencileri.anonim.is_(False)]
    if g.eposta:
        kosul.append(EgitimOgrencileri.eposta == g.eposta)
    elif g.veli_eposta:
        kosul += [EgitimOgrencileri.veli_eposta == g.veli_eposta, func.lower(EgitimOgrencileri.ad) == g.ad.lower()]
    else:
        return False
    return (await db.execute(select(EgitimOgrencileri.id).where(*kosul).limit(1))).first() is not None


async def benzersiz_kod(db: AsyncSession) -> str:
    for _ in range(20):
        kod = s.kod_uret(s.OGRENCI_KODU_UZUNLUGU)
        if (await db.execute(select(EgitimOgrencileri.id).where(EgitimOgrencileri.kod == kod).limit(1))).first() is None:
            return kod
    raise s.EgitimHatasi("kod_uretilemedi", durum=503)


async def kayit_olustur(db: AsyncSession, k: EgitimKurslari, g: KayitGirdisi) -> EgitimOgrencileri:
    """Kilitli kayıt; doluysa bekleme listesi (kapalıysa 409 `dolu`). COMMIT eder."""
    await kilitle(db, k)
    try:
        if await _yinelenen_mi(db, k, g):
            raise s.EgitimHatasi("zaten_kayitli", "eposta", durum=409)
        if k.hesap_email:
            await ogrenci_siniri_denetle(db, k.hesap_email)
        koltuk: Optional[int] = None
        durum = "aktif" if g.durum != "bekleme" else "bekleme"
        if durum == "aktif" and k.kapasite is not None:
            koltuk = bos_koltuk(int(k.kapasite), await dolu_koltuklar(db, k.id))
            if koltuk is None:
                if not k.bekleme_listesi and g.kaynak == "form":
                    raise s.EgitimHatasi("dolu", durum=409)
                durum = "bekleme"
        an = s.simdi()
        cocuk = bool(g.cocuk)
        o = EgitimOgrencileri(
            kurs_id=k.id, hesap_email=k.hesap_email, kod=await benzersiz_kod(db), ad=g.ad, eposta=g.eposta or None,
            telefon=g.telefon, cocuk=cocuk, veli_ad=g.veli_ad if cocuk else None,
            veli_telefon=g.veli_telefon if cocuk else None, veli_eposta=g.veli_eposta if cocuk else None,
            durum=durum, kaynak=g.kaynak, koltuk=koltuk if durum == "aktif" else None, notlar=g.notlar,
            dil=g.dil if g.dil in s.DILLER else k.dil, aydinlatma_at=an if g.kaynak == "form" else None,
            # KVKK: 18 yaş altına pazarlama izni sorulmaz/yazılmaz.
            pazarlama_izni_at=an if g.pazarlama_izni and not cocuk else None,
            pazarlama_metin_surumu=_pazarlama_surumu(g.dil) if g.pazarlama_izni and not cocuk else None,
            portal_surumu=1, devamsizlik_sayisi=0, anonim=False, created_at=an,
        )
        db.add(o)
        await db.flush()
        await db.commit()
    except s.TemelHata:
        await db.rollback()
        await db.refresh(k)  # geri alma nesneleri bayatlatır; çağıran (CSV döngüsü) kursu okumaya devam ediyor
        raise
    except IntegrityError:
        await db.rollback()
        await db.refresh(k)
        raise s.EgitimHatasi("dolu", durum=409)
    await db.refresh(o)
    return o


def _pazarlama_surumu(dil: str) -> str:
    from services import pazarlama_izni

    return pazarlama_izni.surum_etiketi(dil)


async def bekleyenleri_al(db: AsyncSession, k: EgitimKurslari) -> List[int]:
    """Boş koltuk oldukça sıradaki bekleyeni aktif yapar. Commit ÇAĞIRANA. Döner: aktifleşen kimlikler."""
    if k.kapasite is None:
        bekleyenler = (await db.execute(select(EgitimOgrencileri).where(
            EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "bekleme", EgitimOgrencileri.anonim.is_(False))
            .order_by(EgitimOgrencileri.id))).scalars().all()
        for o in bekleyenler:
            o.durum = "aktif"
        return [o.id for o in bekleyenler]
    dolu = await dolu_koltuklar(db, k.id)
    alinan: List[int] = []
    while True:
        koltuk = bos_koltuk(int(k.kapasite), dolu)
        if koltuk is None:
            break
        o = (await db.execute(select(EgitimOgrencileri).where(
            EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "bekleme", EgitimOgrencileri.anonim.is_(False))
            .order_by(EgitimOgrencileri.id).limit(1))).scalars().first()
        if o is None:
            break
        o.durum, o.koltuk = "aktif", koltuk
        dolu.add(koltuk)
        alinan.append(o.id)
        await db.flush()
    return alinan


async def durum_degistir(db: AsyncSession, k: EgitimKurslari, o: EgitimOgrencileri, durum: str) -> List[int]:
    """Panelden durum geçişi. aktif ← bekleme/ayrıldı: koltuk gerekir (yoksa 409 `dolu`); ayrıldı: koltuk
    boşalır ve sıradaki bekleyen aktif olur. Commit ÇAĞIRANA. Döner: aktifleşen bekleyenler."""
    if durum == o.durum:
        return []
    alinan: List[int] = []
    if durum == "aktif":
        if k.kapasite is not None:
            koltuk = bos_koltuk(int(k.kapasite), await dolu_koltuklar(db, k.id))
            if koltuk is None:
                raise s.EgitimHatasi("dolu", "durum", durum=409)
            o.koltuk = koltuk
        o.durum, o.ayrilma_at = "aktif", None
        return alinan
    eski = o.durum
    o.durum, o.koltuk = durum, None
    if durum == "ayrildi":
        o.ayrilma_at = s.simdi()
    await db.flush()
    if eski == "aktif" and durum == "ayrildi":
        alinan = await bekleyenleri_al(db, k)
    return alinan


async def ogrenci_sil(db: AsyncSession, k: EgitimKurslari, o: EgitimOgrencileri) -> List[int]:
    """KVKK silme talebi: öğrencinin bütün kayıtları (ilerleme, yoklama, deneme, teslim + dosyaları,
    sertifika) ve kendisi silinir; koltuk boşalınca sıradaki bekleyen aktif olur. COMMIT eder."""
    aktifti = o.durum == "aktif"
    teslim_idleri = [i for (i,) in (await db.execute(select(EgitimTeslimleri.id).where(EgitimTeslimleri.ogrenci_id == o.id))).all()]
    await dosyalari_sil(db, (await db.execute(select(EgitimDosyalari).where(
        EgitimDosyalari.teslim_id.in_(teslim_idleri or [-1])))).scalars().all())
    for model in (EgitimIlerleme, EgitimYoklama, EgitimDenemeleri, EgitimTeslimleri, EgitimSertifikalari):
        await db.execute(delete(model).where(model.ogrenci_id == o.id).execution_options(synchronize_session=False))
    await _bildirimleri_anonimlestir(db, [o.id])
    await db.delete(o)
    await db.flush()
    alinan = await bekleyenleri_al(db, k) if aktifti else []
    await db.commit()
    return alinan


# ---------------------------------------------------------------------------
# İstatistik ve sertifika koşulları
# ---------------------------------------------------------------------------
async def istatistik(db: AsyncSession, k: EgitimKurslari, ogrenciler: Sequence[EgitimOgrencileri],
                     an: Optional[datetime] = None) -> Dict[int, Dict[str, Any]]:
    """Öğrenci başına: ilerleme %, quiz ortalaması (en iyi deneme), yoklama %, devamsızlık, koşullar."""
    an = an or s.simdi()
    idler = [o.id for o in ogrenciler]
    sonuc: Dict[int, Dict[str, Any]] = {}
    if not idler:
        return sonuc
    ders_idleri = [d.id for d in await dersler(db, k.id, yalniz_yayinda=True)]
    tamam: Dict[int, int] = {}
    if ders_idleri:
        for oid, n in (await db.execute(select(EgitimIlerleme.ogrenci_id, func.count(EgitimIlerleme.id)).where(
                EgitimIlerleme.ogrenci_id.in_(idler), EgitimIlerleme.ders_id.in_(ders_idleri))
                .group_by(EgitimIlerleme.ogrenci_id))).all():
            tamam[int(oid)] = int(n)
    quiz_idleri = [q.id for q in await quizler(db, k.id, yalniz_yayinda=True) if q.tur == "quiz"]
    en_iyi: Dict[Tuple[int, int], int] = {}
    if quiz_idleri:
        for qid, oid, p in (await db.execute(select(EgitimDenemeleri.quiz_id, EgitimDenemeleri.ogrenci_id,
                                                    func.max(EgitimDenemeleri.puan)).where(
                EgitimDenemeleri.quiz_id.in_(quiz_idleri), EgitimDenemeleri.ogrenci_id.in_(idler),
                EgitimDenemeleri.durum.in_(("tamamlandi", "suresi_doldu")))
                .group_by(EgitimDenemeleri.quiz_id, EgitimDenemeleri.ogrenci_id))).all():
            en_iyi[(int(qid), int(oid))] = int(p or 0)
    biten = [o for o in await oturumlar(db, k.id) if o.durum == "planli" and s.utc(o.bitis) < an]
    yoklama: Dict[Tuple[int, int], str] = {}
    if biten:
        for otid, oid, d in (await db.execute(select(EgitimYoklama.oturum_id, EgitimYoklama.ogrenci_id, EgitimYoklama.durum)
                                              .where(EgitimYoklama.kurs_id == k.id, EgitimYoklama.ogrenci_id.in_(idler)))).all():
            yoklama[(int(otid), int(oid))] = d
    sertifikalar = {int(oid): (kod, iptal) for oid, kod, iptal in (await db.execute(
        select(EgitimSertifikalari.ogrenci_id, EgitimSertifikalari.kod, EgitimSertifikalari.iptal_at)
        .where(EgitimSertifikalari.kurs_id == k.id, EgitimSertifikalari.ogrenci_id.in_(idler)))).all()}
    for o in ogrenciler:
        ilerleme = int(round(100 * tamam.get(o.id, 0) / len(ders_idleri))) if ders_idleri else 100
        quiz = int(round(sum(en_iyi.get((q, o.id), 0) for q in quiz_idleri) / len(quiz_idleri))) if quiz_idleri else None
        ilgili = [x for x in biten if s.utc(x.bitis) > s.utc(o.created_at)]
        izinli = sum(1 for x in ilgili if yoklama.get((x.id, o.id)) == "izinli")
        katildi = sum(1 for x in ilgili if yoklama.get((x.id, o.id)) in s.KATILDI)
        payda = len(ilgili) - izinli
        yuzde = int(round(100 * katildi / payda)) if payda > 0 else None
        kosul = {
            "ilerleme": {"deger": ilerleme, "esik": int(k.kosul_ilerleme), "tamam": ilerleme >= int(k.kosul_ilerleme)},
            "quiz": {"deger": quiz, "esik": int(k.kosul_quiz), "tamam": quiz is None or quiz >= int(k.kosul_quiz)},
            "yoklama": {"deger": yuzde, "esik": int(k.kosul_yoklama), "tamam": yuzde is None or yuzde >= int(k.kosul_yoklama)},
        }
        sert = sertifikalar.get(o.id)
        sonuc[o.id] = {
            "ilerleme": ilerleme, "tamamlanan_ders": tamam.get(o.id, 0), "ders_sayisi": len(ders_idleri),
            "quiz_ortalama": quiz, "yoklama": yuzde, "katildi": katildi, "oturum": payda, "devamsizlik": max(0, payda - katildi),
            "kosullar": kosul, "uygun": bool(k.sertifika_aktif) and o.durum == "aktif" and not o.anonim and all(v["tamam"] for v in kosul.values()),
            "sertifika": sert[0] if sert and sert[1] is None else None,
        }
    return sonuc


async def benzersiz_sertifika_kodu(db: AsyncSession) -> str:
    for _ in range(20):
        kod = s.kod_uret(s.SERTIFIKA_KODU_UZUNLUGU)
        if (await db.execute(select(EgitimSertifikalari.id).where(EgitimSertifikalari.kod == kod).limit(1))).first() is None:
            return kod
    raise s.EgitimHatasi("kod_uretilemedi", durum=503)


async def sertifika_ver(db: AsyncSession, k: EgitimKurslari, o: EgitimOgrencileri, *, kaynak: str = "elle",
                        zorla: bool = False, ist: Optional[Dict[str, Any]] = None) -> Tuple[EgitimSertifikalari, bool]:
    """(sertifika, yeni mi). Koşul yoksa 409 `kosul_saglanmadi` (zorla değilse). Commit ÇAĞIRANA."""
    if o.anonim or o.durum != "aktif":
        raise s.EgitimHatasi("ogrenci_aktif_degil", durum=409)
    if not k.sertifika_aktif:
        raise s.EgitimHatasi("sertifika_kapali", durum=409)
    mevcut = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.kurs_id == k.id,
                                                                 EgitimSertifikalari.ogrenci_id == o.id))).scalars().first()
    if mevcut is not None and mevcut.iptal_at is None:
        return mevcut, False
    if not zorla:
        ist = ist or (await istatistik(db, k, [o])).get(o.id) or {}
        if not ist.get("uygun"):
            raise s.EgitimHatasi("kosul_saglanmadi", durum=409, kosullar=ist.get("kosullar"))
    an = s.simdi()
    ayar = await hesap_ayarlari(db, k.hesap_email)
    if mevcut is not None:  # iptal edilmişti: yeniden geçerli (aynı kod)
        mevcut.iptal_at, mevcut.verilme_at, mevcut.ad_maskeli = None, an, s.ad_maskele(o.ad)
        o.tamamlandi_at = an
        return mevcut, False
    sert = EgitimSertifikalari(
        kurs_id=k.id, ogrenci_id=o.id, hesap_email=k.hesap_email, kod=await benzersiz_sertifika_kodu(db),
        ad_maskeli=s.ad_maskele(o.ad), kurs_adi=k.ad, kurum_adi=(ayar.kurum_adi if ayar else None), verilme_at=an,
        kaynak=kaynak, created_at=an,
    )
    db.add(sert)
    o.tamamlandi_at = an
    await db.flush()
    return sert, True


# ---------------------------------------------------------------------------
# Yoklama
# ---------------------------------------------------------------------------
async def yoklama_yaz(db: AsyncSession, k: EgitimKurslari, ot: EgitimOturumlari, o: EgitimOgrencileri, durum: str,
                      kaynak: str, yapan: Optional[str], ust_yaz: bool = False) -> Tuple[str, EgitimYoklama]:
    """("yeni" | "guncellendi" | "zaten", satır). Okutmada (`ust_yaz=False`) katıldı işaretliyse dokunulmaz.
    Commit ÇAĞIRANA."""
    an = s.simdi()
    mevcut = (await db.execute(select(EgitimYoklama).where(EgitimYoklama.oturum_id == ot.id,
                                                           EgitimYoklama.ogrenci_id == o.id))).scalars().first()
    if mevcut is not None:
        if not ust_yaz and mevcut.durum in s.KATILDI:
            return "zaten", mevcut
        if mevcut.durum == durum and ust_yaz:
            return "zaten", mevcut
        mevcut.durum, mevcut.kaynak, mevcut.zaman, mevcut.yapan = durum, kaynak, an, (yapan or None) and yapan[:254]
        return "guncellendi", mevcut
    satir = EgitimYoklama(kurs_id=k.id, oturum_id=ot.id, ogrenci_id=o.id, durum=durum, kaynak=kaynak, zaman=an,
                          yapan=(yapan or None) and yapan[:254])
    try:
        async with db.begin_nested():
            db.add(satir)
            await db.flush()
    except IntegrityError:
        mevcut = (await db.execute(select(EgitimYoklama).where(EgitimYoklama.oturum_id == ot.id,
                                                               EgitimYoklama.ogrenci_id == o.id))).scalars().first()
        return "zaten", mevcut
    return "yeni", satir


def okutma_durumu(ot: EgitimOturumlari, an: Optional[datetime] = None) -> str:
    an = an or s.simdi()
    return "gec" if an > s.utc(ot.baslangic) + s.GEC_ESIGI else "var"


async def sayac(db: AsyncSession, k: EgitimKurslari, ot: EgitimOturumlari) -> Dict[str, Any]:
    toplam = await aktif_sayisi(db, k.id)
    giren = int((await db.execute(select(func.count(EgitimYoklama.id)).join(
        EgitimOgrencileri, EgitimOgrencileri.id == EgitimYoklama.ogrenci_id).where(
        EgitimYoklama.oturum_id == ot.id, EgitimYoklama.durum.in_(s.KATILDI), EgitimOgrencileri.durum == "aktif"))).scalar() or 0)
    return {"toplam": toplam, "giren": giren, "kalan": max(0, toplam - giren), "kapasite": k.kapasite, "turler": []}


async def okut(db: AsyncSession, k: EgitimKurslari, ot: EgitimOturumlari, ham: Any, yapan: Optional[str]) -> Dict[str, Any]:
    """Eğitmen öğrencinin QR'ını (ya da kodunu) okutur. Sonuç etkinlik okutucusuyla aynı sözlük
    (`components/etkinlik/Okutucu.tsx` yeniden kullanılıyor): gecerli | zaten_girdi | gecersiz | iptal
    (öğrenci aktif değil) | farkli_etkinlik (başka kursun öğrencisi) | etkinlik_iptal (oturum iptal)."""
    kod, _ = s.okutma_coz(ham)
    an = s.simdi()
    o: Optional[EgitimOgrencileri] = None
    if kod is not None:
        o = (await db.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.kod == kod))).scalars().first()
    satir: Optional[EgitimYoklama] = None
    if o is None or o.anonim:
        sonuc = "gecersiz"
    elif o.kurs_id != k.id:
        sonuc = "farkli_etkinlik"
    elif ot.durum == "iptal":
        sonuc = "etkinlik_iptal"
    elif o.durum != "aktif":
        sonuc = "iptal"
    else:
        ne, satir = await yoklama_yaz(db, k, ot, o, okutma_durumu(ot, an), "okutma", yapan)
        sonuc = "zaten_girdi" if ne == "zaten" else "gecerli"
    ayrinti = None
    if o is not None and o.kurs_id == k.id and not o.anonim:
        ayrinti = {"kod": o.kod, "tur": k.ad, "ad": o.ad, "giris_at": s.iso(satir.zaman) if satir is not None else None}
    await db.commit()
    return {"sonuc": sonuc, "bilet": ayrinti, "sayac": await sayac(db, k, ot), "zaman": s.iso(an)}


async def devamsizlik_denetle(db: AsyncSession, k: EgitimKurslari, an: Optional[datetime] = None) -> List[int]:
    """Aktif öğrencilerin devamsızlık sayısını günceller; eşiğe İLK ulaşanda `devamsizlik_uyari_at` yazılır
    (olay ve e-posta bir kez). Commit ÇAĞIRANA. Döner: uyarılacak öğrenci kimlikleri."""
    an = an or s.simdi()
    ogrenciler = (await db.execute(select(EgitimOgrencileri).where(
        EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False)))).scalars().all()
    if not ogrenciler:
        return []
    ist = await istatistik(db, k, ogrenciler, an)
    uyarilacak: List[int] = []
    for o in ogrenciler:
        n = int(ist.get(o.id, {}).get("devamsizlik", 0))
        if int(o.devamsizlik_sayisi or 0) != n:
            o.devamsizlik_sayisi = n
        if int(k.devamsizlik_esik or 0) > 0 and n >= int(k.devamsizlik_esik) and o.devamsizlik_uyari_at is None:
            o.devamsizlik_uyari_at = an
            uyarilacak.append(o.id)
    await db.flush()
    return uyarilacak


# ---------------------------------------------------------------------------
# Dosyalar (ders ekleri, ödev teslimleri) — services/dosya_deposu
# ---------------------------------------------------------------------------
async def dosya_kaydet(db: AsyncSession, k: EgitimKurslari, *, ad_ham: str, veri: bytes, yukleyen: Optional[str],
                       ders_id: Optional[int] = None, teslim_id: Optional[int] = None) -> EgitimDosyalari:
    """Tür içerikten doğrulanır (`services/dosyalar.turu_dogrula`), içerik kalıcı depoya. Commit ÇAĞIRANA."""
    import secrets

    from services import dosya_deposu, dosyalar

    try:
        ad = dosyalar.ad_temizle(ad_ham)
        mime = dosyalar.turu_dogrula(ad, veri)
    except dosyalar.DosyaHatasi as h:
        raise s.EgitimHatasi(h.kod, "dosya", durum=h.durum)
    an = s.simdi()
    anahtar = f"egitim/{an:%Y/%m}/{secrets.token_hex(16)}"
    try:
        depo = await dosya_deposu.yaz(db, anahtar, veri, mime)
    except dosya_deposu.DepoHatasi:
        raise s.EgitimHatasi("depo_hatasi", "dosya", durum=502)
    d = EgitimDosyalari(kurs_id=k.id, ders_id=ders_id, teslim_id=teslim_id, ad=ad, tur=mime, boyut=len(veri), depo=depo,
                        anahtar=anahtar, yukleyen=(yukleyen or None) and yukleyen[:254], created_at=an)
    db.add(d)
    await db.flush()
    return d


async def dosyalari_sil(db: AsyncSession, kayitlar: Iterable[EgitimDosyalari]) -> None:
    from services import dosya_deposu

    for d in list(kayitlar):
        try:
            await dosya_deposu.sil(db, d.depo, d.anahtar)
        except Exception:  # noqa: BLE001 - depo silinemezse satır yine gider (yetim içerik zararsız)
            logger.warning("Eğitim dosyası depodan silinemedi (%s)", d.id)
        await db.delete(d)


# ---------------------------------------------------------------------------
# E-postalar
# ---------------------------------------------------------------------------
def alicilar(o: EgitimOgrencileri) -> List[Tuple[str, bool]]:
    """[(e-posta, veli mi)] — 18 yaş altında veli (+ varsa öğrencinin kendi adresi)."""
    sonuc: List[Tuple[str, bool]] = []
    if o.cocuk and o.veli_eposta:
        sonuc.append((o.veli_eposta, True))
    if o.eposta and o.eposta not in {a for a, _ in sonuc}:
        sonuc.append((o.eposta, False))
    return sonuc


def _oturum():
    from core.database import db_manager

    return db_manager.async_session_maker() if db_manager.async_session_maker else None


async def _ogrenciye(db: AsyncSession, alici: str, konu: str, govde: str, ref_id: int, gizliler: Sequence[str] = (),
                     ekler: Optional[List[Dict[str, Any]]] = None, hesap: Optional[str] = None) -> None:
    """Öğrenciye/veliye yalnız e-posta: panel içi kopya silinir; öğrenci bağlantısı (yetki belgesi)
    kalıcı bildirim kaydından çıkarılır. Faz 4L: `hesap` (kursun sahibi) marka teması açıksa
    e-postanın HTML sürümünde marka başlığı (logo + ana renk)."""
    from services.marka import eposta_eki
    from services.notify import dispatch

    ek = await eposta_eki(db, hesap, konu, govde, {"ekler": ekler} if ekler else None)
    satirlar = await dispatch(db, event_type=OGRENCI_OLAYI, title=konu, body=govde,
                              recipients=[{"email": alici, "role": "client"}], link=None, ref_type="egitim_ogrencileri",
                              ref_id=ref_id, eposta_ek=ek)
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


async def _yukle(db: AsyncSession, ogrenci_id: int) -> Tuple[Optional[EgitimOgrencileri], Optional[EgitimKurslari]]:
    o = (await db.execute(select(EgitimOgrencileri).where(EgitimOgrencileri.id == ogrenci_id))).scalars().first()
    if o is None or o.anonim:
        return None, None
    k = (await db.execute(select(EgitimKurslari).where(EgitimKurslari.id == o.kurs_id))).scalars().first()
    return o, k


async def _gonder(db: AsyncSession, o: EgitimOgrencileri, k: EgitimKurslari, konu_anahtari: str, govde_satirlari: Sequence[str],
                  *, giris: str, portal: bool = True, ekler: Optional[List[Dict[str, Any]]] = None,
                  ek_gizli: Sequence[str] = (), konu_metni: Optional[str] = None) -> int:
    """Öğrenciye ve (18 yaş altında) veliye aynı e-posta. Döner: gönderilen sayı."""
    dil = o.dil if o.dil in s.DILLER else k.dil
    m = s.metinler(dil)
    ayar = await hesap_ayarlari(db, k.hesap_email)
    jeton = s.ogrenci_jetonu(o.id, int(o.portal_surumu or 1), o.kod)
    adres = s.portal_adresi(jeton)
    n = 0
    for alici, veli in alicilar(o):
        satirlar = [m["merhaba"].format(ad=(o.veli_ad if veli else o.ad) or "—"), "", giris, ""]
        if veli:
            satirlar += [m["veli_not"].format(ogrenci=o.ad or "—"), ""]
        satirlar += list(govde_satirlari)
        if portal:
            satirlar += ["", m["portal"], adres]
        satirlar += ["", s.imza_satiri(k, ayar.kurum_adi if ayar else None)]
        konu = konu_metni or m[konu_anahtari].format(kurs=k.ad, odev="")
        try:
            await _ogrenciye(db, alici, konu, "\n".join(satirlar), o.id, [adres, jeton, *ek_gizli], ekler, hesap=k.hesap_email)
            n += 1
        except Exception:  # noqa: BLE001
            logger.exception("Eğitim e-postası gönderilemedi (%s)", o.id)
    return n


async def ogrenci_epostasi(ogrenci_id: int, tur: str = "kayit") -> None:
    """`kayit` (program .ics ekli) | `bekleme` | `yer` (bekleme → aktif) | `portal` (bağlantı yeniden)."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            o, k = await _yukle(db, ogrenci_id)
            if o is None or k is None:
                return
            dil = o.dil if o.dil in s.DILLER else k.dil
            m = s.metinler(dil)
            satirlar: List[str] = []
            ekler: List[Dict[str, Any]] = []
            gizli: List[str] = []
            if tur in ("kayit", "yer"):
                program = [x for x in await oturumlar(db, k.id) if x.durum == "planli"]
                ilk = next((x for x in program if s.utc(x.bitis) > s.simdi()), None)
                if ilk is not None:
                    satirlar.append(f"{m['ilk_ders']}: {s.aralik_yaz(ilk.baslangic, ilk.bitis, k.saat_dilimi, dil)}")
                satirlar.append(f"{m['nerede']}: {s.konum_metni(k, dil, ogrenciye=True)}")
                if k.bicim in ("online", "karma") and k.online_baglanti:
                    gizli.append(k.online_baglanti)
                if k.fiyat_metni:
                    satirlar += ["", f"{m['fiyat']}: {k.fiyat_metni}"]
                if program:
                    ekler.append({"dosya_adi": "ders-programi.ics",
                                  "icerik": s.ics_uret(k, program, dil, ogrenciye=True),
                                  "tur": "text/calendar; method=PUBLISH; charset=UTF-8"})
                giris = m["kayit_giris" if tur == "kayit" else "yer_giris"].format(kurs=k.ad)
                konu = "kayit_konu" if tur == "kayit" else "yer_konu"
            elif tur == "bekleme":
                sira = int((await db.execute(select(func.count(EgitimOgrencileri.id)).where(
                    EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "bekleme",
                    EgitimOgrencileri.id <= o.id))).scalar() or 1)
                giris, konu = m["bekleme_giris"].format(kurs=k.ad, sira=sira), "bekleme_konu"
            else:
                giris, konu = m["portal_giris"].format(kurs=k.ad), "portal_konu"
            await _gonder(db, o, k, konu, satirlar, giris=giris, ekler=ekler or None, ek_gizli=gizli)
    except Exception:  # noqa: BLE001
        logger.exception("Eğitim öğrenci e-postası gönderilemedi (%s, %s)", ogrenci_id, tur)


async def ogrenci_epostalari(idler: Sequence[int], tur: str) -> None:
    for i in idler:
        await ogrenci_epostasi(i, tur)


async def duyuru_gonder(duyuru_id: int) -> int:
    """Kursun aktif öğrencilerine (18 yaş altında velisine) bilgilendirme duyurusu — pazarlama değil."""
    oturum = _oturum()
    if oturum is None:
        return 0
    n = 0
    try:
        async with oturum as db:
            d = (await db.execute(select(EgitimDuyurulari).where(EgitimDuyurulari.id == duyuru_id))).scalars().first()
            if d is None:
                return 0
            k = (await db.execute(select(EgitimKurslari).where(EgitimKurslari.id == d.kurs_id))).scalars().first()
            if k is None:
                return 0
            ogrenciler = (await db.execute(select(EgitimOgrencileri).where(
                EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False))
                .order_by(EgitimOgrencileri.id).limit(2000))).scalars().all()
            for o in ogrenciler:
                dil = o.dil if o.dil in s.DILLER else k.dil
                m = s.metinler(dil)
                n += await _gonder(db, o, k, "kayit_konu", [m["duyuru_not"].format(kurs=k.ad)], giris=d.metin,
                                   konu_metni=f"{k.ad}: {d.konu}")
    except Exception:  # noqa: BLE001
        logger.exception("Eğitim duyurusu gönderilemedi (%s)", duyuru_id)
    return n


async def devamsizlik_epostalari(idler: Sequence[int]) -> None:
    oturum = _oturum()
    if oturum is None:
        return
    for i in idler:
        try:
            async with oturum as db:
                o, k = await _yukle(db, i)
                if o is None or k is None:
                    continue
                dil = o.dil if o.dil in s.DILLER else k.dil
                m = s.metinler(dil)
                giris = m["devamsizlik_giris"].format(ogrenci=o.ad or "—", kurs=k.ad, sayi=int(o.devamsizlik_sayisi or 0))
                await _gonder(db, o, k, "devamsizlik_konu", [], giris=giris)
        except Exception:  # noqa: BLE001
            logger.exception("Devamsızlık e-postası gönderilemedi (%s)", i)


async def sertifika_epostasi(sertifika_id: int) -> None:
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            sert = (await db.execute(select(EgitimSertifikalari).where(EgitimSertifikalari.id == sertifika_id))).scalars().first()
            if sert is None or sert.iptal_at is not None:
                return
            o, k = await _yukle(db, sert.ogrenci_id)
            if o is None or k is None:
                return
            dil = o.dil if o.dil in s.DILLER else k.dil
            m = s.metinler(dil)
            await _gonder(db, o, k, "sertifika_konu", [m["dogrulama"], s.sertifika_adresi(sert.kod)],
                          giris=m["sertifika_giris"].format(kurs=k.ad))
    except Exception:  # noqa: BLE001
        logger.exception("Sertifika e-postası gönderilemedi (%s)", sertifika_id)


async def not_epostasi(teslim_id: int) -> None:
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            t = (await db.execute(select(EgitimTeslimleri).where(EgitimTeslimleri.id == teslim_id))).scalars().first()
            if t is None:
                return
            q = (await db.execute(select(EgitimQuizleri).where(EgitimQuizleri.id == t.quiz_id))).scalars().first()
            o, k = await _yukle(db, t.ogrenci_id)
            if q is None or o is None or k is None:
                return
            dil = o.dil if o.dil in s.DILLER else k.dil
            m = s.metinler(dil)
            satirlar = []
            if t.puan is not None:
                satirlar.append(f"{m['puan']}: {int(t.puan)}/100")
            if t.geri_bildirim:
                satirlar += ["", f"{m['geri_bildirim']}:", t.geri_bildirim]
            # Konu ödevin adını taşır.
            for alici, veli in alicilar(o):
                ayar = await hesap_ayarlari(db, k.hesap_email)
                jeton = s.ogrenci_jetonu(o.id, int(o.portal_surumu or 1), o.kod)
                adres = s.portal_adresi(jeton)
                govde = [m["merhaba"].format(ad=(o.veli_ad if veli else o.ad) or "—"), "",
                         m["not_giris"].format(kurs=k.ad, odev=q.baslik), ""]
                if veli:
                    govde += [m["veli_not"].format(ogrenci=o.ad or "—"), ""]
                govde += satirlar + ["", m["portal"], adres, "", s.imza_satiri(k, ayar.kurum_adi if ayar else None)]
                await _ogrenciye(db, alici, m["not_konu"].format(odev=q.baslik), "\n".join(govde), o.id, [adres, jeton],
                                 hesap=k.hesap_email)
    except Exception:  # noqa: BLE001
        logger.exception("Ödev notu e-postası gönderilemedi (%s)", teslim_id)


async def sahip_bildirimi(ogrenci_id: int) -> None:
    """Yeni kayıt — sahibine (müşteride hesap + `egitim` izinli ekip; ajans kursunda yöneticiler)."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            from services import notify

            o, k = await _yukle(db, ogrenci_id)
            if o is None or k is None:
                return
            baslik = f"Yeni kayıt: {o.ad or '—'} — {k.ad}" + (" (bekleme listesi)" if o.durum == "bekleme" else "")
            satirlar = [f"Kurs: {k.ad}", f"Öğrenci: {o.ad or '—'}", f"E-posta: {o.eposta or '—'}",
                        f"Telefon: {o.telefon or '—'}", f"Durum: {o.durum}", f"Öğrenci kodu: {o.kod}"]
            if o.cocuk:
                satirlar += [f"Veli: {o.veli_ad or '—'}", f"Veli e-posta: {o.veli_eposta or '—'}",
                             f"Veli telefon: {o.veli_telefon or '—'}"]
            baslik, govde = await notify.render(db, SAHIP_KAYIT, baslik, "\n".join(satirlar), {"ad": o.ad or "", "kurs": k.ad})
            if k.hesap_email:
                alici_listesi = [{"email": k.hesap_email, "role": "client"}]
                baglanti = "/client?sekme=egitim"
            else:
                alici_listesi = await notify.admin_recipients(db)
                baglanti = "/admin?sekme=egitim"
            await notify.dispatch(db, event_type=SAHIP_KAYIT, title=baslik, body=govde, recipients=alici_listesi,
                                  link=baglanti, ref_type="egitim_ogrencileri", ref_id=o.id)
    except Exception:  # noqa: BLE001
        logger.exception("Eğitim sahip bildirimi gönderilemedi (%s)", ogrenci_id)


# ---------------------------------------------------------------------------
# Hatırlatma (zamanlı)
# ---------------------------------------------------------------------------
async def hatirlatmalar(db: AsyncSession, an: Optional[datetime] = None) -> int:
    """Ders başlamadan `hatirlatma_saat` önce aktif öğrencilere (velisine) hatırlatma — oturum başına bir kez."""
    an = an or s.simdi()
    kurslar = (await db.execute(select(EgitimKurslari).where(
        EgitimKurslari.hatirlatma_saat > 0, EgitimKurslari.durum == "yayinda"))).scalars().all()
    gonderilen = 0
    islenen = 0
    for k in kurslar:
        adaylar = (await db.execute(select(EgitimOturumlari).where(
            EgitimOturumlari.kurs_id == k.id, EgitimOturumlari.durum == "planli", EgitimOturumlari.hatirlatma_at.is_(None),
            EgitimOturumlari.baslangic > an, EgitimOturumlari.baslangic <= an + timedelta(hours=int(k.hatirlatma_saat)))
            .order_by(EgitimOturumlari.baslangic))).scalars().all()
        for ot in adaylar:
            if islenen >= TUR_SINIRI:
                return gonderilen
            islenen += 1
            ot.hatirlatma_at = an
            await db.commit()
            ogrenciler = (await db.execute(select(EgitimOgrencileri).where(
                EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "aktif",
                EgitimOgrencileri.anonim.is_(False)))).scalars().all()
            for o in ogrenciler:
                dil = o.dil if o.dil in s.DILLER else k.dil
                m = s.metinler(dil)
                satirlar = [f"{m['ne_zaman']}: {s.aralik_yaz(ot.baslangic, ot.bitis, k.saat_dilimi, dil)}"]
                if ot.konu:
                    satirlar.append(ot.konu)
                satirlar.append(f"{m['nerede']}: {s.konum_metni(k, dil, ogrenciye=True)}")
                gizli = [k.online_baglanti] if k.online_baglanti else []
                gonderilen += await _gonder(db, o, k, "hatirlatma_konu", satirlar,
                                            giris=m["hatirlatma_giris"].format(kurs=k.ad), ek_gizli=gizli)
    return gonderilen


# ---------------------------------------------------------------------------
# Anonimleştirme (KVKK — saklama süresi)
# ---------------------------------------------------------------------------
KISISEL_BOS = {"ad": None, "eposta": None, "telefon": None, "veli_ad": None, "veli_telefon": None, "veli_eposta": None,
               "notlar": None, "pazarlama_izni_at": None, "pazarlama_metin_surumu": None, "koltuk": None, "anonim": True}


async def anonimlestir(db: AsyncSession, k: Optional[EgitimKurslari] = None, hemen: bool = False) -> int:
    """Saklama süresi (kurs bitişinden) dolan kayıtların kişisel alanları silinir: ad, iletişim, veli
    bilgisi, eğitmen notu, ödev teslim metni ve dosyaları, quiz yanıtları. Sayılar (ilerleme, yoklama,
    puan) istatistik için kalır; sertifika doğrulaması maskeli adla sürer. Commit ETMEZ."""
    an = s.simdi()
    kurslar = [k] if k is not None else (await db.execute(select(EgitimKurslari))).scalars().all()
    toplam = 0
    for x in kurslar:
        if not hemen:
            bitis = kurs_bitis_ani(x, await son_oturum_ani(db, x.id))
            if bitis + timedelta(days=max(1, int(x.saklama_gun or s.VARSAYILAN_SAKLAMA_GUN))) > an:
                continue
        idler = [i for (i,) in (await db.execute(select(EgitimOgrencileri.id).where(
            EgitimOgrencileri.kurs_id == x.id, EgitimOgrencileri.anonim.is_(False)))).all()]
        if not idler:
            continue
        sonuc = await db.execute(update(EgitimOgrencileri).where(EgitimOgrencileri.id.in_(idler))
                                 .values(**KISISEL_BOS).execution_options(synchronize_session=False))
        toplam += int(sonuc.rowcount or 0)
        teslimler = [i for (i,) in (await db.execute(select(EgitimTeslimleri.id).where(EgitimTeslimleri.ogrenci_id.in_(idler)))).all()]
        if teslimler:
            await dosyalari_sil(db, (await db.execute(select(EgitimDosyalari).where(EgitimDosyalari.teslim_id.in_(teslimler)))).scalars().all())
            await db.execute(update(EgitimTeslimleri).where(EgitimTeslimleri.id.in_(teslimler))
                             .values(metin=None, geri_bildirim=None).execution_options(synchronize_session=False))
        await db.execute(update(EgitimDenemeleri).where(EgitimDenemeleri.ogrenci_id.in_(idler))
                         .values(yanitlar=None).execution_options(synchronize_session=False))
        await db.execute(update(EgitimYoklama).where(EgitimYoklama.ogrenci_id.in_(idler))
                         .values(yapan=None).execution_options(synchronize_session=False))
        await _bildirimleri_anonimlestir(db, idler)
    return toplam


async def _bildirimleri_anonimlestir(db: AsyncSession, idler: Sequence[int]) -> None:
    from models.notifications import Notifications

    kosul = (Notifications.ref_type == "egitim_ogrencileri", Notifications.ref_id.in_(list(idler)))
    await db.execute(delete(Notifications).where(*kosul, Notifications.event_type == OGRENCI_OLAYI)
                     .execution_options(synchronize_session=False))
    await db.execute(update(Notifications).where(*kosul)
                     .values(title="Eğitim kaydı (kişisel bilgiler saklama süresi dolunca silindi)", body=None)
                     .execution_options(synchronize_session=False))


# ---------------------------------------------------------------------------
# "AI ile soru üret" hakkı
# ---------------------------------------------------------------------------
def ay_anahtari(an: Optional[datetime] = None) -> str:
    return (an or s.simdi()).strftime("%Y-%m")


async def _ai_satiri(db: AsyncSession, hesap: str, ay: str) -> EgitimAiKullanimi:
    for _ in range(3):
        satir = (await db.execute(select(EgitimAiKullanimi).where(EgitimAiKullanimi.hesap == hesap,
                                                                  EgitimAiKullanimi.ay == ay))).scalars().first()
        if satir is not None:
            return satir
        try:
            async with db.begin_nested():
                db.add(EgitimAiKullanimi(hesap=hesap, ay=ay, sayi=0, kredi=0.0, created_at=s.simdi()))
                await db.flush()
        except IntegrityError:
            pass
    raise s.EgitimHatasi("sayac_hatasi", durum=503)


@dataclass
class AiHakki:
    satir_id: int
    hesap: str
    kredi: float = 0.0


async def ai_ozeti(db: AsyncSession, hesap: Optional[str]) -> Dict[str, Any]:
    h = (hesap or "").strip().lower()
    satir = (await db.execute(select(EgitimAiKullanimi).where(EgitimAiKullanimi.hesap == h,
                                                              EgitimAiKullanimi.ay == ay_anahtari()))).scalars().first()
    hak = await modul_ayari(db, h or None, "ai_hakki", VARSAYILAN_AI_HAKKI)
    asim = await modul_ayari(db, h or None, "kredi_ile_asim", False)
    return {"hazir": s.ai_hazir(), "hak": hak, "kullanilan": int(satir.sayi) if satir else 0,
            "kredi_ile_asim": bool(asim) if h else False, "uretim_kredisi": s.AI_KREDI}


async def ai_hak_ayir(db: AsyncSession, hesap: Optional[str], kisi: Optional[str]) -> AiHakki:
    """Bir üretim hakkı: 429 `butce_doldu` (site geneli günlük), 409 `ai_hakki_doldu`, 402 `kredi_yetersiz`."""
    from services import yapay_zeka as ai

    h = (hesap or "").strip().lower()
    hak = await modul_ayari(db, h or None, "ai_hakki", VARSAYILAN_AI_HAKKI)
    asim = bool(await modul_ayari(db, h or None, "kredi_ile_asim", False)) if h else False
    satir = await _ai_satiri(db, h, ay_anahtari())
    await db.commit()
    kredi = 0.0
    if hak is not None:
        artti = await db.execute(update(EgitimAiKullanimi).where(EgitimAiKullanimi.id == satir.id,
                                                                 EgitimAiKullanimi.sayi < int(hak))
                                 .values(sayi=EgitimAiKullanimi.sayi + 1).execution_options(synchronize_session=False))
        await db.commit()
        if not artti.rowcount:
            if not asim:
                raise s.EgitimHatasi("ai_hakki_doldu", durum=409, sinir=int(hak))
            from fastapi import HTTPException

            from services import kredi as kredi_servisi

            try:
                await kredi_servisi.harca(db, eposta=h, saat=s.AI_KREDI, olusturan=kisi,
                                          aciklama=f"Eğitim: AI ile soru üretimi ({ay_anahtari()}, dahil hak aşımı)")
            except HTTPException as hata:
                if hata.status_code != 409:
                    raise
                raise s.EgitimHatasi("kredi_yetersiz", durum=402, kredi=s.AI_KREDI)
            kredi = s.AI_KREDI
            await db.execute(update(EgitimAiKullanimi).where(EgitimAiKullanimi.id == satir.id).values(
                sayi=EgitimAiKullanimi.sayi + 1, kredi=EgitimAiKullanimi.kredi + kredi).execution_options(synchronize_session=False))
            await db.commit()
    else:
        await db.execute(update(EgitimAiKullanimi).where(EgitimAiKullanimi.id == satir.id)
                         .values(sayi=EgitimAiKullanimi.sayi + 1).execution_options(synchronize_session=False))
        await db.commit()
    if not await ai.sayac_artir(db, s.AI_KAPSAM, s.AI_GUNLUK_BUTCE):
        await ai_hak_iade(db, AiHakki(satir.id, h, kredi))
        raise s.EgitimHatasi("butce_doldu", durum=429)
    return AiHakki(satir.id, h, kredi)


async def ai_hak_iade(db: AsyncSession, hak: AiHakki) -> None:
    """Model hata verdi: sayaç ve (düşüldüyse) kredi geri."""
    try:
        await db.execute(update(EgitimAiKullanimi).where(EgitimAiKullanimi.id == hak.satir_id, EgitimAiKullanimi.sayi > 0)
                         .values(sayi=EgitimAiKullanimi.sayi - 1, kredi=EgitimAiKullanimi.kredi - hak.kredi)
                         .execution_options(synchronize_session=False))
        await db.commit()
        if hak.kredi and hak.hesap:
            from services import kredi as kredi_servisi

            await kredi_servisi.yukle(db, eposta=hak.hesap, saat=hak.kredi, tur="iade",
                                      aciklama="Eğitim: AI soru üretilemedi — iade")
    except Exception:  # noqa: BLE001
        logger.exception("Eğitim AI hakkı iade edilemedi")
        await db.rollback()


# ---------------------------------------------------------------------------
# Zamanlı bakım
# ---------------------------------------------------------------------------
async def zamanli_bakim(db: AsyncSession) -> Dict[str, Any]:
    """Her tur: ders hatırlatmaları, devamsızlık eşiği (bir kez bilgilendirme + olay), biten kurs →
    tamamlandı (+ "otomatik sertifika" açıksa koşulu sağlayanlara sertifika), saklama süresi dolan
    kişisel veri."""
    an = s.simdi()
    hatirlatma = await hatirlatmalar(db, an)
    uyarilar: List[int] = []
    for k in (await db.execute(select(EgitimKurslari).where(EgitimKurslari.durum == "yayinda",
                                                            EgitimKurslari.devamsizlik_esik > 0).limit(300))).scalars().all():
        try:
            uyarilar += await devamsizlik_denetle(db, k, an)
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Devamsızlık denetlenemedi (%s)", k.id)
            await db.rollback()
    await devamsizlik_epostalari(uyarilar)
    bugun = an.date()
    biten = (await db.execute(select(EgitimKurslari).where(EgitimKurslari.durum == "yayinda",
                                                           EgitimKurslari.bitis_tarihi.isnot(None),
                                                           EgitimKurslari.bitis_tarihi < bugun).limit(100))).scalars().all()
    sertifika_idleri: List[int] = []
    for k in biten:
        if k.otomatik_sertifika and k.sertifika_aktif:
            ogrenciler = (await db.execute(select(EgitimOgrencileri).where(
                EgitimOgrencileri.kurs_id == k.id, EgitimOgrencileri.durum == "aktif", EgitimOgrencileri.anonim.is_(False))
                .limit(1000))).scalars().all()
            ist = await istatistik(db, k, ogrenciler, an)
            for o in ogrenciler:
                if len(sertifika_idleri) >= 500 or not ist.get(o.id, {}).get("uygun"):
                    continue
                try:
                    sert, yeni = await sertifika_ver(db, k, o, kaynak="otomatik", ist=ist.get(o.id))
                    if yeni:
                        sertifika_idleri.append(sert.id)
                except s.TemelHata:
                    continue
        k.durum = "tamamlandi"
        await db.commit()
    for sid in sertifika_idleri:
        await sertifika_epostasi(sid)
    anonim = await anonimlestir(db)
    await db.commit()  # 0 satırda da: açık yazma işlemi (SQLite kilidi) kalmasın
    return {"hatirlatma": hatirlatma, "devamsizlik": len(uyarilar), "tamamlanan": len(biten),
            "sertifika": len(sertifika_idleri), "anonimlestirilen": anonim}


__all__ = [
    "kayit_olustur", "KayitGirdisi", "bekleyenleri_al", "durum_degistir", "ogrenci_sil", "istatistik", "sertifika_ver",
    "yoklama_yaz", "okut", "sayac", "devamsizlik_denetle", "anonimlestir", "zamanli_bakim", "ai_hak_ayir", "ai_hak_iade",
]
