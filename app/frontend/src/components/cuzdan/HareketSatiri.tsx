import { useTranslation } from 'react-i18next';

import { paraBicimle, tarihBicimle } from '@/lib/belge';
import type { CuzdanHareketi } from '@/lib/cuzdan';

/** Defter satırı (yönetici ve müşteri ortak görünümü). */
export default function HareketSatiri({ h, yonetici = false }: { h: CuzdanHareketi; yonetici?: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const arti = h.tutar > 0;
  const ayrinti = [
    h.fatura_no ? t('cuzdan.hareketler.fatura', { no: h.fatura_no }) : null,
    h.yontem && h.yontem !== 'bakiye' ? t(`cuzdan.yontem.${h.yontem}`, { defaultValue: h.yontem }) : null,
    h.gerekce,
    h.notu && h.notu !== h.fatura_no ? h.notu : null,
    yonetici && h.yazan ? `${t('cuzdan.yonetim.yazan')}: ${h.yazan}` : null,
  ].filter(Boolean);
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px]">{t(`cuzdan.tur.${h.tur}`)}</span>
          <span className="text-xs text-muted-foreground">{tarihBicimle(h.tarih, dil)}</span>
          {h.ters_edildi && <span className="text-[11px] text-amber-300">{t('cuzdan.hareketler.tersEdildi')}</span>}
        </p>
        {ayrinti.length > 0 && <p className="mt-0.5 break-words text-xs text-muted-foreground">{ayrinti.join(' · ')}</p>}
      </div>
      <div className="text-end">
        <p className={`font-semibold tabular-nums ${arti ? 'text-emerald-300' : 'text-orange-300'}`} dir="ltr">
          {arti ? '+' : '−'}{paraBicimle(Math.abs(h.tutar), h.para_birimi, dil)}
        </p>
        <p className="text-[11px] text-muted-foreground">{t('cuzdan.hareketler.sonra', { tutar: paraBicimle(h.sonra, h.para_birimi, dil) })}</p>
      </div>
    </div>
  );
}

