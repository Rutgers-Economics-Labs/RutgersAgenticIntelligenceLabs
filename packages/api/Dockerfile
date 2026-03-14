FROM python:3.11-slim

WORKDIR /app

# System deps for owlready2 (SQLite headers) and pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY packages/api/pyproject.toml /app/api/pyproject.toml
RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" httpx "pydantic>=2.7" \
    pydantic-settings pyyaml owlready2 "pandas>=2.2" \
    requests openpyxl aioboto3

# Copy FastAPI app
COPY packages/api/app /app/api/app

# Copy engine (hydration worker runs it as a subprocess)
COPY packages/engine /app/engine

# Create artifact storage dir
RUN mkdir -p /tmp/rail_artifacts

ENV ENGINE_ROOT=/app/engine
ENV RAIL_ANALYSIS_DIR=/app/engine/analysis
ENV RAIL_TRANSFORM_DIR=/app/engine/transforms
ENV PYTHONPATH=/app/api:/app/engine

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
