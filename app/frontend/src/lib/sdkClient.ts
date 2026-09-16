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
    instance = createClient();
  }
  return instance;
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
