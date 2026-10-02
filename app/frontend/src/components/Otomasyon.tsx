import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { History, LayoutTemplate, ListChecks, SlidersHorizontal, Workflow } from 'lucide-react';

import Gunluk from '@/components/otomasyon/Gunluk';
import KuralDuzenleyici from '@/components/otomasyon/KuralDuzenleyici';
import Kurallar from '@/components/otomasyon/Kurallar';
import OzelAlanTanimlari from '@/components/otomasyon/OzelAlanTanimlari';
import Sablonlar from '@/components/otomasyon/Sablonlar';
import { hataMetni, otomasyonApi, type Kural, type OtoMeta, type OtoMod } from '@/lib/otomasyon';

/**
 * Faz 4W — "Otomasyon" sekmesi ("şu olunca bunu yap"). Yönetici panelinde
 * (`mod="yonetici"`: ajansın kuralları; bütün hesapların olayları, CRM ve destek
 * eylemleri, özel alan tanımları) ve müşteri panelinde (`mod="musteri"`: modül
 * `otomasyon` + ekip izni `otomasyon`; yalnız kendi hesabının olayları) aynı bileşen.
 *
 * Alt görünümler: kurallar (adım adım düzenleyici + kuru çalıştırma) · hazır şablonlar ·
 * çalıştırma günlüğü · (yönetici) özel alanlar.
 */

type AltSekme = 'kurallar' | 'sablonlar' | 'gunluk' | 'ozel';

export default function Otomasyon({ mod }: { mod: OtoMod }) {
  const { t } = useTranslation();
  const api = useMemo(() => otomasyonApi(mod), [mod]);
  const [sekme, setSekme] = useState<AltSekme>('kurallar');
  const [meta, setMeta] = useState<OtoMeta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<Kural | 'yeni' | null>(null);
  const [gunlukKurali, setGunlukKurali] = useState<number | null>(null);
  const [yenile, setYenile] = useState(0);

  const metaYukle = useCallback(async () => {
    try {
      setMeta(await api.meta());
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void metaYukle();
  }, [metaYukle]);

  const sekmeler: { key: AltSekme; ikon: typeof Workflow }[] = [
    { key: 'kurallar', ikon: ListChecks },
    { key: 'sablonlar', ikon: LayoutTemplate },
    { key: 'gunluk', ikon: History },
    ...(mod === 'yonetici' ? [{ key: 'ozel' as const, ikon: SlidersHorizontal }] : []),
  ];

  return (
    <section aria-labelledby="otomasyon-baslik" data-testid="otomasyon-sekmesi" className="min-w-0">
      <div className="mb-6">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="otomasyon-baslik">
          <Workflow className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('otomasyon.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {mod === 'yonetici' ? t('otomasyon.aciklamaYonetici') : t('otomasyon.aciklama')}
        </p>
      </div>

      {duzenlenen ? (
        meta && (
          <KuralDuzenleyici
            api={api}
            meta={meta}
            mod={mod}
            kural={duzenlenen === 'yeni' ? null : duzenlenen}
            onKapat={() => setDuzenlenen(null)}
            onKaydedildi={() => {
              setDuzenlenen(null);
              setYenile((x) => x + 1);
              void metaYukle();
            }}
          />
        )
      ) : (
        <>
          <div className="mb-6 flex flex-wrap gap-2" role="tablist" aria-label={t('otomasyon.baslik')}>
            {sekmeler.map(({ key, ikon: Ikon }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={sekme === key}
                data-oto-sekme={key}
                onClick={() => setSekme(key)}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 ${
                  sekme === key
                    ? 'border-purple-400/60 bg-purple-500/20 text-white'
                    : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-white'
                }`}
              >
                <Ikon className="h-4 w-4" aria-hidden="true" />
                {t(`otomasyon.sekme.${key}`)}
              </button>
            ))}
          </div>

          {hata && (
            <p className="mb-4 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200" role="alert">
              {hata}
            </p>
          )}

          {sekme === 'kurallar' && (
            <Kurallar
              key={yenile}
              api={api}
              meta={meta}
              onDuzenle={(k) => setDuzenlenen(k)}
              onYeni={() => setDuzenlenen('yeni')}
              onGunluk={(id) => {
                setGunlukKurali(id);
                setSekme('gunluk');
              }}
              onDegisti={metaYukle}
            />
          )}
          {sekme === 'sablonlar' && (
            <Sablonlar
              api={api}
              meta={meta}
              onOlusturuldu={() => {
                setYenile((x) => x + 1);
                void metaYukle();
                setSekme('kurallar');
              }}
            />
          )}
          {sekme === 'gunluk' && <Gunluk api={api} meta={meta} kuralId={gunlukKurali} onKuralSec={setGunlukKurali} />}
          {sekme === 'ozel' && mod === 'yonetici' && <OzelAlanTanimlari onDegisti={metaYukle} />}
        </>
      )}
    </section>
  );
}
