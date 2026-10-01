import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Activity,
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Gauge,
  Home,
  Loader2,
  MessageSquare,
  Printer,
  StickyNote,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { acikRapor, donemAdi, RaporHatasi, type AylikRapor } from '@/lib/aylikRapor';

/**
 * Aylık müşteri raporu: `/rapor-aylik/<jeton>` (Faz 2C).
 *
 * Yazdırmaya uygun tek sayfa: tarayıcının "Yazdır → PDF olarak kaydet"i
 * PDF'i üretiyor (sunucuda Playwright/WeasyPrint yok — ücretsiz Render
 * planı için ağır). Site düzeninin (menü, alt bilgi) dışında çiziliyor ki
 * çıktıda yalnız rapor olsun. Jeton imzalı; yalnız yayındaki rapor açılır
 * (yönetici oturumuyla taslak önizlenir). noindex, prerender yok.
 * Metinler 7 dilde (`aylikRapor` ek paketi); veriler olduğu gibi.
 */

const KART =
  'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5 print:break-inside-avoid print:rounded-none print:border-gray-300 print:bg-white';

function Bolum({ ikon: Ikon, baslik, children, testId }: { ikon: typeof Gauge; baslik: string; children: ReactNode; testId: string }) {
  return (
    <section className={KART} data-testid={testId}>
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <Ikon className="h-5 w-5 text-purple-300 print:text-black" aria-hidden="true" />
        {baslik}
      </h2>
      {children}
    </section>
  );
}

function Kutu({ etiket, deger, ek }: { etiket: string; deger: ReactNode; ek?: ReactNode }) {
  return (
    <div className="rounded-xl bg-white/[0.04] p-3 print:border print:border-gray-200 print:bg-white">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground print:text-gray-600">{etiket}</p>
      <p className="mt-1 text-2xl font-bold">{deger}</p>
      {ek && <p className="text-xs text-muted-foreground print:text-gray-600">{ek}</p>}
    </div>
  );
}

