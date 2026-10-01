"""Faz 2G — müşteri ↔ ajans mesajlaşma (neredeyse gerçek zamanlı, kısa yoklama).

Taraflar
--------
* `client` — müşteri hesabı (sahip + `mesajlar` izni olan ekip üyeleri). Kayıt
  sahibi hesap (`hesap_email`), yazan kişi ayrıca (`yazan_email`).
* `admin` — ajans yöneticileri (role=admin); bütün hesapların konuşmalarını görür.

Gerçek zamanlıya yakınlık
-------------------------
WebSocket/SSE yok: Cloudflare Pages vekili ve uyuyan ücretsiz sunucu bunları
güvenilir taşımıyor. Ön yüz kısa yoklama yapıyor (sohbet açıkken 4–5 sn,
panel açıkken 30–60 sn yalnız özet). Yoklama ucu ucuz: `?sonra=<son_id>` ile
yalnız yeni mesajlar; değişiklik yoksa boş liste + iki sayı. Eski bir mesaj
düzenlenir/silinirse konuşmanın `degisiklik` sayacı artıyor, ön yüz son
pencereyi yeniden çekiyor.

Okunmamış
---------
Kişi başına `konusma_okunma.son_okunan_mesaj_id`; yalnız ileri gidiyor
(koşullu UPDATE). Okunmamış = karşı taraftan, silinmemiş, o kimlikten büyük
mesajlar. Yazan kendi mesajını okumuş sayılıyor.

Bildirim (toplama)
------------------
Mesaj gönderilince bildirim GİTMİYOR. Zamanlı görev (5 dk; GitHub Actions 10
dk'da bir uyandırıyor) ve panelin yoklama isteği (en çok dakikada bir, arka
planda) `bildirimleri_isle`yi çalıştırıyor:

* Karşı taraftan kimse okumadıysa ve okunmamışların İLKİ en az 2 dakikalıksa
  → tek bildirim (Web Push + tercihe göre e-posta; e-postada ilk mesajın ilk
  200 karakteri ve panele bağlantı).
* Aynı konuşmada son bildirimden bu yana 30 dakika geçmediyse yenisi
  gönderilmiyor; o arada gelenler bir sonraki bildirimde toplanıyor.
* Okunduysa hiç gönderilmiyor (kapsandı olarak işaretleniyor).
* Gönderimden ÖNCE koşullu UPDATE ile "talep" ediliyor: zamanlı görev ile
  istek tetiklemesi aynı anda çalışsa da aynı mesajlar iki kez bildirilmez.

Müşteri tarafında alıcı hesap sahibi; `mesajlar` izni olan aktif ekip
üyeleri 2E'nin `dispatch` genişletmesiyle (OLAY_IZNI) kendiliğinden ekleniyor.
"""

import asyncio
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.mesajlar import KonusmaMesajlari, KonusmaOkunma, Konusmalar
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TARAFLAR = ("admin", "client")
DURUMLAR = ("acik", "arsiv")
OLAY = "mesaj_yeni"
IZIN = "mesajlar"

METIN_SINIRI = 5000
KONU_SINIRI = 200
OZET_SINIRI = 200
EK_SINIRI = 5
DUZENLEME_SURESI = timedelta(minutes=15)
BILDIRIM_GECIKMESI = timedelta(minutes=2)
TOPLAMA_SURESI = timedelta(minutes=30)
ONIZLEME_SINIRI = 200
SAYFA = 50
EN_COK_SAYFA = 200
#: Müşterinin açabileceği en çok açık konuşma (kötüye kullanım sınırı).
EN_COK_ACIK_KONUSMA = 50
#: Yönetici listesinde en çok bu kadar konuşma.
LISTE_SINIRI = 200
#: Ekler bu klasöre (müşteriye görünür) yazılıyor; Dosyalar sekmesinde de durur.
MESAJ_KLASORU = "Mesajlar"
GENEL_KONU = "Genel"
#: Yoklama isteğiyle bildirim taraması en çok bu sıklıkta (süreç başına).
TETIK_ARALIGI_SN = 60.0
#: Testler kapatabilsin diye modül düzeyinde.
ISTEKLE_TETIKLE = True


class MesajHatasi(Exception):
    """Uca çevrilecek hata: HTTP durumu + kod (ön yüz yedi dilde metin kuruyor)."""

    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Optional[datetime]) -> Optional[str]:
    a = utc(an)
    return a.isoformat() if a else None


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def karsi(taraf: str) -> str:
    return "client" if taraf == "admin" else "admin"


def site_adresi() -> str:
    return (os.environ.get("SITE_PUBLIC_URL") or "https://mehmetkuru.dev").rstrip("/")


_DENETIM_KARAKTERI = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#: Yön gömme/geçersiz kılma/yalıtma karakterleri (RLO vb.): bir bağlantıyı ya da
#: dosya adını olduğundan başka gösterebilir ("fatura‮gpj.exe").
_YON_KARAKTERI = re.compile("[‪-‮⁦-⁩]")


