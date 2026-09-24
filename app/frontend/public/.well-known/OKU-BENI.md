# /.well-known/ — ajan keşif dosyaları

`ard.json` (ve öncülü `ai-catalog.json`) **Agentic Resource Discovery**
spesifikasyonunun manifest dosyası: bir sitenin yapay zekâ ajanlarına
sunduğu çağrılabilir kaynakları (MCP sunucusu, A2A ajanı, beceri) listeler.

Bu sitede öyle bir kaynak **yok**, o yüzden `entries` dizisi boş. Boş
bırakmak bilinçli bir tercih: olmayan bir kaynağı listelemek yanlış bilgi
olurdu.

Peki neden dosya hiç olmasın demiyoruz? Çünkü diyemiyoruz. Cloudflare
Pages'te `_redirects` yalnızca 200 ve yönlendirme kodlarını destekliyor,
404 ile yeniden yazma desteklenmiyor; `/*  /index.html  200` kuralı
yüzünden var olmayan HER yol 143 kB'lık index.html'i **200** ile
döndürüyor. Ajan bunu JSON sanıp ayrıştırmaya çalışıyor ve
"Unexpected token '<'" hatası veriyordu — PageSpeed'in "Ajan Tabanlı
Tarama" kategorisi de bu yüzden 3/4 veriyordu.

Yani: "burada bir şey yok"u 404 ile söyleyemediğimiz için geçerli ve boş
bir manifest ile söylüyoruz.

Siteye gerçekten çağrılabilir bir kaynak eklenirse (örneğin dışarıya açık
bir MCP ucu), buraya spesifikasyona uygun bir kayıt eklenmeli:
identifier (urn:air:mehmetkuru.dev:...), displayName, type (IANA ortam
türü) ve url/data'dan tam olarak biri; ayrıca 2-5 representativeQueries.

Spesifikasyon: https://agenticresourcediscovery.org/spec/
