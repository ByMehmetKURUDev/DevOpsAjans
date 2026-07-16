---
name: frontend-design
description: Frontend design constraints for React + Tailwind CSS + Shadcn/ui and Search functionality for UI/UX design intelligence across web/mobile stacks (React Native focus) And searching for design templates, choosing styles/colors/fonts, or generating design systems. Must use this skill when the you start to develop frontend project. Generates creative, polished code that avoids generic AI aesthetics.
alwaysApply: false
roles:
  - Alex
---

# Frontend-Design Reference

Load before writing any frontend code. This skill assumes the project uses the standard template: **React + TypeScript + Vite + Tailwind CSS + Shadcn/ui**. Also can use this skill when the task involves **searching for design templates, choosing styles/colors/fonts, or generating design systems for UI/UX design templates across 12 domains + brand design systems.**. All guidance maps directly to the files and config in the template. Every rule here is a design-time constraint: build it right from the start.

## Searching Must Use

- Choosing color schemes, typography, or UI styles for a project
- Generating a complete design system for a new project
- Looking up brand design references (Stripe, Airbnb, Linear, etc.)
- Finding landing page patterns or chart type recommendations
- Searching for Google Fonts or icon recommendations
- Getting React performance tips or app interface guidelines

## Searching Skip

- Pure backend logic, API, or database work
- Infrastructure or DevOps tasks
- Reviewing or fixing existing UI code (use ui-ux-pro-max instead)


---

## 1. Register selection

Every design task starts by choosing a register. All downstream decisions depend on it.

- **Brand**: design IS the product. Marketing pages, landing pages, brand sites, campaigns, portfolios, long-form content. The stance is *communicate, not transact*. Genres vary wildly: tech-minimal, luxury, consumer-warm, brutalist, editorial. Do not collapse them into a single look.
- **Product**: design SERVES the product. App UIs, admin dashboards, settings panels, data tables, tools, authenticated surfaces. The user is in a task. The tool should disappear into the task.

Priority: (1) cue in the task ("landing page" -> Brand, "dashboard" -> Product); (2) the surface being edited. First match wins.

### Register permissions

**Brand can, Product cannot:**

- Single-purpose viewports: one dominant idea per fold, long scroll
- Typographic risk: enormous display type, unexpected italic, mixed cases
- Unexpected color strategies. Palette IS voice
- Art direction per section: different sections can have different visual worlds
- Override Shadcn defaults heavily; build custom page-level compositions

**Product can, Brand cannot:**

- System fonts and default Shadcn styling. Familiarity is a feature
- Standard navigation: `Sidebar` + top bar, `Breadcrumb`, `Tabs`, `Command` palette
- Density: `Table` with many rows, panels with many labels
- Consistency over surprise. Same visual vocabulary across every screen

---

## 2. Quality gate & bans

Run before committing to any visual direction. If someone could say "AI made that" without doubt, it has failed.

### One goal per view

Name the single primary user goal in one sentence. If you cannot, the view needs splitting or progressive disclosure.

### Brand bar: distinctiveness

- **Name a real reference** before committing (e.g. "Klim-style specimen page", "Liquid Death acid maximalism", "Stripe purple restraint").
- **Reflex check**: can someone guess theme + palette from the category alone ("healthcare -> white + teal", "finance -> navy + gold")? If yes, rework.
- **Inverse test**: describe what you are about to build the way a competitor would. If it fits the modal landing page in that category, restart.

### Product bar: trust

Benchmark: Linear, Figma, Notion, Raycast, Stripe. A fluent user of those tools should trust this interface on first sight. The failure mode is not flatness; it is purposeless decoration: over-decorated buttons, mismatched form controls, gratuitous motion, display fonts in UI labels, invented affordances for standard tasks.

### Banned patterns

Reject on sight. These are dominant AI-design defaults and common quality failures.

**Cross-register bans:**

