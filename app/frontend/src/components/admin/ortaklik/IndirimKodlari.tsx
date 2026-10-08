import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, GIRDI, KART, Rozet, SECIM } from '@/components/ortaklik/ortak';
import { BelgeHatasi, paraBicimle, tarihBicimle } from '@/lib/belge';
import { KAPSAMLAR, OZEL_PAKETLER, kodGuncelle, kodListesi, kodOlustur, kodSil, type IndirimKodu, type Kapsam } from '@/lib/indirimKodu';
import { fiyatlandirmaApi } from '@/api/fiyatlandirma';
import { ortakListesi, type Ortak } from '@/lib/ortaklik';

interface Form {
  id?: number;
  kod: string;
  aciklama: string;
  tur: 'yuzde' | 'sabit';
  deger: string;
  para_birimi: string;
  baslangic: string;
  bitis: string;
  toplam_sinir: string;
  kisi_basi_sinir: string;
  en_az_tutar: string;
  kapsam: Kapsam[];
  paketler: string[];
  ortak_id: string;
  aktif: boolean;
}

const bos = (): Form => ({
  kod: '', aciklama: '', tur: 'yuzde', deger: '10', para_birimi: '', baslangic: '', bitis: '', toplam_sinir: '',
  kisi_basi_sinir: '', en_az_tutar: '', kapsam: [...KAPSAMLAR], paketler: [], ortak_id: '', aktif: true,
});

const formdan = (k: IndirimKodu): Form => ({
  id: k.id, kod: k.kod, aciklama: k.aciklama || '', tur: k.tur, deger: String(k.deger), para_birimi: k.para_birimi || '',
  baslangic: k.baslangic || '', bitis: k.bitis || '', toplam_sinir: k.toplam_sinir != null ? String(k.toplam_sinir) : '',
  kisi_basi_sinir: k.kisi_basi_sinir != null ? String(k.kisi_basi_sinir) : '', en_az_tutar: k.en_az_tutar != null ? String(k.en_az_tutar) : '',
  kapsam: k.kapsam, paketler: k.paketler || [], ortak_id: k.ortak_id ? String(k.ortak_id) : '', aktif: k.aktif,
});

/**
 * Faz 5K — indirim kodları (ajansın kendi satışları): yüzde / sabit tutar (KDV hariç), geçerlilik günleri,
 * toplam ve kişi başı kullanım, en az tutar, kapsam (teklif / fatura / hizmet paketi), geçerli paketler (fiyatlandırma
 * ölçekleri + kredi + AI/PM; boş = hepsi), isteğe bağlı ortak.
 * Kullanılmış kodun adı değişmez ve silinemez (belgelerde "İndirim (KOD)" yazıyor) — pasifleştirilir.
 */
