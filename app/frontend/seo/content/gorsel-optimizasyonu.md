---
title: "Görsel Optimizasyonu: Web Performansı İçin Görsel Stratejisi"
description: "Web için görsel optimizasyonu: WebP ve AVIF format seçimi, responsive srcset, tembel yükleme, LCP görseli önceliklendirme, CDN kullanımı ve düzen kaymasını önleme."
keywords: "görsel optimizasyonu, WebP, AVIF, srcset, responsive images, lazy loading, LCP görseli, görsel sıkıştırma, CDN"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "Performans"
  - "Görsel Optimizasyonu"
date: "2026-08-19"
lang: "tr"
og_title: "Görsel Optimizasyonu"
og_description: "Format seçimi, duyarlı boyutlandırma ve yükleme stratejisiyle görsel performansı."
og_type: "article"
twitter_card: "summary"
twitter_title: "Görsel Optimizasyonu"
twitter_description: "Web görsellerini doğru format, boyut ve yükleme stratejisiyle sunmak."
og_image: "https://mehmetkuru.dev/blog-covers/gorsel-optimizasyonu.webp"
og_image_alt: "Görsel Optimizasyonu: Web Performansı İçin Görsel Stratejisi"
---
Tipik bir web sayfasında transfer edilen verinin en büyük kalemi görsellerdir. Bu nedenle görsel optimizasyonu, performans çalışmasında en yüksek getirili müdahale alanıdır. Doğru yapıldığında sayfa boyutu birkaç kat küçülür, LCP metriği belirgin biçimde iyileşir ve düzen kaymaları ortadan kalkar.

## 1. Format Seçimi

**AVIF.** En yüksek sıkıştırma verimliliğini sunar; fotoğraflarda JPEG'e göre çok daha küçük dosya üretir. Kodlama süresi daha uzundur.

**WebP.** Geniş tarayıcı desteği ve iyi sıkıştırma dengesi sağlar. Fotoğraf ve grafik için pratik varsayılan seçimdir.

**JPEG.** Yedek format olarak kullanılır; eski istemciler için gereklidir.

**PNG.** Yalnızca şeffaflık gerektiren ve az renkli grafiklerde. Fotoğraflar için kullanılmamalıdır; dosya boyutu gereksiz büyür.

**SVG.** Logo, ikon ve çizimler için idealdir. Ölçeklenebilir ve genellikle çok küçüktür. Yayına almadan önce temizlenmeli (gereksiz metadata kaldırılmalı).

Pratik yaklaşım `<picture>` elementiyle katmanlı sunumdur: önce AVIF, sonra WebP, en sonda JPEG yedeği.

## 2. Doğru Boyut: En Sık Yapılan Hata

Ekranda 400 piksel genişlikte görünen bir görseli 2400 piksel genişlikte sunmak, en yaygın performans hatasıdır. Çözüm duyarlı görsel sunumudur:

- `srcset` ile aynı görselin farklı genişlikte sürümleri tanımlanır,
- `sizes` ile öğenin farklı ekran genişliklerindeki yerleşim boyutu bildirilir,
- tarayıcı, cihaz genişliği ve piksel yoğunluğuna göre en uygun dosyayı seçer.

Sanatsal kırpma gerekiyorsa (mobilde dikey, masaüstünde geniş kadraj) `<picture>` içinde `media` koşullarıyla farklı görseller sunulur.

## 3. Sıkıştırma Ayarı

Kalite ayarı kör bir değer olarak uygulanmamalıdır. Fotoğraflarda genellikle %70-80 kalite aralığı gözle farkedilir kayıp olmadan belirgin boyut kazancı sağlar. Uygulanacak diğer adımlar: metadata (EXIF) temizliği, gereksiz renk profillerinin kaldırılması, grafiklerde renk paleti azaltma ve çok büyük kaynak dosyaların üretim öncesi yeniden boyutlandırılması.

## 4. Yükleme Stratejisi

**İlk ekran görselleri.** LCP öğesi olan görsel asla tembel yüklenmemelidir. `loading="eager"`, `fetchpriority="high"` ve gerekirse `preload` kullanılır.

**İlk ekran dışındaki görseller.** `loading="lazy"` ile ertelenir. Bu, ilk yüklemede indirilen veri miktarını büyük ölçüde azaltır.

**Kod çözme.** `decoding="async"` ana iş parçacığının bloke olmasını azaltır.

**Bağlantı ipuçları.** Farklı bir alan adından servis ediliyorsa `preconnect` ile bağlantı erken kurulur.

## 5. Düzen Kaymasını Önlemek

Boyutu bildirilmeyen görseller yüklendiklerinde düzeni kaydırır ve CLS metriğini bozar. Önlem: her `<img>` öğesine `width` ve `height` öznitelikleri veya CSS'te `aspect-ratio` tanımlamak. Değerler gerçek en-boy oranını yansıtmalıdır; yanlış oran görselin bozulmasına yol açar.

## 6. CDN ve Görsel Dönüşüm Servisleri

Görselleri kullanıcının coğrafi konumuna yakın bir dağıtım ağından sunmak gecikmeyi azaltır. Görsel dönüşüm yeteneği olan servisler ayrıca URL parametreleriyle anlık yeniden boyutlandırma, format dönüşümü ve kalite ayarı sağlar. Bu, farklı boyutları önceden üretme yükünü ortadan kaldırır.

Önbellek başlıkları doğru ayarlanmalıdır: içerik hash'i içeren dosya adlarıyla uzun süreli önbellek kullanılabilir.

## 7. Görsel Sayısını Azaltmak

Optimizasyonun en etkili biçimi bazen görseli hiç kullanmamaktır:

- dekoratif efektler için CSS gradyan ve şekiller,
- ikonlar için SVG veya ikon bileşenleri,
- tekrarlayan desenler için CSS pattern,
- kalabalık galeri yerine kademeli yükleme.

## 8. Erişilebilirlik ve SEO Yönü

- anlamlı görsellerde açıklayıcı `alt` metni; dekoratif görsellerde `alt=""`,
- dosya adlarının içeriği tanımlaması,
- görsel sitemap'i veya yapılandırılmış veriyle bağlam sağlanması,
- görselin çevresindeki metinle ilişkili olması.

## 9. Otomasyon ve Denetim

Görsel optimizasyonu elle sürdürülemez. Yayın hattına eklenmesi gereken kontroller: dosya boyutu eşiği aşan görsellerin uyarı üretmesi, eski formatta yüklenen dosyaların tespiti, `width`/`height` eksikliği kontrolü ve `alt` metni denetimi. Ayrıca yükleme sürecinde otomatik format dönüşümü ve boyut üretimi kurulmalıdır.

## Sık Sorulan Sorular

**Tüm görselleri AVIF'e mi çevirmeliyim?** Katmanlı sunum (AVIF → WebP → JPEG) en güvenli yaklaşımdır; destek durumuna göre tarayıcı en uygununu seçer.

**Tembel yükleme her görselde kullanılmalı mı?** Hayır. İlk ekranda görünen ve özellikle LCP öğesi olan görselde kullanılması performansı kötüleştirir.

**Ne kadar sıkıştırma çok fazla?** Görsel türüne bağlıdır. Ürün ve portfolyo görsellerinde kalite kritik olduğu için daha yüksek kalite ayarı, arka plan ve dekoratif görsellerde daha agresif sıkıştırma uygundur.
