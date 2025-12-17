FROM python:3.12-slim

# Create a non-root user for security
RUN useradd -m -r appuser

WORKDIR /app

# Install git and tzdata (cron no longer needed)
RUN apt-get update && apt-get install -y git tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directory for backups and set permissions
RUN mkdir -p /backups /var/log /tmp && \
    chown -R appuser:appuser /app /backups /var/log /tmp

# Copy source code and healthcheck script
COPY src/ src/
COPY healthcheck.py run_backup.py ./
RUN chown -R appuser:appuser /app/src /app/healthcheck.py /app/run_backup.py && \
    chmod +x /app/healthcheck.py /app/run_backup.py

# Switch to non-root user
USER appuser

# Set environment variable for backup directory
ENV BACKUP_DIR=/backups

# Healthcheck: Verify backup process is running and responsive
# Checks every 5 minutes, timeout after 10s, 3 retries before marking unhealthy
HEALTHCHECK --interval=5m --timeout=10s --retries=3 \
    CMD python /app/healthcheck.py || exit 1

# Command to run the application directly
CMD ["python", "src/backup.py"]
