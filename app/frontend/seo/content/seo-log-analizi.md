---
title: "SEO Log Analizi Nedir? Sunucu Kayıtlarıyla Tarama Davranışını Okumak"
description: "SEO log analizi ile arama botlarının gerçek tarama davranışını inceleme: log toplama, bot doğrulama, tarama bütçesi dağılımı, hata tespiti ve aksiyon üretme yöntemi."
keywords: "SEO log analizi, log file analysis, sunucu logları, crawl budget analizi, bot doğrulama, Googlebot logları, tarama davranışı"
category: "SEO"
tags:
  - "SEO"
  - "Teknik SEO"
  - "Log Analizi"
date: "2026-04-15"
lang: "tr"
og_title: "SEO Log Analizi Nedir?"
og_description: "Sunucu kayıtlarıyla botların gerçek tarama davranışını analiz etme yöntemi."
og_type: "article"
twitter_card: "summary"
twitter_title: "SEO Log Analizi Nedir?"
twitter_description: "Log verisiyle tarama bütçesi ve teknik hata teşhisi."
---

# SEO Log Analizi Nedir?

SEO log analizi, web sunucusunun tuttuğu erişim kayıtlarını inceleyerek arama motoru botlarının siteyle gerçekte nasıl etkileşim kurduğunu anlama çalışmasıdır. Tarama araçları sitenin nasıl taranabileceğini simüle eder; log verisi ise gerçekte ne olduğunu gösterir. Bu nedenle log analizi teknik SEO'da doğrulayıcı kaynaktır.

## 1. Log Verisi Ne İçerir?

Standart bir erişim kaydında şu alanlar bulunur: istek zamanı, istemci IP adresi, istenen URL, HTTP metodu, dönen durum kodu, yanıt boyutu, kullanıcı aracısı (user agent) ve yönlendiren adres. Bu alanlar tek başına anlamlı değildir; bot bazında gruplanıp zaman serisine dönüştürüldüğünde değer üretir.

## 2. Veri Toplama ve Hazırlık

1. **Kapsam:** En az dört haftalık kayıt, mevsimsel etkileri görmek için tercihen daha uzun dönem.
2. **Bütünlük:** CDN veya yük dengeleyici arkasındaysanız orijinal istemci bilgisinin korunduğundan emin olun; aksi halde bot trafiği kaybolur.
3. **Bot doğrulama:** Kullanıcı aracısı taklit edilebilir. Gerçek botları ters DNS sorgusu ve ardından ileri DNS doğrulamasıyla teyit edin.
4. **Normalizasyon:** URL'leri küçük harfe indirin, izleme parametrelerini ayıklayın, sayfa türüne göre etiketleyin (kategori, ürün, blog, filtre, statik varlık).
5. **Gizlilik:** IP adresleri kişisel veri kapsamına girebilir; saklama süresi ve erişim yetkisi tanımlanmalıdır.

## 3. Hangi Sorular Yanıtlanır?

- Tarama isteklerinin yüzde kaçı gelir üreten sayfalara gidiyor?
- Hangi sayfa türleri gereksiz tarama bütçesi tüketiyor?
- Önemli sayfalar hiç taranıyor mu, hangi sıklıkta?
- Botun karşılaştığı durum kodu dağılımı nasıl (200 / 3xx / 4xx / 5xx)?
- Yönlendirme zincirleri botu kaç adım dolaştırıyor?
- Yeni yayınlanan içerik ne kadar sürede ilk taramayı alıyor?
- Yanıt süreleri tarama hacmini etkiliyor mu?
- Yalnızca logda görünen, hiçbir yerden bağlantı almayan yetim URL'ler var mı?

## 4. Analiz Yaklaşımı

Ham logu sayfa türü boyutuyla birleştirmek en verimli yöntemdir. Örnek bir dağılım tablosu:

| Sayfa türü | Tarama payı | Organik oturum payı | Değerlendirme |
|---|---|---|---|
| Ürün/hizmet | %25 | %60 | Tarama payı artırılmalı |
| Filtre/parametre | %40 | %2 | Kısıtlanmalı |
| Blog | %20 | %30 | Dengeli |
| Statik varlık | %15 | — | Normal |

Bu tabloyu üretmek, aksiyon önceliğini doğrudan görünür kılar.

## 5. Tipik Bulgular ve Aksiyonlar

- **Filtre URL'leri tarama bütçesini yiyor:** Parametre kuralları ve robots kısıtlamaları uygulanır.
- **Yüksek 404 oranı:** Kırık iç bağlantılar düzeltilir, kaldırılan sayfalar için 301/410 kararı verilir.
- **5xx yoğunlaşması:** Belirli saatlerde kaynak yetersizliği olabilir; altyapı ve önbellek gözden geçirilir.
- **Yönlendirme zinciri:** Tüm eski URL'ler doğrudan nihai hedefe bağlanır.
- **Yetim sayfalar:** İç bağlantı verilir veya kaldırılır.
- **Önemli sayfada seyrek tarama:** İç linkleme güçlendirilir, sitemap'te önceliklendirilir, içerik güncellenir.

## 6. Diğer Veri Kaynaklarıyla Birleştirme

Log verisi tek başına eksiktir. Search Console verisiyle birleştirildiğinde "taranıyor ama gösterim almıyor" ve "gösterim alıyor ama seyrek taranıyor" grupları ortaya çıkar. Analytics verisiyle birleştirildiğinde tarama bütçesinin gelir üreten sayfalara ne kadar ayrıldığı ölçülebilir. Tarama aracı çıktısıyla birleştirildiğinde ise site yapısındaki kopukluklar görünür hale gelir.

## 7. Rutin Hale Getirme

Log analizi tek seferlik bir teşhis olarak da yapılabilir, ancak asıl değeri düzenli izlemedir. Aylık olarak durum kodu dağılımı, sayfa türü bazında tarama payı, ortalama yanıt süresi ve yeni içeriğin ilk tarama süresi raporlanmalıdır. Büyük site değişikliklerinden (yeniden yapılandırma, URL değişimi, altyapı taşıma) sonra ise ölçüm sıklığı artırılmalıdır.

## Sık Sorulan Sorular

**Küçük siteler için gerekli mi?** Birkaç yüz sayfalık sitelerde öncelik düşüktür. Kritik hâle geldiği eşik, binlerce URL veya karmaşık filtre yapısıdır.

**Hangi araçlar kullanılır?** Küçük hacimlerde elektronik tablo ve komut satırı araçları yeterlidir. Büyük hacimlerde log analizi için özel araçlar veya bir veri ambarı üzerinde sorgulama tercih edilir.

**Ne kadar log saklanmalı?** Trend analizine imkân verecek kadar; genellikle 6-12 ay. Saklama süresi gizlilik politikasıyla uyumlu olmalıdır.
