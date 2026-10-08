FROM node:22-bookworm-slim AS client
WORKDIR /build
COPY web_demo/client/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web_demo/client/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends lmms ca-certificates libgl1 libxkbcommon-x11-0 fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY web_demo/requirements.lock.txt /app/web_demo/requirements.lock.txt
RUN pip install --no-cache-dir -r web_demo/requirements.lock.txt
COPY backend/ /app/backend/
COPY assets/samples/ /app/assets/samples/
COPY web_demo/api/ /app/web_demo/api/
COPY --from=client /build/dist/ /app/web_demo/client/dist/
RUN useradd -m -u 10001 emoblocks && mkdir -p /var/lib/emoblocks /tmp/emoblocks-runtime && chown -R emoblocks:emoblocks /var/lib/emoblocks /tmp/emoblocks-runtime && chmod 700 /tmp/emoblocks-runtime
ENV EMOBLOCKS_WEB_DATA=/var/lib/emoblocks EMOBLOCKS_DATA_DIR=/var/lib/emoblocks/runtime EMOBLOCKS_LMMS=/usr/bin/lmms QT_QPA_PLATFORM=offscreen XDG_RUNTIME_DIR=/tmp/emoblocks-runtime PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER emoblocks
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=4)"
CMD ["python","-m","uvicorn","web_demo.api.app:app","--host","0.0.0.0","--port","8765","--workers","1","--proxy-headers","--forwarded-allow-ips","*"]
