import { useTranslation } from 'react-i18next';

import { oranRengi, tarihBicimle, yuzdeBicimle, type GunCubugu } from '@/lib/siteBakim';

/**
 * Son 90 günün erişilebilirlik çubukları (gün başına %).
 *
 * Grafik kütüphanesi yok: 90 ince `div`. Çubuklar `flex-1` olduğu için
 * 360 piksellik telefonda da taşmadan sığıyor (çubuk ~3 px). Ölçümü
 * olmayan gün gri. Her çubuğun `title`ı ve bütün grafiğin `aria-label`ı
 * var; ekran okuyucu ortalamayı okuyor, 90 ayrı öğe değil.
 */
export default function UptimeGrafigi({
  gunler,
  ortalama,
  yukseklik = 'h-8',
  testId,
}: {
  gunler: GunCubugu[];
  ortalama?: number | null;
  yukseklik?: string;
  testId?: string;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  if (!gunler.length) return null;

  return (
    <div data-testid={testId}>
      <div
        className={`flex ${yukseklik} items-end gap-[2px]`}
        role="img"
        aria-label={t('siteBakim.uptime.grafikAria', {
          sayi: gunler.length,
          oran: yuzdeBicimle(ortalama ?? null, dil),
        })}
        dir="ltr"
      >
        {gunler.map((g) => (
          <span
            key={g.gun}
            title={`${tarihBicimle(g.gun, dil)} · ${
              g.oran === null ? t('siteBakim.uptime.veriYok') : yuzdeBicimle(g.oran, dil)
            }`}
            className={`block h-full min-w-0 flex-1 rounded-[1px] ${oranRengi(g.oran)} ${
              g.oran === null ? 'opacity-60' : ''
            }`}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground" dir="ltr">
        <span>{t('siteBakim.uptime.gunOnce', { sayi: gunler.length })}</span>
        <span>{t('siteBakim.uptime.bugun')}</span>
      </div>
    </div>
  );
}
