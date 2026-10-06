import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, Save, Sparkles, Trash2, Wand2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, satirlar } from '@/components/icerikStudyosu/ortak';
import { hataMetni, type Marka, type Meta, type Politika, type SesOnerisi, type StudyoApi } from '@/lib/icerikStudyosu';

/**
 * Faz 5I — Marka sesi profilleri (hesap başına birden çok): sektör, hedef kitle, ton ölçekleri,
 * yazım kuralları, yasaklı kelimeler, en çok 5 örnek metin, anahtar mesajlar, emoji/hashtag
 * politikası, diller. "Örneklerden marka sesini çıkar" yapay zekâdan ÖNERİ getirir; kullanıcı
 * "Uygula" deyip kaydedene kadar profil değişmez.
 */

const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];

interface Form {
  ad: string;
  sektor: string;
  hedef_kitle: string;
  ton: Record<string, number>;
  yapilacaklar: string;
  yapilmayacaklar: string;
  yasakli_kelimeler: string;
  ornek_metinler: string[];
  anahtar_mesajlar: string;
  emoji_politikasi: Politika;
  hashtag_politikasi: Politika;
  hashtagler: string;
  diller: string[];
}

function formdan(m: Marka | null, olcekler: string[]): Form {
  return {
    ad: m?.ad ?? '',
    sektor: m?.sektor ?? '',
    hedef_kitle: m?.hedef_kitle ?? '',
    ton: Object.fromEntries(olcekler.map((k) => [k, m?.ton?.[k] ?? 50])),
    yapilacaklar: (m?.yapilacaklar ?? []).join('\n'),
    yapilmayacaklar: (m?.yapilmayacaklar ?? []).join('\n'),
    yasakli_kelimeler: (m?.yasakli_kelimeler ?? []).join(', '),
    ornek_metinler: m?.ornek_metinler?.length ? [...m.ornek_metinler] : [''],
    anahtar_mesajlar: (m?.anahtar_mesajlar ?? []).join('\n'),
    emoji_politikasi: m?.emoji_politikasi ?? 'az',
    hashtag_politikasi: m?.hashtag_politikasi ?? 'az',
    hashtagler: (m?.hashtagler ?? []).join(' '),
    diller: m?.diller ?? ['tr'],
  };
}

