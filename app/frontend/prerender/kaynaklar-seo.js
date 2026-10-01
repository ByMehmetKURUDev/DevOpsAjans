/**
 * Kaynaklar sayfalarının SEO metinleri (7 dil).
 *
 * Neden `site.js` içindeki PAGE_SEO'da değil?
 * -------------------------------------------
 * `site.js` Layout üzerinden ana sayfanın ilk JS paketine giriyor. Bu
 * metinlerin yedi dili oraya konunca ana paket ~0,8 kB (gzip) büyüyordu —
 * hiçbir ana sayfa ziyaretçisinin ihtiyaç duymadığı metin. Burada durunca
 * yalnız prerender (Node) ve tembel yüklenen Kaynaklar sayfası okuyor.
 *
 * `site.js` yine tek kaynak olmaya devam ediyor: `kaynaklar` orada PAGE_KEYS,
 * PAGE_PATHS ve PAGE_SEO_KEYS içinde (yollar, hreflang, site haritası ve
 * panelden SEO metni değiştirme). Yalnız varsayılan başlık/açıklama burada.
 *
 * Bağımlılığı olmayan düz JS: prerender, vite.config ve istemci okuyabiliyor.
 */
export const KAYNAKLAR_SEO = {
  tr: {
    title: 'Yapay Zekâ Kaynakları: Araçlar ve Açık Kaynak Projeler | Mehmet KURU',
    description:
      "Mehmet KURU'nun kullandığı ve önerdiği yapay zekâ araçları, Claude becerileri, MCP eklentileri ve açık kaynak projeler; ne işe yarar, nasıl başlanır.",
    detaySonEki: 'Kaynaklar | Mehmet KURU',
    anaSayfa: 'Ana Sayfa',
    kaynaklar: 'Kaynaklar',
  },
  en: {
    title: 'AI Resources: Tools, Skills and Open-Source Projects | Mehmet KURU',
    description:
      'AI tools, Claude skills, MCP plugins and open-source projects that Mehmet KURU uses and recommends — what each one does and how to get started.',
    detaySonEki: 'Resources | Mehmet KURU',
    anaSayfa: 'Home',
    kaynaklar: 'Resources',
  },
  de: {
    title: 'KI-Ressourcen: Tools, Skills und Open-Source-Projekte | Mehmet KURU',
    description:
      'KI-Tools, Claude-Skills, MCP-Plugins und Open-Source-Projekte, die Mehmet KURU nutzt und empfiehlt – wofür sie gut sind und wie der Einstieg gelingt.',
    detaySonEki: 'Ressourcen | Mehmet KURU',
    anaSayfa: 'Startseite',
    kaynaklar: 'Ressourcen',
  },
  ar: {
    title: 'موارد الذكاء الاصطناعي: أدوات ومهارات ومشاريع مفتوحة المصدر | Mehmet KURU',
    description:
      'أدوات ذكاء اصطناعي ومهارات Claude وإضافات MCP ومشاريع مفتوحة المصدر يستخدمها Mehmet KURU ويوصي بها: ما فائدة كل منها وكيف تبدأ.',
    detaySonEki: 'الموارد | Mehmet KURU',
    anaSayfa: 'الرئيسية',
    kaynaklar: 'الموارد',
  },
  ru: {
    title: 'ИИ-ресурсы: инструменты, навыки и open source | Mehmet KURU',
    description:
      'ИИ-инструменты, навыки Claude, MCP-плагины и проекты с открытым кодом, которые использует и рекомендует Mehmet KURU: для чего они и как начать.',
    detaySonEki: 'Ресурсы | Mehmet KURU',
    anaSayfa: 'Главная',
    kaynaklar: 'Ресурсы',
  },
  zh: {
    title: 'AI 资源：工具、技能与开源项目 | Mehmet KURU',
    description: 'Mehmet KURU 正在使用并推荐的 AI 工具、Claude 技能、MCP 插件和开源项目：各自的用途以及如何上手。',
    detaySonEki: '资源 | Mehmet KURU',
    anaSayfa: '首页',
    kaynaklar: '资源',
  },
  hi: {
    title: 'AI संसाधन: टूल, स्किल्स और ओपन-सोर्स प्रोजेक्ट | Mehmet KURU',
    description:
      'Mehmet KURU जिन AI टूल, Claude स्किल्स, MCP प्लगइन और ओपन-सोर्स प्रोजेक्ट का उपयोग व सिफ़ारिश करते हैं — हर एक किस काम आता है और कैसे शुरू करें।',
    detaySonEki: 'संसाधन | Mehmet KURU',
    anaSayfa: 'होम',
    kaynaklar: 'संसाधन',
  },
};

/** Ayrıntı sayfasının <title>'ı: "<kaynak> · <son ek>". */
export function kaynakBasligi(baslik, dil) {
  const seo = KAYNAKLAR_SEO[dil] ?? KAYNAKLAR_SEO.tr;
  return `${baslik} · ${seo.detaySonEki}`;
}

/** Meta açıklama: 160 karakteri aşarsa kelime sınırında kısaltılır. */
export function metaAciklama(metin) {
  const temiz = String(metin ?? '').replace(/\s+/g, ' ').trim();
  if (temiz.length <= 160) return temiz;
  const kesik = temiz.slice(0, 157);
  const bosluk = kesik.lastIndexOf(' ');
  return `${(bosluk > 100 ? kesik.slice(0, bosluk) : kesik).trimEnd()}…`;
}
