"""Faz 5K — ortaklık (referans) programı: başvuru, atıf, tıklama, komisyon defteri, ödeme talebi.

PARA AKTARIMI YOK. Komisyonu yönetici kendi bankasından öder ve panelde
"ödendi" işaretler (dekont eki, ortağa e-posta). Bu modül yalnız defter tutar.

Akış
----
1. Herkese açık `/ortaklik` sayfasından başvuru (KVKK aydınlatma satırı +
   AYRI, isteğe bağlı pazarlama izni; program koşullarının kabulü sözleşme
   kurulması içindir, rıza değil — kabul anı ve koşul metninin sürümü
   yazılır). Başvuru Gelen kutusuna (`ortak_basvurusu`) düşer.
2. Yönetici onaylar: referans kodu (yoksa addan üretilir) ve oran (boşsa
   program varsayılanı). Ortak panele başvurudaki e-postalı kullanıcı
   hesabıyla girer (hesabı yoksa aynı adresle kayıt olur).
3. Ziyaretçi `?ref=<kod>` ile gelir: tarayıcı kodu YALNIZ çerez/rıza bandında
   izin verildiyse cihazda 30 gün saklar (izin yoksa yalnız o sayfa
   oturumunun belleğinde); tıklama ortak başına GÜNLÜK toplam olarak sayılır
   (IP, çerez kimliği, tarayıcı bilgisi tutulmaz). Formda (iletişim, teklif al)
   kod CRM adayına yazılır ve müşteri (e-posta) → ortak ATFI açılır. Müşteri
   başına tek atıf: ayardan "ilk" (varsayılan) ya da "son" referans geçerli.
4. Komisyon: `fatura.odendi` olayından (Faz 4A olay altyapısının ek abonesi,
   aynı işlemde, SAVEPOINT), fatura başına TEK (`tekil` benzersiz). Kural
   (ayarlardan):
   * İLK SATIŞ — oran X (ortağa özel oran, yoksa `varsayilan_oran`): atıflı
     müşterinin (ortak × müşteri) komisyon yazılan ilk satışı. Satış sayılan
     fatura: kabul edilmiş bir teklife bağlı, ortağa bağlı bir indirim kodu
     taşıyor ya da sitedeki "Teklif al" / "Satın al" akışından (fiyat talebi)
     doğmuş (ayarda "bütün ödenen faturalar" açılabilir). Aynı teklifin
     sonraki faturaları (peşinat → kalan) ilk satışın parçası, yine X.
   * TEKRAR — oran Y, süre N ay (`tekrar_oran`, `tekrar_ay`; N = 0 kapalı):
     ilk satıştan sonraki N ay içinde ödenen TEKRARLAYAN (abonelik)
     faturaları. Başka sonraki satışlara komisyon yazılmaz.
   Taban: KDV HARİÇ tutar (kalemli faturada ara toplam; tek tutarlı eski
   faturada tutar).
   İade faturası → oranlı TERS kayıt; ödeme geri alınırsa (ödendi → başka
   durum) kalanın tamamı ters kayıt. Ters kayıt, aslı beklemedeyse beklemede
   (birlikte olgunlaşır, net 0), değilse hemen onaylı (bakiyeden düşer; ödenmiş
   komisyonun iadesi şüpheli işaretlenir).
5. Durumlar: beklemede (iade süresi; ayar, varsayılan 30 gün) → onaylandi
   (zamanlı iş ve panel açılışında) → odeme_talebinde → odendi; iptal.
   Ödeme talebi para birimi başına onaylı bakiyenin TAMAMI, en az tutar
   ayardan; IBAN biçim + mod-97 denetimli metin (kart numarası kabul edilmez).

Kötüye kullanım
---------------
* Ortak kendi kendine referans veremez: müşteri e-postası ortağınkiyle aynıysa
  ya da ikisi aynı müşteri hesabının ekibindeyse (`hesap_uyeleri` aktif) atıf
  açılmaz, komisyon yazılmaz; ortak şüpheli işaretlenir.
* Aynı kurumsal alan adı (ortak@firma.com → musteri@firma.com), ödenmiş
  komisyonun iadesi → komisyon şüpheli işaretlenir; yönetici görür, isterse
  iptal eder.

Ayarlar `site_settings` `ortaklik_ayarlari` (JSON; gizli anahtar — herkese
açık okuma `/api/v1/ortaklik/program` ucundan, yalnız gerekli alanlar).
"""

import hashlib
import json
import logging
import re
import secrets
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models.ortaklik import (
    AJANS,
    IndirimKodlari,
    OrtakKomisyonlari,
    OrtakOdemeTalepleri,
    Ortaklar,
    OrtakReferanslari,
    OrtakTiklamalari,
)
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AYAR_ANAHTARI = "ortaklik_ayarlari"
DURUMLAR = ("beklemede", "onaylandi", "reddedildi", "askida")
KOMISYON_DURUMLARI = ("beklemede", "onaylandi", "odeme_talebinde", "odendi", "iptal")
TALEP_DURUMLARI = ("bekliyor", "odendi", "reddedildi")
PARA_BIRIMLERI = ("TRY", "USD", "EUR", "GBP")
#: Referans kodunun cihazda (rıza varsa) saklandığı gün — ön yüzde de aynı sabit.
CEREZ_GUN = 30
#: Ayarda koşul metni yoksa sayfadaki varsayılan metnin (i18n ek paketi) sürümü.
VARSAYILAN_KOSUL_SURUMU = "varsayilan-1"
VARSAYILAN_AYAR: Dict[str, Any] = {
    "acik": True,
    "varsayilan_oran": 10.0,
    #: Tekrar eden (abonelik) faturalarında oran Y ve ilk satıştan sonraki süre N ay (0 = kapalı).
    "tekrar_oran": 5.0,
    "tekrar_ay": 0,
    "bekleme_gun": 30,
    "odeme_en_az": {"TRY": 500.0, "USD": 25.0, "EUR": 25.0, "GBP": 20.0},
    "atif": "ilk",
    "tum_faturalar": False,
    "kosullar": {},
}
DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
SINIR = {"ad": 120, "web": 300, "tanitim": 2000, "not": 500, "kosul": 20000}
KAYNAKLAR = ("form", "fiyat", "kod", "kayit", "elle")
#: Kayıt sonrası referans: yalnız bu kadar saat içinde açılmış kullanıcı hesabına (eski müşteri sonradan
#: bağlantıya tıklayıp girişte atıf kazandırmasın).
KAYIT_PENCERESI_SAAT = 48
ONBELLEK_SN = 30.0

_EPOSTA = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class OrtaklikHatasi(Exception):
    def __init__(self, durum: int, kod: str, **ek: Any):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod
        self.ek = ek

    def detay(self) -> Dict[str, Any]:
        return {"kod": self.kod, **self.ek}


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Any) -> Optional[str]:
    u = _utc(an) if isinstance(an, datetime) else None
    return u.isoformat().replace("+00:00", "Z") if u else None


def eposta_duzelt(e: Any) -> str:
    return str(e or "").strip().lower()


def eposta_gecerli(e: str) -> bool:
    return bool(_EPOSTA.match(e or ""))


def _metin(ham: Any, sinir: int) -> Optional[str]:
    t = str(ham or "").strip()
    return t[:sinir] or None


def _kurus(d: Decimal) -> Decimal:
    from services.belge_hesap import kurus

    return kurus(d)


def _json_liste(metin: Any) -> List[str]:
    try:
        d = json.loads(metin or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in d] if isinstance(d, list) else []


def _tr_gunu(an: Optional[datetime] = None) -> str:
    from services.site_izleme import tr_gunu

    return tr_gunu(an or simdi()).isoformat()


# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------
def _ayar_duzelt(ham: Any) -> Dict[str, Any]:
    a = json.loads(json.dumps(VARSAYILAN_AYAR))
    if not isinstance(ham, dict):
        return a
    if "acik" in ham:
        a["acik"] = bool(ham["acik"])
    try:
        oran = float(ham.get("varsayilan_oran", a["varsayilan_oran"]))
        if 0 <= oran <= 90:
            a["varsayilan_oran"] = round(oran, 2)
    except (TypeError, ValueError):
        pass
    try:
        gun = int(ham.get("bekleme_gun", a["bekleme_gun"]))
        if 0 <= gun <= 365:
            a["bekleme_gun"] = gun
    except (TypeError, ValueError):
        pass
    try:
        oran = float(ham.get("tekrar_oran", a["tekrar_oran"]))
        if 0 <= oran <= 90:
            a["tekrar_oran"] = round(oran, 2)
    except (TypeError, ValueError):
        pass
    try:
        ay = int(ham.get("tekrar_ay", a["tekrar_ay"]))
        if 0 <= ay <= 36:
            a["tekrar_ay"] = ay
    except (TypeError, ValueError):
        pass
    en_az = ham.get("odeme_en_az")
    if isinstance(en_az, dict):
        for pb in PARA_BIRIMLERI:
            if pb in en_az:
                try:
                    d = float(en_az[pb])
                    if 0 <= d <= 1_000_000:
                        a["odeme_en_az"][pb] = round(d, 2)
                except (TypeError, ValueError):
                    pass
    if ham.get("atif") in ("ilk", "son"):
        a["atif"] = ham["atif"]
    if "tum_faturalar" in ham:
        a["tum_faturalar"] = bool(ham["tum_faturalar"])
    kosullar = ham.get("kosullar")
    if isinstance(kosullar, dict):
        a["kosullar"] = {d: str(kosullar[d])[: SINIR["kosul"]] for d in DILLER if str(kosullar.get(d) or "").strip()}
    return a


