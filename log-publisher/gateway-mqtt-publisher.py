#!/usr/bin/env python3
"""
Gateway MQTT Publisher
- Reads Basic Station logs via Docker API (docker.sock)
- Parses RX/TX stats
- Fetches TTN gateway connection stats via HTTP API
- Publishes everything to MQTT
"""

import os
import time
from datetime import datetime, timezone
import docker
import paho.mqtt.client as mqtt
import requests

# -----------------------------------------------------------------------------
# Docker client (requires /var/run/docker.sock mounted)
# -----------------------------------------------------------------------------
docker_client = docker.DockerClient(base_url="unix://var/run/docker.sock")

# -----------------------------------------------------------------------------
# Configuration (env overrides defaults)
# -----------------------------------------------------------------------------
# Local MQTT / gateway settings
MQTT_BROKER = os.getenv("MQTT_BROKER", "")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "gateways")
BASICSTATION_CONTAINER = os.getenv("BASICSTATION_CONTAINER", "basicstation")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# TTN settings
TTN_CLUSTER = os.getenv("TTN_CLUSTER", "eu1")          # e.g. eu1, in1
TTN_GATEWAY_ID = os.getenv("TTN_GATEWAY_ID", "")      # your TTN gateway ID
TTN_API_KEY = os.getenv("TTN_API_KEY", "")            # API key with gateway status rights

client = mqtt.Client(client_id="basicstation-mqtt-publisher")

# -----------------------------------------------------------------------------
# MQTT callbacks
# -----------------------------------------------------------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[{datetime.now()}] Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"[{datetime.now()}] Failed to connect, return code {rc}")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[{datetime.now()}] Unexpected disconnection, return code {rc}")


# -----------------------------------------------------------------------------
# Docker log helpers
# -----------------------------------------------------------------------------
def get_docker_logs(container_name: str, tail_lines: int = 100):
    """Get recent logs from the basicstation container via Docker API."""
    try:
        container = docker_client.containers.get(container_name)
        raw = container.logs(tail=tail_lines).decode("utf-8", errors="ignore")
        lines = raw.splitlines()
        if DEBUG:
            print(f"[DEBUG] Got {len(lines)} lines from Docker API logs")
        return lines
    except Exception as e:
        print(f"[{datetime.now()}] Error getting docker logs via API: {e}")
        return []


# -----------------------------------------------------------------------------
# Parsing Basic Station logs
# -----------------------------------------------------------------------------
def parse_log_lines(lines):
    """Parse log lines and extract RX/TX packet counts."""
    rx_count = 0
    tx_count = 0

    for line in lines:
        if not line.strip():
            continue

        # RX: any Basic Station S2E RX line
        if "[S2E:" in line and " RX " in line:
            rx_count += 1
            if DEBUG:
                print(f"[DEBUG] Found RX: {line[:120]}")

        # TX: downlink lines (rare unless you have downlinks)
        if "[S2E:" in line and " TX " in line:
            tx_count += 1
            if DEBUG:
                print(f"[DEBUG] Found TX: {line[:120]}")

    return {"rx": rx_count, "tx": tx_count}


def get_gateway_stats(container_name: str):
    """Get current local gateway stats from Basic Station logs."""
    try:
        lines = get_docker_logs(container_name, tail_lines=100)
        stats = parse_log_lines(lines)

        # Consider connected if any RX lines are present in recent tail
        recent_lines = lines[-50:] if lines else []
        has_rx_recent = any("[S2E:" in line and " RX " in line for line in recent_lines)
        connected = has_rx_recent

        if DEBUG:
            print(
                f"[DEBUG] Local stats: RX={stats['rx']}, "
                f"TX={stats['tx']}, Connected={connected}"
            )

        return {
            "rx_total": stats["rx"],
            "tx_total": stats["tx"],
            "connected": connected,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"[{datetime.now()}] Error parsing local stats: {e}")
        return {
            "rx_total": 0,
            "tx_total": 0,
            "connected": False,
            "timestamp": datetime.now().isoformat(),
        }


# -----------------------------------------------------------------------------
# TTN status (HTTP API)
# -----------------------------------------------------------------------------
def fetch_ttn_stats():
    """Fetch gateway connection stats from TTN / The Things Stack."""
   
    if not (TTN_CLUSTER and TTN_GATEWAY_ID and TTN_API_KEY):
        if DEBUG:
            print("[DEBUG] TTN config incomplete, skipping TTN stats fetch")
        return None

    url = f"https://{TTN_CLUSTER}.cloud.thethings.network/api/v3/gs/gateways/{TTN_GATEWAY_ID}/connection/stats"
    headers = {"Authorization": f"Bearer {TTN_API_KEY}", "Accept": "application/json"}
    print(url)
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        if DEBUG:
            print(f"[DEBUG] TTN stats raw: {data}")
        return data
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching TTN stats: {e}")
        return None

