import { useState } from 'react';
import { Check, Copy, MailCheck, ShieldAlert, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

/**
 * Yeni üretilen girişsiz bağlantıyı (teklif / sözleşme) BİR KEZ gösterir.
 * Sunucu jetonun yalnız özetini tutuyor; kutu kapanınca bağlantı bir daha
 * gösterilemez (yeniden gönder → yeni bağlantı, eskisi iptal).
 * Metinler çağıranın ek paketinden geliyor.
 */
export default function TekSeferlikBaglanti({
  baglanti,
  baslik,
  altSatir,
  uyari,
  epostaMetni,
  kopyalaMetni,
  kapatMetni,
  onKapat,
}: {
  baglanti: string;
  baslik: string;
  altSatir?: string;
  uyari: string;
  epostaMetni?: string | null;
  kopyalaMetni: string;
  kapatMetni: string;
  onKapat: () => void;
}) {
  const [kopyalandi, setKopyalandi] = useState(false);
  const kopyala = async () => {
    try {
      await navigator.clipboard.writeText(baglanti);
      setKopyalandi(true);
      window.setTimeout(() => setKopyalandi(false), 2000);
    } catch {
      (document.getElementById('tek-seferlik-baglanti') as HTMLInputElement | null)?.select();
    }
  };
  return (
    <div className="cam-kart rounded-2xl border border-emerald-400/30 bg-emerald-500/[0.06] p-5" role="status"
      data-testid="baglanti-kutusu">
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold">{baslik}</p>
        <button type="button" onClick={onKapat} className="rounded-md p-1 text-muted-foreground hover:text-foreground"
          aria-label={kapatMetni}>
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      {altSatir && <p className="mt-1 break-words text-sm text-muted-foreground">{altSatir}</p>}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          id="tek-seferlik-baglanti"
          readOnly
          value={baglanti}
          onFocus={(e) => e.currentTarget.select()}
          className="h-10 min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-3 font-mono text-xs"
          data-testid="tek-seferlik-baglanti"
        />
        <Button type="button" onClick={() => void kopyala()} className="gap-2">
          {kopyalandi ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
          {kopyalaMetni}
        </Button>
      </div>
      <p className="mt-3 flex items-start gap-2 text-xs text-amber-200">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {uyari}
      </p>
      {epostaMetni && (
        <p className="mt-1 flex items-center gap-2 text-xs text-emerald-200">
          <MailCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
          {epostaMetni}
        </p>
      )}
    </div>
  );
}
