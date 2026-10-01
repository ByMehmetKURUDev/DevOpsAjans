import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RotateCcw, Search, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  aramaIcinSadelestir,
  aramayaUyar,
  eldekiListe,
  listeyiGetir,
  type KaynakListesi,
} from '@/lib/kaynaklar';
import { KAYNAKLAR_SEO } from '../../../prerender/kaynaklar-seo.js';
import { kaynakYolu } from '../../../prerender/kaynaklar-veri.js';
import { PAGE_SEO_KEYS } from '../../../prerender/site.js';
import { KaynakCagrisi, KaynakKarti, paneldenSeo, useIcerikDili, useSayfaBasi } from './ortak';

/**
 * Kaynaklar — Mehmet KURU'nun kullandığı ve önerdiği yapay zekâ araçları,
 * beceriler ve açık kaynak projeler.
 *
 * Arama ve kategori süzgeci istemcide, eldeki liste üzerinde çalışıyor:
 * liste küçük (onlarca kayıt) ve her tuşta ağa gitmek gereksiz. Liste
 * prerender'da gömülü geliyor; API'den tazelenince yalnız değiştiyse
 * yeniden çiziliyor.
 */

const ISKELET_SAYISI = 6;

export default function KaynaklarListesi() {
  const { t } = useTranslation();
  const dil = useIcerikDili();
  const { pathname } = useLocation();
  const [liste, setListe] = useState<KaynakListesi | null>(() => eldekiListe(pathname, dil));
  const [hata, setHata] = useState(false);
  const [deneme, setDeneme] = useState(0);
  const [arama, setArama] = useState('');
  const [kategori, setKategori] = useState('hepsi');

  useEffect(() => {
    const eldeki = eldekiListe(pathname, dil);
    if (eldeki) setListe(eldeki);
    setHata(false);
    const kesici = new AbortController();
    listeyiGetir(dil, kesici.signal)
      .then((yeni) =>
        setListe((onceki) => (onceki && JSON.stringify(onceki) === JSON.stringify(yeni) ? onceki : yeni)),
      )
      .catch(() => {
        if (!kesici.signal.aborted && !eldeki) setHata(true);
      });
    return () => kesici.abort();
  }, [dil, pathname, deneme]);

  const seo = KAYNAKLAR_SEO[dil] ?? KAYNAKLAR_SEO.tr;
  useSayfaBasi({
    baslik: paneldenSeo(PAGE_SEO_KEYS.kaynaklar.title, dil, seo.title),
    aciklama: paneldenSeo(PAGE_SEO_KEYS.kaynaklar.description, dil, seo.description),
    yol: kaynakYolu(dil),
    diller: (d) => kaynakYolu(d),
  });

  const kategoriAdlari = useMemo(
    () => Object.fromEntries((liste?.kategoriler ?? []).map((c) => [c.anahtar, c.ad])) as Record<string, string>,
    [liste],
  );
  const doluKategoriler = useMemo(() => (liste?.kategoriler ?? []).filter((c) => c.sayi > 0), [liste]);
  const kelimeler = useMemo(() => aramaIcinSadelestir(arama).split(/\s+/).filter(Boolean), [arama]);
  const gorunen = useMemo(
    () =>
      (liste?.kaynaklar ?? []).filter(
        (k) =>
          (kategori === 'hepsi' || k.kategori === kategori) &&
          aramayaUyar(k, kelimeler, kategoriAdlari[k.kategori] ?? ''),
      ),
    [liste, kategori, kelimeler, kategoriAdlari],
  );
  const suzgecVar = kategori !== 'hepsi' || kelimeler.length > 0;

  const temizle = () => {
    setArama('');
    setKategori('hepsi');
  };

  const cip = 'rounded-full border px-4 py-2 text-sm font-semibold transition-colors';

  return (
    <div className="pt-32 pb-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <header className="mx-auto mb-10 max-w-3xl text-center">
          <p className="mb-4 text-xs uppercase tracking-[0.3em] text-primary">{t('kaynaklar.etiket')}</p>
          <h1 className="mb-4 text-4xl font-bold md:text-5xl">
            {t('kaynaklar.baslik')} <span className="gradient-text">{t('kaynaklar.baslikVurgu')}</span>
          </h1>
          <p className="text-muted-foreground">{t('kaynaklar.giris')}</p>
        </header>

        {/* Arama */}
        <div className="mx-auto mb-6 max-w-xl">
          <label htmlFor="kaynak-ara" className="sr-only">
            {t('kaynaklar.araEtiket')}
          </label>
          {/* Simge ve temizle düğmesi akışta (mutlak konum yok): RTL'de kendiliğinden yer değiştiriyor. */}
          <div className="flex h-12 items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 transition-colors focus-within:border-purple-400">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <input
              id="kaynak-ara"
              // type="search" değil: Chromium kendi temizle düğmesini de ekliyor, iki çarpı oluyordu.
              type="text"
              role="searchbox"
              enterKeyHint="search"
              value={arama}
              onChange={(e) => setArama(e.target.value)}
              placeholder={t('kaynaklar.araYerTutucu')}
              autoComplete="off"
              className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            {arama && (
              <button
                type="button"
                onClick={() => setArama('')}
                aria-label={t('kaynaklar.temizle')}
                className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        {/* Kategori çipleri */}
        {doluKategoriler.length > 1 && (
          <div
            className="mb-10 flex flex-wrap items-center justify-center gap-2"
            role="group"
            aria-label={t('kaynaklar.kategoriSecimi')}
          >
            {[{ anahtar: 'hepsi', ad: t('kaynaklar.tumu'), sayi: liste?.kaynaklar.length ?? 0 }, ...doluKategoriler].map(
              (c) => (
                <button
                  key={c.anahtar}
                  type="button"
                  data-kategori={c.anahtar}
                  onClick={() => setKategori(c.anahtar)}
                  aria-pressed={kategori === c.anahtar}
                  className={`${cip} ${
                    kategori === c.anahtar
                      ? 'border-purple-400 bg-purple-500/20 text-foreground'
                      : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-purple-500/40 hover:text-foreground'
                  }`}
                >
                  {c.ad} <span className="ms-1 text-xs opacity-70">{c.sayi}</span>
                </button>
              ),
            )}
          </div>
        )}

        {/* Yükleniyor: kart iskeletleri (yerleşim kaymasın) */}
        {liste === null && !hata && (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label={t('kaynaklar.yukleniyor')}>
            {Array.from({ length: ISKELET_SAYISI }, (_, i) => (
              <div key={i} className="h-40 animate-pulse rounded-2xl border border-white/10 bg-white/[0.03]" />
            ))}
          </div>
        )}

        {liste === null && hata && (
          <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-12 text-center">
            <p className="mb-4 text-muted-foreground">{t('kaynaklar.hata')}</p>
            <Button variant="outline" onClick={() => setDeneme((n) => n + 1)} className="gap-2 border-white/20">
              <RotateCcw className="h-4 w-4" aria-hidden="true" /> {t('kaynaklar.tekrarDene')}
            </Button>
          </div>
        )}

        {liste !== null && (
          <>
            <p className="mb-4 text-sm text-muted-foreground" aria-live="polite" data-sonuc-sayisi={gorunen.length}>
              {t('kaynaklar.sonucSayisi', { sayi: gorunen.length })}
            </p>

            {liste.kaynaklar.length === 0 ? (
              <p className="rounded-2xl border border-white/10 bg-white/[0.03] px-6 py-12 text-center text-muted-foreground">
                {t('kaynaklar.bos')}
              </p>
            ) : gorunen.length === 0 ? (
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-6 py-12 text-center">
                <p className="mb-4 text-muted-foreground">{t('kaynaklar.sonucYok')}</p>
                {suzgecVar && (
                  <Button variant="outline" onClick={temizle} className="border-white/20">
                    {t('kaynaklar.temizle')}
                  </Button>
                )}
              </div>
            ) : (
              // Kartlar ızgaranın doğrudan çocuğu: Modern görünümün sıralı kart tonları buna bakıyor.
              <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3" data-kaynak-listesi>
                {gorunen.map((k) => (
                  <KaynakKarti key={k.slug} k={k} dil={dil} kategoriAdi={kategoriAdlari[k.kategori] ?? k.kategori} />
                ))}
              </div>
            )}
          </>
        )}

        <div className="mt-16">
          <KaynakCagrisi dil={dil} />
        </div>
      </div>
    </div>
  );
}
