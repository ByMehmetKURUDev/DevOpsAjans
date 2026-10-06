import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, Clock, MapPin, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { bugunIso, gunEkle, gunYaz, hataMetni, saatYaz, tarihSaat, type IsOzeti, type Meta, type Riza, type SahaApi } from '@/lib/sahaServisi';
import { Bos, DurumRozeti, KART, OncelikRozeti, Yukleniyor } from './ortak';

const IsAyrintisi = lazy(() => import('./IsAyrintisi'));
const KonumRizasi = lazy(() => import('./KonumRizasi'));

/**
 * Faz 6S — teknisyen ekranı: "Bugünkü işlerim" (mobil öncelikli, büyük dokunma hedefleri).
 * Yalnız kendine atanan işler; dokununca ayrıntı (durum, kontrol listesi, fotoğraf, imza, PDF).
 */
export default function Islerim({ api, meta, baslangicIs }: { api: SahaApi; meta: Meta; baslangicIs?: number | null }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [gun, setGun] = useState(bugunIso);
  const [veri, setVeri] = useState<{ kayitli: boolean; bugun: IsOzeti[]; diger: IsOzeti[] } | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [secili, setSecili] = useState<number | null>(baslangicIs ?? null);
  const [riza, setRiza] = useState<Riza | null>(null);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [l, r] = await Promise.all([api.islerim(gun), api.rizam()]);
      setVeri(l);
      setRiza(r);
    } catch (e) {
      setHata(hataMetni(t, e));
      setVeri({ kayitli: false, bugun: [], diger: [] });
    }
  }, [api, gun, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (secili !== null) {
    return (
      <Suspense fallback={<Yukleniyor />}>
        <IsAyrintisi
          api={api}
          meta={meta}
          isId={secili}
          riza={riza}
          onGeri={() => {
            setSecili(null);
            void yukle();
          }}
        />
      </Suspense>
    );
  }

  const bugunMu = gun === bugunIso();
  return (
    <div className="space-y-4" data-testid="saha-islerim">
      {veri?.kayitli && riza && (
        <Suspense fallback={null}>
          <KonumRizasi api={api} riza={riza} surum={meta.riza_surumu} onDegisti={setRiza} />
        </Suspense>
      )}
      <div className="flex items-center gap-2">
        <Button size="icon" variant="ghost" className="h-11 w-11" onClick={() => setGun(gunEkle(gun, -1))} aria-label={t('sahaServisi.pano.onceki')}>
          <ChevronLeft className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <div className="min-w-0 flex-1 text-center">
          <p className="text-base font-semibold" data-testid="saha-islerim-gun">
            {bugunMu ? t('sahaServisi.islerim.bugun') : gunYaz(gun, dil, true)}
          </p>
          {bugunMu && <p className="text-xs text-muted-foreground">{gunYaz(gun, dil, true)}</p>}
        </div>
        <Button size="icon" variant="ghost" className="h-11 w-11" onClick={() => setGun(gunEkle(gun, 1))} aria-label={t('sahaServisi.pano.sonraki')}>
          <ChevronRight className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <Button size="icon" variant="ghost" className="h-11 w-11" onClick={() => void yukle()} aria-label={t('sahaServisi.yenile')}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {hata && (
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {veri === null ? (
        <Yukleniyor />
      ) : !veri.kayitli ? (
        <div className={`${KART} p-6`}>
          <Bos testid="saha-islerim-kayitsiz">{t('sahaServisi.islerim.kayitliDegil')}</Bos>
        </div>
      ) : (
        <>
          {veri.bugun.length === 0 ? (
            <div className={`${KART} p-4`}>
              <Bos testid="saha-islerim-bos">{t('sahaServisi.islerim.bos')}</Bos>
            </div>
          ) : (
            <ul className="space-y-3" data-testid="saha-islerim-liste">
              {veri.bugun.map((x) => (
                <IsKarti key={x.id} is={x} dil={dil} saatGoster onAc={() => setSecili(x.id)} />
              ))}
            </ul>
          )}
          {veri.diger.length > 0 && (
            <section>
              <h3 className="mb-2 mt-2 text-sm font-semibold text-muted-foreground">{t('sahaServisi.islerim.diger')}</h3>
              <ul className="space-y-3">
                {veri.diger.map((x) => (
                  <IsKarti key={x.id} is={x} dil={dil} onAc={() => setSecili(x.id)} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function IsKarti({ is, dil, onAc, saatGoster }: { is: IsOzeti; dil: string; onAc: () => void; saatGoster?: boolean }) {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        onClick={onAc}
        className={`${KART} flex w-full items-stretch gap-3 p-4 text-start transition-colors hover:border-purple-400/40 active:bg-white/[0.06]`}
        data-testid="saha-is-karti"
        data-is-id={is.id}
      >
        <div className="flex w-14 flex-none flex-col items-center justify-center rounded-xl bg-white/[0.05] text-center">
          <Clock className="mb-0.5 h-4 w-4 text-purple-300" aria-hidden="true" />
          <span className="text-sm font-semibold tabular-nums" dir="ltr">
            {is.plan_bas ? (saatGoster ? saatYaz(is.plan_bas, dil) : tarihSaat(is.plan_bas, dil).split(' ').slice(0, 2).join(' ')) : '—'}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <DurumRozeti durum={is.durum} />
            <OncelikRozeti oncelik={is.oncelik} />
            <span className="text-[11px] text-muted-foreground">{t(`sahaServisi.tur.${is.tur}`)}</span>
          </div>
          <p className="mt-1 truncate text-base font-semibold">{is.baslik}</p>
          <p className="truncate text-sm text-white/80">{is.musteri_ad}</p>
          {is.adres && (
            <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground">
              <MapPin className="h-3.5 w-3.5 flex-none" aria-hidden="true" />
              <span className="truncate">{is.adres}</span>
            </p>
          )}
        </div>
        <ChevronRight className="h-5 w-5 flex-none self-center text-muted-foreground rtl:rotate-180" aria-hidden="true" />
      </button>
    </li>
  );
}
