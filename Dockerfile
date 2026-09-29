FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY refundry ./refundry
COPY scripts ./scripts
COPY data/seed ./data/seed

ENV REFUNDRY_HOST=0.0.0.0
EXPOSE 8080 8000-8006 8201-8207

CMD ["python", "scripts/run_all.py"]
