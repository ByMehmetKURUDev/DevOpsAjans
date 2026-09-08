---
title: "CRM ve Google Ads Çevrimdışı Dönüşüm Entegrasyonu"
description: "CRM verisiyle Google Ads çevrimdışı dönüşüm yükleme: GCLID yakalama, satış aşaması eşleme, gerçek gelir geri besleme, teklif optimizasyonu ve doğrulama adımları."
keywords: "çevrimdışı dönüşüm, offline conversion, GCLID, CRM entegrasyonu, gerçek gelir yükleme, müşteri adayı kalitesi, teklif optimizasyonu"
category: "Reklam"
tags:
  - "Reklam"
  - "Ölçüm"
  - "CRM"
date: "2026-09-05"
lang: "tr"
og_title: "CRM ve Çevrimdışı Dönüşüm Entegrasyonu"
og_description: "Gerçek satış verisini reklam optimizasyonuna geri beslemek."
og_type: "article"
twitter_card: "summary"
twitter_title: "Çevrimdışı Dönüşüm Entegrasyonu"
twitter_description: "CRM satış verisiyle Google Ads optimizasyonu."
---

# CRM ve Google Ads Çevrimdışı Dönüşüm Entegrasyonu

Satışın telefonla, saha görüşmesiyle veya uzun bir teklif süreciyle tamamlandığı işlerde, web üzerindeki form gönderimi gerçek sonucu temsil etmez. Reklam algoritması "form dolduran" profili öğrenir; oysa iş hedefi "sözleşme imzalayan" profildir. Çevrimdışı dönüşüm entegrasyonu bu boşluğu kapatır.

## 1. Neden Gerekli?

Tipik bir hizmet işletmesinde form gönderimlerinin dağılımı şöyledir: bir bölümü hiç ulaşılamayan, bir bölümü bütçesi uymayan, bir bölümü hedef dışı segment ve küçük bir bölümü gerçek müşteri.

Tüm form gönderimlerini eşit değerde dönüşüm olarak raporlarsanız:

- otomatik teklif, en çok form getiren ama en az satış üreten kanallara yönelir,
- düşük nitelikli trafiği getiren anahtar kelimeler "başarılı" görünür,
- gerçekten kârlı segmentler yeterli bütçe almaz,
- EBM iyi görünürken CAC kötüleşir.

Çevrimdışı dönüşüm yüklemesi, algoritmaya gerçek sonucu öğretir. Müşteri adayı odaklı işlerde en yüksek etkili optimizasyon budur.

## 2. Akışın Yapısı

**Adım 1 — Tıklama kimliğini yakalamak.** Kullanıcı reklama tıkladığında adres satırına eklenen tıklama kimliği (GCLID), form gönderiminde gizli alan olarak toplanır.

**Adım 2 — CRM'e yazmak.** Bu kimlik, müşteri adayı kaydıyla birlikte CRM'de saklanır. Kaydın yanına kaynak, kampanya ve ilk temas zamanı da yazılır.

**Adım 3 — Satış sürecini izlemek.** Aday nitelendirilir, teklif verilir, kazanılır veya kaybedilir. Her aşama değişikliği zaman damgasıyla kaydedilir.

**Adım 4 — Sonucu geri yüklemek.** Kazanılan satışlar, tıklama kimliği, dönüşüm adı, dönüşüm zamanı ve gerçek gelirle birlikte reklam platformuna yüklenir.

**Adım 5 — Optimizasyonu bu sinyale bağlamak.** Teklif stratejisi, form gönderimi yerine nitelikli aday veya kazanılmış satış dönüşümünü hedefler.

## 3. Aşama Eşlemesi

Tek bir dönüşüm yeterli değildir; satış hunisi aşamaları ayrı dönüşüm eylemleri olarak tanımlanır:

| CRM aşaması | Dönüşüm eylemi | Kullanım |
|---|---|---|
| Form gönderildi | Ham müşteri adayı | Gözlem (ikincil) |
| İletişim kuruldu | Ulaşılabilir aday | Gözlem |
| Nitelikli | Nitelikli aday | Teklife dahil edilebilir |
| Teklif verildi | Fırsat | Gözlem |
| Kazanıldı | Satış + gerçek gelir | Birincil optimizasyon hedefi |

