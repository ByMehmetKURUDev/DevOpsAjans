import { useEffect, useState } from 'react';
import { ExternalLink, Map as HaritaIkonu, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { RIZA_OLAYI, rizayiOku } from '@/lib/riza';

/**
 * İletişim sayfasındaki Google Haritalar gömmesi — rızaya bağlı (Faz 4G).
 *
 * Gömülü harita Google'dan yükleniyor ve Google o çerçevede kendi çerezlerini
 * kullanabiliyor. Bu yüzden ziyaretçi çerez bandında "Kabul et" demediyse
 * çerçeve HİÇ yüklenmiyor; yerine adres, "Haritayı göster" düğmesi ve
 * "Google Haritalar'da aç" bağlantısı (yeni sekme) çiziliyor. Düğmeye
 * basılınca (yalnız bu sayfa görüntülemesi için) ya da rıza verilince harita
 * yükleniyor. Yer tutucu haritayla aynı yükseklikte: geçişte sayfa kaymıyor.
 *
 * Prerender'da (sunucuda) rıza okunamıyor → her zaman yer tutucu basılıyor;
 * yani arama motorunun gördüğü HTML'de de Google çerçevesi yok.
 */

const GOMME =
  'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3008.5!2d28.98!3d41.08!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2zNDHCsDA0JzQ4LjAiTiAyOMKwNTgnNDguMCJF!5e0!3m2!1str!2str!4v1';

export default function IletisimHaritasi({ adres }: { adres: string }) {
  const { t } = useTranslation();
  const [riza, setRiza] = useState(() => rizayiOku() === 'kabul');
  const [acildi, setAcildi] = useState(false);

  useEffect(() => {
    const tazele = () => setRiza(rizayiOku() === 'kabul');
    window.addEventListener(RIZA_OLAYI, tazele);
    return () => window.removeEventListener(RIZA_OLAYI, tazele);
  }, []);

  const goster = riza || acildi;
  const disBaglanti = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(adres || 'Kağıthane, İstanbul')}`;

  return (
    <div className="cam-kart overflow-hidden rounded-3xl border border-white/10 glass" data-harita={goster ? 'acik' : 'kapali'}>
      {goster ? (
        <iframe
          title={t('iletisimHarita.cerceveBaslik')}
          src={GOMME}
          width="100%"
          height="400"
          style={{ border: 0 }}
          allowFullScreen
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          className="block h-[400px] w-full"
          data-testid="iletisim-harita-cerceve"
        />
      ) : (
        <div
          className="relative flex h-[400px] flex-col items-center justify-center gap-5 px-6 text-center"
          data-testid="iletisim-harita-yer-tutucu"
        >
          {/* Harita izlenimi veren hafif ızgara (dış kaynak yok). */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-[0.07]"
            style={{
              backgroundImage:
                'linear-gradient(currentColor 1px, transparent 1px), linear-gradient(90deg, currentColor 1px, transparent 1px)',
              backgroundSize: '40px 40px',
            }}
          />
          <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-purple-500">
            <MapPin className="h-6 w-6 text-white" aria-hidden="true" />
          </div>
          <div className="relative max-w-md space-y-2">
            <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">{t('iletisimHarita.baslik')}</p>
            {adres && <p className="text-lg font-semibold" data-testid="iletisim-harita-adres">{adres}</p>}
            <p className="text-xs leading-relaxed text-muted-foreground">{t('iletisimHarita.not')}</p>
          </div>
          <div className="relative flex w-full max-w-md flex-col gap-2 sm:flex-row sm:justify-center">
            <Button
              type="button"
              onClick={() => setAcildi(true)}
              className="h-11 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
              data-testid="iletisim-harita-goster"
            >
              <HaritaIkonu className="h-4 w-4" aria-hidden="true" />
              {t('iletisimHarita.goster')}
            </Button>
            <Button asChild variant="outline" className="h-11 gap-2 border-white/20 !bg-transparent">
              <a href={disBaglanti} target="_blank" rel="noopener noreferrer" data-testid="iletisim-harita-dis">
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
                {t('iletisimHarita.disAc')}
              </a>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
