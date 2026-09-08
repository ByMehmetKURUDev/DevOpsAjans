---
title: "Müşteri Yaşam Boyu Değeri (LTV) Nasıl Hesaplanır?"
description: "Müşteri yaşam boyu değeri (LTV) hesaplama yöntemleri: kohort tabanlı yaklaşım, marj odaklı hesap, tahmin modelleri, segment bazlı LTV ve pazarlama kararlarında kullanımı."
keywords: "LTV hesaplama, müşteri yaşam boyu değeri, CLV, kohort analizi, elde tutma, segment bazlı LTV, tahminsel LTV"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Müşteri Analitiği"
  - "Kârlılık"
date: "2026-09-09"
lang: "tr"
og_title: "Müşteri Yaşam Boyu Değeri (LTV)"
og_description: "LTV'yi doğru hesaplamak ve pazarlama kararlarında kullanmak."
og_type: "article"
twitter_card: "summary"
twitter_title: "Müşteri Yaşam Boyu Değeri"
twitter_description: "Kohort tabanlı ve marj odaklı LTV hesaplaması."
---

# Müşteri Yaşam Boyu Değeri (LTV) Nasıl Hesaplanır?

LTV, bir müşterinin ilişki süresi boyunca ürettiği net değeri ifade eder. Doğru hesaplandığında müşteri edinme bütçesinin üst sınırını, segment önceliklerini ve ürün yatırım kararlarını belirler. Yanlış hesaplandığında sürdürülemez pazarlama harcamasını meşrulaştıran bir rakama dönüşür.

## 1. Basit Formül ve Sınırları

**Temel hesap:** Ortalama sipariş kârı × yıllık sipariş sıklığı × müşteri ömrü (yıl).

Bu hesap hızlı bir büyüklük fikri verir ancak ciddi sınırları vardır:

- "müşteri ömrü" çoğu işletmede gözlemlenmiş bir veri değil, tahmindir,
- ortalama kullanmak, segmentler arasındaki büyük farkları gizler,
- gelecekteki nakit akışını bugünkü değere indirgemez,
- yeni işletmelerde yeterli geçmiş veri yoktur.

Bu nedenle karar amaçlı LTV, kohort tabanlı ölçülmelidir.

## 2. Kohort Tabanlı Yaklaşım (Önerilen)

Yöntem: müşterileri ilk satın alma ayına göre gruplayın ve her grubun kümülatif katkısını aylar boyunca izleyin.

| Kohort | 1. ay | 3. ay | 6. ay | 12. ay |
|---|---|---|---|---|
| Ocak | 100 | 145 | 190 | 240 |
| Şubat | 105 | 150 | 200 | — |
| Mart | 98 | 140 | 185 | — |

(Değerler müşteri başına kümülatif brüt kâr temsilidir.)

Bu tablo üç şeyi birlikte gösterir: mevcut doğrulanmış değer, değerin büyüme hızı ve kohortlar arası kalite değişimi.

**Avantajı:** Tahmine dayanmaz; gerçekleşmiş veriyi gösterir. Karar için "12 aylık müşteri değeri" gibi net bir pencere kullanılabilir.

## 3. Gelir Değil Kâr

LTV gelir üzerinden hesaplandığında yanıltıcıdır. Düşülmesi gerekenler: ürün maliyeti, kargo ve lojistik, ödeme komisyonu, iade ve iptal maliyeti, müşteri destek maliyeti ve varsa abonelik hizmet maliyeti.

Brüt kâr üzerinden hesaplanan LTV, pazarlama bütçesi kararı için tek geçerli tabandır.

## 4. Pencere Seçimi

"Yaşam boyu" ifadesi pratik değildir. Karar için sınırlı pencere kullanılır:

- **3 aylık LTV:** hızlı geri dönüş gerektiren nakit hassas işletmeler,
- **12 aylık LTV:** çoğu e-ticaret ve hizmet işletmesi için standart,
- **24 aylık LTV:** abonelik ve yüksek elde tutmalı modeller.

Pencere, işletmenin nakit akışı dayanıklılığıyla uyumlu seçilmelidir. Uzun pencere yüksek LTV gösterir ama nakdi bugün gerektirmez.

## 5. Segment Bazlı LTV

Tek bir ortalama LTV, kararların çoğu için yetersizdir. Anlamlı kırılımlar:

- edinme kanalı (organik, arama reklamı, sosyal, yönlendirme),
- ilk satın alınan ürün/kategori,
- ilk sipariş tutarı aralığı,
- coğrafya,
- cihaz,
- indirimle mi tam fiyatla mı kazanıldığı.

