"""teardown web app - upload or paste a link, get an illustrated guide.

Real wiring only: jobs run the actual teardown pipeline (transcribe, plan,
segment, render). Status shown is the pipeline's real stage. No mock states.
"""
import html as html_mod
import json, os, re, subprocess, sys, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("TEARDOWN_DATA", os.path.join(ROOT, "data"))
PIPELINE = os.environ.get("TEARDOWN_PKG", os.path.join(ROOT, ".."))  # repo root
KEY_FILE = os.environ.get("TEARDOWN_KEY_FILE")  # fallback if MODEL_API_KEY is not set

JOBS = {}


def load_plan(job_id):
    p = os.path.join(DATA, job_id, "plan.json")
    return json.load(open(p)) if os.path.exists(p) else None


def run_pipeline(job_id, video_path):
    JOBS[job_id]["status"] = "processing"
    try:
        sys.path.insert(0, PIPELINE)
        from teardown import ingest, steps as steps_mod, segment as segment_mod, render
        from teardown.meta_api import MetaApi
        if not os.environ.get("MODEL_API_KEY"):
            os.environ["MODEL_API_KEY"] = open(KEY_FILE).read().strip()
        api = MetaApi()
        out = os.path.join(DATA, job_id)
        os.makedirs(os.path.join(out, "steps"), exist_ok=True)
        JOBS[job_id]["stage"] = "extracting audio"
        wav = ingest.extract_audio(video_path, os.path.join(out, "audio.wav"))
        JOBS[job_id]["stage"] = "transcribing"
        transcript = api.transcribe_timed(wav) if wav else []
        JOBS[job_id]["stage"] = "watching video and planning steps"
        video_id = api.upload_file(video_path)
        duration = ingest.probe_duration(video_path)
        plan = steps_mod.plan_steps(api, video_id, transcript, duration)
        n = len(plan["steps"])
        for i, s in enumerate(plan["steps"]):
            JOBS[job_id]["stage"] = f"choosing frames ({i + 1}/{n})"
            # candidate frames around the step timestamp; Spark picks the clearest
            cands = []
            for j, dt in enumerate((-8, -4, 0, 4, 8)):
                ct = max(0.0, s["t"] + dt)
                cp = os.path.join(out, "steps", f"cand-{i + 1}-{j}.png")
                ingest.extract_frame(video_path, ct, cp)
                cands.append((ct, cp))
            pick = steps_mod.pick_frame(api, cands, s["part"], s["title"])
            frame = cands[pick][1]
            JOBS[job_id]["stage"] = f"highlighting parts ({i + 1}/{n})"
            hit = segment_mod.segment_part(api, frame, s["part"])  # fail-closed
            if hit:
                render.annotate(frame, tuple(hit["bounds"]), hit["mask"], i + 1,
                                os.path.join(out, "steps", f"step-{i + 1}.png"))
                s["image"] = f"steps/step-{i + 1}.png"
            else:
                s["image"] = f"steps/cand-{i + 1}-{pick}.png"
            s["segmented"] = bool(hit)
        json.dump(plan, open(os.path.join(out, "plan.json"), "w"), indent=1)
        JOBS[job_id].update(status="done", device=plan["device"], steps=n)
    except Exception as e:
        JOBS[job_id].update(status="error", error=str(e)[:300])


def build_pdf(job_id):
    """Compact print layout -> PDF via headless chrome. Returns pdf path or None."""
    plan = load_plan(job_id)
    if not plan:
        return None
    steps = plan["steps"]
    esc = html_mod.escape

    def ts(t):
        return f"~{int(t // 60)}:{int(t % 60):02d}"

    blocks = []
    for i, s in enumerate(steps):
        n = i + 1
        detail = []
        if s.get("fasteners"):
            detail.append(f'<div class=dt><b>Fasteners:</b> {esc(s["fasteners"])}</div>')
        if s.get("connectors"):
            detail.append(f'<div class=dt><b>Connectors:</b> {esc(s["connectors"])}</div>')
        caut = f'<div class=caution>{esc(s["caution"])}</div>' if s.get("caution") else ""
        hl = ' &middot; <b class=hl>part highlighted</b>' if s.get("segmented") else ""
        blocks.append(f"""
<div class=step>
  <div class=imgcol><img src="steps-img/{n}.png"></div>
  <div class=txtcol>
    <div class=head><span class=num>{n}</span><h2>{esc(s['title'])}</h2></div>
    <div class=meta>{ts(s['t'])} &middot; {esc(s.get('tool') or 'fingers')}{hl}</div>
    <p>{esc(s['instruction'])}</p>
    {''.join(detail)}
    {caut}
  </div>
</div>""")
    tools_list = "".join(f"<li>{esc(t)}</li>" for t in plan.get("tools_summary", []))
    page = f"""<!doctype html><html><head><meta charset=utf-8><style>
@page {{ size: A4; margin: 14mm 14mm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: "Newsreader", Georgia, serif; color:#26261f; }}
.cover h1 {{ font-size: 30px; color:#2f4632; margin-bottom: 4mm; }}
.cover h1 .dot {{ color:#b3562e; }}
.sub {{ font-size: 13px; color:#6b6b5f; margin-bottom: 5mm; }}
.banner {{ border:1px solid #d9d4c5; border-left:3px solid #b3562e; padding: 3mm 4mm; font-size: 11px; color:#6b6b5f; margin-bottom: 5mm; }}
.tools {{ border-top:1px solid #d9d4c5; padding-top: 3mm; margin-bottom: 2mm; }}
.tools h3 {{ font-size: 13px; color:#2f4632; margin-bottom: 1.5mm; }}
.tools ul {{ list-style: none; font-size: 12px; }}
.tools li:before {{ content: "-  "; color:#b3562e; }}
.step {{ display: grid; grid-template-columns: 47% 1fr; gap: 5mm; border-top: 1px solid #d9d4c5; padding: 4mm 0; page-break-inside: avoid; }}
.imgcol img {{ width: 100%; border:1px solid #d9d4c5; }}
.head {{ display:flex; align-items:center; gap: 3mm; margin-bottom: 1.5mm; }}
.num {{ flex:none; width: 7.5mm; height: 7.5mm; border-radius: 50%; background:#2f4632; color:#fff; font-family: "Inter", system-ui, sans-serif; font-size: 11px; text-align:center; line-height: 7.5mm; }}
h2 {{ font-size: 14px; color:#2f4632; }}
.meta {{ font-size: 11px; color:#6b6b5f; margin-bottom: 2mm; }}
.hl {{ color:#b3562e; }}
p {{ font-size: 11.5px; line-height: 1.45; margin-bottom: 2mm; }}
.dt {{ font-size: 10.5px; color:#444a42; margin-bottom: 1mm; }}
.dt b {{ color:#2f4632; }}
.caution {{ border-left: 2px solid #b3562e; padding-left: 2mm; font-size: 10.5px; color:#b3562e; margin-top: 2mm; }}
</style></head><body>
<div class=cover>
  <h1>{esc(plan['device'])}<span class=dot>.</span></h1>
  <div class=sub>Teardown and reassembly guide &middot; {len(steps)} steps &middot; generated from video footage</div>
  <div class=banner>Demo output &mdash; not validated repair instructions. Follow manufacturer service manuals for actual repairs. Fasteners and connectors are highlighted where detected.</div>
  <div class=tools>
    <h3>Tools required</h3>
    <ul>{tools_list}</ul>
  </div>
</div>
{''.join(blocks)}
</body></html>"""
    jd = os.path.join(DATA, job_id)
    imgdir = os.path.join(jd, "steps-img")
    os.makedirs(imgdir, exist_ok=True)
    for i, s in enumerate(steps):
        srcimg = os.path.join(jd, s["image"])
        dst = os.path.join(imgdir, f"{i + 1}.png")
        if os.path.exists(srcimg) and not os.path.exists(dst):
            os.link(srcimg, dst)
    hp = os.path.join(jd, "guide-print.html")
    open(hp, "w").write(page)
    pdf = os.path.join(jd, "guide.pdf")
    subprocess.run(["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
                    f"--print-to-pdf={pdf}", "--no-pdf-header-footer", hp],
                   capture_output=True, timeout=120)
    return pdf if os.path.exists(pdf) else None


