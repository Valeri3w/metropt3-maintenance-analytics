FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py pyproject.toml ./
COPY src ./src
COPY scripts ./scripts
COPY sql ./sql
COPY artifacts/audit ./artifacts/audit
COPY ["data/raw/metropt3/MetroPT3(AirCompressor).csv", "./data/raw/metropt3/"]
COPY ["data/raw/metropt3/Data Description_Metro.pdf", "./data/raw/metropt3/"]

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
