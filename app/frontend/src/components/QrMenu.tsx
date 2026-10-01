import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  BarChart3,
  Copy,
  ExternalLink,
  FileUp,
  Loader2,
  Palette,
  Plus,
  QrCode,
  Receipt,
  Search,
  Settings2,
  ShoppingBag,
  TicketPercent,
  UtensilsCrossed,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useYoklama } from '@/hooks/useYoklama';
import { KART, Rozet, SECIM, kopyala, sayiYaz } from '@/components/qrMenu/ortak';
import { hataMetni, menuApi, type Magaza, type MenuMeta, type MenuMod } from '@/lib/qrMenu';
import type { Duzen } from '@/lib/qrMenuOrtak';

const IcerikDuzenleyici = lazy(() => import('@/components/qrMenu/IcerikDuzenleyici'));
const MagazaAyarlari = lazy(() => import('@/components/qrMenu/MagazaAyarlari'));
const Kuponlar = lazy(() => import('@/components/qrMenu/Kuponlar'));
const Siparisler = lazy(() => import('@/components/qrMenu/Siparisler'));
const MasaQr = lazy(() => import('@/components/qrMenu/MasaQr'));
const Analiz = lazy(() => import('@/components/qrMenu/Analiz'));
const IceAktar = lazy(() => import('@/components/qrMenu/IceAktar'));

/**
 * Faz 4M — "QR menü ve katalog" sekmesi. Yönetici panelinde (`mod="yonetici"`:
 * ajansın kendi mağazaları + bütün müşterilerinki, müşteri adına kurulum) ve
 * müşteri panelinde (`mod="musteri"`: yalnız etkin hesabın mağazaları; açık
 * modüle göre düzen) aynı bileşen.
 *
 * Mağaza listesi → mağaza düzenleyici: menü (kategori/ürün), görünüm, sipariş
 * ayarları, kuponlar, siparişler (yeni sipariş sayacı), masa QR'ları, analiz,
 * CSV içe aktarma.
 */

type AltSekme = 'menu' | 'gorunum' | 'siparisAyarlari' | 'kuponlar' | 'siparisler' | 'masaQr' | 'analiz' | 'iceAktar';
const ALT_SEKMELER: { anahtar: AltSekme; ikon: typeof Palette }[] = [
  { anahtar: 'menu', ikon: UtensilsCrossed },
  { anahtar: 'siparisler', ikon: Receipt },
  { anahtar: 'gorunum', ikon: Palette },
  { anahtar: 'siparisAyarlari', ikon: Settings2 },
  { anahtar: 'kuponlar', ikon: TicketPercent },
  { anahtar: 'masaQr', ikon: QrCode },
  { anahtar: 'analiz', ikon: BarChart3 },
  { anahtar: 'iceAktar', ikon: FileUp },
];
/** Yeni sipariş sayacı yoklaması (panel açıkken). */
const YOKLAMA_MS = 30000;