def metin_temizle(ham: Any, sinir: int = METIN_SINIRI) -> str:
    """Düz metin: satır sonları `\\n`, denetim karakterleri (sekme/satır hariç) yok.

    HTML olduğu gibi METİN olarak saklanıyor; ön yüz hiçbir zaman HTML olarak
    çizmiyor (React metin düğümü). Uzunsa 400 `metin_uzun`.
    """
    metin = unicodedata.normalize("NFC", str(ham or ""))
    metin = metin.replace("\r\n", "\n").replace("\r", "\n")
    metin = _DENETIM_KARAKTERI.sub("", metin)
    metin = _YON_KARAKTERI.sub("", metin)
    metin = metin.strip()
    if len(metin) > sinir:
        raise MesajHatasi(400, "metin_uzun", sinir=sinir)
    return metin


def konu_temizle(ham: Any) -> str:
    konu = " ".join(metin_temizle(ham, sinir=10_000).split())
    return konu[:KONU_SINIRI]


def ozet_metni(metin: str, ekler: Sequence[Dict[str, Any]] = ()) -> str:
    duz = " ".join((metin or "").split())
    if not duz and ekler:
        duz = "📎 " + ", ".join(str(e.get("ad") or "") for e in ekler)
    return duz if len(duz) <= OZET_SINIRI else duz[: OZET_SINIRI - 1] + "…"


def ekleri_coz(ham: Optional[str]) -> List[Dict[str, Any]]:
    try:
        deger = json.loads(ham) if ham else []
    except (TypeError, ValueError):
        return []
    if not isinstance(deger, list):
        return []
    sonuc = []
    for e in deger:
        if isinstance(e, dict) and isinstance(e.get("id"), int):
            sonuc.append({"id": e["id"], "ad": str(e.get("ad") or ""), "boyut": int(e.get("boyut") or 0), "tur": e.get("tur")})
    return sonuc


def duzenlenebilir_mi(m: KonusmaMesajlari, an: Optional[datetime] = None) -> bool:
    olusma = utc(m.created_at)
    return bool(not m.silindi and olusma is not None and (an or simdi()) - olusma <= DUZENLEME_SURESI)


# ---------------------------------------------------------------------------
# Sözlükler
# ---------------------------------------------------------------------------
def konusma_sozlugu(
    k: Konusmalar, *, okunmamis: int = 0, hesap_adi: Optional[str] = None, yonetici: bool = False
) -> Dict[str, Any]:
    d = {
        "id": k.id,
        "hesap_email": k.hesap_email,
        "konu": k.konu,
        "genel": bool(k.tekil_anahtar),
        "proje_id": k.proje_id,
        "durum": k.durum,
        "son_mesaj_at": iso(k.son_mesaj_at),
        "son_mesaj_id": k.son_mesaj_id,
        "son_mesaj_ozet": k.son_mesaj_ozet,
        "son_mesaj_rol": k.son_mesaj_rol,
        "okunmamis": int(okunmamis or 0),
        "created_at": iso(k.created_at),
    }
    if yonetici:
        d["hesap_adi"] = hesap_adi
        d["olusturan"] = k.olusturan
    return d


def mesaj_sozlugu(m: KonusmaMesajlari, *, bakan_taraf: str, kisi: str, an: Optional[datetime] = None) -> Dict[str, Any]:
    silindi = bool(m.silindi)
    benim = m.yazan_rol == bakan_taraf and eposta_duzelt(m.yazan_email) == kisi
    bitis = utc(m.created_at) + DUZENLEME_SURESI if m.created_at else None
    return {
        "id": m.id,
        "konusma_id": m.konusma_id,
        "yazan_rol": m.yazan_rol,
        "yazan_ad": m.yazan_ad,
        # Müşteriye ajans çalışanının e-postası gösterilmiyor (yalnız adı).
        "yazan_email": m.yazan_email if (bakan_taraf == "admin" or m.yazan_rol == "client") else None,
        "benim": benim,
        "metin": "" if silindi else (m.metin or ""),
        "ekler": [] if silindi else ekleri_coz(m.ekler),
        "silindi": silindi,
        "duzenlendi_at": iso(m.duzenlendi_at),
        "created_at": iso(m.created_at),
        "duzenleme_bitis": iso(bitis) if (benim and duzenlenebilir_mi(m, an)) else None,
    }


# ---------------------------------------------------------------------------
# Konuşmalar
# ---------------------------------------------------------------------------
def genel_anahtari(hesap: str) -> str:
    return f"genel:{hesap}"


async def genel_konusma(db: AsyncSession, hesap: str, olusturan: Optional[str] = None) -> Konusmalar:
    """Hesabın "Genel" konuşması; yoksa açar (eş zamanlı açılışta tek kalır)."""
    anahtar = genel_anahtari(hesap)
    k = (await db.execute(select(Konusmalar).where(Konusmalar.tekil_anahtar == anahtar))).scalars().first()
    if k is not None:
        return k
    k = Konusmalar(
        hesap_email=hesap,
        konu=GENEL_KONU,
        durum="acik",
        tekil_anahtar=anahtar,
        olusturan=olusturan or None,
        created_at=simdi(),
        degisiklik=0,
    )
    db.add(k)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        k = (await db.execute(select(Konusmalar).where(Konusmalar.tekil_anahtar == anahtar))).scalars().one()
        return k
    await db.refresh(k)
    return k


