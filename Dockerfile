FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY config.yaml ./

# Create directories for logs and documents
RUN mkdir -p /app/logs /app/documents

# Create non-root user
RUN useradd -m -s /bin/bash salesdesk && \
    chown -R salesdesk:salesdesk /app

USER salesdesk

# Default command
CMD ["python", "main.py", "monitor"]