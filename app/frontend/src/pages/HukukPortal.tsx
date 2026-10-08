import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import i18n from 'i18next';
import type { TFunction } from 'i18next';
import { AlertTriangle, CalendarDays, Download, FileText, Globe, Loader2, Lock, MessageSquare, Receipt, Scale, Send } from 'lucide-react';

import { DIL_ADLARI, ETKINLIK_DILLERI, api, depoOku, depoYaz, dilSec, hataKodu, sorgu, type EtkinlikDili } from '@/lib/etkinlikOrtak';
import { govdeyiTuket } from '@/lib/yanit';

/**
 * Faz 6H — hukuk bürosunun girişsiz müvekkil portalı `/hukuk/muvekkil/<jeton>` (imzalı, kişiye özel; site düzeni
 * DIŞINDA, lazy, prerender yok, HER ZAMAN noindex — Pages Function `X-Robots-Tag` + `no-referrer` da yazıyor).
 * Müvekkil yalnız büronun "müvekkile görünür" işaretlediği alanları görür (konu, durum, sonraki duruşma,
 * paylaşılan belgeler, masraf dökümü, büronun notu) ve mesaj bırakabilir. Metinler ek paket `hukukPortal`.
 */

const EK_PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/hukukPortal/*.json');
const yuklenenler = new Set<string>();

async function paketYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenenler.has(d)) continue;
    const yukleyici = EK_PAKETLER[`../i18n/ek/hukukPortal/${d}.json`];
    if (!yukleyici) continue;
    const mod = await yukleyici();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenenler.add(d);
  }
}

const DIL_ANAHTARI = 'mk-hukuk-dil';

interface PortalDosyasi {
  id: number;
  sira: number;
  tur: string;
  konu?: string;
  durum?: 'acik' | 'beklemede' | 'kapandi';
  sonraki_durusma?: { tarih: string; saat: string } | null;
  belgeler?: { id: number; ad: string; boyut: number; tur: string; created_at: string | null; adres: string }[];
  masraf?: { kalem: number; toplamlar: { para_birimi: string; toplam_kurus: number; avans_kurus: number }[]; pdf: string };
  not?: string;
}

interface PortalVerisi {
  buro_adi: string;
  muvekkil: { ad: string };
  dosyalar: PortalDosyasi[];
  mesajlar: { id: number; yon: 'muvekkil' | 'buro'; metin: string; dosya_id: number | null; created_at: string | null }[];
  bugun: string;
}

type Durum = 'yukleniyor' | 'hazir' | 'gecersiz' | 'kapali' | 'hata';

const KART = 'rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm';

function gunYaz(gun: string | null | undefined, dil: string): string {
  if (!gun) return '';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'full', timeZone: 'UTC' }).format(new Date(`${gun.slice(0, 10)}T00:00:00Z`));
  } catch {
    return gun;
  }
}

function zamanYaz(iso: string | null, dil: string): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Istanbul' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function paraYaz(kurus: number, para: string, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: para || 'TRY' }).format((kurus || 0) / 100);
  } catch {
    return `${(kurus / 100).toFixed(2)} ${para}`;
  }
}

function boyutYaz(b: number): string {
  return b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
}

export default function HukukPortal() {
  const { jeton = '' } = useParams<{ jeton: string }>();
  const [dil, setDil] = useState<EtkinlikDili | null>(null);
  const [t, setT] = useState<TFunction | null>(null);
  const [durum, setDurum] = useState<Durum>('yukleniyor');
  const [veri, setVeri] = useState<PortalVerisi | null>(null);
  const [metin, setMetin] = useState('');
  const [dosyaId, setDosyaId] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [bildiri, setBildiri] = useState<{ tur: 'ok' | 'hata'; metin: string } | null>(null);

  const dilKur = useCallback(async (d: EtkinlikDili, kaydet = false) => {
    await paketYukle(d).catch(() => undefined);
    if (kaydet) depoYaz(DIL_ANAHTARI, d);
    setDil(d);
    setT(() => i18n.getFixedT(d));
  }, []);

  useEffect(() => {
    void dilKur(dilSec(sorgu('dil'), depoOku(DIL_ANAHTARI), 'tr'));
  }, [dilKur]);

  // Belge başlığı, yön ve robots: HER ZAMAN noindex (Function da yazıyor; istemci gezintisinde de kalsın).
  useEffect(() => {
    const kok = document.documentElement;
    const eski = { lang: kok.lang, dir: kok.dir, bg: document.body.style.background, baslik: document.title };
    if (dil) {
      kok.lang = dil;
      kok.dir = dil === 'ar' ? 'rtl' : 'ltr';
    }
    document.body.style.background = '#f6f7fb';
    let etiket = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!etiket) {
      etiket = document.createElement('meta');
      etiket.name = 'robots';
      document.head.appendChild(etiket);
    }
    etiket.content = 'noindex, nofollow';
    let ref = document.head.querySelector<HTMLMetaElement>('meta[name="referrer"]');
    if (!ref) {
      ref = document.createElement('meta');
      ref.name = 'referrer';
      document.head.appendChild(ref);
    }
    ref.content = 'no-referrer';
    if (t) document.title = `${t('hukukPortal.baslik')}${veri?.buro_adi ? ` · ${veri.buro_adi}` : ''}`;
    return () => {
      kok.lang = eski.lang;
      kok.dir = eski.dir;
      document.body.style.background = eski.bg;
      document.title = eski.baslik;
    };
  }, [dil, t, veri?.buro_adi]);

  const yukle = useCallback(async () => {
    try {
      const y = await fetch(`${api()}/api/v1/hukuk/muvekkil/${encodeURIComponent(jeton)}`, { cache: 'no-store', referrerPolicy: 'no-referrer' });
      if (!y.ok) {
        // 404/410 durum sayfaları gövdeyi kullanmıyor; yine de okunmalı (yoksa istek açık kalıyor).
        await govdeyiTuket(y);
        return setDurum(y.status === 404 ? 'gecersiz' : y.status === 410 ? 'kapali' : 'hata');
      }
      setVeri((await y.json()) as PortalVerisi);
      setDurum('hazir');
    } catch {
      setDurum('hata');
    }
  }, [jeton]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    if (!t || !metin.trim()) return;
    setGonderiliyor(true);
    setBildiri(null);
    try {
      const y = await fetch(`${api()}/api/v1/hukuk/muvekkil/${encodeURIComponent(jeton)}/mesaj`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metin: metin.trim(), ...(dosyaId ? { dosya_id: Number(dosyaId) } : {}) }),
        referrerPolicy: 'no-referrer',
      });
      if (!y.ok) {
        const kod = hataKodu(await y.json().catch(() => null));
        setBildiri({ tur: 'hata', metin: t(`hukukPortal.hata.${kod}`, { defaultValue: t('hukukPortal.hata.genel') }) as string });
      } else {
        await govdeyiTuket(y);
        setMetin('');
        setBildiri({ tur: 'ok', metin: t('hukukPortal.mesaj.gonderildi') });
        await yukle();
      }
    } catch {
      setBildiri({ tur: 'hata', metin: t('hukukPortal.hata.genel') });
    } finally {
      setGonderiliyor(false);
    }
  };

  if (!t || !dil) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-zinc-400" aria-hidden="true" />
      </div>
    );
  }

  const icerik = () => {
    if (durum === 'yukleniyor') {
      return (
        <div className="flex min-h-[40vh] items-center justify-center" data-testid="hukuk-portal-yukleniyor">
          <Loader2 className="h-8 w-8 animate-spin text-zinc-400" aria-label={t('hukukPortal.yukleniyor')} />
        </div>
      );
    }
    if (durum !== 'hazir' || !veri) {
      return (
        <div className={`${KART} text-center`} data-testid="hukuk-portal-durum" data-durum={durum}>
          <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-500" aria-hidden="true" />
          <p className="text-lg font-medium">{t(`hukukPortal.durum.${durum}`)}</p>
        </div>
      );
    }
    return (
      <div className="space-y-4" data-testid="hukuk-portal-icerik">
        <div className={KART}>
          <p className="text-sm text-zinc-500">{t('hukukPortal.merhaba', { ad: veri.muvekkil.ad })}</p>
          <p className="mt-2 flex items-start gap-2 rounded-xl bg-zinc-50 p-3 text-xs text-zinc-600">
            <Lock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {t('hukukPortal.gizlilik')}
          </p>
        </div>
        {veri.dosyalar.length === 0 ? (
          <div className={`${KART} text-center text-sm text-zinc-500`}>{t('hukukPortal.dosyaYok')}</div>
        ) : (
          veri.dosyalar.map((d) => (
            <section key={d.id} className={KART} data-testid="hukuk-portal-dosya" data-dosya-id={d.id}>
              <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
                <FileText className="h-5 w-5 text-zinc-500" aria-hidden="true" />
                {d.konu || t('hukukPortal.dosyaNo', { sira: d.sira })}
                <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600">{t(`hukukPortal.tur.${d.tur}`)}</span>
              </h2>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                {d.durum && (
                  <div>
                    <dt className="text-xs text-zinc-500">{t('hukukPortal.durumEtiket')}</dt>
                    <dd className="font-medium" data-testid="hukuk-portal-durum-deger">
                      {t(`hukukPortal.dosyaDurum.${d.durum}`)}
                    </dd>
                  </div>
                )}
                {d.sonraki_durusma !== undefined && (
                  <div>
                    <dt className="flex items-center gap-1 text-xs text-zinc-500">
                      <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('hukukPortal.sonrakiDurusma')}
                    </dt>
                    <dd className="font-medium" data-testid="hukuk-portal-durusma">
                      {d.sonraki_durusma ? `${gunYaz(d.sonraki_durusma.tarih, dil)}${d.sonraki_durusma.saat ? ` · ${d.sonraki_durusma.saat}` : ''}` : t('hukukPortal.durusmaYok')}
                    </dd>
                  </div>
                )}
              </dl>
              {d.not && (
                <p className="mt-3 whitespace-pre-wrap rounded-xl bg-blue-50 p-3 text-sm text-blue-900" data-testid="hukuk-portal-not">
                  {d.not}
                </p>
              )}
              {d.belgeler && (
                <div className="mt-4">
                  <h3 className="mb-1 text-sm font-semibold">{t('hukukPortal.belgeler')}</h3>
                  {d.belgeler.length === 0 ? (
                    <p className="text-sm text-zinc-500">{t('hukukPortal.belgeYok')}</p>
                  ) : (
                    <ul className="divide-y divide-zinc-100" data-testid="hukuk-portal-belgeler">
                      {d.belgeler.map((b) => (
                        <li key={b.id} className="flex items-center gap-2 py-2 text-sm">
                          <span className="min-w-0 flex-1 truncate">{b.ad}</span>
                          <span className="text-xs text-zinc-500">{boyutYaz(b.boyut)}</span>
                          <a href={`${api()}${b.adres}`} rel="noreferrer noopener" className="inline-flex items-center gap-1 text-blue-700 hover:underline" data-testid="hukuk-portal-belge-indir">
                            <Download className="h-4 w-4" aria-hidden="true" />
                            {t('hukukPortal.indir')}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {d.masraf && (
                <div className="mt-4">
                  <h3 className="mb-1 flex items-center gap-1 text-sm font-semibold">
                    <Receipt className="h-4 w-4" aria-hidden="true" />
                    {t('hukukPortal.masraf')}
                  </h3>
                  {d.masraf.toplamlar.length === 0 ? (
                    <p className="text-sm text-zinc-500">{t('hukukPortal.masrafYok')}</p>
                  ) : (
                    d.masraf.toplamlar.map((x) => (
                      <p key={x.para_birimi} className="text-sm">
                        {t('hukukPortal.masrafToplam', { tutar: paraYaz(x.toplam_kurus, x.para_birimi, dil), sayi: d.masraf?.kalem ?? 0 })}
                      </p>
                    ))
                  )}
                  <a
                    href={`${api()}${d.masraf.pdf}?dil=${dil}`}
                    rel="noreferrer noopener"
                    className="mt-2 inline-flex items-center gap-1 rounded-xl border border-zinc-300 px-3 py-1.5 text-sm text-zinc-800 hover:bg-zinc-50"
                    data-testid="hukuk-portal-masraf-pdf"
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                    {t('hukukPortal.masrafPdf')}
                  </a>
                  <p className="mt-1 text-xs text-zinc-500">{t('hukukPortal.masrafNot')}</p>
                </div>
              )}
            </section>
          ))
        )}

        <section className={KART} data-testid="hukuk-portal-mesajlar">
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
            <MessageSquare className="h-5 w-5 text-zinc-500" aria-hidden="true" />
            {t('hukukPortal.mesaj.baslik')}
          </h2>
          {veri.mesajlar.length > 0 && (
            <ul className="mb-3 space-y-2">
              {veri.mesajlar.map((m) => (
                <li key={m.id} className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${m.yon === 'muvekkil' ? 'ms-auto bg-blue-50 text-blue-950' : 'bg-zinc-100'}`} data-yon={m.yon}>
                  <p className="mb-0.5 text-[11px] text-zinc-500">
                    {m.yon === 'muvekkil' ? t('hukukPortal.mesaj.siz') : veri.buro_adi || t('hukukPortal.mesaj.buro')} · {zamanYaz(m.created_at, dil)}
                  </p>
                  <p className="whitespace-pre-wrap break-words">{m.metin}</p>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={(e) => void gonder(e)} className="space-y-2">
            {veri.dosyalar.length > 1 && (
              <select className="w-full rounded-xl border !border-zinc-300 !bg-white px-3 py-2 text-sm text-zinc-900" value={dosyaId} onChange={(e) => setDosyaId(e.target.value)} aria-label={t('hukukPortal.mesaj.dosya')}>
                <option value="">{t('hukukPortal.mesaj.dosyaGenel')}</option>
                {veri.dosyalar.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.konu || t('hukukPortal.dosyaNo', { sira: d.sira })}
                  </option>
                ))}
              </select>
            )}
            <textarea
              className="min-h-[96px] w-full rounded-xl border !border-zinc-300 !bg-white px-3 py-2 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={metin}
              maxLength={2000}
              onChange={(e) => setMetin(e.target.value)}
              placeholder={t('hukukPortal.mesaj.yer')}
              aria-label={t('hukukPortal.mesaj.yer')}
              data-testid="hukuk-portal-mesaj"
            />
            <p className="text-xs text-zinc-500">{t('hukukPortal.mesaj.not')}</p>
            {bildiri && (
              <p className={`text-sm ${bildiri.tur === 'ok' ? 'text-emerald-700' : 'text-red-700'}`} role="status" data-testid="hukuk-portal-bildiri">
                {bildiri.metin}
              </p>
            )}
            <button
              type="submit"
              disabled={gonderiliyor || !metin.trim()}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
              data-testid="hukuk-portal-gonder"
            >
              {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />}
              {t('hukukPortal.mesaj.gonder')}
            </button>
          </form>
        </section>
      </div>
    );
  };

  return (
    <div className="min-h-screen px-3 py-6 text-zinc-900 sm:px-6 sm:py-10" data-testid="hukuk-portal">
      <div className="mx-auto max-w-3xl space-y-4">
        <header className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-900 text-white">
            <Scale className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-lg font-bold" data-testid="hukuk-portal-buro">
              {veri?.buro_adi || t('hukukPortal.baslik')}
            </p>
            <p className="text-xs text-zinc-500">{t('hukukPortal.altBaslik')}</p>
          </div>
        </header>
        {icerik()}
        {/* `!` sınıfları: site görünümü (Modern/Nebula) <footer> ve girdilere koyu zemin veriyor; bu açık renkli bağımsız sayfada etkisiz. */}
        <footer className="flex flex-wrap items-center justify-between gap-3 border-0 !bg-transparent px-1 pb-4 text-xs text-zinc-500 !shadow-none">
          <label className="inline-flex items-center gap-1.5">
            <Globe className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="sr-only">{t('hukukPortal.dil')}</span>
            <select value={dil} onChange={(e) => void dilKur(e.target.value as EtkinlikDili, true)} className="rounded-md border !border-zinc-300 !bg-white px-1.5 py-1 text-zinc-700" data-testid="hukuk-portal-dil">
              {ETKINLIK_DILLERI.map((d) => (
                <option key={d} value={d}>
                  {DIL_ADLARI[d]}
                </option>
              ))}
            </select>
          </label>
          <span>{t('hukukPortal.altBilgi')}</span>
        </footer>
      </div>
    </div>
  );
}
