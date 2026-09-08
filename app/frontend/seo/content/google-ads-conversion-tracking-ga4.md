---
title: "Google Ads Dönüşüm İzleme: GA4 ile Doğru Kurulum"
description: "Google Ads dönüşüm izleme nasıl kurulur? GA4 önemli olay içe aktarımı, doğrudan Ads etiketi, gelişmiş dönüşümler, dönüşüm değeri, çift sayım önleme ve doğrulama adımları."
keywords: "Google Ads dönüşüm izleme, GA4 dönüşüm içe aktarma, gelişmiş dönüşümler, dönüşüm değeri, çift sayım, dönüşüm doğrulama"
category: "Reklam"
tags:
  - "Reklam"
  - "Google Ads"
  - "Ölçüm"
date: "2026-07-29"
lang: "tr"
og_title: "Google Ads Dönüşüm İzleme"
og_description: "GA4 ve Google Ads arasında doğru dönüşüm ölçümü kurulumu."
og_type: "article"
twitter_card: "summary"
twitter_title: "Google Ads Dönüşüm İzleme"
twitter_description: "Dönüşüm izleme kurulumu, değer sinyali ve doğrulama."
---

# Google Ads Dönüşüm İzleme: GA4 ile Doğru Kurulum

Dönüşüm izleme, reklam hesabının en kritik altyapısıdır. Yanlış kurulmuş bir dönüşüm yapısı, yalnızca raporları bozmakla kalmaz; otomatik teklif stratejilerini yanlış hedefe yönlendirdiği için doğrudan bütçe kaybına yol açar. Bu nedenle kampanya açmadan önce yapılması gereken iş budur.

## 1. İki Kurulum Yolu

**GA4'ten içe aktarma.** GA4'te "önemli olay" olarak işaretlenen olaylar Google Ads'e içe aktarılır.

- Avantajı: tek ölçüm kaynağı, tutarlı olay tanımları, tüm kanallar için ortak veri modeli.
- Dezavantajı: veri aktarımında gecikme olabilir, GA4 ilişkilendirme modeline bağımlılık.

**Doğrudan Google Ads etiketi.** Dönüşüm, Ads etiketiyle doğrudan ölçülür.

- Avantajı: daha hızlı veri, teklif algoritması için doğrudan sinyal.
- Dezavantajı: GA4 ile ayrışan tanımlar, ikinci bir bakım noktası.

**Pratik öneri:** Ana dönüşüm (satın alma, nitelikli müşteri adayı) için doğrudan Ads etiketi + GA4'te aynı olayın kendi amacı için ölçülmesi. Kritik olan, aynı dönüşümün Ads tarafında iki farklı yolla birlikte sayılmamasıdır.

## 2. Çift Sayım Nasıl Önlenir?

En sık görülen hata, aynı dönüşümün hem GA4 içe aktarımıyla hem doğrudan etiketle Ads'e gelmesi ve her ikisinin de "birincil" olarak işaretlenmesidir. Sonuç: dönüşüm sayısı iki katına çıkar, EBM yarıya düşmüş görünür, teklif algoritması gerçekte olmayan performansa göre agresifleşir.

Önlem:

- her dönüşüm eylemi için tek bir kaynak seçin,
- yedek olarak tutulan ölçümleri "ikincil" (yalnızca gözlem) olarak işaretleyin,
- teklif stratejisinin yalnızca birincil dönüşümleri kullandığını doğrulayın,
- dönüşüm eylemi listesini düzenli olarak gözden geçirip yinelenenleri kapatın.

## 3. Dönüşüm Değeri Göndermek

Dönüşüm sayısı yerine dönüşüm değeri optimize edildiğinde performans belirgin biçimde iyileşir. Uygulama:

- e-ticarette gerçek sipariş tutarı (KDV ve kargo politikası tutarlı biçimde) gönderilir,
- para birimi mutlaka belirtilir,
- müşteri adayı işlerinde her adayın aynı değeri taşımadığı kabul edilir: form türü, talep büyüklüğü veya kaynak segmentine göre farklı değerler atanabilir,
- iade oranı yüksek işlerde brüt yerine net değere yaklaşan bir tahmin kullanılır.

