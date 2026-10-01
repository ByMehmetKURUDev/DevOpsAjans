import { useTranslation } from 'react-i18next';
import { Bot } from 'lucide-react';

import { KART, KodKutusu, ROZET } from '@/components/apiErisimi/ortak';
import type { ApiMeta, ApiMod } from '@/lib/apiErisimi';

/**
 * Faz 4A — "Claude ile bağla": uzak MCP sunucusunun adresi ve Claude Desktop /
 * Claude Code yapılandırma örnekleri (kopyala düğmeli). Anahtar burada yer tutucu:
 * ham anahtar yalnız oluşturulduğu anda gösteriliyor, sayfada saklanmıyor.
 */

const ARACLAR: { ad: string; kapsam: string | null; ajans?: boolean }[] = [
  { ad: 'hesap_ozeti', kapsam: null },
  { ad: 'projeleri_listele', kapsam: 'projeler:oku' },
  { ad: 'proje_getir', kapsam: 'projeler:oku' },
  { ad: 'gorevleri_listele', kapsam: 'gorevler:oku' },
  { ad: 'gorev_olustur', kapsam: 'gorevler:yaz' },
  { ad: 'gorev_guncelle', kapsam: 'gorevler:yaz' },
  { ad: 'faturalari_listele', kapsam: 'faturalar:oku' },
  { ad: 'destek_talepleri_listele', kapsam: 'destek:oku' },
  { ad: 'destek_talebi_getir', kapsam: 'destek:oku' },
  { ad: 'destek_talebi_olustur', kapsam: 'destek:yaz' },
  { ad: 'destek_talebini_yanitla', kapsam: 'destek:yaz' },
  { ad: 'crm_adaylarini_listele', kapsam: 'crm:oku', ajans: true },
  { ad: 'crm_adayi_olustur', kapsam: 'crm:yaz', ajans: true },
];

const YER_TUTUCU = 'mk_live_…';

export default function McpYardimi({ meta, mod }: { meta: ApiMeta | null; mod: ApiMod }) {
  const { t } = useTranslation();
  const url = meta?.mcp_url || 'https://mehmetkuru.dev/api/public/v1/mcp';
  const claudeCode = `claude mcp add --transport http mehmetkuru-dev ${url} \\
  --header "Authorization: Bearer ${YER_TUTUCU}"`;
  const projeDosyasi = JSON.stringify(
    { mcpServers: { 'mehmetkuru-dev': { type: 'http', url, headers: { Authorization: 'Bearer ${MK_API_KEY}' } } } },
    null,
    2
  );
  const desktop = JSON.stringify(
    {
      mcpServers: {
        'mehmetkuru-dev': {
          command: 'npx',
          args: ['-y', 'mcp-remote', url, '--header', 'Authorization:${MK_AUTH}'],
          env: { MK_AUTH: `Bearer ${YER_TUTUCU}` },
        },
      },
    },
    null,
    2
  );

  return (
    <div className="space-y-6" data-testid="api-mcp">
      <div className={`${KART} space-y-3 p-5`}>
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <Bot className="h-5 w-5 text-purple-300" aria-hidden="true" />
          {t('apiErisimi.mcp.baslik')}
        </h3>
        <p className="text-sm text-muted-foreground">{t('apiErisimi.mcp.aciklama')}</p>
        <KodKutusu baslik={t('apiErisimi.mcp.url')} kod={url} testId="api-mcp-url" />
        <p className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">{t('apiErisimi.mcp.anahtarNotu')}</p>
      </div>

      <div className="space-y-3">
        <h3 className="text-base font-semibold">{t('apiErisimi.mcp.code')}</h3>
        <p className="text-sm text-muted-foreground">{t('apiErisimi.mcp.codeAciklama')}</p>
        <KodKutusu baslik="Terminal" kod={claudeCode} testId="api-mcp-claude-code" />
        <KodKutusu baslik={t('apiErisimi.mcp.projeDosyasi')} kod={projeDosyasi} />
      </div>

      <div className="space-y-3">
        <h3 className="text-base font-semibold">{t('apiErisimi.mcp.desktop')}</h3>
        <p className="text-sm text-muted-foreground">{t('apiErisimi.mcp.desktopAciklama')}</p>
        <KodKutusu baslik="claude_desktop_config.json" kod={desktop} testId="api-mcp-desktop" />
      </div>

      <div className={`${KART} p-5`}>
        <h3 className="mb-2 text-base font-semibold">{t('apiErisimi.mcp.araclar')}</h3>
        <p className="mb-3 text-xs text-muted-foreground">{t('apiErisimi.mcp.araclarAciklama')}</p>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {ARACLAR.filter((a) => mod === 'yonetici' || !a.ajans).map((a) => (
            <li key={a.ad} className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
              <code className="font-mono text-white" dir="ltr">
                {a.ad}
              </code>
              <span className={`${ROZET} border-purple-400/30 bg-purple-500/10 text-purple-100`} dir="ltr">
                {a.kapsam || t('apiErisimi.mcp.herAnahtar')}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
