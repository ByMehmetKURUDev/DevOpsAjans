/**
 * Site geneli sabitler, dil tablosu ve sayfa SEO metinleri.
 *
 * Burası tek kaynak: `vite.config.ts` bu dosyadan prerender route listesini,
 * sitemap girdilerini ve `VITE_*` ortam değişkenlerini besler; `prerender/app.js`
 * aynı tablodan `<head>` üretir; `Layout.tsx` da SPA gezinmesinde aynı
 * başlıkları kullanır.
 *
 * Bağımlılığı olmayan düz JS olarak kalmalı — `vite.config.ts` bunu ham Node
 * ortamında, herhangi bir derleme adımı olmadan import ediyor.
 */

export const SITE_URL = 'https://mehmetkuru.dev';
export const SITE_NAME = 'By Mehmet KURU Dev';

/** Varsayılan paylaşım görseli — site kendi domaininden servis eder. */
export const SITE_OG_IMAGE = `${SITE_URL}/logo.jpeg`;

/**
 * İçerik dilleri.
 *
 * Türkçe ön eksiz kökte durur (`/hizmetler` değil `/services` — route adları
 * İngilizce, içerik Türkçe). Diğer diller `/en/...`, `/de/...` biçiminde
 * ön ekli. Blog yalnızca Türkçe olduğu için ön ekli blog yolu üretilmiyor.
 */
export const DEFAULT_LANGUAGE = 'tr';

export const LANGUAGES = [
  { code: 'tr', htmlLang: 'tr', locale: 'tr_TR', dir: 'ltr' },
  { code: 'en', htmlLang: 'en', locale: 'en_US', dir: 'ltr' },
  { code: 'de', htmlLang: 'de', locale: 'de_DE', dir: 'ltr' },
  { code: 'ar', htmlLang: 'ar', locale: 'ar_AR', dir: 'rtl' },
  { code: 'ru', htmlLang: 'ru', locale: 'ru_RU', dir: 'ltr' },
  { code: 'zh', htmlLang: 'zh', locale: 'zh_CN', dir: 'ltr' },
  { code: 'hi', htmlLang: 'hi', locale: 'hi_IN', dir: 'ltr' },
];

export const LANGUAGE_CODES = LANGUAGES.map((l) => l.code);
export const PREFIXED_LANGUAGES = LANGUAGE_CODES.filter((c) => c !== DEFAULT_LANGUAGE);

export function getLanguage(code) {
  return LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
}

/** Çok dilli olarak yayınlanan sayfalar. Blog bu listede değil. */
export const PAGE_KEYS = ['home', 'services', 'portfolio', 'contact'];

/** Sayfa anahtarı → Türkçe kökteki route yolu. */
export const PAGE_PATHS = {
  home: '/',
  services: '/services',
  portfolio: '/portfolio',
  contact: '/contact',
};

export const PAGE_PRIORITY = {
  home: 1.0,
  services: 0.9,
  portfolio: 0.8,
  contact: 0.7,
};

/**
 * Sayfa başlıkları ve açıklamaları.
 *
 * Kod burada tek doğruluk kaynağı: prerender'ın ürettiği, yani Google'ın
 * gördüğü metin buradan geliyor. Yönetim panelindeki SEO alanları yalnızca
 * ziyaretçi tarafında ve yalnızca ana sayfa için bunu geçersiz kılar —
 * arama motorunun gördüğü metni değiştirmek için burayı düzenleyip yeniden
 * yayınlamak gerekir.
 *
 * Türkçe dışındaki çeviriler tarafımdan yazıldı; Arapça, Hintçe ve Çince
 * metinlerin yayına almadan önce ana dili konuşan biri tarafından
 * okunmasında fayda var.
 */
