import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CalendarDays, ClipboardCheck, LayoutTemplate, Palette, PenTool, Sparkles } from 'lucide-react';

import { SECIM, Yukleniyor } from '@/components/icerikStudyosu/ortak';
import { hataMetni, studyoApi, type HesapSecenegi, type Meta, type StudyoMod } from '@/lib/icerikStudyosu';

const Planlayici = lazy(() => import('@/components/icerikStudyosu/Planlayici'));
const AiYazar = lazy(() => import('@/components/icerikStudyosu/AiYazar'));
const MarkaSesi = lazy(() => import('@/components/icerikStudyosu/MarkaSesi'));
const Sablonlar = lazy(() => import('@/components/icerikStudyosu/Sablonlar'));
const Onaylar = lazy(() => import('@/components/icerikStudyosu/Onaylar'));

/**
 * Faz 5I — "İçerik stüdyosu" sekmesi. Yönetici panelinde (`mod="yonetici"`; mevcut "İçerik"
 * sekmesinin yerini aldı — eski içerik takvimi kayıtları burada) ve müşteri panelinde
 * (`mod="musteri"`; modül `icerik_studyosu`) aynı bileşen.
 *
 * Yönetici üstte hesap seçer: "Ajans" (kendi içeriği) ya da bir müşteri (ajans müşteri İÇİN
 * içerik hazırlar → müşteri onayına sunar). Müşteri kendi içeriğini yönetir.
 *
 * Alt sekmeler: Planlayıcı (takvim/liste), AI yazar, Marka sesi, Şablonlar, Onaylar.
 */

export type AltSekme = 'planlayici' | 'yazar' | 'marka' | 'sablonlar' | 'onaylar';
const ALT_SEKMELER: { anahtar: AltSekme; ikon: typeof CalendarDays }[] = [
  { anahtar: 'planlayici', ikon: CalendarDays },
  { anahtar: 'yazar', ikon: Sparkles },
  { anahtar: 'marka', ikon: Palette },
  { anahtar: 'sablonlar', ikon: LayoutTemplate },
  { anahtar: 'onaylar', ikon: ClipboardCheck },
];
const HESAP_ANAHTARI = 'icerikStudyosu.hesap';

/** Yapay zekâ yazarından planlayıcıya aktarılan taslak. */
export interface PlanTaslagi {
  baslik: string;
  metin: string;
  kanallar: string[];
  marka_id: number | null;
  uretim_id: number | null;
}

function ilkAlt(): AltSekme {
  try {
    const s = new URLSearchParams(window.location.search).get('alt') as AltSekme | null;
    return s && ALT_SEKMELER.some((x) => x.anahtar === s) ? s : 'planlayici';
  } catch {
    return 'planlayici';
  }
}

