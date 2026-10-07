import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  Award,
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  Copy,
  ExternalLink,
  GraduationCap,
  Loader2,
  Megaphone,
  Plus,
  Settings2,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KART, Rozet, Yukleniyor, kopyala } from '@/components/randevu/ortak';
import { egitimApi, gunYaz, hataMetni, tarihSaat, type EgitimMod, type Kurs, type Meta } from '@/lib/egitim';

const KursAyarlari = lazy(() => import('@/components/egitim/KursAyarlari'));
const Ogrenciler = lazy(() => import('@/components/egitim/Ogrenciler'));
const Program = lazy(() => import('@/components/egitim/Program'));
const Dersler = lazy(() => import('@/components/egitim/Dersler'));
const QuizOdev = lazy(() => import('@/components/egitim/QuizOdev'));
const Sertifikalar = lazy(() => import('@/components/egitim/Sertifikalar'));
const Duyurular = lazy(() => import('@/components/egitim/Duyurular'));
const HesapAyarlari = lazy(() => import('@/components/egitim/HesapAyarlari'));

/**
 * Faz 6K — "Eğitim" sekmesi (kurs merkezi, dershane, atölye, eğitmen, okul). Yönetici panelinde
 * (`mod="yonetici"`: ajansın kendi kursları + müşterilerinkini destek için görür) ve müşteri panelinde
 * (`mod="musteri"`: etkin hesabın kursları) aynı bileşen. Menüde TEK sekme; bölümler burada alt gezinme:
 * Kurslar (→ kurs: Genel, Öğrenciler, Program/Yoklama, Dersler, Quiz/Ödev, Sertifikalar, Duyurular) ve
 * Ayarlar (kurum adı, sertifika imzası, kurs listesi sayfası, AI hakkı).
 *
 * Ekipte yalnız `egitim_egitmen` izni olan kişi (sunucu `meta.egitmen`): yalnız eğitmeni olduğu kurslar;
 * öğrenci listesi (iletişim bilgisi yok), program/yoklama, dersler (okuma), quiz/ödev (sonuç + not).
 */

type Ust = 'kurslar' | 'ayarlar';
type Alt = 'genel' | 'ogrenciler' | 'program' | 'dersler' | 'quiz' | 'sertifikalar' | 'duyurular';

const ALT_SEKMELER: { anahtar: Alt; ikon: typeof Users; yonetim?: boolean }[] = [
  { anahtar: 'genel', ikon: Settings2, yonetim: true },
  { anahtar: 'ogrenciler', ikon: Users },
  { anahtar: 'program', ikon: CalendarDays },
  { anahtar: 'dersler', ikon: BookOpen },
  { anahtar: 'quiz', ikon: ClipboardCheck },
  { anahtar: 'sertifikalar', ikon: Award, yonetim: true },
  { anahtar: 'duyurular', ikon: Megaphone, yonetim: true },
];

export const DURUM_RENGI: Record<string, string> = {
  taslak: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  yayinda: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  tamamlandi: 'border-sky-400/40 bg-sky-500/15 text-sky-200',
  arsiv: 'border-zinc-400/30 bg-zinc-500/10 text-zinc-300',
};

function SekmeDugmesi({ secili, onClick, children, testid }: { secili: boolean; onClick: () => void; children: ReactNode; testid?: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={secili}
      onClick={onClick}
      className={`flex flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        secili ? 'bg-blue-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
      }`}
      data-egitim-alt={testid}
    >
      {children}
    </button>
  );
}

