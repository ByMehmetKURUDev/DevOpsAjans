/**
 * `public/_headers` denetimi (Cloudflare Pages biçimi).
 *
 * Yerel önizleme sunucusu `_headers` dosyasını uygulamıyor; yanlış yazılmış
 * bir kural ancak yayında, sessizce etkisiz kalarak fark ediliyordu. Bu
 * betik derlemenin sonunda çalışıyor:
 *
 *  1. Dosyayı Cloudflare'in kurallarıyla ayrıştırıyor (yol satırı sütun
 *     0'da, başlık satırları girintili `Ad: değer`, satır ≤ 2000 karakter,
 *     en çok 100 kural) ve her yol için hangi başlıkların düştüğünü yazıyor.
 *  2. `/*` kuralında zorunlu güvenlik başlıklarının varlığını denetliyor.
 *  3. CSP'yi yönergelerine ayırıp derlenen HTML'deki (dist) her satır içi
 *     betiğin ve satır içi olay işleyicisinin hash'i `script-src`'de var mı
 *     bakıyor. index.html'deki bir betik değişip hash güncellenmezse:
 *       - CSP yalnız rapor modundaysa UYARI (derleme sürer),
 *       - CSP zorunluysa HATA (derleme durur; yoksa site betiksiz kalır).
 *
 * Kullanım: `node scripts/guvenlik-basliklari.mjs [--json]`
 * Sözdizimi hatasında çıkış kodu 1.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dosya = fs.existsSync(path.join(kok, 'dist', '_headers'))
  ? path.join(kok, 'dist', '_headers')
  : path.join(kok, 'public', '_headers');

const ZORUNLU = [
  'strict-transport-security',
  'x-frame-options',
  'x-content-type-options',
  'referrer-policy',
  'permissions-policy',
];

/** Cloudflare `_headers` ayrıştırıcısı: [{ yol, basliklar: [[ad, deger]], satir }]. */
export function ayristir(metin) {
  const kurallar = [];
  const hatalar = [];
  let simdiki = null;
  metin.split(/\r?\n/).forEach((satir, i) => {
    const no = i + 1;
    if (satir.length > 2000) hatalar.push(`${no}. satır 2000 karakteri aşıyor (${satir.length})`);
    if (!satir.trim() || satir.trim().startsWith('#')) return;
    if (!/^\s/.test(satir)) {
      const yol = satir.trim();
      if (!/^(\/|https?:\/\/)/.test(yol)) hatalar.push(`${no}. satır: yol "/" ya da "https://" ile başlamalı: ${yol}`);
      simdiki = { yol, basliklar: [], satir: no };
      kurallar.push(simdiki);
      return;
    }
    if (!simdiki) {
      hatalar.push(`${no}. satır: yol satırından önce başlık`);
      return;
    }
    const m = satir.trim().match(/^(!?)([A-Za-z0-9-]+):\s*(.*)$/);
    if (!m) {
      hatalar.push(`${no}. satır: "Ad: değer" biçiminde değil: ${satir.trim().slice(0, 60)}`);
      return;
    }
    if (m[1] === '!') simdiki.basliklar.push([`!${m[2].toLowerCase()}`, '']);
    else {
      if (!m[3]) hatalar.push(`${no}. satır: ${m[2]} değeri boş`);
      simdiki.basliklar.push([m[2].toLowerCase(), m[3]]);
    }
  });
  if (kurallar.length > 100) hatalar.push(`kural sayısı ${kurallar.length} > 100`);
  return { kurallar, hatalar };
}

/** CSP metnini { yönerge: [değerler] } haritasına çevirir. */
export function cspAyristir(deger) {
  const harita = {};
  for (const parca of deger.split(';')) {
    const [ad, ...degerler] = parca.trim().split(/\s+/).filter(Boolean);
    if (!ad) continue;
    harita[ad.toLowerCase()] = degerler;
  }
  return harita;
}

function htmlDosyalari(dizin) {
  if (!fs.existsSync(dizin)) return [];
  const sonuc = [];
  for (const g of fs.readdirSync(dizin, { withFileTypes: true })) {
    const tam = path.join(dizin, g.name);
    if (g.isDirectory()) sonuc.push(...htmlDosyalari(tam));
    else if (g.name.endsWith('.html')) sonuc.push(tam);
  }
  return sonuc;
}

