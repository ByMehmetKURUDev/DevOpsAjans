import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Code2, Copy, Download, ExternalLink, Link2, ListChecks, Loader2, QrCode } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, kopyala } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { blobIndir, hataMetni, type Etkinlik, type EtkinlikApi, type ListeAyari, type Meta } from '@/lib/etkinlik';

/**
 * Faz 6E — paylaş: herkese açık bağlantı, QR (PNG/SVG), gömme kodu (satır içi / açılır pencere;
 * `public/etkinlik-widget.js`) ve hesabın etkinlik listesi sayfası (`/etkinlikler/<slug>`).
 */
export default function Paylas({ api, meta, etkinlik }: { api: EtkinlikApi; meta: Meta; etkinlik: Etkinlik }) {
  const { t } = useTranslation();
  const [bicim, setBicim] = useState<'satir' | 'pencere'>('satir');
  const [qr, setQr] = useState<string | null>(null);
  const [liste, setListe] = useState<ListeAyari | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const hesap = meta.yonetici ? etkinlik.hesap_email : null;
  const yayinda = etkinlik.durum === 'yayinda';

  useEffect(() => {
    let adres: string | null = null;
    let iptal = false;
    api
      .qrBlob(etkinlik.id, 'svg')
      .then((b) => {
        if (iptal) return;
        adres = URL.createObjectURL(b);
        setQr(adres);
      })
      .catch(() => setQr(null));
    return () => {
      iptal = true;
      if (adres) URL.revokeObjectURL(adres);
    };
  }, [api, etkinlik.id, etkinlik.slug]);

  useEffect(() => {
    api
      .listeAyari(hesap)
      .then(setListe)
      .catch(() => setListe(null));
  }, [api, hesap]);

  const kod =
    bicim === 'satir'
      ? `<div data-mk-etkinlik="${etkinlik.slug}"></div>\n<script src="${meta.widget_adresi}" async></script>`
      : `<button type="button" data-mk-etkinlik-ac="${etkinlik.slug}">${t('etkinlik.paylas.dugmeMetni')}</button>\n<script src="${meta.widget_adresi}" async></script>`;

  const qrIndir = async (b: 'png' | 'svg') => {
    try {
      blobIndir(await api.qrBlob(etkinlik.id, b), `etkinlik-${etkinlik.slug}-qr.${b}`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const listeKaydet = async () => {
    if (!liste) return;
    setMesgul(true);
    try {
      setListe(await api.listeAyariYaz({ baslik: liste.baslik, slug: liste.slug || undefined, aciklama: liste.aciklama, acik: liste.acik }, hesap));
      toast.success(t('etkinlik.ayar.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="grid gap-4" data-testid="etkinlik-paylas">
      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <Link2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('etkinlik.paylas.baglanti')}
        </h3>
        {!yayinda && <p className="mb-3 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100">{t('etkinlik.paylas.yayindaDegil')}</p>}
        <div className="flex items-center gap-2">
          <Input value={etkinlik.adres_url} readOnly dir="ltr" className="font-mono text-xs" aria-label={t('etkinlik.paylas.baglanti')} data-testid="etkinlik-paylas-adres" />
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void kopyala(etkinlik.adres_url, t('etkinlik.kopyalandi'), t('etkinlik.kopyalanamadi'))}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.kopyala')}
          </Button>
          <a href={etkinlik.adres_url} target="_blank" rel="noopener" className="inline-flex h-9 shrink-0 items-center rounded-md border border-white/20 px-2" aria-label={t('etkinlik.ac')}>
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
          </a>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <QrCode className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('etkinlik.paylas.qr')}
        </h3>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-40 w-40 items-center justify-center rounded-xl bg-white p-2">
            {qr ? <img src={qr} alt={t('etkinlik.paylas.qrAlt')} width={144} height={144} data-testid="etkinlik-qr" /> : <QrCode className="h-10 w-10 text-zinc-400" aria-hidden="true" />}
          </div>
          <div className="flex flex-col gap-2">
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void qrIndir('png')}>
              <Download className="h-4 w-4" aria-hidden="true" />
              PNG
            </Button>
            <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void qrIndir('svg')}>
              <Download className="h-4 w-4" aria-hidden="true" />
              SVG
            </Button>
            <p className="max-w-xs text-xs text-muted-foreground">{t('etkinlik.paylas.qrIpucu')}</p>
          </div>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 flex items-center gap-2 text-base font-semibold">
          <Code2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('etkinlik.paylas.gomme')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.paylas.gommeAciklama')}</p>
        <div className="mb-2 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" name="etkinlik-gomme" className="accent-purple-500" checked={bicim === 'satir'} onChange={() => setBicim('satir')} />
            {t('etkinlik.paylas.satirIci')}
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="etkinlik-gomme" className="accent-purple-500" checked={bicim === 'pencere'} onChange={() => setBicim('pencere')} />
            {t('etkinlik.paylas.pencere')}
          </label>
        </div>
        <textarea readOnly value={kod} dir="ltr" className="min-h-[88px] w-full rounded-md border border-white/10 bg-black/40 p-3 font-mono text-xs text-white" data-testid="etkinlik-gomme-kodu" />
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void kopyala(kod, t('etkinlik.kopyalandi'), t('etkinlik.kopyalanamadi'))}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('etkinlik.paylas.koduKopyala')}
          </Button>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`} data-testid="etkinlik-liste-ayari">
        <h3 className="mb-1 flex items-center gap-2 text-base font-semibold">
          <ListChecks className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('etkinlik.paylas.liste')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('etkinlik.paylas.listeAciklama')}</p>
        {liste && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Alan etiket={t('etkinlik.paylas.listeBaslik')}>
              <Input value={liste.baslik} maxLength={160} onChange={(e) => setListe({ ...liste, baslik: e.target.value })} data-testid="etkinlik-liste-baslik" />
            </Alan>
            <Alan etiket={t('etkinlik.alan.slug')}>
              <Input value={liste.slug} maxLength={50} dir="ltr" onChange={(e) => setListe({ ...liste, slug: e.target.value.toLowerCase() })} />
            </Alan>
            <Alan etiket={t('etkinlik.alan.aciklama')} className="sm:col-span-2">
              <textarea className={METIN_ALANI} rows={2} maxLength={1000} value={liste.aciklama} onChange={(e) => setListe({ ...liste, aciklama: e.target.value })} />
            </Alan>
            <div className="sm:col-span-2">
              <Anahtar acik={liste.acik} onDegis={(v) => setListe({ ...liste, acik: v })} etiket={t('etkinlik.paylas.listeAcik')} testid="etkinlik-liste-acik" />
            </div>
            <p className="text-xs text-muted-foreground sm:col-span-2">{t('etkinlik.paylas.listeIpucu')}</p>
            <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
              <Button onClick={() => void listeKaydet()} disabled={mesgul || !liste.baslik.trim()} className="gap-1.5" data-testid="etkinlik-liste-kaydet">
                {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('etkinlik.kaydet')}
              </Button>
              {liste.adres_url && liste.acik && (
                <a href={liste.adres_url} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-sm text-purple-300 hover:underline" dir="ltr">
                  {liste.adres_url}
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                </a>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
