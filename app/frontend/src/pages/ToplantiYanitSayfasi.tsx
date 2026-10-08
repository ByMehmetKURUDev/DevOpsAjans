import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { CalendarPlus, CheckCircle2, Clock, Loader2, MapPin, Phone, Video } from 'lucide-react';

import { getAPIBaseURL } from '@/lib/config';
import { ciftZaman } from '@/lib/toplantiZaman';
import { govdeyiTuket } from '@/lib/yanit';

/**
 * Faz 6T — girişsiz katılım yanıtı: `/toplanti-yanit/<jeton>` (davet e-postasındaki kişiye özel bağlantı).
 *
 * Katılımcı toplantının özetini görür (diğer katılımcılar YOK) ve Katılacağım / Katılamayacağım / Belki + kısa not
 * gönderir. Jeton POST'ta gövdede (istek yolu denetim kaydına yazılıyor). Toplantı bitince ya da iptal edilince
 * bağlantı geçersiz. Çevrim içi toplantı bağlantısı YALNIZ metin bağlantı (iframe/betik yok). Site düzeni dışında,
 * lazy, prerender yok, noindex, Referer yok (`_headers` + meta). Metinler küçük ek pakette (`i18n/ek/toplantiYanit`,
 * 7 dil; ar sağdan sola); dil `?dil=` ya da sitenin seçili dili.
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/toplantiYanit/*.json');
const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const YANITLAR = ['katilacak', 'katilamayacak', 'belki'] as const;
type Yanit = (typeof YANITLAR)[number] | 'bekliyor';
const yuklenen = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenen.has(d)) continue;
    const y = EK_PAKETLER[`../i18n/ek/toplantiYanit/${d}.json`];
    if (!y) continue;
    const mod = await y();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenen.add(d);
  }
}

interface Veri {
  baslik: string;
  baslangic: string;
  bitis: string;
  sure_dk: number;
  yer_turu: 'cevrimici' | 'yuz_yuze' | 'telefon';
  baglanti: string | null;
  adres: string | null;
  telefon: string | null;
  gundem: string[];
  durum: string;
  ad: string | null;
  eposta: string;
  yanit: Yanit;
  yanit_notu: string | null;
}

const API = () => getAPIBaseURL();

function ilkDil(): string {
  let istenen: string | null = null;
  try {
    istenen = new URLSearchParams(window.location.search).get('dil');
  } catch {
    /* yoksay */
  }
  return [istenen, i18n.language, 'tr'].find((x) => x && DILLER.includes(x)) || 'tr';
}