**Pratik denge:** Satış döngüsü çok uzunsa (3 aydan fazla), "kazanıldı" sinyali algoritmanın öğrenmesi için fazla gecikir. Bu durumda "nitelikli aday" birincil hedef yapılır ve kazanılmış satış değerle birlikte gözlem amacıyla yüklenir.

## 4. Veri Hacmi Şartı

Otomatik teklif stratejilerinin öğrenmesi için yeterli dönüşüm hacmi gerekir. Aylık kazanılmış satış sayısı çok düşükse (örneğin 10'un altında) doğrudan satış hedefi optimizasyonu istikrarsız olur.

Bu durumda yapılabilecekler: nitelikli aday aşamasını hedeflemek, aşamalara farklı değerler atayarak değer tabanlı optimizasyon kurmak veya daha uzun dönüşüm pencereleri kullanmak.

## 5. Değer Atama Stratejisi

Her adayı aynı değerde saymak, ölçümün en büyük eksiğidir. Değer farklılaştırma yöntemleri:

- talep büyüklüğüne göre (küçük/orta/kurumsal proje),
- hizmet hattına göre (marj farkı),
- coğrafyaya göre (hizmet maliyeti farkı),
- tarihsel kapanış oranıyla ağırlıklandırma: aşama değeri = ortalama satış kârı × o aşamadan kazanma olasılığı.

Son yöntem, kısa vadeli sinyal ile gerçek kârlılığı dengeleyen en pratik yaklaşımdır.

## 6. Teknik Uygulama Notları

- tıklama kimliği tarayıcı oturumu boyunca saklanmalı (birden çok sayfa gezildiğinde kaybolmamalı),
- kimliğin geçerlilik süresi vardır; yükleme bu pencere içinde yapılmalıdır,
- yükleme düzenli ve otomatik olmalı (günlük veya birkaç günde bir),
- zaman damgası doğru saat dilimiyle gönderilmelidir,
- yinelenen yükleme kontrolü yapılmalı,
- iade ve iptal durumunda düzeltme (negatif ayarlama) süreci tanımlanmalı,
- kimlik yakalanamayan adaylar için ayrı raporlama tutulmalı.

## 7. Gizlilik ve Uyum

- yalnızca gerekli veri gönderilir; ham kişisel veri paylaşılmaz,
- iletişim bilgisi tabanlı eşleme kullanılacaksa karma değer kullanılır,
- gizlilik bildirimi ve rıza metni bu veri akışını kapsayacak biçimde güncellenir,
- veri saklama ve silme talepleri süreci CRM tarafında tanımlanır,
- veri işleme sözleşmeleri gözden geçirilir.

## 8. Doğrulama

Entegrasyon çalışıyor demek için:

- test bir adayın uçtan uca akışı izlenir,
- yükleme raporunda başarılı/başarısız kayıt sayıları kontrol edilir,
- eşleşme oranı izlenir (düşük oran, kimlik yakalama sorununa işaret eder),
- reklam platformundaki dönüşüm sayısı ile CRM'deki kazanılmış satış sayısı karşılaştırılır,
- test verisinin üretim optimizasyonunu etkilemediği doğrulanır.

## 9. Beklenen Etki

Doğru kurulduğunda görülen tipik değişimler: form gönderimi başına maliyet artar (çünkü hedef değişti), nitelikli aday oranı yükselir, satış başına maliyet düşer, satış ekibinin harcadığı boş zaman azalır ve bütçe gerçekten dönüşen segmentlere kayar.

Raporlamada bu nedenle EBM tek başına okunmamalıdır; birincil metrik satış başına maliyet olmalıdır.

## Sık Sorulan Sorular

**CRM'im yoksa yapılabilir mi?** Elektronik tablo ile başlanabilir ancak sürdürülebilir değildir. Aday sayısı artınca otomatik akış şarttır.

**Ne kadar sürede sonuç verir?** İlk yüklemelerden sonra algoritmanın yeni sinyale uyum sağlaması genellikle 4-8 hafta alır. Satış döngüsü uzunsa daha fazla.

**Analitik tarafına da yansıtmalı mıyım?** Evet, önerilir. Böylece kanal bazlı gerçek satış performansı tek yerde raporlanabilir ve pazarlama panosu gerçek sonuç üzerinden okunur.
