/**
 * Cloudflare Pages Function — `/etkinlikler/<slug>` (Faz 6E: hesabın herkese açık etkinlik listesi).
 *
 * `functions/etkinlik/[[yol]].js` yardımcılarıyla: arka uçtan liste özeti
 * (`GET /api/v1/etkinlikler/<slug>`, vekil imzalı), kabuğun `<head>`ine başlık / açıklama /
 * og / canonical; robots HER ZAMAN `noindex, nofollow` (liste bir dizin sayfası; etkinliklerin
 * kendisi kendi ayarıyla indekslenir). `?gomulu=1`: çerçeve izni.
 */

import { BOS, basliklariEkle, jsonAl, kabukAl, kisalt, sadeSayfa, yenidenYaz } from '../etkinlik/[[yol]].js';

const SLUG = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const LISTE = { tr: 'Etkinlikler', en: 'Events', de: 'Veranstaltungen', ru: 'Мероприятия', zh: '活动', hi: 'कार्यक्रम', ar: 'الفعاليات' };

export async function onRequest({ request, env, params }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return basliklariEkle(new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } }));
  }
  const url = new URL(request.url);
  const gomulu = url.searchParams.get('gomulu') === '1';
  const dilParam = (url.searchParams.get('dil') || '').slice(0, 2).toLowerCase();
  const dil = DILLER.includes(dilParam) ? dilParam : 'tr';
  const slug = String(params?.slug || '').toLowerCase();

  const kabuk = await kabukAl(env, request);
  if (!kabuk) return sadeSayfa(502);

  const cevap = (durum, s) => {
    const yazilan = yenidenYaz(kabuk, { ...BOS, dil, gomulu, ...s });
    return basliklariEkle(
      new Response(yazilan.body, { status: durum, headers: yazilan.headers }),
      { 'Cache-Control': durum === 200 ? 'public, max-age=0, must-revalidate' : 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
      gomulu
    );
  };

  if (!SLUG.test(slug)) return cevap(404, { baslik: 'By Mehmet KURU Dev' });
  let sonuc = { durum: 0 };
  if (env.API_ORIGIN) sonuc = await jsonAl(env.API_ORIGIN, `/api/v1/etkinlikler/${encodeURIComponent(slug)}`, request, env);
  if (sonuc.durum !== 200) return cevap(sonuc.durum === 0 ? 200 : sonuc.durum, { baslik: 'By Mehmet KURU Dev' });

  const v = sonuc.veri || {};
  const sayfaAdi = kisalt(v.baslik || slug, 120);
  const adres = typeof v.adres_url === 'string' && /^https?:\/\//.test(v.adres_url) ? v.adres_url : `${url.origin}/etkinlikler/${slug}`;
  const sayi = Array.isArray(v.etkinlikler) ? v.etkinlikler.length : 0;
  return cevap(200, {
    baslik: `${sayfaAdi} | ${LISTE[dil]}`,
    aciklama: kisalt(v.aciklama || `${sayfaAdi} — ${LISTE[dil]}${sayi ? ` (${sayi})` : ''}`, 200),
    adres,
    sayfaAdi,
    ozetVar: true,
  });
}
