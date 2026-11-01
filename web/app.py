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
        transcript = api.transcribe(wav) if wav else ""
        JOBS[job_id]["stage"] = "watching video and planning steps"
        video_id = api.upload_file(video_path)
        duration = ingest.probe_duration(video_path)
        plan = steps_mod.plan_steps(api, video_id, transcript, duration)
        n = len(plan["steps"])
        for i, s in enumerate(plan["steps"]):
            JOBS[job_id]["stage"] = f"highlighting parts ({i + 1}/{n})"
            frame = os.path.join(out, "steps", f"frame-{i + 1}.png")
            ingest.extract_frame(video_path, s["t"], frame)
            hit = segment_mod.segment_part(api, frame, s["part"])  # fail-closed
            if hit:
                render.annotate(frame, tuple(hit["bounds"]), hit["mask"], i + 1,
                                os.path.join(out, "steps", f"step-{i + 1}.png"))
                s["image"] = f"steps/step-{i + 1}.png"
            else:
                s["image"] = f"steps/frame-{i + 1}.png"
            s["segmented"] = bool(hit)
        json.dump(plan, open(os.path.join(out, "plan.json"), "w"), indent=1)
        JOBS[job_id].update(status="done", device=plan["device"], steps=n)
    except Exception as e:
        JOBS[job_id].update(status="error", error=str(e)[:300])


