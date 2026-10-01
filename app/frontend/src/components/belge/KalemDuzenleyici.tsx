import { useEffect, useRef, useState } from 'react';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BelgeHatasi, bosKalem, kalemHesapla, paraBicimle, sayiBicimle, type BelgeOzeti, type Kalem } from '@/lib/belge';

/**
 * Kalem düzenleyici (yönetici): açıklama, adet, birim fiyat, KDV %, indirim %.
 *
 * Toplamları ÖN YÜZ HESAPLAMIYOR: her değişiklikten 350 ms sonra sunucunun
 * önizleme ucu (`/hesapla`, Decimal + kuruş yuvarlama) çağrılıyor; kayıtta da
 * toplam yine sunucuda hesaplanıyor. Böylece ekrandaki toplam ile PDF'teki
 * toplam hiçbir zaman ayrışmıyor.
 */
const KDV_SECENEKLERI = [0, 1, 10, 20];
/** Geniş ekranda tek satırlık kolon düzeni. Satır içi stil: ortak Tailwind CSS'i büyütmüyor. */
const GENIS_KOLONLAR = 'minmax(0,1fr) 5rem 7rem 5.5rem 5rem 2.5rem';
const GENIS_SORGU = '(min-width: 768px)';

function useGenisEkran(): boolean {
  const [genis, setGenis] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.(GENIS_SORGU).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(GENIS_SORGU);
    if (!mq) return;
    const dinle = () => setGenis(mq.matches);
    dinle();
    mq.addEventListener?.('change', dinle);
    return () => mq.removeEventListener?.('change', dinle);
  }, []);
  return genis;
}

