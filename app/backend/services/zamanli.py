"""Zamanlanmış görevler — zamanlayıcısı olmayan (uyuyan) sunucu için.

Render'ın ücretsiz sunucusu 15 dakika istek gelmeyince uyuyor; içeride
çalışan bir zamanlayıcı (APScheduler, while döngüsü) uyuyan süreçte çalışmaz.
Bu yüzden dışarıdan tetikleniyor: GitHub Actions her 10 dakikada
`POST /api/v1/zamanli/calistir` çağırıyor (`.github/workflows/zamanli.yml`).
İstek sunucuyu da uyandırıyor.

Uç herkese açık (isteğe bağlı `ZAMANLI_ANAHTAR` başlığı), o yüzden:

* **Küresel kısma:** gerçek iş en çok 5 dakikada bir. Daha sık çağrı
  200 `{"atlandi": true}` alıyor — hata değil, cron'u kırmızıya boyamasın.
* **Kilit:** aynı anda iki çağrı gelirse yalnız biri çalışıyor. Kilit
  `zamanli_calisma` tablosundaki `__genel__` satırına KOŞULLU UPDATE ile
  alınıyor (`... WHERE son_baslangic <= esik AND (kilit_bitis IS NULL OR
  kilit_bitis <= simdi)`); veritabanı aynı satırı iki işleme birden
  güncelletmediği için ikinci çağrının etkilediği satır sayısı 0 oluyor.
  Süreç çalışma ortasında ölürse kilit KILIT_SURESI sonra kendiliğinden
  düşüyor.
* Her görevin kendi sıklığı var (uptime her turda — kontrol başına aralık
  ayrıca; bitiş taraması / hatırlatmalar / kredi günde bir; temizlik
  haftada bir). Görev hata verirse diğerleri yine çalışıyor; hata yalnız
  yönetici panelinde görünüyor, herkese açık yanıtta yok.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from models.site_izleme import ZamanliCalisma
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

GENEL = "__genel__"
EN_AZ_ARALIK = timedelta(minutes=5)
KILIT_SURESI = timedelta(minutes=10)
SONUC_SINIRI = 500
HATA_SINIRI = 300


def simdi() -> datetime:
    return datetime.now(timezone.utc)


def _utc(an: Optional[datetime]) -> Optional[datetime]:
    if an is None:
        return None
    return an.replace(tzinfo=timezone.utc) if an.tzinfo is None else an.astimezone(timezone.utc)


@dataclass(frozen=True)
class Gorev:
    ad: str
    #: Bu kadar süre geçmeden tekrar çalışmıyor (zorla=True değilse).
    siklik: timedelta
    calistir: Callable[[AsyncSession, bool], Awaitable[Dict[str, Any]]]


# ---------------------------------------------------------------------------
# Görevler
# ---------------------------------------------------------------------------
async def _uptime(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.site_izleme import uptime_calistir

    return await uptime_calistir(db, zorla=zorla)


async def _bitis_taramasi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.site_izleme import bitis_taramasi

    return await bitis_taramasi(db, zorla=zorla)


async def _yenileme_hatirlatmalari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.site_izleme import yenileme_hatirlatmalari

    return await yenileme_hatirlatmalari(db)


async def _kredi_sure_dolumlari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.kredi import sure_dolumlarini_isle

    return await sure_dolumlarini_isle(db)


async def _imzali_islem_sureleri(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.imzali_islem import sureleri_isle

    return {"suresi_dolan": await sureleri_isle(db)}


async def _uptime_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.site_izleme import olcum_temizligi

    return await olcum_temizligi(db)


async def _analiz_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.site_analizi_temizlik import eski_analizleri_temizle

    return await eski_analizleri_temizle(db)


async def _sla_kontrolu(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.sla import sla_kontrolu

    return await sla_kontrolu(db)


async def _belge_hatirlatmalari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.dosyalar import belge_hatirlatmalari

    return await belge_hatirlatmalari(db)


async def _aylik_rapor_taslaklari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.aylik_rapor import aylik_taslaklar

    return await aylik_taslaklar(db)


async def _aylik_site_analizi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.aylik_rapor import aylik_analizler

    return await aylik_analizler(db)


#: Kayıt listesi — SIRA ÖNEMLİ: uptime en önce (en zamana duyarlı),
#: ağır/yavaş olabilecek bitiş taraması sonra.
GOREVLER: List[Gorev] = [
    Gorev("uptime", timedelta(0), _uptime),
    Gorev("imzali_islem_sureleri", timedelta(0), _imzali_islem_sureleri),
    # Faz 2C: SLA her turda (ucuz sorgu; uyarı/eskalasyon dakikası kaçmasın).
    Gorev("sla_kontrolu", timedelta(0), _sla_kontrolu),
    Gorev("belge_hatirlatmalari", timedelta(hours=6), _belge_hatirlatmalari),
    Gorev("aylik_rapor_taslaklari", timedelta(hours=6), _aylik_rapor_taslaklari),
    Gorev("bitis_taramasi", timedelta(minutes=30), _bitis_taramasi),
    Gorev("yenileme_hatirlatmalari", timedelta(hours=20), _yenileme_hatirlatmalari),
    Gorev("kredi_sure_dolumlari", timedelta(hours=20), _kredi_sure_dolumlari),
    Gorev("uptime_temizligi", timedelta(hours=20), _uptime_temizligi),
    Gorev("analiz_temizligi", timedelta(days=6, hours=20), _analiz_temizligi),
    # Tur başına en çok bir site analizi (yavaş, dış ağ): en sonda.
    Gorev("aylik_site_analizi", timedelta(hours=1), _aylik_site_analizi),
]
GOREV_ADLARI = [g.ad for g in GOREVLER]


# ---------------------------------------------------------------------------
# Kilit
# ---------------------------------------------------------------------------
async def _satir(db: AsyncSession, ad: str) -> ZamanliCalisma:
    sonuc = await db.execute(select(ZamanliCalisma).where(ZamanliCalisma.gorev == ad))
    satir = sonuc.scalar_one_or_none()
    if satir is not None:
        return satir
    try:
        async with db.begin_nested():
            db.add(ZamanliCalisma(gorev=ad, calisma_sayisi=0))
            await db.flush()
    except IntegrityError:
        pass  # eş zamanlı çağrı açtı
    await db.commit()
    sonuc = await db.execute(select(ZamanliCalisma).where(ZamanliCalisma.gorev == ad))
    return sonuc.scalar_one()


async def kilidi_al(db: AsyncSession, zorla: bool = False) -> Optional[str]:
    """Kilidi alırsa None, alamazsa sebep: 'erken' | 'calisiyor'.

    `zorla` (yalnız yönetici) 5 dakika kuralını atlıyor ama çalışan bir
    turun kilidini ASLA ezmiyor.
    """
    await _satir(db, GENEL)
    an = simdi()
    kosullar = [or_(ZamanliCalisma.kilit_bitis.is_(None), ZamanliCalisma.kilit_bitis <= an)]
    if not zorla:
        kosullar.append(
            or_(ZamanliCalisma.son_baslangic.is_(None), ZamanliCalisma.son_baslangic <= an - EN_AZ_ARALIK)
        )
    sonuc = await db.execute(
        update(ZamanliCalisma)
        .where(ZamanliCalisma.gorev == GENEL, and_(*kosullar))
        .values(son_baslangic=an, kilit_bitis=an + KILIT_SURESI)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if int(sonuc.rowcount or 0) == 1:
        return None
    satir = (await db.execute(select(ZamanliCalisma).where(ZamanliCalisma.gorev == GENEL))).scalar_one()
    await db.refresh(satir)
    kilit = _utc(satir.kilit_bitis)
    return "calisiyor" if kilit is not None and kilit > an else "erken"


async def _kilidi_birak(db: AsyncSession, sure_ms: int, ozet: Dict[str, Any]) -> None:
    await db.execute(
        update(ZamanliCalisma)
        .where(ZamanliCalisma.gorev == GENEL)
        .values(
            kilit_bitis=None,
            son_calisma=simdi(),
            sure_ms=sure_ms,
            sonuc=json.dumps(ozet, ensure_ascii=False, default=str)[:SONUC_SINIRI],
            calisma_sayisi=ZamanliCalisma.calisma_sayisi + 1,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Çalıştırıcı
# ---------------------------------------------------------------------------
async def calistir(db: AsyncSession, zorla: bool = False) -> Dict[str, Any]:
    """Kilidi alıp zamanı gelen görevleri sırayla çalıştırır."""
    from services import denetim

    sebep = await kilidi_al(db, zorla=zorla)
    if sebep is not None:
        return {"atlandi": True, "sebep": sebep}

    # Bu isteğin geri kalanındaki yazımlar denetimde "sistem" görünsün.
    try:
        denetim.aktor_ata(None, "sistem")
    except Exception:  # noqa: BLE001
        pass

    basla = time.perf_counter()
    sonuclar: List[Dict[str, Any]] = []
    try:
        for gorev in GOREVLER:
            satir = await _satir(db, gorev.ad)
            son = _utc(satir.son_calisma)
            if not zorla and son is not None and gorev.siklik and simdi() - son < gorev.siklik:
                sonuclar.append({"gorev": gorev.ad, "calisti": False})
                continue
            g_basla = time.perf_counter()
            hata: Optional[str] = None
            ozet: Dict[str, Any] = {}
            try:
                ozet = await gorev.calistir(db, zorla) or {}
            except Exception as exc:  # noqa: BLE001 - bir görev diğerlerini durdurmasın
                logger.exception("Zamanlı görev hata verdi: %s", gorev.ad)
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                hata = f"{type(exc).__name__}: {exc}"[:HATA_SINIRI]
            sure = int((time.perf_counter() - g_basla) * 1000)
            await db.execute(
                update(ZamanliCalisma)
                .where(ZamanliCalisma.gorev == gorev.ad)
                .values(
                    son_baslangic=simdi() - timedelta(milliseconds=sure),
                    son_calisma=simdi(),
                    sure_ms=sure,
                    sonuc=json.dumps(ozet, ensure_ascii=False, default=str)[:SONUC_SINIRI],
                    hata=hata,
                    calisma_sayisi=ZamanliCalisma.calisma_sayisi + 1,
                )
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            sonuclar.append({"gorev": gorev.ad, "calisti": True, "sure_ms": sure, "basarili": hata is None, "ozet": ozet})
    finally:
        toplam = int((time.perf_counter() - basla) * 1000)
        await _kilidi_birak(
            db, toplam, {"calisan": [s["gorev"] for s in sonuclar if s.get("calisti")]}
        )
    return {"atlandi": False, "sure_ms": toplam, "gorevler": sonuclar}


def acik_yanit(sonuc: Dict[str, Any]) -> Dict[str, Any]:
    """Herkese açık uçtaki yanıt: görev adları + sayılar; hata metni YOK."""
    if sonuc.get("atlandi"):
        return {"atlandi": True, "sebep": sonuc.get("sebep")}
    return {
        "atlandi": False,
        "sure_ms": sonuc.get("sure_ms"),
        "gorevler": [
            {k: v for k, v in g.items() if k in ("gorev", "calisti", "sure_ms", "basarili")}
            for g in sonuc.get("gorevler", [])
        ],
    }


async def durum_listesi(db: AsyncSession) -> Dict[str, Any]:
    """Yönetici kartı: her görevin son çalışması, süresi, sonucu, hatası."""
    satirlar = {
        s.gorev: s for s in (await db.execute(select(ZamanliCalisma))).scalars().all()
    }

    def sozluk(s: Optional[ZamanliCalisma]) -> Dict[str, Any]:
        if s is None:
            return {"son_calisma": None, "sure_ms": None, "sonuc": None, "hata": None, "calisma_sayisi": 0}
        try:
            sonuc = json.loads(s.sonuc) if s.sonuc else None
        except ValueError:
            sonuc = None
        return {
            "son_calisma": (_utc(s.son_calisma).isoformat() if s.son_calisma else None),  # type: ignore[union-attr]
            "sure_ms": s.sure_ms,
            "sonuc": sonuc,
            "hata": s.hata,
            "calisma_sayisi": int(s.calisma_sayisi or 0),
        }

    genel = satirlar.get(GENEL)
    kilit = _utc(genel.kilit_bitis) if genel else None
    return {
        "genel": {**sozluk(genel), "calisiyor": bool(kilit and kilit > simdi())},
        "gorevler": [
            {"gorev": g.ad, "siklik_dk": int(g.siklik.total_seconds() // 60), **sozluk(satirlar.get(g.ad))}
            for g in GOREVLER
        ],
        "anahtar_tanimli": _anahtar() is not None,
    }


def _anahtar() -> Optional[str]:
    import os

    deger = (os.environ.get("ZAMANLI_ANAHTAR") or "").strip()
    return deger or None


def anahtar_gecerli_mi(gelen: Optional[str]) -> bool:
    """`ZAMANLI_ANAHTAR` tanımlı değilse herkes; tanımlıysa başlık eşleşmeli."""
    import hmac

    beklenen = _anahtar()
    if beklenen is None:
        return True
    return bool(gelen) and hmac.compare_digest(str(gelen).encode(), beklenen.encode())
