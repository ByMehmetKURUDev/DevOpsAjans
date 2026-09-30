import { Mail, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Faz 2F — e-postadan gelen talebin küçük rozeti (müşteri ve yönetici
 * listelerinde). `dogrulanmadi` yalnız yönetici tarafında verilir: gönderen
 * kayıtlı bir müşteri değil, otomatik yanıt gitmedi. Metinler `yardim`
 * ek paketinde.
 */
export default function EpostaRozeti({ dogrulanmadi = false }: { dogrulanmadi?: boolean }) {
  const { t } = useTranslation();
  return (
    <>
      <span
        className="inline-flex items-center gap-1 rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[10px] uppercase tracking-widest text-sky-200"
        data-testid="eposta-rozeti"
        title={t('yardim.eposta.rozetIpucu')}
      >
        <Mail className="h-3 w-3" aria-hidden="true" />
        {t('yardim.eposta.rozet')}
      </span>
      {dogrulanmadi ? (
        <span
          className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[10px] uppercase tracking-widest text-amber-200"
          title={t('yardim.eposta.dogrulanmadiIpucu')}
        >
          <ShieldAlert className="h-3 w-3" aria-hidden="true" />
          {t('yardim.eposta.dogrulanmadi')}
        </span>
      ) : null}
    </>
  );
}
