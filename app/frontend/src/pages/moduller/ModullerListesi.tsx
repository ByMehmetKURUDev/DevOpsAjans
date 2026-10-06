import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { VITRIN } from '@/lib/modulVitrini';
import { modullerYolu } from '../../../prerender/moduller-veri.js';
import { PAGE_SEO_KEYS } from '../../../prerender/site.js';
import { paneldenSeo } from '../kaynaklar/ortak';
import {
  ModulIkonu,
  ModulKarti,
  PaketKarti,
  VitrinCagrisi,
  modulAdi,
  useSayfaBasi,
  useVitrinDili,
  useVitrinFiyatlari,
} from './ortak';

/**
 * Modül vitrini (Faz 4V): sektör paketleri, kategoriye göre modüller,
 * yakında gelenler ve her portalda zaten olanlar.
 *
 * Hangi modülün burada olduğu modül kaydından türetiliyor (bkz.
 * `services/modul_vitrini.py`); bu sayfa listeyi elle tutmuyor.
 * Ağır görsel ya da animasyon yok: ikonlar SVG, kartlar düz.
 */
export default function ModullerListesi() {
  const { t } = useTranslation();
  const dil = useVitrinDili();
  const fiyatlar = useVitrinFiyatlari();

  const baslik = paneldenSeo(PAGE_SEO_KEYS.moduller.title, dil, t('modulVitrini.seo.baslik'));
  const aciklama = paneldenSeo(PAGE_SEO_KEYS.moduller.description, dil, t('modulVitrini.seo.aciklama'));
  useSayfaBasi({ baslik, aciklama, yol: modullerYolu(dil), diller: (d) => modullerYolu(d) });

  const kategoriler = useMemo(
    () => VITRIN.kategoriler.map((k) => ({ k, moduller: VITRIN.moduller.filter((m) => m.kategori === k) })),
    [],
  );

  const cip =
    'inline-block rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-sm font-semibold text-muted-foreground transition-colors hover:border-purple-500/40 hover:text-foreground';

  return (
    <div className="pt-32 pb-24" data-modul-vitrini>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <header className="mx-auto mb-10 max-w-3xl text-center">
          <p className="mb-4 text-xs uppercase tracking-[0.3em] text-primary">{t('modulVitrini.liste.etiket')}</p>
          <h1 className="mb-4 text-4xl font-bold md:text-5xl">
            {t('modulVitrini.liste.baslik')} <span className="gradient-text">{t('modulVitrini.liste.baslikVurgu')}</span>
          </h1>
          <p className="text-muted-foreground">{t('modulVitrini.liste.giris')}</p>
        </header>

        {/* Bölüm bağlantıları (çapa; JS gerekmiyor) */}
        <nav className="mb-14 flex flex-wrap items-center justify-center gap-2" aria-label={t('modulVitrini.liste.gezinme')}>
          <a href="#paketler" className={cip}>
            {t('modulVitrini.liste.paketlerBaslik')}
          </a>
          {kategoriler.map(({ k }) => (
            <a key={k} href={`#kategori-${k}`} className={cip} data-kategori-baglanti={k}>
              {t(`modul.kategori.${k}`)}
            </a>
          ))}
        </nav>

        {/* Sektör paketleri */}
        <section id="paketler" className="mb-20 scroll-mt-28" aria-labelledby="paketler-baslik" data-sektor-paketleri>
          <div className="mb-8 max-w-3xl">
            <h2 id="paketler-baslik" className="text-3xl font-bold">
              {t('modulVitrini.liste.paketlerBaslik')}
            </h2>
            <p className="mt-3 text-muted-foreground">{t('modulVitrini.liste.paketlerGiris')}</p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {VITRIN.paketler.map((p) => (
              <PaketKarti key={p.anahtar} p={p} dil={dil} />
            ))}
          </div>
        </section>

        {/* Kategoriye göre modüller */}
        {kategoriler.map(({ k, moduller }) => (
          <section
            key={k}
            id={`kategori-${k}`}
            className="mb-16 scroll-mt-28"
            aria-labelledby={`kategori-${k}-baslik`}
            data-kategori-bolumu={k}
          >
            <div className="mb-6 max-w-3xl">
              <h2 id={`kategori-${k}-baslik`} className="text-2xl font-bold">
                {t(`modul.kategori.${k}`)}
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">{t(`modulVitrini.kategori.${k}`)}</p>
            </div>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {moduller.map((m) => (
                <ModulKarti key={m.anahtar} m={m} dil={dil} fiyatlar={fiyatlar} />
              ))}
            </div>
          </section>
        ))}

        {/* Yakında — ayrıntı sayfası yok */}
        {VITRIN.yakinda.length > 0 && (
          <section className="mb-16" aria-labelledby="yakinda-baslik" data-yakinda>
            <h2 id="yakinda-baslik" className="mb-2 text-2xl font-bold">
              {t('modulVitrini.liste.yakindaBaslik')}
            </h2>
            <p className="mb-6 max-w-3xl text-sm text-muted-foreground">{t('modulVitrini.liste.yakindaGiris')}</p>
            <ul className="grid gap-4 md:grid-cols-2">
              {VITRIN.yakinda.map((m) => (
                <li
                  key={m.anahtar}
                  data-yakinda-modul={m.anahtar}
                  className="flex min-w-0 gap-4 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-5"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/5 text-muted-foreground">
                    <ModulIkonu ad={m.ikon} />
                  </span>
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      {modulAdi(t, m.anahtar)}
                      <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
                        {t('modulVitrini.liste.yakindaRozet')}
                      </span>
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">{t(`modul.m.${m.anahtar}.aciklama`)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Her portalda gelenler — ad olarak */}
        {VITRIN.temeller.length > 0 && (
          <section className="mb-16" aria-labelledby="temeller-baslik" data-temeller>
            <h2 id="temeller-baslik" className="mb-2 text-2xl font-bold">
              {t('modulVitrini.liste.temellerBaslik')}
            </h2>
            <p className="mb-6 max-w-3xl text-sm text-muted-foreground">{t('modulVitrini.liste.temellerGiris')}</p>
            <ul className="flex flex-wrap gap-2">
              {VITRIN.temeller.map((m) => (
                <li
                  key={m.anahtar}
                  className="inline-flex max-w-full items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm"
                >
                  <ModulIkonu ad={m.ikon} className="h-4 w-4 shrink-0 text-purple-300" />
                  <span className="truncate">{modulAdi(t, m.anahtar)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <VitrinCagrisi dil={dil} />
      </div>
    </div>
  );
}
