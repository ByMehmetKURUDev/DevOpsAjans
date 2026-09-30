import { ThumbsUp, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Yol haritası › "Topluluktan" (Faz 2B, isteğe bağlı): müşterilerin önerip
 * oyladığı ve "planlandı" durumuna alınan geliştirmeler — yalnız başlık +
 * oy sayısı. Yönetici Öneri kutusu ayarından açıyor; kapalıysa sayfa bu
 * bileşeni hiç yüklemiyor.
 */
export default function TopluluktanBolumu({ oneriler }: { oneriler: { baslik: string; oy_sayisi: number }[] }) {
  const { t } = useTranslation();
  if (!oneriler.length) return null;
  return (
    <section
      className="cam-kart cam-mor mt-10 rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-8"
      aria-labelledby="topluluk-baslik"
      data-testid="topluluktan"
    >
      <h2 id="topluluk-baslik" className="flex items-center gap-2 text-2xl font-bold">
        <Users className="h-6 w-6 text-purple-300" aria-hidden="true" /> {t('duyurular.topluluk.baslik')}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">{t('duyurular.topluluk.aciklama')}</p>
      <ul className="mt-5 grid gap-2 md:grid-cols-2">
        {oneriler.map((o, i) => (
          <li key={`${i}-${o.baslik}`} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-purple-500/15 px-2 py-0.5 text-xs text-purple-200">
              <ThumbsUp className="h-3 w-3" aria-hidden="true" />
              <span className="sr-only">{t('duyurular.topluluk.oy', { sayi: o.oy_sayisi })}</span>
              <span aria-hidden="true">{o.oy_sayisi}</span>
            </span>
            <span className="min-w-0 break-words text-sm">{o.baslik}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
