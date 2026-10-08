import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ChevronLeft, ChevronRight, Save } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DIS_DUGME, GIRDI, HataSatiri, KART, Not, Rozet, SECIM, Yukleniyor } from '@/components/onMuhasebe/ortak';
import { ayEkle, ayYaz, bugun, hataMetni, kategoriAdi, kurusMetni, para, type BolumProps, type ButceDurumu, type ButceKalemi } from '@/lib/onMuhasebe';

const DURUM_RENGI: Record<ButceKalemi['durum'], string> = {
  normal: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  yaklasti: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  asildi: 'border-rose-400/40 bg-rose-500/15 text-rose-200',
  butcesiz: 'border-white/10 bg-white/[0.05] text-muted-foreground',
};
const CUBUK: Record<ButceKalemi['durum'], string> = { normal: 'bg-emerald-400', yaklasti: 'bg-amber-400', asildi: 'bg-rose-500', butcesiz: 'bg-white/30' };

interface Satir extends Omit<ButceKalemi, 'durum'> {
  durum: ButceKalemi['durum'];
}

/** Faz 6M — bütçe: gider kategorisi başına aylık bütçe (her ay ya da yalnız bu ay), gerçekleşen/bütçe, aşım uyarısı. */
export default function Butce({ api, meta, surum }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const [ay, setAy] = useState(bugun().slice(0, 7));
  const [d, setD] = useState<ButceDurumu | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [girdi, setGirdi] = useState<Record<string, { tutar: string; kapsam: 'her_ay' | 'ay' }>>({});
  const [kaydedilen, setKaydedilen] = useState<string | null>(null);
  const pb = meta.ayarlar.para_birimi || 'TRY';

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const r = await api.butceler(ay);
      setD(r);
      const g: Record<string, { tutar: string; kapsam: 'her_ay' | 'ay' }> = {};
      for (const x of r.kalemler) g[`${x.kategori_id}|${x.para_birimi}`] = { tutar: x.butce !== null ? kurusMetni(x.butce) : '', kapsam: x.butce_kaynak === 'ay' ? 'ay' : 'her_ay' };
      setGirdi(g);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, ay, t]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum]);

  const satirlar = useMemo<Satir[]>(() => {
    if (!d) return [];
    const var_ = new Set(d.kalemler.map((x) => `${x.kategori_id}|${x.para_birimi}`));
    const ek: Satir[] = meta.kategoriler
      .filter((k) => k.tur === 'gider' && !k.arsiv && !var_.has(`${k.id}|${pb}`))
      .map((k) => ({
        kategori_id: k.id, ad: k.ad, anahtar: k.anahtar, ad_degisti: k.ad_degisti, renk: k.renk, para_birimi: pb, butce: null, butce_id: null,
        butce_kaynak: null, gerceklesen: 0, oran: null, kalan: null, durum: 'butcesiz', uyari_at: null,
      }));
    return [...d.kalemler, ...ek];
  }, [d, meta.kategoriler, pb]);

  const kaydet = async (x: Satir) => {
    const anahtar = `${x.kategori_id}|${x.para_birimi}`;
    const g = girdi[anahtar] || { tutar: '', kapsam: 'her_ay' };
    setHata(null);
    try {
      // Kapsam "her ay"dan "bu ay"a geçtiyse eski satır kalır (her ay); bu ayın satırı onu ezer.
      await api.butceYaz({ kategori_id: x.kategori_id, ay: g.kapsam === 'ay' ? ay : '*', tutar: g.tutar.trim() || null, para_birimi: x.para_birimi });
      setKaydedilen(anahtar);
      window.setTimeout(() => setKaydedilen(null), 1500);
      void yukle();
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-3" data-testid="mh-butce">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setAy((a) => ayEkle(a, -1))} aria-label={t('onMuhasebe.ortak.oncekiAy')}>
          <ChevronLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
        <span className="min-w-[8rem] text-center font-semibold" data-testid="mh-butce-ay">
          {ayYaz(ay, dil, 'long')}
        </span>
        <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setAy((a) => ayEkle(a, 1))} aria-label={t('onMuhasebe.ortak.sonrakiAy')}>
          <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">{t('onMuhasebe.butce.aciklama', { yuzde: meta.ayarlar.uyari_yuzde })}</p>
      {d && d.asim_sayisi > 0 && (
        <p className="flex items-start gap-2 rounded-xl border border-rose-400/40 bg-rose-500/10 p-3 text-sm text-rose-100" role="alert" data-testid="mh-butce-asim">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          {t('onMuhasebe.butce.asimUyari', { sayi: d.asim_sayisi })}
        </p>
      )}
      <HataSatiri hata={hata} />
      {!d ? (
        <Yukleniyor />
      ) : (
        <>
          {d.toplamlar.length > 0 && (
            <div className="flex flex-wrap gap-2 text-sm">
              {d.toplamlar.map((x) => (
                <span key={x.para_birimi} className={`${KART} px-3 py-2`}>
                  {t('onMuhasebe.butce.toplam')}: <b>{para(x.gerceklesen, x.para_birimi, dil)}</b> / {para(x.butce, x.para_birimi, dil)}
                </span>
              ))}
            </div>
          )}
          <ul className="space-y-2" data-testid="mh-butce-liste">
            {satirlar.map((x) => {
              const anahtar = `${x.kategori_id}|${x.para_birimi}`;
              const g = girdi[anahtar] || { tutar: '', kapsam: 'her_ay' as const };
              const oran = Math.min(100, x.oran ?? 0);
              return (
                <li key={anahtar} className={`${KART} p-3`} data-testid="mh-butce-satir" data-durum={x.durum} data-kategori={x.anahtar || x.ad}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ backgroundColor: x.renk || '#9ca3af' }} aria-hidden="true" />
                      <span className="truncate font-medium">{kategoriAdi(t, x)}</span>
                      {x.para_birimi !== pb && <Rozet>{x.para_birimi}</Rozet>}
                    </span>
                    <Rozet renk={DURUM_RENGI[x.durum]} testid="mh-butce-durum">
                      {t(`onMuhasebe.butce.durum.${x.durum}`)}
                      {x.oran !== null ? ` · %${x.oran}` : ''}
                    </Rozet>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={oran}>
                    <div className={`h-full ${CUBUK[x.durum]}`} style={{ width: `${x.butce ? oran : 0}%` }} />
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-muted-foreground">
                      {t('onMuhasebe.butce.gerceklesen')}: <b className="text-white">{para(x.gerceklesen, x.para_birimi, dil)}</b>
                      {x.kalan !== null && (
                        <>
                          {' · '}
                          {t('onMuhasebe.butce.kalan')}: <b className={x.kalan < 0 ? 'text-rose-300' : 'text-white'}>{para(x.kalan, x.para_birimi, dil)}</b>
                        </>
                      )}
                    </span>
                    {!salt && (
                      <span className="ms-auto flex flex-wrap items-center gap-1.5">
                        <input
                          className={`${GIRDI} w-28`}
                          inputMode="decimal"
                          placeholder={t('onMuhasebe.butce.butce')}
                          aria-label={t('onMuhasebe.butce.butce')}
                          value={g.tutar}
                          onChange={(e) => setGirdi((s) => ({ ...s, [anahtar]: { ...g, tutar: e.target.value } }))}
                          data-testid="mh-butce-tutar"
                        />
                        <select
                          className={`${SECIM} w-32`}
                          aria-label={t('onMuhasebe.butce.kapsam')}
                          value={g.kapsam}
                          onChange={(e) => setGirdi((s) => ({ ...s, [anahtar]: { ...g, kapsam: e.target.value as 'her_ay' | 'ay' } }))}
                        >
                          <option value="her_ay">{t('onMuhasebe.butce.herAy')}</option>
                          <option value="ay">{t('onMuhasebe.butce.buAy')}</option>
                        </select>
                        <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => void kaydet(x)} data-testid="mh-butce-kaydet">
                          <Save className="h-4 w-4" aria-hidden="true" />
                          {kaydedilen === anahtar ? t('onMuhasebe.ortak.kaydedildi') : t('onMuhasebe.ortak.kaydet')}
                        </Button>
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          <Not>{t('onMuhasebe.butce.not')}</Not>
        </>
      )}
    </div>
  );
}
