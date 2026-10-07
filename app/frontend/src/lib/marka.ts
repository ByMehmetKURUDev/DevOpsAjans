import type { CSSProperties } from 'react';

import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 4L — Marka teması (white-label): herkese açık sayfaların hafif yardımcıları.
 *
 * Müşterinin herkese açık sayfaları (kartvizit, Google yorum, QR menü, randevu,
 * etkinlik, eğitim, AI asistan, saha servisi, bülten) marka bilgisini AYRI bir
 * istekle değil, zaten yaptıkları herkese açık isteğin yanıtındaki `marka`
 * alanından alıyor (`services/marka.py` `acik_marka`). Bu dosya yalnız tip +
 * küçük saf fonksiyonlar (panel API'si `markaPanel.ts`'te) — sayfa paketlerine
 * eklenen yük birkaç yüz bayt.
 *
 * Öncelik: sayfanın kendi açık teması (kartvizit `tema`, menü `tema_rengi`,
 * randevu/etkinlik/kurs/asistan `renk` varsayılandan farklıysa — `sayfa_ozel`)
 * o sayfanın kendi renkli öğelerinde öncelikli; marka yalnız boş kalanları
 * (düğmeler, logo, yazı tipi, köşeler) dolduruyor.
 *
 * CSS değişkenleri (`--marka-*`) sayfa kabına satır içi stil olarak yazılıyor
 * (CSP: `style-src 'unsafe-inline'` zaten açık); kartvizit sayfasında Pages
 * Function aynı değişkenleri sunucuda `<style>` olarak da yazıyor (ilk boyama).
 */

export type MarkaZemin = 'koyu' | 'acik';
export type MarkaKose = 'keskin' | 'yumusak' | 'yuvarlak';
export type MarkaYaziTipi = 'jakarta' | 'sistem_sans' | 'sistem_serif' | 'mono';

export interface MarkaLogo {
  url: string;
  genislik: number | null;
  yukseklik: number | null;
}

export interface MarkaTemasi {
  ad: string;
  ana: string;
  ana_yazi: string;
  vurgu: string;
  vurgu_yazi: string;
  zemin: MarkaZemin;
  kose: MarkaKose;
  yazi_tipi: MarkaYaziTipi;
  logo: MarkaLogo | null;
}

export interface AcikMarka {
  /** "mehmetkuru.dev ile hazırlandı" rozeti görünsün mü. */
  rozet: boolean;
  tema: MarkaTemasi | null;
  /** Sayfanın kendi açık teması var (o sayfanın renkli öğelerinde öncelikli). */
  sayfa_ozel: boolean;
}

/** Zemin → sayfa renkleri (arka uç `ZEMIN_RENKLERI` ve `functions/_ortak/marka.js` ile aynı). */
export const ZEMIN_RENKLERI: Record<MarkaZemin, { zemin: string; yuzey: string; metin: string; soluk: string; cerceve: string }> = {
  koyu: { zemin: '#0b0b12', yuzey: '#16161f', metin: '#f4f4f7', soluk: '#a1a1aa', cerceve: '#2a2a36' },
  acik: { zemin: '#f7f7f8', yuzey: '#ffffff', metin: '#111827', soluk: '#4b5563', cerceve: '#e5e7eb' },
};

/** Yalnız sitede zaten yüklü yazı tipleri ya da sistem yığınları (yeni font dosyası YOK). */
export const YAZI_YIGINLARI: Record<MarkaYaziTipi, string> = {
  jakarta: "'Plus Jakarta Sans', 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  sistem_sans: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', Arial, sans-serif",
  sistem_serif: "ui-serif, Georgia, Cambria, 'Times New Roman', Times, serif",
  mono: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
};

/** Köşe → [kart, düğme/girdi] yarıçapı. */
export const KOSE_DEGERLERI: Record<MarkaKose, [string, string]> = {
  keskin: ['4px', '4px'],
  yumusak: ['16px', '10px'],
  yuvarlak: ['28px', '18px'],
};

const RENK = /^#[0-9a-f]{6}$/i;

export const gecerliRenk = (r: unknown): r is string => typeof r === 'string' && RENK.test(r);

