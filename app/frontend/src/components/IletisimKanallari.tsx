import { CalendarClock, Mail, MessageCircle, MessageSquareText, Phone } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { kesifOzetiniOku } from '@/lib/kesifOzetiSaklama';
import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Doğrudan iletişim kanalları — asistan panelinin içinde.
 *
 * Eskiden ekranın sağ altında iki ayrı balon vardı: AI asistan ve onun
 * altında WhatsApp. İkisi üst üste durunca hem mobilde yer kaplıyordu hem
 * de ziyaretçiye "hangisi?" diye bir karar yüklüyordu. Artık tek tuş var;
 * WhatsApp da dahil bütün kanallar panelin içinde.
 *
 * Kanalların hepsi cihazın kendi uygulamasını açıyor (wa.me, tel:, sms:,
 * mailto:) — araya bir form ya da kayıt koymuyoruz. Numara ve adres
 * yönetim panelindeki ayarlardan geliyor, koda gömülü değil.
 *
 * Toplantı bağlantısı ayarlarda boşsa o tuş HİÇ görünmüyor. Çalışmayan
 * bir "Toplantı ayarla" tuşu, hiç olmamasından kötü.
 */

/** Yalnızca rakamlar; + ve boşluklar wa.me'de kabul edilmiyor. */
function rakamlar(deger: string): string {
  return (deger || '').replace(/\D/g, '');
}

/**
 * tel: ve sms: için uluslararası biçim.
 *
 * Panelde telefon "0541 296 58 78" gibi yerel biçimde yazılı olabiliyor;
 * bu biçim yurt dışındaki bir ziyaretçinin telefonunda çalışmaz. WhatsApp
 * numarası zaten ülke koduyla duruyor, o yüzden yerel biçim görülürse
 * ona düşülüyor.
 */
function aramaNumarasi(telefon: string, whatsapp: string): string {
  const ham = (telefon || '').trim();
  if (ham.startsWith('+')) return `+${rakamlar(ham)}`;
  const wa = rakamlar(whatsapp);
  if (wa) return `+${wa}`;
  const yerel = rakamlar(ham);
  return yerel ? `+${yerel}` : '';
}

export default function IletisimKanallari() {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();

  const waNumara = rakamlar(settings.whatsapp_number || '905412965878');
  const numara = aramaNumarasi(settings.contact_phone || '', settings.whatsapp_number || '');
  const eposta = (settings.contact_email || '').trim();
  const toplanti = (settings.meeting_link || '').trim();

  // Keşif Sihirbazı doldurulduysa özet mesaja ekleniyor; ziyaretçi
  // anlattıklarını baştan yazmak zorunda kalmasın.
  const ozet = kesifOzetiniOku();
  const giris = t('contact.whatsappIntro');
  const metin = ozet ? `${giris}\n\n${ozet}` : giris;

  /*
   * sms: gövdesinin ayırıcısı platforma göre değişiyor — iOS `&body=`
   * beklerken diğerleri RFC'deki `?body=` ile çalışıyor. Yanlış ayırıcı
   * mesaj kutusunu boş açmakla kalmıyor, bazı sürümlerde bağlantıyı
   * tamamen bozuyor.
   */
  const smsAyirici =
    typeof navigator !== 'undefined' && /iP(hone|ad|od)/.test(navigator.userAgent) ? '&' : '?';

  const kanallar = [
    {
      anahtar: 'whatsapp',
      etiket: t('asistan.kanalWhatsapp'),
      ikon: MessageCircle,
      href: waNumara ? `https://wa.me/${waNumara}?text=${encodeURIComponent(metin)}` : '',
      disBaglanti: true,
    },
    {
      anahtar: 'telefon',
      etiket: t('asistan.kanalTelefon'),
      ikon: Phone,
      href: numara ? `tel:${numara}` : '',
      disBaglanti: false,
    },
    {
      anahtar: 'sms',
      etiket: t('asistan.kanalSms'),
      ikon: MessageSquareText,
      href: numara ? `sms:${numara}${smsAyirici}body=${encodeURIComponent(metin)}` : '',
      disBaglanti: false,
    },
    {
      anahtar: 'eposta',
      etiket: t('asistan.kanalEposta'),
      ikon: Mail,
      href: eposta
        ? `mailto:${eposta}?subject=${encodeURIComponent(
            t('asistan.epostaKonu'),
          )}&body=${encodeURIComponent(metin)}`
        : '',
      disBaglanti: false,
    },
    {
      anahtar: 'toplanti',
      etiket: t('asistan.kanalToplanti'),
      ikon: CalendarClock,
      href: toplanti,
      disBaglanti: true,
    },
  ].filter((k) => k.href);

  if (kanallar.length === 0) return null;

  return (
    <div className="border-b border-white/10 px-4 py-3">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {t('asistan.kanallarBaslik')}
      </p>
      <div className="flex flex-wrap gap-2">
        {kanallar.map(({ anahtar, etiket, ikon: Ikon, href, disBaglanti }) => (
          <a
            key={anahtar}
            href={href}
            {...(disBaglanti ? { target: '_blank', rel: 'noreferrer' } : {})}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
            {etiket}
          </a>
        ))}
      </div>
    </div>
  );
}