def _ayar_satiri_sync(baglanti) -> Optional[str]:
    from models.site_settings import Site_settings

    t = Site_settings.__table__
    return baglanti.execute(select(t.c.setting_value).where(t.c.setting_key == AYAR_ANAHTARI).limit(1)).scalar()


def ayar_sync(baglanti) -> Dict[str, Any]:
    try:
        return _ayar_duzelt(json.loads(_ayar_satiri_sync(baglanti) or "{}"))
    except (TypeError, ValueError):
        return _ayar_duzelt({})


async def ayarlar(db: AsyncSession) -> Dict[str, Any]:
    from models.site_settings import Site_settings

    deger = (
        await db.execute(select(Site_settings.setting_value).where(Site_settings.setting_key == AYAR_ANAHTARI).limit(1))
    ).scalar()
    try:
        return _ayar_duzelt(json.loads(deger or "{}"))
    except (TypeError, ValueError):
        return _ayar_duzelt({})


async def ayarlari_yaz(db: AsyncSession, govde: Dict[str, Any]) -> Dict[str, Any]:
    from models.site_settings import Site_settings

    mevcut = await ayarlar(db)
    birlesik = {**mevcut, **{k: v for k, v in (govde or {}).items() if k in VARSAYILAN_AYAR}}
    if isinstance(govde.get("odeme_en_az"), dict):
        birlesik["odeme_en_az"] = {**mevcut["odeme_en_az"], **govde["odeme_en_az"]}
    yeni = _ayar_duzelt(birlesik)
    satir = (await db.execute(select(Site_settings).where(Site_settings.setting_key == AYAR_ANAHTARI))).scalars().first()
    metin = json.dumps(yeni, ensure_ascii=False)
    if satir is None:
        db.add(Site_settings(setting_key=AYAR_ANAHTARI, setting_value=metin, group_name="ortaklik", label="Ortaklık programı"))
    else:
        satir.setting_value = metin
    await db.commit()
    onbellegi_temizle()
    return yeni


def kosul_metni(ayar: Dict[str, Any], dil: Optional[str]) -> Tuple[Optional[str], str]:
    """(metin ya da None = sayfadaki varsayılan, sürüm). Seçili dil yoksa Türkçe metin."""
    d = (dil or "tr")[:2]
    metin = (ayar.get("kosullar") or {}).get(d) or (ayar.get("kosullar") or {}).get("tr")
    if not metin:
        return None, VARSAYILAN_KOSUL_SURUMU
    return metin, "k-" + hashlib.sha256(metin.encode("utf-8")).hexdigest()[:12]


def program_bilgisi(ayar: Dict[str, Any], dil: Optional[str]) -> Dict[str, Any]:
    metin, surum = kosul_metni(ayar, dil)
    return {
        "acik": ayar["acik"], "varsayilan_oran": ayar["varsayilan_oran"], "bekleme_gun": ayar["bekleme_gun"],
        "tekrar_oran": ayar["tekrar_oran"], "tekrar_ay": ayar["tekrar_ay"],
        "odeme_en_az": ayar["odeme_en_az"], "cerez_gun": CEREZ_GUN, "kosullar": metin, "kosullar_surumu": surum,
    }


# ---------------------------------------------------------------------------
# Önbellek (flush kancası her seferinde tabloya gitmesin)
# ---------------------------------------------------------------------------
_onbellek: Dict[str, Any] = {"bitis": 0.0, "var": None}


def onbellegi_temizle() -> None:
    _onbellek["bitis"] = 0.0
    _onbellek["var"] = None


def _program_var_mi() -> Optional[bool]:
    """Onaylı ortak ya da ortaklı kod var mı (komisyon olabilir mi)? None = bilinmiyor."""
    if _onbellek["var"] is not None and _onbellek["bitis"] >= time.monotonic():
        return _onbellek["var"]
    return None


def _program_yukle_sync(baglanti) -> bool:
    o = Ortaklar.__table__
    var = baglanti.execute(select(o.c.id).where(o.c.durum.in_(("onaylandi", "askida"))).limit(1)).scalar() is not None
    if not var:
        # Daha önce komisyonu olan (ters kayıt gerekebilir) ortak.
        k = OrtakKomisyonlari.__table__
        var = baglanti.execute(select(k.c.id).limit(1)).scalar() is not None
    _onbellek["var"] = var
    _onbellek["bitis"] = time.monotonic() + ONBELLEK_SN
    return var


# ---------------------------------------------------------------------------
# Kendi kendine referans
# ---------------------------------------------------------------------------
def kendi_mi_sync(baglanti, ortak_eposta: str, musteri: str) -> bool:
    from models.hesap_uyeleri import HesapUyeleri

    o, m = eposta_duzelt(ortak_eposta), eposta_duzelt(musteri)
    if not o or not m:
        return False
    if o == m:
        return True
    u = HesapUyeleri.__table__
    satir = baglanti.execute(
        select(u.c.id).where(
            u.c.durum == "aktif",
            or_(and_(func.lower(u.c.hesap_email) == m, func.lower(u.c.uye_email) == o),
                and_(func.lower(u.c.hesap_email) == o, func.lower(u.c.uye_email) == m)),
        ).limit(1)
    ).scalar()
    return satir is not None


async def kendi_mi(db: AsyncSession, ortak: Ortaklar, musteri: str) -> bool:
    eposta = ortak.eposta
    return await db.run_sync(lambda s: kendi_mi_sync(s.connection(), eposta, musteri))


def _supheli_ekle(mevcut: Optional[str], neden: str) -> str:
    liste = _json_liste(mevcut)
    if neden not in liste:
        liste.append(neden)
    return json.dumps(liste[-10:])


def _ayni_kurumsal_alan(a: str, b: str) -> bool:
    from services.crm import alan_adi_turu

    a, b = eposta_duzelt(a), eposta_duzelt(b)
    if "@" not in a or "@" not in b:
        return False
    return a.rsplit("@", 1)[1] == b.rsplit("@", 1)[1] and alan_adi_turu(a) == "kurumsal"


# ---------------------------------------------------------------------------
# Ortak (başvuru ve yönetim)
# ---------------------------------------------------------------------------
async def ortak_getir(db: AsyncSession, ortak_id: int) -> Ortaklar:
    o = (await db.execute(select(Ortaklar).where(Ortaklar.id == ortak_id, Ortaklar.hesap == AJANS))).scalars().first()
    if o is None:
        raise OrtaklikHatasi(404, "ortak_yok")
    return o


async def ortak_bul(db: AsyncSession, eposta: str) -> Optional[Ortaklar]:
    e = eposta_duzelt(eposta)
    if not e:
        return None
    return (await db.execute(select(Ortaklar).where(Ortaklar.hesap == AJANS, Ortaklar.eposta == e))).scalars().first()


def _web_duzelt(ham: Any) -> Optional[str]:
    w = _metin(ham, SINIR["web"])
    if not w:
        return None
    if any(c.isspace() for c in w):
        raise OrtaklikHatasi(400, "web_gecersiz")
    if w.startswith("@"):
        return w  # sosyal medya kullanıcı adı
    if not re.match(r"^https?://", w, re.I):
        w = "https://" + w
    if not re.match(r"^https?://[^/\s.]+\.[^/\s]+", w, re.I):
        raise OrtaklikHatasi(400, "web_gecersiz")
    return w


