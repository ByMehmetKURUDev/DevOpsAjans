import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';

import { anahtarAdi, hataMetni, type Kural, type OtoMeta, type OtomasyonApi } from '@/lib/otomasyon';
import { ANA_DUGME, KART } from './ortak';

/**
 * Hazır şablonlar: tek tıkla kural. Metinler (ad, konu, gövde…) kullanıcının dilinde
 * ön yüzden gidiyor (`otomasyon.sablon.<anahtar>.<metin>`); sunucu yapıyı biliyor.
 */
export default function Sablonlar({
  api,
  meta,
  onOlusturuldu,
}: {
  api: OtomasyonApi;
  meta: OtoMeta | null;
  onOlusturuldu: (k: Kural) => void;
}) {
  const { t } = useTranslation();
  const [mesgul, setMesgul] = useState<string | null>(null);

  const kullan = async (anahtar: string, metinAnahtarlari: string[]) => {
    setMesgul(anahtar);
    try {
      const metinler: Record<string, string> = {};
      for (const m of metinAnahtarlari) {
        // Çeviride yer tutucu `[[aday.ad]]` biçiminde (i18next `{{…}}`i kendisi doldurmasın).
        const deger = (t(`otomasyon.sablon.${anahtar}.${m}`, { defaultValue: '' }) as string).replace(/\[\[([^\]]+)\]\]/g, '{{$1}}');
        if (deger) metinler[m] = deger;
      }
      const k = await api.sablondan(anahtar, metinler);
      toast.success(t('otomasyon.sablon.olusturuldu', { ad: k.ad }));
      onOlusturuldu(k);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  if (!meta) {
    return (
      <div className="flex justify-center py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-label={t('otomasyon.yukleniyor')} />
      </div>
    );
  }
  // Faz 6R: sektör setinin önerdikleri önce ve rozetli (kurulmaz; müşteri isterse tek tıkla kurar).
  const onerilen = meta.onerilen_sablonlar ?? [];
  const sirali = [...meta.sablonlar].sort(
    (a, b) => Number(onerilen.includes(b.anahtar)) - Number(onerilen.includes(a.anahtar))
  );
  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="oto-sablonlar">
      {sirali.map((s) => (
        <article
          key={s.anahtar}
          className={`${KART} flex flex-col p-4 ${onerilen.includes(s.anahtar) ? 'ring-1 ring-purple-400/50' : ''}`}
          data-oto-sablon={s.anahtar}
          data-onerilen={onerilen.includes(s.anahtar) ? 'evet' : undefined}
        >
          {onerilen.includes(s.anahtar) ? (
            <span
              className="mb-2 inline-flex w-fit items-center rounded-full border border-purple-400/40 bg-purple-500/15 px-2 py-0.5 text-[10px] uppercase tracking-wider text-purple-100"
              title={t('otomasyon.sablon.onerilenAciklama')}
            >
              {t('otomasyon.sablon.onerilen')}
            </span>
          ) : null}
          <h3 className="flex items-start gap-2 font-semibold">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-purple-300" aria-hidden="true" />
            {t(`otomasyon.sablon.${s.anahtar}.ad`)}
          </h3>
          <p className="mt-1 flex-1 text-sm text-muted-foreground">{t(`otomasyon.sablon.${s.anahtar}.aciklama`)}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            <span className="text-purple-200">{t(`otomasyon.olay.${anahtarAdi(s.tetik)}`)}</span>
            {' → '}
            {s.eylemler.map((e) => t(`otomasyon.eylem.${e.tur}`)).join(' · ')}
          </p>
          <div className="mt-3">
            <button
              type="button"
              className={ANA_DUGME}
              disabled={mesgul !== null || meta.sinirlar.kural_sayisi >= meta.sinirlar.kural}
              onClick={() => void kullan(s.anahtar, Object.keys(s.metinler))}
              data-testid="oto-sablon-kullan"
            >
              {mesgul === s.anahtar ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
              {t('otomasyon.sablon.kullan')}
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
