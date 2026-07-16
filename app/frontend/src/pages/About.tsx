import { Github, Linkedin, Twitter } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function About() {
  const { t } = useTranslation();

  const VALUES = [
    { title: t('about.v1Title'), desc: t('about.v1Desc') },
    { title: t('about.v2Title'), desc: t('about.v2Desc') },
    { title: t('about.v3Title'), desc: t('about.v3Desc') },
    { title: t('about.v4Title'), desc: t('about.v4Desc') },
  ];

  const TIMELINE = [
    { year: t('about.t1Year'), title: t('about.t1Title'), desc: t('about.t1Desc') },
    { year: t('about.t2Year'), title: t('about.t2Title'), desc: t('about.t2Desc') },
    { year: t('about.t3Year'), title: t('about.t3Title'), desc: t('about.t3Desc') },
    { year: t('about.t4Year'), title: t('about.t4Title'), desc: t('about.t4Desc') },
  ];

  return (
    <div>
      {/* Header */}
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
              {[
                { icon: Github, label: 'GitHub' },
                { icon: Linkedin, label: 'LinkedIn' },
                { icon: Twitter, label: 'Twitter / X' },
              ].map((s) => (
                <a
                  key={s.label}
                  href="#"
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
                src="/assets/founder-photo.jpg"
                alt="Mehmet KURU"
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
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
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
    </div>
  );
}