async def basvuru_yap(db: AsyncSession, g: Dict[str, Any]) -> Tuple[Optional[Ortaklar], str]:
    """Başvuru: (kayıt, sonuç) — sonuç yeni | guncellendi | zaten_ortak. Commit EDER."""
    from services import pazarlama_izni as pi

    ayar = await ayarlar(db)
    if not ayar["acik"]:
        raise OrtaklikHatasi(409, "program_kapali")
    ad = _metin(g.get("ad"), SINIR["ad"])
    if not ad:
        raise OrtaklikHatasi(400, "ad_gerekli")
    eposta = eposta_duzelt(g.get("eposta"))
    if not eposta_gecerli(eposta):
        raise OrtaklikHatasi(400, "eposta_gecersiz")
    web = _web_duzelt(g.get("web"))
    tanitim = _metin(g.get("tanitim"), SINIR["tanitim"])
    if not tanitim:
        raise OrtaklikHatasi(400, "tanitim_gerekli")
    if g.get("kosullar_kabul") is not True:
        raise OrtaklikHatasi(400, "kosullar_gerekli")
    dil = pi.dil_sec(g.get("dil"))
    _, surum = kosul_metni(ayar, dil)
    an = simdi()
    o = await ortak_bul(db, eposta)
    if o is not None and o.durum in ("onaylandi", "askida"):
        return o, "zaten_ortak"
    yeni = o is None
    if yeni:
        o = Ortaklar(hesap=AJANS, eposta=eposta, ad=ad, durum="beklemede", basvuru_at=an)
        db.add(o)
    o.ad, o.web, o.tanitim, o.dil = ad, web, tanitim, dil
    o.durum = "beklemede"
    o.basvuru_at = an
    o.ret_nedeni = None
    o.kosullar_kabul_at, o.kosullar_surumu = an, surum
    if pi.izin_verildi_mi(g.get("pazarlama_izni")):
        o.pazarlama_izni_at, o.pazarlama_metin_surumu = an, pi.surum_etiketi(dil)
    await db.flush()
    from services.webhook import olay_yayinla

    await olay_yayinla(db, "ortaklik.basvuru", None, {"ortak_id": o.id, "durum": o.durum, "dil": dil}, musteri_gorur=False)
    await db.commit()
    await db.refresh(o)
    return o, "yeni" if yeni else "guncellendi"


async def basvuru_bildir(db: AsyncSession, o: Ortaklar) -> None:
    from services.notify import admin_recipients, dispatch

    await dispatch(
        db, event_type="ortaklik_basvuru", title=f"Yeni ortaklık başvurusu: {o.ad}",
        body=f"Ad: {o.ad}\nE-posta: {o.eposta}\nWeb/sosyal: {o.web or '—'}\n\nNasıl tanıtacak:\n{o.tanitim or '—'}",
        recipients=await admin_recipients(db),
        link=f"/admin?sekme=gelenKutusu&kaynak=ortak_basvurusu&oge=ortak_basvurusu:{o.id}",
        ref_type="ortaklik", ref_id=o.id,
    )


def _addan_kod(ad: str) -> str:
    sade = unicodedata.normalize("NFKD", ad or "")
    harfler = "".join(c for c in sade if c.isascii() and c.isalnum()).upper()[:8] or "ORTAK"
    return harfler


async def _kod_uret(db: AsyncSession, o: Ortaklar) -> Tuple[str, str]:
    from services import indirim_kodlari as ik

    kok = _addan_kod(o.ad)
    for _ in range(20):
        aday = f"{kok}{secrets.randbelow(9000) + 1000}"
        anahtar = ik.kod_anahtari(aday)
        if await ik.ad_alani_bos_mu(db, anahtar, haric_ortak=o.id):
            return ik.kod_gorunen(aday), anahtar
    raise OrtaklikHatasi(500, "kod_uretilemedi")


async def _kod_ata(db: AsyncSession, o: Ortaklar, ham: Any) -> None:
    from services import indirim_kodlari as ik

    if ham in (None, ""):
        if not o.kod_anahtar:
            o.kod, o.kod_anahtar = await _kod_uret(db, o)
        return
    if not ik.bicim_gecerli(ham):
        raise OrtaklikHatasi(400, "kod_gecersiz")
    anahtar = ik.kod_anahtari(ham)
    if anahtar == o.kod_anahtar:
        return
    if not await ik.ad_alani_bos_mu(db, anahtar, haric_ortak=o.id):
        raise OrtaklikHatasi(409, "kod_kullaniliyor")
    o.kod, o.kod_anahtar = ik.kod_gorunen(ham), anahtar


def _oran_duzelt(ham: Any) -> Optional[float]:
    if ham in (None, ""):
        return None
    try:
        oran = float(ham)
    except (TypeError, ValueError):
        raise OrtaklikHatasi(400, "oran_gecersiz")
    if not 0 <= oran <= 90:
        raise OrtaklikHatasi(400, "oran_gecersiz")
    return round(oran, 2)


async def karar_ver(db: AsyncSession, o: Ortaklar, karar: str, yapan: str, *, oran: Any = None, kod: Any = None,
                    neden: Any = None) -> Ortaklar:
    if karar not in ("onay", "ret"):
        raise OrtaklikHatasi(400, "karar_gecersiz")
    if o.durum not in ("beklemede", "reddedildi") and karar == "onay":
        raise OrtaklikHatasi(409, f"durum_{o.durum}")
    if o.durum != "beklemede" and karar == "ret":
        raise OrtaklikHatasi(409, f"durum_{o.durum}")
    an = simdi()
    if karar == "onay":
        o.oran = _oran_duzelt(oran)
        await _kod_ata(db, o, kod)
        o.durum = "onaylandi"
        o.ret_nedeni = None
    else:
        o.durum = "reddedildi"
        o.ret_nedeni = _metin(neden, SINIR["not"])
    o.karar_at, o.karar_veren = an, eposta_duzelt(yapan) or None
    await db.commit()
    await db.refresh(o)
    onbellegi_temizle()
    await _karar_bildir(db, o)
    return o


async def _karar_bildir(db: AsyncSession, o: Ortaklar) -> None:
    from services.belge_ortak import site_adresi
    from services.notify import dispatch

    adres = site_adresi()
    if o.durum == "onaylandi":
        baslik = "Ortaklık başvurunuz onaylandı / Your partner application was approved"
        govde = (
            f"Merhaba {o.ad},\n\nOrtaklık başvurunuz onaylandı. Referans kodunuz: {o.kod}\n"
            f"Bağlantınız: {adres}/?ref={o.kod}\n\n"
            f"Panelinize {o.eposta} adresiyle giriş yapın (hesabınız yoksa aynı adresle kayıt olun): {adres}/client?sekme=ortaklik\n\n"
            f"Your partner application was approved. Your referral code: {o.kod}\n"
            f"Sign in (or sign up) with {o.eposta} to see your partner dashboard.\n\n— By Mehmet KURU Dev"
        )
    else:
        baslik = "Ortaklık başvurunuz hakkında / About your partner application"
        govde = (
            f"Merhaba {o.ad},\n\nOrtaklık başvurunuzu şu an kabul edemiyoruz."
            + (f"\nNot: {o.ret_nedeni}" if o.ret_nedeni else "")
            + "\n\nWe cannot accept your partner application at this time.\n\n— By Mehmet KURU Dev"
        )
    await dispatch(db, event_type="ortaklik_durum", title=baslik, body=govde,
                   recipients=[{"email": o.eposta, "role": "client"}], link="/client?sekme=ortaklik",
                   ref_type="ortaklik", ref_id=o.id)


async def ortak_guncelle(db: AsyncSession, o: Ortaklar, g: Dict[str, Any]) -> Ortaklar:
    """Yönetici: oran, kod, askıya al / yeniden aç, not, şüpheli işaretini temizle."""
    if "oran" in g:
        o.oran = _oran_duzelt(g.get("oran"))
    if "kod" in g and o.durum in ("onaylandi", "askida"):
        await _kod_ata(db, o, g.get("kod"))
    if "durum" in g:
        yeni = g.get("durum")
        if yeni not in ("onaylandi", "askida") or o.durum not in ("onaylandi", "askida"):
            raise OrtaklikHatasi(409, "durum_gecersiz")
        o.durum = yeni
    if "notlar" in g:
        o.notlar = _metin(g.get("notlar"), 2000)
    if g.get("supheli_temizle"):
        o.supheli = None
    await db.commit()
    await db.refresh(o)
    onbellegi_temizle()
    return o


# ---------------------------------------------------------------------------
# IBAN (yalnız biçim; kart numarası değil)
# ---------------------------------------------------------------------------
IBAN_DESENI = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def iban_duzelt(ham: Any) -> str:
    """Boşluk/tire atılır, büyük harf; biçim + ülke uzunluğu (TR 26) + mod-97. Kart numarası reddedilir."""
    s = re.sub(r"[\s-]", "", str(ham or "")).upper()
    if not s:
        raise OrtaklikHatasi(400, "iban_gerekli")
    if s.isdigit() and 12 <= len(s) <= 19:
        raise OrtaklikHatasi(400, "kart_numarasi_degil")
    if not IBAN_DESENI.match(s) or (s.startswith("TR") and len(s) != 26):
        raise OrtaklikHatasi(400, "iban_gecersiz")
    dizi = s[4:] + s[:4]
    sayi = "".join(str(int(c, 36)) for c in dizi)
    if int(sayi) % 97 != 1:
        raise OrtaklikHatasi(400, "iban_gecersiz")
    return s


def iban_maskele(iban: Optional[str]) -> Optional[str]:
    if not iban:
        return None
    return f"{iban[:4]} •••• {iban[-4:]}"


async def iban_kaydet(db: AsyncSession, o: Ortaklar, iban: Any, ad: Any) -> Ortaklar:
    o.iban = iban_duzelt(iban)
    o.iban_ad = _metin(ad, 120)
    if not o.iban_ad:
        raise OrtaklikHatasi(400, "iban_ad_gerekli")
    await db.commit()
    await db.refresh(o)
    return o


