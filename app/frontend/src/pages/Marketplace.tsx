import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Blocks,
  Boxes,
  Clock,
  ExternalLink,
  Globe,
  Layers,
  Loader2,
  ShoppingCart,
  Wrench,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  KATEGORILER,
  fiyatMetni,
  kategoriEtiketi,
  ozellikler,
  urunleriGetir,
  type MarketplaceUrunu,
} from '@/lib/marketplace';

/**
 * Marketplace — raftan satılan hazır ürünler.
 *
 * Paketler bloğundan (PricingPlans) ayrı: orası saatlik/aylık hizmet,
 * burası hazır website, e-ticaret ve SaaS paketleri ile araçlar ve
 * eklentiler.
 *
 * Ürünler yönetim panelinden giriliyor ve çalışma anında çekiliyor;
 * kodda gömülü örnek ürün YOK. Katalog boşken sayfa uydurma kart
 * göstermiyor, "henüz ürün eklenmedi" deyip iletişime yönlendiriyor --
 * sahte ürün gösteren bir vitrin, ziyaretçi tıkladığı anda güveni
 * götürür.
 *
 * Satın alma adımı mevcut teklif hunisine bağlı: ürün adı iletişim
 * sayfasına taşınıyor, oradan talep panele düşüyor.
 */

const KATEGORI_IKONU = {
  website: Globe,
  ecommerce: ShoppingCart,
  saas: Layers,
  tool: Wrench,
  plugin: Blocks,
} as const;

