# Multi-stage build for AudioScribe
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libasound2-dev \
    libportaudio2-dev \
    libportaudiocpp0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
COPY requirements.txt ./
RUN pip install --no-cache-dir -e .[typing]

# Runtime stage
FROM python:3.11-slim

# Install runtime dependencies for audio
RUN apt-get update && apt-get install -y \
    libasound2 \
    libportaudio2 \
    libportaudiocpp0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY config.yaml ./
COPY .env.example ./
COPY README.md ./
COPY AGENTS.md ./

# Create non-root user for security
ARG USERNAME=transcriber
ARG USER_UID=1000
ARG GID=1000

RUN groupadd -g $GID $USERNAME || true
RUN useradd -m -s /bin/bash -u $USER_UID -g $GID $USERNAME || true

# Set proper permissions
RUN chown -R $USERNAME:$GID /app
USER $USERNAME

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Expose audio socket path for Linux
ENV PULSE_SERVER=unix:${XDG_RUNTIME_DIR}/pulse/native

# Labels for metadata
LABEL maintainer="Rodolfo <rodolfonobregar@gmail.com>"
LABEL description="Multi-provider audio transcription service"
LABEL version="0.2.0"
LABEL org.opencontainers.image.source="https://github.com/rodolfonobrega/audioscribe"

# Default command
ENTRYPOINT ["python", "-m", "audioscribe.cli"]

# Default arguments
CMD ["start"]