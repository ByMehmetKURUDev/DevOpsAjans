import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Check, Copy, ExternalLink, Eye, EyeOff, Loader2, Pencil, Plus, Save, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  asamaAdi,
  formGuncelle,
  formListesi,
  formOlustur,
  formSil,
  gommeKodu,
  hataMetni,
  tarihGoster,
  type Asama,
  type CrmFormu,
  type FormAlani,
  type FormListesi,
} from '@/lib/crm';
import { AlanEtiketi, Bekle, METIN_ALANI, SECIM } from './ortak';

const ALANLAR: FormAlani[] = ['ad', 'email', 'telefon', 'firma', 'mesaj', 'butce'];

type Taslak = {
  ad: string;
  baslik: string;
  alanlar: Record<FormAlani, { acik: boolean; zorunlu: boolean }>;
  varsayilan_asama: string;
  varsayilan_etiketler: string;
  tesekkur_metni: string;
  yonlendirme_adresi: string;
  izinli_alanlar: string;
  kvkk_metni: string;
  aydinlatma_baglantisi: string;
  aktif: boolean;
};

const BOS_ALANLAR: Taslak['alanlar'] = {
  ad: { acik: true, zorunlu: true },
  email: { acik: true, zorunlu: true },
  telefon: { acik: true, zorunlu: false },
  firma: { acik: false, zorunlu: false },
  mesaj: { acik: true, zorunlu: false },
  butce: { acik: false, zorunlu: false },
};

function taslakYap(f: CrmFormu | null, kvkkVarsayilan: string): Taslak {
  return {
    ad: f?.ad ?? '',
    baslik: f?.baslik ?? '',
    alanlar: f?.alanlar ?? BOS_ALANLAR,
    varsayilan_asama: f?.varsayilan_asama ?? '',
    varsayilan_etiketler: (f?.varsayilan_etiketler ?? []).join(', '),
    tesekkur_metni: f?.tesekkur_metni ?? '',
    yonlendirme_adresi: f?.yonlendirme_adresi ?? '',
    izinli_alanlar: (f?.izinli_alanlar ?? []).join('\n'),
    kvkk_metni: f?.kvkk_metni ?? kvkkVarsayilan,
    aydinlatma_baglantisi: f?.aydinlatma_baglantisi ?? '',
    aktif: f?.aktif ?? true,
  };
}

/**
 * Gömülebilir formlar: oluştur/düzenle (alanlar aç-kapa, zorunluluk, varsayılan
 * aşama/etiket, teşekkür metni, https yönlendirme, izinli alan adları, KVKK
 * metni + aydınlatma bağlantısı), gömme kodunu kopyala, doğrudan bağlantı ve
 * önizleme (aynı sitedeki /form/<anahtar> sayfası bir çerçevede).
 */
