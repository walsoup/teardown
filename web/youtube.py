"""YouTube download for one job.

Two routes, tried in order:

1. Invidious API instances. These are volunteer-run YouTube frontends whose
   servers can still reach YouTube when datacenter IPs (like this demo's
   host) get bot-checked. We read the video's adaptive format list from the
   instance with local=true, which rewrites the media URLs to proxy through
   the instance, download one video-only and one audio-only stream through
   it, and mux them locally with ffmpeg. No account, no cookies.
2. yt-dlp direct. Kept for self-hosters on residential connections; on a
   datacenter host YouTube bot-checks it and the failure is classified
   plainly from stderr.
"""
import json
import os
import re
import subprocess
import time
from urllib.parse import parse_qs, urlparse

import requests

from config import MAX_DURATION_S
from jobs import JOBS, set_stage

VIDEO_CAP_BYTES = 140 * 1024 * 1024
AUDIO_CAP_BYTES = 48 * 1024 * 1024
DL_DEADLINE_S = 600
PRIMARY_INSTANCE = "https://yt.chocolatemoo53.com"
INSTANCES_URL = "https://api.invidious.io/instances.json"

_instances_cache = {"at": 0.0, "list": []}

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

def _extract_video_id(url):
    """Pull the 11-char video id out of a YouTube URL, or None."""
    try:
        p = urlparse(url or "")
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    cand = None
    if host.endswith("youtu.be"):
        cand = p.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if p.path == "/watch":
            cand = (parse_qs(p.query).get("v") or [None])[0]
        else:
            m = re.match(r"^/(shorts|embed|live|v)/([A-Za-z0-9_-]{11})", p.path)
            if m:
                cand = m.group(2)
    if cand and _VIDEO_ID_RE.match(cand):
        return cand
    return None

def _instances():
    """Ordered instance list: env override, known-good primary, then the
    public directory (cached 10 min). Best-effort; failures just shorten it."""
    out = []
    env = os.environ.get("TEARDOWN_INVIDIOUS", "")
    for raw in env.split(","):
        raw = raw.strip().rstrip("/")
        if raw.startswith("https://"):
            out.append(raw)
    out.append(PRIMARY_INSTANCE)
    now = time.time()
    if now - _instances_cache["at"] > 600:
        try:
            r = requests.get(INSTANCES_URL, timeout=8)
            found = []
            for host, meta in r.json():
                if (isinstance(meta, dict) and meta.get("type") == "https"
                        and meta.get("api") and isinstance(host, str)
                        and "." in host):
                    found.append(f"https://{host}")
            _instances_cache.update(at=now, list=found)
        except Exception:
            _instances_cache["at"] = now  # don't hammer the directory
    out.extend(_instances_cache["list"])
    seen, ordered = set(), []
    for base in out:
        if base not in seen:
            seen.add(base)
            ordered.append(base)
    return ordered[:6]

def _pick_formats(adaptive, max_height=480):
    """Choose one video-only and one audio-only adaptive format.
    Prefers h264 (avc1) at the highest quality up to max_height: the guide
    player and the model ingest both handle h264/mp4 without a re-encode.
    Returns (video_format, audio_format) or (None, None)."""
    videos, audios = [], []
    for f in adaptive or []:
        ftype = f.get("type") or ""
        if ftype.startswith("video/"):
            videos.append(f)
        elif ftype.startswith("audio/"):
            audios.append(f)

    def height(f):
        m = re.match(r"(\d+)p", f.get("qualityLabel") or "")
        return int(m.group(1)) if m else 0

    def codec_rank(f):
        t = f.get("type") or ""
        if "avc1" in t:
            return 0
        if "mp4" in t:
            return 1
        return 2

    in_cap = [f for f in videos if 0 < height(f) <= max_height]
    pool = in_cap or videos
    video = None
    if pool:
        video = sorted(pool, key=lambda f: (codec_rank(f), -height(f)))[0]
    audio = None
    if audios:
        def audio_rank(f):
            t = f.get("type") or ""
            container = 0 if "mp4" in t else 1
            try:
                br = -int(f.get("bitrate") or 0)
            except (TypeError, ValueError):
                br = 0
            return (container, br)
        audio = sorted(audios, key=audio_rank)[0]
    return video, audio

def _stream_to_file(job_id, url, dest, cap, pct_lo, pct_hi, label, deadline):
    """Stream one media URL to disk with progress; False on any failure."""
    got = 0
    try:
        with requests.get(url, stream=True, timeout=(10, 60)) as r:
            if r.status_code != 200:
                print(f"[yt fetch job {job_id[:8]}] {label}: HTTP {r.status_code}", flush=True)
                return False
            total = int(r.headers.get("Content-Length") or 0)
            if total > cap:
                print(f"[yt fetch job {job_id[:8]}] {label}: {total} bytes over cap", flush=True)
                return False
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    got += len(chunk)
                    if got > cap or time.time() > deadline:
                        print(f"[yt fetch job {job_id[:8]}] {label}: cap/deadline hit", flush=True)
                        return False
                    if total:
                        frac = pct_lo + (pct_hi - pct_lo) * min(1.0, got / total)
                        set_stage(job_id, "downloading the video", round(frac, 1),
                                  f"{got // (1024*1024)} of {total // (1024*1024)} MB ({label})")
                    else:
                        set_stage(job_id, "downloading the video", None,
                                  f"{got // (1024*1024)} MB ({label})")
    except requests.RequestException as e:
        print(f"[yt fetch job {job_id[:8]}] {label}: {type(e).__name__} {e}", flush=True)
        return False
    return got > 0

