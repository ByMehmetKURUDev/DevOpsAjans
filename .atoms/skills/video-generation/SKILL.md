---
name: video-generation
description: Read when you need to generate a single short visual-only source clip such as a hero background, atmosphere loop, one-shot image-to-video clip, keyframe video, or reference-to-video clip. Do NOT use this for a deliverable that pairs the clip with narration/voiceover or any separate audio track, or that needs the video timed to match an audio length — that belongs to promo-video-production (Remotion), because a single generated clip cannot stretch or sync to a voiceover and the audio would be cut off.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs generated video content as a source asset.
Typical cases: hero background loops, atmosphere clips, short motion scenes, product reference clips, one-shot image-to-video clips, or first/last-frame transitions.

Do not use `VideoCreator.generate_videos` as the final delivery path for a complete multi-shot video. If the request includes a timeline, shot list, captions, narration/audio, editing direction, CTA/end card, multiple scenes, or a total duration beyond one short clip, read `promo-video-production` first and treat AI-generated videos as source clips inside the Remotion timeline.

If the task is specifically to edit an existing source video, prefer the `video-editing` skill and `VideoCreator.edit_videos`. This skill remains the general entry for text-to-video, image-to-video, keyframe-to-video, and reference-to-video generation.

## Command

- Use `VideoCreator.generate_videos` for normal generated clips.

## `generate_videos` Inputs

- `videos`: JSON array of video generation requests.
- `prompt`: video prompt.
- `filename`: logical output name with extension such as `.mp4`.
- `model`: optional.
- `size`: optional. Defaults to `1280x720`. Keep this default unless the task clearly requires another size.
- `seconds`: optional. Defaults to `4`. Keep this default unless the task clearly requires another duration. For `seedance-2.0`, request only `4` to `15` seconds.
- `image`: optional legacy reference image for image-to-video. Must be an absolute local path or an http(s) URL.
- `input_reference`: optional image-to-video reference. Prefer `first_frame` for new requests.
- `first_frame`: optional first-frame image reference.
- `last_frame`: optional last-frame image reference. Requires `first_frame`.
- `reference_images`: optional reference image array for reference-to-video.
- `reference_videos`: optional reference video array for reference-to-video, video edit, or video extend.
- `reference_audios`: optional reference audio array for reference-to-video models that support audio reference.
- `resolution`: optional resolution level such as `720p`, `1080p`, or `4k`.
- `ratio`: optional aspect ratio such as `16:9`, `9:16`, or `1:1`.
- `audio`: optional boolean to request model-generated audio when supported. For a Remotion promo source clip set `audio=false` — the clip is a visual layer and promo audio comes only from the timeline's narration + global BGM; a baked-in clip track would stack on the BGM (also render the clip's `<OffthreadVideo>` with `muted`).
- `audio_setting`: optional video-edit audio behavior, `auto` or `origin`.
- `negative_prompt`: optional elements to avoid.

Reference item fields:

- `url`: required. http(s) URL, supported data URI / gs:// URI, or absolute local path.
- `role`: optional. Common values: `reference_image`, `first_frame`, `last_frame`, `style`, `grid`, `reference_video`, `video`, `extend`, `reference_audio`.
- `tag`: optional prompt binding tag such as `@subject1`.
- `voice_url`: optional voice reference for supported R2V models.

Reference prompt binding:

- If `reference_images`, `reference_videos`, or `reference_audios` are provided, the `prompt` must explicitly bind each reference before the scene description.
- Use provider-readable ordinal labels that match array order: `Video 1` is `reference_videos[0]`, `Image 1` is `reference_images[0]`, and `Audio 1` is `reference_audios[0]`.
- Include any `tag` in the binding line when useful, but do not rely on tags alone. The scene should refer to `Image 1`, `Video 1`, `Audio 1`, or the tag.
- Do not only describe references with natural-language names such as "the brown-haired girl" or "the guitarist"; that does not reliably bind the uploaded assets to the prompt.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `path`
- `absolute_path`
- `message`
- `model`
- `size`
- `seconds`

## Rules / Constraints

