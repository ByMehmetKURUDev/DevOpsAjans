import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarRange, Download, FileText, GitBranch, ListChecks, Lock, Plus, RefreshCw, Target } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { AltDugme, DIS_DUGME, HataSatiri, KART, SECIM, Yukleniyor } from '@/components/hedefler/ortak';
import { donemAdi, hataMetni, okrApi, type Donem, type Meta, type OkrMod } from '@/lib/okr';

const ListeBolumu = lazy(() => import('@/components/hedefler/Liste'));
const AgacBolumu = lazy(() => import('@/components/hedefler/Agac'));
const KapanisBolumu = lazy(() => import('@/components/hedefler/Kapanis'));
const DonemFormu = lazy(() => import('@/components/hedefler/Formlar').then((m) => ({ default: m.DonemFormu })));
const Ayrinti = lazy(() => import('@/components/hedefler/Ayrinti'));

export type Bolum = 'liste' | 'agac' | 'kapanis';
const BOLUMLER: { anahtar: Bolum; ikon: typeof Target }[] = [
  { anahtar: 'liste', ikon: ListChecks },
  { anahtar: 'agac', ikon: GitBranch },
  { anahtar: 'kapanis', ikon: Lock },
];

function adresParametresi(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

/**
 * Faz 6O — "Hedefler" sekmesi (OKR): dönem seçimi; bölümler alt gezinmede (menüde TEK sekme) — dönem listesi (ilerleme
 * çubukları, beklenen ilerleme çizgisi), hizalama ağacı, dönem kapanışı. Hedef ayrıntısı (KR'ler, check-in geçmişi küçük
 * grafik, odak sayacı) pencerede. Yönetici panelinde ajansın KENDİ OKR'ları (hedef bir müşteriye bağlanıp paylaşılabilir);
 * müşteri panelinde etkin hesabın OKR'ları. `hedefler_okur` izni yalnız okur. Açılışta dönemin otomatik KR'leri yenilenir.
 */
export default function Hedefler({ mod }: { mod: OkrMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const api = useMemo(() => okrApi(mod), [mod]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [donemId, setDonemId] = useState<number | null>(null);
  const [bolum, setBolum] = useState<Bolum>(() => {
    const b = adresParametresi('bolum') as Bolum | null;
    return b && BOLUMLER.some((x) => x.anahtar === b) ? b : 'liste';
  });
  const [surum, setSurum] = useState(0);
  const [donemFormu, setDonemFormu] = useState<Donem | 'yeni' | null>(null);
  const [ayrintiId, setAyrintiId] = useState<number | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const yenilenen = useRef<Set<number>>(new Set());

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const m = await api.meta();
      setMeta(m);
      setDonemId((once) => (once && m.donemler.some((d) => d.id === once) ? once : m.etkin_donem_id));
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const donem = meta?.donemler.find((d) => d.id === donemId) || null;

  // Açılışta (dönem başına bir kez) otomatik KR kaynaklarını yenile: sunucu uyurken zamanlı iş gecikebilir.
  useEffect(() => {
    if (!meta || !donem || meta.okur || donem.durum === 'kapandi' || yenilenen.current.has(donem.id)) return;
    yenilenen.current.add(donem.id);
    api
      .donemYenile(donem.id)
      .then((r) => r.degisen > 0 && setSurum((s) => s + 1))
      .catch(() => undefined);
  }, [api, meta, donem]);

  const yenile = useCallback(() => {
    setSurum((s) => s + 1);
    void yukle();
  }, [yukle]);

  const disaAktar = async (tur: 'pdf' | 'csv') => {
    if (!donem) return;
    setMesgul(true);
    try {
      await (tur === 'pdf' ? api.raporPdf(donem.id, dil) : api.raporCsv(donem.id, dil));
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const ortak = meta && donem ? { api, meta, donem, surum, yenile, ac: setAyrintiId } : null;
  return (
    <section aria-labelledby="okr-baslik" data-testid="okr-sekmesi" data-mod={mod}>
      <div className="mb-5">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="okr-baslik">
          <Target className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('hedefler.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('hedefler.aciklamaYonetici') : t('hedefler.aciklama')}</p>
      </div>
      <HataSatiri hata={hata} />
      {meta?.okur && (
        <p className="mb-3 text-xs text-muted-foreground" data-testid="okr-okur-not">
          {t('hedefler.okurNot')}
        </p>
      )}
      {!meta ? (
        !hata && <Yukleniyor />
      ) : (
        <>
          <div className={`${KART} mb-4 flex flex-wrap items-center gap-2 p-3`}>
            <label className="flex min-w-0 flex-1 items-center gap-2 text-sm sm:min-w-[16rem]">
              <CalendarRange className="h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
              <span className="sr-only">{t('hedefler.donem.sec')}</span>
              <select className={SECIM} value={donemId ?? ''} onChange={(e) => setDonemId(Number(e.target.value) || null)} data-testid="okr-donem-sec">
                {meta.donemler.length === 0 && <option value="">{t('hedefler.donem.yok')}</option>}
                {meta.donemler.map((d) => (
                  <option key={d.id} value={d.id}>
                    {donemAdi(t, d, dil)}
                    {d.etkin ? ` · ${t('hedefler.donem.etkin')}` : ''}
                    {d.durum === 'kapandi' ? ` · ${t('hedefler.donem.kapandi')}` : ''}
                  </option>
                ))}
              </select>
            </label>
            {!meta.okur && (
              <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setDonemFormu('yeni')} data-testid="okr-donem-yeni">
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('hedefler.donem.yeni')}
              </Button>
            )}
            {donem && !meta.okur && (
              <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setDonemFormu(donem)} data-testid="okr-donem-duzenle">
                {t('hedefler.donem.duzenle')}
              </Button>
            )}
            {donem && (
              <>
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} disabled={mesgul} onClick={() => void disaAktar('pdf')} data-testid="okr-pdf">
                  <FileText className="h-4 w-4" aria-hidden="true" />
                  PDF
                </Button>
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} disabled={mesgul} onClick={() => void disaAktar('csv')} data-testid="okr-csv">
                  <Download className="h-4 w-4" aria-hidden="true" />
                  CSV
                </Button>
                <Button type="button" size="sm" variant="ghost" className="gap-1.5" onClick={yenile} aria-label={t('hedefler.ortak.yenile')}>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                </Button>
              </>
            )}
          </div>
          {!donem ? (
            <div className={`${KART} p-8 text-center`} data-testid="okr-donem-bos">
              <p className="mb-3 text-sm text-muted-foreground">{t('hedefler.donem.ilkAciklama')}</p>
              {!meta.okur && (
                <Button type="button" onClick={() => setDonemFormu('yeni')} className="gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="okr-donem-ilk">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('hedefler.donem.ilk')}
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('hedefler.baslik')}>
                {BOLUMLER.map(({ anahtar, ikon: Ikon }) => (
                  <AltDugme key={anahtar} secili={bolum === anahtar} onClick={() => setBolum(anahtar)} testid={anahtar}>
                    <Ikon className="h-4 w-4" aria-hidden="true" />
                    {t(`hedefler.bolum.${anahtar}`)}
                  </AltDugme>
                ))}
              </div>
              <Suspense fallback={<Yukleniyor />}>
                {ortak && (bolum === 'liste' ? <ListeBolumu {...ortak} /> : bolum === 'agac' ? <AgacBolumu {...ortak} /> : <KapanisBolumu {...ortak} />)}
              </Suspense>
            </>
          )}
        </>
      )}
      <Suspense fallback={null}>
        {meta && donemFormu && (
          <DonemFormu
            api={api}
            donem={donemFormu === 'yeni' ? null : donemFormu}
            onKapat={() => setDonemFormu(null)}
            onKaydet={(d) => {
              setDonemFormu(null);
              setDonemId(d.id);
              yenile();
            }}
          />
        )}
        {meta && ayrintiId !== null && (
          <Ayrinti
            api={api}
            meta={meta}
            hedefId={ayrintiId}
            onKapat={() => setAyrintiId(null)}
            onDegisti={() => setSurum((s) => s + 1)}
            ac={setAyrintiId}
          />
        )}
      </Suspense>
    </section>
  );
}
