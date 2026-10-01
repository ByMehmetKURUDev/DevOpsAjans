import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Eye,
  FileCheck2,
  FileDown,
  GitBranch,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  Wand2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import KalemDuzenleyici from '@/components/belge/KalemDuzenleyici';
import TekSeferlikBaglanti from '@/components/belge/TekSeferlikBaglanti';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  BelgeHatasi,
  PARA_BIRIMLERI,
  bosKalem,
  bugunIso,
  gunEkle,
  paraBicimle,
  pdfDili,
  pdfIndir,
  tarihBicimle,
  type Kalem,
} from '@/lib/belge';
import { sablonlar as sablonlariGetir, type Sablon } from '@/lib/sozlesmeler';
import { sablonlariGetir as projeSablonlariGetir, type ProjeSablonu } from '@/lib/zamanTakibi';
import {
  TEKLIF_DURUMLARI,
  fiyatTalebindenTeklif,
  fiyatTalepleri,
  teklifDurumRengi,
  teklifGonder,
  teklifGuncelle,
  teklifListesi,
  teklifOlustur,
  teklifRevize,
  teklifSil,
  yoneticiTeklifPdf,
  type FiyatTalebi,
  type Teklif,
  type TeklifGirdisi,
} from '@/lib/teklifler';

/**
 * Yönetici paneli › Teklifler (Faz 3T).
 *
 * Kalemli teklif hazırla → gönder (girişsiz `/teklif/<jeton>` bağlantısı YALNIZ
 * o an bir kez görünür) → görüntülenme sayısı / ilk-son görüntüleme → kabul
 * (ad soyad) ya da gerekçeli ret. Kabulde seçilen otomatik kayıtlar: sözleşme
 * taslağı (şablondan), ilk fatura (peşinat %) ve proje. Gönderilmiş teklif
 * düzenlenmez: "Revize et" yeni sürüm açar. Fiyat sihirbazı kaydı tek tıkla
 * teklife çevrilebilir. Metinler `teklif` ek paketinde.
 */

const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground';

interface Form {
  id?: number;
  baslik: string;
  aliciTuru: 'hesap' | 'aday';
  hesap_email: string;
  aday_ad: string;
  aday_eposta: string;
  para_birimi: string;
  gecerlilik: string;
  kalemler: Kalem[];
  notlar: string;
  sartlar: string;
  otomatik_sozlesme: boolean;
  sozlesme_sablon_id: string;
  otomatik_fatura: boolean;
  pesinat_yuzde: string;
  otomatik_proje: boolean;
  /** Faz 3Z: kabulde oluşan projeye uygulanacak proje şablonu. */
  proje_sablon_id: string;
}

const bosForm = (): Form => ({
  baslik: '',
  aliciTuru: 'hesap',
  hesap_email: '',
  aday_ad: '',
  aday_eposta: '',
  para_birimi: 'TRY',
  gecerlilik: gunEkle(bugunIso(), 30),
  kalemler: [bosKalem()],
  notlar: '',
  sartlar: '',
  otomatik_sozlesme: false,
  sozlesme_sablon_id: '',
  otomatik_fatura: true,
  pesinat_yuzde: '100',
  otomatik_proje: false,
  proje_sablon_id: '',
});

function formdan(t: Teklif): Form {
  return {
    id: t.id,
    baslik: t.baslik,
    aliciTuru: t.hesap_email ? 'hesap' : 'aday',
    hesap_email: t.hesap_email || '',
    aday_ad: t.musteri_ad || '',
    aday_eposta: t.aday_eposta || '',
    para_birimi: t.para_birimi,
    gecerlilik: t.gecerlilik || '',
    kalemler: t.kalemler.length ? t.kalemler : [bosKalem()],
    notlar: t.notlar || '',
    sartlar: t.sartlar || '',
    otomatik_sozlesme: !!t.otomatik_sozlesme,
    sozlesme_sablon_id: t.sozlesme_sablon_id ? String(t.sozlesme_sablon_id) : '',
    otomatik_fatura: !!t.otomatik_fatura,
    pesinat_yuzde: t.pesinat_yuzde != null ? String(t.pesinat_yuzde) : '100',
    otomatik_proje: !!t.otomatik_proje,
    proje_sablon_id: t.proje_sablon_id ? String(t.proje_sablon_id) : '',
  };
}

