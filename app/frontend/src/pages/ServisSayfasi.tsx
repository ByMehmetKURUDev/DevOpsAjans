import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { CheckCircle2, Clock, Download, Loader2, MapPin, Phone, Star, Truck, Wrench } from 'lucide-react';

import { MarkaBasligi, rozetGorunur } from '@/components/marka/MarkaParcalari';
import { getAPIBaseURL } from '@/lib/config';
import { markaKabugu, type AcikMarka } from '@/lib/marka';

/**
 * Faz 6S — servis müşterisinin imzalı (girişsiz) sayfası: `/servis/<jeton>`.
 *
 * İş durumu (planlandı → yolda → işte → tamamlandı), teknisyenin yalnız ilk adı, servis formu PDF'i
 * (iş tamamlanınca), memnuniyet puanı + yorum ve — firmanın Google yorum sayfası (Faz 4K) varsa —
 * Google yorum bağlantısı: puandan BAĞIMSIZ, herkese aynı (review gating yok). Altta KVKK aydınlatma
 * satırı. Site düzeni dışında, lazy, prerender yok, noindex, Referer yok (`_headers` + meta).
 * Metinler küçük ek pakette (`i18n/ek/servisSayfa`, 7 dil; ar sağdan sola); dil müşterinin kayıtlı dili.
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/servisSayfa/*.json');
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const yuklenen = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenen.has(d)) continue;
    const y = EK_PAKETLER[`../i18n/ek/servisSayfa/${d}.json`];
    if (!y) continue;
    const mod = await y();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenen.add(d);
  }
}

interface Veri {
  firma: { ad: string; telefon: string | null; eposta: string | null };
  dil: string;
  musteri_ad: string | null;
  is: {
    no: string;
    tur: string;
    durum: string;
    baslik: string;
    plan_bas: string | null;
    plan_bit: string | null;
    yolda_at: string | null;
    basla_at: string | null;
    bitir_at: string | null;
    teknisyenler: string[];
    adres: string | null;
  };
  pdf_var: boolean;
  memnuniyet: { acik: boolean; puan: number | null; yorum: string | null; at: string | null };
  google_yorum_url: string | null;
  aydinlatma: { firma: string; saklama_ay: number; eposta: string | null };
  /** Faz 4L: firmanın marka teması (servis sayfasının kendi teması yok — marka varsayılan). */
  marka?: AcikMarka;
}

const API = () => getAPIBaseURL();
const ADIMLAR = ['planlandi', 'yolda', 'iste', 'tamamlandi'] as const;

