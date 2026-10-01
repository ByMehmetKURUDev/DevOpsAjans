import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { BarChart3, Building2, Loader2, Play, Plus, Repeat, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import KalemDuzenleyici from '@/components/belge/KalemDuzenleyici';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { BelgeHatasi, PARA_BIRIMLERI, bosKalem, paraBicimle, tarihBicimle, type Kalem } from '@/lib/belge';
import {
  ajansOku,
  ajansYaz,
  tekrarlayanCalistir,
  tekrarlayanEkle,
  tekrarlayanGuncelle,
  tekrarlayanListe,
  yaslandirma,
  type AjansBilgileri,
  type TekrarlayanSablon,
  type Yaslandirma,
} from '@/lib/faturaIslemleri';

/**
 * Yönetici › Faturalar sekmesinin üstündeki araçlar (Faz 3T):
 *  * Tekrarlayan faturalar — tek kaynak ABONELİK: aboneliğin fatura alanları
 *    (kalemler, dönem, vade). Zamanlı görev her dönem bir fatura keser;
 *    "Şimdi çalıştır" aynı dönemi ikinci kez kesmez.
 *  * Alacak yaşlandırma — müşteri × para birimi, 0–30 / 31–60 / 61–90 / 90+ gün.
 *  * Fatura bilgileri — PDF başlığındaki unvan, adres, vergi dairesi/no, IBAN
 *    (site ayarları; boş alan PDF'te görünmez).
 * Metinler `fatura` (+ kalem düzenleyici için `teklif`) ek paketinde.
 */
type Arac = 'tekrarlayan' | 'yaslandirma' | 'ajans';

const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground';

interface TekrarForm {
  id?: number;
  client_email: string;
  client_name: string;
  baslik: string;
  periyot: string;
  para_birimi: string;
  vade_gun: string;
  fatura_baslangic: string;
  fatura_otomatik: boolean;
  fatura_kalemleri: Kalem[];
}

const bosTekrar = (): TekrarForm => ({
  client_email: '',
  client_name: '',
  baslik: '',
  periyot: 'aylik',
  para_birimi: 'TRY',
  vade_gun: '7',
  fatura_baslangic: '',
  fatura_otomatik: true,
  fatura_kalemleri: [bosKalem()],
});

export default function FaturaAraclari({ onDegisti }: { onDegisti?: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [arac, setArac] = useState<Arac | null>(null);
  const [tekrarlar, setTekrarlar] = useState<TekrarlayanSablon[]>([]);
  const [tekrarForm, setTekrarForm] = useState<TekrarForm | null>(null);
  const [yas, setYas] = useState<Yaslandirma | null>(null);
  const [ajans, setAjans] = useState<AjansBilgileri | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`fatura.hata.${kod}`, { defaultValue: t('fatura.hata.genel') }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    if (!arac) return;
    setMesgul(true);
    try {
      if (arac === 'tekrarlayan') setTekrarlar(await tekrarlayanListe());
      if (arac === 'yaslandirma') setYas(await yaslandirma());
      if (arac === 'ajans') setAjans((await ajansOku()).kayitli);
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  }, [arac, hata]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const tekrarKaydet = async (e: FormEvent) => {
    e.preventDefault();
    if (!tekrarForm) return;
    setMesgul(true);
    try {
      const veri = {
        client_email: tekrarForm.client_email.trim(),
        client_name: tekrarForm.client_name.trim(),
        baslik: tekrarForm.baslik.trim(),
        periyot: tekrarForm.periyot,
        para_birimi: tekrarForm.para_birimi,
        vade_gun: Number(tekrarForm.vade_gun) || 0,
        fatura_baslangic: tekrarForm.fatura_baslangic || undefined,
        fatura_otomatik: tekrarForm.fatura_otomatik,
        fatura_kalemleri: tekrarForm.fatura_kalemleri.filter((k) => k.aciklama.trim()),
      };
      if (tekrarForm.id) await tekrarlayanGuncelle(tekrarForm.id, veri);
      else await tekrarlayanEkle(veri);
      toast.success(t('fatura.tekrar.kaydedildi'));
      setTekrarForm(null);
      setTekrarlar(await tekrarlayanListe());
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const calistir = async () => {
    setMesgul(true);
    try {
      const s = await tekrarlayanCalistir();
      toast.success(t('fatura.tekrar.calisti', { sayi: s.kesilen }));
      setTekrarlar(await tekrarlayanListe());
      onDegisti?.();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const ajansKaydet = async (e: FormEvent) => {
    e.preventDefault();
    if (!ajans) return;
    setMesgul(true);
    try {
      setAjans((await ajansYaz(ajans)).kayitli);
      toast.success(t('fatura.ajans.kaydedildi'));
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const DILIMLER = ['vadesi_gelmemis', 'g0_30', 'g31_60', 'g61_90', 'g90_ustu'] as const;

  return (
    <div className="mb-6 space-y-4" data-testid="fatura-araclari">
      <div className="flex flex-wrap gap-2" role="tablist">
        {([['tekrarlayan', Repeat], ['yaslandirma', BarChart3], ['ajans', Building2]] as const).map(([k, Ikon]) => (
          <Button key={k} size="sm" role="tab" aria-selected={arac === k} variant={arac === k ? 'default' : 'outline'}
            className={arac === k ? 'gap-2' : 'gap-2 !bg-transparent'} onClick={() => setArac(arac === k ? null : k)}
            data-testid={`fatura-arac-${k}`}>
            <Ikon className="h-4 w-4" aria-hidden="true" />{t(`fatura.arac.${k}`)}
          </Button>
        ))}
        {mesgul && <Loader2 className="h-4 w-4 animate-spin self-center text-muted-foreground" aria-hidden="true" />}
      </div>

      {arac === 'tekrarlayan' && (
        <section className="cam-kart space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid="tekrarlayan-panel">
          <p className="text-sm text-muted-foreground">{t('fatura.tekrar.aciklama')}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" className="gap-2" onClick={() => setTekrarForm(tekrarForm ? null : bosTekrar())} data-testid="tekrar-yeni">
              {tekrarForm ? <X className="h-4 w-4" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {tekrarForm ? t('fatura.vazgec') : t('fatura.tekrar.yeni')}
            </Button>
            <Button size="sm" variant="outline" className="gap-2 !bg-transparent" disabled={mesgul} onClick={() => void calistir()}
              data-testid="tekrar-calistir">
              <Play className="h-4 w-4" aria-hidden="true" />{t('fatura.tekrar.simdiCalistir')}
            </Button>
          </div>
          {tekrarForm && (
            <form onSubmit={tekrarKaydet} className="grid gap-3 rounded-xl border border-white/10 p-4 md:grid-cols-2" data-testid="tekrar-form">
              {!tekrarForm.id && (
                <>
                  <Input name="tekrar-eposta" type="email" required value={tekrarForm.client_email} placeholder={t('fatura.tekrar.musteriEposta')}
                    aria-label={t('fatura.tekrar.musteriEposta')} onChange={(e) => setTekrarForm({ ...tekrarForm, client_email: e.target.value })} />
                  <Input name="tekrar-ad" value={tekrarForm.client_name} placeholder={t('fatura.tekrar.musteriAd')}
                    aria-label={t('fatura.tekrar.musteriAd')} onChange={(e) => setTekrarForm({ ...tekrarForm, client_name: e.target.value })} />
                </>
              )}
              <Input name="tekrar-baslik" required value={tekrarForm.baslik} placeholder={t('fatura.tekrar.baslik')} className="md:col-span-2"
                aria-label={t('fatura.tekrar.baslik')} onChange={(e) => setTekrarForm({ ...tekrarForm, baslik: e.target.value })} />
              <label className="grid gap-1 text-xs">{t('fatura.tekrar.periyot')}
                <select value={tekrarForm.periyot} className={SECIM} onChange={(e) => setTekrarForm({ ...tekrarForm, periyot: e.target.value })}>
                  <option value="aylik" className="bg-[#150a2b]">{t('fatura.tekrar.aylik')}</option>
                  <option value="yillik" className="bg-[#150a2b]">{t('fatura.tekrar.yillik')}</option>
                </select>
              </label>
              <label className="grid gap-1 text-xs">{t('fatura.tekrar.paraBirimi')}
                <select value={tekrarForm.para_birimi} className={SECIM} onChange={(e) => setTekrarForm({ ...tekrarForm, para_birimi: e.target.value })}>
                  {PARA_BIRIMLERI.map((p) => <option key={p} value={p} className="bg-[#150a2b]">{p}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs">{t('fatura.tekrar.baslangic')}
                <Input type="month" value={tekrarForm.fatura_baslangic} onChange={(e) => setTekrarForm({ ...tekrarForm, fatura_baslangic: e.target.value })} />
              </label>
              <label className="grid gap-1 text-xs">{t('fatura.tekrar.vadeGun')}
                <Input type="number" min={0} max={365} value={tekrarForm.vade_gun} onChange={(e) => setTekrarForm({ ...tekrarForm, vade_gun: e.target.value })} />
              </label>
              <div className="md:col-span-2">
                <KalemDuzenleyici kalemler={tekrarForm.fatura_kalemleri} paraBirimi={tekrarForm.para_birimi}
                  onChange={(k) => setTekrarForm({ ...tekrarForm, fatura_kalemleri: k })} hesapUrl="/api/v1/fatura-yonetim/hesapla" />
              </div>
              <label className="flex items-center gap-2 text-sm md:col-span-2">
                <input type="checkbox" checked={tekrarForm.fatura_otomatik} className="h-4 w-4 accent-purple-500"
                  onChange={(e) => setTekrarForm({ ...tekrarForm, fatura_otomatik: e.target.checked })} />
                {t('fatura.tekrar.otomatik')}
              </label>
              <div className="md:col-span-2"><Button type="submit" disabled={mesgul} data-testid="tekrar-kaydet">{t('fatura.kaydet')}</Button></div>
            </form>
          )}
          <ul className="divide-y divide-white/5 text-sm" data-testid="tekrar-liste">
            {tekrarlar.length === 0 && <li className="py-4 text-center text-muted-foreground">{t('fatura.tekrar.bos')}</li>}
            {tekrarlar.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <span className="min-w-0">
                  <span className="font-medium">{a.baslik || a.hizmet}</span>
                  <span className="block break-all text-xs text-muted-foreground">
                    {a.client_email} · {t(`fatura.tekrar.${a.periyot === 'yillik' ? 'yillik' : 'aylik'}`)} · {paraBicimle(a.tutar ?? null, a.para_birimi || 'TRY', dil)}
                    {a.son_fatura_donemi ? ` · ${t('fatura.tekrar.sonDonem', { donem: a.son_fatura_donemi })}` : ''}
                    {` · ${t('fatura.tekrar.faturaSayisi', { sayi: a.fatura_sayisi ?? 0 })}`}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${a.fatura_otomatik ? 'bg-emerald-500/15 text-emerald-300' : 'bg-white/10 text-muted-foreground'}`}>
                    {a.fatura_otomatik ? t('fatura.tekrar.acik') : t('fatura.tekrar.kapali')}
                  </span>
                  <Button size="sm" variant="ghost" onClick={() => setTekrarForm({
                    id: a.id, client_email: a.client_email, client_name: a.client_name || '', baslik: a.baslik || a.hizmet,
                    periyot: a.periyot || 'aylik', para_birimi: a.para_birimi || 'TRY', vade_gun: String(a.vade_gun ?? 7),
                    fatura_baslangic: a.fatura_baslangic || '', fatura_otomatik: a.fatura_otomatik,
                    fatura_kalemleri: a.fatura_kalemleri.length ? a.fatura_kalemleri : [{ ...bosKalem(), aciklama: a.baslik || a.hizmet, birim_fiyat: a.tutar ?? '' }],
                  })}>
                    {t('fatura.duzenle')}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {arac === 'yaslandirma' && (
        <section className="cam-kart overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid="yaslandirma-panel">
          <p className="mb-3 text-sm text-muted-foreground">{t('fatura.yas.aciklama', { tarih: tarihBicimle(yas?.bugun, dil) })}</p>
          {!yas || yas.satirlar.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">{t('fatura.yas.bos')}</p>
          ) : (
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs text-muted-foreground">
                  <th className="py-2 text-start font-medium">{t('fatura.yas.musteri')}</th>
                  {DILIMLER.map((d) => <th key={d} className="px-2 py-2 text-end font-medium">{t(`fatura.yas.${d}`)}</th>)}
                  <th className="py-2 ps-3 text-end font-medium">{t('fatura.yas.toplam')}</th>
                </tr>
              </thead>
              <tbody>
                {yas.satirlar.map((s) => (
                  <tr key={`${s.client_email}-${s.para_birimi}`} className="border-b border-white/5">
                    <td className="py-2 pe-2">
                      <span className="block break-all">{s.client_name || s.client_email}</span>
                      <span className="text-xs text-muted-foreground">{t('fatura.yas.faturaSayisi', { sayi: s.fatura_sayisi })}</span>
                    </td>
                    {DILIMLER.map((d) => (
                      <td key={d} className={`px-2 py-2 text-end tabular-nums ${s[d] && d === 'g90_ustu' ? 'text-red-300' : ''}`}>
                        {s[d] ? paraBicimle(s[d], s.para_birimi, dil) : '—'}
                      </td>
                    ))}
                    <td className="py-2 ps-3 text-end font-semibold tabular-nums">{paraBicimle(s.toplam, s.para_birimi, dil)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                {yas.toplamlar.map((tp) => (
                  <tr key={tp.para_birimi} className="font-semibold">
                    <td className="py-2">{t('fatura.yas.genelToplam', { para: tp.para_birimi })}</td>
                    {DILIMLER.map((d) => <td key={d} className="px-2 py-2 text-end tabular-nums">{paraBicimle(tp[d], tp.para_birimi, dil)}</td>)}
                    <td className="py-2 ps-3 text-end tabular-nums">{paraBicimle(tp.toplam, tp.para_birimi, dil)}</td>
                  </tr>
                ))}
              </tfoot>
            </table>
          )}
        </section>
      )}

      {arac === 'ajans' && ajans && (
        <form onSubmit={ajansKaydet} className="cam-kart grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-5 md:grid-cols-2"
          data-testid="ajans-form">
          <p className="text-sm text-muted-foreground md:col-span-2">{t('fatura.ajans.aciklama')}</p>
          {(['unvan', 'vergi_dairesi', 'vergi_no', 'iban', 'eposta', 'telefon'] as const).map((k) => (
            <label key={k} className="grid gap-1 text-xs">{t(`fatura.ajans.${k}`)}
              <Input name={`ajans-${k}`} value={ajans[k]} maxLength={300} onChange={(e) => setAjans({ ...ajans, [k]: e.target.value })} />
            </label>
          ))}
          <label className="grid gap-1 text-xs md:col-span-2">{t('fatura.ajans.adres')}
            <Textarea name="ajans-adres" rows={2} value={ajans.adres} maxLength={500} onChange={(e) => setAjans({ ...ajans, adres: e.target.value })} />
          </label>
          <div className="md:col-span-2"><Button type="submit" disabled={mesgul} data-testid="ajans-kaydet">{t('fatura.kaydet')}</Button></div>
        </form>
      )}
    </div>
  );
}
