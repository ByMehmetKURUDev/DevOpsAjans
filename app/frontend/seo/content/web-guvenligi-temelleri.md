---
title: "Web Güvenliği Temelleri: Frontend ve API Katmanında Güvenlik"
description: "Web güvenliği temelleri: XSS, CSRF, kimlik doğrulama, token saklama, güvenlik başlıkları, girdi doğrulama, bağımlılık güvenliği ve pratik önlem listesi."
keywords: "web güvenliği, XSS, CSRF, CSP, güvenlik başlıkları, token saklama, kimlik doğrulama, girdi doğrulama, bağımlılık güvenliği"
category: "Web Geliştirme"
tags:
  - "Web Geliştirme"
  - "Güvenlik"
  - "Backend"
date: "2026-09-09"
lang: "tr"
og_title: "Web Güvenliği Temelleri"
og_description: "XSS, CSRF, token yönetimi ve güvenlik başlıklarıyla temel web güvenliği."
og_type: "article"
twitter_card: "summary"
twitter_title: "Web Güvenliği Temelleri"
twitter_description: "Frontend ve API katmanında uygulanabilir güvenlik önlemleri."
og_image: "https://mehmetkuru.dev/blog-covers/web-guvenligi-temelleri.webp"
og_image_alt: "Web Güvenliği Temelleri: Frontend ve API Katmanında Güvenlik"
---
Web güvenliği, tek bir araçla çözülen bir konu değil; her katmanda alınan kararların toplamıdır. Bu yazı, bir web uygulamasında en sık karşılaşılan saldırı yüzeylerini ve bunlara karşı uygulanabilir önlemleri ele alır. Temel ilke şudur: istemciden gelen hiçbir veri güvenilir değildir ve güvenlik kontrolleri her zaman sunucu tarafında yapılmalıdır.

## 1. XSS — Cross Site Scripting

Saldırgan, sayfaya kendi JavaScript kodunu çalıştırabilecek biçimde içerik enjekte eder. Sonuç: oturum ele geçirme, sahte form gösterimi, veri sızdırma.

**Önlemler:**

- kullanıcı girdisini HTML olarak yorumlamayın; modern arayüz kütüphaneleri metni varsayılan olarak kaçırır (escape),
- ham HTML ekleme yollarından (`innerHTML`, `dangerouslySetInnerHTML`) kaçının; zorunluysa güvenilir bir sanitizasyon kütüphanesi kullanın,
- kullanıcı tarafından sağlanan URL'lerde protokol doğrulaması yapın (`javascript:` şemasını reddedin),
- Content Security Policy uygulayarak satır içi script çalıştırmayı kısıtlayın,
- Markdown veya zengin metin desteği veriyorsanız çıktıyı sunucu tarafında temizleyin.

## 2. CSRF — Cross Site Request Forgery

Kullanıcının oturumu üzerinden, farkında olmadan istenmeyen bir işlem tetiklenir.

**Önlemler:**

- durum değiştiren işlemler için CSRF token kullanın,
- oturum çerezlerinde `SameSite=Lax` veya `Strict` ayarlayın,
- durum değiştiren işlemleri yalnızca POST/PUT/DELETE ile kabul edin,
- kritik işlemlerde ek doğrulama (şifre tekrarı, ikinci faktör) isteyin.

Token tabanlı kimlik doğrulamada `Authorization` başlığı kullanılıyorsa CSRF riski azalır; ancak token çerezde tutuluyorsa risk devam eder.

## 3. Kimlik Doğrulama ve Oturum Yönetimi

- şifreleri asla düz metin saklamayın; güçlü ve yavaş bir hash algoritması kullanın,
- şifre politikası uzunluk odaklı olmalı; karmaşıklık zorunluluğu tek başına yeterli değildir,
- giriş denemelerinde hız sınırı ve kademeli gecikme uygulayın,
- oturum süresi ve yenileme politikası tanımlayın,
- şifre sıfırlama bağlantıları tek kullanımlık ve kısa ömürlü olmalı,
- çıkışta sunucu tarafında oturum geçersiz kılınmalı,
- hassas işlemlerde ikinci faktör doğrulaması sunun.

Hata mesajları bilgi sızdırmamalıdır: "kullanıcı bulunamadı" ile "şifre hatalı" ayrımı, hesap keşfine imkân verir.

## 4. Token Saklama

Sık sorulan ve sık yanlış cevaplanan bir konudur:

