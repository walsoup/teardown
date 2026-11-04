"""HTTP handler: upload admission, guide pages, and media."""
import html as html_mod
import json
import os
import re
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import budget
from config import DATA, MAX_UPLOAD_BYTES, RATE_LIMIT_PER_HOUR
from http_util import (
    _valid_cookie_ids,
    client_ip,
    cookie_header,
    csrf_ok,
    csrf_token,
    new_session_cookie,
    session_id,
    json_for_script,
    origin_ok,
    parse_byte_range,
    redact,
    safe_job_path,
    youtube_url_ok,
)
from jobs import ADMIT, JOBS, RATE, _ACTIVE_STATUSES, load_plan
from pages import (
    CSS,
    CSS_EXTRA,
    GUIDE,
    INDEX,
    _busy_page,
    _error_page,
    _missing_page,
    job_card,
)
from pdf import build_pdf, is_complete_pdf
from upload import _boundary_token, _carve, _clean_credit, _file_part, _stream, _text_field
from worker import run_job

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def setup(self):
        super().setup()
        try:
            self.request.settimeout(30)
        except OSError:
            pass

    def _send(self, body, ctype="text/html; charset=utf-8", status=200, extra=None, cache="no-store"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                         "font-src https://fonts.gstatic.com; img-src 'self' data:; "
                         "media-src 'self'; base-uri 'none'; form-action 'self'; "
                         "frame-ancestors 'none'")
        if cache:
            self.send_header("Cache-Control", "private, no-store" if cache == "no-store" else cache)
        host = os.environ.get("HOST", "127.0.0.1")
        if host not in ("127.0.0.1", "localhost", "::1"):
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def _send_file(self, fp, ctype):
        """Serve a file with HTTP Range support so <video> seeking works.

        Browsers issue Range requests for media; without a 206 response the
        video element cannot seek and currentTime assignment is ignored.
        The body is streamed in 1 MB chunks so a full-file range is not one allocation.
        """
        size = os.path.getsize(fp)
        kind, start, end = parse_byte_range(self.headers.get("Range"), size)
        if kind == "unsat":
            self._send("", "text/plain", 416, extra={"Content-Range": f"bytes */{size}"})
            return
        status = 206 if kind == "partial" else 200
        extra = {"Accept-Ranges": "bytes"}
        if kind == "partial":
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "private")
        self.send_header("Accept-Ranges", "bytes")
        if kind == "partial":
            self.send_header("Content-Range", extra["Content-Range"])
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(fp, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/budget":
            try:
                st = budget.status()
                body = json.dumps({"basis": "conservative in-app estimate (worst-case reservations settled per job), not provider-billed spend",
                                   "budget_usd": st["cap_usd"],
                                   "spent_usd": round(st["spent_usd"], 4),
                                   "reserved_usd": round(st["reserved_usd"], 4),
                                   "remaining_usd": round(st["remaining_usd"], 4),
                                   "guides_built": st["jobs"]})
            except Exception:
                body = json.dumps({"error": "budget ledger unreachable"})
            self._send(body, "application/json")
            return
        if u.path == "/":
            err = parse_qs(u.query).get("e", [""])[0] if u.query else ""
            err_html = f'<div class=err>{html_mod.escape(err)}</div>' if err else ""
            mine = [x for x in _valid_cookie_ids(self.headers.get("Cookie")) if x in JOBS]
            cards = "".join(job_card(j) for j in reversed(mine)) or \
                '<span class="mut">guides you build in this browser show up here</span>'
            model = os.environ.get("TEARDOWN_SPARK_MODEL", "")
            if model.endswith("-contributor"):
                training = ("This demo uses Meta's contributor model, so Meta may use "
                            "submitted footage to train its models.")
            else:
                training = ("Uploads are sent to Meta for transcription, planning, and segmentation.")
            sid = session_id(self.headers.get("Cookie"))
            extra = None
            if not sid:
                sid, cookie = new_session_cookie()
                extra = {"Set-Cookie": cookie}
            self._send(INDEX.replace("__CSS__", CSS + CSS_EXTRA).replace("__REFRESH__", "")
                       .replace("__ERROR__", err_html)
                       .replace("__JOBS__", cards)
                       .replace("__CSRF__", html_mod.escape(csrf_token(sid)))
                       .replace("__TRAINING__", html_mod.escape(training)),
                       extra=extra)
            return
        ms = re.match(r"^/jobs/([\w-]+)/status\.json$", u.path)
        if ms:
            job = ms.group(1)
            if not self._owns(job):
                self._send('{"error":"not found"}', "application/json", 404)
                return
            if load_plan(job):
                self._send('{"status":"done"}', "application/json")
                return
            st = JOBS.get(job)
            if not st:
                self._send('{"status":"missing"}', "application/json")
                return
            self._send(json.dumps({
                "status": st.get("status"), "stage": st.get("stage", ""),
                "pct": st.get("pct"), "detail": st.get("detail", ""),
                "elapsed_s": int(time.time() - st.get("created", time.time())),
                "error": st.get("error", "")}), "application/json")
            return
        m = re.match(r"^/jobs/([\w-]+)(?:/(.*))?$", u.path)
        if m and m.group(2) is None:
            job = m.group(1)
            if not self._owns(job):
                self._send('<p class=mut>guide not found or expired - <a href=/>back to jobs</a></p>', status=404)
                return
            plan = load_plan(job)
            if not plan:
                st = JOBS.get(job)
                if st and st.get("status") in ("queued", "downloading", "processing"):
                    self._send(_busy_page(job, st), status=200)
                elif st and st.get("status") == "error":
                    self._send(_error_page(st.get("error", "unknown error")), status=200)
                else:
                    self._send(_missing_page(), status=404)
                return
            n_steps = len(plan["steps"])

            def step_html(i, s):
                from teardown.present import approx_clock, standard_precaution, step_lines
                esc = html_mod.escape
                active_class = " active" if i == 0 else ""

                meta_parts = [esc(approx_clock(s.get("t") or 0))]
                tool_val = (s.get("tool") or "").strip()
                if tool_val:
                    meta_parts.append(esc(tool_val))
                part_val = (s.get("part") or "").strip()
                if part_val:
                    meta_parts.append(esc(part_val))
                meta_line = f'<div class="step-meta mono-label">{" &middot; ".join(meta_parts)}</div>'""

                if s.get("segmented"):
                    hl_badge = ('<span class="step-hl-badge mono-label"><span class="material-symbols-outlined" aria-hidden="true" style="font-size:14px;color:var(--terracotta);margin-right:2px;">visibility</span><b class="step-hl">part highlighted</b></span>')
                else:
                    hl_badge = '<span class="step-hl-badge mono-label"><b class="step-hl">not highlighted</b></span>'

                # Hardware & fastener registry block
                reg_rows = []
                if s.get("fasteners", "").strip():
                    reg_rows.append(f'<div class="registry-row"><span class="registry-type mono-label">Fasteners:</span> <span class="registry-val">{esc(s["fasteners"].strip())}</span></div>')
                if s.get("connectors", "").strip():
                    reg_rows.append(f'<div class="registry-row"><span class="registry-type mono-label">Connectors:</span> <span class="registry-val">{esc(s["connectors"].strip())}</span></div>')
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

                step_title_esc = esc(s["title"])
                img_url = f"/jobs/{job}/{s['image']}" if s.get("image") else ""
                if img_url:
                    img_wrap = (
                        f'<div class="step-image-wrap" data-full="{img_url}" data-title="{step_title_esc}" title="Click to view full-resolution image">'
                        f'<img loading="lazy" class="step-img" src="{img_url}" alt="{step_title_esc}">'
                        f'<button type="button" class="inspect-btn mono-label"><span class="material-symbols-outlined" aria-hidden="true" style="font-size:14px;">zoom_in</span> Inspect</button>'
                        f'</div>'
                    )
                else:
                    reason = esc((s.get("step_error") or "no frame could be taken from the video").strip())
                    img_wrap = f'<p class="step-desc mut">No usable frame for this step. {reason}</p>'
                films = []
                for cand in s.get("candidates") or []:
                    if not cand or cand == s.get("image"):
                        continue
                    films.append(
                        f'<button type="button" class="film-btn" data-src="/jobs/{job}/{esc(cand)}">'
                        f'<img alt="" src="/jobs/{job}/{esc(cand)}"></button>'
                    )
                film_html = f'<div class="filmstrip">{"".join(films)}</div>' if films else ""
                bullets = "".join(
                    f'<li class="{esc(item["type"])}">{esc(item["text"])}</li>'
                    for item in step_lines(s)
                )
                source = (s.get("source") or "").strip()
                quote_html = (
                    f'<button type="button" class="anchor-quote" data-t="{float(s.get("t") or 0)}">'
                    f'&ldquo;{esc(source)}&rdquo;</button>'
                ) if source else ""
                precaution = standard_precaution(s.get("part") or "")
                precaution_html = f'<p class="precaution">{esc(precaution)}</p>' if precaution else ""

                return (
                    f'<div class="step-item{active_class}" data-index="{i}" data-t="{s["t"]}">'
                    f'  <div class="step-eyebrow-row">'
                    f'    <span class="step-badge mono-label">Step {i + 1} of {n_steps}</span>'
                    f'    {hl_badge}'
                    f'  </div>'
                    f'  <h2 class="step-title"><span class="step-num">{i + 1}</span> {step_title_esc}</h2>'
                    f'  {meta_line}'
                    f'  {img_wrap}'
                    f'  {film_html}'
                    f'  {quote_html}'
                    f'  <ul class="bullet-list">{bullets}</ul>'
                    f'  {reg_html}'
                    f'  {caut_html}'
                    f'  {precaution_html}'
                    f'</div>'
                )

            def rail_row_html(i, s):
                esc = html_mod.escape
                active_class = " active" if i == 0 else ""
                from teardown.present import approx_clock
                ts_str = html_mod.escape(approx_clock(s.get("t") or 0))
                num_str = f"{i + 1:02d}"
                tool_str = esc(s.get("tool") or "fingers")
                if s.get("image"):
                    thumb_html = f'<img loading="lazy" class="row-thumb" src="/jobs/{job}/{s["image"]}" alt="{esc(s["title"])}">'
                else:
                    thumb_html = '<span class="row-thumb row-thumb-missing mono-label">no frame</span>'
                return (
                    f'<div class="rail-row{active_class}" id="rail-row-{i}" data-index="{i}" data-title="{esc(s["title"])}" role="button" tabindex="0">'
                    f'  <span class="row-num mono-label">{num_str}</span>'
                    f'  <div class="row-thumb-wrap">'
                    f'    {thumb_html}'
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
                f'<div class="progress-seg{" active" if i == 0 else ""}" role="button" tabindex="0" data-index="{i}" title="Step {i + 1}: {html_mod.escape(s["title"])}"></div>'
                for i, s in enumerate(plan["steps"])
            )
            steps_html = "".join(step_html(i, s) for i, s in enumerate(plan["steps"]))
            rail_html = "".join(rail_row_html(i, s) for i, s in enumerate(plan["steps"]))
            step_times = json_for_script([s["t"] for s in plan["steps"]])
            step_hardware = json_for_script([{"fasteners": s.get("fasteners", ""), "connectors": s.get("connectors", "")} for s in plan["steps"]])
            poster = plan["steps"][0].get("image") if plan.get("steps") else ""
            poster_url = f"/jobs/{job}/{poster}" if poster else ""

            from teardown.present import unique_parts
            tools = plan.get("tools_summary") or []
            tools_html = ("<ul>" + "".join(f"<li>{html_mod.escape(str(t))}</li>" for t in tools) + "</ul>"
                          if tools else "<p>No tools were named.</p>")
            parts = unique_parts(plan["steps"])
            parts_html = ("<ul>" + "".join(f"<li>{html_mod.escape(p)}</li>" for p in parts) + "</ul>"
                          if parts else "<p>No parts were named.</p>")
            trunc_html = ('<p class="reassembly-banner">This guide was cut at the step limit, so the ending of the video may be missing.</p>'
                          if plan.get("truncated") else "")
            credit = (plan.get("attribution") or "").strip()
            credit_html = f'<p class="mono-label">Source footage: {html_mod.escape(credit)}</p>' if credit else ""
            # Single-pass substitution: model-controlled text (device name,
            # quotes, hardware notes) can literally contain token-looking
            # text such as "__PROGRESS__". A chained str.replace would
            # re-expand those into page markup; substituting all tokens in
            # one regex pass never rescans inserted content.
            subs = {
                "__STEPHARDWARE__": step_hardware,
                "__STEPTIMES__": step_times,
                "__CSS__": CSS,
                "__DEVICE__": html_mod.escape(plan["device"]),
                "__NSTEPS__": str(n_steps),
                "__JOB__": job,
                "__POSTER__": poster_url,
                "__TOOLS__": tools_html,
                "__PARTS__": parts_html,
                "__TRUNCATION__": trunc_html,
                "__ATTRIBUTION__": credit_html,
                "__STEPS__": steps_html,
                "__RAIL__": rail_html,
                "__PROGRESS__": progress_html,
            }
            resp = re.sub(r"__(?:STEPHARDWARE|STEPTIMES|CSS|DEVICE|NSTEPS|JOB|POSTER|TOOLS|PARTS|TRUNCATION|ATTRIBUTION|STEPS|RAIL|PROGRESS)__",
                          lambda match: subs[match.group(0)], GUIDE)
            if os.environ.get("TEARDOWN_NO_PDF") == "1":
                resp = re.sub(r'<a class="pill header-pdf".*?</a>', '', resp, flags=re.S)
            self._send(resp)
            return
        if m and m.group(2) == "guide.pdf":
            job = m.group(1)
            if os.environ.get("TEARDOWN_NO_PDF") == "1":
                self._send("pdf download is disabled in this demo", "text/plain", 404)
                return
            if not self._owns(job):
                self._send("not found", "text/plain", 404)
                return
            pdf = safe_job_path(job, "guide.pdf")
            if pdf and not is_complete_pdf(pdf):
                # A previous run cached a truncated PDF; rebuild instead of
                # serving it forever.
                try:
                    os.remove(pdf)
                except OSError:
                    pass
                pdf = None
            if not pdf:
                try:
                    build_pdf(job)
                except Exception as e:
                    self._send(f"pdf failed: {html_mod.escape(redact(e)[:200])}", "text/plain", 500)
                    return
                pdf = safe_job_path(job, "guide.pdf")
            if pdf:
                with open(pdf, "rb") as fh:
                    body = fh.read()
                self._send(body, "application/pdf",
                           extra={"Content-Disposition": "attachment; filename=teardown-guide.pdf"})
            else:
                self._send("guide not ready", "text/plain", 404)
            return
        if m and m.group(2):
            if not self._owns(m.group(1)):
                self._send("not found", "text/plain", 404)
                return
            fp = safe_job_path(m.group(1), m.group(2))
            if fp:
                ct = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                      ".webp": "image/webp", ".mp4": "video/mp4", ".pdf": "application/pdf"}.get(
                    os.path.splitext(fp)[1].lower(), "application/octet-stream")
                self._send_file(fp, ct)
            else:
                self._send("not found", "text/plain", 404)
            return
        self._send("not found", "text/plain", 404)

    def _redirect(self, msg):
        clean = re.sub(r"[^A-Za-z0-9 .$:-]", "", msg)[:140].replace(" ", "%20")
        self.send_response(303)
        self.send_header("Location", "/?e=" + clean)
        self.end_headers()

    def _job_cookie(self, job):
        ids = _valid_cookie_ids(self.headers.get("Cookie"))
        if job not in ids:
            ids.append(job)
        return cookie_header(ids[-12:])

    def _owns(self, job):
        return job in _valid_cookie_ids(self.headers.get("Cookie"))

    def _drop_job(self, job, directory):
        JOBS.pop(job, None)
        shutil.rmtree(directory, ignore_errors=True)

    def do_POST(self):
        if self.path.split("?")[0] != "/jobs":
            self._send("not found", "text/plain", 404)
            return
        job = None
        directory = None
        started = False
        try:
            if not origin_ok(self):
                print("[origin reject] origin=%r host=%r peer=%r xfh=%r xfp=%r ua=%r" % (
                    self.headers.get("Origin"), self.headers.get("Host"),
                    self.client_address[0], self.headers.get("X-Forwarded-Host"),
                    self.headers.get("X-Forwarded-Proto"),
                    (self.headers.get("User-Agent") or "")[:80]), flush=True)
                self._redirect("that request did not come from this site")
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_UPLOAD_BYTES:
                self._redirect("video too large - keep it under 150 MB")
                return
            ip = client_ip(self)
            now = time.time()
            with ADMIT:
                hits = [t for t in RATE.get(ip, []) if now - t < 3600]
                if len(hits) >= RATE_LIMIT_PER_HOUR:
                    self._redirect("slow down - this demo allows a couple of guides per hour")
                    return
                active = sum(1 for state in list(JOBS.values())
                             if state.get("status") in _ACTIVE_STATUSES)
                if active >= 2:
                    self._redirect("the demo is already building two guides - try again in a few minutes")
                    return
                hits.append(now)
                RATE[ip] = hits
                job = uuid.uuid4().hex
                JOBS[job] = {"status": "queued", "stage": "queued", "pct": None,
                             "detail": "", "created": now, "attribution": ""}
            directory = os.path.join(DATA, job)
            os.makedirs(directory, exist_ok=True)
            video_path = os.path.join(directory, "video.mp4")
            ctype = self.headers.get("Content-Type", "")
            url = ""
            attribution = _clean_credit(self.headers.get("X-TD-Attribution"))
            rights = (self.headers.get("X-TD-Rights") or "").strip().lower()
            form_csrf = ""
            if ctype.startswith("application/octet-stream"):
                if not _stream(self.rfile, length, video_path):
                    self._drop_job(job, directory)
                    self._redirect("the upload was cut off - try again")
                    return
            else:
                boundary = _boundary_token(ctype)
                tmp = os.path.join(directory, "upload.bin")
                if not boundary or not _stream(self.rfile, length, tmp):
                    self._drop_job(job, directory)
                    self._redirect("the upload was cut off - try again")
                    return
                size = os.path.getsize(tmp)
                with open(tmp, "rb") as fh:
                    head = fh.read(min(size, 262144))
                    fh.seek(max(0, size - 65536))
                    tail = fh.read()
                form_csrf = _text_field(head, "csrf")
                rights = rights or _text_field(tail, "rights").lower() or _text_field(head, "rights").lower()
                attribution = attribution or _clean_credit(
                    _text_field(tail, "attribution") or _text_field(head, "attribution"))
                url = _text_field(tail, "url") or _text_field(head, "url")
                filename, file_at = _file_part(head)
                if url:
                    pass
                elif filename and file_at is not None:
                    _carve(tmp, file_at, video_path, boundary)
                else:
                    self._drop_job(job, directory)
                    self._redirect("add a video file or a youtube link first")
                    return
                if os.path.exists(tmp):
                    os.remove(tmp)
            if not csrf_ok(self, self.headers.get("X-TD-CSRF"), form_csrf):
                self._drop_job(job, directory)
                self._redirect("the form token did not match - reload the page and try again")
                return
            if rights != "yes":
                self._drop_job(job, directory)
                self._redirect("confirm you have the right to upload this footage")
                return
            if url and not youtube_url_ok(url):
                self._drop_job(job, directory)
                self._redirect("only public youtube links work in this demo")
                return
            if not url and not os.path.isfile(video_path):
                self._drop_job(job, directory)
                self._redirect("add a video file or a youtube link first")
                return
            JOBS[job]["attribution"] = attribution
            threading.Thread(target=run_job, args=(job, video_path, url, ip), daemon=True).start()
            started = True
            self.send_response(303)
            self.send_header("Location", "/jobs/" + job)
            self.send_header("Set-Cookie", self._job_cookie(job))
            self.end_headers()
        except Exception:
            if job and directory and not started:
                self._drop_job(job, directory)
            self._redirect("that request could not be accepted")