CSS = """
:root {
  --paper: #f7f6f2;
  --paper-card: #ffffff;
  --paper-hover: #efeee8;
  --paper-active: #e7e6e0;
  --forest: #2f4632;
  --forest-hover: #243827;
  --terracotta: #b3562e;
  --terracotta-hover: #9c4925;
  --hair: #e0dfd6;
  --hair-dark: #c7c6bd;
  --mut: #707567;
  --body-ink: #26261f;

  /* Compatibility aliases */
  --green: #2f4632;
  --green-hover: #243827;
  --terra: #b3562e;
  --ink: #2f4632;

  --font-serif: "Newsreader", Georgia, serif;
  --font-sans: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-sans);
  background: var(--paper);
  color: var(--body-ink);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}



.mono-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
  font-variant-numeric: tabular-nums;
}

.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-style: normal;
  font-size: 18px;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  word-wrap: normal;
  direction: ltr;
  -webkit-font-feature-settings: 'liga';
  -webkit-font-smoothing: antialiased;
  vertical-align: middle;
}

a {
  color: var(--forest);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

.mut {
  color: var(--mut);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
}

.dot {
  color: var(--terracotta);
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--forest);
  color: var(--forest);
  border-radius: 6px;
  padding: 8px 18px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  background: transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  user-select: none;
}

.pill:hover {
  background: var(--paper-hover);
  text-decoration: none;
}

.pill.solid {
  background: var(--forest);
  color: #fff;
  border-color: var(--forest);
}

.pill.solid:hover {
  background: var(--forest-hover);
  border-color: var(--forest-hover);
}

.card {
  border: 1px solid var(--hair);
  background: var(--paper-card);
  border-radius: 8px;
}

.err {
  background: #fdf0ec;
  border: 1px solid #eec4b8;
  color: var(--terracotta);
  padding: 12px 16px;
  border-radius: 6px;
  font-family: var(--font-sans);
  font-size: 13px;
  margin-bottom: 20px;
}

/* LANDING PAGE (INDEX) STYLES */
.landing-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--paper);
}

.landing-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--paper);
  border-bottom: 1px solid var(--hair);
}

.landing-container {
  width: 100%;
  max-width: 780px;
  margin: 0 auto;
  padding: 40px 20px 60px 20px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.landing-hero {
  text-align: center;
  margin-bottom: 32px;
}

.landing-headline {
  font-family: var(--font-serif);
  font-size: 38px;
  line-height: 1.2;
  color: var(--forest);
  letter-spacing: -0.02em;
  font-weight: 400;
  margin-bottom: 12px;
}

.landing-subhead {
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.5;
  color: var(--mut);
  max-width: 540px;
  margin: 0 auto;
}

.err, .landing-error {
  color: var(--terra);
  font-family: var(--font-sans);
  font-size: 13px;
  margin-bottom: 16px;
}

.landing-card {
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 12px;
  padding: 28px;
  margin-bottom: 16px;
}

.drop-zone {
  border: 1.5px dashed var(--hair);
  border-radius: 8px;
  padding: 36px 20px;
  text-align: center;
  background: var(--paper);
  transition: border-color 0.15s ease, background 0.15s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.drop-zone:hover, .drop-zone.drag-over {
  border-color: var(--forest);
  background: var(--paper-hover);
}

.drop-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 20px;
  color: var(--forest);
  font-weight: 500;
}

.drop-sub {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
  margin-bottom: 6px;
}

.drop-browse-pill {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 999px;
  color: var(--forest);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.drop-browse-pill:hover {
  border-color: var(--forest);
  background: var(--paper-hover);
}

.landing-or-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 22px 0;
}

.or-line {
  flex: 1;
  height: 1px;
  background: var(--hair);
}

.or-text {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
  text-transform: lowercase;
}

.url-input-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.url-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
}

.url-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.url-input-wrap {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}

.url-icon {
  position: absolute;
  left: 14px;
  color: var(--mut);
  font-size: 18px;
  pointer-events: none;
}

.url-input {
  width: 100%;
  padding: 11px 16px 11px 40px;
  border: 1px solid var(--hair);
  border-radius: 999px;
  background: var(--paper);
  color: var(--body-ink);
  font-family: var(--font-sans);
  font-size: 13.5px;
  outline: none;
  transition: border-color 0.15s ease;
}

.url-input:focus {
  border-color: var(--forest);
}

.submit-pill {
  padding: 11px 22px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.landing-subbar {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  margin-bottom: 36px;
  text-align: center;
}

.recent-guides-section {
  margin-top: 10px;
  margin-bottom: 40px;
}

.recent-guides-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--hair);
  padding-bottom: 8px;
  margin-bottom: 14px;
}

.recent-guides-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 20px;
  color: var(--forest);
  font-weight: 400;
}

.jobs-list {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
  overflow: hidden;
}

.job-card {
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--hair);
  background: transparent;
  transition: background 0.15s ease;
  margin: 0;
  border-radius: 0;
}

.job-card:last-child {
  border-bottom: none;
}

.job-card:hover {
  background: var(--paper-hover);
}

.job-card .pill {
  border: none;
  padding: 0;
  border-radius: 0;
  font-size: 14px;
  font-weight: 500;
  display: inline-block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-card {
  gap: 12px;
}

.job-card > .mut {
  flex-shrink: 0;
  white-space: nowrap;
}

.job-card .mut {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
}

.landing-footer {
  text-align: center;
  margin-top: auto;
  padding-top: 24px;
  border-top: 1px solid var(--hair);
}

.footer-brand {
  font-family: var(--font-serif);
  font-size: 20px;
  color: var(--forest);
  margin-bottom: 6px;
}

@media (max-width: 600px) {
  .landing-headline {
    font-size: 28px;
  }
  .landing-card {
    padding: 18px;
  }
  .drop-zone {
    padding: 24px 14px;
  }
  .url-input-row {
    flex-direction: column;
    align-items: stretch;
  }
  .submit-pill {
    width: 100%;
    justify-content: center;
  }
}

/* APP HEADER & SUBBAR */
.app-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--paper);
  border-bottom: 1px solid var(--hair);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand {
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 500;
  color: var(--forest);
  text-decoration: none;
  letter-spacing: -0.3px;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 0 16px;
  min-width: 0;
}

.header-device {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 16px;
  color: var(--forest);
  font-weight: 500;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-pdf {
  font-size: 12px;
  padding: 6px 14px;
  gap: 4px;
}

.app-subbar {
  background: #ede6d4;
  border-bottom: 1px solid var(--hair);
  padding: 6px 20px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--mut);
  text-align: center;
}

/* VIDEO PLAYER & TIMELINE */
.player-pane {
  display: flex;
  flex-direction: column;
}

.video-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
  border: 1px solid var(--hair);
  border-bottom: none;
  overflow: hidden;
  max-height: 38vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-frame video {
  width: 100%;
  height: 100%;
  max-height: 38vh;
  display: block;
  object-fit: contain;
  background: #000;
}

@media (max-height: 480px) {
  .video-frame { max-height: 30vh !important; }
  .video-frame video { max-height: 30vh !important; }
}

.video-loading {
  position: absolute;
  top: 10px;
  right: 10px;
  background: var(--paper-card);
  color: var(--mut);
  border: 1px solid var(--hair);
  border-radius: 999px;
  padding: 3px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  pointer-events: none;
  z-index: 5;
  transition: opacity 0.2s ease;
}

.video-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 24px 20px;
  background: #faf6ee;
  color: var(--mut);
  text-align: center;
  gap: 4px;
}

.v-error-icon {
  color: var(--terracotta);
  font-size: 20px;
  margin-bottom: 2px;
}

.v-error-msg {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 15px;
  color: var(--forest);
}

.v-error-sub {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  max-width: 280px;
  line-height: 1.4;
}

/* TIMELINE CONTAINER & SEGMENTS */
.timeline-container {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--paper-card);
  border: 1px solid var(--hair);
  padding: 10px 14px;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.timeline-step-label {
  color: var(--mut);
}

.timeline-est {
  color: var(--forest);
  font-weight: 600;
}

.progress-bar {
  display: grid;
  grid-template-columns: repeat(27, minmax(0, 1fr));
  gap: 3px;
  width: 100%;
  height: 10px;
  background: transparent;
  border: none;
}

.progress-seg {
  height: 100%;
  border-radius: 2px;
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--hair);
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.progress-seg:hover {
  border-color: var(--forest);
}

.progress-seg.done {
  background: var(--forest);
  border: 1px solid var(--forest);
}

.progress-seg.active {
  background: var(--terracotta);
  border: 1px solid var(--terracotta);
}

/* TELEMETRY CARD */
.telemetry-card {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 8px;
}

.telemetry-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--hair);
}

.telemetry-pct {
  color: var(--terracotta);
  font-weight: 600;
}

.telemetry-middle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.telemetry-step {
  color: var(--forest);
  font-weight: 600;
}

.telemetry-rem {
  color: var(--mut);
}

.telemetry-tray {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--hair);
}

.telemetry-tray-header {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--mut);
}

.telemetry-tray-header .tray-icon {
  font-size: 15px;
  color: var(--terracotta);
}

.telemetry-tray-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.tray-chip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: var(--paper);
  border: 1px solid var(--hair);
  border-radius: 4px;
  padding: 5px 8px;
  font-size: 12px;
}

.tray-chip-tag {
  color: var(--terracotta);
  font-weight: 600;
  font-size: 10px;
  flex-shrink: 0;
  padding-top: 1px;
}

.tray-chip-val {
  color: var(--body-ink);
  line-height: 1.3;
}

.tray-empty {
  color: var(--mut);
  font-size: 11px;
  font-style: italic;
  padding: 4px 0;
}

/* STEP CARD & CONTENTS */
.step-pane {
  display: flex;
  flex-direction: column;
}

.step-card {
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
  padding: 24px;
}

.step-item {
  display: none;
}

.step-item.active {
  display: block;
}

.step-eyebrow-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--hair);
}

.step-badge {
  color: var(--mut);
  font-weight: 500;
  padding: 3px 0;
}

.step-hl-badge {
  display: inline-flex;
  align-items: center;
  color: var(--terracotta);
  font-weight: 600;
}

.step-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 26px;
  line-height: 1.25;
  color: var(--forest);
  margin-bottom: 12px;
}

.step-chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 16px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  background: #ffffff;
  border: 1px solid var(--hair);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--body-ink);
  line-height: 1.2;
  white-space: normal;
  word-break: break-word;
}

.chip-icon {
  font-size: 14px;
  color: var(--forest);
  flex-shrink: 0;
}

.chip-hl {
  border-color: var(--hair-dark);
}

.step-hl {
  color: var(--terracotta);
}

.step-image-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #181917;
  border: 1px solid var(--hair);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  cursor: pointer;
}

.step-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.inspect-btn {
  position: absolute;
  bottom: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--hair);
  border-radius: 999px;
  padding: 3px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--forest);
  cursor: pointer;
  pointer-events: none;
}

.step-desc {
  font-family: var(--font-sans);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--body-ink);
  margin-bottom: 16px;
}

/* HARDWARE & FASTENER REGISTRY BLOCK */
.step-registry {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--paper);
  border: 1px solid var(--hair);
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 16px;
}

.registry-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.registry-icon {
  font-size: 16px;
  color: var(--terracotta);
}

.registry-title {
  color: var(--forest);
  font-weight: 600;
}

.registry-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.registry-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  line-height: 1.4;
}

.registry-type {
  color: var(--forest);
  font-weight: 600;
  font-size: 11px;
  flex-shrink: 0;
  padding-top: 1px;
}

.registry-val {
  color: var(--body-ink);
}

/* CAUTION BOX */
.step-caution {
  border: 1px solid var(--hair);
  border-left: 3px solid var(--terracotta);
  background: #faf3ee;
  padding: 12px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.caution-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.caution-icon {
  color: var(--terracotta);
  font-size: 16px;
}

.caution-eyebrow {
  color: var(--terracotta);
  font-weight: 700;
}

.caution-text {
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
  color: #7c3a1e;
}

/* STEP NAVIGATION */
.step-nav {
  display: flex;
  gap: 10px;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--hair);
  align-items: center;
}

.nav-btn {
  padding: 10px 18px;
  font-size: 13px;
  min-height: 42px;
}

.nav-btn.primary-action {
  flex: 1.4;
}

.nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}

.bookmark-btn {
  width: 42px;
  height: 42px;
  padding: 0;
  flex-shrink: 0;
}

.bookmark-btn.bookmarked {
  background: #ede6d4;
  color: var(--terracotta);
  border-color: var(--terracotta);
}

.step-nav-shortcuts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding: 0 4px;
}

.step-nav-shortcuts kbd {
  padding: 2px 6px;
  border: 1px solid var(--hair);
  border-radius: 4px;
  background: var(--paper);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--forest);
}

/* STEPS DISCLOSURE & RAIL */
.disclosure-pane {
  display: flex;
  flex-direction: column;
}

.steps-disclosure {
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
  overflow: hidden;
}

.disclosure-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: #ede6d4;
  border-bottom: 1px solid var(--hair);
  list-style: none;
  gap: 12px;
  user-select: none;
}

.disclosure-summary::-webkit-details-marker,
.disclosure-summary::marker {
  display: none;
}

.disclosure-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.disclosure-icon {
  font-size: 18px;
  color: var(--forest);
}

.disclosure-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 16px;
  font-weight: 500;
  color: var(--forest);
}

.disclosure-count {
  color: var(--mut);
}

.disclosure-toggle {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--forest);
  font-weight: 600;
  flex-shrink: 0;
}

.steps-index-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--paper);
  border-bottom: 1px solid var(--hair);
}

.search-icon {
  font-size: 18px;
  color: var(--mut);
}

.steps-search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--body-ink);
}

.steps-search-input::placeholder {
  color: var(--mut);
}

.rail-list {
  max-height: 480px;
  overflow-y: auto;
}

.rail-row {
  display: grid;
  grid-template-columns: 28px 60px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hair);
  cursor: pointer;
  background: transparent;
  transition: background 0.1s ease;
  user-select: none;
  outline: none;
}

.rail-row:last-child {
  border-bottom: none;
}

.rail-row:hover {
  background: var(--paper-hover);
}

.rail-row.active {
  background: var(--paper-active);
  border-left: 3px solid var(--terracotta);
  padding-left: 11px;
}

.row-num {
  font-size: 12px;
  font-weight: 600;
  color: var(--forest);
  text-align: center;
}

.rail-row.active .row-num {
  color: var(--terracotta);
}

.row-thumb-wrap {
  width: 60px;
  aspect-ratio: 16 / 9;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--hair);
  background: #181917;
  flex-shrink: 0;
}

.row-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.row-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.row-title {
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 500;
  color: var(--body-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-row.active .row-title {
  font-weight: 600;
  color: var(--forest);
}

.row-meta {
  color: var(--mut);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-icon {
  font-size: 18px;
  line-height: 1;
}

.icon-done {
  color: var(--forest);
}

.icon-active {
  color: var(--terracotta);
}

.icon-pending {
  color: var(--hair-dark);
}

.bookmark-row-indicator {
  color: var(--terracotta);
  font-size: 16px;
}

/* BANNER & FOOTER */
.notice-pane {
  display: flex;
  flex-direction: column;
}

.banner {
  border: 1px solid var(--hair);
  border-left: 3px solid var(--terracotta);
  background: var(--paper-card);
  padding: 12px 16px;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  line-height: 1.5;
  border-radius: 0 6px 6px 0;
}

.footer-pane {
  padding-top: 12px;
  text-align: center;
}

.app-footer {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--mut);
}

/* MOBILE STICKY BOTTOM THUMB BAR */
.mobile-thumb-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: #ffffff;
  border-top: 1px solid var(--hair);
  padding: 10px 16px;
  padding-bottom: max(10px, env(safe-area-inset-bottom, 10px));
  display: flex;
  align-items: center;
  gap: 10px;
}

.thumb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 999px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  user-select: none;
}

.thumb-prev {
  background: transparent;
  border: 1px solid var(--hair);
  color: var(--forest);
  height: 42px;
  padding: 0 16px;
}

.thumb-prev:disabled {
  opacity: 0.35;
  pointer-events: none;
}

.thumb-complete-next {
  flex: 1;
  background: var(--forest);
  border: 1px solid var(--forest);
  color: #fff;
  height: 42px;
  padding: 0 18px;
  font-weight: 600;
}

#thumb-complete-next-lbl { white-space: nowrap; font-size: 12.5px; }
.thumb-complete-next { min-width: 0; }
.thumb-complete-next:active {
  background: var(--forest-hover);
}

.thumb-bookmark {
  width: 42px;
  height: 42px;
  padding: 0;
  border-radius: 50%;
  background: transparent;
  border: 1px solid var(--hair);
  color: var(--forest);
  flex-shrink: 0;
}

.thumb-bookmark.bookmarked {
  background: #ede6d4;
  color: var(--terracotta);
  border-color: var(--terracotta);
}

/* FULLSCREEN IMAGE OVERLAY */
.image-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(20, 22, 20, 0.9);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.image-overlay-box {
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 8px;
  max-width: 95vw;
  max-height: 95vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.image-overlay-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hair);
  background: var(--paper);
}

.image-overlay-close-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--forest);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 50%;
}

.image-overlay-close-btn:hover {
  background: var(--paper-hover);
}

.image-overlay-body {
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  cursor: zoom-out;
}

.image-overlay-body img {
  max-width: 90vw;
  max-height: 80vh;
  object-fit: contain;
  display: block;
  border: 1px solid var(--hair);
}

/* RESPONSIVE LAYOUTS */
@media (max-width: 1023px) {
  .step-nav, .step-nav-shortcuts { display: none; }
  .layout-container {
    padding: 0 0 90px 0;
  }
  .layout {
    display: flex;
    flex-direction: column;
  }
  .left-col, .right-col {
    display: contents;
  }
  .player-pane {
    order: 1;
    position: sticky;
    top: 0;
    z-index: 30;
    background: var(--paper);
    width: 100%;
  }
  .timeline-container {
    order: 2;
    border-left: none;
    border-right: none;
  }
  .step-pane {
    order: 3;
    padding: 16px 14px 0 14px;
    scroll-margin-top: calc(min(56.25vw, 38vh) + 64px);
  }
  .telemetry-card {
    display: none;
  }
  .disclosure-pane {
    order: 4;
    padding: 14px 14px 0 14px;
  }
  .notice-pane {
    order: 5;
    padding: 14px 14px 0 14px;
  }
  .footer-pane {
    order: 6;
    padding: 14px 14px 24px 14px;
  }
}

@media (min-width: 1024px) {
  .mobile-thumb-bar {
    display: none !important;
  }
  .layout-container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px 28px 48px;
  }
  .layout {
    display: grid;
    grid-template-columns: 480px 1fr;
    gap: 32px;
    align-items: start;
  }
  .left-col {
    display: flex;
    flex-direction: column;
    position: sticky;
    top: 20px;
    gap: 16px;
  }
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 20px;
    min-width: 0;
  }
  .player-pane {
    position: static;
    width: 100%;
  }
  .steps-disclosure {
    border: 1px solid var(--hair);
  }
  .disclosure-summary {
    pointer-events: none;
    cursor: default;
  }
  .disclosure-toggle {
    display: none;
  }
  .rail-list {
    max-height: calc(100vh - 380px);
    min-height: 260px;
  }
}
"""


