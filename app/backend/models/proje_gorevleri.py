"""Faz 2B — proje görevleri, kontrol listesi, bağımlılıklar ve saat girişleri.

Projenin kendi satırı (`projects`) yalnız güncel aşamayı taşıyor; işin
parçaları burada. Görev tahtası (Kanban) `durum` + `sira` ile çiziliyor.

* `musteriye_gorunur=False` görevler iç iş: müşteri paneline hiç çıkmıyor.
* `etiketler` JSON listesi; "revizyon" etiketli görevlerin saatleri aylık
  revizyon hakkından düşüyor (bkz. services/gorevler.revizyon_sayaci).
* Harcanan saat görevde önbellek olarak duruyor; asıl kayıt
  `task_time_entries` (hangi AYA düştüğü saat girişinin `tarih`inden).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


#: yapilacak → suruyor → incelemede → tamam
GOREV_DURUMLARI = ("yapilacak", "suruyor", "incelemede", "tamam")
ONCELIKLER = ("dusuk", "normal", "yuksek", "acil")


class ProjectTasks(Base):
    __tablename__ = "project_tasks"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    proje_id = Column(Integer, nullable=False, index=True)
    baslik = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    durum = Column(String, nullable=False, default="yapilacak", index=True)
    oncelik = Column(String, nullable=False, default="normal")
    #: staff.email (küçük harf); boş = atanmamış.
    atanan = Column(String, nullable=True, index=True)
    bitis_tarihi = Column(Date, nullable=True)
    #: Faz 3Z — planlanan başlangıç (şablondan oluşturulan görevde ofsetle hesaplanıyor).
    baslangic_tarihi = Column(Date, nullable=True)
    #: Sütun içindeki sıra (0'dan).
    sira = Column(Integer, nullable=False, default=0)
    musteriye_gorunur = Column(Boolean, nullable=False, default=False)
    ust_gorev_id = Column(Integer, nullable=True, index=True)
    kilometre_tasi = Column(Boolean, nullable=False, default=False)
    tahmini_saat = Column(Float, nullable=True)
    #: Saat girişlerinin toplamı (önbellek; girişler değişince yeniden yazılıyor).
    harcanan_saat = Column(Float, nullable=False, default=0.0)
    #: JSON metni: ["revizyon", "hata", ...]
    etiketler = Column(Text, nullable=True)
    #: Görev bir geri bildirimden doğduysa (feedback_items.id).
    geri_bildirim_id = Column(Integer, nullable=True, index=True)
    #: Görev 1E revizyon isteğinden doğduysa (signed_actions.id).
    imzali_islem_id = Column(Integer, nullable=True)
    tamamlandi_at = Column(DateTime(timezone=True), nullable=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class TaskChecklist(Base):
    __tablename__ = "task_checklist"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    gorev_id = Column(Integer, nullable=False, index=True)
    metin = Column(String, nullable=False)
    tamam = Column(Boolean, nullable=False, default=False)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class TaskDependencies(Base):
    """`gorev_id`, `bagli_oldugu_id` bitmeden "tamam"a geçemez."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("gorev_id", "bagli_oldugu_id", name="uq_task_dependencies_cift"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    gorev_id = Column(Integer, nullable=False, index=True)
    bagli_oldugu_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class TaskTimeEntries(Base):
    """Bir göreve girilen saat. Revizyon sayacı bu satırlardan hesaplanıyor.

    `revizyon` giriş anındaki etiketten kopyalanıyor (görev etiketi değişince
    görevin girişleri de güncelleniyor); görev silinse bile ayın sayacı
    bozulmasın diye proje ve müşteri de satırda.
    """

    __tablename__ = "task_time_entries"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    gorev_id = Column(Integer, nullable=False, index=True)
    proje_id = Column(Integer, nullable=False, index=True)
    musteri_eposta = Column(String, nullable=True, index=True)
    saat = Column(Float, nullable=False)
    #: İşin yapıldığı gün (Türkiye saati) — hangi aya düştüğünü bu belirliyor.
    tarih = Column(Date, nullable=False, index=True)
    aciklama = Column(String, nullable=True)
    revizyon = Column(Boolean, nullable=False, default=False)
    #: Krediden düşülen saat (credit_ledger harcama satırı) — boşsa düşülmedi.
    kredi_saat = Column(Float, nullable=True)
    kredi_hareket_id = Column(Integer, nullable=True)
    giren_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)


class RevizyonUyarilari(Base):
    """Aylık revizyon hakkı aşıldı uyarısı — müşteri × ay başına bir kez."""

    __tablename__ = "revizyon_uyarilari"
    __table_args__ = (
        UniqueConstraint("musteri_eposta", "ay", name="uq_revizyon_uyarilari_musteri_ay"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    musteri_eposta = Column(String, nullable=False, index=True)
    #: YYYY-MM
    ay = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
