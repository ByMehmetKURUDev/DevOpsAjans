from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text


class Invoices(Base):
    __tablename__ = "invoices"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    invoice_no = Column(String, nullable=False)
    client_name = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=True)
    status = Column(String, nullable=True)
    issue_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    # Faz 3T — kalemler + KDV dökümü (JSON), iade faturası, tekrarlayan bağ.
    # Eski tek tutarlı faturalarda hepsi boş; `amount` yine tek gerçek kaynak
    # (kalemli faturada sunucunun hesapladığı genel toplam). Bkz. core/database.py
    # SONRADAN_EKLENEN_SUTUNLAR.
    kalemler = Column(Text, nullable=True)
    ara_toplam = Column(Float, nullable=True)
    kdv_toplam = Column(Float, nullable=True)
    #: NULL/normal | iade (eksi tutarlı alacak faturası; `bagli_fatura_id` asıl fatura)
    tur = Column(String, nullable=True)
    bagli_fatura_id = Column(Integer, nullable=True)
    teklif_id = Column(Integer, nullable=True)
    #: Tekrarlayan fatura: kaynak abonelik + dönem (YYYY-MM / YYYY)
    tekrarlayan_id = Column(Integer, nullable=True)
    donem = Column(String, nullable=True)
    notlar = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)