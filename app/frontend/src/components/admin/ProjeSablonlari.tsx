import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowDown, ArrowUp, Copy, FolderPlus, LayoutTemplate, Loader2, Pencil, Plus, Rocket, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  ZamanHatasi,
  bugunYerel,
  gunEkle,
  projedenSablon,
  sablonEkle,
  sablonGuncelle,
  sablonSil,
  sablondanProje,
  sablonlariGetir,
  secenekleriGetir,
  tarihGoster,
  type ProjeSablonu,
  type SablonGorevi,
  type SablondanProje,
} from '@/lib/zamanTakibi';

const SECIM =
  'h-9 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';
const KART = 'cam-kart min-w-0 rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-6';
const ETIKET = 'mb-1 block text-xs text-muted-foreground';

const bosGorev = (): SablonGorevi => ({
  baslik: '',
  aciklama: '',
  asama: '',
  baslangic_gun: 0,
  sure_gun: 1,
  kontrol_listesi: [],
  atanan_eposta: '',
  atanan_rol: '',
  musteriye_gorunur: false,
  kilometre_tasi: false,
  tahmini_saat: null,
});

function gorevTarihleri(baslangic: string, g: SablonGorevi): [string, string] {
  const bas = gunEkle(baslangic, Number(g.baslangic_gun) || 0);
  return [bas, gunEkle(bas, Math.max(1, Number(g.sure_gun) || 1) - 1)];
}

interface Props {
  /** Şablondan proje oluşunca (yönetici paneli proje listesini yenilesin). */
  onProjeOlustu?: () => void;
}

/**
 * Yönetici › Proje şablonları (Faz 3Z): hazır görev planları, şablondan proje
 * (görev tarihleri başlangıç gününe göre), projeden şablon kaydetme.
 */
