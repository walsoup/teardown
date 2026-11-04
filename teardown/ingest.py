"""Stage 1: probe the clip and pull out what the models need.

- audio -> 16 kHz mono WAV for Muse Voice Transcribe
- duration, for sane keyframe timestamps later

Needs ffmpeg on PATH. ffmpeg and ffprobe are limited to local files so a
crafted playlist cannot make them fetch a remote URL.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

# pipe is included so volumedetect can write to /dev/null equivalents;
# http/https/tcp are intentionally absent.
_PROTOCOL = ["-protocol_whitelist", "file,crypto,pipe"]


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=timeout,
    )


def looks_like_container(path: str) -> bool:
    """True for an ISO BMFF header (mp4/mov, `ftyp`) or an EBML header (webm/mkv)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return False
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    return head.startswith(b"\x1a\x45\xdf\xa3")


def probe_duration(video_path: str) -> float:
    out = _run(
        [
            "ffprobe", *_PROTOCOL, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", video_path,
        ],
        timeout=60,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def probe_audio_start(video_path: str) -> float:
    """Audio stream start_time in seconds, or 0 when ffprobe does not report one."""
    try:
        out = _run(
            [
                "ffprobe", *_PROTOCOL, "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=start_time",
                "-of", "json", video_path,
            ],
            timeout=60,
        )
        streams = json.loads(out.stdout).get("streams") or []
        raw = streams[0].get("start_time") if streams else None
        if raw not in (None, "N/A", ""):
            return max(0.0, float(raw))
    except Exception:
        return 0.0
    return 0.0


def has_audio_stream(video_path: str) -> bool:
    probe = _run(
        [
            "ffprobe", *_PROTOCOL, "-v", "error",
            "-select_streams", "a:0", "-show_entries", "stream=index",
            "-of", "csv=p=0", video_path,
        ],
        timeout=60,
    )
    return bool(probe.stdout.strip())


def mean_volume_db(wav_path: str) -> float | None:
    """Mean volume of a wav, or None when volumedetect reports nothing."""
    probe = subprocess.run(
        [
            "ffmpeg", *_PROTOCOL, "-v", "info", "-i", wav_path,
            "-af", "volumedetect", "-f", "null", os.devnull,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", probe.stderr or "")
    if not match:
        return None
    return float(match.group(1))


def has_speech(wav_path: str, floor_db: float = -60.0) -> bool:
    """False when the track is missing or quieter than digital silence."""
    if not wav_path or not os.path.isfile(wav_path):
        return False
    volume = mean_volume_db(wav_path)
    if volume is None:
        return True  # could not measure; let transcription decide
    return volume >= floor_db


def extract_audio(video_path: str, wav_path: str) -> str | None:
    """Extract mono 16 kHz WAV. Returns None if the clip has no audio track."""
    if not has_audio_stream(video_path):
        return None
    parent = os.path.dirname(wav_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _run(
        [
            "ffmpeg", "-y", *_PROTOCOL, "-v", "error",
            "-i", video_path,
            "-map", "0:a:0", "-vn",
            "-c:a", "pcm_s16le", "-ac", "1", "-ar", "16000",
            wav_path,
        ],
        timeout=1800,
    )
    return wav_path


def extract_frame(video_path: str, t: float, png_path: str) -> str:
    """Grab one frame at t seconds."""
    extract_frames(video_path, [t], [png_path])
    if not os.path.isfile(png_path) or os.path.getsize(png_path) == 0:
        raise RuntimeError(f"could not extract a frame at {t:.3f}s")
    return png_path


def extract_frames(video_path: str, times: list[float], png_paths: list[str]) -> list[str]:
    """Grab every timestamp in one ffmpeg process.

    Each output uses `-ss` after the shared `-i`, so the file is opened once.
    If that batch fails, each timestamp is tried on its own.
    """
    if len(times) != len(png_paths):
        raise ValueError("times and png_paths must be the same length")
    if not times:
        return []
    for path in png_paths:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    cmd = ["ffmpeg", "-y", *_PROTOCOL, "-v", "error", "-i", video_path]
    for t, path in zip(times, png_paths):
        cmd += ["-map", "0:v:0", "-ss", f"{max(0.0, t):.3f}", "-frames:v", "1", path]
    try:
        _run(cmd, timeout=max(60, 20 * len(times)))
    except Exception:
        for t, path in zip(times, png_paths):
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                continue
            try:
                _run(
                    [
                        "ffmpeg", "-y", *_PROTOCOL, "-v", "error",
                        "-ss", f"{max(0.0, t):.3f}", "-i", video_path,
                        "-map", "0:v:0", "-frames:v", "1", path,
                    ],
                    timeout=60,
                )
            except Exception:
                continue
    missing = [p for p in png_paths if not (os.path.isfile(p) and os.path.getsize(p) > 0)]
    if len(missing) == len(png_paths):
        raise RuntimeError("could not extract any frames")
    return png_paths
