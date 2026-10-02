import { Toaster } from '@/components/ui/sonner';
import { ekliLazy } from '@/i18n/ekliLazy';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import Layout from './components/Layout';
// Ana sayfa LCP kritik yolda olduğu için ayrı chunk isteği yapmadan doğrudan yüklenir.
import Index from './pages/Index';
// Hafif 404 sayfası: platform eklentisinin ~366 kB'lık varsayılan 404 modülünü
// ana bundle'a enjekte etmesini engeller.
import NotFoundPage from './pages/NotFoundPage';
import LanguageGate from './components/LanguageGate';

const AuthCallback = lazy(() => import('./pages/AuthCallback'));
const AuthError = lazy(() => import('./pages/AuthError'));
const Services = lazy(() => import('./pages/Services'));
const Portfolio = lazy(() => import('./pages/Portfolio'));
const Marketplace = lazy(() => import('./pages/Marketplace'));
const BlogIndexPage = lazy(() => import('./pages/blog/BlogIndexPage'));
const BlogPostPage = lazy(() => import('./pages/blog/BlogPostPage'));
// Faz 3Y: iletişim formunun altındaki kısa aydınlatma satırı (ek paket 'aydinlatma');
// Faz 4G: rızaya bağlı harita yer tutucusu (ek paket 'iletisimHarita').
const Contact = ekliLazy(['aydinlatma', 'iletisimHarita'], () => import('./pages/Contact'));
const ClientPanel = lazy(() => import('./pages/ClientPanel'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));
const OdemeSayfasi = lazy(() => import('./pages/OdemeSayfasi'));
const YolHaritasi = lazy(() => import('./pages/YolHaritasi'));
const SiteAnalizi = ekliLazy(['siteAnalizi', 'aydinlatma'], () => import('./pages/SiteAnalizi'));
const SiteRaporu = ekliLazy('siteAnalizi', () => import('./pages/SiteRaporu'));
const IslemSayfasi = ekliLazy('islem', () => import('./pages/IslemSayfasi'));
// Faz 2A: müşterinin açtığı herkese açık durum sayfası (dinamik, prerender yok).
const DurumSayfasi = ekliLazy('siteBakim', () => import('./pages/DurumSayfasi'));
// Faz 2C: girişsiz dosya paylaşımı ve yazdırmaya uygun aylık rapor (ikisi de noindex, prerender yok).
const PaylasSayfasi = ekliLazy('dosyalar', () => import('./pages/PaylasSayfasi'));
const AylikRaporSayfasi = ekliLazy('aylikRapor', () => import('./pages/AylikRaporSayfasi'));
// Faz 2E: hesap ekibi daveti (jetonlu, noindex, prerender yok).
const HesapDavetSayfasi = ekliLazy('hesapEkibi', () => import('./pages/HesapDavetSayfasi'));
// Faz 3C: gömülebilir CRM formunun doğrudan bağlantısı (/form/<anahtar>; prerender yok, noindex).
// Formu `public/crm-form.js` çiziyor (etiketler sunucudan, 7 dil): ek paket gerekmiyor.
const CrmFormSayfasi = lazy(() => import('./pages/CrmFormSayfasi'));
// Faz 3T: girişsiz teklif ve sözleşme imza sayfaları (jetonlu, noindex, prerender yok).
const TeklifSayfasi = ekliLazy('teklif', () => import('./pages/TeklifSayfasi'));
const SozlesmeSayfasi = ekliLazy(['sozlesme', 'teklif'], () => import('./pages/SozlesmeSayfasi'));
// Faz 3K: herkese açık Kaynaklar (7 dil, prerender). Metinleri ek pakette, verisi API'de/gömülü.
const KaynaklarListesi = ekliLazy('kaynaklar', () => import('./pages/kaynaklar/KaynaklarListesi'));
const KaynakDetay = ekliLazy('kaynaklar', () => import('./pages/kaynaklar/KaynakDetay'));
// Faz 3Y: yasal sayfalar (Gizlilik/KVKK, Kullanım Koşulları, Çerez Politikası) — tek bileşen,
// metinleri ek pakette (7 dil), prerender + SEO. Veri sorumlusu bilgileri site ayarlarından.
const YasalSayfa = ekliLazy('yasal', () => import('./pages/yasal/YasalSayfa'));
// Faz 4K: herkese açık dijital kartvizit ve Google yorum sayfası — site düzeni dışında, prerender
// yok, varsayılan noindex. Metinler kartın KENDİ dilinde (i18n/kartSayfasi, sayfa kendisi yüklüyor).
const KartSayfasi = lazy(() => import('./pages/KartSayfasi'));
const YorumSayfasi = lazy(() => import('./pages/YorumSayfasi'));

