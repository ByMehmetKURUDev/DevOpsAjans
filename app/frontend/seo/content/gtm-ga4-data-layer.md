---
title: "GTM ve GA4 için Data Layer Tasarımı"
description: "Data layer nedir, neden gerekir ve nasıl tasarlanır? GTM ile GA4 arasında tutarlı olay şeması, e-ticaret veri yapısı, isimlendirme standardı ve doğrulama yöntemleri."
keywords: "data layer, dataLayer, Google Tag Manager, GTM, GA4 olay şeması, e-ticaret data layer, olay isimlendirme, ölçüm planı"
category: "Reklam"
tags:
  - "Reklam"
  - "Ölçüm"
  - "GTM"
date: "2026-09-02"
lang: "tr"
og_title: "GTM ve GA4 için Data Layer Tasarımı"
og_description: "Tutarlı olay şeması ve doğrulanabilir ölçüm katmanı kurmak."
og_type: "article"
twitter_card: "summary"
twitter_title: "Data Layer Tasarımı"
twitter_description: "GTM ve GA4 için sürdürülebilir veri katmanı şeması."
og_image: "https://mehmetkuru.dev/blog-covers/gtm-ga4-data-layer.webp"
og_image_alt: "GTM ve GA4 için Data Layer Tasarımı"
---
Data layer, web sitesi ile ölçüm araçları arasındaki sözleşmedir. Doğru tasarlandığında ölçüm araçları site kodundan bağımsız hâle gelir; yanlış tasarlandığında her yeni ölçüm ihtiyacı geliştirici müdahalesi gerektirir ve veri tutarsızlaşır.

## 1. Data Layer Nedir?

Sayfada bulunan ve olay bilgisi taşıyan yapılandırılmış bir veri dizisidir. Site kodu bu diziye olay ve bağlam bilgisi yazar; etiket yöneticisi bu bilgiyi okuyup ölçüm araçlarına iletir.

**Neden gerekli:**

- ölçüm mantığı site kodundan ayrılır,
- yeni ölçüm ihtiyaçları geliştirici olmadan karşılanabilir,
- aynı veri farklı araçlara tutarlı biçimde gönderilir,
- CSS seçicilere bağlı kırılgan ölçüm ortadan kalkar.

Data layer olmadan kurulan ölçümler, arayüzde küçük bir tasarım değişikliğinde sessizce bozulur. Bu, en tehlikeli ölçüm hatası türüdür çünkü hata mesajı üretmez.

## 2. Tasarım Sırası: Önce Ölçüm Planı

Kod yazmadan önce ölçüm planı hazırlanır. Plan her olay için şunları tanımlar: olay adı, tetiklenme koşulu, taşıdığı parametreler, parametrelerin veri tipi ve zorunluluk durumu, hangi araca gönderileceği ve hangi iş sorusunu yanıtladığı.

Plan olmadan yazılan data layer, zamanla birbirine benzemeyen olay adlarından oluşan bir yığına dönüşür.

## 3. İsimlendirme Standardı

Tutarlılık, ölçüm kalitesinin temelidir:

- olay adları küçük harf ve alt çizgi ile yazılır (`add_to_cart`),
- GA4'ün önerdiği standart adlar varsa mutlaka onlar kullanılır,
- parametre adları da aynı standarda uyar,
- aynı anlam için tek bir ad kullanılır (`urun_id`, `product_id`, `itemId` karışımı olmaz),
- Türkçe ve İngilizce karışık isimlendirmeden kaçınılır,
- yeni ad eklenmeden önce mevcut şema kontrol edilir.

## 4. E-Ticaret Şeması

E-ticarette GA4'ün beklediği yapı kullanılmalıdır. Temel akış olayları:

| Olay | Tetikleme |
|---|---|
| `view_item_list` | Kategori/liste görüntüleme |
| `select_item` | Listeden ürün seçimi |
| `view_item` | Ürün detay görüntüleme |
| `add_to_cart` | Sepete ekleme |
| `remove_from_cart` | Sepetten çıkarma |
| `view_cart` | Sepet görüntüleme |
| `begin_checkout` | Ödeme başlangıcı |
| `add_shipping_info` | Kargo bilgisi |
| `add_payment_info` | Ödeme bilgisi |
| `purchase` | Sipariş tamamlama |

