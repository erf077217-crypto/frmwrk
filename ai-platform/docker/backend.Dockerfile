# ─── Builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ─── Runtime ───────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY backend/          backend/
COPY agents/           agents/
COPY providers/        providers/
COPY tools/            tools/
COPY configs/          configs/
COPY tests/            tests/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request, json; d=json.loads(urllib.request.urlopen('http://localhost:8000/health').read()); exit(0 if d.get('status') in ('ok','degraded') else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
