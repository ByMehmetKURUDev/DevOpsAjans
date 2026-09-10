---
title: "Müşteri Yolculuğu Analitiği (Customer Journey Analytics)"
description: "Müşteri yolculuğu analitiği nedir ve nasıl uygulanır? Yol haritalama, huni ve kohort analizi, kanal geçişleri, sürtünme noktaları ve iyileştirme döngüsü."
keywords: "müşteri yolculuğu analitiği, journey analytics, huni analizi, kohort analizi, sürtünme noktası, çok kanallı yolculuk"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Müşteri Analitiği"
  - "Deneyim"
date: "2026-09-18"
lang: "tr"
og_title: "Müşteri Yolculuğu Analitiği"
og_description: "Yolculuk verisinden iyileştirme kararı üretmek."
og_type: "article"
twitter_card: "summary"
twitter_title: "Müşteri Yolculuğu Analitiği"
twitter_description: "Huni, kohort ve kanal geçişi analizleri."
og_image: "https://mehmetkuru.dev/blog-covers/customer-journey-analytics.webp"
og_image_alt: "Müşteri Yolculuğu Analitiği (Customer Journey Analytics)"
---
Tek tek sayfa metriklerine bakmak, kullanıcının neden satın almadığını açıklamaz. Müşteri yolculuğu analitiği, temas noktalarını sıralı bir bütün olarak inceleyerek sürtünmenin nerede oluştuğunu ve hangi müdahalenin gerçekten fark yaratacağını gösterir.

## 1. Neyi Farklı Yapar?

Klasik raporlama "kaç kişi geldi, kaçı dönüştü" sorusunu yanıtlar. Yolculuk analitiği ise sırayı ve bağlamı korur:

- kullanıcı hangi adımdan hangi adıma geçti,
- nerede geri döndü veya tekrar denedi,
- hangi kanaldan hangi kanala geçti,
- kaç gün ve kaç oturum sonra karar verdi,
- hangi davranış örüntüsü satın almayı öngörüyor.

Bu bakış, "dönüşüm oranı düşük" gibi genel bir gözlemi eyleme dönüştürülebilir bir teşhise çevirir.

## 2. Temel Analiz Türleri

**Huni analizi.** Tanımlı adımlar arasındaki geçiş oranlarını gösterir. En büyük düşüşün yaşandığı adım, en yüksek getirili iyileştirme alanıdır.

**Yol keşfi.** Kullanıcıların gerçekte izlediği sıraları ortaya çıkarır. Tasarlanan akış ile gerçekleşen akış arasındaki fark burada görünür.

**Kohort analizi.** Belirli bir dönemde başlayan kullanıcıların zaman içindeki davranışını izler. Elde tutma ve tekrar satın alma analizinin temelidir.

**Segment karşılaştırması.** Yeni/mevcut müşteri, kanal, cihaz ve coğrafya kırılımlarında yolculuk farklarını gösterir.

**Zaman aralığı analizi.** İlk temas ile dönüşüm arasındaki süre dağılımı. Dönüşüm penceresi ve yeniden pazarlama zamanlaması bu veriyle belirlenir.

## 3. Yolculuk Aşamalarını Tanımlamak

Analize başlamadan önce aşamalar iş gerçeğine göre tanımlanır. E-ticaret örneği: keşif → kategori/liste görüntüleme → ürün detay → sepete ekleme → ödeme başlangıcı → bilgi girişi → satın alma → teslimat sonrası → tekrar satın alma.

Hizmet işletmesi örneği: farkındalık → içerik tüketimi → hizmet sayfası → fiyat/teklif inceleme → iletişim → nitelendirme → teklif → sözleşme → hizmet sunumu → yenileme/tavsiye.

Her aşama ölçülebilir bir olayla eşleşmelidir. Ölçülemeyen aşama, analizde kör noktadır.

## 4. Sürtünme Noktalarını Bulmak

Huni verisi nerede kayıp olduğunu gösterir; nedeni bulmak için ek sinyaller gerekir:

- form alan bazlı terk verisi (hangi alanda vazgeçiliyor),
- hata mesajı ve doğrulama hatası sıklığı,
- sayfa performansı (yavaş adımlar terk oranını artırır),
- cihaz bazlı fark (mobilde belirgin düşüş genellikle arayüz sorunudur),
- tekrarlanan adım denemeleri (kullanıcı anlamadığı için tekrar deniyor),
- destek talebi ve arama kayıtlarındaki tekrarlayan sorular.

