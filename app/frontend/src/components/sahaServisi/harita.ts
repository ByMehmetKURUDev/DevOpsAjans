import type { HaritaCizgisi, HaritaIsareti } from '@/components/harita/OsmHarita';
import type { Durum, IsOzeti, KomutaTeknisyeni } from '@/lib/sahaServisi';

/** Faz 11E — sevk haritası ve Komuta ekranının ortak harita verisi. */

export const DURUM_HEX: Record<Durum, string> = {
  yeni: '#38bdf8',
  planlandi: '#a78bfa',
  yolda: '#fbbf24',
  iste: '#fb923c',
  tamamlandi: '#34d399',
  iptal: '#a1a1aa',
  ertelendi: '#fb7185',
};
export const ACIL_HEX = '#ef4444';

export const TEKNISYEN_DURUM_HEX: Record<KomutaTeknisyeni['durum'], string> = {
  iste: '#fb923c',
  yolda: '#fbbf24',
  bekliyor: '#a78bfa',
  bitti: '#34d399',
  bos: '#94a3b8',
};

const acik = (x: IsOzeti) => x.durum !== 'tamamlandi' && x.durum !== 'iptal';

/** İşaretler: renk durumdan (açık acil iş kırmızı ve nabızlı), içindeki rakam teknisyenin günlük sırası. */
export function isaretler(isler: IsOzeti[], etiketle: (x: IsOzeti) => string, teknisyen?: number | null): HaritaIsareti[] {
  const sira = new Map<number, number>();
  const gruplar = new Map<number, IsOzeti[]>();
  for (const x of isler) for (const t of x.teknisyenler) gruplar.set(t.id, [...(gruplar.get(t.id) || []), x]);
  for (const liste of gruplar.values()) {
    liste
      .slice()
      .sort((a, b) => (a.plan_bas || '').localeCompare(b.plan_bas || '') || a.id - b.id)
      .forEach((x, i) => {
        if (!sira.has(x.id)) sira.set(x.id, i + 1);
      });
  }
  return isler
    .filter((x) => x.nokta && (teknisyen == null || x.teknisyenler.some((t) => t.id === teknisyen)))
    .map((x) => {
      const acilMi = x.oncelik === 'acil' && acik(x);
      return {
        id: x.id,
        enlem: x.nokta!.enlem,
        boylam: x.nokta!.boylam,
        renk: acilMi ? ACIL_HEX : DURUM_HEX[x.durum],
        etiket: etiketle(x),
        ic: sira.has(x.id) ? String(sira.get(x.id)) : undefined,
        nabiz: acilMi || x.durum === 'iste',
        uyari: !!x.gecikti,
      };
    });
}

/** Teknisyen başına günün sırası (planlanan saate göre) — yol tarifi değil, ziyaret sırası. */
export function rotalar(isler: IsOzeti[], renkler: Map<number, string>, teknisyen?: number | null): HaritaCizgisi[] {
  const gruplar = new Map<number, IsOzeti[]>();
  for (const x of isler) {
    if (!x.nokta || x.durum === 'iptal') continue;
    for (const t of x.teknisyenler) gruplar.set(t.id, [...(gruplar.get(t.id) || []), x]);
  }
  const sonuc: HaritaCizgisi[] = [];
  for (const [tid, liste] of gruplar) {
    if (teknisyen != null && tid !== teknisyen) continue;
    const noktalar = liste
      .slice()
      .sort((a, b) => (a.plan_bas || '').localeCompare(b.plan_bas || '') || a.id - b.id)
      .map((x) => [x.nokta!.enlem, x.nokta!.boylam] as [number, number]);
    if (noktalar.length > 1) sonuc.push({ renk: renkler.get(tid) || '#22d3ee', noktalar });
  }
  return sonuc;
}
