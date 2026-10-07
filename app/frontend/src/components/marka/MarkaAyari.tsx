import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from 'react';
import { CheckCircle2, ImageUp, Loader2, Palette, RotateCcw, Save, Trash2, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  KOSE_DEGERLERI,
  YAZI_YIGINLARI,
  ZEMIN_RENKLERI,
  markaLogoAdresi,
  type MarkaKose,
  type MarkaYaziTipi,
  type MarkaZemin,
} from '@/lib/marka';
import { MarkaUcHatasi, canliDenetim, markaApi, type MarkaGirdisi, type PanelMarka } from '@/lib/markaPanel';

/**
 * Faz 4L — "Marka" bölümü: logo, ana/vurgu rengi, zemin, köşe, yazı tipi + canlı önizleme.
 *
 * İki yerde (yeni üst sekme YOK):
 *  * Müşteri paneli › Profil (modül `marka_temasi` açıkken; etkin hesap) — yazma yalnız hesap
 *    sahibi / hesap yöneticisi (sunucu denetliyor; üye salt okunur görür, kaydetmede 403 metni),
 *  * Yönetici paneli › Sistem › Modüller › müşteri ayrıntısı (`eposta` verilir).
 * Rozet ("mehmetkuru.dev ile hazırlandı") burada yalnız GÖRÜNÜYOR: gizlemek ajansın modül ayarı.
 *
 * Kontrast canlı hesaplanıyor (WCAG 2.1 AA, 4.5:1); ana rengin üstündeki yazı rengi otomatik.
 * Yetersizse uyarı + "öneriyi uygula". Yazı tipleri yalnız sitede yüklü olanlar / sistem yığınları.
 */

const ZEMINLER: MarkaZemin[] = ['acik', 'koyu'];
const KOSELER: MarkaKose[] = ['keskin', 'yumusak', 'yuvarlak'];
const YAZI_TIPLERI: MarkaYaziTipi[] = ['jakarta', 'sistem_sans', 'sistem_serif', 'mono'];
const RENK = /^#[0-9a-f]{6}$/i;
const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

type Form = Required<MarkaGirdisi>;

function formdan(m: PanelMarka): Form {
  return { ad: m.ad, ana_renk: m.ana_renk, vurgu_rengi: m.vurgu_rengi, zemin: m.zemin, kose: m.kose, yazi_tipi: m.yazi_tipi };
}

