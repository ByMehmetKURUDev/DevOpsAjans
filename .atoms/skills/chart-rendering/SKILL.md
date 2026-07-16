---
name: chart-rendering
description: Read when you need to render Mermaid, PlantUML, D2, Graphviz, or similar diagrams into frontend-ready chart assets.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs rendered diagrams or explanatory visuals rather than plain text descriptions.
Typical cases: architecture diagrams, process flows, dependency graphs, sequence diagrams, timelines.

## Command

Use `ChartCreator.generate_charts`.

## Inputs

- `charts`: JSON array of chart render requests.
- `diagram_type`: Kroki diagram type such as `mermaid`, `plantuml`, `d2`, or `graphviz`.
- `code`: raw diagram DSL source.
- `filename`: relative output filename.
- `output_format`: optional. Use `svg` unless PNG is specifically needed.

## Returns

Each result item may include:

- `status`
- `filename`
- `path`
- `absolute_path`
- `url`
- `message`

## Rules / Constraints

- Prefer `svg` for frontend embedding.
- `filename` must stay relative. Do not use absolute paths or parent traversal.
- Use result item `url` directly in frontend code. It is already a local web path such as `/assets/charts/architecture.svg`.
- Use `absolute_path` only when another tool needs the real file path.
- Put the exact DSL source in `code`; do not paraphrase it.

## XML Example

```xml
<ChartCreator.generate_charts>
<charts>
[
  {
    "diagram_type": "mermaid",
    "code": "flowchart TD\n  User[User] --> UI[Frontend]\n  UI --> API[Backend API]\n  API --> DB[(Database)]",
    "filename": "architecture/app-flow.svg",
    "output_format": "svg"
  }
]
</charts>
</ChartCreator.generate_charts>
```
