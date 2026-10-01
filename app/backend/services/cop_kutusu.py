"""Faz 2D — çöp kutusu: silinen kaydı yakala, geri al, süresi dolunca kalıcı sil.

Yakalama — neden flush kancası?
-------------------------------
Silmeler tek bir kapıdan geçmiyor: üretilmiş entity servisleri
(`services/<tablo>.py` → `db.delete(obj)`), görev/duyuru/dosya/bilgi bankası
router'ları da doğrudan `db.delete` çağırıyor. Hepsinin ortak noktası
SQLAlchemy'nin iş birimi (denetim kaydıyla aynı gerekçe, bkz.
`services/denetim.py`). İki olay kullanılıyor:

* `before_flush`: `session.deleted` içindeki izinli tablo nesnelerinin
  bütün sütunları okunuyor. Satır hâlâ veritabanında olduğu için, commit
  sonrası süresi dolmuş (expired) alanlar burada güvenle yükleniyor; sahip
  e-postası gereken yerde üst kayda bakılarak bulunuyor.
* `after_flush`: DELETE gerçekten çalıştıysa kopyalar aynı işlemde bir
  SAVEPOINT'e yazılıyor. Asıl işlem geri alınırsa kopya da gidiyor; kopya
  yazılamazsa yalnız SAVEPOINT geri alınıyor, silme etkilenmiyor.

Bekleyen kopyalar flush'a özgü `flush_context.attributes` içinde duruyor —
başarısız bir flush'ın artığı sonraki flush'a sızmıyor. `grup` ise işlem
(transaction) boyunca aynı: autoflush bir silme işini birkaç flush'a bölse
de (görev + kontrol listesi) hepsi birlikte geri geliyor.

Kapsam
------
Yalnız `IZINLI_TABLOLAR`. Oturum, denetim, çöp kutusu, OIDC durumu gibi
teknik tablolar asla yakalanmıyor. `task_checklist` / `task_dependencies`
yalnız görevle birlikte silindiklerinde yakalanıyor (görev geri gelince
kontrol listesi de gelsin); tek bir kontrol maddesinin silinmesi çöpe düşmüyor.

`delete(Model).where(...)` gibi toplu (Core) silmeler iş biriminden geçmediği
için yakalanmıyor. Faz 2D itibarıyla izinli tablolarda kullanıcı işlemiyle
yapılan toplu silme yok (toplu silmeler: OIDC durumları, uptime ölçümleri,
site analizleri, dosya içerikleri, denetim/oturum/çöp saklama temizliği).

Dosyalar
--------
Dosyanın içeriği (`dosya_icerikleri` ya da S3 nesnesi) JSON'a konmuyor.
Dosya silinirken kayıt çöpe düştüyse içerik SİLİNMİYOR; çöp kaydı kalıcı
silinince (elle ya da saklama süresi dolunca) içerik de siliniyor. Böylece
geri alınan dosya içeriğiyle birlikte geliyor. Çöpe düşmediyse (kanca
hatası) içerik eskisi gibi hemen siliniyor — bkz. `routers/dosyalar.py`.
"""

import json
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models.cop_kutusu import CopKutusu
from sqlalchemy import LargeBinary, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VARSAYILAN_GUN = 30
AYAR_ANAHTARI = "cop_kutusu_gun"

