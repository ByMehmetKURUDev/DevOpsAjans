---
title: "Core Web Vitals Nedir? LCP, CLS ve INP Metriklerini Anlamak"
description: "Core Web Vitals metrikleri LCP, CLS ve INP nedir, nasıl ölçülür ve nasıl iyileştirilir? Eşik değerler, ölçüm araçları, tipik sorunlar ve uygulanabilir çözümler."
keywords: "Core Web Vitals, LCP nedir, CLS nedir, INP nedir, sayfa deneyimi metrikleri, web performans ölçümü, alan verisi lab verisi"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "Performans"
  - "Core Web Vitals"
date: "2026-07-22"
lang: "tr"
og_title: "Core Web Vitals Nedir?"
og_description: "LCP, CLS ve INP metriklerinin tanımı, eşikleri ve iyileştirme yöntemleri."
og_type: "article"
twitter_card: "summary"
twitter_title: "Core Web Vitals Nedir?"
twitter_description: "Üç temel performans metriğini ölçme ve iyileştirme rehberi."
---

# Core Web Vitals Nedir?

Core Web Vitals, bir sayfanın kullanıcı deneyimini üç ölçülebilir davranış üzerinden değerlendiren metrik kümesidir: ana içerik ne zaman göründü, düzen yüklenirken kayıp kaydı ve etkileşimlere ne kadar hızlı yanıt verildi. Bu üç metrik farklı kök nedenlere sahiptir; bu nedenle her biri ayrı yöntemlerle iyileştirilir.

## 1. LCP — Largest Contentful Paint

**Ne ölçer:** Görünür alandaki en büyük içerik öğesinin (genellikle hero görseli veya büyük bir başlık bloğu) render edilme süresi.

**Hedef eşik:** 2,5 saniyenin altı iyi kabul edilir.

**Tipik nedenler:**

- büyük ve optimize edilmemiş görsel dosyası,
- yavaş sunucu yanıt süresi (TTFB),
- render'ı bloke eden CSS ve JavaScript,
- istemci tarafında geç oluşturulan içerik,
- LCP öğesinin yanlışlıkla tembel yüklenmesi.

**Çözümler:**

- LCP görselini WebP/AVIF formatına dönüştürün ve `srcset` ile cihaz genişliğine uygun boyut sunun,
- `fetchpriority="high"` ve `preload` uygulayın; `loading="lazy"` kullanmayın,
- kritik CSS'i erken sunun, gereksiz stil dosyalarını ayırın,
- sunucu tarafında önbellek ve CDN kullanın,
- ana içeriği sunucu tarafında render edin.

## 2. CLS — Cumulative Layout Shift

**Ne ölçer:** Sayfa yüklenirken görünür öğelerin beklenmedik biçimde yer değiştirmesinin toplam etkisi.

**Hedef eşik:** 0,1'in altı iyi kabul edilir.

**Tipik nedenler:**

- boyutu tanımlanmamış görsel ve iframe'ler,
- web fontu yüklendiğinde metin ölçüsünün değişmesi,
- reklam veya gömülü içerik için yer ayrılmaması,
- içeriğin üste sonradan eklenmesi (çerez bandı, bildirim çubuğu),
- animasyonda düzen özelliklerinin (`width`, `top`) değiştirilmesi.

**Çözümler:**

- tüm medya öğelerine `width`/`height` veya `aspect-ratio` tanımlayın,
- `font-display: swap` ve yedek fontla benzer metrikler kullanın,
- dinamik içerik alanları için rezerve alan bırakın,
- animasyonlarda `transform` ve `opacity` kullanın.

## 3. INP — Interaction to Next Paint

**Ne ölçer:** Kullanıcı etkileşimlerinden (tıklama, dokunma, tuş) sonra ekranın güncellenmesine kadar geçen süre. FID metriğinin yerini almıştır ve tüm etkileşimleri kapsar.

**Hedef eşik:** 200 milisaniyenin altı iyi kabul edilir.

**Tipik nedenler:**

- ana iş parçacığını uzun süre meşgul eden JavaScript,
- gereksiz büyük paket boyutu,
- ağır ve tekrarlayan bileşen render'ları,
- üçüncü taraf script'lerinin yükü,
- büyük listelerin sanallaştırılmadan render edilmesi.

**Çözümler:**

- rota bazlı kod bölme uygulayın,
- kullanılmayan bağımlılıkları kaldırın,
- uzun görevleri parçalayın,
- ağır bileşenleri görünür olduklarında yükleyin,
- üçüncü taraf script'lerini ilk etkileşim veya boşta kalma sonrasına erteleyin,
- büyük listelerde sanallaştırma kullanın.

## 4. Destekleyici Metrikler

Core Web Vitals'ı yorumlamak için yardımcı metrikler:

- **TTFB:** Sunucunun ilk baytı gönderme süresi; LCP'nin alt bileşenidir.
- **FCP:** İlk içeriğin görünme anı.
- **TBT:** Ana iş parçacığının bloke kaldığı toplam süre; lab ortamında INP için iyi bir vekildir.

## 5. Lab Verisi ve Alan Verisi

**Lab verisi** kontrollü koşullarda ölçülür (Lighthouse, PageSpeed Insights lab bölümü). Hata ayıklama için idealdir; tekrarlanabilir ve nedenleri gösterir.

**Alan verisi** gerçek kullanıcıların cihaz ve bağlantılarından toplanır. Karar için daha güvenilirdir çünkü gerçek kullanıcı dağılımını yansıtır.

İki veri arasında fark olması normaldir. Lab ortamı tek bir cihaz profili kullanır; alan verisi ise 75. yüzdelik dilim üzerinden değerlendirilir. Karar alan verisine, teşhis lab verisine dayandırılmalıdır.

## 6. Ölçüm Sırası

1. alan verisiyle hangi metriğin ve hangi sayfa grubunun sorunlu olduğunu belirleyin,
2. o sayfa türünde lab ölçümü alarak kök nedeni bulun,
3. tek bir değişiklik yapıp yeniden ölçün,
4. değişikliği yayına alın ve alan verisinde etkisini izleyin,
5. performans bütçesi tanımlayarak kazanımı koruyun.

Aynı anda birden fazla değişiklik yapmak, hangisinin işe yaradığını belirsiz kılar.

## 7. Sürdürülebilirlik

Performans iyileştirmeleri bakımsız kalırsa birkaç ay içinde geri kaybedilir. Kalıcı kazanç için sayfa türü başına JavaScript ve görsel boyutu üst sınırı tanımlanır, her yayın öncesi otomatik ölçüm alınır ve eşiği aşan değişiklikler gözden geçirilir.

## Sık Sorulan Sorular

**Skorun 100 olması gerekir mi?** Hayır. Skor bir teşhis göstergesidir; hedef gerçek kullanıcı metriklerinin iyi eşiklerde kalmasıdır.

**Bu metrikler sıralamayı etkiler mi?** Sayfa deneyimi sinyalleri arasında yer alır. Ancak asıl etkileri dönüşüm oranı ve kullanıcı davranışı üzerindedir.

**Mobil ve masaüstü ayrı mı değerlendirilir?** Evet, ayrı ölçülür ve mobil genellikle daha zorlu koşulları yansıttığı için önce iyileştirilmelidir.
