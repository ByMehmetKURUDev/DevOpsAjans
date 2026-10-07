import { Check, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import type { StratejiIcerigi, StratejiSablonu, Uyari } from '@/lib/belgeler';

import { AiUyarilari } from './ortak';

/**
 * Faz 5B — strateji şablonunun ızgarası (SWOT 2×2, İş Modeli Kanvası 9 kutu …).
 *
 * Düzen sunucudan (`/meta` › `strateji_sablonlari`): her kutunun sütun/satır başlangıcı ve
 * genişliği CSS grid'e aynen geçiyor. Telefonda (≤ 767 px) kutular alt alta. Düzenleme
 * kipinde her kutu bir metin alanı; AI taslağı geldiyse kutunun altında öneri + "uygula".
 */

const VURGULU = new Set(['ikigai', 'ortak_degerler', 'rekabet', 'deger', 'deger_onerisi']);

interface Ozellikler {
  sablon: StratejiSablonu;
  icerik: StratejiIcerigi;
  duzenlenebilir?: boolean;
  onDegis?: (kutu: string, metin: string) => void;
  oneriler?: Record<string, string> | null;
  oneriUyarilari?: Record<string, Uyari[]> | null;
  onOneriUygula?: (kutu: string) => void;
}

export default function StratejiIzgarasi({ sablon, icerik, duzenlenebilir, onDegis, oneriler, oneriUyarilari, onOneriUygula }: Ozellikler) {
  const { t } = useTranslation();
  const ad = (k: string) => t(`belgeler.sablon.${sablon.tur}.kutu.${k}`);
  return (
    <div
      className="strateji-izgara"
      style={{ gridTemplateColumns: `repeat(${sablon.sutun}, minmax(0, 1fr))` }}
      data-testid={`strateji-izgara-${sablon.tur}`}
    >
      {sablon.kutular.map((k) => {
        const metin = icerik.kutular[k.anahtar] || '';
        const oneri = oneriler?.[k.anahtar];
        return (
          <section
            key={k.anahtar}
            className={`strateji-kutu flex min-w-0 flex-col rounded-xl border p-3 ${
              VURGULU.has(k.anahtar) ? 'border-emerald-400/40 bg-emerald-400/10' : 'border-white/10 bg-white/[0.03]'
            }`}
            style={{ gridColumn: `${k.sutun} / span ${k.en}`, gridRow: `${k.satir} / span ${k.boy}`, minHeight: '7rem' }}
            data-kutu={k.anahtar}
            aria-label={ad(k.anahtar)}
          >
            <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-300">{ad(k.anahtar)}</h4>
            {duzenlenebilir ? (
              <textarea
                value={metin}
                onChange={(e) => onDegis?.(k.anahtar, e.target.value)}
                placeholder={t('belgeler.alanlar.kutuIpucu')}
                className="w-full flex-1 resize-y rounded-md border border-white/10 bg-white/5 p-2 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground"
                style={{ minHeight: '5.5rem' }}
                maxLength={3000}
                data-testid={`kutu-${k.anahtar}`}
              />
            ) : metin.trim() ? (
              <ul className="space-y-1 text-sm leading-relaxed text-slate-200">
                {metin
                  .split('\n')
                  .map((s) => s.trim())
                  .filter(Boolean)
                  .map((s, i) => (
                    <li key={i} className="break-words">
                      {/^[-*+•]\s+/.test(s) ? `• ${s.replace(/^[-*+•]\s+/, '')}` : s}
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">—</p>
            )}
            {oneri && (
              <div className="yazdirma mt-2 rounded-lg border border-fuchsia-400/30 bg-fuchsia-500/10 p-2 text-xs text-white" data-testid={`oneri-${k.anahtar}`}>
                <p className="mb-1 flex items-center gap-1 font-medium">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('belgeler.ai.oneri')}
                </p>
                <p className="whitespace-pre-wrap break-words">{oneri}</p>
                <AiUyarilari uyarilar={oneriUyarilari?.[k.anahtar]} />
                {onOneriUygula && (
                  <Button size="sm" variant="outline" className="mt-2 h-7 gap-1 !bg-transparent px-2 text-xs" onClick={() => onOneriUygula(k.anahtar)}>
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('belgeler.ai.kutuyaUygula')}
                  </Button>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
