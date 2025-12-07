FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir paho-mqtt docker requests
COPY gateway-mqtt-publisher.py /app/
CMD ["python3", "/app/gateway-mqtt-publisher.py"]
