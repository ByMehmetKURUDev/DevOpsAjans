/**
 * Faz 4L — Marka teması: Pages Function'larının ilk boyama stili.
 *
 * Kartvizit (`/kart/<slug>`), QR menü (`/menu/<slug>`) ve randevu (`/randevu/...`)
 * sayfaları SPA; React çizene kadar ekranda sunucunun döndürdüğü kabuk görünüyor.
 * Marka teması yalnız istemcide uygulansaydı ilk boyamada sitenin varsayılan
 * zemini/rengi görünüp sonra markaya "sıçrardı". Bu yardımcı, arka ucun özet
 * yanıtındaki `marka` alanından (`services/marka.py` `acik_marka`) sunucuda küçük
 * bir `<style id="marka-temasi">` üretiyor:
 *
 *   :root { --marka-ana … --marka-ilk-zemin …}  html, body { background; color }
 *
 * CSP: `style-src` zaten `'unsafe-inline'` içeriyor (`_ortak/csp.js`) — satır içi
 * `<style>` izinli; betik YOK. Değerler arka uçta sabit listelerden geliyor, burada
 * da yeniden denetleniyor (`#rrggbb`, bilinen zemin/köşe/yazı tipi) — tanınmayan
 * değer hiç yazılmıyor (stil enjeksiyonu yok).
 *
 * Sayfanın kendi açık teması varsa (`marka.sayfa_ozel`) o öncelikli: marka
 * değişkenleri yazılmıyor, ilk boyama sayfanın kendi rengiyle.
 *
 * `_` önekli klasör: rota değil (yalnız içe aktarılıyor; `onRequest*` dışa aktarmıyor).
 */

export const RENK = /^#[0-9a-f]{6}$/i;

/** Arka uç `ZEMIN_RENKLERI` ve `src/lib/marka.ts` ile aynı. */
export const ZEMIN_RENKLERI = {
  koyu: { zemin: '#0b0b12', yuzey: '#16161f', metin: '#f4f4f7', soluk: '#a1a1aa', cerceve: '#2a2a36' },
  acik: { zemin: '#f7f7f8', yuzey: '#ffffff', metin: '#111827', soluk: '#4b5563', cerceve: '#e5e7eb' },
};
export const YAZI_YIGINLARI = {
  jakarta: "'Plus Jakarta Sans', 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  sistem_sans: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', Arial, sans-serif",
  sistem_serif: "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif",
  mono: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
};
export const KOSE_DEGERLERI = { keskin: ['4px', '4px'], yumusak: ['16px', '10px'], yuvarlak: ['28px', '18px'] };

/** Kartvizit şablonlarının düz zemin rengi (`src/lib/kartvizitAcik.ts` SABLONLAR'ın ilk boyama karşılığı). */
export const KART_SABLON_ZEMIN = {
  gece: { zemin: '#0b0714', metin: '#f4f0fb' },
  beyaz: { zemin: '#f5f6fa', metin: '#0f172a' },
  kurumsal: { zemin: '#eef2f7', metin: '#0f172a' },
  canli: { zemin: null, metin: '#111827' }, // zemin = kartın vurgu rengi
  doga: { zemin: '#f3f1ea', metin: '#1c2a1f' },
};

