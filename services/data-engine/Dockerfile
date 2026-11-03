FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /packages/shared
RUN pip install --no-cache-dir -e /packages/shared

COPY services/data-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/data-engine/app ./app

# Compile the vendored Upstox proto schema at build time, straight into
# app/, rather than committing generated source. proto/MarketDataFeed.proto
# is the source of truth.
COPY services/data-engine/proto ./proto
RUN pip install --no-cache-dir grpcio-tools==1.64.1 && \
    python -m grpc_tools.protoc -I proto --python_out=app proto/MarketDataFeed.proto

CMD ["python", "-m", "app.main"]
