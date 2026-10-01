import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Star, Youtube } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { KaynakOzeti } from '@/lib/kaynaklar';
import { KAYNAK_DILLERI, kaynakYolu } from '../../../prerender/kaynaklar-veri.js';
import { absoluteUrl, getLanguage, localizedPath } from '../../../prerender/site.js';

/**
 * Kaynaklar liste ve ayrıntı sayfalarının ortak parçaları.
 *
 * İçerik dili adresten geliyor (`/en/kaynaklar` → en): prerender o dille
 * çizdi ve gömülü veri o dilde; ilk çizim aynı dille yapılırsa ziyaretçi
 * Türkçe içeriğin bir an görünüp değiştiğini görmüyor. Ön eksiz (Türkçe)
 * adreste arayüz dili kullanılıyor — diğer sayfalarla aynı davranış.
 */
export function useIcerikDili(): string {
  const { lang } = useParams<{ lang?: string }>();
  const { i18n } = useTranslation();
  if (lang && KAYNAK_DILLERI.includes(lang)) return lang;
  const arayuz = (i18n.language || 'tr').slice(0, 2);
  return KAYNAK_DILLERI.includes(arayuz) ? arayuz : 'tr';
}

interface SayfaBasi {
  baslik: string;
  aciklama: string;
  /** Kanonik yol (ör. `/en/kaynaklar/superpowers`). */
  yol: string;
  /** Her dil için bu sayfanın yolu; hreflang. Boşsa hreflang basılmaz. */
  diller?: (dil: string) => string;
  noindex?: boolean;
}

function metaYaz(secici: string, oznitelikler: Record<string, string>) {
  let el = document.head.querySelector<HTMLMetaElement>(secici);
  if (!el) {
    el = document.createElement('meta');
    document.head.appendChild(el);
  }
  Object.entries(oznitelikler).forEach(([k, v]) => el!.setAttribute(k, v));
}

/**
 * SPA gezinmesinde <head>. Doğrudan açılışta prerender zaten doğru başlığı
 * basmış oluyor; Layout bu sayfalarda kendi başlık efektini çalıştırmıyor
 * (yalnız tekil blog yazısında olduğu gibi). hreflang bağlantıları Layout'la
 * aynı işaretle (`data-i18n-hreflang`) yazılıyor ki başka sayfaya geçince
 * Layout onları temizlesin.
 */
export function useSayfaBasi({ baslik, aciklama, yol, diller, noindex }: SayfaBasi) {
  const hreflangAnahtari = diller ? KAYNAK_DILLERI.map((d) => diller(d)).join('|') : '';
  useEffect(() => {
    if (typeof document === 'undefined' || !baslik) return;
    document.title = baslik;
    metaYaz('meta[name="description"]', { name: 'description', content: aciklama });
    metaYaz('meta[property="og:title"]', { property: 'og:title', content: baslik });
    metaYaz('meta[property="og:description"]', { property: 'og:description', content: aciklama });
    metaYaz('meta[property="og:url"]', { property: 'og:url', content: absoluteUrl(yol) });
    metaYaz('meta[name="twitter:title"]', { name: 'twitter:title', content: baslik });
    metaYaz('meta[name="twitter:description"]', { name: 'twitter:description', content: aciklama });

    let kanonik = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!kanonik) {
      kanonik = document.createElement('link');
      kanonik.setAttribute('rel', 'canonical');
      document.head.appendChild(kanonik);
    }
    kanonik.setAttribute('href', absoluteUrl(yol));

    document.head.querySelectorAll('meta[data-kaynak-robots]').forEach((el) => el.remove());
    if (noindex) {
      const robots = document.createElement('meta');
      robots.setAttribute('name', 'robots');
      robots.setAttribute('content', 'noindex, follow');
      robots.setAttribute('data-kaynak-robots', 'true');
      document.head.appendChild(robots);
    }

    document.head.querySelectorAll('link[data-i18n-hreflang="true"]').forEach((el) => el.remove());
    if (hreflangAnahtari && !noindex) {
      const yollar = hreflangAnahtari.split('|');
      const ekle = (hreflang: string, href: string) => {
        const link = document.createElement('link');
        link.setAttribute('rel', 'alternate');
        link.setAttribute('hreflang', hreflang);
        link.setAttribute('data-i18n-hreflang', 'true');
        link.setAttribute('href', absoluteUrl(href));
        document.head.appendChild(link);
      };
      KAYNAK_DILLERI.forEach((d, i) => ekle(getLanguage(d).htmlLang, yollar[i]));
      ekle('x-default', yollar[0]);
    }
    return () => {
      document.head.querySelectorAll('meta[data-kaynak-robots]').forEach((el) => el.remove());
    };
  }, [baslik, aciklama, yol, noindex, hreflangAnahtari]);
}

