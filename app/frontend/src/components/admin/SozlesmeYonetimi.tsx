import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Ban,
  FileDown,
  FileSignature,
  History,
  LayoutTemplate,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import TekSeferlikBaglanti from '@/components/belge/TekSeferlikBaglanti';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { BelgeHatasi, pdfIndir, tarihBicimle } from '@/lib/belge';
import {
  SOZLESME_DURUMLARI,
  sablonEkle,
  sablonGuncelle,
  sablonSil,
  sablonlar as sablonlariGetir,
  sozlesmeDurumRengi,
  sozlesmeGonder,
  sozlesmeGuncelle,
  sozlesmeIptal,
  sozlesmeListesi,
  sozlesmeOlustur,
  sozlesmeSil,
  sozlesmeSurumleri,
  yoneticiSozlesmePdf,
  type Sablon,
  type Sozlesme,
} from '@/lib/sozlesmeler';
import { teklifListesi, type Teklif } from '@/lib/teklifler';

/**
 * Yönetici paneli › Sözleşmeler (Faz 3T).
 *
 * Şablondan (yer tutucular: {{musteri_adi}}, {{teklif_no}}, {{toplam}}…) ya da
 * kabul edilmiş tekliften sözleşme; bağlantıyla basit elektronik imza (ad
 * soyad + "okudum, kabul ediyorum" + isteğe bağlı çizim). İmzalı sözleşmenin
 * metni değişmez — değişiklik yeni sürüm açar; imzalı sözleşme silinmez, iptal
 * edilir. Metinler `sozlesme` ek paketinde (sözleşme gövdesi çevrilmez).
 */

const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground';

interface YeniForm {
  sablon_id: string;
  teklif_id: string;
  hesap_email: string;
  taraf_ad: string;
  taraf_eposta: string;
  dil: string;
  baslangic: string;
  bitis: string;
  baslik: string;
  govde: string;
}

const bosYeni = (): YeniForm => ({
  sablon_id: '',
  teklif_id: '',
  hesap_email: '',
  taraf_ad: '',
  taraf_eposta: '',
  dil: 'tr',
  baslangic: '',
  bitis: '',
  baslik: '',
  govde: '',
});

