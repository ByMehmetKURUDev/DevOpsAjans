import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Download, FileUp, Link as LinkIcon, Loader2, Plus, QrCode, Search, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import Ayrinti from '@/components/dinamikQr/Ayrinti';
import Sihirbaz from '@/components/dinamikQr/Sihirbaz';
import TopluYukleme from '@/components/dinamikQr/TopluYukleme';
import { DurumRozeti, KART, SECIM, TurRozeti, kopyala, sayiYaz } from '@/components/dinamikQr/ortak';
import { DURUMLAR, TURLER, hataMetni, qrApi, type QrKaydi, type QrMeta, type QrMod } from '@/lib/dinamikQr';

/**
 * Faz 4Q — "QR ve kısa link" sekmesi. Yönetici panelinde (`mod="yonetici"`:
 * ajansın kendi kayıtları + bütün müşterilerinki, engelleme) ve müşteri
 * panelinde (`mod="musteri"`: yalnız etkin hesabın kayıtları, kayıt hakkı)
 * aynı bileşen.
 *
 * Görünümler: liste (süzgeçler, seçip ZIP indirme) → sihirbaz (oluştur/düzenle)
 * → ayrıntı (görsel, indirme, analitik) → toplu CSV.
 */

type Gorunum =
  | { tip: 'liste' }
  | { tip: 'sihirbaz'; kayit: QrKaydi | null; kisa?: boolean }
  | { tip: 'ayrinti'; id: number }
  | { tip: 'toplu' };

