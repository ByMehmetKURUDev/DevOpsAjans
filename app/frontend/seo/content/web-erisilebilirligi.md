---
title: "Web Erişilebilirliği (a11y) Rehberi"
description: "Web erişilebilirliği nasıl sağlanır? WCAG ilkeleri, semantik HTML, klavye gezinmesi, ekran okuyucu uyumu, renk kontrastı, form erişilebilirliği ve test yöntemleri."
keywords: "web erişilebilirliği, a11y, WCAG, semantik HTML, ekran okuyucu, klavye gezinmesi, renk kontrastı, ARIA, erişilebilirlik testi"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "Erişilebilirlik"
  - "UX"
date: "2026-08-12"
lang: "tr"
og_title: "Web Erişilebilirliği (a11y) Rehberi"
og_description: "Semantik HTML, klavye gezinmesi ve kontrast ile erişilebilir arayüzler."
og_type: "article"
twitter_card: "summary"
twitter_title: "Web Erişilebilirliği (a11y) Rehberi"
twitter_description: "WCAG ilkeleri ve uygulanabilir erişilebilirlik pratikleri."
og_image: "https://mehmetkuru.dev/blog-covers/web-erisilebilirligi.webp"
og_image_alt: "Web Erişilebilirliği (a11y) Rehberi"
---
Erişilebilirlik, bir web arayüzünün farklı yeteneklere, cihazlara ve kullanım koşullarına sahip herkes tarafından kullanılabilmesidir. Kapsamı yalnızca kalıcı engelleri olan kullanıcılar değildir: geçici bir yaralanma, parlak güneş altında ekran okuma, gürültülü ortamda video izleme veya yavaş bağlantı da erişilebilirlik problemi üretir. Bu nedenle erişilebilirlik çalışmaları genel kullanılabilirliği de yükseltir.

## 1. WCAG'in Dört İlkesi

**Algılanabilir.** İçerik duyusal olarak alınabilir olmalı: metin alternatifleri, altyazı, yeterli kontrast.

**Kullanılabilir.** Arayüz farklı giriş yöntemleriyle işletilebilmeli: klavye erişimi, yeterli süre, nöbet tetikleyici içerikten kaçınma.

**Anlaşılabilir.** İçerik ve davranış öngörülebilir olmalı: net dil, tutarlı gezinme, yardımcı hata mesajları.

**Sağlam.** Yardımcı teknolojilerle uyumlu çalışmalı: geçerli işaretleme, standart bileşen davranışları.

## 2. Semantik HTML: En Yüksek Getirili Adım

Erişilebilirliğin büyük kısmı doğru HTML elementi seçmekle çözülür:

- tıklanabilir eylemler için `<button>`, gezinme için `<a href>`,
- sayfa bölümleri için `<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>`,
- başlık hiyerarşisinde atlama yapmadan `<h1>`-`<h6>`,
- listeler için `<ul>`/`<ol>`, tablo verisi için `<table>` ve `<th scope>`,
- form alanları için `<label>` ile ilişkilendirilmiş girdiler.

`<div onclick>` ile buton taklidi yapmak, klavye erişimini ve rol bilgisini kaybettirir. ARIA, doğru elementin yerine geçmez; yalnızca eksik kalan bilgiyi tamamlar.

## 3. Klavye Gezinmesi

Tüm işlevler yalnızca klavye ile tamamlanabilmelidir. Kontrol listesi:

- odak sırası görsel sırayla tutarlı olmalı,
- odak göstergesi her zaman görünür olmalı (`:focus-visible` ile tasarlanabilir, kaldırılmamalı),
- modal açıldığında odak içine alınmalı ve kapanınca tetikleyen öğeye dönmeli,
- açılır menüler `Escape` ile kapanmalı, oklarla gezilebilmeli,
- içeriğe atlama bağlantısı (skip link) bulunmalı,
- klavye tuzağı oluşmamalı.

## 4. Renk ve Görsel Tasarım

