FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV PORT=8080

CMD exec gunicorn --bind :$PORT --worker-class eventlet -w 1 app:app
