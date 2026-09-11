import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Eye, EyeOff, Loader2, Lock, RotateCcw, Save } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SUPPORTED_LANGUAGES } from '@/i18n';
import {
  PAGE_KEYS,
  resolveSections,
  sectionsSettingKey,
  serializeSections,
  type ResolvedSection,
} from '@/lib/pageSections';
import {
  localizedSettingKey,
  saveSiteSetting,
  type SettingRow,
  type SettingsMap,
} from '@/lib/siteSettings';
import { PAGE_SEO, PAGE_SEO_KEYS } from '../../../prerender/site.js';

interface PageSectionsPanelProps {
  settings: SettingsMap;
  settingRows: SettingRow[];
  onSaved: () => Promise<void> | void;
}

/** Panelde listelenen sayfalar. Blog dizini yalnızca SEO metni taşıyor. */
const SAYFALAR = [...PAGE_KEYS, 'blog'];

const SAYFA_ADI: Record<string, string> = {
  home: 'nav.home',
  services: 'nav.services',
  portfolio: 'nav.portfolio',
  contact: 'nav.contact',
  blog: 'nav.blog',
};

/**
 * Site Sayfaları.
 *
 * İki işi bir arada yapıyor:
 *  1. Sayfadaki bölümlerin sırasını ve görünürlüğünü değiştirmek.
 *  2. Her sayfanın başlık ve açıklamasını yedi dilde düzenlemek.
 *
 * SEO metinleri derleme sırasında da okunuyor (prerender/settings.js), yani
 * buradan yapılan değişiklik Google'ın gördüğü metne de yansıyor — ama
 * ancak site yeniden yayınlandığında. Ziyaretçi tarafında anında geçerli.
 */
