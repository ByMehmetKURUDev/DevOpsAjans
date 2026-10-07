import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { CheckCircle2, Loader2, MailCheck, MailX } from 'lucide-react';

import { MarkaBasligi, rozetGorunur } from '@/components/marka/MarkaParcalari';
import { getAPIBaseURL } from '@/lib/config';
import { markaKabugu, type AcikMarka } from '@/lib/marka';

/**
 * Faz 5M — herkese açık bülten sayfaları (site düzeni dışında, lazy, prerender yok, noindex):
 *
 *   /bulten/<anahtar>          barındırılan abonelik formu (gömme betiğinin aynısı: `public/bulten-form.js`)
 *   /bulten/onay/<jeton>       çift onay: "Aboneliğimi onayla" (GET durum değiştirmez; onay POST)
 *   /bulten/tercih/<jeton>     ret ve liste tercihleri; `?islem=ret` → sayfa açılınca tek tıkla ret
 *
 * Metinler küçük ek pakette (`i18n/ek/bultenSayfa`, 7 dil; ar sağdan sola). Dil: `?dil=`,
 * kişinin kayıtlı dili, tarayıcı. Satır içi betik yok (CSP); jeton adresten başka yere
 * sızmasın diye `referrer: no-referrer`.
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/bultenSayfa/*.json');
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const yuklenen = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenen.has(d)) continue;
    const y = EK_PAKETLER[`../i18n/ek/bultenSayfa/${d}.json`];
    if (!y) continue;
    const mod = await y();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenen.add(d);
  }
}

function dilSec(...adaylar: (string | null | undefined)[]): string {
  const tarayici = typeof navigator !== 'undefined' ? (navigator.languages || [navigator.language]).map((x) => (x || '').slice(0, 2)) : [];
  return [...adaylar, ...tarayici].map((x) => (x || '').slice(0, 2).toLowerCase()).find((d) => DILLER.includes(d)) || 'tr';
}

const API = () => getAPIBaseURL();

type Tur = 'form' | 'onay' | 'tercih';

export default function BultenSayfasi() {
  const { anahtar, jeton } = useParams<{ anahtar?: string; jeton?: string }>();
  const { pathname, search } = useLocation();
  const tur: Tur = pathname.startsWith('/bulten/onay/') ? 'onay' : pathname.startsWith('/bulten/tercih/') ? 'tercih' : 'form';
  const sorgu = new URLSearchParams(search);
  const [t, setT] = useState<TFunction | null>(null);
  const [dil, setDil] = useState('tr');
  // Faz 4L: hesabın marka teması. Onay/tercih yanıtında geliyor; barındırılan formda formu gömülü betik
  // (`/bulten-form.js`) kendisi çizdiği için marka bilgisi tek küçük istekle (aynı form tanımı ucu).
  const [marka, setMarka] = useState<AcikMarka | null>(null);
  useEffect(() => {
    if (tur !== 'form' || !anahtar) return;
    let iptal = false;
    fetch(`${API()}/api/v1/bulten/form/${encodeURIComponent(anahtar)}`, { headers: { accept: 'application/json' } })
      .then((y) => (y.ok ? y.json() : null))
      .then((g: { marka?: AcikMarka } | null) => {
        if (!iptal) setMarka(g?.marka ?? null);
      })
      .catch(() => undefined);
    return () => {
      iptal = true;
    };
  }, [tur, anahtar]);

  // Belge: noindex, referrer yok, dil/yön, açık zemin.
  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background };
    kok.lang = dil;
    kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    document.body.style.background = '#f7f7f8';
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

  const dilAyarla = async (d: string) => {
    await paketYukle(d).catch(() => undefined);
    setDil(d);
    setT(() => i18n.getFixedT(d));
  };

  return (
    <main
      className="flex min-h-screen items-start justify-center bg-[#f7f7f8] px-4 py-10 text-slate-900 sm:py-16"
      dir={dil === 'ar' ? 'rtl' : 'ltr'}
      data-testid="bulten-sayfasi"
      data-tur={tur}
      {...markaKabugu(marka, dil)}
    >
      <div className="w-full max-w-lg space-y-6">
        <MarkaBasligi marka={marka} className="justify-center" />
        {tur === 'form' && anahtar && <FormKabi anahtar={anahtar} dil={dilSec(sorgu.get('dil'), i18n.language)} dilAyarla={dilAyarla} />}
        {tur === 'onay' && jeton && <OnaySayfasi jeton={jeton} t={t} dilAyarla={dilAyarla} istenenDil={sorgu.get('dil')} setMarka={setMarka} />}
        {tur === 'tercih' && jeton && (
          <TercihSayfasi jeton={jeton} t={t} dilAyarla={dilAyarla} istenenDil={sorgu.get('dil')} retIstegi={sorgu.get('islem') === 'ret'} setMarka={setMarka} />
        )}
        {rozetGorunur(marka) && (
          <p className="text-center text-xs text-slate-500" data-testid="marka-rozet">
            <a href="/" target="_blank" rel="noopener" className="hover:text-slate-800">
              By Mehmet KURU Dev
            </a>
          </p>
        )}
      </div>
    </main>
  );
}

declare global {
  interface Window {
    MKBulten?: { tara: () => void };
  }
}

function FormKabi({ anahtar, dil, dilAyarla }: { anahtar: string; dil: string; dilAyarla: (d: string) => Promise<void> }) {
  useEffect(() => {
    void dilAyarla(dil);
    if (window.MKBulten) {
      window.MKBulten.tara();
      return;
    }
    if (document.querySelector('script[data-mk-bulten-betik]')) return;
    const betik = document.createElement('script');
    betik.src = '/bulten-form.js';
    betik.async = true;
    betik.setAttribute('data-mk-bulten-betik', '');
    document.body.appendChild(betik);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anahtar]);
  return (
    <div
      key={anahtar}
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      data-mk-bulten={anahtar}
      data-mk-dil={dil}
      data-testid="bulten-form-kabi"
    />
  );
}

function Kart({ children, testid }: { children: ReactNode; testid?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid={testid}>
      {children}
    </div>
  );
}

const DUGME = 'inline-flex items-center justify-center gap-2 rounded-lg bg-purple-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-purple-800 disabled:opacity-60';

function OnaySayfasi({
  jeton,
  t,
  dilAyarla,
  istenenDil,
  setMarka,
}: {
  jeton: string;
  t: TFunction | null;
  dilAyarla: (d: string) => Promise<void>;
  istenenDil: string | null;
  setMarka: (m: AcikMarka | null) => void;
}) {
  const [veri, setVeri] = useState<{ durum: string; eposta: string; liste: string; gonderen: string; dil: string } | null>(null);
  const [durum, setDurum] = useState<'yukleniyor' | 'hazir' | 'onaylandi' | 'gecersiz' | 'kullanildi' | 'suresi_doldu' | 'hata'>('yukleniyor');
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    let iptal = false;
    (async () => {
      let d = 'tr';
      try {
        const y = await fetch(`${API()}/api/v1/bulten/onay/${encodeURIComponent(jeton)}`, { headers: { accept: 'application/json' } });
        const g = await y.json().catch(() => null);
        if (iptal) return;
        if (y.ok && g) {
          setVeri(g);
          setMarka((g as { marka?: AcikMarka }).marka ?? null);
          d = g.dil;
          setDurum(g.durum === 'gecerli' ? 'hazir' : g.durum);
        } else setDurum(y.status === 404 ? 'gecersiz' : 'hata');
      } catch {
        setDurum('hata');
      }
      await dilAyarla(dilSec(istenenDil, d));
    })();
    return () => {
      iptal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jeton]);

  const onayla = async () => {
    setMesgul(true);
    try {
      const y = await fetch(`${API()}/api/v1/bulten/onay/${encodeURIComponent(jeton)}`, { method: 'POST', headers: { accept: 'application/json' } });
      if (y.ok) setDurum('onaylandi');
      else if (y.status === 409) setDurum('kullanildi');
      else if (y.status === 410) setDurum('suresi_doldu');
      else setDurum('hata');
    } catch {
      setDurum('hata');
    } finally {
      setMesgul(false);
    }
  };

  if (!t || durum === 'yukleniyor')
    return (
      <Kart>
        <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-400" aria-hidden="true" />
      </Kart>
    );
  return (
    <Kart testid="bulten-onay">
      {durum === 'hazir' && veri && (
        <div className="space-y-4 text-center">
          <MailCheck className="mx-auto h-10 w-10 text-purple-700" aria-hidden="true" />
          <h1 className="text-xl font-bold">{t('bultenSayfa.onay.baslik')}</h1>
          <p className="text-sm text-slate-600">{t('bultenSayfa.onay.aciklama', { eposta: veri.eposta, liste: veri.liste, gonderen: veri.gonderen })}</p>
          <button type="button" className={DUGME} onClick={() => void onayla()} disabled={mesgul} data-testid="bulten-onayla">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('bultenSayfa.onay.dugme')}
          </button>
          <p className="text-xs text-slate-500">{t('bultenSayfa.onay.not')}</p>
        </div>
      )}
      {durum === 'onaylandi' && (
        <div className="space-y-3 text-center" data-testid="bulten-onaylandi">
          <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600" aria-hidden="true" />
          <h1 className="text-xl font-bold">{t('bultenSayfa.onay.tamam')}</h1>
          <p className="text-sm text-slate-600">{t('bultenSayfa.onay.tamamAciklama')}</p>
        </div>
      )}
      {['gecersiz', 'kullanildi', 'suresi_doldu', 'hata'].includes(durum) && (
        <div className="space-y-2 text-center" data-testid={`bulten-onay-${durum}`}>
          <h1 className="text-lg font-semibold">{t(`bultenSayfa.onay.${durum}`)}</h1>
          <p className="text-sm text-slate-600">{t(`bultenSayfa.onay.${durum}Aciklama`)}</p>
        </div>
      )}
    </Kart>
  );
}

interface TercihVeri {
  eposta: string;
  gonderen: string;
  abone: boolean;
  dil: string;
  listeler: { id: number; ad: string; aktif: boolean }[];
}

function TercihSayfasi({
  jeton,
  t,
  dilAyarla,
  istenenDil,
  retIstegi,
  setMarka,
}: {
  jeton: string;
  t: TFunction | null;
  dilAyarla: (d: string) => Promise<void>;
  istenenDil: string | null;
  retIstegi: boolean;
  setMarka: (m: AcikMarka | null) => void;
}) {
  const [veri, setVeri] = useState<TercihVeri | null>(null);
  const [durum, setDurum] = useState<'yukleniyor' | 'hazir' | 'gecersiz' | 'hata'>('yukleniyor');
  const [mesgul, setMesgul] = useState(false);
  const [yeniRet, setYeniRet] = useState(false);
  const retYapildi = useRef(false);

  const gonder = async (govde: Record<string, unknown>) => {
    const y = await fetch(`${API()}/api/v1/bulten/tercih/${encodeURIComponent(jeton)}`, {
      method: 'POST',
      headers: { accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(govde),
    });
    if (!y.ok) throw new Error(String(y.status));
    return (await y.json()) as TercihVeri;
  };

  useEffect(() => {
    let iptal = false;
    (async () => {
      let d = 'tr';
      try {
        const y = await fetch(`${API()}/api/v1/bulten/tercih/${encodeURIComponent(jeton)}`, { headers: { accept: 'application/json' } });
        const g = (await y.json().catch(() => null)) as TercihVeri | null;
        if (iptal) return;
        if (y.ok && g) {
          d = g.dil;
          setMarka((g as { marka?: AcikMarka }).marka ?? null);
          // E-postadaki "Abonelikten çık" bağlantısı: sayfa açılınca tek tıkla ret (bir kez).
          if (retIstegi && g.abone && !retYapildi.current) {
            retYapildi.current = true;
            const r = await gonder({ islem: 'ret' }).catch(() => null);
            if (r) {
              setVeri(r);
              setYeniRet(true);
            } else setVeri(g);
          } else setVeri(g);
          setDurum('hazir');
        } else setDurum(y.status === 404 ? 'gecersiz' : 'hata');
      } catch {
        setDurum('hata');
      }
      await dilAyarla(dilSec(istenenDil, d));
    })();
    return () => {
      iptal = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jeton]);

  const islem = async (govde: Record<string, unknown>, ret = false) => {
    setMesgul(true);
    try {
      setVeri(await gonder(govde));
      if (ret) setYeniRet(true);
    } catch {
      setDurum('hata');
    } finally {
      setMesgul(false);
    }
  };

  if (!t || durum === 'yukleniyor')
    return (
      <Kart>
        <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-400" aria-hidden="true" />
      </Kart>
    );
  if (durum !== 'hazir' || !veri)
    return (
      <Kart testid={`bulten-tercih-${durum}`}>
        <h1 className="text-center text-lg font-semibold">{t(`bultenSayfa.tercih.${durum}`)}</h1>
      </Kart>
    );
  return (
    <Kart testid="bulten-tercih">
      <div className="space-y-4">
        <div className="text-center">
          {veri.abone ? <MailCheck className="mx-auto h-10 w-10 text-purple-700" aria-hidden="true" /> : <MailX className="mx-auto h-10 w-10 text-rose-600" aria-hidden="true" />}
          <h1 className="mt-2 text-xl font-bold">{veri.abone ? t('bultenSayfa.tercih.baslik') : t('bultenSayfa.tercih.retBaslik')}</h1>
          <p className="mt-1 text-sm text-slate-600">{t('bultenSayfa.tercih.adres', { eposta: veri.eposta, gonderen: veri.gonderen })}</p>
        </div>
        {!veri.abone ? (
          <p className="rounded-lg bg-rose-50 px-4 py-3 text-center text-sm text-rose-800" data-testid="bulten-ret-tamam">
            {yeniRet ? t('bultenSayfa.tercih.retTamam') : t('bultenSayfa.tercih.zatenRet')}
          </p>
        ) : (
          <>
            {veri.listeler.length > 0 && (
              <fieldset className="space-y-2">
                <legend className="mb-1 text-sm font-semibold">{t('bultenSayfa.tercih.listeler')}</legend>
                {veri.listeler.map((l) => (
                  <label key={l.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-purple-700"
                      checked={l.aktif}
                      disabled={mesgul}
                      onChange={(e) => void islem({ listeler: { [l.id]: e.target.checked } })}
                      data-testid={`bulten-liste-${l.id}`}
                    />
                    {l.ad}
                  </label>
                ))}
              </fieldset>
            )}
            <button
              type="button"
              className="w-full rounded-lg border border-rose-300 px-5 py-2.5 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-60"
              onClick={() => void islem({ islem: 'ret' }, true)}
              disabled={mesgul}
              data-testid="bulten-ret"
            >
              {t('bultenSayfa.tercih.retDugme')}
            </button>
          </>
        )}
        <p className="text-center text-xs text-slate-500">{t('bultenSayfa.tercih.not')}</p>
      </div>
    </Kart>
  );
}
