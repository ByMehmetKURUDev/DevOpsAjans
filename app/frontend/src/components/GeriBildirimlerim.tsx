import { useCallback, useEffect, useState } from 'react';
import { Bug, Image as ImageIcon, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { geriBildirimlerim, tarihGoster, type GeriBildirim, type GeriBildirimDurumu } from '@/lib/projeYonetimi';

const DURUM_RENGI: Record<GeriBildirimDurumu, string> = {
  yeni: 'bg-white/10 text-foreground/80',
  inceleniyor: 'bg-amber-500/15 text-amber-200',
  gorev: 'bg-sky-500/15 text-sky-200',
  cozuldu: 'bg-emerald-500/15 text-emerald-200',
  kapatildi: 'bg-white/5 text-muted-foreground',
};

/**
 * Müşteri › Destek › "Hata ve geri bildirimlerim" (Faz 2B): gönderdiği
 * bildirimler ve güncel durumları. `yenile` değiştikçe yeniden yüklenir
 * (yeni bildirim gönderilince panel artırıyor).
 */
export default function GeriBildirimlerim({ yenile = 0 }: { yenile?: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<GeriBildirim[] | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe(await geriBildirimlerim());
    } catch {
      setListe([]);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle, yenile]);

  return (
    <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-testid="geri-bildirimlerim" aria-labelledby="gb-benim-baslik">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 id="gb-benim-baslik" className="flex items-center gap-2 text-lg font-semibold">
          <Bug className="h-5 w-5 text-rose-300" aria-hidden="true" /> {t('geriBildirim.benim.baslik')}
        </h3>
        <button type="button" onClick={() => void yukle()} aria-label={t('geriBildirim.yenile')} className="rounded-md p-1 hover:bg-white/10">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      {liste === null ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      ) : liste.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('geriBildirim.benim.bos')}</p>
      ) : (
        <ul className="space-y-2">
          {liste.map((fb) => (
            <li key={fb.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-sm" data-testid={`gb-benim-${fb.id}`}>
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="rounded-full bg-white/10 px-2 py-0.5">{t(`geriBildirim.tur.${fb.tur}`)}</span>
                <span className={`rounded-full px-2 py-0.5 ${DURUM_RENGI[fb.durum]}`} data-testid={`gb-durum-${fb.id}`} data-durum={fb.durum}>
                  {t(`geriBildirim.durum.${fb.durum}`)}
                </span>
                <span className="text-muted-foreground">{tarihGoster(fb.created_at, dil)}</span>
                {fb.proje_basligi && <span className="min-w-0 truncate text-muted-foreground">· {fb.proje_basligi}</span>}
                {fb.ekler.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-muted-foreground">
                    <ImageIcon className="h-3 w-3" aria-hidden="true" /> {t('geriBildirim.benim.ekler', { sayi: fb.ekler.length })}
                  </span>
                )}
              </div>
              <p className="mt-1 break-words font-medium">{fb.baslik}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
