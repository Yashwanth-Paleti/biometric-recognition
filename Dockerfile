# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered streaming
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies required for OpenCV and ONNX Runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application and migration code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/

# Expose FastAPI REST API port
EXPOSE 8000

# Healthcheck for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Start Uvicorn ASGI server
CMD ["uvicorn", "app.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
