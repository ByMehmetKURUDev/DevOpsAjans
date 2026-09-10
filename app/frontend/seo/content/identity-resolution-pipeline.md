---
title: "Kimlik Çözümleme Boru Hattı: Uçtan Uca Mimari"
description: "Identity resolution pipeline nasıl kurulur? Normalizasyon, aday üretimi (blocking), eşleştirme skoru, küme kararlılığı, ayırma süreci ve izleme metrikleri."
keywords: "identity resolution pipeline, kimlik çözümleme mimarisi, blocking, aday üretimi, eşleştirme skoru, kimlik kümesi, unmerge, veri normalizasyonu"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Müşteri Verisi"
date: "2026-09-10"
lang: "tr"
og_title: "Kimlik Çözümleme Boru Hattı"
og_description: "Kimlik çözümlemenin mühendislik tarafı: katmanlar, ölçek ve geri alınabilirlik."
og_type: "article"
twitter_card: "summary"
twitter_title: "Kimlik Çözümleme Boru Hattı"
twitter_description: "Normalizasyondan küme kararlılığına kadar uçtan uca mimari."
og_image: "https://mehmetkuru.dev/blog-covers/identity-resolution-pipeline.webp"
og_image_alt: "Kimlik Çözümleme Boru Hattı: Uçtan Uca Mimari"
---
Kimlik çözümlemenin ne olduğu ve neden gerektiği ayrı bir konudur; bu yazı onun nasıl kurulduğuna bakıyor. İki milyon kayıt üzerinde her kaydı her kayıtla karşılaştırmak iki trilyon karşılaştırma demektir ve hiçbir sistemde çalışmaz. Boru hattının tasarımı, tam olarak bu ölçek probleminin ve geri alınabilirlik ihtiyacının etrafında şekillenir. Kavramsal çerçeve için [Customer 360 ve kimlik çözümleme](/blog/customer-360-identity-resolution/) yazısına bakabilirsiniz.

## 1. Katmanlar

| Katman | İşi | Çıktısı |
|---|---|---|
| Toplama | Kaynak sistemlerden ham kimlik kayıtlarını almak | Ham kayıt tablosu |
| Normalizasyon | Biçimleri standartlaştırmak | Karşılaştırılabilir kayıt |
| Aday üretimi | Karşılaştırılacak çiftleri daraltmak | Aday çiftler |
| Eşleştirme | Çiftleri skorlamak | Skorlu bağlantılar |
| Kümeleme | Bağlantılardan kimlik kümeleri oluşturmak | Birleşik profil |
| Yayın | Sonucu tüketicilere açmak | Profil tablosu, kimlik haritası |

Bu katmanların ayrı tutulması önemlidir: bir eşleştirme kuralı değiştiğinde yalnızca ilgili katman yeniden çalıştırılabilir.

## 2. Normalizasyon

Bu katman atlandığında sonraki her katman bozulur. Asgari kurallar:

- e-posta küçük harfe çevrilir, baştaki/sondaki boşluk atılır,
- telefon uluslararası biçime dönüştürülür, ülke kodu tamamlanır,
- ad ve soyad büyük-küçük harf ve boşluk açısından standartlaştırılır,
- Türkçe karakterler tutarlı biçimde ele alınır (aynı kaydın hem "İ" hem "I" ile gelmesi yaygındır),
- adres alanlarında kısaltmalar açılır (Mah., Cd., Sk.),
- boş yerine gelen dolgu değerleri (`-`, `bilinmiyor`, `test@test.com`) işaretlenir.

Son madde küçümsenmemelidir: aynı dolgu e-postasını taşıyan yüzlerce kayıt, tek bir devasa yanlış kümeye dönüşür.

## 3. Aday Üretimi (Blocking)

Ölçek problemi burada çözülür. Tüm kayıt çiftleri yerine, aynı "blok anahtarını" paylaşan kayıtlar karşılaştırılır.

Yaygın blok anahtarları:

- e-postanın alan adı + soyadın ilk üç harfi,
- telefonun son yedi hanesi,
- posta kodu + adın ilk harfi,
- ad-soyadın ses temelli kodu.

Tek bir blok anahtarı hem kaçırır hem şişirir; pratikte birkaç anahtar birlikte kullanılır ve aday kümeleri birleştirilir.

Denge şudur: dar blok hızlıdır ama eşleşmeleri kaçırır, geniş blok kapsayıcıdır ama maliyeti hızla büyür. Blok içindeki en büyük grubun boyutu izlenmelidir; binlerce kayıtlık tek bir blok, boru hattını tıkayan tipik sebeptir.

## 4. Eşleştirme ve Skorlama

Her aday çift için alan bazında benzerlik hesaplanır ve tek bir skora indirgenir.

- kesin eşleşen kalıcı kimlik (müşteri numarası) → en yüksek ağırlık,
- kesin eşleşen e-posta veya telefon → yüksek ağırlık,
- benzer ad-soyad → orta ağırlık, tek başına yetersiz,
- aynı adres → orta ağırlık, aile üyeleri nedeniyle riskli,
- aynı cihaz → düşük ağırlık, paylaşılan cihazlar nedeniyle riskli.

