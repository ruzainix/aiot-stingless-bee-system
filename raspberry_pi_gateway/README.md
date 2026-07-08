# NESTR Raspberry Pi Gateway

The Raspberry Pi gateway receives ESP32 sensor data through a Flask API and sends it to Firebase Realtime Database.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Firebase Setup

1. Create Firebase project.
2. Enable Realtime Database.
3. Generate service account key from Project Settings > Service Accounts.
4. Rename it to `serviceAccountKey.json` and place it in this folder.
5. Update `.env` with your Firebase database URL.

## Security Configuration

Configure these in `.env` (see `.env.example`):

- `FLASK_DEBUG` — keep `false`. The Werkzeug debugger allows remote code execution if exposed.
- `FLASK_HOST` — defaults to `127.0.0.1`. Only set `0.0.0.0` if the ESP32 must reach the gateway over the LAN, and firewall the port.
- `API_KEY` — when set, `POST /api/hive-data` requires a matching `X-API-Key` header. Set the same value in the ESP32 sketch (`GATEWAY_API_KEY`).
- `CORS_ALLOWED_ORIGINS` — comma-separated allow-list of browser origins permitted to call the API.

Never commit `.env` or `serviceAccountKey.json` (both are covered by `.gitignore`).

## API Endpoint

POST `/api/hive-data` (requires `X-API-Key` header when `API_KEY` is configured)

Example JSON:

```json
{
  "device_id": "NESTR-HIVE-001",
  "weight_kg": 7.25,
  "temperature_c": 29.4,
  "humidity_percent": 72.1
}
```
