import { useTranslation } from 'react-i18next';

const ITEMS = [
  { emoji: '💻', label: 'Web Dev', gradient: 'from-purple-600/40 to-pink-600/40' },
  { emoji: '🚀', label: 'SaaS', gradient: 'from-pink-600/40 to-orange-500/40' },
  { emoji: '🎨', label: 'Design', gradient: 'from-cyan-500/40 to-purple-600/40' },
  { emoji: '📱', label: 'Mobile', gradient: 'from-emerald-500/40 to-cyan-500/40' },
  { emoji: '⚡', label: 'DevOps', gradient: 'from-purple-500/40 to-cyan-500/40' },
  { emoji: '🔥', label: 'Marketing', gradient: 'from-pink-500/40 to-purple-600/40' },
  { emoji: '✨', label: 'UI/UX', gradient: 'from-orange-500/40 to-pink-600/40' },
  { emoji: '🌐', label: 'E-Commerce', gradient: 'from-cyan-400/40 to-emerald-500/40' },
  { emoji: '🛡️', label: 'Security', gradient: 'from-purple-400/40 to-pink-400/40' },
  { emoji: '☁️', label: 'Cloud', gradient: 'from-emerald-400/40 to-purple-400/40' },
];

export default function InstagramCarousel() {
  const { t: _t } = useTranslation();

  return (
    <section className="py-16 border-t border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center">
            <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/>
            </svg>
          </div>
          <div>
            <p className="font-semibold text-sm">@mehmetkurudev</p>
            <p className="text-xs text-muted-foreground">Instagram</p>
          </div>
        </div>
      </div>
      <div className="overflow-x-auto scrollbar-hide">
        <div className="flex gap-3 px-4 sm:px-6 lg:px-8 pb-4 min-w-max">
          {ITEMS.map((item, i) => (
            <div
              key={i}
              className="w-56 h-56 rounded-xl overflow-hidden flex-shrink-0 glass hover:border-purple-500/40 transition-all duration-300 hover:-translate-y-1 group cursor-pointer"
            >
              <div className={`w-full h-full bg-gradient-to-br ${item.gradient} flex items-center justify-center group-hover:scale-105 transition-transform duration-500`}>
                <div className="text-center">
                  <div className="text-3xl mb-2">{item.emoji}</div>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest">{item.label}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}