def build_pdf(job_id):
    """Print-layout HTML -> PDF via headless chrome. Returns pdf path or None."""
    plan = load_plan(job_id)
    if not plan:
        return None
    steps = plan["steps"]
    esc = html_mod.escape

    def ts(t):
        return f"{int(t // 60)}:{int(t % 60):02d}"

    blocks = []
    for i, s in enumerate(steps):
        n = i + 1
        hl = '<span class="hl">part highlighted</span>' if s.get("segmented") else ""
        blocks.append(f"""
<div class="step">
  <div class="stephead"><span class="num">{n}</span>
    <div><h2>{esc(s['title'])}</h2>
    <div class="meta">{ts(s['t'])} &middot; {esc(s.get('tool') or 'fingers')} {hl}</div></div>
  </div>
  <img src="steps-img/{n}.png" alt="">
  <p>{esc(s['instruction'])}</p>
</div>""")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm 15mm; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: Georgia, serif; color:#26261f; }}
.cover {{ page-break-after: always; padding-top: 60mm; }}
.cover h1 {{ font-size: 34px; color:#2f4632; }}
.cover h1 .dot {{ color:#b3562e; }}
.cover .sub {{ font-size: 15px; color:#6b6b5f; margin-top: 6mm; }}
.banner {{ margin-top: 14mm; border:1px solid #d9d4c5; border-left:3px solid #b3562e; padding: 4mm 5mm; font-size: 12px; color:#6b6b5f; }}
.step {{ page-break-inside: avoid; border-top: 1px solid #d9d4c5; padding: 6mm 0 7mm; }}
.stephead {{ display:flex; align-items:flex-start; gap: 5mm; margin-bottom: 3.5mm; }}
.num {{ flex:none; width: 9mm; height: 9mm; border-radius: 50%; background:#2f4632; color:#fff; font-family: Helvetica, Arial, sans-serif; font-size: 13px; text-align:center; line-height: 9mm; }}
h2 {{ font-size: 17px; color:#2f4632; }}
.meta {{ font-family: Helvetica, Arial, sans-serif; font-size: 10.5px; color:#8a8a7c; margin-top: 1.2mm; }}
.hl {{ color:#2f4632; font-weight: bold; }}
img {{ width: 100%; border:1px solid #d9d4c5; }}
p {{ font-size: 12.5px; line-height: 1.55; margin-top: 3mm; }}
.foot {{ margin-top: 8mm; font-family: Helvetica, Arial, sans-serif; font-size: 9.5px; color:#8a8a7c; border-top:1px solid #d9d4c5; padding-top: 3mm; }}
</style></head><body>
<div class="cover">
  <h1>{esc(plan['device'])} - Teardown Guide<span class="dot">.</span></h1>
  <div class="sub">{len(steps)} steps &middot; generated by teardown</div>
  <div class="banner">Auto-generated demo output - not validated repair instructions.
  Part highlighting is applied only where the segmentation matched the named part directly;
  steps without a highlight show the plain video frame.</div>
</div>
{''.join(blocks)}
<div class="foot">Private test output. Generated by teardown.</div>
</body></html>"""
    jd = os.path.join(DATA, job_id)
    imgdir = os.path.join(jd, "steps-img")
    os.makedirs(imgdir, exist_ok=True)
    for i, s in enumerate(steps):
        src = os.path.join(jd, s["image"])
        dst = os.path.join(imgdir, f"{i + 1}.png")
        if os.path.exists(src) and not os.path.exists(dst):
            os.link(src, dst)
    hp = os.path.join(jd, "guide-print.html")
    open(hp, "w").write(page)
    pdf = os.path.join(jd, "guide.pdf")
    r = subprocess.run(["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
                        f"--print-to-pdf={pdf}", "--no-pdf-header-footer", hp],
                       capture_output=True, timeout=120)
    return pdf if os.path.exists(pdf) else None


CSS = """
:root{--paper:#f7f4ec;--ink:#26261f;--green:#2f4632;--terra:#b3562e;--hair:#d9d4c5;--mut:#8a8a7c;}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Georgia,serif;background:var(--paper);color:var(--ink);max-width:1100px;margin:0 auto;padding:36px 20px}
h1{color:var(--green);font-size:30px}h1 .dot{color:var(--terra)}
a{color:var(--green)}
.mut{color:var(--mut);font-family:Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5}
.card{border:1px solid var(--hair);border-radius:10px;padding:22px;margin:16px 0;background:#fffdf8}
.drop{border:1.5px dashed var(--hair);border-radius:10px;padding:26px;text-align:center;color:var(--mut);
  font-family:Helvetica,Arial,sans-serif;font-size:14px;margin-bottom:14px}
.drop input{display:none}
.drop label{cursor:pointer;display:block}
.drop b{color:var(--green)}
.or{text-align:center;color:var(--mut);font-family:Helvetica,Arial,sans-serif;font-size:12px;margin:12px 0}
input[type=text]{width:100%;padding:11px 16px;border:1px solid var(--hair);border-radius:999px;font-size:14px;background:#fff;outline:none}
input[type=text]:focus{border-color:var(--green)}
.pill{display:inline-block;border:1px solid var(--green);color:var(--green);border-radius:999px;
  padding:9px 22px;font-family:Helvetica,Arial,sans-serif;font-size:13px;background:none;cursor:pointer;text-decoration:none}
.pill.solid{background:var(--green);color:#fff}
.err{border:1px solid var(--terra);border-radius:8px;padding:10px 14px;color:var(--terra);
  font-family:Helvetica,Arial,sans-serif;font-size:13px;margin:12px 0}
.banner{border:1px solid var(--hair);border-left:3px solid var(--terra);padding:10px 14px;font-size:12px;color:var(--mut);margin:14px 0;line-height:1.5}
.layout{display:grid;grid-template-columns:1fr 400px;gap:28px;margin-top:18px;align-items:start}
.vid{position:sticky;top:20px}
video{width:100%;border:1px solid var(--hair);background:#000;display:block}
.step{border-top:1px solid var(--hair);padding:16px 4px;cursor:pointer}
.step:hover{background:#f1ede2}
.step .n{display:inline-block;width:24px;height:24px;border-radius:50%;background:var(--green);color:#fff;
  font-family:Helvetica,Arial,sans-serif;font-size:11px;text-align:center;line-height:24px;margin-right:8px}
.step h3{display:inline;font-size:15px;color:var(--green)}
.step .m{font-family:Helvetica,Arial,sans-serif;font-size:11px;color:var(--mut);margin:4px 0 0 32px}
.step img{width:100%;margin-top:10px;border:1px solid var(--hair)}
.step p{font-size:13.5px;line-height:1.55;margin:8px 0 0 32px}
@media (max-width: 800px){
  body{padding:22px 14px}
  .layout{grid-template-columns:1fr;gap:14px}
  .vid{position:static}
  .step h3{font-size:14px}
}
"""

INDEX = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>teardown</title><style>__CSS__</style>
__REFRESH__</head><body>
<h1>teardown<span class=dot>.</span></h1>
<p class=mut>repair footage in, illustrated guide out</p>
__ERROR__
<div class=card>
<form method=post action=/jobs enctype=multipart/form-data>
<div class=drop><label for=f>drop a video here or <b>browse files</b><input id=f type=file name=video accept="video/mp4,video/quicktime,video/*"></label></div>
<div class=or>or</div>
<p><input type=text name=url placeholder="paste a youtube link"></p>
<p style="margin-top:16px"><button class="pill solid" type=submit>build guide</button></p>
</form></div>
__JOBS__
<script>
document.getElementById('f').addEventListener('change', function(){
  this.closest('.drop').querySelector('b').textContent = this.files[0] ? this.files[0].name : 'browse files';
});
</script>
</body></html>"""

GUIDE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>__DEVICE__ - teardown</title><style>__CSS__</style></head><body>
<h1>__DEVICE__<span class=dot>.</span></h1>
<p class=mut>__NSTEPS__ steps &middot; tap a step to jump the video &middot; <a href="/jobs/__JOB__/guide.pdf">download pdf</a></p>
<div class=banner>Auto-generated demo output - not validated repair instructions. Highlights appear only where the segmentation matched the named part directly; other steps show the plain frame.</div>
<div class=layout>
<div>__STEPS__</div>
<div class=vid><video id=v controls preload=metadata src="/jobs/__JOB__/video.mp4"></video></div>
</div>
<script>
const v=document.getElementById('v');
function seek(t){v.currentTime=t;v.play();}
</script>
</body></html>"""


def job_card(j):
    st = JOBS[j]
    esc = html_mod.escape
    if st["status"] == "done":
        return (f'<div class=card><a class=pill href="/jobs/{j}">{esc(st.get("device") or j)}</a>'
                f'<span class=mut> {st.get("steps", "?")} steps</span></div>')
    if st["status"] == "processing":
        return f'<div class=card><span class=mut>processing&hellip; {esc(st.get("stage", ""))}</span></div>'
    if st["status"] == "error":
        return f'<div class=card><div class=err>failed: {esc(st.get("error", "unknown error"))}</div></div>'
    return f'<div class=card><span class=mut>queued</span></div>'


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
            steps_html = "".join(
                f'<div class=step onclick=seek({s["t"]})><span class=n>{i + 1}</span><h3>{html_mod.escape(s["title"])}</h3>'
                f'<div class=m>{int(s["t"] // 60)}:{int(s["t"] % 60):02d} &middot; {html_mod.escape(s.get("tool") or "fingers")}'
                f'{" &middot; <b>part highlighted</b>" if s.get("segmented") else ""}</div>'
                f'<img loading=lazy src="/jobs/{job}/{s["image"]}"><p>{html_mod.escape(s["instruction"])}</p></div>'
                for i, s in enumerate(plan["steps"]))
            self._send(GUIDE.replace("__CSS__", CSS).replace("__DEVICE__", html_mod.escape(plan["device"]))
                       .replace("__NSTEPS__", str(len(plan["steps"]))).replace("__JOB__", job)
                       .replace("__STEPS__", steps_html))
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
                self._send(open(fp, "rb").read(), ct)
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
