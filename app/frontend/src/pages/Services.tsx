import { Link } from 'react-router-dom';
import {
  Code2,
  Paintbrush,
  Search,
  BarChart3,
  Smartphone,
  ShoppingCart,
  Check,
  ArrowRight,
  Github,
  Linkedin,
  Twitter,
  Zap,
  Rocket,
  Shield,
  Crown,
  Server,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import { useSiteSettings } from '@/lib/siteSettings';

export default function Services() {
  const { settings } = useSiteSettings();
  const { t } = useTranslation();

  const VALUES = [
    { title: t('about.v1Title'), desc: t('about.v1Desc') },
    { title: t('about.v2Title'), desc: t('about.v2Desc') },
    { title: t('about.v3Title'), desc: t('about.v3Desc') },
    { title: t('about.v4Title'), desc: t('about.v4Desc') },
    { title: t('about.v5Title'), desc: t('about.v5Desc') },
  ];

  const TIMELINE = [
    { year: t('about.t1Year'), title: t('about.t1Title'), desc: t('about.t1Desc') },
    { year: t('about.t2Year'), title: t('about.t2Title'), desc: t('about.t2Desc') },
    { year: t('about.t3Year'), title: t('about.t3Title'), desc: t('about.t3Desc') },
    { year: t('about.t4Year'), title: t('about.t4Title'), desc: t('about.t4Desc') },
    { year: t('about.t5Year'), title: t('about.t5Title'), desc: t('about.t5Desc') },
    { year: t('about.t6Year'), title: t('about.t6Title'), desc: t('about.t6Desc') },
  ];

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

  const PLANS = [
    { icon: Zap, name: t('packages.option1'), price: `$${settings.price_starter}`, desc: t('packages.option1Desc'), gradient: 'from-purple-600 to-pink-600', highlight: false, isQuote: false },
    { icon: Rocket, name: t('packages.option2'), price: `$${settings.price_business}`, desc: t('packages.option2Desc'), gradient: 'from-pink-600 to-orange-500', highlight: false, isQuote: false },
    { icon: Shield, name: t('packages.option3'), price: `$${settings.price_ecommerce}`, desc: t('packages.option3Desc'), gradient: 'from-cyan-500 to-purple-600', highlight: true, isQuote: false },
    { icon: Crown, name: t('packages.option4'), price: `$${settings.price_saas}`, desc: t('packages.option4Desc'), gradient: 'from-emerald-500 to-cyan-500', highlight: false, isQuote: false },
    { icon: Server, name: t('packages.option5'), price: `$${settings.price_devops}`, desc: t('packages.option5Desc'), gradient: 'from-purple-500 to-pink-500', highlight: false, isQuote: true },
  ];

  const SOCIALS = [
    { icon: Github, label: 'GitHub', url: '#' },
    { icon: Linkedin, label: 'LinkedIn', url: '#' },
    { icon: Twitter, label: 'Twitter / X', url: '#' },
  ];

  return (
    <div>
      {/* About / Header */}
      <section className="relative py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid gap-16 lg:grid-cols-12 items-center">
          <div className="lg:col-span-7">
            <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">
              {t('about.sectionTag')}
            </p>
            <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6">
              {t('about.title1')}
              <br />
              <span className="gradient-text">{t('about.titleHighlight')}</span>
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl leading-relaxed mb-8">
              {t('about.desc')}
            </p>
            <div className="flex flex-wrap gap-3">
              {SOCIALS.map((s) => (
                <a
                  key={s.label}
                  href={s.url}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass text-sm hover:border-purple-500/40 transition-colors"
                >
                  <s.icon className="h-4 w-4" />
                  {s.label}
                </a>
              ))}
            </div>
          </div>

          <div className="lg:col-span-5 relative">
            <div className="relative aspect-[4/5] rounded-3xl overflow-hidden glass p-2 animate-float">
              <div className="absolute -inset-4 bg-gradient-to-br from-purple-500/30 via-pink-500/20 to-cyan-500/20 blur-2xl -z-10" />
              <img
                src="/assets/founder-photo.webp"
                alt="Mehmet KURU — kurucu, full-stack mühendis"
                width={560}
                height={700}
                loading="lazy"
                decoding="async"
                className="w-full h-full object-cover rounded-2xl"
                onError={(e) => {
                  const el = e.currentTarget as HTMLImageElement;
                  el.style.display = 'none';
                }}
              />
              <div className="absolute bottom-6 left-6 right-6 glass rounded-xl p-4">
                <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('about.founder')}</p>
                <p className="font-semibold">Mehmet KURU</p>
                <p className="text-xs text-muted-foreground mt-1">{t('about.role')}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Values */}
      <section className="py-24 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-14">
            <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">
              {t('about.valuesTag')}
            </p>
            <h2 className="text-4xl md:text-5xl font-bold">{t('about.valuesTitle')}</h2>
          </div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-5">
            {VALUES.map((v, i) => (
              <div key={v.title} className="p-6 rounded-2xl glass hover:border-purple-500/40 transition-colors">
                <div className="text-5xl font-bold gradient-text mb-4">0{i + 1}</div>
                <h3 className="text-xl font-semibold mb-2">{v.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{v.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Timeline */}
      <section className="py-24 border-t border-white/5">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-14 text-center">
            <p className="text-xs uppercase tracking-[0.3em] text-cyan-400 mb-4">{t('about.journeyTag')}</p>
            <h2 className="text-4xl md:text-5xl font-bold">{t('about.journeyTitle')}</h2>
          </div>
          <div className="relative pl-8 border-l border-purple-500/30">
            {TIMELINE.map((item) => (
              <div key={item.year} className="relative mb-10 last:mb-0">
                <div className="absolute -left-[38px] top-1 h-4 w-4 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 ring-4 ring-background" />
                <div className="text-sm font-mono text-purple-400 mb-1">{item.year}</div>
                <h4 className="text-xl font-semibold mb-2">{item.title}</h4>
                <p className="text-muted-foreground">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Services header */}
      <section className="py-24 border-t border-white/5 text-center max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">{t('services.sectionTag')}</p>
        <h2 className="text-4xl md:text-6xl font-bold leading-[1.05] mb-6">
          {t('services.title')} <span className="gradient-text">{t('services.titleHighlight')}</span>.
        </h2>
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

      {/* Pricing packages */}
      <section className="py-24 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">{t('packages.sectionTag')}</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              {t('packages.title')} <span className="gradient-text">{t('packages.titleHighlight')}</span>.
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              {t('packages.desc')}
            </p>
          </div>

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