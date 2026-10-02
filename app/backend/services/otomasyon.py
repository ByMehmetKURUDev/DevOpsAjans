"""Faz 4W — otomasyon kuralları: kuyruk, çalıştırıcı, eylemler, kuru çalıştırma, temizlik.

Akış
----
1. Olay ÜRETİMİ Faz 4A'nın tek noktasında (`services/webhook.py`): flush
   kancası, `olay_yaz_sync` ve zamanlı `olaylari_yayinla_sync`. Bu modül
   oraya `abone_ekle` ile ikinci abone olarak kaydoluyor (webhook teslimatı
   değişmedi).
2. Abone, olayla eşleşen AKTİF kurallar için aynı işlemde (SAVEPOINT)
   `otomasyon_calismalari`na `bekliyor` satırı yazıyor — istek yanıtı
   beklemiyor. Kural listesi 30 sn önbellekte; hiç kural yoksa veritabanına
   gidilmiyor. Eşleşme: ajans kuralı bütün olaylarda (ajansın kendi işi);
   müşteri kuralı yalnız kendi hesabının, müşteriye görünen olaylarında.
3. İşlem onaylanınca arka plan görevi (`after_commit` → asyncio) zamanı
   gelmiş satırları işliyor; kalanlar ve "bekle" eyleminden sonra devam
   edenler zamanlı uçta (`services/zamanli.py` → `otomasyon`).

Koruma
------
* Döngü: bir kuralın eylemi sırasında oturuma zincir bilgisi konuyor
  (`session.info["otomasyon_zinciri"]`: derinlik + zincirdeki kurallar);
  o eylemden doğan olay aynı kuralı (ve zincirdeki atalarını) tetiklemez,
  zincir derinliği en çok 3 — aşan satır `atlandi` (dongu | derinlik) olarak
  günlüğe düşer.
* Hız: hesap başına dakikalık/saatlik çalıştırma sınırı (müşteride modül
  ayarı); aşan satır `atlandi: hiz_siniri`.
* Idempotent: (olay_id, kural_id) benzersiz; satır koşullu kilitle bir kez
  işleniyor; zamanlı `fatura.gecikti` olayının kimliği belirlenimli
  (fatura + eşik).
* Pazarlama e-postası yalnız pazarlama izni olan alıcıya (`crm_adaylar`
  `pazarlama_izni_at`, Faz 4G); yoksa eylem atlanır ve günlüğe yazılır.
"""

import asyncio
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.otomasyon import OtomasyonCalismalari, OtomasyonKurallari
from services import otomasyon_kural as kural
from services.api_erisimi import Sahip
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MODUL = "otomasyon"
IZIN = "otomasyon"
SAKLAMA_SURESI = timedelta(days=30)
KILIT_SURESI = timedelta(seconds=120)
ONBELLEK_SN = 30.0
TUR_SINIRI = 50
TUR_BUTCESI_SN = 40.0
#: Arka plan işi başlamadan önce kısa bekleme: aynı istekteki arka plan işleri
#: (ör. randevunun CRM'e bağlanması) bitsin. Testler 0 yapıyor.
POMPA_GECIKMESI_SN = 2.0
#: Testler kapatıyor (işlemeyi kendileri tetikliyor).
ANLIK_ISLEME = True
LISTE_SINIRI = 100


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


def iso(an: Any) -> Optional[str]:
    if an is None:
        return None
    if isinstance(an, datetime):
        return utc(an).isoformat().replace("+00:00", "Z")
    if isinstance(an, date):
        return an.isoformat()
    return str(an)


def eposta_duzelt(e: Any) -> str:
    return str(e or "").strip().lower()


def _json(metin: Any, varsayilan: Any) -> Any:
    if metin is None or metin == "":
        return varsayilan
    if isinstance(metin, (dict, list)):
        return metin
    try:
        return json.loads(metin)
    except (TypeError, ValueError):
        return varsayilan


