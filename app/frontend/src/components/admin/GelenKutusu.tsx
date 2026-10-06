import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Inbox, Loader2, RefreshCw, Search, X } from 'lucide-react';

import { goreliZaman, tamZaman } from '@/lib/denetim';
import {
  DURUM_SUZGECLERI,
  KAYNAKLAR,
  listeGetir,
  type DurumSuzgeci,
  type Kaynak,
  type ListeYaniti,
  type Oge,
} from '@/lib/gelenKutusu';
import OgeAyrintisi, { type ProjeyeCevrilecekTalep } from './gelenKutusu/OgeAyrintisi';
import { DURUM_RENGI, KAYNAK_IKONU } from './gelenKutusu/ortak';

/**
 * Faz 5G — birleşik gelen kutusu: yanıt bekleyen her şey tek listede.
 *
 * Solda liste (kaynak rozeti + ikon, kişi, özet, göreli zaman, durum noktası),
 * sağda seçili öğenin ayrıntısı + eylemler + AI yanıt taslağı. Dar ekranda tek
 * sütun: liste → ayrıntı (geri düğmesiyle). Eski "İletişim formu" sekmesinin
 * işlevleri burada "İletişim formu" öğelerinin eylemleri.
 *
 * Bağlantılar: `?kaynak=iletisim` süzgeçle açar; eski `?sekme=inquiries` de
 * (geriye uyum) iletişim formu süzgeciyle açılır; `?oge=destek:12` öğeyi seçer.
 */

const SAYFA_ADEDI = 30;

function adrestenBaslangic(): { kaynak: Kaynak | null; oge: string | null } {
  try {
    const q = new URLSearchParams(window.location.search);
    const k = q.get('kaynak') as Kaynak | null;
    const kaynak = k && (KAYNAKLAR as readonly string[]).includes(k) ? k : q.get('sekme') === 'inquiries' ? 'iletisim' : null;
    const oge = q.get('oge');
    return { kaynak, oge: oge && /^[a-z_]+:\d+$/.test(oge) ? oge : null };
  } catch {
    return { kaynak: null, oge: null };
  }
}

interface Props {
  onProjeyeCevir: (talep: ProjeyeCevrilecekTalep) => void;
  /** Menü rozeti: liste her yenilendiğinde yanıt bekleyen toplam. */
  onSayac?: (toplam: number) => void;
}

