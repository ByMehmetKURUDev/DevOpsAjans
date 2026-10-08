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
from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class GelenKutusuIsaretleri(Base):
    __tablename__ = "gelen_kutusu_isaretleri"
    __table_args__ = (
        UniqueConstraint("kaynak", "kimlik", name="uq_gelen_kutusu_isaret"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: fiyat_teklifi | randevu | icerik_revizyon | belge | egitim | belge_paylasim | crm_form | teklif_karari
    kaynak = Column(String(24), nullable=False, index=True)
    kimlik = Column(Integer, nullable=False)
    #: okundu | kapandi
    durum = Column(String(12), nullable=False)
    isaretleyen = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi, nullable=True)


class GelenKutusuYanitlari(Base):
    """Faz 7K — gelen kutusundan e-postayla verilen yanıtlar: öğenin yazışma geçmişi.

    Kendi yanıt yolu olan kaynakların (destek, sohbet) yazışması kendi tablolarında; e-postayla
    yanıtlanan kaynaklarda (iletişim, fiyat teklifi, kartvizit, randevu, CRM formu …) gönderilen metin
    başka hiçbir yerde tutulmuyordu. Her deneme bir satır: kim, kime, ne zaman, konu, metin ve sonuç
    (`gonderildi` | `gonderilemedi` — e-posta sağlayıcısı yoksa ya da sağlayıcı reddederse; metin
    kaybolmasın, elle gönderilebilsin). Kaynak kayıt silinse de satır kalır (yazışma kanıtı).
    """

    __tablename__ = "gelen_kutusu_yanitlari"
    __table_args__ = (
        Index("ix_gelen_kutusu_yanit_oge", "kaynak", "kimlik"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kaynak = Column(String(24), nullable=False)
    kimlik = Column(Integer, nullable=False)
    #: Yanıtı yazan yönetici / ekip üyesi e-postası.
    yazan = Column(String, nullable=True)
    alici = Column(String, nullable=False)
    konu = Column(String, nullable=True)
    metin = Column(Text, nullable=False)
    #: gonderildi | gonderilemedi
    durum = Column(String(16), nullable=False)
    #: gonderilemedi ise: eposta_kapali | eposta_gitmedi
    neden = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False, index=True)
