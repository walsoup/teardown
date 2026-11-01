# teardown

A planned tool: upload a video of someone disassembling a device (an iMac, a phone, whatever) and get back a step-by-step visual repair guide - a clean keyframe per step, every part outlined and labeled, in the style of an iFixit guide.

Being built for the Meta Global AI Developer Hackathon (Oct 27 - Nov 4, 2026, Indie track). **This repo currently holds the build plan only. No code yet.**

## How it will work

1. Upload a short repair clip (30-90 seconds).
2. Muse Voice Transcribe turns the audio into a transcript.
3. Muse Spark watches the clip plus the transcript, picks 6-8 clean keyframes, and names the part and action in each.
4. SAM 3.1 (via the Meta Model API) segments those named parts on just those frames.
5. An OpenCV pass draws the guide look: part outlines, dimmed background, numbered steps, 2x zoom insets.
6. Output is a static guide page that scrolls like a real repair manual.

Keyframe-first is the whole trick: segmenting 6-8 frames instead of the full video is cheaper, faster, and more reliable.

## Plan

[PLAN.md](PLAN.md) has the full build plan: pipeline, milestones, submission requirements, cost guardrails.

## Status

Planning stage. Feedback on the plan welcome.
