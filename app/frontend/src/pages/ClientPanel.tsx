import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2,
  LogIn,
  ExternalLink,
  Briefcase,
  CheckCircle2,
  Clock,
  Receipt,
  MessageSquare,
  UserCog,
  Send,
  UserPlus,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import ProjectTimeline from '@/components/ProjectTimeline';
import { useStageLabels } from '@/lib/projectEvents';
import { client } from '@/lib/sdkClient';
import { useSiteSettings } from '@/lib/siteSettings';


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
  stage?: string;
  progress?: number;
  tech_stack?: string;
  client_name?: string;
  client_email?: string;
  created_at?: string;
}

interface Invoice {
  id: number | string;
  invoice_no: string;
  client_email?: string;
  description?: string;
  amount: number;
  currency?: string;
  status?: string;
  issue_date?: string;
  due_date?: string;
}

interface Ticket {
  id: number | string;
  client_email?: string;
  client_name?: string;
  subject: string;
  message: string;
  reply?: string;
  status?: string;
  priority?: string;
  created_at?: string;
}

type Tab = 'projects' | 'invoices' | 'tickets' | 'profile';


export default function ClientPanel() {
  const { t } = useTranslation();
  const stageLabel = useStageLabels();
  const { settings } = useSiteSettings();

  /** Durum kodunu seçili dile çevirir; karşılığı yoksa ham kodu gösterir. */
  const statusLabel = (status?: string, fallbackKey = 'planning') =>
    t(`ui.status.${status || fallbackKey}`, { defaultValue: status || '' });
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tab, setTab] = useState<Tab>('projects');

  const [projects, setProjects] = useState<Project[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState('');

  const [ticketForm, setTicketForm] = useState({ subject: '', message: '' });
  const [sending, setSending] = useState(false);

  const [profile, setProfile] = useState({ name: '', phone: '', company: '' });

  useEffect(() => {
    client.auth
      .me()
      .then((res) => {
        if (res?.data) setUser(res.data as AuthUser);
      })
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);

  const email = (user?.email || '').toLowerCase();

  useEffect(() => {
    if (!user) return;
    try {
      const raw = window.localStorage.getItem(`mk_profile_${email}`);
      if (raw) setProfile(JSON.parse(raw));
      else
        setProfile({
          name: (user.name as string) || '',
          phone: '',
          company: '',
        });
    } catch {
      /* yoksay */
    }
  }, [user, email]);

  const loadData = useCallback(async () => {
    if (!email) return;
    setDataLoading(true);
    setError('');
    try {
      const [pRes, iRes, tRes] = await Promise.all([
        client.entities.projects.query({ sort: '-created_at', limit: 100 }),
        client.entities.invoices.query({ sort: '-created_at', limit: 100 }),
        client.entities.support_tickets.query({
          sort: '-created_at',
          limit: 100,
        }),
      ]);
      const allProjects = (pRes?.data?.items ?? []) as Project[];
      const allInvoices = (iRes?.data?.items ?? []) as Invoice[];
      const allTickets = (tRes?.data?.items ?? []) as Ticket[];

      setProjects(
        allProjects.filter(
          (p) => (p.client_email || '').toLowerCase() === email
        )
      );
      setInvoices(
        allInvoices.filter(
          (i) => (i.client_email || '').toLowerCase() === email
        )
      );
      setTickets(
        allTickets.filter((t) => (t.client_email || '').toLowerCase() === email)
      );
    } catch (e) {
      const err = e as { message?: string };
      setError(err?.message || t('ui.dataLoadError'));
    } finally {
      setDataLoading(false);
    }
  }, [email]);

  useEffect(() => {
    if (user) loadData();
  }, [user, loadData]);

  const submitTicket = async () => {
    if (!ticketForm.subject.trim() || !ticketForm.message.trim()) {
      toast.error(t('ui.ticketRequired'));
      return;
    }
    setSending(true);
    try {
      await client.entities.support_tickets.create({
        data: {
          client_email: email,
          client_name: profile.name || user?.name || email,
          subject: ticketForm.subject.trim(),
          message: ticketForm.message.trim(),
          status: 'open',
          priority: 'normal',
        },
      });
      toast.success(t('ui.ticketSent'));
      setTicketForm({ subject: '', message: '' });
      loadData();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('ui.ticketSendError'));
    } finally {
      setSending(false);
    }
  };

  const saveProfile = () => {
    try {
      window.localStorage.setItem(
        `mk_profile_${email}`,
        JSON.stringify(profile)
      );
      toast.success(t('ui.profileSaved'));
    } catch {
      toast.error(t('ui.profileSaveError'));
    }
  };

  const stats = useMemo(
    () => ({
      total: projects.length,
      active: projects.filter((p) => p.status === 'in_progress').length,
      done: projects.filter((p) => p.status === 'completed').length,
      openInvoices: invoices.filter((i) => i.status !== 'paid').length,
    }),
    [projects, invoices]
  );

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
          <h1 className="text-3xl font-bold mb-3">{t('ui.clientPanelTitle')}</h1>
          <p className="text-muted-foreground mb-6">
            {t('clientPanel.loginDesc')}
          </p>
          <div className="space-y-3">
            <Button
              onClick={() => client.auth.toLogin()}
              className="w-full h-11 gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
            >
              <LogIn className="h-4 w-4" /> {t('nav.signIn')}
            </Button>
            <Button
              onClick={() => client.auth.toLogin()}
              variant="outline"
              className="w-full h-11 gap-2 !bg-transparent !hover:bg-transparent border-white/20 text-foreground"
            >
              <UserPlus className="h-4 w-4" /> {t('nav.signUp')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const TABS: { key: Tab; label: string; icon: typeof Briefcase }[] = [
    { key: 'projects', label: t('ui.tabMyProjects'), icon: Briefcase },
    { key: 'invoices', label: t('ui.tabInvoices'), icon: Receipt },
    { key: 'tickets', label: t('ui.tabSupport'), icon: MessageSquare },
    { key: 'profile', label: t('ui.tabProfile'), icon: UserCog },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="mb-10">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-2">
          {t('ui.clientPanelTitle')}
        </p>
        <h1 className="text-4xl md:text-5xl font-bold">
          {t('ui.controlCenter')} <span className="gradient-text">{t('ui.controlCenterHighlight')}</span>
        </h1>
        <p className="text-muted-foreground mt-2">
          {t('ui.session')}:{' '}
          <span className="text-foreground">
            {user.email || user.name}
          </span>
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-10">
        {[
          {
            label: t('ui.statTotalProjects'),
            value: stats.total,
            icon: Briefcase,
            color: 'from-purple-600 to-pink-600',
          },
          {
            label: t('ui.statInProgress'),
            value: stats.active,
            icon: Clock,
            color: 'from-cyan-500 to-purple-600',
          },
          {
            label: t('ui.statCompleted'),
            value: stats.done,
            icon: CheckCircle2,
            color: 'from-emerald-500 to-cyan-500',
          },
          {
            label: t('ui.statUnpaidInvoices'),
            value: stats.openInvoices,
            icon: Receipt,
            color: 'from-orange-500 to-pink-500',
          },
        ].map((s) => (
          <div
            key={s.label}
            className="p-6 rounded-2xl glass flex items-center gap-4"
          >
            <div
              className={`w-12 h-12 rounded-xl bg-gradient-to-br ${s.color} flex items-center justify-center shrink-0`}
            >
              <s.icon className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-widest text-muted-foreground">
                {s.label}
              </p>
              <p className="text-3xl font-bold">{s.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-8 border-b border-white/10 overflow-x-auto">
        {TABS.map((tItem) => (
          <button
            key={tItem.key}
            onClick={() => setTab(tItem.key)}
            className={`px-5 py-3 text-sm font-medium transition-colors relative inline-flex items-center gap-2 whitespace-nowrap ${
              tab === tItem.key
                ? 'text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <tItem.icon className="h-4 w-4" />
            {tItem.label}
            {tab === tItem.key && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />
            )}
          </button>
        ))}
      </div>

      {dataLoading ? (
        <div className="py-16 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('ui.loading')}
        </div>
      ) : error ? (
        <div className="p-6 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          {error}
          <Button
            onClick={loadData}
            variant="outline"
            size="sm"
            className="ml-4 !bg-transparent border-white/20"
          >
            {t('ui.retry')}
          </Button>
        </div>
      ) : (
        <>
          {tab === 'projects' && (
            <div className="grid gap-4">
              {projects.length === 0 ? (
                <div className="p-10 rounded-2xl glass text-center">
                  <p className="text-muted-foreground mb-4">
                    {t('ui.noProjectsDesc')}
                  </p>
                  <Button
                    onClick={() => (window.location.href = '/contact')}
                    className="bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    {t('ui.startProject')}
                  </Button>
                </div>
              ) : (
                projects.map((p) => (
                  <div
                    key={p.id}
                    className="p-5 rounded-2xl glass flex flex-col md:flex-row gap-5 hover:border-purple-500/40 transition-colors"
                  >
                    <div className="md:w-48 aspect-video rounded-xl overflow-hidden bg-gradient-to-br from-purple-950/40 to-pink-950/40 shrink-0">
                      {p.image_url ? (
                        <img
                          src={p.image_url}
                          alt={p.title}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-3xl font-bold gradient-text">
                          {p.title.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className="text-[10px] uppercase tracking-widest text-purple-400">
                          {p.category}
                        </span>
                        <span
                          className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                            p.status === 'completed'
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : p.status === 'in_progress'
                                ? 'bg-cyan-500/15 text-cyan-300'
                                : 'bg-white/10 text-muted-foreground'
                          }`}
                        >
                          {statusLabel(p.status, 'planning')}
                        </span>
                      </div>
                      <h3 className="text-xl font-semibold mb-2">{p.title}</h3>
                      <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                        {p.description}
                      </p>

                      {/* Aşama & ilerleme */}
                      <div className="mb-3">
                        <div className="flex items-center justify-between text-xs mb-1.5">
                          <span className="text-muted-foreground">
                            {t('ui.stage')}: {stageLabel(p.stage) || t('ui.notSet')}
                          </span>
                          <span className="text-purple-300 font-medium">
                            {typeof p.progress === 'number' ? p.progress : 0}%
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all"
                            style={{
                              width: `${Math.min(Math.max(p.progress ?? 0, 0), 100)}%`,
                            }}
                          />
                        </div>
                      </div>

                      {/*
                        Proje geçmişi katlanmış geliyor: müşteri birden çok
                        projeye sahipse liste açıkken okunmaz oluyordu.
                        `details` içeriği HTML'de duruyor, tıklayınca açılıyor.
                      */}
                      <details className="mb-3 rounded-xl border border-white/10 bg-white/[0.02] p-3">
                        <summary className="cursor-pointer text-sm font-semibold text-purple-300 hover:text-pink-300">
                          {t('projectStages.history')}
                        </summary>
                        <div className="mt-4">
                          <ProjectTimeline projectId={Number(p.id)} clientView />
                        </div>
                      </details>

                      {p.tech_stack && (
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {p.tech_stack
                            .split(',')
                            .slice(0, 5)
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
                      {p.project_url && (
                        <a
                          href={p.project_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 text-sm text-purple-400 hover:text-pink-400 transition-colors"
                        >
                          {t('ui.viewLive')}{' '}
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === 'invoices' && (
            <div className="grid gap-3">
              {invoices.length === 0 ? (
                <div className="p-10 rounded-2xl glass text-center text-muted-foreground">
                  {t('ui.noInvoices')}
                </div>
              ) : (
                invoices.map((inv) => (
                  <div
                    key={inv.id}
                    className="p-5 rounded-2xl glass flex flex-wrap items-center gap-4"
                  >
                    <div className="flex-1 min-w-[200px]">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold">{inv.invoice_no}</span>
                        <span
                          className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                            inv.status === 'paid'
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : inv.status === 'overdue'
                                ? 'bg-destructive/15 text-destructive'
                                : 'bg-orange-500/15 text-orange-300'
                          }`}
                        >
                          {statusLabel(inv.status, 'unpaid')}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {inv.description}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {t('ui.issued')}: {inv.issue_date || '—'} • {t('ui.due')}:{' '}
                        {inv.due_date || '—'}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold gradient-text">
                        {inv.amount} {inv.currency || 'USD'}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === 'tickets' && (
            <div className="grid gap-8 lg:grid-cols-2">
              <div className="p-6 rounded-2xl glass h-fit">
                <h3 className="text-lg font-semibold mb-4">
                  {t('ui.newTicket')}
                </h3>
                <div className="space-y-4">
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.subject')} *
                    </Label>
                    <Input
                      value={ticketForm.subject}
                      onChange={(e) =>
                        setTicketForm({
                          ...ticketForm,
                          subject: e.target.value,
                        })
                      }
                      placeholder={t('ui.ticketSubjectPlaceholder')}
                      className="bg-white/5 border-white/10"
                    />
                  </div>
                  <div>
                    <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                      {t('ui.message')} *
                    </Label>
                    <Textarea
                      rows={5}
                      value={ticketForm.message}
                      onChange={(e) =>
                        setTicketForm({
                          ...ticketForm,
                          message: e.target.value,
                        })
                      }
                      placeholder={t('ui.ticketMessagePlaceholder')}
                      className="bg-white/5 border-white/10"
                    />
                  </div>
                  <Button
                    onClick={submitTicket}
                    disabled={sending}
                    className="w-full h-11 gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    {sending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    {t('ui.send')}
                  </Button>
                </div>
              </div>

              <div className="grid gap-3">
                <h3 className="text-lg font-semibold">
                  {t('ui.myTickets')} ({tickets.length})
                </h3>
                {tickets.length === 0 ? (
                  <div className="p-8 rounded-2xl glass text-center text-muted-foreground text-sm">
                    {t('ui.noTickets')}
                  </div>
                ) : (
                  tickets.map((tk) => (
                    <div key={tk.id} className="p-5 rounded-2xl glass">
                      <div className="flex items-center gap-2 mb-2">
                        <h4 className="font-semibold">{tk.subject}</h4>
                        <span
                          className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                            tk.status === 'closed'
                              ? 'bg-white/10 text-muted-foreground'
                              : tk.status === 'answered'
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-pink-500/15 text-pink-300'
                          }`}
                        >
                          {statusLabel(tk.status, 'open')}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                        {tk.message}
                      </p>
                      {tk.reply && (
                        <div className="mt-3 pt-3 border-t border-white/10">
                          <p className="text-xs uppercase tracking-widest text-purple-400 mb-1">
                            {t('ui.reply')}
                          </p>
                          <p className="text-sm text-foreground whitespace-pre-wrap">
                            {tk.reply}
                          </p>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {tab === 'profile' && (
            <div className="max-w-xl p-6 rounded-2xl glass">
              <h3 className="text-lg font-semibold mb-4">{t('ui.profileSettings')}</h3>
              <div className="space-y-4">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('ui.emailReadonly')}
                  </Label>
                  <Input
                    value={user.email || ''}
                    disabled
                    className="bg-white/5 border-white/10 opacity-70"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('ui.fullName')}
                  </Label>
                  <Input
                    value={profile.name}
                    onChange={(e) =>
                      setProfile({ ...profile, name: e.target.value })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('ui.phone')}
                  </Label>
                  <Input
                    value={profile.phone}
                    onChange={(e) =>
                      setProfile({ ...profile, phone: e.target.value })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('ui.company')}
                  </Label>
                  <Input
                    value={profile.company}
                    onChange={(e) =>
                      setProfile({ ...profile, company: e.target.value })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <Button
                  onClick={saveProfile}
                  className="h-11 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  {t('ui.save')}
                </Button>
                <p className="text-xs text-muted-foreground pt-2 border-t border-white/10">
                  {t('ui.forQuestions')}:{' '}
                  <a
                    href={`mailto:${settings.contact_email}`}
                    className="text-purple-400 hover:text-pink-400"
                  >
                    {settings.contact_email}
                  </a>
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}