export default function AylikRaporSayfasi() {
  const { jeton = '' } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [rapor, setRapor] = useState<AylikRapor | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => etiket.remove();
  }, []);

  useEffect(() => {
    let iptal = false;
    acikRapor(jeton)
      .then((r) => {
        if (!iptal) setRapor(r);
      })
      .catch((h) => {
        if (!iptal) setHata(h instanceof RaporHatasi ? h.kod : 'genel');
      });
    return () => {
      iptal = true;
    };
  }, [jeton]);

  useEffect(() => {
    if (!rapor) return;
    const onceki = document.title;
    document.title = t('aylikRapor.sayfa.belgeBasligi', { donem: donemAdi(rapor.donem, dil) });
    return () => {
      document.title = onceki;
    };
  }, [rapor, t, dil]);

  const sayi = (n: number | null | undefined, basamak = 1) =>
    n === null || n === undefined ? '—' : n.toLocaleString(dil, { maximumFractionDigits: basamak });
  const yuzde = (n: number | null | undefined) => (n === null || n === undefined ? '—' : `%${sayi(n, 2)}`);
  const tarih = (d: string | null | undefined, saatli = false) => {
    if (!d) return '—';
    const x = new Date(d.length === 10 ? `${d}T12:00:00` : d);
    return Number.isNaN(x.getTime())
      ? '—'
      : x.toLocaleString(dil, { day: '2-digit', month: 'short', year: 'numeric', ...(saatli ? { hour: '2-digit', minute: '2-digit' } : {}) });
  };
  // Faz 2H: Core Web Vitals süreleri yerel birimle (2,9 sn / 240 ms).
  const sure = (ms: number | null | undefined) => {
    if (ms === null || ms === undefined) return '—';
    try {
      return new Intl.NumberFormat(dil, {
        style: 'unit',
        unit: ms >= 1000 ? 'second' : 'millisecond',
        maximumFractionDigits: ms >= 1000 ? 1 : 0,
      }).format(ms >= 1000 ? ms / 1000 : ms);
    } catch {
      return `${ms} ms`;
    }
  };
  const kalanRenk = (k: number | null) =>
    k === null ? '' : k < 0 ? 'text-red-300 print:text-red-700' : k <= 30 ? 'text-amber-200 print:text-amber-700' : 'text-emerald-200 print:text-emerald-700';

  if (hata) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4" data-testid="aylik-rapor-hata">
        <div className="cam-kart max-w-md rounded-3xl border border-white/10 bg-white/[0.03] p-8 text-center">
          <AlertCircle className="mx-auto mb-3 h-10 w-10 text-amber-300" aria-hidden="true" />
          <h1 className="text-xl font-semibold">{t('aylikRapor.sayfa.bulunamadi')}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{t('aylikRapor.sayfa.bulunamadiAciklama')}</p>
          <Link to="/" className="mt-6 inline-flex items-center gap-2 text-sm text-purple-300">
            <Home className="h-4 w-4" aria-hidden="true" /> {t('aylikRapor.sayfa.anaSayfa')}
          </Link>
        </div>
      </div>
    );
  }

  if (!rapor) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  const v = rapor.veri;
  const o = v.ozet;
  const analizVar = !(v.seo.length === 0 || v.seo.every((s) => s.puan === null));
  const izleme = v.seo_izleme ?? [];

  return (
    <div className="aylik-rapor min-h-screen px-4 py-10 print:p-0 print:text-black" data-testid="aylik-rapor-sayfasi">
      <style>{`@media print { html, body { background: #fff !important; color: #000 !important; } @page { margin: 14mm; } }`}</style>
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 pb-6 print:border-gray-300">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-purple-300 print:text-gray-600">mehmetkuru.dev</p>
            <h1 className="mt-2 text-3xl font-bold" data-testid="aylik-rapor-baslik">
              {t('aylikRapor.sayfa.baslik', { donem: donemAdi(rapor.donem, dil) })}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground print:text-gray-600">
              {v.musteri_adi ? `${v.musteri_adi} · ` : ''}
              {tarih(v.baslangic)} – {tarih(v.bitis)}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2 print:hidden">
            {rapor.durum === 'taslak' && (
              <span className="rounded-full bg-amber-500/20 px-3 py-1 text-xs text-amber-100" data-testid="aylik-rapor-taslak">
                {t('aylikRapor.sayfa.taslak')}
              </span>
            )}
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center gap-2 rounded-md bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-2 text-sm text-white"
              data-testid="aylik-rapor-yazdir"
            >
              <Printer className="h-4 w-4" aria-hidden="true" /> {t('aylikRapor.sayfa.yazdir')}
            </button>
          </div>
        </header>

        <Bolum ikon={ClipboardList} baslik={t('aylikRapor.bolum.ozet')} testId="bolum-ozet">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Kutu etiket={t('aylikRapor.ozet.isler')} deger={o.is_sayisi} />
            <Kutu
              etiket={t('aylikRapor.ozet.kredi')}
              deger={t('aylikRapor.ozet.saatDegeri', { sayi: sayi(o.harcanan_kredi, 2) })}
              ek={o.kredi_bakiye !== null ? t('aylikRapor.ozet.bakiye', { sayi: sayi(o.kredi_bakiye, 2) }) : undefined}
            />
            <Kutu
              etiket={t('aylikRapor.ozet.talepler')}
              deger={`${o.acilan_talep} / ${o.cozulen_talep}`}
              ek={t('aylikRapor.ozet.acilanCozulen')}
            />
            <Kutu
              etiket={t('aylikRapor.ozet.sla')}
              deger={o.sla_uyum_yuzde === null ? '—' : yuzde(o.sla_uyum_yuzde)}
              ek={o.sla_uyum_yuzde === null ? t('aylikRapor.ozet.slaYok') : t('aylikRapor.ozet.slaAyrinti', { uyumlu: o.sla_uyumlu, ihlal: o.sla_ihlal })}
            />
          </div>
          {o.tamamlanan_projeler.length > 0 && (
            <p className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-emerald-300 print:text-emerald-700" aria-hidden="true" />
              {t('aylikRapor.ozet.tamamlanan')}: {o.tamamlanan_projeler.map((p) => p.baslik).join(', ')}
            </p>
          )}
          <h3 className="mb-2 mt-5 text-sm font-semibold">{t('aylikRapor.ozet.yapilanlar')}</h3>
          {o.isler.length === 0 ? (
            <p className="text-sm text-muted-foreground print:text-gray-600">{t('aylikRapor.ozet.isYok')}</p>
          ) : (
            <ul className="divide-y divide-white/5 text-sm print:divide-gray-200">
              {o.isler.map((is, i) => (
                <li key={`${is.tarih}-${i}`} className="flex flex-wrap gap-x-3 py-1.5">
                  <span className="w-24 shrink-0 text-muted-foreground print:text-gray-600">{tarih(is.tarih)}</span>
                  <span className="min-w-0 flex-1">{is.baslik}</span>
                  {is.proje && <span className="text-xs text-muted-foreground print:text-gray-600">{is.proje}</span>}
                </li>
              ))}
            </ul>
          )}
        </Bolum>

        <Bolum ikon={Activity} baslik={t('aylikRapor.bolum.site')} testId="bolum-site">
          {v.site_sagligi.length === 0 ? (
            <p className="text-sm text-muted-foreground print:text-gray-600">{t('aylikRapor.site.yok')}</p>
          ) : (
            <div className="space-y-4">
              {v.site_sagligi.map((s) => (
                <div key={s.site_id} className="rounded-xl border border-white/10 p-4 print:border-gray-200">
                  <p className="font-medium">
                    {s.ad} {s.adres && <span className="break-all text-xs text-muted-foreground print:text-gray-600">· {s.adres}</span>}
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">
                    <Kutu
                      etiket={t('aylikRapor.site.uptime')}
                      deger={yuzde(s.uptime_yuzde)}
                      ek={s.olcum ? t('aylikRapor.site.olcum', { sayi: s.olcum }) : t('aylikRapor.site.olcumYok')}
                    />
                    <Kutu
                      etiket={t('aylikRapor.site.kesinti')}
                      deger={s.kesinti_sayisi}
                      ek={s.kesinti_sayisi ? t('aylikRapor.site.kesintiSure', { sayi: s.kesinti_dk }) : undefined}
                    />
                    <div className="col-span-2 space-y-1 rounded-xl bg-white/[0.04] p-3 text-sm md:col-span-1 print:border print:border-gray-200 print:bg-white">
                      {(
                        [
                          ['alan', s.alan_bitis, s.alan_kalan],
                          ['ssl', s.ssl_bitis, s.ssl_kalan],
                          ['hosting', s.hosting_bitis, s.hosting_kalan],
                        ] as const
                      ).map(([tur, bitis, kalan]) => (
                        <p key={tur} className="flex justify-between gap-2">
                          <span className="text-muted-foreground print:text-gray-600">{t(`aylikRapor.site.${tur}`)}</span>
                          <span className={kalanRenk(kalan)}>
                            {bitis ? `${tarih(bitis)} (${t('aylikRapor.site.kalan', { sayi: kalan ?? 0 })})` : '—'}
                          </span>
                        </p>
                      ))}
                    </div>
                  </div>
                  {s.kesintiler.length > 0 && (
                    <ul className="mt-3 space-y-1 text-xs text-muted-foreground print:text-gray-600">
                      {s.kesintiler.map((k, i) => (
                        <li key={`${k.baslangic}-${i}`}>
                          {tarih(k.baslangic, true)} · {t('aylikRapor.site.kesintiSure', { sayi: k.sure_dk })}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </Bolum>

        <Bolum ikon={Gauge} baslik={t('aylikRapor.bolum.seo')} testId="bolum-seo">
          {!analizVar ? (
            izleme.length === 0 ? (
              <p className="text-sm text-muted-foreground print:text-gray-600">{t('aylikRapor.seo.yok')}</p>
            ) : null
          ) : (
            <div className="space-y-3">
              {v.seo.map((s) => (
                <div key={s.alan_adi} className="flex flex-wrap items-center gap-4 rounded-xl border border-white/10 p-4 print:border-gray-200">
                  <div className="text-4xl font-bold" data-testid={`seo-puan-${s.alan_adi}`}>
                    {s.puan ?? '—'}
                  </div>
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-medium">{s.alan_adi}</p>
                    <p className="text-xs text-muted-foreground print:text-gray-600">
                      {t('aylikRapor.seo.tarih', { tarih: tarih(s.tarih) })}
                    </p>
                    {s.bolumler.length > 0 && (
                      <p className="mt-1 flex flex-wrap gap-2 text-xs">
                        {s.bolumler.map((b) => (
                          <span key={b.anahtar} className="rounded-full border border-white/10 px-2 py-0.5 print:border-gray-300">
                            {t(`aylikRapor.seo.bolum.${b.anahtar}`, { defaultValue: b.anahtar })}: {b.puan ?? '—'}
                          </span>
                        ))}
                      </p>
                    )}
                  </div>
                  {s.degisim !== null && (
                    <span
                      className={`inline-flex items-center gap-1 text-sm font-semibold ${
                        s.degisim >= 0 ? 'text-emerald-300 print:text-emerald-700' : 'text-red-300 print:text-red-700'
                      }`}
                    >
                      {s.degisim >= 0 ? <ArrowUpRight className="h-4 w-4" aria-hidden="true" /> : <ArrowDownRight className="h-4 w-4" aria-hidden="true" />}
                      {t('aylikRapor.seo.degisim', { sayi: `${s.degisim > 0 ? '+' : ''}${s.degisim}` })}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          {izleme.length > 0 && (
            <div className={analizVar ? 'mt-5' : ''} data-testid="seo-izleme-ozeti">
              <h3 className="mb-3 text-sm font-semibold">{t('aylikRapor.seoIzleme.baslik')}</h3>
              <div className="space-y-3">
                {izleme.map((s) => (
                  <div key={s.site_id} className="rounded-xl border border-white/10 p-4 print:border-gray-200" data-testid={`seo-izleme-${s.site_id}`}>
                    <div className="flex flex-wrap items-center gap-4">
                      <div className="text-4xl font-bold">{s.son_puan ?? '—'}</div>
                      <div className="min-w-0 flex-1 text-sm">
                        <p className="font-medium">{s.ad}</p>
                        <p className="text-xs text-muted-foreground print:text-gray-600">
                          {t('aylikRapor.seoIzleme.sonPuan')} · {t('aylikRapor.seoIzleme.olcum', { sayi: s.olcum_sayisi })} · {tarih(s.son_tarih)}
                        </p>
                        {s.en_dusuk !== null && s.en_yuksek !== null && (
                          <p className="text-xs text-muted-foreground print:text-gray-600">
                            {t('aylikRapor.seoIzleme.aralik', { dusuk: s.en_dusuk, yuksek: s.en_yuksek })}
                          </p>
                        )}
                      </div>
                      {s.degisim !== null && s.degisim !== 0 && (
                        <span
                          className={`inline-flex items-center gap-1 text-sm font-semibold ${
                            s.degisim > 0 ? 'text-emerald-300 print:text-emerald-700' : 'text-red-300 print:text-red-700'
                          }`}
                        >
                          {s.degisim > 0 ? <ArrowUpRight className="h-4 w-4" aria-hidden="true" /> : <ArrowDownRight className="h-4 w-4" aria-hidden="true" />}
                          {t('aylikRapor.seoIzleme.degisim', { sayi: `${s.degisim > 0 ? '+' : ''}${s.degisim}` })}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 flex flex-wrap gap-2 text-xs">
                      {(
                        [
                          [t('aylikRapor.seoIzleme.mobil'), s.son_mobil ?? '—'],
                          [t('aylikRapor.seoIzleme.masaustu'), s.son_masaustu ?? '—'],
                          ['LCP', sure(s.son_lcp_ms)],
                          ['CLS', s.son_cls === null ? '—' : sayi(s.son_cls, 3)],
                          ['TBT', sure(s.son_tbt_ms)],
                        ] as const
                      ).map(([etiket, deger]) => (
                        <span key={etiket} className="rounded-full border border-white/10 px-2 py-0.5 print:border-gray-300">
                          {etiket}: {deger}
                        </span>
                      ))}
                    </p>
                    {s.son_kritik.length > 0 && (
                      <p className="mt-2 text-xs text-red-300 print:text-red-700">
                        {t('aylikRapor.seoIzleme.kritik')}{' '}
                        {s.son_kritik.map((k) => t(`aylikRapor.seoIzleme.kritikKod.${k}`, { defaultValue: k })).join(', ')}
                      </p>
                    )}
                    {s.uyari_sayisi > 0 && (
                      <p className="mt-1 text-xs text-muted-foreground print:text-gray-600">
                        {t('aylikRapor.seoIzleme.uyari', { sayi: s.uyari_sayisi })}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Bolum>

        <Bolum ikon={CalendarClock} baslik={t('aylikRapor.bolum.plan')} testId="bolum-plan">
          {v.plan.acik_projeler.length + v.plan.acik_talepler.length + v.plan.bekleyen_belgeler.length === 0 ? (
            <p className="text-sm text-muted-foreground print:text-gray-600">{t('aylikRapor.plan.yok')}</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <h3 className="mb-2 text-sm font-semibold">{t('aylikRapor.plan.projeler')}</h3>
                <ul className="space-y-1 text-sm">
                  {v.plan.acik_projeler.map((p, i) => (
                    <li key={`${p.baslik}-${i}`}>
                      {p.baslik}
                      {typeof p.ilerleme === 'number' && <span className="text-muted-foreground print:text-gray-600"> · %{p.ilerleme}</span>}
                    </li>
                  ))}
                  {v.plan.acik_projeler.length === 0 && <li className="text-muted-foreground">—</li>}
                </ul>
              </div>
              <div>
                <h3 className="mb-2 flex items-center gap-1 text-sm font-semibold">
                  <MessageSquare className="h-4 w-4" aria-hidden="true" /> {t('aylikRapor.plan.talepler')}
                </h3>
                <ul className="space-y-1 text-sm">
                  {v.plan.acik_talepler.map((x) => (
                    <li key={x.no}>
                      #{x.no} {x.konu}
                    </li>
                  ))}
                  {v.plan.acik_talepler.length === 0 && <li className="text-muted-foreground">—</li>}
                </ul>
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold">{t('aylikRapor.plan.belgeler')}</h3>
                <ul className="space-y-1 text-sm">
                  {v.plan.bekleyen_belgeler.map((b, i) => (
                    <li key={`${b.baslik}-${i}`}>
                      {b.baslik}
                      {b.son_tarih && <span className="text-muted-foreground print:text-gray-600"> · {tarih(b.son_tarih)}</span>}
                    </li>
                  ))}
                  {v.plan.bekleyen_belgeler.length === 0 && <li className="text-muted-foreground">—</li>}
                </ul>
              </div>
            </div>
          )}
        </Bolum>

        {rapor.yonetici_notu && (
          <Bolum ikon={StickyNote} baslik={t('aylikRapor.bolum.not')} testId="bolum-not">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{rapor.yonetici_notu}</p>
          </Bolum>
        )}

        <footer className="pt-2 text-center text-xs text-muted-foreground print:text-gray-600">
          {t('aylikRapor.sayfa.altBilgi', { tarih: tarih(v.olusturma, true) })}
        </footer>
      </div>
    </div>
  );
}
