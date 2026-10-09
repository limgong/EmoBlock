FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS client
WORKDIR /build
COPY web_demo/client/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web_demo/client/ ./
RUN npm run build

FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89 AS native
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::ForceIPv4=true update && apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY native/json_codec/pyproject.toml native/json_codec/setup.py native/json_codec/emoblocks_json_native.pyx /build/json_codec/
RUN pip wheel --no-deps --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 --retries 3 /build/json_codec -w /wheels && pip download --only-binary=:all: --no-deps --index-url https://pypi.tuna.tsinghua.edu.cn/simple orjson==3.13.0 -d /wheels

FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::ForceIPv4=true update && apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends lmms ca-certificates libgl1 libxkbcommon-x11-0 fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY web_demo/requirements.lock.txt /app/web_demo/requirements.lock.txt
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 --retries 3 -r web_demo/requirements.lock.txt
COPY --from=native /wheels/ /tmp/native-wheels/
RUN pip install --no-cache-dir --no-index /tmp/native-wheels/*.whl && rm -rf /tmp/native-wheels
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
