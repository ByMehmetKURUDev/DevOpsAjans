---
title: "Veri Kökeni (Data Lineage) ve Etki Analizi"
description: "Data lineage nedir, etki analizi nasıl yapılır? Tablo ve sütun düzeyi köken, kök neden analizi, PII takibi, silme talepleri ve kurulum sırası."
keywords: "data lineage, veri kökeni, etki analizi, impact analysis, sütun düzeyi lineage, kök neden analizi, PII takibi, veri yönetişimi"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Veri Mimarisi"
  - "Data Governance"
date: "2026-09-10"
lang: "tr"
og_title: "Veri Kökeni ve Etki Analizi"
og_description: "Bir alanı değiştirmeden önce neyin bozulacağını görebilmek."
og_type: "article"
twitter_card: "summary"
twitter_title: "Veri Kökeni ve Etki Analizi"
twitter_description: "Lineage ile kök neden ve etki sorularını yanıtlamak."
og_image: "https://mehmetkuru.dev/blog-covers/data-lineage-impact-analysis.webp"
og_image_alt: "Veri Kökeni (Data Lineage) ve Etki Analizi"
---
Salı sabahı gelir raporu boş geliyor. Analist ambardaki tabloya bakar, tablo dolu. Ürün ekibi "biz bir şey değiştirmedik" der. Üç saat sonra, iki hafta önce bir alanın tipinin değiştiği ve o alanı kullanan ara tablonun sessizce boş üretmeye başladığı bulunur. Veri kökeni, bu üç saati üç dakikaya indiren şeydir.

## 1. Lineage Nedir?

Veri kökeni, bir verinin nereden geldiğini ve nereye gittiğini gösteren bağlantı haritasıdır. İki soruya cevap verir:

- **Yukarı doğru (kök neden):** Bu rapordaki sayı hangi tablolardan, hangi dönüşümlerden geçerek geldi?
- **Aşağı doğru (etki):** Bu alanı değiştirirsem hangi tablolar, panolar ve senkronizasyonlar etkilenir?

İkinci soru, günlük çalışmada daha sık gerekir ve neredeyse hiçbir ekipte cevaplanabilir durumda değildir.

## 2. Granülerlik: Tablo mu, Sütun mu?

| Düzey | Cevapladığı soru | Maliyeti |
|---|---|---|
| Tablo düzeyi | Bu tablo hangi tablolardan besleniyor? | Düşük |
| Sütun düzeyi | Bu alan hangi alandan türüyor? | Orta-yüksek |
| Rapor düzeyi | Bu pano hangi alanları kullanıyor? | Orta |

Tablo düzeyi lineage kurmak kolaydır ama "hangi rapor bozulur" sorusuna cevap vermez: tablo aynı kalırken tek bir sütun bozulmuş olabilir. Pratik yaklaşım, kritik alanlarda sütun düzeyine inmek, gerisinde tablo düzeyiyle yetinmektir.

## 3. Nasıl Toplanır?

Üç yöntem vardır ve genellikle birlikte kullanılır:

**Sorgu ayrıştırma:** Dönüşüm sorguları ayrıştırılarak hangi alanın hangi alandan türediği çıkarılır. En doğru yöntemdir, SQL dışındaki dönüşümleri kaçırır.

**Çalışma zamanı kaydı:** İşler çalışırken hangi tabloyu okuduğu ve yazdığı kaydedilir. Gerçek kullanımı gösterir, alan düzeyine inmez.

**Elle tanımlama:** Kaynak sistemler ve dış araçlar için tanım yazılır. Bakımı zordur ama başka yolu yoktur.

Rapor katmanı çoğu ekipte en zayıf halkadır: panoların hangi alanları kullandığı genellikle hiçbir yerde kayıtlı değildir. Oysa kullanıcının fark ettiği bozulma tam olarak orada olur.

## 4. Etki Analizi Kullanımları

- bir alanı değiştirmeden önce etkilenecek varlıkları listelemek,
- [veri sözleşmesindeki](/blog/marketing-data-contracts/) kırıcı değişiklik için tüketici listesi çıkarmak,
- kullanılmayan tabloları tespit edip kaldırmak,
- bir kaynak sistem kapatılırken bağımlılıkları görmek,
- maliyet analizinde hangi tablonun kimin için üretildiğini bilmek.

