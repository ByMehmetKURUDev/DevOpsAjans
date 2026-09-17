import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Yatırım getirisi hesaplayıcı.
 *
 * DÜRÜSTLÜK NOTU — bu bileşenin tasarımındaki tek önemli karar:
 * "hız iyileştirmesi dönüşümü şu kadar artırır" diye bir katsayı GÖMÜLMÜYOR.
 * Sektör çalışmalarından alınacak her katsayı ziyaretçinin işine uymayabilir
 * ve ona tutamayacağımız bir söz vermiş oluruz. Bunun yerine beklenen artışı
 * ziyaretçi kendisi seçiyor; biz yalnızca aritmetiği yapıyoruz. Ekranda da
 * bunun bir varsayım olduğu açıkça yazıyor.
 *
 * Paket ücreti panelden (`price_ecommerce`, SEO & Ads paketi) okunuyor;
 * geri ödeme süresi ona göre hesaplanıyor.
 */

const VARSAYILAN_SEO_ADS_UCRETI = 500;

export default function YatirimHesaplayici() {
  const { t, i18n } = useTranslation();
  const { settings } = useSiteSettings();

  const [ziyaretci, setZiyaretci] = useState(15000);
  const [donusum, setDonusum] = useState(1.5);
  const [sepet, setSepet] = useState(120);
  const [artis, setArtis] = useState(15);

  const aylikUcret =
    Number.parseInt(settings.price_ecommerce ?? '', 10) || VARSAYILAN_SEO_ADS_UCRETI;

  const hesap = useMemo(() => {
    const mevcutCiro = ziyaretci * (donusum / 100) * sepet;
    const yeniCiro = ziyaretci * ((donusum * (1 + artis / 100)) / 100) * sepet;
    const aylikFark = yeniCiro - mevcutCiro;
    const yillikFark = aylikFark * 12;
    /** Kaç ayda paket ücretini çıkarır? 0 artışta anlamsız olduğu için null. */
    const geriOdemeAy = aylikFark > 0 ? aylikUcret / aylikFark : null;
    return { mevcutCiro, yeniCiro, aylikFark, yillikFark, geriOdemeAy };
  }, [ziyaretci, donusum, sepet, artis, aylikUcret]);

  const paraBirimi = (n: number) =>
    `$${Math.round(n).toLocaleString(i18n.language === 'tr' ? 'tr-TR' : i18n.language)}`;
  const sayi = (n: number) =>
    n.toLocaleString(i18n.language === 'tr' ? 'tr-TR' : i18n.language);
  /** Ondalik ayraci dile gore: Turkce "%1,5", Ingilizce "%1.5". */
  const ondalik = (n: number) =>
    n.toLocaleString(i18n.language === 'tr' ? 'tr-TR' : i18n.language, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });

  const kaydirici =
    'h-2 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-primary';

  const satir = (
    id: string,
    etiket: string,
    deger: string,
    girdi: React.ReactNode,
  ) => (
    <div key={id}>
      <div className="mb-2 flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="text-sm text-muted-foreground">
          {etiket}
        </label>
        <span className="font-mono text-sm font-semibold text-foreground">{deger}</span>
      </div>
      {girdi}
    </div>
  );

  return (
    <section
      id="yatirim"
      className="alt-bolum relative py-20 md:py-28 border-t border-white/10"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">
            {t('yatirim.sectionTag')}
          </p>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold leading-tight">
            {t('yatirim.title')}{' '}
            <span className="gradient-text">{t('yatirim.titleHighlight')}</span>
          </h2>
          <p className="mt-5 text-muted-foreground leading-relaxed">{t('yatirim.desc')}</p>
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-5">
          {/* Girdiler */}
          <div className="glass rounded-2xl p-6 sm:p-8 lg:col-span-3">
            <div className="space-y-7">
              {satir(
                'yat-ziyaretci',
                t('yatirim.ziyaretci'),
                t('yatirim.kisi', { sayi: sayi(ziyaretci) }),
                <input
                  id="yat-ziyaretci"
                  type="range"
                  min={500}
                  max={200000}
                  step={500}
                  value={ziyaretci}
                  onChange={(e) => setZiyaretci(Number(e.target.value))}
                  className={kaydirici}
                />,
              )}

              {satir(
                'yat-donusum',
                t('yatirim.donusum'),
                `%${ondalik(donusum)}`,
                <input
                  id="yat-donusum"
                  type="range"
                  min={0.1}
                  max={10}
                  step={0.1}
                  value={donusum}
                  onChange={(e) => setDonusum(Number(e.target.value))}
                  className={kaydirici}
                />,
              )}

              {satir(
                'yat-sepet',
                t('yatirim.sepet'),
                paraBirimi(sepet),
                <input
                  id="yat-sepet"
                  type="range"
                  min={10}
                  max={5000}
                  step={10}
                  value={sepet}
                  onChange={(e) => setSepet(Number(e.target.value))}
                  className={kaydirici}
                />,
              )}

              <div className="border-t border-white/10 pt-7">
                {satir(
                  'yat-artis',
                  t('yatirim.artis'),
                  `%${artis}`,
                  <input
                    id="yat-artis"
                    type="range"
                    min={0}
                    max={50}
                    step={1}
                    value={artis}
                    onChange={(e) => setArtis(Number(e.target.value))}
                    className={kaydirici}
                  />,
                )}
                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                  {t('yatirim.artisNotu')}
                </p>
              </div>
            </div>
          </div>

          {/* Sonuç */}
          <div className="rounded-2xl border border-primary/40 bg-primary/[0.07] p-6 sm:p-8 lg:col-span-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" aria-hidden="true" />
              <p className="text-xs font-semibold uppercase tracking-wider text-purple-200">
                {t('yatirim.sonucEtiket')}
              </p>
            </div>

            <p className="mt-4 text-4xl font-bold leading-none gradient-text">
              {hesap.aylikFark > 0 ? '+' : ''}
              {paraBirimi(hesap.aylikFark)}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">{t('yatirim.aylikEk')}</p>

            <dl className="mt-6 space-y-3 border-t border-white/10 pt-6 text-sm">
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-muted-foreground">{t('yatirim.mevcutCiro')}</dt>
                <dd className="font-mono font-medium">{paraBirimi(hesap.mevcutCiro)}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-muted-foreground">{t('yatirim.yeniCiro')}</dt>
                <dd className="font-mono font-medium">{paraBirimi(hesap.yeniCiro)}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-muted-foreground">{t('yatirim.yillikEk')}</dt>
                <dd className="font-mono font-medium">{paraBirimi(hesap.yillikFark)}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-muted-foreground">{t('yatirim.geriOdeme')}</dt>
                <dd className="font-mono font-medium">
                  {hesap.geriOdemeAy === null
                    ? '—'
                    : hesap.geriOdemeAy < 1
                      ? t('yatirim.ilkAy')
                      : t('yatirim.ay', { sayi: ondalik(hesap.geriOdemeAy) })}
                </dd>
              </div>
            </dl>

            <p className="mt-5 text-xs leading-relaxed text-muted-foreground">
              {t('yatirim.geriOdemeNotu', { ucret: paraBirimi(aylikUcret) })}
            </p>

            <Link to="/contact" className="mt-6 block">
              <Button className="h-11 w-full gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500">
                {t('yatirim.cta')}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
