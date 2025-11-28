FROM python:3.9-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

#install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]