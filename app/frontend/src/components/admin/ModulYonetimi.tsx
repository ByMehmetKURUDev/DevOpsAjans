import { Suspense, useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Blocks, Loader2, Lock, RefreshCw, RotateCcw, Save, Search, TriangleAlert, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  KATEGORILER,
  ModulHatasi,
  manifestiGetir,
  modulAyarla,
  modulMusterileriGetir,
  modulOzetiGetir,
  modulVarsayilanaDon,
  musteriModulleriGetir,
  type AyarAlani,
  type ManifestModulu,
  type ModulKategorisi,
  type ModulMusterisi,
  type ModulOzeti,
  type MusteriModulleri,
  type YoneticiModulu,
} from '@/lib/moduller';
import { modulIkonu } from '@/lib/modulIkonlari';
import { ekliLazy } from '@/i18n/ekliLazy';

// Faz 6R: "Sektör paketi uygula" + hazır ayarlar — yalnız müşteri seçilince indirilir
// (metinler `sektorPaketi`, paket/set adları `modulVitrini` ek paketinde).
const SektorPaketiAlani = ekliLazy(['sektorPaketi', 'modulVitrini'], () => import('./sektorPaketi/SektorPaketiAlani'));
// Faz 4L: "Marka teması" modülünün satırında müşterinin markası (logo/renk/yazı tipi) — tıklanınca indirilir.
const MarkaAyari = ekliLazy('markaTemasi', () => import('@/components/marka/MarkaAyari'));

/**
 * Yönetici paneli › Modüller.
 *
 * Üstte modül kataloğu (manifest): kategori süzgeci, durum rozeti, açık
 * müşteri sayısı. Altta bir müşteri seçilince her modül için anahtar:
 * çekirdekler kilitli, kaynak rozeti (varsayılan / paket / elle),
 * bağımlılık uyarıları, "varsayılana dön" ve (manifestte tanımlıysa)
 * müşteriye özel ayarlar. Yöneticinin kendi panelinde bütün modüller her
 * zaman açık; buradaki anahtarlar yalnız müşteriyi etkiler.
 *
 * Faz 6R: müşteri seçiliyken "Sektör paketi uygula" (paketin modülleri + hazır
 * sektör ayarları tek işlemde) ve geçmişten "paketi kaldır". Derin bağlantı:
 * `/admin?sekme=moduller&musteri=<e-posta>&paket=<anahtar>` (gelen kutusu kısayolu).
 */

const EPOSTA_DESENI = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const SECIM_SINIFI =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

function DurumRozeti({ durum }: { durum: string }) {
  const { t } = useTranslation();
  const renk =
    durum === 'yakinda'
      ? 'border-sky-400/30 bg-sky-500/10 text-sky-300'
      : durum === 'beta'
        ? 'border-amber-400/30 bg-amber-500/10 text-amber-300'
        : 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-widest ${renk}`}>
      {t(`modul.durum.${durum}`)}
    </span>
  );
}

function KaynakRozeti({ kaynak }: { kaynak: string }) {
  const { t } = useTranslation();
  const renk =
    kaynak === 'elle'
      ? 'border-pink-400/40 bg-pink-500/10 text-pink-200'
      : kaynak === 'paket'
        ? 'border-purple-400/40 bg-purple-500/10 text-purple-200'
        : 'border-white/15 bg-white/5 text-muted-foreground';
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-widest ${renk}`}
      data-kaynak={kaynak}
    >
      {t(`modul.kaynak.${kaynak}`)}
    </span>
  );
}

