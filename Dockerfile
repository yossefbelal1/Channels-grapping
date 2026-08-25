FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (e.g. gcc, libpq-dev for potential native builds)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create a non-root system user and ensure sessions directory is created and owned by appuser.
# This ensures that SQLite session files can be written securely even as non-root.
RUN useradd -m appuser && mkdir -p /app/sessions && chown -R appuser:appuser /app
USER appuser

# Default command (overridden in compose)
CMD ["python"]
