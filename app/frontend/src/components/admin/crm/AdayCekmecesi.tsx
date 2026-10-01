import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  ArrowRightLeft,
  CalendarClock,
  ChevronDown,
  ExternalLink,
  Loader2,
  Mail,
  MailCheck,
  MailX,
  MessageSquareText,
  Phone,
  Save,
  Settings2,
  Trash2,
  UserCheck,
  Users,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  adayGetir,
  adayGuncelle,
  adaySil,
  aktiviteEkle,
  asamaAdi,
  asamaTasi,
  hataMetni,
  musteriyeDonustur,
  paraGoster,
  renk,
  tarihGoster,
  type AdayAyrintisi,
  type Aktivite,
  type BagliKayit,
  type CrmMeta,
  type DavetSonucu,
  type ElleAktivite,
  type PuanSatiri,
} from '@/lib/crm';
import { AlanEtiketi, Bekle, METIN_ALANI, PuanRozeti, SECIM } from './ortak';

interface Props {
  adayId: number;
  meta: CrmMeta;
  onKapat: () => void;
  onDegisti: () => void;
  onSekmeGit: (sekme: string) => void;
}

const AKTIVITE_IKONU: Record<string, typeof Mail> = {
  not: MessageSquareText,
  arama: Phone,
  eposta: Mail,
  toplanti: Users,
  asama: ArrowRightLeft,
  sistem: Settings2,
};

/**
 * Aday ayrıntı çekmecesi: aşama, puan ("neden bu puan"), alanlar, sonraki
 * adım, not/aktivite ekleme, zaman çizelgesi, bağlı talep/teklif/form kayıtları,
 * müşteriye dönüştür ve silme. Masaüstünde sağdan, mobilde tam ekran.
 */
