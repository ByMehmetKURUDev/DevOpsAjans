/**
 * Cloudflare Pages Function — `/menu/<slug>` (Faz 4M: QR menü ve WhatsApp katalog mağazası).
 *
 * Site bir SPA: `/menu/<slug>` için prerender edilmiş HTML yok, istemci menüyü
 * çalışma zamanında çiziyor. WhatsApp/Instagram/Facebook önizleyicileri ve arama
 * motorları ise JavaScript çalıştırmadan `<head>`e bakıyor. Bu dosya:
 *
 *   1. Arka uçtan menünün kısa özetini alıyor (`GET /api/v1/menu/<slug>/ozet`,
 *      `API_ORIGIN` — `/api` vekili ve `/q/<kod>` ile aynı değişken; ek ayar yok).
 *      `?urun=<id>` varsa ürünün adı/açıklaması/görseli, `?dil=xx` varsa o dil.
 *   2. `env.ASSETS.fetch` ile uygulamanın kabuğunu (index.html) alıyor.
 *   3. `HTMLRewriter` ile `<title>`, description, `og:*`, `twitter:*`, canonical
 *      ve robots'u menüye göre yeniden yazıyor; kabuğun ana sayfaya ait
 *      hreflang bağlantılarını ve yapısal verisini kaldırıyor; `#root`un içindeki
 *      ana sayfa çizimini sade bir yükleniyor iskeletiyle değiştiriyor (ajansın
 *      ana sayfası menünün önünde bir an bile görünmesin).
 *
 * robots: mağaza ayarı "arama motorlarında görünsün" kapalıysa (varsayılan)
 * `noindex, nofollow` + `X-Robots-Tag`. Menü yoksa 404, pasifse 410 (SPA kendi
 * sade sayfasını çiziyor). Arka uç kapalı / yavaşsa (ücretsiz plan uyur) kabuk
 * olduğu gibi döner — yalnız noindex eklenir ve iskelet konur; menüyü istemci
 * kendisi yükler.
 *
 * Dosya tabanlı yönlendirme yalnız TEK parçalı `/menu/<slug>`i karşılıyor.
 * `public/_headers` Function yanıtlarına uygulanmadığı için temel başlıklar (Faz 4G:
 * ve sitenin CSP'si, `_ortak/csp.js`) burada; arka uç isteği vekil imzalı.
 */

import { cspBasliklari } from '../_ortak/csp.js';
import { vekilBasliklari } from '../_ortak/vekil.js';

const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Frame-Options': 'SAMEORIGIN',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};

