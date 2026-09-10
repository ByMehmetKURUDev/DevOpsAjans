---
title: "Veri Sözleşmeleri (Data Contracts) ile Pazarlama Verisini Korumak"
description: "Data contract nedir, pazarlama verisini sessiz bozulmalardan nasıl korur? Şema, anlam, sahiplik, SLA, sürümleme ve ihlal durumunda işleyiş."
keywords: "data contract, veri sözleşmesi, şema doğrulama, veri kalitesi, event tracking, veri sahipliği, kırıcı değişiklik, semantic versioning"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Ölçümleme"
date: "2026-09-10"
lang: "tr"
og_title: "Veri Sözleşmeleri (Data Contracts)"
og_description: "Pazarlama verisinin sessizce bozulmasını engelleyen sözleşme yaklaşımı."
og_type: "article"
twitter_card: "summary"
twitter_title: "Veri Sözleşmeleri (Data Contracts)"
twitter_description: "Şema, sahiplik ve SLA ile veri bozulmalarını önlemek."
og_image: "https://mehmetkuru.dev/blog-covers/marketing-data-contracts.webp"
og_image_alt: "Veri Sözleşmeleri (Data Contracts) ile Pazarlama Verisini Korumak"
---
Bir geliştirici, ödeme akışındaki bir alanın adını `order_total`'dan `total_amount`'a çevirir. Kod testleri geçer, sürüm yayınlanır. Üç hafta sonra pazarlama ekibi gelir raporunun neden yarıya düştüğünü sorar. Kimse bu değişikliğin raporu etkileyeceğini bilmiyordu, çünkü o alanın bir "müşterisi" olduğu hiçbir yerde yazılı değildi. Veri sözleşmeleri tam olarak bu boşluğu kapatır.

## 1. Problem: Sessiz Bozulma

Pazarlama verisi, ürün ekibinin kararlarına bağımlıdır ama bu bağımlılık genellikle görünmezdir. Sonuç, en pahalı hata türüdür: sistem hata vermez, veri akmaya devam eder, sadece yanlıştır.

Tipik sessiz bozulma biçimleri:

- alan adının veya tipinin değişmesi,
- bir olayın gönderilmeyi bırakması,
- para biriminin kuruş yerine lira olarak gönderilmeye başlaması,
- boş değerlerin `null` yerine boş metin gelmesi,
- aynı olayın iki kez tetiklenmesi.

Bunların hiçbiri uygulama tarafında bir arıza üretmez. Hepsi rapor tarafında yanlış karar üretir.

## 2. Veri Sözleşmesi Nedir?

Veri sözleşmesi, bir veri kümesini üreten taraf ile tüketen taraf arasındaki yazılı ve makine tarafından doğrulanabilir anlaşmadır. Belge değil, kod deposunda yaşayan ve derleme sürecinde kontrol edilen bir tanımdır.

Sözleşmenin kritik özelliği makine tarafından doğrulanabilir olmasıdır. Wiki sayfasında duran bir şema tanımı sözleşme değildir; kimse okumaz ve hiçbir şeyi engellemez.

## 3. Bir Sözleşme Neleri İçerir?

| Bölüm | İçerik |
|---|---|
| Şema | Alan adları, tipleri, zorunluluk durumu |
| Anlam | Her alanın ne ifade ettiği, birimi, hesaplanma biçimi |
| Sahiplik | Üreten ekip ve sorumlu kişi |
| Tüketiciler | Bu veriyi kimin, hangi amaçla kullandığı |
| Kalite kuralları | Kabul edilebilir boş değer oranı, değer aralıkları, benzersizlik |
| Tazelik SLA'sı | Verinin en geç ne zaman ulaşmış olması gerektiği |
| Gizlilik sınıfı | Alanın hassasiyet düzeyi ve erişim kuralı |

"Anlam" bölümü en çok atlanan ve en çok soruna yol açan kısımdır. `revenue` alanının vergi dâhil mi hariç mi, iadeler düşülmüş mü olduğu yazılı değilse, iki ekip aynı alandan iki farklı sayı üretir.

## 4. Nerede Uygulanır?

Sözleşme, verinin sisteme girdiği noktada uygulanmalıdır — sonradan ambarda değil.

- olay toplama katmanında şema doğrulaması,
- şemaya uymayan olayın ayrı bir "reddedilen" akışına alınması,
- derleme sürecinde şema değişikliği kontrolü,
- ambar tarafında kalite testleri (ikinci savunma hattı).

