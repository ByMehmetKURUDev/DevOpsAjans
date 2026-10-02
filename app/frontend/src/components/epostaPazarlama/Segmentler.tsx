import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Bos, DIS_DUGME, GIRDI, KART, Rozet, SECIM, Yukleniyor, sayiYaz } from '@/components/epostaPazarlama/ortak';
import { hataMetni, type Liste, type Meta, type PazarlamaApi, type Segment, type SegmentKurali } from '@/lib/epostaPazarlama';

const SAYISAL = new Set(['son_etkilesim', 'kayit']);

/** Faz 5M — segmentler: kural tabanlı dinamik kitle (kaynak, etiket, alıcı türü, izin, son etkileşim, özel alan, liste, CRM). */
export default function Segmentler({ api, meta }: { api: PazarlamaApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [segmentler, setSegmentler] = useState<Segment[] | null>(null);
  const [listeler, setListeler] = useState<Liste[]>([]);
  const [ad, setAd] = useState('');
  const [birlesim, setBirlesim] = useState<'ve' | 'veya'>('ve');
  const [kurallar, setKurallar] = useState<SegmentKurali[]>([{ alan: 'etiket', op: 'icerir', deger: '' }]);
  const [onizleme, setOnizleme] = useState<{ sayi: number } | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([api.segmentler(), api.listeler()]);
      setSegmentler(s.items);
      setListeler(l.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setSegmentler([]);
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kuralDegis = (i: number, k: Partial<SegmentKurali>) => {
    setOnizleme(null);
    setKurallar(kurallar.map((x, j) => {
      if (j !== i) return x;
      const yeni = { ...x, ...k };
      if (k.alan && k.alan !== x.alan) {
        yeni.op = meta.segment_oplari[k.alan]?.[0] ?? 'esit';
        yeni.deger = SAYISAL.has(k.alan) ? 30 : k.alan === 'liste' ? listeler[0]?.id : '';
      }
      return yeni;
    }));
  };
  const temiz = () => ({
    birlesim,
    kurallar: kurallar.map((k) => ({ ...k, deger: SAYISAL.has(k.alan) || k.alan === 'liste' ? Number(k.deger) : k.deger })),
  });
  const onizle = async () => {
    try {
      setOnizleme(await api.segmentOnizleme(temiz()));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const kaydet = async () => {
    try {
      await api.segmentEkle({ ad, kurallar: temiz() });
      toast.success(t('epostaPazarlama.genel.kaydedildi'));
      setAd('');
      setOnizleme(null);
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (segmentler === null) return <Yukleniyor />;
  return (
    <div className="space-y-5" data-testid="ep-segmentler">
      <div className={`${KART} space-y-3 p-4`}>
        <h3 className="font-semibold">{t('epostaPazarlama.segment.yeni')}</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('epostaPazarlama.segment.ad')}>
            <input className={GIRDI} value={ad} onChange={(e) => setAd(e.target.value)} data-testid="ep-segment-ad" />
          </Alan>
          <Alan etiket={t('epostaPazarlama.segment.birlesim')}>
            <select className={SECIM} value={birlesim} onChange={(e) => setBirlesim(e.target.value as 've' | 'veya')}>
              <option value="ve">{t('epostaPazarlama.segment.ve')}</option>
              <option value="veya">{t('epostaPazarlama.segment.veya')}</option>
            </select>
          </Alan>
        </div>
        <ul className="space-y-2">
          {kurallar.map((k, i) => (
            <li key={i} className="grid gap-2 rounded-lg border border-white/10 p-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
              <select className={SECIM} value={k.alan} onChange={(e) => kuralDegis(i, { alan: e.target.value })} aria-label={t('epostaPazarlama.segment.alan')}>
                {meta.segment_alanlari.map((a) => (
                  <option key={a} value={a}>
                    {t(`epostaPazarlama.segment.alanlar.${a}`)}
                  </option>
                ))}
              </select>
              <select className={SECIM} value={k.op} onChange={(e) => kuralDegis(i, { op: e.target.value })} aria-label={t('epostaPazarlama.segment.op')}>
                {(meta.segment_oplari[k.alan] || []).map((o) => (
                  <option key={o} value={o}>
                    {t(`epostaPazarlama.segment.oplar.${o}`)}
                  </option>
                ))}
              </select>
              {k.alan === 'liste' ? (
                <select className={SECIM} value={String(k.deger ?? '')} onChange={(e) => kuralDegis(i, { deger: Number(e.target.value) })} aria-label={t('epostaPazarlama.liste.liste')}>
                  {listeler.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.ad}
                    </option>
                  ))}
                </select>
              ) : k.op === 'hic' || k.op === 'dolu' || k.op === 'bos' ? (
                k.alan === 'ozel' ? (
                  <input className={GIRDI} value={k.anahtar ?? ''} onChange={(e) => kuralDegis(i, { anahtar: e.target.value })} placeholder={t('epostaPazarlama.segment.anahtar')} />
                ) : (
                  <span />
                )
              ) : k.alan === 'alici_turu' || k.alan === 'izin_durumu' || k.alan === 'kaynak' ? (
                <select className={SECIM} value={String(k.deger ?? '')} onChange={(e) => kuralDegis(i, { deger: e.target.value })} aria-label={t('epostaPazarlama.segment.deger')}>
                  <option value="" />
                  {(k.alan === 'alici_turu' ? ['bireysel', 'kurumsal'] : k.alan === 'izin_durumu' ? ['izinli', 'izinsiz', 'bekliyor', 'reddetti'] : ['form', 'csv', 'manuel', 'crm']).map((v) => (
                    <option key={v} value={v}>
                      {t(`epostaPazarlama.${k.alan === 'alici_turu' ? 'tur' : k.alan === 'izin_durumu' ? 'izin' : 'kaynak'}.${v}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex gap-2">
                  {k.alan === 'ozel' && (
                    <input className={GIRDI} value={k.anahtar ?? ''} onChange={(e) => kuralDegis(i, { anahtar: e.target.value })} placeholder={t('epostaPazarlama.segment.anahtar')} />
                  )}
                  <input
                    className={GIRDI}
                    type={SAYISAL.has(k.alan) ? 'number' : 'text'}
                    min={1}
                    value={String(k.deger ?? '')}
                    onChange={(e) => kuralDegis(i, { deger: e.target.value })}
                    placeholder={SAYISAL.has(k.alan) ? t('epostaPazarlama.segment.gun') : t('epostaPazarlama.segment.deger')}
                    aria-label={t('epostaPazarlama.segment.deger')}
                    data-testid={`ep-segment-deger-${i}`}
                  />
                </div>
              )}
              <Button size="sm" variant="ghost" className="h-10" onClick={() => setKurallar(kurallar.filter((_, j) => j !== i))} disabled={kurallar.length === 1}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
              </Button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setKurallar([...kurallar, { alan: 'kaynak', op: 'esit', deger: 'form' }])} disabled={kurallar.length >= 20}>
            <Plus className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.segment.kuralEkle')}
          </Button>
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void onizle()} data-testid="ep-segment-onizle">
            {t('epostaPazarlama.segment.onizle')}
          </Button>
          <Button size="sm" onClick={() => void kaydet()} disabled={!ad.trim()} data-testid="ep-segment-kaydet">
            {t('epostaPazarlama.genel.kaydet')}
          </Button>
          {onizleme && (
            <Rozet renk="border-purple-400/30 bg-purple-400/10 text-purple-100" testid="ep-segment-sayi">
              {t('epostaPazarlama.segment.eslesen', { sayi: sayiYaz(onizleme.sayi, dil) })}
            </Rozet>
          )}
        </div>
      </div>

      <div className={`${KART} p-4`}>
        <h3 className="mb-3 font-semibold">{t('epostaPazarlama.alt.segmentler')}</h3>
        {segmentler.length === 0 ? (
          <Bos>{t('epostaPazarlama.segment.bos')}</Bos>
        ) : (
          <ul className="divide-y divide-white/5">
            {segmentler.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0 truncate">{s.ad}</span>
                <span className="flex items-center gap-2">
                  <Rozet>{t('epostaPazarlama.segment.eslesen', { sayi: sayiYaz(s.sayi ?? 0, dil) })}</Rozet>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2"
                    onClick={async () => {
                      try {
                        await api.segmentSil(s.id);
                        void yukle();
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
