from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Denetim kaydı: panelde "kim, ne zaman, hangi kaydı, neyi değiştirdi".

    `access_log`'dan farkı: o tablo müşteri SİTESİNE yapılan bakım
    erişimlerini tutuyor (müşteriye açık bir söz); bu tablo ise bizim
    kendi veritabanımızdaki kayıtlara yapılan değişiklikleri tutuyor.

    Satırlar çoğunlukla `services/denetim.py`'deki oturum olayından
    kendiliğinden yazılıyor; entity dışı birkaç uç (ortam ayarları gibi
    veritabanına dokunmayan işler) `denetim_yaz` ile elle yazıyor.

    Ham IP saklanmıyor; yalnız özeti. Hassas alanların değerleri
    `degisiklik_json` içinde "***" olarak duruyor.
    """

    __tablename__ = "audit_log"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True, nullable=False)
    #: İşlemi yapanın e-postası (küçük harf). Anonim/sistem işlemlerinde boş.
    aktor_eposta = Column(String, nullable=True, index=True)
    #: admin | client | sistem | anonim
    aktor_rol = Column(String, nullable=False, default="sistem")
    #: olustur | guncelle | sil | giris | onay | odeme | diger
    islem = Column(String, nullable=False)
    tablo = Column(String, nullable=False, index=True)
    kayit_id = Column(String, nullable=True, index=True)
    #: Kısa, insan okunur özet: kaydın etiketi + değişen alan adları.
    ozet = Column(String, nullable=True)
    #: {"alan": [eski, yeni]} — yalnız değişen alanlar, hassaslar maskeli.
    degisiklik_json = Column(Text, nullable=True)
    ip_ozeti = Column(String, nullable=True)
    #: "PUT /api/v1/entities/invoices/5" gibi.
    istek_yolu = Column(String, nullable=True)
    #: Etkilenen kaydın sahibi (client_email). Müşterinin "Hesap
    #: hareketleri" listesi, yöneticinin onun kaydında yaptığı işleri de
    #: bu alanla buluyor.
    ilgili_eposta = Column(String, nullable=True, index=True)
