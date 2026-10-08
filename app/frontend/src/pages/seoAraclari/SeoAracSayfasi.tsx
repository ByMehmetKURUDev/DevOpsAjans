import { Suspense, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Check, Loader2, Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { ekliLazy } from '@/i18n/ekliLazy';
import { AracHatasi, araciCalistir, type AracSonucu } from '@/lib/seoAraclari';
import {
  ROBOTS_AJANLARI,
  SEO_ARACLARI,
  seoAracBul,
  seoAracYolu,
  seoAraclariYolu,
} from '../../../prerender/seo-araclari-veri.js';
import { AracIkonu, AracKarti, SiteAnaliziCagrisi, Sss, dizi, useAracDili, useSayfaBasi } from './ortak';

/** Sonuç görünümü yalnız ilk sonuçta iner (kontrol/bulgu metinleri `seoAracSonuc`, e-posta formunun aydınlatma satırı `aydinlatma`). */
const SeoAracSonucu = ekliLazy(['seoAracSonuc', 'aydinlatma'], () => import('./SeoAracSonucu'));

const GIRDI =
  'w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none';

/** Adres alanının etiketi/örneği araca göre (robots: yol dahil, site haritası: harita adresi, SSL: alan adı). */
function adresMetinleri(anahtar: string): { etiket: string; ornek: string } {
  if (anahtar === 'robots') return { etiket: 'adresRobots', ornek: 'adresRobotsOrnek' };
  if (anahtar === 'sitemap') return { etiket: 'adresSitemap', ornek: 'adresSitemapOrnek' };
  if (anahtar === 'ssl') return { etiket: 'adresSsl', ornek: 'adresSslOrnek' };
  return { etiket: 'adres', ornek: 'adresOrnek' };
}

/**
 * Tek bir ücretsiz SEO aracının sayfası (`/seo-araclari/<slug>`, 7 dil, prerender) — Faz 4S.
 *
 * İlk boyama prerender'dan: başlık, giriş, form, "neleri kontrol eder", SSS ve
 * diğer araçlar statik. Form gönderilince `POST /api/v1/seo-araclari/<slug>`;
 * sonuç bileşeni ve metinleri tembel yükleniyor. E-posta İSTENMİYOR; sonucun
 * altında "Sitenin tam analizini al" (Site Analizi, adres dolu) ve isteğe bağlı
 * "Sonucu e-postayla gönder" var.
 *
 * Adres başka araçtan (router state) ya da `?url=` ile gelebilir; `?calistir=1`
 * (sonuç e-postasındaki "sitede ayrıntılı gör" bağlantısı) aracı bir kez kendiliğinden çalıştırır.
 */
export default function SeoAracSayfasi() {
  const { t } = useTranslation();
  const { slug = '' } = useParams<{ slug: string }>();
  const konum = useLocation();
  const dil = useAracDili();
  const a = seoAracBul(slug);

  const sorgu = new URLSearchParams(konum.search);
  const durumAdresi = (konum.state as { url?: unknown } | null)?.url;
  const ilkAdres = (typeof durumAdresi === 'string' ? durumAdresi : sorgu.get('url') || '').slice(0, 2000);
  const [adres, setAdres] = useState(ilkAdres);
  const [ajan, setAjan] = useState('Googlebot');
  const [ozelAjan, setOzelAjan] = useState('');
  const [kelime, setKelime] = useState('');
  const [calisiyor, setCalisiyor] = useState(false);
  const [sonuc, setSonuc] = useState<AracSonucu | null>(null);
  const [hataKodu, setHataKodu] = useState<string | null>(null);
  const sonucRef = useRef<HTMLDivElement>(null);
  const kesici = useRef<AbortController | null>(null);

  // Başka araca geçince (aynı bileşen, farklı slug) önceki sonuç kalmasın.
  useEffect(() => {
    setSonuc(null);
    setHataKodu(null);
    kesici.current?.abort();
    setCalisiyor(false);
  }, [slug]);
  useEffect(() => () => kesici.current?.abort(), []);

  // Sonuç e-postasındaki bağlantı (`?url=…&calistir=1`): bir kez kendiliğinden çalıştır.
  const otomatik = useRef(false);
  const otomatikIstek = Boolean(a && ilkAdres && sorgu.get('calistir') === '1');

  const calistirRef = useRef<() => void>(() => {});
  useEffect(() => {
    if (otomatik.current || !otomatikIstek) return;
    otomatik.current = true;
    // Bir sonraki karede: form ve durum hazır olsun.
    window.setTimeout(() => calistirRef.current(), 0);
  }, [otomatikIstek]);

  useSayfaBasi({
    baslik: a ? `${t(`seoAraclari.arac.${a.anahtar}.seoBaslik`)} | Mehmet KURU` : t('seoAraclari.seo.baslik'),
    aciklama: a ? t(`seoAraclari.arac.${a.anahtar}.seoAciklama`) : t('seoAraclari.seo.aciklama'),
    yol: a ? seoAracYolu(dil, a.slug) : seoAraclariYolu(dil),
    diller: a ? (d) => seoAracYolu(d, a.slug) : undefined,
    noindex: !a,
  });

  const geri = (
    <Link
      to={seoAraclariYolu(dil)}
      className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      data-geri
    >
      <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
      {t('seoAraclari.sayfa.geri')}
    </Link>
  );

  if (!a) {
    return (
      <div className="pt-32 pb-24">
        <div className="mx-auto max-w-xl px-4 text-center sm:px-6">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-12" data-seo-arac-durum="yok">
            <h1 className="mb-3 text-2xl font-bold">{t('seoAraclari.sayfa.bulunamadi')}</h1>
            <p className="mb-6 text-muted-foreground">{t('seoAraclari.sayfa.bulunamadiAciklama')}</p>
            {geri}
          </div>
        </div>
      </div>
    );
  }

  const k = `seoAraclari.arac.${a.anahtar}`;
  const neler = dizi<string>(t(`${k}.neler`, { returnObjects: true }));
  const sorular = dizi<{ s: string; c: string }>(t(`${k}.sss`, { returnObjects: true }));
  const metin = adresMetinleri(a.anahtar);
  const robotsMu = a.anahtar === 'robots';
  const kelimeMi = a.anahtar === 'kelime';
  const secilenAjan = ajan === '__ozel' ? ozelAjan.trim() : ajan;

  const calistir = async (olay?: FormEvent) => {
    olay?.preventDefault();
    if (calisiyor || !a) return;
    if (!adres.trim()) {
      setHataKodu('adres_gecersiz');
      return;
    }
    if (robotsMu && !secilenAjan) {
      setHataKodu('ajan_gecersiz');
      return;
    }
    kesici.current?.abort();
    const yeni = new AbortController();
    kesici.current = yeni;
    setCalisiyor(true);
    setHataKodu(null);
    setSonuc(null);
    try {
      const s = await araciCalistir(
        a.slug,
        {
          url: adres.trim(),
          ...(robotsMu ? { ajan: secilenAjan } : {}),
          ...(kelimeMi && kelime.trim() ? { kelime: kelime.trim() } : {}),
        },
        yeni.signal,
      );
      setSonuc(s);
      // Sonuç tembel bileşende; çizilince başına kaydır ve odağı oraya taşı.
      window.setTimeout(() => {
        sonucRef.current?.scrollIntoView({ block: 'start' });
        sonucRef.current?.focus({ preventScroll: true });
      }, 60);
    } catch (h) {
      if ((h as { name?: string })?.name === 'AbortError') return;
      setHataKodu(h instanceof AracHatasi ? h.kod : 'genel');
    } finally {
      if (kesici.current === yeni) setCalisiyor(false);
    }
  };

  calistirRef.current = () => void calistir();

  const digerleri = SEO_ARACLARI.filter((x) => x.slug !== a.slug);

  return (
    <div className="pt-32 pb-24">
      <article className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8" data-seo-arac={a.slug}>
        <nav aria-label={t('seoAraclari.sayfa.kirinti')} className="mb-8">
          {geri}
        </nav>

        <header className="mb-10">
          <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-purple-500/15 text-purple-300">
            <AracIkonu ad={a.ikon} className="h-6 w-6" />
          </span>
          <h1 className="mb-4 text-4xl font-bold leading-tight md:text-5xl">{t(`${k}.ad`)}</h1>
          <p className="max-w-3xl text-lg text-muted-foreground">{t(`${k}.giris`)}</p>
        </header>

        <form
          onSubmit={calistir}
          className="cam-kart cam-mor rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6"
          aria-label={t(`${k}.ad`)}
          data-arac-formu
          noValidate
        >
          <label htmlFor="arac-adres" className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            {t(`seoAraclari.form.${metin.etiket}`)}
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="arac-adres"
              value={adres}
              onChange={(o) => setAdres(o.target.value)}
              placeholder={t(`seoAraclari.form.${metin.ornek}`)}
              inputMode="url"
              autoComplete="url"
              spellCheck={false}
              dir="ltr"
              maxLength={2000}
              disabled={calisiyor}
              className={`${GIRDI} h-12 min-w-0 text-base`}
            />
            <Button type="submit" disabled={calisiyor} className="h-12 gap-2 px-6 sm:flex-none" data-arac-calistir>
              {calisiyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />}
              {t(calisiyor ? 'seoAraclari.form.calisiyor' : 'seoAraclari.form.calistir')}
            </Button>
          </div>
          {robotsMu && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="min-w-0">
                <label htmlFor="arac-ajan" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('seoAraclari.form.ajan')}
                </label>
                <select
                  id="arac-ajan"
                  value={ajan}
                  onChange={(o) => setAjan(o.target.value)}
                  disabled={calisiyor}
                  className={`${GIRDI} bg-background`}
                  data-arac-ajan
                >
                  {ROBOTS_AJANLARI.map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                  <option value="__ozel">{t('seoAraclari.form.ajanOzel')}</option>
                </select>
              </div>
              {ajan === '__ozel' && (
                <div className="min-w-0">
                  <label htmlFor="arac-ozel-ajan" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t('seoAraclari.form.ajanOzel')}
                  </label>
                  <input
                    id="arac-ozel-ajan"
                    value={ozelAjan}
                    onChange={(o) => setOzelAjan(o.target.value)}
                    placeholder={t('seoAraclari.form.ajanOzelYerTutucu')}
                    maxLength={40}
                    dir="ltr"
                    className={GIRDI}
                  />
                </div>
              )}
            </div>
          )}
          {kelimeMi && (
            <div className="mt-4 min-w-0 sm:max-w-md">
              <label htmlFor="arac-kelime" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('seoAraclari.form.kelime')}
              </label>
              <input
                id="arac-kelime"
                value={kelime}
                onChange={(o) => setKelime(o.target.value)}
                placeholder={t('seoAraclari.form.kelimeOrnek')}
                maxLength={60}
                disabled={calisiyor}
                dir="auto"
                className={GIRDI}
                aria-describedby="arac-kelime-ipucu"
                data-arac-kelime
              />
              <p id="arac-kelime-ipucu" className="mt-1.5 text-xs text-muted-foreground">
                {t('seoAraclari.form.kelimeIpucu')}
              </p>
            </div>
          )}
          <p className="mt-3 text-xs text-muted-foreground">{t('seoAraclari.form.gizlilik')}</p>
          <div aria-live="polite">
            {calisiyor && (
              <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground" data-arac-bekliyor>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                {t('seoAraclari.form.bekleyin')}
              </p>
            )}
            {hataKodu && (
              <p role="alert" className="mt-3 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200" data-arac-hata={hataKodu}>
                {t(`seoAraclari.hata.${hataKodu}`, { defaultValue: t('seoAraclari.hata.genel') })}
              </p>
            )}
          </div>
        </form>

        {sonuc && (
          <div ref={sonucRef} tabIndex={-1} className="mt-10 scroll-mt-28 outline-none" data-arac-sonuc-kapsayici>
            <Suspense
              fallback={
                <div className="flex justify-center py-10 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
                </div>
              }
            >
              <SeoAracSonucu sonuc={sonuc} arac={a} dil={dil} girilen={adres.trim()} />
            </Suspense>
          </div>
        )}

        <div className="mt-14 grid gap-10 lg:grid-cols-5">
          <section className="lg:col-span-2" data-arac-neler>
            <h2 className="mb-4 text-xl font-bold">{t('seoAraclari.sayfa.nelerBaslik')}</h2>
            <ul className="space-y-3">
              {neler.map((n) => (
                <li key={n} className="flex gap-3">
                  <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
                  <span className="min-w-0 text-sm leading-relaxed text-muted-foreground">{n}</span>
                </li>
              ))}
            </ul>
          </section>
          <div className="min-w-0 lg:col-span-3">
            <Sss sorular={sorular} baslik={t('seoAraclari.sayfa.sssBaslik')} />
          </div>
        </div>

        <section className="mt-16" data-diger-araclar>
          <h2 className="mb-6 text-2xl font-bold">{t('seoAraclari.sayfa.digerAraclar')}</h2>
          <div className="cam-dongu grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {digerleri.map((x) => (
              <AracKarti key={x.slug} a={x} dil={dil} baslikDuzeyi="h3" durum={adres.trim() ? { url: adres.trim() } : undefined} />
            ))}
          </div>
        </section>

        <div className="mt-16">
          <SiteAnaliziCagrisi dil={dil} />
        </div>

        <div className="mt-12">{geri}</div>
      </article>
    </div>
  );
}
