"""Faz 2B — müşteriden hata / öneri / soru bildirimi ve ekran görüntüleri."""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, LargeBinary, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


GERI_BILDIRIM_TURLERI = ("hata", "oneri", "soru")
#: yeni → inceleniyor → gorev (göreve dönüştü) → cozuldu | kapatildi
GERI_BILDIRIM_DURUMLARI = ("yeni", "inceleniyor", "gorev", "cozuldu", "kapatildi")


class FeedbackItems(Base):
    __tablename__ = "feedback_items"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: Müşterinin kendi projesi (boş olabilir: projesi olmayan müşteri de bildirebilir).
    proje_id = Column(Integer, nullable=True, index=True)
    musteri_eposta = Column(String, nullable=False, index=True)
    tur = Column(String, nullable=False, default="hata")
    baslik = Column(String, nullable=False)
    aciklama = Column(Text, nullable=True)
    sayfa_adresi = Column(String, nullable=True)
    #: Tarayıcı bilgisi (user agent + ekran boyutu) — otomatik.
    tarayici = Column(String, nullable=True)
    durum = Column(String, nullable=False, default="yeni", index=True)
    oncelik = Column(String, nullable=False, default="normal")
    #: Göreve dönüştürüldüyse project_tasks.id
    gorev_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class FeedbackAttachments(Base):
    """Ekran görüntüsü. Türü sunucuda dosyanın ilk baytlarından belirleniyor.

    `depo`: "oss" → nesne deposunda (`nesne_anahtari`), "db" → `icerik`
    (nesne deposu tanımlı değilse; ≤5 MB).
    """

    __tablename__ = "feedback_attachments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    geri_bildirim_id = Column(Integer, nullable=False, index=True)
    musteri_eposta = Column(String, nullable=False, index=True)
    dosya_adi = Column(String, nullable=True)
    #: image/png | image/jpeg | image/webp | image/gif (sunucunun belirlediği)
    icerik_turu = Column(String, nullable=False)
    boyut = Column(Integer, nullable=False)
    depo = Column(String, nullable=False, default="db")
    nesne_anahtari = Column(String, nullable=True)
    icerik = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
