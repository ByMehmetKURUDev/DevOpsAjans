"""Faz 3U — amaca özel yapay zekâ çağrıları: tek kapı, sunucuda sabit model ve sınırlar.

Neden?
------
`/api/v1/aihub/*` uçları istemcinin gönderdiği her şeyi (model, max_tokens,
sistem istemi) olduğu gibi sağlayıcıya iletiyordu ve kimlik doğrulaması
yoktu: internetteki herkes sitenin anahtarıyla istediği modeli istediği
uzunlukta çalıştırabiliyordu. Artık aihub yalnız yönetici; herkese açık
sayfaların ve panelin ihtiyacı olan işler amaca özel uçlardan geçiyor ve
hepsi buradaki `metin_uret`i çağırıyor:

* Model ve `max_tokens` çağıran SUNUCU kodundan gelir (site ayarı / ortam
  değişkeni / sabit); istemci gönderemez.
* Sağlayıcıya giden tek yer `_saglayici_cagir`. Testler bunu sahteliyor
  (conftest: varsayılan "ağ yok").
* `ENVIRONMENT=test` iken (ve yalnız o zaman; Render'da asla) sabit sahte
  yanıt dönülür — tarayıcı uçtan uca testleri gerçek modele gitmesin
  (2H'deki sahte PageSpeed düzeni; `sahte_ai_acik_mi`).

Günlük sayaç (`ai_gunluk_kullanim`) bütçe kesiciyi ve yönetici kullanım
özetini besliyor; veritabanında tutuluyor (uyuyan sunucu belleği sıfırlar).
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.ai_kullanim import AiGunlukKullanim
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Sitenin bugün kullandığı model (Google'ın OpenAI uyumlu ucu; ön yüzdeki
#: eski `AI_MODELI` sabiti). Ortam değişkeni `AI_VARSAYILAN_MODEL` ezer.
VARSAYILAN_MODEL = "gemini-3.1-flash-lite"
#: Sağlayıcı bu kadar sürede yanıt vermezse vazgeç (Cloudflare vekili ~100 sn).
ZAMAN_ASIMI_SN = 55.0
MODEL_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")

DILLER = ("tr", "en", "de", "ru", "zh", "hi", "ar")
DIL_ADLARI = {
    "tr": "Türkçe (Turkish)",
    "en": "English",
    "de": "Deutsch (German)",
    "ru": "Русский (Russian)",
    "zh": "简体中文 (Simplified Chinese)",
    "hi": "हिन्दी (Hindi)",
    "ar": "العربية (Arabic)",
}

KAPSAMLAR = ("acik", "asistan", "yonetici")


class YapayZekaHatasi(Exception):
    """Uca çevrilecek hata: kod ön yüzde yedi dilde metne çevriliyor."""

    def __init__(self, kod: str, durum: int = 502):
        super().__init__(kod)
        self.kod = kod
        self.durum = durum


@dataclass
class AiYaniti:
    icerik: str
    model: str
    token_giris: Optional[int] = None
    token_cikis: Optional[int] = None
    sahte: bool = False


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def dil_coz(ham: Optional[str]) -> str:
    d = (ham or "tr").strip().lower()[:2]
    return d if d in DILLER else "tr"


def model_gecerli_mi(model: Optional[str]) -> bool:
    return bool(model) and bool(MODEL_DESENI.match(str(model)))


def varsayilan_model() -> str:
    """Ortam değişkeni `AI_VARSAYILAN_MODEL` → sabit."""
    ortam = (os.environ.get("AI_VARSAYILAN_MODEL") or "").strip()
    return ortam if model_gecerli_mi(ortam) else VARSAYILAN_MODEL


def tam_sayi(ham: Any, varsayilan: int, en_az: int, en_cok: int) -> int:
    """Site ayarındaki metni tam sayıya çevirir; geçersizse varsayılan, sınırlara kırpılır."""
    try:
        deger = int(float(str(ham).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return varsayilan
    return max(en_az, min(en_cok, deger))


def tek_satir(metin: Any, sinir: int) -> str:
    """Satır sonu ve kontrol karakterleri olmadan, kırpılmış tek satır."""
    temiz = re.sub(r"[\x00-\x1f\x7f]+", " ", str(metin or ""))
    return re.sub(r"\s+", " ", temiz).strip()[:sinir]


def bugun() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Site ayarları (site_settings tablosu)
# ---------------------------------------------------------------------------
async def ayar_oku(db: AsyncSession, anahtar: str, varsayilan: str = "") -> str:
    try:
        from models.site_settings import Site_settings

        satir = (
            await db.execute(select(Site_settings).where(Site_settings.setting_key == anahtar).limit(1))
        ).scalars().first()
        if satir is not None and str(satir.setting_value or "").strip():
            return str(satir.setting_value).strip()
    except Exception as hata:  # noqa: BLE001 - tablo yoksa varsayılan
        logger.debug("Ayar okunamadı (%s): %s", anahtar, hata)
    return varsayilan


async def ayar_yaz(db: AsyncSession, anahtar: str, deger: str, etiket: Optional[str] = None) -> None:
    """Satır varsa günceller, yoksa ekler (commit çağıranda)."""
    from models.site_settings import Site_settings

    satir = (
        await db.execute(select(Site_settings).where(Site_settings.setting_key == anahtar).limit(1))
    ).scalars().first()
    if satir is None:
        db.add(Site_settings(setting_key=anahtar, setting_value=deger, group_name="yapay_zeka", label=etiket))
    elif satir.setting_value != deger:
        satir.setting_value = deger


# ---------------------------------------------------------------------------
# Sahte yanıt (yalnız ENVIRONMENT=test)
# ---------------------------------------------------------------------------
SAHTE_HATA_ISARETI = "[[sahte-hata]]"


def sahte_ai_acik_mi() -> bool:
    """Sabit sahte yanıt YALNIZ `ENVIRONMENT=test` iken.

    Üretimde ASLA: `uretim_mi()` evet diyorsa (Render'ın `RENDER` değişkeni
    var ya da ENVIRONMENT tanımsız/dev-test-yerel dışı) kapalı. "dev" ya da
    "yerel" de açmıyor. Bu davranış testle bağlı (`test_yapay_zeka.py`).
    """
    from services.site_analizi import uretim_mi

    if uretim_mi():
        return False
    return (os.environ.get("ENVIRONMENT") or "").strip().lower() == "test"


def _son_kullanici(mesajlar: List[Dict[str, Any]]) -> str:
    for m in reversed(mesajlar):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""


def _sahte_yanit(mesajlar: List[Dict[str, Any]], amac: str) -> str:
    son = _son_kullanici(mesajlar)
    if SAHTE_HATA_ISARETI in son:
        raise YapayZekaHatasi("ai_hatasi", 502)
    if amac == "kesif":
        return json.dumps(
            {
                "ozet": "Test ortamı analizi: ihtiyacınız kurumsal bir web sitesi gibi görünüyor.",
                "paketIndeksi": 0,
                "gerekce": "Test ortamında sabit öneri.",
                "adimlar": ["Keşif görüşmesi planlayın", "İçerik listesini hazırlayın"],
            },
            ensure_ascii=False,
        )
    ozet = tek_satir(son, 160)
    return (
        f"**Test yanıtı** ({amac})\n\n"
        f"Sorunuz: {ozet}\n\n"
        "- Birinci öneri\n- İkinci öneri\n\n"
        "```\nornek_kod()\n```"
    )


# ---------------------------------------------------------------------------
# Sağlayıcı çağrısı
# ---------------------------------------------------------------------------
async def _saglayici_cagir(
    mesajlar: List[Dict[str, Any]], model: str, max_tokens: int, temperature: float
) -> Tuple[str, Dict[str, Any]]:
    """Sağlayıcıya giden TEK yer (testlerde sahteleniyor). (metin, kullanım) döndürür."""
    from schemas.aihub import GenTxtRequest
    from services.aihub import AIHubService

    servis = AIHubService()
    if servis.client is None:
        raise YapayZekaHatasi("ai_kapali", 503)
    istek = GenTxtRequest(messages=mesajlar, model=model, stream=False, temperature=temperature, max_tokens=max_tokens)
    yanit = await servis.gentxt(istek)
    return yanit.content or "", dict(yanit.usage or {})


async def metin_uret(
    mesajlar: List[Dict[str, Any]],
    *,
    model: str,
    max_tokens: int,
    temperature: float = 0.5,
    amac: str = "genel",
) -> AiYaniti:
    """Sunucunun kurduğu mesajlarla tek metin yanıtı. Hata → `YapayZekaHatasi`."""
    if not model_gecerli_mi(model):
        model = varsayilan_model()
    if sahte_ai_acik_mi():
        metin = _sahte_yanit(mesajlar, amac)
        giris = sum(len(str(m.get("content") or "")) for m in mesajlar) // 4
        return AiYaniti(icerik=metin, model=model, token_giris=giris, token_cikis=len(metin) // 4, sahte=True)
    try:
        metin, kullanim = await asyncio.wait_for(
            _saglayici_cagir(mesajlar, model, int(max_tokens), float(temperature)), ZAMAN_ASIMI_SN
        )
    except YapayZekaHatasi:
        raise
    except asyncio.TimeoutError:
        logger.warning("Yapay zekâ zaman aşımı (%s, %s)", amac, model)
        raise YapayZekaHatasi("ai_zaman_asimi", 504)
    except ValueError as hata:  # AIHubService: yapılandırma eksik
        logger.warning("Yapay zekâ yapılandırılmamış (%s): %s", amac, hata)
        raise YapayZekaHatasi("ai_kapali", 503)
    except Exception as hata:  # noqa: BLE001 - sağlayıcı ayrıntısı istemciye sızmasın
        logger.error("Yapay zekâ çağrısı başarısız (%s, %s): %s", amac, model, hata)
        raise YapayZekaHatasi("ai_hatasi", 502)
    metin = (metin or "").strip()
    if not metin:
        raise YapayZekaHatasi("ai_bos", 502)

    def _say(ad: str) -> Optional[int]:
        deger = kullanim.get(ad)
        return int(deger) if isinstance(deger, (int, float)) else None

    return AiYaniti(icerik=metin, model=model, token_giris=_say("prompt_tokens"), token_cikis=_say("completion_tokens"))


# ---------------------------------------------------------------------------
# Günlük sayaç
# ---------------------------------------------------------------------------
async def _bugunku_satir(db: AsyncSession, kapsam: str) -> Optional[AiGunlukKullanim]:
    return (
        await db.execute(
            select(AiGunlukKullanim).where(AiGunlukKullanim.gun == bugun()).where(AiGunlukKullanim.kapsam == kapsam)
        )
    ).scalars().first()


async def sayac_artir(db: AsyncSession, kapsam: str, sinir: Optional[int] = None) -> bool:
    """Bugünkü sayaca bir istek ekler.

    `sinir` (>0) verilmiş ve bugünkü istek sayısı ona ulaşmışsa eklemez,
    False döner (bütçe doldu). Artış tek UPDATE ifadesi: eş zamanlı iki
    istek aynı son hakkı iki kez kullanamıyor.
    """
    for _ in range(3):
        satir = await _bugunku_satir(db, kapsam)
        if satir is None:
            if sinir is not None and sinir <= 0:
                return False
            db.add(AiGunlukKullanim(gun=bugun(), kapsam=kapsam, istek=1, token_giris=0, token_cikis=0))
            try:
                await db.commit()
                return True
            except IntegrityError:
                await db.rollback()
                continue
        ifade = update(AiGunlukKullanim).where(AiGunlukKullanim.id == satir.id)
        if sinir is not None:
            ifade = ifade.where(AiGunlukKullanim.istek < sinir)
        sonuc = await db.execute(ifade.values(istek=AiGunlukKullanim.istek + 1).execution_options(synchronize_session=False))
        await db.commit()
        return sonuc.rowcount > 0
    return True


async def token_ekle(db: AsyncSession, kapsam: str, yanit: Optional[AiYaniti]) -> None:
    """Bugünkü satıra jeton sayılarını ekler; hata yutulur (sayaç işi bozmasın)."""
    if yanit is None:
        return
    try:
        satir = await _bugunku_satir(db, kapsam)
        if satir is None:
            return
        await db.execute(
            update(AiGunlukKullanim)
            .where(AiGunlukKullanim.id == satir.id)
            .values(
                token_giris=AiGunlukKullanim.token_giris + int(yanit.token_giris or 0),
                token_cikis=AiGunlukKullanim.token_cikis + int(yanit.token_cikis or 0),
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("Jeton sayacı yazılamadı", exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def gunluk_ozet(db: AsyncSession, gun_sayisi: int) -> List[Dict[str, Any]]:
    """Son `gun_sayisi` günün kapsam başına sayaçları (yeni gün önce)."""
    bas = (datetime.now(timezone.utc).date() - timedelta(days=max(0, gun_sayisi - 1))).isoformat()
    satirlar = (
        await db.execute(
            select(AiGunlukKullanim).where(AiGunlukKullanim.gun >= bas).order_by(AiGunlukKullanim.gun.desc())
        )
    ).scalars().all()
    return [
        {"gun": s.gun, "kapsam": s.kapsam, "istek": s.istek, "token_giris": s.token_giris, "token_cikis": s.token_cikis}
        for s in satirlar
    ]