Kullanılmayan varlıkların tespiti çoğu ekipte doğrudan maliyet düşürür: hiçbir raporun beslenmediği ağır dönüşümler her gece çalışmaya devam eder.

## 5. Kök Neden Analizi

Bir sayı yanlış göründüğünde izlenecek yol:

1. raporun beslendiği son tabloyu bulmak,
2. o tablonun son çalışma zamanına ve kayıt sayısına bakmak,
3. yukarı doğru ilerleyip ilk anormal adımı tespit etmek,
4. o adımdaki dönüşümün son değişiklik tarihini kontrol etmek,
5. aynı dönemde kaynak sistemde değişiklik olup olmadığına bakmak.

Lineage olmadan bu beş adım tahminle yürür ve genellikle en gürültülü kişinin hipotezinden başlanır. Lineage ile aynı yol dakikalar sürer ve kanıta dayanır.

## 6. Gizlilik: PII Nereye Yayıldı?

Lineage'ın en az konuşulan ama en kritik kullanımı budur. Kişisel veri içeren bir alan, dönüşümler boyunca kopyalanır ve genellikle kimse nereye ulaştığını bilmez.

Gerekli olanlar:

- kaynak alanların gizlilik sınıfının işaretlenmesi,
- bu sınıfın türetilen alanlara taşınması,
- hassas alan içeren varlıkların listelenebilmesi,
- dışa aktarım noktalarının (senkronizasyon, rapor paylaşımı) görünür olması.

Bu yapı olmadan silme talebine "sildik" cevabı verilemez; yalnızca "bildiğimiz yerlerden sildik" denebilir. [Veri sınıflandırma ve PII yönetimi](/blog/data-classification-pii-management/) çalışması lineage'a bağlanmadığında eksik kalır.

## 7. Kalite Kapılarıyla Birlikte

Lineage tek başına pasiftir; haritayı gösterir, olayı engellemez. Değeri kalite kontrolleriyle birleştiğinde ortaya çıkar:

- bir tabloda kalite testi başarısız olduğunda, aşağı akıştaki panolar otomatik "güvenilmez" işaretlenir,
- bozuk veriyi kullanan senkronizasyonlar durdurulur,
- etkilenen tüketicilere bildirim gider.

Bu birleşim, kullanıcının yanlış sayıyı görmeden önce uyarılmasını sağlar — [gözlemlenebilirlik](/blog/marketing-data-quality-observability/) çalışmasının asıl hedefi budur.

## 8. Kurulum Sırası

1. en kritik 5-10 raporu belirlemek,
2. bu raporların beslendiği zinciri elle çıkarmak,
3. dönüşüm katmanında otomatik lineage toplamayı açmak,
4. rapor katmanının bağımlılıklarını kaydetmek,
5. gizlilik sınıfını kaynak alanlara işaretlemek,
6. etki analizini değişiklik sürecinin zorunlu adımı yapmak,
7. kalite testleriyle bağlamak.

İkinci madde küçümsenmemelidir: kritik zinciri elle çıkarmak, otomatik araç kurulmadan önce en yaygın kırılganlıkları zaten görünür kılar.

## Sık Sorulan Sorular

**Özel bir araç gerekir mi?** Küçük ve orta ölçekte gerekmez. Dönüşüm katmanı bağımlılıkları zaten tanımlıysa, oradan üretilen bir grafik çoğu soruyu yanıtlar. Araç, kaynak sayısı ve ekip büyüklüğü arttığında değer kazanır.

**Elle tutulan bir liste yeterli olur mu?** Kısa vadede evet, uzun vadede hayır. Elle tutulan liste güncellenmediği anda yanlış güven verir — hiç lineage olmamasından daha risklidir.

**Lineage geçmişe dönük kurulabilir mi?** Mevcut dönüşüm kodundan bugünkü hâli çıkarılabilir. Geçmişte neyin ne zaman değiştiği ise ancak sürüm geçmişi ve çalışma kayıtları saklanıyorsa bilinebilir; bu yüzden çalışma kayıtlarının saklama süresi baştan kararlaştırılmalıdır.
