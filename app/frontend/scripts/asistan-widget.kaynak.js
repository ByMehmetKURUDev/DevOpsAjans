/*! By Mehmet KURU Dev — AI asistan (Faz 5A). Gömme:
 * <script src="https://mehmetkuru.dev/asistan-widget.js" data-asistan="ANAHTAR" async></script>
 * İsteğe bağlı: data-dil="en" (yoksa sayfanın <html lang>'ı), data-renk="#7c3aed" (balon),
 * data-konum="sol" (sol alt; RTL sayfada varsayılan), data-baslik="Destek" (erişilebilir ad),
 * data-adres (farklı köken).
 * Bağımlılıksız; ziyaretçi balona tıklamadan hiçbir ağ isteği yapmaz. Tıklanınca asistan
 * sayfasını ?gomulu=1 ile iframe'e koyar. Çerçeveyle postMessage: `hazir` → `merhaba`
 * (üst sayfanın kökenini çerçeveye kanıtlar), `yukseklik` (panel boyu), `kapat`.
 * İletiler yalnız asistan kökeninden ve kendi çerçevesinden kabul edilir.
 * Programla: MKAsistan.ac(), MKAsistan.kapat(), MKAsistan.degistir().
 */
(function (w, d) {
  'use strict';
  if (w.MKAsistan) return;
  var s = d.currentScript;
  var oz = function (k) {
    return (s && s.getAttribute(k)) || '';
  };
  var anahtar = oz('data-asistan').trim().toLowerCase();
  if (!/^[a-z0-9]{16}$/.test(anahtar)) return;
  var taban = (oz('data-adres') || (s && s.src ? new URL(s.src, location.href).origin : location.origin)).replace(/\/$/, '');
  var koken = new URL(taban + '/').origin;
  var DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
  var dil = (oz('data-dil') || d.documentElement.lang || '').toLowerCase().slice(0, 2);
  if (DILLER.indexOf(dil) < 0) dil = '';
  var renk = /^#[0-9a-f]{6}$/i.test(oz('data-renk')) ? oz('data-renk') : '#7c3aed';
  var sol = oz('data-konum') ? oz('data-konum') === 'sol' : d.documentElement.dir === 'rtl';
  var yan = sol ? 'left' : 'right';
  var ad = oz('data-baslik') || 'AI';
  var acik = false;
  var boy = 560;
  var kok, balon, panel, f, tasma;

  // Balonun yazı rengi: arka plana göre okunur (WCAG göreli parlaklık).
  function yazi(h) {
    var r = [1, 3, 5].map(function (i) {
      var c = parseInt(h.substr(i, 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r[0] + 0.7152 * r[1] + 0.0722 * r[2] > 0.4 ? '#111827' : '#ffffff';
  }

  function dar() {
    return (w.innerWidth || 1024) < 480;
  }

  function yerlestir() {
    if (!panel) return;
    var p = panel.style;
    if (dar()) {
      p.cssText = 'position:fixed;inset:0;width:100%;height:100%;border-radius:0;';
    } else {
      var h = Math.max(360, Math.min(boy, (w.innerHeight || 800) - 112));
      p.cssText = 'position:fixed;bottom:88px;' + yan + ':16px;width:380px;max-width:calc(100vw - 32px);height:' + h + 'px;border-radius:18px;';
    }
    p.cssText += 'z-index:2147483001;overflow:hidden;background:#fff;box-shadow:0 18px 50px rgba(15,23,42,.28);display:' + (acik ? 'block' : 'none');
    balon.style.display = acik && dar() ? 'none' : 'flex';
    d.documentElement.style.overflow = acik && dar() ? 'hidden' : tasma;
  }

  function ac() {
    if (acik) return;
    if (!f) {
      panel = d.createElement('div');
      panel.setAttribute('data-mk-asistan-panel', '');
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-label', ad);
      f = d.createElement('iframe');
      f.src = taban + '/asistan/' + anahtar + '?gomulu=1' + (dil ? '&dil=' + dil : '');
      f.title = ad;
      f.style.cssText = 'display:block;width:100%;height:100%;border:0;background:transparent;color-scheme:normal';
      panel.appendChild(f);
      kok.appendChild(panel);
    }
    tasma = d.documentElement.style.overflow;
    acik = true;
    balon.setAttribute('aria-expanded', 'true');
    yerlestir();
    try {
      f.focus();
    } catch (_) {
      /* odak verilemedi */
    }
  }

  function kapat() {
    if (!acik) return;
    acik = false;
    balon.setAttribute('aria-expanded', 'false');
    yerlestir();
    balon.focus();
  }

  function kur() {
    if (kok) return;
    kok = d.createElement('div');
    kok.setAttribute('data-mk-asistan', anahtar);
    balon = d.createElement('button');
    balon.type = 'button';
    balon.setAttribute('aria-label', ad);
    balon.setAttribute('aria-expanded', 'false');
    balon.style.cssText =
      'position:fixed;bottom:16px;' + yan + ':16px;z-index:2147483000;width:56px;height:56px;border:0;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(15,23,42,.3);background:' +
      renk +
      ';color:' +
      yazi(renk);
    // innerHTML yok: Trusted Types kullanan sitelerde de çalışsın.
    var NS = 'http://www.w3.org/2000/svg';
    var svg = d.createElementNS(NS, 'svg');
    var yol = d.createElementNS(NS, 'path');
    var nit = { width: 26, height: 26, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' };
    for (var k in nit) svg.setAttribute(k, nit[k]);
    yol.setAttribute('d', 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z');
    svg.appendChild(yol);
    balon.appendChild(svg);
    balon.addEventListener('click', function () {
      acik ? kapat() : ac();
    });
    kok.appendChild(balon);
    d.body.appendChild(kok);
  }

  w.addEventListener('message', function (e) {
    if (!f || e.origin !== koken || e.source !== f.contentWindow) return;
    var v = e.data;
    if (!v || typeof v !== 'object' || v.tur !== 'mk-asistan') return;
    if (v.olay === 'hazir') {
      f.contentWindow.postMessage({ tur: 'mk-asistan', olay: 'merhaba' }, koken);
    } else if (v.olay === 'yukseklik') {
      boy = Math.max(360, Math.min(680, Number(v.deger) || 0));
      yerlestir();
    } else if (v.olay === 'kapat') {
      kapat();
    }
  });
  d.addEventListener('keydown', function (e) {
    if (acik && e.key === 'Escape') kapat();
  });
  w.addEventListener('resize', yerlestir);

  w.MKAsistan = {
    ac: function () {
      kur();
      ac();
    },
    kapat: kapat,
    degistir: function () {
      kur();
      acik ? kapat() : ac();
    },
  };
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', kur);
  else kur();
})(window, document);
