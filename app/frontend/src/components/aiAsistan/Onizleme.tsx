import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { Loader2, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import SohbetPenceresi from '@/components/aiAsistan/SohbetPenceresi';
import { KART, SECIM } from '@/components/aiAsistan/ortak';
import { oturumBasliklari, type Asistan, type AsistanApi } from '@/lib/aiAsistan';
import { AcikHata, acikIstek, asistanPaketiYukle, DILLER, dilSec, type AcikYapilandirma, type AsistanDili } from '@/lib/asistanOrtak';

/**
 * Faz 5A — panel içinde canlı önizleme ("Dene"). Herkese açık pencerenin aynısı; istekler
 * oturumla gidiyor (`onizleme`), asistan pasif olsa da çalışıyor, köken denetimi yok.
 * Yöneticinin müşteri asistanını denemesi müşterinin hakkından/kredisinden düşmez.
 * `ust`: Ayarlar formundaki kaydedilmemiş görünüm (ad, renk, karşılama, önerilen sorular).
 */

const DIL_ADLARI: Record<AsistanDili, string> = {
  tr: 'Türkçe', en: 'English', de: 'Deutsch', ru: 'Русский', zh: '中文', hi: 'हिन्दी', ar: 'العربية',
};

export default function Onizleme({
  asistan,
  ust,
  kompakt = false,
}: {
  api?: AsistanApi;
  asistan: Asistan;
  ust?: Partial<AcikYapilandirma>;
  kompakt?: boolean;
}) {
  const { t: panelT, i18n: panelI18n } = useTranslation();
  const [dil, setDil] = useState<AsistanDili>(() => dilSec(asistan.dil !== 'otomatik' ? asistan.dil : panelI18n.language));
  const [yap, setYap] = useState<AcikYapilandirma | null>(null);
  const [t, setT] = useState<TFunction | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [surum, setSurum] = useState(0);

  useEffect(() => {
    let iptal = false;
    setYap(null);
    setHata(null);
    (async () => {
      try {
        const v = await acikIstek<AcikYapilandirma>(
          `/api/v1/asistan/${encodeURIComponent(asistan.anahtar)}?onizleme=1&dil=${dil}`,
          {},
          oturumBasliklari()
        );
        await asistanPaketiYukle(dil);
        if (iptal) return;
        setT(() => i18n.getFixedT(dil));
        setYap(v);
      } catch (e) {
        if (!iptal) setHata(panelT(`aiAsistan.hata.${e instanceof AcikHata ? e.kod : 'genel'}`, { defaultValue: panelT('aiAsistan.hata.genel') }));
      }
    })();
    return () => {
      iptal = true;
    };
  }, [asistan.anahtar, dil, panelT, surum]);

  const birlesik = useMemo(() => (yap ? { ...yap, ...(ust || {}) } : null), [yap, ust]);

  return (
    <div className={kompakt ? '' : `${KART} p-4`} data-testid="ai-onizleme">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <p className="me-auto text-sm text-muted-foreground">{panelT('aiAsistan.onizleme.aciklama')}</p>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          <span className="sr-only">{panelT('aiAsistan.onizleme.dil')}</span>
          <select className={`${SECIM} h-8 w-auto`} value={dil} onChange={(e) => setDil(e.target.value as AsistanDili)} data-testid="ai-onizleme-dil">
            {DILLER.map((d) => (
              <option key={d} value={d}>
                {DIL_ADLARI[d]}
              </option>
            ))}
          </select>
        </label>
        <Button type="button" variant="outline" size="sm" className="gap-1 !bg-transparent" onClick={() => setSurum((x) => x + 1)} data-testid="ai-onizleme-sifirla">
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          {panelT('aiAsistan.onizleme.sifirla')}
        </Button>
      </div>
      {hata && <p className="text-sm text-red-300">{hata}</p>}
      {!hata && (!birlesik || !t) && (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      )}
      {birlesik && t && (
        <div className="mx-auto h-[min(620px,75vh)] w-full max-w-md overflow-hidden rounded-2xl border border-white/10 shadow-2xl">
          <SohbetPenceresi key={`${surum}-${dil}-${birlesik.oturum}`} t={t} dil={dil} yap={birlesik} onizleme ekBasliklar={oturumBasliklari} depoAnahtari={null} />
        </div>
      )}
    </div>
  );
}
