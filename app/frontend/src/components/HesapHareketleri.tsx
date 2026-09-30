import { useCallback, useEffect, useState } from 'react';
import { History, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { goreliZaman, hesapHareketlerim, islemRengi, tamZaman, type HareketSatiri } from '@/lib/denetim';

/**
 * Müşteri paneli › Profil › Hesap hareketleri.
 *
 * Müşterinin kendi yaptığı işler ile kendi kayıtlarına (proje, fatura,
 * destek talebi, ödeme, site) yapılan son 50 işlem. Alan bazında fark
 * gösterilmiyor; başkası yaptıysa kişinin adı değil yalnız "Ekibimiz" /
 * "Sistem" yazıyor. Liste sunucuda jetondaki e-postaya göre süzülüyor.
 */

/** Sunucu özeti "etiket · alan1, alan2" biçiminde; müşteriye yalnız etiket. */
function etiket(ozet: string | null | undefined): string {
  return (ozet || '').split(' · ')[0].trim();
}

export default function HesapHareketleri() {
  const { t, i18n } = useTranslation();
  const [satirlar, setSatirlar] = useState<HareketSatiri[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      setSatirlar(await hesapHareketlerim());
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kim = (s: HareketSatiri) => {
    if (s.kendisi) return t('denetim.hareket.siz');
    if (s.aktor_rol === 'admin') return t('denetim.hareket.ekip');
    if (s.aktor_rol === 'anonim') return t('denetim.hareket.ziyaretci');
    return t('denetim.hareket.sistem');
  };

  return (
    <section
      className="cam-kart max-w-xl rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      aria-labelledby="hesap-hareketleri-baslik"
      data-testid="hesap-hareketleri"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 id="hesap-hareketleri-baslik" className="flex items-center gap-2 text-lg font-semibold">
            <History className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('denetim.hareket.baslik')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('denetim.hareket.aciklama')}</p>
        </div>
        <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('denetim.yenile')}>
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
        </Button>
      </div>

      {yukleniyor && satirlar.length === 0 ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : hata ? (
        <p className="py-4 text-sm text-red-300">{t('denetim.hareket.hata')}</p>
      ) : satirlar.length === 0 ? (
        <p className="py-4 text-sm text-muted-foreground">{t('denetim.hareket.bos')}</p>
      ) : (
        <ol className="space-y-2">
          {satirlar.map((s) => {
            const ad = etiket(s.ozet);
            return (
              <li key={s.id} className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3">
                <span
                  className={`mt-0.5 inline-block shrink-0 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${islemRengi(s.islem)}`}
                >
                  {t(`denetim.islem.${s.islem}`, { defaultValue: s.islem })}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">
                    {t(`denetim.tablo.${s.tablo}`, { defaultValue: s.tablo })}
                    {s.kayit_id && s.tablo !== 'users' ? <span className="text-muted-foreground"> #{s.kayit_id}</span> : null}
                  </p>
                  {ad && s.tablo !== 'users' && <p className="truncate text-xs text-muted-foreground">{ad}</p>}
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    <span title={tamZaman(s.created_at, i18n.language)}>{goreliZaman(s.created_at, i18n.language)}</span>
                    {' · '}
                    {kim(s)}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
