/**
 * Cloudflare Pages Function — `/etkinlik/*` (Faz 6E: etkinlik ve bilet).
 *
 *   /etkinlik/<slug>                  etkinlik sayfası + kayıt formu
 *   /etkinlik/<slug>/bilet/<jeton>    imzalı bilet sayfası (QR, PDF, takvim, iptal)
 *   /etkinlik/giris/<jeton>           görevli bağlantısı: kapı okutucu (girişsiz, süreli)
 *   /etkinlik/okut/<id>               panel okutucusu (oturum + ekip izni)
 *
 * Site bir SPA; bu adresler için prerender HTML yok. Önizleyiciler ve arama motorları
 * JavaScript çalıştırmadan `<head>`e baktığı için (randevu Function'ı deseni):
 *
 *   1. Etkinlik sayfasında arka uçtan kısa özet (`GET /api/v1/etkinlik/<slug>/ozet`,
 *      `API_ORIGIN`; vekil imzası `_ortak/vekil.js`).
 *   2. `env.ASSETS.fetch` ile uygulama kabuğu (index.html).
 *   3. `HTMLRewriter`: title, description, og/twitter, canonical, robots; ana sayfaya ait
 *      hreflang ve JSON-LD kaldırılır; `#root`a sade iskelet.
 *
 * robots: etkinlik ayarı "arama motorlarında görünsün" kapalıysa (varsayılan) `noindex,
 * nofollow` + `X-Robots-Tag`. Açıksa `index, follow` ve schema.org **Event JSON-LD**
 * (`<script type="application/ld+json" data-mk-etkinlik>`; veri bloğu — çalıştırılmadığı için
 * CSP'nin script-src kuralına takılmaz; `<` kaçışlı). Online bağlantı JSON-LD'de ASLA yok.
 *
 * Bilet / görevli / panel okutucu: HER ZAMAN noindex, arka uca hiç sorulmuyor (jeton bir yetki
 * belgesi), `Referrer-Policy: no-referrer`. Okutucu sayfalarında kamera izni AÇIK
 * (`Permissions-Policy: camera=(self)`); sitenin geri kalanında `camera=()`.
 * `?gomulu=1` (public/etkinlik-widget.js): `X-Frame-Options` yok, `frame-ancestors *`.
 * Arka uç kapalı/yavaşsa (ücretsiz plan uyur) kabuk + noindex; istemci kendisi yükler.
 * `public/_headers` Function yanıtlarına uygulanmadığı için temel başlıklar burada.
 */

import { cspBasliklari } from '../_ortak/csp.js';
import { vekilBasliklari } from '../_ortak/vekil.js';

const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};
export const IZINLER = 'camera=(), microphone=(), geolocation=(), interest-cohort=()';
export const IZINLER_KAMERA = 'camera=(self), microphone=(), geolocation=(), interest-cohort=()';

/** Arka uç bu kadar sürede yanıt vermezse kabuk döner (önizleyiciler beklemez). */
export const ZAMAN_ASIMI_MS = 2500;
const SLUG = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;
const AYRILMIS = new Set(['giris', 'okut', 'bilet']);
const SIPARIS_JETONU = /^\d{1,12}-[0-9a-f]{32}$/;
const GOREVLI_JETONU = /^\d{1,12}-\d{1,6}-\d{9,11}-[0-9a-f]{32}$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const OG_YERELI = { tr: 'tr_TR', en: 'en_US', de: 'de_DE', ru: 'ru_RU', zh: 'zh_CN', hi: 'hi_IN', ar: 'ar_AR' };
export const EK = {
  etkinlik: { tr: 'Etkinlik', en: 'Event', de: 'Veranstaltung', ru: 'Мероприятие', zh: '活动', hi: 'कार्यक्रम', ar: 'فعالية' },
  bilet: { tr: 'Biletiniz', en: 'Your ticket', de: 'Ihr Ticket', ru: 'Ваш билет', zh: '您的门票', hi: 'आपका टिकट', ar: 'تذكرتك' },
  giris: { tr: 'Kapı girişi', en: 'Door check-in', de: 'Einlasskontrolle', ru: 'Контроль входа', zh: '入场检票', hi: 'प्रवेश जाँच', ar: 'تسجيل الدخول عند الباب' },
};

