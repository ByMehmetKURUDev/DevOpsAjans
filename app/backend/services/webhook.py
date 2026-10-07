"""Faz 4A — imzalı webhook'lar: olay yayını, teslimat, yeniden deneme, otomatik pasifleştirme.

Olay nereden doğuyor? — merkezi flush kancası
---------------------------------------------
Olayların çoğu bir kaydın oluşması ya da bir alanın değişmesi (fatura kesildi,
ödendi; talep açıldı, yanıtlandı; görev oluştu, tamamlandı; projenin aşaması
değişti; teklif kabul/ret; sözleşme imzalandı; menü siparişi; kartvizit
mesajı; CRM adayı). Bu kayıtlar tek bir kapıdan geçmiyor: entity CRUD
uçları, servisler, ödeme sağlayıcısı geri çağrıları, imzalı bağlantılar,
e-postayla gelen talep… `services/notify.dispatch` da ortak nokta değil:
insan için metin (başlık/gövde) taşıyor, yapılandırılmış veri değil; görev
oluşturma, fatura kesme (entity ucu), QR taraması gibi olaylarda hiç
çağrılmıyor; alıcı listesi ekip üyelerine genişletilmiş hâlde.

Bu yüzden denetim kaydı (`services/denetim.py`) ve CRM kancasıyla
(`services/crm.py`) aynı yol seçildi: `Session` `after_flush` olayı.
`session.new` / `session.dirty` içindeki izlenen tabloların nesnelerinden ve
alan geçmişinden olay çıkarılıyor (`KURALLAR`), teslimat satırları aynı
işlemde bir SAVEPOINT'e yazılıyor: asıl işlem geri alınırsa olay da yok;
webhook yazımı patlarsa yalnız SAVEPOINT gidiyor, asıl iş etkilenmiyor.
Başka dosyalara dağılmış kanca yok; iki istisna iş biriminden geçmeyen
(Core INSERT) yollar: CRM'in otomatik aday kaydı (`services/crm.py`
`kayittan_aday_sync`) ve QR taraması (`routers/dinamik_qr.py` `_tarama_yaz`)
— ikisinde tek satır `olay_yaz_sync` / `olay_yayinla`. (Faz 6E etkinlik
olayları da bu kancadan: bilet satırının durum geçişi ve okutma kaydı.)

Maliyet: aktif uç noktası listesi süreç içinde 30 sn önbellekte; hiç uç
noktası yoksa (ya da olay türüne abone yoksa) kanca veritabanına hiç gitmiyor.

Yayınlayıcı → aboneler (Faz 4W)
-------------------------------
Olay ÜRETİMİ tek noktada (bu dosya: flush kancası + `olay_yaz_sync` /
`olay_yayinla` / `olaylari_yayinla_sync`), TÜKETİM abone listesinde: webhook
teslimatı her zaman ilk abone (davranışı birebir aynı), otomasyon kuralları
(`services/otomasyon.py`) `abone_ekle` ile kaydolan ikinci abone. Her abone:
önbellekten "belki ilgilenirim" kararı (hayırsa veritabanına gidilmiyor),
izlediği tablolar, aynı işlemde kendi SAVEPOINT'inde yazım ve isteğe bağlı
`after_commit` işi. Bir abonenin hatası diğerini ve asıl işi etkilemiyor.
Webhook kataloğunda olmayan olaylar (ör. `randevu.olusturuldu`,
`aday.asama_degisti`, zamanlı `fatura.gecikti`) yalnız onları isteyen
aboneye gider; webhook abonesi `OLAY_SOZLUGU` dışındaki türleri yok sayıyor.
Otomasyonun zincir bilgisi (`session.info["otomasyon_zinciri"]`: derinlik +
zincirdeki kurallar) abonelere `baglam["zincir"]` olarak geçiyor.

Teslimat
--------
* Gövde `{id, tur, olusturma, hesap, veri}` (kişisel veri asgari: kimlikler
  ve iş alanları; ad/e-posta/telefon/adres yok — gerekirse API'den çekilir).
* Başlıklar: `MK-Webhook-Id` (olay kimliği; yeniden denemelerde aynı),
  `MK-Webhook-Zaman` (unix sn), `MK-Webhook-Imza: v1=<hex HMAC-SHA256(gizli,
  zaman + "." + gövde)>` — sır yenilendiyse 24 saat boyunca eskisiyle ikinci
  bir `v1=` (boşlukla ayrılmış). Alıcı 5 dk zaman toleransı uygulamalı.
* İlk deneme işlem onaylandıktan hemen sonra arka plan görevinde (istek
  yanıtı beklemiyor; `after_commit` → `asyncio` görevi). 10 sn zaman aşımı,
  yönlendirme izlenmiyor, adres her denemede SSRF denetiminden geçiyor
  (bağlantı anında da: `services/site_analizi` güvenli ağ katmanı — DNS
  yeniden bağlama). Yanıtın ilk 1 kB'ı saklanıyor.
* Başarısızsa üstel geri çekilme (5 dk, 30 dk, 2 sa, 6 sa, 12 sa, 24 sa, 24 sa —
  toplam 8 deneme) zamanlı uçtan (`routers/zamanli.py`, GitHub Actions 10 dk)
  işleniyor; 3 günü geçen teslimattan vazgeçiliyor.
* Art arda `OTOMATIK_PASIF_ESIGI` otomatik deneme başarısızsa uç noktası
  pasifleşiyor, bekleyen teslimatları düşüyor ve sahibine bildirim gidiyor
  (`webhook_pasiflesti`).
* Teslimat ve deneme kayıtları 30 gün (zamanlı temizlik + teslimat listesi
  açıldığında saatte bir).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx
from models.api_erisimi import WebhookDenemeleri, WebhookTeslimatlari, WebhookUcNoktalari
from services.api_erisimi import ApiHatasi, Sahip, eposta_duzelt, gizli_oku, gizli_sakla, iso, json_liste, simdi, utc
from sqlalchemy import and_, delete, event, func, inspect, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

AJAN = "MehmetKuruDev-Webhook/1.0 (+https://mehmetkuru.dev)"
ZAMAN_ASIMI = 10.0
YANIT_SINIRI = 1024
TEKRAR_ARALIKLARI: Tuple[timedelta, ...] = (
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
    timedelta(hours=12),
    timedelta(hours=24),
    timedelta(hours=24),
)
EN_COK_DENEME = len(TEKRAR_ARALIKLARI) + 1
VAZGECME_SURESI = timedelta(days=3)
OTOMATIK_PASIF_ESIGI = 20
SAKLAMA_SURESI = timedelta(days=30)
GIZLI_GECIS_SURESI = timedelta(hours=24)
KILIT_SURESI = timedelta(seconds=60)
ONBELLEK_SN = 30.0
VARSAYILAN_WEBHOOK_SINIRI = 5
AJANS_WEBHOOK_SINIRI = 20
URL_SINIRI = 2000
ACIKLAMA_SINIRI = 200
#: Zamanlı turda bir anda en çok bu kadar teslimat; tur başına süre bütçesi.
ESZAMANLILIK = 4
TUR_BUTCESI_SN = 45.0
TUR_SINIRI = 100


@dataclass(frozen=True)
class OlayTuru:
    anahtar: str
    #: Müşteri uç noktası abone olabilir mi? (CRM yalnız ajans.)
    musteri: bool = True
    #: Yeni uç noktasında varsayılan seçili mi? (Yüksek hacimli QR taraması değil.)
    varsayilan: bool = True
    yuksek_hacim: bool = False


OLAY_TURLERI: Tuple[OlayTuru, ...] = (
    OlayTuru("aday.olusturuldu", musteri=False),
    OlayTuru("teklif.kabul_edildi"),
    OlayTuru("teklif.reddedildi"),
    OlayTuru("sozlesme.imzalandi"),
    OlayTuru("fatura.olusturuldu"),
    OlayTuru("fatura.odendi"),
    OlayTuru("destek.olusturuldu"),
    OlayTuru("destek.yanitlandi"),
    OlayTuru("gorev.olusturuldu"),
    OlayTuru("gorev.tamamlandi"),
    OlayTuru("proje.asama_degisti"),
    OlayTuru("menu.siparis"),
    OlayTuru("kart.mesaj"),
    # Faz 5I — İçerik stüdyosu: onay (müşteri ya da ekip), müşterinin revizyon isteği, planlanan
    # saat geldi (onaylı gönderi; zamanlı uçtan, tek kez) ve elle "yayınlandı" işareti.
    OlayTuru("icerik.onaylandi"),
    OlayTuru("icerik.revizyon_istendi"),
    OlayTuru("icerik.yayin_zamani"),
    OlayTuru("icerik.yayinlandi"),
    OlayTuru("qr.tarama", varsayilan=False, yuksek_hacim=True),
    # Faz 5A — AI asistan ziyaretçiyi insana devretti (sohbet durumu "devredildi").
    OlayTuru("asistan.devredildi"),
    # Faz 6S — saha servisi iş emri açıldı / tamamlandı.
    OlayTuru("is_emri.olusturuldu"),
    OlayTuru("is_emri.tamamlandi"),
    # Faz 6E — etkinlik (flush kancası, `_etkinlik_olaylari`): kayıt onaylandı (ücretsizde anında,
    # ücretlide ödeme gelince), ücretli bilet satıldı (yalnız ajans etkinliği — müşteri etkinliğinde
    # ücretli bilet yok), kapıda giriş (okutma kaydı), onaylı bilet iptali. Kişisel veri yok.
    OlayTuru("etkinlik.kayit"),
    OlayTuru("etkinlik.bilet_satildi", musteri=False),
    OlayTuru("etkinlik.giris", varsayilan=False),
    OlayTuru("etkinlik.iptal"),
    # Faz 6P — stok ve POS (`services/stok_kayit.py`, olay_yayinla): satış tamamlandı (her fişte; varsayılan
    # kapalı — yüksek hacim) ve ürün kritik stok seviyesine indi (ürün başına tek olay). Kişisel veri yok.
    OlayTuru("pos.satis", varsayilan=False, yuksek_hacim=True),
    OlayTuru("stok.kritik"),
)
OLAY_SOZLUGU: Dict[str, OlayTuru] = {o.anahtar: o for o in OLAY_TURLERI}
#: Abone olunmaz; "Test olayı gönder" ile seçilen uç noktasına gider.
PING = "ping"


def olay_katalogu(ajans: bool) -> List[Dict[str, Any]]:
    return [
        {"anahtar": o.anahtar, "varsayilan": o.varsayilan, "yuksek_hacim": o.yuksek_hacim}
        for o in OLAY_TURLERI
        if ajans or o.musteri
    ]


# ---------------------------------------------------------------------------
# İmza
# ---------------------------------------------------------------------------
def imza_hesapla(gizli: str, zaman: str, govde: str) -> str:
    """hex(HMAC-SHA256(gizli, zaman + "." + gövde)) — belgelerdeki doğrulama örneğiyle birebir aynı."""
    return hmac.new(gizli.encode("utf-8"), f"{zaman}.{govde}".encode("utf-8"), hashlib.sha256).hexdigest()


def imza_basligi(gizliler: List[str], zaman: str, govde: str) -> str:
    return " ".join(f"v1={imza_hesapla(g, zaman, govde)}" for g in gizliler if g)


def imza_dogrula(gizli: str, zaman: str, govde: str, baslik: str, tolerans_sn: int = 300, an: Optional[float] = None) -> bool:
    """Alıcı tarafı doğrulaması (belgelerdeki Python örneğinin aynısı; testler bununla doğruluyor)."""
    try:
        if abs((an if an is not None else time.time()) - int(zaman)) > tolerans_sn:
            return False
    except (TypeError, ValueError):
        return False
    beklenen = imza_hesapla(gizli, zaman, govde)
    for parca in (baslik or "").split():
        surum, _, deger = parca.partition("=")
        if surum == "v1" and hmac.compare_digest(deger, beklenen):
            return True
    return False


def gizli_uret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Adres (SSRF) denetimi
# ---------------------------------------------------------------------------
async def url_dogrula(ham: Any) -> str:
    """Yalnız https (üretim dışında test izinli host için http), kullanıcı bilgisi/parça yok,
    80/443 dışı port yok, özel/yerel/metadata adresi yok — DNS çözümünden sonra da."""
    from services import site_analizi as sa

    url = str(ham or "").strip()
    if not url or len(url) > URL_SINIRI or any(c.isspace() for c in url):
        raise ApiHatasi(400, "url_gecersiz")
    try:
        parca = urlsplit(url)
        host = (parca.hostname or "").lower()
    except ValueError:
        raise ApiHatasi(400, "url_gecersiz")
    sema = (parca.scheme or "").lower()
    if parca.fragment:
        raise ApiHatasi(400, "url_gecersiz")
    test_hostu = host in sa.test_izinli_hostlar()
    if sema != "https" and not (sema == "http" and test_hostu):
        raise ApiHatasi(400, "url_https_gerekli")
    try:
        await sa.adres_dogrula(url)
    except sa.AnalizHatasi as h:
        raise ApiHatasi(400, f"url_{h.kod}")
    return url


# ---------------------------------------------------------------------------
# Uç noktası CRUD
# ---------------------------------------------------------------------------
def olaylari_duzelt(ham: Any, *, ajans: bool) -> List[str]:
    if not isinstance(ham, list) or not ham:
        raise ApiHatasi(400, "olay_gerekli")
    secili = set()
    for o in ham:
        o = str(o).strip()
        tanim = OLAY_SOZLUGU.get(o)
        if tanim is None:
            raise ApiHatasi(400, "olay_gecersiz", olay=o)
        if not tanim.musteri and not ajans:
            raise ApiHatasi(400, "olay_yalniz_ajans", olay=o)
        secili.add(o)
    return [o.anahtar for o in OLAY_TURLERI if o.anahtar in secili]


async def webhook_siniri(db: AsyncSession, sahip: Sahip) -> int:
    if sahip.yonetici:
        return AJANS_WEBHOOK_SINIRI
    from services.moduller import musteri_ayari

    deger = await musteri_ayari(db, sahip.hesap or "", "api_erisimi", "webhook_siniri")
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else VARSAYILAN_WEBHOOK_SINIRI


def uc_sozlugu(uc: WebhookUcNoktalari, bekleyen: int = 0) -> Dict[str, Any]:
    """Panel yanıtı — imza sırrı ASLA dönmez."""
    return {
        "id": uc.id,
        "sahip_tur": uc.sahip_tur,
        "hesap_email": uc.hesap_email,
        "url": uc.url,
        "aciklama": uc.aciklama,
        "olaylar": json_liste(uc.olaylar),
        "tum_musteriler": bool(uc.tum_musteriler),
        "aktif": bool(uc.aktif),
        "pasif_sebebi": uc.pasif_sebebi,
        "ardisik_hata": int(uc.ardisik_hata or 0),
        "son_basari_at": iso(uc.son_basari_at),
        "son_hata_at": iso(uc.son_hata_at),
        "gizli_gecis_bitis": iso(uc.onceki_gizli_bitis) if uc.onceki_gizli_anahtar else None,
        "bekleyen": bekleyen,
        "olusturan": uc.olusturan,
        "olusturma": iso(uc.created_at),
    }


async def uclar(db: AsyncSession, sahip: Sahip, *, hepsi: bool = False) -> List[Tuple[WebhookUcNoktalari, int]]:
    sorgu = select(WebhookUcNoktalari)
    if not (sahip.yonetici and hepsi):
        sorgu = sorgu.where(sahip.sahip_kosulu(WebhookUcNoktalari))
    liste = list((await db.execute(sorgu.order_by(WebhookUcNoktalari.id.desc()).limit(200))).scalars().all())
    if not liste:
        return []
    sayilar = dict(
        (
            await db.execute(
                select(WebhookTeslimatlari.uc_id, func.count(WebhookTeslimatlari.id))
                .where(WebhookTeslimatlari.uc_id.in_([u.id for u in liste]), WebhookTeslimatlari.durum == "bekliyor")
                .group_by(WebhookTeslimatlari.uc_id)
            )
        ).all()
    )
    return [(u, int(sayilar.get(u.id, 0))) for u in liste]


async def uc_bul(db: AsyncSession, sahip: Sahip, uc_id: int) -> WebhookUcNoktalari:
    sorgu = select(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc_id)
    if not sahip.yonetici:
        sorgu = sorgu.where(sahip.sahip_kosulu(WebhookUcNoktalari))
    uc = (await db.execute(sorgu)).scalars().first()
    if uc is None:
        raise ApiHatasi(404, "bulunamadi")
    return uc


async def uc_olustur(db: AsyncSession, sahip: Sahip, govde: Dict[str, Any]) -> Tuple[str, WebhookUcNoktalari]:
    url = await url_dogrula(govde.get("url"))
    olaylar = olaylari_duzelt(govde.get("olaylar"), ajans=sahip.yonetici)
    sinir = await webhook_siniri(db, sahip)
    sayi = int(
        (await db.execute(select(func.count(WebhookUcNoktalari.id)).where(sahip.sahip_kosulu(WebhookUcNoktalari)))).scalar()
        or 0
    )
    if sayi >= sinir:
        raise ApiHatasi(409, "webhook_siniri", sinir=sinir)
    gizli = gizli_uret()
    an = simdi()
    uc = WebhookUcNoktalari(
        sahip_tur=sahip.sahip_tur,
        hesap_email=None if sahip.yonetici else sahip.hesap,
        url=url,
        aciklama=(str(govde.get("aciklama") or "").strip()[:ACIKLAMA_SINIRI] or None),
        olaylar=json.dumps(olaylar),
        tum_musteriler=bool(govde.get("tum_musteriler")) if sahip.yonetici else False,
        aktif=govde.get("aktif") is not False,
        gizli_anahtar=gizli_sakla(gizli),
        ardisik_hata=0,
        olusturan=sahip.kisi or None,
        created_at=an,
    )
    db.add(uc)
    await db.commit()
    await db.refresh(uc)
    onbellegi_temizle()
    return gizli, uc


async def uc_guncelle(db: AsyncSession, sahip: Sahip, uc: WebhookUcNoktalari, govde: Dict[str, Any]) -> WebhookUcNoktalari:
    if "url" in govde:
        uc.url = await url_dogrula(govde.get("url"))
    if "olaylar" in govde:
        uc.olaylar = json.dumps(olaylari_duzelt(govde.get("olaylar"), ajans=uc.sahip_tur == "ajans"))
    if "aciklama" in govde:
        uc.aciklama = str(govde.get("aciklama") or "").strip()[:ACIKLAMA_SINIRI] or None
    if "tum_musteriler" in govde and uc.sahip_tur == "ajans" and sahip.yonetici:
        uc.tum_musteriler = bool(govde.get("tum_musteriler"))
    if "aktif" in govde:
        aktif = bool(govde.get("aktif"))
        if aktif and not uc.aktif:
            # Yeniden açılış: sayaç sıfırdan başlasın.
            uc.ardisik_hata = 0
            uc.pasif_sebebi = None
        uc.aktif = aktif
    await db.commit()
    await db.refresh(uc)
    onbellegi_temizle()
    return uc


async def gizli_yenile(db: AsyncSession, uc: WebhookUcNoktalari) -> str:
    """Yeni sır; eskisi 24 saat ikinci imzayla gönderilmeye devam eder."""
    yeni = gizli_uret()
    uc.onceki_gizli_anahtar = uc.gizli_anahtar
    uc.onceki_gizli_bitis = simdi() + GIZLI_GECIS_SURESI
    uc.gizli_anahtar = gizli_sakla(yeni)
    await db.commit()
    await db.refresh(uc)
    return yeni


async def uc_sil(db: AsyncSession, uc: WebhookUcNoktalari) -> None:
    """Kalıcı silme (çöp kutusuna düşmez: satır imza sırrını taşıyor). Teslimat geçmişi de gider."""
    uc_id = uc.id
    ids = select(WebhookTeslimatlari.id).where(WebhookTeslimatlari.uc_id == uc_id)
    await db.execute(delete(WebhookDenemeleri).where(WebhookDenemeleri.teslimat_id.in_(ids)))
    await db.execute(delete(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc_id))
    await db.delete(uc)
    await db.commit()
    onbellegi_temizle()


def _gizliler(uc: WebhookUcNoktalari, an: Optional[datetime] = None) -> List[str]:
    an = an or simdi()
    liste = [gizli_oku(uc.gizli_anahtar)]
    bitis = utc(uc.onceki_gizli_bitis)
    if uc.onceki_gizli_anahtar and bitis is not None and bitis > an:
        liste.append(gizli_oku(uc.onceki_gizli_anahtar))
    return [g for g in liste if g]


# ---------------------------------------------------------------------------
# Aktif uç noktası önbelleği
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _UcOzeti:
    id: int
    sahip_tur: str
    hesap: Optional[str]
    olaylar: FrozenSet[str]
    tum_musteriler: bool


_onbellek: Dict[str, Any] = {"bitis": 0.0, "uclar": None}


def onbellegi_temizle() -> None:
    _onbellek["bitis"] = 0.0
    _onbellek["uclar"] = None


def _onbellek_gecerli() -> Optional[List[_UcOzeti]]:
    if _onbellek["uclar"] is not None and _onbellek["bitis"] >= time.monotonic():
        return _onbellek["uclar"]
    return None


def _uclari_yukle_sync(baglanti) -> List[_UcOzeti]:
    t = WebhookUcNoktalari.__table__
    satirlar = baglanti.execute(
        select(t.c.id, t.c.sahip_tur, t.c.hesap_email, t.c.olaylar, t.c.tum_musteriler).where(t.c.aktif.is_(True))
    ).all()
    liste = [
        _UcOzeti(
            id=int(s[0]),
            sahip_tur=s[1],
            hesap=eposta_duzelt(s[2]) or None,
            olaylar=frozenset(json_liste(s[3])),
            tum_musteriler=bool(s[4]),
        )
        for s in satirlar
    ]
    _onbellek["uclar"] = liste
    _onbellek["bitis"] = time.monotonic() + ONBELLEK_SN
    return liste


def _eslesenler(uclar: List[_UcOzeti], tur: str, hesap: Optional[str], musteri_gorur: bool) -> List[_UcOzeti]:
    sonuc = []
    for u in uclar:
        if tur not in u.olaylar:
            continue
        if u.sahip_tur == "ajans":
            if hesap is None or u.tum_musteriler:
                sonuc.append(u)
        elif u.sahip_tur == "musteri" and hesap and musteri_gorur and u.hesap == hesap:
            sonuc.append(u)
    return sonuc


def _abone_var_mi(uclar: List[_UcOzeti], tur: str) -> bool:
    return any(tur in u.olaylar for u in uclar)


# ---------------------------------------------------------------------------
# Olay kaydı (teslimat satırları)
# ---------------------------------------------------------------------------
#: İşlem onaylanınca arka plan teslimatını başlatacak bayrak (süreç içi).
_bekleyen: Dict[str, bool] = {"var": False}
#: Testler kapatıyor (teslimatı kendileri tetikliyor).
ANLIK_TESLIMAT = True


def olay_kimligi() -> str:
    return "evt_" + secrets.token_hex(12)


def olay_govdesi(olay_id: str, tur: str, hesap: Optional[str], veri: Dict[str, Any], an: datetime) -> str:
    return json.dumps(
        {"id": olay_id, "tur": tur, "olusturma": iso(an), "hesap": hesap, "veri": veri},
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _satirlari_ekle_sync(baglanti, hedefler: List[int], tur: str, hesap: Optional[str], veri: Dict[str, Any]) -> int:
    an = simdi()
    olay_id = olay_kimligi()
    govde = olay_govdesi(olay_id, tur, hesap, veri, an)
    satirlar = [
        {
            "uc_id": uc_id,
            "olay_id": olay_id,
            "tur": tur,
            "hesap_email": hesap,
            "govde": govde,
            "durum": "bekliyor",
            "deneme_sayisi": 0,
            "sonraki_deneme": an,
            "created_at": an,
            "updated_at": an,
        }
        for uc_id in hedefler
    ]
    if satirlar:
        baglanti.execute(WebhookTeslimatlari.__table__.insert(), satirlar)
        _bekleyen["var"] = True
    return len(satirlar)


def olay_yaz_sync(baglanti, tur: str, hesap: Optional[str], veri: Dict[str, Any], *, musteri_gorur: bool = True) -> int:
    """Eşleşen aktif uç noktalarına teslimat satırı yazar (çağıranın işleminde, SAVEPOINT).

    Faz 4W: olay ayrıca ek abonelere (otomasyon) dağıtılır. HİÇBİR koşulda hata
    fırlatmaz; dönen değer eskisi gibi yazılan WEBHOOK teslimat satırı sayısı.
    """
    _ek_abonelere_dagit(baglanti, [(tur, hesap, veri, musteri_gorur)], None)
    try:
        uclar = _onbellek_gecerli()
        if uclar is not None and not _abone_var_mi(uclar, tur):
            return 0
        with baglanti.begin_nested():
            if uclar is None:
                uclar = _uclari_yukle_sync(baglanti)
            hesap = eposta_duzelt(hesap) or None
            hedefler = [u.id for u in _eslesenler(uclar, tur, hesap, musteri_gorur)]
            if not hedefler:
                return 0
            return _satirlari_ekle_sync(baglanti, hedefler, tur, hesap, veri)
    except Exception:  # noqa: BLE001 - webhook asıl işi ASLA bozmamalı
        logger.exception("Webhook olayı yazılamadı (%s)", tur)
        return 0


async def olay_yayinla(db: AsyncSession, tur: str, hesap: Optional[str], veri: Dict[str, Any], *, musteri_gorur: bool = True) -> int:
    """Async yollar için (çağıran commit eder). Hata fırlatmaz."""
    uclar = _onbellek_gecerli()
    if uclar is not None and not _abone_var_mi(uclar, tur) and not _ek_abone_ilgilenir_mi(tur):
        return 0
    try:
        return await db.run_sync(lambda s: olay_yaz_sync(s.connection(), tur, hesap, veri, musteri_gorur=musteri_gorur))
    except Exception:  # noqa: BLE001
        logger.exception("Webhook olayı yayınlanamadı (%s)", tur)
        return 0


async def qr_tarama_yayinla(db: AsyncSession, veri: Dict[str, Any]) -> int:
    """`qr.tarama` (yüksek hacimli; varsayılan kapalı). Abone yoksa QR satırına bile bakılmaz."""
    uclar = _onbellek_gecerli()
    if uclar is not None and not _abone_var_mi(uclar, "qr.tarama"):
        return 0
    try:
        from models.dinamik_qr import DinamikQr

        satir = (await db.execute(select(DinamikQr.hesap_email, DinamikQr.kod).where(DinamikQr.id == veri.get("qr_id")))).first()
        if satir is None:
            return 0
        return await olay_yayinla(db, "qr.tarama", satir[0], {
            "qr_id": veri.get("qr_id"), "kod": satir[1], "ulke": veri.get("ulke"), "cihaz": veri.get("cihaz"),
            "isletim": veri.get("isletim"), "zaman": iso(veri.get("zaman")),
        })
    except Exception:  # noqa: BLE001
        logger.exception("QR tarama webhook'u yazılamadı")
        return 0


# ---------------------------------------------------------------------------
# Flush kancası: kayıt değişikliği → olay
# ---------------------------------------------------------------------------
def _gecmis(obj: Any, alan: str) -> Tuple[bool, Any, Any]:
    """(değişti mi, eski, yeni)."""
    try:
        h = inspect(obj).attrs[alan].history
    except Exception:  # noqa: BLE001
        return False, None, None
    if not h.has_changes():
        return False, None, None
    eski = h.deleted[0] if h.deleted else None
    yeni = h.added[0] if h.added else None
    return True, eski, yeni


def _tarih(deger: Any) -> Optional[str]:
    if deger is None:
        return None
    if isinstance(deger, datetime):
        return iso(deger)
    if hasattr(deger, "isoformat"):
        return deger.isoformat()
    return str(deger)


def _sayi(deger: Any) -> Optional[float]:
    if deger is None:
        return None
    try:
        return float(deger)
    except (TypeError, ValueError):
        return None


TASLAK_FATURA = ("draft", "taslak")


def _fatura_verisi(f: Any) -> Dict[str, Any]:
    return {
        "fatura_id": f.id,
        "no": f.invoice_no,
        "tutar": _sayi(f.amount),
        "para_birimi": f.currency or "TRY",
        "durum": f.status,
        "tur": f.tur,
        "vade_tarihi": f.due_date,
    }


def _tek_deger(baglanti, sorgu) -> Any:
    try:
        return baglanti.execute(sorgu).scalar()
    except Exception:  # noqa: BLE001
        return None


def _olaylari_cikar(session: Session, baglanti) -> List[Tuple[str, Optional[str], Dict[str, Any], bool]]:
    """(tür, hesap, veri, müşteri görür mü) listesi. Hesap aramaları aynı bağlantıda."""
    olaylar: List[Tuple[str, Optional[str], Dict[str, Any], bool]] = []
    #: Faz 6E — sipariş kimliği → bu flush'ta geçerli olan / iptal edilen biletler (sipariş başına tek olay).
    etkinlik_gecerli: Dict[int, List[Any]] = {}
    etkinlik_iptal: Dict[int, List[Any]] = {}
    for obj in list(session.new):
        tablo = getattr(type(obj), "__tablename__", "")
        if tablo == "invoices":
            if (obj.status or "") not in TASLAK_FATURA:
                olaylar.append(("fatura.olusturuldu", obj.client_email, _fatura_verisi(obj), True))
                if (obj.status or "") == "paid":
                    olaylar.append(("fatura.odendi", obj.client_email, _fatura_verisi(obj), True))
        elif tablo == "support_tickets":
            olaylar.append((
                "destek.olusturuldu",
                obj.client_email,
                {"talep_id": obj.id, "konu": obj.subject, "durum": obj.status, "oncelik": obj.priority,
                 "proje_id": obj.project_id, "kaynak": obj.kaynak},
                True,
            ))
        elif tablo == "ticket_replies":
            from models.support_tickets import Support_tickets

            hesap = _tek_deger(baglanti, select(Support_tickets.client_email).where(Support_tickets.id == obj.ticket_id))
            olaylar.append(("destek.yanitlandi", hesap, {"talep_id": obj.ticket_id, "mesaj_id": obj.id, "yazan": obj.yazan}, True))
        elif tablo == "project_tasks":
            from models.projects import Projects

            hesap = _tek_deger(baglanti, select(Projects.client_email).where(Projects.id == obj.proje_id))
            veri = {"gorev_id": obj.id, "proje_id": obj.proje_id, "baslik": obj.baslik, "durum": obj.durum,
                    "oncelik": obj.oncelik, "bitis_tarihi": _tarih(obj.bitis_tarihi)}
            gorur = bool(obj.musteriye_gorunur)
            olaylar.append(("gorev.olusturuldu", hesap, veri, gorur))
            if obj.durum == "tamam":
                olaylar.append(("gorev.tamamlandi", hesap, veri, gorur))
        elif tablo == "crm_adaylar":
            olaylar.append(("aday.olusturuldu", None, aday_verisi(obj.id, obj.kaynak, obj.asama, obj.deger_tahmini, obj.para_birimi), False))
        elif tablo == "menu_siparisleri":
            from models.qr_menu import MenuMagazalari

            hesap = _tek_deger(baglanti, select(MenuMagazalari.hesap_email).where(MenuMagazalari.id == obj.magaza_id))
            olaylar.append(("menu.siparis", hesap, {
                "siparis_id": obj.id, "siparis_no": obj.siparis_no, "magaza_id": obj.magaza_id, "durum": obj.durum,
                "teslimat": obj.teslimat, "masa": obj.masa, "toplam_kurus": obj.toplam, "para_birimi": obj.para_birimi,
                "kalem_sayisi": len(json_liste(obj.kalemler)),
            }, True))
        elif tablo == "kartvizit_mesajlari" and obj.sahip_tur == "kart":
            olaylar.append(("kart.mesaj", obj.hesap_email, {"mesaj_id": obj.id, "kart_id": obj.sahip_id}, True))
        elif tablo == "randevular":
            # Faz 4W: yalnız otomasyon (webhook kataloğunda yok).
            olaylar.append(("randevu.olusturuldu", obj.hesap_email, {"randevu_id": obj.id, "tur_id": obj.tur_id}, True))
        elif tablo == "ai_asistan_sohbetleri" and obj.durum == "devredildi":
            olaylar.append(("asistan.devredildi", obj.hesap_email, _devir_verisi(obj), True))
        elif tablo == "saha_is_emirleri":
            olaylar.append(("is_emri.olusturuldu", obj.hesap_email, _is_emri_verisi(obj), True))
        elif tablo == "etkinlik_biletleri" and obj.durum == "gecerli":
            etkinlik_gecerli.setdefault(obj.siparis_id, []).append(obj)
        elif tablo == "etkinlik_okutmalar" and obj.sonuc == "gecerli" and obj.bilet_id:
            olaylar.extend(_etkinlik_giris(baglanti, obj))

    for obj in list(session.dirty):
        tablo = getattr(type(obj), "__tablename__", "")
        if tablo == "invoices":
            degisti, eski, yeni = _gecmis(obj, "status")
            if degisti:
                if (eski or "") in TASLAK_FATURA and (yeni or "") not in TASLAK_FATURA:
                    olaylar.append(("fatura.olusturuldu", obj.client_email, _fatura_verisi(obj), True))
                if yeni == "paid" and eski != "paid":
                    olaylar.append(("fatura.odendi", obj.client_email, _fatura_verisi(obj), True))
        elif tablo == "project_tasks":
            degisti, eski, yeni = _gecmis(obj, "durum")
            if degisti and yeni == "tamam" and eski != "tamam":
                from models.projects import Projects

                hesap = _tek_deger(baglanti, select(Projects.client_email).where(Projects.id == obj.proje_id))
                olaylar.append(("gorev.tamamlandi", hesap, {
                    "gorev_id": obj.id, "proje_id": obj.proje_id, "baslik": obj.baslik, "durum": obj.durum,
                    "oncelik": obj.oncelik, "bitis_tarihi": _tarih(obj.bitis_tarihi),
                }, bool(obj.musteriye_gorunur)))
        elif tablo == "projects":
            degisti, eski, yeni = _gecmis(obj, "stage")
            if degisti and yeni != eski:
                olaylar.append(("proje.asama_degisti", obj.client_email, {
                    "proje_id": obj.id, "baslik": obj.title, "onceki_asama": eski, "asama": yeni, "ilerleme": obj.progress,
                }, True))
        elif tablo == "teklifler":
            degisti, eski, yeni = _gecmis(obj, "durum")
            if degisti and yeni in ("kabul", "ret") and eski != yeni:
                olaylar.append((
                    "teklif.kabul_edildi" if yeni == "kabul" else "teklif.reddedildi",
                    obj.hesap_email,
                    {"teklif_id": obj.id, "no": obj.no, "baslik": obj.baslik, "genel_toplam": _sayi(obj.genel_toplam),
                     "para_birimi": obj.para_birimi, "durum": yeni},
                    True,
                ))
        elif tablo == "ai_asistan_sohbetleri":
            degisti, eski, yeni = _gecmis(obj, "durum")
            if degisti and yeni == "devredildi" and eski != "devredildi":
                olaylar.append(("asistan.devredildi", obj.hesap_email, _devir_verisi(obj), True))
        elif tablo == "sozlesmeler":
            degisti, eski, yeni = _gecmis(obj, "durum")
            if degisti and yeni == "imzalandi" and eski != "imzalandi":
                olaylar.append(("sozlesme.imzalandi", obj.hesap_email, {
                    "sozlesme_id": obj.id, "no": obj.no, "baslik": obj.baslik, "teklif_id": obj.teklif_id,
                    "imza_at": iso(obj.imza_at),
                }, True))
        elif tablo == "content_posts":
            # Faz 5I — içerik stüdyosu durum geçişleri (metin olay verisinde yok).
            degisti, eski, yeni = _gecmis(obj, "status")
            if degisti and yeni != eski:
                from services.icerik_planlayici import olay_verisi

                if yeni == "onaylandi" and eski != "yayinlandi":
                    kaynak = "musteri" if eski == "musteri_onayi" else "ekip"
                    olaylar.append(("icerik.onaylandi", obj.hesap_email or None, olay_verisi(obj, {"kaynak": kaynak}), True))
                elif yeni == "yayinlandi":
                    olaylar.append(("icerik.yayinlandi", obj.hesap_email or None, olay_verisi(obj), True))
                elif eski == "musteri_onayi" and yeni == "taslak" and getattr(obj, "_icerik_revizyon", False):
                    olaylar.append(("icerik.revizyon_istendi", obj.hesap_email or None,
                                    olay_verisi(obj, {"not": obj.durum_notu}), True))
        elif tablo == "saha_is_emirleri":
            degisti, eski, yeni = _gecmis(obj, "durum")
            if degisti and yeni == "tamamlandi" and eski != "tamamlandi":
                olaylar.append(("is_emri.tamamlandi", obj.hesap_email, _is_emri_verisi(obj), True))
        elif tablo == "crm_adaylar":
            # Faz 4W: yalnız otomasyon (webhook kataloğunda yok).
            degisti, eski, yeni = _gecmis(obj, "asama")
            if degisti and yeni != eski and eski is not None:
                olaylar.append(("aday.asama_degisti", None, {**aday_verisi(
                    obj.id, obj.kaynak, yeni, obj.deger_tahmini, obj.para_birimi), "onceki_asama": eski}, False))
        elif tablo == "etkinlik_biletleri":
            degisti, eski, yeni = _gecmis(obj, "durum")
            if degisti and yeni == "gecerli" and eski != "gecerli":
                etkinlik_gecerli.setdefault(obj.siparis_id, []).append(obj)
            elif degisti and yeni == "iptal" and eski == "gecerli":
                # Yalnız onaylı biletin iptali; ödenmemiş tutmanın süresi dolması olay değil.
                etkinlik_iptal.setdefault(obj.siparis_id, []).append(obj)
    if etkinlik_gecerli or etkinlik_iptal:
        olaylar.extend(_etkinlik_olaylari(baglanti, etkinlik_gecerli, etkinlik_iptal))
    return olaylar


def _etkinlik_olaylari(baglanti, gecerli: Dict[int, List[Any]], iptal: Dict[int, List[Any]]) -> List[Tuple[str, Optional[str], Dict[str, Any], bool]]:
    """Faz 6E — sipariş başına `etkinlik.kayit` (+ ücretliyse `etkinlik.bilet_satildi`) / `etkinlik.iptal`.

    Biletler kilitli kayıtta sipariş satırından SONRAKİ flush'ta ekleniyor; olay bilet satırından
    çıkarıldığı için `bilet_sayisi` doğru. Ad/e-posta yok (otomasyon kişi alanlarını kayıttan okur)."""
    from models.etkinlik import Etkinlikler, EtkinlikSiparisleri

    olaylar: List[Tuple[str, Optional[str], Dict[str, Any], bool]] = []
    for tur, gruplar in (("etkinlik.kayit", gecerli), ("etkinlik.iptal", iptal)):
        for sid, biletler in gruplar.items():
            satir = baglanti.execute(
                select(EtkinlikSiparisleri.kod, EtkinlikSiparisleri.durum, EtkinlikSiparisleri.toplam,
                       EtkinlikSiparisleri.para_birimi, EtkinlikSiparisleri.kaynak, Etkinlikler.id, Etkinlikler.slug,
                       Etkinlikler.hesap_email)
                .join(Etkinlikler, Etkinlikler.id == EtkinlikSiparisleri.etkinlik_id)
                .where(EtkinlikSiparisleri.id == sid)
            ).first()
            if satir is None:
                continue
            kod, durum, toplam, para, kaynak, eid, slug, hesap = satir
            veri = {"etkinlik_id": eid, "etkinlik_slug": slug, "siparis_id": sid, "siparis_kod": kod, "durum": durum,
                    "bilet_sayisi": len(biletler), "toplam_kurus": int(toplam or 0), "para_birimi": para, "kaynak": kaynak,
                    "bilet_turleri": sorted({int(b.tur_id) for b in biletler if b.tur_id is not None})}
            olaylar.append((tur, hesap, veri, True))
            if tur == "etkinlik.kayit" and int(toplam or 0) > 0:
                olaylar.append(("etkinlik.bilet_satildi", hesap, dict(veri), True))
    return olaylar


def _etkinlik_giris(baglanti, okutma: Any) -> List[Tuple[str, Optional[str], Dict[str, Any], bool]]:
    """Faz 6E — kapıda geçerli okutma (koşullu UPDATE'in yanında yazılan okutma kaydından)."""
    from models.etkinlik import EtkinlikBiletleri, Etkinlikler

    satir = baglanti.execute(
        select(EtkinlikBiletleri.kod, EtkinlikBiletleri.siparis_id, EtkinlikBiletleri.tur_id, Etkinlikler.id,
               Etkinlikler.slug, Etkinlikler.hesap_email)
        .join(Etkinlikler, Etkinlikler.id == EtkinlikBiletleri.etkinlik_id)
        .where(EtkinlikBiletleri.id == okutma.bilet_id)
    ).first()
    if satir is None:
        return []
    kod, sid, tid, eid, slug, hesap = satir
    return [("etkinlik.giris", hesap, {"etkinlik_id": eid, "etkinlik_slug": slug, "siparis_id": sid, "bilet_kod": kod,
                                       "tur_id": tid, "bilet_sayisi": 1, "kaynak": okutma.kaynak,
                                       "cevrimdisi": bool(okutma.cevrimdisi), "giris_at": iso(okutma.zaman)}, True)]


def _devir_verisi(obj: Any) -> Dict[str, Any]:
    """Faz 5A — AI asistan devri: kimlikler ve sayılar (ziyaretçinin adı/iletişimi YOK)."""
    return {"sohbet_id": obj.id, "asistan_id": obj.asistan_id, "talep_id": obj.talep_id, "aday_id": obj.aday_id,
            "mesaj_sayisi": obj.mesaj_sayisi, "kaynak": obj.kaynak, "koken": obj.koken, "zaman": iso(obj.devir_at)}


def _is_emri_verisi(obj: Any) -> Dict[str, Any]:
    """Faz 6S — saha servisi iş emri: kimlikler ve iş alanları (servis müşterisinin adı/iletişimi/
    adresi ve konum YOK — gerekirse panelden)."""
    return {"is_emri_id": obj.id, "no": obj.no, "tur": obj.tur, "oncelik": obj.oncelik, "durum": obj.durum,
            "musteri_id": obj.musteri_id, "plan_bas": iso(obj.plan_bas), "bitir_at": iso(obj.bitir_at),
            "randevu_id": obj.randevu_id}


def aday_verisi(aday_id: Any, kaynak: Any, asama: Any, deger: Any, para: Any) -> Dict[str, Any]:
    """CRM adayı olay verisi — ad/e-posta/telefon YOK (API'den `crm:oku` kapsamıyla alınır)."""
    return {"aday_id": aday_id, "kaynak": kaynak, "asama": asama, "deger_tahmini": _sayi(deger), "para_birimi": para}


IZLENEN_TABLOLAR = frozenset({
    "invoices", "support_tickets", "ticket_replies", "project_tasks", "crm_adaylar", "menu_siparisleri",
    "content_posts",  # Faz 5I
    "kartvizit_mesajlari", "projects", "teklifler", "sozlesmeler", "ai_asistan_sohbetleri",
    # Faz 6S — saha servisi iş emri.
    "saha_is_emirleri",
    "etkinlik_biletleri", "etkinlik_okutmalar",
})


# ---------------------------------------------------------------------------
# Faz 4W — yayınlayıcı: olay üretimi tek noktada, tüketim abone listesinde
# ---------------------------------------------------------------------------
#: (tür, hesap, veri, müşteri görür mü)
Olay = Tuple[str, Optional[str], Dict[str, Any], bool]


@dataclass
class OlayAbonesi:
    """Webhook dışındaki olay tüketicisi (ör. otomasyon kuralları)."""

    ad: str
    #: Önbellekten hızlı karar: tür verilirse o tür için, None ise herhangi bir olay için
    #: "belki ilgilenirim". False dönerse veritabanına hiç gidilmez.
    ilgileniyor_mu: Callable[[Optional[str]], bool]
    #: Aynı işlemde (kendi SAVEPOINT'inde) olayları işler. baglam: {"zincir": ...}
    yaz: Callable[[Any, List[Olay], Dict[str, Any]], Any]
    #: Bu abonenin flush'ta izlediği tablolar (webhook'unkilere ek olabilir).
    tablolar: FrozenSet[str] = frozenset()
    #: İşlem onaylandıktan sonra (arka plan işini başlatmak için); hata fırlatmamalı.
    commit_sonrasi: Optional[Callable[[], None]] = None


_EK_ABONELER: List[OlayAbonesi] = []


def abone_ekle(abone: OlayAbonesi) -> None:
    """Aboneyi kaydeder (aynı adla ikinci kayıt öncekinin yerine geçer: yeniden import güvenli)."""
    for i, a in enumerate(_EK_ABONELER):
        if a.ad == abone.ad:
            _EK_ABONELER[i] = abone
            return
    _EK_ABONELER.append(abone)


def _ek_abone_ilgilenir_mi(tur: Optional[str]) -> bool:
    for a in _EK_ABONELER:
        try:
            if a.ilgileniyor_mu(tur):
                return True
        except Exception:  # noqa: BLE001
            return True
    return False


def _ek_abonelere_dagit(baglanti, olaylar: List[Olay], zincir: Optional[Dict[str, Any]]) -> None:
    """Ek abonelere dağıtır; her abone kendi SAVEPOINT'inde. Hata fırlatmaz."""
    if not olaylar:
        return
    for a in list(_EK_ABONELER):
        try:
            if not any(a.ilgileniyor_mu(o[0]) for o in olaylar):
                continue
            with baglanti.begin_nested():
                a.yaz(baglanti, olaylar, {"zincir": zincir})
        except Exception:  # noqa: BLE001 - abone asıl işi ASLA bozmamalı
            logger.exception("Olay abonesi yazamadı (%s)", a.ad)


def olaylari_yayinla_sync(baglanti, olaylar: List[Olay], *, zincir: Optional[Dict[str, Any]] = None) -> None:
    """Kayıt değişikliğinden doğmayan olaylar (ör. zamanlı `fatura.gecikti`): bütün abonelere.
    Webhook kataloğunda olmayan türleri webhook zaten yok sayar. Hata fırlatmaz."""
    for tur, hesap, veri, gorur in olaylar:
        if tur in OLAY_SOZLUGU:
            try:
                uclar = _onbellek_gecerli()
                if uclar is None or _abone_var_mi(uclar, tur):
                    with baglanti.begin_nested():
                        if uclar is None:
                            uclar = _uclari_yukle_sync(baglanti)
                        h = eposta_duzelt(hesap) or None
                        hedefler = [u.id for u in _eslesenler(uclar, tur, h, gorur)]
                        if hedefler:
                            _satirlari_ekle_sync(baglanti, hedefler, tur, h, veri)
            except Exception:  # noqa: BLE001
                logger.exception("Webhook olayı yazılamadı (%s)", tur)
    _ek_abonelere_dagit(baglanti, olaylar, zincir)


def _webhook_yaz(baglanti, olaylar: List[Olay]) -> None:
    """Webhook abonesi: eşleşen aktif uç noktalarına teslimat satırları (eski davranış)."""
    uclar = _onbellek_gecerli()
    if uclar is None:
        uclar = _uclari_yukle_sync(baglanti)
    if not uclar:
        return
    for tur, hesap, veri, gorur in olaylar:
        if tur not in OLAY_SOZLUGU or not _abone_var_mi(uclar, tur):
            continue
        hesap = eposta_duzelt(hesap) or None
        hedefler = [u.id for u in _eslesenler(uclar, tur, hesap, gorur)]
        if hedefler:
            _satirlari_ekle_sync(baglanti, hedefler, tur, hesap, veri)


@event.listens_for(Session, "after_flush")
def _flush_sonrasi(session: Session, _flush_baglami) -> None:
    if session.info.get("webhook_kapali"):
        return
    try:
        uclar = _onbellek_gecerli()
        # Hiç aktif uç noktası yoksa webhook ilgilenmiyor (veritabanına gitme).
        webhook_belki = not (uclar is not None and not uclar)
        ek = [a for a in _EK_ABONELER if a.ilgileniyor_mu(None)]
        if not webhook_belki and not ek:
            return
        tablolar = set(IZLENEN_TABLOLAR) if webhook_belki else set()
        for a in ek:
            tablolar |= a.tablolar or IZLENEN_TABLOLAR
        ilgili = any(getattr(type(o), "__tablename__", "") in tablolar for o in (*session.new, *session.dirty))
        if not ilgili:
            return
        baglanti = session.connection()
        with baglanti.begin_nested():
            olaylar = _olaylari_cikar(session, baglanti)
        if not olaylar:
            return
        if webhook_belki:
            try:
                with baglanti.begin_nested():
                    _webhook_yaz(baglanti, olaylar)
            except Exception:  # noqa: BLE001 - webhook asıl işi ASLA bozmamalı
                logger.exception("Webhook flush kancası çalışamadı")
        if ek:
            _ek_abonelere_dagit(baglanti, olaylar, session.info.get("otomasyon_zinciri"))
    except Exception:  # noqa: BLE001 - webhook asıl işi ASLA bozmamalı
        logger.exception("Webhook flush kancası çalışamadı")


# ---------------------------------------------------------------------------
# İşlem onaylandı → arka plan teslimatı
# ---------------------------------------------------------------------------
_gorev: Dict[str, Any] = {"pompa": None, "yeniden": False}


@event.listens_for(Session, "after_commit")
def _commit_sonrasi(session: Session) -> None:
    for a in _EK_ABONELER:  # Faz 4W: ek aboneler (otomasyon kuyruğu) kendi arka plan işini başlatır
        if a.commit_sonrasi is not None:
            try:
                a.commit_sonrasi()
            except Exception:  # noqa: BLE001
                logger.exception("Olay abonesi commit sonrası işi başlatılamadı (%s)", a.ad)
    if not _bekleyen["var"] or not ANLIK_TESLIMAT:
        return
    try:
        dongu = asyncio.get_running_loop()
    except RuntimeError:
        return  # döngü yok (betik): zamanlı uç alır
    pompa = _gorev["pompa"]
    if pompa is not None and not pompa.done():
        _gorev["yeniden"] = True
        return
    _gorev["pompa"] = dongu.create_task(_pompa())


async def _pompa() -> None:
    from core.database import db_manager

    try:
        for _ in range(20):
            _bekleyen["var"] = False
            _gorev["yeniden"] = False
            if not db_manager.async_session_maker:
                return
            async with db_manager.async_session_maker() as db:
                await bekleyenleri_isle(db, yalniz_ilk=True)
            if not (_bekleyen["var"] or _gorev["yeniden"]):
                break
    except Exception:  # noqa: BLE001
        logger.exception("Webhook arka plan teslimatı çalışamadı")


async def pompa_bitmesini_bekle() -> None:
    """Testler için: varsa arka plan teslimatının bitmesini bekler."""
    pompa = _gorev["pompa"]
    if pompa is not None:
        await asyncio.wait_for(asyncio.shield(pompa), timeout=30)


# ---------------------------------------------------------------------------
# Teslimat
# ---------------------------------------------------------------------------
def _istemci() -> httpx.AsyncClient:
    """SSRF korumalı istemci (bağlantı anında IP denetimi); testler `site_analizi._tasiyici_fabrikasi`yla sahteler."""
    from services import site_analizi as sa

    return sa._istemci(zaman_asimi=ZAMAN_ASIMI, eszamanlilik=2, ajan=AJAN)


@dataclass
class DenemeSonucu:
    basarili: bool
    durum_kodu: Optional[int]
    sure_ms: int
    yanit: Optional[str]
    hata: Optional[str]


async def _http_gonder(url: str, govde: str, basliklar: Dict[str, str]) -> DenemeSonucu:
    from services import site_analizi as sa

    bas = time.monotonic()
    try:
        await sa.adres_dogrula(url)
    except sa.AnalizHatasi as h:
        return DenemeSonucu(False, None, int((time.monotonic() - bas) * 1000), None, f"adres_{h.kod}"[:200])
    try:
        async with _istemci() as istemci:
            istek = istemci.build_request("POST", url, content=govde.encode("utf-8"), headers=basliklar)
            yanit = await asyncio.wait_for(istemci.send(istek, stream=True), timeout=ZAMAN_ASIMI + 2)
            try:
                parcalar: List[bytes] = []
                boyut = 0
                async for parca in yanit.aiter_bytes():
                    parcalar.append(parca)
                    boyut += len(parca)
                    if boyut >= YANIT_SINIRI:
                        break
                metin = b"".join(parcalar)[:YANIT_SINIRI].decode("utf-8", errors="replace")
            finally:
                await yanit.aclose()
            sure = int((time.monotonic() - bas) * 1000)
            basarili = 200 <= yanit.status_code < 300
            hata = None if basarili else (f"http_{yanit.status_code}")
            return DenemeSonucu(basarili, yanit.status_code, sure, metin or None, hata)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return DenemeSonucu(False, None, int((time.monotonic() - bas) * 1000), None, "zaman_asimi")
    except httpx.HTTPError as h:
        mesaj = str(h) or type(h).__name__
        kod = "adres_yasak" if "adres reddedildi" in mesaj else "baglanti_hatasi"
        return DenemeSonucu(False, None, int((time.monotonic() - bas) * 1000), None, f"{kod}: {mesaj}"[:200])
    except Exception as h:  # noqa: BLE001
        return DenemeSonucu(False, None, int((time.monotonic() - bas) * 1000), None, f"hata: {type(h).__name__}"[:200])


def basliklari_kur(uc: WebhookUcNoktalari, olay_id: str, govde: str, zaman: Optional[str] = None) -> Dict[str, str]:
    zaman = zaman or str(int(time.time()))
    gizliler = _gizliler(uc)
    if not gizliler:
        raise ApiHatasi(500, "gizli_cozulemedi")
    return {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "*/*",
        "User-Agent": AJAN,
        "MK-Webhook-Id": olay_id,
        "MK-Webhook-Zaman": zaman,
        "MK-Webhook-Imza": imza_basligi(gizliler, zaman, govde),
    }


async def _kilitle(db: AsyncSession, teslimat_id: int, *, yalniz_bekleyen: bool) -> bool:
    an = simdi()
    kosul = [
        WebhookTeslimatlari.id == teslimat_id,
        or_(WebhookTeslimatlari.kilit_bitis.is_(None), WebhookTeslimatlari.kilit_bitis <= an),
    ]
    if yalniz_bekleyen:
        kosul.append(WebhookTeslimatlari.durum == "bekliyor")
    sonuc = await db.execute(
        update(WebhookTeslimatlari)
        .where(and_(*kosul))
        .values(kilit_bitis=an + KILIT_SURESI)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(sonuc.rowcount or 0) == 1


async def _modul_acik_mi(db: AsyncSession, uc: WebhookUcNoktalari) -> bool:
    if uc.sahip_tur != "musteri":
        return True
    from services import moduller as _moduller

    return await _moduller.modul_acik_mi(db, uc.hesap_email or "", "api_erisimi")


async def teslim_et(db: AsyncSession, teslimat_id: int, *, tetik: str = "otomatik") -> Dict[str, Any]:
    """Tek deneme. Kilit alınamazsa {"atlandi": "kilitli"}. Sonuç teslimat sözlüğü."""
    if not await _kilitle(db, teslimat_id, yalniz_bekleyen=tetik == "otomatik"):
        return {"atlandi": "kilitli"}
    t = (
        await db.execute(
            select(WebhookTeslimatlari)
            .where(WebhookTeslimatlari.id == teslimat_id)
            .execution_options(populate_existing=True)
        )
    ).scalars().first()
    if t is None:
        return {"atlandi": "yok"}
    uc = (
        await db.execute(
            select(WebhookUcNoktalari).where(WebhookUcNoktalari.id == t.uc_id).execution_options(populate_existing=True)
        )
    ).scalars().first()
    an = simdi()
    if uc is None or (tetik == "otomatik" and not uc.aktif) or not await _modul_acik_mi(db, uc):
        sebep = "uc_yok" if uc is None else ("uc_pasif" if not uc.aktif else "modul_kapali")
        await db.execute(
            update(WebhookTeslimatlari)
            .where(WebhookTeslimatlari.id == t.id)
            .values(durum="atlandi", son_hata=sebep, kilit_bitis=None, updated_at=an)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return {"atlandi": sebep}

    try:
        basliklar = basliklari_kur(uc, t.olay_id, t.govde)
        sonuc = await _http_gonder(uc.url, t.govde, basliklar)
    except ApiHatasi as h:
        sonuc = DenemeSonucu(False, None, 0, None, h.kod)
    an = simdi()
    deneme_no = int(t.deneme_sayisi or 0) + 1
    # Core INSERT: deneme kaydı denetim kaydına düşmesin (her denemede bir satır olurdu).
    await db.execute(WebhookDenemeleri.__table__.insert().values(
        teslimat_id=t.id, deneme_no=deneme_no, tetik=tetik, durum_kodu=sonuc.durum_kodu, sure_ms=sonuc.sure_ms,
        yanit=sonuc.yanit, hata=sonuc.hata, basarili=sonuc.basarili, created_at=an,
    ))
    if sonuc.basarili:
        yeni_durum, sonraki = "basarili", None
    elif t.tur == PING and tetik != "otomatik":
        # Test olayı otomatik yeniden denenmez (kullanıcı sonucu panelde görüyor).
        yeni_durum, sonraki = "vazgecildi", None
    elif t.durum in ("basarili", "vazgecildi", "atlandi") and tetik != "otomatik":
        # Elle yeniden gönderim başarısız: kesinleşmiş durum değişmiyor.
        yeni_durum, sonraki = t.durum, t.sonraki_deneme
    elif deneme_no >= EN_COK_DENEME or an - (utc(t.created_at) or an) >= VAZGECME_SURESI:
        yeni_durum, sonraki = "vazgecildi", None
    else:
        yeni_durum, sonraki = "bekliyor", an + TEKRAR_ARALIKLARI[min(deneme_no, len(TEKRAR_ARALIKLARI)) - 1]
    await db.execute(
        update(WebhookTeslimatlari)
        .where(WebhookTeslimatlari.id == t.id)
        .values(
            durum=yeni_durum, deneme_sayisi=deneme_no, sonraki_deneme=sonraki, kilit_bitis=None,
            son_durum_kodu=sonuc.durum_kodu, son_sure_ms=sonuc.sure_ms, son_yanit=sonuc.yanit, son_hata=sonuc.hata,
            updated_at=an,
        )
        .execution_options(synchronize_session=False)
    )
    # Uç noktası sayaçları (Core: denetim kaydına her denemede satır düşmesin).
    if sonuc.basarili:
        await db.execute(
            update(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc.id)
            .values(ardisik_hata=0, son_basari_at=an).execution_options(synchronize_session=False)
        )
    elif tetik == "otomatik":
        await db.execute(
            update(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc.id)
            .values(ardisik_hata=WebhookUcNoktalari.ardisik_hata + 1, son_hata_at=an)
            .execution_options(synchronize_session=False)
        )
    else:
        await db.execute(
            update(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc.id)
            .values(son_hata_at=an).execution_options(synchronize_session=False)
        )
    await db.commit()
    if not sonuc.basarili and tetik == "otomatik":
        await _pasiflestirme_denetimi(db, uc.id)
    return {
        "teslimat_id": t.id,
        "durum": yeni_durum,
        "basarili": sonuc.basarili,
        "durum_kodu": sonuc.durum_kodu,
        "sure_ms": sonuc.sure_ms,
        "hata": sonuc.hata,
        "deneme_no": deneme_no,
    }


async def _pasiflestirme_denetimi(db: AsyncSession, uc_id: int) -> bool:
    uc = (await db.execute(select(WebhookUcNoktalari).where(WebhookUcNoktalari.id == uc_id))).scalars().first()
    if uc is None:
        return False
    await db.refresh(uc)
    if not uc.aktif or int(uc.ardisik_hata or 0) < OTOMATIK_PASIF_ESIGI:
        return False
    uc.aktif = False
    uc.pasif_sebebi = "ardisik_hata"
    try:
        from services.denetim import aktor_ata

        aktor_ata(None, "sistem")
    except Exception:  # noqa: BLE001
        pass
    await db.commit()
    an = simdi()
    await db.execute(
        update(WebhookTeslimatlari)
        .where(WebhookTeslimatlari.uc_id == uc_id, WebhookTeslimatlari.durum == "bekliyor")
        .values(durum="vazgecildi", son_hata="uc_pasiflesti", sonraki_deneme=None, updated_at=an)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    onbellegi_temizle()
    await _pasif_bildirimi(db, uc)
    return True


async def _pasif_bildirimi(db: AsyncSession, uc: WebhookUcNoktalari) -> None:
    try:
        from services.notify import admin_recipients, dispatch

        if uc.sahip_tur == "ajans":
            alicilar = await admin_recipients(db)
            link = "/admin?sekme=api"
        else:
            alicilar = [{"email": uc.hesap_email, "role": "client", "phone": ""}]
            link = "/client?sekme=api"
        await dispatch(
            db,
            event_type="webhook_pasiflesti",
            title="Webhook uç noktası durduruldu / Webhook endpoint disabled",
            body=(
                f"{uc.url} adresine art arda {OTOMATIK_PASIF_ESIGI} teslimat başarısız oldu; uç noktası otomatik "
                "olarak pasifleştirildi. Sorunu giderip panelden yeniden açabilirsiniz.\n\n"
                f"{OTOMATIK_PASIF_ESIGI} consecutive deliveries to {uc.url} failed; the endpoint was disabled "
                "automatically. Fix the receiver and re-enable it in the panel."
            ),
            recipients=alicilar,
            link=link,
            ref_type="webhook_uc_noktalari",
            ref_id=uc.id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Webhook pasifleştirme bildirimi gönderilemedi")


async def bekleyenleri_isle(db: AsyncSession, *, yalniz_ilk: bool = False, sinir: int = TUR_SINIRI) -> Dict[str, Any]:
    """Zamanı gelmiş teslimatlar. Her deneme kendi oturumunda (paralel, en çok `ESZAMANLILIK`)."""
    from core.database import db_manager

    an = simdi()
    sorgu = (
        select(WebhookTeslimatlari.id, WebhookTeslimatlari.uc_id)
        .where(
            WebhookTeslimatlari.durum == "bekliyor",
            or_(WebhookTeslimatlari.sonraki_deneme.is_(None), WebhookTeslimatlari.sonraki_deneme <= an),
            or_(WebhookTeslimatlari.kilit_bitis.is_(None), WebhookTeslimatlari.kilit_bitis <= an),
        )
        .order_by(WebhookTeslimatlari.sonraki_deneme.asc(), WebhookTeslimatlari.id.asc())
        .limit(sinir)
    )
    if yalniz_ilk:
        sorgu = sorgu.where(WebhookTeslimatlari.deneme_sayisi == 0)
    satirlar = (await db.execute(sorgu)).all()
    await db.commit()
    ozet = {"islenen": 0, "basarili": 0, "basarisiz": 0, "atlanan": 0}
    if not satirlar:
        return ozet
    baslangic = time.monotonic()
    dusen_uclar: set = set()
    kilit = asyncio.Semaphore(ESZAMANLILIK)

    async def _tek(teslimat_id: int, uc_id: int) -> None:
        async with kilit:
            # Aynı turda başarısız olan uç noktasının diğer teslimatları bir sonraki tura.
            if uc_id in dusen_uclar or time.monotonic() - baslangic > TUR_BUTCESI_SN:
                return
            try:
                if db_manager.async_session_maker is None:
                    return
                async with db_manager.async_session_maker() as oturum:
                    sonuc = await teslim_et(oturum, teslimat_id)
            except Exception:  # noqa: BLE001
                logger.exception("Webhook teslimatı işlenemedi (id=%s)", teslimat_id)
                return
            if "atlandi" in sonuc:
                ozet["atlanan"] += 1
                return
            ozet["islenen"] += 1
            if sonuc.get("basarili"):
                ozet["basarili"] += 1
            else:
                ozet["basarisiz"] += 1
                dusen_uclar.add(uc_id)

    await asyncio.gather(*(_tek(int(s[0]), int(s[1])) for s in satirlar))
    return ozet


async def test_gonder(db: AsyncSession, uc: WebhookUcNoktalari, kisi: Optional[str]) -> Dict[str, Any]:
    """`ping` olayı: yalnız bu uç noktasına, hemen (abonelikten bağımsız)."""
    an = simdi()
    olay_id = olay_kimligi()
    veri = {"mesaj": "Test olayı / Test event", "uc_id": uc.id}
    govde = olay_govdesi(olay_id, PING, uc.hesap_email, veri, an)
    sonuc_ekle = await db.execute(WebhookTeslimatlari.__table__.insert().values(
        uc_id=uc.id, olay_id=olay_id, tur=PING, hesap_email=uc.hesap_email, govde=govde, durum="bekliyor",
        deneme_sayisi=0, sonraki_deneme=None, created_at=an, updated_at=an,
    ))
    teslimat_id = int(sonuc_ekle.inserted_primary_key[0])
    await db.commit()
    sonuc = await teslim_et(db, teslimat_id, tetik="test")
    return {**sonuc, "olay_id": olay_id}


async def yeniden_gonder(db: AsyncSession, teslimat: WebhookTeslimatlari) -> Dict[str, Any]:
    sonuc = await teslim_et(db, teslimat.id, tetik="elle")
    if sonuc.get("atlandi") == "kilitli":
        raise ApiHatasi(409, "teslimat_gonderiliyor")
    return sonuc


async def teslimat_bul(db: AsyncSession, uc: WebhookUcNoktalari, teslimat_id: int) -> WebhookTeslimatlari:
    t = (
        await db.execute(
            select(WebhookTeslimatlari).where(WebhookTeslimatlari.id == teslimat_id, WebhookTeslimatlari.uc_id == uc.id)
        )
    ).scalars().first()
    if t is None:
        raise ApiHatasi(404, "bulunamadi")
    return t


def teslimat_sozlugu(t: WebhookTeslimatlari, denemeler: Optional[List[WebhookDenemeleri]] = None) -> Dict[str, Any]:
    try:
        govde = json.loads(t.govde)
    except (TypeError, ValueError):
        govde = None
    d = {
        "id": t.id,
        "olay_id": t.olay_id,
        "tur": t.tur,
        "durum": t.durum,
        "deneme_sayisi": int(t.deneme_sayisi or 0),
        "sonraki_deneme": iso(t.sonraki_deneme) if t.durum == "bekliyor" else None,
        "son_durum_kodu": t.son_durum_kodu,
        "son_sure_ms": t.son_sure_ms,
        "son_yanit": t.son_yanit,
        "son_hata": t.son_hata,
        "govde": govde,
        "olusturma": iso(t.created_at),
        "guncelleme": iso(t.updated_at),
    }
    if denemeler is not None:
        d["denemeler"] = [
            {
                "deneme_no": x.deneme_no,
                "tetik": x.tetik,
                "durum_kodu": x.durum_kodu,
                "sure_ms": x.sure_ms,
                "yanit": x.yanit,
                "hata": x.hata,
                "basarili": bool(x.basarili),
                "zaman": iso(x.created_at),
            }
            for x in denemeler
        ]
    return d


_son_temizlik: Dict[str, float] = {"an": 0.0}


async def teslimatlar(db: AsyncSession, uc: WebhookUcNoktalari, *, limit: int = 25, once: Optional[int] = None,
                      durum: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """Teslimat geçmişi (yeniden eskiye) + her birinin denemeleri. İkinci değer: sonraki sayfa için `once`."""
    if time.monotonic() - _son_temizlik["an"] > 3600:
        _son_temizlik["an"] = time.monotonic()
        try:
            await temizle(db)
        except Exception:  # noqa: BLE001
            await db.rollback()
            logger.exception("Webhook kayıt temizliği yapılamadı")
    sorgu = select(WebhookTeslimatlari).where(WebhookTeslimatlari.uc_id == uc.id)
    if once:
        sorgu = sorgu.where(WebhookTeslimatlari.id < once)
    if durum:
        sorgu = sorgu.where(WebhookTeslimatlari.durum == durum)
    liste = list((await db.execute(sorgu.order_by(WebhookTeslimatlari.id.desc()).limit(limit + 1))).scalars().all())
    daha = len(liste) > limit
    liste = liste[:limit]
    denemeler: Dict[int, List[WebhookDenemeleri]] = {}
    if liste:
        for x in (
            await db.execute(
                select(WebhookDenemeleri)
                .where(WebhookDenemeleri.teslimat_id.in_([t.id for t in liste]))
                .order_by(WebhookDenemeleri.id.asc())
            )
        ).scalars().all():
            denemeler.setdefault(x.teslimat_id, []).append(x)
    return [teslimat_sozlugu(t, denemeler.get(t.id, [])) for t in liste], (liste[-1].id if daha and liste else None)


async def temizle(db: AsyncSession) -> Dict[str, int]:
    """30 günden eski teslimat/deneme ve 24 saati geçen idempotency kayıtları."""
    from models.api_erisimi import ApiIdempotency
    from services.api_erisimi import IDEMPOTENCY_SURESI

    an = simdi()
    sinir = an - SAKLAMA_SURESI
    eski = select(WebhookTeslimatlari.id).where(WebhookTeslimatlari.created_at < sinir)
    d = await db.execute(delete(WebhookDenemeleri).where(WebhookDenemeleri.teslimat_id.in_(eski)))
    t = await db.execute(delete(WebhookTeslimatlari).where(WebhookTeslimatlari.created_at < sinir))
    i = await db.execute(delete(ApiIdempotency).where(ApiIdempotency.created_at < an - IDEMPOTENCY_SURESI))
    await db.commit()
    return {"teslimat": int(t.rowcount or 0), "deneme": int(d.rowcount or 0), "idempotency": int(i.rowcount or 0)}


__all__ = [
    "OLAY_TURLERI", "PING", "imza_hesapla", "imza_dogrula", "olay_yayinla", "olay_yaz_sync", "aday_verisi",
    "bekleyenleri_isle", "teslim_et", "test_gonder", "temizle", "OlayAbonesi", "abone_ekle", "olaylari_yayinla_sync",
]
