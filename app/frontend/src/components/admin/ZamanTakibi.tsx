import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  BarChart3,
  CalendarRange,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  Lock,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  Square,
  Timer,
  Trash2,
  Undo2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  PARA_BIRIMLERI,
  ZAMAN_DURUMLARI,
  ZamanHatasi,
  bugunYerel,
  cizelgeGetir,
  csvIndir,
  faturalanabilirGetir,
  faturayaAktar,
  gunAdi,
  gunEkle,
  isYukuGetir,
  kayitEkle,
  kayitGuncelle,
  kayitSil,
  kayitlariGetir,
  onayIslemi,
  onayiGeriAl,
  paraGoster,
  projeAyariGetir,
  projeAyariYaz,
  saniyeGoster,
  sayacBaslat,
  sayacDurdur,
  sayacGetir,
  secenekleriGetir,
  sureCoz,
  sureGoster,
  tarihGoster,
  zamanAyarlari,
  zamanAyarlariYaz,
  type AktarimSonucu,
  type Cizelge,
  type Faturalanabilir,
  type Gruplama,
  type IsYuku,
  type KayitGirdisi,
  type ProjeAyari,
  type Secenekler,
  type ZamanDurumu,
  type ZamanKaydi,
  type ZamanTuru,
} from '@/lib/zamanTakibi';

const SECIM =
  'h-9 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';
const KART = 'cam-kart min-w-0 rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6';
const ETIKET = 'mb-1 block text-xs text-muted-foreground';

const DURUM_RENGI: Record<ZamanDurumu, string> = {
  taslak: 'bg-white/10 text-foreground/80',
  onaylandi: 'bg-emerald-500/15 text-emerald-300',
  reddedildi: 'bg-rose-500/15 text-rose-300',
  faturalandi: 'bg-sky-500/15 text-sky-300',
};

type Alt = 'kayitlar' | 'cizelge' | 'isYuku' | 'onay' | 'fatura' | 'ayarlar';

interface Props {
  /** Yönetici paneli (true) ya da personelin kendi bölümü (false). */
  yonetici?: boolean;
  /** Faturaya aktarımdan sonra (yönetici paneli fatura listesini yenilesin). */
  onFaturaOlustu?: () => void;
}

function useHata() {
  const { t } = useTranslation();
  return useCallback(
    (h: unknown) => {
      const kod = h instanceof ZamanHatasi ? h.kod : 'genel';
      toast.error(t(`zamanTakibi.hata.${kod}`, { defaultValue: t('zamanTakibi.hata.genel') }));
    },
    [t],
  );
}

/**
 * Yönetici › Zaman (Faz 3Z): sayaç çubuğu + kayıtlar, haftalık çizelge, iş yükü,
 * onay kuyruğu, faturaya aktarım ve ücret ayarları. `yonetici=false` ile aynı
 * bileşen personelin kendi bölümü olur (yalnız sayaç, kendi kayıtları, çizelge).
 */
