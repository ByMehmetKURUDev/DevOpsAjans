---
name: remotion-best-practices
description: Read alongside promo-video-production when writing, reviewing, validating, or exporting Remotion code in app/promo for an MGX-generated promo or designed multi-shot video, including compositions, props, deterministic animation, sequencing, assets, layout, captions, media handling, and render commands.
alwaysApply: false
roles:
  - Alex
---

## When to use

Read this skill after `promo-video-production` whenever you are:

- writing or reviewing Remotion code in `app/promo`,
- choosing the right validation or render command,
- debugging a Remotion bundle, render, or export,
- deciding which Remotion APIs are appropriate for a deterministic promo or designed multi-shot render.

## What this skill assumes

- The Remotion app lives in `app/promo` and was initialized from the MGX `remotion` template (`FrontendEngineer.use_template("remotion")`).
- The video subject is either a project the agent is building (project promo) or a user-supplied topic / concept (topic promo). Designed multi-shot social, local business, restaurant/food, and discovery videos use the same topic-promo path when no source app exists.
- The storyboard, assets, and rendering are all driven by agent turns and MGX tools, not by a person opening Remotion Studio.

## MGX defaults

- Work inside `app/promo`.
- Default output is landscape `1920x1080`. Use portrait `1080x1920` only when the storyboard or user requests it.
- When writing or reviewing promo copy, asset prompts, or timeline text, follow the storyboard `Language` field. If no explicit user-specified output language is recorded, use English; chat/user message/system prompt language is not an explicit language request.
- Keep renders deterministic and frame-driven; the same inputs must produce the same video on every run.
- Use the exact asset URLs or paths returned by MGX tools or recorded in existing manifests.
- Validate versions, lint, and compositions with `Terminal.run`; final promo export uses `RemotionPromoRenderer.render`, not handwritten Remotion render commands.

## File layout

The template uses a flat `src/` layout under `app/promo`:

- `src/index.ts` — entry point.
- `src/Root.tsx` — Composition registry.
- `src/PromoVideo.tsx` — main component.
- `src/timeline.ts` — `promoScenes` and `getPromoTotalSeconds()`.
- `src/components/` — framing/layout helpers such as `AspectFrame`.
- `src/scenes/` — default scene implementation layer.
- `src/app-demo/` — optional adapters/examples for product/page demos.

Edit these files in place. Do not relocate them under a subdirectory such as `src/remotion/`; that breaks the `package.json` scripts (`remotion render src/index.ts ...`). If you find `app/promo/src/` already populated with a non-template layout, abort and report the wrong deploy — see *Render and export — Sanity-check the deploy*.

## Core rules

### Composition defaults

- Keep MGX promo compositions in `src/Root.tsx`.
- The template registers three preset Compositions sharing one component and prop schema: `PromoLandscape` (1920x1080), `PromoPortrait` (1080x1920), `PromoSquare` (1080x1080), all at 30fps.
- Each Composition uses `calculateMetadata` so `width`, `height`, and `fps` props can override the metadata at render time.
- Total duration is not a prop — it is computed by `getPromoTotalSeconds()` from the `start`/`duration` of `promoScenes` in `src/timeline.ts`. To change overall length, rewrite the scenes; the composition length follows.
- Keep prop schemas as top-level `z.object(...)` values with `width / height / fps` declared as optional.

Use Remotion package versions as a matched set: the template pins Remotion packages to `4.0.453` and `zod` to `4.3.6`; do not mix Remotion package versions.

### Props and metadata

The promo schema accepts:

- `sourceOrientation`: `"landscape" | "portrait" | "square"` — how the storyboard content was designed.
- `targetOrientation`: same values — how the export should look.
- `width`, `height` (positive integers, optional) — composition pixel size.
- `fps` (positive number, optional) — scene timing follows because `PromoVideo.tsx` reads fps from `useVideoConfig()`.

Use `defaultProps` for stable render inputs; props must be serializable and small. Put additional dynamic metadata inside the existing `calculateMetadata` helper. Do not call live backend APIs during render — snapshot project data into local fixtures first.

Do not add a `durationSeconds`-style prop that shortens or lengthens the timeline at render time; trimming the composition silently drops later scenes (and their AI video / audio sources). Length is a storyboard concern: change `promoScenes` instead.

### Timeline schema consistency

The template keeps one lightweight runtime contract:

- `src/timeline.ts` defines `PromoScene`, `promoScenes`, and `promoAudio`.
- `src/PromoVideo.tsx` sequences scenes and owns the global BGM track.
- `src/scenes/*` owns scene-level visuals plus any scene-local narration/media behavior.

If you change `PromoScene` or `promoAudio`, update `src/PromoVideo.tsx` and the affected `src/scenes/*` files in the same pass. Stale scene imports, old `kind` branches, or half-updated scene props make `pnpm run lint` fail at the `tsc` step.

### Determinism

- Drive motion from `useCurrentFrame()` and `useVideoConfig()`. The template's `PromoVideo.tsx` already reads `useVideoConfig().fps`, so scene timing follows any fps override.
- Do not use `Date.now()`, timers, browser event loops, CSS animations, CSS transitions, or unseeded randomness.
- If variety is needed, derive it from stable data such as scene index, frame, or props.

### Tailwind

Tailwind is enabled by the template. Use it for static layout and styling, but never `animate-*` or `transition-*` classes for video motion — use frame-driven styles.

### Product demos

Prefer static fixtures and frame-driven state. Import real frontend components only when they are independently renderable without routing, auth, live API calls, or full app bootstrap; otherwise recreate the actual product screen from project code with Remotion-native layout, local fixtures, and project assets. Do not fall back to generic abstract cards, placeholder dashboards, or fake flow panels when the app already has a concrete interface for that moment.

## Animation and timing

### Frame-driven motion

Use `useCurrentFrame()` and `interpolate()` for most motion:

```tsx
const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 24], [0, 1], {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
});
```

Clamp entering and exiting values unless deliberate overshoot is part of the visual design.

### Promo motion baseline

The baseline is not optional: the video must not feel like a PowerPoint export. Scenes whose only motion is text opacity, a slight y-offset, or a static card crossfade can support a beat, but do not count as the scene's main motion. Give each major beat a few coordinated frame-driven layers: camera push/pan, parallax background, foreground accent movement, mask reveal, kinetic word emphasis, chart/data animation, or product UI state changes.

For still-image or product-led scenes, use at least one background motion layer (slow push, pan, zoom, parallax drift) plus one supporting layer (mask reveal, light sweep/reflection, foreground drift, emphasis word treatment, counter/path/state change). Keep product demos readable: animate the surrounding frame, selection state, counters, paths, or supporting overlays instead of shaking or obscuring the UI. When a shot communicates relationships, flows, checkpoints, or org structure through connectors, default to curved or routed paths rather than raw point-to-point straight lines unless rigid geometry is the actual point of the shot.

Concrete motion vocabulary for describing or implementing a shot:

- Background: slow push, pan, drift, zoom, parallax.
- Support: mask reveal, light sweep, soft reflection, foreground float, wipe.
- Product/data: selected-state change, curved path growth, route tracing, rounded-corner path reveal, highlight travel along a path, counter tick, chart range shift.

Fade in/out may support entrances and exits, but never as the whole motion plan for a scene.

### Normalized progress

Compute one or two normalized progress values per scene and derive transforms, opacity, blur, chart values, and masks from them — timing stays readable, animations stay matched.

```tsx
const enter = interpolate(localFrame, [0, 24], [0, 1], {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
});
const y = interpolate(enter, [0, 1], [32, 0]);
const scale = interpolate(enter, [0, 1], [0.96, 1]);
```

