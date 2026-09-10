---
title: "CDP, CRM ve Veri Ambarı Arasındaki Fark Nedir?"
description: "CDP, CRM ve veri ambarı ne işe yarar, nerede örtüşür ve hangi ihtiyaçta hangisi seçilmelidir? Mimari karşılaştırma, seçim kriterleri ve birlikte çalışma modeli."
keywords: "CDP nedir, CRM nedir, veri ambarı, data warehouse, CDP vs CRM, müşteri veri platformu, veri mimarisi seçimi"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Müşteri Verisi"
date: "2026-09-11"
lang: "tr"
og_title: "CDP, CRM ve Veri Ambarı Farkı"
og_description: "Üç sistemin rolleri, örtüşme alanları ve seçim kriterleri."
og_type: "article"
twitter_card: "summary"
twitter_title: "CDP, CRM ve Veri Ambarı"
twitter_description: "Hangi ihtiyaçta hangi sistem kullanılmalı?"
og_image: "https://mehmetkuru.dev/blog-covers/cdp-vs-crm-vs-data-warehouse.webp"
og_image_alt: "CDP, CRM ve Veri Ambarı Arasındaki Fark Nedir?"
---
Bu üç sistem sık sık birbirinin alternatifi olarak sunulur; oysa farklı sorunları çözerler. Yanlış eşleştirme, hem gereksiz maliyet hem de çözülmemiş ihtiyaç üretir. Ayrımı netleştirmenin en pratik yolu, her birinin hangi soruyu yanıtladığına bakmaktır.

## 1. Üç Sistem, Üç Soru

**CRM — "Bu müşteriyle ilişkimiz nerede?"**
Satış ve hizmet ilişkisini yönetir: kişiler, fırsatlar, görüşme notları, teklifler, destek talepleri. Operasyonel bir çalışma aracıdır; insanlar günlük işlerini burada yapar.

**Veri ambarı — "Ne oldu ve neden?"**
Tüm kaynaklardan gelen veriyi merkezî, sorgulanabilir ve tarihsel biçimde tutar. Analiz ve raporlamanın temelidir. Doğruluk ve derinlik önceliklidir.

**CDP — "Bu müşteriye şimdi hangi mesajı göstermeliyim?"**
Müşteri profillerini birleştirir, segmentler oluşturur ve bu segmentleri pazarlama kanallarına gönderir. Aktivasyon odaklıdır; hız ve kanal entegrasyonu önceliklidir.

## 2. Karşılaştırma

| Boyut | CRM | Veri Ambarı | CDP |
|---|---|---|---|
| Ana kullanıcı | Satış, destek | Analist, veri ekibi | Pazarlama |
| Veri tipi | Yapılandırılmış ilişki verisi | Her tür, tarihsel | Davranış + profil |
| Güçlü yönü | Operasyonel iş akışı | Derin analiz, tek doğruluk kaynağı | Segment ve kanal aktivasyonu |
| Zayıf yönü | Web davranışını ölçekli tutmaz | Doğrudan aktivasyon yapmaz | Derin tarihsel analiz için sınırlı |
| Gerçek zaman | Kısmen | Genellikle toplu | Çoğunlukla evet |
| Kimlik çözümleme | Sınırlı | Kurulabilir | Yerleşik yetenek |

## 3. Örtüşme Alanları ve Karışıklık Nedeni

Üç sistem de müşteri verisi tutar; bu nedenle örtüşme kaçınılmazdır:

- CRM'de de pazarlama otomasyonu modülleri bulunur,
- veri ambarı üzerine kurulan modellerle CDP benzeri segmentler üretilebilir,
- CDP'ler giderek analitik yetenek ekliyor.

Karar verirken sorulacak doğru soru "hangisi daha kapsamlı" değil, "hangi darboğazı çözüyorum" olmalıdır.

## 4. Karar Rehberi

**CRM önce gerekir** eğer: satış süreci elektronik tabloda takip ediliyorsa, müşteri iletişim geçmişi kişilerin e-posta kutusunda dağınıksa, destek talepleri izlenemiyorsa.

