import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Menu, X, User, LogIn, LogOut, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ScrollToTop from '@/components/ScrollToTop';
import SocialLinks from '@/components/SocialLinks';
import StoreBadges from '@/components/StoreBadges';
import { client } from '@/lib/sdkClient';
import { useTranslation } from 'react-i18next';
import {
  useSiteSettings,
  isAdminUser,
  type SettingsMap,
} from '@/lib/siteSettings';
import {
  SUPPORTED_LANGUAGES as LANGUAGES,
  getLanguageMeta,
  changeAppLanguage,
} from '@/i18n';
// Sayfa meta verilerinin tek kaynağı. Bu dosya bağımlılığı olmayan düz JS
// olduğu için hem vite.config (Node) hem prerender hem de istemci okuyabiliyor.
import {
  BLOG_INDEX_ROUTE,
  DEFAULT_LANGUAGE,
  LANGUAGE_CODES,
  PAGE_SEO,
  PAGE_SEO_KEYS,
  SITE_NAME,
  SITE_URL,
  canonicalPathFor as normalizeRoutePath,
  getLanguage as getSiteLanguage,
  localizedPath,
  resolveRoute,
} from '../../prerender/site.js';

/** `/blog/<slug>` biçimindeki tekil yazı yolu mu? */
function isBlogPostPath(path: string): boolean {
  return path.startsWith('/blog/') && path.length > '/blog/'.length;
}

/**
 * Yola karşılık gelen başlık/açıklama.
 *
 * Öncelik: panelde o dil için girilen değer → panelin dilsiz değeri →
 * koddaki varsayılan. Aynı sıra `prerender/settings.js` içinde de
 * uygulanıyor, böylece Google'ın gördüğü metin ile ziyaretçinin gördüğü
 * metin ayrışmıyor.
 */
function getRouteMeta(path: string, settings: SettingsMap) {
  const pick = (settingKey: string, lang: string, fallback: string) => {
    const localized = settings[`${settingKey}__${lang}`]?.trim();
    if (localized) return localized;
    const base = settings[settingKey]?.trim();
    if (base) return base;
    return fallback;
  };

  if (path === BLOG_INDEX_ROUTE.routePath) {
    return {
      pageKey: null as string | null,
      title: pick(PAGE_SEO_KEYS.blog.title, DEFAULT_LANGUAGE, BLOG_INDEX_ROUTE.title),
      description: pick(
        PAGE_SEO_KEYS.blog.description, DEFAULT_LANGUAGE, BLOG_INDEX_ROUTE.description,
      ),
    };
  }

  const { lang, pageKey } = resolveRoute(path);
  if (!pageKey) return undefined;

  const seo = PAGE_SEO[lang]?.[pageKey];
  const keys = PAGE_SEO_KEYS[pageKey];
  if (!seo || !keys) return undefined;

  return {
    pageKey: pageKey as string | null,
    title: pick(keys.title, lang, seo.title),
    description: pick(keys.description, lang, seo.description),
  };
}


interface AuthUser {
  id?: string;
  email?: string;
  name?: string;
  role?: string;
  [key: string]: unknown;
}

