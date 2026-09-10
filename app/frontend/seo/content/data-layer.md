---
title: "Data Layer Nedir? Web Ölçümünün Temel Katmanı"
description: "Data layer nedir, nasıl çalışır ve neden ölçümün temelidir? Veri katmanı mimarisi, olay sözleşmesi, sürüm yönetimi, kalite kontrolü ve yaygın hatalar."
keywords: "data layer nedir, veri katmanı, olay sözleşmesi, ölçüm mimarisi, dataLayer push, ölçüm kalitesi"
category: "Reklam"
tags:
  - "Reklam"
  - "Ölçüm"
  - "Veri Mimarisi"
date: "2026-09-06"
lang: "tr"
og_title: "Data Layer Nedir?"
og_description: "Web ölçümünün temel katmanı olarak veri katmanı mimarisi."
og_type: "article"
twitter_card: "summary"
twitter_title: "Data Layer Nedir?"
twitter_description: "Veri katmanı mimarisi ve olay sözleşmesi."
og_image: "https://mehmetkuru.dev/blog-covers/data-layer.webp"
og_image_alt: "Data Layer Nedir? Web Ölçümünün Temel Katmanı"
---
Ölçüm sorunlarının büyük bölümü araç seçiminden değil, veri katmanının olmayışından kaynaklanır. Data layer, sitenin ne olduğunu ölçüm araçlarına anlatan ortak dildir. Bu katman yoksa her ölçüm ihtiyacı ayrı bir el işi, her arayüz değişikliği potansiyel bir veri kaybıdır.

## 1. Sorunun Kaynağı

Veri katmanı olmadan ölçüm iki yolla yapılır:

**CSS seçicilere bağlanmak.** "Şu sınıfa sahip butona tıklandığında dönüşüm say." Bu yaklaşım tasarım değişikliğinde sessizce bozulur. Hata mesajı üretmez; veri sadece durur.

**Her araç için ayrı kod yazmak.** Analitik için bir çağrı, reklam platformu için başka bir çağrı, ısı haritası için üçüncü bir çağrı. Zamanla birbiriyle çelişen tanımlar oluşur.

Data layer bu iki sorunu da ortadan kaldırır: site bir kez "ne olduğunu" bildirir, araçlar bunu okur.

## 2. Katmanın Rolü

Data layer bir arayüz sözleşmesidir:

- **Site tarafı** olayın gerçekleştiğini ve bağlamını bildirmekle sorumludur,
- **Etiket yönetimi tarafı** bu bilgiyi hangi araca nasıl göndereceğine karar verir,
- iki taraf birbirinden bağımsız değişebilir.

Bu ayrım, ölçüm ihtiyaçlarının geliştirme döngüsünü beklemeden karşılanmasını sağlar. Yeni bir reklam platformu eklendiğinde site kodu değişmez.

## 3. Bir Olayın Anatomisi

Her olay iki parçadan oluşur:

**Olay adı.** Ne olduğunu bildirir. Standart, öngörülebilir ve değişmez olmalıdır.

**Bağlam parametreleri.** Olayın hangi koşulda gerçekleştiğini anlatır: hangi ürün, hangi tutar, hangi kategori, hangi adım, hangi kullanıcı segmenti.

İyi tasarlanmış bir olay, tek başına okunduğunda iş sorusunu yanıtlar. "Sepete ekleme oldu" yetersizdir; "hangi ürün, hangi fiyatla, hangi listeden, hangi adette sepete eklendi" karar üretir.

## 4. Şema Disiplini

Veri katmanının değeri tutarlılığından gelir. Gerekli kurallar:

- tek bir isimlendirme kuralı (küçük harf, alt çizgi),
- aynı anlam için tek bir alan adı,
- her alan için sabit veri tipi (fiyat sayı, kimlik metin),
- zorunlu ve isteğe bağlı alanların belgelenmesi,
- standart adların (sektör/araç önerileri) tercih edilmesi,
- yeni alan eklenmeden önce mevcut şemanın kontrolü.

