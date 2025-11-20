FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP main.py

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8080", "main:app"]

