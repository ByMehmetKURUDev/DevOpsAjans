import { useEffect, useState } from 'react';
import { History, Loader2, RotateCcw, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, tarihYaz, type BelgeApi, type BelgeAyrintisi, type StratejiSablonu, type Surum } from '@/lib/belgeler';

import StratejiIzgarasi from './StratejiIzgarasi';

/**
 * Faz 5B — sürüm geçmişi: son N sürüm (sunucu saklıyor), seçilen sürümün önizlemesi ve geri
 * yükleme. Geri yükleme geçmişi silmez: seçilen sürümün içeriği YENİ sürüm olarak yazılır.
 */

interface Ozellikler {
  api: BelgeApi;
  belge: BelgeAyrintisi;
  sablon: StratejiSablonu | null;
  onKapat: () => void;
  onGeriYuklendi: (b: BelgeAyrintisi) => void;
}

function aciklamaMetni(t: (k: string, o?: Record<string, unknown>) => string, aciklama: string | null): string {
  if (!aciklama) return '';
  const [tur, deger] = aciklama.split(':');
  return t(`belgeler.surum.neden.${tur}`, { sayi: deger ?? '', defaultValue: aciklama });
}

export default function SurumGecmisi({ api, belge, sablon, onKapat, onGeriYuklendi }: Ozellikler) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<Surum[] | null>(null);
  const [secili, setSecili] = useState<Surum | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);

  useEffect(() => {
    let iptal = false;
    api
      .surumler(belge.id)
      .then((y) => {
        if (!iptal) setListe(y.items);
      })
      .catch((e) => {
        if (!iptal) {
          toast.error(hataMetni(t, e));
          setListe([]);
        }
      });
    return () => {
      iptal = true;
    };
  }, [api, belge.id, belge.surum, t]);

  useEffect(() => {
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onKapat();
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, [onKapat]);

  const sec = async (s: Surum) => {
    try {
      setSecili(await api.surum(belge.id, s.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const geriYukle = async () => {
    if (!secili || !window.confirm(t('belgeler.surum.geriYukleOnay', { sayi: secili.surum }))) return;
    setCalisiyor(true);
    try {
      const b = await api.geriYukle(belge.id, secili.id);
      toast.success(t('belgeler.surum.geriYuklendi', { sayi: secili.surum }));
      onGeriYuklendi(b);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="surum-baslik" data-testid="surum-gecmisi">
      <div className="surum-pencere flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-t-2xl border border-white/10 sm:rounded-2xl">
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
          <h3 id="surum-baslik" className="flex items-center gap-2 font-semibold">
            <History className="h-4 w-4 text-purple-300" aria-hidden="true" />
            {t('belgeler.surum.baslik')}
          </h3>
          <Button size="sm" variant="ghost" className="px-2" onClick={onKapat} aria-label={t('belgeler.surum.kapat')}>
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
        <div className="surum-duzen min-h-0 flex-1">
          <div className="surum-liste overflow-y-auto border-white/10">
            {liste === null ? (
              <div className="flex justify-center py-8 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
              </div>
            ) : (
              <ul>
                {liste.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => void sec(s)}
                      className={`w-full px-4 py-2.5 text-left text-sm hover:bg-white/5 ${secili?.id === s.id ? 'bg-purple-500/15' : ''}`}
                      data-testid={`surum-${s.surum}`}
                    >
                      <span className="font-medium">
                        {t('belgeler.rozet.surum', { sayi: s.surum })}
                        {s.surum === belge.surum && <span className="ml-2 text-xs text-emerald-300">{t('belgeler.surum.guncel')}</span>}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {tarihYaz(s.created_at, i18n.language)} · {s.duzenleyen || '—'}
                      </span>
                      <span className="block text-xs text-muted-foreground/80">{aciklamaMetni(t, s.aciklama)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="px-4 py-2 text-[11px] text-muted-foreground">{t('belgeler.surum.aciklama', { sayi: liste?.length ?? 0 })}</p>
          </div>
          <div className="min-h-0 overflow-y-auto p-4">
            {!secili ? (
              <p className="text-sm text-muted-foreground">{t('belgeler.surum.secin')}</p>
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{t('belgeler.surum.onizleme', { sayi: secili.surum })} — {secili.baslik}</p>
                  {secili.surum !== belge.surum && (
                    <Button size="sm" className="gap-1" onClick={() => void geriYukle()} disabled={calisiyor} data-testid="surum-geri-yukle">
                      {calisiyor ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />}
                      {t('belgeler.surum.geriYukle')}
                    </Button>
                  )}
                </div>
                {secili.strateji_icerik && sablon ? (
                  <StratejiIzgarasi sablon={sablon} icerik={secili.strateji_icerik} />
                ) : (
                  <div
                    className="belge-icerik prose prose-invert max-w-none break-words"
                    // Sunucu temizledi (services/guvenli_html.belge_html).
                    dangerouslySetInnerHTML={{ __html: secili.html || '<p>—</p>' }}
                    data-testid="surum-onizleme"
                  />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
