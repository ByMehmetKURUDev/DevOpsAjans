import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Braces, FlaskConical, Loader2, Plus, Save, Trash2, X } from 'lucide-react';

import KuruSonucGorunumu from '@/components/otomasyon/KuruSonuc';
import {
  alanAdi,
  anahtarAdi,
  bosEylem,
  hataMetni,
  type Eylem,
  type EylemTuru,
  type Kosul,
  type KosulGrubu,
  type Kural,
  type KuruSonuc,
  type OtoMeta,
  type OtoMod,
  type OtomasyonApi,
  type SemaAlani,
} from '@/lib/otomasyon';
import { ALAN, ANA_DUGME, Etiket, IKINCIL_DUGME, KART, SECIM } from './ortak';

interface Props {
  api: OtomasyonApi;
  meta: OtoMeta;
  mod: OtoMod;
  kural: Kural | null;
  onKapat: () => void;
  onKaydedildi: () => void;
  /** Faz 11C: akış görünümünde tıklanan düğümün adımıyla aç (tetikleyici / koşullar / eylemler). */
  baslangic?: 'tetik' | 'kosullar' | 'eylemler';
}

interface Taslak {
  ad: string;
  aciklama: string;
  aktif: boolean;
  /** Faz 7H: "bekle"den sonra koşulları yeniden denetle (yeni kuralda açık). */
  denetim: boolean;
  tetik: string;
  kosullar: KosulGrubu;
  eylemler: Eylem[];
}

const ADIMLAR = ['tetik', 'kosullar', 'eylemler', 'kaydet'] as const;
type Adim = (typeof ADIMLAR)[number];
/** Yer tutucu yazılabilen eylem alanları. */
const METIN_ALANLARI = new Set(['konu', 'govde', 'baslik', 'aciklama', 'metin']);

/**
 * Adım adım kural düzenleyici: tetikleyici olay → koşullar (tek seviye VE/VEYA) →
 * sıralı eylemler (en çok 5) → ad + kuru çalıştırma + kaydet. Doğrulamanın asıl
 * sahibi sunucu; burada yalnız rahat bir form.
 */