export default function PageSectionsPanel({
  settings,
  settingRows,
  onSaved,
}: PageSectionsPanelProps) {
  const { t } = useTranslation();
  const [aktifSayfa, setAktifSayfa] = useState<string>(SAYFALAR[0]);
  const [aktifDil, setAktifDil] = useState<string>('tr');
  const [bolumler, setBolumler] = useState<ResolvedSection[]>([]);
  const [seo, setSeo] = useState<Record<string, string>>({});
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const bolumluMu = aktifSayfa !== 'blog';

  useEffect(() => {
    setBolumler(bolumluMu ? resolveSections(aktifSayfa, settings) : []);
  }, [aktifSayfa, settings, bolumluMu]);

  const seoAnahtarlari = useMemo(() => PAGE_SEO_KEYS[aktifSayfa], [aktifSayfa]);

  useEffect(() => {
    if (!seoAnahtarlari) return;
    const taslak: Record<string, string> = {};
    (['title', 'description'] as const).forEach((alan) => {
      SUPPORTED_LANGUAGES.forEach((dil) => {
        const anahtar = localizedSettingKey(seoAnahtarlari[alan], dil.code);
        taslak[anahtar] = settings[anahtar] ?? '';
      });
    });
    setSeo(taslak);
  }, [seoAnahtarlari, settings]);

  const tasi = (index: number, yon: -1 | 1) => {
    const hedef = index + yon;
    if (hedef < 0 || hedef >= bolumler.length) return;
    const kopya = [...bolumler];
    [kopya[index], kopya[hedef]] = [kopya[hedef], kopya[index]];
    setBolumler(kopya);
  };

  const gorunurlukDegistir = (index: number) => {
    const kopya = [...bolumler];
    if (kopya[index].locked) return;
    kopya[index] = { ...kopya[index], visible: !kopya[index].visible };
    setBolumler(kopya);
  };

  const varsayilanaDon = () => {
    setBolumler(resolveSections(aktifSayfa, {}));
  };

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      if (bolumluMu) {
        await saveSiteSetting(
          settingRows,
          sectionsSettingKey(aktifSayfa),
          serializeSections(bolumler),
          'pages',
          `${t(SAYFA_ADI[aktifSayfa])} — ${t('pageSections.orderLabel')}`,
        );
      }

      if (seoAnahtarlari) {
        for (const [anahtar, deger] of Object.entries(seo)) {
          const mevcut = settingRows.find((r) => r.setting_key === anahtar);
          if ((mevcut?.setting_value ?? '') === deger) continue;
          await saveSiteSetting(settingRows, anahtar, deger, 'pages', anahtar);
        }
      }

      toast.success(t('pageSections.saved', { page: t(SAYFA_ADI[aktifSayfa]) }));
      await onSaved();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err?.message || t('admin.settingsSaveError'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const varsayilanSeo = (alan: 'title' | 'description') =>
    PAGE_SEO[aktifDil]?.[aktifSayfa]?.[alan] ?? '';

  return (
    <div className="space-y-8">
      {/* Sayfa seçimi */}
      <div className="flex flex-wrap gap-2" role="group" aria-label={t('pageSections.pickPage')}>
        {SAYFALAR.map((sayfa) => (
          <button
            key={sayfa}
            type="button"
            onClick={() => setAktifSayfa(sayfa)}
            aria-pressed={aktifSayfa === sayfa}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition-colors ${
              aktifSayfa === sayfa
                ? 'border-purple-400 bg-purple-500/20 text-white'
                : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-purple-500/40 hover:text-white'
            }`}
          >
            {t(SAYFA_ADI[sayfa])}
          </button>
        ))}
      </div>

      {/* Bölüm sırası */}
      {bolumluMu ? (
        <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-lg font-semibold">{t('pageSections.orderTitle')}</h3>
            <Button type="button" variant="outline" size="sm" onClick={varsayilanaDon} className="gap-2">
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              {t('pageSections.reset')}
            </Button>
          </div>
          <p className="mb-5 text-sm text-muted-foreground">{t('pageSections.orderDesc')}</p>

          <ol className="space-y-2">
            {bolumler.map((bolum, index) => (
              <li
                key={bolum.key}
                className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 transition-colors ${
                  bolum.visible
                    ? 'border-white/10 bg-white/[0.03]'
                    : 'border-dashed border-white/10 bg-transparent opacity-60'
                }`}
              >
                <span className="w-6 font-mono text-xs text-muted-foreground">{index + 1}</span>
                <span className="flex-1 min-w-[8rem] font-medium">{t(bolum.labelKey)}</span>

                {bolum.locked ? (
                  <span
                    className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
                    title={t('pageSections.lockedHint')}
                  >
                    <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('pageSections.locked')}
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => gorunurlukDegistir(index)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs hover:border-purple-500/40"
                    aria-pressed={bolum.visible}
                  >
                    {bolum.visible ? (
                      <>
                        <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('pageSections.visible')}
                      </>
                    ) : (
                      <>
                        <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('pageSections.hidden')}
                      </>
                    )}
                  </button>
                )}

                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => tasi(index, -1)}
                    disabled={index === 0}
                    aria-label={t('pageSections.moveUp')}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 disabled:opacity-30 hover:border-purple-500/40"
                  >
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => tasi(index, 1)}
                    disabled={index === bolumler.length - 1}
                    aria-label={t('pageSections.moveDown')}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 disabled:opacity-30 hover:border-purple-500/40"
                  >
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* Sayfa SEO metinleri */}
      {seoAnahtarlari ? (
        <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
          <h3 className="text-lg font-semibold">{t('pageSections.seoTitle')}</h3>
          <p className="mb-5 text-sm text-muted-foreground">{t('pageSections.seoDesc')}</p>

          <div className="mb-5 flex flex-wrap gap-2" role="group" aria-label={t('pageSections.pickLang')}>
            {SUPPORTED_LANGUAGES.map((dil) => (
              <button
                key={dil.code}
                type="button"
                onClick={() => setAktifDil(dil.code)}
                aria-pressed={aktifDil === dil.code}
                className={`rounded-lg border px-3 py-1.5 text-xs font-semibold uppercase transition-colors ${
                  aktifDil === dil.code
                    ? 'border-purple-400 bg-purple-500/20 text-white'
                    : 'border-white/10 text-muted-foreground hover:border-purple-500/40 hover:text-white'
                }`}
              >
                {dil.code}
              </button>
            ))}
          </div>

          <div className="grid gap-5">
            <div className="grid gap-2">
              <Label htmlFor={`seo-baslik-${aktifSayfa}-${aktifDil}`}>
                {t('pageSections.metaTitle')}
              </Label>
              <Input
                id={`seo-baslik-${aktifSayfa}-${aktifDil}`}
                value={seo[localizedSettingKey(seoAnahtarlari.title, aktifDil)] ?? ''}
                onChange={(e) =>
                  setSeo((s) => ({
                    ...s,
                    [localizedSettingKey(seoAnahtarlari.title, aktifDil)]: e.target.value,
                  }))
                }
                placeholder={varsayilanSeo('title')}
              />
              <p className="text-xs text-muted-foreground">
                {t('pageSections.fallbackHint')}
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor={`seo-aciklama-${aktifSayfa}-${aktifDil}`}>
                {t('pageSections.metaDesc')}
              </Label>
              <Textarea
                id={`seo-aciklama-${aktifSayfa}-${aktifDil}`}
                rows={3}
                value={seo[localizedSettingKey(seoAnahtarlari.description, aktifDil)] ?? ''}
                onChange={(e) =>
                  setSeo((s) => ({
                    ...s,
                    [localizedSettingKey(seoAnahtarlari.description, aktifDil)]: e.target.value,
                  }))
                }
                placeholder={varsayilanSeo('description')}
              />
            </div>
          </div>
        </section>
      ) : null}

      <div className="flex justify-end">
        <Button type="button" onClick={kaydet} disabled={kaydediliyor} className="gap-2">
          {kaydediliyor ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Save className="h-4 w-4" aria-hidden="true" />
          )}
          {t('pageSections.save')}
        </Button>
      </div>
    </div>
  );
}