def _yaz(deger: Any) -> str:
    return json.dumps(deger, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Kural önbelleği (flush kancası her seferinde tabloya gitmesin)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _KuralOzeti:
    id: int
    sahip_tur: str
    hesap: Optional[str]
    tetik: str


_onbellek: Dict[str, Any] = {"bitis": 0.0, "kurallar": None}


def onbellegi_temizle() -> None:
    _onbellek["bitis"] = 0.0
    _onbellek["kurallar"] = None


def _onbellek_gecerli() -> Optional[List[_KuralOzeti]]:
    if _onbellek["kurallar"] is not None and _onbellek["bitis"] >= time.monotonic():
        return _onbellek["kurallar"]
    return None


def _kurallari_yukle_sync(baglanti) -> List[_KuralOzeti]:
    t = OtomasyonKurallari.__table__
    satirlar = baglanti.execute(select(t.c.id, t.c.sahip_tur, t.c.hesap_email, t.c.tetik).where(t.c.aktif.is_(True))).all()
    liste = [_KuralOzeti(int(s[0]), s[1], eposta_duzelt(s[2]) or None, s[3]) for s in satirlar]
    _onbellek["kurallar"] = liste
    _onbellek["bitis"] = time.monotonic() + ONBELLEK_SN
    return liste


def _ilgileniyor_mu(tur: Optional[str]) -> bool:
    if tur is not None and tur not in kural.OLAY_SOZLUGU:
        return False  # ör. yüksek hacimli `qr.tarama`: otomasyon kataloğunda yok
    kurallar = _onbellek_gecerli()
    if kurallar is None:
        return True  # bilinmiyor: yazımda yüklenecek
    if tur is None:
        return bool(kurallar)
    return any(k.tetik == tur for k in kurallar)


def _eslesenler(kurallar: List[_KuralOzeti], tur: str, hesap: Optional[str], gorur: bool) -> List[_KuralOzeti]:
    olay = kural.OLAY_SOZLUGU.get(tur)
    if olay is None:
        return []
    sonuc = []
    for k in kurallar:
        if k.tetik != tur:
            continue
        if k.sahip_tur == "ajans":
            sonuc.append(k)
        elif k.sahip_tur == "musteri" and olay.musteri and hesap and gorur and k.hesap == hesap:
            sonuc.append(k)
    return sonuc


# ---------------------------------------------------------------------------
# Abone: olay → kuyruk satırları (çağıranın işleminde)
# ---------------------------------------------------------------------------
_bekleyen: Dict[str, bool] = {"var": False}


def _kuyruga_yaz(baglanti, olaylar: List[Tuple[str, Optional[str], Dict[str, Any], bool]], baglam: Dict[str, Any]) -> int:
    kurallar = _onbellek_gecerli()
    if kurallar is None:
        kurallar = _kurallari_yukle_sync(baglanti)
    if not kurallar:
        return 0
    zincir = baglam.get("zincir") or {}
    derinlik = int(zincir.get("derinlik") or 1)
    zincirdeki = {int(x) for x in (zincir.get("kurallar") or []) if str(x).isdigit()}
    an = simdi()
    satirlar: List[Dict[str, Any]] = []
    t = OtomasyonCalismalari.__table__
    for tur, hesap, veri, gorur in olaylar:
        if tur not in kural.OLAY_SOZLUGU:
            continue
        h = eposta_duzelt(hesap) or None
        eslesen = _eslesenler(kurallar, tur, h, bool(gorur))
        if not eslesen:
            continue
        veri = dict(veri or {})
        belirli = veri.pop("_olay_id", None)
        olay_id = str(belirli or ("oto_" + secrets.token_hex(12)))[:80]
        if belirli:
            # Belirlenimli kimlik (zamanlı olay): daha önce yazılmışsa ikinci kez yazma.
            var_olan = {
                int(r[0]) for r in baglanti.execute(select(t.c.kural_id).where(t.c.olay_id == olay_id)).all()
            }
            eslesen = [k for k in eslesen if k.id not in var_olan]
        for k in eslesen:
            durum, neden = "bekliyor", None
            if k.id in zincirdeki:
                durum, neden = "atlandi", "dongu"
            elif derinlik > kural.EN_COK_DERINLIK:
                durum, neden = "atlandi", "derinlik"
            satirlar.append({
                "kural_id": k.id, "sahip_tur": k.sahip_tur, "hesap_email": k.hesap, "olay_id": olay_id, "tur": tur,
                "olay_hesap": h, "veri": _yaz(veri), "derinlik": derinlik, "zincir": _yaz(sorted(zincirdeki)),
                "durum": durum, "neden": neden, "sonraki_eylem": 0,
                "sonraki_zaman": an if durum == "bekliyor" else None, "bitis_at": an if durum != "bekliyor" else None,
                "created_at": an, "updated_at": an,
            })
    if satirlar:
        baglanti.execute(t.insert(), satirlar)
        if any(s["durum"] == "bekliyor" for s in satirlar):
            _bekleyen["var"] = True
    return len(satirlar)


# ---------------------------------------------------------------------------
# İşlem onaylandı → arka plan işleme
# ---------------------------------------------------------------------------
_gorev: Dict[str, Any] = {"pompa": None, "yeniden": False}


def _commit_sonrasi() -> None:
    if not _bekleyen["var"] or not ANLIK_ISLEME:
        return
    try:
        dongu = asyncio.get_running_loop()
    except RuntimeError:
        return  # döngü yok: zamanlı uç alır
    pompa = _gorev["pompa"]
    if pompa is not None and not pompa.done():
        _gorev["yeniden"] = True
        return
    _gorev["pompa"] = dongu.create_task(_pompa())


async def _pompa() -> None:
    try:
        if POMPA_GECIKMESI_SN:
            await asyncio.sleep(POMPA_GECIKMESI_SN)
        for _ in range(10):
            _bekleyen["var"] = False
            _gorev["yeniden"] = False
            await bekleyenleri_isle()
            if not (_bekleyen["var"] or _gorev["yeniden"]):
                break
    except Exception:  # noqa: BLE001
        logger.exception("Otomasyon arka plan işlemesi çalışamadı")


async def pompa_bitmesini_bekle() -> None:
    """Testler için."""
    pompa = _gorev["pompa"]
    if pompa is not None:
        await asyncio.wait_for(asyncio.shield(pompa), timeout=60)


def _abone_kaydet() -> None:
    from services import webhook

    webhook.abone_ekle(webhook.OlayAbonesi(
        ad="otomasyon",
        ilgileniyor_mu=_ilgileniyor_mu,
        yaz=_kuyruga_yaz,
        tablolar=webhook.IZLENEN_TABLOLAR | {"randevular"},
        commit_sonrasi=_commit_sonrasi,
    ))


_abone_kaydet()


# ---------------------------------------------------------------------------
# Sınırlar
# ---------------------------------------------------------------------------
async def _modul_ayari(db: AsyncSession, hesap: str, alan: str, varsayilan: int) -> int:
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, hesap, MODUL, alan)
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else varsayilan


async def kural_siniri(db: AsyncSession, sahip: Sahip) -> int:
    if sahip.yonetici:
        return kural.AJANS_KURAL_SINIRI
    return await _modul_ayari(db, sahip.hesap or "", "kural_siniri", kural.VARSAYILAN_KURAL_SINIRI)


async def hiz_sinirlari(db: AsyncSession, sahip_tur: str, hesap: Optional[str]) -> Tuple[int, int]:
    if sahip_tur == "ajans":
        return kural.AJANS_DAKIKA_SINIRI, kural.AJANS_SAAT_SINIRI
    return (
        await _modul_ayari(db, hesap or "", "calisma_dakika_siniri", kural.VARSAYILAN_DAKIKA_SINIRI),
        await _modul_ayari(db, hesap or "", "calisma_saat_siniri", kural.VARSAYILAN_SAAT_SINIRI),
    )


def _sahip_kosulu_calisma(sahip_tur: str, hesap: Optional[str]):
    if sahip_tur == "ajans":
        return and_(OtomasyonCalismalari.sahip_tur == "ajans", OtomasyonCalismalari.hesap_email.is_(None))
    return and_(OtomasyonCalismalari.sahip_tur == "musteri", OtomasyonCalismalari.hesap_email == hesap)


async def _hiz_asildi_mi(db: AsyncSession, k: OtomasyonKurallari) -> Optional[str]:
    dakika, saat = await hiz_sinirlari(db, k.sahip_tur, k.hesap_email)
    an = simdi()
    kosul = _sahip_kosulu_calisma(k.sahip_tur, k.hesap_email)
    say = lambda esik: select(func.count(OtomasyonCalismalari.id)).where(kosul, OtomasyonCalismalari.baslama_at >= esik)  # noqa: E731
    if int((await db.execute(say(an - timedelta(minutes=1)))).scalar() or 0) >= dakika:
        return "hiz_siniri_dakika"
    if int((await db.execute(say(an - timedelta(hours=1)))).scalar() or 0) >= saat:
        return "hiz_siniri_saat"
    return None


# ---------------------------------------------------------------------------
# Bağlam: olay verisi → taze kayıtlar (yalnız şemadaki alanlar)
# ---------------------------------------------------------------------------
def _sayi(d: Any) -> Optional[float]:
    if d is None:
        return None
    try:
        f = float(d)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def aday_sozlugu(a: Any) -> Dict[str, Any]:
    return {
        "id": a.id, "ad": a.ad, "firma": a.firma, "email": a.email, "telefon": a.telefon, "kaynak": a.kaynak,
        "asama": a.asama, "deger_tahmini": _sayi(a.deger_tahmini), "para_birimi": a.para_birimi,
        "etiketler": _json(a.etiketler, []), "sorumlu": a.sorumlu, "puan": a.puan, "butce": a.butce,
        "pazarlama_izni": a.pazarlama_izni_at is not None,
    }


