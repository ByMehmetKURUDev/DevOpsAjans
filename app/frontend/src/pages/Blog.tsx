import { useEffect, useState } from 'react';
import { Calendar, ArrowRight, Loader2 } from 'lucide-react';
import { createClient } from '@metagptx/web-sdk';

const client = createClient();

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
  created_at?: string;
}

export default function Blog() {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [selected, setSelected] = useState<BlogPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    client.entities.blog_posts
      .queryAll({ query: { published: true }, sort: '-created_at', limit: 50 })
      .then((res) => {
        if (cancelled) return;
        setPosts((res?.data?.items ?? []) as BlogPost[]);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || 'Failed to load articles');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  if (selected) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <button
          onClick={() => setSelected(null)}
          className="text-sm text-purple-400 hover:text-purple-300 mb-8 inline-flex items-center gap-2"
        >
          ← Back to all articles
        </button>
        {selected.cover_image && (
          <div className="rounded-2xl overflow-hidden mb-8 aspect-[16/9]">
            <img src={selected.cover_image} alt={selected.title} className="w-full h-full object-cover" />
          </div>
        )}
        <div className="mb-6">
          {selected.category && (
            <span className="text-xs uppercase tracking-widest text-purple-400">
              {selected.category}
            </span>
          )}
          <h1 className="text-4xl md:text-5xl font-bold mt-3 leading-tight">{selected.title}</h1>
          <div className="flex items-center gap-4 mt-4 text-sm text-muted-foreground">
            {selected.author && <span>By {selected.author}</span>}
            {selected.created_at && (
              <span className="flex items-center gap-1.5">
                <Calendar className="h-3.5 w-3.5" />
                {new Date(selected.created_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        {selected.excerpt && (
          <p className="text-xl text-muted-foreground leading-relaxed mb-6 italic border-l-2 border-purple-500 pl-4">
            {selected.excerpt}
          </p>
        )}
        <div className="prose prose-invert max-w-none prose-p:text-muted-foreground prose-p:leading-relaxed">
          {(selected.content || '').split('\n\n').map((para, i) => (
            <p key={i} className="mb-4 text-muted-foreground leading-relaxed">
              {para}
            </p>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <section className="py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">Journal</p>
          <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6 max-w-3xl">
            Notes from the <span className="gradient-text">studio.</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl">
            Practical writing on software craft, product design, and modern
            digital marketing — for people who ship.
          </p>
        </div>
      </section>

      <section className="pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {loading ? (
            <div className="py-24 flex items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-3" />
              Loading articles...
            </div>
          ) : error ? (
            <div className="py-24 text-center text-destructive">{error}</div>
          ) : posts.length === 0 ? (
            <div className="py-24 text-center text-muted-foreground">No articles yet.</div>
          ) : (
            <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
              {posts.map((post) => (
                <article
                  key={post.id}
                  onClick={() => setSelected(post)}
                  className="group cursor-pointer rounded-2xl overflow-hidden glass hover:border-purple-500/40 transition-all duration-500 hover:-translate-y-1"
                >
                  <div className="relative aspect-[16/9] overflow-hidden bg-gradient-to-br from-purple-950/40 to-pink-950/40">
                    {post.cover_image ? (
                      <img
                        src={post.cover_image}
                        alt={post.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-4xl gradient-text font-bold">
                        {post.title.charAt(0)}
                      </div>
                    )}
                  </div>
                  <div className="p-6">
                    {post.category && (
                      <span className="text-[10px] uppercase tracking-widest text-purple-400">
                        {post.category}
                      </span>
                    )}
                    <h3 className="text-xl font-semibold my-3 group-hover:gradient-text transition-all leading-tight">
                      {post.title}
                    </h3>
                    <p className="text-sm text-muted-foreground line-clamp-3 mb-5">{post.excerpt}</p>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{post.author}</span>
                      <span className="inline-flex items-center gap-1 text-purple-400 group-hover:text-pink-400 transition-colors">
                        Read <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}