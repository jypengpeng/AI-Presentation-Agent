# Backend Dockerfile
FROM python:3.11-slim

# Build arguments for mirror configuration
ARG USE_CHINA_MIRROR=false

# Set working directory
WORKDIR /app

# Configure China mirrors if needed
RUN if [ "$USE_CHINA_MIRROR" = "true" ]; then \
        sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
        sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
    fi

# Install system dependencies, Google Chrome stable, Chinese fonts and emoji
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    fonts-wqy-zenhei \
    fonts-noto-color-emoji \
    && mkdir -p /etc/apt/keyrings \
    && wget -q -O /etc/apt/keyrings/google-chrome.asc https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

# Create data directory
RUN mkdir -p /app/data/tasks

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]