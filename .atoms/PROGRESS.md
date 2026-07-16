---
last_updated: 2026-07-16T17:53:26Z
---

# Requirements & Progress

## Requirements Overview
Build mehmetkuru.dev — a professional portfolio + agency website with 3D animated hero, About/Services/Portfolio/Blog/Contact pages, client & admin management panels, and Atoms Cloud auth/database backend.

## User Stories
- As a visitor, I want to see a striking 3D animated hero on the homepage so that I feel the brand quality.
- As a visitor, I want to browse services and portfolio work so I can evaluate hiring the agency.
- As a visitor, I want to read blog articles related to the industry.
- As a visitor, I want to contact via a form, WhatsApp button, and social links.
- As a client, I want to log in and view my project status in a management panel.
- As an admin, I want to log in and manage projects, blog posts, and client accounts.

## Task Breakdown
| ID | Task | Assignee | Status | Deps |
|----|------|----------|--------|------|
| T1 | Initialize backend template (frontend + Atoms Cloud) | Alex | Pending | — |
| T2 | Design and build homepage with 3D hero | Alex | Pending | T1 |
| T3 | Build About / Services / Portfolio / Blog / Contact pages | Alex | Pending | T1 |
| T4 | Implement client login + panel | Alex | Pending | T1 |
| T5 | Implement admin login + panel | Alex | Pending | T1 |
| T6 | Wire Atoms Cloud backend entities (projects, blog posts) | Alex | Pending | T1 |
| T7 | Lint + build + CheckUI validation | Alex | Done | T2-T6 |

## Progress Log
- 2026-07-16 | Initial repo commit ("original")
- 2026-07-16 | Context files bootstrapped from .wiki.md summary
- 2026-07-16 | Backend template initialized; projects/blog_posts/inquiries tables created; mock data seeded
- 2026-07-16 | Hero images and portfolio/blog imagery generated (10 assets)
- 2026-07-16 | Frontend built: Layout, Hero3D (three.js), Home, About, Services, Portfolio, Blog, Contact, ClientPanel, AdminPanel
- 2026-07-16 | Lint + build passed; CheckUI grade 4
- 2026-07-16 | Added i18n (EN/TR/DE) with react-i18next; language switcher in nav; all pages translated; lint+build pass
- 2026-07-16 | Added Packages page (5 pricing cards: $100/$300/$500/$700/DevOps) with Buy Now buttons; updated contact info (by@mehmetkuru.dev, 0541 296 58 78, Sultan Selim Mah address) across Contact page and footer

