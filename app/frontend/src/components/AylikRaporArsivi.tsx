import { useEffect, useState } from 'react';
import { BarChart3, ExternalLink, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { aylikRaporlarim, donemAdi, type RaporSatiri } from '@/lib/aylikRapor';

/**
 * Müşteri paneli › Raporlar › "Aylık raporlarım" (Faz 2C, modül `aylik_rapor`).
 *
 * Yalnız yayınlanmış aylık raporlar; her biri yazdırmaya uygun
 * `/rapor-aylik/<jeton>` sayfasında açılıyor (tarayıcıdan PDF).
 */
export default function AylikRaporArsivi() {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<RaporSatiri[] | null>(null);

  useEffect(() => {
    aylikRaporlarim()
      .then(setListe)
      .catch(() => setListe([]));
  }, []);

  return (
    <section className="cam-kart mb-8 rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-testid="aylik-rapor-arsivi">
      <h3 className="flex items-center gap-2 text-lg font-semibold">
        <BarChart3 className="h-5 w-5 text-cyan-300" aria-hidden="true" /> {t('aylikRapor.arsiv.baslik')}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{t('aylikRapor.arsiv.aciklama')}</p>
      {liste === null ? (
        <div className="flex justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        </div>
      ) : liste.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">{t('aylikRapor.arsiv.bos')}</p>
      ) : (
        <ul className="mt-4 divide-y divide-white/5">
          {liste.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium capitalize">{donemAdi(r.donem, i18n.language)}</p>
                {r.ozet && <p className="line-clamp-2 text-xs text-muted-foreground">{r.ozet}</p>}
              </div>
              <Link
                to={`/rapor-aylik/${r.jeton}`}
                target="_blank"
                rel="noopener"
                className="inline-flex items-center gap-1 text-sm text-purple-300 hover:text-pink-300"
                data-testid={`aylik-rapor-ac-${r.id}`}
              >
                {t('aylikRapor.arsiv.ac')} <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
