import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, MapPin, MapPinOff, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { hataMetni, tarihSaat, type Riza, type SahaApi } from '@/lib/sahaServisi';
import { KART } from './ortak';

/**
 * Faz 6S — KVKK: teknisyenin konum rızası. Açık bilgilendirme + açık rıza (zaman + metin sürümü
 * sunucuda); istediği an geri alır. Rıza yoksa konum hiç istenmez, iş yine yapılır.
 */
export default function KonumRizasi({ api, riza, surum, onDegisti }: { api: SahaApi; riza: Riza | null; surum: string; onDegisti: (r: Riza) => void }) {
  const { t, i18n } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [mesgul, setMesgul] = useState(false);
  const gecerli = !!riza?.gecerli;

  const ver = async () => {
    setMesgul(true);
    try {
      const r = await api.rizaVer(surum);
      onDegisti({ ...r, kayitli: true });
      setAcik(false);
      toast.success(t('sahaServisi.riza.verildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const geriAl = async () => {
    setMesgul(true);
    try {
      const r = await api.rizaGeriAl();
      onDegisti({ ...r, kayitli: true, surum });
      toast.success(t('sahaServisi.riza.geriAlindi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  if (gecerli && !acik) {
    return (
      <div className={`${KART} flex flex-wrap items-center gap-2 p-3 text-sm`} data-testid="saha-riza" data-durum="var">
        <ShieldCheck className="h-4 w-4 flex-none text-emerald-300" aria-hidden="true" />
        <span className="min-w-0 flex-1 text-white/85">
          {t('sahaServisi.riza.var', { tarih: tarihSaat(riza?.verildi_at, i18n.language) })}
        </span>
        <Button size="sm" variant="ghost" className="min-h-[40px]" onClick={() => setAcik(true)}>
          {t('sahaServisi.riza.metniGor')}
        </Button>
        <Button size="sm" variant="ghost" className="min-h-[40px] text-rose-200" onClick={() => void geriAl()} disabled={mesgul} data-testid="saha-riza-geri-al">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <MapPinOff className="h-4 w-4" aria-hidden="true" />}
          {t('sahaServisi.riza.geriAl')}
        </Button>
      </div>
    );
  }

  return (
    <section className={`${KART} p-4`} aria-labelledby="saha-riza-baslik" data-testid="saha-riza" data-durum={gecerli ? 'var' : 'yok'}>
      <h3 id="saha-riza-baslik" className="flex items-center gap-2 text-base font-semibold">
        <MapPin className="h-5 w-5 text-purple-300" aria-hidden="true" />
        {t('sahaServisi.riza.baslik')}
      </h3>
      {!acik && !gecerli ? (
        <>
          <p className="mt-1 text-sm text-muted-foreground">{t('sahaServisi.riza.ozet')}</p>
          <Button className="mt-3 min-h-[44px] w-full sm:w-auto" onClick={() => setAcik(true)} data-testid="saha-riza-ac">
            {t('sahaServisi.riza.oku')}
          </Button>
        </>
      ) : (
        <div className="mt-2 space-y-3 text-sm">
          <p className="whitespace-pre-line text-white/85" data-testid="saha-riza-metni">
            {t('sahaServisi.riza.metin', { gun: 90 })}
          </p>
          <p className="text-xs text-muted-foreground">{t('sahaServisi.riza.surum', { surum })}</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            {!gecerli && (
              <Button className="min-h-[44px]" onClick={() => void ver()} disabled={mesgul} data-testid="saha-riza-ver">
                {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {t('sahaServisi.riza.onayla')}
              </Button>
            )}
            <Button variant="outline" className="min-h-[44px] !bg-transparent border-white/20" onClick={() => setAcik(false)}>
              {gecerli ? t('sahaServisi.kapat') : t('sahaServisi.riza.simdiDegil')}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
