import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Crown, Rocket, Server, Shield, Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useSiteSettings } from '@/lib/siteSettings';

/** Yıllık ödemede uygulanan indirim. Panelden `yearly_discount` ile değişir. */
const DEFAULT_YEARLY_DISCOUNT = 20;

type Billing = 'monthly' | 'yearly';

/**
 * Paket kartları.
 *
 * Daha önce bu blok hem ana sayfada hem Nasıl Çalışır'da ayrı ayrı yazılıydı;
 * ikisi zamanla ayrışmıştı. Artık tek bileşen.
 *
 * Üç düzeltme:
 *  - Aylık/Yıllık anahtarı; yıllıkta panelden gelen indirim uygulanıyor.
 *  - Kartlar `flex` kolon, açıklama `flex-1`: metin uzunluğu farklı olsa da
 *    butonlar aynı hizada kalıyor (eskiden kart yüksekliğine göre kayıyordu).
 *  - DevOps'ta fiyat yok; yerinde "Görüşelim" duruyor, kart yapısı bozulmuyor.
 */
export default function PricingPlans({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();
  const [billing, setBilling] = useState<Billing>('monthly');

  const discount = Number.parseInt(settings.yearly_discount ?? '', 10) || DEFAULT_YEARLY_DISCOUNT;

  const priceFor = (monthly: string) => {
    const value = Number.parseInt(monthly, 10);
    if (!Number.isFinite(value)) return `$${monthly}`;
    if (billing === 'monthly') return `$${value}`;
    const yearly = Math.round(value * 12 * (1 - discount / 100));
    return `$${yearly.toLocaleString('en-US')}`;
  };

  const PLANS = [
    { icon: Zap, name: t('packages.option1'), monthly: settings.price_starter, desc: t('packages.option1Desc'), gradient: 'from-purple-600 to-pink-600', highlight: false, isQuote: false },
    { icon: Rocket, name: t('packages.option2'), monthly: settings.price_business, desc: t('packages.option2Desc'), gradient: 'from-pink-600 to-orange-500', highlight: false, isQuote: false },
    { icon: Shield, name: t('packages.option3'), monthly: settings.price_ecommerce, desc: t('packages.option3Desc'), gradient: 'from-cyan-500 to-purple-600', highlight: true, isQuote: false },
    { icon: Crown, name: t('packages.option4'), monthly: settings.price_saas, desc: t('packages.option4Desc'), gradient: 'from-emerald-500 to-cyan-500', highlight: false, isQuote: false },
    // DevOps sürekli hizmet: kapsam projeden projeye değiştiği için fiyat yazılmıyor.
    { icon: Server, name: t('packages.option5'), monthly: null, desc: t('packages.option5Desc'), gradient: 'from-purple-500 to-pink-500', highlight: false, isQuote: true },
  ];

  const tab =
    'rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-400';

  return (
    <section className={`py-24 border-t border-white/10 ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10">
          <p className="text-xs uppercase tracking-[0.3em] text-pink-300 mb-4">
            {t('packages.sectionTag')}
          </p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            {t('packages.title')} <span className="gradient-text">{t('packages.titleHighlight')}</span>.
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">{t('packages.desc')}</p>
        </div>

        {/* Ödeme dönemi anahtarı */}
        <div className="mb-12 flex justify-center">
          <div
            className="inline-flex items-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1"
            role="group"
            aria-label={t('packages.billingLabel')}
          >
            <button
              type="button"
              onClick={() => setBilling('monthly')}
              aria-pressed={billing === 'monthly'}
              className={`${tab} ${
                billing === 'monthly'
                  ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                  : 'text-muted-foreground hover:text-white'
              }`}
            >
              {t('packages.monthly')}
            </button>
            <button
              type="button"
              onClick={() => setBilling('yearly')}
              aria-pressed={billing === 'yearly'}
              className={`${tab} ${
                billing === 'yearly'
                  ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                  : 'text-muted-foreground hover:text-white'
              }`}
            >
              {t('packages.yearly')}
              <span className="ms-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-300">
                −{discount}%
              </span>
            </button>
          </div>
        </div>

        {/* `items-stretch` + kart içi flex: bütün butonlar aynı hizada */}
        <div className="grid items-stretch gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`relative flex h-full flex-col rounded-2xl p-8 transition-all duration-500 hover:-translate-y-1 ${
                plan.highlight
                  ? 'glass border-purple-500/50 ring-1 ring-purple-500/40'
                  : 'glass hover:border-purple-500/30'
              }`}
            >
              {plan.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-white">
                  {t('ui.popular')}
                </div>
              )}

              <div
                className={`mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${plan.gradient}`}
              >
                <plan.icon className="h-5 w-5 text-white" aria-hidden="true" />
              </div>

              <h3 className="mb-2 text-xl font-bold">{plan.name}</h3>

              {/* Fiyat satırı sabit yükseklikte: DevOps kartı diğerleriyle hizalı kalsın */}
              <div className="mb-4 min-h-[3.25rem]">
                {plan.monthly ? (
                  <>
                    <p className="text-3xl font-bold gradient-text">{priceFor(plan.monthly)}</p>
                    <p className="text-xs text-muted-foreground">
                      {billing === 'monthly' ? t('packages.perMonth') : t('packages.perYear')}
                    </p>
                  </>
                ) : (
                  <p className="text-2xl font-bold gradient-text">{t('packages.customPrice')}</p>
                )}
              </div>

              <p className="mb-8 flex-1 text-sm leading-relaxed text-muted-foreground">{plan.desc}</p>

              <Link to="/contact" className="mt-auto block">
                <Button
                  className={`h-11 w-full gap-2 ${
                    plan.highlight
                      ? 'border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500'
                      : '!bg-transparent border border-white/25 hover:border-white/50'
                  }`}
                  variant={plan.highlight ? 'default' : 'outline'}
                >
                  {plan.isQuote ? t('packages.getQuote') : t('packages.buyNow')}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
