/**
 * Cloudflare Pages Function — `/api/*` isteklerini arka uca taşır.
 *
 * SDK bütün çağrılarını kendi origin'ine göreli atıyor (`/api/v1/...`).
 * Site Cloudflare Pages'te yayında; `/api/*` yönlendirmesini bu dosya yapıyor.
 *
 * Arka uç adresi koda gömülmüyor: Pages panelinden `API_ORIGIN` ortam
 * değişkeni olarak veriliyor. Böylece geçici adresten gerçek adrese
 * geçerken tek bir yer değişiyor.
 */
/*
 * Temel güvenlik başlıkları. `public/_headers` Pages Function yanıtlarına
 * uygulanmıyor (Cloudflare kuralı), bu yüzden `/api/*` yanıtlarına burada
 * ekleniyor. CSP yok: yanıtlar JSON, tarayıcıda belge olarak çizilmiyor.
 * Arka uç aynı başlığı zaten gönderdiyse onunki korunuyor.
 */
const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Frame-Options': 'SAMEORIGIN',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};

function basliklariEkle(yanit) {
  // fetch() yanıtının başlıkları değiştirilemez; kopyası üzerinde çalışılıyor.
  const kopya = new Response(yanit.body, yanit);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  return kopya;
}

export async function onRequest({ request, env }) {
  const origin = env.API_ORIGIN;

  if (!origin) {
    return basliklariEkle(
      new Response(
        JSON.stringify({
          detail:
            'API_ORIGIN ortam değişkeni tanımlı değil. Pages → Settings → Environment variables.',
        }),
        { status: 503, headers: { 'content-type': 'application/json; charset=utf-8' } }
      )
    );
  }

  const url = new URL(request.url);
  const hedef = origin.replace(/\/$/, '') + url.pathname + url.search;

  // Gövde ve başlıklar olduğu gibi taşınıyor; oturum çerezi de öyle.
  const istek = new Request(hedef, request);
  istek.headers.set('X-Forwarded-Host', url.host);
  istek.headers.set('X-Forwarded-Proto', url.protocol.replace(':', ''));
  // Arka uca Worker alt isteğiyle gidildiği için oradaki CF-Connecting-IP
  // Worker'ın adresi olur; ziyaretçinin adresini ayrıca taşıyoruz (IP sınırları).
  const ziyaretciIp = request.headers.get('CF-Connecting-IP');
  if (ziyaretciIp) istek.headers.set('X-MK-Istemci-IP', ziyaretciIp);
  else istek.headers.delete('X-MK-Istemci-IP');

  try {
    return basliklariEkle(await fetch(istek));
  } catch (e) {
    // Ücretsiz planda arka uç uykudaysa ilk istek zaman aşımına düşebilir.
    return basliklariEkle(
      new Response(
        JSON.stringify({ detail: 'Arka uca ulaşılamadı: ' + String(e) }),
        { status: 502, headers: { 'content-type': 'application/json; charset=utf-8' } }
      )
    );
  }
}