# ---------------------------------------------------------------------------
# Tıklama (günlük toplam, kişi verisi yok)
# ---------------------------------------------------------------------------
async def tiklama_say(db: AsyncSession, ham_kod: Any) -> bool:
    from services import indirim_kodlari as ik

    if not ik.bicim_gecerli(ham_kod):
        return False
    o = await ik.ortak_kodu_bul(db, ham_kod)
    if o is None:
        return False
    gun = _tr_gunu()
    T = OrtakTiklamalari
    sonuc = await db.execute(update(T).where(T.ortak_id == o.id, T.gun == gun).values(sayi=T.sayi + 1))
    if not sonuc.rowcount:
        try:
            async with db.begin_nested():
                db.add(T(ortak_id=o.id, gun=gun, sayi=1))
                await db.flush()
        except IntegrityError:
            await db.execute(update(T).where(T.ortak_id == o.id, T.gun == gun).values(sayi=T.sayi + 1))
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Atıf (müşteri → ortak)
# ---------------------------------------------------------------------------
async def atif_yaz(db: AsyncSession, *, musteri_eposta: str, ortak: Optional[Ortaklar], kaynak: str,
                   aday_id: Optional[int] = None) -> str:
    """Sonuç: yeni | guncellendi | korundu | kendi | yok. Commit ETMEZ."""
    m = eposta_duzelt(musteri_eposta)
    if ortak is None or ortak.durum != "onaylandi" or not eposta_gecerli(m):
        return "yok"
    if await kendi_mi(db, ortak, m):
        ortak.supheli = _supheli_ekle(ortak.supheli, "kendi_referansi")
        await db.flush()
        return "kendi"
    R = OrtakReferanslari
    an = simdi()
    h = ortak.hesap or AJANS
    mevcut = (await db.execute(select(R).where(R.hesap == h, R.musteri_eposta == m))).scalars().first()
    if mevcut is None:
        try:
            async with db.begin_nested():
                db.add(R(hesap=h, musteri_eposta=m, ortak_id=ortak.id, kaynak=kaynak if kaynak in KAYNAKLAR else "form",
                         aday_id=aday_id, ilk_at=an, son_at=an))
                await db.flush()
            return "yeni"
        except IntegrityError:
            mevcut = (await db.execute(select(R).where(R.hesap == h, R.musteri_eposta == m))).scalars().first()
            if mevcut is None:
                return "yok"
    if mevcut.ortak_id == ortak.id:
        mevcut.son_at = an
        if aday_id and not mevcut.aday_id:
            mevcut.aday_id = aday_id
        await db.flush()
        return "guncellendi"
    ayar = await ayarlar(db)
    if ayar["atif"] == "son":
        mevcut.ortak_id, mevcut.kaynak, mevcut.son_at = ortak.id, kaynak if kaynak in KAYNAKLAR else "form", an
        mevcut.aday_id = aday_id or mevcut.aday_id
        await db.flush()
        return "guncellendi"
    return "korundu"


async def formdan_isle(db: AsyncSession, *, tablo: str, kayit_id: Optional[int], eposta: Optional[str],
                       ham_kod: Any) -> Dict[str, Any]:
    """İletişim / teklif al formunda girilen kod: CRM adayına yaz + atıf aç. Commit EDER. Hata yutulur."""
    from services import indirim_kodlari as ik
    from services.pazarlama_izni import bagli_adayi_bul

    sonuc: Dict[str, Any] = {"indirim_kodu": None, "referans_kodu": None}
    try:
        if not ham_kod:
            return sonuc
        cozum = await ik.formdan_coz(db, ham_kod)
        sonuc = {"indirim_kodu": cozum["indirim_kodu"], "referans_kodu": cozum["referans_kodu"]}
        if not (cozum["indirim_kodu"] or cozum["referans_kodu"]):
            return sonuc
        aday_id = await bagli_adayi_bul(db, tablo, kayit_id)
        if aday_id:
            from models.crm import CrmAdaylari

            degerler: Dict[str, Any] = {}
            if cozum["indirim_kodu"]:
                degerler["indirim_kodu"] = cozum["indirim_kodu"]
            if cozum["referans_kodu"]:
                degerler["referans_kodu"] = cozum["referans_kodu"]
            await db.execute(update(CrmAdaylari).where(CrmAdaylari.id == int(aday_id)).values(**degerler))
        if cozum["ortak"] is not None and eposta:
            sonuc["atif"] = await atif_yaz(db, musteri_eposta=eposta, ortak=cozum["ortak"],
                                           kaynak="fiyat" if tablo == "pricing_inquiries" else "form", aday_id=aday_id)
        await db.commit()
    except Exception:  # noqa: BLE001 - form kaydı kod yüzünden bozulmasın
        logger.exception("Ortaklık: formdaki kod işlenemedi (%s %s)", tablo, kayit_id)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return sonuc


async def kayit_referansi(db: AsyncSession, kisi_eposta: str, ham_kod: Any) -> str:
    """Kayıt: bağlantıdan (`?ref=`) gelip YENİ hesap açan kişiye atıf. Commit EDER.

    Sonuç: yeni | guncellendi | korundu | kendi | eski_hesap | yok. Yalnız `KAYIT_PENCERESI_SAAT` içinde açılmış
    kullanıcı hesabında (eski müşteri sonradan bağlantıya tıklayıp girişte bir ortağa atıf kazandırmasın).
    """
    from models.auth import User
    from services import indirim_kodlari as ik

    e = eposta_duzelt(kisi_eposta)
    if not e or not ham_kod or not ik.bicim_gecerli(ham_kod):
        return "yok"
    cozum = await ik.formdan_coz(db, ham_kod)
    if cozum["ortak"] is None:
        return "yok"
    acilis = (
        await db.execute(select(User.created_at).where(func.lower(User.email) == e).order_by(User.created_at).limit(1))
    ).scalar()
    if acilis is None or simdi() - (_utc(acilis) or simdi()) > timedelta(hours=KAYIT_PENCERESI_SAAT):
        return "eski_hesap"
    sonuc = await atif_yaz(db, musteri_eposta=e, ortak=cozum["ortak"], kaynak="kayit")
    await db.commit()
    return sonuc


# ---------------------------------------------------------------------------
# Komisyon defteri — olay abonesi (eşzamanlı Connection, çağıranın işleminde)
# ---------------------------------------------------------------------------
IZLENEN_OLAYLAR = frozenset({"fatura.odendi", "fatura.iade_edildi", "fatura.odeme_geri_alindi"})


def _ilgileniyor_mu(tur: Optional[str]) -> bool:
    if tur is not None and tur not in IZLENEN_OLAYLAR:
        return False
    var = _program_var_mi()
    return True if var is None else var


def _yaz(baglanti, olaylar, baglam) -> int:
    var = _program_var_mi()
    if var is None:
        var = _program_yukle_sync(baglanti)
    if not var:
        return 0
    sayi = 0
    for tur, _hesap, veri, _gorur in olaylar:
        if tur not in IZLENEN_OLAYLAR:
            continue
        fid = veri.get("fatura_id")
        if not fid:
            continue
        try:
            with baglanti.begin_nested():
                if tur == "fatura.odendi":
                    sayi += _komisyon_olustur_sync(baglanti, int(fid))
                elif tur == "fatura.iade_edildi":
                    sayi += _ters_kayit_sync(baglanti, int(fid), iade_id=int(veri.get("iade_fatura_id") or 0) or None)
                else:
                    sayi += _ters_kayit_sync(baglanti, int(fid), iade_id=None)
        except Exception:  # noqa: BLE001 - defter yazılamasa da ödeme kaydı bozulmasın
            logger.exception("Ortaklık: komisyon defteri yazılamadı (%s fatura=%s)", tur, fid)
    return sayi


def _abone_kaydet() -> None:
    from services import webhook

    webhook.abone_ekle(webhook.OlayAbonesi(
        ad="ortaklik",
        ilgileniyor_mu=_ilgileniyor_mu,
        yaz=_yaz,
        tablolar=frozenset({"invoices"}),
    ))


def _kod_ortagi_sync(c, ham_kod: Optional[str]) -> Optional[int]:
    if not ham_kod:
        return None
    from services.indirim_kodlari import kod_anahtari

    k = IndirimKodlari.__table__
    return c.execute(select(k.c.ortak_id).where(k.c.hesap == AJANS, k.c.kod_anahtar == kod_anahtari(ham_kod))).scalar()


def _ay_ekle(an: datetime, ay: int) -> datetime:
    """Takvim ayı ekler (ayın günü yoksa ayın son günü: 31 Ocak + 1 ay = 28/29 Şubat)."""
    import calendar

    toplam = an.month - 1 + int(ay)
    yil, ay_ = an.year + toplam // 12, toplam % 12 + 1
    return an.replace(year=yil, month=ay_, day=min(an.day, calendar.monthrange(yil, ay_)[1]))


