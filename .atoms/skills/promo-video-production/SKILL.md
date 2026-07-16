---
name: promo-video-production
description: Read when creating a complete edited video — promo, product/demo, explainer, topic, social/Reels/TikTok, 探店/local business, e-commerce/packshot/360, DTC/before-after ad, or any 20s+ multi-shot/storyboarded piece — for the current project or a user-supplied subject. Also use whenever the video pairs with narration/voiceover or a separate audio track, or must be timed to a measured audio length (even one image-to-video clip plus one voiceover line), since only the Remotion timeline keeps the audio from being cut off.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the user asks for a promotional video, product video, demo video, marketing video, launch video, explainer video, brand video, designed video, multi-shot video, storyboarded video, social/Reels/TikTok discovery video, local business video, restaurant/food vlog style video, product ad, e-commerce / Amazon-style product video, packshot or 360 product-spin video, storefront / 探店 video, DTC / direct-response / before-after conversion ad, 20s+ edited video, or any complete video that introduces a subject visually.

Prefer this Remotion workflow whenever the request describes a complete edited video with timeline, shots, captions, audio, camera language, visual style, consistency requirements, CTA/end card, or multiple scenes — even if the user never says "promo" or "promotional". Use direct AI video generation only for a single short source clip or background loop, not as the final delivery path for a complete multi-shot video.

The video subject can be either:

1. **Project promo** — a project, app, or feature that the agent itself is building or that already exists in the workspace, or another existing app already identified in the user request or prior confirmed context. First resolve the **source app** being promoted. `app/promo` is the output video project, not automatically the source app.
2. **Topic promo** — a user-supplied topic, concept, brand, or external subject that does not require a workspace project. Examples: "the Solar System", "Song dynasty history", "what is a vector database".

Both paths share the same Remotion template, the same composition presets, and the same render commands. Only the storyboard authoring differs.

## Command

Use `RemotionPromoRenderer.render` for final promo export after validation. This command is documented by this skill and may be called even if it is not listed in `<Available Commands>`.

**`width`/`height`/`source_orientation` MUST come from the storyboard's Export Spec, not from this example.** The example below shows landscape values as placeholders; if the storyboard is portrait, pass `width=1080 height=1920 source_orientation=portrait` (and square → `1080`/`1080`/`square`). The output filename is `promo-<width>x<height>.mp4`, so a portrait render that wrongly used `1920x1080` is a sign you copied the example instead of reading the storyboard.

```xml
<RemotionPromoRenderer.render>
<promo_dir>/absolute/path/to/app/promo</promo_dir>
<width>WIDTH_FROM_STORYBOARD</width>
<height>HEIGHT_FROM_STORYBOARD</height>
<source_orientation>ORIENTATION_FROM_STORYBOARD</source_orientation>
</RemotionPromoRenderer.render>
```

## Subject classification

Before doing anything else, classify the subject from the original user request. Do not ask the user to clarify if the request already names a topic or project.

- If the user message names a clear external topic / concept (e.g. "做一个介绍太阳系的宣传视频") and the workspace has no `app/frontend` or no application code to promote → **topic promo**.
- If the user message references an existing `app/frontend` build, an in-progress app the agent has been generating, or an upcoming feature → **project promo**.
- If the subject is a physical product, a retail/local business or place, or a direct-response offer with no rebuildable app UI as its primary subject (e.g. a car-diffuser ad, a jewelry 360 spin, a ramen-shop 探店, a pet-hair-remover DTC ad) → **commerce promo**.
- If both apply (e.g. "make a promo for our solar-system explainer app") → treat the app as primary and use the topic as supporting subject; this is a project promo.

Use these tie-breakers when more than one could fit: a rebuildable software UI is the subject → project promo; a physical product / physical place / offer with no rebuildable UI → commerce promo; an external concept or knowledge with no product → topic promo. A mixed case (e.g. a DTC software product whose ad also shows a real checkout screen) is classified by what the hero shots sell, and may borrow the other class's rules per-shot (e.g. one `ui-demo` checkout beat inside a commerce promo).

Topic promos and commerce promos are first-class. Do not reject or stall on a topic promo just because there is no `app/frontend` in the workspace, and do not downgrade a commerce promo to a topic promo just because the product has no `app/frontend` to rebuild.

## Compliance baseline

Promo videos must default to conservative ad-safety rules. Use only claims, offers, prices, discounts, gifts, brand names, CTAs, certifications, sales numbers, effects, and services that are present in the user's request, project, ad copy, or landing page. Do not imply official partnerships, platform recommendations, brand endorsements, or certifications unless the source material explicitly provides them.

Do not use misleading or unverifiable claims such as guaranteed results, absolute rankings, risk-free promises, fake scarcity, fake countdowns, fake notifications, fake buttons, fake system UI, fake testimonials, fake reviews, fake news, or exaggerated result screenshots. Do not directly target sensitive personal attributes such as health, finances, age, race, religion, sexuality, disability, marital status, body shape, or appearance; use neutral audience wording instead.

Do not include unlicensed brand marks, recognizable people, copyrighted characters, third-party product UI, media, fonts, watermarks, adult content, gore, shock, hate, harassment, humiliating content, weapons, drugs, gambling, tobacco, or political-sensitive material. For high-risk categories such as medical, supplements, weight loss, cosmetic procedures, finance, loans, crypto, gambling, alcohol, dating, children, legal, recruiting, real estate, politics, religion, or social issues, keep the video informational and avoid strong promises, dramatic before/after visuals, or aggressive conversion pressure.

Keep footage clear, stable, and high quality: no flicker, severe compression, stretching, watermark, black bars caused by bad asset sizing, or edge-cropped subtitles/logos/CTAs. If compliance is uncertain, choose the safer, more neutral, information-first expression. This baseline reduces risk but is not a platform approval guarantee.

Final conversion CTAs are static video content, not interactive web UI. Do not render the closing CTA as a clickable-looking website button, fake click target, arrow button, fake input, fake popup, fake system UI, cursor target, hover/pressed state, or any control that implies the viewer can click to navigate. Use an end-card line, brand tagline, account handle, URL, QR placeholder, or plain "visit / scan / follow" text instead. Product demos and page walkthroughs may show real or simulated UI buttons, forms, and navigation when they demonstrate the product flow, but they must not become the final conversion CTA.