export default function ZamanTakibi({ yonetici = true, onFaturaOlustu }: Props) {
  const { t } = useTranslation();
  const hata = useHata();
  const [secenekler, setSecenekler] = useState<Secenekler | null>(null);
  const [alt, setAlt] = useState<Alt>('kayitlar');
  // Sayaç/kayıt değişince listeler yenilensin.
  const [surum, setSurum] = useState(0);
  const yenile = useCallback(() => setSurum((s) => s + 1), []);

  useEffect(() => {
    secenekleriGetir()
      .then(setSecenekler)
      .catch((h) => {
        hata(h);
        setSecenekler({ projeler: [], gorevler: [], uzun_sayac_dk: 720, en_cok_sure_dk: 1440 });
      });
  }, [hata]);

  const altlar: [Alt, string, typeof Timer][] = [
    ['kayitlar', t('zamanTakibi.alt.kayitlar'), Timer],
    ['cizelge', t('zamanTakibi.alt.cizelge'), CalendarRange],
  ];
  if (yonetici) {
    altlar.push(
      ['isYuku', t('zamanTakibi.alt.isYuku'), BarChart3],
      ['onay', t('zamanTakibi.alt.onay'), CheckCheck],
      ['fatura', t('zamanTakibi.alt.fatura'), FileText],
      ['ayarlar', t('zamanTakibi.alt.ayarlar'), Settings2],
    );
  }

  return (
    <section className="min-w-0 space-y-5" data-testid="zaman-takibi">
      <div>
        <h2 className="text-xl font-semibold">{yonetici ? t('zamanTakibi.baslik') : t('zamanTakibi.personel.baslik')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{yonetici ? t('zamanTakibi.aciklama') : t('zamanTakibi.personel.aciklama')}</p>
      </div>
      {!secenekler ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : (
        <>
          <SayacCubugu secenekler={secenekler} onDegisti={yenile} />
          <div className="flex flex-wrap gap-2" role="tablist">
            {altlar.map(([k, etiket, Ikon]) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={alt === k}
                onClick={() => setAlt(k)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors ${
                  alt === k ? 'bg-purple-500/20 text-purple-200 ring-1 ring-purple-400/40' : 'bg-white/5 text-muted-foreground hover:text-foreground'
                }`}
                data-testid={`zaman-alt-${k}`}
              >
                <Ikon className="h-3.5 w-3.5" aria-hidden="true" /> {etiket}
              </button>
            ))}
          </div>
          {alt === 'kayitlar' && <KayitListesi secenekler={secenekler} yonetici={yonetici} surum={surum} onDegisti={yenile} />}
          {alt === 'cizelge' && <CizelgeGorunumu yonetici={yonetici} surum={surum} />}
          {yonetici && alt === 'isYuku' && <IsYukuGorunumu />}
          {yonetici && alt === 'onay' && <OnayKuyrugu surum={surum} onDegisti={yenile} />}
          {yonetici && alt === 'fatura' && (
            <FaturayaAktar
              secenekler={secenekler}
              onAktarildi={() => {
                yenile();
                onFaturaOlustu?.();
              }}
            />
          )}
          {yonetici && alt === 'ayarlar' && <Ayarlar secenekler={secenekler} />}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sayaç çubuğu
// ---------------------------------------------------------------------------
function SayacCubugu({ secenekler, onDegisti }: { secenekler: Secenekler; onDegisti: () => void }) {
  const { t } = useTranslation();
  const hata = useHata();
  const [sayac, setSayac] = useState<ZamanKaydi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [proje, setProje] = useState('');
  const [gorev, setGorev] = useState('');
  const [aciklama, setAciklama] = useState('');
  const [simdi, setSimdi] = useState(() => Date.now());
  const [mesgul, setMesgul] = useState(false);
  const [uzun, setUzun] = useState<ZamanKaydi | null>(null);
  const [uzunSure, setUzunSure] = useState('');

  useEffect(() => {
    sayacGetir()
      .then((y) => setSayac(y.sayac))
      .catch(() => setSayac(null))
      .finally(() => setYukleniyor(false));
  }, []);

  useEffect(() => {
    if (!sayac?.calisiyor) return undefined;
    const kimlik = window.setInterval(() => setSimdi(Date.now()), 1000);
    return () => window.clearInterval(kimlik);
  }, [sayac]);

  const gorevler = useMemo(() => secenekler.gorevler.filter((g) => String(g.proje_id) === proje), [secenekler, proje]);
  const gecenSn = sayac ? Math.max(0, (simdi - Date.parse(sayac.baslangic)) / 1000) : 0;

  const uzunAc = (h: unknown): boolean => {
    if (h instanceof ZamanHatasi && h.kod === 'uzun_sayac' && h.ek.kayit) {
      setUzun(h.ek.kayit as ZamanKaydi);
      setUzunSure('');
      return true;
    }
    return false;
  };

  const baslat = async () => {
    if (!proje) {
      toast.error(t('zamanTakibi.sayac.projeSec'));
      return;
    }
    setMesgul(true);
    try {
      const y = await sayacBaslat({ proje_id: Number(proje), gorev_id: gorev ? Number(gorev) : null, aciklama: aciklama.trim() || undefined });
      setSayac(y.sayac);
      setSimdi(Date.now());
      toast.success(t('zamanTakibi.sayac.basladi'));
      if (y.durdurulan) toast.message(t('zamanTakibi.sayac.oncekiDurdu', { sure: sureGoster(y.durdurulan.sure_dk) }));
      onDegisti();
    } catch (h) {
      if (!uzunAc(h)) hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const durdur = async (sure_dk?: number) => {
    setMesgul(true);
    try {
      const y = await sayacDurdur(sure_dk ? { sure_dk } : {});
      setSayac(null);
      setUzun(null);
      setAciklama('');
      toast.success(t('zamanTakibi.sayac.durdu', { sure: sureGoster(y.kayit.sure_dk) }));
      onDegisti();
    } catch (h) {
      if (!uzunAc(h)) hata(h);
    } finally {
      setMesgul(false);
    }
  };

  if (yukleniyor) return null;
  return (
    <div className={`${KART} space-y-3`} data-testid="sayac-cubugu">
      {sayac ? (
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex h-2.5 w-2.5 shrink-0 animate-pulse rounded-full bg-emerald-400" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="break-words text-sm font-medium">
              {sayac.proje_baslik}
              {sayac.gorev_baslik ? <span className="text-muted-foreground"> · {sayac.gorev_baslik}</span> : null}
            </p>
            {sayac.aciklama && <p className="break-words text-xs text-muted-foreground">{sayac.aciklama}</p>}
          </div>
          <span className="font-mono text-2xl tabular-nums" data-testid="sayac-sure" aria-live="off">
            {saniyeGoster(gecenSn)}
          </span>
          <Button type="button" size="sm" variant="destructive" onClick={() => void durdur()} disabled={mesgul} className="gap-1.5" data-testid="sayac-durdur">
            <Square className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.sayac.durdur')}
          </Button>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)_auto] sm:items-end">
          <label className="min-w-0">
            <span className={ETIKET}>{t('zamanTakibi.sayac.proje')}</span>
            <select value={proje} onChange={(e) => { setProje(e.target.value); setGorev(''); }} className={SECIM} data-testid="sayac-proje">
              <option value="">{t('zamanTakibi.fatura.projeSec')}</option>
              {secenekler.projeler.map((p) => (
                <option key={p.id} value={p.id}>{p.baslik}</option>
              ))}
            </select>
          </label>
          <label className="min-w-0">
            <span className={ETIKET}>{t('zamanTakibi.sayac.gorev')}</span>
            <select value={gorev} onChange={(e) => setGorev(e.target.value)} className={SECIM} disabled={!proje} data-testid="sayac-gorev">
              <option value="">{t('zamanTakibi.sayac.gorevYok')}</option>
              {gorevler.map((g) => (
                <option key={g.id} value={g.id}>{g.baslik}</option>
              ))}
            </select>
          </label>
          <label className="min-w-0">
            <span className={ETIKET}>{t('zamanTakibi.alan.aciklama')}</span>
            <Input value={aciklama} onChange={(e) => setAciklama(e.target.value)} placeholder={t('zamanTakibi.sayac.aciklama')} maxLength={1000}
              className="h-9 bg-white/5 border-white/10" data-testid="sayac-aciklama" />
          </label>
          <Button type="button" size="sm" onClick={() => void baslat()} disabled={mesgul} className="gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0" data-testid="sayac-baslat">
            <Play className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.sayac.baslat')}
          </Button>
        </div>
      )}
      {uzun && (
        <form
          className="space-y-2 rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm"
          data-testid="uzun-sayac"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            const dk = sureCoz(uzunSure);
            if (!dk) {
              toast.error(t('zamanTakibi.hata.sure_gecersiz'));
              return;
            }
            void durdur(dk);
          }}
        >
          <p className="font-semibold text-amber-200">{t('zamanTakibi.sayac.uzunBaslik')}</p>
          <p className="text-muted-foreground">{t('zamanTakibi.sayac.uzunAciklama', { sure: sureGoster(uzun.gecen_dk) })}</p>
          <div className="flex flex-wrap items-end gap-2">
            <label>
              <span className={ETIKET}>{t('zamanTakibi.sayac.uzunSure')}</span>
              <Input value={uzunSure} onChange={(e) => setUzunSure(e.target.value)} placeholder="8:00" className="h-9 w-28 bg-white/5 border-white/10" data-testid="uzun-sure" />
            </label>
            <Button type="submit" size="sm" disabled={mesgul} data-testid="uzun-onayla">{t('zamanTakibi.sayac.uzunOnayla')}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setUzun(null)} aria-label={t('zamanTakibi.kayit.vazgec')}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Kayıt formu
// ---------------------------------------------------------------------------
function KayitFormu({
  secenekler,
  yonetici,
  kayit,
  onBitti,
}: {
  secenekler: Secenekler;
  yonetici: boolean;
  kayit?: ZamanKaydi | null;
  onBitti: (degisti: boolean) => void;
}) {
  const { t } = useTranslation();
  const hata = useHata();
  // Sunucu "saat"i Türkiye saati sayıyor: düzenlemede de o saat diliminde göster.
  const ilkSaat = kayit
    ? new Date(kayit.baslangic).toLocaleTimeString('en-GB', { timeZone: 'Europe/Istanbul', hour: '2-digit', minute: '2-digit', hour12: false })
    : '09:00';
  const [form, setForm] = useState({
    proje: kayit ? String(kayit.proje_id) : '',
    gorev: kayit?.gorev_id ? String(kayit.gorev_id) : '',
    tarih: kayit?.gun || bugunYerel(),
    saat: ilkSaat,
    sure: kayit?.sure_dk ? sureGoster(kayit.sure_dk) : '',
    aciklama: kayit?.aciklama || '',
    faturalanabilir: kayit ? kayit.faturalanabilir : true,
    tur: (kayit?.tur || '') as ZamanTuru | '',
    kisi: kayit?.kisi_eposta || '',
  });
  const [mesgul, setMesgul] = useState(false);
  const gorevler = secenekler.gorevler.filter((g) => String(g.proje_id) === form.proje);
  const alan = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.proje) {
      toast.error(t('zamanTakibi.hata.proje_gerekli'));
      return;
    }
    const dk = sureCoz(form.sure);
    if (!dk) {
      toast.error(t('zamanTakibi.hata.sure_gecersiz'));
      return;
    }
    const girdi: KayitGirdisi = {
      proje_id: Number(form.proje),
      gorev_id: form.gorev ? Number(form.gorev) : null,
      tarih: form.tarih,
      saat: form.saat || '09:00',
      sure_dk: dk,
      aciklama: form.aciklama.trim(),
      faturalanabilir: form.faturalanabilir,
    };
    if (form.tur) girdi.tur = form.tur;
    if (yonetici && form.kisi && !kayit) girdi.kisi_eposta = form.kisi;
    setMesgul(true);
    try {
      if (kayit) {
        await kayitGuncelle(kayit.id, girdi);
        toast.success(t('zamanTakibi.kayit.guncellendi'));
      } else {
        await kayitEkle(girdi);
        toast.success(t('zamanTakibi.kayit.eklendi'));
      }
      onBitti(true);
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  return (
    <form onSubmit={gonder} className="space-y-3 rounded-xl border border-purple-500/30 bg-white/[0.02] p-3 sm:p-4" data-testid="kayit-formu">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.proje')}</span>
          <select name="proje" value={form.proje} onChange={(e) => { alan('proje', e.target.value); alan('gorev', ''); }} className={SECIM} required>
            <option value="">{t('zamanTakibi.fatura.projeSec')}</option>
            {secenekler.projeler.map((p) => (
              <option key={p.id} value={p.id}>{p.baslik}</option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.gorev')}</span>
          <select name="gorev" value={form.gorev} onChange={(e) => alan('gorev', e.target.value)} className={SECIM} disabled={!form.proje}>
            <option value="">{t('zamanTakibi.sayac.gorevYok')}</option>
            {gorevler.map((g) => (
              <option key={g.id} value={g.id}>{g.baslik}</option>
            ))}
          </select>
        </label>
        {yonetici && !kayit && secenekler.ekip && (
          <label className="min-w-0">
            <span className={ETIKET}>{t('zamanTakibi.alan.kisi')}</span>
            <select name="kisi" value={form.kisi} onChange={(e) => alan('kisi', e.target.value)} className={SECIM}>
              <option value="">—</option>
              {secenekler.ekip.map((k) => (
                <option key={k.email} value={k.email}>{k.ad} ({k.email})</option>
              ))}
            </select>
          </label>
        )}
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.tarih')}</span>
          <Input type="date" name="tarih" value={form.tarih} max={bugunYerel()} onChange={(e) => alan('tarih', e.target.value)} className="h-9 bg-white/5 border-white/10" required />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.saat')}</span>
          <Input type="time" name="saat" value={form.saat} onChange={(e) => alan('saat', e.target.value)} className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.sure')}</span>
          <Input name="sure" value={form.sure} onChange={(e) => alan('sure', e.target.value)} placeholder={t('zamanTakibi.alan.sureIpucu')} className="h-9 bg-white/5 border-white/10" required />
        </label>
        <label className="min-w-0 sm:col-span-2">
          <span className={ETIKET}>{t('zamanTakibi.alan.aciklama')}</span>
          <Input name="aciklama" value={form.aciklama} onChange={(e) => alan('aciklama', e.target.value)} maxLength={1000} className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.tur')}</span>
          <select name="tur" value={form.tur} onChange={(e) => alan('tur', e.target.value as ZamanTuru | '')} className={SECIM}>
            <option value="">—</option>
            <option value="normal">{t('zamanTakibi.tur.normal')}</option>
            <option value="revizyon">{t('zamanTakibi.tur.revizyon')}</option>
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" name="faturalanabilir" checked={form.faturalanabilir} onChange={(e) => alan('faturalanabilir', e.target.checked)} className="h-4 w-4 accent-purple-500" />
          {t('zamanTakibi.alan.faturalanabilir')}
        </label>
        <div className="ms-auto flex gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={() => onBitti(false)}>{t('zamanTakibi.kayit.vazgec')}</Button>
          <Button type="submit" size="sm" disabled={mesgul} data-testid="kayit-kaydet">
            {kayit ? t('zamanTakibi.kayit.guncelle') : t('zamanTakibi.kayit.kaydet')}
          </Button>
        </div>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Kayıt listesi
// ---------------------------------------------------------------------------
function KayitListesi({
  secenekler,
  yonetici,
  surum,
  onDegisti,
}: {
  secenekler: Secenekler;
  yonetici: boolean;
  surum: number;
  onDegisti: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const hata = useHata();
  const [suzgec, setSuzgec] = useState({ durum: '', proje: '', kisi: '', baslangic: '', bitis: '' });
  const [liste, setListe] = useState<ZamanKaydi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [form, setForm] = useState<'yeni' | ZamanKaydi | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setListe(
        await kayitlariGetir({
          durum: suzgec.durum || undefined,
          proje_id: suzgec.proje ? Number(suzgec.proje) : undefined,
          kisi: suzgec.kisi || undefined,
          baslangic: suzgec.baslangic || undefined,
          bitis: suzgec.bitis || undefined,
          sinir: 300,
        }),
      );
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [suzgec, hata]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum]);

  const sil = async (k: ZamanKaydi) => {
    if (!confirm(t('zamanTakibi.kayit.silOnay'))) return;
    try {
      await kayitSil(k.id);
      toast.success(t('zamanTakibi.kayit.silindi'));
      onDegisti();
    } catch (h) {
      hata(h);
    }
  };

  const geriAl = async (k: ZamanKaydi) => {
    try {
      await onayiGeriAl(k.id);
      toast.success(t('zamanTakibi.kayit.geriAlindi'));
      onDegisti();
    } catch (h) {
      hata(h);
    }
  };

  const csv = async () => {
    try {
      await csvIndir({ baslangic: suzgec.baslangic || undefined, bitis: suzgec.bitis || undefined, proje_id: suzgec.proje ? Number(suzgec.proje) : null });
      toast.success(t('zamanTakibi.kayit.csvIndirildi'));
    } catch {
      toast.error(t('zamanTakibi.hata.genel'));
    }
  };

  const toplam = liste.reduce((s, k) => s + (k.sure_dk || 0), 0);
  const s = (k: keyof typeof suzgec, v: string) => setSuzgec((x) => ({ ...x, [k]: v }));

  return (
    <div className={`${KART} space-y-4`}>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.durum')}</span>
          <select value={suzgec.durum} onChange={(e) => s('durum', e.target.value)} className={SECIM} data-testid="suzgec-durum">
            <option value="">{t('zamanTakibi.alan.hepsi')}</option>
            {ZAMAN_DURUMLARI.map((d) => (
              <option key={d} value={d}>{t(`zamanTakibi.durum.${d}`)}</option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.proje')}</span>
          <select value={suzgec.proje} onChange={(e) => s('proje', e.target.value)} className={SECIM} data-testid="suzgec-proje">
            <option value="">{t('zamanTakibi.alan.hepsi')}</option>
            {secenekler.projeler.map((p) => (
              <option key={p.id} value={p.id}>{p.baslik}</option>
            ))}
          </select>
        </label>
        {yonetici && (
          <label className="min-w-0">
            <span className={ETIKET}>{t('zamanTakibi.alan.kisi')}</span>
            <select value={suzgec.kisi} onChange={(e) => s('kisi', e.target.value)} className={SECIM}>
              <option value="">{t('zamanTakibi.alan.hepsi')}</option>
              {(secenekler.ekip || []).map((k) => (
                <option key={k.email} value={k.email}>{k.ad}</option>
              ))}
            </select>
          </label>
        )}
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.baslangic')}</span>
          <Input type="date" value={suzgec.baslangic} onChange={(e) => s('baslangic', e.target.value)} className="h-9 bg-white/5 border-white/10" data-testid="suzgec-baslangic" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.alan.bitis')}</span>
          <Input type="date" value={suzgec.bitis} onChange={(e) => s('bitis', e.target.value)} className="h-9 bg-white/5 border-white/10" data-testid="suzgec-bitis" />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={() => setForm(form === 'yeni' ? null : 'yeni')} className="gap-1.5" data-testid="kayit-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.kayit.yeni')}
        </Button>
        {yonetici && (
          <Button type="button" size="sm" variant="outline" onClick={() => void csv()} className="gap-1.5 !bg-transparent" data-testid="csv-indir">
            <Download className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.kayit.csv')}
          </Button>
        )}
        <Button type="button" size="sm" variant="ghost" onClick={() => void yukle()} aria-label="↻">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <span className="ms-auto text-sm text-muted-foreground" data-testid="kayit-toplam">{t('zamanTakibi.kayit.toplam', { sure: sureGoster(toplam) })}</span>
      </div>
      {form === 'yeni' && (
        <KayitFormu
          secenekler={secenekler}
          yonetici={yonetici}
          onBitti={(d) => {
            setForm(null);
            if (d) onDegisti();
          }}
        />
      )}
      {yukleniyor ? (
        <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
      ) : liste.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t('zamanTakibi.kayit.bos')}</p>
      ) : (
        <ul className="space-y-2" data-testid="kayit-listesi">
          {liste.map((k) => (
            <li key={k.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm" data-testid={`kayit-${k.id}`}>
              {form !== 'yeni' && form && form.id === k.id ? (
                <KayitFormu
                  secenekler={secenekler}
                  yonetici={yonetici}
                  kayit={k}
                  onBitti={(d) => {
                    setForm(null);
                    if (d) onDegisti();
                  }}
                />
              ) : (
                <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
                  <span className="w-14 shrink-0 font-mono font-semibold tabular-nums">{k.calisiyor ? '⏱' : sureGoster(k.sure_dk)}</span>
                  <div className="min-w-0 flex-1 basis-48">
                    <p className="break-words font-medium">
                      {k.proje_baslik || `#${k.proje_id}`}
                      {k.gorev_id ? <span className="text-muted-foreground"> · {k.gorev_baslik || `#${k.gorev_id}`}</span> : null}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {[tarihGoster(k.gun, dil), yonetici ? k.kisi_ad || k.kisi_eposta : null, k.aciklama].filter(Boolean).join(' · ')}
                    </p>
                    {k.ret_notu && <p className="mt-1 text-xs text-rose-300">{t('zamanTakibi.kayit.retNotu', { not: k.ret_notu })}</p>}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {k.tur === 'revizyon' && <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-200">{t('zamanTakibi.tur.revizyon')}</span>}
                    {!k.faturalanabilir && <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-muted-foreground line-through">{t('zamanTakibi.alan.faturalanabilir')}</span>}
                    <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider ${k.calisiyor ? 'bg-emerald-500/20 text-emerald-200' : DURUM_RENGI[k.durum]}`} data-testid={`kayit-durum-${k.id}`}>
                      {k.calisiyor ? t('zamanTakibi.sayac.calisiyor') : t(`zamanTakibi.durum.${k.durum}`)}
                    </span>
                    {yonetici && k.tutar !== null && <span className="text-xs text-muted-foreground">{paraGoster(k.tutar, k.para_birimi, dil)}</span>}
                    {k.fatura_id && <span className="text-[10px] text-sky-300">{t('zamanTakibi.kayit.faturaNo', { id: k.fatura_id })}</span>}
                    {k.kilitli ? (
                      <>
                        <Lock className="h-3.5 w-3.5 text-muted-foreground" aria-label={t('zamanTakibi.kayit.kilitli')} />
                        {yonetici && k.durum === 'onaylandi' && (
                          <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => void geriAl(k)} data-testid={`kayit-geri-al-${k.id}`}>
                            <Undo2 className="h-3.5 w-3.5" /> {t('zamanTakibi.kayit.geriAl')}
                          </Button>
                        )}
                      </>
                    ) : (
                      <>
                        {!k.calisiyor && (
                          <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setForm(k)} aria-label={t('zamanTakibi.kayit.duzenle')} data-testid={`kayit-duzenle-${k.id}`}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive hover:text-destructive" onClick={() => void sil(k)} aria-label={t('zamanTakibi.kayit.sil')} data-testid={`kayit-sil-${k.id}`}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Haftalık çizelge
// ---------------------------------------------------------------------------
function CizelgeGorunumu({ yonetici, surum }: { yonetici: boolean; surum: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const hata = useHata();
  const [hafta, setHafta] = useState(bugunYerel());
  const [veri, setVeri] = useState<Cizelge | null>(null);

  useEffect(() => {
    let iptal = false;
    cizelgeGetir(hafta)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch((h) => hata(h));
    return () => {
      iptal = true;
    };
  }, [hafta, surum, hata]);

  return (
    <div className={`${KART} space-y-3`} data-testid="cizelge">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="me-auto font-semibold">{t('zamanTakibi.cizelge.baslik')}</h3>
        <Button type="button" size="sm" variant="ghost" onClick={() => setHafta(gunEkle(veri?.hafta_baslangic || hafta, -7))} aria-label={t('zamanTakibi.cizelge.onceki')} data-testid="cizelge-onceki">
          <ChevronLeft className="h-4 w-4 rtl:rotate-180" />
        </Button>
        <Button type="button" size="sm" variant="outline" className="!bg-transparent" onClick={() => setHafta(bugunYerel())}>{t('zamanTakibi.cizelge.buHafta')}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setHafta(gunEkle(veri?.hafta_baslangic || hafta, 7))} aria-label={t('zamanTakibi.cizelge.sonraki')} data-testid="cizelge-sonraki">
          <ChevronRight className="h-4 w-4 rtl:rotate-180" />
        </Button>
      </div>
      {!veri ? (
        <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
      ) : veri.kisiler.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t('zamanTakibi.cizelge.bos')}</p>
      ) : (
        <div className="max-w-full overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-white/[0.03] text-xs text-muted-foreground">
              <tr>
                <th className="p-2 text-start font-medium">{t('zamanTakibi.cizelge.kisi')}</th>
                {veri.gunler.map((g) => (
                  <th key={g} className="p-2 text-end font-medium">{gunAdi(g, dil)}</th>
                ))}
                <th className="p-2 text-end font-medium">{t('zamanTakibi.cizelge.toplam')}</th>
              </tr>
            </thead>
            <tbody>
              {veri.kisiler.map((s) => (
                <tr key={s.eposta} className="border-t border-white/5" data-testid={`cizelge-satir-${s.eposta}`}>
                  <td className="p-2">
                    <p className="font-medium">{s.ad || s.eposta}</p>
                    {yonetici && (
                      <p className="text-[10px] text-muted-foreground">
                        {t('zamanTakibi.cizelge.onayli')} {sureGoster(s.onayli_dk)} · {t('zamanTakibi.cizelge.taslak')} {sureGoster(s.taslak_dk)}
                      </p>
                    )}
                  </td>
                  {s.gunler.map((dk, i) => (
                    <td key={i} className={`p-2 text-end font-mono tabular-nums ${dk ? '' : 'text-muted-foreground/40'}`}>{dk ? sureGoster(dk) : '—'}</td>
                  ))}
                  <td className="p-2 text-end font-mono font-semibold tabular-nums">{sureGoster(s.toplam_dk)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t border-white/10 text-xs">
              <tr>
                <td className="p-2 font-semibold">{t('zamanTakibi.cizelge.toplam')}</td>
                {veri.gun_toplamlari.map((dk, i) => (
                  <td key={i} className="p-2 text-end font-mono tabular-nums">{dk ? sureGoster(dk) : '—'}</td>
                ))}
                <td className="p-2 text-end font-mono font-semibold tabular-nums" data-testid="cizelge-genel-toplam">{sureGoster(veri.genel_toplam_dk)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// İş yükü (CSS çubuk)
// ---------------------------------------------------------------------------
function IsYukuGorunumu() {
  const { t } = useTranslation();
  const hata = useHata();
  const [veri, setVeri] = useState<IsYuku | null>(null);

  useEffect(() => {
    isYukuGetir().then(setVeri).catch((h) => hata(h));
  }, [hata]);

  if (!veri) return <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  const tavan = Math.max(veri.en_cok_dk, 60);
  return (
    <div className={`${KART} space-y-4`} data-testid="is-yuku">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <h3 className="me-auto text-base font-semibold text-foreground">{t('zamanTakibi.isYuku.baslik')}</h3>
        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-4 rounded bg-gradient-to-r from-purple-500 to-pink-500" />{t('zamanTakibi.isYuku.buHafta')}</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-4 rounded bg-white/25" />{t('zamanTakibi.isYuku.gecenHafta')}</span>
      </div>
      {veri.kisiler.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t('zamanTakibi.isYuku.bos')}</p>
      ) : (
        <ul className="space-y-3">
          {veri.kisiler.map((k) => (
            <li key={k.eposta} className="space-y-1.5" data-testid={`yuk-${k.eposta}`}>
              <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
                <span className="me-auto min-w-0 break-words font-medium">{k.ad || k.eposta}</span>
                <span className="text-xs text-muted-foreground">
                  {t('zamanTakibi.isYuku.acikGorev')}: <b className="text-foreground">{k.acik_gorev}</b>
                  {' · '}
                  {t('zamanTakibi.isYuku.gecikenGorev')}: <b className={k.geciken_gorev ? 'text-rose-300' : 'text-foreground'}>{k.geciken_gorev}</b>
                </span>
              </div>
              <div className="flex items-center gap-2" title={t('zamanTakibi.isYuku.buHafta')}>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/5" role="meter" aria-valuemin={0} aria-valuemax={tavan} aria-valuenow={k.bu_hafta_dk} aria-label={t('zamanTakibi.isYuku.buHafta')}>
                  <div className="h-full rounded-full bg-gradient-to-r from-purple-500 to-pink-500" style={{ width: `${Math.min(100, (k.bu_hafta_dk / tavan) * 100)}%` }} />
                </div>
                <span className="w-12 text-end font-mono text-xs tabular-nums">{sureGoster(k.bu_hafta_dk)}</span>
              </div>
              <div className="flex items-center gap-2" title={t('zamanTakibi.isYuku.gecenHafta')}>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5" role="meter" aria-valuemin={0} aria-valuemax={tavan} aria-valuenow={k.gecen_hafta_dk} aria-label={t('zamanTakibi.isYuku.gecenHafta')}>
                  <div className="h-full rounded-full bg-white/25" style={{ width: `${Math.min(100, (k.gecen_hafta_dk / tavan) * 100)}%` }} />
                </div>
                <span className="w-12 text-end font-mono text-[11px] tabular-nums text-muted-foreground">{sureGoster(k.gecen_hafta_dk)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Onay kuyruğu
// ---------------------------------------------------------------------------
function OnayKuyrugu({ surum, onDegisti }: { surum: number; onDegisti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const hata = useHata();
  const [liste, setListe] = useState<ZamanKaydi[] | null>(null);
  const [secili, setSecili] = useState<Set<number>>(new Set());
  const [not, setNot] = useState('');
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    kayitlariGetir({ durum: 'taslak', sinir: 500 })
      .then((l) => {
        const durmus = l.filter((k) => !k.calisiyor);
        setListe(durmus);
        setSecili(new Set());
      })
      .catch((h) => hata(h));
  }, [surum, hata]);

  const islem = async (tur: 'onayla' | 'reddet') => {
    if (secili.size === 0) {
      toast.error(t('zamanTakibi.hata.kayit_secilmedi'));
      return;
    }
    if (tur === 'reddet' && !not.trim()) {
      toast.error(t('zamanTakibi.hata.ret_notu_gerekli'));
      return;
    }
    setMesgul(true);
    try {
      const y = await onayIslemi([...secili], tur, tur === 'reddet' ? not.trim() : undefined);
      toast.success(t(tur === 'onayla' ? 'zamanTakibi.onay.onaylandi' : 'zamanTakibi.onay.reddedildi', { sayi: y.islenen.length }));
      if (y.atlanan.length) toast.message(t('zamanTakibi.onay.atlanan', { sayi: y.atlanan.length }));
      setNot('');
      onDegisti();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  if (!liste) return <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  const hepsi = liste.length > 0 && secili.size === liste.length;
  return (
    <div className={`${KART} space-y-3`} data-testid="onay-kuyrugu">
      <h3 className="font-semibold">{t('zamanTakibi.onay.baslik')}</h3>
      {liste.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">{t('zamanTakibi.onay.bos')}</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" checked={hepsi} onChange={(e) => setSecili(e.target.checked ? new Set(liste.map((k) => k.id)) : new Set())}
                className="h-4 w-4 accent-purple-500" data-testid="onay-hepsi" />
              {t('zamanTakibi.onay.hepsi')}
            </label>
            <span className="text-xs text-muted-foreground">{t('zamanTakibi.onay.secim', { sayi: secili.size })}</span>
          </div>
          <ul className="space-y-1.5">
            {liste.map((k) => (
              <li key={k.id} className="flex items-start gap-2 rounded-lg bg-white/[0.03] p-2 text-sm">
                <input type="checkbox" checked={secili.has(k.id)} aria-label={`#${k.id}`}
                  onChange={(e) => setSecili((s) => { const y = new Set(s); if (e.target.checked) y.add(k.id); else y.delete(k.id); return y; })}
                  className="mt-1 h-4 w-4 shrink-0 accent-purple-500" data-testid={`onay-sec-${k.id}`} />
                <span className="w-12 shrink-0 font-mono tabular-nums">{sureGoster(k.sure_dk)}</span>
                <span className="min-w-0 flex-1 break-words">
                  <b>{k.kisi_ad || k.kisi_eposta}</b> · {k.proje_baslik}
                  {k.gorev_baslik ? ` · ${k.gorev_baslik}` : ''}
                  <span className="block text-xs text-muted-foreground">{[tarihGoster(k.gun, dil), k.aciklama].filter(Boolean).join(' · ')}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" onClick={() => void islem('onayla')} disabled={mesgul} className="gap-1.5" data-testid="onay-onayla">
              <CheckCheck className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.onay.onayla')}
            </Button>
            <Input value={not} onChange={(e) => setNot(e.target.value)} placeholder={t('zamanTakibi.onay.not')} maxLength={1000}
              className="h-9 min-w-0 flex-1 basis-48 bg-white/5 border-white/10" data-testid="onay-not" />
            <Button type="button" size="sm" variant="outline" onClick={() => void islem('reddet')} disabled={mesgul} className="!bg-transparent text-rose-300" data-testid="onay-reddet">
              {t('zamanTakibi.onay.reddet')}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Faturaya aktar
// ---------------------------------------------------------------------------
function FaturayaAktar({ secenekler, onAktarildi }: { secenekler: Secenekler; onAktarildi: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const hata = useHata();
  const [proje, setProje] = useState('');
  const [veri, setVeri] = useState<Faturalanabilir | null>(null);
  const [secili, setSecili] = useState<Set<number>>(new Set());
  const [gruplama, setGruplama] = useState<Gruplama>('tek');
  const [kdv, setKdv] = useState('20');
  const [ucret, setUcret] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [sonuc, setSonuc] = useState<AktarimSonucu | null>(null);

  const yukle = useCallback(async (pid: string) => {
    setVeri(null);
    if (!pid) return;
    try {
      const v = await faturalanabilirGetir(Number(pid));
      setVeri(v);
      setSecili(new Set(v.kayitlar.map((k) => k.id)));
    } catch (h) {
      hata(h);
    }
  }, [hata]);

  useEffect(() => {
    void yukle(proje);
  }, [proje, yukle]);

  const ucretsizVar = !!veri?.kayitlar.some((k) => secili.has(k.id) && k.saatlik_ucret === null);
  const seciliDk = veri ? veri.kayitlar.filter((k) => secili.has(k.id)).reduce((s, k) => s + (k.sure_dk || 0), 0) : 0;

  const aktar = async () => {
    if (!veri || secili.size === 0) {
      toast.error(t('zamanTakibi.hata.kayit_secilmedi'));
      return;
    }
    setMesgul(true);
    try {
      const y = await faturayaAktar({
        proje_id: veri.proje.id,
        idler: [...secili],
        gruplama,
        kdv_orani: Number(kdv) || 0,
        varsayilan_ucret: ucretsizVar && ucret ? Number(ucret.replace(',', '.')) : null,
      });
      setSonuc(y);
      toast.success(t('zamanTakibi.fatura.sonuc', { sayi: y.kayit_sayisi, no: y.invoice_no, tutar: paraGoster(y.tutar, y.para_birimi, dil) }));
      onAktarildi();
      await yukle(proje);
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className={`${KART} space-y-4`} data-testid="faturaya-aktar">
      <div>
        <h3 className="font-semibold">{t('zamanTakibi.fatura.baslik')}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t('zamanTakibi.fatura.aciklama')}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0 lg:col-span-2">
          <span className={ETIKET}>{t('zamanTakibi.fatura.proje')}</span>
          <select value={proje} onChange={(e) => { setProje(e.target.value); setSonuc(null); }} className={SECIM} data-testid="aktar-proje">
            <option value="">{t('zamanTakibi.fatura.projeSec')}</option>
            {secenekler.projeler.map((p) => (
              <option key={p.id} value={p.id}>{p.baslik}{p.client_email ? ` — ${p.client_email}` : ''}</option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.fatura.gruplama')}</span>
          <select value={gruplama} onChange={(e) => setGruplama(e.target.value as Gruplama)} className={SECIM} data-testid="aktar-gruplama">
            {(['tek', 'kisi', 'gorev'] as Gruplama[]).map((g) => (
              <option key={g} value={g}>{t(`zamanTakibi.fatura.grup.${g}`)}</option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('zamanTakibi.fatura.kdv')}</span>
          <select value={kdv} onChange={(e) => setKdv(e.target.value)} className={SECIM} data-testid="aktar-kdv">
            {['0', '1', '10', '20'].map((o) => (
              <option key={o} value={o}>%{o}</option>
            ))}
          </select>
        </label>
      </div>
      {sonuc && (
        <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm" data-testid="aktar-sonuc">
          {t('zamanTakibi.fatura.sonuc', { sayi: sonuc.kayit_sayisi, no: sonuc.invoice_no, tutar: paraGoster(sonuc.tutar, sonuc.para_birimi, dil) })}{' '}
          <Link to={{ search: '?sekme=invoices' }} className="font-medium text-emerald-200 underline underline-offset-2" data-testid="aktar-faturalara-git">
            {t('zamanTakibi.fatura.faturalaraGit')}
          </Link>
        </div>
      )}
      {proje && !veri && <div className="flex justify-center py-4 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>}
      {veri && (
        veri.kayitlar.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">{t('zamanTakibi.fatura.bos')}</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">
              {t(`zamanTakibi.fatura.ucretKaynagi.${veri.ucret_kaynagi}`)}
              {veri.proje_ucreti !== null ? `: ${paraGoster(veri.proje_ucreti, veri.para_birimi, dil)}` : ''}
            </p>
            <ul className="space-y-1.5">
              {veri.kayitlar.map((k) => (
                <li key={k.id} className="flex items-start gap-2 rounded-lg bg-white/[0.03] p-2 text-sm">
                  <input type="checkbox" checked={secili.has(k.id)} aria-label={`#${k.id}`}
                    onChange={(e) => setSecili((s) => { const y = new Set(s); if (e.target.checked) y.add(k.id); else y.delete(k.id); return y; })}
                    className="mt-1 h-4 w-4 shrink-0 accent-purple-500" data-testid={`aktar-sec-${k.id}`} />
                  <span className="w-12 shrink-0 font-mono tabular-nums">{sureGoster(k.sure_dk)}</span>
                  <span className="min-w-0 flex-1 break-words">
                    <b>{k.kisi_ad || k.kisi_eposta}</b>{k.gorev_baslik ? ` · ${k.gorev_baslik}` : ''}
                    <span className="block text-xs text-muted-foreground">{[tarihGoster(k.gun, dil), k.aciklama].filter(Boolean).join(' · ')}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">{paraGoster(k.tutar, k.para_birimi, dil)}</span>
                </li>
              ))}
            </ul>
            {ucretsizVar && (
              <label className="block max-w-xs">
                <span className={ETIKET}>{t('zamanTakibi.fatura.varsayilanUcret')}</span>
                <Input value={ucret} onChange={(e) => setUcret(e.target.value)} inputMode="decimal" className="h-9 bg-white/5 border-white/10" data-testid="aktar-ucret" />
              </label>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-muted-foreground">{t('zamanTakibi.fatura.secili', { sure: sureGoster(seciliDk) })}</span>
              <Button type="button" size="sm" onClick={() => void aktar()} disabled={mesgul || secili.size === 0} className="ms-auto gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0" data-testid="aktar-gonder">
                <FileText className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.fatura.aktar')}
              </Button>
            </div>
          </>
        )
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ayarlar
// ---------------------------------------------------------------------------
function Ayarlar({ secenekler }: { secenekler: Secenekler }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const hata = useHata();
  const [genel, setGenel] = useState({ ucret: '', pb: 'TRY' });
  const [proje, setProje] = useState('');
  const [ayar, setAyar] = useState<ProjeAyari | null>(null);
  const [projeForm, setProjeForm] = useState({ ucret: '', pb: '', sure: false, faturalanabilir: false });

  useEffect(() => {
    zamanAyarlari()
      .then((a) => setGenel({ ucret: a.saatlik_ucret === null ? '' : String(a.saatlik_ucret), pb: a.para_birimi }))
      .catch((h) => hata(h));
  }, [hata]);

  useEffect(() => {
    setAyar(null);
    if (!proje) return;
    projeAyariGetir(Number(proje))
      .then((a) => {
        setAyar(a);
        setProjeForm({ ucret: a.saatlik_ucret === null ? '' : String(a.saatlik_ucret), pb: a.ucret_para_birimi || '', sure: a.sure_musteriye_gorunur, faturalanabilir: a.faturalanabilir_musteriye_gorunur });
      })
      .catch((h) => hata(h));
  }, [proje, hata]);

  const genelKaydet = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const a = await zamanAyarlariYaz({ saatlik_ucret: genel.ucret.trim() ? Number(genel.ucret.replace(',', '.')) : null, para_birimi: genel.pb });
      setGenel({ ucret: a.saatlik_ucret === null ? '' : String(a.saatlik_ucret), pb: a.para_birimi });
      toast.success(t('zamanTakibi.ayar.kaydedildi'));
    } catch (h) {
      hata(h);
    }
  };

  const projeKaydet = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const a = await projeAyariYaz(Number(proje), {
        saatlik_ucret: projeForm.ucret.trim() ? Number(projeForm.ucret.replace(',', '.')) : null,
        ucret_para_birimi: projeForm.pb || null,
        sure_musteriye_gorunur: projeForm.sure,
        faturalanabilir_musteriye_gorunur: projeForm.faturalanabilir,
      });
      setAyar(a);
      toast.success(t('zamanTakibi.ayar.kaydedildi'));
    } catch (h) {
      hata(h);
    }
  };

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-2" data-testid="zaman-ayarlari">
      <form onSubmit={genelKaydet} className={`${KART} space-y-3`}>
        <h3 className="font-semibold">{t('zamanTakibi.ayar.baslik')}</h3>
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-0 flex-1 basis-40">
            <span className={ETIKET}>{t('zamanTakibi.ayar.varsayilan')}</span>
            <Input value={genel.ucret} onChange={(e) => setGenel((g) => ({ ...g, ucret: e.target.value }))} inputMode="decimal" className="h-9 bg-white/5 border-white/10" data-testid="ayar-ucret" />
          </label>
          <label className="w-24">
            <span className={ETIKET}>{t('zamanTakibi.alan.paraBirimi')}</span>
            <select value={genel.pb} onChange={(e) => setGenel((g) => ({ ...g, pb: e.target.value }))} className={SECIM}>
              {PARA_BIRIMLERI.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <Button type="submit" size="sm" data-testid="ayar-kaydet">{t('zamanTakibi.ayar.kaydet')}</Button>
        </div>
      </form>
      <form onSubmit={projeKaydet} className={`${KART} space-y-3`}>
        <h3 className="font-semibold">{t('zamanTakibi.ayar.proje')}</h3>
        <select value={proje} onChange={(e) => setProje(e.target.value)} className={SECIM} data-testid="ayar-proje">
          <option value="">{t('zamanTakibi.fatura.projeSec')}</option>
          {secenekler.projeler.map((p) => <option key={p.id} value={p.id}>{p.baslik}</option>)}
        </select>
        {ayar && (
          <>
            <div className="flex flex-wrap items-end gap-2">
              <label className="min-w-0 flex-1 basis-40">
                <span className={ETIKET}>{t('zamanTakibi.ayar.projeUcret')}</span>
                <Input value={projeForm.ucret} onChange={(e) => setProjeForm((f) => ({ ...f, ucret: e.target.value }))} inputMode="decimal" className="h-9 bg-white/5 border-white/10" data-testid="ayar-proje-ucret" />
              </label>
              <label className="w-24">
                <span className={ETIKET}>{t('zamanTakibi.alan.paraBirimi')}</span>
                <select value={projeForm.pb} onChange={(e) => setProjeForm((f) => ({ ...f, pb: e.target.value }))} className={SECIM}>
                  <option value="">—</option>
                  {PARA_BIRIMLERI.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('zamanTakibi.ayar.etkin', { ucret: paraGoster(ayar.etkin_ucret, ayar.etkin_para_birimi, dil), kaynak: t(`zamanTakibi.fatura.ucretKaynagi.${ayar.ucret_kaynagi}`) })}
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={projeForm.sure} onChange={(e) => setProjeForm((f) => ({ ...f, sure: e.target.checked }))} className="h-4 w-4 accent-purple-500" data-testid="ayar-sure-goster" />
              {t('zamanTakibi.ayar.sureGoster')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={projeForm.faturalanabilir} disabled={!projeForm.sure} onChange={(e) => setProjeForm((f) => ({ ...f, faturalanabilir: e.target.checked }))} className="h-4 w-4 accent-purple-500" />
              {t('zamanTakibi.ayar.faturalanabilirGoster')}
            </label>
            <Button type="submit" size="sm" data-testid="ayar-proje-kaydet">{t('zamanTakibi.ayar.kaydet')}</Button>
          </>
        )}
      </form>
    </div>
  );
}