def _ilk_satis_sync(c, ortak_id: int, musteri: str):
    """Ortak × müşteri için ilk satış komisyonu (iptal ya da tamamı ters kayıtla geri alınmış olanlar sayılmaz)."""
    K = OrtakKomisyonlari.__table__
    adaylar = c.execute(
        select(K.c.id, K.c.fatura_id, K.c.teklif_id, K.c.tutar, K.c.created_at).where(
            K.c.ortak_id == ortak_id, K.c.musteri_eposta == musteri, K.c.tur == "komisyon", K.c.kural == "ilk",
            K.c.durum != "iptal",
        ).order_by(K.c.id)
    ).mappings().all()
    for a in adaylar:
        ters = c.execute(select(func.coalesce(func.sum(K.c.tutar), 0)).where(K.c.bagli_id == a["id"], K.c.tur == "ters")).scalar()
        if Decimal(str(a["tutar"])) + Decimal(str(ters or 0)) > 0:
            return a
    return None


def _site_satisi_mi_sync(c, fatura_id: int) -> bool:
    """Fatura sitedeki "Teklif al" / "Satın al" akışından (fiyat talebi) mı doğdu?"""
    from models.pricing import Pricing_inquiries

    P = Pricing_inquiries.__table__
    return c.execute(select(P.c.id).where(P.c.invoice_id == fatura_id).limit(1)).scalar() is not None


def _komisyon_olustur_sync(c, fatura_id: int) -> int:
    from models.invoices import Invoices
    from models.teklifler import Teklifler

    I = Invoices.__table__
    f = c.execute(select(I).where(I.c.id == fatura_id)).mappings().first()
    if f is None or (f["tur"] or "") == "iade":
        return 0
    musteri = eposta_duzelt(f["client_email"])
    if not musteri:
        return 0
    K = OrtakKomisyonlari.__table__
    # Tekil: ödeme döngüsü başına bir komisyon. Ödeme geri alındıysa (tam ters kayıt) yeniden ödenince yenisi.
    k_sayisi = int(c.execute(select(func.count(K.c.id)).where(K.c.fatura_id == fatura_id, K.c.tur == "komisyon")).scalar() or 0)
    t_sayisi = int(c.execute(select(func.count(K.c.id)).where(
        K.c.fatura_id == fatura_id, K.c.tur == "ters", K.c.tekil.like(f"t:{fatura_id}:durum:%"))).scalar() or 0)
    if k_sayisi > t_sayisi:
        return 0
    tekil = f"k:{fatura_id}" if k_sayisi == 0 else f"k:{fatura_id}:{k_sayisi}"

    T = Teklifler.__table__
    teklif = None
    if f["teklif_id"]:
        teklif = c.execute(select(T.c.id, T.c.durum, T.c.indirim_kodu).where(T.c.id == f["teklif_id"])).mappings().first()
    if teklif is None:
        teklif = c.execute(select(T.c.id, T.c.durum, T.c.indirim_kodu).where(T.c.fatura_id == fatura_id, T.c.durum == "kabul")
                           .order_by(T.c.id.desc()).limit(1)).mappings().first()
    teklifli = teklif is not None and teklif["durum"] == "kabul"
    teklif_id = int(teklif["id"]) if teklifli else None
    ortak_id = _kod_ortagi_sync(c, f["indirim_kodu"]) or (_kod_ortagi_sync(c, teklif["indirim_kodu"]) if teklif else None)
    kodlu = ortak_id is not None
    if ortak_id is None:
        R = OrtakReferanslari.__table__
        ortak_id = c.execute(select(R.c.ortak_id).where(R.c.hesap == AJANS, R.c.musteri_eposta == musteri)).scalar()
    if ortak_id is None:
        return 0
    ayar = ayar_sync(c)
    O = Ortaklar.__table__
    o = c.execute(select(O).where(O.c.id == ortak_id)).mappings().first()
    if o is None or o["durum"] != "onaylandi":
        return 0
    an = simdi()
    # Kural: ilk satış (X) mı, ilk satıştan sonra N ay içindeki tekrarlayan fatura (Y) mı, hiçbiri mi?
    ilk = _ilk_satis_sync(c, o["id"], musteri)
    if ilk is None or ilk["fatura_id"] == fatura_id or (teklif_id and ilk["teklif_id"] == teklif_id):
        if ilk is None and not (teklifli or kodlu or _site_satisi_mi_sync(c, fatura_id) or ayar["tum_faturalar"]):
            return 0
        kural = "ilk"
        oran = Decimal(str(o["oran"] if o["oran"] is not None else ayar["varsayilan_oran"]))
    else:
        ay, y = int(ayar["tekrar_ay"]), Decimal(str(ayar["tekrar_oran"]))
        if not (f["tekrarlayan_id"] and ay > 0 and y > 0 and an <= _ay_ekle(_utc(ilk["created_at"]) or an, ay)):
            return 0
        kural, oran = "tekrar", y
    if kendi_mi_sync(c, o["eposta"], musteri):
        c.execute(update(O).where(O.c.id == o["id"]).values(supheli=_supheli_ekle(o["supheli"], "kendi_referansi")))
        return 0
    matrah = Decimal(str(f["ara_toplam"])) if f["kalemler"] and f["ara_toplam"] is not None else Decimal(str(f["amount"] or 0))
    tutar = _kurus(matrah * oran / Decimal("100"))
    if tutar <= 0:
        return 0
    supheli: List[str] = []
    if _ayni_kurumsal_alan(o["eposta"], musteri):
        supheli.append("ayni_alan_adi")
    bekleme = int(ayar["bekleme_gun"])
    durum = "beklemede" if bekleme > 0 else "onaylandi"
    sonuc = c.execute(K.insert().values(
        hesap=o["hesap"] or AJANS, ortak_id=o["id"], tur="komisyon", kural=kural, teklif_id=teklif_id, tekil=tekil,
        fatura_id=fatura_id,
        fatura_no=f["invoice_no"],
        musteri_eposta=musteri, matrah=float(_kurus(matrah)), oran=float(oran), tutar=float(tutar),
        para_birimi=(f["currency"] or "TRY").upper()[:3], durum=durum,
        bekleme_bitis=an + timedelta(days=bekleme), supheli=json.dumps(supheli) if supheli else None,
        created_at=an, updated_at=an,
    ))
    kid = int(sonuc.inserted_primary_key[0])
    _olay_sync(c, "ortaklik.komisyon", {
        "komisyon_id": kid, "ortak_id": o["id"], "fatura_id": fatura_id, "tur": "komisyon", "kural": kural,
        "tutar": float(tutar),
        "para_birimi": (f["currency"] or "TRY").upper()[:3], "durum": durum,
    })
    return 1


def _ters_kayit_sync(c, fatura_id: int, *, iade_id: Optional[int]) -> int:
    """İade faturası (oranlı) ya da ödemenin geri alınması (kalanın tamamı) → ters kayıt."""
    from models.invoices import Invoices

    K = OrtakKomisyonlari.__table__
    asil = c.execute(select(K).where(K.c.fatura_id == fatura_id, K.c.tur == "komisyon").order_by(K.c.id.desc()).limit(1)).mappings().first()
    if asil is None or asil["durum"] == "iptal":
        return 0
    if iade_id:
        tekil = f"t:{fatura_id}:iade:{iade_id}"
    else:
        n = int(c.execute(select(func.count(K.c.id)).where(K.c.tekil.like(f"t:{fatura_id}:durum:%"))).scalar() or 0)
        tekil = f"t:{fatura_id}:durum:{n}"
    if c.execute(select(K.c.id).where(K.c.tekil == tekil)).scalar() is not None:
        return 0
    onceki = Decimal(str(c.execute(select(func.coalesce(func.sum(K.c.tutar), 0)).where(
        K.c.bagli_id == asil["id"], K.c.tur == "ters")).scalar() or 0))
    asil_tutar = Decimal(str(asil["tutar"]))
    kalan = asil_tutar + onceki
    if kalan <= 0:
        return 0
    if iade_id:
        I = Invoices.__table__
        f = c.execute(select(I.c.amount).where(I.c.id == fatura_id)).scalar()
        iade = c.execute(select(I.c.amount).where(I.c.id == iade_id)).scalar()
        if not f or not iade:
            return 0
        oran = min(abs(Decimal(str(iade))) / Decimal(str(f)), Decimal("1"))
        miktar = min(_kurus(asil_tutar * oran), kalan)
    else:
        miktar = kalan
    if miktar <= 0:
        return 0
    an = simdi()
    beklemede = asil["durum"] == "beklemede"
    supheli = ["odendikten_sonra_iade"] if asil["durum"] in ("odeme_talebinde", "odendi") else []
    sonuc = c.execute(K.insert().values(
        hesap=asil["hesap"] or AJANS, ortak_id=asil["ortak_id"], tur="ters", kural=asil["kural"] or "ilk",
        teklif_id=asil["teklif_id"], tekil=tekil,
        fatura_id=fatura_id, fatura_no=asil["fatura_no"],
        bagli_id=asil["id"], musteri_eposta=asil["musteri_eposta"], matrah=0, oran=asil["oran"], tutar=float(-miktar),
        para_birimi=asil["para_birimi"], durum="beklemede" if beklemede else "onaylandi",
        bekleme_bitis=asil["bekleme_bitis"] if beklemede else an, supheli=json.dumps(supheli) if supheli else None,
        notu=("iade" if iade_id else "odeme_geri_alindi"), created_at=an, updated_at=an,
    ))
    kid = int(sonuc.inserted_primary_key[0])
    _olay_sync(c, "ortaklik.komisyon", {
        "komisyon_id": kid, "ortak_id": asil["ortak_id"], "fatura_id": fatura_id, "tur": "ters", "tutar": float(-miktar),
        "para_birimi": asil["para_birimi"], "durum": "beklemede" if beklemede else "onaylandi",
    })
    return 1


