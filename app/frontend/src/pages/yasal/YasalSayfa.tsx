import { Fragment, useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Cookie, FileText, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { rizayiSifirla } from '@/lib/riza';
import { useSiteSettings, type SettingsMap } from '@/lib/siteSettings';
import { useYasalBilgiler, type YasalBilgiler } from '@/lib/yasal';
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_CODES,
  PAGE_SEO_KEYS,
  PREFIXED_LANGUAGES,
  YASAL_SAYFALAR,
  absoluteUrl,
  getLanguage,
  localizedPath,
} from '../../../prerender/site.js';
import { yasalSeo } from '../../../prerender/yasal-seo.js';
import { tarihBicimle } from '../../../prerender/yasal-veri.js';

/**
 * Yasal sayfalar (Faz 3Y): Gizlilik Politikası ve KVKK Aydınlatma Metni,
 * Kullanım Koşulları, Çerez Politikası. Üçü tek bileşen, metinler
 * `src/i18n/ek/yasal/<dil>.json` ek paketinde (7 dil; Türkçe asıl).
 *
 * Metin biçimi (ek paket):
 *   bolumler: [{ id, baslik, bloklar: Blok[] }]
 *   Blok: "paragraf" | { p, kosul? } | { liste: (string | { metin, kosul })[] }
 *       | { tablo: { basliklar, satirlar } } | { ozel: veriSorumlusu | limitedUse | cerezTercihi }
 *   Metin içinde: **kalın**, [etiket](hedef) — hedef `sayfa:<anahtar>#çapa`, `mailto:`,
 *   `https://`; yer tutucular {{unvan}} {{eposta}} {{adres}} {{kep}}.
 *   `kosul` doluysa o bilgi panelde boşken satır HİÇ çizilmez (ör. adres).
 *
 * Veri sorumlusu bilgileri koda gömülü değil: yönetici paneli › Site Ayarları
 * › Yasal bilgiler (`src/lib/yasal.ts`, `prerender/yasal-veri.js`).
 */

export type YasalSayfaAnahtari = 'gizlilik' | 'kullanimKosullari' | 'cerezPolitikasi';

type Kosul = 'adres' | 'kep' | 'vkn' | 'mersis';
type Madde = string | { metin: string; kosul?: Kosul };
type Blok =
  | string
  | { p: string; kosul?: Kosul }
  | { liste: Madde[] }
  | { tablo: { basliklar: string[]; satirlar: string[][] } }
  | { ozel: 'veriSorumlusu' | 'limitedUse' | 'cerezTercihi' };
interface Bolum {
  id: string;
  baslik: string;
  bloklar: Blok[];
}
interface Belge {
  baslik: string;
  ozet: string;
  limitedUse?: string;
  bolumler: Bolum[];
}

const LIMITED_USE_EN =
  "mehmetkuru.dev's use and transfer to any other app of information received from Google APIs will adhere to Google API Services User Data Policy, including the Limited Use requirements.";
const POLITIKA_ADI = 'Google API Services User Data Policy';
const POLITIKA_ADRESI = 'https://developers.google.com/terms/api-services-user-data-policy';

const IKON: Record<YasalSayfaAnahtari, typeof ShieldCheck> = {
  gizlilik: ShieldCheck,
  kullanimKosullari: FileText,
  cerezPolitikasi: Cookie,
};

/** Etkin dildeki belge; yoksa Türkçe (ek paket henüz inmediyse undefined). */
function belgeyiOku(i18n: { language: string; getResource: (l: string, ns: string, k: string) => unknown }, sayfa: string) {
  const oku = (dil: string) => i18n.getResource(dil, 'translation', `yasal.${sayfa}`) as Belge | undefined;
  const belge = oku(i18n.language) ?? oku(DEFAULT_LANGUAGE);
  return belge && Array.isArray(belge.bolumler) ? belge : undefined;
}

function doldur(metin: string, b: YasalBilgiler): string {
  return metin.replace(/\{\{(\w+)\}\}/g, (_tam, ad: string) => String((b as Record<string, string>)[ad] ?? ''));
}

