FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    jq \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies for the shim and proxy
RUN pip install --no-cache-dir fastapi uvicorn httpx mcp-proxy cryptography

# Setup credentials folder symlink to PVC mount (/data)
RUN mkdir -p /root/.config && ln -s /data /root/.config/trainingpeaks-mcp

# Copy application code and install it
COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir .

# Expose port
EXPOSE 8000

# Start the shim on container startup
CMD ["uvicorn", "tp_mcp.shim:app", "--host", "0.0.0.0", "--port", "8000"]
