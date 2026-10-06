import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Blocks, Check } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { MODUL_IKONLARI } from '@/lib/modulIkonlari';
import {
  VITRIN,
  eldekiFiyatlar,
  fiyatlariGetir,
  fiyatlarTazeMi,
  type VitrinFiyatlari,
  type VitrinModulu,
  type VitrinPaketi,
} from '@/lib/modulVitrini';
import { modulFiyati, modulYolu, olcekAdi, paketYolu, paraBicimi } from '../../../prerender/moduller-veri.js';
import { localizedPath } from '../../../prerender/site.js';

/**
 * Modül vitrini sayfalarının (liste, modül, paket) ortak parçaları (Faz 4V).
 *
 * İçerik dili ve <head> yönetimi Kaynaklar'daki yardımcılarla aynı
 * (`../kaynaklar/ortak`): dil adresten geliyor, SPA gezinmesinde başlık,
 * açıklama, kanonik adres ve hreflang sayfanın kendisinden yazılıyor.
 */
export { useIcerikDili as useVitrinDili, useSayfaBasi } from '../kaynaklar/ortak';

export function ModulIkonu({ ad, className = 'h-5 w-5' }: { ad: string; className?: string }) {
  const Ikon = MODUL_IKONLARI[ad] ?? Blocks;
  return <Ikon className={className} aria-hidden="true" />;
}

/** `t(..., { returnObjects: true })` dizi döndürmezse boş dizi. */
export function dizi<T>(deger: unknown): T[] {
  return Array.isArray(deger) ? (deger as T[]) : [];
}

export function modulAdi(t: (k: string) => string, anahtar: string): string {
  return t(`modul.m.${anahtar}.ad`);
}

/**
 * Fiyatlar: ilk çizim gömülü/önbellekteki veriyle, sonra uçtan tazelenir.
 * Uç yanıt vermezse eldeki (boş olabilir) kalır — sayfa "pakete dahil" / "teklif alın" der.
 * Aynı oturumda bir kez alındıysa (vitrin sayfaları arası gezinme) yeniden istenmez.
 */
export function useVitrinFiyatlari(): VitrinFiyatlari {
  const [fiyatlar, setFiyatlar] = useState<VitrinFiyatlari>(() => eldekiFiyatlar());
  useEffect(() => {
    if (fiyatlarTazeMi()) return undefined;
    const kesici = new AbortController();
    fiyatlariGetir(kesici.signal)
      .then((yeni) => setFiyatlar((onceki) => (JSON.stringify(onceki) === JSON.stringify(yeni) ? onceki : yeni)))
      .catch(() => {});
    return () => kesici.abort();
  }, []);
  return fiyatlar;
}

