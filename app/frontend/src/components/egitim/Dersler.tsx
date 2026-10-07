import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, Download, Eye, FileText, Loader2, Paperclip, Pencil, Plus, Save, Trash2, Video, X } from 'lucide-react';
import { toast } from 'sonner';

import GuvenliMarkdown from '@/components/asistanlar/GuvenliMarkdown';
import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, Rozet, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { blobIndir, hataMetni, type Ders, type EgitimApi, type Kurs } from '@/lib/egitim';

/**
 * Faz 6K — dersler (LMS): bölüm + sıra, güvenli Markdown içerik, video BAĞLANTISI (sitenin CSP'si YouTube/Vimeo
 * çerçevesine izin vermiyor: öğrenci sayfasında yeni sekmede açılır — tıklanana kadar üçüncü tarafa istek yok),
 * dosya ekleri (kalıcı depo; tür içerikten doğrulanır), yayında/taslak. Eğitmen yalnız okur.
 */

type Taslak = { baslik: string; bolum: string; icerik: string; video_url: string; sure_dk: string; yayinda: boolean };
const bos: Taslak = { baslik: '', bolum: '', icerik: '', video_url: '', sure_dk: '', yayinda: true };

function boyutYaz(b: number): string {
  if (b >= 1048576) return `${(b / 1048576).toFixed(1)} MB`;
  if (b >= 1024) return `${Math.round(b / 1024)} KB`;
  return `${b} B`;
}

