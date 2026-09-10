---
title: "Reverse ETL Nedir? Ambardaki Veriyi Operasyona Taşımak"
description: "Reverse ETL nedir, ETL'den farkı nedir ve pazarlama operasyonuna nasıl bağlanır? Senkronizasyon stratejileri, idempotency, API sınırları ve gizlilik kuralları."
keywords: "Reverse ETL, veri ambarı senkronizasyonu, operasyonel analitik, CRM senkronizasyonu, data activation, idempotency, upsert"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Müşteri Verisi"
date: "2026-09-10"
lang: "tr"
og_title: "Reverse ETL Nedir?"
og_description: "Veri ambarındaki modellenmiş veriyi operasyonel sistemlere geri taşımanın kuralları."
og_type: "article"
twitter_card: "summary"
twitter_title: "Reverse ETL Nedir?"
twitter_description: "Ambardan CRM ve reklam platformlarına veri taşımanın mühendisliği."
og_image: "https://mehmetkuru.dev/blog-covers/reverse-etl.webp"
og_image_alt: "Reverse ETL Nedir? Ambardaki Veriyi Operasyona Taşımak"
---
Veri ambarında müşteri başına hesaplanmış bir "risk skoru" vardır. Satış ekibi bu skoru göremez, çünkü CRM'de böyle bir alan yoktur. Birisi her pazartesi ambardan bir tablo dışa aktarıp CRM'e elle yükler. İki hafta sonra yükleme unutulur, skorlar eskir ve kimse fark etmez. Reverse ETL, bu döngüyü otomatik, izlenebilir ve geri alınabilir hâle getiren katmandır.

## 1. Tanım ve Yön

Klasik ETL/ELT, kaynak sistemlerden veriyi ambara taşır. Reverse ETL ise ters yönde çalışır: ambarda modellenmiş veriyi, insanların gerçekten çalıştığı sistemlere geri yazar.

| Yön | Kaynak | Hedef | Amaç |
|---|---|---|---|
| ETL / ELT | Uygulama, reklam, ödeme sistemleri | Veri ambarı | Analiz ve raporlama |
| Reverse ETL | Veri ambarı | CRM, e-posta aracı, reklam platformu, destek sistemi | Karar ve aksiyon |

Fark yalnızca yön değildir. ETL'de hedef sizin kontrolünüzdedir; Reverse ETL'de hedef, kendi kuralları, alan sınırları ve hız limitleri olan bir üçüncü taraf sistemdir. Mühendislik zorluğu buradan gelir.

## 2. Tipik Senaryolar

- ambarda hesaplanan yaşam boyu değerin CRM'de müşteri kartında görünmesi,
- terk riski yüksek hesapların destek ekibine işaretlenmesi,
- ürün kullanım verisinin satış ekibine görünür olması,
- segmentlerin reklam platformlarına kitle olarak gönderilmesi,
- fatura ve ödeme durumunun müşteri iletişim aracına taşınması.

Ortak nokta: veri zaten vardır, eksik olan onun doğru yerde ve güncel olmasıdır.

## 3. Ön Koşul: Model Katmanı

Reverse ETL'in ham tablolar üzerine kurulması, en sık yapılan hatadır. Hedef sisteme yazılan her alanın tanımı net olmalıdır; aksi hâlde "aktif müşteri" alanı CRM'de bir şey, raporda başka bir şey ifade eder.

Doğru sıra: önce ambarda modellenmiş, tanımı yazılı, testleri olan bir katman; sonra o katmandan senkronizasyon. Bu katman aynı zamanda [metrik katmanının](/blog/marketing-metric-layer/) çıktısıdır.

## 4. Senkronizasyon Stratejileri

**Tam senkronizasyon:** Her çalışmada tüm kayıtlar gönderilir. Basittir, küçük veri kümelerinde uygundur, büyük tablolarda API kotasını hızla tüketir.

**Artımsal senkronizasyon:** Yalnızca değişen kayıtlar gönderilir. Bunun için kaynakta güvenilir bir değişiklik damgası (`updated_at`) veya karşılaştırma anahtarı gerekir. Damga güvenilir değilse artımsal senkronizasyon sessizce eksik çalışır — en tehlikeli hata biçimi budur.

**Olay tabanlı senkronizasyon:** Belirli bir olay gerçekleştiğinde tetiklenir. Tazelik en yüksek, karmaşıklık da en yüksektir.

Çoğu ekip için doğru başlangıç, güvenilir bir değişiklik damgası üzerine kurulmuş artımsal senkronizasyondur.

