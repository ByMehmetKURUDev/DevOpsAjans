/**
 * Faz 5A — gömülebilir AI asistan betiğinin (public/asistan-widget.js) testi.
 * Çalıştır: node --test scripts/asistan-widget.test.mjs
 *
 * Küçültülmüş çıktı küçük bir DOM taklidiyle vm içinde koşturulur: boyut (gzip < 6 kB),
 * ağ isteği yok, balon → panel + ?gomulu=1 çerçevesi, dil/renk/konum, el sıkışma
 * (`hazir` → `merhaba` yalnız asistan kökenine), yükseklik ve kapatma iletileri yalnız
 * doğru köken ve doğru çerçeveden; geçersiz anahtar; mobilde tam ekran.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import zlib from 'node:zlib';

const DOSYA = new URL('../public/asistan-widget.js', import.meta.url);
const KAYNAK = new URL('./asistan-widget.kaynak.js', import.meta.url);
const kod = fs.readFileSync(DOSYA, 'utf8');
const ANAHTAR = 'abcd2345efgh6789';

class Olay {
  constructor(tur, oz = {}) {
    this.type = tur;
    this.bubbles = !!oz.bubbles;
    this.defaultPrevented = false;
  }
  preventDefault() {
    this.defaultPrevented = true;
  }
}

function dunya({ oznitelik = {}, betikSrc = 'https://mehmetkuru.dev/asistan-widget.js', genislik = 1280, lang = 'tr', dir = '', yukleniyor = false } = {}) {
  const dinle = (hedef) => {
    hedef._d = {};
    hedef.addEventListener = (t, f) => (hedef._d[t] = hedef._d[t] || []).push(f);
    hedef.removeEventListener = (t, f) => (hedef._d[t] = (hedef._d[t] || []).filter((x) => x !== f));
    hedef.dispatchEvent = (o) => {
      o.target = o.target || hedef;
      for (const f of hedef._d[o.type] || []) f(o);
      return true;
    };
  };
  const gonderilen = [];
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
      appendChild(c) {
        c.parentNode = this;
        this.children.push(c);
        return c;
      },
      focus() {
        belge.activeElement = this;
      },
    };
    Object.defineProperty(e, 'innerHTML', {
      set() {
        throw new Error('innerHTML kullanılmamalı');
      },
    });
    dinle(e);
    if (ad === 'iframe') e.contentWindow = { postMessage: (veri, hedefKoken) => gonderilen.push({ veri, hedefKoken }) };
    return e;
  }
  const govde = el('body');
  const kok = el('html');
  kok.lang = lang;
  kok.dir = dir;
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
  const betik = el('script');
  betik.src = betikSrc;
  for (const [k, v] of Object.entries({ 'data-asistan': ANAHTAR, ...oznitelik })) if (v !== null) betik.setAttribute(k, v);
  const belge = {
    readyState: yukleniyor ? 'loading' : 'complete',
    body: govde,
    documentElement: kok,
    activeElement: govde,
    currentScript: betik,
    createElement: el,
    createElementNS: (_ns, ad) => el(ad),
  };
  dinle(belge);
  const pencere = { innerWidth: genislik, innerHeight: 900, location: { href: 'https://musteri.example/sayfa', origin: 'https://musteri.example' } };
  dinle(pencere);
  let agIstegi = 0;
  const baglam = vm.createContext({
    window: pencere,
    document: belge,
    location: pencere.location,
    URL,
    Number,
    Math,
    String,
    parseInt,
    fetch: () => {
      agIstegi += 1;
    },
    XMLHttpRequest: function () {
      agIstegi += 1;
    },
  });
  pencere.document = belge;
  const kos = () => vm.runInContext(kod, baglam);
  const ileti = (veri, kaynak, origin = 'https://mehmetkuru.dev') => pencere.dispatchEvent(Object.assign(new Olay('message'), { data: veri, source: kaynak, origin }));
  const balon = () => tumu().find((n) => n.tagName === 'BUTTON');
  const panel = () => tumu().find((n) => n.getAttribute('data-mk-asistan-panel') !== null);
  const cerceve = () => tumu().find((n) => n.tagName === 'IFRAME');
  const tikla = () => balon().dispatchEvent(new Olay('click'));
  return { belge, pencere, kok, kos, ileti, balon, panel, cerceve, tikla, gonderilen, agIstegi: () => agIstegi, tumu };
}

test('boyut: gzip 6 kB altında, başlık ve kaynak; ağ isteği, çerez, depolama, innerHTML yok', () => {
  const gz = zlib.gzipSync(kod).length;
  assert.ok(gz < 6144, `gzip ${gz} bayt`);
  assert.ok(kod.startsWith('/*! By Mehmet KURU Dev'));
  const kaynak = fs.readFileSync(KAYNAK, 'utf8');
  for (const p of ['data-asistan', 'gomulu=1', 'mk-asistan', 'merhaba', 'yukseklik', 'MKAsistan']) assert.ok(kaynak.includes(p) && kod.includes(p), p);
  assert.ok(!/fetch\(|XMLHttpRequest|localStorage|sessionStorage|document\.cookie|innerHTML|eval\(/.test(kod), 'betik ağ/çerez/innerHTML kullanmamalı');
});

test('yükleme: yalnız balon; tıklanmadan çerçeve ve ağ isteği yok; ikinci yükleme ikinci balon eklemez', () => {
  const d = dunya();
  d.kos();
  d.kos();
  assert.equal(d.tumu().filter((n) => n.tagName === 'BUTTON').length, 1);
  assert.equal(d.cerceve(), undefined);
  assert.equal(d.agIstegi(), 0);
  const b = d.balon();
  assert.equal(b.getAttribute('aria-expanded'), 'false');
  assert.match(b.style.cssText, /right:16px/);
  assert.match(b.style.cssText, /background:#7c3aed/);
  assert.match(b.style.cssText, /color:#ffffff/);
});

test('balon → panel ve ?gomulu=1 çerçevesi; dil sayfadan, ikinci tık kapatır', () => {
  const d = dunya({ lang: 'de-DE' });
  d.kos();
  d.tikla();
  const f = d.cerceve();
  assert.equal(f.src, `https://mehmetkuru.dev/asistan/${ANAHTAR}?gomulu=1&dil=de`);
  assert.equal(d.balon().getAttribute('aria-expanded'), 'true');
  assert.match(d.panel().style.cssText, /display:block/);
  assert.match(d.panel().style.cssText, /bottom:88px/);
  assert.equal(d.belge.activeElement, f);
  d.tikla();
  assert.match(d.panel().style.cssText, /display:none/);
  assert.equal(d.belge.activeElement, d.balon());
  // Yeniden açınca aynı çerçeve kullanılır (sohbet kaybolmaz).
  d.tikla();
  assert.equal(d.tumu().filter((n) => n.tagName === 'IFRAME').length, 1);
});

test('öznitelikler: data-dil, data-renk (açık renkte koyu yazı), data-konum, data-adres, data-baslik', () => {
  const d = dunya({ oznitelik: { 'data-dil': 'AR', 'data-renk': '#FDE68A', 'data-konum': 'sol', 'data-adres': 'https://asistan.ornek.dev/', 'data-baslik': 'Destek' } });
  d.kos();
  const b = d.balon();
  assert.match(b.style.cssText, /left:16px/);
  assert.match(b.style.cssText, /color:#111827/);
  assert.equal(b.getAttribute('aria-label'), 'Destek');
  d.tikla();
  assert.equal(d.cerceve().src, `https://asistan.ornek.dev/asistan/${ANAHTAR}?gomulu=1&dil=ar`);
  assert.equal(d.cerceve().title, 'Destek');
  assert.match(d.panel().style.cssText, /left:16px/);
});

test('geçersiz değerler: kötü dil yok sayılır, kötü renk varsayılan, RTL sayfada sol', () => {
  const d = dunya({ oznitelik: { 'data-dil': 'javascript:', 'data-renk': 'red;background:url(x)' }, lang: 'xx', dir: 'rtl' });
  d.kos();
  assert.match(d.balon().style.cssText, /background:#7c3aed/);
  assert.match(d.balon().style.cssText, /left:16px/);
  d.tikla();
  assert.equal(d.cerceve().src, `https://mehmetkuru.dev/asistan/${ANAHTAR}?gomulu=1`);
});

test('geçersiz ya da eksik anahtar: hiçbir şey eklenmez', () => {
  for (const a of [null, '', '../admin', 'ABCD2345EFGH678', 'abcd2345efgh6789x']) {
    const d = dunya({ oznitelik: { 'data-asistan': a } });
    d.kos();
    assert.equal(d.balon(), undefined, String(a));
    assert.equal(d.pencere.MKAsistan, undefined);
  }
});

test('el sıkışma: hazir → merhaba yalnız asistan kökenine; yanlış köken/kaynak yok sayılır', () => {
  const d = dunya();
  d.kos();
  d.tikla();
  const f = d.cerceve();
  d.ileti({ tur: 'mk-asistan', olay: 'hazir' }, f.contentWindow, 'https://kotu.example');
  d.ileti({ tur: 'mk-asistan', olay: 'hazir' }, { baska: true });
  assert.equal(d.gonderilen.length, 0);
  d.ileti({ tur: 'mk-asistan', olay: 'hazir' }, f.contentWindow);
  // vm bağlamındaki nesne başka bir realm'den: JSON üzerinden karşılaştır.
  assert.deepEqual(JSON.parse(JSON.stringify(d.gonderilen)), [{ veri: { tur: 'mk-asistan', olay: 'merhaba' }, hedefKoken: 'https://mehmetkuru.dev' }]);
});

test('yükseklik ve kapatma iletileri: sınırlar uygulanır; yanlış kökenden gelen kapatmaz', () => {
  const d = dunya();
  d.kos();
  d.tikla();
  const f = d.cerceve();
  assert.match(d.panel().style.cssText, /height:560px/);
  d.ileti({ tur: 'mk-asistan', olay: 'yukseklik', deger: 900 }, f.contentWindow, 'https://kotu.example');
  assert.match(d.panel().style.cssText, /height:560px/);
  d.ileti({ tur: 'mk-asistan', olay: 'yukseklik', deger: 430 }, f.contentWindow);
  assert.match(d.panel().style.cssText, /height:430px/);
  d.ileti({ tur: 'mk-asistan', olay: 'yukseklik', deger: 99999 }, f.contentWindow);
  assert.match(d.panel().style.cssText, /height:680px/);
  d.ileti({ tur: 'mk-asistan', olay: 'yukseklik', deger: 'x' }, f.contentWindow);
  assert.match(d.panel().style.cssText, /height:360px/);
  d.ileti({ tur: 'mk-asistan', olay: 'kapat' }, f.contentWindow, 'https://kotu.example');
  assert.match(d.panel().style.cssText, /display:block/);
  d.ileti('metin', f.contentWindow);
  d.ileti({ tur: 'mk-asistan', olay: 'kapat' }, f.contentWindow);
  assert.match(d.panel().style.cssText, /display:none/);
  assert.equal(d.balon().getAttribute('aria-expanded'), 'false');
});

test('Esc kapatır; programla aç/kapat/değiştir', () => {
  const d = dunya({ yukleniyor: true });
  d.kos();
  assert.equal(d.balon(), undefined, 'DOM hazır olmadan balon eklenmemeli');
  d.pencere.MKAsistan.ac();
  assert.match(d.panel().style.cssText, /display:block/);
  d.belge.dispatchEvent(Object.assign(new Olay('keydown'), { key: 'Escape' }));
  assert.match(d.panel().style.cssText, /display:none/);
  d.pencere.MKAsistan.degistir();
  assert.match(d.panel().style.cssText, /display:block/);
  d.pencere.MKAsistan.kapat();
  assert.match(d.panel().style.cssText, /display:none/);
  // DOMContentLoaded sonradan gelse de ikinci balon eklenmez.
  d.belge.dispatchEvent(new Olay('DOMContentLoaded'));
  assert.equal(d.tumu().filter((n) => n.tagName === 'BUTTON').length, 1);
});

test('mobil (375 px): panel tam ekran, balon gizli, sayfa kaydırması kilitli; kapatınca geri gelir', () => {
  const d = dunya({ genislik: 375 });
  d.kos();
  d.tikla();
  assert.match(d.panel().style.cssText, /inset:0/);
  assert.match(d.panel().style.cssText, /width:100%/);
  assert.match(d.balon().style.display, /none/);
  assert.equal(d.kok.style.overflow, 'hidden');
  d.ileti({ tur: 'mk-asistan', olay: 'kapat' }, d.cerceve().contentWindow);
  assert.equal(d.balon().style.display, 'flex');
  assert.equal(d.kok.style.overflow, '');
});
