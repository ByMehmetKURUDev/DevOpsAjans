import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { Clock, Info, MapPin, Minus, Phone, Plus, Search, Share2, ShoppingBag, Trash2, X } from 'lucide-react';

import { rozetGorunur } from '@/components/marka/MarkaParcalari';
import { getAPIBaseURL } from '@/lib/config';
import { etkinRenk, markaKabugu, markaLogoAdresi, markaTemasi } from '@/lib/marka';
import {
  DILLER,
  DIL_ADLARI,
  GUNLER,
  birimFiyat,
  eksikGrup,
  kucukBoyut,
  paraYaz,
  secimFarki,
  srcset,
  tekYerel,
  varsayilanSecimler,
  yerel,
  type AcikMenu,
  type MenuDili,
  type MenuUrun,
  type SepetHesabi,
  type Teslimat,
} from '@/lib/qrMenuOrtak';
import { LANGUAGE_CODES, localizedPath } from '../../prerender/site.js';

/**
 * Faz 4M — herkese açık menü / katalog sayfası: `/menu/<slug>`.
 *
 * Site düzeninin (Layout) DIŞINDA, lazy; ana paketi büyütmüyor, prerender
 * edilmiyor, site haritasına girmiyor. Paylaşım önizlemesi (og/twitter/robots)
 * Cloudflare Pages Function'ında (`functions/menu/[slug].js`).
 *
 * * Dil: `?dil=` → bu menü için son seçilen → tarayıcı dili → mağazanın varsayılanı.
 *   Arayüz metinleri ek paket `qrMenuSayfa` (7 dil, ar sağdan sola); ürün
 *   metinleri mağazanın çevirileri.
 * * Sepet tarayıcıda (localStorage yalnız try/catch ile, isteğe bağlı).
 *   Tutarları SUNUCU hesaplıyor (`/hesapla`); kupon da sunucuda doğrulanıyor.
 * * WhatsApp siparişi: sunucu kaydeder, `wa.me` bağlantısı döner, tarayıcı gider.
 * * `?masa=12` masada sipariş için masa numarası; `?urun=<id>` ürünü açar
 *   (paylaşılabilir).
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/qrMenuSayfa/*.json');
const yuklenenDiller = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenenDiller.has(d)) continue;
    const yukleyici = EK_PAKETLER[`../i18n/ek/qrMenuSayfa/${d}.json`];
    if (!yukleyici) continue;
    const mod = await yukleyici();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenenDiller.add(d);
  }
}

function depoOku<T>(anahtar: string, varsayilan: T): T {
  try {
    const ham = localStorage.getItem(anahtar);
    return ham ? (JSON.parse(ham) as T) : varsayilan;
  } catch {
    return varsayilan;
  }
}

function depoYaz(anahtar: string, deger: unknown): void {
  try {
    localStorage.setItem(anahtar, JSON.stringify(deger));
  } catch {
    /* gizli sekme / kapalı depolama: sepet yalnız bellekte */
  }
}

function sorgu(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

interface SepetKalemi {
  anahtar: string;
  urun_id: number;
  adet: number;
  secimler: Record<string, string[]>;
}

type Durum = 'yukleniyor' | 'hazir' | 'yok' | 'pasif' | 'hata';

const API = () => getAPIBaseURL();

function olayGonder(slug: string, tur: 'urun' | 'sepet', urun_id: number) {
  try {
    void fetch(`${API()}/api/v1/menu/${encodeURIComponent(slug)}/olay`, {
      method: 'POST',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tur, urun_id }),
    }).catch(() => undefined);
  } catch {
    /* analitik menüyü asla bozmasın */
  }
}

/** Mağazanın saat dilimine göre bugünün indeksi (0 = pazartesi). */
function bugunMagazada(tz: string): (typeof GUNLER)[number] {
  try {
    const ad = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short' }).format(new Date());
    const i = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(ad);
    if (i >= 0) return String(i) as (typeof GUNLER)[number];
  } catch {
    /* geçersiz saat dilimi: tarayıcınınki */
  }
  return String((new Date().getDay() + 6) % 7) as (typeof GUNLER)[number];
}

/** Açık zeminde etiket rozetleri. */
const ETIKET_ACIK: Record<string, string> = {
  vegan: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  vejetaryen: 'border-lime-200 bg-lime-50 text-lime-800',
  glutensiz: 'border-amber-200 bg-amber-50 text-amber-800',
  acili: 'border-red-200 bg-red-50 text-red-700',
  yeni: 'border-sky-200 bg-sky-50 text-sky-800',
  cok_satan: 'border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800',
};

function hataKodu(govde: unknown): string {
  const d = (govde as { detail?: { kod?: string } } | null)?.detail;
  return d && typeof d === 'object' && typeof d.kod === 'string' ? d.kod : 'genel';
}

function Gorsel({ g, alt, buyuk, className }: { g: NonNullable<MenuUrun['gorsel']>; alt: string; buyuk?: boolean; className?: string }) {
  const boyut = kucukBoyut(g);
  return (
    <img
      src={buyuk ? g.b : g.k}
      srcSet={srcset(g)}
      sizes={buyuk ? '(min-width: 640px) 560px, 100vw' : '(min-width: 640px) 240px, 45vw'}
      width={buyuk ? g.genislik || boyut.width : boyut.width}
      height={buyuk ? g.yukseklik || boyut.height : boyut.height}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={className}
    />
  );
}

