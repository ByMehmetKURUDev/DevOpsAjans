import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import fs from 'node:fs';
import path from 'path';
import { viteSourceLocator } from '@metagptx/vite-plugin-source-locator';
import { atoms } from '@metagptx/web-sdk/plugins';
import { vitePrerenderPlugin } from 'vite-prerender-plugin';
import Sitemap from 'vite-plugin-sitemap';
import { getAllPrerenderRoutes } from './prerender/blog-routes.js';
import { getSitemapLastmod } from './prerender/blog-sitemap.js';
import {
  BLOG_INDEX_ROUTE,
  DEFAULT_LANGUAGE,
  NOINDEX_ROUTES,
  PAGE_SEO,
  SITE_NAME,
  SITE_URL,
  getLocalizedRoutes,
} from './prerender/site.js';

function escapeHtmlAttr(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Şablon varsayılanları ("shadcnui", "Atoms Generated Project") üretim
 * çıktısına sızıyordu: blog dizininin başlığı Google'a `Blog | shadcnui`
 * olarak gidiyor, `VITE_SITE_URL` tanımsız olduğu için og:url hiç
 * üretilemiyordu. Varsayılanlar artık sitenin gerçek değerleri.
 */
process.env.VITE_APP_TITLE ??= process.env.OVERVIEW_TITLE ?? SITE_NAME;
process.env.VITE_APP_DESCRIPTION ??=
  process.env.OVERVIEW_DESCRIPTION ?? PAGE_SEO[DEFAULT_LANGUAGE].home.description;
process.env.VITE_SITE_URL ??= SITE_URL;
process.env.VITE_APP_TITLE = escapeHtmlAttr(process.env.VITE_APP_TITLE);
process.env.VITE_APP_DESCRIPTION = escapeHtmlAttr(process.env.VITE_APP_DESCRIPTION);
process.env.VITE_APP_LOGO_URL ??= process.env.OVERVIEW_LOGO_URL ?? `${SITE_URL}/logo192.png`;

/**
 * Teşhis eklentisi: her chunk içindeki modülleri gerçek (minified) boyutlarına
 * göre `bundle-stats.txt` dosyasına yazar. Yalnızca STATS=1 ile çalışır,
 * üretim build'ini etkilemez.
 */
function bundleStats() {
  return {
    name: 'bundle-stats',
    generateBundle(_options: unknown, bundle: Record<string, unknown>) {
      const lines: string[] = [];
      for (const [file, chunk] of Object.entries(bundle)) {
        const c = chunk as { type?: string; modules?: Record<string, { renderedLength: number }> };
        if (c.type !== 'chunk' || !c.modules) continue;
        const mods = Object.entries(c.modules)
          .map(([id, m]) => [id, m.renderedLength] as [string, number])
          .sort((a, b) => b[1] - a[1]);
        const total = mods.reduce((s, m) => s + m[1], 0);
        lines.push(`\n### ${file} — ${(total / 1024).toFixed(1)} kB`);
        mods.slice(0, 20).forEach(([id, len]) => {
          const short = id.replace(/^.*node_modules\//, 'nm/').replace(/^.*\/src\//, 'src/');
          lines.push(`${(len / 1024).toFixed(1).padStart(9)} kB  ${short}`);
        });
      }
      // Rapor doğrudan konsola yazılır: prerender eklentisinin ikinci build
      // geçişi bir dosyayı ezmesin ve kodlama sorunu yaşanmasın.
      if (lines.length > 0) {
        console.log(`\n===== BUNDLE STATS BEGIN =====${lines.join('\n')}\n===== BUNDLE STATS END =====`);
      }
    },
  };
}

function ensureBuildOutDir() {
  let outDir = path.resolve(__dirname, 'dist');

  return {
    name: 'ensure-build-out-dir',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir);
      // Klasör burada oluşturulmalı: sitemap eklentisi robots.txt'yi
      // closeBundle aşamasında yazıyor ve prerender'ın ilk geçişinde
      // writeBundle hiç çalışmadığı için temiz bir klonda ilk build
      // "ENOENT: dist/robots.txt" ile düşüyordu.
      fs.mkdirSync(outDir, { recursive: true });
    },
    writeBundle() {
      fs.mkdirSync(outDir, { recursive: true });
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig(({ command }) => {
  const prerenderRoutes = command === 'build' ? getAllPrerenderRoutes() : [];
  // Sitemap eklentisi yolları üretilen HTML'lerden eğik çizgisiz topluyor;
  // priority anahtarları da o biçimde olmalı. Türkçe sayfalar tam ağırlıkta,
  // dil varyantları bir kademe düşük.
  const sitemapPriority: Record<string, number> = Object.fromEntries([
    ...getLocalizedRoutes().map((route) => [
      route.path,
      route.lang === DEFAULT_LANGUAGE ? route.priority : route.priority - 0.2,
    ]),
    [BLOG_INDEX_ROUTE.routePath, BLOG_INDEX_ROUTE.priority],
  ]);

  return {
    plugins: [
      viteSourceLocator({
        prefix: 'mgx', // Prefix used to identify source locations; do not change.
      }),
      react(),
      atoms(),
      ensureBuildOutDir(),
      ...(process.env.STATS === '1' ? [bundleStats()] : []),
      Sitemap({
        hostname: SITE_URL,
        // `dynamicRoutes` VERİLMİYOR: eklenti prerender edilen HTML
        // dosyalarından yolları kendisi topluyor. İkisi birlikte verildiğinde
        // her URL sitemap'e iki kez giriyordu (biri eğik çizgili, biri değil).
        exclude: NOINDEX_ROUTES,
        lastmod: getSitemapLastmod(),
        // Blog yazıları ana sayfayla eşit ağırlıkta değil; her URL'in
        // priority 1.0 olması sıralamaya bilgi taşımıyordu.
        priority: { ...sitemapPriority, '*': 0.6 } as unknown as number,
        readable: true,
        generateRobotsTxt: true,
      }),
      ...(prerenderRoutes.length > 0
        ? vitePrerenderPlugin({
            renderTarget: '#root',
            prerenderScript: path.resolve(__dirname, 'prerender/app.js'),
            additionalPrerenderRoutes: prerenderRoutes,
          })
        : []),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0', // Listen on all network interfaces.
      port: parseInt(process.env.VITE_PORT || '3000'),
      proxy: {
        '/api': {
          target: `http://localhost:${process.env.BACKEND_PORT || '8000'}`,
          changeOrigin: true,
        },
      },
      watch: { usePolling: true, interval: 600 },
    },
    build: {
      rollupOptions: {
        output: {
          /**
           * Chunk stratejisi id tabanlı fonksiyon ile kurulur.
           *
           * Nesne biçimi (paket adı listesi) kodda hiç import edilmeyen paketleri de
           * zorla bundle grafiğine soktuğu için ölü kod üretiyordu. Fonksiyon biçimi
           * yalnızca gerçekten kullanılan modülleri gruplar; listelenmeyen paketler
           * Rollup'ın kullanım grafiğine bırakılır, böylece bir chunk yalnızca ona
           * ihtiyaç duyan route tarafından indirilir.
           */
          manualChunks(id: string) {
            if (!id.includes('node_modules')) return undefined;

            // Teşhis modu: her bağımlılığı kendi chunk'ına ayırarak gerçek
            // minified boyutlarını ölçmemizi sağlar. Üretim build'inde kapalıdır.
            if (process.env.ANALYZE === '1') {
              const after = id.split('node_modules/').pop() || '';
              const parts = after.split('/');
              const pkg = parts[0].startsWith('@') ? `${parts[0]}_${parts[1]}` : parts[0];
              return `dep-${pkg.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
            }

            // Grafik kütüphanesi yalnızca admin analitik sekmesinde kullanılıyor.
            if (
              id.includes('recharts') ||
              id.includes('victory-vendor') ||
              /node_modules\/d3-/.test(id)
            ) {
              return 'chart-vendor';
            }
            if (id.includes('markdown-to-jsx')) return 'markdown-vendor';
            if (id.includes('@metagptx')) return 'sdk-vendor';
            if (id.includes('react-router') || id.includes('@remix-run')) return 'router-vendor';
            if (id.includes('@tanstack')) return 'query-vendor';
            if (id.includes('i18next')) return 'i18n-vendor';
            if (
              id.includes('@radix-ui') ||
              id.includes('node_modules/sonner') ||
              id.includes('next-themes')
            ) {
              return 'ui-vendor';
            }
            if (
              /node_modules\/(react|react-dom|scheduler)\//.test(id) ||
              id.includes('node_modules/use-sync-external-store')
            ) {
              return 'react-vendor';
            }

            // Kalan paketler bilinçli olarak Rollup'a bırakılır: böylece yalnızca
            // ilgili route'un yüklediği chunk'a girerler.
            return undefined;
          },
        },
      },
      target: 'es2020',
      cssCodeSplit: true,
      sourcemap: process.env.ANALYZE === '1',
      reportCompressedSize: false,
      chunkSizeWarningLimit: 800,
    },
  };
});
