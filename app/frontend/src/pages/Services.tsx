import { Link } from 'react-router-dom';
import {
  Code2,
  Paintbrush,
  Search,
  BarChart3,
  Smartphone,
  ShoppingCart,
  Sparkles,
  ArrowRight,
  Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

export default function Services() {
  const { t } = useTranslation();

  const CORE_SERVICES = [
    {
      icon: Code2,
      title: t('services.webDev'),
      tag: t('services.tagEngineering'),
      desc: t('services.webDevDesc'),
      bullets: [t('services.webDevB1'), t('services.webDevB2'), t('services.webDevB3')],
      gradient: 'from-purple-600 to-pink-600',
    },
    {
      icon: Smartphone,
      title: t('services.mobile'),
      tag: t('services.tagEngineering'),
      desc: t('services.mobileDesc'),
      bullets: [t('services.mobileB1'), t('services.mobileB2'), t('services.mobileB3')],
      gradient: 'from-pink-600 to-orange-500',
    },
    {
      icon: ShoppingCart,
      title: t('services.ecommerce'),
      tag: t('services.tagEngineering'),
      desc: t('services.ecommerceDesc'),
      bullets: [t('services.ecommerceB1'), t('services.ecommerceB2'), t('services.ecommerceB3')],
      gradient: 'from-cyan-500 to-purple-600',
    },
    {
      icon: Paintbrush,
      title: t('services.brandDesign'),
      tag: t('services.tagDesign'),
      desc: t('services.brandDesignDesc'),
      bullets: [t('services.brandDesignB1'), t('services.brandDesignB2'), t('services.brandDesignB3')],
      gradient: 'from-emerald-500 to-cyan-500',
    },
    {
      icon: Search,
      title: t('services.seo'),
      tag: t('services.tagGrowth'),
      desc: t('services.seoDesc'),
      bullets: [t('services.seoB1'), t('services.seoB2'), t('services.seoB3')],
      gradient: 'from-purple-500 to-cyan-500',
    },
    {
      icon: BarChart3,
      title: t('services.ads'),
      tag: t('services.tagGrowth'),
      desc: t('services.adsDesc'),
      bullets: [t('services.adsB1'), t('services.adsB2'), t('services.adsB3')],
      gradient: 'from-pink-500 to-purple-600',
    },
  ];

  const PACKAGES = [
    {
      name: t('services.sprint'),
      price: t('services.sprintPrice'),
      duration: t('services.sprintDuration'),
      desc: t('services.sprintDesc'),
      features: ['Kickoff workshop', 'Design + build', 'One senior lead', 'Weekly demos', 'Launch handoff'],
      highlight: false,
    },
    {
      name: t('services.studio'),
      price: t('services.studioPrice'),
      duration: t('services.studioDuration'),
      desc: t('services.studioDesc'),
      features: ['Everything in Sprint', 'Design system', 'Multi-page or multi-screen product', 'Analytics + SEO setup', 'Post-launch support'],
      highlight: true,
    },
    {
      name: t('services.retainer'),
      price: t('services.retainerPrice'),
      duration: t('services.retainerDuration'),
      desc: t('services.retainerDesc'),
      features: ['Dedicated senior time', 'Weekly production releases', 'Growth experiments', 'Priority support', 'Quarterly strategy'],
      highlight: false,
    },
  ];

  return (
    <div>
      {/* Header */}
      <section className="py-24 md:py-32 text-center max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">{t('services.sectionTag')}</p>
        <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6">
          {t('services.title')} <span className="gradient-text">{t('services.titleHighlight')}</span>.
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          {t('services.desc')}
        </p>
      </section>

      {/* Services grid */}
      <section className="pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {CORE_SERVICES.map((s) => (
            <div
              key={s.title}
              className="relative p-8 rounded-2xl glass hover:border-purple-500/40 transition-all duration-500 group hover:-translate-y-1"
            >
              <div className="flex items-center justify-between mb-6">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${s.gradient} flex items-center justify-center`}>
                  <s.icon className="h-5 w-5 text-white" />
                </div>
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground px-2 py-1 rounded-full bg-white/5">
                  {s.tag}
                </span>
              </div>
              <h3 className="text-xl font-semibold mb-3">{s.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed mb-5">{s.desc}</p>
              <ul className="space-y-2 text-sm">
                {s.bullets.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-muted-foreground">
                    <Check className="h-4 w-4 text-purple-400 mt-0.5 shrink-0" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Packages */}
      <section className="py-24 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">{t('services.packagesTag')}</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">{t('services.packagesTitle')}</h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              {t('services.packagesDesc')}
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            {PACKAGES.map((p) => (
              <div
                key={p.name}
                className={`relative p-8 rounded-2xl transition-all ${
                  p.highlight
                    ? 'glass border-purple-500/50 ring-1 ring-purple-500/40 md:-translate-y-3'
                    : 'glass hover:border-white/20'
                }`}
              >
                {p.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-gradient-to-r from-purple-600 to-pink-600 text-white text-[10px] uppercase tracking-widest font-semibold">
                    {t('services.mostPopular')}
                  </div>
                )}
                <div className="flex items-baseline justify-between mb-2">
                  <h3 className="text-2xl font-bold">{p.name}</h3>
                  <span className="text-xs text-muted-foreground">{p.duration}</span>
                </div>
                <p className="text-3xl font-bold gradient-text mb-4">{p.price}</p>
                <p className="text-sm text-muted-foreground mb-6">{p.desc}</p>
                <ul className="space-y-3 mb-8">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <Check className="h-4 w-4 text-purple-400 mt-0.5 shrink-0" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <Link to="/contact">
                  <Button
                    className={`w-full h-11 gap-2 ${
                      p.highlight
                        ? 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0'
                        : '!bg-transparent border border-white/20 hover:border-white/40'
                    }`}
                    variant={p.highlight ? 'default' : 'outline'}
                  >
                    {t('services.startConversation')} <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <Sparkles className="h-10 w-10 gradient-text mx-auto mb-4" />
          <h2 className="text-3xl md:text-5xl font-bold mb-4">
            {t('services.notSure')}
          </h2>
          <p className="text-muted-foreground mb-8">
            {t('services.notSureDesc')}
          </p>
          <Link to="/contact">
            <Button size="lg" className="bg-gradient-to-r from-purple-600 to-pink-600 text-white h-12 px-8">
              {t('services.tellUs')}
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}