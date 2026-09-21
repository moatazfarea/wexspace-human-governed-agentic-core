FROM python:3.12-slim
WORKDIR /app
COPY services/pairing_relay/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services ./services
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","services.pairing_relay.app:app","--host","0.0.0.0","--port","8080"]
