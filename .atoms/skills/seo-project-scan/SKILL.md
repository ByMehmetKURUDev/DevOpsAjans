---
name: seo-project-scan
description: Scan the frontend project efficiently, identify product value, routes and theme system, then persist a structured SEO context.
alwaysApply: true
roles:
  - Sarah
---

Use this skill whenever you need to understand a project before producing an SEO plan.

Goals:
- Extract enough product context quickly without over-reading.
- Identify how navigation works so SEO pages can fit the existing route-switching model.
- Identify how theming works so later blog integration can match the application shell.

Recommended workflow:
1. Use `Editor.find_file` to locate key files, then `Editor.read` to inspect them.
   Suggested targets:
   - Router or app entry files such as `App.tsx`, `main.tsx`, `router.tsx`, `routes.tsx`
   - The home page or landing page
   - A representative feature page with business logic
2. Stop when you have enough context:
   - 3+ concrete product features or use cases
   - Main audience and value proposition
   - Route structure or at least the app entry and navigation pattern
   - Theme mechanism or styling convention

After scanning, call `SEOSpecialist.set_project_context` with:
- `project_summary`: brief product summary with audience and value
- `routes`: list of `{path, description}` objects for meaningful app routes and CTA routes
- `theme_summary`: current theme tokens/layout/style system that blog pages should inherit

Assessment rules:
- If theme handling is unclear, summarize the styling stack you can prove from code instead of guessing.