| Ban | Do instead |
|---|---|
| Gradient text (`bg-clip-text text-transparent`) | Single solid color; emphasize via weight or size |
| Cyan/purple gradients | Choose a palette specific to THIS project |
| Glassmorphism as default surface (`backdrop-blur bg-white/30`) | Solid backgrounds. Glass only if rare and purposeful |
| Neon on dark (`text-green-400` on `bg-gray-900`) | Tinted neutrals and the project's actual accent |
| Side-stripe borders (`border-l-4 border-blue-500`) | Full border, background tint, or leading icon |
| Hero-metric template (big number + small label, repeated 3-4x) | Design metrics contextually, not as a template block |
| Identical card grids (3+ cards, same structure) | Vary card sizes, content types, or use different layouts |
| Modal as first thought | Inline expansion, `Sheet`, `Popover`, or page navigation first |
| Gray text on colored bg | Darker shade of the background color, or foreground at reduced opacity |
| Pure black/white surfaces | Tinted neutrals from the palette. `bg-background`/`text-foreground` |
| Default Shadcn slate palette | Replace all token values with project-specific colors |
| Repeated uppercase labels above every section | Use sparingly as anchors, not systematically |

**Brand additional bans:**

- Monospace (`font-mono`) as lazy "technical" signaling when the brand is not technical
- Large rounded-corner icons above every heading
- Timid palette + average layout. Safe = invisible
- Zero imagery on briefs that imply it (restaurant, hotel, food, travel, fashion)
- Editorial-magazine aesthetics on non-editorial briefs. The editorial lane is saturated

**Product additional bans:**

- Decorative motion that does not convey state
- Inconsistent button variants across screens
- Display fonts (`font-display`) in UI labels, buttons, or data
- Reinventing standard affordances (custom scrollbars, non-standard modals, unusual form controls)
- `clamp()` for font sizes in app UI. Product uses fixed rem scale

---

## 3. Design foundation setup

Before writing page components, set up the design foundation by modifying these template files.

### 3a. Color system — `src/index.css`

The template ships with Shadcn default slate tokens in HSL format. **Replace them** with project-specific values.

**Pick a color strategy first** (do not skip this step):
- **Restrained**: tinted neutrals + one accent <=10%. Product default; brand minimalism.
- **Committed**: one saturated color carries 30-60% of the surface. Brand default.
- **Full palette**: 3-4 named roles, each used deliberately. Brand campaigns; product data viz.
- **Drenched**: the surface IS the color. Brand heroes, campaign pages.

**Color distribution target — 60/30/10 rule** (visual weight, not pixel count):
- 60% neutral backgrounds and surfaces
- 30% secondary/supporting colors
- 10% accent (CTAs, active states, focal points)

**Token roles and what to change in `:root` / `.dark`:**

| CSS variable | Role | Guidance |
|---|---|---|
| `--background` / `--foreground` | Page base | Tint toward brand hue. Never pure white or pure black. |
| `--primary` / `--primary-foreground` | CTAs, key actions | Brand color. Sparingly in Restrained; boldly in Committed+. |
| `--secondary` / `--secondary-foreground` | Supporting elements | Muted complement or neutral variant of primary. |
| `--muted` / `--muted-foreground` | Disabled, hints, captions | Low-chroma version of the palette. |
| `--accent` / `--accent-foreground` | Hover, highlights, current | Accent works because it is rare; overuse kills it. |
| `--destructive` / `--destructive-foreground` | Error, delete | Keep semantic; do not make this "the red in the palette." |
| `--border` / `--input` / `--ring` | Form controls, focus | Subtle; should not compete with content. |
| `--card` / `--card-foreground` | Elevated surfaces | Slightly different from background to create depth. |
| `--sidebar-*` | Side navigation | A second neutral layer, slightly cooler or warmer than content. |
| `--radius` | Border radius | Adjust globally here; all Shadcn components inherit it. |

**Tinted neutrals rule**: every neutral must carry a tiny color tint toward the project's brand hue. In HSL, shift the hue to match the brand and keep saturation at 3-8% instead of 0%.

**Concrete example — warm green product palette (Restrained strategy):** All neutrals (background, card, secondary, muted, border, input) share hue 80 (yellow-green) at 4-6% saturation, with lightness varying by role: background 98%, card 96%, secondary 93%, muted 92%, border/input 89%. The only high-saturation color is primary at hue 145 / 60% saturation / 32% lightness (deep green). Accent uses the same hue 145 at much lower saturation (45%) and high lightness (90%) for subtle tinting. For `.dark`: keep same hues, raise surface lightness per elevation (9% → 12% → 16% → 18%), desaturate accents slightly.

