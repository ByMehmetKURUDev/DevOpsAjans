import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CreditCard,
  FileCheck2,
  FileDown,
  FileSignature,
  Loader2,
  Paperclip,
  Receipt,
  Wallet,
  XCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import ImzaTuvali from '@/components/belge/ImzaTuvali';
import KalemTablosu from '@/components/belge/KalemTablosu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { BelgeHatasi, paraBicimle, pdfDili, pdfIndir, tarihBicimle } from '@/lib/belge';
import { adresiIndir } from '@/lib/dosyalar';
import {
  faturaDurumRengi,
  faturalarim,
  faturamAyrinti,
  faturamDekont,
  faturamOdemeBaglantisi,
  faturamPdf,
  type FaturaAyrintisi,
  type FaturaSatiri,
} from '@/lib/faturaIslemleri';
import { cuzdanim, faturamiBakiyedenOde, istekAnahtari, type MusteriCuzdani } from '@/lib/cuzdan';
import { sozlesmeDurumRengi, sozlesmelerim, sozlesmemImza, sozlesmemPdf, type Sozlesme } from '@/lib/sozlesmeler';
import { teklifDurumRengi, teklifimKarar, teklifimPdf, tekliflerim, type Teklif } from '@/lib/teklifler';

/** Faz 5C — "Bakiyem" (ayrı parça; metinler `cuzdan` ek paketinde, Faturalar sekmesiyle birlikte yükleniyor). */
const Bakiyem = lazy(() => import('@/components/cuzdan/Bakiyem'));

/**
 * Müşteri paneli › Faturalar sekmesi (Faz 3T): teklifler (karar), sözleşmeler
 * (oku + basit elektronik imza), faturalar (kalan bakiye, ödemeler, dekont, PDF,
 * kalan için ödeme). `faturalar` izni; teklif/sözleşme modülü kapalıysa o
 * bölüm sessizce gizleniyor. Metinler `fatura`, `teklif`, `sozlesme` ek paketlerinde.
 */
