/**
 * Yasal sayfaların veri sorumlusu bilgilerini derlemede okur (yalnız Node:
 * prerender betiği). Faz 3Y.
 *
 * Sıra (kaynaklar-yukle.js ile aynı düzen):
 *   1. Canlı API: `https://mehmetkuru.dev/api/v1/entities/site_settings`
 *      (herkese açık okuma; 5 sn zaman aşımı). Panelde girilen unvan, adres,
 *      KEP… böylece bir sonraki yayında prerender HTML'ine giriyor.
 *   2. Erişilemezse (uyuyan sunucu, ağ yok): boş harita → `yasal-veri.js`
 *      varsayılanları. Derleme hiçbir koşulda düşmez.
 *
 * `YASAL_KAYNAGI=yok` canlı isteği atlar; başka bir değer canlı adresin
 * yerine geçer (ör. yerel arka uç). `SITE_API_BASE_URL` tanımlıysa önce o.
 * Tarayıcı tarafında sayfa aynı değerleri site ayarları önbelleğinden okuyor.
 */
import { YASAL_OKUNAN_ANAHTARLAR } from './yasal-veri.js';

const CANLI_ADRES = 'https://mehmetkuru.dev/api/v1/entities/site_settings?limit=2000';
const ZAMAN_ASIMI_MS = 5000;

function adres() {
  const ayar = (process.env.YASAL_KAYNAGI || '').trim();
  if (ayar) return ayar;
  const taban = (process.env.SITE_API_BASE_URL || process.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '');
  return taban ? `${taban}/api/v1/entities/site_settings?limit=2000` : CANLI_ADRES;
}

let onbellek = null;

/** `{ ayar_anahtari: değer }` — yalnız yasal anahtarlar ve iletişim e-postası. */
export async function yasalAyarlariniYukle() {
  if (onbellek) return onbellek;
  if ((process.env.YASAL_KAYNAGI || '').trim() === 'yok') {
    onbellek = {};
    return onbellek;
  }
  const kesici = new AbortController();
  const zaman = setTimeout(() => kesici.abort(), ZAMAN_ASIMI_MS);
  try {
    const yanit = await fetch(adres(), { headers: { accept: 'application/json' }, signal: kesici.signal });
    if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
    const govde = await yanit.json();
    const ogeler = Array.isArray(govde?.items) ? govde.items : [];
    const harita = {};
    for (const o of ogeler) {
      if (o?.setting_key && YASAL_OKUNAN_ANAHTARLAR.includes(o.setting_key)) {
        harita[o.setting_key] = String(o.setting_value ?? '');
      }
    }
    console.log(`[yasal] Canlı ayarlar okundu: ${Object.keys(harita).length} anahtar.`);
    onbellek = harita;
  } catch (hata) {
    console.warn(`[yasal] Canlı ayarlar okunamadı (${hata?.message ?? hata}) — varsayılanlar kullanılıyor.`);
    onbellek = {};
  } finally {
    clearTimeout(zaman);
  }
  return onbellek;
}
