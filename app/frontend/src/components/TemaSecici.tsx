import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { temaOku, temaYaz, type Tema } from '@/lib/tema';

/**
 * Renk teması tuşu — dil seçicinin yanında.
 *
 * İki yuvarlak nokta: mor ve yeşil. Seçilen nokta çerçeveleniyor.
 * Renk örnekleri temanın kendi değişkeninden değil SABİT değerlerden
 * çiziliyor; yoksa yeşil temadayken yeşil nokta da yeşil olur ve iki
 * seçenek birbirinden ayırt edilemez.
 *
 * `radiogroup` olarak işaretli: ekran okuyucu "mor seçili, 1/2" diye
 * okuyor, ok tuşlarıyla geçiş beklentisini karşılıyor.
 */

const ORNEK: Record<Tema, string> = {
  mor: 'linear-gradient(135deg,#8b3dff,#d4a5ff)',
  yesil: 'linear-gradient(135deg,#00dc82,#38bdf8)',
};

interface TemaSeciciProps {
  /** Mobil menüde tuşlar biraz daha büyük. */
  buyuk?: boolean;
}

export default function TemaSecici({ buyuk = false }: TemaSeciciProps) {
  const { t } = useTranslation();
  const [tema, setTema] = useState<Tema>('mor');

  // İlk boyamada gerçek tema `index.html` tarafından zaten uygulanmış
  // oluyor; buradaki okuma yalnızca tuşu o duruma getirmek için.
  useEffect(() => setTema(temaOku()), []);

  const sec = (yeni: Tema) => {
    temaYaz(yeni);
    setTema(yeni);
  };

  const boyut = buyuk ? 'h-8 w-8' : 'h-6 w-6';

  return (
    <div
      role="radiogroup"
      aria-label={t('tema.baslik')}
      className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-1.5 py-1"
    >
      {(['mor', 'yesil'] as Tema[]).map((secenek) => {
        const aktif = tema === secenek;
        return (
          <button
            key={secenek}
            type="button"
            role="radio"
            aria-checked={aktif}
            title={t(`tema.${secenek}`)}
            onClick={() => sec(secenek)}
            className={`${boyut} rounded-full transition-all ${
              aktif
                ? 'ring-2 ring-white/70 ring-offset-2 ring-offset-background'
                : 'opacity-55 hover:opacity-100'
            }`}
            style={{ backgroundImage: ORNEK[secenek] }}
          >
            <span className="sr-only">{t(`tema.${secenek}`)}</span>
          </button>
        );
      })}
    </div>
  );
}
