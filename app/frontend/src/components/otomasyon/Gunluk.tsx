import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ChevronDown, Loader2, RefreshCw } from 'lucide-react';

import { anahtarAdi, hataMetni, tarihYaz, type Calisma, type Kural, type OtoMeta, type OtomasyonApi } from '@/lib/otomasyon';
import { DurumRozeti, IKINCIL_DUGME, KART, OzetSatirlari, SECIM } from './ortak';

const DURUMLAR = ['tamam', 'bekliyor', 'kosul_tutmadi', 'atlandi', 'hata'] as const;

/** Çalıştırma günlüğü (30 gün): koşul sonucu, her eylemin sonucu ve nedeni. */
export default function Gunluk({
  api,
  meta,
  kuralId,
  onKuralSec,
}: {
  api: OtomasyonApi;
  meta: OtoMeta | null;
  kuralId: number | null;
  onKuralSec: (id: number | null) => void;
}) {
  const { t, i18n } = useTranslation();
  const [kurallar, setKurallar] = useState<Kural[]>([]);
  const [durum, setDurum] = useState<string>('');
  const [liste, setListe] = useState<Calisma[] | null>(null);
  const [sonraki, setSonraki] = useState<number | null>(null);
  const [acik, setAcik] = useState<number | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);

  useEffect(() => {
    api.kurallar().then(setKurallar).catch(() => undefined);
  }, [api]);

  const yukle = useCallback(
    async (once?: number | null) => {
      setYukleniyor(true);
      try {
        const y = await api.gunluk({ kural_id: kuralId, durum: durum || null, once });
        setListe((x) => (once && x ? [...x, ...y.items] : y.items));
        setSonraki(y.sonraki);
      } catch (e) {
        toast.error(hataMetni(t, e));
        setListe((x) => x ?? []);
      } finally {
        setYukleniyor(false);
      }
    },
    [api, kuralId, durum, t]
  );

  useEffect(() => {
    void yukle();
  }, [yukle]);

  return (
    <div className="space-y-4" data-testid="oto-gunluk">
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-0 flex-1 text-sm sm:max-w-xs">
          <span className="mb-1 block text-xs text-muted-foreground">{t('otomasyon.gunluk.kural')}</span>
          <select className={SECIM} value={kuralId ?? ''} onChange={(e) => onKuralSec(e.target.value ? Number(e.target.value) : null)} data-testid="oto-gunluk-kural">
            <option value="">{t('otomasyon.gunluk.hepsi')}</option>
            {kurallar.map((k) => (
              <option key={k.id} value={k.id}>
                {k.ad}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">{t('otomasyon.gunluk.durum')}</span>
          <select className={SECIM} value={durum} onChange={(e) => setDurum(e.target.value)}>
            <option value="">{t('otomasyon.gunluk.hepsi')}</option>
            {DURUMLAR.map((d) => (
              <option key={d} value={d}>
                {t(`otomasyon.durum.${d}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={IKINCIL_DUGME} onClick={() => void yukle()} disabled={yukleniyor} data-testid="oto-gunluk-yenile">
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          {t('otomasyon.yenile')}
        </button>
      </div>
      <p className="text-xs text-muted-foreground">{t('otomasyon.gunluk.saklama', { gun: meta?.sinirlar.saklama_gun ?? 30 })}</p>

      {liste === null ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-label={t('otomasyon.yukleniyor')} />
        </div>
      ) : liste.length === 0 ? (
        <p className={`${KART} p-6 text-center text-sm text-muted-foreground`} data-testid="oto-gunluk-bos">
          {t('otomasyon.gunluk.bos')}
        </p>
      ) : (
        <ul className="space-y-2">
          {liste.map((c) => (
            <li key={c.id} className={`${KART} p-3`} data-oto-calisma={c.id} data-durum={c.durum}>
              <button
                type="button"
                className="flex w-full flex-wrap items-center justify-between gap-2 text-start"
                aria-expanded={acik === c.id}
                onClick={() => setAcik(acik === c.id ? null : c.id)}
              >
                <span className="min-w-0">
                  <span className="block break-words text-sm font-medium">{c.kural || `#${c.kural_id}`}</span>
                  <span className="block text-xs text-muted-foreground">
                    {t(`otomasyon.olay.${anahtarAdi(c.tur)}`)} · {tarihYaz(c.olusturma, i18n.language)}
                    {c.olay_hesap ? ` · ${c.olay_hesap}` : ''}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <DurumRozeti durum={c.durum} metin={t(`otomasyon.durum.${c.durum}`)} />
                  <ChevronDown className={`h-4 w-4 transition-transform ${acik === c.id ? 'rotate-180' : ''}`} aria-hidden="true" />
                </span>
              </button>
              {acik === c.id && (
                <div className="mt-3 space-y-2 border-t border-white/10 pt-3 text-sm" data-testid="oto-gunluk-ayrinti">
                  {c.neden && (
                    <p className="text-xs text-amber-200">
                      {t('otomasyon.gunluk.neden')}: {t(`otomasyon.neden.${anahtarAdi(c.neden)}`, { defaultValue: c.neden })}
                    </p>
                  )}
                  {c.sonraki_zaman && (
                    <p className="text-xs text-sky-200">{t('otomasyon.gunluk.devam', { zaman: tarihYaz(c.sonraki_zaman, i18n.language) })}</p>
                  )}
                  {c.kosul_sonucu !== null && (
                    <p className="text-xs">
                      {t('otomasyon.gunluk.kosul')}: {c.kosul_sonucu ? t('otomasyon.test.kosulTuttu') : t('otomasyon.test.kosulTutmadi')}
                    </p>
                  )}
                  {c.eylem_sonuclari.length > 0 && (
                    <ol className="space-y-1.5">
                      {c.eylem_sonuclari.map((e, i) => (
                        <li key={i} className="rounded-lg border border-white/10 bg-black/20 p-2" data-oto-eylem-sonuc={e.tur} data-durum={e.durum}>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="font-medium">
                              {e.sira + 1}. {t(`otomasyon.eylem.${e.tur}`)}
                            </span>
                            <DurumRozeti durum={e.durum} metin={t(`otomasyon.durum.${e.durum}`)} />
                            {e.neden && <span className="text-muted-foreground">{t(`otomasyon.neden.${anahtarAdi(e.neden)}`, { defaultValue: e.neden })}</span>}
                          </div>
                          <OzetSatirlari ozet={e.ozet} />
                        </li>
                      ))}
                    </ol>
                  )}
                  <p className="text-[11px] text-muted-foreground">
                    {t('otomasyon.gunluk.derinlik', { sayi: c.derinlik })} · {c.olay_id}
                  </p>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {sonraki && (
        <button type="button" className={IKINCIL_DUGME} onClick={() => void yukle(sonraki)} disabled={yukleniyor}>
          {t('otomasyon.dahaFazla')}
        </button>
      )}
    </div>
  );
}
