import { useEffect, useState } from 'react';
import { Loader2, LogIn, Plus, Trash2, Edit3, X, Mail, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { createClient } from '@metagptx/web-sdk';

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
  status?: string;
  tech_stack?: string;
  featured?: boolean;
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

type Tab = 'projects' | 'blog' | 'inquiries';

const emptyProject: Partial<Project> = {
  title: '',
  description: '',
  category: 'Web Application',
  image_url: '',
  project_url: '',
  client_name: '',
  status: 'in_progress',
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
  category: 'Development',
  published: true,
};

export default function AdminPanel() {
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tab, setTab] = useState<Tab>('projects');

  const [projects, setProjects] = useState<Project[]>([]);
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [loading, setLoading] = useState(false);

  const [editProject, setEditProject] = useState<Partial<Project> | null>(null);
  const [editPost, setEditPost] = useState<Partial<BlogPost> | null>(null);

  useEffect(() => {
    client.auth
      .me()
      .then((res) => {
        if (res?.data) setUser(res.data as AuthUser);
      })
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [pRes, bRes, iRes] = await Promise.all([
        client.entities.projects.queryAll({ sort: '-created_at', limit: 100 }),
        client.entities.blog_posts.queryAll({ sort: '-created_at', limit: 100 }),
        client.entities.inquiries.queryAll({ sort: '-created_at', limit: 100 }),
      ]);
      setProjects((pRes?.data?.items ?? []) as Project[]);
      setPosts((bRes?.data?.items ?? []) as BlogPost[]);
      setInquiries((iRes?.data?.items ?? []) as Inquiry[]);
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || 'Failed to load admin data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) loadAll();
  }, [user]);

  const saveProject = async () => {
    if (!editProject) return;
    if (!editProject.title || !editProject.description || !editProject.category) {
      toast.error('Title, description, and category are required.');
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
        status: editProject.status || 'in_progress',
        tech_stack: editProject.tech_stack || '',
        featured: !!editProject.featured,
      };
      if (editProject.id) {
        await client.entities.projects.update({ id: String(editProject.id), data: payload });
        toast.success('Project updated');
      } else {
        await client.entities.projects.create({ data: payload });
        toast.success('Project created');
      }
      setEditProject(null);
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || 'Failed to save project');
    }
  };

  const deleteProject = async (id: number | string) => {
    if (!confirm('Delete this project?')) return;
    try {
      await client.entities.projects.delete({ id: String(id) });
      toast.success('Project deleted');
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || 'Delete failed');
    }
  };

  const savePost = async () => {
    if (!editPost) return;
    if (!editPost.title || !editPost.slug || !editPost.content) {
      toast.error('Title, slug, and content are required.');
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
        category: editPost.category || 'Development',
        published: editPost.published !== false,
      };
      if (editPost.id) {
        await client.entities.blog_posts.update({ id: String(editPost.id), data: payload });
        toast.success('Post updated');
      } else {
        await client.entities.blog_posts.create({ data: payload });
        toast.success('Post created');
      }
      setEditPost(null);
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || 'Failed to save post');
    }
  };

  const deletePost = async (id: number | string) => {
    if (!confirm('Delete this blog post?')) return;
    try {
      await client.entities.blog_posts.delete({ id: String(id) });
      toast.success('Post deleted');
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || 'Delete failed');
    }
  };

  const markInquiryResolved = async (inq: Inquiry) => {
    try {
      await client.entities.inquiries.update({
        id: String(inq.id),
        data: { status: 'resolved' },
      });
      toast.success('Marked as resolved');
      loadAll();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || 'Update failed');
    }
  };

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
          <h1 className="text-3xl font-bold mb-3">Admin Panel</h1>
          <p className="text-muted-foreground mb-6">Sign in with an admin account to continue.</p>
          <Button
            onClick={() => client.auth.toLogin()}
            className="w-full h-11 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
          >
            Sign in
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-2">Admin</p>
          <h1 className="text-4xl md:text-5xl font-bold">
            Studio <span className="gradient-text">control room</span>
          </h1>
        </div>
        <div className="text-sm text-muted-foreground">
          Signed in as <span className="text-foreground">{user.email || user.name}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 border-b border-white/10 overflow-x-auto">
        {(['projects', 'blog', 'inquiries'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-3 text-sm font-medium capitalize transition-colors relative ${
              tab === t ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t} {tab === t && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-16 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading...
        </div>
      ) : (
        <>
          {tab === 'projects' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold">Projects ({projects.length})</h2>
                <Button
                  onClick={() => setEditProject({ ...emptyProject })}
                  className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  <Plus className="h-4 w-4" /> New project
                </Button>
              </div>
              <div className="grid gap-3">
                {projects.map((p) => (
                  <div key={p.id} className="p-4 rounded-xl glass flex items-center gap-4">
                    <div className="w-20 h-14 rounded-lg overflow-hidden bg-white/5 shrink-0">
                      {p.image_url && <img src={p.image_url} alt="" className="w-full h-full object-cover" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-[10px] uppercase tracking-widest text-purple-400">{p.category}</p>
                        {p.featured && <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300">Featured</span>}
                      </div>
                      <h3 className="font-semibold truncate">{p.title}</h3>
                      <p className="text-xs text-muted-foreground truncate">{p.description}</p>
                    </div>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditProject(p)}>
                        <Edit3 className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => deleteProject(p.id)} className="text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {projects.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">No projects yet.</div>
                )}
              </div>
            </div>
          )}

          {tab === 'blog' && (
            <div>
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold">Blog posts ({posts.length})</h2>
                <Button
                  onClick={() => setEditPost({ ...emptyPost })}
                  className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  <Plus className="h-4 w-4" /> New post
                </Button>
              </div>
              <div className="grid gap-3">
                {posts.map((p) => (
                  <div key={p.id} className="p-4 rounded-xl glass flex items-center gap-4">
                    <div className="w-20 h-14 rounded-lg overflow-hidden bg-white/5 shrink-0">
                      {p.cover_image && <img src={p.cover_image} alt="" className="w-full h-full object-cover" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-[10px] uppercase tracking-widest text-purple-400">{p.category}</p>
                        {p.published ? (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300">Published</span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-muted-foreground">Draft</span>
                        )}
                      </div>
                      <h3 className="font-semibold truncate">{p.title}</h3>
                      <p className="text-xs text-muted-foreground truncate">/{p.slug}</p>
                    </div>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditPost(p)}>
                        <Edit3 className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => deletePost(p.id)} className="text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
                {posts.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">No posts yet.</div>
                )}
              </div>
            </div>
          )}

          {tab === 'inquiries' && (
            <div>
              <h2 className="text-xl font-semibold mb-6">Inbox ({inquiries.length})</h2>
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
                            {inq.status || 'new'}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <a href={`mailto:${inq.email}`} className="hover:text-foreground inline-flex items-center gap-1">
                            <Mail className="h-3 w-3" /> {inq.email}
                          </a>
                          {inq.phone && <span>{inq.phone}</span>}
                          {inq.created_at && <span>{new Date(inq.created_at).toLocaleDateString()}</span>}
                        </div>
                      </div>
                      {inq.status !== 'resolved' && (
                        <Button size="sm" variant="ghost" onClick={() => markInquiryResolved(inq)} className="gap-1 text-emerald-300">
                          <CheckCircle2 className="h-4 w-4" /> Resolve
                        </Button>
                      )}
                    </div>
                    {inq.subject && <p className="font-medium text-sm mb-2">{inq.subject}</p>}
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">{inq.message}</p>
                  </div>
                ))}
                {inquiries.length === 0 && (
                  <div className="p-10 rounded-xl glass text-center text-muted-foreground">No inquiries yet.</div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Project modal */}
      {editProject && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl my-8 rounded-2xl glass p-8 border border-purple-500/30">
            <button className="absolute top-4 right-4 p-2 hover:bg-white/5 rounded-lg" onClick={() => setEditProject(null)}>
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-2xl font-bold mb-6">{editProject.id ? 'Edit project' : 'New project'}</h3>
            <div className="space-y-4">
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Title *</Label>
                <Input value={editProject.title || ''} onChange={(e) => setEditProject({ ...editProject, title: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Description *</Label>
                <Textarea rows={3} value={editProject.description || ''} onChange={(e) => setEditProject({ ...editProject, description: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Category *</Label>
                  <Input value={editProject.category || ''} onChange={(e) => setEditProject({ ...editProject, category: e.target.value })} className="bg-white/5 border-white/10" />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Status</Label>
                  <select
                    value={editProject.status || 'in_progress'}
                    onChange={(e) => setEditProject({ ...editProject, status: e.target.value })}
                    className="w-full h-10 rounded-md bg-white/5 border border-white/10 px-3 text-sm"
                  >
                    <option value="planning">Planning</option>
                    <option value="in_progress">In progress</option>
                    <option value="completed">Completed</option>
                  </select>
                </div>
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Image URL</Label>
                <Input value={editProject.image_url || ''} onChange={(e) => setEditProject({ ...editProject, image_url: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Project URL</Label>
                <Input value={editProject.project_url || ''} onChange={(e) => setEditProject({ ...editProject, project_url: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Client name</Label>
                  <Input value={editProject.client_name || ''} onChange={(e) => setEditProject({ ...editProject, client_name: e.target.value })} className="bg-white/5 border-white/10" />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Tech stack</Label>
                  <Input value={editProject.tech_stack || ''} onChange={(e) => setEditProject({ ...editProject, tech_stack: e.target.value })} className="bg-white/5 border-white/10" />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={!!editProject.featured} onChange={(e) => setEditProject({ ...editProject, featured: e.target.checked })} className="rounded" />
                Featured project
              </label>
            </div>
            <div className="flex gap-3 mt-8">
              <Button onClick={saveProject} className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11">
                {editProject.id ? 'Save changes' : 'Create project'}
              </Button>
              <Button onClick={() => setEditProject(null)} variant="outline" className="!bg-transparent border-white/20 h-11">
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Blog modal */}
      {editPost && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl my-8 rounded-2xl glass p-8 border border-purple-500/30">
            <button className="absolute top-4 right-4 p-2 hover:bg-white/5 rounded-lg" onClick={() => setEditPost(null)}>
              <X className="h-4 w-4" />
            </button>
            <h3 className="text-2xl font-bold mb-6">{editPost.id ? 'Edit post' : 'New post'}</h3>
            <div className="space-y-4">
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Title *</Label>
                <Input value={editPost.title || ''} onChange={(e) => setEditPost({ ...editPost, title: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Slug *</Label>
                <Input value={editPost.slug || ''} onChange={(e) => setEditPost({ ...editPost, slug: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Excerpt</Label>
                <Textarea rows={2} value={editPost.excerpt || ''} onChange={(e) => setEditPost({ ...editPost, excerpt: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Content *</Label>
                <Textarea rows={8} value={editPost.content || ''} onChange={(e) => setEditPost({ ...editPost, content: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Author</Label>
                  <Input value={editPost.author || ''} onChange={(e) => setEditPost({ ...editPost, author: e.target.value })} className="bg-white/5 border-white/10" />
                </div>
                <div>
                  <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Category</Label>
                  <Input value={editPost.category || ''} onChange={(e) => setEditPost({ ...editPost, category: e.target.value })} className="bg-white/5 border-white/10" />
                </div>
              </div>
              <div>
                <Label className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">Cover image URL</Label>
                <Input value={editPost.cover_image || ''} onChange={(e) => setEditPost({ ...editPost, cover_image: e.target.value })} className="bg-white/5 border-white/10" />
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={editPost.published !== false} onChange={(e) => setEditPost({ ...editPost, published: e.target.checked })} className="rounded" />
                Published
              </label>
            </div>
            <div className="flex gap-3 mt-8">
              <Button onClick={savePost} className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0 h-11">
                {editPost.id ? 'Save changes' : 'Create post'}
              </Button>
              <Button onClick={() => setEditPost(null)} variant="outline" className="!bg-transparent border-white/20 h-11">
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}