export default function ProjeSablonlari({ onProjeOlustu }: Props) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<ProjeSablonu[] | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<ProjeSablonu | 'yeni' | null>(null);
  const [olusturulan, setOlusturulan] = useState<ProjeSablonu | null>(null);
  const [projeler, setProjeler] = useState<{ id: number; baslik: string }[]>([]);
  const [kaynakProje, setKaynakProje] = useState('');

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof ZamanHatasi ? h.kod : 'genel';
      toast.error(t(`projeSablonlari.hata.${kod}`, { defaultValue: t('projeSablonlari.hata.genel') }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    try {
      setListe(await sablonlariGetir());
    } catch {
      toast.error(t('projeSablonlari.hata.yuklenemedi'));
      setListe([]);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
    secenekleriGetir()
      .then((s) => setProjeler(s.projeler))
      .catch(() => setProjeler([]));
  }, [yukle]);

  const sil = async (s: ProjeSablonu) => {
    if (!confirm(t('projeSablonlari.silOnay', { ad: s.ad }))) return;
    try {
      await sablonSil(s.id);
      toast.success(t('projeSablonlari.silindi'));
      void yukle();
    } catch (h) {
      hata(h);
    }
  };

  const projedenKaydet = async () => {
    if (!kaynakProje) {
      toast.error(t('projeSablonlari.projeSec'));
      return;
    }
    try {
      const s = await projedenSablon(Number(kaynakProje));
      toast.success(t('projeSablonlari.kaydedildi'));
      setKaynakProje('');
      await yukle();
      setDuzenlenen(s);
    } catch (h) {
      hata(h);
    }
  };

  return (
    <section className="min-w-0 space-y-5" data-testid="proje-sablonlari">
      <div>
        <h2 className="flex items-center gap-2 text-xl font-semibold">
          <LayoutTemplate className="h-5 w-5 text-purple-300" aria-hidden="true" /> {t('projeSablonlari.baslik')}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('projeSablonlari.aciklama')}</p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Button type="button" size="sm" onClick={() => { setDuzenlenen('yeni'); setOlusturulan(null); }} className="gap-1.5" data-testid="sablon-yeni">
          <Plus className="h-4 w-4" aria-hidden="true" /> {t('projeSablonlari.yeni')}
        </Button>
        <div className="ms-auto flex min-w-0 flex-wrap items-center gap-2">
          <select value={kaynakProje} onChange={(e) => setKaynakProje(e.target.value)} className={`${SECIM} w-auto min-w-0 max-w-[16rem]`} aria-label={t('projeSablonlari.projeSec')} data-testid="sablon-kaynak-proje">
            <option value="">{t('projeSablonlari.projeSec')}</option>
            {projeler.map((p) => <option key={p.id} value={p.id}>{p.baslik}</option>)}
          </select>
          <Button type="button" size="sm" variant="outline" onClick={() => void projedenKaydet()} className="gap-1.5 !bg-transparent" data-testid="sablon-projeden">
            <Copy className="h-4 w-4" aria-hidden="true" /> {t('projeSablonlari.projedenKaydet')}
          </Button>
        </div>
      </div>

      {duzenlenen && (
        <SablonFormu
          sablon={duzenlenen === 'yeni' ? null : duzenlenen}
          onBitti={(kaydedildi) => {
            setDuzenlenen(null);
            if (kaydedildi) void yukle();
          }}
          hata={hata}
        />
      )}

      {olusturulan && (
        <ProjeOlusturFormu
          sablon={olusturulan}
          onKapat={() => setOlusturulan(null)}
          onOlustu={() => onProjeOlustu?.()}
          hata={hata}
        />
      )}

      {!liste ? (
        <div className="flex justify-center py-10 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
      ) : liste.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t('projeSablonlari.bos')}</p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="sablon-listesi">
          {liste.map((s) => (
            <li key={s.id} className={`${KART} flex flex-col gap-3`} data-testid={`sablon-${s.id}`}>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="break-words font-semibold">{s.ad}</h3>
                  {s.hazir && <span className="rounded-full bg-purple-500/15 px-2 py-0.5 text-[10px] text-purple-200">{t('projeSablonlari.hazir')}</span>}
                  {s.kategori && <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-muted-foreground">{s.kategori}</span>}
                </div>
                {s.aciklama && <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{s.aciklama}</p>}
                <p className="mt-2 text-xs text-muted-foreground">
                  {s.tahmini_saat
                    ? t('projeSablonlari.ozet', { gorev: s.gorev_sayisi, gun: s.toplam_gun, saat: s.tahmini_saat })
                    : t('projeSablonlari.ozetSaatsiz', { gorev: s.gorev_sayisi, gun: s.toplam_gun })}
                </p>
              </div>
              <div className="mt-auto flex flex-wrap gap-1.5">
                <Button type="button" size="sm" onClick={() => { setOlusturulan(s); setDuzenlenen(null); }} className="gap-1.5" data-testid={`sablon-olustur-${s.id}`}>
                  <Rocket className="h-4 w-4" aria-hidden="true" /> {t('projeSablonlari.olustur.dugme')}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => { setDuzenlenen(s); setOlusturulan(null); }} className="gap-1.5" data-testid={`sablon-duzenle-${s.id}`}>
                  <Pencil className="h-4 w-4" aria-hidden="true" /> {t('projeSablonlari.duzenle')}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => void sil(s)} className="ms-auto text-destructive hover:text-destructive" aria-label={t('projeSablonlari.sil')} data-testid={`sablon-sil-${s.id}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Şablondan proje
// ---------------------------------------------------------------------------
function ProjeOlusturFormu({
  sablon,
  onKapat,
  onOlustu,
  hata,
}: {
  sablon: ProjeSablonu;
  onKapat: () => void;
  onOlustu: () => void;
  hata: (h: unknown) => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [form, setForm] = useState({ baslangic: bugunYerel(), baslik: sablon.ad, eposta: '', ad: '' });
  const [mesgul, setMesgul] = useState(false);
  const [sonuc, setSonuc] = useState<SablondanProje | null>(null);

  const gonder = async (e: FormEvent) => {
    e.preventDefault();
    setMesgul(true);
    try {
      const y = await sablondanProje(sablon.id, {
        baslangic_tarihi: form.baslangic,
        baslik: form.baslik.trim() || undefined,
        client_email: form.eposta.trim() || undefined,
        client_name: form.ad.trim() || undefined,
      });
      setSonuc(y);
      toast.success(t('projeSablonlari.olustur.olustu', { gorev: y.gorev_sayisi }));
      onOlustu();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  return (
    <form onSubmit={gonder} className={`${KART} space-y-4 border-purple-500/30`} data-testid="sablon-proje-formu">
      <div className="flex items-start gap-2">
        <h3 className="me-auto font-semibold">{t('projeSablonlari.olustur.baslik')}: {sablon.ad}</h3>
        <Button type="button" size="sm" variant="ghost" onClick={onKapat} aria-label={t('projeSablonlari.vazgec')}><X className="h-4 w-4" /></Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0">
          <span className={ETIKET}>{t('projeSablonlari.olustur.baslangic')}</span>
          <Input type="date" name="baslangic_tarihi" value={form.baslangic} onChange={(e) => setForm((f) => ({ ...f, baslangic: e.target.value }))} required className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('projeSablonlari.olustur.projeAdi')}</span>
          <Input name="baslik" value={form.baslik} onChange={(e) => setForm((f) => ({ ...f, baslik: e.target.value }))} maxLength={200} className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('projeSablonlari.olustur.musteriEposta')}</span>
          <Input type="email" name="client_email" value={form.eposta} onChange={(e) => setForm((f) => ({ ...f, eposta: e.target.value }))} className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('projeSablonlari.olustur.musteriAdi')}</span>
          <Input name="client_name" value={form.ad} onChange={(e) => setForm((f) => ({ ...f, ad: e.target.value }))} maxLength={200} className="h-9 bg-white/5 border-white/10" />
        </label>
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold text-muted-foreground">{t('projeSablonlari.olustur.onizleme')}</p>
        <ol className="max-h-72 space-y-1 overflow-y-auto pe-1 text-sm" data-testid="sablon-onizleme">
          {(sonuc ? sonuc.gorevler.map((g) => ({ baslik: g.baslik, bas: g.baslangic_tarihi || '', bit: g.bitis_tarihi || '', gorunur: g.musteriye_gorunur }))
            : sablon.gorevler.map((g) => {
              const [bas, bit] = gorevTarihleri(form.baslangic || bugunYerel(), g);
              return { baslik: g.baslik, bas, bit, gorunur: g.musteriye_gorunur };
            })
          ).map((g, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-2 rounded-lg bg-white/[0.03] px-2 py-1.5" data-testid={sonuc ? `sablon-sonuc-gorev-${i}` : undefined}>
              <span className="min-w-0 flex-1 break-words">{g.baslik}</span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {g.bas === g.bit ? tarihGoster(g.bas, dil) : `${tarihGoster(g.bas, dil)} – ${tarihGoster(g.bit, dil)}`}
              </span>
            </li>
          ))}
        </ol>
      </div>
      {sonuc ? (
        <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm" data-testid="sablon-sonuc">
          {t('projeSablonlari.olustur.olustu', { gorev: sonuc.gorev_sayisi })}{' '}
          <Link to={{ search: '?sekme=projects' }} className="font-medium text-emerald-200 underline underline-offset-2">
            {t('projeSablonlari.olustur.projelereGit')}
          </Link>
        </div>
      ) : (
        <Button type="submit" size="sm" disabled={mesgul} className="gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 text-white border-0" data-testid="sablon-proje-olustur">
          <FolderPlus className="h-4 w-4" aria-hidden="true" /> {t('projeSablonlari.olustur.dugme')}
        </Button>
      )}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Şablon düzenleyici
// ---------------------------------------------------------------------------
function SablonFormu({
  sablon,
  onBitti,
  hata,
}: {
  sablon: ProjeSablonu | null;
  onBitti: (kaydedildi: boolean) => void;
  hata: (h: unknown) => void;
}) {
  const { t } = useTranslation();
  const [ad, setAd] = useState(sablon?.ad || '');
  const [aciklama, setAciklama] = useState(sablon?.aciklama || '');
  const [kategori, setKategori] = useState(sablon?.kategori || '');
  const [saat, setSaat] = useState(sablon?.tahmini_saat != null ? String(sablon.tahmini_saat) : '');
  const [gorevler, setGorevler] = useState<SablonGorevi[]>(sablon?.gorevler.length ? sablon.gorevler.map((g) => ({ ...g })) : [bosGorev()]);
  const [mesgul, setMesgul] = useState(false);

  const guncelle = (i: number, alan: Partial<SablonGorevi>) => setGorevler((l) => l.map((g, j) => (j === i ? { ...g, ...alan } : g)));
  const tasi = (i: number, yon: -1 | 1) =>
    setGorevler((l) => {
      const j = i + yon;
      if (j < 0 || j >= l.length) return l;
      const y = [...l];
      [y[i], y[j]] = [y[j], y[i]];
      return y;
    });

  const kaydet = async (e: FormEvent) => {
    e.preventDefault();
    if (!ad.trim()) {
      toast.error(t('projeSablonlari.hata.ad_gerekli'));
      return;
    }
    const temiz = gorevler
      .filter((g) => g.baslik.trim())
      .map((g) => ({
        ...g,
        baslik: g.baslik.trim(),
        asama: (g.asama || '').trim() || null,
        aciklama: (g.aciklama || '').trim() || null,
        atanan_eposta: (g.atanan_eposta || '').trim() || null,
        atanan_rol: (g.atanan_rol || '').trim() || null,
        baslangic_gun: Math.max(0, Number(g.baslangic_gun) || 0),
        sure_gun: Math.max(1, Number(g.sure_gun) || 1),
        tahmini_saat: g.tahmini_saat === null || g.tahmini_saat === undefined || String(g.tahmini_saat) === '' ? null : Number(g.tahmini_saat),
      }));
    const govde = {
      ad: ad.trim(),
      aciklama: aciklama.trim() || null,
      kategori: kategori.trim() || null,
      tahmini_saat: saat.trim() ? Number(saat.replace(',', '.')) : null,
      gorevler: temiz,
    };
    setMesgul(true);
    try {
      if (sablon) await sablonGuncelle(sablon.id, govde);
      else await sablonEkle(govde);
      toast.success(t('projeSablonlari.kaydedildi'));
      onBitti(true);
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  return (
    <form onSubmit={kaydet} className={`${KART} space-y-4 border-purple-500/30`} data-testid="sablon-formu">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0 sm:col-span-2">
          <span className={ETIKET}>{t('projeSablonlari.alan.ad')}</span>
          <Input name="ad" value={ad} onChange={(e) => setAd(e.target.value)} maxLength={200} required className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('projeSablonlari.alan.kategori')}</span>
          <Input name="kategori" value={kategori} onChange={(e) => setKategori(e.target.value)} maxLength={60} className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0">
          <span className={ETIKET}>{t('projeSablonlari.alan.tahminiSaat')}</span>
          <Input name="tahmini_saat" value={saat} onChange={(e) => setSaat(e.target.value)} inputMode="decimal" className="h-9 bg-white/5 border-white/10" />
        </label>
        <label className="min-w-0 sm:col-span-2 lg:col-span-4">
          <span className={ETIKET}>{t('projeSablonlari.alan.aciklama')}</span>
          <textarea name="aciklama" value={aciklama} onChange={(e) => setAciklama(e.target.value)} rows={2} maxLength={4000}
            className="w-full rounded-md border border-white/10 bg-white/5 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40" />
        </label>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-semibold">{t('projeSablonlari.alan.gorevler')}</p>
        <ol className="space-y-2">
          {gorevler.map((g, i) => (
            <li key={i} className="space-y-2 rounded-xl border border-white/10 bg-white/[0.02] p-3" data-testid={`sablon-gorev-${i}`}>
              <div className="grid gap-2 sm:grid-cols-6">
                <label className="min-w-0 sm:col-span-3">
                  <span className={ETIKET}>{t('projeSablonlari.alan.baslik')}</span>
                  <Input name={`gorev-baslik-${i}`} value={g.baslik} onChange={(e) => guncelle(i, { baslik: e.target.value })} maxLength={200} className="h-9 bg-white/5 border-white/10" />
                </label>
                <label className="min-w-0">
                  <span className={ETIKET}>{t('projeSablonlari.alan.asama')}</span>
                  <Input name={`gorev-asama-${i}`} value={g.asama || ''} onChange={(e) => guncelle(i, { asama: e.target.value })} maxLength={30} className="h-9 bg-white/5 border-white/10" />
                </label>
                <label className="min-w-0">
                  <span className={ETIKET}>{t('projeSablonlari.alan.baslangicGun')}</span>
                  <Input type="number" min={0} name={`gorev-gun-${i}`} value={g.baslangic_gun} onChange={(e) => guncelle(i, { baslangic_gun: Number(e.target.value) })} className="h-9 bg-white/5 border-white/10" />
                </label>
                <label className="min-w-0">
                  <span className={ETIKET}>{t('projeSablonlari.alan.sureGun')}</span>
                  <Input type="number" min={1} name={`gorev-sure-${i}`} value={g.sure_gun} onChange={(e) => guncelle(i, { sure_gun: Number(e.target.value) })} className="h-9 bg-white/5 border-white/10" />
                </label>
              </div>
              <div className="grid gap-2 sm:grid-cols-6">
                <label className="min-w-0 sm:col-span-3">
                  <span className={ETIKET}>{t('projeSablonlari.alan.kontrol')}</span>
                  <textarea value={g.kontrol_listesi.join('\n')} rows={2}
                    onChange={(e) => guncelle(i, { kontrol_listesi: e.target.value.split('\n') })}
                    className="w-full rounded-md border border-white/10 bg-white/5 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40" />
                </label>
                <label className="min-w-0 sm:col-span-2">
                  <span className={ETIKET}>{t('projeSablonlari.alan.atananEposta')}</span>
                  <Input type="email" value={g.atanan_eposta || ''} onChange={(e) => guncelle(i, { atanan_eposta: e.target.value })} className="h-9 bg-white/5 border-white/10" />
                  <Input value={g.atanan_rol || ''} onChange={(e) => guncelle(i, { atanan_rol: e.target.value })} placeholder={t('projeSablonlari.alan.atananRol')}
                    aria-label={t('projeSablonlari.alan.atananRol')} maxLength={40} className="mt-1 h-9 bg-white/5 border-white/10" />
                </label>
                <label className="min-w-0">
                  <span className={ETIKET}>{t('projeSablonlari.alan.tahmini')}</span>
                  <Input value={g.tahmini_saat ?? ''} inputMode="decimal"
                    onChange={(e) => guncelle(i, { tahmini_saat: e.target.value === '' ? null : Number(e.target.value.replace(',', '.')) })}
                    className="h-9 bg-white/5 border-white/10" />
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <label className="inline-flex items-center gap-2">
                  <input type="checkbox" checked={g.musteriye_gorunur} onChange={(e) => guncelle(i, { musteriye_gorunur: e.target.checked })} className="h-4 w-4 accent-purple-500" />
                  {t('projeSablonlari.alan.gorunur')}
                </label>
                <label className="inline-flex items-center gap-2">
                  <input type="checkbox" checked={g.kilometre_tasi} onChange={(e) => guncelle(i, { kilometre_tasi: e.target.checked })} className="h-4 w-4 accent-purple-500" />
                  {t('projeSablonlari.alan.kilometre')}
                </label>
                <div className="ms-auto flex gap-1">
                  <Button type="button" size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => tasi(i, -1)} disabled={i === 0} aria-label={t('projeSablonlari.yukari')}><ArrowUp className="h-4 w-4" /></Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => tasi(i, 1)} disabled={i === gorevler.length - 1} aria-label={t('projeSablonlari.asagi')}><ArrowDown className="h-4 w-4" /></Button>
                  <Button type="button" size="sm" variant="ghost" className="h-8 w-8 p-0 text-destructive hover:text-destructive" onClick={() => setGorevler((l) => l.filter((_, j) => j !== i))} aria-label={t('projeSablonlari.gorevSil')}><Trash2 className="h-4 w-4" /></Button>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <Button type="button" size="sm" variant="outline" onClick={() => setGorevler((l) => [...l, { ...bosGorev(), baslangic_gun: l.length ? (Number(l[l.length - 1].baslangic_gun) || 0) + (Number(l[l.length - 1].sure_gun) || 1) : 0 }])}
          className="gap-1.5 !bg-transparent" data-testid="sablon-gorev-ekle">
          <Plus className="h-4 w-4" aria-hidden="true" /> {t('projeSablonlari.gorevEkle')}
        </Button>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={() => onBitti(false)}>{t('projeSablonlari.vazgec')}</Button>
        <Button type="submit" size="sm" disabled={mesgul} data-testid="sablon-kaydet">{t('projeSablonlari.kaydet')}</Button>
      </div>
    </form>
  );
}
