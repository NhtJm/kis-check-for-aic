FROM python:3.11-slim

# ffmpeg cho yt-dlp; libgl/libglib cho opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py index.html kis-viewer.html media-index.json ./

# Host nho: chi cho cham qua API, video tai theo yeu cau roi tu xoa bot
ENV HOST=0.0.0.0 \
    PORT=8777 \
    KIS_BACKENDS=api \
    KIS_FETCH=1 \
    KIS_VIDEO_DIR=/tmp/videos \
    KIS_VIDEO_CACHE_MB=800

EXPOSE 8777
CMD ["python3", "serve.py"]