def _proje_sozlugu(p: Any) -> Dict[str, Any]:
    return {"id": p.id, "baslik": p.title, "asama": p.stage, "durum": p.status, "ilerleme": p.progress,
            "kategori": p.category}


async def _hesap_adi(db: AsyncSession, eposta: str) -> Optional[str]:
    from models.auth import User

    ad = (await db.execute(select(User.name).where(func.lower(User.email) == eposta).limit(1))).scalar()
    if ad:
        return ad
    from models.projects import Projects

    return (
        await db.execute(
            select(Projects.client_name).where(func.lower(Projects.client_email) == eposta, Projects.client_name.isnot(None)).limit(1)
        )
    ).scalar()


async def _kayit(db: AsyncSession, model: Any, kimlik: Any) -> Any:
    try:
        kimlik = int(kimlik)
    except (TypeError, ValueError):
        return None
    return (await db.execute(select(model).where(model.id == kimlik).execution_options(populate_existing=True))).scalars().first()


async def baglam_kur(db: AsyncSession, tur: str, veri: Dict[str, Any], olay_hesap: Optional[str], ajans: bool
                     ) -> Optional[Dict[str, Any]]:
    """Kuralın koşul/yer tutucu bağlamı. Asıl kayıt silinmişse None."""
    from services import ozel_alanlar as oz

    b: Dict[str, Any] = {}
    onceki: Dict[str, Any] = {}
    on = tur.split(".", 1)[0]
    proje_id = None
    if on == "aday":
        from models.crm import CrmAdaylari

        a = await _kayit(db, CrmAdaylari, veri.get("aday_id"))
        if a is None:
            return None
        b["aday"] = aday_sozlugu(a)
        if tur == "aday.asama_degisti":
            onceki["aday.asama"] = veri.get("onceki_asama")
    elif on == "teklif":
        from models.teklifler import Teklifler

        t = await _kayit(db, Teklifler, veri.get("teklif_id"))
        if t is None:
            return None
        b["teklif"] = {"id": t.id, "no": t.no, "baslik": t.baslik, "genel_toplam": _sayi(t.genel_toplam),
                       "para_birimi": t.para_birimi, "durum": t.durum, "aday_ad": t.aday_ad, "aday_eposta": t.aday_eposta}
        proje_id = t.proje_id
    elif on == "sozlesme":
        from models.sozlesmeler import Sozlesmeler

        s = await _kayit(db, Sozlesmeler, veri.get("sozlesme_id"))
        if s is None:
            return None
        b["sozlesme"] = {"id": s.id, "no": s.no, "baslik": s.baslik}
    elif on == "fatura":
        from models.invoices import Invoices

        f = await _kayit(db, Invoices, veri.get("fatura_id"))
        if f is None:
            return None
        gecikme = veri.get("gecikme_gun")
        if gecikme is None and f.due_date:
            try:
                gecikme = max(0, (date.today() - date.fromisoformat(str(f.due_date)[:10])).days)
            except ValueError:
                gecikme = None
        b["fatura"] = {"id": f.id, "no": f.invoice_no, "tutar": _sayi(f.amount), "para_birimi": f.currency or "TRY",
                       "durum": f.status, "vade_tarihi": (str(f.due_date)[:10] if f.due_date else None), "gecikme_gun": gecikme}
    elif on == "destek":
        from models.support_tickets import Support_tickets

        t = await _kayit(db, Support_tickets, veri.get("talep_id"))
        if t is None:
            return None
        b["talep"] = {"id": t.id, "konu": t.subject, "durum": t.status, "oncelik": t.priority or "normal",
                      "hizmet": t.hizmet, "kaynak": t.kaynak,
                      "etiketler": [e.strip() for e in (t.etiketler or "").split(",") if e.strip()],
                      "yazan": veri.get("yazan")}
        proje_id = t.project_id
    elif on == "gorev":
        from models.proje_gorevleri import ProjectTasks

        g = await _kayit(db, ProjectTasks, veri.get("gorev_id"))
        if g is None:
            return None
        b["gorev"] = {"id": g.id, "baslik": g.baslik, "durum": g.durum, "oncelik": g.oncelik, "atanan": g.atanan,
                      "bitis_tarihi": iso(g.bitis_tarihi)}
        proje_id = g.proje_id
    elif on == "proje":
        proje_id = veri.get("proje_id")
        onceki["proje.asama"] = veri.get("onceki_asama")
    elif on == "menu":
        from models.qr_menu import MenuSiparisleri

        s = await _kayit(db, MenuSiparisleri, veri.get("siparis_id"))
        if s is None:
            return None
        b["siparis"] = {"id": s.id, "no": s.siparis_no, "durum": s.durum, "teslimat": s.teslimat, "masa": s.masa,
                        "toplam": round((s.toplam or 0) / 100, 2), "para_birimi": s.para_birimi,
                        "kalem_sayisi": len(_json(s.kalemler, [])), "musteri_ad": s.musteri_ad}
    elif on == "kart":
        from models.kartvizit import KartvizitMesajlari

        m = await _kayit(db, KartvizitMesajlari, veri.get("mesaj_id"))
        if m is None:
            return None
        b["mesaj"] = {"id": m.id, "ad": m.ad, "eposta": m.eposta, "telefon": m.telefon}
    elif on == "randevu":
        from models.randevu import Randevular, RandevuTurleri

        r = await _kayit(db, Randevular, veri.get("randevu_id"))
        if r is None:
            return None
        rt = await _kayit(db, RandevuTurleri, r.tur_id)
        b["randevu"] = {"id": r.id, "ad": r.ad, "eposta": r.eposta, "telefon": r.telefon, "baslangic": iso(r.baslangic),
                        "tur": rt.ad if rt else None, "sure_dk": rt.sure_dk if rt else None, "konum": r.konum}
        if ajans and r.crm_aday_id:
            from models.crm import CrmAdaylari

            a = await _kayit(db, CrmAdaylari, r.crm_aday_id)
            if a is not None:
                b["aday"] = aday_sozlugu(a)
    if proje_id:
        from models.projects import Projects

        p = await _kayit(db, Projects, proje_id)
        if p is not None and (ajans or eposta_duzelt(p.client_email) == eposta_duzelt(olay_hesap)):
            b["proje"] = _proje_sozlugu(p)
        elif on == "proje":
            return None
    if olay_hesap:
        b["hesap"] = {"email": olay_hesap, "ad": await _hesap_adi(db, olay_hesap)}

    # Yalnız olayın şemasındaki ad alanları (müşteride aday yok) + özel alanlar.
    izinli = set(kural.olay_nesneleri(tur, ajans))
    b = {ns: d for ns, d in b.items() if ns in izinli}
    for ns, varlik in kural.OZEL_VARLIK.items():
        if ns not in b or (not ajans and varlik not in ("proje", "destek")):
            continue
        kimlik = b[ns].get("email") if ns == "hesap" else b[ns].get("id")
        if kimlik is not None:
            b[ns]["ozel"] = await oz.degerler(db, varlik, kimlik, yalniz_gorunur=not ajans)
    b["olay"] = {"tur": tur, "zaman": veri.get("_zaman") or iso(simdi())}
    b["kisi"] = kural.kisi_sec(tur, b)
    b["_onceki"] = {k: v for k, v in onceki.items() if v is not None}
    return b


