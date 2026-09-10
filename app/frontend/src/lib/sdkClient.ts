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