export const PAGE_SEO = {
  tr: {
    home: {
      title: 'Web Geliştirme ve Dijital Pazarlama | By Mehmet KURU Dev',
      description:
        'Web geliştirme, e-ticaret, SaaS ve dijital pazarlama hizmetleri. React ve TypeScript ile kurulan hızlı, ölçülebilir ve arama motorlarına uygun projeler.',
    },
    services: {
      title: 'Hizmetler: Web Geliştirme, E-Ticaret ve SEO | Mehmet KURU',
      description:
        'Özel web geliştirme, e-ticaret ve SaaS kurulumu, teknik SEO, Google Ads ve ölçümleme. Tek kıdemli lider altında uçtan uca yürütülen hizmetler.',
    },
    portfolio: {
      title: 'Portföy: Web, E-Ticaret ve SaaS Projeleri | Mehmet KURU',
      description:
        'Teslim edilen web uygulamaları, e-ticaret altyapıları, SaaS platformları ve pazarlama siteleri. Her projede kullanılan yaklaşım ve elde edilen sonuçlar.',
    },
    contact: {
      title: 'İletişim | By Mehmet KURU Dev',
      description:
        'Projenizi konuşmak için yazın. E-posta, WhatsApp veya iletişim formu üzerinden ulaşın; 24 saat içinde dürüst bir değerlendirmeyle dönüş yapılır.',
    },
  },
  en: {
    home: {
      title: 'Web Development and Digital Marketing | By Mehmet KURU Dev',
      description:
        'Web development, e-commerce, SaaS and digital marketing services. Fast, measurable and search-friendly products built with React and TypeScript.',
    },
    services: {
      title: 'Services: Web Development, E-Commerce and SEO | Mehmet KURU',
      description:
        'Custom web development, e-commerce and SaaS builds, technical SEO, Google Ads and measurement — delivered end to end under one senior lead.',
    },
    portfolio: {
      title: 'Portfolio: Web, E-Commerce and SaaS Projects | Mehmet KURU',
      description:
        'Delivered web applications, e-commerce platforms, SaaS products and marketing sites, with the approach taken and the results reached on each.',
    },
    contact: {
      title: 'Contact | By Mehmet KURU Dev',
      description:
        'Tell us about your project by email, WhatsApp or the contact form. You get an honest assessment back within 24 hours.',
    },
  },
  de: {
    home: {
      title: 'Webentwicklung und digitales Marketing | By Mehmet KURU Dev',
      description:
        'Webentwicklung, E-Commerce, SaaS und digitales Marketing. Schnelle, messbare und suchmaschinenfreundliche Projekte mit React und TypeScript.',
    },
    services: {
      title: 'Leistungen: Webentwicklung, E-Commerce und SEO | Mehmet KURU',
      description:
        'Individuelle Webentwicklung, E-Commerce- und SaaS-Aufbau, technisches SEO, Google Ads und Messung — durchgängig von einer erfahrenen Leitung betreut.',
    },
    portfolio: {
      title: 'Portfolio: Web-, E-Commerce- und SaaS-Projekte | Mehmet KURU',
      description:
        'Umgesetzte Webanwendungen, E-Commerce-Plattformen, SaaS-Produkte und Marketing-Websites — mit Vorgehen und Ergebnissen je Projekt.',
    },
    contact: {
      title: 'Kontakt | By Mehmet KURU Dev',
      description:
        'Schildern Sie Ihr Projekt per E-Mail, WhatsApp oder Kontaktformular. Innerhalb von 24 Stunden erhalten Sie eine ehrliche Einschätzung.',
    },
  },
  ar: {
    home: {
      title: 'تطوير المواقع والتسويق الرقمي | By Mehmet KURU Dev',
      description:
        'خدمات تطوير المواقع والتجارة الإلكترونية ومنصات SaaS والتسويق الرقمي. مشاريع سريعة وقابلة للقياس ومهيأة لمحركات البحث باستخدام React وTypeScript.',
    },
    services: {
      title: 'الخدمات: تطوير المواقع والتجارة الإلكترونية وتحسين محركات البحث | Mehmet KURU',
      description:
        'تطوير مواقع مخصص، وبناء متاجر إلكترونية ومنصات SaaS، وتحسين تقني لمحركات البحث، وإعلانات Google والقياس — بإشراف مباشر من مسؤول واحد.',
    },
    portfolio: {
      title: 'أعمالنا: مشاريع الويب والتجارة الإلكترونية وSaaS | Mehmet KURU',
      description:
        'تطبيقات ويب ومتاجر إلكترونية ومنتجات SaaS ومواقع تسويقية منجزة، مع شرح المنهج والنتائج في كل مشروع.',
    },
    contact: {
      title: 'اتصل بنا | By Mehmet KURU Dev',
      description:
        'اشرح مشروعك عبر البريد الإلكتروني أو واتساب أو نموذج التواصل، وستصلك إجابة صريحة خلال 24 ساعة.',
    },
  },
  ru: {
    home: {
      title: 'Веб-разработка и цифровой маркетинг | By Mehmet KURU Dev',
      description:
        'Веб-разработка, электронная коммерция, SaaS и цифровой маркетинг. Быстрые, измеримые и понятные поисковым системам проекты на React и TypeScript.',
    },
    services: {
      title: 'Услуги: веб-разработка, электронная коммерция и SEO | Mehmet KURU',
      description:
        'Индивидуальная веб-разработка, запуск интернет-магазинов и SaaS, техническое SEO, Google Ads и аналитика — под руководством одного специалиста.',
    },
    portfolio: {
      title: 'Портфолио: веб, электронная коммерция и SaaS | Mehmet KURU',
      description:
        'Реализованные веб-приложения, интернет-магазины, SaaS-продукты и маркетинговые сайты с описанием подхода и результатов.',
    },
    contact: {
      title: 'Контакты | By Mehmet KURU Dev',
      description:
        'Расскажите о проекте по электронной почте, в WhatsApp или через форму. Честный ответ в течение 24 часов.',
    },
  },
  zh: {
    home: {
      title: '网站开发与数字营销 | By Mehmet KURU Dev',
      description:
        '网站开发、电子商务、SaaS 与数字营销服务。使用 React 和 TypeScript 构建快速、可衡量且利于搜索引擎的项目。',
    },
    services: {
      title: '服务：网站开发、电子商务与 SEO | Mehmet KURU',
      description:
        '定制网站开发、电商与 SaaS 搭建、技术 SEO、Google Ads 与数据衡量，由一位资深负责人端到端交付。',
    },
    portfolio: {
      title: '作品集：网站、电商与 SaaS 项目 | Mehmet KURU',
      description:
        '已交付的网页应用、电商平台、SaaS 产品与营销网站，并说明每个项目的做法与成果。',
    },
    contact: {
      title: '联系方式 | By Mehmet KURU Dev',
      description: '通过电子邮件、WhatsApp 或联系表单说明您的项目，24 小时内获得坦诚的评估。',
    },
  },
  hi: {
    home: {
      title: 'वेब डेवलपमेंट और डिजिटल मार्केटिंग | By Mehmet KURU Dev',
      description:
        'वेब डेवलपमेंट, ई-कॉमर्स, SaaS और डिजिटल मार्केटिंग सेवाएँ। React और TypeScript पर बने तेज़, मापनीय और सर्च-अनुकूल प्रोजेक्ट।',
    },
    services: {
      title: 'सेवाएँ: वेब डेवलपमेंट, ई-कॉमर्स और SEO | Mehmet KURU',
      description:
        'कस्टम वेब डेवलपमेंट, ई-कॉमर्स और SaaS सेटअप, तकनीकी SEO, Google Ads और मेज़रमेंट — एक ही वरिष्ठ लीड के तहत आद्योपांत।',
    },
    portfolio: {
      title: 'पोर्टफ़ोलियो: वेब, ई-कॉमर्स और SaaS प्रोजेक्ट | Mehmet KURU',
      description:
        'पूरे किए गए वेब ऐप्लिकेशन, ई-कॉमर्स प्लेटफ़ॉर्म, SaaS उत्पाद और मार्केटिंग साइटें, हर प्रोजेक्ट के तरीक़े और नतीजों के साथ।',
    },
    contact: {
      title: 'संपर्क | By Mehmet KURU Dev',
      description:
        'अपना प्रोजेक्ट ईमेल, WhatsApp या संपर्क फ़ॉर्म से बताइए। 24 घंटे के भीतर ईमानदार आकलन मिलेगा।',
    },
  },
};

