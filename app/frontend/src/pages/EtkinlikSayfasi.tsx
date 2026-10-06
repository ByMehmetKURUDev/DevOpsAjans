import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import {
  AlertTriangle,
  CalendarDays,
  CalendarPlus,
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  Globe,
  Loader2,
  MapPin,
  Minus,
  Plus,
  Ticket,
  Users,
  Video,
} from 'lucide-react';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import {
  DIL_ADLARI,
  ETKINLIK_DILLERI,
  api,
  aralikYaz,
  depoOku,
  depoYaz,
  dilSec,
  gorevliIstemcisi,
  hataKodu,
  panelIstemcisi,
  paraYaz,
  saatYaz,
  sorgu,
  tarihYaz,
  type Bicim,
  type BiletDurumu,
  type EtkinlikDili,
  type Oturum,
  type Soru,
  type TelefonKurali,
} from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — herkese açık etkinlik sayfaları (site düzeninin DIŞINDA, lazy; prerender yok,
 * site haritasında yok; varsayılan noindex — sahibi "arama motorlarında görünsün" derse index +
 * Event JSON-LD; paylaşım önizlemesi `functions/etkinlik/[[yol]].js`):
 *
 *   /etkinlik/<slug>                   etkinlik + kayıt formu (?kod= gizli tür, ?davet= bekleme daveti,
 *                                      ?gomulu=1 gömme penceresi, ?dil=)
 *   /etkinlik/<slug>/bilet/<jeton>     imzalı bilet sayfası: QR, PDF, takvim, iptal
 *   /etkinlik/giris/<jeton>            görevli bağlantısı: yalnız kapı okutma (girişsiz, süreli)
 *   /etkinlik/okut/<id>?mod=           panel okutucusu (oturum + ekip izni `etkinlik_giris`)
 *   /etkinlikler/<slug>                hesabın etkinlik listesi
 *
 * Metinler sayfanın KENDİ dilinde (ziyaretçi seçimi → etkinlik dili); ek paket `etkinlikSayfa`.
 */

const Okutucu = lazy(() => import('@/components/etkinlik/Okutucu'));

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/etkinlikSayfa/*.json');
const yuklenenDiller = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenenDiller.has(d)) continue;
    const yukleyici = EK_PAKETLER[`../i18n/ek/etkinlikSayfa/${d}.json`];
    if (!yukleyici) continue;
    const mod = await yukleyici();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenenDiller.add(d);
  }
}

const DIL_ANAHTARI = 'mk-etkinlik-dil';

export type EtkinlikGorunumu = 'etkinlik' | 'bilet' | 'giris' | 'okut' | 'liste';

interface AcikTur {
  id: number;
  ad: string;
  aciklama: string;
  fiyat: number;
  para_birimi: string;
  kalan: number | null;
  dolu: boolean;
  satis: 'acik' | 'baslamadi' | 'bitti';
  satis_bas: string | null;
  satis_bit: string | null;
  kisi_basi_en_cok: number;
  gizli: boolean;
}

interface AcikEtkinlik {
  slug: string;
  baslik: string;
  ozet: string;
  aciklama: string;
  kapak: string | null;
  renk: string;
  bicim: Bicim;
  mekan_adi: string;
  adres: string;
  harita: string | null;
  saat_dilimi: string;
  baslangic: string;
  bitis: string;
  oturumlar: Oturum[];
  durum: 'yayinda' | 'iptal' | 'tamamlandi';
  dil: EtkinlikDili;
  organizator_ad: string;
  organizator_url: string;
  iade_politikasi: string;
  kvkk_metni: string;
  odeme_notu: string;
  katilimci_adlari: boolean;
  telefon: TelefonKurali;
  sorular: Soru[];
  bekleme_listesi: boolean;
  kapasite: number | null;
  kalan: number | null;
  dolu: boolean;
  kayit_acik: boolean;
  kayit_neden: string | null;
  kayit_acilis: string | null;
  kayit_kapanis: string | null;
  indirim_var: boolean;
  gizli_tur_var: boolean;
  indekslenebilir: boolean;
  ajans: boolean;
  turler: AcikTur[];
  pazarlama_metinleri: Record<string, string>;
  adres_url: string;
  davet: { gecerli: boolean; son: string; adet: number; tur_id: number | null; ad: string | null; eposta: string | null } | null;
}

interface BiletVerisi {
  siparis: { kod: string; durum: string; ad: string | null; eposta: string | null; toplam: number; indirim: number; para_birimi: string; dil: string; odeme_adresi: string | null; odeme_son: string | null };
  etkinlik: {
    slug: string;
    baslik: string;
    ozet: string;
    kapak: string | null;
    renk: string;
    bicim: Bicim;
    mekan_adi: string;
    adres: string;
    harita: string | null;
    online_baglanti: string | null;
    baslangic: string;
    bitis: string;
    saat_dilimi: string;
    dil: EtkinlikDili;
    oturumlar: Oturum[];
    organizator_ad: string;
    iade_politikasi: string;
    odeme_notu: string;
    durum: string;
  };
  biletler: { kod: string; tur: string; katilimci_ad: string | null; durum: BiletDurumu; giris_at: string | null; iade: string; qr: string | null; qr_adresi: string | null }[];
  iptal_edilebilir: boolean;
  iptal_son: string;
  pdf_adresi: string | null;
  ics_adresi: string | null;
  takvim?: { google: string; outlook: string; ics: string };
}

interface ListeVerisi {
  slug: string;
  baslik: string;
  aciklama: string;
  gecmis: boolean;
  etkinlikler: { slug: string; baslik: string; ozet: string; kapak: string | null; renk: string; bicim: Bicim; mekan_adi: string; baslangic: string; bitis: string; saat_dilimi: string; durum: string; dolu: boolean; ucretsiz: boolean }[];
}

type Yukleme = 'yukleniyor' | 'hazir' | 'yok' | 'pasif' | 'suresi' | 'hata';

async function getir<T>(yol: string): Promise<{ durum: number; veri: T | null; kod: string }> {
  try {
    const y = await fetch(`${api()}${yol}`, { headers: { accept: 'application/json' } });
    const g = await y.json().catch(() => null);
    return { durum: y.status, veri: y.ok ? (g as T) : null, kod: y.ok ? '' : hataKodu(g) };
  } catch {
    return { durum: 0, veri: null, kod: 'ag' };
  }
}

async function gonder<T>(yol: string, govde: unknown): Promise<{ ok: boolean; veri: T | null; kod: string; ek: Record<string, unknown> }> {
  try {
    const y = await fetch(`${api()}${yol}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(govde),
    });
    const g = await y.json().catch(() => null);
    const detay = (g as { detail?: Record<string, unknown> } | null)?.detail;
    return { ok: y.ok, veri: y.ok ? (g as T) : null, kod: y.ok ? '' : y.status === 429 ? 'cok_hizli' : hataKodu(g), ek: detay && typeof detay === 'object' ? detay : {} };
  } catch {
    return { ok: false, veri: null, kod: 'ag', ek: {} };
  }
}

function gorselAdresi(yol: string | null): string | null {
  if (!yol) return null;
  return /^https?:/.test(yol) ? yol : `${api()}${yol}`;
}

function durumYukleme(durum: number, kod: string): Yukleme {
  if (durum === 404) return 'yok';
  if (durum === 410) return kod === 'baglanti_suresi_doldu' ? 'suresi' : 'pasif';
  return 'hata';
}

// ===========================================================================
// Kabuk: dil, belge başlığı/yönü/robots, gömülü yükseklik
// ===========================================================================
export default function EtkinlikSayfasi({ gorunum }: { gorunum: EtkinlikGorunumu }) {
  const p = useParams<{ slug: string; jeton: string; eid: string }>();
  const gomulu = useMemo(() => sorgu('gomulu') === '1', []);
  const karanlik = gorunum === 'giris' || gorunum === 'okut';
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

  // Okutucuların dili: veriden önce (uygulama dili / seçim).
  useEffect(() => {
    if (karanlik) void hazirla(i18n.language || 'tr');
  }, [karanlik, hazirla]);

  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background, baslik: document.title };
    if (dil) {
      kok.lang = dil;
      kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    }
    document.body.style.background = gomulu ? 'transparent' : karanlik ? '#09090b' : '#f7f7f8';
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      document.title = eski.baslik;
    };
  }, [dil, gomulu, karanlik]);

  useEffect(() => {
    if (baslik) document.title = baslik;
    let etiket = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!etiket) {
      etiket = document.createElement('meta');
      etiket.name = 'robots';
      document.head.appendChild(etiket);
    }
    etiket.content = indeks && gorunum === 'etkinlik' ? 'index, follow' : 'noindex, nofollow';
  }, [baslik, indeks, gorunum]);

  // Gömülü pencere: yüksekliği üst sayfaya bildir (public/etkinlik-widget.js).
  useEffect(() => {
    if (!gomulu || typeof ResizeObserver === 'undefined' || window.parent === window) return;
    const bildir = () => {
      try {
        const g = document.body;
        const stil = getComputedStyle(g);
        const y = g.getBoundingClientRect().height + parseFloat(stil.marginTop || '0') + parseFloat(stil.marginBottom || '0');
        window.parent.postMessage({ tur: 'mk-etkinlik', yukseklik: Math.ceil(y) }, '*');
      } catch {
        /* üst sayfa yok */
      }
    };
    const gozlemci = new ResizeObserver(bildir);
    gozlemci.observe(document.body);
    bildir();
    return () => gozlemci.disconnect();
  }, [gomulu]);

  const ortak = { t, dil: dil || 'tr', gomulu, hazirla, setBaslik, setIndeks };

  let icerik: ReactNode;
  if (gorunum === 'etkinlik') icerik = <EtkinlikGorunum slug={p.slug || ''} {...ortak} />;
  else if (gorunum === 'bilet') icerik = <BiletGorunum slug={p.slug || ''} jeton={p.jeton || ''} {...ortak} />;
  else if (gorunum === 'liste') icerik = <ListeGorunum slug={p.slug || ''} {...ortak} />;
  else icerik = <OkutGorunum gorunum={gorunum} jeton={p.jeton || ''} eid={Number(p.eid || 0)} t={t} dil={dil || 'tr'} setBaslik={setBaslik} />;

  return (
    <div
      className={`${gomulu ? 'p-2 sm:p-3' : karanlik ? 'min-h-screen' : 'min-h-screen px-3 py-6 sm:px-6 sm:py-10'} ${karanlik ? 'text-white' : 'text-zinc-900'}`}
      data-testid="etkinlik-sayfasi"
      data-gorunum={gorunum}
      data-gomulu={gomulu ? '1' : '0'}
    >
      {icerik}
      {t && dil && !gomulu && (
        <footer className={`mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-between gap-3 px-1 pb-4 text-xs ${karanlik ? 'text-zinc-500' : 'text-zinc-500'}`}>
          <label className="inline-flex items-center gap-1.5">
            <Globe className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="sr-only">{t('etkinlikSayfa.dil')}</span>
            <select
              value={dil}
              onChange={(e) => void dilDegistir(e.target.value as EtkinlikDili)}
              className={`rounded-md border px-1.5 py-1 ${karanlik ? 'border-white/15 bg-zinc-900 text-zinc-200' : 'border-zinc-300 bg-white text-zinc-700'}`}
              data-testid="etkinlik-dil"
            >
              {ETKINLIK_DILLERI.map((d) => (
                <option key={d} value={d}>
                  {DIL_ADLARI[d]}
                </option>
              ))}
            </select>
          </label>
          <a href="/" className="hover:underline">
            {t('etkinlikSayfa.altBilgi')}
          </a>
        </footer>
      )}
    </div>
  );
}

