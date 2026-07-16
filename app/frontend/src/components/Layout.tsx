import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Menu, X, MessageCircle, User, LogIn, LogOut, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';

const client = createClient();

const WHATSAPP_NUMBER = '905555555555';

const LANGUAGES = [
  { code: 'en', label: 'EN', full: 'English' },
  { code: 'tr', label: 'TR', full: 'Türkçe' },
  { code: 'de', label: 'DE', full: 'Deutsch' },
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
    { to: '/about', label: t('nav.about') },
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
              <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-purple-500 via-pink-500 to-cyan-400 blur-md opacity-60 group-hover:opacity-100 transition-opacity" />
              <img
                src="/assets/logo.avif"
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
                <Globe className="h-4 w-4" />
                {currentLang.label}
              </button>
              {langOpen && (
                <div className="absolute top-full right-0 mt-2 w-36 rounded-xl glass p-1.5 animate-in fade-in slide-in-from-top-2 duration-200 z-50">
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => switchLang(lang.code)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                        lang.code === i18n.language
                          ? 'bg-purple-500/15 text-foreground'
                          : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                      }`}
                    >
                      <span className="font-medium">{lang.label}</span>
                      <span className="ml-2 text-xs text-muted-foreground">{lang.full}</span>
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
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      lang.code === i18n.language
                        ? 'bg-purple-500/20 text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
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

      {/* Footer */}
      <footer className="mt-24 border-t border-white/5 bg-background/60 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 grid gap-10 md:grid-cols-4">
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <img
                src="/assets/logo.avif"
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
            <div className="flex gap-3 pt-2">
              {['Twitter', 'GitHub', 'LinkedIn', 'Instagram'].map((s) => (
                <a
                  key={s}
                  href="#"
                  className="text-xs uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
                >
                  {s}
                </a>
              ))}
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
              <li>hello@mehmetkuru.dev</li>
              <li>{t('contact.location')}</li>
              <li>
                <a
                  href={`https://wa.me/${WHATSAPP_NUMBER}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-foreground"
                >
                  WhatsApp
                </a>
              </li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/5 py-6 text-center text-xs text-muted-foreground">
          &copy; {new Date().getFullYear()} {t('footer.copyright')}
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