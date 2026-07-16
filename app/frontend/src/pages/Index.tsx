import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, Code2, Rocket, Target } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Hero3D from '@/components/Hero3D';
import { useTranslation } from 'react-i18next';

const TECH = [
  'React', 'Next.js', 'TypeScript', 'Node.js', 'Python',
  'PostgreSQL', 'AWS', 'Stripe', 'Figma', 'Three.js',
  'Framer Motion', 'Tailwind', 'GraphQL', 'Rust', 'Solidity',
];

export default function Index() {
  const { t } = useTranslation();

  const STATS = [
    { value: '150+', label: t('stats.projects') },
    { value: '8+', label: t('stats.years') },
    { value: '40+', label: t('stats.clients') },
    { value: '12', label: t('stats.countries') },
  ];

  const CAPABILITIES = [
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
      icon: Sparkles,
      title: t('capabilities.design'),
      desc: t('capabilities.designDesc'),
      gradient: 'from-cyan-400 to-purple-500',
    },
    {
      icon: Target,
      title: t('capabilities.consulting'),
      desc: t('capabilities.consultingDesc'),
      gradient: 'from-emerald-400 to-cyan-400',
    },
  ];

  const STEPS = [
    { n: '01', title: t('process.step1Title'), desc: t('process.step1Desc') },
    { n: '02', title: t('process.step2Title'), desc: t('process.step2Desc') },
    { n: '03', title: t('process.step3Title'), desc: t('process.step3Desc') },
    { n: '04', title: t('process.step4Title'), desc: t('process.step4Desc') },
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

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
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