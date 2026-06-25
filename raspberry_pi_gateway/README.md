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

## API Endpoint

POST `/api/hive-data`

Example JSON:

```json
{
  "device_id": "NESTR-HIVE-001",
  "weight_kg": 7.25,
  "temperature_c": 29.4,
  "humidity_percent": 72.1
}
```
