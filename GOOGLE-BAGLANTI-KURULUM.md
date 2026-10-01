# Google bağlantısı — kurulum (Analytics 4 + Search Console + YouTube)

Amaç: Yönetim panelindeki **Anlık Analitik** panosu örnek sayılar yerine sitenizin
gerçek verisini göstersin. Bağlantı yalnız **okuma** izni ister; panelden tek
tıkla kaldırılır.

Toplam süre: ~15 dakika. Sıra önemli. Hiçbir anahtarı sohbete ya da bir
dosyaya yazmayın — yalnız Render'a girin.

## 1. API'leri açın

1. [console.cloud.google.com](https://console.cloud.google.com) → üstteki proje
   seçiciden **mehmetkuru-dev** projesini seçin.
2. Sol menü → **APIs & Services → Library**.
3. Aşağıdaki beşini tek tek arayın ve her birinde **Enable**'a basın:
   - Google Analytics Data API
   - Google Analytics Admin API
   - Google Search Console API
   - YouTube Data API v3
   - YouTube Analytics API

## 2. OAuth onay ekranı

Sol menü → **Google Auth Platform** (eski adı: *OAuth consent screen*).

1. **Branding**: Uygulama adı `mehmetkuru.dev Panel`, destek e-postası olarak
   kendi adresinizi seçin, **Save**.
2. **Audience**: Kullanıcı türü **External**.
3. **Data Access** → **Add or remove scopes** → şunları işaretleyin, **Update** → **Save**:
   - `.../auth/analytics.readonly`
   - `.../auth/webmasters.readonly`
   - `.../auth/youtube.readonly`
   - `.../auth/yt-analytics.readonly`
   - `openid` ve `.../auth/userinfo.email`
4. **Audience** → *Publishing status* → **Publish app** → durum **In production** olmalı.

> **Neden "In production"?** "Testing" durumunda Google'ın verdiği izin
> **7 günde düşer**; panel her hafta "Yeniden bağlan" der.
>
> Uygulama Google tarafından doğrulanmadığı için bağlanırken
> **"Google hasn't verified this app"** uyarısı çıkar. Kendi hesabınız için
> sorun değil: **Advanced (Gelişmiş) → Go to mehmetkuru.dev Panel (unsafe)** deyin.

## 3. OAuth istemcisi (yeni)

Projede gördüğünüz **mehmetkuru-dev-web** istemcisi büyük olasılıkla sitenin
"Google ile giriş" özelliğinde kullanılıyor; ona dokunmayın, **yenisini açın**.

1. **Google Auth Platform → Clients → Create client**.
2. Application type: **Web application**. Name: `mehmetkuru-dev-baglantilar`.
3. **Authorized redirect URIs → Add URI** →
   `https://mehmetkuru.dev/api/v1/baglantilar/google/geri-donus`
   (panelde Bağlantılar sekmesi de bu adresi gösterir, oradan kopyalayabilirsiniz).
4. **Create**. Açılan pencerede **Client ID** ve **Client secret** görünür —
   pencereyi kapatmayın, 4. adımda kullanacaksınız.

## 4. Render ortam değişkenleri

Önce şifreleme anahtarı üretin. Mac'te **Terminal**'i açın, şunu yapıştırıp Enter'a basın:

```
openssl rand -base64 32 | tr '+/' '-_'
```

Çıkan 44 karakterlik satır anahtarınızdır. (Depoda Python kuruluysa aynı işi
`python scripts/baglanti_anahtari_uret.py` de yapar; ikisi de yalnız ekrana basar.)

Sonra [dashboard.render.com/web/srv-daikvbgae00c73eur4j0/env](https://dashboard.render.com/web/srv-daikvbgae00c73eur4j0/env)
adresinde **Add Environment Variable** ile üçünü ekleyin:

| Değişken | Değer |
| --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` | 3. adımdaki Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | 3. adımdaki Client secret |
| `BAGLANTI_SIFRE_ANAHTARI` | Terminal'de üretilen satır |

**Save Changes** → servis kendini yeniden başlatır (~1 dk). Terminal'i kapatın.

> Şifreleme anahtarını sonradan değiştirirseniz kayıtlı bağlantı okunamaz;
> panelde bir kez **Yeniden bağlan** demeniz yeterli.

## 5. Panelden bağlanın

1. Yönetim paneli → **Bağlantılar** sekmesi. Google kartında "Kurulmadı"
   yazıyorsa hangi değişkenin eksik olduğu orada yazar.
2. **Google ile bağlan** → Analytics, Search Console ve YouTube'a erişimi olan
   Google hesabınızı seçin → uyarıda **Gelişmiş → devam et** → bütün kutuları
   işaretleyip **Continue**.
3. Panele dönünce üç kutudan **GA4 mülkünü**, **Search Console sitesini** ve
   **YouTube kanalını** seçin → **Seçimi kaydet** → **Şimdi eşitle**.
4. **Analitik** sekmesinde "Örnek veri" şeridi kalkar, gerçek kartlar görünür.
   Bundan sonra veri 6 saatte bir kendiliğinden yenilenir.

## Sorun çıkarsa

| Ne görüyorsunuz? | Ne yapmalı? |
| --- | --- |
| Google'da `redirect_uri_mismatch` | 3. adımdaki adresi birebir (sonda `/` olmadan) ekleyin. |
| Panelde "Bu API … etkin değil" | 1. adımda ilgili API'yi **Enable** edin, 5 dk sonra yeniden eşitleyin. |
| Panelde "Bu hesabın seçilen kaynağa erişimi yok" | Bağlanan Google hesabını GA4 mülküne (en az *Viewer*) / Search Console'a ekleyin. |
| Her hafta "Yeniden bağlan" | 2. adımın 4. maddesi: yayın durumu **In production** olmalı. |
| Bağlantıyı kaldırmak | Panel → Bağlantılar → **Bağlantıyı kaldır** (Google'daki izin de iptal edilir). |