### Easing

Use `Easing.out(Easing.cubic)` for most entrances, `Easing.in(Easing.cubic)` for exits, and a custom `Easing.bezier(...)` only when the storyboard needs a specific feel. Use `spring()` sparingly for UI pops, counters, and emphasis; keep damping high enough to avoid distracting bounce in SaaS or productivity demos.

### Text animation

Use text animation to support meaning, not to decorate every line: fade + slight y-offset for headings; stagger words only for hero claims or short punchlines; highlight important words with frame-driven background width, underline, or color. Text moves are supporting animation, not a substitute for the scene's main motion layers. No CSS `animation`, `transition`, or JavaScript timers.

### Time conversion

Use `const { fps } = useVideoConfig()` when converting seconds to frames inside components; use constants in `timeline.ts` for global shot timing.

## Sequencing and transitions

### Scene timeline

Keep storyboard timing in `src/timeline.ts`. A scene needs a start frame, duration, role in the story, visual copy, and any asset references. Inside a scene component, prefer local frame/progress:

```tsx
const frame = useCurrentFrame();
const localFrame = frame - scene.from;
const progress = interpolate(localFrame, [0, scene.duration], [0, 1], {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
});
```

Avoid one long static state per scene. If a scene lasts more than about 6 seconds, split it into internal beats with nested `Sequence`s or local progress windows so something meaningful changes every 1-2 seconds: product state, chart values, camera framing, captions, masks, reflections, or foreground accents. A slow fade over a frozen composition is not enough.

### Sequence and Series

Use `<Sequence from={...} durationInFrames={...}>` to place scene layers and product demo beats. `useCurrentFrame()` inside a `Sequence` starts at `0` for that sequence. Without `layout="none"`, `Sequence` wraps children in the default absolute-fill wrapper, which inherits the `AbsoluteFill` flex-column behavior — pass `layout="none"` when you already own the container layout or a horizontal row/grid would be distorted by the wrapper.

Use `<Series>` for strictly sequential sections; for promos with overlapping scene elements, a timeline array plus `Sequence` is usually clearer.

### Transitions

Prefer simple frame-driven crossfades, slides, wipes, or masks; add `@remotion/transitions` only when the storyboard genuinely benefits from reusable transition primitives. Keep transitions short enough that the product remains readable. Transitions that overlap scenes reduce total timeline duration; overlays do not. Fade-only scene cuts may support a transition, but do not replace the scene's internal motion plan.

Do not let the whole video become a list of slide cuts: carry visual energy between beats with a foreground wipe, media match cut, light sweep, zoom-through, or product-panel move, while keeping the story and UI legible. A still-image scene that only moves at the cut points still reads like a slide deck and needs more internal beat changes.

### Product demo timing

Simulate user flows with frame-driven state: change selected tab, table row, chart range, or form progress by frame. No real user events, browser recordings, or live backend calls. Keep each demo beat visually understandable for at least one second.

## Assets and media

This section covers the Remotion-code side of media: loading-aware components, local/remote asset wiring, render timeouts, the `promoAudio` mix, fonts, and charts. The design decisions about which assets to generate — clip duration/density/resolution, consistency anchors, scene composition, and BGM fit — are planned in `promo-video-production` and not restated here.

### MGX asset references

Use the exact URL or path returned by MGX tools or existing manifest records; do not invent CDN URLs, local filenames, or manifest paths. Asset manifests may be managed outside `app/promo` — do not assume one exists inside the promo directory.

### Local assets

Put local render assets under `public/` and reference them with `staticFile("...")`.

Use Remotion loading-aware components from the `remotion` package: `Img` for images, `OffthreadVideo` (preferred for promo timelines) or `Video` for videos, `Audio` for audio. New scene-level remote video layers should use `OffthreadVideo` and keep the same loading-aware pattern.

