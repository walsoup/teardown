"""Downloader configuration and honest 403 diagnosis without network calls."""
import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def downloader(lines, monkeypatch, tmp_path):
    source = (ROOT / "web" / "youtube.py").read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_download')
    captured = []
    proc = SimpleNamespace(stdout=iter(lines), returncode=1, wait=lambda **k: None, kill=lambda: None)
    import os, re, time
    namespace = dict(subprocess=SimpleNamespace(Popen=lambda cmd, **kwargs: captured.append(cmd) or proc, PIPE=-1, STDOUT=-2),
                     os=os, re=re, time=time, JOBS={'test': {}}, set_stage=lambda *a: None)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<download>', 'exec'), namespace)
    assert namespace['_download']('test', 'https://youtu.be/example', str(tmp_path/'none.mp4')) is False
    return namespace['JOBS']['test']['error'], captured[0]


def test_plain_403_does_not_claim_confirmed_ip_ban(monkeypatch, tmp_path):
    error, cmd = downloader(['ERROR: HTTP Error 403: Forbidden'], monkeypatch, tmp_path)
    assert 'cause is not confirmed' in error
    assert "--ignore-config" in cmd
    assert cmd[cmd.index("--use-extractors") + 1] == "youtube*"
    assert cmd[cmd.index('--js-runtimes')+1] == 'deno'
    for option in ['--retries', '--extractor-retries', '--fragment-retries']:
        assert cmd[cmd.index(option)+1] == '0'


def test_missing_runtime_is_setup_error(monkeypatch, tmp_path):
    error, _ = downloader(['WARNING: No supported JavaScript runtime could be found',
                           'ERROR: HTTP Error 403: Forbidden'], monkeypatch, tmp_path)
    assert 'setup is incomplete' in error
