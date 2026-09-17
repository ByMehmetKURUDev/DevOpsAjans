import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight,
  Bell,
  EyeOff,
  FileText,
  Flag,
  LayoutDashboard,
  MessageSquare,
  Paperclip,
  Receipt,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Müşteri paneli önizlemesi.
 *
 * Buradaki aşamalar uydurma değil: arka uçtaki `STAGES` listesinin aynısı
 * (`routers/project_events.py`). Müşteri panele girdiğinde gerçekten bu
 * altı aşamayı ve bu kayıt tiplerini görüyor.
 *
 * Bilerek yapılmayan şey: sahte tarih, sahte commit ve sahte ilerleme
 * yüzdesi. Prototipte bunlar vardı; gerçek bir projeden gelmediği için
 * ziyaretçiye yanlış söz veriyordu. Onun yerine kayıt BAŞLIKLARI örnek
 * olarak veriliyor ve bölüm "örnek görünüm" diye açıkça etiketleniyor.
 */

/** Arka uçtaki sıra — değişirse ikisi birlikte değişmeli. */
const ASAMALAR = ['discovery', 'design', 'build', 'review', 'launch', 'aftercare'] as const;
type Asama = (typeof ASAMALAR)[number];

/** Her aşamada panele düşen örnek kayıtlar; ikon gerçek kayıt tipini gösteriyor. */
const KAYIT_TIPLERI: Record<Asama, { tip: 'stage_change' | 'note' | 'file' | 'delivery'; n: 1 | 2 | 3 }[]> = {
  discovery: [{ tip: 'stage_change', n: 1 }, { tip: 'note', n: 2 }, { tip: 'file', n: 3 }],
  design: [{ tip: 'stage_change', n: 1 }, { tip: 'file', n: 2 }, { tip: 'note', n: 3 }],
  build: [{ tip: 'stage_change', n: 1 }, { tip: 'delivery', n: 2 }, { tip: 'note', n: 3 }],
  review: [{ tip: 'stage_change', n: 1 }, { tip: 'note', n: 2 }, { tip: 'file', n: 3 }],
  launch: [{ tip: 'stage_change', n: 1 }, { tip: 'delivery', n: 2 }, { tip: 'note', n: 3 }],
  aftercare: [{ tip: 'stage_change', n: 1 }, { tip: 'note', n: 2 }, { tip: 'delivery', n: 3 }],
};

const IKONLAR = {
  stage_change: Flag,
  note: MessageSquare,
  file: Paperclip,
  delivery: FileText,
} as const;

/** Panelin gerçek sekmeleri (`ClientPanel.tsx` içindeki `Tab` tipi). */
const SEKMELER = [
  { anahtar: 'projeler', Icon: LayoutDashboard },
  { anahtar: 'faturalar', Icon: Receipt },
  { anahtar: 'destek', Icon: MessageSquare },
] as const;

export default function MusteriPaneliOnizleme() {
  const { t } = useTranslation();
  const [secili, setSecili] = useState<Asama>('build');
  const seciliSira = ASAMALAR.indexOf(secili);

  return (
    <section id="panel" className="alt-bolum relative py-20 md:py-28 border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">
            {t('panel.sectionTag')}
          </p>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold leading-tight">
            {t('panel.title')} <span className="gradient-text">{t('panel.titleHighlight')}</span>
          </h2>
          <p className="mt-5 text-muted-foreground leading-relaxed">{t('panel.desc')}</p>
        </div>

        {/* Aşama rayı */}
        <div className="mt-12">
          <div className="flex items-center justify-between gap-1 text-[11px] uppercase tracking-wider text-muted-foreground">
            <span>{t('panel.rayEtiket')}</span>
            <span className="rounded-full border border-white/15 px-2.5 py-0.5 normal-case tracking-normal">
              {t('panel.ornekRozet')}
            </span>
          </div>

          <ol className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {ASAMALAR.map((a, i) => {
              const aktif = a === secili;
              const gecildi = i < seciliSira;
              return (
                <li key={a}>
                  <button
                    type="button"
                    onClick={() => setSecili(a)}
                    aria-pressed={aktif}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                      aktif
                        ? 'border-primary/50 bg-primary/10'
                        : gecildi
                          ? 'border-primary/25 bg-primary/[0.04] hover:border-primary/40'
                          : 'border-white/10 bg-white/[0.03] hover:border-white/25'
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className={`h-1.5 w-1.5 flex-none rounded-full ${
                          aktif || gecildi ? 'bg-primary' : 'bg-white/25'
                        }`}
                      />
                      <span className="font-mono text-[10px] tracking-wider text-muted-foreground">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                    </span>
                    <span className="mt-1 block text-sm font-medium">
                      {t(`panel.asama.${a}.ad`)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-5">
          {/* Panel çerçevesi */}
          <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] lg:col-span-3">
            {/* Sahte sekme çubuğu — panelin gerçek sekmeleri */}
            <div className="flex items-center gap-1 border-b border-white/10 px-3 py-2">
              {SEKMELER.map((s, i) => (
                <span
                  key={s.anahtar}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs ${
                    i === 0 ? 'bg-white/[0.06] text-foreground' : 'text-muted-foreground'
                  }`}
                >
                  <s.Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(`panel.sekme.${s.anahtar}`)}
                </span>
              ))}
            </div>

            <div className="p-5 sm:p-6">
              <p className="text-xs font-semibold uppercase tracking-wider text-purple-200">
                {t('panel.gecmisEtiket')}
              </p>
              <h3 className="mt-2 text-lg font-bold">{t(`panel.asama.${secili}.ad`)}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {t(`panel.asama.${secili}.aciklama`)}
              </p>

              <ol className="relative mt-5 space-y-3 border-s border-white/10 ps-6">
                {KAYIT_TIPLERI[secili].map(({ tip, n }) => {
                  const Ikon = IKONLAR[tip];
                  return (
                    <li key={n} className="relative">
                      <span className="absolute -start-[31px] top-1 flex h-5 w-5 items-center justify-center rounded-full border border-white/10 bg-background">
                        <Ikon className="h-3 w-3 text-primary" aria-hidden="true" />
                      </span>
                      <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                        <p className="text-sm font-medium">{t(`panel.asama.${secili}.k${n}`)}</p>
                        <p className="mt-1 text-[11px] uppercase tracking-wider text-muted-foreground/70">
                          {t(`panel.kayitTipi.${tip}`)}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          </div>

          {/* Panelin gerçekten yaptıkları */}
          <div className="space-y-3 lg:col-span-2">
            {[
              { Icon: Bell, anahtar: 'bildirim' },
              { Icon: EyeOff, anahtar: 'icNot' },
              { Icon: Receipt, anahtar: 'fatura' },
            ].map(({ Icon, anahtar }) => (
              <div
                key={anahtar}
                className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              >
                <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-primary/15">
                  <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
                </span>
                <span>
                  <span className="block font-semibold">{t(`panel.ozellik.${anahtar}.ad`)}</span>
                  <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">
                    {t(`panel.ozellik.${anahtar}.aciklama`)}
                  </span>
                </span>
              </div>
            ))}

            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <p className="text-sm text-muted-foreground">{t('panel.girisNotu')}</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link to="/contact">
                  <Button className="h-11 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500">
                    {t('panel.cta')}
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </Link>
                <Link to="/client">
                  <Button
                    variant="outline"
                    className="h-11 !bg-transparent border-white/25 hover:border-white/50"
                  >
                    {t('panel.ctaGiris')}
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
