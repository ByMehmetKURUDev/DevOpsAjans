---
title: "Medya Karması Modelleme (MMM) Nedir?"
description: "Medya karması modelleme nedir ve ne zaman kullanılır? Model girdileri, doygunluk ve gecikme etkileri, kalibrasyon, sınırlar ve bütçe planlamasında kullanımı."
keywords: "medya karması modelleme, MMM, marketing mix modeling, bütçe optimizasyonu, doygunluk eğrisi, adstock, kalibrasyon"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Modelleme"
  - "Bütçe Planlama"
date: "2026-09-15"
lang: "tr"
og_title: "Medya Karması Modelleme (MMM)"
og_description: "Üst düzey bütçe kararları için istatistiksel modelleme."
og_type: "article"
twitter_card: "summary"
twitter_title: "Medya Karması Modelleme"
twitter_description: "MMM'nin girdileri, sınırları ve kullanım alanı."
---

# Medya Karması Modelleme (MMM) Nedir?

Medya karması modelleme, toplam satışı açıklamak için pazarlama harcamalarını ve dış faktörleri istatistiksel olarak modelleyen yöntemdir. Kullanıcı düzeyinde takip gerektirmez; toplu (agrega) veriyle çalışır. Bu özelliği, gizlilik kısıtlarının arttığı dönemde yeniden önem kazanmasının nedenidir.

## 1. Hangi Soruyu Yanıtlar?

MMM, kampanya içi optimizasyon aracı değildir. Yanıtladığı sorular üst düzeydir:

- toplam pazarlama bütçesi kanallar arasında nasıl dağıtılmalı,
- hangi kanal doygunluğa ulaşmış,
- bütçeyi %20 artırırsam beklenen ek satış nedir,
- çevrimdışı ve dijital kanalların birlikte katkısı nasıl,
- fiyat, mevsimsellik ve promosyonun payı ne kadar.

Bu nedenle MMM aylık/çeyreklik planlama ritmine uygundur, günlük teklif kararlarına değil.

## 2. Model Girdileri

**Pazarlama değişkenleri:** kanal bazlı harcama veya gösterim/erişim verisi, kampanya dönemleri, kreatif değişim noktaları.

**Kontrol değişkenleri:** fiyat ve indirim seviyesi, promosyon dönemleri, mevsimsellik ve tatiller, stok durumu, mağaza/kanal sayısı, rekabet aktivitesi, makroekonomik göstergeler, hava durumu (ilgili sektörlerde).

**Bağımlı değişken:** toplam satış, sipariş sayısı veya brüt kâr.

Kontrol değişkenlerinin eksikliği, MMM'nin en yaygın hata kaynağıdır. Fiyat ve promosyon modele girmezse, indirim dönemlerindeki satış artışı reklam katkısı olarak atfedilir.

## 3. İki Temel Etki

**Doygunluk (saturation).** Harcama arttıkça ek her birimin getirisi azalır. Model bu ilişkiyi doğrusal değil, eğri olarak kurar. Doygunluk eğrisi, "bu kanala ne kadar daha yatırım yapılabilir" sorusunun yanıtıdır.

**Gecikme / taşıma etkisi (adstock).** Reklamın etkisi yayınlandığı gün bitmez; sonraki günlere/haftalara taşınır. Model bu taşımayı parametreyle temsil eder.

Bu iki etkiyi modellemeyen bir yaklaşım, kanal katkısını sistematik olarak yanlış hesaplar.

## 4. Veri Gereksinimleri

- en az 2-3 yıllık haftalık veri (mevsimselliği ve varyasyonu yakalamak için),
- kanal harcamalarının tutarlı ve eksiksiz kaydı,
- fiyat ve promosyon geçmişi,
- satış verisinin aynı zaman çözünürlüğünde olması,
- harcamada yeterli varyasyon (hiç değişmemiş bir kanalın etkisi ölçülemez).

Son madde kritiktir: sabit harcanan bir kanalın katkısı istatistiksel olarak ayrıştırılamaz. Bu nedenle bilinçli varyasyon (test dönemleri) modelin kalitesini artırır.

## 5. Kalibrasyon: Deneylerle Doğrulama

