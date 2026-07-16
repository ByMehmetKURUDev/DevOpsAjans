import {
  Code2,
  Paintbrush,
  Search,
  BarChart3,
  Smartphone,
  ShoppingCart,
  Check,
} from 'lucide-react';
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
    </div>
  );
}