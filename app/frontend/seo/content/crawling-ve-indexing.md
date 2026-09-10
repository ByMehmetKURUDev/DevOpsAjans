---
title: "Crawling ve Indexing Nedir? Tarama ve İndeksleme Yönetimi"
description: "Crawling ve indexing süreçleri nasıl çalışır? Tarama bütçesi yönetimi, robots.txt, canonical, noindex kullanımı, indeksleme sorunlarının teşhisi ve çözüm yöntemleri."
keywords: "crawling nedir, indexing nedir, tarama bütçesi, crawl budget, robots.txt, noindex, canonical, indeksleme sorunları, Search Console"
category: "SEO"
tags:
  - "SEO"
  - "Teknik SEO"
  - "Indexing"
date: "2026-04-08"
lang: "tr"
og_title: "Crawling ve Indexing Nedir?"
og_description: "Tarama ve indeksleme sürecinin yönetimi ve sorun teşhisi."
og_type: "article"
twitter_card: "summary"
twitter_title: "Crawling ve Indexing Nedir?"
twitter_description: "Tarama bütçesi, indeksleme kontrolü ve teşhis yöntemleri."
---
Arama görünürlüğünün ilk iki koşulu taranmak ve indekslenmektir. Bir sayfa taranmazsa içeriği bilinmez; indekslenmezse sorgu sonuçlarında yer alamaz. Bu nedenle içerik ve bağlantı çalışmalarından önce bu iki katmanın sağlıklı olduğundan emin olunmalıdır.

## 1. Crawling (Tarama)

Tarama, botların bağlantıları izleyerek sayfaları keşfetme ve içeriğini indirme sürecidir. Keşif kaynakları: iç bağlantılar, sitemap kayıtları, dış bağlantılar ve daha önce bilinen URL'ler.

Taramayı etkileyen unsurlar:

- **Sunucu yanıt süresi ve hata oranı:** Yavaş veya hata dönen sunucu tarama hızını düşürür.
- **İç link yapısı:** Hiçbir yerden bağlantı almayan sayfalar geç keşfedilir.
- **URL uzayının büyüklüğü:** Filtre ve parametre kombinasyonları sınırsız URL üretiyorsa bot değersiz sayfalarda dolaşır.
- **Yönlendirme zincirleri:** Her ek adım tarama maliyeti üretir.

## 2. Indexing (İndeksleme)

İndeksleme, taranan sayfanın işlenip dizine alınmasıdır. Bu aşamada içerik render edilir, konusu belirlenir, kanonik sürüm seçilir ve kalite değerlendirmesi yapılır. Taranmış her sayfa indekslenmez; içerik yetersizse, kopya olarak değerlendirilirse veya `noindex` taşıyorsa dizine alınmaz.

## 3. Tarama Bütçesi Yönetimi

Küçük sitelerde tarama bütçesi genellikle sorun değildir; binlerce URL üreten sitelerde kritiktir. Uygulanacaklar:

- değersiz parametreli URL'lerin taranmasını engelleyin,
- sonsuz takvim, filtre ve sıralama kombinasyonlarını kapatın,
- yönlendirme zincirlerini tek adıma indirin,
- kırık bağlantıları temizleyin,
- sitemap'te yalnızca kanonik ve indekslenmesi istenen URL'leri tutun,
- önemli sayfalara ana gezinme ve içerik içinden bağlantı verin.

## 4. Kontrol Araçları ve Doğru Kullanımı

**robots.txt:** Taramayı engeller, indekslemeyi garanti etmez. CSS ve JS dosyaları engellenmemelidir; aksi halde sayfa doğru render edilemez.

**noindex meta etiketi:** İndekslemeyi engeller. Ancak sayfa robots.txt ile taranması engellenmişse bot bu etiketi göremez. İki yöntem aynı URL'de birlikte kullanılmamalıdır.

**canonical:** Kopya veya çok benzer sayfalar arasında tercih edilen sürümü bildirir. Bir öneridir, kesin komut değildir; çelişkili sinyaller verilirse yok sayılabilir.

**301 / 302:** Kalıcı taşımalarda 301 kullanılır. Geçici durumlar dışında 302 tercih edilmemelidir.

**410:** Kalıcı olarak kaldırılan ve karşılığı olmayan içerikler için doğru yanıttır.

## 5. Render Katmanı

İçerik yalnızca JavaScript çalıştıktan sonra oluşuyorsa indekslenme gecikebilir veya eksik olabilir. Güvenli yaklaşım sunucu tarafı render veya statik ön render'dır. Kontrol yöntemi: sayfanın HTML kaynağında ana metin, başlıklar ve iç bağlantıların bulunup bulunmadığını doğrulamak.

## 6. Yaygın İndeksleme Sorunları ve Teşhis

| Belirti | Olası neden | Çözüm |
|---|---|---|
| Sayfa keşfedilmiyor | İç bağlantı yok, sitemap'te değil | Bağlantı ver, sitemap'e ekle |
| Tarandı ama indekslenmedi | İçerik yetersiz veya kopya | İçeriği güçlendir veya birleştir |
| Alternatif sürüm seçildi | Çelişkili canonical | Canonical ve iç bağlantıları tek adrese hizala |
| robots ile engellendi | Yanlış kural | robots.txt kuralını düzelt |
| Yönlendirme hatası | Zincir veya döngü | Tek adımlı 301 kur |
| Sunucu hatası | 5xx yanıtlar | Altyapı ve kaynak kullanımını incele |

Teşhis için Search Console'daki sayfa raporu, URL denetimi ve sunucu erişim kayıtları birlikte okunmalıdır.

## 7. İzleme Rutini

Aylık kontrol edilmesi gerekenler: indekslenen ve indekslenmeyen sayfa sayısındaki değişim, hata dönen URL'lerin oranı, ortalama sunucu yanıt süresi, sitemap'teki URL sayısı ile indekslenen sayı arasındaki fark ve tarama isteklerinin sayfa türlerine dağılımı.

## Sık Sorulan Sorular

**Yeni sayfa ne kadar sürede indekslenir?** Site otoritesi ve iç bağlantı gücüne bağlı olarak saatler ile haftalar arasında değişir. Sitemap ve iç bağlantı süreci hızlandırır.

**Her sayfa indekslenmeli mi?** Hayır. Filtre sonuçları, teşekkür sayfaları ve yönetim ekranları dizinde olmamalıdır.

**robots.txt ile engellemek dizinden kaldırır mı?** Hayır; hâlâ dizinde kalabilir. Kaldırmak için taramaya izin verip `noindex` kullanmak gerekir.
