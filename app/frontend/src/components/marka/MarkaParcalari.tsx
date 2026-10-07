import './marka.css';

import { markaLogoAdresi, markaTemasi, type AcikMarka } from '@/lib/marka';

/**
 * Faz 4L — herkese açık müşteri sayfalarının ortak marka parçaları.
 *
 * `MarkaRozeti`: sayfanın altındaki küçük "mehmetkuru.dev ile hazırlandı" bağlantısı.
 * Metin sayfanın KENDİ dilinde (ziyaretçinin site dilinden bağımsız; herkese açık
 * sayfalar i18next ek paketini yüklemeden çizilebilsin diye 7 dil burada — Pages
 * Function'lardaki `EK` sözlükleriyle aynı yaklaşım; metinler `randevuSayfa.hazirlayan`
 * ile aynı). Marka modülü açık ve yönetici "rozeti gizle" dediyse (`marka.rozet === false`)
 * hiç çizilmiyor.
 *
 * `MarkaBasligi`: kendi logosu olmayan sayfalarda üstte marka logosu (+ adı).
 */

const ROZET_METNI: Record<string, string> = {
  tr: 'mehmetkuru.dev ile hazırlandı',
  en: 'Made with mehmetkuru.dev',
  de: 'Erstellt mit mehmetkuru.dev',
  ru: 'Сделано на mehmetkuru.dev',
  zh: '由 mehmetkuru.dev 提供',
  hi: 'mehmetkuru.dev के साथ बनाया गया',
  ar: 'صُنع بواسطة mehmetkuru.dev',
};

export const rozetMetni = (dil: string | null | undefined) => ROZET_METNI[dil || 'tr'] || ROZET_METNI.tr;

/** Rozet görünsün mü: marka bilgisi yoksa (eski yanıt / ajans sayfası) görünür. */
export const rozetGorunur = (m: AcikMarka | null | undefined) => m?.rozet !== false;

export function MarkaRozeti({ marka, dil, className = '' }: { marka: AcikMarka | null | undefined; dil?: string | null; className?: string }) {
  if (!rozetGorunur(marka)) return null;
  return (
    <p className={`marka-rozet ${className}`} data-testid="marka-rozet">
      <a href="https://mehmetkuru.dev/" target="_blank" rel="noopener">
        {rozetMetni(dil)}
      </a>
    </p>
  );
}

export function MarkaBasligi({ marka, className = '' }: { marka: AcikMarka | null | undefined; className?: string }) {
  const t = markaTemasi(marka);
  const logo = t ? markaLogoAdresi(t.logo) : null;
  if (!t || (!logo && !t.ad)) return null;
  return (
    <div className={`marka-baslik ${className}`} data-testid="marka-basligi">
      {logo ? (
        <img
          src={logo}
          alt={t.ad || ''}
          width={t.logo?.genislik ?? undefined}
          height={t.logo?.yukseklik ?? undefined}
          decoding="async"
          data-testid="marka-logo"
        />
      ) : null}
      {t.ad && !logo ? <span className="text-sm font-semibold">{t.ad}</span> : null}
    </div>
  );
}
