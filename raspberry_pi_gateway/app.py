"""
NESTR Raspberry Pi Gateway - Flask API
Receives hive sensor data from ESP32 and stores it in Firebase Realtime Database.

Run:
  pip install -r requirements.txt
  python app.py
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import firebase_admin
from firebase_admin import credentials, db

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nestr.gateway")

app = Flask(__name__)
CORS(app)

FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL", "")
SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")


class GatewayError(Exception):
    """Raised when the gateway cannot fulfil a request.

    Carries an HTTP status code so the error surfaces to the client as a
    structured JSON response instead of an opaque 500 with a stack trace.
    """

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def init_firebase() -> None:
    """Initialize Firebase Admin SDK once.

    Raises GatewayError (503) when the service is misconfigured or the SDK
    cannot connect, so callers propagate a clear error to the client instead
    of a bare traceback.
    """
    if firebase_admin._apps:
        return

    if not FIREBASE_DATABASE_URL:
        raise GatewayError("FIREBASE_DATABASE_URL is missing in .env", status_code=503)

    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        raise GatewayError(
            f"Firebase service account file not found: {SERVICE_ACCOUNT_PATH}",
            status_code=503,
        )

    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})
    except Exception as exc:
        logger.exception("Failed to initialize Firebase")
        raise GatewayError(f"Failed to initialize Firebase: {exc}", status_code=503) from exc


def classify_conditions(data: Dict[str, Any]) -> Dict[str, Any]:
    """Prototype condition detection rules for stingless beehive monitoring."""
    temp = float(data.get("temperature_c", 0))
    humidity = float(data.get("humidity_percent", 0))
    weight = float(data.get("weight_kg", 0))

    alerts = []
    status = "Normal"

    if temp < 24:
        alerts.append("Temperature Low")
    elif temp > 34:
        alerts.append("Temperature High")

    if humidity < 50:
        alerts.append("Humidity Low")
    elif humidity > 85:
        alerts.append("Humidity High")

    if weight >= 8:
        alerts.append("Harvest Potential")

    if alerts:
        status = "Attention Required"

    return {
        "status": status,
        "alerts": alerts,
        "harvest_ready": weight >= 8,
        "readiness_percent": min(round((weight / 8) * 100, 2), 100),
    }


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


@app.errorhandler(GatewayError)
def handle_gateway_error(error: GatewayError):
    return jsonify({"error": error.message}), error.status_code


@app.errorhandler(HTTPException)
def handle_http_error(error: HTTPException):
    return jsonify({"error": error.description}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    logger.exception("Unhandled error while processing request")
    return jsonify({"error": "Internal server error"}), 500


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
        "weight_kg": float(payload["weight_kg"]),
        "temperature_c": float(payload["temperature_c"]),
        "humidity_percent": float(payload["humidity_percent"]),
        "timestamp": now,
    }
    record["condition"] = classify_conditions(record)

    try:
        readings_ref = db.reference(f"hives/{device_id}/readings")
        new_record = readings_ref.push(record)

        latest_ref = db.reference(f"hives/{device_id}/latest")
        latest_ref.set(record)
    except Exception as exc:
        logger.exception("Failed to write hive data for device %s", device_id)
        raise GatewayError(f"Failed to store hive data: {exc}", status_code=502) from exc

    return jsonify({
        "message": "Data saved successfully",
        "record_id": new_record.key,
        "data": record,
    }), 201


@app.route("/api/hive-data/<device_id>/latest", methods=["GET"])
def get_latest(device_id: str):
    init_firebase()
    try:
        data = db.reference(f"hives/{device_id}/latest").get()
    except Exception as exc:
        logger.exception("Failed to read latest data for device %s", device_id)
        raise GatewayError(f"Failed to read hive data: {exc}", status_code=502) from exc
    return jsonify(data or {})


@app.route("/api/hive-data/<device_id>/history", methods=["GET"])
def get_history(device_id: str):
    init_firebase()

    raw_limit = request.args.get("limit", "50")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        raise GatewayError("Query parameter 'limit' must be an integer", status_code=400)
    if limit <= 0:
        raise GatewayError("Query parameter 'limit' must be a positive integer", status_code=400)

    try:
        raw = db.reference(f"hives/{device_id}/readings").order_by_key().limit_to_last(limit).get()
    except Exception as exc:
        logger.exception("Failed to read history for device %s", device_id)
        raise GatewayError(f"Failed to read hive history: {exc}", status_code=502) from exc

    if not raw:
        return jsonify([])
    records = list(raw.values())
    return jsonify(records)


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
