import { Toaster } from '@/components/ui/sonner';
import { ekliLazy } from '@/i18n/ekliLazy';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
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
const Contact = lazy(() => import('./pages/Contact'));
const ClientPanel = lazy(() => import('./pages/ClientPanel'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));
const OdemeSayfasi = lazy(() => import('./pages/OdemeSayfasi'));
const YolHaritasi = lazy(() => import('./pages/YolHaritasi'));
const SiteAnalizi = ekliLazy('siteAnalizi', () => import('./pages/SiteAnalizi'));
const SiteRaporu = ekliLazy('siteAnalizi', () => import('./pages/SiteRaporu'));
const IslemSayfasi = ekliLazy('islem', () => import('./pages/IslemSayfasi'));
// Faz 2A: müşterinin açtığı herkese açık durum sayfası (dinamik, prerender yok).
const DurumSayfasi = ekliLazy('siteBakim', () => import('./pages/DurumSayfasi'));
// Faz 2C: girişsiz dosya paylaşımı ve yazdırmaya uygun aylık rapor (ikisi de noindex, prerender yok).
const PaylasSayfasi = ekliLazy('dosyalar', () => import('./pages/PaylasSayfasi'));
const AylikRaporSayfasi = ekliLazy('aylikRapor', () => import('./pages/AylikRaporSayfasi'));
// Faz 2E: hesap ekibi daveti (jetonlu, noindex, prerender yok).
const HesapDavetSayfasi = ekliLazy('hesapEkibi', () => import('./pages/HesapDavetSayfasi'));
// Faz 3K: herkese açık Kaynaklar (7 dil, prerender). Metinleri ek pakette, verisi API'de/gömülü.
const KaynaklarListesi = ekliLazy('kaynaklar', () => import('./pages/kaynaklar/KaynaklarListesi'));
const KaynakDetay = ekliLazy('kaynaklar', () => import('./pages/kaynaklar/KaynakDetay'));

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
        <Route path="durum/:slug" element={<DurumSayfasi />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      {/* Aylık müşteri raporu: site düzeni dışında (yazdırınca yalnız rapor çıksın). İmzalı jeton, noindex. */}
      <Route path="/rapor-aylik/:jeton" element={<AylikRaporSayfasi />} />
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