import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart3, Copy, Download, ExternalLink, Loader2, Lock, Pencil, Plus, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KART, kopyala, sayiYaz } from '@/components/dinamikQr/ortak';
import KartAnalizi from '@/components/kartvizit/KartAnalizi';
import KartDuzenleyici from '@/components/kartvizit/KartDuzenleyici';
import { apiAdresi } from '@/lib/kartvizitAcik';
import { hataMetni, type KartApi, type KartKaydi, type KartMeta, type PanelMod } from '@/lib/kartvizit';

/** Faz 4K — kart listesi → düzenleyici / analiz. */

type Gorunum = { tip: 'liste' } | { tip: 'duzenle'; kayit: KartKaydi | null } | { tip: 'analiz'; kayit: KartKaydi };

export default function KartlarBolumu({ api, mod }: { api: KartApi; mod: PanelMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [gorunum, setGorunum] = useState<Gorunum>({ tip: 'liste' });
  const [meta, setMeta] = useState<KartMeta | null>(null);
  const [kartlar, setKartlar] = useState<KartKaydi[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [ara, setAra] = useState('');
  const [hesap, setHesap] = useState('');

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [m, l] = await Promise.all([api.meta(), api.liste({ ara: ara.trim() || undefined, hesap: mod === 'yonetici' ? hesap.trim() || undefined : undefined })]);
      setMeta(m);
      setKartlar(l.items);
    } catch (e) {
      setHata(hataMetni(t, e));
      setKartlar([]);
    }
  }, [api, ara, hesap, mod, t]);

  useEffect(() => {
    if (gorunum.tip !== 'liste') return;
    const z = window.setTimeout(() => void yukle(), ara || hesap ? 300 : 0);
    return () => window.clearTimeout(z);
  }, [yukle, gorunum.tip, ara, hesap]);

  if (gorunum.tip === 'duzenle') {
    return (
      <KartDuzenleyici
        api={api}
        mod={mod}
        meta={meta}
        kayit={gorunum.kayit}
        onKapat={() => setGorunum({ tip: 'liste' })}
        onKaydedildi={(k) => setGorunum({ tip: 'duzenle', kayit: k })}
      />
    );
  }
  if (gorunum.tip === 'analiz') {
    return <KartAnalizi api={api} kayit={gorunum.kayit} onGeri={() => setGorunum({ tip: 'liste' })} />;
  }

  const sinirDolu = !!meta && meta.kart_siniri !== null && (meta.kart_sayisi ?? 0) >= meta.kart_siniri;
  const sil = async (k: KartKaydi) => {
    if (!window.confirm(t('kartvizit.liste.silOnay', { ad: k.ad_soyad }))) return;
    try {
      await api.sil(k.id);
      toast.success(t('kartvizit.liste.silindi'));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="kart-listesi">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button
          onClick={() => (sinirDolu ? toast.error(t('kartvizit.hata.kart_siniri', { sinir: meta?.kart_siniri })) : setGorunum({ tip: 'duzenle', kayit: null }))}
          className="gap-1.5"
          data-testid="kart-yeni"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('kartvizit.liste.yeni')}
        </Button>
        {meta && meta.kart_siniri !== null && (
          <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground" data-testid="kart-hakki">
            {t('kartvizit.liste.hak', { sayi: meta.kart_sayisi ?? 0, sinir: meta.kart_siniri })}
          </span>
        )}
        <label className="kv-ara ms-auto">
          <span className="sr-only">{t('kartvizit.liste.ara')}</span>
          <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('kartvizit.liste.ara')} className="ps-8" />
        </label>
        {mod === 'yonetici' && (
          <label className="block w-full sm:w-56">
            <span className="sr-only">{t('kartvizit.liste.hesapSuzgeci')}</span>
            <Input value={hesap} onChange={(e) => setHesap(e.target.value)} placeholder={t('kartvizit.liste.hesapSuzgeci')} />
          </label>
        )}
      </div>
      {hata && (
        <p className="mb-3 text-sm text-red-300" role="alert">
          {hata}
        </p>
      )}
      {kartlar === null ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : kartlar.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t('kartvizit.liste.bos')}</p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {kartlar.map((k) => (
            <li key={k.id} className="rounded-xl border border-white/10 bg-black/20 p-4" data-testid="kart-satiri" data-slug={k.slug}>
              <div className="flex items-start gap-3">
                {k.foto ? (
                  <img src={apiAdresi(k.foto.url)} alt="" width={48} height={48} className="h-12 w-12 shrink-0 rounded-full object-cover" loading="lazy" />
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-bold" style={{ background: k.tema.renk, color: '#fff' }} aria-hidden="true">
                    {k.ad_soyad.charAt(0).toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{k.ad_soyad}</p>
                  <p className="truncate text-xs text-muted-foreground">{[k.unvan, k.sirket].filter(Boolean).join(' · ') || '—'}</p>
                  <a href={k.kart_adresi} target="_blank" rel="noopener" className="mt-0.5 block truncate text-xs text-purple-300 hover:underline" dir="ltr">
                    /kart/{k.slug}
                  </a>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Rozet renk={k.aktif ? 'yesil' : 'gri'}>{t(k.aktif ? 'kartvizit.durum.aktif' : 'kartvizit.durum.pasif')}</Rozet>
                    <Rozet>{t(`kartvizit.duzen.${k.duzen}`)}</Rozet>
                    {k.sifreli && (
                      <Rozet renk="sari">
                        <Lock className="h-3 w-3" aria-hidden="true" /> {t('kartvizit.liste.parolali')}
                      </Rozet>
                    )}
                    {!!k.okunmamis && <Rozet renk="mor">{t('kartvizit.liste.okunmamis', { sayi: k.okunmamis })}</Rozet>}
                    {mod === 'yonetici' && <Rozet>{k.hesap_email || t('kartvizit.liste.ajans')}</Rozet>}
                  </div>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                {(['goruntulenme', 'rehber', 'tik'] as const).map((o) => (
                  <div key={o} className="rounded-lg bg-white/[0.04] p-2">
                    <dt className="text-muted-foreground">{t(`kartvizit.olay.${o}`)}</dt>
                    <dd className="mt-0.5 text-base font-semibold tabular-nums" data-sayi={o}>
                      {sayiYaz(k.son30[o] || 0, dil)}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-1 text-[10px] text-muted-foreground">{t('kartvizit.liste.son30')}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Button size="sm" variant="outline" className="h-9 gap-1 !bg-transparent border-white/20" onClick={() => setGorunum({ tip: 'duzenle', kayit: k })} data-testid="kart-duzenle">
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('kartvizit.liste.duzenle')}
                </Button>
                <Button size="sm" variant="outline" className="h-9 gap-1 !bg-transparent border-white/20" onClick={() => setGorunum({ tip: 'analiz', kayit: k })} data-testid="kart-analiz">
                  <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('kartvizit.liste.analiz')}
                </Button>
                <Button size="sm" variant="ghost" className="h-9 w-9 p-0" asChild>
                  <a href={k.kart_adresi} target="_blank" rel="noopener" aria-label={t('kartvizit.liste.ac')} title={t('kartvizit.liste.ac')}>
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                  </a>
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-9 w-9 p-0"
                  aria-label={t('kartvizit.liste.kopyala')}
                  title={t('kartvizit.liste.kopyala')}
                  onClick={() => void kopyala(k.kart_adresi, t('kartvizit.liste.kopyalandi'), t('kartvizit.hata.genel'))}
                >
                  <Copy className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-9 w-9 p-0"
                  aria-label={t('kartvizit.liste.qrIndir')}
                  title={t('kartvizit.liste.qrIndir')}
                  onClick={() => void api.qrIndir(k.id, 'png', k.slug).catch((e) => toast.error(hataMetni(t, e)))}
                  data-testid="kart-qr-indir-panel"
                >
                  <Download className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button size="sm" variant="ghost" className="h-9 w-9 p-0 text-red-300" aria-label={t('kartvizit.liste.sil')} title={t('kartvizit.liste.sil')} onClick={() => void sil(k)}>
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

export function Rozet({ children, renk }: { children: ReactNode; renk?: 'yesil' | 'gri' | 'sari' | 'mor' }) {
  const s =
    renk === 'yesil'
      ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
      : renk === 'sari'
        ? 'border-amber-400/30 bg-amber-500/10 text-amber-200'
        : renk === 'mor'
          ? 'border-purple-400/40 bg-purple-500/15 text-purple-100'
          : 'border-white/10 bg-white/[0.04] text-muted-foreground';
  return <span className={`inline-flex max-w-full items-center gap-1 truncate rounded-full border px-2 py-0.5 text-[11px] ${s}`}>{children}</span>;
}
