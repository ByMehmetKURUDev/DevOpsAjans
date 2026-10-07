"""Faz 6H — hukuk bürosu: veritabanı işleri (ayarlar, tatiller, görünürlük, çatışma adayları, meta, zamanlı bakım).

Gizlilik (avukat–müvekkil sırrı)
--------------------------------
* `gizli` dosya yalnız hesap SAHİBİNE ve dosyanın SORUMLU avukatına görünür (ekip izni `hukuk` yetmez).
  Gizli dosyanın olayları, zaman/masraf kayıtları, ekleri ve portal paylaşımları da aynı kurala tabi.
* Ajans yöneticisi yalnız `meta_ozeti` görür: sayılar ve depolama. İçerik, not, belge, müvekkil kişisel
  verisi yönetici uçlarından DÖNMEZ.
* Bildirimler (panel/e-posta) içerik taşımaz: tür + tarih + kalan gün; ayrıntı modülde. Bildirim satırları
  ajans yöneticisinin okuyabildiği tabloda durduğu için bu bilerek böyle.

Zamanlı bakım (`hukuk_bakimi`, `services/zamanli.py`)
----------------------------------------------------
* Hatırlatmalar: tamamlanmamış her olay için kalan gün (İstanbul saatiyle) hesaplanır; hesabın eşikleri
  (varsayılan 7/3/1 gün önce + aynı gün sabah) içinde, kalan güne uyan EN KÜÇÜK eşik bir kez gönderilir
  (`hukuk_hatirlatmalari` benzersiz kısıtı). Sunucu uyuyup bir eşiği kaçırırsa eski eşik sonradan
  gönderilmez ("geçildi" yazılır) — 2 gün kala "7 gün kaldı" iletisi gitmesin. Aynı gün eşiği sabah
  saatinden (varsayılan 08:00) önce gitmez. Alıcı: olayın (yoksa dosyanın) sorumlu avukatı — hâlâ `hukuk`
  izinli aktif üyeyse; değilse hesap sahibi. E-posta Resend yapılandırılmamışsa panel bildirimi kalır.
* Silinenler: 30 günü dolan müvekkil/dosya ve bağlı kayıtları (ekler depodan) kalıcı silinir.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models.hukuk import (
    HukukAyarlari,
    HukukDosyalari,
    HukukEkleri,
    HukukHatirlatmalari,
    HukukMasraflari,
    HukukMesajlari,
    HukukMuvekkilleri,
    HukukOlaylari,
    HukukTatilleri,
    HukukZamanKayitlari,
)
from services import hukuk as s
from sqlalchemy import and_, delete, false, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def modul_ayari(db: AsyncSession, hesap: str, ad: str, varsayilan: Any) -> Any:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, s.MODUL, ad)
    return varsayilan if deger is None else deger


# ---------------------------------------------------------------------------
# Ayarlar ve tatiller
# ---------------------------------------------------------------------------
async def ayarlar(db: AsyncSession, hesap: str, olustur: bool = False) -> Optional[HukukAyarlari]:
    a = (await db.execute(select(HukukAyarlari).where(HukukAyarlari.hesap_email == hesap))).scalars().first()
    if a is None and olustur:
        a = HukukAyarlari(hesap_email=hesap, hatirlatma_gunleri=s.json_yaz(list(s.VARSAYILAN_HATIRLATMA)),
                          sabah_saati="08:00", adli_tatil_bas="07-20", adli_tatil_bit="08-31", adli_tatil_uzatma_gun=7,
                          adli_tatil_varsayilan=True, tatiller_tohumlandi=False, created_at=s.simdi())
        db.add(a)
        try:
            await db.flush()
        except IntegrityError:  # eşzamanlı ilk istek
            await db.rollback()
            a = (await db.execute(select(HukukAyarlari).where(HukukAyarlari.hesap_email == hesap))).scalars().first()
    return a


async def tatilleri_tohumla(db: AsyncSession, hesap: str) -> bool:
    """Sabit ulusal günleri (2429 s. Kanun) hesaba BİR KEZ ekler; kullanıcı sonra silebilir/düzenleyebilir."""
    a = await ayarlar(db, hesap, olustur=True)
    if a is None or a.tatiller_tohumlandi:
        return False
    for ay_gun, ad, yarim, _ in s.SABIT_TATILLER:
        db.add(HukukTatilleri(hesap_email=hesap, ad=ad, tarih=datetime(2000, int(ay_gun[:2]), int(ay_gun[3:])).date(),
                              tekrar=True, yarim=yarim, tur="sabit", created_at=s.simdi()))
    a.tatiller_tohumlandi = True
    await db.flush()
    return True


async def tatiller(db: AsyncSession, hesap: str) -> List[HukukTatilleri]:
    return list((await db.execute(select(HukukTatilleri).where(HukukTatilleri.hesap_email == hesap)
                                  .order_by(HukukTatilleri.tekrar.desc(), HukukTatilleri.tarih))).scalars().all())


def tatil_kurallari(satirlar: Iterable[HukukTatilleri]) -> List[s.Tatil]:
    return [s.Tatil(ad=t.ad, tarih=t.tarih, bitis=t.bitis, tekrar=bool(t.tekrar), yarim=bool(t.yarim)) for t in satirlar]


async def sure_hesapla(db: AsyncSession, hesap: str, g: Dict[str, Any]) -> Dict[str, Any]:
    """Son günü hesaplar. Sabit ulusal günler henüz eklenmemişse önce ekler (çağıran commit eder)."""
    await tatilleri_tohumla(db, hesap)
    a = await ayarlar(db, hesap)
    baslangic = s.tarih_duzelt(g.get("baslangic"), "baslangic", bos_olabilir=False)
    miktar = s.tam_sayi(g.get("miktar"), "miktar", 1, 3650)
    birim = s.secim(g.get("birim"), s.SURE_BIRIMLERI, "birim")
    adli = g.get("adli_tatil")
    if adli is None:
        adli = bool(a.adli_tatil_varsayilan) if a else True
    adli = s.bool_duzelt(adli, "adli_tatil")
    sonuc = s.son_gun_hesapla(
        baslangic, int(miktar), birim, adli_tatil=adli, tatiller=tatil_kurallari(await tatiller(db, hesap)),
        adli_bas=(a.adli_tatil_bas if a else "07-20"), adli_bit=(a.adli_tatil_bit if a else "08-31"),
        uzatma_gun=int(a.adli_tatil_uzatma_gun if a else 7),
    )
    return sonuc


# ---------------------------------------------------------------------------
# Görünürlük (gizli dosya)
# ---------------------------------------------------------------------------
def dosya_gorebilir_mi(d: HukukDosyalari, kisi: str, sahip: bool) -> bool:
    return (not d.gizli) or sahip or (bool(d.sorumlu_email) and d.sorumlu_email == kisi)


def gorunur_dosya_kosulu(kisi: str, sahip: bool):
    if sahip:
        return true()
    return or_(HukukDosyalari.gizli.is_(False), HukukDosyalari.gizli.is_(None), HukukDosyalari.sorumlu_email == kisi)


async def gorunur_dosya_idleri(db: AsyncSession, hesap: str, kisi: str, sahip: bool, silinmis: bool = False) -> List[int]:
    kosul = HukukDosyalari.silindi_at.isnot(None) if silinmis else HukukDosyalari.silindi_at.is_(None)
    return [i for (i,) in (await db.execute(select(HukukDosyalari.id).where(
        HukukDosyalari.hesap_email == hesap, kosul, gorunur_dosya_kosulu(kisi, sahip)))).all()]


async def acik_dosya_sayisi(db: AsyncSession, hesap: str) -> int:
    return int((await db.execute(select(func.count(HukukDosyalari.id)).where(
        HukukDosyalari.hesap_email == hesap, HukukDosyalari.silindi_at.is_(None),
        HukukDosyalari.durum.in_(("acik", "beklemede"))))).scalar() or 0)


async def ekip(db: AsyncSession, hesap: str) -> List[Dict[str, Any]]:
    """Sorumlu avukat seçimi: hesap sahibi + `hukuk` izinli aktif üyeler."""
    from services import hesap_ekibi as he

    liste = [{"eposta": hesap, "sahip": True}]
    for u in await he.uyeler(db, hesap):
        if he.gecerli_durum(u) == "aktif" and s.IZIN in he.izinleri_coz(u.izinler, u.rol):
            liste.append({"eposta": u.uye_email, "sahip": False})
    return liste


async def sorumlu_gecerli_mi(db: AsyncSession, hesap: str, eposta: str) -> bool:
    from services import hesap_ekibi as he

    return eposta == hesap or await he.hesapta_izinli_mi(db, eposta, hesap, s.IZIN)


# ---------------------------------------------------------------------------
# Çıkar çatışması adayları
# ---------------------------------------------------------------------------
async def catisma_adaylari(db: AsyncSession, hesap: str) -> Tuple[List[s.Aday], Dict[int, HukukDosyalari], Dict[int, HukukMuvekkilleri]]:
    """Silinmemiş bütün müvekkiller ve dosyaların karşı tarafları (gizli dosyalar DAHİL — çatışma kaçmasın;
    ayrıntıyı gösterip göstermemeye router karar verir)."""
    adaylar: List[s.Aday] = []
    muv = {m.id: m for m in (await db.execute(select(HukukMuvekkilleri).where(
        HukukMuvekkilleri.hesap_email == hesap, HukukMuvekkilleri.silindi_at.is_(None)))).scalars().all()}
    for m in muv.values():
        adaylar.append(s.Aday("muvekkil", m.ad, m.ad_normal or s.ad_normalle(m.ad), m.vergi_no, m.id))
    dosyalar = {d.id: d for d in (await db.execute(select(HukukDosyalari).where(
        HukukDosyalari.hesap_email == hesap, HukukDosyalari.silindi_at.is_(None)))).scalars().all()}
    for d in dosyalar.values():
        for k in s.json_yukle(d.karsi_taraflar, []) or []:
            if isinstance(k, dict) and k.get("ad"):
                adaylar.append(s.Aday("karsi_taraf", k["ad"], s.ad_normalle(k["ad"]), k.get("vergi_no") or None,
                                      d.muvekkil_id, d.id))
    return adaylar, dosyalar, muv


# ---------------------------------------------------------------------------
# Yönetici destek görünümü: YALNIZ meta veri
# ---------------------------------------------------------------------------
META_ALANLARI = ("hesap_email", "modul_acik", "muvekkil_sayisi", "dosya_sayisi", "acik_dosya", "kapanan_dosya",
                 "yaklasan_sure", "yaklasan_olay", "depolama_bayt", "ek_sayisi", "portal_bagli_muvekkil")


async def meta_ozeti(db: AsyncSession, hesaplar: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Hesap başına sayılar. İçerik (ad, no, konu, not, belge adı) ASLA buraya girmez — test bunu tarıyor."""
    from models.workspace_modules import WorkspaceModules
    from services.moduller import modul_acik_mi

    if hesaplar is None:
        kume: Set[str] = set()
        for model in (HukukMuvekkilleri, HukukDosyalari):
            kume |= {h for (h,) in (await db.execute(select(model.hesap_email).distinct())).all() if h}
        kume |= {h for (h,) in (await db.execute(select(WorkspaceModules.musteri_eposta).where(
            WorkspaceModules.modul_anahtari == s.MODUL, WorkspaceModules.acik.is_(True)))).all() if h}
        hesaplar = sorted(kume)
    bugun = s.yerel_bugun()
    sinir = bugun + timedelta(days=s.YAKLASAN_GUN)
    sonuc = []
    for h in hesaplar:
        async def say(sorgu) -> int:
            return int((await db.execute(sorgu)).scalar() or 0)

        dosya_kosul = and_(HukukDosyalari.hesap_email == h, HukukDosyalari.silindi_at.is_(None))
        canli_dosya = select(HukukDosyalari.id).where(dosya_kosul)
        olay_kosul = and_(HukukOlaylari.hesap_email == h, HukukOlaylari.tamamlandi_at.is_(None),
                          HukukOlaylari.tarih >= bugun, HukukOlaylari.tarih <= sinir,
                          or_(HukukOlaylari.dosya_id.is_(None), HukukOlaylari.dosya_id.in_(canli_dosya)))
        sonuc.append({
            "hesap_email": h,
            "modul_acik": await modul_acik_mi(db, h, s.MODUL),
            "muvekkil_sayisi": await say(select(func.count(HukukMuvekkilleri.id)).where(
                HukukMuvekkilleri.hesap_email == h, HukukMuvekkilleri.silindi_at.is_(None))),
            "dosya_sayisi": await say(select(func.count(HukukDosyalari.id)).where(dosya_kosul)),
            "acik_dosya": await say(select(func.count(HukukDosyalari.id)).where(
                dosya_kosul, HukukDosyalari.durum.in_(("acik", "beklemede")))),
            "kapanan_dosya": await say(select(func.count(HukukDosyalari.id)).where(dosya_kosul, HukukDosyalari.durum == "kapandi")),
            "yaklasan_sure": await say(select(func.count(HukukOlaylari.id)).where(olay_kosul, HukukOlaylari.tur == "kesin_sure")),
            "yaklasan_olay": await say(select(func.count(HukukOlaylari.id)).where(olay_kosul)),
            "depolama_bayt": await say(select(func.coalesce(func.sum(HukukEkleri.boyut), 0)).where(HukukEkleri.hesap_email == h)),
            "ek_sayisi": await say(select(func.count(HukukEkleri.id)).where(HukukEkleri.hesap_email == h,
                                                                            HukukEkleri.tip != "baglanti")),
            "portal_bagli_muvekkil": await say(select(func.count(HukukMuvekkilleri.id)).where(
                HukukMuvekkilleri.hesap_email == h, HukukMuvekkilleri.silindi_at.is_(None),
                HukukMuvekkilleri.portal_acik.is_(True))),
        })
    return sonuc


