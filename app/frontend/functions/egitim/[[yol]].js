/**
 * Cloudflare Pages Function — `/egitim/*` (Faz 6K: eğitim modülü).
 *
 *   /egitim/<slug>                 kurs sayfası + kayıt formu
 *   /egitim/ogrenci/<jeton>        imzalı öğrenci sayfası (girişsiz; dersler, quiz, yoklama, sertifika)
 *   /egitim/yoklama/<jeton>        sınıfta okutulan oturum QR'ı
 *   /egitim/sertifika/<kod>        sertifika doğrulama
 *   /egitim/okut/<kurs>/<oturum>   panel okutucusu (eğitmen öğrencinin QR'ını okutur)
 *   /egitim/kurum/<slug>           hesabın kurs listesi
 *
 * Etkinlik Function'ının (Faz 6E) yardımcıları yeniden kullanılıyor (kabuk, HTMLRewriter, CSP,
 * vekil imzası, güvenlik başlıkları). Kurs sayfasında arka uçtan kısa özet
 * (`GET /api/v1/egitim/kurs/<slug>/ozet`); "arama motorlarında görünsün" kapalıysa (varsayılan)
 * `noindex, nofollow` + `X-Robots-Tag`, açıksa `index, follow` + schema.org **Course JSON-LD**.
 *
 * Öğrenci / yoklama / sertifika / okutucu: HER ZAMAN noindex, arka uca sorulmuyor (jeton bir yetki
 * belgesi; sertifika doğrulaması istemcide), `Referrer-Policy: no-referrer`. Kamera izni YALNIZ panel
 * okutucusunda (`camera=(self)`); sitenin geri kalanında `camera=()`. Arka uç kapalı/yavaşsa kabuk +
 * noindex; istemci kendisi yükler.
 */

import { BOS, IZINLER_KAMERA, basliklariEkle, jsonAl, kabukAl, kisalt, yenidenYaz } from '../etkinlik/[[yol]].js';

export { IZINLER_KAMERA };

const SLUG = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;
const AYRILMIS = new Set(['ogrenci', 'yoklama', 'sertifika', 'okut', 'kurum', 'kurs', 'egitim', 'egitimler', 'kayit', 'liste', 'dosya', 'quiz', 'odev', 'takvim']);
const JETON = /^\d{1,12}-\d{1,6}-[0-9a-f]{32}$/;
const SERTIFIKA = /^[A-HJ-NP-Z2-9]{12}$/;
const KIMLIK = /^\d{1,12}$/;
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
export const EK = {
  kurs: { tr: 'Kurs', en: 'Course', de: 'Kurs', ru: 'Курс', zh: '课程', hi: 'पाठ्यक्रम', ar: 'دورة' },
  ogrenci: { tr: 'Öğrenci sayfası', en: 'Student page', de: 'Teilnehmerseite', ru: 'Страница ученика', zh: '学员页面', hi: 'छात्र पृष्ठ', ar: 'صفحة الطالب' },
  yoklama: { tr: 'Yoklama', en: 'Attendance', de: 'Anwesenheit', ru: 'Посещаемость', zh: '签到', hi: 'उपस्थिति', ar: 'الحضور' },
  sertifika: { tr: 'Sertifika doğrulama', en: 'Certificate verification', de: 'Zertifikatsprüfung', ru: 'Проверка сертификата', zh: '证书验证', hi: 'प्रमाणपत्र सत्यापन', ar: 'التحقق من الشهادة' },
  okut: { tr: 'Yoklama okutucu', en: 'Attendance scanner', de: 'Anwesenheitsscanner', ru: 'Сканер посещаемости', zh: '签到扫描', hi: 'उपस्थिति स्कैनर', ar: 'ماسح الحضور' },
  kurum: { tr: 'Kurslar', en: 'Courses', de: 'Kurse', ru: 'Курсы', zh: '课程', hi: 'पाठ्यक्रम', ar: 'الدورات' },
};

/** Yol parçaları → ne istendiği. */
export function yolCoz(parcalar) {
  const p = (Array.isArray(parcalar) ? parcalar : parcalar ? [parcalar] : []).map((x) => String(x));
  if (p.length === 2 && (p[0] === 'ogrenci' || p[0] === 'yoklama')) return { tur: p[0], gecerli: JETON.test(p[1]) };
  if (p.length === 2 && p[0] === 'sertifika') return { tur: 'sertifika', gecerli: SERTIFIKA.test(p[1].replace(/-/g, '').toUpperCase()) };
  if (p.length === 3 && p[0] === 'okut') return { tur: 'okut', gecerli: KIMLIK.test(p[1]) && KIMLIK.test(p[2]) };
  if (p.length === 2 && p[0] === 'kurum' && SLUG.test(p[1].toLowerCase())) return { tur: 'kurum', slug: p[1].toLowerCase() };
  if (p.length === 1 && SLUG.test(p[0].toLowerCase()) && !AYRILMIS.has(p[0].toLowerCase())) return { tur: 'sayfa', slug: p[0].toLowerCase() };
  return { tur: 'yok' };
}