Any visible URL, account handle, QR target, browser address-bar text, or brand endpoint must come from the user's request, confirmed project source, landing page, or another verified asset. If the project only exposes a placeholder domain or no confirmed public address, omit the URL and end with brand copy instead; for a browser-window treatment, use a non-URL page label or leave the address bar blank. Do not infer a domain, handle, or destination from the app name, repo name, download filename, template placeholder, env var token, or similar hints.

## Core workflow

1. Initialize the Remotion project with `FrontendEngineer.use_template("remotion")` if `app/promo` is not already ready. The tool itself rejects a non-Remotion source before copying, so you do not need a separate verify step.
2. Pick the target orientation up front from the user request and storyboard plan: landscape (16:9), portrait (9:16), or square (1:1). All later validation, smoke, and full-render commands must use the matching variant.
3. Classify the subject (project promo vs. topic promo) using *Subject classification* above. Do not stop to ask "what should this be about?" if the original request already names a topic or project.
4. Ground the subject:
   - **Project promo**: first resolve the source app being promoted, then read that app's `app/frontend` source, manifests, and prior validation feedback. If the current workspace mainly contains the promo output, do not treat `app/promo` itself as the source app. Once you identify the source app, lock that source project root / frontend path in `promo_storyboard.md` or working notes and keep reusing the same path after switching into `app/promo`; do not downgrade to topic promo just because the promo workspace itself has no `app/frontend`. Before writing Remotion code, record the key source frontend file paths you will rely on in `promo_storyboard.md` (pages/routes/components for the demo beats). Later, when implementing `src/`, reopen those source files and copy/recreate from the code instead of relying on a long prose summary.
   - **Topic promo**: extract the subject from the user message and prior conversation; pull additional facts from your own knowledge or external tools (image / video / audio generation, search if available). Do not require a workspace project to exist.
   - If the user provided reference images but the current request only exposes file paths instead of attached image content, read `image-understanding` and call `ImageAnalyzer.analyze_images` before storyboarding so the visual plan is grounded in the actual image content rather than filenames.
   - If the user provided a website URL as the promo subject, use `Browser.goto` to visit the page, then `Browser.take_screenshot` to capture the visual, then call `ImageAnalyzer.analyze_images` on the screenshot before storyboarding so the visual plan is grounded in the actual page content rather than the URL alone.
5. Apply the *Compliance baseline*: confirm which facts, claims, offers, and assets are actually supported by the request, product, ad copy, or landing page. Do not invent unsupported offers, certifications, sales numbers, effects, official partnerships, platform endorsements, or brand backing; when uncertain, choose conservative information-first wording and visuals.
6. Determine the default language for newly generated promo content before writing `promo_storyboard.md`. If the user explicitly specifies an output language, use that language. Otherwise, default to English. A user message written in Chinese/Japanese/etc., the surrounding chat language, or the system prompt language is not an explicit language request. Record the decision directly in the storyboard as `Language: English (default)` or `Language: Chinese (user specified)` before drafting shots, copy, narration, or generation prompts.
7. Create `promo_storyboard.md` before writing video code or generating assets. Use the field set that matches the subject type (see *Storyboard requirements*). For promo/remotion runs, `promo_storyboard.md` is the only planning artifact; do not create or maintain a separate `todo.md`.
8. If the user requests narration, voice-over, spoken walkthrough, or the storyboard clearly needs a narrator, include a short-segment narration plan in the storyboard, check each segment's script length against its target shot seconds, then read `audio-generation` and call `AudioCreator.generate_audios` with one request per shot/beat.
9. After TTS generation, prefer each audio segment's returned `duration`. If `duration` is missing or `null`, measure the real duration from the returned URL (for example with `ffprobe`), then decide the final per-shot timing from those measured durations. This calculation is not enough if it only appears in thought or terminal output.
10. Immediately update `promo_storyboard.md` with each narration URL, measured audio seconds, final shot start/end/duration, total duration, and any script/timing changes. This is a hard checkpoint: do not call `MusicCreator.generate_music`, `VideoCreator.generate_videos`, generate more visual assets, or write `src/timeline.ts` until the updated timing is persisted in `promo_storyboard.md`.
   After this lock, `promo_storyboard.md` must no longer keep placeholder `TBD` timing rows or an outdated total duration.
11. By default, promo videos should also include one global background-music plan unless the user explicitly says no music or the piece is clearly better without music. Read `music-generation` and call `MusicCreator.generate_music` with exactly one instrumental / no-vocals request after the final shot timing is locked. The prompt must include the target total seconds, mood, pacing, instrumentation, and whether the track should leave room for narration.
12. After music generation, use the returned URL directly and prefer the returned `duration`, just like narration. If `duration` is missing or `null`, measure the real BGM duration with `ffprobe`. Immediately update `promo_storyboard.md` with the BGM URL, measured seconds, target total duration, fit strategy, and planned mix values before writing `src/timeline.ts` or `src/PromoVideo.tsx`.
   The locked storyboard/timeline duration is the source of truth. Never shorten the video just to match a short BGM; trim, minimally loop, or regenerate the music instead unless the user explicitly asked for a shorter cut.
13. Generate any other needed AI image/video/audio assets after the storyboard is written and the narration + BGM timing is settled in `promo_storyboard.md`.
14. Read `remotion-best-practices` and focus on the sections relevant to the storyboard.
15. Edit the Remotion implementation **in place** under `app/promo` — keep the template's flat `src/` layout (`src/Root.tsx`, `src/PromoVideo.tsx`, `src/timeline.ts`, `src/components/`, `src/scenes/`, `src/app-demo/`). Do not move sources into a subdirectory like `src/remotion/`. Before validation, do one quick self-check: remove unused imports/vars, omit redundant `Sequence from={0}`, keep motion purely frame-driven (no CSS `animation` / `transition`, timers, or other non-deterministic patterns), and update any changed `src/timeline.ts` / `src/PromoVideo.tsx` / `src/scenes/*` contract in the same pass.
16. Run validation in order: `verify:versions`, `lint`, `verify:compositions`. Passing `verify:compositions` only proves Remotion can see the compositions; it is not a deliverable and is not a valid stopping point.
17. Run `RemotionPromoRenderer.render` for the target resolution recorded in the storyboard/export spec; it performs smoke + full render internally. Pass `width`/`height`/`source_orientation` straight from the storyboard Export Spec — for portrait/9:16 use `width=1080`, `height=1920`, `source_orientation=portrait`; do not copy the landscape-looking placeholders in the examples above. The task is **only done** when `out/promo-<width>x<height>.mp4` exists and is non-empty, AND that filename's dimensions match the storyboard orientation (a portrait storyboard must produce `promo-1080x1920.mp4`, never `promo-1920x1080.mp4`). Do not tell the user the video is ready to export, ask them to export it, call `RoleZero.reply_to_human`, or use `<end></end>` before this tool succeeds.