#: tablo → {"sahip": sütun} ya da {"sahip_sorgu": SQL (:v), "sahip_alan": veri anahtarı}.
#: "sira": geri almada ebeveyn → çocuk sırası (küçük önce).
IZINLI_TABLOLAR: Dict[str, Dict[str, Any]] = {
    "projects": {"sahip": "client_email", "sira": 10},
    "support_tickets": {"sahip": "client_email", "sira": 10},
    "invoices": {"sahip": "client_email", "sira": 10},
    "client_sites": {"sahip": "client_email", "sira": 10},
    "blog_posts": {"sira": 10},
    "content_posts": {"sira": 10},
    "marketplace_items": {"sira": 10},
    "bilgi_makaleleri": {"sira": 10},
    "duyurular": {"sira": 10},
    "hazir_cevaplar": {"sira": 10},
    # Faz 3K: sitedeki Kaynaklar listesi (etiket: Türkçe başlık).
    "kaynaklar": {"sira": 10},
    # Faz 3C: CRM adayı (aktiviteleriyle birlikte geri gelir) ve form tanımı.
    "crm_adaylar": {"sira": 10},
    "crm_formlar": {"sira": 10},
    "crm_aktiviteler": {"sira": 20, "ebeveyn": "crm_adaylar"},
    # Faz 3Z: zaman kaydı (yalnız taslak/reddedilen silinebiliyor) ve proje
    # şablonu. Sahip YOK: iç kayıt — müşterinin "Silinenler"inde görünmez.
    "zaman_kayitlari": {"sira": 10},
    "proje_sablonlari": {"sira": 10},
    # Faz 3T: teklif (kabul edilmişse silinmez), sözleşme (imzalıysa silinmez)
    # ve şablon. İmzalı sözleşme hiç silinemediği için imza görseli/IP özeti
    # çöp kutusuna kopyalanmıyor.
    "teklifler": {"sahip": "hesap_email", "sira": 10},
    "sozlesmeler": {"sahip": "hesap_email", "sira": 10},
    "sozlesme_sablonlari": {"sira": 10},
    # Faz 4Q: QR kodu / kısa link ve logosu (birlikte silinir, birlikte geri gelir).
    # Ajansın kendi kaydında sahip boş (yalnız yönetici görür). Taramalar silinmiyor:
    # geri alınan QR analitiğiyle birlikte döner.
    "dinamik_qr": {"sahip": "hesap_email", "sira": 10},
    "dinamik_qr_logolari": {
        "sahip_sorgu": "SELECT hesap_email FROM dinamik_qr WHERE id = :v",
        "sahip_alan": "qr_id",
        "sira": 20,
        "ebeveyn": "dinamik_qr",
    },
    "files": {"sahip": "client_email", "sira": 20},
    "project_tasks": {
        "sahip_sorgu": "SELECT client_email FROM projects WHERE id = :v",
        "sahip_alan": "proje_id",
        "sira": 20,
    },
    "ticket_replies": {
        "sahip_sorgu": "SELECT client_email FROM support_tickets WHERE id = :v",
        "sahip_alan": "ticket_id",
        "sira": 20,
    },
    "task_checklist": {
        "sahip_sorgu": "SELECT p.client_email FROM project_tasks g JOIN projects p ON p.id = g.proje_id WHERE g.id = :v",
        "sahip_alan": "gorev_id",
        "sira": 30,
        "ebeveyn": "project_tasks",
    },
    "task_dependencies": {
        "sahip_sorgu": "SELECT p.client_email FROM project_tasks g JOIN projects p ON p.id = g.proje_id WHERE g.id = :v",
        "sahip_alan": "gorev_id",
        "sira": 30,
        "ebeveyn": "project_tasks",
    },
    # Faz 2G: konuşmayı yalnız yönetici siler; mesajları ve okunma satırları
    # onunla birlikte yakalanıyor (tek mesaj silme yumuşak, çöpe düşmüyor).
    "konusmalar": {"sahip": "hesap_email", "sira": 10},
    "konusma_mesajlari": {
        "sahip_sorgu": "SELECT hesap_email FROM konusmalar WHERE id = :v",
        "sahip_alan": "konusma_id",
        "sira": 20,
        "ebeveyn": "konusmalar",
    },
    "konusma_okunma": {
        "sahip_sorgu": "SELECT hesap_email FROM konusmalar WHERE id = :v",
        "sahip_alan": "konusma_id",
        "sira": 30,
        "ebeveyn": "konusmalar",
    },
}

#: Yalnız ebeveyniyle birlikte yakalanan (listede ayrı satır olarak görünmeyen) tablolar.
COCUK_TABLOLAR = frozenset(t for t, a in IZINLI_TABLOLAR.items() if a.get("ebeveyn"))