def parse_ttn_stats(data, max_age_seconds=600):
    """Extract fields from TTN stats and derive a 'connected' flag."""
    if not data:
        return {
            "uplink_count": 0,
            "downlink_count": 0,
            "last_uplink_received_at": "",
            "last_downlink_received_at": "",
            "connected": False,
        }

    uplink = int(data.get("uplink_count", 0))
    downlink = int(data.get("downlink_count", 0))
    last_up = data.get("last_uplink_received_at", "")
    last_down = data.get("last_downlink_received_at", "")

    connected = False
    if last_up:
        try:
            # TTN timestamps are RFC3339/ISO8601, e.g. "2025-12-07T10:40:12.345Z"
            t_last = datetime.fromisoformat(last_up.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - t_last).total_seconds()
            # Consider connected if last uplink within max_age_seconds
            connected = age <= max_age_seconds and uplink > 0
        except Exception:
            connected = uplink > 0

    return {
        "uplink_count": uplink,
        "downlink_count": downlink,
        "last_uplink_received_at": last_up,
        "last_downlink_received_at": last_down,
        "connected": connected,
    }

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------
def publish_stats():
    """Connect to MQTT and publish local + TTN stats periodically."""
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    # Initial connect with simple retry
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(
                f"[{datetime.now()}] Attempting to connect to MQTT broker "
                f"(attempt {attempt}/{max_retries})..."
            )
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as e:
            print(f"[{datetime.now()}] Failed to connect to MQTT: {e}")
            if attempt == max_retries:
                print(f"[{datetime.now()}] Max retries reached. Exiting.")
                return
            time.sleep(5)

    client.loop_start()

    print(f"[{datetime.now()}] Starting to publish gateway stats from {BASICSTATION_CONTAINER}...")
    print(f"[{datetime.now()}] Publishing to MQTT topics under: {TOPIC_PREFIX}/...")

    local_interval = 5    # seconds between local log reads
    ttn_interval = 10     # seconds between TTN API calls
    last_local = 0.0
    last_ttn = 0.0

    while True:
        try:
            now = time.time()

            if now - last_ttn >= ttn_interval:
                ttn_raw = fetch_ttn_stats()
                ttn = parse_ttn_stats(ttn_raw)

                client.publish(f"{TOPIC_PREFIX}/ttn/uplink_count", ttn["uplink_count"], retain=True)
                client.publish(f"{TOPIC_PREFIX}/ttn/downlink_count", ttn["downlink_count"], retain=True)
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/last_uplink_received_at",
                    ttn["last_uplink_received_at"],
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/last_downlink_received_at",
                    ttn["last_downlink_received_at"],
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/connected",
                    "1" if ttn["connected"] else "0",
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/last_update",
                    datetime.now().isoformat(),
                    retain=True,
                )

                print(
                    f"[{datetime.now()}] TTN: up={ttn['uplink_count']}, "
                    f"down={ttn['downlink_count']}, connected={ttn['connected']}"
                )

                last_ttn = now

            if now - last_ttn >= ttn_interval:
                ttn_raw = fetch_ttn_stats()
                ttn = parse_ttn_stats(ttn_raw)

                client.publish(
                    f"{TOPIC_PREFIX}/ttn/uplink_count",
                    ttn["uplink_count"],
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/downlink_count",
                    ttn["downlink_count"],
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/last_uplink_received_at",
                    ttn["last_uplink_received_at"],
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/last_downlink_received_at",
                    ttn["last_downlink_received_at"],
                    retain=True,
                )
                client.publish(
                    f"{TOPIC_PREFIX}/ttn/last_update",
                    datetime.now().isoformat(),
                    retain=True,
                )

                print(
                    f"[{datetime.now()}] TTN: up={ttn['uplink_count']}, "
                    f"down={ttn['downlink_count']}"
                )

                last_ttn = now

            time.sleep(1)

        except KeyboardInterrupt:
            print(f"\n[{datetime.now()}] Shutting down...")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Error in publish loop: {e}")
            time.sleep(5)

    client.loop_stop()
    client.disconnect()


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"[{datetime.now()}] Gateway MQTT Publisher starting...")
    print(f"[{datetime.now()}] MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"[{datetime.now()}] MQTT User: {MQTT_USER if MQTT_USER else '(none)'}")
    print(f"[{datetime.now()}] Basic Station Container: {BASICSTATION_CONTAINER}")
    print(f"[{datetime.now()}] TTN: cluster={TTN_CLUSTER}, gateway={TTN_GATEWAY_ID}")
    print(f"[{datetime.now()}] Topic Prefix: {TOPIC_PREFIX}")
    print(f"[{datetime.now()}] Debug Mode: {DEBUG}")
    print()

    publish_stats()
