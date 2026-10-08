import { Suspense, useState, type FormEvent } from 'react';
import { CheckCircle2, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import AydinlatmaSatiri from '@/components/AydinlatmaSatiri';
import { Button } from '@/components/ui/button';
import { fiyatlandirmaApi, type FiyatTeklifIstegi } from '@/api/fiyatlandirma';
import { ekliLazy } from '@/i18n/ekliLazy';
import { secimPaketi } from '@/lib/indirimKodu';

// Faz 5K: isteğe bağlı "indirim / referans kodu" — metni ek pakette, alan pencere açılınca yüklenir.
const IndirimKoduAlani = ekliLazy('indirimKodu', () => import('@/components/IndirimKoduAlani'));

/**
 * "Teklif Al" onay penceresi — Fiyatlandırma v5.
 *
 * `HizliTalep`'ten farkı: burada bir CRM mesajı değil, gerçek bir fatura +
 * `pricing_inquiries` kaydı oluşuyor (bkz. `POST /api/v1/fiyat-teklif`).
 * O yüzden ayrı bileşen — aynı formu `inquiries.create`'e değil bu uca
 * gönderiyor ve 409 (aynı teklif az önce gönderildi) durumunu ayrıca
 * karşılıyor.
 *
 * Çift gönderim koruması: sunucu tarafında zaten 60 saniyelik pencere var
 * (aynı e-posta + aynı seçim); burada ayrıca `gonderiliyor` ile buton geçici
 * olarak kilitleniyor ki çift tıklama iki isteğe yol açmasın.
 */

export interface FiyatTeklifModalProps {
  acik: boolean;
  kapat: () => void;
  /** Modalin üstünde gösterilen başlık — "ALFA / Kurumsal / Aylık" gibi. */
  konu: string;
  /** Gösterilen fiyat metni — "$540/ay" gibi, yalnızca bilgi amaçlı. */
  fiyatMetni: string;
  /** `/fiyat-teklif`'e gidecek seçim: (scale+profile+period+addon_ids) ya da ai_pm_tier_kod. */
  secim: Omit<FiyatTeklifIstegi, 'musteri_eposta' | 'musteri_adi'>;
  /**
   * "teklif" (varsayılan): fatura + teklif kaydı açılır, e-posta gider.
   * "satinAl": aynı kayıt açılır, ardından ödeme sayfasına (`/ode/<jeton>`) gidilir.
   */
  mod?: 'teklif' | 'satinAl';
}

export default function FiyatTeklifModal({ acik, kapat, konu, fiyatMetni, secim, mod = 'teklif' }: FiyatTeklifModalProps) {
  const satinAl = mod === 'satinAl';
  const { t } = useTranslation();
  const [ad, setAd] = useState('');
  const [eposta, setEposta] = useState('');
  const [referansKodu, setReferansKodu] = useState('');
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [bitti, setBitti] = useState(false);

  if (!acik) return null;

  const gonder = async (olay: FormEvent) => {
    olay.preventDefault();
    if (gonderiliyor || bitti) return;
    if (!ad.trim() || !eposta.trim()) {
      toast.error(t('fiyatTeklif.eksik', 'Ad ve e-posta gerekli.'));
      return;
    }
    setGonderiliyor(true);
    try {
      if (satinAl) {
        const sonuc = await fiyatlandirmaApi.satinAl({
          ...secim,
          musteri_eposta: eposta.trim(),
          musteri_adi: ad.trim(),
          ...(referansKodu.trim() ? { referans_kodu: referansKodu.trim() } : {}),
        });
        // Ödeme sayfası aynı sitede; tam sayfa geçişi ödeme sağlayıcısına
        // yönlendirmeyi de temiz tutuyor.
        window.location.assign(sonuc.adres);
        return;
      }
      await fiyatlandirmaApi.teklifGonder({
        ...secim,
        musteri_eposta: eposta.trim(),
        musteri_adi: ad.trim(),
        ...(referansKodu.trim() ? { referans_kodu: referansKodu.trim() } : {}),
      });
      setBitti(true);
      toast.success(t('fiyatTeklif.alindi', 'Teklifiniz oluşturuldu, fatura e-postanıza gönderilecek.'));
    } catch (hata) {
      const h = hata as { status?: number; message?: string };
      if (h?.status === 429) {
        // Faz 7H: IP başına istek sınırı (kalıcı sayaç) — kibar "biraz sonra deneyin".
        toast.error(t('genel.cokHizli'));
      } else if (h?.status === 409) {
        // Sunucu 60sn'lik cift-gonderim korumasina takildi -- kullaniciya
        // hata gibi degil, "zaten aldik" gibi gosteriliyor.
        setBitti(true);
        toast.info(t('fiyatTeklif.zatenGonderildi', 'Bu teklif az önce zaten gönderildi.'));
      } else {
        toast.error(h?.message || t('fiyatTeklif.hata', 'Teklif gönderilemedi.'));
      }
    } finally {
      setGonderiliyor(false);
    }
  };

  const kapatVeSifirla = () => {
    kapat();
    // Pencere tekrar acildiginda onceki "bitti" durumunda takili kalmasin.
    setTimeout(() => {
      setBitti(false);
      setAd('');
      setEposta('');
      setReferansKodu('');
    }, 200);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onClick={(o) => {
        if (o.target === o.currentTarget) kapatVeSifirla();
      }}
    >
      <div className="relative w-full max-w-md rounded-2xl border border-white/12 bg-[#0b0f14] p-6 shadow-2xl">
        <button
          type="button"
          onClick={kapatVeSifirla}
          aria-label={t('genel.kapat', 'Kapat')}
          className="absolute right-4 top-4 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>

        {bitti ? (
          <div className="py-6 text-center">
            <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-emerald-400" aria-hidden="true" />
            <p className="text-lg font-semibold">{t('fiyatTeklif.tesekkur', 'Teklifiniz alındı')}</p>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {t(
                'fiyatTeklif.donus',
                'Fatura ve detaylar e-postanıza gönderiliyor. En kısa sürede sizinle iletişime geçeceğiz.',
              )}
            </p>
            <Button onClick={kapatVeSifirla} className="mt-5 w-full">
              {t('genel.kapat', 'Kapat')}
            </Button>
          </div>
        ) : (
          <form onSubmit={gonder} className="space-y-3">
            <div className="pr-8">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {satinAl ? t('fiyatTeklif.satinAlBaslik', 'Satın al') : t('fiyatTeklif.baslik', 'Teklifi onayla')}
              </p>
              <p className="mt-1 text-lg font-semibold leading-snug">{konu}</p>
              <p className="mt-1 text-2xl font-bold gradient-text">{fiyatMetni}</p>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {satinAl
                  ? t(
                      'fiyatTeklif.satinAlAciklama',
                      'Bilgilerinizi girin; faturanız oluşsun ve güvenli ödeme sayfasına geçin.',
                    )
                  : t(
                      'fiyatTeklif.aciklama',
                      'Bilgilerinizi girin, size özel fatura ve teklif kaydı otomatik oluşsun.',
                    )}
              </p>
            </div>

            <input
              required
              value={ad}
              onChange={(o) => setAd(o.target.value)}
              placeholder={t('fiyatTeklif.ad', 'Adınız / Firma *')}
              autoComplete="name"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <input
              required
              type="email"
              value={eposta}
              onChange={(o) => setEposta(o.target.value)}
              placeholder={t('fiyatTeklif.eposta', 'E-posta *')}
              autoComplete="email"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            <Suspense fallback={null}>
              {/* Satın Al: indirim ödeme sağlayıcısına aktarılmaz — alan yalnız referans (atıf), kodlu alım Teklif Al'dan. */}
              <IndirimKoduAlani deger={referansKodu} onDegis={setReferansKodu} id="fiyat-referans-kodu" satinAl={satinAl}
                paket={secimPaketi(secim)} />
            </Suspense>

            <Button type="submit" disabled={gonderiliyor} className="w-full gap-2">
              {gonderiliyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
              {satinAl ? t('fiyatTeklif.odemeyeGec', 'Ödemeye geç') : t('fiyatTeklif.gonder', 'Teklifi Onayla ve Al')}
            </Button>
            <AydinlatmaSatiri metin={t('fiyatTeklif.gizlilik', 'Bilgileriniz yalnızca bu teklif için kullanılır.')} />
          </form>
        )}
      </div>
    </div>
  );
}
