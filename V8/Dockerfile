# The online app, for a Hugging Face Docker Space (free CPU Basic).
# Keys and the password come from the Space's secrets, never from this image.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face runs the container as user 1000
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . .
RUN mkdir -p jobs && chown -R app:app /app

USER app
ENV PUBLIC=1 ALLOW_FETCH=0 VIDEOS_DIR=/app/clips PYTHONUNBUFFERED=1
EXPOSE 7860
# One process, because the job list lives in memory; threads serve the page while a job runs.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "900", "--bind", "0.0.0.0:7860", "app:app"]