## Storyboard requirements

`promo_storyboard.md` must be specific to the subject. Pick the field set that matches the subject type:

### Brief expansion checklist (auto-fill short requests)

Most requests arrive as one line ("a car-diffuser ad", "拉面店探店"). Before writing shots, expand the brief by resolving these seven dimensions, inferring conservative, subject-appropriate defaults for whatever the user left out. Record the resolved choices in the field sets below — these are a reasoning pass that fills the existing fields, not seven new per-shot columns. Do not invent claims, offers, prices, or facts the request/product does not support (see *Compliance baseline*).

1. **Goal** — conversion / showcase / tutorial / brand / store-visit (探店). Drives the story shape and the CTA.
2. **Spec** — duration, aspect ratio, target platform, and whether narration/subtitles are needed. Default to 60s landscape. Platform overrides this: TikTok / Reels / Shorts / 抖音 / 快手 default to portrait 9:16 and a shorter 20-30s length unless the user gives an explicit duration. An explicit user orientation (e.g. 竖屏 / portrait / vertical) or duration always overrides these defaults.
3. **Timeline** — break the runtime into labeled beats (e.g. `0-3s` hook, `3-8s` …) before assigning shots.
4. **Key frames** — the must-appear visuals (the product, storefront, or result that cannot be missing).
5. **Camera language** — per beat: handheld POV, 360 product spin, before/after split-screen, slow push, etc.
6. **Visual style** — the reference register (Amazon product photography / TikTok 探店 / cinematic brand film …); pick the palette per *Visual motion baseline*.
7. **Consistency constraints** — what must stay identical across shots: product color & form, subject/character appearance, scene style. Note the lock method (a `Consistency anchor` reference reused across images and clips — see *AI visual strategy*).

Put the resolved Goal, Spec, and scene-type label near the **top** of `promo_storyboard.md`: the downstream asset prompt optimizer reads only the first ~600 characters of the storyboard as context, so the scene type must appear early to reach it. Expand from the request and proceed with conservative defaults; do not stall to ask the user to fill these in.

Every storyboard must include:

- Compliance notes: supported claims/offers/assets, whether the subject is high-risk, the conservative wording choices, and visual/copy/asset risks to avoid.
- CTA treatment: record whether the final CTA is static video copy, a URL/account/QR/end-card, or only appears inside a product demo (final CTA rules: *Compliance baseline*).
- Language: record the default language for newly generated promo content in the exact format `Language: English (default)` or `Language: Chinese (user specified)`. Unless the user explicitly requests another output language, use English; chat/user message/system prompt language is not an explicit language request. This field governs newly written shot copy, narration scripts, subtitles, end-card / CTA text, and image / video / BGM generation prompts. Do not force-translate existing source-app UI copy or user-provided brand names, URLs, handles, or other supplied asset text.
- Audio treatment: record whether narration is present, whether the default global BGM is included, the BGM prompt summary, returned URL, measured seconds from the tool-returned `duration` or fallback `ffprobe`, target total duration, fit strategy (`trim`, `retry`, or minimal `loop` fallback), plus the planned `baseVolume`, `duckVolume`, `fadeInFrames`, and `fadeOutFrames`. Promo audio comes only from narration + one global BGM: AI video source clips must be muted (the model may bake in its own audio that would otherwise stack on the BGM) — generate them with `audio=false` and render each `<OffthreadVideo>` with `muted` (see `remotion-best-practices` — *Promo audio architecture*).
- Shot asset type: for each shot, explicitly choose `video source clip`, `image + Remotion motion`, or `static/end-card`. If a shot depends on realistic camera or object movement but does not use a `video source clip`, record the concrete reason in the storyboard.
- Story shape: unless the subject clearly needs another structure, default to a subject-led opener/hook for shot 1, an overview beat for shot 2, and 3-5 detail beats after that. The overview beat should establish the whole subject before later shots zoom into modules, states, features, or subtopics; do not jump from an abstract opener into a loose stack of floating feature cards. For topic promos, the overview beat can be a map, taxonomy board, chapter layout, labeled system view, or other structural overview rather than a literal webpage.
- Motion language: for each shot, record the main background source, the main foreground showcase element, and the concrete motion recipe instead of a vague "visual + motion" note (the anti-slide-deck baseline and per-scene motion requirements are in *Visual motion baseline*). For shots that show networks, flows, checkpoints, org charts, state transitions, or other node-to-node relationships, default to an Organic Editorial connector language: prefer arcs, Bezier curves, soft S-curves, rounded-corner routes, slightly asymmetric spacing, and draw-on or highlight-travel motion instead of bare straight connector lines. When connector behavior matters, the motion recipe must say how the path behaves (for example `curved paths draw in`, `highlight travels along rounded routes`, or `checkpoint flow follows an arc`), not just `lines appear` or `nodes connect`.
- Foreground scale / framing: for each shot, record whether the main foreground showcase element is the dominant foreground subject or only background atmosphere, whether the frame needs a clean copy area, and what contrast protection keeps labels/captions/metrics readable when they sit over the art (`scrim`, `ribbon`, `pill`, `card`, `stroke`, `shadow`, or a higher-contrast text color). The element marked as the main foreground showcase must stay the shot's most inspectable subject, large enough to inspect — not a smaller duplicate layered over a larger same-role background image. If the shot sells a system map, node network, pipeline, org chart, bar chart, or state machine, the whole foreground structure must stay the dominant readable subject, not a few small nodes/cards floating over a larger background motif.
- Shot list columns: every shot row uses these standard columns — time range, visual, main background source, main foreground showcase element, `foreground scale / framing`, copy, motion recipe, required assets, shot asset type. Each field set below adds only its type-specific columns on top of these.
- Narration plan (when voice-over is needed): language, tone, voice gender, per-shot/beat script text, target seconds, generated audio URL, measured audio seconds after TTS, and final locked shot start/end/duration after timing adjustment. The narration `language` should default to the storyboard `Language` field; only deviate when the user explicitly asks for mixed-language output.
- Export spec: default is a 60-second landscape video; choose portrait or square only when the user or platform target requires it. (Short-form / commerce platform overrides are in the *Brief expansion checklist* Spec rule.)

