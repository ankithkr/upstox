FROM python:3.12-slim

WORKDIR /app

COPY packages/shared /packages/shared
RUN pip install --no-cache-dir -e /packages/shared

COPY services/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api-gateway/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