INDEX = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>teardown</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">
<style>__CSS__</style>
__REFRESH__</head><body class="landing-page">
<!-- __DEVICE__ -->
<header class="landing-header">
  <div class="header-left">
    <a href="/" class="brand font-serif">teardown<span class="dot">.</span></a>
  </div>
</header>

<div class="landing-container">
  <section class="landing-hero">
    <h1 class="landing-headline font-serif">repair footage in, illustrated guide out</h1>
    <p class="landing-subhead">drop in a teardown video, get an illustrated step-by-step guide</p>
  </section>

  __ERROR__

  <div class="card landing-card">
    <form method="post" action="/jobs" enctype="multipart/form-data" class="landing-form">
      <div class="drop-zone" id="drop-zone">
        <div class="drop-title font-serif">drop a video here</div>
        <p class="drop-sub mono-label">mp4 or mov, up to 2 GB</p>
        <label for="f" class="pill drop-browse-pill">
          <span class="material-symbols-outlined" style="font-size:16px;">folder_open</span>
          <span id="browse-label">browse files</span>
          <input id="f" type="file" name="video" accept="video/mp4,video/quicktime,video/*" style="display:none;">
        </label>
      </div>

      <div class="landing-or-divider">
        <span class="or-line"></span>
        <span class="or-text mono-label">or</span>
        <span class="or-line"></span>
      </div>

      <div class="url-input-section">
        <div class="url-input-row">
          <div class="url-input-wrap">
            <span class="material-symbols-outlined url-icon">link</span>
            <input type="text" id="url-input" name="url" placeholder="paste a youtube link" class="url-input">
          </div>
          <button class="pill solid submit-pill" type="submit">
            <span>build guide</span>
            <span class="material-symbols-outlined" style="font-size:16px;">arrow_forward</span>
          </button>
        </div>
      </div>
    </form>
  </div>

  <p class="landing-subbar">generated guides are a private test draft - not validated repair instructions</p>

  <section class="recent-guides-section">
    <div class="recent-guides-header">
      <h2 class="recent-guides-title font-serif">recent guides</h2>
    </div>
    <div class="jobs-list">
      __JOBS__
    </div>
  </section>

  <footer class="landing-footer">
    <div class="footer-brand font-serif">teardown<span class="dot">.</span></div>
    <p class="app-footer">private test output - generated by teardown</p>
  </footer>
