import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, Loader2, Pencil, RefreshCw, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, GIRDI, KART, METIN_ALANI, Rozet } from '@/components/ortaklik/ortak';
import { paraBicimle } from '@/lib/belge';
import { hataMetni, ortakGuncelle, ortakListesi, type Ortak } from '@/lib/ortaklik';

/** Faz 5K — onaylı / askıdaki ortaklar: oran, kod, durum, not, şüpheli işaretleri. */
export default function Ortaklar() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<Ortak[] | null>(null);
  const [duzen, setDuzen] = useState<{ id: number; oran: string; kod: string; notlar: string } | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe(await ortakListesi('onaylandi,askida'));
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
      setListe([]);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kaydet = async (o: Ortak, ek: Record<string, unknown>) => {
    setMesgul(true);
    try {
      await ortakGuncelle(o.id, ek);
      toast.success(t('ortaklik.yonetim.kaydedildi'));
      setDuzen(null);
      await yukle();
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    } finally {
      setMesgul(false);
    }
  };

  if (!liste) {
    return (
      <div className="flex justify-center py-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  return (
    <div className="space-y-3" data-testid="ortaklik-ortaklar">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" className="gap-1.5 border-white/20 !bg-transparent" onClick={() => void yukle()}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('ortaklik.yonetim.yenile')}
        </Button>
      </div>
      {liste.length === 0 && <p className={`${KART} p-6 text-sm text-muted-foreground`}>{t('ortaklik.yonetim.ortak.yok')}</p>}
      {liste.map((o) => (
        <article key={o.id} className={`${KART} p-5`} data-ortak={o.id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                {o.ad}
                <Rozet durum={o.durum}>{t(`ortaklik.yonetim.durum.${o.durum}`)}</Rozet>
                {!!o.supheli?.length && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-red-400/30 bg-red-500/10 px-2 py-0.5 text-[11px] text-red-200" data-supheli>
                    <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                    {o.supheli.map((s) => t(`ortaklik.yonetim.supheli.${s}`, { defaultValue: s })).join(' · ')}
                  </span>
                )}
              </h3>
              <p className="mt-0.5 break-all text-sm text-muted-foreground">
                {o.eposta}
                {o.web ? ` · ${o.web}` : ''}
              </p>
              <p className="mt-2 text-sm">
                <span className="text-muted-foreground">{t('ortaklik.yonetim.ortak.kod')}:</span> <code className="font-semibold">{o.kod}</code> ·{' '}
                <span className="text-muted-foreground">{t('ortaklik.yonetim.ortak.oran')}:</span> %{o.oran}
                {!o.oran_ozel && <span className="text-xs text-muted-foreground"> ({t('ortaklik.yonetim.ortak.varsayilan')})</span>} ·{' '}
                <span className="text-muted-foreground">{t('ortaklik.yonetim.ortak.tiklama')}:</span> {o.tiklama ?? 0} ·{' '}
                <span className="text-muted-foreground">{t('ortaklik.yonetim.ortak.aday')}:</span> {o.aday ?? 0}
              </p>
              <p className="mt-1 text-sm">
                <span className="text-muted-foreground">{t('ortaklik.yonetim.ortak.bakiye')}:</span>{' '}
                {Object.entries(o.bakiyeler || {}).length
                  ? Object.entries(o.bakiyeler || {})
                      .map(([pb, b]) => `${paraBicimle(b.onaylandi, pb, dil)} / ${paraBicimle(b.kazanc, pb, dil)}`)
                      .join(' · ')
                  : '—'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" className="gap-1 border-white/20 !bg-transparent" onClick={() => setDuzen({ id: o.id, oran: o.oran_ozel ? String(o.oran) : '', kod: o.kod || '', notlar: o.notlar || '' })}>
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                {t('ortaklik.yonetim.ortak.duzenle')}
              </Button>
              <Button size="sm" variant="outline" className="border-white/20 !bg-transparent" disabled={mesgul}
                onClick={() => void kaydet(o, { durum: o.durum === 'askida' ? 'onaylandi' : 'askida' })} data-testid={`ortak-askiya-${o.id}`}>
                {o.durum === 'askida' ? t('ortaklik.yonetim.ortak.yenidenAc') : t('ortaklik.yonetim.ortak.askiyaAl')}
              </Button>
              {!!o.supheli?.length && (
                <Button size="sm" variant="ghost" disabled={mesgul} onClick={() => void kaydet(o, { supheli_temizle: true })}>
                  {t('ortaklik.yonetim.ortak.supheliTemizle')}
                </Button>
              )}
            </div>
          </div>
          {duzen?.id === o.id && (
            <div className="mt-4 grid gap-3 rounded-xl border border-white/10 bg-black/20 p-4 md:grid-cols-3">
              <Alan etiket={t('ortaklik.yonetim.ortak.oran')} ipucu={t('ortaklik.yonetim.ortak.oranIpucu')}>
                <input className={GIRDI} type="number" min={0} max={90} step="0.5" value={duzen.oran} onChange={(e) => setDuzen({ ...duzen, oran: e.target.value })} />
              </Alan>
              <Alan etiket={t('ortaklik.yonetim.ortak.kod')} ipucu={t('ortaklik.yonetim.ortak.kodIpucu')}>
                <input className={`${GIRDI} uppercase`} value={duzen.kod} maxLength={32} onChange={(e) => setDuzen({ ...duzen, kod: e.target.value })} />
              </Alan>
              <Alan etiket={t('ortaklik.yonetim.ortak.notlar')} className="md:col-span-3">
                <textarea className={METIN_ALANI} value={duzen.notlar} maxLength={2000} onChange={(e) => setDuzen({ ...duzen, notlar: e.target.value })} />
              </Alan>
              <div className="flex gap-2 md:col-span-3">
                <Button size="sm" disabled={mesgul} onClick={() => void kaydet(o, { oran: duzen.oran, kod: duzen.kod, notlar: duzen.notlar })}>
                  {t('ortaklik.yonetim.kaydet')}
                </Button>
                <Button size="sm" variant="ghost" className="gap-1" onClick={() => setDuzen(null)}>
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('ortaklik.yonetim.vazgec')}
                </Button>
              </div>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
