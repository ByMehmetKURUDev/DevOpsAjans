import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ozelAlanApi, type OzelAlan } from '@/lib/otomasyon';

export interface FormOzelEslemesi {
  alan_id: number;
  zorunlu: boolean;
}

/**
 * Faz 4W — gömülebilir formda sorulacak CRM adayı özel alanları (metin, sayı, URL, seçim).
 * Değer adaya yazılır; kurallar koşulda ve e-posta yer tutucusunda kullanabilir.
 * Ek paket `ozelAlanlar` (CrmFormlari `ekliLazy` ile yüklüyor).
 */
export default function FormOzelAlanlari({
  deger,
  onDegis,
}: {
  deger: FormOzelEslemesi[];
  onDegis: (d: FormOzelEslemesi[]) => void;
}) {
  const { t } = useTranslation();
  const [alanlar, setAlanlar] = useState<OzelAlan[] | null>(null);
  const [formTurleri, setFormTurleri] = useState<string[]>([]);

  useEffect(() => {
    ozelAlanApi
      .liste('crm_aday')
      .then((y) => {
        setAlanlar(y.items.filter((a) => a.aktif));
        setFormTurleri(y.form_turleri);
      })
      .catch(() => setAlanlar([]));
  }, []);

  if (alanlar === null) return null;
  const uygun = alanlar.filter((a) => formTurleri.includes(a.tur));
  const secili = (id: number) => deger.find((d) => d.alan_id === id);
  return (
    <fieldset className="rounded-xl border border-white/10 p-3 sm:col-span-2" data-testid="crm-form-ozel-alanlar">
      <legend className="px-1 text-xs font-medium text-muted-foreground">{t('ozelAlanlar.form.baslik')}</legend>
      {uygun.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('ozelAlanlar.form.bos')}</p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {uygun.map((a) => {
            const s = secili(a.id);
            return (
              <div key={a.id} className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-2 py-1.5 text-sm">
                <span className="min-w-0 break-words">
                  {a.ad} <span className="text-[11px] text-muted-foreground">({t(`ozelAlanlar.turler.${a.tur}`)})</span>
                </span>
                <span className="flex shrink-0 items-center gap-3 text-xs">
                  <label className="inline-flex items-center gap-1">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={!!s}
                      onChange={(e) =>
                        onDegis(e.target.checked ? [...deger, { alan_id: a.id, zorunlu: a.zorunlu }] : deger.filter((d) => d.alan_id !== a.id))
                      }
                      data-crm-form-ozel={a.anahtar}
                    />
                    {t('ozelAlanlar.form.sor')}
                  </label>
                  <label className="inline-flex items-center gap-1">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-500"
                      checked={!!s?.zorunlu}
                      disabled={!s || a.zorunlu}
                      onChange={(e) => onDegis(deger.map((d) => (d.alan_id === a.id ? { ...d, zorunlu: e.target.checked } : d)))}
                    />
                    {t('ozelAlanlar.zorunlu')}
                  </label>
                </span>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">{t('ozelAlanlar.form.ipucu')}</p>
    </fieldset>
  );
}