interface OrtakOzellikler {
  t: TFunction | null;
  dil: string;
  gomulu: boolean;
  hazirla: (yedek: string) => Promise<void>;
  setBaslik: (b: string) => void;
  setIndeks: (v: boolean) => void;
}

function Yukleniyor({ t }: { t: TFunction | null }) {
  return (
    <div className="flex min-h-[50vh] items-center justify-center" data-testid="etkinlik-yukleniyor">
      <Loader2 className="h-8 w-8 animate-spin text-zinc-400" aria-label={t ? t('etkinlikSayfa.yukleniyor') : undefined} />
    </div>
  );
}

function Durum({ t, durum }: { t: TFunction; durum: Yukleme }) {
  return (
    <div className="mx-auto max-w-md py-16 text-center" data-testid="etkinlik-durum" data-durum={durum}>
      <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden="true" />
      <p className="text-lg font-medium">{t(`etkinlikSayfa.yukleme.${durum}`)}</p>
    </div>
  );
}

const KART = 'rounded-2xl border border-zinc-200 bg-white shadow-sm';
const GIRDI = 'w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-base text-zinc-900';

function hataYaz(t: TFunction, kod: string, ek: Record<string, unknown> = {}): string {
  return t(`etkinlikSayfa.hata.${kod}`, { ...ek, defaultValue: t('etkinlikSayfa.hata.genel') }) as string;
}

function BicimRozeti({ t, bicim }: { t: TFunction; bicim: Bicim }) {
  const Ikon = bicim === 'online' ? Video : bicim === 'karma' ? Users : MapPin;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700">
      <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
      {t(`etkinlikSayfa.bicim.${bicim}`)}
    </span>
  );
}