async def proje_dogrula(db: AsyncSession, hesap: str, proje_id: Optional[int]) -> Optional[int]:
    """Proje bu hesabın mı? Değilse 404 (başkasının projesinin varlığı sızmasın)."""
    if proje_id is None:
        return None
    from models.projects import Projects

    satir = (
        await db.execute(
            select(Projects.id).where(Projects.id == int(proje_id), func.lower(Projects.client_email) == hesap)
        )
    ).first()
    if satir is None:
        raise MesajHatasi(404, "proje_yok")
    return int(proje_id)


async def konusma_ac(
    db: AsyncSession, *, hesap: str, konu: Any, proje_id: Optional[int], olusturan: str, musteri: bool
) -> Konusmalar:
    konu_metni = konu_temizle(konu)
    if not konu_metni:
        if proje_id is None:
            return await genel_konusma(db, hesap, olusturan)
        raise MesajHatasi(400, "konu_gerekli")
    proje = await proje_dogrula(db, hesap, proje_id)
    if musteri:
        acik = (
            await db.execute(
                select(func.count(Konusmalar.id)).where(Konusmalar.hesap_email == hesap, Konusmalar.durum == "acik")
            )
        ).scalar()
        if int(acik or 0) >= EN_COK_ACIK_KONUSMA:
            raise MesajHatasi(409, "konusma_siniri")
    k = Konusmalar(
        hesap_email=hesap,
        konu=konu_metni,
        proje_id=proje,
        durum="acik",
        olusturan=olusturan or None,
        created_at=simdi(),
        degisiklik=0,
    )
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return k


async def konusma_bul(db: AsyncSession, konusma_id: int, hesap: Optional[str] = None) -> Konusmalar:
    """`hesap` verilirse yalnız o hesabın konuşması; başkasınınki "yok" (404)."""
    k = (await db.execute(select(Konusmalar).where(Konusmalar.id == konusma_id))).scalars().first()
    if k is None or (hesap is not None and k.hesap_email != hesap):
        raise MesajHatasi(404, "konusma_yok")
    return k


async def okunmamis_sayilari(db: AsyncSession, konusma_idler: Iterable[int], kisi: str, taraf: str) -> Dict[int, int]:
    idler = sorted({int(i) for i in konusma_idler})
    if not idler:
        return {}
    M, O = KonusmaMesajlari, KonusmaOkunma
    satirlar = (
        await db.execute(
            select(M.konusma_id, func.count(M.id))
            .select_from(M)
            .outerjoin(O, and_(O.konusma_id == M.konusma_id, O.kisi_email == kisi))
            .where(
                M.konusma_id.in_(idler),
                M.silindi.is_(False),
                M.yazan_rol != taraf,
                M.id > func.coalesce(O.son_okunan_mesaj_id, 0),
            )
            .group_by(M.konusma_id)
        )
    ).all()
    return {int(k): int(s) for k, s in satirlar}


def _karsi_son_sutunu(taraf: str):
    """Kişinin tarafına göre karşı tarafın son mesaj kimliği sütunu."""
    return Konusmalar.son_client_mesaj_id if taraf == "admin" else Konusmalar.son_admin_mesaj_id


async def okunmamis_adaylari(db: AsyncSession, kisi: str, taraf: str, hesap: Optional[str] = None) -> List[int]:
    """Karşı tarafın son mesajı kişinin okuduğundan ileride olan konuşmalar (mesaj taramadan)."""
    O = KonusmaOkunma
    sorgu = (
        select(Konusmalar.id)
        .outerjoin(O, and_(O.konusma_id == Konusmalar.id, O.kisi_email == kisi))
        .where(func.coalesce(_karsi_son_sutunu(taraf), 0) > func.coalesce(O.son_okunan_mesaj_id, 0))
    )
    if hesap is not None:
        sorgu = sorgu.where(Konusmalar.hesap_email == hesap)
    return [int(r[0]) for r in (await db.execute(sorgu.limit(1000))).all()]


async def ozet(db: AsyncSession, kisi: str, taraf: str, hesap: Optional[str] = None) -> Dict[str, Any]:
    """Yoklama ucu: toplam okunmamış + listenin değişip değişmediğini anlatan iki sayı."""
    adaylar = await okunmamis_adaylari(db, kisi, taraf, hesap)
    sayilar = await okunmamis_sayilari(db, adaylar, kisi, taraf)
    sorgu = select(func.max(Konusmalar.son_mesaj_id), func.count(Konusmalar.id), func.coalesce(func.sum(Konusmalar.degisiklik), 0))
    if hesap is not None:
        sorgu = sorgu.where(Konusmalar.hesap_email == hesap)
    son, adet, degisiklik = (await db.execute(sorgu)).one()
    return {
        "okunmamis": sum(sayilar.values()),
        "okunmamis_konusma": sum(1 for v in sayilar.values() if v),
        "son_mesaj_id": int(son or 0),
        "konusma_sayisi": int(adet or 0),
        "degisiklik": int(degisiklik or 0),
    }