#: Listede gösterilecek kısa ad için bakılan alanlar (ilk dolu olan).
ETIKET_ALANLARI = (
    "invoice_no", "title", "baslik", "subject", "ad", "name", "slug", "adres",
    "metin", "mesaj", "client_email",
)
ETIKET_SINIRI = 120


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Değer ↔ JSON
# ---------------------------------------------------------------------------
def _jsonla(deger: Any) -> Any:
    """Tam değer (denetimdeki gibi kesilmiyor): geri alma için birebir gerekli."""
    if deger is None or isinstance(deger, (bool, int, str)):
        return deger
    if isinstance(deger, float):
        return deger if deger == deger and deger not in (float("inf"), float("-inf")) else None
    if isinstance(deger, Decimal):
        return str(deger)
    if isinstance(deger, (datetime, date, time)):
        return deger.isoformat()
    if isinstance(deger, (dict, list)):
        return deger
    return str(deger)


def _geri_cevir(tur: Any, deger: Any) -> Any:
    """JSON'daki değeri sütun türüne geri çevirir."""
    if deger is None:
        return None
    try:
        python_turu = tur.python_type
    except (NotImplementedError, AttributeError):
        return deger
    try:
        if python_turu is datetime and isinstance(deger, str):
            return datetime.fromisoformat(deger)
        if python_turu is date and isinstance(deger, str):
            return date.fromisoformat(deger[:10])
        if python_turu is time and isinstance(deger, str):
            return time.fromisoformat(deger)
        if python_turu is Decimal:
            return Decimal(str(deger))
        if python_turu is float and isinstance(deger, (int, str)):
            return float(deger)
        if python_turu is int and isinstance(deger, str) and deger.lstrip("-").isdigit():
            return int(deger)
        if python_turu is bool and isinstance(deger, int):
            return bool(deger)
    except (TypeError, ValueError):
        return deger
    return deger


