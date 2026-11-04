"""Narration floor and bounded upload retries (overnight test batch, 2026-11-04)."""
import requests
import pytest

from teardown import orchestrate
from teardown.meta_api import MetaApi


def test_narration_words_counts_all_windows():
    tt = [{"t": 0.0, "text": "remove the four screws"}, {"t": 30.0, "text": ""},
          {"t": 60.0, "text": "lift the cover off"}]
    assert orchestrate.narration_words(tt) == 8


def test_narration_floor_rejects_single_spurious_word():
    # An ambient/music clip whose ASR hallucinates one word ("Nice.") must not
    # reach paid planning: one word cannot ground any guide step.
    tt = [{"t": 30.0 * i, "text": ""} for i in range(18)]
    tt[6] = {"t": 180.0, "text": "Nice."}
    assert orchestrate.narration_words(tt) < orchestrate.MIN_NARRATION_WORDS


def test_narration_floor_passes_real_narration():
    tt = [{"t": 0.0, "text": "today we take apart this console and clean it"},
          {"t": 30.0, "text": "start with the screws on the bottom cover"}]
    assert orchestrate.narration_words(tt) >= orchestrate.MIN_NARRATION_WORDS


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.text = body

    def json(self):
        return {"id": "file-test"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, *a, **k):
        self.calls += 1
        return self.responses.pop(0)


def _api(session):
    api = MetaApi.__new__(MetaApi)
    api.session = session
    return api


def test_upload_retries_burst_400_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr("time.sleep", lambda s: None)
    f = tmp_path / "v.mp4"
    f.write_bytes(b"ftyp")
    api = _api(_Session([_Resp(400, "rate limit"), _Resp(200, "")]))
    assert api.upload_file(str(f)) == "file-test"
    assert api.session.calls == 2


def test_upload_does_not_retry_deterministic_400(monkeypatch, tmp_path):
    monkeypatch.setattr("time.sleep", lambda s: None)
    f = tmp_path / "v.webm"
    f.write_bytes(b"ebml")
    api = _api(_Session([_Resp(400, "Unsupported file type: `video/webm`")]))
    with pytest.raises(requests.HTTPError):
        api.upload_file(str(f))
    assert api.session.calls == 1


def test_upload_gives_up_after_bounded_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr("time.sleep", lambda s: None)
    f = tmp_path / "v.mp4"
    f.write_bytes(b"ftyp")
    api = _api(_Session([_Resp(400, "rate limit")] * 4))
    with pytest.raises(requests.HTTPError):
        api.upload_file(str(f))
    assert api.session.calls == 4
