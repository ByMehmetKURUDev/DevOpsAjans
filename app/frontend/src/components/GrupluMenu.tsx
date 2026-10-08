import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, X, type LucideIcon } from 'lucide-react';
import { DIGER, grubunuBul, grupla, sekmeAra, type GrupTanimi } from '@/lib/grupluMenu';

/**
 * Gruplu panel menüsü (Faz 7Y yönetici menüsünden genelleştirildi, Faz 7M).
 *
 * Üstte gruplar, altta seçili grubun bölümleri. Arama kutusu (kısayol: "/")
 * bütün bölümlerde arar; Enter ilk sonucu açar.
 *
 * Bütün bölüm düğmeleri DOM'da duruyor (seçili grubun dışındakiler `hidden`):
 * `?sekme=` bağlantıları ve rozetler hangi grup açık olursa olsun çalışıyor.
 *
 * Paneli tanımlayan üç şey dışarıdan gelir: grup tanımı (`tanim`), grup
 * ikonları ve etiket paketi (`paket`: `<paket>.grup.<g>`, `<paket>.menu`,
 * `.bolumler`, `.ara`, `.temizle`, `.sonucYok`). `kimlik` kök öğenin veri
 * özniteliğini verir (`yonetim` → `data-yonetim-menusu`).
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

function Rozet({ sayi }: { sayi: number }) {
  return (
    <span
      className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-pink-600 px-1.5 text-[11px] font-semibold leading-5 text-white"
      data-rozet={sayi}
    >
      {sayi > 99 ? '99+' : sayi}
    </span>
  );
}

/** `useGrupluMenu` girdisi: menünün verisi (düzen bağımsız). */
export type GrupluMenuGirdisi<K extends string, G extends string> = Pick<
  GrupluMenuOzellikleri<K, G>,
  'sekmeler' | 'aktif' | 'onSec' | 'rozetler' | 'grubaKatilmayan' | 'tanim' | 'paket'
>;

/**
 * Gruplu menünün durumu ve davranışı (Faz 11A: düzenden ayrıldı). Aynı mantığı iki düzen
 * kullanıyor: bu dosyadaki üst çubuk (müşteri paneli) ve yönetici panelinin sol kenar
 * çubuğu (`components/admin/YonetimKabugu.tsx`). Grup başına son bölüm hafızası, arama
 * ("/" kısayolu, Enter ilk sonuç, Esc temizler) ve grup rozet toplamı burada.
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

export default function GrupluMenu<K extends string, G extends string>({
  sekmeler,
  aktif,
  onSec,
  rozetler = {},
  grubaKatilmayan = [],
  tanim,
  ikonlar,
  paket,
  kimlik,
  cubukOznitelikleri,
}: GrupluMenuOzellikleri<K, G>) {
  const { t, gruplar, grupAdi, bulunanGrup, aranan, setAranan, arama, sonuclar, sonucAnahtarlari, aramaRef, sec, grubaGit, aramaTusu, grubunRozeti } =
    useGrupluMenu<K, G>({ sekmeler, aktif, onSec, rozetler, grubaKatilmayan, tanim, paket });
  const aktifGrup = bulunanGrup ?? gruplar[0]?.anahtar;

  const kokOzniteligi = { [`data-${kimlik}-menusu`]: true };

  return (
    <nav aria-label={t(`${paket}.menu`)} className="mb-8" {...kokOzniteligi}>
      <div className="cam-sekmeler flex gap-1 overflow-x-auto border-b border-white/10" data-grup-cubugu>
        {gruplar.map((g) => {
          const Ikon: LucideIcon = ikonlar[g.anahtar];
          const secili = !arama && g.anahtar === aktifGrup;
          const rozet = grubunRozeti(g.anahtar);
          return (
            <button
              key={g.anahtar}
              type="button"
              data-grup={g.anahtar}
              data-grup-sekmeler={g.sekmeler.map((s) => s.key).join(' ')}
              aria-current={secili ? 'true' : undefined}
              onClick={() => grubaGit(g.anahtar)}
              className={`relative inline-flex shrink-0 items-center gap-2 whitespace-nowrap px-4 py-3 text-sm font-medium transition-colors ${
                secili ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Ikon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {grupAdi(g.anahtar)}
              {rozet > 0 && <Rozet sayi={rozet} />}
              {secili && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />
              )}
            </button>
          );
        })}
      </div>

      <div className="flex flex-col gap-3 pt-4 lg:flex-row lg:items-start">
        <div
          className="cam-alt-sekmeler order-2 flex flex-1 flex-wrap gap-2 lg:order-1"
          aria-label={t(`${paket}.bolumler`)}
          data-sekme-cubugu
          {...cubukOznitelikleri}
        >
          {gruplar.flatMap((g) =>
            g.sekmeler.map((s) => {
              const gorunur = arama ? sonucAnahtarlari.has(s.key) : g.anahtar === aktifGrup;
              const secili = s.key === aktif;
              const rozet = rozetler[s.key] || 0;
              return (
                <button
                  key={s.key}
                  type="button"
                  hidden={!gorunur}
                  data-sekme={s.key}
                  data-secili={secili ? 'evet' : 'hayir'}
                  aria-current={secili ? 'page' : undefined}
                  onClick={() => sec(s.key)}
                  // `hidden` özniteliği tek başına yetmiyor (sınıftaki display onu ezer).
                  className={`${gorunur ? 'inline-flex' : 'hidden'} items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1.5 text-sm transition-colors ${
                    secili
                      ? 'border-pink-400/40 bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-foreground'
                      : 'border-white/10 text-muted-foreground hover:bg-white/5 hover:text-foreground'
                  }`}
                >
                  <s.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {s.label}
                  {arama && <span className="text-xs text-muted-foreground">· {grupAdi(g.anahtar)}</span>}
                  {rozet > 0 && <Rozet sayi={rozet} />}
                </button>
              );
            }),
          )}
          {arama && sonuclar.length === 0 && (
            <p className="py-1.5 text-sm text-muted-foreground" data-arama-bos>
              {t(`${paket}.sonucYok`)}
            </p>
          )}
        </div>
        <div className="relative order-1 w-full shrink-0 lg:order-2 lg:w-56">
          <Search
            className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            ref={aramaRef}
            type="search"
            value={aranan}
            onChange={(e) => setAranan(e.target.value)}
            onKeyDown={aramaTusu}
            placeholder={t(`${paket}.ara`)}
            aria-label={t(`${paket}.ara`)}
            data-menu-arama
            className="h-9 w-full rounded-full border border-white/10 bg-white/5 pe-9 ps-9 text-sm [&::-webkit-search-cancel-button]:hidden placeholder:text-muted-foreground focus:border-pink-400/50 focus:outline-none focus:ring-2 focus:ring-pink-500/20"
          />
          {aranan && (
            <button
              type="button"
              onClick={() => {
                setAranan('');
                aramaRef.current?.focus();
              }}
              aria-label={t(`${paket}.temizle`)}
              className="absolute end-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground hover:bg-white/10 hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}