/** Faz 4K: `/en/kart/x` → `/kart/x` (kartın kendi dili var; dil öneki gerekmiyor). */
function KokAdreseYonlendir({ onek }: { onek: 'kart' | 'yorum' }) {
  const { slug = '' } = useParams<{ slug: string }>();
  return <Navigate to={`/${onek}/${encodeURIComponent(slug)}`} replace />;
}
// Faz 4M: herkese açık QR menü / WhatsApp katalog (/menu/<slug>) — site düzeni dışında,
// prerender yok, site haritasında yok; og/robots Pages Function'ında (functions/menu/[slug].js).
const MenuSayfasi = ekliLazy('qrMenuSayfa', () => import('./pages/MenuSayfasi'));
// Faz 5R: herkese açık randevu sayfası (/randevu/<slug>[/<tür>], /randevu/yonet/<jeton>) — site düzeni
// dışında, prerender yok, site haritasında yok; og/robots Pages Function'ında (functions/randevu/[[yol]].js).
const RandevuSayfasi = ekliLazy('randevuSayfa', () => import('./pages/RandevuSayfasi'));
// Faz 5A: herkese açık AI asistan (/asistan/<anahtar>, gömülü ?gomulu=1) — site düzeni dışında, prerender yok,
// her zaman noindex; metinleri sayfa kendisi yüklüyor (i18n/ek/asistanSayfa); CSP/frame-ancestors Pages Function'ında.
const AsistanSayfasi = lazy(() => import('./pages/AsistanSayfasi'));

const queryClient = new QueryClient();

const PageLoader = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <div className="w-8 h-8 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
  </div>
);