export default function Layout() {
  const { t, i18n } = useTranslation();
  const { settings } = useSiteSettings();
  const [open, setOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  // Gezinme bağlantıları aktif dilin ön ekini taşır; blog yalnızca Türkçe.
  const activeLang = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
  const NAV_LINKS = [
    { to: localizedPath(activeLang, 'home'), label: t('nav.home') },
    { to: localizedPath(activeLang, 'services'), label: t('nav.services') },
    { to: localizedPath(activeLang, 'portfolio'), label: t('nav.portfolio') },
    { to: BLOG_INDEX_ROUTE.routePath, label: t('nav.blog') },
    { to: localizedPath(activeLang, 'contact'), label: t('nav.contact') },
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
  const handleRegister = () => client.auth.toLogin();
  const handleLogout = async () => {
    try {
      await client.auth.logout();
    } finally {
      setUser(null);
      window.location.href = '/';
    }
  };

  /**
   * Dil değişimi artık URL'i de değiştiriyor.
   *
   * Çevirisi olan bir sayfadaysak o dilin gerçek adresine gidilir
   * (`/services` → `/de/services`); böylece seçilen dil paylaşılabilir ve
   * arama motorunun indekslediği adresle aynı olur. Blog Türkçe olduğu için
   * orada yalnızca arayüz dili değişir, adres olduğu gibi kalır.
   */
  const switchLang = (code: string) => {
    setLangOpen(false);
    const { pageKey } = resolveRoute(location.pathname);

    if (pageKey) {
      navigate(localizedPath(code, pageKey));
      return;
    }

    void changeAppLanguage(code);
  };

  const currentLang = getLanguageMeta(i18n.language);
  const isRtl = currentLang.dir === 'rtl';

  /**
   * Sayfa bazlı meta title/description, canonical ve hreflang etiketleri.
   *
   * Önceki hâlinde bu efekt her route'ta `settings.seo_meta_title` değerini
   * basıyordu: prerender'ın ürettiği doğru başlık ve açıklama, sayfa
   * hidrate olur olmaz jenerik site başlığıyla eziliyordu — blog yazıları
   * dâhil. Artık başlık route'un kendi tablosundan geliyor ve kendi
   * meta'sını yöneten sayfalarda (tekil blog yazısı) efekt hiç çalışmıyor.
   */
  useEffect(() => {
    const currentPath = normalizeRoutePath(location.pathname);

    // Tekil blog yazısı kendi başlığını BlogPostPage içinde yönetiyor.
    if (isBlogPostPath(currentPath)) return;

    const routeMeta = getRouteMeta(currentPath, settings);
    const title = routeMeta?.title || SITE_NAME;
    const description = routeMeta?.description || '';
    document.title = title;

    const upsertMeta = (selector: string, attrs: Record<string, string>) => {
      let el = document.head.querySelector<HTMLMetaElement>(selector);
      if (!el) {
        el = document.createElement('meta');
        document.head.appendChild(el);
      }
      Object.entries(attrs).forEach(([k, v]) => el!.setAttribute(k, v));
    };

    // Canonical: SPA gezinmesinde de doğru adresi göstermesi gerekiyor.
    const canonicalPath = currentPath;
    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement('link');
      canonical.setAttribute('rel', 'canonical');
      document.head.appendChild(canonical);
    }
    canonical.setAttribute('href', `${SITE_URL}${canonicalPath}`);

    upsertMeta('meta[name="description"]', { name: 'description', content: description });
    upsertMeta('meta[property="og:title"]', { property: 'og:title', content: title });
    upsertMeta('meta[property="og:description"]', {
      property: 'og:description',
      content: description,
    });
    upsertMeta('meta[property="og:locale"]', {
      property: 'og:locale',
      content: currentLang.htmlLang,
    });
    upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: title });
    upsertMeta('meta[name="twitter:description"]', {
      name: 'twitter:description',
      content: description,
    });

    /*
     * hreflang.
     *
     * Önceki hâli her sayfaya yedi dil için `?lang=xx` alternatifi
     * basıyordu; o adreslerin hepsi aynı HTML'i döndürdüğü için Google'a
     * her sayfanın yedi kopyası bildiriliyordu. Artık alternatifler
     * yalnızca gerçekten çevirisi olan sayfalar için, gerçek `/en/...`
     * adresleriyle üretiliyor. Blog Türkçe olduğundan orada hiç yok.
     */
    document.head
      .querySelectorAll('link[data-i18n-hreflang="true"]')
      .forEach((el) => el.remove());

    if (routeMeta?.pageKey) {
      const alternates = [
        ...LANGUAGE_CODES.map((code) => ({
          hreflang: getSiteLanguage(code).htmlLang,
          href: `${SITE_URL}${localizedPath(code, routeMeta.pageKey)}`,
        })),
        {
          hreflang: 'x-default',
          href: `${SITE_URL}${localizedPath(DEFAULT_LANGUAGE, routeMeta.pageKey)}`,
        },
      ];

      for (const alternate of alternates) {
        const link = document.createElement('link');
        link.setAttribute('rel', 'alternate');
        link.setAttribute('hreflang', alternate.hreflang);
        link.setAttribute('data-i18n-hreflang', 'true');
        link.setAttribute('href', alternate.href);
        document.head.appendChild(link);
      }
    }
  }, [settings, currentLang.htmlLang, location.pathname]);

  /** URL'de ?lang=xx varsa o dile geçer (hreflang varyantları için). */
  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get('lang');
    if (param && LANGUAGES.some((l) => l.code === param) && param !== i18n.language) {
      void changeAppLanguage(param);
    }
  }, [i18n]);

  const isAdmin = isAdminUser(user, settings);
  const logoSrc = settings.brand_logo || '/assets/logo-mark.webp';
  const whatsappNumber = (settings.whatsapp_number || '905412965878').replace(/\D/g, '');

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
            {/*
              Logo saydam zeminli: kutu, çerçeve ve arkasındaki mor parıltı
              kaldırıldı — saydam görselin arkasında mor bir leke olarak
              görünüyorlardı. Künye doğrudan site zemininin üstünde duruyor.
            */}
            <div className="relative">
              <img
                src={logoSrc}
                alt={t('ui.logoAlt')}
                width={48}
                height={48}
                decoding="async"
                className="relative h-12 w-12 object-contain transition-transform group-hover:scale-105"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
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
                <div
                  className={`absolute top-full mt-2 w-44 max-h-[70vh] overflow-y-auto rounded-xl glass p-1.5 animate-in fade-in slide-in-from-top-2 duration-200 z-50 ${
                    isRtl ? 'left-0' : 'right-0'
                  }`}
                >
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => switchLang(lang.code)}
                      className={`w-full text-start px-3 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                        lang.code === i18n.language
                          ? 'bg-purple-500/15 text-foreground'
                          : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                      }`}
                    >
                      <span className="text-base">{lang.flag}</span>
                      <span className="font-medium">{lang.label}</span>
                      <span className="ms-auto text-xs text-muted-foreground">
                        {lang.full}
                      </span>
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
                    {isAdmin ? t('nav.adminPanel') : t('nav.clientPanel')}
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleLogout}
                  className="gap-2 text-muted-foreground hover:text-foreground"
                  aria-label={t('nav.signOut')}
                >
                  <LogOut className="h-4 w-4" />
                </Button>
              </>
            ) : (
              !authLoading && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleLogin}
                    className="gap-2 !bg-transparent !hover:bg-transparent border-white/20 hover:border-purple-400/60 text-foreground"
                  >
                    <LogIn className="h-4 w-4" />
                    {t('nav.signIn')}
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleRegister}
                    className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 glow-primary"
                  >
                    <UserPlus className="h-4 w-4" />
                    {t('nav.signUp')}
                  </Button>
                </>
              )
            )}
          </div>

          <button
            className="lg:hidden p-2 rounded-md hover:bg-white/5"
            onClick={() => setOpen((s) => !s)}
            aria-label={t('ui.toggleMenu')}
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
              <p className="px-4 py-1 text-xs uppercase tracking-widest text-muted-foreground">
                {t('nav.language')}
              </p>
              <div className="flex flex-wrap gap-2 px-4 py-2">
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
                      <User className="h-4 w-4" />{' '}
                      {isAdmin ? t('nav.adminPanel') : t('nav.clientPanel')}
                    </Button>
                  </Link>
                  <Button
                    variant="ghost"
                    onClick={handleLogout}
                    className="w-full gap-2"
                  >
                    <LogOut className="h-4 w-4" /> {t('nav.signOut')}
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    onClick={handleLogin}
                    className="w-full gap-2 !bg-transparent !hover:bg-transparent border-white/20 text-foreground"
                  >
                    <LogIn className="h-4 w-4" /> {t('nav.signIn')}
                  </Button>
                  <Button
                    onClick={handleRegister}
                    className="w-full gap-2 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
                  >
                    <UserPlus className="h-4 w-4" /> {t('nav.signUp')}
                  </Button>
                </>
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
      <footer className="border-t border-white/5 bg-background/60 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 grid gap-10 md:grid-cols-4">
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center gap-3">
              <img
                src={logoSrc}
                alt={t('ui.logoAlt')}
                width={48}
                height={48}
                loading="lazy"
                decoding="async"
                className="h-12 w-12 object-contain"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
            </div>
            <p className="text-sm text-muted-foreground max-w-md">
              {t('footer.desc')}
            </p>
            {/*
              Tek kontrol noktası: footer, Nasıl Çalışır ve İletişim aynı
              bileşeni kullanıyor, adresler panelden giriliyor. Yedi ağ
              birden doluyken dar ekranda taşmasın diye satır kırılıyor.
            */}
            <SocialLinks className="pt-2" />
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-4 tracking-wide">
              {t('footer.navigate')}
            </h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {NAV_LINKS.map((l) => (
                <li key={l.to}>
                  {/*
                    `inline-block` + dikey dolgu: bağlantı metni 16 piksel
                    yüksekliğindeydi ve telefonda ıskalanıyordu. Dolgu
                    dokunma alanını 40 piksele çıkarıyor, görünüm değişmiyor.
                  */}
                  <Link
                    to={l.to}
                    className="inline-block py-2 hover:text-foreground transition-colors"
                  >
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-4 tracking-wide">
              {t('footer.contact')}
            </h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>
                <a
                  href={`mailto:${settings.contact_email}`}
                  className="hover:text-foreground"
                >
                  {settings.contact_email}
                </a>
              </li>
              <li>
                <a
                  href={`tel:${settings.contact_phone.replace(/\s/g, '')}`}
                  className="hover:text-foreground"
                >
                  {settings.contact_phone}
                </a>
              </li>
              <li>{settings.contact_address}</li>
            </ul>
            {/* Uygulama mağazası bağlantıları — panelde adres girilmişse görünür. */}
            <StoreBadges
              appStoreUrl={settings.app_store_url}
              googlePlayUrl={settings.google_play_url}
            />
          </div>
        </div>
        <div className="border-t border-white/5 py-6 text-center text-xs text-muted-foreground">
          &copy; 2026 {t('footer.copyright')}
        </div>
      </footer>

      <ScrollToTop />

      {/* Floating WhatsApp */}
      <a
        href={`https://wa.me/${whatsappNumber}`}
        target="_blank"
        rel="noreferrer"
        className={`fixed bottom-6 z-40 group ${isRtl ? 'left-6' : 'right-6'}`}
        aria-label={t('contact.whatsappLabel')}
      >
        <div className="absolute inset-0 rounded-full bg-green-500 blur-lg opacity-60 group-hover:opacity-90 transition-opacity" />
        <div className="relative flex items-center justify-center h-14 w-14 rounded-full bg-[#25D366] text-white shadow-xl shadow-green-500/30 group-hover:scale-110 transition-transform">
          <svg className="h-7 w-7" fill="currentColor" viewBox="0 0 24 24">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
          </svg>
        </div>
      </a>
    </div>
  );
}