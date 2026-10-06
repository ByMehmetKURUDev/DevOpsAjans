import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, Save, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Bos, DIS_DUGME, GIRDI, KanalIkonu, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor } from '@/components/icerikStudyosu/ortak';
import { hataMetni, type Meta, type Sablon, type SablonGirdisi, type StudyoApi } from '@/lib/icerikStudyosu';

/**
 * Faz 5I — Şablonlar: 13 hazır şablon (adları 7 dilde) + kullanıcının kendi şablonu. Kendi
 * şablonu: alanlar (anahtar, etiket, kısa/uzun, zorunlu) ve `{{anahtar}}` yer tutuculu istem.
 * Kullanıcı girdisi istemde VERİ olarak yerleşir (sunucu kaçışlıyor; tek geçiş).
 */

interface Form {
  ad: string;
  aciklama: string;
  kanal: string;
  alanlar: SablonGirdisi[];
  istem: string;
}

const BOS_FORM: Form = { ad: '', aciklama: '', kanal: '', alanlar: [{ anahtar: 'konu', etiket: '', tur: 'uzun', zorunlu: true }], istem: '' };

export default function Sablonlar({ api, meta }: { api: StudyoApi; meta: Meta }) {
  const { t } = useTranslation();
  const [veri, setVeri] = useState<{ hazir: Sablon[]; ozel: Sablon[] } | null>(null);
  const [secili, setSecili] = useState<Sablon | 'yeni' | null>(null);
  const [form, setForm] = useState<Form>(BOS_FORM);
  const [calisiyor, setCalisiyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setVeri(await api.sablonlar());
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const sec = (s: Sablon | 'yeni') => {
    setSecili(s);
    setForm(
      s === 'yeni'
        ? { ...BOS_FORM, istem: t('icerikStudyosu.sablonlar.ornekIstem') }
        : { ad: s.ad || '', aciklama: s.aciklama || '', kanal: s.kanal || '', alanlar: s.girdiler.map((g) => ({ ...g, etiket: g.etiket || '' })), istem: s.istem || '' }
    );
  };

  const kaydet = async () => {
    setCalisiyor(true);
    try {
      const govde = { ad: form.ad, aciklama: form.aciklama, kanal: form.kanal || null, alanlar: form.alanlar, istem: form.istem };
      const s = secili && secili !== 'yeni' && secili.id ? await api.sablonGuncelle(secili.id, govde) : await api.sablonEkle(govde);
      toast.success(t('icerikStudyosu.form.kaydedildi'));
      setSecili(s);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setCalisiyor(false);
    }
  };

  const sil = async () => {
    if (!secili || secili === 'yeni' || !secili.id || !window.confirm(t('icerikStudyosu.sablonlar.silOnay', { ad: secili.ad }))) return;
    try {
      await api.sablonSil(secili.id);
      setSecili(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (!veri) return <Yukleniyor />;
  return (
    <div className="space-y-6" data-testid="is-sablonlar">
      <section>
        <h3 className="mb-2 text-sm font-semibold">{t('icerikStudyosu.sablonlar.hazir', { sayi: veri.hazir.length })}</h3>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {veri.hazir.map((s) => (
            <article key={s.kod} className={`${KART} p-3`} data-sablon={s.kod}>
              <p className="font-medium">{t(`icerikStudyosu.sablon.${s.kod}.ad`)}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{t(`icerikStudyosu.sablon.${s.kod}.aciklama`)}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1">
                {s.kanallar.map((k) => (
                  <KanalIkonu key={k} kanal={k} className="h-3.5 w-3.5 text-muted-foreground" />
                ))}
                {s.ciktilar.filter((c) => c.sinir).slice(0, 3).map((c) => (
                  <Rozet key={c.anahtar}>{t(`icerikStudyosu.cikti.${c.anahtar}`)} ≤ {c.sinir}</Rozet>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t('icerikStudyosu.sablonlar.ozel')}</h3>
          <Button type="button" size="sm" className="w-full gap-1.5" onClick={() => sec('yeni')} data-testid="is-sablon-yeni">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('icerikStudyosu.sablonlar.yeni')}
          </Button>
          {veri.ozel.length === 0 && <Bos>{t('icerikStudyosu.sablonlar.bos')}</Bos>}
          {veri.ozel.map((s) => (
            <button key={s.kod} type="button" onClick={() => sec(s)} className={`${KART} block w-full p-3 text-start hover:bg-white/[0.06]`}>
              <span className="block truncate font-medium">{s.ad}</span>
              <span className="block truncate text-xs text-muted-foreground">{s.aciklama}</span>
            </button>
          ))}
        </div>
        {secili ? (
          <div className={`${KART} space-y-3 p-4`} data-testid="is-sablon-form">
            <div className="grid gap-3 sm:grid-cols-2">
              <Alan etiket={`${t('icerikStudyosu.sablonlar.ad')} *`}>
                <input className={GIRDI} value={form.ad} onChange={(e) => setForm({ ...form, ad: e.target.value })} maxLength={120} />
              </Alan>
              <Alan etiket={t('icerikStudyosu.sablonlar.kanal')}>
                <select className={SECIM} value={form.kanal} onChange={(e) => setForm({ ...form, kanal: e.target.value })}>
                  <option value="">{t('icerikStudyosu.sablonlar.genel')}</option>
                  {meta.kanallar.map((k) => (
                    <option key={k} value={k}>{t(`icerikOnay.kanal.${k}`)}</option>
                  ))}
                </select>
              </Alan>
            </div>
            <Alan etiket={t('icerikStudyosu.sablonlar.aciklama')}>
              <input className={GIRDI} value={form.aciklama} onChange={(e) => setForm({ ...form, aciklama: e.target.value })} maxLength={500} />
            </Alan>
            <div>
              <span className="mb-1 block text-sm font-medium">{t('icerikStudyosu.sablonlar.alanlar')}</span>
              <div className="space-y-2">
                {form.alanlar.map((a, i) => (
                  <div key={i} className="grid grid-cols-2 gap-2 sm:grid-cols-[8rem_minmax(0,1fr)_7rem_auto_auto] sm:items-center">
                    <input className={GIRDI} value={a.anahtar} dir="ltr" placeholder="anahtar" aria-label={t('icerikStudyosu.sablonlar.anahtar')}
                      onChange={(e) => setForm({ ...form, alanlar: form.alanlar.map((x, k) => (k === i ? { ...x, anahtar: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') } : x)) })} />
                    <input className={GIRDI} value={a.etiket || ''} placeholder={t('icerikStudyosu.sablonlar.etiket')} aria-label={t('icerikStudyosu.sablonlar.etiket')}
                      onChange={(e) => setForm({ ...form, alanlar: form.alanlar.map((x, k) => (k === i ? { ...x, etiket: e.target.value } : x)) })} />
                    <select className={SECIM} value={a.tur} aria-label={t('icerikStudyosu.sablonlar.tur')}
                      onChange={(e) => setForm({ ...form, alanlar: form.alanlar.map((x, k) => (k === i ? { ...x, tur: e.target.value as 'metin' | 'uzun' } : x)) })}>
                      <option value="metin">{t('icerikStudyosu.sablonlar.kisa')}</option>
                      <option value="uzun">{t('icerikStudyosu.sablonlar.uzun')}</option>
                    </select>
                    <label className="flex items-center gap-1 text-xs">
                      <input type="checkbox" className="h-4 w-4 accent-fuchsia-500" checked={a.zorunlu}
                        onChange={(e) => setForm({ ...form, alanlar: form.alanlar.map((x, k) => (k === i ? { ...x, zorunlu: e.target.checked } : x)) })} />
                      {t('icerikStudyosu.sablonlar.zorunlu')}
                    </label>
                    <button type="button" className="justify-self-start rounded p-1.5 text-muted-foreground hover:bg-white/5" aria-label={t('icerikStudyosu.sil')}
                      onClick={() => setForm({ ...form, alanlar: form.alanlar.filter((_, k) => k !== i) })}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
              {form.alanlar.length < 12 && (
                <Button type="button" size="sm" variant="outline" className={DIS_DUGME + ' mt-2'}
                  onClick={() => setForm({ ...form, alanlar: [...form.alanlar, { anahtar: `alan_${form.alanlar.length + 1}`, etiket: '', tur: 'metin', zorunlu: false }] })}>
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('icerikStudyosu.sablonlar.alanEkle')}
                </Button>
              )}
            </div>
            <Alan etiket={`${t('icerikStudyosu.sablonlar.istem')} *`} ipucu={t('icerikStudyosu.sablonlar.istemIpucu', { ornek: form.alanlar.map((a) => `{{${a.anahtar}}}`).join(' ') })}>
              <textarea className={METIN_ALANI + ' min-h-[140px]'} value={form.istem} onChange={(e) => setForm({ ...form, istem: e.target.value })} maxLength={6000} dir="auto" />
            </Alan>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={kaydet} disabled={calisiyor || !form.ad.trim() || !form.istem.trim()} className="gap-1.5" data-testid="is-sablon-kaydet">
                {calisiyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" aria-hidden="true" />}
                {t('icerikStudyosu.kaydet')}
              </Button>
              {secili !== 'yeni' && (
                <Button type="button" variant="outline" className={DIS_DUGME + ' text-rose-200 sm:ms-auto'} onClick={sil}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  {t('icerikStudyosu.sil')}
                </Button>
              )}
            </div>
          </div>
        ) : (
          <Bos>{t('icerikStudyosu.sablonlar.sec')}</Bos>
        )}
      </section>
    </div>
  );
}
