import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { CalendarPlus, Loader2, X } from 'lucide-react';

import { DUGME_ANA, DUGME_IKINCIL, KART, Rozet, Zaman } from '@/components/toplantilar/ortak';
import { hataKodu, talepKapat, talepler, type Talep } from '@/lib/toplantilar';

/** Faz 6T — müşterilerin "Toplantı iste" talepleri (gelen kutusunda da `toplanti_talebi`). */
export default function Talepler({ onPlanla, onDegisti }: { onPlanla: (t: Talep) => void; onDegisti: () => void }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Talep[] | null>(null);
  const [calisan, setCalisan] = useState<number | null>(null);

  const yukle = useCallback(() => {
    talepler()
      .then((g) => setListe(g.items))
      .catch(() => setListe([]));
  }, []);

  useEffect(() => {
    yukle();
  }, [yukle]);

  if (!liste) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  const sirali = [...liste].sort((a, b) => Number(b.durum === 'bekliyor') - Number(a.durum === 'bekliyor'));
  return (
    <section className={`${KART} p-4 sm:p-6`} data-testid="toplanti-talepleri">
      <h3 className="font-semibold">{t('toplantilar.talep.baslik')}</h3>
      <p className="mb-3 text-sm text-muted-foreground">{t('toplantilar.talep.aciklama')}</p>
      {sirali.length === 0 && <p className="text-sm text-muted-foreground">{t('toplantilar.talep.yok')}</p>}
      <ul className="divide-y divide-white/5">
        {sirali.map((x) => (
          <li key={x.id} className="flex flex-wrap items-start justify-between gap-3 py-3 text-sm" data-talep={x.id}>
            <div className="min-w-0 flex-1 basis-56">
              <p className="break-words font-medium">{x.konu}</p>
              <p className="break-all text-xs text-muted-foreground">
                {x.kisi_email}
                {x.hesap_email !== x.kisi_email && ` · ${x.hesap_email}`}
              </p>
              <ul className="mt-1 space-y-0.5 text-xs text-white/80">
                {x.araliklar.map((a, i) => (
                  <li key={i}>
                    {t('toplantilar.iste.aralik', { sayi: i + 1 })}: <Zaman iso={a.bas} /> → <Zaman iso={a.bit} />
                  </li>
                ))}
              </ul>
              {x.not && <p className="mt-1 whitespace-pre-line break-words text-xs text-muted-foreground">{x.not}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Rozet tur={x.durum === 'bekliyor' ? 'uyari' : x.durum === 'planlandi' ? 'katilacak' : 'bekliyor'}>
                {t(`toplantilar.talep.durum.${x.durum}`)}
              </Rozet>
              {x.durum === 'bekliyor' && (
                <>
                  <button type="button" className={DUGME_ANA} onClick={() => onPlanla(x)} data-talep-planla={x.id}>
                    <CalendarPlus className="h-4 w-4" aria-hidden="true" />
                    {t('toplantilar.talep.planla')}
                  </button>
                  <button
                    type="button"
                    className={DUGME_IKINCIL}
                    disabled={calisan === x.id}
                    onClick={() => {
                      setCalisan(x.id);
                      talepKapat(x.id)
                        .then(() => {
                          toast.success(t('toplantilar.talep.kapatildi'));
                          yukle();
                          onDegisti();
                        })
                        .catch((h) => toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') })))
                        .finally(() => setCalisan(null));
                    }}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                    {t('toplantilar.talep.kapat')}
                  </button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
