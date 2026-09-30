"""İmzalı işlem bağlantıları: girişsiz, tek tıkla müşteri kararı.

Akış
----
1. Yönetici bir hedef için (teklif, proje teslimi) bağlantı üretir:
   `olustur` rastgele bir jeton üretir (`secrets.token_urlsafe(24)`, 192 bit),
   veritabanına YALNIZ sha256 özetini yazar ve ham jetonu çağırana bir kez
   döndürür. Bağlantı `SITE_PUBLIC_URL/islem/<jeton>`.
2. Müşteri bağlantıyı açar (`coz`) — oturum gerekmiyor; jetonun kendisi
   yetki. Özet sayfada gösterilir.
3. Müşteri karar verir (`kullan`): kabul/red ya da onay/revizyon. Karar
   hedef kayda işlenir, satır "kullanıldı" olur.

Neden jeton özeti?
------------------
Bağlantı bir yetki belgesi: elinde olan karar verebiliyor. Veritabanında
düz dursaydı, bir yedek ya da okuma yetkili bir sızıntı bütün bekleyen
kararları devralmaya yeterdi. Özetten jeton geri üretilemiyor. 192 bitlik
rastgele jeton için tuzsuz sha256 yeterli (sözlük saldırısı anlamsız).

Yarış koşulu
------------
"Kullanıldı" işaretlemesi tek bir koşullu UPDATE:

    UPDATE signed_actions SET durum='kullanildi', ...
     WHERE id=:id AND durum='bekliyor' AND son_kullanma > :simdi

Aynı anda iki istek gelirse veritabanı satırı birine veriyor; ikincisinin
UPDATE'i 0 satır etkiliyor → 409. Hedef kayda etki (teklif durumu, proje
olayı) AYNI işlemde yazılıyor: etki patlarsa kullanım da geri alınıyor,
bağlantı yeniden denenebilir kalıyor. Bildirimler işlem onaylandıktan
sonra gidiyor (`dispatch` kendi commit'ini yapıyor).

SQLite notu: okuma işlemi açıkken yazmaya yükselmek, başka bir yazar
beklerken "database is locked" ile hemen düşüyor. Bu yüzden ön
denetimlerden sonra okuma işlemi kapatılıyor ve UPDATE yeni işlemin İLK
ifadesi oluyor; böylece bekleme (busy timeout) devreye giriyor.

Denetim kaydı
-------------
Hedefe yapılan değişiklikler 1B'nin `after_flush` olayıyla kendiliğinden
kaydediliyor. Oturum olmadığı için aktör normalde "anonim" olurdu;
`denetim.aktor_ata` ile bağlantının alıcısı yazılıyor. Kullanım UPDATE'i
Core ifadesi olduğundan iş biriminden geçmiyor; onun için `denetim_yaz`
ile ayrı bir "onay" satırı düşülüyor.
"""

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.signed_actions import SignedActions
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VARSAYILAN_GUN = 14
EN_AZ_GUN = 1
EN_COK_GUN = 90
NOT_SINIRI = 2000
DURUMLAR = ("bekliyor", "kullanildi", "iptal", "suresi_doldu")
SONUCLAR = ("kabul", "red", "onay", "revizyon", "goruntulendi")


@dataclass(frozen=True)
class TurTanimi:
    hedef_tablo: str
    #: Bu türde müşterinin seçebileceği sonuçlar.
    sonuclar: Tuple[str, ...]
    #: Not (gerekçe/revizyon metni) zorunlu olan sonuçlar.
    not_zorunlu: Tuple[str, ...] = ()
    tek_kullanimlik: bool = True


#: Yeni tür eklemek: buraya bir satır + `_etkiyi_uygula` içinde bir dal +
#: `hedef_ozeti_kur` içinde başlık/ayrıntı.
TURLER: Dict[str, TurTanimi] = {
    "teklif_kabul": TurTanimi("pricing_inquiries", ("kabul", "red")),
    "teslimat_onay": TurTanimi("projects", ("onay", "revizyon"), not_zorunlu=("revizyon",)),
    # 1A'nın /rapor/<jeton> akışı kendi jetonunu kullanıyor; bu tür yalnız
    # genel desen için tanımlı (ör. "raporu gördüm" onayı). Etkisi yok.
    "rapor_goruntule": TurTanimi("site_analyses", ("goruntulendi",), tek_kullanimlik=False),
}


