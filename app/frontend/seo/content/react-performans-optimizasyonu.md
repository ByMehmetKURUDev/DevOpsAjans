---
title: "React Performans Optimizasyonu"
description: "React uygulamalarında performans optimizasyonu: gereksiz render'ları önleme, memoizasyon, kod bölme, liste sanallaştırma, bundle küçültme ve ölçüm yöntemleri."
keywords: "React performans, gereksiz render, useMemo useCallback, React.memo, kod bölme, lazy loading, liste sanallaştırma, bundle boyutu"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "React"
  - "Performans"
date: "2026-07-29"
lang: "tr"
og_title: "React Performans Optimizasyonu"
og_description: "Render maliyeti, bundle boyutu ve etkileşim gecikmesini azaltma teknikleri."
og_type: "article"
twitter_card: "summary"
twitter_title: "React Performans Optimizasyonu"
twitter_description: "React uygulamalarında ölçüme dayalı performans iyileştirme."
og_image: "https://mehmetkuru.dev/blog-covers/react-performans-optimizasyonu.webp"
og_image_alt: "React Performans Optimizasyonu"
---
React uygulamalarında performans problemleri iki ana kaynaktan gelir: tarayıcıya gönderilen JavaScript miktarı ve çalışma zamanında yapılan gereksiz iş. İlk grup ilk yükleme süresini, ikinci grup etkileşim akıcılığını etkiler. Optimizasyona başlamadan önce hangi grupta sorun olduğunu ölçmek gerekir; aksi halde etkisiz mikro iyileştirmelerle zaman harcanır.

## 1. Önce Ölçün

Kullanılacak araçlar:

- **React Profiler:** Hangi bileşenin ne kadar süre render edildiğini ve neden yeniden render olduğunu gösterir.
- **Tarayıcı performans sekmesi:** Uzun görevleri, ana iş parçacığı blokajını ve düzen hesaplamalarını gösterir.
- **Bundle analizi:** Paket boyutunun hangi bağımlılıklardan geldiğini ortaya koyar.
- **Alan verisi:** Gerçek kullanıcılarda LCP ve INP metrikleri.

Ölçüm yapılmadan yapılan `useMemo` eklemeleri genellikle fayda üretmez, hatta kod karmaşıklığını artırır.

## 2. Bundle Boyutunu Küçültmek

İlk yükleme performansının en büyük belirleyicisi paket boyutudur.

**Rota bazlı kod bölme.** Her sayfa yalnızca ihtiyacı olan kodu indirmelidir. `React.lazy` ve `Suspense` ile rota bileşenleri ayrı parçalara bölünür.

**Ağır bağımlılıkları erteleme.** Grafik, harita, zengin metin editörü, PDF üretimi gibi kütüphaneler yalnızca kullanıldıkları ekranda yüklenir.

**Bağımlılık denetimi.** Tek bir yardımcı fonksiyon için büyük bir kütüphane eklemekten kaçının. Aynı işi yapan birden fazla kütüphanenin (örneğin iki farklı tarih kütüphanesi) projede bulunması yaygın bir sorundur.

**Ağaç sarsma (tree shaking) uyumu.** Modüler içe aktarma kullanın; tüm kütüphaneyi tek isimle içe aktarmak kullanılmayan kodun paketle gelmesine yol açar.

## 3. Gereksiz Render'ları Önlemek

React'te bir bileşen, durumu değiştiğinde veya ebeveyni yeniden render edildiğinde tekrar render olur. Sorun, render'ın kendisi değil pahalı render'ların gereksiz tekrarıdır.

**Durumu aşağıya taşımak.** Sık değişen durumu, onu gerçekten kullanan en alt bileşende tutmak en etkili tekniktir. Üst seviyede tutulan bir durum tüm ağacı yeniden render eder.

**Bileşen bölme.** Sık değişen bölümü ayrı bir bileşene çıkarmak, kardeş bileşenlerin gereksiz render'ını önler.

**`React.memo`.** Aynı prop'larla çağrıldığında render'ı atlar. Yalnızca pahalı render eden ve prop'ları gerçekten stabil olan bileşenlerde anlamlıdır.

**`useMemo` ve `useCallback`.** Pahalı hesaplamaları ve alt bileşene geçirilen fonksiyon referanslarını stabil tutar. Her yerde kullanmak fayda değil maliyet üretir.

**Context bölme.** Tek büyük context yerine, farklı güncelleme sıklığına sahip verileri ayrı context'lere bölmek gereksiz render'ları belirgin biçimde azaltır.

**Liste anahtarları.** `key` olarak dizi indeksi kullanmak, liste değiştiğinde gereksiz yeniden oluşturmaya ve durum karışmasına yol açar; kararlı bir kimlik kullanılmalıdır.

## 4. Uzun Listeler

Yüzlerce veya binlerce satırlık listelerde tüm öğeleri render etmek ana iş parçacığını kilitler. Çözümler: pencereleme/sanallaştırma (yalnızca görünür satırları render etme), sayfalama, sonsuz kaydırmada parça parça yükleme ve satır bileşenlerini hafif tutma.

## 5. Veri Getirme Stratejisi

- aynı veriyi birden çok bileşende ayrı ayrı istemek yerine paylaşılan bir önbellek katmanı kullanın,
- ardışık bağımlı isteklerden kaçının; mümkünse paralel çalıştırın,
- ilk ekran için gereken veriyi öncelikli yükleyin, geri kalanı erteleyin,
- iskelet (skeleton) durumları düzen kaymasını önleyecek biçimde tasarlayın,
- gereksiz yeniden getirmeleri (refetch) sınırlayın.

## 6. Görsel ve Medya

Görseller genellikle en büyük transfer kalemidir. Modern format kullanımı, `srcset` ile duyarlı boyutlandırma, ilk ekran dışındaki görsellerde `loading="lazy"`, boyut tanımlarıyla düzen kaymasının önlenmesi ve LCP görselinde yüksek öncelik ayarı temel uygulamalardır.

## 7. Animasyon ve Etkileşim

Animasyonlarda düzen tetikleyen özellikler (`width`, `height`, `top`, `left`) yerine `transform` ve `opacity` kullanılmalıdır. Kaydırma ve yeniden boyutlandırma dinleyicileri kısıtlanmalı (throttle/debounce), görünürlük tespiti için `IntersectionObserver` tercih edilmelidir. `prefers-reduced-motion` desteği hem erişilebilirlik hem performans açısından yararlıdır.

## 8. Sürdürülebilirlik

Kazanımları korumak için performans bütçesi tanımlanır: sayfa türü başına JavaScript boyutu, görsel toplamı ve metrik eşikleri. Her yayın öncesi otomatik ölçüm alınır; bütçe aşıldığında değişiklik gözden geçirilir.

## Sık Sorulan Sorular

**Her bileşeni memo'lamalı mıyım?** Hayır. Gereksiz memoizasyon karşılaştırma maliyeti ve kod karmaşıklığı ekler. Yalnızca ölçümle doğrulanmış noktalarda kullanılmalıdır.

**En büyük kazanç nereden gelir?** Genellikle bundle boyutunu küçültmek ve görselleri optimize etmek, çalışma zamanı mikro iyileştirmelerinden çok daha fazla etki üretir.

**Sunucu tarafı render gerekli mi?** İlk görüntüleme hızı ve arama görünürlüğü kritikse belirgin fayda sağlar; kimlik doğrulama arkasındaki panellerde önceliği düşüktür.
