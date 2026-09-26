FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Semantic (embedding) search needs sentence-transformers + torch (~2 GB). It is optional: without
# it the API degrades gracefully to structured filters + recency ranking.
#   docker compose build --build-arg EMBEDDINGS=true
ARG EMBEDDINGS=false
COPY requirements.txt .
RUN if [ "$EMBEDDINGS" = "true" ]; then pip install -r requirements.txt; \
    else grep -v -i sentence-transformers requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt; fi

COPY app ./app
COPY seed ./seed
COPY demo ./demo
COPY scripts ./scripts

RUN useradd -m appuser && mkdir -p /app/logs && chown -R appuser /app
USER appuser
EXPOSE 8000 8501
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
