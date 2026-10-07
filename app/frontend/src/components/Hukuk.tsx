import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calculator, CalendarDays, FolderKanban, MessageSquare, Scale, Settings2, Users } from 'lucide-react';

import { KART, Not, SekmeDugmesi, Yukleniyor } from '@/components/hukuk/ortak';
import { hataMetni, hukukApi, type HukukMod, type Meta } from '@/lib/hukuk';

const Dosyalar = lazy(() => import('@/components/hukuk/Dosyalar'));
const Muvekkiller = lazy(() => import('@/components/hukuk/Muvekkiller'));
const Takvim = lazy(() => import('@/components/hukuk/Takvim'));
const SureHesaplayici = lazy(() => import('@/components/hukuk/SureHesaplayici'));
const Mesajlar = lazy(() => import('@/components/hukuk/Mesajlar'));
const Ayarlar = lazy(() => import('@/components/hukuk/Ayarlar'));
const YonetimOzeti = lazy(() => import('@/components/hukuk/YonetimOzeti'));

/**
 * Faz 6H — "Hukuk" sekmesi. Müşteri panelinde (`mod="musteri"`) hukuk bürosunun çalışma alanı; menüde TEK
 * sekme, bölümler burada alt gezinme: Dosyalar, Müvekkiller, Takvim, Süre hesaplayıcı, Mesajlar, Ayarlar.
 * Yönetici panelinde (`mod="yonetici"`) YALNIZ meta veri (hesap başına sayılar) — avukat–müvekkil sırrı.
 * AI yok; UYAP'tan otomatik veri çekilmez (arayüzde açıkça yazıyor).
 */

export type Alt = 'dosyalar' | 'muvekkiller' | 'takvim' | 'sure' | 'mesajlar' | 'ayarlar';
const ALTLAR: { anahtar: Alt; ikon: typeof Users }[] = [
  { anahtar: 'dosyalar', ikon: FolderKanban },
  { anahtar: 'muvekkiller', ikon: Users },
  { anahtar: 'takvim', ikon: CalendarDays },
  { anahtar: 'sure', ikon: Calculator },
  { anahtar: 'mesajlar', ikon: MessageSquare },
  { anahtar: 'ayarlar', ikon: Settings2 },
];

function ilkAlt(): Alt {
  try {
    const a = new URLSearchParams(window.location.search).get('alt');
    if (a && ALTLAR.some((x) => x.anahtar === a)) return a as Alt;
  } catch {
    /* yok say */
  }
  return 'dosyalar';
}

export default function Hukuk({ mod }: { mod: HukukMod }) {
  const { t } = useTranslation();
  const api = useMemo(() => hukukApi(), []);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [alt, setAlt] = useState<Alt>(ilkAlt);
  const [acilacakDosya, setAcilacakDosya] = useState<number | null>(null);

  const metaYukle = useCallback(async () => {
    if (mod === 'yonetici') return;
    try {
      setMeta(await api.meta());
      setHata(null);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, mod, t]);

  useEffect(() => {
    void metaYukle();
  }, [metaYukle]);

  const baslik = (
    <div className="mb-5">
      <h2 className="flex items-center gap-2 text-2xl font-bold" id="hukuk-baslik">
        <Scale className="h-6 w-6 text-blue-300" aria-hidden="true" />
        {t('hukuk.baslik')}
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('hukuk.aciklamaYonetici') : t('hukuk.aciklama')}</p>
    </div>
  );

  if (mod === 'yonetici') {
    return (
      <section aria-labelledby="hukuk-baslik" data-testid="hukuk-sekmesi" data-mod="yonetici">
        {baslik}
        <Suspense fallback={<Yukleniyor />}>
          <YonetimOzeti />
        </Suspense>
      </section>
    );
  }

  return (
    <section aria-labelledby="hukuk-baslik" data-testid="hukuk-sekmesi" data-mod="musteri">
      {baslik}
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {meta && (
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 p-3 text-xs text-muted-foreground`} data-testid="hukuk-ozet">
          <span>
            {t('hukuk.ozet.acikDosya', { sayi: meta.acik_dosya_sayisi })}
            {meta.dosya_siniri != null && <> · {t('hukuk.ozet.sinir', { sinir: meta.dosya_siniri })}</>}
          </span>
          <span>{t('hukuk.ozet.yaklasan', { sayi: meta.yaklasan_olay })}</span>
          {meta.okunmamis_mesaj > 0 && <span className="text-amber-200">{t('hukuk.ozet.okunmamis', { sayi: meta.okunmamis_mesaj })}</span>}
        </div>
      )}
      <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('hukuk.baslik')}>
        {ALTLAR.map(({ anahtar, ikon: Ikon }) => (
          <SekmeDugmesi key={anahtar} secili={alt === anahtar} onClick={() => setAlt(anahtar)} testid={anahtar}>
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`hukuk.alt.${anahtar}`)}
            {anahtar === 'mesajlar' && !!meta?.okunmamis_mesaj && (
              <span className="rounded-full bg-amber-500/30 px-1.5 text-[10px] text-amber-100">{meta.okunmamis_mesaj}</span>
            )}
          </SekmeDugmesi>
        ))}
      </div>
      {!meta ? (
        <Yukleniyor />
      ) : (
        <Suspense fallback={<Yukleniyor />}>
          {alt === 'dosyalar' && (
            <Dosyalar api={api} meta={meta} acilacak={acilacakDosya} onAcildi={() => setAcilacakDosya(null)} onDegisti={() => void metaYukle()} />
          )}
          {alt === 'muvekkiller' && (
            <Muvekkiller
              api={api}
              meta={meta}
              onDosyaAc={(id) => {
                setAcilacakDosya(id);
                setAlt('dosyalar');
              }}
            />
          )}
          {alt === 'takvim' && <Takvim api={api} meta={meta} />}
          {alt === 'sure' && <SureHesaplayici api={api} meta={meta} />}
          {alt === 'mesajlar' && <Mesajlar api={api} onOkundu={() => void metaYukle()} />}
          {alt === 'ayarlar' && <Ayarlar api={api} meta={meta} />}
        </Suspense>
      )}
      <div className="mt-6 space-y-2">
        <Not testid="hukuk-uyap-notu">{t('hukuk.uyap')}</Not>
        <Not>{t('hukuk.bilgilendirme')}</Not>
      </div>
    </section>
  );
}
