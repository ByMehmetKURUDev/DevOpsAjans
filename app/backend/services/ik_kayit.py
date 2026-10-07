"""Faz 6I — İnsan kaynakları: veritabanı yardımcıları (ayarlar, tatiller, bakiye, bildirimler).

Kurallar `services/ik.py`, uçlar `routers/ik.py`. Personele giden e-postalar katalog dışı olay
(`ik_personel`) olarak yalnız e-postayla gider: panel içi kopya yazılmaz, kişisel bağlantı (yetki belgesi)
kalıcı bildirim kaydından çıkarılır (Faz 6K öğrenci deseni). Resend/SMTP yoksa gönderim `notify`
katmanında zarifçe kayda düşer (iş akışı durmaz).
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.ik import IkAyarlari, IkDosyalar, IkIzinler, IkPersonel, IkTatiller, IkVardiyalar
from services import ik as s
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Personele giden e-posta (katalog dışı: yalnız e-posta).
PERSONEL_OLAYI = "ik_personel"
#: Hesap sahibine / ajans yöneticilerine yeni izin talebi (bildirim kataloğunda).
SAHIP_OLAYI = "ik_izin_talebi"


def _oturum():
    from core.database import db_manager

    return db_manager.async_session_maker() if db_manager.async_session_maker else None


# ---------------------------------------------------------------------------
# Ayarlar, sınırlar, tatiller
# ---------------------------------------------------------------------------
async def ayar_satiri(db: AsyncSession, hesap: Optional[str]) -> Optional[IkAyarlari]:
    return (await db.execute(select(IkAyarlari).where(IkAyarlari.kapsam == s.kapsam_anahtari(hesap)))).scalars().first()


async def kurallar_al(db: AsyncSession, hesap: Optional[str]) -> s.Kurallar:
    return s.kurallar(await ayar_satiri(db, hesap))


async def modul_ayari(db: AsyncSession, hesap: Optional[str], ad: str, varsayilan: Any) -> Any:
    """Müşteride modül ayarı; ajansta (hesap yok) sınır yok → None."""
    if not hesap:
        return None
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, s.MODUL, ad)
    return varsayilan if deger is None else deger


async def aktif_personel_sayisi(db: AsyncSession, hesap: Optional[str]) -> int:
    kosul = IkPersonel.hesap_email.is_(None) if hesap is None else IkPersonel.hesap_email == hesap
    return int((await db.execute(select(func.count(IkPersonel.id)).where(kosul, IkPersonel.durum == "aktif"))).scalar() or 0)


def hesap_kosulu(model: Any, hesap: Optional[str]):
    return model.hesap_email.is_(None) if hesap is None else model.hesap_email == hesap


async def eklenen_tatiller(db: AsyncSession, hesap: Optional[str], bas: Optional[date] = None,
                           bit: Optional[date] = None) -> List[IkTatiller]:
    sorgu = select(IkTatiller).where(IkTatiller.kapsam == s.kapsam_anahtari(hesap))
    if bas:
        sorgu = sorgu.where(IkTatiller.tarih >= bas)
    if bit:
        sorgu = sorgu.where(IkTatiller.tarih <= bit)
    return list((await db.execute(sorgu.order_by(IkTatiller.tarih))).scalars().all())


async def tatil_haritasi(db: AsyncSession, hesap: Optional[str], bas: date, bit: date, k: s.Kurallar) -> Dict[date, float]:
    ek = await eklenen_tatiller(db, hesap, bas, bit)
    return s.tatil_haritasi(range(bas.year, bit.year + 1), k.kapali_sabitler, [(t.tarih, bool(t.yarim)) for t in ek])


async def gun_hesapla(db: AsyncSession, hesap: Optional[str], bas: date, bit: date, yarim: bool,
                      k: Optional[s.Kurallar] = None) -> float:
    k = k or await kurallar_al(db, hesap)
    return s.izin_gunu(bas, bit, k.calisma_gunleri, await tatil_haritasi(db, hesap, bas, bit, k), yarim)


# ---------------------------------------------------------------------------
# Bakiye
# ---------------------------------------------------------------------------
async def bakiyeler(db: AsyncSession, personeller: Sequence[IkPersonel], k: s.Kurallar) -> Dict[int, Dict[str, Any]]:
    idler = [p.id for p in personeller]
    onayli: Dict[int, List[Tuple[date, float]]] = {}
    bekleyen: Dict[int, List[Tuple[date, float]]] = {}
    if idler:
        for pid, bas, gun, durum in (await db.execute(select(IkIzinler.personel_id, IkIzinler.baslangic, IkIzinler.gun, IkIzinler.durum)
                                                      .where(IkIzinler.personel_id.in_(idler), IkIzinler.tur == "yillik",
                                                             IkIzinler.durum.in_(s.ETKIN_DURUMLAR)))).all():
            (onayli if durum == "onaylandi" else bekleyen).setdefault(pid, []).append((bas, float(gun or 0)))
    return {p.id: s.bakiye_hesapla(p, k, onayli.get(p.id, []), bekleyen.get(p.id, [])) for p in personeller}


async def bakiye(db: AsyncSession, p: IkPersonel, k: Optional[s.Kurallar] = None) -> Dict[str, Any]:
    k = k or await kurallar_al(db, p.hesap_email)
    return (await bakiyeler(db, [p], k))[p.id]


# ---------------------------------------------------------------------------
# Çakışma ve izinli günler
# ---------------------------------------------------------------------------
async def cakisan_izinler(db: AsyncSession, personel_id: int, bas: date, bit: date, haric: Optional[int] = None) -> List[IkIzinler]:
    sorgu = select(IkIzinler).where(IkIzinler.personel_id == personel_id, IkIzinler.durum.in_(s.ETKIN_DURUMLAR),
                                    IkIzinler.baslangic <= bit, IkIzinler.bitis >= bas)
    if haric is not None:
        sorgu = sorgu.where(IkIzinler.id != haric)
    return list((await db.execute(sorgu.order_by(IkIzinler.baslangic))).scalars().all())


async def ayni_tarihte_izinliler(db: AsyncSession, hesap: Optional[str], personel_id: int, bas: date, bit: date) -> List[Dict[str, Any]]:
    """Aynı aralıkta onaylı izni olan DİĞER personel (ekip planı için bilgi)."""
    satirlar = (await db.execute(
        select(IkIzinler.personel_id, IkIzinler.baslangic, IkIzinler.bitis, IkPersonel.ad, IkPersonel.departman)
        .join(IkPersonel, IkPersonel.id == IkIzinler.personel_id)
        .where(hesap_kosulu(IkIzinler, hesap), IkIzinler.personel_id != personel_id, IkIzinler.durum == "onaylandi",
               IkIzinler.baslangic <= bit, IkIzinler.bitis >= bas).limit(20))).all()
    return [{"personel_id": pid, "ad": ad, "departman": dep, "baslangic": b.isoformat(), "bitis": e.isoformat()}
            for pid, b, e, ad, dep in satirlar]


async def izinli_gunler(db: AsyncSession, hesap: Optional[str], bas: date, bit: date) -> Dict[int, Dict[date, str]]:
    """Onaylı izinler: personel → {gün: tür} ([bas, bit] aralığında)."""
    sonuc: Dict[int, Dict[date, str]] = {}
    for pid, b, e, tur in (await db.execute(select(IkIzinler.personel_id, IkIzinler.baslangic, IkIzinler.bitis, IkIzinler.tur)
                                            .where(hesap_kosulu(IkIzinler, hesap), IkIzinler.durum == "onaylandi",
                                                   IkIzinler.baslangic <= bit, IkIzinler.bitis >= bas))).all():
        for g in s.gunler(max(b, bas), min(e, bit)):
            sonuc.setdefault(pid, {})[g] = tur
    return sonuc


async def izin_uyarilari(db: AsyncSession, p: IkPersonel, tur: str, bas: date, bit: date, gun: float, k: s.Kurallar,
                         haric: Optional[int] = None, haric_bekleyen_gun: float = 0.0) -> List[Dict[str, Any]]:
    """Talep/onay için uyarılar (ENGELLEMEZ): çakışan talep, yetersiz yıllık bakiye, yasal süre aşımı,
    çalışma günü yok, ayrılmış personel. `haric_bekleyen_gun`: değerlendirilen kayıt zaten bekleyen yıllık
    izinse onun günü (bakiyeden iki kez düşülmesin)."""
    uyarilar: List[Dict[str, Any]] = []
    for c in await cakisan_izinler(db, p.id, bas, bit, haric):
        uyarilar.append({"tur": "cakisan_talep", "izin_id": c.id, "izin_turu": c.tur, "durum": c.durum,
                         "baslangic": c.baslangic.isoformat(), "bitis": c.bitis.isoformat()})
    if tur == "yillik":
        b = await bakiye(db, p, k)
        kalan = b["kullanilabilir"] + haric_bekleyen_gun
        if gun > kalan:
            uyarilar.append({"tur": "bakiye_yetersiz", "kalan": kalan, "istenen": gun})
    if tur in s.YASAL_TURLER:
        yasal = k.yasal_gun(tur)
        olcu = s.takvim_gunu(bas, bit) if tur in s.TAKVIM_GUNLU else gun
        if yasal is not None and olcu > yasal:
            uyarilar.append({"tur": "yasal_sure_asildi", "yasal": yasal, "istenen": olcu,
                             "birim": "takvim" if tur in s.TAKVIM_GUNLU else "is_gunu"})
    if gun <= 0:
        uyarilar.append({"tur": "calisma_gunu_yok"})
    if p.durum == "ayrildi":
        uyarilar.append({"tur": "personel_ayrildi"})
    return uyarilar


# ---------------------------------------------------------------------------
# Dosyalar
# ---------------------------------------------------------------------------
async def dosya_kaydet(db: AsyncSession, p: IkPersonel, *, ad_ham: str, veri: bytes, yukleyen: Optional[str]) -> IkDosyalar:
    """Tür içerikten doğrulanır (`services/dosyalar.turu_dogrula`), içerik kalıcı depoya. Commit ÇAĞIRANA."""
    import secrets

    from services import dosya_deposu, dosyalar

    try:
        ad = dosyalar.ad_temizle(ad_ham)
        mime = dosyalar.turu_dogrula(ad, veri)
    except dosyalar.DosyaHatasi as h:
        raise s.IkHatasi(h.kod, "dosya", durum=h.durum)
    an = s.simdi()
    anahtar = f"ik/{an:%Y/%m}/{secrets.token_hex(16)}"
    try:
        depo = await dosya_deposu.yaz(db, anahtar, veri, mime)
    except dosya_deposu.DepoHatasi:
        raise s.IkHatasi("depo_hatasi", "dosya", durum=502)
    d = IkDosyalar(hesap_email=p.hesap_email, personel_id=p.id, ad=ad[:120], tur=mime, boyut=len(veri), depo=depo,
                   depolama_anahtari=anahtar, yukleyen=(yukleyen or None) and yukleyen[:254], created_at=an)
    db.add(d)
    await db.flush()
    return d


# ---------------------------------------------------------------------------
# Bildirimler
# ---------------------------------------------------------------------------
async def _ayar_firma(db: AsyncSession, hesap: Optional[str]) -> str:
    a = await ayar_satiri(db, hesap)
    if a and a.firma_adi:
        return a.firma_adi
    if hesap:
        try:
            from services.hesap_ekibi import hesap_adlari

            return (await hesap_adlari(db, [hesap])).get(hesap) or hesap
        except Exception:  # noqa: BLE001
            return hesap
    return "mehmetkuru.dev"


async def personele_eposta(db: AsyncSession, p: IkPersonel, konu: str, govde: str, gizliler: Sequence[str] = ()) -> bool:
    """Personele yalnız e-posta: panel içi kopya silinir; kişisel bağlantı kalıcı kayıttan çıkarılır."""
    from services.notify import dispatch

    if not p.eposta:
        return False
    satirlar = await dispatch(db, event_type=PERSONEL_OLAYI, title=konu, body=govde,
                              recipients=[{"email": p.eposta, "role": "client"}], link=None, ref_type="ik_personel", ref_id=p.id)
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
    return any(getattr(x, "channel", None) == "email" for x in satirlar)


def _portal_satirlari(p: IkPersonel, m: Dict[str, str]) -> Tuple[List[str], List[str]]:
    if not p.portal_acik or p.durum != "aktif":
        return [], []
    jeton = s.portal_jetonu(p.id, int(p.portal_surumu or 1))
    adres = s.portal_adresi(jeton)
    return ["", m["sayfa"].format(adres=adres)], [adres, jeton]


async def izin_epostasi(izin_id: int, olay: str) -> None:
    """Karar (onay / ret) ya da iptal sonrası personele e-posta (arka planda, kendi oturumuyla)."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            i = (await db.execute(select(IkIzinler).where(IkIzinler.id == izin_id))).scalars().first()
            if i is None:
                return
            p = (await db.execute(select(IkPersonel).where(IkPersonel.id == i.personel_id))).scalars().first()
            if p is None or not p.eposta:
                return
            m = s.metinler(p.dil or "tr")
            tur = s.tur_adi(i.tur, p.dil or "tr")
            aralik = s.aralik_metni(i.baslangic, i.bitis)
            anahtar = {"onay": "onay", "ret": "ret", "iptal": "iptal"}[olay]
            govde = [m["merhaba"].format(ad=p.ad), "", m[anahtar].format(tur=tur, aralik=aralik, gun=s.gun_metni(i.gun))]
            if i.karar_notu and olay in ("onay", "ret"):
                govde.append(m["not"].format(not_=i.karar_notu))
            ek, gizli = _portal_satirlari(p, m)
            govde += ek + ["", m["imza"].format(firma=await _ayar_firma(db, p.hesap_email))]
            await personele_eposta(db, p, m[f"{anahtar}_konu"], "\n".join(govde), gizli)
    except Exception:  # noqa: BLE001
        logger.exception("İK izin e-postası gönderilemedi (%s)", izin_id)


