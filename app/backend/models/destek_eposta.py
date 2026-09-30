"""Faz 2F — E-postadan destek talebi ve otomatik destek kuralları.

Dört tablo
----------
* `gelen_epostalar`   Gelen her iletinin KAYDI (içeriği değil): kimden, konu,
  ne oldu (islendi / yoksayildi / hata), neden, hangi talep. Ham gövde
  saklanmıyor; yalnız 200 karakterlik özet. `message_id` benzersiz: aynı
  ileti ikinci kez gelirse (sağlayıcı yeniden denedi) ikinci talep açılmıyor.
* `talep_eposta_kimlikleri`  Bizim gönderdiğimiz (ve bize gelen) e-postaların
  Message-ID'si → talep. Müşteri e-postayı "Yanıtla" ile cevaplayınca
  In-Reply-To/References bu tabloda aranıyor. Kimliğin biçimine
  (`<talep-5-...@alan>`) GÜVENİLMİYOR: yalnız tabloda olan kimlik eşleşir,
  yoksa herkes `talep-5-uydurma` yazıp başkasının talebine mesaj ekleyebilirdi.
* `talep_ekleri`      E-postayla gelen ekler → talep (ve mesaj). Dosyanın
  kendisi `files` tablosunda (`services/dosyalar.py`), burada yalnız bağ.
* `destek_kurallari`  Talep açılınca sırayla uygulanan otomatik kurallar.
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class GelenEpostalar(Base):
    __tablename__ = "gelen_epostalar"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: İletinin Message-ID'si; yoksa sağlayıcı kimliğinden ya da içerikten türetilir.
    message_id = Column(String, unique=True, index=True, nullable=False)
    gonderen = Column(String, index=True, nullable=True)
    konu = Column(String, nullable=True)
    #: isleniyor | islendi | yoksayildi | hata
    durum = Column(String, index=True, nullable=False, default="isleniyor")
    #: Makine okunur neden: yeni_talep, mesaj_eklendi, otomatik_yanit, hiz_siniri ...
    neden = Column(String, nullable=True)
    talep_id = Column(Integer, index=True, nullable=True)
    #: genel | resend
    kaynak = Column(String, nullable=True)
    #: Sorun ayıklamak için kısa özet (ilk 200 karakter) — ham gövde DEĞİL.
    ozet = Column(String, nullable=True)
    ek_sayisi = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, index=True)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)


class TalepEpostaKimlikleri(Base):
    __tablename__ = "talep_eposta_kimlikleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    message_id = Column(String, unique=True, index=True, nullable=False)
    ticket_id = Column(Integer, index=True, nullable=False)
    #: Hangi yazışma satırı (ticket_replies.id). Talebin açılış iletisi için boş.
    reply_id = Column(Integer, nullable=True)
    #: giden (bizim gönderdiğimiz) | gelen (müşteriden)
    yon = Column(String, nullable=False, default="giden")
    created_at = Column(DateTime(timezone=True), default=_simdi)


class TalepEkleri(Base):
    __tablename__ = "talep_ekleri"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ticket_id = Column(Integer, index=True, nullable=False)
    #: ticket_replies.id; talebin açılış mesajının eki ise boş.
    reply_id = Column(Integer, index=True, nullable=True)
    dosya_id = Column(Integer, nullable=False)
    ad = Column(String, nullable=False)
    boyut = Column(Integer, nullable=False, default=0)
    tur = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi)


class DestekKurallari(Base):
    """Otomatik destek kuralı.

    `kosullar` JSON listesi: [{"alan": "konu", "islec": "icerir", "deger": "fatura"}]
    `eylemler` JSON listesi: [{"tur": "oncelik", "deger": "acil"}, {"tur": "durdur"}]
    Ayrıntı ve doğrulama `services/destek_kurallari.py`.
    """

    __tablename__ = "destek_kurallari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ad = Column(String, nullable=False)
    aktif = Column(Boolean, nullable=False, default=True)
    sira = Column(Integer, nullable=False, default=0, index=True)
    #: hepsi | herhangi
    eslesme = Column(String, nullable=False, default="hepsi")
    kosullar = Column(Text, nullable=False, default="[]")
    eylemler = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), default=_simdi)
    updated_at = Column(DateTime(timezone=True), default=_simdi, onupdate=_simdi)