function AyarFormu({
  modul,
  calisiyor,
  onKaydet,
}: {
  modul: YoneticiModulu;
  calisiyor: boolean;
  onKaydet: (ayarlar: Record<string, unknown>) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [degerler, setDegerler] = useState<Record<string, unknown>>(modul.ayarlar);

  useEffect(() => {
    setDegerler(modul.ayarlar);
  }, [modul.ayarlar]);

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    const temiz: Record<string, unknown> = {};
    for (const alan of modul.ayar_alanlari) {
      const d = degerler[alan.anahtar];
      if (alan.tur === 'int') {
        // Boş bırakılan alan: boş olabiliyorsa null (genel ayar geçerli).
        const bos = d === null || d === undefined || String(d).trim() === '';
        temiz[alan.anahtar] = bos && alan.bos_olabilir ? null : Number(d);
      } else {
        temiz[alan.anahtar] = d;
      }
    }
    await onKaydet(temiz);
  };

  const alanCiz = (alan: AyarAlani) => {
    const id = `ayar-${modul.anahtar}-${alan.anahtar}`;
    const etiket = t(`modul.ayar.${alan.anahtar}`, { defaultValue: alan.anahtar });
    const deger = degerler[alan.anahtar];
    if (alan.tur === 'bool') {
      return (
        <label key={alan.anahtar} htmlFor={id} className="flex items-center gap-2 text-sm">
          <input
            id={id}
            type="checkbox"
            checked={Boolean(deger)}
            onChange={(e) => setDegerler({ ...degerler, [alan.anahtar]: e.target.checked })}
            className="h-4 w-4 accent-purple-500"
          />
          {etiket}
        </label>
      );
    }
    if (alan.tur === 'secim') {
      return (
        <label key={alan.anahtar} htmlFor={id} className="block text-xs text-muted-foreground">
          <span className="mb-1 block">{etiket}</span>
          <select
            id={id}
            value={String(deger ?? '')}
            onChange={(e) => setDegerler({ ...degerler, [alan.anahtar]: e.target.value })}
            className={SECIM_SINIFI}
          >
            {(alan.secenekler ?? []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      );
    }
    return (
      <label key={alan.anahtar} htmlFor={id} className="block text-xs text-muted-foreground">
        <span className="mb-1 block">{etiket}</span>
        <Input
          id={id}
          type={alan.tur === 'int' ? 'number' : 'text'}
          min={alan.en_az ?? undefined}
          max={alan.en_cok ?? undefined}
          value={String(deger ?? '')}
          placeholder={alan.bos_olabilir ? t('modul.yonetim.bosGenel') : undefined}
          onChange={(e) => setDegerler({ ...degerler, [alan.anahtar]: e.target.value })}
          className="h-9 bg-white/5 border-white/10"
        />
      </label>
    );
  };

  return (
    <form onSubmit={gonder} className="mt-3 rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <p className="mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">{t('modul.yonetim.ayarlar')}</p>
      <div className="grid gap-3 sm:grid-cols-2">{modul.ayar_alanlari.map(alanCiz)}</div>
      <Button
        type="submit"
        size="sm"
        variant="outline"
        disabled={calisiyor}
        className="mt-3 gap-1.5 !bg-transparent border-white/20"
      >
        <Save className="h-3.5 w-3.5" aria-hidden="true" />
        {t('modul.yonetim.ayarKaydet')}
      </Button>
    </form>
  );
}

export default function ModulYonetimi() {
  const { t } = useTranslation();

  const [manifest, setManifest] = useState<ManifestModulu[]>([]);
  const [ozet, setOzet] = useState<ModulOzeti | null>(null);
  const [musteriler, setMusteriler] = useState<ModulMusterisi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [kategori, setKategori] = useState<ModulKategorisi | 'hepsi'>('hepsi');

  const [arama, setArama] = useState('');
  const [secili, setSecili] = useState<string | null>(null);
  const [markaAcik, setMarkaAcik] = useState(false);
  const [ayrinti, setAyrinti] = useState<MusteriModulleri | null>(null);
  const [ayrintiYukleniyor, setAyrintiYukleniyor] = useState(false);
  const [calisan, setCalisan] = useState<string | null>(null);
  const [ilkPaket, setIlkPaket] = useState<string | null>(null);
  const location = useLocation();

  const adi = useCallback((anahtar: string) => t(`modul.m.${anahtar}.ad`, { defaultValue: anahtar }), [t]);

  const katalogYukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      const [m, o, ml] = await Promise.all([manifestiGetir(), modulOzetiGetir(), modulMusterileriGetir()]);
      setManifest(m);
      setOzet(o);
      setMusteriler(ml);
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void katalogYukle();
  }, [katalogYukle]);

  const musteriSec = useCallback(async (eposta: string, paket: string | null = null) => {
    setSecili(eposta);
    setIlkPaket(paket);
    setAyrinti(null);
    setAyrintiYukleniyor(true);
    try {
      setAyrinti(await musteriModulleriGetir(eposta));
    } catch {
      toast.error(t('modul.yonetim.musteriHata'));
    } finally {
      setAyrintiYukleniyor(false);
    }
  }, [t]);

  // Faz 6R: derin bağlantı (`?musteri=…&paket=…`) — müşteriyi seç, paket formunu açık getir.
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    const musteri = (q.get('musteri') || '').trim().toLowerCase();
    if (musteri && EPOSTA_DESENI.test(musteri)) void musteriSec(musteri, q.get('paket'));
  }, [location.search, musteriSec]);

  /** Sektör paketi uygulandı/kaldırıldı: ayrıntıyı yerinde tazele (alan kapanmasın). */
  const ayrintiTazele = useCallback(async () => {
    if (!secili) return;
    try {
      setAyrinti(await musteriModulleriGetir(secili));
      modulOzetiGetir().then(setOzet).catch(() => {});
    } catch {
      toast.error(t('modul.yonetim.musteriHata'));
    }
  }, [secili, t]);

  const hataGoster = (h: unknown) => {
    if (h instanceof ModulHatasi) {
      const liste = h.moduller.map(adi).join(', ');
      toast.error(t(`modul.hata.${h.kod}`, { moduller: liste, defaultValue: t('modul.hata.genel') }));
    } else {
      toast.error(t('modul.hata.genel'));
    }
  };

  const islem = async (anahtar: string, calistir: () => Promise<MusteriModulleri>, basari: string) => {
    setCalisan(anahtar);
    try {
      setAyrinti(await calistir());
      toast.success(basari);
      modulOzetiGetir().then(setOzet).catch(() => {});
    } catch (h) {
      hataGoster(h);
    } finally {
      setCalisan(null);
    }
  };

  const ozetSayisi = (anahtar: string) => ozet?.moduller.find((m) => m.anahtar === anahtar)?.acik_musteri ?? null;

  const gorunenKatalog = useMemo(
    () => manifest.filter((m) => kategori === 'hepsi' || m.kategori === kategori),
    [manifest, kategori]
  );

  const aramaSonucu = useMemo(() => {
    const q = arama.trim().toLowerCase();
    const liste = q
      ? musteriler.filter((m) => m.eposta.includes(q) || (m.ad || '').toLowerCase().includes(q))
      : musteriler;
    return liste.slice(0, 50);
  }, [musteriler, arama]);

  const aramaGonder = (e: FormEvent) => {
    e.preventDefault();
    const q = arama.trim().toLowerCase();
    if (EPOSTA_DESENI.test(q)) void musteriSec(q);
    else if (aramaSonucu.length === 1) void musteriSec(aramaSonucu[0].eposta);
  };

  if (yukleniyor) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  if (hata) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive">
        {t('modul.yonetim.hata')}
        <Button onClick={katalogYukle} variant="outline" size="sm" className="ml-4 !bg-transparent border-white/20">
          {t('modul.yonetim.yenile')}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-10" data-testid="modul-yonetimi">
      {/* ---------------- Katalog ---------------- */}
      <section aria-labelledby="modul-katalog-baslik">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="modul-katalog-baslik" className="flex items-center gap-2 text-2xl font-semibold">
              <Blocks className="h-6 w-6 text-purple-400" aria-hidden="true" />
              {t('modul.yonetim.baslik')}
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('modul.yonetim.aciklama')}</p>
          </div>
          <Button onClick={katalogYukle} variant="outline" size="sm" className="gap-1.5 !bg-transparent border-white/20">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            {t('modul.yonetim.yenile')}
          </Button>
        </div>

        <div className="mb-5 flex flex-wrap gap-2" role="group" aria-label={t('modul.yonetim.kategoriSuzgeci')}>
          {(['hepsi', ...KATEGORILER] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKategori(k)}
              aria-pressed={kategori === k}
              data-kategori={k}
              className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                kategori === k
                  ? 'border-purple-400/60 bg-purple-500/20 text-white'
                  : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/25'
              }`}
            >
              {k === 'hepsi' ? t('modul.yonetim.hepsi') : t(`modul.kategori.${k}`)}
            </button>
          ))}
        </div>

        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {gorunenKatalog.map((m) => {
            const Ikon = modulIkonu(m.ikon);
            const sayi = ozetSayisi(m.anahtar);
            return (
              <li
                key={m.anahtar}
                className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5"
                data-testid={`katalog-${m.anahtar}`}
              >
                <div className="flex gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-purple-600 to-pink-600 text-white">
                    <Ikon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{t(m.ad_anahtari)}</h3>
                      <DurumRozeti durum={m.durum} />
                      {m.cekirdek ? (
                        <Lock className="h-3.5 w-3.5 text-muted-foreground" aria-label={t('modul.yonetim.cekirdekKilitli')} />
                      ) : null}
                    </div>
                    <p className="text-xs uppercase tracking-widest text-purple-300/80">
                      {t(`modul.kategori.${m.kategori}`)}
                    </p>
                  </div>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{t(m.aciklama_anahtari)}</p>
                <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                  {m.gerekli_rol === 'admin' ? (
                    <span className="rounded-full border border-white/15 px-2 py-0.5 text-muted-foreground">
                      {t('modul.yonetim.yalnizAjans')}
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 rounded-full border border-white/15 px-2 py-0.5 text-foreground/80"
                      data-testid={`katalog-sayi-${m.anahtar}`}
                    >
                      <Users className="h-3 w-3" aria-hidden="true" />
                      {t('modul.yonetim.acikMusteri', { sayi: sayi ?? 0, toplam: ozet?.toplam_musteri ?? 0 })}
                    </span>
                  )}
                  {m.paketler.length > 0 && m.gerekli_rol !== 'admin' ? (
                    <span className="text-muted-foreground">
                      {t('modul.yonetim.paketler')}: {m.paketler.join(' · ')}
                    </span>
                  ) : null}
                </div>
                {m.bagimliliklar.length > 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {t('modul.yonetim.bagimli', { moduller: m.bagimliliklar.map(adi).join(', ') })}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      {/* ---------------- Müşteri başına ---------------- */}
      <section aria-labelledby="modul-musteri-baslik" className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="cam-kart h-fit rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 id="modul-musteri-baslik" className="mb-1 text-lg font-semibold">
            {t('modul.yonetim.musteriBaslik')}
          </h2>
          <p className="mb-4 text-xs text-muted-foreground">{t('modul.yonetim.musteriAciklama')}</p>
          <form onSubmit={aramaGonder} className="mb-3 flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                value={arama}
                onChange={(e) => setArama(e.target.value)}
                placeholder={t('modul.yonetim.musteriAra')}
                aria-label={t('modul.yonetim.musteriAra')}
                className="h-10 bg-white/5 border-white/10 pl-9"
                data-testid="modul-musteri-ara"
              />
            </div>
            <Button type="submit" size="sm" className="h-10 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0">
              {t('modul.yonetim.ac')}
            </Button>
          </form>
          <ul className="max-h-[420px] space-y-1 overflow-y-auto" data-testid="modul-musteri-listesi">
            {aramaSonucu.length === 0 ? (
              <li className="py-4 text-center text-xs text-muted-foreground">{t('modul.yonetim.musteriYok')}</li>
            ) : (
              aramaSonucu.map((m) => (
                <li key={m.eposta}>
                  <button
                    type="button"
                    onClick={() => void musteriSec(m.eposta)}
                    aria-pressed={secili === m.eposta}
                    data-eposta={m.eposta}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                      secili === m.eposta ? 'bg-purple-500/20 text-white' : 'hover:bg-white/5 text-muted-foreground'
                    }`}
                  >
                    <span className="block truncate">{m.ad || m.eposta}</span>
                    {m.ad ? <span className="block truncate text-xs opacity-70">{m.eposta}</span> : null}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>

        <div data-testid="modul-musteri-ayrinti">
          {!secili ? (
            <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-10 text-center text-sm text-muted-foreground">
              {t('modul.yonetim.musteriSec')}
            </div>
          ) : ayrintiYukleniyor || !ayrinti ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('modul.yonetim.secili')}</p>
                  <p className="text-lg font-semibold">{ayrinti.eposta}</p>
                </div>
                <span className="rounded-full border border-purple-400/30 bg-purple-500/10 px-3 py-1 text-xs text-purple-200">
                  {ayrinti.paket
                    ? t('modul.yonetim.paketVar', { paket: ayrinti.paket })
                    : t('modul.yonetim.paketYok')}
                </span>
              </div>
              <Suspense
                fallback={
                  <div className="flex items-center justify-center py-6 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  </div>
                }
              >
                <SektorPaketiAlani eposta={ayrinti.eposta} ilkPaket={ilkPaket} onDegisti={() => void ayrintiTazele()} />
              </Suspense>
              <ul className="space-y-3">
                {ayrinti.moduller.map((m) => {
                  const Ikon = modulIkonu(m.ikon);
                  const ad = t(m.ad_anahtari);
                  const mesgul = calisan === m.anahtar;
                  const degistir = () =>
                    islem(
                      m.anahtar,
                      () => modulAyarla(ayrinti.eposta, m.anahtar, { acik: !m.acik }),
                      !m.acik ? t('modul.yonetim.acildi', { ad }) : t('modul.yonetim.kapandi', { ad })
                    );
                  return (
                    <li
                      key={m.anahtar}
                      className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                      data-testid={`musteri-modul-${m.anahtar}`}
                      data-acik={m.acik ? 'evet' : 'hayir'}
                    >
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5">
                          <Ikon className="h-4 w-4 text-purple-300" aria-hidden="true" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{ad}</span>
                            <KaynakRozeti kaynak={m.kaynak} />
                            {m.durum !== 'yayinda' ? <DurumRozeti durum={m.durum} /> : null}
                          </div>
                          {m.bagimliliklar.length > 0 ? (
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              {t('modul.yonetim.bagimli', { moduller: m.bagimliliklar.map(adi).join(', ') })}
                            </p>
                          ) : null}
                        </div>
                        {m.elle !== null && !m.cekirdek ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={mesgul}
                            onClick={() =>
                              islem(
                                m.anahtar,
                                () => modulVarsayilanaDon(ayrinti.eposta, m.anahtar),
                                t('modul.yonetim.varsayilanaDondu', { ad })
                              )
                            }
                            className="gap-1 text-xs text-muted-foreground hover:text-foreground"
                            data-testid={`varsayilana-don-${m.anahtar}`}
                          >
                            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                            {t('modul.yonetim.varsayilanaDon')}
                          </Button>
                        ) : null}
                        {m.cekirdek ? (
                          <span
                            className="inline-flex items-center gap-1 text-xs text-muted-foreground"
                            title={t('modul.yonetim.cekirdekKilitli')}
                          >
                            <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                          </span>
                        ) : null}
                        <button
                          type="button"
                          role="switch"
                          aria-checked={m.acik}
                          aria-label={ad}
                          disabled={m.cekirdek || mesgul}
                          onClick={degistir}
                          data-testid={`anahtar-${m.anahtar}`}
                          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                            m.acik ? 'border-purple-400/60 bg-purple-500/60' : 'border-white/15 bg-white/10'
                          }`}
                        >
                          <span
                            className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                              m.acik ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                          {mesgul ? <Loader2 className="absolute -right-6 h-4 w-4 animate-spin text-muted-foreground" /> : null}
                        </button>
                      </div>
                      {m.engelleyen.length > 0 ? (
                        <p className="mt-2 flex items-center gap-1.5 text-xs text-amber-300">
                          <TriangleAlert className="h-3.5 w-3.5" aria-hidden="true" />
                          {t('modul.yonetim.engellendi', { moduller: m.engelleyen.map(adi).join(', ') })}
                        </p>
                      ) : null}
                      {m.anahtar === 'marka_temasi' ? (
                        <div className="mt-3">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => setMarkaAcik((x) => !x)}
                            aria-expanded={markaAcik}
                            className="gap-1.5 !bg-transparent border-white/20"
                            data-testid="marka-duzenle-ac"
                          >
                            {markaAcik ? t('modul.yonetim.markaKapat') : t('modul.yonetim.markaDuzenle')}
                          </Button>
                          {markaAcik ? (
                            <div className="mt-3">
                              <Suspense
                                fallback={
                                  <div className="flex items-center justify-center py-6 text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                                  </div>
                                }
                              >
                                <MarkaAyari key={ayrinti.eposta} eposta={ayrinti.eposta} />
                              </Suspense>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {m.ayar_alanlari.length > 0 ? (
                        <AyarFormu
                          modul={m}
                          calisiyor={mesgul}
                          onKaydet={(ayarlar) =>
                            islem(
                              m.anahtar,
                              () => modulAyarla(ayrinti.eposta, m.anahtar, { ayarlar }),
                              t('modul.yonetim.ayarKaydedildi', { ad })
                            )
                          }
                        />
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
