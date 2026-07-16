import { Link } from 'react-router-dom';
import {
  Code2,
  Rocket,
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

const CORE_SERVICES = [
  {
    icon: Code2,
    title: 'Custom Web Development',
    tag: 'Engineering',
    desc: 'Full-stack applications built on React, Next.js, TypeScript, and modern backends. Fast, accessible, and boringly reliable.',
    bullets: ['Web apps & SaaS platforms', 'Marketing sites & CMS', 'API & backend systems'],
    gradient: 'from-purple-600 to-pink-600',
  },
  {
    icon: Smartphone,
    title: 'Mobile Applications',
    tag: 'Engineering',
    desc: 'Native-quality iOS and Android apps with React Native + Expo. Shared codebase, platform-native feel.',
    bullets: ['iOS & Android from one codebase', 'App Store & Play Store delivery', 'Offline-first architecture'],
    gradient: 'from-pink-600 to-orange-500',
  },
  {
    icon: ShoppingCart,
    title: 'E-Commerce Platforms',
    tag: 'Engineering',
    desc: 'From Shopify custom themes to fully bespoke multi-vendor marketplaces. Conversion-focused, payment-ready.',
    bullets: ['Custom checkout flows', 'Multi-currency & multi-region', 'Stripe / PayPal integrations'],
    gradient: 'from-cyan-500 to-purple-600',
  },
  {
    icon: Paintbrush,
    title: 'Product & Brand Design',
    tag: 'Design',
    desc: 'Design systems, UI kits, and full brand identities in Figma. Delivered production-ready, not just pretty screens.',
    bullets: ['Design systems in Figma', 'Landing pages & brand sites', 'Motion & interaction design'],
    gradient: 'from-emerald-500 to-cyan-500',
  },
  {
    icon: Search,
    title: 'SEO & Content Strategy',
    tag: 'Growth',
    desc: 'Technical SEO audits, content clusters, and site architecture that actually rank — including for AI answer engines.',
    bullets: ['Technical & on-page SEO', 'Content planning & briefs', 'Answer-engine optimization'],
    gradient: 'from-purple-500 to-cyan-500',
  },
  {
    icon: BarChart3,
    title: 'Paid Ads & Growth',
    tag: 'Growth',
    desc: 'Google, Meta, LinkedIn, TikTok. Creative, campaigns, tracking, and honest reporting you can act on.',
    bullets: ['Full-funnel paid strategy', 'Creative production', 'GA4 + server-side tracking'],
    gradient: 'from-pink-500 to-purple-600',
  },
];

const PACKAGES = [
  {
    name: 'Sprint',
    price: 'From $8k',
    duration: '2–3 weeks',
    desc: 'A single, tightly-scoped deliverable. Landing page, MVP feature, or brand refresh.',
    features: ['Kickoff workshop', 'Design + build', 'One senior lead', 'Weekly demos', 'Launch handoff'],
    highlight: false,
  },
  {
    name: 'Studio',
    price: 'From $28k',
    duration: '6–10 weeks',
    desc: 'Full product engagement. New app, redesign, or major release. Design + engineering.',
    features: ['Everything in Sprint', 'Design system', 'Multi-page or multi-screen product', 'Analytics + SEO setup', 'Post-launch support'],
    highlight: true,
  },
  {
    name: 'Retainer',
    price: 'From $6k/mo',
    duration: 'Ongoing',
    desc: 'Continuous product + marketing partnership. For teams shipping every week.',
    features: ['Dedicated senior time', 'Weekly production releases', 'Growth experiments', 'Priority support', 'Quarterly strategy'],
    highlight: false,
  },
];

export default function Services() {
  return (
    <div>
      {/* Header */}
      <section className="py-24 md:py-32 text-center max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">Services</p>
        <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6">
          Everything you need to <span className="gradient-text">ship &amp; grow</span>.
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          Six deeply-integrated services under one senior lead. Pick one — or
          combine them into a single accountable engagement.
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
            <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">How we work</p>
            <h2 className="text-4xl md:text-5xl font-bold mb-4">Three ways to engage.</h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              Every engagement is scoped in writing before we start. No surprises,
              no scope creep, no “more slides please.”
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
                    Most popular
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
                    Start conversation <ArrowRight className="h-4 w-4" />
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
            Not sure which fits?
          </h2>
          <p className="text-muted-foreground mb-8">
            Send a paragraph about the problem. We&apos;ll reply with an honest
            first-take within 24 hours.
          </p>
          <Link to="/contact">
            <Button size="lg" className="bg-gradient-to-r from-purple-600 to-pink-600 text-white h-12 px-8">
              Tell us about your project
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}