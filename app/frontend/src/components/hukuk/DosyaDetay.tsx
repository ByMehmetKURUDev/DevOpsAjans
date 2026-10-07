import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, CalendarDays, Clock, FileText, Globe, Loader2, Lock, Plus, Receipt, Settings2, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, CatismaListesi, DURUM_RENGI, GIRDI, KART, METIN_ALANI, Not, Rozet, SECIM, SekmeDugmesi, Yukleniyor } from '@/components/hukuk/ortak';
import { hataMetni, type Catisma, type Dosya, type HukukApi, type KarsiTaraf, type Meta, type Muvekkil, type PortalAlani } from '@/lib/hukuk';

const OlaylarPaneli = lazy(() => import('@/components/hukuk/DosyaKayitlari').then((m) => ({ default: m.OlaylarPaneli })));
const ZamanPaneli = lazy(() => import('@/components/hukuk/DosyaKayitlari').then((m) => ({ default: m.ZamanPaneli })));
const MasrafPaneli = lazy(() => import('@/components/hukuk/DosyaKayitlari').then((m) => ({ default: m.MasrafPaneli })));
const BelgelerPaneli = lazy(() => import('@/components/hukuk/DosyaKayitlari').then((m) => ({ default: m.BelgelerPaneli })));

type Alt = 'genel' | 'olaylar' | 'zaman' | 'masraf' | 'belgeler' | 'portal';
const ALTLAR: { anahtar: Alt; ikon: typeof Clock }[] = [
  { anahtar: 'genel', ikon: Settings2 },
  { anahtar: 'olaylar', ikon: CalendarDays },
  { anahtar: 'zaman', ikon: Clock },
  { anahtar: 'masraf', ikon: Receipt },
  { anahtar: 'belgeler', ikon: FileText },
  { anahtar: 'portal', ikon: Globe },
];
const PORTAL_ALANLARI: PortalAlani[] = ['konu', 'durum', 'durusma', 'belgeler', 'masraf', 'not'];

