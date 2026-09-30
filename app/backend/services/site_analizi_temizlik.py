"""1A site analizlerinin saklama temizliği (zamanlı görev, haftada bir).

Kural
-----
* Herkese açık formdan gelen (`kaynak == "acik"`) analizler 90 günden
  eskiyse ve rapor bağlantısının süresi dolmuşsa SİLİNİYOR. Bu kayıtlar
  sınır sayımı için tutuluyordu (günlük sayım), 90 günlük kayıt o işe
  yaramıyor; KVKK açısından da gereksiz kişisel veri (e-posta) taşıyor.
  Talebe dönüşmüş olanlar (`inquiry_id` dolu) talep kaydıyla bağlı, kalıyor.
* Müşteri/yönetici analizlerinin 365 günden eskilerinin yalnız AĞIR
  kısmı (`rapor_json`, tam ayrıntı) boşaltılıyor; puan ve özet duruyor —
  müşteri "bir yıl önce puanım neydi" diye bakabilsin.
* 1 saatten uzun "calisiyor" kalmış kayıt (süreç analiz ortasında öldü)
  "hata / zaman_asimi" yapılıyor; yoksa sınıra sayılmaya devam ederdi.

`site_analyses` denetim kaydının dışında (gürültülü tablo); toplu (Core)
ifadeler kullanılıyor.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from models.site_analyses import Site_analyses
from sqlalchemy import and_, delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

ACIK_SAKLAMA_GUN = 90
AYRINTI_SAKLAMA_GUN = 365
TAKILI_SURE = timedelta(hours=1)


async def eski_analizleri_temizle(db: AsyncSession) -> Dict[str, Any]:
    an = datetime.now(timezone.utc)
    silinen = await db.execute(
        delete(Site_analyses).where(
            Site_analyses.kaynak == "acik",
            Site_analyses.inquiry_id.is_(None),
            Site_analyses.created_at < an - timedelta(days=ACIK_SAKLAMA_GUN),
            or_(Site_analyses.jeton_son.is_(None), Site_analyses.jeton_son < an),
        )
    )
    bosaltilan = await db.execute(
        update(Site_analyses)
        .where(
            Site_analyses.kaynak != "acik",
            Site_analyses.rapor_json.isnot(None),
            Site_analyses.created_at < an - timedelta(days=AYRINTI_SAKLAMA_GUN),
        )
        .values(rapor_json=None)
        .execution_options(synchronize_session=False)
    )
    takili = await db.execute(
        update(Site_analyses)
        .where(and_(Site_analyses.durum == "calisiyor", Site_analyses.created_at < an - TAKILI_SURE))
        .values(durum="hata", hata_kodu="zaman_asimi")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return {
        "silinen": int(silinen.rowcount or 0),
        "ayrinti_bosaltilan": int(bosaltilan.rowcount or 0),
        "takili_duzeltilen": int(takili.rowcount or 0),
    }
