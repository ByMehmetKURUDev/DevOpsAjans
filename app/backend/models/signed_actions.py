from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class SignedActions(Base):
    """İmzalı işlem bağlantısı: müşterinin girişsiz, tek tıkla verdiği karar.

    Yönetici "şu teklifi onaylasın" / "şu teslimi onaylasın" diyor; müşteriye
    `/islem/<jeton>` adresi gidiyor. Adresi açan kişi oturum açmadan kabul,
    red, onay ya da revizyon seçebiliyor. Karar hedef kayda (teklif, proje)
    işleniyor ve bu satır "kullanıldı" oluyor.

    Ham jeton hiçbir yerde saklanmıyor, yalnız sha256 özeti
    (`jeton_ozeti`). Veritabanı sızsa bile özetten bağlantı kurulamıyor;
    bağlantı yalnız üretildiği anda, bir kez gösteriliyor.

    `durum`: bekliyor | kullanildi | iptal | suresi_doldu
    `sonuc`: kabul | red | onay | revizyon | goruntulendi

    Kullanım tek bir koşullu UPDATE ile işaretleniyor (`WHERE durum =
    'bekliyor' AND son_kullanma > şimdi`); aynı anda gelen iki istekten
    yalnız biri satırı değiştirebiliyor (bkz. `services/imzali_islem.py`).
    """

    __tablename__ = "signed_actions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    #: sha256(ham jeton), onaltılık. Ham jeton SAKLANMIYOR.
    jeton_ozeti = Column(String(64), nullable=False, unique=True, index=True)
    #: teklif_kabul | teslimat_onay | rapor_goruntule
    tur = Column(String, nullable=False, index=True)
    #: pricing_inquiries | projects | site_analyses
    hedef_tablo = Column(String, nullable=False)
    hedef_id = Column(Integer, nullable=False, index=True)
    #: Küçük harf. Müşteri panelindeki "Onay bekleyenler" bu alanla süzülüyor.
    alici_eposta = Column(String, nullable=False, index=True)
    #: E-postada ve sayfada görünen kısa metin.
    baslik = Column(String, nullable=False)
    #: Sayfada gösterilen özet (tutar, kalemler, aşama adı, not…). JSON.
    ayrinti_json = Column(Text, nullable=True)
    son_kullanma = Column(DateTime(timezone=True), nullable=False, index=True)
    tek_kullanimlik = Column(Boolean, nullable=False, default=True)
    durum = Column(String, nullable=False, default="bekliyor", index=True)
    sonuc = Column(String, nullable=True)
    #: Müşterinin gerekçesi / revizyon metni (≤2000).
    sonuc_notu = Column(Text, nullable=True)
    kullanildi_at = Column(DateTime(timezone=True), nullable=True)
    #: utils.istemci_ip.ip_ozeti — ham IP yok.
    kullanan_ip_ozeti = Column(String, nullable=True)
    olusturan_eposta = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
