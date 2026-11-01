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
        # Timestamps derive from 30-second transcript windows, so they are
        # approximate by construction; render the honest marker.
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
body {{ font-family: Georgia, serif; color:#26261f; }}
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
.num {{ flex:none; width: 7.5mm; height: 7.5mm; border-radius: 50%; background:#2f4632; color:#fff; font-family: Helvetica, Arial, sans-serif; font-size: 11px; text-align:center; line-height: 7.5mm; }}
h2 {{ font-size: 14.5px; color:#2f4632; }}
.meta {{ font-family: Helvetica, Arial, sans-serif; font-size: 10px; color:#8a8a7c; margin-bottom: 2mm; }}
.hl {{ color:#2f4632; }}
p {{ font-size: 11.5px; line-height: 1.5; margin-bottom: 1.5mm; }}
.dt {{ font-size: 10.5px; color:#4a4a40; margin-bottom: 1mm; }}
.caution {{ border-left: 3px solid #b3562e; background:#faf3ee; padding: 1.5mm 2.5mm; font-size: 10.5px; color:#7c3a1e; margin-top: 1.5mm; }}
.foot {{ margin-top: 6mm; font-family: Helvetica, Arial, sans-serif; font-size: 9px; color:#8a8a7c; border-top:1px solid #d9d4c5; padding-top: 2.5mm; }}
</style></head><body>
<div class=cover>
  <h1>{esc(plan['device'])} - Teardown Guide<span class=dot>.</span></h1>
  <div class=sub>{len(steps)} steps &middot; generated by teardown &middot; timestamps approximate (&plusmn;30s)</div>
  <div class=banner>Auto-generated demo output - not validated repair instructions. Part highlighting is applied only where the segmentation matched the named part directly; other steps show the plain video frame.</div>
  <div class=tools><h3>Tools used in this video</h3><ul>{tools_list}</ul></div>
</div>
{''.join(blocks)}
<div class=foot>Private test output. Generated by teardown.</div>
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
  --paper: #f6f1e7;
  --paper-card: #fdfbf7;
  --paper-hover: #f1ebd9;
  --paper-active: #ede5d1;
  --ink: #2f4632;
  --body-ink: #26261f;
  --green: #2f4632;
  --green-hover: #243827;
  --terra: #b3562e;
  --hair: #ddd6c3;
  --hair-dark: #c8c0ad;
  --mut: #707567;
  --font-serif: Georgia, serif;
  --font-sans: Helvetica, Arial, sans-serif;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-serif);
  background: var(--paper);
  color: var(--body-ink);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

a {
  color: var(--green);
}

.mut {
  color: var(--mut);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
}

.dot {
  color: var(--terra);
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--green);
  color: var(--green);
  border-radius: 999px;
  padding: 9px 22px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: bold;
  background: transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
  user-select: none;
}

.pill:hover {
  background: var(--paper-hover);
}

.pill.solid {
  background: var(--green);
  color: #fff;
  border-color: var(--green);
}

.pill.solid:hover {
  background: var(--green-hover);
}

.card {
  border: 1px solid var(--hair);
  border-radius: 10px;
  padding: 22px;
  margin: 16px 0;
  background: var(--paper-card);
}

.err {
  border: 1px solid var(--terra);
  border-radius: 8px;
  padding: 10px 14px;
  color: var(--terra);
  font-family: var(--font-sans);
  font-size: 13px;
  margin: 12px 0;
  background: #fdf5f0;
}

.banner {
  border: 1px solid var(--hair);
  border-left: 3px solid var(--terra);
  background: var(--paper-card);
  padding: 10px 14px;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  line-height: 1.5;
  border-radius: 4px;
}

.app-footer {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--mut);
  text-align: center;
}

/* INDEX TEMPLATE STYLES */
.index-container {
  max-width: 640px;
  margin: 40px auto;
  padding: 0 20px;
}

.index-header {
  margin-bottom: 24px;
}

.index-title {
  font-family: var(--font-serif);
  font-size: 32px;
  color: var(--green);
  letter-spacing: -0.5px;
  font-weight: normal;
}

.drop {
  border: 1.5px dashed var(--hair);
  border-radius: 8px;
  padding: 30px 20px;
  text-align: center;
  color: var(--mut);
  font-family: var(--font-sans);
  font-size: 14px;
  margin-bottom: 14px;
  background: #faf6ee;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.drop:hover {
  border-color: var(--green);
}

.drop input {
  display: none;
}

.drop label {
  cursor: pointer;
  display: block;
}

.drop b {
  color: var(--green);
}

.or {
  text-align: center;
  color: var(--mut);
  font-family: var(--font-sans);
  font-size: 12px;
  margin: 14px 0;
}

input[type=text] {
  width: 100%;
  padding: 11px 18px;
  border: 1px solid var(--hair);
  border-radius: 999px;
  font-size: 14px;
  font-family: var(--font-sans);
  background: #fff;
  outline: none;
  box-sizing: border-box;
  color: var(--body-ink);
}

input[type=text]:focus {
  border-color: var(--green);
}

.job-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  margin: 12px 0;
}

.index-footer {
  margin-top: 40px;
  padding-bottom: 24px;
}

/* GUIDE APP HEADER */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--hair);
  background: var(--paper);
  gap: 16px;
}

.brand {
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: bold;
  color: var(--green);
  text-decoration: none;
  letter-spacing: -0.5px;
}

.header-center {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.header-device {
  font-family: var(--font-serif);
  font-size: 14px;
  color: var(--green);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  max-width: 100%;
}

.header-pdf {
  padding: 6px 16px;
  font-size: 12px;
  background: var(--paper-card);
  border-color: var(--hair);
  flex-shrink: 0;
}

.header-pdf:hover {
  border-color: var(--green);
}

.app-subbar {
  background: #fbf7ee;
  border-bottom: 1px solid var(--hair);
  padding: 6px 16px;
  text-align: center;
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--mut);
  letter-spacing: 0.15px;
  line-height: 1.3;
}

/* GUIDE VIDEO & PROGRESS */
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

.video-loading {
  position: absolute;
  top: 10px;
  right: 10px;
  background: var(--paper-card);
  color: var(--mut);
  border: 1px solid var(--hair);
  border-radius: 999px;
  padding: 3px 10px;
  font-family: var(--font-sans);
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
  color: var(--terra);
  font-size: 16px;
  margin-bottom: 2px;
}

.v-error-msg {
  font-family: var(--font-serif);
  font-size: 14.5px;
  color: var(--green);
}

.v-error-sub {
  font-family: var(--font-sans);
  font-size: 11.5px;
  color: var(--mut);
  max-width: 280px;
  line-height: 1.4;
}

.progress-bar {
  display: flex;
  gap: 2px;
  background: var(--hair);
  height: 5px;
  width: 100%;
  border: 1px solid var(--hair);
  border-top: none;
}

.progress-seg {
  flex: 1;
  height: 100%;
  background: #e2dbcc;
  cursor: pointer;
  transition: background 0.1s ease;
}

.progress-seg.watched {
  background: var(--green);
}

.progress-seg.active {
  background: var(--terra);
}

/* FOCUSED STEP CARD */
.step-card {
  border: 1px solid var(--hair);
  border-radius: 10px;
  background: var(--paper-card);
  padding: 20px;
}

.step-item {
  display: none;
}

.step-item.active {
  display: block;
}

.step-image-wrap {
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
}

.step-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.step-header-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.step-pill {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--green);
  background: #ede6d4;
  border: 1px solid var(--hair);
  border-radius: 999px;
  padding: 3px 10px;
  display: inline-block;
}

.step-title {
  font-family: var(--font-serif);
  font-size: 22px;
  line-height: 1.25;
  color: var(--green);
  margin-bottom: 6px;
  font-weight: normal;
}

.step-meta {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  margin-bottom: 14px;
  line-height: 1.4;
}

.step-hl {
  font-weight: bold;
  color: var(--terra);
}

.step-desc {
  font-family: var(--font-serif);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--body-ink);
  margin-bottom: 14px;
}

.step-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.step-dt {
  font-family: var(--font-sans);
  font-size: 12px;
  color: #444a42;
  background: #f4eee2;
  padding: 6px 10px;
  border: 1px solid var(--hair);
  border-radius: 4px;
  line-height: 1.4;
}

.step-dt b {
  color: var(--green);
}

.step-caution {
  border-left: 3px solid var(--terra);
  background: #faf3ee;
  padding: 10px 14px;
  font-family: var(--font-sans);
  font-size: 12.5px;
  line-height: 1.45;
  color: #7c3a1e;
  margin-top: 10px;
  border-radius: 0 4px 4px 0;
}

.caution-icon {
  font-weight: bold;
  margin-right: 4px;
  color: var(--terra);
}

.step-nav {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--hair);
}

.nav-btn {
  flex: 1;
  padding: 12px 20px;
  font-size: 14px;
  min-height: 48px;
}

.nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}

/* ALL STEPS DISCLOSURE & RAIL */
.steps-disclosure {
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
}

.disclosure-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: #fbf7ee;
  border-radius: 7px;
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
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.disclosure-title {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: bold;
  color: var(--green);
}

.disclosure-count {
  font-family: var(--font-sans);
  font-size: 11.5px;
  color: var(--mut);
}

.disclosure-toggle {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--green);
  font-weight: bold;
  flex-shrink: 0;
}

details[open] .disclosure-summary {
  border-bottom: 1px solid var(--hair);
  border-radius: 7px 7px 0 0;
}

.rail-list {
  max-height: 380px;
  overflow-y: auto;
}

.rail-row {
  display: flex;
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
  border-left: 3px solid var(--terra);
  padding-left: 11px;
}

.row-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--green);
  color: #fff;
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rail-row.active .row-num {
  background: var(--terra);
}

.row-thumb-wrap {
  width: 58px;
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
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.row-title {
  font-family: var(--font-serif);
  font-size: 13.5px;
  color: var(--green);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-row.active .row-title {
  font-weight: bold;
}

.row-meta {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--mut);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* RESPONSIVE LAYOUTS */
@media (max-width: 899px) {
  .layout-container {
    padding: 0;
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
  .step-pane {
    order: 2;
    padding: 16px 14px 0 14px;
  }
  .disclosure-pane {
    order: 3;
    padding: 14px 14px 0 14px;
  }
  .notice-pane {
    order: 4;
    padding: 14px 14px 0 14px;
  }
  .footer-pane {
    order: 5;
    padding: 20px 14px 32px 14px;
  }
}

@media (min-width: 900px) {
  .layout-container {
    max-width: 1240px;
    margin: 0 auto;
    padding: 24px 28px 48px;
  }
  .layout {
    display: grid;
    grid-template-columns: 460px 1fr;
    gap: 36px;
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
    gap: 18px;
    min-width: 0;
  }
  .player-pane {
    position: static;
    width: 100%;
  }
  .step-card {
    padding: 26px;
  }
  .step-title {
    font-size: 26px;
  }
  .step-desc {
    font-size: 15px;
  }
  .disclosure-pane {
    margin-top: 0;
  }
  .steps-disclosure {
    border: 1px solid var(--hair);
    border-radius: 8px;
    background: var(--paper-card);
    overflow: hidden;
  }
  .disclosure-summary {
    pointer-events: none;
    cursor: default;
    background: #f3edd9;
    border-bottom: 1px solid var(--hair);
    padding: 12px 16px;
    border-radius: 7px 7px 0 0;
  }
  .disclosure-toggle {
    display: none;
  }
  .rail-list {
    max-height: calc(100vh - 380px);
    min-height: 260px;
    overflow-y: auto;
  }
}
"""

INDEX = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>teardown</title><style>__CSS__</style>
__REFRESH__</head><body>
<div class="index-container">
  <header class="index-header">
    <h1 class="index-title">teardown<span class="dot">.</span></h1>
    <p class="mut">repair footage in, illustrated guide out</p>
  </header>
  __ERROR__
  <div class="card index-card">
    <form method="post" action="/jobs" enctype="multipart/form-data">
      <div class="drop">
        <label for="f">drop a video here or <b>browse files</b>
          <input id="f" type="file" name="video" accept="video/mp4,video/quicktime,video/*">
        </label>
      </div>
      <div class="or">or</div>
      <p><input type="text" name="url" placeholder="paste a youtube link"></p>
      <p style="margin-top:16px"><button class="pill solid submit-pill" type="submit">build guide</button></p>
    </form>
  </div>
  <div class="jobs-list">
    __JOBS__
  </div>
  <footer class="index-footer">
    <p class="app-footer">private test output - generated by teardown</p>
  </footer>
</div>
<script>
document.getElementById('f').addEventListener('change', function(){
  this.closest('.drop').querySelector('b').textContent = this.files[0] ? this.files[0].name : 'browse files';
});
</script>
</body></html>"""

GUIDE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>__DEVICE__ - teardown</title><style>__CSS__</style></head><body>
<header class="app-header">
  <div class="header-left">
    <a href="/" class="brand">teardown<span class="dot">.</span></a>
  </div>
  <div class="header-center">
    <span class="header-device">__DEVICE__</span>
  </div>
  <div class="header-right">
    <a class="pill header-pdf" href="/jobs/__JOB__/guide.pdf">PDF</a>
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
        <div class="progress-bar" id="progress-bar" aria-label="Step progress">
          __PROGRESS__
        </div>
      </div>
      <div class="disclosure-pane">
        <details id="steps-disclosure" class="steps-disclosure">
          <summary class="disclosure-summary">
            <div class="disclosure-meta">
              <span class="disclosure-title">All steps</span>
              <span class="disclosure-count">__NSTEPS__ steps &middot; timestamps approximate (&plusmn;30s)</span>
            </div>
            <span class="disclosure-toggle">Show list ▾</span>
          </summary>
          <div class="rail-list" id="rail-list">
            __RAIL__
          </div>
        </details>
      </div>
    </div>

    <div class="right-col">
      <div class="step-pane" id="step-pane">
        <div class="step-card">
          <div id="step-cards-container">
            __STEPS__
          </div>
          <div class="step-nav">
            <button type="button" class="pill nav-btn" id="prev-btn" onclick="prevStep()" disabled>&larr; Previous</button>
            <button type="button" class="pill solid nav-btn" id="next-btn" onclick="nextStep()">Next &rarr;</button>
          </div>
        </div>
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

<script>
const v = document.getElementById('v');
const stepTimes = __STEPTIMES__;
const totalSteps = stepTimes.length;
let activeStep = 0;

const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const cardsContainer = document.getElementById('step-cards-container');
const railList = document.getElementById('rail-list');
const progressBar = document.getElementById('progress-bar');
const disclosure = document.getElementById('steps-disclosure');
const vLoading = document.getElementById('v-loading');
const vErr = document.getElementById('v-error');

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

  if (prevBtn) prevBtn.disabled = (idx === 0);
  if (nextBtn) nextBtn.disabled = (idx === totalSteps - 1);

  if (progressBar) {
    const segs = progressBar.children;
    for (let i = 0; i < segs.length; i++) {
      segs[i].classList.remove('watched', 'active');
      if (i < idx) {
        segs[i].classList.add('watched');
      } else if (i === idx) {
        segs[i].classList.add('active');
      }
    }
  }

  if (railList) {
    const rows = railList.children;
    for (let i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('active', i === idx);
    }
    if (rows[idx]) {
      rows[idx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  if (andSeek && v) {
    v.currentTime = stepTimes[idx];
    v.play().catch(function(){});
  }
}

function selectStep(idx) {
  setStep(idx, true);
  if (disclosure && window.innerWidth < 900) {
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

function seek(t) {
  if (v) {
    v.currentTime = t;
    v.play().catch(function(){});
  }
}

if (v) {
  if (v.readyState >= 2 && vLoading) {
    vLoading.style.display = 'none';
  }
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

if (progressBar) {
  const segs = progressBar.children;
  for (let i = 0; i < segs.length; i++) {
    (function(index) {
      segs[index].addEventListener('click', function() {
        selectStep(index);
      });
    })(i);
  }
}

function syncDisclosure() {
  if (disclosure) {
    if (window.innerWidth >= 900) {
      disclosure.open = true;
    }
    const toggleLbl = disclosure.querySelector('.disclosure-toggle');
    if (toggleLbl && window.innerWidth < 900) {
      toggleLbl.textContent = disclosure.open ? 'Hide list ▴' : 'Show list ▾';
    }
  }
}

if (disclosure) {
  disclosure.addEventListener('toggle', function() {
    const toggleLbl = disclosure.querySelector('.disclosure-toggle');
    if (toggleLbl && window.innerWidth < 900) {
      toggleLbl.textContent = disclosure.open ? 'Hide list ▴' : 'Show list ▾';
    }
  });
}

window.addEventListener('resize', syncDisclosure);
syncDisclosure();

document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'ArrowLeft') prevStep();
  if (e.key === 'ArrowRight') nextStep();
});
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
                det = []
                if s.get("fasteners"):
                    det.append(f'<div class="step-dt"><b>Fasteners:</b> {esc(s["fasteners"])}</div>')
                if s.get("connectors"):
                    det.append(f'<div class="step-dt"><b>Connectors:</b> {esc(s["connectors"])}</div>')
                det_html = f'<div class="step-details">{"".join(det)}</div>' if det else ""
                caut_html = f'<div class="step-caution"><span class="caution-icon">&#9650;</span> {esc(s["caution"])}</div>' if s.get("caution") else ""
                hl = ' &middot; <b class="step-hl">part highlighted</b>' if s.get("segmented") else ""
                active_class = " active" if i == 0 else ""
                ts_str = f"~{int(s['t'] // 60)}:{int(s['t'] % 60):02d}"
                tool_str = esc(s.get("tool") or "fingers")
                return (
                    f'<div class="step-item{active_class}" data-index="{i}" data-t="{s["t"]}">'
                    f'  <div class="step-image-wrap">'
                    f'    <img loading="lazy" class="step-img" src="/jobs/{job}/{s["image"]}" alt="{esc(s["title"])}">'
                    f'  </div>'
                    f'  <div class="step-header-row">'
                    f'    <span class="step-pill">Step {i + 1} of {n_steps}</span>'
                    f'  </div>'
                    f'  <h2 class="step-title">{esc(s["title"])}</h2>'
                    f'  <div class="step-meta">{ts_str} &middot; {tool_str}{hl}</div>'
                    f'  <p class="step-desc">{esc(s["instruction"])}</p>'
                    f'  {det_html}'
                    f'  {caut_html}'
                    f'</div>'
                )

            def rail_row_html(i, s):
                esc = html_mod.escape
                active_class = " active" if i == 0 else ""
                ts_str = f"~{int(s['t'] // 60)}:{int(s['t'] % 60):02d}"
                tool_str = esc(s.get("tool") or "fingers")
                return (
                    f'<div class="rail-row{active_class}" id="rail-row-{i}" data-index="{i}" role="button" tabindex="0" onclick="selectStep({i})">'
                    f'  <span class="row-num">{i + 1}</span>'
                    f'  <div class="row-thumb-wrap">'
                    f'    <img loading="lazy" class="row-thumb" src="/jobs/{job}/{s["image"]}" alt="{esc(s["title"])}">'
                    f'  </div>'
                    f'  <div class="row-content">'
                    f'    <div class="row-title">{esc(s["title"])}</div>'
                    f'    <div class="row-meta">{ts_str} &middot; {tool_str}</div>'
                    f'  </div>'
                    f'</div>'
                )

            progress_html = "".join(
                f'<div class="progress-seg{" active" if i == 0 else ""}" data-index="{i}" title="Step {i + 1}"></div>'
                for i in range(n_steps)
            )
            steps_html = "".join(step_html(i, s) for i, s in enumerate(plan["steps"]))
            rail_html = "".join(rail_row_html(i, s) for i, s in enumerate(plan["steps"]))
            step_times = json.dumps([s["t"] for s in plan["steps"]])
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
                    .replace("__STEPTIMES__", step_times))
            self._send(resp)
            return
        if m and m.group(2) == "guide.pdf":
            try:
                pdf = build_pdf(m.group(1))
            except Exception as e:
                self._send(f"pdf failed: {html_mod.escape(str(e)[:200])}", "text/plain", 500)
                return
            if pdf:
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

