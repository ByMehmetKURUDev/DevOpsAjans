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
    #: Faz 7O — sıklıktan farklı bir takvimi olan iş için panelde gösterilecek plan anahtarı
    #: (ör. "haftalik_pazartesi": 30 dakikada bir denetlenir ama haftada bir gönderir).
    plan: Optional[str] = None


# ---------------------------------------------------------------------------
# Görevler
# ---------------------------------------------------------------------------
async def _ortaklik_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    """Faz 5K — iade süresi dolan (beklemedeki) komisyonlar onaylanır (panel açılışında da)."""
    from services.ortaklik import zamanli_gorev

    return await zamanli_gorev(db, zorla)


async def _toplanti_hatirlatmalari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    """Faz 6T — toplantıdan 24 saat ve 1 saat önce katılımcılara hatırlatma (her biri bir kez; panel açılınca da)."""
    from services.toplantilar import hatirlatmalari_gonder

    return await hatirlatmalari_gonder(db)


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


async def _saklama_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 7H: 13 aydan eski ham analiz olayları (QR, kartvizit/yorum, kampanya tıklaması önce günlük
    # özete; menü/randevu olayları yalnız silinir) ve penceresi geçmiş kalıcı hız sayaçları.
    from services.analiz_saklama import saklama_temizligi

    return await saklama_temizligi(db)


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


async def _seo_taramasi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # `zorla` (yöneticinin "Şimdi çalıştır"ı) site başına sıklığı ATLAMIYOR:
    # her basışta 3 sitenin PageSpeed kotası harcanmasın.
    from services.seo_izleme import zamanli_tarama

    return await zamanli_tarama(db)


async def _oturum_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.oturumlar import temizle

    return await temizle(db)


async def _cop_kutusu_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.cop_kutusu import suresi_dolanlari_temizle

    return await suresi_dolanlari_temizle(db)


async def _mesaj_bildirimleri(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.mesajlar import bildirimleri_isle

    return await bildirimleri_isle(db)


async def _tekrarlayan_faturalar(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 3T: dönem kilidi benzersiz — "Şimdi çalıştır" da aynı dönemi ikinci kez kesmez.
    from services.faturalar import tekrarlayan_faturalari_uret

    return await tekrarlayan_faturalari_uret(db)


async def _fatura_hatirlatmalari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.faturalar import vade_hatirlatmalari

    return await vade_hatirlatmalari(db)


async def _teklif_ve_sozlesme(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    from services.sozlesmeler import bitis_hatirlatmalari
    from services.teklifler import sureleri_isle

    teklif = await sureleri_isle(db)
    sozlesme = await bitis_hatirlatmalari(db)
    return {"teklif": teklif, "sozlesme": sozlesme}


async def _google_esitleme(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 3B: GA4 + Search Console + YouTube → analytics_snapshots. Her Google
    # isteği 10 sn, kaynak başına 20 sn (paralel) — tur kısa kalıyor. `zorla`
    # (yöneticinin "Şimdi çalıştır"ı) 6 saatlik sıklığı atlıyor; Google kotası
    # bunu rahat kaldırıyor (bağlantı başına ~7 istek).
    from services.google_esitleme import zamanli_esitleme

    return await zamanli_esitleme(db)


async def _crm_bildirimleri(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 3C: kendi bildirimi olmayan kaynaktan (fiyat teklifi) açılan yeni adaylar.
    from services.crm import bekleyen_bildirimleri_gonder

    return await bekleyen_bildirimleri_gonder(db)


async def _crm_hatirlatma(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 3C: sonraki adım tarihi gelen açık adaylar — alıcı başına günlük özet.
    # Aday başına `hatirlatma_tarihi` aynı gün ikinci gönderimi engelliyor
    # ("Şimdi çalıştır" da aynı adayı ikinci kez göndermez).
    from services.crm import hatirlatmalari_gonder

    return await hatirlatmalari_gonder(db)


async def _webhook_teslimatlari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 4A: zamanı gelen webhook yeniden denemeleri (üstel geri çekilme; 3 gün sonra vazgeçilir).
    from services.webhook import bekleyenleri_isle

    return await bekleyenleri_isle(db)


async def _webhook_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 4A: 30 günden eski teslimat/deneme kayıtları ve 24 saati geçen idempotency kayıtları.
    from services.webhook import temizle

    return await temizle(db)
async def _randevu_hatirlatmalari(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 5R: randevu hatırlatmaları (ör. 24 saat ve 1 saat önce) — her turda (ucuz
    # sorgu). `randevu_hatirlatmalari` benzersizliği her hatırlatmanın tek kez gitmesini
    # sağlıyor ("Şimdi çalıştır" da ikinci kez göndermez). Saklama süresi dolan
    # randevuların kişisel alanları da burada anonimleşiyor.
    from services.randevu_kayit import hatirlatmalari_gonder

    return await hatirlatmalari_gonder(db)


async def _otomasyon(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 4W: `fatura.gecikti` olayı (fatura + eşik başına bir kez) ve kuyrukta bekleyen /
    # "bekle" eyleminden sonra zamanı gelen otomasyon çalıştırmaları (süre bütçeli).
    from services.otomasyon import zamanli_gorev

    return await zamanli_gorev(db, zorla)


async def _otomasyon_temizligi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 4W: 30 günden eski otomasyon çalıştırma kayıtları.
    from services.otomasyon import temizle

    return await temizle(db)
async def _ai_asistan_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 5A: AI asistan — "haftalık yenile" işaretli URL kaynakları (tur başına en çok 2) ve
    # saklama süresi dolan sohbetlerin silinmesi.
    from services.ai_asistan import bakim_calistir

    return await bakim_calistir(db)
async def _icerik_studyosu(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 5I: planlanan saatten 30 dk önce "paylaşıma hazır" hatırlatması ve onaylı gönderide
    # `icerik.yayin_zamani` olayı — ikisi de gönderi başına TEK KEZ (koşullu UPDATE).
    from services.icerik_planlayici import zamanli_gorev

    return await zamanli_gorev(db)


async def _eposta_pazarlama(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 5M: zamanı gelen kampanyalar, A/B kararı, damla dizisi adımları ve kuyruktaki iletiler
    # (tur başına süre ve ileti bütçesi; Resend hız sınırı). Satırlar tek kez gönderilir.
    from services.eposta_gonderim import zamanli_isle

    return await zamanli_isle(db)


async def _saha_servisi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 6S: bakım zamanı gelen cihazlar (hesap başına tek özet bildirim; cihaz başına vade başına
    # bir kez), rızayla alınmış ham konumun 90 gün sonra silinmesi, saklama süresi dolan servis
    # müşterisinin anonimleşmesi.
    from services.saha_kayit import zamanli_gorev

    return await zamanli_gorev(db)


async def _haftalik_ozet(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 7O: Pazartesi 08:00'den (İstanbul) sonraki ilk turda, ISO hafta başına bir kez yöneticiye özet.
    # `zorla` (yöneticinin "Şimdi çalıştır"ı) pencereyi ve hafta kilidini ATLAMIYOR: ikinci özet gitmez.
    from services.haftalik_ozet import gonder

    return await gonder(db)


async def _etkinlik_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 6E: ödemesi gelmeyen kayıtların yerleri ve süresi geçen davetler bırakılır, yer açılan
    # etkinlikte bekleme listesine 24 saatlik davet gider, biten etkinlik "tamamlandı" olur, teşekkür +
    # anket e-postası (tur başına bütçeli, sipariş başına bir kez) ve saklama süresi dolan kişisel veri.
    from services.etkinlik_kayit import zamanli_bakim

    return await zamanli_bakim(db)


async def _egitim_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 6K: ders hatırlatmaları (oturum başına bir kez), devamsızlık eşiği (öğrenci başına bir kez
    # bilgilendirme + `egitim.devamsizlik`), biten kurs → tamamlandı (+ "otomatik sertifika"), saklama süresi
    # dolan öğrenci/veli kişisel verisinin anonimleştirilmesi.
    from services.egitim_kayit import zamanli_bakim

    return await zamanli_bakim(db)


async def _hukuk_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 6H: duruşma/keşif/bilirkişi/kesin süre/görev hatırlatmaları (7/3/1 gün önce + aynı gün sabah; olay ×
    # eşik başına BİR KEZ, içeriksiz bildirim — e-posta yoksa panel) ve 30 günü dolan silinen müvekkil/dosyaların
    # kalıcı silinmesi.
    from services.hukuk_kayit import zamanli_bakim

    return await zamanli_bakim(db)


async def _muhasebe_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 6M: ön muhasebe — vadesi gelen tekrarlayan kayıtlar (dönem başına bir kez), açık otomatik aktarmalar (ödenen
    # fatura / POS gün sonu / hukuk masrafı / saha işi; tekil + ters kayıt) ve bütçe aşımı (kategori × ay başına bir olay).
    from services.muhasebe_kayit import zamanli_bakim

    return await zamanli_bakim(db)


async def _okr_bakimi(db: AsyncSession, zorla: bool) -> Dict[str, Any]:
    # Faz 6O: OKR — açık dönemlerin otomatik KR kaynaklarını yenile (KR başına saatte bir) ve 7 gündür check-in almamış
    # etkin elle KR'lerin sahibine haftalık hatırlatma (KR başına 7 günde en çok bir).
    from services.okr_kayit import zamanli_bakim

    return await zamanli_bakim(db)


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
    Gorev("saklama_temizligi", timedelta(hours=20), _saklama_temizligi),
    # Faz 2D: 30 günden eski biten/iptal oturumlar; saklama süresi dolan çöp kutusu.
    Gorev("oturum_temizligi", timedelta(hours=20), _oturum_temizligi),
    Gorev("cop_kutusu_temizligi", timedelta(hours=20), _cop_kutusu_temizligi),
    # Faz 2G: okunmamış mesaj bildirimi her turda (ucuz sorgu; 2 dk gecikme + 30 dk toplama).
    Gorev("mesaj_bildirimleri", timedelta(0), _mesaj_bildirimleri),
    # Faz 2H: teknik SEO + hız izleme — tur başına en çok 3 site (paralel, dış ağ).
    Gorev("seo_taramasi", timedelta(minutes=55), _seo_taramasi),
    # Faz 3B: Google bağlantısı (ajans) — GA4 / Search Console / YouTube eşitlemesi.
    Gorev("google_esitleme", timedelta(hours=6), _google_esitleme),
    # Faz 3C: CRM — yeni aday bildirimi her turda (ucuz sorgu), hatırlatma günde bir.
    Gorev("crm_bildirimleri", timedelta(0), _crm_bildirimleri),
    Gorev("crm_hatirlatma", timedelta(hours=20), _crm_hatirlatma),
    # Faz 3T: tekrarlayan fatura (dönem başına bir kez), vade +1/+7/+14 hatırlatması,
    # süresi dolan teklifler ve sözleşme bitişi (30/7 gün).
    Gorev("tekrarlayan_faturalar", timedelta(hours=6), _tekrarlayan_faturalar),
    Gorev("fatura_hatirlatmalari", timedelta(hours=6), _fatura_hatirlatmalari),
    Gorev("teklif_ve_sozlesme", timedelta(hours=6), _teklif_ve_sozlesme),
    # Faz 4A: webhook yeniden denemeleri her turda (ucuz sorgu; tur başına süre bütçeli), temizlik günde bir.
    Gorev("webhook_teslimatlari", timedelta(0), _webhook_teslimatlari),
    Gorev("webhook_temizligi", timedelta(hours=20), _webhook_temizligi),
    Gorev("randevu_hatirlatmalari", timedelta(0), _randevu_hatirlatmalari),
    Gorev("otomasyon", timedelta(0), _otomasyon),
    Gorev("otomasyon_temizligi", timedelta(hours=20), _otomasyon_temizligi),
    Gorev("ai_asistan_bakimi", timedelta(hours=1), _ai_asistan_bakimi),
    Gorev("icerik_studyosu", timedelta(0), _icerik_studyosu),
    Gorev("eposta_pazarlama", timedelta(0), _eposta_pazarlama),
    Gorev("saha_servisi", timedelta(hours=20), _saha_servisi),
    Gorev("etkinlik_bakimi", timedelta(0), _etkinlik_bakimi),
    Gorev("egitim_bakimi", timedelta(0), _egitim_bakimi),
    Gorev("hukuk_bakimi", timedelta(0), _hukuk_bakimi),
    Gorev("muhasebe_bakimi", timedelta(minutes=30), _muhasebe_bakimi),
    Gorev("okr_bakimi", timedelta(minutes=30), _okr_bakimi),
    Gorev("ortaklik_bakimi", timedelta(hours=6), _ortaklik_bakimi),
    # Faz 6T: her turda (ucuz sorgu; 24 sa / 1 sa eşiği kaçmasın).
    Gorev("toplanti_hatirlatmalari", timedelta(0), _toplanti_hatirlatmalari),
    Gorev("haftalik_ozet", timedelta(minutes=30), _haftalik_ozet, plan="haftalik_pazartesi"),
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
            {"gorev": g.ad, "siklik_dk": int(g.siklik.total_seconds() // 60), "plan": g.plan, **sozluk(satirlar.get(g.ad))}
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
