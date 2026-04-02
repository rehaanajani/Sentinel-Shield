# ── Base image ────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Metadata
LABEL maintainer="SentinelShield"
LABEL description="Policy-enforced autonomous AI agent backend"

# ── Working directory ──────────────────────────────────────────────────────
WORKDIR /sentinelshield

# ── Install dependencies ───────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy source ────────────────────────────────────────────────────────────
COPY app/ ./app/

# ── Expose port ────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Start server ───────────────────────────────────────────────────────────
# Run from app/ so that relative imports (policy.json, sentinel.log) resolve correctly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
