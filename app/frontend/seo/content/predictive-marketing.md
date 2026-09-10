---
title: "Öngörücü Pazarlama (Predictive Marketing) Nedir?"
description: "Öngörücü pazarlama nedir, hangi tahminler işe yarar? Terk riski, yaşam boyu değer, eğilim skoru; etiket tanımı, veri sızıntısı, değerlendirme ve karara bağlama."
keywords: "öngörücü pazarlama, predictive marketing, churn tahmini, terk riski, propensity model, eğilim skoru, LTV tahmini, veri sızıntısı"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Müşteri Verisi"
  - "Ölçümleme"
date: "2026-09-10"
lang: "tr"
og_title: "Öngörücü Pazarlama Nedir?"
og_description: "Tahmin modellerini pazarlama kararına bağlamanın doğru sırası."
og_type: "article"
twitter_card: "summary"
twitter_title: "Öngörücü Pazarlama Nedir?"
twitter_description: "Terk riski, LTV ve eğilim skorlarını işe yarar hâle getirmek."
og_image: "https://mehmetkuru.dev/blog-covers/predictive-marketing.webp"
og_image_alt: "Öngörücü Pazarlama (Predictive Marketing) Nedir?"
---
Bir ekip terk riski modeli kurar, doğruluk oranı %92 çıkar, herkes memnun olur. Model üretime alınır, riskli görünen müşterilere indirim gönderilir ve terk oranı hiç değişmez. Sebep genellikle modelin kötü olması değildir: model, zaten terk etmiş müşterileri işaret ediyordur. Öngörücü pazarlamada asıl zorluk algoritmada değil, tahminin nasıl tanımlandığı ve hangi karara bağlandığındadır.

## 1. Hangi Tahminler Gerçekten İşe Yarar?

| Tahmin | Sorusu | Bağlandığı karar |
|---|---|---|
| Terk riski (churn) | Bu müşteri yakında ayrılacak mı? | Elde tutma teması, öncelik sırası |
| Yaşam boyu değer | Bu müşteri ne kadar değer üretecek? | Edinim bütçesi, hizmet seviyesi |
| Satın alma eğilimi | Bu kişi bu ürünü alır mı? | Teklif seçimi, hedefleme |
| Bir sonraki sipariş zamanı | Ne zaman tekrar alacak? | İletişim zamanlaması |
| İndirim duyarlılığı | İndirim olmadan da alır mı? | Kupon israfını azaltma |

Son satır çoğu ekipte en yüksek getiriyi verir ve en az kurulanıdır: indirim olmadan da satın alacak kişilere kupon göndermek, doğrudan kâr kaybıdır.

## 2. Ön Koşul: Veri ve Kimlik

Tahmin, geçmiş davranışın müşteri düzeyinde birleştirilebilmesini gerektirir. Kimlikler birleşmemişse aynı kişi birden çok kayıt olarak görünür ve model hem yanlış öğrenir hem yanlış uygulanır. Bu yüzden öngörücü çalışma, [Customer 360 ve kimlik çözümleme](/blog/customer-360-identity-resolution/) çalışmasından sonra gelir.

Gereken asgari geçmiş: modellenen döngünün en az iki katı. Yılda iki kez satın alınan bir kategoride altı aylık veriyle terk modeli kurulamaz.

## 3. En Kritik Adım: Etiket Tanımı

Model neyi tahmin edeceğini etiketten öğrenir. Etiket yanlış tanımlanırsa, teknik olarak kusursuz bir model işe yaramaz sonuç üretir.

"Terk" için sorulması gerekenler:

- terk, aboneliğin iptali mi yoksa alışkanlığın kesilmesi mi?
- kaç gün işlem yapmayan müşteri terk etmiş sayılır?
- bu eşik kategoriye göre değişiyor mu?
- tahmin ne kadar önceden yapılmalı — 7 gün mü, 60 gün mü?

Son soru, girişteki hatanın kaynağıdır. Terk anına çok yakın tahmin yapan bir model yüksek doğruluk verir ama müdahale için zaman bırakmaz. Doğru kurulum, kararın uygulanabileceği kadar erken bir ufuk seçmektir.

## 4. Veri Sızıntısı

Sızıntı, tahmin anında gerçekte bilinmeyen bir bilginin modele girmesidir. Sonuç: testte mükemmel, üretimde işe yaramaz bir model.

Tipik kaynaklar:

