import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, FileText, Globe, HelpCircle, Layers, Loader2, Pencil, Plus, RefreshCw, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, Rozet, SECIM, Yukleniyor, sayiYaz, tarihYaz } from '@/components/aiAsistan/ortak';
import { hataMetni, type Asistan, type AsistanApi, type Kaynak, type KaynakTuru, type Meta, type Sinirlar } from '@/lib/aiAsistan';

/**
 * Faz 5A — bilgi bankası: metin, SSS, belge (PDF/DOCX/TXT/MD), URL ya da site haritası
 * (SSRF korumalı, robots.txt'ye saygılı), modülden içe aktarma (QR menü, randevu).
 * Kaynak başına durum (işleniyor / hazır / hata), yeniden işle, düzenle, sil.
 * İşlenen URL kaynağı varken liste 3 sn'de bir tazelenir.
 */

type Form =
  | { tur: 'metin'; id?: number; baslik: string; metin: string }
  | { tur: 'sss'; id?: number; baslik: string; sss: { soru: string; cevap: string }[] }
  | { tur: 'belge'; baslik: string; dosya: File | null }
  | { tur: 'url'; id?: number; baslik: string; url: string; kapsam: 'tek' | 'site_haritasi'; en_cok: number; haftalik: boolean }
  | { tur: 'modul'; secim: string; baslik: string };

const IKON: Record<KaynakTuru, typeof FileText> = { metin: FileText, sss: HelpCircle, belge: Upload, url: Globe, modul: Layers };

function bosForm(tur: KaynakTuru): Form {
  switch (tur) {
    case 'metin':
      return { tur, baslik: '', metin: '' };
    case 'sss':
      return { tur, baslik: '', sss: [{ soru: '', cevap: '' }] };
    case 'belge':
      return { tur, baslik: '', dosya: null };
    case 'url':
      return { tur, baslik: '', url: '', kapsam: 'tek', en_cok: 20, haftalik: false };
    default:
      return { tur: 'modul', secim: '', baslik: '' };
  }
}

