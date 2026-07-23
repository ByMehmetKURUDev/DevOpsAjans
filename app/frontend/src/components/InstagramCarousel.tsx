import { Link } from 'react-router-dom';
import { Globe, ShoppingCart, Cloud, Smartphone, Megaphone } from 'lucide-react';

const PORTFOLIO_CATEGORIES = [
  { slug: 'Website', label: 'Website', icon: Globe, gradient: 'from-purple-600/40 to-pink-600/40', emoji: '💻' },
  { slug: 'E-Ticaret', label: 'E-Ticaret', icon: ShoppingCart, gradient: 'from-pink-600/40 to-orange-500/40', emoji: '🛒' },
  { slug: 'SaaS', label: 'SaaS', icon: Cloud, gradient: 'from-cyan-500/40 to-purple-600/40', emoji: '🚀' },
  { slug: 'Mobil Uygulama', label: 'Mobil Uygulama', icon: Smartphone, gradient: 'from-emerald-500/40 to-cyan-500/40', emoji: '📱' },
  { slug: 'Reklam', label: 'Reklam', icon: Megaphone, gradient: 'from-purple-500/40 to-pink-500/40', emoji: '📣' },
];

export default function InstagramCarousel() {
  return (
    <section className="py-16 border-t border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center">
            <span className="text-white text-lg font-bold">P</span>
          </div>
          <div>
            <p className="font-semibold text-sm">Portföy Kategorileri</p>
            <p className="text-xs text-muted-foreground">Projelerimizi keşfedin</p>
          </div>
        </div>
      </div>
      <div className="overflow-x-auto scrollbar-hide">
        <div className="flex gap-3 px-4 sm:px-6 lg:px-8 pb-4 min-w-max">
          {[...PORTFOLIO_CATEGORIES, ...PORTFOLIO_CATEGORIES].map((cat, i) => (
            <Link
              key={`${cat.slug}-${i}`}
              to={`/portfolio?category=${encodeURIComponent(cat.slug)}`}
              className="w-56 h-56 rounded-xl overflow-hidden flex-shrink-0 glass hover:border-purple-500/40 transition-all duration-300 hover:-translate-y-1 group cursor-pointer"
            >
              <div className={`w-full h-full bg-gradient-to-br ${cat.gradient} flex items-center justify-center group-hover:scale-105 transition-transform duration-500`}>
                <div className="text-center">
                  <div className="text-3xl mb-2">{cat.emoji}</div>
                  <p className="text-sm font-medium text-foreground">{cat.label}</p>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-widest mt-1">Keşfet →</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}