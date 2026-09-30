import { useEffect, useState } from 'react';
import { ChevronRight, Coins } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { kalanGun, kredilerimiGetir, saatBicimle, sonKullanmaRengi, tarihBicimle, type Kredilerim } from '@/lib/kredi';

/**
 * Müşteri paneli genel görünümündeki küçük "Kredi bakiyesi" kartı.
 *
 * Yalnız defterinde hareketi olan (Kullandıkça Öde kullanan) müşteride
 * görünüyor; diğerlerinde hiçbir şey çizmiyor. Tıklanınca Kredilerim
 * sekmesine geçiyor.
 */
export default function KrediOzetKarti({ onAc }: { onAc: () => void }) {
  const { t, i18n } = useTranslation();
  const [veri, setVeri] = useState<Kredilerim | null>(null);

  useEffect(() => {
    let iptal = false;
    kredilerimiGetir()
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, []);

  if (!veri || veri.hareketler.length === 0) return null;

  const ilk = veri.yaklasan_son_kullanma[0];
  const gun = kalanGun(ilk?.tarih);

  return (
    <button
      type="button"
      onClick={onAc}
      className="cam-kart mb-10 flex w-full flex-wrap items-center gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-left transition-colors hover:border-emerald-400/40"
      data-testid="kredi-ozet-karti"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-cyan-500">
        <Coins className="h-5 w-5 text-white" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs uppercase tracking-widest text-muted-foreground">
          {t('kredi.musteri.kartBaslik')}
        </span>
        <span className={`block text-2xl font-bold ${veri.bakiye < 0 ? 'text-red-300' : ''}`}>
          {t('kredi.saatKisa', { deger: saatBicimle(veri.bakiye, i18n.language) })}
        </span>
      </span>
      {ilk && (
        <span className={`text-xs ${sonKullanmaRengi(gun)}`}>
          {t('kredi.musteri.kartSonKullanma', {
            saat: saatBicimle(ilk.miktar, i18n.language),
            tarih: tarihBicimle(ilk.tarih, i18n.language),
          })}
        </span>
      )}
      <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
    </button>
  );
}