**Contrast minimums**: body text 4.5:1, large text 3:1, UI components 3:1.

**Color anti-reflexes:**
- Do not default to blue (hue ~210-250) or warm orange (hue ~30-60); tint neutrals toward THIS project's brand hue instead.
- When a cultural-symbol palette is the obvious pull (Chinese red, eco green), reach past it. Let cultural reading come from typography and imagery.
- Default saturation for non-accent colors: 70-85%, not full saturation.

**Dark mode (`.dark` block):**
- Depth comes from surface lightness, not shadow. Higher elevation = lighter surface.
- Desaturate accents slightly. Reduce font weight by one step for body text.
- Bump line-height by +0.05-0.1 and letter-spacing by +0.01-0.02em for body text.
- Design both light and dark token sets with correct contrast from the start.

**Palette structure** (plan before picking values):
- Primary: 1 color, 3-5 lightness shades
- Neutral: 9-11 shades (all tinted toward brand hue)
- Semantic: success, warning, error, info — 2-3 shades each
- Surface: 2-3 elevation levels (base, raised, overlay)

### 3b. Typography — `index.html` + `tailwind.config.ts` + `src/index.css`

The template ships with no custom font. The browser default (system font) is the starting point.

**Step 1: Choose font(s)**

For **Product** register: system fonts or Inter are legitimate. One family is often right. Use fixed rem scale, not fluid.

For **Brand** register:
1. Write three concrete brand-voice words. Not "modern" or "elegant" — physical-object words like "warm and mechanical and opinionated."
2. List the three fonts you would reach for by reflex. If any are on the reject list below, reject them.
3. Choose a font that matches the voice words but is NOT on the reject list and NOT your first reflex. Prefer fonts with distinctive optical character: unusual x-height, stroke contrast, or terminal shapes.
4. Cross-check: if the final pick feels "safe" or "obvious" for this category, reconsider.

**Reflex-reject font list** (training-data defaults — overused in AI output):
Fraunces, Newsreader, Lora, Crimson / Crimson Pro, Playfair Display, Cormorant / Cormorant Garamond, Syne, IBM Plex Mono / Sans / Serif, Space Mono, Space Grotesk, Inter (Brand only), DM Sans, DM Serif Display / Text, Outfit, Plus Jakarta Sans, Instrument Sans, Instrument Serif

**Step 2: Set type scale and vertical rhythm in `src/index.css`**

Line-height is the base unit for all vertical spacing. If body is 16px at 1.5 line-height, the rhythm unit is 24px. All vertical spacing should be multiples of this unit.

In `@layer base`: set body to text-base, leading-relaxed, font-kerning normal, text-wrap pretty. Set h1 to text-4xl, font-bold, leading-tight, tracking-tight, text-wrap balance. Set h2 to text-2xl, font-semibold, leading-snug, text-wrap balance. Set h3 to text-xl, font-semibold.

For **Brand** headings, use fluid type via clamp (e.g. h1: clamp(2rem, 5vw + 1rem, 4.5rem)). For **Product** headings, use fixed rem values only.

**Typography rules:**
- Scale ratio: Brand >=1.25 (major third), Product 1.125-1.2.
- Max body line length: `max-w-prose` (65ch). Data tables can run wider.
- Minimum body text: `text-base` (16px). Never smaller for reading.
- `font-variant-numeric: tabular-nums` for data tables, dashboards, and any column of numbers.
- ALL-CAPS labels: always add `tracking-wide` or `tracking-wider` (5-12% letter-spacing).
- Maximum 2 font families. Pairing fonts that are similar but not identical reads as a mistake.

**Typography anti-reflexes:**
- "Technical" does NOT need serif "for warmth."
- "Premium" does NOT need the same expressive serif everyone uses.
- "Modern" does NOT need a geometric sans.

### 3c. Theme decision — light or dark

Not dark "because tools look cool dark." Not light "to be safe."

Write one sentence describing the physical scene: who uses this, where, under what light, in what mood. If it does not force the answer, it is not concrete enough.

Implementation: the template uses `darkMode: ['class']`. Apply `.dark` to `<html>` for dark mode. Both `:root` and `.dark` token sets must be fully designed (see 3a).

