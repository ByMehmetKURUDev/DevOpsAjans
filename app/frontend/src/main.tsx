import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import './i18n';
import { loadRuntimeConfig } from './lib/config.ts';

function initializeApp() {
  // Prerendered blog pages are served as pure static HTML for SEO.
  // Intentionally skip React mounting so the crawler-facing markup stays
  // lightweight and self-contained — no client-side hydration needed.
  if (
    document
      .querySelector('meta[name="prerender-static-page"]')
      ?.getAttribute('content') === 'blog'
  ) {
    return;
  }

  // Runtime config yalnızca yönetim/auth yardımcıları tarafından kullanılıyor.
  // İlk boyamayı (LCP) geciktirmemek için beklemeden, paralel olarak yükleriz.
  void loadRuntimeConfig();

  createRoot(document.getElementById('root')!).render(<App />);
}

/**
 * Servis çalışanını kaydeder.
 *
 * Yalnızca üretimde ve yalnızca sayfa yüklendikten sonra: geliştirme
 * sunucusunda önbellek sıcak yeniden yüklemeyi bozuyor, `load` olayından
 * önce kaydetmek ise ilk boyamayla yarışıyor.
 *
 * Hata yutuluyor — servis çalışanı kaydedilemezse (eski tarayıcı, gizli
 * pencere, izin yok) site normal çalışmaya devam etmeli.
 */
function registerServiceWorker() {
  if (!import.meta.env.PROD) return;
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}

initializeApp();
registerServiceWorker();