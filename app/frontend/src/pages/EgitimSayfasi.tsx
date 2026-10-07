import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import {
  AlertTriangle,
  Award,
  BookOpen,
  CalendarDays,
  CalendarPlus,
  CheckCircle2,
  Circle,
  ClipboardCheck,
  Clock,
  Download,
  ExternalLink,
  FileText,
  Globe,
  GraduationCap,
  Loader2,
  MapPin,
  Megaphone,
  PlayCircle,
  QrCode,
  ShieldCheck,
  ShieldX,
  Upload,
  Users,
  Video,
  XCircle,
} from 'lucide-react';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import { seciliHesap } from '@/lib/hesapSecimi';
import {
  DIL_ADLARI,
  ETKINLIK_DILLERI,
  OkutmaHatasi,
  api,
  aralikYaz,
  depoOku,
  depoYaz,
  dilSec,
  hataKodu,
  sorgu,
  tarihYaz,
  type EtkinlikDili,
  type OkutmaIstemcisi,
  type OkutmaYaniti,
  type Sayac,
} from '@/lib/etkinlikOrtak';

/**
 * Faz 6K — eğitim modülünün herkese açık sayfaları (site düzeninin DIŞINDA, lazy; prerender yok, site
 * haritasında yok; varsayılan noindex — sahibi "arama motorlarında görünsün" derse kurs sayfası index +
 * Course JSON-LD; paylaşım önizlemesi `functions/egitim/[[yol]].js`):
 *
 *   /egitim/<slug>                 kurs + kayıt formu (KVKK aydınlatma, isteğe bağlı pazarlama izni, veli)
 *   /egitim/ogrenci/<jeton>        imzalı öğrenci sayfası (girişsiz): dersler, ilerleme, quiz/ödev, yoklama, sertifika
 *   /egitim/yoklama/<jeton>        sınıfta okutulan oturum QR'ı → bu cihazdaki öğrenci bağlantısıyla yoklama
 *   /egitim/sertifika/<kod>        sertifika doğrulama (yalnız maskeli ad)
 *   /egitim/okut/<kurs>/<oturum>   panel okutucusu (eğitmen öğrencinin QR'ını okutur; ekip izni)
 *   /egitim/kurum/<slug>           hesabın kurs listesi
 *
 * Metinler sayfanın KENDİ dilinde (ziyaretçi seçimi → kurs dili); ek paket `egitimSayfa`.
 */

const Okutucu = lazy(() => import('@/components/etkinlik/Okutucu'));

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/egitimSayfa/*.json');
const yuklenenDiller = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenenDiller.has(d)) continue;
    const yukleyici = EK_PAKETLER[`../i18n/ek/egitimSayfa/${d}.json`];
    if (!yukleyici) continue;
    const mod = await yukleyici();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenenDiller.add(d);
  }
}

const DIL_ANAHTARI = 'mk-egitim-dil';
/** Bu cihazda açılmış öğrenci bağlantıları (yalnız tarayıcıda; sınıftaki QR yoklaması için). */
const JETON_ANAHTARI = 'mk-egitim-jetonlar';

export type EgitimGorunumu = 'kurs' | 'ogrenci' | 'yoklama' | 'sertifika' | 'okut' | 'kurum';
type Bicim = 'yuz_yuze' | 'online' | 'karma';
type Yukleme = 'yukleniyor' | 'hazir' | 'yok' | 'pasif' | 'suresi' | 'kapandi' | 'gecersiz' | 'hata';

interface AcikKurs {
  slug: string;
  ad: string;
  ozet: string;
  aciklama: string;
  renk: string;
  egitmenler: string[];
  bicim: Bicim;
  mekan: string;
  adres: string;
  saat_dilimi: string;
  baslangic_tarihi: string | null;
  bitis_tarihi: string | null;
  kapasite: number | null;
  fiyat_metni: string;
  durum: 'yayinda' | 'tamamlandi';
  hedef_kitle: 'yetiskin' | 'cocuk' | 'karma';
  telefon: 'gizli' | 'istege_bagli' | 'zorunlu';
  dil: EtkinlikDili;
  kvkk_metni: string;
  ders_sayisi: number;
  program: { baslangic: string; bitis: string; konu: string }[];
  sertifika: boolean;
  indekslenebilir: boolean;
  pazarlama_metinleri: Record<string, string>;
  kayit_acik: boolean;
  kayit_neden: string | null;
  kalan: number | null;
  dolu: boolean;
  bekleme_listesi: boolean;
}

interface Kosul {
  deger: number | null;
  esik: number;
  tamam: boolean;
}

interface Istatistik {
  ilerleme: number;
  tamamlanan_ders: number;
  ders_sayisi: number;
  quiz_ortalama: number | null;
  yoklama: number | null;
  devamsizlik: number;
  kosullar: { ilerleme: Kosul; quiz: Kosul; yoklama: Kosul };
  uygun: boolean;
}

interface PortalQuiz {
  id: number;
  tur: 'quiz' | 'odev';
  baslik: string;
  aciklama: string;
  ders_id: number | null;
  soru_sayisi: number;
  sure_dk: number | null;
  gecme_puani: number;
  son_tarih: string | null;
  deneme?: number;
  deneme_hakki?: number;
  en_iyi?: number | null;
  gecti?: boolean;
  devam_eden?: number | null;
  teslim?: { id: number; metin: string; teslim_at: string; puan: number | null; geri_bildirim: string; notlandi_at: string | null; dosyalar: { id: number; ad: string }[] } | null;
}

interface PortalVerisi {
  ogrenci: { ad: string; kod: string; durum: 'aktif' | 'bekleme'; sira: number | null; dil: string; qr: string };
  kurs: {
    ad: string;
    slug: string;
    ozet: string;
    aciklama: string;
    renk: string;
    egitmenler: string[];
    bicim: Bicim;
    mekan: string;
    adres: string;
    online_baglanti: string;
    saat_dilimi: string;
    dil: string;
    baslangic_tarihi: string | null;
    bitis_tarihi: string | null;
    fiyat_metni: string;
    sertifika: boolean;
  };
  program: { id: number; baslangic: string; bitis: string; konu: string; durum: 'planli' | 'iptal'; yoklama: string | null; yoklama_acik: boolean }[];
  dersler: { id: number; bolum: string; baslik: string; sure_dk: number | null; tamamlandi: boolean; video: boolean }[];
  quizler: PortalQuiz[];
  istatistik: Istatistik;
  sertifika: { kod: string; kod_yazi: string; verilme_at: string; pdf: string; dogrulama: string } | null;
  duyurular: { konu: string; metin: string; created_at: string }[];
  takvim: string;
}

interface DersAyrintisi {
  id: number;
  baslik: string;
  bolum: string;
  icerik: string;
  video: { saglayici: 'youtube' | 'vimeo' | 'baglanti'; kimlik: string | null; adres: string } | null;
  sure_dk: number | null;
  dosyalar: { id: number; ad: string; tur: string; boyut: number }[];
  tamamlandi: boolean;
}

interface CozulecekSoru {
  id: string;
  tur: 'coktan' | 'dogru_yanlis' | 'kisa';
  metin: string;
  secenekler?: string[];
  puan?: number;
}

// ---------------------------------------------------------------------------
// Ağ
// ---------------------------------------------------------------------------
async function getir<T>(yol: string): Promise<{ durum: number; veri: T | null; kod: string }> {
  try {
    const y = await fetch(`${api()}${yol}`, { headers: { accept: 'application/json' } });
    const g = await y.json().catch(() => null);
    return { durum: y.status, veri: y.ok ? (g as T) : null, kod: y.ok ? '' : y.status === 429 ? 'cok_hizli' : hataKodu(g) };
  } catch {
    return { durum: 0, veri: null, kod: 'ag' };
  }
}

async function gonder<T>(yol: string, govde: unknown, form = false): Promise<{ ok: boolean; durum: number; veri: T | null; kod: string; ek: Record<string, unknown> }> {
  try {
    const y = await fetch(`${api()}${yol}`, {
      method: 'POST',
      headers: form ? { accept: 'application/json' } : { 'Content-Type': 'application/json', accept: 'application/json' },
      body: form ? (govde as FormData) : JSON.stringify(govde),
    });
    const g = await y.json().catch(() => null);
    const detay = (g as { detail?: Record<string, unknown> } | null)?.detail;
    return { ok: y.ok, durum: y.status, veri: y.ok ? (g as T) : null, kod: y.ok ? '' : y.status === 429 ? 'cok_hizli' : hataKodu(g), ek: detay && typeof detay === 'object' ? detay : {} };
  } catch {
    return { ok: false, durum: 0, veri: null, kod: 'ag', ek: {} };
  }
}

function durumYukleme(durum: number, kod: string): Yukleme {
  if (durum === 404) return kod === 'baglanti_gecersiz' ? 'gecersiz' : 'yok';
  if (durum === 410) return kod === 'baglanti_suresi_doldu' ? 'suresi' : kod === 'kayit_kapandi' ? 'kapandi' : 'pasif';
  return 'hata';
}

function jetonlariOku(): string[] {
  try {
    const v = JSON.parse(depoOku(JETON_ANAHTARI) || '[]');
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, 8) : [];
  } catch {
    return [];
  }
}

function jetonSakla(jeton: string): void {
  depoYaz(JETON_ANAHTARI, JSON.stringify([jeton, ...jetonlariOku().filter((x) => x !== jeton)].slice(0, 8)));
}

