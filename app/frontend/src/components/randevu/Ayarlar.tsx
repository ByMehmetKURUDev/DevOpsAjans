import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ImagePlus, Loader2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, Anahtar, DIS_DUGME, KART, METIN_ALANI, SECIM, sureYaz } from '@/components/randevu/ortak';
import { hataMetni, type Meta, type RandevuApi, type Sayfa } from '@/lib/randevu';
import { DIL_ADLARI, saatDilimleri, tzFarki } from '@/lib/randevuOrtak';

/** Faz 5R — sayfa ayarları: başlık, adres, karşılama, logo, renk, saat dilimi, dil, hatırlatmalar, KVKK. */

const IPTAL_SINIRLARI = [0, 30, 60, 120, 240, 720, 1440, 2880];

export default function Ayarlar({
  api,
  meta,
  sayfa,
  onKaydedildi,
  onSilindi,
}: {
  api: RandevuApi;
  meta: Meta;
  sayfa: Sayfa;
  onKaydedildi: (s: Sayfa) => void;
  onSilindi: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [g, setG] = useState({
    baslik: sayfa.baslik,
    slug: sayfa.slug,
    karsilama: sayfa.karsilama,
    renk: sayfa.renk,
    saat_dilimi: sayfa.saat_dilimi,
    dil: sayfa.dil,
    arama_motoru: sayfa.arama_motoru,
    hatirlatmalar: sayfa.hatirlatmalar,
    iptal_sinir_dk: sayfa.iptal_sinir_dk,
    saklama_gun: sayfa.saklama_gun,
    aktif: sayfa.aktif,
  });
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [logoYukleniyor, setLogoYukleniyor] = useState(false);
  const girdi = useRef<HTMLInputElement>(null);
  const dilimler = useMemo(() => saatDilimleri([sayfa.saat_dilimi, meta.varsayilan_saat_dilimi]), [sayfa.saat_dilimi, meta.varsayilan_saat_dilimi]);
  const alan = <K extends keyof typeof g>(k: K, v: (typeof g)[K]) => setG((x) => ({ ...x, [k]: v }));

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      onKaydedildi(await api.guncelle(sayfa.id, { ...g, slug: g.slug.trim().toLowerCase() }));
      toast.success(t('randevu.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const logo = async (dosya: File | undefined) => {
    if (!dosya) return;
    if (dosya.size > 5 * 1024 * 1024) {
      toast.error(t('randevu.hata.gorsel_buyuk', { en_cok_mb: 5 }));
      return;
    }
    setLogoYukleniyor(true);
    try {
      onKaydedildi(await api.logoYukle(sayfa.id, dosya));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setLogoYukleniyor(false);
      if (girdi.current) girdi.current.value = '';
    }
  };

  const hatirlatmaDegis = (dk: number, acik: boolean) => {
    const yeni = acik ? [...new Set([...g.hatirlatmalar, dk])] : g.hatirlatmalar.filter((x) => x !== dk);
    if (yeni.length > meta.en_cok_hatirlatma) {
      toast.error(t('randevu.ayarlar.hatirlatmaSiniri', { sayi: meta.en_cok_hatirlatma }));
      return;
    }
    alan('hatirlatmalar', yeni.sort((a, b) => b - a));
  };

  return (
    <div className="grid gap-4" data-testid="randevu-ayarlar">
      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-4 text-base font-semibold">{t('randevu.ayarlar.sayfa')}</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <Alan etiket={t('randevu.ayarlar.baslik')}>
            <Input value={g.baslik} onChange={(e) => alan('baslik', e.target.value)} maxLength={120} data-testid="randevu-ayar-baslik" />
          </Alan>
          <Alan etiket={t('randevu.ayarlar.slug')} ipucu={t('randevu.ayarlar.slugIpucu')}>
            <div className="flex items-center gap-1">
              <span className="text-xs text-muted-foreground" dir="ltr">
                /randevu/
              </span>
              <Input value={g.slug} onChange={(e) => alan('slug', e.target.value.toLowerCase())} maxLength={50} dir="ltr" data-testid="randevu-ayar-slug" />
            </div>
          </Alan>
          <Alan etiket={t('randevu.ayarlar.karsilama')} className="md:col-span-2">
            <textarea className={METIN_ALANI} value={g.karsilama} onChange={(e) => alan('karsilama', e.target.value)} maxLength={1000} placeholder={t('randevu.ayarlar.karsilamaOrnek')} />
          </Alan>
          <div className="text-sm">
            <span className="mb-1 block font-medium text-white/90">{t('randevu.ayarlar.logo')}</span>
            <div className="flex items-center gap-3">
              <div className="flex h-14 w-14 flex-none items-center justify-center overflow-hidden rounded-xl border border-white/10" style={{ background: g.renk }}>
                {sayfa.logo ? <img src={sayfa.logo} alt="" width={56} height={56} className="h-full w-full object-cover" /> : <ImagePlus className="h-5 w-5 text-white/70" aria-hidden="true" />}
              </div>
              <input ref={girdi} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => void logo(e.target.files?.[0])} data-testid="randevu-logo-girdi" />
              <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => girdi.current?.click()} disabled={logoYukleniyor}>
                {logoYukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
                {sayfa.logo ? t('randevu.ayarlar.logoDegistir') : t('randevu.ayarlar.logoYukle')}
              </Button>
              {sayfa.logo && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  aria-label={t('randevu.ayarlar.logoKaldir')}
                  onClick={async () => {
                    try {
                      onKaydedildi(await api.logoSil(sayfa.id));
                    } catch (e) {
                      toast.error(hataMetni(t, e));
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
            </div>
            <span className="mt-1 block text-xs text-muted-foreground">{t('randevu.ayarlar.logoIpucu')}</span>
          </div>
          <Alan etiket={t('randevu.ayarlar.renk')}>
            <input type="color" className="h-10 w-20 rounded-md border border-white/10 bg-transparent" value={g.renk} onChange={(e) => alan('renk', e.target.value)} />
          </Alan>
          <Alan etiket={t('randevu.ayarlar.saatDilimi')} ipucu={t('randevu.ayarlar.saatDilimiIpucu')}>
            <select className={SECIM} value={g.saat_dilimi} onChange={(e) => alan('saat_dilimi', e.target.value)}>
              {dilimler.map((z) => (
                <option key={z} value={z}>
                  {z.replace(/_/g, ' ')} ({tzFarki(z, dil)})
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('randevu.ayarlar.dil')} ipucu={t('randevu.ayarlar.dilIpucu')}>
            <select className={SECIM} value={g.dil} onChange={(e) => alan('dil', e.target.value as Sayfa['dil'])}>
              {meta.diller.map((d) => (
                <option key={d} value={d}>
                  {DIL_ADLARI[d]}
                </option>
              ))}
            </select>
          </Alan>
          <div className="md:col-span-2 grid gap-2">
            <Anahtar acik={g.aktif} onDegis={(v) => alan('aktif', v)} etiket={t('randevu.ayarlar.aktif')} />
            <Anahtar acik={g.arama_motoru} onDegis={(v) => alan('arama_motoru', v)} etiket={t('randevu.ayarlar.aramaMotoru')} />
            <p className="ms-6 text-xs text-muted-foreground">{t('randevu.ayarlar.aramaMotoruIpucu')}</p>
          </div>
        </div>
      </section>

      <section className={`${KART} p-4 sm:p-6`}>
        <h3 className="mb-4 text-base font-semibold">{t('randevu.ayarlar.bildirimler')}</h3>
        <fieldset>
          <legend className="mb-2 text-sm font-medium">{t('randevu.ayarlar.hatirlatmalar')}</legend>
          <div className="flex flex-wrap gap-3" data-testid="randevu-hatirlatmalar">
            {meta.hatirlatma_secenekleri.map((dk) => (
              <Anahtar key={dk} acik={g.hatirlatmalar.includes(dk)} onDegis={(v) => hatirlatmaDegis(dk, v)} etiket={t('randevu.ayarlar.once', { sure: sureYaz(t, dk) })} />
            ))}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t('randevu.ayarlar.hatirlatmaIpucu')}</p>
        </fieldset>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Alan etiket={t('randevu.ayarlar.iptalSiniri')} ipucu={t('randevu.ayarlar.iptalSiniriIpucu')}>
            <select className={SECIM} value={g.iptal_sinir_dk} onChange={(e) => alan('iptal_sinir_dk', Number(e.target.value))}>
              {[...new Set([...IPTAL_SINIRLARI, g.iptal_sinir_dk])].sort((a, b) => a - b).map((dk) => (
                <option key={dk} value={dk}>
                  {dk === 0 ? t('randevu.ayarlar.sinirYok') : t('randevu.ayarlar.kala', { sure: sureYaz(t, dk) })}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('randevu.ayarlar.saklama')} ipucu={t('randevu.ayarlar.saklamaIpucu')}>
            <Input type="number" min={30} max={1095} value={g.saklama_gun} onChange={(e) => alan('saklama_gun', Number(e.target.value) || 30)} />
          </Alan>
        </div>
      </section>

      <div className="flex justify-end">
        <Button onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="randevu-ayar-kaydet">
          {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('randevu.kaydet')}
        </Button>
      </div>

      <section className="rounded-2xl border border-red-500/30 bg-red-500/5 p-4 sm:p-6">
        <h3 className="mb-1 text-base font-semibold text-red-200">{t('randevu.ayarlar.silBaslik')}</h3>
        <p className="mb-3 text-sm text-muted-foreground">{t('randevu.ayarlar.silAciklama')}</p>
        <Button
          variant="outline"
          className="gap-1.5 border-red-400/40 !bg-transparent text-red-200"
          onClick={async () => {
            if (!window.confirm(t('randevu.ayarlar.silOnay', { ad: sayfa.baslik }))) return;
            try {
              await api.sil(sayfa.id);
              toast.success(t('randevu.silindi'));
              onSilindi();
            } catch (e) {
              toast.error(hataMetni(t, e));
            }
          }}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          {t('randevu.ayarlar.sil')}
        </Button>
      </section>
    </div>
  );
}
