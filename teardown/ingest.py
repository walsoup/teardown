"""Stage 1: probe the clip and pull out what the models need.

- audio -> 16 kHz mono WAV for Muse Voice Transcribe
- duration, for sane keyframe timestamps later

Needs ffmpeg on PATH.
"""

from __future__ import annotations

import json
import subprocess


def probe_duration(video_path: str) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", video_path,
        ],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def extract_audio(video_path: str, wav_path: str) -> str | None:
    """Extract mono 16 kHz WAV. Returns None if the clip has no audio track."""
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a", "-show_entries", "stream=index",
            "-of", "csv=p=0", video_path,
        ],
        capture_output=True, text=True, check=True, timeout=60,
    )
    if not probe.stdout.strip():
        return None
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000",
            wav_path,
        ],
        check=True, timeout=1800,
    )
    return wav_path


def extract_frame(video_path: str, t: float, png_path: str) -> str:
    """Grab one frame at t seconds (accurate seek)."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{t:.3f}",
            "-i", video_path,
            "-frames:v", "1",
            png_path,
        ],
        check=True, timeout=60,
    )
    return png_path