/** "YYYY-MM-DD" (takvim günü) → yerel biçim. */
function gunYaz(gun: string | null | undefined, dil: string): string {
  if (!gun) return '';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${gun}T00:00:00Z`));
  } catch {
    return gun;
  }
}

function zamanYaz(iso: string | null | undefined, tz: string, dil: string): string {
  return tarihYaz(iso, tz, dil, { dateStyle: 'medium', timeStyle: 'short' });
}

const KART = 'rounded-2xl border border-zinc-200 bg-white shadow-sm';
const GIRDI = 'w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-base text-zinc-900';
const DUGME = 'inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors disabled:opacity-60';
const ANA_DUGME = `${DUGME} bg-blue-600 text-white hover:bg-blue-700`;
const IKINCIL_DUGME = `${DUGME} border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50`;

function hataYaz(t: TFunction, kod: string, ek: Record<string, unknown> = {}): string {
  return t(`egitimSayfa.hata.${kod}`, { ...ek, defaultValue: t('egitimSayfa.hata.genel') }) as string;
}

// ===========================================================================
// Kabuk: dil, belge başlığı/yönü/robots
// ===========================================================================
export default function EgitimSayfasi({ gorunum }: { gorunum: EgitimGorunumu }) {
  const p = useParams<{ slug: string; jeton: string; kod: string; kid: string; oid: string }>();
  const karanlik = gorunum === 'okut';
  const [dil, setDil] = useState<EtkinlikDili | null>(null);
  const [t, setT] = useState<TFunction | null>(null);
  const [baslik, setBaslik] = useState('');
  const [indeks, setIndeks] = useState(false);

  const hazirla = useCallback(async (yedek: string) => {
    const d = dilSec(sorgu('dil'), depoOku(DIL_ANAHTARI), yedek || 'tr');
    await paketYukle(d).catch(() => undefined);
    setDil(d);
    setT(() => i18n.getFixedT(d));
  }, []);

  const dilDegistir = useCallback(async (d: EtkinlikDili) => {
    await paketYukle(d).catch(() => undefined);
    depoYaz(DIL_ANAHTARI, d);
    setDil(d);
    setT(() => i18n.getFixedT(d));
  }, []);

  useEffect(() => {
    if (karanlik || gorunum === 'sertifika') void hazirla(i18n.language || 'tr');
  }, [karanlik, gorunum, hazirla]);

  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background, baslik: document.title };
    if (dil) {
      kok.lang = dil;
      kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    }
    document.body.style.background = karanlik ? '#09090b' : '#f6f7fb';
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      document.title = eski.baslik;
    };
  }, [dil, karanlik]);

  useEffect(() => {
    if (baslik) document.title = baslik;
    let etiket = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!etiket) {
      etiket = document.createElement('meta');
      etiket.name = 'robots';
      document.head.appendChild(etiket);
    }
    etiket.content = indeks && gorunum === 'kurs' ? 'index, follow' : 'noindex, nofollow';
  }, [baslik, indeks, gorunum]);

  const ortak = { t, dil: dil || 'tr', hazirla, setBaslik, setIndeks };

  let icerik: ReactNode;
  if (gorunum === 'kurs') icerik = <KursGorunum slug={p.slug || ''} {...ortak} />;
  else if (gorunum === 'ogrenci') icerik = <OgrenciGorunum jeton={p.jeton || ''} {...ortak} />;
  else if (gorunum === 'yoklama') icerik = <YoklamaGorunum jeton={p.jeton || ''} {...ortak} />;
  else if (gorunum === 'sertifika') icerik = <SertifikaGorunum kod={p.kod || ''} {...ortak} />;
  else if (gorunum === 'kurum') icerik = <KurumGorunum slug={p.slug || ''} {...ortak} />;
  else icerik = <OkutGorunum kid={Number(p.kid || 0)} oid={Number(p.oid || 0)} t={t} dil={dil || 'tr'} setBaslik={setBaslik} />;

  return (
    <div className={`${karanlik ? 'min-h-screen text-white' : 'min-h-screen px-3 py-6 text-zinc-900 sm:px-6 sm:py-10'}`} data-testid="egitim-sayfasi" data-gorunum={gorunum}>
      {icerik}
      {t && dil && (
        <footer className="mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-between gap-3 px-1 pb-4 text-xs text-zinc-500">
          <label className="inline-flex items-center gap-1.5">
            <Globe className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="sr-only">{t('egitimSayfa.dil')}</span>
            <select
              value={dil}
              onChange={(e) => void dilDegistir(e.target.value as EtkinlikDili)}
              className={`rounded-md border px-1.5 py-1 ${karanlik ? 'border-white/15 bg-zinc-900 text-zinc-200' : 'border-zinc-300 bg-white text-zinc-700'}`}
              data-testid="egitim-dil"
            >
              {ETKINLIK_DILLERI.map((d) => (
                <option key={d} value={d}>
                  {DIL_ADLARI[d]}
                </option>
              ))}
            </select>
          </label>
          <a href="/" className="hover:underline">
            {t('egitimSayfa.altBilgi')}
          </a>
        </footer>
      )}
    </div>
  );
}

interface OrtakOzellikler {
  t: TFunction | null;
  dil: string;
  hazirla: (yedek: string) => Promise<void>;
  setBaslik: (b: string) => void;
  setIndeks: (v: boolean) => void;
}

function Yukleniyor({ t }: { t: TFunction | null }) {
  return (
    <div className="flex min-h-[50vh] items-center justify-center" data-testid="egitim-yukleniyor">
      <Loader2 className="h-8 w-8 animate-spin text-zinc-400" aria-label={t ? t('egitimSayfa.yukleniyor') : undefined} />
    </div>
  );
}

function Durum({ t, durum }: { t: TFunction; durum: Yukleme }) {
  return (
    <div className="mx-auto max-w-md py-16 text-center" data-testid="egitim-durum" data-durum={durum}>
      <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden="true" />
      <p className="text-lg font-medium">{t(`egitimSayfa.yukleme.${durum}`)}</p>
    </div>
  );
}

function BicimRozeti({ t, bicim }: { t: TFunction; bicim: Bicim }) {
  const Ikon = bicim === 'online' ? Video : bicim === 'karma' ? Users : MapPin;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700">
      <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
      {t(`egitimSayfa.bicim.${bicim}`)}
    </span>
  );
}

function BilgiSatiri({ ikon: Ikon, children }: { ikon: typeof MapPin; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <Ikon className="mt-0.5 h-5 w-5 shrink-0 text-zinc-500" aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function Seridi({ renk }: { renk: string }) {
  return <div className="h-2 rounded-t-2xl" style={{ background: renk || '#2563eb' }} aria-hidden="true" />;
}

// ===========================================================================
// Kurs + kayıt
// ===========================================================================
function KursGorunum({ slug, t, dil, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { slug: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [k, setK] = useState<AcikKurs | null>(null);
  const [cocukSecimi, setCocukSecimi] = useState(false);
  const [f, setF] = useState({ ad: '', eposta: '', telefon: '', veli_ad: '', veli_eposta: '', veli_telefon: '' });
  const [izin, setIzin] = useState(false);
  const [balKupu, setBalKupu] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [sonuc, setSonuc] = useState<{ durum: 'aktif' | 'bekleme' | null; portal: string | null; sira: number | null } | null>(null);

  const yukle = useCallback(async () => {
    const y = await getir<AcikKurs>(`/api/v1/egitim/kurs/${encodeURIComponent(slug)}`);
    await hazirla(y.veri?.dil || 'tr');
    if (!y.veri) {
      setYukleme(durumYukleme(y.durum, y.kod));
      return;
    }
    setK(y.veri);
    setBaslik(y.veri.ad);
    setIndeks(!!y.veri.indekslenebilir);
    setYukleme('hazir');
  }, [slug, hazirla, setBaslik, setIndeks]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !k) return <Durum t={t} durum={yukleme} />;

  const cocuk = k.hedef_kitle === 'cocuk' || (k.hedef_kitle === 'karma' && cocukSecimi);
  const pazarlamaMetni = cocuk ? '' : k.pazarlama_metinleri[dil] || k.pazarlama_metinleri.tr || '';
  const beklemeyeKayit = k.dolu && k.bekleme_listesi;
  const formAcik = k.kayit_acik && (!k.dolu || k.bekleme_listesi);
  const alan = (ad: keyof typeof f) => ({ value: f[ad], onChange: (x: { target: { value: string } }) => setF({ ...f, [ad]: x.target.value }) });

  const kayitGonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (gonderiliyor) return;
    setHata(null);
    setGonderiliyor(true);
    const y = await gonder<{ ok: boolean; durum: 'aktif' | 'bekleme' | null; portal_adresi?: string; sira?: number }>(`/api/v1/egitim/kurs/${encodeURIComponent(k.slug)}/kayit`, {
      ad: f.ad,
      eposta: f.eposta,
      telefon: k.telefon === 'gizli' ? undefined : f.telefon,
      cocuk,
      ...(cocuk ? { veli_ad: f.veli_ad, veli_eposta: f.veli_eposta, veli_telefon: k.telefon === 'gizli' ? undefined : f.veli_telefon } : {}),
      pazarlama_izni: !cocuk && izin,
      dil,
      web_adresi: balKupu,
    });
    setGonderiliyor(false);
    if (!y.ok || !y.veri) {
      setHata(hataYaz(t, y.kod, y.ek));
      if (y.kod === 'dolu') void yukle();
      return;
    }
    const portal = y.veri.portal_adresi || null;
    if (portal) jetonSakla(portal.split('/').pop() || '');
    setSonuc({ durum: y.veri.durum, portal, sira: y.veri.sira ?? null });
    window.scrollTo?.({ top: 0 });
  };

  const tz = k.saat_dilimi;
  return (
    <main className="mx-auto max-w-3xl space-y-4" data-testid="egitim-kurs-sayfasi">
      {sonuc && (
        <section className={`${KART} border-emerald-200 bg-emerald-50 p-5`} role="status" data-testid="egitim-kayit-tamam" data-durum={sonuc.durum || ''}>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-emerald-900">
            <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
            {sonuc.durum === 'bekleme' ? t('egitimSayfa.tamam.bekleme', { sira: sonuc.sira ?? 1 }) : t('egitimSayfa.tamam.baslik')}
          </h2>
          <p className="mt-1 text-sm text-emerald-900/80">{t('egitimSayfa.tamam.metin')}</p>
          {sonuc.portal && (
            <a href={sonuc.portal} className={`${ANA_DUGME} mt-3`} data-testid="egitim-portal-git">
              <GraduationCap className="h-4 w-4" aria-hidden="true" />
              {t('egitimSayfa.tamam.portal')}
            </a>
          )}
        </section>
      )}
      <article className={KART}>
        <Seridi renk={k.renk} />
        <div className="space-y-4 p-5 sm:p-7">
          <div className="flex flex-wrap gap-1.5">
            <BicimRozeti t={t} bicim={k.bicim} />
            {k.hedef_kitle !== 'yetiskin' && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">{t(`egitimSayfa.hedef.${k.hedef_kitle}`)}</span>}
            {k.sertifika && (
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800">
                <Award className="h-3.5 w-3.5" aria-hidden="true" />
                {t('egitimSayfa.kurs.sertifikali')}
              </span>
            )}
            {k.durum === 'tamamlandi' && <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700">{t('egitimSayfa.kurs.tamamlandi')}</span>}
          </div>
          <h1 className="text-2xl font-bold leading-tight sm:text-3xl" data-testid="egitim-kurs-adi">
            {k.ad}
          </h1>
          {k.ozet && <p className="text-zinc-600">{k.ozet}</p>}
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            {(k.baslangic_tarihi || k.bitis_tarihi) && (
              <BilgiSatiri ikon={CalendarDays}>
                <div className="font-medium">
                  {gunYaz(k.baslangic_tarihi, dil)}
                  {k.bitis_tarihi && k.bitis_tarihi !== k.baslangic_tarihi ? ` – ${gunYaz(k.bitis_tarihi, dil)}` : ''}
                </div>
                {k.ders_sayisi > 0 && <div className="text-xs text-zinc-500">{t('egitimSayfa.kurs.dersSayisi', { sayi: k.ders_sayisi })}</div>}
              </BilgiSatiri>
            )}
            {k.egitmenler.length > 0 && (
              <BilgiSatiri ikon={GraduationCap}>
                <div className="text-xs text-zinc-500">{t('egitimSayfa.kurs.egitmen')}</div>
                <div className="font-medium">{k.egitmenler.join(', ')}</div>
              </BilgiSatiri>
            )}
            {k.bicim !== 'online' && (k.mekan || k.adres) && (
              <BilgiSatiri ikon={MapPin}>
                {k.mekan && <div className="font-medium">{k.mekan}</div>}
                {k.adres && <div className="whitespace-pre-line text-zinc-600">{k.adres}</div>}
              </BilgiSatiri>
            )}
            {k.bicim !== 'yuz_yuze' && (
              <BilgiSatiri ikon={Video}>
                <span className="text-zinc-600">{t('egitimSayfa.kurs.onlineNot')}</span>
              </BilgiSatiri>
            )}
            {k.fiyat_metni && (
              <BilgiSatiri ikon={FileText}>
                <div className="text-xs text-zinc-500">{t('egitimSayfa.kurs.ucret')}</div>
                <div className="font-medium" data-testid="egitim-fiyat">
                  {k.fiyat_metni}
                </div>
              </BilgiSatiri>
            )}
            {k.kapasite != null && (
              <BilgiSatiri ikon={Users}>
                <span className={k.dolu ? 'font-medium text-amber-700' : 'text-zinc-700'}>
                  {k.dolu ? t('egitimSayfa.kurs.dolu') : t('egitimSayfa.kurs.kalan', { sayi: k.kalan ?? 0 })}
                </span>
              </BilgiSatiri>
            )}
          </div>
          {k.aciklama && (
            <div className="border-t border-zinc-100 pt-4 text-[15px] leading-relaxed text-zinc-800">
              <GuvenliMarkdown metin={k.aciklama} className="space-y-3" />
            </div>
          )}
        </div>
      </article>

      {k.program.length > 0 && (
        <section className={`${KART} p-5 sm:p-7`}>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
            <CalendarDays className="h-5 w-5 text-blue-600" aria-hidden="true" />
            {t('egitimSayfa.kurs.program')}
          </h2>
          <ul className="space-y-1.5 text-sm" data-testid="egitim-program">
            {k.program.map((o, i) => (
              <li key={i} className="flex flex-wrap gap-x-2">
                <span className="font-medium">{aralikYaz(o.baslangic, o.bitis, tz, dil)}</span>
                {o.konu && <span className="text-zinc-600">· {o.konu}</span>}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-zinc-500">{t('egitimSayfa.saatDilimi', { tz: tz.replace(/_/g, ' ') })}</p>
        </section>
      )}

      {!sonuc && (
        <section className={`${KART} p-5 sm:p-7`} aria-labelledby="egitim-kayit-baslik">
          <h2 id="egitim-kayit-baslik" className="mb-1 text-lg font-semibold">
            {beklemeyeKayit ? t('egitimSayfa.kayit.beklemeBaslik') : t('egitimSayfa.kayit.baslik')}
          </h2>
          {!k.kayit_acik ? (
            <p className="text-sm text-zinc-600" data-testid="egitim-kayit-kapali">
              {t(`egitimSayfa.kayit.${k.kayit_neden || 'kayit_kapali'}`)}
            </p>
          ) : !formAcik ? (
            <p className="text-sm text-amber-700" data-testid="egitim-kayit-dolu">
              {t('egitimSayfa.kurs.dolu')}
            </p>
          ) : (
            <form onSubmit={kayitGonder} className="relative mt-3 space-y-4" data-testid="egitim-kayit-formu">
              {beklemeyeKayit && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{t('egitimSayfa.kayit.beklemeNotu')}</p>}
              {k.hedef_kitle === 'karma' && (
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={cocukSecimi} onChange={(x) => setCocukSecimi(x.target.checked)} className="mt-0.5 h-4 w-4 accent-blue-600" data-testid="egitim-cocuk" />
                  <span>{t('egitimSayfa.kayit.cocukSecimi')}</span>
                </label>
              )}
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm">
                  <span className="mb-1 block font-medium">{cocuk ? t('egitimSayfa.kayit.ogrenciAdi') : t('egitimSayfa.kayit.ad')}</span>
                  <input required maxLength={120} autoComplete={cocuk ? 'off' : 'name'} className={GIRDI} data-testid="egitim-ad" {...alan('ad')} />
                </label>
                <label className="block text-sm">
                  <span className="mb-1 block font-medium">
                    {t('egitimSayfa.kayit.eposta')}
                    {cocuk && <span className="font-normal text-zinc-500"> ({t('egitimSayfa.kayit.istegeBagli')})</span>}
                  </span>
                  <input required={!cocuk} type="email" maxLength={254} autoComplete={cocuk ? 'off' : 'email'} className={GIRDI} dir="ltr" data-testid="egitim-eposta" {...alan('eposta')} />
                </label>
                {k.telefon !== 'gizli' && !cocuk && (
                  <label className="block text-sm sm:col-span-2">
                    <span className="mb-1 block font-medium">
                      {t('egitimSayfa.kayit.telefon')}
                      {k.telefon === 'istege_bagli' && <span className="font-normal text-zinc-500"> ({t('egitimSayfa.kayit.istegeBagli')})</span>}
                    </span>
                    <input required={k.telefon === 'zorunlu'} type="tel" maxLength={24} autoComplete="tel" className={GIRDI} dir="ltr" data-testid="egitim-telefon" {...alan('telefon')} />
                  </label>
                )}
              </div>
              {cocuk && (
                <fieldset className="grid gap-3 rounded-xl border border-zinc-200 p-4 sm:grid-cols-2" data-testid="egitim-veli">
                  <legend className="px-1 text-sm font-semibold">{t('egitimSayfa.kayit.veliBaslik')}</legend>
                  <p className="text-xs text-zinc-500 sm:col-span-2">{t('egitimSayfa.kayit.veliNotu')}</p>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium">{t('egitimSayfa.kayit.veliAd')}</span>
                    <input required maxLength={120} autoComplete="name" className={GIRDI} data-testid="egitim-veli-ad" {...alan('veli_ad')} />
                  </label>
                  <label className="block text-sm">
                    <span className="mb-1 block font-medium">{t('egitimSayfa.kayit.veliEposta')}</span>
                    <input required type="email" maxLength={254} autoComplete="email" className={GIRDI} dir="ltr" data-testid="egitim-veli-eposta" {...alan('veli_eposta')} />
                  </label>
                  {k.telefon !== 'gizli' && (
                    <label className="block text-sm sm:col-span-2">
                      <span className="mb-1 block font-medium">
                        {t('egitimSayfa.kayit.veliTelefon')}
                        {k.telefon === 'istege_bagli' && <span className="font-normal text-zinc-500"> ({t('egitimSayfa.kayit.istegeBagli')})</span>}
                      </span>
                      <input required={k.telefon === 'zorunlu'} type="tel" maxLength={24} autoComplete="tel" className={GIRDI} dir="ltr" {...alan('veli_telefon')} />
                    </label>
                  )}
                </fieldset>
              )}
              {/* Bal küpü: insan görmez, bot doldurur (sunucu sessizce yok sayar). Sayfanın dışına itilmiyor:
                  sağdan sola (ar) düzende negatif konum yatay kaydırma açıyordu. */}
              <div className="sr-only" aria-hidden="true">
                <label>
                  Web
                  <input tabIndex={-1} autoComplete="off" value={balKupu} onChange={(x) => setBalKupu(x.target.value)} name="web_adresi" />
                </label>
              </div>
              {pazarlamaMetni && (
                <label className="flex items-start gap-2 text-sm text-zinc-700">
                  <input type="checkbox" checked={izin} onChange={(x) => setIzin(x.target.checked)} className="mt-0.5 h-4 w-4 accent-blue-600" data-testid="egitim-pazarlama-izni" />
                  <span>
                    {pazarlamaMetni} <span className="text-zinc-500">({t('egitimSayfa.kayit.istegeBagli')})</span>
                  </span>
                </label>
              )}
              <details className="rounded-xl bg-zinc-50 p-3 text-xs text-zinc-600" data-testid="egitim-kvkk">
                <summary className="cursor-pointer font-medium text-zinc-700">{t('egitimSayfa.kayit.kvkkBaslik')}</summary>
                <p className="mt-2 whitespace-pre-line">{k.kvkk_metni || t('egitimSayfa.kayit.kvkk')}</p>
                {cocuk && <p className="mt-2">{t('egitimSayfa.kayit.kvkkCocuk')}</p>}
              </details>
              {hata && (
                <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert" data-testid="egitim-kayit-hata">
                  {hata}
                </p>
              )}
              <button type="submit" disabled={gonderiliyor} className={`${ANA_DUGME} w-full sm:w-auto`} data-testid="egitim-kayit-gonder">
                {gonderiliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {beklemeyeKayit ? t('egitimSayfa.kayit.beklemeyeKatil') : t('egitimSayfa.kayit.gonder')}
              </button>
            </form>
          )}
        </section>
      )}
    </main>
  );
}

// ===========================================================================
// Öğrenci sayfası (imzalı bağlantı)
// ===========================================================================
type PortalSekme = 'ozet' | 'dersler' | 'quiz' | 'program';

function OgrenciGorunum({ jeton, t, dil, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { jeton: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [v, setV] = useState<PortalVerisi | null>(null);
  const [sekme, setSekme] = useState<PortalSekme>('ozet');
  const [ders, setDers] = useState<number | null>(null);
  const [quiz, setQuiz] = useState<PortalQuiz | null>(null);
  const taban = `/api/v1/egitim/ogrenci/${encodeURIComponent(jeton)}`;

  const yukle = useCallback(async () => {
    const y = await getir<PortalVerisi>(taban);
    await hazirla(y.veri?.ogrenci.dil || y.veri?.kurs.dil || 'tr');
    setIndeks(false);
    if (!y.veri) {
      setYukleme(durumYukleme(y.durum, y.kod));
      return;
    }
    jetonSakla(jeton);
    setV(y.veri);
    setBaslik(y.veri.kurs.ad);
    setYukleme('hazir');
  }, [taban, jeton, hazirla, setBaslik, setIndeks]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !v) return <Durum t={t} durum={yukleme} />;

  const tz = v.kurs.saat_dilimi;
  const aktif = v.ogrenci.durum === 'aktif';
  const ist = v.istatistik;
  const sekmeler: { anahtar: PortalSekme; ikon: typeof BookOpen }[] = aktif
    ? [
        { anahtar: 'ozet', ikon: GraduationCap },
        { anahtar: 'dersler', ikon: BookOpen },
        { anahtar: 'quiz', ikon: ClipboardCheck },
        { anahtar: 'program', ikon: CalendarDays },
      ]
    : [];

  return (
    <main className="mx-auto max-w-3xl space-y-4" data-testid="egitim-portal" data-durum={v.ogrenci.durum}>
      <header className={KART}>
        <Seridi renk={v.kurs.renk} />
        <div className="flex flex-wrap items-center gap-3 p-5">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-zinc-500">{t('egitimSayfa.portal.merhaba', { ad: v.ogrenci.ad })}</p>
            <h1 className="text-xl font-bold leading-tight sm:text-2xl" data-testid="egitim-portal-kurs">
              {v.kurs.ad}
            </h1>
            {v.kurs.egitmenler.length > 0 && <p className="mt-0.5 text-sm text-zinc-600">{v.kurs.egitmenler.join(', ')}</p>}
          </div>
          {aktif && (
            <div className="text-end">
              <div className="text-2xl font-bold text-blue-700" data-testid="egitim-portal-ilerleme">
                %{ist.ilerleme}
              </div>
              <div className="text-xs text-zinc-500">{t('egitimSayfa.portal.ilerleme')}</div>
            </div>
          )}
        </div>
      </header>

      {!aktif && (
        <section className={`${KART} border-amber-200 bg-amber-50 p-5`} data-testid="egitim-portal-bekleme">
          <h2 className="font-semibold text-amber-900">{t('egitimSayfa.portal.beklemeBaslik', { sira: v.ogrenci.sira ?? 1 })}</h2>
          <p className="mt-1 text-sm text-amber-900/80">{t('egitimSayfa.portal.beklemeMetin')}</p>
        </section>
      )}

      {sekmeler.length > 0 && (
        <nav className="flex gap-1 overflow-x-auto rounded-2xl border border-zinc-200 bg-white p-1" role="tablist" aria-label={v.kurs.ad}>
          {sekmeler.map(({ anahtar, ikon: Ikon }) => (
            <button
              key={anahtar}
              type="button"
              role="tab"
              aria-selected={sekme === anahtar}
              onClick={() => {
                setSekme(anahtar);
                setDers(null);
                setQuiz(null);
              }}
              className={`flex flex-none items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium ${sekme === anahtar ? 'bg-blue-600 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`}
              data-portal-sekme={anahtar}
            >
              <Ikon className="h-4 w-4" aria-hidden="true" />
              {t(`egitimSayfa.portal.sekme.${anahtar}`)}
            </button>
          ))}
        </nav>
      )}

      {(!aktif || sekme === 'ozet') && <PortalOzet t={t} dil={dil} v={v} taban={taban} onYenile={yukle} />}
      {aktif && sekme === 'program' && <PortalProgram t={t} dil={dil} v={v} taban={taban} />}
      {aktif && sekme === 'dersler' &&
        (ders !== null ? (
          <DersGorunum t={t} taban={taban} did={ders} onGeri={() => setDers(null)} onDegisti={yukle} />
        ) : (
          <DersListesi t={t} v={v} onAc={setDers} />
        ))}
      {aktif && sekme === 'quiz' &&
        (quiz ? (
          quiz.tur === 'quiz' ? (
            <QuizCoz t={t} taban={taban} q={quiz} onGeri={() => setQuiz(null)} onBitti={yukle} />
          ) : (
            <OdevTeslim t={t} dil={dil} tz={tz} taban={taban} q={quiz} onGeri={() => setQuiz(null)} onBitti={yukle} />
          )
        ) : (
          <QuizListesi t={t} dil={dil} tz={tz} v={v} onAc={setQuiz} />
        ))}
    </main>
  );
}

