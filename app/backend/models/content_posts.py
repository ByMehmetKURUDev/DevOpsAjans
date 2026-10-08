from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Text


class Content_posts(Base):
    """
    İçerik takvimi — planlanan gönderiler.

    Bu tablo YAYIN YAPMIYOR, plan tutuyor. Instagram, Facebook ve
    LinkedIn'e program üzerinden gönderi atmak için platformların onaylı
    uygulama hesapları gerekiyor; X'in API'si ücretli. Üstelik arka uç
    ücretsiz planda 15 dakikada uykuya geçtiği için "salı 09:00'da at"
    denen bir iş tam saatinde çalışmaz. Söz verip tutmamaktansa dürüst
    olanı yapıyoruz: metin burada hazırlanıyor, zamanı gelince tek tuşla
    kopyalanıp ilgili uygulamada paylaşılıyor.

    Platform onayları alınırsa buraya gerçek gönderim eklenebilir; tablo
    o gün için de uygun (status alanı zaten "published" durumunu
    tutuyor).

    Faz 5I — İçerik stüdyosu bu tabloyu GENİŞLETTİ (ikinci bir gönderi tablosu
    yok): hesap (ajans / müşteri), birden çok kanal + kanal başına metin, ilk
    yorum, görseller, UTM'li kısa linkler, saat dilimi, sorumlu, müşteri onayı
    (imzalı bağlantı) ve tek seferlik hatırlatma. Yeni sütunlar
    `core/database.py` › `SONRADAN_EKLENEN_SUTUNLAR` ile eski veritabanına
    ekleniyor. Eski satırlar: hesap boş (ajans), saat dilimi boş (İstanbul),
    durum İngilizce (draft/approved/published) → stüdyo ilk açılışta Türkçe
    durum koduna çeviriyor (`services/icerik_studyosu.eski_kayitlari_duzelt`).
    """

    __tablename__ = "content_posts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Panelde görünen iç ad; gönderi metni değil.
    title = Column(String, nullable=False)
    # Birincil kanal (eski alan; Faz 5I'de `kanallar[0]` ile eşit tutuluyor).
    channel = Column(String, nullable=True)
    # Paylaşılacak metnin kendisi.
    body = Column(String, nullable=True)
    hashtags = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    link_url = Column(String, nullable=True)
    # Ne zaman paylaşılacak — YEREL duvar saati. Faz 5I: saat dilimi
    # `saat_dilimi` sütununda (boşsa Europe/Istanbul — eski satırlar yöneticinin
    # kendi saatiyle girildi). Takvim sorgusu ve hatırlatma bunu UTC'ye çevirip
    # karşılaştırıyor; tek kaynak bu sütun (ikinci bir "UTC zamanı" yok).
    scheduled_at = Column(DateTime, nullable=True)
    # Faz 5I: taslak | incelemede | musteri_onayi | onaylandi | yayinlandi | reddedildi
    # (eski: draft | approved | published).
    status = Column(String, nullable=True)
    # Aynı kampanyaya ait gönderileri birlikte görmek için.
    campaign = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)

    # --- Faz 5I — İçerik stüdyosu ---------------------------------------
    #: Sahip hesap; boşsa ajansın kendi içeriği.
    hesap_email = Column(String, nullable=True)
    #: ajans (ajans müşteri için yönetir; müşteri onayı istenebilir) | musteri (müşteri kendi içeriği)
    yoneten = Column(String, nullable=True)
    marka_id = Column(Integer, nullable=True)
    #: JSON liste — instagram, facebook, linkedin, x, tiktok, youtube_shorts, google_isletme, pinterest, blog, email
    kanallar = Column(Text, nullable=True)
    #: JSON {kanal: metin} — ana metinden türetilip kanala uyarlanmış metin.
    kanal_metinleri = Column(Text, nullable=True)
    ilk_yorum = Column(Text, nullable=True)
    #: JSON [{anahtar, url, ad, genislik, yukseklik}]
    gorseller = Column(Text, nullable=True)
    video_url = Column(String, nullable=True)
    #: JSON {kanal: {qr_id, kod, adres}} — UTM'li kısa linkler (Faz 4Q motoru).
    kisa_linkler = Column(Text, nullable=True)
    saat_dilimi = Column(String, nullable=True)
    sorumlu_eposta = Column(String, nullable=True)
    olusturan_eposta = Column(String, nullable=True)
    uretim_id = Column(Integer, nullable=True)
    #: Son durum değişikliğinin notu (ret gerekçesi / müşterinin revizyon notu).
    durum_notu = Column(Text, nullable=True)
    durum_at = Column(DateTime(timezone=True), nullable=True)
    durum_degistiren = Column(String, nullable=True)
    #: Bekleyen müşteri onayı bağlantısı (`signed_actions.id`, tür `icerik_onay`).
    onay_islem_id = Column(Integer, nullable=True)
    onaylayan = Column(String, nullable=True)
    onay_at = Column(DateTime(timezone=True), nullable=True)
    #: "Paylaşıma hazır" hatırlatması (planlanan saatten 30 dk önce) — tek kez; tarih değişince sıfırlanır.
    hatirlatma_at = Column(DateTime(timezone=True), nullable=True)
    #: `icerik.yayin_zamani` olayı üretildi mi (tek kez; tarih değişince sıfırlanır).
    yayin_olayi_at = Column(DateTime(timezone=True), nullable=True)
    #: Faz 7K — isteğe bağlı proje (`projects.id`; gönderinin hesabının projesi). Otomasyonda `icerik.*`
    #: olaylarının "olaydaki proje"si: "İçerik onaylandı → Paylaş" şablonu projeye görev açar.
    proje_id = Column(Integer, nullable=True)
