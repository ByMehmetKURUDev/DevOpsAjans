/**
 * Prerender edilmeyen (yalnız istemcide çizilen) rotalar — TEK KAYNAK (Parti 14).
 *
 * İki yerde kullanılıyor:
 *   1. `check-routes.mjs`: App.tsx'te olup prerender ağacında olmayan her rota
 *      burada listelenmiş olmalı, yoksa derleme durur.
 *   2. `spa-ve-404.mjs`: Cloudflare Pages `_redirects` dosyasına bu rotalar için
 *      `/index.html 200` yeniden yazma kuralı üretiliyor. Listede olmayan,
 *      dosyası da olmayan her adres `404.html` ile GERÇEK 404 durum kodu alıyor
 *      (önceden `/* /index.html 200` her şeyi 200'le yutuyordu: soft-404).
 *
 * Yeni bir istemci rotası eklerken: App.tsx + bu liste. Başka yere gerek yok.
 */

// Prerender bilinçli olarak kapsamıyor: kimliği doğrulanmış paneller ve
// auth geri dönüş sayfaları arama motorlarına açılmamalı.
export const INTENTIONALLY_NOT_PRERENDERED = new Set([
  '/client',
  '/admin',
  '/auth/callback',
  '/auth/error',
  // Ödeme bağlantısı jetona özel: her adres tek bir faturaya ait,
  // önceden üretilecek bir HTML'i yok ve dizine girmemeli.
  '/ode/:jeton',
  // Site analiz raporu da jetona özel (e-postayla gidiyor), noindex.
  '/rapor/:jeton',
  // İmzalı işlem bağlantısı: jetona özel, girişsiz karar sayfası, noindex.
  '/islem/:jeton',
  // Faz 5I: girişsiz içerik onayı — jetona özel (noindex).
  '/icerik-onay/:jeton',
  // Müşterinin durum sayfası: dinamik, müşteriye ait; varsayılan noindex (Faz 2A).
  '/durum/:slug',
  'durum/:slug',
  // Faz 2C: jetona özel dosya paylaşımı ve aylık müşteri raporu (noindex).
  '/paylas/:jeton',
  '/rapor-aylik/:jeton',
  // Faz 2E: hesap ekibi daveti — jetona özel, kişiye özel (noindex).
  '/hesap-davet/:jeton',
  // Faz 3C: gömülebilir CRM formunun doğrudan bağlantısı — dinamik, noindex.
  '/form/:anahtar',
  // Faz 3T: girişsiz teklif ve sözleşme imza sayfaları — jetona özel (noindex).
  '/teklif/:jeton',
  '/sozlesme/:jeton',
  // Faz 4K: dijital kartvizit ve Google yorum sayfası — kişiye/işletmeye ait, dinamik;
  // paylaşım önizlemesini Pages Function yazıyor (functions/kart/[slug].js). Dil önekli
  // adresler köke yönleniyor.
  '/kart/:slug',
  '/yorum/:slug',
  '/:lang/kart/:slug',
  '/:lang/yorum/:slug',
  // Faz 4M: herkese açık QR menü / katalog — dinamik, mağazaya ait; paylaşım
  // önizlemesini Pages Function yazıyor (functions/menu/[slug].js).
  '/menu/:slug',
  // Faz 5R: herkese açık randevu sayfası ve imzalı yönetim bağlantısı — dinamik,
  // sahibine ait; paylaşım önizlemesini Pages Function yazıyor (functions/randevu/[[yol]].js).
  '/randevu/:slug',
  '/randevu/:slug/:tur',
  '/randevu/yonet/:jeton',
  // Faz 5A: herkese açık AI asistan (tam sayfa ve gömülü pencere) — dinamik, noindex; CSP'yi
  // ve gömülüde frame-ancestors iznini Pages Function yazıyor (functions/asistan/[[yol]].js).
  '/asistan/:anahtar',
  // Faz 5M: bülten abonelik formu, çift onay ve ret/tercih sayfası — dinamik, jetona/
  // forma özel; prerender yok, noindex (sayfa + `_headers` X-Robots-Tag).
  '/bulten/:anahtar',
  '/bulten/onay/:jeton',
  '/bulten/tercih/:jeton',
  // Faz 6S: saha servisi — servis müşterisinin imzalı sayfası (iş durumu, servis formu,
  // memnuniyet); jetona özel, prerender yok, noindex (sayfa + `_headers` X-Robots-Tag).
  '/servis/:jeton',
  // Faz 6E: etkinlik sayfası, imzalı bilet ve kapı (görevli/panel okutucu) bağlantıları, hesabın
  // etkinlik listesi — dinamik, sahibine ait; önizleme/robots/JSON-LD'yi Pages Function yazıyor
  // (functions/etkinlik/[[yol]].js, functions/etkinlikler/[slug].js).
  '/etkinlik/:slug',
  '/etkinlik/:slug/bilet/:jeton',
  '/etkinlik/giris/:jeton',
  '/etkinlik/okut/:eid',
  '/etkinlikler/:slug',
  // Faz 6K: eğitim — kurs sayfası, imzalı öğrenci sayfası, oturum QR yoklaması, sertifika doğrulama,
  // panel okutucusu, hesabın kurs listesi; dinamik, sahibine ait; önizleme/robots/JSON-LD'yi Pages
  // Function yazıyor (functions/egitim/[[yol]].js).
  '/egitim/:slug',
  '/egitim/ogrenci/:jeton',
  '/egitim/yoklama/:jeton',
  '/egitim/sertifika/:kod',
  '/egitim/okut/:kid/:oid',
  '/egitim/kurum/:slug',
  // Faz 6I: girişsiz personel sayfası (vardiyalar, izin bakiyesi, izin talebi) — jetona özel, prerender
  // yok, noindex (sayfa + `_headers` X-Robots-Tag).
  '/personel/:jeton',
  // Faz 6H: hukuk bürosunun imzalı müvekkil portalı; kişiye özel, her zaman noindex (functions/hukuk/[[yol]].js).
  '/hukuk/muvekkil/:jeton',
  // Faz 6T: girişsiz toplantı katılım yanıtı (davetteki kişiye özel bağlantı) — jetona özel, prerender yok,
  // noindex (sayfa + `_headers` X-Robots-Tag).
  '/toplanti-yanit/:jeton',
]);

/**
 * Prerender EDİLEN ama derlemeden sonra da yenisi eklenebilen rotalar. Yazı
 * panelden yayımlanınca bir sonraki derlemeye kadar statik dosyası yok; istemci
 * çizsin diye bunlara da yeniden yazma kuralı veriliyor. (Var olmayan bir yazı
 * adresi bu yüzden 200 + "bulunamadı" ekranı alıyor; kabul edilen tek istisna.)
 */
export const SONRADAN_EKLENEBILEN = ['/blog/:slug'];
