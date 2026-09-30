import { Timer } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { HedefBilgisi, HedefDurumu, SlaDurumu } from '@/lib/destek';

/**
 * Destek talebi kartındaki SLA rozeti (Faz 2C).
 *
 * Özet: iki hedefin (ilk yanıt, çözüm) en kötüsü. Açık hedefte kalan mesai
 * süresi; aşılmışsa ne kadar aşıldığı. Ayrıntı `title` ile.
 */

const RENK: Record<HedefDurumu, string> = {
  asildi: 'border-red-400/40 bg-red-500/15 text-red-200',
  yaklasiyor: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  zamaninda: 'border-cyan-400/30 bg-cyan-500/10 text-cyan-200',
  gecikti: 'border-orange-400/30 bg-orange-500/10 text-orange-200',
  karsilandi: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  yok: 'border-white/10 bg-white/5 text-muted-foreground',
};

function sureMetni(dk: number, t: (k: string, o?: Record<string, unknown>) => string): string {
  const m = Math.abs(Math.round(dk));
  const saat = Math.floor(m / 60);
  const dakika = m % 60;
  if (saat && dakika) return t('yardim.sla.saatDakika', { saat, dakika });
  if (saat) return t('yardim.sla.saat', { sayi: saat });
  return t('yardim.sla.dakika', { sayi: dakika });
}

function hedefSatiri(ad: string, h: HedefBilgisi, t: (k: string, o?: Record<string, unknown>) => string): string {
  let ek = '';
  if (h.durum === 'zamaninda' || h.durum === 'yaklasiyor') ek = ` — ${t('yardim.sla.kaldi', { sure: sureMetni(h.kalan_dk ?? 0, t) })}`;
  if (h.durum === 'asildi') ek = ` — ${t('yardim.sla.asti', { sure: sureMetni(h.kalan_dk ?? 0, t) })}`;
  return `${ad}: ${t(`yardim.sla.durum.${h.durum}`)}${ek}`;
}

export default function SlaRozeti({ durum }: { durum: SlaDurumu }) {
  const { t } = useTranslation();
  const acik = durum.ilk_yanit.durum === 'zamaninda' || durum.ilk_yanit.durum === 'yaklasiyor' || durum.ilk_yanit.durum === 'asildi'
    ? durum.ilk_yanit
    : durum.cozum;
  let metin = t(`yardim.sla.durum.${durum.ozet}`);
  if (durum.ozet === 'zamaninda' || durum.ozet === 'yaklasiyor') {
    metin = `${t(acik === durum.ilk_yanit ? 'yardim.sla.ilkYanitKisa' : 'yardim.sla.cozumKisa')} · ${sureMetni(acik.kalan_dk ?? 0, t)}`;
  }
  const baslik = [
    t(`yardim.oncelik.${durum.oncelik}`),
    hedefSatiri(t('yardim.sla.ilkYanit'), durum.ilk_yanit, t),
    hedefSatiri(t('yardim.sla.cozum'), durum.cozum, t),
  ].join('\n');
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${RENK[durum.ozet]}`}
      title={baslik}
      data-testid={`sla-rozeti-${durum.ticket_id}`}
      data-durum={durum.ozet}
    >
      <Timer className="h-3 w-3" aria-hidden="true" />
      {metin}
    </span>
  );
}