- gövde metni için en az 4.5:1, büyük metin için 3:1 kontrast oranı,
- bilgi yalnızca renkle iletilmemeli; ikon, metin veya desen desteği eklenmeli,
- form hataları hem renk hem metinle bildirilmeli,
- odak göstergesi arka planla yeterli kontrasta sahip olmalı,
- metin ölçeklendirildiğinde (%200) düzen bozulmamalı.

Buton kontrastı özellikle sık yapılan hatadır: metin rengi arka plan rengiyle aynı tonda olmamalıdır.

## 5. Form Erişilebilirliği

- her girdi kalıcı bir `<label>` ile ilişkilendirilmeli; yalnızca placeholder yeterli değildir,
- zorunlu alanlar hem görsel hem programatik olarak işaretlenmeli,
- hata mesajları ilgili alanla ilişkilendirilmeli (`aria-describedby`) ve alan yanında gösterilmeli,
- gruplandırılmış seçenekler için `<fieldset>` ve `<legend>` kullanılmalı,
- doğru `type`, `inputmode` ve `autocomplete` değerleri tanımlanmalı,
- gönderim sonrası durum (başarı veya hata) ekran okuyucuya duyurulmalı.

## 6. Dinamik İçerik ve ARIA

Tek sayfa uygulamalarında görsel değişimler ekran okuyucuya otomatik bildirilmez. Gerekli önlemler: rota değişiminde sayfa başlığının güncellenmesi ve odağın uygun yere taşınması, canlı bölge (`aria-live`) ile bildirimlerin duyurulması, yükleme durumlarının programatik olarak iletilmesi ve açılır/katlanır bileşenlerde `aria-expanded` gibi durum özniteliklerinin doğru yönetilmesi.

ARIA kullanımında temel kural: gerekmiyorsa kullanmayın. Yanlış ARIA, hiç ARIA olmamasından daha kötüdür.

## 7. Medya

- görsellerde anlamlı `alt` metni; dekoratif görsellerde boş `alt=""`,
- videolarda altyazı, mümkünse transkript,
- sesli içerikte metin alternatifi,
- otomatik oynatmadan kaçınma; kullanıcı kontrolü sunma,
- hareketli içerik için durdurma imkânı ve `prefers-reduced-motion` desteği.

## 8. Test Yöntemi

Otomatik araçlar sorunların yalnızca bir kısmını yakalar; manuel test zorunludur.

**Otomatik:** Tarayıcı denetim araçları ve erişilebilirlik linter'ları ile kontrast, eksik etiket ve geçersiz işaretleme taraması.

**Manuel:** Fareyi kullanmadan tüm akışları tamamlamak, ekran okuyucu ile temel gezinme, %200 yakınlaştırmada düzen kontrolü, yalnızca klavye ile form doldurma.

**Otomatik kontrollere entegrasyon:** Erişilebilirlik kontrollerini yayın hattına eklemek, regresyonları önler.

## 9. Erişilebilirlik ve SEO İlişkisi

Semantik yapı, açıklayıcı bağlantı metni, doğru başlık hiyerarşisi ve görsel alternatif metinleri hem yardımcı teknolojiler hem arama motorları için aynı sinyalleri üretir. Erişilebilirlik çalışması bu nedenle SEO'yu doğrudan destekler.

## Sık Sorulan Sorular

**Erişilebilirlik maliyeti yükseltir mi?** Baştan planlandığında maliyeti düşüktür. Sonradan düzeltme çok daha pahalıdır.

**Hangi seviyeye ulaşmak yeterli?** Genel pratik WCAG AA seviyesini hedeflemektir; kamu ve kurumsal projelerde bu genellikle bir gerekliliktir.

**Otomatik araç yeterli mi?** Değildir. Otomatik testler tespit edilebilir teknik ihlalleri yakalar; anlamlı `alt` metni veya mantıklı odak sırası gibi konular insan değerlendirmesi gerektirir.
