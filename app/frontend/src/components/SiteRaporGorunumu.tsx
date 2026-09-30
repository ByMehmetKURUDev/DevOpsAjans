import { useEffect, type ReactNode } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Info,
  Link2Off,
  Printer,
  XCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { Button } from '@/components/ui/button';
import {
  BOLUM_SIRASI,
  puanDerecesi,
  puanRengi,
  type Bolum,
  type Bulgu,
  type Seviye,
  type TamRapor,
} from '@/lib/siteAnalizi';

/**
 * Site analiz raporunun ortak görünümü.
 *
 * Üç yerde aynı rapor gösteriliyor: e-postadaki bağlantının açtığı
 * `/rapor/:jeton` sayfası, yönetici panelindeki "Site analizleri" sekmesi
 * ve müşteri panelindeki "Analiz" sekmesi. Görünüm tek yerde ki üçü
 * ayrışmasın.
 *
 * Bulgu metinleri arka uçtan gelmiyor; `kod` + `deger` geliyor ve cümle
 * burada yedi dilde kuruluyor (`siteAnalizi.bulgu.<kod>`).
 *
 * Yazdırma: rapor açıkken gövdeye `rapor-yazdir` sınıfı ekleniyor;
 * `index.css`'teki yazdırma kuralı sayfada yalnız raporu bırakıp arka
 * planı beyaza çeviriyor.
 */

const SEVIYE_BICIMI: Record<Seviye, { renk: string; Ikon: typeof AlertTriangle }> = {
  hata: { renk: 'text-red-300', Ikon: XCircle },
  uyari: { renk: 'text-amber-300', Ikon: AlertTriangle },
  bilgi: { renk: 'text-sky-300', Ikon: Info },
  iyi: { renk: 'text-emerald-300', Ikon: CheckCircle2 },
};

const HALKA_RENGI = (puan: number | null) =>
  puan == null ? '#64748b' : puan >= 90 ? '#34d399' : puan >= 50 ? '#fbbf24' : '#f87171';

export function bulguBasligi(t: TFunction, b: Bulgu): string {
  return t(`siteAnalizi.bulgu.${b.kod}.baslik`, { deger: b.deger ?? '', defaultValue: b.kod });
}

