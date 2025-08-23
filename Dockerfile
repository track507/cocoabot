# Build stage
FROM python:3.13.3-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -r requirements.txt

# Final runtime image
FROM python:3.13.3-slim

ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# Copy installed environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy app code
COPY . .

# Expose the port (Railway will set the PORT env var)
EXPOSE $PORT

# Run the bot
CMD ["python", "main.py"]