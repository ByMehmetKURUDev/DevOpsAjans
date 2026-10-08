import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Check, Loader2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, GIRDI, KART, Rozet } from '@/components/ortaklik/ortak';
import { tarihBicimle } from '@/lib/belge';
import { hataMetni, ortakKarar, ortakListesi, type Ortak } from '@/lib/ortaklik';

/** Faz 5K — ortaklık başvuruları: onay (oran + kod; boşsa varsayılan / otomatik) ya da ret (neden ortağa gider). */
export default function Basvurular({ onDegisti }: { onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [goster, setGoster] = useState<'beklemede' | 'reddedildi'>('beklemede');
  const [liste, setListe] = useState<Ortak[] | null>(null);
  const [karar, setKarar] = useState<{ id: number; tur: 'onay' | 'ret'; oran: string; kod: string; neden: string } | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe(await ortakListesi(goster));
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
      setListe([]);
    }
  }, [goster, t]);

  useEffect(() => {
    setListe(null);
    void yukle();
  }, [yukle]);

  const uygula = async () => {
    if (!karar) return;
    setMesgul(true);
    try {
      await ortakKarar(karar.id, karar.tur === 'onay' ? { karar: 'onay', oran: karar.oran, kod: karar.kod } : { karar: 'ret', neden: karar.neden });
      toast.success(karar.tur === 'onay' ? t('ortaklik.yonetim.basvuru.onaylandi') : t('ortaklik.yonetim.basvuru.reddedildi'));
      setKarar(null);
      onDegisti();
      await yukle();
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="ortaklik-basvurular">
      <div className="flex gap-2 text-sm">
        {(['beklemede', 'reddedildi'] as const).map((d) => (
          <button key={d} type="button" onClick={() => setGoster(d)} aria-pressed={goster === d}
            className={`rounded-full border px-3 py-1 ${goster === d ? 'border-purple-400 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground'}`}>
            {t(`ortaklik.yonetim.durum.${d}`)}
          </button>
        ))}
      </div>
      {!liste ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : liste.length === 0 ? (
        <p className={`${KART} p-6 text-sm text-muted-foreground`}>{t('ortaklik.yonetim.basvuru.yok')}</p>
      ) : (
        liste.map((o) => (
          <article key={o.id} className={`${KART} p-5`} data-basvuru={o.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                  {o.ad} <Rozet durum={o.durum}>{t(`ortaklik.yonetim.durum.${o.durum}`)}</Rozet>
                </h3>
                <p className="mt-0.5 break-all text-sm text-muted-foreground">
                  {o.eposta}
                  {o.web ? ` · ${o.web}` : ''} · {tarihBicimle(o.basvuru_at, dil, true)}
                </p>
                <p className="mt-2 whitespace-pre-line text-sm">
                  <span className="text-muted-foreground">{t('ortaklik.yonetim.basvuru.tanitim')}:</span> {o.tanitim}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t('ortaklik.yonetim.basvuru.kosul', { tarih: tarihBicimle(o.kosullar_kabul_at, dil, true) })} · {o.kosullar_surumu}
                  {o.pazarlama_izni ? ` · ${t('ortaklik.yonetim.basvuru.pazarlama')}` : ''}
                </p>
                {o.ret_nedeni && <p className="mt-1 text-xs text-red-200">{o.ret_nedeni}</p>}
              </div>
              <div className="flex gap-2">
                <Button size="sm" className="gap-1" onClick={() => setKarar({ id: o.id, tur: 'onay', oran: '', kod: '', neden: '' })} data-testid={`basvuru-onayla-${o.id}`}>
                  <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('ortaklik.yonetim.basvuru.onayla')}
                </Button>
                {o.durum === 'beklemede' && (
                  <Button size="sm" variant="outline" className="gap-1 border-white/20 !bg-transparent" onClick={() => setKarar({ id: o.id, tur: 'ret', oran: '', kod: '', neden: '' })}>
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('ortaklik.yonetim.basvuru.reddet')}
                  </Button>
                )}
              </div>
            </div>
            {karar?.id === o.id && (
              <div className="mt-4 grid gap-3 rounded-xl border border-white/10 bg-black/20 p-4 md:grid-cols-3">
                {karar.tur === 'onay' ? (
                  <>
                    <Alan etiket={t('ortaklik.yonetim.basvuru.oran')}>
                      <input className={GIRDI} type="number" min={0} max={90} step="0.5" value={karar.oran} onChange={(e) => setKarar({ ...karar, oran: e.target.value })} data-testid="basvuru-oran" />
                    </Alan>
                    <Alan etiket={t('ortaklik.yonetim.basvuru.kod')}>
                      <input className={`${GIRDI} uppercase`} value={karar.kod} maxLength={32} onChange={(e) => setKarar({ ...karar, kod: e.target.value })} data-testid="basvuru-kod" />
                    </Alan>
                  </>
                ) : (
                  <Alan etiket={t('ortaklik.yonetim.basvuru.neden')} className="md:col-span-2">
                    <input className={GIRDI} value={karar.neden} maxLength={500} onChange={(e) => setKarar({ ...karar, neden: e.target.value })} />
                  </Alan>
                )}
                <div className="flex items-end gap-2">
                  <Button size="sm" disabled={mesgul} onClick={() => void uygula()} data-testid="basvuru-karar-kaydet">
                    {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                    {karar.tur === 'onay' ? t('ortaklik.yonetim.basvuru.onayla') : t('ortaklik.yonetim.basvuru.reddet')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setKarar(null)}>
                    {t('ortaklik.yonetim.vazgec')}
                  </Button>
                </div>
              </div>
            )}
          </article>
        ))
      )}
    </div>
  );
}
