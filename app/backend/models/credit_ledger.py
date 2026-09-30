from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Float, Integer, String


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class CreditLedger(Base):
    """Kredi defteri: Kullandıkça Öde'nin arka yüzü.

    1 kredi = 1 saat senior işçilik. Her hareket bir satır; satırlar hiç
    güncellenmiyor, yanlış bir hareket ancak ters yönde yeni bir satırla
    (`duzeltme`) düzeltiliyor. Bakiye bu satırlardan hesaplanıyor, ayrı bir
    "bakiye" sütunu yok — iki yerde tutulan sayı eninde sonunda ayrışır.

    Artı satırlar (yükleme) `son_kullanma` taşıyor (oluşturma + 365 gün);
    eksi satırlar (harcama, süre dolumu, eksi düzeltme) taşımıyor. Hangi
    harcamanın hangi yüklemeden düştüğü saklanmıyor; `services/kredi.py`
    satırları sırayla yeniden oynatarak (FIFO) hesaplıyor.

    `kaynak_ref` benzersiz: aynı ödeme ya da aynı süre dolumu iki kez
    işlenirse ikinci satır yazılamıyor (`fatura:<id>:kredi`,
    `fatura:<id>:bonus`, `sure_dolumu:<yukleme_id>`).
    """

    __tablename__ = "credit_ledger"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True, nullable=False)
    #: Küçük harf. Müşteri paneli bu alanla, jetondaki e-postaya göre süzüyor.
    musteri_eposta = Column(String, nullable=False, index=True)
    #: Saat cinsinden, 0.25 hassasiyet. + yükleme, − harcama.
    miktar = Column(Float, nullable=False)
    #: satin_alma | bonus | harcama | iade | hediye | duzeltme | sure_dolumu
    tur = Column(String, nullable=False)
    aciklama = Column(String, nullable=True)
    fatura_id = Column(Integer, nullable=True, index=True)
    proje_id = Column(Integer, nullable=True)
    #: Yalnız artı satırlarda: created_at + 365 gün.
    son_kullanma = Column(DateTime(timezone=True), nullable=True)
    kaynak_ref = Column(String, nullable=True, unique=True)
    #: Satırı yazan yönetici; ödeme ve süre dolumunda boş (sistem).
    olusturan_eposta = Column(String, nullable=True)
