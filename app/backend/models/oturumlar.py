"""Faz 2D — oturumlar ve kullanıcı bazlı jeton kesimi.

* `oturumlar`: verilen her uygulama jetonunun (JWT) kaydı. Jetonda rastgele
  bir `sid` taşınıyor; satır iptal edilince (`iptal_zamani`) o jeton, süresi
  dolmamış olsa bile reddediliyor. Ham IP yok: yalnız tuzlu sha256 özetinin
  kısaltması. User-Agent en çok 300 karakter; ekranda gösterilen kısa ad
  (`cihaz`: "Chrome · macOS") ayrıca tutuluyor.
* `oturum_kesimleri`: "bu e-postaya bu andan önce verilmiş TÜM jetonlar
  geçersiz" — `sid` taşımayan eski jetonları da düşürmenin tek yolu.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class Oturumlar(Base):
    __tablename__ = "oturumlar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Jetondaki rastgele oturum kimliği (token_urlsafe(18)). API yanıtlarında DÖNMEZ.
    sid = Column(String(64), unique=True, index=True, nullable=False)
    kullanici_id = Column(String, index=True, nullable=True)
    #: Küçük harf.
    email = Column(String, index=True, nullable=False)
    rol = Column(String, nullable=True)
    olusturma = Column(DateTime(timezone=True), default=_simdi, index=True)
    #: En çok 5 dakikada bir güncelleniyor (her istekte yazmamak için).
    son_gorulme = Column(DateTime(timezone=True), default=_simdi)
    #: Jetonun `exp` zamanı: bundan sonra satır zaten geçersiz.
    bitis = Column(DateTime(timezone=True), index=True, nullable=True)
    #: sha256(IP_OZET_TUZU + ip) ilk 16 hanesi.
    ip_ozet = Column(String(64), nullable=True)
    #: Okunur kısa ad: "Chrome · macOS".
    cihaz = Column(String(80), nullable=True)
    user_agent = Column(String(300), nullable=True)
    iptal_zamani = Column(DateTime(timezone=True), nullable=True, index=True)
    #: İptal eden kişinin e-postası (ya da "sistem").
    iptal_eden = Column(String, nullable=True)


class OturumKesimleri(Base):
    __tablename__ = "oturum_kesimleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    #: Bu andan önce verilen (iat < gecersiz_once) jetonlar reddediliyor.
    gecersiz_once = Column(DateTime(timezone=True), nullable=False)
    guncelleyen = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)