export default function CrmFormlari({ asamalar }: { asamalar: Asama[] }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<FormListesi | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<CrmFormu | 'yeni' | null>(null);
  const [onizleme, setOnizleme] = useState<number | null>(null);
  const [kopyalanan, setKopyalanan] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setVeri(await formListesi());
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (!veri) return <Bekle />;
  // Gömme kodu panelin açık olduğu kökene göre (canlıda mehmetkuru.dev).
  const taban = typeof window !== 'undefined' ? window.location.origin : veri.site_adresi;

  const kopyala = async (f: CrmFormu) => {
    try {
      await navigator.clipboard.writeText(gommeKodu(taban, f.genel_anahtar));
      setKopyalanan(f.id);
      toast.success(t('crm.form.kopyalandi'));
      window.setTimeout(() => setKopyalanan((x) => (x === f.id ? null : x)), 2000);
    } catch {
      toast.error(t('crm.form.kopyalanamadi'));
    }
  };

  const sil = async (f: CrmFormu) => {
    if (!window.confirm(t('crm.form.silOnay', { ad: f.ad }))) return;
    try {
      await formSil(f.id);
      toast.success(t('crm.form.silindi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-4" data-testid="crm-formlar">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">{t('crm.form.aciklama')}</p>
        <Button size="sm" className="gap-1" onClick={() => setDuzenlenen('yeni')} data-testid="crm-form-yeni">
          <Plus className="h-4 w-4" /> {t('crm.form.yeni')}
        </Button>
      </div>

      {veri.formlar.length === 0 && (
        <p className="rounded-2xl border border-dashed border-white/10 p-6 text-center text-sm text-muted-foreground">{t('crm.form.bos')}</p>
      )}

      <ul className="space-y-3">
        {veri.formlar.map((f) => (
          <li key={f.id} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-crm-form={f.genel_anahtar}>
            <div className="flex flex-wrap items-start gap-3">
              <div className="min-w-0 flex-1">
                <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                  {f.ad}
                  <span className={`rounded px-1.5 py-0.5 text-[11px] ${f.aktif ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/10 text-muted-foreground'}`}>
                    {f.aktif ? t('crm.form.aktif') : t('crm.form.pasif')}
                  </span>
                </h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {t('crm.form.istatistik', { sayi: f.gonderim_sayisi, surum: f.kvkk_surum })}
                  {f.son_gonderim_at ? ` · ${t('crm.form.sonGonderim', { tarih: tarihGoster(f.son_gonderim_at, dil, true) })}` : ''}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {t('crm.form.izinli')}: {[...veri.her_zaman_izinli, ...f.izinli_alanlar].join(', ')}
                </p>
              </div>
              <div className="flex flex-wrap gap-1">
                <Button size="sm" variant="outline" className="gap-1" onClick={() => void kopyala(f)} data-testid="crm-form-kopyala">
                  {kopyalanan === f.id ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {t('crm.form.gommeKopyala')}
                </Button>
                <a
                  className="inline-flex h-9 items-center gap-1 rounded-md border border-input px-3 text-sm hover:bg-accent"
                  href={`/form/${f.genel_anahtar}`}
                  target="_blank"
                  rel="noopener"
                  data-testid="crm-form-baglanti"
                >
                  <ExternalLink className="h-4 w-4" /> {t('crm.form.dogrudanBaglanti')}
                </a>
                <Button size="sm" variant="ghost" onClick={() => setOnizleme((x) => (x === f.id ? null : f.id))} aria-pressed={onizleme === f.id}>
                  {onizleme === f.id ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  <span className="sr-only sm:not-sr-only sm:ms-1">{t('crm.form.onizleme')}</span>
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDuzenlenen(f)} aria-label={t('crm.form.duzenle')}>
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => void sil(f)} aria-label={t('crm.sil')}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <pre
              className="mt-3 overflow-x-auto whitespace-pre rounded-xl border border-white/10 bg-black/30 p-3 text-xs"
              dir="ltr"
              data-testid="crm-form-gomme"
            >
              {gommeKodu(taban, f.genel_anahtar)}
            </pre>
            {onizleme === f.id && (
              <div className="mt-3 space-y-1">
                <p className="text-xs text-amber-200">{t('crm.form.onizlemeUyari')}</p>
                <iframe
                  title={t('crm.form.onizleme')}
                  src={`/form/${f.genel_anahtar}?dil=${dil.slice(0, 2)}`}
                  className="h-[640px] w-full rounded-xl border border-white/10 bg-background"
                />
              </div>
            )}
          </li>
        ))}
      </ul>

      {duzenlenen && (
        <FormPenceresi
          form={duzenlenen === 'yeni' ? null : duzenlenen}
          asamalar={asamalar}
          sinirlar={veri.her_zaman_izinli}
          onKapat={() => setDuzenlenen(null)}
          onKaydedildi={() => {
            setDuzenlenen(null);
            void yukle();
          }}
        />
      )}
    </div>
  );
}

function FormPenceresi({
  form,
  asamalar,
  sinirlar,
  onKapat,
  onKaydedildi,
}: {
  form: CrmFormu | null;
  asamalar: Asama[];
  sinirlar: string[];
  onKapat: () => void;
  onKaydedildi: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [taslak, setTaslak] = useState<Taslak>(() => taslakYap(form, t('crm.form.kvkkVarsayilan')));
  const [mesgul, setMesgul] = useState(false);
  const yaz = (k: keyof Taslak) => (e: { target: { value: string } }) => setTaslak((x) => ({ ...x, [k]: e.target.value }));
  const alanDegistir = (ad: FormAlani, k: 'acik' | 'zorunlu', v: boolean) =>
    setTaslak((x) => {
      const eski = x.alanlar[ad];
      const yeni = k === 'acik' ? { acik: v, zorunlu: v ? eski.zorunlu : false } : { acik: eski.acik || v, zorunlu: v };
      return { ...x, alanlar: { ...x.alanlar, [ad]: yeni } };
    });

  const kaydet = async () => {
    setMesgul(true);
    try {
      const govde = {
        ...taslak,
        varsayilan_asama: taslak.varsayilan_asama || null,
        izinli_alanlar: taslak.izinli_alanlar.split(/[\s,;]+/).filter(Boolean),
        varsayilan_etiketler: taslak.varsayilan_etiketler,
      };
      if (form) await formGuncelle(form.id, govde);
      else await formOlustur(govde);
      toast.success(t('crm.kaydedildi'));
      onKaydedildi();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] overflow-y-auto bg-background/80 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="crm-form-baslik"
        className="relative mx-auto my-8 max-w-2xl rounded-2xl border border-white/10 bg-background p-6 shadow-2xl"
      >
        <button type="button" className="absolute end-4 top-4 rounded-lg p-2 hover:bg-white/5" onClick={onKapat} aria-label={t('crm.kapat')}>
          <X className="h-4 w-4" />
        </button>
        <h3 id="crm-form-baslik" className="mb-4 text-xl font-bold">
          {form ? t('crm.form.duzenle') : t('crm.form.yeni')}
        </h3>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            void kaydet();
          }}
        >
          <AlanEtiketi ad={t('crm.form.ad')} zorunlu>
            <Input value={taslak.ad} onChange={yaz('ad')} maxLength={120} required data-testid="crm-form-ad" />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.baslik')}>
            <Input value={taslak.baslik} onChange={yaz('baslik')} maxLength={160} data-testid="crm-form-baslik-alani" />
          </AlanEtiketi>

          <fieldset className="rounded-xl border border-white/10 p-3 sm:col-span-2">
            <legend className="px-1 text-xs font-medium text-muted-foreground">{t('crm.form.alanlar')}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {ALANLAR.map((ad) => {
                const deger = taslak.alanlar[ad];
                const kilitli = ad === 'email';
                return (
                  <div key={ad} className="flex items-center justify-between gap-2 rounded-lg bg-white/[0.03] px-2 py-1.5 text-sm">
                    <span>{t(`crm.alan.${ad}`)}</span>
                    <span className="flex items-center gap-3 text-xs">
                      <label className="inline-flex items-center gap-1">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-purple-500"
                          checked={deger.acik}
                          disabled={kilitli}
                          onChange={(e) => alanDegistir(ad, 'acik', e.target.checked)}
                          data-crm-form-alan={ad}
                        />
                        {t('crm.form.goster')}
                      </label>
                      <label className="inline-flex items-center gap-1">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-purple-500"
                          checked={deger.zorunlu}
                          disabled={kilitli}
                          onChange={(e) => alanDegistir(ad, 'zorunlu', e.target.checked)}
                        />
                        {t('crm.form.zorunlu')}
                      </label>
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">{t('crm.form.epostaKilitli')}</p>
          </fieldset>

          <AlanEtiketi ad={t('crm.form.varsayilanAsama')}>
            <select className={SECIM} value={taslak.varsayilan_asama} onChange={yaz('varsayilan_asama')}>
              <option value="">{t('crm.form.ilkAsama')}</option>
              {asamalar.map((a) => (
                <option key={a.anahtar} value={a.anahtar}>
                  {asamaAdi(a, dil)}
                </option>
              ))}
            </select>
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.varsayilanEtiketler')}>
            <Input value={taslak.varsayilan_etiketler} onChange={yaz('varsayilan_etiketler')} placeholder={t('crm.etiketIpucu')} />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.tesekkur')} tam>
            <textarea className={METIN_ALANI} rows={2} value={taslak.tesekkur_metni} onChange={yaz('tesekkur_metni')} maxLength={1000} placeholder={t('crm.form.tesekkurIpucu')} />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.yonlendirme')} tam>
            <Input type="url" value={taslak.yonlendirme_adresi} onChange={yaz('yonlendirme_adresi')} placeholder="https://" dir="ltr" data-testid="crm-form-yonlendirme" />
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.izinliAlanlar')} tam>
            <textarea
              className={METIN_ALANI}
              rows={3}
              value={taslak.izinli_alanlar}
              onChange={yaz('izinli_alanlar')}
              placeholder="ornek.com"
              dir="ltr"
              data-testid="crm-form-izinli"
            />
            <span className="block text-[11px] text-muted-foreground">{t('crm.form.izinliIpucu', { liste: sinirlar.join(', ') })}</span>
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.kvkkMetni')} zorunlu tam>
            <textarea className={METIN_ALANI} rows={3} value={taslak.kvkk_metni} onChange={yaz('kvkk_metni')} maxLength={2000} required data-testid="crm-form-kvkk" />
            {form && <span className="block text-[11px] text-muted-foreground">{t('crm.form.kvkkSurumIpucu', { sayi: form.kvkk_surum })}</span>}
          </AlanEtiketi>
          <AlanEtiketi ad={t('crm.form.aydinlatma')} tam>
            <Input type="url" value={taslak.aydinlatma_baglantisi} onChange={yaz('aydinlatma_baglantisi')} placeholder="https://" dir="ltr" />
          </AlanEtiketi>
          <label className="inline-flex items-center gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-purple-500"
              checked={taslak.aktif}
              onChange={(e) => setTaslak((x) => ({ ...x, aktif: e.target.checked }))}
            />
            {t('crm.form.aktifEt')}
          </label>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={onKapat}>
              {t('crm.vazgec')}
            </Button>
            <Button type="submit" disabled={mesgul || !taslak.ad.trim() || taslak.kvkk_metni.trim().length < 10} className="gap-1" data-testid="crm-form-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {t('crm.kaydet')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
