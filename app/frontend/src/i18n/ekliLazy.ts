import { lazy, type ComponentType } from 'react';

import { ekYukle } from './index';

/**
 * `lazy()` gibi; bileşenin kodu ile ek çeviri paketini birlikte bekler.
 * Böylece sayfa/sekme ilk çizildiğinde anahtar adları görünmez.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function ekliLazy<T extends ComponentType<any>>(
  ad: string | string[],
  yukleyici: () => Promise<{ default: T }>
) {
  const adlar = Array.isArray(ad) ? ad : [ad];
  return lazy(() => Promise.all([yukleyici(), ...adlar.map((a) => ekYukle(a))]).then(([mod]) => mod));
}
