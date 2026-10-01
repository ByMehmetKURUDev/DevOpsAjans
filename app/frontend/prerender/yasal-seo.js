/**
 * Yasal sayfaların (Faz 3Y) varsayılan başlık ve açıklamaları — 7 dil.
 *
 * Neden `site.js` içindeki PAGE_SEO'da değil? `site.js` Layout üzerinden
 * ana sayfanın ilk JS paketine giriyor; bu metinler oraya konunca ana sayfa
 * ziyaretçisi hiç açmayacağı üç sayfanın yedi dillik başlığını indirirdi.
 * Burada durunca yalnız prerender (Node), tembel yüklenen yasal sayfalar ve
 * yönetici panelindeki SEO düzenleyicisi okuyor (aynı düzen: kaynaklar-seo.js).
 *
 * Yollar, hreflang, site haritası ve panelden SEO metni değiştirme yine
 * `site.js`'te (PAGE_KEYS, PAGE_PATHS, PAGE_SEO_KEYS).
 *
 * Bağımlılığı olmayan düz JS.
 */
export const YASAL_SEO = {
  tr: {
    gizlilik: {
      title: 'Gizlilik Politikası ve KVKK Aydınlatma Metni | Mehmet KURU',
      description:
        "mehmetkuru.dev'de hangi kişisel verilerin hangi amaç ve hukuki sebeple işlendiği, kimlere aktarıldığı, ne kadar saklandığı ve KVKK kapsamındaki haklarınız.",
    },
    kullanimKosullari: {
      title: 'Kullanım Koşulları | By Mehmet KURU Dev',
      description:
        'mehmetkuru.dev sitesi, müşteri paneli ve hizmetlerin kullanım koşulları: hesap, ödeme, cayma ve iade, fikri mülkiyet, sorumluluk ve uyuşmazlıklar.',
    },
    cerezPolitikasi: {
      title: 'Çerez Politikası | By Mehmet KURU Dev',
      description:
        "mehmetkuru.dev'de kullanılan çerezler ve tarayıcı depolama öğeleri: adları, amaçları ve süreleri. Analitik ve pazarlama araçları yalnız onayınızla yüklenir.",
    },
  },
  en: {
    gizlilik: {
      title: 'Privacy Policy and KVKK Notice | Mehmet KURU',
      description:
        'What personal data mehmetkuru.dev processes, why and on what legal basis, who receives it, how long it is kept and your rights under Turkish data protection law (KVKK).',
    },
    kullanimKosullari: {
      title: 'Terms of Use | By Mehmet KURU Dev',
      description:
        'Terms of use for the mehmetkuru.dev website, client portal and services: accounts, payments, withdrawal and refunds, intellectual property, liability and disputes.',
    },
    cerezPolitikasi: {
      title: 'Cookie Policy | By Mehmet KURU Dev',
      description:
        'Cookies and browser storage used on mehmetkuru.dev: names, purposes and lifetimes. Analytics and marketing tools load only with your consent.',
    },
  },
  de: {
    gizlilik: {
      title: 'Datenschutzerklärung und KVKK-Hinweise | Mehmet KURU',
      description:
        'Welche personenbezogenen Daten mehmetkuru.dev wofür und auf welcher Rechtsgrundlage verarbeitet, wer sie erhält, wie lange sie gespeichert werden und Ihre Rechte nach dem KVKK.',
    },
    kullanimKosullari: {
      title: 'Nutzungsbedingungen | By Mehmet KURU Dev',
      description:
        'Nutzungsbedingungen für die Website mehmetkuru.dev, das Kundenportal und die Leistungen: Konto, Zahlung, Widerruf und Erstattung, geistiges Eigentum, Haftung und Streitfälle.',
    },
    cerezPolitikasi: {
      title: 'Cookie-Richtlinie | By Mehmet KURU Dev',
      description:
        'Cookies und Browser-Speicher auf mehmetkuru.dev: Namen, Zwecke und Speicherdauer. Analyse- und Marketing-Tools werden nur mit Ihrer Einwilligung geladen.',
    },
  },
  ar: {
    gizlilik: {
      title: 'سياسة الخصوصية وإشعار KVKK | Mehmet KURU',
      description:
        'ما البيانات الشخصية التي يعالجها mehmetkuru.dev، ولأي غرض وعلى أي أساس قانوني، ومن يتلقاها، ومدة حفظها، وحقوقك بموجب قانون حماية البيانات التركي (KVKK).',
    },
    kullanimKosullari: {
      title: 'شروط الاستخدام | By Mehmet KURU Dev',
      description:
        'شروط استخدام موقع mehmetkuru.dev وبوابة العملاء والخدمات: الحساب، والدفع، والعدول والاسترداد، والملكية الفكرية، والمسؤولية، والنزاعات.',
    },
    cerezPolitikasi: {
      title: 'سياسة ملفات تعريف الارتباط | By Mehmet KURU Dev',
      description:
        'ملفات تعريف الارتباط وعناصر تخزين المتصفح المستخدمة في mehmetkuru.dev: أسماؤها وأغراضها ومددها. أدوات التحليلات والتسويق لا تُحمَّل إلا بموافقتك.',
    },
  },
  ru: {
    gizlilik: {
      title: 'Политика конфиденциальности и уведомление KVKK | Mehmet KURU',
      description:
        'Какие персональные данные обрабатывает mehmetkuru.dev, с какой целью и на каком основании, кому они передаются, сколько хранятся и ваши права по турецкому закону KVKK.',
    },
    kullanimKosullari: {
      title: 'Условия использования | By Mehmet KURU Dev',
      description:
        'Условия использования сайта mehmetkuru.dev, клиентского портала и услуг: аккаунт, оплата, отказ и возврат, интеллектуальная собственность, ответственность и споры.',
    },
    cerezPolitikasi: {
      title: 'Политика в отношении файлов cookie | By Mehmet KURU Dev',
      description:
        'Файлы cookie и хранилище браузера на mehmetkuru.dev: названия, цели и сроки. Инструменты аналитики и рекламы загружаются только с вашего согласия.',
    },
  },
  zh: {
    gizlilik: {
      title: '隐私政策与 KVKK 告知书 | Mehmet KURU',
      description:
        'mehmetkuru.dev 处理哪些个人数据、出于何种目的和法律依据、提供给谁、保存多久，以及您依据土耳其个人数据保护法（KVKK）享有的权利。',
    },
    kullanimKosullari: {
      title: '使用条款 | By Mehmet KURU Dev',
      description: 'mehmetkuru.dev 网站、客户门户及各项服务的使用条款：账户、付款、撤回与退款、知识产权、责任与争议解决。',
    },
    cerezPolitikasi: {
      title: 'Cookie 政策 | By Mehmet KURU Dev',
      description: 'mehmetkuru.dev 使用的 Cookie 和浏览器存储项：名称、用途与保存期限。分析和营销工具仅在您同意后加载。',
    },
  },
  hi: {
    gizlilik: {
      title: 'गोपनीयता नीति और KVKK सूचना | Mehmet KURU',
      description:
        'mehmetkuru.dev कौन-सा व्यक्तिगत डेटा किस उद्देश्य और कानूनी आधार पर संसाधित करता है, किसे देता है, कितने समय रखता है और तुर्की डेटा संरक्षण कानून (KVKK) के तहत आपके अधिकार।',
    },
    kullanimKosullari: {
      title: 'उपयोग की शर्तें | By Mehmet KURU Dev',
      description:
        'mehmetkuru.dev वेबसाइट, क्लाइंट पोर्टल और सेवाओं के उपयोग की शर्तें: खाता, भुगतान, निरसन और धनवापसी, बौद्धिक संपदा, दायित्व और विवाद।',
    },
    cerezPolitikasi: {
      title: 'कुकी नीति | By Mehmet KURU Dev',
      description:
        'mehmetkuru.dev पर उपयोग होने वाली कुकीज़ और ब्राउज़र स्टोरेज: नाम, उद्देश्य और अवधि। एनालिटिक्स और मार्केटिंग टूल केवल आपकी सहमति से लोड होते हैं।',
    },
  },
};

/** Sayfanın o dildeki varsayılan SEO metni (yoksa Türkçe). */
export function yasalSeo(dil, sayfa) {
  return (YASAL_SEO[dil] ?? YASAL_SEO.tr)[sayfa] ?? YASAL_SEO.tr[sayfa];
}