# ---------------------------------------------------------------------------
# Kalıcı silme (silinenler 30 gün sonra; elle "kalıcı sil" yok — geri alma penceresi)
# ---------------------------------------------------------------------------
async def ekleri_sil(db: AsyncSession, ekler: Iterable[HukukEkleri]) -> None:
    from services import dosya_deposu

    for e in list(ekler):
        if e.depo and e.anahtar:
            try:
                await dosya_deposu.sil(db, e.depo, e.anahtar)
            except Exception:  # noqa: BLE001 - yetim içerik zararsız; satır yine gider
                logger.warning("Hukuk eki depodan silinemedi (%s)", e.id)
        await db.delete(e)


async def dosyayi_kalici_sil(db: AsyncSession, d: HukukDosyalari) -> None:
    olay_idleri = [i for (i,) in (await db.execute(select(HukukOlaylari.id).where(HukukOlaylari.dosya_id == d.id))).all()]
    if olay_idleri:
        await db.execute(delete(HukukHatirlatmalari).where(HukukHatirlatmalari.olay_id.in_(olay_idleri)))
    for model in (HukukOlaylari, HukukZamanKayitlari, HukukMasraflari):
        for x in (await db.execute(select(model).where(model.dosya_id == d.id))).scalars().all():
            await db.delete(x)
    await ekleri_sil(db, (await db.execute(select(HukukEkleri).where(HukukEkleri.dosya_id == d.id))).scalars().all())
    for m in (await db.execute(select(HukukMesajlari).where(HukukMesajlari.dosya_id == d.id))).scalars().all():
        m.dosya_id = None
    await db.delete(d)