### Project promo

- Project positioning: one clear sentence describing what the project is.
- Audience and usage context.
- User pain points, project value, key capabilities, and differentiators.
- Video style: pace, visual language, motion direction, colors, typography, and tone. Default to the source app's real palette, brand accents, and UI material cues (or a neutral / warm editorial palette around them) per *Visual motion baseline*.
- Shot list: standard columns plus `product/page demo?` and `shot_type` (`ui-demo` or `abstract`). For every `ui-demo` shot, also record the source route/page, source files, viewport focus, and implementation mode (`import`, `recreate-in-remotion`, or `abstract-fallback`). By default, shot 2 should be a recognizable whole-page / app-shell / browser-window / dashboard overview that shows the overall product surface before later shots crop, zoom, or isolate specific modules, states, and result areas. If the shot comes from a real page, `viewport focus` must describe a crop/highlight inside the real page frame, and the main background/base layer must stay that real page viewport unless the actual product surface is not page-based. Do not label an AI-generated image or abstract tech plate as the main background source of a real-page `ui-demo` shot; if you need atmosphere, record it separately as a supporting layer behind the page. For page-based `ui-demo` shots, whole-page does not mean full-screen: the default presentation is an inset browser/app window with rounded edges, subtle chrome, shadow/glow, and an atmospheric outer background unless the storyboard truly needs a full-bleed crop. Treat that inset window as the dominant subject, not a decorative corner card, and keep copy in compact support placements unless the storyboard explicitly needs a split-layout comparison.
- Source app lock: source project root, source frontend path, why it is the promoted app, and the exact path you will keep reusing after switching into `app/promo`.
- Source frontend file anchors: the key pages/components/layout files that later `src/` recreation must reopen and copy from.
- Page or product demo plan: identify the source app being promoted, then list which actual routes/screens/states/viewport slices the video will show, which real components can be reused, and which shots genuinely need non-UI or abstract Remotion visuals. For each product-demo shot, record the source screen/route and source files.
- AI creative asset plan: which shots use AI-generated images or video to express atmosphere, metaphors, transitions, or product value, especially which non-video shots should use AI-generated images as the main background or transition plate. Draft those prompts with a subject-grounded palette per *AI visual strategy*.

### Topic promo

- Topic positioning: one clear sentence describing the subject (e.g. "A 60-second introduction to the Solar System for a general audience").
- Audience and viewing context (web, social feed, classroom, kids, etc.).
- Hook: what makes this topic worth watching for the audience.
- Key facts / structural beats: 4–8 sub-points, each with a short visual idea (e.g. "scene 3 — 太阳：体积占比 / 主要构成 / 光球/日冕").
- Video style: pace, visual language, motion direction, colors, typography, and tone. Pick colors from the subject itself, the intended audience context, or an editorial palette that supports clarity, per *Visual motion baseline*.
- Shot list: standard columns; shot 2 is the topic overview beat per *Story shape* above.
- AI creative asset plan: which shots use generated images or short video clips to externalize the topic (concept art, scene posters, atmosphere, transitions), especially where AI-generated images should carry the main full-frame background. Topic promos typically lean more heavily on AI-generated visuals than project promos because there is no product UI to reuse; still specify subject-grounded palette/material choices per *AI visual strategy*.

### Commerce promo

A commerce promo sells a physical product, a retail/local business, or a direct-response offer. It reuses the shared "Every storyboard must include" block above; add these commerce-specific fields. For the per-scenario beat structure, follow *Commerce scenario playbooks*; for motion mechanics follow *Visual motion baseline*; for asset choice follow *AI visual strategy*.

- Product/offer positioning: one sentence — what is sold, to whom, and the single hero benefit.
- Supported claims/assets lock: list the real claims, prices, and offers and the source of each (see *Compliance baseline*). Commerce is the highest ad-safety-risk class — keep claims and before/after honest and conservative.
- Consistency anchor: one canonical product/subject reference (user-uploaded, or a generated hero packshot) that every later image and clip must match. Reuse it both ways — as the `image` reference for product images and as the video clips' `reference_images` (see *AI visual strategy*).
- Scenario archetype: name which playbook applies — single product showcase & ad, local business & offline, or DTC direct-response — and pull that playbook's enhancement checklist.
- Shot list: standard columns plus a `commerce_beat` label (`hook` / `detail` / `demo` / `proof` / `cta`).
- CTA treatment: state the conversion CTA (store visit / buy / scan) explicitly — this class is the most likely to drift into a fake click target, so lock it to static video copy or an end-card line per *Compliance baseline*.

Do not use a fixed marketing structure such as title → pain → solution → features → CTA unless it genuinely fits the subject. Choose the story shape from the actual subject.

## Visual motion baseline

Default promos should feel like edited marketing videos, not presentations. In almost every scene, the primary visual should come from media, real UI, charts/diagrams, or generated artwork, not a bare solid color or bare gradient canvas. Solid colors and gradients may be used as support layers such as masks, glows, vignettes, or readability washes, but they should not be the only full-frame background. Treat the background as atmosphere and depth, not as the only thing the viewer is meant to inspect. Except for intentionally open hero shots, brief bridge beats, or simple end cards, each scene should usually include at least one clear foreground showcase element such as a product demo frame, result card, comparison crop, gallery tile, packshot, chart, diagram, or feature panel. Avoid a sequence of static full-screen cards, centered headlines, and simple fade-only transitions unless the user explicitly asks for a minimal deck style. The opener should not default to the same blue/purple AI-tech gradient look, HUD overlays, particle fields, or other generic cyber-AI motifs used across generic demo reels, and mid-video backgrounds should also avoid repeating that motif unless the real brand or subject specifically supports it; use blue/purple only as minor accents when the subject genuinely calls for it.

