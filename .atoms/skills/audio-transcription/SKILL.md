---
name: audio-transcription
description: Read when you need to transcribe a local audio file or an http(s) audio URL into text.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when you need text from existing audio.
Typical cases: captions, transcript generation, subtitle source text, meeting notes, spoken-content extraction.

## Command

Use `AudioTranscriber.transcribe_audios`.

## Inputs

- `audios`: JSON array of transcription requests.
- `audio`: absolute local path or http(s) URL.
- `model`: optional.

## Returns

Each result item may include:

- `status`
- `audio`
- `source_name`
- `text`
- `message`
- `model`

## Rules / Constraints

- Local audio must use an absolute path.
- Read transcript content from `text`.
- This tool does not write transcript files to disk for you.
- If you need subtitles or captions in project files, write them yourself after reading the returned text.

## XML Example

```xml
<AudioTranscriber.transcribe_audios>
<audios>
[
  {
    "audio": "/absolute/path/to/media/founder-interview.mp3"
  },
  {
    "audio": "https://example.com/media/demo.wav"
  }
]
</audios>
</AudioTranscriber.transcribe_audios>
```
