# LoRaWAN Basic Station for RAK831

A containerised LoRaWAN gateway setup for the RAK831 (SX1301) concentrator, using Semtech LoRa Basics™ Station and The Things Stack (TTN/TTS). This project wraps the upstream Basics Station Docker image and adds a sidecar service that publishes gateway statistics to MQTT and optionally queries TTN for gateway status.  

## Based On

- Upstream project: https://github.com/xoseperez/basicstation-docker  

## Features

- Runs Semtech LoRa Basics Station in Docker for SX1301-based RAK831 concentrators.  
- Connects to The Things Stack / The Things Network using LNS (and optionally CUPS) with a gateway API key.  
- Sidecar **gateway-mqtt-publisher** that:
  - Tails Basic Station logs via the Docker API and counts RX/TX frames.  
  - Derives a local “connected” flag based on recent RX activity.  
  - Queries TTN gateway connection stats over HTTP and exposes:
    - Uplink/downlink counters.  
    - Last uplink/downlink timestamps.  
    - A TTN-side “connected” flag (online/offline heuristic).  
  - Publishes all metrics to MQTT topics for consumption by ESP32, OpenHAB, Home Assistant, etc.  

## Repository Layout

- `docker-compose.yml`  
  Main stack definition: Basic Station, Mosquitto, and the MQTT publisher sidecar.  

- `log-publisher/`  
  - `Dockerfile` – builds the `gateway-mqtt-publisher` image (Python + paho-mqtt + docker SDK + requests).  
  - `gateway-mqtt-publisher.py` – combined script for local log parsing and TTN status polling.  

- `.env`  
  Runtime configuration for both Basic Station and the publisher.  

- `example.env`  
  Sample environment file to copy and adapt.  

## Prerequisites

- Linux host with Docker and Docker Compose installed.  
- RAK831 (SX1301) LoRa concentrator wired to the host SPI (`/dev/spidev0.0`) and reset GPIO (for example, GPIO17).  
- A The Things Stack / TTN account with:
  - A registered gateway (correct EUI).  
  - A gateway API key for Basics Station (`TC_KEY`).  
  - An additional API key for querying gateway status if TTN HTTP polling is enabled.  

## Configuration

### `.env`

Example `.env`:

```json
Basics Station / hardware
MODEL=SX1301
INTERFACE=SPI
RESET_GPIO=17
DEVICE=/dev/spidev0.0
HAS_GPS=1

Local MQTT / publisher
MQTT_BROKER=192.168.0.7
MQTT_PORT=1883
MQTT_USER=
MQTT_PASS=
MQTT_TOPIC_PREFIX=gateways
BASICSTATION_CONTAINER=basicstation
DEBUG=false

TTN / The Things Stack
TTN_CLUSTER=eu1
TTN_GATEWAY_ID=
TTN_API_KEY=YOUR_TTN_GATEWAY_STATUS_KEY
```

Adjust values to match your hardware (SPI device, GPIO) and TTN gateway configuration.


## Running

From the project root
```shell
docker compose build gateway-mqtt-publisher
docker compose up -d
```

Then subscribe to the MQTT topics:

```shell
mosquitto_sub -h 192.168.0.7 -t 'gateways/#' -v
```

You should see:

- `gateways/stats/rx_total`, `tx_total`, `connected`, `last_update`  
- `gateways/ttn/uplink_count`, `downlink_count`, `last_uplink_received_at`, `last_downlink_received_at`, `connected`, `last_update`  

These topics can be consumed by an ESP32, dashboards, or home-automation platforms to visualize and react to gateway status. 