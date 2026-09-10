---
title: "Veri Kalitesi ve Gözlemlenebilirlik: Sessiz Bozulmayı Yakalamak"
description: "Pazarlama verisinde kalite nasıl ölçülür? Tazelik, hacim, şema, dağılım ve ilişki testleri; anomali tespiti, uyarı tasarımı ve olay yönetimi."
keywords: "veri kalitesi, data observability, tazelik testi, hacim anomalisi, şema değişikliği, veri testi, uyarı yorgunluğu, veri olayı yönetimi"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Ölçümleme"
  - "Data Governance"
date: "2026-09-10"
lang: "tr"
og_title: "Veri Kalitesi ve Gözlemlenebilirlik"
og_description: "Hata vermeden bozulan veriyi kullanıcıdan önce yakalamak."
og_type: "article"
twitter_card: "summary"
twitter_title: "Veri Kalitesi ve Gözlemlenebilirlik"
twitter_description: "Tazelik, hacim, şema ve dağılım testleriyle sessiz bozulmayı yakalamak."
og_image: "https://mehmetkuru.dev/blog-covers/marketing-data-quality-observability.webp"
og_image_alt: "Veri Kalitesi ve Gözlemlenebilirlik: Sessiz Bozulmayı Yakalamak"
---
Veri sistemlerinde en pahalı arıza, sistemin çökmesi değildir. Çökme fark edilir ve düzeltilir. Asıl maliyet, boru hattının yeşil görünmeye devam ederken yanlış sayı üretmesidir — çünkü o sayıya bakarak bütçe kaydırılır, kampanya durdurulur, hedef değiştirilir. Gözlemlenebilirlik, bu sessiz bozulmayı kullanıcıdan önce yakalama disiplinidir.

## 1. Beş Test Ailesi

| Aile | Sorusu | Tipik yakaladığı |
|---|---|---|
| Tazelik | Veri zamanında geldi mi? | Duran iş, gecikmiş kaynak |
| Hacim | Beklenen kadar kayıt var mı? | Yarım yüklenme, kaynak kesintisi |
| Şema | Alanlar ve tipler beklendiği gibi mi? | Sessiz alan değişikliği |
| Dağılım | Değerler makul aralıkta mı? | Birim değişikliği, bozuk hesaplama |
| İlişki | Kayıtlar tutarlı mı? | Yetim kayıt, yinelenen anahtar |

Çoğu ekip yalnızca ilk ikisini kurar. Oysa girişte anlatılan hata tipini — hata vermeden yanlış üretme — genellikle dağılım ve ilişki testleri yakalar.

## 2. Tazelik

En basit ve en yüksek getirili testtir. Her kritik tablo için "en geç ne zaman güncellenmiş olmalı" tanımlanır ve aşıldığında uyarı üretilir.

Dikkat edilmesi gereken: tazelik eşiği iş takvimine göre tanımlanmalıdır. Hafta sonu çalışmayan bir kaynak için pazartesi sabahı üretilen "24 saattir güncellenmedi" uyarısı, uyarı yorgunluğunun başlangıcıdır.

## 3. Hacim

Kayıt sayısındaki ani değişimler izlenir. Sabit eşik yerine geçmişe göre karşılaştırma daha güvenilirdir: "dünkü sayının %40 altında" veya "son dört haftanın aynı günüyle karşılaştırıldığında beklenen aralığın dışında".

Aynı günün karşılaştırılması önemlidir; pazartesi ile pazar gününü karşılaştıran bir kontrol her hafta yanlış alarm üretir.

## 4. Şema

Alanların varlığı ve tipi kontrol edilir. Bu kontrol ambarda ikinci savunma hattıdır; asıl önlem veri toplama noktasındaki [veri sözleşmeleridir](/blog/marketing-data-contracts/). Ambar tarafı, sözleşmenin kapsamadığı kaynaklar için gereklidir.

## 5. Dağılım

En çok bilgi taşıyan ve en az kurulan aile budur.