- iptal tarihinden sonra güncellenen alanların kullanılması,
- "iade sayısı" gibi olayın kendisinden türeyen alanlar,
- gelecekteki veriyle hesaplanmış toplamlar,
- eğitim ve test kümesinin zamana göre değil rastgele bölünmesi.

Tek etkili önlem, zaman temelli bölmedir: model geçmiş bir tarihe kadar olan veriyle eğitilir, sonrasında ne olduğuyla test edilir. Doğruluk beklenenden düşük çıkarsa bu genellikle iyi haberdir — gerçeğe yaklaşmışsınızdır.

## 5. Değerlendirme: Doğruluk Yanıltıcıdır

Müşterilerin %5'i terk ediyorsa, "hiç kimse terk etmeyecek" diyen bir model %95 doğruluk verir. Dengesiz sınıflarda doğruluk anlamsızdır.

Bakılması gerekenler:

- **Kesinlik (precision):** işaretlediklerimizin kaçı gerçekten terk etti?
- **Duyarlılık (recall):** terk edenlerin kaçını yakaladık?
- **İlk dilim getirisi (lift):** en riskli %10'da terk oranı ortalamanın kaç katı?
- **Kalibrasyon:** %70 olasılık verdiklerimizin gerçekten %70'i mi terk etti?

Pazarlama kararı için genellikle en yararlısı ilk dilim getirisidir: bütçe sınırlıysa, önce en riskli %10'a bakılır.

## 6. Tahmini Karara Bağlamak

Skor üretmek yarım iştir. Skorun bir eşiği, bir aksiyonu ve bir sahibi olmalıdır.

1. eşik belirlenir — kaç kişiye müdahale edilecek, bütçe ne?
2. aksiyon tanımlanır — hangi mesaj, hangi kanal, hangi teklif,
3. maliyet hesaplanır — yanlış işaretlemenin bedeli ne?
4. kontrol grubu ayrılır — müdahale edilmeyen bir kesim tutulur,
5. sonuç [artımsallık](/blog/incrementality-testing/) ile ölçülür.

Dördüncü madde olmadan modelin işe yarayıp yaramadığı asla bilinemez. Riskli müşterilerin bir kısmı zaten kalacaktı; müdahale etmeden ölçmezseniz, onların kalmasını modele yazarsınız.

## 7. Etik ve Gizlilik Sınırları

- hassas veri kategorileri tahmin girdisi olarak kullanılmaz,
- dolaylı olarak hassas nitelik türeten değişkenler denetlenir,
- fiyat farklılaştırmasında tahmin kullanımı hukuki ve itibar riski taşır,
- müşteriye zarar veren kararlarda (hizmet kısıtlama) otomatik karar tek başına yeterli değildir,
- modelin hangi veriyle eğitildiği ve nasıl kullanıldığı kayıt altına alınır.

Bu sınırlar, [veri sınıflandırma ve erişim kontrolü](/blog/marketing-data-access-control/) çalışmasıyla birlikte tanımlanmalıdır.

## 8. Uygulama Sırası

1. hangi kararın iyileşeceğini yazmak,
2. o karara uygun etiketi ve tahmin ufkunu tanımlamak,
3. müşteri düzeyinde geçmiş veriyi hazırlamak,
4. basit bir temel modelle başlamak (kural tabanlı bile olabilir),
5. zaman temelli bölmeyle sızıntıyı elemek,
6. ilk dilim getirisine bakmak,
7. kontrol grubuyla üretime almak,
8. artımsal etkiyi ölçüp eşiği güncellemek.

Dördüncü madde önemlidir: kural tabanlı bir temel modeli geçemeyen karmaşık bir model, karmaşıklığını hak etmiyordur.

## Sık Sorulan Sorular

**Kaç müşteri verisi gerekir?** Kesin bir sayı yoktur; belirleyici olan azınlık sınıfın büyüklüğüdür. Terk eden müşteri sayısı birkaç yüzün altındaysa, model yerine kural tabanlı segmentasyon daha güvenilir sonuç verir.

**Hazır platformların skorları kullanılabilir mi?** Kullanılabilir, ancak etiketin nasıl tanımlandığını bilmiyorsanız skoru karara bağlamak risklidir. En azından ilk dilim getirisini kendi verinizle doğrulayın.

**Model ne sıklıkla yenilenmeli?** Davranış değiştikçe. Performans izleniyorsa yenileme kararı veriden gelir; izlenmiyorsa üç aylık bir gözden geçirme makul bir başlangıçtır.