def _tablo_adi(obj: Any) -> str:
    try:
        return getattr(inspect(obj).mapper.local_table, "name", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def _satir_verisi(obj: Any) -> Tuple[Dict[str, Any], str]:
    """(veri, kayit_id). Süresi dolmuş alanlar burada yükleniyor (before_flush)."""
    durum = inspect(obj)
    mapper = durum.mapper
    veri: Dict[str, Any] = {}
    for ozellik in mapper.column_attrs:
        sutun = ozellik.columns[0]
        if isinstance(sutun.type, LargeBinary):
            continue  # ikili içerik JSON'a konmuyor
        try:
            deger = getattr(obj, ozellik.key)
        except Exception:  # noqa: BLE001 - yüklenemeyen alan: yoksay
            deger = durum.dict.get(ozellik.key)
        veri[ozellik.key] = _jsonla(deger)
    pk = [mapper.get_property_by_column(k).key for k in mapper.primary_key]
    kimlik = ",".join(str(veri.get(k)) for k in pk if veri.get(k) is not None)
    return veri, kimlik[:64]


def _etiket(veri: Dict[str, Any]) -> Optional[str]:
    for alan in ETIKET_ALANLARI:
        deger = veri.get(alan)
        if deger not in (None, ""):
            metin = " ".join(str(deger).split())
            return metin if len(metin) <= ETIKET_SINIRI else metin[: ETIKET_SINIRI - 1] + "…"
    return None


def _sahip(session: Session, tablo: str, veri: Dict[str, Any]) -> Optional[str]:
    ayar = IZINLI_TABLOLAR.get(tablo) or {}
    deger: Any = None
    if ayar.get("sahip"):
        deger = veri.get(ayar["sahip"])
    elif ayar.get("sahip_sorgu"):
        anahtar = veri.get(ayar.get("sahip_alan") or "")
        if anahtar is not None:
            try:
                with session.no_autoflush:
                    deger = session.execute(text(ayar["sahip_sorgu"]), {"v": anahtar}).scalar()
            except Exception:  # noqa: BLE001
                logger.debug("Sahip bulunamadı: %s", tablo, exc_info=True)
    deger = (str(deger).strip().lower() if deger else "") or None
    return deger


# ---------------------------------------------------------------------------
# Oturum olayları
# ---------------------------------------------------------------------------
BEKLEYEN = "cop_kutusu_bekleyen"
ISLEM_GRUBU = "cop_kutusu_grup"
ISLEM_TABLOLARI = "cop_kutusu_tablolar"


def _islem_bitti(session: Session, *_args) -> None:
    session.info.pop(ISLEM_GRUBU, None)
    session.info.pop(ISLEM_TABLOLARI, None)


event.listen(Session, "after_commit", _islem_bitti)
event.listen(Session, "after_rollback", _islem_bitti)


@event.listens_for(Session, "before_flush")
def _flush_oncesi(session: Session, flush_context, _nesneler) -> None:
    if session.info.get("cop_kutusu_kapali") or not session.deleted:
        return
    try:
        adaylar = [(obj, _tablo_adi(obj)) for obj in list(session.deleted)]
        adaylar = [(o, t) for o, t in adaylar if t in IZINLI_TABLOLAR]
        if not adaylar:
            return
        # Çocuk tablo yalnız ebeveyni aynı işlemde (bu flush ya da aynı
        # transaction'ın önceki flush'ı) silindiyse yakalanıyor.
        ebeveynler = {t for _, t in adaylar} | set(session.info.get(ISLEM_TABLOLARI) or ())
        adaylar = [
            (o, t) for o, t in adaylar
            if t not in COCUK_TABLOLAR or IZINLI_TABLOLAR[t]["ebeveyn"] in ebeveynler
        ]
        if not adaylar:
            return

        from services.denetim import _gecerli_baglam

        baglam = _gecerli_baglam()
        # Grup: aynı işlemde (commit'e kadar) silinenler — autoflush silmeyi
        # birkaç flush'a bölse de görev ile kontrol listesi aynı grupta kalır.
        grup = session.info.get(ISLEM_GRUBU) or str(uuid.uuid4())
        session.info[ISLEM_GRUBU] = grup
        session.info.setdefault(ISLEM_TABLOLARI, set()).update(t for _, t in adaylar)
        bekleyen = []
        for obj, tablo in adaylar:
            veri, kimlik = _satir_verisi(obj)
            bekleyen.append(
                (
                    obj,
                    {
                        "tablo": tablo,
                        "kayit_id": kimlik or None,
                        "veri": json.dumps(veri, ensure_ascii=False, default=str),
                        "grup": grup,
                        "silen_email": baglam.aktor_eposta,
                        "silen_rol": baglam.aktor_rol or "sistem",
                        "sahip_email": _sahip(session, tablo, veri),
                        "etiket": _etiket(veri),
                        "geri_alindi": False,
                    },
                )
            )
        flush_context.attributes[BEKLEYEN] = bekleyen
    except Exception:  # noqa: BLE001 - çöp kutusu asıl silmeyi ASLA bozmamalı
        logger.exception("Çöp kutusu: silinen kayıt okunamadı")


def _ekleme_sorgusu():
    """Ayrı fonksiyon: testler yazımı bilerek patlatabilsin."""
    return CopKutusu.__table__.insert()


@event.listens_for(Session, "after_flush")
def _flush_sonrasi(session: Session, flush_context) -> None:
    bekleyen = flush_context.attributes.pop(BEKLEYEN, None)
    if not bekleyen:
        return
    silinenler = {id(o) for o in session.deleted}
    an = simdi()
    satirlar = [dict(s, silinme=an) for o, s in bekleyen if id(o) in silinenler]
    if not satirlar:
        return
    try:
        baglanti = session.connection()
        with baglanti.begin_nested():
            baglanti.execute(_ekleme_sorgusu(), satirlar)
    except Exception:  # noqa: BLE001
        logger.exception("Çöp kutusu kaydı yazılamadı (%d satır)", len(satirlar))


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def model_bul(tablo: str) -> Any:
    """Tablo adından ORM modelini bulur (model modülü import edilmiş olmalı)."""
    from core.database import Base

    for mapper in Base.registry.mappers:
        if getattr(mapper.local_table, "name", None) == tablo:
            return mapper.class_
    return None


async def cop_kutusunda_mi(db: AsyncSession, tablo: str, kayit_id: Any) -> bool:
    """Bu kayıt (bu işlemde ya da önce) çöpe düştü mü — geri alınmamış hâlde."""
    sayi = (
        await db.execute(
            select(func.count(CopKutusu.id)).where(
                CopKutusu.tablo == tablo,
                CopKutusu.kayit_id == str(kayit_id),
                CopKutusu.geri_alindi.is_(False),
            )
        )
    ).scalar()
    return bool(sayi)


async def saklama_gunu(db: AsyncSession) -> int:
    from models.site_settings import Site_settings

    try:
        satir = (
            await db.execute(select(Site_settings.setting_value).where(Site_settings.setting_key == AYAR_ANAHTARI))
        ).first()
        if satir and satir[0] not in (None, ""):
            return max(1, min(365, int(str(satir[0]).strip())))
    except Exception:  # noqa: BLE001
        logger.debug("cop_kutusu_gun okunamadı", exc_info=True)
    return VARSAYILAN_GUN


def veri_coz(kayit: CopKutusu) -> Dict[str, Any]:
    try:
        veri = json.loads(kayit.veri or "{}")
        return veri if isinstance(veri, dict) else {}
    except ValueError:
        return {}


class CopHatasi(Exception):
    def __init__(self, kod: int, anahtar: str, ek: Optional[Dict[str, Any]] = None):
        self.kod = kod
        self.anahtar = anahtar
        self.ek = ek or {}
        super().__init__(anahtar)


# ---------------------------------------------------------------------------
# Geri alma
# ---------------------------------------------------------------------------
async def geri_al(
    db: AsyncSession,
    kayit: CopKutusu,
    *,
    geri_alan: Optional[str],
    request: Any = None,
    yalniz_sahip: Optional[str] = None,
    yalniz_silen: Optional[str] = None,
) -> Dict[str, Any]:
    """Kaydı ve aynı gruptaki (henüz geri alınmamış) kayıtları geri getirir.

    Ebeveyn → çocuk sırasıyla (IZINLI_TABLOLAR["sira"]) aynı kimlikle ekler.
    Kimliklerden biri doluysa HİÇBİRİ eklenmez: 409 `cakisma`.
    `yalniz_sahip`: müşteri geri alırken grup yalnız kendi sildiği, kendi
    kayıtlarıyla sınırlanıyor. Faz 2E: `yalniz_silen` (ekip üyesi) verilirse
    "kendi sildiği" o kişi, "kendi kaydı" hesap (`yalniz_sahip`).
    """
    from services.denetim import denetim_yaz

    if kayit.geri_alindi:
        raise CopHatasi(409, "zaten_geri_alindi")
    sorgu = select(CopKutusu).where(CopKutusu.grup == kayit.grup, CopKutusu.geri_alindi.is_(False))
    if yalniz_sahip:
        sorgu = sorgu.where(
            CopKutusu.sahip_email == yalniz_sahip, CopKutusu.silen_email == (yalniz_silen or yalniz_sahip)
        )
    grup = list((await db.execute(sorgu)).scalars().all())
    if kayit.id not in {g.id for g in grup}:
        grup.append(kayit)
    grup.sort(key=lambda g: (IZINLI_TABLOLAR.get(g.tablo, {}).get("sira", 50), g.id))

    # 1) Denetle: model var mı, kimlik boş mu?
    hazirlik = []
    for g in grup:
        model = model_bul(g.tablo)
        if model is None:
            raise CopHatasi(409, "tablo_yok", {"tablo": g.tablo})
        veri = veri_coz(g)
        mapper = inspect(model)
        pk_ozellikleri = [mapper.get_property_by_column(k) for k in mapper.primary_key]
        kosullar = []
        for oz in pk_ozellikleri:
            deger = _geri_cevir(oz.columns[0].type, veri.get(oz.key))
            if deger is None:
                raise CopHatasi(409, "kimlik_yok", {"tablo": g.tablo})
            kosullar.append(getattr(model, oz.key) == deger)
        var_mi = (await db.execute(select(func.count()).select_from(model).where(*kosullar))).scalar()
        if var_mi:
            raise CopHatasi(409, "cakisma", {"tablo": g.tablo, "kayit_id": g.kayit_id})
        hazirlik.append((g, model, mapper, veri))

    # 2) Ekle (aynı kimlikle)
    for g, model, mapper, veri in hazirlik:
        obj = model()
        for oz in mapper.column_attrs:
            if oz.key in veri:
                setattr(obj, oz.key, _geri_cevir(oz.columns[0].type, veri[oz.key]))
        db.add(obj)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise CopHatasi(409, "cakisma", {"neden": "benzersiz_alan"}) from exc

    # 3) Postgres: sabit kimlikle eklemeden sonra dizi geride kalmasın.
    if (await db.connection()).dialect.name == "postgresql":
        for tablo in sorted({g.tablo for g, *_ in hazirlik}):
            try:
                async with db.begin_nested():
                    await db.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{tablo}', 'id'), "
                            f"(SELECT COALESCE(MAX(id), 1) FROM {tablo}))"
                        )
                    )
            except Exception:  # noqa: BLE001
                logger.warning("Dizi ileri alınamadı: %s", tablo)

    # 4) Tabloya özel toparlama
    for g, model, mapper, veri in hazirlik:
        if g.tablo == "files":
            await _dosya_guncelini_duzelt(db, model, veri)

    an = simdi()
    for g, *_ in hazirlik:
        g.geri_alindi = True
        g.geri_alan = geri_alan
        g.geri_alinma = an
        await denetim_yaz(
            db,
            request=request,
            islem="diger",
            tablo=g.tablo,
            kayit_id=g.kayit_id,
            ozet=f"Çöp kutusundan geri alındı · {g.etiket or g.kayit_id}",
        )
    await db.commit()
    return {
        "geri_alinan": [{"id": g.id, "tablo": g.tablo, "kayit_id": g.kayit_id} for g, *_ in hazirlik],
    }


