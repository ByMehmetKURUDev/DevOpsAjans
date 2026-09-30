import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Activity, AlertCircle, CheckCircle2, CircleHelp, Home, Loader2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import UptimeGrafigi from '@/components/UptimeGrafigi';
import { Button } from '@/components/ui/button';
import { acikDurumGetir, tarihBicimle, yuzdeBicimle, type AcikDurum } from '@/lib/siteBakim';

/**
 * Herkese açık durum sayfası: `/durum/<slug>` (ve `/<dil>/durum/<slug>`).
 *
 * Müşteri açarsa var; oturum istemiyor. Prerender edilmiyor (her sayfa bir
 * müşteriye ait, dinamik). Varsayılan noindex — müşteri "arama motorlarında
 * görünsün" derse robots etiketi eklenmiyor. Uç zaten yalnız
 * toplulaştırılmış veri veriyor (adres, e-posta, hata ayrıntısı yok).
 */
export default function DurumSayfasi() {
  const { slug } = useParams<{ slug: string }>();
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<AcikDurum | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  useEffect(() => {
    let iptal = false;
    if (!slug) return;
    acikDurumGetir(slug)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch(() => {
        if (!iptal) setHata(true);
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [slug]);

  // Varsayılan noindex; yalnız müşteri açıkça izin verdiyse kaldırılıyor.
  const index = Boolean(veri?.index);
  useEffect(() => {
    if (index) return;
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => etiket.remove();
  }, [index]);

  useEffect(() => {
    if (!veri?.ad) return;
    const onceki = document.title;
    document.title = t('siteBakim.sayfa.baslik', { ad: veri.ad });
    return () => {
      document.title = onceki;
    };
  }, [veri?.ad, t]);

  let icerik;
  if (yukleniyor) {
    icerik = (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  } else if (hata || !veri) {
    icerik = (
      <div
        className="cam-kart mx-auto max-w-xl rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center sm:p-8"
        data-testid="durum-bulunamadi"
      >
        <AlertCircle className="mx-auto mb-3 h-10 w-10 text-amber-300" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t('siteBakim.sayfa.bulunamadi')}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t('siteBakim.sayfa.bulunamadiAciklama')}</p>
        <Button asChild variant="outline" className="mt-6 !bg-transparent">
          <Link to="/">
            <Home className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('siteBakim.sayfa.anaSayfa')}
          </Link>
        </Button>
      </div>
    );
  } else {
    const guncel = veri.guncel ?? 'bilinmiyor';
    const ust =
      guncel === 'calisiyor'
        ? { ikon: CheckCircle2, renk: 'text-emerald-300 border-emerald-400/30 bg-emerald-500/10', metin: t('siteBakim.sayfa.tumSistemler') }
        : guncel === 'kesinti'
          ? { ikon: XCircle, renk: 'text-red-300 border-red-400/30 bg-red-500/10', metin: t('siteBakim.sayfa.kesintiVar') }
          : { ikon: CircleHelp, renk: 'text-muted-foreground border-white/10 bg-white/[0.03]', metin: t('siteBakim.sayfa.bilinmiyor') };
    const UstIkon = ust.ikon;
    icerik = (
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="break-words text-2xl font-bold sm:text-3xl">{t('siteBakim.sayfa.baslik', { ad: veri.ad })}</h1>
        <div className={`flex items-center gap-3 rounded-2xl border p-4 ${ust.renk}`} data-testid="durum-guncel">
          <UstIkon className="h-6 w-6 shrink-0" aria-hidden="true" />
          <span className="font-semibold">{ust.metin}</span>
        </div>

        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="flex items-center gap-2 font-semibold">
              <Activity className="h-4 w-4" aria-hidden="true" />
              {t('siteBakim.sayfa.son90')}
            </h2>
            <span className="text-sm text-muted-foreground">
              {t('siteBakim.sayfa.erisilebilirlik')}:{' '}
              <span className="font-semibold text-foreground" data-testid="durum-oran-90">
                {yuzdeBicimle(veri.oran_90g ?? null, dil)}
              </span>
            </span>
          </div>
          <UptimeGrafigi gunler={veri.gunler ?? []} ortalama={veri.oran_90g ?? null} yukseklik="h-10" testId="durum-grafik" />
          <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
            {(
              [
                ['son24', veri.oran_24s],
                ['son7', veri.oran_7g],
                ['son30', veri.oran_30g],
              ] as const
            ).map(([anahtar, oran]) => (
              <div key={anahtar} className="rounded-xl bg-white/[0.03] p-2">
                <dt className="text-[11px] text-muted-foreground">{t(`siteBakim.uptime.${anahtar}`)}</dt>
                <dd className="font-semibold">{yuzdeBicimle(oran ?? null, dil)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="mb-3 font-semibold">{t('siteBakim.sayfa.sonKesintiler')}</h2>
          {veri.kesintiler && veri.kesintiler.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {veri.kesintiler.map((k, i) => (
                <li key={`${k.baslangic}-${i}`} className="flex flex-wrap justify-between gap-2 rounded-lg bg-white/[0.03] px-3 py-2">
                  <span>{tarihBicimle(k.baslangic, dil, true)}</span>
                  <span className="text-muted-foreground">
                    {k.bitis ? t('siteBakim.sayfa.sure', { sayi: k.sure_dk ?? 0 }) : t('siteBakim.sayfa.devamEdiyor')}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t('siteBakim.sayfa.kesintiYok')}</p>
          )}
        </section>

        <p className="text-center text-xs text-muted-foreground">
          {veri.son_kontrol && `${t('siteBakim.sayfa.guncelleme', { zaman: tarihBicimle(veri.son_kontrol, dil, true) })} · `}
          {t('siteBakim.sayfa.altBilgi')}
        </p>
      </div>
    );
  }

  return (
    <div className="pt-28 pb-20 sm:pt-32" data-testid="durum-sayfasi">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">{icerik}</div>
    </div>
  );
}
