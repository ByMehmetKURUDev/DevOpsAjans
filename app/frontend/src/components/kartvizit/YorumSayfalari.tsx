import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, BarChart3, Check, Copy, Download, ExternalLink, ImagePlus, Info, Loader2, Pencil, Plus, Save, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { KART, SECIM, kopyala, sayiYaz } from '@/components/dinamikQr/ortak';
import { AnalizPaneli, type AnalizKaynagi } from '@/components/kartvizit/KartAnalizi';
import { Rozet } from '@/components/kartvizit/KartlarBolumu';
import { apiAdresi } from '@/lib/kartvizitAcik';
import { hataMetni, slugOner, type PanelMod, type SlugDurumu, type YorumApi, type YorumMeta, type YorumSayfasi } from '@/lib/kartvizit';

/**
 * Faz 4K — Google yorum sayfaları: liste → düzenleyici / analiz.
 *
 * Google kuralı ("review gating" yasak): sayfada puan sorulmuyor; Google
 * düğmesi her ziyaretçiye aynı adresle görünüyor. Düzenleyicide bu kural kısa
 * bir notla hatırlatılıyor ve hiçbir ayar Google bağlantısını koşula bağlamıyor.
 */

type Gorunum = { tip: 'liste' } | { tip: 'duzenle'; kayit: YorumSayfasi | null } | { tip: 'analiz'; kayit: YorumSayfasi };
const DIL_ADI: Record<string, string> = { tr: 'Türkçe', en: 'English', de: 'Deutsch', ru: 'Русский', zh: '中文', hi: 'हिन्दी', ar: 'العربية' };