/** WCAG göreli parlaklığına göre rengin üstündeki yazı (arka uç `yazi_rengi` ile aynı kural). */
export function yaziRengi(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return '#ffffff';
  const kanal = (i) => {
    const s = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * kanal(0) + 0.7152 * kanal(2) + 0.0722 * kanal(4);
  return 1.05 / (l + 0.05) >= (l + 0.05) / (0.0056 + 0.05) ? '#ffffff' : '#111111';
}

/** Yanıttaki marka teması — biçimi denetlenmiş kopya ya da null. */
export function markaTemasi(marka) {
  const t = marka && typeof marka === 'object' ? marka.tema : null;
  if (!t || typeof t !== 'object') return null;
  if (!RENK.test(t.ana || '') || !RENK.test(t.vurgu || '')) return null;
  if (!ZEMIN_RENKLERI[t.zemin] || !KOSE_DEGERLERI[t.kose] || !YAZI_YIGINLARI[t.yazi_tipi]) return null;
  return {
    ana: t.ana.toLowerCase(),
    ana_yazi: RENK.test(t.ana_yazi || '') ? t.ana_yazi.toLowerCase() : '#ffffff',
    vurgu: t.vurgu.toLowerCase(),
    vurgu_yazi: RENK.test(t.vurgu_yazi || '') ? t.vurgu_yazi.toLowerCase() : '#ffffff',
    zemin: t.zemin,
    kose: t.kose,
    yazi_tipi: t.yazi_tipi,
  };
}

/** Marka uygulanacak mı: tema var ve sayfanın kendi teması yok. */
export function markaUygulanir(marka) {
  return !!markaTemasi(marka) && !(marka && marka.sayfa_ozel === true);
}

/** `--marka-*` bildirimleri (`;` ile). */
export function markaDegiskenleri(t) {
  const z = ZEMIN_RENKLERI[t.zemin];
  const [kart, dugme] = KOSE_DEGERLERI[t.kose];
  return [
    ['--marka-ana', t.ana],
    ['--marka-ana-yazi', t.ana_yazi],
    ['--marka-vurgu', t.vurgu],
    ['--marka-vurgu-yazi', t.vurgu_yazi],
    ['--marka-zemin', z.zemin],
    ['--marka-yuzey', z.yuzey],
    ['--marka-metin', z.metin],
    ['--marka-soluk', z.soluk],
    ['--marka-cerceve', z.cerceve],
    ['--marka-kose', kart],
    ['--marka-kose-dugme', dugme],
    ['--marka-yazi-tipi', YAZI_YIGINLARI[t.yazi_tipi]],
  ]
    .map(([ad, deger]) => `${ad}:${deger}`)
    .join(';');
}

/**
 * `<style id="marka-temasi">`: kök değişkenler + ilk boyama zemini/yazısı.
 * `zemin`/`metin` biçimi tutmazsa ilgili kural yazılmıyor.
 */
export function ilkBoyamaStili({ zemin, metin, degiskenler = '' }) {
  const kok = [];
  if (degiskenler) kok.push(degiskenler);
  const govde = [];
  if (RENK.test(zemin || '')) {
    kok.push(`--marka-ilk-zemin:${zemin}`);
    govde.push(`background:${zemin} !important`);
  }
  if (RENK.test(metin || '')) {
    kok.push(`--marka-ilk-metin:${metin}`);
    govde.push(`color:${metin}`);
  }
  if (!kok.length) return '';
  return `<style id="marka-temasi">:root{${kok.join(';')}}${govde.length ? `html,html body{${govde.join(';')}}` : ''}</style>`;
}

/**
 * Kartvizit: kartın kendi teması (özel) ya da marka teması → ilk boyama.
 * `ozet`: `GET /api/v1/kart/<slug>/ozet` (alanlar: `tema`, `marka`).
 */
export function kartIlkBoyama(ozet) {
  if (!ozet || typeof ozet !== 'object') return '';
  if (markaUygulanir(ozet.marka)) {
    const t = markaTemasi(ozet.marka);
    const z = ZEMIN_RENKLERI[t.zemin];
    return ilkBoyamaStili({ zemin: z.zemin, metin: z.metin, degiskenler: markaDegiskenleri(t) });
  }
  const tema = ozet.tema && typeof ozet.tema === 'object' ? ozet.tema : null;
  if (!tema) return '';
  const s = KART_SABLON_ZEMIN[tema.sablon] || KART_SABLON_ZEMIN.gece;
  const zemin = s.zemin || (RENK.test(tema.renk || '') ? tema.renk : KART_SABLON_ZEMIN.gece.zemin);
  return ilkBoyamaStili({ zemin, metin: s.metin });
}

/**
 * Menü / randevu: marka uygulanıyorsa değişkenler (+ istenirse zemin). Döner:
 * `{ stil, ana, tema }` — `ana` iskeletteki dönen halkanın rengi (sayfanın kendi rengi öncelikli).
 */
export function sayfaIlkBoyama(marka, { sayfaRengi = null, zeminUygula = false } = {}) {
  const t = markaTemasi(marka);
  if (!t) return { stil: '', ana: null, tema: null };
  const ozel = marka.sayfa_ozel === true;
  const ana = ozel && RENK.test(sayfaRengi || '') ? sayfaRengi : t.ana;
  const z = ZEMIN_RENKLERI[t.zemin];
  const degiskenler = markaDegiskenleri({ ...t, ana, ana_yazi: ana === t.ana ? t.ana_yazi : yaziRengi(ana) });
  const stil = zeminUygula
    ? ilkBoyamaStili({ zemin: z.zemin, metin: z.metin, degiskenler })
    : ilkBoyamaStili({ degiskenler });
  return { stil, ana, tema: t };
}
