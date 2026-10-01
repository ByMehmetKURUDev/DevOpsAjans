import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarSync, Code2, Copy, Download, Link2, QrCode, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, DIS_DUGME, KART, SECIM, kopyala } from '@/components/randevu/ortak';
import { blobIndir, hataMetni, type Meta, type RandevuApi, type Sayfa, type Tur } from '@/lib/randevu';

/** Faz 5R — paylaş: bağlantılar, gömme kodu (satır içi / açılır pencere), QR, ICS besleme. */

export default function Paylas({ api, meta, sayfa, onSayfa }: { api: RandevuApi; meta: Meta; sayfa: Sayfa; onSayfa: (s: Sayfa) => void }) {
  const { t } = useTranslation();
  const [turler, setTurler] = useState<Tur[]>([]);
  const [tur, setTur] = useState('');
  const [bicim, setBicim] = useState<'satir' | 'pencere'>('satir');
  const [qr, setQr] = useState<string | null>(null);
  const origin = meta.widget_adresi.replace(/\/randevu-widget\.js$/, '');

  useEffect(() => {
    api
      .turler(sayfa.id)
      .then((l) => setTurler(l.items.filter((x) => x.aktif)))
      .catch(() => setTurler([]));
  }, [api, sayfa.id]);

  useEffect(() => {
    let adres: string | null = null;
    let iptal = false;
    api
      .qrBlob(sayfa.id, 'svg', tur || undefined)
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
  }, [api, sayfa.id, sayfa.slug, tur]);

  const hedef = tur ? `${sayfa.slug}/${tur}` : sayfa.slug;
  const adres = `${sayfa.adres_url}${tur ? `/${tur}` : ''}`;
  const kod =
    bicim === 'satir'
      ? `<div data-mk-randevu="${hedef}"></div>\n<script src="${meta.widget_adresi}" async></script>`
      : `<button type="button" data-mk-randevu-ac="${hedef}">${t('randevu.paylas.dugmeMetni')}</button>\n<script src="${meta.widget_adresi}" async></script>`;

  const qrIndir = async (b: 'png' | 'svg') => {
    try {
      blobIndir(await api.qrBlob(sayfa.id, b, tur || undefined), `randevu-${sayfa.slug}${tur ? `-${tur}` : ''}-qr.${b}`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="grid gap-4" data-testid="randevu-paylas">
      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <Link2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('randevu.paylas.baglantilar')}
        </h3>
        <Alan etiket={t('randevu.paylas.neyi')}>
          <select className={SECIM} value={tur} onChange={(e) => setTur(e.target.value)} data-testid="randevu-paylas-tur">
            <option value="">{t('randevu.paylas.butunSayfa')}</option>
            {turler.map((x) => (
              <option key={x.id} value={x.slug}>
                {x.ad}
              </option>
            ))}
          </select>
        </Alan>
        <div className="mt-3 flex items-center gap-2">
          <Input value={adres} readOnly dir="ltr" className="font-mono text-xs" aria-label={t('randevu.paylas.baglanti')} />
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => kopyala(adres, t('randevu.kopyalandi'), t('randevu.kopyalanamadi'))}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('randevu.kopyala')}
          </Button>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 flex items-center gap-2 text-base font-semibold">
          <Code2 className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('randevu.paylas.gomme')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('randevu.paylas.gommeAciklama')}</p>
        <div className="mb-2 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" name="gomme" className="accent-purple-500" checked={bicim === 'satir'} onChange={() => setBicim('satir')} />
            {t('randevu.paylas.satirIci')}
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="gomme" className="accent-purple-500" checked={bicim === 'pencere'} onChange={() => setBicim('pencere')} />
            {t('randevu.paylas.pencere')}
          </label>
        </div>
        <textarea readOnly value={kod} dir="ltr" className="min-h-[88px] w-full rounded-md border border-white/10 bg-black/40 p-3 font-mono text-xs text-white" data-testid="randevu-gomme-kodu" />
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => kopyala(kod, t('randevu.kopyalandi'), t('randevu.kopyalanamadi'))}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('randevu.paylas.koduKopyala')}
          </Button>
        </div>
        <p className="mt-1 text-xs text-muted-foreground" dir="auto">
          {t('randevu.paylas.gommeIpucu', { site: origin.replace(/^https?:\/\//, '') })}
        </p>
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-3 flex items-center gap-2 text-base font-semibold">
          <QrCode className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('randevu.paylas.qr')}
        </h3>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-40 w-40 items-center justify-center rounded-xl bg-white p-2">
            {qr ? <img src={qr} alt={t('randevu.paylas.qrAlt')} width={144} height={144} data-testid="randevu-qr" /> : <QrCode className="h-10 w-10 text-zinc-400" aria-hidden="true" />}
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
            <p className="max-w-xs text-xs text-muted-foreground">{t('randevu.paylas.qrIpucu')}</p>
          </div>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-1 flex items-center gap-2 text-base font-semibold">
          <CalendarSync className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {t('randevu.paylas.besleme')}
        </h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('randevu.paylas.beslemeAciklama')}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Input value={sayfa.besleme_adresi} readOnly dir="ltr" className="min-w-0 flex-1 font-mono text-xs" aria-label={t('randevu.paylas.besleme')} data-testid="randevu-besleme" />
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => kopyala(sayfa.besleme_adresi, t('randevu.kopyalandi'), t('randevu.kopyalanamadi'))}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('randevu.kopyala')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className={DIS_DUGME}
            onClick={async () => {
              if (!window.confirm(t('randevu.paylas.yenileOnay'))) return;
              try {
                onSayfa(await api.beslemeYenile(sayfa.id));
                toast.success(t('randevu.paylas.yenilendi'));
              } catch (e) {
                toast.error(hataMetni(t, e));
              }
            }}
            data-testid="randevu-besleme-yenile"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t('randevu.paylas.yenile')}
          </Button>
        </div>
        <ul className="mt-3 list-disc space-y-1 ps-5 text-xs text-muted-foreground">
          <li>{t('randevu.paylas.google')}</li>
          <li>{t('randevu.paylas.apple')}</li>
          <li>{t('randevu.paylas.gizli')}</li>
        </ul>
      </section>
    </div>
  );
}
