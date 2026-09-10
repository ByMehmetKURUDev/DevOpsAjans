---
title: "Pazarlama Analitiği Panosu Nasıl Kurulur?"
description: "Pazarlama analitiği panosu tasarımı: hedef kitleye göre katmanlı raporlama, doğru metrik seçimi, veri kaynağı birleştirme, güncellik yönetimi ve karar odaklı görselleştirme."
keywords: "pazarlama analitiği panosu, dashboard tasarımı, KPI seçimi, raporlama katmanları, veri görselleştirme, kanal performansı"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Raporlama"
  - "Pazarlama"
date: "2026-09-07"
lang: "tr"
og_title: "Pazarlama Analitiği Panosu"
og_description: "Karar üreten pazarlama panoları nasıl tasarlanır?"
og_type: "article"
twitter_card: "summary"
twitter_title: "Pazarlama Analitiği Panosu"
twitter_description: "Katmanlı raporlama ve doğru metrik seçimi."
og_image: "https://mehmetkuru.dev/blog-covers/marketing-analytics-dashboard.webp"
og_image_alt: "Pazarlama Analitiği Panosu Nasıl Kurulur?"
---
Çoğu pazarlama panosu bakılmayı bırakır. Nedeni veri eksikliği değil, panonun bir karar sorusuna bağlanmamış olmasıdır. Ekranda otuz metrik varsa hiçbiri önemli değildir. İyi bir pano, "şimdi ne yapmalıyım" sorusunu yanıtlar.

## 1. Tasarımın Başlangıcı: Karar Sorusu

Grafik seçmeden önce yanıtlanması gerekenler:

- bu panoyu kim, hangi sıklıkta açacak,
- açtığında hangi kararı verecek,
- hangi eşik aşıldığında müdahale edecek,
- hangi veri olmadan karar veremez.

Karar sorusu yoksa pano bir veri sergisidir. Her metriğin yanında "bu sayı değişirse ne yaparım" cevabı olmalıdır.

## 2. Katmanlı Yapı

Tek bir pano tüm ihtiyaçları karşılamaz. Üç katman ayrılmalıdır:

**Yönetici katmanı.** Aylık/haftalık, 5-7 metrik: toplam gelir, pazarlama gideri, müşteri edinme maliyeti, LTV/CAC, kanal bazlı katkı, hedefe göre sapma. Amaç: durum ve trend.

**Kanal yönetimi katmanı.** Haftalık/günlük: kanal bazlı harcama, dönüşüm, EBM, ROAS/POAS, gösterim payı, dönüşüm oranı. Amaç: bütçe dağıtımı ve optimizasyon.

**Teşhis katmanı.** Gerektiğinde: kampanya/reklam grubu/anahtar kelime kırılımı, açılış sayfası performansı, huni adım kayıpları, cihaz ve coğrafya detayı. Amaç: sorunun nerede olduğunu bulmak.

Katmanlar arasında geçiş (özetten detaya) mümkün olmalıdır.

## 3. Metrik Seçimi

| Katman | Öncelikli metrikler |
|---|---|
| Yönetici | Gelir, brüt kâr, pazarlama gideri, CAC, LTV/CAC, geri ödeme süresi |
| Kanal | Harcama, dönüşüm, EBM, POAS, dönüşüm oranı, trafik kalitesi |
| Teşhis | Huni adım oranları, açılış sayfası dönüşümü, arama terimi verimi |

**Kaçınılması gerekenler:** yalnızca gösterim ve tıklama gösteren panolar, bağlamsız yüzdeler, hedefsiz mutlak sayılar ve karar üretmeyen "ilginç" kırılımlar.

Her metrik yanında bulunması gerekenler: karşılaştırma tabanı (önceki dönem veya hedef), değişim yönü ve anlamlılık işareti.

## 4. Veri Kaynaklarının Birleştirilmesi

Pazarlama verisi doğal olarak dağınıktır: reklam platformları, web analitiği, CRM, sipariş sistemi, e-posta aracı.

Birleştirme için gerekenler:

- ortak zaman tanımı (aynı saat dilimi, aynı hafta başlangıcı),
- ortak kampanya isimlendirme standardı (UTM disiplini),
- ortak müşteri/sipariş kimliği,
- para birimi ve vergi tanımlarının tutarlılığı,
- yeni/mevcut müşteri ayrımının tek bir yerde tanımlanması.

Bu standartlar olmadan yapılan birleştirme, birbirini doğrulamayan sayılar üretir ve panoya güven kaybolur.

## 5. Tanım Sözlüğü

Panonun en çok ihmal edilen parçasıdır. Her metriğin yanında erişilebilir bir tanım bulunmalıdır: nasıl hesaplanıyor, hangi kaynaktan geliyor, neyi dışlıyor, hangi ilişkilendirme modeliyle ölçülüyor.

"Dönüşüm" kelimesinin farklı ekiplerde farklı anlama gelmesi, pazarlama raporlamasında en yaygın güven kaybı nedenidir.

## 6. Güncellik ve Güvenilirlik

Kullanıcı, verinin ne kadar güncel olduğunu görmek zorundadır:

- son güncelleme zaman damgası,
- eksik veya gecikmiş kaynak uyarısı,
- kısmi gün verisinin açıkça işaretlenmesi,
- ilişkilendirme gecikmesi olan metriklerde uyarı notu.

Kısmi günü tam gün gibi göstermek, her sabah yanlış alarm üretir ve panonun terk edilmesine yol açar.

## 7. Görselleştirme İlkeleri

- trend için çizgi, karşılaştırma için yatay çubuk, kompozisyon için yığılmış alan,
- pasta grafikten kaçınmak (üçten fazla dilimde okunmaz),
- renk anlamlı kullanılmalı (iyi/kötü, kanal kimliği), dekoratif olmamalı,
- eksen sıfırdan başlamalı; kesilmiş eksen değişimi abartır,
- huni ve kohort görünümleri kayıp noktalarını görünür kılar,
- ekranda en fazla 6-8 görsel bileşen bulunmalı.

Erişilebilirlik de tasarımın parçasıdır: yalnızca renkle ayrım yapmamak, yeterli kontrast kullanmak ve tabloları metin olarak okunabilir tutmak.

## 8. Uyarı ve Otomasyon

Pano izlemeyi kolaylaştırır ama sürekli bakılmasını gerektirmemelidir. Kritik değişiklikler otomatik bildirilmelidir:

- harcamanın beklenen aralığın dışına çıkması,
- dönüşüm hacminde ani düşüş (ölçüm bozulmasının ilk sinyali),
- EBM'nin hedef eşiği aşması,
- kritik kampanyanın bütçe sınırına takılması,
- veri kaynağının güncellenmemesi.

## 9. Bakım

Panolar zamanla bozulur: kampanya yapısı değişir, yeni kanal eklenir, metrik tanımı güncellenir. Sürdürülebilirlik için:

- her çeyrekte kullanılmayan görsellerin kaldırılması,
- tanım sözlüğünün güncel tutulması,
- kaynak şeması değişikliklerinin panoya yansıtılması,
- panonun gerçekten kararlara girdiğinin kullanıcılarla doğrulanması.

## Sık Sorulan Sorular

**Hangi araçla kurulmalı?** Araç ikincildir. Veri modeli ve tanım disiplini doğruysa çoğu görselleştirme aracı yeterlidir.

**Gerçek zamanlı olmalı mı?** Pazarlama kararlarının çoğu günlük/haftalık ritimde alınır. Gerçek zamanlı ihtiyaç genellikle lansman ve kampanya günleriyle sınırlıdır.

**Kaç pano olmalı?** Hedef kitle sayısı kadar. Tek bir "her şeyi gösteren" pano yerine, üç net amaçlı pano her zaman daha çok kullanılır.
