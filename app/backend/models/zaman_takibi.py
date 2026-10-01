"""Faz 3Z — zaman takibi (sayaç + elle kayıt + çizelge onayı) ve proje şablonları.

Zaman kaydı
-----------
Bir kişinin (ajans personeli ya da yönetici) bir projede — isteğe bağlı bir
görevde — harcadığı süre. Sayaç sunucuda tutuluyor: `baslangic` dolu,
`bitis` boş satır = çalışan sayaç (sayfa kapansa da süre işlemeye devam
ediyor). Kişi başına aynı anda TEK açık sayaç: kısmi benzersiz indeks
(`bitis IS NULL`) bunu veritabanı düzeyinde garanti ediyor.

* `saatlik_ucret` + `para_birimi` kayıt anında sabitleniyor (proje ücreti,
  yoksa site ayarı). Ücret sonradan değişse de eski kayıt değişmez.
* Durum: taslak → onaylandi | reddedildi; onaylandi → faturalandi.
  Onaylanmış ve faturalanmış kayıt kilitli (düzenlenemez, silinemez).
* Görevli kayıt onaylanınca Faz 2B'nin `task_time_entries` tablosuna bir
  AYNA satır yazılıyor (`gorev_saat_id`): görev kartındaki harcanan saat ve
  aylık revizyon sayacı (tür = revizyon) tek kaynaktan hesaplanmaya devam
  ediyor. Görevsiz revizyon kaydı sayaca `services/gorevler.revizyon_sayaci`
  içinde ayrıca ekleniyor.

Faturalama bağı
---------------
`zaman_fatura_baglari` satırı = "bu kayıt bu faturaya yazıldı". `zaman_kaydi_id`
BENZERSİZ: aynı kayıt iki kez faturalanamaz (veritabanı düzeyinde). Fatura
iptal edilince ya da silinince bağ siliniyor, kayıt yeniden `onaylandi` oluyor
(`services/zaman_takibi.py` flush kancası).

Proje şablonu
-------------
Görev listesi JSON (`gorevler`): başlık, açıklama, aşama, göreli başlangıç
günü + süre (gün), kontrol listesi, varsayılan atanan (kişi ya da rol),
müşteriye görünür mü, tahmini saat. Şablondan proje oluşturulurken tarihler
seçilen başlangıç gününe göre hesaplanıyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, Numeric, String, Text, UniqueConstraint, text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


#: Kayıt türleri ve durumları.
TURLER = ("normal", "revizyon")
DURUMLAR = ("taslak", "onaylandi", "reddedildi", "faturalandi")
#: Kilitli (düzenlenemez/silinemez) durumlar.
KILITLI_DURUMLAR = ("onaylandi", "faturalandi")


class ZamanKayitlari(Base):
    __tablename__ = "zaman_kayitlari"
    __table_args__ = (
        # Kişi başına tek açık sayaç (bitis boş = çalışıyor). SQLite ve
        # PostgreSQL ikisi de kısmi indeksi destekliyor.
        Index(
            "uq_zaman_kayitlari_acik_sayac",
            "kisi_eposta",
            unique=True,
            sqlite_where=text("bitis IS NULL"),
            postgresql_where=text("bitis IS NULL"),
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    proje_id = Column(Integer, nullable=False, index=True)
    gorev_id = Column(Integer, nullable=True, index=True)
    #: Personel / yönetici e-postası (küçük harf).
    kisi_eposta = Column(String, nullable=False, index=True)
    #: UTC. Gün (çizelge, CSV) Türkiye saatine göre bu andan hesaplanıyor.
    baslangic = Column(DateTime(timezone=True), nullable=False, index=True)
    #: Boş = sayaç çalışıyor.
    bitis = Column(DateTime(timezone=True), nullable=True)
    #: Dakika; sayaç durunca ya da elle girilince dolar.
    sure_dk = Column(Integer, nullable=True)
    aciklama = Column(Text, nullable=True)
    faturalanabilir = Column(Boolean, nullable=False, default=True)
    #: Kayıt anında sabitlenen ücret (yoksa boş: faturaya aktarırken sorulur).
    saatlik_ucret = Column(Numeric(14, 2), nullable=True)
    para_birimi = Column(String, nullable=True)
    #: normal | revizyon
    tur = Column(String, nullable=False, default="normal")
    #: taslak | onaylandi | reddedildi | faturalandi
    durum = Column(String, nullable=False, default="taslak", index=True)
    ret_notu = Column(Text, nullable=True)
    onaylayan_eposta = Column(String, nullable=True)
    onay_at = Column(DateTime(timezone=True), nullable=True)
    fatura_id = Column(Integer, nullable=True, index=True)
    #: Onayda yazılan Faz 2B saat girişi (task_time_entries.id) — görevliyse.
    gorev_saat_id = Column(Integer, nullable=True, index=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class ZamanFaturaBaglari(Base):
    """Kayıt → fatura bağı. `zaman_kaydi_id` benzersiz: çift faturalama yok."""

    __tablename__ = "zaman_fatura_baglari"
    __table_args__ = (
        UniqueConstraint("zaman_kaydi_id", name="uq_zaman_fatura_baglari_kayit"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    zaman_kaydi_id = Column(Integer, nullable=False)
    fatura_id = Column(Integer, nullable=False, index=True)
    #: Faturadaki kalem sırası (0'dan) — hangi satıra yazıldığı.
    kalem_sira = Column(Integer, nullable=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class ProjeSablonlari(Base):
    __tablename__ = "proje_sablonlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ad = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    #: Oluşturulan projenin kategorisi (projects.category).
    kategori = Column(String, nullable=True)
    tahmini_saat = Column(Float, nullable=True)
    #: JSON: [{baslik, aciklama, asama, baslangic_gun, sure_gun, kontrol_listesi,
    #:         atanan_eposta, atanan_rol, musteriye_gorunur, kilometre_tasi,
    #:         oncelik, tahmini_saat}]
    gorevler = Column(Text, nullable=True)
    #: Tohum şablonu mu (ilk kurulumda yazılan örnek)?
    hazir = Column(Boolean, nullable=False, default=False)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
