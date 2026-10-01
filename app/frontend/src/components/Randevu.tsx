import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BarChart3, CalendarCheck, CalendarClock, Copy, ExternalLink, Layers, Loader2, Plus, Settings2, Share2, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KART, Rozet, Yukleniyor, kopyala } from '@/components/randevu/ortak';
import { hataMetni, randevuApi, type Meta, type RandevuMod, type Sayfa } from '@/lib/randevu';

const Randevular = lazy(() => import('@/components/randevu/Randevular'));
const Turler = lazy(() => import('@/components/randevu/Turler'));
const Uygunluk = lazy(() => import('@/components/randevu/Uygunluk'));
const Ayarlar = lazy(() => import('@/components/randevu/Ayarlar'));
const Paylas = lazy(() => import('@/components/randevu/Paylas'));
const Analiz = lazy(() => import('@/components/randevu/Analiz'));

/**
 * Faz 5R — "Randevular" sekmesi. Yönetici panelinde (`mod="yonetici"`: ajansın
 * kendi sayfası + müşterilerinkiler, müşteri adına kurulum) ve müşteri panelinde
 * (`mod="musteri"`: etkin hesabın tek sayfası) aynı bileşen.
 *
 * Sayfa → alt sekmeler: randevular (liste + hafta), etkinlik türleri, ekip ve
 * uygunluk (haftalık saatler, istisnalar, tatil), sayfa ayarları, paylaş (gömme
 * kodu, QR, ICS besleme), analiz.
 */

type AltSekme = 'randevular' | 'turler' | 'uygunluk' | 'ayarlar' | 'paylas' | 'analiz';
const ALT_SEKMELER: { anahtar: AltSekme; ikon: typeof Layers }[] = [
  { anahtar: 'randevular', ikon: CalendarClock },
  { anahtar: 'turler', ikon: Layers },
  { anahtar: 'uygunluk', ikon: Users },
  { anahtar: 'ayarlar', ikon: Settings2 },
  { anahtar: 'paylas', ikon: Share2 },
  { anahtar: 'analiz', ikon: BarChart3 },
];

