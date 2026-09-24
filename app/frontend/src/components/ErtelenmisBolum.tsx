import { useEffect, useRef, useState, type ReactNode } from 'react';
import type React from 'react';

/**
 * Ekranın altındaki bölümleri ilk çizimde atlar.
 *
 * Ana sayfa on üç bölümden oluşuyor ve tarayıcı bunların tamamını daha
 * ilk karede kuruyordu. Ölçümde ana iş parçacığındaki uzun görevlerin
 * yarısı (yaklaşık 400 ms, işlemci dört kat yavaşlatılmış) ziyaretçinin
 * henüz görmediği bölümlerden geliyordu — PageSpeed'in TBT kalemi tam
 * olarak bu.
 *
 * Burada her bölüm, görünür alana 800 piksel yaklaşana kadar yalnızca
 * doğru yükseklikte boş bir kutu. Kaydırma başlayınca sırası gelen
 * bölüm çiziliyor; kullanıcı farkı görmüyor çünkü bölüm ekrana
 * girmeden önce hazır oluyor.
 *
 * Prerender (sunucu) tarafında `canli` doğrudan açık: Google'ın gördüğü
 * HTML eksiksiz kalıyor, bölümler statik dosyada aynen duruyor.
 *
 * Çapa bağlantıları (#kesif, #sss) için `hashchange` dinleniyor: adres
 * çubuğunda ya da menüde bir çapaya gidilirse bütün bölümler anında
 * çiziliyor ve hedefe kaydırılıyor.
 */

const SUNUCUDA = typeof window === 'undefined';

/** Çapa istendiğinde tüm bölümleri açmak için ortak anahtar. */
const dinleyiciler = new Set<() => void>();
let hepsiAcik = false;

function hepsiniAc() {
  if (hepsiAcik) return;
  hepsiAcik = true;
  dinleyiciler.forEach((f) => {
    try {
      f();
    } catch {
      /* bir dinleyicinin hatası diğerlerini düşürmesin */
    }
  });
}

/**
 * Çapaya kaydır.
 *
 * Bölümler bu karede çiziliyor ama `content-visibility` yüzünden
 * yükseklikler bir-iki kare sonra oturuyor; bu yüzden kaydırma birkaç
 * kez deneniyor — ilki hemen, sonrakiler yerleşim oturdukça.
 */
function capayaKaydir(hedef: string) {
  if (!hedef) return;
  const git = (yumusak: boolean) =>
    document
      .getElementById(hedef)
      ?.scrollIntoView(yumusak ? { behavior: 'smooth' } : undefined);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      git(false);
      setTimeout(() => git(false), 300);
      setTimeout(() => git(true), 900);
    });
  });
}

if (!SUNUCUDA) {
  window.addEventListener('hashchange', () => {
    hepsiniAc();
    capayaKaydir(decodeURIComponent(window.location.hash.slice(1)));
  });

  /*
   * Sayfada arama (Ctrl/Cmd+F) ve yazdırma, henüz çizilmemiş bölümleri
   * de kapsamalı. Tarayıcının arama çubuğu açılmadan önce tuş basımı
   * sayfaya ulaşıyor; o anda hepsini çiziyoruz.
   */
  window.addEventListener(
    'keydown',
    (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) hepsiniAc();
    },
    { capture: true },
  );
  window.addEventListener('beforeprint', hepsiniAc);
}

/**
 * Çok uzun bir görünür alan = kaydırmayan bir istemci (arama motoru
 * tarayıcısı, ekran görüntüsü aracı). Böyle bir istemciye sayfanın
 * tamamını ilk karede veriyoruz; erteleme yalnızca gerçek ziyaretçinin
 * hız kazancı için var, içeriği kimseden saklamak için değil.
 */
function kaydirmayanIstemci(): boolean {
  return window.innerHeight > 2000;
}

interface Props {
  children: ReactNode;
  /** Bölüm çizilene kadar tutulacak yükseklik — mobil ve masaüstü ayrı. */
  yukseklikMobil: number;
  yukseklikMasa: number;
}

export default function ErtelenmisBolum({ children, yukseklikMobil, yukseklikMasa }: Props) {
  const [canli, setCanli] = useState(() => SUNUCUDA || hepsiAcik);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (canli) return;

    // Sayfa doğrudan bir çapayla açıldıysa beklemeye gerek yok.
    if (window.location.hash) {
      hepsiniAc();
      setCanli(true);
      capayaKaydir(decodeURIComponent(window.location.hash.slice(1)));
      return;
    }

    // IntersectionObserver yoksa (çok eski tarayıcı) hiçbir şeyi
    // gizlemeyelim: yavaş olması, eksik olmasından iyidir.
    if (typeof IntersectionObserver === 'undefined' || kaydirmayanIstemci()) {
      hepsiniAc();
      setCanli(true);
      return;
    }

    const ac = () => setCanli(true);
    dinleyiciler.add(ac);

    const el = ref.current;
    let gozcu: IntersectionObserver | undefined;
    if (el) {
      gozcu = new IntersectionObserver(
        (girdiler) => {
          if (girdiler.some((g) => g.isIntersecting)) setCanli(true);
        },
        { rootMargin: '800px 0px' },
      );
      gozcu.observe(el);
    } else {
      setCanli(true);
    }

    return () => {
      dinleyiciler.delete(ac);
      gozcu?.disconnect();
    };
  }, [canli]);

  if (canli) return <>{children}</>;

  /*
   * Yükseklik iki kırılım için ayrı veriliyor: masaüstünde bölümler
   * mobile göre çok daha kısa, tek bir değer kullanılınca sayfa önce
   * gereğinden uzun açılıp kaydırma çubuğu geri kaçıyordu.
   */
  return (
    <div
      ref={ref}
      className="bolum-yer"
      style={
        {
          '--yer-mobil': `${yukseklikMobil}px`,
          '--yer-masa': `${yukseklikMasa}px`,
        } as React.CSSProperties
      }
      aria-hidden="true"
    />
  );
}
