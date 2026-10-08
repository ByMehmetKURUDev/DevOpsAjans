import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BadgePercent, CheckCircle2, HandCoins, Loader2, MousePointerClick, Send, Wallet } from 'lucide-react';

import AydinlatmaSatiri from '@/components/AydinlatmaSatiri';
import { Button } from '@/components/ui/button';
import { paraBicimle } from '@/lib/belge';
import { basvur, BelgeHatasi, programBilgisi, type ProgramBilgisi } from '@/lib/ortaklik';
import { localizedPath, PAGE_SEO_KEYS } from '../../prerender/site.js';
import { paneldenSeo, useIcerikDili, useSayfaBasi } from './kaynaklar/ortak';

/**
 * Faz 5K — herkese açık ortaklık (referans) programı sayfası: tanıtım, nasıl çalışır, program koşulları
 * (metin ayarlardan; yoksa ek paketteki varsayılan), SSS ve başvuru formu.
 *
 * KVKK: formun altında aydınlatma satırı (rıza değil); program koşullarının kabulü sözleşme içindir
 * (zorunlu kutu); pazarlama izni AYRI, isteğe bağlı, varsayılan işaretsiz (metni sunucudaki
 * `pazarlama_izni.METINLER` ile aynı — test karşılaştırıyor). Bal küpü alanı görünmez.
 * Metinler `ortaklik` ek paketinde (ana pakete girmez); prerender bütün ek paketleri yüklüyor.
 */

const VARSAYILAN: ProgramBilgisi = {
  acik: true,
  varsayilan_oran: 10,
  tekrar_oran: 5,
  tekrar_ay: 0,
  bekleme_gun: 30,
  odeme_en_az: { TRY: 500, USD: 25, EUR: 25, GBP: 20 },
  cerez_gun: 30,
  kosullar: null,
  kosullar_surumu: 'varsayilan-1',
};

const GIRDI =
  'w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none';

function dizi<T>(deger: unknown): T[] {
  return Array.isArray(deger) ? (deger as T[]) : [];
}

