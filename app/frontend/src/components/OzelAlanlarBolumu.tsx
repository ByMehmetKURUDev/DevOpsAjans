import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, Save, SlidersHorizontal } from 'lucide-react';

import { ozelAlanApi, ozelHataMetni, type OzelAlan, type OzelBolum, type OzelVarlik } from '@/lib/otomasyon';

const ALAN =
  'w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';

interface Props {
  varlik: OzelVarlik;
  /** Kayıt kimliği (müşteri hesabında e-posta). */
  kimlik: string | number;
  /** yonetici: düzenlenebilir; musteri: yalnız "müşteriye görünür" alanlar, salt okunur. */
  mod?: 'yonetici' | 'musteri';
  className?: string;
}

/**
 * Faz 4W — kayıt ekranlarına (CRM aday çekmecesi, proje ayrıntısı, destek talebi, müşteri
 * ayrıntısı) gömülen "Özel alanlar" bölümü. Tanım yoksa hiçbir şey çizmez (ekran kalabalıklaşmasın).
 * Ek paket `ozelAlanlar` — kullanan yer `ekliLazy('ozelAlanlar', …)` ile yükler.
 */
export default function OzelAlanlarBolumu({ varlik, kimlik, mod = 'yonetici', className = '' }: Props) {
  const { t, i18n } = useTranslation();
  const [bolum, setBolum] = useState<OzelBolum | null>(null);
  const [taslak, setTaslak] = useState<Record<string, unknown>>({});
  const [mesgul, setMesgul] = useState(false);
  const [degisti, setDegisti] = useState(false);

  const yukle = useCallback(async () => {
    try {
      const b =
        mod === 'musteri'
          ? await ozelAlanApi.musteriBolum(varlik as 'proje' | 'destek', Number(kimlik))
          : await ozelAlanApi.bolum(varlik, kimlik);
      setBolum(b);
      setTaslak(b.degerler);
      setDegisti(false);
    } catch {
      setBolum(null);
    }
  }, [varlik, kimlik, mod]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (!bolum || bolum.alanlar.length === 0) return null;
  if (mod === 'musteri' && Object.keys(bolum.degerler).length === 0) return null;

  const yaz = (anahtar: string, deger: unknown) => {
    setTaslak((x) => ({ ...x, [anahtar]: deger }));
    setDegisti(true);
  };

  const kaydet = async () => {
    setMesgul(true);
    try {
      const degerler: Record<string, unknown> = {};
      for (const a of bolum.alanlar) degerler[a.anahtar] = taslak[a.anahtar] ?? null;
      const b = await ozelAlanApi.kaydet(varlik, kimlik, degerler);
      setBolum(b);
      setTaslak(b.degerler);
      setDegisti(false);
      toast.success(t('ozelAlanlar.kaydedildi'));
    } catch (e) {
      toast.error(ozelHataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const goster = (a: OzelAlan, v: unknown): string => {
    if (v === null || v === undefined || v === '') return '—';
    if (a.tur === 'evet_hayir') return v ? t('ozelAlanlar.evet') : t('ozelAlanlar.hayir');
    if (Array.isArray(v)) return v.join(', ');
    if (a.tur === 'tarih') {
      try {
        return new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(`${v}T00:00:00`));
      } catch {
        return String(v);
      }
    }
    return String(v);
  };

  return (
    <section
      aria-labelledby={`ozel-${varlik}-${kimlik}`}
      className={`cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-3 ${className}`}
      data-testid="ozel-alanlar-bolumu"
      data-varlik={varlik}
    >
      <h4 id={`ozel-${varlik}-${kimlik}`} className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
        <SlidersHorizontal className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {t('ozelAlanlar.bolumBaslik')}
      </h4>
      {mod === 'musteri' ? (
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          {bolum.alanlar
            .filter((a) => bolum.degerler[a.anahtar] !== undefined)
            .map((a) => (
              <div key={a.id} className="min-w-0">
                <dt className="text-xs text-muted-foreground">{a.ad}</dt>
                <dd className="break-words" data-ozel-deger={a.anahtar}>
                  {a.tur === 'url' ? (
                    <a href={String(bolum.degerler[a.anahtar])} target="_blank" rel="noopener noreferrer" className="text-purple-300 underline-offset-2 hover:underline" dir="ltr">
                      {String(bolum.degerler[a.anahtar])}
                    </a>
                  ) : (
                    goster(a, bolum.degerler[a.anahtar])
                  )}
                </dd>
              </div>
            ))}
        </dl>
      ) : (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            void kaydet();
          }}
        >
          {bolum.alanlar.map((a) => (
            <AlanGirdisi key={a.id} a={a} deger={taslak[a.anahtar]} yaz={yaz} />
          ))}
          <div className="flex justify-end sm:col-span-2">
            <button
              type="submit"
              disabled={mesgul || !degisti}
              className="inline-flex items-center gap-1.5 rounded-md bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
              data-testid="ozel-alanlar-kaydet"
            >
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('ozelAlanlar.kaydet')}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function AlanGirdisi({ a, deger, yaz }: { a: OzelAlan; deger: unknown; yaz: (anahtar: string, deger: unknown) => void }) {
  const { t } = useTranslation();
  const etiket = (
    <span className="block text-xs font-medium text-muted-foreground">
      {a.ad}
      {a.zorunlu && ' *'}
      {a.musteriye_gorunur && <span className="ms-1 text-[10px] text-emerald-300">({t('ozelAlanlar.gorunurRozet')})</span>}
    </span>
  );
  const s = deger === null || deger === undefined ? '' : String(deger);
  if (a.tur === 'evet_hayir') {
    return (
      <label className="flex items-center gap-2 text-sm" data-ozel-girdi={a.anahtar}>
        <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={deger === true} onChange={(e) => yaz(a.anahtar, e.target.checked)} />
        {a.ad}
      </label>
    );
  }
  if (a.tur === 'coklu_secim') {
    const secili = Array.isArray(deger) ? (deger as string[]) : [];
    return (
      <fieldset className="min-w-0 sm:col-span-2" data-ozel-girdi={a.anahtar}>
        <legend>{etiket}</legend>
        <div className="mt-1 flex flex-wrap gap-3 text-sm">
          {a.secenekler.map((sec) => (
            <label key={sec} className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                className="h-4 w-4 accent-purple-500"
                checked={secili.includes(sec)}
                onChange={(e) => yaz(a.anahtar, e.target.checked ? [...secili, sec] : secili.filter((x) => x !== sec))}
              />
              {sec}
            </label>
          ))}
        </div>
      </fieldset>
    );
  }
  return (
    <label className="block min-w-0 space-y-1 text-sm" data-ozel-girdi={a.anahtar}>
      {etiket}
      {a.tur === 'secim' ? (
        <select className={ALAN} value={s} onChange={(e) => yaz(a.anahtar, e.target.value || null)}>
          <option value="">—</option>
          {a.secenekler.map((sec) => (
            <option key={sec}>{sec}</option>
          ))}
        </select>
      ) : (
        <input
          className={ALAN}
          type={a.tur === 'sayi' ? 'number' : a.tur === 'tarih' ? 'date' : a.tur === 'url' ? 'url' : 'text'}
          step="any"
          dir={a.tur === 'url' ? 'ltr' : undefined}
          maxLength={a.tur === 'url' ? 500 : 1000}
          value={s}
          onChange={(e) => yaz(a.anahtar, e.target.value === '' ? null : a.tur === 'sayi' ? Number(e.target.value) : e.target.value)}
        />
      )}
    </label>
  );
}
