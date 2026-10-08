import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeftRight, BarChart3, Calculator, CalendarClock, Eye, LayoutDashboard, PiggyBank, Scale, Settings2, Users, Wallet } from 'lucide-react';

import { AltDugme, HataSatiri, KART, SECIM, Yukleniyor } from '@/components/onMuhasebe/ortak';
import { hataMetni, muhasebeApi, type Meta, type MuhasebeMod, type MusteriHesabi } from '@/lib/onMuhasebe';

const OzetBolumu = lazy(() => import('@/components/onMuhasebe/Ozet'));
const HareketlerBolumu = lazy(() => import('@/components/onMuhasebe/Hareketler'));
const HesaplarBolumu = lazy(() => import('@/components/onMuhasebe/Hesaplar'));
const CarilerBolumu = lazy(() => import('@/components/onMuhasebe/Cariler'));
const TekrarlarBolumu = lazy(() => import('@/components/onMuhasebe/Tekrarlar'));
const ButceBolumu = lazy(() => import('@/components/onMuhasebe/Butce'));
const RaporlarBolumu = lazy(() => import('@/components/onMuhasebe/Raporlar'));
const AyarlarBolumu = lazy(() => import('@/components/onMuhasebe/Ayarlar'));

export type Bolum = 'ozet' | 'hareketler' | 'hesaplar' | 'cariler' | 'tekrarlar' | 'butce' | 'raporlar' | 'ayarlar';
const BOLUMLER: { anahtar: Bolum; ikon: typeof Wallet }[] = [
  { anahtar: 'ozet', ikon: LayoutDashboard },
  { anahtar: 'hareketler', ikon: ArrowLeftRight },
  { anahtar: 'hesaplar', ikon: Wallet },
  { anahtar: 'cariler', ikon: Users },
  { anahtar: 'tekrarlar', ikon: CalendarClock },
  { anahtar: 'butce', ikon: PiggyBank },
  { anahtar: 'raporlar', ikon: BarChart3 },
  { anahtar: 'ayarlar', ikon: Settings2 },
];
/** `muhasebe_okur` (yalnız rapor) izniyle açılan bölümler. */
const OKUR_BOLUMLERI: Bolum[] = ['ozet', 'butce', 'raporlar'];

