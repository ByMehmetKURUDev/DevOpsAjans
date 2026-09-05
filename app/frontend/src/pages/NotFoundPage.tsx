import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Home, ArrowLeft } from 'lucide-react';

/**
 * Hafif 404 sayfası.
 *
 * Platform eklentisi (vite-plugin-404), App.tsx içinde `NotFoundPage` importu
 * ve `path="*"` route'u bulamazsa base64 gömülü görsel içeren ~366 kB'lık
 * varsayılan bir 404 modülünü ana bundle'a enjekte ediyor. Bu bileşen o
 * enjeksiyonu engeller ve aynı işlevi birkaç kB ile karşılar.
 */

type Copy = {
  badge: string;
  title: string;
  description: string;
  home: string;
  back: string;
};

const COPY: Record<string, Copy> = {
  tr: {
    badge: 'Sayfa bulunamadı',
    title: 'Aradığınız sayfa burada değil',
    description:
      'Bağlantı taşınmış, adı değişmiş veya hiç var olmamış olabilir. Ana sayfadan devam edebilirsiniz.',
    home: 'Ana sayfaya dön',
    back: 'Geri git',
  },
  en: {
    badge: 'Page not found',
    title: "The page you're looking for isn't here",
    description:
      'The link may have moved, been renamed, or never existed. You can continue from the homepage.',
    home: 'Back to homepage',
    back: 'Go back',
  },
  de: {
    badge: 'Seite nicht gefunden',
    title: 'Die gesuchte Seite ist nicht hier',
    description:
      'Der Link wurde möglicherweise verschoben, umbenannt oder hat nie existiert. Sie können auf der Startseite fortfahren.',
    home: 'Zur Startseite',
    back: 'Zurück',
  },
  ar: {
    badge: 'الصفحة غير موجودة',
    title: 'الصفحة التي تبحث عنها غير موجودة',
    description:
      'قد يكون الرابط قد نُقل أو تغيّر اسمه أو لم يكن موجودًا أبدًا. يمكنك المتابعة من الصفحة الرئيسية.',
    home: 'العودة إلى الصفحة الرئيسية',
    back: 'رجوع',
  },
  ru: {
    badge: 'Страница не найдена',
    title: 'Страница, которую вы ищете, отсутствует',
    description:
      'Ссылка могла быть перемещена, переименована или никогда не существовала. Вы можете продолжить с главной страницы.',
    home: 'На главную страницу',
    back: 'Назад',
  },
  zh: {
    badge: '页面未找到',
    title: '您要访问的页面不存在',
    description: '该链接可能已移动、被重命名或从未存在。您可以从首页继续浏览。',
    home: '返回首页',
    back: '返回上一页',
  },
  hi: {
    badge: 'पेज नहीं मिला',
    title: 'आप जिस पेज को खोज रहे हैं वह यहाँ नहीं है',
    description:
      'यह लिंक स्थानांतरित हो सकता है, इसका नाम बदल गया हो सकता है, या यह कभी मौजूद नहीं था। आप होमपेज से आगे बढ़ सकते हैं।',
    home: 'होमपेज पर लौटें',
    back: 'वापस जाएँ',
  },
};

const NotFoundPage = () => {
  const { i18n } = useTranslation();
  const lang = (i18n.language || 'tr').split('-')[0];
  const copy = COPY[lang] ?? COPY.tr;

  return (
    <section className="min-h-[70vh] flex items-center justify-center px-4 py-20">
      <div className="max-w-xl w-full text-center">
        <p className="text-xs uppercase tracking-[0.3em] text-purple-300/80">{copy.badge}</p>
        <p
          aria-hidden="true"
          className="mt-4 text-[5.5rem] leading-none font-black bg-gradient-to-br from-purple-300 via-purple-500 to-fuchsia-600 bg-clip-text text-transparent"
        >
          404
        </p>
        <h1 className="mt-4 text-2xl sm:text-3xl font-bold text-white">{copy.title}</h1>
        <p className="mt-4 text-sm sm:text-base text-purple-100/70">{copy.description}</p>

        <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold text-white bg-gradient-to-r from-purple-600 to-fuchsia-600 hover:from-purple-500 hover:to-fuchsia-500 transition-colors"
          >
            <Home className="w-4 h-4" aria-hidden="true" />
            {copy.home}
          </Link>
          <button
            type="button"
            onClick={() => window.history.back()}
            className="inline-flex items-center justify-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold text-purple-100 border border-purple-400/40 hover:border-purple-300 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            {copy.back}
          </button>
        </div>
      </div>
    </section>
  );
};

export default NotFoundPage;