export default function SozlesmeYonetimi() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [gorunum, setGorunum] = useState<'sozlesmeler' | 'sablonlar'>('sozlesmeler');
  const [liste, setListe] = useState<Sozlesme[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [durum, setDurum] = useState('');
  const [sablonListesi, setSablonListesi] = useState<Sablon[]>([]);
  const [yerTutucular, setYerTutucular] = useState<string[]>([]);
  const [varsayilan, setVarsayilan] = useState('');
  const [kabulTeklifler, setKabulTeklifler] = useState<Teklif[]>([]);
  const [yeni, setYeni] = useState<YeniForm | null>(null);
  const [duzenle, setDuzenle] = useState<Sozlesme | null>(null);
  const [sablonForm, setSablonForm] = useState<Partial<Sablon> | null>(null);
  const [surumler, setSurumler] = useState<{ id: number; liste: Sozlesme[] } | null>(null);
  const [baglanti, setBaglanti] = useState<{ s: Sozlesme; adres: string; eposta: boolean } | null>(null);
  const [epostaGonder, setEpostaGonder] = useState(true);
  const [mesgul, setMesgul] = useState(false);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`sozlesme.hata.${kod}`, { defaultValue: t('sozlesme.hata.genel') }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const [l, s] = await Promise.all([sozlesmeListesi({ durum: durum || undefined }), sablonlariGetir()]);
      setListe(l);
      setSablonListesi(s.sablonlar);
      setYerTutucular(s.yer_tutucular);
      setVarsayilan(s.varsayilan_govde);
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [durum, hata]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  useEffect(() => {
    if (!yeni) return;
    teklifListesi({ durum: 'kabul' }).then(setKabulTeklifler).catch(() => setKabulTeklifler([]));
  }, [yeni]);

  const calistir = async (fn: () => Promise<void>) => {
    setMesgul(true);
    try {
      await fn();
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const olustur = (e: FormEvent) => {
    e.preventDefault();
    if (!yeni) return;
    void calistir(async () => {
      await sozlesmeOlustur({
        sablon_id: yeni.sablon_id ? Number(yeni.sablon_id) : null,
        teklif_id: yeni.teklif_id ? Number(yeni.teklif_id) : null,
        hesap_email: yeni.hesap_email.trim() || undefined,
        taraf_ad: yeni.taraf_ad.trim() || undefined,
        taraf_eposta: yeni.taraf_eposta.trim() || undefined,
        dil: yeni.dil,
        baslangic: yeni.baslangic || undefined,
        bitis: yeni.bitis || undefined,
        baslik: yeni.baslik.trim() || undefined,
        govde: yeni.govde.trim() || undefined,
      });
      toast.success(t('sozlesme.yonetim.olusturuldu'));
      setYeni(null);
    });
  };

  const kaydet = (e: FormEvent) => {
    e.preventDefault();
    if (!duzenle) return;
    void calistir(async () => {
      const y = await sozlesmeGuncelle(duzenle.id, {
        baslik: duzenle.baslik,
        govde: duzenle.govde,
        taraf_ad: duzenle.taraf_ad || '',
        taraf_eposta: duzenle.taraf_eposta || '',
        baslangic: duzenle.baslangic || '',
        bitis: duzenle.bitis || '',
      });
      toast.success(y.yeni_surum ? t('sozlesme.yonetim.yeniSurumAcildi', { surum: y.surum }) : t('sozlesme.yonetim.kaydedildi'));
      setDuzenle(null);
    });
  };

  const gonder = (s: Sozlesme) =>
    calistir(async () => {
      const y = await sozlesmeGonder(s.id, epostaGonder);
      setBaglanti({ s: y.sozlesme, adres: y.baglanti, eposta: y.eposta_gonderildi });
      toast.success(t('sozlesme.yonetim.gonderildi'));
    });

  const sablonKaydet = (e: FormEvent) => {
    e.preventDefault();
    if (!sablonForm) return;
    void calistir(async () => {
      const veri = {
        baslik: sablonForm.baslik || '',
        govde: sablonForm.govde || '',
        baslik_en: sablonForm.baslik_en || '',
        govde_en: sablonForm.govde_en || '',
        aktif: sablonForm.aktif !== false,
      };
      if (sablonForm.id) await sablonGuncelle(sablonForm.id, veri);
      else await sablonEkle(veri);
      toast.success(t('sozlesme.sablon.kaydedildi'));
      setSablonForm(null);
    });
  };

  return (
    <div className="space-y-6" data-testid="sozlesme-yonetim">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-2xl font-bold">
            <FileSignature className="h-6 w-6 text-purple-300" aria-hidden="true" />
            {t('sozlesme.yonetim.baslik')}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('sozlesme.yonetim.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2" role="tablist">
          {(['sozlesmeler', 'sablonlar'] as const).map((g) => (
            <Button key={g} role="tab" aria-selected={gorunum === g} variant={gorunum === g ? 'default' : 'outline'}
              className={gorunum === g ? 'gap-2' : 'gap-2 !bg-transparent'} onClick={() => setGorunum(g)} data-testid={`sozlesme-gorunum-${g}`}>
              {g === 'sozlesmeler' ? <FileSignature className="h-4 w-4" aria-hidden="true" /> : <LayoutTemplate className="h-4 w-4" aria-hidden="true" />}
              {t(`sozlesme.yonetim.${g}`)}
            </Button>
          ))}
        </div>
      </div>

      <p className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-100">{t('sozlesme.hukukiNot')}</p>

      {baglanti && (
        <TekSeferlikBaglanti
          baglanti={baglanti.adres}
          baslik={t('sozlesme.yonetim.baglantiHazir')}
          altSatir={`${baglanti.s.no} v${baglanti.s.surum} · ${baglanti.s.taraf_eposta || baglanti.s.hesap_email || ''}`}
          uyari={t('sozlesme.yonetim.birKezUyari')}
          epostaMetni={baglanti.eposta ? t('sozlesme.yonetim.epostaGitti') : null}
          kopyalaMetni={t('sozlesme.kopyala')}
          kapatMetni={t('sozlesme.kapat')}
          onKapat={() => setBaglanti(null)}
        />
      )}

      {gorunum === 'sablonlar' ? (
        <section className="space-y-4">
          <Button onClick={() => setSablonForm(sablonForm ? null : { aktif: true, govde: varsayilan })} className="gap-2"
            data-testid="sablon-yeni">
            {sablonForm ? <X className="h-4 w-4" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
            {sablonForm ? t('sozlesme.vazgec') : t('sozlesme.sablon.yeni')}
          </Button>
          {sablonForm && (
            <form onSubmit={sablonKaydet} className="cam-kart grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
              data-testid="sablon-form">
              <Input name="sablon-baslik" value={sablonForm.baslik || ''} required maxLength={200} placeholder={t('sozlesme.sablon.baslik')}
                aria-label={t('sozlesme.sablon.baslik')} onChange={(e) => setSablonForm({ ...sablonForm, baslik: e.target.value })} />
              <Textarea name="sablon-govde" rows={10} required value={sablonForm.govde || ''} aria-label={t('sozlesme.sablon.govde')}
                onChange={(e) => setSablonForm({ ...sablonForm, govde: e.target.value })} className="font-mono text-xs" />
              <p className="text-xs text-muted-foreground">
                {t('sozlesme.sablon.yerTutucular')}: {yerTutucular.map((y) => `{{${y}}}`).join(' ')}
              </p>
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">{t('sozlesme.sablon.ingilizce')}</summary>
                <div className="mt-2 grid gap-2">
                  <Input value={sablonForm.baslik_en || ''} maxLength={200} placeholder="Title (EN)" aria-label="Title (EN)"
                    onChange={(e) => setSablonForm({ ...sablonForm, baslik_en: e.target.value })} />
                  <Textarea rows={6} value={sablonForm.govde_en || ''} aria-label="Body (EN)" className="font-mono text-xs"
                    onChange={(e) => setSablonForm({ ...sablonForm, govde_en: e.target.value })} />
                </div>
              </details>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={sablonForm.aktif !== false} className="h-4 w-4 accent-purple-500"
                  onChange={(e) => setSablonForm({ ...sablonForm, aktif: e.target.checked })} />
                {t('sozlesme.sablon.aktif')}
              </label>
              <div>
                <Button type="submit" disabled={mesgul} data-testid="sablon-kaydet">{t('sozlesme.kaydet')}</Button>
              </div>
            </form>
          )}
          <ul className="cam-kart divide-y divide-white/5 rounded-2xl border border-white/10 bg-white/[0.03] px-4" data-testid="sablon-liste">
            {sablonListesi.length === 0 && <li className="py-6 text-center text-sm text-muted-foreground">{t('sozlesme.sablon.bos')}</li>}
            {sablonListesi.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <span className="min-w-0 break-words">
                  {s.baslik} {!s.aktif && <span className="text-xs text-muted-foreground">({t('sozlesme.sablon.pasif')})</span>}
                </span>
                <span className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setSablonForm(s)} aria-label={t('sozlesme.duzenle')}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                  <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" aria-label={t('sozlesme.sil')}
                    onClick={() => window.confirm(t('sozlesme.sablon.silOnay')) && void calistir(async () => { await sablonSil(s.id); })}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => setYeni(yeni ? null : bosYeni())} className="gap-2" data-testid="sozlesme-yeni">
              {yeni ? <X className="h-4 w-4" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {yeni ? t('sozlesme.vazgec') : t('sozlesme.yonetim.yeni')}
            </Button>
            <select aria-label={t('sozlesme.yonetim.durum')} value={durum} onChange={(e) => setDurum(e.target.value)}
              className={`${SECIM} !w-auto`}>
              <option value="" className="bg-[#150a2b]">{t('sozlesme.yonetim.tumDurumlar')}</option>
              {SOZLESME_DURUMLARI.map((d) => <option key={d} value={d} className="bg-[#150a2b]">{t(`sozlesme.durum.${d}`)}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={epostaGonder} onChange={(e) => setEpostaGonder(e.target.checked)}
                className="h-4 w-4 accent-purple-500" />
              {t('sozlesme.yonetim.epostaGonder')}
            </label>
            <Button variant="outline" size="sm" className="gap-2 !bg-transparent" onClick={() => void yukle()}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />{t('sozlesme.yenile')}
            </Button>
          </div>

          {yeni && (
            <form onSubmit={olustur} className="cam-kart grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6 md:grid-cols-2"
              data-testid="sozlesme-form">
              <label className="grid gap-1 text-sm">
                {t('sozlesme.alan.sablon')}
                <select name="sablon" value={yeni.sablon_id} className={SECIM} onChange={(e) => setYeni({ ...yeni, sablon_id: e.target.value })}>
                  <option value="" className="bg-[#150a2b]">{t('sozlesme.alan.sablonsuz')}</option>
                  {sablonListesi.filter((s) => s.aktif).map((s) => <option key={s.id} value={s.id} className="bg-[#150a2b]">{s.baslik}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                {t('sozlesme.alan.teklif')}
                <select name="teklif" value={yeni.teklif_id} className={SECIM} onChange={(e) => {
                  const tk = kabulTeklifler.find((x) => String(x.id) === e.target.value);
                  setYeni({ ...yeni, teklif_id: e.target.value, hesap_email: tk?.hesap_email || yeni.hesap_email,
                    taraf_eposta: tk?.hesap_email || yeni.taraf_eposta, taraf_ad: tk?.karar_ad || tk?.musteri_ad || yeni.taraf_ad });
                }}>
                  <option value="" className="bg-[#150a2b]">—</option>
                  {kabulTeklifler.map((tk) => <option key={tk.id} value={tk.id} className="bg-[#150a2b]">{tk.no} · {tk.baslik}</option>)}
                </select>
              </label>
              <Input name="hesap_email" type="email" value={yeni.hesap_email} placeholder={t('sozlesme.alan.hesapEposta')}
                aria-label={t('sozlesme.alan.hesapEposta')} onChange={(e) => setYeni({ ...yeni, hesap_email: e.target.value })} />
              <Input name="taraf_eposta" type="email" value={yeni.taraf_eposta} placeholder={t('sozlesme.alan.tarafEposta')}
                aria-label={t('sozlesme.alan.tarafEposta')} onChange={(e) => setYeni({ ...yeni, taraf_eposta: e.target.value })} />
              <Input name="taraf_ad" value={yeni.taraf_ad} placeholder={t('sozlesme.alan.tarafAd')} aria-label={t('sozlesme.alan.tarafAd')}
                onChange={(e) => setYeni({ ...yeni, taraf_ad: e.target.value })} />
              <label className="grid gap-1 text-sm">
                {t('sozlesme.alan.dil')}
                <select name="dil" value={yeni.dil} className={SECIM} onChange={(e) => setYeni({ ...yeni, dil: e.target.value })}>
                  <option value="tr" className="bg-[#150a2b]">Türkçe</option>
                  <option value="en" className="bg-[#150a2b]">English</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                {t('sozlesme.alan.baslangic')}
                <Input name="baslangic" type="date" value={yeni.baslangic} onChange={(e) => setYeni({ ...yeni, baslangic: e.target.value })} />
              </label>
              <label className="grid gap-1 text-sm">
                {t('sozlesme.alan.bitis')}
                <Input name="bitis" type="date" value={yeni.bitis} onChange={(e) => setYeni({ ...yeni, bitis: e.target.value })} />
              </label>
              {!yeni.sablon_id && (
                <>
                  <Input name="baslik" className="md:col-span-2" value={yeni.baslik} placeholder={t('sozlesme.alan.baslik')}
                    aria-label={t('sozlesme.alan.baslik')} onChange={(e) => setYeni({ ...yeni, baslik: e.target.value })} />
                  <Textarea name="govde" className="font-mono text-xs md:col-span-2" rows={8} value={yeni.govde}
                    placeholder={t('sozlesme.alan.govdeIpucu')} aria-label={t('sozlesme.alan.govde')}
                    onChange={(e) => setYeni({ ...yeni, govde: e.target.value })} />
                </>
              )}
              <div className="md:col-span-2">
                <Button type="submit" disabled={mesgul} className="gap-2" data-testid="sozlesme-olustur">
                  {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                  {t('sozlesme.yonetim.olustur')}
                </Button>
              </div>
            </form>
          )}

          {duzenle && (
            <form onSubmit={kaydet} className="cam-kart grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6 lg:grid-cols-2"
              data-testid="sozlesme-duzenle-form">
              <div className="grid gap-2">
                {duzenle.durum === 'imzalandi' && (
                  <p className="rounded-lg border border-white/10 bg-sky-500/10 p-2 text-xs text-sky-100">
                    {t('sozlesme.yonetim.imzaliDuzenlemeUyari')}
                  </p>
                )}
                <Input value={duzenle.baslik} maxLength={200} aria-label={t('sozlesme.alan.baslik')}
                  onChange={(e) => setDuzenle({ ...duzenle, baslik: e.target.value })} />
                <Textarea rows={14} value={duzenle.govde} className="font-mono text-xs" aria-label={t('sozlesme.alan.govde')}
                  onChange={(e) => setDuzenle({ ...duzenle, govde: e.target.value })} />
                <div className="grid grid-cols-2 gap-2">
                  <label className="grid gap-1 text-xs">{t('sozlesme.alan.baslangic')}
                    <Input type="date" value={duzenle.baslangic || ''} onChange={(e) => setDuzenle({ ...duzenle, baslangic: e.target.value })} />
                  </label>
                  <label className="grid gap-1 text-xs">{t('sozlesme.alan.bitis')}
                    <Input type="date" value={duzenle.bitis || ''} onChange={(e) => setDuzenle({ ...duzenle, bitis: e.target.value })} />
                  </label>
                </div>
                <div className="flex gap-2">
                  <Button type="submit" disabled={mesgul}>{t('sozlesme.kaydet')}</Button>
                  <Button type="button" variant="ghost" onClick={() => setDuzenle(null)}>{t('sozlesme.vazgec')}</Button>
                </div>
              </div>
              <div className="max-h-[32rem] overflow-y-auto rounded-xl border border-white/10 bg-black/20 p-4">
                <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">{t('sozlesme.yonetim.onizleme')}</p>
                <h3 className="mb-2 font-semibold">{duzenle.baslik}</h3>
                <GuvenliMarkdown metin={duzenle.govde} />
              </div>
            </form>
          )}

          <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6">
            {yukleniyor ? (
              <div className="flex justify-center py-10 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /></div>
            ) : liste.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">{t('sozlesme.yonetim.bos')}</p>
            ) : (
              <ul className="divide-y divide-white/5" data-testid="sozlesme-liste">
                {liste.map((s) => (
                  <li key={s.id} className="py-4" data-testid={`sozlesme-satir-${s.id}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-semibold">{s.no}</span>
                      <span className="text-xs text-muted-foreground">v{s.surum}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${sozlesmeDurumRengi(s.durum)}`} data-testid="sozlesme-durum">
                        {t(`sozlesme.durum.${s.durum}`, { defaultValue: s.durum })}
                      </span>
                    </div>
                    <p className="mt-1 break-words font-medium">{s.baslik}</p>
                    <p className="mt-0.5 break-all text-xs text-muted-foreground">
                      {s.taraf_ad ? `${s.taraf_ad} · ` : ''}{s.taraf_eposta || s.hesap_email}
                      {s.bitis ? ` · ${t('sozlesme.yonetim.bitisKisa', { tarih: tarihBicimle(s.bitis, dil) })}` : ''}
                    </p>
                    {s.imza_at && (
                      <p className="mt-1 text-xs text-emerald-300" data-testid="sozlesme-imza-bilgisi">
                        {t('sozlesme.yonetim.imzalayan', { ad: s.imza_ad, tarih: tarihBicimle(s.imza_at, dil, true) })}
                        {' · '}<span className="font-mono">{(s.imza_metin_ozeti || '').slice(0, 16)}…</span>
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {s.durum !== 'iptal' && (
                        <Button size="sm" variant="ghost" className="gap-1" onClick={() => setDuzenle(s)} data-testid={`sozlesme-duzenle-${s.id}`}>
                          <Pencil className="h-3.5 w-3.5" aria-hidden="true" />{t('sozlesme.duzenle')}
                        </Button>
                      )}
                      {(s.durum === 'taslak' || s.durum === 'gonderildi') && (
                        <Button size="sm" variant="outline" className="gap-1 !bg-transparent" disabled={mesgul} onClick={() => void gonder(s)}
                          data-testid={`sozlesme-gonder-${s.id}`}>
                          <Send className="h-3.5 w-3.5" aria-hidden="true" />
                          {s.durum === 'taslak' ? t('sozlesme.yonetim.gonder') : t('sozlesme.yonetim.yenidenGonder')}
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="gap-1" disabled={mesgul}
                        onClick={() => void calistir(async () => { await pdfIndir(yoneticiSozlesmePdf(s.id), `sozlesme-${s.no}-v${s.surum}.pdf`); })}
                        data-testid={`sozlesme-pdf-${s.id}`}>
                        <FileDown className="h-3.5 w-3.5" aria-hidden="true" />PDF
                      </Button>
                      {s.surum > 1 || s.kok_id !== s.id ? (
                        <Button size="sm" variant="ghost" className="gap-1"
                          onClick={() => void sozlesmeSurumleri(s.id).then((l) => setSurumler({ id: s.id, liste: l })).catch(hata)}>
                          <History className="h-3.5 w-3.5" aria-hidden="true" />{t('sozlesme.yonetim.surumler')}
                        </Button>
                      ) : null}
                      {s.durum !== 'iptal' && (
                        <Button size="sm" variant="ghost" className="gap-1 text-amber-300" disabled={mesgul}
                          onClick={() => window.confirm(t('sozlesme.yonetim.iptalOnay', { no: s.no })) && void calistir(async () => { await sozlesmeIptal(s.id); })}>
                          <Ban className="h-3.5 w-3.5" aria-hidden="true" />{t('sozlesme.yonetim.iptal')}
                        </Button>
                      )}
                      {s.durum !== 'imzalandi' && !s.imza_at && (
                        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" disabled={mesgul} aria-label={t('sozlesme.sil')}
                          onClick={() => window.confirm(t('sozlesme.yonetim.silOnay', { no: s.no })) && void calistir(async () => { await sozlesmeSil(s.id); })}>
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        </Button>
                      )}
                    </div>
                    {surumler?.id === s.id && (
                      <ul className="mt-2 space-y-1 rounded-lg border border-white/10 p-2 text-xs">
                        {surumler.liste.map((v) => (
                          <li key={v.id}>
                            v{v.surum} · {t(`sozlesme.durum.${v.durum}`, { defaultValue: v.durum })}
                            {v.imza_at ? ` · ${tarihBicimle(v.imza_at, dil, true)}` : ''}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
