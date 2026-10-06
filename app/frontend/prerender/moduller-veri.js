/**
 * Modül vitrini (Faz 4V) — yol ve veri yardımcıları.
 *
 * Yapı (hangi modül vitrinde, ikonu, kategorisi, paketi, ilgili modüller,
 * sektör paketleri) arka uçtaki modül kaydından türetiliyor ve depoya
 * `prerender/modul-vitrini-veri.json` olarak yazılıyor
 * (`app/backend/scripts/modul_vitrini_tohum.py`; test kayıtla aynı olduğunu
 * doğruluyor). Bu dosya JSON'u kendisi içe aktarmıyor — Node betikleri onu
 * `fs` ile, Vite istemcisi ve prerender `import` ile okuyor; yardımcılar veriyi
 * parametre olarak alıyor.
 *
 * Fiyat yapıda yok: fiyatlandırma v5'ten (`GET /api/v1/modul-vitrini` →
 * `fiyatlar`), ölçek başına başlangıç aylık tutarı. Derlemede canlı uçtan
 * okunuyor (olmazsa fiyatsız), sayfa açılışta tazeliyor.
 *
 * Bağımlılığı olmayan düz JS: prerender, vite.config, llms.txt betiği ve
 * istemci okuyabiliyor.
 */

export const MODUL_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const VARSAYILAN_DIL = 'tr';

/** `/moduller` (tr) ya da `/en/moduller`. */
export function modullerYolu(dil) {
  return dil && dil !== VARSAYILAN_DIL ? `/${dil}/moduller` : '/moduller';
}

export function modulYolu(dil, slug) {
  return `${modullerYolu(dil)}/${slug}`;
}

export function paketYolu(dil, slug) {
  return `${modullerYolu(dil)}/paket/${slug}`;
}

/**
 * Bir yol modül vitrini mi? `{ dil, tur: 'liste' | 'modul' | 'paket', slug }` ya da null.
 * `/moduller`, `/moduller/x`, `/moduller/paket/x`, dil önekli biçimleri (sondaki `/` önemsiz).
 */
export function modulYolunuCoz(yol) {
  const temiz = String(yol ?? '').split(/[?#]/)[0].replace(/\/+$/, '');
  const e = temiz.match(/^(?:\/([a-z]{2}))?\/moduller(?:\/paket\/([^/]+)|\/([^/]+))?$/);
  if (!e) return null;
  const dil = e[1] ?? VARSAYILAN_DIL;
  if (!MODUL_DILLERI.includes(dil) || (e[1] && dil === VARSAYILAN_DIL)) return null;
  if (e[2]) return { dil, tur: 'paket', slug: decodeURIComponent(e[2]) };
  if (e[3]) return { dil, tur: 'modul', slug: decodeURIComponent(e[3]) };
  return { dil, tur: 'liste', slug: null };
}

export function modulBul(veri, slug) {
  return (veri?.moduller ?? []).find((m) => m.slug === slug) ?? null;
}

export function modulAnahtarla(veri, anahtar) {
  return (veri?.moduller ?? []).find((m) => m.anahtar === anahtar) ?? null;
}

export function paketBul(veri, slug) {
  return (veri?.paketler ?? []).find((p) => p.slug === slug) ?? null;
}

/** Prerender edilecek bütün ayrıntı yolları (7 dil × modüller + paketler), sonda `/` ile. */
export function modulDetayYollari(veri) {
  const yollar = [];
  for (const dil of MODUL_DILLERI) {
    for (const m of veri?.moduller ?? []) yollar.push(`${modulYolu(dil, m.slug)}/`);
    for (const p of veri?.paketler ?? []) yollar.push(`${paketYolu(dil, p.slug)}/`);
  }
  return yollar;
}

/** `ALFA` → `Alfa` (fiyat uçtan gelmediyse paket adının yedeği). */
export function olcekKisaAdi(kod) {
  const s = String(kod ?? '');
  return s ? s.charAt(0) + s.slice(1).toLowerCase() : '';
}

/** Ölçeğin seçili dildeki adı: uçtan gelen çeviri → Türkçe ad → kısa ad. */
export function olcekAdi(fiyatlar, kod, dil) {
  const ad = fiyatlar?.[kod]?.ad;
  return (ad && (ad[dil] || ad.tr)) || olcekKisaAdi(kod);
}

/** Hizmetler sayfasındaki biçim: `$1,140`. */
export function paraBicimi(tutar) {
  const n = Number(tutar);
  if (!Number.isFinite(n)) return '';
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

/**
 * Modülün fiyat bilgisi: pakete dahilse `{ paket, tutar|null, paraBirimi }`, değilse null
 * (ayrı açılan modül → "teklif alın").
 */
export function modulFiyati(modul, fiyatlar) {
  if (!modul?.paket) return null;
  const f = fiyatlar?.[modul.paket];
  const tutar = f && Number.isFinite(Number(f.baslangic_aylik)) && Number(f.baslangic_aylik) > 0 ? Number(f.baslangic_aylik) : null;
  return { paket: modul.paket, tutar, paraBirimi: f?.para_birimi || 'USD' };
}
