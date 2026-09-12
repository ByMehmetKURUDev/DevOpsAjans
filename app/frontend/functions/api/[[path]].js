/**
 * Cloudflare Pages Function — `/api/*` isteklerini arka uca taşır.
 *
 * SDK bütün çağrılarını kendi origin'ine göreli atıyor (`/api/v1/...`).
 * Vercel'de bu işi `vercel.json` içindeki rewrite kuralı yapıyor;
 * Cloudflare Pages'te karşılığı bu dosya. İkisi de depoda duruyor,
 * hangisinde yayındaysak o çalışıyor.
 *
 * Arka uç adresi koda gömülmüyor: Pages panelinden `API_ORIGIN` ortam
 * değişkeni olarak veriliyor. Böylece geçici adresten gerçek adrese
 * geçerken tek bir yer değişiyor.
 */
export async function onRequest({ request, env }) {
  const origin = env.API_ORIGIN;

  if (!origin) {
    return new Response(
      JSON.stringify({
        detail:
          'API_ORIGIN ortam değişkeni tanımlı değil. Pages → Settings → Environment variables.',
      }),
      { status: 503, headers: { 'content-type': 'application/json; charset=utf-8' } }
    );
  }

  const url = new URL(request.url);
  const hedef = origin.replace(/\/$/, '') + url.pathname + url.search;

  // Gövde ve başlıklar olduğu gibi taşınıyor; oturum çerezi de öyle.
  const istek = new Request(hedef, request);
  istek.headers.set('X-Forwarded-Host', url.host);
  istek.headers.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

  try {
    return await fetch(istek);
  } catch (e) {
    // Ücretsiz planda arka uç uykudaysa ilk istek zaman aşımına düşebilir.
    return new Response(
      JSON.stringify({ detail: 'Arka uca ulaşılamadı: ' + String(e) }),
      { status: 502, headers: { 'content-type': 'application/json; charset=utf-8' } }
    );
  }
}
