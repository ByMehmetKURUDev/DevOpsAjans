---
name: image-understanding
description: Read when you need image understanding, OCR, or visual question answering for a local image or an http(s) image URL.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when you need to inspect an image, extract text from it, or answer a question based on what the image shows.
Typical cases: OCR, UI screenshot analysis, chart reading, image QA, asset inspection.

## Command

Use `ImageAnalyzer.analyze_images`.

## Inputs

- `images`: JSON array of image analysis requests.
- `image_path`: absolute local path or http(s) URL.
- `mode`: `summary`, `ocr`, or `qa`. Defaults to `summary`.
- `instruction`: optional for `summary` and `ocr`; required for `qa`.

## Returns

Each result item may include:

- `status`
- `image_path`
- `mode`
- `instruction`
- `result`
- `message`
- `model`

## Rules / Constraints

- Local images must use absolute paths. Relative paths are invalid.
- Use `summary` for general understanding, `ocr` for text extraction, and `qa` for direct questions.
- When `mode` is `qa`, always provide `instruction`.
- Read the useful content from `result`.
- If you need OCR or QA for images extracted from Office documents, this skill is also the follow-up tool.

## XML Example

```xml
<ImageAnalyzer.analyze_images>
<images>
[
  {
    "image_path": "/absolute/path/to/mockups/pricing-table.png",
    "mode": "summary",
    "instruction": "Describe the layout and the main pricing differences."
  },
  {
    "image_path": "https://example.com/assets/invoice-scan.jpg",
    "mode": "ocr"
  },
  {
    "image_path": "/absolute/path/to/screenshots/dashboard.png",
    "mode": "qa",
    "instruction": "What error message is visible in the top-right alert?"
  }
]
</images>
</ImageAnalyzer.analyze_images>
```
