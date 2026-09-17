import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Adresteki `#bolum` çapasına kaydırır.
 *
 * React Router hash'i kendiliğinden işlemiyor; menüden "/#nasil-calisir"
 * gibi bir bağlantıya basıldığında sayfa yerinde kalıyordu. Burası hash
 * değiştikçe hedefi bulup oraya kaydırıyor.
 *
 * İki ayrıntı: hedef bölüm `content-visibility: auto` ile geç
 * boyutlandığından tek denemede bulunamayabiliyor, bu yüzden birkaç kare
 * deneniyor. Üstte sabit başlık var, o yüzden biraz pay bırakılıyor.
 */
const UST_PAY = 88;
const DENEME = 12;

export default function HashKaydirma() {
  const { pathname, hash } = useLocation();

  useEffect(() => {
    if (!hash) return;
    const id = decodeURIComponent(hash.slice(1));
    if (!id) return;

    let kalan = DENEME;
    let istek = 0;

    const dene = () => {
      const hedef = document.getElementById(id);
      if (hedef) {
        const y = hedef.getBoundingClientRect().top + window.scrollY - UST_PAY;
        const azalt = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        window.scrollTo({ top: y, behavior: azalt ? 'auto' : 'smooth' });
        return;
      }
      if (--kalan > 0) istek = requestAnimationFrame(dene);
    };

    istek = requestAnimationFrame(dene);
    return () => cancelAnimationFrame(istek);
  }, [pathname, hash]);

  return null;
}