export default function Marketplace() {
  const { t } = useTranslation();
  const [urunler, setUrunler] = useState<MarketplaceUrunu[] | null>(null);
  const [secili, setSecili] = useState<string>('hepsi');

  useEffect(() => {
    const kontrol = new AbortController();
    void urunleriGetir(kontrol.signal).then(setUrunler);
    return () => kontrol.abort();
  }, []);

  // Panelde hangi kategorilerde ürün varsa yalnızca onlar sekme oluyor;
  // boş bir sekmeye tıklayıp "hiçbir şey yok" görmek can sıkıcı.
  const doluKategoriler = useMemo(() => {
    if (!urunler) return [];
    const mevcut = new Set(urunler.map((u) => u.category).filter(Boolean));
    return KATEGORILER.filter((k) => mevcut.has(k));
  }, [urunler]);

  const gosterilen = useMemo(() => {
    if (!urunler) return [];
    if (secili === 'hepsi') return urunler;
    return urunler.filter((u) => u.category === secili);
  }, [urunler, secili]);

  const sekme =
    'rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary';

  return (
    <div className="pt-32 pb-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Başlık */}
        <header className="text-center mb-12">
          <p className="text-xs uppercase tracking-[0.3em] text-primary mb-4">
            {t('marketplace.sectionTag')}
          </p>
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            {t('marketplace.title')}{' '}
            <span className="gradient-text">{t('marketplace.titleHighlight')}</span>
          </h1>
          <p className="text-muted-foreground max-w-2xl mx-auto">{t('marketplace.desc')}</p>
        </header>

        {/* Kategori sekmeleri */}
        {doluKategoriler.length > 1 && (
          <div className="mb-12 flex justify-center">
            <div
              className="inline-flex flex-wrap items-center justify-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1"
              role="group"
              aria-label={t('marketplace.kategoriSecimi')}
            >
              <button
                type="button"
                onClick={() => setSecili('hepsi')}
                aria-pressed={secili === 'hepsi'}
                className={`${sekme} ${
                  secili === 'hepsi'
                    ? 'bg-primary text-background'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t('marketplace.hepsi')}
              </button>
              {doluKategoriler.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setSecili(k)}
                  aria-pressed={secili === k}
                  className={`${sekme} ${
                    secili === k
                      ? 'bg-primary text-background'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t(kategoriEtiketi(k))}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Yükleniyor */}
        {urunler === null && (
          <p className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
            {t('marketplace.yukleniyor')}
          </p>
        )}

        {/* Katalog boş */}
        {urunler !== null && urunler.length === 0 && (
          <div className="mx-auto max-w-lg rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-12 text-center">
            <Boxes className="mx-auto mb-4 h-10 w-10 text-primary" aria-hidden="true" />
            <h2 className="mb-2 text-lg font-bold">{t('marketplace.bosBaslik')}</h2>
            <p className="mb-6 text-sm text-muted-foreground">{t('marketplace.bosAciklama')}</p>
            <Button asChild className="bg-primary text-background border-0 h-11">
              <Link to="/contact">
                {t('marketplace.bosCta')}
                <ArrowRight className="ms-2 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          </div>
        )}

        {/* Ürünler */}
        {gosterilen.length > 0 && (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {gosterilen.map((urun) => {
              const Ikon =
                KATEGORI_IKONU[urun.category as keyof typeof KATEGORI_IKONU] ?? Boxes;
              const fiyat = fiyatMetni(urun);
              const liste = ozellikler(urun).slice(0, 5);

              return (
                <article
                  key={urun.id}
                  className="flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] transition-colors hover:border-primary/40"
                >
                  {urun.image_url && (
                    <img
                      src={urun.image_url}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      className="h-40 w-full object-cover"
                    />
                  )}

                  <div className="flex flex-1 flex-col p-6">
                    <div className="mb-3 flex items-start gap-3">
                      <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-primary/15">
                        <Ikon className="h-4 w-4 text-primary" aria-hidden="true" />
                      </span>
                      <div className="min-w-0">
                        <h2 className="text-lg font-bold leading-tight">{urun.title}</h2>
                        {urun.category && (
                          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                            {t(kategoriEtiketi(urun.category), urun.category)}
                          </p>
                        )}
                      </div>
                      {urun.badge && (
                        <span className="ms-auto flex-none rounded-full bg-primary/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-primary">
                          {urun.badge}
                        </span>
                      )}
                    </div>

                    {urun.summary && (
                      <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
                        {urun.summary}
                      </p>
                    )}

                    {liste.length > 0 && (
                      <ul className="mb-4 space-y-1.5">
                        {liste.map((ozellik) => (
                          <li
                            key={ozellik}
                            className="flex gap-2 text-sm text-muted-foreground"
                          >
                            <span className="mt-2 h-1 w-1 flex-none rounded-full bg-primary" />
                            {ozellik}
                          </li>
                        ))}
                      </ul>
                    )}

                    {urun.delivery_time && (
                      <p className="mb-4 flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                        {urun.delivery_time}
                      </p>
                    )}

                    {/* Fiyat ve butonlar en altta hizalı dursun diye mt-auto */}
                    <div className="mt-auto">
                      <p className="mb-4 text-2xl font-bold">
                        {fiyat || (
                          <span className="text-base font-semibold text-muted-foreground">
                            {t('marketplace.fiyatAliniz')}
                          </span>
                        )}
                        {fiyat && urun.price_note && (
                          <span className="ms-2 text-xs font-normal text-muted-foreground">
                            {urun.price_note}
                          </span>
                        )}
                      </p>

                      <div className="flex flex-wrap gap-2">
                        <Button
                          asChild
                          className="flex-1 bg-primary text-background border-0 h-11"
                        >
                          <Link
                            to="/contact"
                            state={{ konu: urun.title, kaynak: 'marketplace' }}
                          >
                            {fiyat ? t('marketplace.satinAl') : t('marketplace.teklifIste')}
                          </Link>
                        </Button>
                        {urun.demo_url && (
                          <Button
                            asChild
                            variant="outline"
                            className="!bg-transparent !hover:bg-transparent border-white/20 h-11"
                          >
                            <a href={urun.demo_url} target="_blank" rel="noreferrer">
                              {t('marketplace.demo')}
                              <ExternalLink className="ms-1.5 h-3.5 w-3.5" aria-hidden="true" />
                            </a>
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {/* Seçili kategoride ürün yok (katalog dolu ama sekme boş) */}
        {urunler !== null && urunler.length > 0 && gosterilen.length === 0 && (
          <p className="py-16 text-center text-muted-foreground">
            {t('marketplace.kategoriBos')}
          </p>
        )}

        {/* Alt çağrı */}
        {urunler !== null && urunler.length > 0 && (
          <div className="mt-16 rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-10 text-center">
            <h2 className="mb-2 text-xl font-bold">{t('marketplace.ozelBaslik')}</h2>
            <p className="mb-6 text-sm text-muted-foreground">{t('marketplace.ozelAciklama')}</p>
            <Button asChild className="bg-primary text-background border-0 h-11">
              <Link to="/contact">
                {t('marketplace.ozelCta')}
                <ArrowRight className="ms-2 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