### 3d. Spatial system

Use Tailwind's 4pt base grid. Pick spacing deliberately by role: 4px for icon-label gaps, 8-12px for related items, 16px for card padding, 24-32px for section spacing, 48-96px for major breaks and heroes. Vary spacing for rhythm; same padding everywhere is monotony.

**Gap over margin**: use `gap` (Flexbox/Grid) for sibling spacing instead of margins. Only use margin for spacing between unrelated sections.

**Self-adjusting grid**: for responsive card/item grids without breakpoints, use grid-template-columns with repeat(auto-fit, minmax(280px, 1fr)).

---

## 4. Page composition and layout

### Shared rules

- **Hierarchy**: build through multiple dimensions simultaneously: size (3:1+ ratio between primary and secondary), weight, color contrast, position, whitespace. Use the fewest dimensions needed. The squint test: blur your eyes. Can you identify the most important element, the second, and clear groupings?
- **Cards** (`<Card>`): only when content is truly distinct and actionable, items need grid comparison, or content needs interaction boundaries. Never nest cards inside cards. If 3+ cards have identical structure, vary sizes, content types, or use a different layout.
- **Containers**: do not wrap everything in a container. Use `max-w-screen-xl mx-auto px-4 sm:px-6 lg:px-8` only where content needs constraint.
- **Shadows**: use `shadow-sm` or `shadow`. If you reach for `shadow-lg` or `shadow-xl`, reconsider. Shadows should be barely visible.

### Brand layout

- Asymmetric compositions: break the grid intentionally. `grid-cols-5` with content spanning 3 + image spanning 2 is more interesting than 50/50. Try 70/30 or 80/20 splits.
- Do not default to centering everything. Left-aligned with asymmetric layouts feels designed; a centered stack of icon-title-subtitle cards reads as template.
- One dominant idea per viewport fold. Long scroll with deliberate pacing. Different sections can have different visual worlds.
- Alternative: a strict, visible grid as voice (Swiss / brutalist). Either asymmetric or rigorously-gridded works; the failure is splitting the difference into a generic centered stack.

### Product layout

- Predictable grids. Consistency IS an affordance.
- Familiar patterns: Shadcn `Sidebar` + top bar, `Breadcrumb`, `Tabs`, standard form layouts. Do not reinvent for flavor.
- Responsive is structural: collapse sidebar (`Sheet` on mobile), responsive tables, breakpoint-driven columns.

---

## 5. Component usage and interaction design

The template includes 50+ pre-built Shadcn/ui components. Use them as the primary vocabulary.

### Customize for Brand register

Brand surfaces may override Shadcn defaults via Tailwind classes to match the visual language. Examples:
- `<Button className="rounded-none tracking-wider uppercase text-sm">` for a brutalist brand
- `<Card className="border-0 shadow-none bg-transparent">` to break the default card look
- Custom hero sections, feature grids, and page compositions are NOT Shadcn components. Build them as page-level JSX with Tailwind.

### Interactive states — all 8 required

Every interactive element must handle all 8 states. Most are built into Shadcn; verify you are not overriding them:

| State | What it communicates | Implementation note |
|---|---|---|
| Default | Resting, available | Base styling |
| Hover | Clickable, interactive | `hover:` — gate behind `md:` for touch: `hover:md:bg-accent` |
| Focus | Keyboard-selected | `:focus-visible` ring — never remove |
| Active | Being pressed | `active:` — brief feedback |
| Disabled | Unavailable | `disabled:opacity-50 disabled:pointer-events-none` |
| Loading | Processing | Replace label with spinner or `<Skeleton>`. Disable re-submission |
| Error | Something failed | Red ring/border + message below |
| Success | Action completed | Brief confirmation, then return to default. Sonner toast for async |

### Forms

- Always use `<Label>` with `<Input>`. Placeholders are not labels.
- Validate on blur, not on every keystroke. Show errors immediately below the field.
- Group related fields: <=4 fields per visible group. Use progressive disclosure for longer forms.

### Destructive actions

- Prefer **undo** over confirmation: remove from UI immediately, show Sonner undo toast, actually delete after toast expires.
- When you must confirm (irreversible + high-stakes), use specific labels: "Delete project" / "Keep project", not "Yes" / "No".

