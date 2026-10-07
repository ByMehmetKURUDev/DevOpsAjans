import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import {
  ArrowLeft,
  CalendarCheck,
  CalendarPlus,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Globe,
  Loader2,
  MapPin,
  Phone,
  Users,
  Video,
} from 'lucide-react';

import { rozetGorunur } from '@/components/marka/MarkaParcalari';
import { getAPIBaseURL } from '@/lib/config';
import { ZEMIN_RENKLERI, etkinRenk, markaKabugu, markaLogoAdresi, markaTemasi, type AcikMarka } from '@/lib/marka';
import {
  DIL_ADLARI,
  RANDEVU_DILLERI,
  ayAdiYaz,
  ayIzgarasi,
  aydakiGunSayisi,
  bugun,
  dilSec,
  gunAdiYaz,
  haftaGunleri,
  hataKodu,
  isoGun,
  saatDilimleri,
  saatYaz,
  tarayiciSaatDilimi,
  tarihYaz,
  tzFarki,
  type KonumTuru,
  type Musaitlik,
  type RandevuDili,
  type Slot,
  type Soru,
  type TelefonSecenegi,
} from '@/lib/randevuOrtak';
import { LANGUAGE_CODES, localizedPath } from '../../prerender/site.js';

/**
 * Faz 5R — herkese açık randevu sayfası.
 *
 *   /randevu/<slug>            hesabın sayfası: etkinlik türleri
 *   /randevu/<slug>/<tür>      takvim (ay + gün) → saat → form → onay
 *   /randevu/yonet/<jeton>     imzalı yönetim bağlantısı: iptal / yeniden planla (girişsiz)
 *
 * Site düzeninin (Layout) DIŞINDA, lazy; ana paketi büyütmüyor, prerender
 * edilmiyor, site haritasına girmiyor; varsayılan `noindex`. Paylaşım önizlemesi
 * Pages Function'ında (`functions/randevu/[[yol]].js`). `?gomulu=1` gömülü
 * pencere (`public/randevu-widget.js`): sade görünüm, yüksekliği üst sayfaya bildirir.
 * Saatler ziyaretçinin saat diliminde (tarayıcıdan; seçilebilir), sunucu UTC saklar.
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/randevuSayfa/*.json');
const yuklenenDiller = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenenDiller.has(d)) continue;
    const yukleyici = EK_PAKETLER[`../i18n/ek/randevuSayfa/${d}.json`];
    if (!yukleyici) continue;
    const mod = await yukleyici();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenenDiller.add(d);
  }
}

function depoOku(anahtar: string): string | null {
  try {
    return localStorage.getItem(anahtar);
  } catch {
    return null;
  }
}

function depoYaz(anahtar: string, deger: string): void {
  try {
    localStorage.setItem(anahtar, deger);
  } catch {
    /* gizli sekme: yalnız bellekte */
  }
}