export default function Faturalarim() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [teklifler, setTeklifler] = useState<Teklif[]>([]);
  const [sozlesmeler, setSozlesmeler] = useState<Sozlesme[]>([]);
  const [faturalar, setFaturalar] = useState<FaturaSatiri[]>([]);
  const [ozet, setOzet] = useState<{ para_birimi: string; kalan: number; adet: number }[]>([]);
  const [cuzdan, setCuzdan] = useState<MusteriCuzdani | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hataVar, setHataVar] = useState(false);

  const hataGoster = useCallback(
    (h: unknown, paket = 'fatura') => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`${paket}.hata.${kod}`, { defaultValue: t(`${paket}.hata.genel`) }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHataVar(false);
    const [tk, sz, ft, cz] = await Promise.allSettled([tekliflerim(), sozlesmelerim(), faturalarim(), cuzdanim()]);
    setCuzdan(cz.status === 'fulfilled' ? cz.value : null);
    setTeklifler(tk.status === 'fulfilled' ? tk.value : []);
    setSozlesmeler(sz.status === 'fulfilled' ? sz.value : []);
    if (ft.status === 'fulfilled') {
      setFaturalar(ft.value.faturalar);
      setOzet(ft.value.ozet);
    } else setHataVar(true);
    setYukleniyor(false);
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (yukleniyor) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    );
  }

  /** Faz 5C — faturanın para birimindeki bakiye (dönüşüm yok). */
  const bakiyeOf = (pb: string) => cuzdan?.bakiyeler.find((b) => b.para_birimi === (pb || 'TRY'))?.bakiye ?? 0;
  /** Bakiyeden ödemeden sonra yalnız veriyi yenile (sekme iskeleti yerinde kalsın). */
  const sessizYukle = async () => {
    const [ft, cz] = await Promise.allSettled([faturalarim(), cuzdanim()]);
    if (ft.status === 'fulfilled') {
      setFaturalar(ft.value.faturalar);
      setOzet(ft.value.ozet);
    }
    if (cz.status === 'fulfilled') setCuzdan(cz.value);
  };

  return (
    <div className="space-y-8" data-testid="faturalarim">
      {cuzdan && (
        <Suspense fallback={null}>
          <Bakiyem ozet={cuzdan} onDegisti={() => void sessizYukle()} />
        </Suspense>
      )}

      {teklifler.length > 0 && (
        <section data-testid="tekliflerim">
          <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold">
            <FileCheck2 className="h-5 w-5 text-purple-300" aria-hidden="true" />{t('teklif.musteri.baslik')}
          </h3>
          <div className="grid gap-3">
            {teklifler.map((tk) => <TeklifKarti key={tk.id} teklif={tk} onDegisti={yukle} hataGoster={hataGoster} />)}
          </div>
        </section>
      )}

      {sozlesmeler.length > 0 && (
        <section data-testid="sozlesmelerim">
          <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold">
            <FileSignature className="h-5 w-5 text-purple-300" aria-hidden="true" />{t('sozlesme.musteri.baslik')}
          </h3>
          <div className="grid gap-3">
            {sozlesmeler.map((s) => <SozlesmeKarti key={s.id} sozlesme={s} onDegisti={yukle} hataGoster={hataGoster} />)}
          </div>
        </section>
      )}

      <section data-testid="faturalar-listesi">
        <h3 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <Receipt className="h-5 w-5 text-purple-300" aria-hidden="true" />{t('fatura.musteri.baslik')}
        </h3>
        {ozet.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-3" data-testid="fatura-ozet">
            {ozet.map((o) => (
              <div key={o.para_birimi} className="cam-kart rounded-xl border border-orange-500/20 bg-orange-500/10 px-4 py-2 text-sm">
                {t('fatura.musteri.toplamKalan', { sayi: o.adet })}: <span className="font-bold">{paraBicimle(o.kalan, o.para_birimi, dil)}</span>
              </div>
            ))}
          </div>
        )}
        {hataVar ? (
          <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-center text-muted-foreground">{t('fatura.hata.genel')}</div>
        ) : faturalar.length === 0 ? (
          <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-10 text-center text-muted-foreground">{t('fatura.musteri.bos')}</div>
        ) : (
          <div className="grid gap-3">
            {faturalar.map((f) => (
              <FaturaKarti key={f.id} fatura={f} hataGoster={hataGoster} bakiye={bakiyeOf(f.currency)} onOdendi={() => void sessizYukle()} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TeklifKarti({ teklif, onDegisti, hataGoster }: { teklif: Teklif; onDegisti: () => void; hataGoster: (h: unknown, p?: string) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [acik, setAcik] = useState(false);
  const [karar, setKarar] = useState<'kabul' | 'red' | null>(null);
  const [ad, setAd] = useState('');
  const [neden, setNeden] = useState('');
  const [mesgul, setMesgul] = useState(false);

  const gonder = async () => {
    if (!karar) return;
    setMesgul(true);
    try {
      await teklifimKarar(teklif.id, karar === 'kabul' ? { sonuc: 'kabul', ad_soyad: ad } : { sonuc: 'red', not: neden });
      toast.success(karar === 'kabul' ? t('teklif.sonuc.kabul') : t('teklif.sonuc.red'));
      onDegisti();
    } catch (h) {
      hataGoster(h, 'teklif');
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid={`teklifim-${teklif.id}`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold">{teklif.no}</span>
            <span className={`rounded-full border px-2 py-0.5 text-xs ${teklifDurumRengi(teklif.durum)}`}>
              {t(`teklif.durum.${teklif.durum}`, { defaultValue: teklif.durum })}
            </span>
          </div>
          <p className="mt-1 break-words font-medium">{teklif.baslik}</p>
          {teklif.gecerlilik && <p className="text-xs text-muted-foreground">{t('teklif.gecerlilik', { tarih: tarihBicimle(teklif.gecerlilik, dil) })}</p>}
        </div>
        <p className="text-xl font-bold tabular-nums">{paraBicimle(teklif.ozet.genel_toplam, teklif.para_birimi, dil)}</p>
        <Button size="sm" variant="ghost" className="gap-1" onClick={() => setAcik(!acik)} aria-expanded={acik}>
          {acik ? <ChevronUp className="h-4 w-4" aria-hidden="true" /> : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
          {t('teklif.incele')}
        </Button>
      </div>
      {acik && (
        <div className="mt-4 space-y-4">
          <KalemTablosu kalemler={teklif.kalemler} ozet={teklif.ozet} paraBirimi={teklif.para_birimi} />
          {teklif.notlar && <p className="whitespace-pre-line text-sm text-muted-foreground">{teklif.notlar}</p>}
          {teklif.sartlar && (
            <div className="rounded-xl border border-white/10 p-3 text-sm">
              <p className="mb-1 font-semibold">{t('teklif.sartlar')}</p>
              <p className="whitespace-pre-line text-muted-foreground">{teklif.sartlar}</p>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="gap-1 !bg-transparent"
              onClick={() => void pdfIndir(teklifimPdf(teklif.id, pdfDili(dil)), `teklif-${teklif.no}.pdf`).catch((h) => hataGoster(h, 'teklif'))}>
              <FileDown className="h-4 w-4" aria-hidden="true" />{t('teklif.pdfIndir')}
            </Button>
            {teklif.karar_verilebilir && !karar && (
              <>
                <Button size="sm" className="gap-1" onClick={() => setKarar('kabul')} data-testid="teklifim-kabul">
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />{t('teklif.kabulEt')}
                </Button>
                <Button size="sm" variant="ghost" className="gap-1" onClick={() => setKarar('red')}>
                  <XCircle className="h-4 w-4" aria-hidden="true" />{t('teklif.reddet')}
                </Button>
              </>
            )}
          </div>
          {karar && (
            <div className="grid gap-2 rounded-xl border border-white/10 p-3">
              {karar === 'kabul' ? (
                <>
                  <label className="text-sm" htmlFor={`teklif-ad-${teklif.id}`}>{t('teklif.adSoyadEtiket')}</label>
                  <Input id={`teklif-ad-${teklif.id}`} value={ad} maxLength={120} onChange={(e) => setAd(e.target.value)} autoComplete="name" />
                  <p className="text-xs text-muted-foreground">{t('teklif.kabulAciklama')}</p>
                </>
              ) : (
                <>
                  <label className="text-sm" htmlFor={`teklif-neden-${teklif.id}`}>{t('teklif.retNedeni')}</label>
                  <Textarea id={`teklif-neden-${teklif.id}`} value={neden} rows={3} maxLength={2000} onChange={(e) => setNeden(e.target.value)} />
                </>
              )}
              <div className="flex gap-2">
                <Button size="sm" disabled={mesgul || (karar === 'kabul' ? ad.trim().length < 2 : !neden.trim())} onClick={() => void gonder()}>
                  {mesgul && <Loader2 className="me-1 h-4 w-4 animate-spin" aria-hidden="true" />}
                  {karar === 'kabul' ? t('teklif.kabulOnayla') : t('teklif.retOnayla')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setKarar(null)}>{t('teklif.vazgec')}</Button>
              </div>
            </div>
          )}
          {teklif.durum === 'kabul' && teklif.karar_ad && (
            <p className="text-xs text-emerald-300">{t('teklif.kabulBilgisi', { ad: teklif.karar_ad, tarih: tarihBicimle(teklif.karar_at, dil, true) })}</p>
          )}
        </div>
      )}
    </div>
  );
}

function SozlesmeKarti({ sozlesme, onDegisti, hataGoster }: { sozlesme: Sozlesme; onDegisti: () => void; hataGoster: (h: unknown, p?: string) => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [acik, setAcik] = useState(false);
  const [ad, setAd] = useState('');
  const [onay, setOnay] = useState(false);
  const [png, setPng] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const imzala = async () => {
    setMesgul(true);
    try {
      await sozlesmemImza(sozlesme.id, { ad_soyad: ad, onay, metin_ozeti: sozlesme.metin_ozeti, imza_png: png });
      toast.success(t('sozlesme.imza.basarili'));
      onDegisti();
    } catch (h) {
      hataGoster(h, 'sozlesme');
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid={`sozlesmem-${sozlesme.id}`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold">{sozlesme.no}</span>
            <span className="text-xs text-muted-foreground">v{sozlesme.surum}</span>
            <span className={`rounded-full border px-2 py-0.5 text-xs ${sozlesmeDurumRengi(sozlesme.durum)}`}>
              {t(`sozlesme.durum.${sozlesme.durum}`, { defaultValue: sozlesme.durum })}
            </span>
          </div>
          <p className="mt-1 break-words font-medium">{sozlesme.baslik}</p>
          {sozlesme.imza_at && <p className="text-xs text-emerald-300">{t('sozlesme.imzalayanBilgi', { ad: sozlesme.imza_ad, tarih: tarihBicimle(sozlesme.imza_at, dil, true) })}</p>}
        </div>
        <Button size="sm" variant="outline" className="gap-1 !bg-transparent"
          onClick={() => void pdfIndir(sozlesmemPdf(sozlesme.id), `sozlesme-${sozlesme.no}-v${sozlesme.surum}.pdf`).catch((h) => hataGoster(h, 'sozlesme'))}>
          <FileDown className="h-4 w-4" aria-hidden="true" />PDF
        </Button>
        <Button size="sm" variant="ghost" className="gap-1" onClick={() => setAcik(!acik)} aria-expanded={acik}>
          {acik ? <ChevronUp className="h-4 w-4" aria-hidden="true" /> : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
          {t('sozlesme.oku')}
        </Button>
      </div>
      {acik && (
        <div className="mt-4 space-y-4">
          <div className="max-h-[32rem] overflow-y-auto rounded-xl border border-white/10 bg-black/20 p-4" dir="ltr" lang={sozlesme.dil}>
            <GuvenliMarkdown metin={sozlesme.govde} />
          </div>
          {sozlesme.imzalanabilir && (
            <div className="grid gap-3 rounded-xl border border-white/10 p-4">
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={onay} onChange={(e) => setOnay(e.target.checked)} className="mt-0.5 h-4 w-4 accent-purple-500" />
                {t('sozlesme.imza.onayKutusu')}
              </label>
              <Input value={ad} maxLength={120} onChange={(e) => setAd(e.target.value)} placeholder={t('sozlesme.imza.adSoyad')}
                aria-label={t('sozlesme.imza.adSoyad')} autoComplete="name" />
              <p className="text-xs text-muted-foreground">{t('sozlesme.imza.cizimIstegeBagli')}</p>
              <ImzaTuvali onChange={setPng} />
              <Button disabled={mesgul || !onay || ad.trim().length < 2} onClick={() => void imzala()} className="gap-2">
                {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                <FileSignature className="h-4 w-4" aria-hidden="true" />{t('sozlesme.imza.imzala')}
              </Button>
              <p className="text-xs text-muted-foreground">{t('sozlesme.hukukiNot')}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FaturaKarti({ fatura, hataGoster, bakiye = 0, onOdendi }: {
  fatura: FaturaSatiri;
  hataGoster: (h: unknown, p?: string) => void;
  bakiye?: number;
  onOdendi?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [acik, setAcik] = useState(false);
  const [ayrinti, setAyrinti] = useState<FaturaAyrintisi | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const kalan = fatura.bakiye?.kalan ?? 0;
  const odenebilir = fatura.tur !== 'iade' && kalan > 0 && !['paid', 'cancelled', 'iade'].includes(fatura.status || '');
  // Faz 5C — "Bakiyeden öde": faturanın para birimindeki bakiyeden tamamı ya da girilen kısım (istek anahtarı tekrarı önler).
  const [bakiyeAcik, setBakiyeAcik] = useState(false);
  const [bakiyeTutar, setBakiyeTutar] = useState('');
  const anahtar = useRef(istekAnahtari());
  const bakiyedenOdenebilir = odenebilir && bakiye > 0;
  const bakiyedenOde = async () => {
    setMesgul(true);
    try {
      const s = await faturamiBakiyedenOde(fatura.id, bakiyeTutar, anahtar.current);
      anahtar.current = istekAnahtari();
      toast.success(s.tekrar ? t('cuzdan.ode.tekrar') : t('cuzdan.ode.basarili'));
      setBakiyeAcik(false);
      onOdendi?.();
    } catch (h) {
      hataGoster(h, 'cuzdan');
    } finally {
      setMesgul(false);
    }
  };

  const ac = async () => {
    const yeni = !acik;
    setAcik(yeni);
    if (yeni && !ayrinti) {
      try {
        setAyrinti(await faturamAyrinti(fatura.id));
      } catch (h) {
        hataGoster(h);
      }
    }
  };

  const ode = async () => {
    setMesgul(true);
    try {
      const adres = fatura.odeme_adresi || (await faturamOdemeBaglantisi(fatura.id)).adres;
      window.location.assign(adres);
    } catch (h) {
      hataGoster(h);
      setMesgul(false);
    }
  };

  return (
    <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid={`faturam-${fatura.id}`}>
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-[200px] flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="font-semibold">{fatura.invoice_no}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${faturaDurumRengi(fatura.status)}`} data-testid="faturam-durum">
              {t(`fatura.durum.${fatura.status || 'unpaid'}`, { defaultValue: fatura.status || '' })}
            </span>
          </div>
          {fatura.description && <p className="text-sm text-muted-foreground">{fatura.description}</p>}
          <p className="mt-1 text-xs text-muted-foreground">
            {t('fatura.musteri.duzenleme')}: {tarihBicimle(fatura.issue_date, dil)} • {t('fatura.musteri.vade')}: {tarihBicimle(fatura.due_date, dil)}
          </p>
        </div>
        <div className="text-end">
          <p className="text-2xl font-bold tabular-nums gradient-text">{paraBicimle(fatura.amount, fatura.currency, dil)}</p>
          {fatura.bakiye && fatura.bakiye.odenen > 0 && kalan > 0 && (
            <p className="text-xs text-orange-300" data-testid="faturam-kalan">{t('fatura.musteri.kalan', { tutar: paraBicimle(kalan, fatura.currency, dil) })}</p>
          )}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {odenebilir && (
          <Button size="sm" className="gap-1" disabled={mesgul} onClick={() => void ode()} data-testid="faturam-ode">
            <CreditCard className="h-4 w-4" aria-hidden="true" />{t('fatura.musteri.ode')}
          </Button>
        )}
        {bakiyedenOdenebilir && (
          <Button size="sm" variant="outline" className="gap-1 !bg-transparent" disabled={mesgul} data-testid="faturam-bakiyeden-ode"
            aria-expanded={bakiyeAcik}
            onClick={() => {
              setBakiyeTutar(Math.min(bakiye, kalan).toFixed(2));
              setBakiyeAcik(!bakiyeAcik);
            }}>
            <Wallet className="h-4 w-4" aria-hidden="true" />{t('cuzdan.ode.dugme')}
          </Button>
        )}
        <Button size="sm" variant="outline" className="gap-1 !bg-transparent" data-testid="faturam-pdf"
          onClick={() => void pdfIndir(faturamPdf(fatura.id, pdfDili(dil)), `fatura-${fatura.invoice_no}.pdf`).catch((h) => hataGoster(h))}>
          <FileDown className="h-4 w-4" aria-hidden="true" />PDF
        </Button>
        <Button size="sm" variant="ghost" className="gap-1" onClick={() => void ac()} aria-expanded={acik}>
          {acik ? <ChevronUp className="h-4 w-4" aria-hidden="true" /> : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
          {t('fatura.musteri.ayrinti')}
        </Button>
      </div>
      {bakiyeAcik && bakiyedenOdenebilir && (
        <form className="mt-3 flex flex-wrap items-end gap-3 rounded-xl border border-purple-400/30 bg-purple-500/[0.05] p-3" data-testid="bakiyeden-ode-formu"
          onSubmit={(e) => {
            e.preventDefault();
            void bakiyedenOde();
          }}>
          <div className="min-w-0 text-xs text-muted-foreground">
            <p>{t('cuzdan.ode.kullanilabilir', { tutar: paraBicimle(bakiye, fatura.currency, dil) })}</p>
            <p>{t('cuzdan.ode.kalan', { tutar: paraBicimle(kalan, fatura.currency, dil) })}</p>
          </div>
          <label className="grid gap-1 text-xs">{t('cuzdan.ode.tutar')}
            <Input type="number" min={0.01} step="0.01" max={Math.min(bakiye, kalan)} required value={bakiyeTutar}
              onChange={(e) => setBakiyeTutar(e.target.value)} className="w-36" data-testid="bakiyeden-ode-tutar" />
          </label>
          <Button type="submit" size="sm" disabled={mesgul || !bakiyeTutar} className="gap-1" data-testid="bakiyeden-ode-onayla">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}{t('cuzdan.ode.onayla')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setBakiyeAcik(false)}>{t('cuzdan.vazgec')}</Button>
        </form>
      )}
      {acik && ayrinti && (
        <div className="mt-4 space-y-4">
          {ayrinti.kalemler.length > 0 && <KalemTablosu kalemler={ayrinti.kalemler} ozet={ayrinti.ozet} paraBirimi={ayrinti.currency} />}
          {ayrinti.bakiye && (
            <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
              <div><dt className="text-xs text-muted-foreground">{t('fatura.bakiye.odenen')}</dt><dd className="tabular-nums">{paraBicimle(ayrinti.bakiye.odenen, ayrinti.currency, dil)}</dd></div>
              {ayrinti.bakiye.iade_toplam > 0 && <div><dt className="text-xs text-muted-foreground">{t('fatura.bakiye.iade')}</dt><dd className="tabular-nums">{paraBicimle(ayrinti.bakiye.iade_toplam, ayrinti.currency, dil)}</dd></div>}
              <div><dt className="text-xs text-muted-foreground">{t('fatura.bakiye.kalan')}</dt><dd className="font-semibold tabular-nums">{paraBicimle(Math.max(ayrinti.bakiye.kalan, 0), ayrinti.currency, dil)}</dd></div>
            </dl>
          )}
          {ayrinti.odemeler.length > 0 && (
            <ul className="divide-y divide-white/5 text-sm">
              {ayrinti.odemeler.map((o) => (
                <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>{tarihBicimle(o.odeme_tarihi || o.odendi_at, dil)} · {t(`fatura.yontem.${o.saglayici}`, { defaultValue: o.yontem_etiketi || '—' })}
                    {o.durum === 'iade' && <span className="ms-1 text-amber-300">({t('fatura.ayrinti.geriOdeme')})</span>}</span>
                  <span className="flex items-center gap-1">
                    <span className="tabular-nums">{o.durum === 'iade' ? '−' : ''}{paraBicimle(o.tutar, ayrinti.currency, dil)}</span>
                    {o.dekont_var && (
                      <Button size="sm" variant="ghost" aria-label={t('fatura.ayrinti.dekont')}
                        onClick={() => void faturamDekont(fatura.id, o.id).then((d) => adresiIndir(d.adres)).catch((h) => hataGoster(h))}>
                        <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
                      </Button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {ayrinti.notlar && <p className="whitespace-pre-line text-xs text-muted-foreground">{ayrinti.notlar}</p>}
          <p className="text-xs text-muted-foreground">{t('fatura.musteri.eFaturaNotu')}</p>
        </div>
      )}
    </div>
  );
}
