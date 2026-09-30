import { createClient } from '@metagptx/web-sdk';

type SdkClient = ReturnType<typeof createClient>;

let instance: SdkClient | null = null;

/**
 * SDK istemcisini ilk kullanımda oluşturur.
 *
 * `createClient()` tarayıcıya bağımlı: `window` yoksa çağrıldığı anda
 * `ReferenceError` atıyor. Dokuz dosya bunu modül seviyesinde çağırdığı
 * için o modülleri import etmek Node'da tek başına build'i düşürüyordu —
 * prerender'ın ana sayfayı ve statik sayfaları hiç kapsayamamasının,
 * `dist/index.html` gövdesinin boş kalmasının sebebi buydu.
 *
 * İstemci artık yalnızca bir özelliğine ilk erişildiğinde kuruluyor;
 * bütün kullanım noktaları effect ve olay işleyicilerinin içinde olduğu
 * için sunucuda render sırasında hiç oluşturulmuyor.
 */
export function getSdkClient(): SdkClient {
  if (!instance) {
    instance = createClient({ onUnauthorized: yetkisizYanitGeldi });
  }
  return instance;
}

let girisYonlendirmesiBasladi = false;

/**
 * Faz 2D: jeton varken gelen 401 — jeton artık geçersiz (süresi dolmuş ya da
 * oturum sonlandırılmış: "Oturum sonlandırıldı"). İzi siliyoruz; yönetici /
 * müşteri panelindeysek girişe yönlendiriyoruz. Herkese açık sayfada yalnız
 * iz siliniyor (ziyaretçi okumaya devam etsin). Jetonsuz 401'e dokunulmuyor.
 */
function yetkisizYanitGeldi(): void {
  let jetonVardi = false;
  try {
    jetonVardi = !!localStorage.getItem('token');
  } catch {
    return;
  }
  if (!jetonVardi) return;
  oturumIziniTemizle();
  try {
    const yol = window.location.pathname.replace(/^\/(tr|en|de|ru|zh|hi|ar)(?=\/)/, '');
    if (!girisYonlendirmesiBasladi && /^\/(admin|client)(\/|$)/.test(yol)) {
      girisYonlendirmesiBasladi = true;
      getSdkClient().auth.toLogin();
    }
  } catch {
    /* tarayıcı dışı */
  }
}

/**
 * Faz 2D: çıkışta sunucudaki oturumu da kapatır (jeton kopyalanmış olsa
 * bile işe yaramasın). SDK'nın `logout()`u jetonu istekten ÖNCE sildiği için
 * sunucu hangi oturumun kapandığını bilemiyordu. En çok 2 sn beklenir;
 * hata/zaman aşımı çıkışı engellemez.
 */
export async function sunucuOturumunuKapat(): Promise<void> {
  let jeton: string | null = null;
  try {
    jeton = localStorage.getItem('token');
  } catch {
    return;
  }
  if (!jeton) return;
  const kontrol = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const zaman = window.setTimeout(() => kontrol?.abort(), 2000);
  try {
    await fetch('/api/v1/auth/logout', {
      headers: { Authorization: `Bearer ${jeton}` },
      signal: kontrol?.signal,
    });
  } catch {
    /* ağ hatası: çıkış yine yapılır */
  } finally {
    window.clearTimeout(zaman);
  }
}

/**
 * Çağrı noktalarının `client.foo(...)` yazımını koruyabilmesi için tembel
 * bir vekil. Erişilen ilk özellikte gerçek istemci kurulur.
 */
export const client = new Proxy({} as SdkClient, {
  get(_target, property, receiver) {
    const actual = getSdkClient() as unknown as Record<string | symbol, unknown>;
    const value = Reflect.get(actual, property, receiver);
    return typeof value === 'function' ? value.bind(actual) : value;
  },
  has(_target, property) {
    return property in (getSdkClient() as unknown as object);
  },
});

/**
 * Tarayicida bir oturum izi var mi?
 *
 * SDK oturum jetonunu `localStorage`'da `token` anahtarinda tutuyor;
 * arka uc cerez kullanmiyor, jeton giris donusunde adresten okunup oraya
 * yaziliyor. Iz yokken `auth.me()` cagirmak kesin 401 donuyor: bos bir ag
 * istegi ve tarayici konsolunda bir hata satiri. Herkese acik sayfalarda
 * ziyaretcilerin cogu giris yapmamis oluyor, yani bu her yuklemede
 * tekrarlaniyordu.
 *
 * Iz bulunmadiginda cagri hic yapilmiyor; sonuc ayni -- eskiden de 401
 * yakalanip kullanici bos birakiliyordu.
 *
 * Gizli sekmede ya da depolama kapaliyken erisim hata atabildigi icin
 * her iki okuma da korumali.
 */
export function oturumIziVarMi(): boolean {
  try {
    if (localStorage.getItem('token')) return true;
  } catch {
    /* depolamaya erisilemiyor */
  }
  try {
    // SDK, platform devri icin bir cerezi de okuyabiliyor.
    return document.cookie.includes('atoms_token=');
  } catch {
    return false;
  }
}

/**
 * Gecersiz oturum izini siler.
 *
 * Suresi dolmus bir token localStorage'da kalinca her sayfa acilisinda
 * `me()` cagriliyor, 401 donuyor ve o sure boyunca header bos kaliyordu.
 * 401 gordugumuz anda izi siliyoruz ki bir dahaki acilista beklenmesin.
 */
export function oturumIziniTemizle(): void {
  try {
    localStorage.removeItem('token');
  } catch {
    /* ozel sekme / depolama kapali: yapacak bir sey yok */
  }
}

/** Hata 401 mi? Gecici ag hatasinda token silmemek icin ayirt ediyoruz. */
export function yetkisizHataMi(hata: unknown): boolean {
  const h = hata as { status?: number; response?: { status?: number }; message?: string };
  if (h?.status === 401 || h?.response?.status === 401) return true;
  return /\b401\b|unauthorized/i.test(String(h?.message ?? ''));
}
