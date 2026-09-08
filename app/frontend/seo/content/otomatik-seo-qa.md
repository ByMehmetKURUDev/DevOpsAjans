---
title: "Otomatik SEO QA: Yayın Öncesi SEO Kalite Kontrolü"
description: "Otomatik SEO QA nasıl kurulur? Yayın hattına eklenen kontroller, test seviyeleri, kritik ve uyarı seviyeli kurallar, örnek kontrol listesi ve regresyonları önleme yöntemi."
keywords: "SEO QA, otomatik SEO testi, SEO regresyon kontrolü, CI SEO kontrolü, yayın öncesi kontrol listesi, teknik SEO testi, kalite kapısı"
category: "SEO"
tags:
  - "SEO"
  - "QA"
  - "Otomasyon"
date: "2026-06-24"
lang: "tr"
og_title: "Otomatik SEO QA"
og_description: "Yayın hattına entegre otomatik SEO kalite kontrolleri kurmak."
og_type: "article"
twitter_card: "summary"
twitter_title: "Otomatik SEO QA"
twitter_description: "SEO regresyonlarını canlıya çıkmadan yakalayan test katmanı."
---

# Otomatik SEO QA: Yayın Öncesi SEO Kalite Kontrolü

SEO sorunlarının önemli bir kısmı yeni bir sorun değil, daha önce çözülmüş bir sorunun tekrar ortaya çıkmasıdır. Bir şablon değişikliğinde canonical kaybolur, bir bileşen eklemesinde ikinci bir `h1` oluşur, bir yeniden yapılandırmada iç bağlantılar kırılır. Otomatik SEO QA, bu regresyonları canlıya çıkmadan yakalayan test katmanıdır.

## 1. Neden Manuel Denetim Yetmez?

Manuel denetim üç nedenle yetersizdir: her yayında tekrarlanamaz, örnekleme yapıldığı için kapsamı sınırlıdır ve sorunun fark edilmesi ile düzeltilmesi arasında haftalar geçer. Otomatik kontrol ise her yayında, tüm şablonlarda ve dakikalar içinde çalışır.

## 2. Test Seviyeleri

**Bileşen testleri.** Şablon bileşenlerinin doğru çıktı ürettiği doğrulanır: başlık bileşeni tek `h1` üretiyor mu, meta bileşeni verilen değerleri doğru yazıyor mu, bağlantı bileşeni doğru URL biçimi kuruyor mu.

**Yapı sonrası (build) kontrolleri.** Üretilen HTML çıktısı taranır. Statik veya ön render edilmiş sitelerde bu en verimli katmandır; tüm sayfalar dosya sisteminden okunarak denetlenebilir.

**Ön yayın (staging) taraması.** Küçük bir tarama aracı örnek sayfa kümesini gezer; yönlendirme, durum kodu ve iç bağlantı bütünlüğü kontrol edilir.

**Performans kontrolleri.** Kritik sayfa türlerinde ölçüm alınır ve bütçe eşiği aşılmışsa uyarı üretilir.

**Canlı izleme.** Yayın sonrası düzenli kontrol, altyapı veya içerik kaynaklı sonradan oluşan sorunları yakalar.

## 3. Örnek Kontrol Kümesi

**Kritik (yayını engeller):**

- sayfada `h1` yok veya birden fazla,
- `title` eksik veya boş,
- `canonical` eksik ya da yanlış alan adına işaret ediyor,
- yanlışlıkla `noindex` eklenmiş,
- ana içerik sunucu yanıtındaki HTML'de yok,
- iç bağlantılar 404 dönüyor,
- yönlendirme döngüsü var,
- sitemap oluşmamış veya boş.

**Uyarı (rapor edilir, yayını engellemez):**

- `title` karakter aralığı dışında,
- `meta description` eksik,
- görsellerde `alt` metni yok,
- yapılandırılmış veride şema uyarısı,
- aynı `title`/`description` birden fazla sayfada,
- görsel dosya boyutu eşiğin üstünde,
- sayfa başına JavaScript bütçesi aşılmış,
- `hreflang` karşılıklılığı eksik.

Kritik ve uyarı ayrımı önemlidir; her bulguyu yayın engelleyici yapmak süreci tıkar ve kuralların devre dışı bırakılmasına yol açar.

## 4. Yayın Hattına Entegrasyon

Akış şöyle kurulur: kod değişikliği gönderilir → proje derlenir → yapı sonrası SEO kontrolleri çalışır → kritik ihlal varsa süreç durur ve rapor üretilir → geçerse ön yayın ortamına aktarılır → performans ve tarama kontrolleri çalışır → sonuç raporu ilgili kanala gönderilir.

Rapor çıktısı okunabilir olmalıdır: hangi kural, hangi sayfada, hangi değerle ihlal edildi. "SEO testi başarısız" mesajı düzeltmeyi kolaylaştırmaz.

## 5. Kuralların Yönetimi

- tüm kurallar ve eşikler sürüm kontrolünde bir yapılandırma dosyasında tutulur,
- sayfa türüne göre farklı kurallar tanımlanabilir (blog ile ürün sayfası aynı kriterlere tabi olmayabilir),
- bilinçli istisnalar açık biçimde ve gerekçesiyle kaydedilir,
- yeni bir regresyon yaşandığında ilk aksiyon o regresyon için kural yazmaktır.

Son madde, sistemin zamanla güçlenmesini sağlayan mekanizmadır.

## 6. Kapsamı Kademeli Büyütmek

Baştan onlarca kural yazmaya çalışmak yerine en sık yaşanan üç regresyonla başlanır. Kontroller güvenilir çalıştıkça kapsam genişletilir. Yanlış pozitif üreten kurallar hemen düzeltilir; güvenilmeyen bir test kısa sürede görmezden gelinir.

## 7. Ölçülebilir Fayda

QA katmanının değeri şu göstergelerle izlenir: canlıya çıkan SEO regresyon sayısı, bir sorunun fark edilme süresi, denetlenen sayfa oranı, tekrarlayan hata tipi sayısı ve manuel denetime harcanan zaman.

## Sık Sorulan Sorular

**Küçük siteler için gerekli mi?** Tek bir yapı sonrası kontrol script'i bile en yaygın hataları yakalar; maliyeti düşük, getirisi yüksektir.

**Hangi araçlar kullanılır?** HTML ayrıştırma kütüphaneleri, headless tarayıcı ile render kontrolü, performans ölçüm araçları ve yapılandırılmış veri doğrulayıcıları tipik bileşenlerdir.

**Testler yayını çok yavaşlatır mı?** Yapı sonrası statik kontroller hızlıdır. Performans ve tarama kontrolleri örneklem üzerinde çalıştırılarak süre kontrol altında tutulur.
