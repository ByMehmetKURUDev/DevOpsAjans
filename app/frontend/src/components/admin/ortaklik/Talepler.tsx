import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy, Download, FileDown, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, GIRDI, KART, Rozet } from '@/components/ortaklik/ortak';
import { getAPIBaseURL } from '@/lib/config';
import { paraBicimle, tarihBicimle } from '@/lib/belge';
import { hataMetni, talepCsv, talepDekontu, talepListesi, talepOdendi, talepReddet, type OdemeTalebi } from '@/lib/ortaklik';

const SUZGECLER = ['bekliyor', 'odendi', 'reddedildi', ''] as const;

/**
 * Faz 5K — ortakların ödeme talepleri. Para aktarımı YOK: ödemeyi bankanızdan (IBAN) yapın, burada
 * "ödendi" işaretleyin (dekont isteğe bağlı; ortağa e-posta gider). Geri çevirince tutar bakiyeye döner.
 */
export default function Talepler({ onDegisti }: { onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [suzgec, setSuzgec] = useState<(typeof SUZGECLER)[number]>('bekliyor');
  const [liste, setListe] = useState<OdemeTalebi[] | null>(null);
  const [acik, setAcik] = useState<{ id: number; tur: 'odendi' | 'ret'; not: string; dosya: File | null } | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe(await talepListesi(suzgec || undefined));
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
      setListe([]);
    }
  }, [suzgec, t]);

  useEffect(() => {
    setListe(null);
    void yukle();
  }, [yukle]);

  const uygula = async () => {
    if (!acik) return;
    setMesgul(true);
    try {
      if (acik.tur === 'odendi') {
        await talepOdendi(acik.id, acik.not, acik.dosya);
        toast.success(t('ortaklik.yonetim.talep.odendiOldu'));
      } else {
        await talepReddet(acik.id, acik.not);
        toast.success(t('ortaklik.yonetim.talep.reddedildi'));
      }
      setAcik(null);
      onDegisti();
      await yukle();
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    } finally {
      setMesgul(false);
    }
  };

  const dekont = async (id: number) => {
    try {
      const { adres } = await talepDekontu(id);
      window.open(`${getAPIBaseURL()}${adres}`, '_blank', 'noopener');
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    }
  };

  const csv = async () => {
    try {
      await talepCsv(suzgec || undefined);
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    }
  };

  return (
    <div className="space-y-3" data-testid="ortaklik-talepler">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {SUZGECLER.map((d) => (
          <button key={d || 'hepsi'} type="button" onClick={() => setSuzgec(d)} aria-pressed={suzgec === d}
            className={`rounded-full border px-3 py-1 ${suzgec === d ? 'border-purple-400 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground'}`}>
            {d ? t(`ortaklik.panel.talepDurum.${d}`) : t('ortaklik.yonetim.komisyon.filtre.hepsi')}
          </button>
        ))}
        <Button size="sm" variant="outline" className="ms-auto gap-1.5" onClick={() => void csv()} data-testid="talep-csv">
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          {t('ortaklik.yonetim.csv')}
        </Button>
      </div>
      {!liste ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : liste.length === 0 ? (
        <p className={`${KART} p-6 text-sm text-muted-foreground`}>{t('ortaklik.yonetim.talep.yok')}</p>
      ) : (
        liste.map((x) => (
          <article key={x.id} className={`${KART} p-5`} data-talep={x.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                  <span className="tabular-nums">{paraBicimle(x.tutar, x.para_birimi, dil)}</span> · {x.ortak_ad}
                  <Rozet durum={x.durum}>{t(`ortaklik.panel.talepDurum.${x.durum}`)}</Rozet>
                </h3>
                <p className="mt-0.5 break-all text-sm text-muted-foreground">
                  {x.ortak_eposta} · {tarihBicimle(x.created_at, dil, true)}
                </p>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-muted-foreground">{t('ortaklik.yonetim.talep.iban')}:</span>
                  <code className="font-mono" data-testid={`talep-iban-${x.id}`}>{x.iban}</code>
                  <span className="text-muted-foreground">({x.iban_ad || '—'})</span>
                  <Button size="sm" variant="ghost" className="h-7 gap-1 px-2" onClick={() => void navigator.clipboard?.writeText(x.iban || '')}>
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('ortaklik.yonetim.talep.kopyala')}
                  </Button>
                </p>
                {x.notu && <p className="mt-1 text-xs text-muted-foreground">{x.notu}</p>}
                {x.ret_nedeni && <p className="mt-1 text-xs text-red-200">{x.ret_nedeni}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                {x.durum === 'bekliyor' && (
                  <>
                    <Button size="sm" onClick={() => setAcik({ id: x.id, tur: 'odendi', not: '', dosya: null })} data-testid={`talep-odendi-${x.id}`}>
                      {t('ortaklik.yonetim.talep.odendi')}
                    </Button>
                    <Button size="sm" variant="outline" className="border-white/20 !bg-transparent" onClick={() => setAcik({ id: x.id, tur: 'ret', not: '', dosya: null })}>
                      {t('ortaklik.yonetim.talep.reddet')}
                    </Button>
                  </>
                )}
                {x.dekont_var && (
                  <Button size="sm" variant="ghost" className="gap-1" onClick={() => void dekont(x.id)}>
                    <FileDown className="h-4 w-4" aria-hidden="true" />
                    {t('ortaklik.yonetim.talep.dekontAc')}
                  </Button>
                )}
              </div>
            </div>
            {acik?.id === x.id && (
              <div className="mt-4 grid gap-3 rounded-xl border border-white/10 bg-black/20 p-4 md:grid-cols-2">
                {acik.tur === 'odendi' && (
                  <Alan etiket={t('ortaklik.yonetim.talep.dekont')}>
                    <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="block w-full text-sm text-muted-foreground"
                      onChange={(e) => setAcik({ ...acik, dosya: e.target.files?.[0] ?? null })} data-testid="talep-dekont" />
                  </Alan>
                )}
                <Alan etiket={acik.tur === 'odendi' ? t('ortaklik.yonetim.talep.not') : t('ortaklik.yonetim.talep.neden')}>
                  <input className={GIRDI} value={acik.not} maxLength={500} onChange={(e) => setAcik({ ...acik, not: e.target.value })} data-testid="talep-not" />
                </Alan>
                <div className="flex gap-2 md:col-span-2">
                  <Button size="sm" disabled={mesgul} onClick={() => void uygula()} data-testid="talep-kaydet">
                    {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                    {acik.tur === 'odendi' ? t('ortaklik.yonetim.talep.gonder') : t('ortaklik.yonetim.talep.reddet')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setAcik(null)}>
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
