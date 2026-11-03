"""YouTube download for one job, with the failure classified from stderr."""
import os
import re
import subprocess
import time

from jobs import JOBS, set_stage

def _download(job_id, url, video_path):
    """yt-dlp with live progress into JOBS; classifies the real stderr on
    failure. No alternate-client bypasses: if YouTube bot-checks this
    server we say so plainly."""
    cmd = ["yt-dlp", "--ignore-config", "--no-playlist",
           "--use-extractors", "youtube*",
           "--max-filesize", "140m",
           "-f", "bv*[height<=720]+ba/b[height<=720]/b",
           "--merge-output-format", "mp4", "--newline",
           "--js-runtimes", "deno", "--retries", "0",
           "--extractor-retries", "0", "--fragment-retries", "0",
           "-o", video_path, url]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        JOBS[job_id].update(status="error",
                            error="the demo's downloader is unavailable right now")
        return False
    lines = []
    t0 = time.time()
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            lines.append(line)
            m = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+\s*\S+)(?:\s+at\s+(\S+))?", line)
            if m:
                frac = min(1.0, float(m.group(1)) / 100.0)
                det = f"{m.group(1)}% of {m.group(2)}"
                if m.group(3):
                    det += f" at {m.group(3)}"
                set_stage(job_id, "downloading the video", round(5 * frac, 1), det)
            if time.time() - t0 > 600:
                proc.kill()
                break
        proc.wait(timeout=60)
    except Exception:
        proc.kill()
    if proc.returncode == 0 and os.path.exists(video_path):
        return True
    tail = " | ".join(lines[-12:])
    print(f"[yt-dlp fail job {job_id[:8]}] {tail[:4000]}", flush=True)
    if os.path.exists(video_path):
        os.remove(video_path)
    low = tail.lower()
    if "no supported javascript runtime" in low or ("ejs" in low and "not available" in low):
        msg = "the server's YouTube downloader setup is incomplete - please try a file upload while it is repaired"
    elif ("confirm" in low and "bot" in low) or "sign in to" in low:
        msg = ("YouTube is blocking this demo's server, not your video - it makes "
               "datacenter servers prove they are not bots, and this one can't. "
               "Save the video yourself and upload the file here instead.")
    elif "http error 403" in low:
        msg = ("YouTube refused this download (HTTP 403). This can be a server access "
               "restriction or a downloader compatibility issue; the cause is not confirmed. "
               "You can upload a video file instead.")
    elif "max-filesize" in low or "larger than" in low:
        msg = "that video is over this demo's 140 MB download limit - use a shorter or lower-quality clip"
    elif "unsupported url" in low:
        msg = "that link doesn't look like a YouTube video page"
    elif "private" in low or "unavailable" in low or "removed" in low or "copyright" in low:
        msg = "YouTube says that video is unavailable - check it plays publicly without signing in"
    else:
        msg = "could not download that link - check it plays publicly and is under 20 minutes"
    JOBS[job_id].update(status="error", error=msg, pct=None, detail="")
    return False
