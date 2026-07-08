"""
NESTR Raspberry Pi Gateway - Flask API
Receives hive sensor data from ESP32 and stores it in Firebase Realtime Database.

Run:
  pip install -r requirements.txt
  python app.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, db

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nestr_common import classify_conditions, coerce_float

load_dotenv()

app = Flask(__name__)
CORS(app)

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")
SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))


def init_firebase() -> None:
    """Initialize Firebase Admin SDK once."""
    if firebase_admin._apps:
        return

    if not FIREBASE_DATABASE_URL:
        raise RuntimeError("FIREBASE_DATABASE_URL is missing in .env")

    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        raise RuntimeError(f"Firebase service account file not found: {SERVICE_ACCOUNT_PATH}")

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})


def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required = ["device_id", "weight_kg", "temperature_c", "humidity_percent"]
    missing = [key for key in required if key not in payload]
    if missing:
        return {"valid": False, "error": "Missing fields", "missing": missing}

    try:
        float(payload["weight_kg"])
        float(payload["temperature_c"])
        float(payload["humidity_percent"])
    except (TypeError, ValueError):
        return {"valid": False, "error": "Sensor values must be numeric"}

    return {"valid": True}


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"service": "NESTR Gateway", "status": "running"})


@app.route("/api/hive-data", methods=["POST"])
def receive_hive_data():
    init_firebase()
    payload = request.get_json(silent=True) or {}

    validation = validate_payload(payload)
    if not validation["valid"]:
        return jsonify(validation), 400

    now = datetime.now(timezone.utc).isoformat()
    device_id = str(payload["device_id"])

    record = {
        "device_id": device_id,
        "weight_kg": coerce_float(payload["weight_kg"]),
        "temperature_c": coerce_float(payload["temperature_c"]),
        "humidity_percent": coerce_float(payload["humidity_percent"]),
        "timestamp": now,
    }
    record["condition"] = classify_conditions(
        temperature_c=record["temperature_c"],
        humidity_percent=record["humidity_percent"],
        weight_kg=record["weight_kg"],
    )

    readings_ref = db.reference(f"hives/{device_id}/readings")
    new_record = readings_ref.push(record)

    latest_ref = db.reference(f"hives/{device_id}/latest")
    latest_ref.set(record)

    return jsonify({
        "message": "Data saved successfully",
        "record_id": new_record.key,
        "data": record,
    }), 201


@app.route("/api/hive-data/<device_id>/latest", methods=["GET"])
def get_latest(device_id: str):
    init_firebase()
    data = db.reference(f"hives/{device_id}/latest").get()
    return jsonify(data or {})


@app.route("/api/hive-data/<device_id>/history", methods=["GET"])
def get_history(device_id: str):
    init_firebase()
    limit = int(request.args.get("limit", 50))
    raw = db.reference(f"hives/{device_id}/readings").order_by_key().limit_to_last(limit).get()
    if not raw:
        return jsonify([])
    records = list(raw.values())
    return jsonify(records)


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=True)
