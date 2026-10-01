"""Faz 4A — herkese açık API'nin kaynak işlemleri (REST uçları ve MCP araçları ORTAK).

Her fonksiyon doğrulanmış bir `ApiKimlik` alıyor ve kaydı yalnız anahtarın
erişebildiği kapsamda arıyor:

* Müşteri anahtarı → yalnız kendi hesabı (`client_email` / `hesap_email`
  küçük harfle eşleşir). Başka hesabın kaydı "yok" (404) — varlığı sızmıyor.
  Görevlerde yalnız `musteriye_gorunur`, faturalarda taslak olmayanlar.
* Ajans anahtarı → bütün hesaplar; `hesap` süzgeci isteğe bağlı.

Dönüş değerleri `schemas/public_api.py` modellerinin sözlük hâli; REST ucu
`response_model` ile, MCP aracı JSON metni + `structuredContent` olarak döndürüyor.
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from services.api_erisimi import (
    EN_COK_LIMIT,
    VARSAYILAN_LIMIT,
    ApiHatasi,
    ApiKimlik,
    cursor_coz,
    cursor_uret,
    eposta_duzelt,
    guncelleme_kosulu,
    iso,
    json_liste,
    tarih_coz,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TASLAK_FATURA = ("draft", "taslak")
GOREV_DURUMLARI = ("yapilacak", "suruyor", "incelemede", "tamam")
ONCELIKLER = ("dusuk", "normal", "yuksek", "acil")


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------
def _hesap_suzgeci(kimlik: ApiKimlik, hesap: Optional[str]) -> Optional[str]:
    """Sorgunun hesap koşulu: müşteride her zaman kendi hesabı; ajansta isteğe bağlı süzgeç."""
    if not kimlik.ajans:
        return kimlik.hesap
    return eposta_duzelt(hesap) or None


def _limit(limit: Optional[int]) -> int:
    try:
        sayi = int(limit if limit is not None else VARSAYILAN_LIMIT)
    except (TypeError, ValueError):
        raise ApiHatasi(400, "gecersiz_istek", mesaj="limit 1–100 arasında olmalı.")
    if sayi < 1 or sayi > EN_COK_LIMIT:
        raise ApiHatasi(400, "gecersiz_istek", mesaj="limit 1–100 arasında olmalı.")
    return sayi


async def _sayfala(
    db: AsyncSession,
    model: Any,
    sorgu: Any,
    donustur: Callable[[Any], Dict[str, Any]],
    *,
    limit: Optional[int],
    cursor: Optional[str],
    updated_since: Optional[str],
) -> Dict[str, Any]:
    """id artan sırada imleçli sayfa: yeni kayıtlar sona eklenir, sayfalarken kayıt kaçmaz."""
    adet = _limit(limit)
    son_id = cursor_coz(cursor)
    an = tarih_coz(updated_since, alan="updated_since")
    if son_id is not None:
        sorgu = sorgu.where(model.id > son_id)
    kosul = guncelleme_kosulu(model, an)
    if kosul is not None:
        sorgu = sorgu.where(kosul)
    satirlar = list((await db.execute(sorgu.order_by(model.id.asc()).limit(adet + 1))).scalars().all())
    daha = len(satirlar) > adet
    satirlar = satirlar[:adet]
    return {
        "veri": [donustur(s) for s in satirlar],
        "sonraki_cursor": cursor_uret(satirlar[-1].id) if daha and satirlar else None,
        "daha_var": daha,
    }


def _yok() -> ApiHatasi:
    return ApiHatasi(404, "bulunamadi")


def _tarih_metni(deger: Any) -> Optional[str]:
    if deger is None:
        return None
    if isinstance(deger, datetime):
        return iso(deger)
    if isinstance(deger, date):
        return deger.isoformat()
    return str(deger)


def _sayi(deger: Any) -> Optional[float]:
    if deger is None:
        return None
    try:
        return float(deger)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Projeler
# ---------------------------------------------------------------------------
def proje_sozlugu(p: Any) -> Dict[str, Any]:
    return {
        "id": p.id,
        "baslik": p.title,
        "kategori": p.category,
        "aciklama": p.description,
        "durum": p.status,
        "asama": p.stage,
        "ilerleme": p.progress,
        "hesap": eposta_duzelt(p.client_email) or None,
        "olusturma": iso(p.created_at),
        "guncelleme": iso(p.updated_at),
    }


def _proje_sorgusu(kimlik: ApiKimlik, hesap: Optional[str] = None):
    from models.projects import Projects

    sorgu = select(Projects)
    h = _hesap_suzgeci(kimlik, hesap)
    if h:
        sorgu = sorgu.where(func.lower(Projects.client_email) == h)
    return sorgu


async def projeler(db: AsyncSession, kimlik: ApiKimlik, *, hesap=None, limit=None, cursor=None, updated_since=None):
    from models.projects import Projects

    return await _sayfala(db, Projects, _proje_sorgusu(kimlik, hesap), proje_sozlugu, limit=limit, cursor=cursor,
                          updated_since=updated_since)


async def _proje(db: AsyncSession, kimlik: ApiKimlik, proje_id: int):
    from models.projects import Projects

    p = (await db.execute(_proje_sorgusu(kimlik).where(Projects.id == int(proje_id)))).scalars().first()
    if p is None:
        raise _yok()
    return p


async def proje(db: AsyncSession, kimlik: ApiKimlik, proje_id: int) -> Dict[str, Any]:
    return proje_sozlugu(await _proje(db, kimlik, proje_id))


# ---------------------------------------------------------------------------
# Görevler
# ---------------------------------------------------------------------------
def gorev_sozlugu(g: Any, ajans: bool) -> Dict[str, Any]:
    return {
        "id": g.id,
        "proje_id": g.proje_id,
        "baslik": g.baslik,
        "aciklama": g.aciklama,
        "durum": g.durum,
        "oncelik": g.oncelik or "normal",
        "bitis_tarihi": _tarih_metni(g.bitis_tarihi),
        "kilometre_tasi": bool(g.kilometre_tasi),
        "musteriye_gorunur": bool(g.musteriye_gorunur) if ajans else None,
        "tamamlandi_at": iso(g.tamamlandi_at),
        "olusturma": iso(g.created_at),
        "guncelleme": iso(g.updated_at),
    }


def _gorev_sorgusu(kimlik: ApiKimlik, hesap: Optional[str] = None):
    from models.proje_gorevleri import ProjectTasks
    from models.projects import Projects

    sorgu = select(ProjectTasks)
    h = _hesap_suzgeci(kimlik, hesap)
    if h:
        projeler_alt = select(Projects.id).where(func.lower(Projects.client_email) == h)
        sorgu = sorgu.where(ProjectTasks.proje_id.in_(projeler_alt))
    if not kimlik.ajans:
        sorgu = sorgu.where(ProjectTasks.musteriye_gorunur.is_(True))
    return sorgu


async def gorevler(db: AsyncSession, kimlik: ApiKimlik, *, proje_id=None, durum=None, hesap=None, limit=None, cursor=None,
                   updated_since=None):
    from models.proje_gorevleri import ProjectTasks

    sorgu = _gorev_sorgusu(kimlik, hesap)
    if proje_id is not None:
        sorgu = sorgu.where(ProjectTasks.proje_id == int(proje_id))
    if durum:
        if durum not in GOREV_DURUMLARI:
            raise ApiHatasi(400, "gecersiz_istek", mesaj="durum: yapilacak | suruyor | incelemede | tamam")
        sorgu = sorgu.where(ProjectTasks.durum == durum)
    return await _sayfala(db, ProjectTasks, sorgu, lambda g: gorev_sozlugu(g, kimlik.ajans), limit=limit, cursor=cursor,
                          updated_since=updated_since)


async def _gorev(db: AsyncSession, kimlik: ApiKimlik, gorev_id: int):
    from models.proje_gorevleri import ProjectTasks

    g = (await db.execute(_gorev_sorgusu(kimlik).where(ProjectTasks.id == int(gorev_id)))).scalars().first()
    if g is None:
        raise _yok()
    return g


async def gorev(db: AsyncSession, kimlik: ApiKimlik, gorev_id: int) -> Dict[str, Any]:
    return gorev_sozlugu(await _gorev(db, kimlik, gorev_id), kimlik.ajans)


def _metin(deger: Any, sinir: int, *, zorunlu: bool = False, alan: str = "") -> Optional[str]:
    metin = (str(deger) if deger is not None else "").strip()
    if not metin:
        if zorunlu:
            raise ApiHatasi(400, "gecersiz_istek", mesaj=f"{alan} gerekli.")
        return None
    if len(metin) > sinir:
        raise ApiHatasi(400, "gecersiz_istek", mesaj=f"{alan} en çok {sinir} karakter.")
    return metin


def _gun(deger: Any) -> Optional[date]:
    if deger in (None, ""):
        return None
    try:
        return date.fromisoformat(str(deger)[:10])
    except ValueError:
        raise ApiHatasi(400, "gecersiz_istek", mesaj="bitis_tarihi YYYY-MM-DD olmalı.")


async def _musteri_gorevi_mi(db: AsyncSession, kimlik: ApiKimlik, g: Any) -> bool:
    """Müşteri anahtarı yalnız kendi tarafının (hesap sahibi ya da ekip üyesi) açtığı görevi değiştirebilir."""
    olusturan = eposta_duzelt(g.olusturan_eposta)
    if not olusturan:
        return False
    if olusturan == kimlik.hesap:
        return True
    from models.hesap_uyeleri import HesapUyeleri

    satir = (
        await db.execute(
            select(HesapUyeleri.id).where(HesapUyeleri.hesap_email == kimlik.hesap, HesapUyeleri.uye_email == olusturan)
        )
    ).first()
    return satir is not None


async def gorev_olustur(db: AsyncSession, kimlik: ApiKimlik, govde: Dict[str, Any]) -> Dict[str, Any]:
    from models.proje_gorevleri import ProjectTasks
    from services import gorevler as gs

    p = await _proje(db, kimlik, govde.get("proje_id"))
    adet = (await db.execute(select(func.count(ProjectTasks.id)).where(ProjectTasks.proje_id == p.id))).scalar()
    if int(adet or 0) >= 500:
        raise ApiHatasi(409, "gorev_siniri")
    durum = "yapilacak"
    gorunur = True
    if kimlik.ajans:
        durum = govde.get("durum") or "yapilacak"
        gorunur = bool(govde.get("musteriye_gorunur"))
    if durum not in GOREV_DURUMLARI:
        raise ApiHatasi(400, "gecersiz_istek", mesaj="durum geçersiz.")
    oncelik = govde.get("oncelik") or "normal"
    if oncelik not in ONCELIKLER:
        raise ApiHatasi(400, "gecersiz_istek", mesaj="oncelik geçersiz.")
    sira = (
        await db.execute(
            select(func.coalesce(func.max(ProjectTasks.sira), -1)).where(ProjectTasks.proje_id == p.id, ProjectTasks.durum == durum)
        )
    ).scalar()
    an = datetime.now(timezone.utc)
    g = ProjectTasks(
        proje_id=p.id,
        baslik=_metin(govde.get("baslik"), 200, zorunlu=True, alan="baslik"),
        aciklama=_metin(govde.get("aciklama"), 4000, alan="aciklama"),
        durum=durum,
        oncelik=oncelik,
        bitis_tarihi=_gun(govde.get("bitis_tarihi")),
        sira=int(sira if sira is not None else -1) + 1,
        musteriye_gorunur=gorunur,
        kilometre_tasi=False,
        harcanan_saat=0.0,
        etiketler=json.dumps(["api"]),
        olusturan_eposta=kimlik.olusturan or (kimlik.hesap if not kimlik.ajans else None),
        tamamlandi_at=an if durum == "tamam" else None,
        created_at=an,
    )
    db.add(g)
    await db.commit()
    await db.refresh(g)
    if durum in gs.BILDIRIMLI_DURUMLAR:
        try:
            await gs.gorev_bildir(db, p, g)
        except Exception:  # noqa: BLE001
            logger.exception("API görevi bildirimi gönderilemedi")
    return gorev_sozlugu(g, kimlik.ajans)


async def gorev_guncelle(db: AsyncSession, kimlik: ApiKimlik, gorev_id: int, govde: Dict[str, Any]) -> Dict[str, Any]:
    from services import gorevler as gs

    g = await _gorev(db, kimlik, gorev_id)
    if not kimlik.ajans and not await _musteri_gorevi_mi(db, kimlik, g):
        raise ApiHatasi(403, "gorev_degistirilemez", mesaj="Müşteri anahtarı yalnız kendi tarafının açtığı görevi değiştirebilir.")
    if "baslik" in govde and govde["baslik"] is not None:
        g.baslik = _metin(govde["baslik"], 200, zorunlu=True, alan="baslik")
    if "aciklama" in govde:
        g.aciklama = _metin(govde.get("aciklama"), 4000, alan="aciklama")
    if "oncelik" in govde and govde["oncelik"] is not None:
        if govde["oncelik"] not in ONCELIKLER:
            raise ApiHatasi(400, "gecersiz_istek", mesaj="oncelik geçersiz.")
        g.oncelik = govde["oncelik"]
    if "bitis_tarihi" in govde:
        g.bitis_tarihi = _gun(govde.get("bitis_tarihi"))
    durum_degisti = False
    if govde.get("durum") is not None:
        yeni = govde["durum"]
        if yeni not in GOREV_DURUMLARI:
            raise ApiHatasi(400, "gecersiz_istek", mesaj="durum geçersiz.")
        if yeni == "tamam" and g.durum != "tamam":
            await gs.tamam_denetle(db, g)
        durum_degisti = gs.durum_ata(g, yeni)
    await db.commit()
    await db.refresh(g)
    if durum_degisti:
        try:
            p = await gs.proje_bul(db, g.proje_id)
            await gs.gorev_bildir(db, p, g)
        except Exception:  # noqa: BLE001
            logger.exception("API görev güncellemesi bildirimi gönderilemedi")
    return gorev_sozlugu(g, kimlik.ajans)


# ---------------------------------------------------------------------------
# Faturalar
# ---------------------------------------------------------------------------
def fatura_sozlugu(f: Any) -> Dict[str, Any]:
    return {
        "id": f.id,
        "no": f.invoice_no,
        "hesap": eposta_duzelt(f.client_email) or None,
        "aciklama": f.description,
        "tutar": float(f.amount or 0),
        "para_birimi": f.currency or "TRY",
        "durum": f.status,
        "tur": f.tur,
        "duzenleme_tarihi": f.issue_date,
        "vade_tarihi": f.due_date,
        "ara_toplam": _sayi(f.ara_toplam),
        "kdv_toplam": _sayi(f.kdv_toplam),
        "olusturma": iso(f.created_at),
        "guncelleme": iso(f.updated_at),
    }


def _fatura_sorgusu(kimlik: ApiKimlik, hesap: Optional[str] = None):
    from models.invoices import Invoices
    from sqlalchemy import or_

    sorgu = select(Invoices)
    h = _hesap_suzgeci(kimlik, hesap)
    if h:
        sorgu = sorgu.where(func.lower(Invoices.client_email) == h)
    if not kimlik.ajans:
        sorgu = sorgu.where(or_(Invoices.status.is_(None), Invoices.status.notin_(TASLAK_FATURA)))
    return sorgu


async def faturalar(db: AsyncSession, kimlik: ApiKimlik, *, durum=None, hesap=None, limit=None, cursor=None, updated_since=None):
    from models.invoices import Invoices

    sorgu = _fatura_sorgusu(kimlik, hesap)
    if durum:
        sorgu = sorgu.where(Invoices.status == str(durum)[:20])
    return await _sayfala(db, Invoices, sorgu, fatura_sozlugu, limit=limit, cursor=cursor, updated_since=updated_since)


async def fatura(db: AsyncSession, kimlik: ApiKimlik, fatura_id: int) -> Dict[str, Any]:
    from models.invoices import Invoices

    f = (await db.execute(_fatura_sorgusu(kimlik).where(Invoices.id == int(fatura_id)))).scalars().first()
    if f is None:
        raise _yok()
    return fatura_sozlugu(f)


# ---------------------------------------------------------------------------
# Destek
# ---------------------------------------------------------------------------
def talep_sozlugu(t: Any, mesajlar: Optional[List[Any]] = None) -> Dict[str, Any]:
    d = {
        "id": t.id,
        "konu": t.subject,
        "mesaj": t.message,
        "durum": t.status,
        "oncelik": t.priority,
        "proje_id": t.project_id,
        "hesap": eposta_duzelt(t.client_email) or None,
        "kaynak": t.kaynak,
        "son_mesaj_at": iso(t.son_mesaj_at),
        "olusturma": iso(t.created_at),
        "guncelleme": iso(t.updated_at),
        "mesajlar": None,
    }
    if mesajlar is not None:
        d["mesajlar"] = [
            {"id": m.id, "yazan": m.yazan if m.yazan in ("musteri", "ajans", "otomatik") else "ajans", "mesaj": m.mesaj,
             "olusturma": iso(m.created_at)}
            for m in mesajlar
        ]
    return d


def _talep_sorgusu(kimlik: ApiKimlik, hesap: Optional[str] = None):
    from models.support_tickets import Support_tickets

    sorgu = select(Support_tickets)
    h = _hesap_suzgeci(kimlik, hesap)
    if h:
        sorgu = sorgu.where(func.lower(Support_tickets.client_email) == h)
    return sorgu


async def talepler(db: AsyncSession, kimlik: ApiKimlik, *, durum=None, hesap=None, limit=None, cursor=None, updated_since=None):
    from models.support_tickets import Support_tickets

    sorgu = _talep_sorgusu(kimlik, hesap)
    if durum:
        sorgu = sorgu.where(Support_tickets.status == str(durum)[:20])
    return await _sayfala(db, Support_tickets, sorgu, talep_sozlugu, limit=limit, cursor=cursor, updated_since=updated_since)


async def _talep(db: AsyncSession, kimlik: ApiKimlik, talep_id: int):
    from models.support_tickets import Support_tickets

    t = (await db.execute(_talep_sorgusu(kimlik).where(Support_tickets.id == int(talep_id)))).scalars().first()
    if t is None:
        raise _yok()
    return t


async def talep(db: AsyncSession, kimlik: ApiKimlik, talep_id: int) -> Dict[str, Any]:
    from models.ticket_replies import Ticket_replies

    t = await _talep(db, kimlik, talep_id)
    mesajlar = (
        await db.execute(select(Ticket_replies).where(Ticket_replies.ticket_id == t.id).order_by(Ticket_replies.id.asc()).limit(500))
    ).scalars().all()
    return talep_sozlugu(t, list(mesajlar))


async def talep_olustur(db: AsyncSession, kimlik: ApiKimlik, govde: Dict[str, Any]) -> Dict[str, Any]:
    from models.support_tickets import Support_tickets
    from services.destek_talep import talep_acildi

    if kimlik.ajans:
        hesap = eposta_duzelt(govde.get("hesap"))
        if not hesap or "@" not in hesap:
            raise ApiHatasi(400, "gecersiz_istek", mesaj="Ajans anahtarıyla talep açarken `hesap` (müşteri e-postası) zorunlu.")
    else:
        hesap = kimlik.hesap
    proje_id = govde.get("proje_id")
    if proje_id is not None:
        p = await _proje(db, kimlik, proje_id)
        if eposta_duzelt(p.client_email) != hesap:
            raise _yok()
    oncelik = govde.get("oncelik") or "normal"
    if oncelik not in ONCELIKLER:
        raise ApiHatasi(400, "gecersiz_istek", mesaj="oncelik geçersiz.")
    t = Support_tickets(
        client_email=hesap,
        acan_email=kimlik.olusturan if not kimlik.ajans else None,
        subject=_metin(govde.get("konu"), 200, zorunlu=True, alan="konu"),
        message=_metin(govde.get("mesaj"), 10000, zorunlu=True, alan="mesaj"),
        status="open",
        priority=oncelik,
        project_id=int(proje_id) if proje_id is not None else None,
        kaynak="api",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    try:
        await talep_acildi(db, t, kanal="panel")
    except Exception:  # noqa: BLE001 - kurallar/SLA/bildirim talebi düşürmesin
        logger.exception("API talebi açılış adımları tamamlanamadı (id=%s)", t.id)
        await db.rollback()
    await db.refresh(t)
    return talep_sozlugu(t, [])


async def talep_yanitla(db: AsyncSession, kimlik: ApiKimlik, talep_id: int, govde: Dict[str, Any]) -> Dict[str, Any]:
    from services.destek_talep import mesaj_ekle

    t = await _talep(db, kimlik, talep_id)
    metin = _metin(govde.get("mesaj"), 10000, zorunlu=True, alan="mesaj")
    yazan = "ajans" if kimlik.ajans else "musteri"
    kayit = await mesaj_ekle(db, t, yazan=yazan, yazan_ad=None, yazan_email=kimlik.olusturan, metin=metin)
    return {"id": kayit.id, "yazan": yazan, "mesaj": kayit.mesaj, "olusturma": iso(kayit.created_at)}


# ---------------------------------------------------------------------------
# CRM (yalnız ajans)
# ---------------------------------------------------------------------------
def aday_sozlugu(a: Any) -> Dict[str, Any]:
    return {
        "id": a.id,
        "ad": a.ad,
        "firma": a.firma,
        "email": a.email,
        "telefon": a.telefon,
        "kaynak": a.kaynak,
        "asama": a.asama,
        "deger_tahmini": _sayi(a.deger_tahmini),
        "para_birimi": a.para_birimi,
        "olusturma": iso(a.created_at),
        "guncelleme": iso(a.updated_at),
    }


def _yalniz_ajans(kimlik: ApiKimlik) -> None:
    if not kimlik.ajans:
        raise ApiHatasi(403, "yalniz_ajans")


async def adaylar(db: AsyncSession, kimlik: ApiKimlik, *, asama=None, limit=None, cursor=None, updated_since=None):
    from models.crm import CrmAdaylari

    _yalniz_ajans(kimlik)
    sorgu = select(CrmAdaylari)
    if asama:
        sorgu = sorgu.where(CrmAdaylari.asama == str(asama)[:60])
    return await _sayfala(db, CrmAdaylari, sorgu, aday_sozlugu, limit=limit, cursor=cursor, updated_since=updated_since)


async def aday(db: AsyncSession, kimlik: ApiKimlik, aday_id: int) -> Dict[str, Any]:
    from models.crm import CrmAdaylari

    _yalniz_ajans(kimlik)
    a = (await db.execute(select(CrmAdaylari).where(CrmAdaylari.id == int(aday_id)))).scalars().first()
    if a is None:
        raise _yok()
    return aday_sozlugu(a)


async def aday_olustur(db: AsyncSession, kimlik: ApiKimlik, govde: Dict[str, Any]) -> Dict[str, Any]:
    from models.crm import CrmAdaylari, CrmAktiviteler
    from services import crm as servis

    _yalniz_ajans(kimlik)
    S = servis.SINIR
    ad = _metin(govde.get("ad"), S["ad"], zorunlu=True, alan="ad")
    email = servis.eposta_duzelt(govde.get("email"))
    if email and not servis.eposta_gecerli(email):
        raise ApiHatasi(400, "gecersiz_istek", mesaj="email geçersiz.")
    para = str(govde.get("para_birimi") or "TRY").upper()
    if para not in servis.PARA_BIRIMLERI:
        raise ApiHatasi(400, "gecersiz_istek", mesaj="para_birimi geçersiz.")
    deger = govde.get("deger_tahmini")
    if deger not in (None, ""):
        deger = _sayi(deger)
        if deger is None or deger < 0 or deger > 1e12:
            raise ApiHatasi(400, "gecersiz_istek", mesaj="deger_tahmini geçersiz.")
    else:
        deger = None
    await servis.asamalari_hazirla(db)
    liste = await servis.asamalar(db)
    hedef = servis.ilk_asama(liste)
    if hedef is None:
        raise ApiHatasi(409, "asama_yok")
    if email:
        mevcut = await db.run_sync(lambda s: servis._acik_aday_sync(s.connection(), email))
        if mevcut:
            raise ApiHatasi(409, "ayni_eposta_acik_aday", aday_id=mevcut)
    an = servis.simdi()
    a = CrmAdaylari(
        ad=ad, firma=_metin(govde.get("firma"), S["firma"], alan="firma"), email=email or None,
        telefon=_metin(govde.get("telefon"), S["telefon"], alan="telefon"), kaynak="manuel", kaynak_detay="API",
        asama=hedef.anahtar, olasilik=hedef.olasilik, deger_tahmini=round(deger, 2) if deger is not None else None,
        para_birimi=para, notlar=_metin(govde.get("notlar"), S["notlar"], alan="notlar"), etiketler=json.dumps(["api"]),
        puan=0, created_at=an, updated_at=an, asama_degisme_at=an,
    )
    db.add(a)
    await db.flush()
    db.add(CrmAktiviteler(
        aday_id=a.id, tur="sistem", olay="aday_olustu",
        veri=json.dumps({"kaynak": "manuel", "api": True}, ensure_ascii=False), yapan=kimlik.olusturan, zaman=an,
    ))
    await db.flush()
    await servis.puani_guncelle(db, a)
    await db.commit()
    await db.refresh(a)
    return aday_sozlugu(a)


# ---------------------------------------------------------------------------
# QR ve menü (salt okuma)
# ---------------------------------------------------------------------------
def qr_sozlugu(k: Any) -> Dict[str, Any]:
    from routers.dinamik_qr import durum_hesapla
    from services import dinamik_qr as qs

    statik = k.tur in qs.STATIK_TURLER
    return {
        "id": k.id,
        "ad": k.ad,
        "tur": k.tur,
        "kod": k.kod,
        "kisa_adres": None if statik else qs.kisa_adres(k.takma_ad or k.kod),
        "aktif": bool(k.aktif),
        "durum": durum_hesapla(k),
        "tarama_sayisi": int(k.tarama_sayisi or 0),
        "son_tarama_at": iso(k.son_tarama_at),
        "hesap": eposta_duzelt(k.hesap_email) or None,
        "olusturma": iso(k.created_at),
        "guncelleme": iso(k.updated_at),
    }


def _sahipli_sorgu(model: Any, kimlik: ApiKimlik, hesap: Optional[str]):
    sorgu = select(model)
    h = _hesap_suzgeci(kimlik, hesap)
    if h:
        sorgu = sorgu.where(func.lower(model.hesap_email) == h)
    return sorgu


async def qr_kodlari(db: AsyncSession, kimlik: ApiKimlik, *, hesap=None, limit=None, cursor=None, updated_since=None):
    from models.dinamik_qr import DinamikQr

    return await _sayfala(db, DinamikQr, _sahipli_sorgu(DinamikQr, kimlik, hesap), qr_sozlugu, limit=limit, cursor=cursor,
                          updated_since=updated_since)


async def qr_kodu(db: AsyncSession, kimlik: ApiKimlik, qr_id: int) -> Dict[str, Any]:
    from models.dinamik_qr import DinamikQr

    k = (await db.execute(_sahipli_sorgu(DinamikQr, kimlik, None).where(DinamikQr.id == int(qr_id)))).scalars().first()
    if k is None:
        raise _yok()
    return qr_sozlugu(k)


def menu_sozlugu(m: Any) -> Dict[str, Any]:
    from services.qr_menu import menu_adresi

    return {
        "id": m.id,
        "ad": m.ad,
        "slug": m.slug,
        "duzen": m.duzen,
        "aktif": bool(m.aktif),
        "adres": menu_adresi(m.slug),
        "hesap": eposta_duzelt(m.hesap_email) or None,
        "olusturma": iso(m.created_at),
        "guncelleme": iso(m.updated_at),
    }


def siparis_sozlugu(s: Any) -> Dict[str, Any]:
    return {
        "id": s.id,
        "siparis_no": s.siparis_no,
        "magaza_id": s.magaza_id,
        "durum": s.durum,
        "teslimat": s.teslimat,
        "masa": s.masa,
        "kalem_sayisi": len(json_liste(s.kalemler)),
        "ara_toplam_kurus": int(s.ara_toplam or 0),
        "indirim_kurus": int(s.indirim or 0),
        "paket_ucreti_kurus": int(s.paket_ucreti or 0),
        "toplam_kurus": int(s.toplam or 0),
        "para_birimi": s.para_birimi or "TRY",
        "olusturma": iso(s.created_at),
        "guncelleme": iso(s.updated_at),
    }


async def menuler(db: AsyncSession, kimlik: ApiKimlik, *, hesap=None, limit=None, cursor=None, updated_since=None):
    from models.qr_menu import MenuMagazalari

    return await _sayfala(db, MenuMagazalari, _sahipli_sorgu(MenuMagazalari, kimlik, hesap), menu_sozlugu, limit=limit,
                          cursor=cursor, updated_since=updated_since)


async def menu_siparisleri(db: AsyncSession, kimlik: ApiKimlik, magaza_id: int, *, durum=None, limit=None, cursor=None,
                           updated_since=None):
    from models.qr_menu import MenuMagazalari, MenuSiparisleri

    m = (await db.execute(_sahipli_sorgu(MenuMagazalari, kimlik, None).where(MenuMagazalari.id == int(magaza_id)))).scalars().first()
    if m is None:
        raise _yok()
    sorgu = select(MenuSiparisleri).where(MenuSiparisleri.magaza_id == m.id)
    if durum:
        sorgu = sorgu.where(MenuSiparisleri.durum == str(durum)[:16])
    return await _sayfala(db, MenuSiparisleri, sorgu, siparis_sozlugu, limit=limit, cursor=cursor, updated_since=updated_since)


# ---------------------------------------------------------------------------
# Hesap özeti
# ---------------------------------------------------------------------------
async def hesap_ozeti(db: AsyncSession, kimlik: ApiKimlik) -> Dict[str, Any]:
    from models.api_erisimi import ApiAnahtarlari
    from models.invoices import Invoices
    from models.support_tickets import Support_tickets
    from services.api_erisimi import gorunen_onek, kapsam_modulu_acik_mi

    a = (await db.execute(select(ApiAnahtarlari).where(ApiAnahtarlari.id == kimlik.anahtar_id))).scalars().first()
    sayilar: Dict[str, Any] = {}

    async def say(sorgu) -> int:
        return int((await db.execute(select(func.count()).select_from(sorgu.subquery()))).scalar() or 0)

    if kimlik.kapsam_var("projeler:oku"):
        sayilar["projeler"] = await say(_proje_sorgusu(kimlik))
    if kimlik.kapsam_var("gorevler:oku") and await kapsam_modulu_acik_mi(db, kimlik, "gorevler:oku"):
        sayilar["gorevler"] = await say(_gorev_sorgusu(kimlik))
    if kimlik.kapsam_var("faturalar:oku"):
        f = _fatura_sorgusu(kimlik)
        sayilar["faturalar"] = await say(f)
        sayilar["odenmemis_faturalar"] = await say(f.where(Invoices.status.in_(("unpaid", "overdue", "kismi_odendi"))))
    if kimlik.kapsam_var("destek:oku"):
        t = _talep_sorgusu(kimlik)
        sayilar["destek_talepleri"] = await say(t)
        sayilar["acik_destek_talepleri"] = await say(t.where(Support_tickets.status.in_(("open", "answered"))))
    return {
        "sahip": "ajans" if kimlik.ajans else "musteri",
        "hesap": kimlik.hesap,
        "anahtar": {
            "ad": a.ad if a else "",
            "onek": gorunen_onek(kimlik.onek),
            "kapsamlar": sorted(kimlik.kapsamlar),
            "son_kullanma": iso(a.son_kullanma) if a else None,
        },
        "sayilar": sayilar,
    }
