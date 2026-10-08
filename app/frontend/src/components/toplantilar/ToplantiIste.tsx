import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, Plus, Send, X } from 'lucide-react';

import { Alan, DUGME_ANA, DUGME_IKINCIL, GIRDI, KART, METIN } from '@/components/toplantilar/ortak';
import { hataKodu, mTalepGonder, yereldenUtc, type Talep } from '@/lib/toplantilar';

/**
 * Faz 6T — müşterinin "Toplantı iste" formu: konu + en çok 3 tercih edilen zaman aralığı (tarayıcının saat
 * diliminde girilir, UTC gönderilir) + not. Talep ajansın Gelen kutusuna düşer (`toplanti_talebi`).
 */
export default function ToplantiIste({ onGonderildi, onKapat }: { onGonderildi: (t: Talep) => void; onKapat: () => void }) {
  const { t } = useTranslation();
  const [konu, setKonu] = useState('');
  const [araliklar, setAraliklar] = useState<{ bas: string; bit: string }[]>([{ bas: '', bit: '' }]);
  const [not, setNot] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  async function gonder() {
    setHata(null);
    const temiz = araliklar
      .map((a) => ({ bas: yereldenUtc(a.bas), bit: yereldenUtc(a.bit) }))
      .filter((a): a is { bas: string; bit: string } => !!a.bas && !!a.bit);
    if (!konu.trim()) {
      setHata(t('toplantilar.hata.konu_gecersiz'));
      return;
    }
    if (!temiz.length) {
      setHata(t('toplantilar.hata.aralik_gerekli'));
      return;
    }
    setGonderiliyor(true);
    try {
      const s = await mTalepGonder({ konu: konu.trim(), araliklar: temiz, not: not.trim() || undefined });
      toast.success(t('toplantilar.iste.gonderildi'));
      onGonderildi(s);
    } catch (h) {
      setHata(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setGonderiliyor(false);
    }
  }

  return (
    <section className={`${KART} p-4 sm:p-6`} aria-labelledby="toplanti-iste-baslik" data-testid="toplanti-iste">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="toplanti-iste-baslik" className="text-lg font-semibold">
            {t('toplantilar.iste.baslik')}
          </h3>
          <p className="text-sm text-muted-foreground">{t('toplantilar.iste.aciklama')}</p>
        </div>
        <button type="button" className={DUGME_IKINCIL} onClick={onKapat} aria-label={t('toplantilar.musteri.kapat')}>
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <Alan etiket={t('toplantilar.iste.konu')}>
        <input className={GIRDI} value={konu} maxLength={200} onChange={(e) => setKonu(e.target.value)} data-iste-konu />
      </Alan>
      <fieldset className="mt-4">
        <legend className="mb-1 text-sm font-medium text-white/90">{t('toplantilar.iste.araliklar')}</legend>
        <p className="mb-2 text-xs text-muted-foreground">{t('toplantilar.iste.saatNotu')}</p>
        <div className="space-y-2">
          {araliklar.map((a, i) => (
            <div key={i} className="grid min-w-0 gap-2 sm:grid-cols-[auto_1fr_1fr_auto] sm:items-center" data-iste-aralik={i}>
              <span className="text-xs text-muted-foreground">{t('toplantilar.iste.aralik', { sayi: i + 1 })}</span>
              <input
                type="datetime-local"
                className={GIRDI}
                value={a.bas}
                aria-label={`${t('toplantilar.iste.aralik', { sayi: i + 1 })} — ${t('toplantilar.iste.bas')}`}
                onChange={(e) => {
                  const deger = e.target.value;
                  setAraliklar((x) =>
                    x.map((y, j) => {
                      if (j !== i) return y;
                      // Bitiş boşsa başlangıçtan 1 saat sonrası öner.
                      let bit = y.bit;
                      if (!bit && deger) {
                        const d = new Date(deger);
                        if (!Number.isNaN(d.getTime())) {
                          const s = new Date(d.getTime() + 3600000);
                          const p = (n: number) => String(n).padStart(2, '0');
                          bit = `${s.getFullYear()}-${p(s.getMonth() + 1)}-${p(s.getDate())}T${p(s.getHours())}:${p(s.getMinutes())}`;
                        }
                      }
                      return { bas: deger, bit };
                    })
                  );
                }}
                dir="ltr"
                data-iste-bas={i}
              />
              <input
                type="datetime-local"
                className={GIRDI}
                value={a.bit}
                aria-label={`${t('toplantilar.iste.aralik', { sayi: i + 1 })} — ${t('toplantilar.iste.bit')}`}
                onChange={(e) => setAraliklar((x) => x.map((y, j) => (j === i ? { ...y, bit: e.target.value } : y)))}
                dir="ltr"
                data-iste-bit={i}
              />
              <button
                type="button"
                className={DUGME_IKINCIL}
                disabled={araliklar.length === 1}
                onClick={() => setAraliklar((x) => x.filter((_, j) => j !== i))}
                aria-label={t('toplantilar.form.kaldir')}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
        <button type="button" className={`${DUGME_IKINCIL} mt-2`} disabled={araliklar.length >= 3} onClick={() => setAraliklar((x) => [...x, { bas: '', bit: '' }])}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('toplantilar.iste.aralikEkle')}
        </button>
      </fieldset>
      <Alan etiket={t('toplantilar.iste.not')} className="mt-4">
        <textarea className={METIN} value={not} maxLength={2000} onChange={(e) => setNot(e.target.value)} data-iste-not />
      </Alan>
      {hata && (
        <p className="mt-3 rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm text-red-200" role="alert">
          {hata}
        </p>
      )}
      <button type="button" className={`${DUGME_ANA} mt-4`} onClick={() => void gonder()} disabled={gonderiliyor} data-iste-gonder>
        {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
        {t('toplantilar.iste.gonder')}
      </button>
    </section>
  );
}
