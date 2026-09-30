/*!
 * By Mehmet KURU Dev — site geri bildirim düğmesi
 *
 * Müşterinin sitesine tek satırla gömülüyor:
 *   <script src="https://mehmetkuru.dev/widget.js" data-jeton="..." defer></script>
 *
 * Sayfanın sağ kenarında ajans logolu küçük bir düğme çıkıyor. Müşteri
 * "şurası şöyle olsun" yazıyor, istek onun hesabına destek talebi
 * olarak düşüyor ve siteye bakan ekip üyesine atanıyor.
 *
 * Tasarım kararları
 * -----------------
 * - Her şey shadow DOM içinde. Müşterinin sitesinin CSS'i bize,
 *   bizimki ona karışmasın diye: gömülen bir parçanın ev sahibi
 *   sayfanın görünümünü bozma hakkı yok.
 * - Hiçbir küresel değişken, hiçbir dış bağımlılık, tek istek.
 * - alert/confirm kullanılmıyor; tarayıcı diyaloğu sayfayı kilitler.
 * - Müşterinin e-postası localStorage'da hatırlanıyor (yalnızca
 *   kolaylık; try/catch içinde, olmazsa alan boş açılıyor).
 */
(function () {
  'use strict';

  var betik = document.currentScript;
  if (!betik) {
    var hepsi = document.querySelectorAll('script[data-jeton]');
    betik = hepsi[hepsi.length - 1];
  }
  if (!betik) return;

  var jeton = betik.getAttribute('data-jeton') || '';
  if (!jeton) return;

  var kok = betik.getAttribute('data-adres') || new URL(betik.src, location.href).origin;
  var ucBasi = kok.replace(/\/$/, '') + '/api/v1/geri-bildirim/' + encodeURIComponent(jeton);
  var HATIRA = 'mkdev-geri-bildirim-eposta';

  function hatirla(anahtar, deger) {
    try {
      if (deger === undefined) return localStorage.getItem(anahtar) || '';
      localStorage.setItem(anahtar, deger);
    } catch (e) {
      /* gizli sekme, kapalı depolama: önemli değil */
    }
    return '';
  }

  var BICIM = [
    ':host{all:initial}',
    '*,*::before,*::after{box-sizing:border-box}',
    '.sarmal{position:fixed;right:0;bottom:22%;z-index:2147483000;',
    'font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}',
    '.dugme{display:flex;align-items:center;gap:8px;border:0;cursor:pointer;',
    'background:#111827;color:#fff;padding:10px 14px 10px 11px;',
    'border-radius:12px 0 0 12px;box-shadow:0 6px 24px rgba(0,0,0,.28);',
    'font-size:13px;font-weight:600;letter-spacing:.2px;transition:transform .18s ease}',
    '.dugme:hover{transform:translateX(-3px)}',
    '.dugme img{width:20px;height:20px;border-radius:5px;display:block}',
    '.panel{position:fixed;right:16px;bottom:16px;width:340px;max-width:calc(100vw - 32px);',
    'max-height:calc(100vh - 32px);overflow:auto;background:#fff;color:#111827;',
    'border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.32);',
    'z-index:2147483000;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}',
    '.ust{display:flex;align-items:center;gap:10px;padding:14px 14px 10px}',
    '.ust img{width:26px;height:26px;border-radius:7px;display:block}',
    '.ust b{font-size:14px;line-height:1.2}',
    '.ust small{display:block;font-size:11px;color:#6b7280;font-weight:400}',
    '.kapat{margin-left:auto;border:0;background:transparent;cursor:pointer;',
    'font-size:20px;line-height:1;color:#9ca3af;padding:2px 4px}',
    '.govde{padding:0 14px 14px;display:grid;gap:9px}',
    'label{font-size:11px;font-weight:600;color:#4b5563;display:block;margin-bottom:3px}',
    'input,textarea{width:100%;border:1px solid #d1d5db;border-radius:9px;padding:9px 10px;',
    'font-size:13px;font-family:inherit;color:#111827;background:#fff}',
    'input:focus,textarea:focus{outline:2px solid #34d399;outline-offset:-1px;border-color:#34d399}',
    'textarea{min-height:92px;resize:vertical}',
    '.gonder{border:0;border-radius:10px;background:#111827;color:#fff;padding:11px;',
    'font-size:13px;font-weight:600;cursor:pointer}',
    '.gonder[disabled]{opacity:.55;cursor:progress}',
    '.not{font-size:11px;color:#6b7280;line-height:1.45;margin:0}',
    '.uyari{font-size:12px;border-radius:9px;padding:9px 10px;margin:0}',
    '.uyari.iyi{background:#ecfdf5;color:#065f46}',
    '.uyari.kotu{background:#fef2f2;color:#991b1b}',
    '@media (prefers-color-scheme:dark){',
    '.panel{background:#0f172a;color:#e5e7eb}',
    '.ust small,.not{color:#94a3b8}',
    'input,textarea{background:#1e293b;border-color:#334155;color:#e5e7eb}',
    '.gonder,.dugme{background:#34d399;color:#062e22}',
    '.uyari.iyi{background:#052e22;color:#6ee7b7}',
    '.uyari.kotu{background:#3f1717;color:#fca5a5}}'
  ].join('');

  function el(ad, ozellikler, metin) {
    var d = document.createElement(ad);
    if (ozellikler) for (var k in ozellikler) d.setAttribute(k, ozellikler[k]);
    if (metin != null) d.textContent = metin;
    return d;
  }

  function kur(bilgi) {
    var yuva = document.createElement('div');
    yuva.setAttribute('data-mkdev-geri-bildirim', '');
    var golge = yuva.attachShadow ? yuva.attachShadow({ mode: 'open' }) : null;
    if (!golge) return; // shadow DOM yoksa müşterinin sitesine hiç dokunmuyoruz
    var stil = document.createElement('style');
    stil.textContent = BICIM;
    golge.appendChild(stil);
    document.body.appendChild(yuva);

    var sarmal = el('div', { class: 'sarmal' });
    var dugme = el('button', { class: 'dugme', type: 'button', 'aria-haspopup': 'dialog' });
    var logo = el('img', { src: bilgi.logo, alt: '', loading: 'lazy' });
    dugme.appendChild(logo);
    dugme.appendChild(el('span', null, 'Geri bildirim'));
    sarmal.appendChild(dugme);
    golge.appendChild(sarmal);

    var panel = null;

    function kapat() {
      if (panel) { panel.remove(); panel = null; }
      sarmal.style.display = '';
      dugme.focus();
    }

    function ac() {
      if (panel) return;
      sarmal.style.display = 'none';
      panel = el('div', { class: 'panel', role: 'dialog', 'aria-label': 'Geri bildirim' });

      var ust = el('div', { class: 'ust' });
      ust.appendChild(el('img', { src: bilgi.logo, alt: '' }));
      var baslik = el('div');
      baslik.appendChild(el('b', null, 'Bu sayfada ne değişsin?'));
      baslik.appendChild(el('small', null, bilgi.ajans + ' · ' + bilgi.ad));
      ust.appendChild(baslik);
      var kapatDugmesi = el('button', { class: 'kapat', type: 'button', 'aria-label': 'Kapat' }, '×');
      kapatDugmesi.addEventListener('click', kapat);
      ust.appendChild(kapatDugmesi);
      panel.appendChild(ust);

      var govde = el('form', { class: 'govde' });

      var a1 = el('div');
      a1.appendChild(el('label', { for: 'mk-eposta' }, 'Üyelik e-postanız'));
      var eposta = el('input', {
        id: 'mk-eposta', type: 'email', autocomplete: 'email',
        placeholder: 'ornek@firma.com'
      });
      eposta.value = hatirla(HATIRA);
      a1.appendChild(eposta);
      govde.appendChild(a1);

      var a2 = el('div');
      a2.appendChild(el('label', { for: 'mk-ad' }, 'Adınız (isteğe bağlı)'));
      a2.appendChild(el('input', { id: 'mk-ad', type: 'text', autocomplete: 'name' }));
      govde.appendChild(a2);

      var a3 = el('div');
      a3.appendChild(el('label', { for: 'mk-mesaj' }, 'İsteğiniz'));
      a3.appendChild(el('textarea', {
        id: 'mk-mesaj',
        placeholder: 'Örn: Ana sayfadaki telefon numarası eski, 0541 ... olacak.'
      }));
      govde.appendChild(a3);

      var uyari = el('p', { class: 'uyari iyi' });
      uyari.style.display = 'none';
      govde.appendChild(uyari);

      var gonder = el('button', { class: 'gonder', type: 'submit' }, 'Gönder');
      govde.appendChild(gonder);
      govde.appendChild(el('p', { class: 'not' },
        'İsteğiniz ' + bilgi.ajans + ' panelinde hesabınıza düşer, size dönülür.'));

      panel.appendChild(govde);
      golge.appendChild(panel);
      setTimeout(function () { (eposta.value ? govde.querySelector('#mk-mesaj') : eposta).focus(); }, 40);

      govde.addEventListener('submit', function (olay) {
        olay.preventDefault();
        var mesaj = (govde.querySelector('#mk-mesaj').value || '').trim();
        if (mesaj.length < 3) {
          uyari.className = 'uyari kotu';
          uyari.textContent = 'Lütfen ne istediğinizi yazın.';
          uyari.style.display = '';
          return;
        }
        uyari.style.display = 'none';
        gonder.disabled = true;
        gonder.textContent = 'Gönderiliyor…';

        var adres = (govde.querySelector('#mk-eposta').value || '').trim();
        if (adres) hatirla(HATIRA, adres);

        fetch(ucBasi, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            eposta: adres,
            ad: (govde.querySelector('#mk-ad').value || '').trim(),
            mesaj: mesaj,
            sayfa: location.href.slice(0, 500)
          })
        })
          .then(function (y) {
            return y.json().catch(function () { return {}; }).then(function (v) {
              if (!y.ok) throw new Error(v.detail || 'Gönderilemedi');
              return v;
            });
          })
          .then(function (v) {
            govde.innerHTML = '';
            var iyi = el('p', { class: 'uyari iyi' },
              'Aldık. Talep numaranız #' + (v.talep_no || '—') + '. Ekibimiz bakıp size dönecek.');
            govde.appendChild(iyi);
            if (adres && v.uyelik_eslesti === false) {
              govde.appendChild(el('p', { class: 'not' },
                'Not: bu e-posta hesabınızla eşleşmedi; istek yine de site sahibinin hesabına düştü.'));
            }
            var tamam = el('button', { class: 'gonder', type: 'button' }, 'Kapat');
            tamam.addEventListener('click', kapat);
            govde.appendChild(tamam);
          })
          .catch(function (hata) {
            gonder.disabled = false;
            gonder.textContent = 'Gönder';
            uyari.className = 'uyari kotu';
            uyari.textContent = (hata && hata.message) || 'Gönderilemedi, birazdan tekrar deneyin.';
            uyari.style.display = '';
          });
      });

      panel.addEventListener('keydown', function (olay) {
        if (olay.key === 'Escape') kapat();
      });
    }

    dugme.addEventListener('click', ac);
  }

  function basla() {
    fetch(ucBasi, { method: 'GET' })
      .then(function (y) { return y.ok ? y.json() : null; })
      .then(function (bilgi) {
        // Jeton geçersiz ya da düğme kapatılmışsa hiçbir şey çizmiyoruz.
        if (bilgi && bilgi.ad) kur(bilgi);
      })
      .catch(function () { /* müşterinin sitesinde hata gürültüsü yapmıyoruz */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', basla);
  } else {
    basla();
  }
})();
