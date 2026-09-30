import { memo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Check, Cloud, Database, Layers, Server } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Sistem mimarisi gezgini.
 *
 * Dört katman soldan seçiliyor, sağda o katmanın ayrıntısı açılıyor.
 *
 * Teknoloji adları uydurma değil: "Kullanılan Araçlar" bölümündeki gerçek
 * listeden (`DEFAULT_TOOL_ORDER`) seçildi. Katman maddeleri de ölçülemez
 * iddialar değil, uygulanan pratikler — "şu kadar hızlı" demek yerine "ne
 * yapıyoruz" diyor; tutulamayacak bir söz vermiyoruz.
 */

const KATMANLAR = [
  { anahtar: 'arayuz', Icon: Layers, teknolojiler: ['React', 'TypeScript', 'Tailwind CSS', 'Vite'] },
  { anahtar: 'kenar', Icon: Cloud, teknolojiler: ['Cloudflare', 'Nginx', 'GitHub Actions'] },
  { anahtar: 'servis', Icon: Server, teknolojiler: ['Python', 'FastAPI', 'Node.js'] },
  { anahtar: 'veri', Icon: Database, teknolojiler: ['PostgreSQL', 'Redis', 'Supabase'] },
] as const;

/** Her katmanda dört madde var; i18n anahtarları `mimari.<katman>.m1..m4`. */
const MADDELER = ['m1', 'm2', 'm3', 'm4'] as const;

function MimariKatmanlari() {
  const { t } = useTranslation();
  const [secili, setSecili] = useState(0);
  const katman = KATMANLAR[secili];

  return (
    <section id="mimari" className="alt-bolum relative py-20 md:py-28 border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">
            {t('mimari.sectionTag')}
          </p>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold leading-tight">
            {t('mimari.title')} <span className="gradient-text">{t('mimari.titleHighlight')}</span>
          </h2>
          <p className="mt-5 text-muted-foreground leading-relaxed">{t('mimari.desc')}</p>
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-5">
          {/* Katman listesi */}
          <div className="space-y-3 lg:col-span-2">
            {KATMANLAR.map((k, i) => {
              const aktif = i === secili;
              return (
                <button
                  key={k.anahtar}
                  type="button"
                  onClick={() => setSecili(i)}
                  aria-pressed={aktif}
                  className={`flex w-full items-start gap-4 rounded-2xl border p-5 text-left transition-colors ${
                    aktif
                      ? 'border-primary/50 bg-primary/10'
                      : 'border-white/10 bg-white/[0.03] hover:border-white/25'
                  }`}
                >
                  <span
                    className={`flex h-10 w-10 flex-none items-center justify-center rounded-xl ${
                      aktif ? 'bg-primary/20' : 'bg-white/5'
                    }`}
                  >
                    <k.Icon
                      className={`h-5 w-5 ${aktif ? 'text-primary' : 'text-muted-foreground'}`}
                      aria-hidden="true"
                    />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-mono text-[11px] tracking-wider text-muted-foreground">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span className="mt-0.5 block font-semibold">
                      {t(`mimari.${k.anahtar}.ad`)}
                    </span>
                    <span className="mt-1 block truncate text-xs text-muted-foreground">
                      {k.teknolojiler.join(' · ')}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* Seçili katmanın ayrıntısı */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 sm:p-8 lg:col-span-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-purple-200">
              {t('mimari.detayEtiket')}
            </p>
            <h3 className="mt-3 text-xl font-bold sm:text-2xl">
              {String(secili + 1).padStart(2, '0')} · {t(`mimari.${katman.anahtar}.ad`)}
            </h3>
            <p className="mt-3 leading-relaxed text-muted-foreground">
              {t(`mimari.${katman.anahtar}.aciklama`)}
            </p>

            <p className="mt-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t('mimari.pratikler')}
            </p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {MADDELER.map((m) => (
                <li
                  key={m}
                  className="flex items-start gap-2 rounded-lg border border-white/10 px-3 py-2.5 text-sm"
                >
                  <Check className="mt-0.5 h-4 w-4 flex-none text-primary" aria-hidden="true" />
                  <span className="text-muted-foreground">
                    {t(`mimari.${katman.anahtar}.${m}`)}
                  </span>
                </li>
              ))}
            </ul>

            <p className="mt-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t('mimari.yigin')}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {katman.teknolojiler.map((tek) => (
                <span
                  key={tek}
                  className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 font-mono text-xs text-foreground"
                >
                  {tek}
                </span>
              ))}
            </div>

            <Link to="/contact" className="mt-7 block">
              <Button className="h-11 w-full gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-500 hover:to-pink-500 sm:w-auto sm:px-6">
                {t('mimari.cta')}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export default memo(MimariKatmanlari);