For still-image or UI-led scenes, fade-in/out or a static card crossfade can only be a supporting move, not the whole motion plan. Use at least one background motion layer such as a slow push, pan, zoom, or parallax drift, plus one supporting motion layer such as a mask reveal, light sweep/reflection, foreground drift, emphasis words, or path/counter/state change. The foreground showcase element should carry the message of the shot; the background should support it rather than replace it. Do not shrink the intended subject into a corner just to make room for extra copy or extra decorative elements. If the shot needs more text, reserve cleaner negative space, crop/push the background, or reframe the camera instead of reducing the subject until it loses visual priority. For topic-promo maps, pipelines, charts, and other abstract diagram beats, default the main foreground structure to the central major visual area rather than a small decorative overlay. For scenes longer than about 6 seconds, add internal beats with frame-driven changes such as camera push/pan, mask reveals, selected-state changes, counters, flowing paths, caption highlights, or foreground wipes so something meaningful changes every 1-2 seconds. When a scene's structure is communicated through connectors or routes, do not default to rigid point-to-point straight lines; prefer curved path growth, rounded route reveals, or highlight travel along a path unless the shot is intentionally showing rigid geometry such as axes, grids, tables, timelines, or a strict technical schematic. Use AI video clips or generated images with Remotion motion when they materially improve atmosphere or storytelling; for product-heavy shots, preserve readability and use subtle motion around the UI instead of covering it with decorative effects.
If a shot keeps extra padding after narration ends, that extra time must still contain meaningful motion or state change such as camera drift, highlight travel, scroll/pan, particles, glow pulse, light sweep, or another UI transition. Do not leave a frozen frame on screen for multiple seconds after the narrator stops speaking; shorten the shot instead when no useful motion remains.

## Product demo rules

These rules apply only to **project promos**. Topic promos rely on Remotion-native visuals plus AI-generated assets and skip this section.

Default to project-code-grounded product demos when the project has a frontend:

- Resolve the source app first (`app/promo` is the video output, not automatically the app being promoted); if the request or prior confirmed context points to another existing app/project, read that source app's frontend code before storyboarding, and keep reusing that exact source root / frontend path for later reads instead of rediscovering it from the promo workspace.
- Explore the relevant frontend pages first and write the key source file paths into `promo_storyboard.md` before writing Remotion code. Treat those file paths as anchors: when implementing `src/`, reopen the actual source files and copy/recreate from code, not from a long paraphrased note.
- Start from the real frontend routes, pages, and components. Identify which exact screen, section, or state the shot is selling before designing motion.
- When a shot is about product usage, feature flow, result output, dashboard state, or page UX, recreate that actual screen or viewport in Remotion using the project's real layout, labels, navigation, sample assets, and state changes. Do not default to a generic three-step card strip, fake SaaS dashboard, abstract flow panel, or unrelated placeholder UI when the project already has a concrete interface for that feature.
- Keep asset-role mapping semantically correct and continuous across the workflow. A person slot should show a person photo, an outfit slot should show garment/reference clothing, and a result slot should show the dressed output. Reuse source-app sample assets when available, or generated replacements that preserve the same role and visual continuity across beats; do not swap unrelated images into those slots just because they fit the palette.
- When a concrete source screen exists for the beat, generic upload cards, fake dashboards, and abstract flow panels are not acceptable default MVPs. MVP here means the simplest faithful recreation of the real source screen or viewport.
- For shots sourced from a real page, keep enough surrounding page context to prove it is the real screen: navbar/tab state, page heading, container grid, neighboring panel, or other page chrome. Do not cut one panel out of a multi-column page and place it on an empty background unless the actual product uses that isolated surface.
- For `ui-demo` shots, keep the real page or page crop visible as the base layer for most of the shot. Abstract AI/tech imagery may sit behind it as atmosphere or appear in brief transitions, but it must not replace the page and leave only a floating result/upload card.
- When page interaction is the message, make the browser/app window the primary visual weight. Do not default to a large side headline block plus a much smaller page window floating over atmosphere; use eyebrow/caption/callout copy as support and let the page carry the shot.
- Establish the whole app shell or page overview in shot 2 (per the Project promo shot-list rule) before later shots slice it into modules, flows, and result states; the viewer should understand the overall surface first.
- Preserve the real page's visual style, not just its information architecture. Reuse source colors, border opacities, radius, shadow treatment, spacing, button styles, nav structure, and typography scale from the code when feasible. Do not re-theme the page into a new glossy / futuristic / glassmorphism variant unless the source app already looks that way.
- If a single real page already contains multiple key beats, keep that page as the source for multiple consecutive shots and vary the camera framing, highlight state, or scroll position. Do not split one real page into several standalone floating marketing cards unless that card structure already exists in the product.
- `src/app-demo/AppDemoFrame.tsx` is a generic fallback adapter. Do not use it as storyboard inspiration or as the default product demo when the source app already has real screens to recreate.
- For long pages, treat the shot like a camera-framed viewport. It is fine if content below the fold is not visible in one frame. Do not shrink the entire page until the UI becomes unreadable just to show everything at once; pick the most relevant viewport per shot, then use another shot or a controlled scroll/pan if later sections matter.

- Reuse independently renderable pages, business components, and UI components.
- Put video-specific adapters under `src/app-demo/`.
- Use static fixtures and frame-driven state to simulate user flows.
- Do not call real backend APIs during Remotion render.
- Do not use Playwright screenshots or browser recording. Promo renders must be deterministic and frame-driven.

If the real components are too coupled to routing, auth, backend state, browser side effects, or a full app bootstrap, do not force the import. Recreate the actual product screen from project code in Remotion using the same information architecture, layout hierarchy, labels, sample assets, and local fixtures. Abstract cards, charts, or flow diagrams are a fallback only when the feature truly has no concrete UI surface to show. Record this choice in `promo_storyboard.md`.

If you cannot name the source screen/route or source files for a claimed product-demo shot, stop and read more code or explicitly mark the shot as an abstract fallback. Do not describe a shot as a real UI demo while keeping the source screen unspecified.

