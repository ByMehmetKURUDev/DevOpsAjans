import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, RefreshCw, Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DURUMLAR, hataMetni, tarihSaat, type Durum, type IsOzeti, type SahaApi } from '@/lib/sahaServisi';
import { Bos, DurumRozeti, GIRDI, KART, OncelikRozeti, SECIM, Yukleniyor } from './ortak';

const IsFormu = lazy(() => import('./IsFormu'));

/** Faz 6S — iş emirleri listesi (süzgeç + arama) ve yeni iş emri. */
export default function IsEmirleri({ api, onAc, saltOkunur }: { api: SahaApi; onAc: (id: number) => void; saltOkunur: boolean }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<IsOzeti[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [durum, setDurum] = useState<string>('acik');
  const [ara, setAra] = useState('');
  const [yeni, setYeni] = useState(false);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const d = durum === 'acik' ? 'yeni,planlandi,yolda,iste,ertelendi' : durum;
      setListe((await api.isler({ durum: d || undefined, ara: ara.trim() || undefined })).items);
    } catch (e) {
      setHata(hataMetni(t, e));
      setListe([]);
    }
  }, [api, durum, ara, t]);

  useEffect(() => {
    const z = window.setTimeout(() => void yukle(), ara ? 300 : 0);
    return () => window.clearTimeout(z);
  }, [yukle, ara]);

  return (
    <div className="space-y-4" data-testid="saha-isler">
      <div className={`${KART} flex flex-wrap items-end gap-2 p-3`}>
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">{t('sahaServisi.ara')}</span>
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <input className={`${GIRDI} ps-9`} value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('sahaServisi.isler.ara')} />
        </label>
        <select className={`${SECIM} w-auto`} value={durum} onChange={(e) => setDurum(e.target.value)} aria-label={t('sahaServisi.isler.durum')}>
          <option value="acik">{t('sahaServisi.isler.acikOlanlar')}</option>
          <option value="">{t('sahaServisi.isler.hepsi')}</option>
          {DURUMLAR.map((d) => (
            <option key={d} value={d}>
              {t(`sahaServisi.durum.${d}`)}
            </option>
          ))}
        </select>
        <Button size="icon" variant="ghost" onClick={() => void yukle()} aria-label={t('sahaServisi.yenile')}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </Button>
        {!saltOkunur && (
          <Button className="gap-1.5" onClick={() => setYeni(true)} data-testid="saha-is-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('sahaServisi.isler.yeni')}
          </Button>
        )}
      </div>
      {hata && (
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {liste === null ? (
        <Yukleniyor />
      ) : liste.length === 0 ? (
        <div className={KART}>
          <Bos testid="saha-isler-bos">{t('sahaServisi.isler.bos')}</Bos>
        </div>
      ) : (
        <ul className={`${KART} divide-y divide-white/5`} data-testid="saha-isler-liste">
          {liste.map((x) => (
            <li key={x.id}>
              <button type="button" onClick={() => onAc(x.id)} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-start hover:bg-white/[0.03]" data-testid="saha-is-satiri" data-is-id={x.id}>
                <span className="w-24 flex-none font-mono text-xs text-muted-foreground" dir="ltr">
                  {x.no}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{x.baslik}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {x.musteri_ad}
                    {x.adres ? ` · ${x.adres}` : ''}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-1">
                  <DurumRozeti durum={x.durum as Durum} />
                  <OncelikRozeti oncelik={x.oncelik} />
                </span>
                <span className="w-32 text-xs text-muted-foreground">{x.plan_bas ? tarihSaat(x.plan_bas, i18n.language) : t('sahaServisi.planYok')}</span>
                <span className="flex w-28 flex-wrap gap-1 text-xs">
                  {x.teknisyenler.map((te) => (
                    <span key={te.id} className="inline-flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full" style={{ background: te.renk }} aria-hidden="true" />
                      {te.ad}
                    </span>
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {yeni && (
        <Suspense fallback={null}>
          <IsFormu
            api={api}
            onKapat={() => setYeni(false)}
            onKaydedildi={(d) => {
              setYeni(false);
              void yukle();
              onAc(d.id);
            }}
          />
        </Suspense>
      )}
    </div>
  );
}