# ---------------------------------------------------------------------------
# Eylemler
# ---------------------------------------------------------------------------
_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def pazarlama_izni_var_mi(db: AsyncSession, eposta: str) -> bool:
    """Faz 4G izni: bu adresle bir CRM adayında pazarlama izni kayıtlı mı (geri alınınca boşalıyor)."""
    from models.crm import CrmAdaylari

    e = eposta_duzelt(eposta)
    if not e:
        return False
    return (
        await db.execute(
            select(CrmAdaylari.id).where(func.lower(CrmAdaylari.email) == e, CrmAdaylari.pazarlama_izni_at.isnot(None)).limit(1)
        )
    ).scalar() is not None


def _sonuc(durum: str, neden: Optional[str] = None, **ozet: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"durum": durum}
    if neden:
        d["neden"] = neden[:120]
    if ozet:
        d["ozet"] = ozet
    return d


async def _aday_bul(db: AsyncSession, baglam: Dict[str, Any]) -> Any:
    from models.crm import CrmAdaylari, CrmAsamalari

    a_id = (baglam.get("aday") or {}).get("id")
    if a_id:
        a = await _kayit(db, CrmAdaylari, a_id)
        if a is not None:
            return a
    email = eposta_duzelt((baglam.get("kisi") or {}).get("email"))
    if not email:
        return None
    return (
        await db.execute(
            select(CrmAdaylari)
            .outerjoin(CrmAsamalari, CrmAsamalari.anahtar == CrmAdaylari.asama)
            .where(func.lower(CrmAdaylari.email) == email, or_(CrmAsamalari.tur.is_(None), CrmAsamalari.tur == "acik"))
            .order_by(CrmAdaylari.id.desc())
            .limit(1)
        )
    ).scalars().first()