export default function IndirimKodlari() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<IndirimKodu[] | null>(null);
  const [ortaklar, setOrtaklar] = useState<Ortak[]>([]);
  const [olcekler, setOlcekler] = useState<{ kod: string; ad: string }[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const hata = (h: unknown) => {
    const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
    toast.error(t(`indirimKodu.hata.${kod}`, { defaultValue: t('indirimKodu.hata.genel') }));
  };

  const yukle = useCallback(async () => {
    try {
      setListe(await kodListesi());
    } catch (h) {
      setListe([]);
      hata(h);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void yukle();
    ortakListesi('onaylandi').then(setOrtaklar).catch(() => setOrtaklar([]));
    fiyatlandirmaApi
      .scales()
      .then((l) => setOlcekler([...l].sort((a, b) => a.sira - b.sira).map((x) => ({ kod: x.kod.toUpperCase(), ad: x.ad }))))
      .catch(() => setOlcekler([]));
  }, [yukle]);

  const alan = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const kaydet = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setMesgul(true);
    const g: Record<string, unknown> = {
      kod: form.kod.trim(), aciklama: form.aciklama, tur: form.tur, deger: form.deger, para_birimi: form.para_birimi || null,
      baslangic: form.baslangic || null, bitis: form.bitis || null, toplam_sinir: form.toplam_sinir || null,
      kisi_basi_sinir: form.kisi_basi_sinir || null, en_az_tutar: form.en_az_tutar || null, kapsam: form.kapsam,
      paketler: form.paketler,
      ortak_id: form.ortak_id ? Number(form.ortak_id) : null, aktif: form.aktif,
    };
    try {
      if (form.id) await kodGuncelle(form.id, g);
      else await kodOlustur(g);
      toast.success(t('indirimKodu.yonetim.kaydedildi'));
      setForm(null);
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const sil = async (k: IndirimKodu) => {
    if (!window.confirm(t('indirimKodu.yonetim.silOnay', { kod: k.kod }))) return;
    try {
      await kodSil(k.id);
      toast.success(t('indirimKodu.yonetim.silindi'));
      await yukle();
    } catch (h) {
      hata(h);
    }
  };

  const degerMetni = (k: IndirimKodu) => (k.tur === 'yuzde' ? `%${k.deger}` : paraBicimle(k.deger, k.para_birimi || 'TRY', dil));

  return (
    <div className="space-y-4" data-testid="indirim-kodlari">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">{t('indirimKodu.yonetim.aciklama')}</p>
        <Button onClick={() => setForm(form ? null : bos())} className="gap-2" data-testid="indirim-kodu-yeni">
          {form ? <X className="h-4 w-4" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
          {form ? t('indirimKodu.yonetim.vazgec') : t('indirimKodu.yonetim.yeni')}
        </Button>
      </div>

      {form && (
        <form onSubmit={kaydet} className={`${KART} grid gap-3 p-5 md:grid-cols-3`} data-testid="indirim-kodu-form">
          <Alan etiket={t('indirimKodu.yonetim.kod')}>
            <input className={`${GIRDI} uppercase`} value={form.kod} required maxLength={32} onChange={(e) => alan('kod', e.target.value)} data-testid="indirim-kodu-kod" />
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.turEtiket')}>
            <select className={SECIM} value={form.tur} onChange={(e) => alan('tur', e.target.value as Form['tur'])} data-testid="indirim-kodu-tur">
              <option value="yuzde">{t('indirimKodu.yonetim.tur.yuzde')}</option>
              <option value="sabit">{t('indirimKodu.yonetim.tur.sabit')}</option>
            </select>
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.deger')}>
            <input className={GIRDI} type="number" min={0} step="any" required value={form.deger} onChange={(e) => alan('deger', e.target.value)} data-testid="indirim-kodu-deger" />
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.paraBirimi')} ipucu={t('indirimKodu.yonetim.paraIpucu')}>
            <select className={SECIM} value={form.para_birimi} onChange={(e) => alan('para_birimi', e.target.value)}>
              <option value="">{t('indirimKodu.yonetim.paraHepsi')}</option>
              {['TRY', 'USD', 'EUR', 'GBP'].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.baslangic')}>
            <input className={GIRDI} type="date" value={form.baslangic} onChange={(e) => alan('baslangic', e.target.value)} />
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.bitis')}>
            <input className={GIRDI} type="date" value={form.bitis} onChange={(e) => alan('bitis', e.target.value)} />
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.toplamSinir')}>
            <input className={GIRDI} type="number" min={1} value={form.toplam_sinir} placeholder={t('indirimKodu.yonetim.sinirsiz')} onChange={(e) => alan('toplam_sinir', e.target.value)} />
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.kisiBasiSinir')}>
            <input className={GIRDI} type="number" min={1} value={form.kisi_basi_sinir} placeholder={t('indirimKodu.yonetim.sinirsiz')} onChange={(e) => alan('kisi_basi_sinir', e.target.value)} />
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.enAz')}>
            <input className={GIRDI} type="number" min={0} step="any" value={form.en_az_tutar} onChange={(e) => alan('en_az_tutar', e.target.value)} />
          </Alan>
          <fieldset className="md:col-span-2">
            <legend className="mb-1 text-sm font-medium">{t('indirimKodu.yonetim.kapsam')}</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              {KAPSAMLAR.map((k) => (
                <label key={k} className="flex items-center gap-2">
                  <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={form.kapsam.includes(k)}
                    onChange={(e) => alan('kapsam', e.target.checked ? [...form.kapsam, k] : form.kapsam.filter((x) => x !== k))} />
                  {t(`indirimKodu.yonetim.kapsamlar.${k}`)}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t('indirimKodu.yonetim.paketNotu')}</p>
          </fieldset>
          <fieldset className="md:col-span-3" data-testid="indirim-kodu-paketler">
            <legend className="mb-1 text-sm font-medium">{t('indirimKodu.yonetim.paketler')}</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              {[...olcekler.map((o) => ({ kod: o.kod, ad: `${o.ad} (${o.kod})` })),
                ...OZEL_PAKETLER.map((kod) => ({ kod, ad: t(`indirimKodu.yonetim.ozelPaket.${kod}`) }))].map((p) => (
                <label key={p.kod} className="flex items-center gap-2">
                  <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={form.paketler.includes(p.kod)}
                    onChange={(e) => alan('paketler', e.target.checked ? [...form.paketler, p.kod] : form.paketler.filter((x) => x !== p.kod))} />
                  {p.ad}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t('indirimKodu.yonetim.paketIpucu')}</p>
          </fieldset>
          <Alan etiket={t('indirimKodu.yonetim.ortak')}>
            <select className={SECIM} value={form.ortak_id} onChange={(e) => alan('ortak_id', e.target.value)}>
              <option value="">{t('indirimKodu.yonetim.ortakYok')}</option>
              {ortaklar.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.ad} ({o.kod})
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('indirimKodu.yonetim.aciklamaAlani')} className="md:col-span-2">
            <input className={GIRDI} value={form.aciklama} maxLength={300} onChange={(e) => alan('aciklama', e.target.value)} />
          </Alan>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={form.aktif} onChange={(e) => alan('aktif', e.target.checked)} />
            {t('indirimKodu.yonetim.aktif')}
          </label>
          <div className="md:col-span-3">
            <Button type="submit" disabled={mesgul} className="gap-2" data-testid="indirim-kodu-kaydet">
              {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('indirimKodu.yonetim.kaydet')}
            </Button>
          </div>
        </form>
      )}

      <div className={`${KART} overflow-x-auto p-4`}>
        {!liste ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : liste.length === 0 ? (
          <p className="p-2 text-sm text-muted-foreground">{t('indirimKodu.yonetim.yok')}</p>
        ) : (
          <table className="w-full min-w-[720px] text-sm">
            <tbody className="divide-y divide-white/5">
              {liste.map((k) => (
                <tr key={k.id} data-indirim-kodu={k.kod}>
                  <td className="py-2 align-top">
                    <code className="font-semibold">{k.kod}</code>
                    {k.aciklama && <span className="block text-xs text-muted-foreground">{k.aciklama}</span>}
                  </td>
                  <td className="py-2 align-top tabular-nums">{degerMetni(k)}</td>
                  <td className="py-2 align-top text-xs text-muted-foreground">
                    {k.baslangic || k.bitis ? `${k.baslangic ? tarihBicimle(k.baslangic, dil) : '…'} – ${k.bitis ? tarihBicimle(k.bitis, dil) : '…'}` : '—'}
                    <span className="block">{k.kapsam.map((x) => t(`indirimKodu.yonetim.kapsamlar.${x}`)).join(', ')}</span>
                    {!!k.paketler?.length && <span className="block">{t('indirimKodu.yonetim.paketler')}: {k.paketler.join(', ')}</span>}
                  </td>
                  <td className="py-2 align-top text-xs">
                    {t('indirimKodu.yonetim.kullanim', { sayi: k.kullanim })}
                    {k.toplam_sinir != null && ` / ${k.toplam_sinir}`}
                    {k.ortak_ad && <span className="block text-muted-foreground">{k.ortak_ad}</span>}
                  </td>
                  <td className="py-2 align-top">
                    <Rozet durum={k.durum === 'gecerli' ? 'onaylandi' : 'iptal'}>{t(`indirimKodu.yonetim.durum.${k.durum}`)}</Rozet>
                  </td>
                  <td className="py-2 text-end align-top">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" aria-label={t('indirimKodu.yonetim.duzenle')} onClick={() => setForm(formdan(k))}>
                        <Pencil className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button size="sm" variant="ghost" aria-label={t('indirimKodu.yonetim.sil')} onClick={() => void sil(k)} disabled={k.kullanim > 0}>
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
