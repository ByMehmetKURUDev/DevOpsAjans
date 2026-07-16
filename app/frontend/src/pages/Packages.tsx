import { Link } from 'react-router-dom';
import { ArrowRight, Check, Zap, Rocket, Shield, Crown, Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

export default function Packages() {
  const { t } = useTranslation();

  const PLANS = [
    {
      icon: Zap,
      name: t('packages.option1'),
      price: t('packages.option1Price'),
      desc: t('packages.option1Desc'),
      gradient: 'from-purple-600 to-pink-600',
      highlight: false,
      isQuote: false,
    },
    {
      icon: Rocket,
      name: t('packages.option2'),
      price: t('packages.option2Price'),
      desc: t('packages.option2Desc'),
      gradient: 'from-pink-600 to-orange-500',
      highlight: false,
      isQuote: false,
    },
    {
      icon: Shield,
      name: t('packages.option3'),
      price: t('packages.option3Price'),
      desc: t('packages.option3Desc'),
      gradient: 'from-cyan-500 to-purple-600',
      highlight: true,
      isQuote: false,
    },
    {
      icon: Crown,
      name: t('packages.option4'),
      price: t('packages.option4Price'),
      desc: t('packages.option4Desc'),
      gradient: 'from-emerald-500 to-cyan-500',
      highlight: false,
      isQuote: false,
    },
    {
      icon: Server,
      name: t('packages.option5'),
      price: t('packages.option5Price'),
      desc: t('packages.option5Desc'),
      gradient: 'from-purple-500 to-pink-500',
      highlight: false,
      isQuote: true,
    },
  ];

  return (
    <div>
      {/* Header */}
      <section className="py-24 md:py-32 text-center max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">{t('packages.sectionTag')}</p>
        <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6">
          {t('packages.title')} <span className="gradient-text">{t('packages.titleHighlight')}</span>.
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          {t('packages.desc')}
        </p>
      </section>

      {/* Pricing grid */}
      <section className="pb-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`relative p-8 rounded-2xl transition-all duration-500 hover:-translate-y-1 ${
                  plan.highlight
                    ? 'glass border-purple-500/50 ring-1 ring-purple-500/40'
                    : 'glass hover:border-purple-500/30'
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-gradient-to-r from-purple-600 to-pink-600 text-white text-[10px] uppercase tracking-widest font-semibold whitespace-nowrap">
                    Popular
                  </div>
                )}

                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${plan.gradient} flex items-center justify-center mb-6`}>
                  <plan.icon className="h-5 w-5 text-white" />
                </div>

                <h3 className="text-xl font-bold mb-2">{plan.name}</h3>
                <p className="text-3xl font-bold gradient-text mb-4">{plan.price}</p>
                <p className="text-sm text-muted-foreground leading-relaxed mb-8">{plan.desc}</p>

                <Link to="/contact">
                  <Button
                    className={`w-full h-11 gap-2 ${
                      plan.highlight
                        ? 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0'
                        : '!bg-transparent border border-white/20 hover:border-white/40'
                    }`}
                    variant={plan.highlight ? 'default' : 'outline'}
                  >
                    {plan.isQuote ? t('packages.getQuote') : t('packages.buyNow')} <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}