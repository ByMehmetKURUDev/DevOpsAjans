import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { CalendarPlus, CheckCircle2, Clock, Loader2, Send, Undo2 } from 'lucide-react';

import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 6I — girişsiz personel sayfası: `/personel/<jeton>` (imzalı; işveren yenileyebilir/iptal edebilir).
 *
 * Personel kendi yayınlanmış vardiyalarını, yıllık izin bakiyesini ve izin geçmişini görür; izin talebi
 * gönderir (rapor türünde YALNIZ tarih aralığı — teşhis/açıklama sorulmaz), bekleyen talebini geri çeker,
 * vardiyalarını ICS ile telefonunun takvimine ekler. Kamera/konum yok. Site düzeni dışında, lazy, prerender
 * yok, noindex, Referer yok (`_headers` + meta). Metinler küçük ek pakette (`i18n/ek/ikPortal`, 7 dil; ar
 * sağdan sola); dil personelin kayıtlı dili (`?dil=` ile değişir).
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/ikPortal/*.json');
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const TURLER = ['yillik', 'mazeret', 'ucretsiz', 'rapor', 'dogum', 'babalik', 'evlilik', 'olum', 'diger'] as const;
const yuklenen = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenen.has(d)) continue;
    const y = EK_PAKETLER[`../i18n/ek/ikPortal/${d}.json`];
    if (!y) continue;
    const mod = await y();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenen.add(d);
  }
}

interface Izin {
  id: number;
  tur: string;
  baslangic: string;
  bitis: string;
  gun: number;
  durum: 'beklemede' | 'onaylandi' | 'reddedildi' | 'iptal';
  aciklama: string;
  karar_notu: string;
  kaynak: string;
}

interface Vardiya {
  id: number;
  tarih: string;
  baslangic: string;
  bitis: string;
  mola_dk: number;
  net_dk: number;
  notlar: string;
}

interface Veri {
  firma: string;
  dil: string;
  bugun: string;
  personel: { ad: string; gorev: string; departman: string; ise_giris: string | null };
  bakiye: { kalan: number; kazanilan: number; kullanilan: number; bekleyen: number; kullanilabilir: number; devir: number; kidem_yil: number; sonraki: { tarih: string; gun: number } | null };
  izinler: Izin[];
  vardiyalar: Vardiya[];
  yasal_gunler: Record<string, number>;
}

const API = () => getAPIBaseURL();
const DURUM_RENGI: Record<string, string> = {
  beklemede: 'bg-amber-100 text-amber-800',
  onaylandi: 'bg-emerald-100 text-emerald-800',
  reddedildi: 'bg-rose-100 text-rose-800',
  iptal: 'bg-slate-100 text-slate-600',
};

function yerel(dil: string): string {
  return dil === 'ar' ? 'ar-u-nu-latn' : dil;
}

function gun(iso: string, dil: string, s: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }): string {
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  try {
    return new Intl.DateTimeFormat(yerel(dil), { ...s, timeZone: 'UTC' }).format(new Date(Date.UTC(y, a - 1, g)));
  } catch {
    return iso.slice(0, 10);
  }
}

function sayi(n: number, dil: string): string {
  try {
    return new Intl.NumberFormat(yerel(dil), { maximumFractionDigits: 1 }).format(n);
  } catch {
    return String(n);
  }
}

function istekKimligi(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export default function PersonelSayfasi() {
  const { jeton = '' } = useParams<{ jeton: string }>();
  const [t, setT] = useState<TFunction | null>(null);
  const [dil, setDil] = useState('tr');
  const [veri, setVeri] = useState<Veri | null>(null);
  const [durum, setDurum] = useState<'yukleniyor' | 'hazir' | 'gecersiz' | 'kapali' | 'hata'>('yukleniyor');
  const [tur, setTur] = useState<string>('yillik');
  const [bas, setBas] = useState('');
  const [bit, setBit] = useState('');
  const [yarim, setYarim] = useState(false);
  const [aciklama, setAciklama] = useState('');
  const [onizleme, setOnizleme] = useState<{ gun: number; takvim_gunu: number } | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [mesaj, setMesaj] = useState<{ tur: 'ok' | 'hata' | 'uyari'; metin: string } | null>(null);
  const [kimlik, setKimlik] = useState(istekKimligi);

  // Belge: noindex, referrer yok, dil/yön, açık zemin.
  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background };
    kok.lang = dil;
    kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    document.body.style.background = '#f5f5f7';
    const etiketler = [
      ['robots', 'noindex, nofollow'],
      ['referrer', 'no-referrer'],
    ].map(([ad, icerik]) => {
      const m = document.createElement('meta');
      m.name = ad;
      m.content = icerik;
      document.head.appendChild(m);
      return m;
    });
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      etiketler.forEach((m) => m.remove());
    };
  }, [dil]);

  const yukle = useCallback(async (): Promise<string> => {
    let d = 'tr';
    try {
      const y = await fetch(`${API()}/api/v1/ik-portal/${encodeURIComponent(jeton)}`, { headers: { accept: 'application/json' } });
      const g = (await y.json().catch(() => null)) as Veri | null;
      if (y.ok && g) {
        setVeri(g);
        d = g.dil;
        setDurum('hazir');
        setBas((x) => x || g.bugun);
        setBit((x) => x || g.bugun);
      } else setDurum(y.status === 404 ? 'gecersiz' : y.status === 410 ? 'kapali' : 'hata');
    } catch {
      setDurum('hata');
    }
    return d;
  }, [jeton]);

  useEffect(() => {
    let iptal = false;
    (async () => {
      const d = await yukle();
      let istenen: string | null = null;
      try {
        istenen = new URLSearchParams(window.location.search).get('dil');
      } catch {
        /* yoksay */
      }
      const secilen = [istenen, d].find((x) => x && DILLER.includes(x)) || 'tr';
      await paketYukle(secilen).catch(() => undefined);
      if (iptal) return;
      setDil(secilen);
      setT(() => i18n.getFixedT(secilen));
    })();
    return () => {
      iptal = true;
    };
  }, [yukle]);

  useEffect(() => {
    if (!bas || !bit || bit < bas || durum !== 'hazir') {
      setOnizleme(null);
      return;
    }
    let iptal = false;
    const q = new URLSearchParams({ bas, bit, yarim: String(yarim && bas === bit) });
    fetch(`${API()}/api/v1/ik-portal/${encodeURIComponent(jeton)}/gun-hesapla?${q}`, { headers: { accept: 'application/json' } })
      .then((y) => (y.ok ? y.json() : null))
      .then((g) => !iptal && setOnizleme(g))
      .catch(() => !iptal && setOnizleme(null));
    return () => {
      iptal = true;
    };
  }, [bas, bit, yarim, jeton, durum]);

  const gonder = async () => {
    if (!t) return;
    setMesgul(true);
    setMesaj(null);
    try {
      const y = await fetch(`${API()}/api/v1/ik-portal/${encodeURIComponent(jeton)}/izin`, {
        method: 'POST',
        headers: { accept: 'application/json', 'content-type': 'application/json' },
        body: JSON.stringify({
          tur,
          baslangic: bas,
          bitis: bit,
          yarim_gun: yarim && bas === bit,
          aciklama: tur === 'rapor' ? undefined : aciklama.trim() || undefined,
          istek_kimligi: kimlik,
        }),
      });
      const g = (await y.json().catch(() => null)) as { uyarilar?: { tur: string }[]; tekrar?: boolean; detail?: { kod?: string } } | null;
      if (y.ok) {
        const uyarilar = (g?.uyarilar || []).map((u) => t(`ikPortal.uyari.${u.tur}`, { defaultValue: '' })).filter(Boolean);
        setMesaj(uyarilar.length ? { tur: 'uyari', metin: `${t('ikPortal.gonderildi')} ${uyarilar.join(' ')}` } : { tur: 'ok', metin: t(g?.tekrar ? 'ikPortal.zatenVar' : 'ikPortal.gonderildi') });
        setAciklama('');
        setKimlik(istekKimligi());
        await yukle();
      } else {
        const kod = g?.detail?.kod || '';
        setMesaj({ tur: 'hata', metin: t(`ikPortal.hata.${kod}`, { defaultValue: t(y.status === 429 ? 'ikPortal.hata.cok_hizli' : 'ikPortal.hata.genel') }) });
      }
    } catch {
      setMesaj({ tur: 'hata', metin: t('ikPortal.hata.ag') });
    } finally {
      setMesgul(false);
    }
  };

  const geriCek = async (id: number) => {
    if (!t || !window.confirm(t('ikPortal.geriCekOnay'))) return;
    try {
      const y = await fetch(`${API()}/api/v1/ik-portal/${encodeURIComponent(jeton)}/izin/${id}/geri-cek`, { method: 'POST', headers: { accept: 'application/json' } });
      if (y.ok) await yukle();
    } catch {
      /* yoksay */
    }
  };

  if (!t || durum === 'yukleniyor') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f5f5f7]">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" aria-hidden="true" />
      </main>
    );
  }

  if (durum !== 'hazir' || !veri) {
    return (
      <main className="flex min-h-screen items-start justify-center bg-[#f5f5f7] px-4 py-16 text-slate-900" dir={dil === 'ar' ? 'rtl' : 'ltr'} data-testid="personel-sayfasi" data-durum={durum}>
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          <h1 className="text-lg font-semibold">{t(`ikPortal.durum.${durum}`)}</h1>
          <p className="mt-2 text-sm text-slate-600">{t(`ikPortal.durum.${durum}Aciklama`)}</p>
        </div>
      </main>
    );
  }

  const b = veri.bakiye;
  const gunler: Record<string, Vardiya[]> = {};
  for (const v of veri.vardiyalar) (gunler[v.tarih] ||= []).push(v);
  const yaklasan = Object.keys(gunler)
    .filter((g) => g >= veri.bugun)
    .sort();
  const yasal = veri.yasal_gunler[tur];
  // Açık temalı sayfa: site görünümü (Modern/Nebula) girdilere koyu zemin veriyor; burada açık kalsın.
  const girdi = 'min-h-[44px] w-full rounded-xl border !border-slate-300 !bg-white px-3 text-sm text-slate-900 [color-scheme:light]';

  return (
    <main className="min-h-screen bg-[#f5f5f7] px-4 py-8 text-slate-900 sm:py-12" dir={dil === 'ar' ? 'rtl' : 'ltr'} data-testid="personel-sayfasi" data-durum="hazir">
      <div className="mx-auto w-full max-w-xl space-y-4">
        <header className="text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{veri.firma}</p>
          <h1 className="mt-1 text-2xl font-bold" data-testid="personel-ad">
            {t('ikPortal.merhaba', { ad: veri.personel.ad })}
          </h1>
          {(veri.personel.gorev || veri.personel.departman) && (
            <p className="mt-1 text-sm text-slate-600">{[veri.personel.gorev, veri.personel.departman].filter(Boolean).join(' · ')}</p>
          )}
        </header>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="personel-bakiye">
          <h2 className="text-base font-semibold">{t('ikPortal.bakiye.baslik')}</h2>
          <p className="mt-2 text-4xl font-bold text-purple-700">
            {sayi(b.kalan, dil)} <span className="text-base font-medium text-slate-500">{t('ikPortal.gun')}</span>
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {(
              [
                ['devir', b.devir],
                ['kazanilan', b.kazanilan],
                ['kullanilan', b.kullanilan],
                ['bekleyen', b.bekleyen],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="rounded-xl bg-slate-50 p-2">
                <dt className="text-xs text-slate-500">{t(`ikPortal.bakiye.${k}`)}</dt>
                <dd className="font-semibold">{sayi(v, dil)}</dd>
              </div>
            ))}
          </dl>
          {b.sonraki && <p className="mt-3 text-xs text-slate-500">{t('ikPortal.bakiye.sonraki', { tarih: gun(b.sonraki.tarih, dil), gun: b.sonraki.gun })}</p>}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="personel-vardiyalar">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold">{t('ikPortal.vardiya.baslik')}</h2>
            <a
              href={`${API()}/api/v1/ik-portal/${encodeURIComponent(jeton)}/vardiyalar.ics`}
              className="inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-slate-300 px-3 text-sm font-medium hover:bg-slate-50"
              rel="noopener"
              data-testid="personel-ics"
            >
              <CalendarPlus className="h-4 w-4" aria-hidden="true" />
              {t('ikPortal.vardiya.takvim')}
            </a>
          </div>
          {yaklasan.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">{t('ikPortal.vardiya.bos')}</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100">
              {yaklasan.map((g) => (
                <li key={g} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" data-vardiya-gun={g}>
                  <span className="font-medium">{gun(g, dil, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
                  <span className="flex flex-wrap gap-1.5">
                    {gunler[g].map((v) => (
                      <span key={v.id} className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2.5 py-1 text-xs font-semibold text-purple-800" dir="ltr">
                        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                        {v.baslangic}–{v.bitis}
                      </span>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="personel-izin-formu">
          <h2 className="text-base font-semibold">{t('ikPortal.talep.baslik')}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block text-slate-600">{t('ikPortal.talep.tur')}</span>
              <select className={girdi} value={tur} onChange={(e) => setTur(e.target.value)} data-testid="personel-izin-tur">
                {TURLER.map((x) => (
                  <option key={x} value={x}>
                    {t(`ikPortal.tur.${x}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">{t('ikPortal.talep.baslangic')}</span>
              <input
                className={girdi}
                type="date"
                value={bas}
                onChange={(e) => {
                  setBas(e.target.value);
                  if (bit < e.target.value) setBit(e.target.value);
                }}
                data-testid="personel-izin-bas"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">{t('ikPortal.talep.bitis')}</span>
              <input className={girdi} type="date" value={bit} min={bas} onChange={(e) => setBit(e.target.value)} data-testid="personel-izin-bit" />
            </label>
            {bas && bas === bit && (
              <label className="flex items-center gap-2 text-sm sm:col-span-2">
                <input type="checkbox" className="h-4 w-4 accent-purple-700" checked={yarim} onChange={(e) => setYarim(e.target.checked)} />
                {t('ikPortal.talep.yarim')}
              </label>
            )}
            <p className="text-sm text-purple-800 sm:col-span-2" data-testid="personel-izin-onizleme">
              {onizleme ? t('ikPortal.talep.onizleme', { gun: sayi(onizleme.gun, dil), takvim: onizleme.takvim_gunu }) : ''}
              {yasal != null && ['dogum', 'babalik', 'evlilik', 'olum'].includes(tur) && (
                <span className="block text-xs text-slate-500">{t(tur === 'dogum' ? 'ikPortal.talep.yasalTakvim' : 'ikPortal.talep.yasalIsGunu', { sayi: yasal })}</span>
              )}
            </p>
            {tur === 'rapor' ? (
              <p className="text-xs text-slate-500 sm:col-span-2">{t('ikPortal.talep.raporNotu')}</p>
            ) : (
              <label className="block text-sm sm:col-span-2">
                <span className="mb-1 block text-slate-600">{t('ikPortal.talep.aciklama')}</span>
                <textarea className="min-h-[72px] w-full rounded-xl border !border-slate-300 !bg-white px-3 py-2 text-sm text-slate-900 [color-scheme:light]" value={aciklama} maxLength={500} onChange={(e) => setAciklama(e.target.value)} />
              </label>
            )}
          </div>
          {mesaj && (
            <p
              className={`mt-3 rounded-xl px-3 py-2 text-sm ${mesaj.tur === 'ok' ? 'bg-emerald-50 text-emerald-800' : mesaj.tur === 'uyari' ? 'bg-amber-50 text-amber-800' : 'bg-rose-50 text-rose-700'}`}
              role={mesaj.tur === 'hata' ? 'alert' : 'status'}
              data-testid="personel-izin-mesaj"
            >
              {mesaj.tur === 'ok' && <CheckCircle2 className="me-1 inline h-4 w-4" aria-hidden="true" />}
              {mesaj.metin}
            </p>
          )}
          <button
            type="button"
            className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-purple-700 px-4 text-sm font-semibold text-white hover:bg-purple-800 disabled:opacity-50"
            disabled={mesgul || !bas || !bit || bit < bas}
            onClick={() => void gonder()}
            data-testid="personel-izin-gonder"
          >
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
            {t('ikPortal.talep.gonder')}
          </button>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="personel-izinler">
          <h2 className="text-base font-semibold">{t('ikPortal.gecmis.baslik')}</h2>
          {veri.izinler.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">{t('ikPortal.gecmis.bos')}</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100">
              {veri.izinler.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm" data-izin-durum={i.durum}>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{t(`ikPortal.tur.${i.tur}`)}</span>
                    <span className="block text-xs text-slate-500">
                      {i.baslangic === i.bitis ? gun(i.baslangic, dil) : `${gun(i.baslangic, dil)} – ${gun(i.bitis, dil)}`} · {t('ikPortal.gecmis.gun', { sayi: sayi(i.gun, dil) })}
                    </span>
                    {i.karar_notu && <span className="block text-xs text-slate-600">{t('ikPortal.gecmis.not', { not: i.karar_notu })}</span>}
                  </span>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${DURUM_RENGI[i.durum]}`}>{t(`ikPortal.durumlar.${i.durum}`)}</span>
                  {i.durum === 'beklemede' && (
                    <button type="button" onClick={() => void geriCek(i.id)} className="inline-flex min-h-[36px] items-center gap-1 rounded-lg px-2 text-xs text-slate-600 hover:bg-slate-100" data-testid="personel-geri-cek">
                      <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('ikPortal.gecmis.geriCek')}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="text-center text-[11px] leading-relaxed text-slate-500" data-testid="personel-not">
          {t('ikPortal.not')}
        </p>
        <p className="text-center text-xs text-slate-400">
          <a href="/" className="hover:text-slate-700">
            By Mehmet KURU Dev
          </a>
        </p>
      </div>
    </main>
  );
}
