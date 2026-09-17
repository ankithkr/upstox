FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY webui/ webui/
COPY ui.py precompute_ui.py ./

EXPOSE 5001

CMD ["python", "ui.py"]
