FROM python:3.13-slim

# ping and ip are needed for the ICMP, router and VPN interface checks.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends iputils-ping iproute2 \
    && apt-get clean

RUN useradd --system --create-home --shell /usr/sbin/nologin tashevnet \
    && mkdir -p /data \
    && chown tashevnet:tashevnet /data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config.example.yaml /app/config.yaml

# Inside the container the dashboard must listen on all interfaces; docker-compose.yml
# publishes it on the host's 127.0.0.1 only.
ENV TASHEVNET_CONFIG=/app/config.yaml \
    TASHEVNET_HOST=0.0.0.0 \
    TASHEVNET_DB_PATH=/data/tashevnet.db \
    PYTHONUNBUFFERED=1

USER tashevnet
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('TASHEVNET_PORT', '8765') + '/healthz', timeout=4)"]

CMD ["tashevnet", "run"]
