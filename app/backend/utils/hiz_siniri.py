"""Hız sınırları: bellek içi (`HizSiniri`) ve veritabanı destekli (`KaliciHizSiniri`).

İlk kez imzalı işlem bağlantılarında (`routers/imzali_islemler.py`) yazıldı;
Faz 2D'de giriş uçları (`/auth/login`, `/auth/callback`,
`/auth/token/exchange`) da kullanınca buraya taşındı.

Bellek içi sayaç (`HizSiniri`, kayan pencere) süreç belleğinde duruyor:
Render'ın ücretsiz sunucusu uyuyup kalkınca ya da yeniden yayında sıfırlanıyor.
Panelin sık çağrılan iç uçları (oturum açmış kişinin yazmaları, görüntülenme
sayımının tekrar süzgeci) için bu yeterli ve ucuz. Anahtar genellikle IP'nin
tuzlu özeti (`utils.istemci_ip.ip_ozeti`) — ham IP bellekte bile tutulmuyor.

Faz 7H — kalıcı sayaç (`KaliciHizSiniri`)
-----------------------------------------
Kötüye kullanıma açık HERKESE AÇIK uçlar (giriş, formlar, bülten aboneliği,
yapay zekâ sohbeti, randevu / etkinlik kaydı, imzalı bağlantı denemeleri…)
sayacı `hiz_sayaclari` tablosunda tutuyor: sunucu uyanınca sayaç sıfırlanmıyor.

* Sabit pencere, anahtarın İLK isteğiyle başlıyor; pencere dolunca sayaç
  sıfırdan başlıyor (ayrıntı `models/hiz_sayaclari.py`).
* Artırma tek atomik `INSERT … ON CONFLICT DO UPDATE … WHERE … RETURNING`
  (Postgres ve SQLite aynı ifade). Sınıra ulaşmış satır artmıyor; satır
  dönmezse istek reddediliyor.
* Sayaç isteğin kendi oturumunda DEĞİL, kısa ve ayrı bir işlemde yazılıyor:
  uç sonradan hata verip geri alınsa da deneme sayılmış oluyor.
* Veritabanı hatası ya da yavaşlığında (`ZAMAN_ASIMI_SN`) aynı sınırlayıcının
  bellek içi yedeğine düşülüyor: istek asla 500 olmuyor.
* Anahtar sha256(sınırlayıcı adı | anahtar); çağıranlar anahtara ham IP değil
  `utils.istemci_ip.ip_ozeti` (tuzlu özet) ya da kayıt kimliği veriyor.

Kullanım: `await izin_ver((sinirlayici, anahtar), ...)` — hepsi izin verirse
True. Sırayla denetler, ilk reddedende durur (sonrakiler sayılmaz). Bellek
içi `HizSiniri` da verilebilir (testler sınırlayıcıyı onunla değiştiriyor).
"""

import asyncio
import hashlib
import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Tuple, Union

logger = logging.getLogger(__name__)

#: Veritabanı bu kadar saniyede yanıt vermezse bellek içi yedeğe düşülür.
ZAMAN_ASIMI_SN = 2.0
#: "Veritabanına yazılamadı" uyarısı en çok bu aralıkla bir kez (saniye).
UYARI_ARALIGI_SN = 600


class HizSiniri:
    """`pencere` saniye içinde anahtar başına en çok `sinir` istek."""

    def __init__(self, sinir: int, pencere: float = 60.0):
        self.sinir = sinir
        self.pencere = pencere
        self._kayitlar: Dict[str, Deque[float]] = {}
        self._kilit = threading.Lock()

    def izin_var_mi(self, anahtar: str) -> bool:
        simdi = time.monotonic()
        with self._kilit:
            kuyruk = self._kayitlar.setdefault(anahtar, deque())
            while kuyruk and simdi - kuyruk[0] > self.pencere:
                kuyruk.popleft()
            if len(kuyruk) >= self.sinir:
                return False
            kuyruk.append(simdi)
            # Bellek büyümesin: çok anahtar birikince boşları at.
            if len(self._kayitlar) > 5000:
                for k in [k for k, v in self._kayitlar.items() if not v]:
                    self._kayitlar.pop(k, None)
            return True

    def temizle(self) -> None:
        with self._kilit:
            self._kayitlar.clear()


# ---------------------------------------------------------------------------
# Faz 7H — veritabanı destekli sayaç
# ---------------------------------------------------------------------------
# Tablo uygulama kurulurken oluşsun (model kaydı router importuyla oluyor; bu
# modülü herkese açık uçların router'ları içe aktarıyor).
from models.hiz_sayaclari import HizSayaclari  # noqa: E402

_son_uyari: Dict[str, float] = {"an": -1e9}
_durum: Dict[str, int] = {"yedek": 0}


def simdi_ms() -> int:
    """Duvar saati (ms). Testler pencerenin dolmasını taklit etmek için değiştiriyor."""
    return int(time.time() * 1000)


