# Bildirimler — kurulum kılavuzu

Kod hazır. Çalışması için hesap açıp anahtarları sunucuya tanıtmanız
gerekiyor. Bu dosya hangi anahtarın ne işe yaradığını anlatıyor.

---

## Nasıl çalışıyor

Üç olay bildirim üretiyor:

| Olay | Kime gider |
|---|---|
| İletişim formu dolduruldu | Yöneticiye |
| Destek talebi açıldı | Yöneticiye |
| Proje aşaması değişti | Müşteriye ve yöneticiye |

Her olay açık olan her kanaldan ayrı ayrı gönderiliyor ve **her gönderim
veritabanına yazılıyor**. Panelde `Bildirimler` sekmesinde ne gittiğini,
ne gitmediğini ve gitmediyse neden gitmediğini görüyorsunuz.

**Panel içi bildirim** (çan) her zaman çalışıyor; dışarıya bağımlılığı yok.

---

## Kanallar

### 1. E-posta — en kolayı, buradan başlayın

İki seçenek var, birini seçin.

**Resend (önerilen)** — `resend.com`, ayda 3.000 e-postaya kadar ücretsiz.

```
RESEND_API_KEY=re_xxxxxxxxxxxx
NOTIFY_FROM_EMAIL=bildirim@mehmetkuru.dev
```

Gönderen adresin alan adını Resend panelinde doğrulamanız gerekiyor
(DNS'e birkaç kayıt ekleniyor). Doğrulanmamış adresten gönderim
yapılamaz — bu Resend'in değil, e-posta dünyasının kuralı.

**Kendi SMTP sunucunuz**

```
SMTP_HOST=smtp.yandex.com
SMTP_PORT=587
SMTP_USER=by@mehmetkuru.dev
SMTP_PASSWORD=uygulama-parolasi
NOTIFY_FROM_EMAIL=by@mehmetkuru.dev
```

Gmail ve Yandex için hesap parolanız değil, **uygulama parolası**
üretmeniz gerekiyor.

İkisi birden tanımlıysa Resend kullanılır.

---

### 2. SMS

**Netgsm** — Türkiye için uygun, ön ödemeli.

```
SMS_PROVIDER=netgsm
NETGSM_USER=850xxxxxxx
NETGSM_PASSWORD=parola
NETGSM_HEADER=onayli-basligniz
```

`NETGSM_HEADER` Netgsm'de onaylattığınız gönderici başlığı. Onaysız
başlıkla gönderim reddedilir.

**Twilio** — uluslararası.

```
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_FROM_NUMBER=+15551234567
```

---

### 3. WhatsApp — en uzun süren

Meta Cloud API kullanılıyor.

```
WHATSAPP_TOKEN=EAAxxxxxxxx
WHATSAPP_PHONE_ID=1234567890
WHATSAPP_TEMPLATE=proje_bildirimi
WHATSAPP_TEMPLATE_LANG=tr
```

Bilmeniz gereken üç şey:

1. **İşletme doğrulaması gerekiyor.** Meta Business hesabı açıp
   işletmenizi doğrulatmanız lazım; birkaç gün sürebiliyor.
2. **Serbest metin gönderemezsiniz.** WhatsApp Business API'de bir
   kişiye ancak o kişi size son 24 saat içinde yazdıysa serbest metin
   gidebiliyor. Bildirimler için Meta'nın **onayladığı bir şablon**
   zorunlu. Şablonu Meta panelinden oluşturup onaya gönderiyorsunuz.
3. Şablon adını `WHATSAPP_TEMPLATE` olarak buraya yazıyorsunuz.

Şablonunuzun gövdesinde iki değişken olmalı; kod başlığı ve metni
sırasıyla oraya koyuyor:

```
{{1}}
{{2}}
```

---

## Yönetici adresleri

Panelde **Site Ayarları → Bildirimler** altında:

* `admin_emails` — virgülle ayrılmış yönetici e-postaları
* `notify_admin_phone` — SMS ve WhatsApp için yönetici numarası
* `notify_email` / `notify_sms` / `notify_whatsapp` — kanal açık mı (1/0)

Panelde hiç yönetici adresi yoksa `NOTIFY_ADMIN_EMAIL` ortam
değişkenine düşülür.

---

## API anahtarları neden panelde değil?

Kanalları panelden açıp kapatıyorsunuz ama anahtarlar ortam
değişkenlerinde duruyor. Sebebi: site ayarları tablosu veritabanında düz
metin. Bir yedek dosyası ya da veritabanı dökümü sızarsa SMS
parolanız da onunla birlikte sızar. Ortam değişkenleri host panelinde
şifreli tutuluyor ve yedeklere girmiyor.

---

## Doğrulama

Panelde **Bildirimler** sekmesi:

1. **Kanal testi** — gerçek bir olay beklemeden kanalı deneyin.
   Sonuç anında görünür; başarısızsa sebebi yazar.
2. **Gönderim kayıtları** — ne gitti, ne gitmedi. `skipped` satırındaki
   açıklama eksik olanı söyler, örneğin "SMS_PROVIDER tanımlı değil".
3. **Şablonlar** — bildirim metinlerini değiştirin. Yer tutucular
   (`{{ad}}`, `{{proje}}`, `{{asama}}` …) panelde listeleniyor.

---

## Sırayla ne yapmalı

1. Resend hesabı açın, alan adını doğrulayın, `RESEND_API_KEY` girin.
2. Panelde Bildirimler → e-posta testi gönderin. Gelirse tamam.
3. `admin_emails` alanına kendi adresinizi yazın.
4. Sitedeki iletişim formunu kendiniz doldurup deneyin.
5. SMS ve WhatsApp'a ihtiyacınız olduğunda yukarıdaki adımları izleyin.

E-posta tek başına çoğu iş için yeterli. SMS ve WhatsApp'ı acele
etmeyin: ikisi de ücretli ve WhatsApp'ın onay süreci var.
