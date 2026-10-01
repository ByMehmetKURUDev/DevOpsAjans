import { ArrowLeftRight, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Hesap } from '@/lib/hesapEkibi';

/**
 * Faz 2E — müşteri panelinin üstündeki hesap seçici ve "başka hesapta
 * çalışıyorsunuz" şeridi. Panel bunu yalnız kişinin birden çok hesaba
 * erişimi varsa (ya da etkin hesap kendi hesabı değilse) yüklüyor (lazy,
 * ek paket `hesapEkibi`).
 */
export default function HesapSecici({
  hesaplar,
  etkin,
  ben,
  onSec,
}: {
  hesaplar: Hesap[];
  etkin: Hesap;
  ben: string;
  onSec: (hesapEmail: string) => void;
}) {
  const { t } = useTranslation();
  const rolAdi = t(`hesapEkibi.rol.${etkin.rol}`);
  const etiket = (h: Hesap) =>
    h.kendi
      ? `${t('hesapEkibi.secici.kendiHesabim')} · ${h.hesap_email}`
      : `${h.ad || h.hesap_email} · ${t(`hesapEkibi.rol.${h.rol}`)}`;

  return (
    <div className="mb-6 space-y-3" data-hesap-secici>
      {hesaplar.length > 1 && (
        <label className="cam-kart flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <span className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
            <Users className="h-4 w-4" aria-hidden="true" />
            {t('hesapEkibi.secici.etiket')}
          </span>
          <select
            data-testid="hesap-secici"
            value={etkin.hesap_email}
            onChange={(e) => onSec(e.target.value)}
            className="h-10 min-w-0 flex-1 rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40 sm:max-w-md"
          >
            {hesaplar.map((h) => (
              <option key={h.hesap_email} value={h.hesap_email} className="bg-background">
                {etiket(h)}
              </option>
            ))}
          </select>
        </label>
      )}
      {!etkin.kendi && (
        <div
          role="status"
          data-hesap-serit
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-400/30 bg-sky-500/10 px-4 py-2 text-sm text-sky-100"
        >
          <span>{t('hesapEkibi.secici.serit', { hesap: etkin.ad || etkin.hesap_email, rol: rolAdi })}</span>
          <button
            type="button"
            onClick={() => onSec(ben)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-sky-200 underline-offset-2 hover:underline"
          >
            <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden="true" />
            {t('hesapEkibi.secici.donus')}
          </button>
        </div>
      )}
    </div>
  );
}
