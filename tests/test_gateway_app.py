"""Unit tests for the NESTR Raspberry Pi gateway Flask API."""

import pytest

import app as gateway


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------
class TestClassifyConditions:
    def test_normal_conditions(self):
        result = gateway.classify_conditions(
            {"temperature_c": 28, "humidity_percent": 65, "weight_kg": 5}
        )
        assert result["status"] == "Normal"
        assert result["alerts"] == []
        assert result["harvest_ready"] is False
        assert result["readiness_percent"] == pytest.approx(62.5)

    def test_temperature_low(self):
        result = gateway.classify_conditions(
            {"temperature_c": 20, "humidity_percent": 65, "weight_kg": 5}
        )
        assert "Temperature Low" in result["alerts"]
        assert result["status"] == "Attention Required"

    def test_temperature_high(self):
        result = gateway.classify_conditions(
            {"temperature_c": 40, "humidity_percent": 65, "weight_kg": 5}
        )
        assert "Temperature High" in result["alerts"]

    def test_humidity_low_and_high(self):
        low = gateway.classify_conditions(
            {"temperature_c": 28, "humidity_percent": 40, "weight_kg": 5}
        )
        high = gateway.classify_conditions(
            {"temperature_c": 28, "humidity_percent": 90, "weight_kg": 5}
        )
        assert "Humidity Low" in low["alerts"]
        assert "Humidity High" in high["alerts"]

    def test_harvest_potential_and_readiness_cap(self):
        result = gateway.classify_conditions(
            {"temperature_c": 28, "humidity_percent": 65, "weight_kg": 12}
        )
        assert result["harvest_ready"] is True
        assert "Harvest Potential" in result["alerts"]
        # Readiness is capped at 100 even though 12/8 = 150%.
        assert result["readiness_percent"] == 100

    def test_missing_values_default_to_zero(self):
        result = gateway.classify_conditions({})
        # temp 0 -> low, humidity 0 -> low.
        assert "Temperature Low" in result["alerts"]
        assert "Humidity Low" in result["alerts"]
        assert result["readiness_percent"] == 0


class TestValidatePayload:
    def test_valid_payload(self):
        payload = {
            "device_id": "hive-1",
            "weight_kg": 5.0,
            "temperature_c": 28,
            "humidity_percent": 65,
        }
        assert gateway.validate_payload(payload) == {"valid": True}

    def test_missing_fields_reported(self):
        result = gateway.validate_payload({"device_id": "hive-1"})
        assert result["valid"] is False
        assert result["error"] == "Missing fields"
        assert set(result["missing"]) == {"weight_kg", "temperature_c", "humidity_percent"}

    def test_non_numeric_values_rejected(self):
        payload = {
            "device_id": "hive-1",
            "weight_kg": "heavy",
            "temperature_c": 28,
            "humidity_percent": 65,
        }
        result = gateway.validate_payload(payload)
        assert result["valid"] is False
        assert result["error"] == "Sensor values must be numeric"

    def test_invalid_device_id_rejected(self):
        payload = {
            "device_id": "bad id/../etc",
            "weight_kg": 5.0,
            "temperature_c": 28,
            "humidity_percent": 65,
        }
        result = gateway.validate_payload(payload)
        assert result["valid"] is False
        assert result["error"] == "Invalid device_id format"


class TestIsValidDeviceId:
    @pytest.mark.parametrize("device_id", ["hive-1", "NESTR_HIVE_001", "abc123", "A" * 64])
    def test_accepts_safe_ids(self, device_id):
        assert gateway.is_valid_device_id(device_id) is True

    @pytest.mark.parametrize(
        "device_id", ["", "has space", "path/traversal", "../etc", "A" * 65, "emoji😀"]
    )
    def test_rejects_unsafe_ids(self, device_id):
        assert gateway.is_valid_device_id(device_id) is False


# ---------------------------------------------------------------------------
# Firebase initialization
# ---------------------------------------------------------------------------
class TestInitFirebase:
    def test_returns_early_when_already_initialized(self, monkeypatch):
        monkeypatch.setattr(gateway.firebase_admin, "_apps", {"default": object()})
        # Should not raise even though config/credentials are absent.
        gateway.init_firebase()

    def test_raises_when_database_url_missing(self, monkeypatch):
        monkeypatch.setattr(gateway.firebase_admin, "_apps", {})
        monkeypatch.setattr(gateway, "FIREBASE_DATABASE_URL", "")
        with pytest.raises(RuntimeError, match="FIREBASE_DATABASE_URL"):
            gateway.init_firebase()

    def test_raises_when_service_account_missing(self, monkeypatch):
        monkeypatch.setattr(gateway.firebase_admin, "_apps", {})
        monkeypatch.setattr(gateway, "FIREBASE_DATABASE_URL", "https://example.firebaseio.com")
        monkeypatch.setattr(gateway, "SERVICE_ACCOUNT_PATH", "/no/such/key.json")
        monkeypatch.setattr(gateway.os.path, "exists", lambda path: False)
        with pytest.raises(RuntimeError, match="service account"):
            gateway.init_firebase()

    def test_initializes_app_when_configured(self, monkeypatch):
        calls = {}
        monkeypatch.setattr(gateway.firebase_admin, "_apps", {})
        monkeypatch.setattr(gateway, "FIREBASE_DATABASE_URL", "https://example.firebaseio.com")
        monkeypatch.setattr(gateway, "SERVICE_ACCOUNT_PATH", "/tmp/key.json")
        monkeypatch.setattr(gateway.os.path, "exists", lambda path: True)
        monkeypatch.setattr(
            gateway.credentials, "Certificate", lambda path: calls.setdefault("cert", path)
        )
        monkeypatch.setattr(
            gateway.firebase_admin,
            "initialize_app",
            lambda cred, options: calls.setdefault("init", options),
        )
        gateway.init_firebase()
        assert calls["cert"] == "/tmp/key.json"
        assert calls["init"] == {"databaseURL": "https://example.firebaseio.com"}


