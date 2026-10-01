import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ChevronDown, ChevronUp, FileDown, Loader2, Paperclip, Pencil, Trash2, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import KalemDuzenleyici from '@/components/belge/KalemDuzenleyici';
import KalemTablosu from '@/components/belge/KalemTablosu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BelgeHatasi, bosKalem, bugunIso, paraBicimle, pdfDili, pdfIndir, tarihBicimle, type Kalem } from '@/lib/belge';
import { adresiIndir } from '@/lib/dosyalar';
import {
  ODEME_YONTEMLERI,
  dekontAdresi,
  faturaAyrintisi,
  faturaDurumRengi,
  faturaKalemleriniYaz,
  iadeKes,
  odemeEkle,
  odemeSil,
  yoneticiFaturaPdf,
  type FaturaAyrintisi,
} from '@/lib/faturaIslemleri';

/**
 * Yönetici › Faturalar satırındaki "Ayrıntı" (Faz 3T): kalemler + KDV dökümü,
 * kısmi ödeme ekle/sil (dekont dosya deposuna), iade faturası, bakiye, PDF.
 * Satır başına çiziliyor ama yalnız açılınca veri çekiyor. Metinler `fatura`
 * (+ kalem tablosu için `teklif`) ek paketinde.
 */
/**
 * Açık ayrıntılar: ödeme sonrası liste yenilenirken (yükleniyor → yeniden çizim)
 * bileşen yeniden kurulsa da ayrıntı açık kalsın.
 */
const ACIK_FATURALAR = new Set<number>();

