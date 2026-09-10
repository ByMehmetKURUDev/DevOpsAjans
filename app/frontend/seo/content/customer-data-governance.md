---
title: "Müşteri Veri Yönetişimi (Data Governance) Nasıl Kurulur?"
description: "Müşteri veri yönetişimi çerçevesi: sahiplik modeli, veri sınıflandırma, erişim kontrolü, kalite standartları, saklama politikası, denetim ve uygulama adımları."
keywords: "veri yönetişimi, data governance, veri sahipliği, erişim kontrolü, veri kalitesi, saklama politikası, uyum, denetim"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Yönetişim"
  - "Gizlilik"
date: "2026-09-16"
lang: "tr"
og_title: "Müşteri Veri Yönetişimi"
og_description: "Sahiplik, erişim, kalite ve saklama politikalarıyla veri yönetişimi."
og_type: "article"
twitter_card: "summary"
twitter_title: "Müşteri Veri Yönetişimi"
twitter_description: "Uygulanabilir bir veri yönetişimi çerçevesi."
---
Veri yönetişimi, çoğu kurumda kimsenin okumadığı bir politika dokümanı olarak kalır. İşe yarayan yönetişim ise günlük çalışmanın içine gömülüdür: kimin hangi veriye erişeceği, bir alanın ne anlama geldiği, verinin ne kadar saklanacağı ve bir sorun çıktığında kimin karar verdiği net olur.

## 1. Yönetişimin Amacı

Yönetişim, veriye erişimi zorlaştırmak değildir. Amacı üç şeyi birlikte sağlamaktır:

- **güvenilirlik:** aynı soruya aynı yanıt,
- **güvenlik ve uyum:** doğru kişinin doğru veriye erişmesi, yasal yükümlülüklerin karşılanması,
- **hız:** izin sürecinin öngörülebilir olması sayesinde işin durmaması.

Erişimi tamamen kapatan bir yönetişim başarısızdır; insanlar gölge kopyalar üretir ve kontrol tamamen kaybolur.

## 2. Sahiplik Modeli

Her veri varlığı için üç rol tanımlanır:

**Veri sahibi (iş tarafı).** Verinin iş anlamından, tanımından ve erişim kararlarından sorumludur. Genellikle ilgili iş biriminin yöneticisidir.

**Veri yöneticisi / kâhya (steward).** Günlük kalite takibi, tanım dokümantasyonu ve sorun çözümünden sorumludur.

**Teknik sahip (veri/mühendislik).** Boru hatları, depolama, erişim uygulaması ve izlemeden sorumludur.

Sahipsiz veri, yönetişimin çöktüğü ilk yerdir. "Herkesin sorumlu olduğu" veri, pratikte kimsenin sorumlu olmadığı veridir.

## 3. Veri Sınıflandırma

Tüm veri aynı korumayı gerektirmez. Pratik bir sınıflandırma:

| Seviye | İçerik | Erişim |
|---|---|---|
| Genel | Anonim toplu metrikler | Geniş |
| İç kullanım | Kampanya ve performans verisi | Kurum içi |
| Gizli | Kişisel veri (iletişim, sipariş) | Rol bazlı, gerekçeli |
| Hassas | Özel nitelikli veri, ödeme bilgisi | Çok kısıtlı, denetimli |

Sınıflandırma, erişim kontrolünün ve maskeleme kurallarının temelini oluşturur. Etiketleme otomatikleştirilebilir ancak sorumluluk veri sahibinde kalır.

## 4. Erişim Kontrolü

- rol bazlı erişim (kişi bazlı değil pozisyon bazlı),
- en az yetki ilkesi: iş için gereken minimum erişim,
- hassas alanlarda maskeleme ve toplu görünüm sunma,
- geçici erişimlerin süre sonunda otomatik kapanması,
- düzenli erişim gözden geçirmesi (en az altı ayda bir),
- ayrılan çalışanların erişiminin süreçle kapatılması.

Analitik ihtiyaçların çoğu, kişisel veriye erişmeden karşılanabilir. Bu ayrım (analiz için toplu görünüm, operasyon için kişi düzeyi) yönetişimi hem güvenli hem pratik kılar.

## 5. Tanım ve Dokümantasyon

Yönetişimin en görünür faydası burada ortaya çıkar. Her önemli veri varlığı için tutulması gerekenler:

