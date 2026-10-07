/**
 * Vite eklentisi: site ayarı Modern/Nebula ise derlenen HTML'e `data-gorunum` yazar.
 *
 * `transformIndexHtml` index.html'i prerender'dan ÖNCE dönüştürüyor;
 * prerender eklentisi bütün sayfaları bu şablondan ürettiği için öznitelik
 * her prerender sayfasına (7 dil, blog) kendiliğinden geçiyor.
 *
 * Ayar derleme sırasında `SITE_API_BASE_URL` üzerinden okunuyor
 * (prerender/settings.js). Adres yoksa ya da istek düşerse site Klasik
 * sayılır ve HTML değişmez — derleme hiçbir koşulda düşmez.
 */
import { htmlGorunumYaz, loadPanelSettings, nebulaAdresiYaz, siteGorunumu } from './settings.js';

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

/**
 * Faz 8N — derlenmiş Nebula stil dosyasının adresi (`src/lib/gorunum.ts`'teki
 * `gorunum-nebula.css?url` içe aktarımının ürettiği `assets/gorunum-nebula-<özet>.css`).
 * Paket bilgisi yoksa (birim testi, geliştirme) `null`: HTML'e hiçbir şey eklenmez.
 */
export function nebulaStilAdresiBul(bundle, taban = '/') {
  if (!bundle) return null;
  const dosya = Object.values(bundle).find(
    (o) => o?.type === 'asset' && /(^|\/)gorunum-nebula[-.][^/]*\.css$/.test(o.fileName || ''),
  );
  return dosya ? `${taban.replace(/\/?$/, '/')}${dosya.fileName}` : null;
}

export function gorunumOzniteligi({ ayarlariYukle = ayarlariYukleYedekli } = {}) {
  let taban = '/';
  return {
    name: 'mk-gorunum-ozniteligi',
    apply: 'build',
    configResolved(config) {
      taban = config.base || '/';
    },
    transformIndexHtml: {
      order: 'post',
      async handler(html, ctx) {
        const gorunum = siteGorunumu(await ayarlariYukle());
        const nebulaStili = nebulaStilAdresiBul(ctx?.bundle, taban);
        if (gorunum !== 'klasik') console.log(`[prerender] Site görünümü ${gorunum}: <html data-gorunum="${gorunum}"> yazılıyor.`);
        return htmlGorunumYaz(nebulaAdresiYaz(html, nebulaStili), gorunum, { nebulaStili });
      },
    },
  };
}
