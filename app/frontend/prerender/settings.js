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