/** Ücretsiz / açık kaynak rozetleri. */
export function KaynakRozetleri({ k }: { k: Pick<KaynakOzeti, 'ucretsiz' | 'acik_kaynak'> }) {
  const { t } = useTranslation();
  if (!k.ucretsiz && !k.acik_kaynak) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {k.ucretsiz && (
        <span className="rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
          {t('kaynaklar.ucretsiz')}
        </span>
      )}
      {k.acik_kaynak && (
        <span className="rounded-md border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-semibold text-sky-300">
          {t('kaynaklar.acikKaynak')}
        </span>
      )}
    </div>
  );
}

/** Liste ve "ilgili kaynaklar" kartı. Kartın tamamı ayrıntı sayfasına bağlantı. */
export function KaynakKarti({
  k,
  dil,
  kategoriAdi,
  baslikDuzeyi = 'h2',
}: {
  k: KaynakOzeti;
  dil: string;
  kategoriAdi: string;
  baslikDuzeyi?: 'h2' | 'h3';
}) {
  const { t } = useTranslation();
  const Baslik = baslikDuzeyi;
  return (
    <Link
      to={kaynakYolu(dil, k.slug)}
      data-kaynak={k.slug}
      className={`cam-kart${k.one_cikan ? ' cam-one' : ''} group flex h-full flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition-colors hover:border-purple-500/40`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="truncate rounded-full bg-purple-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-purple-300">
          {kategoriAdi}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {k.youtube_short && (
            <Youtube className="h-4 w-4 text-red-400" role="img" aria-label={t('kaynaklar.youtubeVar')} />
          )}
          {k.one_cikan && (
            <Star className="h-4 w-4 fill-amber-400 text-amber-400" role="img" aria-label={t('kaynaklar.oneCikan')} />
          )}
        </span>
      </div>
      <Baslik className="mb-2 text-lg font-bold leading-snug">{k.baslik}</Baslik>
      <p className="mb-4 flex-1 text-sm leading-relaxed text-muted-foreground">{k.ozet}</p>
      <KaynakRozetleri k={k} />
      {k.etiketler.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
          {k.etiketler.slice(0, 4).map((e) => (
            <li key={e}>#{e}</li>
          ))}
        </ul>
      )}
    </Link>
  );
}

/** "Bu araçları işinize kuralım" — iletişim formuna konu ve kaynak bilgisiyle gider. */
export function KaynakCagrisi({ dil, baslik, slug }: { dil: string; baslik?: string; slug?: string }) {
  const { t } = useTranslation();
  const konu = baslik ? t('kaynaklar.cta.konu', { baslik }) : t('kaynaklar.cta.konuGenel');
  return (
    <section
      className="cam-kart cam-mor rounded-2xl border border-purple-500/30 bg-purple-500/10 p-8 text-center"
      data-kaynak-cagrisi
    >
      <h2 className="mb-3 text-2xl font-bold">{t('kaynaklar.cta.baslik')}</h2>
      <p className="mx-auto mb-6 max-w-2xl text-muted-foreground">{t('kaynaklar.cta.metin')}</p>
      <Button asChild className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
        <Link to={localizedPath(dil, 'contact')} state={{ kaynak: 'kaynaklar', konu, kaynakKonu: slug || '' }}>
          {t('kaynaklar.cta.dugme')}
        </Link>
      </Button>
    </section>
  );
}

/** Panelden girilmiş SEO metni (Layout'un yazdığı ayar önbelleğinden); yoksa varsayılan. */
export function paneldenSeo(anahtar: string, dil: string, yedek: string): string {
  try {
    const ham = typeof localStorage !== 'undefined' ? localStorage.getItem('mk_site_settings_v2') : null;
    const ayarlar = ham ? (JSON.parse(ham) as Record<string, string>) : null;
    const deger = ayarlar?.[`${anahtar}__${dil}`]?.trim() || ayarlar?.[anahtar]?.trim();
    return deger || yedek;
  } catch {
    return yedek;
  }
}
