import { useState } from 'react';
import { AlertTriangle, CalendarClock, CheckCircle2, ExternalLink, Image as Resim, Loader2, MessageSquareWarning, Tag, Video } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { olcumYaz, planlananYaz, type OnaySonucu, type Onizleme } from '@/lib/icerikOnay';

/**
 * Faz 5I — Bir gönderinin müşteriye gösterilen önizlemesi (kanal sekmeleri, metin, görseller)
 * ve isteğe bağlı karar düğmeleri. Üç yerde: müşteri paneli "Onay bekleyen içerikler",
 * girişsiz `/icerik-onay/<jeton>` sayfası ve İçerik stüdyosu › Onaylar (müşteri modu).
 * Metinler `icerikOnay` ek paketinde.
 */

const NOT_SINIRI = 2000;

function guvenliAdres(adres?: string | null): string | null {
  if (!adres) return null;
  try {
    const u = new URL(adres);
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null;
  } catch {
    return null;
  }
}

export function IcerikOnizleme({ g, testId }: { g: Onizleme; testId?: string }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [secili, setSecili] = useState(0);
  const kanal = g.kanallar[Math.min(secili, Math.max(0, g.kanallar.length - 1))];
  const video = guvenliAdres(g.video_url);

  return (
    <div className="min-w-0" data-testid={testId}>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
          {t('icerikOnay.planlanan')}: <span className="text-white/90">{planlananYaz(g, dil)}</span>
        </span>
        {g.kampanya && (
          <span className="inline-flex items-center gap-1">
            <Tag className="h-3.5 w-3.5" aria-hidden="true" />
            {t('icerikOnay.kampanya')}: <span className="text-white/90">{g.kampanya}</span>
          </span>
        )}
        {g.marka_adi && (
          <span>
            {t('icerikOnay.marka')}: <span className="text-white/90">{g.marka_adi}</span>
          </span>
        )}
      </div>

      {g.kanallar.length > 1 && (
        <div className="mb-2 flex flex-wrap gap-1" role="tablist" aria-label={t('icerikOnay.kanallar')}>
          {g.kanallar.map((k, i) => (
            <button
              key={k.kanal}
              type="button"
              role="tab"
              aria-selected={i === secili}
              onClick={() => setSecili(i)}
              data-onizleme-kanal={k.kanal}
              className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                i === secili ? 'border-purple-400/50 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'
              }`}
            >
              {t(`icerikOnay.kanal.${k.kanal}`, { defaultValue: k.kanal })}
            </button>
          ))}
        </div>
      )}

      {kanal && (
        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
          <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
            <span className="font-medium text-white/80">{t(`icerikOnay.kanal.${kanal.kanal}`, { defaultValue: kanal.kanal })}</span>
            <span className={kanal.olcum.asim ? 'text-rose-300' : ''} title={kanal.olcum.asim ? t('icerikOnay.sinirAsimi') : undefined}>
              {kanal.olcum.asim && <AlertTriangle className="me-1 inline h-3 w-3" aria-hidden="true" />}
              {olcumYaz(kanal.olcum, dil)}
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed" dir="auto" data-testid="onizleme-metin">
            {kanal.metin || '—'}
          </p>
          {kanal.baglanti && !kanal.metin.includes(kanal.baglanti) && (
            <p className="mt-2 break-all text-xs text-muted-foreground">
              {t('icerikOnay.baglanti')}: <span className="text-sky-200">{kanal.baglanti}</span>
            </p>
          )}
          {kanal.ilk_yorum && (
            <p className="mt-2 border-t border-white/5 pt-2 text-xs text-muted-foreground" dir="auto">
              {t('icerikOnay.ilkYorum')}: <span className="whitespace-pre-wrap text-white/80">{kanal.ilk_yorum}</span>
            </p>
          )}
        </div>
      )}

      {g.gorseller.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 flex items-center gap-1 text-xs text-muted-foreground">
            <Resim className="h-3.5 w-3.5" aria-hidden="true" />
            {t('icerikOnay.gorseller')}
          </p>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {g.gorseller.map((r) => (
              <a key={r.url} href={r.url} target="_blank" rel="noopener noreferrer" className="block overflow-hidden rounded-lg border border-white/10">
                <img src={r.url} alt={r.ad || t('icerikOnay.gorseller')} loading="lazy" className="aspect-square w-full object-cover" />
              </a>
            ))}
          </div>
        </div>
      )}
      {video && (
        <a href={video} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-sky-200 hover:underline">
          <Video className="h-3.5 w-3.5" aria-hidden="true" />
          {t('icerikOnay.video')}
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </a>
      )}
    </div>
  );
}

/** Onayla / revizyon iste (not zorunlu) — onay penceresi yerine satır içi adım. */
export function IcerikKarari({
  onKarar,
  testId,
}: {
  onKarar: (sonuc: OnaySonucu, not?: string) => Promise<void>;
  testId?: string;
}) {
  const { t } = useTranslation();
  const [secilen, setSecilen] = useState<OnaySonucu | null>(null);
  const [not, setNot] = useState('');
  const [calisiyor, setCalisiyor] = useState(false);
  const notGecersiz = (secilen === 'revizyon' && !not.trim()) || not.length > NOT_SINIRI;

  const gonder = async () => {
    if (!secilen || notGecersiz) return;
    setCalisiyor(true);
    try {
      await onKarar(secilen, not.trim() || undefined);
    } finally {
      setCalisiyor(false);
    }
  };

  if (!secilen) {
    return (
      <div className="mt-4 flex flex-col gap-2 sm:flex-row" data-testid={testId}>
        <Button type="button" onClick={() => setSecilen('onay')} className="gap-1.5 sm:flex-1" data-karar="onay">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          {t('icerikOnay.onayla')}
        </Button>
        <Button type="button" variant="outline" onClick={() => setSecilen('revizyon')} className="gap-1.5 !bg-transparent sm:flex-1" data-karar="revizyon">
          <MessageSquareWarning className="h-4 w-4" aria-hidden="true" />
          {t('icerikOnay.revizyonIste')}
        </Button>
      </div>
    );
  }
  return (
    <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-3" data-testid={testId} data-secilen={secilen}>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">{secilen === 'revizyon' ? t('icerikOnay.revizyonNotu') : t('icerikOnay.notIstege')}</span>
        <textarea
          value={not}
          onChange={(e) => setNot(e.target.value)}
          rows={3}
          maxLength={NOT_SINIRI}
          dir="auto"
          placeholder={secilen === 'revizyon' ? t('icerikOnay.revizyonIpucu') : ''}
          className="w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
          data-testid="karar-not"
        />
      </label>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" className="!bg-transparent" onClick={() => setSecilen(null)} disabled={calisiyor}>
          {t('icerikOnay.vazgec')}
        </Button>
        <Button type="button" onClick={gonder} disabled={calisiyor || notGecersiz} className="gap-1.5" data-testid="karar-gonder">
          {calisiyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {secilen === 'onay' ? t('icerikOnay.onayla') : t('icerikOnay.revizyonGonder')}
        </Button>
      </div>
    </div>
  );
}