export default function AdayCekmecesi({ adayId, meta, onKapat, onDegisti, onSekmeGit }: Props) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<{ aday: AdayAyrintisi; aktiviteler: Aktivite[]; bagli_kayitlar: BagliKayit[] } | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [mesgul, setMesgul] = useState(false);
  const [akt, setAkt] = useState<{ tur: ElleAktivite; metin: string }>({ tur: 'not', metin: '' });
  const [puanAcik, setPuanAcik] = useState(false);
  const [davet, setDavet] = useState<DavetSonucu | null>(null);
  const [kayipNedeni, setKayipNedeni] = useState('');

  const asamaHaritasi = useMemo(() => new Map(meta.asamalar.map((a) => [a.anahtar, a])), [meta]);
  // Üst bileşen her çizimde yeni `onKapat` veriyor; yükleme/klavye etkileri ona bağlanırsa
  // çekmece her yenilemede sıfırlanır (davet sonucu kaybolurdu). Güncel işlev ref'te.
  const kapatRef = useRef(onKapat);
  kapatRef.current = onKapat;

  const formuDoldur = (a: AdayAyrintisi) =>
    setForm({
      ad: a.ad || '',
      firma: a.firma || '',
      email: a.email || '',
      telefon: a.telefon || '',
      deger_tahmini: a.deger_tahmini === null ? '' : String(a.deger_tahmini),
      para_birimi: a.para_birimi || 'TRY',
      olasilik: a.olasilik === null ? '' : String(a.olasilik),
      sorumlu: a.sorumlu || '',
      etiketler: (a.etiketler || []).join(', '),
      sonraki_adim: a.sonraki_adim || '',
      sonraki_adim_tarihi: a.sonraki_adim_tarihi || '',
      notlar: a.notlar || '',
      butce: a.butce || '',
    });

  const yukle = useCallback(async () => {
    try {
      const y = await adayGetir(adayId);
      setVeri(y);
      formuDoldur(y.aday);
      setKayipNedeni(y.aday.kaybedilme_nedeni || '');
    } catch (e) {
      toast.error(hataMetni(t, e));
      kapatRef.current();
    }
  }, [adayId, t]);

  useEffect(() => {
    setVeri(null);
    setDavet(null);
    void yukle();
  }, [yukle]);

  useEffect(() => {
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') kapatRef.current();
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, []);

  const islem = async (is: () => Promise<void>) => {
    setMesgul(true);
    try {
      await is();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const kaydet = () =>
    islem(async () => {
      const a = await adayGuncelle(adayId, {
        ...form,
        deger_tahmini: form.deger_tahmini === '' ? null : Number(form.deger_tahmini),
        olasilik: form.olasilik === '' ? null : Number(form.olasilik),
        etiketler: form.etiketler,
        sonraki_adim_tarihi: form.sonraki_adim_tarihi || null,
      });
      setVeri((v) => (v ? { ...v, aday: a } : v));
      formuDoldur(a);
      toast.success(t('crm.kaydedildi'));
      onDegisti();
    });

  // Faz 4G: kişi vazgeçtiğini bildirdiğinde pazarlama iznini geri al (vermek panelden mümkün değil).
  const izniGeriAl = () =>
    islem(async () => {
      if (!window.confirm(t('crm.pazarlama.geriAlOnay'))) return;
      const a = await adayGuncelle(adayId, { pazarlama_izni: false });
      setVeri((v) => (v ? { ...v, aday: a } : v));
      toast.success(t('crm.pazarlama.geriAlindi'));
      onDegisti();
    });

  const izinKaynagi = (k?: string | null) => {
    if (!k) return null;
    const [tur, no] = k.split(':');
    return tur === 'form' ? t('crm.pazarlama.kaynakForm', { no }) : tur === 'site_analizi' ? t('crm.pazarlama.kaynakSiteAnalizi') : k;
  };

  const tasi = (asama: string, neden?: string) =>
    islem(async () => {
      await asamaTasi(adayId, asama, neden);
      toast.success(t('crm.tasindi', { asama: asamaAdi(asamaHaritasi.get(asama), dil) }));
      await yukle();
      onDegisti();
    });

  const aktiviteKaydet = () =>
    islem(async () => {
      if (!akt.metin.trim()) return;
      await aktiviteEkle(adayId, akt.tur, akt.metin.trim());
      setAkt((a) => ({ ...a, metin: '' }));
      toast.success(t('crm.aktiviteEklendi'));
      await yukle();
      onDegisti();
    });

  const donustur = () =>
    islem(async () => {
      if (!window.confirm(t('crm.donusturOnay', { eposta: veri?.aday.email || '' }))) return;
      const y = await musteriyeDonustur(adayId);
      setDavet(y.davet);
      toast.success(t('crm.donusturuldu'));
      await yukle();
      onDegisti();
    });

  const sil = () =>
    islem(async () => {
      if (!window.confirm(t('crm.silOnay', { ad: veri?.aday.ad || '' }))) return;
      await adaySil(adayId);
      toast.success(t('crm.silindi'));
      onDegisti();
      onKapat();
    });

  const yaz = (k: string) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const a = veri?.aday;
  const asama = a ? asamaHaritasi.get(a.asama) : undefined;

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-background/70 backdrop-blur-sm" onClick={onKapat}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="crm-cekmece-baslik"
        className="h-full w-full overflow-y-auto border-s border-white/10 bg-background p-4 shadow-2xl sm:max-w-xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
        data-testid="crm-cekmece"
        data-crm-cekmece={adayId}
      >
        {!a || !veri ? (
          <Bekle />
        ) : (
          <div className="space-y-5">
            <header className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <h3 id="crm-cekmece-baslik" className="break-words text-xl font-bold">
                  {a.ad}
                </h3>
                <p className="text-sm text-muted-foreground">{[a.firma, t(`crm.kaynak.${a.kaynak}`)].filter(Boolean).join(' · ')}</p>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                  {a.email && (
                    <a className="inline-flex items-center gap-1 text-purple-200 hover:underline" href={`mailto:${a.email}`} dir="ltr">
                      <Mail className="h-3 w-3" aria-hidden="true" /> {a.email}
                    </a>
                  )}
                  {a.telefon && (
                    <a className="inline-flex items-center gap-1 text-purple-200 hover:underline" href={`tel:${a.telefon}`} dir="ltr">
                      <Phone className="h-3 w-3" aria-hidden="true" /> {a.telefon}
                    </a>
                  )}
                </div>
              </div>
              <PuanRozeti puan={a.puan} buyuk />
              <button type="button" className="rounded-lg p-2 hover:bg-white/5" onClick={onKapat} aria-label={t('crm.kapat')}>
                <X className="h-4 w-4" />
              </button>
            </header>

            {/* Faz 4G: pazarlama (ticari elektronik ileti) izni — yalnız kişinin kendisi verir; panelden geri alınabilir. */}
            <div
              className={`flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-xs ${
                a.pazarlama_izni ? 'border-emerald-400/30 bg-emerald-500/10' : 'border-white/10 bg-white/[0.03]'
              }`}
              data-testid="crm-pazarlama-izni"
              data-izin={a.pazarlama_izni ? 'var' : 'yok'}
            >
              {a.pazarlama_izni ? (
                <MailCheck className="h-4 w-4 flex-none text-emerald-300" aria-hidden="true" />
              ) : (
                <MailX className="h-4 w-4 flex-none text-muted-foreground" aria-hidden="true" />
              )}
              <span className="min-w-0 flex-1">
                <span className="font-medium">{a.pazarlama_izni ? t('crm.pazarlama.var') : t('crm.pazarlama.yok')}</span>
                {a.pazarlama_izni && (
                  <span className="block text-muted-foreground">
                    {[
                      a.pazarlama_izni_at ? tarihGoster(a.pazarlama_izni_at, dil, true) : null,
                      izinKaynagi(a.pazarlama_izni_kaynak),
                      a.pazarlama_metin_surumu ? t('crm.pazarlama.surum', { surum: a.pazarlama_metin_surumu }) : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                )}
              </span>
              {a.pazarlama_izni && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs"
                  disabled={mesgul}
                  onClick={() => void izniGeriAl()}
                  data-testid="crm-pazarlama-geri-al"
                >
                  {t('crm.pazarlama.geriAl')}
                </Button>
              )}
            </div>

            {/* Aşama */}
            <div className={`cam-kart rounded-2xl border bg-white/[0.03] p-3 ${renk(asama?.renk).kenar}`}>
              <label className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">{t('crm.alan.asama')}</span>
                <select
                  className={SECIM + ' max-w-[16rem]'}
                  value={a.asama}
                  onChange={(e) => {
                    const hedef = asamaHaritasi.get(e.target.value);
                    void tasi(e.target.value, hedef?.tur === 'kaybedildi' ? kayipNedeni : undefined);
                  }}
                  disabled={mesgul}
                  data-testid="crm-cekmece-asama"
                >
                  {meta.asamalar.map((x) => (
                    <option key={x.anahtar} value={x.anahtar}>
                      {asamaAdi(x, dil)}
                    </option>
                  ))}
                </select>
                {a.olasilik !== null && <span className="text-xs text-muted-foreground">{t('crm.olasilikYuzde', { sayi: a.olasilik })}</span>}
              </label>
              {asama?.tur === 'kaybedildi' && (
                <div className="mt-2 flex gap-2">
                  <Input
                    value={kayipNedeni}
                    onChange={(e) => setKayipNedeni(e.target.value)}
                    placeholder={t('crm.alan.kaybedilme_nedeni')}
                    maxLength={1000}
                    aria-label={t('crm.alan.kaybedilme_nedeni')}
                  />
                  <Button size="sm" variant="outline" disabled={mesgul} onClick={() => void tasi(a.asama, kayipNedeni)}>
                    <Save className="h-4 w-4" />
                  </Button>
                </div>
              )}
              {a.asama_degisme_at && (
                <p className="mt-1 text-[11px] text-muted-foreground">{t('crm.asamadaSince', { tarih: tarihGoster(a.asama_degisme_at, dil, true) })}</p>
              )}
            </div>

            {/* Puan açıklaması */}
            <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-3">
              <button
                type="button"
                className="flex w-full items-center justify-between text-sm font-medium"
                onClick={() => setPuanAcik((x) => !x)}
                aria-expanded={puanAcik}
                data-testid="crm-puan-neden"
              >
                <span>{t('crm.puan.neden', { puan: a.puan })}</span>
                <ChevronDown className={`h-4 w-4 transition-transform ${puanAcik ? 'rotate-180' : ''}`} aria-hidden="true" />
              </button>
              {puanAcik && (
                <ul className="mt-2 space-y-1.5 text-xs" data-testid="crm-puan-ayrinti">
                  {a.puan_ayrinti.map((p) => (
                    <PuanSatirGorunumu key={p.kural} p={p} />
                  ))}
                  <li className="pt-1 text-[11px] text-muted-foreground">{t('crm.puan.dipnot')}</li>
                </ul>
              )}
            </div>

            {/* Sonraki adım + alanlar */}
            <form
              className="cam-kart grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 sm:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                void kaydet();
              }}
            >
              <AlanEtiketi ad={t('crm.alan.sonraki_adim')}>
                <Input value={form.sonraki_adim} onChange={yaz('sonraki_adim')} maxLength={300} data-testid="crm-sonraki-adim" />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.sonraki_adim_tarihi')}>
                <Input type="date" value={form.sonraki_adim_tarihi} onChange={yaz('sonraki_adim_tarihi')} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.ad')} zorunlu>
                <Input value={form.ad} onChange={yaz('ad')} maxLength={120} required />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.firma')}>
                <Input value={form.firma} onChange={yaz('firma')} maxLength={160} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.email')}>
                <Input type="email" value={form.email} onChange={yaz('email')} maxLength={254} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.telefon')}>
                <Input value={form.telefon} onChange={yaz('telefon')} maxLength={40} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.deger_tahmini')}>
                <div className="flex gap-2">
                  <Input type="number" min={0} step="any" value={form.deger_tahmini} onChange={yaz('deger_tahmini')} />
                  <select aria-label={t('crm.alan.para_birimi')} className={SECIM + ' w-24'} value={form.para_birimi} onChange={yaz('para_birimi')}>
                    {meta.para_birimleri.map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                </div>
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.olasilik')}>
                <Input type="number" min={0} max={100} value={form.olasilik} onChange={yaz('olasilik')} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.sorumlu')}>
                <select className={SECIM} value={form.sorumlu} onChange={yaz('sorumlu')}>
                  <option value="">{t('crm.sorumsuz')}</option>
                  {meta.sorumlular.map((s) => (
                    <option key={s.email} value={s.email}>
                      {s.ad || s.email}
                    </option>
                  ))}
                  {form.sorumlu && !meta.sorumlular.some((s) => s.email === form.sorumlu) && <option value={form.sorumlu}>{form.sorumlu}</option>}
                </select>
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.butce')}>
                <Input value={form.butce} onChange={yaz('butce')} maxLength={120} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.etiketler')} tam>
                <Input value={form.etiketler} onChange={yaz('etiketler')} placeholder={t('crm.etiketIpucu')} />
              </AlanEtiketi>
              <AlanEtiketi ad={t('crm.alan.notlar')} tam>
                <textarea className={METIN_ALANI} rows={3} value={form.notlar} onChange={yaz('notlar')} maxLength={10000} />
              </AlanEtiketi>
              <div className="flex justify-end sm:col-span-2">
                <Button type="submit" size="sm" disabled={mesgul} className="gap-1" data-testid="crm-cekmece-kaydet">
                  {mesgul ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {t('crm.kaydet')}
                </Button>
              </div>
            </form>

            {/* Aktivite ekle */}
            <form
              className="cam-kart space-y-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3"
              onSubmit={(e) => {
                e.preventDefault();
                void aktiviteKaydet();
              }}
            >
              <div className="flex flex-wrap gap-1" role="group" aria-label={t('crm.aktiviteTuru')}>
                {meta.aktivite_turleri.map((tur) => {
                  const Ikon = AKTIVITE_IKONU[tur];
                  return (
                    <button
                      key={tur}
                      type="button"
                      aria-pressed={akt.tur === tur}
                      onClick={() => setAkt((x) => ({ ...x, tur }))}
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${
                        akt.tur === tur ? 'bg-purple-500/25 text-foreground' : 'border border-white/10 text-muted-foreground hover:text-foreground'
                      }`}
                      data-crm-aktivite-turu={tur}
                    >
                      <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
                      {t(`crm.aktivite.${tur}`)}
                    </button>
                  );
                })}
              </div>
              <textarea
                className={METIN_ALANI}
                rows={2}
                value={akt.metin}
                onChange={(e) => setAkt((x) => ({ ...x, metin: e.target.value }))}
                placeholder={t('crm.aktiviteOrnek')}
                maxLength={4000}
                aria-label={t('crm.aktiviteMetni')}
                data-testid="crm-aktivite-metin"
              />
              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={mesgul || !akt.metin.trim()} data-testid="crm-aktivite-ekle">
                  {t('crm.aktiviteEkle')}
                </Button>
              </div>
            </form>

            {/* Zaman çizelgesi */}
            <section aria-labelledby="crm-zaman-baslik">
              <h4 id="crm-zaman-baslik" className="mb-2 text-sm font-semibold">
                {t('crm.zamanCizelgesi')}
              </h4>
              <ol className="space-y-2 border-s border-white/10 ps-4" data-testid="crm-zaman-cizelgesi">
                {veri.aktiviteler.map((k) => (
                  <AktiviteSatiri key={k.id} k={k} meta={meta} />
                ))}
              </ol>
            </section>

            {/* İlk mesaj */}
            {a.ilk_mesaj && (
              <details className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-sm">
                <summary className="cursor-pointer font-medium">{t('crm.ilkMesaj')}</summary>
                <p className="mt-2 whitespace-pre-wrap break-words text-muted-foreground">{a.ilk_mesaj}</p>
              </details>
            )}

            {/* Bağlı kayıtlar */}
            {veri.bagli_kayitlar.length > 0 && (
              <section aria-labelledby="crm-bagli-baslik">
                <h4 id="crm-bagli-baslik" className="mb-2 text-sm font-semibold">
                  {t('crm.bagliKayitlar')}
                </h4>
                <ul className="space-y-1.5 text-sm">
                  {veri.bagli_kayitlar.map((b) => (
                    <li key={`${b.tablo}-${b.kayit_id}`} className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 px-3 py-2">
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[11px]">{t(`crm.tablo.${b.tablo}`)}</span>
                      <span className="min-w-0 flex-1 truncate">
                        {b.silinmis ? t('crm.kayitSilinmis') : b.baslik || `#${b.kayit_id}`}
                        {b.tutar ? ` · ${paraGoster(b.tutar, b.para_birimi || 'USD', dil)}` : ''}
                        {b.kvkk_surum ? ` · ${t('crm.kvkkSurumu', { sayi: b.kvkk_surum })}` : ''}
                      </span>
                      {b.pazarlama_izni && (
                        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] text-emerald-200" data-testid="crm-bagli-pazarlama">
                          {t('crm.pazarlama.rozet')}
                        </span>
                      )}
                      {b.zaman && <span className="text-[11px] text-muted-foreground">{tarihGoster(b.zaman, dil)}</span>}
                      {!b.silinmis && (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 text-xs text-purple-200 hover:underline"
                          onClick={() =>
                            onSekmeGit(b.tablo === 'inquiries' ? 'inquiries' : b.tablo === 'pricing_inquiries' ? 'fiyatlandirmaV5' : 'crmFormlar')
                          }
                        >
                          <ExternalLink className="h-3 w-3" aria-hidden="true" /> {t('crm.ac')}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Dönüştür / sil */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4">
              {a.musteri_email ? (
                <span className="inline-flex items-center gap-1 text-sm text-emerald-200">
                  <UserCheck className="h-4 w-4" aria-hidden="true" /> {t('crm.musteriOldu', { eposta: a.musteri_email })}
                </span>
              ) : (
                <Button size="sm" onClick={() => void donustur()} disabled={mesgul || !a.email} className="gap-1" data-testid="crm-donustur">
                  <UserCheck className="h-4 w-4" /> {t('crm.donustur')}
                </Button>
              )}
              <Button size="sm" variant="ghost" className="gap-1 text-destructive" onClick={() => void sil()} disabled={mesgul}>
                <Trash2 className="h-4 w-4" /> {t('crm.sil')}
              </Button>
            </div>
            {!a.email && !a.musteri_email && <p className="text-xs text-muted-foreground">{t('crm.donusturEpostaGerekli')}</p>}
            {davet && (
              <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm" role="status" data-testid="crm-davet-sonucu">
                <p className="font-medium">{t(`crm.davetDurumu.${davet.email_status}`, { defaultValue: t('crm.davetDurumu.unknown') })}</p>
                {davet.email_status !== 'sent' && (
                  <>
                    <p className="mt-1 text-xs text-muted-foreground">{t('crm.davetElle')}</p>
                    <textarea className={METIN_ALANI + ' mt-2 text-xs'} rows={5} readOnly value={`${davet.subject}\n\n${davet.message}`} />
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function PuanSatirGorunumu({ p }: { p: PuanSatiri }) {
  const { t } = useTranslation();
  let ayrinti = '';
  if (p.kural === 'kaynak') ayrinti = t('crm.puan.deger.kaynak', { kaynak: t(`crm.kaynak.${p.deger}`) });
  else if (p.kural === 'butce') ayrinti = t(p.deger ? 'crm.puan.deger.butceVar' : 'crm.puan.deger.butceYok');
  else if (p.kural === 'kapsam') ayrinti = t('crm.puan.deger.kapsam', { sayi: Number(p.deger) });
  else if (p.kural === 'alan_adi') ayrinti = t(`crm.puan.deger.alan_${p.deger}`);
  else if (p.kural === 'etkilesim') ayrinti = t('crm.puan.deger.etkilesim', { sayi: Number(p.deger) });
  return (
    <li className="flex items-start gap-2">
      <span className="w-14 shrink-0 tabular-nums text-foreground">
        +{p.puan}/{p.en_cok}
      </span>
      <span className="min-w-0">
        <span className="font-medium text-foreground/90">{t(`crm.puan.kural.${p.kural}`)}</span>
        <span className="text-muted-foreground"> — {ayrinti}</span>
      </span>
    </li>
  );
}

function AktiviteSatiri({ k, meta }: { k: Aktivite; meta: CrmMeta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const Ikon = AKTIVITE_IKONU[k.tur] || CalendarClock;
  const asama = (anahtar: unknown) =>
    asamaAdi(meta.asamalar.find((a) => a.anahtar === anahtar), dil) || String(anahtar ?? '');
  let baslik: string;
  if (k.olay) {
    const v = k.veri || {};
    baslik = t(`crm.olay.${k.olay}`, {
      kaynak: v.kaynak ? t(`crm.kaynak.${String(v.kaynak)}`) + (typeof v.form === 'string' ? `: ${v.form}` : '') : '',
      eski: asama(v.eski),
      yeni: asama(v.yeni),
      form: typeof v.form === 'string' ? v.form : '',
      eposta: typeof v.musteri_email === 'string' ? v.musteri_email : '',
      davet: v.davet ? t(`crm.davetDurumu.${String(v.davet)}`, { defaultValue: String(v.davet) }) : '',
      defaultValue: k.olay,
    });
    if (v.ice_aktarma) baslik += ` · ${t('crm.iceAktarmaIle')}`;
    if (v.sebep === 'asama_silindi') baslik += ` · ${t('crm.asamaSilindiSebep')}`;
  } else {
    baslik = t(`crm.aktivite.${k.tur}`);
  }
  return (
    <li className="relative" data-crm-aktivite={k.tur}>
      <span className="absolute -start-[1.4rem] top-0.5 flex h-5 w-5 items-center justify-center rounded-full border border-white/10 bg-background">
        <Ikon className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
      </span>
      <p className="text-sm font-medium">{baslik}</p>
      {k.metin && <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-muted-foreground">{k.metin}</p>}
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {tarihGoster(k.zaman, dil, true)}
        {k.yapan ? ` · ${k.yapan === 'sistem' ? t('crm.sistem') : k.yapan}` : ''}
      </p>
    </li>
  );
}