/** Öznitelik ve metin için HTML kaçışı. */
export function kacis(metin) {
  return String(metin ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function kisalt(metin, sinir) {
  const tek = String(metin ?? '').replace(/\s+/g, ' ').trim();
  return tek.length > sinir ? tek.slice(0, sinir - 1).trimEnd() + '…' : tek;
}

/** JSON-LD'yi `<script>` içine güvenle koymak için: `<`, `>`, `&`, U+2028/9 kaçışlı. */
export function jsonGuvenli(veri) {
  return JSON.stringify(veri)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

/** Yol parçaları → ne istendiği. */
export function yolCoz(parcalar) {
  const p = (Array.isArray(parcalar) ? parcalar : parcalar ? [parcalar] : []).map((x) => String(x));
  if (p.length === 2 && p[0] === 'giris') return { tur: 'giris', gecerli: GOREVLI_JETONU.test(p[1]) };
  if (p.length === 2 && p[0] === 'okut') return { tur: 'okut', gecerli: /^\d{1,12}$/.test(p[1]) };
  if (p.length === 3 && p[1] === 'bilet' && SLUG.test(p[0].toLowerCase())) {
    return { tur: 'bilet', slug: p[0].toLowerCase(), gecerli: SIPARIS_JETONU.test(p[2]) };
  }
  if (p.length === 1 && SLUG.test(p[0].toLowerCase()) && !AYRILMIS.has(p[0].toLowerCase())) {
    return { tur: 'sayfa', slug: p[0].toLowerCase() };
  }
  return { tur: 'yok' };
}

export function basliklariEkle(yanit, ek = {}, gomulu = false) {
  const kopya = new Response(yanit.body, yanit);
  for (const ad of ['etag', 'last-modified', 'content-length', 'x-frame-options']) kopya.headers.delete(ad);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  kopya.headers.set('Permissions-Policy', IZINLER);
  // Faz 4G CSP'si (tek kaynak `_ortak/csp.js`); gömülü pencerede yalnız frame-ancestors gevşer.
  for (const [ad, deger] of Object.entries(cspBasliklari(gomulu ? { cerceveIzni: '*' } : {}))) kopya.headers.set(ad, deger);
  if (!gomulu) kopya.headers.set('X-Frame-Options', 'SAMEORIGIN');
  for (const [ad, deger] of Object.entries(ek)) kopya.headers.set(ad, deger);
  return kopya;
}

/** Arka uçtan JSON: `{durum, veri}`; ağ hatası / zaman aşımı / 5xx → `{durum: 0}`. */
export async function jsonAl(origin, yol, request, env) {
  const adres = `${origin.replace(/\/$/, '')}${yol}`;
  const iptal = new AbortController();
  const zaman = setTimeout(() => iptal.abort(), ZAMAN_ASIMI_MS);
  try {
    const basliklar = vekilBasliklari(new Headers({ accept: 'application/json' }), request, env);
    const y = await fetch(adres, { headers: basliklar, signal: iptal.signal, cf: { cacheTtl: 60, cacheEverything: true } });
    if (y.status === 404 || y.status === 410) return { durum: y.status };
    if (!y.ok) return { durum: 0 };
    return { durum: 200, veri: await y.json() };
  } catch {
    return { durum: 0 };
  } finally {
    clearTimeout(zaman);
  }
}

/** Yükleniyor iskeleti (React ilk çizimde yerine koyar). Satır içi stil; betik yok. */
function iskelet(ad, renk, gomulu, karanlik) {
  const r = /^#[0-9a-fA-F]{6}$/.test(renk || '') ? renk : '#7c3aed';
  const zemin = gomulu ? 'transparent' : karanlik ? '#09090b' : '#f7f7f8';
  return (
    `<div style="min-height:${gomulu ? '320px' : '100vh'};display:flex;flex-direction:column;align-items:center;justify-content:center;` +
    `gap:14px;background:${zemin};color:${karanlik ? '#fafafa' : '#18181b'};font:600 18px/1.4 system-ui,-apple-system,sans-serif;padding:24px;text-align:center">` +
    `<div style="width:40px;height:40px;border-radius:50%;border:3px solid ${r};border-top-color:transparent" aria-hidden="true"></div>` +
    (ad ? `<p style="margin:0">${kacis(ad)}</p>` : '') +
    '</div>'
  );
}

/** Kabuğun `<head>`ini yeniden yazar (HTMLRewriter). `s.jsonld` varsa Event JSON-LD eklenir. */
export function yenidenYaz(kabuk, s) {
  const etiketler = [`<meta name="description" content="${kacis(s.aciklama)}">`, `<meta name="robots" content="${s.robots}">`];
  if (s.adres) etiketler.push(`<link rel="canonical" href="${kacis(s.adres)}">`);
  if (s.ozetVar) {
    etiketler.push(
      '<meta property="og:type" content="website">',
      `<meta property="og:site_name" content="${kacis(s.siteAdi || 'By Mehmet KURU Dev')}">`,
      `<meta property="og:title" content="${kacis(s.baslik)}">`,
      `<meta property="og:description" content="${kacis(s.aciklama)}">`,
      `<meta property="og:url" content="${kacis(s.adres)}">`,
      `<meta property="og:locale" content="${OG_YERELI[s.dil] || 'tr_TR'}">`,
      `<meta name="twitter:card" content="${s.gorsel ? 'summary_large_image' : 'summary'}">`,
      `<meta name="twitter:title" content="${kacis(s.baslik)}">`,
      `<meta name="twitter:description" content="${kacis(s.aciklama)}">`
    );
    if (s.gorsel) {
      etiketler.push(`<meta property="og:image" content="${kacis(s.gorsel)}">`, `<meta name="twitter:image" content="${kacis(s.gorsel)}">`);
    }
  }
  if (s.jsonld) etiketler.push(`<script type="application/ld+json" data-mk-etkinlik>${jsonGuvenli(s.jsonld)}</script>`);
  return new HTMLRewriter()
    .on('html', {
      element(e) {
        e.setAttribute('lang', s.dil);
        e.setAttribute('dir', s.dil === 'ar' ? 'rtl' : 'ltr');
      },
    })
    .on('title', {
      element(e) {
        e.setInnerContent(s.baslik);
      },
    })
    .on('meta', {
      element(e) {
        const ad = (e.getAttribute('name') || '').toLowerCase();
        const ozellik = (e.getAttribute('property') || '').toLowerCase();
        if (ad === 'description' || ad === 'robots' || ad.startsWith('twitter:') || ozellik.startsWith('og:')) e.remove();
      },
    })
    .on('link', {
      element(e) {
        const rel = (e.getAttribute('rel') || '').toLowerCase();
        if (rel === 'canonical' || rel === 'alternate') e.remove();
      },
    })
    .on('script', {
      element(e) {
        if ((e.getAttribute('type') || '').toLowerCase() === 'application/ld+json') e.remove();
      },
    })
    .on('head', {
      element(e) {
        e.append(etiketler.join(''), { html: true });
      },
    })
    .on('div#root', {
      element(e) {
        e.setInnerContent(iskelet(s.sayfaAdi, s.renk, s.gomulu, s.karanlik), { html: true });
      },
    })
    .transform(kabuk);
}

export async function kabukAl(env, request) {
  if (!env.ASSETS || typeof env.ASSETS.fetch !== 'function') return null;
  try {
    const y = await env.ASSETS.fetch(new Request(new URL('/', request.url), { method: 'GET', headers: { accept: 'text/html' } }));
    return y.ok ? y : null;
  } catch {
    return null;
  }
}

export function sadeSayfa(durum) {
  const govde =
    '<!doctype html><html lang="tr"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="robots" content="noindex, nofollow"><title>mehmetkuru.dev</title></head>' +
    '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;' +
    'background:#f7f7f8;color:#18181b;font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center">' +
    '<main><p>Etkinlik sayfası şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.</p>' +
    '<p lang="en" style="color:#71717a">The event page could not be opened right now. Please try again in a few seconds.</p></main></body></html>';
  return basliklariEkle(new Response(govde, { status: durum, headers: { 'content-type': 'text/html; charset=utf-8' } }), {
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
  });
}

export const BOS = { robots: 'noindex, nofollow', aciklama: '', adres: '', sayfaAdi: '', ozetVar: false, gorsel: null, renk: null, jsonld: null };

function tarihMetni(iso, tz, dil) {
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short', timeZone: tz || 'Europe/Istanbul' }).format(new Date(iso));
  } catch {
    return String(iso || '').slice(0, 16).replace('T', ' ');
  }
}

export async function onRequest({ request, env, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return basliklariEkle(new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } }));
  }
  const url = new URL(request.url);
  const gomulu = url.searchParams.get('gomulu') === '1';
  const dilParam = (url.searchParams.get('dil') || '').slice(0, 2).toLowerCase();
  const yol = yolCoz(params?.yol);

  const kabuk = await kabukAl(env, request);
  if (!kabuk) return sadeSayfa(502);

  const kapali = (durum, baslik, dil = 'tr', ek = {}, karanlik = false) => {
    const yazilan = yenidenYaz(kabuk, { ...BOS, dil, baslik, gomulu, karanlik });
    return basliklariEkle(
      new Response(yazilan.body, { status: durum, headers: yazilan.headers }),
      { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow', ...ek },
      gomulu
    );
  };

  const dilSec = (yedek) => (DILLER.includes(dilParam) ? dilParam : DILLER.includes(yedek) ? yedek : 'tr');

  if (yol.tur === 'giris' || yol.tur === 'okut') {
    // Kapı okutucu: arka uca sorulmuyor (jeton/oturum istemcide doğrulanır); kamera izni yalnız burada.
    const dil = dilSec('tr');
    return kapali(yol.gecerli ? 200 : 404, `${EK.giris[dil]} | By Mehmet KURU Dev`, dil, {
      'Permissions-Policy': IZINLER_KAMERA,
      'Referrer-Policy': 'no-referrer',
    }, true);
  }
  if (yol.tur === 'bilet') {
    const dil = dilSec('tr');
    return kapali(yol.gecerli ? 200 : 404, `${EK.bilet[dil]} | By Mehmet KURU Dev`, dil, { 'Referrer-Policy': 'no-referrer' });
  }
  if (yol.tur === 'yok') return kapali(404, 'By Mehmet KURU Dev');

  let sonuc = { durum: 0 };
  if (env.API_ORIGIN) sonuc = await jsonAl(env.API_ORIGIN, `/api/v1/etkinlik/${encodeURIComponent(yol.slug)}/ozet`, request, env);
  if (sonuc.durum !== 200) {
    // 404 / 410: SPA sade sayfasını çizer. 0 (arka uç kapalı): kabuk + noindex, istemci yükler.
    return kapali(sonuc.durum === 0 ? 200 : sonuc.durum, 'By Mehmet KURU Dev');
  }

  const v = sonuc.veri || {};
  const dil = dilSec(v.dil);
  const sayfaAdi = kisalt(v.baslik || yol.slug, 120);
  const zaman = v.baslangic ? tarihMetni(v.baslangic, v.saat_dilimi, dil) : '';
  const baslik = `${sayfaAdi} | ${EK.etkinlik[dil]}`;
  const aciklama = kisalt(v.aciklama || [sayfaAdi, zaman].filter(Boolean).join(' · '), 200);
  const adres = typeof v.adres_url === 'string' && /^https?:\/\//.test(v.adres_url) ? v.adres_url : `${url.origin}/etkinlik/${yol.slug}`;
  const indekslenebilir = v.indekslenebilir === true && !gomulu;
  const gorsel = typeof v.gorsel === 'string' && /^https?:\/\//.test(v.gorsel) ? v.gorsel : null;
  const jsonld = indekslenebilir && v.jsonld && typeof v.jsonld === 'object' ? v.jsonld : null;

  const yazilan = yenidenYaz(kabuk, {
    dil, robots: indekslenebilir ? 'index, follow' : 'noindex, nofollow', baslik, aciklama, adres, sayfaAdi,
    ozetVar: true, gorsel, renk: v.renk, gomulu, jsonld,
  });
  const ek = { 'Cache-Control': 'public, max-age=0, must-revalidate' };
  if (!indekslenebilir) ek['X-Robots-Tag'] = 'noindex, nofollow';
  return basliklariEkle(new Response(yazilan.body, { status: 200, headers: yazilan.headers }), ek, gomulu);
}
