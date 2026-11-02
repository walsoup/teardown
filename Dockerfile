FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt yt-dlp
COPY budget.py ./web/
COPY teardown ./teardown
COPY web ./web

ENV CHROME_BIN=chromium \
    TEARDOWN_DATA=/app/data \
    HOST=0.0.0.0
EXPOSE 8377
CMD ["python", "web/app.py"]