const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export default function QrMenu({ mod }: { mod: MenuMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const api = useMemo(() => menuApi(mod), [mod]);
  const [meta, setMeta] = useState<MenuMeta | null>(null);
  const [magazalar, setMagazalar] = useState<Magaza[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [seciliId, setSeciliId] = useState<number | null>(null);
  const [secili, setSecili] = useState<Magaza | null>(null);
  const [altSekme, setAltSekme] = useState<AltSekme>('menu');
  const [yeniSayilari, setYeniSayilari] = useState<Record<string, number>>({});
  const [ara, setAra] = useState('');
  const [kapsam, setKapsam] = useState('');
  const [yeniAd, setYeniAd] = useState('');
  const [yeniDuzen, setYeniDuzen] = useState<Duzen>('menu');
  const [yeniHesap, setYeniHesap] = useState('');
  const [olusturuluyor, setOlusturuluyor] = useState(false);

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [m, l] = await Promise.all([
        api.meta(),
        api.liste({ ara: ara.trim() || undefined, hesap: mod === 'yonetici' && kapsam ? kapsam : undefined }),
      ]);
      setMeta(m);
      setMagazalar(l.items);
      if (m.duzenler.length && !m.duzenler.includes(yeniDuzen)) setYeniDuzen(m.duzenler[0]);
    } catch (e) {
      setHata(hataMetni(t, e));
      setMagazalar([]);
    }
  }, [api, ara, kapsam, mod, t, yeniDuzen]);

  useEffect(() => {
    if (seciliId !== null) return;
    const zaman = window.setTimeout(() => void yukle(), ara ? 300 : 0);
    return () => window.clearTimeout(zaman);
  }, [yukle, seciliId, ara]);

  // Seçili mağazayı (ayrıntı) yükle.
  useEffect(() => {
    if (seciliId === null) {
      setSecili(null);
      return;
    }
    let iptal = false;
    api
      .getir(seciliId)
      .then((m) => {
        if (!iptal) setSecili(m);
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

  useYoklama(
    async () => {
      const o = await api.siparisOzeti();
      setYeniSayilari(o.magazalar);
    },
    { aralik: YOKLAMA_MS, etkin: true, anahtar: mod }
  );

  const olustur = async () => {
    if (!yeniAd.trim()) {
      toast.error(t('qrMenu.hata.zorunlu'));
      return;
    }
    setOlusturuluyor(true);
    try {
      const m = await api.olustur({
        ad: yeniAd.trim(),
        duzen: yeniDuzen,
        ...(mod === 'yonetici' && yeniHesap.trim() ? { hesap_email: yeniHesap.trim() } : {}),
      });
      setYeniAd('');
      setYeniHesap('');
      toast.success(t('qrMenu.liste.olusturuldu'));
      setAltSekme('menu');
      setSeciliId(m.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOlusturuluyor(false);
    }
  };

  const yeniSayisi = (id: number) => yeniSayilari[String(id)] || 0;

  const ust = (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="menu-baslik">
          <UtensilsCrossed className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('qrMenu.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {mod === 'yonetici' ? t('qrMenu.aciklamaYonetici') : t('qrMenu.aciklama')}
        </p>
      </div>
    </div>
  );

  // ------------------------------------------------------------------ düzenleyici
  if (seciliId !== null) {
    if (!secili || !meta) {
      return (
        <section aria-labelledby="menu-baslik">
          {ust}
          <Yukleniyor />
        </section>
      );
    }
    const yazilabilir = mod === 'yonetici' || secili.duzen_acik !== false;
    const guncellendi = (m: Magaza) => setSecili((eski) => ({ ...(eski || m), ...m }));
    return (
      <section aria-labelledby="menu-baslik" data-testid="menu-duzenleyici" data-magaza-id={secili.id}>
        {ust}
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-3 p-4`}>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => setSeciliId(null)} data-testid="menu-geri">
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            {t('qrMenu.geri')}
          </Button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-lg font-semibold" data-testid="menu-magaza-adi">
                {secili.ad}
              </h3>
              <Rozet>{t(`qrMenu.duzen.${secili.duzen}`)}</Rozet>
              {!secili.aktif && <Rozet renk="border-amber-400/30 bg-amber-500/10 text-amber-200">{t('qrMenu.pasif')}</Rozet>}
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs">
              <a href={`/menu/${secili.slug}`} target="_blank" rel="noopener" className="truncate font-mono text-purple-200 hover:underline" dir="ltr" data-testid="menu-acik-baglanti">
                {secili.adres_url.replace(/^https?:\/\//, '')}
              </a>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 flex-none"
                aria-label={t('qrMenu.kopyala')}
                onClick={() => kopyala(secili.adres_url, t('qrMenu.kopyalandi'), t('qrMenu.kopyalanamadi'))}
              >
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <a href={`/menu/${secili.slug}`} target="_blank" rel="noopener" aria-label={t('qrMenu.ac')} className="text-muted-foreground hover:text-white">
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>
        {!yazilabilir && (
          <p className="mb-4 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100" role="status">
            {t('qrMenu.duzenKapali')}
          </p>
        )}
        <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('qrMenu.baslik')}>
          {ALT_SEKMELER.map(({ anahtar, ikon: Ikon }) => {
            const sayi = anahtar === 'siparisler' ? yeniSayisi(secili.id) : 0;
            return (
              <button
                key={anahtar}
                type="button"
                role="tab"
                aria-selected={altSekme === anahtar}
                onClick={() => setAltSekme(anahtar)}
                className={`flex flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  altSekme === anahtar ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
                }`}
                data-menu-alt={anahtar}
              >
                <Ikon className="h-4 w-4" aria-hidden="true" />
                {t(`qrMenu.alt.${anahtar}`)}
                {sayi > 0 && (
                  <span className="rounded-full bg-emerald-500 px-1.5 text-[11px] font-semibold text-black" data-testid="menu-yeni-siparis-sayaci">
                    {sayi}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <Suspense fallback={<Yukleniyor />}>
          {altSekme === 'menu' && <IcerikDuzenleyici api={api} meta={meta} magaza={secili} yazilabilir={yazilabilir} />}
          {(altSekme === 'gorunum' || altSekme === 'siparisAyarlari') && (
            <MagazaAyarlari
              key={altSekme}
              api={api}
              meta={meta}
              magaza={secili}
              bolum={altSekme === 'gorunum' ? 'gorunum' : 'siparis'}
              yazilabilir={yazilabilir}
              mod={mod}
              onKaydedildi={guncellendi}
              onSilindi={() => setSeciliId(null)}
            />
          )}
          {altSekme === 'kuponlar' && <Kuponlar api={api} magaza={secili} yazilabilir={yazilabilir} />}
          {altSekme === 'siparisler' && (
            <Siparisler api={api} magaza={secili} onSayac={(n) => setYeniSayilari((s) => ({ ...s, [String(secili.id)]: n }))} />
          )}
          {altSekme === 'masaQr' && <MasaQr api={api} meta={meta} magaza={secili} />}
          {altSekme === 'analiz' && <Analiz api={api} magaza={secili} />}
          {altSekme === 'iceAktar' && <IceAktar api={api} meta={meta} magaza={secili} yazilabilir={yazilabilir} onBitti={() => setAltSekme('menu')} />}
        </Suspense>
      </section>
    );
  }

  // ------------------------------------------------------------------ liste
  const sinir = meta?.sinirlar[yeniDuzen];
  const sinirDolu = !!sinir && sinir.magaza_siniri !== null && (sinir.magaza_sayisi ?? 0) >= sinir.magaza_siniri;
  return (
    <section aria-labelledby="menu-baslik" data-testid="menu-sekmesi">
      {ust}
      <div className={`${KART} mb-4 p-4 sm:p-6`}>
        <h3 className="mb-3 text-base font-semibold">{t('qrMenu.liste.yeniBaslik')}</h3>
        {meta && meta.duzenler.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('qrMenu.liste.duzenYok')}</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end">
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">{t('qrMenu.liste.ad')}</span>
              <Input value={yeniAd} onChange={(e) => setYeniAd(e.target.value)} maxLength={120} placeholder={t('qrMenu.liste.adOrnek')} data-testid="menu-yeni-ad" />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted-foreground">{t('qrMenu.liste.duzen')}</span>
              <select className={SECIM} value={yeniDuzen} onChange={(e) => setYeniDuzen(e.target.value as Duzen)} data-testid="menu-yeni-duzen">
                {(meta?.duzenler || ['menu']).map((d) => (
                  <option key={d} value={d}>
                    {t(`qrMenu.duzen.${d}`)}
                  </option>
                ))}
              </select>
            </label>
            <Button onClick={() => void olustur()} disabled={olusturuluyor || sinirDolu} className="gap-1.5" data-testid="menu-yeni">
              {olusturuluyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {t('qrMenu.liste.olustur')}
            </Button>
            {mod === 'yonetici' && (
              <label className="block text-sm sm:col-span-3">
                <span className="mb-1 block text-muted-foreground">{t('qrMenu.liste.hesap')}</span>
                <Input value={yeniHesap} onChange={(e) => setYeniHesap(e.target.value)} type="email" placeholder="musteri@ornek.com" dir="ltr" />
              </label>
            )}
          </div>
        )}
        {sinir && sinir.magaza_siniri !== null && (
          <p className="mt-2 text-xs text-muted-foreground" data-testid="menu-magaza-hakki">
            {t('qrMenu.liste.hak', { sayi: sinir.magaza_sayisi ?? 0, sinir: sinir.magaza_siniri, duzen: t(`qrMenu.duzen.${yeniDuzen}`) })}
          </p>
        )}
      </div>

      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-4 grid gap-2 sm:grid-cols-2">
          <label className="relative block">
            <span className="sr-only">{t('qrMenu.liste.ara')}</span>
            <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('qrMenu.liste.ara')} className="ps-8" />
          </label>
          {mod === 'yonetici' && (
            <select className={SECIM} value={kapsam} onChange={(e) => setKapsam(e.target.value)} aria-label={t('qrMenu.liste.sahip')}>
              <option value="">{t('qrMenu.liste.hepsi')}</option>
              <option value="ajans">{t('qrMenu.liste.yalnizAjans')}</option>
            </select>
          )}
        </div>
        {hata && (
          <p className="mb-3 text-sm text-red-300" role="alert">
            {hata}
          </p>
        )}
        {magazalar === null ? (
          <Yukleniyor />
        ) : magazalar.length === 0 ? (
          <div className="py-12 text-center" data-testid="menu-bos">
            <ShoppingBag className="mx-auto mb-3 h-10 w-10 text-purple-300/60" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">{ara ? t('qrMenu.liste.sonucYok') : t('qrMenu.liste.bos')}</p>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="menu-liste">
            {magazalar.map((m) => {
              const yeni = yeniSayisi(m.id) || m.yeni_siparis || 0;
              return (
                <li key={m.id} data-magaza={m.id} data-slug={m.slug}>
                  <button
                    type="button"
                    onClick={() => {
                      setAltSekme(yeni ? 'siparisler' : 'menu');
                      setSeciliId(m.id);
                    }}
                    className="flex h-full w-full items-start gap-3 rounded-xl border border-white/10 bg-black/20 p-3 text-start transition-colors hover:border-purple-400/40 hover:bg-white/[0.04]"
                    data-testid="menu-magaza-ac"
                  >
                    <span
                      className="flex h-12 w-12 flex-none items-center justify-center overflow-hidden rounded-xl"
                      style={{ background: m.tema_rengi }}
                    >
                      {m.logo ? (
                        <img src={m.logo.k} alt="" width={48} height={48} className="h-full w-full object-cover" loading="lazy" decoding="async" />
                      ) : m.duzen === 'katalog' ? (
                        <ShoppingBag className="h-5 w-5 text-white" aria-hidden="true" />
                      ) : (
                        <UtensilsCrossed className="h-5 w-5 text-white" aria-hidden="true" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{m.ad}</span>
                      <span className="block truncate font-mono text-[11px] text-purple-200" dir="ltr">
                        /menu/{m.slug}
                      </span>
                      <span className="mt-1.5 flex flex-wrap gap-1">
                        <Rozet>{t(`qrMenu.duzen.${m.duzen}`)}</Rozet>
                        <Rozet>{t('qrMenu.liste.urunSayisi', { sayi: sayiYaz(m.urun_sayisi || 0, dil) })}</Rozet>
                        {!m.aktif && <Rozet renk="border-amber-400/30 bg-amber-500/10 text-amber-200">{t('qrMenu.pasif')}</Rozet>}
                        {yeni > 0 && (
                          <Rozet renk="border-emerald-400/40 bg-emerald-500/15 text-emerald-200" testid="menu-liste-yeni">
                            {t('qrMenu.liste.yeniSiparis', { sayi: yeni })}
                          </Rozet>
                        )}
                        {mod === 'yonetici' && (
                          <span className="truncate text-[11px] text-muted-foreground">{m.hesap_email || t('qrMenu.liste.ajans')}</span>
                        )}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