async def muvekkili_kalici_sil(db: AsyncSession, m: HukukMuvekkilleri) -> None:
    for d in (await db.execute(select(HukukDosyalari).where(HukukDosyalari.muvekkil_id == m.id))).scalars().all():
        await dosyayi_kalici_sil(db, d)
    for x in (await db.execute(select(HukukMesajlari).where(HukukMesajlari.muvekkil_id == m.id))).scalars().all():
        await db.delete(x)
    await db.delete(m)


async def silinenleri_temizle(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, int]:
    esik = (an or s.simdi()) - timedelta(days=s.SILINENLER_GUN)
    sayi = {"dosya": 0, "muvekkil": 0}
    for d in (await db.execute(select(HukukDosyalari).where(HukukDosyalari.silindi_at.isnot(None),
                                                             HukukDosyalari.silindi_at <= esik).limit(200))).scalars().all():
        await dosyayi_kalici_sil(db, d)
        sayi["dosya"] += 1
    for m in (await db.execute(select(HukukMuvekkilleri).where(HukukMuvekkilleri.silindi_at.isnot(None),
                                                                HukukMuvekkilleri.silindi_at <= esik).limit(200))).scalars().all():
        await muvekkili_kalici_sil(db, m)
        sayi["muvekkil"] += 1
    await db.commit()
    return sayi


