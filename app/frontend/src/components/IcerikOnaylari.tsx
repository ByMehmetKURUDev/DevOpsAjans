import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, PenTool } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { IcerikKarari, IcerikOnizleme } from '@/components/IcerikOnizleme';
import { OnayHatasi, onayHataMetni, onaylarim, onaylarimKarar, planlananYaz, type BekleyenOnay, type OnaySonucu } from '@/lib/icerikOnay';

/**
 * Faz 5I — Müşteri paneli › "Onay bekleyen içerikler" (genel görünümün üstü).
 *
 * Ajansın bu hesap için hazırlayıp onaya sunduğu gönderiler. İçerik stüdyosu modülü
 * KAPALI olsa da görünür (ajans müşteri için içerik yönetir); yalnız ekip izni `icerik`.
 * E-postadaki imzalı bağlantıyla aynı karar, oturumla. Bekleyen yoksa hiçbir şey çizmez.
 * `gomulu`: İçerik stüdyosu › Onaylar sekmesinde (başlıksız, boşken bilgi metni).
 */
export default function IcerikOnaylari({ gomulu = false, onDegisti }: { gomulu?: boolean; onDegisti?: () => void }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<BekleyenOnay[] | null>(null);
  const [acik, setAcik] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      const l = await onaylarim();
      setListe(l);
      setAcik((a) => a ?? (l.length === 1 ? l[0].gonderi.id : null));
    } catch {
      setListe([]);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (!liste) return null;
  if (liste.length === 0) {
    return gomulu ? (
      <p className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-muted-foreground" data-testid="icerik-onaylari-bos">
        {t('icerikOnay.bos')}
      </p>
    ) : null;
  }

  const karar = (gid: number) => async (sonuc: OnaySonucu, not?: string) => {
    try {
      await onaylarimKarar(gid, sonuc, not);
    } catch (h) {
      toast.error(onayHataMetni(t, h));
      if (h instanceof OnayHatasi && [404, 409, 410].includes(h.durum)) await yukle();
      return;
    }
    toast.success(sonuc === 'onay' ? t('icerikOnay.onaylandi') : t('icerikOnay.revizyonGonderildi'));
    setListe((l) => (l || []).filter((x) => x.gonderi.id !== gid));
    onDegisti?.();
  };

  return (
    <section className={gomulu ? '' : 'mb-10'} data-testid="icerik-onaylari" aria-labelledby={gomulu ? undefined : 'icerik-onaylari-baslik'}>
      {!gomulu && (
        <>
          <h2 id="icerik-onaylari-baslik" className="mb-1 flex items-center gap-2 text-lg font-semibold">
            <PenTool className="h-5 w-5 text-fuchsia-300" aria-hidden="true" />
            {t('icerikOnay.baslik')}
            <span className="rounded-full border border-fuchsia-400/30 bg-fuchsia-500/10 px-2 py-0.5 text-xs text-fuchsia-200">{liste.length}</span>
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">{t('icerikOnay.aciklama')}</p>
        </>
      )}
      <div className="grid gap-3">
        {liste.map(({ gonderi: g, son_kullanma }) => {
          const acikMi = acik === g.id;
          return (
            <article key={g.id} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-icerik-onay={g.id}>
              <button
                type="button"
                className="flex w-full items-start justify-between gap-3 text-start"
                onClick={() => setAcik(acikMi ? null : g.id)}
                aria-expanded={acikMi}
              >
                <span className="min-w-0">
                  <span className="block break-words font-medium">{g.baslik}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {planlananYaz(g, i18n.language)} · {g.kanallar.map((k) => t(`icerikOnay.kanal.${k.kanal}`, { defaultValue: k.kanal })).join(', ')}
                  </span>
                </span>
                {acikMi ? <ChevronUp className="h-4 w-4 shrink-0" aria-hidden="true" /> : <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />}
              </button>
              {acikMi && (
                <div className="mt-3 border-t border-white/5 pt-3">
                  <IcerikOnizleme g={g} />
                  {son_kullanma && (
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      {t('icerikOnay.sonKullanma', { tarih: new Date(son_kullanma).toLocaleDateString(i18n.language) })}
                    </p>
                  )}
                  <IcerikKarari onKarar={karar(g.id)} testId={`icerik-karar-${g.id}`} />
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
