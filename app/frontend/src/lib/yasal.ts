/**
 * Yasal sayfaların (Faz 3Y) veri sorumlusu bilgileri — tarayıcı tarafı.
 *
 * Değerler yönetici panelindeki "Yasal bilgiler" ayarlarından geliyor
 * (`yasal_*`, herkese açık site ayarları). Çözümleme kuralı ve varsayılanlar
 * `prerender/yasal-veri.js`'te; burada yalnız kaynak seçimi var:
 *
 *   * Prerender: canlı API'den okunan ayarlar `yasalVeriyiAyarla` ile verilir
 *     ve aynı veri sayfaya `<script id="yasal-verisi">` olarak gömülür.
 *   * Tarayıcı: site ayarları gelene kadar gömülü veri (prerender'daki HTML ile
 *     aynı metin, ilk çizimde zıplama yok), geldikten sonra canlı ayarlar.
 *
 * Bu dosya yalnız yasal sayfa paketine giriyor (ana pakete değil).
 */
import { useMemo } from 'react';

import { useSiteSettings, type SettingsMap } from '@/lib/siteSettings';
import { yasalBilgileriCoz } from '../../prerender/yasal-veri.js';

export type YasalBilgiler = ReturnType<typeof yasalBilgileriCoz>;

let prerenderVerisi: SettingsMap | null = null;
let sayfaVerisi: SettingsMap | null | undefined;

/** Prerender betiği her yasal sayfadan önce çağırır (diğer sayfalarda null). */
export function yasalVeriyiAyarla(veri: SettingsMap | null): void {
  prerenderVerisi = veri;
}

function gomuluVeri(): SettingsMap | null {
  if (prerenderVerisi) return prerenderVerisi;
  if (typeof document === 'undefined') return null;
  if (sayfaVerisi !== undefined) return sayfaVerisi;
  try {
    const el = document.getElementById('yasal-verisi');
    sayfaVerisi = el?.textContent ? (JSON.parse(el.textContent) as SettingsMap) : null;
  } catch {
    sayfaVerisi = null;
  }
  return sayfaVerisi;
}

/** Sayfada gösterilecek unvan, e-posta, adres… (boş isteğe bağlı alanlar ''). */
export function useYasalBilgiler(): YasalBilgiler {
  const { rawSettings, loading } = useSiteSettings();
  const gomulu = gomuluVeri();
  return useMemo(
    () => yasalBilgileriCoz(loading && gomulu ? { ...rawSettings, ...gomulu } : rawSettings),
    [rawSettings, loading, gomulu],
  );
}
