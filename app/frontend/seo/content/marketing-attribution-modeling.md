---
title: "Pazarlama İlişkilendirme Modelleme (Attribution Modeling)"
description: "Pazarlama ilişkilendirme modelleri nasıl çalışır? Son tıklama, ilk tıklama, doğrusal, zaman azalmalı ve veri odaklı modeller; sınırları, seçim kriterleri ve artımsallıkla ilişkisi."
keywords: "ilişkilendirme modelleme, attribution model, son tıklama, veri odaklı ilişkilendirme, çok kanallı ölçüm, dönüşüm yolu analizi"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Ölçüm"
  - "Pazarlama"
date: "2026-09-13"
lang: "tr"
og_title: "Pazarlama İlişkilendirme Modelleme"
og_description: "İlişkilendirme modellerinin çalışma mantığı ve sınırları."
og_type: "article"
twitter_card: "summary"
twitter_title: "İlişkilendirme Modelleme"
twitter_description: "Kanal katkısını doğru okumanın yöntemleri."
---
Bir müşteri satın almadan önce ortalama olarak birden fazla temas noktasından geçer: bir sosyal medya gönderisi görür, bir arama sonucuna tıklar, e-posta alır, günler sonra marka adıyla arayıp satın alır. İlişkilendirme, bu satıştaki katkının kanallar arasında nasıl paylaştırılacağı sorusudur.

## 1. Sorunun Doğası

İlişkilendirme, matematiksel olarak kesin çözümü olmayan bir sorudur. Hiçbir model "gerçek katkıyı" ölçmez; her model bir varsayım seti uygular. Bu nedenle doğru soru "hangi model doğru" değil, "hangi model hangi karar için yararlı" olmalıdır.

## 2. Kural Tabanlı Modeller

**Son tıklama.** Tüm katkı son temasa verilir. Basit ve yaygındır; ancak keşif ve değerlendirme aşamasındaki kanalları sistematik olarak değersizleştirir. Marka aramalarını abartır.

**İlk tıklama.** Tüm katkı ilk temasa verilir. Keşif kanallarını öne çıkarır, ancak kapanışı sağlayan çabayı görmezden gelir.

**Doğrusal.** Katkı tüm temaslara eşit dağıtılır. Adil görünür ama gerçekte temasların etkisi eşit değildir.

**Zaman azalmalı.** Dönüşüme yakın temaslar daha fazla katkı alır. Kısa satın alma döngülerinde makul çalışır.

**Konum tabanlı.** İlk ve son temasa ağırlık verir, aradakileri paylaştırır. Hem keşfi hem kapanışı tanır.

## 3. Veri Odaklı Modeller

Gerçek dönüşüm yollarını istatistiksel olarak inceleyerek her temasın katkısını hesaplar. Dönüşen ve dönüşmeyen yolları karşılaştırarak hangi temasın olasılığı gerçekten artırdığını tahmin eder.

**Güçlü yönü:** Kural yerine veriye dayanır, kanal ağırlıklarını otomatik günceller.
**Sınırı:** Yeterli veri hacmi gerektirir, kara kutu etkisi yaratır, yalnızca ölçülebilen temasları görür.

## 4. Modellerin Ortak Kör Noktası

Hiçbir tıklama tabanlı model şunları göremez:

- reklamı gören ama tıklamayan kullanıcının etkisi,
- çevrimdışı temaslar (mağaza, tavsiye, açık hava),
- farklı cihazlar arası kopan yollar,
- rıza reddi nedeniyle ölçülemeyen ziyaretler,
- uzun vadeli marka etkisi,
- doğal talebin (hiç reklam olmasa da gelecek olan satış) payı.

Son madde en önemlisidir: ilişkilendirme, bir kanalın **artımsal** katkısını değil, ölçülen yolda görünürlüğünü ölçer. Marka aramaları bu nedenle her modelde yüksek performanslı görünür.

## 5. Artımsallıkla İlişkisi

