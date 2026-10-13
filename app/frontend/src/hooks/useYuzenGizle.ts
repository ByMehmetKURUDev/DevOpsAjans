import { useEffect } from 'react';

/**
 * Faz 11F — telefonda panelin yüzen düğmeleri (AI asistan, Hata bildir, Yukarı çık) aşağı kaydırırken
 * çekilir, yukarı kaydırınca / sayfanın başında ve sonunda geri gelir: içerik ve satır düğmeleri
 * kaydırma boyunca örtülmesin. Yalnız `<html data-yuzen-gizli>` özniteliği; görünümü CSS yapıyor
 * (`panelBolumleri.css`). Telefon dışında (≥ 768 px) hiçbir şey yapmaz.
 */
const SORGU = '(max-width: 767px)';
const OZNITELIK = 'data-yuzen-gizli';

export function useYuzenGizle(): void {
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const kok = document.documentElement;
    const telefon = window.matchMedia(SORGU);
    let son = window.scrollY;
    let kare = 0;
    const goster = () => kok.removeAttribute(OZNITELIK);
    const kaydir = () => {
      if (kare) return;
      kare = window.requestAnimationFrame(() => {
        kare = 0;
        const y = window.scrollY;
        const dipte = window.innerHeight + y >= kok.scrollHeight - 96;
        if (!telefon.matches || y < 140 || dipte || y < son - 6) goster();
        else if (y > son + 6) kok.setAttribute(OZNITELIK, '');
        son = y;
      });
    };
    const degisti = () => {
      if (!telefon.matches) goster();
    };
    window.addEventListener('scroll', kaydir, { passive: true });
    telefon.addEventListener?.('change', degisti);
    return () => {
      window.removeEventListener('scroll', kaydir);
      telefon.removeEventListener?.('change', degisti);
      if (kare) window.cancelAnimationFrame(kare);
      goster();
    };
  }, []);
}
