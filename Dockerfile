# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for Pillow (and handy curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libjpeg62-turbo-dev zlib1g-dev curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src ./src

# Create runtime dirs (persisted via volumes in compose)
RUN mkdir -p data images

# Default port used by the FastMCP server
ENV PORT=8000
EXPOSE 8000

# Start the MCP server
CMD ["python", "src/server.py"]