export default function ToplantiYanitSayfasi() {
  const { jeton = '' } = useParams<{ jeton: string }>();
  const [t, setT] = useState<TFunction | null>(null);
  const [dil, setDil] = useState(ilkDil);
  const [veri, setVeri] = useState<Veri | null>(null);
  const [durum, setDurum] = useState<'yukleniyor' | 'hazir' | 'gecersiz' | 'suresi_doldu' | 'iptal' | 'hata'>('yukleniyor');
  const [not, setNot] = useState('');
  const [secim, setSecim] = useState<Yanit | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [mesaj, setMesaj] = useState<{ tur: 'ok' | 'hata'; metin: string } | null>(null);

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
    paketYukle(dil)
      .catch(() => undefined)
      .then(() => {
        if (!iptal) setT(() => i18n.getFixedT(dil));
      });
    return () => {
      iptal = true;
    };
  }, [dil]);

  const durumYaz = (status: number, kod?: string) => {
    if (status === 404) setDurum('gecersiz');
    else if (status === 410) setDurum(kod === 'iptal' ? 'iptal' : 'suresi_doldu');
    else setDurum('hata');
  };

  const yukle = useCallback(async () => {
    try {
      const y = await fetch(`${API()}/api/v1/toplanti-yanit/${encodeURIComponent(jeton)}`, { headers: { accept: 'application/json' } });
      const g = (await y.json().catch(() => null)) as (Veri & { detail?: { kod?: string } }) | null;
      if (y.ok && g) {
        setVeri(g);
        setSecim(g.yanit === 'bekliyor' ? null : g.yanit);
        setNot((x) => x || g.yanit_notu || '');
        setDurum('hazir');
      } else durumYaz(y.status, g?.detail?.kod);
    } catch {
      setDurum('hata');
    }
  }, [jeton]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const gonder = async (y_: Yanit) => {
    if (!t) return;
    setSecim(y_);
    setMesgul(true);
    setMesaj(null);
    try {
      const y = await fetch(`${API()}/api/v1/toplanti-yanit`, {
        method: 'POST',
        headers: { accept: 'application/json', 'content-type': 'application/json' },
        body: JSON.stringify({ jeton, yanit: y_, not: not.trim() || null }),
      });
      const g = (await y.json().catch(() => null)) as (Veri & { detail?: { kod?: string } }) | null;
      if (y.ok && g) {
        setVeri(g);
        setMesaj({ tur: 'ok', metin: t('toplantiYanit.kaydedildi') });
      } else if (y.status === 404 || y.status === 410) {
        durumYaz(y.status, g?.detail?.kod);
      } else {
        setMesaj({ tur: 'hata', metin: t(y.status === 429 ? 'toplantiYanit.hata.cok_hizli' : 'toplantiYanit.hata.genel') });
      }
    } catch {
      setMesaj({ tur: 'hata', metin: t('toplantiYanit.hata.ag') });
    } finally {
      setMesgul(false);
    }
  };

  const icsIndir = async () => {
    // ICS: dosya indirme (yanıt gövdesi blob olarak tüketilir).
    try {
      const y = await fetch(`${API()}/api/v1/toplanti-yanit/${encodeURIComponent(jeton)}/ics`);
      if (!y.ok) {
        await govdeyiTuket(y);
        return;
      }
      const blob = await y.blob();
      const adres = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = adres;
      a.download = 'toplanti.ics';
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(adres), 30000);
    } catch {
      /* ağ hatası: önemsiz */
    }
  };

  if (!t) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f5f5f7] text-slate-500">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </main>
    );
  }

  const zaman = (iso: string) => ciftZaman(iso, dil, { istanbul: t('toplantiYanit.istanbul'), yerel: t('toplantiYanit.yerel') });
  const YerIkon = veri?.yer_turu === 'telefon' ? Phone : veri?.yer_turu === 'yuz_yuze' ? MapPin : Video;

  return (
    <main className="min-h-screen bg-[#f5f5f7] px-4 py-8 text-slate-900" data-toplanti-yanit-sayfasi>
      <div className="mx-auto w-full max-w-xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-slate-600">By Mehmet KURU Dev</p>
          <select
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={dil}
            onChange={(e) => setDil(e.target.value)}
            aria-label={t('toplantiYanit.dil')}
          >
            {DILLER.map((d) => (
              <option key={d} value={d}>
                {d.toUpperCase()}
              </option>
            ))}
          </select>
        </div>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
          {durum === 'yukleniyor' && (
            <div className="flex justify-center py-10 text-slate-500">
              <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
            </div>
          )}
          {durum !== 'yukleniyor' && durum !== 'hazir' && (
            <div className="py-6 text-center" data-durum={durum}>
              <h1 className="text-xl font-semibold">{t(`toplantiYanit.durum.${durum}.baslik`)}</h1>
              <p className="mt-2 text-sm text-slate-600">{t(`toplantiYanit.durum.${durum}.aciklama`)}</p>
            </div>
          )}
          {durum === 'hazir' && veri && (
            <>
              <p className="text-xs font-semibold uppercase tracking-wider text-purple-700">{t('toplantiYanit.ust')}</p>
              <h1 className="mt-1 break-words text-2xl font-bold" data-yanit-baslik>
                {veri.baslik}
              </h1>
              {veri.ad && <p className="mt-1 text-sm text-slate-600">{t('toplantiYanit.merhaba', { ad: veri.ad })}</p>}
              <dl className="mt-4 space-y-2 text-sm">
                <div className="flex items-start gap-2">
                  <Clock className="mt-0.5 h-4 w-4 flex-none text-purple-700" aria-hidden="true" />
                  <dd>
                    {zaman(veri.baslangic)} · {t('toplantiYanit.dk', { sayi: veri.sure_dk })}
                  </dd>
                </div>
                <div className="flex min-w-0 items-start gap-2">
                  <YerIkon className="mt-0.5 h-4 w-4 flex-none text-purple-700" aria-hidden="true" />
                  <dd className="min-w-0 break-words">
                    {veri.yer_turu === 'cevrimici' && veri.baglanti ? (
                      <a href={veri.baglanti} target="_blank" rel="noopener noreferrer" className="break-all text-purple-700 underline" data-katil>
                        {t('toplantiYanit.katil')}
                      </a>
                    ) : veri.yer_turu === 'yuz_yuze' ? (
                      veri.adres || t('toplantiYanit.yer.yuz_yuze')
                    ) : veri.yer_turu === 'telefon' ? (
                      <span dir="ltr">{veri.telefon || t('toplantiYanit.yer.telefon')}</span>
                    ) : (
                      t('toplantiYanit.yer.cevrimici')
                    )}
                  </dd>
                </div>
              </dl>
              {veri.gundem.length > 0 && (
                <>
                  <h2 className="mt-5 text-sm font-semibold">{t('toplantiYanit.gundem')}</h2>
                  <ol className="mt-1 list-decimal space-y-1 ps-6 text-sm text-slate-700">
                    {veri.gundem.map((g, i) => (
                      <li key={i} className="break-words">{g}</li>
                    ))}
                  </ol>
                </>
              )}

              <h2 className="mt-6 text-sm font-semibold">{t('toplantiYanit.soru')}</h2>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                {YANITLAR.map((y) => (
                  <button
                    key={y}
                    type="button"
                    disabled={mesgul}
                    onClick={() => void gonder(y)}
                    aria-pressed={veri.yanit === y}
                    className={`min-h-[44px] rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                      veri.yanit === y ? 'border-purple-700 bg-purple-700 text-white' : 'border-slate-300 bg-white text-slate-800 hover:border-purple-500'
                    }`}
                    data-yanit-dugmesi={y}
                  >
                    {mesgul && secim === y && <Loader2 className="me-1 inline h-4 w-4 animate-spin" aria-hidden="true" />}
                    {t(`toplantiYanit.yanit.${y}`)}
                  </button>
                ))}
              </div>
              <label className="mt-3 block text-sm">
                <span className="mb-1 block text-slate-600">{t('toplantiYanit.not')}</span>
                <textarea
                  className="min-h-[72px] w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                  value={not}
                  maxLength={500}
                  onChange={(e) => setNot(e.target.value)}
                  data-yanit-not
                />
              </label>
              {veri.yanit !== 'bekliyor' && (
                <p className="mt-3 flex items-center gap-1.5 text-sm text-emerald-700" data-mevcut-yanit={veri.yanit}>
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  {t('toplantiYanit.mevcut', { yanit: t(`toplantiYanit.yanit.${veri.yanit}`) })}
                </p>
              )}
              {mesaj && (
                <p className={`mt-3 rounded-md px-3 py-2 text-sm ${mesaj.tur === 'ok' ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'}`} role="status">
                  {mesaj.metin}
                </p>
              )}
              <button
                type="button"
                onClick={() => void icsIndir()}
                className="mt-5 inline-flex min-h-[40px] items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 hover:border-purple-500"
                data-ics
              >
                <CalendarPlus className="h-4 w-4" aria-hidden="true" />
                {t('toplantiYanit.ics')}
              </button>
              <p className="mt-4 text-xs text-slate-500">{t('toplantiYanit.gizlilik', { eposta: veri.eposta })}</p>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
