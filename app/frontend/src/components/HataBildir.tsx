import { useEffect, useRef, useState } from 'react';
import { Bug, ImagePlus, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  EN_BUYUK_EKRAN,
  GERI_BILDIRIM_TURLERI,
  IZINLI_GORSELLER,
  ProjeHatasi,
  geriBildirimGonder,
  type GeriBildirim,
  type GeriBildirimTuru,
} from '@/lib/projeYonetimi';

interface Props {
  projeler: { id: number | string; title: string }[];
  onGonderildi?: (fb: GeriBildirim) => void;
}

const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

/** Tarayıcı bilgisi: user agent · ekran / görünüm alanı · dil (otomatik; dilden bağımsız biçim). */
function tarayiciBilgisi(): string {
  try {
    const ekran = `${window.screen?.width ?? 0}×${window.screen?.height ?? 0}`;
    const alan = `${window.innerWidth}×${window.innerHeight}`;
    return `${navigator.userAgent} · ${ekran} / ${alan} · ${navigator.language}`.slice(0, 400);
  } catch {
    return '';
  }
}

/**
 * Müşteri paneli › "Hata bildir" (Faz 2B): sağ altta küçük düğme + form.
 *
 * Başlık, açıklama, sayfa adresi (bulunduğu sayfa önerilir), tür, proje ve
 * isteğe bağlı ekran görüntüsü. Görsel tarayıcıda da süzülüyor (tür/boyut)
 * ama asıl doğrulama sunucuda: dosyanın imzasına bakılıyor, ≤5 MB.
 * Tarayıcı bilgisi otomatik ekleniyor ve formda gösteriliyor.
 */
