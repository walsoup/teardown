# teardown

Upload a video of someone disassembling a device (an iMac, a phone, whatever) and get back a step-by-step visual repair guide - a clean keyframe per step, every part outlined and labeled, in the style of an iFixit guide.

Being built for the Meta Global AI Developer Hackathon (Oct 27 - Nov 4, 2026, Indie track).

## How it works

1. `ingest` pulls the audio track (for transcription) and probes the clip with ffmpeg.
2. Muse Voice Transcribe turns the audio into a TIMED transcript: the endpoint returns no timestamps, so the audio is transcribed in 30-second windows and each window carries its known offset.
3. Muse Spark watches the clip plus the timed transcript and plans the guide steps, anchoring every step to a verbatim narration quote. Spark cannot reliably judge time from video alone, so the plan is then verified mechanically: each anchor quote must appear in the transcript window that contains it, and the step time snaps to that window. A bad step is dropped on its own. The prompt asks for 15-40 steps; the web demo caps a guide at 35. The offline `--mock` plan has 6 steps.
4. SAM 3.1 (via the Meta Model API) segments the named part on each keyframe.
5. An OpenCV pass draws the guide look: part outlines, dimmed background, numbered steps, 2x zoom insets.
6. Output is a static guide page (`output/guide.html`) that scrolls like a real repair manual.

Keyframe-first is the whole trick: segmenting one frame per step instead of the full video is cheaper, faster, and more reliable. Times on the page are labeled "about mm:ss (±30s)" because the transcript has no word timestamps.

## Usage

```bash
pip install -r requirements.txt   # needs ffmpeg on PATH too
export MODEL_API_KEY=...          # Model API dashboard > API keys
python -m teardown path/to/clip.mp4 --i-accept-api-cost --attribution "Creator, license, source URL"
```

A real run refuses to start without `--i-accept-api-cost`. Clips longer than `TEARDOWN_MAX_DURATION` (default 20 minutes) also need `--allow-long`. When `LEDGER_GITHUB_TOKEN` is set, the CLI reserves and settles on the same ledger as the web demo. Without that token it prints a warning and spends the key unmetered.

Set `TEARDOWN_SPARK_MODEL` to override the planning model (default `muse-spark-1.3`,
e.g. `muse-spark-1.3-contributor` for the cheaper contributor tier). Note the contributor
tier lets Meta use submitted content to train its models - only send footage you own or
have explicit permission for.

`python -m teardown clip.mp4 --mock` runs the whole pipeline with canned steps and a synthetic mask - no API calls, no credit spent. Use it to test ingest, rendering and the guide page. `pytest` runs the offline suite (see `.github/workflows/test.yml`). Dev packages live in `requirements-dev.txt`.

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
  clean frames. A simplified-noun retry exists for experiments (`allow_retry=True`)
  and would set `retried=True`, but the pipeline default does not send that second query.
- Drawn-animation synthetic clip (flat colors): Spark planned correct steps with
  and without caption text (one clip each), SAM returned zero matches on all
  frames tried - drawn graphics appear to be a hard input for it.
- One AI-generated photoreal still (muse-image-1.0): SAM matched "battery" at
  0.84 and missed "battery connector" on that still. That still is not in the repo.
- `scripts/generate_synth.py` writes PNG frames (needs opencv). It muxes an mp4
  only when you pass `--video`. `--no-captions` leaves the labels off.

## Web app

`python web/app.py` serves the pipeline as a small site: upload an mp4 or paste a
YouTube link, watch it process, then read the guide with per-step timestamps
that seek the video, plus a print-PDF export. The HTTP server is the standard
library. Transcription, planning, and segmentation use the packages in
`requirements.txt`.

    export MODEL_API_KEY=...
    python web/app.py            # http://127.0.0.1:8377

The process binds to `127.0.0.1` unless `HOST` is set. A non-loopback bind
refuses to start without `TD_COOKIE_SECRET`, so a restart does not orphan
guides behind a new random cookie key. `POST /jobs` checks `Origin` and a CSRF
token, and it ignores `X-Forwarded-For` unless the peer is listed in
`TEARDOWN_TRUSTED_PROXY`.

### Docker

The image runs as a non-root user and expects the cookie secret because it
binds `0.0.0.0`:

```bash
docker build -t teardown .
docker run --rm -p 8377:8377 \
  -e TD_COOKIE_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  -e MODEL_API_KEY="$MODEL_API_KEY" \
  -e LEDGER_GITHUB_TOKEN="$LEDGER_GITHUB_TOKEN" \
  teardown
```

Headless Chromium prints the PDF. Set `TEARDOWN_NO_PDF=1` if the container
cannot start Chromium. A container health check requests `http://127.0.0.1:8377/`.

## Status

A development session described a 19-minute laptop disassembly that produced a
long ordered guide. That run's frames and transcript are not in this tree, so
this README does not treat "23/23 anchors" or a manual frame audit as something
you can re-check here. What the code does now: step times snap to the transcript
window that contains the anchor quote, the guide labels them "about mm:ss (±30s)",
and a missed segmentation is stamped "not highlighted" instead of a clean frame
that looks finished. Small parts and low-resolution frames remain the weak spot.

`demo/backup/` is an offline `--mock` guide rendered from a local clip, so the
page can be opened with no API key. It is not a recording of a live model run.
A live demo still needs a narrated mp4 on disk: YouTube can answer 403 from a
datacenter address, and the upload page says so.

The web app answers HTTP Range requests with 206 so the guide player can seek.

### Superseded results

Earlier long-video plans (a 28-step and a 24-step version) were built from an
UNTIMED transcript. Spark had no source of truth for time and allocated step
timestamps across the duration instead of deriving them from the footage -
review caught frames that no longer matched their step's action (for example
a battery step framed after the panels were already off). Any coverage or
accuracy claims based on those runs are superseded by the window-snapping
checks above, not by an archived 19-minute artifact.

## License

MIT. See [LICENSE](LICENSE).
