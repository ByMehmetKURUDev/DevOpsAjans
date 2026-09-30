import { useEffect, useState } from 'react';
import { Mail } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { epostaBilgisi } from '@/lib/destekEposta';

/**
 * Faz 2F — müşteri talep ekranında "Bu talebe e-postayla da yanıt
 * verebilirsiniz" ipucu. Yalnız gelen adres tanımlı (ve e-posta alımı açık)
 * ise görünür. Bilgi sayfa başına bir kez çekilir.
 */
let bilgi: Promise<{ acik: boolean; gelen_adres: string }> | null = null;

export default function EpostaIpucu() {
  const { t } = useTranslation();
  const [adres, setAdres] = useState('');

  useEffect(() => {
    let iptal = false;
    bilgi = bilgi || epostaBilgisi().catch(() => ({ acik: false, gelen_adres: '' }));
    void bilgi.then((b) => {
      if (!iptal && b?.acik) setAdres(b.gelen_adres);
    });
    return () => {
      iptal = true;
    };
  }, []);

  if (!adres) return null;
  return (
    <p className="mt-3 flex items-start gap-2 text-xs text-muted-foreground" data-testid="eposta-ipucu">
      <Mail className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-300" aria-hidden="true" />
      <span>{t('yardim.eposta.ipucu', { adres })}</span>
    </p>
  );
}
