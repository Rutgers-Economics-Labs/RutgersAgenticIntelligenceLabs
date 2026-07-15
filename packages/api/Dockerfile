FROM python:3.11-slim

WORKDIR /app/api
RUN pip install --no-cache-dir uv

COPY packages/api/pyproject.toml packages/api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY packages/api/app ./app

ENV PATH="/app/api/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main_krail:app", "--host", "0.0.0.0", "--port", "8000"]