class IslemHatasi(Exception):
    """Ön yüzün yedi dilde kendi metnini kurduğu hata: `kod` + HTTP durumu."""

    def __init__(self, durum: int, kod: str):
        super().__init__(kod)
        self.durum = durum
        self.kod = kod


@dataclass
class KullanimSonucu:
    kayit: SignedActions
    #: İşlem onaylandıktan sonra gönderilecek bildirimler (dispatch argümanları).
    bildirimler: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini düşürüyor; kayıtların hepsi UTC yazılıyor."""
    if an is None:
        return None
    return an if an.tzinfo else an.replace(tzinfo=timezone.utc)


def jeton_ozeti(jeton: str) -> str:
    return hashlib.sha256((jeton or "").encode("utf-8")).hexdigest()


def eposta_duzelt(eposta: Optional[str]) -> str:
    return (eposta or "").strip().lower()


def eposta_maskele(eposta: Optional[str]) -> str:
    """`ahmet@alan.com` → `a***@alan.com`. Bağlantı elden ele gidebilir."""
    eposta = eposta_duzelt(eposta)
    if "@" not in eposta:
        return "***"
    yerel, alan = eposta.split("@", 1)
    return f"{yerel[:1]}***@{alan}"


def ayrinti(kayit: SignedActions) -> Dict[str, Any]:
    if not kayit.ayrinti_json:
        return {}
    try:
        deger = json.loads(kayit.ayrinti_json)
        return deger if isinstance(deger, dict) else {}
    except (TypeError, ValueError):
        return {}


def gecerli_durum(kayit: SignedActions, simdi: Optional[datetime] = None) -> str:
    """Yazılmış durum + süre: süresi geçmiş "bekliyor" → "suresi_doldu"."""
    simdi = simdi or _simdi()
    if kayit.durum == "bekliyor" and (_utc(kayit.son_kullanma) or simdi) <= simdi:
        return "suresi_doldu"
    return kayit.durum


def gun_duzelt(gun: Optional[int]) -> int:
    if gun is None:
        return VARSAYILAN_GUN
    try:
        gun = int(gun)
    except (TypeError, ValueError):
        raise IslemHatasi(400, "gun_gecersiz")
    if gun < EN_AZ_GUN or gun > EN_COK_GUN:
        raise IslemHatasi(400, "gun_gecersiz")
    return gun


def _not_duzelt(not_: Optional[str]) -> Optional[str]:
    temiz = (not_ or "").strip()
    if len(temiz) > NOT_SINIRI:
        raise IslemHatasi(400, "not_uzun")
    return temiz or None


# ---------------------------------------------------------------------------
# Oluşturma
# ---------------------------------------------------------------------------


async def olustur(
    db: AsyncSession,
    tur: str,
    hedef: Tuple[str, int],
    alici: str,
    baslik: str,
    ayrinti_: Optional[Dict[str, Any]] = None,
    gun: Optional[int] = None,
    *,
    olusturan: Optional[str] = None,
) -> Tuple[str, SignedActions]:
    """Yeni bağlantı üretir. Ham jetonu (bir kez) ve kaydı döndürür.

    Ham jeton veritabanına yazılmıyor; kaybedilirse `yenile` ile yenisi
    üretiliyor.
    """
    tanim = TURLER.get(tur)
    if tanim is None:
        raise IslemHatasi(400, "tur_gecersiz")
    hedef_tablo, hedef_id = hedef
    if hedef_tablo != tanim.hedef_tablo:
        raise IslemHatasi(400, "hedef_gecersiz")
    alici = eposta_duzelt(alici)
    if "@" not in alici or len(alici) > 254:
        raise IslemHatasi(400, "alici_gecersiz")
    gun = gun_duzelt(gun)

    jeton = secrets.token_urlsafe(24)
    kayit = SignedActions(
        jeton_ozeti=jeton_ozeti(jeton),
        tur=tur,
        hedef_tablo=hedef_tablo,
        hedef_id=int(hedef_id),
        alici_eposta=alici,
        baslik=(baslik or "").strip()[:300] or tur,
        ayrinti_json=json.dumps(ayrinti_ or {}, ensure_ascii=False, default=str),
        son_kullanma=_simdi() + timedelta(days=gun),
        tek_kullanimlik=tanim.tek_kullanimlik,
        durum="bekliyor",
        olusturan_eposta=eposta_duzelt(olusturan) or None,
        created_at=_simdi(),
    )
    db.add(kayit)
    await db.commit()
    await db.refresh(kayit)
    return jeton, kayit


async def _proje_asama_etiketi(asama: Optional[str]) -> str:
    from routers.project_events import STAGE_LABELS

    return STAGE_LABELS.get(asama or "", asama or "—")


async def hedef_ozeti_kur(
    db: AsyncSession,
    tur: str,
    hedef_id: int,
    *,
    not_: Optional[str] = None,
    baglanti: Optional[str] = None,
    ilerlet: bool = True,
) -> Tuple[str, str, Dict[str, Any], Optional[str]]:
    """Hedef kayıttan (tablo, başlık, ayrıntı, varsayılan alıcı) kurar.

    Ayrıntıya yalnız müşterinin görmesinde sakınca olmayan alanlar giriyor:
    bağlantı elden ele gidebilir.
    """
    tanim = TURLER.get(tur)
    if tanim is None:
        raise IslemHatasi(400, "tur_gecersiz")
    not_ = _not_duzelt(not_)

    if tur == "teklif_kabul":
        from models.invoices import Invoices
        from models.pricing import Ai_pm_tiers, Pricing_inquiries, Pricing_profiles, Pricing_scales

        teklif = (
            await db.execute(select(Pricing_inquiries).where(Pricing_inquiries.id == hedef_id))
        ).scalar_one_or_none()
        if teklif is None:
            raise IslemHatasi(404, "hedef_yok")

        async def _ad(model, kod):
            if not kod:
                return None
            satir = (await db.execute(select(model).where(model.kod == kod))).scalars().first()
            return satir.ad if satir is not None else kod

        try:
            eklentiler = json.loads(teklif.addon_ids or "[]")
        except (TypeError, ValueError):
            eklentiler = []
        kredi = None
        if teklif.period == "kullandikca_ode":
            for e in eklentiler:
                if isinstance(e, str) and e.startswith("kredi_paketi:"):
                    kredi = e.split(":", 1)[1]
            eklentiler = []
        fatura_no = None
        if teklif.invoice_id:
            fatura = (await db.execute(select(Invoices).where(Invoices.id == teklif.invoice_id))).scalar_one_or_none()
            fatura_no = fatura.invoice_no if fatura is not None else None

        paket = await _ad(Pricing_scales, teklif.scale_kod)
        profil = await _ad(Pricing_profiles, teklif.profile_kod)
        ai_pm = await _ad(Ai_pm_tiers, teklif.ai_pm_tier_kod)
        tutar = round(float(teklif.hesaplanan_tutar or 0), 2)
        ozet = paket or (f"AI vs PM {ai_pm}" if ai_pm else (f"{kredi} kredi" if kredi else "Teklif"))
        baslik = f"#{teklif.id} · {ozet} · {tutar:g} USD"
        ayr = {
            "teklif_id": teklif.id,
            "tutar": tutar,
            "para_birimi": "USD",
            "paket": paket,
            "profil": profil,
            "donem": teklif.period,
            "eklentiler": [str(e) for e in eklentiler if e],
            "ai_pm": ai_pm,
            "kredi": kredi,
            "fatura_no": fatura_no,
            "not": not_,
        }
        return "pricing_inquiries", baslik, ayr, eposta_duzelt(teklif.musteri_eposta) or None

    if tur == "teslimat_onay":
        from models.projects import Projects

        proje = (await db.execute(select(Projects).where(Projects.id == hedef_id))).scalar_one_or_none()
        if proje is None:
            raise IslemHatasi(404, "hedef_yok")
        etiket = await _proje_asama_etiketi(proje.stage)
        baslik = f"{proje.title} · {etiket}"
        ayr = {
            "proje_id": proje.id,
            "proje": proje.title,
            "asama": proje.stage,
            "asama_etiketi": etiket,
            "not": not_,
            "baglanti": (baglanti or "").strip()[:500] or proje.project_url or None,
            "ilerlet": bool(ilerlet),
        }
        return "projects", baslik, ayr, eposta_duzelt(proje.client_email) or None

    # rapor_goruntule
    from models.site_analyses import Site_analyses

    analiz = (await db.execute(select(Site_analyses).where(Site_analyses.id == hedef_id))).scalar_one_or_none()
    if analiz is None:
        raise IslemHatasi(404, "hedef_yok")
    baslik = f"{analiz.alan_adi} · {analiz.puan if analiz.puan is not None else '—'}/100"
    ayr = {"analiz_id": analiz.id, "alan_adi": analiz.alan_adi, "puan": analiz.puan, "not": not_}
    return "site_analyses", baslik, ayr, eposta_duzelt(getattr(analiz, "eposta", None)) or None


# ---------------------------------------------------------------------------
# Çözme ve kullanma
# ---------------------------------------------------------------------------


async def _sureyi_isle(db: AsyncSession, kayit: SignedActions) -> SignedActions:
    """Süresi geçmiş bekleyen kaydı "suresi_doldu" yazar (istekle tetiklenir)."""
    if kayit.durum != "bekliyor" or gecerli_durum(kayit) != "suresi_doldu":
        return kayit
    await db.execute(
        update(SignedActions)
        .where(SignedActions.id == kayit.id, SignedActions.durum == "bekliyor")
        .values(durum="suresi_doldu")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    kayit.durum = "suresi_doldu"
    return kayit


async def coz(db: AsyncSession, jeton: str) -> Optional[SignedActions]:
    """Jetondan kaydı bulur; yoksa None. Süresi geçmişse durumu işler."""
    if not jeton or len(jeton) > 200:
        return None
    kayit = (
        await db.execute(select(SignedActions).where(SignedActions.jeton_ozeti == jeton_ozeti(jeton)))
    ).scalar_one_or_none()
    if kayit is None:
        return None
    return await _sureyi_isle(db, kayit)


def _on_denetim(kayit: SignedActions, sonuc: str, not_: Optional[str]) -> Optional[str]:
    tanim = TURLER.get(kayit.tur)
    if tanim is None or sonuc not in tanim.sonuclar:
        raise IslemHatasi(400, "gecersiz_sonuc")
    temiz = _not_duzelt(not_)
    if sonuc in tanim.not_zorunlu and not temiz:
        raise IslemHatasi(400, "not_gerekli")
    return temiz


def _durum_hatasi(kayit: SignedActions) -> IslemHatasi:
    durum = gecerli_durum(kayit)
    if durum == "kullanildi":
        return IslemHatasi(409, "kullanildi")
    if durum == "iptal":
        return IslemHatasi(410, "iptal")
    if durum == "suresi_doldu":
        return IslemHatasi(410, "suresi_doldu")
    return IslemHatasi(409, "kullanildi")


async def kullan(
    db: AsyncSession,
    jeton: str,
    sonuc: str,
    not_: Optional[str] = None,
    *,
    ip_ozeti: Optional[str] = None,
) -> KullanimSonucu:
    """Bağlantıyı kullanır (girişsiz sayfa)."""
    kayit = await coz(db, jeton)
    if kayit is None:
        raise IslemHatasi(404, "bulunamadi")
    return await _kullan_kayit(db, kayit, sonuc, not_, ip_ozeti=ip_ozeti)


async def kullan_id(
    db: AsyncSession,
    islem_id: int,
    eposta: str,
    sonuc: str,
    not_: Optional[str] = None,
    *,
    ip_ozeti: Optional[str] = None,
) -> KullanimSonucu:
    """Aynı işlemi müşteri panelinden, oturumla yapar. Yalnız kendi kaydı."""
    kayit = (
        await db.execute(
            select(SignedActions).where(
                SignedActions.id == islem_id,
                SignedActions.alici_eposta == eposta_duzelt(eposta),
            )
        )
    ).scalar_one_or_none()
    if kayit is None:
        raise IslemHatasi(404, "bulunamadi")
    kayit = await _sureyi_isle(db, kayit)
    return await _kullan_kayit(db, kayit, sonuc, not_, ip_ozeti=ip_ozeti)


async def _kullan_kayit(
    db: AsyncSession,
    kayit: SignedActions,
    sonuc: str,
    not_: Optional[str],
    *,
    ip_ozeti: Optional[str],
) -> KullanimSonucu:
    from services import denetim

    sonuc = (sonuc or "").strip().lower()
    temiz_not = _on_denetim(kayit, sonuc, not_)
    if gecerli_durum(kayit) != "bekliyor":
        raise _durum_hatasi(kayit)

    # Okuma işlemini kapat: UPDATE yeni işlemin ilk ifadesi olsun (SQLite
    # kilidi bekleyebilsin; bkz. modül notu).
    await db.commit()

    # Bundan sonraki yazımların denetim aktörü bağlantının alıcısı.
    denetim.aktor_ata(kayit.alici_eposta, "client")

    simdi = _simdi()
    kayit_id = kayit.id
    yeni_durum = "kullanildi" if kayit.tek_kullanimlik else "bekliyor"
    try:
        sonuc_satiri = await db.execute(
            update(SignedActions)
            .where(
                SignedActions.id == kayit_id,
                SignedActions.durum == "bekliyor",
                SignedActions.son_kullanma > simdi,
            )
            .values(
                durum=yeni_durum,
                sonuc=sonuc,
                sonuc_notu=temiz_not,
                kullanildi_at=simdi,
                kullanan_ip_ozeti=ip_ozeti,
            )
            .execution_options(synchronize_session=False)
        )
        etkilenen = sonuc_satiri.rowcount
    except OperationalError:
        # SQLite: başka bir yazar kilidi tutuyor ve beklemek mümkün değil.
        logger.warning("İmzalı işlem kilidi alınamadı: id=%s", kayit_id)
        await db.rollback()
        etkilenen = 0

    if etkilenen != 1:
        await db.rollback()  # geri alma oturumdaki nesneleri bayatlatıyor
        taze = (
            await db.execute(
                select(SignedActions)
                .where(SignedActions.id == kayit_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        raise _durum_hatasi(taze) if gecerli_durum(taze) != "bekliyor" else IslemHatasi(409, "mesgul")

    try:
        bildirimler = await _etkiyi_uygula(db, kayit, sonuc, temiz_not)
        await denetim.denetim_yaz(
            db,
            aktor={"email": kayit.alici_eposta, "rol": "client"},
            islem="onay",
            tablo="signed_actions",
            kayit_id=kayit.id,
            ozet=f"{kayit.tur}: {sonuc} · {kayit.baslik}",
            once={"durum": "bekliyor", "sonuc": None},
            sonra={"durum": yeni_durum, "sonuc": sonuc},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(kayit)
    return KullanimSonucu(kayit=kayit, bildirimler=bildirimler)


# ---------------------------------------------------------------------------
# Türe göre etki
# ---------------------------------------------------------------------------


async def _etkiyi_uygula(
    db: AsyncSession, kayit: SignedActions, sonuc: str, not_: Optional[str]
) -> List[Dict[str, Any]]:
    """Kararı hedef kayda işler (commit ETMEZ). Bildirim listesini döndürür."""
    if kayit.tur == "teklif_kabul":
        return await _teklif_etkisi(db, kayit, sonuc, not_)
    if kayit.tur == "teslimat_onay":
        return await _teslimat_etkisi(db, kayit, sonuc, not_)
    return []


def _yonetici_bildirimi(baslik: str, govde: str, ref_type: str, ref_id: Optional[int]) -> Dict[str, Any]:
    return {
        "event_type": "imzali_islem_sonuc",
        "title": baslik[:250],
        "body": govde,
        "yoneticiye": True,
        "link": "/admin",
        "ref_type": ref_type,
        "ref_id": ref_id,
    }


async def _teklif_etkisi(db: AsyncSession, kayit: SignedActions, sonuc: str, not_: Optional[str]):
    from models.pricing import Pricing_inquiries

    teklif = (
        await db.execute(select(Pricing_inquiries).where(Pricing_inquiries.id == kayit.hedef_id))
    ).scalar_one_or_none()
    if teklif is None:
        raise IslemHatasi(404, "hedef_yok")
    teklif.durum = "kabul" if sonuc == "kabul" else "red"
    teklif.durum_notu = not_ if sonuc == "red" else None
    teklif.durum_at = _simdi()
    await db.flush()

    tutar = f"{float(teklif.hesaplanan_tutar or 0):g} USD"
    if sonuc == "kabul":
        baslik = f"Teklif kabul edildi: #{teklif.id} ({tutar}) — {kayit.alici_eposta}"
        govde = f"{kayit.baslik}\nMüşteri teklifi imzalı bağlantıyla kabul etti."
    else:
        baslik = f"Teklif reddedildi: #{teklif.id} ({tutar}) — {kayit.alici_eposta}"
        govde = f"{kayit.baslik}\nGerekçe: {not_ or '—'}"
    return [_yonetici_bildirimi(baslik, govde, "pricing_inquiry", teklif.id)]


async def _teslimat_etkisi(db: AsyncSession, kayit: SignedActions, sonuc: str, not_: Optional[str]):
    from models.project_events import Project_events
    from models.projects import Projects
    from models.support_tickets import Support_tickets
    from routers.project_events import STAGE_LABELS, STAGES

    proje = (await db.execute(select(Projects).where(Projects.id == kayit.hedef_id))).scalar_one_or_none()
    if proje is None:
        raise IslemHatasi(404, "hedef_yok")
    ayr = ayrinti(kayit)
    asama = ayr.get("asama") or proje.stage
    etiket = STAGE_LABELS.get(asama or "", asama or "—")
    simdi = datetime.now()
    aktor_adi = proje.client_name or kayit.alici_eposta
    bildirimler: List[Dict[str, Any]] = []

    if sonuc == "onay":
        db.add(
            Project_events(
                project_id=proje.id,
                event_type="client_approval",
                title=f"Müşteri onayladı: {etiket}",
                body=not_,
                to_value=asama,
                actor_name=aktor_adi,
                actor_email=kayit.alici_eposta,
                visible_to_client="1",
                created_at=simdi,
            )
        )
        ilerledi = None
        # Aşama ilerletme: bağlantı üretildiğinde proje hangi aşamadaysa ve
        # hâlâ oradaysa, onay bir sonraki aşamaya geçiriyor (yönetici panelde
        # elle ilerletmiş olabilir; o zaman dokunulmuyor).
        if ayr.get("ilerlet") and asama in STAGES and proje.stage == asama:
            sira = STAGES.index(asama)
            if sira + 1 < len(STAGES):
                sonraki = STAGES[sira + 1]
                proje.stage = sonraki
                proje.progress = round((sira + 2) / len(STAGES) * 100)
                proje.updated_at = simdi
                ilerledi = STAGE_LABELS[sonraki]
                db.add(
                    Project_events(
                        project_id=proje.id,
                        event_type="stage_change",
                        title=f"Aşama: {etiket} → {ilerledi}",
                        body="Müşteri onayıyla ilerledi.",
                        from_value=asama,
                        to_value=sonraki,
                        actor_name=aktor_adi,
                        actor_email=kayit.alici_eposta,
                        visible_to_client="1",
                        created_at=simdi,
                    )
                )
        await db.flush()
        govde = f"{proje.title} — {etiket} teslimi müşteri tarafından onaylandı."
        if ilerledi:
            govde += f"\nProje {ilerledi} aşamasına geçti."
        if not_:
            govde += f"\nNot: {not_}"
        bildirimler.append(
            _yonetici_bildirimi(f"Teslim onaylandı: {proje.title} ({etiket})", govde, "project", proje.id)
        )
        return bildirimler

    # revizyon
    db.add(
        Project_events(
            project_id=proje.id,
            event_type="revision_request",
            title=f"Revizyon istendi: {etiket}",
            body=not_,
            to_value=asama,
            actor_name=aktor_adi,
            actor_email=kayit.alici_eposta,
            visible_to_client="1",
            created_at=simdi,
        )
    )
    talep = Support_tickets(
        client_name=proje.client_name,
        client_email=kayit.alici_eposta,
        subject=f"Revizyon isteği — {proje.title} ({etiket})"[:200],
        message=not_ or "",
        status="open",
        priority="normal",
        hizmet="genel",
        project_id=proje.id,
        kaynak="islem",
        son_mesaj_at=simdi,
        created_at=simdi,
    )
    db.add(talep)
    await db.flush()
    # Faz 2B — revizyon isteği projede "revizyon" etiketli bir görev açıyor;
    # bu göreve girilen saatler aylık revizyon sayacına düşüyor.
    try:
        from services.gorevler import revizyon_gorevi_ac

        async with db.begin_nested():
            await revizyon_gorevi_ac(
                db,
                proje_id=proje.id,
                baslik=f"Revizyon: {etiket}",
                aciklama=not_,
                imzali_islem_id=kayit.id,
            )
    except Exception:  # noqa: BLE001 - görev açılamasa da karar kaydedilsin
        logger.exception("Revizyon görevi açılamadı: proje %s", proje.id)
    bildirimler.append(
        _yonetici_bildirimi(
            f"Revizyon istendi: {proje.title} ({etiket})",
            f"{kayit.alici_eposta} revizyon istedi:\n{not_ or ''}\nDestek talebi #{talep.id} açıldı.",
            "project",
            proje.id,
        )
    )
    return bildirimler


async def bildirimleri_gonder(db: AsyncSession, bildirimler: List[Dict[str, Any]]) -> None:
    """İşlem onaylandıktan sonra çağrılır. Hata fırlatmaz."""
    if not bildirimler:
        return
    try:
        from services.notify import admin_recipients, dispatch

        yoneticiler = None
        for b in bildirimler:
            alicilar = b.get("alicilar") or []
            if b.get("yoneticiye"):
                if yoneticiler is None:
                    yoneticiler = await admin_recipients(db)
                alicilar = list(alicilar) + list(yoneticiler)
            await dispatch(
                db,
                event_type=b["event_type"],
                title=b["title"],
                body=b.get("body") or "",
                recipients=alicilar,
                link=b.get("link"),
                ref_type=b.get("ref_type"),
                ref_id=b.get("ref_id"),
            )
    except Exception:  # noqa: BLE001 - karar kaydedildi; bildirim düşse de olur
        logger.exception("İmzalı işlem bildirimi gönderilemedi")


# ---------------------------------------------------------------------------
# Yönetim: iptal, yenile, liste
# ---------------------------------------------------------------------------


async def iptal_et(db: AsyncSession, islem_id: int) -> SignedActions:
    kayit = (await db.execute(select(SignedActions).where(SignedActions.id == islem_id))).scalar_one_or_none()
    if kayit is None:
        raise IslemHatasi(404, "bulunamadi")
    sonuc = await db.execute(
        update(SignedActions)
        .where(SignedActions.id == islem_id, SignedActions.durum == "bekliyor")
        .values(durum="iptal")
        .execution_options(synchronize_session=False)
    )
    if sonuc.rowcount != 1:
        await db.rollback()
        await db.refresh(kayit)
        raise IslemHatasi(409, f"durum_{kayit.durum}")
    await db.commit()
    await db.refresh(kayit)
    return kayit


async def yenile(
    db: AsyncSession, islem_id: int, *, gun: Optional[int] = None, olusturan: Optional[str] = None
) -> Tuple[str, SignedActions, SignedActions]:
    """Eskisini (bekliyorsa) iptal edip aynı içerikle yenisini üretir.

    Kullanılmış bağlantı yenilenmiyor (karar zaten verildi). Süresi dolmuş
    ya da iptal edilmiş olan yenilenebiliyor — asıl kullanım bu.
    """
    eski = (await db.execute(select(SignedActions).where(SignedActions.id == islem_id))).scalar_one_or_none()
    if eski is None:
        raise IslemHatasi(404, "bulunamadi")
    if eski.durum == "kullanildi" and eski.tek_kullanimlik:
        raise IslemHatasi(409, "durum_kullanildi")
    if gun is None:
        sure = (_utc(eski.son_kullanma) or _simdi()) - (_utc(eski.created_at) or _simdi())
        gun = max(EN_AZ_GUN, min(EN_COK_GUN, round(sure.total_seconds() / 86400) or VARSAYILAN_GUN))
    gun = gun_duzelt(gun)
    if eski.durum == "bekliyor":
        await db.execute(
            update(SignedActions)
            .where(SignedActions.id == eski.id, SignedActions.durum == "bekliyor")
            .values(durum="iptal")
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        await db.refresh(eski)
    jeton, yeni = await olustur(
        db,
        eski.tur,
        (eski.hedef_tablo, eski.hedef_id),
        eski.alici_eposta,
        eski.baslik,
        ayrinti(eski),
        gun,
        olusturan=olusturan,
    )
    return jeton, eski, yeni


async def sureleri_isle(db: AsyncSession) -> int:
    """Süresi geçmiş bütün bekleyenleri "suresi_doldu" yazar (liste açılınca)."""
    sonuc = await db.execute(
        update(SignedActions)
        .where(SignedActions.durum == "bekliyor", SignedActions.son_kullanma <= _simdi())
        .values(durum="suresi_doldu")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(sonuc.rowcount or 0)