async def eylem_yap(db: AsyncSession, k: Any, e: Dict[str, Any], baglam: Dict[str, Any], *, kuru: bool,
                    calisma: Any = None, ornek: bool = False) -> Dict[str, Any]:
    """Tek eylem. `kuru=True`: HİÇBİR yan etki yok, ne yapılacağı döner ("yapilacak" | "atlanacak").

    `ornek=True` (kuru çalıştırma örnek/elle düzenlenmiş veriyle): bağlamdaki kimlikler uydurma
    olduğundan olaydaki kayıt (aday, talep, olaydaki proje) veritabanında ARANMAZ; ne yapılacağı
    bağlamdan anlatılır. Kullanıcının seçtiği kayıtlar (sabit proje, webhook ucu) yine denetlenir."""
    tur = e.get("tur")
    ajans = k.sahip_tur == "ajans"
    yap, atla = ("yapilacak", "atlanacak") if kuru else ("basarili", "atlandi")

    def coz(metin: Any, kip: str = "metin") -> str:
        return kural.yer_tutuculari_coz(metin, baglam, kip)[0]

    if tur == "eposta":
        alici_tur = e.get("alici")
        if alici_tur == "sabit":
            alici = eposta_duzelt(e.get("adres"))
        elif alici_tur == "hesap":
            alici = eposta_duzelt((baglam.get("hesap") or {}).get("email") or (k.hesap_email if not ajans else ""))
        else:
            alici = eposta_duzelt((baglam.get("kisi") or {}).get("email"))
        if not alici or not _EPOSTA.match(alici):
            return _sonuc(atla, "alici_yok")
        if e.get("nitelik") == "pazarlama" and not await pazarlama_izni_var_mi(db, alici):
            return _sonuc(atla, "pazarlama_izni_yok", alici=alici)
        konu = coz(e.get("konu"), "konu")
        metin = coz(e.get("govde"), "metin")
        if kuru:
            return _sonuc(yap, None, alici=alici, konu=konu, govde=metin, nitelik=e.get("nitelik"))
        from services.notify import _eposta_gonder

        html = kural.html_govde(coz(e.get("govde"), "html"))
        durum, ayrinti = await _eposta_gonder(alici, konu, metin, {"html": html})
        if durum == "sent":
            return _sonuc("basarili", None, alici=alici, konu=konu, kanal=ayrinti)
        if durum == "skipped":
            return _sonuc("atlandi", "eposta_kanali_yok", alici=alici, konu=konu)
        return _sonuc("hata", f"eposta: {ayrinti}", alici=alici, konu=konu)

    if tur == "bildirim":
        alici_tur = e.get("alici")
        if alici_tur == "yoneticiler" and ajans:
            from services.notify import admin_recipients

            alicilar = await admin_recipients(db)
            link = "/admin?sekme=otomasyon"
        elif alici_tur == "sorumlu" and ajans:
            s = eposta_duzelt((baglam.get("aday") or {}).get("sorumlu"))
            alicilar = [{"email": s, "role": "admin"}] if s else []
            link = "/admin?sekme=crm"
        elif alici_tur == "ekip_uyesi" and ajans:
            alicilar = [{"email": eposta_duzelt(e.get("adres")), "role": "admin"}]
            link = "/admin?sekme=otomasyon"
        else:
            hesap = k.hesap_email if not ajans else (baglam.get("hesap") or {}).get("email")
            alicilar = [{"email": eposta_duzelt(hesap), "role": "client"}] if hesap else []
            link = "/client?sekme=otomasyon" if not ajans else "/client"
        alicilar = [a for a in alicilar if a.get("email")]
        if not alicilar:
            return _sonuc(atla, "alici_yok")
        baslik = coz(e.get("baslik"), "konu")
        govde = coz(e.get("govde") or "", "metin")
        if kuru:
            return _sonuc(yap, None, alicilar=[a["email"] for a in alicilar], baslik=baslik, govde=govde)
        from services.notify import dispatch

        yazilan = await dispatch(db, event_type="otomasyon_bildirimi", title=baslik, body=govde, recipients=alicilar,
                                 link=link, ref_type="otomasyon_kurallari", ref_id=k.id)
        return _sonuc("basarili", None, alici_sayisi=len({n.recipient_email for n in yazilan}), baslik=baslik)

    if tur == "gorev":
        from models.projects import Projects
        from models.proje_gorevleri import ProjectTasks

        proje_id = (baglam.get("proje") or {}).get("id") if e.get("proje") == "olay" else e.get("proje")
        if ornek and e.get("proje") == "olay":
            if not proje_id:
                return _sonuc(atla, "proje_yok")
            gun = e.get("son_tarih_gun")
            return _sonuc(yap, None, proje_id=proje_id, proje=(baglam.get("proje") or {}).get("baslik"),
                          baslik=coz(e.get("baslik"), "konu")[:200],
                          bitis_tarihi=iso(date.today() + timedelta(days=int(gun))) if gun is not None else None,
                          atanan=e.get("atanan"))
        p = await _kayit(db, Projects, proje_id) if proje_id else None
        if p is None or (not ajans and eposta_duzelt(p.client_email) != eposta_duzelt(k.hesap_email)):
            return _sonuc(atla, "proje_yok")
        adet = (await db.execute(select(func.count(ProjectTasks.id)).where(ProjectTasks.proje_id == p.id))).scalar()
        if int(adet or 0) >= 500:
            return _sonuc(atla, "gorev_siniri")
        baslik = coz(e.get("baslik"), "konu")[:200] or "—"
        aciklama = coz(e.get("aciklama") or "", "metin")[:4000] or None
        gun = e.get("son_tarih_gun")
        bitis = (date.today() + timedelta(days=int(gun))) if gun is not None else None
        if kuru:
            return _sonuc(yap, None, proje_id=p.id, proje=p.title, baslik=baslik, bitis_tarihi=iso(bitis),
                          atanan=e.get("atanan"))
        sira = (
            await db.execute(
                select(func.coalesce(func.max(ProjectTasks.sira), -1)).where(ProjectTasks.proje_id == p.id, ProjectTasks.durum == "yapilacak")
            )
        ).scalar()
        g = ProjectTasks(
            proje_id=p.id, baslik=baslik, aciklama=aciklama, durum="yapilacak", oncelik=e.get("oncelik") or "normal",
            atanan=e.get("atanan") or None, bitis_tarihi=bitis, sira=int(sira if sira is not None else -1) + 1,
            musteriye_gorunur=bool(e.get("musteriye_gorunur")) if ajans else True, kilometre_tasi=False,
            harcanan_saat=0.0, etiketler=json.dumps(["otomasyon"]), olusturan_eposta="otomasyon", created_at=simdi(),
        )
        db.add(g)
        await db.commit()
        return _sonuc("basarili", None, gorev_id=g.id, proje_id=p.id, baslik=baslik)

    if tur in ("crm_asama", "crm_etiket", "crm_sahip", "crm_aktivite"):
        if not ajans:
            return _sonuc(atla, "yalniz_ajans")
        if ornek:
            aday = baglam.get("aday") or {}
            if not aday and not (baglam.get("kisi") or {}).get("email"):
                return _sonuc(atla, "aday_yok")
            ayrinti = {k_: e.get(k_) for k_ in ("asama", "islem", "etiket", "sorumlu", "aktivite_tur") if e.get(k_)}
            if tur == "crm_aktivite":
                ayrinti["metin"] = coz(e.get("metin"), "metin")[:4000]
            return _sonuc(yap, None, aday_id=aday.get("id"), **ayrinti)
        a = await _aday_bul(db, baglam)
        if a is None:
            return _sonuc(atla, "aday_yok")
        if tur == "crm_asama":
            from models.crm import CrmAsamalari
            from services import crm

            hedef = (await db.execute(select(CrmAsamalari).where(CrmAsamalari.anahtar == e.get("asama")))).scalars().first()
            if hedef is None:
                return _sonuc("hata" if not kuru else atla, "asama_yok")
            if a.asama == hedef.anahtar:
                return _sonuc(atla, "zaten_asamada", aday_id=a.id)
            if kuru:
                return _sonuc(yap, None, aday_id=a.id, onceki=a.asama, asama=hedef.anahtar)
            await crm.asama_tasi(db, a, hedef, yapan="otomasyon", sebep=f"kural:{k.id}")
            a.updated_at = simdi()
            await db.commit()
            return _sonuc("basarili", None, aday_id=a.id, asama=hedef.anahtar)
        if tur == "crm_etiket":
            etiketler = [str(x) for x in _json(a.etiketler, [])]
            etiket = e.get("etiket")
            if e.get("islem") == "kaldir":
                if etiket not in etiketler:
                    return _sonuc(atla, "etiket_yok", aday_id=a.id)
                yeni = [x for x in etiketler if x != etiket]
            else:
                if etiket in etiketler:
                    return _sonuc(atla, "etiket_var", aday_id=a.id)
                if len(etiketler) >= 20:
                    return _sonuc(atla, "etiket_siniri", aday_id=a.id)
                yeni = etiketler + [etiket]
            if kuru:
                return _sonuc(yap, None, aday_id=a.id, etiketler=yeni)
            a.etiketler = json.dumps(yeni, ensure_ascii=False)
            a.updated_at = simdi()
            await db.commit()
            return _sonuc("basarili", None, aday_id=a.id, etiketler=yeni)
        if tur == "crm_sahip":
            if eposta_duzelt(a.sorumlu) == e.get("sorumlu"):
                return _sonuc(atla, "zaten_sorumlu", aday_id=a.id)
            if kuru:
                return _sonuc(yap, None, aday_id=a.id, sorumlu=e.get("sorumlu"))
            a.sorumlu = e.get("sorumlu")
            a.updated_at = simdi()
            await db.commit()
            return _sonuc("basarili", None, aday_id=a.id, sorumlu=e.get("sorumlu"))
        metin = coz(e.get("metin"), "metin")[:4000]
        if kuru:
            return _sonuc(yap, None, aday_id=a.id, aktivite_tur=e.get("aktivite_tur"), metin=metin)
        from models.crm import CrmAktiviteler

        db.add(CrmAktiviteler(aday_id=a.id, tur=e.get("aktivite_tur") or "not", olay=None, metin=metin,
                              veri=_yaz({"kural_id": k.id}), yapan="otomasyon", zaman=simdi()))
        await db.commit()
        return _sonuc("basarili", None, aday_id=a.id, aktivite_tur=e.get("aktivite_tur"))

    if tur == "destek":
        from models.support_tickets import Support_tickets

        if not ajans:
            return _sonuc(atla, "yalniz_ajans")
        if ornek:
            talep = baglam.get("talep") or {}
            return _sonuc(yap if talep else atla, None if talep else "talep_yok", talep_id=talep.get("id"),
                          oncelik=e.get("oncelik"), etiket=e.get("etiket"))
        t = await _kayit(db, Support_tickets, (baglam.get("talep") or {}).get("id"))
        if t is None:
            return _sonuc(atla, "talep_yok")
        etiketler = [x.strip() for x in (t.etiketler or "").split(",") if x.strip()]
        degisim: Dict[str, Any] = {}
        if e.get("oncelik") and (t.priority or "normal") != e.get("oncelik"):
            degisim["oncelik"] = e.get("oncelik")
        if e.get("etiket") and e.get("etiket") not in etiketler:
            degisim["etiketler"] = etiketler + [e.get("etiket")]
        if not degisim:
            return _sonuc(atla, "degisiklik_yok", talep_id=t.id)
        if kuru:
            return _sonuc(yap, None, talep_id=t.id, **degisim)
        if "oncelik" in degisim:
            t.priority = degisim["oncelik"]
        if "etiketler" in degisim:
            t.etiketler = ",".join(degisim["etiketler"])[:500]
        await db.commit()
        return _sonuc("basarili", None, talep_id=t.id, **degisim)

    if tur == "webhook":
        from models.api_erisimi import WebhookTeslimatlari, WebhookUcNoktalari
        from services import webhook as w

        uc = await _kayit(db, WebhookUcNoktalari, e.get("uc_id"))
        sahibi_mi = uc is not None and (
            (ajans and uc.sahip_tur == "ajans")
            or (not ajans and uc.sahip_tur == "musteri" and eposta_duzelt(uc.hesap_email) == eposta_duzelt(k.hesap_email))
        )
        if not sahibi_mi:
            return _sonuc(atla, "webhook_yok")
        if not uc.aktif:
            return _sonuc(atla, "webhook_pasif", uc_id=uc.id)
        olay_turu = "otomasyon." + (e.get("etiket") or "kural")
        if kuru:
            return _sonuc(yap, None, uc_id=uc.id, url=uc.url, olay=olay_turu)
        an = simdi()
        olay_id = w.olay_kimligi()
        veri = {"kural_id": k.id, "kural": k.ad, "tetik": getattr(calisma, "tur", None),
                "tetik_olay_id": getattr(calisma, "olay_id", None), "veri": _json(getattr(calisma, "veri", None), {})}
        govde = w.olay_govdesi(olay_id, olay_turu, uc.hesap_email, veri, an)
        sonuc = await db.execute(WebhookTeslimatlari.__table__.insert().values(
            uc_id=uc.id, olay_id=olay_id, tur=olay_turu, hesap_email=uc.hesap_email, govde=govde, durum="bekliyor",
            deneme_sayisi=0, sonraki_deneme=an, created_at=an, updated_at=an,
        ))
        w._bekleyen["var"] = True
        await db.commit()
        return _sonuc("basarili", None, uc_id=uc.id, teslimat_id=int(sonuc.inserted_primary_key[0]), olay=olay_turu)

    if tur == "bekle":
        dk = int(e.get("miktar") or 0) * kural.BEKLEME_BIRIMLERI.get(e.get("birim") or "dakika", 1)
        return _sonuc(yap if kuru else "bekliyor", None, dakika=dk)
    return _sonuc("hata", "eylem_turu_gecersiz")