function Zaman({ t, dil, bas, bit, tz, oturumlar }: { t: TFunction; dil: string; bas: string; bit: string; tz: string; oturumlar: Oturum[] }) {
  return (
    <div className="flex items-start gap-2">
      <CalendarDays className="mt-0.5 h-5 w-5 shrink-0 text-zinc-500" aria-hidden="true" />
      <div>
        <div className="font-medium" data-testid="etkinlik-zaman">
          {aralikYaz(bas, bit, tz, dil)}
        </div>
        <div className="text-xs text-zinc-500">{t('etkinlikSayfa.saatDilimi', { tz: tz.replace(/_/g, ' ') })}</div>
        {oturumlar.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-sm text-zinc-700">
            {oturumlar.map((o, i) => (
              <li key={i}>
                <span className="font-medium">{o.ad || t('etkinlikSayfa.oturum', { sayi: i + 1 })}</span> · {aralikYaz(o.baslangic, o.bitis, tz, dil)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Konum({ t, bicim, mekan, adres, harita, online }: { t: TFunction; bicim: Bicim; mekan: string; adres: string; harita: string | null; online?: string | null }) {
  return (
    <div className="space-y-2">
      {bicim !== 'online' && (mekan || adres) && (
        <div className="flex items-start gap-2">
          <MapPin className="mt-0.5 h-5 w-5 shrink-0 text-zinc-500" aria-hidden="true" />
          <div>
            {mekan && <div className="font-medium">{mekan}</div>}
            {adres && <div className="whitespace-pre-line text-sm text-zinc-600">{adres}</div>}
            {harita && (
              <a href={harita} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-purple-700 hover:underline">
                {t('etkinlikSayfa.harita')}
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            )}
          </div>
        </div>
      )}
      {bicim !== 'yuz_yuze' && (
        <div className="flex items-start gap-2">
          <Video className="mt-0.5 h-5 w-5 shrink-0 text-zinc-500" aria-hidden="true" />
          {online ? (
            <a href={online} target="_blank" rel="noopener noreferrer" className="break-all font-medium text-purple-700 underline" dir="ltr" data-testid="etkinlik-online-baglanti">
              {online}
            </a>
          ) : (
            <span className="text-sm text-zinc-600">{t('etkinlikSayfa.onlineNot')}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// Etkinlik + kayıt
// ===========================================================================
function EtkinlikGorunum({ slug, t, dil, gomulu, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { slug: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [e, setE] = useState<AcikEtkinlik | null>(null);
  const [gizliKod, setGizliKod] = useState(() => sorgu('kod') || '');
  const [kodGirdisi, setKodGirdisi] = useState('');
  const [davet, setDavet] = useState(() => sorgu('davet') || '');
  const [davetHatasi, setDavetHatasi] = useState<string | null>(null);
  const [adetler, setAdetler] = useState<Record<number, number>>({});
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [telefon, setTelefon] = useState('');
  const [adlar, setAdlar] = useState<string[]>([]);
  const [yanitlar, setYanitlar] = useState<Record<string, string | boolean>>({});
  const [izin, setIzin] = useState(false);
  const [balKupu, setBalKupu] = useState('');
  const [indirimKodu, setIndirimKodu] = useState('');
  const [fiyat, setFiyat] = useState<{ ara_toplam: number; indirim: number; toplam: number; para_birimi: string } | null>(null);
  const [indirimHatasi, setIndirimHatasi] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [odeme, setOdeme] = useState<{ adres: string; son: string | null; bilet: string } | null>(null);
  const [bekleme, setBekleme] = useState<{ acik: boolean; adet: number; tur_id: number | null; tamam: number | null }>({ acik: false, adet: 1, tur_id: null, tamam: null });

  const yukle = useCallback(async () => {
    const q = new URLSearchParams();
    if (gizliKod) q.set('kod', gizliKod);
    if (davet) q.set('davet', davet);
    const s = q.toString();
    let y = await getir<AcikEtkinlik>(`/api/v1/etkinlik/${encodeURIComponent(slug)}${s ? `?${s}` : ''}`);
    if (!y.veri && davet && y.kod.startsWith('davet_')) {
      setDavetHatasi(y.kod);
      setDavet('');
      y = await getir<AcikEtkinlik>(`/api/v1/etkinlik/${encodeURIComponent(slug)}${gizliKod ? `?kod=${encodeURIComponent(gizliKod)}` : ''}`);
    }
    await hazirla(y.veri?.dil || 'tr');
    if (!y.veri) {
      setYukleme(durumYukleme(y.durum, y.kod));
      return;
    }
    const v = y.veri;
    setE(v);
    setBaslik(v.baslik);
    setIndeks(v.indekslenebilir);
    if (v.davet) {
      setAd((x) => x || v.davet?.ad || '');
      setEposta((x) => x || v.davet?.eposta || '');
    }
    setYukleme('hazir');
  }, [slug, gizliKod, davet, hazirla, setBaslik, setIndeks]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  // Event JSON-LD: Pages Function sunucuda basıyor; SPA içi gezinmede yoksa ekle (CSP: veri bloğu, çalışmaz).
  useEffect(() => {
    if (!e?.indekslenebilir || document.querySelector('script[data-mk-etkinlik]')) return;
    let iptal = false;
    let eklenen: HTMLScriptElement | null = null;
    void getir<{ jsonld: Record<string, unknown> | null }>(`/api/v1/etkinlik/${encodeURIComponent(e.slug)}/ozet`).then((o) => {
      if (iptal || !o.veri?.jsonld || document.querySelector('script[data-mk-etkinlik]')) return;
      eklenen = document.createElement('script');
      eklenen.type = 'application/ld+json';
      eklenen.setAttribute('data-mk-etkinlik', '');
      eklenen.textContent = JSON.stringify(o.veri.jsonld).replace(/</g, '\\u003c');
      document.head.appendChild(eklenen);
    });
    return () => {
      iptal = true;
      eklenen?.remove();
    };
  }, [e?.indekslenebilir, e?.slug]);

  const secili = useMemo(() => (e ? e.turler.filter((x) => (adetler[x.id] || 0) > 0).map((x) => ({ tur: x, adet: adetler[x.id] })) : []), [e, adetler]);
  const toplamAdet = secili.reduce((a, x) => a + x.adet, 0);
  const ucretliSecim = secili.some((x) => x.tur.fiyat > 0);

  // Fiyat (indirimle) — ücretli seçimde sunucudan; ücretsizde yerel.
  useEffect(() => {
    if (!e || !ucretliSecim) {
      setFiyat(null);
      return;
    }
    let iptal = false;
    const z = window.setTimeout(async () => {
      const y = await gonder<{ ara_toplam: number; indirim: number; toplam: number; para_birimi: string }>(`/api/v1/etkinlik/${encodeURIComponent(e.slug)}/fiyat`, {
        kalemler: secili.map((x) => ({ tur_id: x.tur.id, adet: x.adet })),
        indirim_kodu: indirimKodu.trim() || undefined,
        gizli_kod: gizliKod || undefined,
      });
      if (iptal) return;
      if (y.ok && y.veri) {
        setFiyat(y.veri);
        setIndirimHatasi(null);
      } else if (y.kod.startsWith('indirim_')) {
        setIndirimHatasi(y.kod);
        setFiyat(null);
      }
    }, 250);
    return () => {
      iptal = true;
      window.clearTimeout(z);
    };
    // indirim kodu yalnız "Uygula" ile (indirimUygula sayacı) gönderilsin diye bağımlılıkta değil
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e, secili, ucretliSecim, gizliKod]);

  const indirimUygula = async () => {
    if (!e || !secili.length) return;
    const y = await gonder<{ ara_toplam: number; indirim: number; toplam: number; para_birimi: string }>(`/api/v1/etkinlik/${encodeURIComponent(e.slug)}/fiyat`, {
      kalemler: secili.map((x) => ({ tur_id: x.tur.id, adet: x.adet })),
      indirim_kodu: indirimKodu.trim() || undefined,
      gizli_kod: gizliKod || undefined,
    });
    if (y.ok && y.veri) {
      setFiyat(y.veri);
      setIndirimHatasi(null);
    } else {
      setIndirimHatasi(y.kod || 'genel');
    }
  };

  // Katılımcı adları (çok biletli kayıtta, istenmişse): ilk ad formdaki addan.
  useEffect(() => {
    if (!e?.katilimci_adlari) return;
    setAdlar((eski) => Array.from({ length: Math.max(0, toplamAdet - 1) }, (_, i) => eski[i] || ''));
  }, [toplamAdet, e?.katilimci_adlari]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !e) return <Durum t={t} durum={yukleme} />;

  const tz = e.saat_dilimi;
  const kayitAcik = e.kayit_acik;
  const enCok = (x: AcikTur) => {
    const sinir = e.davet ? e.davet.adet : x.kisi_basi_en_cok;
    return Math.max(0, Math.min(sinir, x.kalan ?? sinir));
  };
  const satilabilir = (x: AcikTur) => kayitAcik && x.satis === 'acik' && !x.dolu;
  const beklemeyeUygun = kayitAcik && e.bekleme_listesi && !e.davet && (e.dolu || e.turler.some((x) => x.dolu && x.satis === 'acik'));
  const pazarlamaMetni = e.pazarlama_metinleri[dil] || e.pazarlama_metinleri.tr || '';

  const adetYaz = (x: AcikTur, n: number) => {
    const sinir = enCok(x);
    const yeni = Math.max(0, Math.min(sinir, n));
    // Davet: toplam davet adedini aşmasın
    if (e.davet) {
      const digerleri = Object.entries(adetler).reduce((a, [k, v]) => (Number(k) === x.id ? a : a + v), 0);
      if (digerleri + yeni > e.davet.adet) return;
    }
    setAdetler({ ...adetler, [x.id]: yeni });
  };

  const kayitGonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (gonderiliyor || !toplamAdet) return;
    setHata(null);
    setGonderiliyor(true);
    const y = await gonder<{ ok: boolean; siparis: { kod: string } | null; jeton: string; bilet_adresi: string; odeme_adresi?: string; odeme_son?: string }>(
      `/api/v1/etkinlik/${encodeURIComponent(e.slug)}/kayit`,
      {
        kalemler: secili.map((x) => ({ tur_id: x.tur.id, adet: x.adet })),
        ad,
        eposta,
        telefon: e.telefon === 'gizli' ? undefined : telefon,
        yanitlar,
        katilimcilar: e.katilimci_adlari && toplamAdet > 1 ? [ad, ...adlar] : [],
        indirim_kodu: ucretliSecim && indirimKodu.trim() ? indirimKodu.trim() : undefined,
        gizli_kod: gizliKod || undefined,
        davet: davet || undefined,
        pazarlama_izni: izin,
        dil,
        web_adresi: balKupu,
      }
    );
    setGonderiliyor(false);
    if (!y.ok || !y.veri) {
      setHata(hataYaz(t, y.kod, y.ek));
      if (y.kod === 'dolu' || y.kod === 'tur_dolu') void yukle();
      return;
    }
    if (!y.veri.siparis) {
      // bal küpü: sessiz
      setHata(null);
      return;
    }
    try {
      if (gomulu) window.parent.postMessage({ tur: 'mk-etkinlik-tamam', kod: y.veri.siparis.kod }, '*');
    } catch {
      /* yok say */
    }
    if (y.veri.odeme_adresi) {
      setOdeme({ adres: y.veri.odeme_adresi, son: y.veri.odeme_son || null, bilet: y.veri.bilet_adresi });
      window.scrollTo?.({ top: 0 });
      return;
    }
    const q = new URLSearchParams();
    if (dil !== e.dil) q.set('dil', dil);
    if (gomulu) q.set('gomulu', '1');
    window.location.assign(`${y.veri.bilet_adresi}${q.toString() ? `?${q.toString()}` : ''}`);
  };

  const beklemeGonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (gonderiliyor) return;
    setHata(null);
    setGonderiliyor(true);
    const y = await gonder<{ ok: boolean; sira?: number }>(`/api/v1/etkinlik/${encodeURIComponent(e.slug)}/bekleme`, {
      ad,
      eposta,
      telefon: e.telefon === 'gizli' ? undefined : telefon,
      adet: bekleme.adet,
      tur_id: bekleme.tur_id ?? undefined,
      gizli_kod: gizliKod || undefined,
      pazarlama_izni: izin,
      dil,
      web_adresi: balKupu,
    });
    setGonderiliyor(false);
    if (!y.ok) {
      setHata(hataYaz(t, y.kod, y.ek));
      return;
    }
    setBekleme({ ...bekleme, tamam: y.veri?.sira || 1 });
  };

  const kapak = gorselAdresi(e.kapak);
  const ustBilgi =
    e.durum === 'iptal'
      ? { renk: 'border-red-300 bg-red-50 text-red-800', metin: t('etkinlikSayfa.durum.iptal') }
      : e.durum === 'tamamlandi'
        ? { renk: 'border-zinc-300 bg-zinc-100 text-zinc-700', metin: t('etkinlikSayfa.durum.tamamlandi') }
        : !kayitAcik
          ? {
              renk: 'border-amber-300 bg-amber-50 text-amber-900',
              metin: t(`etkinlikSayfa.kayitNeden.${e.kayit_neden || 'kayit_kapali'}`, {
                tarih: e.kayit_acilis ? `${tarihYaz(e.kayit_acilis, tz, dil, { dateStyle: 'medium' })} ${saatYaz(e.kayit_acilis, tz, dil)}` : '',
              }),
            }
          : e.dolu
            ? { renk: 'border-amber-300 bg-amber-50 text-amber-900', metin: t(e.bekleme_listesi ? 'etkinlikSayfa.doluBekleme' : 'etkinlikSayfa.dolu') }
            : null;

  // Ödeme bekleniyor ekranı (ücretli kayıt sonrası)
  if (odeme) {
    return (
      <main className="mx-auto max-w-xl" data-testid="etkinlik-odeme">
        <div className={`${KART} p-6 text-center`}>
          <Ticket className="mx-auto mb-3 h-10 w-10 text-purple-600" aria-hidden="true" />
          <h1 className="text-xl font-semibold">{t('etkinlikSayfa.odeme.baslik')}</h1>
          <p className="mt-2 text-sm text-zinc-600">
            {t('etkinlikSayfa.odeme.aciklama', { saat: odeme.son ? saatYaz(odeme.son, tz, dil) : '' })}
          </p>
          <a href={odeme.adres} className="mt-5 inline-flex items-center justify-center gap-2 rounded-xl bg-purple-600 px-5 py-3 font-semibold text-white hover:bg-purple-500" data-testid="etkinlik-odeme-git">
            {t('etkinlikSayfa.odeme.git')}
          </a>
          <p className="mt-4 text-xs text-zinc-500">
            <a href={odeme.bilet} className="underline">
              {t('etkinlikSayfa.odeme.bilet')}
            </a>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl space-y-4" data-testid="etkinlik-detay" data-slug={e.slug}>
      <article className={`${KART} overflow-hidden`}>
        {kapak ? (
          <img src={kapak} alt="" className="aspect-[2/1] w-full object-cover" width={1200} height={600} />
        ) : (
          <div className="h-2 w-full" style={{ background: e.renk || '#7c3aed' }} aria-hidden="true" />
        )}
        <div className="space-y-4 p-5 sm:p-7">
          <div className="flex flex-wrap items-center gap-2">
            <BicimRozeti t={t} bicim={e.bicim} />
            {e.organizator_ad && (
              <span className="text-xs text-zinc-500">
                {e.organizator_url ? (
                  <a href={e.organizator_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                    {e.organizator_ad}
                  </a>
                ) : (
                  e.organizator_ad
                )}
              </span>
            )}
          </div>
          <h1 className="text-2xl font-bold leading-tight sm:text-3xl" data-testid="etkinlik-baslik">
            {e.baslik}
          </h1>
          {e.ozet && <p className="text-base text-zinc-600">{e.ozet}</p>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Zaman t={t} dil={dil} bas={e.baslangic} bit={e.bitis} tz={tz} oturumlar={e.oturumlar} />
            <Konum t={t} bicim={e.bicim} mekan={e.mekan_adi} adres={e.adres} harita={e.harita} />
          </div>
          {ustBilgi && (
            <p className={`rounded-xl border px-3 py-2 text-sm font-medium ${ustBilgi.renk}`} data-testid="etkinlik-ust-bilgi">
              {ustBilgi.metin}
            </p>
          )}
          {e.aciklama && (
            <div className="etkinlik-aciklama text-[15px] leading-relaxed text-zinc-800" style={{ '--foreground': '240 10% 4%', '--muted-foreground': '240 4% 40%' } as CSSProperties}>
              <GuvenliMarkdown metin={e.aciklama} className="space-y-3" />
            </div>
          )}
        </div>
      </article>

      {e.davet && (
        <p className="rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" data-testid="etkinlik-davet">
          {t('etkinlikSayfa.davet', { tarih: `${tarihYaz(e.davet.son, tz, dil, { dateStyle: 'medium' })} ${saatYaz(e.davet.son, tz, dil)}`, sayi: e.davet.adet })}
        </p>
      )}
      {davetHatasi && <p className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">{hataYaz(t, davetHatasi)}</p>}

      {e.durum === 'yayinda' && (
        <section className={`${KART} p-5 sm:p-7`} aria-labelledby="etkinlik-biletler-baslik">
          <h2 id="etkinlik-biletler-baslik" className="mb-3 text-lg font-semibold">
            {t('etkinlikSayfa.biletler')}
          </h2>
          <ul className="divide-y divide-zinc-100" data-testid="etkinlik-turler">
            {e.turler.map((x) => {
              const n = adetler[x.id] || 0;
              const acik = satilabilir(x);
              return (
                <li key={x.id} className="flex flex-wrap items-center gap-3 py-3" data-tur={x.id}>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{x.ad}</div>
                    {x.aciklama && <div className="text-sm text-zinc-600">{x.aciklama}</div>}
                    <div className="mt-0.5 text-xs text-zinc-500">
                      {x.satis === 'baslamadi' && x.satis_bas
                        ? t('etkinlikSayfa.satisBaslamadi', { tarih: `${tarihYaz(x.satis_bas, tz, dil, { dateStyle: 'medium' })} ${saatYaz(x.satis_bas, tz, dil)}` })
                        : x.satis === 'bitti'
                          ? t('etkinlikSayfa.satisBitti')
                          : x.dolu
                            ? t('etkinlikSayfa.turDolu')
                            : x.kalan != null && x.kalan <= 10
                              ? t('etkinlikSayfa.sonBiletler', { sayi: x.kalan })
                              : x.satis_bit
                                ? t('etkinlikSayfa.satisSonu', { tarih: `${tarihYaz(x.satis_bit, tz, dil, { dateStyle: 'medium' })} ${saatYaz(x.satis_bit, tz, dil)}` })
                                : ''}
                    </div>
                  </div>
                  <div className="text-end font-semibold tabular-nums">{x.fiyat > 0 ? paraYaz(x.fiyat, x.para_birimi, dil) : t('etkinlikSayfa.ucretsiz')}</div>
                  <div className="flex items-center gap-1" role="group" aria-label={t('etkinlikSayfa.adet', { ad: x.ad })}>
                    <button
                      type="button"
                      onClick={() => adetYaz(x, n - 1)}
                      disabled={!acik || n <= 0}
                      className="flex h-9 w-9 items-center justify-center rounded-full border border-zinc-300 disabled:opacity-30"
                      aria-label={t('etkinlikSayfa.azalt')}
                    >
                      <Minus className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <span className="w-7 text-center font-semibold tabular-nums" data-testid={`etkinlik-adet-${x.id}`}>
                      {n}
                    </span>
                    <button
                      type="button"
                      onClick={() => adetYaz(x, n + 1)}
                      disabled={!acik || n >= enCok(x)}
                      className="flex h-9 w-9 items-center justify-center rounded-full border border-zinc-300 disabled:opacity-30"
                      aria-label={t('etkinlikSayfa.artir')}
                      data-testid={`etkinlik-artir-${x.id}`}
                    >
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          {e.gizli_tur_var && !gizliKod && (
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-zinc-600">{t('etkinlikSayfa.gizliKodSoru')}</summary>
              <div className="mt-2 flex gap-2">
                <input value={kodGirdisi} onChange={(x) => setKodGirdisi(x.target.value.toUpperCase())} className={`${GIRDI} max-w-xs`} maxLength={40} aria-label={t('etkinlikSayfa.gizliKod')} dir="ltr" />
                <button type="button" onClick={() => kodGirdisi.trim() && setGizliKod(kodGirdisi.trim())} className="rounded-xl border border-zinc-300 px-4 py-2 font-medium hover:bg-zinc-50">
                  {t('etkinlikSayfa.uygula')}
                </button>
              </div>
            </details>
          )}
          {e.odeme_notu && <p className="mt-3 whitespace-pre-line rounded-xl bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{e.odeme_notu}</p>}
        </section>
      )}

      {bekleme.tamam != null ? (
        <section className={`${KART} p-5 text-center`} data-testid="etkinlik-bekleme-tamam">
          <CheckCircle2 className="mx-auto mb-2 h-10 w-10 text-emerald-600" aria-hidden="true" />
          <p className="font-semibold">{t('etkinlikSayfa.bekleme.tamam', { sayi: bekleme.tamam })}</p>
          <p className="mt-1 text-sm text-zinc-600">{t('etkinlikSayfa.bekleme.tamamAciklama')}</p>
        </section>
      ) : bekleme.acik ? (
        <form onSubmit={beklemeGonder} className={`${KART} space-y-3 p-5 sm:p-7`} data-testid="etkinlik-bekleme-formu">
          <h2 className="text-lg font-semibold">{t('etkinlikSayfa.bekleme.baslik')}</h2>
          <p className="text-sm text-zinc-600">{t('etkinlikSayfa.bekleme.aciklama')}</p>
          <KisiAlanlari t={t} ad={ad} setAd={setAd} eposta={eposta} setEposta={setEposta} telefon={telefon} setTelefon={setTelefon} kural={e.telefon} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block font-medium">{t('etkinlikSayfa.bekleme.tur')}</span>
              <select className={GIRDI} value={bekleme.tur_id ?? ''} onChange={(x) => setBekleme({ ...bekleme, tur_id: x.target.value ? Number(x.target.value) : null })}>
                <option value="">{t('etkinlikSayfa.bekleme.herhangi')}</option>
                {e.turler.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.ad}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">{t('etkinlikSayfa.bekleme.adet')}</span>
              <input type="number" min={1} max={20} value={bekleme.adet} onChange={(x) => setBekleme({ ...bekleme, adet: Math.max(1, Math.min(20, Number(x.target.value) || 1)) })} className={GIRDI} />
            </label>
          </div>
          <IzinVeBalKupu t={t} metin={pazarlamaMetni} izin={izin} setIzin={setIzin} balKupu={balKupu} setBalKupu={setBalKupu} kvkk={e.kvkk_metni} />
          {hata && (
            <p className="rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
              {hata}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={gonderiliyor} className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-5 py-3 font-semibold text-white hover:bg-purple-500 disabled:opacity-60" data-testid="etkinlik-bekleme-gonder">
              {gonderiliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('etkinlikSayfa.bekleme.gonder')}
            </button>
            <button type="button" onClick={() => setBekleme({ ...bekleme, acik: false })} className="rounded-xl border border-zinc-300 px-4 py-3 font-medium">
              {t('etkinlikSayfa.vazgec')}
            </button>
          </div>
        </form>
      ) : (
        <>
          {beklemeyeUygun && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm">
              <span>{t('etkinlikSayfa.bekleme.davetMetni')}</span>
              <button type="button" onClick={() => setBekleme({ ...bekleme, acik: true, tur_id: e.turler.find((x) => x.dolu)?.id ?? null })} className="rounded-xl border border-purple-300 px-4 py-2 font-medium text-purple-700 hover:bg-purple-50" data-testid="etkinlik-bekleme-ac">
                {t('etkinlikSayfa.bekleme.katil')}
              </button>
            </div>
          )}
          {e.durum === 'yayinda' && kayitAcik && toplamAdet > 0 && (
            <form onSubmit={kayitGonder} className={`${KART} space-y-3 p-5 sm:p-7`} data-testid="etkinlik-kayit-formu">
              <h2 className="text-lg font-semibold">{t('etkinlikSayfa.form.baslik')}</h2>
              <KisiAlanlari t={t} ad={ad} setAd={setAd} eposta={eposta} setEposta={setEposta} telefon={telefon} setTelefon={setTelefon} kural={e.telefon} />
              {e.katilimci_adlari && adlar.length > 0 && (
                <fieldset className="space-y-2">
                  <legend className="mb-1 text-sm font-medium">{t('etkinlikSayfa.form.katilimcilar')}</legend>
                  {adlar.map((x, i) => (
                    <input
                      key={i}
                      required
                      value={x}
                      maxLength={120}
                      onChange={(ev) => setAdlar(adlar.map((y, j) => (j === i ? ev.target.value : y)))}
                      placeholder={t('etkinlikSayfa.form.katilimci', { sayi: i + 2 })}
                      aria-label={t('etkinlikSayfa.form.katilimci', { sayi: i + 2 })}
                      className={GIRDI}
                    />
                  ))}
                </fieldset>
              )}
              {e.sorular.map((s) => (
                <SoruAlani key={s.id} t={t} s={s} deger={yanitlar[s.id]} onDegis={(v) => setYanitlar({ ...yanitlar, [s.id]: v })} />
              ))}
              {ucretliSecim && e.indirim_var && (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="block min-w-[10rem] flex-1 text-sm">
                    <span className="mb-1 block font-medium">{t('etkinlikSayfa.form.indirim')}</span>
                    <input value={indirimKodu} onChange={(x) => setIndirimKodu(x.target.value.toUpperCase())} className={GIRDI} maxLength={40} dir="ltr" data-testid="etkinlik-indirim-kodu" />
                  </label>
                  <button type="button" onClick={() => void indirimUygula()} className="rounded-xl border border-zinc-300 px-4 py-2.5 font-medium hover:bg-zinc-50" data-testid="etkinlik-indirim-uygula">
                    {t('etkinlikSayfa.uygula')}
                  </button>
                  {indirimHatasi && <p className="w-full text-sm text-red-700">{hataYaz(t, indirimHatasi)}</p>}
                </div>
              )}
              {ucretliSecim && fiyat && (
                <dl className="space-y-1 rounded-xl bg-zinc-50 px-4 py-3 text-sm" data-testid="etkinlik-fiyat">
                  <div className="flex justify-between">
                    <dt>{t('etkinlikSayfa.form.araToplam')}</dt>
                    <dd className="tabular-nums">{paraYaz(fiyat.ara_toplam, fiyat.para_birimi, dil)}</dd>
                  </div>
                  {fiyat.indirim > 0 && (
                    <div className="flex justify-between text-emerald-700">
                      <dt>{t('etkinlikSayfa.form.indirimTutari')}</dt>
                      <dd className="tabular-nums">−{paraYaz(fiyat.indirim, fiyat.para_birimi, dil)}</dd>
                    </div>
                  )}
                  <div className="flex justify-between text-base font-semibold">
                    <dt>{t('etkinlikSayfa.form.toplam')}</dt>
                    <dd className="tabular-nums">{paraYaz(fiyat.toplam, fiyat.para_birimi, dil)}</dd>
                  </div>
                </dl>
              )}
              {e.iade_politikasi && (
                <details className="text-sm text-zinc-600">
                  <summary className="cursor-pointer font-medium">{t('etkinlikSayfa.iadePolitikasi')}</summary>
                  <p className="mt-1 whitespace-pre-line">{e.iade_politikasi}</p>
                </details>
              )}
              <IzinVeBalKupu t={t} metin={pazarlamaMetni} izin={izin} setIzin={setIzin} balKupu={balKupu} setBalKupu={setBalKupu} kvkk={e.kvkk_metni} />
              {hata && (
                <p className="rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert" data-testid="etkinlik-kayit-hata">
                  {hata}
                </p>
              )}
              <button type="submit" disabled={gonderiliyor} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-purple-600 px-5 py-3 text-base font-semibold text-white hover:bg-purple-500 disabled:opacity-60 sm:w-auto" data-testid="etkinlik-kayit-gonder">
                {gonderiliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {ucretliSecim ? t('etkinlikSayfa.form.odemeyeGec') : t('etkinlikSayfa.form.kaydol', { sayi: toplamAdet })}
              </button>
            </form>
          )}
          {e.durum === 'yayinda' && kayitAcik && toplamAdet === 0 && e.turler.some(satilabilir) && (
            <p className="text-center text-sm text-zinc-500" data-testid="etkinlik-sec-ipucu">
              {t('etkinlikSayfa.secIpucu')}
            </p>
          )}
        </>
      )}
    </main>
  );
}

function KisiAlanlari({ t, ad, setAd, eposta, setEposta, telefon, setTelefon, kural }: { t: TFunction; ad: string; setAd: (v: string) => void; eposta: string; setEposta: (v: string) => void; telefon: string; setTelefon: (v: string) => void; kural: TelefonKurali }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block text-sm">
        <span className="mb-1 block font-medium">{t('etkinlikSayfa.form.ad')}</span>
        <input required maxLength={120} autoComplete="name" value={ad} onChange={(x) => setAd(x.target.value)} className={GIRDI} data-testid="etkinlik-ad" />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">{t('etkinlikSayfa.form.eposta')}</span>
        <input required type="email" maxLength={254} autoComplete="email" value={eposta} onChange={(x) => setEposta(x.target.value)} className={GIRDI} dir="ltr" data-testid="etkinlik-eposta" />
      </label>
      {kural !== 'gizli' && (
        <label className="block text-sm sm:col-span-2">
          <span className="mb-1 block font-medium">
            {t('etkinlikSayfa.form.telefon')}
            {kural === 'istege_bagli' && <span className="font-normal text-zinc-500"> ({t('etkinlikSayfa.form.istegeBagli')})</span>}
          </span>
          <input required={kural === 'zorunlu'} type="tel" maxLength={24} autoComplete="tel" value={telefon} onChange={(x) => setTelefon(x.target.value)} className={GIRDI} dir="ltr" data-testid="etkinlik-telefon" />
        </label>
      )}
    </div>
  );
}

function SoruAlani({ t, s, deger, onDegis }: { t: TFunction; s: Soru; deger: string | boolean | undefined; onDegis: (v: string | boolean) => void }) {
  const etiket = (
    <span className="mb-1 block font-medium">
      {s.etiket}
      {!s.zorunlu && <span className="font-normal text-zinc-500"> ({t('etkinlikSayfa.form.istegeBagli')})</span>}
    </span>
  );
  if (s.tur === 'onay') {
    return (
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" required={s.zorunlu} checked={deger === true} onChange={(x) => onDegis(x.target.checked)} className="mt-0.5 h-4 w-4 accent-purple-600" />
        <span>{s.etiket}</span>
      </label>
    );
  }
  if (s.tur === 'secim') {
    return (
      <label className="block text-sm">
        {etiket}
        <select required={s.zorunlu} value={typeof deger === 'string' ? deger : ''} onChange={(x) => onDegis(x.target.value)} className={GIRDI}>
          <option value="">{t('etkinlikSayfa.form.sec')}</option>
          {s.secenekler.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <label className="block text-sm">
      {etiket}
      {s.tur === 'uzun' ? (
        <textarea required={s.zorunlu} maxLength={2000} rows={3} value={typeof deger === 'string' ? deger : ''} onChange={(x) => onDegis(x.target.value)} className={GIRDI} />
      ) : (
        <input required={s.zorunlu} maxLength={300} value={typeof deger === 'string' ? deger : ''} onChange={(x) => onDegis(x.target.value)} className={GIRDI} />
      )}
    </label>
  );
}

function IzinVeBalKupu({ t, metin, izin, setIzin, balKupu, setBalKupu, kvkk }: { t: TFunction; metin: string; izin: boolean; setIzin: (v: boolean) => void; balKupu: string; setBalKupu: (v: string) => void; kvkk: string }) {
  return (
    <>
      {/* Bal küpü: insan görmez, bot doldurur (sunucu sessizce yok sayar). */}
      <div className="absolute -left-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
        <label>
          Web
          <input tabIndex={-1} autoComplete="off" value={balKupu} onChange={(x) => setBalKupu(x.target.value)} name="web_adresi" />
        </label>
      </div>
      {metin && (
        <label className="flex items-start gap-2 text-sm text-zinc-700">
          <input type="checkbox" checked={izin} onChange={(x) => setIzin(x.target.checked)} className="mt-0.5 h-4 w-4 accent-purple-600" data-testid="etkinlik-pazarlama-izni" />
          <span>
            {metin} <span className="text-zinc-500">({t('etkinlikSayfa.form.istegeBagli')})</span>
          </span>
        </label>
      )}
      <p className="text-xs text-zinc-500" data-testid="etkinlik-kvkk">
        {kvkk || t('etkinlikSayfa.form.kvkk')}
      </p>
    </>
  );
}

// ===========================================================================
// Bilet sayfası
// ===========================================================================
function BiletGorunum({ jeton, t, dil, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { slug: string; jeton: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [v, setV] = useState<BiletVerisi | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    setIndeks(false);
    void (async () => {
      const y = await getir<BiletVerisi>(`/api/v1/etkinlik/bilet/${encodeURIComponent(jeton)}`);
      if (iptal) return;
      await hazirla(y.veri?.siparis.dil || y.veri?.etkinlik.dil || 'tr');
      if (!y.veri) {
        setYukleme(durumYukleme(y.durum, y.kod));
        return;
      }
      setV(y.veri);
      setBaslik(y.veri.etkinlik.baslik);
      setYukleme('hazir');
    })();
    return () => {
      iptal = true;
    };
  }, [jeton, hazirla, setBaslik, setIndeks]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !v) return <Durum t={t} durum={yukleme} />;

  const e = v.etkinlik;
  const tz = e.saat_dilimi;
  const iptalEt = async (kodlar?: string[]) => {
    if (!window.confirm(t(kodlar ? 'etkinlikSayfa.bilet.iptalOnayTek' : 'etkinlikSayfa.bilet.iptalOnay'))) return;
    setMesgul(true);
    setHata(null);
    const y = await gonder<BiletVerisi>(`/api/v1/etkinlik/bilet/${encodeURIComponent(jeton)}/iptal`, kodlar ? { kodlar } : {});
    setMesgul(false);
    if (y.ok && y.veri) setV(y.veri);
    else setHata(hataYaz(t, y.kod, y.ek));
  };
  const sd = v.siparis.durum;
  const bant =
    e.durum === 'iptal'
      ? { renk: 'border-red-300 bg-red-50 text-red-800', metin: t('etkinlikSayfa.durum.iptal') }
      : sd === 'odeme_bekliyor'
        ? { renk: 'border-amber-300 bg-amber-50 text-amber-900', metin: t('etkinlikSayfa.bilet.odemeBekliyor', { saat: v.siparis.odeme_son ? saatYaz(v.siparis.odeme_son, tz, dil) : '' }) }
        : sd === 'iptal'
          ? { renk: 'border-red-300 bg-red-50 text-red-800', metin: t('etkinlikSayfa.bilet.siparisIptal') }
          : sd === 'suresi_doldu'
            ? { renk: 'border-zinc-300 bg-zinc-100 text-zinc-700', metin: t('etkinlikSayfa.bilet.suresiDoldu') }
            : sd === 'iade_gerekli'
              ? { renk: 'border-amber-300 bg-amber-50 text-amber-900', metin: t('etkinlikSayfa.bilet.iadeGerekli') }
              : { renk: 'border-emerald-300 bg-emerald-50 text-emerald-900', metin: t('etkinlikSayfa.bilet.onayli') };

  return (
    <main className="mx-auto max-w-2xl space-y-4" data-testid="etkinlik-bilet" data-siparis-durum={sd}>
      <section className={`${KART} space-y-3 p-5 sm:p-7`}>
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{t('etkinlikSayfa.bilet.baslik', { kod: v.siparis.kod })}</p>
        <h1 className="text-2xl font-bold leading-tight">
          <a href={`/etkinlik/${e.slug}`} className="hover:underline">
            {e.baslik}
          </a>
        </h1>
        <p className={`rounded-xl border px-3 py-2 text-sm font-medium ${bant.renk}`} data-testid="etkinlik-bilet-bant">
          {bant.metin}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Zaman t={t} dil={dil} bas={e.baslangic} bit={e.bitis} tz={tz} oturumlar={e.oturumlar} />
          <Konum t={t} bicim={e.bicim} mekan={e.mekan_adi} adres={e.adres} harita={e.harita} online={e.online_baglanti} />
        </div>
        {v.siparis.odeme_adresi && (
          <a href={v.siparis.odeme_adresi} className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-5 py-3 font-semibold text-white hover:bg-purple-500" data-testid="etkinlik-bilet-ode">
            {t('etkinlikSayfa.odeme.git')}
          </a>
        )}
        {(v.pdf_adresi || v.takvim) && (
          <div className="flex flex-wrap gap-2 pt-1">
            {v.pdf_adresi && (
              <a href={`${api()}${v.pdf_adresi}`} className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-50" data-testid="etkinlik-bilet-pdf">
                <Download className="h-4 w-4" aria-hidden="true" />
                {t('etkinlikSayfa.bilet.pdf')}
              </a>
            )}
            {v.ics_adresi && (
              <a href={`${api()}${v.ics_adresi}`} className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-50" data-testid="etkinlik-bilet-ics">
                <CalendarPlus className="h-4 w-4" aria-hidden="true" />
                {t('etkinlikSayfa.bilet.ics')}
              </a>
            )}
            {v.takvim && (
              <>
                <a href={v.takvim.google} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-50">
                  Google
                </a>
                <a href={v.takvim.outlook} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-50">
                  Outlook
                </a>
              </>
            )}
          </div>
        )}
      </section>

      <ul className="grid gap-4 sm:grid-cols-2" data-testid="etkinlik-bilet-listesi">
        {v.biletler.map((b) => (
          <li key={b.kod} className={`${KART} flex flex-col items-center gap-2 p-5 text-center ${b.durum === 'iptal' ? 'opacity-60' : ''}`} data-kod={b.kod} data-durum={b.durum}>
            {b.qr_adresi ? (
              <img src={`${api()}${b.qr_adresi}`} alt={t('etkinlikSayfa.bilet.qrAlt', { kod: b.kod })} width={220} height={220} className="h-56 w-56 rounded-xl bg-white" data-testid="etkinlik-bilet-qr" />
            ) : (
              <div className="flex h-56 w-56 items-center justify-center rounded-xl bg-zinc-100 px-4 text-sm text-zinc-500">{t(`etkinlikSayfa.bilet.durum.${b.durum}`)}</div>
            )}
            <code className="bg-transparent text-lg font-bold tracking-[0.2em] text-zinc-900" dir="ltr" data-testid="etkinlik-bilet-kod">
              {b.kod}
            </code>
            <div className="text-sm">
              <span className="font-medium">{b.tur}</span>
              {b.katilimci_ad && <span className="text-zinc-600"> · {b.katilimci_ad}</span>}
            </div>
            {b.giris_at && (
              <p className="inline-flex items-center gap-1 text-sm text-emerald-700">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {t('etkinlikSayfa.bilet.girisYapildi', { saat: saatYaz(b.giris_at, tz, dil) })}
              </p>
            )}
            {b.durum === 'iptal' && <p className="text-sm text-red-700">{t('etkinlikSayfa.bilet.durum.iptal')}{b.iade === 'bekliyor' ? ` · ${t('etkinlikSayfa.bilet.iadeBekliyor')}` : b.iade === 'yapildi' ? ` · ${t('etkinlikSayfa.bilet.iadeYapildi')}` : ''}</p>}
            {v.iptal_edilebilir && b.durum !== 'iptal' && !b.giris_at && v.biletler.filter((x) => x.durum !== 'iptal').length > 1 && (
              <button type="button" disabled={mesgul} onClick={() => void iptalEt([b.kod])} className="text-xs text-red-700 underline disabled:opacity-50">
                {t('etkinlikSayfa.bilet.buBiletiIptal')}
              </button>
            )}
          </li>
        ))}
      </ul>

      <section className={`${KART} space-y-2 p-5 text-sm text-zinc-700`}>
        <p className="inline-flex items-center gap-1.5">
          <Clock className="h-4 w-4 text-zinc-500" aria-hidden="true" />
          {v.iptal_edilebilir
            ? t('etkinlikSayfa.bilet.iptalSonu', { tarih: `${tarihYaz(v.iptal_son, tz, dil, { dateStyle: 'medium' })} ${saatYaz(v.iptal_son, tz, dil)}` })
            : t('etkinlikSayfa.bilet.iptalYok')}
        </p>
        {e.iade_politikasi && <p className="whitespace-pre-line text-zinc-600">{e.iade_politikasi}</p>}
        {hata && (
          <p className="rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-red-800" role="alert">
            {hata}
          </p>
        )}
        {v.iptal_edilebilir && (
          <button type="button" disabled={mesgul} onClick={() => void iptalEt()} className="inline-flex items-center gap-1.5 rounded-xl border border-red-300 px-4 py-2 font-medium text-red-700 hover:bg-red-50 disabled:opacity-50" data-testid="etkinlik-bilet-iptal">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('etkinlikSayfa.bilet.iptal')}
          </button>
        )}
        <p className="text-xs text-zinc-500">{t('etkinlikSayfa.bilet.gizlilik')}</p>
      </section>
    </main>
  );
}

// ===========================================================================
// Hesabın etkinlik listesi
// ===========================================================================
function ListeGorunum({ slug, t, dil, gomulu, hazirla, setBaslik, setIndeks }: OrtakOzellikler & { slug: string }) {
  const [yukleme, setYukleme] = useState<Yukleme>('yukleniyor');
  const [v, setV] = useState<ListeVerisi | null>(null);
  const [gecmis, setGecmis] = useState(false);

  useEffect(() => {
    let iptal = false;
    setIndeks(false);
    void (async () => {
      const y = await getir<ListeVerisi>(`/api/v1/etkinlikler/${encodeURIComponent(slug)}${gecmis ? '?gecmis=true' : ''}`);
      if (iptal) return;
      await hazirla(i18n.language || 'tr');
      if (!y.veri) {
        setYukleme(durumYukleme(y.durum, y.kod));
        return;
      }
      setV(y.veri);
      setBaslik(y.veri.baslik);
      setYukleme('hazir');
    })();
    return () => {
      iptal = true;
    };
  }, [slug, gecmis, hazirla, setBaslik, setIndeks]);

  if (yukleme === 'yukleniyor' || !t) return <Yukleniyor t={t} />;
  if (yukleme !== 'hazir' || !v) return <Durum t={t} durum={yukleme} />;

  return (
    <main className="mx-auto max-w-3xl space-y-4" data-testid="etkinlik-liste-sayfasi">
      <header>
        <h1 className="text-2xl font-bold">{v.baslik}</h1>
        {v.aciklama && <p className="mt-1 whitespace-pre-line text-zinc-600">{v.aciklama}</p>}
      </header>
      <div className="inline-flex rounded-xl border border-zinc-200 bg-white p-1 text-sm" role="tablist">
        {[false, true].map((g) => (
          <button key={String(g)} type="button" role="tab" aria-selected={gecmis === g} onClick={() => setGecmis(g)} className={`rounded-lg px-3 py-1.5 font-medium ${gecmis === g ? 'bg-purple-600 text-white' : 'text-zinc-600'}`}>
            {t(g ? 'etkinlikSayfa.liste.gecmis' : 'etkinlikSayfa.liste.yaklasan')}
          </button>
        ))}
      </div>
      {v.etkinlikler.length === 0 ? (
        <p className="py-10 text-center text-zinc-500">{t('etkinlikSayfa.liste.bos')}</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {v.etkinlikler.map((x) => {
            const kapak = gorselAdresi(x.kapak);
            return (
              <li key={x.slug} className={`${KART} overflow-hidden`}>
                <a href={`/etkinlik/${x.slug}${gomulu ? '?gomulu=1' : ''}`} className="block h-full hover:bg-zinc-50">
                  {kapak ? <img src={kapak} alt="" loading="lazy" className="aspect-[2/1] w-full object-cover" width={600} height={300} /> : <div className="h-2" style={{ background: x.renk || '#7c3aed' }} aria-hidden="true" />}
                  <div className="space-y-1.5 p-4">
                    <div className="flex flex-wrap gap-1.5">
                      <BicimRozeti t={t} bicim={x.bicim} />
                      {x.ucretsiz && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">{t('etkinlikSayfa.ucretsiz')}</span>}
                      {x.durum === 'iptal' ? (
                        <span className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700">{t('etkinlikSayfa.liste.iptal')}</span>
                      ) : x.dolu ? (
                        <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">{t('etkinlikSayfa.liste.dolu')}</span>
                      ) : null}
                    </div>
                    <h2 className="font-semibold leading-snug">{x.baslik}</h2>
                    <p className="text-sm text-zinc-600">{aralikYaz(x.baslangic, x.bitis, x.saat_dilimi, dil)}</p>
                    {x.mekan_adi && <p className="text-sm text-zinc-500">{x.mekan_adi}</p>}
                    {x.ozet && <p className="line-clamp-2 text-sm text-zinc-600">{x.ozet}</p>}
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

// ===========================================================================
// Kapı okutucu (görevli bağlantısı / panel)
// ===========================================================================
function OkutGorunum({ gorunum, jeton, eid, t, dil, setBaslik }: { gorunum: 'giris' | 'okut'; jeton: string; eid: number; t: TFunction | null; dil: string; setBaslik: (b: string) => void }) {
  const istemci = useMemo(() => (gorunum === 'giris' ? gorevliIstemcisi(jeton) : panelIstemcisi(eid, sorgu('mod') === 'yonetici')), [gorunum, jeton, eid]);
  const baslikYaz = useCallback((b: string) => setBaslik(b), [setBaslik]);
  if (!t) return <Yukleniyor t={t} />;
  return (
    <Suspense fallback={<Yukleniyor t={t} />}>
      <Okutucu istemci={istemci} t={t} dil={dil} panelAdresi={gorunum === 'okut' ? (sorgu('mod') === 'yonetici' ? '/admin' : '/client') : undefined} onBaslik={baslikYaz} />
    </Suspense>
  );
}