export default function HataBildir({ projeler, onGonderildi }: Props) {
  const { t } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [form, setForm] = useState({ baslik: '', aciklama: '', sayfa: '', tur: 'hata' as GeriBildirimTuru, proje: '' });
  const [dosya, setDosya] = useState<File | null>(null);
  const [onizleme, setOnizleme] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const ilkAlan = useRef<HTMLInputElement>(null);
  const dugme = useRef<HTMLButtonElement>(null);
  const tarayici = acik ? tarayiciBilgisi() : '';

  useEffect(() => {
    if (!acik) return;
    setForm((f) => ({
      ...f,
      sayfa: f.sayfa || window.location.href,
      proje: f.proje || (projeler.length === 1 ? String(projeler[0].id) : ''),
    }));
    const zaman = setTimeout(() => ilkAlan.current?.focus(), 30);
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAcik(false);
    };
    window.addEventListener('keydown', tus);
    return () => {
      clearTimeout(zaman);
      window.removeEventListener('keydown', tus);
    };
  }, [acik, projeler]);

  useEffect(() => {
    if (!acik) dugme.current?.focus({ preventScroll: true } as FocusOptions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [acik]);

  useEffect(
    () => () => {
      if (onizleme) URL.revokeObjectURL(onizleme);
    },
    [onizleme],
  );

  const dosyaSec = (f: File | null) => {
    if (onizleme) URL.revokeObjectURL(onizleme);
    setOnizleme(null);
    setDosya(null);
    if (!f) return;
    if (!IZINLI_GORSELLER.includes(f.type)) {
      toast.error(t('geriBildirim.dosyaTur'));
      return;
    }
    if (f.size > EN_BUYUK_EKRAN) {
      toast.error(t('geriBildirim.dosyaBuyuk'));
      return;
    }
    setDosya(f);
    setOnizleme(URL.createObjectURL(f));
  };

  const gonder = async () => {
    if (!form.baslik.trim()) {
      toast.error(t('geriBildirim.hata.baslik_gerekli'));
      return;
    }
    setGonderiliyor(true);
    try {
      const fb = await geriBildirimGonder({
        baslik: form.baslik.trim(),
        aciklama: form.aciklama.trim() || undefined,
        tur: form.tur,
        sayfa_adresi: form.sayfa.trim() || undefined,
        tarayici,
        proje_id: form.proje ? Number(form.proje) : null,
        ekran: dosya,
      });
      toast.success(t('geriBildirim.gonderildi'));
      onGonderildi?.(fb);
      setForm({ baslik: '', aciklama: '', sayfa: '', tur: 'hata', proje: '' });
      dosyaSec(null);
      setAcik(false);
    } catch (h) {
      toast.error(
        h instanceof ProjeHatasi ? t(`geriBildirim.hata.${h.kod}`, { defaultValue: t('geriBildirim.hata.genel') }) : t('geriBildirim.hata.genel'),
      );
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <>
      <button
        ref={dugme}
        type="button"
        onClick={() => setAcik(true)}
        className="fixed bottom-40 end-6 z-40 inline-flex h-11 items-center gap-2 rounded-full border border-rose-400/40 bg-[#1b0e1e]/90 px-3 text-xs font-semibold text-rose-100 shadow-lg backdrop-blur transition-colors hover:border-rose-300/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-300 sm:bottom-24 sm:end-24"
        aria-label={t('geriBildirim.dugmeAria')}
        aria-haspopup="dialog"
        data-testid="hata-bildir"
      >
        <Bug className="h-4 w-4" aria-hidden="true" />
        <span className="hidden sm:inline">{t('geriBildirim.dugme')}</span>
      </button>

      {acik && (
        <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={() => setAcik(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="hata-bildir-baslik"
            onClick={(e) => e.stopPropagation()}
            className="cam-kart max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-background/95 p-5 shadow-2xl backdrop-blur-xl sm:rounded-3xl"
            data-testid="hata-bildir-formu"
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 id="hata-bildir-baslik" className="flex items-center gap-2 text-lg font-semibold">
                  <Bug className="h-5 w-5 text-rose-300" aria-hidden="true" /> {t('geriBildirim.baslik')}
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">{t('geriBildirim.aciklama')}</p>
              </div>
              <button type="button" onClick={() => setAcik(false)} aria-label={t('geriBildirim.kapat')} className="rounded-md p-1 hover:bg-white/10">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form
              className="grid gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                void gonder();
              }}
            >
              <fieldset className="flex flex-wrap gap-2">
                <legend className="sr-only">{t('geriBildirim.alan.tur')}</legend>
                {GERI_BILDIRIM_TURLERI.map((tur) => (
                  <label
                    key={tur}
                    className={`cursor-pointer rounded-full px-3 py-1 text-xs ${
                      form.tur === tur ? 'bg-rose-500/20 text-rose-100 ring-1 ring-rose-400/40' : 'bg-white/5 text-muted-foreground'
                    }`}
                  >
                    <input
                      type="radio"
                      name="hb-tur"
                      value={tur}
                      checked={form.tur === tur}
                      onChange={() => setForm({ ...form, tur })}
                      className="sr-only"
                    />
                    {t(`geriBildirim.tur.${tur}`)}
                  </label>
                ))}
              </fieldset>
              <label className="grid gap-1 text-xs">
                {t('geriBildirim.alan.baslik')}
                <Input
                  ref={ilkAlan}
                  value={form.baslik}
                  onChange={(e) => setForm({ ...form, baslik: e.target.value })}
                  maxLength={200}
                  required
                  data-testid="hb-baslik"
                />
              </label>
              <label className="grid gap-1 text-xs">
                {t('geriBildirim.alan.aciklama')}
                <textarea
                  value={form.aciklama}
                  onChange={(e) => setForm({ ...form, aciklama: e.target.value })}
                  rows={4}
                  maxLength={4000}
                  className="rounded-md border border-white/10 bg-white/5 p-2 text-sm"
                  data-testid="hb-aciklama"
                />
              </label>
              <label className="grid gap-1 text-xs">
                {t('geriBildirim.alan.sayfa')}
                <Input value={form.sayfa} onChange={(e) => setForm({ ...form, sayfa: e.target.value })} maxLength={500} inputMode="url" data-testid="hb-sayfa" />
              </label>
              {projeler.length > 0 && (
                <label className="grid gap-1 text-xs">
                  {t('geriBildirim.alan.proje')}
                  <select value={form.proje} onChange={(e) => setForm({ ...form, proje: e.target.value })} className={SECIM} data-testid="hb-proje">
                    <option value="">{t('geriBildirim.alan.projeSec')}</option>
                    {projeler.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="grid gap-1 text-xs">
                <span>{t('geriBildirim.alan.ekran')}</span>
                <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-white/15 p-3 text-muted-foreground hover:border-rose-300/50">
                  <ImagePlus className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 truncate">{dosya ? dosya.name : t('geriBildirim.alan.ekranIpucu')}</span>
                  <input
                    type="file"
                    accept={IZINLI_GORSELLER.join(',')}
                    onChange={(e) => dosyaSec(e.target.files?.[0] || null)}
                    className="sr-only"
                    data-testid="hb-ekran"
                  />
                </label>
                {onizleme && (
                  <div className="relative mt-1">
                    <img src={onizleme} alt="" className="max-h-40 w-full rounded-md object-contain" />
                    <button
                      type="button"
                      onClick={() => dosyaSec(null)}
                      className="absolute end-1 top-1 rounded-full bg-black/60 p-1"
                      aria-label={t('geriBildirim.dosyaKaldir')}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
              <p className="break-words text-[10px] leading-relaxed text-muted-foreground">{t('geriBildirim.otomatik', { bilgi: tarayici })}</p>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={() => setAcik(false)}>
                  {t('geriBildirim.iptal')}
                </Button>
                <Button type="submit" disabled={gonderiliyor} className="gap-2" data-testid="hb-gonder">
                  {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
                  {t('geriBildirim.gonder')}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