export default function MenuSayfasi() {
  const { slug = '' } = useParams<{ slug: string }>();
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [menu, setMenu] = useState<AcikMenu | null>(null);
  const [dil, setDil] = useState<MenuDili>('tr');
  const [t, setT] = useState<TFunction | null>(null);
  const [ara, setAra] = useState('');
  const [aktifKategori, setAktifKategori] = useState<number | null>(null);
  const [acikUrun, setAcikUrun] = useState<MenuUrun | null>(null);
  const [secimler, setSecimler] = useState<Record<string, string[]>>({});
  const [adet, setAdet] = useState(1);
  const sepetAnahtari = `mk-menu-sepet:${slug}`;
  const [sepet, setSepet] = useState<SepetKalemi[]>(() => depoOku<SepetKalemi[]>(sepetAnahtari, []));
  const [sepetAcik, setSepetAcik] = useState(false);
  const [bilgiAcik, setBilgiAcik] = useState(false);
  const [hesap, setHesap] = useState<SepetHesabi | null>(null);
  const [hesapHatasi, setHesapHatasi] = useState<string | null>(null);
  const [kuponGirdi, setKuponGirdi] = useState('');
  const [kupon, setKupon] = useState('');
  const [teslimat, setTeslimat] = useState<Teslimat>('gel_al');
  const masaParam = useMemo(() => (sorgu('masa') || '').replace(/[^A-Za-z0-9 .-]/g, '').slice(0, 12), []);
  const [masa, setMasa] = useState(masaParam);
  const [ad, setAd] = useState('');
  const [adres, setAdres] = useState('');
  const [not, setNot] = useState('');
  const [balKupu, setBalKupu] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [siparisHatasi, setSiparisHatasi] = useState<string | null>(null);
  const [sonuc, setSonuc] = useState<{ siparis_no: string; wa_adresi: string } | null>(null);
  const bolumler = useRef<Map<number, HTMLElement>>(new Map());

  // ------------------------------------------------------------------ veri + dil
  useEffect(() => {
    let iptal = false;
    (async () => {
      try {
        const y = await fetch(`${API()}/api/v1/menu/${encodeURIComponent(slug)}`, { headers: { accept: 'application/json' } });
        if (y.status === 404 || y.status === 410) {
          // Sade durum sayfası: ziyaretçinin dili (7 dilden biri) ya da Türkçe.
          const tarayiciDili = (typeof navigator !== 'undefined' ? (navigator.languages || [navigator.language]) : [])
            .map((x) => x.slice(0, 2))
            .find((d) => (DILLER as readonly string[]).includes(d));
          const d = (sorgu('dil') || '').slice(0, 2);
          const secilen = (DILLER as readonly string[]).includes(d) ? d : tarayiciDili || 'tr';
          await paketYukle(secilen);
          if (iptal) return;
          setDil(secilen as MenuDili);
          setT(() => i18n.getFixedT(secilen));
          setDurum(y.status === 404 ? 'yok' : 'pasif');
          return;
        }
        if (!y.ok) throw new Error(String(y.status));
        const m = (await y.json()) as AcikMenu;
        const istenen = (sorgu('dil') || '').slice(0, 2);
        const kayitli = depoOku<string>(`mk-menu-dil:${slug}`, '');
        const tarayici = typeof navigator !== 'undefined' ? (navigator.languages || [navigator.language]).map((x) => x.slice(0, 2)) : [];
        const secilen = [istenen, kayitli, ...tarayici].find((d) => d && m.diller.includes(d as MenuDili)) || m.varsayilan_dil;
        await paketYukle(secilen);
        if (iptal) return;
        const ilkTeslimat = (['masada', 'gel_al', 'paket'] as Teslimat[]).filter((x) => m.siparis[x]);
        setTeslimat(masaParam && m.siparis.masada ? 'masada' : ilkTeslimat.find((x) => x !== 'masada') || ilkTeslimat[0] || 'gel_al');
        setMenu(m);
        // Menüden kalkmış ürünler eski sepetten düşsün.
        setSepet((l) => l.filter((k) => m.urunler.some((u) => u.id === k.urun_id)));
        setDil(secilen as MenuDili);
        setT(() => i18n.getFixedT(secilen));
        setDurum('hazir');
        const urunId = Number(sorgu('urun'));
        const u = urunId ? m.urunler.find((x) => x.id === urunId) : undefined;
        if (u) {
          setAcikUrun(u);
          setSecimler(varsayilanSecimler(u));
        }
      } catch {
        if (!iptal) {
          await paketYukle('tr').catch(() => undefined);
          setT(() => i18n.getFixedT('tr'));
          setDurum('hata');
        }
      }
    })();
    return () => {
      iptal = true;
    };
  }, [slug, masaParam]);

  const dilDegistir = async (yeni: MenuDili) => {
    await paketYukle(yeni);
    setDil(yeni);
    setT(() => i18n.getFixedT(yeni));
    depoYaz(`mk-menu-dil:${slug}`, yeni);
  };

  // Belge dili/yönü, başlık, robots; menü açıkken sayfa zemini açık renk.
  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background, baslik: document.title };
    kok.lang = dil;
    kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    document.body.style.background = '#f7f7f8';
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      document.title = eski.baslik;
    };
  }, [dil]);
  useEffect(() => {
    if (menu) document.title = yerel(menu.ad, menu.ceviriler, dil);
    let etiket = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!etiket) {
      etiket = document.createElement('meta');
      etiket.name = 'robots';
      document.head.appendChild(etiket);
    }
    etiket.content = menu?.indekslenebilir ? 'index, follow' : 'noindex, nofollow';
  }, [menu, dil]);

  useEffect(() => depoYaz(sepetAnahtari, sepet), [sepet, sepetAnahtari]);

  // ------------------------------------------------------------------ sunucu hesabı
  useEffect(() => {
    if (!menu || sepet.length === 0) {
      setHesap(null);
      setHesapHatasi(null);
      return;
    }
    let iptal = false;
    const zaman = window.setTimeout(async () => {
      try {
        const y = await fetch(`${API()}/api/v1/menu/${encodeURIComponent(slug)}/hesapla`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kalemler: sepet.map(({ urun_id, adet: a, secimler: s }) => ({ urun_id, adet: a, secimler: s })), kupon: kupon || undefined, teslimat, dil }),
        });
        const govde = await y.json().catch(() => null);
        if (iptal) return;
        if (!y.ok) {
          setHesap(null);
          setHesapHatasi(hataKodu(govde));
          return;
        }
        setHesap(govde as SepetHesabi);
        setHesapHatasi(null);
      } catch {
        if (!iptal) setHesapHatasi('ag');
      }
    }, 300);
    return () => {
      iptal = true;
      window.clearTimeout(zaman);
    };
  }, [menu, sepet, kupon, teslimat, dil, slug]);

  // ------------------------------------------------------------------ kategori izleme
  useEffect(() => {
    if (!menu || typeof IntersectionObserver === 'undefined') return;
    const gozlemci = new IntersectionObserver(
      (girdiler) => {
        const gorunen = girdiler.filter((g) => g.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (gorunen) setAktifKategori(Number((gorunen.target as HTMLElement).dataset.kategori));
      },
      { rootMargin: '-120px 0px -60% 0px' }
    );
    bolumler.current.forEach((el) => gozlemci.observe(el));
    return () => gozlemci.disconnect();
  }, [menu, ara]);

  const urunAc = useCallback(
    (u: MenuUrun) => {
      setAcikUrun(u);
      setSecimler(varsayilanSecimler(u));
      setAdet(1);
      olayGonder(slug, 'urun', u.id);
      try {
        const adresi = new URL(window.location.href);
        adresi.searchParams.set('urun', String(u.id));
        window.history.replaceState(null, '', adresi.toString());
      } catch {
        /* yoksay */
      }
    },
    [slug]
  );
  const urunKapat = () => {
    setAcikUrun(null);
    try {
      const adresi = new URL(window.location.href);
      adresi.searchParams.delete('urun');
      window.history.replaceState(null, '', adresi.toString());
    } catch {
      /* yoksay */
    }
  };

  // ------------------------------------------------------------------ durum sayfaları
  if (durum === 'yukleniyor' || !t) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f7f7f8]" aria-busy="true">
        <div className="h-9 w-9 animate-spin rounded-full border-[3px] border-zinc-400 border-t-transparent" />
      </main>
    );
  }
  if (durum !== 'hazir' || !menu) {
    const anahtar = durum === 'yok' ? 'yok' : durum === 'pasif' ? 'pasif' : 'hata';
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f7f7f8] px-4 text-zinc-900" data-testid={`menu-durum-${anahtar}`}>
        <div className="max-w-sm rounded-2xl bg-white p-8 text-center shadow-sm">
          <ShoppingBag className="mx-auto mb-3 h-10 w-10 text-zinc-400" aria-hidden="true" />
          <h1 className="text-lg font-semibold">{t(`qrMenuSayfa.durum.${anahtar}Baslik`)}</h1>
          <p className="mt-2 text-sm text-zinc-600">{t(`qrMenuSayfa.durum.${anahtar}Aciklama`)}</p>
        </div>
      </main>
    );
  }

  // ------------------------------------------------------------------ hazır
  const m = menu;
  const para = (n: number) => paraYaz(n, m.para_birimi, dil);
  const katalog = m.duzen === 'katalog';
  // Faz 4L: mağazanın kendi tema rengi seçiliyse o; değilse hesabın marka rengi (yoksa bugünkü renk).
  const vurgu = etkinRenk(m.tema_rengi, m.marka, m.tema_rengi || '#7c3aed');
  const kabuk = markaKabugu(m.marka, dil, vurgu);
  const markaT = markaTemasi(m.marka);
  const markaLogo = markaT ? markaLogoAdresi(markaT.logo) : null;
  // --ring: sitenin yeşil odak halkası yerine nötr gri (işletme sayfası site renklerini taşımasın).
  const stil = { ...kabuk.style, '--menu-vurgu': vurgu, '--ring': '240 4% 46%' } as CSSProperties;
  const aranan = ara.trim().toLocaleLowerCase(dil);
  const eslesir = (u: MenuUrun) =>
    !aranan ||
    [u.ad, u.aciklama, yerel(u.ad, u.ceviriler, dil), yerel(u.aciklama, u.ceviriler, dil, 'aciklama')].some((x) => x && x.toLocaleLowerCase(dil).includes(aranan));
  const kategoriler = m.kategoriler
    .map((k) => ({ k, urunler: m.urunler.filter((u) => u.kategori_id === k.id && eslesir(u)) }))
    .filter((x) => x.urunler.length > 0);
  const sepetAdedi = sepet.reduce((a, k) => a + k.adet, 0);
  const tahmini = sepet.reduce((a, k) => {
    const u = m.urunler.find((x) => x.id === k.urun_id);
    return u ? a + (birimFiyat(u) + secimFarki(u, k.secimler)) * k.adet : a;
  }, 0);
  const teslimatlar = (['gel_al', 'paket', 'masada'] as Teslimat[]).filter((x) => m.siparis[x]);
  const siparisAcik = m.siparis.whatsapp_acik && (m.acik !== false || m.siparis.kapaliyken_siparis);
  const bugun = bugunMagazada(m.saat_dilimi);
  const saatMetni = (gun: (typeof GUNLER)[number]) => {
    const a = m.calisma_saatleri[gun] || [];
    return a.length ? a.map(([b, s]) => `${b}–${s}`).join(', ') : t('qrMenuSayfa.kapali');
  };
  const sepeteEkle = () => {
    if (!acikUrun) return;
    const anahtar = `${acikUrun.id}|${JSON.stringify(Object.keys(secimler).sort().map((g) => [g, [...(secimler[g] || [])].sort()]))}`;
    setSepet((l) => {
      const var_ = l.find((x) => x.anahtar === anahtar);
      if (var_) return l.map((x) => (x.anahtar === anahtar ? { ...x, adet: Math.min(99, x.adet + adet) } : x));
      return [...l, { anahtar, urun_id: acikUrun.id, adet, secimler }];
    });
    olayGonder(slug, 'sepet', acikUrun.id);
    urunKapat();
  };
  const siparisVer = async () => {
    setSiparisHatasi(null);
    setGonderiliyor(true);
    try {
      const y = await fetch(`${API()}/api/v1/menu/${encodeURIComponent(slug)}/siparis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kalemler: sepet.map(({ urun_id, adet: a, secimler: s }) => ({ urun_id, adet: a, secimler: s })),
          kupon: kupon || undefined,
          teslimat,
          masa: teslimat === 'masada' ? masa : undefined,
          ad,
          adres: teslimat === 'paket' ? adres : undefined,
          not,
          dil,
          web_adresi: balKupu,
        }),
      });
      const govde = await y.json().catch(() => null);
      if (!y.ok) {
        setSiparisHatasi(hataKodu(govde));
        return;
      }
      const s = govde as { siparis_no: string | null; wa_adresi: string | null };
      if (!s.siparis_no || !s.wa_adresi) return;
      setSonuc({ siparis_no: s.siparis_no, wa_adresi: s.wa_adresi });
      setSepet([]);
      setKupon('');
      setKuponGirdi('');
      window.setTimeout(() => window.location.assign(s.wa_adresi as string), 600);
    } catch {
      setSiparisHatasi('ag');
    } finally {
      setGonderiliyor(false);
    }
  };
  const paylas = async (u: MenuUrun) => {
    const adresi = `${window.location.origin}/menu/${m.slug}?urun=${u.id}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: yerel(u.ad, u.ceviriler, dil), url: adresi });
        return;
      }
      await navigator.clipboard.writeText(adresi);
      setSiparisHatasi(null);
    } catch {
      /* kullanıcı vazgeçti */
    }
  };
  const kuponHata = hesap?.kupon && !hesap.kupon.gecerli ? hesap.kupon.hata : null;
  const eksik = hesap ? hesap.en_dusuk_eksik : 0;
  const gonderilebilir =
    siparisAcik && sepet.length > 0 && !!hesap && !hesapHatasi && eksik <= 0 && !kuponHata && ad.trim().length > 0 && (teslimat !== 'paket' || adres.trim().length >= 5) && (teslimat !== 'masada' || masa.trim().length > 0);
  const acikGrup = acikUrun ? eksikGrup(acikUrun, secimler) : null;

  return (
    <div className="min-h-screen bg-[#f7f7f8] pb-28 text-zinc-900" dir={dil === 'ar' ? 'rtl' : 'ltr'} lang={dil} style={stil} data-marka={kabuk['data-marka']} data-testid="menu-sayfasi" data-duzen={m.duzen} data-dil={dil}>
      {/* Başlık */}
      <header className="relative">
        {m.kapak ? (
          <div className="h-40 w-full overflow-hidden bg-zinc-200 sm:h-56">
            <Gorsel g={m.kapak} alt="" buyuk className="h-full w-full object-cover" />
          </div>
        ) : (
          <div className="h-24 w-full" style={{ background: vurgu }} />
        )}
        <div className="mx-auto max-w-3xl px-4">
          <div className="-mt-10 flex items-end gap-3">
            <div className="flex h-20 w-20 flex-none items-center justify-center overflow-hidden rounded-2xl border-4 border-[#f7f7f8] bg-white shadow-sm">
              {m.logo ? (
                <img src={m.logo.k} alt="" width={80} height={80} className="h-full w-full object-cover" decoding="async" />
              ) : markaLogo ? (
                <img src={markaLogo} alt={markaT?.ad || ''} width={80} height={80} className="h-full w-full object-contain p-1.5" decoding="async" data-testid="marka-logo" />
              ) : (
                <ShoppingBag className="h-8 w-8" style={{ color: vurgu }} aria-hidden="true" />
              )}
            </div>
            <div className="ms-auto flex items-center gap-2 pb-1">
              {m.diller.length > 1 && (
                <label className="relative">
                  <span className="sr-only">{t('qrMenuSayfa.dil')}</span>
                  <select
                    value={dil}
                    onChange={(e) => void dilDegistir(e.target.value as MenuDili)}
                    className="h-9 rounded-full border !border-zinc-300 bg-white px-3 text-sm focus:!border-zinc-500 focus:!shadow-none"
                    data-testid="menu-dil"
                  >
                    {m.diller.map((d) => (
                      <option key={d} value={d}>
                        {DIL_ADLARI[d]}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button type="button" onClick={() => setBilgiAcik(true)} className="flex h-9 w-9 items-center justify-center rounded-full border border-zinc-300 bg-white" aria-label={t('qrMenuSayfa.bilgi')} data-testid="menu-bilgi">
                <Info className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
          <h1 className="mt-3 text-2xl font-bold leading-tight" data-testid="menu-ad">
            {yerel(m.ad, m.ceviriler, dil)}
          </h1>
          {(m.aciklama || m.ceviriler[dil]?.aciklama) && <p className="mt-1 text-sm text-zinc-600">{yerel(m.aciklama, m.ceviriler, dil, 'aciklama')}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            {m.acik !== null && (
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ${m.acik ? 'bg-emerald-100 text-emerald-800' : 'bg-zinc-200 text-zinc-700'}`}
                data-testid="menu-acik-durum"
                data-acik={m.acik}
              >
                <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                {m.acik ? t('qrMenuSayfa.suAnAcik') : t('qrMenuSayfa.suAnKapali')}
              </span>
            )}
            {m.acik !== null && <span className="text-zinc-600">{t('qrMenuSayfa.bugun', { saat: saatMetni(bugun) })}</span>}
            {masaParam && m.siparis.masada && (
              <span className="rounded-full px-2.5 py-1 font-semibold text-white" style={{ background: vurgu }} data-testid="menu-masa-rozeti">
                {t('qrMenuSayfa.masa', { masa: masaParam })}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Yapışkan kategori sekmeleri + arama */}
      <nav className="sticky top-0 z-30 mt-4 border-b border-zinc-200 bg-[#f7f7f8]/95 backdrop-blur" aria-label={t('qrMenuSayfa.kategoriler')}>
        <div className="mx-auto max-w-3xl px-4 pt-2">
          <label className="relative block">
            <span className="sr-only">{t(katalog ? 'qrMenuSayfa.araKatalog' : 'qrMenuSayfa.ara')}</span>
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" aria-hidden="true" />
            <input
              type="search"
              value={ara}
              onChange={(e) => setAra(e.target.value)}
              placeholder={t(katalog ? 'qrMenuSayfa.araKatalog' : 'qrMenuSayfa.ara')}
              className="h-10 w-full rounded-xl border !border-zinc-200 bg-white ps-9 pe-3 text-sm outline-none focus:!border-zinc-400 focus:!shadow-none"
              data-testid="menu-ara"
            />
          </label>
          <div className="-mx-4 mt-2 flex gap-2 overflow-x-auto px-4 pb-2" data-testid="menu-kategori-sekmeleri">
            {kategoriler.map(({ k }) => (
              <button
                key={k.id}
                type="button"
                onClick={() => {
                  const el = bolumler.current.get(k.id);
                  if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 118, behavior: 'smooth' });
                  setAktifKategori(k.id);
                }}
                className={`flex-none rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${aktifKategori === k.id ? 'text-white' : 'bg-white text-zinc-700 ring-1 ring-zinc-200'}`}
                style={aktifKategori === k.id ? { background: vurgu } : undefined}
              >
                {yerel(k.ad, k.ceviriler, dil)}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Ürünler */}
      <main className="mx-auto max-w-3xl px-4">
        {kategoriler.length === 0 && <p className="py-12 text-center text-sm text-zinc-500">{ara ? t('qrMenuSayfa.sonucYok') : t('qrMenuSayfa.bos')}</p>}
        {kategoriler.map(({ k, urunler }) => (
          <section
            key={k.id}
            ref={(el) => {
              if (el) bolumler.current.set(k.id, el);
              else bolumler.current.delete(k.id);
            }}
            data-kategori={k.id}
            className="pt-6"
            aria-labelledby={`kategori-${k.id}`}
          >
            <h2 id={`kategori-${k.id}`} className="mb-3 text-lg font-bold">
              {yerel(k.ad, k.ceviriler, dil)}
            </h2>
            <ul className={katalog ? 'grid grid-cols-2 gap-3 sm:grid-cols-3' : 'space-y-3'}>
              {urunler.map((u) => {
                const indirimli = birimFiyat(u) < u.fiyat;
                return (
                  <li key={u.id}>
                    <button
                      type="button"
                      onClick={() => urunAc(u)}
                      className={`w-full overflow-hidden rounded-2xl bg-white text-start shadow-sm ring-1 ring-zinc-100 transition hover:ring-zinc-300 ${katalog ? 'flex h-full flex-col' : 'flex items-stretch gap-3 p-3'} ${u.stokta_yok ? 'opacity-60' : ''}`}
                      data-urun={u.id}
                      data-testid="menu-urun-karti"
                    >
                      {katalog && (
                        <div className="aspect-square w-full bg-zinc-100">
                          {u.gorsel && <Gorsel g={u.gorsel} alt="" className="h-full w-full object-cover" />}
                        </div>
                      )}
                      <div className={`min-w-0 flex-1 ${katalog ? 'p-3' : ''}`}>
                        <div className="font-semibold leading-snug">{yerel(u.ad, u.ceviriler, dil)}</div>
                        {u.aciklama && !katalog && <p className="mt-0.5 line-clamp-2 text-sm text-zinc-600">{yerel(u.aciklama, u.ceviriler, dil, 'aciklama')}</p>}
                        <div className="mt-1.5 flex flex-wrap items-center gap-1">
                          {u.etiketler.map((e) => (
                            <span key={e} className={`rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${ETIKET_ACIK[e]}`} data-etiket={e}>
                              {t(`qrMenuSayfa.etiket.${e}`)}
                            </span>
                          ))}
                          {u.alerjenler.length > 0 && (
                            <span className="rounded-full border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-900" title={u.alerjenler.map((a) => t(`qrMenuSayfa.alerjen.${a}`)).join(', ')}>
                              {t('qrMenuSayfa.alerjenSayisi', { sayi: u.alerjenler.length })}
                            </span>
                          )}
                        </div>
                        <div className="mt-1.5 flex items-baseline gap-2">
                          <span className="font-bold" style={{ color: vurgu }}>
                            {para(birimFiyat(u))}
                          </span>
                          {indirimli && <span className="text-xs text-zinc-400 line-through">{para(u.fiyat)}</span>}
                          {u.stokta_yok && <span className="text-xs font-semibold text-red-600">{t('qrMenuSayfa.stoktaYok')}</span>}
                        </div>
                      </div>
                      {!katalog && u.gorsel && (
                        <div className="h-24 w-24 flex-none overflow-hidden rounded-xl bg-zinc-100">
                          <Gorsel g={u.gorsel} alt="" className="h-full w-full object-cover" />
                        </div>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
        {rozetGorunur(m.marka) && (
          <div role="contentinfo" className="py-10 text-center text-xs text-zinc-400" data-testid="marka-rozet">
            <a href="/" target="_blank" rel="noopener" className="hover:text-zinc-600">
              {t('qrMenuSayfa.hazirlayan')}
            </a>
          </div>
        )}
      </main>

      {/* Sepet düğmesi */}
      {sepetAdedi > 0 && !sepetAcik && (
        <div className="fixed inset-x-0 bottom-0 z-40 p-3" style={{ paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}>
          <button
            type="button"
            onClick={() => setSepetAcik(true)}
            className="mx-auto flex w-full max-w-3xl items-center justify-between rounded-2xl px-5 py-3.5 font-semibold text-white shadow-lg"
            style={{ background: vurgu }}
            data-testid="menu-sepet-ac"
          >
            <span className="flex items-center gap-2">
              <ShoppingBag className="h-5 w-5" aria-hidden="true" />
              {t('qrMenuSayfa.sepet', { sayi: sepetAdedi })}
            </span>
            <span>{para(hesap ? hesap.toplam : tahmini)}</span>
          </button>
        </div>
      )}

      {/* Ürün ayrıntısı */}
      {acikUrun && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="urun-baslik" onClick={urunKapat}>
          <div className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-white sm:max-w-lg sm:rounded-3xl" onClick={(e) => e.stopPropagation()} data-testid="menu-urun-ayrinti">
            {acikUrun.gorsel && (
              <div className="aspect-[4/3] w-full bg-zinc-100">
                <Gorsel g={acikUrun.gorsel} alt={yerel(acikUrun.ad, acikUrun.ceviriler, dil)} buyuk className="h-full w-full object-cover" />
              </div>
            )}
            <div className="p-5">
              <div className="flex items-start gap-2">
                <h2 id="urun-baslik" className="flex-1 text-xl font-bold">
                  {yerel(acikUrun.ad, acikUrun.ceviriler, dil)}
                </h2>
                <button type="button" onClick={() => void paylas(acikUrun)} className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100" aria-label={t('qrMenuSayfa.paylas')}>
                  <Share2 className="h-4 w-4" aria-hidden="true" />
                </button>
                <button type="button" onClick={urunKapat} className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100" aria-label={t('qrMenuSayfa.kapat')} data-testid="menu-urun-kapat">
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              {acikUrun.aciklama && <p className="mt-1 text-sm text-zinc-600">{yerel(acikUrun.aciklama, acikUrun.ceviriler, dil, 'aciklama')}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {acikUrun.etiketler.map((e) => (
                  <span key={e} className="rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs font-medium">
                    {t(`qrMenuSayfa.etiket.${e}`)}
                  </span>
                ))}
                {acikUrun.kalori !== null && <span className="rounded-full border border-zinc-200 px-2 py-0.5 text-xs">{t('qrMenuSayfa.kalori', { sayi: acikUrun.kalori })}</span>}
              </div>
              {acikUrun.alerjenler.length > 0 && (
                <div className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-900" data-testid="menu-alerjenler">
                  <strong className="font-semibold">{t('qrMenuSayfa.alerjenler')}:</strong> {acikUrun.alerjenler.map((a) => t(`qrMenuSayfa.alerjen.${a}`)).join(', ')}
                </div>
              )}
              {acikUrun.secenek_gruplari.map((g) => {
                const secili = secimler[g.id] || [];
                return (
                  <fieldset key={g.id} className="mt-4" data-grup={g.id}>
                    <legend className="mb-1.5 flex w-full items-center justify-between text-sm font-semibold">
                      <span>{tekYerel(g.ad, g.ceviriler, dil)}</span>
                      <span className={`text-xs font-normal ${acikGrup === g.id ? 'text-red-600' : 'text-zinc-500'}`}>
                        {g.tur === 'tek'
                          ? g.zorunlu
                            ? t('qrMenuSayfa.zorunluBir')
                            : t('qrMenuSayfa.istegeBagli')
                          : t('qrMenuSayfa.enCok', { en_az: g.en_az, en_cok: g.en_cok })}
                      </span>
                    </legend>
                    <div className="space-y-1">
                      {g.secenekler.map((s) => {
                        const isaretli = secili.includes(s.id);
                        return (
                          <label key={s.id} className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 text-sm ${isaretli ? 'border-zinc-900' : 'border-zinc-200'}`}>
                            <input
                              type={g.tur === 'tek' ? 'radio' : 'checkbox'}
                              name={`grup-${g.id}`}
                              checked={isaretli}
                              onChange={(e) =>
                                setSecimler((onceki) => {
                                  if (g.tur === 'tek') return { ...onceki, [g.id]: e.target.checked ? [s.id] : [] };
                                  const l = onceki[g.id] || [];
                                  if (e.target.checked) return l.length >= g.en_cok ? onceki : { ...onceki, [g.id]: [...l, s.id] };
                                  return { ...onceki, [g.id]: l.filter((x) => x !== s.id) };
                                })
                              }
                              onClick={() => {
                                if (g.tur === 'tek' && !g.zorunlu && isaretli) setSecimler((o) => ({ ...o, [g.id]: [] }));
                              }}
                              className="h-4 w-4"
                              style={{ accentColor: vurgu }}
                              data-secenek={s.id}
                            />
                            <span className="flex-1">{tekYerel(s.ad, s.ceviriler, dil)}</span>
                            {s.fiyat_farki !== 0 && <span className="text-zinc-600">{s.fiyat_farki > 0 ? '+' : '−'}{para(Math.abs(s.fiyat_farki))}</span>}
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                );
              })}
            </div>
            <div className="sticky bottom-0 flex items-center gap-3 border-t border-zinc-100 bg-white p-4">
              <div className="flex items-center rounded-full border border-zinc-200">
                <button type="button" className="flex h-10 w-10 items-center justify-center" onClick={() => setAdet((a) => Math.max(1, a - 1))} aria-label={t('qrMenuSayfa.azalt')}>
                  <Minus className="h-4 w-4" aria-hidden="true" />
                </button>
                <span className="w-6 text-center font-semibold tabular-nums" data-testid="menu-adet">
                  {adet}
                </span>
                <button type="button" className="flex h-10 w-10 items-center justify-center" onClick={() => setAdet((a) => Math.min(99, a + 1))} aria-label={t('qrMenuSayfa.artir')}>
                  <Plus className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <button
                type="button"
                disabled={acikUrun.stokta_yok || !!acikGrup}
                onClick={sepeteEkle}
                className="flex flex-1 items-center justify-between rounded-full px-5 py-3 font-semibold text-white disabled:opacity-50"
                style={{ background: vurgu }}
                data-testid="menu-sepete-ekle"
              >
                <span>{acikUrun.stokta_yok ? t('qrMenuSayfa.stoktaYok') : t('qrMenuSayfa.sepeteEkle')}</span>
                <span>{para((birimFiyat(acikUrun) + secimFarki(acikUrun, secimler)) * adet)}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sepet ve sipariş */}
      {sepetAcik && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="sepet-baslik">
          <div className="flex max-h-[94vh] w-full flex-col overflow-hidden rounded-t-3xl bg-white sm:max-w-lg sm:rounded-3xl" data-testid="menu-sepet">
            <div className="flex items-center justify-between border-b border-zinc-100 p-4">
              <h2 id="sepet-baslik" className="text-lg font-bold">
                {t('qrMenuSayfa.sepetBaslik')}
              </h2>
              <button type="button" onClick={() => setSepetAcik(false)} className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100" aria-label={t('qrMenuSayfa.kapat')} data-testid="menu-sepet-kapat">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {sepet.length === 0 && <p className="py-6 text-center text-sm text-zinc-500">{t('qrMenuSayfa.sepetBos')}</p>}
              <ul className="space-y-3">
                {sepet.map((k, i) => {
                  const u = m.urunler.find((x) => x.id === k.urun_id);
                  const satir = hesap?.kalemler[i];
                  if (!u) return null;
                  return (
                    <li key={k.anahtar} className="flex items-start gap-3" data-sepet-kalemi={u.id}>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">{yerel(u.ad, u.ceviriler, dil)}</div>
                        {satir && satir.secenekler.length > 0 && <div className="text-xs text-zinc-500">{satir.secenekler.map((s) => s.ad_dil).join(', ')}</div>}
                        <div className="mt-1 flex items-center gap-1">
                          <button type="button" className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-200" aria-label={t('qrMenuSayfa.azalt')} onClick={() => setSepet((l) => l.map((x, j) => (j === i ? { ...x, adet: Math.max(1, x.adet - 1) } : x)))}>
                            <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                          <span className="w-6 text-center text-sm tabular-nums">{k.adet}</span>
                          <button type="button" className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-200" aria-label={t('qrMenuSayfa.artir')} onClick={() => setSepet((l) => l.map((x, j) => (j === i ? { ...x, adet: Math.min(99, x.adet + 1) } : x)))}>
                            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                          <button type="button" className="ms-1 flex h-8 w-8 items-center justify-center rounded-full text-zinc-500" aria-label={t('qrMenuSayfa.cikar')} onClick={() => setSepet((l) => l.filter((_, j) => j !== i))}>
                            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        </div>
                      </div>
                      <span className="whitespace-nowrap text-sm font-semibold tabular-nums">{satir ? para(satir.tutar) : '…'}</span>
                    </li>
                  );
                })}
              </ul>

              {sepet.length > 0 && (
                <div className="mt-5 space-y-4">
                  {m.kupon_var && (
                    <div>
                      <div className="flex gap-2">
                        <input
                          value={kuponGirdi}
                          onChange={(e) => setKuponGirdi(e.target.value.toUpperCase())}
                          placeholder={t('qrMenuSayfa.kuponKodu')}
                          className="h-10 min-w-0 flex-1 rounded-xl border !border-zinc-200 px-3 focus:!border-zinc-400 focus:!shadow-none text-sm uppercase"
                          dir="ltr"
                          data-testid="menu-kupon"
                        />
                        <button type="button" onClick={() => setKupon(kuponGirdi.trim())} className="rounded-xl border border-zinc-300 px-4 text-sm font-semibold" data-testid="menu-kupon-uygula">
                          {t('qrMenuSayfa.uygula')}
                        </button>
                      </div>
                      {kupon && hesap?.kupon && (
                        <p className={`mt-1 text-xs ${hesap.kupon.gecerli ? 'text-emerald-700' : 'text-red-600'}`} data-testid="menu-kupon-durum">
                          {hesap.kupon.gecerli ? t('qrMenuSayfa.kuponUygulandi', { kod: hesap.kupon.kod }) : t(`qrMenuSayfa.hata.${hesap.kupon.hata}`, { defaultValue: t('qrMenuSayfa.hata.kupon_gecersiz') })}
                        </p>
                      )}
                    </div>
                  )}

                  {teslimatlar.length > 0 && (
                    <fieldset>
                      <legend className="mb-1.5 text-sm font-semibold">{t('qrMenuSayfa.teslimatBaslik')}</legend>
                      <div className="grid grid-cols-3 gap-2">
                        {teslimatlar.map((x) => (
                          <label key={x} className={`flex cursor-pointer items-center justify-center rounded-xl border px-2 py-2.5 text-center text-sm ${teslimat === x ? 'border-zinc-900 font-semibold' : 'border-zinc-200'}`}>
                            <input type="radio" name="teslimat" className="sr-only" checked={teslimat === x} onChange={() => setTeslimat(x)} data-teslimat={x} />
                            {t(`qrMenuSayfa.teslimat.${x}`)}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  )}

                  <div className="space-y-2">
                    <input value={ad} onChange={(e) => setAd(e.target.value)} maxLength={80} placeholder={t('qrMenuSayfa.adiniz')} autoComplete="name" className="h-11 w-full rounded-xl border !border-zinc-200 px-3 focus:!border-zinc-400 focus:!shadow-none text-sm" data-testid="menu-musteri-ad" />
                    {teslimat === 'masada' && (
                      <input value={masa} onChange={(e) => setMasa(e.target.value.replace(/[^A-Za-z0-9 .-]/g, '').slice(0, 12))} placeholder={t('qrMenuSayfa.masaNo')} className="h-11 w-full rounded-xl border !border-zinc-200 px-3 focus:!border-zinc-400 focus:!shadow-none text-sm" inputMode="numeric" data-testid="menu-masa" />
                    )}
                    {teslimat === 'paket' && (
                      <textarea value={adres} onChange={(e) => setAdres(e.target.value)} maxLength={300} placeholder={t('qrMenuSayfa.adresiniz')} autoComplete="street-address" className="min-h-[72px] w-full rounded-xl border !border-zinc-200 px-3 focus:!border-zinc-400 focus:!shadow-none py-2 text-sm" data-testid="menu-adres" />
                    )}
                    <textarea value={not} onChange={(e) => setNot(e.target.value)} maxLength={500} placeholder={t('qrMenuSayfa.notunuz')} className="min-h-[60px] w-full rounded-xl border !border-zinc-200 px-3 focus:!border-zinc-400 focus:!shadow-none py-2 text-sm" data-testid="menu-not" />
                    {/* Bal küpü: insanlar görmez, botlar doldurur. */}
                    <input value={balKupu} onChange={(e) => setBalKupu(e.target.value)} tabIndex={-1} autoComplete="off" aria-hidden="true" className="absolute -start-[9999px] h-px w-px opacity-0" name="web_adresi" />
                  </div>
                  {m.siparis.siparis_notu && <p className="rounded-xl bg-zinc-50 p-3 text-xs text-zinc-600">{m.siparis.siparis_notu}</p>}

                  <dl className="space-y-1 text-sm" data-testid="menu-tutarlar">
                    {hesap && (
                      <>
                        <div className="flex justify-between">
                          <dt>{t('qrMenuSayfa.araToplam')}</dt>
                          <dd className="tabular-nums">{para(hesap.ara_toplam)}</dd>
                        </div>
                        {hesap.indirim > 0 && (
                          <div className="flex justify-between text-emerald-700">
                            <dt>{t('qrMenuSayfa.indirim')}</dt>
                            <dd className="tabular-nums" data-testid="menu-indirim">
                              −{para(hesap.indirim)}
                            </dd>
                          </div>
                        )}
                        {hesap.paket_ucreti > 0 && (
                          <div className="flex justify-between">
                            <dt>{t('qrMenuSayfa.paketUcreti')}</dt>
                            <dd className="tabular-nums">{para(hesap.paket_ucreti)}</dd>
                          </div>
                        )}
                        <div className="flex justify-between border-t border-zinc-100 pt-1 text-base font-bold">
                          <dt>{t('qrMenuSayfa.toplam')}</dt>
                          <dd className="tabular-nums" data-testid="menu-toplam">
                            {para(hesap.toplam)}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>
                  {eksik > 0 && (
                    <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-900" data-testid="menu-en-dusuk">
                      {t('qrMenuSayfa.enDusuk', { tutar: para(hesap?.en_dusuk_tutar || 0), eksik: para(eksik) })}
                    </p>
                  )}
                  {hesapHatasi && <p className="text-xs text-red-600">{t(`qrMenuSayfa.hata.${hesapHatasi}`, { defaultValue: t('qrMenuSayfa.hata.genel') })}</p>}
                </div>
              )}
            </div>
            {sepet.length > 0 && (
              <div className="border-t border-zinc-100 p-4" style={{ paddingBottom: 'max(16px, env(safe-area-inset-bottom))' }}>
                {!siparisAcik && (
                  <p className="mb-2 text-center text-xs text-zinc-600" data-testid="menu-siparis-kapali">
                    {!m.siparis.whatsapp_acik ? t('qrMenuSayfa.siparisKapali') : t('qrMenuSayfa.suAnKapaliSiparis')}
                  </p>
                )}
                {siparisHatasi && (
                  <p className="mb-2 text-center text-xs text-red-600" role="alert" data-testid="menu-siparis-hatasi">
                    {t(`qrMenuSayfa.hata.${siparisHatasi}`, { defaultValue: t('qrMenuSayfa.hata.genel') })}
                  </p>
                )}
                <button
                  type="button"
                  disabled={!gonderilebilir || gonderiliyor}
                  onClick={() => void siparisVer()}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#25D366] px-5 py-3.5 font-semibold text-white disabled:opacity-50"
                  data-testid="menu-whatsapp-siparis"
                >
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
                    <path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .1-3.3-.8-2.8-1.1-4.5-4-4.7-4.2-.1-.2-1.1-1.5-1.1-2.9s.7-2 1-2.3c.2-.3.6-.4.8-.4h.6c.2 0 .4 0 .6.5l.9 2.1c.1.2.1.4 0 .6l-.4.6-.4.4c-.1.2-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.3.2.5.1.6-.1l.9-1c.2-.3.4-.2.7-.1l2 1c.3.1.5.2.6.3.1.2.1.8-.1 1.4Z" />
                  </svg>
                  {gonderiliyor ? t('qrMenuSayfa.gonderiliyor') : t('qrMenuSayfa.whatsappIleSiparis')}
                </button>
                <p className="mt-2 text-center text-[11px] leading-relaxed text-zinc-500" data-aydinlatma>
                  {t('qrMenuSayfa.aydinlatma', { gun: m.saklama_gun })}{' '}
                  <a href={localizedPath(LANGUAGE_CODES.includes(dil) ? dil : 'tr', 'gizlilik')} target="_blank" rel="noopener" className="underline underline-offset-2">
                    {t('qrMenuSayfa.gizlilik')}
                  </a>
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sipariş sonucu */}
      {sonuc && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="sonuc-baslik">
          <div className="w-full max-w-sm rounded-3xl bg-white p-6 text-center" data-testid="menu-siparis-sonuc">
            <h2 id="sonuc-baslik" className="text-lg font-bold">
              {t('qrMenuSayfa.siparisAlindi')}
            </h2>
            <p className="mt-1 text-sm text-zinc-600">{t('qrMenuSayfa.siparisNo', { no: sonuc.siparis_no })}</p>
            <p className="mt-3 text-sm text-zinc-600">{t('qrMenuSayfa.whatsappaGidiliyor')}</p>
            <a href={sonuc.wa_adresi} className="mt-4 inline-flex w-full items-center justify-center rounded-2xl bg-[#25D366] px-5 py-3 font-semibold text-white" data-testid="menu-wa-baglanti">
              {t('qrMenuSayfa.whatsappAc')}
            </a>
            <button type="button" onClick={() => setSonuc(null)} className="mt-2 text-sm text-zinc-500 underline">
              {t('qrMenuSayfa.kapat')}
            </button>
          </div>
        </div>
      )}

      {/* Bilgi: adres, telefon, saatler */}
      {bilgiAcik && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="bilgi-baslik" onClick={() => setBilgiAcik(false)}>
          <div className="w-full rounded-t-3xl bg-white p-5 sm:max-w-md sm:rounded-3xl" onClick={(e) => e.stopPropagation()} data-testid="menu-bilgi-paneli">
            <div className="mb-3 flex items-center justify-between">
              <h2 id="bilgi-baslik" className="text-lg font-bold">
                {t('qrMenuSayfa.bilgi')}
              </h2>
              <button type="button" onClick={() => setBilgiAcik(false)} className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100" aria-label={t('qrMenuSayfa.kapat')}>
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            {m.adres && (
              <p className="mb-2 flex items-start gap-2 text-sm">
                <MapPin className="mt-0.5 h-4 w-4 flex-none text-zinc-500" aria-hidden="true" />
                <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(m.adres)}`} target="_blank" rel="noopener" className="underline underline-offset-2">
                  {m.adres}
                </a>
              </p>
            )}
            {m.telefon && (
              <p className="mb-3 flex items-center gap-2 text-sm">
                <Phone className="h-4 w-4 text-zinc-500" aria-hidden="true" />
                <a href={`tel:${m.telefon}`} dir="ltr">
                  {m.telefon}
                </a>
              </p>
            )}
            <h3 className="mb-1 text-sm font-semibold">{t('qrMenuSayfa.calismaSaatleri')}</h3>
            <dl className="text-sm">
              {GUNLER.map((g) => (
                <div key={g} className={`flex justify-between py-1 ${g === bugun ? 'font-semibold' : ''}`}>
                  <dt>{t(`qrMenuSayfa.gun.${g}`)}</dt>
                  <dd dir="ltr">{saatMetni(g)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-zinc-500">{t('qrMenuSayfa.saatDilimi', { tz: m.saat_dilimi })}</p>
          </div>
        </div>
      )}
    </div>
  );
}
