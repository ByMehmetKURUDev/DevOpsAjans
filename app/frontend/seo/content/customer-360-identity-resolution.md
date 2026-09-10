---
title: "Customer 360 ve Kimlik Çözümleme (Identity Resolution)"
description: "Customer 360 nedir ve kimlik çözümleme nasıl yapılır? Deterministik ve olasılıksal eşleme, kimlik grafiği, veri kalitesi, gizlilik sınırları ve uygulama adımları."
keywords: "Customer 360, kimlik çözümleme, identity resolution, müşteri birleştirme, kimlik grafiği, deterministik eşleme, tek müşteri görünümü"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Müşteri Verisi"
  - "Veri Mimarisi"
date: "2026-09-10"
lang: "tr"
og_title: "Customer 360 ve Kimlik Çözümleme"
og_description: "Tek müşteri görünümü kurmanın teknik ve organizasyonel adımları."
og_type: "article"
twitter_card: "summary"
twitter_title: "Customer 360 ve Kimlik Çözümleme"
twitter_description: "Kimlik grafiği ve müşteri birleştirme yöntemleri."
---
Aynı kişi, sitede misafir olarak sipariş verir, mobil uygulamada üye girişi yapar, çağrı merkezini arar ve e-posta kampanyasına tıklar. Bu dört temas, veri sisteminde dört farklı kayıt olarak durur. Customer 360, bu parçaları tek bir müşteri görünümünde birleştirme çalışmasıdır; kimlik çözümleme ise bu birleştirmenin teknik yöntemidir.

## 1. Neden Gerekli?

Kimlik çözümlemesi olmadan:

- müşteri sayısı olduğundan yüksek görünür,
- LTV sistematik olarak düşük hesaplanır,
- aynı kişiye çelişkili mesajlar gönderilir,
- yeni müşteri edinme maliyeti yanlış hesaplanır,
- mevcut müşteriye "yeni müşteri indirimi" gösterilir,
- destek ekibi müşterinin geçmişini göremez.

Bunlar yalnızca raporlama sorunu değildir; doğrudan pazarlama verimliliğini ve müşteri deneyimini bozar.

## 2. Kimlik Türleri

| Tür | Örnek | Kalıcılık |
|---|---|---|
| Kalıcı kimlik | Müşteri numarası, üyelik kimliği | Yüksek |
| İletişim kimliği | E-posta, telefon | Orta-yüksek |
| Cihaz kimliği | Tarayıcı tanımlayıcısı, uygulama kimliği | Düşük-orta |
| Oturum kimliği | Ziyaret tanımlayıcısı | Çok düşük |
| İş kimliği | Sipariş numarası, fatura numarası | Kayıt bazlı |

Sağlam bir mimari, düşük kalıcılıklı kimlikleri yüksek kalıcılıklı kimliğe bağlama noktalarını (giriş, sipariş, form gönderimi) bilinçli olarak tasarlar.

## 3. Deterministik Eşleme

Kesin tanımlayıcı üzerinden yapılan eşlemedir: aynı e-posta, aynı telefon, aynı müşteri numarası.

**Güçlü yönü:** Yüksek doğruluk, açıklanabilirlik, denetlenebilirlik.
**Sınırı:** Kimlik bilgisi bulunmayan temasları birleştiremez (misafir ziyaretler).

Uygulama için normalizasyon şarttır: e-posta küçük harfe çevrilir ve nokta/etiket varyasyonları normalize edilir, telefon uluslararası biçime dönüştürülür, ad-soyad alanları boşluk ve büyük-küçük harf açısından standartlaştırılır.

Normalizasyon yapılmadan deterministik eşleme bile başarısız olur; "Ahmet@Ornek.COM" ile "ahmet@ornek.com" ayrı kişi sayılır.

## 4. Olasılıksal Eşleme

Kesin tanımlayıcı yokken, davranışsal ve bağlamsal sinyallerin benzerliğine dayanarak yapılan tahmini eşlemedir: benzer cihaz özellikleri, ortak ağ, zaman örüntüsü, adres benzerliği.

**Güçlü yönü:** Kapsamı genişletir.
**Riski:** Yanlış birleştirme, iki farklı kişinin verisini karıştırır. Bu, gizlilik açısından ciddi bir hatadır.

**Pratik yaklaşım:** Olasılıksal eşleme yalnızca analitik ve segmentasyon amaçlı kullanılmalı; kişiselleştirilmiş iletişim, fiyatlandırma veya hassas veri erişimi kararlarında yalnızca deterministik eşleme esas alınmalıdır.

## 5. Kimlik Grafiği

Kimlikler arasındaki bağlantıları tutan yapıdır. Her düğüm bir kimlik, her kenar bir gözlemlenmiş bağlantıdır.

