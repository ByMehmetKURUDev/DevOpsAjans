/**
 * Blog yazıları için kapak görseli üretir.
 *
 * 61 yazının 58'inde `og_image` yoktu: paylaşımlarda görsel çıkmıyor,
 * yazılar da tamamen metin olarak duruyordu. Bu betik her yazı için
 * 1200x630 (OG standardı) bir kapak üretir — kategori rengi, başlık ve
 * kategoriye özgü soyut bir desen.
 *
 * Görseller uydurma ekran görüntüsü ya da uydurma veri içeren grafik
 * DEĞİLDİR; tipografik kapaklardır. Yazının içeriğine dair yanlış bir şey
 * iddia etmezler.
 *
 * Çıktı: public/blog-covers/<slug>.webp
 * Çalıştırma: npm run covers
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import { parse as parseYaml } from 'yaml';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const contentDir = path.join(root, 'seo', 'content');
const outDir = path.join(root, 'public', 'blog-covers');

const W = 1200;
const H = 630;

/** Kategori başına renk ve desen. Sitenin mor paletiyle aynı ailede. */
const CATEGORIES = {
  SEO: { from: '#8b3dff', to: '#ff5db1', motif: 'rings' },
  Reklam: { from: '#ff7a3d', to: '#ff3d81', motif: 'bars' },
  'Veri ve Analitik': { from: '#2fd4c4', to: '#3d8bff', motif: 'grid' },
  'Web Geliştirme': { from: '#5c8bff', to: '#a05cff', motif: 'brackets' },
  Website: { from: '#a05cff', to: '#ff5db1', motif: 'window' },
  SaaS: { from: '#3ddc97', to: '#3d8bff', motif: 'layers' },
};
const FALLBACK = { from: '#8b3dff', to: '#5c27a3', motif: 'rings' };

function escapeXml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** Başlığı satırlara böler — kabaca karakter genişliğine göre. */
function wrap(title, maxChars, maxLines) {
  const words = title.split(/\s+/);
  const lines = [];
  let line = '';

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length > maxChars && line) {
      lines.push(line);
      line = word;
      if (lines.length === maxLines) break;
    } else {
      line = candidate;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);

  if (lines.length === maxLines) {
    const consumed = lines.join(' ').split(/\s+/).length;
    if (consumed < words.length) {
      lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[.,;:]$/, '')}…`;
    }
  }
  return lines;
}

function motifMarkup(motif, from, to) {
  const stroke = `stroke="url(#accent)" fill="none" opacity="0.5"`;
  switch (motif) {
    case 'bars':
      return [40, 110, 70, 160, 100].map((h, i) =>
        `<rect x="${880 + i * 52}" y="${470 - h}" width="30" height="${h}" rx="8" fill="url(#accent)" opacity="${0.25 + i * 0.12}"/>`,
      ).join('');
    case 'grid':
      return Array.from({ length: 5 }, (_, r) =>
        Array.from({ length: 5 }, (_, c) =>
          `<circle cx="${900 + c * 52}" cy="${300 + r * 52}" r="${4 + ((r + c) % 3) * 3}" fill="url(#accent)" opacity="${0.2 + ((r + c) % 4) * 0.14}"/>`,
        ).join(''),
      ).join('');
    case 'brackets':
      return `<path d="M940 300 L880 400 L940 500" ${stroke} stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M1080 300 L1140 400 L1080 500" ${stroke} stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="1030" y1="285" x2="990" y2="515" ${stroke} stroke-width="10" stroke-linecap="round"/>`;
    case 'window':
      return `<rect x="880" y="290" width="240" height="220" rx="18" ${stroke} stroke-width="8"/>
              <line x1="880" y1="340" x2="1120" y2="340" ${stroke} stroke-width="8"/>
              <circle cx="908" cy="315" r="7" fill="url(#accent)" opacity="0.7"/>
              <circle cx="932" cy="315" r="7" fill="url(#accent)" opacity="0.5"/>
              <circle cx="956" cy="315" r="7" fill="url(#accent)" opacity="0.35"/>`;
    case 'layers':
      return [0, 1, 2].map((i) =>
        `<rect x="${890 + i * 14}" y="${300 + i * 62}" width="220" height="52" rx="14" fill="url(#accent)" opacity="${0.5 - i * 0.13}"/>`,
      ).join('');
    default:
      return [0, 1, 2, 3].map((i) =>
        `<circle cx="1010" cy="400" r="${52 + i * 44}" ${stroke} stroke-width="${8 - i}"/>`,
      ).join('');
  }
}

