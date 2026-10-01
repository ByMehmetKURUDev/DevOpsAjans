/**
 * Faz 5R — gömülebilir randevu betiğinin (public/randevu-widget.js) testi.
 * Çalıştır: node --test scripts/randevu-widget.test.mjs
 *
 * Küçültülmüş çıktı küçük bir DOM taklidiyle vm içinde koşturulur: satır içi
 * çerçeve, açılır pencere, yükseklik iletisi (yalnız doğru köken ve doğru
 * çerçeveden), tamamlanma olayı, geçersiz yol ve tekrar tarama.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const DOSYA = new URL('../public/randevu-widget.js', import.meta.url);
const KAYNAK = new URL('./randevu-widget.kaynak.js', import.meta.url);
const kod = fs.readFileSync(DOSYA, 'utf8');

class Olay {
  constructor(tur, oz = {}) {
    this.type = tur;
    this.bubbles = !!oz.bubbles;
    this.detail = oz.detail;
    this.defaultPrevented = false;
  }
  preventDefault() {
    this.defaultPrevented = true;
  }
}

function dunya({ betikSrc = 'https://mehmetkuru.dev/randevu-widget.js', adres = null } = {}) {
  const dinleyiciler = new Map();
  const dinle = (hedef) => {
    hedef._d = {};
    hedef.addEventListener = (t, f) => (hedef._d[t] = hedef._d[t] || []).push(f);
    hedef.removeEventListener = (t, f) => (hedef._d[t] = (hedef._d[t] || []).filter((x) => x !== f));
    hedef.dispatchEvent = (o) => {
      let h = hedef;
      while (h) {
        o.target = o.target || hedef;
        o.currentTarget = h;
        for (const f of (h._d && h._d[o.type]) || []) f(o);
        if (!o.bubbles) break;
        h = h.parentNode;
      }
      return true;
    };
  };
  function el(ad) {
    const e = {
      tagName: ad.toUpperCase(),
      attrs: {},
      children: [],
      parentNode: null,
      style: { cssText: '' },
      setAttribute(k, v) {
        this.attrs[k] = String(v);
      },
      getAttribute(k) {
        return k in this.attrs ? this.attrs[k] : null;
      },
      hasAttribute(k) {
        return k in this.attrs;
      },
      appendChild(c) {
        c.parentNode = this;
        this.children.push(c);
        return c;
      },
      removeChild(c) {
        this.children = this.children.filter((x) => x !== c);
        c.parentNode = null;
        return c;
      },
      contains(c) {
        for (let h = c; h; h = h.parentNode) if (h === this) return true;
        return false;
      },
      focus() {
        belge.activeElement = this;
      },
    };
    dinle(e);
    if (ad === 'iframe') e.contentWindow = { iframe: true };
    return e;
  }
  const govde = el('body');
  const kok = el('html');
  kok.style.overflow = '';
  kok.appendChild(govde);
  const tumu = () => {
    const out = [];
    const gez = (n) => {
      for (const c of n.children) {
        out.push(c);
        gez(c);
      }
    };
    gez(kok);
    return out;
  };
  const belge = {
    readyState: 'complete',
    body: govde,
    documentElement: kok,
    activeElement: govde,
    currentScript: (() => {
      const s = el('script');
      s.src = betikSrc;
      if (adres) s.setAttribute('data-adres', adres);
      return s;
    })(),
    createElement: el,
    createEvent: () => ({ initCustomEvent() {} }),
    querySelectorAll(secici) {
      const m = secici.match(/^\[([a-z-]+)\]:not\(\[([a-z-]+)\]\)$/);
      assert.ok(m, 'beklenmeyen seçici: ' + secici);
      return tumu().filter((n) => n.hasAttribute(m[1]) && !n.hasAttribute(m[2]));
    },
  };
  dinle(belge);
  const pencere = { location: { href: 'https://musteri.example/sayfa', origin: 'https://musteri.example' } };
  dinle(pencere);
  const baglam = vm.createContext({
    window: pencere,
    document: belge,
    location: pencere.location,
    URL,
    CustomEvent: Olay,
    Number,
    Math,
    String,
  });
  pencere.document = belge;
  const kos = () => vm.runInContext(kod, baglam);
  const ileti = (veri, kaynak, origin = 'https://mehmetkuru.dev') =>
    pencere.dispatchEvent(Object.assign(new Olay('message'), { data: veri, source: kaynak, origin }));
  return { belge, pencere, govde, el, kos, ileti, tumu, dinleyiciler };
}

const cerceveler = (d) => d.tumu().filter((n) => n.tagName === 'IFRAME');

test('boyut: küçültülmüş betik 4 kB altında, kaynakla eşleşen başlık; kaynak okunur halde duruyor', () => {
  assert.ok(Buffer.byteLength(kod) < 4096, `betik ${Buffer.byteLength(kod)} bayt`);
  assert.ok(kod.startsWith('/*! By Mehmet KURU Dev'));
  const kaynak = fs.readFileSync(KAYNAK, 'utf8');
  for (const p of ['data-mk-randevu', 'data-mk-randevu-ac', 'gomulu=1', 'mk-randevu-tamam', 'MKRandevu']) {
    assert.ok(kaynak.includes(p) && kod.includes(p), p);
  }
  assert.ok(!/fetch\(|XMLHttpRequest|localStorage|document\.cookie/.test(kod), 'betik ağ isteği/çerez kullanmamalı');
});

test('satır içi: data-mk-randevu → ?gomulu=1 çerçevesi, dil parametresi, betiğin kökeni', () => {
  const d = dunya();
  const a = d.el('div');
  a.setAttribute('data-mk-randevu', 'Ayse-D/tanisma');
  a.setAttribute('data-mk-dil', 'EN');
  d.govde.appendChild(a);
  d.kos();
  const f = cerceveler(d);
  assert.equal(f.length, 1);
  assert.equal(f[0].src, 'https://mehmetkuru.dev/randevu/ayse-d/tanisma?gomulu=1&dil=en');
  assert.equal(f[0].parentNode, a);
  assert.ok(a.hasAttribute('data-mk-hazir'));
  assert.match(f[0].style.cssText, /width:100%/);
  assert.equal(f[0].loading, 'lazy');
});

test('geçersiz yol çerçeve üretmez; data-adres kökeni değiştirir; tekrar tarama ikinci çerçeve eklemez', () => {
  const d = dunya({ adres: 'https://randevu.ornek.dev/' });
  const kotu = d.el('div');
  kotu.setAttribute('data-mk-randevu', '../../admin');
  const iyi = d.el('div');
  iyi.setAttribute('data-mk-randevu', 'ayse-d');
  iyi.setAttribute('data-mk-dil', 'javascript:');
  d.govde.appendChild(kotu);
  d.govde.appendChild(iyi);
  d.kos();
  let f = cerceveler(d);
  assert.equal(f.length, 1);
  assert.equal(f[0].src, 'https://randevu.ornek.dev/randevu/ayse-d?gomulu=1');
  // Betik ikinci kez yüklenirse (ya da MKRandevu.tara()) yeni öğeleri işler, eskileri ellemez.
  const yeni = d.el('div');
  yeni.setAttribute('data-mk-randevu', 'mehmet-k');
  d.govde.appendChild(yeni);
  d.kos();
  d.pencere.MKRandevu.tara();
  f = cerceveler(d);
  assert.deepEqual(f.map((x) => x.src), ['https://randevu.ornek.dev/randevu/ayse-d?gomulu=1', 'https://randevu.ornek.dev/randevu/mehmet-k?gomulu=1']);
});

test('yükseklik iletisi: yalnız doğru köken ve doğru çerçeveden; sınırlar uygulanır', () => {
  const d = dunya();
  const a = d.el('div');
  a.setAttribute('data-mk-randevu', 'ayse-d');
  d.govde.appendChild(a);
  d.kos();
  const [f] = cerceveler(d);
  assert.match(f.style.cssText, /height:640px/);
  d.ileti({ tur: 'mk-randevu', yukseklik: 812.4 }, f.contentWindow, 'https://kotu.example');
  assert.equal(f.style.height, undefined);
  d.ileti({ tur: 'mk-randevu', yukseklik: 812 }, { baska: true });
  assert.equal(f.style.height, undefined);
  d.ileti({ tur: 'mk-randevu', yukseklik: 812 }, f.contentWindow);
  assert.equal(f.style.height, '812px');
  d.ileti({ tur: 'mk-randevu', yukseklik: 999999 }, f.contentWindow);
  assert.equal(f.style.height, '4000px');
  d.ileti({ tur: 'mk-randevu', yukseklik: 'x' }, f.contentWindow);
  assert.equal(f.style.height, '240px');
  d.ileti('metin', f.contentWindow);
  assert.equal(f.style.height, '240px');
});

test('tamamlanma: kapsayıcıda mk-randevu-tamam olayı (uid) kabarır', () => {
  const d = dunya();
  const a = d.el('div');
  a.setAttribute('data-mk-randevu', 'ayse-d');
  d.govde.appendChild(a);
  d.kos();
  const [f] = cerceveler(d);
  const gelen = [];
  d.govde.addEventListener('mk-randevu-tamam', (o) => gelen.push(o.detail.uid));
  d.ileti({ tur: 'mk-randevu-tamam', uid: 'abc' }, f.contentWindow);
  assert.deepEqual(gelen, ['abc']);
});

test('açılır pencere: tık → diyalog + çerçeve; Esc ve arka plan tıkı kapatır, kaydırma geri gelir', () => {
  const d = dunya();
  const b = d.el('button');
  b.setAttribute('data-mk-randevu-ac', 'ayse-d/tanisma');
  d.govde.appendChild(b);
  d.kos();
  assert.equal(cerceveler(d).length, 0);
  const tik = new Olay('click');
  b.dispatchEvent(tik);
  assert.ok(tik.defaultPrevented);
  const diyalog = () => d.tumu().find((n) => n.hasAttribute('data-mk-randevu-pencere'));
  let p = diyalog();
  assert.ok(p, 'diyalog açılmalı');
  assert.equal(p.getAttribute('role'), 'dialog');
  assert.equal(p.getAttribute('aria-modal'), 'true');
  assert.equal(cerceveler(d)[0].src, 'https://mehmetkuru.dev/randevu/ayse-d/tanisma?gomulu=1');
  assert.equal(d.belge.documentElement.style.overflow, 'hidden');
  assert.equal(d.belge.activeElement.tagName, 'BUTTON');
  d.belge.dispatchEvent(Object.assign(new Olay('keydown'), { key: 'Escape' }));
  assert.equal(diyalog(), undefined);
  assert.equal(d.belge.documentElement.style.overflow, '');
  assert.equal(cerceveler(d).length, 0);
  // İkinci açılış; bu kez arka plana tık.
  b.dispatchEvent(new Olay('click'));
  p = diyalog();
  p.dispatchEvent(Object.assign(new Olay('click'), { target: p }));
  assert.equal(diyalog(), undefined);
  // Kapanan pencerenin çerçevesinden gelen ileti artık hiçbir şeyi etkilemez.
  b.dispatchEvent(new Olay('click'));
  const [f] = cerceveler(d);
  d.ileti({ tur: 'mk-randevu', yukseklik: 700 }, f.contentWindow);
  assert.equal(f.style.height, '700px');
});