# ---------------------------------------------------------------------------
# Hatırlatmalar
# ---------------------------------------------------------------------------
BILDIRIM_BASLIGI = {
    "durusma": "Yaklaşan duruşma", "kesif": "Yaklaşan keşif", "bilirkisi": "Yaklaşan bilirkişi incelemesi",
    "kesin_sure": "Kesin süre yaklaşıyor", "gorev": "Yaklaşan görev",
}


def hatirlatma_esigi(kalan: int, esikler: Sequence[int], sabah_gecti: bool) -> Optional[int]:
    """Kalan güne uyan EN KÜÇÜK eşik (0 = aynı gün; sabah saatinden önce yok)."""
    uygun = [e for e in esikler if kalan <= e and not (e == 0 and not sabah_gecti)]
    if kalan == 0 and not sabah_gecti:
        return None
    return min(uygun) if uygun else None


async def _alici(db: AsyncSession, o: HukukOlaylari, d: Optional[HukukDosyalari]) -> str:
    aday = o.sorumlu_email or (d.sorumlu_email if d is not None else None) or o.hesap_email
    if aday != o.hesap_email and not await sorumlu_gecerli_mi(db, o.hesap_email, aday):
        aday = o.hesap_email
    # Gizli dosyada alıcı yalnız sahip ya da dosyanın sorumlusu olabilir.
    if d is not None and d.gizli and aday not in (o.hesap_email, d.sorumlu_email):
        aday = o.hesap_email
    return aday


