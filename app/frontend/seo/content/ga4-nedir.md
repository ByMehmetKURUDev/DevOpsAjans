---
title: "GA4 Nedir? Google Analytics 4'e Geçiş ve Olay Tabanlı Ölçüm"
description: "GA4 nedir ve Universal Analytics'ten farkı nedir? Olay tabanlı veri modeli, temel raporlar, dönüşüm tanımı, kitleler, BigQuery aktarımı ve doğru kurulum adımları."
keywords: "GA4 nedir, Google Analytics 4, olay tabanlı ölçüm, GA4 dönüşüm, GA4 kurulumu, keşif raporları, BigQuery aktarımı"
category: "Reklam"
tags:
  - "Reklam"
  - "Analitik"
  - "GA4"
date: "2026-07-22"
lang: "tr"
og_title: "GA4 Nedir?"
og_description: "Olay tabanlı veri modeli, raporlar ve doğru GA4 kurulumu."
og_type: "article"
twitter_card: "summary"
twitter_title: "GA4 Nedir?"
twitter_description: "Google Analytics 4'ün veri modeli ve kurulum mantığı."
---
Google Analytics 4, Google'ın mevcut analitik ürünüdür ve önceki sürümden yalnızca arayüz olarak değil, veri modeli olarak farklıdır. Bu farkı anlamadan yapılan kurulumlar, veri toplayan ama karar üretmeyen bir yapıyla sonuçlanır.

## 1. Temel Fark: Olay Tabanlı Model

Önceki sürümde veri "oturum" merkezliydi ve etkileşimler farklı türlere ayrılıyordu (sayfa görüntüleme, olay, e-ticaret, sosyal etkileşim). GA4'te **her etkileşim bir olaydır**. Sayfa görüntüleme de bir olaydır, buton tıklaması da, satın alma da.

Her olay, adı ve isteğe bağlı parametrelerinden oluşur. Bu model esneklik sağlar: yeni bir davranışı ölçmek için yeni bir olay tanımlamak yeterlidir. Ancak esneklik disiplinsizlikle birleştiğinde tutarsız isimlendirme ve kullanılamaz veri üretir.

## 2. Olay Kategorileri

**Otomatik toplanan olaylar.** Kurulum sonrası kendiliğinden gelir: ilk ziyaret, oturum başlangıcı, sayfa görüntüleme.

**Gelişmiş ölçüm olayları.** Ayarla açılabilen otomatik olaylar: kaydırma, giden bağlantı tıklaması, site içi arama, video etkileşimi, dosya indirme.

**Önerilen olaylar.** Google'ın standart isim ve parametrelerini tanımladığı olaylar. E-ticaret için özellikle önemlidir: `view_item`, `add_to_cart`, `begin_checkout`, `purchase`. Bu isimleri kullanmak, hazır raporların ve entegrasyonların çalışmasını sağlar.

**Özel olaylar.** İşe özgü davranışlar için tanımlanan olaylar.

**Kritik kural:** Önerilen bir olay adı varsa mutlaka o kullanılmalıdır. Kendi adınızı verirseniz (`urun_satin_alma` gibi) hazır e-ticaret raporları boş kalır.

## 3. Veri Modeli Kavramları

**Kullanıcı.** Cihaz/tanımlayıcı bazlı benzersiz ziyaretçi.

**Oturum.** Belirli bir zaman aralığındaki etkileşim grubu. GA4'te oturum tanımı önceki sürümden farklıdır; kampanya değişimi yeni oturum başlatmaz.

**Etkileşimli oturum.** 10 saniyeden uzun süren, dönüşüm içeren veya en az iki sayfa görüntülemesi olan oturum. "Hemen çıkma oranı" bunun tersidir.

**Kullanıcı özellikleri.** Kullanıcıya bağlı kalıcı nitelikler (üyelik seviyesi, dil tercihi gibi).

**Parametre.** Olaya bağlı bağlam bilgisi. Raporlarda kullanılabilmesi için özel boyut/metrik olarak kaydedilmelidir — bu adım sıkça atlanır ve parametreler görünmez kalır.

## 4. Dönüşüm Tanımı

GA4'te dönüşüm ayrı bir varlık değildir; bir olay "önemli olay" olarak işaretlenir. Doğru yaklaşım:

