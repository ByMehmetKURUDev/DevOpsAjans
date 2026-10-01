/**
 * Kaynaklar — derleme verisini (7 dil, "tam" biçim) sayfa verisine çevirir.
 *
 * Girdi: arka ucun `GET /api/v1/kaynaklar?bicim=tam` yanıtı ya da depodaki
 * tohum dosyası (`app/backend/data/kaynaklar_tohum.json`) — ikisi aynı
 * biçimde: metin alanları `{ tr, en, ... }` sözlüğü.
 *
 * Çıktı: arka ucun dile çözülmüş liste/ayrıntı yanıtlarıyla BİREBİR aynı
 * şekil (`services/kaynaklar.py`: `ozet_satiri`, `ayrinti`). Prerender
 * HTML'i bu çıktıyla çiziliyor ve aynı veri sayfaya gömülüyor; istemci ilk
 * çizimi ağ beklemeden aynı veriyle yapıyor, sonra API'den tazeliyor.
 * Dil kuralı ve sıralama iki tarafta aynı olmalı:
 *   - metin alanı seçili dilde doluysa o, değilse Türkçesi;
 *   - öne çıkanlar önce, sonra `sira`, sonra slug.
 *
 * Bağımlılığı olmayan düz JS (prerender paketi ve Node betikleri okuyor).
 */

export const KAYNAK_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const VARSAYILAN_DIL = 'tr';
const SLUG_DESENI = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ILGILI_SAYISI = 3;

function doluMu(deger) {
  if (Array.isArray(deger)) return deger.length > 0;
  return typeof deger === 'string' && deger.trim() !== '';
}

/** `{tr, en, ...}` sözlüğünden seçili dili, yoksa Türkçeyi döndürür. */
function dilde(deger, dil, bos = '') {
  if (deger && typeof deger === 'object' && !Array.isArray(deger)) {
    if (doluMu(deger[dil])) return deger[dil];
    return doluMu(deger.tr) ? deger.tr : bos;
  }
  return doluMu(deger) ? deger : bos;
}

/** Yalnız http/https bağlantı; değilse null (derlemede javascript: vb. basılmasın). */
export function guvenliBaglanti(adres) {
  if (typeof adres !== 'string') return null;
  const temiz = adres.trim();
  if (!temiz || /\s/.test(temiz)) return null;
  try {
    const u = new URL(temiz);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    return u.hostname && !u.username && !u.password ? temiz : null;
  } catch {
    return null;
  }
}

function siralama(a, b) {
  if (Boolean(a.one_cikan) !== Boolean(b.one_cikan)) return a.one_cikan ? -1 : 1;
  const sa = Number.isFinite(a.sira) ? a.sira : 100;
  const sb = Number.isFinite(b.sira) ? b.sira : 100;
  if (sa !== sb) return sa - sb;
  return a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0;
}

/** Yayındaki, geçerli kayıtlar — sıralı. */
export function yayindakiler(veri) {
  const kayitlar = Array.isArray(veri?.kaynaklar) ? veri.kaynaklar : [];
  const gorulen = new Set();
  return kayitlar
    .filter((k) => {
      if (!k || typeof k !== 'object' || k.yayinda === false) return false;
      if (typeof k.slug !== 'string' || !SLUG_DESENI.test(k.slug) || gorulen.has(k.slug)) return false;
      if (!guvenliBaglanti(k.baglanti) || !doluMu(dilde(k.baslik, VARSAYILAN_DIL))) return false;
      gorulen.add(k.slug);
      return true;
    })
    .slice()
    .sort(siralama);
}

function kategoriAdi(veri, anahtar, dil) {
  const kat = (veri?.kategoriler ?? []).find((c) => c?.anahtar === anahtar);
  return (kat && dilde(kat.ad, dil)) || anahtar;
}

