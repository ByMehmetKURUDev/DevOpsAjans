---
title: "Pazarlama Deneyleri: A/B Testinden Deney Programına"
description: "Pazarlama deneyleri nasıl kurulur? Hipotez yazımı, rastgeleleştirme birimi, örneklem ve süre, erken bakma hatası, guardrail metrikleri ve sonuç okuma."
keywords: "A/B testi, pazarlama deneyi, hipotez, örneklem büyüklüğü, istatistiksel anlamlılık, peeking, guardrail metrik, deney programı"
category: "Veri ve Analitik"
tags:
  - "Veri ve Analitik"
  - "Ölçümleme"
  - "Dijital Pazarlama"
date: "2026-09-10"
lang: "tr"
og_title: "Pazarlama Deneyleri"
og_description: "Tekil A/B testinden sürdürülebilir bir deney programına geçmek."
og_type: "article"
twitter_card: "summary"
twitter_title: "Pazarlama Deneyleri"
twitter_description: "Deney kurmanın ve sonucunu doğru okumanın kuralları."
og_image: "https://mehmetkuru.dev/blog-covers/marketing-experimentation.webp"
og_image_alt: "Pazarlama Deneyleri: A/B Testinden Deney Programına"
---
Ekip iki başlık dener, üçüncü gün B seçeneği %18 önde görünür, test durdurulur ve B kalıcı hâle getirilir. Bir ay sonra dönüşüm oranında hiçbir iyileşme yoktur. Bu, kötü bir fikirle değil, kötü bir deney kurulumuyla açıklanan bir sonuçtur — ve pazarlama ekiplerinde en sık tekrarlanan hatadır.

## 1. Neden Tekil Test Yetmez?

Tek tek yapılan testler üç sorun üretir: sonuçlar birikmez, aynı sorular tekrar sorulur ve başarısız testler öğrenme olarak kaydedilmez. Deney programı, testleri bir öğrenme sistemine dönüştürür.

Programın farkı basittir: her deneyin yazılı bir hipotezi, önceden belirlenmiş bir bitiş kuralı ve saklanan bir sonucu vardır.

## 2. Hipotez Yazımı

İyi bir hipotez üç parçadan oluşur:

> **Çünkü** [gözlem], **eğer** [değişiklik] yaparsak, [metrik] [yön ve büyüklük] değişir.

Örnek: *Çünkü mobilde ödeme adımında %62 terk var, eğer adres formunu tek ekrana indirirsek, mobil ödeme tamamlama oranı 3 puan artar.*

"Büyüklük" kısmı zorunludur. Beklenen etkiyi yazmadan örneklem büyüklüğü hesaplanamaz; hesaplanmadan da testin ne kadar süreceği bilinemez.

## 3. Rastgeleleştirme Birimi

Kimin hangi grupta olduğu neye göre belirlenecek?

| Birim | Uygun olduğu durum | Riski |
|---|---|---|
| Ziyaretçi/oturum | Arayüz değişiklikleri | Aynı kişi iki grubu da görebilir |
| Kullanıcı | Girişli deneyimler | Girişsiz trafiği kapsamaz |
| Coğrafi bölge | Kanal ve bütçe deneyleri | Az sayıda birim, düşük hassasiyet |
| Zaman dilimi | Kanal kapatma testleri | Mevsimsellik etkisi |

Kritik kural: rastgeleleştirme birimi ile ölçüm birimi aynı olmalıdır. Oturum bazında rastgeleleştirip kullanıcı bazında dönüşüm ölçmek, sonucu bozar.

## 4. Örneklem ve Süre

Süre "biz yeterli gördüğümüzde" değil, baştan hesapla belirlenir. Belirleyiciler:

- mevcut dönüşüm oranı (taban),
- tespit edilmek istenen en küçük etki,
- kabul edilen hata payları,
- günlük trafik.

İki pratik kural:

