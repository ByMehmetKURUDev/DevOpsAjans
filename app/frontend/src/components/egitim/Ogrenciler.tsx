import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Download, Loader2, Mail, Plus, RefreshCw, Trash2, Upload, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, kopyala } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { blobIndir, hataMetni, type EgitimApi, type Kurs, type Ogrenci, type OgrenciDurumu } from '@/lib/egitim';

/**
 * Faz 6K — öğrenciler: liste (ilerleme / yoklama / quiz özetiyle), elle ekleme, CSV içe/dışa aktarma, durum
 * (aktif / bekleme / ayrıldı — ayrılanın yerine sıradaki bekleyen kendiliğinden alınır), öğrenci bağlantısı
 * (kopyala, e-postayla gönder, yenile = eskiler geçersiz) ve KVKK silme. Eğitmen (yalnız `egitim_egitmen`)
 * yalnız ad + kod + ilerleme görür; iletişim ve veli bilgisi gelmez.
 */

export const OGRENCI_RENGI: Record<OgrenciDurumu, string> = {
  aktif: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  bekleme: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  ayrildi: 'border-white/15 bg-white/[0.05] text-muted-foreground',
};

export function Cubuk({ deger, etiket }: { deger: number | null | undefined; etiket: string }) {
  const v = deger == null ? null : Math.max(0, Math.min(100, deger));
  return (
    <span className="flex min-w-[6.5rem] items-center gap-1.5 text-[11px] text-muted-foreground" title={etiket}>
      <span className="sr-only">{etiket}</span>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
        <span className="block h-full rounded-full bg-blue-400" style={{ width: `${v ?? 0}%` }} />
      </span>
      <span>{v == null ? '—' : `%${v}`}</span>
    </span>
  );
}

const BOS_FORM = { ad: '', eposta: '', telefon: '', cocuk: false, veli_ad: '', veli_eposta: '', veli_telefon: '', bekleme: false, bildir: true };

