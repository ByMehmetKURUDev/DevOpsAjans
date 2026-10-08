import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Info, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alan, GIRDI, KART, METIN_ALANI, SECIM } from '@/components/ortaklik/ortak';
import { ayarlariGetir, ayarlariKaydet, hataMetni, type ProgramAyarlari } from '@/lib/ortaklik';

const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const PARALAR = ['TRY', 'USD', 'EUR', 'GBP'];

/**
 * Faz 5K — program ayarları: başvuru açık mı, ilk satış oranı (X), tekrar eden (abonelik) faturalarında oran (Y) ve
 * süre (N ay; 0 = kapalı), iade süresi (komisyonun "beklemede" kaldığı gün),
 * para birimi başına en az ödeme, atıf kuralı (ilk / son referans), kapsam (yalnız teklifli/kodlu ya da bütün
 * ödenen faturalar) ve 7 dilde program koşulları metni (boş dilde sayfanın varsayılan metni).
 * Bilgilendirme amaçlıdır, hukuki danışmanlık değildir.
 */
export default function Ayarlar() {
  const { t } = useTranslation();
  const [a, setA] = useState<ProgramAyarlari | null>(null);
  const [kosulDili, setKosulDili] = useState('tr');
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    ayarlariGetir()
      .then(setA)
      .catch((h) => toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata')));
  }, [t]);

  if (!a) {
    return (
      <div className="flex justify-center py-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  const kaydet = async () => {
    setMesgul(true);
    try {
      setA(await ayarlariKaydet(a));
      toast.success(t('ortaklik.yonetim.kaydedildi'));
    } catch (h) {
      toast.error(hataMetni(t, h, 'ortaklik.yonetim.hata'));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className={`${KART} space-y-5 p-5`} data-testid="ortaklik-ayarlar">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={a.acik} onChange={(e) => setA({ ...a, acik: e.target.checked })} />
        {t('ortaklik.yonetim.ayar.acik')}
      </label>
      <div className="grid gap-4 md:grid-cols-3">
        <Alan etiket={t('ortaklik.yonetim.ayar.oran')}>
          <input className={GIRDI} type="number" min={0} max={90} step="0.5" value={a.varsayilan_oran}
            onChange={(e) => setA({ ...a, varsayilan_oran: Number(e.target.value) })} data-testid="ayar-oran" />
        </Alan>
        <Alan etiket={t('ortaklik.yonetim.ayar.tekrarOran')}>
          <input className={GIRDI} type="number" min={0} max={90} step="0.5" value={a.tekrar_oran}
            onChange={(e) => setA({ ...a, tekrar_oran: Number(e.target.value) })} data-testid="ayar-tekrar-oran" />
        </Alan>
        <Alan etiket={t('ortaklik.yonetim.ayar.tekrarAy')} ipucu={t('ortaklik.yonetim.ayar.tekrarIpucu')}>
          <input className={GIRDI} type="number" min={0} max={36} value={a.tekrar_ay}
            onChange={(e) => setA({ ...a, tekrar_ay: Number(e.target.value) })} data-testid="ayar-tekrar-ay" />
        </Alan>
        <Alan etiket={t('ortaklik.yonetim.ayar.bekleme')} ipucu={t('ortaklik.yonetim.ayar.beklemeIpucu')}>
          <input className={GIRDI} type="number" min={0} max={365} value={a.bekleme_gun} onChange={(e) => setA({ ...a, bekleme_gun: Number(e.target.value) })} />
        </Alan>
        <Alan etiket={t('ortaklik.yonetim.ayar.atif')}>
          <select className={SECIM} value={a.atif} onChange={(e) => setA({ ...a, atif: e.target.value as 'ilk' | 'son' })}>
            <option value="ilk">{t('ortaklik.yonetim.ayar.atif_ilk')}</option>
            <option value="son">{t('ortaklik.yonetim.ayar.atif_son')}</option>
          </select>
        </Alan>
      </div>
      <fieldset>
        <legend className="mb-2 text-sm font-medium">{t('ortaklik.yonetim.ayar.enAz')}</legend>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {PARALAR.map((p) => (
            <label key={p} className="block text-sm">
              <span className="mb-1 block text-xs text-muted-foreground">{p}</span>
              <input className={GIRDI} type="number" min={0} step="any" value={a.odeme_en_az[p] ?? 0}
                onChange={(e) => setA({ ...a, odeme_en_az: { ...a.odeme_en_az, [p]: Number(e.target.value) } })} />
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-0.5 h-4 w-4 flex-none accent-purple-500" checked={a.tum_faturalar} onChange={(e) => setA({ ...a, tum_faturalar: e.target.checked })} />
        {t('ortaklik.yonetim.ayar.tumFaturalar')}
      </label>
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium">{t('ortaklik.yonetim.ayar.kosullar')}</span>
          <select className={`${SECIM} !w-auto`} value={kosulDili} onChange={(e) => setKosulDili(e.target.value)} aria-label={t('ortaklik.yonetim.ayar.dil')}>
            {DILLER.map((d) => (
              <option key={d} value={d}>
                {d.toUpperCase()}
                {a.kosullar[d] ? ' ✓' : ''}
              </option>
            ))}
          </select>
        </div>
        <textarea className={`${METIN_ALANI} min-h-[180px]`} value={a.kosullar[kosulDili] || ''} maxLength={20000}
          dir={kosulDili === 'ar' ? 'rtl' : 'ltr'}
          onChange={(e) => setA({ ...a, kosullar: { ...a.kosullar, [kosulDili]: e.target.value } })} data-testid="ayar-kosullar" />
        <p className="mt-1 text-xs text-muted-foreground">{t('ortaklik.yonetim.ayar.kosullarIpucu')}</p>
      </div>
      <p className="flex items-start gap-2 rounded-xl border border-sky-400/20 bg-sky-500/10 p-3 text-xs text-sky-100">
        <Info className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
        {t('ortaklik.yonetim.ayar.bilgi')}
      </p>
      <Button onClick={() => void kaydet()} disabled={mesgul} className="gap-2" data-testid="ayar-kaydet">
        {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
        {t('ortaklik.yonetim.kaydet')}
      </Button>
    </div>
  );
}
