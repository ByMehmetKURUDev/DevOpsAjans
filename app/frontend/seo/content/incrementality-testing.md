---
title: "Artımsallık Testi (Incrementality Testing) Nasıl Yapılır?"
description: "Artımsallık testi nedir ve nasıl kurgulanır? Coğrafi bölme, kitle bölme, kanal duraklatma testleri, örneklem büyüklüğü, ölçüm süresi ve sonuç yorumlama."
keywords: "artımsallık testi, incrementality, geo test, holdout grubu, kanal duraklatma, gerçek katkı ölçümü, deneysel tasarım"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Deney"
  - "Ölçüm"
date: "2026-09-14"
lang: "tr"
og_title: "Artımsallık Testi"
og_description: "Reklamın gerçek katkısını deneyle ölçmek."
og_type: "article"
twitter_card: "summary"
twitter_title: "Artımsallık Testi"
twitter_description: "Coğrafi ve kitle bölme testleriyle gerçek katkı ölçümü."
og_image: "https://mehmetkuru.dev/blog-covers/incrementality-testing.webp"
og_image_alt: "Artımsallık Testi (Incrementality Testing) Nasıl Yapılır?"
---
İlişkilendirme raporları bir kanalın kaç dönüşümde göründüğünü söyler. Ancak iş kararının gerçek sorusu şudur: bu harcamayı kesersem bu satışların kaçını kaybederim? Artımsallık testi, bu soruya deneyle yanıt veren tek yöntemdir.

## 1. Neden Gerekli?

Reklam raporunda "1.000 dönüşüm" görünmesi, bu 1.000 satışın reklam sayesinde gerçekleştiği anlamına gelmez. Bir bölümü, reklam olmasa da gerçekleşecekti:

- markayı zaten arayan müşteriler,
- e-posta veya doğrudan kanalla gelecek olanlar,
- organik sonuçtan bulacak olanlar,
- tekrar satın alacak mevcut müşteriler.

Bu paya **yamyamlık (cannibalization)** denir ve özellikle marka kampanyalarında yüksektir. Artımsallık testi, gerçek net katkıyı ayırır.

## 2. Temel Mantık

Deneyin özü basittir: benzer iki grup oluşturulur, birine reklam gösterilir, diğerine gösterilmez, sonuç farkı ölçülür.

**Artımsal dönüşüm** = test grubu dönüşümü − kontrol grubu dönüşümü (ölçek düzeltmesiyle).

**Artımsal EBM** = harcama / artımsal dönüşüm.

Artımsal EBM, platformun bildirdiği EBM'den genellikle belirgin biçimde yüksektir. Gerçek karar metriği budur.

## 3. Test Tasarımları

**Coğrafi bölme (geo test).** Benzer şehir/bölgeler iki gruba ayrılır; bir gruba reklam yayınlanır, diğerinde durdurulur.

- Avantajı: platform bağımsız, çevrimdışı satışı da kapsar, uygulaması nispeten kolay.
- Dikkat: bölgelerin geçmiş satış eğiliminin benzer olması, bölgeler arası taşma etkisinin (medya kapsamı) düşük olması gerekir.

**Kitle bölme (holdout).** Hedef kitlenin bir bölümü reklamdan sistematik olarak dışlanır.

- Avantajı: aynı pazarda, aynı dönemde karşılaştırma.
- Dikkat: dışlama kuralının gerçekten uygulandığı doğrulanmalı; kullanıcı diğer kanallardan aynı mesajı almamalı.

**Kanal duraklatma (on/off).** Kanal belirli bir süre tamamen durdurulur ve sonrasında karşılaştırılır.

- Avantajı: en basit yöntem.
- Dikkat: mevsimsellik ve dış etkiler sonucu bozar; en zayıf kanıt düzeyini üretir. Yine de hiç test yapmamaktan iyidir.

**Zamanlı bölme (dönüşümlü açma-kapama).** Aynı bölgede dönemsel olarak açılıp kapatılır; mevsimsellik etkisini kısmen dengeler.

## 4. Kurgu Adımları