**Yaygın bulgu:** Sepete ekleme ile ödeme başlangıcı arasındaki büyük düşüş genellikle kargo maliyetinin geç görünmesinden, ödeme adımındaki düşüş ise zorunlu üyelik veya sınırlı ödeme seçeneğinden kaynaklanır.

## 5. Çok Kanallı Yolculuk

Gerçek yolculuklar tek kanalda geçmez. İzlenmesi gerekenler: kanallar arası geçiş örüntüleri, cihaz değişimi noktaları, çevrimiçi-çevrimdışı geçişler ve destek temasının satın almaya etkisi.

Bu analiz için kimlik çözümlemesi ön koşuldur; aksi halde tek kişinin yolculuğu birden fazla kullanıcı gibi görünür ve yolculuk uzunluğu sistematik olarak eksik hesaplanır.

## 6. Öngörücü Sinyaller

Yolculuk verisi, dönüşüm olasılığını öngören davranışları ortaya çıkarır. Sık rastlanan örnekler: belirli sayıda ürün karşılaştırması, fiyat/teslimat sayfasının görüntülenmesi, ikinci oturumda geri dönüş, kaydedilmiş favori oluşturma.

Bu sinyaller iki şekilde kullanılır: yüksek olasılıklı kullanıcılara doğru zamanda destek/teşvik sunmak ve düşük olasılıklı segmente gereksiz maliyet harcamamak.

## 7. Ölçüm Altyapısı

- tutarlı olay şeması ve veri katmanı,
- kullanıcı/oturum kimliklerinin doğru bağlanması,
- aşamaların açıkça olaylarla eşleştirilmesi,
- çevrimdışı temasların veri modeline dahil edilmesi,
- ham olay verisine erişim (esnek yol analizi için),
- rıza durumunun analize yansıtılması.

Ham olay verisine erişim olmadan yol analizi, hazır rapor şablonlarının sınırında kalır.

## 8. İyileştirme Döngüsü

1. huni verisinden en büyük kaybın olduğu adımı belirlemek,
2. nedeni destekleyici sinyallerle daraltmak,
3. hipotez yazmak ("kargo bedeli sepette görünürse ödeme başlangıcı artar"),
4. değişikliği kontrollü test etmek,
5. sonucu birincil metrikle değerlendirmek,
6. kazanan değişikliği kalıcılaştırmak ve sonraki darboğaza geçmek.

Aynı anda birçok değişiklik yapmak, hangisinin işe yaradığını öğrenmeyi imkânsız kılar.

## 9. Raporlama İlkeleri

- yolculuk raporu adım bazlı geçiş oranıyla sunulur,
- segment kırılımı olmadan tek huni yanıltıcıdır (mobil/masaüstü ayrı bakılmalı),
- mutlak sayı ve oran birlikte gösterilir,
- karşılaştırma dönemi belirtilir,
- ölçülemeyen aşamalar açıkça işaretlenir.

## 10. Sık Yapılan Hatalar

- aşamaları ölçüm imkânına göre değil varsayıma göre tanımlamak,
- tek bir ortalama huniye bakıp segment farklarını kaçırmak,
- kimlik çözümlemesi olmadan çok kanallı yolculuk analizi yapmak,
- sürtünme nedenini araştırmadan tasarım değiştirmek,
- yalnızca dönüşen yolları incelemek (dönüşmeyen yollar daha öğreticidir),
- teslimat sonrası aşamayı analiz dışında bırakmak.

## Sık Sorulan Sorular

**Hangi araç gerekir?** Olay tabanlı analitik ve keşif/huni yetenekleri yeterlidir. Derin analiz için ham veri ambarı erişimi değer katar.

**Kaç adımlı huni kurulmalı?** Karar için gereken en az adım. Çok detaylı huniler okunmaz hâle gelir; 5-7 adım çoğu durumda yeterlidir.

**Nereden başlanmalı?** En yüksek iş değeri taşıyan tek akış (satın alma veya teklif talebi). Bu akış netleştikten sonra diğerleri eklenir.
