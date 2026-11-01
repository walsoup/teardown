# teardown

Upload a video of someone disassembling a device (an iMac, a phone, whatever) and get back a step-by-step visual repair guide - a clean keyframe per step, every part outlined and labeled, in the style of an iFixit guide.

Being built for the Meta Global AI Developer Hackathon (Oct 27 - Nov 4, 2026, Indie track).

## How it works

1. `ingest` pulls the audio track (for transcription) and probes the clip with ffmpeg.
2. Muse Voice Transcribe turns the audio into a transcript.
3. Muse Spark watches the clip plus the transcript, picks 6-8 clean keyframes, and names the part and action in each.
4. SAM 3.1 (via the Meta Model API) segments the named part on each keyframe.
5. An OpenCV pass draws the guide look: part outlines, dimmed background, numbered steps, 2x zoom insets.
6. Output is a static guide page (`output/guide.html`) that scrolls like a real repair manual.

Keyframe-first is the whole trick: segmenting 6-8 frames instead of the full video is cheaper, faster, and more reliable.

## Usage

```bash
pip install -r requirements.txt   # needs ffmpeg on PATH too
export MODEL_API_KEY=...          # Model API dashboard > API keys
python -m teardown path/to/clip.mp4
```

`python -m teardown clip.mp4 --mock` runs the whole pipeline with canned steps and a synthetic mask - no API calls, no credit spent. Use it to test ingest, rendering and the guide page.

## Plan

[PLAN.md](PLAN.md) has the full build plan: pipeline, milestones, submission requirements, cost guardrails.

## Status

Pipeline implemented and verified end-to-end with `--mock`. Next: first real run against the Meta Model API on an actual repair clip.
