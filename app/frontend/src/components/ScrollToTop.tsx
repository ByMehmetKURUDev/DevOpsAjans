import { useEffect, useState } from 'react';
import { ArrowUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Sayfa başına dönüş butonu.
 *
 * Sağ altta WhatsApp butonu duruyor; bu yüzden onun üstüne yerleşiyor
 * (`bottom-24`), yan yana değil — dar ekranda çakışıyorlardı.
 * RTL dillerde sağ/sol otomatik dönsün diye `end-6` kullanılıyor.
 */
export default function ScrollToTop() {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 600);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const toTop = () => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
  };

  return (
    <button
      type="button"
      onClick={toTop}
      aria-label={t('ui.scrollTop')}
      title={t('ui.scrollTop')}
      className={`fixed bottom-24 end-6 z-40 inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/15 bg-[#12091f]/90 text-white shadow-lg backdrop-blur transition-all duration-300 hover:border-purple-400/60 hover:bg-[#1b0e2e] focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-400 ${
        visible ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-3 opacity-0'
      }`}
    >
      <ArrowUp className="h-5 w-5" aria-hidden="true" />
    </button>
  );
}