def _siralama():
    return (func.coalesce(Konusmalar.son_mesaj_at, Konusmalar.created_at).desc(), Konusmalar.id.desc())


async def musteri_konusmalari(db: AsyncSession, hesap: str, kisi: str) -> List[Dict[str, Any]]:
    await genel_konusma(db, hesap, kisi)
    satirlar = list(
        (await db.execute(select(Konusmalar).where(Konusmalar.hesap_email == hesap).order_by(*_siralama()).limit(LISTE_SINIRI)))
        .scalars()
        .all()
    )
    sayilar = await okunmamis_sayilari(db, [k.id for k in satirlar], kisi, "client")
    return [konusma_sozlugu(k, okunmamis=sayilar.get(k.id, 0)) for k in satirlar]


async def yonetici_konusmalari(
    db: AsyncSession,
    kisi: str,
    *,
    durum: Optional[str] = None,
    q: Optional[str] = None,
    okunmamis: bool = False,
    hesap: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from services.hesap_ekibi import hesap_adlari

    sorgu = select(Konusmalar)
    if durum in DURUMLAR:
        sorgu = sorgu.where(Konusmalar.durum == durum)
    if hesap:
        sorgu = sorgu.where(Konusmalar.hesap_email == eposta_duzelt(hesap))
    aranan = " ".join((q or "").split())[:100].lower()
    if aranan:
        desen = f"%{aranan.replace('%', '').replace('_', '')}%"
        mesajda = (
            select(KonusmaMesajlari.id)
            .where(
                KonusmaMesajlari.konusma_id == Konusmalar.id,
                KonusmaMesajlari.silindi.is_(False),
                func.lower(KonusmaMesajlari.metin).like(desen),
            )
            .exists()
        )
        sorgu = sorgu.where(
            or_(func.lower(Konusmalar.konu).like(desen), func.lower(Konusmalar.hesap_email).like(desen), mesajda)
        )
    if okunmamis:
        adaylar = await okunmamis_adaylari(db, kisi, "admin")
        if not adaylar:
            return []
        sorgu = sorgu.where(Konusmalar.id.in_(adaylar))
    satirlar = list((await db.execute(sorgu.order_by(*_siralama()).limit(LISTE_SINIRI))).scalars().all())
    sayilar = await okunmamis_sayilari(db, [k.id for k in satirlar], kisi, "admin")
    if okunmamis:
        satirlar = [k for k in satirlar if sayilar.get(k.id)]
    adlar = await hesap_adlari(db, [k.hesap_email for k in satirlar])
    return [
        konusma_sozlugu(k, okunmamis=sayilar.get(k.id, 0), hesap_adi=adlar.get(k.hesap_email), yonetici=True)
        for k in satirlar
    ]


# ---------------------------------------------------------------------------
# Mesajlar
# ---------------------------------------------------------------------------
async def karsi_okunan(db: AsyncSession, konusma_id: int, taraf: str) -> int:
    """Karşı taraftan herhangi birinin okuduğu en ileri mesaj ("okundu" işareti)."""
    deger = (
        await db.execute(
            select(func.max(KonusmaOkunma.son_okunan_mesaj_id)).where(
                KonusmaOkunma.konusma_id == konusma_id, KonusmaOkunma.taraf == karsi(taraf)
            )
        )
    ).scalar()
    return int(deger or 0)


async def benim_okudugum(db: AsyncSession, konusma_id: int, kisi: str) -> int:
    deger = (
        await db.execute(
            select(KonusmaOkunma.son_okunan_mesaj_id).where(
                KonusmaOkunma.konusma_id == konusma_id, KonusmaOkunma.kisi_email == kisi
            )
        )
    ).scalar()
    return int(deger or 0)


async def mesaj_listesi(
    db: AsyncSession,
    k: Konusmalar,
    *,
    taraf: str,
    kisi: str,
    sonra: Optional[int] = None,
    once: Optional[int] = None,
    adet: Optional[int] = None,
) -> Dict[str, Any]:
    """`sonra` → yalnız yeniler (artan); `once` → daha eskiler; ikisi de yoksa son pencere."""
    adet = max(1, min(int(adet or SAYFA), EN_COK_SAYFA))
    M = KonusmaMesajlari
    temel = select(M).where(M.konusma_id == k.id)
    daha_eski: Optional[bool] = None
    if sonra is not None:
        satirlar = list((await db.execute(temel.where(M.id > int(sonra)).order_by(M.id.asc()).limit(EN_COK_SAYFA))).scalars().all())
    else:
        if once is not None:
            temel = temel.where(M.id < int(once))
        satirlar = list((await db.execute(temel.order_by(M.id.desc()).limit(adet + 1))).scalars().all())
        daha_eski = len(satirlar) > adet
        satirlar = list(reversed(satirlar[:adet]))
    an = simdi()
    return {
        "konusma": {
            "id": k.id,
            "durum": k.durum,
            "degisiklik": int(k.degisiklik or 0),
            "son_mesaj_id": k.son_mesaj_id,
        },
        "mesajlar": [mesaj_sozlugu(m, bakan_taraf=taraf, kisi=kisi, an=an) for m in satirlar],
        "daha_eski": daha_eski,
        "karsi_okunan": await karsi_okunan(db, k.id, taraf),
        "okudugum": await benim_okudugum(db, k.id, kisi),
    }


async def ekleri_dogrula(db: AsyncSession, k: Konusmalar, *, taraf: str, kisi: str, idler: Any) -> List[Dict[str, Any]]:
    """Ek dosya kimlikleri: hepsi BU hesabın dosyası olmalı.

    Müşteri yalnız kendi sohbetten yüklediği dosyayı (`Mesajlar` klasörü,
    yükleyen kendisi) ekleyebilir: yoksa ekip klasöründeki ya da `dosyalar`
    izni olmadığı için göremediği bir dosyayı sohbete ekleyip indirebilirdi.
    """
    if not idler:
        return []
    if not isinstance(idler, (list, tuple)):
        raise MesajHatasi(400, "ek_gecersiz")
    temiz: List[int] = []
    for i in idler:
        if isinstance(i, bool) or not isinstance(i, int):
            raise MesajHatasi(400, "ek_gecersiz")
        if i not in temiz:
            temiz.append(i)
    if len(temiz) > EK_SINIRI:
        raise MesajHatasi(400, "cok_ek", sinir=EK_SINIRI)
    from models.dosyalar import Dosyalar

    satirlar = {d.id: d for d in (await db.execute(select(Dosyalar).where(Dosyalar.id.in_(temiz)))).scalars().all()}
    sonuc = []
    for i in temiz:
        d = satirlar.get(i)
        if d is None or d.client_email != k.hesap_email:
            raise MesajHatasi(400, "ek_gecersiz")
        if taraf == "client" and not (
            d.klasor == MESAJ_KLASORU and d.yukleyen_rol == "client" and eposta_duzelt(d.yukleyen) == kisi
        ):
            raise MesajHatasi(400, "ek_gecersiz")
        sonuc.append({"id": d.id, "ad": d.ad, "boyut": int(d.boyut or 0), "tur": d.tur})
    return sonuc


async def _okunmayi_ilerlet(db: AsyncSession, konusma_id: int, kisi: str, taraf: str, mesaj_id: int) -> None:
    """Yalnız ileri: koşullu UPDATE; satır yoksa ekle (yarışta tekrar dene). Commit etmez."""
    O = KonusmaOkunma
    an = simdi()
    sonuc = await db.execute(
        update(O)
        .where(O.konusma_id == konusma_id, O.kisi_email == kisi, O.son_okunan_mesaj_id < mesaj_id)
        .values(son_okunan_mesaj_id=mesaj_id, taraf=taraf, updated_at=an)
        .execution_options(synchronize_session=False)
    )
    if int(sonuc.rowcount or 0):
        return
    var = (await db.execute(select(O.id).where(O.konusma_id == konusma_id, O.kisi_email == kisi))).first()
    if var is not None:
        return  # zaten ileride
    try:
        async with db.begin_nested():
            db.add(O(konusma_id=konusma_id, kisi_email=kisi, taraf=taraf, son_okunan_mesaj_id=mesaj_id, updated_at=an))
            await db.flush()
    except IntegrityError:
        await db.execute(
            update(O)
            .where(O.konusma_id == konusma_id, O.kisi_email == kisi, O.son_okunan_mesaj_id < mesaj_id)
            .values(son_okunan_mesaj_id=mesaj_id, updated_at=an)
            .execution_options(synchronize_session=False)
        )


async def okundu(db: AsyncSession, k: Konusmalar, *, kisi: str, taraf: str, mesaj_id: int) -> int:
    """Okundu işareti; konuşmanın son mesajını geçemez. Geri gitmez. Yeni değeri döndürür."""
    hedef = min(max(0, int(mesaj_id or 0)), int(k.son_mesaj_id or 0))
    if hedef > 0:
        await _okunmayi_ilerlet(db, k.id, kisi, taraf, hedef)
        await db.commit()
    return await benim_okudugum(db, k.id, kisi)


async def mesaj_gonder(
    db: AsyncSession,
    k: Konusmalar,
    *,
    taraf: str,
    kisi: str,
    yazan_ad: Optional[str],
    metin: Any,
    ek_idler: Any = None,
) -> KonusmaMesajlari:
    temiz = metin_temizle(metin)
    ekler = await ekleri_dogrula(db, k, taraf=taraf, kisi=kisi, idler=ek_idler)
    if not temiz and not ekler:
        raise MesajHatasi(400, "bos_mesaj")
    an = simdi()
    m = KonusmaMesajlari(
        konusma_id=k.id,
        yazan_email=kisi,
        yazan_rol=taraf,
        yazan_ad=(yazan_ad or "")[:120] or None,
        metin=temiz,
        ekler=json.dumps(ekler, ensure_ascii=False) if ekler else None,
        silindi=False,
        created_at=an,
    )
    db.add(m)
    await db.flush()
    k.son_mesaj_at = an
    k.son_mesaj_id = max(int(k.son_mesaj_id or 0), m.id)
    k.son_mesaj_ozet = ozet_metni(temiz, ekler)
    k.son_mesaj_rol = taraf
    if taraf == "client":
        k.son_client_mesaj_id = max(int(k.son_client_mesaj_id or 0), m.id)
    else:
        k.son_admin_mesaj_id = max(int(k.son_admin_mesaj_id or 0), m.id)
    if k.durum != "acik":
        # Arşivdeki konuşmaya yazılınca yeniden açılıyor (e-posta zinciri gibi).
        k.durum = "acik"
    await _okunmayi_ilerlet(db, k.id, kisi, taraf, m.id)
    await db.commit()
    await db.refresh(m)
    return m


async def _son_alanlari_yenile(db: AsyncSession, k: Konusmalar) -> None:
    """Silme sonrası: son mesaj özeti ve taraf başına son kimlik (silinmemişlerden)."""
    M = KonusmaMesajlari
    son = (
        await db.execute(select(M).where(M.konusma_id == k.id, M.silindi.is_(False)).order_by(M.id.desc()).limit(1))
    ).scalars().first()
    k.son_mesaj_ozet = ozet_metni(son.metin, ekleri_coz(son.ekler)) if son else None
    k.son_mesaj_rol = son.yazan_rol if son else None
    for rol in TARAFLAR:
        deger = (
            await db.execute(
                select(func.max(M.id)).where(M.konusma_id == k.id, M.silindi.is_(False), M.yazan_rol == rol)
            )
        ).scalar()
        setattr(k, f"son_{rol}_mesaj_id", int(deger) if deger else None)


async def kendi_mesaji(db: AsyncSession, mesaj_id: int, *, taraf: str, kisi: str, hesap: Optional[str] = None) -> Tuple[KonusmaMesajlari, Konusmalar]:
    """Düzenleme/silme hedefi: yalnız kendi (aynı taraf + aynı kişi) mesajı, 15 dk içinde."""
    m = (await db.execute(select(KonusmaMesajlari).where(KonusmaMesajlari.id == mesaj_id))).scalars().first()
    if m is None:
        raise MesajHatasi(404, "mesaj_yok")
    k = await konusma_bul(db, m.konusma_id, hesap)
    if m.yazan_rol != taraf or eposta_duzelt(m.yazan_email) != kisi:
        raise MesajHatasi(403, "mesaj_sizin_degil")
    if m.silindi:
        raise MesajHatasi(409, "mesaj_silinmis")
    if not duzenlenebilir_mi(m):
        raise MesajHatasi(409, "duzenleme_suresi_doldu", dakika=int(DUZENLEME_SURESI.total_seconds() // 60))
    return m, k


async def mesaj_duzenle(db: AsyncSession, m: KonusmaMesajlari, k: Konusmalar, metin: Any) -> KonusmaMesajlari:
    temiz = metin_temizle(metin)
    if not temiz and not ekleri_coz(m.ekler):
        raise MesajHatasi(400, "bos_mesaj")
    m.metin = temiz
    m.duzenlendi_at = simdi()
    k.degisiklik = int(k.degisiklik or 0) + 1
    if k.son_mesaj_id == m.id:
        k.son_mesaj_ozet = ozet_metni(temiz, ekleri_coz(m.ekler))
    await db.commit()
    await db.refresh(m)
    return m


async def mesaj_sil(db: AsyncSession, m: KonusmaMesajlari, k: Konusmalar) -> KonusmaMesajlari:
    """Yumuşak silme: satır kalıyor ("bu mesaj silindi"), içerik ve ekler boşalıyor."""
    m.silindi = True
    m.metin = ""
    m.ekler = None
    m.duzenlendi_at = simdi()
    k.degisiklik = int(k.degisiklik or 0) + 1
    await db.flush()
    await _son_alanlari_yenile(db, k)
    await db.commit()
    await db.refresh(m)
    return m


async def ek_indirme(db: AsyncSession, mesaj_id: int, dosya_id: int, hesap: Optional[str] = None) -> Tuple[str, int]:
    """Mesajdaki ekin imzalı (15 dk) indirme yolu. Ek o mesajda değilse 404."""
    from services.dosyalar import imzali_yol

    m = (await db.execute(select(KonusmaMesajlari).where(KonusmaMesajlari.id == mesaj_id))).scalars().first()
    if m is None or m.silindi:
        raise MesajHatasi(404, "ek_yok")
    await konusma_bul(db, m.konusma_id, hesap)
    if dosya_id not in {e["id"] for e in ekleri_coz(m.ekler)}:
        raise MesajHatasi(404, "ek_yok")
    return imzali_yol(dosya_id)


async def konusma_sil(db: AsyncSession, k: Konusmalar) -> None:
    """Konuşma + mesajları + okunma satırları ORM ile siliniyor: çöp kutusu
    kancası hepsini aynı grupta yakalıyor (geri alınınca birlikte gelir)."""
    # Önce hepsi okunuyor, sonra siliniyor: araya giren bir sorgu (autoflush)
    # mesajları konuşmadan ÖNCEKİ bir flush'a bölerse çöp kutusu çocukları
    # ebeveynsiz sanıp yakalamazdı.
    mesajlar = list((await db.execute(select(KonusmaMesajlari).where(KonusmaMesajlari.konusma_id == k.id))).scalars().all())
    okunmalar = list((await db.execute(select(KonusmaOkunma).where(KonusmaOkunma.konusma_id == k.id))).scalars().all())
    await db.delete(k)
    for nesne in (*mesajlar, *okunmalar):
        await db.delete(nesne)
    await db.commit()


# ---------------------------------------------------------------------------
# Ad
# ---------------------------------------------------------------------------
async def ajans_adi(db: AsyncSession, eposta: str, jeton_adi: Optional[str] = None) -> str:
    """Ajans tarafında yazanın görünen adı: `staff` tablosunda varsa adı."""
    try:
        from models.staff import Staff

        ad = (
            await db.execute(
                select(Staff.ad).where(func.lower(Staff.email) == eposta, Staff.aktif.isnot(False)).limit(1)
            )
        ).scalar()
        if ad and str(ad).strip():
            return str(ad).strip()[:120]
    except Exception:  # noqa: BLE001 - ad süs; mesajı engellemesin
        logger.debug("Ekip adı okunamadı", exc_info=True)
    ad = (jeton_adi or "").strip()
    return ad[:120] if ad and "@" not in ad else "Ajans"


def musteri_adi(eposta: str, jeton_adi: Optional[str] = None) -> str:
    ad = (jeton_adi or "").strip()
    return ad[:120] if ad and "@" not in ad else eposta.split("@")[0][:120]


# ---------------------------------------------------------------------------
# Bildirimler (zamanlı görev + yoklama isteği)
# ---------------------------------------------------------------------------
_bildirim_kilidi = asyncio.Lock()
_son_tetik = 0.0


def _bildirim_sutunlari(alici_taraf: str):
    if alici_taraf == "admin":
        return Konusmalar.son_client_mesaj_id, Konusmalar.bildirilen_admin_mesaj_id, Konusmalar.bildirim_admin_at
    return Konusmalar.son_admin_mesaj_id, Konusmalar.bildirilen_client_mesaj_id, Konusmalar.bildirim_client_at


async def _taraf_okunan(db: AsyncSession, konusma_id: int, taraf: str) -> int:
    deger = (
        await db.execute(
            select(func.max(KonusmaOkunma.son_okunan_mesaj_id)).where(
                KonusmaOkunma.konusma_id == konusma_id, KonusmaOkunma.taraf == taraf
            )
        )
    ).scalar()
    return int(deger or 0)


async def _talep_et(db: AsyncSession, k_id: int, alici_taraf: str, eski: int, yeni: int, an: Optional[datetime]) -> bool:
    """Koşullu UPDATE: bildirilen kimliği `eski`yken `yeni` yap. Yarışı kazanan True."""
    _, bildirilen, zaman = _bildirim_sutunlari(alici_taraf)
    degerler: Dict[str, Any] = {bildirilen.key: yeni}
    if an is not None:
        degerler[zaman.key] = an
    sonuc = await db.execute(
        update(Konusmalar)
        .where(Konusmalar.id == k_id, func.coalesce(bildirilen, 0) == eski)
        .values(**degerler)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(sonuc.rowcount or 0) == 1


async def _bildirim_gonder(db: AsyncSession, k: Konusmalar, alici_taraf: str, mesajlar: List[KonusmaMesajlari]) -> None:
    from urllib.parse import quote

    from services.notify import admin_recipients, dispatch, render

    ilk, son = mesajlar[0], mesajlar[-1]
    sayi = len(mesajlar)
    yazan = ilk.yazan_ad or (ilk.yazan_email if ilk.yazan_rol == "client" else "Ajans")
    onizleme = " ".join((ilk.metin or "").split())
    if not onizleme:
        onizleme = "📎 " + ", ".join(e["ad"] for e in ekleri_coz(ilk.ekler))
    if len(onizleme) > ONIZLEME_SINIRI:
        onizleme = onizleme[: ONIZLEME_SINIRI - 1] + "…"
    konu = "Genel" if k.tekil_anahtar else k.konu
    if alici_taraf == "client":
        link = f"/client?sekme=mesajlar&konusma={k.id}"
        # E-postadaki bağlantıda hesap da var: ekip üyesi doğru hesapta açsın.
        tam = f"{site_adresi()}{link}&hesap={quote(k.hesap_email)}"
        alicilar = [{"email": k.hesap_email, "role": "client"}]
        varsayilan_baslik = f"Yeni mesajınız var: {konu}"
    else:
        link = f"/admin?sekme=mesajlar&konusma={k.id}"
        tam = f"{site_adresi()}{link}"
        alicilar = await admin_recipients(db)
        varsayilan_baslik = f"Müşteriden yeni mesaj ({k.hesap_email}): {konu}"
    ek_satir = f"\n\nBu konuşmada {sayi} okunmamış mesaj var." if sayi > 1 else ""
    varsayilan_govde = f"{yazan}:\n{onizleme}{ek_satir}\n\nYanıtlamak için: {tam}"
    baslik, govde = await render(
        db,
        OLAY,
        varsayilan_baslik,
        varsayilan_govde,
        {"yazan": yazan, "konu": konu, "onizleme": onizleme, "sayi": sayi, "baglanti": tam, "hesap": k.hesap_email},
    )
    if not alicilar:
        return
    await dispatch(
        db,
        event_type=OLAY,
        title=baslik,
        body=govde,
        recipients=alicilar,
        link=link,
        ref_type="konusma",
        ref_id=k.id,
    )
    logger.info("Mesaj bildirimi: konuşma %s → %s (%d mesaj, son #%s)", k.id, alici_taraf, sayi, son.id)


async def bildirimleri_isle(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """Okunmamış mesajlar için toplu bildirim (bkz. modül açıklaması)."""
    an = utc(an) or simdi()
    sonuc = {"gonderilen": 0, "kapsanan": 0, "bekleyen": 0}
    async with _bildirim_kilidi:
        for alici_taraf in TARAFLAR:
            yazan_taraf = karsi(alici_taraf)
            son_sutun, bildirilen_sutun, zaman_sutun = _bildirim_sutunlari(alici_taraf)
            adaylar = list(
                (
                    await db.execute(
                        select(Konusmalar.id, son_sutun, bildirilen_sutun, zaman_sutun)
                        .where(func.coalesce(son_sutun, 0) > func.coalesce(bildirilen_sutun, 0))
                        .order_by(Konusmalar.id.asc())
                        .limit(500)
                    )
                ).all()
            )
            for k_id, son_id, bildirilen, son_bildirim in adaylar:
                bildirilen = int(bildirilen or 0)
                taban = max(bildirilen, await _taraf_okunan(db, k_id, alici_taraf))
                M = KonusmaMesajlari
                bekleyenler = list(
                    (
                        await db.execute(
                            select(M)
                            .where(M.konusma_id == k_id, M.yazan_rol == yazan_taraf, M.silindi.is_(False), M.id > taban)
                            .order_by(M.id.asc())
                            .limit(100)
                        )
                    )
                    .scalars()
                    .all()
                )
                if not bekleyenler:
                    # Hepsi okundu (ya da silindi): bir daha bakılmasın; bildirim yok.
                    if await _talep_et(db, k_id, alici_taraf, bildirilen, int(son_id or 0), None):
                        sonuc["kapsanan"] += 1
                    continue
                if an - utc(bekleyenler[0].created_at) < BILDIRIM_GECIKMESI:  # type: ignore[operator]
                    sonuc["bekleyen"] += 1
                    continue
                son_zaman = utc(son_bildirim)
                if son_zaman is not None and an - son_zaman < TOPLAMA_SURESI:
                    sonuc["bekleyen"] += 1
                    continue
                if not await _talep_et(db, k_id, alici_taraf, bildirilen, bekleyenler[-1].id, an):
                    continue  # başka bir tur aldı
                k = await konusma_bul(db, k_id)
                try:
                    await _bildirim_gonder(db, k, alici_taraf, bekleyenler)
                    sonuc["gonderilen"] += 1
                except Exception:  # noqa: BLE001 - bir konuşma diğerlerini durdurmasın
                    logger.exception("Mesaj bildirimi gönderilemedi (konuşma %s)", k_id)
                    try:
                        await db.rollback()
                    except Exception:  # noqa: BLE001
                        pass
    return sonuc


def istekle_tetiklenmeli_mi() -> bool:
    """Süreç başına en çok TETIK_ARALIGI_SN'de bir (yoklama isteği arka planda tetikler)."""
    global _son_tetik
    if not ISTEKLE_TETIKLE:
        return False
    an = time.monotonic()
    if an - _son_tetik < TETIK_ARALIGI_SN:
        return False
    _son_tetik = an
    return True


async def arka_planda_isle() -> None:
    """Yanıt gönderildikten sonra kendi oturumuyla çalışır; hata fırlatmaz."""
    try:
        from core.database import db_manager

        yapici = db_manager.async_session_maker
        if yapici is None:
            return
        async with yapici() as db:
            await bildirimleri_isle(db)
    except Exception:  # noqa: BLE001
        logger.exception("Mesaj bildirimi taraması (istek) başarısız")