def _ffmpeg_mux(vpart, apart, out, video_ok_copy, audio_ok_copy):
    vargs = ["-c:v", "copy"] if video_ok_copy else [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    aargs = ["-c:a", "copy"] if audio_ok_copy else ["-c:a", "aac", "-b:a", "128k"]
    cmd = (["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", vpart, "-i", apart] + vargs + aargs +
           ["-movflags", "+faststart", out])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)

def _invidious_download(job_id, video_id, video_path):
    """Try Invidious instances in order. True on success, False when the
    route is exhausted and the yt-dlp fallback should run."""
    deadline = time.time() + DL_DEADLINE_S
    last_note = ""
    for base in _instances():
        if time.time() > deadline:
            break
        set_stage(job_id, "downloading the video", 2.0,
                  f"resolving via {urlparse(base).hostname}")
        try:
            r = requests.get(f"{base}/api/v1/videos/{video_id}",
                             params={"local": "true"}, timeout=20)
        except requests.RequestException as e:
            last_note = f"{base}: {type(e).__name__}"
            continue
        if r.status_code != 200:
            last_note = f"{base}: HTTP {r.status_code}"
            continue
        try:
            info = r.json()
        except (ValueError, json.JSONDecodeError):
            last_note = f"{base}: bad json"
            continue
        if "error" in info:
            err = str(info.get("error")).lower()
            if any(k in err for k in ("private", "unavailable", "not exist",
                                      "removed", "copyright", "deleted")):
                return _fail(job_id, "YouTube says that video is unavailable - "
                                     "check it plays publicly without signing in")
            if "live" in err or "premiere" in err:
                return _fail(job_id, "that looks like a live stream or premiere - "
                                     "this demo works on finished videos")
            last_note = f"{base}: {err[:120]}"
            continue
        length = info.get("lengthSeconds") or 0
        if not length:
            return _fail(job_id, "that looks like a live stream or premiere - "
                                 "this demo works on finished videos")
        if length > MAX_DURATION_S:
            return _fail(job_id, f"that video is about {round(length / 60)} minutes - "
                                 "this demo handles up to 20")
        vfmt, afmt = _pick_formats(info.get("adaptiveFormats"))
        if not vfmt or not afmt or not vfmt.get("url") or not afmt.get("url"):
            last_note = f"{base}: no usable streams"
            continue
        vpart, apart = video_path + ".vpart", video_path + ".apart"
        ok = (_stream_to_file(job_id, vfmt["url"], vpart, VIDEO_CAP_BYTES,
                              5.0, 75.0, "video", deadline)
              and _stream_to_file(job_id, afmt["url"], apart, AUDIO_CAP_BYTES,
                                  75.0, 95.0, "audio", deadline))
        if ok:
            set_stage(job_id, "downloading the video", 97.0, "joining audio and video")
            try:
                proc = _ffmpeg_mux(vpart, apart, video_path,
                                   "avc1" in (vfmt.get("type") or ""),
                                   "mp4" in (afmt.get("type") or ""))
                ok = proc.returncode == 0 and os.path.isfile(video_path)
                if not ok:
                    print(f"[yt mux fail job {job_id[:8]}] "
                          f"{(proc.stderr or '')[:2000]}", flush=True)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"[yt mux fail job {job_id[:8]}] {e}", flush=True)
                ok = False
        for part in (vpart, apart):
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
        if ok:
            return True
        last_note = f"{base}: stream fetch/mux failed"
    print(f"[invidious route exhausted job {job_id[:8]}] {last_note}", flush=True)
    return False

def _fail(job_id, msg):
    JOBS[job_id].update(status="error", error=msg, pct=None, detail="")
    return False

def _ytdlp_download(job_id, url, video_path):
    """yt-dlp with live progress into JOBS; classifies the real stderr on
    failure. Direct route - works where the host's IP is not bot-checked."""
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
        return _fail(job_id, "the demo's downloader is unavailable right now")
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
            if time.time() - t0 > DL_DEADLINE_S:
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
    if "live stream" in low or "live event" in low or "premiere" in low:
        msg = "that looks like a live stream or premiere - this demo works on finished videos"
    elif "private" in low or "unavailable" in low or "removed" in low or "copyright" in low:
        msg = "YouTube says that video is unavailable - check it plays publicly without signing in"
    elif "no supported javascript runtime" in low or ("ejs" in low and "not available" in low):
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
    else:
        msg = "could not download that link - check it plays publicly and is under 20 minutes"
    return _fail(job_id, msg)

def _download(job_id, url, video_path):
    """Invidious-proxy route first, direct yt-dlp as the fallback."""
    video_id = _extract_video_id(url)
    if video_id and _invidious_download(job_id, video_id, video_path):
        return True
    if JOBS.get(job_id, {}).get("status") == "error":
        return False  # classified already (live stream, too long)
    if not video_id:
        print(f"[yt job {job_id[:8]}] no video id in url, yt-dlp only", flush=True)
    return _ytdlp_download(job_id, url, video_path)