When multiple consecutive beats come from one real page workflow, keep the same page scaffold across those beats: if upload, submit, loading, success, and result all live on one source page, keep that page frame, surrounding layout, and neighboring panels visible while only the state changes — animate each upload inside its real drop zone, scroll to the real generate button if it sits lower on the page, then reveal loading and the final result inside the real result area, instead of decomposing the flow into standalone cards or replacing a later state with a centered button, spinner, toast, or result card on an abstract AI background. Keep the page inside an embedded browser/app window (not stretched edge-to-edge) and keep that same window shell across the beats while the camera crops/highlights move inside it, so the walkthrough feels like a cinematic product demo rather than a screen recording.
Bad: a result-showcase shot from one source page where the main background is an AI image and the recreated UI is only a floating result card. Good: keep the real page viewport as the background/base layer and emphasize the result area inside that page.

Before writing `src/timeline.ts` or `src/scenes/*`, reopen the recorded source files for every planned `ui-demo` shot and cross-check the implementation against the real page code. The implementation must preserve the page chrome/layout from those source files. If the code only renders a floating panel, spinner, or generic card while omitting the recorded page viewport, it is not a valid real-UI recreation.

Real UI, charts, or flow diagrams may be the main visual without AI image generation, but they still need layered motion and scene texture: do not drop them onto an empty solid/gradient background and call the shot done, and do not hide the promised feature/result inside a decorative full-frame background plate — keep the UI readable in the foreground while adding framing, highlights, reflections, moving accents, or contextual background treatment.

## Commerce scenario playbooks

These apply to commerce promos. Each lists the beats that must appear, the defaults to auto-fill when the brief is one line, and the consistency emphasis for that scenario. For motion mechanics follow *Visual motion baseline*; for asset choice and the AI-video-first default follow *AI visual strategy*; for ad-safety follow *Compliance baseline*.

### Single product showcase & ad (e.g. car diffuser, jewelry 360)

- Must appear: a hero product reveal, a 360 / orbit pass, 2-3 macro detail beats (material, texture, mechanism), a believable use/placement environment, and a closing end-card CTA.
- Auto-fill default when the brief is one line: hook on the product in context → 360 / orbit detail → 2-3 macro detail beats → benefit/result → end-card CTA.
- Consistency: generate one hero packshot first, then drive the spin and detail clips reference-guided from that packshot so the object does not morph between clips.
- Multi-item / multi-SKU sets (e.g. a 17-piece kitchen set): one AI video clip panning/orbiting across the real pieces with Remotion overlaying per-item labels — not label cards sliding over a static plate (see *AI visual strategy*).

### Local business & offline (e.g. ramen-shop 探店)

- Must appear: a storefront/façade establishing shot, an entry/approach move (door, walk-in), an interior environment scan, a signature product/dish close-up, and a visit CTA.
- Auto-fill default: exterior hook → walk-in POV → interior pan → signature dish macro → seating/atmosphere → visit CTA.
- Style default: handheld 探店 / vlog energy unless the brief asks for cinematic.
- Consistency: there is no single product, so anchor on the storefront sign and the signature dish — keep them identical across the exterior, interior, and close-up clips by reusing their reference images.
- The visit CTA (address / hours / handle) is static end-card text, never a fake map button or clickable target.

### DTC direct-response (e.g. pet-hair remover)

- Must appear: a pain-point hook (the problem on screen in the first beats), the product in dynamic use, a before/after contrast, result proof, and a purchase CTA.
- Auto-fill default: problem hook → product intro → in-use demo → before/after split → result close-up → buy CTA.
- Compliance: the before/after must be honest and non-exaggerated — this scenario is where over-promising is most tempting (see *Compliance baseline*).
- If the DTC product *is* an app, the in-use demo beat may be a `ui-demo` shot under *Product demo rules*.

## AI visual strategy

Consider 2-4 AI creative assets by default, but only when they serve the storyboard. If a shot would otherwise rely on a flat background or a static graphic card, strongly prefer generating an AI image instead of accepting the empty look. Do not let "AI-generated" automatically imply neon blue/purple cyber styling; choose palettes and scene materials from the subject, brand, environment, or intended editorial tone.

Use AI images for concept backgrounds, large-format atmosphere plates, product metaphors, brand visuals, scene posters, abstract capability visuals, and transition plates.

When an AI image must show a specific real product or subject that has a reference image (user-supplied or your own anchor packshot), generate it with image-to-image — pass the reference in `ImageCreator.generate_images`' `image` field and write the description as an edit instruction — instead of a text-only prompt that would reinvent the product. Reserve text-only image generation for backgrounds, atmosphere, and subjects with no reference. This mirrors the `reference_images` consistency mechanism on the video side.

Use AI videos for short atmosphere clips, dynamic backgrounds, product metaphors, data-flow moments, workflow transitions, and other brief motion scenes. Default to an AI video source clip for any beat that depends on real motion, lighting change, environment, or human/product action — including most commerce beats; if a beat would otherwise be a still image with a slow push, prefer a short AI video clip instead. Reserve `image + Remotion motion` only for these carve-outs — app/SaaS UI demos, charts/data, end-cards/CTA, consistency packshots, video unavailable, or intentionally static beats — and record the reason in the storyboard when a motion beat falls back. The carve-out list is exhaustive: "precise timing control", "showing several items quickly", or "easier to animate cards in Remotion" are not valid fallback reasons — a catalog / multi-item / 360 beat stays on AI video (one clip panning/orbiting across the real products, Remotion overlaying only labels and callouts) unless video generation is genuinely unavailable.

Budget and spec each AI video source clip before generating it — AI video is slower and costlier than images (a 15s clip can take around 10 minutes) and the same product/subject can drift across separately generated clips:

- Duration: source clips support `seconds` from `4` to `15`. Request the shortest length that still covers the scene window plus a ~1s tail for a clean `trimAfter`, and never shorter than the scene `duration` — a clip shorter than its scene makes `<OffthreadVideo>` freeze on its last frame or loop at render. A beat longer than 15s splits into multiple consecutive clips; a product / catalog / multi-item / 360 beat splits into several continuous pan/orbit clips rather than dropping to images-plus-motion (that fallback at this length is only for non-product atmosphere, abstract, or bridge beats).
- Density: aim for about one clip per major beat — roughly `4-8` clips for a 60s promo (about one clip per `8-12s`), and about one clip per `3-5s` for short-form (≤20s), never below the `4s` floor. When beats outnumber the budget, merge adjacent beats into one continuous clip or compress to the essential beats; a scene shorter than `4s` must be a Remotion still/recreation, not an AI video clip. Keep static information (specs, CTA, charts, UI) on Remotion stills instead of spending a clip on it.
- Resolution: generate each clip at the closest same-aspect option to the Composition (`1920x1080` / `1080x1920` / `1080x1080`); do not upscale a low-resolution clip or use a wrong-aspect clip that will letterbox or crop. The same sizing rule applies to `Img` backgrounds.
- On failure: if a source clip cannot be generated, fall back to generated images plus Remotion motion, not a frozen poster or a flat color card.

