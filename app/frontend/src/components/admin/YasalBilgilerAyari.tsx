import { useEffect, useState } from 'react';
import { ExternalLink, Loader2, Save, Scale } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { saveSiteSetting, type SettingRow, type SettingsMap } from '@/lib/siteSettings';
import { LANGUAGE_CODES, YASAL_SAYFALAR, localizedPath } from '../../../prerender/site.js';
import { YASAL_ANAHTARLAR, YASAL_VARSAYILAN } from '../../../prerender/yasal-veri.js';

/**
 * Site Ayarları › Yasal bilgiler (Faz 3Y).
 *
 * Gizlilik/KVKK, Kullanım Koşulları ve Çerez Politikası sayfalarındaki veri
 * sorumlusu bilgileri. Değerler herkese açık site ayarı (`yasal_*`) olarak
 * saklanıyor — sayfada zaten gösteriliyorlar; yazma yalnız yöneticide.
 * Boş adres/KEP/VKN/MERSİS sayfada hiç basılmıyor. Prerender bu değerleri
 * bir sonraki yayında canlı API'den okuyor; ziyaretçi tarafında hemen geçerli.
 *
 * Etiketler `ek/yasalAyar` paketinde (AdminPanel bu bileşeni ekliLazy ile yüklüyor).
 */

type Alan = 'unvan' | 'eposta' | 'adres' | 'kep' | 'vkn' | 'mersis' | 'sonGuncelleme';
const ALANLAR: Alan[] = ['unvan', 'eposta', 'adres', 'kep', 'vkn', 'mersis', 'sonGuncelleme'];
const EPOSTA = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TARIH = /^\d{4}-\d{2}-\d{2}$/;

export default function YasalBilgilerAyari({
  settingRows,
  settings,
  onSaved,
}: {
  settingRows: SettingRow[];
  settings: SettingsMap;
  onSaved: () => Promise<void> | void;
}) {
  const { t, i18n } = useTranslation();
  const [taslak, setTaslak] = useState<Record<Alan, string>>(() => ilkDeger(settingRows));
  const [kaydediliyor, setKaydediliyor] = useState(false);

  useEffect(() => {
    setTaslak(ilkDeger(settingRows));
  }, [settingRows]);

  const yerTutucu: Partial<Record<Alan, string>> = {
    unvan: YASAL_VARSAYILAN.unvan,
    eposta: (settings.contact_email || '').trim() || YASAL_VARSAYILAN.eposta,
    sonGuncelleme: YASAL_VARSAYILAN.sonGuncelleme,
  };

  const kaydet = async () => {
    const temiz = Object.fromEntries(ALANLAR.map((a) => [a, taslak[a].trim()])) as Record<Alan, string>;
    for (const a of ['eposta', 'kep'] as const) {
      if (temiz[a] && !EPOSTA.test(temiz[a])) {
        toast.error(t('yasalAyar.epostaHatasi'));
        return;
      }
    }
    if (temiz.sonGuncelleme && !TARIH.test(temiz.sonGuncelleme)) {
      toast.error(t('yasalAyar.tarihHatasi'));
      return;
    }
    setKaydediliyor(true);
    try {
      for (const a of ALANLAR) {
        const anahtar = YASAL_ANAHTARLAR[a];
        const mevcut = settingRows.find((r) => r.setting_key === anahtar);
        if ((mevcut?.setting_value ?? '') === temiz[a]) continue;
        if (!mevcut && !temiz[a]) continue;
        await saveSiteSetting(settingRows, anahtar, temiz[a], 'yasal', t(`yasalAyar.alan.${a}`));
      }
      toast.success(t('yasalAyar.kaydedildi'));
      await onSaved();
    } catch (e) {
      toast.error((e as { message?: string })?.message || t('yasalAyar.hata'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const dil = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : 'tr';

  return (
    <div className="cam-kart rounded-2xl glass p-6" data-testid="yasal-ayar">
      <h3 className="mb-1 flex items-center gap-2 text-lg font-semibold">
        <Scale className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {t('yasalAyar.baslik')}
      </h3>
      <p className="mb-5 text-xs text-muted-foreground">{t('yasalAyar.aciklama')}</p>
      <div className="space-y-4">
        {ALANLAR.map((a) => {
          const kimlik = `yasal-${a}`;
          const ortak = {
            id: kimlik,
            name: YASAL_ANAHTARLAR[a],
            value: taslak[a],
            placeholder: yerTutucu[a] ? t('yasalAyar.varsayilan', { deger: yerTutucu[a] }) : undefined,
            className: 'bg-white/5 border-white/10',
          };
          return (
            <div key={a}>
              <Label htmlFor={kimlik} className="mb-2 block text-xs uppercase tracking-widest text-muted-foreground">
                {t(`yasalAyar.alan.${a}`)}
              </Label>
              {a === 'adres' ? (
                <Textarea rows={2} {...ortak} onChange={(o) => setTaslak({ ...taslak, [a]: o.target.value })} />
              ) : (
                <Input
                  {...ortak}
                  type={a === 'sonGuncelleme' ? 'date' : a === 'eposta' || a === 'kep' ? 'email' : 'text'}
                  dir={a === 'unvan' ? undefined : 'ltr'}
                  onChange={(o) => setTaslak({ ...taslak, [a]: o.target.value })}
                />
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{t('yasalAyar.not')}</p>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button
          onClick={kaydet}
          disabled={kaydediliyor}
          data-testid="yasal-kaydet"
          className="h-10 gap-2 border-0 bg-gradient-to-r from-purple-600 to-pink-600 text-white"
        >
          {kaydediliyor ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {t('yasalAyar.kaydet')}
        </Button>
        <span className="text-xs text-muted-foreground">{t('yasalAyar.sayfalar')}:</span>
        {(YASAL_SAYFALAR as string[]).map((s) => (
          <a
            key={s}
            href={localizedPath(dil, s)}
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-1 text-xs text-primary underline underline-offset-2"
          >
            {t(`footer.${s}`)}
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        ))}
      </div>
    </div>
  );
}

function ilkDeger(satirlar: SettingRow[]): Record<Alan, string> {
  return Object.fromEntries(
    ALANLAR.map((a) => [a, satirlar.find((r) => r.setting_key === YASAL_ANAHTARLAR[a])?.setting_value ?? '']),
  ) as Record<Alan, string>;
}
