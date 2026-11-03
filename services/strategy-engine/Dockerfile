FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /packages/shared
RUN pip install --no-cache-dir -e /packages/shared

COPY services/strategy-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/strategy-engine/app ./app

CMD ["python", "-m", "app.main"]
