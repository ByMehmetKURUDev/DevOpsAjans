from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Staff(Base):
    """Ajans ekibi.

    Bu tablo yetki tablosu değil, ekip listesi. Yöneticiliği hâlâ
    kullanıcı hesabının `role` alanı belirliyor. Buradaki kayıt bir
    kişiye talep atanabilmesini ve atandığı talebi görebilmesini
    sağlıyor — o kadar.

    Böyle ayırmanın nedeni: bir çalışana talep atayabilmek için ona
    yönetici yetkisi vermek gerekseydi, fatura ve site ayarları da
    açılırdı.

    `hizmetler` virgülle ayrılmış anahtar listesi (seo, website ...).
    Boşsa kişi her hizmete bakabiliyor demek.
    """

    __tablename__ = "staff"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ad = Column(String, nullable=False)
    email = Column(String, index=True, nullable=False)
    # yonetici | calisan
    rol = Column(String, nullable=True)
    hizmetler = Column(String, nullable=True)
    aktif = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
