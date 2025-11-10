# Multi-stage build for PutPlace FastAPI server
# Optimized for production deployment on AWS

# Build stage
FROM python:3.12-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy only dependency files first (for better caching)
COPY pyproject.toml README.md ./

# Install dependencies
RUN uv pip install --system -e . && \
    uv pip install --system -e ".[s3]"

# Production stage
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code
COPY src ./src
COPY pyproject.toml README.md ./

# Create non-root user for security
RUN useradd -m -u 1000 putplace && \
    chown -R putplace:putplace /app
USER putplace

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/putplace/.local/bin:$PATH"

# Run with production settings (4 workers for 2GB RAM)
# Use --workers 2 for 1GB RAM, --workers 8 for 4GB RAM
CMD ["uvicorn", "putplace.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info"]