/** Arka uç bu kadar sürede yanıt vermezse kabuk döner (önizleyiciler beklemez). */
export const ZAMAN_ASIMI_MS = 2500;
const SLUG = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const OG_YERELI = { tr: 'tr_TR', en: 'en_US', de: 'de_DE', ru: 'ru_RU', zh: 'zh_CN', hi: 'hi_IN', ar: 'ar_AR' };
const EK = {
  menu: { tr: 'Menü', en: 'Menu', de: 'Speisekarte', ru: 'Меню', zh: '菜单', hi: 'मेन्यू', ar: 'قائمة الطعام' },
  katalog: { tr: 'Katalog', en: 'Catalog', de: 'Katalog', ru: 'Каталог', zh: '商品目录', hi: 'कैटलॉग', ar: 'الكتالوج' },
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

function kisalt(metin, sinir) {
  const tek = String(metin ?? '').replace(/\s+/g, ' ').trim();
  return tek.length > sinir ? tek.slice(0, sinir - 1).trimEnd() + '…' : tek;
}

function basliklariEkle(yanit, ek = {}) {
  const kopya = new Response(yanit.body, yanit);
  // Kabuğun doğrulayıcıları yeniden yazılmış gövdeye ait değil.
  for (const ad of ['etag', 'last-modified', 'content-length']) kopya.headers.delete(ad);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  for (const [ad, deger] of Object.entries(cspBasliklari())) kopya.headers.set(ad, deger);
  for (const [ad, deger] of Object.entries(ek)) kopya.headers.set(ad, deger);
  return kopya;
}

/**
 * Menünün özeti: `{durum, veri}`; ağ hatası / zaman aşımı / 5xx → `{durum: 0}`.
 * `istek`/`env` verilirse arka uç isteği vekil imzalı (Faz 4G).
 */
export async function ozetAl(origin, slug, urun, dil, istek = null, env = null) {
  const p = new URLSearchParams();
  if (urun && /^\d{1,10}$/.test(urun)) p.set('urun', urun);
  if (dil && DILLER.includes(dil)) p.set('dil', dil);
  const sorgu = p.toString();
  const adres = `${origin.replace(/\/$/, '')}/api/v1/menu/${encodeURIComponent(slug)}/ozet${sorgu ? `?${sorgu}` : ''}`;
  const iptal = new AbortController();
  const zaman = setTimeout(() => iptal.abort(), ZAMAN_ASIMI_MS);
  try {
    const y = await fetch(adres, {
      headers: vekilBasliklari(new Headers({ accept: 'application/json' }), istek, env),
      signal: iptal.signal,
      // Kenarda kısa süre önbellek: aynı menü art arda paylaşılınca arka uç yorulmasın.
      cf: { cacheTtl: 60, cacheEverything: true },
    });
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
function iskelet(ad, renk) {
  const r = /^#[0-9a-fA-F]{6}$/.test(renk || '') ? renk : '#7c3aed';
  return (
    '<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;' +
    'gap:14px;background:#0b0714;color:#ece8f5;font:600 18px/1.4 system-ui,-apple-system,sans-serif;padding:24px;text-align:center">' +
    `<div style="width:40px;height:40px;border-radius:50%;border:3px solid ${r};border-top-color:transparent" aria-hidden="true"></div>` +
    (ad ? `<p style="margin:0">${kacis(ad)}</p>` : '') +
    '</div>'
  );
}

/** Kabuğun `<head>`ini menüye göre yeniden yazar (HTMLRewriter). */
export function yenidenYaz(kabuk, s) {
  const etiketler = [
    `<meta name="description" content="${kacis(s.aciklama)}">`,
    `<meta name="robots" content="${s.robots}">`,
  ];
  if (s.adres) {
    etiketler.push(`<link rel="canonical" href="${kacis(s.adres)}">`);
  }
  if (s.ozetVar) {
    etiketler.push(
      `<meta property="og:type" content="${s.urunVar ? 'product' : 'website'}">`,
      `<meta property="og:site_name" content="${kacis(s.magazaAdi)}">`,
      `<meta property="og:title" content="${kacis(s.baslik)}">`,
      `<meta property="og:description" content="${kacis(s.aciklama)}">`,
      `<meta property="og:url" content="${kacis(s.adres)}">`,
      `<meta property="og:locale" content="${OG_YERELI[s.dil] || 'tr_TR'}">`,
      `<meta name="twitter:card" content="${s.gorsel ? 'summary_large_image' : 'summary'}">`,
      `<meta name="twitter:title" content="${kacis(s.baslik)}">`,
      `<meta name="twitter:description" content="${kacis(s.aciklama)}">`
    );
    if (s.gorsel) {
      etiketler.push(
        `<meta property="og:image" content="${kacis(s.gorsel)}">`,
        `<meta name="twitter:image" content="${kacis(s.gorsel)}">`
      );
    }
  }
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
        // canonical ve hreflang (alternate) ana sayfaya ait.
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
        e.setInnerContent(iskelet(s.magazaAdi, s.renk), { html: true });
      },
    })
    .transform(kabuk);
}

async function kabukAl(env, request) {
  if (!env.ASSETS || typeof env.ASSETS.fetch !== 'function') return null;
  try {
    const y = await env.ASSETS.fetch(new Request(new URL('/', request.url), { method: 'GET', headers: { accept: 'text/html' } }));
    return y.ok ? y : null;
  } catch {
    return null;
  }
}

