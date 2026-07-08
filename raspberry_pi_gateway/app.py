"""
NESTR Raspberry Pi Gateway - Flask API
Receives hive sensor data from ESP32 and stores it in Firebase Realtime Database.

Run:
  pip install -r requirements.txt
  python app.py
"""

import logging
import math
import os
import re
import sys
import threading
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import firebase_admin
from firebase_admin import credentials, db

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nestr_common import classify_conditions as classify_hive_conditions, coerce_float

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nestr.gateway")

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


class GatewayError(Exception):
    """Raised when the gateway cannot fulfil a request.

    Carries an HTTP status code so the error surfaces to the client as a
    structured JSON response instead of an opaque 500 with a stack trace.
    """

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


_firebase_lock = threading.Lock()


def init_firebase() -> None:
    """Initialize Firebase Admin SDK once.

    Thread-safe: a lock guards the check-then-init so concurrent requests under
    threaded Flask don't both call initialize_app. Raises GatewayError (503)
    when the service is misconfigured or the SDK cannot connect, with a generic
    client-facing message (details are logged server-side, never returned).
    """
    if firebase_admin._apps:
        return

    with _firebase_lock:
        if firebase_admin._apps:
            return

        if not FIREBASE_DATABASE_URL:
            logger.error("FIREBASE_DATABASE_URL is missing in .env")
            raise GatewayError("Gateway is not configured correctly", status_code=503)

        if not os.path.exists(SERVICE_ACCOUNT_PATH):
            logger.error("Firebase service account file not found: %s", SERVICE_ACCOUNT_PATH)
            raise GatewayError("Gateway is not configured correctly", status_code=503)

        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})
        except ValueError:
            # Another initializer won the race; the app already exists.
            if firebase_admin._apps:
                return
            logger.exception("Failed to initialize Firebase")
            raise GatewayError("Failed to initialize Firebase gateway", status_code=503)
        except Exception as exc:
            logger.exception("Failed to initialize Firebase")
            raise GatewayError("Failed to initialize Firebase gateway", status_code=503) from exc


def classify_conditions(data: Dict[str, Any]) -> Dict[str, Any]:
    """Prototype condition detection rules for stingless beehive monitoring."""
    return classify_hive_conditions(
        temperature_c=data.get("temperature_c", 0),
        humidity_percent=data.get("humidity_percent", 0),
        weight_kg=data.get("weight_kg", 0),
    )


def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required = ["device_id", "weight_kg", "temperature_c", "humidity_percent"]
    missing = [key for key in required if key not in payload]
    if missing:
        return {"valid": False, "error": "Missing fields", "missing": missing}

    if not is_valid_device_id(str(payload["device_id"])):
        return {"valid": False, "error": "Invalid device_id format"}

    numeric_fields = ["weight_kg", "temperature_c", "humidity_percent"]
    try:
        values = {field: float(payload[field]) for field in numeric_fields}
    except (TypeError, ValueError):
        return {"valid": False, "error": "Sensor values must be numeric"}

    non_finite = [field for field, value in values.items() if not math.isfinite(value)]
    if non_finite:
        return {
            "valid": False,
            "error": "Sensor values must be finite numbers",
            "invalid": non_finite,
        }

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
    record["condition"] = classify_conditions(record)

    try:
        readings_ref = db.reference(f"hives/{device_id}/readings")
        new_record = readings_ref.push(record)
    except Exception as exc:
        logger.exception("Failed to write hive data for device %s", device_id)
        raise GatewayError("Failed to store hive data", status_code=502) from exc

    # 'latest' is a derived snapshot of the reading just stored above. If this
    # write fails the reading is still durably saved and the snapshot refreshes
    # on the next reading, so we log it rather than failing the request (which
    # would prompt a retry and duplicate the history entry).
    try:
        db.reference(f"hives/{device_id}/latest").set(record)
    except Exception:
        logger.exception("Failed to update latest snapshot for device %s", device_id)

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
    try:
        data = db.reference(f"hives/{device_id}/latest").get()
    except Exception as exc:
        logger.exception("Failed to read latest data for device %s", device_id)
        raise GatewayError("Failed to read hive data", status_code=502) from exc
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
    try:
        raw = db.reference(f"hives/{device_id}/readings").order_by_key().limit_to_last(limit).get()
    except Exception as exc:
        logger.exception("Failed to read history for device %s", device_id)
        raise GatewayError("Failed to read hive history", status_code=502) from exc
    if not raw:
        return jsonify([])
    records = list(raw.values())
    return jsonify(records)


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
