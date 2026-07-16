import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, Code2, Rocket, Target, Zap, Award, Users, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Hero3D from '@/components/Hero3D';

const STATS = [
  { value: '150+', label: 'Projects Delivered' },
  { value: '8+', label: 'Years of Craft' },
  { value: '40+', label: 'Happy Clients' },
  { value: '12', label: 'Countries Served' },
];

const CAPABILITIES = [
  {
    icon: Code2,
    title: 'Custom Software',
    desc: 'Full-stack web & mobile apps engineered for performance and scale.',
    gradient: 'from-purple-500 to-pink-500',
  },
  {
    icon: Rocket,
    title: 'Digital Marketing',
    desc: 'SEO, paid ads, and content strategy that ships measurable ROI.',
    gradient: 'from-pink-500 to-orange-400',
  },
  {
    icon: Sparkles,
    title: 'Product Design',
    desc: 'Interfaces that feel inevitable. Motion. Systems. Brand identity.',
    gradient: 'from-cyan-400 to-purple-500',
  },
  {
    icon: Target,
    title: 'Consulting',
    desc: 'Roadmaps, architecture reviews, and hands-on team enablement.',
    gradient: 'from-emerald-400 to-cyan-400',
  },
];

const TECH = [
  'React', 'Next.js', 'TypeScript', 'Node.js', 'Python',
  'PostgreSQL', 'AWS', 'Stripe', 'Figma', 'Three.js',
  'Framer Motion', 'Tailwind', 'GraphQL', 'Rust', 'Solidity',
];

export default function Index() {
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
                Available for projects · Q3 2026
              </span>
            </div>

            <h1 className="text-5xl sm:text-6xl lg:text-7xl xl:text-8xl font-bold leading-[1.02] mb-8 animate-in fade-in slide-in-from-bottom-4 duration-1000">
              We build the{' '}
              <span className="gradient-text">software</span>
              <br />
              behind ambitious{' '}
              <span className="italic font-light text-muted-foreground">brands.</span>
            </h1>

            <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl mb-10 animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-200">
              A boutique dev &amp; digital agency by <span className="text-foreground font-medium">Mehmet KURU</span>.
              Custom web, mobile, and marketing systems crafted for teams that
              refuse to look like everyone else.
            </p>

            <div className="flex flex-wrap gap-4 animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-300">
              <Link to="/contact">
                <Button
                  size="lg"
                  className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 glow-primary h-12 px-6 gap-2"
                >
                  Start a project <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link to="/portfolio">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-12 px-6 !bg-transparent !hover:bg-transparent border-white/20 hover:border-white/40 gap-2"
                >
                  See our work
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
              What we do
            </p>
            <h2 className="text-4xl sm:text-5xl font-bold leading-tight">
              Full-stack craft, from{' '}
              <span className="gradient-text">idea to launch</span>.
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
                    Learn more <ArrowRight className="h-3 w-3" />
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
            <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">Process</p>
            <h2 className="text-4xl sm:text-5xl font-bold leading-tight mb-6">
              Fewer meetings.
              <br />
              <span className="gradient-text">Sharper deliverables.</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-lg">
              We keep engagements deliberately lean. One tight team, one
              senior lead, one shared repo — from kickoff to launch.
            </p>
          </div>

          <div className="space-y-6">
            {[
              { n: '01', title: 'Discover', desc: 'Deep-dive workshops, technical audits, and a written scope you actually understand.' },
              { n: '02', title: 'Design', desc: 'Low-fi → hi-fi in Figma with a real design system, not a mood board.' },
              { n: '03', title: 'Build', desc: 'Weekly production releases. You watch it come alive in staging every Friday.' },
              { n: '04', title: 'Grow', desc: 'Post-launch: performance, SEO, paid, analytics, and iterative product bets.' },
            ].map((step) => (
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
          Tools of the trade
        </p>
        <div className="relative">
          <div className="flex marquee gap-8 whitespace-nowrap">
            {[...TECH, ...TECH].map((t, i) => (
              <span
                key={`${t}-${i}`}
                className="text-2xl md:text-3xl font-bold tracking-tight text-muted-foreground/60 hover:text-foreground transition-colors"
              >
                {t}
                <span className="mx-8 text-purple-500/40">◆</span>
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
              Have an idea?{' '}
              <span className="gradient-text italic">Let&apos;s make it real.</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-xl mx-auto mb-8">
              Book a discovery call. We&apos;ll tell you honestly whether the
              project makes sense — and how we&apos;d ship it.
            </p>
            <div className="flex flex-wrap gap-4 justify-center">
              <Link to="/contact">
                <Button
                  size="lg"
                  className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 h-12 px-8"
                >
                  Get in touch
                </Button>
              </Link>
              <Link to="/services">
                <Button
                  size="lg"
                  variant="outline"
                  className="h-12 px-8 !bg-transparent border-white/20 hover:border-white/40"
                >
                  View services
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}