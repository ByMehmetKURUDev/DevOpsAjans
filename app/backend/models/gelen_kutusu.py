"""Faz 5G — birleşik gelen kutusu: yalnız KENDİ "okundu/kapandı" alanı olmayan kaynaklar için işaret.

Neden ayrı (ve en küçük) bir tablo?
-----------------------------------
Gelen kutusundaki öğelerin durumu kaynağın kendi alanından türetiliyor
(iletişim formu `inquiries.status`, destek `support_tickets.status`, sohbet
`konusmalar.durum` + son yazan, kartvizit `okundu`, geri bildirim `durum`).
Dört kaynakta ajansın "gördüm / hallettim" bilgisini taşıyacak alan YOK ve var
olan durum alanı başka bir şeyi anlatıyor:

* `pricing_inquiries.durum` müşterinin teklif kararı (bekliyor/kabul/red) —
  imzalı işlem akışı bu alana bakıyor; ajans işaretini oraya yazmak kararı bozar.
* `randevular.durum` rezervasyonun kendisi (onayli/iptal).
* İçerik revizyon isteği bir `signed_actions` satırı (kullanılmış bağlantı).
* `belge_talepleri.durum` teslim durumu (bekliyor/teslim_edildi/iptal).

Bu dört tabloya ayrı ayrı sütun eklemek gelen kutusunun durumunu dört yere
dağıtırdı; burada tek satır (kaynak, kimlik) → durum. Kullanıcı başına DEĞİL,
ajans geneli: tek kişi "okudum" dediyse öğe herkes için okunmuş sayılır.
Satır yoksa öğe "yeni". "Yeniden aç" satırı siler.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class GelenKutusuIsaretleri(Base):
    __tablename__ = "gelen_kutusu_isaretleri"
    __table_args__ = (
        UniqueConstraint("kaynak", "kimlik", name="uq_gelen_kutusu_isaret"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: fiyat_teklifi | randevu | icerik_revizyon | belge
    kaynak = Column(String(24), nullable=False, index=True)
    kimlik = Column(Integer, nullable=False)
    #: okundu | kapandi
    durum = Column(String(12), nullable=False)
    isaretleyen = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)