function adresParametresi(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

/**
 * Faz 6M — "Ön muhasebe" sekmesi: özet, hareketler (gelir/gider/tahsilat/ödeme/virman, CSV içe/dışa), hesaplar
 * (kasa/banka/kart), cariler (ekstre, yaşlandırma), tekrarlayan kayıtlar, bütçe, raporlar (grafikler, KDV özeti),
 * ayarlar (otomatik aktarım, kategoriler). Menüde TEK sekme; bölümler burada alt gezinme. Müşteri panelinde
 * (`mod="musteri"`) etkin hesabın defteri; yönetici panelinde ajansın KENDİ defteri tam yönetim, müşteri hesabı
 * seçilince salt okunur destek görünümü. `muhasebe_okur` ekip izni (ör. mali müşavir) yalnız özet / bütçe / raporlar.
 * e-Fatura/e-Arşiv ve banka entegrasyonu yok; üstteki not bunu her bölümde açıkça söyler.
 */
export default function OnMuhasebe({ mod }: { mod: MuhasebeMod }) {
  const { t } = useTranslation();
  const [hesap, setHesap] = useState('');
  const [hesaplar, setHesaplar] = useState<MusteriHesabi[] | null>(null);
  const api = useMemo(() => muhasebeApi(mod, hesap || undefined), [mod, hesap]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [surum, setSurum] = useState(0);
  const esitlenen = useRef<string | null>(null);
  const [bolum, setBolum] = useState<Bolum>(() => {
    const b = adresParametresi('bolum') as Bolum | null;
    return b && BOLUMLER.some((x) => x.anahtar === b) ? b : 'ozet';
  });

  useEffect(() => {
    if (mod !== 'yonetici') return;
    muhasebeApi('yonetici')
      .musteriHesaplari()
      .then((r) => setHesaplar(r.items))
      .catch(() => setHesaplar([]));
  }, [mod]);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setMeta(await api.meta());
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    setMeta(null);
    void yukle();
  }, [yukle]);

  // Açılışta bir kez eşitle: vadesi gelen tekrarlayan kayıtlar + açık otomatik aktarımlar + bütçe denetimi
  // (sunucu uyurken zamanlı iş gecikebilir). Değişiklik varsa açık bölüm yenilenir.
  useEffect(() => {
    if (!meta || meta.salt_okunur) return;
    const anahtar = `${mod}|${hesap}`;
    if (esitlenen.current === anahtar) return;
    esitlenen.current = anahtar;
    api
      .esitle()
      .then((r) => {
        if (r.tekrar || r.olusturulan || r.ters || r.oneri || (r.bekleyen_oneri ?? 0) !== meta.oneri_sayisi) {
          setSurum((s) => s + 1);
          void yukle();
        }
      })
      .catch(() => undefined);
  }, [api, meta, mod, hesap, yukle]);

  const yenile = useCallback(() => {
    setSurum((s) => s + 1);
    void yukle();
  }, [yukle]);

  const saltOkunur = !!meta?.salt_okunur;
  const gorunenBolumler = meta?.okur ? BOLUMLER.filter((b) => OKUR_BOLUMLERI.includes(b.anahtar)) : BOLUMLER;
  const etkinBolum: Bolum = gorunenBolumler.some((b) => b.anahtar === bolum) ? bolum : 'ozet';
  const ortak = meta ? { api, meta, yenile, surum, git: setBolum } : null;
  return (
    <section aria-labelledby="mh-baslik" data-testid="mh-sekmesi" data-mod={mod}>
      <div className="mb-5">
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="mh-baslik">
          <Calculator className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('onMuhasebe.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('onMuhasebe.aciklamaYonetici') : t('onMuhasebe.aciklama')}</p>
        <p
          className="mt-3 flex max-w-3xl items-start gap-2 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-xs text-amber-100"
          role="note"
          data-testid="mh-yasal-not"
        >
          <Scale className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          <span>{t('onMuhasebe.yasalNot')}</span>
        </p>
      </div>
      {mod === 'yonetici' && (
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-2 p-3`}>
          <label className="flex min-w-0 flex-1 items-center gap-2 text-sm sm:min-w-[16rem]">
            <span className="flex-none text-muted-foreground">{t('onMuhasebe.yonetici.kapsam')}</span>
            <select className={SECIM} value={hesap} onChange={(e) => setHesap(e.target.value)} data-testid="mh-yonetici-hesap">
              <option value="">{t('onMuhasebe.yonetici.ajans')}</option>
              {(hesaplar || []).map((h) => (
                <option key={h.hesap_email} value={h.hesap_email}>
                  {h.firma_adi ? `${h.firma_adi} — ` : ''}
                  {h.hesap_email} ({t('onMuhasebe.yonetici.sayilar', { hesap: h.hesap_sayisi, hareket: h.hareket_sayisi })})
                </option>
              ))}
            </select>
          </label>
          {saltOkunur && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200" data-testid="mh-salt-okunur">
              <Eye className="h-3.5 w-3.5" aria-hidden="true" />
              {t('onMuhasebe.yonetici.saltOkunur')}
            </span>
          )}
        </div>
      )}
      <HataSatiri hata={hata} />
      {meta?.okur && (
        <p className="mb-3 text-xs text-muted-foreground" data-testid="mh-okur-not">
          {t('onMuhasebe.okurNot')}
        </p>
      )}
      {!meta || !ortak ? (
        !hata && <Yukleniyor />
      ) : (
        <>
          <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('onMuhasebe.baslik')}>
            {gorunenBolumler.map(({ anahtar, ikon: Ikon }) => (
              <AltDugme key={anahtar} secili={etkinBolum === anahtar} onClick={() => setBolum(anahtar)} testid={anahtar}>
                <Ikon className="h-4 w-4" aria-hidden="true" />
                {t(`onMuhasebe.bolum.${anahtar}`)}
                {anahtar === 'ozet' && meta.oneri_sayisi > 0 && (
                  <span
                    className="ml-0.5 rounded-full bg-amber-400/90 px-1.5 text-[10px] font-semibold text-black"
                    aria-label={t('onMuhasebe.oneri.rozet', { sayi: meta.oneri_sayisi })}
                    data-testid="mh-oneri-rozet"
                  >
                    {meta.oneri_sayisi}
                  </span>
                )}
              </AltDugme>
            ))}
          </div>
          <Suspense fallback={<Yukleniyor />}>
            {etkinBolum === 'ozet' ? (
              <OzetBolumu {...ortak} />
            ) : etkinBolum === 'hareketler' ? (
              <HareketlerBolumu {...ortak} />
            ) : etkinBolum === 'hesaplar' ? (
              <HesaplarBolumu {...ortak} />
            ) : etkinBolum === 'cariler' ? (
              <CarilerBolumu {...ortak} />
            ) : etkinBolum === 'tekrarlar' ? (
              <TekrarlarBolumu {...ortak} />
            ) : etkinBolum === 'butce' ? (
              <ButceBolumu {...ortak} />
            ) : etkinBolum === 'raporlar' ? (
              <RaporlarBolumu {...ortak} />
            ) : (
              <AyarlarBolumu {...ortak} />
            )}
          </Suspense>
        </>
      )}
    </section>
  );
}
