import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Bot, Braces, Gauge, Heading, Lock, Network, Route, Share2, ShieldCheck, Tags, TextSearch, Wrench } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SEO_ARACLARI, seoAracYolu } from '../../../prerender/seo-araclari-veri.js';
import { localizedPath } from '../../../prerender/site.js';

/**
 * Ücretsiz SEO araçları sayfalarının (dizin + araç) ortak parçaları (Faz 4S).
 *
 * İçerik dili ve <head> yönetimi Kaynaklar'daki yardımcılarla aynı
 * (`../kaynaklar/ortak`): dil adresten geliyor; SPA gezinmesinde başlık,
 * açıklama, kanonik adres ve hreflang sayfanın kendisinden yazılıyor.
 */
export { useIcerikDili as useAracDili, useSayfaBasi, paneldenSeo } from '../kaynaklar/ortak';

export type AracTanimi = (typeof SEO_ARACLARI)[number];

const IKONLAR: Record<string, LucideIcon> = { Tags, Share2, Braces, Bot, Network, Route, ShieldCheck, Lock, Heading, TextSearch };

export function AracIkonu({ ad, className = 'h-5 w-5' }: { ad: string; className?: string }) {
  const Ikon = IKONLAR[ad] ?? Wrench;
  return <Ikon className={className} aria-hidden="true" />;
}

/** `t(..., { returnObjects: true })` dizi döndürmezse boş dizi. */
export function dizi<T>(deger: unknown): T[] {
  return Array.isArray(deger) ? (deger as T[]) : [];
}

/** Araç kartı (dizin ve "diğer araçlar"). Kartın tamamı araç sayfasına bağlantı. */
export function AracKarti({
  a,
  dil,
  baslikDuzeyi = 'h2',
  durum,
}: {
  a: AracTanimi;
  dil: string;
  baslikDuzeyi?: 'h2' | 'h3';
  /** Araçtan araca geçerken girilen adres taşınıyor (adres çubuğuna yazılmadan, router state). */
  durum?: { url?: string };
}) {
  const { t } = useTranslation();
  const Baslik = baslikDuzeyi;
  return (
    <Link
      to={seoAracYolu(dil, a.slug)}
      state={durum}
      data-seo-arac={a.slug}
      className="cam-kart group flex h-full flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition-colors hover:border-purple-500/40"
    >
      <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-purple-500/15 text-purple-300">
        <AracIkonu ad={a.ikon} />
      </span>
      <Baslik className="mb-2 text-lg font-bold leading-snug">{t(`seoAraclari.arac.${a.anahtar}.ad`)}</Baslik>
      <p className="mb-4 flex-1 text-sm leading-relaxed text-muted-foreground">{t(`seoAraclari.arac.${a.anahtar}.kisa`)}</p>
      <span className="inline-flex items-center gap-1 text-sm font-semibold text-purple-300">
        {t('seoAraclari.dizin.araciAc')}
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 rtl:rotate-180" aria-hidden="true" />
      </span>
    </Link>
  );
}

/** "Sitenin tamamını puanlayalım" — ücretsiz Site Analiz Raporu'na bağlantı. */
export function SiteAnaliziCagrisi({ dil }: { dil: string }) {
  const { t } = useTranslation();
  return (
    <section className="cam-kart cam-mor rounded-2xl border border-purple-500/30 bg-purple-500/10 p-8 text-center" data-site-analizi-cagrisi>
      <Gauge className="mx-auto mb-3 h-8 w-8 text-purple-300" aria-hidden="true" />
      <h2 className="mb-3 text-2xl font-bold">{t('seoAraclari.sayfa.siteAnaliziBaslik')}</h2>
      <p className="mx-auto mb-6 max-w-2xl text-muted-foreground">{t('seoAraclari.sayfa.siteAnaliziMetin')}</p>
      <Button asChild className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
        <Link to={localizedPath(dil, 'siteAnalysis')}>{t('seoAraclari.sayfa.siteAnaliziDugme')}</Link>
      </Button>
    </section>
  );
}

/** SSS — `<details>` (tarayıcının kendi aç/kapa davranışı). FAQPage JSON-LD aynı metinden üretiliyor. */
export function Sss({ sorular, baslik }: { sorular: { s: string; c: string }[]; baslik: string }) {
  if (!sorular.length) return null;
  return (
    <section data-sss>
      <h2 className="mb-4 text-xl font-bold">{baslik}</h2>
      <div className="space-y-3">
        {sorular.map((s) => (
          <details key={s.s} className="group rounded-xl border border-white/10 bg-white/[0.02] px-5 py-4">
            <summary className="cursor-pointer list-none font-semibold marker:hidden">
              <span className="me-2 inline-block text-purple-300 transition-transform group-open:rotate-45" aria-hidden="true">
                +
              </span>
              {s.s}
            </summary>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{s.c}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
