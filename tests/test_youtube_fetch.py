"""Offline tests for the Invidious-route helpers in web/youtube.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web"))

from youtube import _extract_video_id, _pick_formats  # noqa: E402

def test_extract_watch_url():
    assert _extract_video_id("https://www.youtube.com/watch?v=jNQXAC9IVRw") == "jNQXAC9IVRw"

def test_extract_watch_url_extra_params():
    u = "https://www.youtube.com/watch?v=jNQXAC9IVRw&t=42s&list=PLxyz"
    assert _extract_video_id(u) == "jNQXAC9IVRw"

def test_extract_short_link():
    assert _extract_video_id("https://youtu.be/jNQXAC9IVRw") == "jNQXAC9IVRw"

def test_extract_shorts_and_embed():
    assert _extract_video_id("https://www.youtube.com/shorts/jNQXAC9IVRw") == "jNQXAC9IVRw"
    assert _extract_video_id("https://www.youtube.com/embed/jNQXAC9IVRw?rel=0") == "jNQXAC9IVRw"

def test_extract_rejects_non_youtube():
    assert _extract_video_id("https://evil.example/watch?v=jNQXAC9IVRw") is None
    assert _extract_video_id("https://www.youtube.com/feed/subscriptions") is None
    assert _extract_video_id("") is None
    assert _extract_video_id(None) is None

def _fmt(ftype, label=None, br="1000", url="https://x"):
    f = {"type": ftype, "bitrate": br, "url": url}
    if label:
        f["qualityLabel"] = label
    return f

def test_pick_prefers_avc1_under_cap():
    adaptive = [
        _fmt('video/mp4; codecs="av01.0.08M.08"', "720p"),
        _fmt('video/mp4; codecs="avc1.64001F"', "360p"),
        _fmt('video/mp4; codecs="avc1.640020"', "1080p"),
        _fmt('audio/mp4; codecs="mp4a.40.2"', br="128000"),
        _fmt('audio/webm; codecs="opus"', br="96000"),
    ]
    v, a = _pick_formats(adaptive)
    assert "avc1" in v["type"] and v["qualityLabel"] == "360p"
    assert "mp4a" in a["type"]

def test_pick_falls_back_when_nothing_under_cap():
    adaptive = [
        _fmt('video/mp4; codecs="avc1.640020"', "1080p"),
        _fmt('video/mp4; codecs="av01.0.08M.08"', "720p"),
        _fmt('audio/mp4; codecs="mp4a.40.2"', br="128000"),
    ]
    v, a = _pick_formats(adaptive)
    assert "avc1" in v["type"] and v["qualityLabel"] == "1080p"

def test_pick_takes_non_avc1_when_only_option():
    adaptive = [
        _fmt('video/webm; codecs="vp9"', "240p"),
        _fmt('audio/webm; codecs="opus"', br="96000"),
    ]
    v, a = _pick_formats(adaptive)
    assert "vp9" in v["type"] and "opus" in a["type"]

def test_pick_empty():
    assert _pick_formats([]) == (None, None)
    assert _pick_formats(None) == (None, None)