## 5. Idempotency ve Yeniden Çalıştırma

Senkronizasyon işleri başarısız olur: ağ kesilir, kota dolar, hedef sistem yavaşlar. Bu yüzden her iş, aynı veriyle iki kez çalıştırıldığında aynı sonucu üretmelidir.

Pratikte bu şu demektir:

- kayıtlar `insert` ile değil, dış anahtar üzerinden `upsert` ile yazılır,
- her kaydın hedef sistemdeki karşılığı kararlı bir kimlikle eşlenir,
- kısmen tamamlanmış bir çalışma, baştan çalıştırıldığında yinelenen kayıt üretmez,
- başarısız kayıtlar ayrı bir kuyruğa alınır, tüm iş durdurulmaz.

Idempotency sağlanmadan kurulan bir boru hattı, ilk ciddi hatada CRM'de binlerce yinelenen kayıt bırakır.

## 6. Hedef Sistem Sınırları

Üçüncü taraf sistemler tasarımınızı kısıtlar:

- saniye veya günlük istek limitleri,
- toplu yazma boyutu üst sınırı,
- özel alan sayısı sınırı,
- alan tipi kısıtları (metin/sayı/tarih dönüşümleri),
- bazı alanların salt okunur olması.

Bu sınırlar keşif aşamasında öğrenilmezse, tasarım tamamlandıktan sonra baştan yazılır. İlk gün yapılacak iş, hedef sistemin kotalarını ve alan şemasını yazılı hâle getirmektir.

## 7. İzleme

İzlenmeyen bir senkronizasyon, sessizce durur ve kimse fark etmez. En az şu dördü ölçülmelidir:

- son başarılı çalışma zamanı (tazelik),
- gönderilen, kabul edilen ve reddedilen kayıt sayısı,
- hata oranı ve hata tipleri,
- hedef sistemdeki kayıt sayısının kaynakla farkı.

Son madde en değerlisidir: sayı farkı büyüyorsa, hata vermeden çalışan ama eksik yazan bir iş vardır. Bu tür sessiz bozulmaları erken yakalamak için [veri kalitesi gözlemlenebilirliği](/blog/marketing-data-quality-observability/) ile birlikte kurulmalıdır.

## 8. Gizlilik ve Alan Seçimi

Ambarda olan her alanın hedef sisteme gitmesi gerekmez ve çoğu zaman gitmemelidir.

- yalnızca o sistemdeki iş için gerekli alanlar gönderilir,
- hassas veri kategorileri varsayılan olarak dışarıda bırakılır,
- rıza durumu her senkronizasyonda yeniden değerlendirilir,
- silme talepleri hedef sistemlere de yansıtılabilir olmalıdır,
- hangi alanın hangi sisteme gittiği kayıt altına alınır.

Son madde, [veri kökeni](/blog/data-lineage-impact-analysis/) çalışmasının bir parçasıdır ve silme talebi geldiğinde tek dayanağınızdır.

## 9. Ne Zaman Gerekmez?

- hedef sistem zaten kaynak sistemin kendisiyse,
- taşınacak veri gerçek zamanlı olmalıysa ve gecikme kabul edilemezse (o durumda olay akışı daha uygundur),
- tek seferlik bir aktarımsa,
- taşınacak alan sayısı bir elin parmaklarını geçmiyorsa ve hedef sistem doğrudan sorgu destekliyorsa.

Araç seçmeden önce sorulacak soru şudur: bu veri hedefte olmasa, hangi karar kötüleşir? Cevap net değilse senkronizasyon kurmaya gerek yoktur.

## Sık Sorulan Sorular

**Reverse ETL için özel bir araç şart mı?** Şart değil. Zamanlanmış işler ve hedef sistemin API'siyle yazılmış bir senkronizasyon katmanı çoğu ihtiyacı karşılar. Araç, hedef sayısı arttıkça ve hata yönetimi karmaşıklaştıkça değer katar.

**Ne sıklıkla çalıştırmalıyım?** Hedef alanın karar süresine göre. Satış ekibinin sabah gördüğü skor için günlük yeterlidir; sepet terk kitlesi için saatlik bile geç kalabilir.

**Hedef sistemde veri bozulursa ne olur?** Bu yüzden senkronizasyon tek yönlü olmalı ve hedefteki alan salt okunur kabul edilmelidir. İnsanların elle düzenlediği bir alana yazmak, her çalışmada değişikliklerin silinmesine yol açar.