/** Kartta kısa fiyat ipucu: "Alfa paketinde" ya da "Teklif ile". */
export function FiyatIpucu({ m, fiyatlar, dil }: { m: VitrinModulu; fiyatlar: VitrinFiyatlari; dil: string }) {
  const { t } = useTranslation();
  const f = modulFiyati(m, fiyatlar);
  return (
    <span
      className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${
        f ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300' : 'border-white/15 bg-white/[0.04] text-muted-foreground'
      }`}
      data-fiyat-ipucu={f ? 'paket' : 'teklif'}
    >
      {f ? t('modulVitrini.fiyat.kartPaket', { paket: olcekAdi(fiyatlar, f.paket, dil) }) : t('modulVitrini.fiyat.kartTeklif')}
    </span>
  );
}

/** Modül kartı (liste, paket sayfası, "birlikte iyi çalışır"). Kartın tamamı ayrıntıya bağlantı. */
export function ModulKarti({
  m,
  dil,
  fiyatlar,
  baslikDuzeyi = 'h3',
}: {
  m: VitrinModulu;
  dil: string;
  fiyatlar: VitrinFiyatlari;
  baslikDuzeyi?: 'h2' | 'h3';
}) {
  const { t } = useTranslation();
  const Baslik = baslikDuzeyi;
  return (
    <Link
      to={modulYolu(dil, m.slug)}
      data-modul={m.anahtar}
      className="cam-kart group flex h-full min-w-0 flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition-colors hover:border-purple-500/40"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-purple-500/15 text-purple-300">
          <ModulIkonu ad={m.ikon} />
        </span>
        {m.durum === 'beta' && (
          <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-semibold text-sky-300">
            {t('modulVitrini.liste.betaRozet')}
          </span>
        )}
      </div>
      <Baslik className="mb-2 text-lg font-bold leading-snug">{modulAdi(t, m.anahtar)}</Baslik>
      <p className="mb-4 flex-1 text-sm leading-relaxed text-muted-foreground">{t(`modulVitrini.m.${m.anahtar}.ozet`)}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FiyatIpucu m={m} fiyatlar={fiyatlar} dil={dil} />
        <span className="inline-flex items-center gap-1 text-sm font-medium text-purple-300 group-hover:text-purple-200">
          {t('modulVitrini.liste.incele')}
          <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </span>
      </div>
    </Link>
  );
}

/** Sektör paketi kartı: içindeki modüller adlarıyla, paket sayfasına bağlantı. */
export function PaketKarti({ p, dil }: { p: VitrinPaketi; dil: string }) {
  const { t } = useTranslation();
  return (
    <article
      data-paket={p.anahtar}
      className="cam-kart flex h-full min-w-0 flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-6"
    >
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-pink-500/15 text-pink-300">
          <ModulIkonu ad={p.ikon} />
        </span>
        <h3 className="min-w-0 text-lg font-bold leading-snug">{t(`modulVitrini.p.${p.anahtar}.ad`)}</h3>
      </div>
      <p className="mb-4 text-sm leading-relaxed text-muted-foreground">{t(`modulVitrini.p.${p.anahtar}.ozet`)}</p>
      <ul className="mb-5 flex flex-1 flex-wrap content-start gap-2" aria-label={t('modulVitrini.liste.paketModulleri')}>
        {p.moduller.map((k) => {
          const m = VITRIN.moduller.find((x) => x.anahtar === k);
          return (
            <li key={k} className="min-w-0">
              {m ? (
                <Link
                  to={modulYolu(dil, m.slug)}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-foreground/90 transition-colors hover:border-purple-500/40"
                >
                  <Check className="h-3 w-3 shrink-0 text-emerald-400" aria-hidden="true" />
                  <span className="truncate">{modulAdi(t, k)}</span>
                </Link>
              ) : (
                <span className="text-xs">{modulAdi(t, k)}</span>
              )}
            </li>
          );
        })}
      </ul>
      <Button asChild variant="outline" className="h-10 w-full gap-2 border-white/20 !bg-transparent">
        <Link to={paketYolu(dil, p.slug)} data-paket-baglanti={p.anahtar}>
          {t('modulVitrini.liste.paketiIncele')}
          <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
        </Link>
      </Button>
    </article>
  );
}

/** Ayrıntı sayfasının yan kutusu: pakete dahilse paket + başlangıç fiyatı, değilse "teklif alın". */
export function FiyatKutusu({ m, fiyatlar, dil }: { m: VitrinModulu | null; fiyatlar: VitrinFiyatlari; dil: string }) {
  const { t } = useTranslation();
  const f = m ? modulFiyati(m, fiyatlar) : null;
  return (
    <section
      className="cam-kart cam-mor rounded-2xl border border-purple-500/30 bg-purple-500/10 p-6"
      aria-labelledby="fiyat-baslik"
      data-fiyat-kutusu={f ? 'paket' : 'teklif'}
    >
      <h2 id="fiyat-baslik" className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        {t('modulVitrini.fiyat.baslik')}
      </h2>
      {f ? (
        <>
          <p className="font-semibold">{t('modulVitrini.fiyat.dahil', { paket: olcekAdi(fiyatlar, f.paket, dil) })}</p>
          {f.tutar !== null && (
            <p className="mt-3" data-fiyat-tutar={f.tutar}>
              <span className="block text-xs text-muted-foreground">{t('modulVitrini.fiyat.baslangic')}</span>
              <span className="text-2xl font-bold">{t('modulVitrini.fiyat.aylik', { tutar: paraBicimi(f.tutar) })}</span>
            </p>
          )}
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{t('modulVitrini.fiyat.profilNotu')}</p>
          <Link
            to={localizedPath(dil, 'services')}
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-purple-300 underline-offset-2 hover:underline"
          >
            {t('modulVitrini.fiyat.karsilastir')}
            <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          </Link>
        </>
      ) : (
        <>
          <p className="text-xl font-bold">{t('modulVitrini.fiyat.teklifBaslik')}</p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {t(m ? 'modulVitrini.fiyat.teklifMetni' : 'modulVitrini.fiyat.paketTeklifMetni')}
          </p>
        </>
      )}
      <Button asChild className="mt-5 h-11 w-full border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
        <a href="#talep" data-talep-baglanti>
          {t(m ? 'modulVitrini.form.baslikModul' : 'modulVitrini.form.baslikPaket')}
        </a>
      </Button>
    </section>
  );
}

/** "Hangisi bana uygun?" — iletişim formuna konu ile gider. */
export function VitrinCagrisi({ dil }: { dil: string }) {
  const { t } = useTranslation();
  return (
    <section
      className="cam-kart cam-mor rounded-2xl border border-purple-500/30 bg-purple-500/10 p-8 text-center"
      data-vitrin-cagrisi
    >
      <h2 className="mb-3 text-2xl font-bold">{t('modulVitrini.cta.baslik')}</h2>
      <p className="mx-auto mb-6 max-w-2xl text-muted-foreground">{t('modulVitrini.cta.metin')}</p>
      <Button asChild className="h-11 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
        <Link to={localizedPath(dil, 'contact')} state={{ kaynak: 'modul', konu: t('modulVitrini.cta.konu') }}>
          {t('modulVitrini.cta.dugme')}
        </Link>
      </Button>
    </section>
  );
}
