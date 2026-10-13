import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ExternalLink, MapPinOff, Monitor, RefreshCw } from 'lucide-react';

import OsmHarita from '@/components/harita/OsmHarita';
import { hataMetni, saatYaz, type Komuta, type SahaApi } from '@/lib/sahaServisi';
import { DURUM_RENK, KART, Yukleniyor } from './ortak';
import { DURUM_HEX, isaretler, rotalar } from './harita';

/**
 * Faz 11E — Sevk panosu › Harita: günün işleri gerçek haritada (OpenStreetMap), teknisyen başına ziyaret
 * sırası çizgisi, yanda iş listesi ve teknisyen süzgeci. Veri: GET /komuta (60 sn'de bir, sekme görünürken).
 * Konumu olmayan işler listede "konum yok" rozetiyle; adres müşteri kartından haritada işaretleniyor.
 */
export default function HaritaGorunumu({
  api,
  gun,
  onAc,
  onKomuta,
}: {
  api: SahaApi;
  gun: string;
  onAc: (id: number) => void;
  onKomuta: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<Komuta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [secili, setSecili] = useState<number | null>(null);
  const [teknisyen, setTeknisyen] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setVeri(await api.komuta(gun));
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, gun, t]);

  useEffect(() => {
    void yukle();
    const z = window.setInterval(() => {
      if (document.visibilityState === 'visible') void yukle();
    }, 60_000);
    return () => window.clearInterval(z);
  }, [yukle]);

  const renkler = useMemo(() => new Map((veri?.teknisyenler || []).map((x) => [x.id, x.renk])), [veri]);
  const etiketle = useCallback(
    (x: Komuta['isler'][number]) => `${x.plan_bas ? saatYaz(x.plan_bas, dil) : ''} · ${x.baslik} — ${x.musteri_ad}`,
    [dil]
  );
  const pinler = useMemo(() => (veri ? isaretler(veri.isler, etiketle, teknisyen) : []), [veri, etiketle, teknisyen]);
  const cizgiler = useMemo(() => (veri ? rotalar(veri.isler, renkler, teknisyen) : []), [veri, renkler, teknisyen]);
  const liste = useMemo(
    () =>
      (veri?.isler || [])
        .filter((x) => teknisyen == null || x.teknisyenler.some((y) => y.id === teknisyen))
        .slice()
        .sort((a, b) => (a.plan_bas || '').localeCompare(b.plan_bas || '') || a.id - b.id),
    [veri, teknisyen]
  );

  if (!veri) return hata ? <p className="text-sm text-red-300" role="alert">{hata}</p> : <Yukleniyor />;

  const s = veri.sayilar;
  const kutular: [string, number, string][] = [
    ['toplam', s.toplam, 'text-white'],
    ['tamamlanan', s.tamamlanan, 'text-emerald-300'],
    ['yolda', s.yolda, 'text-amber-300'],
    ['iste', s.iste, 'text-orange-300'],
    ['bekleyen', s.bekleyen, 'text-violet-300'],
    ['geciken', s.geciken, s.geciken ? 'text-red-300' : 'text-white/70'],
  ];

  return (
    <div className="space-y-3" data-testid="saha-harita">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {kutular.map(([a, n, renk]) => (
          <div key={a} className={`${KART} px-3 py-2`} data-testid={`saha-harita-sayi-${a}`}>
            <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{t(`sahaServisi.harita.sayi.${a}`)}</p>
            <p className={`font-mono text-xl font-semibold tabular-nums ${renk}`}>{n}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-2">
          <OsmHarita
            isaretler={pinler}
            cizgiler={cizgiler}
            secili={secili}
            onSec={(id) => setSecili(Number(id))}
            sigdirAnahtari={`${veri.gun}-${teknisyen ?? 'hepsi'}-${pinler.length}`}
            className="h-[440px] border border-white/10 lg:h-[560px]"
            etiket={t('sahaServisi.harita.haritaEtiket')}
            testid="saha-harita-osm"
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            {(['planlandi', 'yolda', 'iste', 'tamamlandi', 'ertelendi'] as const).map((d) => (
              <span key={d} className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: DURUM_HEX[d] }} aria-hidden="true" />
                {t(`sahaServisi.durum.${d}`)}
              </span>
            ))}
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-red-500/40" aria-hidden="true" />
              {t('sahaServisi.oncelik.acil')}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0 w-5 border-t-2 border-dashed border-cyan-300" aria-hidden="true" />
              {t('sahaServisi.harita.siraCizgisi')}
            </span>
          </div>
          {s.konumsuz > 0 && (
            <p className="flex items-start gap-2 rounded-lg border border-amber-400/25 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-100/90" data-testid="saha-harita-konumsuz">
              <MapPinOff className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden="true" />
              {t('sahaServisi.harita.konumsuzIpucu', { sayi: s.konumsuz })}
            </p>
          )}
        </div>

        <aside className={`${KART} flex min-h-0 flex-col p-3 lg:max-h-[640px]`} aria-label={t('sahaServisi.harita.listeBaslik')}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t('sahaServisi.harita.listeBaslik')}</h3>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => void yukle()}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-white/5 hover:text-white"
                aria-label={t('sahaServisi.yenile')}
                title={t('sahaServisi.yenile')}
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={onKomuta}
                className="inline-flex items-center gap-1.5 rounded-md border border-cyan-400/40 bg-cyan-500/10 px-2 py-1 text-xs font-medium text-cyan-100 hover:bg-cyan-500/20"
                data-testid="saha-komuta-ac"
              >
                <Monitor className="h-3.5 w-3.5" aria-hidden="true" />
                {t('sahaServisi.komuta.ac')}
              </button>
            </div>
          </div>
          <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label={t('sahaServisi.harita.teknisyenSuzgeci')}>
            <button
              type="button"
              aria-pressed={teknisyen == null}
              onClick={() => setTeknisyen(null)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] ${teknisyen == null ? 'border-cyan-300/60 bg-cyan-500/15 text-white' : 'border-white/10 text-muted-foreground hover:text-white'}`}
            >
              {t('sahaServisi.harita.hepsi')}
            </button>
            {veri.teknisyenler.map((x) => (
              <button
                key={x.id}
                type="button"
                aria-pressed={teknisyen === x.id}
                onClick={() => setTeknisyen(teknisyen === x.id ? null : x.id)}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] ${teknisyen === x.id ? 'border-cyan-300/60 bg-cyan-500/15 text-white' : 'border-white/10 text-muted-foreground hover:text-white'}`}
                data-testid={`saha-harita-teknisyen-${x.id}`}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: x.renk }} aria-hidden="true" />
                {x.ad}
              </button>
            ))}
          </div>
          {liste.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">{t('sahaServisi.harita.isYok')}</p>
          ) : (
            <ul className="-mx-1 min-h-0 flex-1 space-y-1 overflow-y-auto px-1">
              {liste.map((x) => (
                <li
                  key={x.id}
                  className={`group flex items-start gap-1 rounded-lg border transition-colors ${
                    secili === x.id ? 'border-cyan-300/50 bg-cyan-500/10' : 'border-transparent hover:bg-white/[0.04]'
                  }`}
                  data-testid="saha-harita-is"
                  data-is-id={x.id}
                >
                  <button
                    type="button"
                    aria-pressed={secili === x.id}
                    onClick={() => setSecili(secili === x.id ? null : x.id)}
                    className="flex min-w-0 flex-1 items-start gap-2 px-2 py-1.5 text-start text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 rounded-lg"
                  >
                    <span
                      className={`mt-1 h-2.5 w-2.5 flex-none rounded-full ${x.oncelik === 'acil' && x.durum !== 'tamamlandi' ? 'ring-2 ring-red-500/60' : ''}`}
                      style={{ background: x.oncelik === 'acil' && x.durum !== 'tamamlandi' ? '#ef4444' : DURUM_HEX[x.durum] }}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="font-mono tabular-nums text-white/80" dir="ltr">
                          {x.plan_bas ? saatYaz(x.plan_bas, dil) : '—'}
                        </span>
                        <span className="truncate font-medium text-white">{x.baslik}</span>
                      </span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {x.musteri_ad}
                        {x.teknisyenler.length ? ` · ${x.teknisyenler.map((y) => y.ad).join(', ')}` : ''}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-1">
                        <span className={`rounded-full border px-1.5 py-px text-[10px] ${DURUM_RENK[x.durum]}`}>{t(`sahaServisi.durum.${x.durum}`)}</span>
                        {x.gecikti && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-red-400/40 bg-red-500/15 px-1.5 py-px text-[10px] text-red-200">
                            <AlertTriangle className="h-2.5 w-2.5" aria-hidden="true" />
                            {t('sahaServisi.harita.gecikti')}
                          </span>
                        )}
                        {!x.nokta && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-1.5 py-px text-[10px] text-muted-foreground">
                            <MapPinOff className="h-2.5 w-2.5" aria-hidden="true" />
                            {t('sahaServisi.harita.konumYok')}
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onAc(x.id)}
                    className="m-1 rounded p-1 text-muted-foreground opacity-70 hover:bg-white/10 hover:text-white group-hover:opacity-100 focus-visible:opacity-100"
                    aria-label={t('sahaServisi.harita.isiAc', { no: x.no })}
                    title={t('sahaServisi.harita.isiAc', { no: x.no })}
                    data-testid="saha-harita-is-ac"
                  >
                    <ExternalLink className="h-3.5 w-3.5 rtl:-scale-x-100" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}
