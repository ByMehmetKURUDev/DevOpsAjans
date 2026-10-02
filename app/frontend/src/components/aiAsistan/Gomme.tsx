import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, ExternalLink, KeyRound, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, Anahtar, KART, METIN_ALANI, SECIM, kopyala, satirlar } from '@/components/aiAsistan/ortak';
import { gommeKodu, hataMetni, type Asistan, type AsistanApi, type Meta } from '@/lib/aiAsistan';

/**
 * Faz 5A — gömme kodu (tek satır betik: sağ altta balon + panel), paylaşılabilir tam sayfa
 * bağlantısı ve izinli alan adları (asistan yalnız bu sitelerde açılır; boş = her yer).
 * Anahtarı yenilemek eski gömme kodunu ve bağlantıyı geçersiz kılar.
 */

export default function Gomme({ api, asistan, meta, onDegisti }: { api: AsistanApi; asistan: Asistan; meta: Meta; onDegisti: (a: Asistan) => void }) {
  const { t } = useTranslation();
  const [dil, setDil] = useState('');
  const [kokenler, setKokenler] = useState(asistan.izinli_kokenler.join('\n'));
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const kod = gommeKodu(meta.widget_adresi, asistan.anahtar, dil || undefined, asistan.renk);

  const kaydet = async (govde: Partial<Asistan>) => {
    setKaydediliyor(true);
    try {
      const a = await api.guncelle(asistan.id, govde);
      onDegisti(a);
      setKokenler(a.izinli_kokenler.join('\n'));
      toast.success(t('aiAsistan.ayar.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  const yenile = async () => {
    if (!window.confirm(t('aiAsistan.gomme.yenileOnay'))) return;
    try {
      onDegisti(await api.anahtarYenile(asistan.id));
      toast.success(t('aiAsistan.gomme.yenilendi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    }
  };

  return (
    <div className="space-y-5" data-testid="ai-gomme">
      <div className={`${KART} space-y-3 p-5`}>
        <h4 className="font-semibold">{t('aiAsistan.gomme.kodBaslik')}</h4>
        <p className="text-sm text-muted-foreground">{t('aiAsistan.gomme.kodAciklama')}</p>
        <Alan etiket={t('aiAsistan.gomme.dil')}>
          <select className={`${SECIM} max-w-xs`} value={dil} onChange={(e) => setDil(e.target.value)} data-testid="ai-gomme-dil">
            <option value="">{t('aiAsistan.gomme.dilSayfa')}</option>
            {meta.diller.map((d) => (
              <option key={d} value={d}>
                {t(`aiAsistan.ayar.diller.${d}`)}
              </option>
            ))}
          </select>
        </Alan>
        <textarea readOnly className={`${METIN_ALANI} font-mono text-xs`} value={kod} dir="ltr" rows={2} data-testid="ai-gomme-kodu" onFocus={(e) => e.currentTarget.select()} />
        <Button type="button" variant="outline" size="sm" className="gap-1.5 !bg-transparent" onClick={() => void kopyala(kod, t('aiAsistan.kopyalandi'), t('aiAsistan.kopyalanamadi'))}>
          <Copy className="h-4 w-4" aria-hidden="true" />
          {t('aiAsistan.kopyala')}
        </Button>
      </div>

      <div className={`${KART} space-y-3 p-5`}>
        <h4 className="font-semibold">{t('aiAsistan.gomme.sayfaBaslik')}</h4>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input readOnly value={asistan.adres} dir="ltr" data-testid="ai-tam-sayfa-adresi" onFocus={(e) => e.currentTarget.select()} />
          <Button type="button" variant="outline" size="sm" className="gap-1.5 !bg-transparent" onClick={() => void kopyala(asistan.adres, t('aiAsistan.kopyalandi'), t('aiAsistan.kopyalanamadi'))}>
            <Copy className="h-4 w-4" aria-hidden="true" />
            {t('aiAsistan.kopyala')}
          </Button>
          <a href={asistan.adres} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 self-center text-sm text-purple-200 hover:underline">
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t('aiAsistan.gomme.ac')}
          </a>
        </div>
        <Anahtar acik={asistan.tam_sayfa} onDegis={(v) => void kaydet({ tam_sayfa: v })} etiket={t('aiAsistan.gomme.tamSayfa')} testid="ai-tam-sayfa" />
      </div>

      <div className={`${KART} space-y-3 p-5`}>
        <h4 className="font-semibold">{t('aiAsistan.gomme.kokenBaslik')}</h4>
        <p className="text-sm text-muted-foreground">{t('aiAsistan.gomme.kokenAciklama')}</p>
        <textarea className={METIN_ALANI} value={kokenler} onChange={(e) => setKokenler(e.target.value)} placeholder={'ornek.com\nmagaza.ornek.com'} dir="ltr" data-testid="ai-izinli-kokenler" />
        <Button type="button" onClick={() => void kaydet({ izinli_kokenler: satirlar(kokenler) })} disabled={kaydediliyor} className="gap-1.5" data-testid="ai-gomme-kaydet">
          {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {t('aiAsistan.kaydet')}
        </Button>
      </div>

      <div className={`${KART} flex flex-col gap-3 p-5 sm:flex-row sm:items-center`}>
        <p className="flex-1 text-sm text-muted-foreground">{t('aiAsistan.gomme.yenileAciklama')}</p>
        <Button type="button" variant="outline" size="sm" className="gap-1.5 !bg-transparent" onClick={() => void yenile()}>
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          {t('aiAsistan.gomme.yenile')}
        </Button>
      </div>
    </div>
  );
}
