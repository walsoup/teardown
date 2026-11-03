"""Stream an upload to disk and carve a multipart video part."""
import re

def _stream(rfile, ln, path):
    """Copy exactly ln bytes from the request body to disk in 1 MB chunks."""
    remaining = ln
    with open(path, "wb") as fh:
        while remaining > 0:
            chunk = rfile.read(min(1 << 20, remaining))
            if not chunk:
                return False
            fh.write(chunk)
            remaining -= len(chunk)
    return True


def _boundary_token(ctype):
    """Boundary from a multipart Content-Type, or None."""
    match = re.search(r'boundary\s*=\s*("[^"]+"|[^;]+)', ctype or "", re.I)
    if not match:
        return None
    raw = match.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        raw = raw[1:-1]
    raw = raw.strip()
    if not raw or len(raw) > 200:
        return None
    try:
        return raw.encode("ascii")
    except UnicodeEncodeError:
        return None


def _text_field(blob, name):
    pattern = re.compile(
        rb'name="' + re.escape(name.encode()) + rb'"[^\r\n]*\r\n(?:[^\r\n]+\r\n)*\r\n([^\r\n]*)',
        re.I,
    )
    match = pattern.search(blob or b"")
    if not match:
        return ""
    return match.group(1).decode("utf-8", "replace").strip()


def _file_part(blob):
    """(filename, body_offset) for the video part, or (None, None)."""
    pattern = re.compile(
        rb'name="video"[^\r\n]*filename="([^"]*)"[^\r\n]*\r\n(?:[^\r\n]+\r\n)*\r\n',
        re.I,
    )
    match = pattern.search(blob or b"")
    if not match or not match.group(1):
        return None, None
    return match.group(1).decode("utf-8", "replace"), match.end()


def _clean_credit(value):
    text = re.sub(r"[\r\n\x00]", " ", value or "").strip()
    return text[:200]


def _carve(tmp, start, out_path, boundary):
    """Copy the file part up to the real multipart boundary."""
    marker = b"\r\n--" + boundary
    with open(tmp, "rb") as fh:
        fh.seek(start)
        prev = b""
        with open(out_path, "wb") as out:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    out.write(prev)
                    break
                buf = prev + chunk
                idx = buf.find(marker)
                if idx != -1:
                    out.write(buf[:idx])
                    break
                keep = len(marker) - 1
                if keep <= 0:
                    out.write(buf)
                    prev = b""
                    continue
                out.write(buf[:-keep])
                prev = buf[-keep:]
