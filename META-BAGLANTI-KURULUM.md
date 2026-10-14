# Meta bağlantısı (Facebook sayfası + Instagram) — kurulum

Panel › Otomasyon › **Bağlantılar** › **Meta** kartı, ajansın kendi Facebook sayfasının ve
Instagram profesyonel hesabının istatistiklerini **Anlık Analitik** panosundaki "Sosyal Medya"
kartına getirir (takipçi, görüntülenme, etkileşim, yeni takipçi; son 28 gün, önceki 28 güne göre).
Yalnız okuma izni istenir. Kod: `app/backend/services/meta_baglanti.py`.

## 1. Meta uygulaması

1. https://developers.facebook.com/apps → **Uygulama oluştur**.
2. Kullanım alanı: **"Sayfadaki her şeyi yönet"** (Manage everything on your Page). Varsa
   Instagram için **"Instagram API'ye eriş"** kullanım alanını da ekleyin.
3. İşletme portföyü olarak ajansın portföyünü seçin (yoksa sonra da bağlanabilir).
4. Uygulama **Geliştirme** modunda kalabilir: ajans yalnız kendi sayfasını bağlıyor ve
   uygulamada rolü olan (yönetici/geliştirici) kişiler bütün izinleri İNCELEMESİZ verebiliyor.
   Müşteri hesapları bağlanacağı gün uygulama incelemesi gerekecek.
5. İzinler (kullanım alanı › Özelleştir › Ekle): `pages_show_list`, `pages_read_engagement`,
   `read_insights`, `instagram_basic`, `instagram_manage_insights`, `business_management`,
   `ads_read`.
6. **Facebook Girişi › Ayarlar** › Geçerli OAuth yönlendirme URI'leri:

   ```
   https://mehmetkuru.dev/api/v1/baglantilar/meta/geri-donus
   ```

7. **Uygulama ayarları › Temel**: Gizlilik politikası `https://mehmetkuru.dev/gizlilik/`,
   Hizmet koşulları `https://mehmetkuru.dev/kullanim-kosullari/`, uygulama alan adı
   `mehmetkuru.dev`. Buradaki **Uygulama Kimliği** ve **Uygulama Sırrı** sonraki adımda lazım.

"Facebook Login for Business" yapılandırması kullanılıyorsa yapılandırma kimliği
`META_CONFIG_ID` olarak girilir; o zaman izinler yapılandırmadan gelir (`scope` gönderilmez).

## 2. Render ortam değişkenleri

Render › `mehmetkuru-api` › Environment (değerleri kendiniz yapıştırın; sohbete yazmayın):

| Değişken | Değer |
| --- | --- |
| `META_APP_ID` | Uygulama Kimliği (yalnız rakam) |
| `META_APP_SECRET` | Uygulama Sırrı |
| `BAGLANTI_SIFRE_ANAHTARI` | Google bağlantısıyla AYNI anahtar (zaten tanımlı) |
| `META_CONFIG_ID` | (isteğe bağlı) Facebook Login for Business yapılandırma kimliği |

**Save, rebuild, and deploy**. Kartta "Kurulmadı" yazısı kalkar, "Meta ile bağlan" çıkar.

## 3. Bağlanma

1. **Meta ile bağlan** → Facebook onay ekranı → sayfayı ve Instagram hesabını seçin → Devam.
2. Panele dönünce Facebook sayfasını ve Instagram hesabını seçip **Seçimi kaydet** →
   **Şimdi eşitle**. Sonra veriler 6 saatte bir kendiliğinden yenilenir.

Instagram hesabı **profesyonel** (işletme/içerik üreticisi) olmalı ve Facebook sayfasına
bağlı olmalı; değilse listede çıkmaz. 100 takipçinin altındaki hesaplarda Instagram bazı
ölçümleri (yeni takipçi) vermiyor; o ölçüm atlanır, diğerleri gelir.

## Güvenlik

* Jetonlar yalnız Fernet ile şifreli saklanır (`BAGLANTI_SIFRE_ANAHTARI`); düz metin yok.
* Eşitleme süresi dolmayan **sayfa jetonuyla** yürür; kullanıcı jetonu (~60 gün) yalnız
  sayfa listesi için. Graph isteklerinde jeton adreste değil başlıkta, `appsecret_proof` ile.
* İzin kalkarsa bağlantı "Yeniden bağlanmalı" olur ve yöneticiye bir kez bildirim gider.
* "Bağlantıyı kaldır" Facebook'taki uygulama iznini de geri alır.