const AppRoutes = () => (
  <Suspense fallback={<PageLoader />}>
    <Routes>
      {/* Türkçe kökte, ön eksiz. Blog yalnızca Türkçe yayımlanıyor. */}
      <Route element={<Layout />}>
        <Route path="/" element={<Index />} />
        <Route path="/services" element={<Services />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/marketplace" element={<Marketplace />} />
        <Route path="/blog" element={<BlogIndexPage />} />
        <Route path="/blog/:slug" element={<BlogPostPage />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/yol-haritasi" element={<YolHaritasi />} />
        <Route path="/site-analizi" element={<SiteAnalizi />} />
        <Route path="/kaynaklar" element={<KaynaklarListesi />} />
        <Route path="/kaynaklar/:slug" element={<KaynakDetay />} />
        <Route path="/gizlilik" element={<YasalSayfa sayfa="gizlilik" />} />
        <Route path="/kullanim-kosullari" element={<YasalSayfa sayfa="kullanimKosullari" />} />
        <Route path="/cerez-politikasi" element={<YasalSayfa sayfa="cerezPolitikasi" />} />
        <Route path="/client" element={<ClientPanel />} />
        <Route path="/admin" element={<AdminPanel />} />
        {/* Müşteriye giden ödeme bağlantısı. Oturum istemiyor. */}
        <Route path="/ode/:jeton" element={<OdemeSayfasi />} />
        {/* E-postayla giden tam site analiz raporu. Oturum istemiyor, noindex. */}
        <Route path="/rapor/:jeton" element={<SiteRaporu />} />
        {/* İmzalı işlem bağlantısı (teklif kabulü, teslim onayı). Oturum istemiyor, noindex. */}
        <Route path="/islem/:jeton" element={<IslemSayfasi />} />
        {/* Herkese açık durum sayfası (/durum/<slug>). Varsayılan noindex; müşteri seçerse index. */}
        <Route path="/durum/:slug" element={<DurumSayfasi />} />
        {/* Süreli, isteğe bağlı parolalı dosya paylaşımı (/paylas/<jeton>). Oturum istemiyor, noindex. */}
        <Route path="/paylas/:jeton" element={<PaylasSayfasi />} />
        {/* Faz 2E: müşteri hesabına ekip daveti (/hesap-davet/<jeton>). Bilgi girişsiz, kabul girişli; noindex. */}
        <Route path="/hesap-davet/:jeton" element={<HesapDavetSayfasi />} />
        {/* Faz 3T: teklif (görüntüle, kabul/ret, PDF) ve sözleşme imzası. Oturum istemiyor, noindex. */}
        <Route path="/teklif/:jeton" element={<TeklifSayfasi />} />
        <Route path="/sozlesme/:jeton" element={<SozlesmeSayfasi />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      {/*
        Diğer altı dil `/en`, `/de`, `/ar`, `/ru`, `/zh`, `/hi` ön ekiyle.
        Dil artık URL'de: her varyantın kendi canonical'ı ve hreflang'i var,
        önceki `?lang=xx` sorgu parametreleri gibi aynı HTML'i yedi ayrı
        adreste sunmuyor. LanguageGate desteklenmeyen kodlarda 404 döner.
      */}
      <Route path="/:lang" element={<LanguageGate />}>
        <Route index element={<Index />} />
        <Route path="services" element={<Services />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="marketplace" element={<Marketplace />} />
        <Route path="contact" element={<Contact />} />
        <Route path="yol-haritasi" element={<YolHaritasi />} />
        <Route path="site-analizi" element={<SiteAnalizi />} />
        <Route path="kaynaklar" element={<KaynaklarListesi />} />
        <Route path="kaynaklar/:slug" element={<KaynakDetay />} />
        <Route path="gizlilik" element={<YasalSayfa sayfa="gizlilik" />} />
        <Route path="kullanim-kosullari" element={<YasalSayfa sayfa="kullanimKosullari" />} />
        <Route path="cerez-politikasi" element={<YasalSayfa sayfa="cerezPolitikasi" />} />
        <Route path="durum/:slug" element={<DurumSayfasi />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      {/* Aylık müşteri raporu: site düzeni dışında (yazdırınca yalnız rapor çıksın). İmzalı jeton, noindex. */}
      <Route path="/rapor-aylik/:jeton" element={<AylikRaporSayfasi />} />
      {/* Faz 3C: CRM formu — site düzeni dışında (sade sayfa, çerçevede önizlenebilir). noindex. */}
      <Route path="/form/:anahtar" element={<CrmFormSayfasi />} />
      {/* Faz 4K: dijital kartvizit / bio link ve Google yorum sayfası (değişmez kodla da açılır). */}
      <Route path="/kart/:slug" element={<KartSayfasi />} />
      <Route path="/yorum/:slug" element={<YorumSayfasi />} />
      <Route path="/:lang/kart/:slug" element={<KokAdreseYonlendir onek="kart" />} />
      <Route path="/:lang/yorum/:slug" element={<KokAdreseYonlendir onek="yorum" />} />
      {/* Faz 4M: QR menü / katalog — site düzeni dışında (restoranın kendi sayfası gibi). */}
      <Route path="/menu/:slug" element={<MenuSayfasi />} />
      {/* Faz 5R: randevu — site düzeni dışında; yönetim bağlantısı girişsiz (imzalı jeton). */}
      <Route path="/randevu/yonet/:jeton" element={<RandevuSayfasi />} />
      <Route path="/randevu/:slug" element={<RandevuSayfasi />} />
      <Route path="/randevu/:slug/:tur" element={<RandevuSayfasi />} />
      {/* Faz 5A: AI asistan — site düzeni dışında (paylaşılabilir tam sayfa ve gömülü pencere). */}
      <Route path="/asistan/:anahtar" element={<AsistanSayfasi />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/auth/error" element={<AuthError />} />
    </Routes>
  </Suspense>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster theme="dark" position="top-right" />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };