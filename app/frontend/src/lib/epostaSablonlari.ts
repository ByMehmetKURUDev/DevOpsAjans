import type { TFunction } from 'i18next';

import type { Blok } from '@/lib/epostaPazarlama';

/**
 * Faz 5M — hazır e-posta şablonları (sade, mobil uyumlu; marka rengi ve logo hesap
 * ayarından). Metinler seçili panel dilinde (ek paket `epostaPazarlama.sablon.*`);
 * şablon seçilince bloklar düzenleyiciye kopyalanır, kullanıcı içeriği değiştirir.
 */

export type SablonAdi = 'bos' | 'duyuru' | 'bulten' | 'kampanya' | 'etkinlik' | 'hosgeldin';
export const SABLONLAR: SablonAdi[] = ['bos', 'duyuru', 'bulten', 'kampanya', 'etkinlik', 'hosgeldin'];

export function sablonBloklari(ad: SablonAdi, t: TFunction): Blok[] {
  // Çeviri metinleri i18next enterpolasyonuyla çakışmasın diye kişiselleştirme
  // [[ad|yedek]] olarak yazılır; düzenleyiciye sunucunun anladığı {{ad|yedek}} gider.
  const s = (k: string) => String(t(`epostaPazarlama.sablon.${ad}.${k}`)).replace(/\[\[(\w+)\|([^\]]*)\]\]/g, '{{$1|$2}}');
  switch (ad) {
    case 'bos':
      return [{ tur: 'logo' }, { tur: 'metin', metin: s('metin') }];
    case 'duyuru':
      return [
        { tur: 'logo' },
        { tur: 'baslik', metin: s('baslik'), seviye: 1 },
        { tur: 'metin', metin: s('metin') },
        { tur: 'dugme', metin: s('dugme'), url: 'https://mehmetkuru.dev' },
      ];
    case 'bulten':
      return [
        { tur: 'logo' },
        { tur: 'baslik', metin: s('baslik'), seviye: 1 },
        { tur: 'metin', metin: s('giris') },
        { tur: 'ayirici' },
        {
          tur: 'iki_sutun',
          sol: [
            { tur: 'baslik', metin: s('yazi1'), seviye: 2 },
            { tur: 'metin', metin: s('ozet1') },
            { tur: 'dugme', metin: s('devam'), url: 'https://mehmetkuru.dev/blog' },
          ],
          sag: [
            { tur: 'baslik', metin: s('yazi2'), seviye: 2 },
            { tur: 'metin', metin: s('ozet2') },
            { tur: 'dugme', metin: s('devam'), url: 'https://mehmetkuru.dev/kaynaklar' },
          ],
        },
        { tur: 'ayirici' },
        { tur: 'metin', metin: s('kapanis') },
      ];
    case 'kampanya':
      return [
        { tur: 'logo' },
        { tur: 'baslik', metin: s('baslik'), seviye: 1, hiza: 'orta' },
        { tur: 'metin', metin: s('metin'), hiza: 'orta' },
        { tur: 'metin', metin: s('kod'), hiza: 'orta' },
        { tur: 'dugme', metin: s('dugme'), url: 'https://mehmetkuru.dev', hiza: 'orta' },
        { tur: 'metin', metin: s('kosul'), hiza: 'orta' },
      ];
    case 'etkinlik':
      return [
        { tur: 'logo' },
        { tur: 'baslik', metin: s('baslik'), seviye: 1 },
        { tur: 'metin', metin: s('metin') },
        { tur: 'metin', metin: s('ayrinti') },
        { tur: 'dugme', metin: s('dugme'), url: 'https://mehmetkuru.dev/contact' },
      ];
    case 'hosgeldin':
    default:
      return [
        { tur: 'logo' },
        { tur: 'baslik', metin: s('baslik'), seviye: 1 },
        { tur: 'metin', metin: s('metin') },
        { tur: 'dugme', metin: s('dugme'), url: 'https://mehmetkuru.dev' },
        { tur: 'metin', metin: s('imza') },
      ];
  }
}

/** İpucu metinlerindeki örnek yer tutucular (i18next'in yorumlamaması için değer olarak verilir). */
export function yerTutucuOrnekleri(t: TFunction): { a: string; f: string; e: string; v: string } {
  const yedek = /\[\[ad\|([^\]]*)\]\]/.exec(String(t('epostaPazarlama.sablon.bos.metin')))?.[1] || '…';
  return { a: '{{ad}}', f: '{{firma}}', e: '{{eposta}}', v: `{{ad|${yedek}}}` };
}

/** Yeni blok için varsayılan içerik. */
export function yeniBlok(tur: Blok['tur'], t: TFunction): Blok {
  switch (tur) {
    case 'logo':
      return { tur: 'logo' };
    case 'baslik':
      return { tur: 'baslik', metin: t('epostaPazarlama.blok.ornekBaslik'), seviye: 1 };
    case 'metin':
      return { tur: 'metin', metin: t('epostaPazarlama.blok.ornekMetin') };
    case 'gorsel':
      return { tur: 'gorsel', url: '', alt: '', genislik: 100 };
    case 'dugme':
      return { tur: 'dugme', metin: t('epostaPazarlama.blok.ornekDugme'), url: 'https://' };
    case 'ayirici':
      return { tur: 'ayirici' };
    case 'bosluk':
      return { tur: 'bosluk', yukseklik: 24 };
    case 'iki_sutun':
    default:
      return {
        tur: 'iki_sutun',
        sol: [{ tur: 'metin', metin: t('epostaPazarlama.blok.solSutun') }],
        sag: [{ tur: 'metin', metin: t('epostaPazarlama.blok.sagSutun') }],
      };
  }
}