### Loading states

- Use `<Skeleton>` for content shapes — match the shape of what will load. Not spinners in the middle of content.
- Sonner toast for async feedback ("Saving your draft...", not "Loading...").
- For long waits (>3s), set expectations with specific copy.

### Consistent vocabulary (Product)

Same button variant for the same action type across all screens:
- `default` — primary actions
- `secondary` — supporting actions
- `destructive` — danger/delete
- `outline` — neutral/cancel
- `ghost` — de-emphasized/tertiary

---

## 6. Motion

### Implementation: `tailwindcss-animate` + custom

The template includes `tailwindcss-animate`. Use its classes for standard animations:
- `animate-in`, `fade-in`, `slide-in-from-bottom-4` — entrance
- `animate-out`, `fade-out`, `slide-out-to-top-4` — exit
- `duration-200`, `duration-300`, `duration-500` — timing

For custom animations, add keyframes in `tailwind.config.ts` `theme.extend.keyframes`.

### Easing curves

Never use the generic `ease` or `linear`. Use purpose-specific curves:

| Curve | CSS | Use for |
|---|---|---|
| ease-out-quart | `cubic-bezier(0.25, 1, 0.5, 1)` | Entrances, default choice |
| ease-out-expo | `cubic-bezier(0.16, 1, 0.3, 1)` | Confident, decisive entrances |
| ease-in | `cubic-bezier(0.4, 0, 1, 1)` | Exits only |

**Banned**: bounce and elastic easing feel dated.

### Duration rules

| Purpose | Duration | Example |
|---|---|---|
| Micro-feedback | 100-150ms | Button press, checkbox toggle |
| State changes | 200-300ms | Hover effects, tab switch |
| Layout transitions | 300-500ms | Accordion, sheet open |
| Page entrances | 500-800ms | Brand hero reveal |

Exit animations: ~75% of entrance duration.

### Stagger rules

- Total stagger <=500ms. 10 items at 50ms max.
- Animation fatigue is real. Do not animate everything.

### Brand motion

- Orchestrated page-load with stagger is permitted when the brand invites it.
- Scroll-driven animation (`animation-timeline: scroll()`) is available in modern browsers.
- Not every brand needs motion. Restraint can be the voice.

### Product motion

- 150-250ms for most transitions. Users are in flow.
- Motion conveys state only: change, feedback, loading, reveal. Nothing else.
- No orchestrated page-load sequences. No decorative motion.

---

## 7. Imagery

### Brand

A restaurant, hotel, or photography site without imagery is a bug, not restraint.

- For work without local assets, use Unsplash via `<img>`. Search for the brand's physical object: "handmade pasta on a scratched wooden table" beats "Italian food."
- One decisive photo beats five mediocre ones.
- Alt text is part of the voice: "coastal fettuccine, hand-cut, served on the terrace" beats "pasta dish."
- Use Tailwind's `aspect-ratio` plugin (`aspect-video`, `aspect-square`) and `object-cover` for consistent image treatment.

### Product

- Use `<Skeleton>` for loading states — match the shape of what will load.
- Empty states teach the interface: acknowledge, explain value, provide action. Not "No items."
- Data visualization: limit to 5-7 colors maximum. Use the brand palette, not arbitrary chart defaults. Label directly when possible instead of relying on color legends.

---

## 8. Copy and UX writing

- Every word earns its place. No restated headings. Say it once, say it well.
- **Button labels**: never "OK", "Submit", or "Yes/No". Use verb + object: "Save changes", "Create account", "Delete 5 items".
- **Error messages**: (1) What happened? (2) Why? (3) How to fix it? Never blame the user.
- **Empty states**: (1) acknowledge the emptiness, (2) explain the value, (3) clear action to get started.
- **Loading copy**: "Saving your draft..." not "Loading...". For long waits (>3s), set expectations.
- **Terminology**: pick one term and stick. Delete/Remove/Trash -> one. Settings/Preferences -> one.
- **AI slop loading messages are banned**: "Herding pixels", "Teaching robots to dance", "Consulting the magic 8-ball." Write messages specific to what the product actually does.
- **Link text**: standalone meaning. "Read the migration guide" not "Click here."

---

## 9. Cognitive load

Humans hold <=4 items in working memory.

