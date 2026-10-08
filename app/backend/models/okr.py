"""Faz 6O — Hedefler ve OKR: dönem, hedef (objective), anahtar sonuç (KR), check-in.

Kapsam
------
`kapsam`: ajansın kendi OKR'ları için `@ajans`, müşteride hesap e-postası (modül `hedefler`). `hesap_email` ajans
kaydında BOŞ (NULL) — çöp kutusu / denetim "sahip" alanı (müşterinin "Silinenler" ve "Hesap hareketleri"nde görünür).
Bütün sorgular `kapsam` üzerinden; bir hesabın kaydı başka kapsamdan hiçbir uçla okunmaz.

Tablolar
--------
* `okr_donemler` — çeyrek / yıl / özel tarih aralığı. Kapsam başına en çok bir `etkin` dönem (panelin açılışta
  gösterdiği). `durum`: acik | kapandi; kapanışta not, kapatan, zaman.
* `okr_hedefler` — hedef (objective): başlık, açıklama, sahibi (ekip üyesinin e-postası), üst hedef (`ust_id`,
  hizalama ağacı; döngü yasak — sunucu denetler), görünürlük (`ekip` | `ozel` = yalnız sahibi ve oluşturan),
  durum (taslak | etkin | kapandi). Yalnız ajans kaydında: `musteri_email` (bağlı müşteri hesabı) + `musteri_paylasim`
  (müşteri panelinde salt okunur kart; check-in notları paylaşılmaz). `tamamlandi_at`: ilerleme 1'e ulaştığı an
  (`okr.hedef_tamamlandi` olayı geçişte bir kez; ilerleme düşerse boşalır). `tasindi_kaynak_id`: önceki dönemden
  taşındıysa asıl hedef.
* `okr_anahtar_sonuclar` — KR: tür (sayi | yuzde | para | evet_hayir | kilometre), başlangıç / hedef / mevcut değer
  (para KURUŞ; evet/hayır 0/1; kilometre taşında tamamlanan sayısı — liste `kilometre_taslari` JSON), yön (artir |
  azalt), ağırlık (1–10), sahibi. İsteğe bağlı OTOMATİK KAYNAK (`kaynak` + `kaynak_ayar` JSON: para birimi, proje):
  değer elle check-in yerine hesaplanır (`services/okr_kaynak.py`), son yenileme ve hata kaydedilir.
  `guven`: son check-in'in güveni. `son_checkin_at` / `son_hatirlatma_at`: haftalık hatırlatma (7 gündür check-in
  almamış etkin elle KR'nin sahibine; KR başına 7 günde en çok bir). `kapanis_puani`: dönem kapanışında 0–1.
* `okr_checkinler` — değer geçmişi: elle check-in (değer + güven + not + tarih + yazan), otomatik kaynak değişimi
  (`tur=otomatik`, değer değiştiyse) ve odak oturumu notu (`tur=odak`, değer değişmez; süre dakika).
"""

from datetime import datetime, timezone

from core.database import Base
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Index, Integer, String, Text


def _simdi() -> datetime:
    return datetime.now(timezone.utc)


