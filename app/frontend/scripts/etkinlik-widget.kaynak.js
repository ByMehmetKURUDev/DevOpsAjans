/*! By Mehmet KURU Dev — etkinlik ve bilet (Faz 6E). Gömme:
 * <div data-mk-etkinlik="ETKINLIK"></div>                     satır içi kayıt formu
 * <button type="button" data-mk-etkinlik-ac="ETKINLIK">Kayıt ol</button>   açılır pencere
 * <div data-mk-etkinlikler="LISTE"></div>                     hesabın etkinlik listesi
 * <script src="https://mehmetkuru.dev/etkinlik-widget.js" async></script>
 * İsteğe bağlı: data-mk-dil="en" (dil), script'te data-adres (farklı köken).
 * Bağımlılıksız; etkinlik sayfasını ?gomulu=1 ile iframe'e koyar, yüksekliği
 * çerçevenin postMessage'ıyla ayarlar. Kayıt bitince kapsayıcı öğede
 * `mk-etkinlik-tamam` olayı (detail.kod) tetiklenir. SPA siteler için
 * yeni öğeler eklendikten sonra `MKEtkinlik.tara()` çağrılabilir.
 */
(function (w, d) {
  'use strict';
  if (w.MKEtkinlik) return w.MKEtkinlik.tara();
  var s = d.currentScript;
  var taban = ((s && s.getAttribute('data-adres')) || (s && s.src ? new URL(s.src, location.href).origin : location.origin)).replace(/\/$/, '');
  var koken = new URL(taban + '/').origin;
  var YOL = /^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/;
  var cerceveler = [];

  function adres(onek, yol, dil) {
    yol = String(yol || '').trim().toLowerCase().replace(/^\/+|\/+$/g, '');
    if (!YOL.test(yol)) return '';
    dil = String(dil || '').toLowerCase();
    return taban + '/' + onek + '/' + yol + '?gomulu=1' + (/^[a-z]{2}$/.test(dil) ? '&dil=' + dil : '');
  }

  function cerceve(src, sahip, yukseklik) {
    var f = d.createElement('iframe');
    f.src = src;
    f.title = sahip.getAttribute('data-mk-baslik') || 'Etkinlik';
    f.loading = 'lazy';
    f.setAttribute('allow', 'clipboard-write');
    f.style.cssText = 'display:block;width:100%;border:0;min-height:' + yukseklik + 'px;height:' + yukseklik + 'px;background:transparent;color-scheme:normal';
    cerceveler.push({ f: f, sahip: sahip });
    return f;
  }

  function pencere(src, sahip) {
    var onceki = d.activeElement;
    var tasma = d.documentElement.style.overflow;
    var ortu = d.createElement('div');
    ortu.setAttribute('role', 'dialog');
    ortu.setAttribute('aria-modal', 'true');
    ortu.setAttribute('data-mk-etkinlik-pencere', '');
    ortu.style.cssText = 'position:fixed;inset:0;z-index:2147483646;background:rgba(15,23,42,.55);display:flex;align-items:center;justify-content:center;padding:12px';
    var kutu = d.createElement('div');
    kutu.style.cssText = 'position:relative;width:100%;max-width:760px;max-height:100%;overflow:auto;background:#fff;border-radius:16px;box-shadow:0 20px 50px rgba(0,0,0,.3);-webkit-overflow-scrolling:touch';
    var kapat = d.createElement('button');
    kapat.type = 'button';
    kapat.setAttribute('aria-label', '×');
    kapat.textContent = '×';
    kapat.style.cssText = 'position:sticky;top:6px;float:right;margin:6px 6px 0 0;z-index:1;width:36px;height:36px;border:0;border-radius:50%;background:#f4f4f5;color:#18181b;font:600 22px/1 system-ui,sans-serif;cursor:pointer';
    function bitir() {
      d.removeEventListener('keydown', tus);
      cerceveler = cerceveler.filter(function (c) {
        return !kutu.contains(c.f);
      });
      if (ortu.parentNode) ortu.parentNode.removeChild(ortu);
      d.documentElement.style.overflow = tasma;
      if (onceki && onceki.focus) onceki.focus();
    }
    function tus(e) {
      if (e.key === 'Escape') bitir();
    }
    kapat.addEventListener('click', bitir);
    ortu.addEventListener('click', function (e) {
      if (e.target === ortu) bitir();
    });
    d.addEventListener('keydown', tus);
    kutu.appendChild(kapat);
    kutu.appendChild(cerceve(src, sahip, 560));
    ortu.appendChild(kutu);
    d.body.appendChild(ortu);
    d.documentElement.style.overflow = 'hidden';
    kapat.focus();
  }

  function satirIci(secici, onek) {
    var liste = d.querySelectorAll('[' + secici + ']:not([data-mk-hazir])');
    for (var i = 0; i < liste.length; i++) {
      var el = liste[i];
      el.setAttribute('data-mk-hazir', '');
      var src = adres(onek, el.getAttribute(secici), el.getAttribute('data-mk-dil'));
      if (src) el.appendChild(cerceve(src, el, 640));
    }
  }

  function tara() {
    satirIci('data-mk-etkinlik', 'etkinlik');
    satirIci('data-mk-etkinlikler', 'etkinlikler');
    var dugme = d.querySelectorAll('[data-mk-etkinlik-ac]:not([data-mk-hazir])');
    for (var i = 0; i < dugme.length; i++) {
      dugme[i].setAttribute('data-mk-hazir', '');
      dugme[i].addEventListener('click', function (e) {
        var hedef = e.currentTarget;
        var a = adres('etkinlik', hedef.getAttribute('data-mk-etkinlik-ac'), hedef.getAttribute('data-mk-dil'));
        if (!a) return;
        e.preventDefault();
        pencere(a, hedef);
      });
    }
  }

  w.addEventListener('message', function (e) {
    if (e.origin !== koken || !e.data || typeof e.data !== 'object') return;
    for (var i = 0; i < cerceveler.length; i++) {
      var c = cerceveler[i];
      if (c.f.contentWindow !== e.source) continue;
      if (e.data.tur === 'mk-etkinlik') {
        var y = Math.max(240, Math.min(4000, Number(e.data.yukseklik) || 0));
        c.f.style.height = y + 'px';
        c.f.style.minHeight = '0';
      } else if (e.data.tur === 'mk-etkinlik-tamam') {
        var olay;
        try {
          olay = new CustomEvent('mk-etkinlik-tamam', { bubbles: true, detail: { kod: e.data.kod || null } });
        } catch (_) {
          olay = d.createEvent('CustomEvent');
          olay.initCustomEvent('mk-etkinlik-tamam', true, false, { kod: e.data.kod || null });
        }
        c.sahip.dispatchEvent(olay);
      }
    }
  });

  w.MKEtkinlik = { tara: tara };
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', tara);
  else tara();
})(window, document);