function sadeSayfa(durum) {
  const govde =
    '<!doctype html><html lang="tr"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="robots" content="noindex, nofollow"><title>mehmetkuru.dev</title></head>' +
    '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;' +
    'background:#0b0714;color:#ece8f5;font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center">' +
    '<main><p>Menü şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.</p>' +
    '<p lang="en" style="color:#b9b2c9">The menu could not be opened right now. Please try again in a few seconds.</p></main></body></html>';
  return basliklariEkle(new Response(govde, { status: durum, headers: { 'content-type': 'text/html; charset=utf-8' } }), {
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
  });
}

export async function onRequest({ request, env, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return basliklariEkle(new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } }));
  }
  const url = new URL(request.url);
  const slug = (Array.isArray(params?.slug) ? params.slug.join('/') : String(params?.slug ?? '')).toLowerCase();
  const urun = url.searchParams.get('urun') || '';
  const dilParam = (url.searchParams.get('dil') || '').slice(0, 2).toLowerCase();

  const kabuk = await kabukAl(env, request);
  if (!kabuk) return sadeSayfa(502);

  let sonuc = { durum: 404 };
  if (SLUG.test(slug) && env.API_ORIGIN) {
    sonuc = await ozetAl(env.API_ORIGIN, slug, urun, dilParam, request, env);
  } else if (SLUG.test(slug)) {
    sonuc = { durum: 0 };
  }

  if (sonuc.durum !== 200) {
    // 404 / 410: SPA sade sayfasını çizer. 0 (arka uç kapalı): kabuk + noindex, menüyü istemci yükler.
    const durum = sonuc.durum === 0 ? 200 : sonuc.durum;
    const yazilan = yenidenYaz(kabuk, {
      dil: 'tr', robots: 'noindex, nofollow', baslik: 'By Mehmet KURU Dev', aciklama: '', adres: '', magazaAdi: '',
      ozetVar: false, urunVar: false, gorsel: null, renk: null,
    });
    return basliklariEkle(new Response(yazilan.body, { status: durum, headers: yazilan.headers }), {
      'Cache-Control': 'no-store',
      'X-Robots-Tag': 'noindex, nofollow',
    });
  }

  const v = sonuc.veri || {};
  const dil = DILLER.includes(v.dil) ? v.dil : 'tr';
  const duzen = v.duzen === 'katalog' ? 'katalog' : 'menu';
  const magazaAdi = kisalt(v.ad || slug, 120);
  const u = v.urun && typeof v.urun === 'object' ? v.urun : null;
  const baslik = u ? `${kisalt(u.ad, 120)} — ${magazaAdi}` : `${magazaAdi} | ${EK[duzen][dil]}`;
  const aciklama = kisalt(
    u ? u.aciklama || [u.fiyat, magazaAdi].filter(Boolean).join(' · ') : v.aciklama || `${magazaAdi} — ${EK[duzen][dil]}`,
    200
  );
  const taban = typeof v.adres_url === 'string' && /^https?:\/\//.test(v.adres_url) ? v.adres_url : `${url.origin}/menu/${slug}`;
  const sorgu = new URLSearchParams();
  if (u) sorgu.set('urun', String(u.id));
  if (dilParam && dilParam === dil && Array.isArray(v.diller) && v.diller[0] !== dil) sorgu.set('dil', dil);
  const adres = taban + (sorgu.toString() ? `?${sorgu.toString()}` : '');
  const indekslenebilir = v.indekslenebilir === true;
  const gorsel = (u && u.gorsel) || v.gorsel || null;

  const yazilan = yenidenYaz(kabuk, {
    dil, robots: indekslenebilir ? 'index, follow' : 'noindex, nofollow', baslik, aciklama, adres, magazaAdi,
    ozetVar: true, urunVar: !!u, gorsel: typeof gorsel === 'string' && /^https?:\/\//.test(gorsel) ? gorsel : null,
    renk: v.tema_rengi,
  });
  const ek = { 'Cache-Control': 'public, max-age=0, must-revalidate' };
  if (!indekslenebilir) ek['X-Robots-Tag'] = 'noindex, nofollow';
  return basliklariEkle(new Response(yazilan.body, { status: 200, headers: yazilan.headers }), ek);
}
