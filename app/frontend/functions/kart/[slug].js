/**
 * Cloudflare Pages Function — `/kart/<slug>` (Faz 4K: dijital kartvizit).
 *
 * Kartvizit sayfası SPA: HTML kabuğu (index.html) her yolda aynı ve ana
 * sayfanın başlık/açıklama/og etiketlerini taşıyor. WhatsApp, LinkedIn,
 * Telegram gibi önizleyiciler JavaScript çalıştırmadığı için paylaşılan kartta
 * ad, unvan ve fotoğraf görünmezdi. Bu dosya:
 *
 *   1. arka uçtan kartın AÇIK ÖZETİNİ alıyor (`GET /api/v1/kart/<slug>/ozet`
 *      — sayılmaz; parolalı kartta kişisel bilgi içermez),
 *   2. SPA kabuğunu `env.ASSETS.fetch` ile alıyor,
 *   3. `HTMLRewriter` ile `<title>`, `meta description`, `og:*`, `twitter:*`,
 *      `canonical` ve `robots` etiketlerini karta göre yeniden yazıyor; ana
 *      sayfaya ait hreflang ve yapısal veriyi (JSON-LD) kaldırıyor; `#root`
 *      içindeki ana sayfa ön çizimini boşaltıyor (kart açılırken ana sayfa
 *      bir an görünmesin).
 *
 * Arama motorları: kart ayarı (`index_acik`) açıksa `index, follow`, değilse
 * (varsayılan) `noindex, nofollow` — hem etikette hem `X-Robots-Tag`'de.
 * Eski slug → 301 yeni adres; bilinmeyen kart 404, pasif 410 (SPA kendi
 * mesajını çiziyor).
 *
 * Arka uç uykuda / hata veriyorsa (Render ücretsiz plan) kabuk OLDUĞU GİBİ
 * dönüyor: sayfa yine açılır, yalnız önizleme genel kalır. Bekleme sınırı 4 sn.
 *
 * Ek ayar gerekmez: `/api` vekilinin kullandığı `API_ORIGIN` yetiyor. Faz 4G:
 * arka uç isteği vekil imzalı (`_ortak/vekil.js`); HTML yanıtına sitenin CSP'si
 * ekleniyor (`_ortak/csp.js` — `_headers` Function yanıtlarına uygulanmıyor).
 * Dosya tabanlı yönlendirme: yalnız TEK parçalı `/kart/<slug>` (değişmez kod da
 * buradan geçer: `/kart/AbC2xyz`).
 */

import { cspBasliklari } from '../_ortak/csp.js';
import { vekilBasliklari } from '../_ortak/vekil.js';

const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Frame-Options': 'SAMEORIGIN',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};
const ZAMAN_ASIMI_MS = 4000;
const SITE_ADI = 'By Mehmet KURU Dev';
/** slug (küçük harf) ya da değişmez kod (büyük harf içerir). */
const ADRES_DESENI = /^[A-Za-z0-9][A-Za-z0-9-]{1,48}[A-Za-z0-9]$/;

/** Kabukta kaldırılan (ana sayfaya ait) etiketler; yerine kartınkiler ekleniyor. */
export const KALDIRILANLAR = [
  'meta[name="description"]',
  'meta[property^="og:"]',
  'meta[name^="twitter:"]',
  'meta[name="robots"]',
  'link[rel="canonical"]',
  'link[rel="alternate"][hreflang]',
  'script[type="application/ld+json"]',
];

