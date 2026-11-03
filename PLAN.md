# teardown - build plan

Meta Global AI Developer Hackathon 2026. Indie track, theme "Build for Your World".
Facts below verified against the live participant guide (cerebralvalley.ai/e/meta-ai-developer-hackathon/details) on Nov 1, 2026.

## The one-sentence version

Repair footage in, illustrated step-by-step repair guide out.

## Deadline and submission

- Submissions due **Wed Nov 4, 9:00 PM EST** via the Cerebral Valley platform - that is **Thu Nov 5, 2:00 AM Morocco time**. Late submissions are not considered.
- Submission needs: this repo **public**, a **3-minute demo video**, and everyone who worked on it listed. One submission per team.
- Hackathon rules require the repo to be public at submission. The repo is private for now; flipping visibility is the owner's call, do it before submitting.
- New work only: the demo and submission must clearly show what was built during the event (Oct 27 - Nov 4).

## Judging (stage-two rubric, 0-10 scale)

- Impact 30% - real-world potential, fit to a problem statement.
- Use of Meta AI Tooling 25% - creative use beyond a basic integration.
- Technical Depth & Execution 20%.
- Demo 25% - working, impressive, the video is genuinely cool to watch.

Stage one is pass/fail: project must fit a theme and actually use the Meta Model API and/or Meta open-weight models.

## Why this fits

- It needs real Meta model capability: transcription (Muse Voice Transcribe), video understanding (Muse Spark), and segmentation (SAM 3.1 via Meta Model API), each doing something the others can't. Not a wrapper a regular coding agent could fake.
- The guide's anti-project list includes "Simple Image Analyzers". This clears that bar as long as the demo actually produces a guide: real keyframes, real segmented parts, real annotated steps.
- Disqualification rule: no code, data, or assets you don't have rights to. Shoot a short repair clip or use footage with clear permission.

## Pipeline

| Stage | Tool | Output |
| --- | --- | --- |
| Ingest | ffmpeg | frames + audio |
| Transcript | Muse Voice Transcribe | step narration text |
| Step & keyframe selection | Muse Spark | one keyframe per narrated step (the prompt asks for 15-40; the web cap is 35) |
| Segmentation | SAM 3.1 (Meta Model API) | masks for the named parts on each keyframe |
| Guide rendering | OpenCV | outlines, dimmed background, numbered steps, 2x zoom insets |
| Output | static HTML | scrollable guide page |

## MVP (what "done" means)

- One narrated clip in, one guide page out.
- Each step has an image, a window-snapped time, and short bullets.
- Runs end-to-end from `python -m teardown clip.mp4 --i-accept-api-cost`. `--mock` does the same path with no API calls.

Stretch, only if ahead: tools list per guide, difficulty/time estimate, PDF export, a second device category.

## Milestones

- **Nov 1**: repo + this plan. Pick test footage. Spike: Muse Spark returns structured keyframe picks (timestamps, part names, step text) for one clip.
- **Nov 2**: SAM 3.1 masks on the chosen keyframes. OpenCV overlay renderer. First ugly-but-real full guide.
- **Nov 3**: polish the rendering and guide page, run a second clip, record the 3-minute demo video.
- **Nov 4**: buffer for breakage. Flip the repo public, submit on the CV platform before 9 PM EST.

## Cost guardrails

- Around $148 of the $150 Meta API credits remained as of Oct 28 (dashboard usage display lags up to an hour). That figure is a point-in-time note, not a live balance.
- Using the API at all requires a card on the Meta developer account, and the "Spend Limit" on the Billing page is a notification, not a hard cap. The web app and the CLI (when `LEDGER_GITHUB_TOKEN` is set) keep their own ledger and reserve a worst case before each job. Check the Billing page before any heavy batch runs.

## Open questions

- Teammate eligibility: a support email about adding a friend is still unanswered; solo is the default until it lands. Teams cap at 4, everyone must be individually accepted.
- Repo visibility is still the owner's call before submission. The tree ships an MIT [LICENSE](LICENSE); swap it if you want a different one.
