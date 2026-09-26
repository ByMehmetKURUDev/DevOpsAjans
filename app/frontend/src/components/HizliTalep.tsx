import { useState, type FormEvent } from 'react';
import { CheckCircle2, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { client } from '@/lib/sdkClient';

/**
 * Sayfadan ayrılmadan talep bırakma penceresi.
 *
 * Neden var
 * ---------
 * Paket kartındaki "Satın al" ve keşif asistanındaki "Teklif iste"
 * düğmeleri iletişim sayfasına atıyordu. Müşteri seçtiği paketi ya da
 * az önce cevapladığı onca soruyu orada baştan anlatmak zorunda
 * kalıyordu — çoğu da anlatmıyor, sayfayı kapatıyordu.
 *
 * Bu pencere talebi bulunduğu yerden gönderiyor. Seçilen paket ya da
 * keşif özeti `konu` ve `onDolgu` ile birlikte geliyor, müşteri
 * yalnızca kendi bilgilerini yazıyor.
 *
 * `kaynak` alanı panelde hangi sayfanın iş getirdiğini gösteriyor
 * (`paket:...`, `kesif`), `brief` ise keşif özetini taşıyor.
 */

export interface HizliTalepProps {
  acik: boolean;
  kapat: () => void;
  /** Talebin konusu — paket adı ya da "Keşif özeti". */
  konu: string;
  /** Mesaj alanına önceden yazılan metin. */
  onDolgu?: string;
  /** Panelde kaynağı ayırt etmek için: "paket:Business", "kesif" … */
  kaynak: string;
  /** Keşif asistanının ürettiği uzun özet; panelde brief olarak duruyor. */
  brief?: string;
  /** Pencerenin üstünde gösterilen kısa açıklama. */
  aciklama?: string;
}

export default function HizliTalep({
  acik,
  kapat,
  konu,
  onDolgu,
  kaynak,
  brief,
  aciklama,
}: HizliTalepProps) {
  const { t } = useTranslation();
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [telefon, setTelefon] = useState('');
  const [mesaj, setMesaj] = useState(onDolgu ?? '');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [bitti, setBitti] = useState(false);

  if (!acik) return null;

  const gonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (!ad.trim() || !eposta.trim()) {
      toast.error(t('hizliTalep.eksik', 'Ad ve e-posta gerekli.'));
      return;
    }
    setGonderiliyor(true);
    try {
      await client.entities.inquiries.create({
        data: {
          name: ad.trim(),
          email: eposta.trim(),
          phone: telefon.trim(),
          subject: konu,
          // Mesaj boş bırakılsa bile konu tek başına anlamlı: hangi
          // paket ya da hangi keşif olduğunu zaten taşıyor.
          message: mesaj.trim() || konu,
          status: 'new',
          source: kaynak,
          ...(brief ? { brief } : {}),
        },
      });
      setBitti(true);
      toast.success(t('hizliTalep.alindi', 'Talebiniz alındı.'));
    } catch (hata) {
      const h = hata as { data?: { detail?: string }; message?: string };
      toast.error(h?.data?.detail || h?.message || t('hizliTalep.hata', 'Gönderilemedi.'));
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={(o) => {
        if (o.target === o.currentTarget) kapat();
      }}
    >
      <div className="relative w-full max-w-md rounded-2xl border border-white/12 bg-[#0b0f14] p-6 shadow-2xl">
        <button
          type="button"
          onClick={kapat}
          aria-label={t('genel.kapat', 'Kapat')}
          className="absolute right-4 top-4 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>

        {bitti ? (
          <div className="py-6 text-center">
            <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-400" aria-hidden="true" />
            <p className="text-lg font-semibold">{t('hizliTalep.tesekkur', 'Talebiniz bize ulaştı')}</p>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {t(
                'hizliTalep.donus',
                'En kısa sürede e-posta ile dönüyoruz. Aciliyeti varsa telefonla da arayabilirsiniz.',
              )}
            </p>
            <Button onClick={kapat} className="mt-5 w-full">
              {t('genel.kapat', 'Kapat')}
            </Button>
          </div>
        ) : (
          <form onSubmit={gonder} className="space-y-3">
            <div className="pr-8">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {t('hizliTalep.baslik', 'Talep bırakın')}
              </p>
              <p className="mt-1 text-lg font-semibold leading-snug">{konu}</p>
              {aciklama ? (
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{aciklama}</p>
              ) : null}
            </div>

            <input
              required
              value={ad}
              onChange={(o) => setAd(o.target.value)}
              placeholder={t('hizliTalep.ad', 'Adınız *')}
              autoComplete="name"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <input
              required
              type="email"
              value={eposta}
              onChange={(o) => setEposta(o.target.value)}
              placeholder={t('hizliTalep.eposta', 'E-posta *')}
              autoComplete="email"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <input
              value={telefon}
              onChange={(o) => setTelefon(o.target.value)}
              placeholder={t('hizliTalep.telefon', 'Telefon (isteğe bağlı)')}
              autoComplete="tel"
              inputMode="tel"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <textarea
              value={mesaj}
              onChange={(o) => setMesaj(o.target.value)}
              rows={4}
              placeholder={t('hizliTalep.mesaj', 'Eklemek istedikleriniz')}
              className="w-full resize-y rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />

            <Button type="submit" disabled={gonderiliyor} className="w-full gap-2">
              {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
              {t('hizliTalep.gonder', 'Gönder')}
            </Button>
            <p className="text-center text-[11px] leading-relaxed text-muted-foreground">
              {t('hizliTalep.gizlilik', 'Bilgileriniz yalnızca bu talep için kullanılır.')}
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
