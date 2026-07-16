import { useEffect, useState } from 'react';
import { Loader2, LogIn, ExternalLink, Briefcase, CheckCircle2, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';

const client = createClient();

interface AuthUser {
  id?: string;
  email?: string;
  name?: string;
  [key: string]: unknown;
}

interface Project {
  id: number | string;
  title: string;
  description: string;
  category: string;
  image_url?: string;
  project_url?: string;
  status?: string;
  tech_stack?: string;
  client_name?: string;
  created_at?: string;
}

export default function ClientPanel() {
  const { t } = useTranslation();
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    client.auth
      .me()
      .then((res) => {
        if (res?.data) setUser(res.data as AuthUser);
      })
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    setProjectsLoading(true);
    client.entities.projects
      .query({ sort: '-created_at', limit: 50 })
      .then((res) => {
        setProjects((res?.data?.items ?? []) as Project[]);
      })
      .catch((e) => setError(e?.message || 'Failed to load your projects'))
      .finally(() => setProjectsLoading(false));
  }, [user]);

  if (authLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="max-w-md text-center p-10 rounded-2xl glass">
          <LogIn className="h-10 w-10 mx-auto text-purple-400 mb-4" />
          <h1 className="text-3xl font-bold mb-3">{t('clientPanel.loginTitle')}</h1>
          <p className="text-muted-foreground mb-6">
            {t('clientPanel.loginDesc')}
          </p>
          <Button
            onClick={() => client.auth.toLogin()}
            className="w-full h-11 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
          >
            {t('nav.signIn')}
          </Button>
        </div>
      </div>
    );
  }

  const stats = {
    total: projects.length,
    active: projects.filter((p) => p.status === 'in_progress').length,
    done: projects.filter((p) => p.status === 'completed').length,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="mb-10">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-2">{t('clientPanel.sectionTag')}</p>
        <h1 className="text-4xl md:text-5xl font-bold">
          {t('clientPanel.title')}<span className="gradient-text">.</span>
        </h1>
        <p className="text-muted-foreground mt-2">
          {t('clientPanel.signedAs')} <span className="text-foreground">{user.email || user.name || 'you'}</span>
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3 mb-10">
        {[
          { label: t('clientPanel.totalProjects'), value: stats.total, icon: Briefcase, color: 'from-purple-600 to-pink-600' },
          { label: t('clientPanel.inProgress'), value: stats.active, icon: Clock, color: 'from-cyan-500 to-purple-600' },
          { label: t('clientPanel.completed'), value: stats.done, icon: CheckCircle2, color: 'from-emerald-500 to-cyan-500' },
        ].map((s) => (
          <div key={s.label} className="p-6 rounded-2xl glass flex items-center gap-4">
            <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${s.color} flex items-center justify-center`}>
              <s.icon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-widest text-muted-foreground">{s.label}</p>
              <p className="text-3xl font-bold">{s.value}</p>
            </div>
          </div>
        ))}
      </div>

      <h2 className="text-2xl font-bold mb-6">{t('clientPanel.yourProjects')}</h2>
      {projectsLoading ? (
        <div className="py-16 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('clientPanel.loading')}
        </div>
      ) : error ? (
        <div className="p-6 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          {error}
        </div>
      ) : projects.length === 0 ? (
        <div className="p-10 rounded-2xl glass text-center">
          <p className="text-muted-foreground mb-4">
            {t('clientPanel.empty')}
          </p>
          <Button
            onClick={() => (window.location.href = '/contact')}
            className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
          >
            {t('clientPanel.startProject')}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4">
          {projects.map((p) => (
            <div key={p.id} className="p-5 rounded-2xl glass flex flex-col md:flex-row gap-5 hover:border-purple-500/40 transition-colors">
              <div className="md:w-48 aspect-video rounded-xl overflow-hidden bg-gradient-to-br from-purple-950/40 to-pink-950/40 shrink-0">
                {p.image_url ? (
                  <img src={p.image_url} alt={p.title} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-3xl font-bold gradient-text">
                    {p.title.charAt(0)}
                  </div>
                )}
              </div>
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className="text-[10px] uppercase tracking-widest text-purple-400">{p.category}</span>
                  <span
                    className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                      p.status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-300'
                        : p.status === 'in_progress'
                        ? 'bg-cyan-500/15 text-cyan-300'
                        : 'bg-white/10 text-muted-foreground'
                    }`}
                  >
                    {p.status || 'planning'}
                  </span>
                </div>
                <h3 className="text-xl font-semibold mb-2">{p.title}</h3>
                <p className="text-sm text-muted-foreground line-clamp-2 mb-3">{p.description}</p>
                {p.tech_stack && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {p.tech_stack.split(',').slice(0, 5).map((tech) => (
                      <span key={tech} className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-full bg-white/5 text-muted-foreground">
                        {tech.trim()}
                      </span>
                    ))}
                  </div>
                )}
                {p.project_url && (
                  <a
                    href={p.project_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-purple-400 hover:text-pink-400 transition-colors"
                  >
                    {t('clientPanel.viewLive')} <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}