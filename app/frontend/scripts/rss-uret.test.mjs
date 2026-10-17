import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { AKISLAR, akisUret, rfc822, robotsaAkisEkle, xmlKacis, yazilariOku } from './rss-uret.mjs';

test('rfc822: tarih İstanbul saatiyle, geçersiz tarih null', () => {
  assert.equal(rfc822('2026-03-04'), 'Wed, 04 Mar 2026 09:00:00 +0300');
  assert.equal(rfc822(''), null);
  assert.equal(rfc822('tarih yok'), null);
});

test('xmlKacis: özel karakterler kaçırılıyor', () => {
  assert.equal(xmlKacis(`A & B <c> "d" 'e'`), 'A &amp; B &lt;c&gt; &quot;d&quot; &apos;e&apos;');
});

test('yazilariOku: en yeni önce, tarihsiz ve taslak yazı akışa girmez', () => {
  const dizin = fs.mkdtempSync(path.join(os.tmpdir(), 'rss-'));
  const yaz = (ad, fm) => fs.writeFileSync(path.join(dizin, ad), `---\n${fm}\n---\nmetin\n`);
  yaz('eski.md', 'title: "Eski"\ndate: "2026-01-02"');
  yaz('yeni.md', 'title: "Yeni"\ndate: "2026-05-06"\ncategory: "SEO"');
  yaz('tarihsiz.md', 'title: "Tarihsiz"');
  yaz('taslak.md', 'title: "Taslak"\ndate: "2026-06-01"\ndraft: true');
  const liste = yazilariOku(dizin);
  assert.deepEqual(liste.map((y) => y.slug), ['yeni', 'eski']);
});

test('akisUret: geçerli RSS iskeleti, kalıcı bağlantı ve JPG kapak', () => {
  const publicDizini = fs.mkdtempSync(path.join(os.tmpdir(), 'rss-pub-'));
  fs.mkdirSync(path.join(publicDizini, 'blog-covers'));
  fs.writeFileSync(path.join(publicDizini, 'blog-covers', 'seo-nedir.jpg'), Buffer.alloc(1234));
  const xml = akisUret(
    [
      { slug: 'seo-nedir', baslik: 'SEO & Sıralama', aciklama: 'Açıklama', kategori: 'SEO', tarih: '2026-03-04' },
      { slug: 'kapaksiz', baslik: 'Kapaksız', aciklama: '', kategori: '', tarih: '2026-03-01' },
    ],
    publicDizini,
  );
  assert.match(xml, /^<\?xml version="1.0" encoding="UTF-8"\?>\n<rss version="2.0"/);
  assert.match(xml, /<atom:link href="https:\/\/mehmetkuru.dev\/rss.xml" rel="self"/);
  assert.match(xml, /<link>https:\/\/mehmetkuru.dev\/blog\/seo-nedir\/<\/link>/);
  assert.match(xml, /<guid isPermaLink="true">https:\/\/mehmetkuru.dev\/blog\/seo-nedir\/<\/guid>/);
  assert.match(xml, /<title>SEO &amp; Sıralama<\/title>/);
  assert.match(xml, /<enclosure url="https:\/\/mehmetkuru.dev\/blog-covers\/seo-nedir.jpg" length="1234" type="image\/jpeg" \/>/);
  assert.equal((xml.match(/<enclosure /g) || []).length, 1);
  assert.match(xml, /<lastBuildDate>Wed, 04 Mar 2026 09:00:00 \+0300<\/lastBuildDate>/);
});

test('robotsaAkisEkle: Sitemap satırı bir kez eklenir', () => {
  const eski = 'User-agent: *\nAllow: /\n\nSitemap: https://mehmetkuru.dev/sitemap.xml';
  const yeni = robotsaAkisEkle(eski);
  assert.equal(yeni, `${eski}\nSitemap: https://mehmetkuru.dev/rss.xml\n`);
  assert.equal(robotsaAkisEkle(yeni), yeni);
});

test('akisUret (google): 4:3 kapak, kendi self bağlantısı ve başlık eki', () => {
  const publicDizini = fs.mkdtempSync(path.join(os.tmpdir(), 'rss-g-'));
  fs.mkdirSync(path.join(publicDizini, 'blog-covers', 'sosyal'), { recursive: true });
  fs.writeFileSync(path.join(publicDizini, 'blog-covers', 'seo-nedir.jpg'), Buffer.alloc(10));
  fs.writeFileSync(path.join(publicDizini, 'blog-covers', 'sosyal', 'seo-nedir-4x3.jpg'), Buffer.alloc(4321));
  const xml = akisUret(
    [{ slug: 'seo-nedir', baslik: 'SEO', aciklama: 'A', kategori: 'SEO', tarih: '2026-03-04' }],
    publicDizini,
    AKISLAR.google,
  );
  assert.match(xml, /<atom:link href="https:\/\/mehmetkuru.dev\/rss-google.xml" rel="self"/);
  assert.match(xml, /<title>By Mehmet KURU Dev — Blog \(Google İşletme\)<\/title>/);
  assert.match(xml, /<enclosure url="https:\/\/mehmetkuru.dev\/blog-covers\/sosyal\/seo-nedir-4x3.jpg" length="4321" type="image\/jpeg" \/>/);
  assert.doesNotMatch(xml, /blog-covers\/seo-nedir.jpg/);
});
