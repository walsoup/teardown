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

import requests

BASE_URL = "https://api.meta.ai/v1"


class MetaApi:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY")
        if not self.api_key:
            raise SystemExit(
                "MODEL_API_KEY is not set. Create a key in the Model API "
                "dashboard (https://dev.meta.ai) under API keys, then:\n"
                "  export MODEL_API_KEY=..."
            )
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def upload_file(self, path: str, purpose: str = "user_data") -> str:
        """Upload a file once, get back a file_id to reference in requests."""
        with open(path, "rb") as fh:
            r = self.session.post(
                f"{BASE_URL}/files",
                files={"file": (os.path.basename(path), fh)},
                data={"purpose": purpose},
            )
        r.raise_for_status()
        return r.json()["id"]

    def respond(self, model: str, content: list[dict], **extra) -> str:
        """One non-streaming Responses call. Returns the output_text."""
        r = self.session.post(
            f"{BASE_URL}/responses",
            json={
                "model": model,
                "input": [{"type": "message", "role": "user", "content": content}],
                **extra,
            },
        )
        r.raise_for_status()
        return _output_text(r.json())

    def respond_stream(self, model: str, content: list[dict], **extra):
        """Streaming Responses call. Yields the raw event dicts.

        Used for SAM 3.1: events feed the meta_sam_parser stream parser.
        """
        r = self.session.post(
            f"{BASE_URL}/responses",
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

    def _transcribe_chunk(self, wav_path: str) -> str:
        with open(wav_path, "rb") as audio:
            r = self.session.post(
                f"{BASE_URL}/asr/transcribe",
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


def _chunk_wav(wav_path: str) -> list[str]:
    """Split into <=8-minute WAV parts; returns [wav_path] when already short."""
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", wav_path],
        capture_output=True, text=True)
    try:
        duration = float(out.stdout.strip())
    except ValueError:
        return [wav_path]
    if duration <= 8 * 60:
        return [wav_path]
    pattern = wav_path.rsplit(".", 1)[0] + ".part%02d.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
         "-f", "segment", "-segment_time", str(8 * 60), "-c", "copy", pattern],
        check=True)
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