function ozetKaydi(k, dil) {
  const youtube = guvenliBaglanti(k.youtube_short);
  return {
    slug: k.slug,
    kategori: k.kategori,
    baslik: dilde(k.baslik, dil),
    ozet: dilde(k.ozet, dil),
    etiketler: Array.isArray(k.etiketler) ? k.etiketler.map(String) : [],
    ucretsiz: k.ucretsiz !== false,
    acik_kaynak: Boolean(k.acik_kaynak),
    youtube_short: youtube,
    one_cikan: Boolean(k.one_cikan),
    sira: Number.isFinite(k.sira) ? k.sira : 100,
    baglanti_turu: k.baglanti_turu || 'site',
  };
}

/** Liste sayfası verisi — `GET /api/v1/kaynaklar?dil=` ile aynı şekil. */
export function listeVerisi(veri, dil) {
  const kayitlar = yayindakiler(veri);
  const sayilar = {};
  for (const k of kayitlar) sayilar[k.kategori] = (sayilar[k.kategori] ?? 0) + 1;
  return {
    dil,
    kaynaklar: kayitlar.map((k) => ozetKaydi(k, dil)),
    kategoriler: (veri?.kategoriler ?? [])
      .filter((c) => c && typeof c.anahtar === 'string')
      .map((c) => ({ anahtar: c.anahtar, ad: kategoriAdi(veri, c.anahtar, dil), sayi: sayilar[c.anahtar] ?? 0 })),
    toplam: kayitlar.length,
  };
}

/** Ayrıntı sayfası verisi — `GET /api/v1/kaynaklar/{slug}?dil=` ile aynı şekil; yoksa null. */
export function detayVerisi(veri, slug, dil) {
  const kayitlar = yayindakiler(veri);
  const k = kayitlar.find((x) => x.slug === slug);
  if (!k) return null;
  const adimlar = dilde(k.adimlar, dil, []);
  return {
    dil,
    kaynak: {
      ...ozetKaydi(k, dil),
      aciklama: dilde(k.aciklama, dil),
      adimlar: Array.isArray(adimlar) ? adimlar.map(String) : [],
      baglanti: guvenliBaglanti(k.baglanti),
      lisans: k.lisans || null,
      kategori_adi: kategoriAdi(veri, k.kategori, dil),
      dogrulama_tarihi: k.dogrulama_tarihi || null,
      updated_at: k.updated_at || null,
    },
    ilgili: kayitlar
      .filter((x) => x.kategori === k.kategori && x.slug !== k.slug)
      .slice(0, ILGILI_SAYISI)
      .map((x) => ozetKaydi(x, dil)),
  };
}

/** Kaynaklar sayfasının yolu: Türkçe ön eksiz, diğer diller `/en/...`. */
export function kaynakYolu(dil, slug) {
  const kok = dil && dil !== VARSAYILAN_DIL ? `/${dil}/kaynaklar` : '/kaynaklar';
  return slug ? `${kok}/${slug}` : kok;
}

/**
 * Bir yol Kaynaklar sayfası mı? `{ dil, slug }` (liste için slug null) ya da null.
 * `/kaynaklar`, `/kaynaklar/x`, `/en/kaynaklar`, `/en/kaynaklar/x` (sondaki `/` önemsiz).
 */
export function kaynakYolunuCoz(yol) {
  const temiz = String(yol ?? '').split(/[?#]/)[0].replace(/\/+$/, '');
  const e = temiz.match(/^(?:\/([a-z]{2}))?\/kaynaklar(?:\/([^/]+))?$/);
  if (!e) return null;
  const dil = e[1] ?? VARSAYILAN_DIL;
  if (!KAYNAK_DILLERI.includes(dil) || (e[1] && dil === VARSAYILAN_DIL)) return null;
  return { dil, slug: e[2] ? decodeURIComponent(e[2]) : null };
}

/** Prerender edilecek bütün ayrıntı yolları (7 dil × yayındaki kaynaklar), sonda `/` ile. */
export function kaynakDetayYollari(veri) {
  const yollar = [];
  for (const k of yayindakiler(veri)) {
    for (const dil of KAYNAK_DILLERI) yollar.push(`${kaynakYolu(dil, k.slug)}/`);
  }
  return yollar;
}