export default function MarkaSesi({ api, meta }: { api: StudyoApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const [liste, setListe] = useState<Marka[] | null>(null);
  const [sinir, setSinir] = useState<number | null>(null);
  const [secili, setSecili] = useState<Marka | 'yeni' | null>(null);
  const [form, setForm] = useState<Form>(() => formdan(null, meta.ton_olcekleri));
  const [calisiyor, setCalisiyor] = useState<string | null>(null);
  const [oneri, setOneri] = useState<SesOnerisi | null>(null);

  const yukle = useCallback(async () => {
    try {
      const r = await api.markalar();
      setListe(r.items);
      setSinir(r.sinir);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const sec = (m: Marka | 'yeni') => {
    setSecili(m);
    setOneri(null);
    setForm(formdan(m === 'yeni' ? null : m, meta.ton_olcekleri));
  };

  const yaz = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));

  const govde = () => ({
    ad: form.ad,
    sektor: form.sektor,
    hedef_kitle: form.hedef_kitle,
    ton: form.ton,
    yapilacaklar: satirlar(form.yapilacaklar),
    yapilmayacaklar: satirlar(form.yapilmayacaklar),
    yasakli_kelimeler: form.yasakli_kelimeler.split(',').map((x) => x.trim()).filter(Boolean),
    ornek_metinler: form.ornek_metinler.map((x) => x.trim()).filter(Boolean),
    anahtar_mesajlar: satirlar(form.anahtar_mesajlar),
    emoji_politikasi: form.emoji_politikasi,
    hashtag_politikasi: form.hashtag_politikasi,
    hashtagler: form.hashtagler.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean),
    diller: form.diller,
  });

  const kaydet = async () => {
    if (!form.ad.trim()) {
      toast.error(t('icerikStudyosu.marka.adGerekli'));
      return;
    }
    setCalisiyor('kaydet');
    try {
      const m = secili && secili !== 'yeni' ? await api.markaGuncelle(secili.id, govde()) : await api.markaEkle(govde());
      toast.success(t('icerikStudyosu.form.kaydedildi'));
      setSecili(m);
      setForm(formdan(m, meta.ton_olcekleri));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const sil = async () => {
    if (!secili || secili === 'yeni' || !window.confirm(t('icerikStudyosu.marka.silOnay', { ad: secili.ad }))) return;
    setCalisiyor('sil');
    try {
      await api.markaSil(secili.id);
      setSecili(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const sesCikar = async () => {
    if (!secili || secili === 'yeni') return;
    setCalisiyor('ses');
    try {
      // Örnek metinler kayıtlı olmalı (sunucu kayıttan okuyor): önce kaydet.
      await api.markaGuncelle(secili.id, { ornek_metinler: form.ornek_metinler.map((x) => x.trim()).filter(Boolean) });
      const y = await api.sesCikar(secili.id, ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'].includes(i18n.language) ? i18n.language : 'tr');
      setOneri(y.oneri);
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(null);
    }
  };

  const oneriyiUygula = () => {
    if (!oneri) return;
    setForm((f) => ({
      ...f,
      ton: { ...f.ton, ...oneri.ton },
      yapilacaklar: oneri.yapilacaklar.length ? oneri.yapilacaklar.join('\n') : f.yapilacaklar,
      yapilmayacaklar: oneri.yapilmayacaklar.length ? oneri.yapilmayacaklar.join('\n') : f.yapilmayacaklar,
      anahtar_mesajlar: oneri.anahtar_mesajlar.length ? oneri.anahtar_mesajlar.join('\n') : f.anahtar_mesajlar,
      emoji_politikasi: oneri.emoji_politikasi,
      hashtag_politikasi: oneri.hashtag_politikasi,
    }));
    setOneri(null);
    toast.success(t('icerikStudyosu.marka.oneriUygulandi'));
  };

  if (!liste) return <Yukleniyor />;
  const sinirDolu = !meta.yonetici && sinir !== null && liste.length >= sinir;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]" data-testid="is-marka">
      <div className="space-y-2">
        <Button type="button" size="sm" className="w-full gap-1.5" onClick={() => sec('yeni')} disabled={sinirDolu} data-testid="is-marka-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('icerikStudyosu.marka.yeni')}
        </Button>
        {sinirDolu && <p className="text-[11px] text-amber-200">{t('icerikStudyosu.marka.sinirDolu', { sinir })}</p>}
        {liste.length === 0 && <Bos>{t('icerikStudyosu.marka.bos')}</Bos>}
        {liste.map((m) => (
          <button key={m.id} type="button" onClick={() => sec(m)} data-marka={m.ad}
            className={`${KART} block w-full p-3 text-start hover:bg-white/[0.06] ${secili !== 'yeni' && secili?.id === m.id ? 'ring-1 ring-fuchsia-400/50' : ''}`}>
            <span className="block truncate font-medium">{m.ad}</span>
            <span className="block truncate text-xs text-muted-foreground">{[m.sektor, m.diller.join(', ')].filter(Boolean).join(' · ')}</span>
          </button>
        ))}
      </div>

      {!secili ? (
        <Bos>{t('icerikStudyosu.marka.sec')}</Bos>
      ) : (
        <div className={`${KART} space-y-4 p-4`} data-testid="is-marka-form">
          <div className="grid gap-3 sm:grid-cols-2">
            <Alan etiket={`${t('icerikStudyosu.marka.ad')} *`}>
              <input className={GIRDI} value={form.ad} onChange={(e) => yaz('ad', e.target.value)} maxLength={120} data-testid="is-marka-ad" />
            </Alan>
            <Alan etiket={t('icerikStudyosu.marka.sektor')}>
              <input className={GIRDI} value={form.sektor} onChange={(e) => yaz('sektor', e.target.value)} maxLength={120} data-testid="is-marka-sektor" />
            </Alan>
          </div>
          <Alan etiket={t('icerikStudyosu.marka.hedefKitle')}>
            <textarea className={METIN_ALANI + ' min-h-[64px]'} value={form.hedef_kitle} onChange={(e) => yaz('hedef_kitle', e.target.value)} maxLength={1000} />
          </Alan>

          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">{t('icerikStudyosu.marka.ton')}</legend>
            {meta.ton_olcekleri.map((k) => (
              <div key={k} className="grid grid-cols-[minmax(0,6rem)_minmax(0,1fr)_minmax(0,6rem)] items-center gap-2 text-xs">
                <span className="truncate text-end text-muted-foreground">{t(`icerikStudyosu.ton.${k}.sol`)}</span>
                <input type="range" min={0} max={100} step={5} value={form.ton[k] ?? 50} onChange={(e) => yaz('ton', { ...form.ton, [k]: Number(e.target.value) })}
                  aria-label={`${t(`icerikStudyosu.ton.${k}.sol`)} ↔ ${t(`icerikStudyosu.ton.${k}.sag`)}`} className="w-full accent-fuchsia-500" data-ton={k} />
                <span className="truncate text-muted-foreground">{t(`icerikStudyosu.ton.${k}.sag`)}</span>
              </div>
            ))}
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <Alan etiket={t('icerikStudyosu.marka.yapilacaklar')} ipucu={t('icerikStudyosu.marka.satirIpucu')}>
              <textarea className={METIN_ALANI} value={form.yapilacaklar} onChange={(e) => yaz('yapilacaklar', e.target.value)} />
            </Alan>
            <Alan etiket={t('icerikStudyosu.marka.yapilmayacaklar')} ipucu={t('icerikStudyosu.marka.satirIpucu')}>
              <textarea className={METIN_ALANI} value={form.yapilmayacaklar} onChange={(e) => yaz('yapilmayacaklar', e.target.value)} />
            </Alan>
            <Alan etiket={t('icerikStudyosu.marka.yasakli')} ipucu={t('icerikStudyosu.marka.virgulIpucu')}>
              <input className={GIRDI} value={form.yasakli_kelimeler} onChange={(e) => yaz('yasakli_kelimeler', e.target.value)} data-testid="is-marka-yasakli" />
            </Alan>
            <Alan etiket={t('icerikStudyosu.marka.hashtagler')} ipucu={t('icerikStudyosu.marka.hashtagIpucu')}>
              <input className={GIRDI} value={form.hashtagler} onChange={(e) => yaz('hashtagler', e.target.value)} />
            </Alan>
            <Alan etiket={t('icerikStudyosu.marka.emoji')}>
              <select className={SECIM} value={form.emoji_politikasi} onChange={(e) => yaz('emoji_politikasi', e.target.value as Politika)}>
                {meta.politikalar.map((p) => (
                  <option key={p} value={p}>{t(`icerikStudyosu.politika.${p}`)}</option>
                ))}
              </select>
            </Alan>
            <Alan etiket={t('icerikStudyosu.marka.hashtagPolitikasi')}>
              <select className={SECIM} value={form.hashtag_politikasi} onChange={(e) => yaz('hashtag_politikasi', e.target.value as Politika)}>
                {meta.politikalar.map((p) => (
                  <option key={p} value={p}>{t(`icerikStudyosu.politika.${p}`)}</option>
                ))}
              </select>
            </Alan>
          </div>
          <Alan etiket={t('icerikStudyosu.marka.anahtarMesajlar')} ipucu={t('icerikStudyosu.marka.satirIpucu')}>
            <textarea className={METIN_ALANI + ' min-h-[64px]'} value={form.anahtar_mesajlar} onChange={(e) => yaz('anahtar_mesajlar', e.target.value)} />
          </Alan>
          <div>
            <span className="mb-1 block text-sm font-medium">{t('icerikStudyosu.marka.diller')}</span>
            <div className="flex flex-wrap gap-2">
              {DILLER.map((d) => (
                <label key={d} className="flex items-center gap-1 text-xs">
                  <input type="checkbox" className="h-4 w-4 accent-fuchsia-500" checked={form.diller.includes(d)}
                    onChange={(e) => yaz('diller', e.target.checked ? [...form.diller, d] : form.diller.filter((x) => x !== d))} />
                  {t(`icerikStudyosu.dil.${d}`)}
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-white/10 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{t('icerikStudyosu.marka.ornekler')}</span>
              <Rozet>{form.ornek_metinler.filter((x) => x.trim()).length}/5</Rozet>
            </div>
            <div className="space-y-2">
              {form.ornek_metinler.map((o, i) => (
                <div key={i} className="flex gap-2">
                  <textarea className={METIN_ALANI + ' min-h-[64px]'} value={o} dir="auto" maxLength={2000} data-ornek={i}
                    onChange={(e) => yaz('ornek_metinler', form.ornek_metinler.map((x, k) => (k === i ? e.target.value : x)))} />
                  <button type="button" className="self-start rounded p-1.5 text-muted-foreground hover:bg-white/5" aria-label={t('icerikStudyosu.sil')}
                    onClick={() => yaz('ornek_metinler', form.ornek_metinler.filter((_, k) => k !== i).length ? form.ornek_metinler.filter((_, k) => k !== i) : [''])}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {form.ornek_metinler.length < 5 && (
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => yaz('ornek_metinler', [...form.ornek_metinler, ''])}>
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('icerikStudyosu.marka.ornekEkle')}
                </Button>
              )}
              {secili !== 'yeni' && (
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={sesCikar}
                  disabled={!meta.ai_hazir || !!calisiyor || !form.ornek_metinler.some((x) => x.trim())}
                  title={!meta.ai_hazir ? t('icerikStudyosu.uyariAiKapali') : !form.ornek_metinler.some((x) => x.trim()) ? t('icerikStudyosu.hata.ornek_gerekli') : undefined}
                  data-testid="is-marka-ses-cikar">
                  {calisiyor === 'ses' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />}
                  {t('icerikStudyosu.marka.sesCikar')}
                </Button>
              )}
            </div>
            {oneri && (
              <div className="mt-3 rounded-lg border border-fuchsia-400/30 bg-fuchsia-500/10 p-3 text-sm" data-testid="is-marka-oneri">
                <p className="mb-1 flex items-center gap-1.5 font-medium">
                  <Sparkles className="h-4 w-4 text-fuchsia-300" aria-hidden="true" />
                  {t('icerikStudyosu.marka.oneri')}
                </p>
                <p className="text-xs text-white/90">{oneri.ozet}</p>
                <ul className="mt-1 list-disc ps-5 text-xs text-muted-foreground">
                  {oneri.yapilacaklar.map((x) => <li key={x}>{x}</li>)}
                </ul>
                <div className="mt-2 flex gap-2">
                  <Button type="button" size="sm" onClick={oneriyiUygula} data-testid="is-marka-oneri-uygula">{t('icerikStudyosu.marka.uygula')}</Button>
                  <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => setOneri(null)}>{t('icerikOnay.vazgec')}</Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={kaydet} disabled={!!calisiyor} className="gap-1.5" data-testid="is-marka-kaydet">
              {calisiyor === 'kaydet' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" aria-hidden="true" />}
              {t('icerikStudyosu.kaydet')}
            </Button>
            {secili !== 'yeni' && (
              <Button type="button" variant="outline" className={DIS_DUGME + ' text-rose-200 sm:ms-auto'} onClick={sil} disabled={!!calisiyor}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {t('icerikStudyosu.sil')}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