Değer sinyali olmadan "Hedef ROAS" stratejisi çalışmaz.

## 4. Gelişmiş Dönüşümler

Tarayıcı tanımlayıcılarının kısıtlandığı ortamlarda ölçüm kaybı yaşanır. Gelişmiş dönüşümler, dönüşüm anında toplanan iletişim bilgisinin karma (hash) hâlinde gönderilmesiyle eşleşme oranını artırır.

Uygulama notları: veri gönderilmeden önce karma alınır, yalnızca gerekli alanlar gönderilir, gizlilik bildirimi ve rıza yönetimi buna uygun güncellenir, veri kalitesi (boş/hatalı alan oranı) izlenir.

## 5. Çevrimdışı Dönüşümler

Satışın telefon veya saha görüşmesiyle tamamlandığı işlerde, web üzerindeki form gönderimi gerçek sonucu temsil etmez. Bu durumda:

1. form gönderiminde tıklama kimliği (GCLID) yakalanır ve CRM kaydına yazılır,
2. satış süreci CRM'de takip edilir,
3. kazanılan satışlar, tıklama kimliği ve gerçek gelirle birlikte Ads'e geri yüklenir.

Bu döngü kurulduğunda teklif algoritması "form dolduran" yerine "gerçekten satın alan" profili öğrenir. Müşteri adayı odaklı işlerde en yüksek etkili optimizasyon budur.

## 6. Dönüşüm Ayarları

| Ayar | Dikkat edilecek nokta |
|---|---|
| Sayma yöntemi | Satışta "her biri", müşteri adayında "bir kez" |
| Dönüşüm zaman aralığı | Satın alma döngüsü uzunsa genişletilir |
| İlişkilendirme modeli | Veri odaklı model çoğu hesapta uygundur |
| Teklife dahil etme | Yalnızca gerçek iş sonucu olan eylemler |
| Kategori | Doğru kategori raporlamayı netleştirir |

## 7. Doğrulama: Kurulum Bitti Demek İçin Ne Gerekir?

Kurulum, arayüzde "aktif" yazması ile bitmez. Yapılması gerekenler:

- etiket önizleme/hata ayıklama modunda gerçek bir dönüşüm akışı test edilir,
- test dönüşümünün doğru olay adı, değer ve para birimiyle geldiği görülür,
- dönüşüm eyleminin durumu birkaç gün sonra "kayıtlı dönüşüm var" olarak doğrulanır,
- Ads ve GA4 sayıları karşılaştırılıp sapmanın makul aralıkta olduğu görülür,
- test verisinin üretim raporlarını kirletmediği kontrol edilir,
- rıza durumuna göre ölçüm davranışı test edilir.

## 8. Sık Karşılaşılan Sorunlar

- teşekkür sayfası olmadığı için dönüşümün ölçülememesi (tek sayfa uygulamalarda olay tabanlı ölçüm gerekir),
- sayfa yenilenmesiyle dönüşümün tekrar sayılması,
- test siparişlerinin ve iç trafiğin filtrelenmemesi,
- para biriminin gönderilmemesi nedeniyle değerlerin yanlış yorumlanması,
- mikro dönüşümlerin teklife dahil edilmesi ve algoritmanın değersiz eylemlere optimize etmesi,
- rıza reddedildiğinde ölçümün tamamen kaybedilmesi,
- form doğrulama hatasında bile dönüşüm tetiklenmesi.

## Sık Sorulan Sorular

**Ads ve GA4 sayıları neden farklı?** İlişkilendirme modeli, zaman damgası (tıklama tarihi mi dönüşüm tarihi mi) ve dönüşüm penceresi farklıdır. Belirli bir sapma normaldir; iki katı fark ise kurulum hatasına işaret eder.

**Kaç dönüşüm eylemi tanımlanmalı?** Teklife dahil edilen 1-2 ana eylem yeterlidir. Diğerleri gözlem amacıyla ikincil olarak tutulur.

**Dönüşüm izleme sonradan kurulabilir mi?** Kurulabilir ama geçmiş veri geriye dönük oluşmaz. Kampanya başlatmadan önce kurulmalıdır.