async def baglanti_epostasi(personel_id: int) -> bool:
    oturum = _oturum()
    if oturum is None:
        return False
    try:
        async with oturum as db:
            p = (await db.execute(select(IkPersonel).where(IkPersonel.id == personel_id))).scalars().first()
            if p is None or not p.eposta:
                return False
            m = s.metinler(p.dil or "tr")
            ek, gizli = _portal_satirlari(p, m)
            if not ek:
                return False
            govde = [m["merhaba"].format(ad=p.ad), "", m["baglanti"], *ek, "", m["imza"].format(firma=await _ayar_firma(db, p.hesap_email))]
            return await personele_eposta(db, p, m["baglanti_konu"], "\n".join(govde), gizli)
    except Exception:  # noqa: BLE001
        logger.exception("İK portal bağlantısı e-postası gönderilemedi (%s)", personel_id)
        return False


async def vardiya_epostalari(hesap: Optional[str], hafta_bas: date, personel_idleri: Sequence[int]) -> None:
    """Yayınlanan haftanın vardiyaları — etkilenen her personele bir e-posta."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            firma = await _ayar_firma(db, hesap)
            hafta_bit = hafta_bas + timedelta(days=7)
            for pid in personel_idleri:
                p = (await db.execute(select(IkPersonel).where(IkPersonel.id == pid))).scalars().first()
                if p is None or not p.eposta or p.durum != "aktif":
                    continue
                vardiyalar = (await db.execute(select(IkVardiyalar).where(
                    IkVardiyalar.personel_id == pid, IkVardiyalar.durum == "yayinda", IkVardiyalar.tarih >= hafta_bas,
                    IkVardiyalar.tarih < hafta_bit).order_by(IkVardiyalar.bas))).scalars().all()
                m = s.metinler(p.dil or "tr")
                satirlar = [m["merhaba"].format(ad=p.ad), "", m["vardiya"].format(hafta=hafta_bas.strftime("%d.%m.%Y"))]
                for v in vardiyalar:
                    satirlar.append(f"• {v.bas.strftime('%d.%m.%Y')} {s.saat_metni(v.bas)}–{s.saat_metni(v.bit)}")
                ek, gizli = _portal_satirlari(p, m)
                satirlar += ek + ["", m["imza"].format(firma=firma)]
                await personele_eposta(db, p, m["vardiya_konu"], "\n".join(satirlar), gizli)
    except Exception:  # noqa: BLE001
        logger.exception("İK vardiya e-postaları gönderilemedi")


async def talep_bildirimi(izin_id: int) -> None:
    """Personelin portaldan gönderdiği izin talebi → hesap sahibine (ekipte `ik` izinlilere de) / ajans
    yöneticilerine panel + e-posta bildirimi. Rapor türünde yalnız tarih aralığı."""
    oturum = _oturum()
    if oturum is None:
        return
    try:
        async with oturum as db:
            from services import notify

            i = (await db.execute(select(IkIzinler).where(IkIzinler.id == izin_id))).scalars().first()
            if i is None:
                return
            p = (await db.execute(select(IkPersonel).where(IkPersonel.id == i.personel_id))).scalars().first()
            if p is None:
                return
            tur = s.tur_adi(i.tur, "tr")
            baslik = f"Yeni izin talebi: {p.ad} — {tur}"
            satirlar = [f"Personel: {p.ad}", f"Tür: {tur}", f"Tarih: {s.aralik_metni(i.baslangic, i.bitis)}",
                        f"Çalışma günü: {s.gun_metni(i.gun)}"]
            if i.aciklama and i.tur != "rapor":
                satirlar.append(f"Not: {i.aciklama}")
            baslik, govde = await notify.render(db, SAHIP_OLAYI, baslik, "\n".join(satirlar), {"ad": p.ad, "tur": tur})
            if p.hesap_email:
                alicilar = [{"email": p.hesap_email, "role": "client"}]
                baglanti = "/client?sekme=ik"
            else:
                alicilar = await notify.admin_recipients(db)
                baglanti = "/admin?sekme=ik"
            await notify.dispatch(db, event_type=SAHIP_OLAYI, title=baslik, body=govde, recipients=alicilar, link=baglanti,
                                  ref_type="ik_izinler", ref_id=i.id)
    except Exception:  # noqa: BLE001
        logger.exception("İK izin talebi bildirimi gönderilemedi (%s)", izin_id)


async def personel_dosyalari(db: AsyncSession, personel_id: int) -> List[IkDosyalar]:
    return list((await db.execute(select(IkDosyalar).where(IkDosyalar.personel_id == personel_id)
                                  .order_by(IkDosyalar.id.desc()))).scalars().all())


def ilk(it: Iterable[Any]) -> Any:
    for x in it:
        return x
    return None