function ilkGonderi(): number | null {
  try {
    const n = Number(new URLSearchParams(window.location.search).get('gonderi'));
    return Number.isInteger(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

export default function IcerikStudyosu({ mod }: { mod: StudyoMod }) {
  const { t } = useTranslation();
  const [hesap, setHesap] = useState<string>(() => {
    if (mod !== 'yonetici') return '';
    try {
      return localStorage.getItem(HESAP_ANAHTARI) || '';
    } catch {
      return '';
    }
  });
  const [hesaplar, setHesaplar] = useState<HesapSecenegi[]>([]);
  const api = useMemo(() => studyoApi(mod, hesap || null), [mod, hesap]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [alt, setAlt] = useState<AltSekme>(ilkAlt);
  const [taslak, setTaslak] = useState<PlanTaslagi | null>(null);
  const [acilacak, setAcilacak] = useState<number | null>(ilkGonderi);

  const metaYukle = useCallback(async () => {
    try {
      setMeta(await api.meta());
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void metaYukle();
  }, [metaYukle]);

  useEffect(() => {
    if (mod !== 'yonetici') return;
    api
      .hesaplar()
      .then((r) => setHesaplar(r.items))
      .catch(() => setHesaplar([]));
    // Yalnız ilk açılışta (hesap listesi hesaptan bağımsız).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mod]);

  const hesapSec = (e: string) => {
    setHesap(e);
    try {
      localStorage.setItem(HESAP_ANAHTARI, e);
    } catch {
      /* depolama yok */
    }
  };

  const planlayiciyaAktar = (tg: PlanTaslagi) => {
    setTaslak(tg);
    setAlt('planlayici');
  };

  const seciliHesap = hesaplar.find((h) => h.eposta === hesap);

  return (
    <section data-testid="icerik-studyosu" data-mod={mod} className="min-w-0">
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-2xl font-bold" id="icerik-studyosu-baslik">
            <PenTool className="h-6 w-6 text-fuchsia-300" aria-hidden="true" />
            {t('icerikStudyosu.baslik')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            {mod === 'yonetici' ? t('icerikStudyosu.aciklamaYonetici') : t('icerikStudyosu.aciklama')}
          </p>
        </div>
        {mod === 'yonetici' && (
          <label className="block w-full text-sm lg:w-80">
            <span className="mb-1 block text-xs text-muted-foreground">{t('icerikStudyosu.hesap.etiket')}</span>
            <select className={SECIM} value={hesap} onChange={(e) => hesapSec(e.target.value)} data-testid="is-hesap">
              <option value="">{t('icerikStudyosu.hesap.ajans')}</option>
              {hesap && !seciliHesap && <option value={hesap}>{hesap}</option>}
              {hesaplar.map((h) => (
                <option key={h.eposta} value={h.eposta}>
                  {h.ad ? `${h.ad} — ${h.eposta}` : h.eposta}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {mod === 'yonetici' && hesap && (
        <p className="mb-3 rounded-xl border border-fuchsia-400/30 bg-fuchsia-500/10 px-4 py-2.5 text-sm text-fuchsia-100" data-testid="is-musteri-baglami">
          {t('icerikStudyosu.hesap.musteriIcin', { hesap })}
          {seciliHesap && !seciliHesap.modul_acik ? ` ${t('icerikStudyosu.hesap.modulKapali')}` : ''}
        </p>
      )}
      {hata && (
        <p className="mb-4 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200" role="alert">
          {hata}
        </p>
      )}
      {meta && !meta.ai_hazir && (
        <p className="mb-3 flex items-start gap-2 rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100" data-testid="is-uyari-ai">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t('icerikStudyosu.uyariAiKapali')}</span>
        </p>
      )}
      {meta?.sahte_mod && (
        <p className="mb-3 flex items-start gap-2 rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-3 text-sm text-sky-100" data-testid="is-uyari-sahte">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t('icerikStudyosu.uyariSahte')}</span>
        </p>
      )}

      <div className="-mx-1 mb-5 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('icerikStudyosu.baslik')}>
        {ALT_SEKMELER.map(({ anahtar, ikon: Ikon }) => (
          <button
            key={anahtar}
            type="button"
            role="tab"
            aria-selected={alt === anahtar}
            onClick={() => setAlt(anahtar)}
            data-is-alt={anahtar}
            className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
              alt === anahtar ? 'bg-fuchsia-500/20 text-white ring-1 ring-fuchsia-400/40' : 'text-muted-foreground hover:bg-white/5 hover:text-white'
            }`}
          >
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`icerikStudyosu.alt.${anahtar}`)}
          </button>
        ))}
      </div>

      {!meta && !hata ? (
        <Yukleniyor />
      ) : meta ? (
        <Suspense fallback={<Yukleniyor />}>
          {alt === 'planlayici' && (
            <Planlayici
              key={hesap}
              api={api}
              meta={meta}
              taslak={taslak}
              onTaslakKullanildi={() => setTaslak(null)}
              acilacak={acilacak}
              onAcildi={() => setAcilacak(null)}
            />
          )}
          {alt === 'yazar' && <AiYazar key={hesap} api={api} meta={meta} onPlanla={planlayiciyaAktar} metaYenile={metaYukle} />}
          {alt === 'marka' && <MarkaSesi key={hesap} api={api} meta={meta} />}
          {alt === 'sablonlar' && <Sablonlar key={hesap} api={api} meta={meta} />}
          {alt === 'onaylar' && <Onaylar key={hesap} api={api} meta={meta} onAc={(id) => { setAcilacak(id); setAlt('planlayici'); }} />}
        </Suspense>
      ) : null}

      <p className="mt-6 text-xs text-muted-foreground">{t('icerikStudyosu.yayinNotu')}</p>
    </section>
  );
}