function zaman(iso: string | null, dil: string): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { timeZone: 'Europe/Istanbul', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function ServisSayfasi() {
  const { jeton = '' } = useParams<{ jeton: string }>();
  const [t, setT] = useState<TFunction | null>(null);
  const [dil, setDil] = useState('tr');
  const [veri, setVeri] = useState<Veri | null>(null);
  const [durum, setDurum] = useState<'yukleniyor' | 'hazir' | 'gecersiz' | 'suresi_doldu' | 'hata'>('yukleniyor');
  const [puan, setPuan] = useState(0);
  const [yorum, setYorum] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

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

  useEffect(() => {
    let iptal = false;
    (async () => {
      let d = 'tr';
      try {
        const y = await fetch(`${API()}/api/v1/saha/servis/${encodeURIComponent(jeton)}`, { headers: { accept: 'application/json' } });
        const g = (await y.json().catch(() => null)) as Veri | null;
        if (iptal) return;
        if (y.ok && g) {
          setVeri(g);
          d = g.dil;
          setDurum('hazir');
        } else setDurum(y.status === 404 ? 'gecersiz' : y.status === 410 ? 'suresi_doldu' : 'hata');
      } catch {
        if (!iptal) setDurum('hata');
      }
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
  }, [jeton]);

  const gonder = async () => {
    if (!puan) return;
    setMesgul(true);
    setHata(null);
    try {
      const y = await fetch(`${API()}/api/v1/saha/servis/${encodeURIComponent(jeton)}/memnuniyet`, {
        method: 'POST',
        headers: { accept: 'application/json', 'content-type': 'application/json' },
        body: JSON.stringify({ puan, yorum: yorum.trim() || undefined }),
      });
      const g = (await y.json().catch(() => null)) as Veri | null;
      if (y.ok && g) setVeri(g);
      else setHata(t ? t(y.status === 429 ? 'servisSayfa.hata.cokHizli' : 'servisSayfa.hata.puan') : '');
    } catch {
      setHata(t ? t('servisSayfa.hata.ag') : '');
    } finally {
      setMesgul(false);
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
      <main className="flex min-h-screen items-start justify-center bg-[#f5f5f7] px-4 py-16 text-slate-900" dir={dil === 'ar' ? 'rtl' : 'ltr'} data-testid="servis-sayfasi" data-durum={durum}>
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          <h1 className="text-lg font-semibold">{t(`servisSayfa.durum.${durum}`)}</h1>
          <p className="mt-2 text-sm text-slate-600">{t(`servisSayfa.durum.${durum}Aciklama`)}</p>
        </div>
      </main>
    );
  }

  const is = veri.is;
  const adimSirasi = ADIMLAR.indexOf(is.durum as (typeof ADIMLAR)[number]);
  const adimZamani: Record<string, string | null> = { planlandi: is.plan_bas, yolda: is.yolda_at, iste: is.basla_at, tamamlandi: is.bitir_at };
  const IKON = { planlandi: Clock, yolda: Truck, iste: Wrench, tamamlandi: CheckCircle2 } as const;
  const puanli = !!veri.memnuniyet.puan;

  return (
    <main
      className="min-h-screen bg-[#f5f5f7] px-4 py-8 text-slate-900 sm:py-14"
      dir={dil === 'ar' ? 'rtl' : 'ltr'}
      data-testid="servis-sayfasi"
      data-durum={is.durum}
      {...markaKabugu(veri.marka, dil)}
    >
      <div className="mx-auto w-full max-w-lg space-y-4">
        <MarkaBasligi marka={veri.marka} className="justify-center" />
        <header className="text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{t('servisSayfa.ust')}</p>
          <h1 className="mt-1 text-2xl font-bold" data-testid="servis-firma">
            {veri.firma.ad}
          </h1>
          {veri.musteri_ad && <p className="mt-1 text-sm text-slate-600">{t('servisSayfa.merhaba', { ad: veri.musteri_ad })}</p>}
        </header>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-mono text-xs text-slate-500" dir="ltr">
              {is.no}
            </p>
            <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-800" data-testid="servis-durum">
              {t(`servisSayfa.is.${is.durum}`, { defaultValue: is.durum })}
            </span>
          </div>
          <h2 className="mt-1 text-lg font-semibold">{is.baslik}</h2>
          <p className="text-sm text-slate-600">{t(`servisSayfa.tur.${is.tur}`, { defaultValue: is.tur })}</p>
          {is.durum !== 'iptal' && is.durum !== 'ertelendi' && (
            <ol className="mt-4 space-y-3">
              {ADIMLAR.map((a, i) => {
                const Ikon = IKON[a];
                const tamam = adimSirasi >= i;
                return (
                  <li key={a} className="flex items-start gap-3">
                    <span className={`flex h-8 w-8 flex-none items-center justify-center rounded-full ${tamam ? 'bg-purple-700 text-white' : 'bg-slate-100 text-slate-400'}`}>
                      <Ikon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 pt-1">
                      <span className={`block text-sm font-medium ${tamam ? '' : 'text-slate-400'}`}>{t(`servisSayfa.adim.${a}`)}</span>
                      {adimZamani[a] && (tamam || a === 'planlandi') && <span className="block text-xs text-slate-500">{zaman(adimZamani[a], dil)}</span>}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          {(is.teknisyenler.length > 0 || is.adres) && (
            <div className="mt-4 space-y-1 border-t border-slate-100 pt-3 text-sm text-slate-700">
              {is.teknisyenler.length > 0 && <p>{t('servisSayfa.teknisyen', { ad: is.teknisyenler.join(', ') })}</p>}
              {is.adres && (
                <p className="flex items-start gap-1">
                  <MapPin className="mt-0.5 h-4 w-4 flex-none text-slate-400" aria-hidden="true" />
                  {is.adres}
                </p>
              )}
            </div>
          )}
          {veri.pdf_var && (
            <a
              href={`${API()}/api/v1/saha/servis/${encodeURIComponent(jeton)}/pdf`}
              className="mt-4 inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-purple-700 px-4 text-sm font-semibold text-white hover:bg-purple-800"
              data-testid="servis-pdf"
              rel="noopener"
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              {t('servisSayfa.pdf')}
            </a>
          )}
        </section>

        {veri.memnuniyet.acik && (
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="servis-memnuniyet">
            {puanli ? (
              <div className="text-center" data-testid="servis-tesekkur">
                <CheckCircle2 className="mx-auto h-9 w-9 text-emerald-600" aria-hidden="true" />
                <p className="mt-2 font-semibold">{t('servisSayfa.puan.tesekkur')}</p>
                <p className="mt-1 text-lg text-amber-500" aria-label={t('servisSayfa.puan.verilen', { puan: veri.memnuniyet.puan })}>
                  {'★'.repeat(veri.memnuniyet.puan || 0)}
                  <span className="text-slate-300">{'★'.repeat(5 - (veri.memnuniyet.puan || 0))}</span>
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <h2 className="text-base font-semibold">{t('servisSayfa.puan.baslik')}</h2>
                <div className="flex justify-center gap-1" role="radiogroup" aria-label={t('servisSayfa.puan.baslik')}>
                  {[1, 2, 3, 4, 5].map((p) => (
                    <button
                      key={p}
                      type="button"
                      role="radio"
                      aria-checked={puan === p}
                      aria-label={t('servisSayfa.puan.yildiz', { sayi: p })}
                      onClick={() => setPuan(p)}
                      className="flex h-12 w-12 items-center justify-center rounded-xl hover:bg-amber-50"
                      data-testid={`servis-yildiz-${p}`}
                    >
                      <Star className={`h-8 w-8 ${puan >= p ? 'fill-amber-400 text-amber-400' : 'text-slate-300'}`} aria-hidden="true" />
                    </button>
                  ))}
                </div>
                <textarea
                  className="min-h-[80px] w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
                  maxLength={1000}
                  value={yorum}
                  onChange={(e) => setYorum(e.target.value)}
                  placeholder={t('servisSayfa.puan.yorum')}
                  aria-label={t('servisSayfa.puan.yorum')}
                  data-testid="servis-yorum"
                />
                {hata && (
                  <p className="text-sm text-red-600" role="alert">
                    {hata}
                  </p>
                )}
                <button
                  type="button"
                  className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white disabled:opacity-50"
                  disabled={!puan || mesgul}
                  onClick={() => void gonder()}
                  data-testid="servis-puan-gonder"
                >
                  {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                  {t('servisSayfa.puan.gonder')}
                </button>
              </div>
            )}
            {veri.google_yorum_url && (
              <p className="mt-4 border-t border-slate-100 pt-3 text-center text-sm text-slate-600">
                {t('servisSayfa.google.metin')}{' '}
                <a href={veri.google_yorum_url} target="_blank" rel="noopener noreferrer" className="font-medium text-purple-700 underline" data-testid="servis-google">
                  {t('servisSayfa.google.baglanti')}
                </a>
              </p>
            )}
          </section>
        )}

        {(veri.firma.telefon || veri.firma.eposta) && (
          <p className="flex flex-wrap items-center justify-center gap-3 text-sm text-slate-600">
            {veri.firma.telefon && (
              <a href={`tel:${veri.firma.telefon}`} className="inline-flex items-center gap-1 hover:text-slate-900" dir="ltr">
                <Phone className="h-4 w-4" aria-hidden="true" />
                {veri.firma.telefon}
              </a>
            )}
            {veri.firma.eposta && (
              <a href={`mailto:${veri.firma.eposta}`} className="hover:text-slate-900" dir="ltr">
                {veri.firma.eposta}
              </a>
            )}
          </p>
        )}

        <p className="text-center text-[11px] leading-relaxed text-slate-500" data-testid="servis-aydinlatma">
          {t('servisSayfa.aydinlatma', { firma: veri.aydinlatma.firma, ay: veri.aydinlatma.saklama_ay })}
          {veri.aydinlatma.eposta ? ` ${t('servisSayfa.aydinlatmaIletisim', { eposta: veri.aydinlatma.eposta })}` : ''}
        </p>
        {rozetGorunur(veri.marka) && (
          <p className="text-center text-xs text-slate-400" data-testid="marka-rozet">
            <a href="/" target="_blank" rel="noopener" className="hover:text-slate-700">
              By Mehmet KURU Dev
            </a>
          </p>
        )}
      </div>
    </main>
  );
}
