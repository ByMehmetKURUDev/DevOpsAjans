---
name: audio-generation
description: Read when you need text-to-speech audio assets such as narration, voice-over, walkthrough audio, or short spoken clips.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs generated speech audio.
Typical cases: narrator tracks, onboarding voice-over, guided audio, spoken product descriptions.

## Command

Use `AudioCreator.generate_audios`.

## Inputs

- `audios`: JSON array of audio generation requests.
- `text`: text to speak.
- `filename`: logical output filename such as `intro.mp3`.
- `model`: optional.
- `gender`: optional. `male` or `female`. Defaults to `female`.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `path`
- `absolute_path`
- `message`
- `model`
- `voice`
- `gender`
- `duration`

## Rules / Constraints

- `filename` is a logical name for tracking, not a promised local file path.
- Use the returned CDN `url` directly in your code.
- If the tool returns `duration`, prefer it as the measured audio length. Only fall back to manual `ffprobe` when exact timing matters and `duration` is missing or `null`.
- Keep speech text polished before generation; the tool returns audio, not a draft-writing workflow.
- Use this after `todo.md` when generating project assets.
- If the user wants runtime in-app TTS, implement that through backend APIs instead of this internal command.

## XML Example

```xml
<AudioCreator.generate_audios>
<audios>
[
  {
    "text": "Welcome to the dashboard. Here you can track performance, review tasks, and manage your team workflow.",
    "filename": "dashboard-intro.mp3",
    "gender": "female"
  }
]
</audios>
</AudioCreator.generate_audios>
```
