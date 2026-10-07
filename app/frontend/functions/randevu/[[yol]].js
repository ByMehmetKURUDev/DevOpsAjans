/**
 * Cloudflare Pages Function — `/randevu/*` (Faz 5R: randevu ve toplantılar).
 *
 *   /randevu/<slug>              hesabın randevu sayfası (etkinlik türleri)
 *   /randevu/<slug>/<tür>        etkinlik türünün takvimi
 *   /randevu/yonet/<jeton>       imzalı yönetim bağlantısı (iptal / yeniden planla)
 *
 * Site bir SPA: bu adresler için prerender edilmiş HTML yok. WhatsApp/LinkedIn
 * önizleyicileri ve arama motorları JavaScript çalıştırmadan `<head>`e bakıyor.
 * Bu dosya (`functions/menu/[slug].js` deseni):
 *
 *   1. Arka uçtan sayfanın kısa özetini alıyor (`GET /api/v1/randevu/<slug>/ozet?tur=`,
 *      `API_ORIGIN` — `/api` vekili ile aynı değişken; ek ayar yok).
 *   2. `env.ASSETS.fetch` ile uygulamanın kabuğunu (index.html) alıyor.
 *   3. `HTMLRewriter` ile `<title>`, description, `og:*`, `twitter:*`, canonical ve
 *      robots'u yeniden yazıyor; ana sayfaya ait hreflang ve yapısal veriyi kaldırıyor;
 *      `#root` içine sade bir yükleniyor iskeleti koyuyor.
 *
 * robots: sayfa ayarı "arama motorlarında görünsün" kapalıysa (varsayılan)
 * `noindex, nofollow` + `X-Robots-Tag`. Yönetim bağlantısı HER ZAMAN noindex ve arka uca
 * hiç sorulmuyor (jeton bir yetki belgesi; önizleyiciye kişisel bilgi gitmesin).
 * `?gomulu=1` (gömülü pencere, `public/randevu-widget.js`): başka sitelerin çerçevesinde
 * açılabilsin diye `X-Frame-Options` konmuyor, `frame-ancestors *` veriliyor.
 * Arka uç kapalı/yavaşsa (ücretsiz plan uyur) kabuk + noindex döner; istemci kendisi yükler.
 * `public/_headers` Function yanıtlarına uygulanmadığı için temel başlıklar burada.
 *
 * Faz 4L — marka teması: özetteki `marka` uygulanıyorsa `<head>`e `--marka-*` değişkenleri ve
 * ilk boyama zemini (`_ortak/marka.js`); iskelet markanın zemininde, markanın renginde (sayfanın
 * kendi rengi seçiliyse o). Gömülü pencerede zemin saydam kalıyor (başka sitenin içinde).
 */

import { cspBasliklari } from '../_ortak/csp.js';
import { sayfaIlkBoyama } from '../_ortak/marka.js';

const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};

