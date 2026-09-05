---
last_updated: 2026-07-16T17:53:26Z
status: active
---

# Project Context

## Project Overview
mehmetkuru.dev — a professional portfolio and agency website for "By Mehmet KURU Dev". Features a modern design with a 3D animated hero section, service/portfolio showcases, blog, and contact page. Includes user authentication and management panels for both clients and administrators via Atoms Cloud backend.

## Key Decisions
| Date | Decision | By | Rationale |
|------|----------|-----|-----------|
| 2026-07-16 | Use React + Vite + Tailwind + shadcn/ui frontend | Alex | Modern stack, matches template scaffold |
| 2026-07-16 | Use Atoms Cloud as backend | Alex | Provides built-in auth, DB, storage for client/admin panels |
| 2026-07-16 | Use three.js (native WebGL) for 3D hero | Alex | Instruction #17 mandates native three.js for 3D scenes |
| 2026-07-16 | Reference uploaded logo.avif and photo for brand identity | Alex | User-provided brand assets |
| 2026-09-05 | 3D hero (three.js) tamamen kaldırıldı | Alex | Bileşen artık kullanılmıyordu; ~370 kB JS ve mobil TBT yükü getiriyordu |
| 2026-09-05 | Görseller WebP + responsive srcset, PNG kaynakları silindi | Alex | LCP'yi düşürmek ve transfer boyutunu 20x azaltmak için |
| 2026-09-05 | i18n çeviri paketleri ve recharts lazy-load | Alex | Başlangıç JS yükünü küçültmek (TBT/FCP) |
| 2026-09-05 | GA4 yalnızca ilk etkileşim veya idle sonrası yüklenir | Alex | Render-blocking 3rd-party script'i kritik yoldan çıkarmak |

## Constraints
- 3D hero must use three.js directly (no react-three-fiber/drei).
- Modern, bold visual design with animations, gradients, glassmorphism where appropriate.
- Include WhatsApp contact button and social media links on Contact page.
- Blog section required.
- Both client-facing site and admin management panel must exist.
- Reuse Atoms authentication — do not create parallel admin auth system.
- File limit: no more than 8 code files for MVP scope.
- Reference uploaded assets: /workspace/uploads/logo.avif, PHOTO-2025-12-24-00-28-49.jpg, hero-3d-jack-portfolio-preview-BS06Nx21.gif.