- boş değer oranının aniden yükselmesi,
- ortalama sipariş tutarının bir gecede yüz katına çıkması (kuruş/lira karışıklığı),
- bir kategorinin toplam içindeki payının sıçraması,
- para biriminde beklenmeyen değerler,
- tarih alanında gelecekteki tarihler.

Kuruş/lira karışıklığı klasik örnektir: sistem hata vermez, tüm raporlar yüz kat şişer ve fark edilene kadar kararlar bu sayıya göre alınır.

## 6. İlişki

- her sipariş satırının geçerli bir siparişe bağlı olması,
- birincil anahtarın benzersizliği,
- toplam gelirin kalem toplamlarıyla uyuşması,
- kanal atfı toplamının toplam dönüşümü aşmaması.

Son madde, ölçümleme kurulumlarında sık görülen çift sayımı yakalar.

## 7. Uyarı Tasarımı

Kurulmuş ama okunmayan uyarılar, hiç kurulmamış uyarılardan daha kötüdür: güvende olduğunuz yanılsaması üretirler.

- her uyarının bir sahibi olmalı,
- her uyarının bir eylemi olmalı — "ne yapacağımı bilmiyorum" diyorsa uyarı yanlış tasarlanmıştır,
- kritik ve bilgilendirici uyarılar ayrı kanallara gitmeli,
- tekrarlayan yanlış alarmlar düzeltilmeli veya kapatılmalı,
- uyarı sayısı bir metrik olarak izlenmeli.

Pratik kural: bir uyarı üst üste üç kez yanlış alarm verdiyse, eşiği düzeltilir ya da kaldırılır. Görmezden gelinmeye başlanan bir uyarı artık koruma sağlamıyordur.

## 8. Olay Yönetimi

Bozulma tespit edildiğinde izlenecek yol önceden yazılmalıdır:

1. etkilenen varlıkları belirlemek — [veri kökeni](/blog/data-lineage-impact-analysis/) burada devreye girer,
2. etkilenen raporları "güvenilmez" olarak işaretlemek,
3. aşağı akıştaki senkronizasyonları durdurmak,
4. kök nedeni bulmak,
5. düzeltmek ve geriye dönük yeniden hesaplamak,
6. tüketicileri bilgilendirmek,
7. aynı hatayı yakalayacak testi eklemek.

İkinci madde çoğu ekipte eksiktir. Bozuk olduğu bilinen bir rapor, bilinmeden kullanılmaya devam eder; oysa panonun üstünde tek bir uyarı bandı, yanlış kararı engeller.

Yedinci madde ise programı ilerleten şeydir: her olay, kalıcı bir testle sonuçlanmalıdır.

## 9. Nereden Başlamalı?

1. karara en çok bağlanan 5 tabloyu seçmek,
2. hepsine tazelik ve hacim testi koymak,
3. gelir ve dönüşüm alanlarına dağılım testi eklemek,
4. anahtar benzersizliğini kontrol etmek,
5. uyarı sahiplerini atamak,
6. bir olay yönetimi akışı yazmak,
7. her olaydan sonra yeni test eklemek,
8. kapsamı genişletmek.

Tüm tablolara test yazmaya çalışmak yerine, yanlış olduğunda en pahalı olan beş tabloyla başlamak çok daha hızlı sonuç verir.

## Sık Sorulan Sorular

**Özel bir gözlemlenebilirlik aracı gerekir mi?** Başlangıçta gerekmez. Dönüşüm katmanının test yeteneği ve birkaç zamanlanmış kontrol sorgusu ilk aşamayı karşılar. Araç, tablo sayısı ve ekip büyüklüğü arttığında anomali tespitini otomatikleştirdiği için değer kazanır.

**Kaç test yeterli?** Sayı değil kapsam önemlidir: her kritik tabloda beş aileden en az üçü temsil edilmelidir. Yüz tane tazelik testi, tek bir dağılım testinin yakaladığını yakalamaz.

**Testler boru hattını durdurmalı mı?** Kritik tablolarda evet — bozuk veriyi yaymak, geç kalmaktan daha maliyetlidir. İkincil tablolarda uyarı üretip devam etmek daha uygundur.
