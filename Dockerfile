FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY config.example.yaml ./config.yaml
ENV TASHEVNET_CONFIG=/app/config.yaml
EXPOSE 8765

CMD ["tashevnet", "run"]