const hash = (metin) => `'sha256-${crypto.createHash('sha256').update(metin, 'utf8').digest('base64')}'`;

/** HTML'deki satır içi betiklerin ve olay işleyicilerinin hash'leri. */
export function satirIciHashler(html) {
  const betikler = new Map();
  const isleyiciler = new Map();
  for (const m of html.matchAll(/<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/gi)) {
    if (/type=["']?application\/(ld\+)?json/i.test(m[1])) continue;
    betikler.set(hash(m[2]), m[2].trim().slice(0, 60).replace(/\s+/g, ' '));
  }
  for (const m of html.matchAll(/\son[a-z]+=(?:"([^"]*)"|'([^']*)')/gi)) {
    const kod = m[1] ?? m[2];
    isleyiciler.set(hash(kod), kod);
  }
  return { betikler, isleyiciler };
}

function calistir() {
  const metin = fs.readFileSync(dosya, 'utf8');
  const { kurallar, hatalar } = ayristir(metin);
  const uyarilar = [];

  const genel = kurallar.find((k) => k.yol === '/*');
  if (!genel) hatalar.push('"/*" kuralı yok');
  const basliklar = Object.fromEntries(genel?.basliklar ?? []);
  for (const ad of ZORUNLU) if (!basliklar[ad]) hatalar.push(`"/*" kuralında ${ad} yok`);
  if (/preload/i.test(basliklar['strict-transport-security'] ?? '')) uyarilar.push('HSTS preload içeriyor');

  const cspAdi = basliklar['content-security-policy']
    ? 'content-security-policy'
    : basliklar['content-security-policy-report-only']
      ? 'content-security-policy-report-only'
      : null;
  const zorunlu = cspAdi === 'content-security-policy';
  let csp = {};
  if (!cspAdi) hatalar.push('CSP başlığı yok');
  else {
    csp = cspAyristir(basliklar[cspAdi]);
    for (const y of ['default-src', 'script-src', 'object-src', 'base-uri', 'frame-ancestors']) {
      if (!csp[y]) hatalar.push(`CSP'de ${y} yok`);
    }
    if (!zorunlu && csp['upgrade-insecure-requests']) uyarilar.push('upgrade-insecure-requests rapor modunda yok sayılır');
  }

  // Derlenen HTML'deki satır içi kodlar CSP'de izinli mi?
  const izinli = new Set(csp['script-src'] ?? []);
  const eksik = new Map();
  const sayfalar = htmlDosyalari(path.join(kok, 'dist'));
  for (const f of sayfalar) {
    const { betikler, isleyiciler } = satirIciHashler(fs.readFileSync(f, 'utf8'));
    for (const [h, ozet] of betikler) if (!izinli.has(h)) eksik.set(h, `betik: ${ozet}`);
    for (const [h, kod] of isleyiciler) {
      if (!izinli.has(h) || !izinli.has("'unsafe-hashes'")) eksik.set(h, `olay işleyici: ${kod}`);
    }
  }
  for (const [h, ne] of eksik) {
    const satir = `script-src'de hash yok ${h} (${ne})`;
    (zorunlu ? hatalar : uyarilar).push(satir);
  }

  const rapor = {
    dosya: path.relative(kok, dosya),
    kurallar: kurallar.map((k) => ({ yol: k.yol, basliklar: k.basliklar.map(([a]) => a) })),
    csp: cspAdi ? { baslik: cspAdi, yonergeler: Object.keys(csp) } : null,
    taranan_html: sayfalar.length,
    hatalar,
    uyarilar,
  };

  if (process.argv.includes('--json')) {
    console.log(JSON.stringify(rapor, null, 2));
  } else {
    console.log(`[_headers] ${rapor.dosya}: ${kurallar.length} kural, ${sayfalar.length} HTML tarandı`);
    for (const k of kurallar) console.log(`  ${k.yol} → ${k.basliklar.map(([a]) => a).join(', ')}`);
    if (cspAdi) console.log(`  CSP (${zorunlu ? 'zorunlu' : 'yalnız rapor'}): ${Object.keys(csp).join(' ')}`);
    for (const u of uyarilar) console.warn(`  UYARI: ${u}`);
    for (const h of hatalar) console.error(`  HATA: ${h}`);
  }
  if (hatalar.length) process.exitCode = 1;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) calistir();