1. **Hipotez yazmak.** "X kanalını durdurursak toplam satışın en fazla %Y'sini kaybederiz."
2. **Birincil metriği seçmek.** Toplam satış veya toplam brüt kâr — kanal içi dönüşüm değil.
3. **Grupları oluşturmak.** Geçmiş veriye göre dengeli bölme yapmak.
4. **Ön dönem doğrulaması.** Test öncesinde iki grubun eğiliminin benzer olduğunu göstermek (bu adım atlanırsa sonuç tartışmalı olur).
5. **Süre belirlemek.** Satın alma döngüsünü kapsayacak kadar uzun; genellikle en az 3-4 hafta.
6. **Test sırasında müdahale etmemek.** Bütçe, teklif, kreatif ve site değişikliği yapılmamalı.
7. **Sonucu değerlendirmek.** Fark ve belirsizlik aralığı birlikte raporlanır.

## 5. Örneklem ve Güç

Küçük etkileri ölçmek büyük örneklem gerektirir. Test kurgulanmadan önce sorulmalıdır: mevcut hacimle en az hangi büyüklükte bir etki tespit edilebilir?

Eğer hacim, beklenen etkiyi tespit etmeye yetmiyorsa test yapılmamalıdır — sonuç "etki yok" gibi görünür ve yanlış karar üretir. Bu durumda daha büyük bir kanal veya daha uzun süre seçilmelidir.

## 6. Sonuç Yorumlama

- fark, belirsizlik aralığıyla birlikte okunur,
- tek testten kesin genelleme yapılmaz,
- sonuç o dönem, o kreatif ve o bütçe seviyesi için geçerlidir,
- doygunluk etkisi vardır: bütçe iki katına çıktığında artımsal katkı aynı oranda artmaz,
- negatif sonuç da değerlidir; kesilmesi gereken harcamayı gösterir.

**Yaygın bulgu:** Marka aramalarında artımsallık genellikle düşüktür; jenerik keşif kampanyalarında ve yeni müşteri segmentinde daha yüksektir. Bu bulgu bütçe dağıtımını doğrudan değiştirir.

## 7. Ölçüm Altyapısı

- toplam satış verisinin bölge/segment kırılımıyla erişilebilir olması,
- test ve kontrol gruplarının tanımının veri katmanında saklanması,
- çevrimdışı satışların dahil edilmesi,
- yeni/mevcut müşteri ayrımının yapılabilmesi,
- test dönemlerinin raporlarda işaretlenmesi.

## 8. Test Programı Kurmak

Tek seferlik test sınırlı değer üretir. Sürdürülebilir yaklaşım:

- yılda birkaç kez, en büyük harcama kalemlerinde test yapmak,
- her testin hipotez, tasarım ve sonucunu belgelemek,
- sonuçları ilişkilendirme modelinin kalibrasyonunda kullanmak,
- öğrenilenleri kanal bazlı düzeltme katsayılarına dönüştürmek,
- medya karması modellemesi varsa test sonuçlarıyla doğrulamak.

## 9. Sık Yapılan Hatalar

- ön dönem denge kontrolü yapmamak,
- test süresini satın alma döngüsünden kısa tutmak,
- test sırasında kampanyaya müdahale etmek,
- birincil metrik olarak kanal içi dönüşümü seçmek,
- yetersiz hacimle test yapıp "etki yok" sonucuna varmak,
- tek testin sonucunu her dönem için geçerli saymak,
- taşma etkisini (komşu bölgelerin aynı medyaya maruz kalması) göz ardı etmek.

## Sık Sorulan Sorular

**Küçük bütçeyle yapılabilir mi?** Hacim düşükse istatistiksel güç yetersiz kalır. Bu durumda basit kanal duraklatma testi yön verebilir, ancak kesin sonuç beklenmemelidir.

**Sonuçlar ne kadar geçerli kalır?** Pazar, rekabet ve kreatif değiştiğinde geçerlilik azalır. Kritik kanallar için yıllık tekrar önerilir.

**İlişkilendirmenin yerini alır mı?** Almaz. İlişkilendirme günlük yön verir, artımsallık testi bütçe kararını doğrular. İkisi birlikte kullanılır.