İki eşik tanımlanır: üst eşiğin üzerindekiler otomatik birleştirilir, alt eşiğin altındakiler reddedilir, arada kalanlar insan incelemesine gider. Ara bandı hiç tanımlamamak, ya çok fazla yanlış birleştirme ya da çok fazla kaçırma üretir.

## 5. Kümeleme ve Kararlılık

Bağlantılar ikili çiftlerdir; profil ise bir kümedir. A-B ve B-C bağlantısı varsa A-C de aynı kümededir. Bu geçişlilik, kontrol edilmezse zincirleme birleşmelere yol açar: zayıf bağlantılar üzerinden yüzlerce kayıt tek profilde toplanabilir.

Önlemler:

- küme büyüklüğüne üst sınır koymak ve aşanları incelemeye almak,
- zayıf bağlantıların geçişliliğe katılmasını engellemek,
- her kümeye kararlı bir kimlik vermek ve bu kimliği çalışmalar arasında korumak.

Son madde kritiktir. Küme kimliği her çalışmada yeniden üretilirse, aşağı akıştaki tüm sistemler her gece yeni müşteri görür; geçmiş analizler karşılaştırılamaz hâle gelir.

## 6. Ayırma (Unmerge)

Yanlış birleştirme kaçınılmazdır; boru hattı bunu geri alabilecek biçimde tasarlanmalıdır.

Bunun için her bağlantının hangi kanıtla kurulduğu saklanmalıdır: kaynak, kural, skor, zaman damgası. Ayırma talebi geldiğinde ilgili kanıt geçersizleştirilir ve küme yeniden hesaplanır.

Ayrıca bir "asla birleştirme" listesi tutulmalıdır: incelenip ayrı oldukları doğrulanmış çiftler, sonraki çalışmalarda yeniden birleşmemelidir. Bu liste olmadan aynı hata her gece tekrarlanır.

## 7. Tazelik: Toplu mu, Akış mı?

**Toplu (batch):** Gecelik tam veya artımsal hesaplama. Basit, denetlenebilir, çoğu senaryo için yeterli.

**Akış (streaming):** Yeni kimlik sinyali geldiğinde anında bağlama. Karmaşık; kümeleme kararlarının anlık verilmesi gerekir ve geri alma zorlaşır.

Yaygın ve sağlıklı yaklaşım karmadır: kümeler toplu işle hesaplanır, yeni gelen kayıtlar mevcut kümelere hafif bir kuralla anında bağlanır, tam yeniden hesaplama gece yapılır.

## 8. İzleme Metrikleri

- kimliklendirilmiş kayıt oranı,
- ortalama ve en büyük küme boyutu,
- ara banda düşen çift sayısı (insan incelemesi yükü),
- ayırma talebi sayısı,
- çalışma başına küme kimliği değişim oranı (kararlılık),
- blok içi en büyük grup boyutu (performans erken uyarısı).

Kararlılık metriği en önemlisidir: aniden yükselmesi, bir eşiğin veya kaynak verinin sessizce değiştiğini gösterir. Bu tür sessiz bozulmalar [veri sözleşmeleri](/blog/marketing-data-contracts/) ile büyük ölçüde önlenebilir.

## 9. Uygulama Sırası

1. iki kaynak sistemle sınırlı bir kapsam seçmek,
2. normalizasyon kurallarını yazıp test etmek,
3. yalnızca deterministik eşleme ile başlamak,
4. küme kimliğini kararlı üretmek,
5. blok anahtarlarını ekleyip ölçeği açmak,
6. skor eşiklerini ve ara bandı tanımlamak,
7. ayırma sürecini ve "asla birleştirme" listesini kurmak,
8. izleme metriklerini yerleştirmek,
9. ancak bundan sonra olasılıksal eşlemeyi değerlendirmek.

Dokuzuncu maddeyi başa almak, en sık görülen ve en pahalı tasarım hatasıdır.

## Sık Sorulan Sorular

**Boru hattı ne kadar sürede kurulur?** İki kaynakla sınırlı, deterministik bir ilk sürüm birkaç hafta içinde çalışır hâle gelebilir. Ara band incelemesi, ayırma süreci ve izleme ile birlikte olgun bir sürüm aylar alır.

**İnsan incelemesi şart mı?** Ara band tanımlandıysa evet. İnceleme yükü fazlaysa çözüm bandı daraltmak değil, normalizasyonu ve blok anahtarlarını iyileştirmektir; yük genellikle veri kalitesinden doğar.

**Kümeler neden zamanla büyüyor?** Genellikle dolgu değerleri veya paylaşılan iletişim bilgileri yüzünden. Küme boyutu üst sınırı ve büyüyen kümelerin düzenli incelenmesi, bu sorunu erken yakalar.