async def hatirlatmalari_gonder(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, int]:
    from services import notify
    from services.hesap_ekibi import _hesap_baglantisi
    from services.moduller import modul_acik_mi

    an = an or s.simdi()
    bugun = s.yerel_bugun(an)
    saat = s.yerel_saat(an)
    sonuc = {"gonderilen": 0, "atlanan": 0}
    olaylar = (await db.execute(select(HukukOlaylari).where(
        HukukOlaylari.tamamlandi_at.is_(None), HukukOlaylari.tarih >= bugun,
        HukukOlaylari.tarih <= bugun + timedelta(days=s.HATIRLATMA_EN_COK_GUN)).order_by(HukukOlaylari.tarih).limit(2000))).scalars().all()
    if not olaylar:
        return sonuc
    ayar_onbellek: Dict[str, Tuple[List[int], str, bool]] = {}
    gonderilmis: Dict[int, Set[int]] = {}
    for oid, esik in (await db.execute(select(HukukHatirlatmalari.olay_id, HukukHatirlatmalari.esik).where(
            HukukHatirlatmalari.olay_id.in_([o.id for o in olaylar])))).all():
        gonderilmis.setdefault(oid, set()).add(int(esik))
    dosyalar = {d.id: d for d in (await db.execute(select(HukukDosyalari).where(
        HukukDosyalari.id.in_([o.dosya_id for o in olaylar if o.dosya_id])))).scalars().all()}
    for o in olaylar:
        d = dosyalar.get(o.dosya_id) if o.dosya_id else None
        if o.dosya_id and (d is None or d.silindi_at is not None):
            continue
        if o.hesap_email not in ayar_onbellek:
            a = await ayarlar(db, o.hesap_email)
            ayar_onbellek[o.hesap_email] = (
                s.hatirlatma_gunleri(a.hatirlatma_gunleri if a else None), (a.sabah_saati if a else None) or "08:00",
                await modul_acik_mi(db, o.hesap_email, s.MODUL))
        esikler, sabah, acik = ayar_onbellek[o.hesap_email]
        if not acik:
            continue
        kalan = (o.tarih - bugun).days
        esik = hatirlatma_esigi(kalan, esikler, saat >= sabah)
        if esik is None or esik in gonderilmis.get(o.id, set()):
            continue
        # Bu eşik + daha büyük (kaçırılmış) eşikler tek işlemde yazılır; benzersiz kısıt ikinci gönderimi engeller.
        try:
            db.add(HukukHatirlatmalari(olay_id=o.id, esik=esik, durum="gonderildi", created_at=an))
            for e in esikler:
                if e > esik and e not in gonderilmis.get(o.id, set()):
                    db.add(HukukHatirlatmalari(olay_id=o.id, esik=e, durum="gecildi", created_at=an))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            sonuc["atlanan"] += 1
            continue
        gonderilmis.setdefault(o.id, set()).update({e for e in esikler if e >= esik})
        alici = await _alici(db, o, d)
        baslik = BILDIRIM_BASLIGI.get(o.tur, "Yaklaşan olay")
        ne_zaman = "bugün" if kalan == 0 else f"{kalan} gün kaldı"
        tarih_metni = o.tarih.strftime("%d.%m.%Y") + (f" {o.saat}" if o.saat else "")
        link = "/client?sekme=hukuk&alt=takvim"
        if alici != o.hesap_email:
            link = _hesap_baglantisi(link, o.hesap_email)
        await notify.dispatch(
            db, event_type="hukuk_hatirlatma", title=f"{baslik}: {ne_zaman}",
            # Gizlilik: dosya no, mahkeme, müvekkil adı bildirimde YOK (bildirim satırını ajans da okuyabilir).
            body=f"Tarih: {tarih_metni}. Ayrıntılar Hukuk › Takvim bölümünde.",
            recipients=[{"email": alici, "role": "client"}], link=link, ref_type="hukuk_olay", ref_id=o.id,
        )
        sonuc["gonderilen"] += 1
    return sonuc


