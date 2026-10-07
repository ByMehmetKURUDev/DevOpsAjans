import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { VITRIN } from '@/lib/modulVitrini';
import { modullerYolu, paketBul, paketYolu } from '../../../prerender/moduller-veri.js';
import TalepFormu from './TalepFormu';
import { FiyatKutusu, ModulIkonu, ModulKarti, useSayfaBasi, useVitrinDili, useVitrinFiyatlari } from './ortak';

/**
 * Sektör paketi sayfası (Faz 4V): kimin için, neden bu modüller, paketteki
 * modüller (kartlarıyla), fiyat ("teklif alın") ve "Bu paketi isteyin" formu.
 * Paketin tanımı `core/sektor_paketleri.py`'de; burada yalnız çiziliyor.
 */
export default function PaketDetay() {
  const { t } = useTranslation();
  const { slug = '' } = useParams<{ slug: string }>();
  const dil = useVitrinDili();
  const fiyatlar = useVitrinFiyatlari();
  const p = paketBul(VITRIN, slug);

  const ad = p ? t(`modulVitrini.p.${p.anahtar}.ad`) : '';
  useSayfaBasi({
    baslik: p ? `${ad} · ${t('modulVitrini.seo.paketSonEki')}` : t('modulVitrini.seo.baslik'),
    aciklama: p ? t(`modulVitrini.p.${p.anahtar}.ozet`) : t('modulVitrini.seo.aciklama'),
    yol: p ? paketYolu(dil, slug) : modullerYolu(dil),
    diller: p ? (d) => paketYolu(d, slug) : undefined,
    noindex: !p,
  });

  const geri = (
    <Link
      to={`${modullerYolu(dil)}#paketler`}
      className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      data-geri
    >
      <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
      {t('modulVitrini.detay.geri')}
    </Link>
  );

  if (!p) {
    return (
      <div className="pt-32 pb-24">
        <div className="mx-auto max-w-xl px-4 text-center sm:px-6">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-8 py-12" data-modul-durum="yok">
            <h1 className="mb-3 text-2xl font-bold">{t('modulVitrini.detay.paketBulunamadi')}</h1>
            <p className="mb-6 text-muted-foreground">{t('modulVitrini.detay.bulunamadiAciklama')}</p>
            {geri}
          </div>
        </div>
      </div>
    );
  }

  const moduller = p.moduller.map((a) => VITRIN.moduller.find((x) => x.anahtar === a)).filter(Boolean);
  const digerleri = VITRIN.paketler.filter((x) => x.anahtar !== p.anahtar);

  return (
    <div className="pt-32 pb-24">
      <article className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8" data-paket-detay={p.anahtar}>
        <nav aria-label={t('modulVitrini.detay.kirinti')} className="mb-8">
          {geri}
        </nav>

        <header className="mb-12">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-pink-500/15 text-pink-300">
              <ModulIkonu ad={p.ikon} className="h-6 w-6" />
            </span>
            <span className="rounded-full bg-pink-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-pink-300">
              {t('modulVitrini.detay.sektorPaketi')}
            </span>
          </div>
          <h1 className="mb-4 text-4xl font-bold leading-tight md:text-5xl">{ad}</h1>
          <p className="max-w-3xl text-lg text-muted-foreground">{t(`modulVitrini.p.${p.anahtar}.ozet`)}</p>
          <div className="mt-8">
            <Button asChild className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
              <a href="#talep">{t('modulVitrini.form.baslikPaket')}</a>
            </Button>
          </div>
        </header>

        <div className="grid gap-10 lg:grid-cols-3">
          <div className="min-w-0 space-y-10 lg:col-span-2">
            <section>
              <h2 className="mb-3 text-xl font-bold">{t('modulVitrini.detay.kimIcin')}</h2>
              <p className="leading-relaxed text-muted-foreground">{t(`modulVitrini.p.${p.anahtar}.kimIcin`)}</p>
            </section>
            <section>
              <h2 className="mb-3 text-xl font-bold">{t('modulVitrini.detay.neden')}</h2>
              <p className="leading-relaxed text-muted-foreground">{t(`modulVitrini.p.${p.anahtar}.neden`)}</p>
            </section>
          </div>
          <aside className="min-w-0">
            <FiyatKutusu m={null} fiyatlar={fiyatlar} dil={dil} />
          </aside>
        </div>

        {p.setler && p.setler.length > 0 ? (
          <section className="mt-16" data-hazir-kurulum>
            <h2 className="mb-2 text-2xl font-bold">{t('modulVitrini.detay.hazirKurulum')}</h2>
            <p className="mb-6 max-w-3xl text-muted-foreground">{t('modulVitrini.detay.hazirKurulumAciklama')}</p>
            <ul className="grid gap-4 sm:grid-cols-2">
              {p.setler.map((s) => (
                <li key={s} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-hazir-set={s}>
                  <h3 className="mb-1 font-semibold">{t(`modulVitrini.s.${s}.ad`)}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{t(`modulVitrini.s.${s}.ozet`)}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="mt-16" data-paket-modulleri>
          <h2 className="mb-6 text-2xl font-bold">{t('modulVitrini.detay.paketModulleri')}</h2>
          <div className="grid gap-6 sm:grid-cols-2">
            {moduller.map((m) => (
              <ModulKarti key={m.anahtar} m={m} dil={dil} fiyatlar={fiyatlar} />
            ))}
          </div>
        </section>

        <div className="mt-16">
          <TalepFormu tur="paket" anahtar={p.anahtar} dil={dil} isletmeTuru={p.anahtar} />
        </div>

        <section className="mt-16" data-diger-paketler>
          <h2 className="mb-4 text-xl font-bold">{t('modulVitrini.detay.digerPaketler')}</h2>
          <ul className="flex flex-wrap gap-2">
            {digerleri.map((x) => (
              <li key={x.anahtar}>
                <Link
                  to={paketYolu(dil, x.slug)}
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm transition-colors hover:border-purple-500/40"
                >
                  <ModulIkonu ad={x.ikon} className="h-4 w-4 text-pink-300" />
                  {t(`modulVitrini.p.${x.anahtar}.ad`)}
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-12">{geri}</div>
      </article>
    </div>
  );
}
