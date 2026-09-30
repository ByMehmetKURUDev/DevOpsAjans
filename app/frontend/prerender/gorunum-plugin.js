/**
 * Vite eklentisi: site ayarı Modern ise derlenen HTML'e `data-gorunum` yazar.
 *
 * `transformIndexHtml` index.html'i prerender'dan ÖNCE dönüştürüyor;
 * prerender eklentisi bütün sayfaları bu şablondan ürettiği için öznitelik
 * her prerender sayfasına (7 dil, blog) kendiliğinden geçiyor.
 *
 * Ayar derleme sırasında `SITE_API_BASE_URL` üzerinden okunuyor
 * (prerender/settings.js). Adres yoksa ya da istek düşerse site Klasik
 * sayılır ve HTML değişmez — derleme hiçbir koşulda düşmez.
 */
import { htmlGorunumYaz, loadPanelSettings, siteGorunumu } from './settings.js';

/**
 * `SITE_API_BASE_URL` derleme ortamında yoksa (Cloudflare'de tanımlı olmayabilir)
 * görünüm ayarı canlı siteden okunur; 5 sn içinde gelmezse Klasik sayılır.
 */
const CANLI_AYAR_ADRESI =
  process.env.SITE_GORUNUM_KAYNAGI || 'https://mehmetkuru.dev/api/v1/entities/site_settings/all?limit=500';

async function ayarlariYukleYedekli() {
  const ayarlar = (await loadPanelSettings()) || {};
  if (ayarlar.site_gorunum) return ayarlar;
  if (process.env.SITE_GORUNUM_KAYNAGI === 'yok') return ayarlar;
  const kesici = new AbortController();
  const zaman = setTimeout(() => kesici.abort(), 5000);
  try {
    const yanit = await fetch(CANLI_AYAR_ADRESI, { headers: { accept: 'application/json' }, signal: kesici.signal });
    if (!yanit.ok) return ayarlar;
    const govde = await yanit.json();
    const satir = (govde?.items || []).find((o) => o?.setting_key === 'site_gorunum');
    return satir ? { ...ayarlar, site_gorunum: satir.setting_value } : ayarlar;
  } catch {
    return ayarlar;
  } finally {
    clearTimeout(zaman);
  }
}

export function gorunumOzniteligi({ ayarlariYukle = ayarlariYukleYedekli } = {}) {
  return {
    name: 'mk-gorunum-ozniteligi',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      async handler(html) {
        const gorunum = siteGorunumu(await ayarlariYukle());
        if (gorunum === 'modern') console.log('[prerender] Site görünümü Modern: <html data-gorunum="modern"> yazılıyor.');
        return htmlGorunumYaz(html, gorunum);
      },
    },
  };
}
