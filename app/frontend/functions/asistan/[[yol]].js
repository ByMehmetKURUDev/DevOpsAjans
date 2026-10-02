/**
 * Cloudflare Pages Function — `/asistan/*` (Faz 5A: AI asistan).
 *
 *   /asistan/<anahtar>             paylaşılabilir tam sayfa (asistanın "tam sayfa" ayarı açıksa)
 *   /asistan/<anahtar>?gomulu=1    gömülü pencere (public/asistan-widget.js çerçevesi)
 *
 * Site bir SPA; bu adresler için prerender edilmiş HTML yok. Bu dosya
 * (`functions/randevu/[[yol]].js` deseni):
 *
 *   1. Arka uçtan asistanın kısa özetini alıyor (`GET /api/v1/asistan/<anahtar>/ozet`,
 *      `API_ORIGIN` — `/api` vekili ile aynı değişken; ek ayar yok).
 *   2. `env.ASSETS.fetch` ile uygulamanın kabuğunu (index.html) alıyor.
 *   3. `HTMLRewriter` ile `<title>`, robots (HER ZAMAN noindex), dil/yön yazıyor;
 *      ana sayfaya ait description, OG, canonical, hreflang ve yapısal veriyi kaldırıyor;
 *      `#root` içine sade bir yükleniyor iskeleti koyuyor.
 *
 * Çerçeve izni (clickjacking'e karşı): normal sayfa `X-Frame-Options: SAMEORIGIN` +
 * `frame-ancestors 'self'`. Gömülü modda `X-Frame-Options` YOK ve `frame-ancestors`
 * asistanın izinli alan adlarından kuruluyor (`'self' ornek.com *.ornek.com`);
 * liste boşsa ya da arka uca ulaşılamazsa `*` (asıl denetim sunucuda: gömülü istekte üst
 * sayfanın kökeni izinli listeye göre doğrulanıyor, `Origin` başlığı da). Böylece tarayıcı
 * izinsiz sitedeki çerçeveyi hiç çizmiyor.
 * `public/_headers` Function yanıtlarına uygulanmadığı için temel başlıklar burada.
 */

import { cspBasliklari } from '../_ortak/csp.js';

const GUVENLIK_BASLIKLARI = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
};

