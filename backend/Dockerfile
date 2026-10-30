# MENDORA API (FastAPI) — production image.
# Build:  docker build -t mendora-backend ./backend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # SQLite database lives on a volume so data survives container restarts
    MENDORA_DATABASE_URL=sqlite:////data/mendora.db \
    MENDORA_UPLOAD_DIR=/data/uploads \
    MENDORA_ENVIRONMENT=production

WORKDIR /app

# Dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Run as an unprivileged user; /data is owned by it so the volume is writable
RUN useradd --create-home --uid 10001 mendora \
    && mkdir -p /data \
    && chown mendora:mendora /data
USER mendora
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# No --reload in production. --proxy-headers: trust X-Forwarded-For from the nginx container
# (the backend port is not published to the outside, only nginx can reach it).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