export function sadeSayfa(durum) {
  const govde =
    '<!doctype html><html lang="tr"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="robots" content="noindex, nofollow"><title>mehmetkuru.dev</title></head>' +
    '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;' +
    'background:#f6f7fb;color:#18181b;font:16px/1.6 system-ui,sans-serif;padding:24px;text-align:center">' +
    '<main><p>Kurs sayfası şu an açılamadı. Lütfen birkaç saniye sonra yeniden deneyin.</p>' +
    '<p lang="en" style="color:#71717a">The course page could not be opened right now. Please try again in a few seconds.</p></main></body></html>';
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
  const dilParam = (url.searchParams.get('dil') || '').slice(0, 2).toLowerCase();
  const yol = yolCoz(params?.yol);

  const kabuk = await kabukAl(env, request);
  if (!kabuk) return sadeSayfa(502);

  const dilSec = (yedek) => (DILLER.includes(dilParam) ? dilParam : DILLER.includes(yedek) ? yedek : 'tr');
  const kapali = (durum, baslik, dil = 'tr', ek = {}, karanlik = false) => {
    const yazilan = yenidenYaz(kabuk, { ...BOS, dil, baslik, gomulu: false, karanlik });
    return basliklariEkle(new Response(yazilan.body, { status: durum, headers: yazilan.headers }), {
      'Cache-Control': 'no-store',
      'X-Robots-Tag': 'noindex, nofollow',
      ...ek,
    });
  };

  if (yol.tur === 'okut') {
    // Panel okutucusu: arka uca sorulmuyor (oturum istemcide); kamera izni yalnız burada.
    const dil = dilSec('tr');
    return kapali(yol.gecerli ? 200 : 404, `${EK.okut[dil]} | By Mehmet KURU Dev`, dil, { 'Permissions-Policy': IZINLER_KAMERA, 'Referrer-Policy': 'no-referrer' }, true);
  }
  if (yol.tur === 'ogrenci' || yol.tur === 'yoklama' || yol.tur === 'sertifika') {
    const dil = dilSec('tr');
    return kapali(yol.gecerli ? 200 : 404, `${EK[yol.tur][dil]} | By Mehmet KURU Dev`, dil, { 'Referrer-Policy': 'no-referrer' });
  }
  if (yol.tur === 'yok') return kapali(404, 'By Mehmet KURU Dev');

  if (yol.tur === 'kurum') {
    let sonuc = { durum: 0 };
    if (env.API_ORIGIN) sonuc = await jsonAl(env.API_ORIGIN, `/api/v1/egitim/kurum/${encodeURIComponent(yol.slug)}`, request, env);
    if (sonuc.durum !== 200) return kapali(sonuc.durum === 0 ? 200 : sonuc.durum, 'By Mehmet KURU Dev');
    const v = sonuc.veri || {};
    const dil = dilSec('tr');
    const sayfaAdi = kisalt(v.baslik || v.kurum_adi || yol.slug, 120);
    const sayi = Array.isArray(v.items) ? v.items.length : 0;
    const yazilan = yenidenYaz(kabuk, {
      ...BOS, dil, baslik: `${sayfaAdi} | ${EK.kurum[dil]}`, aciklama: kisalt(v.aciklama || `${sayfaAdi} — ${EK.kurum[dil]} (${sayi})`, 200),
      adres: `${url.origin}/egitim/kurum/${yol.slug}`, sayfaAdi, ozetVar: true,
    });
    return basliklariEkle(new Response(yazilan.body, { status: 200, headers: yazilan.headers }), {
      'Cache-Control': 'public, max-age=0, must-revalidate',
      'X-Robots-Tag': 'noindex, nofollow',
    });
  }

  let sonuc = { durum: 0 };
  if (env.API_ORIGIN) sonuc = await jsonAl(env.API_ORIGIN, `/api/v1/egitim/kurs/${encodeURIComponent(yol.slug)}/ozet`, request, env);
  if (sonuc.durum !== 200) {
    // 404 / 410: SPA sade sayfasını çizer. 0 (arka uç kapalı): kabuk + noindex, istemci yükler.
    return kapali(sonuc.durum === 0 ? 200 : sonuc.durum, 'By Mehmet KURU Dev');
  }
  const v = sonuc.veri || {};
  const dil = dilSec(v.dil);
  const sayfaAdi = kisalt(v.baslik || yol.slug, 120);
  const adres = typeof v.adres_url === 'string' && /^https?:\/\//.test(v.adres_url) ? v.adres_url : `${url.origin}/egitim/${yol.slug}`;
  const indekslenebilir = v.indekslenebilir === true;
  const jsonld = indekslenebilir && v.jsonld && typeof v.jsonld === 'object' ? v.jsonld : null;
  const yazilan = yenidenYaz(kabuk, {
    dil, robots: indekslenebilir ? 'index, follow' : 'noindex, nofollow', baslik: `${sayfaAdi} | ${EK.kurs[dil]}`,
    aciklama: kisalt(v.aciklama || sayfaAdi, 200), adres, sayfaAdi, ozetVar: true, gorsel: null, renk: v.renk, gomulu: false, jsonld,
  });
  const ek = { 'Cache-Control': 'public, max-age=0, must-revalidate' };
  if (!indekslenebilir) ek['X-Robots-Tag'] = 'noindex, nofollow';
  return basliklariEkle(new Response(yazilan.body, { status: 200, headers: yazilan.headers }), ek);
}
