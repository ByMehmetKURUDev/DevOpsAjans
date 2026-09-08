---
title: "SEO Data Warehouse Nedir? SEO Verisi İçin Veri Ambarı Mimarisi"
description: "SEO data warehouse kurulumu: veri kaynakları, katmanlı modelleme, URL normalizasyonu, boyut tabloları, tarihsel saklama, maliyet yönetimi ve raporlama katmanı tasarımı."
keywords: "SEO data warehouse, veri ambarı, SEO veri modeli, ELT süreci, boyut tablosu, URL normalizasyonu, veri katmanı, SEO raporlama"
category: "SEO"
tags:
  - "SEO"
  - "Veri Ambarı"
  - "Analitik"
date: "2026-05-20"
lang: "tr"
og_title: "SEO Data Warehouse Nedir?"
og_description: "SEO verisini tek bir ambarda modelleyip güvenilir raporlama kurma yöntemi."
og_type: "article"
twitter_card: "summary"
twitter_title: "SEO Data Warehouse Nedir?"
twitter_description: "Katmanlı veri modeli, boyut tabloları ve maliyet yönetimi."
---

# SEO Data Warehouse Nedir?

SEO data warehouse, arama performansı, site davranışı, teknik tarama, log ve iş verisinin tek bir analitik depoda birleştirilmesidir. Ayrı arayüzlerde duran veriler ancak birleştirildiğinde anlamlı sorulara cevap verir: hangi konu kümesi gerçekten gelir üretiyor, teknik düzeltmeler hangi sayfa grubunda etki yaptı, tarama bütçesi değerli sayfalara mı gidiyor.

## 1. Neden Ayrı Bir Ambar Gerekir?

Kaynak arayüzlerin üç temel sınırı vardır: veri saklama süresi kısıtlıdır, boyut kombinasyonları sınırlıdır ve başka veri kaynaklarıyla birleştirme yapılamaz. Ambar bu üç sınırı da kaldırır; ayrıca geçmişi kalıcı biçimde saklayarak yıllar arası karşılaştırma imkânı verir.

## 2. Veri Kaynakları

- arama performansı (sorgu, sayfa, ülke, cihaz, tarih),
- indeksleme ve teknik durum raporları,
- web analitiği (oturum, giriş sayfası, dönüşüm, gelir),
- sıralama takip verisi,
- kendi tarama aracınızın teknik envanteri,
- sunucu erişim kayıtları,
- içerik envanteri (yayın tarihi, yazar, konu kümesi, güncelleme geçmişi),
- CRM veya sipariş verisi.

## 3. Katmanlı Mimari

**Ham katman (raw).** Kaynaktan gelen veri değiştirilmeden, çekim zamanı damgasıyla saklanır. Bu katman asla üzerine yazılmaz; iş kuralı değiştiğinde yeniden işleme imkânı sağlar.

**Hazırlık katmanı (staging).** Alan adları standartlaştırılır, tipler düzeltilir, tekrarlı kayıtlar ayıklanır, URL'ler normalize edilir.

**Model katmanı (marts).** Olgu (fact) ve boyut (dimension) tabloları kurulur. Metrikler burada tek bir tanımla hesaplanır.

**Sunum katmanı.** Panolar ve raporlar yalnızca model katmanını okur; kaynak değiştiğinde raporlar bozulmaz.

## 4. URL Normalizasyonu: En Kritik Adım

Farklı kaynaklarda aynı sayfa farklı yazılır. Birleştirme öncesi zorunlu işlemler:

- protokol ve alt alan adını tek biçime indirmek,
- sondaki eğik çizgi kuralını sabitlemek,
- izleme parametrelerini ayıklamak,
- büyük/küçük harf tutarlılığı sağlamak,
- yönlendirilen URL'leri nihai hedefe eşlemek,
- her URL'ye kalıcı bir sayfa kimliği (page_key) atamak.

Bu adım atlanırsa tüm birleştirmeler sessizce yanlış sonuç üretir.

## 5. Boyut Tabloları

Metrikleri anlamlı kılan şey boyutlardır:

| Boyut | İçerik |
|---|---|
| Sayfa | page_key, URL, sayfa türü, dil, yayın tarihi |
| Konu | konu kümesi, hub ilişkisi, arama amacı |
| Sorgu | sorgu metni, marka/marka dışı, amaç sınıfı |
| Tarih | gün, hafta, ay, mevsimsellik bayrağı |
| Cihaz/Ülke | segment analizleri için |
| Değişiklik | yayın, güncelleme ve teknik müdahale kayıtları |

Değişiklik boyutu özellikle değerlidir: bir müdahalenin öncesi-sonrası etkisini ölçmeyi mümkün kılar.

## 6. Tarihsel Saklama ve Maliyet

Veri hacmi hızla büyür. Maliyeti kontrol altında tutmak için:

- tabloları tarihe göre bölümlendirin,
- sık filtrelenen alanlarda kümeleme kullanın,
- ham katmanda eski dönemleri özetleyip detayı arşive taşıyın,
- sorgu maliyetini azaltmak için önceden toplanmış özet tablolar üretin,
- kullanılmayan tabloları ve zamanlanmış işleri düzenli olarak temizleyin.

## 7. Veri Kalitesi ve Yönetişim

- her yükleme sonrası tazelik ve satır sayısı kontrolü,
- metrik tanımlarının tek bir sözlükte tutulması,
- tabloların sahibinin ve güncelleme sıklığının belgelenmesi,
- kişisel veri içeren alanlarda erişim kısıtı ve saklama süresi,
- tüm dönüşüm mantığının sürüm kontrolünde tutulması.

## 8. Ambarın Cevapladığı Sorular

- konu kümesi bazında organik gelir katkısı nedir,
- hangi sayfa grubu güncellemeden sonra gerçekten büyüdü,
- tarama isteklerinin yüzde kaçı dönüşüm üreten sayfalara gidiyor,
- teknik hata sayısı ile organik performans arasında ilişki var mı,
- yeni içeriğin ilk gösterime kadar geçen ortalama süresi ne,
- marka dışı trafiğin toplam gelir içindeki payı nasıl seyrediyor.

## Sık Sorulan Sorular

**Küçük siteler için gerekli mi?** Birkaç yüz sayfalık sitelerde hazır panolar yeterlidir. Ambar, çok kaynaklı birleştirme ve uzun tarihsel analiz ihtiyacıyla anlam kazanır.

**Hangi teknolojiler kullanılır?** Yönetilen bir analitik veritabanı, zamanlanmış veri çekim işleri, SQL tabanlı dönüşüm katmanı ve bir görselleştirme aracı tipik bileşenlerdir.

**Kurulum ne kadar sürer?** Temel bir çekirdek (arama performansı + analitik + içerik envanteri) sınırlı sürede kurulabilir; log ve CRM entegrasyonu ek planlama gerektirir.
