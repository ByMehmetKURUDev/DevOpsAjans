/**
 * Cloudflare Pages Function — `/q/<kod>` kısa adresleri (Faz 4Q: dinamik QR ve kısa link).
 *
 * QR kodlarının içinde `https://mehmetkuru.dev/q/<kod>` yazıyor. Bu dosya o
 * isteği arka uçtaki `GET /api/v1/q/<kod>` ucuna taşıyor ve yanıtı OLDUĞU
 * GİBİ döndürüyor:
 *
 *   * 302 yönlendirme (hedef adres arka uçta beyaz listeden geçmiş) —
 *     `redirect: 'manual'`: yönlendirmeyi burada izlemiyoruz, ziyaretçinin
 *     tarayıcısı izliyor. Yönlendirmeler her zaman `Cache-Control: no-store`
 *     (hedef değişince eski hedef hiçbir önbellekte kalmasın).
 *   * vCard (.vcf) ve takvim (.ics) dosyaları, pasif (410) ve bulunamadı (404)
 *     HTML sayfaları — arka uç 7 dilde, noindex olarak üretiyor.
 *
 * Arka uca giden başlıklar (analitik ve dil için; çerez ve oturum GİTMİYOR):
 *   * `X-MK-Istemci-IP` ← `CF-Connecting-IP` (arka uç ham IP saklamıyor,
 *     günlük tuzlu özet alıyor — `/api` vekiliyle aynı düzen),
 *   * `X-MK-Ulke` ← `request.cf.country`,
 *   * `User-Agent`, `Referer`, `Accept-Language` (+ önden yükleme işaretleri).
 *
 * Dosya tabanlı yönlendirme: `functions/q/[kod].js` yalnız TEK parçalı
 * `/q/<kod>` adresini karşılar (`/q/a/b` ve `/q` karşılanmaz, SPA'ya düşer).
 * `public/_redirects` kuralları Function yanıtlarına uygulanmadığı için
 * `/* /index.html 200` SPA yedeği bu yolu yutmuyor.
 *
 * Ek ayar gerekmez: `/api` vekilinin kullandığı `API_ORIGIN` ortam
 * değişkeni burada da kullanılıyor.
 */

/* `public/_headers` Function yanıtlarına uygulanmadığı için temel başlıklar burada. */
const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Frame-Options': 'SAMEORIGIN',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};

/** Arka uca iletilen istek başlıkları (küçük harf). */
const ILETILEN_BASLIKLAR = ['user-agent', 'referer', 'accept-language', 'accept', 'purpose', 'sec-purpose', 'x-purpose', 'x-moz'];

function basliklariEkle(yanit, ek = {}) {
  // fetch() yanıtının başlıkları değiştirilemez; kopyası üzerinde çalışılıyor.
  const kopya = new Response(yanit.body, yanit);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  for (const [ad, deger] of Object.entries(ek)) kopya.headers.set(ad, deger);
  return kopya;
}

function hataSayfasi(durum, tr, en) {
  const govde =
    '<!doctype html><html lang="tr"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="robots" content="noindex, nofollow"><title>mehmetkuru.dev</title></head>' +
    '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;' +
    'background:#0b0714;color:#ece8f5;font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center">' +
    `<main><p>${tr}</p><p lang="en" style="color:#b9b2c9">${en}</p></main></body></html>`;
  return basliklariEkle(
    new Response(govde, { status: durum, headers: { 'content-type': 'text/html; charset=utf-8' } }),
    { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' }
  );
}

export async function onRequest({ request, env, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return basliklariEkle(new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } }));
  }

  const origin = env.API_ORIGIN;
  if (!origin) {
    return hataSayfasi(
      503,
      'Kısa bağlantı servisi yapılandırılmamış (API_ORIGIN ortam değişkeni tanımlı değil).',
      'The short link service is not configured (API_ORIGIN is not set).'
    );
  }

  const kod = Array.isArray(params?.kod) ? params.kod.join('/') : String(params?.kod ?? '');
  const hedef = origin.replace(/\/$/, '') + '/api/v1/q/' + encodeURIComponent(kod);
  const url = new URL(request.url);

  const basliklar = new Headers();
  for (const ad of ILETILEN_BASLIKLAR) {
    const deger = request.headers.get(ad);
    if (deger) basliklar.set(ad, deger);
  }
  basliklar.set('X-Forwarded-Host', url.host);
  basliklar.set('X-Forwarded-Proto', url.protocol.replace(':', ''));
  // Worker alt isteğinde arka uca varan CF-Connecting-IP Worker'ın adresi olur;
  // ziyaretçinin adresini ayrıca taşıyoruz (tekil sayım ve hız sınırı için).
  const ziyaretciIp = request.headers.get('CF-Connecting-IP');
  if (ziyaretciIp) basliklar.set('X-MK-Istemci-IP', ziyaretciIp);
  const ulke = request.cf && request.cf.country;
  if (ulke) basliklar.set('X-MK-Ulke', String(ulke));

  let yanit;
  try {
    yanit = await fetch(hedef, { method: request.method, headers: basliklar, redirect: 'manual' });
  } catch (e) {
    // Ücretsiz planda arka uç uykudaysa ilk istek zaman aşımına düşebilir.
    return hataSayfasi(
      502,
      'Bağlantı şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.',
      'The link could not be opened right now. Please try again in a few seconds.'
    );
  }

  const ek = { 'X-Robots-Tag': 'noindex, nofollow' };
  const yonlendirme = yanit.status >= 300 && yanit.status < 400;
  if (yonlendirme || !yanit.headers.has('cache-control')) ek['Cache-Control'] = 'no-store';
  return basliklariEkle(yanit, ek);
}
