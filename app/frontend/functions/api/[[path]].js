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

  // Istegi hedefe tasiyoruz. Yonlendirme davranisi ve govde boylece aynen korunuyor:
  // giris akisindaki 302 tarayiciya ulasmali, koprude takip edilmemeli.
  const istek = new Request(hedef, request);

  // Bu Request'in baslik listesi degistirilemez, o yuzden kopyasini cikarip
  // fetch'e ayrica veriyoruz.
  const basliklar = new Headers(istek.headers);

  // Arka uc, giris akisindaki donus adresini istegin gordugu alan adindan
  // uretiyor. Araya girdigimiz icin bunu acikca bildirmemiz gerekiyor; yoksa
  // Google'a arka ucun adresi gidiyor ve redirect_uri_mismatch aliniyor.
  // Uygulamanin oncelik sirasi: mgx-external-domain > x-forwarded-host > host.
  basliklar.set('mgx-external-domain', url.host);
  basliklar.set('X-Forwarded-Host', url.host);
  basliklar.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

  try {
    // redirect: manual olmazsa 302'yi kopru kendi takip ediyor ve giris
    // akisi tarayiciya ulasmiyor.
    return await fetch(istek, { headers: basliklar, redirect: 'manual' });
  } catch (e) {
    // Ucretsiz planda arka uc uykudaysa ilk istek zaman asimina dusebilir.
    return new Response(
      JSON.stringify({ detail: 'Arka uca ulasilamadi: ' + String(e) }),
      { status: 502, headers: { 'content-type': 'application/json; charset=utf-8' } }
    );
  }
}
