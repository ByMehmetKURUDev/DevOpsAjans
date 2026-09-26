from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Access_log(Base):
    """Müşterinin sitesine yapılan her bakım erişiminin kaydı.

    Bu tablonun tek amacı müşterinin "siteme kim, ne zaman, ne için
    girdi" sorusunu panelden kendi başına cevaplayabilmesi. Kayıt
    silinmiyor: site listeden kaldırılsa bile günlük duruyor, yoksa
    denetim kaydı olmaktan çıkardı.

    `kim` ajans tarafındaki kişinin e-postası, `client_email` ise site
    sahibininki. İkisini birden yazıyoruz ki site silinse de satır tek
    başına okunabilsin.
    """

    __tablename__ = "access_log"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    site_id = Column(Integer, index=True, nullable=True)
    site_ad = Column(String, nullable=True)
    client_email = Column(String, index=True, nullable=False)
    kim = Column(String, nullable=False)
    # giris | guncelleme | yedek | eklenti | duzeltme | izin_acildi | izin_kapandi
    islem = Column(String, nullable=False)
    aciklama = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
