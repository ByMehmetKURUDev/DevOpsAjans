import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  Clock,
  Copy,
  Download,
  ExternalLink,
  FileSignature,
  Loader2,
  MapPin,
  Navigation,
  Pause,
  Pencil,
  Phone,
  Play,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  Truck,
  WifiOff,
  X,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  blobIndir,
  gorselAdresi,
  haritaAdresi,
  hataMetni,
  paraYaz,
  SahaHatasi,
  tarihSaat,
  taslakOku,
  taslakSil,
  taslakYaz,
  tekSeferlikKonum,
  yolTarifi,
  type Durum,
  type Fotograf,
  type IsAyrintisi as Ayrinti,
  type Madde,
  type Malzeme,
  type Meta,
  type Riza,
  type SahaApi,
  type StokUrunu,
} from '@/lib/sahaServisi';
import { Alan, BIRIM_SECENEKLERI, DurumRozeti, GIRDI, KART, kopyala, METIN_ALANI, OncelikRozeti, Rozet, SECIM, Yukleniyor } from './ortak';

const ImzaAlani = lazy(() => import('./ImzaAlani'));
const IsFormu = lazy(() => import('./IsFormu'));

type Yanit = string | number | boolean;

/**
 * Faz 6S — iş emri ayrıntısı. Teknisyen ekranı (mobil öncelikli, 360–390 px; büyük dokunma
 * hedefleri) ve yönetim görünümü aynı bileşen. Teknisyen: adres → haritada aç / yol tarifi,
 * müşteriyi ara, yolda / başla / bitir (başla ve bitirde rızaya bağlı tek seferlik konum),
 * kontrol listesi, önce/sonra fotoğraf, malzeme, not, yerinde imza, servis formu PDF'i.
 * Zayıf bağlantı: kontrol listesi ve notlar önce tarayıcıya (taslak) yazılır, bağlantı gelince gider.
 */
