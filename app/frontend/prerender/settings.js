/**
 * Yönetim panelindeki ayarları derleme sırasında okur.
 *
 * Prerender build sırasında çalışıyor ve backend'e erişemiyordu; bu yüzden
 * üretilen HTML her zaman koddaki yedek değerleri taşıyordu. Panelden hero
 * başlığını veya SEO metnini değiştirdiğinizde Google'ın gördüğü sayfa
 * değişmiyordu.
 *
 * Artık `SITE_API_BASE_URL` (veya `VITE_API_BASE_URL`) tanımlıysa ayarlar
 * build sırasında düz HTTP ile çekiliyor ve prerender'a besleniyor. Adres
 * tanımlı değilse ya da istek başarısız olursa yalnızca koddaki
 * varsayılanlar kullanılır — build hiçbir koşulda düşmez.
 */

const ENDPOINT = '/api/v1/entities/site_settings';
const TIMEOUT_MS = 8000;

function getBaseUrl() {
  const raw =
    process.env.SITE_API_BASE_URL ||
    process.env.VITE_API_BASE_URL ||
    '';
  return raw.trim().replace(/\/+$/, '');
}

let cached = null;

/** Ayar haritasını döndürür: { setting_key: setting_value }. */
export async function loadPanelSettings() {
  if (cached) return cached;

  const base = getBaseUrl();
  if (!base) {
    console.log(
      '[prerender] SITE_API_BASE_URL tanımlı değil — sayfa metinleri koddaki varsayılanlardan üretiliyor.',
    );
    cached = {};
    return cached;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${base}${ENDPOINT}?limit=500`, {
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const map = {};

    for (const item of items) {
      if (item?.setting_key) {
        map[item.setting_key] = String(item.setting_value ?? '');
      }
    }

    cached = map;
    console.log(`[prerender] Panel ayarları okundu: ${Object.keys(map).length} kayıt.`);
    return cached;
  } catch (error) {
    console.warn(
      `[prerender] Panel ayarları okunamadı (${error.message}) — koddaki varsayılanlar kullanılıyor.`,
    );
    cached = {};
    return cached;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Dil bazlı ayar değerini çözer.
 * `hero_title__ar` varsa onu, yoksa `hero_title`ı, o da yoksa yedeği döndürür.
 */
export function resolvePanelValue(settings, key, lang, fallback) {
  const localized = settings[`${key}__${lang}`];
  if (localized && localized.trim()) return localized.trim();

  const base = settings[key];
  if (base && base.trim()) return base.trim();

  return fallback;
}

/**
 * Derlemede geçerli site görünümü (`site_gorunum`): 'modern', 'nebula' ya da 'klasik'.
 *
 * Tanınmayan/boş değer klasik sayılır — src/lib/gorunum.ts ile aynı kural.
 */
export function siteGorunumu(settings = {}) {
  const deger = String(settings?.site_gorunum ?? '').trim();
  return deger === 'modern' || deger === 'nebula' ? deger : 'klasik';
}

/**
 * Prerender HTML'inin `<html>` etiketine `data-gorunum` yazar.
 *
 * Yalnız Modern ve Nebula'da yazılıyor: Klasik varsayılan ve HTML'in eski
 * hâlinden tek bayt farkı olmasın. Modern/Nebula iken ilk kez gelen ziyaretçi
 * (önbelleği yok) böylece ayar isteği dönmeden doğru görünümü görüyor; kritik
 * CSS'i gömen `scripts/css-gomule.mjs` de o görünümün kurallarını ilk boyamaya
 * katıyor.
 *
 * Faz 8N — Nebula'nın stili ayrı dosya (yalnız Nebula'da iner): `nebulaStili`
 * (derlenmiş dosyanın adresi) verilirse `</head>`'den önce bağlantısı da yazılır;
 * css-gomule onu da işleyip kritik kurallarını gömer, kalanını arkadan yükletir.
 */
export function htmlGorunumYaz(html, gorunum, { nebulaStili } = {}) {
  if (gorunum !== 'modern' && gorunum !== 'nebula') return html;
  let sonuc = html.replace(/<html\b([^>]*)>/i, (_tam, oznitelikler) => {
    const temiz = oznitelikler.replace(/\s+data-gorunum=("[^"]*"|'[^']*'|\S+)/gi, '');
    return `<html${temiz} data-gorunum="${gorunum}">`;
  });
  if (gorunum === 'nebula' && nebulaStili && !sonuc.includes(`href="${nebulaStili}"`)) {
    sonuc = sonuc.replace(/<\/head>/i, `  <link rel="stylesheet" href="${nebulaStili}">\n  </head>`);
  }
  return sonuc;
}

/**
 * Faz 8N — Nebula stil dosyasının adresini `<meta name="gorunum-nebula-css">`
 * olarak yazar. index.html'deki satır içi görünüm betiği (`?gorunum=nebula` ya
 * da önbellekteki ayar Nebula iken) dosyayı ilk boyamadan önce buradan ekliyor;
 * adres derlemeye göre değiştiği (içerik özeti) için betiğe gömülemiyor — gömülse
 * betiğin CSP özeti her derlemede değişirdi. Etiket `<meta charset>`ın hemen
 * ardına, yani betikten önceye yazılır.
 */
export function nebulaAdresiYaz(html, nebulaStili) {
  // Satır içi betik de bu adı (seçici olarak) taşıyor: yalnız gerçek <meta> etiketine bak.
  if (!nebulaStili || /<meta\s+name="gorunum-nebula-css"/i.test(html)) return html;
  const etiket = `<meta name="gorunum-nebula-css" content="${nebulaStili}" />`;
  if (/<meta\s+charset[^>]*>/i.test(html)) return html.replace(/(<meta\s+charset[^>]*>)/i, `$1\n    ${etiket}`);
  return html.replace(/<head>/i, `<head>\n    ${etiket}`);
}