**En az bir tam hafta çalıştırın.** Hafta içi ve hafta sonu davranışı farklıdır; beş günlük test hafta sonunu görmez.

**Hesaplanan örnekleme ulaşmadan bakmayın.** Bakmak zorundaysanız, yalnızca guardrail metriklerine bakın.

## 5. En Sık Üç Hata

**Erken bakma (peeking):** Test süresince sonuca defalarca bakıp "anlamlı" olduğu anda durdurmak. Bu yöntem, gerçekte fark olmasa bile er ya da geç "anlamlı" bir sonuç üretir. Bitiş kuralı önceden yazılmalıdır.

**Çoklu karşılaştırma:** Aynı testte on metriğe bakmak. On metrikten birinin şans eseri anlamlı çıkma olasılığı yüksektir. Bir birincil metrik seçilir, gerisi ikincil olarak raporlanır.

**Anlamlılığı büyüklükle karıştırmak:** "İstatistiksel olarak anlamlı" demek, "iş açısından önemli" demek değildir. %0,2'lik bir artış, yeterince büyük örneklemde anlamlı çıkar ama uygulama maliyetini karşılamayabilir.

## 6. Guardrail Metrikleri

Birincil metriği iyileştirirken başka bir şeyi bozmadığınızdan emin olmak için izlenen metriklerdir.

- sayfa yüklenme süresi ve [Core Web Vitals](/blog/core-web-vitals/),
- iade ve iptal oranı,
- destek talebi sayısı,
- abonelikten çıkma oranı,
- ortalama sepet tutarı.

Klasik örnek: agresif bir açılır pencere kayıt oranını artırır, aynı anda çıkma oranını ve destek yükünü de artırır. Guardrail olmadan bu deney "başarılı" görünür.

## 7. Sonucu Okumak

Sonuç üç kategoriden birine düşer:

1. **Kazandı** — etki hipotezle uyumlu ve iş açısından anlamlı. Uygulanır ve kalıcı etkisi izlenir.
2. **Kaybetti** — etki yok veya ters yönde. Değişiklik geri alınır, öğrenme kaydedilir.
3. **Belirsiz** — örneklem yetersiz veya etki çok küçük. En yaygın sonuçtur ve "kaybetti" değildir.

Belirsiz sonuçların ayrı kaydedilmesi önemlidir: aynı fikri altı ay sonra daha büyük trafikle yeniden denemek mantıklı olabilir.

## 8. Deney Programı Kurmak

1. deney kayıt defteri açmak (hipotez, kurulum, sonuç, karar),
2. birincil metrik ve guardrail listesini standartlaştırmak,
3. örneklem hesabını kurulumun zorunlu adımı yapmak,
4. bitiş kuralını baştan yazmak,
5. sonuçları kazanan/kaybeden ayrımı yapmadan paylaşmak,
6. kanal düzeyindeki büyük sorular için [artımsallık testlerine](/blog/incrementality-testing/) geçmek.

Beşinci madde kültürel açıdan belirleyicidir: yalnızca kazanan deneylerin paylaşıldığı bir ekipte, kaybeden deneyler tekrar tekrar kurulur.

## Sık Sorulan Sorular

**Trafiğim az, test yapabilir miyim?** Küçük etkileri ölçemezsiniz ama büyük değişiklikleri ölçebilirsiniz. Düşük trafikte doğru strateji, küçük iyileştirmeler yerine belirgin farklar üreten seçenekleri denemektir. Test süresini uzatmak da bir seçenektir, ancak mevsimsellik riski artar.

**Kaç varyant denenmeli?** İki varyantla başlayın. Varyant sayısı arttıkça her birine düşen örneklem azalır ve test uzar. Üçten fazla varyant, ancak yüksek trafikte anlamlıdır.

**Test bittikten sonra ne kadar izlemeli?** Yenilik etkisi ilk haftalarda sonucu şişirebilir. Kazanan değişikliğin etkisini bir ay boyunca izlemek, kalıcı olup olmadığını gösterir.