Sık görülen bulgu: ağır indirimle kazanılan müşterilerin LTV'si belirgin biçimde düşüktür. Bu bulgu, kampanya stratejisini doğrudan değiştirir.

Kanal bazlı LTV, bütçe dağıtımının en değerli girdisidir: pahalı görünen bir kanal, yüksek LTV üretiyorsa aslında en kârlı kanaldır.

## 6. Elde Tutma Bağlantısı

LTV, elde tutmanın sonucudur. LTV'yi artırmanın yolları:

- ikinci siparişe geçiş oranını iyileştirmek (en yüksek etkili müdahale),
- sipariş sıklığını artırmak,
- sepet büyüklüğünü ve çapraz satışı geliştirmek,
- kayıp müşteriyi geri kazanma akışları kurmak,
- yüksek marjlı ürünlere yönlendirmek,
- hizmet kalitesiyle iptal/iade oranını düşürmek.

İlk siparişten ikinciye geçiş oranı, LTV üzerindeki en belirleyici tek metriktir.

## 7. Tahminsel LTV

Geçmiş veriye dayanarak gelecekteki değeri tahmin eden modeller, edinme anında karar vermeyi mümkün kılar. Girdi olarak kullanılan sinyaller: ilk sipariş tutarı ve kategorisi, edinme kanalı, ilk günlerdeki etkileşim davranışı, coğrafya ve ödeme yöntemi.

Uygulama uyarıları:

- model tahminidir; kesin gelir taahhüdü değildir,
- tahminlerin gerçekleşenle karşılaştırılıp düzenli kalibre edilmesi gerekir,
- aşırı iyimser tahmin, yüksek edinme maliyetini haklı gösterip zarara yol açar,
- basit segment ortalamaları çoğu işletmede karmaşık modele yakın fayda sağlar.

## 8. Karar Kullanımı

| Karar | LTV'nin rolü |
|---|---|
| Maksimum CAC belirleme | Hedef LTV/CAC oranıyla üst sınır hesaplanır |
| Kanal bütçe dağıtımı | Kanal bazlı LTV/CAC karşılaştırması |
| İndirim politikası | İndirimle gelen müşterinin LTV etkisi |
| Sadakat programı yatırımı | Elde tutma iyileşmesinin LTV etkisi |
| Segment önceliklendirme | Yüksek LTV segmentlerine odaklanma |
| Ürün geliştirme | Hangi ilk ürünün daha değerli müşteri getirdiği |

**Sağlıklı referans:** LTV/CAC oranının 3 civarında olması ve CAC geri ödeme süresinin nakit döngüsüne uygun kalması.

## 9. Veri Altyapısı Gereksinimleri

LTV hesabı için gerekli olanlar: müşteri bazlı sipariş geçmişinin birleştirilebilmesi, yeni/mevcut müşteri ayrımı, ürün maliyet verisinin erişilebilirliği, iade ve iptal verisinin geri beslenmesi, edinme kanalının müşteri kaydına yazılması ve kimlik çözümlemesinin (aynı kişinin farklı siparişlerinin birleştirilmesi) yapılabilmesi.

Kimlik çözümlemesi eksikse LTV sistematik olarak düşük hesaplanır.

## 10. Sık Yapılan Hatalar

- gelir üzerinden hesaplayıp kâr sanmak,
- iade oranını hesaba katmamak,
- tek ortalamayla tüm kararları vermek,
- "yaşam boyu" tanımını sınırsız kabul etmek,
- tahminsel LTV'yi doğrulamadan bütçe gerekçesi yapmak,
- misafir siparişleri nedeniyle aynı müşteriyi birden fazla saymak,
- geri ödeme süresini göz ardı etmek.

## Sık Sorulan Sorular

**Yeni işletmede LTV nasıl hesaplanır?** Yeterli geçmiş yoksa kısa pencereyle (3 ay) başlanır ve veri biriktikçe genişletilir. Sektör ortalamaları yalnızca kaba referanstır.

**LTV ne sıklıkla güncellenmeli?** Kohort tablosu aylık güncellenmeli; karar eşikleri (maksimum CAC) çeyreklik gözden geçirilmelidir.

**Abonelik modelinde farkı ne?** Elde tutma ve iptal oranı doğrudan ölçülebildiği için LTV daha güvenilir hesaplanır; iptal oranı temel girdi olur.