function sorgu(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

const API = () => getAPIBaseURL();

interface AcikTur {
  slug: string;
  ad: string;
  aciklama: string;
  sure_dk: number;
  konum_turu: KonumTuru;
  konum: string | null;
  renk: string;
  kapasite: number;
  ev_sahipleri: string[];
  ekip: boolean;
  telefon?: TelefonSecenegi;
  sorular?: Soru[];
  en_gec_gun?: number;
}

interface AcikSayfa {
  slug: string;
  baslik: string;
  karsilama: string;
  logo: string | null;
  renk: string;
  saat_dilimi: string;
  dil: RandevuDili;
  indekslenebilir: boolean;
  saklama_gun: number;
  iptal_sinir_dk: number;
  ajans: boolean;
  turler?: AcikTur[];
}

interface AcikRandevu {
  uid: string;
  durum: 'onayli' | 'iptal';
  baslangic: string;
  bitis: string;
  onceki_baslangic: string | null;
  ziyaretci_tz: string;
  ad: string | null;
  eposta: string | null;
  konum_turu: KonumTuru;
  konum: string | null;
  telefon: string | null;
  iptal_eden: 'ziyaretci' | 'sahip' | null;
  tur: { slug: string; ad: string; sure_dk: number; renk: string };
  sayfa: { slug: string; baslik: string; renk: string; logo: string | null; dil: RandevuDili; saat_dilimi: string; iptal_sinir_dk: number };
  kisi: string | null;
  degistirilebilir: boolean;
  son_degisiklik: string;
  gecti: boolean;
  takvim?: { google: string; outlook: string; ics: string };
}

type Durum = 'yukleniyor' | 'hazir' | 'yok' | 'pasif' | 'hata' | 'gecersiz' | 'suresi';

const KONUM_IKONU: Record<KonumTuru, typeof Video> = { jitsi: Video, baglanti: Video, telefon: Phone, yuz_yuze: MapPin };

function sureMetni(t: TFunction, dk: number): string {
  if (dk >= 1440 && dk % 1440 === 0) return t('randevuSayfa.sure.gun', { sayi: dk / 1440 });
  if (dk >= 60 && dk % 60 === 0) return t('randevuSayfa.sure.saat', { sayi: dk / 60 });
  return t('randevuSayfa.sure.dk', { sayi: dk });
}

// ---------------------------------------------------------------------------
// Takvim: ay + gün + saat
// ---------------------------------------------------------------------------
function Takvim({
  t,
  dil,
  tz,
  renk,
  adres,
  onSec,
  testid = 'randevu-takvim',
}: {
  t: TFunction;
  dil: string;
  tz: string;
  renk: string;
  adres: (bas: string, gun: number, tz: string) => string;
  onSec: (s: Slot, gun: string) => void;
  testid?: string;
}) {
  const bugunGun = bugun(tz);
  const [ay, setAy] = useState(() => ({ yil: Number(bugunGun.slice(0, 4)), ay: Number(bugunGun.slice(5, 7)) }));
  const [veri, setVeri] = useState<Musaitlik | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [seciliGun, setSeciliGun] = useState<string | null>(null);
  const [ilerleme, setIlerleme] = useState(0);

  useEffect(() => {
    let iptal = false;
    setVeri(null);
    setHata(null);
    const bas = isoGun(ay.yil, ay.ay, 1);
    fetch(adres(bas, aydakiGunSayisi(ay.yil, ay.ay), tz), { headers: { accept: 'application/json' } })
      .then(async (y) => {
        const g = await y.json().catch(() => null);
        if (iptal) return;
        if (!y.ok) {
          setHata(hataKodu(g));
          return;
        }
        const m = g as Musaitlik;
        setVeri(m);
        const gunler = Object.keys(m.gunler).sort();
        // İlk açılışta bu ay boşsa sonraki aylara bak (en çok iki kez).
        if (!gunler.length && ilerleme < 2 && new Date(m.en_gec) > new Date(Date.UTC(ay.yil, ay.ay, 1))) {
          setIlerleme((x) => x + 1);
          setAy((a) => (a.ay === 12 ? { yil: a.yil + 1, ay: 1 } : { yil: a.yil, ay: a.ay + 1 }));
          return;
        }
        setSeciliGun((s) => (s && m.gunler[s] ? s : gunler[0] || null));
      })
      .catch(() => {
        if (!iptal) setHata('ag');
      });
    return () => {
      iptal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ay, tz, adres]);

  const izgara = ayIzgarasi(ay.yil, ay.ay);
  const gunAdlari = haftaGunleri(dil);
  const ilkAy = isoGun(ay.yil, ay.ay, 1) <= bugunGun.slice(0, 8) + '01';
  const slotlar = seciliGun && veri ? veri.gunler[seciliGun] || [] : [];

  return (
    <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_13rem]" data-testid={testid}>
      <div>
        <div className="mb-3 flex items-center justify-between">
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-600 hover:bg-zinc-100 disabled:opacity-30"
            onClick={() => {
              setIlerleme(9);
              setAy((a) => (a.ay === 1 ? { yil: a.yil - 1, ay: 12 } : { yil: a.yil, ay: a.ay - 1 }));
            }}
            disabled={ilkAy}
            aria-label={t('randevuSayfa.takvim.oncekiAy')}
          >
            <ChevronLeft className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
          </button>
          <h3 className="text-base font-semibold" aria-live="polite" data-testid="randevu-ay">
            {ayAdiYaz(ay.yil, ay.ay, dil)}
          </h3>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-600 hover:bg-zinc-100 disabled:opacity-30"
            onClick={() => {
              setIlerleme(9);
              setAy((a) => (a.ay === 12 ? { yil: a.yil + 1, ay: 1 } : { yil: a.yil, ay: a.ay + 1 }));
            }}
            disabled={!!veri && new Date(veri.en_gec) < new Date(Date.UTC(ay.yil, ay.ay, 1))}
            aria-label={t('randevuSayfa.takvim.sonrakiAy')}
          >
            <ChevronRight className="h-5 w-5 rtl:rotate-180" aria-hidden="true" />
          </button>
        </div>
        <table className="w-full table-fixed border-separate border-spacing-1 text-center text-sm" role="grid" aria-label={ayAdiYaz(ay.yil, ay.ay, dil)}>
          <thead>
            <tr>
              {gunAdlari.map((g) => (
                <th key={g} scope="col" className="pb-1 text-[11px] font-medium uppercase text-zinc-500">
                  {g}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {izgara.map((hafta, i) => (
              <tr key={i}>
                {hafta.map((gun, j) => {
                  if (!gun) return <td key={j} />;
                  const musait = !!veri?.gunler[gun]?.length;
                  const secili = gun === seciliGun;
                  return (
                    <td key={j}>
                      <button
                        type="button"
                        disabled={!musait}
                        onClick={() => setSeciliGun(gun)}
                        aria-pressed={secili}
                        aria-label={gunAdiYaz(gun, dil)}
                        className={`mx-auto flex h-10 w-10 items-center justify-center rounded-full text-sm transition-colors ${
                          secili ? 'font-bold text-white' : musait ? 'font-semibold hover:brightness-95' : 'text-zinc-300'
                        } ${gun === bugunGun ? 'ring-1 ring-zinc-400' : ''}`}
                        style={secili ? { background: renk } : musait ? { background: `${renk}1f`, color: renk } : undefined}
                        data-gun={gun}
                        data-musait={musait ? '1' : '0'}
                      >
                        {Number(gun.slice(8))}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {!veri && !hata && (
          <p className="mt-2 flex items-center justify-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            {t('randevuSayfa.yukleniyor')}
          </p>
        )}
        {hata && (
          <p className="mt-2 text-center text-sm text-red-600" role="alert">
            {t(`randevuSayfa.hata.${hata}`, { defaultValue: t('randevuSayfa.hata.genel') })}
          </p>
        )}
        {veri && !Object.keys(veri.gunler).length && (
          <p className="mt-2 text-center text-sm text-zinc-500" data-testid="randevu-ay-bos">
            {t('randevuSayfa.takvim.ayBos')}
          </p>
        )}
      </div>
      <div>
        {seciliGun ? (
          <>
            <h4 className="mb-2 text-sm font-semibold">{gunAdiYaz(seciliGun, dil)}</h4>
            <ul className="grid max-h-[22rem] grid-cols-2 gap-2 overflow-y-auto pe-1 md:grid-cols-1" data-testid="randevu-saatler">
              {slotlar.map((s) => (
                <li key={s.bas}>
                  <button
                    type="button"
                    onClick={() => onSec(s, seciliGun)}
                    className="w-full rounded-xl border-2 bg-white px-3 py-2.5 text-sm font-semibold transition-colors hover:text-white"
                    style={{ borderColor: renk, color: renk }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = renk)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '#fff')}
                    data-slot={s.bas}
                  >
                    <span dir="ltr">{saatYaz(s.bas, tz, dil)}</span>
                    {veri && veri.kapasite > 1 && <span className="ms-1 text-[11px] font-normal opacity-80">· {t('randevuSayfa.takvim.yer', { sayi: s.kalan })}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          veri && <p className="text-sm text-zinc-500">{t('randevuSayfa.takvim.gunSec')}</p>
        )}
      </div>
    </div>
  );
}

function SaatDilimiSecici({ t, dil, tz, onDegis }: { t: TFunction; dil: string; tz: string; onDegis: (tz: string) => void }) {
  const liste = useMemo(() => saatDilimleri([tz, tarayiciSaatDilimi()]), [tz]);
  return (
    <label className="mt-4 flex flex-wrap items-center gap-2 text-sm text-zinc-600">
      <Globe className="h-4 w-4" aria-hidden="true" />
      <span>{t('randevuSayfa.saatDilimi')}</span>
      <select value={tz} onChange={(e) => onDegis(e.target.value)} className="max-w-full rounded-lg border border-zinc-200 bg-white px-2 py-1 text-sm" data-testid="randevu-tz">
        {liste.map((z) => (
          <option key={z} value={z}>
            {z.replace(/_/g, ' ')} ({tzFarki(z, dil)})
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Randevu özeti (onay ve yönetim ekranı ortak)
// ---------------------------------------------------------------------------
function Ozet({ t, dil, r, tz }: { t: TFunction; dil: string; r: AcikRandevu; tz: string }) {
  const Ikon = KONUM_IKONU[r.konum_turu] || Video;
  const baglanti = r.konum && /^https:\/\//.test(r.konum) ? r.konum : null;
  return (
    <dl className="mt-4 space-y-2 text-sm" data-testid="randevu-ozet">
      <div className="flex gap-2">
        <dt className="sr-only">{t('randevuSayfa.onay.ne')}</dt>
        <span className="mt-1 h-3 w-3 flex-none rounded-full" style={{ background: r.tur.renk }} aria-hidden="true" />
        <dd className="font-semibold">{r.tur.ad}</dd>
      </div>
      <div className="flex gap-2">
        <dt className="sr-only">{t('randevuSayfa.onay.neZaman')}</dt>
        <Clock className="mt-0.5 h-4 w-4 flex-none text-zinc-500" aria-hidden="true" />
        <dd>
          <span className="block" data-testid="randevu-ozet-zaman">
            {tarihYaz(r.baslangic, tz, dil)} · <span dir="ltr">{saatYaz(r.baslangic, tz, dil)} – {saatYaz(r.bitis, tz, dil)}</span>
          </span>
          <span className="block text-xs text-zinc-500">
            {tz.replace(/_/g, ' ')} ({tzFarki(tz, dil, new Date(r.baslangic))}) · {sureMetni(t, r.tur.sure_dk)}
          </span>
        </dd>
      </div>
      <div className="flex gap-2">
        <dt className="sr-only">{t('randevuSayfa.onay.nerede')}</dt>
        <Ikon className="mt-0.5 h-4 w-4 flex-none text-zinc-500" aria-hidden="true" />
        <dd className="min-w-0 break-words">
          {t(`randevuSayfa.konum.${r.konum_turu}`)}
          {baglanti ? (
            <a href={baglanti} target="_blank" rel="noopener noreferrer" className="mt-0.5 block truncate text-sm font-medium underline" dir="ltr" data-testid="randevu-toplanti-baglantisi">
              {baglanti}
            </a>
          ) : r.konum ? (
            <span className="block text-zinc-600">{r.konum}</span>
          ) : r.konum_turu === 'telefon' ? (
            <span className="block text-zinc-600">{t('randevuSayfa.onay.biziAranacak', { telefon: r.telefon || '' })}</span>
          ) : null}
        </dd>
      </div>
      {r.kisi && (
        <div className="flex gap-2">
          <dt className="sr-only">{t('randevuSayfa.onay.kiminle')}</dt>
          <Users className="mt-0.5 h-4 w-4 flex-none text-zinc-500" aria-hidden="true" />
          <dd>{r.kisi}</dd>
        </div>
      )}
    </dl>
  );
}

function TakvimeEkle({ t, r, gomulu }: { t: TFunction; r: AcikRandevu; gomulu: boolean }) {
  if (!r.takvim) return null;
  // Gömülü pencerede de takvim sağlayıcısı yeni sekmede açılsın (çerçeve içinde açılmaz).
  const hedef = gomulu ? '_blank' : '_blank';
  return (
    <div className="mt-5">
      <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
        <CalendarPlus className="h-4 w-4" aria-hidden="true" />
        {t('randevuSayfa.onay.takvimeEkle')}
      </p>
      <div className="flex flex-wrap gap-2" data-testid="randevu-takvime-ekle">
        <a href={r.takvim.google} target={hedef} rel="noopener noreferrer" className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm hover:bg-zinc-50">
          Google
        </a>
        <a href={r.takvim.outlook} target={hedef} rel="noopener noreferrer" className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm hover:bg-zinc-50">
          Outlook
        </a>
        <a href={r.takvim.ics} className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm hover:bg-zinc-50" download>
          {t('randevuSayfa.onay.apple')}
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sayfa
// ---------------------------------------------------------------------------
export default function RandevuSayfasi() {
  const { slug = '', tur = '', jeton = '' } = useParams<{ slug: string; tur: string; jeton: string }>();
  const navigate = useNavigate();
  const gomulu = useMemo(() => sorgu('gomulu') === '1', []);
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [sayfa, setSayfa] = useState<AcikSayfa | null>(null);
  const [etkinlik, setEtkinlik] = useState<AcikTur | null>(null);
  const [randevu, setRandevu] = useState<AcikRandevu | null>(null);
  // Faz 4L: hesabın marka teması (sayfanın kendi rengi seçiliyse `sayfa_ozel`).
  const [marka, setMarka] = useState<AcikMarka | null>(null);
  const markaZemini = (() => {
    const mt = markaTemasi(marka);
    return mt ? ZEMIN_RENKLERI[mt.zemin].zemin : null;
  })();
  const [yonetJeton, setYonetJeton] = useState<string>(jeton);
  const [dil, setDil] = useState<RandevuDili>('tr');
  const [t, setT] = useState<TFunction | null>(null);
  const [tz, setTz] = useState(() => depoOku('mk-randevu-tz') || tarayiciSaatDilimi());
  const [secim, setSecim] = useState<Slot | null>(null);
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [telefon, setTelefon] = useState('');
  const [yanitlar, setYanitlar] = useState<Record<string, string | boolean>>({});
  const [balKupu, setBalKupu] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [formHatasi, setFormHatasi] = useState<string | null>(null);
  const [tamam, setTamam] = useState(false);
  // Yönetim ekranı
  const [islem, setIslem] = useState<'yok' | 'iptal' | 'yeniden'>('yok');
  const [neden, setNeden] = useState('');
  const [yeniSecim, setYeniSecim] = useState<Slot | null>(null);
  const [mesaj, setMesaj] = useState<string | null>(null);

  const ekSorgu = useMemo(() => {
    const p = new URLSearchParams();
    if (gomulu) p.set('gomulu', '1');
    const d = sorgu('dil');
    if (d) p.set('dil', d);
    const s = p.toString();
    return s ? `?${s}` : '';
  }, [gomulu]);

  // ------------------------------------------------------------------ veri + dil
  useEffect(() => {
    let iptal = false;
    setDurum('yukleniyor');
    (async () => {
      const yol = jeton
        ? `/api/v1/randevu/islem/${encodeURIComponent(jeton)}`
        : tur
          ? `/api/v1/randevu/${encodeURIComponent(slug)}/${encodeURIComponent(tur)}`
          : `/api/v1/randevu/${encodeURIComponent(slug)}`;
      let yeniDurum: Durum = 'hazir';
      let sayfaDili: string = 'tr';
      try {
        const y = await fetch(`${API()}${yol}`, { headers: { accept: 'application/json' } });
        const g = await y.json().catch(() => null);
        if (iptal) return;
        if (y.ok) {
          setMarka((g as { marka?: AcikMarka } | null)?.marka ?? null);
          if (jeton) {
            const r = g as AcikRandevu;
            setRandevu(r);
            setYonetJeton(jeton);
            sayfaDili = r.sayfa.dil;
          } else if (tur) {
            const v = g as { sayfa: AcikSayfa; tur: AcikTur };
            setSayfa(v.sayfa);
            setEtkinlik(v.tur);
            sayfaDili = v.sayfa.dil;
          } else {
            const v = g as AcikSayfa;
            setSayfa(v);
            sayfaDili = v.dil;
          }
        } else if (y.status === 404) {
          yeniDurum = jeton ? 'gecersiz' : 'yok';
        } else if (y.status === 410) {
          yeniDurum = jeton ? 'suresi' : 'pasif';
        } else {
          yeniDurum = 'hata';
        }
      } catch {
        yeniDurum = 'hata';
      }
      const secilen = dilSec(sorgu('dil'), depoOku('mk-randevu-dil'), sayfaDili);
      await paketYukle(secilen).catch(() => undefined);
      if (iptal) return;
      setDil(secilen);
      setT(() => i18n.getFixedT(secilen));
      setDurum(yeniDurum);
    })();
    return () => {
      iptal = true;
    };
  }, [slug, tur, jeton]);

  const dilDegistir = async (yeni: RandevuDili) => {
    await paketYukle(yeni);
    setDil(yeni);
    setT(() => i18n.getFixedT(yeni));
    depoYaz('mk-randevu-dil', yeni);
  };

  const tzDegistir = (yeni: string) => {
    setTz(yeni);
    depoYaz('mk-randevu-tz', yeni);
  };

  // Belge dili/yönü, başlık, robots; açık zemin. Gömülüde zemin saydam.
  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background, baslik: document.title };
    kok.lang = dil;
    kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    document.body.style.background = gomulu ? 'transparent' : markaZemini || '#f7f7f8';
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      document.title = eski.baslik;
    };
  }, [dil, gomulu, markaZemini]);
  useEffect(() => {
    const ad_ = etkinlik ? `${etkinlik.ad} — ${sayfa?.baslik || ''}` : sayfa?.baslik || randevu?.sayfa.baslik;
    if (ad_) document.title = ad_;
    let etiket = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!etiket) {
      etiket = document.createElement('meta');
      etiket.name = 'robots';
      document.head.appendChild(etiket);
    }
    etiket.content = sayfa?.indekslenebilir && !jeton ? 'index, follow' : 'noindex, nofollow';
  }, [sayfa, etkinlik, randevu, jeton]);

  // Gömülü pencere: yüksekliği üst sayfaya bildir.
  useEffect(() => {
    if (!gomulu || typeof ResizeObserver === 'undefined' || window.parent === window) return;
    // documentElement.scrollHeight çerçevenin kendi yüksekliğinin altına inmiyor (pencere küçülemezdi);
    // gövdenin içerik yüksekliği ölçülüyor (gövdede min-height yok).
    const bildir = () => {
      try {
        const g = document.body;
        const stil = getComputedStyle(g);
        const yukseklik = g.getBoundingClientRect().height + parseFloat(stil.marginTop || '0') + parseFloat(stil.marginBottom || '0');
        window.parent.postMessage({ tur: 'mk-randevu', yukseklik: Math.ceil(yukseklik) }, '*');
      } catch {
        /* üst sayfa yok */
      }
    };
    const gozlemci = new ResizeObserver(bildir);
    gozlemci.observe(document.body);
    bildir();
    return () => gozlemci.disconnect();
  }, [gomulu]);

  const musaitlikAdresi = useCallback(
    (bas: string, gun: number, z: string) =>
      `${API()}/api/v1/randevu/${encodeURIComponent(slug)}/${encodeURIComponent(tur)}/musaitlik?bas=${bas}&gun=${gun}&tz=${encodeURIComponent(z)}`,
    [slug, tur]
  );
  const yenidenAdresi = useCallback(
    (bas: string, gun: number, z: string) =>
      `${API()}/api/v1/randevu/islem/${encodeURIComponent(yonetJeton)}/musaitlik?bas=${bas}&gun=${gun}&tz=${encodeURIComponent(z)}`,
    [yonetJeton]
  );

  const gonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (!secim || !etkinlik || gonderiliyor) return;
    setFormHatasi(null);
    setGonderiliyor(true);
    try {
      const y = await fetch(`${API()}/api/v1/randevu/${encodeURIComponent(slug)}/${encodeURIComponent(tur)}/rezervasyon`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baslangic: secim.bas, tz, ad, eposta, telefon, yanitlar, dil, web_adresi: balKupu }),
      });
      const g = await y.json().catch(() => null);
      if (!y.ok) {
        const kod = hataKodu(g);
        setFormHatasi(kod);
        if (kod === 'dolu') setSecim(null);
        return;
      }
      if (g?.randevu) {
        setRandevu(g.randevu as AcikRandevu);
        setYonetJeton(String(g.jeton || ''));
      }
      setTamam(true);
      try {
        if (gomulu) window.parent.postMessage({ tur: 'mk-randevu-tamam', uid: g?.randevu?.uid || null }, '*');
      } catch {
        /* yok say */
      }
      window.scrollTo?.({ top: 0 });
    } catch {
      setFormHatasi('ag');
    } finally {
      setGonderiliyor(false);
    }
  };

  const yonetIslemi = async (yol: 'iptal' | 'yeniden') => {
    if (!randevu || !t) return;
    setGonderiliyor(true);
    setMesaj(null);
    try {
      const y = await fetch(`${API()}/api/v1/randevu/islem/${encodeURIComponent(yonetJeton)}/${yol}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(yol === 'iptal' ? { neden } : { baslangic: yeniSecim?.bas, tz }),
      });
      const g = await y.json().catch(() => null);
      if (!y.ok) {
        setMesaj(t(`randevuSayfa.hata.${hataKodu(g)}`, { defaultValue: t('randevuSayfa.hata.genel') }));
        if (hataKodu(g) === 'dolu') setYeniSecim(null);
        return;
      }
      const r = g as AcikRandevu;
      // Takvim bağlantıları yeniden planlamada da güncel kalsın.
      setRandevu(r);
      setIslem('yok');
      setYeniSecim(null);
      setMesaj(yol === 'iptal' ? t('randevuSayfa.yonetim.iptalEdildi') : t('randevuSayfa.yonetim.tasindi'));
    } catch {
      setMesaj(t('randevuSayfa.hata.ag'));
    } finally {
      setGonderiliyor(false);
    }
  };

  // ------------------------------------------------------------------ çizim
  if (!t) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-zinc-500" data-testid="randevu-yukleniyor">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  // Faz 4L: sayfanın kendi rengi seçiliyse o; değilse marka rengi. Logo yoksa marka logosu.
  const sayfaRengi = (randevu?.sayfa.renk || sayfa?.renk || '#7c3aed').toLowerCase();
  const renk = etkinRenk(sayfaRengi, marka, sayfaRengi).toLowerCase();
  const markaT = markaTemasi(marka);
  const baslik = randevu?.sayfa.baslik || sayfa?.baslik || '';
  const sayfaLogosu = randevu?.sayfa.logo || sayfa?.logo || null;
  const logo = sayfaLogosu || (markaT ? markaLogoAdresi(markaT.logo) : null);
  // Marka logosu çoğunlukla yatay: kareye kırpılmasın.
  const logoSinifi = sayfaLogosu ? 'h-12 w-12 flex-none rounded-xl object-cover' : 'h-12 w-auto max-w-[10rem] flex-none object-contain';
  const markaOz = markaKabugu(marka, dil, renk);
  const dilDugmesi = (
    <label className="flex items-center gap-1 text-xs text-zinc-500">
      <Globe className="h-3.5 w-3.5" aria-hidden="true" />
      <span className="sr-only">{t('randevuSayfa.dil')}</span>
      <select value={dil} onChange={(e) => void dilDegistir(e.target.value as RandevuDili)} className="rounded border border-zinc-200 bg-white px-1 py-0.5 text-xs" data-testid="randevu-dil">
        {RANDEVU_DILLERI.map((d) => (
          <option key={d} value={d}>
            {DIL_ADLARI[d]}
          </option>
        ))}
      </select>
    </label>
  );

  const kabuk = (icerik: ReactNode, genis = false) => (
    <div
      className={`${gomulu ? 'p-2 sm:p-3' : 'min-h-screen px-3 py-6 sm:px-6 sm:py-10'} text-zinc-900`}
      style={markaT ? { ...markaOz.style, fontFamily: 'var(--marka-yazi-tipi)' } : { fontFamily: 'inherit' }}
      data-marka={markaOz['data-marka']}
      data-testid="randevu-sayfasi"
      data-gomulu={gomulu ? '1' : '0'}
    >
      <main className={`mx-auto ${genis ? 'max-w-4xl' : 'max-w-2xl'} overflow-hidden rounded-3xl bg-white shadow-sm ring-1 ring-zinc-100`}>
        <div className="h-1.5" style={{ background: renk }} aria-hidden="true" />
        <div className="p-5 sm:p-8">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              {logo ? (
                <img src={logo} alt={sayfaLogosu ? '' : markaT?.ad || ''} width={48} height={48} className={logoSinifi} />
              ) : (
                <span className="flex h-12 w-12 flex-none items-center justify-center rounded-xl text-white" style={{ background: renk }}>
                  <CalendarCheck className="h-6 w-6" aria-hidden="true" />
                </span>
              )}
              <p className="truncate text-sm font-medium text-zinc-500">{baslik}</p>
            </div>
            {dilDugmesi}
          </div>
          {icerik}
        </div>
      </main>
      {!gomulu && rozetGorunur(marka) && (
        <footer className="py-6 text-center text-xs text-zinc-400" style={markaT ? { color: 'var(--marka-soluk)' } : undefined} data-testid="marka-rozet">
          <a href="/" target="_blank" rel="noopener" className="hover:text-zinc-600">
            {t('randevuSayfa.hazirlayan')}
          </a>
        </footer>
      )}
    </div>
  );

  if (durum === 'yukleniyor') {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-zinc-500" data-testid="randevu-yukleniyor">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  }
  if (durum !== 'hazir') {
    return kabuk(
      <div className="py-8 text-center" data-testid="randevu-durum" data-durum={durum}>
        <CalendarCheck className="mx-auto mb-3 h-10 w-10 text-zinc-300" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t(`randevuSayfa.durum.${durum}`)}</h1>
        <p className="mt-2 text-sm text-zinc-500">{t(`randevuSayfa.durum.${durum}Aciklama`)}</p>
      </div>
    );
  }

  // ------------------------------------------------------------------ yönetim bağlantısı
  if (jeton && randevu) {
    const r = randevu;
    const rTz = tz;
    const iptalMi = r.durum === 'iptal';
    return kabuk(
      <div data-testid="randevu-yonetim" data-durum={r.durum}>
        <h1 className="text-2xl font-bold">{iptalMi ? t('randevuSayfa.yonetim.iptalBaslik') : t('randevuSayfa.yonetim.baslik')}</h1>
        {r.ad && <p className="mt-1 text-sm text-zinc-500">{t('randevuSayfa.yonetim.merhaba', { ad: r.ad })}</p>}
        {mesaj && (
          <p className="mt-3 rounded-xl bg-zinc-50 p-3 text-sm" role="status" data-testid="randevu-mesaj">
            {mesaj}
          </p>
        )}
        <div className={iptalMi ? 'opacity-60' : ''}>
          <Ozet t={t} dil={dil} r={r} tz={rTz} />
        </div>
        {r.onceki_baslangic && !iptalMi && (
          <p className="mt-2 text-xs text-zinc-500">{t('randevuSayfa.yonetim.onceki', { zaman: `${tarihYaz(r.onceki_baslangic, rTz, dil, { dateStyle: 'medium', timeStyle: 'short' })}` })}</p>
        )}
        {iptalMi ? (
          <div className="mt-6">
            <p className="text-sm text-zinc-600">{r.iptal_eden === 'sahip' ? t('randevuSayfa.yonetim.sahipIptal') : t('randevuSayfa.yonetim.siziIptal')}</p>
            <a href={`/randevu/${r.sayfa.slug}/${r.tur.slug}${ekSorgu}`} className="mt-3 inline-block rounded-xl px-4 py-2.5 text-sm font-semibold text-white" style={{ background: renk }}>
              {t('randevuSayfa.yonetim.yeniRandevu')}
            </a>
          </div>
        ) : r.gecti ? (
          <p className="mt-6 text-sm text-zinc-600">{t('randevuSayfa.yonetim.gecti')}</p>
        ) : (
          <>
            <TakvimeEkle t={t} r={r} gomulu={gomulu} />
            {!r.degistirilebilir ? (
              <p className="mt-6 rounded-xl bg-amber-50 p-3 text-sm text-amber-900" data-testid="randevu-sure-doldu">
                {t('randevuSayfa.yonetim.sureDoldu', { sure: sureMetni(t, r.sayfa.iptal_sinir_dk) })}
              </p>
            ) : islem === 'yok' ? (
              <div className="mt-6 flex flex-wrap gap-2">
                <button type="button" onClick={() => setIslem('yeniden')} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white" style={{ background: renk }} data-testid="randevu-yeniden-ac">
                  {t('randevuSayfa.yonetim.yenidenPlanla')}
                </button>
                <button type="button" onClick={() => setIslem('iptal')} className="rounded-xl border border-zinc-300 px-4 py-2.5 text-sm font-semibold" data-testid="randevu-iptal-ac">
                  {t('randevuSayfa.yonetim.iptalEt')}
                </button>
                <p className="w-full text-xs text-zinc-500">
                  {t('randevuSayfa.yonetim.sonDegisiklik', { zaman: tarihYaz(r.son_degisiklik, rTz, dil, { dateStyle: 'medium', timeStyle: 'short' }) })}
                </p>
              </div>
            ) : islem === 'iptal' ? (
              <div className="mt-6 rounded-2xl border border-zinc-200 p-4">
                <label className="block text-sm">
                  <span className="mb-1 block font-medium">{t('randevuSayfa.yonetim.iptalNedeni')}</span>
                  <textarea value={neden} onChange={(e) => setNeden(e.target.value)} maxLength={500} className="min-h-[80px] w-full rounded-xl border border-zinc-300 p-2 text-sm" data-testid="randevu-iptal-neden" />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" disabled={gonderiliyor} onClick={() => void yonetIslemi('iptal')} className="rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" data-testid="randevu-iptal-onayla">
                    {t('randevuSayfa.yonetim.iptalOnayla')}
                  </button>
                  <button type="button" onClick={() => setIslem('yok')} className="rounded-xl px-4 py-2.5 text-sm">
                    {t('randevuSayfa.vazgec')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-6">
                <h2 className="mb-3 text-base font-semibold">{t('randevuSayfa.yonetim.yeniSaat')}</h2>
                {yeniSecim ? (
                  <div className="rounded-2xl border border-zinc-200 p-4" data-testid="randevu-yeni-saat">
                    <p className="text-sm">
                      {tarihYaz(yeniSecim.bas, rTz, dil)} · <strong dir="ltr">{saatYaz(yeniSecim.bas, rTz, dil)}</strong>
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button type="button" disabled={gonderiliyor} onClick={() => void yonetIslemi('yeniden')} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" style={{ background: renk }} data-testid="randevu-tasi">
                        {t('randevuSayfa.yonetim.tasi')}
                      </button>
                      <button type="button" onClick={() => setYeniSecim(null)} className="rounded-xl px-4 py-2.5 text-sm">
                        {t('randevuSayfa.degistir')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <Takvim t={t} dil={dil} tz={rTz} renk={renk} adres={yenidenAdresi} onSec={(s) => setYeniSecim(s)} />
                    <SaatDilimiSecici t={t} dil={dil} tz={rTz} onDegis={tzDegistir} />
                    <button type="button" onClick={() => setIslem('yok')} className="mt-3 text-sm text-zinc-500 underline">
                      {t('randevuSayfa.vazgec')}
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>,
      islem === 'yeniden'
    );
  }

  // ------------------------------------------------------------------ sayfa: tür listesi
  if (!tur && sayfa) {
    const turler = sayfa.turler || [];
    return kabuk(
      <div data-testid="randevu-sayfa-turleri">
        <h1 className="text-2xl font-bold">{sayfa.baslik}</h1>
        {sayfa.karsilama && <p className="mt-2 whitespace-pre-line text-sm text-zinc-600">{sayfa.karsilama}</p>}
        <h2 className="mb-3 mt-6 text-sm font-semibold uppercase tracking-wide text-zinc-500">{t('randevuSayfa.turSec')}</h2>
        {turler.length === 0 ? (
          <p className="py-6 text-center text-sm text-zinc-500">{t('randevuSayfa.turYok')}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {turler.map((x) => {
              const Ikon = KONUM_IKONU[x.konum_turu] || Video;
              return (
                <li key={x.slug}>
                  <a
                    href={`/randevu/${sayfa.slug}/${x.slug}${ekSorgu}`}
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/randevu/${sayfa.slug}/${x.slug}${ekSorgu}`);
                    }}
                    className="flex h-full flex-col rounded-2xl border border-zinc-200 p-4 transition-shadow hover:shadow-md"
                    style={{ borderTopColor: markaT && (x.renk || '').toLowerCase() === '#7c3aed' ? renk : x.renk, borderTopWidth: 4 }}
                    data-tur={x.slug}
                    data-testid="randevu-tur-karti"
                  >
                    <span className="font-semibold">{x.ad}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                        {sureMetni(t, x.sure_dk)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
                        {t(`randevuSayfa.konum.${x.konum_turu}`)}
                      </span>
                      {x.kapasite > 1 && (
                        <span className="flex items-center gap-1">
                          <Users className="h-3.5 w-3.5" aria-hidden="true" />
                          {t('randevuSayfa.grup', { sayi: x.kapasite })}
                        </span>
                      )}
                    </span>
                    {x.aciklama && <span className="mt-2 line-clamp-3 text-sm text-zinc-600">{x.aciklama}</span>}
                  </a>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    );
  }

  // ------------------------------------------------------------------ tür: takvim → form → onay
  if (!etkinlik || !sayfa) return null;
  const Ikon = KONUM_IKONU[etkinlik.konum_turu] || Video;
  const gizlilik = localizedPath(LANGUAGE_CODES.includes(dil) ? dil : 'tr', 'gizlilik');

  if (tamam) {
    return kabuk(
      <div data-testid="randevu-onay">
        <CheckCircle2 className="mb-2 h-12 w-12" style={{ color: renk }} aria-hidden="true" />
        <h1 className="text-2xl font-bold">{t('randevuSayfa.onay.baslik')}</h1>
        <p className="mt-1 text-sm text-zinc-600">{t('randevuSayfa.onay.epostaGitti', { eposta })}</p>
        {randevu && <Ozet t={t} dil={dil} r={randevu} tz={tz} />}
        {randevu && <TakvimeEkle t={t} r={randevu} gomulu={gomulu} />}
        {yonetJeton && (
          <p className="mt-5 text-sm">
            <a href={`/randevu/yonet/${yonetJeton}${ekSorgu}`} target={gomulu ? '_blank' : undefined} rel="noopener" className="font-medium underline" style={{ color: renk }} data-testid="randevu-yonet-baglantisi">
              {t('randevuSayfa.onay.yonet')}
            </a>
          </p>
        )}
      </div>
    );
  }

  const telefonKurali = etkinlik.telefon || 'istege_bagli';
  return kabuk(
    <div className="grid gap-6 md:grid-cols-[14rem_minmax(0,1fr)]" data-testid="randevu-rezervasyon">
      <aside className="border-zinc-100 md:border-e md:pe-5">
        {(
          <a
            href={`/randevu/${sayfa.slug}${ekSorgu}`}
            onClick={(e) => {
              e.preventDefault();
              navigate(`/randevu/${sayfa.slug}${ekSorgu}`);
            }}
            className="mb-3 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-800"
          >
            <ArrowLeft className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden="true" />
            {t('randevuSayfa.geri')}
          </a>
        )}
        <h1 className="text-xl font-bold" data-testid="randevu-tur-adi">
          {etkinlik.ad}
        </h1>
        <ul className="mt-3 space-y-2 text-sm text-zinc-600">
          <li className="flex items-center gap-2">
            <Clock className="h-4 w-4 flex-none" aria-hidden="true" />
            {sureMetni(t, etkinlik.sure_dk)}
          </li>
          <li className="flex items-start gap-2">
            <Ikon className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
            <span>
              {t(`randevuSayfa.konum.${etkinlik.konum_turu}`)}
              {etkinlik.konum && <span className="block text-xs">{etkinlik.konum}</span>}
              {(etkinlik.konum_turu === 'jitsi' || etkinlik.konum_turu === 'baglanti') && <span className="block text-xs text-zinc-400">{t('randevuSayfa.konumSonra')}</span>}
            </span>
          </li>
          {(etkinlik.ev_sahipleri.length > 0 || etkinlik.ekip) && (
            <li className="flex items-center gap-2">
              <Users className="h-4 w-4 flex-none" aria-hidden="true" />
              {etkinlik.ekip ? t('randevuSayfa.ekipIle') : etkinlik.ev_sahipleri.join(', ')}
            </li>
          )}
          {etkinlik.kapasite > 1 && (
            <li className="flex items-center gap-2">
              <Users className="h-4 w-4 flex-none" aria-hidden="true" />
              {t('randevuSayfa.grup', { sayi: etkinlik.kapasite })}
            </li>
          )}
        </ul>
        {etkinlik.aciklama && <p className="mt-3 whitespace-pre-line text-sm text-zinc-600">{etkinlik.aciklama}</p>}
      </aside>

      <section aria-label={t('randevuSayfa.takvim.baslik')}>
        {!secim ? (
          <>
            <h2 className="mb-3 text-base font-semibold">{t('randevuSayfa.takvim.baslik')}</h2>
            {formHatasi === 'dolu' && (
              <p className="mb-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900" role="alert">
                {t('randevuSayfa.hata.dolu')}
              </p>
            )}
            <Takvim key={formHatasi === 'dolu' ? 'yenile' : 'ilk'} t={t} dil={dil} tz={tz} renk={renk} adres={musaitlikAdresi} onSec={(s) => {
              setSecim(s);
              setFormHatasi(null);
            }} />
            <SaatDilimiSecici t={t} dil={dil} tz={tz} onDegis={tzDegistir} />
          </>
        ) : (
          <form onSubmit={(e) => void gonder(e)} className="space-y-4" data-testid="randevu-form" noValidate={false}>
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl p-3" style={{ background: `${renk}14` }}>
              <p className="text-sm" data-testid="randevu-secilen">
                <span className="block font-semibold">{tarihYaz(secim.bas, tz, dil)}</span>
                <span dir="ltr">{saatYaz(secim.bas, tz, dil)}</span> · {tz.replace(/_/g, ' ')}
              </p>
              <button type="button" onClick={() => setSecim(null)} className="text-sm font-medium underline" style={{ color: renk }}>
                {t('randevuSayfa.degistir')}
              </button>
            </div>
            <h2 className="text-base font-semibold">{t('randevuSayfa.form.baslik')}</h2>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">{t('randevuSayfa.form.ad')} *</span>
              <input required maxLength={120} autoComplete="name" value={ad} onChange={(e) => setAd(e.target.value)} className="w-full rounded-xl border border-zinc-300 px-3 py-2.5 text-base" data-testid="randevu-ad" />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">{t('randevuSayfa.form.eposta')} *</span>
              <input required type="email" maxLength={254} autoComplete="email" value={eposta} onChange={(e) => setEposta(e.target.value)} className="w-full rounded-xl border border-zinc-300 px-3 py-2.5 text-base" dir="ltr" data-testid="randevu-eposta" />
            </label>
            {telefonKurali !== 'gizli' && (
              <label className="block text-sm">
                <span className="mb-1 block font-medium">
                  {t('randevuSayfa.form.telefon')} {telefonKurali === 'zorunlu' ? '*' : <span className="font-normal text-zinc-400">({t('randevuSayfa.form.istegeBagli')})</span>}
                </span>
                <input required={telefonKurali === 'zorunlu'} type="tel" maxLength={24} autoComplete="tel" value={telefon} onChange={(e) => setTelefon(e.target.value)} className="w-full rounded-xl border border-zinc-300 px-3 py-2.5 text-base" dir="ltr" data-testid="randevu-telefon" />
              </label>
            )}
            {(etkinlik.sorular || []).map((s) => (
              <div key={s.id} className="text-sm" data-soru={s.id}>
                {s.tur === 'onay' ? (
                  <label className="flex items-start gap-2">
                    <input type="checkbox" required={s.zorunlu} checked={yanitlar[s.id] === true} onChange={(e) => setYanitlar((y) => ({ ...y, [s.id]: e.target.checked }))} className="mt-1 h-4 w-4" />
                    <span>
                      {s.etiket}
                      {s.zorunlu && ' *'}
                    </span>
                  </label>
                ) : (
                  <label className="block">
                    <span className="mb-1 block font-medium">
                      {s.etiket}
                      {s.zorunlu ? ' *' : <span className="font-normal text-zinc-400"> ({t('randevuSayfa.form.istegeBagli')})</span>}
                    </span>
                    {s.tur === 'secim' ? (
                      <select required={s.zorunlu} value={String(yanitlar[s.id] || '')} onChange={(e) => setYanitlar((y) => ({ ...y, [s.id]: e.target.value }))} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-base">
                        <option value="">{t('randevuSayfa.form.sec')}</option>
                        {s.secenekler.map((x) => (
                          <option key={x} value={x}>
                            {x}
                          </option>
                        ))}
                      </select>
                    ) : s.tur === 'uzun' ? (
                      <textarea required={s.zorunlu} maxLength={2000} value={String(yanitlar[s.id] || '')} onChange={(e) => setYanitlar((y) => ({ ...y, [s.id]: e.target.value }))} className="min-h-[90px] w-full rounded-xl border border-zinc-300 px-3 py-2 text-base" />
                    ) : (
                      <input required={s.zorunlu} maxLength={300} value={String(yanitlar[s.id] || '')} onChange={(e) => setYanitlar((y) => ({ ...y, [s.id]: e.target.value }))} className="w-full rounded-xl border border-zinc-300 px-3 py-2.5 text-base" />
                    )}
                  </label>
                )}
              </div>
            ))}
            {/* Bal küpü: insanlar görmez, botlar doldurur. Ekran dışına itilmiyor (RTL'de sayfayı yana genişletiyordu);
                1 px, kırpılmış ve saydam. */}
            <div
              aria-hidden="true"
              style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clipPath: 'inset(50%)', whiteSpace: 'nowrap', opacity: 0, pointerEvents: 'none' }}
            >
              <label>
                Web
                <input tabIndex={-1} autoComplete="off" name="web_adresi" value={balKupu} onChange={(e) => setBalKupu(e.target.value)} />
              </label>
            </div>
            {formHatasi && formHatasi !== 'dolu' && (
              <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert" data-testid="randevu-form-hatasi">
                {t(`randevuSayfa.hata.${formHatasi}`, { defaultValue: t('randevuSayfa.hata.genel') })}
              </p>
            )}
            <button type="submit" disabled={gonderiliyor} className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-base font-semibold text-white disabled:opacity-60" style={{ background: renk }} data-testid="randevu-gonder">
              {gonderiliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {gonderiliyor ? t('randevuSayfa.form.gonderiliyor') : t('randevuSayfa.form.gonder')}
            </button>
            <p className="text-center text-[11px] leading-relaxed text-zinc-500" data-aydinlatma>
              {t('randevuSayfa.form.aydinlatma', { sayfa: sayfa.baslik, gun: sayfa.saklama_gun })}{' '}
              <a href={gizlilik} target="_blank" rel="noopener" className="underline underline-offset-2">
                {t('randevuSayfa.form.gizlilik')}
              </a>
            </p>
          </form>
        )}
      </section>
    </div>,
    true
  );
}