# ---------------------------------------------------------------------------
# Flask routes (Firebase mocked out)
# ---------------------------------------------------------------------------
class FakeRef:
    """Minimal stand-in for a firebase_admin.db reference."""

    def __init__(self, store, path):
        self._store = store
        self._path = path

    def push(self, record):
        self._store.setdefault("pushed", []).append((self._path, record))

        class _Pushed:
            key = "generated-key"

        return _Pushed()

    def set(self, record):
        self._store["set"] = (self._path, record)

    def get(self):
        return self._store.get("get")

    def order_by_key(self):
        return self

    def limit_to_last(self, limit):
        self._store["limit"] = limit
        return self


@pytest.fixture()
def client(monkeypatch):
    store = {}

    monkeypatch.setattr(gateway, "init_firebase", lambda: None)

    class FakeDb:
        def reference(self, path):
            return FakeRef(store, path)

    monkeypatch.setattr(gateway, "db", FakeDb())
    gateway.app.config.update(TESTING=True)
    test_client = gateway.app.test_client()
    test_client.store = store
    return test_client


def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json() == {"service": "NESTR Gateway", "status": "running"}


def test_receive_hive_data_success(client):
    payload = {
        "device_id": "hive-1",
        "weight_kg": 9.0,
        "temperature_c": 30,
        "humidity_percent": 70,
    }
    response = client.post("/api/hive-data", json=payload)
    assert response.status_code == 201
    body = response.get_json()
    assert body["message"] == "Data saved successfully"
    assert body["record_id"] == "generated-key"
    assert body["data"]["device_id"] == "hive-1"
    assert body["data"]["condition"]["harvest_ready"] is True
    assert "timestamp" in body["data"]
    # Both a push (history) and a set (latest) should have occurred.
    assert client.store["pushed"][0][0] == "hives/hive-1/readings"
    assert client.store["set"][0] == "hives/hive-1/latest"


def test_receive_hive_data_invalid(client):
    response = client.post("/api/hive-data", json={"device_id": "hive-1"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing fields"


def test_receive_hive_data_empty_body(client):
    response = client.post("/api/hive-data", data="", content_type="application/json")
    assert response.status_code == 400


def test_get_latest_returns_stored_value(client):
    client.store["get"] = {"weight_kg": 5.0}
    response = client.get("/api/hive-data/hive-1/latest")
    assert response.status_code == 200
    assert response.get_json() == {"weight_kg": 5.0}


def test_get_latest_returns_empty_when_missing(client):
    response = client.get("/api/hive-data/hive-1/latest")
    assert response.status_code == 200
    assert response.get_json() == {}


def test_get_latest_invalid_device_id(client):
    response = client.get("/api/hive-data/bad%20id/latest")
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid device_id format"


def test_get_history_returns_records(client):
    client.store["get"] = {"k1": {"weight_kg": 5.0}, "k2": {"weight_kg": 6.0}}
    response = client.get("/api/hive-data/hive-1/history?limit=2")
    assert response.status_code == 200
    assert response.get_json() == [{"weight_kg": 5.0}, {"weight_kg": 6.0}]
    assert client.store["limit"] == 2


def test_get_history_empty(client):
    response = client.get("/api/hive-data/hive-1/history")
    assert response.status_code == 200
    assert response.get_json() == []


def test_get_history_invalid_device_id(client):
    response = client.get("/api/hive-data/bad%20id/history")
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid device_id format"


def test_get_history_non_integer_limit(client):
    response = client.get("/api/hive-data/hive-1/history?limit=abc")
    assert response.status_code == 400
    assert response.get_json()["error"] == "limit must be an integer"


def test_get_history_limit_clamped_to_max(client):
    client.store["get"] = {}
    client.get(f"/api/hive-data/hive-1/history?limit={gateway.MAX_HISTORY_LIMIT + 100}")
    assert client.store["limit"] == gateway.MAX_HISTORY_LIMIT


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------
def _valid_payload():
    return {
        "device_id": "hive-1",
        "weight_kg": 9.0,
        "temperature_c": 30,
        "humidity_percent": 70,
    }


def test_api_key_not_required_when_unset(client, monkeypatch):
    monkeypatch.setattr(gateway, "API_KEY", "")
    response = client.post("/api/hive-data", json=_valid_payload())
    assert response.status_code == 201


def test_api_key_rejects_missing_or_wrong_key(client, monkeypatch):
    monkeypatch.setattr(gateway, "API_KEY", "secret")
    missing = client.post("/api/hive-data", json=_valid_payload())
    assert missing.status_code == 401
    assert missing.get_json()["error"] == "Unauthorized"
    wrong = client.post(
        "/api/hive-data", json=_valid_payload(), headers={"X-API-Key": "nope"}
    )
    assert wrong.status_code == 401


def test_api_key_accepts_correct_key(client, monkeypatch):
    monkeypatch.setattr(gateway, "API_KEY", "secret")
    response = client.post(
        "/api/hive-data", json=_valid_payload(), headers={"X-API-Key": "secret"}
    )
    assert response.status_code == 201
