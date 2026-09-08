---
title: "Tasarım Sistemi Nasıl Kurulur?"
description: "Tasarım sistemi kurma rehberi: tasarım token'ları, bileşen kütüphanesi, dokümantasyon, sürümleme, erişilebilirlik standartları ve ekip benimseme stratejisi."
keywords: "tasarım sistemi, design system, tasarım token, bileşen kütüphanesi, design tokens, UI kit, komponent dokümantasyonu, tutarlılık"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "Tasarım Sistemi"
  - "UI/UX"
date: "2026-09-02"
lang: "tr"
og_title: "Tasarım Sistemi Nasıl Kurulur?"
og_description: "Token'lardan bileşen kütüphanesine tasarım sistemi kurma yöntemi."
og_type: "article"
twitter_card: "summary"
twitter_title: "Tasarım Sistemi Nasıl Kurulur?"
twitter_description: "Tutarlı ve ölçeklenebilir arayüzler için tasarım sistemi kurmak."
---

# Tasarım Sistemi Nasıl Kurulur?

Tasarım sistemi, bir ürünün arayüzünü oluşturan kararların tek bir kaynakta toplanmasıdır: renkler, boşluklar, tipografi, bileşenler, davranış kalıpları ve erişilebilirlik standartları. Amaç estetik bir kütüphane üretmek değil; her yeni ekranın tutarlı, hızlı ve doğru biçimde inşa edilmesini sağlamaktır.

Sistem kurulmadığında ortaya çıkan tablo tanıdıktır: on farklı buton stili, birbirine benzemeyen form alanları, her ekranda farklı boşluk değerleri ve her yeni özellikte baştan verilen kararlar.

## 1. Token Katmanı: Temel

Tasarım token'ları, ham değerlerin anlamlı isimlerle tanımlanmasıdır. İki seviyeli yaklaşım en dayanıklısıdır:

**Temel token'lar.** Ham değerler: renk paletindeki tonlar, boşluk ölçeği, yazı boyutları, yarıçap ve gölge değerleri.

**Anlamsal token'lar.** Kullanım amacına göre isimlendirilmiş referanslar: yüzey rengi, birincil eylem rengi, tehlike durumu rengi, gövde metni rengi, kenarlık rengi.

Bileşenler yalnızca anlamsal token'ları kullanır. Bu ayrım sayesinde tema değişikliği (açık/koyu mod, marka varyantı) tek katmanda çözülür.

**Boşluk ölçeği** özellikle önemlidir. Serbest değerler yerine sınırlı bir ölçek (4, 8, 12, 16, 24, 32, 48, 64) kullanmak görsel ritmi kendiliğinden sağlar.

**Tipografi ölçeği** benzer biçimde tanımlanır: sınırlı sayıda boyut, her boyut için satır yüksekliği ve harf aralığı.

## 2. Bileşen Kütüphanesi

Bileşenler öncelik sırasına göre üretilir. En sık kullanılanlar önce:

1. buton, bağlantı,
2. metin girdisi, seçim alanı, onay kutusu, radyo,
3. kart, ayırıcı, etiket/badge,
4. modal, açılır menü, ipucu (tooltip),
5. tablo, sekme, sayfalama,
6. bildirim ve uyarı bileşenleri,
7. yükleme ve boş durum bileşenleri.

Her bileşen için tüm durumlar tanımlanmalıdır: varsayılan, üzerine gelme, odak, basılı, devre dışı, hata, yükleniyor, seçili. Eksik durum tanımı, geliştirme aşamasında tutarsız çözümlere yol açar.

**Kritik kural:** Bileşenler iş kuralı içermez. Bir buton neyin gönderileceğini bilmez; bir tablo veriyi nereden aldığını bilmez. Bu ayrım bileşenlerin yeniden kullanılabilirliğini korur.

## 3. Erişilebilirlik Bileşen Düzeyinde Çözülür

