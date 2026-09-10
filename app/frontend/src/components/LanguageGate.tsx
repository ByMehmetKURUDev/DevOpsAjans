import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Layout from '@/components/Layout';
import NotFoundPage from '@/pages/NotFoundPage';
import { changeAppLanguage } from '@/i18n';
import { PREFIXED_LANGUAGES } from '../../prerender/site.js';

/**
 * `/en`, `/de` gibi dil ön ekli yolların kapısı.
 *
 * Ön ekteki kod desteklenen bir dil değilse 404 döner — aksi hâlde
 * `/:lang` deseni her bilinmeyen tek segmentli yolu yutar ve site
 * mevcut olmayan sayfalar için ana sayfayı gösterirdi.
 *
 * Geçerliyse uygulama dilini o koda çevirip normal düzeni render eder.
 * Prerender sırasında dil zaten doğru ayarlanmış olduğu için efekt
 * yalnızca istemci tarafında iş yapar.
 */
export default function LanguageGate() {
  const { lang } = useParams<{ lang: string }>();
  const isSupported = Boolean(lang) && PREFIXED_LANGUAGES.includes(lang as string);

  useEffect(() => {
    if (isSupported && lang) {
      void changeAppLanguage(lang);
    }
  }, [isSupported, lang]);

  if (!isSupported) {
    return <NotFoundPage />;
  }

  return <Layout />;
}
