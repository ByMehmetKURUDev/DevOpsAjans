import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BarChart3, Copy, DoorOpen, ExternalLink, Loader2, Mail, Plus, ScanLine, Settings2, Share2, Ticket, Users } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KART, Rozet, Yukleniyor, kopyala } from '@/components/randevu/ortak';
import { etkinlikApi, hataMetni, yerelIso, type Etkinlik as EtkinlikKaydi, type EtkinlikMod, type Meta } from '@/lib/etkinlik';
import { aralikYaz } from '@/lib/etkinlikOrtak';

const Ayarlar = lazy(() => import('@/components/etkinlik/Ayarlar'));
const Biletler = lazy(() => import('@/components/etkinlik/Biletler'));
const Katilimcilar = lazy(() => import('@/components/etkinlik/Katilimcilar'));
const Kapi = lazy(() => import('@/components/etkinlik/Kapi'));
const Satis = lazy(() => import('@/components/etkinlik/Satis'));
const Iletisim = lazy(() => import('@/components/etkinlik/Iletisim'));
const Paylas = lazy(() => import('@/components/etkinlik/Paylas'));

/**
 * Faz 6E — "Etkinlikler" sekmesi. Yönetici panelinde (`mod="yonetici"`: ajansın kendi etkinlikleri —
 * ücretli bilet yalnız burada — ve müşterilerinkiler) ve müşteri panelinde (`mod="musteri"`: etkin
 * hesabın etkinlikleri) aynı bileşen. `yalnizGiris`: ekipte yalnız `etkinlik_giris` izni olan kişi —
 * katılımcı bilgisi görmeden yalnız kapı okutma ekranını açar.
 *
 * Etkinlik → alt sekmeler: ayarlar, biletler (türler + indirim kodları), katılımcılar (+ bekleme
 * listesi), kapı (canlı sayaç, son okutmalar, görevli bağlantısı, okutma ekranı), satış, e-posta
 * (duyuru, teşekkür + anket, pazarlamaya aktarım), paylaş (bağlantı, QR, gömme kodu, liste sayfası).
 */

type AltSekme = 'ayarlar' | 'biletler' | 'katilimcilar' | 'kapi' | 'satis' | 'iletisim' | 'paylas';
const ALT_SEKMELER: { anahtar: AltSekme; ikon: typeof Ticket }[] = [
  { anahtar: 'ayarlar', ikon: Settings2 },
  { anahtar: 'biletler', ikon: Ticket },
  { anahtar: 'katilimcilar', ikon: Users },
  { anahtar: 'kapi', ikon: DoorOpen },
  { anahtar: 'satis', ikon: BarChart3 },
  { anahtar: 'iletisim', ikon: Mail },
  { anahtar: 'paylas', ikon: Share2 },
];

export const DURUM_RENGI: Record<string, string> = {
  taslak: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  yayinda: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  iptal: 'border-red-400/40 bg-red-500/15 text-red-200',
  tamamlandi: 'border-sky-400/40 bg-sky-500/15 text-sky-200',
};