/** `**kalın**` ve `[etiket](hedef)` → React düğümleri; yer tutucular parça parça dolduruluyor. */
function Metin({ metin, b, dil }: { metin: string; b: YasalBilgiler; dil: string }) {
  const desen = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g;
  const parcalar: ReactNode[] = [];
  let son = 0;
  let m: RegExpExecArray | null;
  while ((m = desen.exec(metin))) {
    if (m.index > son) parcalar.push(doldur(metin.slice(son, m.index), b));
    if (m[1] !== undefined) {
      parcalar.push(<Baglanti key={m.index} hedef={doldur(m[2], b)} etiket={doldur(m[1], b)} dil={dil} />);
    } else {
      parcalar.push(
        <strong key={m.index} className="font-semibold text-foreground">
          {doldur(m[3], b)}
        </strong>,
      );
    }
    son = desen.lastIndex;
  }
  if (son < metin.length) parcalar.push(doldur(metin.slice(son), b));
  return <>{parcalar}</>;
}

const BAGLANTI_SINIFI = 'text-primary underline underline-offset-2 hover:text-foreground break-words';

function Baglanti({ hedef, etiket, dil }: { hedef: string; etiket: string; dil: string }) {
  if (hedef.startsWith('sayfa:')) {
    const [anahtar, capa] = hedef.slice('sayfa:'.length).split('#');
    return (
      <Link to={`${localizedPath(dil, anahtar)}${capa ? `#${capa}` : ''}`} className={BAGLANTI_SINIFI}>
        {etiket}
      </Link>
    );
  }
  if (hedef.startsWith('https://')) {
    return (
      <a href={hedef} target="_blank" rel="noopener noreferrer" className={BAGLANTI_SINIFI}>
        {etiket}
      </a>
    );
  }
  // mailto: ve sayfa içi çapa. E-posta adresi RTL'de de soldan sağa okunmalı.
  return (
    <a href={hedef} className={BAGLANTI_SINIFI} dir={hedef.startsWith('mailto:') ? 'ltr' : undefined}>
      {etiket}
    </a>
  );
}

function VeriSorumlusu({ b }: { b: YasalBilgiler }) {
  const { t } = useTranslation();
  const satirlar: { ad: string; deger: ReactNode; ltr?: boolean }[] = [
    { ad: 'unvan', deger: b.unvan },
    {
      ad: 'eposta',
      deger: (
        <a href={`mailto:${b.eposta}`} className={BAGLANTI_SINIFI}>
          {b.eposta}
        </a>
      ),
      ltr: true,
    },
    ...(b.adres ? [{ ad: 'adres', deger: b.adres }] : []),
    ...(b.kep ? [{ ad: 'kep', deger: b.kep, ltr: true }] : []),
    ...(b.vkn ? [{ ad: 'vkn', deger: b.vkn, ltr: true }] : []),
    ...(b.mersis ? [{ ad: 'mersis', deger: b.mersis, ltr: true }] : []),
    {
      ad: 'site',
      deger: (
        <a href="https://mehmetkuru.dev/" className={BAGLANTI_SINIFI}>
          mehmetkuru.dev
        </a>
      ),
      ltr: true,
    },
  ];
  return (
    <dl
      className="grid gap-x-6 gap-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-5 text-sm sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]"
      data-veri-sorumlusu
    >
      {satirlar.map((s) => (
        <Fragment key={s.ad}>
          <dt className="text-xs font-semibold uppercase tracking-wider text-muted-foreground sm:pt-0.5">
            {t(`yasal.ortak.alanlar.${s.ad}`)}
          </dt>
          <dd className="min-w-0 break-words text-foreground" data-yasal-alan={s.ad}>
            {s.ltr ? <bdi dir="ltr">{s.deger}</bdi> : s.deger}
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}

function LimitedUse({ metin, dil }: { metin?: string; dil: string }) {
  const { t } = useTranslation();
  return (
    <blockquote
      className="space-y-3 rounded-xl border border-sky-400/30 bg-sky-500/10 p-5 text-sm leading-relaxed"
      data-limited-use
    >
      {dil === 'en' || !metin ? (
        <p lang="en" dir="ltr" className="font-medium text-foreground">
          {LIMITED_USE_EN}
        </p>
      ) : (
        <>
          <p className="font-medium text-foreground">{metin}</p>
          <p lang="en" dir="ltr" className="text-muted-foreground">
            <span className="font-semibold">{t('yasal.ortak.ozgunMetin')}:</span> {LIMITED_USE_EN}
          </p>
        </>
      )}
      <p dir="ltr" lang="en">
        <a href={POLITIKA_ADRESI} target="_blank" rel="noopener noreferrer" className={BAGLANTI_SINIFI}>
          {POLITIKA_ADI}
        </a>
      </p>
    </blockquote>
  );
}

function CerezTercihi() {
  const { t } = useTranslation();
  const [sifirlandi, setSifirlandi] = useState(false);
  return (
    <div className="flex flex-col items-start gap-3" data-cerez-tercihi>
      <Button
        type="button"
        onClick={() => {
          rizayiSifirla();
          setSifirlandi(true);
        }}
        className="h-11 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
      >
        <Cookie className="h-4 w-4" aria-hidden="true" />
        {t('yasal.ortak.tercihDugmesi')}
      </Button>
      <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
        {sifirlandi ? t('yasal.ortak.tercihSifirlandi') : ''}
      </p>
    </div>
  );
}

function BlokCiz({ blok, b, dil, sayfa, belge }: { blok: Blok; b: YasalBilgiler; dil: string; sayfa: YasalSayfaAnahtari; belge: Belge }) {
  const paragraf = 'text-[15px] leading-relaxed text-muted-foreground';
  if (typeof blok === 'string') {
    return (
      <p className={paragraf}>
        <Metin metin={blok} b={b} dil={dil} />
      </p>
    );
  }
  if ('p' in blok) {
    if (blok.kosul && !b[blok.kosul]) return null;
    return (
      <p className={paragraf}>
        <Metin metin={blok.p} b={b} dil={dil} />
      </p>
    );
  }
  if ('liste' in blok) {
    const maddeler = blok.liste.filter((m) => typeof m === 'string' || !m.kosul || b[m.kosul]);
    return (
      <ul className="list-disc space-y-2 ps-5 text-[15px] leading-relaxed text-muted-foreground marker:text-primary">
        {maddeler.map((m, i) => (
          <li key={i} {...(typeof m !== 'string' && m.kosul ? { 'data-kosul': m.kosul } : {})}>
            <Metin metin={typeof m === 'string' ? m : m.metin} b={b} dil={dil} />
          </li>
        ))}
      </ul>
    );
  }
  if ('tablo' in blok) {
    // Geniş ekranda tablo; dar ekranda (md altı) her satır bir kart, hücreler "Başlık: değer".
    const kodSutunu = sayfa === 'cerezPolitikasi';
    const { basliklar, satirlar } = blok.tablo;
    return (
      <div className="rounded-xl border border-white/10 md:overflow-x-auto" role="region" aria-label={basliklar.join(', ')}>
        <table className="w-full border-collapse text-sm">
          <thead className="hidden bg-white/[0.04] md:table-header-group">
            <tr>
              {basliklar.map((h) => (
                <th key={h} scope="col" className="px-4 py-3 text-start font-semibold text-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="block md:table-row-group">
            {satirlar.map((satir, i) => (
              <tr
                key={i}
                className="block border-t border-white/10 p-4 align-top first:border-t-0 md:table-row md:p-0 md:first:border-t"
              >
                {satir.map((hucre, j) =>
                  j === 0 ? (
                    <th
                      key={j}
                      scope="row"
                      className={`block pb-2 text-start font-medium text-foreground md:table-cell md:px-4 md:py-3 ${kodSutunu ? 'break-all font-mono text-xs md:whitespace-nowrap md:break-normal' : ''}`}
                    >
                      {kodSutunu ? <bdi dir="ltr">{hucre}</bdi> : hucre}
                    </th>
                  ) : (
                    <td key={j} className="block py-0.5 text-muted-foreground md:table-cell md:px-4 md:py-3">
                      <span className="font-semibold text-foreground md:hidden">{basliklar[j]}: </span>
                      {hucre}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (blok.ozel === 'veriSorumlusu') return <VeriSorumlusu b={b} />;
  if (blok.ozel === 'limitedUse') return <LimitedUse metin={belge.limitedUse} dil={dil} />;
  if (blok.ozel === 'cerezTercihi') return <CerezTercihi />;
  return null;
}

/** Panelden girilmiş SEO metni (dil → dilsiz → varsayılan); prerender/settings.js ile aynı sıra. */
function sec(ayarlar: SettingsMap, anahtar: string, dil: string, yedek: string) {
  return ayarlar[`${anahtar}__${dil}`]?.trim() || ayarlar[anahtar]?.trim() || yedek;
}

/**
 * SPA gezinmesinde <head>. Doğrudan açılışta prerender doğru başlığı zaten
 * basıyor; Layout bu sayfalarda kendi başlık efektini çalıştırmıyor.
 * hreflang bağlantıları Layout'la aynı işaretle yazılıyor ki başka sayfaya
 * geçince Layout onları temizlesin (prerender'ınkiler burada siliniyor).
 */
function useYasalBasi(sayfa: YasalSayfaAnahtari, yolDili: string, ayarlar: SettingsMap) {
  const seo = yasalSeo(yolDili, sayfa);
  const anahtarlar = PAGE_SEO_KEYS[sayfa];
  const baslik = sec(ayarlar, anahtarlar.title, yolDili, seo.title);
  const aciklama = sec(ayarlar, anahtarlar.description, yolDili, seo.description);
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const yaz = (secici: string, oz: Record<string, string>) => {
      let el = document.head.querySelector<HTMLMetaElement>(secici);
      if (!el) {
        el = document.createElement('meta');
        document.head.appendChild(el);
      }
      Object.entries(oz).forEach(([k, v]) => el!.setAttribute(k, v));
    };
    const adres = absoluteUrl(localizedPath(yolDili, sayfa));
    document.title = baslik;
    yaz('meta[name="description"]', { name: 'description', content: aciklama });
    yaz('meta[property="og:title"]', { property: 'og:title', content: baslik });
    yaz('meta[property="og:description"]', { property: 'og:description', content: aciklama });
    yaz('meta[property="og:url"]', { property: 'og:url', content: adres });
    yaz('meta[name="twitter:title"]', { name: 'twitter:title', content: baslik });
    yaz('meta[name="twitter:description"]', { name: 'twitter:description', content: aciklama });
    let kanonik = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!kanonik) {
      kanonik = document.createElement('link');
      kanonik.setAttribute('rel', 'canonical');
      document.head.appendChild(kanonik);
    }
    kanonik.setAttribute('href', adres);
    // Prerender'ın bastığı (işaretsiz) hreflang'ler de siliniyor: aynı sekiz bağlantı iki kez kalmasın.
    document.head.querySelectorAll('link[rel="alternate"][hreflang]').forEach((el) => el.remove());
    const ekle = (hreflang: string, href: string) => {
      const link = document.createElement('link');
      link.setAttribute('rel', 'alternate');
      link.setAttribute('hreflang', hreflang);
      link.setAttribute('data-i18n-hreflang', 'true');
      link.setAttribute('href', absoluteUrl(href));
      document.head.appendChild(link);
    };
    LANGUAGE_CODES.forEach((d: string) => ekle(getLanguage(d).htmlLang, localizedPath(d, sayfa)));
    ekle('x-default', localizedPath(DEFAULT_LANGUAGE, sayfa));
  }, [sayfa, yolDili, baslik, aciklama]);
}

export default function YasalSayfa({ sayfa }: { sayfa: YasalSayfaAnahtari }) {
  const { t, i18n } = useTranslation();
  const { lang } = useParams<{ lang?: string }>();
  const { rawSettings } = useSiteSettings();
  const bilgi = useYasalBilgiler();
  // Adres önekinin dili (kanonik/hreflang) ve içeriğin dili (arayüz dili).
  const yolDili = lang && PREFIXED_LANGUAGES.includes(lang) ? lang : DEFAULT_LANGUAGE;
  const dil = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
  useYasalBasi(sayfa, yolDili, rawSettings);

  const belge = belgeyiOku(i18n, sayfa);
  if (!belge) return <div className="min-h-[60vh]" aria-busy="true" />;
  const Ikon = IKON[sayfa];
  const digerleri = (YASAL_SAYFALAR as YasalSayfaAnahtari[]).filter((s) => s !== sayfa);

  return (
    <div className="pb-24 pt-32" data-yasal-sayfa={sayfa}>
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <header className="mx-auto mb-10 max-w-3xl text-center" id="yasal-ust">
          <p className="mb-4 inline-flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-primary">
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t('yasal.ortak.etiket')}
          </p>
          <h1 className="mb-4 text-3xl font-bold leading-tight md:text-5xl">{belge.baslik}</h1>
          <p className="text-muted-foreground">{belge.ozet}</p>
          <p className="mt-4 text-sm text-muted-foreground" data-son-guncelleme>
            {t('yasal.ortak.sonGuncelleme')}:{' '}
            <time dateTime={bilgi.sonGuncelleme} className="font-semibold text-foreground">
              {tarihBicimle(bilgi.sonGuncelleme, dil)}
            </time>
          </p>
        </header>

        <div className="grid items-start gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <nav
            aria-label={t('yasal.ortak.icindekiler')}
            className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5 lg:sticky lg:top-28"
            data-icindekiler
          >
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              {t('yasal.ortak.icindekiler')}
            </p>
            <ol className="space-y-1.5 text-sm">
              {belge.bolumler.map((bolum) => (
                <li key={bolum.id}>
                  <a
                    href={`#${bolum.id}`}
                    className="block rounded-md px-2 py-1 text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
                  >
                    {bolum.baslik}
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          <article className="cam-kart min-w-0 space-y-12 rounded-2xl border border-white/10 bg-white/[0.03] p-6 md:p-10">
            {belge.bolumler.map((bolum) => (
              <section key={bolum.id} id={bolum.id} aria-labelledby={`${bolum.id}-baslik`} className="scroll-mt-28 space-y-4">
                <h2 id={`${bolum.id}-baslik`} className="text-xl font-bold md:text-2xl">
                  {bolum.baslik}
                </h2>
                {bolum.bloklar.map((blok, i) => (
                  <BlokCiz key={i} blok={blok} b={bilgi} dil={dil} sayfa={sayfa} belge={belge} />
                ))}
              </section>
            ))}
            <p className="border-t border-white/10 pt-6 text-sm">
              <a href="#yasal-ust" className={BAGLANTI_SINIFI}>
                {t('yasal.ortak.basaDon')}
              </a>
            </p>
          </article>
        </div>

        <nav aria-label={t('yasal.ortak.digerBelgeler')} className="mt-10" data-diger-belgeler>
          <p className="mb-3 text-center text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            {t('yasal.ortak.digerBelgeler')}
          </p>
          <ul className="flex flex-wrap justify-center gap-3">
            {digerleri.map((s) => {
              const DigerIkon = IKON[s];
              return (
                <li key={s}>
                  <Link
                    to={localizedPath(dil, s)}
                    className="cam-kart inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm font-medium transition-colors hover:border-purple-500/40"
                  >
                    <DigerIkon className="h-4 w-4 text-primary" aria-hidden="true" />
                    {t(`yasal.ortak.belgeler.${s}`)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </div>
  );
}