export default function YorumSayfalari({ api, mod }: { api: YorumApi; mod: PanelMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [gorunum, setGorunum] = useState<Gorunum>({ tip: 'liste' });
  const [meta, setMeta] = useState<YorumMeta | null>(null);
  const [liste, setListe] = useState<YorumSayfasi[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [ara, setAra] = useState('');

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [m, l] = await Promise.all([api.meta(), api.liste({ ara: ara.trim() || undefined })]);
      setMeta(m);
      setListe(l.items);
    } catch (e) {
      setHata(hataMetni(t, e));
      setListe([]);
    }
  }, [api, ara, t]);

  useEffect(() => {
    if (gorunum.tip !== 'liste') return;
    const z = window.setTimeout(() => void yukle(), ara ? 300 : 0);
    return () => window.clearTimeout(z);
  }, [yukle, gorunum.tip, ara]);

  const analizKaynagi = useMemo<AnalizKaynagi | null>(() => {
    if (gorunum.tip !== 'analiz') return null;
    const k = gorunum.kayit;
    return { id: k.id, baslik: k.isletme_adi, analiz: api.analiz, qrIndir: (b) => api.qrIndir(k.id, b, k.slug) };
  }, [gorunum, api]);

  if (gorunum.tip === 'duzenle') {
    return (
      <YorumDuzenleyici
        api={api}
        mod={mod}
        meta={meta}
        kayit={gorunum.kayit}
        onKapat={() => setGorunum({ tip: 'liste' })}
        onKaydedildi={(k) => setGorunum({ tip: 'duzenle', kayit: k })}
      />
    );
  }
  if (gorunum.tip === 'analiz' && analizKaynagi) {
    return <AnalizPaneli kaynak={analizKaynagi} tur="yorum" onGeri={() => setGorunum({ tip: 'liste' })} />;
  }

  const sinirDolu = !!meta && meta.sayfa_siniri !== null && (meta.sayfa_sayisi ?? 0) >= meta.sayfa_siniri;
  const sil = async (y: YorumSayfasi) => {
    if (!window.confirm(t('kartvizit.liste.silOnay', { ad: y.isletme_adi }))) return;
    try {
      await api.sil(y.id);
      toast.success(t('kartvizit.liste.silindi'));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="yorum-listesi">
      <PolitikaNotu />
      <div className="mb-4 mt-4 flex flex-wrap items-center gap-2">
        <Button
          onClick={() => (sinirDolu ? toast.error(t('kartvizit.hata.sayfa_siniri', { sinir: meta?.sayfa_siniri })) : setGorunum({ tip: 'duzenle', kayit: null }))}
          className="gap-1.5"
          data-testid="yorum-yeni"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('kartvizit.yorum.yeni')}
        </Button>
        {meta && meta.sayfa_siniri !== null && (
          <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground">
            {t('kartvizit.liste.hak', { sayi: meta.sayfa_sayisi ?? 0, sinir: meta.sayfa_siniri })}
          </span>
        )}
        <label className="kv-ara ms-auto">
          <span className="sr-only">{t('kartvizit.liste.ara')}</span>
          <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('kartvizit.liste.ara')} className="ps-8" />
        </label>
      </div>
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {liste === null ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : liste.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t('kartvizit.yorum.bos')}</p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {liste.map((y) => (
            <li key={y.id} className="rounded-xl border border-white/10 bg-black/20 p-4" data-testid="yorum-satiri" data-slug={y.slug}>
              <div className="flex items-start gap-3">
                {y.logo ? (
                  <img src={apiAdresi(y.logo.url)} alt="" width={48} height={48} className="h-12 w-12 shrink-0 rounded-lg bg-white object-contain p-1" loading="lazy" />
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg text-lg font-bold text-white" style={{ background: y.renk || '#4285f4' }} aria-hidden="true">
                    {y.isletme_adi.charAt(0).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{y.isletme_adi}</p>
                  <a href={y.sayfa_adresi} target="_blank" rel="noopener" className="block truncate text-xs text-purple-300 hover:underline" dir="ltr">
                    /yorum/{y.slug}
                  </a>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Rozet renk={y.aktif ? 'yesil' : 'gri'}>{t(y.aktif ? 'kartvizit.durum.aktif' : 'kartvizit.durum.pasif')}</Rozet>
                    {!!y.okunmamis && <Rozet renk="mor">{t('kartvizit.liste.okunmamis', { sayi: y.okunmamis })}</Rozet>}
                    {mod === 'yonetici' && <Rozet>{y.hesap_email || t('kartvizit.liste.ajans')}</Rozet>}
                  </div>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                {(['goruntulenme', 'google', 'geri_bildirim'] as const).map((o) => (
                  <div key={o} className="rounded-lg bg-white/[0.04] p-2">
                    <dt className="truncate text-muted-foreground">{t(`kartvizit.olay.${o}`)}</dt>
                    <dd className="mt-0.5 text-base font-semibold tabular-nums">{sayiYaz(y.son30[o] || 0, dil)}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-1 text-[10px] text-muted-foreground">{t('kartvizit.liste.son30')}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Button size="sm" variant="outline" className="h-9 gap-1 !bg-transparent border-white/20" onClick={() => setGorunum({ tip: 'duzenle', kayit: y })} data-testid="yorum-duzenle">
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('kartvizit.liste.duzenle')}
                </Button>
                <Button size="sm" variant="outline" className="h-9 gap-1 !bg-transparent border-white/20" onClick={() => setGorunum({ tip: 'analiz', kayit: y })} data-testid="yorum-analiz">
                  <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('kartvizit.liste.analiz')}
                </Button>
                <Button size="sm" variant="ghost" className="h-9 w-9 p-0" asChild>
                  <a href={y.sayfa_adresi} target="_blank" rel="noopener" aria-label={t('kartvizit.liste.ac')} title={t('kartvizit.liste.ac')}>
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                  </a>
                </Button>
                <Button size="sm" variant="ghost" className="h-9 w-9 p-0" aria-label={t('kartvizit.liste.kopyala')} title={t('kartvizit.liste.kopyala')}
                  onClick={() => void kopyala(y.sayfa_adresi, t('kartvizit.liste.kopyalandi'), t('kartvizit.hata.genel'))}>
                  <Copy className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button size="sm" variant="ghost" className="h-9 w-9 p-0" aria-label={t('kartvizit.liste.qrIndir')} title={t('kartvizit.liste.qrIndir')}
                  onClick={() => void api.qrIndir(y.id, 'png', y.slug).catch((e) => toast.error(hataMetni(t, e)))} data-testid="yorum-qr-indir">
                  <Download className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button size="sm" variant="ghost" className="h-9 w-9 p-0 text-red-300" aria-label={t('kartvizit.liste.sil')} title={t('kartvizit.liste.sil')} onClick={() => void sil(y)}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PolitikaNotu() {
  const { t } = useTranslation();
  return (
    <div className="flex gap-2.5 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100" role="note" data-testid="yorum-politika">
      <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="font-semibold">{t('kartvizit.yorum.politikaNotu')}</p>
        <p className="kv-not-aciklama mt-0.5 text-xs">{t('kartvizit.yorum.politikaAciklama')}</p>
      </div>
    </div>
  );
}

function YorumDuzenleyici({
  api,
  mod,
  meta,
  kayit,
  onKapat,
  onKaydedildi,
}: {
  api: YorumApi;
  mod: PanelMod;
  meta: YorumMeta | null;
  kayit: YorumSayfasi | null;
  onKapat: () => void;
  onKaydedildi: (k: YorumSayfasi) => void;
}) {
  const { t } = useTranslation();
  const [sayfa, setSayfa] = useState<YorumSayfasi | null>(kayit);
  const [ad, setAd] = useState(kayit?.isletme_adi || '');
  const [placeId, setPlaceId] = useState(kayit?.place_id || '');
  const [tesekkur, setTesekkur] = useState(kayit?.tesekkur || '');
  const [dil, setDil] = useState(kayit?.dil || 'tr');
  const [renk, setRenk] = useState(kayit?.renk || '#4285f4');
  const [geriBildirim, setGeriBildirim] = useState(kayit?.geri_bildirim_acik ?? true);
  const [aktif, setAktif] = useState(kayit?.aktif ?? true);
  const [slug, setSlug] = useState(kayit?.slug || '');
  const [slugElle, setSlugElle] = useState(!!kayit);
  const [slugDurumu, setSlugDurumu] = useState<SlugDurumu | null>(null);
  const [hesapEmail, setHesapEmail] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [logoYukleniyor, setLogoYukleniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const girdi = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!slugElle) setSlug(slugOner(ad));
  }, [ad, slugElle]);
  useEffect(() => {
    if (!slug || slug === sayfa?.slug) {
      setSlugDurumu(null);
      return;
    }
    const z = window.setTimeout(() => void api.slugUygun(slug, sayfa?.id, ad).then(setSlugDurumu).catch(() => setSlugDurumu(null)), 400);
    return () => window.clearTimeout(z);
  }, [slug, sayfa?.id, sayfa?.slug, api, ad]);

  const kaydet = async () => {
    setHata(null);
    setMesgul(true);
    const govde: Record<string, unknown> = {
      isletme_adi: ad,
      place_id: placeId.trim(),
      tesekkur,
      dil,
      renk,
      geri_bildirim_acik: geriBildirim,
      aktif,
      ...(slug ? { slug } : {}),
      ...(mod === 'yonetici' && !sayfa && hesapEmail.trim() ? { hesap_email: hesapEmail.trim() } : {}),
    };
    try {
      const k = sayfa ? await api.guncelle(sayfa.id, govde) : await api.olustur(govde);
      setSayfa(k);
      setSlug(k.slug);
      setSlugElle(true);
      toast.success(t(sayfa ? 'kartvizit.duzenle.kaydedildi' : 'kartvizit.duzenle.olusturuldu'));
      onKaydedildi(k);
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const logo = async (dosya: File | undefined) => {
    if (!sayfa || !dosya) return;
    setLogoYukleniyor(true);
    try {
      setSayfa(await api.logoYukle(sayfa.id, dosya));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setLogoYukleniyor(false);
    }
  };

  const alan = (etiket: string, icerik: ReactNode, ipucu?: string, grup?: boolean) => {
    const Kap = grup ? 'div' : 'label';
    return (
      <Kap className="block">
        <span className="mb-1 block text-xs font-medium text-muted-foreground">{etiket}</span>
        {icerik}
        {ipucu && <span className="mt-1 block text-[11px] text-muted-foreground">{ipucu}</span>}
      </Kap>
    );
  };

  return (
    <div data-testid="yorum-duzenleyici">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={onKapat}>
          <ArrowLeft className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
          {t('kartvizit.duzenle.listeyeDon')}
        </Button>
        <h3 className="text-lg font-semibold">{sayfa ? t('kartvizit.yorum.duzenleBaslik') : t('kartvizit.yorum.yeniBaslik')}</h3>
        {sayfa && (
          <a href={sayfa.sayfa_adresi} target="_blank" rel="noopener" className="ms-auto text-sm text-purple-300 hover:underline" dir="ltr">
            /yorum/{sayfa.slug}
          </a>
        )}
      </div>
      <PolitikaNotu />
      <div className={`${KART} mt-4 space-y-3 p-4`}>
        {alan(t('kartvizit.alan.isletme_adi'), <Input value={ad} onChange={(e) => setAd(e.target.value)} maxLength={120} data-testid="yd-ad" />)}
        {alan(
          t('kartvizit.alan.place_id'),
          <Input value={placeId} onChange={(e) => setPlaceId(e.target.value)} maxLength={512} dir="ltr" placeholder="ChIJ…" data-testid="yd-place" />,
          t('kartvizit.yorum.placeIpucu')
        )}
        <a href="https://developers.google.com/maps/documentation/places/web-service/place-id" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-purple-300 hover:underline">
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
          {t('kartvizit.yorum.placeBul')}
        </a>
        {sayfa && (
          <p className="text-xs text-muted-foreground">
            {t('kartvizit.yorum.googleAdresi')}:{' '}
            <a href={sayfa.google_adresi} target="_blank" rel="noopener noreferrer" className="break-all text-purple-300 hover:underline" dir="ltr" data-testid="yd-google">
              {sayfa.google_adresi}
            </a>
          </p>
        )}
        {alan(t('kartvizit.alan.tesekkur'), <Textarea value={tesekkur} onChange={(e) => setTesekkur(e.target.value)} maxLength={500} rows={2} />, t('kartvizit.yorum.tesekkurIpucu'))}
        <div className="grid gap-3 sm:grid-cols-2">
          {alan(
            t('kartvizit.alan.dil'),
            <select className={SECIM} value={dil} onChange={(e) => setDil(e.target.value)} data-testid="yd-dil">
              {(meta?.diller || Object.keys(DIL_ADI)).map((d) => (
                <option key={d} value={d}>
                  {DIL_ADI[d] || d}
                </option>
              ))}
            </select>
          )}
          {alan(
            t('kartvizit.alan.renk'),
            <div className="flex items-center gap-2">
              <input type="color" value={renk} onChange={(e) => setRenk(e.target.value)} className="h-10 w-12 cursor-pointer rounded border border-white/10 bg-transparent" aria-label={t('kartvizit.alan.renk')} />
              <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                {renk}
              </span>
            </div>,
            undefined,
            true
          )}
        </div>
        {alan(
          t('kartvizit.alan.slug'),
          <>
            <div className="flex items-stretch overflow-hidden rounded-md border border-white/10 bg-black/40 kv-slug" dir="ltr">
              <span className="flex items-center px-2 text-xs text-muted-foreground">/yorum/</span>
              <input
                className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm text-white outline-none"
                value={slug}
                onChange={(e) => {
                  setSlugElle(true);
                  setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 50));
                }}
                aria-label={t('kartvizit.alan.slug')}
                data-testid="yd-slug"
              />
            </div>
            {slugDurumu && (
              <p className={`mt-1 flex items-center gap-1 text-xs ${slugDurumu.uygun ? 'text-emerald-300' : 'text-amber-300'}`} role="status">
                {slugDurumu.uygun && <Check className="h-3 w-3" aria-hidden="true" />}
                {slugDurumu.uygun ? t('kartvizit.duzenle.slugUygun') : t(`kartvizit.hata.${slugDurumu.kod}`, { defaultValue: t('kartvizit.hata.genel') })}
              </p>
            )}
          </>,
          sayfa ? t('kartvizit.duzenle.slugIpucu', { gun: meta?.eski_slug_gun ?? 30 }) : undefined,
          true
        )}
        <label className="flex items-start gap-3">
          <input type="checkbox" checked={geriBildirim} onChange={(e) => setGeriBildirim(e.target.checked)} className="mt-0.5 h-4 w-4 accent-purple-500" />
          <span>
            <span className="block text-sm">{t('kartvizit.yorum.geriBildirimAcik')}</span>
            <span className="block text-xs text-muted-foreground">{t('kartvizit.yorum.geriBildirimAciklama')}</span>
          </span>
        </label>
        <label className="flex items-center gap-3">
          <input type="checkbox" checked={aktif} onChange={(e) => setAktif(e.target.checked)} className="h-4 w-4 accent-purple-500" />
          <span className="text-sm">{t('kartvizit.duzenle.aktif')}</span>
        </label>
        {mod === 'yonetici' && !sayfa &&
          alan(t('kartvizit.alan.hesap_email'), <Input type="email" value={hesapEmail} onChange={(e) => setHesapEmail(e.target.value)} dir="ltr" />, t('kartvizit.duzenle.hesapIpucu'))}
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <p className="mb-2 text-xs font-medium">{t('kartvizit.gorsel.logo')}</p>
          {!sayfa ? (
            <p className="text-xs text-muted-foreground">{t('kartvizit.duzenle.gorselOnceKaydet')}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              {sayfa.logo && <img src={apiAdresi(sayfa.logo.url)} alt="" width={sayfa.logo.genislik} height={sayfa.logo.yukseklik} className="h-14 w-auto rounded bg-white object-contain p-1" />}
              <Button type="button" size="sm" variant="outline" className="gap-1.5 !bg-transparent border-white/20" disabled={logoYukleniyor} onClick={() => girdi.current?.click()} data-testid="yd-logo">
                {logoYukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
                {sayfa.logo ? t('kartvizit.duzenle.degistir') : t('kartvizit.duzenle.yukle')}
              </Button>
              {sayfa.logo && (
                <Button type="button" size="sm" variant="ghost" className="text-red-300" onClick={() => void api.logoKaldir(sayfa.id).then(setSayfa).catch((e) => toast.error(hataMetni(t, e)))}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
              <input ref={girdi} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => { void logo(e.target.files?.[0]); e.target.value = ''; }} data-testid="yd-logo-dosya" />
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
          <Button onClick={() => void kaydet()} disabled={mesgul || !ad.trim() || !placeId.trim()} className="gap-1.5" data-testid="yd-kaydet">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
            {sayfa ? t('kartvizit.duzenle.kaydet') : t('kartvizit.duzenle.olustur')}
          </Button>
          {sayfa && (
            <>
              <Button variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => void api.qrIndir(sayfa.id, 'png', sayfa.slug).catch((e) => toast.error(hataMetni(t, e)))}>
                <Download className="h-4 w-4" aria-hidden="true" />
                QR PNG
              </Button>
              <Button variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => void api.qrIndir(sayfa.id, 'svg', sayfa.slug).catch((e) => toast.error(hataMetni(t, e)))}>
                <Download className="h-4 w-4" aria-hidden="true" />
                QR SVG
              </Button>
            </>
          )}
          {hata && (
            <p className="w-full text-sm text-red-300" role="alert">
              {hata}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