Reddedilen olayları sessizce atmak yerine ayrı bir yerde tutmak önemlidir: hem hata teşhisi hem de veri kurtarma için tek şansınız odur.

## 5. Sürümleme ve Kırıcı Değişiklik

Sözleşmeler değişir; önemli olan değişimin öngörülebilir olmasıdır.

**Kırıcı olmayan değişiklikler:** yeni isteğe bağlı alan eklemek, açıklama güncellemek, kalite eşiğini gevşetmek.

**Kırıcı değişiklikler:** alan silmek, alan adı değiştirmek, tip değiştirmek, isteğe bağlı alanı zorunlu yapmak, birim değiştirmek.

Kırıcı değişiklik için işleyiş:

1. yeni sürüm tanımlanır, eski sürüm bir süre birlikte yayınlanır,
2. tüketiciler bilgilendirilir ve geçiş süresi verilir,
3. eski sürümün kullanımı izlenir,
4. kullanım sıfırlandığında eski sürüm kaldırılır.

Bu işleyişin uygulanabilmesi, verinin kimler tarafından tüketildiğinin bilinmesine bağlıdır — yani [veri kökeni ve etki analizi](/blog/data-lineage-impact-analysis/) çalışmasına.

## 6. İhlal Durumunda Ne Olur?

Sözleşmenin yaptırımı yoksa sözleşme değildir. Önceden kararlaştırılması gerekenler:

- şema ihlali derlemeyi mi durduracak, uyarı mı üretecek,
- tazelik SLA'sı aşıldığında kim haberdar edilecek,
- kalite eşiği aşıldığında ilgili rapor "güvenilmez" olarak mı işaretlenecek,
- ihlal kaydı nerede tutulacak.

Pratik bir başlangıç: kritik olaylarda derlemeyi durdurmak, diğerlerinde uyarı üretmek. Her ihlalde derlemeyi durdurmak, ekibin kontrolü tamamen devre dışı bırakmasıyla sonuçlanır.

## 7. Organizasyonel Taraf

Veri sözleşmeleri teknik bir çözüm gibi görünür ama asıl işlevi sorumluluğu netleştirmektir. Sözleşme, "bu alanı değiştirirsen şu üç rapor bozulur" cümlesini tartışmadan önce görünür kılar.

Bunun işlemesi için:

- her veri kümesinin bir sahibi olmalı,
- tüketici listesi güncel tutulmalı,
- değişiklik talebi için bir yol olmalı,
- ölçümleme ihtiyacı, ürün geliştirme sürecinin başında konuşulmalı.

Son madde en büyük farkı yaratır: ölçümleme, sürüm çıktıktan sonra eklenen bir iş olmaktan çıkıp gereksinimin parçası hâline gelir.

## 8. Nereden Başlamalı?

1. en çok karara bağlanan 3-5 olayı seçmek (satın alma, kayıt, form gönderimi),
2. bu olayların mevcut şemasını yazılı hâle getirmek,
3. her alanın anlamını ve birimini yazmak,
4. sahibi ve tüketicileri belirlemek,
5. toplama katmanına şema doğrulaması eklemek,
6. reddedilen olay akışını kurmak,
7. kırıcı değişiklik sürecini yazmak,
8. kapsamı kademeli genişletmek.

Tüm veri kümelerini bir seferde sözleşmeye bağlamaya çalışmak, hiçbirini bağlamamakla sonuçlanır.

## Sık Sorulan Sorular

**Küçük bir ekip için fazla ağır değil mi?** Tam sürümü ağır olabilir; ancak "hangi olaylar kritik, alanları ne anlama geliyor, sahibi kim" sorusunun yazılı cevabı her ölçekte değer üretir. Küçük ekipte tek bir dosya yeterlidir.

**Şema doğrulaması performansı etkiler mi?** Toplama katmanında yapılan doğrulama genellikle ihmal edilebilir maliyettedir. Asıl maliyet, doğrulama olmadan üretilen yanlış raporların yol açtığı kararlardır.

**Ambar tarafındaki testler yeterli olmaz mı?** Yardımcı olur ama geç kalır. Bozuk veri ambara ulaştığında zaten toplanmıştır; geriye dönük düzeltme çoğu zaman mümkün değildir. Sözleşme girişte, testler ise ikinci savunma hattında durmalıdır.
