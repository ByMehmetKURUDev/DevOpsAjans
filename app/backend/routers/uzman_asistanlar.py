"""Faz 3U — Uzman Asistanlar (müşteri paneli) + yönetim.

Müşteri (`/api/v1/asistanlarim`; modül `uzman_asistanlar` açık + hesap izni `asistanlar`):
  GET    ""                              aktif asistanlar (dilde), kategoriler, günlük hak, kredi, atıf
  GET    "/sohbetler"                    kişinin bu hesaptaki sohbetleri (?asistan=)
  POST   "/sohbetler"                    {asistan_anahtar, baslik?} → yeni sohbet
  GET    "/sohbetler/{id}"               sohbet + mesajlar
  POST   "/sohbetler/{id}/mesaj"         {icerik, yeniden?} → yanıt (akış yok; bekleme göstergesi yeter)
  DELETE "/sohbetler/{id}"               yumuşak silme

Yönetici (`/api/v1/uzman-asistanlar/yonetim`):
  GET    ""                              hepsi (sistem istemi dahil) + kategoriler + ayarlar + atıf
  PUT    "/ayarlar"                      model, max_tokens, günlük sınır, mesaj kredisi, açık uç bütçesi
  GET    "/kullanim?gun=30"              hesap başına mesaj/jeton, asistan başına mesaj, günlük sayaç
  PUT    "/{anahtar}"                    ad/açıklama/örnek sorular (7 dil), sistem istemi, aktif, sıra
  POST   "/{anahtar}/dene"               {icerik, sistem_istemi?} → yanıt; HİÇBİR ŞEY KAYDEDİLMEZ

Güvenlik
--------
* Sistem istemi yalnız sunucuda: müşteri yanıtlarında hiçbir alanda dönmez.
  Gövdede gelen `model`, `max_tokens`, `sistem_istemi`, `messages` yok sayılır.
* Sohbet kişiye özel (`hesap_email` + `kisi_email`); başka hesabın ya da
  ekipteki başka kişinin sohbeti 404.
* Kullanım: hesap başına günlük mesaj sınırı (modül ayarı `gunluk_mesaj` →
  site ayarı `asistan_gunluk_sinir`, varsayılan 50; 429 `gunluk_sinir`),
  kişi başı dakikada 10 mesaj (429 `cok_hizli`), isteğe bağlı mesaj başı
  kredi (site ayarı `asistan_mesaj_kredi`; bakiye yetmezse 402
  `kredi_yetersiz`). Model hata verirse kullanıcı mesajı kalır, kredi iade
  edilir, yanıt yerine hata kodu döner (`yeniden: true` ile tekrar denenir).

Çöp kutusu: sohbet silme yumuşak (`silindi`), çöp kutusuna düşmüyor — yapay
zekâ sohbeti iş kaydı değil; geri almak yerine yeni sohbet açmak yeterli.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import izin_gerekli, izin_iste
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from models.uzman_asistanlar import AsistanMesajlari, AsistanSohbetleri, UzmanAsistanlar
from pydantic import BaseModel, ConfigDict, Field
from services import uzman_asistanlar as servis
from services import yapay_zeka as ai
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri

logger = logging.getLogger(__name__)

musteri_router = APIRouter(
    prefix="/api/v1/asistanlarim",
    tags=["uzman_asistanlar"],
    dependencies=[Depends(modul_gerekli("uzman_asistanlar")), Depends(izin_gerekli("asistanlar"))],
)
yonetici_router = APIRouter(
    prefix="/api/v1/uzman-asistanlar/yonetim",
    tags=["uzman_asistanlar"],
    dependencies=[Depends(yonetici_gerekli)],
)

IZIN = "asistanlar"
#: Kişi başı dakikada en çok bu kadar mesaj.
_kisi_hizi = HizSiniri(10, 60.0)
#: Yöneticinin "Dene" kutusu: kişi başı dakikada 20.
_dene_hizi = HizSiniri(20, 60.0)
SOHBET_LISTE_SINIRI = 100
MESAJ_LISTE_SINIRI = 200


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    _kisi_hizi.temizle()
    _dene_hizi.temizle()


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _dogrulama_hatasi(h: servis.AsistanHatasi) -> HTTPException:
    return _hata(400, h.kod, alan=h.alan)


def _an(deger: Any) -> Optional[str]:
    if not deger:
        return None
    if deger.tzinfo is None:
        deger = deger.replace(tzinfo=timezone.utc)
    return deger.isoformat()


def _gun_basi() -> datetime:
    simdi = datetime.now(timezone.utc)
    return simdi.replace(hour=0, minute=0, second=0, microsecond=0)


def _sohbet_sozlugu(s: AsistanSohbetleri) -> Dict[str, Any]:
    return {
        "id": s.id,
        "asistan_anahtar": s.asistan_anahtar,
        "baslik": s.baslik or "",
        "created_at": _an(s.created_at),
        "updated_at": _an(s.updated_at),
    }


def _mesaj_sozlugu(m: AsistanMesajlari) -> Dict[str, Any]:
    return {"id": m.id, "sohbet_id": m.sohbet_id, "rol": m.rol, "icerik": m.icerik, "created_at": _an(m.created_at)}


async def _bugunku_mesaj(db: AsyncSession, hesap: str) -> int:
    """Hesabın bugün (UTC) aldığı asistan yanıtı sayısı (silinen sohbetler dahil)."""
    sonuc = await db.execute(
        select(func.count(AsistanMesajlari.id))
        .join(AsistanSohbetleri, AsistanSohbetleri.id == AsistanMesajlari.sohbet_id)
        .where(AsistanSohbetleri.hesap_email == hesap)
        .where(AsistanMesajlari.rol == "assistant")
        .where(AsistanMesajlari.created_at >= _gun_basi())
    )
    return int(sonuc.scalar() or 0)


def _kullanim(bugun: int, sinir: int) -> Dict[str, int]:
    return {"bugun": bugun, "sinir": sinir, "kalan": max(0, sinir - bugun)}


async def _asistan(db: AsyncSession, anahtar: str, yalniz_aktif: bool = True) -> Optional[UzmanAsistanlar]:
    sorgu = select(UzmanAsistanlar).where(UzmanAsistanlar.anahtar == (anahtar or "").strip().lower())
    if yalniz_aktif:
        sorgu = sorgu.where(UzmanAsistanlar.aktif.is_(True))
    return (await db.execute(sorgu)).scalars().first()


async def _sohbet(db: AsyncSession, sohbet_id: int, baglam) -> AsistanSohbetleri:
    """Kişinin bu hesaptaki, silinmemiş sohbeti; değilse 404 (var olup olmadığı sızmasın)."""
    s = (
        await db.execute(
            select(AsistanSohbetleri)
            .where(AsistanSohbetleri.id == sohbet_id)
            .where(AsistanSohbetleri.hesap_email == baglam.hesap_email)
            .where(AsistanSohbetleri.kisi_email == baglam.kisi_email)
            .where(AsistanSohbetleri.silindi.is_(False))
        )
    ).scalars().first()
    if s is None:
        raise _hata(404, "sohbet_yok")
    return s


# ---------------------------------------------------------------------------
# Müşteri
# ---------------------------------------------------------------------------
@musteri_router.get("")
async def asistanlarim(request: Request, dil: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    baglam = izin_iste(request, IZIN)
    d = servis.dil_coz(dil)
    kategori_sirasi = servis.kategori_anahtarlari()
    satirlar = list(
        (await db.execute(select(UzmanAsistanlar).where(UzmanAsistanlar.aktif.is_(True)))).scalars().all()
    )
    satirlar.sort(key=lambda a: servis.siralama_anahtari(a, kategori_sirasi))
    ayar = await servis.ayarlar(db, baglam.hesap_email)
    kredi: Dict[str, Any] = {"mesaj_basi": ayar["mesaj_kredi"], "bakiye": None}
    if ayar["mesaj_kredi"] > 0 and baglam.izin_var("krediler"):
        from services.kredi import bakiye

        kredi["bakiye"] = await bakiye(db, baglam.hesap_email)
    kaynak = servis.kaynak_bilgisi()
    return {
        "asistanlar": [servis.musteri_satiri(a, d) for a in satirlar],
        "kategoriler": servis.kategoriler_dilde(d),
        "kullanim": _kullanim(await _bugunku_mesaj(db, baglam.hesap_email), ayar["gunluk_sinir"]),
        "kredi": kredi,
        "kaynak": {"ad": kaynak["ad"], "depo": kaynak["depo"], "lisans": kaynak["lisans"]},
    }


@musteri_router.get("/sohbetler")
async def sohbetlerim(request: Request, asistan: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    baglam = izin_iste(request, IZIN)
    sorgu = (
        select(AsistanSohbetleri)
        .where(AsistanSohbetleri.hesap_email == baglam.hesap_email)
        .where(AsistanSohbetleri.kisi_email == baglam.kisi_email)
        .where(AsistanSohbetleri.silindi.is_(False))
    )
    if asistan:
        sorgu = sorgu.where(AsistanSohbetleri.asistan_anahtar == asistan.strip().lower())
    sorgu = sorgu.order_by(AsistanSohbetleri.updated_at.desc(), AsistanSohbetleri.id.desc()).limit(SOHBET_LISTE_SINIRI)
    return {"sohbetler": [_sohbet_sozlugu(s) for s in (await db.execute(sorgu)).scalars().all()]}


class SohbetGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asistan_anahtar: str = Field(..., min_length=1, max_length=80)
    baslik: str = Field(default="", max_length=200)


@musteri_router.post("/sohbetler")
async def sohbet_ac(request: Request, govde: SohbetGirdisi = Body(...), db: AsyncSession = Depends(get_db)):
    baglam = izin_iste(request, IZIN)
    a = await _asistan(db, govde.asistan_anahtar)
    if a is None:
        raise _hata(404, "asistan_yok")
    simdi = datetime.now(timezone.utc)
    s = AsistanSohbetleri(
        hesap_email=baglam.hesap_email,
        kisi_email=baglam.kisi_email,
        asistan_anahtar=a.anahtar,
        baslik=ai.tek_satir(govde.baslik, 120) or None,
        created_at=simdi,
        updated_at=simdi,
        silindi=False,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _sohbet_sozlugu(s)


@musteri_router.get("/sohbetler/{sohbet_id}")
async def sohbet_ayrintisi(sohbet_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    baglam = izin_iste(request, IZIN)
    s = await _sohbet(db, sohbet_id, baglam)
    mesajlar = list(
        (
            await db.execute(
                select(AsistanMesajlari)
                .where(AsistanMesajlari.sohbet_id == s.id)
                .order_by(AsistanMesajlari.id.desc())
                .limit(MESAJ_LISTE_SINIRI)
            )
        ).scalars().all()
    )
    mesajlar.reverse()
    return {"sohbet": _sohbet_sozlugu(s), "mesajlar": [_mesaj_sozlugu(m) for m in mesajlar]}


class MesajGirdisi(BaseModel):
    # Bilinmeyen alanlar (model, max_tokens, sistem_istemi, messages…) yok sayılır.
    model_config = ConfigDict(extra="ignore")

    icerik: str = Field(default="", max_length=servis.MESAJ_SINIRI)
    #: Yanıtı alınamamış son kullanıcı mesajını tekrar dener (yeni mesaj yazılmaz).
    yeniden: bool = False


@musteri_router.post("/sohbetler/{sohbet_id}/mesaj")
async def mesaj_gonder(
    sohbet_id: int, request: Request, govde: MesajGirdisi = Body(...), db: AsyncSession = Depends(get_db)
):
    baglam = izin_iste(request, IZIN)
    s = await _sohbet(db, sohbet_id, baglam)
    a = await _asistan(db, s.asistan_anahtar)
    if a is None:
        raise _hata(409, "asistan_pasif")

    gecmis = list(
        (
            await db.execute(
                select(AsistanMesajlari)
                .where(AsistanMesajlari.sohbet_id == s.id)
                .order_by(AsistanMesajlari.id.desc())
                .limit(servis.BAGLAM_MESAJ * 2)
            )
        ).scalars().all()
    )
    gecmis.reverse()
    bekleyen = gecmis[-1] if govde.yeniden and gecmis and gecmis[-1].rol == "user" else None
    icerik = (govde.icerik or "").strip()
    if bekleyen is None and not icerik:
        raise _hata(422, "bos_mesaj")

    if not _kisi_hizi.izin_var_mi(f"{baglam.hesap_email}|{baglam.kisi_email}"):
        raise _hata(429, "cok_hizli")
    ayar = await servis.ayarlar(db, baglam.hesap_email)
    bugun = await _bugunku_mesaj(db, baglam.hesap_email)
    if bugun >= ayar["gunluk_sinir"]:
        raise _hata(429, "gunluk_sinir", **_kullanim(bugun, ayar["gunluk_sinir"]))

    # Kredi: önce düş (eş zamanlı iki istek aynı son krediyi kullanamasın),
    # model hata verirse iade et.
    harcama = None
    if ayar["mesaj_kredi"] > 0:
        from services import kredi

        try:
            harcama, _ = await kredi.harca(
                db,
                eposta=baglam.hesap_email,
                saat=ayar["mesaj_kredi"],
                aciklama=f"Uzman asistan: {a.ad}",
                olusturan=baglam.kisi_email,
            )
        except HTTPException as h:
            if h.status_code == status.HTTP_409_CONFLICT:
                raise _hata(402, "kredi_yetersiz", gerekli=ayar["mesaj_kredi"])
            raise

    simdi = datetime.now(timezone.utc)
    if bekleyen is None:
        kullanici_mesaji = AsistanMesajlari(sohbet_id=s.id, rol="user", icerik=icerik, created_at=simdi)
        db.add(kullanici_mesaji)
        if not s.baslik:
            s.baslik = ai.tek_satir(icerik, 80)
        s.updated_at = simdi
        await db.commit()
        await db.refresh(kullanici_mesaji)
        gecmis.append(kullanici_mesaji)
    else:
        kullanici_mesaji = bekleyen

    mesajlar = [{"role": "system", "content": servis.sistem_metni(a)}]
    mesajlar += servis.baglam_kur((m.rol, m.icerik) for m in gecmis)
    await ai.sayac_artir(db, "asistan")
    try:
        yanit = await ai.metin_uret(
            mesajlar, model=ayar["model"], max_tokens=ayar["max_tokens"], temperature=0.6, amac="uzman"
        )
    except ai.YapayZekaHatasi as h:
        if harcama is not None:
            await _iade(db, baglam, harcama, ayar["mesaj_kredi"])
        raise _hata(h.durum, h.kod, mesaj_id=kullanici_mesaji.id)

    simdi = datetime.now(timezone.utc)
    yanit_mesaji = AsistanMesajlari(
        sohbet_id=s.id,
        rol="assistant",
        icerik=yanit.icerik[: servis.MESAJ_SINIRI],
        token_giris=yanit.token_giris,
        token_cikis=yanit.token_cikis,
        created_at=simdi,
    )
    db.add(yanit_mesaji)
    s.updated_at = simdi
    await db.commit()
    await db.refresh(yanit_mesaji)
    await ai.token_ekle(db, "asistan", yanit)
    return {
        "kullanici_mesaji": _mesaj_sozlugu(kullanici_mesaji),
        "asistan_mesaji": _mesaj_sozlugu(yanit_mesaji),
        "sohbet": _sohbet_sozlugu(s),
        "kullanim": _kullanim(bugun + 1, ayar["gunluk_sinir"]),
    }


async def _iade(db: AsyncSession, baglam, harcama, saat: float) -> None:
    from services import kredi

    try:
        await kredi.yukle(
            db,
            eposta=baglam.hesap_email,
            saat=saat,
            tur="iade",
            aciklama="Uzman asistan yanıt veremedi — iade",
            kaynak_ref=f"asistan_iade:{harcama.id}",
            olusturan=baglam.kisi_email,
        )
    except Exception:  # noqa: BLE001 - iade yazılamazsa günlüğe; yanıt yine hata dönsün
        logger.exception("Asistan kredisi iade edilemedi (harcama %s)", getattr(harcama, "id", None))


@musteri_router.delete("/sohbetler/{sohbet_id}")
async def sohbet_sil(sohbet_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    baglam = izin_iste(request, IZIN)
    s = await _sohbet(db, sohbet_id, baglam)
    s.silindi = True
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Yönetici
# ---------------------------------------------------------------------------
async def _ayar_ozeti(db: AsyncSession) -> Dict[str, Any]:
    ayar = await servis.ayarlar(db)
    return {
        "asistan_model": ayar["model_ayari"],
        "asistan_max_tokens": ayar["max_tokens"],
        "asistan_gunluk_sinir": ayar["genel_gunluk_sinir"],
        "asistan_mesaj_kredi": ayar["mesaj_kredi"],
        "ai_acik_gunluk_butce": ai.tam_sayi(await ai.ayar_oku(db, "ai_acik_gunluk_butce"), 1000, 0, 10_000_000),
        "ai_acik_model": await ai.ayar_oku(db, "ai_acik_model"),
        "varsayilan_model": ai.varsayilan_model(),
        "etkin_model": ayar["model"],
    }


@yonetici_router.get("")
async def yonetim_listesi(db: AsyncSession = Depends(get_db)):
    kategori_sirasi = servis.kategori_anahtarlari()
    satirlar = list((await db.execute(select(UzmanAsistanlar))).scalars().all())
    satirlar.sort(key=lambda a: servis.siralama_anahtari(a, kategori_sirasi))
    return {
        "asistanlar": [servis.yonetim_satiri(a) for a in satirlar],
        "kategoriler": servis.kategoriler(),
        "ayarlar": await _ayar_ozeti(db),
        "kaynak": servis.kaynak_bilgisi(),
    }


class AyarGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asistan_model: Optional[str] = Field(default=None, max_length=80)
    asistan_max_tokens: Optional[int] = Field(default=None, ge=servis.MAX_TOKENS_ARALIGI[0], le=servis.MAX_TOKENS_ARALIGI[1])
    asistan_gunluk_sinir: Optional[int] = Field(default=None, ge=0, le=servis.GUNLUK_SINIR_ARALIGI[1])
    asistan_mesaj_kredi: Optional[float] = Field(default=None, ge=0, le=servis.KREDI_UST)
    ai_acik_gunluk_butce: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    ai_acik_model: Optional[str] = Field(default=None, max_length=80)


@yonetici_router.put("/ayarlar")
async def ayarlari_kaydet(govde: AyarGirdisi = Body(...), db: AsyncSession = Depends(get_db)):
    for alan in ("asistan_model", "ai_acik_model"):
        deger = getattr(govde, alan)
        if deger is not None and deger.strip() and not ai.model_gecerli_mi(deger.strip()):
            raise _hata(400, "gecersiz", alan=alan)
    yazilacak = {
        "asistan_model": (govde.asistan_model or "").strip() if govde.asistan_model is not None else None,
        "asistan_max_tokens": govde.asistan_max_tokens,
        "asistan_gunluk_sinir": govde.asistan_gunluk_sinir,
        "asistan_mesaj_kredi": servis.kredi_coz(govde.asistan_mesaj_kredi) if govde.asistan_mesaj_kredi is not None else None,
        "ai_acik_gunluk_butce": govde.ai_acik_gunluk_butce,
        "ai_acik_model": (govde.ai_acik_model or "").strip() if govde.ai_acik_model is not None else None,
    }
    for anahtar, deger in yazilacak.items():
        if deger is None:
            continue
        # Boş model = varsayılana dön (satır boş metinle kalır; okuyan varsayılana düşer).
        await ai.ayar_yaz(db, anahtar, str(deger), etiket=f"Faz 3U: {anahtar}")
    await db.commit()
    return await _ayar_ozeti(db)


@yonetici_router.get("/kullanim")
async def kullanim_ozeti(gun: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    bas = datetime.now(timezone.utc) - timedelta(days=gun)
    satirlar = (
        await db.execute(
            select(
                AsistanSohbetleri.hesap_email,
                AsistanMesajlari.rol,
                func.count(AsistanMesajlari.id),
                func.coalesce(func.sum(AsistanMesajlari.token_giris), 0),
                func.coalesce(func.sum(AsistanMesajlari.token_cikis), 0),
                func.max(AsistanMesajlari.created_at),
            )
            .join(AsistanSohbetleri, AsistanSohbetleri.id == AsistanMesajlari.sohbet_id)
            .where(AsistanMesajlari.created_at >= bas)
            .group_by(AsistanSohbetleri.hesap_email, AsistanMesajlari.rol)
        )
    ).all()
    hesaplar: Dict[str, Dict[str, Any]] = {}
    for hesap, rol, sayi, giris, cikis, son in satirlar:
        h = hesaplar.setdefault(
            hesap,
            {"hesap_email": hesap, "kullanici_mesaji": 0, "asistan_mesaji": 0, "token_giris": 0, "token_cikis": 0, "son_mesaj_at": None},
        )
        if rol == "assistant":
            h["asistan_mesaji"] += int(sayi)
        else:
            h["kullanici_mesaji"] += int(sayi)
        h["token_giris"] += int(giris or 0)
        h["token_cikis"] += int(cikis or 0)
        son_metin = _an(son)
        if son_metin and (h["son_mesaj_at"] is None or son_metin > h["son_mesaj_at"]):
            h["son_mesaj_at"] = son_metin
    asistan_satirlari = (
        await db.execute(
            select(AsistanSohbetleri.asistan_anahtar, func.count(AsistanMesajlari.id))
            .join(AsistanSohbetleri, AsistanSohbetleri.id == AsistanMesajlari.sohbet_id)
            .where(AsistanMesajlari.created_at >= bas)
            .where(AsistanMesajlari.rol == "assistant")
            .group_by(AsistanSohbetleri.asistan_anahtar)
        )
    ).all()
    liste = sorted(hesaplar.values(), key=lambda h: (-h["asistan_mesaji"], h["hesap_email"]))
    return {
        "gun": gun,
        "hesaplar": liste,
        "asistanlar": sorted(
            [{"anahtar": k, "asistan_mesaji": int(n)} for k, n in asistan_satirlari], key=lambda x: -x["asistan_mesaji"]
        ),
        "toplam": {
            "kullanici_mesaji": sum(h["kullanici_mesaji"] for h in liste),
            "asistan_mesaji": sum(h["asistan_mesaji"] for h in liste),
            "token_giris": sum(h["token_giris"] for h in liste),
            "token_cikis": sum(h["token_cikis"] for h in liste),
        },
        "gunluk": await ai.gunluk_ozet(db, min(gun, 31)),
    }


@yonetici_router.put("/{anahtar}")
async def asistan_guncelle(anahtar: str, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    a = await _asistan(db, anahtar, yalniz_aktif=False)
    if a is None:
        raise _hata(404, "asistan_yok")
    try:
        alanlar = servis.girdiyi_dogrula(govde, servis.kategori_anahtarlari())
    except servis.AsistanHatasi as h:
        raise _dogrulama_hatasi(h)
    for alan, deger in alanlar.items():
        setattr(a, alan, deger)
    await db.commit()
    await db.refresh(a)
    return servis.yonetim_satiri(a)


class DeneGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    icerik: str = Field(..., min_length=1, max_length=servis.MESAJ_SINIRI)
    #: Kaydedilmemiş bir istemi denemek için (yalnız yönetici).
    sistem_istemi: Optional[str] = Field(default=None, max_length=servis.SINIR["sistem_istemi"])


@yonetici_router.post("/{anahtar}/dene")
async def asistan_dene(anahtar: str, request: Request, govde: DeneGirdisi = Body(...), db: AsyncSession = Depends(get_db)):
    from dependencies.kayit_sahipligi import _yonetici_mi

    a = await _asistan(db, anahtar, yalniz_aktif=False)
    if a is None:
        raise _hata(404, "asistan_yok")
    kullanici, _ = _yonetici_mi(request)
    if not _dene_hizi.izin_var_mi((getattr(kullanici, "email", "") or "").lower()):
        raise _hata(429, "cok_hizli")
    ayar = await servis.ayarlar(db)
    istem = govde.sistem_istemi if (govde.sistem_istemi or "").strip() else None
    mesajlar = [
        {"role": "system", "content": servis.sistem_metni(a, istem)},
        {"role": "user", "content": govde.icerik.strip()},
    ]
    await ai.sayac_artir(db, "yonetici")
    try:
        yanit = await ai.metin_uret(mesajlar, model=ayar["model"], max_tokens=ayar["max_tokens"], temperature=0.6, amac="dene")
    except ai.YapayZekaHatasi as h:
        raise _hata(h.durum, h.kod)
    await ai.token_ekle(db, "yonetici", yanit)
    return {"icerik": yanit.icerik, "model": yanit.model, "token_giris": yanit.token_giris, "token_cikis": yanit.token_cikis}


# Yönetici router'ı ÖNCE: sabit yollar (/ayarlar, /kullanim) `/{anahtar}`tan önce tanımlı.
router = (yonetici_router, musteri_router)