export default function Ortaklik() {
  const { t } = useTranslation();
  const dil = useIcerikDili();
  const [program, setProgram] = useState<ProgramBilgisi>(VARSAYILAN);
  const [form, setForm] = useState({ ad: '', eposta: '', web: '', tanitim: '', web_sitesi: '' });
  const [kosul, setKosul] = useState(false);
  const [pazarlama, setPazarlama] = useState(false);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [gonderilen, setGonderilen] = useState<string | null>(null);

  const baslik = paneldenSeo(PAGE_SEO_KEYS.ortaklik.title, dil, t('ortaklik.seo.baslik'));
  const aciklama = paneldenSeo(PAGE_SEO_KEYS.ortaklik.description, dil, t('ortaklik.seo.aciklama'));
  useSayfaBasi({ baslik, aciklama, yol: localizedPath(dil, 'ortaklik'), diller: (d) => localizedPath(d, 'ortaklik') });

  useEffect(() => {
    let iptal = false;
    programBilgisi(dil)
      .then((p) => !iptal && setProgram(p))
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, [dil]);

  const enAz = paraBicimle(program.odeme_en_az.TRY ?? 500, 'TRY', dil);
  const ozellikler = [
    {
      ikon: BadgePercent,
      baslik: t('ortaklik.ozellik.oranBaslik', { oran: program.varsayilan_oran }),
      // Tekrar eden (abonelik) komisyonu ayarda açıksa (N ay > 0) cümlesi eklenir.
      metin:
        t('ortaklik.ozellik.oranMetin') +
        (program.tekrar_ay > 0 && program.tekrar_oran > 0
          ? ` ${t('ortaklik.ozellik.tekrarMetin', { oran: program.tekrar_oran, ay: program.tekrar_ay })}`
          : ''),
    },
    { ikon: MousePointerClick, baslik: t('ortaklik.ozellik.cerezBaslik', { gun: program.cerez_gun }), metin: t('ortaklik.ozellik.cerezMetin', { gun: program.cerez_gun }) },
    { ikon: Wallet, baslik: t('ortaklik.ozellik.odemeBaslik'), metin: t('ortaklik.ozellik.odemeMetin', { en_az: enAz }) },
  ];
  const adimlar = [1, 2, 3, 4].map((n) => ({
    baslik: t(`ortaklik.adim.b${n}`),
    metin: t(`ortaklik.adim.m${n}`, { gun: program.bekleme_gun }),
  }));
  const varsayilanKosullar = dizi<string>(t('ortaklik.kosul.varsayilan', { returnObjects: true, gun: program.bekleme_gun }));
  if (program.tekrar_ay > 0 && program.tekrar_oran > 0 && varsayilanKosullar.length) {
    // Varsayılan metinde tekrar eden komisyon maddesi ilk satış maddesinin hemen ardından.
    varsayilanKosullar.splice(1, 0, t('ortaklik.kosul.tekrar', { oran: program.tekrar_oran, ay: program.tekrar_ay }));
  }
  const kosulParagraflari = program.kosullar
    ? program.kosullar.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)
    : varsayilanKosullar;
  const sss = dizi<{ s: string; c: string }>(
    t('ortaklik.sss.liste', { returnObjects: true, gun: program.bekleme_gun, cerez: program.cerez_gun }),
  );

  const alan = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (gonderiliyor) return;
    setHata(null);
    if (!kosul) {
      setHata(t('ortaklik.form.hata.kosullar_gerekli'));
      return;
    }
    setGonderiliyor(true);
    try {
      await basvur({
        ad: form.ad.trim(),
        eposta: form.eposta.trim(),
        web: form.web.trim(),
        tanitim: form.tanitim.trim(),
        kosullar_kabul: true,
        pazarlama_izni: pazarlama,
        dil,
        ...(form.web_sitesi ? { web_sitesi: form.web_sitesi } : {}),
      });
      setGonderilen(form.eposta.trim());
    } catch (h) {
      const kod = h instanceof BelgeHatasi ? (h.durum === 429 ? 'cok_hizli' : h.kod) : 'genel';
      setHata(t(`ortaklik.form.hata.${kod}`, { defaultValue: t('ortaklik.form.hata.genel') }));
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <div className="pt-32 pb-24" data-ortaklik-sayfasi>
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <header className="mx-auto mb-14 max-w-3xl text-center">
          <p className="mb-4 text-xs uppercase tracking-[0.3em] text-primary">{t('ortaklik.sayfa.etiket')}</p>
          <h1 className="mb-5 text-4xl font-bold md:text-6xl">
            {t('ortaklik.sayfa.baslik')} <span className="gradient-text">{t('ortaklik.sayfa.vurgu')}</span>
          </h1>
          <p className="text-lg text-muted-foreground">{t('ortaklik.sayfa.aciklama')}</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Button asChild className="h-11 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
              <a href="#basvuru">
                <HandCoins className="h-4 w-4" aria-hidden="true" />
                {t('ortaklik.sayfa.basvur')}
              </a>
            </Button>
            <Button asChild variant="outline" className="h-11 border-white/20 !bg-transparent">
              <a href="#nasil">{t('ortaklik.sayfa.nasil')}</a>
            </Button>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            {t('ortaklik.sayfa.girisMetni')}{' '}
            <Link to="/client?sekme=ortaklik" className="text-primary underline underline-offset-2">
              {t('ortaklik.sayfa.girisBaglanti')}
            </Link>
          </p>
        </header>

        <section className="mb-16 grid gap-5 md:grid-cols-3" aria-label={t('ortaklik.sayfa.etiket')}>
          {ozellikler.map(({ ikon: Ikon, baslik: b, metin }) => (
            <article key={b} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
              <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-primary/15">
                <Ikon className="h-5 w-5 text-primary" aria-hidden="true" />
              </span>
              <h2 className="mb-2 text-xl font-semibold">{b}</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">{metin}</p>
            </article>
          ))}
        </section>

        <section id="nasil" className="mb-16 scroll-mt-28" aria-labelledby="ortaklik-nasil">
          <h2 id="ortaklik-nasil" className="mb-6 text-3xl font-bold">
            {t('ortaklik.adim.baslik')}
          </h2>
          <ol className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {adimlar.map((a, i) => (
              <li key={a.baslik} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <span className="mb-3 inline-flex h-8 w-8 items-center justify-center rounded-full bg-purple-500/20 text-sm font-bold text-purple-200">
                  {i + 1}
                </span>
                <h3 className="mb-1 font-semibold">{a.baslik}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{a.metin}</p>
              </li>
            ))}
          </ol>
        </section>

        <div className="grid gap-10 lg:grid-cols-5">
          <div className="space-y-12 lg:col-span-3">
            <section aria-labelledby="ortaklik-kosul" data-ortaklik-kosullar>
              <h2 id="ortaklik-kosul" className="mb-4 text-2xl font-bold">
                {t('ortaklik.kosul.baslik')}
              </h2>
              <div className="cam-kart space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm leading-relaxed text-muted-foreground">
                {program.kosullar ? (
                  kosulParagraflari.map((p, i) => (
                    <p key={i} className="whitespace-pre-line">
                      {p}
                    </p>
                  ))
                ) : (
                  <ul className="list-disc space-y-2 ps-5">
                    {kosulParagraflari.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                )}
                <p className="pt-2 text-xs italic">{t('ortaklik.kosul.bilgi')}</p>
              </div>
            </section>

            <section aria-labelledby="ortaklik-sss">
              <h2 id="ortaklik-sss" className="mb-4 text-2xl font-bold">
                {t('ortaklik.sss.baslik')}
              </h2>
              <div className="space-y-3">
                {sss.map((x) => (
                  <details key={x.s} className="cam-kart group rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                    <summary className="cursor-pointer font-semibold">{x.s}</summary>
                    <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{x.c}</p>
                  </details>
                ))}
              </div>
            </section>
          </div>

          <section id="basvuru" className="scroll-mt-28 lg:col-span-2" aria-labelledby="ortaklik-form">
            <div className="relative rounded-3xl glass p-6 md:p-8">
              <h2 id="ortaklik-form" className="mb-1 text-2xl font-bold">
                {t('ortaklik.form.baslik')}
              </h2>
              <p className="mb-5 text-sm text-muted-foreground">{t('ortaklik.form.aciklama')}</p>
              {gonderilen ? (
                <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-5" role="status" data-testid="ortaklik-basarili">
                  <CheckCircle2 className="mb-2 h-8 w-8 text-emerald-400" aria-hidden="true" />
                  <p className="font-semibold text-emerald-200">{t('ortaklik.form.basarili')}</p>
                  <p className="mt-2 text-sm text-muted-foreground">{t('ortaklik.form.basariliMetin', { eposta: gonderilen })}</p>
                </div>
              ) : !program.acik ? (
                <p className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">{t('ortaklik.sayfa.kapali')}</p>
              ) : (
                <form onSubmit={gonder} className="space-y-4" data-testid="ortaklik-form" noValidate>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium">{t('ortaklik.form.ad')} *</span>
                    <input className={GIRDI} name="ad" value={form.ad} onChange={alan('ad')} required maxLength={120} autoComplete="name" />
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium">{t('ortaklik.form.eposta')} *</span>
                    <input className={GIRDI} name="eposta" type="email" value={form.eposta} onChange={alan('eposta')} required maxLength={254} autoComplete="email" />
                    <span className="mt-1 block text-xs text-muted-foreground">{t('ortaklik.form.epostaIpucu')}</span>
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium">{t('ortaklik.form.web')}</span>
                    <input className={GIRDI} name="web" value={form.web} onChange={alan('web')} maxLength={300} placeholder={t('ortaklik.form.webYerTutucu')} />
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium">{t('ortaklik.form.tanitim')} *</span>
                    <textarea
                      className={`${GIRDI} min-h-[96px] resize-y`}
                      name="tanitim"
                      value={form.tanitim}
                      onChange={alan('tanitim')}
                      required
                      maxLength={2000}
                      placeholder={t('ortaklik.form.tanitimYerTutucu')}
                    />
                  </label>
                  {/* Bal küpü: insan görmüyor (ekran okuyucudan da gizli), bot dolduruyor. */}
                  <div className="absolute -left-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
                    <label>
                      web_sitesi
                      <input tabIndex={-1} autoComplete="off" name="web_sitesi" value={form.web_sitesi} onChange={alan('web_sitesi')} />
                    </label>
                  </div>
                  <label className="flex cursor-pointer items-start gap-3 text-sm" data-ortaklik-kosul-kutusu>
                    <input type="checkbox" className="mt-0.5 h-4 w-4 flex-none accent-purple-500" checked={kosul} onChange={(e) => setKosul(e.target.checked)} required />
                    <span>
                      {t('ortaklik.form.kosullar')}{' '}
                      <a href="#ortaklik-kosul" className="text-primary underline underline-offset-2">
                        {t('ortaklik.kosul.baslik')}
                      </a>
                    </span>
                  </label>
                  <label className="flex cursor-pointer items-start gap-3 text-sm text-muted-foreground" data-pazarlama-izni>
                    <input type="checkbox" className="mt-0.5 h-4 w-4 flex-none accent-purple-500" checked={pazarlama} onChange={(e) => setPazarlama(e.target.checked)} />
                    <span>{t('ortaklik.form.pazarlama')}</span>
                  </label>
                  {hata && (
                    <p className="text-sm text-red-300" role="alert" data-testid="ortaklik-hata">
                      {hata}
                    </p>
                  )}
                  <Button type="submit" disabled={gonderiliyor} className="h-11 w-full gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white" data-testid="ortaklik-gonder">
                    {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
                    {gonderiliyor ? t('ortaklik.form.gonderiliyor') : t('ortaklik.form.gonder')}
                  </Button>
                  <AydinlatmaSatiri metin={t('ortaklik.form.aydinlatma')} className="text-center text-xs leading-relaxed text-muted-foreground" />
                </form>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
