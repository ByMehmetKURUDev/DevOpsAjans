import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, ExternalLink, RotateCcw, Youtube } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  KaynakBulunamadi,
  detayiGetir,
  eldekiDetay,
  listedekiOzet,
  type KaynakDetayi,
} from '@/lib/kaynaklar';
import { KAYNAKLAR_SEO, kaynakBasligi, metaAciklama } from '../../../prerender/kaynaklar-seo.js';
import { kaynakYolu } from '../../../prerender/kaynaklar-veri.js';
import { KaynakCagrisi, KaynakKarti, KaynakRozetleri, useIcerikDili, useSayfaBasi } from './ortak';

/**
 * Tek bir kaynağın sayfası: ne işe yarar, nasıl başlanır, resmi bağlantı.
 *
 * Dış bağlantılar yeni sekmede, `rel="noopener noreferrer"` ile açılıyor.
 * YouTube Short gömülmüyor (iframe ~1 MB betik indirir); yalnız bağlantı.
 */

type Durum = 'hazir' | 'yukleniyor' | 'yok' | 'hata';

function tarihMetni(iso: string | null, dil: string): string {
  if (!iso) return '';
  const tarih = new Date(`${iso.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(tarih.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(dil, { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(tarih);
  } catch {
    return iso.slice(0, 10);
  }
}

export default function KaynakDetay() {
  const { t } = useTranslation();
  const { slug = '' } = useParams<{ slug: string }>();
  const dil = useIcerikDili();
  const { pathname } = useLocation();
  const ilk = eldekiDetay(pathname, slug, dil);
  const [detay, setDetay] = useState<KaynakDetayi | null>(ilk ?? null);
  const [durum, setDurum] = useState<Durum>(ilk ? 'hazir' : 'yukleniyor');
  const [deneme, setDeneme] = useState(0);

  useEffect(() => {
    const eldeki = eldekiDetay(pathname, slug, dil);
    if (eldeki) {
      setDetay(eldeki);
      setDurum('hazir');
    } else {
      setDetay((onceki) => (onceki?.kaynak.slug === slug ? onceki : null));
      setDurum((onceki) => (onceki === 'hazir' ? onceki : 'yukleniyor'));
    }
    const kesici = new AbortController();
    detayiGetir(slug, dil, kesici.signal)
      .then((yeni) => {
        setDetay((onceki) => (onceki && JSON.stringify(onceki) === JSON.stringify(yeni) ? onceki : yeni));
        setDurum('hazir');
      })
      .catch((hata) => {
        if (kesici.signal.aborted) return;
        if (hata instanceof KaynakBulunamadi) {
          setDetay(null);
          setDurum('yok');
        } else if (!eldeki) {
          setDurum((onceki) => (onceki === 'hazir' ? onceki : 'hata'));
        }
      });
    return () => kesici.abort();
  }, [slug, dil, pathname, deneme]);

  // Listeden gelindiyse ayrıntı gelene kadar başlık ve özet kartından.
  const onizleme = detay?.kaynak ?? (durum === 'yukleniyor' ? listedekiOzet(slug, dil) : null);
  const k = detay?.kaynak ?? null;
  const seo = KAYNAKLAR_SEO[dil] ?? KAYNAKLAR_SEO.tr;

  useSayfaBasi({
    baslik: onizleme ? kaynakBasligi(onizleme.baslik, dil) : durum === 'yok' ? seo.title : '',
    aciklama: onizleme ? metaAciklama(onizleme.ozet) : seo.description,
    yol: kaynakYolu(dil, slug),
    diller: (d) => kaynakYolu(d, slug),
    noindex: durum === 'yok',
  });

  const paragraflar = useMemo(
    () => (k?.aciklama ?? '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean),
    [k?.aciklama],
  );

  const geriBaglantisi = (
    <Link
      to={kaynakYolu(dil)}
      className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      data-geri
    >
      <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
      {t('kaynaklar.detay.geri')}
    </Link>
  );

  if (durum === 'yok' || (durum === 'hata' && !onizleme)) {
    return (
      <div className="pt-32 pb-24">
        <div className="mx-auto max-w-xl px-4 text-center sm:px-6">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-12" data-kaynak-durum={durum}>
            {durum === 'yok' ? (
              <>
                <h1 className="mb-3 text-2xl font-bold">{t('kaynaklar.detay.bulunamadi')}</h1>
                <p className="mb-6 text-muted-foreground">{t('kaynaklar.detay.bulunamadiAciklama')}</p>
              </>
            ) : (
              <>
                <p className="mb-4 text-muted-foreground">{t('kaynaklar.hata')}</p>
                <Button variant="outline" onClick={() => setDeneme((n) => n + 1)} className="mb-6 gap-2 border-white/20">
                  <RotateCcw className="h-4 w-4" aria-hidden="true" /> {t('kaynaklar.tekrarDene')}
                </Button>
              </>
            )}
            <div>{geriBaglantisi}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pt-32 pb-24">
      <article className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8" data-kaynak-detay={slug}>
        <nav aria-label={t('kaynaklar.detay.kirinti')} className="mb-8">
          {geriBaglantisi}
        </nav>

        <header className="mb-10">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            {k && (
              <span className="rounded-full bg-purple-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-purple-300">
                {k.kategori_adi}
              </span>
            )}
            {onizleme && <KaynakRozetleri k={onizleme} />}
          </div>
          <h1 className="mb-4 text-4xl font-bold leading-tight md:text-5xl">
            {onizleme?.baslik ?? <span className="inline-block h-10 w-2/3 animate-pulse rounded-lg bg-white/10" />}
          </h1>
          {onizleme?.ozet && <p className="text-lg text-muted-foreground">{onizleme.ozet}</p>}

          {k && (
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
                <a href={k.baglanti} target="_blank" rel="noopener noreferrer" data-dis-baglanti>
                  {t(`kaynaklar.detay.git.${k.baglanti_turu}`, t('kaynaklar.detay.git.site'))}
                  <ExternalLink className="ms-2 h-4 w-4" aria-hidden="true" />
                  <span className="sr-only"> {t('kaynaklar.detay.yeniSekme')}</span>
                </a>
              </Button>
              {k.youtube_short && (
                <Button asChild variant="outline" className="h-11 gap-2 border-white/20 !bg-transparent">
                  <a href={k.youtube_short} target="_blank" rel="noopener noreferrer" data-youtube-short>
                    <Youtube className="h-4 w-4 text-red-400" aria-hidden="true" />
                    {t('kaynaklar.detay.short')}
                    <span className="sr-only"> {t('kaynaklar.detay.shortAciklama')}</span>
                  </a>
                </Button>
              )}
            </div>
          )}
        </header>

        {!k && (
          <div className="space-y-3" aria-busy="true" aria-label={t('kaynaklar.detay.yukleniyor')}>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-4 animate-pulse rounded bg-white/10" />
            ))}
          </div>
        )}

        {k && (
          <div className="grid gap-10 lg:grid-cols-3">
            <div className="space-y-10 lg:col-span-2">
              {paragraflar.length > 0 && (
                <section>
                  <h2 className="mb-4 text-xl font-bold">{t('kaynaklar.detay.nedir')}</h2>
                  <div className="space-y-4 leading-relaxed text-muted-foreground">
                    {paragraflar.map((p, i) => (
                      <p key={i} className="whitespace-pre-line">
                        {p}
                      </p>
                    ))}
                  </div>
                </section>
              )}

              {k.adimlar.length > 0 && (
                <section>
                  <h2 className="mb-4 text-xl font-bold">{t('kaynaklar.detay.nasilBaslanir')}</h2>
                  <ol className="space-y-3" data-adimlar>
                    {k.adimlar.map((adim, i) => (
                      <li key={i} className="flex gap-3">
                        <span
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-purple-500/15 text-sm font-semibold text-purple-300"
                          aria-hidden="true"
                        >
                          {i + 1}
                        </span>
                        <span className="min-w-0 break-words pt-1 text-muted-foreground">{adim}</span>
                      </li>
                    ))}
                  </ol>
                </section>
              )}
            </div>

            <aside>
              <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('kaynaklar.detay.bilgiler')}
                </h2>
                <dl className="space-y-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">{t('kaynaklar.detay.kategori')}</dt>
                    <dd className="font-medium">{k.kategori_adi}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">{t('kaynaklar.detay.lisans')}</dt>
                    <dd className="font-medium">{k.lisans || t('kaynaklar.detay.lisansYok')}</dd>
                  </div>
                  {k.dogrulama_tarihi && (
                    <div>
                      <dt className="text-muted-foreground">{t('kaynaklar.detay.dogrulama')}</dt>
                      <dd className="font-medium">
                        <time dateTime={k.dogrulama_tarihi}>{tarihMetni(k.dogrulama_tarihi, dil)}</time>
                      </dd>
                    </div>
                  )}
                </dl>
                {k.etiketler.length > 0 && (
                  <ul className="mt-4 flex flex-wrap gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    {k.etiketler.map((e) => (
                      <li key={e}>#{e}</li>
                    ))}
                  </ul>
                )}
              </div>
            </aside>
          </div>
        )}

        <div className="mt-16">
          <KaynakCagrisi dil={dil} baslik={onizleme?.baslik} slug={slug} />
        </div>

        {detay && detay.ilgili.length > 0 && (
          <section className="mt-16" data-ilgili>
            <h2 className="mb-6 text-2xl font-bold">{t('kaynaklar.detay.ilgili')}</h2>
            <div className="grid gap-6 md:grid-cols-3">
              {detay.ilgili.map((i) => (
                <KaynakKarti key={i.slug} k={i} dil={dil} kategoriAdi={k?.kategori_adi ?? i.kategori} baslikDuzeyi="h3" />
              ))}
            </div>
          </section>
        )}

        <div className="mt-12">{geriBaglantisi}</div>
      </article>
    </div>
  );
}