**Veri ambarı önce gerekir** eğer: raporlar birbiriyle çelişiyorsa, her analiz elle veri birleştirmeyle yapılıyorsa, kanal performansı kârlılıkla ilişkilendirilemiyorsa, LTV ve CAC güvenilir hesaplanamıyorsa.

**CDP değer üretir** eğer: veri zaten toplanıyor ama pazarlama kanallarına hızlı segment gönderilemiyorsa, segment oluşturmak her seferinde veri ekibi talebi gerektiriyorsa, çok kanallı kişiselleştirme ihtiyacı gerçekten varsa ve bunu karşılayacak içerik/operasyon kapasitesi mevcutsa.

**Sık yapılan hata:** Veri kalitesi ve kimlik çözümlemesi çözülmeden CDP satın almak. CDP, girdi kalitesini iyileştirmez; yalnızca mevcut veriyi hızlı aktive eder. Kötü veriyle daha hızlı yanlış mesaj gönderilir.

## 5. Modern Mimari: Birlikte Çalışma

Bugün yaygın ve dayanıklı model şudur:

1. **Veri ambarı merkezde durur.** Tüm kaynaklar buraya akar; tanımlar burada netleşir; kimlik çözümlemesi ve metrik katmanı burada kurulur.
2. **CRM operasyonel gerçeği besler.** Satış aşamaları ve ilişki verisi ambara aktarılır.
3. **Aktivasyon ambardan yapılır.** Segmentler ambarda üretilir ve tersine ETL ile pazarlama araçlarına gönderilir. Bu yaklaşım, ayrı bir CDP ihtiyacını birçok kurumda ortadan kaldırır.
4. **CDP, gerçek zamanlı ve karmaşık kanal ihtiyacı varsa eklenir**, ambarın yerine değil üzerine.

Bu mimarinin avantajı: tek gerçek kaynak korunur, tanım tekrarı olmaz, araç değişimi veri katmanını bozmaz.

## 6. Ortak Ön Koşullar

Hangi sistem seçilirse seçilsin, önce çözülmesi gerekenler:

- kimlik çözümleme stratejisi,
- metrik ve boyut tanımlarının merkezileştirilmesi,
- kampanya isimlendirme ve UTM disiplini,
- veri kalitesi izleme,
- rıza ve gizlilik yönetimi,
- erişim kontrolü ve hassas veri politikası.

Bu ön koşullar olmadan alınan hiçbir araç, beklenen değeri üretmez. Araç seçimi, disiplin eksikliğini kapatmaz.

## 7. Maliyet ve Sahiplik

Değerlendirmede yalnızca lisans bedeli değil, toplam sahip olma maliyeti hesaplanmalıdır: entegrasyon geliştirme, veri hacmi bazlı ücretlendirme, bakım ve izleme yükü, ekip eğitimi, tedarikçiye bağımlılık riski ve veriyi taşıma maliyeti.

Ekip kapasitesi de kritiktir: güçlü bir araç, onu işletecek kimse yoksa değer üretmez.

## 8. Aşamalı Yol Haritası

Sıfırdan kuran bir kurum için pratik sıra:

1. temel analitik ve ölçüm hijyeni,
2. CRM ile satış/hizmet ilişkisinin kayda geçmesi,
3. veri ambarı ve merkezi tanımlar,
4. kimlik çözümleme ve müşteri modeli,
5. tersine ETL ile aktivasyon,
6. ihtiyaç kanıtlandıysa CDP.

Her adım, sonrakinin ön koşuludur. Sıra atlandığında en yaygın sonuç, kullanılmayan bir platform lisansıdır.

## Sık Sorulan Sorular

**Küçük işletme hangisinden başlamalı?** CRM ve doğru kurulmuş web analitiği yeterlidir. Veri ambarı, kaynak sayısı ve rapor çelişkisi arttığında gerekir.

**CDP olmadan kişiselleştirme yapılabilir mi?** Yapılabilir. Ambar tabanlı segment üretimi ve tersine ETL, çoğu kişiselleştirme senaryosunu karşılar.

**Üçü birlikte gerekli mi?** Orta ve büyük ölçekte CRM + ambar neredeyse her zaman gereklidir. CDP ise gerçek zamanlı, çok kanallı ve yüksek hacimli aktivasyon ihtiyacı kanıtlandığında eklenir.
