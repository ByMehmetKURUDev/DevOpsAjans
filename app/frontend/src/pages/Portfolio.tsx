import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';

const client = createClient();

interface Project {
  id: number | string;
  title: string;
  description: string;
  category: string;
  image_url?: string;
  project_url?: string;
  client_name?: string;
  status?: string;
  tech_stack?: string;
  featured?: boolean;
}

const STATIC_PROJECTS: Project[] = [
  // SaaS
  { id: 's1', title: 'Airtag Cards', description: 'Digital business card SaaS platform', category: 'SaaS', project_url: 'https://airtag.cards', featured: true },
  { id: 's2', title: 'StartHub', description: 'Startup management and collaboration platform', category: 'SaaS', project_url: 'https://starthub.llc' },
  { id: 's3', title: 'WorkApp', description: 'Workforce management and productivity SaaS', category: 'SaaS', project_url: 'https://workapp.llc' },
  { id: 's4', title: 'Mentalist', description: 'AI-powered mentoring and coaching platform', category: 'SaaS', project_url: 'https://mentalist.llc' },
  { id: 's5', title: 'Roadrunner Delivery', description: 'Logistics and delivery management system', category: 'SaaS', project_url: 'https://roadrunner.delivery' },
  { id: 's6', title: 'Mastermind', description: 'Business mastermind group management platform', category: 'SaaS', project_url: 'https://mastermind.llc' },
  // E-Ticaret
  { id: 'e1', title: 'Watermaker Market', description: 'E-commerce platform for water purification products', category: 'E-Ticaret', project_url: 'https://watermaker.market', featured: true },
  // Website
  { id: 'w1', title: 'FSM Watermakers', description: 'Corporate website for water purification company', category: 'Website', project_url: 'https://fsmwatermakers.com' },
  { id: 'w2', title: 'Acemi Tesisatçı', description: 'Plumbing services and information website', category: 'Website', project_url: 'https://acemitesisatci.com' },
  // Mobil Uygulama
  { id: 'm1', title: 'Airtag Cards Mobile', description: 'Mobile app for digital business cards', category: 'Mobil Uygulama', project_url: 'https://airtag.cards' },
  { id: 'm2', title: 'WorkApp Mobile', description: 'Mobile workforce management application', category: 'Mobil Uygulama', project_url: 'https://workapp.llc' },
  { id: 'm3', title: 'Watermaker Mobile', description: 'Mobile shopping app for water products', category: 'Mobil Uygulama', project_url: 'https://watermaker.market' },
  { id: 'm4', title: 'FSM Watermakers Mobile', description: 'Mobile app for FSM Watermakers services', category: 'Mobil Uygulama', project_url: 'https://fsmwatermaker.com' },
];

const CATEGORIES_KEYS = ['all', 'SaaS', 'E-Ticaret', 'Website', 'Mobil Uygulama'];

export default function Portfolio() {
  const { t } = useTranslation();
  const [dbProjects, setDbProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCat, setActiveCat] = useState('all');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    client.entities.projects
      .queryAll({ sort: '-featured', limit: 100 })
      .then((res) => {
        if (cancelled) return;
        const items = (res?.data?.items ?? []) as Project[];
        setDbProjects(items);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const allProjects = useMemo(() => {
    return [...STATIC_PROJECTS, ...dbProjects];
  }, [dbProjects]);

  const filtered = useMemo(() => {
    if (activeCat === 'all') return allProjects;
    return allProjects.filter((p) => p.category === activeCat);
  }, [allProjects, activeCat]);

  const getCatLabel = (cat: string) => {
    if (cat === 'all') return t('portfolio.all');
    return cat;
  };

  return (
    <div>
      {/* Header */}
      <section className="py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">{t('portfolio.sectionTag')}</p>
          <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6 max-w-4xl">
            {t('portfolio.title1')}<br />
            <span className="gradient-text">{t('portfolio.titleHighlight')}</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl">
            {t('portfolio.desc')}
          </p>
        </div>
      </section>

      {/* Filter tabs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-10">
        <div className="flex flex-wrap gap-2">
          {CATEGORIES_KEYS.map((cat) => {
            const active = cat === activeCat;
            return (
              <button
                key={cat}
                onClick={() => setActiveCat(cat)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  active
                    ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                    : 'glass text-muted-foreground hover:text-foreground hover:border-purple-500/30'
                }`}
              >
                {getCatLabel(cat)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Grid */}
      <section className="pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {loading ? (
            <div className="py-24 flex items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-3" />
              {t('portfolio.loading')}
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-24 text-center text-muted-foreground">
              {t('portfolio.empty')}
            </div>
          ) : (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {filtered.map((p, i) => (
                <a
                  key={p.id}
                  href={p.project_url || '#'}
                  target={p.project_url ? '_blank' : undefined}
                  rel="noreferrer"
                  className={`group relative rounded-2xl overflow-hidden glass hover:border-purple-500/40 transition-all duration-500 hover:-translate-y-1 ${
                    p.featured && i === 0 ? 'md:col-span-2 md:row-span-1' : ''
                  }`}
                >
                  <div className="relative aspect-[16/10] overflow-hidden bg-gradient-to-br from-purple-950/40 to-pink-950/40">
                    {p.image_url ? (
                      <img
                        src={p.image_url}
                        alt={p.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-4xl gradient-text font-bold">
                        {p.title.charAt(0)}
                      </div>
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent" />
                    {p.featured && (
                      <div className="absolute top-4 left-4 px-2.5 py-1 rounded-full bg-purple-500/90 text-white text-[10px] uppercase tracking-widest font-semibold">
                        {t('portfolio.featured')}
                      </div>
                    )}
                    {p.status === 'in_progress' && (
                      <div className="absolute top-4 right-4 px-2.5 py-1 rounded-full bg-cyan-500/90 text-white text-[10px] uppercase tracking-widest font-semibold">
                        {t('portfolio.inProgress')}
                      </div>
                    )}
                  </div>
                  <div className="p-6">
                    <div className="flex items-center justify-between mb-2 text-xs text-muted-foreground">
                      <span className="uppercase tracking-widest">{p.category}</span>
                      {p.project_url && <ExternalLink className="h-3.5 w-3.5" />}
                    </div>
                    <h3 className="text-xl font-semibold mb-2 group-hover:gradient-text transition-all">
                      {p.title}
                    </h3>
                    <p className="text-sm text-muted-foreground line-clamp-2 mb-4">
                      {p.description}
                    </p>
                    {p.tech_stack && (
                      <div className="flex flex-wrap gap-1.5">
                        {p.tech_stack
                          .split(',')
                          .slice(0, 4)
                          .map((tech) => (
                            <span
                              key={tech}
                              className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-full bg-white/5 text-muted-foreground"
                            >
                              {tech.trim()}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}