function YalnizGiris({ mod }: { mod: EtkinlikMod }) {
  const { t, i18n } = useTranslation();
  const api = useMemo(() => etkinlikApi(mod), [mod]);
  const [liste, setListe] = useState<{ id: number; baslik: string; baslangic: string; bitis: string; saat_dilimi: string; durum: string }[] | null>(null);
  useEffect(() => {
    api
      .girisListesi()
      .then((g) => setListe(g.items))
      .catch((e) => {
        toast.error(hataMetni(t, e));
        setListe([]);
      });
  }, [api, t]);
  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="etkinlik-giris-listesi">
      <h3 className="mb-1 text-base font-semibold">{t('etkinlik.giris.baslik')}</h3>
      <p className="mb-4 text-sm text-muted-foreground">{t('etkinlik.giris.aciklama')}</p>
      {liste === null ? (
        <Yukleniyor />
      ) : liste.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t('etkinlik.giris.bos')}</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {liste.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 p-3">
              <span className="min-w-0">
                <span className="block truncate font-medium">{e.baslik}</span>
                <span className="block text-xs text-muted-foreground">{aralikYaz(e.baslangic, e.bitis, e.saat_dilimi, i18n.language)}</span>
              </span>
              <a href={`/etkinlik/okut/${e.id}?mod=${mod}`} className="flex flex-none items-center gap-1.5 rounded-lg bg-purple-500/80 px-3 py-2 text-sm font-medium text-white hover:bg-purple-500" data-testid="etkinlik-okut-ac">
                <ScanLine className="h-4 w-4" aria-hidden="true" />
                {t('etkinlik.kapi.okutAc')}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Etkinlik({ mod, yalnizGiris = false }: { mod: EtkinlikMod; yalnizGiris?: boolean }) {
  const { t, i18n } = useTranslation();
  const api = useMemo(() => etkinlikApi(mod), [mod]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [liste, setListe] = useState<EtkinlikKaydi[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [seciliId, setSeciliId] = useState<number | null>(null);
  const [secili, setSecili] = useState<EtkinlikKaydi | null>(null);
  const [altSekme, setAltSekme] = useState<AltSekme>('ayarlar');
  const [yeniBaslik, setYeniBaslik] = useState('');
  const [yeniBas, setYeniBas] = useState('');
  const [yeniBit, setYeniBit] = useState('');
  const [yeniHesap, setYeniHesap] = useState('');
  const [olusturuluyor, setOlusturuluyor] = useState(false);
  const [kapsam, setKapsam] = useState('');

  const yukle = useCallback(async () => {
    if (yalnizGiris) return;
    setHata(null);
    try {
      const [m, l] = await Promise.all([api.meta(), api.liste(mod === 'yonetici' && kapsam ? kapsam : undefined)]);
      setMeta(m);
      setListe(l.items);
    } catch (e) {
      setHata(hataMetni(t, e));
      setListe([]);
    }
  }, [api, kapsam, mod, t, yalnizGiris]);

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
      .then((e) => {
        if (!iptal) setSecili(e);
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
    const tz = meta?.varsayilan_saat_dilimi || 'Europe/Istanbul';
    const bas = yerelIso(yeniBas, tz);
    const bit = yerelIso(yeniBit, tz);
    if (!yeniBaslik.trim() || !bas || !bit) {
      toast.error(t('etkinlik.hata.zorunlu'));
      return;
    }
    setOlusturuluyor(true);
    try {
      const e = await api.olustur({
        baslik: yeniBaslik.trim(),
        baslangic: bas,
        bitis: bit,
        saat_dilimi: tz,
        dil: (i18n.language || 'tr').slice(0, 2),
        ...(mod === 'yonetici' && yeniHesap.trim() ? { hesap_email: yeniHesap.trim() } : {}),
      });
      setYeniBaslik('');
      setYeniHesap('');
      toast.success(t('etkinlik.liste.olusturuldu'));
      setAltSekme('ayarlar');
      setSeciliId(e.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOlusturuluyor(false);
    }
  };

  const ust = (
    <div className="mb-6">
      <h2 className="flex items-center gap-2 text-2xl font-bold" id="etkinlik-baslik">
        <Ticket className="h-6 w-6 text-purple-300" aria-hidden="true" />
        {t('etkinlik.baslik')}
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('etkinlik.aciklamaYonetici') : t('etkinlik.aciklama')}</p>
    </div>
  );

  if (yalnizGiris) {
    return (
      <section aria-labelledby="etkinlik-baslik" data-testid="etkinlik-sekmesi">
        {ust}
        <YalnizGiris mod={mod} />
      </section>
    );
  }

  // ------------------------------------------------------------------ düzenleyici
  if (seciliId !== null) {
    if (!secili || !meta) {
      return (
        <section aria-labelledby="etkinlik-baslik" data-testid="etkinlik-sekmesi">
          {ust}
          <Yukleniyor />
        </section>
      );
    }
    const guncellendi = (e: EtkinlikKaydi) => setSecili((eski) => ({ ...(eski || e), ...e }));
    return (
      <section aria-labelledby="etkinlik-baslik" data-testid="etkinlik-sekmesi">
        {ust}
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-3 p-4`} data-testid="etkinlik-duzenleyici" data-etkinlik-id={secili.id} data-slug={secili.slug}>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => setSeciliId(null)} data-testid="etkinlik-geri">
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            {t('etkinlik.geri')}
          </Button>
          <span className="flex h-10 w-10 flex-none items-center justify-center overflow-hidden rounded-xl" style={{ background: secili.renk }}>
            {secili.kapak ? <img src={secili.kapak} alt="" width={40} height={40} className="h-full w-full object-cover" /> : <Ticket className="h-5 w-5 text-white" aria-hidden="true" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-lg font-semibold" data-testid="etkinlik-adi">
                {secili.baslik}
              </h3>
              <Rozet renk={DURUM_RENGI[secili.durum]} testid="etkinlik-durum-rozeti">
                {t(`etkinlik.durum.${secili.durum}`)}
              </Rozet>
              {mod === 'yonetici' && <span className="truncate text-xs text-muted-foreground">{secili.hesap_email || t('etkinlik.liste.ajans')}</span>}
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs">
              <a href={`/etkinlik/${secili.slug}`} target="_blank" rel="noopener" className="truncate font-mono text-purple-200 hover:underline" dir="ltr" data-testid="etkinlik-acik-baglanti">
                {secili.adres_url.replace(/^https?:\/\//, '')}
              </a>
              <Button size="icon" variant="ghost" className="h-7 w-7 flex-none" aria-label={t('etkinlik.kopyala')} onClick={() => kopyala(secili.adres_url, t('etkinlik.kopyalandi'), t('etkinlik.kopyalanamadi'))}>
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <a href={`/etkinlik/${secili.slug}`} target="_blank" rel="noopener" aria-label={t('etkinlik.ac')} className="text-muted-foreground hover:text-white">
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>
        <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('etkinlik.baslik')}>
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
              data-etkinlik-alt={anahtar}
            >
              <Ikon className="h-4 w-4" aria-hidden="true" />
              {t(`etkinlik.alt.${anahtar}`)}
            </button>
          ))}
        </div>
        <Suspense fallback={<Yukleniyor />}>
          {altSekme === 'ayarlar' && (
            <Ayarlar
              api={api}
              meta={meta}
              etkinlik={secili}
              onKaydedildi={guncellendi}
              onSilindi={() => {
                setSeciliId(null);
                setListe(null);
              }}
            />
          )}
          {altSekme === 'biletler' && <Biletler api={api} meta={meta} etkinlik={secili} />}
          {altSekme === 'katilimcilar' && <Katilimcilar api={api} etkinlik={secili} />}
          {altSekme === 'kapi' && <Kapi api={api} etkinlik={secili} mod={mod} />}
          {altSekme === 'satis' && <Satis api={api} etkinlik={secili} />}
          {altSekme === 'iletisim' && <Iletisim api={api} etkinlik={secili} onKaydedildi={guncellendi} />}
          {altSekme === 'paylas' && <Paylas api={api} meta={meta} etkinlik={secili} />}
        </Suspense>
      </section>
    );
  }

  // ------------------------------------------------------------------ liste / kurulum
  const sinirDolu = meta?.aylik_etkinlik_siniri != null && (meta.bu_ay ?? 0) >= meta.aylik_etkinlik_siniri;
  return (
    <section aria-labelledby="etkinlik-baslik" data-testid="etkinlik-sekmesi">
      {ust}
      <div className={`${KART} mb-4 p-4 sm:p-6`}>
        <h3 className="mb-1 text-base font-semibold">{t('etkinlik.liste.yeniBaslik')}</h3>
        <p className="mb-3 text-sm text-muted-foreground">
          {t('etkinlik.liste.yeniAciklama')}
          {meta?.aylik_etkinlik_siniri != null && <> {t('etkinlik.liste.sinir', { sayi: meta.bu_ay ?? 0, sinir: meta.aylik_etkinlik_siniri })}</>}
        </p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end">
          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">{t('etkinlik.liste.ad')}</span>
            <Input value={yeniBaslik} onChange={(e) => setYeniBaslik(e.target.value)} maxLength={160} placeholder={t('etkinlik.liste.adOrnek')} data-testid="etkinlik-yeni-baslik" />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">{t('etkinlik.alan.baslangic')}</span>
            <Input type="datetime-local" value={yeniBas} onChange={(e) => setYeniBas(e.target.value)} data-testid="etkinlik-yeni-baslangic" />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-muted-foreground">{t('etkinlik.alan.bitis')}</span>
            <Input type="datetime-local" value={yeniBit} onChange={(e) => setYeniBit(e.target.value)} data-testid="etkinlik-yeni-bitis" />
          </label>
          <Button onClick={() => void olustur()} disabled={olusturuluyor || sinirDolu} className="gap-1.5" data-testid="etkinlik-yeni">
            {olusturuluyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
            {t('etkinlik.liste.olustur')}
          </Button>
          {mod === 'yonetici' && (
            <label className="block text-sm sm:col-span-2 lg:col-span-4">
              <span className="mb-1 block text-muted-foreground">{t('etkinlik.liste.hesap')}</span>
              <Input value={yeniHesap} onChange={(e) => setYeniHesap(e.target.value)} type="email" placeholder="musteri@ornek.com" dir="ltr" />
            </label>
          )}
        </div>
      </div>
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold">{t('etkinlik.liste.etkinlikler')}</h3>
          {mod === 'yonetici' && (
            <select className="h-9 rounded-md border border-white/10 bg-black/40 px-2 text-sm" value={kapsam} onChange={(e) => setKapsam(e.target.value)} aria-label={t('etkinlik.liste.sahip')}>
              <option value="">{t('etkinlik.liste.hepsi')}</option>
              <option value="ajans">{t('etkinlik.liste.yalnizAjans')}</option>
            </select>
          )}
        </div>
        {hata && (
          <p className="mb-3 text-sm text-red-300" role="alert">
            {hata}
          </p>
        )}
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground" data-testid="etkinlik-bos">
            {t('etkinlik.liste.bos')}
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="etkinlik-liste">
            {liste.map((e) => (
              <li key={e.id} data-slug={e.slug}>
                <button
                  type="button"
                  onClick={() => {
                    setAltSekme(e.durum === 'taslak' ? 'ayarlar' : 'katilimcilar');
                    setSeciliId(e.id);
                  }}
                  className="flex h-full w-full items-start gap-3 rounded-xl border border-white/10 bg-black/20 p-3 text-start transition-colors hover:border-purple-400/40 hover:bg-white/[0.04]"
                  data-testid="etkinlik-ac"
                >
                  <span className="flex h-11 w-11 flex-none items-center justify-center overflow-hidden rounded-xl" style={{ background: e.renk }}>
                    {e.kapak ? <img src={e.kapak} alt="" width={44} height={44} className="h-full w-full object-cover" loading="lazy" /> : <Ticket className="h-5 w-5 text-white" aria-hidden="true" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{e.baslik}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{aralikYaz(e.baslangic, e.bitis, e.saat_dilimi, i18n.language)}</span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-1">
                      <Rozet renk={DURUM_RENGI[e.durum]}>{t(`etkinlik.durum.${e.durum}`)}</Rozet>
                      <Rozet>{t('etkinlik.liste.biletSayisi', { sayi: e.bilet_sayisi || 0 })}</Rozet>
                      {mod === 'yonetici' && <span className="truncate text-[11px] text-muted-foreground">{e.hesap_email || t('etkinlik.liste.ajans')}</span>}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
