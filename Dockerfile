FROM python:3.11-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY FlaskBackend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask application
COPY FlaskBackend/Formatting ./Formatting

EXPOSE 8080

CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:8080", "Formatting.app:app"]
