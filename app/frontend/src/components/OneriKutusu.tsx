import { useCallback, useEffect, useState } from 'react';
import { Lightbulb, Loader2, Send, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ProjeHatasi, oneriGonder, oneriler as onerileriGetir, oyGeriAl, oyVer, type Oneri, type OneriDurumu } from '@/lib/projeYonetimi';

const DURUM_RENGI: Record<OneriDurumu, string> = {
  yeni: 'bg-white/10 text-foreground/80',
  inceleniyor: 'bg-amber-500/15 text-amber-200',
  planlandi: 'bg-sky-500/15 text-sky-200',
  yapildi: 'bg-emerald-500/15 text-emerald-200',
  reddedildi: 'bg-white/5 text-muted-foreground',
};

/**
 * Müşteri › Destek › Öneri kutusu (Faz 2B, beta).
 *
 * Müşteri öneri gönderir, diğer müşterilerin önerilerini oylar (kişi başına
 * tek oy, geri alınabilir). Kimin önerdiği ve kimin oy verdiği görünmez;
 * yalnız "sizin öneriniz" rozeti ve anonim oy sayısı.
 */
export default function OneriKutusu() {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Oneri[] | null>(null);
  const [form, setForm] = useState({ baslik: '', aciklama: '' });
  const [mesgul, setMesgul] = useState<number | 'form' | null>(null);

  const hata = (h: unknown) =>
    toast.error(h instanceof ProjeHatasi ? t(`duyurular.hata.${h.kod}`, { defaultValue: t('duyurular.hata.genel') }) : t('duyurular.hata.genel'));

  const yukle = useCallback(async () => {
    try {
      setListe(await onerileriGetir());
    } catch {
      setListe([]);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const gonder = async () => {
    if (!form.baslik.trim()) {
      toast.error(t('duyurular.hata.baslik_gerekli'));
      return;
    }
    setMesgul('form');
    try {
      const o = await oneriGonder(form.baslik.trim(), form.aciklama.trim() || undefined);
      setListe((l) => [o, ...(l || [])]);
      setForm({ baslik: '', aciklama: '' });
      toast.success(t('duyurular.oneri.gonderildi'));
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(null);
    }
  };

  const oyla = async (o: Oneri) => {
    setMesgul(o.id);
    try {
      const y = o.oyladim ? await oyGeriAl(o.id) : await oyVer(o.id);
      setListe((l) => (l || []).map((x) => (x.id === o.id ? y : x)));
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(null);
    }
  };

  return (
    <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-testid="oneri-kutusu" aria-labelledby="oneri-baslik">
      <h3 id="oneri-baslik" className="flex items-center gap-2 text-lg font-semibold">
        <Lightbulb className="h-5 w-5 text-amber-300" aria-hidden="true" /> {t('duyurular.oneri.baslik')}
        <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[10px] font-normal text-purple-200">{t('duyurular.oneri.beta')}</span>
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{t('duyurular.oneri.aciklama')}</p>

      <form
        className="mt-4 grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void gonder();
        }}
      >
        <label className="sr-only" htmlFor="oneri-yeni-baslik">
          {t('duyurular.oneri.yeniBaslik')}
        </label>
        <Input
          id="oneri-yeni-baslik"
          value={form.baslik}
          onChange={(e) => setForm({ ...form, baslik: e.target.value })}
          placeholder={t('duyurular.oneri.yeniBaslik')}
          maxLength={160}
          data-testid="oneri-baslik"
        />
        <label className="sr-only" htmlFor="oneri-yeni-aciklama">
          {t('duyurular.oneri.yeniAciklama')}
        </label>
        <textarea
          id="oneri-yeni-aciklama"
          value={form.aciklama}
          onChange={(e) => setForm({ ...form, aciklama: e.target.value })}
          placeholder={t('duyurular.oneri.yeniAciklama')}
          rows={2}
          maxLength={2000}
          className="rounded-md border border-white/10 bg-white/5 p-2 text-sm"
        />
        <div>
          <Button type="submit" size="sm" disabled={mesgul === 'form'} className="gap-2" data-testid="oneri-gonder">
            {mesgul === 'form' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {t('duyurular.oneri.gonder')}
          </Button>
        </div>
      </form>

      <div className="mt-5">
        {liste === null ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : liste.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('duyurular.oneri.bos')}</p>
        ) : (
          <ul className="space-y-2">
            {liste.map((o) => (
              <li key={o.id} className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3" data-testid={`oneri-${o.id}`}>
                <button
                  type="button"
                  onClick={() => void oyla(o)}
                  disabled={o.benim || mesgul === o.id || o.durum === 'yapildi' || o.durum === 'reddedildi'}
                  aria-pressed={o.oyladim}
                  aria-label={o.oyladim ? t('duyurular.oneri.oyGeriAl') : t('duyurular.oneri.oy')}
                  title={o.benim ? t('duyurular.oneri.benim') : undefined}
                  className={`flex shrink-0 flex-col items-center rounded-xl px-3 py-1.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                    o.oyladim ? 'bg-purple-500/25 text-purple-100 ring-1 ring-purple-400/50' : 'bg-white/5 hover:bg-white/10'
                  }`}
                  data-testid={`oneri-oy-${o.id}`}
                >
                  <ThumbsUp className="h-4 w-4" aria-hidden="true" />
                  <span className="font-semibold" data-testid={`oneri-oy-sayisi-${o.id}`}>
                    {o.oy_sayisi}
                  </span>
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className={`rounded-full px-2 py-0.5 ${DURUM_RENGI[o.durum]}`}>{t(`duyurular.oneriDurum.${o.durum}`)}</span>
                    {o.benim && <span className="rounded-full bg-white/10 px-2 py-0.5">{t('duyurular.oneri.benim')}</span>}
                    <span className="text-muted-foreground">{t('duyurular.oneri.oySayisi', { sayi: o.oy_sayisi })}</span>
                  </div>
                  <p className="mt-1 break-words text-sm font-medium">{o.baslik}</p>
                  {o.aciklama && <p className="mt-0.5 whitespace-pre-line break-words text-sm text-muted-foreground">{o.aciklama}</p>}
                  {o.yonetici_notu && (
                    <p className="mt-1 break-words text-xs text-sky-200">
                      {t('duyurular.oneri.yoneticiNotu')}: {o.yonetici_notu}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
