/**
 * Modül vitrini (Faz 4V) — herkese açık `/moduller` sayfalarının verisi.
 *
 * Yapı: modül kaydından türetilmiş, depodaki kopya (`prerender/modul-vitrini-veri.json`).
 * Sayfa paketine giriyor (~1 kB gzip); ağ beklemeden çiziliyor, prerender ile aynı.
 *
 * Fiyat (ölçek başına başlangıç aylık tutarı, fiyatlandırma v5) sırasıyla:
 *  1. Sayfaya gömülü veri (`<script id="modul-vitrini-verisi">`): prerender hangi
 *     fiyatla çizdiyse o (derlemede uç okunamadıysa boş).
 *  2. Bellek önbelleği (aynı oturumda sayfalar arası).
 *  3. `GET /api/v1/modul-vitrini` — açılışta arka planda tazeleniyor.
 *
 * Teklif talebi: `POST /api/v1/modul-vitrini/talep` (girişsiz; `inquiries` + CRM adayı).
 */
import { getAPIBaseURL } from '@/lib/config';
import { referansOku } from '@/lib/referans';

import VERI from '../../prerender/modul-vitrini-veri.json';
import { govdeyiTuket } from '@/lib/yanit';

export interface VitrinModulu {
  anahtar: string;
  slug: string;
  ikon: string;
  kategori: string;
  durum: string;
  /** Dahil olduğu en düşük ölçek (ALFA…); null → ayrı açılan modül. */
  paket: string | null;
  ilgili: string[];
  sektor_paketleri: string[];
}

export interface VitrinPaketi {
  anahtar: string;
  slug: string;
  ikon: string;
  moduller: string[];
  /** Faz 6R: hazır kurulum seçenekleri (`core/sektor_ayarlari.py`; ilki varsayılan). */
  setler?: string[];
}

export interface VitrinYapisi {
  surum: number;
  olcekler: string[];
  kategoriler: string[];
  moduller: VitrinModulu[];
  yakinda: { anahtar: string; ikon: string; kategori: string }[];
  temeller: { anahtar: string; ikon: string }[];
  paketler: VitrinPaketi[];
}

export interface OlcekFiyati {
  baslangic_aylik: number;
  para_birimi: string;
  ad: Record<string, string>;
}

export type VitrinFiyatlari = Record<string, OlcekFiyati>;

export const VITRIN: VitrinYapisi = VERI as VitrinYapisi;

// ---------------------------------------------------------------------------
// Fiyat
// ---------------------------------------------------------------------------
const GOMULU_KIMLIK = 'modul-vitrini-verisi';
let gomulu: { fiyatlar?: VitrinFiyatlari } | null | undefined;
let bellek: VitrinFiyatlari | null = null;

/** Prerender: her sayfa çiziminden önce (vitrin dışı sayfalarda null). */
export function gomuluFiyatlariAyarla(fiyatlar: VitrinFiyatlari | null): void {
  gomulu = fiyatlar ? { fiyatlar } : null;
}

function gomuluVeri(): { fiyatlar?: VitrinFiyatlari } | null {
  if (gomulu !== undefined) return gomulu;
  gomulu = null;
  if (typeof document === 'undefined') return gomulu;
  const el = document.getElementById(GOMULU_KIMLIK);
  if (el?.textContent) {
    try {
      gomulu = JSON.parse(el.textContent) as { fiyatlar?: VitrinFiyatlari };
    } catch {
      gomulu = null;
    }
  }
  return gomulu;
}

/** Bu oturumda uçtan fiyat alındı mı (vitrin sayfaları arası gezinmede yeniden istenmesin)? */
export function fiyatlarTazeMi(): boolean {
  return bellek !== null;
}

/** İlk çizim için eldeki fiyatlar (önbellek ya da gömülü); yoksa boş sözlük. */
export function eldekiFiyatlar(): VitrinFiyatlari {
  if (bellek) return bellek;
  return gomuluVeri()?.fiyatlar ?? {};
}

export async function fiyatlariGetir(signal?: AbortSignal): Promise<VitrinFiyatlari> {
  const yanit = await fetch(`${getAPIBaseURL()}/api/v1/modul-vitrini`, { headers: { accept: 'application/json' }, signal });
  if (!yanit.ok) {
    await govdeyiTuket(yanit);
    throw new Error(`HTTP ${yanit.status}`);
  }
  const veri = (await yanit.json()) as { fiyatlar?: VitrinFiyatlari };
  const fiyatlar = veri?.fiyatlar && typeof veri.fiyatlar === 'object' ? veri.fiyatlar : {};
  if (typeof window !== 'undefined') bellek = fiyatlar;
  return fiyatlar;
}

// ---------------------------------------------------------------------------
// Teklif talebi
// ---------------------------------------------------------------------------
export interface TalepGovdesi {
  tur: 'modul' | 'paket';
  anahtar: string;
  ad: string;
  eposta: string;
  telefon?: string;
  isletme_turu?: string;
  not?: string;
  dil: string;
  pazarlama_izni?: boolean;
  /** Bal küpü — insan doldurmuyor. */
  web_sitesi?: string;
}

export class TalepHatasi extends Error {
  kod: string;
  constructor(kod: string) {
    super(kod);
    this.kod = kod;
  }
}

export async function talepGonder(govde: TalepGovdesi): Promise<void> {
  let yanit: Response;
  // Faz 5K: ortaklık bağlantısından gelen kod gizli alan olarak (rıza yoksa yalnız bu oturumdaki).
  const referans_kodu = referansOku();
  try {
    yanit = await fetch(`${getAPIBaseURL()}/api/v1/modul-vitrini/talep`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(referans_kodu ? { ...govde, referans_kodu } : govde),
    });
  } catch {
    throw new TalepHatasi('ag');
  }
  if (yanit.ok) {
    await govdeyiTuket(yanit);
    return;
  }
  let kod = 'genel';
  try {
    const veri = (await yanit.json()) as { detail?: { kod?: string } };
    if (typeof veri?.detail?.kod === 'string') kod = veri.detail.kod;
  } catch {
    /* gövde yok */
  }
  throw new TalepHatasi(kod);
}
