---
title: "Pazarlama Verisinde Erişim Kontrolü ve Yetkilendirme"
description: "Pazarlama verisine erişim nasıl yönetilir? Rol tabanlı yetkilendirme, sütun ve satır düzeyi kısıtlama, maskeleme, ajans erişimi ve denetim kaydı."
keywords: "veri erişim kontrolü, RBAC, sütun düzeyi güvenlik, satır düzeyi güvenlik, veri maskeleme, PII erişimi, denetim kaydı, ajans erişimi"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Data Governance"
  - "Güvenlik"
date: "2026-09-10"
lang: "tr"
og_title: "Pazarlama Verisinde Erişim Kontrolü"
og_description: "Kimin hangi veriyi görebileceğini tasarlamanın pratik kuralları."
og_type: "article"
twitter_card: "summary"
twitter_title: "Pazarlama Verisinde Erişim Kontrolü"
twitter_description: "Rol, sütun, satır ve maskeleme katmanlarıyla veri erişimi."
og_image: "https://mehmetkuru.dev/blog-covers/marketing-data-access-control.webp"
og_image_alt: "Pazarlama Verisinde Erişim Kontrolü ve Yetkilendirme"
---
Yeni işe başlayan bir stajyere rapor erişimi verilir. Verilen yetki, aslında tüm müşteri tablosunu okuma yetkisidir — çünkü rapor o tablodan besleniyordur ve kimse arada bir katman kurmamıştır. Kimse kötü niyetli değildir; sadece erişim, ihtiyaç yerine kolaylık üzerine tasarlanmıştır. Pazarlama verisinde erişim kontrolü, bu kolaylığın maliyetini ortadan kaldırma işidir.

## 1. Temel İlke: Gereken Kadar

Her erişim kararının çıkış noktası tek bir sorudur: bu kişi işini yapmak için hangi veriye, hangi ayrıntı düzeyinde ihtiyaç duyuyor?

Çoğu pazarlama işi kişisel veri gerektirmez:

| İş | Gerekli veri | Gerekmeyen |
|---|---|---|
| Kampanya performans raporu | Toplulaştırılmış metrikler | Müşteri kimlikleri |
| Segment büyüklüğü analizi | Sayımlar | E-posta, telefon |
| Kitle aktivasyonu | Karma (hash) kimlik | Açık iletişim bilgisi |
| Müşteri destek çözümü | Tek müşterinin kaydı | Tüm müşteri tablosu |
| Veri modeli geliştirme | Örnek/maskelenmiş veri | Üretim kişisel verisi |

Bu tablo çıkarıldığında, gerçekten açık kişisel veri gerektiren iş sayısının ne kadar az olduğu görülür.

## 2. Katmanlar

Erişim kontrolü tek bir ayar değil, üst üste binen katmanlardır:

**Rol düzeyi:** Kişi hangi veri kümelerine erişebilir? Kişi bazlı değil rol bazlı tanımlanır; kişi işten ayrıldığında veya görev değiştirdiğinde tek yerden düşer.

**Sütun düzeyi:** Erişilen tablonun hangi alanları görünür? Analistin sipariş tablosuna erişmesi, müşterinin telefonunu görmesi anlamına gelmemelidir.

**Satır düzeyi:** Hangi kayıtlar görünür? Bölge sorumlusu yalnızca kendi bölgesinin kayıtlarını görür.

**Maskeleme:** Alan görünür ama değeri kısmen gizlidir (`05** *** ** 78`). Destek ekibinin doğrulama yapması için genellikle yeterlidir.

Dördüncü katman en az kullanılan ve en çok işe yarayanıdır: pek çok senaryoda ihtiyaç "veriyi görmek" değil, "doğrulamak"tır.

## 3. Sınıflandırmaya Bağlamak

Erişim kuralları alan alan yazılırsa bakımı imkânsız hâle gelir. Doğru yöntem, kuralları [veri sınıflandırmasına](/blog/data-classification-pii-management/) bağlamaktır:

