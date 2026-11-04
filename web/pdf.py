"""Print layout rendered to PDF with headless Chrome."""
import html as html_mod
import os
import shutil
import subprocess
import tempfile
import time

from config import DATA
from jobs import load_plan


def _chrome_bin():
    """Headless Chrome, not a wrapper that pins a shared debugging profile."""
    configured = os.environ.get("CHROME_BIN")
    if configured:
        return configured
    for candidate in ("/opt/google/chrome/chrome", "chromium", "google-chrome"):
        if os.path.isfile(candidate) or shutil.which(candidate):
            return candidate
    return "google-chrome"

def build_pdf(job_id):
    """Compact print layout -> PDF via headless chrome. Returns pdf path or None."""
    plan = load_plan(job_id)
    if not plan:
        return None
    steps = plan["steps"]
    esc = html_mod.escape

    from teardown.present import approx_clock, standard_precaution, step_lines, unique_parts

    def ts(t):
        return esc(approx_clock(t))

    blocks = []
    for i, s in enumerate(steps):
        n = i + 1
        detail = []
        if s.get("fasteners"):
            detail.append(f'<div class=dt><b>Fasteners:</b> {esc(s["fasteners"])}</div>')
        if s.get("connectors"):
            detail.append(f'<div class=dt><b>Connectors:</b> {esc(s["connectors"])}</div>')
        bullets = "".join(
            f'<li class="{esc(item["type"])}">{esc(item["text"])}</li>'
            for item in step_lines(s)
        )
        caut = f'<div class=caution>{esc(s["caution"])}</div>' if s.get("caution") else ""
        precaution = standard_precaution(s.get("part") or "")
        if precaution:
            caut += f'<div class=precaution>{esc(precaution)}</div>'
        quote = ""
        if (s.get("source") or "").strip():
            quote = f'<div class=quote>&ldquo;{esc(s["source"].strip())}&rdquo;</div>'
        hl = ' &middot; <b class=hl>part highlighted</b>' if s.get("segmented") else ""
        if s.get("image"):
            img_html = f'<img src="steps-img/{n}.png">'
        else:
            img_html = ('<div class=noimg><b>No frame for this step.</b><br>'
                        'This step could not be illustrated from the video; '
                        'the text below comes from the narration only.</div>')
        blocks.append(f"""
<div class=step>
  <div class=imgcol>{img_html}</div>
  <div class=txtcol>
    <div class=head><span class=num>{n}</span><h2>{esc(s['title'])}</h2></div>
    <div class=meta>{ts(s['t'])} &middot; {esc(s.get('tool') or 'fingers')}{hl}</div>
    {quote}
    <ul class=lines>{bullets}</ul>
    {''.join(detail)}
    {caut}
  </div>
</div>""")
    tools_list = "".join(f"<li>{esc(t)}</li>" for t in plan.get("tools_summary", []))
    page = f"""<!doctype html><html lang="en"><head><meta charset=utf-8><style>
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
.noimg {{ border:1px dashed #b3562e; color:#6b6b5f; font-size: 11px; padding: 6mm 4mm; }}
.head {{ display:flex; align-items:center; gap: 3mm; margin-bottom: 1.5mm; }}
.num {{ flex:none; width: 7.5mm; height: 7.5mm; border-radius: 50%; background:#2f4632; color:#fff; font-family: "Inter", system-ui, sans-serif; font-size: 11px; text-align:center; line-height: 7.5mm; }}
h2 {{ font-size: 14px; color:#2f4632; }}
.meta {{ font-size: 11px; color:#6b6b5f; margin-bottom: 2mm; }}
.hl {{ color:#b3562e; }}
p {{ font-size: 11.5px; line-height: 1.45; margin-bottom: 2mm; }}
.dt {{ font-size: 10.5px; color:#444a42; margin-bottom: 1mm; }}
.dt b {{ color:#2f4632; }}
.caution {{ border-left: 2px solid #b3562e; padding-left: 2mm; font-size: 10.5px; color:#b3562e; margin-top: 2mm; }}
.precaution {{ border: 1px dashed #b3562e; padding: 1.5mm; font-size: 10px; color:#7c3a1e; margin-top: 2mm; }}
.quote {{ font-size: 10.5px; color:#5c6154; margin: 1mm 0 2mm; }}
ul.lines {{ margin: 0 0 2mm 4mm; padding: 0; font-size: 11.5px; }}
ul.lines li {{ margin: 1mm 0; }}
</style></head><body>
<div class=cover>
  <h1>{esc(plan['device'])}<span class=dot>.</span></h1>
  <div class=sub>Teardown and reassembly guide &middot; {len(steps)} steps &middot; generated from video footage</div>
  <div class=banner>Demo output &mdash; not validated repair instructions. Times are about &plusmn;30 seconds. Follow manufacturer service manuals for actual repairs. A highlight is drawn only for a direct segmentation match.</div>
  <div class=tools>
    <h3>Tools in this video</h3>
    <ul>{tools_list or "<li>none named</li>"}</ul>
    <h3>Parts named</h3>
    <ul>{"".join(f"<li>{esc(p)}</li>" for p in unique_parts(steps)) or "<li>none named</li>"}</ul>
  </div>
</div>
{''.join(blocks)}
</body></html>"""
    jd = os.path.join(DATA, job_id)
    imgdir = os.path.join(jd, "steps-img")
    os.makedirs(imgdir, exist_ok=True)
    for i, s in enumerate(steps):
        if not s.get("image"):
            continue  # degraded step: no frame to link; the page shows a note instead
        srcimg = os.path.join(jd, s["image"])
        dst = os.path.join(imgdir, f"{i + 1}.png")
        if os.path.isfile(srcimg):
            if os.path.exists(dst):
                os.remove(dst)
            try:
                os.link(srcimg, dst)
            except OSError:
                shutil.copyfile(srcimg, dst)
    hp = os.path.join(jd, "guide-print.html")
    with open(hp, "w", encoding="utf-8") as fh:
        fh.write(page)
    pdf = os.path.join(jd, "guide.pdf")
    partial = pdf + ".partial"
    if os.path.exists(partial):
        os.remove(partial)
    # A private profile keeps this print from attaching to a Chrome that is
    # already open on the debugging port.
    profile = tempfile.mkdtemp(prefix="teardown-pdf-")
    proc = None
    try:
        proc = subprocess.Popen(
            [_chrome_bin(),
             "--headless=new", "--disable-gpu", "--disable-dev-shm-usage",
             f"--user-data-dir={profile}", "--remote-debugging-port=0",
             "--no-first-run", f"--print-to-pdf={partial}",
             "--no-pdf-header-footer", "file://" + os.path.abspath(hp)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Current Chrome often writes the PDF and then stays up on a dead
        # session bus. Treat a finished file as success and stop the process.
        # A file is finished only when Chrome has exited AND the bytes are a
        # complete PDF; a size check alone can promote a truncated write.
        deadline = time.time() + 45
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if is_complete_pdf(partial):
                break
            time.sleep(0.15)
    except OSError:
        return None
    finally:
        if proc is not None and proc.poll() is None:
            if is_complete_pdf(partial):
                # Complete bytes on disk; the lingering process is the known
                # dead-session-bus hang, not more output to wait for.
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    if is_complete_pdf(partial):
        os.replace(partial, pdf)
    elif os.path.exists(partial):
        os.remove(partial)
    return pdf if os.path.exists(pdf) else None


def is_complete_pdf(path: str) -> bool:
    """True when path holds a complete PDF: %PDF header, %%EOF trailer."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) < 1000:
            return False
        with open(path, "rb") as fh:
            head = fh.read(5)
            fh.seek(max(0, os.path.getsize(path) - 1024), os.SEEK_SET)
            tail = fh.read()
    except OSError:
        return False
    return head.startswith(b"%PDF") and b"%%EOF" in tail
