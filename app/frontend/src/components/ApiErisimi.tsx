import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BookOpenText, Bot, KeyRound, ShieldAlert, Webhook } from 'lucide-react';

import Anahtarlar from '@/components/apiErisimi/Anahtarlar';
import Belgeler from '@/components/apiErisimi/Belgeler';
import McpYardimi from '@/components/apiErisimi/McpYardimi';
import Webhooklar from '@/components/apiErisimi/Webhooklar';
import { apiErisimApi, hataMetni, type ApiMeta, type ApiMod } from '@/lib/apiErisimi';

/**
 * Faz 4A — "API ve webhook" sekmesi. Yönetici panelinde (`mod="yonetici"`: ajans
 * anahtarları — bütün müşterilere erişir; müşterilerinkini de görüp iptal edebilir)
 * ve müşteri panelinde (`mod="musteri"`: yalnız etkin hesap; modül `api_erisimi`
 * + ekip izni `api`) aynı bileşen.
 *
 * Alt görünümler: anahtarlar · webhook'lar (teslimat geçmişi) · API belgeleri
 * (OpenAPI'den, dış CDN yok) · Claude ile bağla (MCP).
 */

type AltSekme = 'anahtarlar' | 'webhooklar' | 'belgeler' | 'mcp';

const ALT_SEKMELER: { key: AltSekme; ikon: typeof KeyRound }[] = [
  { key: 'anahtarlar', ikon: KeyRound },
  { key: 'webhooklar', ikon: Webhook },
  { key: 'belgeler', ikon: BookOpenText },
  { key: 'mcp', ikon: Bot },
];

export default function ApiErisimi({ mod }: { mod: ApiMod }) {
  const { t } = useTranslation();
  const api = useMemo(() => apiErisimApi(mod), [mod]);
  const [sekme, setSekme] = useState<AltSekme>('anahtarlar');
  const [meta, setMeta] = useState<ApiMeta | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  const metaYukle = useCallback(async () => {
    try {
      setMeta(await api.meta());
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void metaYukle();
  }, [metaYukle]);

  return (
    <section aria-labelledby="api-baslik" data-testid="api-sekmesi" className="min-w-0">
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="api-baslik">
          <KeyRound className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('apiErisimi.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {mod === 'yonetici' ? t('apiErisimi.aciklamaYonetici') : t('apiErisimi.aciklama')}
        </p>
      </div>

      {mod === 'yonetici' && (
        <div
          className="mb-6 flex gap-3 rounded-2xl border border-amber-400/40 bg-amber-500/10 p-4 text-sm text-amber-100"
          data-testid="api-ajans-uyari"
        >
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <p>{t('apiErisimi.ajansUyari', { gun: meta?.onerilen_ajans_suresi_gun ?? 90 })}</p>
        </div>
      )}

      <div className="mb-6 flex flex-wrap gap-2" role="tablist" aria-label={t('apiErisimi.baslik')}>
        {ALT_SEKMELER.map(({ key, ikon: Ikon }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={sekme === key}
            data-api-sekme={key}
            onClick={() => setSekme(key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 ${
              sekme === key
                ? 'border-purple-400/60 bg-purple-500/20 text-white'
                : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-white'
            }`}
          >
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`apiErisimi.sekme.${key}`)}
          </button>
        ))}
      </div>

      {hata && (
        <p className="mb-4 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200" role="alert">
          {hata}
        </p>
      )}

      {sekme === 'anahtarlar' && <Anahtarlar api={api} mod={mod} meta={meta} onDegisti={metaYukle} />}
      {sekme === 'webhooklar' && <Webhooklar api={api} mod={mod} meta={meta} onDegisti={metaYukle} />}
      {sekme === 'belgeler' && <Belgeler meta={meta} />}
      {sekme === 'mcp' && <McpYardimi meta={meta} mod={mod} />}
    </section>
  );
}