function Secenekler<T extends string>({
  ad,
  degerler,
  secili,
  etiket,
  onSec,
}: {
  ad: string;
  degerler: T[];
  secili: T;
  etiket: (d: T) => string;
  onSec: (d: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={ad}>
      {degerler.map((d) => (
        <button
          key={d}
          type="button"
          role="radio"
          aria-checked={secili === d}
          onClick={() => onSec(d)}
          className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
            secili === d ? 'border-purple-400/60 bg-purple-500/20 text-foreground' : 'border-white/10 bg-white/5 text-muted-foreground hover:text-foreground'
          }`}
          data-testid={`marka-${ad}-${d}`}
        >
          {etiket(d)}
        </button>
      ))}
    </div>
  );
}

function KontrastSatiri({
  testid,
  oran,
  yeterli,
  oneri,
  onUygula,
}: {
  testid: string;
  oran: number;
  yeterli: boolean;
  oneri: string | null;
  onUygula: (renk: string) => void;
}) {
  const { t } = useTranslation();
  if (!oran) return null;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs" data-testid={testid} data-yeterli={yeterli ? '1' : '0'}>
      {yeterli ? (
        <span className="inline-flex items-center gap-1 text-emerald-300">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          {t('markaTemasi.kontrast.yeterli', { oran: oran.toFixed(2) })}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-amber-300" role="status">
          <TriangleAlert className="h-3.5 w-3.5" aria-hidden="true" />
          {t('markaTemasi.kontrast.yetersiz', { oran: oran.toFixed(2), esik: '4.5' })}
        </span>
      )}
      {!yeterli && oneri && (
        <button
          type="button"
          onClick={() => onUygula(oneri)}
          className="inline-flex items-center gap-1.5 rounded-md border border-white/15 bg-white/5 px-2 py-0.5 hover:bg-white/10"
          data-testid={`${testid}-oneri`}
        >
          <span className="h-3 w-3 rounded-sm border border-white/30" style={{ background: oneri }} aria-hidden="true" />
          {t('markaTemasi.kontrast.uygula', { renk: oneri })}
        </button>
      )}
    </div>
  );
}

export default function MarkaAyari({ eposta }: { eposta?: string }) {
  const { t } = useTranslation();
  const api = useMemo(() => markaApi(eposta), [eposta]);
  const [marka, setMarka] = useState<PanelMarka | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [onizlemeZemin, setOnizlemeZemin] = useState<MarkaZemin | null>(null);
  const [mesgul, setMesgul] = useState<'' | 'kaydet' | 'logo' | 'sifirla'>('');
  const [hata, setHata] = useState<string | null>(null);
  const dosyaRef = useRef<HTMLInputElement>(null);

  const hataMetni = useCallback(
    (h: unknown) => {
      const kod = h instanceof MarkaUcHatasi ? h.kod : 'genel';
      return t(`markaTemasi.hata.${kod}`, { defaultValue: t('markaTemasi.hata.genel') });
    },
    [t]
  );

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const m = await api.getir();
      setMarka(m);
      setForm(formdan(m));
    } catch (h) {
      setHata(hataMetni(h));
    }
  }, [api, hataMetni]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const zeminRengi = form ? ZEMIN_RENKLERI[form.zemin].zemin : ZEMIN_RENKLERI.acik.zemin;
  const denetim = useMemo(
    () => (form ? canliDenetim(form.ana_renk, form.vurgu_rengi, zeminRengi) : null),
    [form, zeminRengi]
  );

  if (hata && !marka) {
    return (
      <section className="cam-kart max-w-4xl rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-amber-300" data-testid="marka-ayari">
        {hata}
      </section>
    );
  }
  if (!marka || !form || !denetim) {
    return (
      <div className="flex max-w-4xl items-center justify-center py-10 text-muted-foreground" data-testid="marka-ayari-yukleniyor">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  const degisti = JSON.stringify(form) !== JSON.stringify(formdan(marka));
  const gecerli = RENK.test(form.ana_renk) && RENK.test(form.vurgu_rengi);
  const ayarla = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const kaydet = async (e: FormEvent) => {
    e.preventDefault();
    if (!gecerli) {
      toast.error(t('markaTemasi.hata.renk_gecersiz'));
      return;
    }
    setMesgul('kaydet');
    try {
      const m = await api.kaydet({ ...form, ana_renk: form.ana_renk.toLowerCase(), vurgu_rengi: form.vurgu_rengi.toLowerCase() });
      setMarka(m);
      setForm(formdan(m));
      toast.success(t('markaTemasi.kaydedildi'));
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setMesgul('');
    }
  };

  const logoSec = async (dosya: File | undefined) => {
    if (!dosya) return;
    setMesgul('logo');
    try {
      const m = await api.logoYukle(dosya);
      setMarka(m);
      toast.success(t('markaTemasi.logoYuklendi'));
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setMesgul('');
      if (dosyaRef.current) dosyaRef.current.value = '';
    }
  };

  const logoKaldir = async () => {
    setMesgul('logo');
    try {
      setMarka(await api.logoKaldir());
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setMesgul('');
    }
  };

  const sifirla = async () => {
    if (!window.confirm(t('markaTemasi.sifirlaOnay'))) return;
    setMesgul('sifirla');
    try {
      const m = await api.sifirla();
      setMarka(m);
      setForm(formdan(m));
      toast.success(t('markaTemasi.sifirlandi'));
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setMesgul('');
    }
  };

  // Canlı önizleme: seçili zemin (ya da önizlemede değiştirilen) + kaydedilmemiş renkler.
  const oz = onizlemeZemin || form.zemin;
  const z = ZEMIN_RENKLERI[oz];
  const ana = RENK.test(form.ana_renk) ? form.ana_renk : marka.ana_renk;
  const vurgu = RENK.test(form.vurgu_rengi) ? form.vurgu_rengi : marka.vurgu_rengi;
  const vurguZeminde = canliDenetim(ana, vurgu, z.zemin);
  const [kartKose, dugmeKose] = KOSE_DEGERLERI[form.kose];
  const onizlemeStili = {
    background: z.zemin,
    color: z.metin,
    fontFamily: YAZI_YIGINLARI[form.yazi_tipi],
    borderRadius: kartKose,
  } as CSSProperties;
  const logo = markaLogoAdresi(marka.logo);

  const renkAlani = (alan: 'ana_renk' | 'vurgu_rengi', etiket: string, kontrastTestId: string, satir: { oran: number; yeterli: boolean; oneri: string | null }) => (
    <div>
      <label className="mb-1.5 block text-xs uppercase tracking-widest text-muted-foreground" htmlFor={`marka-${alan}`}>
        {etiket}
      </label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={RENK.test(form[alan]) ? form[alan] : '#000000'}
          onChange={(e) => ayarla(alan, e.target.value)}
          className="h-10 w-12 cursor-pointer rounded-md border border-white/10 bg-transparent p-1"
          aria-label={etiket}
        />
        <Input
          id={`marka-${alan}`}
          value={form[alan]}
          onChange={(e) => ayarla(alan, e.target.value.trim())}
          maxLength={7}
          spellCheck={false}
          className="h-10 w-32 bg-white/5 border-white/10 font-mono"
          aria-invalid={!RENK.test(form[alan])}
          data-testid={`marka-${alan === 'ana_renk' ? 'ana' : 'vurgu'}-renk`}
        />
      </div>
      <KontrastSatiri testid={kontrastTestId} {...satir} onUygula={(r) => ayarla(alan, r)} />
    </div>
  );

  return (
    <section className="cam-kart max-w-4xl rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-testid="marka-ayari">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Palette className="h-5 w-5 text-purple-300" aria-hidden="true" />
            {t('markaTemasi.baslik')}
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('markaTemasi.aciklama')}</p>
        </div>
        {!marka.modul_acik && (
          <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200" data-testid="marka-modul-kapali">
            {t('markaTemasi.modulKapali')}
          </span>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <form onSubmit={kaydet} className="space-y-5">
          <div>
            <label className="mb-1.5 block text-xs uppercase tracking-widest text-muted-foreground" htmlFor="marka-ad">
              {t('markaTemasi.alan.ad')}
            </label>
            <Input
              id="marka-ad"
              value={form.ad}
              onChange={(e) => ayarla('ad', e.target.value)}
              maxLength={80}
              className="h-10 bg-white/5 border-white/10"
              data-testid="marka-ad"
            />
            <p className="mt-1 text-xs text-muted-foreground">{t('markaTemasi.alan.adIpucu')}</p>
          </div>

          <div>
            <p className="mb-1.5 text-xs uppercase tracking-widest text-muted-foreground">{t('markaTemasi.alan.logo')}</p>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-14 min-w-[3.5rem] max-w-[11rem] items-center justify-center rounded-lg border border-white/10 bg-white p-1.5">
                {logo ? (
                  <img src={logo} alt={form.ad || t('markaTemasi.alan.logo')} className="max-h-11 w-auto object-contain" data-testid="marka-logo-onizleme" />
                ) : (
                  <ImageUp className="h-5 w-5 text-zinc-400" aria-hidden="true" />
                )}
              </div>
              <input
                ref={dosyaRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="sr-only"
                id="marka-logo-dosya"
                onChange={(e) => void logoSec(e.target.files?.[0])}
                data-testid="marka-logo-dosya"
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={mesgul !== ''}
                onClick={() => dosyaRef.current?.click()}
                className="gap-1.5 !bg-transparent border-white/20"
              >
                {mesgul === 'logo' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <ImageUp className="h-3.5 w-3.5" aria-hidden="true" />}
                {logo ? t('markaTemasi.logoDegistir') : t('markaTemasi.logoYukle')}
              </Button>
              {logo && (
                <Button type="button" size="sm" variant="ghost" disabled={mesgul !== ''} onClick={() => void logoKaldir()} className="gap-1.5 text-muted-foreground" data-testid="marka-logo-kaldir">
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('markaTemasi.logoKaldir')}
                </Button>
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t('markaTemasi.logoNot')}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {renkAlani('ana_renk', t('markaTemasi.alan.ana'), 'marka-kontrast-ana', denetim.ana)}
            {renkAlani('vurgu_rengi', t('markaTemasi.alan.vurgu'), 'marka-kontrast-vurgu', denetim.vurgu)}
          </div>
          <p className="-mt-2 text-xs text-muted-foreground">
            {t('markaTemasi.kontrast.yaziRengi', { renk: denetim.ana.yazi === '#ffffff' ? t('markaTemasi.kontrast.beyaz') : t('markaTemasi.kontrast.koyu') })}
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1.5 text-xs uppercase tracking-widest text-muted-foreground">{t('markaTemasi.alan.zemin')}</p>
              <Secenekler ad="zemin" degerler={ZEMINLER} secili={form.zemin} etiket={(d) => t(`markaTemasi.zemin.${d}`)} onSec={(d) => { ayarla('zemin', d); setOnizlemeZemin(null); }} />
            </div>
            <div>
              <p className="mb-1.5 text-xs uppercase tracking-widest text-muted-foreground">{t('markaTemasi.alan.kose')}</p>
              <Secenekler ad="kose" degerler={KOSELER} secili={form.kose} etiket={(d) => t(`markaTemasi.kose.${d}`)} onSec={(d) => ayarla('kose', d)} />
            </div>
          </div>

          <div className="max-w-xs">
            <label className="mb-1.5 block text-xs uppercase tracking-widest text-muted-foreground" htmlFor="marka-yazi-tipi">
              {t('markaTemasi.alan.yaziTipi')}
            </label>
            <select id="marka-yazi-tipi" value={form.yazi_tipi} onChange={(e) => ayarla('yazi_tipi', e.target.value as MarkaYaziTipi)} className={SECIM} data-testid="marka-yazi-tipi">
              {YAZI_TIPLERI.map((y) => (
                <option key={y} value={y}>
                  {t(`markaTemasi.yaziTipi.${y}`)}
                </option>
              ))}
            </select>
          </div>

          <p className="text-xs text-muted-foreground" data-testid="marka-rozet-durum" data-gizli={marka.rozet_gizle ? '1' : '0'}>
            {marka.rozet_gizle ? t('markaTemasi.rozet.gizli') : t('markaTemasi.rozet.gorunur')} {t(eposta ? 'markaTemasi.rozet.yoneticiNot' : 'markaTemasi.rozet.yalnizAjans')}
          </p>
          <p className="text-xs text-muted-foreground">{t('markaTemasi.uygulananSayfalar')}</p>

          <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
            <Button
              type="submit"
              disabled={mesgul !== '' || !degisti || !gecerli}
              className="h-10 gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0"
              data-testid="marka-kaydet"
            >
              {mesgul === 'kaydet' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('markaTemasi.kaydet')}
            </Button>
            {marka.kayitli && (
              <Button type="button" variant="ghost" disabled={mesgul !== ''} onClick={() => void sifirla()} className="gap-1.5 text-muted-foreground" data-testid="marka-sifirla">
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                {t('markaTemasi.sifirla')}
              </Button>
            )}
          </div>
        </form>

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('markaTemasi.onizleme.baslik')}</p>
            <Secenekler ad="onizleme" degerler={ZEMINLER} secili={oz} etiket={(d) => t(`markaTemasi.zemin.${d}`)} onSec={(d) => setOnizlemeZemin(d)} />
          </div>
          <div className="overflow-hidden border p-5" style={{ ...onizlemeStili, borderColor: z.cerceve }} data-testid="marka-onizleme" data-zemin={oz}>
            <div className="mb-4 flex min-h-[2.5rem] items-center gap-2">
              {logo ? (
                <img src={logo} alt="" className="max-h-10 w-auto max-w-[10rem] object-contain" />
              ) : (
                <span className="inline-flex h-9 w-9 items-center justify-center text-sm font-bold" style={{ background: ana, color: denetim.ana.yazi, borderRadius: dugmeKose }} aria-hidden="true">
                  {(form.ad || 'M').trim().charAt(0).toUpperCase()}
                </span>
              )}
              {form.ad && <span className="truncate text-sm font-semibold">{form.ad}</span>}
            </div>
            <div className="border p-4" style={{ background: z.yuzey, borderColor: z.cerceve, borderRadius: kartKose }}>
              <p className="text-lg font-bold" data-testid="marka-onizleme-baslik">
                {t('markaTemasi.onizleme.ornekBaslik')}
              </p>
              <p className="mt-1 text-sm" style={{ color: z.soluk }}>
                {t('markaTemasi.onizleme.ornekMetin')}
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <span
                  className="inline-flex items-center px-4 py-2 text-sm font-semibold"
                  style={{ background: ana, color: denetim.ana.yazi, borderRadius: dugmeKose }}
                  data-testid="marka-onizleme-dugme"
                >
                  {t('markaTemasi.onizleme.dugme')}
                </span>
                <span className="text-sm font-medium underline underline-offset-2" style={{ color: vurgu }} data-yeterli={vurguZeminde.vurgu.yeterli ? '1' : '0'}>
                  {t('markaTemasi.onizleme.baglanti')}
                </span>
              </div>
            </div>
            {!marka.rozet_gizle && (
              <p className="mt-4 text-center text-[11px]" style={{ color: z.soluk }}>
                mehmetkuru.dev
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
