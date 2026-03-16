FROM python:3.11-slim

LABEL maintainer="APEX Trading Bot"
LABEL description="Agentic AI Trading Bot — Multi-Asset, Multi-Broker"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt \
    --ignore-requires-python \
    --extra-index-url https://pypi.org/simple/ \
    || true

# Copy source
COPY . .

# Create logs dir
RUN mkdir -p /app/logs

# Non-root user
RUN useradd -m -u 1000 apex && chown -R apex:apex /app
USER apex

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s \
  CMD curl -f http://localhost:8000/api/status || exit 1

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
