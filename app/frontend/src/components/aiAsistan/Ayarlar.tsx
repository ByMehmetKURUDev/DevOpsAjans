import { lazy, Suspense, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ImagePlus, Loader2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, Anahtar, KART, METIN_ALANI, SECIM, satirlar } from '@/components/aiAsistan/ortak';
import { hataMetni, type Asistan, type AsistanApi, type Meta } from '@/lib/aiAsistan';

const Onizleme = lazy(() => import('@/components/aiAsistan/Onizleme'));

/**
 * Faz 5A — asistan ayarları: ad, karşılama, ton, dil, marka rengi, avatar, önerilen sorular,
 * yanıt uzunluğu, "bilmiyorsam insana devret" eşiği, yasaklı konular, mesai saatleri, saklama
 * süresi, aydınlatma metni/bağlantısı, hibrit arama. Geniş ekranda yanında canlı önizleme.
 */

const ESIKLER = [
  { deger: 0.3, anahtar: 'dusuk' },
  { deger: 0.5, anahtar: 'orta' },
  { deger: 0.7, anahtar: 'yuksek' },
] as const;
const GUNLER = ['0', '1', '2', '3', '4', '5', '6'];
const SAAT_DILIMLERI = ['Europe/Istanbul', 'Europe/Berlin', 'Europe/London', 'Europe/Moscow', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Shanghai', 'America/New_York', 'UTC'];

export default function Ayarlar({
  api,
  asistan,
  meta,
  onDegisti,
  onSilindi,
}: {
  api: AsistanApi;
  asistan: Asistan;
  meta: Meta;
  onDegisti: (a: Asistan) => void;
  onSilindi: () => void;
}) {
  const { t } = useTranslation();
  const [f, setF] = useState(() => ({
    ad: asistan.ad,
    karsilama: asistan.karsilama,
    ton: asistan.ton,
    dil: asistan.dil,
    renk: asistan.renk,
    sorular: asistan.onerilen_sorular.join('\n'),
    uzunluk: asistan.yanit_uzunlugu,
    esik: asistan.devir_esigi,
    yasakli: asistan.yasakli_konular.join('\n'),
    mesaiAktif: asistan.mesai?.aktif ?? false,
    saatDilimi: asistan.mesai?.saat_dilimi || 'Europe/Istanbul',
    mesaiGunleri: Object.keys(asistan.mesai?.gunler || {}).length ? Object.keys(asistan.mesai.gunler) : ['0', '1', '2', '3', '4'],
    mesaiBas: Object.values(asistan.mesai?.gunler || {})[0]?.[0]?.[0] || '09:00',
    mesaiBit: Object.values(asistan.mesai?.gunler || {})[0]?.[0]?.[1] || '18:00',
    saklama: asistan.saklama_gun,
    aydinlatmaMetni: asistan.aydinlatma_metni,
    aydinlatmaBaglantisi: asistan.aydinlatma_baglantisi,
    aktif: asistan.aktif,
    hibrit: asistan.hibrit,
  }));
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const dosyaRef = useRef<HTMLInputElement>(null);

  const kaydet = async () => {
    setKaydediliyor(true);
    try {
      const gunler: Record<string, [string, string][]> = {};
      for (const g of f.mesaiGunleri) gunler[g] = [[f.mesaiBas, f.mesaiBit]];
      const a = await api.guncelle(asistan.id, {
        ad: f.ad,
        karsilama: f.karsilama,
        ton: f.ton,
        dil: f.dil,
        renk: f.renk,
        onerilen_sorular: satirlar(f.sorular),
        yanit_uzunlugu: f.uzunluk,
        devir_esigi: f.esik,
        yasakli_konular: satirlar(f.yasakli),
        mesai: { aktif: f.mesaiAktif, saat_dilimi: f.saatDilimi, gunler },
        saklama_gun: f.saklama,
        aydinlatma_metni: f.aydinlatmaMetni,
        aydinlatma_baglantisi: f.aydinlatmaBaglantisi,
        aktif: f.aktif,
        hibrit: f.hibrit,
      } as Partial<Asistan>);
      onDegisti(a);
      toast.success(t('aiAsistan.ayar.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const avatar = async (dosya: File | undefined) => {
    if (!dosya) return;
    try {
      onDegisti(await api.avatarYukle(asistan.id, dosya));
      toast.success(t('aiAsistan.ayar.avatarYuklendi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const sil = async () => {
    if (!window.confirm(t('aiAsistan.ayar.silOnay', { ad: asistan.ad }))) return;
    try {
      await api.sil(asistan.id);
      toast.success(t('aiAsistan.ayar.silindi'));
      onSilindi();
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  const ust = useMemo(
    () => ({ ad: f.ad || asistan.ad, renk: /^#[0-9a-f]{6}$/i.test(f.renk) ? f.renk : asistan.renk, karsilama: f.karsilama || null, onerilen_sorular: satirlar(f.sorular).slice(0, 6) }),
    [f.ad, f.renk, f.karsilama, f.sorular, asistan.ad, asistan.renk]
  );

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="space-y-5" data-testid="ai-ayarlar">
        <div className={`${KART} grid gap-4 p-5 md:grid-cols-2`}>
          <Alan etiket={t('aiAsistan.ayar.ad')}>
            <Input value={f.ad} onChange={(e) => setF({ ...f, ad: e.target.value })} maxLength={meta.sinir.ad} data-testid="ai-ayar-ad" />
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.renk')}>
            <div className="flex gap-2">
              <input type="color" value={/^#[0-9a-f]{6}$/i.test(f.renk) ? f.renk : '#7c3aed'} onChange={(e) => setF({ ...f, renk: e.target.value })} className="h-10 w-12 rounded border border-white/10 bg-transparent" aria-label={t('aiAsistan.ayar.renk')} />
              <Input value={f.renk} onChange={(e) => setF({ ...f, renk: e.target.value })} maxLength={7} dir="ltr" className="max-w-[8rem]" data-testid="ai-ayar-renk" />
            </div>
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.karsilama')} ipucu={t('aiAsistan.ayar.karsilamaIpucu')} className="md:col-span-2">
            <textarea className={METIN_ALANI} value={f.karsilama} onChange={(e) => setF({ ...f, karsilama: e.target.value })} maxLength={meta.sinir.karsilama} data-testid="ai-ayar-karsilama" />
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.ton')}>
            <select className={SECIM} value={f.ton} onChange={(e) => setF({ ...f, ton: e.target.value as Asistan['ton'] })}>
              {meta.tonlar.map((x) => (
                <option key={x} value={x}>
                  {t(`aiAsistan.ayar.tonlar.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.dil')} ipucu={t('aiAsistan.ayar.dilIpucu')}>
            <select className={SECIM} value={f.dil} onChange={(e) => setF({ ...f, dil: e.target.value as Asistan['dil'] })} data-testid="ai-ayar-dil">
              {meta.dil_secenekleri.map((x) => (
                <option key={x} value={x}>
                  {t(`aiAsistan.ayar.diller.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.uzunluk')}>
            <select className={SECIM} value={f.uzunluk} onChange={(e) => setF({ ...f, uzunluk: e.target.value as Asistan['yanit_uzunlugu'] })}>
              {meta.uzunluklar.map((x) => (
                <option key={x} value={x}>
                  {t(`aiAsistan.ayar.uzunluklar.${x}`)}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.esik')} ipucu={t('aiAsistan.ayar.esikIpucu')}>
            <select className={SECIM} value={String(f.esik)} onChange={(e) => setF({ ...f, esik: Number(e.target.value) })} data-testid="ai-ayar-esik">
              {ESIKLER.map((x) => (
                <option key={x.anahtar} value={String(x.deger)}>
                  {t(`aiAsistan.ayar.esikler.${x.anahtar}`)}
                </option>
              ))}
              {!ESIKLER.some((x) => x.deger === f.esik) && <option value={String(f.esik)}>{f.esik}</option>}
            </select>
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.sorular')} ipucu={t('aiAsistan.ayar.sorularIpucu')} className="md:col-span-2">
            <textarea className={METIN_ALANI} value={f.sorular} onChange={(e) => setF({ ...f, sorular: e.target.value })} data-testid="ai-ayar-sorular" />
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.yasakli')} ipucu={t('aiAsistan.ayar.yasakliIpucu')} className="md:col-span-2">
            <textarea className={METIN_ALANI} value={f.yasakli} onChange={(e) => setF({ ...f, yasakli: e.target.value })} />
          </Alan>
          <div className="md:col-span-2">
            <span className="mb-1 block text-sm font-medium text-white/90">{t('aiAsistan.ayar.avatar')}</span>
            <div className="flex flex-wrap items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full" style={{ background: asistan.renk }}>
                {asistan.avatar && <img src={asistan.avatar} alt="" className="h-full w-full object-cover" />}
              </span>
              <input ref={dosyaRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => void avatar(e.target.files?.[0])} />
              <Button type="button" variant="outline" size="sm" className="gap-1.5 !bg-transparent" onClick={() => dosyaRef.current?.click()}>
                <ImagePlus className="h-4 w-4" aria-hidden="true" />
                {t('aiAsistan.ayar.avatarYukle')}
              </Button>
              {asistan.avatar && (
                <Button type="button" variant="ghost" size="sm" onClick={() => void api.avatarSil(asistan.id).then(onDegisti).catch((e) => toast.error(hataMetni(t, e)))}>
                  {t('aiAsistan.ayar.avatarKaldir')}
                </Button>
              )}
            </div>
          </div>
        </div>

        <div className={`${KART} space-y-3 p-5`}>
          <Anahtar acik={f.mesaiAktif} onDegis={(v) => setF({ ...f, mesaiAktif: v })} etiket={t('aiAsistan.ayar.mesai')} testid="ai-ayar-mesai" />
          <p className="text-xs text-muted-foreground">{t('aiAsistan.ayar.mesaiIpucu')}</p>
          {f.mesaiAktif && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {GUNLER.map((g) => (
                  <label key={g} className="flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 text-xs">
                    <input
                      type="checkbox"
                      className="accent-purple-500"
                      checked={f.mesaiGunleri.includes(g)}
                      onChange={(e) => setF({ ...f, mesaiGunleri: e.target.checked ? [...f.mesaiGunleri, g].sort() : f.mesaiGunleri.filter((x) => x !== g) })}
                    />
                    {t(`aiAsistan.ayar.gunler.${g}`)}
                  </label>
                ))}
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <Alan etiket={t('aiAsistan.ayar.mesaiBas')}>
                  <Input type="time" value={f.mesaiBas} onChange={(e) => setF({ ...f, mesaiBas: e.target.value })} className="w-32" />
                </Alan>
                <Alan etiket={t('aiAsistan.ayar.mesaiBit')}>
                  <Input type="time" value={f.mesaiBit} onChange={(e) => setF({ ...f, mesaiBit: e.target.value })} className="w-32" />
                </Alan>
                <Alan etiket={t('aiAsistan.ayar.saatDilimi')}>
                  <select className={`${SECIM} w-56`} value={f.saatDilimi} onChange={(e) => setF({ ...f, saatDilimi: e.target.value })}>
                    {[...new Set([f.saatDilimi, ...SAAT_DILIMLERI])].map((z) => (
                      <option key={z} value={z}>
                        {z.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                </Alan>
              </div>
            </div>
          )}
        </div>

        <div className={`${KART} grid gap-4 p-5 md:grid-cols-2`}>
          <Alan etiket={t('aiAsistan.ayar.saklama')} ipucu={t('aiAsistan.ayar.saklamaIpucu')}>
            <select className={SECIM} value={f.saklama} onChange={(e) => setF({ ...f, saklama: Number(e.target.value) })} data-testid="ai-ayar-saklama">
              {meta.saklama_secenekleri.map((g) => (
                <option key={g} value={g}>
                  {t('aiAsistan.ayar.gun', { sayi: g })}
                </option>
              ))}
            </select>
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.aydinlatmaBaglantisi')} ipucu={t('aiAsistan.ayar.aydinlatmaBaglantisiIpucu')}>
            <Input value={f.aydinlatmaBaglantisi} onChange={(e) => setF({ ...f, aydinlatmaBaglantisi: e.target.value })} placeholder="https://" dir="ltr" />
          </Alan>
          <Alan etiket={t('aiAsistan.ayar.aydinlatmaMetni')} ipucu={t('aiAsistan.ayar.aydinlatmaMetniIpucu')} className="md:col-span-2">
            <textarea className={METIN_ALANI} value={f.aydinlatmaMetni} onChange={(e) => setF({ ...f, aydinlatmaMetni: e.target.value })} maxLength={meta.sinir.aydinlatma} />
          </Alan>
          <Anahtar acik={f.aktif} onDegis={(v) => setF({ ...f, aktif: v })} etiket={t('aiAsistan.ayar.aktif')} testid="ai-ayar-aktif" />
          <div>
            <Anahtar acik={f.hibrit} onDegis={(v) => setF({ ...f, hibrit: v })} etiket={t('aiAsistan.ayar.hibrit')} devreDisi={!meta.gomme_hazir && !f.hibrit} />
            <p className="mt-1 text-xs text-muted-foreground">{t(meta.gomme_hazir ? 'aiAsistan.ayar.hibritIpucu' : 'aiAsistan.ayar.hibritYok')}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5" data-testid="ai-ayar-kaydet">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('aiAsistan.kaydet')}
          </Button>
          <Button type="button" variant="ghost" className="ms-auto gap-1.5 text-red-300 hover:text-red-200" onClick={() => void sil()} data-testid="ai-asistan-sil">
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t('aiAsistan.ayar.sil')}
          </Button>
        </div>
      </div>
      <div className="hidden xl:block">
        <div className="sticky top-4">
          <Suspense fallback={null}>
            <Onizleme asistan={asistan} ust={ust} />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