Erişilebilirlik her kullanımda yeniden düşünülmemelidir. Bileşen içine yerleşik olması gerekenler: doğru semantik element seçimi, klavye davranışı (modal odak tuzağı, menüde ok tuşları, `Escape` ile kapatma), görünür odak göstergesi, etiket-girdi ilişkilendirmesi, hata mesajı bağlantısı ve yeterli kontrast oranı sağlayan token seçimleri.

Bir bileşen erişilebilir olarak üretildiğinde, onu kullanan yüzlerce ekran otomatik olarak erişilebilir olur.

## 4. Dokümantasyon

Belgelenmeyen sistem kullanılmaz. Her bileşen için gerekli minimum bilgi:

- ne zaman kullanılır, ne zaman kullanılmaz,
- prop/varyant listesi ve anlamları,
- canlı örnekler (tüm durumlarla),
- erişilebilirlik notları,
- yaygın hatalar.

Ayrıca sistem düzeyinde kılavuzlar gerekir: renk kullanım kuralları, boşluk uygulama prensipleri, tipografi hiyerarşisi, ikon kullanımı, hata ve boş durum yazım tonu.

## 5. Sürümleme ve Değişiklik Yönetimi

Tasarım sistemi bir üründür ve tüketicileri vardır:

- anlamsal sürümleme kullanılır; kırıcı değişiklikler açıkça işaretlenir,
- değişiklik günlüğü tutulur,
- kaldırılacak bileşenler önce "kullanımdan kaldırılacak" olarak işaretlenir, geçiş yolu belgelenir,
- görsel regresyon testleri beklenmeyen görünüm değişikliklerini yakalar.

## 6. Benimseme Stratejisi

En sık başarısızlık nedeni teknik değil, benimsenme eksikliğidir. İşe yarayan yaklaşımlar:

- mevcut kodu bir gecede taşımak yerine yeni ekranlarda sistemi zorunlu kılmak,
- en sık kullanılan üç bileşenle başlayıp değeri görünür kılmak,
- sistemi kullanmanın kendi çözümünü yazmaktan hızlı olmasını sağlamak,
- ekipten gelen ihtiyaçları sisteme geri beslemek,
- token dışı ham değer kullanımını linter kurallarıyla tespit etmek.

Sistem, ekiplere dayatılan bir kısıt gibi hissettirilirse etrafından dolaşılır.

## 7. Tasarım ve Kod Senkronizasyonu

Tasarım aracındaki kütüphane ile koddaki bileşenlerin ayrışması yaygın bir problemdir. Azaltma yolları: token'ları tek bir kaynaktan üretip her iki tarafa dağıtmak, isimlendirmeyi birebir aynı tutmak, yeni bileşenlerin her iki tarafta aynı sprint içinde tanımlanması ve düzenli senkronizasyon gözden geçirmeleri.

## 8. Ölçüm

Sistemin işe yarayıp yaramadığı ölçülebilir: sistem bileşeni kullanım oranı, tek seferlik (özel) stil sayısı, yeni bir ekranın hazırlanma süresi, tespit edilen erişilebilirlik ihlali sayısı ve arayüz kaynaklı hata bildirimleri.

## Sık Sorulan Sorular

**Hazır bir kütüphaneyi mi kullanmalıyım, kendi sistemimi mi kurmalıyım?** Erişilebilir bir temel kütüphane üzerine kendi token ve bileşen katmanınızı kurmak çoğu ekip için en verimli yoldur. Sıfırdan üretim yalnızca çok özel gereksinimlerde anlamlıdır.

**Ne zaman kurulmalı?** İkinci veya üçüncü benzer ekran yazıldığında. Çok erken kurmak gereksiz soyutlama, çok geç kurmak pahalı taşıma üretir.

**Küçük ekipler için gerekli mi?** Token katmanı ve temel bileşenler tek kişilik projede bile zaman kazandırır. Kapsamlı dokümantasyon ve sürümleme ise ekip büyüdükçe anlam kazanır.
