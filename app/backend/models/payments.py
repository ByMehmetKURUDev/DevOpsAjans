"""Tahsilat kayıtları.

Fatura ile ödeme ayrı şeyler: fatura "şu kadar borç var" der, ödeme
"şu kadarı şu tarihte şu kanaldan geldi" der. İkisini tek tabloda
tutmak üç yerde tıkanıyordu — kısmi ödeme, iade, ve başarısız deneme.
Bu yüzden `invoices` olduğu gibi duruyor, tahsilat buraya yazılıyor.

Alanların çoğu sağlayıcıdan geliyor. `saglayici_ref` o sağlayıcının
kendi işlem numarası; iade ya da itiraz olduğunda aradığımız tek anahtar
bu. `ham_yanit` sağlayıcının gönderdiği gövdenin tamamı: bugün
okumadığımız bir alanı yarın aramak zorunda kalmayalım diye saklanıyor.

`jeton` ödeme bağlantısındaki rastgele parça (`/ode/<jeton>`). Fatura
numarası kullanılmıyor: numaralar sıralı, biri tahmin edilirse diğer
müşterilerin faturaları da görünür olurdu.
"""

from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Float, Integer, String, Text


class Payments(Base):
    __tablename__ = "payments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)

    # Hangi faturanın tahsilatı
    invoice_id = Column(Integer, index=True, nullable=True)
    invoice_no = Column(String, nullable=True)
    client_email = Column(String, index=True, nullable=True)

    # Ödeme bağlantısının adresindeki rastgele parça
    jeton = Column(String, index=True, nullable=True)

    # Kanal: shopier | iyzico | paytr | elden | havale
    saglayici = Column(String, nullable=True)
    saglayici_ref = Column(String, index=True, nullable=True)
    # Eski Shopier V1 formunun imzasında kullanılıyordu. V1 kaldırıldı;
    # sütun eski kayıtlar için duruyor, yeni kayıtlarda boş.
    rastgele = Column(String, nullable=True)

    # Shopier yeni API: fatura için açılan gizli ürünün kimliği ve
    # satın alma linki. Ödeme bildirimi geldiğinde siparişteki
    # productId ile bu alan eşleştiriliyor — tutar/e-posta tahminine
    # gerek kalmıyor.
    shopier_urun_id = Column(String, index=True, nullable=True)
    shopier_url = Column(String, nullable=True)

    tutar = Column(Float, nullable=True)
    para_birimi = Column(String, nullable=True)
    komisyon = Column(Float, nullable=True)

    # bekliyor | odendi | basarisiz | iade | iptal
    durum = Column(String, index=True, nullable=True)
    hata_mesaji = Column(String, nullable=True)

    ham_yanit = Column(Text, nullable=True)

    odendi_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
