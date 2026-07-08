"""
NESTR Raspberry Pi Gateway - Flask API
Receives hive sensor data from ESP32 and stores it in Firebase Realtime Database.

Run:
  pip install -r requirements.txt
  python app.py
"""

import os
import re
import sys
from datetime import datetime, timezone
from functools import wraps
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

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")
SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes", "on")

# API key required to write hive data. Auth is enforced only when this is set,
# so existing read-only setups keep working while ingestion can be locked down.
API_KEY = os.getenv("API_KEY", "")

# Restrict CORS to an explicit allow-list of dashboard origins.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5000").split(",")
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": CORS_ALLOWED_ORIGINS}})

# Reject oversized request bodies (defensive DoS limit).
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_BYTES", str(64 * 1024)))

# Device identifiers are used as Firebase Realtime Database path segments, so
# restrict them to a safe character set to prevent path traversal/injection.
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_HISTORY_LIMIT = 500


def is_valid_device_id(device_id: str) -> bool:
    return bool(DEVICE_ID_PATTERN.fullmatch(device_id))


def require_api_key(view):
    """Enforce API key auth on a view when API_KEY is configured."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if API_KEY:
            provided = request.headers.get("X-API-Key", "")
            if provided != API_KEY:
                return jsonify({"error": "Unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapper


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

    if not is_valid_device_id(str(payload["device_id"])):
        return {"valid": False, "error": "Invalid device_id format"}

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
@require_api_key
def receive_hive_data():
    payload = request.get_json(silent=True) or {}

    validation = validate_payload(payload)
    if not validation["valid"]:
        return jsonify(validation), 400

    init_firebase()
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
    if not is_valid_device_id(device_id):
        return jsonify({"error": "Invalid device_id format"}), 400
    init_firebase()
    data = db.reference(f"hives/{device_id}/latest").get()
    return jsonify(data or {})


@app.route("/api/hive-data/<device_id>/history", methods=["GET"])
def get_history(device_id: str):
    if not is_valid_device_id(device_id):
        return jsonify({"error": "Invalid device_id format"}), 400
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    init_firebase()
    raw = db.reference(f"hives/{device_id}/readings").order_by_key().limit_to_last(limit).get()
    if not raw:
        return jsonify([])
    records = list(raw.values())
    return jsonify(records)


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