- alanlar hassasiyet sınıfına göre etiketlenir,
- erişim kuralı sınıf düzeyinde yazılır,
- yeni bir alan eklendiğinde sınıfı belirlenir, kural otomatik uygulanır.

Bu bağ kurulmazsa, her yeni alan varsayılan olarak herkese açık gelir — ve bu, veri sızıntılarının en sık yoludur.

## 4. Ajans ve Üçüncü Taraf Erişimi

Dış ekiplerin erişimi, iç ekiplerden farklı ele alınmalıdır:

- erişim süreli verilir ve bitiş tarihi tanımlanır,
- kapsam sözleşmede yazılı işle sınırlanır,
- açık kişisel veri yerine toplulaştırılmış veya karma veri paylaşılır,
- veri işleme sorumlulukları yazılı olarak belirlenir,
- erişim, iş bittiğinde kapatılır ve kapatıldığı doğrulanır.

Son madde çoğu kurumda atlanır: biten projelerin erişimleri yıllarca açık kalır. Düzenli bir erişim gözden geçirmesi, bulunması en kolay ve kapatılması en hızlı risktir.

## 5. Denetim Kaydı

Kimin hangi veriye ne zaman eriştiği kaydedilmelidir. Bu kayıt üç işe yarar:

- olağandışı erişim örüntülerini fark etmek (tek seferde yüz binlerce kaydın dışa aktarılması),
- bir olay sonrası kapsamı belirlemek,
- kullanılmayan erişimleri tespit edip kapatmak.

Üçüncüsü günlük değer üretir: altı aydır kullanılmayan erişimler, çoğunlukla artık gerekli olmayan erişimlerdir.

## 6. Dışa Aktarım Noktaları

Erişim kontrolü yalnızca ambarda uygulanırsa eksik kalır. Veri sistemden şu yollarla çıkar:

- rapor araçlarından CSV indirme,
- [Reverse ETL](/blog/reverse-etl/) ile üçüncü taraf sistemlere yazma,
- reklam platformlarına kitle yükleme,
- geliştirme ortamına üretim verisi kopyalama.

Son madde en riskli olanıdır ve en sık yapılanıdır. Geliştirme ortamına üretim kişisel verisi kopyalanmamalı; maskelenmiş veya sentetik veri kullanılmalıdır.

## 7. Uygulama Sırası

1. hangi rollerin hangi işi yaptığını yazmak,
2. her iş için gereken asgari veriyi belirlemek,
3. alanları hassasiyet sınıfına göre etiketlemek,
4. kuralları sınıf düzeyinde tanımlamak,
5. açık kişisel veri yerine maskeleme veya toplulaştırma sunmak,
6. dışa aktarım noktalarını kapsama almak,
7. denetim kaydını açmak,
8. üç ayda bir erişim gözden geçirmesi yapmak,
9. ayrılan/görev değiştiren kişiler için otomatik kapatma kurmak.

İkinci madde en çok direnç gören adımdır ve en çok değer üretendir: "her ihtimale karşı" istenen erişimlerin çoğu, gerekçesi yazılmaya çalışıldığında kendiliğinden düşer.

## Sık Sorulan Sorular

**Erişimi kısıtlamak analiz hızını düşürmez mi?** Doğru kurulduğunda düşürmez. Analistlerin ihtiyacı genellikle toplulaştırılmış veridir; hazır ve erişimi açık bir toplulaştırılmış katman, hem daha hızlı hem daha güvenlidir.

**Küçük ekipte bu kadar katman gerekli mi?** Katmanların hepsi değil, ilkeler gerekli. Üç kişilik bir ekipte bile "kişisel veri yalnızca gerektiğinde, maskelenmiş biçimde" kuralı uygulanabilir ve ekip büyüdüğünde temel hazır olur.

**Rapor aracı kendi yetkilendirmesini sunuyor, yetmez mi?** Yetmez. Rapor aracındaki yetki yalnızca o aracı kapsar; aynı veriye ambardan doğrudan erişen bir kişi o kuralları görmez. Yetkilendirmenin veri katmanında da uygulanması gerekir.