export default function IsAyrintisi({
  api,
  meta,
  isId,
  riza,
  onGeri,
  onDegisti,
}: {
  api: SahaApi;
  meta: Meta;
  isId: number;
  riza: Riza | null;
  onGeri: () => void;
  onDegisti?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [is, setIs] = useState<Ayrinti | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState<string | null>(null);
  const [eksikler, setEksikler] = useState<string[]>([]);
  const [yanitlar, setYanitlar] = useState<Record<string, Yanit>>({});
  const [not, setNot] = useState('');
  const [iscilik, setIscilik] = useState('');
  const [takip, setTakip] = useState(false);
  const [bekliyor, setBekliyor] = useState(false);
  const [duzenle, setDuzenle] = useState(false);
  const zamanlayici = useRef<number | null>(null);
  const saltOkunur = meta.salt_okunur;
  const yonetim = meta.yonetim && !saltOkunur;
  const hesap = meta.hesap;
  const listeRef = useRef<HTMLElement | null>(null);

  const yukle = useCallback(async () => {
    try {
      const d = await api.is(isId);
      setIs(d);
      const taslak = taslakOku(hesap, isId);
      const sunucu: Record<string, Yanit> = { ...d.kontrol_yanitlari };
      setYanitlar(taslak?.bekliyor && taslak.yanitlar ? { ...sunucu, ...(taslak.yanitlar as Record<string, Yanit>) } : sunucu);
      setNot(taslak?.bekliyor && taslak.not !== undefined ? taslak.not : d.teknisyen_notu || '');
      setIscilik(
        taslak?.bekliyor && taslak.iscilik_dk !== undefined ? String(taslak.iscilik_dk ?? '') : d.iscilik_dk != null ? String(d.iscilik_dk) : ''
      );
      setTakip(taslak?.bekliyor && taslak.takip_gerekli !== undefined ? !!taslak.takip_gerekli : d.takip_gerekli);
      setBekliyor(!!taslak?.bekliyor);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, hesap, isId, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kapali = !is || is.durum === 'tamamlandi' || is.durum === 'iptal' || saltOkunur;

  // ------------------------------------------------------------------ taslak gönderimi
  const gonder = useCallback(async () => {
    const taslak = taslakOku(hesap, isId);
    if (!taslak?.bekliyor) return;
    try {
      if (taslak.yanitlar && Object.keys(taslak.yanitlar).length) await api.kontrol(isId, taslak.yanitlar);
      await api.saha(isId, {
        teknisyen_notu: taslak.not ?? '',
        iscilik_dk: taslak.iscilik_dk ?? null,
        takip_gerekli: !!taslak.takip_gerekli,
      });
      taslakSil(hesap, isId);
      setBekliyor(false);
      setEksikler([]);
    } catch (e) {
      if (e instanceof SahaHatasi && e.durum === 0) {
        setBekliyor(true);
        return;
      }
      taslakSil(hesap, isId);
      setBekliyor(false);
      toast.error(hataMetni(t, e));
    }
  }, [api, hesap, isId, t]);

  useEffect(() => {
    const cevrimici = () => void gonder();
    window.addEventListener('online', cevrimici);
    return () => window.removeEventListener('online', cevrimici);
  }, [gonder]);

  useEffect(() => {
    if (is && taslakOku(hesap, isId)?.bekliyor) void gonder();
    // Yalnız ilk yüklemede.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [is?.id]);

  const kaydetPlanla = (degisim: { yanitlar?: Record<string, Yanit>; not?: string; iscilik?: string; takip?: boolean }) => {
    const y = degisim.yanitlar ?? yanitlar;
    const tas = {
      yanitlar: y,
      not: degisim.not ?? not,
      iscilik_dk: (degisim.iscilik ?? iscilik).trim() === '' ? null : Number((degisim.iscilik ?? iscilik).replace(',', '.')),
      takip_gerekli: degisim.takip ?? takip,
      bekliyor: true,
    };
    taslakYaz(hesap, isId, tas);
    setBekliyor(true);
    if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    zamanlayici.current = window.setTimeout(() => void gonder(), 700);
  };

  useEffect(
    () => () => {
      if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    },
    []
  );

  const yanitDegis = (m: Madde, deger: Yanit | null) => {
    const yeni = { ...yanitlar };
    if (deger === null || deger === '') delete yeni[m.id];
    else yeni[m.id] = deger;
    // Silinen yanıt sunucuda da boşalsın: null gönder.
    setYanitlar(yeni);
    kaydetPlanla({ yanitlar: deger === null || deger === '' ? { ...yeni, [m.id]: null as unknown as Yanit } : yeni });
    setEksikler((e) => e.filter((x) => x !== m.id));
  };

  // ------------------------------------------------------------------ durum
  const gecisler = useMemo(() => {
    if (!is) return [] as Durum[];
    const tum = meta.gecisler[is.durum] || [];
    if (yonetim) return tum;
    const izinli = new Set(meta.teknisyen_gecisleri.map(([a, b]) => `${a}>${b}`));
    return tum.filter((d) => izinli.has(`${is.durum}>${d}`));
  }, [is, meta, yonetim]);

  const durumDegistir = async (yeni: Durum) => {
    if (!is) return;
    let neden: string | undefined;
    if (yeni === 'ertelendi' || yeni === 'iptal') {
      const girdi = window.prompt(t(`sahaServisi.ayrinti.neden.${yeni}`)) ?? null;
      if (girdi === null) return;
      neden = girdi.trim() || undefined;
    }
    // Önce bekleyen taslak gitsin (bitirirken zorunlu maddeler sunucuda olsun).
    await gonder();
    let konum: Awaited<ReturnType<typeof tekSeferlikKonum>> = null;
    const konumlu = (yeni === 'iste' || yeni === 'tamamlandi') && !!riza?.gecerli && is.benim_isim;
    setMesgul(yeni);
    try {
      if (konumlu) {
        toast.message(t('sahaServisi.ayrinti.konumAliniyor'));
        konum = await tekSeferlikKonum();
      }
      const d = await api.durum(is.id, { durum: yeni, ...(neden ? { neden } : {}), ...(konum ? { konum } : {}) });
      setIs(d);
      setEksikler([]);
      if (konumlu) {
        if (d.konum_kaydedildi) toast.success(t('sahaServisi.ayrinti.konumEklendi'));
        else toast.message(t('sahaServisi.ayrinti.konumYok'));
      }
      toast.success(t(`sahaServisi.ayrinti.gecti.${yeni}`));
      onDegisti?.();
    } catch (e) {
      if (e instanceof SahaHatasi && e.kod === 'zorunlu_madde_eksik') {
        setEksikler(((e.ek.maddeler as string[]) || []).map(String));
        listeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  /** Faz 6Q — tamamlanmış işi yeniden aç (yönetim); stoktan düşülen malzemeler geri eklenir. */
  const yenidenAc = async () => {
    if (!is) return;
    const girdi = window.prompt(t('sahaServisi.ayrinti.yenidenAcNeden'));
    if (girdi === null) return;
    setMesgul('yeniden');
    try {
      setIs(await api.yenidenAc(is.id, girdi.trim() || undefined));
      toast.success(t('sahaServisi.ayrinti.yenidenAcildi'));
      onDegisti?.();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  // ------------------------------------------------------------------ fotoğraf
  const fotoYukle = async (dosyalar: FileList | null, tur: Fotograf['tur'], madde?: string) => {
    if (!is || !dosyalar?.length) return;
    setMesgul(`foto-${tur}-${madde || ''}`);
    try {
      const eklenen: Fotograf[] = [];
      for (const dosya of Array.from(dosyalar)) {
        eklenen.push(await api.fotoYukle(is.id, dosya, tur, madde));
      }
      setIs((x) => (x ? { ...x, fotograflar: [...x.fotograflar, ...eklenen] } : x));
      if (madde) setEksikler((e) => e.filter((x) => x !== madde));
      toast.success(t('sahaServisi.foto.eklendi', { sayi: eklenen.length }));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const fotoSil = async (f: Fotograf) => {
    if (!is || !window.confirm(t('sahaServisi.foto.silOnay'))) return;
    try {
      await api.fotoSil(is.id, f.id);
      setIs((x) => (x ? { ...x, fotograflar: x.fotograflar.filter((y) => y.id !== f.id) } : x));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  // ------------------------------------------------------------------ PDF
  const pdfIndir = async () => {
    if (!is) return;
    setMesgul('pdf');
    try {
      blobIndir(await api.pdf(is.id), `servis-formu-${is.no}.pdf`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  if (hata) {
    return (
      <div className={`${KART} p-6`}>
        <Button size="sm" variant="ghost" className="mb-3 gap-1" onClick={onGeri}>
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          {t('sahaServisi.geri')}
        </Button>
        <p className="text-sm text-red-300" role="alert">
          {hata}
        </p>
      </div>
    );
  }
  if (!is) return <Yukleniyor />;

  const adres = is.lokasyon?.tam_adres || is.adres || '';
  const telefon = is.musteri?.telefon;
  const para = meta.ayarlar.para_birimi || 'TRY';
  const onceler = is.fotograflar.filter((f) => f.tur === 'once');
  const sonralar = is.fotograflar.filter((f) => f.tur === 'sonra');
  const fotoDolu = is.fotograflar.length >= is.foto_siniri;

  return (
    <article className="space-y-4" data-testid="saha-is-ayrinti" data-is-id={is.id} data-durum={is.durum}>
      {/* Üst bilgi */}
      <div className={`${KART} p-4`}>
        <div className="flex items-start gap-2">
          <Button size="icon" variant="ghost" className="h-11 w-11 flex-none" onClick={onGeri} aria-label={t('sahaServisi.geri')} data-testid="saha-geri">
            <ArrowLeft className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
          </Button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                {is.no}
              </span>
              <DurumRozeti durum={is.durum} />
              <OncelikRozeti oncelik={is.oncelik} />
              <Rozet>{t(`sahaServisi.tur.${is.tur}`)}</Rozet>
            </div>
            <h2 className="mt-1 text-lg font-semibold leading-snug" data-testid="saha-is-baslik">
              {is.baslik}
            </h2>
            <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
              <Clock className="h-4 w-4 flex-none" aria-hidden="true" />
              {is.plan_bas ? `${tarihSaat(is.plan_bas, dil)} · ${t('sahaServisi.dk', { sayi: is.tahmini_dk })}` : t('sahaServisi.planYok')}
            </p>
          </div>
          {yonetim && (
            <Button size="sm" variant="outline" className="flex-none gap-1 !bg-transparent border-white/20" onClick={() => setDuzenle(true)} data-testid="saha-is-duzenle">
              <Pencil className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline">{t('sahaServisi.duzenle')}</span>
            </Button>
          )}
        </div>
        {is.teknisyenler.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {is.teknisyenler.map((x) => (
              <Rozet key={x.id} renk="border-white/15 bg-white/[0.05] text-white/85">
                <span className="h-2 w-2 rounded-full" style={{ background: x.renk }} aria-hidden="true" />
                {x.ad}
              </Rozet>
            ))}
          </div>
        )}
        {is.aciklama && <p className="mt-3 whitespace-pre-line text-sm text-white/85">{is.aciklama}</p>}
      </div>

      {/* Müşteri ve adres */}
      <section className={`${KART} p-4`} aria-labelledby="saha-musteri-b">
        <h3 id="saha-musteri-b" className="text-sm font-semibold text-muted-foreground">
          {t('sahaServisi.ayrinti.musteri')}
        </h3>
        <p className="mt-1 text-base font-medium">{is.musteri?.ad || is.musteri_ad}</p>
        {is.musteri?.firma && <p className="text-sm text-muted-foreground">{is.musteri.firma}</p>}
        {adres && (
          <p className="mt-2 flex items-start gap-1.5 text-sm text-white/85" data-testid="saha-adres">
            <MapPin className="mt-0.5 h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
            <span>{adres}</span>
          </p>
        )}
        {is.lokasyon?.notlar && <p className="mt-1 text-xs text-amber-200/90">{is.lokasyon.notlar}</p>}
        <div className="mt-3 grid grid-cols-2 gap-2 min-[480px]:grid-cols-3">
          {adres && (
            <a href={haritaAdresi(adres)} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-3 text-sm font-medium hover:bg-white/[0.08]" data-testid="saha-harita">
              <MapPin className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.ayrinti.haritadaAc')}
            </a>
          )}
          {adres && (
            <a href={yolTarifi(adres)} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-3 text-sm font-medium hover:bg-white/[0.08]">
              <Navigation className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.ayrinti.yolTarifi')}
            </a>
          )}
          {telefon && (
            <a href={`tel:${telefon}`} className="col-span-2 inline-flex min-h-[44px] items-center min-[480px]:col-span-1 justify-center gap-1.5 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 text-sm font-medium text-emerald-100 hover:bg-emerald-500/20" data-testid="saha-ara">
              <Phone className="h-4 w-4" aria-hidden="true" />
              {t('sahaServisi.ayrinti.ara')}
            </a>
          )}
        </div>
        {is.cihazlar.length > 0 && (
          <ul className="mt-3 space-y-1 border-t border-white/5 pt-3 text-sm">
            {is.cihazlar.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{c.tur}</span>
                <span className="text-muted-foreground">{[c.marka, c.model].filter(Boolean).join(' ')}</span>
                {c.seri_no && (
                  <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                    {c.seri_no}
                  </span>
                )}
                {c.garantide && <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-200">{t('sahaServisi.cihaz.garantide')}</Rozet>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Durum düğmeleri */}
      {!saltOkunur && gecisler.length > 0 && (
        <section className={`${KART} p-4`} aria-label={t('sahaServisi.ayrinti.durumDegistir')} data-testid="saha-durum-dugmeleri">
          {(is.durum === 'iste' || is.durum === 'yolda' || is.durum === 'planlandi') && is.benim_isim && !riza?.gecerli && (
            <p className="mb-2 text-xs text-muted-foreground">{t('sahaServisi.ayrinti.rizasizBilgi')}</p>
          )}
          <div className="grid gap-2 min-[400px]:grid-cols-2">
            {gecisler.includes('yolda') && (
              <AnaDugme ikon={Truck} etiket={t('sahaServisi.eylem.yolda')} mesgul={mesgul === 'yolda'} onClick={() => void durumDegistir('yolda')} testid="saha-yolda" />
            )}
            {gecisler.includes('iste') && (
              <AnaDugme ikon={Play} etiket={t('sahaServisi.eylem.basla')} mesgul={mesgul === 'iste'} onClick={() => void durumDegistir('iste')} testid="saha-basla" vurgu />
            )}
            {gecisler.includes('tamamlandi') && (
              <AnaDugme ikon={CheckCircle2} etiket={t('sahaServisi.eylem.bitir')} mesgul={mesgul === 'tamamlandi'} onClick={() => void durumDegistir('tamamlandi')} testid="saha-bitir" vurgu />
            )}
            {gecisler.includes('ertelendi') && (
              <AnaDugme ikon={Pause} etiket={t('sahaServisi.eylem.ertele')} mesgul={mesgul === 'ertelendi'} onClick={() => void durumDegistir('ertelendi')} testid="saha-ertele" />
            )}
          </div>
          {yonetim && gecisler.some((d) => ['yeni', 'planlandi', 'iptal'].includes(d)) && (
            <div className="mt-3 flex flex-wrap gap-2 border-t border-white/5 pt-3">
              {gecisler
                .filter((d) => ['yeni', 'planlandi', 'iptal'].includes(d))
                .map((d) => (
                  <Button key={d} size="sm" variant="outline" className="min-h-[40px] !bg-transparent border-white/20" disabled={!!mesgul} onClick={() => void durumDegistir(d)} data-testid={`saha-durum-${d}`}>
                    {t(`sahaServisi.eylem.${d}`)}
                  </Button>
                ))}
            </div>
          )}
        </section>
      )}

      {yonetim && is.durum === 'tamamlandi' && (
        <section className={`${KART} flex flex-wrap items-center gap-2 p-4`} data-testid="saha-yeniden-ac-bolumu">
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">{t('sahaServisi.ayrinti.yenidenAcBilgi')}</p>
          <Button size="sm" variant="outline" className="min-h-[40px] gap-1 !bg-transparent border-white/20" disabled={!!mesgul} onClick={() => void yenidenAc()} data-testid="saha-yeniden-ac">
            {mesgul === 'yeniden' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RotateCcw className="h-4 w-4" aria-hidden="true" />}
            {t('sahaServisi.ayrinti.yenidenAc')}
          </Button>
        </section>
      )}

      {/* Kontrol listesi */}
      {is.kontrol_listesi.length > 0 && (
        <section ref={listeRef} className={`${KART} p-4`} aria-labelledby="saha-kontrol-b" data-testid="saha-kontrol">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 id="saha-kontrol-b" className="text-base font-semibold">
              {t('sahaServisi.kontrol.baslik')}
            </h3>
            {bekliyor && (
              <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200" testid="saha-taslak-bekliyor">
                <WifiOff className="h-3 w-3" aria-hidden="true" />
                {t('sahaServisi.kontrol.taslak')}
              </Rozet>
            )}
          </div>
          <ol className="space-y-3">
            {is.kontrol_listesi.map((m, i) => {
              const eksik = eksikler.includes(m.id);
              const fotolar = is.fotograflar.filter((f) => f.tur === 'madde' && f.madde_id === m.id);
              return (
                <li key={m.id} className={`rounded-xl border p-3 ${eksik ? 'border-red-400/60 bg-red-500/10' : 'border-white/10 bg-black/20'}`} data-madde={m.id} data-testid="saha-madde">
                  <p className="mb-2 text-sm font-medium">
                    <span className="me-1 text-muted-foreground">{i + 1}.</span>
                    {m.metin}
                    {m.zorunlu && (
                      <span className="ms-1 text-red-300" aria-label={t('sahaServisi.kontrol.zorunlu')}>
                        *
                      </span>
                    )}
                  </p>
                  {m.tur === 'evet_hayir' && (
                    <div className="grid grid-cols-2 gap-2" role="group" aria-label={m.metin}>
                      {[true, false].map((d) => (
                        <button
                          key={String(d)}
                          type="button"
                          disabled={kapali}
                          aria-pressed={yanitlar[m.id] === d}
                          onClick={() => yanitDegis(m, yanitlar[m.id] === d ? null : d)}
                          className={`min-h-[44px] rounded-lg border text-sm font-medium transition-colors ${
                            yanitlar[m.id] === d
                              ? d
                                ? 'border-emerald-400/60 bg-emerald-500/25 text-emerald-50'
                                : 'border-rose-400/60 bg-rose-500/25 text-rose-50'
                              : 'border-white/15 bg-white/[0.04] text-white/80 hover:bg-white/[0.08]'
                          }`}
                          data-testid={`saha-madde-${d ? 'evet' : 'hayir'}`}
                        >
                          {d ? t('sahaServisi.evet') : t('sahaServisi.hayir')}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.tur === 'metin' && (
                    <textarea className={METIN_ALANI} disabled={kapali} value={String(yanitlar[m.id] ?? '')} onChange={(e) => yanitDegis(m, e.target.value)} maxLength={500} data-testid="saha-madde-metin" />
                  )}
                  {(m.tur === 'sayi' || m.tur === 'olcum') && (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        className={`${GIRDI} max-w-[10rem] text-base`}
                        disabled={kapali}
                        value={String(yanitlar[m.id] ?? '')}
                        onChange={(e) => yanitDegis(m, e.target.value.replace(/[^0-9.,-]/g, ''))}
                        dir="ltr"
                        aria-label={m.metin}
                        data-testid="saha-madde-sayi"
                      />
                      {m.birim && <span className="text-sm text-muted-foreground">{m.birim}</span>}
                    </div>
                  )}
                  {m.tur === 'foto' && (
                    <FotoSatiri
                      fotolar={fotolar}
                      onYukle={(d) => void fotoYukle(d, 'madde', m.id)}
                      onSil={(f) => void fotoSil(f)}
                      kapali={kapali || fotoDolu}
                      mesgul={mesgul === `foto-madde-${m.id}`}
                      testid={`saha-foto-madde-${m.id}`}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {/* Fotoğraflar */}
      <section className={`${KART} p-4`} aria-labelledby="saha-foto-b">
        <h3 id="saha-foto-b" className="mb-1 text-base font-semibold">
          {t('sahaServisi.foto.baslik')}
        </h3>
        <p className="mb-3 text-xs text-muted-foreground">{t('sahaServisi.foto.bilgi', { sinir: is.foto_siniri })}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-medium">{t('sahaServisi.foto.once')}</p>
            <FotoSatiri fotolar={onceler} onYukle={(d) => void fotoYukle(d, 'once')} onSil={(f) => void fotoSil(f)} kapali={kapali || fotoDolu} mesgul={mesgul === 'foto-once-'} testid="saha-foto-once" />
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">{t('sahaServisi.foto.sonra')}</p>
            <FotoSatiri fotolar={sonralar} onYukle={(d) => void fotoYukle(d, 'sonra')} onSil={(f) => void fotoSil(f)} kapali={kapali || fotoDolu} mesgul={mesgul === 'foto-sonra-'} testid="saha-foto-sonra" />
          </div>
        </div>
      </section>

      {/* Malzeme */}
      <MalzemeBolumu api={api} is={is} kapali={kapali} para={para} stokAcik={!!meta.stok?.acik} onDegis={(m) => setIs((x) => (x ? { ...x, malzemeler: m } : x))} />

      {/* Not ve işçilik */}
      <section className={`${KART} space-y-3 p-4`} aria-labelledby="saha-not-b">
        <h3 id="saha-not-b" className="text-base font-semibold">
          {t('sahaServisi.not.baslik')}
        </h3>
        <textarea
          className={METIN_ALANI}
          disabled={kapali}
          value={not}
          maxLength={4000}
          placeholder={t('sahaServisi.not.ornek')}
          onChange={(e) => {
            setNot(e.target.value);
            kaydetPlanla({ not: e.target.value });
          }}
          aria-label={t('sahaServisi.not.baslik')}
          data-testid="saha-not"
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Alan etiket={t('sahaServisi.not.iscilik')}>
            <input
              type="text"
              inputMode="numeric"
              className={`${GIRDI} text-base`}
              disabled={kapali}
              value={iscilik}
              onChange={(e) => {
                const v = e.target.value.replace(/[^0-9]/g, '');
                setIscilik(v);
                kaydetPlanla({ iscilik: v });
              }}
              dir="ltr"
            />
          </Alan>
          <div className="flex items-end">
            <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-5 w-5 accent-purple-500"
                disabled={kapali}
                checked={takip}
                onChange={(e) => {
                  setTakip(e.target.checked);
                  kaydetPlanla({ takip: e.target.checked });
                }}
              />
              {t('sahaServisi.not.takip')}
            </label>
          </div>
        </div>
      </section>

      {/* İmza */}
      <ImzaBolumu api={api} is={is} saltOkunur={saltOkunur} onImza={(imza) => setIs((x) => (x ? { ...x, imza, imzali: true } : x))} />

      {/* PDF, müşteri bağlantısı, konum (yönetim) */}
      <section className={`${KART} space-y-3 p-4`}>
        <Button className="min-h-[48px] w-full gap-2 text-base sm:w-auto" onClick={() => void pdfIndir()} disabled={mesgul === 'pdf'} data-testid="saha-pdf">
          {mesgul === 'pdf' ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : <Download className="h-5 w-5" aria-hidden="true" />}
          {t('sahaServisi.ayrinti.pdf')}
        </Button>
        {is.musteri_baglantisi && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">{t('sahaServisi.ayrinti.musteriSayfasi')}</span>
            <a href={is.musteri_baglantisi} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-purple-200 hover:underline" data-testid="saha-musteri-sayfasi">
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              {t('sahaServisi.ac')}
            </a>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-purple-200 hover:underline"
              onClick={async () => toast[(await kopyala(is.musteri_baglantisi || '')) ? 'success' : 'error'](t('sahaServisi.kopyalandi'))}
            >
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              {t('sahaServisi.kopyala')}
            </button>
          </div>
        )}
        {meta.yonetim && (
          <p className="text-xs text-muted-foreground" data-testid="saha-konum-bilgi">
            {is.konum?.basla || is.konum?.bitir
              ? t('sahaServisi.ayrinti.konumVar', { gun: meta.konum_saklama_gun })
              : is.konum_alindi.indirgendi_at
                ? t('sahaServisi.ayrinti.konumIndirgendi')
                : t('sahaServisi.ayrinti.konumAlinmadi')}
            {(['basla', 'bitir'] as const).map((a) =>
              is.konum?.[a] ? (
                <a key={a} className="ms-2 text-purple-200 hover:underline" href={haritaAdresi(`${is.konum[a]!.enlem},${is.konum[a]!.boylam}`)} target="_blank" rel="noopener noreferrer">
                  {t(`sahaServisi.ayrinti.konum_${a}`)}
                </a>
              ) : null
            )}
          </p>
        )}
        {is.memnuniyet && (
          <p className="text-sm" data-testid="saha-memnuniyet">
            {'★'.repeat(is.memnuniyet.puan)}
            <span className="text-muted-foreground">{'★'.repeat(5 - is.memnuniyet.puan)}</span>
            {is.memnuniyet.yorum && <span className="ms-2 text-white/80">“{is.memnuniyet.yorum}”</span>}
          </p>
        )}
      </section>

      {/* Geçmiş */}
      {meta.yonetim && (
        <section className={`${KART} p-4`}>
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{t('sahaServisi.ayrinti.gecmis')}</h3>
          <ol className="space-y-1 text-xs">
            {is.gecmis.map((g, i) => (
              <li key={i} className="flex flex-wrap gap-x-2 text-white/80">
                <span className="text-muted-foreground">{tarihSaat(g.zaman, dil)}</span>
                <span>{t(`sahaServisi.durum.${g.yeni}`)}</span>
                {g.kisi && <span className="text-muted-foreground">· {g.kisi}</span>}
                {g.konum_alindi && <MapPin className="h-3 w-3 text-purple-300" aria-label={t('sahaServisi.ayrinti.konumAlindi')} />}
                {g.neden && <span className="text-amber-200">— {g.neden}</span>}
              </li>
            ))}
          </ol>
        </section>
      )}

      {duzenle && (
        <Suspense fallback={null}>
          <IsFormu
            api={api}
            mevcut={is}
            onKapat={() => setDuzenle(false)}
            onKaydedildi={(d) => {
              setIs(d);
              setDuzenle(false);
              onDegisti?.();
            }}
          />
        </Suspense>
      )}
    </article>
  );
}

function AnaDugme({ ikon: Ikon, etiket, onClick, mesgul, vurgu, testid }: { ikon: typeof Play; etiket: string; onClick: () => void; mesgul: boolean; vurgu?: boolean; testid: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={mesgul}
      className={`inline-flex min-h-[56px] items-center justify-center gap-2 rounded-xl px-4 text-base font-semibold transition-colors disabled:opacity-60 ${
        vurgu ? 'bg-gradient-to-r from-purple-600 to-fuchsia-600 text-white hover:brightness-110' : 'border border-white/15 bg-white/[0.06] text-white hover:bg-white/[0.1]'
      }`}
      data-testid={testid}
    >
      {mesgul ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : <Ikon className="h-5 w-5" aria-hidden="true" />}
      {etiket}
    </button>
  );
}

function FotoSatiri({
  fotolar,
  onYukle,
  onSil,
  kapali,
  mesgul,
  testid,
}: {
  fotolar: Fotograf[];
  onYukle: (d: FileList | null) => void;
  onSil: (f: Fotograf) => void;
  kapali: boolean;
  mesgul: boolean;
  testid: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-start gap-2" data-testid={testid}>
      {fotolar.map((f) => (
        <div key={f.id} className="relative">
          <a href={gorselAdresi(f.url)} target="_blank" rel="noopener noreferrer">
            <img src={gorselAdresi(f.kucuk_url)} alt="" width={72} height={72} loading="lazy" className="h-[72px] w-[72px] rounded-lg border border-white/10 object-cover" data-testid="saha-foto-kucuk" />
          </a>
          {!kapali && (
            <button type="button" onClick={() => onSil(f)} className="absolute -end-1.5 -top-1.5 flex h-7 w-7 items-center justify-center rounded-full bg-black/80 text-white" aria-label={t('sahaServisi.sil')}>
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      ))}
      {!kapali && (
        <label className="flex h-[72px] w-[72px] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-white/25 text-[11px] text-muted-foreground hover:border-purple-400/60 hover:text-white">
          {mesgul ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : <Camera className="h-5 w-5" aria-hidden="true" />}
          {t('sahaServisi.foto.ekle')}
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            multiple
            className="sr-only"
            disabled={mesgul}
            onChange={(e) => {
              onYukle(e.target.files);
              e.target.value = '';
            }}
            data-testid={`${testid}-girdi`}
          />
        </label>
      )}
    </div>
  );
}

function MalzemeBolumu({
  api,
  is,
  kapali,
  para,
  stokAcik,
  onDegis,
}: {
  api: SahaApi;
  is: Ayrinti;
  kapali: boolean;
  para: string;
  /** Faz 6Q: Stok ve POS bağlantısı açık — stok ürünü aranır, iş bitince stoktan düşer. */
  stokAcik: boolean;
  onDegis: (m: Ayrinti['malzemeler']) => void;
}) {
  const { t, i18n } = useTranslation();
  const [katalog, setKatalog] = useState<Malzeme[] | null>(null);
  const [acik, setAcik] = useState(false);
  const [secili, setSecili] = useState('');
  const [miktar, setMiktar] = useState('1');
  const [serbest, setSerbest] = useState({ ad: '', birim: 'adet', fiyat: '' });
  const [mesgul, setMesgul] = useState(false);
  const [stokAra, setStokAra] = useState('');
  const [stokSonuc, setStokSonuc] = useState<StokUrunu[] | null>(null);
  const [stokSecili, setStokSecili] = useState<StokUrunu | null>(null);
  const [stokMiktar, setStokMiktar] = useState('1');

  // Stok ürünü araması (ad / barkod / SKU) — yazdıkça, kısa gecikmeyle.
  useEffect(() => {
    if (!acik || !stokAcik) return;
    const z = window.setTimeout(() => {
      api
        .stokUrunleri(stokAra.trim() || undefined)
        .then((r) => setStokSonuc(r.items))
        .catch(() => setStokSonuc([]));
    }, 250);
    return () => window.clearTimeout(z);
  }, [acik, api, stokAcik, stokAra]);

  const stokEkle = async () => {
    if (!stokSecili) return;
    setMesgul(true);
    try {
      const k = await api.kullanimEkle(is.id, { stok_urun_id: stokSecili.id, miktar: stokMiktar.replace(',', '.') });
      onDegis([...is.malzemeler, k]);
      setStokSecili(null);
      setStokMiktar('1');
      setStokAra('');
      toast.success(t('sahaServisi.malzeme.eklendi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  useEffect(() => {
    if (!acik || katalog) return;
    api
      .malzemeler()
      .then((r) => setKatalog(r.items.filter((m) => m.aktif)))
      .catch(() => setKatalog([]));
  }, [acik, api, katalog]);

  const ekle = async () => {
    setMesgul(true);
    try {
      const g: Record<string, unknown> = { miktar: miktar.replace(',', '.') };
      if (secili && secili !== 'serbest') g.malzeme_id = Number(secili);
      else Object.assign(g, { ad: serbest.ad, birim: serbest.birim, birim_fiyat: serbest.fiyat.replace(',', '.') });
      const k = await api.kullanimEkle(is.id, g);
      onDegis([...is.malzemeler, k]);
      setMiktar('1');
      setSerbest({ ad: '', birim: 'adet', fiyat: '' });
      toast.success(t('sahaServisi.malzeme.eklendi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const sil = async (kid: number) => {
    try {
      await api.kullanimSil(is.id, kid);
      onDegis(is.malzemeler.filter((x) => x.id !== kid));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const toplam = is.malzemeler.reduce((a, x) => a + x.tutar, 0);
  return (
    <section className={`${KART} p-4`} aria-labelledby="saha-malzeme-b" data-testid="saha-malzemeler">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 id="saha-malzeme-b" className="text-base font-semibold">
          {t('sahaServisi.malzeme.kullanilan')}
        </h3>
        {!kapali && (
          <Button size="sm" variant="ghost" className="min-h-[40px] gap-1" onClick={() => setAcik((x) => !x)} data-testid="saha-malzeme-ekle-ac">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('sahaServisi.malzeme.ekle')}
          </Button>
        )}
      </div>
      {is.malzemeler.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('sahaServisi.malzeme.yok')}</p>
      ) : (
        <ul className="divide-y divide-white/5 text-sm">
          {is.malzemeler.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-2 py-2" data-testid="saha-malzeme-satiri-is" data-stok-urun-id={x.stok_urun_id ?? ''}>
              <span className="min-w-0 flex-1">
                <span className="block truncate">{x.ad}</span>
                {x.stok_urun_id ? (
                  <span className={`mt-0.5 inline-block rounded-full border px-1.5 text-[10px] ${x.stoktan_dusuldu ? 'border-emerald-400/40 text-emerald-200' : 'border-sky-400/40 text-sky-200'}`} data-testid="saha-malzeme-stok-rozet">
                    {x.stoktan_dusuldu ? t('sahaServisi.stok.dusuldu') : t('sahaServisi.stok.bitinceDusulur')}
                  </span>
                ) : null}
              </span>
              <span className="text-muted-foreground" dir="ltr">
                {x.miktar} {t(`sahaServisi.birim.${x.birim}`, { defaultValue: x.birim })}
              </span>
              <span className="w-24 text-end tabular-nums">{paraYaz(x.tutar, para, i18n.language)}</span>
              {!kapali && (
                <button type="button" className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/[0.06] hover:text-white" aria-label={t('sahaServisi.sil')} onClick={() => void sil(x.id)}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
          <li className="flex justify-between py-2 font-medium">
            <span>{t('sahaServisi.malzeme.toplam')}</span>
            <span className="tabular-nums">{paraYaz(toplam, para, i18n.language)}</span>
          </li>
        </ul>
      )}
      {acik && !kapali && stokAcik && (
        <div className="mt-3 space-y-2 rounded-xl border border-purple-400/20 bg-purple-500/[0.06] p-3" data-testid="saha-stok-bolumu">
          <p className="text-sm font-medium">{t('sahaServisi.stok.urunEkle')}</p>
          <div className="relative">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <input
              className={`${GIRDI} ps-9 text-base`}
              value={stokAra}
              onChange={(e) => {
                setStokAra(e.target.value);
                setStokSecili(null);
              }}
              placeholder={t('sahaServisi.stok.araIpucu')}
              aria-label={t('sahaServisi.stok.ara')}
              autoComplete="off"
              data-testid="saha-stok-ara"
            />
          </div>
          {stokSecili ? (
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_auto] sm:items-end">
              <p className="text-sm" data-testid="saha-stok-secili">
                <span className="font-medium">{stokSecili.ad}</span>
                <span className="ms-1 text-xs text-muted-foreground">
                  {paraYaz(stokSecili.birim_fiyat, para, i18n.language)} / {t(`sahaServisi.birim.${stokSecili.birim}`, { defaultValue: stokSecili.birim })}
                </span>
              </p>
              <Alan etiket={t('sahaServisi.malzeme.miktar')}>
                <input type="text" inputMode="decimal" className={`${GIRDI} text-base`} value={stokMiktar} onChange={(e) => setStokMiktar(e.target.value)} dir="ltr" data-testid="saha-stok-miktar" />
              </Alan>
              <Button className="min-h-[44px]" onClick={() => void stokEkle()} disabled={mesgul} data-testid="saha-stok-ekle">
                {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
                {t('sahaServisi.ekle')}
              </Button>
            </div>
          ) : (
            <ul className="max-h-56 divide-y divide-white/5 overflow-y-auto" data-testid="saha-stok-sonuclar">
              {(stokSonuc || []).map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    className="flex min-h-[44px] w-full flex-wrap items-center gap-x-2 px-1 py-1.5 text-start text-sm hover:bg-white/[0.05]"
                    onClick={() => setStokSecili(u)}
                    data-testid="saha-stok-urun"
                    data-urun-id={u.id}
                  >
                    <span className="min-w-0 flex-1 truncate font-medium">{u.ad}</span>
                    <span className="font-mono text-[11px] text-muted-foreground" dir="ltr">
                      {u.barkod}
                    </span>
                    {u.stok_takibi && (
                      <span className={`text-xs ${u.kritik ? 'text-amber-300' : 'text-muted-foreground'}`}>
                        {t('sahaServisi.stok.stokta', { miktar: u.stok ?? 0, birim: t(`sahaServisi.birim.${u.birim}`, { defaultValue: u.birim }) })}
                      </span>
                    )}
                  </button>
                </li>
              ))}
              {stokSonuc && !stokSonuc.length && <li className="py-2 text-center text-xs text-muted-foreground">{t('sahaServisi.stok.urunYok')}</li>}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">{t('sahaServisi.stok.bilgi')}</p>
        </div>
      )}
      {acik && !kapali && (
        <div className="mt-3 grid gap-2 rounded-xl border border-white/10 bg-black/20 p-3 sm:grid-cols-[minmax(0,1fr)_7rem_auto] sm:items-end">
          <Alan etiket={t('sahaServisi.malzeme.sec')}>
            <select className={SECIM} value={secili} onChange={(e) => setSecili(e.target.value)} data-testid="saha-malzeme-sec">
              <option value="">{t('sahaServisi.malzeme.secin')}</option>
              {(katalog || []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.ad}
                  {m.stok != null ? ` (${m.stok} ${t(`sahaServisi.birim.${m.birim}`, { defaultValue: m.birim })})` : ''}
                </option>
              ))}
              <option value="serbest">{t('sahaServisi.malzeme.serbest')}</option>
            </select>
          </Alan>
          <Alan etiket={t('sahaServisi.malzeme.miktar')}>
            <input type="text" inputMode="decimal" className={`${GIRDI} text-base`} value={miktar} onChange={(e) => setMiktar(e.target.value)} dir="ltr" data-testid="saha-malzeme-miktar" />
          </Alan>
          <Button className="min-h-[44px]" onClick={() => void ekle()} disabled={mesgul || !secili || (secili === 'serbest' && !serbest.ad.trim())} data-testid="saha-malzeme-ekle">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
            {t('sahaServisi.ekle')}
          </Button>
          {secili === 'serbest' && (
            <div className="grid gap-2 sm:col-span-3 sm:grid-cols-3">
              <Alan etiket={t('sahaServisi.malzeme.ad')}>
                <input className={GIRDI} value={serbest.ad} maxLength={160} onChange={(e) => setSerbest({ ...serbest, ad: e.target.value })} />
              </Alan>
              <Alan etiket={t('sahaServisi.malzeme.birim')}>
                <select className={SECIM} value={serbest.birim} onChange={(e) => setSerbest({ ...serbest, birim: e.target.value })}>
                  {BIRIM_SECENEKLERI.map((b) => (
                    <option key={b} value={b}>
                      {t(`sahaServisi.birim.${b}`)}
                    </option>
                  ))}
                </select>
              </Alan>
              <Alan etiket={t('sahaServisi.malzeme.birimFiyat')}>
                <input type="text" inputMode="decimal" className={GIRDI} value={serbest.fiyat} onChange={(e) => setSerbest({ ...serbest, fiyat: e.target.value })} dir="ltr" />
              </Alan>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ImzaBolumu({ api, is, saltOkunur, onImza }: { api: SahaApi; is: Ayrinti; saltOkunur: boolean; onImza: (i: Ayrinti['imza']) => void }) {
  const { t, i18n } = useTranslation();
  const [png, setPng] = useState<string | null>(null);
  const [ad, setAd] = useState(is.musteri?.ad && is.musteri.ad !== '—' ? is.musteri.ad : '');
  const [mesgul, setMesgul] = useState(false);
  const [yeniden, setYeniden] = useState(false);
  const alinabilir = !saltOkunur && (is.durum === 'iste' || (is.durum === 'tamamlandi' && !is.imza));

  const kaydet = async () => {
    if (!png || !ad.trim()) return;
    setMesgul(true);
    try {
      const r = await api.imza(is.id, ad.trim(), png);
      onImza(r.imza);
      setYeniden(false);
      toast.success(t('sahaServisi.imza.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  if (!alinabilir && !is.imza) return null;
  return (
    <section className={`${KART} p-4`} aria-labelledby="saha-imza-b" data-testid="saha-imza">
      <h3 id="saha-imza-b" className="mb-2 flex items-center gap-2 text-base font-semibold">
        <FileSignature className="h-5 w-5 text-purple-300" aria-hidden="true" />
        {t('sahaServisi.imza.baslik')}
      </h3>
      {is.imza && !yeniden ? (
        <div className="space-y-2">
          <div className="inline-block rounded-xl border border-white/15 bg-white p-2">
            <img src={gorselAdresi(is.imza.url)} alt={t('sahaServisi.imza.alt', { ad: is.imza.ad })} className="h-24 w-auto" data-testid="saha-imza-gorsel" />
          </div>
          <p className="text-sm text-white/85">
            {is.imza.ad} · <span className="text-muted-foreground">{tarihSaat(is.imza.at, i18n.language)}</span>
          </p>
          {is.durum === 'iste' && !saltOkunur && (
            <Button size="sm" variant="ghost" onClick={() => setYeniden(true)}>
              {t('sahaServisi.imza.yeniden')}
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">{t('sahaServisi.imza.bilgi')}</p>
          <Suspense fallback={<Yukleniyor />}>
            <ImzaAlani onDegis={setPng} />
          </Suspense>
          <Alan etiket={t('sahaServisi.imza.ad')}>
            <input className={`${GIRDI} text-base`} value={ad} onChange={(e) => setAd(e.target.value)} maxLength={120} autoComplete="off" data-testid="saha-imza-ad" />
          </Alan>
          <Button className="min-h-[48px] w-full gap-2 sm:w-auto" disabled={!png || !ad.trim() || mesgul} onClick={() => void kaydet()} data-testid="saha-imza-kaydet">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileSignature className="h-4 w-4" aria-hidden="true" />}
            {t('sahaServisi.imza.kaydet')}
          </Button>
        </div>
      )}
    </section>
  );
}
