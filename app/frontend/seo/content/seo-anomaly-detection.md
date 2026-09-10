---
title: "SEO Anomaly Detection: Organik Performansta Anomali Tespiti"
description: "SEO anomali tespiti nasıl kurulur? Temel çizgi modelleme, mevsimsellik ayrıştırma, eşik ve istatistiksel yöntemler, segment bazlı uyarılar ve kök neden analizi akışı."
keywords: "SEO anomaly detection, anomali tespiti, trafik düşüşü tespiti, mevsimsellik ayrıştırma, uyarı sistemi, kök neden analizi, SEO izleme"
category: "SEO"
tags:
  - "SEO"
  - "Anomali Tespiti"
  - "İzleme"
date: "2026-06-10"
lang: "tr"
og_title: "SEO Anomaly Detection"
og_description: "Organik performans anomalilerini erken yakalayan izleme sistemi kurmak."
og_type: "article"
twitter_card: "summary"
twitter_title: "SEO Anomaly Detection"
twitter_description: "Temel çizgi, mevsimsellik ve segment bazlı anomali uyarıları."
og_image: "https://mehmetkuru.dev/blog-covers/seo-anomaly-detection.webp"
og_image_alt: "SEO Anomaly Detection: Organik Performansta Anomali Tespiti"
---
SEO'da en pahalı hata, bir sorunun geç fark edilmesidir. Yanlışlıkla eklenen bir `noindex`, bozulan bir şablon, kaybolan iç bağlantılar veya sunucu tarafında oluşan hatalar haftalarca sessizce trafik kaybettirebilir. Anomali tespiti, bu tür sapmaları insan gözü fark etmeden yakalamayı hedefler.

## 1. Anomali Nedir, Ne Değildir?

Anomali, metriğin geçmiş davranışından istatistiksel olarak anlamlı biçimde ayrılmasıdır. Her düşüş anomali değildir: hafta sonu düşüşü, tatil dönemi, mevsimsel gerileme veya bilinen bir kampanya bitişi beklenen davranıştır. İyi bir sistem beklenen hareketleri modele dahil eder ve yalnızca açıklanamayan sapmaları raporlar.

## 2. Neyi İzlemeli?

Tek bir toplam metrik izlemek yetersizdir. İzleme kümesi:

- **Arama tarafı:** gösterim, tıklama, tıklama oranı, ortalama konum,
- **Site tarafı:** organik oturum, giriş sayfası dağılımı, dönüşüm, gelir,
- **Teknik taraf:** indekslenen sayfa sayısı, 4xx/5xx oranı, ortalama yanıt süresi, tarama isteği hacmi,
- **İçerik tarafı:** kritik sayfalarda `title`, `canonical`, `noindex` durumu,
- **Performans:** Core Web Vitals metrikleri.

Her metrik hem toplamda hem segment bazında (sayfa türü, cihaz, ülke, marka/marka dışı) izlenmelidir. Sorunlar genellikle toplamda görünmeden önce tek bir segmentte başlar.

## 3. Temel Çizgi Modelleme

Anomali tespiti bir tahmin problemidir: metriğin bugün ne olması beklendiği hesaplanır, gerçekleşen değerle karşılaştırılır.

Basitten karmaşığa yaklaşımlar:

- **Hareketli ortalama ve standart sapma:** Kolay kurulur, mevsimselliği zayıf yakalar.
- **Haftanın günü bazlı temel çizgi:** Aynı günün son 8 haftalık ortalaması; haftalık döngüyü çözer.
- **Mevsimsellik ayrıştırması:** Seri trend, mevsimsellik ve artık bileşenlerine ayrılır; anomali artık bileşende aranır.
- **Tahmin aralığı yöntemleri:** Beklenen değer bir güven aralığıyla üretilir, aralık dışı değerler işaretlenir.

Küçük hacimli metriklerde gürültü yüksektir; bu metrikler için daha geniş eşikler veya daha uzun toplama pencereleri kullanılmalıdır.

## 4. Eşik Tasarımı ve Alarm Yorgunluğu

Fazla uyarı, hiç uyarı olmamasıyla aynı sonucu verir: kimse bakmaz. Uyarı tasarımında pratik kurallar:

- her uyarıya bir öncelik seviyesi verin (kritik / uyarı / bilgi),
- kritik uyarıları yalnızca iş etkisi olan metriklere bağlayın,
- ardışık iki dönem koşulu ekleyerek tek günlük gürültüyü filtreleyin,
- aynı kök nedene bağlı uyarıları tek bildirimde gruplayın,
- düşük hacimli segmentleri minimum eşik altında sessize alın,
- her uyarının bir sahibi ve beklenen ilk aksiyonu olsun.

## 5. Kök Neden Analizi Akışı

Uyarı geldiğinde izlenecek sıra:

1. **Kapsam:** Etki tek sayfada mı, bir sayfa türünde mi, tüm sitede mi?
2. **Zamanlama:** Sapma bir yayın, altyapı değişikliği veya bilinen bir güncellemeyle çakışıyor mu?
3. **Teknik kontrol:** Sayfa erişilebilir mi, `noindex` var mı, canonical doğru mu, robots kuralı değişti mi?
4. **Sunucu tarafı:** Hata kodu ve yanıt süresi artışı var mı?
5. **Arama tarafı:** Gösterim mi düştü, tıklama oranı mı? Gösterim sabit tıklama düşükse sonuç sayfası düzeni değişmiş olabilir.
6. **Ölçüm katmanı:** Etiket veya veri toplama bozulmuş olabilir; gerçek trafik kaybı olmadan metrik düşebilir.
7. **Dış etken:** Mevsimsellik, rekabet hareketi veya haber etkisi.

Altıncı adım özellikle önemlidir: ölçüm hatası ile gerçek kayıp ayrımı yapılmadan yapılan müdahaleler zaman kaybettirir.

## 6. Uygulama Mimarisi

Sürdürülebilir bir kurulum şu bileşenlerden oluşur: zamanlanmış veri çekimi, tarihsel metrikleri tutan bir veri deposu, temel çizgi hesaplayan bir işleme adımı, kural ve eşik tanımlarının sürüm kontrolünde tutulduğu bir yapılandırma, bildirim kanalı ve incelenen uyarıların sonucunun kaydedildiği bir kayıt defteri.

Kayıt defteri sistemin öğrenmesini sağlar: hangi uyarıların gerçek sorun çıktığı bilindikçe eşikler kalibre edilir.

## 7. Sistemin Kendi Sağlığı

İzleme sistemi de bozulabilir. Veri gelmediğinde uyarı üretilmediği için her şey yolunda görünür. Bu nedenle veri tazeliği kontrolü, beklenen satır sayısı doğrulaması ve işlerin başarısızlık bildirimi zorunludur.

## Sık Sorulan Sorular

**Basit eşikler yeterli mi?** Başlangıç için evet. Mevsimselliği güçlü metriklerde kısa sürede yetersiz kalır ve gün bazlı temel çizgiye geçmek gerekir.

**Hangi sıklıkta çalışmalı?** Teknik metrikler için günlük, kritik sayfa etiket kontrolleri için daha sık; arama performansı verisi zaten gecikmeli geldiği için günlük yeterlidir.

**Yükseliş de anomali sayılır mı?** Evet. Beklenmeyen artış çoğu zaman bir ölçüm hatası, bot trafiği veya kopya içerik sinyalidir; incelenmesi gerekir.