/** Faz 6H — dosya çalışma alanı: genel bilgiler + karşı taraflar (çatışma kontrolü), takvim, saat, masraf, belgeler, portal. */
export default function DosyaDetay({ api, meta, id, onKapat }: { api: HukukApi; meta: Meta; id: number; onKapat: () => void }) {
  const { t } = useTranslation();
  const [d, setD] = useState<Dosya | null>(null);
  const [form, setForm] = useState<Dosya | null>(null);
  const [etiketMetni, setEtiketMetni] = useState('');
  const [muvekkiller, setMuvekkiller] = useState<Muvekkil[]>([]);
  const [alt, setAlt] = useState<Alt>('genel');
  const [catisma, setCatisma] = useState<Catisma[] | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      const x = await api.dosya(id);
      setD(x);
      setForm(x);
      setEtiketMetni(x.etiketler.join(', '));
    } catch (e) {
      toast.error(hataMetni(t, e));
      onKapat();
    }
  }, [api, id, onKapat, t]);

  useEffect(() => {
    void yukle();
    api
      .muvekkiller()
      .then((r) => setMuvekkiller(r.items))
      .catch(() => setMuvekkiller([]));
  }, [api, yukle]);

  if (!d || !form) return <Yukleniyor />;

  const alan = <K extends keyof Dosya>(k: K, v: Dosya[K]) => setForm({ ...form, [k]: v });
  const karsi = (i: number, k: keyof KarsiTaraf, v: string) => {
    const liste = form.karsi_taraflar.map((x, j) => (j === i ? { ...x, [k]: v } : x));
    setForm({ ...form, karsi_taraflar: liste });
  };
  const karsiKontrol = async (x: KarsiTaraf) => {
    if (!x.ad.trim() && !x.vergi_no.trim()) return;
    try {
      const r = await api.catisma({ ad: x.ad, vergi_no: x.vergi_no || undefined, rol: 'karsi_taraf', haric_dosya_id: d.id });
      setCatisma(r.items.map((c) => ({ ...c, aranan: x.ad })));
    } catch {
      /* uyarı yalnız bilgi */
    }
  };

  const kaydet = async (yalniz?: Partial<Dosya>) => {
    setKaydediliyor(true);
    try {
      const g: Partial<Dosya> = yalniz ?? {
        muvekkil_id: form.muvekkil_id, tur: form.tur, dosya_no: form.dosya_no, esas_no: form.esas_no, mahkeme: form.mahkeme,
        konu: form.konu, durum: form.durum, sorumlu_email: form.sorumlu_email, acilis_tarihi: form.acilis_tarihi,
        kapanis_tarihi: form.kapanis_tarihi, notlar: form.notlar, gizli: form.gizli,
        karsi_taraflar: form.karsi_taraflar.filter((x) => x.ad.trim()),
        etiketler: etiketMetni.split(',').map((x) => x.trim()).filter(Boolean),
      };
      const r = await api.dosyaKaydet(d.id, g);
      setD(r.dosya);
      setForm(r.dosya);
      setEtiketMetni(r.dosya.etiketler.join(', '));
      if ('karsi_taraflar' in g) setCatisma(r.catisma);
      toast.success(t('hukuk.ortak.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const sil = async () => {
    if (!window.confirm(t('hukuk.ortak.onaySil'))) return;
    try {
      await api.dosyaSil(d.id);
      toast.success(t('hukuk.ortak.silindi', { gun: meta.silinenler_gun }));
      onKapat();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div data-testid="hukuk-dosya" data-dosya-id={d.id}>
      <div className={`${KART} mb-4 flex flex-wrap items-center gap-3 p-4`}>
        <Button size="sm" variant="ghost" className="gap-1" onClick={onKapat} data-testid="hukuk-dosya-geri">
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          {t('hukuk.ortak.geri')}
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {d.gizli && <Lock className="h-4 w-4 text-amber-300" aria-label={t('hukuk.dosya.gizliRozet')} />}
            <h3 className="truncate text-lg font-semibold" data-testid="hukuk-dosya-baslik">
              {d.baslik}
            </h3>
            <Rozet renk={DURUM_RENGI[d.durum]}>{t(`hukuk.dosya.durum.${d.durum}`)}</Rozet>
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {d.muvekkil_ad}
            {d.mahkeme ? ` · ${d.mahkeme}` : ''}
          </p>
        </div>
      </div>
      <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label={d.baslik}>
        {ALTLAR.map(({ anahtar, ikon: Ikon }) => (
          <SekmeDugmesi key={anahtar} secili={alt === anahtar} onClick={() => setAlt(anahtar)} testid={`dosya-${anahtar}`}>
            <Ikon className="h-4 w-4" aria-hidden="true" />
            {t(`hukuk.dosya.alt.${anahtar}`)}
          </SekmeDugmesi>
        ))}
      </div>

      {alt === 'genel' && (
        <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-dosya-genel">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Alan etiket={t('hukuk.dosya.alan.muvekkil')}>
              <select className={SECIM} value={form.muvekkil_id} onChange={(e) => alan('muvekkil_id', Number(e.target.value))}>
                {muvekkiller.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.ad}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.tur')}>
              <select className={SECIM} value={form.tur} onChange={(e) => alan('tur', e.target.value as Dosya['tur'])}>
                {meta.dosya_turleri.map((x) => (
                  <option key={x} value={x}>
                    {t(`hukuk.dosya.tur.${x}`)}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.durum')}>
              <select className={SECIM} value={form.durum} onChange={(e) => alan('durum', e.target.value as Dosya['durum'])} data-testid="hukuk-dosya-durum">
                {meta.dosya_durumlari.map((x) => (
                  <option key={x} value={x}>
                    {t(`hukuk.dosya.durum.${x}`)}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.dosyaNo')}>
              <input className={GIRDI} value={form.dosya_no} maxLength={60} onChange={(e) => alan('dosya_no', e.target.value)} />
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.esasNo')}>
              <input className={GIRDI} value={form.esas_no} maxLength={60} onChange={(e) => alan('esas_no', e.target.value)} data-testid="hukuk-dosya-esas" />
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.mahkeme')}>
              <input className={GIRDI} value={form.mahkeme} maxLength={200} onChange={(e) => alan('mahkeme', e.target.value)} data-testid="hukuk-dosya-mahkeme" />
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.konu')} className="sm:col-span-2 lg:col-span-3">
              <input className={GIRDI} value={form.konu} maxLength={300} onChange={(e) => alan('konu', e.target.value)} />
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.sorumlu')}>
              <select className={SECIM} value={form.sorumlu_email} onChange={(e) => alan('sorumlu_email', e.target.value)}>
                <option value="">—</option>
                {meta.ekip.map((k) => (
                  <option key={k.eposta} value={k.eposta}>
                    {k.eposta}
                  </option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.acilis')}>
              <input className={GIRDI} type="date" value={form.acilis_tarihi || ''} onChange={(e) => alan('acilis_tarihi', e.target.value || null)} />
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.kapanis')}>
              <input className={GIRDI} type="date" value={form.kapanis_tarihi || ''} onChange={(e) => alan('kapanis_tarihi', e.target.value || null)} />
            </Alan>
            <Alan etiket={t('hukuk.dosya.alan.etiketler')} className="sm:col-span-2 lg:col-span-3">
              <input className={GIRDI} value={etiketMetni} onChange={(e) => setEtiketMetni(e.target.value)} />
            </Alan>
          </div>

          <fieldset className="rounded-xl border border-white/10 p-3" data-testid="hukuk-karsi-taraflar">
            <legend className="px-1 text-sm font-medium">{t('hukuk.dosya.karsi.baslik')}</legend>
            <div className="space-y-2">
              {form.karsi_taraflar.map((x, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,2fr)_auto]">
                  <input
                    className={GIRDI}
                    value={x.ad}
                    placeholder={t('hukuk.dosya.karsi.ad')}
                    aria-label={t('hukuk.dosya.karsi.ad')}
                    onChange={(e) => karsi(i, 'ad', e.target.value)}
                    onBlur={() => void karsiKontrol(form.karsi_taraflar[i])}
                    data-testid="hukuk-karsi-ad"
                  />
                  <input
                    className={GIRDI}
                    value={x.vergi_no}
                    dir="ltr"
                    placeholder={t('hukuk.dosya.karsi.vergiNo')}
                    aria-label={t('hukuk.dosya.karsi.vergiNo')}
                    onChange={(e) => karsi(i, 'vergi_no', e.target.value)}
                    onBlur={() => void karsiKontrol(form.karsi_taraflar[i])}
                  />
                  <input className={GIRDI} value={x.vekil} placeholder={t('hukuk.dosya.karsi.vekil')} aria-label={t('hukuk.dosya.karsi.vekil')} onChange={(e) => karsi(i, 'vekil', e.target.value)} />
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={t('hukuk.ortak.sil')}
                    onClick={() => setForm({ ...form, karsi_taraflar: form.karsi_taraflar.filter((_, j) => j !== i) })}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              ))}
            </div>
            <Button
              size="sm"
              variant="ghost"
              className="mt-2 gap-1"
              onClick={() => setForm({ ...form, karsi_taraflar: [...form.karsi_taraflar, { ad: '', vergi_no: '', vekil: '' }] })}
              data-testid="hukuk-karsi-ekle"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('hukuk.dosya.karsi.ekle')}
            </Button>
            <div className="mt-2">
              <CatismaListesi items={catisma} testid="hukuk-dosya-catisma" />
            </div>
          </fieldset>

          <Alan etiket={t('hukuk.dosya.alan.notlar')}>
            <textarea className={`${METIN_ALANI} min-h-[120px]`} value={form.notlar} maxLength={20000} onChange={(e) => alan('notlar', e.target.value)} data-testid="hukuk-dosya-notlar" />
          </Alan>
          <div>
            <Anahtar acik={form.gizli} onDegis={(v) => alan('gizli', v)} etiket={t('hukuk.dosya.alan.gizli')} testid="hukuk-dosya-gizli" />
            <p className="ms-6 text-xs text-muted-foreground">{t('hukuk.dosya.alan.gizliIpucu')}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="hukuk-dosya-kaydet">
              {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('hukuk.ortak.kaydet')}
            </Button>
            <Button variant="ghost" className="ms-auto gap-1 text-red-300" onClick={() => void sil()}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('hukuk.ortak.sil')}
            </Button>
          </div>
        </div>
      )}

      {alt === 'portal' && (
        <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="hukuk-dosya-portal">
          <Anahtar acik={form.portal_acik} onDegis={(v) => alan('portal_acik', v)} etiket={t('hukuk.dosya.portal.acik')} testid="hukuk-dosya-portal-acik" />
          <fieldset disabled={!form.portal_acik} className="space-y-2 disabled:opacity-50">
            <legend className="mb-1 text-sm font-medium">{t('hukuk.dosya.portal.alanlar')}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {PORTAL_ALANLARI.map((a) => (
                <Anahtar
                  key={a}
                  acik={!!form.portal_alanlari[a]}
                  onDegis={(v) => alan('portal_alanlari', { ...form.portal_alanlari, [a]: v })}
                  etiket={t(`hukuk.dosya.portal.alan.${a}`)}
                  testid={`hukuk-portal-alan-${a}`}
                />
              ))}
            </div>
            {form.portal_alanlari.not && (
              <Alan etiket={t('hukuk.dosya.portal.not')} ipucu={t('hukuk.dosya.portal.notIpucu')}>
                <textarea className={METIN_ALANI} value={form.muvekkil_notu} maxLength={2000} onChange={(e) => alan('muvekkil_notu', e.target.value)} />
              </Alan>
            )}
          </fieldset>
          <Not>{t('hukuk.dosya.portal.gizlilik')}</Not>
          <Button
            onClick={() => void kaydet({ portal_acik: form.portal_acik, portal_alanlari: form.portal_alanlari, muvekkil_notu: form.muvekkil_notu })}
            disabled={kaydediliyor}
            data-testid="hukuk-dosya-portal-kaydet"
          >
            {t('hukuk.ortak.kaydet')}
          </Button>
        </div>
      )}

      <Suspense fallback={<Yukleniyor />}>
        {alt === 'olaylar' && <OlaylarPaneli api={api} meta={meta} dosya={d} />}
        {alt === 'zaman' && <ZamanPaneli api={api} dosya={d} />}
        {alt === 'masraf' && <MasrafPaneli api={api} meta={meta} dosya={d} />}
        {alt === 'belgeler' && <BelgelerPaneli api={api} meta={meta} dosya={d} />}
      </Suspense>
    </div>
  );
}