export default function KuralDuzenleyici({ api, meta, mod, kural, onKapat, onKaydedildi, baslangic }: Props) {
  const { t } = useTranslation();
  const ajans = mod === 'yonetici';
  const [adim, setAdim] = useState<Adim>(kural ? (baslangic ?? 'eylemler') : 'tetik');
  const [taslak, setTaslak] = useState<Taslak>(() => ({
    ad: kural?.ad ?? '',
    aciklama: kural?.aciklama ?? '',
    aktif: kural?.aktif ?? true,
    denetim: kural ? !!kural.bekleme_sonrasi_denetim : true,
    tetik: kural?.tetik ?? '',
    kosullar: kural?.kosullar ?? { baglac: 've', kosullar: [] },
    eylemler: kural?.eylemler ?? [],
  }));
  const [mesgul, setMesgul] = useState(false);
  const [testMetni, setTestMetni] = useState('');
  const [testSonuc, setTestSonuc] = useState<KuruSonuc | null>(null);
  const odak = useRef<{ i: number; alan: string; imlec: number } | null>(null);

  const olay = meta.olaylar.find((o) => o.anahtar === taslak.tetik);
  const sema: SemaAlani[] = useMemo(() => olay?.sema ?? [], [olay]);
  const semaHaritasi = useMemo(() => new Map(sema.map((a) => [a.yol, a])), [sema]);

  useEffect(() => {
    if (adim !== 'kaydet' || !taslak.tetik || testMetni) return;
    api
      .ornekBaglam(taslak.tetik)
      .then((b) => setTestMetni(JSON.stringify(b, null, 2)))
      .catch(() => undefined);
  }, [adim, api, taslak.tetik, testMetni]);

  const tetikSec = (tetik: string) =>
    setTaslak((x) => {
      const yeni = meta.olaylar.find((o) => o.anahtar === tetik);
      const yollar = new Set((yeni?.sema ?? []).map((a) => a.yol));
      return {
        ...x,
        tetik,
        kosullar: { ...x.kosullar, kosullar: x.kosullar.kosullar.filter((k) => yollar.has(k.alan)) },
        eylemler: x.eylemler.map((e) => (e.tur === 'gorev' && e.proje === 'olay' && !yeni?.proje_var ? { ...e, proje: '' } : e)),
      };
    });

  // --- Koşullar -----------------------------------------------------------------
  const kosulYaz = (i: number, k: Partial<Kosul>) =>
    setTaslak((x) => ({
      ...x,
      kosullar: { ...x.kosullar, kosullar: x.kosullar.kosullar.map((v, j) => (j === i ? { ...v, ...k } : v)) },
    }));
  const kosulEkle = () =>
    setTaslak((x) => ({
      ...x,
      kosullar: { ...x.kosullar, kosullar: [...x.kosullar.kosullar, { alan: sema[0]?.yol ?? '', islec: 'esittir', deger: '' }] },
    }));
  const kosulSil = (i: number) =>
    setTaslak((x) => ({ ...x, kosullar: { ...x.kosullar, kosullar: x.kosullar.kosullar.filter((_, j) => j !== i) } }));

  // --- Eylemler -----------------------------------------------------------------
  const eylemYaz = (i: number, alan: string, deger: unknown) =>
    setTaslak((x) => ({ ...x, eylemler: x.eylemler.map((e, j) => (j === i ? { ...e, [alan]: deger } : e)) }));
  const eylemEkle = (tur: EylemTuru) => setTaslak((x) => ({ ...x, eylemler: [...x.eylemler, bosEylem(tur, ajans)] }));
  const eylemSil = (i: number) => setTaslak((x) => ({ ...x, eylemler: x.eylemler.filter((_, j) => j !== i) }));
  const eylemTasi = (i: number, yon: -1 | 1) =>
    setTaslak((x) => {
      const l = [...x.eylemler];
      const j = i + yon;
      if (j < 0 || j >= l.length) return x;
      [l[i], l[j]] = [l[j], l[i]];
      return { ...x, eylemler: l };
    });

  const degiskenEkle = (yol: string) => {
    const o = odak.current;
    if (!o) {
      toast.message(t('otomasyon.duzenleyici.once_alan_sec'));
      return;
    }
    const mevcut = String(taslak.eylemler[o.i]?.[o.alan] ?? '');
    const imlec = Math.min(o.imlec, mevcut.length);
    const ek = `{{${yol}}}`;
    eylemYaz(o.i, o.alan, mevcut.slice(0, imlec) + ek + mevcut.slice(imlec));
    odak.current = { ...o, imlec: imlec + ek.length };
  };

  const metinOlaylari = (i: number, alan: string) => ({
    onFocus: (e: { target: HTMLInputElement | HTMLTextAreaElement }) =>
      (odak.current = { i, alan, imlec: e.target.selectionStart ?? String(e.target.value).length }),
    onSelect: (e: { currentTarget: HTMLInputElement | HTMLTextAreaElement }) =>
      (odak.current = { i, alan, imlec: e.currentTarget.selectionStart ?? 0 }),
    'data-oto-metin': `${i}-${alan}`,
  });

  const govde = () => ({
    ad: taslak.ad.trim(),
    aciklama: taslak.aciklama.trim() || null,
    aktif: taslak.aktif,
    bekleme_sonrasi_denetim: taslak.denetim,
    tetik: taslak.tetik,
    kosullar: {
      baglac: taslak.kosullar.baglac,
      kosullar: taslak.kosullar.kosullar.map((k) =>
        meta.degersiz_islecler.includes(k.islec) ? { alan: k.alan, islec: k.islec } : { alan: k.alan, islec: k.islec, deger: k.deger ?? '' }
      ),
    },
    eylemler: taslak.eylemler,
  });

  const testEt = async () => {
    let baglam: Record<string, unknown> | undefined;
    if (testMetni.trim()) {
      try {
        baglam = JSON.parse(testMetni) as Record<string, unknown>;
      } catch {
        toast.error(t('otomasyon.test.jsonHatali'));
        return;
      }
    }
    setMesgul(true);
    try {
      setTestSonuc(await api.taslakTest({ ...govde(), ad: govde().ad || '—' }, baglam ? { baglam } : {}));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const kaydet = async () => {
    setMesgul(true);
    try {
      if (kural) await api.guncelle(kural.id, govde());
      else await api.olustur(govde());
      toast.success(t('otomasyon.kural.kaydedildi'));
      onKaydedildi();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const adimNo = ADIMLAR.indexOf(adim);
  const ileriOlur =
    (adim === 'tetik' && !!taslak.tetik) || adim === 'kosullar' || (adim === 'eylemler' && taslak.eylemler.length > 0);

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="oto-duzenleyici">
      <div className="mb-4 flex items-start justify-between gap-3">
        <h3 className="text-lg font-semibold">{kural ? t('otomasyon.duzenleyici.duzenle') : t('otomasyon.duzenleyici.yeni')}</h3>
        <button type="button" className="rounded-lg p-2 hover:bg-white/5" onClick={onKapat} aria-label={t('otomasyon.kapat')}>
          <X className="h-4 w-4" />
        </button>
      </div>

      <ol className="mb-5 flex gap-1 overflow-x-auto pb-1" aria-label={t('otomasyon.duzenleyici.adimlar')}>
        {ADIMLAR.map((a, i) => (
          <li key={a} className="shrink-0">
            <button
              type="button"
              onClick={() => (i <= adimNo || (taslak.tetik && i < 3) || (taslak.tetik && taslak.eylemler.length) ? setAdim(a) : undefined)}
              aria-current={adim === a ? 'step' : undefined}
              data-oto-adim={a}
              className={`rounded-full border px-3 py-1 text-xs ${
                adim === a ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'
              }`}
            >
              {i + 1}. {t(`otomasyon.duzenleyici.adim.${a}`)}
            </button>
          </li>
        ))}
      </ol>

      {adim === 'tetik' && (
        <fieldset>
          <legend className="mb-3 text-sm text-muted-foreground">{t('otomasyon.duzenleyici.tetikAciklama')}</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {meta.olaylar.map((o) => (
              <label
                key={o.anahtar}
                className={`flex cursor-pointer items-start gap-2 rounded-xl border p-3 text-sm ${
                  taslak.tetik === o.anahtar ? 'border-purple-400/60 bg-purple-500/15' : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05]'
                }`}
              >
                <input
                  type="radio"
                  name="oto-tetik"
                  className="mt-0.5 accent-purple-500"
                  checked={taslak.tetik === o.anahtar}
                  onChange={() => tetikSec(o.anahtar)}
                  data-oto-tetik={o.anahtar}
                />
                <span className="min-w-0">
                  <span className="block font-medium">{t(`otomasyon.olay.${anahtarAdi(o.anahtar)}`)}</span>
                  <span className="block text-xs text-muted-foreground">{t(`otomasyon.olayAciklama.${anahtarAdi(o.anahtar)}`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {adim === 'kosullar' && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t('otomasyon.duzenleyici.kosulAciklama')}</p>
          <div className="flex flex-wrap items-center gap-3 text-sm" role="radiogroup" aria-label={t('otomasyon.duzenleyici.baglac')}>
            {(['ve', 'veya'] as const).map((b) => (
              <label key={b} className="inline-flex items-center gap-1.5">
                <input
                  type="radio"
                  name="oto-baglac"
                  className="accent-purple-500"
                  checked={taslak.kosullar.baglac === b}
                  onChange={() => setTaslak((x) => ({ ...x, kosullar: { ...x.kosullar, baglac: b } }))}
                  data-oto-baglac={b}
                />
                {t(`otomasyon.baglac.${b}`)}
              </label>
            ))}
          </div>
          {taslak.kosullar.kosullar.length === 0 && (
            <p className="rounded-lg border border-dashed border-white/15 p-3 text-xs text-muted-foreground">{t('otomasyon.duzenleyici.kosulYok')}</p>
          )}
          <ul className="space-y-2">
            {taslak.kosullar.kosullar.map((k, i) => {
              const a = semaHaritasi.get(k.alan);
              const degersiz = meta.degersiz_islecler.includes(k.islec);
              return (
                <li key={i} className="grid gap-2 rounded-xl border border-white/10 bg-black/20 p-2 sm:grid-cols-[2fr_1.3fr_2fr_auto]" data-oto-kosul={i}>
                  <select
                    className={SECIM}
                    value={k.alan}
                    aria-label={t('otomasyon.duzenleyici.alan')}
                    onChange={(e) => {
                      const yeni = semaHaritasi.get(e.target.value);
                      kosulYaz(i, { alan: e.target.value, islec: k.islec === 'degisti' && !yeni?.degisir ? 'esittir' : k.islec });
                    }}
                    data-testid="oto-kosul-alan"
                  >
                    {sema.map((s) => (
                      <option key={s.yol} value={s.yol}>
                        {alanAdi(t, s, s.yol)}
                      </option>
                    ))}
                  </select>
                  <select
                    className={SECIM}
                    value={k.islec}
                    aria-label={t('otomasyon.duzenleyici.islec')}
                    onChange={(e) => kosulYaz(i, { islec: e.target.value })}
                    data-testid="oto-kosul-islec"
                  >
                    {meta.islecler
                      .filter((is) => is !== 'degisti' || a?.degisir)
                      .map((is) => (
                        <option key={is} value={is}>
                          {t(`otomasyon.islec.${is}`)}
                        </option>
                      ))}
                  </select>
                  {degersiz ? (
                    <span className="hidden sm:block" />
                  ) : a?.secenekler?.length ? (
                    <select className={SECIM} value={k.deger ?? ''} aria-label={t('otomasyon.duzenleyici.deger')} onChange={(e) => kosulYaz(i, { deger: e.target.value })} data-testid="oto-kosul-deger">
                      <option value="">—</option>
                      {a.secenekler.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  ) : a?.tur === 'evet_hayir' ? (
                    <select className={SECIM} value={k.deger ?? ''} aria-label={t('otomasyon.duzenleyici.deger')} onChange={(e) => kosulYaz(i, { deger: e.target.value })} data-testid="oto-kosul-deger">
                      <option value="">—</option>
                      <option value="true">{t('otomasyon.evet')}</option>
                      <option value="false">{t('otomasyon.hayir')}</option>
                    </select>
                  ) : (
                    <input
                      className={ALAN}
                      type={a?.tur === 'tarih' ? 'date' : a?.tur === 'sayi' ? 'number' : 'text'}
                      step="any"
                      value={k.deger ?? ''}
                      maxLength={200}
                      aria-label={t('otomasyon.duzenleyici.deger')}
                      onChange={(e) => kosulYaz(i, { deger: e.target.value })}
                      data-testid="oto-kosul-deger"
                    />
                  )}
                  <button type="button" className={`${IKINCIL_DUGME} px-2`} onClick={() => kosulSil(i)} aria-label={t('otomasyon.duzenleyici.kosulSil')}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            className={IKINCIL_DUGME}
            onClick={kosulEkle}
            disabled={taslak.kosullar.kosullar.length >= meta.sinirlar.kosul || !sema.length}
            data-testid="oto-kosul-ekle"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('otomasyon.duzenleyici.kosulEkle')}
          </button>
        </div>
      )}

      {adim === 'eylemler' && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t('otomasyon.duzenleyici.eylemAciklama', { sayi: meta.sinirlar.eylem })}</p>
          <ol className="space-y-3">
            {taslak.eylemler.map((e, i) => (
              <li key={i} className="rounded-xl border border-white/10 bg-black/20 p-3" data-oto-eylem={e.tur} data-sira={i}>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">
                    {i + 1}. {t(`otomasyon.eylem.${e.tur}`)}
                  </span>
                  <span className="flex gap-1">
                    <button type="button" className={`${IKINCIL_DUGME} px-2 py-1`} onClick={() => eylemTasi(i, -1)} disabled={i === 0} aria-label={t('otomasyon.duzenleyici.yukari')}>
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      className={`${IKINCIL_DUGME} px-2 py-1`}
                      onClick={() => eylemTasi(i, 1)}
                      disabled={i === taslak.eylemler.length - 1}
                      aria-label={t('otomasyon.duzenleyici.asagi')}
                    >
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                    <button type="button" className={`${IKINCIL_DUGME} px-2 py-1`} onClick={() => eylemSil(i)} aria-label={t('otomasyon.duzenleyici.eylemSil')}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </span>
                </div>
                <EylemAlanlari e={e} i={i} meta={meta} ajans={ajans} projeVar={!!olay?.proje_var} yaz={eylemYaz} metinOlaylari={metinOlaylari} />
              </li>
            ))}
          </ol>
          <label className="block max-w-xs text-sm">
            <span className="mb-1 block text-xs text-muted-foreground">{t('otomasyon.duzenleyici.eylemEkle')}</span>
            <select
              className={SECIM}
              value=""
              disabled={taslak.eylemler.length >= meta.sinirlar.eylem}
              onChange={(ev) => ev.target.value && eylemEkle(ev.target.value as EylemTuru)}
              data-testid="oto-eylem-ekle"
            >
              <option value="">{t('otomasyon.duzenleyici.eylemSec')}</option>
              {meta.eylemler
                .filter((tur) => tur !== 'destek' || taslak.tetik.startsWith('destek.'))
                .map((tur) => (
                  <option key={tur} value={tur}>
                    {t(`otomasyon.eylem.${tur}`)}
                  </option>
                ))}
            </select>
          </label>
          {taslak.eylemler.some((e) => e.tur === 'bekle') && (
            <label className="flex items-start gap-2 rounded-xl border border-sky-400/20 bg-sky-500/[0.06] p-3 text-sm" data-testid="oto-bekle-denetim">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0 accent-purple-500"
                checked={taslak.denetim}
                onChange={(e) => setTaslak((x) => ({ ...x, denetim: e.target.checked }))}
                data-testid="oto-bekle-denetim-kutu"
              />
              <span className="min-w-0">
                <span className="block font-medium">{t('otomasyon.duzenleyici.bekleDenetim')}</span>
                <span className="block text-xs text-muted-foreground">{t('otomasyon.duzenleyici.bekleDenetimAciklama')}</span>
              </span>
            </label>
          )}
          {sema.length > 0 && taslak.eylemler.some((e) => Object.keys(e).some((k) => METIN_ALANLARI.has(k))) && (
            <details className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-sm" data-testid="oto-degiskenler">
              <summary className="flex cursor-pointer items-center gap-1.5 text-purple-200">
                <Braces className="h-4 w-4" aria-hidden="true" />
                {t('otomasyon.duzenleyici.degiskenler')}
              </summary>
              <p className="mt-2 text-xs text-muted-foreground">{t('otomasyon.duzenleyici.degiskenIpucu')}</p>
              <div className="mt-2 flex flex-wrap gap-1.5" dir="ltr">
                {sema.map((a) => (
                  <button
                    key={a.yol}
                    type="button"
                    title={alanAdi(t, a, a.yol)}
                    onMouseDown={(ev) => ev.preventDefault()}
                    onClick={() => degiskenEkle(a.yol)}
                    className="rounded-md border border-white/10 bg-black/40 px-2 py-0.5 font-mono text-[11px] text-slate-200 hover:border-purple-400/60"
                    data-oto-degisken={a.yol}
                  >
                    {`{{${a.yol}}}`}
                  </button>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {adim === 'kaydet' && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Etiket ad={t('otomasyon.duzenleyici.ad')}>
              <input className={ALAN} value={taslak.ad} maxLength={120} onChange={(e) => setTaslak((x) => ({ ...x, ad: e.target.value }))} required data-testid="oto-kural-ad-alani" />
            </Etiket>
            <label className="inline-flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={taslak.aktif} onChange={(e) => setTaslak((x) => ({ ...x, aktif: e.target.checked }))} />
              {t('otomasyon.duzenleyici.aktif')}
            </label>
            <Etiket ad={t('otomasyon.duzenleyici.aciklamaAlani')} tam>
              <textarea className={ALAN} rows={2} maxLength={1000} value={taslak.aciklama} onChange={(e) => setTaslak((x) => ({ ...x, aciklama: e.target.value }))} />
            </Etiket>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <h4 className="mb-1 flex items-center gap-1.5 text-sm font-medium">
              <FlaskConical className="h-4 w-4 text-sky-300" aria-hidden="true" />
              {t('otomasyon.test.kuruBaslik')}
            </h4>
            <p className="mb-2 text-xs text-muted-foreground">{t('otomasyon.test.kuruAciklama')}</p>
            <textarea
              className={`${ALAN} font-mono text-xs`}
              rows={8}
              dir="ltr"
              value={testMetni}
              onChange={(e) => setTestMetni(e.target.value)}
              aria-label={t('otomasyon.test.ornekVeri')}
              data-testid="oto-test-veri"
            />
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className={IKINCIL_DUGME} onClick={() => void testEt()} disabled={mesgul || !taslak.eylemler.length} data-testid="oto-test-et">
                {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" aria-hidden="true" />}
                {t('otomasyon.kural.test')}
              </button>
              <button type="button" className={IKINCIL_DUGME} onClick={() => setTestMetni('')}>
                {t('otomasyon.test.ornekYenile')}
              </button>
            </div>
            {testSonuc && (
              <div className="mt-3">
                <KuruSonucGorunumu sonuc={testSonuc} meta={meta} tetik={taslak.tetik} onKapat={() => setTestSonuc(null)} />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mt-6 flex flex-wrap justify-between gap-2 border-t border-white/10 pt-4">
        <button type="button" className={IKINCIL_DUGME} onClick={() => (adimNo > 0 ? setAdim(ADIMLAR[adimNo - 1]) : onKapat())}>
          <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          {adimNo > 0 ? t('otomasyon.duzenleyici.geri') : t('otomasyon.vazgec')}
        </button>
        {adim !== 'kaydet' ? (
          <button type="button" className={ANA_DUGME} disabled={!ileriOlur} onClick={() => setAdim(ADIMLAR[adimNo + 1])} data-testid="oto-ileri">
            {t('otomasyon.duzenleyici.ileri')}
            <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden="true" />
          </button>
        ) : (
          <button type="button" className={ANA_DUGME} disabled={mesgul || !taslak.ad.trim() || !taslak.eylemler.length} onClick={() => void kaydet()} data-testid="oto-kaydet">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" aria-hidden="true" />}
            {t('otomasyon.kaydet')}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Eylem türüne göre alanlar
// ---------------------------------------------------------------------------
function EylemAlanlari({
  e,
  i,
  meta,
  ajans,
  projeVar,
  yaz,
  metinOlaylari,
}: {
  e: Eylem;
  i: number;
  meta: OtoMeta;
  ajans: boolean;
  projeVar: boolean;
  yaz: (i: number, alan: string, deger: unknown) => void;
  metinOlaylari: (i: number, alan: string) => Record<string, unknown>;
}) {
  const { t, i18n } = useTranslation();
  const s = (alan: string) => String(e[alan] ?? '');
  const metin = (alan: string, sinir: number, cok = false) =>
    cok ? (
      <textarea className={ALAN} rows={4} maxLength={sinir} value={s(alan)} onChange={(ev) => yaz(i, alan, ev.target.value)} {...metinOlaylari(i, alan)} />
    ) : (
      <input className={ALAN} maxLength={sinir} value={s(alan)} onChange={(ev) => yaz(i, alan, ev.target.value)} {...metinOlaylari(i, alan)} />
    );
  const ekip = meta.ekip ?? [];

  if (e.tur === 'eposta') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <fieldset className="sm:col-span-2">
          <legend className="mb-1 text-xs font-medium text-muted-foreground">{t('otomasyon.eposta.nitelik')} *</legend>
          <div className="flex flex-wrap gap-3 text-sm">
            {(['bilgilendirme', 'pazarlama'] as const).map((n) => (
              <label key={n} className="inline-flex items-center gap-1.5">
                <input type="radio" name={`nitelik-${i}`} className="accent-purple-500" checked={e.nitelik === n} onChange={() => yaz(i, 'nitelik', n)} data-oto-nitelik={n} />
                {t(`otomasyon.eposta.${n}`)}
              </label>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">{t('otomasyon.eposta.nitelikIpucu')}</p>
        </fieldset>
        <Etiket ad={t('otomasyon.eposta.alici')}>
          <select className={SECIM} value={s('alici')} onChange={(ev) => yaz(i, 'alici', ev.target.value)}>
            {['kisi', 'hesap', 'sabit'].map((a) => (
              <option key={a} value={a}>
                {t(`otomasyon.eposta.alici_${a}`)}
              </option>
            ))}
          </select>
        </Etiket>
        {e.alici === 'sabit' ? (
          <Etiket ad={t('otomasyon.eposta.adres')}>
            <input className={ALAN} type="email" dir="ltr" maxLength={254} value={s('adres')} onChange={(ev) => yaz(i, 'adres', ev.target.value)} />
          </Etiket>
        ) : (
          <span className="hidden sm:block" />
        )}
        <Etiket ad={t('otomasyon.eposta.konu')} tam>
          {metin('konu', 200)}
        </Etiket>
        <Etiket ad={t('otomasyon.eposta.govde')} tam>
          {metin('govde', 5000, true)}
        </Etiket>
      </div>
    );
  }
  if (e.tur === 'bildirim') {
    const alicilar = ajans ? ['yoneticiler', 'hesap', 'sorumlu', 'sorumlu_yonetici', 'ekip_uyesi'] : ['hesap'];
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Etiket ad={t('otomasyon.bildirim.alici')}>
          <select className={SECIM} value={s('alici')} onChange={(ev) => yaz(i, 'alici', ev.target.value)}>
            {alicilar.map((a) => (
              <option key={a} value={a}>
                {t(`otomasyon.bildirim.alici_${a}`)}
              </option>
            ))}
          </select>
        </Etiket>
        {e.alici === 'ekip_uyesi' ? (
          <Etiket ad={t('otomasyon.bildirim.uye')}>
            <select className={SECIM} value={s('adres')} onChange={(ev) => yaz(i, 'adres', ev.target.value)}>
              <option value="">—</option>
              {ekip.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Etiket>
        ) : (
          <span className="hidden sm:block" />
        )}
        <Etiket ad={t('otomasyon.bildirim.baslik')} tam>
          {metin('baslik', 200)}
        </Etiket>
        <Etiket ad={t('otomasyon.bildirim.govde')} tam>
          {metin('govde', 2000, true)}
        </Etiket>
      </div>
    );
  }
  if (e.tur === 'gorev') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Etiket ad={t('otomasyon.gorev.proje')}>
          <select
            className={SECIM}
            value={String(e.proje ?? '')}
            onChange={(ev) => yaz(i, 'proje', ev.target.value === 'olay' || ev.target.value === '' ? ev.target.value : Number(ev.target.value))}
          >
            <option value="">—</option>
            {projeVar && <option value="olay">{t('otomasyon.gorev.olaydakiProje')}</option>}
            {meta.projeler.map((p) => (
              <option key={p.id} value={p.id}>
                #{p.id} {p.baslik}
                {ajans && p.hesap ? ` (${p.hesap})` : ''}
              </option>
            ))}
          </select>
        </Etiket>
        <Etiket ad={t('otomasyon.gorev.oncelik')}>
          <select className={SECIM} value={s('oncelik') || 'normal'} onChange={(ev) => yaz(i, 'oncelik', ev.target.value)}>
            {meta.oncelikler.map((o) => (
              <option key={o} value={o}>
                {t(`otomasyon.oncelik.${o}`)}
              </option>
            ))}
          </select>
        </Etiket>
        <Etiket ad={t('otomasyon.gorev.baslik')} tam>
          {metin('baslik', 200)}
        </Etiket>
        <Etiket ad={t('otomasyon.gorev.aciklama')} tam>
          {metin('aciklama', 2000, true)}
        </Etiket>
        <Etiket ad={t('otomasyon.gorev.sonTarih')} ipucu={t('otomasyon.gorev.sonTarihIpucu')}>
          <input
            className={ALAN}
            type="number"
            min={0}
            max={365}
            value={e.son_tarih_gun === null || e.son_tarih_gun === undefined ? '' : String(e.son_tarih_gun)}
            onChange={(ev) => yaz(i, 'son_tarih_gun', ev.target.value === '' ? null : Number(ev.target.value))}
          />
        </Etiket>
        {ajans && (
          <Etiket ad={t('otomasyon.gorev.atanan')}>
            <select className={SECIM} value={s('atanan')} onChange={(ev) => yaz(i, 'atanan', ev.target.value || null)}>
              <option value="">{t('otomasyon.gorev.atanmamis')}</option>
              {ekip.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Etiket>
        )}
        {ajans && (
          <label className="inline-flex items-center gap-2 text-sm sm:col-span-2">
            <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={e.musteriye_gorunur === true} onChange={(ev) => yaz(i, 'musteriye_gorunur', ev.target.checked)} />
            {t('otomasyon.gorev.musteriyeGorunur')}
          </label>
        )}
      </div>
    );
  }
  if (e.tur === 'crm_asama') {
    return (
      <Etiket ad={t('otomasyon.crm.asama')}>
        <select className={SECIM} value={s('asama')} onChange={(ev) => yaz(i, 'asama', ev.target.value)}>
          <option value="">—</option>
          {(meta.crm_asamalari ?? []).map((a) => (
            <option key={a.anahtar} value={a.anahtar}>
              {a.ceviriler?.[i18n.language]?.ad || a.ad || a.anahtar}
            </option>
          ))}
        </select>
      </Etiket>
    );
  }
  if (e.tur === 'crm_etiket') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Etiket ad={t('otomasyon.crm.islem')}>
          <select className={SECIM} value={s('islem') || 'ekle'} onChange={(ev) => yaz(i, 'islem', ev.target.value)}>
            <option value="ekle">{t('otomasyon.crm.ekle')}</option>
            <option value="kaldir">{t('otomasyon.crm.kaldir')}</option>
          </select>
        </Etiket>
        <Etiket ad={t('otomasyon.crm.etiket')}>
          <input className={ALAN} maxLength={40} value={s('etiket')} onChange={(ev) => yaz(i, 'etiket', ev.target.value)} />
        </Etiket>
      </div>
    );
  }
  if (e.tur === 'crm_sahip') {
    return (
      <Etiket ad={t('otomasyon.crm.sorumlu')}>
        <select className={SECIM} value={s('sorumlu')} onChange={(ev) => yaz(i, 'sorumlu', ev.target.value)}>
          <option value="">—</option>
          {ekip.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </Etiket>
    );
  }
  if (e.tur === 'crm_aktivite') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Etiket ad={t('otomasyon.crm.aktiviteTuru')}>
          <select className={SECIM} value={s('aktivite_tur') || 'not'} onChange={(ev) => yaz(i, 'aktivite_tur', ev.target.value)}>
            {meta.aktivite_turleri.map((a) => (
              <option key={a} value={a}>
                {t(`otomasyon.crm.aktivite_${a}`)}
              </option>
            ))}
          </select>
        </Etiket>
        <span className="hidden sm:block" />
        <Etiket ad={t('otomasyon.crm.metin')} tam>
          {metin('metin', 2000, true)}
        </Etiket>
      </div>
    );
  }
  if (e.tur === 'destek') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Etiket ad={t('otomasyon.destek.oncelik')}>
          <select className={SECIM} value={s('oncelik')} onChange={(ev) => yaz(i, 'oncelik', ev.target.value || null)}>
            <option value="">{t('otomasyon.destek.degistirme')}</option>
            {meta.oncelikler.map((o) => (
              <option key={o} value={o}>
                {t(`otomasyon.oncelik.${o}`)}
              </option>
            ))}
          </select>
        </Etiket>
        <Etiket ad={t('otomasyon.destek.etiket')}>
          <input className={ALAN} maxLength={40} value={s('etiket')} onChange={(ev) => yaz(i, 'etiket', ev.target.value)} />
        </Etiket>
      </div>
    );
  }
  if (e.tur === 'webhook') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <Etiket ad={t('otomasyon.webhook.uc')} ipucu={meta.webhook_uclari.length ? undefined : t('otomasyon.webhook.ucYok')}>
          <select className={SECIM} value={String(e.uc_id ?? '')} onChange={(ev) => yaz(i, 'uc_id', ev.target.value ? Number(ev.target.value) : null)}>
            <option value="">—</option>
            {meta.webhook_uclari.map((u) => (
              <option key={u.id} value={u.id}>
                {u.aciklama || u.url}
                {u.aktif ? '' : ` (${t('otomasyon.kural.pasif')})`}
              </option>
            ))}
          </select>
        </Etiket>
        <Etiket ad={t('otomasyon.webhook.etiket')} ipucu={t('otomasyon.webhook.etiketIpucu')}>
          <input className={ALAN} dir="ltr" maxLength={40} value={s('etiket')} onChange={(ev) => yaz(i, 'etiket', ev.target.value)} />
        </Etiket>
      </div>
    );
  }
  // bekle
  return (
    <div className="grid grid-cols-2 gap-3 sm:max-w-sm">
      <Etiket ad={t('otomasyon.bekle.miktar')}>
        <input className={ALAN} type="number" min={1} value={String(e.miktar ?? 1)} onChange={(ev) => yaz(i, 'miktar', Number(ev.target.value))} />
      </Etiket>
      <Etiket ad={t('otomasyon.bekle.birim')}>
        <select className={SECIM} value={s('birim') || 'saat'} onChange={(ev) => yaz(i, 'birim', ev.target.value)}>
          {meta.bekleme_birimleri.map((b) => (
            <option key={b} value={b}>
              {t(`otomasyon.bekle.${b}`)}
            </option>
          ))}
        </select>
      </Etiket>
      <p className="col-span-2 text-[11px] text-muted-foreground">{t('otomasyon.bekle.ipucu')}</p>
    </div>
  );
}
