# Osada Hygge storefront API (examples/hygge). Deployed on Railway; also runnable locally
# with `docker build -t hygge-api . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... hygge-api`.
FROM python:3.12-slim

WORKDIR /app

# Install the seven local packages (editable) and their pinned deps. The editable targets
# are relative paths in requirements.txt, so the sources must be present first.
COPY . .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Railway sets $PORT; default to 8000 for a plain `docker run`.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn hygge.api.main:app --app-dir examples --host 0.0.0.0 --port ${PORT:-8000}"]