export default function Ogrenciler({ api, kurs, yonetim }: { api: EgitimApi; kurs: Kurs; yonetim: boolean }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Ogrenci[] | null>(null);
  const [suzgec, setSuzgec] = useState<'' | OgrenciDurumu>('');
  const [form, setForm] = useState(BOS_FORM);
  const [formAcik, setFormAcik] = useState(false);
  const [csvAcik, setCsvAcik] = useState(false);
  const [csv, setCsv] = useState('');
  const [csvBildir, setCsvBildir] = useState(false);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.ogrenciler(kurs.id, suzgec || undefined)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, kurs.id, suzgec, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const ekle = async () => {
    setMesgul(true);
    try {
      const o = await api.ogrenciEkle(kurs.id, {
        ad: form.ad, eposta: form.eposta, telefon: form.telefon, cocuk: form.cocuk, veli_ad: form.veli_ad,
        veli_eposta: form.veli_eposta, veli_telefon: form.veli_telefon, bildir: form.bildir,
        ...(form.bekleme ? { durum: 'bekleme' } : {}),
      });
      toast.success(o.durum === 'bekleme' ? t('egitim.ogrenci.beklemeyeEklendi') : t('egitim.ogrenci.eklendi'));
      setForm(BOS_FORM);
      setFormAcik(false);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const csvYukle = async () => {
    setMesgul(true);
    try {
      const s = await api.ogrenciCsv(kurs.id, csv, csvBildir);
      toast.success(t('egitim.ogrenci.csvSonuc', { aktif: s.aktif, bekleme: s.bekleme, atlanan: s.atlanan, hata: s.hata_sayisi }));
      if (s.hatalar.length) toast.error(s.hatalar.slice(0, 5).map((h) => t('egitim.ogrenci.csvHata', { satir: h.satir, hata: t(`egitim.hata.${h.kod}`, { defaultValue: h.kod }) })).join('\n'));
      setCsv('');
      setCsvAcik(false);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const durumDegis = async (o: Ogrenci, durum: OgrenciDurumu) => {
    try {
      await api.ogrenciGuncelle(kurs.id, o.id, { durum });
      toast.success(t('egitim.kaydedildi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const baglanti = async (o: Ogrenci, g: { yenile?: boolean; gonder?: boolean }) => {
    if (g.yenile && !window.confirm(t('egitim.ogrenci.yenileOnay'))) return;
    try {
      const b = await api.ogrenciBaglantisi(kurs.id, o.id, g);
      if (g.gonder) toast.success(t('egitim.ogrenci.gonderildi'));
      else await kopyala(b.adres, t('egitim.ogrenci.baglantiKopyalandi'), t('egitim.kopyalanamadi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async (o: Ogrenci) => {
    if (!window.confirm(t('egitim.ogrenci.silOnay', { ad: o.ad }))) return;
    try {
      await api.ogrenciSil(kurs.id, o.id);
      toast.success(t('egitim.ogrenci.silindi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const csvIndir = async () => {
    try {
      blobIndir(await api.ogrenciCsvBlob(kurs.id), `${kurs.slug}-ogrenciler.csv`);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const cocukGerekli = kurs.hedef_kitle === 'cocuk' || (kurs.hedef_kitle === 'karma' && form.cocuk);

  return (
    <div className="grid gap-4" data-testid="egitim-ogrenciler">
      {yonetim && (
        <div className={`${KART} flex flex-wrap items-center gap-2 p-4`}>
          <Button size="sm" className="gap-1.5" onClick={() => setFormAcik((v) => !v)} data-testid="egitim-ogrenci-ekle-ac">
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ogrenci.ekle')}
          </Button>
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => setCsvAcik((v) => !v)}>
            <Upload className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ogrenci.csvIceAktar')}
          </Button>
          <Button size="sm" variant="outline" className={DIS_DUGME} onClick={() => void csvIndir()}>
            <Download className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ogrenci.csvIndir')}
          </Button>
          <span className="flex-1" />
          <span className="text-xs text-muted-foreground">
            {kurs.kapasite != null ? t('egitim.ogrenci.kapasite', { sayi: kurs.ogrenci ?? 0, kapasite: kurs.kapasite }) : ''}
          </span>
        </div>
      )}
      {yonetim && formAcik && (
        <div className={`${KART} grid gap-3 p-4 sm:p-6 md:grid-cols-3`} data-testid="egitim-ogrenci-form">
          <Alan etiket={t('egitim.alan.ogrenciAd')}>
            <Input value={form.ad} onChange={(e) => setForm({ ...form, ad: e.target.value })} maxLength={120} data-testid="egitim-ogrenci-ad" />
          </Alan>
          <Alan etiket={cocukGerekli ? t('egitim.alan.epostaIstegeBagli') : t('egitim.alan.eposta')}>
            <Input value={form.eposta} onChange={(e) => setForm({ ...form, eposta: e.target.value })} type="email" dir="ltr" data-testid="egitim-ogrenci-eposta" />
          </Alan>
          <Alan etiket={t('egitim.alan.telefon')}>
            <Input value={form.telefon} onChange={(e) => setForm({ ...form, telefon: e.target.value })} type="tel" dir="ltr" />
          </Alan>
          {kurs.hedef_kitle === 'karma' && (
            <div className="md:col-span-3">
              <Anahtar acik={form.cocuk} onDegis={(v) => setForm({ ...form, cocuk: v })} etiket={t('egitim.ogrenci.cocuk')} />
            </div>
          )}
          {cocukGerekli && (
            <>
              <Alan etiket={t('egitim.alan.veliAd')}>
                <Input value={form.veli_ad} onChange={(e) => setForm({ ...form, veli_ad: e.target.value })} maxLength={120} />
              </Alan>
              <Alan etiket={t('egitim.alan.veliEposta')}>
                <Input value={form.veli_eposta} onChange={(e) => setForm({ ...form, veli_eposta: e.target.value })} type="email" dir="ltr" />
              </Alan>
              <Alan etiket={t('egitim.alan.veliTelefon')}>
                <Input value={form.veli_telefon} onChange={(e) => setForm({ ...form, veli_telefon: e.target.value })} type="tel" dir="ltr" />
              </Alan>
            </>
          )}
          <div className="flex flex-wrap items-center gap-4 md:col-span-3">
            <Anahtar acik={form.bekleme} onDegis={(v) => setForm({ ...form, bekleme: v })} etiket={t('egitim.ogrenci.beklemeyeEkle')} />
            <Anahtar acik={form.bildir} onDegis={(v) => setForm({ ...form, bildir: v })} etiket={t('egitim.ogrenci.bildir')} />
            <span className="flex-1" />
            <Button onClick={() => void ekle()} disabled={mesgul || !form.ad.trim()} className="gap-1.5" data-testid="egitim-ogrenci-kaydet">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
              {t('egitim.ekle')}
            </Button>
          </div>
        </div>
      )}
      {yonetim && csvAcik && (
        <div className={`${KART} grid gap-3 p-4 sm:p-6`}>
          <p className="text-sm text-muted-foreground">{t('egitim.ogrenci.csvIpucu')}</p>
          <textarea value={csv} onChange={(e) => setCsv(e.target.value)} rows={6} className={`${METIN_ALANI} font-mono`} dir="ltr" placeholder={'ad,eposta,telefon,veli_ad,veli_eposta\nAyşe Yılmaz,ayse@ornek.com,05551112233,,'} />
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm">
              <span className="sr-only">{t('egitim.ogrenci.csvDosya')}</span>
              <input
                type="file"
                accept=".csv,text/csv"
                className="text-xs"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (f) setCsv(await f.text());
                }}
              />
            </label>
            <Anahtar acik={csvBildir} onDegis={setCsvBildir} etiket={t('egitim.ogrenci.bildir')} />
            <span className="flex-1" />
            <Button onClick={() => void csvYukle()} disabled={mesgul || !csv.trim()} className="gap-1.5">
              {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
              {t('egitim.ogrenci.iceAktar')}
            </Button>
          </div>
        </div>
      )}
      <div className={`${KART} p-4 sm:p-6`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-base font-semibold">{t('egitim.ogrenci.baslik')}</h4>
          <select value={suzgec} onChange={(e) => setSuzgec(e.target.value as '' | OgrenciDurumu)} className={`${SECIM} w-auto`} aria-label={t('egitim.ogrenci.suzgec')}>
            <option value="">{t('egitim.ogrenci.hepsi')}</option>
            {(['aktif', 'bekleme', 'ayrildi'] as const).map((x) => (
              <option key={x} value={x}>
                {t(`egitim.ogrenciDurum.${x}`)}
              </option>
            ))}
          </select>
        </div>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('egitim.ogrenci.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="egitim-ogrenci-liste">
            {liste.map((o) => (
              <li key={o.id} className="flex flex-col gap-2 py-3 lg:flex-row lg:items-center" data-ogrenci-id={o.id}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{o.anonim ? t('egitim.ogrenci.anonim') : o.ad}</span>
                    <Rozet renk={OGRENCI_RENGI[o.durum]}>{t(`egitim.ogrenciDurum.${o.durum}`)}</Rozet>
                    {o.cocuk && <Rozet>{t('egitim.ogrenci.cocukRozet')}</Rozet>}
                    {o.istatistik?.sertifika && <Rozet renk="border-blue-400/40 bg-blue-500/15 text-blue-200">{t('egitim.ogrenci.sertifikali')}</Rozet>}
                    <code className="text-[11px] text-muted-foreground" dir="ltr">
                      {o.kod}
                    </code>
                  </div>
                  {yonetim && !o.anonim && (
                    <div className="mt-0.5 truncate text-xs text-muted-foreground" dir="ltr">
                      {[o.eposta, o.telefon, o.cocuk && o.veli_ad ? `${t('egitim.ogrenci.veli')}: ${o.veli_ad} ${o.veli_eposta || ''} ${o.veli_telefon || ''}` : '']
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                  )}
                </div>
                {o.istatistik && (
                  <div className="flex flex-wrap gap-3">
                    <Cubuk deger={o.istatistik.ilerleme} etiket={t('egitim.ilerleme.ilerleme')} />
                    <Cubuk deger={o.istatistik.yoklama} etiket={t('egitim.ilerleme.yoklama')} />
                    <Cubuk deger={o.istatistik.quiz_ortalama} etiket={t('egitim.ilerleme.quiz')} />
                  </div>
                )}
                {yonetim && !o.anonim && (
                  <div className="flex flex-wrap items-center gap-1">
                    <select value={o.durum} onChange={(e) => void durumDegis(o, e.target.value as OgrenciDurumu)} className={`${SECIM} h-8 w-auto text-xs`} aria-label={t('egitim.ogrenci.durum')}>
                      {(['aktif', 'bekleme', 'ayrildi'] as const).map((x) => (
                        <option key={x} value={x}>
                          {t(`egitim.ogrenciDurum.${x}`)}
                        </option>
                      ))}
                    </select>
                    <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('egitim.ogrenci.baglantiKopyala')} title={t('egitim.ogrenci.baglantiKopyala')} onClick={() => void baglanti(o, {})} data-testid="egitim-ogrenci-baglanti">
                      <Copy className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('egitim.ogrenci.baglantiGonder')} title={t('egitim.ogrenci.baglantiGonder')} onClick={() => void baglanti(o, { gonder: true })}>
                      <Mail className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('egitim.ogrenci.baglantiYenile')} title={t('egitim.ogrenci.baglantiYenile')} onClick={() => void baglanti(o, { yenile: true })}>
                      <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-red-300" aria-label={t('egitim.ogrenci.sil')} title={t('egitim.ogrenci.sil')} onClick={() => void sil(o)}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {yonetim && <p className="mt-3 text-xs text-muted-foreground">{t('egitim.ogrenci.kvkkNotu')}</p>}
      </div>
    </div>
  );
}
