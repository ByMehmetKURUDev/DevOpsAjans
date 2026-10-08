import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { LucideIcon } from 'lucide-react';
import { DIGER, grubunuBul, grupla, sekmeAra, type GrupTanimi } from '@/lib/grupluMenu';

/**
 * Gruplu panel menüsünün ortak mantığı (Faz 7Y yönetici menüsünden genelleştirildi, Faz 7M).
 *
 * Gruplar ve seçili grubun bölümleri; arama (kısayol: "/") bütün bölümlerde arar, Enter ilk sonucu açar.
 * Düzeni kullanan bileşen çizer: yönetici paneli sol kenar çubuğu (Faz 11A, `admin/YonetimKabugu.tsx` +
 * `YonetimMenusu.tsx`), müşteri paneli üst çubuğu (Faz 11B, `MusteriKabugu.tsx`). Faz 11B'de eski üst çubuk
 * bileşeni (bu dosyanın varsayılan dışa aktarımı) iki panelde de kullanılmadığı için kaldırıldı.
 *
 * Bütün bölüm düğmeleri DOM'da durur (seçili grubun dışındakiler `hidden`): `?sekme=` bağlantıları ve rozetler
 * hangi grup açık olursa olsun çalışır. Etiket paketi (`paket`): `<paket>.grup.<g>`, `<paket>.menu`, `.bolumler`,
 * `.ara`, `.temizle`, `.sonucYok`.
 */

export interface MenuOgesi<K extends string> {
  key: K;
  label: string;
  icon: LucideIcon;
}

export interface GrupluMenuOzellikleri<K extends string, G extends string> {
  sekmeler: MenuOgesi<K>[];
  aktif: K;
  onSec: (sekme: K) => void;
  /** Sekme başına sayı rozeti (ör. okunmamış sohbet); grubun rozeti toplamdır. */
  rozetler?: Partial<Record<K, number>>;
  /**
   * Rozeti yalnız kendi düğmesinde görünen, grubun toplamına KATILMAYAN sekmeler (Faz 5G):
   * sohbetler gelen kutusunun sayısında zaten var — Destek grubunda iki kez sayılmasın.
   */
  grubaKatilmayan?: readonly K[];
  tanim: readonly GrupTanimi<G>[];
  ikonlar: Record<G | typeof DIGER, LucideIcon>;
  paket: string;
  kimlik: string;
  /** Bölüm çubuğuna (`data-sekme-cubugu`) eklenecek veri öznitelikleri. */
  cubukOznitelikleri?: Record<`data-${string}`, string>;
}

/** `useGrupluMenu` girdisi: menünün verisi (düzen bağımsız). */
export type GrupluMenuGirdisi<K extends string, G extends string> = Pick<
  GrupluMenuOzellikleri<K, G>,
  'sekmeler' | 'aktif' | 'onSec' | 'rozetler' | 'grubaKatilmayan' | 'tanim' | 'paket'
>;

/**
 * Gruplu menünün durumu ve davranışı (Faz 11A: düzenden ayrıldı). Aynı mantığı iki düzen
 * kullanıyor: müşteri panelinin üst çubuğu (`components/MusteriKabugu.tsx`, Faz 11B) ve yönetici
 * panelinin sol kenar çubuğu (`components/admin/YonetimKabugu.tsx`). Grup başına son bölüm hafızası,
 * arama ("/" kısayolu, Enter ilk sonuç, Esc temizler) ve grup rozet toplamı burada.
 */
export function useGrupluMenu<K extends string, G extends string>({
  sekmeler,
  aktif,
  onSec,
  rozetler = {},
  grubaKatilmayan = [],
  tanim,
  paket,
}: GrupluMenuGirdisi<K, G>) {
  const { t } = useTranslation();
  const [aranan, setAranan] = useState('');
  const aramaRef = useRef<HTMLInputElement>(null);
  // Grup başına son açılan bölüm: gruba dönünce kaldığı yerden açılsın.
  const sonBolum = useRef<Partial<Record<G | typeof DIGER, K>>>({});

  const gruplar = useMemo(() => grupla(sekmeler, tanim), [sekmeler, tanim]);
  const grupAdi = (g: G | typeof DIGER) => t(`${paket}.grup.${g}`);
  /** Etkin bölümün grubu; bölüm hiçbir grupta değilse (ör. yönetici "Genel bakış") null. */
  const bulunanGrup = grubunuBul(gruplar, aktif);
  useEffect(() => {
    if (bulunanGrup) sonBolum.current[bulunanGrup] = aktif;
  }, [aktif, bulunanGrup]);

  const arama = aranan.trim();
  const sonuclar = useMemo(
    () => (arama ? sekmeAra(gruplar, arama, grupAdi) : []),
    // grupAdi her çizimde yeni; dil değişince `gruplar` da yenileniyor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gruplar, arama],
  );
  const sonucAnahtarlari = useMemo(() => new Set<string>(sonuclar.map((s) => s.key)), [sonuclar]);

  // "/" ile arama kutusuna odaklan (yazı alanındayken değil).
  useEffect(() => {
    const dinle = (e: globalThis.KeyboardEvent) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
      const hedef = e.target as HTMLElement | null;
      if (hedef && (hedef.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(hedef.tagName))) return;
      e.preventDefault();
      aramaRef.current?.focus();
    };
    window.addEventListener('keydown', dinle);
    return () => window.removeEventListener('keydown', dinle);
  }, []);

  const sec = (k: K) => {
    setAranan('');
    onSec(k);
  };

  /** Grubun en son açılan (yoksa ilk) bölümüne geçer. */
  const grubaGit = (g: G | typeof DIGER) => {
    const grup = gruplar.find((x) => x.anahtar === g);
    if (grup) sec(sonBolum.current[g] ?? grup.sekmeler[0].key);
  };

  const aramaTusu = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && sonuclar[0]) {
      e.preventDefault();
      sec(sonuclar[0].key);
      aramaRef.current?.blur();
    } else if (e.key === 'Escape') {
      setAranan('');
    }
  };

  const grubunRozeti = (anahtar: G | typeof DIGER) =>
    gruplar.find((g) => g.anahtar === anahtar)?.sekmeler.reduce((top, s) => top + (grubaKatilmayan.includes(s.key) ? 0 : rozetler[s.key] || 0), 0) || 0;

  return {
    t,
    gruplar,
    grupAdi,
    bulunanGrup,
    aranan,
    setAranan,
    arama,
    sonuclar,
    sonucAnahtarlari,
    aramaRef,
    sec,
    grubaGit,
    aramaTusu,
    grubunRozeti,
    rozetler,
  };
}

export type GrupluMenuDurumu<K extends string, G extends string> = ReturnType<typeof useGrupluMenu<K, G>>;
