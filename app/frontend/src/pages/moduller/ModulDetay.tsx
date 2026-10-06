import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Check } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { VITRIN } from '@/lib/modulVitrini';
import { modulBul, modulYolu, modullerYolu, paketYolu } from '../../../prerender/moduller-veri.js';
import TalepFormu from './TalepFormu';
import {
  FiyatKutusu,
  ModulIkonu,
  ModulKarti,
  dizi,
  modulAdi,
  useSayfaBasi,
  useVitrinDili,
  useVitrinFiyatlari,
} from './ortak';

/**
 * Tek modülün tanıtım sayfası (Faz 4V): ne işe yarar, kimin için, neler var,
 * SSS, fiyat (pakete dahilse başlangıç fiyatı, değilse "teklif alın"), birlikte
 * iyi çalışan modüller ve "Bu modülü isteyin" formu.
 *
 * SSS `<details>` ile: tarayıcının kendi aç/kapa davranışı, JS yok.
 */
export default function ModulDetay() {
  const { t } = useTranslation();
  const { slug = '' } = useParams<{ slug: string }>();
  const dil = useVitrinDili();
  const fiyatlar = useVitrinFiyatlari();
  const m = modulBul(VITRIN, slug);

  const ad = m ? modulAdi(t, m.anahtar) : '';
  useSayfaBasi({
    baslik: m ? `${ad} · ${t('modulVitrini.seo.detaySonEki')}` : t('modulVitrini.seo.baslik'),
    aciklama: m ? t(`modulVitrini.m.${m.anahtar}.ozet`) : t('modulVitrini.seo.aciklama'),
    yol: m ? modulYolu(dil, slug) : modullerYolu(dil),
    diller: m ? (d) => modulYolu(d, slug) : undefined,
    noindex: !m,
  });

  const geri = (
    <Link
      to={modullerYolu(dil)}
      className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      data-geri
    >
      <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
      {t('modulVitrini.detay.geri')}
    </Link>
  );

  if (!m) {
    return (
      <div className="pt-32 pb-24">
        <div className="mx-auto max-w-xl px-4 text-center sm:px-6">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-12" data-modul-durum="yok">
            <h1 className="mb-3 text-2xl font-bold">{t('modulVitrini.detay.bulunamadi')}</h1>
            <p className="mb-6 text-muted-foreground">{t('modulVitrini.detay.bulunamadiAciklama')}</p>
            {geri}
          </div>
        </div>
      </div>
    );
  }

  const k = `modulVitrini.m.${m.anahtar}`;
  const ozellikler = dizi<string>(t(`${k}.ozellikler`, { returnObjects: true }));
  const sss = dizi<{ s: string; c: string }>(t(`${k}.sss`, { returnObjects: true }));
  const ilgili = m.ilgili.map((a) => VITRIN.moduller.find((x) => x.anahtar === a)).filter(Boolean);
  const paketler = m.sektor_paketleri.map((a) => VITRIN.paketler.find((p) => p.anahtar === a)).filter(Boolean);

  return (
    <div className="pt-32 pb-24">
      <article className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8" data-modul-detay={m.anahtar}>
        <nav aria-label={t('modulVitrini.detay.kirinti')} className="mb-8">
          {geri}
        </nav>

        <header className="mb-12">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-purple-500/15 text-purple-300">
              <ModulIkonu ad={m.ikon} className="h-6 w-6" />
            </span>
            <Link
              to={`${modullerYolu(dil)}#kategori-${m.kategori}`}
              className="rounded-full bg-purple-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-purple-300 hover:bg-purple-500/20"
            >
              {t(`modul.kategori.${m.kategori}`)}
            </Link>
            {m.durum === 'beta' && (
              <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-semibold text-sky-300">
                {t('modulVitrini.liste.betaRozet')}
              </span>
            )}
          </div>
          <h1 className="mb-4 text-4xl font-bold leading-tight md:text-5xl">{ad}</h1>
          <p className="max-w-3xl text-lg text-muted-foreground">{t(`${k}.ozet`)}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
              <a href="#talep">{t('modulVitrini.form.baslikModul')}</a>
            </Button>
          </div>
        </header>

        <div className="grid gap-10 lg:grid-cols-3">
          <div className="min-w-0 space-y-10 lg:col-span-2">
            <section>
              <h2 className="mb-3 text-xl font-bold">{t('modulVitrini.detay.neYapar')}</h2>
              <p className="leading-relaxed text-muted-foreground">{t(`modul.m.${m.anahtar}.aciklama`)}</p>
            </section>
            <section>
              <h2 className="mb-3 text-xl font-bold">{t('modulVitrini.detay.kimIcin')}</h2>
              <p className="leading-relaxed text-muted-foreground">{t(`${k}.kimIcin`)}</p>
            </section>
            {ozellikler.length > 0 && (
              <section>
                <h2 className="mb-4 text-xl font-bold">{t('modulVitrini.detay.ozellikler')}</h2>
                <ul className="space-y-3" data-ozellikler>
                  {ozellikler.map((o) => (
                    <li key={o} className="flex gap-3">
                      <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
                      <span className="min-w-0 text-muted-foreground">{o}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {sss.length > 0 && (
              <section>
                <h2 className="mb-4 text-xl font-bold">{t('modulVitrini.detay.sss')}</h2>
                <div className="space-y-3" data-sss>
                  {sss.map((s) => (
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
            )}
          </div>

          <aside className="min-w-0 space-y-6">
            <FiyatKutusu m={m} fiyatlar={fiyatlar} dil={dil} />
            {paketler.length > 0 && (
              <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-modul-paketleri>
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  {t('modulVitrini.detay.paketlerde')}
                </h2>
                <ul className="space-y-2 text-sm">
                  {paketler.map((p) => (
                    <li key={p.anahtar}>
                      <Link to={paketYolu(dil, p.slug)} className="inline-flex items-center gap-2 hover:text-purple-300">
                        <ModulIkonu ad={p.ikon} className="h-4 w-4 shrink-0 text-pink-300" />
                        {t(`modulVitrini.p.${p.anahtar}.ad`)}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        </div>

        {ilgili.length > 0 && (
          <section className="mt-16" data-ilgili>
            <h2 className="mb-6 text-2xl font-bold">{t('modulVitrini.detay.ilgili')}</h2>
            <div className="grid gap-6 sm:grid-cols-2">
              {ilgili.map((x) => (
                <ModulKarti key={x.anahtar} m={x} dil={dil} fiyatlar={fiyatlar} />
              ))}
            </div>
          </section>
        )}

        <div className="mt-16">
          <TalepFormu tur="modul" anahtar={m.anahtar} dil={dil} />
        </div>

        <div className="mt-12">{geri}</div>
      </article>
    </div>
  );
}