/** Arka uç bu kadar sürede yanıt vermezse kabuk döner. */
export const ZAMAN_ASIMI_MS = 2500;
const ANAHTAR = /^[a-z0-9]{16}$/;
/** İzinli alan adı (arka uç da doğruluyor; başlığa yazmadan önce bir kez daha). */
const ALAN_ADI = /^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const EK = {
  asistan: { tr: 'AI asistan', en: 'AI assistant', de: 'KI-Assistent', ru: 'ИИ-ассистент', zh: 'AI 助手', hi: 'AI सहायक', ar: 'المساعد الذكي' },
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

/** Yol parçaları → anahtar (geçersizse null). */
export function yolCoz(parcalar) {
  const p = (Array.isArray(parcalar) ? parcalar : parcalar ? [parcalar] : []).map((x) => String(x));
  return p.length === 1 && ANAHTAR.test(p[0]) ? p[0] : null;
}

/**
 * Gömülü pencerenin `frame-ancestors` değeri: izinli alan adları (alt alan adları dahil) +
 * 'self'. Şemasız yazılıyor: CSP3'te şemasız kaynak ifadesi korunan belgenin şemasıyla
 * eşleşir (https sitede yalnız https), bağlantı noktası varsayılan olmalı. Boş liste → '*'.
 * Geçersiz girdiler (ve `localhost`) atlanır; hiçbiri geçerli değilse yalnız 'self'
 * (liste doluysa "her yer" anlamına gelmesin).
 */
export function cerceveIzni(kokenler) {
  if (!Array.isArray(kokenler) || kokenler.length === 0) return '*';
  const parcalar = ["'self'"];
  for (const ham of kokenler.slice(0, 50)) {
    const a = String(ham || '').trim().toLowerCase().replace(/\.$/, '');
    if (!ALAN_ADI.test(a)) continue;
    const kok = a.replace(/^\*\./, '');
    for (const p of [kok, `*.${kok}`]) if (!parcalar.includes(p)) parcalar.push(p);
  }
  return parcalar.join(' ');
}

function basliklariEkle(yanit, ek = {}, cerceve = null) {
  const kopya = new Response(yanit.body, yanit);
  for (const ad of ['etag', 'last-modified', 'content-length', 'x-frame-options']) kopya.headers.delete(ad);
  for (const [ad, deger] of Object.entries(GUVENLIK_BASLIKLARI)) {
    if (!kopya.headers.has(ad)) kopya.headers.set(ad, deger);
  }
  // Faz 4G CSP'si (tek kaynak `_ortak/csp.js`); gömülü pencerede yalnız frame-ancestors değişir.
  for (const [ad, deger] of Object.entries(cspBasliklari(cerceve ? { cerceveIzni: cerceve } : {}))) kopya.headers.set(ad, deger);
  if (!cerceve) kopya.headers.set('X-Frame-Options', 'SAMEORIGIN');
  // Sohbet sayfası hiçbir zaman dizine girmez, önbelleğe alınmaz (ayarlar anında geçerli olsun).
  kopya.headers.set('X-Robots-Tag', 'noindex, nofollow');
  kopya.headers.set('Cache-Control', 'no-store');
  for (const [ad, deger] of Object.entries(ek)) kopya.headers.set(ad, deger);
  return kopya;
}

/** Asistanın özeti: `{durum, veri}`; ağ hatası / zaman aşımı / 5xx → `{durum: 0}`. */
export async function ozetAl(origin, anahtar) {
  const adres = `${origin.replace(/\/$/, '')}/api/v1/asistan/${encodeURIComponent(anahtar)}/ozet`;
  const iptal = new AbortController();
  const zaman = setTimeout(() => iptal.abort(), ZAMAN_ASIMI_MS);
  try {
    const y = await fetch(adres, {
      headers: { accept: 'application/json' },
      signal: iptal.signal,
      cf: { cacheTtl: 30, cacheEverything: true },
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
function iskelet(ad, renk, gomulu) {
  const r = /^#[0-9a-fA-F]{6}$/.test(renk || '') ? renk : '#7c3aed';
  return (
    `<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;` +
    `gap:14px;background:${gomulu ? '#fff' : '#eef0f4'};color:#18181b;font:600 16px/1.4 system-ui,-apple-system,sans-serif;padding:24px;text-align:center">` +
    `<div style="width:36px;height:36px;border-radius:50%;border:3px solid ${r};border-top-color:transparent" aria-hidden="true"></div>` +
    (ad ? `<p style="margin:0">${kacis(ad)}</p>` : '') +
    '</div>'
  );
}

/** Kabuğun `<head>`ini yeniden yazar (HTMLRewriter). */
export function yenidenYaz(kabuk, s) {
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
        e.append('<meta name="robots" content="noindex, nofollow">', { html: true });
      },
    })
    .on('div#root', {
      element(e) {
        e.setInnerContent(iskelet(s.ad, s.renk, s.gomulu), { html: true });
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
    '<main><p>Asistan şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.</p>' +
    '<p lang="en" style="color:#71717a">The assistant could not be opened right now. Please try again in a few seconds.</p></main></body></html>';
  return basliklariEkle(new Response(govde, { status: durum, headers: { 'content-type': 'text/html; charset=utf-8' } }));
}

export async function onRequest({ request, env, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return basliklariEkle(new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } }));
  }
  const url = new URL(request.url);
  const gomulu = url.searchParams.get('gomulu') === '1';
  const dilParam = (url.searchParams.get('dil') || '').slice(0, 2).toLowerCase();
  const anahtar = yolCoz(params?.yol);

  const kabuk = await kabukAl(env, request);
  if (!kabuk) return sadeSayfa(502);

  const sayfa = (durum, s, cerceve) => {
    const yazilan = yenidenYaz(kabuk, s);
    return basliklariEkle(new Response(yazilan.body, { status: durum, headers: yazilan.headers }), {}, gomulu ? cerceve : null);
  };
  const varsayilanDil = DILLER.includes(dilParam) ? dilParam : 'tr';

  if (!anahtar) {
    return sayfa(404, { dil: varsayilanDil, baslik: 'By Mehmet KURU Dev', ad: '', renk: null, gomulu }, "'self'");
  }

  let sonuc = { durum: 0 };
  if (env.API_ORIGIN) sonuc = await ozetAl(env.API_ORIGIN, anahtar);
  if (sonuc.durum !== 200) {
    // 404 / 410: SPA "bulunamadı / kullanılamıyor" sayfasını çizer (gömülüde de görünsün diye '*').
    // 0 (arka uç kapalı/yavaş): kabuk; istemci kendisi yükler, sunucu kökeni yine doğrular.
    return sayfa(sonuc.durum === 0 ? 200 : sonuc.durum, { dil: varsayilanDil, baslik: `${EK.asistan[varsayilanDil]} | By Mehmet KURU Dev`, ad: '', renk: null, gomulu }, '*');
  }

  const v = sonuc.veri || {};
  const dil = DILLER.includes(dilParam) ? dilParam : DILLER.includes(v.dil) ? v.dil : 'tr';
  const ad = kisalt(v.ad || EK.asistan[dil], 80);
  return sayfa(200, { dil, baslik: `${ad} | ${EK.asistan[dil]}`, ad, renk: v.renk, gomulu }, cerceveIzni(v.izinli_kokenler));
}
