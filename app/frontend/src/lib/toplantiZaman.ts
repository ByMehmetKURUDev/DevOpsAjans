/**
 * Faz 6T — toplantı zamanları: sunucu UTC saklar, panel Europe/Istanbul gösterir; tarayıcının saat dilimi farklıysa
 * ikisi birden. Bağımlılıksız (girişsiz yanıt sayfası da kullanıyor; ana pakete SDK çekmesin).
 */

export const SAAT_DILIMI = 'Europe/Istanbul';

/** Arapçada Latin rakamlar (tablo/saat hizası); diğer dillerde dilin kendi biçimi. */
export function yerelAd(dil: string): string {
  return dil === 'ar' ? 'ar-u-nu-latn' : dil;
}

export function tarayiciSaatDilimi(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || SAAT_DILIMI;
  } catch {
    return SAAT_DILIMI;
  }
}

function ofset(an: Date, tz: string): number {
  try {
    const p = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).formatToParts(an);
    const al = (t: string) => Number(p.find((x) => x.type === t)?.value || 0);
    const yerelZaman = Date.UTC(al('year'), al('month') - 1, al('day'), al('hour') % 24, al('minute'));
    return Math.round((yerelZaman - Math.floor(an.getTime() / 60000) * 60000) / 60000);
  } catch {
    return 180;
  }
}

/** Tarayıcı saat dilimi bu anda İstanbul'la aynı mı (ofset karşılaştırması)? */
export function istanbulMu(an: Date = new Date()): boolean {
  return ofset(an, tarayiciSaatDilimi()) === ofset(an, SAAT_DILIMI);
}

export function zamanYaz(iso: string | null | undefined, dil: string, tz: string = SAAT_DILIMI, kisa = false): string {
  if (!iso) return '—';
  const an = new Date(iso);
  if (Number.isNaN(an.getTime())) return '—';
  try {
    return new Intl.DateTimeFormat(yerelAd(dil), {
      timeZone: tz,
      ...(kisa ? { hour: '2-digit', minute: '2-digit' } : { dateStyle: 'medium', timeStyle: 'short' }),
    }).format(an);
  } catch {
    return an.toISOString().slice(0, 16).replace('T', ' ');
  }
}

/** "6 Eki 2030 10:00 (İstanbul)" + tarayıcı farklıysa " · 08:00 (yerel)". */
export function ciftZaman(iso: string | null | undefined, dil: string, etiketler: { istanbul: string; yerel: string }): string {
  if (!iso) return '—';
  const ana = `${zamanYaz(iso, dil)} (${etiketler.istanbul})`;
  if (istanbulMu(new Date(iso))) return ana;
  return `${ana} · ${zamanYaz(iso, dil, tarayiciSaatDilimi())} (${etiketler.yerel})`;
}

/** UTC ISO → datetime-local değeri (İstanbul saati), ör. "2030-05-06T10:00". */
export function istanbulGirdisi(iso: string | null | undefined): string {
  if (!iso) return '';
  const an = new Date(iso);
  if (Number.isNaN(an.getTime())) return '';
  const yerelMs = an.getTime() + ofset(an, SAAT_DILIMI) * 60000;
  return new Date(yerelMs).toISOString().slice(0, 16);
}

/** Tarayıcının yerel datetime-local değeri → UTC ISO (müşteri talebi). */
export function yereldenUtc(deger: string): string | null {
  if (!deger) return null;
  const an = new Date(deger);
  return Number.isNaN(an.getTime()) ? null : an.toISOString();
}

/** Liste için İstanbul ISO haftası (sunucu `hafta` döndürüyor; yedek). */
export function haftaBasi(iso: string): string {
  const yerel = istanbulGirdisi(iso).slice(0, 10);
  const g = new Date(`${yerel}T00:00:00Z`);
  const gun = (g.getUTCDay() + 6) % 7;
  g.setUTCDate(g.getUTCDate() - gun);
  return g.toISOString().slice(0, 10);
}

