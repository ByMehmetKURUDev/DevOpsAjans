import { useCallback, useEffect, useMemo, useState } from 'react';
import { ExternalLink, ListChecks, Loader2, SquarePlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, projeGoreviOlustur, type BelgeApi, type YapilacakOgesi } from '@/lib/belgeler';

import { KART, Rozet, Yukleniyor } from './ortak';

/**
 * Faz 5B — "Yapılacaklarım": belgelerdeki işaretlenmemiş onay kutuları (`- [ ] …`).
 *
 * "Bana atanan" = maddede `@benim-epostam` geçenler; "Tüm açık maddeler" = görebildiğim
 * belgelerin hepsi. Görevler modülü (Faz 2B) AYRI: yönetici, projeye bağlı belgedeki maddeyi
 * mevcut görev ucuyla projeye görev yapar; madde `→ #<görev>` bağıyla işaretlenir.
 */

interface Ozellikler {
  api: BelgeApi;
  onBelgeAc: (id: number) => void;
}

export default function Yapilacaklarim({ api, onBelgeAc }: Ozellikler) {
  const { t } = useTranslation();
  const [kapsam, setKapsam] = useState<'bana' | 'hepsi'>('bana');
  const [ogeler, setOgeler] = useState<YapilacakOgesi[] | null>(null);
  const [calisan, setCalisan] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    try {
      setOgeler((await api.yapilacaklar(kapsam)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setOgeler([]);
    }
  }, [api, kapsam, t]);

  useEffect(() => {
    setOgeler(null);
    void yukle();
  }, [yukle]);

  const gruplar = useMemo(() => {
    const g = new Map<number, { baslik: string; ogeler: YapilacakOgesi[] }>();
    for (const o of ogeler ?? []) {
      if (!g.has(o.belge_id)) g.set(o.belge_id, { baslik: o.belge_baslik, ogeler: [] });
      g.get(o.belge_id)!.ogeler.push(o);
    }
    return [...g.entries()];
  }, [ogeler]);

  const isaretle = async (o: YapilacakOgesi) => {
    const anahtar = `${o.belge_id}:${o.satir}`;
    setCalisan(anahtar);
    try {
      await api.yapilacak(o.belge_id, { satir: o.satir, metin: o.metin, tamam: true });
      setOgeler((l) => (l ?? []).filter((x) => !(x.belge_id === o.belge_id && x.satir === o.satir)));
      toast.success(t('belgeler.yapilacak.tamamlandi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
      void yukle();
    } finally {
      setCalisan(null);
    }
  };

  const gorevYap = async (o: YapilacakOgesi) => {
    if (!o.proje_id) return;
    const anahtar = `g${o.belge_id}:${o.satir}`;
    setCalisan(anahtar);
    try {
      const baslik = o.metin.replace(/@\S+@\S+/g, '').replace(/\s+/g, ' ').trim() || o.metin;
      const g = await projeGoreviOlustur(o.proje_id, baslik, t('belgeler.yapilacak.gorevAciklama', { belge: o.belge_baslik }));
      await api.gorevBagla(o.belge_id, { satir: o.satir, metin: o.metin, gorev_id: g.id });
      toast.success(t('belgeler.yapilacak.gorevOlustu', { sayi: g.id }));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisan(null);
    }
  };

  return (
    <section className={KART} data-testid="yapilacaklarim">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-semibold">
          <ListChecks className="h-5 w-5 text-emerald-300" aria-hidden="true" />
          {t('belgeler.yapilacak.baslik')}
        </h3>
        <div className="flex gap-1" role="tablist" aria-label={t('belgeler.yapilacak.baslik')}>
          {(['bana', 'hepsi'] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={kapsam === k}
              onClick={() => setKapsam(k)}
              className={`rounded-lg px-3 py-1.5 text-sm ${kapsam === k ? 'bg-emerald-500/20 text-white ring-1 ring-emerald-400/40' : 'text-muted-foreground hover:bg-white/5'}`}
              data-yapilacak-kapsam={k}
            >
              {t(`belgeler.yapilacak.${k}`)}
            </button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">{t('belgeler.yapilacak.aciklama')}</p>
      {ogeler === null ? (
        <Yukleniyor />
      ) : gruplar.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground" data-testid="yapilacak-bos">
          {kapsam === 'bana' ? t('belgeler.yapilacak.bos') : t('belgeler.yapilacak.bosHepsi')}
        </p>
      ) : (
        <div className="space-y-4">
          {gruplar.map(([belgeId, g]) => (
            <div key={belgeId}>
              <button type="button" onClick={() => onBelgeAc(belgeId)} className="mb-1 flex items-center gap-1 text-sm font-medium text-purple-200 hover:underline">
                {g.baslik}
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <ul className="space-y-1">
                {g.ogeler.map((o) => {
                  const anahtar = `${o.belge_id}:${o.satir}`;
                  return (
                    <li key={anahtar} className="flex flex-wrap items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/[0.03]" data-testid="yapilacak-oge">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-emerald-500"
                        checked={false}
                        disabled={!!o.salt_okunur || calisan === anahtar}
                        onChange={() => void isaretle(o)}
                        aria-label={t('belgeler.yapilacak.isaretle', { metin: o.metin })}
                      />
                      <span className="min-w-0 flex-1 break-words text-sm">{o.metin}</span>
                      {o.bana && <Rozet renk="emerald">{t('belgeler.yapilacak.banaRozet')}</Rozet>}
                      {o.salt_okunur && <Rozet renk="amber">{t('belgeler.yapilacak.salt')}</Rozet>}
                      {o.gorev_id ? (
                        <Rozet renk="sky">{t('belgeler.yapilacak.gorevBagli', { sayi: o.gorev_id })}</Rozet>
                      ) : api.mod === 'yonetici' ? (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 gap-1 !bg-transparent px-2 text-xs"
                          disabled={!o.proje_id || calisan === `g${anahtar}`}
                          title={o.proje_id ? undefined : t('belgeler.yapilacak.projeGerekli')}
                          onClick={() => void gorevYap(o)}
                          data-testid="yapilacak-gorev"
                        >
                          {calisan === `g${anahtar}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <SquarePlus className="h-3.5 w-3.5" aria-hidden="true" />}
                          {t('belgeler.yapilacak.gorevOlustur')}
                        </Button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