The template's default `<OffthreadVideo>` already sets `delayRenderTimeoutInMilliseconds={90000}` and `delayRenderRetries={3}`, and the package render scripts pass `--timeout=90000` (smoke) / `--timeout=120000` (full). Remotion fetches every remote video through its local proxy at render time, and CDN-served AI clips routinely take 30–60 s on a cold fetch — the stock 28 s `delayRender` deadline aborts the render with `delayRender() ... was called but not cleared after 28000ms`. Copy these props to every new `<OffthreadVideo>` and the matching `--timeout` flag to every new render script. Don't lower them, and don't add per-render `--timeout` overrides on top of the bumped defaults unless you've measured a need.

Add `@remotion/media` only when you specifically need its media-parser features; run `pnpm exec remotion add @remotion/media` first, then switch the relevant imports.

Do not use native `<img>` for important render images, CSS `background-image` for critical assets, or framework-runtime image components that depend on Next.js, Vite plugins, or similar layers.

### Remote assets

Tool-returned remote image, video, and audio URLs can be used directly; prefer stable HTTPS URLs. If render fails because of CORS, redirects, expiry, decode support, or proxy fetch timing out beyond the bumped `delayRenderTimeoutInMilliseconds`, store the asset locally and use `staticFile()`.

AI videos are source clips in the Remotion timeline, not the final render output. (When source generation fails, the image-plus-Remotion-motion fallback is a design decision planned in `promo-video-production` *AI visual strategy*.)

### Still-image and no-AI-video scenes

