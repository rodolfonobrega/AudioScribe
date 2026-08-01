# AudioScribe Python engine image.
# The Electron desktop app is packaged separately; this image is for the
# headless/IPC engine and requires host audio passthrough on Linux.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libasound2 \
    libasound2-dev \
    libportaudio2 \
    portaudio19-dev \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-docker.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-docker.txt

COPY main.py __init__.py ./
COPY config ./config
COPY core ./core

RUN useradd --create-home --uid 10001 audioscribe \
    && mkdir -p /home/audioscribe/.audioscribe \
    && chown -R audioscribe:audioscribe /app /home/audioscribe
USER audioscribe
ENV HOME=/home/audioscribe \
    AUDIOSCRIBE_DATA_DIR=/home/audioscribe/.audioscribe

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket,json; s=socket.create_connection(('127.0.0.1',8765),2); s.sendall(b'{\\\"id\\\":\\\"health\\\",\\\"command\\\":\\\"ping\\\"}\\n'); data=s.recv(4096); s.close(); r=json.loads(data); raise SystemExit(0 if r.get('status') == 'ok' else 1)"

ENTRYPOINT ["python", "main.py"]
CMD ["--server", "--no-keyboard", "--output", "stdout"]