MMM tek başına bırakıldığında yanlış sonuçlar üretebilir; çünkü korelasyonu nedensellikle karıştırma riski yüksektir. Bu riski azaltmanın yolu, artımsallık deneyleriyle kalibrasyondur:

- deneyle ölçülmüş artımsal katkı, model çıktısıyla karşılaştırılır,
- büyük sapma varsa model varsayımları gözden geçirilir,
- deney sonuçları modele öncül bilgi olarak verilebilir.

Kalibre edilmemiş MMM, güvenle kullanılabilir bir karar aracı sayılmamalıdır.

## 6. Sınırlar

- toplu veri kullandığı için kişi düzeyinde içgörü vermez,
- geçmişe dayanır; pazar yapısı değişirse geçerliliği azalır,
- kreatif kalitesi gibi ölçülmeyen faktörleri kanal etkisine karıştırabilir,
- yeni kanallar için yeterli geçmiş olmadığından güvenilir tahmin üretmez,
- model kurulumu ve yorumlanması uzmanlık gerektirir,
- aynı veriyle farklı varsayımlar farklı sonuçlar verebilir.

Bu nedenle çıktı, tek bir sayı değil bir aralık ve senaryo seti olarak sunulmalıdır.

## 7. Ne Zaman Yatırım Yapmaya Değer?

MMM aşağıdaki koşullarda anlamlıdır:

- birden fazla kanalda kayda değer bütçe harcanıyor,
- çevrimdışı kanallar da bütçenin önemli bir bölümünü oluşturuyor,
- 2+ yıllık tutarlı veri mevcut,
- planlama kararları çeyreklik alınıyor,
- kullanıcı düzeyi takip yetersiz kaldığı için üst düzey bir bakış gerekiyor.

Küçük ölçekte, tek kanal ağırlıklı yapılarda ise MMM aşırı yatırımdır; artımsallık testleri ve temiz ilişkilendirme daha yüksek getiri sağlar.

## 8. Üç Katmanlı Ölçüm Mimarisi

Olgun bir ölçüm yapısı üç yöntemi birlikte kullanır:

| Katman | Yöntem | Ritim | Karar |
|---|---|---|---|
| Günlük | İlişkilendirme | Günlük | Kampanya optimizasyonu |
| Doğrulama | Artımsallık testi | Çeyreklik | Gerçek katkı kanıtı |
| Planlama | MMM | Çeyreklik/yıllık | Bütçe dağıtımı |

Bu üçlü yapıya "birleşik pazarlama ölçümü" denir ve her katman diğerinin kör noktasını kapatır.

## 9. Uygulama Adımları

1. iş sorusunu netleştirmek (hangi bütçe kararı iyileşecek),
2. veri envanteri ve kalite kontrolü,
3. kontrol değişkenlerinin toplanması,
4. model kurulumu ve doygunluk/gecikme parametrelerinin tahmini,
5. deney sonuçlarıyla kalibrasyon,
6. senaryo analizi (farklı bütçe dağıtımlarının beklenen sonucu),
7. sonuçların belirsizlik aralığıyla raporlanması,
8. periyodik yeniden eğitim ve doğrulama.

## 10. Sık Yapılan Hatalar

- fiyat ve promosyon değişkenlerini modele almamak,
- doygunluk ve gecikme etkilerini ihmal etmek,
- modeli deneyle kalibre etmemek,
- tek nokta tahminini kesin gerçek gibi sunmak,
- yeni kanallar için model çıktısına güvenmek,
- modeli bir kez kurup yıllarca güncellememek,
- MMM'yi günlük optimizasyon aracı gibi kullanmak.

## Sık Sorulan Sorular

**Ne kadar veri gerekir?** Haftalık çözünürlükte en az 2 yıl önerilir. Daha kısa veriyle mevsimsellik ve doygunluk güvenilir tahmin edilemez.

**Açık kaynak araçlarla yapılabilir mi?** Yapılabilir. Ancak zorluk araçta değil, veri kalitesinde, kontrol değişkenlerinde ve kalibrasyondadır.

**Kullanıcı düzeyi ölçümün yerini alır mı?** Almaz. Farklı katmanlarda çalışırlar; MMM üst düzey bütçe, ilişkilendirme günlük yön verir.