Her olayda ürün bilgisi ortak bir yapıda taşınır: ürün kimliği, ad, kategori, varyant, marka, fiyat, adet, liste konumu. `purchase` olayında ek olarak sipariş kimliği, toplam tutar, vergi, kargo, indirim kodu ve para birimi gönderilir.

**Kritik nokta:** Sipariş kimliği gönderilmezse tekrarlanan sayımlar engellenemez ve gelir verisi şişer.

## 5. Kritik Uygulama Kuralları

**Zamanlama.** Olay, ölçüm etiketi yüklenmeden önce diziye yazılmışsa kaybolmaz; ancak tek sayfa uygulamalarında sıralama dikkatle kurulmalıdır.

**Kalıcı kirlenme.** Aynı nesne üzerinde eski değerlerin kalması yanlış veri üretir. Ürün dizisi gibi alanlar her olaydan önce temizlenmelidir.

**Tek sayfa uygulamaları.** Sayfa yenilenmediği için rota değişimi manuel olarak sayfa görüntüleme olayına dönüştürülmelidir.

**Kişisel veri yasağı.** E-posta, telefon, ad, adres gibi bilgiler data layer'a ham hâlde yazılmaz. Gerekliyse yalnızca karma değer ve rıza koşuluna bağlı olarak iletilir.

**Veri tipi tutarlılığı.** Fiyat her zaman sayı, kimlik her zaman metin olarak gönderilir. Tip karışıklığı raporlarda sessiz hatalara yol açar.

## 6. Sunucu Tarafı Ölçüm

Tarayıcı kısıtlamalarının arttığı ortamda sunucu tarafı etiket yönetimi giderek önem kazanıyor. Sağladıkları: istemci tarafındaki script yükünün azalması, veri üzerinde daha fazla kontrol, hassas verinin tarayıcıya çıkmadan işlenmesi ve tanımlayıcı ömrünün iyileştirilmesi.

Data layer şeması iyi tasarlanmışsa, sunucu tarafına geçiş sitede yeniden yazım gerektirmez. Bu, iyi tasarımın en somut getirilerinden biridir.

## 7. Doğrulama ve İzleme

Kurulum sonrası yapılması gerekenler:

- etiket yöneticisinin önizleme modunda her olayın tetiklendiğinin ve doğru parametrelerle geldiğinin görülmesi,
- e-ticaret akışının uçtan uca test edilmesi,
- test verisinin üretim raporlarından filtrelenmesi,
- rıza reddi durumunda davranışın test edilmesi,
- şemayı belgeleyen bir dokümanın güncel tutulması.

Sürekli izleme için: kritik olayların hacminde ani düşüş uyarısı, zorunlu parametre boşluk oranı takibi ve yeni sürümlerden sonra ölçüm regresyon kontrolü.

## 8. Sürüm ve Değişiklik Yönetimi

Data layer bir arayüz sözleşmesidir; değiştirilirken dikkat gerekir:

- olay veya parametre adı değiştirileceğinde geçiş dönemi tanımlanır,
- kaldırılacak alanlar önce kullanımdan kaldırılmış olarak işaretlenir,
- etiket yöneticisi değişiklikleri sürüm notlarıyla kaydedilir,
- şema dokümantasyonu tek kaynak olarak korunur.

## Sık Sorulan Sorular

**Etiket yöneticisi olmadan data layer gerekir mi?** Ölçüm doğrudan kodla yapılıyorsa bile, olay şemasının merkezi ve belgelenmiş olması aynı faydayı sağlar.

**Mevcut sitede sonradan kurulabilir mi?** Kurulabilir. Doğru sıra: önce en kritik akış (satın alma veya form gönderimi), sonra kademeli genişletme.

**Şema ne sıklıkla gözden geçirilmeli?** Her önemli ürün değişikliğinde ve en az üç ayda bir. Ölçülmeyen bir işlev ve karşılığı olmayan bir olay birikmemelidir.
