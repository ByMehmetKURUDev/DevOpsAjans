import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Fragment, useEffect, useState } from 'react';
import { gorunumUygula } from '@/lib/gorunum';
import { Menu, X, User, LogIn, LogOut, UserPlus, Languages } from 'lucide-react';
import AsistanSohbeti from '@/components/AsistanSohbeti';
import PazarlamaEtiketleri from '@/components/PazarlamaEtiketleri';
import RizaBandi from '@/components/RizaBandi';
import { rizayiSifirla } from '@/lib/riza';
import { Button } from '@/components/ui/button';
import NotificationBell from '@/components/NotificationBell';
import ScrollToTop from '@/components/ScrollToTop';
import SocialLinks from '@/components/SocialLinks';
import StoreBadges from '@/components/StoreBadges';
import { client, oturumIziVarMi, oturumIziniTemizle, sunucuOturumunuKapat, yetkisizHataMi } from '@/lib/sdkClient';
import MarkaLogosu from '@/components/MarkaLogosu';
import HashKaydirma from '@/components/HashKaydirma';
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
  YASAL_SAYFALAR,
  absoluteUrl,
  canonicalPathFor as normalizeRoutePath,
  getLanguage as getSiteLanguage,
  localizedPath,
  resolveRoute,
} from '../../prerender/site.js';

/** `/blog/<slug>` biçimindeki tekil yazı yolu mu? */
function isBlogPostPath(path: string): boolean {
  return path.startsWith('/blog/') && path.length > '/blog/'.length;
}

