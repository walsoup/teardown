# teardown - build plan

Meta Global AI Developer Hackathon 2026. Indie track, theme "Build for Your World".
Submissions due **Nov 4, 9:00 PM ET**. Judging: Impact 30%, creative use of Meta tooling 25%, technical depth 20%, live demo 25%.

## The one-sentence version

Repair footage in, illustrated step-by-step repair guide out.

## Why this fits

- It needs real Meta model capability: video understanding (Muse Spark) plus segmentation (SAM 3.1 via Meta Model API), each doing something the other can't. Not a wrapper a regular coding agent could fake.
- The participant guide warns "simple image analyzers" don't count. This clears that bar as long as the demo actually produces a guide: real keyframes, real segmented parts, real annotated steps.
- Footage must be owned or properly licensed. Shoot a short clip for this or use footage with clear permission.

## Pipeline

| Stage | Tool | Output |
| --- | --- | --- |
| Ingest | ffmpeg | frames + audio/transcript |
| Step & keyframe selection | Muse Spark | 6-8 keyframes, part names, one line of instruction per step |
| Segmentation | SAM 3.1 (Meta Model API) | masks for the named parts on each keyframe |
| Guide rendering | OpenCV | outlines, dimmed background, numbered steps, 2x zoom insets |
| Output | static HTML | scrollable guide page |

## MVP (what "done" means)

- One 30-90s clip in, one correct-looking guide page out.
- 6-8 steps, each with an annotated image and one sentence of instruction.
- Runs end-to-end from a single command.

Stretch, only if ahead: tools list per guide, difficulty/time estimate, PDF export, a second device category.

## Milestones

- **Nov 1**: repo + this plan. Pick test footage. Spike: Muse Spark returns structured keyframe picks (timestamps, part names, step text) for one clip.
- **Nov 2**: SAM 3.1 masks on the chosen keyframes. OpenCV overlay renderer. First ugly-but-real full guide.
- **Nov 3**: polish the rendering and guide page, run a second clip, record the demo.
- **Nov 4**: buffer for breakage. Submit before 9 PM ET.

## Cost guardrails

- Around $148 of Meta API credits are on the account.
- Meta's spend limit only sends an email alert; it is not a hard cap. The keyframe-first design keeps usage small, but check the dashboard before any heavy batch runs.

## Open questions

- Submission mechanics on Cerebral Valley (form, repo link, demo video?) - confirm on the event dashboard before Nov 4.
- Teammate eligibility: a support email about adding a friend is still unanswered; solo is the default until it lands.