export default function Randevu({ mod }: { mod: RandevuMod }) {
  const { t } = useTranslation();
  const api = useMemo(() => randevuApi(mod), [mod]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [sayfalar, setSayfalar] = useState<Sayfa[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [seciliId, setSeciliId] = useState<number | null>(null);
  const [secili, setSecili] = useState<Sayfa | null>(null);
  const [altSekme, setAltSekme] = useState<AltSekme>('randevular');
  const [yeniBaslik, setYeniBaslik] = useState('');
  const [yeniHesap, setYeniHesap] = useState('');
  const [olusturuluyor, setOlusturuluyor] = useState(false);
  const [kapsam, setKapsam] = useState('');

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [m, l] = await Promise.all([api.meta(), api.liste(mod === 'yonetici' && kapsam ? kapsam : undefined)]);
      setMeta(m);
      setSayfalar(l.items);
      // Müşterinin tek sayfası var: doğrudan aç.
      if (mod === 'musteri' && l.items.length === 1) setSeciliId(l.items[0].id);
    } catch (e) {
      setHata(hataMetni(t, e));
      setSayfalar([]);
    }
  }, [api, kapsam, mod, t]);

  useEffect(() => {
    if (seciliId !== null) return;
    void yukle();
  }, [yukle, seciliId]);

  useEffect(() => {
    if (seciliId === null) {
      setSecili(null);
      return;
    }
    let iptal = false;
    api
      .getir(seciliId)
      .then((s) => {
        if (!iptal) setSecili(s);
      })
      .catch((e) => {
        if (iptal) return;
        toast.error(hataMetni(t, e));
        setSeciliId(null);
      });
    return () => {
      iptal = true;
    };
  }, [api, seciliId, t]);

  const olustur = async () => {
    if (!yeniBaslik.trim()) {
      toast.error(t('randevu.hata.zorunlu'));
      return;
    }
    setOlusturuluyor(true);
    try {
      const s = await api.olustur({
        baslik: yeniBaslik.trim(),
        ...(mod === 'yonetici' && yeniHesap.trim() ? { hesap_email: yeniHesap.trim() } : {}),
      });
      setYeniBaslik('');
      setYeniHesap('');
      toast.success(t('randevu.liste.olusturuldu'));
      setAltSekme('turler');
      setSeciliId(s.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOlusturuluyor(false);
    }
  };

  const ust = (
    <div className="mb-6">
      <h2 className="flex items-center gap-2 text-2xl font-bold" id="randevu-baslik">
        <CalendarCheck className="h-6 w-6 text-purple-300" aria-hidden="true" />
        {t('randevu.baslik')}
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('randevu.aciklamaYonetici') : t('randevu.aciklama')}</p>
    </div>
  );

  // ------------------------------------------------------------------ sayfa düzenleyici
  if (seciliId !== null) {
    if (!secili || !meta) {
      return (
        <section aria-labelledby="randevu-baslik" data-testid="randevu-sekmesi">
          {ust}
          <Yukleniyor />
        </section>
      );
    }
    const guncellendi = (s: Sayfa) => setSecili((eski) => ({ ...(eski || s), ...s }));
    return (
      <section aria-labelledby="randevu-baslik" data-testid="randevu-sekmesi">
        {ust}
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-3 p-4`} data-testid="randevu-duzenleyici" data-sayfa-id={secili.id}>
          {(mod === 'yonetici' || (sayfalar?.length ?? 0) > 1) && (
            <Button size="sm" variant="ghost" className="gap-1" onClick={() => setSeciliId(null)} data-testid="randevu-geri">
              <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
              {t('randevu.geri')}
            </Button>
          )}
          <span className="flex h-10 w-10 flex-none items-center justify-center overflow-hidden rounded-xl" style={{ background: secili.renk }}>
            {secili.logo ? <img src={secili.logo} alt="" width={40} height={40} className="h-full w-full object-cover" /> : <CalendarCheck className="h-5 w-5 text-white" aria-hidden="true" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-lg font-semibold" data-testid="randevu-sayfa-adi">
                {secili.baslik}
              </h3>
              {!secili.aktif && <Rozet renk="border-amber-400/30 bg-amber-500/10 text-amber-200">{t('randevu.pasif')}</Rozet>}
              {mod === 'yonetici' && <span className="truncate text-xs text-muted-foreground">{secili.hesap_email || t('randevu.liste.ajans')}</span>}
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs">
              <a href={`/randevu/${secili.slug}`} target="_blank" rel="noopener" className="truncate font-mono text-purple-200 hover:underline" dir="ltr" data-testid="randevu-acik-baglanti">
                {secili.adres_url.replace(/^https?:\/\//, '')}
              </a>
              <Button size="icon" variant="ghost" className="h-7 w-7 flex-none" aria-label={t('randevu.kopyala')} onClick={() => kopyala(secili.adres_url, t('randevu.kopyalandi'), t('randevu.kopyalanamadi'))}>
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <a href={`/randevu/${secili.slug}`} target="_blank" rel="noopener" aria-label={t('randevu.ac')} className="text-muted-foreground hover:text-white">
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>
        <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('randevu.baslik')}>
          {ALT_SEKMELER.map(({ anahtar, ikon: Ikon }) => (
            <button
              key={anahtar}
              type="button"
              role="tab"
              aria-selected={altSekme === anahtar}
              onClick={() => setAltSekme(anahtar)}
              className={`flex flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                altSekme === anahtar ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
              }`}
              data-randevu-alt={anahtar}
            >
              <Ikon className="h-4 w-4" aria-hidden="true" />
              {t(`randevu.alt.${anahtar}`)}
            </button>
          ))}
        </div>
        <Suspense fallback={<Yukleniyor />}>
          {altSekme === 'randevular' && <Randevular api={api} sayfa={secili} />}
          {altSekme === 'turler' && <Turler api={api} meta={meta} sayfa={secili} />}
          {altSekme === 'uygunluk' && <Uygunluk api={api} sayfa={secili} mod={mod} onSayfa={guncellendi} />}
          {altSekme === 'ayarlar' && (
            <Ayarlar
              api={api}
              meta={meta}
              sayfa={secili}
              onKaydedildi={guncellendi}
              onSilindi={() => {
                setSeciliId(null);
                setSayfalar(null);
              }}
            />
          )}
          {altSekme === 'paylas' && <Paylas api={api} meta={meta} sayfa={secili} onSayfa={guncellendi} />}
          {altSekme === 'analiz' && <Analiz api={api} sayfa={secili} />}
        </Suspense>
      </section>
    );
  }

  // ------------------------------------------------------------------ liste / kurulum
  const musteriSayfasiVar = mod === 'musteri' && (sayfalar?.length ?? 0) > 0;
  return (
    <section aria-labelledby="randevu-baslik" data-testid="randevu-sekmesi">
      {ust}
      {!musteriSayfasiVar && (
        <div className={`${KART} mb-4 p-4 sm:p-6`}>
          <h3 className="mb-1 text-base font-semibold">{t('randevu.liste.yeniBaslik')}</h3>
          <p className="mb-3 text-sm text-muted-foreground">{t('randevu.liste.yeniAciklama')}</p>
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">{t('randevu.liste.ad')}</span>
              <Input value={yeniBaslik} onChange={(e) => setYeniBaslik(e.target.value)} maxLength={120} placeholder={t('randevu.liste.adOrnek')} data-testid="randevu-yeni-baslik" />
            </label>
            <Button onClick={() => void olustur()} disabled={olusturuluyor} className="gap-1.5" data-testid="randevu-yeni">
              {olusturuluyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {t('randevu.liste.olustur')}
            </Button>
            {mod === 'yonetici' && (
              <label className="block text-sm sm:col-span-2">
                <span className="mb-1 block text-muted-foreground">{t('randevu.liste.hesap')}</span>
                <Input value={yeniHesap} onChange={(e) => setYeniHesap(e.target.value)} type="email" placeholder="musteri@ornek.com" dir="ltr" />
              </label>
            )}
          </div>
        </div>
      )}
      {mod === 'yonetici' && (
        <div className={`${KART} p-4 sm:p-6`}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold">{t('randevu.liste.sayfalar')}</h3>
            <select
              className="h-9 rounded-md border border-white/10 bg-black/40 px-2 text-sm"
              value={kapsam}
              onChange={(e) => setKapsam(e.target.value)}
              aria-label={t('randevu.liste.sahip')}
            >
              <option value="">{t('randevu.liste.hepsi')}</option>
              <option value="ajans">{t('randevu.liste.yalnizAjans')}</option>
            </select>
          </div>
          {hata && (
            <p className="mb-3 text-sm text-red-300" role="alert">
              {hata}
            </p>
          )}
          {sayfalar === null ? (
            <Yukleniyor />
          ) : sayfalar.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground" data-testid="randevu-bos">
              {t('randevu.liste.bos')}
            </p>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="randevu-liste">
              {sayfalar.map((s) => (
                <li key={s.id} data-slug={s.slug}>
                  <button
                    type="button"
                    onClick={() => {
                      setAltSekme('randevular');
                      setSeciliId(s.id);
                    }}
                    className="flex h-full w-full items-start gap-3 rounded-xl border border-white/10 bg-black/20 p-3 text-start transition-colors hover:border-purple-400/40 hover:bg-white/[0.04]"
                    data-testid="randevu-sayfa-ac"
                  >
                    <span className="flex h-11 w-11 flex-none items-center justify-center overflow-hidden rounded-xl" style={{ background: s.renk }}>
                      {s.logo ? <img src={s.logo} alt="" width={44} height={44} className="h-full w-full object-cover" loading="lazy" /> : <CalendarCheck className="h-5 w-5 text-white" aria-hidden="true" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{s.baslik}</span>
                      <span className="block truncate font-mono text-[11px] text-purple-200" dir="ltr">
                        /randevu/{s.slug}
                      </span>
                      <span className="mt-1.5 flex flex-wrap items-center gap-1">
                        <Rozet>{t('randevu.liste.turSayisi', { sayi: s.tur_sayisi || 0 })}</Rozet>
                        {(s.yaklasan || 0) > 0 && <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200">{t('randevu.liste.yaklasan', { sayi: s.yaklasan })}</Rozet>}
                        <span className="truncate text-[11px] text-muted-foreground">{s.hesap_email || t('randevu.liste.ajans')}</span>
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {mod === 'musteri' && hata && (
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {mod === 'musteri' && sayfalar === null && <Yukleniyor />}
    </section>
  );
}
