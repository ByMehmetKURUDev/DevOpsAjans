---
last_updated: 2026-07-16T17:53:26Z
---

# Architecture Design

## System Overview
Single-page React application with client-side routing for the marketing site (Home, About, Services, Portfolio, Blog, Contact) plus authenticated Client Panel and Admin Panel routes. Atoms Cloud backend provides authentication, entity CRUD (projects, blog posts, inquiries), and file storage.

## Tech Stack
- Frontend: React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui
- 3D: three.js (native WebGL, no fiber/drei)
- Routing: react-router-dom
- Icons: lucide-react
- Backend: Atoms Cloud (Auth + Database + Storage + Edge Functions)

## Module Design
| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| Layout & Navigation | Global header, footer, theme, routing shell | src/App.tsx, src/components/Layout.tsx |
| Home + 3D Hero | Landing page with three.js animated hero | src/pages/Home.tsx, src/components/Hero3D.tsx |
| Marketing Pages | About, Services, Portfolio, Blog, Contact | src/pages/*.tsx |
| Auth | Login/register for clients & admins via Atoms | src/pages/Auth.tsx |
| Client Panel | Client dashboard: view own projects | src/pages/ClientPanel.tsx |
| Admin Panel | Admin dashboard: manage projects, blog posts, inquiries | src/pages/AdminPanel.tsx |
| Backend Entities | projects, blog_posts, inquiries tables | app/backend/models, edge functions |

## Tech Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| 3D library | three.js native | Platform rule for 3D scenes |
| Backend | Atoms Cloud | Built-in auth + DB, no need for external services |
| Auth model | Atoms user roles (client vs admin) | Reuse Atoms auth per platform rule |
| Styling | Tailwind + shadcn/ui | Speed + modern aesthetic |
| Blog storage | Atoms DB entity | Enables admin CMS via panel |

## File Tree Plan
```
app/frontend/
├── src/
│   ├── App.tsx                  # Router shell
│   ├── main.tsx                 # Entry
│   ├── components/
│   │   ├── Layout.tsx           # Header + Footer + WhatsApp FAB
│   │   └── Hero3D.tsx           # three.js animated hero
│   ├── pages/
│   │   ├── Home.tsx
│   │   ├── About.tsx
│   │   ├── Services.tsx
│   │   ├── Portfolio.tsx
│   │   ├── Blog.tsx
│   │   ├── Contact.tsx
│   │   ├── Auth.tsx
│   │   ├── ClientPanel.tsx
│   │   └── AdminPanel.tsx
│   └── index.css
└── public/assets/               # logo, brand images
app/backend/                     # Atoms Cloud config, entities, edge functions
```

## Implementation Guide
1. Run FrontendEngineer.use_template("backend") to scaffold frontend + Atoms Cloud backend.
2. Copy user-provided logo (logo.avif) and reference imagery into public/assets/.
3. Generate hero background + service/portfolio imagery via image-generation skill.
4. Build Layout (header/nav, footer, floating WhatsApp button, social links).
5. Implement Hero3D with three.js (animated particle/geometry scene, mouse-parallax).
6. Build marketing pages with modern gradient + glassmorphism aesthetic.
7. Define backend entities: projects (title, description, category, image_url, client_id), blog_posts (title, slug, content, cover_image, author), inquiries (name, email, message).
8. Add Atoms Auth login/register page; on login, role-based redirect to Client or Admin panel.
9. Client Panel: list own projects (filtered by client_id).
10. Admin Panel: CRUD for projects, blog posts, view inquiries.
11. Run pnpm i && pnpm run lint && pnpm run build; then CheckUI.run.