The composition design for scenes without an AI source clip — real/generated background layer instead of a bare solid or gradient, at least one inspectable foreground showcase layer over a low-detail copy zone, structural diagrams dominant in the foreground rather than echoed larger in the background, layered motion for real UI/charts — is planned in `promo-video-production` (*Visual motion baseline*, *AI visual strategy*, and the storyboard's foreground-scale and product-demo fields) and not restated here.

### Video and audio behavior

Trim media in frames using `trimBefore` and `trimAfter`. Wrap media in `Sequence` to delay its start. Use frame-driven volume fades for audio and video.

Render-side reasons the clip-covers-scene and resolution/aspect rules matter: a source clip shorter than its scene makes `<OffthreadVideo>` freeze on the final decoded frame or loop (a common "scene N looks broken" report) — the ~1s tail exists so `trimAfter` can cut the last frame cleanly; an upscaled or wrong-aspect clip renders soft or gets letterboxed/cropped. The override over `video-generation`'s default `seconds=4` is intentional — promo timelines require the clip to cover the scene.

Keep background music quiet under narration or product copy. Fade audio at scene boundaries to avoid hard cuts.

### Promo audio architecture

All promo audio comes from exactly two sources: per-scene narration and one global BGM track. AI video source clips are a **visual** layer only — the model (e.g. `seedance-2.0`) may bake ambient sound or music into the clip, and `<OffthreadVideo>` plays that embedded track by default (`muted` defaults to `false`), stacking it on your BGM and narration. Apply both guards:

- Render every promo source clip muted: pass `muted` on each scene `<OffthreadVideo>` (e.g. `<OffthreadVideo src={...} muted ... />`). This is the authoritative guard and works even when a clip already has a baked-in track.
- Generate promo source clips with `audio=false` in the `VideoCreator.generate_videos` request so no audio track is produced in the first place (saves bandwidth, avoids surprises). Do not rely on this alone — keep `muted` as the deterministic backstop.

Use exactly one global BGM track in `src/PromoVideo.tsx` and keep narration audio inside each scene `Sequence`. Do not attach the same BGM track to every scene. Scene-level components own scene-local narration/media behavior; the top-level promo component owns global BGM and ducking.

Store promo-wide mix settings in `src/timeline.ts` as a `promoAudio` object with at least `backgroundMusicUrl`, `backgroundMusicDurationSeconds`, `baseVolume`, `duckVolume`, `fadeInFrames`, `fadeOutFrames`, and `loopIfShort`.

Defaults unless the user explicitly requires a different mix:

- Narration peak volume: `1.0`
- BGM `baseVolume` when no narration is active: `0.26`
- BGM `duckVolume` when narration is active: `0.14`
- BGM `fadeInFrames`: `18`, `fadeOutFrames`: `24`
- BGM hard ceiling: do not exceed `0.30`

Use `volume={(frame) => ...}` on the top-level BGM `Audio` so the track can both fade in/out and duck under narration. Never lower narration to make the music more audible.

### Promo audio duration policy

The measured-BGM-vs-total fit policy (trim / regenerate / minimal loop / light-fill, with the `2s` / `10%` thresholds) is planned in `promo-video-production` *Narration and audio timing* before the timeline is written. On the Remotion side, implement whichever fit strategy the storyboard recorded: trim the top-level track to the final length and fade the tail, or apply the minimal loop fallback with a short seam fade. Do not shorten the locked promo runtime to match a short BGM.

### Fonts

Prefer local or template-safe fonts for repeatable renders. If adding Google or local font loaders, load fonts before measuring text or rendering typography-heavy frames.

### Charts

Build charts with React/SVG/HTML and drive chart animation from frames. Disable third-party chart library animations — they are not synchronized with the Remotion frame clock.

## Layout and text

### Aspect ratios

The template ships landscape `1920x1080` (16:9), portrait `1080x1920` (9:16), and square `1080x1080` (1:1). When the export orientation differs from the storyboard design, `AspectFrame` centers the source content with black bars (top/bottom for narrower targets, left/right for taller targets); matching orientations fill the frame. Non-default sizes (4K, 720p, 4:5 social, etc.) reuse the same Composition via `--props='{"width":N,"height":M}'`; `sourceOrientation` and `targetOrientation` should still describe the closest design intent so the aspect framing behaves correctly. Use the template aspect-frame components instead of stretching the source UI.

Treat page demos like camera-framed viewports: choose the most relevant viewport or section per shot and keep the embedded browser/app window the dominant, readable inset subject. Viewport choice, below-the-fold handling, and window framing are planned in `promo-video-production` *Product demo rules* and the storyboard's `viewport focus` field.

### Safe layout

Keep key copy, product UI, and logos away from edges. Use stable dimensions for cards, demo frames, charts, counters, and text blocks so animation does not resize the layout.

Compose promo scenes in layers: background for atmosphere, foreground showcase modules for what the viewer should actually inspect. If a feature, result, object, or workflow state is important to the shot, give it a readable foreground frame/panel/card instead of leaving it only in the background art.

Do not place large text over detailed product UI unless the UI is intentionally backgrounded. If headings, captions, node labels, bar labels, or numeric metrics sit over textured art, glow, or a similar-color background, move them into a clean copy area or add local contrast protection (scrim, ribbon, pill, card, stroke, shadow, or a higher-contrast text color). Never rely on accent-colored text placed directly on a near-accent background without separation.

Video CTAs should read as video graphics: end-card copy, a logo lockup, an info strip, a URL/account line, or a QR placeholder. Avoid final CTA visuals that look like interactive web controls — rounded primary buttons, hover/pressed states, cursor/click affordances, fake input boxes, or navigation arrows. UI buttons are fine inside a product demo shot showing the actual flow; do not reuse that treatment as the closing conversion CTA.

`AbsoluteFill` defaults to `display: flex` with `flexDirection: column`. For horizontal bands, comparison rows, step strips, or two-column showcase modules, set `flexDirection: "row"` explicitly or use a plain `div` wrapper — otherwise cards stack vertically, stretch on the wrong axis, or hug one side of the frame.

### Text fitting and typography

Shorten copy first. If text still risks overflow: use line breaks in the storyboard copy, cap heading size per scene instead of scaling with viewport width, and use `@remotion/layout-utils` only when dynamic text genuinely needs measurement. Keep letter spacing at `0` unless a specific brand treatment requires otherwise.

Hero-sized type belongs in open scenes, not compact panels; product demo overlays use tighter headings and smaller labels so the app remains readable.

When measuring text, load fonts first and measure with the same font family, size, weight, and letter spacing used for rendering.

## Captions

Use structured caption data with text and timing — JSON fixtures checked into `app/promo` or generated outputs explicitly returned by tools. Each caption item: `text`, start time or start frame, end time or duration, optional confidence/speaker metadata.

Render captions with `Sequence` or frame checks; keep them inside the safe area and off primary product UI. For word highlighting, pre-split caption text and drive the active word by frame with a simple treatment: weight, color, underline, or background fill.

Convert `.srt` sources to JSON before rendering; do not parse raw `.srt` text inside a frame-rendering component. When captions must be generated, use MGX audio/video transcription tools, keep the generated files as stable render inputs, and avoid transcription calls during render.

## Advanced media

Only needed when the task requires media inspection, preprocessing, silence trimming, or nonstandard export behavior.

Use FFmpeg for preprocessing outside the Remotion frame render path: trim or normalize long source clips, extract audio tracks, detect leading/trailing silence, re-encode media that Chrome cannot decode reliably. Keep FFmpeg commands deterministic and record generated file paths in the storyboard or local fixture data.

When duration or dimensions are needed for layout, gather them before rendering or in `calculateMetadata` — never as expensive work inside frame components. Prefer Remotion-supported helpers or a small Node-side utility, and cache results in fixture data when the same media is reused.

If a video source fails in Chrome but plays elsewhere, verify codec/container support and re-encode to a browser-safe MP4 before using it in the timeline. Store extracted frames (filmstrips, thumbnails, visual analysis) under `public/` and reference them with `staticFile()`. Use silence detection to trim source voiceover or demo clips before they enter the timeline; keep the final timeline frame-based and never run silence detection during render.

Do not add Mapbox, ElevenLabs, Lottie, 3D, light leaks, audio visualization, transparent video, or transcription dependencies unless the user explicitly asks for one of those capabilities and the required credentials or assets are already available.

## Render and export

### Sanity-check the deploy if anything looks off

`use_template("remotion")` validates the source before copying, so a successful return means `app/promo` is a real Remotion deploy — no separate `grep` step needed in normal runs. If something downstream looks wrong (`package.json` scripts don't match this section, `src/Root.tsx` is missing, or the template feels like a different framework), stop before running renders:

- Do not run `pnpm install`, `pnpm add`, or any render command.
- Do not bolt Remotion on top of a non-Remotion `app/promo`.
- Report the wrong deploy back. The fix is on the platform / orchestration side, not in your render commands.

### Standard command order

Run commands from `app/promo`:

```console
pnpm install
pnpm run verify:versions
pnpm run lint
pnpm run verify:compositions
```

Then export through the agent-facing renderer tool:

```xml
<RemotionPromoRenderer.render>
<promo_dir>/absolute/path/to/app/promo</promo_dir>
<width>1920</width>
<height>1080</height>
<source_orientation>landscape</source_orientation>
</RemotionPromoRenderer.render>
```

Set `width` and `height` to the concrete target resolution. The renderer chooses `PromoLandscape`, `PromoPortrait`, or `PromoSquare` from that resolution, writes `out/render-<width>x<height>.log`, and returns `out/promo-<width>x<height>.mp4`. The parameters must match `promo_storyboard.md` and the export spec — do not copy the landscape example when the storyboard says portrait/9:16/TikTok/Reels; portrait exports use `width=1080`, `height=1920`, `source_orientation=portrait`.

`verify:compositions` is a pre-render check only. After it passes, continue to the renderer; the workflow is not done until `out/promo-<width>x<height>.mp4` exists and is non-empty.

Do not use `Terminal.run` for final promo export — the renderer already runs smoke first and skips full render if smoke fails. `Terminal.run` remains appropriate for install, version checks, lint, composition verification, and targeted manual debugging. Do not run `pnpm run build` as a compile check: in this template `build` is a lower-level alias for the default landscape render, so it starts a full export and bypasses the agent-facing renderer workflow.

If `RemotionPromoRenderer.render` fails, inspect `out/render-<width>x<height>.log`, fix the reported issue, confirm `width` / `height` / `source_orientation` against the current storyboard export spec, then retry `RemotionPromoRenderer.render`. Do not switch to manual `pnpm exec remotion render` just because the failure was fixed, a smoke render passed, assets were localized, or the next step feels like a retry.

### Custom dimensions or fps

Each preset Composition accepts `width`, `height`, `fps`, `sourceOrientation`, and `targetOrientation` as props. The renderer passes `width`, `height`, `sourceOrientation`, and the resolution-derived `targetOrientation` for final export. **Total duration is not a render-time prop** — it comes from `promoScenes` in `src/timeline.ts` (see *Core rules*).

```xml
<RemotionPromoRenderer.render>
<promo_dir>/absolute/path/to/app/promo</promo_dir>
<width>3840</width>
<height>2160</height>
<source_orientation>landscape</source_orientation>
</RemotionPromoRenderer.render>
```

For unusual debugging, you may inspect the generated log or run the package scripts manually, but do not replace the final renderer call with manual `pnpm exec remotion render` during normal agent delivery.

When width and height change to a non-preset aspect, set `sourceOrientation` to the orientation closest to the storyboard design and `targetOrientation` to the orientation closest to the export aspect, so `AspectFrame` produces correct black bars or fills the frame. Layout uses fixed `px` values calibrated for 1080p — rendering at 4K or 720p makes text and padding look proportionally smaller or larger; pick a size close to 1080p, or update `src/components/` to scale typography for the target resolution.

### Command meanings

- `verify:versions`: validates Remotion and peer package versions.
- `lint`: runs ESLint and TypeScript.
- `verify:compositions`: bundles the code and lists available compositions.
- `build`: lower-level alias for the default landscape render. Do not use it as validation in agent runs.
- `prewarm:browser`: downloads or verifies Remotion's Headless Chrome.
- `still:landscape` / `still:portrait` / `still:square`: export frame 30 at quarter scale of the matching Composition.
- `render:smoke` / `render:smoke-portrait` / `render:smoke-square`: lower-level smoke scripts for manual debugging.
- `render:landscape` / `render:portrait` / `render:square`: lower-level full-render scripts for local/manual debugging. Agent final export still uses `RemotionPromoRenderer.render`.

### Ports and first run

Do not pass `--port` by default — Remotion `4.0.453` uses bind-based port probing and chooses an available renderer port. Only pass `--port=<free-port>` when debugging a confirmed local port conflict. The first browser-backed command (`prewarm:browser`, `verify:compositions`, render commands) may need network access to download Headless Chrome.

### Failure triage

- Version mismatch: fix `package.json` so all Remotion packages share the same pinned version and `zod` matches Remotion's requirement.
- Composition lookup failure: run `verify:compositions`, then check `src/index.ts`, `src/Root.tsx`, and composition IDs.
- Smoke render failure: fix it before a full render. The renderer log shows the smoke command and stderr.
- `--props` parse error: ensure the JSON is valid and quoted for the shell. Optional fields can be omitted; missing required fields fall back to `defaultProps`.
- Slow render: shorten heavy scenes, reduce media layers, avoid full app bootstraps. The renderer full render omits `--concurrency` (Remotion auto-selects; pushing it higher rarely helps); the smoke pass intentionally pins `--concurrency=1` so error messages stay readable.
- Remote asset failure: use exact tool-returned URLs and verify CORS, or convert the asset to a local `public/` file.
