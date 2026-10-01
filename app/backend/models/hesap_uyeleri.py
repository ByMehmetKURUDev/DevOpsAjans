"""Faz 2E — bir müşteri hesabında birden çok kişi.

"Müşteri hesabı" bugünkü kimliğin kendisi: sahibinin e-postası. Kayıtlar
(proje, fatura, talep…) hâlâ o e-postaya bağlı; veri modeli değişmiyor,
mevcut kayıtlar taşınmıyor. Bu tablo yalnız "bu hesapta başka kim var,
hangi rol ve izinlerle" sorusunu tutuyor.

* Sahip kendisi satır olarak tutulmaz (örtük tam yetki).
* `davet_jetonu_ozet`: davet bağlantısındaki jetonun sha256 özeti; ham
  jeton veritabanına yazılmıyor. Kabulde boşaltılıyor (tek kullanımlık).
  Adında "jeton" geçtiği için denetim kaydında değeri zaten maskeli.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class HesapUyeleri(Base):
    __tablename__ = "hesap_uyeleri"
    __table_args__ = (
        UniqueConstraint("hesap_email", "uye_email", name="uq_hesap_uyeleri_hesap_uye"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Hesabın sahibi (küçük harf) — kayıtların bağlı olduğu e-posta.
    hesap_email = Column(String(254), index=True, nullable=False)
    #: Üye kişinin giriş e-postası (küçük harf).
    uye_email = Column(String(254), index=True, nullable=False)
    #: yonetici | uye | fatura
    rol = Column(String(20), nullable=False, default="uye")
    #: JSON: modül anahtarları listesi (services/hesap_ekibi.IZINLER).
    izinler = Column(Text, nullable=True)
    #: davet | aktif | pasif
    durum = Column(String(10), nullable=False, default="davet", index=True)
    davet_jetonu_ozet = Column(String(64), unique=True, index=True, nullable=True)
    davet_bitis = Column(DateTime(timezone=True), nullable=True)
    #: Ekleyen kişinin e-postası (sahip, hesap yöneticisi ya da ajans yöneticisi).
    ekleyen = Column(String(254), nullable=True)
    olusturma = Column(DateTime(timezone=True), default=_simdi)
    #: Üyenin bu hesapta en son ne zaman çalıştığı (en çok 5 dk'da bir yazılır).
    son_kullanim = Column(DateTime(timezone=True), nullable=True)