class KaliciHizSiniri:
    """Herkese açık uçlar için `hiz_sayaclari` tablosunda tutulan sabit pencere sayacı.

    `ad` sınırlayıcıyı tanımlar (anahtar özetine girer; iki sınırlayıcının sayaçları
    karışmasın). Bellek içi `HizSiniri` ile aynı `sinir` / `pencere` alanları var;
    `temizle()` (testler) yeni bir sayaç kuşağına geçer ve yedeği boşaltır.
    Bilerek `izin_var_mi` YOK: eşzamansız sayaç yanlışlıkla eşzamanlı çağrılmasın
    (`await izin_ver(...)` kullanılır).
    """

    def __init__(self, ad: str, sinir: int, pencere: float = 60.0):
        self.ad = ad
        self.sinir = sinir
        self.pencere = pencere
        self._yedek = HizSiniri(sinir, pencere)
        self._kusak = 0

    def ozet(self, anahtar: str) -> str:
        return hashlib.sha256(f"{self.ad}|{self._kusak}|{anahtar}".encode("utf-8")).hexdigest()

    def yedek_izin(self, anahtar: str) -> bool:
        return self._yedek.izin_var_mi(anahtar)

    def temizle(self) -> None:
        self._kusak += 1
        self._yedek.temizle()


Sinirlayici = Union[HizSiniri, KaliciHizSiniri]


def _upsert_ifadesi(dialekt: str, sinirlayici: KaliciHizSiniri, anahtar: str, an: int):
    from sqlalchemy import case, or_

    if dialekt == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    t = HizSayaclari.__table__
    pencere_ms = max(1, int(sinirlayici.pencere * 1000))
    dolmus = t.c.bitis <= an
    return (
        insert(t)
        .values(anahtar=sinirlayici.ozet(anahtar), pencere_bas=an, bitis=an + pencere_ms, sayac=1)
        .on_conflict_do_update(
            index_elements=[t.c.anahtar],
            set_={
                "sayac": case((dolmus, 1), else_=t.c.sayac + 1),
                "pencere_bas": case((dolmus, an), else_=t.c.pencere_bas),
                "bitis": case((dolmus, an + pencere_ms), else_=t.c.bitis),
            },
            # Sınıra ulaşmış (pencere sürerken) satır güncellenmez → RETURNING boş → ret.
            where=or_(dolmus, t.c.sayac < int(sinirlayici.sinir)),
        )
        .returning(t.c.sayac)
    )


async def _veritabaninda(denemeler, bellekte_sayilan: set) -> bool:
    from core.database import db_manager

    motor = db_manager.engine
    if motor is None:
        raise RuntimeError("veritabanı hazır değil")
    an = simdi_ms()
    async with motor.begin() as baglanti:
        for i, (sinirlayici, anahtar) in enumerate(denemeler):
            if isinstance(sinirlayici, KaliciHizSiniri):
                satir = (await baglanti.execute(_upsert_ifadesi(motor.dialect.name, sinirlayici, anahtar, an))).first()
                if satir is None:
                    return False
            else:
                bellekte_sayilan.add(i)
                if not sinirlayici.izin_var_mi(anahtar):
                    return False
    return True


def _seyrek_uyar(hata: BaseException) -> None:
    an = time.monotonic()
    if an - _son_uyari["an"] >= UYARI_ARALIGI_SN:
        _son_uyari["an"] = an
        logger.warning("Kalıcı hız sayacı yazılamadı (%s: %s); bellek içi sayaca düşüldü.", type(hata).__name__, hata)


async def izin_ver(*denemeler: Tuple[Sinirlayici, str]) -> bool:
    """Verilen (sınırlayıcı, anahtar) çiftlerinin HEPSİ izin verirse True.

    Kalıcı sınırlayıcılar tek kısa işlemde veritabanında sayılır; veritabanı hata verir
    ya da `ZAMAN_ASIMI_SN` içinde yanıt vermezse aynı sınırlar bellekte uygulanır.
    """
    temiz = [(s, str(a or "anonim")) for s, a in denemeler]
    if not any(isinstance(s, KaliciHizSiniri) for s, _ in temiz):
        return all(s.izin_var_mi(a) for s, a in temiz)
    bellekte_sayilan: set = set()
    try:
        return await asyncio.wait_for(_veritabaninda(temiz, bellekte_sayilan), timeout=ZAMAN_ASIMI_SN)
    except asyncio.CancelledError:
        raise
    except Exception as hata:  # noqa: BLE001 - sayaç yazılamadı diye istek düşmesin
        _durum["yedek"] += 1
        _seyrek_uyar(hata)
        # Veritabanı işlemi geri alındı: kalıcıların hepsi bellek yedeğinde sayılır; bellek
        # içi sınırlayıcılardan zaten sayılmış olanlar ikinci kez sayılmaz.
        for i, (s, a) in enumerate(temiz):
            if isinstance(s, KaliciHizSiniri):
                izin = s.yedek_izin(a)
            elif i in bellekte_sayilan:
                continue
            else:
                izin = s.izin_var_mi(a)
            if not izin:
                return False
        return True


async def suresi_gecenleri_sil(db: Any, pay_sn: int = 3600) -> int:
    """Penceresi `pay_sn`den daha önce bitmiş sayaçlar (zamanlı `saklama_temizligi`)."""
    from sqlalchemy import delete

    sonuc = await db.execute(delete(HizSayaclari).where(HizSayaclari.bitis < simdi_ms() - pay_sn * 1000))
    await db.commit()
    return int(sonuc.rowcount or 0)


def yedek_sayisi() -> int:
    """Süreç açıldığından beri veritabanı yerine bellekle karar verilen istek sayısı (testler / tanı)."""
    return _durum["yedek"]


__all__ = ["HizSiniri", "KaliciHizSiniri", "izin_ver", "suresi_gecenleri_sil", "simdi_ms", "yedek_sayisi"]
