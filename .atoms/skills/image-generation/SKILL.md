---
name: image-generation
description: Read when you need to generate or edit project image assets such as hero banners, product visuals, logos, icons, or transparent cutouts.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the task needs new image assets or image-to-image editing for project delivery.
Typical cases: hero banners, product cards, logos, decorative visuals, section backgrounds, transparent PNG assets, product packshots, e-commerce / Amazon-style product photos, product detail / macro shots, storefront / lifestyle plates, and consistency-anchor hero images that later drive reference-guided video clips.

## Command

Use `ImageCreator.generate_images`.

## Inputs
- `images`: JSON array of image request objects.
- `description`: detailed visual description.
- `filename`: descriptive output filename, usually in English.
- `style`: optional. Defaults to `photorealistic`. Common values: `photorealistic`, `cartoon`, `sketch`, `watercolor`, `minimalist`, `3d`.
- `size`: optional image size such as `1024x1024`, `1024x576`, `1024x768`. Defaults to `1024x1024`.
- `model`: optional image model for this request. Only include it when a specific model is requested; otherwise omit it and the configured default model will be used.
- `image`: optional reference image for image-to-image editing. Must be an absolute local path or an http(s) URL.
- `background`: optional. Use `transparent` for transparent output.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `path`
- `absolute_path`
- `message`

## Rules / Constraints

- Batch all required images into one call whenever possible.
- The tool automatically enhances your prompt with professional composition/lighting/style detail. You don't need to write exhaustive keywords yourself.
- **But you MUST still provide a clear, specific base prompt**: subject + key visual elements + intended mood + any required on-image text/brand. The optimizer enhances intent, it cannot invent missing facts.
- Brand names, on-image text, and exact counts are preserved as-is — state them explicitly.
- For image editing (`image` set), write an instruction describing the change, not a fresh scene.
- For a packshot or catalog-style product image, request a clean/seamless or transparent background (`background: "transparent"` with a `.png` filename) and a clear product-centered composition.
- When the image must show a specific real product/subject that already has a reference image, generate it image-to-image (pass the reference in `image` and describe the change), not text-only — otherwise the model reinvents the product. Backgrounds/atmosphere with no specific product stay text-only.
- Use descriptive English filenames so later code references stay clear.
- If a result item has `url`, use that URL directly in code. Do not download it.
- If there is no `url`, use the returned local asset path according to the tool result.
- Reference `image` only supports absolute local paths or http(s) URLs. Do not pass data URIs.
- Transparent background requests should use `background: "transparent"` and a `.png` or `.webp` filename, or no extension.
- Transparent background requests temporarily switch the underlying model to `gpt-image-1.5`.
- Run image generation after the active workflow's planning artifact is written and locked. If the current workflow already names a storyboard or other source-of-truth file, follow that file instead of creating a separate `todo.md`.
- If the user wants end-user in-app image generation, implement that through backend AI APIs instead of this internal command.

## XML Example

```xml
<ImageCreator.generate_images>
<images>
[
  {
    "description": "Cinematic homepage hero banner showing a futuristic electric motorcycle on a wet city street at dusk, neon reflections, dynamic angle, bold composition",
    "filename": "hero-electric-motorcycle-dusk.jpg",
    "style": "photorealistic",
    "size": "1024x576"
  },
  {
    "description": "Minimal owl logo mark for a productivity app, centered composition, clean vector-like shapes, no background shadows",
    "filename": "logo-owl-mark.png",
    "style": "minimalist",
    "size": "1024x1024",
    "background": "transparent"
  }
]
</images>
</ImageCreator.generate_images>
```