İyi tasarlanmış grafik şunları tutar:

- bağlantının hangi olayla kurulduğu,
- bağlantının zaman damgası,
- bağlantının güven skoru,
- bağlantının kaynağı (sistem/kanal).

Bu meta veri kritik önemdedir: yanlış birleştirme tespit edildiğinde geri alınabilmesi ve denetim sorularının yanıtlanabilmesi için gerekir.

## 6. Birleştirme Kuralları

Çakışma durumlarında karar kuralları önceden yazılmalıdır:

- hangi kaynak sistemin verisi öncelikli (genellikle işlem sistemi),
- çakışan ad/adres bilgisinde en güncel mi en çok doğrulanmış mı seçilecek,
- iki profil birleştiğinde tercih ve rıza kayıtları nasıl birleşecek,
- rıza konusunda en kısıtlayıcı kayıt esas alınır (güvenli varsayılan),
- yanlış birleşme tespit edildiğinde ayırma (unmerge) süreci nasıl işleyecek.

Rıza birleştirmesinde en kısıtlayıcıyı seçmek yalnızca uyum gereği değil, marka güveni açısından da doğru varsayılandır.

## 7. Veri Kalitesi Ön Koşulu

Kimlik çözümlemesi, girdi kalitesinden daha iyi sonuç üretemez. Ön çalışma:

- kaynak sistemlerde zorunlu alan disiplininin sağlanması,
- yazım hatası ve biçim sorunlarının temizlenmesi,
- test ve iç kullanıcı kayıtlarının işaretlenmesi,
- kurumsal müşterilerde kişi/şirket ayrımının netleştirilmesi,
- paylaşılan e-posta adreslerinin (info@, satis@) özel olarak ele alınması.

Paylaşılan adresler, olasılıksal eşlemede en sık yanlış birleştirme kaynağıdır.

## 8. Gizlilik Sınırları

Customer 360, gizlilik açısından yüksek riskli bir çalışmadır:

- yalnızca tanımlanmış iş amacı için gerekli veri birleştirilir,
- hassas veri kategorileri ayrı erişim kontrolüyle korunur,
- veri saklama süreleri tanımlanır ve uygulanır,
- silme talebi geldiğinde tüm bağlı kayıtların silinebilmesi sağlanır,
- rıza durumu profil düzeyinde izlenir ve aktivasyonda uygulanır,
- birleştirme kararları denetlenebilir biçimde kaydedilir.

Silme talebini karşılayamayan bir Customer 360 mimarisi, uyum açısından kabul edilemez.

## 9. Uygulama Sırası

1. iş amacını netleştirmek (hangi karar iyileşecek),
2. kaynak sistemleri ve içerdikleri kimlikleri envanterlemek,
3. normalizasyon kurallarını yazmak,
4. deterministik eşleme ile başlamak,
5. kimlik grafiğini meta veriyle birlikte kurmak,
6. birleştirme ve çakışma kurallarını uygulamak,
7. kalite ölçümlerini kurmak (eşleşme oranı, yanlış birleştirme şüphesi),
8. aktivasyon senaryolarını rıza kontrolüyle bağlamak,
9. gerekliyse sınırlı kapsamda olasılıksal eşleme eklemek.

Tek adımda mükemmel çözüm hedeflemek yerine, en yüksek değerli tek senaryodan başlamak (örneğin sipariş geçmişini web davranışıyla birleştirmek) çok daha yüksek başarı oranı verir.

## 10. Başarı Ölçütleri

- kimliklendirilmiş temas oranının artması,
- birleştirilmiş profil sayısının kaynak kayıt sayısına oranı,
- yinelenen profil oranının düşmesi,
- yanlış birleştirme şikayeti sayısı,
- LTV ve elde tutma metriklerinin daha tutarlı hâle gelmesi,
- kişiselleştirme senaryolarında ulaşılabilir kitle büyüklüğü.

## Sık Sorulan Sorular

**Özel bir platform şart mı?** Şart değil. Veri ambarı üzerinde iyi tanımlanmış eşleme mantığıyla anlamlı bir Customer 360 kurulabilir. Platform, ölçek ve gerçek zamanlı aktivasyon ihtiyacı doğduğunda değer katar.

**Misafir siparişleri birleştirilebilir mi?** E-posta veya telefon toplanıyorsa evet. Hiç iletişim bilgisi yoksa yalnızca sınırlı ve dikkatli olasılıksal yaklaşımlar kalır.

**Ne kadar sürer?** İlk anlamlı sonuç (iki ana kaynağın birleştirilmesi) genellikle haftalar içinde alınır. Kapsamlı bir Customer 360 ise süregelen bir programdır, tek seferlik proje değildir.