- gerçekten iş değeri taşıyan eylemleri işaretlemek (satın alma, teklif talebi, kayıt),
- mikro etkileşimleri (kaydırma, sayfa görüntüleme) dönüşüm olarak işaretlememek,
- e-ticarette `purchase` olayına gelir değeri ve para birimi göndermek,
- müşteri adayı formunda tekrarlanan gönderimleri filtrelemek.

Dönüşüm tanımı yanlışsa reklam tarafındaki otomatik teklif stratejileri de yanlış hedefe optimize eder. Bu, ölçüm hatalarının en pahalı sonucudur.

## 5. Raporlar

**Standart raporlar.** Edinme, etkileşim, para kazanma, elde tutma ve kullanıcı özellikleri başlıkları altında hazır görünümler.

**Keşif (Explore).** Serbest form tablolar, huni analizi, yol keşfi, segment örtüşmesi ve kohort analizi. Gerçek analiz burada yapılır.

**Huni analizi** özellikle değerlidir: hangi adımda kaybın yaşandığını görünür kılar. Örneğin sepete ekleme ile ödeme başlangıcı arasındaki büyük düşüş, kargo maliyeti şeffaflığı veya form karmaşıklığı sorununa işaret eder.

## 6. Kitleler ve Reklam Entegrasyonu

GA4'te tanımlanan kitleler Google Ads'e aktarılabilir ve yeniden pazarlama ile hedefleme için kullanılabilir. Yararlı kitle örnekleri: sepete ekleyip satın almayanlar, belirli bir kategoriyi inceleyenler, yüksek etkileşimli ama dönüşmeyen ziyaretçiler, mevcut müşteriler (dışlama için).

Kitleler geriye dönük çalışmaz; ihtiyaç duyulacak kitleler önceden tanımlanmalıdır.

## 7. Veri Kalitesi ve Yapılandırma

Kurulum sonrası mutlaka yapılması gerekenler:

- iç trafik (ofis IP'leri) ve geliştirme ortamının filtrelenmesi,
- istenmeyen yönlendirenlerin (ödeme sağlayıcısı gibi) hariç tutulması,
- kampanya bağlantılarında tutarlı UTM parametreleri kullanılması,
- veri saklama süresinin uzatılması,
- alan adları arası ölçüm gerekiyorsa yapılandırılması,
- Google Ads ve Search Console bağlantılarının kurulması,
- veri filtreleme ve iç arama parametrelerinin tanımlanması.

## 8. BigQuery Aktarımı

GA4'ün en güçlü yönlerinden biri, ham olay verisinin veri ambarına ücretsiz aktarılabilmesidir. Bu, arayüz sınırlarının ötesine geçmeyi sağlar: özel ilişkilendirme modelleri, CRM verisiyle birleştirme, kullanıcı düzeyinde derin analiz ve örnekleme sorunundan bağımsız raporlama.

Uzun vadeli veri stratejisi olan her kurumda bu aktarım ilk günden açılmalıdır; geriye dönük veri aktarılmaz.

## 9. Gizlilik ve Rıza Yönetimi

- rıza (consent) durumuna göre ölçüm davranışının yapılandırılması,
- kişisel verinin olay parametrelerine yazılmaması (e-posta, telefon, ad),
- IP ve tanımlayıcı işleme politikalarının belgelenmesi,
- rıza verilmediğinde modellenmiş veri davranışının anlaşılması.

Olay parametrelerine kişisel veri göndermek hem politika ihlalidir hem de veri silme talebi durumunda ciddi operasyonel yük yaratır.

## Sık Sorulan Sorular

**Etiket yöneticisi kullanmak zorunlu mu?** Zorunlu değil ama şiddetle önerilir. Olay yönetimini koddan ayırır, sürüm kontrolü ve önizleme imkânı verir.

**Veriler neden reklam platformuyla birebir aynı değil?** İlişkilendirme modelleri, dönüşüm zaman aralıkları ve tanımlar farklıdır. Küçük sapmalar normaldir; her platform kendi içinde tutarlı biçimde okunmalıdır.

**Eski verilerim ne olacak?** Önceki sürüm verisi GA4'e taşınamaz. Bu nedenle yıl karşılaştırmaları için eski verinin dışa aktarılıp arşivlenmesi gerekir.
