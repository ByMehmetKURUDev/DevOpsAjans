from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Client_sites(Base):
    """Müşterinin bizim baktığımız sitesi.

    Burada müşterinin şifresi TUTULMUYOR ve tutulmayacak. Bakım için
    ajansın kendi hesabı açılıyor, o hesapla girilen her işlem
    `access_log` tablosuna yazılıyor. Müşteri panelden `bakim_izni`
    anahtarını kapattığı anda ajansın erişim kaydı açma hakkı bitiyor.

    Şifreyi panelde saklasaydık müşterinin sitesinin anahtarı bizde
    dururdu; panel bir gün ele geçse müşterinin sitesi de giderdi.
    Ayrı hesap + günlük, hem geri alınabilir hem denetlenebilir.

    `widget_jetonu` müşterinin sitesine gömülen geri bildirim
    düğmesinin kimliği. Adres değil jeton kullanıyoruz: jeton
    sızarsa tek bir siteyi iptal edip yenisini üretmek yetiyor.
    """

    __tablename__ = "client_sites"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_email = Column(String, index=True, nullable=False)
    ad = Column(String, nullable=False)
    adres = Column(String, nullable=True)
    # wordpress | custom | shopify | wix | diger
    platform = Column(String, nullable=True)
    # aktif | beklemede | bitti
    durum = Column(String, nullable=True)

    # Bakım erişimi. Varsayılan KAPALI: izin, müşteri açıkça verene
    # kadar yok sayılıyor.
    bakim_izni = Column(Boolean, nullable=True, default=False)
    izin_at = Column(DateTime(timezone=True), nullable=True)
    izin_notu = Column(String, nullable=True)

    # Geri bildirim düğmesi
    widget_jetonu = Column(String, index=True, nullable=True)
    widget_acik = Column(Boolean, nullable=True, default=True)

    # Bu siteye bakan ekip üyesi (staff.email).
    atanan = Column(String, index=True, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