async def zamanli_bakim(db: AsyncSession) -> Dict[str, Any]:
    h = await hatirlatmalari_gonder(db)
    t = await silinenleri_temizle(db)
    return {"hatirlatma": h, "silinen": t}


# ---------------------------------------------------------------------------
# Portal mesajı bildirimi (içeriksiz; ajansın gelen kutusuna düşmez)
# ---------------------------------------------------------------------------
async def portal_mesaji_bildir(db: AsyncSession, m: HukukMuvekkilleri, mesaj_id: int) -> None:
    from services import notify

    alicilar = [{"email": m.hesap_email, "role": "client"}]
    await notify.dispatch(
        db, event_type="hukuk_portal_mesaj", title="Müvekkil portalından yeni mesaj",
        body="Hukuk › Mesajlar bölümünden okuyabilirsiniz.", recipients=alicilar,
        link="/client?sekme=hukuk&alt=mesajlar", ref_type="hukuk_mesaj", ref_id=mesaj_id,
    )


__all__ = [
    "ayarlar", "tatilleri_tohumla", "tatiller", "tatil_kurallari", "sure_hesapla", "dosya_gorebilir_mi",
    "gorunur_dosya_kosulu", "gorunur_dosya_idleri", "acik_dosya_sayisi", "ekip", "sorumlu_gecerli_mi",
    "catisma_adaylari", "meta_ozeti", "META_ALANLARI", "silinenleri_temizle", "hatirlatma_esigi",
    "hatirlatmalari_gonder", "zamanli_bakim", "portal_mesaji_bildir", "dosyayi_kalici_sil", "muvekkili_kalici_sil",
    "ekleri_sil", "modul_ayari",
]