/** Kaynaklar (liste + ayrıntı): başlığını sayfa kendisi yazıyor. Eşleşmede [, dil?, slug?]. */
const KAYNAK_YOLU = /^(?:\/([a-z]{2}))?\/kaynaklar(?:\/([^/]+))?$/;
/** Faz 4V — modül vitrini (liste, modül, paket): başlığını sayfa kendisi yazıyor. Eşleşmede [, dil?, alt yol?]. */
const MODUL_YOLU = /^(?:\/([a-z]{2}))?\/moduller((?:\/paket)?\/[^/]+)?$/;

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
  const { settings, loading: ayarlarYukleniyor } = useSiteSettings();
  // Site görünümü (Klasik / Modern) — admin panelindeki Görünüm ayarı.
  // Ayarlar gelene kadar koddaki varsayılan ('klasik') uygulanmıyor:
  // önbellek ya da derlemenin HTML'e yazdığı değer geçerli kalıyor.
  useEffect(() => {
    gorunumUygula(ayarlarYukleniyor ? undefined : settings.site_gorunum);
  }, [settings.site_gorunum, ayarlarYukleniyor]);
  const [open, setOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  // Gezinme bağlantıları aktif dilin ön ekini taşır; blog yalnızca Türkçe.
  const activeLang = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
  /*
   * Capali baglanti ("/#nasil-calisir") NavLink icin sadece "/" gorunuyor,
   * bu yuzden Ana Sayfa ile ayni anda aktif isaretleniyordu. Aktifligi
   * capaya gore kendimiz belirliyoruz.
   */
  const navAktifMi = (linkTo: string, routerAktif: boolean) => {
    const capaBasi = linkTo.indexOf('#');
    if (capaBasi !== -1) return location.hash === linkTo.slice(capaBasi);
    return routerAktif && !location.hash;
  };

  // Ana sayfa bağlantısı yalnız tam eşleşmede etkin: `/de` önekli her sayfayı (ör. /de/kaynaklar) kapsamasın.
  const anaSayfaYolu = localizedPath(activeLang, 'home');
  const NAV_LINKS = [
    { to: anaSayfaYolu, label: t('nav.home') },
    { to: localizedPath(activeLang, 'services'), label: t('nav.services') },
    { to: localizedPath(activeLang, 'portfolio'), label: t('nav.portfolio') },
    { to: localizedPath(activeLang, 'marketplace'), label: t('nav.marketplace') },
    { to: BLOG_INDEX_ROUTE.routePath, label: t('nav.blog') },
    { to: localizedPath(activeLang, 'contact'), label: t('nav.contact') },
  ];
  /*
   * Kaynaklar (Faz 3K) masaüstü üst menüde YOK: 1280 px ve üstünde (xl dolgusu)
   * yedinci bağlantı tr/en/de/ru'da sağdaki giriş düğmelerini kabın dışına
   * itiyordu (ölçüm: 3–40 px). Mobil menüde ve alt bilgide Blog'un hemen yanında.
   */
  const ALT_LINKS = [
    ...NAV_LINKS.slice(0, 5),
    { to: localizedPath(activeLang, 'kaynaklar'), label: t('nav.kaynaklar') },
    ...NAV_LINKS.slice(5),
  ];

  useEffect(() => {
    // Oturum izi yoksa cagri kesin 401 doner; bos yere istek atmiyoruz.
    if (!oturumIziVarMi()) {
      setAuthLoading(false);
      return;
    }
    // Render ucretsiz plani uykudan kalkarken `me()` yarim dakika askida
    // kalabiliyor. Eskiden bu sure boyunca header'da ne profil ne de
    // Giris/Kayit goruluyordu -- kullanici butonlar yok saniyordu.
    // Artik 3 saniyede vazgecip butonlari aciyoruz; yanit sonra gelirse
    // profil yerine oturuyor.
    let cevapGeldi = false;
    const zamanAsimi = window.setTimeout(() => {
      if (!cevapGeldi) setAuthLoading(false);
    }, 3000);

    client.auth
      .me()
      .then((res) => {
        if (res?.data) setUser(res.data as AuthUser);
        else oturumIziniTemizle();
      })
      .catch((hata) => {
        // Sadece 401'de siliyoruz: gecici ag hatasi oturumu dusurmesin.
        if (yetkisizHataMi(hata)) oturumIziniTemizle();
      })
      .finally(() => {
        cevapGeldi = true;
        window.clearTimeout(zamanAsimi);
        setAuthLoading(false);
      });

    return () => window.clearTimeout(zamanAsimi);
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
      await sunucuOturumunuKapat();
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

    // Dil her durumda burada değiştiriliyor: Türkçe kök yollarda (`/`,
    // `/marketplace`) dili ayarlayan bir kapı yok (LanguageGate yalnız
    // `/en`, `/de`… önekli yollarda). Yalnız adres değiştiğinde /en'den
    // Türkçeye geçen ziyaretçi Türkçe adreste İngilizce sayfa görüyordu.
    void changeAppLanguage(code);
    if (pageKey) {
      navigate(localizedPath(code, pageKey));
      return;
    }
    // Kaynak ayrıntısı: aynı kaynağın o dildeki adresi.
    const kaynak = normalizeRoutePath(location.pathname).match(KAYNAK_YOLU);
    if (kaynak?.[2]) navigate(`${localizedPath(code, 'kaynaklar')}/${kaynak[2]}`);
    // Modül / sektör paketi ayrıntısı: aynı sayfanın o dildeki adresi.
    const modul = normalizeRoutePath(location.pathname).match(MODUL_YOLU);
    if (modul?.[2]) navigate(`${localizedPath(code, 'moduller')}${modul[2]}`);
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

    // Tekil blog yazısı, Kaynaklar ve yasal sayfalar (Faz 3Y) başlığını kendisi yönetiyor.
    if (isBlogPostPath(currentPath) || KAYNAK_YOLU.test(currentPath) || MODUL_YOLU.test(currentPath)) return;
    if (YASAL_SAYFALAR.includes(resolveRoute(currentPath).pageKey ?? '')) return;

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
    canonical.setAttribute('href', absoluteUrl(canonicalPath));

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
          href: absoluteUrl(localizedPath(code, routeMeta.pageKey)),
        })),
        {
          hreflang: 'x-default',
          href: absoluteUrl(localizedPath(DEFAULT_LANGUAGE, routeMeta.pageKey)),
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
  const logoSrc = settings.brand_logo || '/assets/logo-mark-144.webp';

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
          <Link to="/" className="flex items-center gap-3 group shrink-0">
            {/*
              Logo saydam zeminli: kutu, çerçeve ve arkasındaki mor parıltı
              kaldırıldı — saydam görselin arkasında mor bir leke olarak
              görünüyorlardı. Künye doğrudan site zemininin üstünde duruyor.
            */}
            <MarkaLogosu />
          </Link>

          {/*
            1024–1279 px arası dar masaüstü: bağlantılar sıkıştırılıyor ve tek
            satırda tutuluyor. Almanca/Rusça etiketler uzun olduğu için eskiden
            menü taşıyor, Türkçe/İngilizce'de de iki satıra kırılıyordu.
          */}
          <nav className="hidden lg:flex items-center gap-0 xl:gap-1">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === anaSayfaYolu}
                className={({ isActive }) =>
                  `relative px-2 xl:px-4 py-2 text-[13px] xl:text-sm whitespace-nowrap font-medium transition-colors rounded-md ${
                    navAktifMi(link.to, isActive)
                      ? 'text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {link.label}
                    {navAktifMi(link.to, isActive) && (
                      <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 h-0.5 w-6 rounded-full bg-gradient-to-r from-purple-500 to-pink-500" />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="hidden lg:flex items-center gap-1.5 xl:gap-2 shrink-0">
            {/* Language switcher */}
            <div className="relative">
              <button
                onClick={() => setLangOpen((s) => !s)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
              >
                <Languages className="h-4 w-4" aria-hidden="true" />
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
                {/* Bildirim çanı yalnızca giriş yapmış kullanıcıya. */}
                <NotificationBell email={user.email} />
                <Link to={isAdmin ? '/admin' : '/client'} title={isAdmin ? t('nav.adminPanel') : t('nav.clientPanel')}>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={isAdmin ? t('nav.adminPanel') : t('nav.clientPanel')}
                    className="gap-2 hover:bg-purple-500/10 hover:text-purple-300"
                  >
                    <User className="h-4 w-4" />
                    <span className="hidden xl:inline">{isAdmin ? t('nav.adminPanel') : t('nav.clientPanel')}</span>
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
                    aria-label={t('nav.signIn')}
                    title={t('nav.signIn')}
                    className="gap-2 !bg-transparent !hover:bg-transparent border-white/20 hover:border-purple-400/60 text-foreground"
                  >
                    <LogIn className="h-4 w-4" />
                    {/* Dar masaüstünde (1024–1279) yalnız simge; menüye yer açılıyor. */}
                    <span className="hidden xl:inline">{t('nav.signIn')}</span>
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleRegister}
                    aria-label={t('nav.signUp')}
                    title={t('nav.signUp')}
                    className="gap-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white border-0 glow-primary"
                  >
                    <UserPlus className="h-4 w-4" />
                    <span className="hidden xl:inline">{t('nav.signUp')}</span>
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
            {ALT_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === anaSayfaYolu}
                className={({ isActive }) =>
                  `block px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                    navAktifMi(link.to, isActive)
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
            <MarkaLogosu />
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
            <h3 className="text-sm font-semibold mb-4 tracking-wide">
              {t('footer.navigate')}
            </h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {ALT_LINKS.map((l) => (
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
              <li>
                <Link
                  to={localizedPath(activeLang, 'roadmap')}
                  className="inline-block py-2 hover:text-foreground transition-colors"
                >
                  {t('footer.roadmap')}
                </Link>
              </li>
              <li>
                <Link
                  to={localizedPath(activeLang, 'siteAnalysis')}
                  className="inline-block py-2 hover:text-foreground transition-colors"
                >
                  {t('footer.siteAnalizi')}
                </Link>
              </li>
              {/* Faz 4V: modül vitrini — üst menü dolu olduğu için yalnız alt bilgide. */}
              <li>
                <Link
                  to={localizedPath(activeLang, 'moduller')}
                  className="inline-block py-2 hover:text-foreground transition-colors"
                  data-alt-moduller
                >
                  {t('footer.moduller')}
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-4 tracking-wide">
              {t('footer.contact')}
            </h3>
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
        <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-2 border-t border-white/5 py-6 text-center text-xs text-muted-foreground">
          <span>&copy; 2026 {t('footer.copyright')}</span>
          {/* Faz 3Y: yasal sayfalar (dile göre adres). */}
          {(YASAL_SAYFALAR as string[]).map((sayfa) => (
            <Fragment key={sayfa}>
              <span aria-hidden="true">·</span>
              <Link
                to={localizedPath(activeLang, sayfa)}
                className="inline-block py-1 underline-offset-2 transition-colors hover:text-foreground hover:underline"
                data-yasal-baglanti={sayfa}
              >
                {t(`footer.${sayfa}`)}
              </Link>
            </Fragment>
          ))}
          <span aria-hidden="true">·</span>
          {/*
            Rızayı geri almanın bir yolu olmak zorunda: KVKK ve GDPR
            "vazgeçmek en az onaylamak kadar kolay olsun" diyor.
            Karar sıfırlanınca bant yeniden çıkıyor.
          */}
          <button
            type="button"
            onClick={rizayiSifirla}
            className="underline underline-offset-2 transition-colors hover:text-foreground"
          >
            {t('riza.tercihler')}
          </button>
        </div>
      </footer>

      <HashKaydirma />
      <ScrollToTop />

      {/*
        Sağ alt köşe: tek tuş.

        Eskiden burada AI asistanın altında ayrı bir WhatsApp balonu
        vardı. WhatsApp artık asistan panelinin içindeki kanal satırında
        (arama, SMS, e-posta ve toplantı ile birlikte) — iki üst üste
        balon mobilde yer kaplıyor ve ziyaretçiye gereksiz bir seçim
        yaptırıyordu.
      */}
      <AsistanSohbeti />

      {/* Reklam ve dogrulama etiketleri; kimlikler panelden geliyor. */}
      <PazarlamaEtiketleri />

      {/* Olcum ve reklam rizasi; cevaplanana kadar hicbir izleme yok. */}
      <RizaBandi />

    </div>
  );
}