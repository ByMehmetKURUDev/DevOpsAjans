import { Toaster } from '@/components/ui/sonner';
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
const BlogIndexPage = lazy(() => import('./pages/blog/BlogIndexPage'));
const BlogPostPage = lazy(() => import('./pages/blog/BlogPostPage'));
const Contact = lazy(() => import('./pages/Contact'));
const ClientPanel = lazy(() => import('./pages/ClientPanel'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));

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
        <Route path="/blog" element={<BlogIndexPage />} />
        <Route path="/blog/:slug" element={<BlogPostPage />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/client" element={<ClientPanel />} />
        <Route path="/admin" element={<AdminPanel />} />
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
        <Route path="contact" element={<Contact />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

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