export function kacis(metin) {
  return String(metin ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function guvenliAdres(adres, taban) {
  try {
    const u = new URL(String(adres), taban);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null;
  } catch {
    return null;
  }
}

/** Özet → yazılacak değerler (başlık, robots, dil ve `<head>` sonuna eklenecek etiketler). */
export function etiketler(ozet, istekAdresi) {
  const aktif = ozet && (ozet.durum === 'aktif' || ozet.durum === 'kilitli');
  const index = Boolean(ozet && ozet.durum === 'aktif' && ozet.index === true);
  const robots = index ? 'index, follow' : 'noindex, nofollow';
  const dil = /^[a-z]{2}$/.test(ozet?.dil || '') ? ozet.dil : 'tr';
  const baslik = (aktif && ozet.baslik) || 'Dijital kartvizit · mehmetkuru.dev';
  const aciklama = (aktif && ozet.aciklama) || '';
  const kanonik = guvenliAdres(ozet?.kart_adresi || istekAdresi, istekAdresi) || istekAdresi;
  // Parolalı kartın önizlemesinde görsel YOK (özet zaten vermiyor; burada da kesin).
  const gorsel = ozet?.durum === 'aktif' && ozet.gorsel ? guvenliAdres(ozet.gorsel, istekAdresi) : null;
  const m = (ad, deger) => `<meta name="${ad}" content="${kacis(deger)}">`;
  const p = (ad, deger) => `<meta property="${ad}" content="${kacis(deger)}">`;
  const parcalar = [m('robots', robots)];
  if (aktif) {
    parcalar.push(
      m('description', aciklama),
      `<link rel="canonical" href="${kacis(kanonik)}">`,
      p('og:type', 'profile'),
      p('og:site_name', SITE_ADI),
      p('og:title', baslik),
      p('og:description', aciklama),
      p('og:url', kanonik),
      p('og:locale', ozet.locale || 'tr_TR'),
      m('twitter:card', 'summary'),
      m('twitter:title', baslik),
      m('twitter:description', aciklama)
    );
    if (gorsel) {
      parcalar.push(p('og:image', gorsel), m('twitter:image', gorsel));
      if (ozet.gorsel_genislik) parcalar.push(p('og:image:width', ozet.gorsel_genislik));
      if (ozet.gorsel_yukseklik) parcalar.push(p('og:image:height', ozet.gorsel_yukseklik));
      if (ozet.gorsel_alt) parcalar.push(p('og:image:alt', ozet.gorsel_alt), m('twitter:image:alt', ozet.gorsel_alt));
    }
  }
  return { baslik, robots, dil, yon: dil === 'ar' ? 'rtl' : 'ltr', eklenecek: parcalar.join('') };
}

/** Üretim yolu: HTMLRewriter (akışlı, Cloudflare çalışma zamanı). */
export function htmlRewriterIle(yanit, e) {
  let r = new HTMLRewriter();
  for (const secici of KALDIRILANLAR) {
    r = r.on(secici, { element: (el) => el.remove() });
  }
  return r
    .on('html', {
      element: (el) => {
        el.setAttribute('lang', e.dil);
        el.setAttribute('dir', e.yon);
      },
    })
    .on('title', { element: (el) => el.setInnerContent(e.baslik) })
    .on('head', { element: (el) => el.append(e.eklenecek, { html: true }) })
    .on('#root', { element: (el) => el.setInnerContent('') })
    .transform(yanit);
}

/** HTMLRewriter olmayan ortam (Node testi) için basit yedek: aynı kurallar metin üzerinde. */
export function metinIle(html, e) {
  let h = String(html);
  const sil = [
    /<meta\b[^>]*\bname="description"[^>]*>\s*/gi,
    /<meta\b[^>]*\bproperty="og:[^"]*"[^>]*>\s*/gi,
    /<meta\b[^>]*\bname="twitter:[^"]*"[^>]*>\s*/gi,
    /<meta\b[^>]*\bname="robots"[^>]*>\s*/gi,
    /<link\b[^>]*\brel="canonical"[^>]*>\s*/gi,
    /<link\b[^>]*\brel="alternate"[^>]*\bhreflang="[^"]*"[^>]*>\s*/gi,
    /<script\b[^>]*type="application\/ld\+json"[^>]*>[\s\S]*?<\/script>\s*/gi,
  ];
  for (const d of sil) h = h.replace(d, '');
  h = h.replace(/<title>[\s\S]*?<\/title>/i, `<title>${kacis(e.baslik)}</title>`);
  h = h.replace(/<\/head>/i, `${e.eklenecek}</head>`);
  h = h.replace(/<html\b([^>]*)>/i, (_, nitelikler) => {
    const temiz = nitelikler.replace(/\s(lang|dir)="[^"]*"/gi, '');
    return `<html${temiz} lang="${e.dil}" dir="${e.yon}">`;
  });
  const bas = h.indexOf('<div id="root">');
  const govdeSonu = h.lastIndexOf('</body>');
  if (bas >= 0 && govdeSonu > bas) {
    const kapanis = h.lastIndexOf('</div>', govdeSonu);
    if (kapanis > bas) h = h.slice(0, bas) + '<div id="root"></div>' + h.slice(kapanis + 6);
  }
  return h;
}

async function ozetAl(origin, adres, istek, env) {
  const hedef = origin.replace(/\/$/, '') + '/api/v1/kart/' + encodeURIComponent(adres) + '/ozet';
  const basliklar = new Headers({ Accept: 'application/json' });
  const dil = istek.headers.get('accept-language');
  if (dil) basliklar.set('Accept-Language', dil);
  basliklar.set('X-Forwarded-Host', new URL(istek.url).host);
  vekilBasliklari(basliklar, istek, env);
  const yanit = await fetch(hedef, {
    method: 'GET',
    headers: basliklar,
    signal: AbortSignal.timeout(ZAMAN_ASIMI_MS),
  });
  if (!yanit.ok) throw new Error('ozet ' + yanit.status);
  const veri = await yanit.json();
  if (!veri || typeof veri !== 'object' || typeof veri.durum !== 'string') throw new Error('ozet bicimi');
  return veri;
}

function guvenlikEkle(yanit, ek = {}) {
  const kopya = new Response(yanit.body, yanit);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  for (const [ad, deger] of Object.entries(ek)) kopya.headers.set(ad, deger);
  return kopya;
}

export async function onRequest({ request, env, params }) {
  const url = new URL(request.url);
  // SPA kabuğu: kök index.html (pretty URL — `/index.html` 308 verirdi). Koşullu
  // başlıklar (If-None-Match…) bilerek iletilmiyor: kabuğun 304'ü karta uymaz.
  const kabuk = await env.ASSETS.fetch(new Request(new URL('/', url), { method: 'GET' }));
  if (request.method !== 'GET' && request.method !== 'HEAD') return kabuk;
  const adres = Array.isArray(params?.slug) ? params.slug.join('/') : String(params?.slug ?? '');
  if (!kabuk.ok) return kabuk;
  if (!env.API_ORIGIN || !ADRES_DESENI.test(adres)) return guvenlikEkle(kabuk, cspBasliklari());

  let ozet;
  try {
    ozet = await ozetAl(env.API_ORIGIN, adres, request, env);
  } catch {
    // arka uç kapalı / yavaş: sayfa yine açılsın, önizleme genel kalsın
    return guvenlikEkle(kabuk, cspBasliklari());
  }

  if (ozet.durum === 'yonlendir' && typeof ozet.yonlendir === 'string' && ADRES_DESENI.test(ozet.yonlendir)) {
    return guvenlikEkle(
      new Response(null, {
        status: 301,
        headers: { Location: `/kart/${encodeURIComponent(ozet.yonlendir)}${url.search}`, 'Cache-Control': 'no-store' },
      })
    );
  }

  const e = etiketler(ozet, url.toString());
  const durum = ozet.durum === 'yok' ? 404 : ozet.durum === 'pasif' ? 410 : 200;
  const yazilmis =
    typeof HTMLRewriter === 'function'
      ? htmlRewriterIle(kabuk, e)
      : new Response(metinIle(await kabuk.text(), e), kabuk);

  const basliklar = new Headers(yazilmis.headers);
  // İçerik değişti: kabuğun uzunluğu ve ETag'i artık geçerli değil.
  basliklar.delete('content-length');
  basliklar.delete('etag');
  basliklar.delete('last-modified');
  basliklar.set('content-type', 'text/html; charset=utf-8');
  basliklar.set('Cache-Control', 'no-cache');
  basliklar.set('X-Robots-Tag', e.robots);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!basliklar.has(ad)) basliklar.set(ad, deger);
  }
  for (const [ad, deger] of Object.entries(cspBasliklari())) basliklar.set(ad, deger);
  return new Response(request.method === 'HEAD' ? null : yazilmis.body, { status: durum, headers: basliklar });
}
