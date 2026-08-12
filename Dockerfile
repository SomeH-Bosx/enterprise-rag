FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV VECTOR_DB_PATH=/app/chroma_db
ENV UPLOAD_CACHE_DIR=/app/upload_cache
ENV BM25_STORE_PATH=/app/chroma_db/bm25_store.json
ENV DOC_REGISTRY_PATH=/app/chroma_db/doc_registry.json
# Prefer host Ollama unless overridden by compose.
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV API_BASE_URL=http://127.0.0.1:8000
ENV LOG_LEVEL=INFO

EXPOSE 8000 8501

# Default: API server. Streamlit is started by docker-compose `ui` service.
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
