/**
 * Cloudflare Pages Function - `/api/*` isteklerini arka uca tasir.
 *
 * SDK butun cagrilarini kendi origin'ine goreli atiyor (`/api/v1/...`).
 * Vercel'de bu isi `vercel.json` icindeki rewrite kurali yapiyor;
 * Cloudflare Pages'te karsiligi bu dosya. Ikisi de depoda duruyor,
 * hangisinde yayindaysak o calisiyor.
 *
 * Arka uc adresi koda gomulmuyor: Pages panelinden `API_ORIGIN` ortam
 * degiskeni olarak veriliyor. Boylece gecici adresten gercek adrese
 * gecerken tek bir yer degisiyor.
 */
export async function onRequest({ request, env }) {
  const origin = env.API_ORIGIN;

  if (!origin) {
    return new Response(
      JSON.stringify({
        detail:
          'API_ORIGIN ortam degiskeni tanimli degil. Pages -> Settings -> Environment variables.',
      }),
      { status: 503, headers: { 'content-type': 'application/json; charset=utf-8' } }
    );
  }

  const url = new URL(request.url);
  const hedef = origin.replace(/\/$/, '') + url.pathname + url.search;

  // Basliklari kopyalayip ustune yaziyoruz. `new Request(hedef, request)`
  // ile gelen baslik listesi degistirilemiyor, o yuzden yeni bir Headers.
  const basliklar = new Headers(request.headers);

  // Arka uc, giris akisindaki donus adresini istegin gordugu alan adindan
  // uretiyor. Araya girdigimiz icin o adres bizim adresimiz olmali, yoksa
  // Google'a arka ucun adresi bildiriliyor ve donusu kullanici goremiyor.
  // Uygulamanin oncelik sirasi: mgx-external-domain > x-forwarded-host > host.
  basliklar.set('mgx-external-domain', url.host);
  basliklar.set('X-Forwarded-Host', url.host);
  basliklar.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

  const govdesiz = request.method === 'GET' || request.method === 'HEAD';
  const istek = new Request(hedef, {
    method: request.method,
    headers: basliklar,
    body: govdesiz ? undefined : request.body,
    // Arka ucun 302'si tarayiciya ulassin; burada takip edersek giris akisi kirilir.
    redirect: 'manual',
  });

  try {
    return await fetch(istek);
  } catch (e) {
    // Ucretsiz planda arka uc uykudaysa ilk istek zaman asimina dusebilir.
    return new Response(
      JSON.stringify({ detail: 'Arka uca ulasilamadi: ' + String(e) }),
      { status: 502, headers: { 'content-type': 'application/json; charset=utf-8' } }
    );
  }
}
