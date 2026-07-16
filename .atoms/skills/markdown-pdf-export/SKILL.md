---
name: markdown-pdf-export
description: Read when you need to convert a local Markdown file into a print-first PDF for delivery, export, or sharing.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project already has a Markdown file and needs a PDF export.
Typical cases: report export, printable proposal, presentation handout, final deliverable PDF.

## Command

Use `MarkdownPdfCreator.convert_file`.

## Inputs

- `markdown_path`: source Markdown file path.
- `output_path`: optional target PDF path or output directory. If omitted, the tool uses the source directory and the same stem.
- `title`: optional PDF title override.
- `enable_math`: optional boolean for MathJax rendering. Defaults to `true`.
- `enable_mermaid`: optional boolean for Mermaid rendering. Defaults to `true`.
- `keep_html`: optional boolean to keep the intermediate HTML file.

## Returns

The result may include:

- `status`
- `input_path`
- `output_path`
- `html_path`
- `message`

## Rules / Constraints

- Use this only when the source content already exists as a local Markdown file.
- Prefer leaving `enable_math` and `enable_mermaid` enabled unless the document clearly does not need them.
- Use `keep_html: true` only when you need to debug rendering or keep the intermediate HTML artifact.
- Read the final PDF location from `output_path`.
- This is an internal export tool, not an end-user runtime feature.

## XML Example

```xml
<MarkdownPdfCreator.convert_file>
<markdown_path>
/absolute/path/to/reports/quarterly-summary.md
</markdown_path>
<output_path>
/absolute/path/to/reports/quarterly-summary.pdf
</output_path>
<title>
Quarterly Summary
</title>
<enable_math>
True
</enable_math>
<enable_mermaid>
True
</enable_mermaid>
<keep_html>
False
</keep_html>
</MarkdownPdfCreator.convert_file>
```
