/**
 * Cloudflare Pages Function — `/hukuk/*` (Faz 6H: hukuk bürosu).
 *
 *   /hukuk/muvekkil/<jeton>   imzalı müvekkil portalı (girişsiz): dosyalarının yalnız "müvekkile görünür"
 *                             alanları, paylaşılan belgeler, masraf dökümü, mesaj
 *
 * Avukat–müvekkil sırrı: sayfa HER ZAMAN `noindex, nofollow` (+ `X-Robots-Tag`), `Referrer-Policy:
 * no-referrer`, `Cache-Control: no-store`; arka uca SORULMUYOR (jeton bir yetki belgesi — paylaşım önizlemesine
 * ad, dosya ya da büro bilgisi yazılmaz, OG etiketleri yok). İstemci verisini kendisi yükler. Kamera izni yok.
 * Herkese açık tanıtım sayfası YOK (Avukatlık Kanunu m.55, TBB reklam yasağı): `/hukuk/<başka>` → 404.
 *
 * Etkinlik Function'ının (Faz 6E) yardımcıları yeniden kullanılıyor (kabuk, HTMLRewriter, CSP, güvenlik başlıkları).
 */

import { BOS, basliklariEkle, kabukAl, yenidenYaz } from '../etkinlik/[[yol]].js';

const JETON = /^\d{1,12}-\d{1,6}-[0-9a-f]{32}$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
export const BASLIK = {
  tr: 'Müvekkil bilgilendirme sayfası',
  en: 'Client information page',
  de: 'Mandanteninformationsseite',
  ru: 'Страница для клиента',
  zh: '客户信息页面',
  hi: 'मुवक्किल सूचना पृष्ठ',
  ar: 'صفحة معلومات الموكّل',
};

/** Yol parçaları → ne istendiği. */
export function yolCoz(parcalar) {
  const p = (Array.isArray(parcalar) ? parcalar : parcalar ? [parcalar] : []).map((x) => String(x));
  if (p.length === 2 && p[0] === 'muvekkil') return { tur: 'muvekkil', gecerli: JETON.test(p[1]) };
  return { tur: 'yok' };
}

export async function onRequest({ request, env, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return basliklariEkle(new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } }));
  }
  const url = new URL(request.url);
  const dilParam = (url.searchParams.get('dil') || '').slice(0, 2).toLowerCase();
  const dil = DILLER.includes(dilParam) ? dilParam : 'tr';
  const yol = yolCoz(params?.yol);
  const ek = { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'no-referrer' };
  const durum = yol.tur === 'muvekkil' && yol.gecerli ? 200 : 404;
  const kabuk = await kabukAl(env, request);
  if (!kabuk) {
    const govde =
      '<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<meta name="robots" content="noindex, nofollow"><title>mehmetkuru.dev</title></head><body style="margin:0;min-height:100vh;' +
      'display:flex;align-items:center;justify-content:center;background:#f6f7fb;color:#18181b;font:16px/1.6 system-ui,sans-serif;' +
      'padding:24px;text-align:center"><main><p>Sayfa şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.</p>' +
      '<p lang="en" style="color:#71717a">The page could not be opened right now. Please try again in a few seconds.</p></main></body></html>';
    return basliklariEkle(new Response(govde, { status: 502, headers: { 'content-type': 'text/html; charset=utf-8' } }), ek);
  }
  const yazilan = yenidenYaz(kabuk, { ...BOS, dil, baslik: `${BASLIK[dil]} | By Mehmet KURU Dev`, gomulu: false });
  return basliklariEkle(new Response(yazilan.body, { status: durum, headers: yazilan.headers }), ek);
}