/** Yanıttaki marka teması (biçimi denetlenmiş) ya da null. */
export function markaTemasi(m: AcikMarka | null | undefined): MarkaTemasi | null {
  const t = m?.tema;
  if (!t || !gecerliRenk(t.ana) || !gecerliRenk(t.vurgu)) return null;
  return t;
}

/** Sayfanın rengi: sayfa kendi rengini seçtiyse o, değilse marka ana rengi, o da yoksa sayfanınki/yedek. */
export function etkinRenk(sayfaRengi: string | null | undefined, m: AcikMarka | null | undefined, yedek: string): string {
  const t = markaTemasi(m);
  if (t && !m?.sayfa_ozel) return t.ana;
  return gecerliRenk(sayfaRengi) ? sayfaRengi : yedek;
}

/** Yazı tipi yığını; Arapça/Hintçe sayfada o yazının kendi yazı tipi önde (site yalnız o dilde indiriyor). */
export function markaYaziTipi(t: MarkaTemasi, dil?: string): string {
  const yigin = YAZI_YIGINLARI[t.yazi_tipi] || YAZI_YIGINLARI.jakarta;
  if (dil === 'ar') return `'Noto Naskh Arabic', ${yigin}`;
  if (dil === 'hi') return `'Noto Sans Devanagari', ${yigin}`;
  return yigin;
}

/** `--marka-*` CSS değişkenleri (+ `anaRenk` verilirse ana renk o; yazı rengi ona göre seçiliyor). */
export function markaDegiskenleri(t: MarkaTemasi, dil?: string, anaRenk?: string): CSSProperties {
  const z = ZEMIN_RENKLERI[t.zemin] || ZEMIN_RENKLERI.acik;
  const [kart, dugme] = KOSE_DEGERLERI[t.kose] || KOSE_DEGERLERI.yumusak;
  const ana = anaRenk && gecerliRenk(anaRenk) ? anaRenk : t.ana;
  return {
    ['--marka-ana' as string]: ana,
    ['--marka-ana-yazi' as string]: ana === t.ana ? t.ana_yazi : yaziRengi(ana),
    ['--marka-vurgu' as string]: t.vurgu,
    ['--marka-vurgu-yazi' as string]: t.vurgu_yazi,
    ['--marka-zemin' as string]: z.zemin,
    ['--marka-yuzey' as string]: z.yuzey,
    ['--marka-metin' as string]: z.metin,
    ['--marka-soluk' as string]: z.soluk,
    ['--marka-cerceve' as string]: z.cerceve,
    ['--marka-kose' as string]: kart,
    ['--marka-kose-dugme' as string]: dugme,
    ['--marka-yazi-tipi' as string]: markaYaziTipi(t, dil),
  } as CSSProperties;
}

/**
 * Sayfa kabına yayılacak öznitelikler: `data-marka` (bkz. `components/marka/marka.css`) + değişkenler.
 * Marka yoksa boş nesne (sayfa bugünkü görünümüyle kalır).
 */
export interface MarkaKabugu {
  'data-marka'?: string;
  style?: CSSProperties;
}

export function markaKabugu(m: AcikMarka | null | undefined, dil?: string, anaRenk?: string): MarkaKabugu {
  const t = markaTemasi(m);
  if (!t) return {};
  return { 'data-marka': t.zemin, style: markaDegiskenleri(t, dil, anaRenk) };
}

/** WCAG göreli parlaklığından yazı rengi (arka uç `yazi_rengi` ile aynı kural). */
export function yaziRengi(hex: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return '#ffffff';
  const kanal = (i: number) => {
    const s = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * kanal(0) + 0.7152 * kanal(2) + 0.0722 * kanal(4);
  return 1.05 / (l + 0.05) >= (l + 0.05) / (0.0056 + 0.05) ? '#ffffff' : '#111111';
}

export const markaLogoAdresi = (logo: MarkaLogo | null | undefined): string | null =>
  logo && typeof logo.url === 'string' && logo.url.startsWith('/api/v1/marka/logo/') ? `${getAPIBaseURL()}${logo.url}` : null;