export default function TeklifYonetimi() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<Teklif[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [durum, setDurum] = useState('');
  const [arama, setArama] = useState('');
  const [form, setForm] = useState<Form | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [sablonlar, setSablonlar] = useState<Sablon[]>([]);
  const [projeSablonlari, setProjeSablonlari] = useState<ProjeSablonu[]>([]);
  const [talepler, setTalepler] = useState<FiyatTalebi[] | null>(null);
  const [baglanti, setBaglanti] = useState<{ teklif: Teklif; adres: string; eposta: boolean } | null>(null);
  const [epostaGonder, setEpostaGonder] = useState(true);
  const [mesgul, setMesgul] = useState<number | null>(null);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`teklif.hata.${kod}`, { defaultValue: t('teklif.hata.genel') }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setListe(await teklifListesi({ durum: durum || undefined, q: arama.trim() || undefined }));
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [durum, arama, hata]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    if (!form) return;
    sablonlariGetir()
      .then((s) => setSablonlar(s.sablonlar.filter((x) => x.aktif)))
      .catch(() => setSablonlar([]));
    projeSablonlariGetir()
      .then(setProjeSablonlari)
      .catch(() => setProjeSablonlari([]));
  }, [form]);

  const alan = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const kaydet = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setKaydediliyor(true);
    const girdi: TeklifGirdisi = {
      baslik: form.baslik,
      kalemler: form.kalemler.filter((k) => k.aciklama.trim() || k.birim_fiyat !== ''),
      para_birimi: form.para_birimi,
      hesap_email: form.aliciTuru === 'hesap' ? form.hesap_email.trim() : '',
      aday_ad: form.aday_ad.trim(),
      aday_eposta: form.aliciTuru === 'aday' ? form.aday_eposta.trim() : '',
      gecerlilik: form.gecerlilik,
      notlar: form.notlar,
      sartlar: form.sartlar,
      otomatik_sozlesme: form.otomatik_sozlesme,
      sozlesme_sablon_id: form.otomatik_sozlesme && form.sozlesme_sablon_id ? Number(form.sozlesme_sablon_id) : null,
      otomatik_fatura: form.otomatik_fatura,
      pesinat_yuzde: form.otomatik_fatura ? form.pesinat_yuzde : null,
      otomatik_proje: form.otomatik_proje,
      proje_sablon_id: form.otomatik_proje && form.proje_sablon_id ? Number(form.proje_sablon_id) : null,
    };
    try {
      if (form.id) await teklifGuncelle(form.id, girdi);
      else await teklifOlustur(girdi);
      toast.success(t('teklif.yonetim.kaydedildi'));
      setForm(null);
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setKaydediliyor(false);
    }
  };

  const islem = async (id: number, fn: () => Promise<void>) => {
    setMesgul(id);
    try {
      await fn();
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(null);
    }
  };

  const gonder = (tk: Teklif) =>
    islem(tk.id, async () => {
      const y = await teklifGonder(tk.id, epostaGonder);
      setBaglanti({ teklif: y.teklif, adres: y.baglanti, eposta: y.eposta_gonderildi });
      toast.success(t('teklif.yonetim.gonderildi'));
    });

  const revize = (tk: Teklif) =>
    islem(tk.id, async () => {
      if (!window.confirm(t('teklif.yonetim.revizeOnay', { no: tk.no }))) return;
      const yeni = await teklifRevize(tk.id);
      toast.success(t('teklif.yonetim.revizeEdildi', { no: yeni.no }));
      setForm(formdan(yeni));
    });

  const sil = (tk: Teklif) =>
    islem(tk.id, async () => {
      if (!window.confirm(t('teklif.yonetim.silOnay', { no: tk.no }))) return;
      await teklifSil(tk.id);
      toast.success(t('teklif.yonetim.silindi'));
    });

  const pdf = (tk: Teklif) =>
    islem(tk.id, async () => {
      await pdfIndir(yoneticiTeklifPdf(tk.id, pdfDili(dil)), `teklif-${tk.no}.pdf`);
    });

  const talepleriAc = async () => {
    try {
      setTalepler(await fiyatTalepleri());
    } catch (h) {
      hata(h);
    }
  };

  const teklifeCevir = async (talep: FiyatTalebi) => {
    try {
      const yeni = await fiyatTalebindenTeklif(talep.id);
      toast.success(t('teklif.yonetim.cevrildi', { no: yeni.no }));
      setTalepler(null);
      setForm(formdan(yeni));
      await yukle();
    } catch (h) {
      hata(h);
    }
  };

  return (
    <div className="space-y-6" data-testid="teklif-yonetim">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-2xl font-bold">
            <FileCheck2 className="h-6 w-6 text-purple-300" aria-hidden="true" />
            {t('teklif.yonetim.baslik')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('teklif.yonetim.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="gap-2 !bg-transparent" onClick={() => void talepleriAc()} data-testid="teklif-talepten">
            <Wand2 className="h-4 w-4" aria-hidden="true" />
            {t('teklif.yonetim.fiyatTalebinden')}
          </Button>
          <Button onClick={() => setForm(form ? null : bosForm())} className="gap-2" data-testid="teklif-yeni">
            {form ? <X className="h-4 w-4" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
            {form ? t('teklif.vazgec') : t('teklif.yonetim.yeni')}
          </Button>
        </div>
      </div>

      {baglanti && (
        <TekSeferlikBaglanti
          baglanti={baglanti.adres}
          baslik={t('teklif.yonetim.baglantiHazir')}
          altSatir={`${baglanti.teklif.no} · ${baglanti.teklif.hesap_email || baglanti.teklif.aday_eposta || ''}`}
          uyari={t('teklif.yonetim.birKezUyari')}
          epostaMetni={baglanti.eposta ? t('teklif.yonetim.epostaGitti') : null}
          kopyalaMetni={t('teklif.kopyala')}
          kapatMetni={t('teklif.kapat')}
          onKapat={() => setBaglanti(null)}
        />
      )}

      {talepler && (
        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid="teklif-talep-listesi">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="font-semibold">{t('teklif.yonetim.fiyatTalepleri')}</h3>
            <button type="button" onClick={() => setTalepler(null)} aria-label={t('teklif.kapat')}
              className="rounded-md p-1 text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {talepler.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('teklif.yonetim.talepYok')}</p>
          ) : (
            <ul className="divide-y divide-white/5 text-sm">
              {talepler.map((x) => (
                <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="min-w-0 break-all">
                    #{x.id} · {x.musteri_adi || x.musteri_eposta} · {x.scale_kod || x.ai_pm_tier_kod || x.period || '—'} ·{' '}
                    {paraBicimle(x.tutar, 'USD', dil)}
                  </span>
                  {x.teklif ? (
                    <span className="text-xs text-muted-foreground">{x.teklif.no}</span>
                  ) : (
                    <Button size="sm" variant="outline" className="!bg-transparent" onClick={() => void teklifeCevir(x)}>
                      {t('teklif.yonetim.teklifeCevir')}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {form && (
        <form onSubmit={kaydet} className="cam-kart grid gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 md:grid-cols-2"
          data-testid="teklif-form">
          <div className="grid gap-2 md:col-span-2">
            <label htmlFor="teklif-baslik" className="text-sm font-medium">{t('teklif.alan.baslik')}</label>
            <Input id="teklif-baslik" name="baslik" value={form.baslik} maxLength={200} required
              onChange={(e) => alan('baslik', e.target.value)} />
          </div>
          <fieldset className="grid gap-2 md:col-span-2">
            <legend className="mb-1 text-sm font-medium">{t('teklif.alan.alici')}</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              {(['hesap', 'aday'] as const).map((tur) => (
                <label key={tur} className="flex items-center gap-2">
                  <input type="radio" name="alici-turu" value={tur} checked={form.aliciTuru === tur}
                    onChange={() => alan('aliciTuru', tur)} className="accent-purple-500" />
                  {t(`teklif.alan.alici_${tur}`)}
                </label>
              ))}
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {form.aliciTuru === 'hesap' ? (
                <Input name="hesap_email" type="email" value={form.hesap_email} placeholder="musteri@alan.com"
                  aria-label={t('teklif.alan.hesapEposta')} onChange={(e) => alan('hesap_email', e.target.value)} required />
              ) : (
                <Input name="aday_eposta" type="email" value={form.aday_eposta} placeholder="aday@alan.com"
                  aria-label={t('teklif.alan.adayEposta')} onChange={(e) => alan('aday_eposta', e.target.value)} required />
              )}
              <Input name="aday_ad" value={form.aday_ad} placeholder={t('teklif.alan.adSoyad')}
                aria-label={t('teklif.alan.adSoyad')} onChange={(e) => alan('aday_ad', e.target.value)} />
            </div>
          </fieldset>
          <div className="grid gap-2">
            <label htmlFor="teklif-para" className="text-sm font-medium">{t('teklif.alan.paraBirimi')}</label>
            <select id="teklif-para" name="para_birimi" value={form.para_birimi} className={SECIM}
              onChange={(e) => alan('para_birimi', e.target.value)}>
              {PARA_BIRIMLERI.map((p) => <option key={p} value={p} className="bg-[#150a2b]">{p}</option>)}
            </select>
          </div>
          <div className="grid gap-2">
            <label htmlFor="teklif-gecerlilik" className="text-sm font-medium">{t('teklif.alan.gecerlilik')}</label>
            <Input id="teklif-gecerlilik" name="gecerlilik" type="date" value={form.gecerlilik}
              onChange={(e) => alan('gecerlilik', e.target.value)} />
          </div>
          <div className="grid gap-2 md:col-span-2">
            <span className="text-sm font-medium">{t('teklif.alan.kalemler')}</span>
            <KalemDuzenleyici kalemler={form.kalemler} onChange={(k) => alan('kalemler', k)} paraBirimi={form.para_birimi}
              hesapUrl="/api/v1/teklif-yonetim/hesapla" />
          </div>
          <div className="grid gap-2">
            <label htmlFor="teklif-notlar" className="text-sm font-medium">{t('teklif.alan.notlar')}</label>
            <Textarea id="teklif-notlar" name="notlar" rows={3} maxLength={5000} value={form.notlar}
              onChange={(e) => alan('notlar', e.target.value)} />
          </div>
          <div className="grid gap-2">
            <label htmlFor="teklif-sartlar" className="text-sm font-medium">{t('teklif.alan.sartlar')}</label>
            <Textarea id="teklif-sartlar" name="sartlar" rows={3} maxLength={5000} value={form.sartlar}
              onChange={(e) => alan('sartlar', e.target.value)} />
          </div>
          <fieldset className="grid gap-3 rounded-xl border border-white/10 p-4 md:col-span-2">
            <legend className="px-1 text-sm font-medium">{t('teklif.alan.kabuldeOtomatik')}</legend>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              <input type="checkbox" name="otomatik_fatura" checked={form.otomatik_fatura} className="h-4 w-4 accent-purple-500"
                onChange={(e) => alan('otomatik_fatura', e.target.checked)} />
              {t('teklif.alan.otomatikFatura')}
              {form.otomatik_fatura && (
                <span className="flex items-center gap-1">
                  <Input name="pesinat" type="number" min={1} max={100} step="any" value={form.pesinat_yuzde}
                    aria-label={t('teklif.alan.pesinat')} className="h-8 w-20" onChange={(e) => alan('pesinat_yuzde', e.target.value)} />
                  <span className="text-xs text-muted-foreground">{t('teklif.alan.pesinat')}</span>
                </span>
              )}
            </label>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              <input type="checkbox" name="otomatik_sozlesme" checked={form.otomatik_sozlesme} className="h-4 w-4 accent-purple-500"
                onChange={(e) => alan('otomatik_sozlesme', e.target.checked)} />
              {t('teklif.alan.otomatikSozlesme')}
              {form.otomatik_sozlesme && (
                <select name="sablon" value={form.sozlesme_sablon_id} className={`${SECIM} !w-auto`} style={{ height: '2rem' }}
                  aria-label={t('teklif.alan.sablon')} onChange={(e) => alan('sozlesme_sablon_id', e.target.value)}>
                  <option value="" className="bg-[#150a2b]">{t('teklif.alan.varsayilanSablon')}</option>
                  {sablonlar.map((s) => <option key={s.id} value={s.id} className="bg-[#150a2b]">{s.baslik}</option>)}
                </select>
              )}
            </label>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              <input type="checkbox" name="otomatik_proje" checked={form.otomatik_proje} className="h-4 w-4 accent-purple-500"
                onChange={(e) => alan('otomatik_proje', e.target.checked)} />
              {t('teklif.alan.otomatikProje')}
              {form.otomatik_proje && projeSablonlari.length > 0 && (
                <select name="proje_sablon_id" value={form.proje_sablon_id} className={`${SECIM} !w-auto max-w-full`} style={{ height: '2rem' }}
                  aria-label={t('teklif.alan.projeSablonu')} title={t('teklif.alan.projeSablonu')} onChange={(e) => alan('proje_sablon_id', e.target.value)}>
                  <option value="" className="bg-[#150a2b]">{t('teklif.alan.sablonsuz')}</option>
                  {projeSablonlari.map((s) => <option key={s.id} value={s.id} className="bg-[#150a2b]">{s.ad}</option>)}
                </select>
              )}
            </label>
          </fieldset>
          <div className="md:col-span-2">
            <Button type="submit" disabled={kaydediliyor} className="gap-2" data-testid="teklif-kaydet">
              {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('teklif.kaydet')}
            </Button>
          </div>
        </form>
      )}

      <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select aria-label={t('teklif.yonetim.durum')} value={durum} onChange={(e) => setDurum(e.target.value)}
            className={`${SECIM} !w-auto`}>
            <option value="" className="bg-[#150a2b]">{t('teklif.yonetim.tumDurumlar')}</option>
            {TEKLIF_DURUMLARI.map((d) => <option key={d} value={d} className="bg-[#150a2b]">{t(`teklif.durum.${d}`)}</option>)}
          </select>
          <Input value={arama} onChange={(e) => setArama(e.target.value)} placeholder={t('teklif.yonetim.ara')}
            aria-label={t('teklif.yonetim.ara')} className="max-w-md" />
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={epostaGonder} onChange={(e) => setEpostaGonder(e.target.checked)}
              className="h-4 w-4 accent-purple-500" />
            {t('teklif.yonetim.epostaGonder')}
          </label>
          <Button variant="outline" size="sm" className="gap-2 !bg-transparent" onClick={() => void yukle()}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t('teklif.yenile')}
          </Button>
        </div>
        {yukleniyor ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : liste.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('teklif.yonetim.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="teklif-liste">
            {liste.map((tk) => (
              <li key={tk.id} className="py-4" data-testid={`teklif-satir-${tk.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-semibold">{tk.no}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${teklifDurumRengi(tk.durum)}`} data-testid="teklif-durum">
                        {t(`teklif.durum.${tk.durum}`, { defaultValue: tk.durum })}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="teklif-goruntulenme"
                        title={tk.son_goruntulenme ? t('teklif.yonetim.sonGoruntulenme', { tarih: tarihBicimle(tk.son_goruntulenme, dil, true) }) : undefined}>
                        <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('teklif.yonetim.goruntulenme', { sayi: tk.goruntulenme_sayisi ?? 0 })}
                      </span>
                    </div>
                    <p className="mt-1 break-words font-medium">{tk.baslik}</p>
                    <p className="mt-0.5 break-all text-xs text-muted-foreground">
                      {tk.hesap_email || tk.aday_eposta}
                      {tk.gecerlilik ? ` · ${t('teklif.yonetim.gecerlilikKisa', { tarih: tarihBicimle(tk.gecerlilik, dil) })}` : ''}
                      {tk.ilk_goruntulenme ? ` · ${t('teklif.yonetim.ilkGoruntulenme', { tarih: tarihBicimle(tk.ilk_goruntulenme, dil, true) })}` : ''}
                    </p>
                    {tk.karar_at && (
                      <p className="mt-1 text-xs">
                        {tk.durum === 'kabul'
                          ? t('teklif.yonetim.kabulEden', { ad: tk.karar_ad || '—', tarih: tarihBicimle(tk.karar_at, dil, true) })
                          : t('teklif.yonetim.retNedeni', { not: tk.karar_notu || '—' })}
                      </p>
                    )}
                    {(tk.fatura_id || tk.sozlesme_id || tk.proje_id) && (
                      <p className="mt-1 text-xs text-emerald-300" data-testid="teklif-olusanlar">
                        {[tk.fatura_id && t('teklif.yonetim.olusanFatura', { id: tk.fatura_id }),
                          tk.sozlesme_id && t('teklif.yonetim.olusanSozlesme', { id: tk.sozlesme_id }),
                          tk.proje_id && t('teklif.yonetim.olusanProje', { id: tk.proje_id })].filter(Boolean).join(' · ')}
                      </p>
                    )}
                  </div>
                  <p className="text-lg font-bold tabular-nums">{paraBicimle(tk.ozet.genel_toplam, tk.para_birimi, dil)}</p>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {tk.durum === 'taslak' && (
                    <Button size="sm" variant="ghost" className="gap-1" onClick={() => setForm(formdan(tk))} data-testid={`teklif-duzenle-${tk.id}`}>
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />{t('teklif.duzenle')}
                    </Button>
                  )}
                  {['taslak', 'gonderildi', 'goruntulendi'].includes(tk.durum) && (
                    <Button size="sm" variant="outline" className="gap-1 !bg-transparent" disabled={mesgul === tk.id}
                      onClick={() => void gonder(tk)} data-testid={`teklif-gonder-${tk.id}`}>
                      <Send className="h-3.5 w-3.5" aria-hidden="true" />
                      {tk.durum === 'taslak' ? t('teklif.yonetim.gonder') : t('teklif.yonetim.yenidenGonder')}
                    </Button>
                  )}
                  {['gonderildi', 'goruntulendi', 'ret', 'suresi_doldu'].includes(tk.durum) && (
                    <Button size="sm" variant="ghost" className="gap-1" disabled={mesgul === tk.id} onClick={() => void revize(tk)}>
                      <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />{t('teklif.yonetim.revize')}
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="gap-1" disabled={mesgul === tk.id} onClick={() => void pdf(tk)}
                    data-testid={`teklif-pdf-${tk.id}`}>
                    <FileDown className="h-3.5 w-3.5" aria-hidden="true" />PDF
                  </Button>
                  {tk.durum !== 'kabul' && (
                    <Button size="sm" variant="ghost" className="gap-1 text-destructive hover:text-destructive" disabled={mesgul === tk.id}
                      onClick={() => void sil(tk)} aria-label={t('teklif.sil')}>
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
