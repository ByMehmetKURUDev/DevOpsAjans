---
title: "Web Tasarım ve Web Geliştirme Arasındaki Fark Nedir?"
description: "Web tasarım ile web geliştirme arasındaki farkı; sorumluluk alanları, kullanılan araçlar, teslim çıktıları ve iki disiplinin projede nasıl birlikte çalıştığı üzerinden açıklıyoruz."
keywords: "web tasarım nedir, web geliştirme nedir, web tasarım web geliştirme farkı, frontend backend farkı, UI UX tasarım, web developer"
category: "Website"
tags:
  - "Website"
  - "Web Tasarım"
  - "Web Geliştirme"
date: "2026-01-20"
lang: "tr"
og_title: "Web Tasarım ve Web Geliştirme Arasındaki Fark"
og_description: "İki disiplinin sorumlulukları, çıktıları ve projede birlikte çalışma biçimi."
og_type: "article"
twitter_card: "summary"
twitter_title: "Web Tasarım ve Web Geliştirme Arasındaki Fark"
twitter_description: "Tasarım ve geliştirme sorumluluklarının net ayrımı ve teslim çıktıları."
og_image: "https://mehmetkuru.dev/blog-covers/web-tasarim-ve-web-gelistirme-farki.webp"
og_image_alt: "Web Tasarım ve Web Geliştirme Arasındaki Fark Nedir?"
---
Web tasarım ve web geliştirme sıkça birbirinin yerine kullanılır. Oysa iki disiplin farklı sorular yanıtlar: tasarım "ne görünecek ve kullanıcı nasıl ilerleyecek" sorusunu, geliştirme "bu deneyim hangi teknik yapıyla güvenli, hızlı ve sürdürülebilir biçimde çalışacak" sorusunu çözer.

## 1. Web Tasarım Ne Yapar?

Web tasarım, kullanıcının ekranda gördüğü ve hissettiği katmanı üretir. Çalışma alanı şu başlıkları kapsar:

- bilgi mimarisi ve sayfa hiyerarşisi,
- akış tasarımı: kullanıcı hangi adımdan hangi adıma geçecek,
- tipografi, renk sistemi ve boşluk düzeni,
- bileşen kütüphanesi: buton, form, kart, tablo durumları,
- mobil, tablet ve masaüstü için responsive davranış,
- erişilebilirlik: kontrast oranları, dokunma alanı boyutları, odak göstergeleri.

Tipik çıktılar: wireframe, tasarım sistemi, sayfa tasarımları ve etkileşim notları.

## 2. Web Geliştirme Ne Yapar?

Web geliştirme, tasarımı çalışan bir ürüne dönüştürür ve iki ana katmanda ilerler.

**Frontend:** HTML, CSS ve JavaScript ile arayüzün tarayıcıda çalışan hali. Bileşen mimarisi, durum yönetimi, form doğrulama, animasyon performansı ve tarayıcı uyumluluğu bu katmanın sorumluluğundadır.

**Backend:** Veritabanı modeli, kimlik doğrulama, yetkilendirme, API'ler, ödeme ve üçüncü taraf entegrasyonları, dosya depolama, önbellekleme ve güvenlik önlemleri.

Tipik çıktılar: kaynak kod, veritabanı şeması, API dokümantasyonu, dağıtım yapılandırması ve testler.

## 3. İki Disiplinin Kesişim Noktaları

Projelerdeki gerçek sorunlar genellikle kesişim noktalarında çıkar:

- **Boş durumlar:** listede hiç kayıt yoksa ekran ne gösterecek?
- **Hata durumları:** form gönderimi başarısız olursa kullanıcı ne görecek?
- **Yükleme durumları:** veri gelene kadar iskelet mi, spinner mı?
- **Uzun içerik:** başlık üç satıra çıktığında kart tasarımı bozulacak mı?
- **Performans bütçesi:** tasarımdaki büyük görsel ve özel font, mobil hızda ne kadar maliyet üretiyor?

Bu durumlar tasarım aşamasında konuşulmazsa geliştirme aşamasında tahminle doldurulur ve sonuç tutarsız olur.

## 4. Hangi Rol Hangi Sorudan Sorumlu?

| Soru | Sorumlu |
|---|---|
| Sayfa hiyerarşisi ve akış nasıl olacak? | Tasarım |
| Buton durumları ve kontrast yeterli mi? | Tasarım |
| Bileşenler nasıl yapılandırılacak? | Frontend |
| Veri nereden gelecek, nasıl saklanacak? | Backend |
| Sayfa mobilde neden yavaş? | Frontend + Tasarım |
| Form verisi kime, nasıl iletilecek? | Backend |

## 5. Küçük Projelerde Tek Kişi Yeterli mi?

Kurumsal tanıtım siteleri gibi sınırlı kapsamlı projelerde her iki tarafı da yürütebilen bir uzman verimli çalışır; iletişim maliyeti düşer. Ancak e-ticaret, üyelik sistemi, panel veya çok dilli yapı gibi ihtiyaçlarda uzmanlaşmış roller daha güvenli sonuç verir. Kritik olan unvan değil, yukarıdaki soruların tamamının bir sahibi olmasıdır.

## Sık Sorulan Sorular

**UI/UX tasarımcısı ile web tasarımcısı aynı şey mi?** UX daha çok araştırma, akış ve kullanılabilirlik; UI görsel dil ve bileşen tasarımı odaklıdır. Küçük ekiplerde bu iki rol tek kişide birleşir.

**Full-stack geliştirici tasarım da yapar mı?** Genellikle mevcut bir tasarım sistemini uygulayabilir; ancak sıfırdan görsel dil ve marka kimliği üretmek ayrı bir uzmanlıktır.

**Hangisi daha maliyetli?** Kapsama bağlıdır. Karmaşık entegrasyon içeren projelerde geliştirme, marka odaklı projelerde tasarım ağırlığı artar.
