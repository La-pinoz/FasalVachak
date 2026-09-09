FROM python:3.12-slim

# 1. Prevent Python from buffering logs & generating .pyc files in container
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 2. Install basic system dependencies required for SSL and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 3. Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 4. Copy application source code (relies on .dockerignore to skip venv, .env, etc.)
COPY . .

# 5. Run the LiveKit worker process
CMD ["python", "server.py", "start"]
