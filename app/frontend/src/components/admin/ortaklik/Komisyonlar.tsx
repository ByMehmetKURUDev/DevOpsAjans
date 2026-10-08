import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, Download, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { KART, Rozet } from '@/components/ortaklik/ortak';
import { paraBicimle, tarihBicimle } from '@/lib/belge';
import { hataMetni, komisyonCsv, komisyonIslem, komisyonListesi, type Komisyon } from '@/lib/ortaklik';

const SUZGECLER = ['', 'beklemede', 'onaylandi', 'odeme_talebinde', 'odendi', 'iptal', 'supheli'] as const;

/** Faz 5K — komisyon defteri: komisyon (+) ve ters kayıt (−); beklemedekini erken onayla, şüpheliyi iptal et; CSV. */
export default function Komisyonlar({ onDegisti }: { onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [suzgec, setSuzgec] = useState<(typeof SUZGECLER)[number]>('');
  const [liste, setListe] = useState<Komisyon[] | null>(null);
  const [mesgul, setMesgul] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe(await komisyonListesi(suzgec || undefined));
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
      setListe([]);
    }
  }, [suzgec, t]);

  useEffect(() => {
    setListe(null);
    void yukle();
  }, [yukle]);

  const islem = async (k: Komisyon, tur: 'onayla' | 'iptal') => {
    if (tur === 'iptal' && !window.confirm(t('ortaklik.yonetim.komisyon.iptalOnay'))) return;
    setMesgul(k.id);
    try {
      await komisyonIslem(k.id, tur);
      onDegisti();
      await yukle();
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    } finally {
      setMesgul(null);
    }
  };

  const csv = async () => {
    try {
      await komisyonCsv(suzgec || undefined);
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    }
  };

  return (
    <div className="space-y-3" data-testid="ortaklik-komisyonlar">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {SUZGECLER.map((d) => (
          <button key={d || 'hepsi'} type="button" onClick={() => setSuzgec(d)} aria-pressed={suzgec === d}
            className={`rounded-full border px-3 py-1 ${suzgec === d ? 'border-purple-400 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground'}`}>
            {d === '' ? t('ortaklik.yonetim.komisyon.filtre.hepsi') : d === 'supheli' ? t('ortaklik.yonetim.komisyon.filtre.supheli') : t(`ortaklik.panel.durum.${d}`)}
          </button>
        ))}
        <Button size="sm" variant="outline" className="ms-auto gap-1.5" onClick={() => void csv()} data-testid="komisyon-csv">
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          {t('ortaklik.yonetim.csv')}
        </Button>
      </div>
      <div className={`${KART} overflow-x-auto p-4`}>
        {!liste ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : liste.length === 0 ? (
          <p className="p-2 text-sm text-muted-foreground">{t('ortaklik.yonetim.komisyon.yok')}</p>
        ) : (
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground">
                <th className="py-2 text-start font-medium">{t('ortaklik.panel.sutun.tarih')}</th>
                <th className="py-2 text-start font-medium">{t('ortaklik.yonetim.ortak.ad')}</th>
                <th className="py-2 text-start font-medium">{t('ortaklik.panel.sutun.fatura')}</th>
                <th className="py-2 text-start font-medium">{t('ortaklik.panel.sutun.musteri')}</th>
                <th className="py-2 text-end font-medium">{t('ortaklik.panel.sutun.tutar')}</th>
                <th className="py-2 text-end font-medium">{t('ortaklik.panel.sutun.durum')}</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {liste.map((k) => (
                <tr key={k.id} data-komisyon={k.id}>
                  <td className="py-2 align-top">{tarihBicimle(k.created_at, dil)}</td>
                  <td className="py-2 align-top">{k.ortak_ad || `#${k.ortak_id}`}</td>
                  <td className="py-2 align-top">
                    {k.fatura_no || '—'}
                    {k.tur === 'ters' && <span className="block text-xs text-amber-200">{t('ortaklik.panel.tur.ters')}</span>}
                    {!!k.supheli?.length && (
                      <span className="mt-0.5 flex items-center gap-1 text-xs text-red-200" data-supheli>
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                        {k.supheli.map((s) => t(`ortaklik.yonetim.supheli.${s}`, { defaultValue: s })).join(' · ')}
                      </span>
                    )}
                  </td>
                  <td className="break-all py-2 align-top text-muted-foreground">{k.musteri_eposta || '—'}</td>
                  <td className={`py-2 text-end align-top tabular-nums ${k.tutar < 0 ? 'text-amber-200' : ''}`}>
                    {paraBicimle(k.tutar, k.para_birimi, dil)}
                    {k.tur === 'komisyon' && (
                      <span className="block text-[11px] text-muted-foreground">
                        {t('ortaklik.yonetim.komisyon.matrah', { tutar: paraBicimle(k.matrah, k.para_birimi, dil), oran: k.oran })}
                        {' · '}
                        {t(`ortaklik.panel.kural.${k.kural || 'ilk'}`)}
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-end align-top">
                    <Rozet durum={k.durum}>{t(`ortaklik.panel.durum.${k.durum}`)}</Rozet>
                  </td>
                  <td className="py-2 text-end align-top">
                    <div className="flex justify-end gap-1">
                      {k.durum === 'beklemede' && (
                        <Button size="sm" variant="ghost" disabled={mesgul === k.id} onClick={() => void islem(k, 'onayla')}>
                          {t('ortaklik.yonetim.komisyon.onayla')}
                        </Button>
                      )}
                      {(k.durum === 'beklemede' || k.durum === 'onaylandi') && (
                        <Button size="sm" variant="ghost" className="text-red-200" disabled={mesgul === k.id} onClick={() => void islem(k, 'iptal')}>
                          {t('ortaklik.yonetim.komisyon.iptal')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
