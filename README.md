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
python -m teardown path/to/clip.mp4 --attribution "Creator, license, source URL"
```

Set `TEARDOWN_SPARK_MODEL` to override the planning model (default `muse-spark-1.3`,
e.g. `muse-spark-1.3-contributor` for the cheaper contributor tier). Note the contributor
tier lets Meta use submitted content to train its models - only send footage you own or
have explicit permission for.

`python -m teardown clip.mp4 --mock` runs the whole pipeline with canned steps and a synthetic mask - no API calls, no credit spent. Use it to test ingest, rendering and the guide page.

## Plan

[PLAN.md](PLAN.md) has the full build plan: pipeline, milestones, submission requirements, cost guardrails.

## Footage rights and guide accuracy

Only run teardown on footage you own or have permission to use, and credit the source
with `--attribution`. Generated guides are auto-produced demo output, **not** validated
repair instructions - the page says so in a banner. Verify against the manufacturer's
service documentation before attempting any repair.

## Tested findings (Nov 1, 2026)

Small-sample results from development runs; treat as orientation, not benchmarks:

- Real disassembly clip (90s, narrated): full pipeline OK. Spark planned 7 steps;
  SAM segmented 5/7 parts (battery 0.85-0.91 confidence); two small parts
  ("dust filter", "battery connector") returned zero matches and fell back to
  clean frames. On zero match for a multi-word part, SAM is re-queried once with
  the final noun; a retry match is marked `retried=True` with the actual prompt.
- Drawn-animation synthetic clip (flat colors): Spark planned correct steps with
  and without caption text (one clip each), SAM returned zero matches on all
  frames tried - drawn graphics appear to be a hard input for it.
- One AI-generated photoreal still (muse-image-1.0): SAM matched "battery" at
  0.84, missed "battery connector" even after the simplified-noun retry.
- `scripts/generate_synth.py` makes the synthetic test clip (needs opencv-python
  and ffmpeg).

## Web app

`web/app.py` serves the pipeline as a small site: upload an mp4 or paste a
YouTube link, watch it process, then read the guide with per-step timestamps
that seek the video, plus a print-PDF export. Standard library only.

    export MODEL_API_KEY=...
    python web/app.py            # http://127.0.0.1:8377

## Status

Long-video run on a 19-minute laptop disassembly: 28 ordered steps with tools
and timestamps spanning the full disassembly, audio transcribed in chunks under
the ASR cap, guide page and PDF export rendered. Part highlighting is
fail-closed: only direct segmentation matches are drawn (1/28 on that
low-resolution footage); wrong-object matches are dropped rather than shown.
Small parts and low-resolution frames remain the weak spot.
