import { Archive } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Konusma } from '@/lib/mesajlar';

/** "14:05" (bugün) / "12 Eki" (bu yıl) / "12.10.2025". */
export function kisaZaman(iso: string | null | undefined, dil: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const simdi = new Date();
  if (d.toDateString() === simdi.toDateString()) return d.toLocaleTimeString(dil, { hour: '2-digit', minute: '2-digit' });
  if (d.getFullYear() === simdi.getFullYear()) return d.toLocaleDateString(dil, { day: 'numeric', month: 'short' });
  return d.toLocaleDateString(dil);
}

export function konusmaAdi(k: Pick<Konusma, 'genel' | 'konu'>, t: (a: string) => string): string {
  return k.genel ? t('mesajlar.genel') : k.konu;
}

interface Props {
  liste: Konusma[];
  secili: number | null;
  onSec: (id: number) => void;
  /** Yönetici görünümü: hesap adı / e-posta satırı. */
  yonetici?: boolean;
}

export default function KonusmaListesi({ liste, secili, onSec, yonetici }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  if (liste.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t('mesajlar.konusmaYok')}</p>;
  }
  return (
    <ul className="min-h-0 flex-1 overflow-y-auto" aria-label={t('mesajlar.konusmalar')} data-konusma-listesi>
      {liste.map((k) => {
        const seciliMi = k.id === secili;
        return (
          <li key={k.id}>
            <button
              type="button"
              onClick={() => onSec(k.id)}
              aria-current={seciliMi ? 'true' : undefined}
              className={`w-full border-b border-white/5 px-3 py-3 text-start transition-colors ${
                seciliMi ? 'bg-white/[0.07]' : 'hover:bg-white/[0.04]'
              }`}
              data-konusma={k.id}
              data-secili={seciliMi ? 'evet' : undefined}
            >
              {yonetici && (
                <p className="truncate text-[11px] text-purple-300" dir="auto">
                  {k.hesap_adi ? `${k.hesap_adi} · ${k.hesap_email}` : k.hesap_email}
                </p>
              )}
              <div className="flex items-center gap-2">
                <span className={`min-w-0 flex-1 truncate text-sm ${k.okunmamis ? 'font-semibold text-foreground' : 'font-medium'}`} dir="auto">
                  {konusmaAdi(k, t)}
                </span>
                {k.durum === 'arsiv' && (
                  <span className="inline-flex items-center gap-0.5 rounded bg-white/10 px-1.5 text-[10px] text-muted-foreground">
                    <Archive className="h-3 w-3" aria-hidden="true" /> {t('mesajlar.durumAdi.arsiv')}
                  </span>
                )}
                {k.okunmamis > 0 && (
                  <span
                    className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-pink-600 px-1.5 text-[11px] font-semibold text-white"
                    title={t('mesajlar.okunmamisSayi', { sayi: k.okunmamis })}
                    data-okunmamis={k.okunmamis}
                  >
                    {k.okunmamis}
                    <span className="sr-only"> — {t('mesajlar.okunmamisSayi', { sayi: k.okunmamis })}</span>
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="min-w-0 flex-1 truncate" dir="auto">
                  {k.son_mesaj_ozet || '—'}
                </span>
                <time className="shrink-0" dateTime={k.son_mesaj_at || undefined}>
                  {kisaZaman(k.son_mesaj_at || k.created_at, dil)}
                </time>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
