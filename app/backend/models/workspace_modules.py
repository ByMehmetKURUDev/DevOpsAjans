from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceModules(Base):
    """Müşteri başına modül durumu — varsayılanı ELLE geçersiz kılan satır.

    Satır yoksa modülün durumu manifestten (`core/moduller.py`) hesaplanıyor:
    müşterinin paketi (son kabul edilen / ödenen fiyat teklifinin ölçeği) ya
    da `varsayilan_acik`. Satır varsa ve `acik` dolu ise o geçerli.

    `acik` NULL olabilir: "varsayılana dön" satırı silmiyor, yalnız `acik`i
    boşaltıyor — müşteriye özel ayarlar (`ayarlar_json`) korunuyor.

    Sahibi `musteri_eposta` (küçük harf) ile tutulduğu için her değişiklik
    denetim kaydına müşterinin "ilgili" kaydı olarak düşüyor (1B).
    """

    __tablename__ = "workspace_modules"
    __table_args__ = (
        UniqueConstraint("musteri_eposta", "modul_anahtari", name="uq_workspace_modules_musteri_modul"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    musteri_eposta = Column(String, nullable=False, index=True)
    modul_anahtari = Column(String, nullable=False)
    #: True/False = elle açık/kapalı; NULL = varsayılanı izle (yalnız ayar taşıyor).
    acik = Column(Boolean, nullable=True)
    #: JSON: {ayar_anahtari: deger} — yalnız manifestte tanımlı alanlar.
    ayarlar_json = Column(Text, nullable=True)
    #: Son değişikliği yapan yönetici.
    acan_eposta = Column(String, nullable=True)
    acilis_at = Column(DateTime(timezone=True), nullable=True)
    kapanis_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