- iş tanımı ve kullanım amacı,
- alan bazlı açıklamalar ve veri tipleri,
- kaynak sistem ve güncellenme sıklığı,
- kalite beklentileri,
- bilinen kısıtlar ve dikkat noktaları,
- sahibi ve iletişim noktası.

Bu dokümantasyon, veri kataloğu aracıyla veya basit bir yapılandırılmış depo ile tutulabilir; önemli olan tek kaynak olması ve güncel kalmasıdır.

## 6. Kalite Standartları

Ölçülebilir kalite boyutları:

- **eksiksizlik:** zorunlu alanların dolu olma oranı,
- **doğruluk:** kaynak sistemle mutabakat,
- **tutarlılık:** sistemler arası çelişki olmaması,
- **güncellik:** verinin beklenen sürede güncellenmesi,
- **teklik:** yinelenen kayıt oranı,
- **geçerlilik:** biçim ve aralık kurallarına uyum.

Her boyut için eşik tanımlanır ve eşik aşıldığında uyarı üretilir. Uyarısı olmayan kalite standardı, yalnızca bir dilek listesidir.

## 7. Saklama ve Silme Politikası

- her veri kategorisi için saklama süresi tanımlanır,
- süre sonunda silme veya anonimleştirme otomatik çalışır,
- kullanıcı silme talebi için uçtan uca süreç kurulur (tüm bağlı sistemler dahil),
- yedeklerdeki verinin de politikaya dahil olduğu unutulmaz,
- silme işlemleri denetlenebilir biçimde kaydedilir.

Silme talebini karşılayamayan bir mimari, uyum açısından kabul edilemez ve bu genellikle teknik değil tasarım hatasıdır.

## 8. Rıza ve Amaç Sınırlaması

- verinin hangi amaçla toplandığı kayıt altına alınır,
- amaç dışı kullanım için yeni rıza gerekir,
- rıza durumu tüm aktivasyon noktalarında kontrol edilir,
- rıza geri çekildiğinde aşağı akıştaki tüm sistemlere yayılır,
- profil birleşmelerinde en kısıtlayıcı rıza esas alınır.

## 9. Karar ve Değişiklik Yönetimi

Yönetişim bir komite toplantısı değil, işleyen bir süreç olmalıdır:

- yeni veri kaynağı eklenmesi için basit onay akışı,
- şema değişikliklerinin etki analiziyle duyurulması,
- metrik tanımı değişikliklerinin sürüm notuyla kaydı,
- veri olaylarında (kalite bozulması, sızıntı şüphesi) olay müdahale süreci,
- düzenli gözden geçirme ritmi.

Süreç ağırlaştıkça atlanır. Hafif ama gerçekten uygulanan bir süreç, ağır ama kâğıt üzerinde kalan bir çerçeveden çok daha değerlidir.

## 10. Uygulama Sırası

1. en kritik veri varlıklarını listelemek (hepsi değil, en çok kullanılan 10-15),
2. her biri için sahip atamak,
3. sınıflandırma yapmak,
4. erişim kurallarını yazmak ve uygulamak,
5. tanım dokümantasyonunu oluşturmak,
6. kalite ölçümlerini ve uyarıları kurmak,
7. saklama ve silme politikasını uygulamaya almak,
8. gözden geçirme ritmini işletmeye almak.

## 11. Başarı Göstergeleri

- veri kaynaklı rapor çelişkisi şikayetlerinin azalması,
- erişim taleplerinin öngörülebilir sürede karşılanması,
- kalite uyarılarının erken yakalanması,
- silme ve erişim taleplerinin süresinde tamamlanması,
- gölge veri kopyalarının azalması,
- yeni analiz projelerinin daha hızlı başlaması.

## Sık Sorulan Sorular

**Küçük ekipte gerekli mi?** Ağır bir çerçeve gerekmez; ancak sahiplik, tanım dokümantasyonu ve saklama politikası her boyutta gereklidir.

**Özel araç şart mı?** Şart değil. Katalog araçları kolaylaştırır ama disiplin araçtan önce gelir.

**Nereden başlanmalı?** En çok tartışılan metriklerin tanımı ve en hassas veri kategorisinin erişim kontrolü. Bu iki adım en hızlı görünür faydayı üretir.