Keep a recurring product/subject consistent by reusing one canonical reference image across every clip (in `reference_images`) and image (image-to-image), recorded in the storyboard `Consistency anchor` field. Prefer this reference-guided anchor over a `first_frame` anchor — a first frame only pins the opening frame and the subject can still drift later in the clip. That `reference_images` binding produces a `Reference map:` prefix which the downstream prompt optimizer preserves verbatim, so it is safe with automatic prompt optimization. For a 360 / orbit / multi-angle clip, a single front reference cannot describe the back and sides; generate front/side/back anchor packshots and pass them together in `reference_images` (or prompt an explicit turntable rotation) so the product stays consistent through the full spin.

A Remotion source clip must be ONE continuous shot. The Remotion timeline owns all shot changes, cuts, and transitions, so each `VideoCreator.generate_videos` prompt for a source clip must explicitly state it is a single continuous shot — for example end the prompt with "single continuous shot, no cuts, no scene changes". This matters because the AI video model will otherwise add its own internal hard cuts on longer or information-dense prompts, which then collide with the timeline's own cuts. Keep each source clip to one subject/action/beat; if a beat needs multiple shots, split it into multiple timeline shots, each with its own single-shot source clip, rather than asking one generated clip to cover several shots.

If a shot does not use an AI video clip, strongly prefer AI-generated images as the main background or atmosphere layer unless a real product UI, chart, flow diagram, or user-provided asset is already the clear primary visual. Do not default to a bare solid or gradient background for these shots. If the generated image is only setting mood, still add a foreground showcase layer for the actual feature, result, or subject the shot is selling. When the layer role is `background atmosphere only`, keep it supportive: do not let it carry the main explanation through readable small text, small charts, small UI panels, or a larger same-role subject that visually overpowers the planned foreground layer.
Generated substitute assets must still match the UI slot they inhabit and the story beat they support. For example, if the UI has person / outfit / result columns, the inserted images must remain person / outfit / dressed-result across the sequence instead of changing roles from one beat to the next.

Before generating assets:

- Read `image-generation` before `ImageCreator.generate_images`.
- Read `video-generation` before `VideoCreator.generate_videos`.
- Read `audio-generation` before `AudioCreator.generate_audios`.

For promo assets, every `ImageCreator.generate_images` description and `VideoCreator.generate_videos` prompt must include or clearly reflect this safety clause: "Original generic visuals only; no unauthorized logos, trademarks, celebrity likenesses, copyrighted characters, third-party UI, watermarks, fake buttons/notifications/popups, adult/gore/hate/weapons/drugs/gambling/tobacco content, exaggerated medical/weight-loss/financial results, or misleading before-after effects; clear stable footage, no flicker, no black bars."

When writing those prompts, specify the intended orientation, layer role (`background atmosphere only` or `dominant foreground subject`), subject scale, clean copy area, palette, materials, lighting, and scene context from the actual subject. When the plate will sit under titles, labels, or metrics, keep a low-detail, low-contrast copy zone — do not place the brightest glow or busiest texture where that copy will sit. Do not use vague defaults such as "futuristic AI tech", "neon blue purple", "cyber HUD", or similar generic AI-demo phrasing unless the user or source material explicitly asks for that look.

For promo AI video clips, use `seedance-2.0` — set `model: "seedance-2.0"` explicitly unless the user requested another model or the tool/config clearly cannot use it. It is one unified model: pass no reference for text-only generation, and pass `reference_images` for reference-guided generation (including the consistency-anchor pattern above).

Use exact tool-returned URLs or paths; do not invent asset URLs, local filenames, or promo-local manifest paths.

For the AI-video duration / density / resolution / consistency decisions, follow *AI visual strategy* above. For the Remotion-code side of media — loading-aware components, `staticFile`, render timeouts, `trimBefore`/`trimAfter`, and source-clip fallback wiring — read `remotion-best-practices` *Assets and media*.

## Narration and audio timing

Narration is optional. Use it only when the user asks for it or the storyboard clearly benefits from voice-over; do not generate speech by default just because the promo has text.

Do not imitate a celebrity, public figure, influencer, or recognizable person's voice. Use background music only when it is explicitly commercially licensed or generated as original/royalty-free style audio; if unsure, omit BGM.

Before calling `AudioCreator.generate_audios`, split narration into short shot/beat-level segments and generate them as separate audio files. Do not synthesize one long full-video narration track; long tracks drift against visual edits and are hard to realign. Keep each segment final enough to synthesize and short enough for its target shot window. Use concise narrator copy; on-screen text can carry extra detail that should not be spoken.