</div>

<script>
const fileInput = document.getElementById('f');
if (fileInput) {
  fileInput.addEventListener('change', function(){
    const b = document.getElementById('browse-label');
    if (b) b.textContent = this.files[0] ? this.files[0].name : 'browse files';
  });
}
const dropZone = document.getElementById('drop-zone');
if (dropZone && fileInput) {
  ['dragenter', 'dragover'].forEach(function(name) {
    dropZone.addEventListener(name, function(e) {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
  });
  ['dragleave', 'drop'].forEach(function(name) {
    dropZone.addEventListener(name, function(e) {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
    });
  });
  dropZone.addEventListener('drop', function(e) {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      const b = document.getElementById('browse-label');
      if (b) b.textContent = fileInput.files[0].name;
    }
  });
}
</script>
</body></html>"""


GUIDE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>__DEVICE__ - teardown</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">
<style>__CSS__</style></head><body>
<header class="app-header">
  <div class="header-left">
    <a href="/" class="brand">teardown<span class="dot">.</span></a>
  </div>
  <div class="header-center">
    <span class="header-device">__DEVICE__</span>
  </div>
  <div class="header-right">
    <a class="pill header-pdf" href="/jobs/__JOB__/guide.pdf" download="teardown-guide.pdf">
      <span class="material-symbols-outlined" style="font-size:16px; margin-right:4px;">download</span>PDF
    </a>
  </div>
</header>
<div class="app-subbar">Demo output - not validated repair instructions</div>

<main class="layout-container">
  <div class="layout">
    <div class="left-col">
      <div class="player-pane">
        <div class="video-frame">
          <video id="v" controls playsinline preload="metadata" poster="__POSTER__" src="/jobs/__JOB__/video.mp4"></video>
          <div id="v-loading" class="video-loading" aria-live="polite">loading footage&hellip;</div>
          <div id="v-error" class="video-error" style="display:none;" role="alert">
            <span class="v-error-icon">&#9888;</span>
            <p class="v-error-msg">Video footage unavailable</p>
            <p class="v-error-sub">Use the illustrated repair steps below.</p>
          </div>
        </div>
        <div class="timeline-container">
          <div class="timeline-header">
            <span class="mono-label timeline-step-label" id="timeline-step-label">Step 01 of __NSTEPS__ - active</span>
            <span class="mono-label timeline-est" id="timeline-est">Est. remaining 19m 20s</span>
          </div>
          <div class="progress-bar" id="progress-bar" aria-label="Step progress">
            __PROGRESS__
          </div>
        </div>
      </div>
      <div class="telemetry-card card">
        <div class="telemetry-top">
          <div class="telemetry-title mono-label">Disassembly telemetry</div>
          <div class="telemetry-pct mono-label" id="telemetry-pct">0% completed</div>
        </div>
        <div class="telemetry-middle">
          <div class="telemetry-step mono-label" id="telemetry-step">Step 01 of __NSTEPS__</div>
          <div class="telemetry-rem mono-label" id="telemetry-rem">Est. remaining 19m 20s</div>
        </div>
        <div class="telemetry-tray">
          <div class="telemetry-tray-header mono-label">
            <span class="material-symbols-outlined tray-icon">tune</span>
            <span>Active step hardware</span>
          </div>
          <div class="telemetry-tray-body" id="telemetry-tray-body">
            <!-- Dynamic update via JS -->
          </div>
        </div>
      </div>
    </div>

    <div class="right-col">
      <div class="step-pane" id="step-pane">
        <div class="step-card">
          <div id="step-cards-container">
            __STEPS__
          </div>
          <div class="step-nav">
            <button type="button" class="pill nav-btn" id="prev-btn" onclick="prevStep()" disabled>
              <span class="material-symbols-outlined" style="font-size:16px; margin-right:4px;">arrow_back</span> Prev
            </button>
            <button type="button" class="pill solid nav-btn primary-action" id="complete-next-btn" onclick="completeAndNext()">
              <span id="complete-next-lbl">Complete &amp; Next: Step 02</span>
              <span class="material-symbols-outlined" style="font-size:16px; margin-left:4px;">arrow_forward</span>
            </button>
            <button type="button" class="pill nav-btn" id="next-btn" onclick="nextStep()" title="Next without completing">
              <span>Next</span>
              <span class="material-symbols-outlined" style="font-size:16px; margin-left:4px;">arrow_forward</span>
            </button>
            <button type="button" class="pill bookmark-btn" id="bookmark-btn" onclick="toggleBookmark()" title="Bookmark step">
              <span class="material-symbols-outlined" id="bookmark-icon">bookmark_border</span>
            </button>
          </div>
          <div class="step-nav-shortcuts">
            <span class="mono-label">Keyboard:</span>
            <span class="mono-label"><kbd>J</kbd> prev &middot; <kbd>K</kbd> next</span>
          </div>
        </div>
      </div>

      <div class="disclosure-pane">
        <details id="steps-disclosure" class="steps-disclosure">
          <summary class="disclosure-summary">
            <div class="disclosure-meta">
              <span class="material-symbols-outlined disclosure-icon">list_alt</span>
              <span class="disclosure-title">Complete Disassembly Manual</span>
              <span class="disclosure-count mono-label">__NSTEPS__ steps &middot; ~&plusmn;30s</span>
            </div>
            <span class="disclosure-toggle">Hide list ▴</span>
          </summary>
          <div class="steps-index-content">
            <div class="steps-index-search-bar">
              <span class="material-symbols-outlined search-icon">search</span>
              <input type="text" id="steps-search-input" class="steps-search-input" placeholder="Search procedure, screw, or tool..." oninput="filterSteps(this.value)">
            </div>
            <div class="rail-list" id="rail-list">
              __RAIL__
            </div>
          </div>
        </details>
      </div>

      <div class="notice-pane">
        <div class="banner">Auto-generated demo output - not validated repair instructions. Highlights appear only where the segmentation matched the named part directly; other steps show the plain frame.</div>
      </div>
      <footer class="footer-pane">
        <p class="app-footer">private test output - generated by teardown</p>
      </footer>
    </div>
  </div>
</main>

<!-- MOBILE STICKY BOTTOM THUMB BAR -->
<aside class="mobile-thumb-bar" id="mobile-thumb-bar">
  <button type="button" class="thumb-btn thumb-prev" id="thumb-prev-btn" onclick="prevStep()" aria-label="Previous step">
    <span class="material-symbols-outlined">arrow_back</span>
    <span>Prev</span>
  </button>
  <button type="button" class="thumb-btn thumb-complete-next" id="thumb-complete-next-btn" onclick="completeAndNext()">
    <span id="thumb-complete-next-lbl">Complete &amp; Next: Step 02</span>
    <span class="material-symbols-outlined">arrow_forward</span>
  </button>
  <button type="button" class="thumb-btn thumb-bookmark" id="thumb-bookmark-btn" onclick="toggleBookmark()" title="Bookmark step">
    <span class="material-symbols-outlined" id="thumb-bookmark-icon">bookmark_border</span>
  </button>
</aside>

<!-- FULLSCREEN IMAGE OVERLAY -->
<div id="image-overlay" class="image-overlay" style="display:none;" onclick="if(event.target===this)closeImageOverlay()">
  <div class="image-overlay-box">
    <div class="image-overlay-header">
      <span class="mono-label" id="image-overlay-title">STEP PHOTOGRAPHIC REFERENCE</span>
      <button type="button" class="image-overlay-close-btn" id="image-overlay-close-btn" onclick="closeImageOverlay()" aria-label="Close fullscreen view">
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>
    <div class="image-overlay-body" onclick="closeImageOverlay()">
      <img id="image-overlay-img" src="" alt="Full resolution inspection view">
    </div>
  </div>
</div>

<script>
const stepTimes = __STEPTIMES__;
const stepHardware = __STEPHARDWARE__;
const totalSteps = stepTimes.length;
let activeStep = 0;

let doneSteps = new Set();
let bookmarkSteps = new Set();

function loadStorage() {
  try {
    const d = localStorage.getItem('td4-done');
    if (d) {
      const arr = JSON.parse(d);
      if (Array.isArray(arr)) doneSteps = new Set(arr);
    }
  } catch(e) {}
  try {
    const b = localStorage.getItem('td4-bookmarks');
    if (b) {
      const arr = JSON.parse(b);
      if (Array.isArray(arr)) bookmarkSteps = new Set(arr);
    }
  } catch(e) {}
}

function saveStorage() {
  try {
    localStorage.setItem('td4-done', JSON.stringify(Array.from(doneSteps)));
  } catch(e) {}
  try {
    localStorage.setItem('td4-bookmarks', JSON.stringify(Array.from(bookmarkSteps)));
  } catch(e) {}
}

const v = document.getElementById('v');
const progressBar = document.getElementById('progress-bar');
const cardsContainer = document.getElementById('step-cards-container');
const railList = document.getElementById('rail-list');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const completeNextLbl = document.getElementById('complete-next-lbl');
const thumbPrevBtn = document.getElementById('thumb-prev-btn');
const thumbCompleteNextLbl = document.getElementById('thumb-complete-next-lbl');
const bookmarkBtn = document.getElementById('bookmark-btn');
const bookmarkIcon = document.getElementById('bookmark-icon');
const thumbBookmarkBtn = document.getElementById('thumb-bookmark-btn');
const thumbBookmarkIcon = document.getElementById('thumb-bookmark-icon');
const disclosure = document.getElementById('steps-disclosure');
const vLoading = document.getElementById('v-loading');
const vErr = document.getElementById('v-error');

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatRemaining(idx) {
  const t = stepTimes[idx] || 0;
  const dur = (v && isFinite(v.duration) && v.duration > 0) ? v.duration : 1156;
  const rem = Math.max(0, dur - t);
  const mins = Math.floor(rem / 60);
  const secs = Math.floor(rem % 60);
  return 'Est. remaining ' + mins + 'm ' + secs + 's';
}

function updateStateUI() {
  const idx = activeStep;
  const remText = formatRemaining(idx);
  const stepNumStr = String(idx + 1).padStart(2, '0');

  // Timeline header
  const timelineStepLabel = document.getElementById('timeline-step-label');
  if (timelineStepLabel) timelineStepLabel.textContent = 'Step ' + stepNumStr + ' of ' + totalSteps + ' - active';
  const timelineEst = document.getElementById('timeline-est');
  if (timelineEst) timelineEst.textContent = remText;

  // Segments
  if (progressBar) {
    const segs = progressBar.children;
    for (let i = 0; i < segs.length; i++) {
      segs[i].classList.remove('done', 'active');
      if (doneSteps.has(i)) {
        segs[i].classList.add('done');
      }
      if (i === idx) {
        segs[i].classList.add('active');
      }
    }
  }

  // Telemetry Card
  const pctEl = document.getElementById('telemetry-pct');
  if (pctEl) {
    const pct = Math.round((doneSteps.size / totalSteps) * 100);
    pctEl.textContent = pct + '% completed';
  }
  const telemetryStep = document.getElementById('telemetry-step');
  if (telemetryStep) telemetryStep.textContent = 'Step ' + stepNumStr + ' of ' + totalSteps;
  const telemetryRem = document.getElementById('telemetry-rem');
  if (telemetryRem) telemetryRem.textContent = remText;

  const trayEl = document.getElementById('telemetry-tray-body');
  if (trayEl) {
    const hw = stepHardware[idx];
    let trayHtml = '';
    if (hw && (hw.fasteners || hw.connectors)) {
      if (hw.fasteners) {
        trayHtml += '<div class="tray-chip"><span class="tray-chip-tag mono-label">Fastener:</span><span class="tray-chip-val">' + escapeHtml(hw.fasteners) + '</span></div>';
      }
      if (hw.connectors) {
        trayHtml += '<div class="tray-chip"><span class="tray-chip-tag mono-label">CONNECTOR:</span><span class="tray-chip-val">' + escapeHtml(hw.connectors) + '</span></div>';
      }
    } else {
      trayHtml = '<div class="tray-empty mono-label">None for this step</div>';
    }
    trayEl.innerHTML = trayHtml;
  }

  // Nav buttons
  if (prevBtn) prevBtn.disabled = (idx === 0);
  if (thumbPrevBtn) thumbPrevBtn.disabled = (idx === 0);
  if (nextBtn) nextBtn.disabled = (idx === totalSteps - 1);

  const nextNumStr = String(idx + 2).padStart(2, '0');
  const completeLblText = (idx < totalSteps - 1) ? ('Complete & Next: Step ' + nextNumStr) : ('Complete: Step ' + stepNumStr);
  if (completeNextLbl) completeNextLbl.textContent = completeLblText;
  if (thumbCompleteNextLbl) thumbCompleteNextLbl.textContent = completeLblText;

  // Bookmark buttons
  const isBookmarked = bookmarkSteps.has(idx);
  if (bookmarkBtn) bookmarkBtn.classList.toggle('bookmarked', isBookmarked);
  if (bookmarkIcon) bookmarkIcon.textContent = isBookmarked ? 'bookmark' : 'bookmark_border';
  if (thumbBookmarkBtn) thumbBookmarkBtn.classList.toggle('bookmarked', isBookmarked);
  if (thumbBookmarkIcon) thumbBookmarkIcon.textContent = isBookmarked ? 'bookmark' : 'bookmark_border';

  // Rail rows
  if (railList) {
    const rows = railList.children;
    for (let i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('active', i === idx);
      const sIcon = document.getElementById('status-icon-' + i);
      if (sIcon) {
        sIcon.classList.remove('icon-done', 'icon-active', 'icon-pending');
        if (i === idx) {
          sIcon.textContent = 'sync';
          sIcon.classList.add('icon-active');
        } else if (doneSteps.has(i)) {
          sIcon.textContent = 'check_circle';
          sIcon.classList.add('icon-done');
        } else {
          sIcon.textContent = 'radio_button_unchecked';
          sIcon.classList.add('icon-pending');
        }
      }
      const bInd = document.getElementById('bm-ind-' + i);
      if (bInd) {
        bInd.style.display = bookmarkSteps.has(i) ? 'inline-block' : 'none';
      }
    }
    if (rows[idx] && hasInteracted && disclosure && disclosure.open) {
      rows[idx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }
}

function setStep(idx, andSeek) {
  if (idx < 0) idx = 0;
  if (idx >= totalSteps) idx = totalSteps - 1;
  activeStep = idx;

  if (cardsContainer) {
    const cards = cardsContainer.children;
    for (let i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('active', i === idx);
    }
  }

  updateStateUI();

  if (andSeek && v) {
    expectedSeekTime = stepTimes[idx];
    v.currentTime = stepTimes[idx];
    v.play().catch(function(){});
  }
}

function selectStep(idx) {
  hasInteracted = true;
  setStep(idx, true);
  if (disclosure && window.innerWidth < 1024) {
    disclosure.open = false;
    const pane = document.getElementById('step-pane');
    if (pane) {
      pane.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

function prevStep() {
  if (activeStep > 0) {
    selectStep(activeStep - 1);
  }
}

function nextStep() {
  if (activeStep < totalSteps - 1) {
    selectStep(activeStep + 1);
  }
}

function completeAndNext() {
  doneSteps.add(activeStep);
  saveStorage();
  if (activeStep < totalSteps - 1) {
    selectStep(activeStep + 1);
  } else {
    updateStateUI();
  }
}

function toggleBookmark() {
  if (bookmarkSteps.has(activeStep)) {
    bookmarkSteps.delete(activeStep);
  } else {
    bookmarkSteps.add(activeStep);
  }
  saveStorage();
  updateStateUI();
}

function filterSteps(q) {
  const query = (q || '').trim().toLowerCase();
  const rows = document.querySelectorAll('.rail-row');
  for (let i = 0; i < rows.length; i++) {
    const title = rows[i].getAttribute('data-title') || '';
    if (!query || title.toLowerCase().indexOf(query) !== -1) {
      rows[i].style.display = '';
    } else {
      rows[i].style.display = 'none';
    }
  }
}

function openImageOverlay(src, title) {
  const overlay = document.getElementById('image-overlay');
  const img = document.getElementById('image-overlay-img');
  const titleEl = document.getElementById('image-overlay-title');
  if (overlay && img) {
    img.src = src;
    if (titleEl && title) titleEl.textContent = title;
    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
}

function closeImageOverlay() {
  const overlay = document.getElementById('image-overlay');
  if (overlay && overlay.style.display !== 'none') {
    overlay.style.display = 'none';
    document.body.style.overflow = '';
  }
}

if (v) {
  if (v.readyState >= 2 && vLoading) {
    vLoading.style.display = 'none';
  }
  v.addEventListener('loadedmetadata', function() { updateStateUI(); });
  v.addEventListener('seeked', function() { expectedSeekTime = null; });
  if (vLoading) {
    v.addEventListener('loadeddata', function() { vLoading.style.display = 'none'; });
    v.addEventListener('canplay', function() { vLoading.style.display = 'none'; });
    v.addEventListener('playing', function() { vLoading.style.display = 'none'; });
    v.addEventListener('waiting', function() { vLoading.style.display = 'block'; });
  }
  v.addEventListener('error', function() {
    if (vLoading) vLoading.style.display = 'none';
    v.style.display = 'none';
    if (vErr) vErr.style.display = 'flex';
  });
  v.addEventListener('timeupdate', function() {
    const ct = v.currentTime;
    if (expectedSeekTime !== null) {
      if (Math.abs(ct - expectedSeekTime) > 1.5) {
        return; // stale position from before our programmatic seek landed
      }
      expectedSeekTime = null;
    }
    let idx = 0;
    for (let i = 0; i < stepTimes.length; i++) {
      if (ct >= stepTimes[i]) {
        idx = i;
      } else {
        break;
      }
    }
    if (idx !== activeStep) {
      setStep(idx, false);
    }
  });
}

function syncDisclosure() {
  if (disclosure) {
    if (window.innerWidth >= 1024) {
      disclosure.open = true;
    }
    const toggleLbl = disclosure.querySelector('.disclosure-toggle');
    if (toggleLbl && window.innerWidth < 1024) {
      toggleLbl.textContent = disclosure.open ? 'Hide list ▴' : 'Show list ▾';
    }
  }
}

if (disclosure) {
  disclosure.addEventListener('toggle', function() {
    const toggleLbl = disclosure.querySelector('.disclosure-toggle');
    if (toggleLbl && window.innerWidth < 1024) {
      toggleLbl.textContent = disclosure.open ? 'Hide list ▴' : 'Show list ▾';
    }
  });
}

window.addEventListener('resize', syncDisclosure);
syncDisclosure();

document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
  if (e.key === 'Escape') {
    closeImageOverlay();
    return;
  }
  if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowLeft') {
    prevStep();
  }
  if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowRight') {
    nextStep();
  }
});

var hasInteracted = false;
var expectedSeekTime = null;
if (disclosure && window.innerWidth >= 1024) { disclosure.open = true; }
// Initialize storage and UI
loadStorage();
updateStateUI();
</script>
</body></html>"""


def job_card(j):
    st = JOBS[j]
    esc = html_mod.escape
    if st["status"] == "done":
        return (f'<div class="card job-card"><a class="pill" href="/jobs/{j}">{esc(st.get("device") or j)}</a>'
                f'<span class="mut"> {st.get("steps", "?")} steps</span></div>')
    if st["status"] == "processing":
        return f'<div class="card job-card"><span class="mut">processing&hellip; {esc(st.get("stage", ""))}</span></div>'
    if st["status"] == "error":
        return f'<div class="card job-card"><div class="err">failed: {esc(st.get("error", "unknown error"))}</div></div>'
    return f'<div class="card job-card"><span class="mut">queued</span></div>'


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="text/html; charset=utf-8", status=200, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, fp, ctype):
        """Serve a file with HTTP Range support so <video> seeking works.

        Browsers issue Range requests for media; without a 206 response the
        video element cannot seek and currentTime assignment is ignored.
        """
        size = os.path.getsize(fp)
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                    end = size - 1
                if start >= size or start > end:
                    self._send("", "text/plain", 416,
                               extra={"Content-Range": f"bytes */{size}"})
                    return
                end = min(end, size - 1)
                with open(fp, "rb") as fh:
                    fh.seek(start)
                    body = fh.read(end - start + 1)
                self._send(body, ctype, 206, extra={
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Accept-Ranges": "bytes",
                })
                return
        with open(fp, "rb") as fh:
            body = fh.read()
        self._send(body, ctype, extra={"Accept-Ranges": "bytes"})

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            busy = any(j["status"] in ("queued", "processing") for j in JOBS.values())
            refresh = '<meta http-equiv="refresh" content="4">' if busy else ""
            err = parse_qs(u.query).get("e", [""])[0] if u.query else ""
            err_html = f'<div class=err>{html_mod.escape(err)}</div>' if err else ""
            self._send(INDEX.replace("__CSS__", CSS).replace("__REFRESH__", refresh)
                       .replace("__ERROR__", err_html)
                       .replace("__JOBS__", "".join(job_card(j) for j in JOBS)))
            return
        if u.path == "/pdf":
            pdf_path = os.path.join(DATA, "job4", "guide.pdf")
            if os.path.isfile(pdf_path):
                self._send(open(pdf_path, "rb").read(), "application/pdf",
                           extra={"Content-Disposition": "attachment; filename=teardown-guide.pdf"})
                return
            else:
                self._send("guide not found", "text/plain", 404)
                return
        m = re.match(r"^/jobs/([\w-]+)(?:/(.*))?$", u.path)
        if m and m.group(2) is None:
            job = m.group(1)
            plan = load_plan(job)
            if not plan:
                self._send('<p class=mut>guide not ready yet - <a href=/>back to jobs</a></p>', status=404)
                return
            n_steps = len(plan["steps"])

            def step_html(i, s):
                esc = html_mod.escape
                active_class = " active" if i == 0 else ""

                # Time calculation
                t_start = int(s["t"])
                t_end = int(plan["steps"][i + 1]["t"]) if i + 1 < n_steps else 1160
                ts_start = f"{t_start // 60:02d}:{t_start % 60:02d}"
                ts_end = f"{t_end // 60:02d}:{t_end % 60:02d}"
                chip_time = f'<span class="chip mono-label"><span class="material-symbols-outlined chip-icon">schedule</span>{ts_start} &ndash; {ts_end}</span>'

                tool_val = (s.get("tool") or "").strip()
                chip_tool = f'<span class="chip mono-label"><span class="material-symbols-outlined chip-icon">build</span>{esc(tool_val)}</span>' if tool_val else ""

                part_val = (s.get("part") or "").strip()
                chip_part = f'<span class="chip mono-label"><span class="material-symbols-outlined chip-icon">category</span>{esc(part_val)}</span>' if part_val else ""

                hl_badge = ('<span class="step-hl-badge mono-label"><span class="material-symbols-outlined" style="font-size:14px;color:var(--terracotta);margin-right:2px;">visibility</span><b class="step-hl">part highlighted</b></span>'
                            if s.get("segmented") else "")

                # Hardware & fastener registry block
                reg_rows = []
                if s.get("fasteners", "").strip():
                    reg_rows.append(f'<div class="registry-row"><span class="registry-type mono-label">Fasteners:</span> <span class="registry-val">{esc(s["fasteners"].strip())}</span></div>')
                if s.get("connectors", "").strip():
                    reg_rows.append(f'<div class="registry-row"><span class="registry-type mono-label">CONNECTORS:</span> <span class="registry-val">{esc(s["connectors"].strip())}</span></div>')
                if reg_rows:
                    reg_items = "".join(reg_rows)
                    reg_html = f'<div class="step-registry"><div class="registry-header"><span class="material-symbols-outlined registry-icon">tune</span><span class="registry-title mono-label">Hardware &amp; fastener registry</span></div><div class="registry-list">{reg_items}</div></div>'
                else:
                    reg_html = ""

                # Caution box
                if s.get("caution", "").strip():
                    caution_text = esc(s["caution"].strip())
                    caut_html = f'<div class="step-caution"><div class="caution-header"><span class="material-symbols-outlined caution-icon">warning</span><span class="caution-eyebrow mono-label">CAUTION</span></div><p class="caution-text">{caution_text}</p></div>'
                else:
                    caut_html = ""

                img_url = f"/jobs/{job}/{s['image']}"
                step_title_esc = esc(s["title"])
                step_inst_esc = esc(s["instruction"])

                return (
                    f'<div class="step-item{active_class}" data-index="{i}" data-t="{s["t"]}">'
                    f'  <div class="step-eyebrow-row">'
                    f'    <span class="step-badge mono-label">Step {i + 1} of {n_steps}</span>'
                    f'    {hl_badge}'
                    f'  </div>'
                    f'  <h2 class="step-title">{step_title_esc}</h2>'
                    f'  <div class="step-chips-row">'
                    f'    {chip_time}'
                    f'    {chip_tool}'
                    f'    {chip_part}'
                    f'  </div>'
                    f'  <div class="step-image-wrap" onclick="openImageOverlay(\'{img_url}\', \'{step_title_esc}\')" title="Click to view full-resolution image">'
                    f'    <img loading="lazy" class="step-img" src="{img_url}" alt="{step_title_esc}">'
                    f'    <button type="button" class="inspect-btn mono-label"><span class="material-symbols-outlined" style="font-size:14px;">zoom_in</span> Inspect</button>'
                    f'  </div>'
                    f'  <p class="step-desc">{step_inst_esc}</p>'
                    f'  {reg_html}'
                    f'  {caut_html}'
                    f'</div>'
                )

            def rail_row_html(i, s):
                esc = html_mod.escape
                active_class = " active" if i == 0 else ""
                t_sec = int(s["t"])
                ts_str = f"{t_sec // 60:02d}:{t_sec % 60:02d}"
                num_str = f"{i + 1:02d}"
                tool_str = esc(s.get("tool") or "fingers")
                return (
                    f'<div class="rail-row{active_class}" id="rail-row-{i}" data-index="{i}" data-title="{esc(s["title"])}" role="button" tabindex="0" onclick="selectStep({i})">'
                    f'  <span class="row-num mono-label">{num_str}</span>'
                    f'  <div class="row-thumb-wrap">'
                    f'    <img loading="lazy" class="row-thumb" src="/jobs/{job}/{s["image"]}" alt="{esc(s["title"])}">'
                    f'  </div>'
                    f'  <div class="row-content">'
                    f'    <div class="row-title">{esc(s["title"])}</div>'
                    f'    <div class="row-meta mono-label">{ts_str} &middot; {tool_str}</div>'
                    f'  </div>'
                    f'  <div class="row-actions">'
                    f'    <span class="material-symbols-outlined bookmark-row-indicator" id="bm-ind-{i}" title="Bookmarked" style="display:none;">bookmark</span>'
                    f'    <span class="material-symbols-outlined status-icon status-pending" id="status-icon-{i}">radio_button_unchecked</span>'
                    f'  </div>'
                    f'</div>'
                )

            progress_html = "".join(
                f'<div class="progress-seg{" active" if i == 0 else ""}" data-index="{i}" title="Step {i + 1}: {html_mod.escape(s["title"])}" onclick="selectStep({i})"></div>'
                for i, s in enumerate(plan["steps"])
            )
            steps_html = "".join(step_html(i, s) for i, s in enumerate(plan["steps"]))
            rail_html = "".join(rail_row_html(i, s) for i, s in enumerate(plan["steps"]))
            step_times = json.dumps([s["t"] for s in plan["steps"]])
            step_hardware = json.dumps([{"fasteners": s.get("fasteners", ""), "connectors": s.get("connectors", "")} for s in plan["steps"]])
            poster = plan["steps"][0]["image"] if plan.get("steps") else ""
            poster_url = f"/jobs/{job}/{poster}" if poster else ""

            resp = (GUIDE.replace("__CSS__", CSS)
                    .replace("__DEVICE__", html_mod.escape(plan["device"]))
                    .replace("__NSTEPS__", str(n_steps))
                    .replace("__JOB__", job)
                    .replace("__POSTER__", poster_url)
                    .replace("__STEPS__", steps_html)
                    .replace("__RAIL__", rail_html)
                    .replace("__PROGRESS__", progress_html)
                    .replace("__STEPTIMES__", step_times)
                    .replace("__STEPHARDWARE__", step_hardware))
            self._send(resp)
            return
        if m and m.group(2) == "guide.pdf":
            job = m.group(1)
            pdf = os.path.join(DATA, job, "guide.pdf")
            if not os.path.exists(pdf):
                try:
                    pdf = build_pdf(job)
                except Exception as e:
                    self._send(f"pdf failed: {html_mod.escape(str(e)[:200])}", "text/plain", 500)
                    return
            if pdf and os.path.exists(pdf):
                self._send(open(pdf, "rb").read(), "application/pdf",
                           extra={"Content-Disposition": "attachment; filename=teardown-guide.pdf"})
            else:
                self._send("guide not ready", "text/plain", 404)
            return
        if m and m.group(2):
            fp = os.path.join(DATA, m.group(1), m.group(2))
            if os.path.isfile(fp) and os.path.realpath(fp).startswith(os.path.realpath(DATA)):
                ct = {".png": "image/png", ".mp4": "video/mp4", ".pdf": "application/pdf"}.get(
                    os.path.splitext(fp)[1], "application/octet-stream")
                self._send_file(fp, ct)
            else:
                self._send("not found", "text/plain", 404)
            return
        self._send("not found", "text/plain", 404)

    def do_POST(self):
        if self.path != "/jobs":
            self._send("not found", "text/plain", 404)
            return
        try:
            ln = int(self.headers.get("Content-Length", 0))
            if ln <= 0 or ln > 2 * 1024**3:
                raise ValueError("bad upload size")
            body = self.rfile.read(ln)
            url_m = re.search(rb'name="url"\r\n\r\n([^\r]*)', body)
            url = url_m.group(1).decode().strip() if url_m else ""
            fm = re.search(rb'name="video"; filename="([^"]+)"\r\nContent-Type:[^\r]+\r\n\r\n', body)
            has_file = bool(fm and fm.group(1))
            if not url and not has_file:
                self.send_response(303)
                self.send_header("Location", "/?e=add a video file or a youtube link first")
                self.end_headers()
                return
            job = uuid.uuid4().hex[:8]
            JOBS[job] = {"status": "queued", "stage": ""}
            d = os.path.join(DATA, job)
            os.makedirs(d, exist_ok=True)
            video_path = os.path.join(d, "video.mp4")
            if has_file and not url:
                end = body.rfind(b"\r\n------")
                open(video_path, "wb").write(body[fm.end():end])
            else:
                r = subprocess.run(["yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
                                    "-o", video_path, url], capture_output=True, timeout=600)
                if r.returncode != 0 or not os.path.exists(video_path):
                    raise ValueError("could not download that link - check it plays publicly")
            threading.Thread(target=run_pipeline, args=(job, video_path), daemon=True).start()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        except Exception as e:
            self.send_response(303)
            self.send_header("Location", "/?e=" + re.sub(r"[^A-Za-z0-9 .-]", "", str(e))[:120].replace(" ", "%20"))
            self.end_headers()


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    for d in os.listdir(DATA):
        if os.path.exists(os.path.join(DATA, d, "plan.json")):
            plan = json.load(open(os.path.join(DATA, d, "plan.json")))
            JOBS[d] = {"status": "done", "device": plan["device"], "steps": len(plan["steps"])}
    port = int(os.environ.get("PORT", "8377"))
    print(f"serving on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
