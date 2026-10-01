import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { DEFAULT_LANGUAGE, LANGUAGE_CODES, localizedPath } from '../../prerender/site.js';

/**
 * Formların gönder düğmesi yakınındaki kısa aydınlatma satırı (Faz 3Y).
 *
 * Bir BİLGİLENDİRME: onay kutusu değil, açık rızayla birleştirilmiyor.
 * Metin verilmezse ek paketteki genel cümle (`aydinlatma.satir`) kullanılır —
 * o durumda sayfa `ekliLazy('aydinlatma', …)` ile yüklenmeli. Formun zaten
 * kendi gizlilik cümlesi varsa (`metin`) yalnız bağlantı eklenir. Bağlantı
 * etkin dildeki /gizlilik sayfasına, yeni sekmede açılır (form kaybolmasın).
 */
export default function AydinlatmaSatiri({ metin, className }: { metin?: string; className?: string }) {
  const { t, i18n } = useTranslation();
  const dil = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
  return (
    <p className={className ?? 'text-center text-[11px] leading-relaxed text-muted-foreground'} data-aydinlatma>
      {metin ?? t('aydinlatma.satir')}{' '}
      <Link
        to={localizedPath(dil, 'gizlilik')}
        target="_blank"
        rel="noopener"
        className="underline underline-offset-2 transition-colors hover:text-foreground"
      >
        {t('footer.gizlilik')}
      </Link>
    </p>
  );
}