export default function Egitim({ mod }: { mod: EgitimMod }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const api = useMemo(() => egitimApi(mod), [mod]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [liste, setListe] = useState<Kurs[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [ust, setUst] = useState<Ust>('kurslar');
  const [seciliId, setSeciliId] = useState<number | null>(null);
  const [secili, setSecili] = useState<Kurs | null>(null);
  const [alt, setAlt] = useState<Alt>('genel');
  const [yeniAd, setYeniAd] = useState('');
  const [yeniHesap, setYeniHesap] = useState('');
  const [olusturuluyor, setOlusturuluyor] = useState(false);
  const [kapsam, setKapsam] = useState('');

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      const [m, l] = await Promise.all([api.meta(), api.liste(mod === 'yonetici' && kapsam ? kapsam : undefined)]);
      setMeta(m);
      setListe(l.items);
    } catch (e) {
      setHata(hataMetni(t, e));
      setListe([]);
    }
  }, [api, kapsam, mod, t]);

  useEffect(() => {
    if (seciliId !== null) return;
    void yukle();
  }, [yukle, seciliId]);

  useEffect(() => {
    if (seciliId === null) {
      setSecili(null);
      return;
    }
    let iptal = false;
    api
      .getir(seciliId)
      .then((k) => {
        if (!iptal) setSecili(k);
      })
      .catch((e) => {
        if (iptal) return;
        toast.error(hataMetni(t, e));
        setSeciliId(null);
      });
    return () => {
      iptal = true;
    };
  }, [api, seciliId, t]);

  const yonetim = !!meta?.yonetim;

  const olustur = async () => {
    if (!yeniAd.trim()) {
      toast.error(t('egitim.hata.zorunlu'));
      return;
    }
    setOlusturuluyor(true);
    try {
      const k = await api.olustur({
        ad: yeniAd.trim(),
        dil: dil.slice(0, 2),
        saat_dilimi: meta?.varsayilan_saat_dilimi || 'Europe/Istanbul',
        ...(mod === 'yonetici' && yeniHesap.trim() ? { hesap_email: yeniHesap.trim() } : {}),
      });
      setYeniAd('');
      setYeniHesap('');
      toast.success(t('egitim.kurslar.olusturuldu'));
      setAlt('genel');
      setSeciliId(k.id);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setOlusturuluyor(false);
    }
  };

  const ustBaslik = (
    <div className="mb-5">
      <h2 className="flex items-center gap-2 text-2xl font-bold" id="egitim-baslik">
        <GraduationCap className="h-6 w-6 text-blue-300" aria-hidden="true" />
        {t('egitim.baslik')}
      </h2>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{mod === 'yonetici' ? t('egitim.aciklamaYonetici') : t('egitim.aciklama')}</p>
    </div>
  );

  // ------------------------------------------------------------------ kurs çalışma alanı
  if (seciliId !== null) {
    if (!secili || !meta) {
      return (
        <section aria-labelledby="egitim-baslik" data-testid="egitim-sekmesi">
          {ustBaslik}
          <Yukleniyor />
        </section>
      );
    }
    const altlar = ALT_SEKMELER.filter((s) => yonetim || !s.yonetim);
    const etkinAlt = altlar.some((s) => s.anahtar === alt) ? alt : altlar[0].anahtar;
    const guncellendi = (k: Kurs) => setSecili((eski) => ({ ...(eski || k), ...k }));
    return (
      <section aria-labelledby="egitim-baslik" data-testid="egitim-sekmesi">
        {ustBaslik}
        <div className={`${KART} mb-4 flex flex-wrap items-center gap-3 p-4`} data-testid="egitim-kurs" data-kurs-id={secili.id} data-slug={secili.slug}>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => setSeciliId(null)} data-testid="egitim-geri">
            <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
            {t('egitim.geri')}
          </Button>
          <span className="flex h-10 w-10 flex-none items-center justify-center rounded-xl" style={{ background: secili.renk }}>
            <GraduationCap className="h-5 w-5 text-white" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-lg font-semibold" data-testid="egitim-kurs-adi">
                {secili.ad}
              </h3>
              <Rozet renk={DURUM_RENGI[secili.durum]} testid="egitim-durum-rozeti">
                {t(`egitim.durum.${secili.durum}`)}
              </Rozet>
              {mod === 'yonetici' && <span className="truncate text-xs text-muted-foreground">{secili.hesap_email || t('egitim.kurslar.ajans')}</span>}
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs">
              <a href={`/egitim/${secili.slug}`} target="_blank" rel="noopener" className="truncate font-mono text-blue-200 hover:underline" dir="ltr" data-testid="egitim-acik-baglanti">
                {secili.adres_url.replace(/^https?:\/\//, '')}
              </a>
              <Button size="icon" variant="ghost" className="h-7 w-7 flex-none" aria-label={t('egitim.kopyala')} onClick={() => kopyala(secili.adres_url, t('egitim.kopyalandi'), t('egitim.kopyalanamadi'))}>
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <a href={`/egitim/${secili.slug}`} target="_blank" rel="noopener" aria-label={t('egitim.ac')} className="text-muted-foreground hover:text-white">
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>
        <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={t('egitim.baslik')}>
          {altlar.map(({ anahtar, ikon: Ikon }) => (
            <SekmeDugmesi key={anahtar} secili={etkinAlt === anahtar} onClick={() => setAlt(anahtar)} testid={anahtar}>
              <Ikon className="h-4 w-4" aria-hidden="true" />
              {t(`egitim.alt.${anahtar}`)}
            </SekmeDugmesi>
          ))}
        </div>
        <Suspense fallback={<Yukleniyor />}>
          {etkinAlt === 'genel' && (
            <KursAyarlari
              api={api}
              meta={meta}
              kurs={secili}
              onKaydedildi={guncellendi}
              onSilindi={() => {
                setSeciliId(null);
                setListe(null);
              }}
            />
          )}
          {etkinAlt === 'ogrenciler' && <Ogrenciler api={api} kurs={secili} yonetim={yonetim} />}
          {etkinAlt === 'program' && <Program api={api} kurs={secili} yonetim={yonetim} />}
          {etkinAlt === 'dersler' && <Dersler api={api} kurs={secili} yonetim={yonetim} />}
          {etkinAlt === 'quiz' && <QuizOdev api={api} kurs={secili} yonetim={yonetim} meta={meta} />}
          {etkinAlt === 'sertifikalar' && <Sertifikalar api={api} kurs={secili} />}
          {etkinAlt === 'duyurular' && <Duyurular api={api} kurs={secili} />}
        </Suspense>
      </section>
    );
  }

  // ------------------------------------------------------------------ üst düzey: kurslar / ayarlar
  const sinirDolu = meta?.kurs_siniri != null && (meta.kurs_sayisi ?? 0) >= meta.kurs_siniri;
  return (
    <section aria-labelledby="egitim-baslik" data-testid="egitim-sekmesi">
      {ustBaslik}
      {yonetim && (
        <div className="mb-4 flex gap-1" role="tablist" aria-label={t('egitim.baslik')}>
          <SekmeDugmesi secili={ust === 'kurslar'} onClick={() => setUst('kurslar')} testid="kurslar">
            <GraduationCap className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ust.kurslar')}
          </SekmeDugmesi>
          <SekmeDugmesi secili={ust === 'ayarlar'} onClick={() => setUst('ayarlar')} testid="ayarlar">
            <Settings2 className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ust.ayarlar')}
          </SekmeDugmesi>
        </div>
      )}
      {ust === 'ayarlar' && yonetim && meta ? (
        <Suspense fallback={<Yukleniyor />}>
          <HesapAyarlari api={api} meta={meta} />
        </Suspense>
      ) : (
        <>
          {meta?.egitmen && (
            <p className={`${KART} mb-4 p-4 text-sm text-muted-foreground`} data-testid="egitim-egitmen-notu">
              {t('egitim.kurslar.egitmenNotu')}
            </p>
          )}
          {yonetim && (
            <div className={`${KART} mb-4 p-4 sm:p-6`}>
              <h3 className="mb-1 text-base font-semibold">{t('egitim.kurslar.yeniBaslik')}</h3>
              <p className="mb-3 text-sm text-muted-foreground">
                {t('egitim.kurslar.yeniAciklama')}
                {meta?.kurs_siniri != null && <> {t('egitim.kurslar.sinir', { sayi: meta.kurs_sayisi ?? 0, sinir: meta.kurs_siniri })}</>}
              </p>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                <label className="block text-sm">
                  <span className="mb-1 block text-muted-foreground">{t('egitim.alan.ad')}</span>
                  <Input
                    value={yeniAd}
                    onChange={(e) => setYeniAd(e.target.value)}
                    maxLength={160}
                    placeholder={t('egitim.kurslar.adOrnek')}
                    data-testid="egitim-yeni-ad"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void olustur();
                    }}
                  />
                </label>
                <Button onClick={() => void olustur()} disabled={olusturuluyor || sinirDolu} className="gap-1.5" data-testid="egitim-yeni">
                  {olusturuluyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
                  {t('egitim.kurslar.olustur')}
                </Button>
                {mod === 'yonetici' && (
                  <label className="block text-sm sm:col-span-2">
                    <span className="mb-1 block text-muted-foreground">{t('egitim.kurslar.hesap')}</span>
                    <Input value={yeniHesap} onChange={(e) => setYeniHesap(e.target.value)} type="email" placeholder="musteri@ornek.com" dir="ltr" />
                  </label>
                )}
              </div>
            </div>
          )}
          <div className={`${KART} p-4 sm:p-6`}>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-semibold">{t('egitim.kurslar.baslik')}</h3>
              {mod === 'yonetici' && (
                <select className="h-9 rounded-md border border-white/10 bg-black/40 px-2 text-sm" value={kapsam} onChange={(e) => setKapsam(e.target.value)} aria-label={t('egitim.kurslar.sahip')}>
                  <option value="">{t('egitim.kurslar.hepsi')}</option>
                  <option value="ajans">{t('egitim.kurslar.yalnizAjans')}</option>
                </select>
              )}
            </div>
            {hata && (
              <p className="mb-3 text-sm text-red-300" role="alert">
                {hata}
              </p>
            )}
            {liste === null ? (
              <Yukleniyor />
            ) : liste.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground" data-testid="egitim-bos">
                {meta?.egitmen ? t('egitim.kurslar.bosEgitmen') : t('egitim.kurslar.bos')}
              </p>
            ) : (
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="egitim-liste">
                {liste.map((k) => (
                  <li key={k.id} data-slug={k.slug}>
                    <button
                      type="button"
                      onClick={() => {
                        setAlt(yonetim ? (k.durum === 'taslak' ? 'genel' : 'ogrenciler') : 'program');
                        setSeciliId(k.id);
                      }}
                      className="flex h-full w-full items-start gap-3 rounded-xl border border-white/10 bg-black/20 p-3 text-start transition-colors hover:border-blue-400/40 hover:bg-white/[0.04]"
                      data-testid="egitim-ac"
                    >
                      <span className="flex h-11 w-11 flex-none items-center justify-center rounded-xl" style={{ background: k.renk }}>
                        <GraduationCap className="h-5 w-5 text-white" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{k.ad}</span>
                        <span className="block truncate text-[11px] text-muted-foreground">
                          {k.baslangic_tarihi ? `${gunYaz(k.baslangic_tarihi, dil)}${k.bitis_tarihi ? ` – ${gunYaz(k.bitis_tarihi, dil)}` : ''}` : t('egitim.kurslar.tarihYok')}
                        </span>
                        {k.sonraki_ders && (
                          <span className="block truncate text-[11px] text-muted-foreground">
                            {t('egitim.kurslar.sonrakiDers', { zaman: tarihSaat(k.sonraki_ders, k.saat_dilimi, dil) })}
                          </span>
                        )}
                        <span className="mt-1.5 flex flex-wrap items-center gap-1">
                          <Rozet renk={DURUM_RENGI[k.durum]}>{t(`egitim.durum.${k.durum}`)}</Rozet>
                          <Rozet>{t('egitim.kurslar.ogrenciSayisi', { sayi: k.ogrenci || 0 })}</Rozet>
                          {!!k.bekleme && <Rozet renk="border-amber-400/40 bg-amber-500/15 text-amber-200">{t('egitim.kurslar.beklemeSayisi', { sayi: k.bekleme })}</Rozet>}
                          {mod === 'yonetici' && <span className="truncate text-[11px] text-muted-foreground">{k.hesap_email || t('egitim.kurslar.ajans')}</span>}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
