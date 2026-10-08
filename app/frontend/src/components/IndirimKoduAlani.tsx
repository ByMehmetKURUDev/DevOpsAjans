import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2, TicketPercent } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { koduDogrula, type DogrulamaSonucu } from '@/lib/indirimKodu';
import { referansOku } from '@/lib/referans';

/**
 * Faz 5K — sitedeki formların (iletişim, "Teklif al") isteğe bağlı "indirim / referans kodu" alanı.
 *
 * Ortak bağlantısıyla (`?ref=`) gelindiyse alan o kodla dolar (rıza varsa cihazda saklanan, yoksa bu
 * oturumdaki kod). Kod alan bırakıldığında BİR KEZ denetlenir (tuş başına değil: kod tahmin sınırı IP
 * başına 10 dakikada 10); geçersiz kod formu engellemez — sunucu bilinmeyen kodu sessizce yok sayar.
 * Metinler `indirimKodu` ek paketinde: bileşen `ekliLazy('indirimKodu', …)` ile yüklenir.
 *
 * `satinAl`: doğrudan satın alma (Lemon Squeezy / Shopier ödeme sayfası) — indirim sağlayıcıya AKTARILMAZ
 * (sağlayıcıda kupon nesnesi açmak hesap işlemi). Alan yalnız referans kodu olarak kalır (atıf için); geçerli bir
 * indirim kodu yazılırsa "indirim teklif üzerinden uygulanır, Teklif Al'ı kullanın" uyarısı çıkar.
 */
export default function IndirimKoduAlani({
  deger,
  onDegis,
  id = 'indirim-kodu',
  sinif,
  satinAl = false,
  paket,
}: {
  deger: string;
  onDegis: (v: string) => void;
  id?: string;
  sinif?: string;
  satinAl?: boolean;
  /** "Teklif al" seçiminin paketi (paketle sınırlı kodlar için). */
  paket?: string;
}) {
  const { t } = useTranslation();
  const [sonuc, setSonuc] = useState<DogrulamaSonucu | null>(null);
  const [denetleniyor, setDenetleniyor] = useState(false);
  const sonDenetlenen = useRef('');

  // Bağlantıdan gelen kod: yalnız alan boşsa ve bir kez (ziyaretçinin yazdığını ezmesin).
  useEffect(() => {
    if (!deger) {
      const kod = referansOku();
      if (kod) onDegis(kod);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const denetle = async () => {
    const kod = deger.trim();
    if (!kod || kod === sonDenetlenen.current) return;
    sonDenetlenen.current = kod;
    setDenetleniyor(true);
    try {
      setSonuc(await koduDogrula(kod, paket));
    } finally {
      setDenetleniyor(false);
    }
  };

  useEffect(() => {
    if (!deger.trim()) {
      setSonuc(null);
      sonDenetlenen.current = '';
    }
  }, [deger]);

  const indirimMetni = () => {
    const i = sonuc?.indirim;
    if (!i) return '';
    return i.tur === 'yuzde' ? `%${i.deger}` : `${i.deger} ${i.para_birimi ?? ''}`.trim();
  };

  return (
    <div className="space-y-1.5" data-indirim-kodu-alani>
      <label htmlFor={id} className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <TicketPercent className="h-3.5 w-3.5" aria-hidden="true" />
        {t(satinAl ? 'indirimKodu.alan.referansEtiket' : 'indirimKodu.alan.etiket')} <span className="text-xs">({t('indirimKodu.alan.istege')})</span>
      </label>
      <input
        id={id}
        name="referans_kodu"
        value={deger}
        maxLength={32}
        autoComplete="off"
        spellCheck={false}
        placeholder={t('indirimKodu.alan.yerTutucu')}
        onChange={(e) => onDegis(e.target.value.replace(/\s+/g, ''))}
        onBlur={() => void denetle()}
        className={
          sinif ??
          'w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm uppercase tracking-wide text-white placeholder:normal-case placeholder:tracking-normal placeholder:text-muted-foreground focus:border-primary focus:outline-none'
        }
        aria-describedby={`${id}-durum`}
        data-testid="indirim-kodu-girdi"
      />
      <p id={`${id}-durum`} className="min-h-[1rem] text-xs" aria-live="polite" data-testid="indirim-kodu-durum">
        {denetleniyor ? (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            {t('indirimKodu.alan.denetleniyor')}
          </span>
        ) : sonuc?.gecerli && satinAl && sonuc.tur === 'indirim' ? (
          <span className="text-amber-200" data-durum="satin-al-indirim">{t('indirimKodu.alan.satinAlIndirim')}</span>
        ) : sonuc?.gecerli ? (
          <span className="inline-flex items-center gap-1 text-emerald-300" data-durum="gecerli">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            {sonuc.tur === 'indirim'
              ? t('indirimKodu.alan.indirim', { deger: indirimMetni() })
              : t('indirimKodu.alan.referans')}
          </span>
        ) : sonuc?.sinir ? (
          <span className="text-amber-200">{t('indirimKodu.alan.cokHizli')}</span>
        ) : sonuc ? (
          <span className="text-muted-foreground" data-durum="gecersiz">{t('indirimKodu.alan.gecersiz')}</span>
        ) : satinAl ? (
          <span className="text-muted-foreground" data-durum="satin-al-not">{t('indirimKodu.alan.satinAlNotu')}</span>
        ) : null}
      </p>
    </div>
  );
}
