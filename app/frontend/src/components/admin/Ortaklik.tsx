import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Banknote, HandCoins, Inbox, Loader2, ReceiptText, Settings2, TicketPercent, Users } from 'lucide-react';

import { AltDugme } from '@/components/ortaklik/ortak';
import { yonetimOzeti } from '@/lib/ortaklik';

const Ortaklar = lazy(() => import('@/components/admin/ortaklik/Ortaklar'));
const Basvurular = lazy(() => import('@/components/admin/ortaklik/Basvurular'));
const Komisyonlar = lazy(() => import('@/components/admin/ortaklik/Komisyonlar'));
const Talepler = lazy(() => import('@/components/admin/ortaklik/Talepler'));
const IndirimKodlari = lazy(() => import('@/components/admin/ortaklik/IndirimKodlari'));
const Ayarlar = lazy(() => import('@/components/admin/ortaklik/Ayarlar'));

type Alt = 'ortaklar' | 'basvurular' | 'komisyonlar' | 'talepler' | 'kodlar' | 'ayarlar';
const ALTLAR: { anahtar: Alt; ikon: typeof Users }[] = [
  { anahtar: 'ortaklar', ikon: Users },
  { anahtar: 'basvurular', ikon: Inbox },
  { anahtar: 'komisyonlar', ikon: ReceiptText },
  { anahtar: 'talepler', ikon: Banknote },
  { anahtar: 'kodlar', ikon: TicketPercent },
  { anahtar: 'ayarlar', ikon: Settings2 },
];

function ilkAlt(): Alt {
  try {
    const a = new URLSearchParams(window.location.search).get('alt') as Alt | null;
    return a && ALTLAR.some((x) => x.anahtar === a) ? a : 'ortaklar';
  } catch {
    return 'ortaklar';
  }
}

/**
 * Faz 5K — Yönetici › Satış › Ortaklık programı (menüde TEK sekme; bölümler burada alt gezinme):
 * ortaklar, başvurular, komisyon defteri, ödeme talepleri ("ödendi" + dekont + ortağa e-posta),
 * indirim kodları ve program ayarları. PARA AKTARIMI YOK: ödemeyi bankadan yapıp burada işaretleyin.
 * Metinler `ortaklik` + `indirimKodu` ek paketlerinde.
 */
export default function Ortaklik() {
  const { t } = useTranslation();
  const [alt, setAlt] = useState<Alt>(ilkAlt);
  const [ozet, setOzet] = useState<{ bekleyen_basvuru: number; bekleyen_talep: number; supheli_komisyon: number } | null>(null);

  const ozetiYukle = useCallback(() => {
    yonetimOzeti()
      .then(setOzet)
      .catch(() => setOzet(null));
  }, []);

  useEffect(() => {
    ozetiYukle();
  }, [ozetiYukle, alt]);

  const rozet = (sayi?: number) =>
    sayi ? (
      <span className="rounded-full bg-amber-500/80 px-1.5 text-[10px] font-semibold text-zinc-950" data-ortaklik-rozet>
        {sayi}
      </span>
    ) : null;

  return (
    <section aria-labelledby="ortaklik-yonetim-baslik" data-testid="ortaklik-yonetim">
      <div className="mb-5">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="ortaklik-yonetim-baslik">
          <HandCoins className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('ortaklik.yonetim.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('ortaklik.yonetim.aciklama')}</p>
      </div>
      <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('ortaklik.yonetim.baslik')}>
        {ALTLAR.map(({ anahtar, ikon: Ikon }) => (
          <AltDugme key={anahtar} secili={alt === anahtar} onClick={() => setAlt(anahtar)} testid={anahtar}>
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`ortaklik.yonetim.alt.${anahtar}`)}
            {anahtar === 'basvurular' && rozet(ozet?.bekleyen_basvuru)}
            {anahtar === 'talepler' && rozet(ozet?.bekleyen_talep)}
            {anahtar === 'komisyonlar' && rozet(ozet?.supheli_komisyon)}
          </AltDugme>
        ))}
      </div>
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        }
      >
        {alt === 'ortaklar' ? (
          <Ortaklar />
        ) : alt === 'basvurular' ? (
          <Basvurular onDegisti={ozetiYukle} />
        ) : alt === 'komisyonlar' ? (
          <Komisyonlar onDegisti={ozetiYukle} />
        ) : alt === 'talepler' ? (
          <Talepler onDegisti={ozetiYukle} />
        ) : alt === 'kodlar' ? (
          <IndirimKodlari />
        ) : (
          <Ayarlar />
        )}
      </Suspense>
    </section>
  );
}