- `filename` is a logical identifier, not a guaranteed local file path.
- The tool automatically enriches your prompt with visual detail, motion, and physical realism, and picks a shot strategy that fits the content. You don't need to write cinematography jargon yourself, but you MUST still give a clear base prompt: subject + key action + intended mood.
- You do not need to script the camera. The optimizer leaves atmosphere/single-subject clips open so the model finds its own shot rhythm, and organizes information-dense clips (product, ad, demo) into a multi-shot sequence. State an explicit shot wish only when you truly need one — e.g. ask for a "single continuous shot, no cuts" when the clip is a source clip for a Remotion timeline, or describe the shots yourself when you need a specific edit. Any explicit shot/camera/pace request you write is followed exactly.
- For commerce / product / ad / demo clips, name the scene type in the base prompt using the optimizer's own vocabulary — "product showcase", "commercial/ad", or "feature demo" — so the information-dense branch reliably produces a multi-shot `Shot 1: / Shot 2: / Shot 3:` sequence. Single-shot vs multi-shot is a real distinction: a single source clip for a Remotion timeline must stay "single continuous shot, no cuts" (the timeline owns the cuts); use the multi-shot phrasing only when you want one standalone clip to cover several selling points/angles itself.
- For a Remotion promo source clip, use `seedance-2.0` (one unified model: text-only generation passes no reference; reference-guided generation passes `reference_images`). To keep a product/subject consistent across clips, reuse one canonical reference image in `reference_images` on every clip; the resulting `Reference map:` block must stay the literal start of the prompt and the optimizer preserves it verbatim.
- Always keep the `Reference map:` block as the literal start of your prompt. The optimizer preserves it; do not rely on it to create the binding.
- For a true multi-shot edited deliverable (timeline, captions, narration), use the Remotion timeline rather than asking one generated clip to be the whole video.
- Use the returned CDN `url` directly in your code.
- Use absolute local paths or http(s) URLs for internal local file references. Runtime backend APIs may accept browser data URIs.
- Do not provide both top-level `first_frame` and a `reference_images` item with `role: "first_frame"`.
- Do not provide both top-level `last_frame` and a `reference_images` item with `role: "last_frame"`.
- `last_frame` requires `first_frame`.
- If the user provides uploaded asset paths, pass them through `reference_images`, `reference_videos`, `reference_audios`, `first_frame`, or `input_reference`; never only describe those assets in the prompt.
- For multi-reference R2V prompts, begin the prompt with a reference map, for example: `Reference map:\nVideo 1 = @player, main performer\nImage 1 = @girl, brown-haired girl\n\nScene:\nVideo 1 sits beside Image 1`.
- `1280x720` and `4` seconds are the safest defaults across current video models, so do not change them unless the requirement clearly needs it.
- `seedance-2.0` accepts `seconds` only from `4` to `15`; never pass `1`, `2`, or `3` seconds to this model. If a beat feels shorter, generate a 4-second clip and trim it in the consuming timeline/component.
- This tool is for internal asset creation after the active planning artifact, not for end-user runtime video generation.
- If the user wants in-app video generation, implement it through backend AI APIs.

## XML Example

```xml
<VideoCreator.generate_videos>
<videos>
[
  {
    "prompt": "Slow cinematic fly-through of a modern workspace with warm sunlight, shallow depth of field, premium brand mood",
    "filename": "hero-workspace-loop.mp4"
  },
  {
    "prompt": "Subtle motion applied to a product poster for a homepage hero section",
    "filename": "poster-motion.mp4",
    "image": "/absolute/path/to/assets/poster-reference.png"
  },
  {
    "prompt": "Reference map:\nImage 1 = @product_front, product front view\nImage 2 = @product_side, product side view\n\nScene:\nCreate a clean product teaser using Image 1 as the hero product view and Image 2 for secondary angle details",
    "filename": "product-reference-teaser.mp4",
    "model": "seedance-2.0",
    "reference_images": [
      {"url": "https://example.com/product-front.png", "role": "reference_image", "tag": "@product_front"},
      {"url": "https://example.com/product-side.png", "role": "reference_image", "tag": "@product_side"}
    ],
    "resolution": "720p",
    "ratio": "16:9",
    "seconds": 5
  }
]
</videos>
</VideoCreator.generate_videos>
```