İlişkilendirme "bu satış hangi yolda gerçekleşti" sorusunu yanıtlar. İş kararının gerçek sorusu ise farklıdır: "bu harcamayı kesersem ne kaybederim?"

Bu sorunun yanıtı ancak deneyle alınır: coğrafi bölme testleri, kitle bölme testleri, kanal duraklatma testleri. İlişkilendirme günlük optimizasyon için yön verir; bütçe tahsisi kararı deneyle doğrulanmalıdır.

Olgun ölçüm yapısı üç bileşeni birlikte kullanır: ilişkilendirme (günlük yön), artımsallık deneyleri (gerçek katkı), medya karması modellemesi (üst düzey bütçe dağıtımı).

## 6. Model Seçimi

| Karar | Uygun yaklaşım |
|---|---|
| Kampanya içi optimizasyon | Veri odaklı veya zaman azalmalı |
| Kanal bütçesi dağıtımı | Artımsallık testi + medya karması |
| Yeni kanal değerlendirmesi | Kontrollü deney |
| Huni üstü içerik değeri | İlk tıklama / yardımlı dönüşüm analizi |
| Yönetici raporlaması | Tek ve tutarlı model + not olarak sınırları |

**En önemli kural:** Model seçildikten sonra tutarlı kullanılmalıdır. Model değiştirmek geçmiş raporları da değiştirir; bu, güven kaybının en hızlı yoludur.

## 7. Dönüşüm Penceresi

Model kadar önemli bir parametredir. Satın alma döngüsü uzun olan işlerde kısa pencere, üst huni kanallarının katkısını yok sayar. Çok uzun pencere ise ilgisiz temasları katkı olarak sayar.

Pencere, gerçek satın alma döngüsü verisine bakılarak seçilmelidir: dönüşümlerin büyük bölümü ilk temastan kaç gün sonra gerçekleşiyor?

## 8. Veri Altyapısı Gereksinimleri

- tutarlı UTM ve kampanya isimlendirme standardı,
- kimlik çözümlemesiyle cihazlar arası yolların birleştirilmesi,
- çevrimdışı satışların geri beslenmesi,
- yeni/mevcut müşteri ayrımı,
- ham olay verisine erişim (kendi modelinizi kurmak için),
- rıza durumunun ölçüme yansıtılması.

Bu altyapı olmadan yapılan ilişkilendirme analizi, hangi model kullanılırsa kullanılsın güvenilmezdir.

## 9. Raporlama İlkeleri

- kullanılan model ve pencere her raporda belirtilir,
- marka ve jenerik trafik ayrı raporlanır,
- yeni müşteri kazanımı ayrı gösterilir,
- yardımlı dönüşümler ayrı bir görünüm olarak sunulur,
- platform raporlarıyla farkların nedeni açıklanır,
- model değişikliği sürüm notuyla duyurulur.

## 10. Sık Yapılan Hatalar

- son tıklama modeliyle üst huni kanallarını kapatmak,
- platform raporlarını toplayıp kanal katkılarını üst üste saymak,
- model değiştirip performans iyileşmesi gibi raporlamak,
- artımsallık testi yapmadan bütçe kesmek,
- marka aramalarının yüksek getirisini performans başarısı saymak,
- dönüşüm penceresini varsayılanda bırakmak.

## Sık Sorulan Sorular

**Platformlar neden farklı sayılar gösteriyor?** Her platform kendi ilişkilendirme modelini ve penceresini kullanır ve yalnızca kendi temasını görür. Toplamları üst üste eklemek, gerçek dönüşüm sayısının çok üzerinde bir sonuç verir.

**Hangi model en iyisi?** Karar bağlamına bağlıdır. Yeterli veri varsa veri odaklı model günlük optimizasyon için en pratiktir; stratejik kararlar deneyle desteklenmelidir.

**Küçük ölçekte ne yapılmalı?** Karmaşık model kurmak yerine tek bir tutarlı model kullanıp, kanal kararlarını basit duraklatma testleriyle doğrulamak daha yüksek getiri sağlar.