function KosulSatiri({ t, ad, k, yuzde }: { t: TFunction; ad: string; k: Kosul; yuzde: boolean }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {k.tamam ? <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" /> : <Circle className="h-4 w-4 text-zinc-300" aria-hidden="true" />}
      <span className="flex-1">{t(`egitimSayfa.portal.kosul.${ad}`)}</span>
      <span className="font-medium tabular-nums">
        {k.deger == null ? '—' : yuzde ? `%${k.deger}` : k.deger} / {yuzde ? `%${k.esik}` : k.esik}
      </span>
    </li>
  );
}

function PortalOzet({ t, dil, v, taban, onYenile }: { t: TFunction; dil: string; v: PortalVerisi; taban: string; onYenile: () => Promise<void> }) {
  const tz = v.kurs.saat_dilimi;
  const aktif = v.ogrenci.durum === 'aktif';
  const [kod, setKod] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [yoklamaSonucu, setYoklamaSonucu] = useState<{ ok: boolean; metin: string } | null>(null);
  const acikOturum = v.program.find((o) => o.yoklama_acik);
  const sonraki = v.program.find((o) => o.durum === 'planli' && new Date(o.bitis).getTime() > Date.now());

  const yoklamaGonder = async (olay: FormEvent) => {
    olay.preventDefault();
    setMesgul(true);
    const y = await gonder<{ sonuc: 'isaretlendi' | 'zaten'; durum: string }>(`${taban}/yoklama`, { kod });
    setMesgul(false);
    if (!y.ok || !y.veri) {
      setYoklamaSonucu({ ok: false, metin: hataYaz(t, y.kod, y.ek) });
      return;
    }
    setKod('');
    setYoklamaSonucu({ ok: true, metin: y.veri.sonuc === 'zaten' ? t('egitimSayfa.yoklama.zaten') : t(`egitimSayfa.yoklama.isaretlendi_${y.veri.durum === 'gec' ? 'gec' : 'var'}`) });
    await onYenile();
  };

  return (
    <div className="space-y-4">
      {aktif && (
        <section className={`${KART} p-5`} data-testid="egitim-portal-yoklama">
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <ClipboardCheck className="h-5 w-5 text-blue-600" aria-hidden="true" />
            {t('egitimSayfa.yoklama.baslik')}
          </h2>
          {acikOturum ? (
            <form onSubmit={yoklamaGonder} className="flex flex-wrap items-end gap-2">
              <label className="block min-w-[10rem] flex-1 text-sm">
                <span className="mb-1 block text-zinc-600">{t('egitimSayfa.yoklama.kodEtiket')}</span>
                <input
                  value={kod}
                  onChange={(x) => setKod(x.target.value.toUpperCase())}
                  maxLength={8}
                  autoComplete="off"
                  inputMode="text"
                  className={`${GIRDI} font-mono tracking-[0.3em]`}
                  dir="ltr"
                  required
                  data-testid="egitim-yoklama-kod"
                />
              </label>
              <button type="submit" disabled={mesgul || kod.trim().length < 4} className={ANA_DUGME} data-testid="egitim-yoklama-gonder">
                {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('egitimSayfa.yoklama.gonder')}
              </button>
            </form>
          ) : (
            <p className="text-sm text-zinc-600">{t('egitimSayfa.yoklama.kapali')}</p>
          )}
          {yoklamaSonucu && (
            <p className={`mt-2 rounded-xl p-3 text-sm ${yoklamaSonucu.ok ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-700'}`} role="status" data-testid="egitim-yoklama-sonuc" data-ok={yoklamaSonucu.ok ? '1' : '0'}>
              {yoklamaSonucu.metin}
            </p>
          )}
          <details className="mt-3 text-sm">
            <summary className="flex cursor-pointer items-center gap-1.5 text-zinc-600">
              <QrCode className="h-4 w-4" aria-hidden="true" />
              {t('egitimSayfa.yoklama.qrBaslik')}
            </summary>
            <div className="mt-3 flex flex-wrap items-center gap-4">
              <img src={`${api()}${v.ogrenci.qr}`} alt={t('egitimSayfa.yoklama.qrAlt')} width={160} height={160} className="h-40 w-40 rounded-xl border border-zinc-200 bg-white p-2" loading="lazy" />
              <div>
                <p className="text-xs text-zinc-500">{t('egitimSayfa.yoklama.qrNot')}</p>
                <code className="mt-1 block text-lg font-bold tracking-[0.2em]" dir="ltr" data-testid="egitim-ogrenci-kod">
                  {v.ogrenci.kod}
                </code>
              </div>
            </div>
          </details>
        </section>
      )}

      {aktif && v.kurs.sertifika && (
        <section className={`${KART} p-5`} data-testid="egitim-portal-sertifika">
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <Award className="h-5 w-5 text-blue-600" aria-hidden="true" />
            {t('egitimSayfa.sertifika.baslik')}
          </h2>
          {v.sertifika ? (
            <div className="space-y-2">
              <p className="text-sm text-emerald-800">{t('egitimSayfa.sertifika.hazir', { tarih: tarihYaz(v.sertifika.verilme_at, tz, dil, { dateStyle: 'medium' }) })}</p>
              <div className="flex flex-wrap gap-2">
                <a href={`${api()}${v.sertifika.pdf}`} className={ANA_DUGME} data-testid="egitim-sertifika-indir" rel="noreferrer">
                  <Download className="h-4 w-4" aria-hidden="true" />
                  {t('egitimSayfa.sertifika.indir')}
                </a>
                <a href={v.sertifika.dogrulama} target="_blank" rel="noopener" className={IKINCIL_DUGME} data-testid="egitim-sertifika-dogrulama">
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                  {t('egitimSayfa.sertifika.dogrulama')}
                </a>
              </div>
              <p className="text-xs text-zinc-500" dir="ltr">
                {v.sertifika.kod_yazi}
              </p>
            </div>
          ) : (
            <>
              <p className="mb-2 text-sm text-zinc-600">{v.istatistik.uygun ? t('egitimSayfa.sertifika.uygun') : t('egitimSayfa.sertifika.kosullar')}</p>
              <ul className="space-y-1.5">
                <KosulSatiri t={t} ad="ilerleme" k={v.istatistik.kosullar.ilerleme} yuzde />
                <KosulSatiri t={t} ad="quiz" k={v.istatistik.kosullar.quiz} yuzde={false} />
                <KosulSatiri t={t} ad="yoklama" k={v.istatistik.kosullar.yoklama} yuzde />
              </ul>
            </>
          )}
        </section>
      )}

      <section className={`${KART} space-y-3 p-5 text-sm`}>
        {sonraki && (
          <BilgiSatiri ikon={Clock}>
            <div className="text-xs text-zinc-500">{t('egitimSayfa.portal.sonrakiDers')}</div>
            <div className="font-medium" data-testid="egitim-sonraki-ders">
              {aralikYaz(sonraki.baslangic, sonraki.bitis, tz, dil)}
              {sonraki.konu ? ` · ${sonraki.konu}` : ''}
            </div>
          </BilgiSatiri>
        )}
        {v.kurs.bicim !== 'online' && (v.kurs.mekan || v.kurs.adres) && (
          <BilgiSatiri ikon={MapPin}>
            {v.kurs.mekan && <div className="font-medium">{v.kurs.mekan}</div>}
            {v.kurs.adres && <div className="whitespace-pre-line text-zinc-600">{v.kurs.adres}</div>}
          </BilgiSatiri>
        )}
        {v.kurs.online_baglanti && (
          <BilgiSatiri ikon={Video}>
            <a href={v.kurs.online_baglanti} target="_blank" rel="noopener noreferrer" className="break-all font-medium text-blue-700 underline" dir="ltr">
              {v.kurs.online_baglanti}
            </a>
          </BilgiSatiri>
        )}
        <a href={`${api()}${v.takvim}`} className={IKINCIL_DUGME} data-testid="egitim-takvim">
          <CalendarPlus className="h-4 w-4" aria-hidden="true" />
          {t('egitimSayfa.portal.takvim')}
        </a>
      </section>

      {v.duyurular.length > 0 && (
        <section className={`${KART} p-5`}>
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <Megaphone className="h-5 w-5 text-blue-600" aria-hidden="true" />
            {t('egitimSayfa.portal.duyurular')}
          </h2>
          <ul className="divide-y divide-zinc-100">
            {v.duyurular.map((d, i) => (
              <li key={i} className="py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{d.konu}</span>
                  <span className="text-xs text-zinc-500">{zamanYaz(d.created_at, tz, dil)}</span>
                </div>
                <p className="mt-0.5 whitespace-pre-line text-sm text-zinc-700">{d.metin}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="px-1 text-xs text-zinc-500">{t('egitimSayfa.portal.gizlilik')}</p>
    </div>
  );
}

const YOKLAMA_RENGI: Record<string, string> = {
  var: 'bg-emerald-50 text-emerald-800',
  gec: 'bg-amber-50 text-amber-800',
  yok: 'bg-red-50 text-red-700',
  izinli: 'bg-sky-50 text-sky-800',
};

function PortalProgram({ t, dil, v }: { t: TFunction; dil: string; v: PortalVerisi; taban: string }) {
  const tz = v.kurs.saat_dilimi;
  return (
    <section className={`${KART} p-5`} data-testid="egitim-portal-program">
      <h2 className="mb-3 font-semibold">{t('egitimSayfa.portal.sekme.program')}</h2>
      {v.program.length === 0 ? (
        <p className="text-sm text-zinc-500">{t('egitimSayfa.portal.programBos')}</p>
      ) : (
        <ul className="divide-y divide-zinc-100 text-sm">
          {v.program.map((o) => (
            <li key={o.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className={`flex-1 ${o.durum === 'iptal' ? 'text-zinc-400 line-through' : ''}`}>
                <span className="font-medium">{aralikYaz(o.baslangic, o.bitis, tz, dil)}</span>
                {o.konu && <span className="text-zinc-600"> · {o.konu}</span>}
              </span>
              {o.durum === 'iptal' ? (
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">{t('egitimSayfa.portal.iptal')}</span>
              ) : o.yoklama ? (
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${YOKLAMA_RENGI[o.yoklama] || ''}`}>{t(`egitimSayfa.yoklamaDurum.${o.yoklama}`)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-zinc-500">{t('egitimSayfa.saatDilimi', { tz: tz.replace(/_/g, ' ') })}</p>
    </section>
  );
}

function DersListesi({ t, v, onAc }: { t: TFunction; v: PortalVerisi; onAc: (id: number) => void }) {
  const gruplar = useMemo(() => {
    const g: { bolum: string; dersler: PortalVerisi['dersler'] }[] = [];
    for (const d of v.dersler) {
      const son = g[g.length - 1];
      if (son && son.bolum === d.bolum) son.dersler.push(d);
      else g.push({ bolum: d.bolum, dersler: [d] });
    }
    return g;
  }, [v.dersler]);
  if (v.dersler.length === 0) return <p className={`${KART} p-6 text-center text-sm text-zinc-500`}>{t('egitimSayfa.ders.bos')}</p>;
  return (
    <section className={`${KART} p-5`} data-testid="egitim-ders-listesi">
      <p className="mb-3 text-sm text-zinc-600">{t('egitimSayfa.ders.ozet', { tamam: v.istatistik.tamamlanan_ders, toplam: v.istatistik.ders_sayisi })}</p>
      {gruplar.map((g, i) => (
        <div key={i} className="mb-3 last:mb-0">
          {g.bolum && <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">{g.bolum}</h3>}
          <ul className="divide-y divide-zinc-100">
            {g.dersler.map((d) => (
              <li key={d.id}>
                <button type="button" onClick={() => onAc(d.id)} className="flex w-full items-center gap-3 py-2.5 text-start hover:bg-zinc-50" data-testid="egitim-ders-ac" data-ders-id={d.id}>
                  {d.tamamlandi ? <CheckCircle2 className="h-5 w-5 flex-none text-emerald-600" aria-label={t('egitimSayfa.ders.tamamlandi')} /> : <Circle className="h-5 w-5 flex-none text-zinc-300" aria-hidden="true" />}
                  <span className="flex-1 font-medium">{d.baslik}</span>
                  {d.video && <PlayCircle className="h-4 w-4 text-zinc-400" aria-hidden="true" />}
                  {d.sure_dk ? <span className="text-xs text-zinc-500">{t('egitimSayfa.ders.dakika', { sayi: d.sure_dk })}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function DersGorunum({ t, taban, did, onGeri, onDegisti }: { t: TFunction; taban: string; did: number; onGeri: () => void; onDegisti: () => Promise<void> }) {
  const [d, setD] = useState<DersAyrintisi | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    let iptal = false;
    void getir<DersAyrintisi>(`${taban}/ders/${did}`).then((y) => {
      if (iptal) return;
      if (y.veri) setD(y.veri);
      else setHata(hataYaz(t, y.kod));
    });
    return () => {
      iptal = true;
    };
  }, [taban, did, t]);

  const isaretle = async () => {
    if (!d) return;
    setMesgul(true);
    const y = await gonder<{ tamamlandi: boolean }>(`${taban}/ders/${did}/tamamla`, { tamamlandi: !d.tamamlandi });
    setMesgul(false);
    if (!y.ok || !y.veri) {
      setHata(hataYaz(t, y.kod));
      return;
    }
    setD({ ...d, tamamlandi: y.veri.tamamlandi });
    await onDegisti();
  };

  return (
    <article className={`${KART} p-5`} data-testid="egitim-ders">
      <button type="button" onClick={onGeri} className="mb-3 text-sm text-blue-700 hover:underline">
        ← {t('egitimSayfa.geri')}
      </button>
      {hata && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{hata}</p>}
      {!d ? (
        !hata && <Loader2 className="mx-auto h-6 w-6 animate-spin text-zinc-400" aria-hidden="true" />
      ) : (
        <div className="space-y-4">
          <div>
            {d.bolum && <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{d.bolum}</p>}
            <h2 className="text-xl font-bold" data-testid="egitim-ders-baslik">
              {d.baslik}
            </h2>
          </div>
          {d.video && (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <a href={d.video.adres} target="_blank" rel="noopener noreferrer" className={ANA_DUGME} data-testid="egitim-ders-video">
                <PlayCircle className="h-4 w-4" aria-hidden="true" />
                {t(`egitimSayfa.ders.video_${d.video.saglayici}`)}
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
              <p className="mt-2 text-xs text-zinc-500">{t('egitimSayfa.ders.videoNot')}</p>
            </div>
          )}
          {d.icerik && (
            <div className="text-[15px] leading-relaxed text-zinc-800">
              <GuvenliMarkdown metin={d.icerik} className="space-y-3" />
            </div>
          )}
          {d.dosyalar.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-semibold">{t('egitimSayfa.ders.dosyalar')}</h3>
              <ul className="space-y-1 text-sm">
                {d.dosyalar.map((f) => (
                  <li key={f.id}>
                    <a href={`${api()}${taban}/dosya/${f.id}`} className="inline-flex items-center gap-1.5 text-blue-700 hover:underline" rel="noreferrer">
                      <Download className="h-4 w-4" aria-hidden="true" />
                      {f.ad}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button type="button" onClick={() => void isaretle()} disabled={mesgul} className={d.tamamlandi ? IKINCIL_DUGME : ANA_DUGME} data-testid="egitim-ders-tamamla" data-tamam={d.tamamlandi ? '1' : '0'}>
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
            {d.tamamlandi ? t('egitimSayfa.ders.isaretKaldir') : t('egitimSayfa.ders.tamamla')}
          </button>
        </div>
      )}
    </article>
  );
}

function QuizListesi({ t, dil, tz, v, onAc }: { t: TFunction; dil: string; tz: string; v: PortalVerisi; onAc: (q: PortalQuiz) => void }) {
  if (v.quizler.length === 0) return <p className={`${KART} p-6 text-center text-sm text-zinc-500`}>{t('egitimSayfa.quiz.bos')}</p>;
  return (
    <section className={`${KART} p-5`} data-testid="egitim-quiz-listesi">
      <ul className="divide-y divide-zinc-100">
        {v.quizler.map((q) => {
          const hakBitti = q.tur === 'quiz' && (q.deneme ?? 0) >= (q.deneme_hakki ?? 1) && !q.devam_eden;
          return (
            <li key={q.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600">{t(`egitimSayfa.quiz.tur_${q.tur}`)}</span>
                  <span className="font-medium">{q.baslik}</span>
                </div>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {q.tur === 'quiz'
                    ? [
                        t('egitimSayfa.quiz.soruSayisi', { sayi: q.soru_sayisi }),
                        q.sure_dk ? t('egitimSayfa.quiz.sure', { sayi: q.sure_dk }) : '',
                        t('egitimSayfa.quiz.deneme', { sayi: q.deneme ?? 0, hak: q.deneme_hakki ?? 1 }),
                        q.en_iyi != null ? t('egitimSayfa.quiz.enIyi', { puan: q.en_iyi }) : '',
                      ]
                        .filter(Boolean)
                        .join(' · ')
                    : [q.son_tarih ? t('egitimSayfa.quiz.sonTarih', { tarih: zamanYaz(q.son_tarih, tz, dil) }) : '', q.teslim ? (q.teslim.puan != null ? t('egitimSayfa.odev.notu', { puan: q.teslim.puan }) : t('egitimSayfa.odev.teslimEdildi')) : '']
                        .filter(Boolean)
                        .join(' · ')}
                </p>
              </div>
              {q.tur === 'quiz' && q.gecti && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800">{t('egitimSayfa.quiz.gecti')}</span>}
              <button type="button" onClick={() => onAc(q)} disabled={hakBitti} className={IKINCIL_DUGME} data-testid="egitim-quiz-ac" data-quiz-id={q.id}>
                {q.tur === 'odev' ? t('egitimSayfa.odev.ac') : q.devam_eden ? t('egitimSayfa.quiz.devam') : hakBitti ? t('egitimSayfa.quiz.hakBitti') : t('egitimSayfa.quiz.basla')}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function QuizCoz({ t, taban, q, onGeri, onBitti }: { t: TFunction; taban: string; q: PortalQuiz; onGeri: () => void; onBitti: () => Promise<void> }) {
  const [deneme, setDeneme] = useState<{ deneme_id: number; son_at: string | null; sunucu_saati: string; sorular: CozulecekSoru[]; aciklama: string } | null>(null);
  const [yanitlar, setYanitlar] = useState<Record<string, unknown>>({});
  const [hata, setHata] = useState<string | null>(null);
  const [kalan, setKalan] = useState<number | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [sonuc, setSonuc] = useState<{ durum: string; puan: number; dogru: number; toplam: number; gecti: boolean } | null>(null);
  const fark = useRef(0);
  const gonderildi = useRef(false);

  useEffect(() => {
    let iptal = false;
    void gonder<{ deneme_id: number; son_at: string | null; sunucu_saati: string; sorular: CozulecekSoru[]; aciklama: string }>(`${taban}/quiz/${q.id}/basla`, {}).then((y) => {
      if (iptal) return;
      if (!y.ok || !y.veri) {
        setHata(hataYaz(t, y.kod, y.ek));
        return;
      }
      fark.current = new Date(y.veri.sunucu_saati).getTime() - Date.now();
      setDeneme(y.veri);
    });
    return () => {
      iptal = true;
    };
  }, [taban, q.id, t]);

  const bitir = useCallback(async () => {
    if (!deneme || gonderildi.current) return;
    gonderildi.current = true;
    setMesgul(true);
    const y = await gonder<{ durum: string; puan: number; dogru: number; toplam: number; gecti: boolean }>(`${taban}/quiz/${q.id}/gonder`, { deneme_id: deneme.deneme_id, yanitlar });
    setMesgul(false);
    if (!y.ok || !y.veri) {
      gonderildi.current = false;
      setHata(hataYaz(t, y.kod, y.ek));
      return;
    }
    setSonuc(y.veri);
    await onBitti();
  }, [deneme, taban, q.id, yanitlar, t, onBitti]);

  // Süre: sunucu saatine göre geri sayım; bitince yanıtlar kendiliğinden gönderilir.
  useEffect(() => {
    if (!deneme?.son_at || sonuc) return;
    const son = new Date(deneme.son_at).getTime();
    const tik = () => {
      const k = Math.max(0, Math.floor((son - (Date.now() + fark.current)) / 1000));
      setKalan(k);
      if (k <= 0) void bitir();
    };
    tik();
    const z = window.setInterval(tik, 1000);
    return () => window.clearInterval(z);
  }, [deneme, sonuc, bitir]);

  return (
    <section className={`${KART} p-5`} data-testid="egitim-quiz" data-quiz-id={q.id}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={onGeri} className="text-sm text-blue-700 hover:underline">
          ← {t('egitimSayfa.geri')}
        </button>
        <span className="flex-1" />
        {kalan != null && !sonuc && (
          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-mono text-sm ${kalan < 60 ? 'bg-red-50 text-red-700' : 'bg-zinc-100 text-zinc-700'}`} data-testid="egitim-quiz-sure" aria-live="polite">
            <Clock className="h-4 w-4" aria-hidden="true" />
            {String(Math.floor(kalan / 60)).padStart(2, '0')}:{String(kalan % 60).padStart(2, '0')}
          </span>
        )}
      </div>
      <h2 className="text-xl font-bold">{q.baslik}</h2>
      {hata && (
        <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">
          {hata}
        </p>
      )}
      {sonuc ? (
        <div className={`mt-4 rounded-2xl p-5 text-center ${sonuc.gecti ? 'bg-emerald-50 text-emerald-900' : 'bg-amber-50 text-amber-900'}`} role="status" data-testid="egitim-quiz-sonuc" data-puan={sonuc.puan}>
          {sonuc.gecti ? <CheckCircle2 className="mx-auto mb-2 h-10 w-10" aria-hidden="true" /> : <XCircle className="mx-auto mb-2 h-10 w-10" aria-hidden="true" />}
          <div className="text-3xl font-bold">{sonuc.puan}</div>
          <p className="mt-1 text-sm">
            {sonuc.durum === 'suresi_doldu' ? t('egitimSayfa.quiz.sureDoldu') : t('egitimSayfa.quiz.sonuc', { dogru: sonuc.dogru, toplam: sonuc.toplam })}
          </p>
          <p className="mt-1 text-sm font-medium">{sonuc.gecti ? t('egitimSayfa.quiz.gecti') : t('egitimSayfa.quiz.kaldi', { puan: q.gecme_puani })}</p>
        </div>
      ) : deneme ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void bitir();
          }}
          className="mt-4 space-y-5"
        >
          {deneme.aciklama && <p className="whitespace-pre-line text-sm text-zinc-600">{deneme.aciklama}</p>}
          {deneme.sorular.map((s, n) => (
            <fieldset key={s.id} className="space-y-2" data-soru-id={s.id} data-soru-tur={s.tur}>
              <legend className="font-medium">
                {n + 1}. {s.metin}
              </legend>
              {s.tur === 'coktan' &&
                (s.secenekler || []).map((sec, i) => {
                  const secili = yanitlar[s.id] === i;
                  return (
                    <label key={i} className={`flex cursor-pointer items-center gap-2 rounded-xl border p-2.5 text-sm ${secili ? 'border-blue-500 bg-blue-50' : 'border-zinc-200'}`}>
                      <input type="radio" name={`soru-${s.id}`} checked={secili} onChange={() => setYanitlar({ ...yanitlar, [s.id]: i })} className="h-4 w-4 accent-blue-600" />
                      {sec}
                    </label>
                  );
                })}
              {s.tur === 'dogru_yanlis' && (
                <div className="flex gap-2">
                  {[true, false].map((d) => (
                    <label key={String(d)} className={`flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl border p-2.5 text-sm ${yanitlar[s.id] === d ? 'border-blue-500 bg-blue-50' : 'border-zinc-200'}`}>
                      <input type="radio" name={`soru-${s.id}`} checked={yanitlar[s.id] === d} onChange={() => setYanitlar({ ...yanitlar, [s.id]: d })} className="h-4 w-4 accent-blue-600" />
                      {d ? t('egitimSayfa.quiz.dogru') : t('egitimSayfa.quiz.yanlis')}
                    </label>
                  ))}
                </div>
              )}
              {s.tur === 'kisa' && (
                <input value={typeof yanitlar[s.id] === 'string' ? (yanitlar[s.id] as string) : ''} onChange={(x) => setYanitlar({ ...yanitlar, [s.id]: x.target.value })} maxLength={200} className={GIRDI} aria-label={s.metin} />
              )}
            </fieldset>
          ))}
          <button type="submit" disabled={mesgul} className={ANA_DUGME} data-testid="egitim-quiz-gonder">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('egitimSayfa.quiz.gonder')}
          </button>
        </form>
      ) : (
        !hata && <Loader2 className="mx-auto mt-6 h-6 w-6 animate-spin text-zinc-400" aria-hidden="true" />
      )}
    </section>
  );
}

function OdevTeslim({ t, dil, tz, taban, q, onGeri, onBitti }: { t: TFunction; dil: string; tz: string; taban: string; q: PortalQuiz; onGeri: () => void; onBitti: () => Promise<void> }) {
  const [metin, setMetin] = useState(q.teslim?.metin || '');
  const [dosya, setDosya] = useState<File | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [mesaj, setMesaj] = useState<{ ok: boolean; metin: string } | null>(null);
  const notlandi = !!q.teslim?.notlandi_at;

  const teslim = async (e: FormEvent) => {
    e.preventDefault();
    const form = new FormData();
    form.append('metin', metin);
    if (dosya) form.append('dosya', dosya);
    setMesgul(true);
    const y = await gonder<{ ok: boolean; gec: boolean }>(`${taban}/odev/${q.id}`, form, true);
    setMesgul(false);
    if (!y.ok || !y.veri) {
      setMesaj({ ok: false, metin: hataYaz(t, y.kod, y.ek) });
      return;
    }
    setMesaj({ ok: true, metin: y.veri.gec ? t('egitimSayfa.odev.gecTeslim') : t('egitimSayfa.odev.teslimEdildi') });
    setDosya(null);
    await onBitti();
  };

  return (
    <section className={`${KART} p-5`} data-testid="egitim-odev" data-quiz-id={q.id}>
      <button type="button" onClick={onGeri} className="mb-3 text-sm text-blue-700 hover:underline">
        ← {t('egitimSayfa.geri')}
      </button>
      <h2 className="text-xl font-bold">{q.baslik}</h2>
      {q.son_tarih && <p className="mt-1 text-sm text-zinc-600">{t('egitimSayfa.quiz.sonTarih', { tarih: zamanYaz(q.son_tarih, tz, dil) })}</p>}
      {q.aciklama && <p className="mt-3 whitespace-pre-line text-sm text-zinc-700">{q.aciklama}</p>}
      {q.teslim && (
        <div className="mt-4 rounded-xl bg-zinc-50 p-3 text-sm">
          <p className="text-zinc-600">{t('egitimSayfa.odev.sonTeslim', { tarih: zamanYaz(q.teslim.teslim_at, tz, dil) })}</p>
          {q.teslim.dosyalar.map((f) => (
            <a key={f.id} href={`${api()}${taban}/dosya/${f.id}`} className="mt-1 inline-flex items-center gap-1 text-blue-700 hover:underline" rel="noreferrer">
              <FileText className="h-4 w-4" aria-hidden="true" />
              {f.ad}
            </a>
          ))}
          {notlandi && (
            <div className="mt-2 border-t border-zinc-200 pt-2" data-testid="egitim-odev-not">
              <p className="font-semibold">{t('egitimSayfa.odev.notu', { puan: q.teslim.puan ?? '—' })}</p>
              {q.teslim.geri_bildirim && <p className="mt-1 whitespace-pre-line text-zinc-700">{q.teslim.geri_bildirim}</p>}
            </div>
          )}
        </div>
      )}
      {!notlandi && (
        <form onSubmit={teslim} className="mt-4 space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">{t('egitimSayfa.odev.metin')}</span>
            <textarea value={metin} onChange={(x) => setMetin(x.target.value)} rows={6} maxLength={20000} className={GIRDI} data-testid="egitim-odev-metin" />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">{t('egitimSayfa.odev.dosya')}</span>
            <input type="file" onChange={(x) => setDosya(x.target.files?.[0] || null)} className="text-sm" />
          </label>
          {mesaj && (
            <p className={`rounded-xl p-3 text-sm ${mesaj.ok ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-700'}`} role="status">
              {mesaj.metin}
            </p>
          )}
          <button type="submit" disabled={mesgul || (!metin.trim() && !dosya)} className={ANA_DUGME} data-testid="egitim-odev-gonder">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
            {q.teslim ? t('egitimSayfa.odev.yenidenTeslim') : t('egitimSayfa.odev.teslimEt')}
          </button>
        </form>
      )}
    </section>
  );
}

// ===========================================================================
// Sınıftaki oturum QR'ı → yoklama (bu cihazdaki öğrenci bağlantısıyla)
// ===========================================================================
function YoklamaGorunum({ jeton, t, dil, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { jeton: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [o, setO] = useState<{ kurs: string; renk: string; dil: string; saat_dilimi: string; baslangic: string; bitis: string; konu: string; acik: boolean; iptal: boolean } | null>(null);
  const [sonuc, setSonuc] = useState<{ ok: boolean; metin: string } | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const denendi = useRef(false);

  const isaretle = useCallback(
    async (tf: TFunction) => {
      const jetonlar = jetonlariOku();
      if (!jetonlar.length) {
        setSonuc({ ok: false, metin: tf('egitimSayfa.yoklama.cihazdaYok') });
        return;
      }
      setMesgul(true);
      let son = { kod: 'farkli_kurs', ek: {} as Record<string, unknown> };
      for (const j of jetonlar) {
        const y = await gonder<{ sonuc: 'isaretlendi' | 'zaten'; durum: string }>(`/api/v1/egitim/yoklama/${encodeURIComponent(jeton)}`, { ogrenci: j });
        if (y.ok && y.veri) {
          setMesgul(false);
          setSonuc({ ok: true, metin: y.veri.sonuc === 'zaten' ? tf('egitimSayfa.yoklama.zaten') : tf(`egitimSayfa.yoklama.isaretlendi_${y.veri.durum === 'gec' ? 'gec' : 'var'}`) });
          return;
        }
        son = { kod: y.kod, ek: y.ek };
        // Başka kursun / geçersiz bağlantı: sıradakini dene. Diğer hatalar (kapalı, hız) kesin.
        if (!['farkli_kurs', 'baglanti_gecersiz', 'kayit_kapandi', 'baglanti_suresi_doldu', 'bekleme_listesinde'].includes(y.kod)) break;
      }
      setMesgul(false);
      setSonuc({ ok: false, metin: son.kod === 'farkli_kurs' || son.kod === 'baglanti_gecersiz' ? tf('egitimSayfa.yoklama.cihazdaYok') : hataYaz(tf, son.kod, son.ek) });
    },
    [jeton]
  );

  useEffect(() => {
    let iptal = false;
    void (async () => {
      const y = await getir<NonNullable<typeof o>>(`/api/v1/egitim/yoklama/${encodeURIComponent(jeton)}`);
      if (iptal) return;
      await hazirla(y.veri?.dil || 'tr');
      setIndeks(false);
      if (!y.veri) {
        setYukleme(durumYukleme(y.durum, y.kod));
        return;
      }
      setO(y.veri);
      setBaslik(y.veri.kurs);
      setYukleme('hazir');
    })();
    return () => {
      iptal = true;
    };
  }, [jeton, hazirla, setBaslik, setIndeks]);

  // Açık oturumda bu cihazdaki bağlantıyla kendiliğinden işaretle (QR okutmak zaten bilinçli bir adım).
  useEffect(() => {
    if (!t || !o || !o.acik || o.iptal || denendi.current) return;
    denendi.current = true;
    void isaretle(t);
  }, [t, o, isaretle]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !o) return <Durum t={t} durum={yukleme} />;
  return (
    <main className={`${KART} mx-auto max-w-md overflow-hidden`} data-testid="egitim-yoklama-sayfasi">
      <Seridi renk={o.renk} />
      <div className="space-y-3 p-6 text-center">
        <ClipboardCheck className="mx-auto h-10 w-10 text-blue-600" aria-hidden="true" />
        <h1 className="text-xl font-bold">{o.kurs}</h1>
        <p className="text-sm text-zinc-600">
          {aralikYaz(o.baslangic, o.bitis, o.saat_dilimi, dil)}
          {o.konu ? ` · ${o.konu}` : ''}
        </p>
        {o.iptal ? (
          <p className="text-sm text-zinc-600">{t('egitimSayfa.yoklama.oturumIptal')}</p>
        ) : !o.acik ? (
          <p className="text-sm text-amber-700">{t('egitimSayfa.yoklama.kapali')}</p>
        ) : mesgul ? (
          <Loader2 className="mx-auto h-6 w-6 animate-spin text-zinc-400" aria-hidden="true" />
        ) : sonuc ? (
          <div className={`rounded-xl p-4 text-sm ${sonuc.ok ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`} role="status" data-testid="egitim-yoklama-qr-sonuc" data-ok={sonuc.ok ? '1' : '0'}>
            {sonuc.ok ? <CheckCircle2 className="mx-auto mb-1 h-8 w-8" aria-hidden="true" /> : null}
            {sonuc.metin}
          </div>
        ) : null}
        {sonuc && !sonuc.ok && o.acik && (
          <button type="button" className={IKINCIL_DUGME} onClick={() => void isaretle(t)}>
            {t('egitimSayfa.yoklama.tekrarDene')}
          </button>
        )}
      </div>
    </main>
  );
}

// ===========================================================================
// Sertifika doğrulama
// ===========================================================================
function SertifikaGorunum({ kod, t, dil, setBaslik, setIndeks }: OrtakOzellikler & { kod: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [c, setC] = useState<{ gecerli: boolean; kod: string; ad: string; kurs: string; kurum: string; verilme_at: string; iptal_at: string | null } | null>(null);
  const [girdi, setGirdi] = useState('');

  useEffect(() => {
    let iptal = false;
    setIndeks(false);
    void (async () => {
      const y = await getir<NonNullable<typeof c>>(`/api/v1/egitim/sertifika/${encodeURIComponent(kod)}`);
      if (iptal) return;
      if (!y.veri) {
        setYukleme(y.durum === 404 ? 'yok' : 'hata');
        return;
      }
      setC(y.veri);
      setYukleme('hazir');
    })();
    return () => {
      iptal = true;
    };
  }, [kod, setIndeks]);

  useEffect(() => {
    if (t) setBaslik(t('egitimSayfa.dogrula.baslik'));
  }, [t, setBaslik]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  return (
    <main className="mx-auto max-w-md space-y-4" data-testid="egitim-dogrulama">
      <section className={`${KART} p-6 text-center`}>
        {yukleme !== 'hazir' || !c ? (
          <div data-testid="egitim-dogrulama-sonuc" data-gecerli="0">
            <ShieldX className="mx-auto mb-2 h-12 w-12 text-red-500" aria-hidden="true" />
            <h1 className="text-lg font-semibold">{yukleme === 'yok' ? t('egitimSayfa.dogrula.yok') : t('egitimSayfa.yukleme.hata')}</h1>
          </div>
        ) : (
          <div data-testid="egitim-dogrulama-sonuc" data-gecerli={c.gecerli ? '1' : '0'}>
            {c.gecerli ? <ShieldCheck className="mx-auto mb-2 h-12 w-12 text-emerald-600" aria-hidden="true" /> : <ShieldX className="mx-auto mb-2 h-12 w-12 text-red-500" aria-hidden="true" />}
            <h1 className={`text-lg font-semibold ${c.gecerli ? 'text-emerald-800' : 'text-red-700'}`}>{c.gecerli ? t('egitimSayfa.dogrula.gecerli') : t('egitimSayfa.dogrula.iptal')}</h1>
            <dl className="mt-4 space-y-2 text-start text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-zinc-500">{t('egitimSayfa.dogrula.ad')}</dt>
                <dd className="font-medium" data-testid="egitim-dogrulama-ad">
                  {c.ad}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-zinc-500">{t('egitimSayfa.dogrula.kurs')}</dt>
                <dd className="text-end font-medium">{c.kurs}</dd>
              </div>
              {c.kurum && (
                <div className="flex justify-between gap-3">
                  <dt className="text-zinc-500">{t('egitimSayfa.dogrula.kurum')}</dt>
                  <dd className="text-end font-medium">{c.kurum}</dd>
                </div>
              )}
              <div className="flex justify-between gap-3">
                <dt className="text-zinc-500">{t('egitimSayfa.dogrula.tarih')}</dt>
                <dd className="font-medium">{tarihYaz(c.verilme_at, 'UTC', dil, { dateStyle: 'long' })}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-zinc-500">{t('egitimSayfa.dogrula.kod')}</dt>
                <dd className="font-mono" dir="ltr">
                  {c.kod}
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-xs text-zinc-500">{t('egitimSayfa.dogrula.gizlilik')}</p>
          </div>
        )}
      </section>
      <form
        className={`${KART} flex flex-wrap items-end gap-2 p-4`}
        onSubmit={(e) => {
          e.preventDefault();
          const temiz = girdi.replace(/[^0-9A-Za-z]/g, '').toUpperCase();
          if (temiz) window.location.assign(`/egitim/sertifika/${temiz}`);
        }}
      >
        <label className="block min-w-[10rem] flex-1 text-sm">
          <span className="mb-1 block text-zinc-600">{t('egitimSayfa.dogrula.baskaKod')}</span>
          <input value={girdi} onChange={(x) => setGirdi(x.target.value)} maxLength={20} className={`${GIRDI} font-mono`} dir="ltr" />
        </label>
        <button type="submit" className={IKINCIL_DUGME}>
          {t('egitimSayfa.dogrula.denetle')}
        </button>
      </form>
    </main>
  );
}

// ===========================================================================
// Kurum kurs listesi
// ===========================================================================
function KurumGorunum({ slug, t, dil, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { slug: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [gecmis, setGecmis] = useState(false);
  const [v, setV] = useState<{ baslik: string; aciklama: string; kurum_adi: string; items: { slug: string; ad: string; ozet: string; renk: string; bicim: Bicim; baslangic_tarihi: string | null; bitis_tarihi: string | null; fiyat_metni: string; durum: string; egitmenler: string[] }[] } | null>(null);

  useEffect(() => {
    let iptal = false;
    setIndeks(false);
    void (async () => {
      const y = await getir<NonNullable<typeof v>>(`/api/v1/egitim/kurum/${encodeURIComponent(slug)}${gecmis ? '?gecmis=true' : ''}`);
      if (iptal) return;
      await hazirla(i18n.language || 'tr');
      if (!y.veri) {
        setYukleme(durumYukleme(y.durum, y.kod));
        return;
      }
      setV(y.veri);
      setBaslik(y.veri.baslik || y.veri.kurum_adi);
      setYukleme('hazir');
    })();
    return () => {
      iptal = true;
    };
  }, [slug, gecmis, hazirla, setBaslik, setIndeks]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !v) return <Durum t={t} durum={yukleme} />;
  return (
    <main className="mx-auto max-w-3xl space-y-4" data-testid="egitim-kurum">
      <header>
        <h1 className="text-2xl font-bold">{v.baslik || v.kurum_adi || t('egitimSayfa.kurum.baslik')}</h1>
        {v.aciklama && <p className="mt-1 whitespace-pre-line text-zinc-600">{v.aciklama}</p>}
      </header>
      <div className="inline-flex rounded-xl border border-zinc-200 bg-white p-1 text-sm" role="tablist">
        {[false, true].map((g) => (
          <button key={String(g)} type="button" role="tab" aria-selected={gecmis === g} onClick={() => setGecmis(g)} className={`rounded-lg px-3 py-1.5 font-medium ${gecmis === g ? 'bg-blue-600 text-white' : 'text-zinc-600'}`}>
            {t(g ? 'egitimSayfa.kurum.tumu' : 'egitimSayfa.kurum.acik')}
          </button>
        ))}
      </div>
      {v.items.length === 0 ? (
        <p className="py-10 text-center text-zinc-500">{t('egitimSayfa.kurum.bos')}</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {v.items.map((x) => (
            <li key={x.slug} className={`${KART} overflow-hidden`}>
              <a href={`/egitim/${x.slug}`} className="block h-full hover:bg-zinc-50">
                <Seridi renk={x.renk} />
                <div className="space-y-1.5 p-4">
                  <div className="flex flex-wrap gap-1.5">
                    <BicimRozeti t={t} bicim={x.bicim} />
                    {x.durum === 'tamamlandi' && <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700">{t('egitimSayfa.kurs.tamamlandi')}</span>}
                  </div>
                  <h2 className="font-semibold leading-snug">{x.ad}</h2>
                  {x.baslangic_tarihi && (
                    <p className="text-sm text-zinc-600">
                      {gunYaz(x.baslangic_tarihi, dil)}
                      {x.bitis_tarihi && x.bitis_tarihi !== x.baslangic_tarihi ? ` – ${gunYaz(x.bitis_tarihi, dil)}` : ''}
                    </p>
                  )}
                  {x.egitmenler.length > 0 && <p className="text-sm text-zinc-500">{x.egitmenler.join(', ')}</p>}
                  {x.ozet && <p className="line-clamp-2 text-sm text-zinc-600">{x.ozet}</p>}
                  {x.fiyat_metni && <p className="text-sm font-medium">{x.fiyat_metni}</p>}
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

// ===========================================================================
// Panel okutucusu: eğitmen öğrencinin QR'ını / kodunu okutur (ekip izni; etkinlik okutucusu yeniden kullanılıyor)
// ===========================================================================
function okutmaIstemcisi(kid: number, oid: number, yonetici: boolean): OkutmaIstemcisi {
  const taban = `${yonetici ? '/api/v1/egitim/yonetim' : '/api/v1/egitimim'}/${kid}/oturumlar/${oid}`;
  const basliklar = (): Record<string, string> => {
    const b: Record<string, string> = { accept: 'application/json' };
    try {
      const j = localStorage.getItem('token');
      if (j) b.Authorization = `Bearer ${j}`;
    } catch {
      /* depolama yok */
    }
    const h = seciliHesap();
    if (h) b['X-MK-Hesap'] = h;
    return b;
  };
  const json = async <T,>(yol: string, init: RequestInit = {}): Promise<T> => {
    let y: Response;
    try {
      y = await fetch(`${api()}${yol}`, { ...init, headers: { ...basliklar(), ...(init.headers as Record<string, string> | undefined) } });
    } catch {
      throw new OkutmaHatasi(0, 'ag');
    }
    const g = await y.json().catch(() => null);
    if (!y.ok) throw new OkutmaHatasi(y.status, hataKodu(g));
    return g as T;
  };
  return {
    anahtar: `mk-egitim-kuyruk-${kid}-${oid}`,
    async ozet() {
      const g = await json<{ baslik: string; baslangic: string; bitis: string; saat_dilimi: string; sayac: Sayac }>(`${taban}/okutucu`);
      return { ...g, dil: '', durum: '' };
    },
    okut: (kod) => json<OkutmaYaniti>(`${taban}/okut`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kod }) }),
    sayac: () => json<Sayac>(`${taban}/sayac`),
  };
}

function OkutGorunum({ kid, oid, t, dil, setBaslik }: { kid: number; oid: number; t: TFunction | null; dil: string; setBaslik: (b: string) => void }) {
  const yonetici = sorgu('mod') === 'yonetici';
  const istemci = useMemo(() => okutmaIstemcisi(kid, oid, yonetici), [kid, oid, yonetici]);
  if (!t) return <Yukleniyor t={t} />;
  return (
    <Suspense fallback={<Yukleniyor t={t} />}>
      <Okutucu istemci={istemci} t={t} dil={dil} panelAdresi={yonetici ? '/admin' : '/client'} onBaslik={setBaslik} onek="egitimSayfa" />
    </Suspense>
  );
}
