"""Faz 5A — AI asistan + bilgi bankası (modül `ai_asistan`, hesap ekibi izni `asistan`).

Panel — yönetici `/api/v1/ai-asistan/yonetim` (ajansın kendi asistanı + bütün müşterilerinki,
müşteri adına kurulum) ve müşteri `/api/v1/ai-asistanim` (etkin hesabın asistanı; modül açık +
`asistan` izni). Aynı uçlar:
  GET  /meta                                   sınırlar, seçenekler, gömme adresleri
  GET|POST ""                                  asistanlar / yeni asistan (hesap başına bir)
  GET|PUT|DELETE /{aid}                        ayrıntı / ayarlar / kalıcı sil (kaynak + sohbet dahil)
  POST /{aid}/anahtar                          herkese açık anahtarı yenile (eski gömme kodu çalışmaz)
  POST|DELETE /{aid}/avatar                    avatar (JPEG/PNG/WebP ≤ 5 MB → WebP)
  GET  /{aid}/ice-aktarim                      içe aktarılabilir modül kayıtları (QR menü, randevu)
  GET|POST /{aid}/kaynaklar                    bilgi bankası: metin, SSS, URL/site haritası, modül
  POST /{aid}/kaynaklar/belge                  belge yükle (PDF, DOCX, TXT, MD ≤ 10 MB)
  GET|PUT|DELETE /{aid}/kaynaklar/{kid}        ayrıntı / düzenle (yeniden işlenir) / sil
  POST /{aid}/kaynaklar/{kid}/isle             yeniden işle
  GET  /{aid}/sohbetler?durum=&sayfa=          sohbetler (saklama süresi dolanlar önce silinir)
  GET|DELETE /{aid}/sohbetler/{sid}            döküm / sil
  POST /{aid}/sohbetler/{sid}/anonimlestir     iletişim bilgisi + IP özeti silinir, mesajlarda e-posta/telefon maskelenir
  GET  /{aid}/kullanim?gun=30                  mesaj, jeton, kredi, devir; aylık dahil hak ve sınırlar
Yalnız yönetici: GET|PUT /api/v1/ai-asistan/yonetim/ayarlar (model, günlük bütçe, kredi bloğu, gömme modeli).

Herkese açık (`/api/v1/asistan`):
  GET  /{anahtar}?dil=&gomulu=1&kaynak=&onizleme=1   yapılandırma + imzalı oturum jetonu
  GET  /{anahtar}/ozet                               Pages Function için (ad, renk, izinli kökenler)
  POST /{anahtar}/mesaj                              soru → kaynaklı yanıt (ya da bilmiyorum / bütçe modu)
  POST /{anahtar}/devret                             insana devret (ad + e-posta/telefon)
  GET  /gorsel/{anahtar}                             avatar

Köken: istekte `Origin` varsa sitenin kendisi ya da asistanın izinli alan adı olmalı; gömülü
pencerede (`gomulu`) çerçevenin üst sayfası (`kaynak`: postMessage/ancestorOrigins/referrer)
izinli listede olmalı (boş liste = her yer). Önizleme (`onizleme`) oturum ister ve sahibine/yöneticiye
açık; köken ve aktiflik denetimi atlanır.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.database import get_db
from dependencies.hesap_baglami import hesap_baglami, izin_gerekli, izin_iste
from dependencies.kayit_sahipligi import _yonetici_mi
from dependencies.modul_bekcisi import modul_gerekli
from dependencies.yonetici_bekcisi import yonetici_gerekli
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from models.ai_asistan import AiAsistanKaynaklari, AiAsistanlar, AiAsistanMesajlari, AiAsistanSohbetleri
from pydantic import BaseModel, ConfigDict, Field
from services import ai_asistan as s
from services import ai_asistan_icerik as icerik
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.hiz_siniri import HizSiniri, KaliciHizSiniri, izin_ver
from utils.istemci_ip import ip_ozeti, istemci_ip

logger = logging.getLogger(__name__)

yonetici_router = APIRouter(prefix="/api/v1/ai-asistan/yonetim", tags=["ai_asistan"], dependencies=[Depends(yonetici_gerekli)])
musteri_router = APIRouter(
    prefix="/api/v1/ai-asistanim",
    tags=["ai_asistan"],
    dependencies=[Depends(modul_gerekli(s.MODUL)), Depends(izin_gerekli(s.IZIN))],
)
gorsel_router = APIRouter(prefix="/api/v1/asistan/gorsel", tags=["ai_asistan"])
acik_router = APIRouter(prefix="/api/v1/asistan", tags=["ai_asistan"])

#: Panel (kişi başı)
_yazma_hizi = HizSiniri(60, 60.0)
_belge_hizi = HizSiniri(20, 600.0)
_url_hizi = HizSiniri(10, 600.0)
#: Ziyaretçi: IP özeti başına dakikada 20 / günde 300 mesaj; oturum başına dakikada 8;
#: asistan başına dakikada 120 (çok IP'den gelen saldırı); devir IP başına 10 dakikada 5.
#: Faz 7H: ziyaretçi sayaçları veritabanında (sunucu uyanınca / yeniden yayında sıfırlanmıyor).
_ip_dakika = KaliciHizSiniri("asistan-ip-dk", 20, 60.0)
_ip_gun = KaliciHizSiniri("asistan-ip-gun", 300, 86400.0)
_oturum_hizi = KaliciHizSiniri("asistan-oturum", 8, 60.0)
_asistan_hizi = KaliciHizSiniri("asistan-genel", 120, 60.0)
_devir_hizi = KaliciHizSiniri("asistan-devir", 5, 600.0)
_yapilandirma_hizi = HizSiniri(120, 60.0)

SAYFA_BOYU = 50


def hiz_sinirlarini_temizle() -> None:
    """Testler için."""
    for h in (_yazma_hizi, _belge_hizi, _url_hizi, _ip_dakika, _ip_gun, _oturum_hizi, _asistan_hizi, _devir_hizi,
              _yapilandirma_hizi):
        h.temizle()


@dataclass
class Kapsam:
    yonetici: bool
    #: Müşteride etkin hesap; yöneticide None.
    hesap: Optional[str]
    kisi: str


def _yonetici_kapsami(request: Request) -> Kapsam:
    kullanici, _ = _yonetici_mi(request)
    return Kapsam(True, None, (getattr(kullanici, "email", "") or "").strip().lower())


def _musteri_kapsami(request: Request) -> Kapsam:
    baglam = izin_iste(request, s.IZIN)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


def _hata(durum: int, kod: str, **ek: Any) -> HTTPException:
    return HTTPException(status_code=durum, detail={"kod": kod, **ek})


def _cevir(h: Exception) -> HTTPException:
    if isinstance(h, (s.AsistanHatasi, icerik.IcerikHatasi)):
        return HTTPException(status_code=h.durum, detail=h.detay())
    raise h


def _hiz(sinir: HizSiniri, anahtar: str) -> None:
    if not sinir.izin_var_mi(anahtar):
        raise _hata(429, "cok_hizli")


async def _kalici_hiz(*denemeler) -> None:
    """Faz 7H: herkese açık uçların veritabanı destekli sayacı ((sınırlayıcı, anahtar) çiftleri)."""
    if not await izin_ver(*denemeler):
        raise _hata(429, "cok_hizli")


async def _asistan(db: AsyncSession, aid: int, kapsam: Kapsam) -> AiAsistanlar:
    a = await db.get(AiAsistanlar, aid)
    if a is None or (not kapsam.yonetici and (a.hesap_email or None) != kapsam.hesap):
        raise _hata(404, "bulunamadi")
    return a


async def _kaynak(db: AsyncSession, a: AiAsistanlar, kid: int) -> AiAsistanKaynaklari:
    k = await db.get(AiAsistanKaynaklari, kid)
    if k is None or k.asistan_id != a.id:
        raise _hata(404, "bulunamadi")
    return k


async def _sohbet(db: AsyncSession, a: AiAsistanlar, sid: int) -> AiAsistanSohbetleri:
    so = await db.get(AiAsistanSohbetleri, sid)
    if so is None or so.asistan_id != a.id:
        raise _hata(404, "bulunamadi")
    return so


async def _ozet_bilgiler(db: AsyncSession, a: AiAsistanlar) -> Dict[str, Any]:
    kaynak = (await db.execute(
        select(func.count(AiAsistanKaynaklari.id), func.coalesce(func.sum(AiAsistanKaynaklari.parca_sayisi), 0))
        .where(AiAsistanKaynaklari.asistan_id == a.id)
    )).first()
    sohbet = (await db.execute(
        select(func.count(AiAsistanSohbetleri.id)).where(AiAsistanSohbetleri.asistan_id == a.id)
    )).scalar()
    return {"kaynak_sayisi": int(kaynak[0] or 0), "parca_sayisi": int(kaynak[1] or 0), "sohbet_sayisi": int(sohbet or 0)}


async def _meta(db: AsyncSession, kapsam: Kapsam) -> Dict[str, Any]:
    site = s.site_adresi()
    veri: Dict[str, Any] = {
        "yonetici": kapsam.yonetici,
        "diller": list(s.DILLER),
        "dil_secenekleri": list(s.DIL_SECENEKLERI),
        "tonlar": list(s.TONLAR),
        "uzunluklar": list(s.UZUNLUKLAR),
        "saklama_secenekleri": list(s.SAKLAMA_SECENEKLERI),
        "kaynak_turleri": list(s.KAYNAK_TURLERI),
        "url_kapsamlari": list(s.URL_KAPSAMLARI),
        "belge_turleri": list(icerik.UZANTILAR),
        "belge_en_cok_mb": icerik.BELGE_EN_COK_BAYT // (1024 * 1024),
        "mesaj_siniri": s.MESAJ_SINIRI,
        "sinir": {k: v for k, v in s.SINIR.items() if k != "metin"},
        "metin_en_cok": s.SINIR["metin"],
        "widget_adresi": f"{site}/asistan-widget.js",
        "adres_tabani": f"{site}/asistan/",
        "gomme_hazir": s.gomme_hazir_mi(),
    }
    if not kapsam.yonetici:
        veri["sinirlar"] = await s.hesap_sinirlari(db, kapsam.hesap)
        veri["kaynak_kullanilan"] = await s.kaynak_sayisi(db, kapsam.hesap)
        veri["sayfa_kullanilan"] = await s.kullanilan_sayfa(db, kapsam.hesap)
    return veri


def _eposta(ham: Any) -> Optional[str]:
    e = str(ham or "").strip().lower()
    if not e:
        return None
    if not s._EPOSTA.match(e) or len(e) > 254:
        raise _hata(400, "eposta_gecersiz", alan="hesap_email")
    return e


async def _hesap_bilgileri(db: AsyncSession, a: AiAsistanlar) -> Dict[str, Any]:
    sinirlar = await s.hesap_sinirlari(db, a.hesap_email)
    return {
        "sinirlar": sinirlar,
        "kaynak_kullanilan": await s.kaynak_sayisi(db, a.hesap_email),
        "sayfa_kullanilan": await s.kullanilan_sayfa(db, a.hesap_email),
    }


async def _kaynak_olustur(
    db: AsyncSession, arka: BackgroundTasks, kapsam: Kapsam, a: AiAsistanlar, govde: Dict[str, Any]
) -> Dict[str, Any]:
    tur = govde.get("tur")
    if tur not in ("metin", "sss", "url", "modul"):
        raise _hata(400, "gecersiz", alan="tur")
    sinirlar = await s.hesap_sinirlari(db, a.hesap_email)
    if await s.kaynak_sayisi(db, a.hesap_email) >= int(sinirlar["kaynak_siniri"]):
        raise _hata(409, "kaynak_siniri", sinir=sinirlar["kaynak_siniri"])
    k = AiAsistanKaynaklari(asistan_id=a.id, hesap_email=a.hesap_email, tur=tur, durum="isleniyor", olusturan=kapsam.kisi)
    try:
        if tur == "metin":
            k.baslik = s._metin(govde.get("baslik"), "baslik", s.SINIR["baslik"], zorunlu=True)
            k.metin = s._metin(govde.get("metin"), "metin", s.SINIR["metin"], zorunlu=True, tek=False)
        elif tur == "sss":
            k.baslik = s._metin(govde.get("baslik"), "baslik", s.SINIR["baslik"]) or "SSS"
            k.metin = json.dumps(s.sss_dogrula(govde.get("sss")), ensure_ascii=False)
        elif tur == "url":
            _hiz(_url_hizi, kapsam.kisi)
            ayar = s.url_ayari_dogrula(govde.get("ayar"), int(sinirlar["sayfa_siniri"]))
            kalan = int(sinirlar["sayfa_siniri"]) - await s.kullanilan_sayfa(db, a.hesap_email)
            if kalan <= 0:
                raise s.AsistanHatasi("sayfa_siniri", 409, sinir=sinirlar["sayfa_siniri"])
            ayar["en_cok"] = min(ayar["en_cok"], kalan)
            k.ayar = json.dumps(ayar)
            k.baslik = s._metin(govde.get("baslik"), "baslik", s.SINIR["baslik"]) or icerik._host(ayar["url"]) or ayar["url"][:160]
            k.haftalik_yenile = govde.get("haftalik_yenile") is True
        else:
            ayar = govde.get("ayar") if isinstance(govde.get("ayar"), dict) else {}
            if ayar.get("modul") not in icerik.MODULLER:
                raise s.AsistanHatasi("gecersiz", alan="modul")
            secenek = next((x for x in await icerik.modul_secenekleri(db, a.hesap_email)
                            if x["modul"] == ayar["modul"] and str(x["id"]) == str(ayar.get("id"))), None)
            if secenek is None:
                raise icerik.IcerikHatasi("modul_kaydi_yok", 404)
            k.ayar = json.dumps({"modul": ayar["modul"], "id": int(secenek["id"])})
            k.baslik = s._metin(govde.get("baslik"), "baslik", s.SINIR["baslik"]) or secenek["ad"][:160]
    except (s.AsistanHatasi, icerik.IcerikHatasi) as h:
        raise _cevir(h)
    db.add(k)
    await db.commit()
    await db.refresh(k)
    if tur == "url":
        arka.add_task(s.arka_planda_isle, k.id)
    else:
        k = await s.kaynak_isle(db, a, k)
    return s.kaynak_sozlugu(k)


async def _kaynak_guncelle(db: AsyncSession, arka: BackgroundTasks, kapsam: Kapsam, a: AiAsistanlar,
                           k: AiAsistanKaynaklari, govde: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if "baslik" in govde:
            k.baslik = s._metin(govde.get("baslik"), "baslik", s.SINIR["baslik"], zorunlu=True)
        if "metin" in govde and k.tur in ("metin", "belge"):
            k.metin = s._metin(govde.get("metin"), "metin", s.SINIR["metin"], zorunlu=True, tek=False)
        if "sss" in govde and k.tur == "sss":
            k.metin = json.dumps(s.sss_dogrula(govde.get("sss")), ensure_ascii=False)
        if "ayar" in govde and k.tur == "url":
            sinirlar = await s.hesap_sinirlari(db, a.hesap_email)
            k.ayar = json.dumps(s.url_ayari_dogrula(govde.get("ayar"), int(sinirlar["sayfa_siniri"])))
        if "haftalik_yenile" in govde and k.tur == "url":
            k.haftalik_yenile = govde.get("haftalik_yenile") is True
    except s.AsistanHatasi as h:
        raise _cevir(h)
    k.durum = "isleniyor"
    await db.commit()
    await db.refresh(k)
    if k.tur == "url":
        arka.add_task(s.arka_planda_isle, k.id)
        return s.kaynak_sozlugu(k)
    k = await s.kaynak_isle(db, a, k)
    return s.kaynak_sozlugu(k, ayrintili=True)


def _uclari_kur(router: APIRouter, kapsam_al: Callable[[Request], Kapsam]) -> None:
    @router.get("/meta")
    async def meta(request: Request, db: AsyncSession = Depends(get_db)):
        return await _meta(db, kapsam_al(request))

    @router.get("")
    async def liste(request: Request, hesap: Optional[str] = Query(None, max_length=254), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        sorgu = select(AiAsistanlar).order_by(AiAsistanlar.hesap_email.isnot(None), AiAsistanlar.id)
        if not kapsam.yonetici:
            sorgu = sorgu.where(AiAsistanlar.hesap_email == kapsam.hesap)
        elif hesap:
            h = hesap.strip().lower()
            sorgu = sorgu.where(AiAsistanlar.hesap_email.is_(None) if h == "ajans" else AiAsistanlar.hesap_email == h)
        satirlar = (await db.execute(sorgu.limit(500))).scalars().all()
        return {"items": [s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a)) for a in satirlar], "toplam": len(satirlar)}

    @router.post("")
    async def olustur(request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        hesap = (_eposta(govde.get("hesap_email")) if kapsam.yonetici else kapsam.hesap)
        kosul = AiAsistanlar.hesap_email == hesap if hesap else AiAsistanlar.hesap_email.is_(None)
        if (await db.execute(select(func.count(AiAsistanlar.id)).where(kosul))).scalar():
            raise _hata(409, "asistan_var")
        try:
            alanlar = s.ayarlari_dogrula({k: v for k, v in govde.items() if k != "hesap_email"}, yeni=True)
        except s.AsistanHatasi as h:
            raise _cevir(h)
        a = AiAsistanlar(hesap_email=hesap, anahtar=s.yeni_anahtar(), olusturan=kapsam.kisi, dizin_surumu=0,
                         mesai=json.dumps(s.mesai_dogrula(None)), **alanlar)
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a), **await _hesap_bilgileri(db, a))

    @router.get("/{aid}")
    async def getir(aid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        return s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a), **await _hesap_bilgileri(db, a))

    @router.put("/{aid}")
    async def guncelle(aid: int, request: Request, govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        try:
            alanlar = s.ayarlari_dogrula({k: v for k, v in govde.items() if k != "hesap_email"})
        except s.AsistanHatasi as h:
            raise _cevir(h)
        for k, v in alanlar.items():
            setattr(a, k, v)
        await db.commit()
        await db.refresh(a)
        return s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a), **await _hesap_bilgileri(db, a))

    @router.delete("/{aid}")
    async def sil(aid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        await s.asistani_sil(db, a)
        return {"ok": True}

    @router.post("/{aid}/anahtar")
    async def anahtar_yenile(aid: int, request: Request, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        a.anahtar = s.yeni_anahtar()
        await db.commit()
        await db.refresh(a)
        return s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a), **await _hesap_bilgileri(db, a))

    @router.post("/{aid}/avatar")
    async def avatar_yukle(aid: int, request: Request, dosya: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_belge_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        from services import dosya_deposu
        from services import qr_menu as gorsel_kurallari

        bayt = await dosya.read(gorsel_kurallari.GORSEL_EN_COK_BAYT + 1)
        try:
            hazir = gorsel_kurallari.gorsel_hazirla(bayt)
        except gorsel_kurallari.MenuHatasi as h:
            raise HTTPException(status_code=h.durum, detail=h.detay())
        anahtar = gorsel_kurallari.gorsel_anahtari()
        try:
            depo = await dosya_deposu.yaz(db, f"asistan/{anahtar}.webp", hazir.kucuk, "image/webp")
        except dosya_deposu.DepoHatasi:
            await db.rollback()
            raise _hata(502, "depo_hatasi")
        eski, eski_depo = a.avatar, a.avatar_depo
        a.avatar, a.avatar_depo = anahtar, depo
        await db.commit()
        await db.refresh(a)
        if eski and eski_depo:
            await s.avatar_dosyasini_sil(db, eski, eski_depo)
        return s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a))

    @router.delete("/{aid}/avatar")
    async def avatar_sil(aid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        eski, eski_depo = a.avatar, a.avatar_depo
        a.avatar = a.avatar_depo = None
        await db.commit()
        await db.refresh(a)
        if eski and eski_depo:
            await s.avatar_dosyasini_sil(db, eski, eski_depo)
        return s.asistan_sozlugu(a, **await _ozet_bilgiler(db, a))

    @router.get("/{aid}/ice-aktarim")
    async def ice_aktarim(aid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        return {"items": await icerik.modul_secenekleri(db, a.hesap_email)}

    @router.get("/{aid}/kaynaklar")
    async def kaynaklar(aid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        satirlar = (await db.execute(
            select(AiAsistanKaynaklari).where(AiAsistanKaynaklari.asistan_id == a.id).order_by(AiAsistanKaynaklari.id.desc())
        )).scalars().all()
        return {"items": [s.kaynak_sozlugu(k) for k in satirlar], **await _hesap_bilgileri(db, a)}

    @router.post("/{aid}/kaynaklar")
    async def kaynak_ekle(aid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                          db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        return await _kaynak_olustur(db, arka, kapsam, a, govde)

    @router.post("/{aid}/kaynaklar/belge")
    async def belge_yukle(aid: int, request: Request, dosya: UploadFile = File(...), baslik: Optional[str] = Form(None),
                          db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_belge_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        sinirlar = await s.hesap_sinirlari(db, a.hesap_email)
        if await s.kaynak_sayisi(db, a.hesap_email) >= int(sinirlar["kaynak_siniri"]):
            raise _hata(409, "kaynak_siniri", sinir=sinirlar["kaynak_siniri"])
        ad = (dosya.filename or "belge").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200]
        bayt = await dosya.read(icerik.BELGE_EN_COK_BAYT + 1)
        try:
            metin = icerik.belge_metni(ad, bayt)
            baslik_ = s._metin(baslik, "baslik", s.SINIR["baslik"]) or ad.rsplit(".", 1)[0][:160] or ad
        except (icerik.IcerikHatasi, s.AsistanHatasi) as h:
            raise _cevir(h)
        k = AiAsistanKaynaklari(asistan_id=a.id, hesap_email=a.hesap_email, tur="belge", baslik=baslik_, metin=metin,
                                dosya_adi=ad, boyut=len(bayt), durum="isleniyor", olusturan=kapsam.kisi)
        db.add(k)
        await db.commit()
        await db.refresh(k)
        k = await s.kaynak_isle(db, a, k)
        return s.kaynak_sozlugu(k)

    @router.get("/{aid}/kaynaklar/{kid}")
    async def kaynak_getir(aid: int, kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        k = await _kaynak(db, a, kid)
        from models.ai_asistan import AiAsistanParcalari

        parcalar = (await db.execute(
            select(AiAsistanParcalari).where(AiAsistanParcalari.kaynak_id == k.id).order_by(AiAsistanParcalari.sira).limit(20)
        )).scalars().all()
        return {**s.kaynak_sozlugu(k, ayrintili=True),
                "parcalar": [{"baslik": p.baslik, "metin": p.metin[:600], "adres": p.adres} for p in parcalar]}

    @router.put("/{aid}/kaynaklar/{kid}")
    async def kaynak_guncelle(aid: int, kid: int, request: Request, arka: BackgroundTasks, govde: Dict[str, Any] = Body(...),
                              db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        k = await _kaynak(db, a, kid)
        return await _kaynak_guncelle(db, arka, kapsam, a, k, govde)

    @router.post("/{aid}/kaynaklar/{kid}/isle")
    async def kaynak_isle(aid: int, kid: int, request: Request, arka: BackgroundTasks, db: AsyncSession = Depends(get_db)):
        kapsam = kapsam_al(request)
        _hiz(_yazma_hizi, kapsam.kisi)
        a = await _asistan(db, aid, kapsam)
        k = await _kaynak(db, a, kid)
        return await _kaynak_guncelle(db, arka, kapsam, a, k, {})

    @router.delete("/{aid}/kaynaklar/{kid}")
    async def kaynak_sil(aid: int, kid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        k = await _kaynak(db, a, kid)
        await s.kaynagi_sil(db, k)
        return {"ok": True}

    @router.get("/{aid}/sohbetler")
    async def sohbetler(aid: int, request: Request, durum: str = Query("hepsi", max_length=20),
                        sayfa: int = Query(1, ge=1, le=10_000), db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        await s.saklama_temizligi(db, a.id)
        sorgu = select(AiAsistanSohbetleri).where(AiAsistanSohbetleri.asistan_id == a.id)
        if durum == "devredildi":
            sorgu = sorgu.where(AiAsistanSohbetleri.durum == "devredildi")
        elif durum == "bilinmeyen":
            sorgu = sorgu.where(AiAsistanSohbetleri.bilinmeyen_sayisi > 0)
        elif durum == "onizleme":
            sorgu = sorgu.where(AiAsistanSohbetleri.kaynak == "onizleme")
        toplam = int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)
        satirlar = (await db.execute(
            sorgu.order_by(AiAsistanSohbetleri.son_mesaj_at.desc(), AiAsistanSohbetleri.id.desc())
            .offset((sayfa - 1) * SAYFA_BOYU).limit(SAYFA_BOYU)
        )).scalars().all()
        ilkler: Dict[int, str] = {}
        if satirlar:
            ids = [x.id for x in satirlar]
            alt = (select(AiAsistanMesajlari.sohbet_id, func.min(AiAsistanMesajlari.id).label("mid"))
                   .where(AiAsistanMesajlari.sohbet_id.in_(ids), AiAsistanMesajlari.rol == "kullanici")
                   .group_by(AiAsistanMesajlari.sohbet_id).subquery())
            for sid_, metin in (await db.execute(
                select(AiAsistanMesajlari.sohbet_id, AiAsistanMesajlari.metin).join(alt, AiAsistanMesajlari.id == alt.c.mid)
            )).all():
                ilkler[sid_] = s.tek_satir(metin, 140)
        return {"items": [s.sohbet_sozlugu(x, ilkler.get(x.id)) for x in satirlar], "toplam": toplam,
                "sayfa_boyu": SAYFA_BOYU, "saklama_gun": int(a.saklama_gun or s.VARSAYILAN_SAKLAMA)}

    @router.get("/{aid}/sohbetler/{sid}")
    async def sohbet_getir(aid: int, sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        so = await _sohbet(db, a, sid)
        mesajlar = (await db.execute(
            select(AiAsistanMesajlari).where(AiAsistanMesajlari.sohbet_id == so.id).order_by(AiAsistanMesajlari.id)
        )).scalars().all()
        return {**s.sohbet_sozlugu(so), "mesajlar": [s.mesaj_sozlugu(m) for m in mesajlar]}

    @router.post("/{aid}/sohbetler/{sid}/anonimlestir")
    async def sohbet_anonimlestir(aid: int, sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        so = await s.sohbet_anonimlestir(db, await _sohbet(db, a, sid))
        return s.sohbet_sozlugu(so)

    @router.delete("/{aid}/sohbetler/{sid}")
    async def sohbet_sil(aid: int, sid: int, request: Request, db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        await s.sohbeti_sil(db, await _sohbet(db, a, sid))
        return {"ok": True}

    @router.get("/{aid}/kullanim")
    async def kullanim(aid: int, request: Request, gun: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
        a = await _asistan(db, aid, kapsam_al(request))
        return await s.kullanim_ozeti(db, a.hesap_email, gun)


# Yönetici: genel ayarlar (/{aid}'den ÖNCE kayıtlı olmalı).
@yonetici_router.get("/ayarlar")
async def genel_ayarlar(db: AsyncSession = Depends(get_db)):
    return await s.genel_ayarlar(db)


@yonetici_router.put("/ayarlar")
async def genel_ayarlari_yaz(govde: Dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    try:
        return await s.genel_ayarlari_yaz(db, govde)
    except s.AsistanHatasi as h:
        raise _cevir(h)


_uclari_kur(yonetici_router, _yonetici_kapsami)
_uclari_kur(musteri_router, _musteri_kapsami)


# ---------------------------------------------------------------------------
# Herkese açık
# ---------------------------------------------------------------------------
ACIK_BASLIKLAR = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex"}


def _ziyaretci(request: Request) -> str:
    return ip_ozeti("ai-asistan|" + istemci_ip(request))


def _bot_mu(request: Request) -> bool:
    """Bilinen bot/önizleyici ajanı. Ajan başlığı hiç yoksa karar verilmiyor (vekil taşımayabilir)."""
    from services.dinamik_qr import bot_mu

    ua = (request.headers.get("user-agent") or "").strip()
    return bool(ua) and bot_mu(ua)


async def _onizleme_yetkisi(request: Request, db: AsyncSession, a: AiAsistanlar) -> Kapsam:
    """Panel önizlemesi: oturum + asistanın sahibi (izin `asistan`, modül açık) ya da yönetici."""
    baglam = hesap_baglami(request)
    if baglam is None:
        raise _hata(401, "oturum_gerekli")
    kullanici, yonetici = _yonetici_mi(request)
    if yonetici:
        return Kapsam(True, None, baglam.kisi_email)
    if (a.hesap_email or None) != baglam.hesap_email:
        raise _hata(404, "asistan_yok")
    if not baglam.izin_var(s.IZIN):
        raise _hata(403, "hesap_izni_yok", izin=s.IZIN)
    from services.moduller import modul_acik_mi

    if not await modul_acik_mi(db, baglam.hesap_email, s.MODUL):
        raise _hata(403, "modul_kapali", modul=s.MODUL)
    return Kapsam(False, baglam.hesap_email, baglam.kisi_email)


async def _asistan_bul(db: AsyncSession, anahtar: str) -> AiAsistanlar:
    temiz = (anahtar or "").strip().lower()
    if not s.ANAHTAR_DESENI.match(temiz):
        raise _hata(404, "asistan_yok")
    a = (await db.execute(select(AiAsistanlar).where(AiAsistanlar.anahtar == temiz))).scalars().first()
    if a is None:
        raise _hata(404, "asistan_yok")
    return a


async def _yayinda_mi(db: AsyncSession, a: AiAsistanlar) -> bool:
    if not a.aktif:
        return False
    if a.hesap_email:
        from services.moduller import modul_acik_mi

        return await modul_acik_mi(db, a.hesap_email, s.MODUL)
    return True


async def _kapi(request: Request, db: AsyncSession, anahtar: str, *, onizleme: bool, gomulu: bool,
                kaynak: Optional[str]) -> tuple:
    """(asistan, önizleme kapsamı | None, gömüldüğü host). Yayında değil/izinsiz → hata."""
    a = await _asistan_bul(db, anahtar)
    if onizleme:
        return a, await _onizleme_yetkisi(request, db, a), None
    if not await _yayinda_mi(db, a):
        raise _hata(410, "asistan_pasif")
    origin = request.headers.get("origin")
    if origin:
        h = s.koken_hostu(origin)
        if not (s.site_kokeni_mi(h) or s.koken_izinli_mi(a, h)):
            raise _hata(403, "koken_izinsiz")
    host = None
    if gomulu:
        host = s.koken_hostu(kaynak)
        if not s.koken_izinli_mi(a, host):
            raise _hata(403, "koken_izinsiz")
    elif not a.tam_sayfa:
        raise _hata(403, "tam_sayfa_kapali")
    return a, None, host


def _gizlilik_adresi(dil: str) -> str:
    return f"{s.site_adresi()}/gizlilik" if dil == "tr" else f"{s.site_adresi()}/{dil}/gizlilik"


@gorsel_router.get("/{anahtar}")
async def gorsel(anahtar: str, db: AsyncSession = Depends(get_db)):
    if len(anahtar) > 64:
        raise _hata(404, "bulunamadi")
    a = (await db.execute(select(AiAsistanlar).where(AiAsistanlar.avatar == anahtar))).scalars().first()
    if a is None or not a.avatar_depo:
        raise _hata(404, "bulunamadi")
    from services import dosya_deposu

    try:
        veri = await dosya_deposu.oku(db, a.avatar_depo, f"asistan/{a.avatar}.webp")
    except dosya_deposu.DepoHatasi:
        raise _hata(404, "bulunamadi")
    return Response(veri, media_type="image/webp", headers={
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    })


@acik_router.get("/{anahtar}/ozet")
async def ozet(anahtar: str, db: AsyncSession = Depends(get_db)):
    """Pages Function: paylaşım önizlemesi ve çerçeve izni (frame-ancestors) için kısa bilgi."""
    a = await _asistan_bul(db, anahtar)
    yayinda = await _yayinda_mi(db, a)
    if not yayinda:
        raise _hata(410, "asistan_pasif")
    return Response(json.dumps({
        "ad": a.ad, "renk": a.renk, "dil": a.dil, "tam_sayfa": bool(a.tam_sayfa),
        "izinli_kokenler": s.json_yukle(a.izinli_kokenler, []), "avatar": s.gorsel_adresi(a.avatar, mutlak=True),
    }, ensure_ascii=False), media_type="application/json", headers={
        "Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex",
    })


@acik_router.get("/{anahtar}")
async def yapilandirma(
    anahtar: str,
    request: Request,
    dil: Optional[str] = Query(None, max_length=8),
    gomulu: int = Query(0, ge=0, le=1),
    kaynak: Optional[str] = Query(None, max_length=300),
    onizleme: int = Query(0, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
):
    _hiz(_yapilandirma_hizi, _ziyaretci(request))
    a, _, _ = await _kapi(request, db, anahtar, onizleme=bool(onizleme), gomulu=bool(gomulu), kaynak=kaynak)
    istenen = (dil or "").strip().lower()[:2]
    ui_dil = istenen if istenen in s.DILLER else (a.dil if a.dil in s.DILLER else None)
    hazir_dil = ui_dil or "tr"
    mesai = s.mesai_ici_mi(a)
    veri = {
        "anahtar": a.anahtar,
        "ad": a.ad,
        "karsilama": a.karsilama or None,
        "varsayilan_karsilama": s.hazir_metin("karsilama", hazir_dil),
        "renk": a.renk,
        "avatar": s.gorsel_adresi(a.avatar),
        "onerilen_sorular": s.json_yukle(a.onerilen_sorular, []),
        "dil": a.dil,
        "ui_dil": ui_dil,
        "aydinlatma": {
            "metin": a.aydinlatma_metni or None,
            "baglanti": a.aydinlatma_baglantisi or _gizlilik_adresi(hazir_dil),
            "ozel": bool(a.aydinlatma_baglantisi),
        },
        "mesai": {"aktif": mesai is not None, "ici": mesai},
        "mesaj_siniri": s.MESAJ_SINIRI,
        "oturum": s.oturum_uret(a.id),
        "ajans": a.hesap_email is None,
        "onizleme": bool(onizleme),
        "aktif": bool(a.aktif),
    }
    return Response(json.dumps(veri, ensure_ascii=False), media_type="application/json", headers=ACIK_BASLIKLAR)


class MesajGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    oturum: str = Field(..., max_length=100)
    mesaj: str = Field(..., max_length=8000)
    dil: str = Field(default="tr", max_length=8)
    gomulu: bool = False
    kaynak: Optional[str] = Field(default=None, max_length=300)
    onizleme: bool = False
    #: Bal küpü: görünmeyen alan; doluysa bot.
    web_adresi: Optional[str] = Field(default=None, max_length=500)


class DevirGirdisi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    oturum: str = Field(..., max_length=100)
    ad: str = Field(default="", max_length=500)
    eposta: str = Field(default="", max_length=500)
    telefon: str = Field(default="", max_length=100)
    not_: str = Field(default="", max_length=4000, alias="not")
    dil: str = Field(default="tr", max_length=8)
    gomulu: bool = False
    kaynak: Optional[str] = Field(default=None, max_length=300)
    onizleme: bool = False
    web_adresi: Optional[str] = Field(default=None, max_length=500)


def _ortak_kontroller(request: Request, a: AiAsistanlar, oturum: str, onizleme: bool) -> str:
    """Bot, hız sınırları ve oturum jetonu. Oturum özetini döndürür."""
    if not onizleme and _bot_mu(request):
        raise _hata(403, "bot")
    try:
        ozet_ = s.oturum_dogrula(oturum, a.id, en_az_sn=0 if onizleme else s.OTURUM_EN_AZ_SN)
    except s.AsistanHatasi as h:
        raise _cevir(h)
    return ozet_


@acik_router.post("/{anahtar}/mesaj")
async def mesaj(anahtar: str, request: Request, govde: MesajGirdisi = Body(...), db: AsyncSession = Depends(get_db)):
    a, onizleme, host = await _kapi(request, db, anahtar, onizleme=govde.onizleme, gomulu=govde.gomulu, kaynak=govde.kaynak)
    if govde.web_adresi:
        # Bal küpü: bot "başarılı" sansın, hiçbir şey yapılmasın.
        return {"mod": "normal", "yanit": s.hazir_metin("karsilama", s.dil_coz(govde.dil)), "kaynaklar": [],
                "bilinmiyor": False, "devir_onerisi": False, "mesaj_id": None}
    oturum_ozeti = _ortak_kontroller(request, a, govde.oturum, govde.onizleme)
    soru = s.mesaj_temizle(govde.mesaj, 10**6)
    if not soru:
        raise _hata(422, "mesaj_bos")
    if len(soru) > s.MESAJ_SINIRI:
        raise _hata(413, "mesaj_uzun", en_cok=s.MESAJ_SINIRI)
    ziyaretci = _ziyaretci(request)
    if not govde.onizleme:
        await _kalici_hiz((_ip_dakika, ziyaretci), (_ip_gun, ziyaretci), (_asistan_hizi, str(a.id)), (_oturum_hizi, oturum_ozeti))
    else:
        await _kalici_hiz((_oturum_hizi, oturum_ozeti))
    so = await s.sohbet_ac(db, a, oturum_ozeti, kaynak="onizleme" if govde.onizleme else ("gomulu" if govde.gomulu else "sayfa"),
                           koken=host, dil=s.dil_coz(govde.dil), ip_ozeti=None if govde.onizleme else ziyaretci)
    from services import yapay_zeka as ai

    try:
        sonuc = await s.yanit_uret(
            db, a, so, soru, ui_dil=govde.dil,
            ucretsiz=bool(onizleme and onizleme.yonetici and a.hesap_email), kisi=onizleme.kisi if onizleme else None,
        )
    except s.AsistanHatasi as h:
        raise _cevir(h)
    except ai.YapayZekaHatasi as h:
        raise _hata(h.durum, h.kod)
    return sonuc


@acik_router.post("/{anahtar}/devret")
async def devret(anahtar: str, request: Request, govde: DevirGirdisi = Body(...), db: AsyncSession = Depends(get_db)):
    a, onizleme, host = await _kapi(request, db, anahtar, onizleme=govde.onizleme, gomulu=govde.gomulu, kaynak=govde.kaynak)
    if govde.web_adresi:
        return {"ok": True}
    oturum_ozeti = _ortak_kontroller(request, a, govde.oturum, govde.onizleme)
    ziyaretci = _ziyaretci(request)
    if not govde.onizleme:
        await _kalici_hiz((_devir_hizi, ziyaretci))
    try:
        bilgi = s.devir_dogrula({"ad": govde.ad, "eposta": govde.eposta, "telefon": govde.telefon, "not": govde.not_})
    except s.AsistanHatasi as h:
        raise _cevir(h)
    so = await s.sohbet_ac(db, a, oturum_ozeti, kaynak="onizleme" if govde.onizleme else ("gomulu" if govde.gomulu else "sayfa"),
                           koken=host, dil=s.dil_coz(govde.dil), ip_ozeti=None if govde.onizleme else ziyaretci)
    sonuc = await s.devret(db, a, so, bilgi, onizleme=govde.onizleme)
    if govde.onizleme:
        return sonuc
    return {"ok": True, "zaten": sonuc.get("zaten", False), "mesai": sonuc.get("mesai")}


# Yönetici ve müşteri router'ları önce; sabit önekli görsel, genel `/{anahtar}` kalıbından önce.
router = (yonetici_router, musteri_router, gorsel_router, acik_router)