export default function Dersler({ api, kurs, yonetim }: { api: EgitimApi; kurs: Kurs; yonetim: boolean }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Ders[] | null>(null);
  const [duzenlenen, setDuzenlenen] = useState<number | 'yeni' | null>(null);
  const [d, setD] = useState<Taslak>(bos);
  const [onizleme, setOnizleme] = useState(false);
  const [mesgul, setMesgul] = useState(false);
  const [acik, setAcik] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setListe((await api.dersler(kurs.id)).items);
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, kurs.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const duzenle = (x: Ders | null) => {
    setDuzenlenen(x ? x.id : 'yeni');
    setOnizleme(false);
    setD(x ? { baslik: x.baslik, bolum: x.bolum, icerik: x.icerik, video_url: x.video_url, sure_dk: x.sure_dk == null ? '' : String(x.sure_dk), yayinda: x.yayinda } : { ...bos, bolum: liste?.[liste.length - 1]?.bolum || '' });
  };

  const kaydet = async () => {
    setMesgul(true);
    const g = { baslik: d.baslik, bolum: d.bolum, icerik: d.icerik, video_url: d.video_url, sure_dk: d.sure_dk.trim() ? Number(d.sure_dk) : null, yayinda: d.yayinda };
    try {
      if (duzenlenen === 'yeni') await api.dersEkle(kurs.id, g);
      else if (duzenlenen != null) await api.dersGuncelle(kurs.id, duzenlenen, g);
      toast.success(t('egitim.kaydedildi'));
      setDuzenlenen(null);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const sil = async (x: Ders) => {
    if (!window.confirm(t('egitim.ders.silOnay', { ad: x.baslik }))) return;
    try {
      await api.dersSil(kurs.id, x.id);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const tasi = async (i: number, yon: -1 | 1) => {
    if (!liste) return;
    const j = i + yon;
    if (j < 0 || j >= liste.length) return;
    const yeni = [...liste];
    [yeni[i], yeni[j]] = [yeni[j], yeni[i]];
    setListe(yeni);
    try {
      await api.dersSirasi(kurs.id, yeni.map((x) => x.id));
    } catch (e) {
      toast.error(hataMetni(t, e));
      await yukle();
    }
  };

  const dosyaYukle = async (x: Ders, dosya: File | undefined) => {
    if (!dosya) return;
    setMesgul(true);
    try {
      await api.dosyaYukle(kurs.id, x.id, dosya);
      toast.success(t('egitim.ders.dosyaYuklendi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const dosyaIndir = async (fid: number, ad: string) => {
    try {
      blobIndir(await api.dosyaBlob(kurs.id, fid), ad);
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const dosyaSil = async (fid: number) => {
    try {
      await api.dosyaSil(kurs.id, fid);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const editor = (
    <div className={`${KART} grid gap-3 p-4 sm:p-6 md:grid-cols-2`} data-testid="egitim-ders-editor">
      <h4 className="text-base font-semibold md:col-span-2">{duzenlenen === 'yeni' ? t('egitim.ders.yeni') : t('egitim.ders.duzenle')}</h4>
      <Alan etiket={t('egitim.ders.baslik')}>
        <Input value={d.baslik} onChange={(e) => setD({ ...d, baslik: e.target.value })} maxLength={160} data-testid="egitim-ders-baslik" />
      </Alan>
      <Alan etiket={t('egitim.ders.bolum')} ipucu={t('egitim.ders.bolumIpucu')}>
        <Input value={d.bolum} onChange={(e) => setD({ ...d, bolum: e.target.value })} maxLength={120} />
      </Alan>
      <div className="md:col-span-2">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-sm font-medium text-white/90">{t('egitim.ders.icerik')}</span>
          <Button size="sm" variant="ghost" className="gap-1" onClick={() => setOnizleme((v) => !v)}>
            <Eye className="h-4 w-4" aria-hidden="true" />
            {onizleme ? t('egitim.ayar.duzenle') : t('egitim.ayar.onizle')}
          </Button>
        </div>
        {onizleme ? (
          <div className="min-h-[120px] rounded-md border border-white/10 bg-black/30 p-3 text-sm">
            <GuvenliMarkdown metin={d.icerik || '—'} />
          </div>
        ) : (
          <textarea value={d.icerik} onChange={(e) => setD({ ...d, icerik: e.target.value })} rows={10} maxLength={50000} className={METIN_ALANI} data-testid="egitim-ders-icerik" />
        )}
        <span className="mt-1 block text-xs text-muted-foreground">{t('egitim.ayar.markdownIpucu')}</span>
      </div>
      <Alan etiket={t('egitim.ders.video')} ipucu={t('egitim.ders.videoIpucu')}>
        <Input value={d.video_url} onChange={(e) => setD({ ...d, video_url: e.target.value })} dir="ltr" placeholder="https://www.youtube.com/watch?v=…" data-testid="egitim-ders-video" />
      </Alan>
      <Alan etiket={t('egitim.ders.sure')}>
        <Input type="number" min={1} value={d.sure_dk} onChange={(e) => setD({ ...d, sure_dk: e.target.value })} />
      </Alan>
      <div className="flex flex-wrap items-center gap-3 md:col-span-2">
        <Anahtar acik={d.yayinda} onDegis={(v) => setD({ ...d, yayinda: v })} etiket={t('egitim.ders.yayinda')} />
        <span className="flex-1" />
        <Button variant="ghost" onClick={() => setDuzenlenen(null)}>
          {t('egitim.vazgec')}
        </Button>
        <Button onClick={() => void kaydet()} disabled={mesgul || !d.baslik.trim()} className="gap-1.5" data-testid="egitim-ders-kaydet">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
          {t('egitim.kaydet')}
        </Button>
      </div>
    </div>
  );

  let sonBolum: string | null = null;
  return (
    <div className="grid gap-4" data-testid="egitim-dersler">
      {yonetim && duzenlenen === null && (
        <div className={`${KART} flex flex-wrap items-center gap-2 p-4`}>
          <Button size="sm" className="gap-1.5" onClick={() => duzenle(null)} data-testid="egitim-ders-ekle">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('egitim.ders.ekle')}
          </Button>
          <span className="text-xs text-muted-foreground">{t('egitim.ders.ipucu')}</span>
        </div>
      )}
      {yonetim && duzenlenen !== null && editor}
      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-base font-semibold">{t('egitim.ders.baslikListe')}</h4>
        {liste === null ? (
          <Yukleniyor />
        ) : liste.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{t('egitim.ders.bos')}</p>
        ) : (
          <ol className="grid gap-2" data-testid="egitim-ders-liste">
            {liste.map((x, i) => {
              const bolumBasligi = x.bolum && x.bolum !== sonBolum ? x.bolum : null;
              sonBolum = x.bolum || sonBolum;
              return (
                <li key={x.id} data-ders-id={x.id}>
                  {bolumBasligi && <h5 className="mb-1 mt-2 text-xs font-semibold uppercase tracking-wide text-blue-200">{bolumBasligi}</h5>}
                  <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-white/10 text-xs">{i + 1}</span>
                      <button type="button" className="min-w-0 flex-1 truncate text-start font-medium hover:underline" onClick={() => setAcik(acik === x.id ? null : x.id)}>
                        {x.baslik}
                      </button>
                      {!x.yayinda && <Rozet>{t('egitim.ders.taslak')}</Rozet>}
                      {x.video && (
                        <Rozet>
                          <Video className="h-3 w-3" aria-hidden="true" />
                          {t('egitim.ders.videoVar')}
                        </Rozet>
                      )}
                      {x.dosyalar.length > 0 && (
                        <Rozet>
                          <Paperclip className="h-3 w-3" aria-hidden="true" />
                          {x.dosyalar.length}
                        </Rozet>
                      )}
                      {yonetim && (
                        <span className="flex items-center gap-0.5">
                          <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('egitim.yukari')} onClick={() => void tasi(i, -1)} disabled={i === 0}>
                            <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('egitim.asagi')} onClick={() => void tasi(i, 1)} disabled={i === liste.length - 1}>
                            <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7" aria-label={t('egitim.ders.duzenle')} onClick={() => duzenle(x)}>
                            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-7 w-7 text-red-300" aria-label={t('egitim.sil')} onClick={() => void sil(x)}>
                            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          </Button>
                        </span>
                      )}
                    </div>
                    {acik === x.id && (
                      <div className="mt-3 grid gap-3 border-t border-white/5 pt-3 text-sm">
                        {x.icerik ? <GuvenliMarkdown metin={x.icerik} /> : <p className="text-muted-foreground">{t('egitim.ders.icerikYok')}</p>}
                        {x.video && (
                          <a href={x.video.adres} target="_blank" rel="noopener noreferrer" className="inline-flex w-fit items-center gap-1.5 text-blue-200 hover:underline" dir="ltr">
                            <Video className="h-4 w-4" aria-hidden="true" />
                            {x.video.adres}
                          </a>
                        )}
                        <div className="grid gap-1">
                          {x.dosyalar.map((f) => (
                            <div key={f.id} className="flex items-center gap-2 text-xs">
                              <FileText className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                              <button type="button" className="truncate hover:underline" onClick={() => void dosyaIndir(f.id, f.ad)}>
                                {f.ad}
                              </button>
                              <span className="text-muted-foreground">{boyutYaz(f.boyut)}</span>
                              <Download className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                              {yonetim && (
                                <button type="button" className="text-red-300 hover:text-red-200" aria-label={t('egitim.sil')} onClick={() => void dosyaSil(f.id)}>
                                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                                </button>
                              )}
                            </div>
                          ))}
                          {yonetim && (
                            <label className={`mt-1 inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${DIS_DUGME}`}>
                              <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
                              {t('egitim.ders.dosyaEkle')}
                              <input type="file" className="sr-only" onChange={(e) => void dosyaYukle(x, e.target.files?.[0])} disabled={mesgul} />
                            </label>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