/** Blog yalnızca Türkçe yayımlanıyor. */
export const BLOG_INDEX_ROUTE = {
  routePath: '/blog',
  priority: 0.9,
  title: 'Blog: SEO, Reklam Ölçümleme ve Web Geliştirme Rehberleri',
  description:
    'Teknik SEO, Google Ads ve GA4 ölçümleme, Customer 360 veri yönetimi ve web geliştirme üzerine uygulamaya dönük rehberler.',
};

/** Arama motorlarına açılmaması gereken uygulama içi route'lar. */
export const NOINDEX_ROUTES = ['/client', '/admin', '/auth/callback', '/auth/error'];

/** Ana sayfada yayınlanan yapısal veri. */
export const ORGANIZATION_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'ProfessionalService',
  name: SITE_NAME,
  url: `${SITE_URL}/`,
  image: SITE_OG_IMAGE,
  description: 'Web geliştirme, özel yazılım ve dijital pazarlama hizmetleri.',
  email: 'by@mehmetkuru.dev',
  telephone: '+90 541 296 58 78',
  priceRange: '$$',
  areaServed: 'TR',
  address: {
    '@type': 'PostalAddress',
    addressCountry: 'TR',
    addressLocality: 'İstanbul',
  },
  founder: {
    '@type': 'Person',
    name: 'Mehmet KURU',
    jobTitle: 'Full-stack Developer & Digital Marketing Specialist',
  },
};