/** Arka uç bu kadar sürede yanıt vermezse kabuk döner (önizleyiciler beklemez). */
export const ZAMAN_ASIMI_MS = 2500;
const SLUG = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;
const JETON = /^\d{1,12}-[0-9a-f]{32}$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const OG_YERELI = { tr: 'tr_TR', en: 'en_US', de: 'de_DE', ru: 'ru_RU', zh: 'zh_CN', hi: 'hi_IN', ar: 'ar_AR' };
const EK = {
  randevu: { tr: 'Randevu al', en: 'Book a time', de: 'Termin buchen', ru: 'Записаться', zh: '在线预约', hi: 'समय बुक करें', ar: 'احجز موعدًا' },
  dk: { tr: 'dk', en: 'min', de: 'Min.', ru: 'мин', zh: '分钟', hi: 'मिनट', ar: 'دقيقة' },
  yonet: { tr: 'Randevunuz', en: 'Your appointment', de: 'Ihr Termin', ru: 'Ваша запись', zh: '您的预约', hi: 'आपकी अपॉइंटमेंट', ar: 'موعدك' },
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

/** Yol parçaları → ne istendiği. */
export function yolCoz(parcalar) {
  const p = (Array.isArray(parcalar) ? parcalar : parcalar ? [parcalar] : []).map((x) => String(x));
  if (p.length === 2 && p[0] === 'yonet') return { tur: 'yonet', gecerli: JETON.test(p[1]) };
  if (p.length === 1 && SLUG.test(p[0].toLowerCase())) return { tur: 'sayfa', slug: p[0].toLowerCase() };
  if (p.length === 2 && SLUG.test(p[0].toLowerCase()) && SLUG.test(p[1].toLowerCase())) {
    return { tur: 'etkinlik', slug: p[0].toLowerCase(), etkinlik: p[1].toLowerCase() };
  }
  return { tur: 'yok' };
}

function basliklariEkle(yanit, ek = {}, gomulu = false) {
  const kopya = new Response(yanit.body, yanit);
  for (const ad of ['etag', 'last-modified', 'content-length', 'x-frame-options']) kopya.headers.delete(ad);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  // Faz 4G CSP'si (tek kaynak `_ortak/csp.js`); gömülü pencerede yalnız frame-ancestors gevşer.
  for (const [ad, deger] of Object.entries(cspBasliklari(gomulu ? { cerceveIzni: '*' } : {}))) kopya.headers.set(ad, deger);
  if (!gomulu) kopya.headers.set('X-Frame-Options', 'SAMEORIGIN');
  for (const [ad, deger] of Object.entries(ek)) kopya.headers.set(ad, deger);
  return kopya;
}

/** Sayfanın özeti: `{durum, veri}`; ağ hatası / zaman aşımı / 5xx → `{durum: 0}`. */
export async function ozetAl(origin, slug, etkinlik) {
  const sorgu = etkinlik ? `?tur=${encodeURIComponent(etkinlik)}` : '';
  const adres = `${origin.replace(/\/$/, '')}/api/v1/randevu/${encodeURIComponent(slug)}/ozet${sorgu}`;
  const iptal = new AbortController();
  const zaman = setTimeout(() => iptal.abort(), ZAMAN_ASIMI_MS);
  try {
    const y = await fetch(adres, {
      headers: { accept: 'application/json' },
      signal: iptal.signal,
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
function iskelet(ad, renk, gomulu, markali = false) {
  const r = /^#[0-9a-fA-F]{6}$/.test(renk || '') ? renk : '#7c3aed';
  // Faz 4L: marka zemini (`--marka-ilk-zemin`, `_ortak/marka.js`) varsa iskelet de onun üstünde.
  const zemin = gomulu ? 'transparent' : markali ? 'var(--marka-ilk-zemin,#f7f7f8)' : '#f7f7f8';
  const yazi = markali ? 'var(--marka-ilk-metin,#18181b)' : '#18181b';
  const font = markali ? 'var(--marka-yazi-tipi,system-ui,-apple-system,sans-serif)' : 'system-ui,-apple-system,sans-serif';
  return (
    `<div style="min-height:${gomulu ? '320px' : '100vh'};display:flex;flex-direction:column;align-items:center;justify-content:center;` +
    `gap:14px;background:${zemin};color:${yazi};font:600 18px/1.4 ${font};padding:24px;text-align:center">` +
    `<div style="width:40px;height:40px;border-radius:50%;border:3px solid ${r};border-top-color:transparent" aria-hidden="true"></div>` +
    (ad ? `<p style="margin:0">${kacis(ad)}</p>` : '') +
    '</div>'
  );
}

/** Kabuğun `<head>`ini yeniden yazar (HTMLRewriter). */
export function yenidenYaz(kabuk, s) {
  const etiketler = [`<meta name="description" content="${kacis(s.aciklama)}">`, `<meta name="robots" content="${s.robots}">`];
  if (s.adres) etiketler.push(`<link rel="canonical" href="${kacis(s.adres)}">`);
  if (s.ozetVar) {
    etiketler.push(
      '<meta property="og:type" content="website">',
      `<meta property="og:site_name" content="${kacis(s.sayfaAdi)}">`,
      `<meta property="og:title" content="${kacis(s.baslik)}">`,
      `<meta property="og:description" content="${kacis(s.aciklama)}">`,
      `<meta property="og:url" content="${kacis(s.adres)}">`,
      `<meta property="og:locale" content="${OG_YERELI[s.dil] || 'tr_TR'}">`,
      '<meta name="twitter:card" content="summary">',
      `<meta name="twitter:title" content="${kacis(s.baslik)}">`,
      `<meta name="twitter:description" content="${kacis(s.aciklama)}">`
    );
    if (s.gorsel) {
      etiketler.push(`<meta property="og:image" content="${kacis(s.gorsel)}">`, `<meta name="twitter:image" content="${kacis(s.gorsel)}">`);
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
        e.append(etiketler.join('') + (s.markaStili || ''), { html: true });
      },
    })
    .on('div#root', {
      element(e) {
        e.setInnerContent(iskelet(s.sayfaAdi, s.renk, s.gomulu, !!s.markaStili), { html: true });
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
    'background:#f7f7f8;color:#18181b;font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center">' +
    '<main><p>Randevu sayfası şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.</p>' +
    '<p lang="en" style="color:#71717a">The booking page could not be opened right now. Please try again in a few seconds.</p></main></body></html>';
  return basliklariEkle(new Response(govde, { status: durum, headers: { 'content-type': 'text/html; charset=utf-8' } }), {
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
  });
}

const BOS = { robots: 'noindex, nofollow', aciklama: '', adres: '', sayfaAdi: '', ozetVar: false, gorsel: null, renk: null };

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

  const kapali = (durum, baslik, dil = 'tr') => {
    const yazilan = yenidenYaz(kabuk, { ...BOS, dil, baslik, gomulu });
    return basliklariEkle(
      new Response(yazilan.body, { status: durum, headers: yazilan.headers }),
      { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
      gomulu
    );
  };

  if (yol.tur === 'yonet') {
    // Jeton arka uca sorulmuyor; sayfa istemcide doğrular.
    const dil = DILLER.includes(dilParam) ? dilParam : 'tr';
    return kapali(yol.gecerli ? 200 : 404, `${EK.yonet[dil]} | By Mehmet KURU Dev`, dil);
  }
  if (yol.tur === 'yok') return kapali(404, 'By Mehmet KURU Dev');

  let sonuc = { durum: 0 };
  if (env.API_ORIGIN) sonuc = await ozetAl(env.API_ORIGIN, yol.slug, yol.etkinlik);
  if (sonuc.durum !== 200) {
    // 404 / 410: SPA sade sayfasını çizer. 0 (arka uç kapalı): kabuk + noindex, istemci yükler.
    return kapali(sonuc.durum === 0 ? 200 : sonuc.durum, 'By Mehmet KURU Dev');
  }

  const v = sonuc.veri || {};
  const dil = DILLER.includes(dilParam) ? dilParam : DILLER.includes(v.dil) ? v.dil : 'tr';
  const sayfaAdi = kisalt(v.baslik || yol.slug, 120);
  const t = v.tur && typeof v.tur === 'object' ? v.tur : null;
  const baslik = t ? `${kisalt(t.ad, 120)} — ${sayfaAdi}` : `${sayfaAdi} | ${EK.randevu[dil]}`;
  const aciklama = kisalt(
    t ? t.aciklama || `${t.ad} · ${t.sure_dk} ${EK.dk[dil]} · ${sayfaAdi}` : v.aciklama || `${sayfaAdi} — ${EK.randevu[dil]}`,
    200
  );
  const taban = typeof v.adres_url === 'string' && /^https?:\/\//.test(v.adres_url) ? v.adres_url : `${url.origin}/randevu/${yol.slug}`;
  const adres = t && typeof t.adres_url === 'string' && /^https?:\/\//.test(t.adres_url) ? t.adres_url : t ? `${taban}/${t.slug}` : taban;
  const indekslenebilir = v.indekslenebilir === true && !gomulu;
  const gorsel = typeof v.gorsel === 'string' && /^https?:\/\//.test(v.gorsel) ? v.gorsel : null;

  // Faz 4L: marka teması (sayfanın kendi rengi seçiliyse halka o renkte); gömülüde zemin yazılmıyor.
  const marka = sayfaIlkBoyama(v.marka, { sayfaRengi: v.renk, zeminUygula: !gomulu });
  const yazilan = yenidenYaz(kabuk, {
    dil, robots: indekslenebilir ? 'index, follow' : 'noindex, nofollow', baslik, aciklama, adres, sayfaAdi,
    ozetVar: true, gorsel, renk: marka.ana || v.renk, gomulu, markaStili: marka.stil,
  });
  const ek = { 'Cache-Control': 'public, max-age=0, must-revalidate' };
  if (!indekslenebilir) ek['X-Robots-Tag'] = 'noindex, nofollow';
  return basliklariEkle(new Response(yazilan.body, { status: 200, headers: yazilan.headers }), ek, gomulu);
}