- **`localStorage`:** XSS durumunda doğrudan okunabilir. Uzun ömürlü token'lar için riskli.
- **`HttpOnly` çerez:** JavaScript erişemez; XSS'e karşı daha dayanıklıdır. CSRF önlemi gerekir.
- **Bellekte tutma:** En güvenli ama sayfa yenilenmesinde kaybolur; yenileme token'ı ile birlikte kullanılır.

Pratik yaklaşım: kısa ömürlü erişim token'ı bellekte, yenileme token'ı `HttpOnly` + `Secure` + `SameSite` çerezde.

## 5. Güvenlik Başlıkları

Sunucu yanıtına eklenmesi gereken başlıklar:

| Başlık | İşlevi |
|---|---|
| `Content-Security-Policy` | Kaynak yükleme ve script çalıştırma kısıtı |
| `Strict-Transport-Security` | HTTPS zorunluluğu |
| `X-Content-Type-Options: nosniff` | MIME tipi tahmininin engellenmesi |
| `Referrer-Policy` | Referans bilgisinin sızmasının sınırlanması |
| `Permissions-Policy` | Tarayıcı özelliklerine erişim kısıtı |
| `X-Frame-Options` / `frame-ancestors` | Clickjacking koruması |

CSP en etkili ama en dikkatli uygulanması gereken başlıktır; önce rapor modunda çalıştırıp ihlalleri gözlemlemek doğru yaklaşımdır.

## 6. Girdi Doğrulama ve Yetkilendirme

- doğrulama hem istemcide (kullanıcı deneyimi) hem sunucuda (güvenlik) yapılmalı; istemci doğrulaması güvenlik önlemi değildir,
- şema tabanlı doğrulama kullanın; beklenmeyen alanları reddedin,
- veritabanı sorgularında parametreli sorgu kullanın; dize birleştirmeyle sorgu kurmayın,
- her istekte yetkilendirme kontrolü yapın; nesne kimliği tahmin edilerek başka kullanıcının verisine erişilememeli,
- dosya yüklemede tip, boyut ve içerik doğrulaması yapın; yüklenen dosyaları uygulama alanı dışında saklayın.

Yetkilendirme kontrolünün eksikliği, pratikte en sık rastlanan ciddi güvenlik açığıdır: arayüzde gizlenen bir işlem, API üzerinden hâlâ çağrılabiliyor olabilir.

## 7. API Katmanı

- hız sınırı (rate limiting) uygulayın,
- CORS yapılandırmasını yalnızca gereken kaynaklara açın; joker karakteri kimlik doğrulamalı isteklerle birlikte kullanmayın,
- hata yanıtlarında yığın izi ve iç yapı bilgisi döndürmeyin,
- hassas verileri günlüklere yazmayın,
- API anahtarlarını istemci koduna gömmeyin; gizli anahtar gerektiren çağrıları sunucu tarafından yapın.

## 8. Bağımlılık ve Altyapı Güvenliği

- bağımlılıkları düzenli güncelleyin ve bilinen zafiyet taraması yapın,
- kullanılmayan paketleri kaldırın; her bağımlılık bir saldırı yüzeyidir,
- gizli anahtarları sürüm kontrolüne koymayın; gizli anahtar yöneticisi kullanın,
- üretim ve geliştirme yapılandırmalarını ayırın,
- yedekleme ve geri yükleme sürecini test edin,
- HTTPS'i her yerde zorunlu kılın.

## 9. Uygulanabilir Kontrol Listesi

Yayın öncesi hızlı kontrol: HTTPS zorunlu mu, güvenlik başlıkları tanımlı mı, kimlik doğrulama gerektiren tüm uç noktalar korunuyor mu, yetkilendirme nesne düzeyinde kontrol ediliyor mu, girdi doğrulaması sunucuda var mı, hata mesajları bilgi sızdırıyor mu, gizli anahtarlar kod dışında mı, bağımlılık taraması yapıldı mı, hız sınırı aktif mi, günlüklerde hassas veri var mı.

## Sık Sorulan Sorular

**Küçük projeler için bu önlemler fazla mı?** Otomatik tarama araçları büyüklük ayırt etmez. HTTPS, güvenlik başlıkları, girdi doğrulaması ve yetkilendirme kontrolü her ölçekte zorunludur.

**Güvenlik testi nasıl yapılır?** Otomatik zafiyet taraması ve bağımlılık denetimi temel katmandır. Hassas veri işleyen uygulamalarda bağımsız sızma testi önerilir.

**Frontend'de güvenlik olur mu?** Frontend güvenlik kararlarını uygulayabilir ama garanti edemez. Her kontrolün sunucu tarafında tekrarlanması zorunludur.