def _olay_sync(c, tur: str, veri: Dict[str, Any]) -> None:
    try:
        from services.webhook import olaylari_yayinla_sync

        olaylari_yayinla_sync(c, [(tur, None, veri, False)])
    except Exception:  # noqa: BLE001
        logger.exception("Ortaklık olayı yayınlanamadı (%s)", tur)


_abone_kaydet()


# ---------------------------------------------------------------------------
# Olgunlaşma (zamanlı iş + panel açılışı)
# ---------------------------------------------------------------------------
async def olgunlasanlari_onayla(db: AsyncSession, an: Optional[datetime] = None) -> Dict[str, Any]:
    """İade süresi dolan beklemedeki kayıtlar onaylanır; net tutarı artı olan her ortağa TEK özet bildirimi."""
    an = an or simdi()
    K = OrtakKomisyonlari
    kosul = (K.durum == "beklemede", K.bekleme_bitis.isnot(None), K.bekleme_bitis <= an)
    satirlar = (await db.execute(select(K.id, K.ortak_id, K.para_birimi, K.tutar).where(*kosul))).all()
    if not satirlar:
        return {"onaylanan": 0}
    idler = [int(r[0]) for r in satirlar]
    sonuc = await db.execute(
        update(K).where(K.id.in_(idler), K.durum == "beklemede")
        .values(durum="onaylandi", updated_at=an).execution_options(synchronize_session=False)
    )
    await db.commit()
    ozet: Dict[int, Dict[str, Decimal]] = {}
    for _, oid, pb, tutar in satirlar:
        d = ozet.setdefault(int(oid), {})
        d[pb or "TRY"] = d.get(pb or "TRY", Decimal("0")) + Decimal(str(tutar or 0))
    for oid, tutarlar in ozet.items():
        await komisyon_onay_bildir(db, oid, {pb: t for pb, t in tutarlar.items() if t > 0})
    return {"onaylanan": int(sonuc.rowcount or 0)}


