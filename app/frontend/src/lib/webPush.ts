import { client } from '@/lib/sdkClient';

/**
 * Tarayıcı bildirimleri (Web Push).
 *
 * İzin YALNIZ kullanıcı düğmeye bastığında isteniyor: sayfa açılır açılmaz
 * izin penceresi çıkarmak hem rahatsız edici hem de tarayıcıların bu
 * isteği sessizce engellemesine yol açıyor.
 *
 * iOS/iPadOS Safari'de Web Push yalnız site "Ana ekrana ekle" ile
 * uygulama gibi açıldığında (16.4+) çalışıyor; normal sekmede
 * `PushManager` hiç yok. Arayüz bu durumda açıklama gösteriyor.
 */

export type PushDestegi = 'var' | 'yok' | 'ios-ana-ekran';

export function iosMu(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  // iPadOS 13+ kendini masaüstü Safari gibi tanıtıyor; dokunmatik ile ayırt ediliyor.
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && (navigator.maxTouchPoints ?? 0) > 1);
}

function anaEkrandanMi(): boolean {
  try {
    return (
      window.matchMedia?.('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true
    );
  } catch {
    return false;
  }
}

export function pushDestegi(): PushDestegi {
  if (typeof window === 'undefined') return 'yok';
  const temel = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (temel) return 'var';
  if (iosMu() && !anaEkrandanMi()) return 'ios-ana-ekran';
  return 'yok';
}

export function izinDurumu(): NotificationPermission | 'desteklenmiyor' {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'desteklenmiyor';
  return Notification.permission;
}

/** base64url → Uint8Array (applicationServerKey). */
function anahtarBaytlari(base64url: string): Uint8Array {
  const dolgu = '='.repeat((4 - (base64url.length % 4)) % 4);
  const b64 = (base64url + dolgu).replace(/-/g, '+').replace(/_/g, '/');
  const ham = atob(b64);
  const baytlar = new Uint8Array(ham.length);
  for (let i = 0; i < ham.length; i++) baytlar[i] = ham.charCodeAt(i);
  return baytlar;
}

async function kayitGetir(): Promise<ServiceWorkerRegistration> {
  const mevcut = await navigator.serviceWorker.getRegistration();
  if (!mevcut) await navigator.serviceWorker.register('/sw.js');
  // `ready` servis çalışanı etkinleşince çözülüyor; sonsuza dek beklemesin.
  return Promise.race([
    navigator.serviceWorker.ready,
    new Promise<never>((_, reddet) => setTimeout(() => reddet(new Error('sw-zaman-asimi')), 10000)),
  ]);
}

/** Bu tarayıcının mevcut aboneliği (yoksa null). */
export async function mevcutAbonelik(): Promise<PushSubscription | null> {
  if (pushDestegi() !== 'var') return null;
  try {
    const kayit = await navigator.serviceWorker.getRegistration();
    return (await kayit?.pushManager.getSubscription()) ?? null;
  } catch {
    return null;
  }
}

export async function sunucuAnahtari(): Promise<string | null> {
  try {
    const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/bildirim/push/anahtar' });
    const govde = (yanit as { data?: { acik?: boolean; anahtar?: string } })?.data;
    return govde?.acik && govde.anahtar ? govde.anahtar : null;
  } catch {
    return null;
  }
}

export class PushHatasi extends Error {
  constructor(public kod: 'destek-yok' | 'izin-yok' | 'anahtar-yok' | 'sunucu') {
    super(kod);
  }
}

/**
 * İzin ister, abone olur, aboneliği sunucuya kaydeder.
 * Yalnız bir tıklama işleyicisinden çağrılmalı.
 */
export async function bildirimleriAc(anahtar?: string | null): Promise<PushSubscription> {
  if (pushDestegi() !== 'var') throw new PushHatasi('destek-yok');
  const acikAnahtar = anahtar ?? (await sunucuAnahtari());
  if (!acikAnahtar) throw new PushHatasi('anahtar-yok');

  const izin = await Notification.requestPermission();
  if (izin !== 'granted') throw new PushHatasi('izin-yok');

  const kayit = await kayitGetir();
  let abonelik = await kayit.pushManager.getSubscription();
  if (!abonelik) {
    abonelik = await kayit.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: anahtarBaytlari(acikAnahtar) as BufferSource,
    });
  }
  try {
    await client.apiCall.invoke({
      method: 'POST',
      url: '/api/v1/bildirim/push/abone',
      data: abonelik.toJSON(),
    });
  } catch {
    throw new PushHatasi('sunucu');
  }
  return abonelik;
}

/** Bu tarayıcıyı hem sunucudan hem tarayıcıdan çıkarır. */
export async function bildirimleriKapat(): Promise<void> {
  const abonelik = await mevcutAbonelik();
  if (!abonelik) return;
  try {
    await client.apiCall.invoke({
      method: 'DELETE',
      url: '/api/v1/bildirim/push/abone',
      // SDK DELETE'te `data`yı sorguya çeviriyor; gövde için axios seçeneği.
      options: { data: { endpoint: abonelik.endpoint } },
    });
  } catch {
    // Sunucuda zaten yoksa da tarayıcı tarafı kapatılsın.
  }
  await abonelik.unsubscribe().catch(() => undefined);
}

export async function denemeBildirimi(): Promise<{ durum: string; ayrinti: string }> {
  const yanit = await client.apiCall.invoke({ method: 'POST', url: '/api/v1/bildirim/push/dene' });
  return ((yanit as { data?: { durum: string; ayrinti: string } })?.data ?? { durum: 'failed', ayrinti: '' });
}