class OkrDonemler(Base):
    __tablename__ = "okr_donemler"
    __table_args__ = (
        Index("ix_okr_donemler_kapsam_bas", "kapsam", "baslangic"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), index=True, nullable=False)
    hesap_email = Column(String(254), nullable=True)
    #: Boşsa arayüz türden üretir ("2026 Ç4" / "2026").
    ad = Column(String(80), nullable=True)
    #: ceyrek | yil | ozel
    tur = Column(String(8), nullable=False, default="ceyrek")
    yil = Column(Integer, nullable=True)
    ceyrek = Column(Integer, nullable=True)
    baslangic = Column(Date, nullable=False)
    bitis = Column(Date, nullable=False)
    etkin = Column(Boolean, nullable=False, default=False)
    #: acik | kapandi
    durum = Column(String(8), nullable=False, default="acik")
    kapanis_notu = Column(Text, nullable=True)
    kapandi_at = Column(DateTime(timezone=True), nullable=True)
    kapatan = Column(String(254), nullable=True)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class OkrHedefler(Base):
    __tablename__ = "okr_hedefler"
    __table_args__ = (
        Index("ix_okr_hedefler_kapsam_donem", "kapsam", "donem_id"),
        Index("ix_okr_hedefler_musteri", "musteri_email", "musteri_paylasim"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), nullable=False)
    hesap_email = Column(String(254), nullable=True)
    donem_id = Column(Integer, nullable=False)
    baslik = Column(String(200), nullable=False)
    aciklama = Column(Text, nullable=True)
    sahip = Column(String(254), nullable=True)
    ust_id = Column(Integer, index=True, nullable=True)
    #: ekip | ozel (yalnız sahibi ve oluşturan)
    gorunurluk = Column(String(5), nullable=False, default="ekip")
    #: taslak | etkin | kapandi
    durum = Column(String(7), nullable=False, default="etkin")
    #: Yalnız ajans kaydında: bağlı müşteri hesabı ve "müşteriyle paylaş".
    musteri_email = Column(String(254), nullable=True)
    musteri_paylasim = Column(Boolean, nullable=False, default=False)
    tamamlandi_at = Column(DateTime(timezone=True), nullable=True)
    tasindi_kaynak_id = Column(Integer, nullable=True)
    sira = Column(Integer, nullable=False, default=0)
    olusturan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class OkrAnahtarSonuclar(Base):
    __tablename__ = "okr_anahtar_sonuclar"
    __table_args__ = (
        Index("ix_okr_kr_kapsam_hedef", "kapsam", "hedef_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), nullable=False)
    hesap_email = Column(String(254), nullable=True)
    hedef_id = Column(Integer, index=True, nullable=False)
    baslik = Column(String(200), nullable=False)
    #: sayi | yuzde | para | evet_hayir | kilometre
    tur = Column(String(10), nullable=False, default="sayi")
    #: Sayı türünde birim etiketi ("müşteri", "saat"); arayüzde değerin yanında.
    birim = Column(String(20), nullable=True)
    #: Para türünde (değerler kuruş).
    para_birimi = Column(String(3), nullable=True)
    baslangic_deger = Column(Float, nullable=False, default=0.0)
    hedef_deger = Column(Float, nullable=False, default=0.0)
    mevcut_deger = Column(Float, nullable=False, default=0.0)
    #: artir | azalt
    yon = Column(String(5), nullable=False, default="artir")
    agirlik = Column(Integer, nullable=False, default=1)
    sahip = Column(String(254), nullable=True)
    #: JSON: [{"id": "k1", "metin": "...", "tamam": false}] (yalnız kilometre taşı türünde).
    kilometre_taslari = Column(Text, nullable=True)
    #: Otomatik kaynak (services/okr_kaynak.py KAYNAKLAR) ya da NULL (elle check-in).
    kaynak = Column(String(24), nullable=True)
    #: JSON: {"para_birimi": "TRY", "proje_id": 12}
    kaynak_ayar = Column(Text, nullable=True)
    kaynak_son_yenileme = Column(DateTime(timezone=True), nullable=True)
    kaynak_hata = Column(String(40), nullable=True)
    #: Son check-in'in güveni: yolunda | riskli | tehlikede
    guven = Column(String(9), nullable=True)
    son_checkin_at = Column(DateTime(timezone=True), nullable=True)
    son_hatirlatma_at = Column(DateTime(timezone=True), nullable=True)
    kapanis_puani = Column(Float, nullable=True)
    tasindi_kaynak_id = Column(Integer, nullable=True)
    sira = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class OkrCheckinler(Base):
    __tablename__ = "okr_checkinler"
    __table_args__ = (
        Index("ix_okr_checkinler_kr_tarih", "kr_id", "tarih"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kapsam = Column(String(254), nullable=False)
    hesap_email = Column(String(254), nullable=True)
    kr_id = Column(Integer, index=True, nullable=False)
    hedef_id = Column(Integer, nullable=False)
    #: elle | otomatik | odak
    tur = Column(String(8), nullable=False, default="elle")
    deger = Column(Float, nullable=False, default=0.0)
    onceki = Column(Float, nullable=True)
    guven = Column(String(9), nullable=True)
    notlar = Column(Text, nullable=True)
    #: Odak oturumunun süresi (dakika).
    sure_dk = Column(Integer, nullable=True)
    tarih = Column(Date, nullable=False)
    yazan = Column(String(254), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_simdi, nullable=False)
