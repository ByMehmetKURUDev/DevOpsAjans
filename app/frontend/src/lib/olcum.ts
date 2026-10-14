/**
 * Parti 13 — reklam ölçümü: hangi sayfalar ölçülür, dönüşüm olayları.
 *
 * Özel yollar (yönetim/müşteri panelleri, jetonlu bağlantılar, müşterilerin
 * beyaz etiketli sayfaları) HİÇ ölçülmez: hem ajansın istatistiğini kendi
 * oturumlarıyla bozmasın, hem de adresteki jeton Google/Meta'ya gitmesin.
 * Aynı desen `index.html`'deki GA yükleyicisinde de var (satır içi betik
 * modül içe aktaramıyor); ikisinin aynı kaldığını `olcum.test.ts` denetliyor.
 *
 * Dönüşümler GA4 olayı (`generate_lead`, `contact`) ve Meta Pixel olayı
 * (`Lead`, `Contact`) olarak gidiyor. Google Ads dönüşümü ayrı etiket
 * gerektirmiyor: GA4'teki "temel etkinlik" Ads'e içe aktarılıyor.
 * Rıza yoksa GA/Pixel betiği hiç inmediği için olaylar da hiçbir yere gitmez.
 */

export const OZEL_YOL_DESENI =
  /^\/(admin|client|auth|personel|ode|rapor|rapor-aylik|islem|icerik-onay|paylas|hesap-davet|teklif|sozlesme|servis|toplanti-yanit|durum|form|kart|yorum|randevu|menu|q)(\/|$)/;

/** Dil önekli yollar da (`/en/admin`) özel sayılır. */
export function ozelYolMu(yol: string): boolean {
  const temiz = yol.replace(/^\/(tr|en|de|ru|zh|hi|ar)(?=\/|$)/, '') || '/';
  return OZEL_YOL_DESENI.test(temiz);
}

export type DonusumTuru = 'lead' | 'contact';

export function donusum(tur: DonusumTuru, ayrinti: { kaynak?: string; yontem?: string } = {}): void {
  if (typeof window === 'undefined' || ozelYolMu(window.location.pathname)) return;
  try {
    if (tur === 'lead') {
      window.gtag?.('event', 'generate_lead', {
        lead_source: ayrinti.kaynak || 'form',
      });
      window.fbq?.('track', 'Lead', ayrinti.kaynak ? { content_name: ayrinti.kaynak } : undefined);
    } else {
      window.gtag?.('event', 'contact', { method: ayrinti.yontem || 'diger' });
      window.fbq?.('track', 'Contact', ayrinti.yontem ? { content_name: ayrinti.yontem } : undefined);
    }
  } catch {
    /* ölçüm hatası sayfayı bozmasın */
  }
}

/** Tıklanan bağlantı bir iletişim kanalıysa yöntemi (telefon / e-posta / whatsapp). */
export function iletisimYontemi(href: string | null | undefined): string | null {
  const h = (href || '').trim().toLowerCase();
  if (h.startsWith('tel:')) return 'telefon';
  if (h.startsWith('mailto:')) return 'eposta';
  if (h.startsWith('whatsapp:') || /^https?:\/\/(wa\.me|api\.whatsapp\.com|web\.whatsapp\.com)\//.test(h)) return 'whatsapp';
  return null;
}
