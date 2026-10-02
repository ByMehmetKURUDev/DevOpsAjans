import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, ExternalLink, FormInput, ListPlus, Loader2, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Alan, Anahtar, Bos, DIS_DUGME, GIRDI, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, kopyala, sayiYaz } from '@/components/epostaPazarlama/ortak';
import { hataMetni, type Form, type Liste, type Meta, type PazarlamaApi } from '@/lib/epostaPazarlama';

/** Faz 5M — listeler (statik) ve herkese açık abonelik formları (gömme kodu + /bulten/<anahtar>, çift onay). */
export default function Listeler({ api, meta }: { api: PazarlamaApi; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [listeler, setListeler] = useState<Liste[] | null>(null);
  const [formlar, setFormlar] = useState<Form[]>([]);
  const [yeniAd, setYeniAd] = useState('');
  const [duzenlenen, setDuzenlenen] = useState<Form | 'yeni' | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [l, f] = await Promise.all([api.listeler(), api.formlar()]);
      setListeler(l.items);
      setFormlar(f.items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListeler([]);
    }
  }, [api, t]);
  useEffect(() => {
    void yukle();
  }, [yukle]);

  const listeEkle = async () => {
    try {
      await api.listeEkle({ ad: yeniAd.trim() });
      setYeniAd('');
      toast.success(t('epostaPazarlama.liste.eklendi'));
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const listeSil = async (l: Liste) => {
    if (!window.confirm(t('epostaPazarlama.liste.silOnay', { ad: l.ad }))) return;
    try {
      await api.listeSil(l.id);
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };
  const listeYenidenAdlandir = async (l: Liste) => {
    const ad = window.prompt(t('epostaPazarlama.liste.ad'), l.ad);
    if (!ad || ad === l.ad) return;
    try {
      await api.listeGuncelle(l.id, { ad });
      void yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (listeler === null) return <Yukleniyor />;

  return (
    <div className="space-y-5" data-testid="ep-listeler">
      <div className={`${KART} p-4`}>
        <h3 className="mb-3 font-semibold">{t('epostaPazarlama.liste.baslik')}</h3>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row">
          <input
            className={GIRDI}
            value={yeniAd}
            onChange={(e) => setYeniAd(e.target.value)}
            placeholder={t('epostaPazarlama.liste.yeniAd')}
            aria-label={t('epostaPazarlama.liste.yeniAd')}
            data-testid="ep-liste-ad"
          />
          <Button size="sm" onClick={() => void listeEkle()} disabled={!yeniAd.trim()} className="shrink-0 gap-1.5" data-testid="ep-liste-ekle">
            <ListPlus className="h-4 w-4" aria-hidden="true" /> {t('epostaPazarlama.liste.ekle')}
          </Button>
        </div>
        {listeler.length === 0 ? (
          <Bos>{t('epostaPazarlama.liste.bos')}</Bos>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="ep-liste-listesi">
            {listeler.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 py-2" data-liste={l.ad}>
                <span className="min-w-0 truncate text-sm font-medium">{l.ad}</span>
                <span className="flex flex-wrap items-center gap-1.5 text-xs">
                  <Rozet renk="border-emerald-400/30 bg-emerald-400/10 text-emerald-200">
                    {t('epostaPazarlama.liste.aktif', { sayi: sayiYaz(l.aktif, dil) })}
                  </Rozet>
                  {l.bekliyor > 0 && <Rozet>{t('epostaPazarlama.liste.bekliyor', { sayi: sayiYaz(l.bekliyor, dil) })}</Rozet>}
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => void listeYenidenAdlandir(l)}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">{t('epostaPazarlama.genel.duzenle')}</span>
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => void listeSil(l)}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">{t('epostaPazarlama.genel.sil')}</span>
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={`${KART} p-4`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 font-semibold">
            <FormInput className="h-4 w-4 text-purple-300" aria-hidden="true" />
            {t('epostaPazarlama.form.baslik')}
          </h3>
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setDuzenlenen('yeni')} disabled={listeler.length === 0} data-testid="ep-form-yeni">
            {t('epostaPazarlama.form.yeni')}
          </Button>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">{t('epostaPazarlama.form.aciklama')}</p>
        {duzenlenen && (
          <FormDuzenle api={api} meta={meta} listeler={listeler} form={duzenlenen === 'yeni' ? null : duzenlenen} kapat={() => setDuzenlenen(null)} bitti={yukle} />
        )}
        {formlar.length === 0 ? (
          <Bos>{t('epostaPazarlama.form.bos')}</Bos>
        ) : (
          <ul className="space-y-3" data-testid="ep-form-listesi">
            {formlar.map((f) => (
              <li key={f.id} className="rounded-xl border border-white/10 p-3" data-form-anahtar={f.genel_anahtar}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-sm font-medium">{f.ad}</span>
                  <span className="flex items-center gap-1.5">
                    <Rozet renk={f.aktif ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : undefined}>
                      {f.aktif ? t('epostaPazarlama.form.yayinda') : t('epostaPazarlama.form.pasif')}
                    </Rozet>
                    <Rozet>{t('epostaPazarlama.form.gonderim', { sayi: sayiYaz(f.gonderim_sayisi, dil) })}</Rozet>
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <a href={f.adres} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-purple-200 hover:underline" data-testid="ep-form-adres">
                    {f.adres.replace(/^https?:\/\//, '')} <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                </div>
                <pre className="mt-2 overflow-x-auto whitespace-pre rounded-md bg-black/40 p-2 text-[11px]" data-testid="ep-form-gomme">
                  {f.gomme_kodu}
                </pre>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className={DIS_DUGME}
                    onClick={() => void kopyala(f.gomme_kodu, t('epostaPazarlama.genel.kopyalandi'), t('epostaPazarlama.genel.kopyalanamadi'))}
                  >
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" /> {t('epostaPazarlama.form.kodKopyala')}
                  </Button>
                  <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setDuzenlenen(f)}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> {t('epostaPazarlama.genel.duzenle')}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      if (!window.confirm(t('epostaPazarlama.form.silOnay'))) return;
                      try {
                        await api.formSil(f.id);
                        void yukle();
                      } catch (e) {
                        toast.error(hataMetni(t, e));
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> {t('epostaPazarlama.genel.sil')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function FormDuzenle({
  api,
  meta,
  listeler,
  form,
  kapat,
  bitti,
}: {
  api: PazarlamaApi;
  meta: Meta;
  listeler: Liste[];
  form: Form | null;
  kapat: () => void;
  bitti: () => void;
}) {
  const { t } = useTranslation();
  const [d, setD] = useState({
    ad: form?.ad ?? '',
    liste_id: form?.liste_id ?? listeler[0]?.id ?? 0,
    baslik: form?.baslik ?? '',
    aciklama: form?.aciklama ?? '',
    dil: form?.dil ?? 'tr',
    ad_sor: form?.ad_sor ?? true,
    tur_sor: form?.tur_sor ?? false,
    tesekkur_metni: form?.tesekkur_metni ?? '',
    aydinlatma_baglantisi: form?.aydinlatma_baglantisi ?? '',
    izinli_alanlar: (form?.izinli_alanlar ?? []).join(', '),
    aktif: form?.aktif ?? true,
  });
  const [mesgul, setMesgul] = useState(false);
  const kaydet = async () => {
    setMesgul(true);
    try {
      const govde = { ...d, izinli_alanlar: d.izinli_alanlar as unknown as string[], aydinlatma_baglantisi: d.aydinlatma_baglantisi.trim() || null } as unknown as Partial<Form>;
      if (form) await api.formGuncelle(form.id, govde);
      else await api.formEkle(govde);
      toast.success(t('epostaPazarlama.genel.kaydedildi'));
      kapat();
      bitti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };
  return (
    <div className="mb-4 space-y-3 rounded-xl border border-purple-400/30 p-3" data-testid="ep-form-duzenle">
      <div className="grid gap-3 sm:grid-cols-2">
        <Alan etiket={t('epostaPazarlama.form.ad')}>
          <input className={GIRDI} value={d.ad} onChange={(e) => setD({ ...d, ad: e.target.value })} data-testid="ep-form-ad" />
        </Alan>
        <Alan etiket={t('epostaPazarlama.liste.liste')}>
          <select className={SECIM} value={d.liste_id} onChange={(e) => setD({ ...d, liste_id: Number(e.target.value) })} data-testid="ep-form-liste">
            {listeler.map((l) => (
              <option key={l.id} value={l.id}>
                {l.ad}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.form.gorunenBaslik')}>
          <input className={GIRDI} value={d.baslik} onChange={(e) => setD({ ...d, baslik: e.target.value })} data-testid="ep-form-baslik" />
        </Alan>
        <Alan etiket={t('epostaPazarlama.form.dil')}>
          <select className={SECIM} value={d.dil} onChange={(e) => setD({ ...d, dil: e.target.value })}>
            {meta.diller.map((x) => (
              <option key={x} value={x}>
                {x.toUpperCase()}
              </option>
            ))}
          </select>
        </Alan>
        <Alan etiket={t('epostaPazarlama.form.aciklamaAlani')} className="sm:col-span-2">
          <textarea className={METIN_ALANI} value={d.aciklama} onChange={(e) => setD({ ...d, aciklama: e.target.value })} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.form.tesekkur')} className="sm:col-span-2">
          <input className={GIRDI} value={d.tesekkur_metni} onChange={(e) => setD({ ...d, tesekkur_metni: e.target.value })} />
        </Alan>
        <Alan etiket={t('epostaPazarlama.form.izinliAlanlar')} ipucu={t('epostaPazarlama.form.izinliIpucu')}>
          <input className={GIRDI} value={d.izinli_alanlar} onChange={(e) => setD({ ...d, izinli_alanlar: e.target.value })} placeholder="ornek.com" />
        </Alan>
        {!meta.yonetici && (
          <Alan etiket={t('epostaPazarlama.form.aydinlatma')} ipucu={t('epostaPazarlama.form.aydinlatmaIpucu')}>
            <input className={GIRDI} value={d.aydinlatma_baglantisi} onChange={(e) => setD({ ...d, aydinlatma_baglantisi: e.target.value })} placeholder="https://" />
          </Alan>
        )}
      </div>
      <div className="flex flex-wrap gap-4">
        <Anahtar acik={d.ad_sor} onDegis={(v) => setD({ ...d, ad_sor: v })} etiket={t('epostaPazarlama.form.adSor')} />
        <Anahtar acik={d.tur_sor} onDegis={(v) => setD({ ...d, tur_sor: v })} etiket={t('epostaPazarlama.form.turSor')} />
        <Anahtar acik={d.aktif} onDegis={(v) => setD({ ...d, aktif: v })} etiket={t('epostaPazarlama.form.yayinda')} />
      </div>
      <p className="text-xs text-muted-foreground">{t('epostaPazarlama.form.ciftOnayNotu')}</p>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void kaydet()} disabled={mesgul || !d.ad.trim()} data-testid="ep-form-kaydet">
          {mesgul && <Loader2 className="me-1 h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('epostaPazarlama.genel.kaydet')}
        </Button>
        <Button size="sm" variant="ghost" onClick={kapat}>
          {t('epostaPazarlama.genel.iptal')}
        </Button>
      </div>
    </div>
  );
}
