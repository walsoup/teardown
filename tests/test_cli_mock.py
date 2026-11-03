"""CLI exit codes and an offline --mock guide. Needs ffmpeg."""

import os
import shutil
import subprocess

import pytest

from teardown.cli import main
from teardown.ingest import has_speech, looks_like_container


def _ffmpeg(*args):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)


def _clip(path):
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    )
    return path


def test_missing_file_and_cost_flag(tmp_path):
    assert main([str(tmp_path / "missing.mp4"), "--mock"]) == 1
    video = _clip(tmp_path / "clip.mp4")
    assert looks_like_container(str(video))
    assert main([str(video), "--out", str(tmp_path / "real")]) == 2


def test_duration_cap_refuses_without_calling_out(tmp_path, monkeypatch):
    video = _clip(tmp_path / "clip.mp4")
    monkeypatch.setenv("TEARDOWN_MAX_DURATION", "0.2")
    code = main([str(video), "--i-accept-api-cost", "--out", str(tmp_path / "long")])
    assert code == 2
    assert not (tmp_path / "long" / "plan.json").exists()


def test_mock_writes_a_guide(tmp_path):
    video = _clip(tmp_path / "clip.mp4")
    out = tmp_path / "guide"
    assert main([str(video), "--mock", "--out", str(out), "--attribution", "local test"]) == 0
    page = (out / "guide.html").read_text(encoding="utf-8")
    assert "test device (mock)" in page
    assert "Standard precaution, not from this video" in page
    assert "local test" in page
    assert (out / "plan.json").is_file()


def test_silence_floor(tmp_path):
    silent = tmp_path / "silent.wav"
    _ffmpeg(
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
        "-t", "1", "-c:a", "pcm_s16le", str(silent),
    )
    assert has_speech(str(silent)) is False
    assert has_speech(str(tmp_path / "missing.wav")) is False
    assert os.path.isfile(silent)
