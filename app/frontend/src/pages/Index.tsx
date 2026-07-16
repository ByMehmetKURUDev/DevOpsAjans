import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, Code2, Rocket, Target, Paintbrush, Globe, Zap, Shield, Crown, Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Hero3D from '@/components/Hero3D';
import { useTranslation } from 'react-i18next';

const TECH = [
  'React', 'Next.js', 'TypeScript', 'Node.js', 'Python',
  'PostgreSQL', 'AWS', 'Azure', 'GCP', 'Docker',
  'Kubernetes', 'Terraform', 'Jenkins', 'GitHub Actions',
  'Tailwind', 'GraphQL', 'Figma', 'Three.js', 'Stripe',
];

export default function Index() {
  const { t } = useTranslation();

  const STATS = [
    { value: '41+', label: t('stats.projects') },
    { value: '13+', label: t('stats.years') },
    { value: '33+', label: t('stats.clients') },
    { value: '7+', label: t('stats.countries') },
  ];

  const CAPABILITIES = [
    {
      icon: Target,
      title: t('capabilities.consulting'),
      desc: t('capabilities.consultingDesc'),
      gradient: 'from-emerald-400 to-cyan-400',
    },
    {
      icon: Paintbrush,
      title: t('capabilities.design'),
      desc: t('capabilities.designDesc'),
      gradient: 'from-cyan-400 to-purple-500',
    },
    {
      icon: Code2,
      title: t('capabilities.software'),
      desc: t('capabilities.softwareDesc'),
      gradient: 'from-purple-500 to-pink-500',
    },
    {
      icon: Rocket,
      title: t('capabilities.marketing'),
      desc: t('capabilities.marketingDesc'),
      gradient: 'from-pink-500 to-orange-400',
    },
    {
      icon: Globe,
      title: t('capabilities.launch'),
      desc: t('capabilities.launchDesc'),
      gradient: 'from-orange-400 to-emerald-400',
    },
  ];

  const STEPS = [
    { n: '01', title: t('process.step1Title'), desc: t('process.step1Desc') },
    { n: '02', title: t('process.step2Title'), desc: t('process.step2Desc') },
    { n: '03', title: t('process.step3Title'), desc: t('process.step3Desc') },
    { n: '04', title: t('process.step4Title'), desc: t('process.step4Desc') },
  ];

  const PLANS = [
    { icon: Zap, name: t('packages.option1'), price: t('packages.option1Price'), desc: t('packages.option1Desc'), gradient: 'from-purple-600 to-pink-600', highlight: false, isQuote: false },
    { icon: Rocket, name: t('packages.option2'), price: t('packages.option2Price'), desc: t('packages.option2Desc'), gradient: 'from-pink-600 to-orange-500', highlight: false, isQuote: false },
    { icon: Shield, name: t('packages.option3'), price: t('packages.option3Price'), desc: t('packages.option3Desc'), gradient: 'from-cyan-500 to-purple-600', highlight: true, isQuote: false },
    { icon: Crown, name: t('packages.option4'), price: t('packages.option4Price'), desc: t('packages.option4Desc'), gradient: 'from-emerald-500 to-cyan-500', highlight: false, isQuote: false },
    { icon: Server, name: t('packages.option5'), price: t('packages.option5Price'), desc: t('packages.option5Desc'), gradient: 'from-purple-500 to-pink-500', highlight: false, isQuote: true },
  ];

  return (
    <div>
      {/* HERO */}
      <section className="relative min-h-[92vh] flex items-center overflow-hidden">
        <div className="absolute inset-0">
          <Hero3D />
        </div>
        <div className="absolute inset-0 bg-gradient-to-b from-background/30 via-transparent to-background pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full py-24">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass mb-6 animate-in fade-in slide-in-from-bottom-2 duration-700">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
              </span>
              <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {t('hero.badge')}
              </span>
            </div>

            <h1 className="text-5xl sm:text-6xl lg:text-7xl xl:text-8xl font-bold leading-[1.02] mb-8 animate-in fade-in slide-in-from-bottom-4 duration-1000">
              {t('hero.title1')}{' '}
              <span className="gradient-text">{t('hero.titleHighlight')}</span>
              <br />
              {t('hero.title2')}{' '}
              <span className="italic font-light text-muted-foreground">{t('hero.titleItalic')}</span>
            </h1>

            <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl mb-10 animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-200">
              {t('hero.desc')}
            </p>

            <div className="flex flex-wrap gap-4 animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-300">
              <Link to="/contact">
                <Button
                  size="lg"
                  className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 glow-primary h-12 px-6 gap-2"
                >
                  {t('hero.cta')} <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link to="/portfolio">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-12 px-6 !bg-transparent !hover:bg-transparent border-white/20 hover:border-white/40 gap-2"
                >
                  {t('hero.ctaSecondary')}
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* Bottom stats strip */}
        <div className="absolute bottom-0 left-0 right-0 border-t border-white/5 backdrop-blur-md bg-background/40">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-2 md:grid-cols-4">
            {STATS.map((s) => (
              <div key={s.label} className="py-6 px-4 border-r border-white/5 last:border-r-0">
                <div className="text-2xl md:text-3xl font-bold gradient-text">{s.value}</div>
                <div className="text-xs uppercase tracking-widest text-muted-foreground mt-1">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CAPABILITIES */}
      <section className="relative py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-2xl mb-16">
            <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">
              {t('capabilities.sectionTag')}
            </p>
            <h2 className="text-4xl sm:text-5xl font-bold leading-tight">
              {t('capabilities.title')}{' '}
              <span className="gradient-text">{t('capabilities.titleHighlight')}</span>.
            </h2>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-5">
            {CAPABILITIES.map((c, i) => (
              <div
                key={c.title}
                className="group relative p-6 rounded-2xl glass hover:border-purple-500/40 transition-all duration-500 hover:-translate-y-1"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <div
                  className={`w-11 h-11 rounded-xl bg-gradient-to-br ${c.gradient} flex items-center justify-center mb-5 group-hover:scale-110 transition-transform`}
                >
                  <c.icon className="h-5 w-5 text-white" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{c.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{c.desc}</p>
                <div className="mt-5 pt-4 border-t border-white/5">
                  <Link
                    to="/services"
                    className="text-xs uppercase tracking-wider text-purple-400 hover:text-purple-300 flex items-center gap-1"
                  >
                    {t('capabilities.learnMore')} <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PROCESS */}
      <section className="relative py-32 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid gap-16 lg:grid-cols-2">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">{t('process.sectionTag')}</p>
            <h2 className="text-4xl sm:text-5xl font-bold leading-tight mb-6">
              {t('process.title1')}
              <br />
              <span className="gradient-text">{t('process.titleHighlight')}</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-lg">
              {t('process.desc')}
            </p>
          </div>

          <div className="space-y-6">
            {STEPS.map((step) => (
              <div key={step.n} className="flex gap-6 p-5 rounded-xl hover:bg-white/[0.02] transition-colors">
                <div className="text-4xl font-bold gradient-text opacity-60 w-16 shrink-0">
                  {step.n}
                </div>
                <div>
                  <h4 className="text-lg font-semibold mb-1">{step.title}</h4>
                  <p className="text-sm text-muted-foreground leading-relaxed">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PACKAGES */}
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

      {/* TECH MARQUEE */}
      <section className="py-16 border-y border-white/5 bg-gradient-to-r from-purple-950/20 via-pink-950/10 to-cyan-950/20 overflow-hidden">
        <p className="text-center text-xs uppercase tracking-[0.4em] text-muted-foreground mb-8">
          {t('techMarquee')}
        </p>
        <div className="relative">
          <div className="flex marquee gap-8 whitespace-nowrap">
            {[...TECH, ...TECH].map((tech, i) => (
              <span
                key={`${tech}-${i}`}
                className="text-2xl md:text-3xl font-bold tracking-tight text-muted-foreground/60 hover:text-foreground transition-colors"
              >
                {tech}
                <span className="mx-8 text-purple-500/40">&#9670;</span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Instagram Carousel */}
      <section className="py-16 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center">
              <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/>
              </svg>
            </div>
            <div>
              <p className="font-semibold text-sm">@mehmetkurudev</p>
              <p className="text-xs text-muted-foreground">Instagram</p>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto scrollbar-hide">
          <div className="flex gap-3 px-4 sm:px-6 lg:px-8 pb-4 min-w-max">
            {Array.from({ length: 10 }).map((_, i) => (
              <div
                key={i}
                className="w-56 h-56 rounded-xl overflow-hidden flex-shrink-0 glass hover:border-purple-500/40 transition-all duration-300 hover:-translate-y-1 group cursor-pointer"
              >
                <div className={`w-full h-full bg-gradient-to-br ${
                  ['from-purple-600/40 to-pink-600/40', 'from-pink-600/40 to-orange-500/40', 'from-cyan-500/40 to-purple-600/40', 'from-emerald-500/40 to-cyan-500/40', 'from-purple-500/40 to-cyan-500/40', 'from-pink-500/40 to-purple-600/40', 'from-orange-500/40 to-pink-600/40', 'from-cyan-400/40 to-emerald-500/40', 'from-purple-400/40 to-pink-400/40', 'from-emerald-400/40 to-purple-400/40'][i]
                } flex items-center justify-center group-hover:scale-105 transition-transform duration-500`}>
                  <div className="text-center">
                    <div className="text-3xl mb-2">
                      {['💻', '🚀', '🎨', '📱', '⚡', '🔥', '✨', '🌐', '🛡️', '☁️'][i]}
                    </div>
                    <p className="text-xs text-muted-foreground uppercase tracking-widest">
                      {['Web Dev', 'SaaS', 'Design', 'Mobile', 'DevOps', 'Marketing', 'UI/UX', 'E-Commerce', 'Security', 'Cloud'][i]}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative py-32">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="relative rounded-3xl overflow-hidden p-12 md:p-20 text-center glass border border-purple-500/30">
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-purple-600/20 via-pink-600/10 to-cyan-600/20" />
            <div className="absolute top-0 right-0 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="absolute bottom-0 left-0 w-96 h-96 bg-pink-500/20 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2" />

            <h2 className="text-4xl md:text-6xl font-bold mb-6">
              {t('cta.title')}{' '}
              <span className="gradient-text italic">{t('cta.titleHighlight')}</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-xl mx-auto mb-8">
              {t('cta.desc')}
            </p>
            <div className="flex flex-wrap gap-4 justify-center">
              <Link to="/contact">
                <Button
                  size="lg"
                  className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 h-12 px-8"
                >
                  {t('cta.btn')}
                </Button>
              </Link>
              <Link to="/services">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-12 px-8 !bg-transparent border-white/20 hover:border-white/40"
                >
                  {t('cta.btnSecondary')}
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}