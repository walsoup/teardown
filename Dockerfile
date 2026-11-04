FROM denoland/deno:bin-2.9.1 AS deno
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

# Supported yt-dlp JS runtime; no request-time runtime/script downloads.
COPY --from=deno /deno /usr/local/bin/deno

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && deno --version \
    && yt-dlp --version \
    && python -c "from importlib.metadata import version; print('yt-dlp-ejs', version('yt-dlp-ejs'))"
COPY teardown ./teardown
COPY web ./web

RUN useradd --create-home --uid 10001 teardown \
    && mkdir -p /app/data \
    && chown -R teardown:teardown /app
USER teardown

ENV CHROME_BIN=chromium \
    TEARDOWN_DATA=/app/data \
    HOST=0.0.0.0
EXPOSE 8377
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8377/', timeout=4)"
CMD ["python", "web/app.py"]
