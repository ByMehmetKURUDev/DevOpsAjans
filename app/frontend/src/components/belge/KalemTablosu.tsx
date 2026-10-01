import { useTranslation } from 'react-i18next';

import { paraBicimle, sayiBicimle, type BelgeOzeti, type Kalem } from '@/lib/belge';

/**
 * Kalemler + toplamlar + KDV dökümü (salt okunur). Teklif sayfası, müşteri
 * paneli ve yönetici ayrıntısı aynı tabloyu çiziyor. Toplamlar SUNUCUNUN
 * hesapladığı değerler (`ozet`); burada hesap yapılmıyor.
 * Metinler `teklif` ek paketinde (`teklif.kalem.*`).
 */
export default function KalemTablosu({
  kalemler,
  ozet,
  paraBirimi,
  ekSatirlar = [],
}: {
  kalemler: Kalem[];
  ozet: BelgeOzeti | null;
  paraBirimi: string;
  /** Toplamların altına ek satırlar (ödenen, kalan…): [etiket, değer, vurgulu] */
  ekSatirlar?: [string, string, boolean?][];
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const para = (d: number | null | undefined) => paraBicimle(d, paraBirimi, dil);

  return (
    <div className="space-y-4" data-testid="kalem-tablosu">
      {/* Masaüstü tablo */}
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 pe-2 text-start font-medium">{t('teklif.kalem.aciklama')}</th>
              <th className="px-2 py-2 text-end font-medium">{t('teklif.kalem.adet')}</th>
              <th className="px-2 py-2 text-end font-medium">{t('teklif.kalem.birimFiyat')}</th>
              <th className="px-2 py-2 text-end font-medium">{t('teklif.kalem.indirim')}</th>
              <th className="px-2 py-2 text-end font-medium">{t('teklif.kalem.kdv')}</th>
              <th className="py-2 ps-3 text-end font-medium">{t('teklif.kalem.tutar')}</th>
            </tr>
          </thead>
          <tbody>
            {kalemler.map((k, i) => (
              <tr key={i} className="border-b border-white/5 align-top">
                <td className="py-2 pe-2 break-words">{k.aciklama}</td>
                <td className="px-2 py-2 text-end tabular-nums">{sayiBicimle(k.adet, dil)}</td>
                <td className="px-2 py-2 text-end tabular-nums">{para(Number(k.birim_fiyat))}</td>
                <td className="px-2 py-2 text-end tabular-nums">{Number(k.indirim) ? `%${sayiBicimle(k.indirim, dil)}` : '—'}</td>
                <td className="px-2 py-2 text-end tabular-nums">%{sayiBicimle(k.kdv_orani, dil)}</td>
                <td className="py-2 ps-3 text-end tabular-nums">{para(k.matrah ?? null)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Mobil kartlar */}
      <ul className="space-y-2 sm:hidden">
        {kalemler.map((k, i) => (
          <li key={i} className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-sm">
            <p className="break-words font-medium">{k.aciklama}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {sayiBicimle(k.adet, dil)} × {para(Number(k.birim_fiyat))}
              {Number(k.indirim) ? ` · −%${sayiBicimle(k.indirim, dil)}` : ''} · {t('teklif.kalem.kdv')} %{sayiBicimle(k.kdv_orani, dil)}
            </p>
            <p className="mt-1 text-end font-semibold tabular-nums">{para(k.matrah ?? null)}</p>
          </li>
        ))}
      </ul>

      {ozet && (
        <dl className="ms-auto grid max-w-md gap-1 text-sm" data-testid="belge-toplamlari">
          {!!ozet.indirim_toplam && (
            <div className="flex justify-between gap-4 text-muted-foreground">
              <dt>{t('teklif.kalem.indirimToplam')}</dt>
              <dd className="tabular-nums">−{para(ozet.indirim_toplam)}</dd>
            </div>
          )}
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{t('teklif.kalem.araToplam')}</dt>
            <dd className="tabular-nums">{para(ozet.ara_toplam)}</dd>
          </div>
          {(ozet.kdv_dokumu || [])
            .filter((d) => d.oran || d.kdv)
            .map((d) => (
              <div key={d.oran} className="flex justify-between gap-4">
                <dt className="text-muted-foreground">{t('teklif.kalem.kdvSatiri', { oran: sayiBicimle(d.oran, dil) })}</dt>
                <dd className="tabular-nums">{para(d.kdv)}</dd>
              </div>
            ))}
          <div className="mt-1 flex justify-between gap-4 border-t border-white/10 pt-2 text-base font-bold">
            <dt>{t('teklif.kalem.genelToplam')}</dt>
            <dd className="tabular-nums" data-testid="genel-toplam">
              {para(ozet.genel_toplam)}
            </dd>
          </div>
          {ekSatirlar.map(([ad, deger, vurgu]) => (
            <div key={ad} className={`flex justify-between gap-4 ${vurgu ? 'font-semibold' : 'text-muted-foreground'}`}>
              <dt>{ad}</dt>
              <dd className="tabular-nums">{deger}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
