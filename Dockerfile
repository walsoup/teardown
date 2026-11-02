FROM denoland/deno:bin-2.9.1 AS deno
FROM python:3.12-slim

# Supported yt-dlp JS runtime; no request-time runtime/script downloads.
COPY --from=deno /deno /usr/local/bin/deno

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "yt-dlp[default]==2026.10.26" \
    && deno --version \
    && yt-dlp --version \
    && python -c "from importlib.metadata import version; print('yt-dlp-ejs', version('yt-dlp-ejs'))"
COPY teardown ./teardown
COPY web ./web

ENV CHROME_BIN=chromium \
    TEARDOWN_DATA=/app/data \
    HOST=0.0.0.0
EXPOSE 8377
CMD ["python", "web/app.py"]
