"""Faz 6R — sektör paketi / hazır ayar uygulamalarının günlüğü.

`sektor_paketi_uygulamalari`: yöneticinin bir müşteriye uyguladığı her paket
(modüller + hazır ayarlar) ya da yalnız hazır ayar uygulaması bir satır.

* `tur`: `paket` (modüller açıldı, isteğe bağlı hazır ayarlar) | `hazir` (yalnız hazır ayarlar).
* `acilan_moduller` (JSON): paketin AÇTIĞI modüller — `[{anahtar, onceki_elle, acilis_at}]`.
  "Paketi kaldır" yalnız bunları, hâlâ açıksa ve açılış anı değişmemişse (sonradan elle
  kapatılıp açılmamışsa) eski haline (`onceki_elle`: yok → varsayılana dön, false → kapalı)
  döndürüyor. Zaten açık olanlar `zaten_acik`ta; onlara dokunulmuyor.
* `hazir_kayitlar` (JSON): hazır ayarların OLUŞTURDUĞU kayıtlar —
  `[{modul, tablo, id, iz, etiket}]` (oluşturma sırası) ve boş alanı doldurduğu yerler
  `[{modul, tablo, id, alan, iz, etiket, tur: "alan"}]`. `iz` oluşturma anındaki içeriğin
  özeti: geri almada içerik aynıysa (el değmemiş) silinir/boşaltılır, değiştiyse korunur.
* `atlananlar` (JSON): yazılmayan şeyler ve nedenleri (zaten var, modül kapalı, ad bilinmiyor…).
* `oneriler` (JSON): otomasyon şablon önerileri (kurulmaz; müşterinin "Hazır şablonlar"ında işaretli).
* `durum`: `uygulandi` | `kaldirildi`; `hazir_durum`: `yok` | `uygulandi` | `geri_alindi`.
* `geri_alma` (JSON): son geri almanın özeti (kapatılan/korunan modüller, silinen/korunan kayıtlar).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class SektorPaketiUygulamalari(Base):
    __tablename__ = "sektor_paketi_uygulamalari"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    musteri_eposta = Column(String(254), index=True, nullable=False)
    #: paket | hazir
    tur = Column(String(8), nullable=False, default="paket")
    paket = Column(String(40), nullable=True)
    set_anahtari = Column(String(40), nullable=True)
    #: Hesabın dili (kayıtların dil alanı) ve başlangıç içeriğinin dili (tr | en).
    dil = Column(String(2), nullable=False, default="tr")
    icerik_dili = Column(String(2), nullable=False, default="tr")
    acilan_moduller = Column(Text, nullable=True)
    zaten_acik = Column(Text, nullable=True)
    hazir_kayitlar = Column(Text, nullable=True)
    atlananlar = Column(Text, nullable=True)
    oneriler = Column(Text, nullable=True)
    geri_alma = Column(Text, nullable=True)
    #: uygulandi | kaldirildi
    durum = Column(String(12), nullable=False, default="uygulandi", index=True)
    #: yok | uygulandi | geri_alindi
    hazir_durum = Column(String(12), nullable=False, default="yok")
    bildirim = Column(Boolean, nullable=False, default=False)
    uygulayan = Column(String(254), nullable=True)
    geri_alan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    kaldirma_at = Column(DateTime(timezone=True), nullable=True)
    hazir_geri_alma_at = Column(DateTime(timezone=True), nullable=True)
