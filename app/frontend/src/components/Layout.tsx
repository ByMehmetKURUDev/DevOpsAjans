import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState, lazy, Suspense } from 'react';
import { Menu, X, MessageCircle, User, LogIn, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';

const InstagramCarousel = lazy(() => import('@/components/InstagramCarousel'));

const client = createClient();

const WHATSAPP_NUMBER = '905412965878';

const LANGUAGES = [
  { code: 'en', label: 'EN', full: 'English', flag: '🇬🇧' },
  { code: 'tr', label: 'TR', full: 'Türkçe', flag: '🇹🇷' },
  { code: 'de', label: 'DE', full: 'Deutsch', flag: '🇩🇪' },
];

interface AuthUser {
  id?: string;
  email?: string;
  name?: string;
  role?: string;
  [key: string]: unknown;
}

export default function Layout() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const location = useLocation();

  const NAV_LINKS = [
    { to: '/', label: t('nav.home') },
    { to: '/services', label: t('nav.services') },
    { to: '/portfolio', label: t('nav.portfolio') },
    { to: '/blog', label: t('nav.blog') },
    { to: '/contact', label: t('nav.contact') },
  ];

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
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setOpen(false);
    setLangOpen(false);
  }, [location.pathname]);

  const handleLogin = () => client.auth.toLogin();
  const handleLogout = async () => {
    try {
      await client.auth.logout();
    } finally {
      setUser(null);
      window.location.href = '/';
    }
  };

  const switchLang = (code: string) => {
    i18n.changeLanguage(code);
    setLangOpen(false);
  };

  const currentLang = LANGUAGES.find((l) => l.code === i18n.language) || LANGUAGES[0];

  const isAdmin =
    user?.email?.toLowerCase().includes('admin') ||
    (typeof user?.role === 'string' && user.role.toLowerCase() === 'admin');

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Ambient background layers */}
      <div className="pointer-events-none fixed inset-0 -z-10 noise-bg" />
      <div className="pointer-events-none fixed inset-0 -z-10 grid-bg opacity-40" />

      {/* Header */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled ? 'glass py-3' : 'bg-transparent py-5'
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-[#8b3dff] via-[#5c27a3] to-[#d4a5ff] blur-md opacity-60 group-hover:opacity-100 transition-opacity" />
              <img
                src="/assets/logo-new.jpg"
                alt="Mehmet KURU Dev"
                className="relative h-9 w-9 rounded-lg object-cover ring-1 ring-white/10"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
            </div>
            <div className="flex flex-col leading-tight">
              <span className="font-bold text-sm tracking-wide">
                Mehmet <span className="gradient-text">KURU</span>
              </span>
              <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                Dev · Agency
              </span>
            </div>
          </Link>

          <nav className="hidden lg:flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/'}
                className={({ isActive }) =>
                  `relative px-4 py-2 text-sm font-medium transition-colors rounded-md ${
                    isActive
                      ? 'text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {link.label}
                    {isActive && (
                      <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 h-0.5 w-6 rounded-full bg-gradient-to-r from-purple-500 to-pink-500" />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="hidden lg:flex items-center gap-2">
            {/* Language switcher */}
            <div className="relative">
              <button
                onClick={() => setLangOpen((s) => !s)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
              >
                <span className="text-base">{currentLang.flag}</span>
                {currentLang.label}
              </button>
              {langOpen && (
                <div className="absolute top-full right-0 mt-2 w-36 rounded-xl glass p-1.5 animate-in fade-in slide-in-from-top-2 duration-200 z-50">
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => switchLang(lang.code)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                        lang.code === i18n.language
                          ? 'bg-purple-500/15 text-foreground'
                          : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                      }`}
                    >
                      <span className="text-base">{lang.flag}</span>
                      <span className="font-medium">{lang.label}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{lang.full}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {!authLoading && user ? (
              <>
                <Link to={isAdmin ? '/admin' : '/client'}>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-2 hover:bg-purple-500/10 hover:text-purple-300"
                  >
                    <User className="h-4 w-4" />
                    {isAdmin ? t('nav.admin') : t('nav.myPanel')}
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleLogout}
                  className="gap-2 text-muted-foreground hover:text-foreground"
                >
                  <LogOut className="h-4 w-4" />
                </Button>
              </>
            ) : (
              !authLoading && (
                <Button
                  size="sm"
                  onClick={handleLogin}
                  className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 glow-primary"
                >
                  <LogIn className="h-4 w-4" />
                  {t('nav.signIn')}
                </Button>
              )
            )}
          </div>

          <button
            className="lg:hidden p-2 rounded-md hover:bg-white/5"
            onClick={() => setOpen((s) => !s)}
            aria-label="Toggle menu"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {/* Mobile menu */}
        {open && (
          <div className="lg:hidden mt-3 mx-4 rounded-2xl glass p-4 space-y-1 animate-in slide-in-from-top-4 duration-200">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === '/'}
                className={({ isActive }) =>
                  `block px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-purple-500/15 text-foreground'
                      : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
            {/* Mobile language switcher */}
            <div className="pt-3 border-t border-white/10">
              <p className="px-4 py-1 text-xs uppercase tracking-widest text-muted-foreground">Language</p>
              <div className="flex gap-2 px-4 py-2">
                {LANGUAGES.map((lang) => (
                  <button
                    key={lang.code}
                    onClick={() => switchLang(lang.code)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5 ${
                      lang.code === i18n.language
                        ? 'bg-purple-500/20 text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <span>{lang.flag}</span>
                    {lang.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="pt-3 border-t border-white/10 flex flex-col gap-2">
              {user ? (
                <>
                  <Link to={isAdmin ? '/admin' : '/client'}>
                    <Button variant="secondary" className="w-full gap-2">
                      <User className="h-4 w-4" /> {isAdmin ? t('nav.admin') : t('nav.myPanel')}
                    </Button>
                  </Link>
                  <Button variant="ghost" onClick={handleLogout} className="w-full gap-2">
                    <LogOut className="h-4 w-4" /> {t('nav.signOut')}
                  </Button>
                </>
              ) : (
                <Button
                  onClick={handleLogin}
                  className="w-full gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                >
                  <LogIn className="h-4 w-4" /> {t('nav.signIn')}
                </Button>
              )}
            </div>
          </div>
        )}
      </header>

      {/* Main content */}
      <main className="flex-1 pt-24">
        <Outlet />
      </main>

      {/* Instagram Carousel - All pages */}
      <Suspense fallback={null}>
        <InstagramCarousel />
      </Suspense>

      {/* Footer */}
      <footer className="border-t border-white/5 bg-background/60 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 grid gap-10 md:grid-cols-4">
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <img
                src="/assets/logo-new.jpg"
                alt=""
                className="h-8 w-8 rounded-lg object-cover"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
              <span className="font-bold">
                By Mehmet <span className="gradient-text">KURU</span> Dev
              </span>
            </div>
            <p className="text-sm text-muted-foreground max-w-md">
              {t('footer.desc')}
            </p>
            <div className="flex gap-4 pt-2">
              <a href="#" aria-label="Facebook" className="text-muted-foreground hover:text-foreground transition-colors">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
              </a>
              <a href="#" aria-label="Instagram" className="text-muted-foreground hover:text-foreground transition-colors">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
              </a>
              <a href="#" aria-label="Twitter" className="text-muted-foreground hover:text-foreground transition-colors">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/></svg>
              </a>
              <a href="#" aria-label="LinkedIn" className="text-muted-foreground hover:text-foreground transition-colors">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
              </a>
              <a href="#" aria-label="YouTube" className="text-muted-foreground hover:text-foreground transition-colors">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
              </a>
              <a href="#" aria-label="GitHub" className="text-muted-foreground hover:text-foreground transition-colors">
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
              </a>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-4 tracking-wide">{t('footer.navigate')}</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {NAV_LINKS.map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="hover:text-foreground transition-colors">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-4 tracking-wide">{t('footer.contact')}</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><a href="mailto:by@mehmetkuru.dev" className="hover:text-foreground">by@mehmetkuru.dev</a></li>
              <li><a href="tel:+905412965878" className="hover:text-foreground">0541 296 58 78</a></li>
              <li>{t('contact.location')}</li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/5 py-6 text-center text-xs text-muted-foreground">
          &copy; 2026 {t('footer.copyright')}
        </div>
      </footer>

      {/* Floating WhatsApp */}
      <a
        href={`https://wa.me/${WHATSAPP_NUMBER}`}
        target="_blank"
        rel="noreferrer"
        className="fixed bottom-6 right-6 z-40 group"
        aria-label="Chat on WhatsApp"
      >
        <div className="absolute inset-0 rounded-full bg-green-500 blur-lg opacity-60 group-hover:opacity-90 transition-opacity" />
        <div className="relative flex items-center justify-center h-14 w-14 rounded-full bg-gradient-to-br from-green-500 to-emerald-600 text-white shadow-xl shadow-green-500/30 group-hover:scale-110 transition-transform">
          <MessageCircle className="h-6 w-6" />
        </div>
      </a>
    </div>
  );
}