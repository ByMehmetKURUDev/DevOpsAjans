import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CameraOff, Loader2 } from 'lucide-react';

import { Pencere } from '@/components/stokPos/ortak';

/**
 * Faz 6P — kamerayla barkod okutma (Faz 6E kapı okutucusu deseni).
 *
 * Tarayıcıda `BarcodeDetector` varsa arka kamera açılır (EAN-13/8, UPC, Code128/39); yoksa (iOS Safari,
 * masaüstü Firefox) kamera yok — elle giriş ya da USB/Bluetooth okuyucu (klavye gibi yazar; kasa ekranındaki
 * arama alanı odakta). Ek kütüphane yok. Aynı kod 1,5 sn içinde ikinci kez okunmaz.
 */

interface BarkodAlgilayici {
  detect(kaynak: HTMLVideoElement): Promise<{ rawValue: string }[]>;
}
type BarkodSinifi = { new (s: { formats: string[] }): BarkodAlgilayici; getSupportedFormats?: () => Promise<string[]> };

const ISTENEN = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39'];

export function barkodSinifi(): BarkodSinifi | null {
  try {
    const w = window as unknown as { BarcodeDetector?: BarkodSinifi };
    return typeof w.BarcodeDetector === 'function' && !!navigator.mediaDevices?.getUserMedia ? w.BarcodeDetector : null;
  } catch {
    return null;
  }
}

export default function Okutucu({ onKod, onKapat }: { onKod: (kod: string) => void; onKapat: () => void }) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement | null>(null);
  const akis = useRef<MediaStream | null>(null);
  const son = useRef<{ kod: string; an: number }>({ kod: '', an: 0 });
  const [durum, setDurum] = useState<'aciliyor' | 'acik' | 'yok' | 'izin_yok'>(() => (barkodSinifi() ? 'aciliyor' : 'yok'));
  const [elle, setElle] = useState('');

  const kapat = useCallback(() => {
    akis.current?.getTracks().forEach((x) => x.stop());
    akis.current = null;
  }, []);

  useEffect(() => {
    const S = barkodSinifi();
    if (!S) return;
    let iptal = false;
    (async () => {
      try {
        let bicimler = ISTENEN;
        if (typeof S.getSupportedFormats === 'function') {
          const destek = await S.getSupportedFormats().catch(() => ISTENEN);
          bicimler = ISTENEN.filter((b) => destek.includes(b));
          if (!bicimler.length) {
            setDurum('yok');
            return;
          }
        }
        const a = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (iptal) {
          a.getTracks().forEach((x) => x.stop());
          return;
        }
        akis.current = a;
        if (video.current) {
          video.current.srcObject = a;
          await video.current.play().catch(() => undefined);
        }
        setDurum('acik');
        const algilayici = new S({ formats: bicimler });
        const dongu = async () => {
          if (!akis.current) return;
          try {
            if (video.current && video.current.readyState >= 2) {
              const bulunan = await algilayici.detect(video.current);
              const kod = bulunan[0]?.rawValue?.trim();
              const an = Date.now();
              if (kod && !(kod === son.current.kod && an - son.current.an < 1500)) {
                son.current = { kod, an };
                try {
                  navigator.vibrate?.(60);
                } catch {
                  /* titreşim yok */
                }
                onKod(kod);
              }
            }
          } catch {
            /* tek kare hatası */
          }
          if (akis.current) window.setTimeout(() => void dongu(), 200);
        };
        void dongu();
      } catch {
        if (!iptal) setDurum('izin_yok');
      }
    })();
    return () => {
      iptal = true;
      kapat();
    };
  }, [kapat, onKod]);

  return (
    <Pencere baslik={t('stokPos.okut.baslik')} onKapat={onKapat} testid="pos-okutucu">
      {durum === 'aciliyor' || durum === 'acik' ? (
        <div className="relative overflow-hidden rounded-xl bg-black">
          <video ref={video} className="aspect-[4/3] w-full object-cover" playsInline muted />
          <div className="pointer-events-none absolute inset-x-8 top-1/2 h-0.5 -translate-y-1/2 bg-red-500/80" aria-hidden="true" />
          {durum === 'aciliyor' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-white" aria-hidden="true" />
            </div>
          )}
        </div>
      ) : (
        <p className="flex items-start gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100" data-testid="pos-okutucu-yok">
          <CameraOff className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          {t(durum === 'izin_yok' ? 'stokPos.okut.izinYok' : 'stokPos.okut.desteklenmiyor')}
        </p>
      )}
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (elle.trim()) {
            onKod(elle.trim());
            setElle('');
          }
        }}
      >
        <input
          className="h-10 min-w-0 flex-1 rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white"
          value={elle}
          onChange={(e) => setElle(e.target.value)}
          placeholder={t('stokPos.okut.elle')}
          inputMode="text"
          autoComplete="off"
          data-testid="pos-okutucu-elle"
        />
        <button type="submit" className="h-10 rounded-md bg-purple-600 px-4 text-sm font-medium text-white hover:bg-purple-500">
          {t('stokPos.ekle')}
        </button>
      </form>
    </Pencere>
  );
}
