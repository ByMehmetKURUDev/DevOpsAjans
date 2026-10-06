"""Faz 7H — kalıcı hız sınırı sayaçları ve analiz olaylarının günlük özetleri.

`hiz_sayaclari`
---------------
Herkese açık uçların (giriş, formlar, bülten, yapay zekâ sohbeti, randevu /
etkinlik kaydı, imzalı bağlantılar…) istek sayacı. Bellekteki sayaç Render'ın
ücretsiz sunucusu uyuyup kalkınca ya da yeniden yayında sıfırlanıyordu; bu tablo
sayacı veritabanında tutuyor (`utils/hiz_siniri.py` `KaliciHizSiniri`).

* Anahtar başına TEK satır: `anahtar` = sha256(sınırlayıcı adı | anahtar). Çağıranın
  anahtarı zaten IP'nin tuzlu özeti (`utils.istemci_ip.ip_ozeti`) ya da kayıt
  kimliği; ham IP / e-posta bu tabloya hiç girmiyor.
* Sabit pencere, İLK İSTEKLE başlıyor (`pencere_bas` … `bitis`, Unix ms). Pencere
  dolunca aynı satır sıfırdan başlıyor. Takvime hizalı pencerede (dakika başı)
  sınır, pencere sınırına denk gelen art arda isteklerde iki katına çıkabilirdi;
  ilk istekle başlayan pencere bunu sınırın kendisiyle sınırlıyor.
* Artırma tek atomik `INSERT … ON CONFLICT DO UPDATE … WHERE … RETURNING`.
* Süresi geçmiş satırları zamanlı `saklama_temizligi` siliyor.

`analiz_gunluk_ozetleri`
------------------------
Ham analiz olayları (QR taraması, kartvizit / yorum sayfası olayları, e-posta
kampanyası tıklamaları) 13 ay sonra siliniyor (`services/analiz_saklama.py`).
Panellerde "tüm zamanlar" toplamı gösterilen kaynaklarda silmeden önce o günün
sayıları buraya yazılıyor; toplamlar ham + özet olarak hesaplandığı için
kullanıcının gördüğü sayılar değişmiyor. IP özeti burada YOK (yalnız sayılar).
"""

from core.database import Base
from sqlalchemy import BigInteger, Column, Index, Integer, String, UniqueConstraint


class HizSayaclari(Base):
    __tablename__ = "hiz_sayaclari"
    __table_args__ = (
        Index("ix_hiz_sayaclari_bitis", "bitis"),
        {"extend_existing": True},
    )

    #: sha256(sınırlayıcı | anahtar) — 64 hex.
    anahtar = Column(String(64), primary_key=True)
    #: Pencerenin başladığı ve bittiği an (Unix milisaniye).
    pencere_bas = Column(BigInteger, nullable=False)
    bitis = Column(BigInteger, nullable=False)
    #: Bu penceredeki istek sayısı (sınıra ulaşınca artmıyor).
    sayac = Column(Integer, nullable=False, default=0)


class AnalizGunlukOzetleri(Base):
    __tablename__ = "analiz_gunluk_ozetleri"
    __table_args__ = (
        UniqueConstraint("kaynak", "nesne_id", "olay", "gun", name="uq_analiz_gunluk_ozeti"),
        Index("ix_analiz_gunluk_ozeti_nesne", "kaynak", "nesne_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: qr | kart | yorum | eposta_tik
    kaynak = Column(String(16), nullable=False)
    #: QR kimliği, kart / yorum sayfası kimliği, kampanya kimliği.
    nesne_id = Column(Integer, nullable=False)
    #: Kartvizitte olay türü (goruntulenme, tik…), e-posta tıklamasında bağlantı sırası; QR'da boş.
    olay = Column(String(16), nullable=False, default="")
    #: UTC gün (YYYY-MM-DD).
    gun = Column(String(10), nullable=False)
    #: Bot hariç olay sayısı.
    sayi = Column(Integer, nullable=False, default=0)
    #: Bot hariç o günün tekil ziyaretçisi (IP'nin günlük tuzlu özetiyle sayılmıştı).
    tekil = Column(Integer, nullable=False, default=0)
    #: Bot hariç, değişmez QR koduyla açılan görüntülenme (kartvizit).
    qr = Column(Integer, nullable=False, default=0)
    #: Bot / önizleyici olarak işaretlenen olay sayısı.
    bot = Column(Integer, nullable=False, default=0)


__all__ = ["HizSayaclari", "AnalizGunlukOzetleri"]
