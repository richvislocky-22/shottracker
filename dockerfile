# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (optional but good for many Python packages)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Create directory for SQLite data (will be mounted as a volume)
RUN mkdir -p /data

# Environment variable for DB path
ENV SHOT_TRACKER_DB=/data/shots.db

# Expose Flask port
EXPOSE 8080

# Use gunicorn to serve the app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