export default function Kaynaklar({ api, asistan, meta }: { api: AsistanApi; asistan: Asistan; meta: Meta }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [liste, setListe] = useState<Kaynak[] | null>(null);
  const [sinir, setSinir] = useState<{ sinirlar: Sinirlar; kaynak: number; sayfa: number } | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [moduller, setModuller] = useState<{ modul: string; id: number; ad: string }[] | null>(null);
  const zamanlayici = useRef<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      const r = await api.kaynaklar(asistan.id);
      setListe(r.items);
      setSinir({ sinirlar: r.sinirlar, kaynak: r.kaynak_kullanilan, sayfa: r.sayfa_kullanilan });
    } catch (e) {
      toast.error(hataMetni(t, e));
      setListe([]);
    }
  }, [api, asistan.id, t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  // İşlenen kaynak varsa kısa aralıkla tazele.
  useEffect(() => {
    if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    if (liste?.some((k) => k.durum === 'isleniyor')) zamanlayici.current = window.setTimeout(() => void yukle(), 3000);
    return () => {
      if (zamanlayici.current) window.clearTimeout(zamanlayici.current);
    };
  }, [liste, yukle]);

  useEffect(() => {
    if (form?.tur === 'modul' && moduller === null) {
      api
        .iceAktarim(asistan.id)
        .then((r) => setModuller(r.items))
        .catch(() => setModuller([]));
    }
  }, [api, asistan.id, form?.tur, moduller]);

  const duzenle = async (k: Kaynak) => {
    try {
      const d = await api.kaynak(asistan.id, k.id);
      if (d.tur === 'sss') setForm({ tur: 'sss', id: d.id, baslik: d.baslik, sss: d.sss?.length ? d.sss : [{ soru: '', cevap: '' }] });
      else if (d.tur === 'metin' || d.tur === 'belge') setForm({ tur: 'metin', id: d.id, baslik: d.baslik, metin: d.metin || '' });
      else if (d.tur === 'url')
        setForm({ tur: 'url', id: d.id, baslik: d.baslik, url: d.ayar.url || '', kapsam: d.ayar.kapsam || 'tek', en_cok: d.ayar.en_cok || 1, haftalik: d.haftalik_yenile });
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const kaydet = async () => {
    if (!form) return;
    setKaydediliyor(true);
    try {
      if (form.tur === 'belge') {
        if (!form.dosya) throw new Error('dosya');
        await api.belgeYukle(asistan.id, form.dosya, form.baslik.trim() || undefined);
      } else if (form.tur === 'modul') {
        const [modul, id] = form.secim.split(':');
        await api.kaynakEkle(asistan.id, { tur: 'modul', ayar: { modul, id: Number(id) }, ...(form.baslik.trim() ? { baslik: form.baslik.trim() } : {}) });
      } else {
        const govde: Record<string, unknown> =
          form.tur === 'metin'
            ? { baslik: form.baslik, metin: form.metin }
            : form.tur === 'sss'
              ? { baslik: form.baslik || t('aiAsistan.kaynak.sssVarsayilan'), sss: form.sss.filter((x) => x.soru.trim() || x.cevap.trim()) }
              : { baslik: form.baslik, ayar: { url: form.url, kapsam: form.kapsam, en_cok: form.kapsam === 'tek' ? 1 : form.en_cok }, haftalik_yenile: form.haftalik };
        if ('id' in form && form.id) await api.kaynakGuncelle(asistan.id, form.id, govde);
        else await api.kaynakEkle(asistan.id, { tur: form.tur, ...govde });
      }
      toast.success(t('aiAsistan.kaynak.kaydedildi'));
      setForm(null);
      await yukle();
    } catch (e) {
      toast.error(e instanceof Error && e.message === 'dosya' ? t('aiAsistan.kaynak.dosyaSec') : hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const isle = async (k: Kaynak) => {
    try {
      await api.kaynakIsle(asistan.id, k.id);
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async (k: Kaynak) => {
    if (!window.confirm(t('aiAsistan.kaynak.silOnay', { ad: k.baslik }))) return;
    try {
      await api.kaynakSil(asistan.id, k.id);
      toast.success(t('aiAsistan.kaynak.silindi'));
      await yukle();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  if (liste === null) return <Yukleniyor />;
  const doldu = sinir ? sinir.kaynak >= sinir.sinirlar.kaynak_siniri : false;

  return (
    <div className="space-y-5" data-testid="ai-kaynaklar">
      <div className={`${KART} p-4`}>
        <div className="flex flex-wrap items-center gap-2">
          <p className="me-auto text-sm text-muted-foreground">{t('aiAsistan.kaynak.aciklama')}</p>
          {sinir && (
            <>
              <Rozet testid="ai-kaynak-sayac">{t('aiAsistan.kaynak.sayac', { sayi: sinir.kaynak, sinir: sinir.sinirlar.kaynak_siniri })}</Rozet>
              <Rozet>{t('aiAsistan.kaynak.sayfaSayac', { sayi: sinir.sayfa, sinir: sinir.sinirlar.sayfa_siniri })}</Rozet>
            </>
          )}
        </div>
        {!form && (
          <div className="mt-3 flex flex-wrap gap-2">
            {(['sss', 'metin', 'belge', 'url', 'modul'] as KaynakTuru[]).map((tur) => {
              const Ikon = IKON[tur];
              return (
                <Button key={tur} type="button" variant="outline" size="sm" className={DIS_DUGME} disabled={doldu} onClick={() => setForm(bosForm(tur))} data-testid={`ai-kaynak-tur-${tur}`}>
                  <Ikon className="h-4 w-4" aria-hidden="true" />
                  {t(`aiAsistan.kaynak.tur.${tur}`)}
                </Button>
              );
            })}
          </div>
        )}
        {doldu && !form && <p className="mt-2 text-xs text-amber-200">{t('aiAsistan.hata.kaynak_siniri', { sinir: sinir?.sinirlar.kaynak_siniri })}</p>}
        {form && (
          <div className="mt-4 space-y-3 border-t border-white/10 pt-4" data-testid="ai-kaynak-formu" data-tur={form.tur}>
            <div className="flex items-center gap-2">
              <h4 className="me-auto font-semibold">{t(`aiAsistan.kaynak.tur.${form.tur}`)}</h4>
              <Button type="button" variant="ghost" size="icon" onClick={() => setForm(null)} aria-label={t('aiAsistan.vazgec')}>
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            {form.tur !== 'modul' && (
              <Alan etiket={t('aiAsistan.kaynak.baslik')} ipucu={form.tur === 'url' || form.tur === 'belge' ? t('aiAsistan.kaynak.baslikIstege') : undefined}>
                <Input value={form.baslik} onChange={(e) => setForm({ ...form, baslik: e.target.value })} maxLength={160} data-testid="ai-kaynak-baslik" />
              </Alan>
            )}
            {form.tur === 'metin' && (
              <Alan etiket={t('aiAsistan.kaynak.metin')} ipucu={t('aiAsistan.kaynak.metinIpucu')}>
                <textarea className={`${METIN_ALANI} min-h-[200px]`} value={form.metin} onChange={(e) => setForm({ ...form, metin: e.target.value })} maxLength={meta.metin_en_cok} data-testid="ai-kaynak-metin" />
              </Alan>
            )}
            {form.tur === 'sss' && (
              <div className="space-y-3">
                {form.sss.map((x, i) => (
                  <div key={i} className="grid gap-2 rounded-xl border border-white/10 p-3 md:grid-cols-[1fr_2fr_auto]">
                    <Input
                      value={x.soru}
                      onChange={(e) => setForm({ ...form, sss: form.sss.map((y, j) => (j === i ? { ...y, soru: e.target.value } : y)) })}
                      placeholder={t('aiAsistan.kaynak.soru')}
                      aria-label={t('aiAsistan.kaynak.soru')}
                      maxLength={300}
                      data-testid={`ai-sss-soru-${i}`}
                    />
                    <textarea
                      className={`${METIN_ALANI} min-h-[40px]`}
                      value={x.cevap}
                      onChange={(e) => setForm({ ...form, sss: form.sss.map((y, j) => (j === i ? { ...y, cevap: e.target.value } : y)) })}
                      placeholder={t('aiAsistan.kaynak.cevap')}
                      aria-label={t('aiAsistan.kaynak.cevap')}
                      maxLength={4000}
                      rows={2}
                      data-testid={`ai-sss-cevap-${i}`}
                    />
                    <Button type="button" variant="ghost" size="icon" aria-label={t('aiAsistan.sil')} onClick={() => setForm({ ...form, sss: form.sss.filter((_, j) => j !== i) })} disabled={form.sss.length === 1}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" className={DIS_DUGME} onClick={() => setForm({ ...form, sss: [...form.sss, { soru: '', cevap: '' }] })} data-testid="ai-sss-ekle">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('aiAsistan.kaynak.soruEkle')}
                </Button>
              </div>
            )}
            {form.tur === 'belge' && (
              <Alan etiket={t('aiAsistan.kaynak.dosya')} ipucu={t('aiAsistan.kaynak.dosyaIpucu', { turler: meta.belge_turleri.map((x) => x.toUpperCase()).join(', '), mb: meta.belge_en_cok_mb })}>
                <input
                  type="file"
                  accept={meta.belge_turleri.map((x) => `.${x}`).join(',')}
                  onChange={(e) => setForm({ ...form, dosya: e.target.files?.[0] || null })}
                  className="block w-full text-sm file:me-3 file:rounded-md file:border-0 file:bg-purple-500/20 file:px-3 file:py-1.5 file:text-white"
                  data-testid="ai-kaynak-dosya"
                />
              </Alan>
            )}
            {form.tur === 'url' && (
              <>
                <Alan etiket={t('aiAsistan.kaynak.url')} ipucu={t('aiAsistan.kaynak.urlIpucu')}>
                  <Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://" dir="ltr" maxLength={2000} data-testid="ai-kaynak-url" />
                </Alan>
                <div className="flex flex-wrap gap-4 text-sm">
                  {(['tek', 'site_haritasi'] as const).map((k) => (
                    <label key={k} className="flex items-center gap-2">
                      <input type="radio" name="kapsam" className="accent-purple-500" checked={form.kapsam === k} onChange={() => setForm({ ...form, kapsam: k })} />
                      {t(`aiAsistan.kaynak.kapsam.${k}`)}
                    </label>
                  ))}
                </div>
                {form.kapsam === 'site_haritasi' && (
                  <Alan etiket={t('aiAsistan.kaynak.enCok')} ipucu={sinir ? t('aiAsistan.kaynak.enCokIpucu', { kalan: Math.max(0, sinir.sinirlar.sayfa_siniri - sinir.sayfa) }) : undefined}>
                    <Input type="number" min={1} max={200} value={form.en_cok} onChange={(e) => setForm({ ...form, en_cok: Math.max(1, Number(e.target.value) || 1) })} className="max-w-[8rem]" />
                  </Alan>
                )}
                <Anahtar acik={form.haftalik} onDegis={(v) => setForm({ ...form, haftalik: v })} etiket={t('aiAsistan.kaynak.haftalik')} />
                <p className="text-xs text-muted-foreground">{t('aiAsistan.kaynak.robotsNotu')}</p>
              </>
            )}
            {form.tur === 'modul' && (
              <Alan etiket={t('aiAsistan.kaynak.modulSec')} ipucu={t('aiAsistan.kaynak.modulIpucu')}>
                {moduller === null ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : moduller.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('aiAsistan.kaynak.modulYok')}</p>
                ) : (
                  <select className={SECIM} value={form.secim} onChange={(e) => setForm({ ...form, secim: e.target.value })} data-testid="ai-kaynak-modul">
                    <option value="">—</option>
                    {moduller.map((m) => (
                      <option key={`${m.modul}:${m.id}`} value={`${m.modul}:${m.id}`}>
                        {t(`aiAsistan.kaynak.modul.${m.modul}`)} — {m.ad}
                      </option>
                    ))}
                  </select>
                )}
              </Alan>
            )}
            <div className="flex gap-2">
              <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor || (form.tur === 'modul' && !form.secim)} className="gap-1.5" data-testid="ai-kaynak-kaydet">
                {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('aiAsistan.kaydet')}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setForm(null)}>
                {t('aiAsistan.vazgec')}
              </Button>
            </div>
          </div>
        )}
      </div>

      {liste.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="ai-kaynak-bos">
          {t('aiAsistan.kaynak.bos')}
        </p>
      ) : (
        <ul className="space-y-2" data-testid="ai-kaynak-listesi">
          {liste.map((k) => {
            const Ikon = IKON[k.tur];
            return (
              <li key={k.id} className={`${KART} flex flex-col gap-2 p-4 sm:flex-row sm:items-center`} data-kaynak-id={k.id} data-durum={k.durum} data-tur={k.tur}>
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <Ikon className="mt-0.5 h-5 w-5 shrink-0 text-purple-300" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{k.baslik}</p>
                    <p className="truncate text-xs text-muted-foreground" dir={k.tur === 'url' ? 'ltr' : undefined}>
                      {k.tur === 'url' ? k.ayar.url : k.tur === 'belge' ? k.dosya_adi : t(`aiAsistan.kaynak.tur.${k.tur}`)}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      {k.durum === 'isleniyor' && (
                        <Rozet renk="border-sky-400/30 bg-sky-500/10 text-sky-200">
                          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                          {t('aiAsistan.kaynak.durum.isleniyor')}
                        </Rozet>
                      )}
                      {k.durum === 'hazir' && <Rozet renk="border-emerald-400/30 bg-emerald-500/10 text-emerald-200">{t('aiAsistan.kaynak.durum.hazir')}</Rozet>}
                      {k.durum === 'hata' && (
                        <Rozet renk="border-red-400/30 bg-red-500/10 text-red-200">
                          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                          {t(`aiAsistan.hata.${k.hata}`, { defaultValue: t('aiAsistan.kaynak.durum.hata') })}
                        </Rozet>
                      )}
                      {k.durum === 'hazir' && <Rozet>{t('aiAsistan.kaynak.parca', { sayi: k.parca_sayisi })}</Rozet>}
                      {k.tur === 'url' && k.sayfa_sayisi > 0 && <Rozet>{t('aiAsistan.kaynak.sayfa', { sayi: k.sayfa_sayisi })}</Rozet>}
                      {k.haftalik_yenile && <Rozet>{t('aiAsistan.kaynak.haftalikRozet')}</Rozet>}
                      <span className="text-[11px] text-muted-foreground">
                        {t('aiAsistan.kaynak.sonIsleme')}: {tarihYaz(k.son_isleme_at, dil)} · {sayiYaz(k.karakter, dil)} {t('aiAsistan.kaynak.karakter')}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {k.tur !== 'modul' && (
                    <Button type="button" variant="ghost" size="icon" aria-label={t('aiAsistan.duzenle')} onClick={() => void duzenle(k)} disabled={k.durum === 'isleniyor'}>
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  )}
                  <Button type="button" variant="ghost" size="icon" aria-label={t('aiAsistan.kaynak.yenidenIsle')} onClick={() => void isle(k)} disabled={k.durum === 'isleniyor'} data-testid="ai-kaynak-isle">
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button type="button" variant="ghost" size="icon" aria-label={t('aiAsistan.sil')} onClick={() => void sil(k)} data-testid="ai-kaynak-sil">
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