async def komisyon_onay_bildir(db: AsyncSession, ortak_id: int, tutarlar: Dict[str, Decimal]) -> None:
    """Ortağa "komisyonunuz onaylandı" (para birimi başına tutar). Hata yutulur."""
    if not tutarlar:
        return
    try:
        from services.notify import dispatch

        o = (await db.execute(select(Ortaklar).where(Ortaklar.id == ortak_id))).scalars().first()
        if o is None:
            return
        metin = ", ".join(f"{_kurus(t)} {pb}" for pb, t in sorted(tutarlar.items()))
        await dispatch(
            db, event_type="ortaklik_durum", title=f"Komisyonunuz onaylandı / Your commission was approved: {metin}",
            body=(f"Merhaba {o.ad},\n\nİade süresi dolan komisyonunuz onaylandı: {metin}. Onaylı bakiyeniz en az ödeme "
                  f"tutarına ulaştığında panelinizden ödeme isteyebilirsiniz.\n\nYour commission was approved: {metin}. "
                  f"You can request a payout from your dashboard once your approved balance reaches the minimum.\n\n"
                  f"— By Mehmet KURU Dev"),
            recipients=[{"email": o.eposta, "role": "client"}], link="/client?sekme=ortaklik",
            ref_type="ortaklik", ref_id=o.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Ortaklık komisyon onay bildirimi gönderilemedi")


# ---------------------------------------------------------------------------
# Bakiye, ortak paneli
# ---------------------------------------------------------------------------
async def bakiyeler(db: AsyncSession, ortak_id: int) -> Dict[str, Dict[str, float]]:
    """Para birimi → {kazanc, beklemede, onaylandi (bakiye), odeme_talebinde, odendi}."""
    K = OrtakKomisyonlari
    satirlar = (
        await db.execute(
            select(K.para_birimi, K.durum, func.sum(K.tutar)).where(K.ortak_id == ortak_id, K.durum != "iptal")
            .group_by(K.para_birimi, K.durum)
        )
    ).all()
    sonuc: Dict[str, Dict[str, float]] = {}
    for pb, durum, toplam in satirlar:
        d = sonuc.setdefault(pb or "TRY", {"kazanc": 0.0, "beklemede": 0.0, "onaylandi": 0.0, "odeme_talebinde": 0.0, "odendi": 0.0})
        d[durum] = round(d.get(durum, 0.0) + float(toplam or 0), 2)
        d["kazanc"] = round(d["kazanc"] + float(toplam or 0), 2)
    return sonuc


def komisyon_sozlugu(k: OrtakKomisyonlari, *, yonetici: bool, ortak_ad: Optional[str] = None) -> Dict[str, Any]:
    from services.imzali_islem import eposta_maskele

    d = {
        "id": k.id, "tur": k.tur, "kural": k.kural or "ilk", "fatura_no": k.fatura_no, "matrah": k.matrah, "oran": k.oran,
        "tutar": k.tutar,
        "para_birimi": k.para_birimi, "durum": k.durum, "bekleme_bitis": iso(k.bekleme_bitis),
        "odeme_talebi_id": k.odeme_talebi_id, "notu": k.notu, "created_at": iso(k.created_at),
        "musteri": eposta_maskele(k.musteri_eposta) if k.musteri_eposta else None,
    }
    if yonetici:
        d.update({"ortak_id": k.ortak_id, "ortak_ad": ortak_ad, "fatura_id": k.fatura_id, "bagli_id": k.bagli_id,
                  "musteri_eposta": k.musteri_eposta, "supheli": _json_liste(k.supheli)})
    return d


def talep_sozlugu(t: OrtakOdemeTalepleri, *, yonetici: bool, ortak: Optional[Ortaklar] = None) -> Dict[str, Any]:
    d = {
        "id": t.id, "tutar": t.tutar, "para_birimi": t.para_birimi, "durum": t.durum, "iban": iban_maskele(t.iban),
        "notu": t.notu, "ret_nedeni": t.ret_nedeni, "dekont_var": bool(t.dekont_dosya_id), "odendi_at": iso(t.odendi_at),
        "created_at": iso(t.created_at),
    }
    if yonetici:
        d.update({"ortak_id": t.ortak_id, "iban": t.iban, "iban_ad": t.iban_ad, "odeyen": t.odeyen,
                  "ortak_ad": ortak.ad if ortak else None, "ortak_eposta": ortak.eposta if ortak else None})
    return d


def ortak_sozlugu(o: Ortaklar, *, yonetici: bool, ayar: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from services.belge_ortak import site_adresi

    d: Dict[str, Any] = {
        "id": o.id, "ad": o.ad, "eposta": o.eposta, "web": o.web, "kod": o.kod, "durum": o.durum,
        "oran": o.oran if o.oran is not None else (ayar or VARSAYILAN_AYAR)["varsayilan_oran"],
        "oran_ozel": o.oran is not None, "iban": iban_maskele(o.iban), "iban_ad": o.iban_ad,
        "baglanti": f"{site_adresi()}/?ref={o.kod}" if o.kod else None, "basvuru_at": iso(o.basvuru_at),
        "karar_at": iso(o.karar_at),
    }
    if yonetici:
        d.update({"tanitim": o.tanitim, "notlar": o.notlar, "ret_nedeni": o.ret_nedeni, "supheli": _json_liste(o.supheli),
                  "dil": o.dil, "kosullar_kabul_at": iso(o.kosullar_kabul_at), "kosullar_surumu": o.kosullar_surumu,
                  "pazarlama_izni": o.pazarlama_izni_at is not None, "karar_veren": o.karar_veren,
                  "iban_tam": o.iban})
    return d


async def tiklama_ozeti(db: AsyncSession, ortak_id: int, gun: int = 30) -> Dict[str, Any]:
    T = OrtakTiklamalari
    bas = (datetime.fromisoformat(_tr_gunu()) - timedelta(days=gun - 1)).date().isoformat()
    satirlar = (await db.execute(select(T.gun, T.sayi).where(T.ortak_id == ortak_id, T.gun >= bas).order_by(T.gun))).all()
    toplam_tum = int((await db.execute(select(func.coalesce(func.sum(T.sayi), 0)).where(T.ortak_id == ortak_id))).scalar() or 0)
    return {"son_gun": gun, "son_toplam": sum(int(s) for _, s in satirlar), "toplam": toplam_tum,
            "gunler": [{"gun": g, "sayi": int(s)} for g, s in satirlar]}


async def panel(db: AsyncSession, o: Ortaklar) -> Dict[str, Any]:
    await olgunlasanlari_onayla(db)
    ayar = await ayarlar(db)
    K, R = OrtakKomisyonlari, OrtakReferanslari
    adaylar = int((await db.execute(select(func.count(R.id)).where(R.ortak_id == o.id))).scalar() or 0)
    # Satış: komisyon yazılmış farklı fatura sayısı (ödeme geri alınıp yeniden ödenen fatura bir satış).
    satislar = int((await db.execute(select(func.count(func.distinct(K.fatura_id))).where(
        K.ortak_id == o.id, K.tur == "komisyon", K.durum != "iptal"))).scalar() or 0)
    komisyonlar = (await db.execute(select(K).where(K.ortak_id == o.id).order_by(K.id.desc()).limit(100))).scalars().all()
    talepler = (await db.execute(select(OrtakOdemeTalepleri).where(OrtakOdemeTalepleri.ortak_id == o.id)
                                 .order_by(OrtakOdemeTalepleri.id.desc()).limit(50))).scalars().all()
    return {
        "ortak": ortak_sozlugu(o, yonetici=False, ayar=ayar),
        "tiklama": await tiklama_ozeti(db, o.id),
        "aday": adaylar,
        "satis": satislar,
        "bakiyeler": await bakiyeler(db, o.id),
        "komisyonlar": [komisyon_sozlugu(k, yonetici=False) for k in komisyonlar],
        "talepler": [talep_sozlugu(t, yonetici=False) for t in talepler],
        "program": program_bilgisi(ayar, o.dil),
    }


# ---------------------------------------------------------------------------
# Ödeme talebi
# ---------------------------------------------------------------------------
async def odeme_talebi_olustur(db: AsyncSession, o: Ortaklar, para_birimi: Any) -> OrtakOdemeTalepleri:
    if o.durum != "onaylandi":
        raise OrtaklikHatasi(409, f"durum_{o.durum}")
    pb = str(para_birimi or "TRY").upper()
    if pb not in PARA_BIRIMLERI:
        raise OrtaklikHatasi(400, "para_birimi_gecersiz")
    if not o.iban:
        raise OrtaklikHatasi(409, "iban_gerekli")
    await olgunlasanlari_onayla(db)
    T, K = OrtakOdemeTalepleri, OrtakKomisyonlari
    if (await db.execute(select(T.id).where(T.ortak_id == o.id, T.para_birimi == pb, T.durum == "bekliyor"))).scalar():
        raise OrtaklikHatasi(409, "bekleyen_talep_var")
    kayitlar = (await db.execute(select(K).where(K.ortak_id == o.id, K.para_birimi == pb, K.durum == "onaylandi"))).scalars().all()
    toplam = _kurus(sum((Decimal(str(k.tutar)) for k in kayitlar), Decimal("0")))
    en_az = Decimal(str((await ayarlar(db))["odeme_en_az"].get(pb, 0)))
    if toplam <= 0 or toplam < en_az:
        raise OrtaklikHatasi(409, "en_az_tutar", en_az=float(en_az), bakiye=float(toplam), para_birimi=pb)
    t = OrtakOdemeTalepleri(hesap=o.hesap or AJANS, ortak_id=o.id, tutar=float(toplam), para_birimi=pb, iban=o.iban,
                            iban_ad=o.iban_ad, durum="bekliyor")
    db.add(t)
    await db.flush()
    for k in kayitlar:
        k.durum, k.odeme_talebi_id = "odeme_talebinde", t.id
    from services.webhook import olay_yayinla

    await olay_yayinla(db, "ortaklik.odeme_talebi", None, {"talep_id": t.id, "ortak_id": o.id, "tutar": float(toplam),
                                                           "para_birimi": pb, "durum": "bekliyor"}, musteri_gorur=False)
    await db.commit()
    await db.refresh(t)
    try:
        from services.notify import admin_recipients, dispatch

        await dispatch(db, event_type="ortaklik_odeme_talebi", title=f"Ortaklık ödeme talebi: {o.ad} — {toplam} {pb}",
                       body=f"{o.ad} ({o.eposta}) {toplam} {pb} komisyon ödemesi istedi.\nIBAN: {o.iban} ({o.iban_ad or '—'})",
                       recipients=await admin_recipients(db), link="/admin?sekme=ortaklik&alt=talepler",
                       ref_type="ortaklik_talep", ref_id=t.id)
    except Exception:  # noqa: BLE001
        logger.exception("Ortaklık ödeme talebi bildirimi gönderilemedi")
    return t


async def talep_getir(db: AsyncSession, talep_id: int) -> OrtakOdemeTalepleri:
    t = (await db.execute(select(OrtakOdemeTalepleri).where(OrtakOdemeTalepleri.id == talep_id,
                                                             OrtakOdemeTalepleri.hesap == AJANS))).scalars().first()
    if t is None:
        raise OrtaklikHatasi(404, "talep_yok")
    return t


async def dekont_kaydet(db: AsyncSession, o: Ortaklar, dosya: Any, yukleyen: Optional[str]) -> int:
    from services import dosyalar as ds
    from services.faturalar import DEKONT_TURLERI

    try:
        veri = await ds.akistan_oku(dosya, await ds.boyut_siniri_bayt(db))
        await ds.klasor_hazirla(db, o.eposta, "Ortaklık dekontları", "musteri")
        kayit = await ds.dosya_kaydet(
            db, eposta=o.eposta, klasor="Ortaklık dekontları", ad_ham=getattr(dosya, "filename", None) or "dekont.pdf",
            veri=veri, yukleyen=eposta_duzelt(yukleyen) or None, yukleyen_rol="admin", izinli=DEKONT_TURLERI,
        )
    except ds.DosyaHatasi as h:
        raise OrtaklikHatasi(h.durum, h.kod, **getattr(h, "ek", {}))
    return kayit.id


async def odendi_isaretle(db: AsyncSession, t: OrtakOdemeTalepleri, yapan: str, *, dekont: Any = None,
                          notu: Any = None) -> OrtakOdemeTalepleri:
    if t.durum != "bekliyor":
        raise OrtaklikHatasi(409, f"durum_{t.durum}")
    o = await ortak_getir(db, t.ortak_id)
    if dekont is not None and (getattr(dekont, "filename", "") or "").strip():
        t.dekont_dosya_id = await dekont_kaydet(db, o, dekont, yapan)
    an = simdi()
    t.durum, t.odendi_at, t.odeyen, t.notu = "odendi", an, eposta_duzelt(yapan) or None, _metin(notu, SINIR["not"])
    K = OrtakKomisyonlari
    await db.execute(update(K).where(K.odeme_talebi_id == t.id, K.durum == "odeme_talebinde")
                     .values(durum="odendi", updated_at=an).execution_options(synchronize_session=False))
    from services import denetim

    await denetim.denetim_yaz(db, islem="guncelle", tablo="ortak_odeme_talepleri", kayit_id=t.id,
                              ozet=f"Ortaklık ödemesi ödendi: {o.ad} {t.tutar} {t.para_birimi}",
                              sonra={"durum": "odendi", "dekont": bool(t.dekont_dosya_id), "odeyen": t.odeyen})
    await db.commit()
    await db.refresh(t)
    try:
        from services.notify import dispatch

        await dispatch(
            db, event_type="ortaklik_durum",
            title=f"Komisyon ödemeniz yapıldı / Your commission was paid: {t.tutar} {t.para_birimi}",
            body=(f"Merhaba {o.ad},\n\n{t.tutar} {t.para_birimi} tutarındaki komisyon ödemeniz {iban_maskele(t.iban)} "
                  f"hesabına gönderildi." + (" Dekont panelinizde." if t.dekont_dosya_id else "")
                  + (f"\nNot: {t.notu}" if t.notu else "")
                  + f"\n\nYour commission payment of {t.tutar} {t.para_birimi} was sent.\n\n— By Mehmet KURU Dev"),
            recipients=[{"email": o.eposta, "role": "client"}], link="/client?sekme=ortaklik",
            ref_type="ortaklik_talep", ref_id=t.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Ortaklık ödeme e-postası gönderilemedi")
    return t


async def talep_reddet(db: AsyncSession, t: OrtakOdemeTalepleri, yapan: str, neden: Any) -> OrtakOdemeTalepleri:
    if t.durum != "bekliyor":
        raise OrtaklikHatasi(409, f"durum_{t.durum}")
    an = simdi()
    t.durum, t.ret_nedeni, t.odeyen = "reddedildi", _metin(neden, SINIR["not"]), eposta_duzelt(yapan) or None
    K = OrtakKomisyonlari
    await db.execute(update(K).where(K.odeme_talebi_id == t.id, K.durum == "odeme_talebinde")
                     .values(durum="onaylandi", odeme_talebi_id=None, updated_at=an).execution_options(synchronize_session=False))
    await db.commit()
    await db.refresh(t)
    o = await ortak_getir(db, t.ortak_id)
    try:
        from services.notify import dispatch

        await dispatch(db, event_type="ortaklik_durum", title="Ödeme talebiniz hakkında / About your payout request",
                       body=(f"Merhaba {o.ad},\n\n{t.tutar} {t.para_birimi} ödeme talebiniz şu an işleme alınamadı; tutar "
                             f"bakiyenize geri döndü." + (f"\nNot: {t.ret_nedeni}" if t.ret_nedeni else "")
                             + "\n\nYour payout request could not be processed; the amount is back in your balance."),
                       recipients=[{"email": o.eposta, "role": "client"}], link="/client?sekme=ortaklik",
                       ref_type="ortaklik_talep", ref_id=t.id)
    except Exception:  # noqa: BLE001
        logger.exception("Ortaklık talep reddi e-postası gönderilemedi")
    return t


async def komisyon_islem(db: AsyncSession, k: OrtakKomisyonlari, islem: str, yapan: str, notu: Any = None) -> OrtakKomisyonlari:
    """Yönetici: beklemedeki komisyonu erken onayla ya da şüpheliyi iptal et (talepteki/ödenmiş kayda dokunulmaz)."""
    if islem == "onayla":
        if k.durum != "beklemede":
            raise OrtaklikHatasi(409, f"durum_{k.durum}")
        k.durum = "onaylandi"
    elif islem == "iptal":
        if k.durum not in ("beklemede", "onaylandi"):
            raise OrtaklikHatasi(409, f"durum_{k.durum}")
        k.durum = "iptal"
    else:
        raise OrtaklikHatasi(400, "islem_gecersiz")
    k.notu = _metin(notu, SINIR["not"]) or k.notu
    from services import denetim

    await denetim.denetim_yaz(db, islem="guncelle", tablo="ortak_komisyonlari", kayit_id=k.id,
                              ozet=f"Komisyon {islem}: #{k.id} {k.tutar} {k.para_birimi}", sonra={"durum": k.durum,
                                                                                                 "yapan": eposta_duzelt(yapan)})
    await db.commit()
    await db.refresh(k)
    if islem == "onayla" and (k.tutar or 0) > 0:
        await komisyon_onay_bildir(db, k.ortak_id, {k.para_birimi or "TRY": Decimal(str(k.tutar))})
        await db.refresh(k)
    return k


# ---------------------------------------------------------------------------
# Yönetici listeleri, özetler (gelen kutusu / haftalık özet)
# ---------------------------------------------------------------------------
async def ortak_adlari(db: AsyncSession, idler) -> Dict[int, str]:
    idler = {int(i) for i in idler if i}
    if not idler:
        return {}
    return {int(i): a for i, a in (await db.execute(select(Ortaklar.id, Ortaklar.ad).where(Ortaklar.id.in_(idler)))).all()}


async def ortak_listesi(db: AsyncSession, durumlar: Optional[Tuple[str, ...]] = None) -> List[Dict[str, Any]]:
    await olgunlasanlari_onayla(db)
    ayar = await ayarlar(db)
    s = select(Ortaklar).where(Ortaklar.hesap == AJANS)
    if durumlar:
        s = s.where(Ortaklar.durum.in_(durumlar))
    ortaklar = (await db.execute(s.order_by(Ortaklar.id.desc()).limit(500))).scalars().all()
    sonuc = []
    for o in ortaklar:
        d = ortak_sozlugu(o, yonetici=True, ayar=ayar)
        d["bakiyeler"] = await bakiyeler(db, o.id) if o.durum in ("onaylandi", "askida") else {}
        d["tiklama"] = int((await db.execute(select(func.coalesce(func.sum(OrtakTiklamalari.sayi), 0))
                                             .where(OrtakTiklamalari.ortak_id == o.id))).scalar() or 0)
        d["aday"] = int((await db.execute(select(func.count(OrtakReferanslari.id)).where(OrtakReferanslari.ortak_id == o.id))).scalar() or 0)
        sonuc.append(d)
    return sonuc


async def bekleyen_basvurular(db: AsyncSession) -> List[Ortaklar]:
    return list((await db.execute(select(Ortaklar).where(Ortaklar.hesap == AJANS, Ortaklar.durum == "beklemede")
                                  .order_by(Ortaklar.basvuru_at))).scalars().all())


async def bekleyen_talepler(db: AsyncSession) -> List[Tuple[OrtakOdemeTalepleri, Optional[str]]]:
    satirlar = (
        await db.execute(
            select(OrtakOdemeTalepleri, Ortaklar.ad).join(Ortaklar, Ortaklar.id == OrtakOdemeTalepleri.ortak_id, isouter=True)
            .where(OrtakOdemeTalepleri.hesap == AJANS, OrtakOdemeTalepleri.durum == "bekliyor")
            .order_by(OrtakOdemeTalepleri.created_at)
        )
    ).all()
    return [(t, ad) for t, ad in satirlar]


# ---------------------------------------------------------------------------
# CSV (yönetici dışa aktarımı)
# ---------------------------------------------------------------------------
def _csv_hucre(deger: Any) -> Any:
    """Tablo programında formül olarak çalışmasın (CSV enjeksiyonu)."""
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + deger
    return deger


def csv_metni(basliklar: List[str], satirlar: List[List[Any]]) -> str:
    import csv
    import io

    cikti = io.StringIO()
    w = csv.writer(cikti)
    w.writerow(basliklar)
    for satir in satirlar:
        w.writerow([_csv_hucre(x) for x in satir])
    return "\ufeff" + cikti.getvalue()


KOMISYON_CSV = ["id", "tarih", "ortak", "ortak_eposta", "kural", "tur", "fatura_no", "musteri_eposta", "matrah", "oran",
                "tutar", "para_birimi", "durum", "bekleme_bitis", "odeme_talebi_id", "supheli", "not"]
TALEP_CSV = ["id", "tarih", "ortak", "ortak_eposta", "tutar", "para_birimi", "durum", "iban", "odendi_at", "odeyen",
             "not", "ret_nedeni"]


async def _ortak_sozlugu_idden(db: AsyncSession, idler) -> Dict[int, Ortaklar]:
    idler = {int(i) for i in idler if i}
    if not idler:
        return {}
    return {o.id: o for o in (await db.execute(select(Ortaklar).where(Ortaklar.id.in_(idler)))).scalars().all()}


async def komisyon_csv(db: AsyncSession, satirlar: List[OrtakKomisyonlari]) -> str:
    ortaklar = await _ortak_sozlugu_idden(db, {k.ortak_id for k in satirlar})
    veri = []
    for k in satirlar:
        o = ortaklar.get(k.ortak_id)
        veri.append([k.id, iso(k.created_at), o.ad if o else "", o.eposta if o else "", k.kural or "ilk", k.tur,
                     k.fatura_no or "", k.musteri_eposta or "", k.matrah, k.oran, k.tutar, k.para_birimi, k.durum,
                     iso(k.bekleme_bitis) or "", k.odeme_talebi_id or "", ",".join(_json_liste(k.supheli)), k.notu or ""])
    return csv_metni(KOMISYON_CSV, veri)


async def talep_csv(db: AsyncSession, satirlar: List[OrtakOdemeTalepleri]) -> str:
    """IBAN maskeli: dosya uygulamanın dışına çıkıyor (muhasebeye iletilebilir); tam değer yalnız panelde."""
    ortaklar = await _ortak_sozlugu_idden(db, {t.ortak_id for t in satirlar})
    veri = []
    for t in satirlar:
        o = ortaklar.get(t.ortak_id)
        veri.append([t.id, iso(t.created_at), o.ad if o else "", o.eposta if o else "", t.tutar, t.para_birimi, t.durum,
                     iban_maskele(t.iban) or "", iso(t.odendi_at) or "", t.odeyen or "", t.notu or "", t.ret_nedeni or ""])
    return csv_metni(TALEP_CSV, veri)


async def zamanli_gorev(db: AsyncSession, zorla: bool = False) -> Dict[str, Any]:
    return await olgunlasanlari_onayla(db)


__all__ = [
    "OrtaklikHatasi", "ayarlar", "ayarlari_yaz", "program_bilgisi", "basvuru_yap", "karar_ver", "ortak_guncelle",
    "iban_duzelt", "iban_kaydet", "tiklama_say", "atif_yaz", "formdan_isle", "kayit_referansi", "kendi_mi",
    "olgunlasanlari_onayla",
    "panel", "odeme_talebi_olustur", "odendi_isaretle", "talep_reddet", "komisyon_islem", "ortak_listesi",
    "bekleyen_basvurular", "bekleyen_talepler", "zamanli_gorev",
]
