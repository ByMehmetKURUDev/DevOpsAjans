import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw, RotateCcw, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { copHataMetni, silineniGeriAl, silinenlerim, type CopSatiri } from '@/lib/copKutusu';
import { goreliZaman, tamZaman } from '@/lib/denetim';

/**
 * Müşteri paneli › Profil › Silinenler.
 *
 * Müşterinin kendi sildiği, kendisine ait kayıtlar saklama süresi boyunca
 * burada; "Geri al" kaydı aynı numarasıyla yerine koyar. Kalıcı silme yok
 * (süre dolunca sistem siliyor). Liste sunucuda jetondaki e-postaya göre.
 */
export default function Silinenlerim() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [satirlar, setSatirlar] = useState<CopSatiri[]>([]);
  const [gun, setGun] = useState(30);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [calisan, setCalisan] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      const g = await silinenlerim();
      setSatirlar(g.items);
      setGun(g.saklama_gun);
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const geriAl = async (s: CopSatiri) => {
    setCalisan(s.id);
    try {
      await silineniGeriAl(s.id);
      toast.success(t('copKutusu.geriAlindi'));
      await yukle();
    } catch (h) {
      toast.error(copHataMetni(t, h));
    } finally {
      setCalisan(null);
    }
  };

  return (
    <section
      className="cam-kart max-w-xl rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      aria-labelledby="silinenlerim-baslik"
      data-testid="silinenlerim"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 id="silinenlerim-baslik" className="flex items-center gap-2 text-lg font-semibold">
            <Trash2 className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('copKutusu.kisi.baslik')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('copKutusu.kisi.aciklama', { gun })}</p>
        </div>
        <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('copKutusu.yenile')}>
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
        </Button>
      </div>

      {yukleniyor && satirlar.length === 0 ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : hata ? (
        <p className="py-4 text-sm text-red-300">{t('copKutusu.hata')}</p>
      ) : satirlar.length === 0 ? (
        <p className="py-2 text-sm text-muted-foreground">{t('copKutusu.kisi.bos')}</p>
      ) : (
        <ul className="space-y-2">
          {satirlar.map((s) => (
            <li
              key={s.id}
              className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3"
              data-testid={`silinen-${s.id}`}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm">
                  {t(`copKutusu.tablo.${s.tablo}`, { defaultValue: s.tablo })}
                  {s.etiket ? <span className="text-muted-foreground"> · {s.etiket}</span> : null}
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  <span title={tamZaman(s.silinme, dil)}>{goreliZaman(s.silinme, dil)}</span>
                  {s.kalici_silinme && (
                    <>
                      {' · '}
                      {t('copKutusu.kaliciSilinme', { zaman: tamZaman(s.kalici_silinme, dil) })}
                    </>
                  )}
                </p>
              </div>
              <Button size="sm" variant="outline" disabled={calisan !== null} onClick={() => void geriAl(s)}>
                {calisan === s.id ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                )}
                {t('copKutusu.geriAl')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
