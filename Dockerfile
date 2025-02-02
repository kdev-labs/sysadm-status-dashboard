FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py
ENV FLASK_ENV=production

CMD ["sh", "-c", "flask run --host=0.0.0.0 --port=${FLASK_PORT}"]