async def _dosya_guncelini_duzelt(db: AsyncSession, model: Any, veri: Dict[str, Any]) -> None:
    """Aynı müşteri + klasör + ad için en yüksek sürüm `guncel` olsun (tek)."""
    try:
        satirlar = (
            await db.execute(
                select(model)
                .where(
                    model.client_email == veri.get("client_email"),
                    model.klasor == veri.get("klasor"),
                    model.ad == veri.get("ad"),
                )
                .order_by(model.surum.desc(), model.id.desc())
            )
        ).scalars().all()
        for i, s in enumerate(satirlar):
            s.guncel = i == 0
        await db.flush()
    except Exception:  # noqa: BLE001
        logger.exception("Geri alınan dosyanın sürüm bayrağı düzeltilemedi")


# ---------------------------------------------------------------------------
# Kalıcı silme ve saklama temizliği
# ---------------------------------------------------------------------------
async def _icerigi_sil(db: AsyncSession, kayit: CopKutusu) -> None:
    """Çöpteki dosyanın bekletilen içeriğini siler (geri alınmamışsa)."""
    if kayit.tablo != "files" or kayit.geri_alindi:
        return
    veri = veri_coz(kayit)
    anahtar = veri.get("depolama_anahtari")
    if not anahtar:
        return
    try:
        model = model_bul("files")
        if model is not None:
            hala_var = (
                await db.execute(select(func.count()).select_from(model).where(model.depolama_anahtari == anahtar))
            ).scalar()
            if hala_var:
                return
        from services import dosya_deposu

        await dosya_deposu.sil(db, veri.get("depo") or "veritabani", anahtar)
    except Exception:  # noqa: BLE001
        logger.exception("Çöpteki dosyanın içeriği silinemedi")


async def kalici_sil(db: AsyncSession, kayit: CopKutusu, *, request: Any = None) -> None:
    from services.denetim import denetim_yaz

    await _icerigi_sil(db, kayit)
    await denetim_yaz(
        db,
        request=request,
        islem="sil",
        tablo="cop_kutusu",
        kayit_id=kayit.id,
        ozet=f"Çöp kutusundan kalıcı silindi · {kayit.tablo} #{kayit.kayit_id} · {kayit.etiket or ''}",
    )
    await db.delete(kayit)
    await db.commit()


async def suresi_dolanlari_temizle(db: AsyncSession) -> Dict[str, Any]:
    """Saklama süresi (`cop_kutusu_gun`, varsayılan 30) dolan kayıtları kalıcı siler."""
    gun = await saklama_gunu(db)
    esik = simdi() - timedelta(days=gun)
    kayitlar = (
        await db.execute(select(CopKutusu).where(CopKutusu.silinme < esik).limit(1000))
    ).scalars().all()
    for k in kayitlar:
        await _icerigi_sil(db, k)
        await db.delete(k)
    await db.commit()
    return {"silinen": len(kayitlar), "gun": gun}
