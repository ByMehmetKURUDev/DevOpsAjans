---
title: "Pazarlama Metrik Katmanı (Metric Layer) Nedir?"
description: "Metrik katmanı nedir ve neden gereklidir? Merkezi metrik tanımı, semantik katman mimarisi, sürüm yönetimi, tutarlı raporlama ve uygulama adımları."
keywords: "metrik katmanı, metric layer, semantik katman, merkezi metrik tanımı, tek gerçek kaynak, tutarlı raporlama"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Raporlama"
date: "2026-09-08"
lang: "tr"
og_title: "Pazarlama Metrik Katmanı"
og_description: "Merkezi metrik tanımıyla tutarlı raporlama kurmak."
og_type: "article"
twitter_card: "summary"
twitter_title: "Pazarlama Metrik Katmanı"
twitter_description: "Semantik katman ve merkezi metrik yönetimi."
---
Aynı şirkette üç farklı rapor, aynı ay için üç farklı "dönüşüm sayısı" gösteriyorsa sorun veri kalitesi değil, metrik tanımının merkezi olmayışıdır. Metrik katmanı, bu tanımları tek bir yerde tutan ve tüm raporlama araçlarının aynı hesaplamayı kullanmasını sağlayan mimari katmandır.

## 1. Sorun: Dağılmış Tanımlar

Metrik katmanı olmadan hesaplama mantığı şu yerlere dağılır:

- her pano aracının içinde ayrı formüller,
- her analistin kendi sorgusunda,
- her sunum için elle hazırlanan tablolarda,
- kampanya raporlarında platform varsayılanlarıyla.

Sonuç: "Yeni müşteri" bir raporda ilk siparişi veren kişi, diğerinde ilk kez sitede görülen kullanıcı, üçüncüsünde CRM'de yeni açılan kayıt anlamına gelir. Toplantı, verinin doğruluğunu tartışmakla geçer; karar alınamaz.

## 2. Metrik Katmanının Tanımı

Veri ambarı ile raporlama araçları arasında duran, iş metriklerini tek bir yerde tanımlayan katmandır. Her metrik için tuttukları:

- adı ve iş tanımı,
- hesaplama mantığı,
- kullanılan kaynak tablolar,
- hangi boyutlarla kırılabileceği,
- hangi filtrelerin varsayılan olarak uygulandığı,
- sahibi ve güncelleme geçmişi.

Raporlama araçları formülü kendileri kurmaz; katmandan metriği çağırır.

## 3. Sağladıkları

**Tutarlılık.** Her araç aynı sayıyı üretir.

**Bakım kolaylığı.** Tanım değişikliği tek yerde yapılır, tüm raporlara yansır.

**Şeffaflık.** Metriğin nasıl hesaplandığı görünürdür; tartışma tanım üzerinde yürür, sayı üzerinde değil.

**Yeniden kullanım.** Yeni bir pano kurmak, formülleri yeniden yazmayı gerektirmez.

**Denetlenebilirlik.** Bir sayının nereden geldiği izlenebilir.

## 4. Pazarlama İçin Temel Metrik Kümesi

| Metrik | Tanımda netleşmesi gereken |
|---|---|
| Pazarlama gideri | Yalnızca medya mı, araç ve ücret dahil mi |
| Dönüşüm | Hangi olay, hangi ilişkilendirme, hangi pencere |
| Gelir | Brüt mü net mi, KDV ve kargo dahil mi, iadeler düşülüyor mu |
| Yeni müşteri | Hangi sistemde, hangi kriterle |
| CAC | Hangi giderler bölünüyor, hangi müşteri sayılıyor |
| ROAS / POAS | Gelir mi brüt kâr mı esas alınıyor |
| LTV | Hangi zaman penceresi, hangi kâr tanımı |
| Elde tutma | Hangi periyot, hangi aktiflik tanımı |

Bu tanımların yazılı ve merkezi olması, çoğu şirkette raporlama kalitesini araç değiştirmekten daha fazla iyileştirir.

## 5. Boyutlar ve Kırılımlar

Metriklerin yanında boyutlar da merkezi tanımlanmalıdır: kanal, kampanya, ürün kategorisi, müşteri segmenti, coğrafya, cihaz, yeni/mevcut müşteri.

**Kanal tanımı özellikle kritiktir.** Kampanya isimlendirme ve UTM standardı olmadan kanal kırılımı güvenilmez olur. Bu nedenle metrik katmanı çalışması genellikle isimlendirme standardının yazılmasıyla başlar.

## 6. Uygulama Yaklaşımı

Metrik katmanı için üç yaygın yol:

**Dönüşüm katmanında modelleme.** Veri ambarında iş mantığını içeren temiz model tabloları oluşturulur, raporlar yalnızca bu tabloları okur. Basit ve dayanıklıdır.

**Özel semantik katman aracı.** Metrikler bildirimsel olarak tanımlanır, araçlar API üzerinden çağırır. Ölçek büyüdüğünde güçlüdür.

**Raporlama aracının dahili semantik modeli.** Hızlı başlangıç sağlar, ancak birden fazla araç kullanıldığında tutarlılığı korumaz.

Pratik öneri: veri ambarında iyi modellenmiş bir katmanla başlamak, ihtiyaç büyüdüğünde bildirimsel araca geçmek.

## 7. Sürüm ve Değişiklik Yönetimi

Metrik tanımı değiştiğinde geçmiş raporlar da değişir. Bu nedenle:

- her değişiklik sürüm notuyla kaydedilir,
- etkilenen panolar ve paydaşlar önceden bilgilendirilir,
- geriye dönük etki değerlendirilir ve gerekiyorsa yeniden hesaplanır,
- büyük tanım değişikliklerinde eski metrik bir süre paralel yayınlanır,
- her metriğin bir sahibi olur.

Tanım değişikliğini sessizce yapmak, güveni en hızlı yıkan uygulamadır.

## 8. Kalite Kontrolü

- kaynak sistem toplamlarıyla mutabakat testleri,
- beklenen aralık dışı değerler için uyarı,
- yinelenen kayıt ve eksik birleştirme kontrolleri,
- zaman dilimi ve dönem sınırı testleri,
- yeni veri kaynağı eklendiğinde regresyon karşılaştırması.

## 9. Uygulama Sırası

1. en çok tartışılan 8-10 metriği listelemek,
2. her biri için tek bir tanım üzerinde uzlaşmak ve yazmak,
3. kampanya isimlendirme ve UTM standardını sabitlemek,
4. veri ambarında model tablolarını kurmak,
5. metrikleri merkezi katmanda tanımlamak,
6. panoları bu katmana geçirmek,
7. eski elle hazırlanan raporları kapatmak,
8. kalite testlerini ve uyarıları kurmak.

En kritik adım ikincisidir ve teknik değildir: uzlaşma sağlanmadan kurulan katman, yalnızca tartışmanın yerini değiştirir.

## Sık Sorulan Sorular

**Küçük ekipler için gerekli mi?** Rapor sayısı arttıkça gereklidir. Küçük ekipte bile yazılı bir metrik sözlüğü büyük fark yaratır.

**Platform raporlarıyla farklar kalkar mı?** Hayır. Reklam platformları kendi ilişkilendirme modelleriyle raporlar. Metrik katmanı, şirket içi karar metriğinin tek olmasını sağlar; platform raporları teşhis amacıyla ayrı okunur.

**Kim sahiplenmeli?** Tanımın sahibi iş tarafı, uygulamanın sahibi veri tarafı olmalıdır. Tek taraflı sahiplik her iki yönde de başarısızlık üretir.
