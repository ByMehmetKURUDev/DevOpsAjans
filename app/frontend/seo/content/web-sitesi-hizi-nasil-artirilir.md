---
title: "Web Sitesi Hızı Nasıl Artırılır?"
description: "Core Web Vitals metriklerini temel alarak web sitesi hızını artırmanın yolları: görsel optimizasyonu, JavaScript bütçesi, font stratejisi, önbellekleme ve sunucu tarafı iyileştirmeler."
keywords: "web sitesi hızı, site hızlandırma, Core Web Vitals, LCP iyileştirme, CLS düzeltme, PageSpeed Insights, sayfa yükleme hızı"
category: "Website"
tags:
  - "Website"
  - "Performans"
  - "Core Web Vitals"
date: "2026-02-03"
lang: "tr"
og_title: "Web Sitesi Hızı Nasıl Artırılır?"
og_description: "LCP, CLS ve INP metriklerini iyileştiren uygulanabilir performans çalışmaları."
og_type: "article"
twitter_card: "summary"
twitter_title: "Web Sitesi Hızı Nasıl Artırılır?"
twitter_description: "Görsel, JavaScript, font ve önbellek katmanlarında pratik hız optimizasyonu."
og_image: "https://mehmetkuru.dev/blog-covers/web-sitesi-hizi-nasil-artirilir.webp"
og_image_alt: "Web Sitesi Hızı Nasıl Artırılır?"
---
Site hızı tek bir sayı değildir. Kullanıcı deneyimini belirleyen üç ayrı davranış vardır: ana içeriğin ne zaman göründüğü, düzenin oturma sırasında kayıp kaymadığı ve etkileşimlere ne kadar hızlı yanıt verildiği. Bu üçü Core Web Vitals metrikleriyle ölçülür ve her biri farklı yöntemlerle iyileştirilir.

## 1. Ölçmeden Optimize Etmeyin

İki tür veri vardır. **Lab verisi** (Lighthouse, PageSpeed Insights) kontrollü koşullarda ölçüm yapar ve hata ayıklama için uygundur. **Alan verisi** (gerçek kullanıcı ölçümü) kullanıcıların gerçek cihaz ve bağlantılarını yansıtır ve karar için daha güvenilirdir.

Önce mobil ölçüm alınmalıdır; sorunların büyük kısmı mobil cihazlarda ortaya çıkar.

## 2. LCP: Ana İçeriği Hızlı Gösterin

LCP genellikle hero görseli veya büyük bir başlık bloğudur. İyileştirme adımları:

- LCP görselini WebP veya AVIF formatına dönüştürün; büyük PNG dosyaları çoğu sitede en büyük tek kayıptır,
- `srcset` ve `sizes` ile cihaz genişliğine uygun boyut sunun,
- LCP görselini `loading="lazy"` yapmayın; aksine `fetchpriority="high"` ve `preload` kullanın,
- kritik CSS'i erken sunun, render'ı bloke eden gereksiz stil dosyalarını ayırın,
- sunucu yanıt süresini (TTFB) düşürün: önbellek, CDN ve verimli sorgular.

## 3. CLS: Düzen Kaymasını Sıfıra Yaklaştırın

Düzen kayması çoğunlukla dört nedenden kaynaklanır:

- görsel ve iframe'lerde `width`/`height` veya `aspect-ratio` tanımlı değil,
- web fontu yüklenince metin ölçüsü değişiyor (`font-display: swap` ve benzer metrikli yedek font kullanın),
- reklam veya gömülü içerik için yer ayrılmamış,
- içerik sonradan üste ekleniyor (bildirim çubuğu, çerez bandı).

## 4. INP: Etkileşim Yanıtını Hızlandırın

Etkileşim gecikmesinin ana kaynağı ana iş parçacığını uzun süre meşgul eden JavaScript'tir. Yapılacaklar:

- kullanılmayan kütüphaneleri kaldırın; bir tarih veya grafik kütüphanesi tek bir sayfa için tüm siteye yüklenmemelidir,
- rota bazlı kod bölme uygulayın; her sayfa yalnızca ihtiyacı olan kodu indirsin,
- ağır bileşenleri (grafik, harita, editör) yalnızca görünür olduklarında yükleyin,
- uzun döngüleri parçalayın, gereksiz yeniden render'ları önleyin.

## 5. Üçüncü Taraf Script'lerini Kontrol Altına Alın

Analytics, chat, reklam ve sosyal gömülü içerikler genellikle en pahalı yüklerdir. Uygulanabilir kurallar:

- ölçüm script'lerini ilk etkileşimden veya boşta kalma anından sonra yükleyin,
- gerçekten gerekli olmayan etiketleri kaldırın; etiket yöneticisi içinde yıllardır kullanılmayan tag'ler birikir,
- sosyal medya gömülü içeriklerini statik görsel + bağlantı ile değiştirin.

## 6. Önbellekleme ve Aktarım Katmanı

- statik varlıklara uzun süreli `Cache-Control` ve içerik hash'i uygulayın,
- HTML için kısa süreli veya doğrulamalı önbellek kullanın,
- Brotli veya Gzip sıkıştırmayı etkinleştirin,
- HTTP/2 veya HTTP/3 üzerinden sunun,
- CDN ile içeriği kullanıcıya coğrafi olarak yaklaştırın.

## 7. Sürdürülebilirlik: Performans Bütçesi

Optimizasyon bir kez yapılıp bırakılırsa birkaç ay içinde geri kaybedilir. Bunu önlemek için sayfa başına JavaScript ve görsel boyutu üst sınırı belirlenir, her yayın öncesi otomatik ölçüm alınır ve eşiği aşan değişiklikler gözden geçirilir.

## Sık Sorulan Sorular

**PageSpeed skoru 100 olmalı mı?** Hayır. Skor bir teşhis aracıdır. Hedef, gerçek kullanıcı metriklerinin iyi eşiklerde kalmasıdır.

**Eklenti ile hızlandırma yeterli mi?** Önbellek eklentileri belirli kazanç sağlar ancak ağır tema, gereksiz script ve büyük görseller gibi kök nedenleri çözmez.

**Hız SEO'yu etkiler mi?** Sayfa deneyimi sinyalleri sıralama faktörleri arasındadır; ayrıca hız doğrudan dönüşüm oranını etkiler.
