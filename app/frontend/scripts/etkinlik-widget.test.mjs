/**
 * Faz 6E — gömülebilir etkinlik betiğinin (public/etkinlik-widget.js) testi.
 * Çalıştır: node --test scripts/etkinlik-widget.test.mjs
 *
 * Küçültülmüş çıktı küçük bir DOM taklidiyle vm içinde koşturulur (randevu testindeki
 * taklit): satır içi kayıt formu ve etkinlik listesi çerçeveleri, açılır pencere,
 * yükseklik iletisi (yalnız doğru köken ve doğru çerçeveden), tamamlanma olayı,
 * geçersiz yol ve tekrar tarama.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const DOSYA = new URL('../public/etkinlik-widget.js', import.meta.url);
const KAYNAK = new URL('./etkinlik-widget.kaynak.js', import.meta.url);
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

function dunya({ betikSrc = 'https://mehmetkuru.dev/etkinlik-widget.js', adres = null } = {}) {
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

test('boyut: küçültülmüş betik 4 kB altında, kaynakla eşleşen başlık; ağ isteği yok', () => {
  assert.ok(Buffer.byteLength(kod) < 4096, `betik ${Buffer.byteLength(kod)} bayt`);
  assert.ok(kod.startsWith('/*! By Mehmet KURU Dev'));
  const kaynak = fs.readFileSync(KAYNAK, 'utf8');
  for (const p of ['data-mk-etkinlik', 'data-mk-etkinlik-ac', 'data-mk-etkinlikler', 'gomulu=1', 'mk-etkinlik-tamam', 'MKEtkinlik']) {
    assert.ok(kaynak.includes(p) && kod.includes(p), p);
  }
  assert.ok(!/fetch\(|XMLHttpRequest|localStorage|document\.cookie/.test(kod), 'betik ağ isteği/çerez kullanmamalı');
});

test('satır içi: data-mk-etkinlik → /etkinlik/<slug>?gomulu=1, dil; data-mk-etkinlikler → liste', () => {
  const d = dunya();
  const a = d.el('div');
  a.setAttribute('data-mk-etkinlik', 'AI-Atolyesi');
  a.setAttribute('data-mk-dil', 'EN');
  const l = d.el('div');
  l.setAttribute('data-mk-etkinlikler', 'ajans-etkinlikleri');
  d.govde.appendChild(a);
  d.govde.appendChild(l);
  d.kos();
  const f = cerceveler(d);
  assert.deepEqual(f.map((x) => x.src), [
    'https://mehmetkuru.dev/etkinlik/ai-atolyesi?gomulu=1&dil=en',
    'https://mehmetkuru.dev/etkinlikler/ajans-etkinlikleri?gomulu=1',
  ]);
  assert.equal(f[0].parentNode, a);
  assert.equal(f[1].parentNode, l);
  assert.ok(a.hasAttribute('data-mk-hazir') && l.hasAttribute('data-mk-hazir'));
  assert.equal(f[0].loading, 'lazy');
  assert.equal(f[0].title, 'Etkinlik');
});

test('geçersiz yol çerçeve üretmez (alt yol, bilet/jeton yolu); data-adres kökeni; tekrar tarama', () => {
  const d = dunya({ adres: 'https://etkinlik.ornek.dev/' });
  for (const kotu of ['../../admin', 'ai-atolyesi/bilet/1-abc', 'x', 'javascript:alert(1)']) {
    const k = d.el('div');
    k.setAttribute('data-mk-etkinlik', kotu);
    d.govde.appendChild(k);
  }
  const iyi = d.el('div');
  iyi.setAttribute('data-mk-etkinlik', 'seminer-2026');
  iyi.setAttribute('data-mk-dil', 'javascript:');
  d.govde.appendChild(iyi);
  d.kos();
  let f = cerceveler(d);
  assert.deepEqual(f.map((x) => x.src), ['https://etkinlik.ornek.dev/etkinlik/seminer-2026?gomulu=1']);
  const yeni = d.el('div');
  yeni.setAttribute('data-mk-etkinlik', 'konser-aksam');
  d.govde.appendChild(yeni);
  d.kos();
  d.pencere.MKEtkinlik.tara();
  f = cerceveler(d);
  assert.deepEqual(f.map((x) => x.src), ['https://etkinlik.ornek.dev/etkinlik/seminer-2026?gomulu=1', 'https://etkinlik.ornek.dev/etkinlik/konser-aksam?gomulu=1']);
});

test('yükseklik iletisi: yalnız doğru köken ve doğru çerçeveden; sınırlar uygulanır', () => {
  const d = dunya();
  const a = d.el('div');
  a.setAttribute('data-mk-etkinlik', 'seminer-2026');
  d.govde.appendChild(a);
  d.kos();
  const [f] = cerceveler(d);
  assert.match(f.style.cssText, /height:640px/);
  d.ileti({ tur: 'mk-etkinlik', yukseklik: 900 }, f.contentWindow, 'https://kotu.example');
  assert.equal(f.style.height, undefined);
  d.ileti({ tur: 'mk-etkinlik', yukseklik: 900 }, { baska: true });
  assert.equal(f.style.height, undefined);
  d.ileti({ tur: 'mk-randevu', yukseklik: 900 }, f.contentWindow);
  assert.equal(f.style.height, undefined);
  d.ileti({ tur: 'mk-etkinlik', yukseklik: 900 }, f.contentWindow);
  assert.equal(f.style.height, '900px');
  d.ileti({ tur: 'mk-etkinlik', yukseklik: 999999 }, f.contentWindow);
  assert.equal(f.style.height, '4000px');
  d.ileti({ tur: 'mk-etkinlik', yukseklik: 'x' }, f.contentWindow);
  assert.equal(f.style.height, '240px');
});

test('tamamlanma: kapsayıcıda mk-etkinlik-tamam olayı (kod) kabarır', () => {
  const d = dunya();
  const a = d.el('div');
  a.setAttribute('data-mk-etkinlik', 'seminer-2026');
  d.govde.appendChild(a);
  d.kos();
  const [f] = cerceveler(d);
  const gelen = [];
  d.govde.addEventListener('mk-etkinlik-tamam', (o) => gelen.push(o.detail.kod));
  d.ileti({ tur: 'mk-etkinlik-tamam', kod: 'K7Q2M9XH' }, f.contentWindow);
  d.ileti({ tur: 'mk-etkinlik-tamam', kod: 'SAHTE' }, f.contentWindow, 'https://kotu.example');
  assert.deepEqual(gelen, ['K7Q2M9XH']);
});

test('açılır pencere: tık → diyalog + çerçeve; Esc ve arka plan tıkı kapatır, kaydırma geri gelir', () => {
  const d = dunya();
  const b = d.el('button');
  b.setAttribute('data-mk-etkinlik-ac', 'seminer-2026');
  d.govde.appendChild(b);
  d.kos();
  assert.equal(cerceveler(d).length, 0);
  const tik = new Olay('click');
  b.dispatchEvent(tik);
  assert.ok(tik.defaultPrevented);
  const diyalog = () => d.tumu().find((n) => n.hasAttribute('data-mk-etkinlik-pencere'));
  let p = diyalog();
  assert.ok(p, 'diyalog açılmalı');
  assert.equal(p.getAttribute('role'), 'dialog');
  assert.equal(p.getAttribute('aria-modal'), 'true');
  assert.equal(cerceveler(d)[0].src, 'https://mehmetkuru.dev/etkinlik/seminer-2026?gomulu=1');
  assert.equal(d.belge.documentElement.style.overflow, 'hidden');
  d.belge.dispatchEvent(Object.assign(new Olay('keydown'), { key: 'Escape' }));
  assert.equal(diyalog(), undefined);
  assert.equal(d.belge.documentElement.style.overflow, '');
  b.dispatchEvent(new Olay('click'));
  p = diyalog();
  p.dispatchEvent(Object.assign(new Olay('click'), { target: p }));
  assert.equal(diyalog(), undefined);
  assert.equal(cerceveler(d).length, 0);
});