/** Bir sayfanın belirli dildeki yolu. Türkçe ön eksiz. */
export function localizedPath(lang, pageKey) {
  const base = PAGE_PATHS[pageKey];
  if (lang === DEFAULT_LANGUAGE) return base;
  return base === '/' ? `/${lang}` : `/${lang}${base}`;
}

/**
 * Canonical adres biçimi: kök dışında sondaki eğik çizgi yok.
 *
 * `/services` ve `/services/` Google için iki ayrı URL. Sitemap eklentisi
 * yolları üretilen HTML'lerden eğik çizgisiz topluyor; canonical'ın da aynı
 * biçimde olması ikisinin ayrışmasını önlüyor.
 */
export function canonicalPathFor(pathname) {
  const trimmed = pathname.replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
}

/** Verilen yola göre canonical biçiminde mutlak URL üretir. */
export function absoluteUrl(pathname) {
  const normalized = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${SITE_URL}${canonicalPathFor(normalized)}`;
}

/** Bir yolun hangi dile ve hangi sayfaya karşılık geldiğini çözer. */
export function resolveRoute(pathname) {
  const path = canonicalPathFor(pathname);
  const segments = path.split('/').filter(Boolean);
  const maybeLang = segments[0];

  if (PREFIXED_LANGUAGES.includes(maybeLang)) {
    const rest = `/${segments.slice(1).join('/')}`.replace(/\/$/, '') || '/';
    const pageKey = PAGE_KEYS.find((key) => PAGE_PATHS[key] === rest);
    return pageKey ? { lang: maybeLang, pageKey, path } : { lang: maybeLang, pageKey: null, path };
  }

  const pageKey = PAGE_KEYS.find((key) => PAGE_PATHS[key] === path);
  return { lang: DEFAULT_LANGUAGE, pageKey, path };
}

/** Prerender edilecek bütün çok dilli sayfa yolları. */
export function getLocalizedRoutes() {
  const routes = [];
  for (const { code } of LANGUAGES) {
    for (const pageKey of PAGE_KEYS) {
      routes.push({
        lang: code,
        pageKey,
        path: localizedPath(code, pageKey),
        priority: PAGE_PRIORITY[pageKey],
      });
    }
  }
  return routes;
}
