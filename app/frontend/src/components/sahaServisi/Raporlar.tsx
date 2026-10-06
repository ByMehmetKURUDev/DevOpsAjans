import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock, CheckCircle2, Gauge, Loader2, Star, Timer, Wrench } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { bugunIso, gunEkle, hataMetni, type BakimSatiri, type Rapor, type SahaApi } from '@/lib/sahaServisi';
import { Bos, GIRDI, KART, Rozet, Yukleniyor } from './ortak';

/**
 * Faz 6S — raporlar: teknisyen başına tamamlanan iş, ortalama süre, ilk seferde çözüm oranı,
 * memnuniyet ortalaması; açık iş sayıları; bakım zamanı gelen cihazlar → "bakım iş emri oluştur".
 */
export default function Raporlar({ api, onAc, saltOkunur }: { api: SahaApi; onAc: (id: number) => void; saltOkunur: boolean }) {
  const { t, i18n } = useTranslation();
  const [bas, setBas] = useState(() => gunEkle(bugunIso(), -29));
  const [bit, setBit] = useState(bugunIso);
  const [rapor, setRapor] = useState<Rapor | null>(null);
  const [bakim, setBakim] = useState<BakimSatiri[] | null>(null);
  const [mesgul, setMesgul] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [r, b] = await Promise.all([api.raporlar(bas, bit), api.bakim(30)]);
      setRapor(r);
      setBakim(b.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, bas, bit, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const yuzde = (x: number | null) => (x == null ? '—' : new Intl.NumberFormat(i18n.language, { style: 'percent', maximumFractionDigits: 0 }).format(x));
  const sayi = (x: number | null, ek = '') => (x == null ? '—' : `${new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 2 }).format(x)}${ek}`);

  const bakimIsi = async (c: BakimSatiri) => {
    setMesgul(c.cihaz_id);
    try {
      const d = await api.bakimIsEmri(c.cihaz_id);
      toast.success(t('sahaServisi.isler.olusturuldu', { no: d.no }));
      onAc(d.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="saha-raporlar">
      <div className={`${KART} flex flex-wrap items-end gap-2 p-3`}>
        <label className="text-sm">
          <span className="mb-1 block text-muted-foreground">{t('sahaServisi.rapor.bas')}</span>
          <input type="date" className={GIRDI} value={bas} onChange={(e) => setBas(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted-foreground">{t('sahaServisi.rapor.bit')}</span>
          <input type="date" className={GIRDI} value={bit} onChange={(e) => setBit(e.target.value)} />
        </label>
      </div>
      {!rapor ? (
        <Yukleniyor />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kutu ikon={CheckCircle2} etiket={t('sahaServisi.rapor.tamamlanan')} deger={sayi(rapor.toplam.tamamlanan)} testid="saha-rapor-tamamlanan" />
            <Kutu ikon={Timer} etiket={t('sahaServisi.rapor.ortalamaSure')} deger={sayi(rapor.toplam.ortalama_sure_dk, ` ${t('sahaServisi.dkKisa')}`)} />
            <Kutu ikon={Gauge} etiket={t('sahaServisi.rapor.ilkSeferde')} deger={yuzde(rapor.toplam.ilk_seferde_oran)} />
            <Kutu ikon={Star} etiket={t('sahaServisi.rapor.memnuniyet')} deger={rapor.toplam.memnuniyet_ortalama == null ? '—' : `${sayi(rapor.toplam.memnuniyet_ortalama)} / 5`} />
          </div>
          <div className={`${KART} overflow-x-auto`}>
            <table className="w-full min-w-[620px] text-sm" data-testid="saha-rapor-tablo">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  <th className="px-4 py-2 text-start font-medium">{t('sahaServisi.pano.teknisyen')}</th>
                  <th className="px-2 py-2 text-end font-medium">{t('sahaServisi.rapor.tamamlanan')}</th>
                  <th className="px-2 py-2 text-end font-medium">{t('sahaServisi.rapor.ortalamaSure')}</th>
                  <th className="px-2 py-2 text-end font-medium">{t('sahaServisi.rapor.ilkSeferde')}</th>
                  <th className="px-4 py-2 text-end font-medium">{t('sahaServisi.rapor.memnuniyet')}</th>
                </tr>
              </thead>
              <tbody>
                {rapor.teknisyenler.map((x) => (
                  <tr key={x.teknisyen_id} className="border-t border-white/5">
                    <td className="px-4 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: x.renk }} aria-hidden="true" />
                        {x.ad}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-end tabular-nums">{x.tamamlanan}</td>
                    <td className="px-2 py-2 text-end tabular-nums">{sayi(x.ortalama_sure_dk, ` ${t('sahaServisi.dkKisa')}`)}</td>
                    <td className="px-2 py-2 text-end tabular-nums">{yuzde(x.ilk_seferde_oran)}</td>
                    <td className="px-4 py-2 text-end tabular-nums">
                      {x.memnuniyet_ortalama == null ? '—' : `${sayi(x.memnuniyet_ortalama)} (${x.puan_sayisi})`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(rapor.acik).map(([d, n]) => (
              <Rozet key={d}>
                {t(`sahaServisi.durum.${d}`)}: {n}
              </Rozet>
            ))}
          </div>
        </>
      )}
      <section className={`${KART} p-4`} data-testid="saha-bakim-listesi">
        <h3 className="mb-2 flex items-center gap-2 font-semibold">
          <CalendarClock className="h-5 w-5 text-purple-300" aria-hidden="true" />
          {t('sahaServisi.rapor.bakimBaslik')}
        </h3>
        {bakim === null ? (
          <Yukleniyor />
        ) : bakim.length === 0 ? (
          <Bos>{t('sahaServisi.rapor.bakimBos')}</Bos>
        ) : (
          <ul className="divide-y divide-white/5 text-sm">
            {bakim.map((c) => (
              <li key={c.cihaz_id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="font-medium">{c.tur}</span>
                <span className="text-muted-foreground">{[c.marka, c.model].filter(Boolean).join(' ')}</span>
                <span className="text-muted-foreground">· {c.musteri_ad}</span>
                <Rozet renk={c.gecikme_gun > 0 ? 'border-red-400/40 bg-red-500/15 text-red-200' : 'border-amber-400/40 bg-amber-500/15 text-amber-200'}>
                  {c.gecikme_gun > 0 ? t('sahaServisi.rapor.gecikti', { sayi: c.gecikme_gun }) : t('sahaServisi.cihaz.vade', { tarih: c.vade })}
                </Rozet>
                <span className="ms-auto">
                  {c.acik_is_emri ? (
                    <Button size="sm" variant="ghost" onClick={() => onAc(c.acik_is_emri!.id)}>
                      {c.acik_is_emri.no}
                    </Button>
                  ) : (
                    !saltOkunur && (
                      <Button size="sm" className="gap-1" onClick={() => void bakimIsi(c)} disabled={mesgul === c.cihaz_id} data-testid="saha-bakim-is-olustur">
                        {mesgul === c.cihaz_id ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Wrench className="h-4 w-4" aria-hidden="true" />}
                        {t('sahaServisi.cihaz.bakimIsi')}
                      </Button>
                    )
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Kutu({ ikon: Ikon, etiket, deger, testid }: { ikon: typeof Star; etiket: string; deger: string; testid?: string }) {
  return (
    <div className={`${KART} p-4`}>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Ikon className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {etiket}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums" data-testid={testid}>
        {deger}
      </p>
    </div>
  );
}