/** Genel ya da bölüm puanı için SVG halka. */
export function PuanHalkasi({
  puan,
  boyut = 128,
  etiket,
}: {
  puan: number | null;
  boyut?: number;
  etiket?: string;
}) {
  const { t } = useTranslation();
  const yaricap = 52;
  const cevre = 2 * Math.PI * yaricap;
  const oran = puan == null ? 0 : Math.max(0, Math.min(100, puan)) / 100;
  return (
    <div className="relative inline-flex flex-none items-center justify-center" style={{ width: boyut, height: boyut }}>
      <svg viewBox="0 0 120 120" width={boyut} height={boyut} role="img" aria-label={`${etiket ?? ''} ${puan ?? '—'}/100`}>
        <circle cx="60" cy="60" r={yaricap} fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="10" />
        <circle
          cx="60"
          cy="60"
          r={yaricap}
          fill="none"
          stroke={HALKA_RENGI(puan)}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${cevre * oran} ${cevre}`}
          transform="rotate(-90 60 60)"
          style={{ transition: 'stroke-dasharray 0.8s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className={`text-3xl font-bold leading-none ${puanRengi(puan)}`} style={{ fontSize: boyut / 4 }}>
          {puan ?? '—'}
        </span>
        {etiket ? (
          <span className="mt-1 text-[10px] uppercase tracking-widest text-muted-foreground">{etiket}</span>
        ) : puan == null ? (
          <span className="mt-1 text-[10px] text-muted-foreground">{t('siteAnalizi.olculemedi')}</span>
        ) : null}
      </div>
    </div>
  );
}

/** Tek bulgu satırı. `ayrintili` ise "neden önemli / ne yapılmalı" da yazılır. */
export function BulguSatiri({ bulgu, ayrintili = false }: { bulgu: Bulgu; ayrintili?: boolean }) {
  const { t } = useTranslation();
  const bicim = SEVIYE_BICIMI[bulgu.seviye] ?? SEVIYE_BICIMI.bilgi;
  const Ikon = bicim.Ikon;
  const deger = { deger: bulgu.deger ?? '' };
  return (
    <li className="flex items-start gap-2.5 text-sm leading-snug">
      <Ikon className={`mt-0.5 h-4 w-4 flex-none ${bicim.renk}`} aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-medium">{bulguBasligi(t, bulgu)}</p>
        {ayrintili && (
          <div className="mt-1 space-y-1 text-xs leading-relaxed text-muted-foreground">
            <p>
              <span className="font-semibold text-foreground/80">{t('siteAnalizi.rapor.neden')}: </span>
              {t(`siteAnalizi.bulgu.${bulgu.kod}.neden`, { ...deger, defaultValue: '' })}
            </p>
            <p>
              <span className="font-semibold text-foreground/80">{t('siteAnalizi.rapor.oneri')}: </span>
              {t(`siteAnalizi.bulgu.${bulgu.kod}.oneri`, { ...deger, defaultValue: '' })}
            </p>
          </div>
        )}
      </div>
    </li>
  );
}

/** Bölüm kartı (özet ya da tam). */
export function BolumKarti({
  bolum,
  ayrintili = false,
  alt,
}: {
  bolum: Bolum;
  ayrintili?: boolean;
  alt?: ReactNode;
}) {
  const { t } = useTranslation();
  const derece = puanDerecesi(bolum.puan);
  return (
    <section className="rapor-bolum cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">{t(`siteAnalizi.bolum.${bolum.anahtar}`)}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{t(`siteAnalizi.bolumAciklama.${bolum.anahtar}`)}</p>
        </div>
        <div className="text-right">
          <span className={`text-2xl font-bold ${puanRengi(bolum.puan)}`}>{bolum.puan ?? '—'}</span>
          <span className="block text-[11px] text-muted-foreground">
            {bolum.durum === 'olculemedi'
              ? t('siteAnalizi.olculemedi')
              : derece
                ? t(`siteAnalizi.derece.${derece}`)
                : ''}
          </span>
        </div>
      </div>
      {bolum.bulgular.length > 0 && (
        <ul className={`mt-4 ${ayrintili ? 'space-y-4' : 'space-y-2.5'}`}>
          {bolum.bulgular.map((b, i) => (
            <BulguSatiri key={`${b.kod}-${i}`} bulgu={b} ayrintili={ayrintili} />
          ))}
        </ul>
      )}
      {alt}
    </section>
  );
}

function kisaYol(tam: string, koken: string): string {
  const yol = tam.startsWith(koken) ? tam.slice(koken.length) : tam;
  return yol || '/';
}

function tarihBicimle(deger: string | null | undefined, dil: string): string {
  if (!deger) return '';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '';
  return an.toLocaleDateString(dil, { day: '2-digit', month: 'long', year: 'numeric' });
}

export default function SiteRaporGorunumu({
  rapor,
  yazdirilabilir = false,
  ust,
}: {
  rapor: TamRapor;
  yazdirilabilir?: boolean;
  ust?: ReactNode;
}) {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    document.body.classList.add('rapor-yazdir');
    return () => document.body.classList.remove('rapor-yazdir');
  }, []);

  const ayrinti = rapor.ayrinti || {};
  const koken = (() => {
    try {
      return new URL(ayrinti.son_url || rapor.url).origin;
    } catch {
      return '';
    }
  })();
  const bolumler = BOLUM_SIRASI.map((a) => rapor.bolumler.find((b) => b.anahtar === a)).filter(
    (b): b is Bolum => Boolean(b),
  );
  const hiz = ayrinti.hiz || {};
  const kiriklar = ayrinti.kirik_baglantilar || [];
  const sayfalar = ayrinti.sayfalar || [];
  const zincir = ayrinti.yonlendirmeler || [];

  return (
    <div className="site-rapor space-y-6">
      {ust}
      <div className="cam-kart cam-gok rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
          <PuanHalkasi puan={rapor.puan} boyut={144} etiket={t('siteAnalizi.genelPuan')} />
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.3em] text-purple-300">{t('siteAnalizi.rapor.baslik')}</p>
            <h2 className="mt-2 break-all text-2xl font-bold md:text-3xl">{rapor.alan_adi}</h2>
            <a
              href={rapor.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="mt-1 inline-flex items-center gap-1 break-all text-sm text-muted-foreground hover:text-foreground"
            >
              {rapor.url}
              <ExternalLink className="h-3 w-3 flex-none" aria-hidden="true" />
            </a>
            <p className="mt-2 text-xs text-muted-foreground">
              {t('siteAnalizi.rapor.tarih')}: {tarihBicimle(rapor.created_at, i18n.language)}
              {rapor.jeton_son ? (
                <>
                  {' · '}
                  {t('siteAnalizi.rapor.gecerlilik', { tarih: tarihBicimle(rapor.jeton_son, i18n.language) })}
                </>
              ) : null}
            </p>
          </div>
          {yazdirilabilir && (
            <Button variant="outline" onClick={() => window.print()} className="yazdirma gap-2 self-start">
              <Printer className="h-4 w-4" aria-hidden="true" />
              {t('siteAnalizi.rapor.yazdir')}
            </Button>
          )}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {bolumler.map((b) => (
            <div key={b.anahtar} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-center">
              <p className="text-[11px] text-muted-foreground">{t(`siteAnalizi.bolum.${b.anahtar}`)}</p>
              <p className={`text-xl font-bold ${puanRengi(b.puan)}`}>{b.puan ?? '—'}</p>
            </div>
          ))}
        </div>
      </div>

      {bolumler.map((b) => (
        <BolumKarti
          key={b.anahtar}
          bolum={b}
          ayrintili
          alt={
            b.anahtar === 'hiz' && (hiz.mobil || hiz.masaustu) ? (
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {(['mobil', 'masaustu'] as const).map((s) => {
                  const o = hiz[s];
                  return (
                    <div key={s} className="rounded-xl border border-white/10 p-3 text-xs">
                      <p className="mb-1 font-semibold">{t(`siteAnalizi.rapor.${s}`)}</p>
                      {o ? (
                        <p className="text-muted-foreground">
                          {t('siteAnalizi.rapor.hizSatiri', {
                            puan: o.puan,
                            lcp: o.lcp_ms != null ? (o.lcp_ms / 1000).toFixed(1) : '—',
                            cls: o.cls != null ? o.cls.toFixed(3) : '—',
                            tbt: o.tbt_ms != null ? Math.round(o.tbt_ms) : '—',
                          })}
                        </p>
                      ) : (
                        <p className="text-muted-foreground">{t('siteAnalizi.olculemedi')}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : b.anahtar === 'icerik' && kiriklar.length > 0 ? (
              <div className="mt-5 rounded-xl border border-red-400/30 bg-red-500/[0.06] p-4">
                <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
                  <Link2Off className="h-4 w-4 text-red-300" aria-hidden="true" />
                  {t('siteAnalizi.rapor.kirikBaglantilar')}
                </p>
                <ul className="space-y-1.5 text-xs">
                  {kiriklar.map((k) => (
                    <li key={k.url} className="break-all">
                      <span className="font-mono">{kisaYol(k.url, koken)}</span>
                      <span className="ml-2 text-red-300">
                        {k.durum === 0 ? t('siteAnalizi.rapor.ulasilamadi') : k.durum}
                      </span>
                      {k.kaynak ? (
                        <span className="block text-muted-foreground">
                          {t('siteAnalizi.rapor.kaynak')}: {kisaYol(k.kaynak, koken)}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null
          }
        />
      ))}

      <section className="rapor-bolum cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <h3 className="text-lg font-semibold">{t('siteAnalizi.rapor.ayrinti')}</h3>
        {typeof ayrinti.denetlenen_baglanti === 'number' && (
          <p className="mt-1 text-xs text-muted-foreground">
            {t('siteAnalizi.rapor.denetlenen', { sayi: ayrinti.denetlenen_baglanti })}
          </p>
        )}

        {zincir.length > 1 && (
          <div className="mt-4">
            <p className="mb-1 text-sm font-semibold">{t('siteAnalizi.rapor.yonlendirmeler')}</p>
            <ol className="space-y-1 text-xs">
              {zincir.map((z, i) => (
                <li key={`${z.url}-${i}`} className="break-all font-mono text-muted-foreground">
                  {z.durum} → {z.url}
                </li>
              ))}
            </ol>
          </div>
        )}

        {sayfalar.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <p className="mb-2 text-sm font-semibold">
              {t('siteAnalizi.rapor.sayfalar', { sayi: sayfalar.length })}
            </p>
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3 font-medium">URL</th>
                  <th className="py-1 pr-3 font-medium">{t('siteAnalizi.rapor.durum')}</th>
                  <th className="py-1 font-medium">ms</th>
                </tr>
              </thead>
              <tbody>
                {sayfalar.map((s) => (
                  <tr key={s.url} className="border-t border-white/5">
                    <td className="max-w-[18rem] break-all py-1 pr-3 font-mono">{kisaYol(s.url, koken)}</td>
                    <td className={`py-1 pr-3 ${s.durum >= 400 || s.durum === 0 ? 'text-red-300' : ''}`}>
                      {s.durum || '—'}
                    </td>
                    <td className="py-1">{s.sure_ms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