# ---------------------------------------------------------------------------
# Çalıştırıcı
# ---------------------------------------------------------------------------
async def _kilitle(db: AsyncSession, calisma_id: int) -> bool:
    an = simdi()
    sonuc = await db.execute(
        update(OtomasyonCalismalari)
        .where(
            OtomasyonCalismalari.id == calisma_id,
            OtomasyonCalismalari.durum == "bekliyor",
            or_(OtomasyonCalismalari.kilit_bitis.is_(None), OtomasyonCalismalari.kilit_bitis <= an),
        )
        .values(kilit_bitis=an + KILIT_SURESI)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(sonuc.rowcount or 0) == 1


async def _guncelle(db: AsyncSession, calisma_id: int, **degerler: Any) -> None:
    degerler["updated_at"] = simdi()
    await db.execute(
        update(OtomasyonCalismalari).where(OtomasyonCalismalari.id == calisma_id).values(**degerler)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


async def _bitir(db: AsyncSession, c: Any, durum: str, neden: Optional[str] = None, **ek: Any) -> Dict[str, Any]:
    await _guncelle(db, c.id, durum=durum, neden=neden, kilit_bitis=None, bitis_at=simdi(), sonraki_zaman=None, **ek)
    return {"calisma_id": c.id, "durum": durum, "neden": neden}


async def calisma_isle(db: AsyncSession, calisma_id: int) -> Dict[str, Any]:
    """Tek çalıştırma satırı (kilitli). Kalınan yerden devam eder ("bekle" sonrası)."""
    from services import denetim

    if not await _kilitle(db, calisma_id):
        return {"atlandi": "kilitli"}
    c = (
        await db.execute(select(OtomasyonCalismalari).where(OtomasyonCalismalari.id == calisma_id)
                         .execution_options(populate_existing=True))
    ).scalars().first()
    if c is None:
        return {"atlandi": "yok"}
    k = (
        await db.execute(select(OtomasyonKurallari).where(OtomasyonKurallari.id == c.kural_id)
                         .execution_options(populate_existing=True))
    ).scalars().first()
    if k is None:
        return await _bitir(db, c, "atlandi", "kural_yok")
    if not k.aktif:
        return await _bitir(db, c, "atlandi", "kural_pasif")
    ajans = k.sahip_tur == "ajans"
    if not ajans:
        from services.moduller import modul_acik_mi

        if not await modul_acik_mi(db, k.hesap_email or "", MODUL):
            return await _bitir(db, c, "atlandi", "modul_kapali")
    try:
        denetim.aktor_ata(None, "otomasyon")
    except Exception:  # noqa: BLE001
        pass

    if c.baslama_at is None:
        neden = await _hiz_asildi_mi(db, k)
        if neden:
            return await _bitir(db, c, "atlandi", neden)
        await _guncelle(db, c.id, baslama_at=simdi())
        await db.execute(
            update(OtomasyonKurallari).where(OtomasyonKurallari.id == k.id)
            .values(calisma_sayisi=OtomasyonKurallari.calisma_sayisi + 1, son_calisma_at=simdi())
            .execution_options(synchronize_session=False)
        )
        await db.commit()

    veri = _json(c.veri, {})
    baglam = await baglam_kur(db, c.tur, veri, c.olay_hesap, ajans)
    if baglam is None:
        return await _bitir(db, c, "atlandi", "kayit_yok")

    if c.kosul_sonucu is None:
        sonuc, ayrinti = kural.kosullari_degerlendir(k.kosullar, baglam)
        if not sonuc:
            return await _bitir(db, c, "kosul_tutmadi", None, kosul_sonucu=False, kosul_ayrinti=_yaz(ayrinti))
        await _guncelle(db, c.id, kosul_sonucu=True, kosul_ayrinti=_yaz(ayrinti))

    eylemler = _json(k.eylemler, [])
    sonuclar: List[Dict[str, Any]] = _json(c.eylem_sonuclari, [])
    i = int(c.sonraki_eylem or 0)
    zincir = {"derinlik": int(c.derinlik or 1) + 1, "kurallar": sorted(set(_json(c.zincir, [])) | {k.id})}
    oturum_bilgisi = db.sync_session.info
    oturum_bilgisi["otomasyon_zinciri"] = zincir
    try:
        while i < len(eylemler):
            e = eylemler[i]
            if e.get("tur") == "bekle":
                dk = int(e.get("miktar") or 0) * kural.BEKLEME_BIRIMLERI.get(e.get("birim") or "dakika", 1)
                sonraki = simdi() + timedelta(minutes=max(1, dk))
                sonuclar.append({"sira": i, "tur": "bekle", "durum": "basarili", "ozet": {"dakika": dk, "devam": iso(sonraki)}})
                await _guncelle(db, c.id, durum="bekliyor", sonraki_eylem=i + 1, sonraki_zaman=sonraki,
                                eylem_sonuclari=_yaz(sonuclar), kilit_bitis=None)
                return {"calisma_id": c.id, "durum": "bekliyor", "devam": iso(sonraki)}
            try:
                r = await eylem_yap(db, k, e, baglam, kuru=False, calisma=c)
            except Exception as h:  # noqa: BLE001 - bir eylemin hatası diğerlerini durdurmasın
                logger.exception("Otomasyon eylemi hata verdi (kural %s, eylem %s)", k.id, e.get("tur"))
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                r = _sonuc("hata", type(h).__name__)
            sonuclar.append({"sira": i, "tur": e.get("tur"), **r})
            i += 1
            await _guncelle(db, c.id, sonraki_eylem=i, eylem_sonuclari=_yaz(sonuclar))
    finally:
        oturum_bilgisi.pop("otomasyon_zinciri", None)
    durum = "hata" if any(s.get("durum") == "hata" for s in sonuclar) else "tamam"
    return await _bitir(db, c, durum, None)


async def bekleyenleri_isle(*, sinir: int = TUR_SINIRI) -> Dict[str, Any]:
    """Zamanı gelmiş satırlar; her biri kendi oturumunda, sırayla (süre bütçeli)."""
    from core.database import db_manager

    ozet = {"islenen": 0, "tamam": 0, "atlanan": 0, "hata": 0, "bekleyen": 0}
    if db_manager.async_session_maker is None:
        return ozet
    an = simdi()
    async with db_manager.async_session_maker() as db:
        idler = [
            int(r[0])
            for r in (
                await db.execute(
                    select(OtomasyonCalismalari.id)
                    .where(
                        OtomasyonCalismalari.durum == "bekliyor",
                        or_(OtomasyonCalismalari.sonraki_zaman.is_(None), OtomasyonCalismalari.sonraki_zaman <= an),
                        or_(OtomasyonCalismalari.kilit_bitis.is_(None), OtomasyonCalismalari.kilit_bitis <= an),
                    )
                    .order_by(OtomasyonCalismalari.sonraki_zaman.asc(), OtomasyonCalismalari.id.asc())
                    .limit(sinir)
                )
            ).all()
        ]
    baslangic = time.monotonic()
    for cid in idler:
        if time.monotonic() - baslangic > TUR_BUTCESI_SN:
            break
        try:
            async with db_manager.async_session_maker() as db:
                sonuc = await calisma_isle(db, cid)
        except Exception:  # noqa: BLE001
            logger.exception("Otomasyon çalıştırması işlenemedi (id=%s)", cid)
            ozet["hata"] += 1
            continue
        if "atlandi" in sonuc and "durum" not in sonuc:
            continue
        ozet["islenen"] += 1
        d = sonuc.get("durum")
        if d in ("tamam", "kosul_tutmadi"):
            ozet["tamam"] += 1
        elif d == "atlandi":
            ozet["atlanan"] += 1
        elif d == "bekliyor":
            ozet["bekleyen"] += 1
        else:
            ozet["hata"] += 1
    return ozet


# ---------------------------------------------------------------------------
# Kuru çalıştırma ("Test et")
# ---------------------------------------------------------------------------
@dataclass
class _GeciciKural:
    id: int
    sahip_tur: str
    hesap_email: Optional[str]
    ad: str
    kosullar: str
    eylemler: str


def _baglami_temizle(ham: Any) -> Dict[str, Any]:
    """Kullanıcının düzenlediği örnek bağlam: yalnız düz sözlükler/değerler, boyut sınırlı."""
    if not isinstance(ham, dict):
        raise kural.KuralHatasi("baglam_gecersiz")
    metin = json.dumps(ham, ensure_ascii=False, default=str)
    if len(metin) > 20000:
        raise kural.KuralHatasi("baglam_buyuk")
    return json.loads(metin)


async def kuru_calistir(db: AsyncSession, sahip: Sahip, temiz: Dict[str, Any], *, kural_id: Optional[int] = None,
                        baglam: Optional[Dict[str, Any]] = None, calisma_id: Optional[int] = None,
                        ozel: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Doğrulanmış kural sütunları (`temiz`) + örnek/son olay bağlamı → ne yapılacağı. Yan etki YOK."""
    tetik = temiz["tetik"]
    k = _GeciciKural(id=kural_id or 0, sahip_tur=sahip.sahip_tur, hesap_email=None if sahip.yonetici else sahip.hesap,
                     ad=temiz.get("ad") or "", kosullar=temiz["kosullar"], eylemler=temiz["eylemler"])
    kaynak = "ornek"
    if calisma_id:
        c = (
            await db.execute(
                select(OtomasyonCalismalari).where(OtomasyonCalismalari.id == int(calisma_id),
                                                   _sahip_kosulu_calisma(sahip.sahip_tur, None if sahip.yonetici else sahip.hesap))
            )
        ).scalars().first()
        if c is None or c.tur != tetik:
            raise kural.KuralHatasi("calisma_yok", 404)
        b = await baglam_kur(db, c.tur, _json(c.veri, {}), c.olay_hesap, sahip.yonetici)
        if b is None:
            raise kural.KuralHatasi("kayit_yok", 404)
        kaynak = "olay"
    elif baglam is not None:
        b = _baglami_temizle(baglam)
        b.setdefault("olay", {"tur": tetik, "zaman": iso(simdi())})
        if not isinstance(b.get("kisi"), dict):
            b["kisi"] = kural.kisi_sec(tetik, b)
        kaynak = "elle"
    else:
        b = kural.ornek_baglam(tetik, sahip.yonetici, ozel)
    sonuc, ayrinti = kural.kosullari_degerlendir(temiz["kosullar"], b)
    eylemler = _json(temiz["eylemler"], [])
    bilinmeyen: List[str] = []
    cikti = []
    for i, e in enumerate(eylemler):
        for alan in ("konu", "govde", "baslik", "aciklama", "metin"):
            if isinstance(e.get(alan), str):
                bilinmeyen += kural.yer_tutuculari_coz(e[alan], b)[1]
        if not sonuc:
            cikti.append({"sira": i, "tur": e.get("tur"), "durum": "atlanacak", "neden": "kosul_tutmadi"})
            continue
        try:
            r = await eylem_yap(db, k, e, b, kuru=True, ornek=kaynak != "olay")
        except Exception as h:  # noqa: BLE001
            logger.exception("Kuru çalıştırma eylemi hata verdi")
            r = _sonuc("hata", type(h).__name__)
        cikti.append({"sira": i, "tur": e.get("tur"), **r})
    return {
        "kosul_sonucu": sonuc, "kosul_ayrinti": ayrinti, "eylemler": cikti, "baglam": b, "kaynak": kaynak,
        "bilinmeyen_degiskenler": sorted(set(bilinmeyen)),
    }


# ---------------------------------------------------------------------------
# Günlük
# ---------------------------------------------------------------------------
def calisma_sozlugu(c: Any, kural_adi: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": c.id, "kural_id": c.kural_id, "kural": kural_adi, "olay_id": c.olay_id, "tur": c.tur,
        "olay_hesap": c.olay_hesap, "durum": c.durum, "neden": c.neden, "derinlik": int(c.derinlik or 1),
        "kosul_sonucu": c.kosul_sonucu, "kosul_ayrinti": _json(c.kosul_ayrinti, []),
        "eylem_sonuclari": _json(c.eylem_sonuclari, []), "sonraki_eylem": int(c.sonraki_eylem or 0),
        "sonraki_zaman": iso(c.sonraki_zaman) if c.durum == "bekliyor" else None, "veri": _json(c.veri, {}),
        "olusturma": iso(c.created_at), "bitis": iso(c.bitis_at),
    }


_son_temizlik: Dict[str, float] = {"an": 0.0}


async def gunluk(db: AsyncSession, sahip: Sahip, *, kural_id: Optional[int] = None, durum: Optional[str] = None,
                 once: Optional[int] = None, limit: int = 30) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    if time.monotonic() - _son_temizlik["an"] > 3600:
        _son_temizlik["an"] = time.monotonic()
        try:
            await temizle(db)
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception("Otomasyon günlüğü temizlenemedi")
    limit = max(1, min(int(limit or 30), LISTE_SINIRI))
    sorgu = select(OtomasyonCalismalari).where(
        _sahip_kosulu_calisma(sahip.sahip_tur, None if sahip.yonetici else sahip.hesap)
    )
    if kural_id:
        sorgu = sorgu.where(OtomasyonCalismalari.kural_id == int(kural_id))
    if durum:
        sorgu = sorgu.where(OtomasyonCalismalari.durum == str(durum)[:16])
    if once:
        sorgu = sorgu.where(OtomasyonCalismalari.id < int(once))
    liste = list((await db.execute(sorgu.order_by(OtomasyonCalismalari.id.desc()).limit(limit + 1))).scalars().all())
    daha = len(liste) > limit
    liste = liste[:limit]
    adlar: Dict[int, str] = {}
    if liste:
        adlar = dict((await db.execute(
            select(OtomasyonKurallari.id, OtomasyonKurallari.ad).where(OtomasyonKurallari.id.in_({c.kural_id for c in liste}))
        )).all())
    return [calisma_sozlugu(c, adlar.get(c.kural_id)) for c in liste], (liste[-1].id if daha and liste else None)


async def temizle(db: AsyncSession) -> Dict[str, int]:
    """30 günden eski (bitmiş) çalıştırmalar."""
    sinir = simdi() - SAKLAMA_SURESI
    sonuc = await db.execute(
        delete(OtomasyonCalismalari).where(OtomasyonCalismalari.created_at < sinir, OtomasyonCalismalari.durum != "bekliyor")
    )
    await db.commit()
    return {"silinen": int(sonuc.rowcount or 0)}


# ---------------------------------------------------------------------------
# Zamanlı: `fatura.gecikti` üretimi + bekleyenler
# ---------------------------------------------------------------------------
async def fatura_gecikmelerini_uret(db: AsyncSession, bugun: Optional[date] = None) -> Dict[str, Any]:
    """Vadesi geçen açık faturalar için gecikme eşiğine (1/3/7/14/30 gün) ulaşınca `fatura.gecikti`
    olayı — fatura + eşik başına bir kez (belirlenimli olay kimliği). Bu olaya abone kural yoksa hiç çalışmaz."""
    from models.invoices import Invoices
    from services import webhook
    from services.faturalar import KAPALI_DURUMLAR, tarih_coz, tr_bugun

    var = (
        await db.execute(
            select(OtomasyonKurallari.id).where(OtomasyonKurallari.aktif.is_(True), OtomasyonKurallari.tetik == "fatura.gecikti").limit(1)
        )
    ).scalar()
    if var is None:
        return {"uretilen": 0}
    bugun = bugun or tr_bugun()
    faturalar = (
        await db.execute(
            select(Invoices).where(
                or_(Invoices.tur.is_(None), Invoices.tur != "iade"),
                or_(Invoices.status.is_(None), Invoices.status.notin_(KAPALI_DURUMLAR)),
                Invoices.due_date.isnot(None), Invoices.due_date != "",
            ).order_by(Invoices.id.desc()).limit(500)
        )
    ).scalars().all()
    olaylar = []
    for f in faturalar:
        vade = tarih_coz(f.due_date)
        if vade is None or not f.client_email:
            continue
        gecikme = (bugun - vade).days
        esikler = [e for e in kural.GECIKME_ESIKLERI if e <= gecikme]
        if not esikler or gecikme > max(kural.GECIKME_ESIKLERI) + 30:
            continue
        esik = esikler[-1]
        olaylar.append(("fatura.gecikti", f.client_email, {
            "fatura_id": f.id, "no": f.invoice_no, "gecikme_gun": esik, "_olay_id": f"fgecikti-{f.id}-{esik}",
        }, True))
    if not olaylar:
        return {"uretilen": 0}
    once = int((await db.execute(select(func.count(OtomasyonCalismalari.id)))).scalar() or 0)
    await db.run_sync(lambda s: webhook.olaylari_yayinla_sync(s.connection(), olaylar))
    await db.commit()
    sonra = int((await db.execute(select(func.count(OtomasyonCalismalari.id)))).scalar() or 0)
    return {"aday_fatura": len(olaylar), "uretilen": sonra - once}


async def zamanli_gorev(db: AsyncSession, zorla: bool = False) -> Dict[str, Any]:
    gecikme = await fatura_gecikmelerini_uret(db)
    isleme = await bekleyenleri_isle()
    return {"fatura_gecikti": gecikme, **isleme}


__all__ = [
    "MODUL", "IZIN", "onbellegi_temizle", "bekleyenleri_isle", "calisma_isle", "baglam_kur", "eylem_yap",
    "kuru_calistir", "gunluk", "temizle", "fatura_gecikmelerini_uret", "zamanli_gorev", "pazarlama_izni_var_mi",
]