export default function DinamikQr({ mod }: { mod: QrMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const api = useMemo(() => qrApi(mod), [mod]);
  const [gorunum, setGorunum] = useState<Gorunum>({ tip: 'liste' });
  const [meta, setMeta] = useState<QrMeta | null>(null);
  const [kayitlar, setKayitlar] = useState<QrKaydi[] | null>(null);
  const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
  const [ara, setAra] = useState('');
  const [turSuzgeci, setTurSuzgeci] = useState('');
  const [durumSuzgeci, setDurumSuzgeci] = useState('');
  const [kapsam, setKapsam] = useState('');
  const [secili, setSecili] = useState<Set<number>>(new Set());
  const [zipYukleniyor, setZipYukleniyor] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setYuklemeHatasi(null);
    try {
      const [m, l] = await Promise.all([
        api.meta(),
        api.liste({
          tur: turSuzgeci && turSuzgeci !== 'kisa_link' ? turSuzgeci : undefined,
          kisa: turSuzgeci === 'kisa_link' ? true : undefined,
          durum: durumSuzgeci || undefined,
          ara: ara.trim() || undefined,
          hesap: mod === 'yonetici' && kapsam ? kapsam : undefined,
        }),
      ]);
      setMeta(m);
      setKayitlar(l.items);
      setSecili((s) => new Set([...s].filter((id) => l.items.some((k) => k.id === id))));
    } catch (e) {
      setYuklemeHatasi(hataMetni(t, e));
      setKayitlar([]);
    }
  }, [api, turSuzgeci, durumSuzgeci, ara, kapsam, mod, t]);

  useEffect(() => {
    if (gorunum.tip !== 'liste') return;
    const zaman = window.setTimeout(() => void yukle(), ara ? 300 : 0);
    return () => window.clearTimeout(zaman);
  }, [yukle, gorunum.tip, ara]);

  const sinirDolu = !!meta && meta.kayit_siniri !== null && (meta.kayit_sayisi ?? 0) >= meta.kayit_siniri;
  const yeni = (kisa = false) => {
    if (sinirDolu) {
      toast.error(t('dinamikQr.hata.kayit_siniri', { sinir: meta?.kayit_siniri }));
      return;
    }
    setGorunum({ tip: 'sihirbaz', kayit: null, kisa });
  };

  const zip = async (bicim: 'png' | 'svg') => {
    setZipYukleniyor(bicim);
    try {
      await api.zipIndir([...secili], bicim);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setZipYukleniyor(null);
    }
  };

  const ust = (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="flex items-center gap-2 text-2xl font-bold" id="qr-baslik">
          <QrCode className="h-6 w-6 text-purple-300" aria-hidden="true" />
          {t('dinamikQr.baslik')}
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {mod === 'yonetici' ? t('dinamikQr.aciklamaYonetici') : t('dinamikQr.aciklama')}
        </p>
      </div>
      {meta && meta.kayit_siniri !== null && (
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground" data-testid="qr-kayit-hakki">
          {t('dinamikQr.kayitHakki', { sayi: meta.kayit_sayisi ?? 0, sinir: meta.kayit_siniri })}
        </span>
      )}
    </div>
  );

  if (gorunum.tip === 'sihirbaz') {
    return (
      <section aria-labelledby="qr-baslik">
        {ust}
        <Sihirbaz
          api={api}
          mod={mod}
          meta={meta}
          kayit={gorunum.kayit}
          kisaBaslangic={gorunum.kisa}
          onKapat={() => setGorunum(gorunum.kayit ? { tip: 'ayrinti', id: gorunum.kayit.id } : { tip: 'liste' })}
          onKaydedildi={(k) => setGorunum({ tip: 'ayrinti', id: k.id })}
        />
      </section>
    );
  }
  if (gorunum.tip === 'ayrinti') {
    return (
      <section aria-labelledby="qr-baslik">
        {ust}
        <Ayrinti
          key={gorunum.id}
          api={api}
          mod={mod}
          id={gorunum.id}
          onGeri={() => setGorunum({ tip: 'liste' })}
          onDuzenle={(k) => setGorunum({ tip: 'sihirbaz', kayit: k })}
          onSilindi={() => setGorunum({ tip: 'liste' })}
        />
      </section>
    );
  }
  if (gorunum.tip === 'toplu') {
    return (
      <section aria-labelledby="qr-baslik">
        {ust}
        <TopluYukleme
          api={api}
          meta={meta}
          onGeri={() => setGorunum({ tip: 'liste' })}
          onBitti={() => setGorunum({ tip: 'liste' })}
        />
      </section>
    );
  }

  const tumSecili = !!kayitlar?.length && kayitlar.every((k) => secili.has(k.id));

  return (
    <section aria-labelledby="qr-baslik" data-testid="qr-sekmesi">
      {ust}
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-4 flex flex-wrap gap-2">
          <Button onClick={() => yeni(false)} className="gap-1.5" data-testid="qr-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('dinamikQr.yeni')}
          </Button>
          <Button variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => yeni(true)} data-testid="qr-yeni-kisa">
            <LinkIcon className="h-4 w-4" aria-hidden="true" />
            {t('dinamikQr.yeniKisa')}
          </Button>
          <Button
            variant="outline"
            className="gap-1.5 !bg-transparent border-white/20"
            onClick={() => setGorunum({ tip: 'toplu' })}
            data-testid="qr-toplu-ac"
          >
            <FileUp className="h-4 w-4" aria-hidden="true" />
            {t('dinamikQr.toplu.baslik')}
          </Button>
        </div>

        <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <label className="relative block">
            <span className="sr-only">{t('dinamikQr.ara')}</span>
            <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={ara} onChange={(e) => setAra(e.target.value)} placeholder={t('dinamikQr.ara')} className="ps-8" data-testid="qr-ara" />
          </label>
          <label className="block">
            <span className="sr-only">{t('dinamikQr.liste.tur')}</span>
            <select className={SECIM} value={turSuzgeci} onChange={(e) => setTurSuzgeci(e.target.value)} data-testid="qr-tur-suzgeci">
              <option value="">{t('dinamikQr.tumTurler')}</option>
              <option value="kisa_link">{t('dinamikQr.tur.kisa_link')}</option>
              {TURLER.map((x) => (
                <option key={x} value={x}>
                  {t(`dinamikQr.tur.${x}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="sr-only">{t('dinamikQr.liste.durum')}</span>
            <select className={SECIM} value={durumSuzgeci} onChange={(e) => setDurumSuzgeci(e.target.value)}>
              <option value="">{t('dinamikQr.tumDurumlar')}</option>
              {DURUMLAR.map((x) => (
                <option key={x} value={x}>
                  {t(`dinamikQr.durum.${x}`)}
                </option>
              ))}
            </select>
          </label>
          {mod === 'yonetici' && (
            <label className="block">
              <span className="sr-only">{t('dinamikQr.liste.sahip')}</span>
              <select className={SECIM} value={kapsam} onChange={(e) => setKapsam(e.target.value)}>
                <option value="">{t('dinamikQr.hepsi')}</option>
                <option value="ajans">{t('dinamikQr.yalnizAjans')}</option>
              </select>
            </label>
          )}
        </div>

        {secili.size > 0 && (
          <div
            className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-purple-400/30 bg-purple-500/10 p-2 text-sm"
            data-testid="qr-secim-cubugu"
          >
            <span className="px-1">{t('dinamikQr.liste.secili', { sayi: secili.size })}</span>
            {(['png', 'svg'] as const).map((b) => (
              <Button
                key={b}
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 !bg-transparent border-white/20"
                disabled={!!zipYukleniyor}
                onClick={() => zip(b)}
                data-testid={`qr-zip-${b}`}
              >
                {zipYukleniyor === b ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Download className="h-3.5 w-3.5" aria-hidden="true" />}
                {t(b === 'png' ? 'dinamikQr.liste.zipPng' : 'dinamikQr.liste.zipSvg')}
              </Button>
            ))}
            <Button size="sm" variant="ghost" className="h-8 gap-1" onClick={() => setSecili(new Set())}>
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              {t('dinamikQr.liste.secimiTemizle')}
            </Button>
          </div>
        )}

        {yuklemeHatasi && (
          <p className="mb-3 text-sm text-red-300" role="alert">
            {yuklemeHatasi}
          </p>
        )}

        {kayitlar === null ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : kayitlar.length === 0 ? (
          <div className="py-14 text-center" data-testid="qr-bos">
            <QrCode className="mx-auto mb-3 h-10 w-10 text-purple-300/60" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">{ara || turSuzgeci || durumSuzgeci ? t('dinamikQr.sonucYok') : t('dinamikQr.bos')}</p>
          </div>
        ) : (
          <div data-testid="qr-liste">
            <label className="mb-2 flex items-center gap-2 px-1 text-xs text-muted-foreground">
              <input
                type="checkbox"
                className="h-4 w-4 accent-purple-500"
                checked={tumSecili}
                onChange={(e) => setSecili(e.target.checked ? new Set(kayitlar.map((k) => k.id)) : new Set())}
              />
              {t('dinamikQr.liste.tumunuSec')} ({sayiYaz(kayitlar.length, dil)})
            </label>
            <ul className="divide-y divide-white/5 rounded-xl border border-white/10">
              {kayitlar.map((k) => (
                <li key={k.id} className="flex items-start gap-3 p-3 sm:items-center" data-qr-satir={k.id} data-qr-kod={k.kod}>
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 flex-none accent-purple-500 sm:mt-0"
                    checked={secili.has(k.id)}
                    aria-label={t('dinamikQr.liste.sec', { ad: k.ad })}
                    onChange={(e) =>
                      setSecili((s) => {
                        const y = new Set(s);
                        if (e.target.checked) y.add(k.id);
                        else y.delete(k.id);
                        return y;
                      })
                    }
                  />
                  <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1.4fr)_auto_auto] sm:items-center">
                    <div className="min-w-0">
                      <button
                        type="button"
                        onClick={() => setGorunum({ tip: 'ayrinti', id: k.id })}
                        className="block max-w-full truncate text-start font-medium hover:text-purple-200 hover:underline"
                        data-testid="qr-satir-ac"
                      >
                        {k.ad}
                      </button>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <TurRozeti tur={k.tur} kisa={k.kisa_link} />
                        {mod === 'yonetici' && (
                          <span className="truncate text-[11px] text-muted-foreground" title={k.hesap_email || undefined}>
                            {k.hesap_email || t('dinamikQr.liste.ajans')}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex min-w-0 items-center gap-1">
                      {k.kisa_adres ? (
                        <>
                          <span className="truncate font-mono text-xs text-purple-200" dir="ltr" data-testid="qr-satir-adres">
                            {k.kisa_adres.replace(/^https?:\/\//, '')}
                          </span>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 flex-none"
                            aria-label={t('dinamikQr.liste.kopyala')}
                            onClick={() => kopyala(k.kisa_adres!, t('dinamikQr.liste.kopyalandi'), t('dinamikQr.liste.kopyalanamadi'))}
                            data-testid="qr-satir-kopyala"
                          >
                            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                        </>
                      ) : (
                        <span className="truncate text-xs text-muted-foreground" dir="auto">
                          {k.hedef_ozet}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground tabular-nums" data-testid="qr-satir-tarama">
                      {k.statik ? '—' : t('dinamikQr.liste.taramaSayisi', { sayi: sayiYaz(k.tarama_sayisi, dil) })}
                    </div>
                    <div>
                      <DurumRozeti durum={k.durum} statik={k.statik} />
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
