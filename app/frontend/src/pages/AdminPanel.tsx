import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import {
  Loader2,
  LogIn,
  Plus,
  Trash2,
  Edit3,
  X,
  Mail,
  CheckCircle2,
  Settings2,
  BarChart3,
  Users,
  Receipt,
  MessageSquare,
  FolderKanban,
  Newspaper,
  Save,
  ShieldAlert,
  Languages,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { createClient } from '@metagptx/web-sdk';
import {
  SETTING_GROUPS,
  fetchSettingRows,
  saveSiteSetting,
  useSiteSettings,
  isAdminUser,
  localizedSettingKey,
  type SettingRow,
} from '@/lib/siteSettings';
import { SUPPORTED_LANGUAGES } from '@/i18n';

// Analitik panosu recharts'a bağlı olduğu için yalnızca sekme açıldığında indirilir.
const AnalyticsDashboard = lazy(() => import('@/components/AnalyticsDashboard'));

/** Ayar formundaki dil sekmeleri: varsayılan + desteklenen 7 dil. */
const SETTING_LANG_OPTIONS = [
  { code: 'base', label: 'Varsayılan', flag: '🌐' },
  ...SUPPORTED_LANGUAGES.map((l) => ({
    code: l.code,
    label: l.full,
    flag: l.flag,
  })),
];

const client = createClient();

interface AuthUser {
  id?: string;
  email?: string;
  name?: string;
  role?: string;
  [key: string]: unknown;
}

interface Project {
  id: number | string;
  title: string;
  description: string;
  category: string;
  image_url?: string;
  project_url?: string;
  client_name?: string;
  client_email?: string;
  status?: string;
  stage?: string;
  progress?: number;
  tech_stack?: string;
  featured?: boolean;
  created_at?: string;
}

interface BlogPost {
  id: number | string;
  title: string;
  slug: string;
  excerpt?: string;
  content?: string;
  cover_image?: string;
  author?: string;
  category?: string;
  published?: boolean;
}

interface Inquiry {
  id: number | string;
  name: string;
  email: string;
  phone?: string;
  subject?: string;
  message: string;
  status?: string;
  created_at?: string;
}

interface Invoice {
  id: number | string;
  invoice_no: string;
  client_name?: string;
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
  client_name?: string;
  client_email?: string;
  subject: string;
  message: string;
  reply?: string;
  status?: string;
  priority?: string;
  created_at?: string;
}

type Tab =
  | 'analytics'
  | 'settings'
  | 'projects'
  | 'blog'
  | 'clients'
  | 'invoices'
  | 'tickets'
  | 'inquiries';

const emptyProject: Partial<Project> = {
  title: '',
  description: '',
  category: 'Website',
  image_url: '',
  project_url: '',
  client_name: '',
  client_email: '',
  status: 'in_progress',
  stage: 'Tasarım',
  progress: 0,
  tech_stack: '',
  featured: false,
};

const emptyPost: Partial<BlogPost> = {
  title: '',
  slug: '',
  excerpt: '',
  content: '',
  cover_image: '',
  author: 'Mehmet KURU',
  category: 'Website',
  published: true,
};

const emptyInvoice: Partial<Invoice> = {
  invoice_no: '',
  client_name: '',
  client_email: '',
  description: '',
  amount: 0,
  currency: 'USD',
  status: 'unpaid',
  issue_date: '',
  due_date: '',
};

export default function AdminPanel() {
  const { t } = useTranslation();
  const { settings, rawSettings, reload: reloadSettings } = useSiteSettings();
  const [settingLang, setSettingLang] = useState<string>('base');

  /** Seçili dile göre kaydedilecek/okunacak ayar anahtarını verir. */
  const effectiveSettingKey = (field: { key: string; translatable?: boolean }) =>
    field.translatable && settingLang !== 'base'
      ? localizedSettingKey(field.key, settingLang)
      : field.key;
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tab, setTab] = useState<Tab>('analytics');

  const [projects, setProjects] = useState<Project[]>([]);
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(false);

  const [editProject, setEditProject] = useState<Partial<Project> | null>(null);
  const [editPost, setEditPost] = useState<Partial<BlogPost> | null>(null);
  const [editInvoice, setEditInvoice] = useState<Partial<Invoice> | null>(null);
  const [replyTicket, setReplyTicket] = useState<Ticket | null>(null);
  const [replyText, setReplyText] = useState('');

  const [settingRows, setSettingRows] = useState<SettingRow[]>([]);
  const [settingDraft, setSettingDraft] = useState<Record<string, string>>({});
  const [savingSettings, setSavingSettings] = useState(false);

  useEffect(() => {
    client.auth
      .me()
      .then((res) => {
        if (res?.data) setUser(res.data as AuthUser);
      })
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);

  const isAdmin = isAdminUser(user, settings);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [pRes, bRes, iRes, invRes, tRes] = await Promise.all([
        client.entities.projects.query({ sort: '-created_at', limit: 200 }),
        client.entities.blog_posts.query({ sort: '-created_at', limit: 200 }),
        client.entities.inquiries.query({ sort: '-created_at', limit: 200 }),
        client.entities.invoices.query({ sort: '-created_at', limit: 200 }),
        client.entities.support_tickets.query({
          sort: '-created_at',
          limit: 200,
        }),
      ]);
      setProjects((pRes?.data?.items ?? []) as Project[]);
      setPosts((bRes?.data?.items ?? []) as BlogPost[]);
      setInquiries((iRes?.data?.items ?? []) as Inquiry[]);
      setInvoices((invRes?.data?.items ?? []) as Invoice[]);
      setTickets((tRes?.data?.items ?? []) as Ticket[]);
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.loadError'));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const rows = await fetchSettingRows();
      setSettingRows(rows);
      const draft: Record<string, string> = {};
      SETTING_GROUPS.forEach((g) =>
        g.fields.forEach((f) => {
          const row = rows.find((r) => r.setting_key === f.key);
          draft[f.key] = row?.setting_value ?? rawSettings[f.key] ?? '';
          if (f.translatable) {
            SUPPORTED_LANGUAGES.forEach((lng) => {
              const lk = localizedSettingKey(f.key, lng.code);
              const lrow = rows.find((r) => r.setting_key === lk);
              draft[lk] = lrow?.setting_value ?? rawSettings[lk] ?? '';
            });
          }
        })
      );
      setSettingDraft(draft);
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.settingsLoadError'));
    }
  }, [rawSettings]);

  useEffect(() => {
    if (user && isAdmin) {
      loadAll();
      loadSettings();
    }
  }, [user, isAdmin, loadAll, loadSettings]);

  /* ---------------- Ayarlar ---------------- */
  const saveSettingsGroup = async (groupKey: string) => {
    const group = SETTING_GROUPS.find((g) => g.group === groupKey);
    if (!group) return;
    setSavingSettings(true);
    try {
      for (const field of group.fields) {
        const key = effectiveSettingKey(field);
        const value = settingDraft[key] ?? '';
        const current = settingRows.find((r) => r.setting_key === key);
        if ((current?.setting_value ?? '') !== value) {
          await saveSiteSetting(
            settingRows,
            key,
            value,
            group.group,
            key === field.key
              ? t(field.label)
              : `${t(field.label)} (${settingLang.toUpperCase()})`
          );
        }
      }
      toast.success(t('admin.settingsSaved', { group: t(group.title) }));
      await loadSettings();
      await reloadSettings();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.settingsSaveError'));
    } finally {
      setSavingSettings(false);
    }
  };

  /* ---------------- Portföy ---------------- */
  const saveProject = async () => {
    if (!editProject) return;
    if (
      !editProject.title ||
      !editProject.description ||
      !editProject.category
    ) {
      toast.error(t('admin.projectRequired'));
      return;
    }
    try {
      const payload = {
        title: editProject.title,
        description: editProject.description,
        category: editProject.category,
        image_url: editProject.image_url || '',
        project_url: editProject.project_url || '',
        client_name: editProject.client_name || '',
        client_email: (editProject.client_email || '').toLowerCase(),
        status: editProject.status || 'in_progress',
        stage: editProject.stage || '',
        progress: Number(editProject.progress) || 0,
        tech_stack: editProject.tech_stack || '',
        featured: !!editProject.featured,
      };
      if (editProject.id) {
        await client.entities.projects.update({
          id: String(editProject.id),
          data: payload,
        });
        toast.success(t('admin.projectUpdated'));
      } else {
        await client.entities.projects.create({ data: payload });
        toast.success(t('admin.projectCreated'));
      }
      setEditProject(null);
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.projectSaveError'));
    }
  };

  const deleteProject = async (id: number | string) => {
    if (!confirm(t('admin.confirmDeleteProject'))) return;
    try {
      await client.entities.projects.delete({ id: String(id) });
      toast.success(t('admin.projectDeleted'));
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.deleteFailed'));
    }
  };

  /* ---------------- Blog ---------------- */
  const savePost = async () => {
    if (!editPost) return;
    if (!editPost.title || !editPost.slug || !editPost.content) {
      toast.error(t('admin.postRequired'));
      return;
    }
    try {
      const payload = {
        title: editPost.title,
        slug: editPost.slug,
        excerpt: editPost.excerpt || '',
        content: editPost.content,
        cover_image: editPost.cover_image || '',
        author: editPost.author || 'Mehmet KURU',
        category: editPost.category || 'Website',
        published: editPost.published !== false,
      };
      if (editPost.id) {
        await client.entities.blog_posts.update({
          id: String(editPost.id),
          data: payload,
        });
        toast.success(t('admin.postUpdated'));
      } else {
        await client.entities.blog_posts.create({ data: payload });
        toast.success(t('admin.postCreated'));
      }
      setEditPost(null);
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.postSaveError'));
    }
  };

  const deletePost = async (id: number | string) => {
    if (!confirm(t('admin.confirmDeletePost'))) return;
    try {
      await client.entities.blog_posts.delete({ id: String(id) });
      toast.success(t('admin.postDeleted'));
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.deleteFailed'));
    }
  };

  /* ---------------- Fatura ---------------- */
  const saveInvoice = async () => {
    if (!editInvoice) return;
    if (!editInvoice.invoice_no || !editInvoice.amount) {
      toast.error(t('admin.invoiceRequired'));
      return;
    }
    try {
      const payload = {
        invoice_no: editInvoice.invoice_no,
        client_name: editInvoice.client_name || '',
        client_email: (editInvoice.client_email || '').toLowerCase(),
        description: editInvoice.description || '',
        amount: Number(editInvoice.amount),
        currency: editInvoice.currency || 'USD',
        status: editInvoice.status || 'unpaid',
        issue_date: editInvoice.issue_date || '',
        due_date: editInvoice.due_date || '',
      };
      if (editInvoice.id) {
        await client.entities.invoices.update({
          id: String(editInvoice.id),
          data: payload,
        });
        toast.success(t('admin.invoiceUpdated'));
      } else {
        await client.entities.invoices.create({ data: payload });
        toast.success(t('admin.invoiceCreated'));
      }
      setEditInvoice(null);
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.invoiceSaveError'));
    }
  };

  const deleteInvoice = async (id: number | string) => {
    if (!confirm(t('admin.confirmDeleteInvoice'))) return;
    try {
      await client.entities.invoices.delete({ id: String(id) });
      toast.success(t('admin.invoiceDeleted'));
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.deleteFailed'));
    }
  };

  /* ---------------- Destek ---------------- */
  const sendReply = async () => {
    if (!replyTicket) return;
    if (!replyText.trim()) {
      toast.error(t('admin.replyEmpty'));
      return;
    }
    try {
      await client.entities.support_tickets.update({
        id: String(replyTicket.id),
        data: { reply: replyText.trim(), status: 'answered' },
      });
      toast.success(t('admin.replySent'));
      setReplyTicket(null);
      setReplyText('');
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.replySendError'));
    }
  };

  const markInquiryResolved = async (inq: Inquiry) => {
    try {
      await client.entities.inquiries.update({
        id: String(inq.id),
        data: { status: 'resolved' },
      });
      toast.success(t('admin.markedResolved'));
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.updateFailed'));
    }
  };

  /* ---------------- Render ---------------- */
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
          <h1 className="text-3xl font-bold mb-3">{t('ui.adminPanelTitle')}</h1>
          <p className="text-muted-foreground mb-6">
            {t('adminPanel.loginDesc')}
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

  if (!isAdmin) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        <div className="max-w-md text-center p-10 rounded-2xl glass">
          <ShieldAlert className="h-10 w-10 mx-auto text-pink-400 mb-4" />
          <h1 className="text-2xl font-bold mb-3">{t('ui.noAccess')}</h1>
          <p className="text-muted-foreground mb-6">
            {t('clientPanel.loginDesc')}
          </p>
          <Button
            onClick={() => (window.location.href = '/client')}
            className="w-full h-11 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
          >
            {t('ui.goToClientPanel')}
          </Button>
        </div>
      </div>
    );
  }

  const clientList = Array.from(
    new Map(
      [
        ...projects.map((p) => ({
          email: (p.client_email || '').toLowerCase(),
          name: p.client_name || '',
        })),
        ...invoices.map((i) => ({
          email: (i.client_email || '').toLowerCase(),
          name: i.client_name || '',
        })),
        ...tickets.map((t) => ({
          email: (t.client_email || '').toLowerCase(),
          name: t.client_name || '',
        })),
      ]
        .filter((c) => c.email)
        .map((c) => [c.email, c])
    ).values()
  );

  const TABS: { key: Tab; label: string; icon: typeof BarChart3 }[] = [
    { key: 'analytics', label: t('ui.tabAnalytics'), icon: BarChart3 },
    { key: 'settings', label: t('ui.tabSettings'), icon: Settings2 },
    { key: 'projects', label: t('ui.tabPortfolio'), icon: FolderKanban },
    { key: 'blog', label: t('ui.blog'), icon: Newspaper },
    { key: 'clients', label: t('ui.tabClients'), icon: Users },
    { key: 'invoices', label: t('ui.tabInvoices'), icon: Receipt },
    { key: 'tickets', label: t('ui.tabSupport'), icon: MessageSquare },
    { key: 'inquiries', label: t('ui.tabInquiries'), icon: Mail },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-2">
            {t('ui.management')}
          </p>
          <h1 className="text-4xl md:text-5xl font-bold">
            {t('ui.controlCenter')} <span className="gradient-text">{t('ui.controlCenterHighlight')}</span>
          </h1>
        </div>
        <div className="text-sm text-muted-foreground">
          {t('ui.session')}:{' '}
          <span className="text-foreground">{user.email || user.name}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-8 border-b border-white/10 overflow-x-auto">
        {TABS.map((tItem) => (
          <button
            key={tItem.key}
            onClick={() => setTab(tItem.key)}
            className={`px-4 py-3 text-sm font-medium transition-colors relative inline-flex items-center gap-2 whitespace-nowrap ${
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

      {tab === 'analytics' && (
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-20 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          }
        >
          <AnalyticsDashboard ga4Id={settings.ga4_measurement_id} />
        </Suspense>
      )}

      {tab === 'settings' && (
        <div className="space-y-6">
          <div className="p-5 rounded-2xl glass">
            <div className="flex items-center gap-2 mb-1">
              <Languages className="h-4 w-4 text-purple-300" />
              <h3 className="text-sm font-semibold">{t('ui.contentLanguage')}</h3>
            </div>
            <p className="text-xs text-muted-foreground mb-4">
              {t('admin.langHint')}
            </p>
            <div className="flex flex-wrap gap-2">
              {SETTING_LANG_OPTIONS.map((opt) => (
                <button
                  key={opt.code}
                  onClick={() => setSettingLang(opt.code)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors inline-flex items-center gap-1.5 border ${
                    settingLang === opt.code
                      ? 'bg-purple-500/20 border-purple-400/50 text-foreground'
                      : 'border-white/10 text-muted-foreground hover:text-foreground hover:bg-white/5'
                  }`}
                >
                  <span>{opt.flag}</span>
                  {opt.code === 'base' ? t('admin.default') : opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {SETTING_GROUPS.map((group) => (
              <div key={group.group} className="p-6 rounded-2xl glass">
                <h3 className="text-lg font-semibold mb-1">{t(group.title)}</h3>
                <p className="text-xs text-muted-foreground mb-5">
                  {t(group.description)}
                </p>
                <div className="space-y-4">
                  {group.fields.map((field) => {
                    const fieldKey = effectiveSettingKey(field);
                    const isLocalized = fieldKey !== field.key;
                    const fallback = settingDraft[field.key] ?? '';
                    return (
                      <div key={fieldKey}>
                        <Label className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
                          {t(field.label)}
                          {field.translatable && (
                            <span className="normal-case tracking-normal text-[10px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-200">
                              {isLocalized ? settingLang.toUpperCase() : t('admin.default')}
                            </span>
                          )}
                        </Label>
                        {field.multiline ? (
                          <Textarea
                            rows={3}
                            value={settingDraft[fieldKey] ?? ''}
                            placeholder={isLocalized ? fallback : undefined}
                            onChange={(e) =>
                              setSettingDraft({
                                ...settingDraft,
                                [fieldKey]: e.target.value,
                              })
                            }
                            className="bg-white/5 border-white/10"
                          />
                        ) : (
                          <Input
                            value={settingDraft[fieldKey] ?? ''}
                            placeholder={isLocalized ? fallback : undefined}
                            onChange={(e) =>
                              setSettingDraft({
                                ...settingDraft,
                                [fieldKey]: e.target.value,
                              })
                            }
                            className="bg-white/5 border-white/10"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
                <Button
                  onClick={() => saveSettingsGroup(group.group)}
                  disabled={savingSettings}
                  className="mt-6 h-10 gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  {savingSettings ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  {t('admin.saveBtn')}
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && tab !== 'analytics' && tab !== 'settings' ? (
        <div className="py-16 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('ui.loading')}
        </div>
      ) : (
        <>
          {tab === 'projects' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold">
                  {t('ui.tabPortfolio')} ({projects.length})
                </h2>
                <Button
                  onClick={() => setEditProject({ ...emptyProject })}
                  className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  <Plus className="h-4 w-4" /> {t('admin.newProjectBtn')}
                </Button>
              </div>
              <div className="grid gap-3">
                {projects.map((p) => (
                  <div
                    key={p.id}
                    className="p-4 rounded-xl glass flex items-center gap-4"
                  >
                    <div className="w-20 h-14 rounded-lg overflow-hidden bg-white/5 shrink-0">
                      {p.image_url && (
                        <img
                          src={p.image_url}
                          alt=""
                          className="w-full h-full object-cover"
                        />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-[10px] uppercase tracking-widest text-purple-400">
                          {p.category}
                        </p>
                        {p.featured && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300">
                            {t('admin.featured')}
                          </span>
                        )}
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-muted-foreground">
                          {p.progress ?? 0}%
                        </span>
                      </div>
                      <h3 className="font-semibold truncate">{p.title}</h3>
                      <p className="text-xs text-muted-foreground truncate">
                        {p.client_email || t('admin.noClientAssigned')} •{' '}
                        {p.stage || t('admin.noStage')}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditProject(p)}
                      >
                        <Edit3 className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => deleteProject(p.id)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {projects.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">
                    {t('admin.noProjects')}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'blog' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold">
                  Blog ({posts.length})
                </h2>
                <Button
                  onClick={() => setEditPost({ ...emptyPost })}
                  className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  <Plus className="h-4 w-4" /> {t('admin.newPost')}
                </Button>
              </div>
              <div className="grid gap-3">
                {posts.map((p) => (
                  <div
                    key={p.id}
                    className="p-4 rounded-xl glass flex items-center gap-4"
                  >
                    <div className="w-20 h-14 rounded-lg overflow-hidden bg-white/5 shrink-0">
                      {p.cover_image && (
                        <img
                          src={p.cover_image}
                          alt=""
                          className="w-full h-full object-cover"
                        />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-[10px] uppercase tracking-widest text-purple-400">
                          {p.category}
                        </p>
                        {p.published ? (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">
                            {t('admin.published')}
                          </span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-muted-foreground">
                            {t('admin.draft')}
                          </span>
                        )}
                      </div>
                      <h3 className="font-semibold truncate">{p.title}</h3>
                      <p className="text-xs text-muted-foreground truncate">
                        /{p.slug}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditPost(p)}
                      >
                        <Edit3 className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => deletePost(p.id)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {posts.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">
                    {t('admin.noPosts')}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'clients' && (
            <div>
              <h2 className="text-xl font-semibold mb-6">
                {t('ui.tabClients')} ({clientList.length})
              </h2>
              <div className="grid gap-3">
                {clientList.map((c) => {
                  const cProjects = projects.filter(
                    (p) => (p.client_email || '').toLowerCase() === c.email
                  );
                  const cInvoices = invoices.filter(
                    (i) => (i.client_email || '').toLowerCase() === c.email
                  );
                  const unpaid = cInvoices.filter((i) => i.status !== 'paid');
                  return (
                    <div key={c.email} className="p-5 rounded-xl glass">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <h3 className="font-semibold">
                            {c.name || t('admin.unnamedClient')}
                          </h3>
                          <a
                            href={`mailto:${c.email}`}
                            className="text-xs text-purple-400 hover:text-pink-400"
                          >
                            {c.email}
                          </a>
                        </div>
                        <div className="flex gap-6 text-xs">
                          <div>
                            <p className="text-muted-foreground uppercase tracking-widest">
                              {t('admin.projectCount')}
                            </p>
                            <p className="text-lg font-bold">
                              {cProjects.length}
                            </p>
                          </div>
                          <div>
                            <p className="text-muted-foreground uppercase tracking-widest">
                              {t('admin.invoiceCount')}
                            </p>
                            <p className="text-lg font-bold">
                              {cInvoices.length}
                            </p>
                          </div>
                          <div>
                            <p className="text-muted-foreground uppercase tracking-widest">
                              {t('admin.unpaid')}
                            </p>
                            <p className="text-lg font-bold text-orange-300">
                              {unpaid.length}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
                {clientList.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">
                    {t('admin.noClients')}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'invoices' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold">
                  {t('admin.tabInvoices')} ({invoices.length})
                </h2>
                <Button
                  onClick={() =>
                    setEditInvoice({
                      ...emptyInvoice,
                      invoice_no: `INV-${Date.now().toString().slice(-6)}`,
                      issue_date: new Date().toISOString().slice(0, 10),
                    })
                  }
                  className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  <Plus className="h-4 w-4" /> {t('admin.newInvoiceBtn')}
                </Button>
              </div>
              <div className="grid gap-3">
                {invoices.map((inv) => (
                  <div
                    key={inv.id}
                    className="p-4 rounded-xl glass flex flex-wrap items-center gap-4"
                  >
                    <div className="flex-1 min-w-[200px]">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold">{inv.invoice_no}</span>
                        <span
                          className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                            inv.status === 'paid'
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : 'bg-orange-500/15 text-orange-300'
                          }`}
                        >
                          {inv.status === 'paid' ? t('ui.status.paid') : t('ui.status.unpaid')}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {inv.client_email} • {inv.description}
                      </p>
                    </div>
                    <p className="text-lg font-bold gradient-text">
                      {inv.amount} {inv.currency || 'USD'}
                    </p>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditInvoice(inv)}
                      >
                        <Edit3 className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => deleteInvoice(inv.id)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {invoices.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">
                    {t('admin.noInvoices')}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'tickets' && (
            <div>
              <h2 className="text-xl font-semibold mb-6">
                {t('admin.tabTickets')} ({tickets.length})
              </h2>
              <div className="grid gap-3">
                {tickets.map((tk) => (
                  <div key={tk.id} className="p-5 rounded-xl glass">
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold">{tk.subject}</h3>
                          <span
                            className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                              tk.status === 'answered'
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-pink-500/15 text-pink-300'
                            }`}
                          >
                            {tk.status === 'answered' ? t('ui.status.answered') : t('ui.status.open')}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {tk.client_name} • {tk.client_email}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setReplyTicket(tk);
                          setReplyText(tk.reply || '');
                        }}
                        className="gap-1 text-purple-300"
                      >
                        <MessageSquare className="h-4 w-4" /> {t('admin.replyBtn')}
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {tk.message}
                    </p>
                    {tk.reply && (
                      <div className="mt-3 pt-3 border-t border-white/10">
                        <p className="text-xs uppercase tracking-widest text-purple-400 mb-1">
                          {t('admin.yourReply')}
                        </p>
                        <p className="text-sm whitespace-pre-wrap">
                          {tk.reply}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
                {tickets.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">
                    {t('admin.noTickets')}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'inquiries' && (
            <div>
              <h2 className="text-xl font-semibold mb-6">
                {t('admin.tabInquiries')} ({inquiries.length})
              </h2>
              <div className="grid gap-3">
                {inquiries.map((inq) => (
                  <div key={inq.id} className="p-5 rounded-xl glass">
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold">{inq.name}</h3>
                          <span
                            className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
                              inq.status === 'resolved'
                                ? 'bg-emerald-500/15 text-emerald-300'
                                : 'bg-pink-500/15 text-pink-300'
                            }`}
                          >
                            {inq.status === 'resolved' ? t('admin.resolved') : t('admin.newLabel')}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <a
                            href={`mailto:${inq.email}`}
                            className="hover:text-foreground inline-flex items-center gap-1"
                          >
                            <Mail className="h-3 w-3" /> {inq.email}
                          </a>
                          {inq.phone && <span>{inq.phone}</span>}
                          {inq.created_at && (
                            <span>
                              {new Date(inq.created_at).toLocaleDateString(
                                'tr-TR'
                              )}
                            </span>
                          )}
                        </div>
                      </div>
                      {inq.status !== 'resolved' && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => markInquiryResolved(inq)}
                          className="gap-1 text-emerald-300"
                        >
                          <CheckCircle2 className="h-4 w-4" /> {t('admin.resolved')}
                        </Button>
                      )}
                    </div>
                    {inq.subject && (
                      <p className="font-medium text-sm mb-2">{inq.subject}</p>
                    )}
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {inq.message}
                    </p>
                  </div>
                ))}
                {inquiries.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">
                    {t('admin.noInquiries')}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Proje modalı */}
      {editProject && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl my-8 rounded-2xl glass p-8 border border-purple-500/30">
            <button
              className="absolute top-4 right-4 p-2 hover:bg-white/5 rounded-lg"
              onClick={() => setEditProject(null)}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-2xl font-bold mb-6">
              {editProject.id ? t('admin.editProject') : t('admin.newProject')}
            </h3>
            <div className="space-y-4">
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.titleLabel')} *
                </Label>
                <Input
                  value={editProject.title || ''}
                  onChange={(e) =>
                    setEditProject({ ...editProject, title: e.target.value })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.descLabel')} *
                </Label>
                <Textarea
                  rows={3}
                  value={editProject.description || ''}
                  onChange={(e) =>
                    setEditProject({
                      ...editProject,
                      description: e.target.value,
                    })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.categoryLabel')} *
                  </Label>
                  <select
                    value={editProject.category || 'Website'}
                    onChange={(e) =>
                      setEditProject({
                        ...editProject,
                        category: e.target.value,
                      })
                    }
                    className="w-full h-10 rounded-md bg-white/5 border border-white/10 px-3 text-sm"
                  >
                    {['Website', 'E-Ticaret', 'SaaS', 'Mobil Uygulama', 'Reklam'].map(
                      (c) => (
                        <option key={c} value={c} className="bg-[#150a2b]">
                          {c}
                        </option>
                      )
                    )}
                  </select>
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.statusLabel')}
                  </Label>
                  <select
                    value={editProject.status || 'in_progress'}
                    onChange={(e) =>
                      setEditProject({ ...editProject, status: e.target.value })
                    }
                    className="w-full h-10 rounded-md bg-white/5 border border-white/10 px-3 text-sm"
                  >
                    <option value="planning" className="bg-[#150a2b]">
                      {t('ui.status.planning')}
                    </option>
                    <option value="in_progress" className="bg-[#150a2b]">
                      {t('ui.status.in_progress')}
                    </option>
                    <option value="completed" className="bg-[#150a2b]">
                      {t('ui.status.completed')}
                    </option>
                  </select>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.stageLabel')}
                  </Label>
                  <Input
                    value={editProject.stage || ''}
                    placeholder={t('admin.stagePlaceholder')}
                    onChange={(e) =>
                      setEditProject({ ...editProject, stage: e.target.value })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.progressLabel')}
                  </Label>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={editProject.progress ?? 0}
                    onChange={(e) =>
                      setEditProject({
                        ...editProject,
                        progress: Number(e.target.value),
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.imageUrl')}
                </Label>
                <Input
                  value={editProject.image_url || ''}
                  onChange={(e) =>
                    setEditProject({
                      ...editProject,
                      image_url: e.target.value,
                    })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.projectUrl')}
                </Label>
                <Input
                  value={editProject.project_url || ''}
                  onChange={(e) =>
                    setEditProject({
                      ...editProject,
                      project_url: e.target.value,
                    })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.clientNameLabel')}
                  </Label>
                  <Input
                    value={editProject.client_name || ''}
                    onChange={(e) =>
                      setEditProject({
                        ...editProject,
                        client_name: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.clientEmailLabel')}
                  </Label>
                  <Input
                    value={editProject.client_email || ''}
                    placeholder="musteri@ornek.com"
                    onChange={(e) =>
                      setEditProject({
                        ...editProject,
                        client_email: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.techLabel')}
                </Label>
                <Input
                  value={editProject.tech_stack || ''}
                  onChange={(e) =>
                    setEditProject({
                      ...editProject,
                      tech_stack: e.target.value,
                    })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!editProject.featured}
                  onChange={(e) =>
                    setEditProject({
                      ...editProject,
                      featured: e.target.checked,
                    })
                  }
                  className="rounded"
                />
                {t('admin.featuredProject')}
              </label>
            </div>
            <div className="flex gap-3 mt-8">
              <Button
                onClick={saveProject}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11"
              >
                {editProject.id ? t('admin.saveChanges') : t('admin.createProject')}
              </Button>
              <Button
                onClick={() => setEditProject(null)}
                variant="outline"
                className="!bg-transparent !hover:bg-transparent border-white/20 h-11"
              >
                {t('admin.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Blog modalı */}
      {editPost && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl my-8 rounded-2xl glass p-8 border border-purple-500/30">
            <button
              className="absolute top-4 right-4 p-2 hover:bg-white/5 rounded-lg"
              onClick={() => setEditPost(null)}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-2xl font-bold mb-6">
              {editPost.id ? t('admin.editPost') : t('admin.newPost')}
            </h3>
            <div className="space-y-4">
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.titleLabel')} *
                </Label>
                <Input
                  value={editPost.title || ''}
                  onChange={(e) =>
                    setEditPost({ ...editPost, title: e.target.value })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.slugLabel')} *
                </Label>
                <Input
                  value={editPost.slug || ''}
                  onChange={(e) =>
                    setEditPost({ ...editPost, slug: e.target.value })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.excerpt')}
                </Label>
                <Textarea
                  rows={2}
                  value={editPost.excerpt || ''}
                  onChange={(e) =>
                    setEditPost({ ...editPost, excerpt: e.target.value })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.content')} *
                </Label>
                <Textarea
                  rows={8}
                  value={editPost.content || ''}
                  onChange={(e) =>
                    setEditPost({ ...editPost, content: e.target.value })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.authorLabel')}
                  </Label>
                  <Input
                    value={editPost.author || ''}
                    onChange={(e) =>
                      setEditPost({ ...editPost, author: e.target.value })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.categoryLabel')}
                  </Label>
                  <select
                    value={editPost.category || 'Website'}
                    onChange={(e) =>
                      setEditPost({ ...editPost, category: e.target.value })
                    }
                    className="w-full h-10 rounded-md bg-white/5 border border-white/10 px-3 text-sm"
                  >
                    {[
                      'Website',
                      'E-Ticaret',
                      'SaaS',
                      'Mobil Uygulama',
                      'Reklam',
                      'SEO',
                    ].map((c) => (
                      <option key={c} value={c} className="bg-[#150a2b]">
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.coverImage')}
                </Label>
                <Input
                  value={editPost.cover_image || ''}
                  onChange={(e) =>
                    setEditPost({ ...editPost, cover_image: e.target.value })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={editPost.published !== false}
                  onChange={(e) =>
                    setEditPost({ ...editPost, published: e.target.checked })
                  }
                  className="rounded"
                />
                {t('admin.published')}
              </label>
            </div>
            <div className="flex gap-3 mt-8">
              <Button
                onClick={savePost}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11"
              >
                {editPost.id ? t('admin.saveChanges') : t('admin.createPost')}
              </Button>
              <Button
                onClick={() => setEditPost(null)}
                variant="outline"
                className="!bg-transparent !hover:bg-transparent border-white/20 h-11"
              >
                {t('admin.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Fatura modalı */}
      {editInvoice && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="relative w-full max-w-xl my-8 rounded-2xl glass p-8 border border-purple-500/30">
            <button
              className="absolute top-4 right-4 p-2 hover:bg-white/5 rounded-lg"
              onClick={() => setEditInvoice(null)}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-2xl font-bold mb-6">
              {editInvoice.id ? t('admin.editInvoice') : t('admin.newInvoice')}
            </h3>
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.invoiceNo')} *
                  </Label>
                  <Input
                    value={editInvoice.invoice_no || ''}
                    onChange={(e) =>
                      setEditInvoice({
                        ...editInvoice,
                        invoice_no: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.amountLabel')} *
                  </Label>
                  <Input
                    type="number"
                    value={editInvoice.amount ?? 0}
                    onChange={(e) =>
                      setEditInvoice({
                        ...editInvoice,
                        amount: Number(e.target.value),
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.clientNameLabel')}
                  </Label>
                  <Input
                    value={editInvoice.client_name || ''}
                    onChange={(e) =>
                      setEditInvoice({
                        ...editInvoice,
                        client_name: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.clientEmailLabel')}
                  </Label>
                  <Input
                    value={editInvoice.client_email || ''}
                    onChange={(e) =>
                      setEditInvoice({
                        ...editInvoice,
                        client_email: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                  {t('admin.descLabel')}
                </Label>
                <Textarea
                  rows={2}
                  value={editInvoice.description || ''}
                  onChange={(e) =>
                    setEditInvoice({
                      ...editInvoice,
                      description: e.target.value,
                    })
                  }
                  className="bg-white/5 border-white/10"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.currencyLabel')}
                  </Label>
                  <Input
                    value={editInvoice.currency || 'USD'}
                    onChange={(e) =>
                      setEditInvoice({
                        ...editInvoice,
                        currency: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('admin.statusLabel')}
                  </Label>
                  <select
                    value={editInvoice.status || 'unpaid'}
                    onChange={(e) =>
                      setEditInvoice({ ...editInvoice, status: e.target.value })
                    }
                    className="w-full h-10 rounded-md bg-white/5 border border-white/10 px-3 text-sm"
                  >
                    <option value="unpaid" className="bg-[#150a2b]">
                      {t('ui.status.unpaid')}
                    </option>
                    <option value="paid" className="bg-[#150a2b]">
                      {t('ui.status.paid')}
                    </option>
                    <option value="overdue" className="bg-[#150a2b]">
                      {t('ui.status.overdue')}
                    </option>
                  </select>
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                    {t('ui.due')}
                  </Label>
                  <Input
                    type="date"
                    value={editInvoice.due_date || ''}
                    onChange={(e) =>
                      setEditInvoice({
                        ...editInvoice,
                        due_date: e.target.value,
                      })
                    }
                    className="bg-white/5 border-white/10"
                  />
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-8">
              <Button
                onClick={saveInvoice}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11"
              >
                {t('admin.saveBtn')}
              </Button>
              <Button
                onClick={() => setEditInvoice(null)}
                variant="outline"
                className="!bg-transparent !hover:bg-transparent border-white/20 h-11"
              >
                {t('admin.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Destek yanıt modalı */}
      {replyTicket && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="relative w-full max-w-lg my-8 rounded-2xl glass p-8 border border-purple-500/30">
            <button
              className="absolute top-4 right-4 p-2 hover:bg-white/5 rounded-lg"
              onClick={() => setReplyTicket(null)}
            >
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-xl font-bold mb-2">{replyTicket.subject}</h3>
            <p className="text-xs text-muted-foreground mb-4">
              {replyTicket.client_email}
            </p>
            <p className="text-sm text-muted-foreground mb-5 p-4 rounded-xl bg-white/5 whitespace-pre-wrap">
              {replyTicket.message}
            </p>
            <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
              {t('admin.yourReply')}
            </Label>
            <Textarea
              rows={5}
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              className="bg-white/5 border-white/10"
            />
            <div className="flex gap-3 mt-6">
              <Button
                onClick={sendReply}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11"
              >
                {t('admin.sendReply')}
              </Button>
              <Button
                onClick={() => setReplyTicket(null)}
                variant="outline"
                className="!bg-transparent !hover:bg-transparent border-white/20 h-11"
              >
                {t('admin.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}