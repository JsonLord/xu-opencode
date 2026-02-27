FROM python:3.11-slim

WORKDIR /app

# Ensure we have required system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager for fast installs
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Add non-root user and setup directories
RUN useradd -m -u 1000 user
RUN mkdir -p /tmp/opencode-api && chown -R user:user /tmp/opencode-api
RUN chown -R user:user /app

COPY --chown=user:user requirements.txt .
# Run as root but install into system site-packages using uv --system
RUN /root/.local/bin/uv pip install --system --no-cache-dir -r requirements.txt
RUN /root/.local/bin/uv pip install --system --no-cache-dir fastapi[all] uvicorn[standard] httpx jinja2

# Switch to user for runtime
USER user
ENV PATH="/home/user/.local/bin:$PATH"

COPY --chown=user:user . .

ENV PYTHONPATH=/app
ENV OPENCODE_STORAGE_PATH=/tmp/opencode-api

EXPOSE 7860

HEALTHCHECK CMD curl --fail http://localhost:7860/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
