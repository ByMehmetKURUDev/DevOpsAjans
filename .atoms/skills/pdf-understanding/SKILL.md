---
name: pdf-understanding
description: Read when you need to understand a local PDF, answer questions about it, or extract structured information from it.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the task needs real PDF understanding rather than simple string lookup.
Typical cases: summarizing reports, answering PDF questions, extracting tables or structured facts, interpreting visual layout.

## Command

Use `PdfAnalyzer.analyze_pdfs`.

## Inputs

- `pdfs`: JSON array of PDF analysis requests.
- `pdf_path`: local PDF path.
- `instruction`: question or extraction instruction.
- `mode`: `qa` or `extract`. Defaults to `qa`.
- `page_start`: optional 1-based start page. Defaults to `1`.
- `page_end`: optional 1-based end page. If omitted, the tool analyzes up to 80 pages starting from `page_start`. If it exceeds the actual PDF length, the tool truncates it to the last page.

## Returns

Each result item may include:

- `status`
- `pdf_path`
- `instruction`
- `mode`
- `result`
- `message`
- `page_start`
- `page_end`
- `total_pages`

## Rules / Constraints

- Use `Editor.read` only for simple text lookup or direct extraction when PDF understanding is unnecessary.
- Use this skill for summarization, Q&A, structured extraction, or any task that depends on PDF layout, charts, or tables.
- The current tool only supports local PDF files and Claude-based PDF understanding.
- Keep page ranges reasonable. The tool supports up to 80 pages per request window.
- If `page_end` is beyond the real page count, the request does not fail; the tool returns the actual resolved `page_end` in the result.
- Read the useful answer from `result`.

## XML Example

```xml
<PdfAnalyzer.analyze_pdfs>
<pdfs>
[
  {
    "pdf_path": "/absolute/path/to/docs/annual-report.pdf",
    "instruction": "Summarize the main revenue drivers and mention the relevant page numbers.",
    "mode": "extract",
    "page_start": 1,
    "page_end": 20
  }
]
</pdfs>
</PdfAnalyzer.analyze_pdfs>
```