**Practical limits**: nav <=5 top-level items, form sections <=4 fields per group, action buttons 1 primary + 1-2 secondary, dashboard <=4 key metrics visible, pricing <=3 tiers.

**7 constraints** (violating 2+ means the view is overloaded):

1. **Chunking**: <=4 items per visible group
2. **Grouping**: related items use proximity, borders, or shared backgrounds
3. **Visual hierarchy**: squint test passes — primary, secondary, and groupings identifiable
4. **One thing at a time**: multi-step flows show one step per screen
5. **Minimal choices**: <=4 visible options; more behind progressive disclosure
6. **No cross-screen memory**: user should never need to remember info from a previous screen
7. **Progressive disclosure**: secondary content hidden behind clear entry points

**Common violations**: wall of options (fix: group + highlight recommended), visual noise floor (fix: one primary, 2-3 secondary, rest muted), context switching (fix: co-locate info), inconsistent patterns (fix: standardize).

---

## 10. Responsive design

- **Mobile-first**: base styles for mobile, `min-width` queries to layer complexity. This is Tailwind's default model (`sm:`, `md:`, `lg:` are min-width).
- Start narrow, stretch until it breaks, add breakpoint. Three breakpoints usually suffice.
- **Detect input method, not just screen size**: `@media (pointer: fine)` for mouse, `(pointer: coarse)` for touch. Gate hover states: `hover:md:bg-accent`.
- Navigation: `Sheet` + hamburger on mobile -> horizontal on tablet -> full sidebar on desktop.
- Tables: stack to cards on mobile or use Shadcn `Table` with horizontal scroll.

## 11. UI Search - Design Template Search Engine

### How to Use

#### Step 1: Analyze User Requirements

Extract from user request:
- **Product type**: SaaS, e-commerce, portfolio, fintech, healthcare, etc.
- **Style keywords**: minimal, dark mode, glassmorphism, playful, etc.
- **Industry**: tech, beauty, fitness, education, etc.

#### Step 2: Generate Design System (Recommended for New Projects)

**Start with `--design-system`** for comprehensive recommendations:

```bash
python3 scripts/search.py "<product_type> <industry> <keywords>" --design-system [-p "Project Name"]
```

This command:
1. Searches multiple domains in parallel (product, style, color, landing, typography, brand)
2. Applies reasoning rules to select best matches
3. Returns complete design system: pattern, style, colors, typography, effects
4. Includes anti-patterns to avoid
5. Includes **Reference Brands** — up to 2 real-world brand design systems that match the query, with primary color, font, and path to detailed `DESIGN.md`

**Example:**
```bash
python3 scripts/search.py "beauty spa wellness service" --design-system -p "Serenity Spa"
```

#### Step 2b: Persist Design System (Master + Overrides Pattern)

Save for hierarchical retrieval across sessions with `--persist`:

```bash
python3 scripts/search.py "<query>" --design-system --persist -p "Project Name"
```

Creates:
- `design-system/MASTER.md` — Global Source of Truth
- `design-system/pages/` — Folder for page-specific overrides

**With page-specific override:**
```bash
python3 scripts/search.py "<query>" --design-system --persist -p "Project Name" --page "dashboard"
```

**Hierarchical retrieval:**
1. When building a page, check `design-system/pages/[page].md` first
2. If exists, its rules override the Master
3. Otherwise, use `design-system/MASTER.md` exclusively

#### Step 3: Domain Search (Detailed Lookup)

```bash
python3 scripts/search.py "<keyword>" --domain <domain> [-n <max_results>]
```

| Need | Domain | Example |
|------|--------|---------|
| Product type patterns | `product` | `--domain product "entertainment social"` |
| UI style options | `style` | `--domain style "glassmorphism dark"` |
| Color palettes | `color` | `--domain color "fintech purple"` |
| Font pairings | `typography` | `--domain typography "playful modern"` |
| Individual Google Fonts | `google-fonts` | `--domain google-fonts "sans serif variable"` |
| Chart types | `chart` | `--domain chart "real-time dashboard"` |
| UX best practices | `ux` | `--domain ux "animation accessibility"` |
| Landing page patterns | `landing` | `--domain landing "hero social-proof"` |
| Icon recommendations | `icons` | `--domain icons "navigation outline"` |
| React performance | `react` | `--domain react "rerender memo list"` |
| App interface guidelines | `web` | `--domain web "accessibilityLabel touch"` |
| Brand design reference | `brand` | `--domain brand "stripe fintech"` |

