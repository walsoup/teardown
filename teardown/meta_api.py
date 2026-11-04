"""Thin client for the Meta Model API.

Everything goes through https://api.meta.ai/v1 with a Bearer key from
the Model API dashboard. Set MODEL_API_KEY in your environment.

Docs used (read Oct/Nov 2026):
- Quickstart / Responses API: https://dev.meta.ai/docs/quickstart
- Video understanding (Files upload + input_file): https://dev.meta.ai/docs/video-understanding
- SAM 3.1 segmenting: https://dev.meta.ai/docs/sam/segmenting
- SAM output grammar: https://dev.meta.ai/docs/sam/reading-segmentation
- Voice Transcribe: https://dev.meta.ai/docs/api-reference/voice/transcribe
"""

from __future__ import annotations

import json
import os
import threading
import time

import requests

BASE_URL = "https://api.meta.ai/v1"


class MissingApiKey(Exception):
    """MODEL_API_KEY is not set or is blank. An Exception (not SystemExit)
    so `except Exception` pipeline handlers mark the job failed instead of
    leaving it stuck "processing" forever."""


class MetaApi:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY")
        if not self.api_key or not self.api_key.strip():
            raise MissingApiKey(
                "MODEL_API_KEY is not set. Create a key in the Model API "
                "dashboard (https://dev.meta.ai) under API keys, then:\n"
                "  export MODEL_API_KEY=..."
            )
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        # Per-thread usage: step illustration shares one client across
        # worker threads, and MeteredApi reads last_usage after respond()
        # returns. A plain shared attribute lets one thread's response
        # overwrite another's before it is read back.
        self.__dict__["_usage_tls"] = threading.local()
        self.last_usage = None

    @property
    def last_usage(self):
        return getattr(self.__dict__.get("_usage_tls"), "usage", None)

    @last_usage.setter
    def last_usage(self, value):
        tls = self.__dict__.get("_usage_tls")
        if tls is None:
            self.__dict__["_usage_tls"] = tls = threading.local()
        tls.usage = value

    def upload_file(self, path: str, purpose: str = "user_data") -> str:
        """Upload a file once, get back a file_id to reference in requests.

        The files endpoint throttles request bursts with a bare 400 (seen after
        many ASR window uploads in a row), so retry a bounded number of times
        with backoff. A deterministic rejection (e.g. an unsupported file
        type) is not retried.
        """
        delay = 5.0
        for attempt in range(4):
            with open(path, "rb") as fh:
                r = self.session.post(
                    f"{BASE_URL}/files",
                    timeout=300,
                    files={"file": (os.path.basename(path), fh)},
                    data={"purpose": purpose},
                )
            if r.status_code == 400 and "unsupported file type" in r.text.lower():
                r.raise_for_status()
            if r.status_code in (400, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(delay)
                delay = min(60.0, delay * 4)
                continue
            r.raise_for_status()
            return r.json()["id"]

    def respond(self, model: str, content: list[dict], timeout: int = 300, **extra) -> str:
        """One non-streaming Responses call. Returns the output_text."""
        self.last_usage = None
        r = self.session.post(
            f"{BASE_URL}/responses",
            timeout=timeout,
            json={
                "model": model,
                "input": [{"type": "message", "role": "user", "content": content}],
                **extra,
            },
        )
        r.raise_for_status()
        body = r.json()
        self.last_usage = body.get("usage")
        return _output_text(body)

    def respond_stream(self, model: str, content: list[dict], **extra):
        """Streaming Responses call. Yields the raw event dicts.

        Used for SAM 3.1: events feed the meta_sam_parser stream parser.
        """
        self.last_usage = None
        r = self.session.post(
            f"{BASE_URL}/responses",
            timeout=300,
            json={
                "model": model,
                "input": [{"type": "message", "role": "user", "content": content}],
                "stream": True,
                **extra,
            },
            stream=True,
        )
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line.removeprefix("data: ")
            if data.strip() == "[DONE]":
                break
            event = json.loads(data)
            etype = event.get("type", "")
            if etype == "response.completed":
                self.last_usage = (event.get("response") or {}).get("usage")
                yield event
                break
            if etype in ("response.failed", "error"):
                raise RuntimeError(f"API stream failed: {event}")
            yield event

    def transcribe(self, wav_path: str) -> str:
        """Transcribe a WAV file with Muse Voice Transcribe.

        The endpoint caps requests at 10 min / 32 MB, so longer audio is
        split into 8-minute chunks (ffmpeg segment muxer, lossless) and the
        transcripts are joined in order.
        """
        chunks = _chunk_wav(wav_path)
        if len(chunks) > 1:
            return " ".join(self._transcribe_chunk(c) for c in chunks)
        return self._transcribe_chunk(wav_path)

    def transcribe_timed(self, wav_path: str, window_s: float = 30.0, progress=None,
                         checkpoint_path: str | None = None, workers: int | None = None,
                         offset: float = 0.0) -> list[dict]:
        """Transcribe with approximate timing by transcribing small windows.

        The ASR endpoint returns no timestamps, so timing is established by
        cutting the audio into windows of known offsets and transcribing
        each window on its own. Windows overlap by about a second so a word
        on the boundary lands intact in one of them. A sub-second tail is
        merged into the previous window instead of becoming its own request.

        Finished windows are written to checkpoint_path as they complete, so
        a retry skips audio that was already paid for. `offset` (the audio
        stream's start_time in the video) is added to every window start.
        """
        duration = _probe_duration(wav_path)
        planned = plan_windows(duration, window_s)
        done = _load_checkpoint(checkpoint_path)
        pending = []
        ordered: list[dict] = []
        for start, length in planned:
            key = _window_key(start + offset)
            if key in done:
                ordered.append({"t": key, "text": done[key]})
            else:
                pending.append((start, length))
        if progress and planned:
            progress(len(planned) - len(pending), len(planned))
        if not pending:
            return ordered

        from concurrent.futures import ThreadPoolExecutor

        width = workers
        if width is None:
            width = int(os.environ.get("TEARDOWN_ASR_WORKERS", "6"))
        width = max(1, min(width, len(pending)))
        fresh: dict[float, str] = {}

        def work(item):
            start, length = item
            chunk = _cut_wav(wav_path, start, length)
            try:
                text = self._transcribe_chunk_retry(chunk)
            finally:
                try:
                    os.remove(chunk)
                except OSError:
                    pass
            return _window_key(start + offset), text or ""

        completed = len(planned) - len(pending)
        with ThreadPoolExecutor(max_workers=width) as pool:
            for key, text in pool.map(work, pending):
                fresh[key] = text
                _save_checkpoint(checkpoint_path, {**done, **fresh})
                completed += 1
                if progress:
                    progress(completed, len(planned))
        by_t = {item["t"]: item["text"] for item in ordered}
        by_t.update(fresh)
        return [{"t": _window_key(start + offset), "text": by_t.get(_window_key(start + offset), "")}
                for start, _length in planned]

    def _transcribe_chunk_retry(self, wav_path: str) -> str:
        """Retry a single window on rate limits and transient server errors.

        A retry bills one window, not the whole file. Other HTTP errors raise
        immediately so a bad request is not paid for four times.
        """
        delay = 1.0
        last: Exception | None = None
        for attempt in range(4):
            try:
                return self._transcribe_chunk(wav_path)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                last = exc
                if status not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last = exc
                if attempt == 3:
                    raise
            time.sleep(delay)
            delay = min(8.0, delay * 2)
        if last:
            raise last
        return ""

    def _transcribe_chunk(self, wav_path: str) -> str:
        self.last_usage = None
        with open(wav_path, "rb") as audio:
            r = self.session.post(
                f"{BASE_URL}/asr/transcribe",
                timeout=180,
                headers={"Accept": "application/json"},
                files={
                    "request": (
                        None,
                        json.dumps(
                            {
                                "model": "muse-voice-transcribe-1.0",
                                "audioEncoding": "WAV",
                                "mode": "PUSH_TO_TALK",
                            }
                        ),
                        "application/json",
                    ),
                    "audio": (os.path.basename(wav_path), audio, "audio/wav"),
                },
            )
        r.raise_for_status()
        body = r.json()
        # The buffered JSON body carries the transcript; be liberal about the
        # exact field shape and fall back to the raw text.
        if isinstance(body, dict):
            for key in ("transcript", "text"):
                if key in body:
                    return body[key]
            if "turns" in body:
                return " ".join(t.get("text", "") for t in body["turns"])
        return r.text


def plan_windows(duration: float, window_s: float = 30.0,
                 overlap_s: float = 1.0, tail_min_s: float = 1.0) -> list[tuple[float, float]]:
    """Return (start, length) cuts covering `duration`.

    A tail shorter than tail_min_s is merged into the previous window so a
    container duration of 1140.02s does not become its own API call. Every
    window except the last is lengthened by overlap_s so a word on the cut
    is intact in one request.
    """
    if duration <= 0 or window_s <= 0:
        return []
    count = max(1, int(-(-duration // window_s)))
    starts = [i * window_s for i in range(count)]
    if len(starts) >= 2 and (duration - starts[-1]) < tail_min_s:
        starts.pop()
    windows: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        if start >= duration:
            continue
        if index < len(starts) - 1:
            length = min(window_s + overlap_s, duration - start)
        else:
            length = duration - start
        if length <= 0:
            continue
        windows.append((start, length))
    return windows


def _window_key(t: float) -> float:
    return round(float(t), 3)


def _load_checkpoint(path: str | None) -> dict[float, str]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    found: dict[float, str] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "t" in item:
                found[_window_key(item["t"])] = str(item.get("text") or "")
    return found


def _save_checkpoint(path: str | None, windows: dict[float, str]) -> None:
    if not path:
        return
    payload = [{"t": t, "text": windows[t]} for t in sorted(windows)]
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)


def _probe_duration(path: str) -> float:
    import subprocess

    r = subprocess.run(
        [
            "ffprobe", "-protocol_whitelist", "file,crypto,pipe",
            "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", path,
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True, timeout=60,
    )
    return float(r.stdout.strip())


def _cut_wav(wav_path: str, start: float, length: float) -> str:
    """Cut [start, start+length) of a WAV into a temp file.

    The temp file is removed if ffmpeg fails, so a crashed cut does not leak.
    """
    import subprocess
    import tempfile

    fd, out = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-protocol_whitelist", "file,crypto,pipe",
                "-ss", f"{start:.3f}", "-t", f"{max(length, 0.05):.3f}",
                "-i", wav_path, "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", "-f", "wav", out,
            ],
            capture_output=True, check=True, timeout=120,
        )
    except Exception:
        try:
            os.remove(out)
        except OSError:
            pass
        raise
    return out


def _chunk_wav(wav_path: str) -> list[str]:
    """Split into <=8-minute WAV parts; returns [wav_path] when already short."""
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-protocol_whitelist", "file,crypto,pipe", "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", wav_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60)
    try:
        duration = float(out.stdout.strip())
    except ValueError:
        return [wav_path]
    if duration <= 8 * 60:
        return [wav_path]
    pattern = wav_path.rsplit(".", 1)[0] + ".part%02d.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-protocol_whitelist", "file,crypto,pipe",
         "-loglevel", "error", "-i", wav_path,
         "-f", "segment", "-segment_time", str(8 * 60), "-c", "copy", pattern],
        check=True, timeout=1800)
    import glob

    return sorted(glob.glob(pattern.replace("%02d", "*")))


def _output_text(response: dict) -> str:
    """Pull the assistant text out of a Responses API object."""
    for item in response.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return part.get("text", "")
    return ""



