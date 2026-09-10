---
title: "Mobil Uyumlu Web Tasarım Nedir?"
description: "Mobil uyumlu web tasarımın tanımı, responsive ile adaptive yaklaşım farkı, mobile-first tasarım pratikleri, dokunma ergonomisi ve mobil performans kontrol listesi."
keywords: "mobil uyumlu web tasarım, responsive web tasarım, mobile first, mobil site optimizasyonu, dokunma hedefi boyutu, viewport ayarı"
category: "Website"
tags:
  - "Website"
  - "Web Tasarım"
  - "Mobil"
date: "2026-02-11"
lang: "tr"
og_title: "Mobil Uyumlu Web Tasarım Nedir?"
og_description: "Mobile-first yaklaşım, dokunma ergonomisi ve mobil performans pratikleri."
og_type: "article"
twitter_card: "summary"
twitter_title: "Mobil Uyumlu Web Tasarım Nedir?"
twitter_description: "Responsive tasarımın teknik ve ergonomik gereklilikleri."
og_image: "https://mehmetkuru.dev/blog-covers/mobil-uyumlu-web-tasarim.webp"
og_image_alt: "Mobil Uyumlu Web Tasarım Nedir?"
---
Mobil uyumlu tasarım, sayfanın küçük ekranda küçülerek sığması değildir. İçeriğin, gezinmenin ve etkileşim öğelerinin mobil kullanım koşullarına göre yeniden düzenlenmesidir. Bu koşullar masaüstünden üç açıdan farklıdır: ekran alanı sınırlıdır, giriş yöntemi parmaktır ve bağlantı ile işlem gücü genellikle daha zayıftır.

## 1. Responsive ve Adaptive Yaklaşım

**Responsive tasarım** tek bir HTML çıktısını esnek grid, yüzdesel genişlik ve medya sorgularıyla her ekrana uyarlar. Bakımı kolaydır ve SEO açısından tercih edilen yaklaşımdır.

**Adaptive tasarım** belirli kırılma noktaları için ayrı düzenler tanımlar. Daha fazla kontrol sağlar, ancak bakım yükü artar.

Ayrı bir mobil alan adı (m.site.com) günümüzde tavsiye edilmez; içerik ikiye ayrıldığı için hem SEO hem bakım maliyeti yükselir.

## 2. Mobile-First Tasarım Sırası

Mobile-first, tasarıma en küçük ekrandan başlamak demektir. Bu sıra bir disiplin getirir: sınırlı alanda yalnızca gerçekten gerekli öğeler kalır. Masaüstüne çıkıldığında öğe eklenir; tersi yönde çalışıldığında ise mobilde ne çıkarılacağına dair keyfi kararlar alınır.

Pratik uygulama:

- sayfa başına tek birincil eylem belirleyin,
- ilk ekranda başlık, kısa değer önerisi ve eylem butonu bulunsun,
- ikincil bilgileri katlanabilir bölümlere alın,
- uzun formları adımlara bölün.

## 3. Teknik Temel

- `<meta name="viewport" content="width=device-width, initial-scale=1">` tanımlı olmalıdır,
- yatay kaydırma oluşmamalıdır; sabit genişlikli konteyner ve taşan tablolardan kaçınılmalıdır,
- gövde metni mobilde en az 16px olmalıdır; küçük punto hem okunabilirliği hem erişilebilirliği düşürür,
- dokunma hedefleri en az 44×44 piksel ve birbirinden yeterince ayrık olmalıdır,
- `:hover` üzerine kurulu menüler mobilde çalışmaz; dokunmayla açılan alternatif gerekir,
- geniş tablolar mobilde kart görünümüne veya yatay kaydırılabilir bir kapsayıcıya dönüştürülmelidir.

## 4. Mobil Gezinme

Hamburger menü yaygındır ancak tek çözüm değildir. Az sayıda ana bölüm varsa alt sabit gezinme çubuğu veya yatay kaydırmalı sekme daha keşfedilebilir olur. Menü içinde arama, iletişim ve birincil eylem kolay erişilebilir olmalıdır. Parmakla erişimin en rahat olduğu bölge ekranın alt yarısıdır; kritik eylemler oraya yaklaştırılabilir.

## 5. Formlar ve Girdi Ergonomisi

- doğru `type` ve `inputmode` kullanın: telefon için `tel`, e-posta için `email`, sayısal alanlar için `numeric`,
- `autocomplete` özellikleriyle otomatik doldurmayı destekleyin,
- etiketleri yalnızca placeholder ile vermeyin; kalıcı etiket kullanın,
- hata mesajlarını ilgili alanın hemen yanında gösterin,
- gereksiz alanları kaldırın; her ek alan mobilde tamamlama oranını düşürür.

## 6. Mobil Performans

Mobil uyumluluk görsel bir konu olduğu kadar performans konusudur:

- görselleri WebP/AVIF olarak ve cihaz genişliğine uygun boyutta sunun,
- `width`/`height` tanımlayarak düzen kaymasını önleyin,
- ilk ekran dışındaki görselleri `loading="lazy"` ile erteleyin,
- otomatik oynayan büyük videolardan kaçının,
- özel font sayısını sınırlayın ve `font-display: swap` uygulayın.

## 7. Test Yöntemi

Tarayıcı cihaz emülasyonu ilk kontrol için yeterlidir ancak son kontrol gerçek cihazda yapılmalıdır. Test listesi: gerçek bir orta segment Android cihaz, düşük bağlantı hızı simülasyonu, tek elle kullanım denemesi, ekran okuyucu ile temel gezinme ve yatay/dikey yön değişimi.

## Sık Sorulan Sorular

**Mobil uyumluluk SEO için zorunlu mu?** Arama motorları ağırlıklı olarak mobil sürümü indeksler; mobil deneyim doğrudan görünürlüğü etkiler.

**Ayrı mobil uygulama gerekir mi?** İçerik tüketimi ve dönüşüm odaklı ihtiyaçlarda iyi bir mobil web genellikle yeterlidir. Bildirim, çevrimdışı kullanım veya cihaz donanımı gerektiren senaryolarda uygulama anlam kazanır.

**Tasarımı mobilde ne kadar basitleştirmeliyim?** İçeriği silmek yerine hiyerarşiyi düzenlemek gerekir; mobil kullanıcı da aynı bilgiye ihtiyaç duyar.