#### Step 4: Stack Guidelines

```bash
python3 scripts/search.py "<keyword>" --stack react-native
```

#### Step 5: Brand Design System Lookup

When a user says "design like Stripe", "Airbnb style", or mentions any brand name:

```bash
# Explicit brand search
python3 scripts/search.py "stripe" --domain brand

# Auto-detection also works (no --domain needed)
python3 scripts/search.py "design like stripe"
python3 scripts/search.py "inspired by airbnb"
python3 scripts/search.py "notion style dashboard"
```

**Auto-detection:** The engine recognizes 58 brand names and phrases like "design like", "inspired by", "look like", "brand style" — it automatically routes to the brand domain without `--domain brand`.

**Detailed DESIGN.md:** Each brand has a comprehensive design spec at `data/design-md/<brand>/DESIGN.md`. When Claude finds a brand match, it should read the corresponding DESIGN.md for complete specs.

**Available brands (58):** Stripe, Airbnb, Linear, Notion, Vercel, Tesla, Apple, Figma, Spotify, Uber and 48 more. Full list auto-detected by search engine.

### Available Domains

| Domain | Records | Use For | Example Keywords |
|--------|---------|---------|------------------|
| `product` | 161 | Product type recommendations | SaaS, e-commerce, portfolio, healthcare |
| `style` | 50+ | UI styles, effects | glassmorphism, minimalism, dark mode |
| `color` | 161 | Color palettes by product type | saas, fintech, beauty, gaming |
| `typography` | 57 | Font pairings | elegant, playful, professional |
| `google-fonts` | 1500+ | Individual Google Fonts | sans serif, monospace, variable |
| `landing` | — | Page patterns, CTA strategies | hero, social-proof, pricing |
| `chart` | 25 | Chart types, libraries | trend, comparison, funnel |
| `ux` | 99 | Best practices, anti-patterns | animation, accessibility, loading |
| `icons` | — | Icon recommendations | navigation, action, status |
| `react` | — | React/Next.js performance | waterfall, bundle, suspense |
| `web` | — | App interface (iOS/Android/RN) | touch targets, safe areas |
| `brand` | 58 | Brand design systems (colors, fonts, spacing, dos/don'ts, DESIGN.md) | stripe, airbnb, linear, notion, vercel, tesla |

### Available Stacks

| Stack | Focus |
|-------|-------|
| `react-native` | Components, Navigation, Lists |

### Output Formats

```bash
# ASCII box (default)
python3 scripts/search.py "fintech crypto" --design-system

# Markdown
python3 scripts/search.py "fintech crypto" --design-system -f markdown
```

### Tips for Better Results

#### Query Strategy

- Use **multi-dimensional keywords** — combine product + industry + tone: `"entertainment social vibrant"` not just `"app"`
- Try different keywords: `"playful neon"` → `"vibrant dark"` → `"content-first minimal"`
- Use `--design-system` first for full recommendations, then `--domain` to deep-dive
- Auto-detection works when `--domain` is omitted (e.g., `"design like stripe"` auto-detects brand)

#### Example Workflow

**User request:** "Build a fintech payment app"

```bash
# Step 1: Generate design system
python3 /home/longert/run_rollout/MetaGPT/mgx_rollout_server/workspace/.atoms/skills/frontend-design/scripts/search.py "fintech payment modern" --design-system -p "PayFlow"

# Step 2: Deep-dive style options
python3 /home/longert/run_rollout/MetaGPT/mgx_rollout_server/workspace/.atoms/skills/frontend-design/scripts/search.py "minimalism fintech" --domain style

# Step 3: Brand reference
python3 /home/longert/run_rollout/MetaGPT/mgx_rollout_server/workspace/.atoms/skills/frontend-design/scripts/search.py "stripe" --domain brand

# Step 4: Stack guidelines
python3 /home/longert/run_rollout/MetaGPT/mgx_rollout_server/workspace/.atoms/skills/frontend-design/scripts/search.py "list performance" --stack react-native
