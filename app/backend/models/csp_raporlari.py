"""Faz 4G — İçerik Güvenliği Politikası (CSP) ihlal raporları.

Tarayıcı, sitenin CSP'sine takılan bir kaynağı (betik, bağlantı, çerçeve…)
`report-uri` / `report-to` ile `POST /api/v1/csp-rapor` ucuna bildiriyor.
CSP zorunlu moddayken canlıda gözden kaçan bir ihlal (ör. yeni bir analitik
alan adı) bu tabloda görünüyor; yönetici paneli › Güvenlik.

Küçük ve kendini sınırlayan bir tablo: en çok `SINIR` satır (en yenileri)
tutuluyor. Aynı ihlal (sayfa + yönerge + engellenen kaynak + dosya + mod)
bir saat içinde tekrar gelirse yeni satır açılmıyor, `sayi` artıyor.
Kişisel veri yok: IP, tarayıcı kimliği saklanmıyor; adreslerin sorgu dizgesi
atılıyor, sayfa yolunun jeton taşıyabilen kısımları kısaltılıyor.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class CspRaporlari(Base):
    __tablename__ = "csp_raporlari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: İhlalin olduğu sayfa (köken + kısaltılmış yol; sorgu dizgesi yok).
    belge = Column(String, nullable=False, default="")
    #: Etkin yönerge (ör. "script-src-elem", "connect-src").
    yonerge = Column(String, nullable=False, default="")
    #: Engellenen kaynak (köken + yol, sorgusuz) ya da "inline" / "eval".
    engellenen = Column(String, nullable=False, default="")
    #: İhlali tetikleyen dosya (sorgusuz) ve konumu.
    kaynak_dosya = Column(String, nullable=True)
    satir = Column(Integer, nullable=True)
    sutun = Column(Integer, nullable=True)
    #: "enforce" (engellendi) | "report" (yalnız raporlandı).
    mod = Column(String, nullable=False, default="enforce")
    #: Satır içi kodun ilk 40 karakteri (tarayıcı veriyorsa).
    ornek = Column(String, nullable=True)
    #: Aynı ihlal bir saat içinde kaç kez geldi.
    sayi = Column(Integer, nullable=False, default=1)
    ilk_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    son_at = Column(DateTime(timezone=True), default=_simdi, index=True, nullable=False)


__all__ = ["CspRaporlari"]
