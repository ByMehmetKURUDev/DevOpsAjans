import { Link } from 'react-router-dom';
import { ArrowRight, Code2, Rocket, Target, Paintbrush, Globe, Zap, Shield, Crown, Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import { useSiteSettings } from '@/lib/siteSettings';

const TECH = [
  'React', 'Next.js', 'TypeScript', 'Node.js', 'Python',
  'PostgreSQL', 'AWS', 'Azure', 'GCP', 'Docker',
  'Kubernetes', 'Terraform', 'Jenkins', 'GitHub Actions',
  'Tailwind', 'GraphQL', 'Figma', 'Three.js', 'Stripe',
];

export default function Index() {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();

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
    { icon: Zap, name: t('packages.option1'), price: `$${settings.price_starter}`, desc: t('packages.option1Desc'), gradient: 'from-purple-600 to-pink-600', highlight: false, isQuote: false },
    { icon: Rocket, name: t('packages.option2'), price: `$${settings.price_business}`, desc: t('packages.option2Desc'), gradient: 'from-pink-600 to-orange-500', highlight: false, isQuote: false },
    { icon: Shield, name: t('packages.option3'), price: `$${settings.price_ecommerce}`, desc: t('packages.option3Desc'), gradient: 'from-cyan-500 to-purple-600', highlight: true, isQuote: false },
    { icon: Crown, name: t('packages.option4'), price: `$${settings.price_saas}`, desc: t('packages.option4Desc'), gradient: 'from-emerald-500 to-cyan-500', highlight: false, isQuote: false },
    { icon: Server, name: t('packages.option5'), price: `$${settings.price_devops}`, desc: t('packages.option5Desc'), gradient: 'from-purple-500 to-pink-500', highlight: false, isQuote: true },
  ];

  return (
    <div>
      {/* HERO */}
      <section className="relative min-h-[92vh] flex items-center overflow-hidden">
        <div className="absolute inset-0">
          <img
            src="/assets/hero-banner.png"
            alt="Hero Banner"
            className="w-full h-full object-cover"
            loading="eager"
            fetchPriority="high"
          />
        </div>
        <div className="absolute inset-0 bg-gradient-to-b from-[#05010a]/60 via-[#1a0b2e]/40 to-background pointer-events-none" />

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
              <span className="gradient-text">{settings.hero_title}</span>
            </h1>

            <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl mb-10 animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-200">
              {settings.hero_subtitle}
            </p>

            <div className="flex flex-wrap gap-4 animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-300">
              <Link to="/contact">
                <Button
                  size="lg"
                  className="bg-gradient-to-r from-[#8b3dff] to-[#5c27a3] hover:from-[#9b5dff] hover:to-[#7b3dc3] text-white border-0 glow-primary h-12 px-6 gap-2"
                >
                  {settings.hero_cta} <ArrowRight className="h-4 w-4" />
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



      {/* PORTFOLIO CATEGORIES */}
      <section className="py-24 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">{t('portfolio.sectionTag')}</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              {t('portfolio.title1')} <span className="gradient-text">{t('portfolio.titleHighlight')}</span>
            </h2>
          </div>
          <div className="grid gap-6 md:grid-cols-3 lg:grid-cols-5">
            {[
              { slug: 'Website', label: 'Website', emoji: '💻', gradient: 'from-purple-600 to-pink-600' },
              { slug: 'E-Ticaret', label: 'E-Ticaret', emoji: '🛒', gradient: 'from-pink-600 to-orange-500' },
              { slug: 'SaaS', label: 'SaaS', emoji: '🚀', gradient: 'from-cyan-500 to-purple-600' },
              { slug: 'Mobil Uygulama', label: 'Mobil Uygulama', emoji: '📱', gradient: 'from-emerald-500 to-cyan-500' },
              { slug: 'Reklam', label: 'Reklam', emoji: '📣', gradient: 'from-purple-500 to-pink-500' },
            ].map((cat) => (
              <Link
                key={cat.slug}
                to={`/portfolio?category=${encodeURIComponent(cat.slug)}`}
                className="group relative p-8 rounded-2xl glass hover:border-purple-500/40 transition-all duration-500 hover:-translate-y-1 text-center"
              >
                <div className={`w-14 h-14 mx-auto rounded-xl bg-gradient-to-br ${cat.gradient} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                  <span className="text-2xl">{cat.emoji}</span>
                </div>
                <h3 className="text-lg font-semibold">{cat.label}</h3>
                <p className="text-xs text-muted-foreground mt-2 uppercase tracking-wider">Keşfet →</p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* GOOGLE BUSINESS REVIEWS / TESTIMONIALS */}
      <section className="py-24 border-t border-white/5">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs uppercase tracking-[0.3em] text-emerald-400 mb-4">MÜŞTERİ YORUMLARI</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              Google Business <span className="gradient-text">Yorumları</span>
            </h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Müşterilerimizin deneyimlerini ve geri bildirimlerini okuyun.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[
              { name: 'Ahmet Y.', rating: 5, text: 'Profesyonel ve hızlı çalışma. E-ticaret sitemizi kısa sürede teslim ettiler. Kesinlikle tavsiye ederim.', date: '2 ay önce', avatar: 'A' },
              { name: 'Sarah M.', rating: 5, text: 'Excellent communication and top-notch development skills. Our SaaS platform was delivered on time with all features working perfectly.', date: '3 ay önce', avatar: 'S' },
              { name: 'Mehmet K.', rating: 5, text: 'Google Ads kampanyalarımızı yönettiler, ROAS oranımız %300 arttı. Çok memnunuz.', date: '1 ay önce', avatar: 'M' },
              { name: 'Thomas B.', rating: 5, text: 'Sehr professionelle Arbeit. Die mobile App wurde genau nach unseren Vorstellungen entwickelt. Klare Empfehlung!', date: '4 ay önce', avatar: 'T' },
              { name: 'Elif D.', rating: 5, text: 'Kurumsal web sitemiz için harika bir iş çıkardılar. SEO optimizasyonu da dahil edildi, organik trafiğimiz %150 arttı.', date: '2 hafta önce', avatar: 'E' },
              { name: 'James R.', rating: 4, text: 'Great team to work with. They understood our requirements quickly and delivered a solid product. Would work with them again.', date: '5 ay önce', avatar: 'J' },
            ].map((review, i) => (
              <div
                key={i}
                className="p-6 rounded-2xl glass hover:border-purple-500/30 transition-all duration-300"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-bold text-sm">
                    {review.avatar}
                  </div>
                  <div>
                    <p className="font-semibold text-sm">{review.name}</p>
                    <div className="flex items-center gap-1">
                      {Array.from({ length: review.rating }).map((_, si) => (
                        <svg key={si} className="w-3.5 h-3.5 text-yellow-400 fill-current" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      ))}
                      {Array.from({ length: 5 - review.rating }).map((_, si) => (
                        <svg key={si} className="w-3.5 h-3.5 text-white/20 fill-current" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      ))}
                    </div>
                  </div>
                  <span className="ml-auto text-[10px] text-muted-foreground">{review.date}</span>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">"{review.text}"</p>
                <div className="mt-4 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  Google Business
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