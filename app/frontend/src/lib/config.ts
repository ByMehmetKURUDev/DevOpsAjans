// Runtime configuration
let runtimeConfig: {
  API_BASE_URL: string;
} | null = null;

// Configuration loading state
let configLoading = true;

// Default fallback configuration
const defaultConfig = {
  API_BASE_URL: 'http://127.0.0.1:8000', // Only used if runtime config fails to load
};

/**
 * Çalışma zamanı yapılandırmasını hazır eder.
 *
 * Eskiden burada `/api/config` adresine bir istek vardı; o uç Lambda
 * döneminden kalmaydı ve bu arka uçta hiç yok. Her sayfa yüklemesinde
 * boşuna bir 404 alınıyor, konsola hata düşüyordu. İstek kaldırıldı:
 * API adresi zaten aynı origin'den göreli çözülüyor.
 */
export async function loadRuntimeConfig(): Promise<void> {
  configLoading = false;
}

// Get current configuration
export function getConfig() {
  // If config is still loading, return default config to avoid using stale Vite env vars
  if (configLoading) {
    console.log('Config still loading, using default config');
    return defaultConfig;
  }

  // First try runtime config (for Lambda)
  if (runtimeConfig) {
    console.log('Using runtime config');
    return runtimeConfig;
  }

  // Then try Vite environment variables (for local development)
  if (import.meta.env.VITE_API_BASE_URL) {
    const viteConfig = {
      API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
    };
    console.log('Using Vite environment config');
    return viteConfig;
  }

  // Finally fall back to default
  console.log('Using default config');
  return defaultConfig;
}

// Dynamic API_BASE_URL getter - this will always return the current config
export function getAPIBaseURL(): string {
  return getConfig().API_BASE_URL;
}

// For backward compatibility, but this should be avoided
// Removed static export to prevent using stale config values
// export const API_BASE_URL = getAPIBaseURL();

export const config = {
  get API_BASE_URL() {
    return getAPIBaseURL();
  },
};