export default function KalemDuzenleyici({
  kalemler,
  onChange,
  paraBirimi,
  hesapUrl,
}: {
  kalemler: Kalem[];
  onChange: (k: Kalem[]) => void;
  paraBirimi: string;
  hesapUrl: string;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [ozet, setOzet] = useState<BelgeOzeti | null>(null);
  const [hata, setHata] = useState<{ kod: string; sira?: number } | null>(null);
  const [hesapliyor, setHesapliyor] = useState(false);
  const sayac = useRef(0);
  const genis = useGenisEkran();

  useEffect(() => {
    const dolu = kalemler.filter((k) => (k.aciklama || '').trim() && k.birim_fiyat !== '');
    if (!dolu.length) {
      setOzet(null);
      setHata(null);
      return;
    }
    const no = ++sayac.current;
    const zaman = window.setTimeout(() => {
      setHesapliyor(true);
      kalemHesapla(hesapUrl, dolu)
        .then((s) => {
          if (no !== sayac.current) return;
          setOzet(s);
          setHata(null);
        })
        .catch((h) => {
          if (no !== sayac.current) return;
          setOzet(null);
          setHata(h instanceof BelgeHatasi ? { kod: h.kod, sira: h.ek.sira as number | undefined } : { kod: 'genel' });
        })
        .finally(() => {
          if (no === sayac.current) setHesapliyor(false);
        });
    }, 350);
    return () => window.clearTimeout(zaman);
  }, [kalemler, hesapUrl]);

  const degistir = (i: number, alan: keyof Kalem, deger: string) => {
    onChange(kalemler.map((k, j) => (j === i ? { ...k, [alan]: deger } : k)));
  };

  return (
    <div className="space-y-3" data-testid="kalem-duzenleyici">
      <div className={genis ? 'grid gap-2 px-1 text-xs text-muted-foreground' : 'hidden'} style={{ gridTemplateColumns: GENIS_KOLONLAR }}>
        <span>{t('teklif.kalem.aciklama')}</span>
        <span>{t('teklif.kalem.adet')}</span>
        <span>{t('teklif.kalem.birimFiyat')}</span>
        <span>{t('teklif.kalem.kdv')}</span>
        <span>{t('teklif.kalem.indirim')}</span>
        <span />
      </div>
      {kalemler.map((k, i) => (
        <div
          key={i}
          className={`grid gap-2 rounded-xl ${genis ? 'border-0 p-0' : 'grid-cols-2 border p-2'} ${
            hata?.sira === i ? 'border-red-400/40' : 'border-white/10'
          }`}
          style={genis ? { gridTemplateColumns: GENIS_KOLONLAR } : undefined}
          data-testid={`kalem-satir-${i}`}
        >
          <Input
            className={genis ? '' : 'col-span-2'}
            value={k.aciklama}
            maxLength={500}
            placeholder={t('teklif.kalem.aciklama')}
            aria-label={t('teklif.kalem.aciklama')}
            name={`kalem-aciklama-${i}`}
            onChange={(e) => degistir(i, 'aciklama', e.target.value)}
          />
          <Input
            type="number"
            min={0}
            step="any"
            inputMode="decimal"
            value={k.adet}
            aria-label={t('teklif.kalem.adet')}
            name={`kalem-adet-${i}`}
            onChange={(e) => degistir(i, 'adet', e.target.value)}
          />
          <Input
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            value={k.birim_fiyat}
            aria-label={t('teklif.kalem.birimFiyat')}
            name={`kalem-fiyat-${i}`}
            onChange={(e) => degistir(i, 'birim_fiyat', e.target.value)}
          />
          <select
            value={String(k.kdv_orani)}
            aria-label={t('teklif.kalem.kdv')}
            name={`kalem-kdv-${i}`}
            onChange={(e) => degistir(i, 'kdv_orani', e.target.value)}
            className="h-10 rounded-md border border-white/10 bg-white/5 px-2 text-sm"
          >
            {[...new Set([...KDV_SECENEKLERI, Number(k.kdv_orani) || 0])].map((o) => (
              <option key={o} value={o} className="bg-[#150a2b]">
                %{o}
              </option>
            ))}
          </select>
          <Input
            type="number"
            min={0}
            max={100}
            step="any"
            inputMode="decimal"
            value={k.indirim}
            aria-label={t('teklif.kalem.indirim')}
            name={`kalem-indirim-${i}`}
            onChange={(e) => degistir(i, 'indirim', e.target.value)}
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-10 text-destructive hover:text-destructive"
            onClick={() => onChange(kalemler.filter((_, j) => j !== i))}
            disabled={kalemler.length <= 1}
            aria-label={t('teklif.kalem.sil')}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <Button type="button" variant="outline" size="sm" className="gap-2 !bg-transparent" onClick={() => onChange([...kalemler, bosKalem()])}
          data-testid="kalem-ekle">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('teklif.kalem.ekle')}
        </Button>
        <div className="min-w-[14rem] text-sm" aria-live="polite">
          {hata ? (
            <p className="text-red-300" data-testid="kalem-hata">
              {hata.sira != null ? `${t('teklif.kalem.satir', { sayi: hata.sira + 1 })}: ` : ''}
              {t(`teklif.hata.${hata.kod}`, { defaultValue: t('teklif.hata.genel') })}
            </p>
          ) : ozet ? (
            <dl className="grid gap-0.5" data-testid="kalem-onizleme">
              <div className="flex justify-between gap-4 text-muted-foreground">
                <dt>{t('teklif.kalem.araToplam')}</dt>
                <dd className="tabular-nums">{paraBicimle(ozet.ara_toplam, paraBirimi, dil)}</dd>
              </div>
              {(ozet.kdv_dokumu || []).filter((d) => d.oran).map((d) => (
                <div key={d.oran} className="flex justify-between gap-4 text-muted-foreground">
                  <dt>{t('teklif.kalem.kdvSatiri', { oran: sayiBicimle(d.oran, dil) })}</dt>
                  <dd className="tabular-nums">{paraBicimle(d.kdv, paraBirimi, dil)}</dd>
                </div>
              ))}
              <div className="flex justify-between gap-4 font-semibold">
                <dt>{t('teklif.kalem.genelToplam')}</dt>
                <dd className="tabular-nums" data-testid="onizleme-toplam">{paraBicimle(ozet.genel_toplam, paraBirimi, dil)}</dd>
              </div>
            </dl>
          ) : hesapliyor ? (
            <Loader2 className="ms-auto h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
          ) : null}
          <p className="mt-1 text-xs text-muted-foreground">{t('teklif.kalem.sunucuHesaplar')}</p>
        </div>
      </div>
    </div>
  );
}
