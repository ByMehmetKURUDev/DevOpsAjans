# E-postadan destek talebi — kurulum

Amaç: `destek@destek.mehmetkuru.dev` adresine gelen her e-posta panelde destek
talebi olsun; müşteri bildirim e-postasını "Yanıtla" ile cevapladığında
yazdığı, aynı talebe mesaj olarak düşsün.

Toplam süre: ~15 dakika. Sıra önemli.

## 1. Resend'de alıcı alan adı

Ana alan adının (`mehmetkuru.dev`) e-postası başka yerdeyse (Gmail vb.)
bozulmasın diye **alt alan adı** kullanıyoruz.

1. resend.com → **Domains** → **Add Domain** → `destek.mehmetkuru.dev` yazın.
2. Açılan sayfada **Receiving** (e-posta alma) seçeneğini açın.
3. Resend size bir **MX kaydı** gösterir (ör. `inbound-smtp.…amazonaws.com`, öncelik 10).
4. Alan adınızın DNS panelinde (Cloudflare/Hostinger vb.) bu kaydı ekleyin:
   - Tür: `MX`
   - Ad: `destek`
   - Değer: Resend'in gösterdiği adres
   - Öncelik: Resend'in gösterdiği sayı
5. Resend'de **Verify** deyin. Birkaç dakika içinde "Verified" olur.

## 2. Resend API anahtarı

Zaten bildirim göndermek için bir anahtarınız varsa ve **Full access** ise onu
kullanın. Değilse: **API Keys** → **Create API Key** → izin **Full access** →
değeri kopyalayın (bir kez gösterilir).

## 3. Webhook

1. Yönetim paneli → **Destek → SLA ve hazır cevaplar** → aşağıdaki
   **E-postadan talep** kartında **Resend webhook adresi**ni kopyalayın
   (…`/api/v1/destek/eposta-gelen/resend`).
2. resend.com → **Webhooks** → **Add Webhook**
   - Endpoint URL: kopyaladığınız adres
   - Events: yalnız **email.received**
3. Oluşan webhook'un **Signing Secret**'ını kopyalayın (`whsec_` ile başlar).

## 4. Render ortam değişkenleri

render.com → `mehmetkuru-api` servisi → **Environment** → ekleyin/güncelleyin:

| Değişken | Değer |
| --- | --- |
| `RESEND_API_KEY` | 2. adımdaki anahtar |
| `RESEND_GELEN_IMZA_ANAHTARI` | 3. adımdaki `whsec_…` |
| `NOTIFY_FROM_EMAIL` | ör. `mehmetkuru.dev <bildirim@mehmetkuru.dev>` (zaten varsa dokunmayın) |
| `EPOSTA_GELEN_ANAHTARI` | *İsteğe bağlı.* Yalnız Resend dışında bir sağlayıcı kullanacaksanız |

**Save Changes** → servis kendini yeniden başlatır.

## 5. Gelen adresi panelde yazın

Aynı **E-postadan talep** kartında **Gelen destek adresi** alanına
`destek@destek.mehmetkuru.dev` yazıp **Kaydet**. Bu adres:

- müşteriye giden yanıtlarda **Reply-To** olur (müşteri "Yanıtla" deyince buraya yazar),
- müşteri panelinde "Bu talebe e-postayla da yanıt verebilirsiniz" ipucunu açar.

Kart artık dört satırın da yanında **Tanımlı** göstermeli (genel uç anahtarı
isteğe bağlı).

## 6. Deneyin

1. Kendi kişisel adresinizden `destek@destek.mehmetkuru.dev`'e bir e-posta atın.
2. Kartın altındaki **Son gelen e-postalar** listesinde birkaç saniye içinde
   görünür; panelde yeni talep açılır (kayıtlı müşteri değilseniz
   "Doğrulanmadı" rozetiyle).
3. Talebe panelden yanıt yazın → e-postanıza `[#T-<numara>]` konulu yanıt gelir
   → onu yanıtlayın → yazdığınız aynı talebe düşer.

## Nasıl davranır (kısaca)

- **Otomatik yanıtlar** (izin/tatil mesajları, "noreply", posta listeleri,
  kendi adreslerimiz) talep açmaz; listede "Yok sayıldı" görünür.
- Aynı göndericiden saatte **20**'den fazla ileti yok sayılır.
- Ekler: resim, PDF, Office, txt/csv, zip; tanesi en çok **10 MB**, ileti başına
  en çok **10**. Aşanlar atlanır, talep metnine not düşülür.
- Kayıtlı olmayan bir gönderenden gelen talep açılır ama **Doğrulanmadı**
  işaretlenir ve ona **otomatik cevap gitmez**.
- Birinin talep numarasını (`[#T-5]`) konuya yazıp **başkasının** talebine
  mesaj eklemesi engellenir: mesaj ayrı, doğrulanmamış bir talep olur.
- Aynı e-posta iki kez gelirse (Resend yeniden denerse) ikinci talep açılmaz.

## Sorun giderme

- **Liste boş kalıyor:** Resend → Webhooks → ilgili webhook → son denemelere
  bakın. `401` ise `RESEND_GELEN_IMZA_ANAHTARI` yanlış; `503` ise değişken
  eksik ya da `RESEND_API_KEY` tanımlı değil/yetkisiz.
- **Listede "Hata":** Resend otomatik olarak yeniden dener; tekrar gelince
  işlenir. Sürerse satırdaki neden metnine bakın.
- **Yanıtlar eşleşmiyor:** konuda `[#T-<numara>]` duruyorsa eşleşir; müşteri
  konuyu silmediyse sorun yoktur.
