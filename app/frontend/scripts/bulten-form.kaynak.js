/*! By Mehmet KURU Dev — bülten abonelik formu (çift onay). Gömme:
 * <script src="https://mehmetkuru.dev/bulten-form.js" async></script>
 * <div data-mk-bulten="ANAHTAR"></div>   (isteğe bağlı: data-mk-dil="en")
 * Bağımlılıksız; shadow DOM içinde (sitenin CSS'i karışmaz, yazı tipi/renk siteden
 * miras). Kurallar ve 7 dildeki metinler sunucuda: /api/v1/bulten/form/<anahtar>.
 * İzin kutusu zorunlu ve varsayılan işaretsiz; gönderimden sonra onay e-postası gider,
 * abonelik ancak e-postadaki bağlantıyla onaylanınca başlar.
 */
(function (w, d) {
  'use strict';
  var s = d.currentScript;
  var taban = ((s && s.getAttribute('data-adres')) || (s && s.src ? new URL(s.src, location.href).origin : location.origin)).replace(/\/$/, '');
  var CSS =
    ':host{display:block}form{display:grid;gap:10px;max-width:520px;font:inherit;color:inherit}' +
    'h3{margin:0 0 2px;font-size:1.2em}p.d{margin:0 0 4px;opacity:.85;line-height:1.5}label{display:grid;gap:4px;font-size:.9em;font-weight:600}' +
    'input{font:inherit;font-weight:400;color:inherit;background:rgba(127,127,127,.08);border:1px solid rgba(127,127,127,.45);border-radius:10px;padding:10px 12px;width:100%;box-sizing:border-box}' +
    'input:focus{outline:2px solid #8b5cf6;outline-offset:1px}' +
    '.k{display:flex;gap:8px;align-items:flex-start;font-weight:400;font-size:.85em;line-height:1.45}.k input{width:auto;margin:3px 0 0}' +
    '.a{margin:0;font-size:.8em;opacity:.75;line-height:1.45}.a a{color:inherit}' +
    'button{font:inherit;font-weight:700;color:#fff;background:linear-gradient(90deg,#7c3aed,#db2777);border:0;border-radius:10px;padding:11px 20px;cursor:pointer;justify-self:start}' +
    'button:disabled{opacity:.6;cursor:wait}.h{margin:0;font-size:.9em;color:#e11d48;min-height:1.2em}' +
    '.t{margin:0;padding:14px;border-radius:10px;background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.4)}' +
    '.b{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);opacity:0}i{font-weight:400;opacity:.7}';
  var OTO = { ad: 'name', eposta: 'email' };

  function el(ad, oz, cocuklar) {
    var e = d.createElement(ad);
    for (var k in oz || {}) {
      if (k === 'text') e.textContent = oz[k];
      else e.setAttribute(k, oz[k]);
    }
    (cocuklar || []).forEach(function (c) {
      if (c) e.appendChild(typeof c === 'string' ? d.createTextNode(c) : c);
    });
    return e;
  }

  function json(r) {
    return r.json().then(function (j) {
      if (!r.ok) throw j;
      return j;
    });
  }

  function ciz(kok, t, uc) {
    var m = t.metinler;
    var f = el('form', { novalidate: '', dir: t.yon, lang: t.dil, 'data-mk-bulten-form': '' });
    if (t.baslik) f.appendChild(el('h3', { text: t.baslik }));
    if (t.aciklama) f.appendChild(el('p', { class: 'd', text: t.aciklama }));
    t.alanlar.forEach(function (a) {
      var oz = { name: a.ad, maxlength: a.en_cok, autocomplete: OTO[a.ad] || 'off', type: a.ad === 'eposta' ? 'email' : 'text' };
      if (a.zorunlu) oz.required = '';
      f.appendChild(el('label', null, [el('span', null, [a.etiket, a.zorunlu ? ' *' : el('i', { text: ' (' + m.istege_bagli + ')' })]), el('input', oz)]));
    });
    var bal = el('input', { name: t.bal_kupu, tabindex: '-1', autocomplete: 'off', 'aria-hidden': 'true', class: 'b' });
    var kur = t.kurumsal && el('input', { type: 'checkbox', name: 'kurumsal' });
    var izin = el('input', { type: 'checkbox', name: 'izin', required: '' });
    var ileti = el('p', { class: 'h', role: 'alert', 'aria-live': 'polite' });
    var btn = el('button', { type: 'submit', text: m.gonder });
    var ay = null;
    if (t.aydinlatma && t.aydinlatma.baglanti) {
      ay = el('p', { class: 'a' }, [el('a', { href: t.aydinlatma.baglanti, target: '_blank', rel: 'noopener', text: t.aydinlatma.metin })]);
    }
    [bal, kur && el('label', { class: 'k' }, [kur, el('span', null, [t.kurumsal, el('i', { text: ' (' + m.istege_bagli + ')' })])]),
      el('label', { class: 'k' }, [izin, el('span', null, [t.izin.metin, ' *'])]), ileti, btn, ay].forEach(function (x) {
      if (x) f.appendChild(x);
    });
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      ileti.textContent = '';
      if (!f.checkValidity()) {
        ileti.textContent = izin.checked ? m.hata.alan_gerekli : m.hata.izin_gerekli;
        return f.reportValidity && f.reportValidity();
      }
      var v = { jeton: t.jeton, dil: t.dil, izin: !!izin.checked, kurumsal: !!(kur && kur.checked) };
      v[t.bal_kupu] = bal.value;
      t.alanlar.forEach(function (a) {
        v[a.ad] = f.elements.namedItem(a.ad).value;
      });
      btn.disabled = true;
      btn.textContent = m.gonderiliyor;
      // text/plain: tarayıcı ön kontrol (OPTIONS) yapmasın; gövde yine JSON.
      fetch(uc, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=UTF-8' }, body: JSON.stringify(v) })
        .then(json)
        .then(function (j) {
          kok.replaceChild(el('p', { class: 't', role: 'status', dir: t.yon, 'data-mk-tesekkur': '', text: j.tesekkur }), f);
        })
        .catch(function (j) {
          var kod = j && j.detail && j.detail.kod;
          ileti.textContent = m.hata[kod] || m.hata.genel;
          btn.disabled = false;
          btn.textContent = m.gonder;
        });
    });
    kok.appendChild(f);
  }

  function kur(kutu) {
    if (kutu.__mk) return;
    kutu.__mk = 1;
    var dil = (kutu.getAttribute('data-mk-dil') || d.documentElement.lang || navigator.language || 'tr').slice(0, 2);
    var kok = kutu.attachShadow ? kutu.attachShadow({ mode: 'open' }) : kutu;
    kok.appendChild(el('style', { text: CSS }));
    var uc = taban + '/api/v1/bulten/form/' + encodeURIComponent(kutu.getAttribute('data-mk-bulten') || '');
    fetch(uc + '?dil=' + encodeURIComponent(dil))
      .then(json)
      .then(function (t) {
        ciz(kok, t, uc);
      })
      .catch(function () {
        kok.appendChild(el('p', { class: 'h', role: 'alert', text: 'Form yüklenemedi. / The form could not be loaded.' }));
      });
  }

  function tara() {
    var l = d.querySelectorAll('[data-mk-bulten]');
    for (var i = 0; i < l.length; i++) kur(l[i]);
  }

  w.MKBulten = { tara: tara };
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', tara);
  else tara();
})(window, document);
