import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { paylasimJpgListesi } from '../prerender/paylasim-jpg.js';
import { SITE_OG_IMAGE, paylasimGorseli, paylasimGorseliBoyutluMu } from '../prerender/site.js';

test('paylasimGorseli: yalnız kendi WebP kapaklarımız JPG eşine çevriliyor', () => {
  assert.equal(paylasimGorseli(SITE_OG_IMAGE), 'https://mehmetkuru.dev/assets/og-cover.jpg');
  assert.equal(
    paylasimGorseli('https://mehmetkuru.dev/blog-covers/seo-nedir.webp'),
    'https://mehmetkuru.dev/blog-covers/seo-nedir.jpg',
  );
  // Panelden yüklenen ya da dış görsellere dokunulmuyor.
  assert.equal(paylasimGorseli('https://mehmetkuru.dev/uploads/a.webp'), 'https://mehmetkuru.dev/uploads/a.webp');
  assert.equal(paylasimGorseli('https://ornek.com/blog-covers/a.webp'), 'https://ornek.com/blog-covers/a.webp');
  assert.equal(paylasimGorseli('https://mehmetkuru.dev/blog-covers/a.webp?v=2'), 'https://mehmetkuru.dev/blog-covers/a.webp?v=2');
  assert.equal(paylasimGorseli(undefined), undefined);
});

test('paylasimGorseliBoyutluMu: 1200x630 yalnız kendi JPG kapaklarımız için', () => {
  assert.equal(paylasimGorseliBoyutluMu('https://mehmetkuru.dev/assets/og-cover.jpg'), true);
  assert.equal(paylasimGorseliBoyutluMu('https://mehmetkuru.dev/blog-covers/x.jpg'), true);
  assert.equal(paylasimGorseliBoyutluMu('https://mehmetkuru.dev/uploads/x.jpg'), false);
  assert.equal(paylasimGorseliBoyutluMu('https://mehmetkuru.dev/blog-covers/x.webp'), false);
});

test('paylasimJpgListesi: public/ altındaki JPG eşleri', () => {
  const dizin = fs.mkdtempSync(path.join(os.tmpdir(), 'jpg-'));
  fs.mkdirSync(path.join(dizin, 'assets'));
  fs.mkdirSync(path.join(dizin, 'blog-covers'));
  fs.writeFileSync(path.join(dizin, 'assets', 'og-cover.jpg'), '');
  fs.writeFileSync(path.join(dizin, 'blog-covers', 'b.jpg'), '');
  fs.writeFileSync(path.join(dizin, 'blog-covers', 'a.jpg'), '');
  fs.writeFileSync(path.join(dizin, 'blog-covers', 'c.webp'), '');
  assert.deepEqual(paylasimJpgListesi(dizin), ['/assets/og-cover.jpg', '/blog-covers/a.jpg', '/blog-covers/b.jpg']);
});

test('depodaki her kapak WebP için JPG eşi var (npm run covers ikisini birlikte üretir)', () => {
  const kok = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', 'public');
  const eksik = fs
    .readdirSync(path.join(kok, 'blog-covers'))
    .filter((ad) => ad.endsWith('.webp'))
    .filter((ad) => !fs.existsSync(path.join(kok, 'blog-covers', ad.replace(/\.webp$/, '.jpg'))));
  assert.deepEqual(eksik, []);
  assert.ok(fs.existsSync(path.join(kok, 'assets', 'og-cover.jpg')));
});