export default function FaturaAyrinti({ faturaId, onDegisti }: { faturaId: number; onDegisti?: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [acik, setAcik] = useState(() => ACIK_FATURALAR.has(faturaId));
  const [veri, setVeri] = useState<FaturaAyrintisi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [kalemDuzen, setKalemDuzen] = useState<Kalem[] | null>(null);
  const [odeme, setOdeme] = useState({ tutar: '', yontem: 'havale', tarih: bugunIso(), notu: '', geri: false });
  const [dekont, setDekont] = useState<File | null>(null);
  const [iade, setIade] = useState({ tutar: '', neden: '' });
  const [mesgul, setMesgul] = useState(false);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`fatura.hata.${kod}`, { defaultValue: t('fatura.hata.genel') }));
    },
    [t],
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const v = await faturaAyrintisi(faturaId);
      setVeri(v);
      setOdeme((o) => ({ ...o, tutar: v.bakiye && v.bakiye.kalan > 0 ? v.bakiye.kalan.toFixed(2) : '' }));
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [faturaId, hata]);

  const ilkCizim = useRef(true);
  useEffect(() => {
    if (!ilkCizim.current) return;
    ilkCizim.current = false;
    if (acik) void yukle();
  }, [acik, yukle]);

  const ac = () => {
    const yeni = !acik;
    setAcik(yeni);
    if (yeni) {
      ACIK_FATURALAR.add(faturaId);
      void yukle();
    } else ACIK_FATURALAR.delete(faturaId);
  };

  const calistir = async (fn: () => Promise<FaturaAyrintisi | void>) => {
    setMesgul(true);
    try {
      const sonuc = await fn();
      if (sonuc) {
        setVeri(sonuc);
        setOdeme((o) => ({ ...o, tutar: sonuc.bakiye && sonuc.bakiye.kalan > 0 ? sonuc.bakiye.kalan.toFixed(2) : '', notu: '', geri: false }));
      } else await yukle();
      onDegisti?.();
    } catch (h) {
      hata(h);
    } finally {
      setMesgul(false);
    }
  };

  const odemeKaydet = (e: FormEvent) => {
    e.preventDefault();
    void calistir(async () => {
      const y = await odemeEkle(faturaId, { ...odeme, geri_odeme: odeme.geri, dekont });
      setDekont(null);
      toast.success(t('fatura.ayrinti.odemeEklendi'));
      return y.fatura;
    });
  };

  const b = veri?.bakiye;
  const para = (d: number | null | undefined) => paraBicimle(d ?? null, veri?.currency || 'TRY', dil);

  return (
    <div className="w-full" data-testid={`fatura-ayrinti-${faturaId}`}>
      <Button size="sm" variant="ghost" className="gap-1" onClick={ac} data-testid={`fatura-ayrinti-ac-${faturaId}`} aria-expanded={acik}>
        {acik ? <ChevronUp className="h-4 w-4" aria-hidden="true" /> : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
        {t('fatura.ayrinti.ac')}
      </Button>
      {acik && (
        <div className="mt-3 space-y-5 rounded-xl border border-white/10 bg-black/20 p-4" data-testid="fatura-ayrinti">
          {yukleniyor || !veri ? (
            <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /></div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${faturaDurumRengi(veri.status)}`}>
                  {t(`fatura.durum.${veri.status || 'unpaid'}`, { defaultValue: veri.status || '' })}
                </span>
                {veri.tur === 'iade' && <span className="text-xs text-muted-foreground">{t('fatura.ayrinti.iadeFaturasi', { no: veri.bagli_fatura_no || '' })}</span>}
                {veri.teklif_no && <span className="text-xs text-muted-foreground">{t('fatura.ayrinti.tekliften', { no: veri.teklif_no })}</span>}
                {veri.donem && <span className="text-xs text-muted-foreground">{t('fatura.ayrinti.donem', { donem: veri.donem })}</span>}
                <Button size="sm" variant="outline" className="ms-auto gap-1 !bg-transparent" disabled={mesgul}
                  onClick={() => void calistir(async () => { await pdfIndir(yoneticiFaturaPdf(faturaId, pdfDili(dil)), `fatura-${veri.invoice_no}.pdf`); })}
                  data-testid="fatura-pdf">
                  <FileDown className="h-4 w-4" aria-hidden="true" />PDF
                </Button>
              </div>

              {b && (
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4" data-testid="fatura-bakiye">
                  {([['toplam', b.toplam], ['iade', b.iade_toplam], ['odenen', b.odenen], ['kalan', b.kalan]] as const).map(([k, d]) => (
                    <div key={k} className="rounded-lg border border-white/10 p-2">
                      <dt className="text-xs text-muted-foreground">{t(`fatura.bakiye.${k}`)}</dt>
                      <dd className={`font-semibold tabular-nums ${k === 'kalan' && d > 0 ? 'text-orange-300' : ''}`} data-testid={`bakiye-${k}`}>{para(d)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {b && b.fazla > 0 && <p className="text-xs text-amber-300">{t('fatura.bakiye.fazlaUyari', { tutar: para(b.fazla) })}</p>}

              <section>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold">{t('fatura.ayrinti.kalemler')}</h4>
                  {veri.tur !== 'iade' && !kalemDuzen && (
                    <Button size="sm" variant="ghost" className="gap-1" onClick={() => setKalemDuzen(veri.kalemler.length ? veri.kalemler : [{ ...bosKalem(), aciklama: veri.description || '', birim_fiyat: veri.amount, kdv_orani: 0 }])}
                      data-testid="fatura-kalem-duzenle">
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />{t('fatura.ayrinti.kalemDuzenle')}
                    </Button>
                  )}
                </div>
                {kalemDuzen ? (
                  <div className="space-y-3">
                    <KalemDuzenleyici kalemler={kalemDuzen} onChange={setKalemDuzen} paraBirimi={veri.currency} hesapUrl="/api/v1/fatura-yonetim/hesapla" />
                    <div className="flex gap-2">
                      <Button size="sm" disabled={mesgul} data-testid="fatura-kalem-kaydet"
                        onClick={() => void calistir(async () => {
                          await faturaKalemleriniYaz(faturaId, kalemDuzen.filter((k) => k.aciklama.trim()));
                          setKalemDuzen(null);
                          toast.success(t('fatura.ayrinti.kalemKaydedildi'));
                        })}>
                        {t('fatura.kaydet')}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setKalemDuzen(null)}>{t('fatura.vazgec')}</Button>
                    </div>
                  </div>
                ) : veri.kalemler.length ? (
                  <KalemTablosu kalemler={veri.kalemler} ozet={veri.ozet} paraBirimi={veri.currency} />
                ) : (
                  <p className="text-sm text-muted-foreground">{t('fatura.ayrinti.tekTutarli', { tutar: para(veri.amount) })}</p>
                )}
              </section>

              <section>
                <h4 className="mb-2 text-sm font-semibold">{t('fatura.ayrinti.odemeler')}</h4>
                {veri.odemeler.filter((o) => o.durum === 'odendi' || o.durum === 'iade').length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('fatura.ayrinti.odemeYok')}</p>
                ) : (
                  <ul className="divide-y divide-white/5 text-sm" data-testid="fatura-odemeler">
                    {veri.odemeler.filter((o) => o.durum === 'odendi' || o.durum === 'iade').map((o) => (
                      <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                        <span className="min-w-0">
                          {tarihBicimle(o.odeme_tarihi || o.odendi_at, dil)} · {t(`fatura.yontem.${o.saglayici}`, { defaultValue: o.yontem_etiketi || o.saglayici || '—' })}
                          {o.durum === 'iade' && <span className="ms-1 text-amber-300">({t('fatura.ayrinti.geriOdeme')})</span>}
                          {o.notu && <span className="block text-xs text-muted-foreground">{o.notu}</span>}
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="font-semibold tabular-nums">{o.durum === 'iade' ? '−' : ''}{para(o.tutar)}</span>
                          {o.dekont_var && (
                            <Button size="sm" variant="ghost" aria-label={t('fatura.ayrinti.dekont')}
                              onClick={() => void dekontAdresi(o.id).then((d) => adresiIndir(d.adres)).catch(hata)}>
                              <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                          )}
                          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" aria-label={t('fatura.sil')} disabled={mesgul}
                            onClick={() => window.confirm(t('fatura.ayrinti.odemeSilOnay')) && void calistir(async () => (await odemeSil(o.id)).fatura)}>
                            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {veri.tur !== 'iade' && b && (b.kalan > 0 || b.fazla > 0) && (
                <form onSubmit={odemeKaydet} className="grid gap-2 rounded-lg border border-white/10 p-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="odeme-form">
                  <p className="text-sm font-semibold sm:col-span-2 lg:col-span-3">{odeme.geri ? t('fatura.ayrinti.geriOdemeEkle') : t('fatura.ayrinti.odemeEkle')}</p>
                  <label className="grid gap-1 text-xs">{t('fatura.ayrinti.tutar')}
                    <Input name="odeme-tutar" type="number" min={0.01} step="0.01" required value={odeme.tutar}
                      onChange={(e) => setOdeme({ ...odeme, tutar: e.target.value })} data-testid="odeme-tutar" />
                  </label>
                  <label className="grid gap-1 text-xs">{t('fatura.ayrinti.yontem')}
                    <select name="odeme-yontem" value={odeme.yontem} onChange={(e) => setOdeme({ ...odeme, yontem: e.target.value })}
                      className="h-10 rounded-md border border-white/10 bg-white/5 px-2 text-sm">
                      {ODEME_YONTEMLERI.map((y) => <option key={y} value={y} className="bg-[#150a2b]">{t(`fatura.yontem.${y}`)}</option>)}
                    </select>
                  </label>
                  <label className="grid gap-1 text-xs">{t('fatura.ayrinti.tarih')}
                    <Input name="odeme-tarih" type="date" value={odeme.tarih} max={bugunIso()} onChange={(e) => setOdeme({ ...odeme, tarih: e.target.value })} />
                  </label>
                  <label className="grid gap-1 text-xs sm:col-span-2">{t('fatura.ayrinti.not')}
                    <Input name="odeme-not" value={odeme.notu} maxLength={1000} onChange={(e) => setOdeme({ ...odeme, notu: e.target.value })} />
                  </label>
                  <label className="grid gap-1 text-xs">{t('fatura.ayrinti.dekont')}
                    <Input name="odeme-dekont" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="text-xs"
                      onChange={(e) => setDekont(e.target.files?.[0] || null)} />
                  </label>
                  {b.fazla > 0 && (
                    <label className="flex items-center gap-2 text-xs sm:col-span-2">
                      <input type="checkbox" checked={odeme.geri} className="h-4 w-4 accent-purple-500"
                        onChange={(e) => setOdeme({ ...odeme, geri: e.target.checked, tutar: e.target.checked ? b.fazla.toFixed(2) : odeme.tutar })} />
                      {t('fatura.ayrinti.geriOdemeSecenegi')}
                    </label>
                  )}
                  <div className="sm:col-span-2 lg:col-span-3">
                    <Button type="submit" size="sm" disabled={mesgul} className="gap-2" data-testid="odeme-kaydet">
                      {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                      {t('fatura.ayrinti.odemeKaydet')}
                    </Button>
                  </div>
                </form>
              )}

              {veri.tur !== 'iade' && b && b.net > 0 && (
                <details className="rounded-lg border border-white/10 p-3 text-sm">
                  <summary className="flex cursor-pointer items-center gap-2 font-semibold">
                    <Undo2 className="h-4 w-4" aria-hidden="true" />{t('fatura.ayrinti.iadeBaslik')}
                  </summary>
                  <p className="mt-2 text-xs text-muted-foreground">{t('fatura.ayrinti.iadeAciklama')}</p>
                  <div className="mt-2 grid gap-2 sm:grid-cols-3">
                    <Input type="number" min={0.01} step="0.01" value={iade.tutar} placeholder={para(b.net)}
                      aria-label={t('fatura.ayrinti.tutar')} onChange={(e) => setIade({ ...iade, tutar: e.target.value })} />
                    <Input value={iade.neden} maxLength={500} placeholder={t('fatura.ayrinti.iadeNeden')} aria-label={t('fatura.ayrinti.iadeNeden')}
                      onChange={(e) => setIade({ ...iade, neden: e.target.value })} />
                    <Button size="sm" variant="outline" className="!bg-transparent" disabled={mesgul}
                      onClick={() => window.confirm(t('fatura.ayrinti.iadeOnay')) && void calistir(async () => {
                        const y = await iadeKes(faturaId, iade);
                        setIade({ tutar: '', neden: '' });
                        toast.success(t('fatura.ayrinti.iadeKesildi', { no: y.iade_fatura_no }));
                        return y.fatura;
                      })}>
                      {t('fatura.ayrinti.iadeKes')}
                    </Button>
                  </div>
                  {veri.iadeler.length > 0 && (
                    <ul className="mt-2 text-xs text-muted-foreground">
                      {veri.iadeler.map((i) => <li key={i.id}>{i.invoice_no} · {para(i.amount)} · {tarihBicimle(i.issue_date, dil)}</li>)}
                    </ul>
                  )}
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