Şema dokümanı tek gerçek kaynak olarak tutulmalı ve kod ile birlikte güncellenmelidir.

## 5. Kritik Teknik Konular

**Zamanlama.** Olay bilgisi, etiket yönetimi yüklenmeden önce yazılırsa kaybolmaz; dizi yapısı bu gecikmeyi tolere eder. Ancak tek sayfa uygulamalarında rota değişimi ve veri hazır olma sırası açıkça yönetilmelidir.

**Durum kirlenmesi.** Aynı nesne üzerinde önceki olayın verisi kalırsa yanlış rapor üretir. Dizi/nesne alanları her olaydan önce temizlenmelidir.

**Tek sayfa uygulamaları.** Sayfa yenilenmediği için sayfa görüntüleme olayı elle tetiklenir; aksi halde tüm ziyaret tek sayfa görüntülemesi olarak görünür.

**Kişisel veri.** E-posta, telefon, ad, adres ham hâlde veri katmanına yazılmaz. Gerekliyse karma değer ve rıza koşuluna bağlı olarak iletilir.

**Sunucu tarafı ölçüm.** İyi tasarlanmış bir şema, ölçümün sunucu tarafına taşınmasını sitede yeniden yazım gerektirmeden mümkün kılar.

## 6. Kalite Kontrolü

Veri katmanı, yazılım gibi test edilmelidir:

- her olayın önizleme modunda doğru parametrelerle geldiği doğrulanır,
- kritik akış (satın alma, form gönderimi) uçtan uca test edilir,
- zorunlu alanların boş gelme oranı izlenir,
- kritik olay hacminde ani düşüş için uyarı kurulur,
- her sürüm sonrası ölçüm regresyon kontrolü yapılır,
- test verisi üretim raporlarından filtrelenir.

Ölçümün sessizce bozulması, hiç ölçmemekten daha maliyetlidir; çünkü yanlış veriye dayanarak karar alınır.

## 7. Sürüm ve Değişiklik Yönetimi

Şema bir sözleşme olduğu için değişiklikleri planlı yapılır:

- ad değişikliğinde eski ve yeni alan bir süre birlikte gönderilir,
- kaldırılacak alanlar önce kullanımdan kaldırılmış olarak işaretlenir,
- etiket yönetimi değişiklikleri sürüm notlarıyla kaydedilir,
- bozucu değişiklikler analitik ve reklam tarafına önceden bildirilir.

## 8. Uygulama Yol Haritası

Sıfırdan kuruyorsanız önerilen sıra:

1. ölçüm planı: hangi iş soruları yanıtlanacak,
2. şema tasarımı: olaylar, parametreler, tipler,
3. en kritik akışın uygulanması (satın alma veya müşteri adayı formu),
4. doğrulama ve üretime alma,
5. kademeli genişletme (liste görüntüleme, sepet, kayıt, etkileşim),
6. izleme ve uyarı kurulumu,
7. dokümantasyonun canlı tutulması.

## 9. Sık Yapılan Hatalar

- ölçüm planı olmadan doğrudan koda başlamak,
- her yeni ihtiyaçta yeni ve benzersiz olay adı üretmek,
- veri tiplerini karışık göndermek,
- kişisel veriyi katmana yazmak,
- test ortamını üretim ölçümünden ayırmamak,
- dokümantasyonu bir kez yazıp güncellememek,
- olayların çalıştığını yalnızca kurulum gününde doğrulamak.

## Sık Sorulan Sorular

**Küçük bir site için gerekli mi?** Yalnızca sayfa görüntüleme ölçen bir site için gereksiz görünür; ancak form gönderimi veya satış varsa ilk günden kurulması sonraki tüm işleri kolaylaştırır.

**Hangi araçlarla kullanılır?** Etiket yönetimi araçlarıyla en verimli çalışır, ancak katman kavramı araçtan bağımsızdır: merkezi ve belgelenmiş bir olay şeması her durumda değer üretir.

**Mevcut sitede sonradan eklenebilir mi?** Eklenebilir. En kritik akıştan başlayıp kademeli genişletmek, riski en düşük yaklaşımdır.