function buildSvg({ title, category }) {
  const palette = CATEGORIES[category] ?? FALLBACK;
  // Metin alanı x=72..820 arası; desen x=880'de başlıyor. Satır uzunluğu
  // ve punto bu sınıra göre seçiliyor, aksi hâlde uzun başlıklar desenin
  // üzerine biniyordu.
  const lines = wrap(title, 22, 4);
  const fontSize = lines.length > 3 ? 46 : 54;
  const startY = 330 - ((lines.length - 1) * (fontSize + 14)) / 2;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${palette.from}"/>
      <stop offset="100%" stop-color="${palette.to}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.18" cy="0.1" r="0.9">
      <stop offset="0%" stop-color="${palette.from}" stop-opacity="0.34"/>
      <stop offset="100%" stop-color="#05010a" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="${W}" height="${H}" fill="#05010a"/>
  <rect width="${W}" height="${H}" fill="url(#glow)"/>
  <rect x="0" y="0" width="10" height="${H}" fill="url(#accent)"/>

  ${motifMarkup(palette.motif, palette.from, palette.to)}

  <text x="72" y="120" font-family="DejaVu Sans, sans-serif" font-size="22" font-weight="700"
        letter-spacing="6" fill="${palette.from}">${escapeXml((category ?? 'BLOG').toUpperCase())}</text>

  ${lines
    .map(
      (line, i) =>
        `<text x="72" y="${startY + i * (fontSize + 14)}" font-family="DejaVu Sans, sans-serif" font-size="${fontSize}" font-weight="700" fill="#ffffff">${escapeXml(line)}</text>`,
    )
    .join('\n  ')}

  <line x1="72" y1="520" x2="360" y2="520" stroke="#ffffff" stroke-opacity="0.18" stroke-width="2"/>
  <text x="72" y="562" font-family="DejaVu Sans, sans-serif" font-size="26" font-weight="600"
        fill="#b9a9d6">mehmetkuru.dev</text>
</svg>`;
}

function readPosts() {
  return fs
    .readdirSync(contentDir)
    .filter((name) => name.endsWith('.md'))
    .map((name) => {
      const raw = fs.readFileSync(path.join(contentDir, name), 'utf8');
      const match = raw.match(/^---\n([\s\S]*?)\n---\n?/);
      const data = match ? parseYaml(match[1]) ?? {} : {};
      return {
        slug: name.replace(/\.md$/, ''),
        title: String(data.title ?? name.replace(/\.md$/, '')),
        category: data.category ? String(data.category) : undefined,
        file: path.join(contentDir, name),
        raw,
        frontmatter: match ? match[0] : null,
      };
    });
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const posts = readPosts();
  let written = 0;
  let stamped = 0;

  for (const post of posts) {
    const svg = buildSvg(post);
    const target = path.join(outDir, `${post.slug}.webp`);

    await sharp(Buffer.from(svg)).webp({ quality: 82 }).toFile(target);
    written += 1;

    // Frontmatter'a og_image / og_image_alt yaz (yoksa).
    if (post.frontmatter && !/^og_image:/m.test(post.frontmatter)) {
      const url = `https://mehmetkuru.dev/blog-covers/${post.slug}.webp`;
      const updated = post.frontmatter.replace(
        /\n---\n?$/,
        `\nog_image: "${url}"\nog_image_alt: "${post.title.replace(/"/g, "'")}"\n---\n`,
      );
      fs.writeFileSync(post.file, post.raw.replace(post.frontmatter, updated), 'utf8');
      stamped += 1;
    }
  }

  const sizes = fs
    .readdirSync(outDir)
    .filter((f) => f.endsWith('.webp'))
    .map((f) => fs.statSync(path.join(outDir, f)).size);

  console.log(`✓ ${written} kapak üretildi → public/blog-covers/`);
  console.log(`✓ ${stamped} yazının frontmatter'ına og_image eklendi`);
  console.log(
    `  boyut: ortalama ${(sizes.reduce((a, b) => a + b, 0) / sizes.length / 1024).toFixed(1)} kB, en büyük ${(Math.max(...sizes) / 1024).toFixed(1)} kB`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