After audio generation, use the returned CDN `url` directly and prefer the tool-returned `duration` before coding the timeline. If `duration` is missing or `null`, measure it manually. Prefer a command like:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "https://..."
```

Then use `Editor.write` or `Editor.edit_file_by_replace` to update `promo_storyboard.md` with each narration segment URL, measured duration, final locked shot start/end/duration, and recalculated total duration. Do not continue from a mental note, terminal output, or chat-only timing summary; `promo_storyboard.md` is the source of truth that `src/timeline.ts` must follow. If a segment is shorter than its shot, keep the shot length and fill the remaining time with visuals, subtitles, transitions, or quiet music. If a segment is slightly longer, extend that shot and shift later shots. If it is clearly too long, tighten or split the script and regenerate that segment; do not default to speeding up audio, hard-cutting narration, or letting the next scene start while the prior narration is still speaking. If the user requires an exact total length, treat the total duration as fixed and shorten narration scripts first.
If BGM generation later fails or is intentionally omitted, that does not unlock timing. Narration measurement and storyboard timing rewrite are still mandatory before `src/timeline.ts` or scene code is finalized.

By default, promo videos should also have one global BGM track after the narration timing is locked. Read `music-generation` before `MusicCreator.generate_music`. Use exactly one BGM request per promo, not one per shot. The prompt must include the target total seconds, mood, pacing, instrumentation, and explicit constraints such as `instrumental`, `no vocals`, and `leave room for narration` whenever voice-over exists.
If music generation fails, record that BGM is omitted or blocked in `promo_storyboard.md` and continue from the narration-locked timing. Do not fall back to fixed scene durations, starter timeline values, or an unmeasured narration guess.
If BGM generation fails or is intentionally omitted, the final user summary must explicitly say whether the rendered video is silent/no-BGM/visual-only and whether retrying music generation is recommended.

Write promo BGM prompts as natural music descriptions, not as a comma-separated keyword pile. Describe the track in 2-4 short sentences: first name the kind of track and use case, then describe how it starts / builds / resolves, then add mood, instrumentation, and narration-safety constraints. Duration may be stated in prose such as `around 60 seconds` or `60-second structure`, but do not make the prompt read like a CSV tag list.

When the storyboard has clear scene beats or big chapter changes, prefer a segmented music prompt that roughly follows the promo structure. Time-stamped sections or clearly labeled phases are better than one undifferentiated paragraph, because the music should help visual cuts feel intentional rather than arbitrary. Do not force one segment per shot, but do align the major intro / build / showcase / close changes to the storyboard's larger beats. Even when timestamps are present, restate the intended total duration in the final summary sentence because duration control through prompting is not perfectly stable.

Bad pattern:

```text
modern fashion tech background music, upbeat electronic with elegant synth pads, light electronic beats, subtle piano accent, aspirational and sophisticated mood, 100 BPM, instrumental, no vocals, 60 seconds
```

Better pattern:

```text
[0:00 - 0:08] Intro: airy synth pads, light clean beat, elegant opening, leave clear space for narration.
[0:08 - 0:24] Build: add subtle piano accents and a warm bass pulse, energy rises slightly.
[0:24 - 0:42] Showcase: fuller polished electronic groove, sophisticated and aspirational, still narration-safe.
[0:42 - 0:52] Transition: simplify percussion and prepare the close without a hard drop.
[0:52 - 1:00] Outro: reduce layers and end with a gentle polished fade.
An elegant electronic promo track for a fashion-tech film. Instrumental only, no vocals. Designed to sit under narration. Target total length: around 60 seconds.
```

Avoid vague labels like `background music` as the main idea, generic marketing slogans, or long stacks of adjectives with no musical structure. If BPM is useful, treat it as a supporting hint rather than the whole prompt.

After music generation, prefer the tool-returned `duration` before writing the final Remotion timeline; if it is missing or `null`, measure the real BGM duration with the same `ffprobe` command shown above (from the returned URL or local archived path). Then write the BGM URL, measured seconds, target total duration, fit strategy, and planned mix values back into `promo_storyboard.md`. Never lower narration to make the music stand out more.

Choose the `fit strategy` from the measured BGM seconds against the locked promo total, and record which one applies:

- BGM ≥ total: keep one top-level track, trim it to the final length, fade out at the tail.
- Short by more than `2s` or more than `10%`: regenerate once with a more explicit duration prompt before writing final timeline code.
- Still materially short after regenerating: allow only a minimal loop fallback on the global track, hiding the seam with a short fade rather than an abrupt restart.
- Only slightly short: do not regenerate; apply the lightest trim / fade / short-fill in Remotion and keep it unobtrusive.

Do not shorten the locked promo runtime just because the BGM came out short. Music adapts to the locked scene timing, not the other way around.

## Remotion implementation rules

Before writing or reviewing Remotion code, read the `remotion-best-practices` SKILL.md (open it at the absolute path the skill index gave you) and use it as the technical reference. Its key sections:

- *Core rules* owns compositions, `promoScenes` / `getPromoTotalSeconds()`, prop schema, and deterministic motion.
- *Assets and media* owns the Remotion-code side of media: loading-aware components, `staticFile`, render timeouts, `trimBefore`/`trimAfter`, the `promoAudio` mix structure and default volumes, fonts, and charts. (Clip `4-15` duration, density budget, aspect-matching, and source-clip choice live in *AI visual strategy*.)
- *Render and export* owns validation order, `RemotionPromoRenderer.render`, `verify:compositions`, `pnpm run build`, and lower-level render/debug commands.
- *Animation and timing* and *Sequencing and transitions* own the anti-PPT motion baseline and scene pacing details.

Workflow-specific constraints still apply here:

- Render each narration segment with Remotion's `Audio` component inside a `Sequence` aligned to its shot/beat. Do not place one long narration track across the whole video.
- Use `src/timeline.ts` to keep the per-scene narration URLs and one global `promoAudio` object containing `backgroundMusicUrl`, `backgroundMusicDurationSeconds`, `baseVolume`, `duckVolume`, `fadeInFrames`, `fadeOutFrames`, and `loopIfShort`.
- Put the global BGM `Audio` track in `src/PromoVideo.tsx`, not inside every scene. Scene-level code should stay responsible only for scene-local narration/media behavior. Do not duplicate the same BGM across multiple `Sequence`s unless you are intentionally applying the minimal loop fallback documented in `remotion-best-practices` *Promo audio architecture*.
- Keep generated code focused on the storyboard. Do not build a configurable video editor or extra UI.

## Expected commands

```xml
<FrontendEngineer.use_template>
<scene>remotion</scene>
</FrontendEngineer.use_template>
```

Validate in order (all three mandatory), each as its own `Terminal.run`:

```console
pnpm run verify:versions
pnpm run lint
pnpm run verify:compositions
```

`verify:compositions` is a pre-render check only; do not stop there. For `pnpm run build`, lower-level render scripts, and debugging, follow `remotion-best-practices` *Render and export*. Then run the renderer — it performs the matching smoke + full render internally and waits until Remotion returns. Fill `width`/`height`/`source_orientation` from the storyboard Export Spec, not the placeholders below (see the *Command* section for the copy-the-example warning):

```xml
<RemotionPromoRenderer.render>
<promo_dir>/absolute/path/to/app/promo</promo_dir>
<width>WIDTH_FROM_STORYBOARD</width>
<height>HEIGHT_FROM_STORYBOARD</height>
<source_orientation>ORIENTATION_FROM_STORYBOARD</source_orientation>
</RemotionPromoRenderer.render>
```

Completion criteria: `out/promo-<width>x<height>.mp4` exists and is non-empty. Verify before replying. A project that is only "ready to render/export" is unfinished.