export default function GelenKutusu({ onProjeyeCevir, onSayac }: Props) {
  const { t, i18n } = useTranslation();
  const baslangic = useMemo(adrestenBaslangic, []);
  const [kaynak, setKaynak] = useState<Kaynak | null>(baslangic.kaynak);
  const [durum, setDurum] = useState<DurumSuzgeci>('bekleyen');
  const [aranan, setAranan] = useState('');
  const [q, setQ] = useState('');
  const [bas, setBas] = useState('');
  const [bit, setBit] = useState('');
  const [veri, setVeri] = useState<ListeYaniti | null>(null);
  const [ogeler, setOgeler] = useState<Oge[]>([]);
  const [sayfa, setSayfa] = useState(1);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [secili, setSecili] = useState<string | null>(baslangic.oge);
  const istekNo = useRef(0);
  const ayrintiRef = useRef<HTMLDivElement>(null);

  // Dar ekranda öğe seçilince ayrıntı (süzgeçlerin altında) görünür alana gelsin.
  useEffect(() => {
    if (!secili || window.matchMedia('(min-width: 1024px)').matches) return;
    ayrintiRef.current?.scrollIntoView({ block: 'start' });
  }, [secili]);

  // Arama: yazmayı bitirince (300 ms).
  useEffect(() => {
    const z = window.setTimeout(() => setQ(aranan.trim()), 300);
    return () => window.clearTimeout(z);
  }, [aranan]);

  const yukle = useCallback(
    async (hedefSayfa = 1) => {
      const no = ++istekNo.current;
      setYukleniyor(true);
      try {
        const g = await listeGetir({ kaynak, durum, q, bas, bit, sayfa: hedefSayfa, adet: SAYFA_ADEDI });
        if (no !== istekNo.current) return;
        setVeri(g);
        setOgeler((eski) => (hedefSayfa > 1 ? [...eski, ...g.ogeler] : g.ogeler));
        setSayfa(hedefSayfa);
        setHata(false);
        onSayac?.(g.sayilar.toplam);
      } catch {
        if (no === istekNo.current) setHata(true);
      } finally {
        if (no === istekNo.current) setYukleniyor(false);
      }
    },
    [kaynak, durum, q, bas, bit, onSayac]
  );

  useEffect(() => {
    void yukle(1);
  }, [yukle]);

  const seciliOge = useMemo(() => {
    if (!secili) return null;
    const [k, id] = secili.split(':');
    return { kaynak: k as Kaynak, kimlik: Number(id) };
  }, [secili]);

  const sayilar = veri?.sayilar;
  const meta = veri?.meta;
  const dil = i18n.language;

  return (
    <section className="space-y-4" data-testid="gelen-kutusu">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <Inbox className="h-5 w-5 text-pink-300" aria-hidden="true" />
            {t('gelenKutusu.baslik')}
            {sayilar && sayilar.toplam > 0 ? (
              <span className="rounded-full bg-pink-600 px-2 text-xs font-semibold leading-5 text-white" data-gk-toplam={sayilar.toplam}>
                {sayilar.toplam}
              </span>
            ) : null}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('gelenKutusu.aciklama')}</p>
        </div>
        <button
          type="button"
          onClick={() => void yukle(1)}
          className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
          data-testid="gk-yenile"
        >
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          {t('gelenKutusu.yenile')}
        </button>
      </div>

      {/* Kaynak hapları (yanıt bekleyen sayısıyla) */}
      {/* Dar ekranda tek kaydırmalı satır (dokuz hap alt alta yer kaplamasın); geniş ekranda sarılır. */}
      <div
        className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 lg:flex-wrap lg:overflow-visible"
        role="group"
        aria-label={t('gelenKutusu.kaynakSuzgeci')}
        data-testid="gk-kaynaklar"
      >
        <Hap secili={kaynak === null} onClick={() => setKaynak(null)} sayi={sayilar?.toplam} veriAnahtari="hepsi">
          {t('gelenKutusu.tumKaynaklar')}
        </Hap>
        {KAYNAKLAR.map((k) => {
          const Ikon = KAYNAK_IKONU[k];
          return (
            <Hap key={k} secili={kaynak === k} onClick={() => setKaynak(kaynak === k ? null : k)} sayi={sayilar?.kaynaklar[k]} veriAnahtari={k}>
              <Ikon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {t(`gelenKutusu.kaynak.${k}`)}
            </Hap>
          );
        })}
      </div>

      {/* Durum, arama, tarih */}
      <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
        <div className="flex flex-wrap gap-1" role="group" aria-label={t('gelenKutusu.durumSuzgeci.etiket')} data-testid="gk-durumlar">
          {DURUM_SUZGECLERI.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={durum === d}
              onClick={() => setDurum(d)}
              data-gk-durum={d}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                durum === d
                  ? 'border-pink-400/40 bg-pink-500/15 text-foreground'
                  : 'border-white/10 text-muted-foreground hover:bg-white/5 hover:text-foreground'
              }`}
            >
              {t(`gelenKutusu.durumSuzgeci.${d}`)}
            </button>
          ))}
        </div>
        <div className="relative w-full lg:ms-auto lg:w-64">
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            value={aranan}
            onChange={(e) => setAranan(e.target.value)}
            placeholder={t('gelenKutusu.ara')}
            aria-label={t('gelenKutusu.ara')}
            data-testid="gk-ara"
            className="h-9 w-full rounded-full border border-white/10 bg-white/5 pe-3 ps-9 text-sm placeholder:text-muted-foreground focus:border-pink-400/50 focus:outline-none focus:ring-2 focus:ring-pink-500/20"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <label className="inline-flex items-center gap-1">
            {t('gelenKutusu.tarih.bas')}
            <input
              type="date"
              value={bas}
              max={bit || undefined}
              onChange={(e) => setBas(e.target.value)}
              data-testid="gk-bas"
              className="h-8 rounded-lg border border-white/10 bg-white/5 px-2 text-xs text-foreground"
            />
          </label>
          <label className="inline-flex items-center gap-1">
            {t('gelenKutusu.tarih.bit')}
            <input
              type="date"
              value={bit}
              min={bas || undefined}
              onChange={(e) => setBit(e.target.value)}
              data-testid="gk-bit"
              className="h-8 rounded-lg border border-white/10 bg-white/5 px-2 text-xs text-foreground"
            />
          </label>
          {bas || bit ? (
            <button
              type="button"
              onClick={() => {
                setBas('');
                setBit('');
              }}
              className="inline-flex items-center gap-1 rounded-full px-2 py-1 hover:bg-white/5 hover:text-foreground"
            >
              <X className="h-3 w-3" aria-hidden="true" />
              {t('gelenKutusu.tarih.temizle')}
            </button>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        {/* Liste */}
        <div className={`${seciliOge ? 'hidden lg:block' : ''} min-w-0`} data-testid="gk-liste-kutusu">
          {hata ? (
            <p className="rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-100">{t('gelenKutusu.hata')}</p>
          ) : yukleniyor && !ogeler.length ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
            </div>
          ) : !ogeler.length ? (
            <p className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-muted-foreground" data-testid="gk-bos">
              {durum === 'bekleyen' && !q && !kaynak && !bas && !bit ? t('gelenKutusu.bosBekleyen') : t('gelenKutusu.bos')}
            </p>
          ) : (
            <>
              <ul className="cam-kart divide-y divide-white/5 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]" data-testid="gk-liste">
                {ogeler.map((o) => {
                  const Ikon = KAYNAK_IKONU[o.kaynak];
                  const aktif = secili === o.anahtar;
                  return (
                    <li key={o.anahtar}>
                      <button
                        type="button"
                        onClick={() => setSecili(o.anahtar)}
                        aria-current={aktif ? 'true' : undefined}
                        data-gk-oge={o.anahtar}
                        data-gk-oge-durum={o.durum}
                        className={`flex w-full min-w-0 items-start gap-3 px-4 py-3 text-start transition-colors ${
                          aktif ? 'bg-pink-500/10' : 'hover:bg-white/[0.04]'
                        }`}
                      >
                        <span className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5">
                          <Ikon className="h-4 w-4 text-purple-200" aria-hidden="true" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex min-w-0 items-center gap-2">
                            <span
                              className={`h-2 w-2 shrink-0 rounded-full ${DURUM_RENGI[o.durum]}`}
                              title={t(`gelenKutusu.durum.${o.durum}`)}
                              aria-hidden="true"
                            />
                            <span className="sr-only">{t(`gelenKutusu.durum.${o.durum}`)}</span>
                            <span className={`truncate text-sm ${o.durum === 'yeni' ? 'font-semibold' : 'font-medium'}`}>
                              <bdi>{o.kisi_ad || o.kisi_eposta || '—'}</bdi>
                            </span>
                            <time
                              className="ms-auto shrink-0 text-[11px] text-muted-foreground"
                              dateTime={o.zaman || undefined}
                              title={tamZaman(o.zaman, dil)}
                            >
                              {goreliZaman(o.zaman, dil)}
                            </time>
                          </span>
                          <span className="mt-0.5 flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
                            <span className="shrink-0 rounded-full border border-white/10 px-1.5 py-px uppercase tracking-wider">
                              {t(`gelenKutusu.kaynak.${o.kaynak}`)}
                            </span>
                            {o.baslik ? (
                              <span className="truncate">
                                <bdi>{o.baslik}</bdi>
                              </span>
                            ) : null}
                          </span>
                          {o.ozet ? (
                            <span className="mt-1 line-clamp-2 break-words text-xs text-slate-300">
                              <bdi>{o.ozet}</bdi>
                            </span>
                          ) : null}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span data-testid="gk-gosterilen">{t('gelenKutusu.gosterilen', { sayi: ogeler.length, toplam: veri?.toplam ?? 0 })}</span>
                {veri && ogeler.length < veri.toplam ? (
                  <button
                    type="button"
                    onClick={() => void yukle(sayfa + 1)}
                    disabled={yukleniyor}
                    className="rounded-full border border-white/10 px-3 py-1 hover:bg-white/5 hover:text-foreground disabled:opacity-50"
                    data-testid="gk-daha"
                  >
                    {t('gelenKutusu.dahaFazla')}
                  </button>
                ) : null}
              </div>
            </>
          )}
        </div>

        {/* Ayrıntı — geniş ekranda liste kaydırılırken görünür kalır. */}
        <div
          ref={ayrintiRef}
          className={`${seciliOge ? '' : 'hidden lg:block'} min-w-0 scroll-mt-24 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto`}
        >
          {seciliOge ? (
            <OgeAyrintisi
              key={secili}
              kaynak={seciliOge.kaynak}
              kimlik={seciliOge.kimlik}
              aiHazir={meta?.ai_hazir}
              epostaHazir={meta?.eposta_hazir}
              onDegisti={() => void yukle(1)}
              onGeri={() => setSecili(null)}
              onProjeyeCevir={onProjeyeCevir}
            />
          ) : (
            <div className="cam-kart flex min-h-[12rem] items-center justify-center rounded-2xl border border-dashed border-white/10 p-6 text-center text-sm text-muted-foreground">
              {t('gelenKutusu.secin')}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Hap({
  secili,
  onClick,
  sayi,
  veriAnahtari,
  children,
}: {
  secili: boolean;
  onClick: () => void;
  sayi?: number;
  veriAnahtari: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={secili}
      onClick={onClick}
      data-gk-kaynak={veriAnahtari}
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs transition-colors ${
        secili
          ? 'border-pink-400/40 bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-foreground'
          : 'border-white/10 text-muted-foreground hover:bg-white/5 hover:text-foreground'
      }`}
    >
      {children}
      {sayi ? (
        <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-pink-600 px-1.5 text-[10px] font-semibold leading-4 text-white" data-gk-sayi={sayi}>
          {sayi > 99 ? '99+' : sayi}
        </span>
      ) : null}
    </button>
  );
}
