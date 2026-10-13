import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, MapPin, Trash2, X } from 'lucide-react';

import OsmHarita from '@/components/harita/OsmHarita';
import { Button } from '@/components/ui/button';
import type { Lokasyon } from '@/lib/sahaServisi';
import { GIRDI } from './ortak';

/**
 * Faz 11E — adresin haritadaki yerini işaretleme. Haritaya tıklamak (ya da "41.0, 29.0" biçiminde
 * koordinat yapıştırmak) noktayı koyar; Kaydet `PUT /lokasyonlar/{id}` ile enlem/boylam yazar, Kaldır siler.
 * Adres çözümleme (geocoding) servisi kullanılmıyor: adres dışarı gönderilmiyor.
 */
export default function KonumSecici({
  lokasyon,
  onKaydet,
  onKapat,
}: {
  lokasyon: Lokasyon;
  onKaydet: (enlem: number | null, boylam: number | null) => Promise<void>;
  onKapat: () => void;
}) {
  const { t } = useTranslation();
  const [nokta, setNokta] = useState<[number, number] | null>(
    lokasyon.enlem != null && lokasyon.boylam != null ? [lokasyon.enlem, lokasyon.boylam] : null
  );
  const [metin, setMetin] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const kapatRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    kapatRef.current?.focus();
    const tus = (e: KeyboardEvent) => e.key === 'Escape' && onKapat();
    document.addEventListener('keydown', tus);
    return () => document.removeEventListener('keydown', tus);
  }, [onKapat]);

  const yapistir = (v: string) => {
    setMetin(v);
    const m = v.trim().match(/^(-?\d{1,2}(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:[.,]\d+)?)$/);
    if (!m) return;
    const e = Number(m[1].replace(',', '.'));
    const b = Number(m[2].replace(',', '.'));
    if (Math.abs(e) <= 85 && Math.abs(b) <= 180) setNokta([e, b]);
  };

  const kaydet = async (n: [number, number] | null) => {
    setMesgul(true);
    try {
      await onKaydet(n ? n[0] : null, n ? n[1] : null);
      onKapat();
    } catch {
      /* hata iletisi üst bileşende gösterildi; pencere açık kalır */
    } finally {
      setMesgul(false);
    }
  };

  // Katman <body> altına: panel kabuğundaki dönüşümlü/kapsamlı ataların içinde `fixed` kaymasın.
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="konum-secici-b" data-testid="saha-konum-secici">
      <div className="flex max-h-full w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl border border-white/10 bg-[#0a0f1e] shadow-2xl sm:rounded-2xl">
        <div className="flex items-start gap-3 border-b border-white/10 px-4 py-3">
          <MapPin className="mt-0.5 h-5 w-5 flex-none text-cyan-300" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <h3 id="konum-secici-b" className="font-semibold">
              {t('sahaServisi.konumSecici.baslik')}
            </h3>
            <p className="truncate text-xs text-muted-foreground">
              {lokasyon.ad} — {lokasyon.tam_adres || '—'}
            </p>
          </div>
          <button ref={kapatRef} type="button" onClick={onKapat} className="rounded-md p-1.5 text-muted-foreground hover:bg-white/10 hover:text-white" aria-label={t('sahaServisi.kapat')}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <OsmHarita
          isaretler={nokta ? [{ id: 'nokta', enlem: nokta[0], boylam: nokta[1], renk: '#22d3ee', etiket: lokasyon.ad }] : []}
          onTikla={(e, b) => setNokta([e, b])}
          sigdirAnahtari="sabit"
          varsayilanYakinlik={11}
          enFazlaYakinlik={16}
          className="h-[52vh] min-h-[280px] rounded-none"
          etiket={t('sahaServisi.konumSecici.haritaEtiket')}
          testid="saha-konum-harita"
        />
        <div className="space-y-3 px-4 py-3">
          <p className="text-xs text-muted-foreground">{t('sahaServisi.konumSecici.ipucu')}</p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              className={`${GIRDI} max-w-xs font-mono`}
              value={metin}
              onChange={(e) => yapistir(e.target.value)}
              placeholder="41.0082, 28.9784"
              aria-label={t('sahaServisi.konumSecici.koordinat')}
              inputMode="decimal"
              data-testid="saha-konum-metin"
            />
            <span className="font-mono text-xs text-cyan-200" dir="ltr" data-testid="saha-konum-deger">
              {nokta ? `${nokta[0].toFixed(5)}, ${nokta[1].toFixed(5)}` : t('sahaServisi.konumSecici.secilmedi')}
            </span>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {lokasyon.enlem != null && (
              <Button variant="ghost" className="me-auto gap-1.5 text-red-300 hover:text-red-200" disabled={mesgul} onClick={() => void kaydet(null)} data-testid="saha-konum-kaldir">
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                {t('sahaServisi.konumSecici.kaldir')}
              </Button>
            )}
            <Button variant="outline" className="!bg-transparent border-white/20" onClick={onKapat}>
              {t('sahaServisi.vazgec')}
            </Button>
            <Button disabled={!nokta || mesgul} onClick={() => void kaydet(nokta)} className="gap-1.5" data-testid="saha-konum-kaydet">
              {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('sahaServisi.kaydet')}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
