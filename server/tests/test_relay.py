import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from server.app import Settings, create_app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ELINK_DATA", str(tmp_path))
    monkeypatch.setenv("ELINK_APP_TOKEN", "test-app")
    monkeypatch.setenv("ELINK_DEVICE_TOKEN", "test-device")
    monkeypatch.setenv("ELINK_MQTT_ENABLED", "0")
    app = create_app(Settings())
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer test-app"
        yield client, app.state.relay


def image(client, data=b"\x01" * 192000):
    r = client.post("/v1/images", content=data)
    assert r.status_code == 201, r.text
    return r.json()["image_id"]


def test_auth_and_invalid_images(setup):
    c, _ = setup
    assert c.get("/v1/device", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/v1/images", content=b"small").status_code == 422
    assert c.post("/v1/images", content=b"\x44" * 192000).status_code == 422
    assert c.post("/v1/images", content=b"\x11" * 192001).status_code == 422


def test_job_lifecycle_idempotency_and_integrity(setup):
    c, relay = setup
    i = image(c)
    body = {"image_id": i, "idempotency_key": "retry-key-1"}
    assert c.post("/v1/refresh-jobs", json=body).json()["detail"] == "device_offline"
    relay.event({"state": "idle"})
    j = c.post("/v1/refresh-jobs", json=body).json()
    assert c.post("/v1/refresh-jobs", json=body).json()["id"] == j["id"]
    assert c.post("/v1/refresh-jobs", json={**body, "idempotency_key": "another-key"}).status_code == 409
    relay.event({"job_id": j["id"], "state": "refreshing"})
    relay.event({"job_id": j["id"], "state": "downloading"})
    assert c.get("/v1/refresh-jobs/" + j["id"]).json()["state"] == "refreshing"
    relay.event({"job_id": j["id"], "state": "succeeded", "sha256": hashlib.sha256(b"\x01" * 192000).hexdigest()})
    assert c.get("/v1/refresh-jobs/" + j["id"]).json()["state"] == "succeeded"
    assert c.get("/v1/device/images/" + i).status_code == 401
    data = c.get("/v1/device/images/" + i, headers={"Authorization": "Bearer test-device"})
    assert data.content == b"\x01" * 192000


def test_timeout_and_bad_success(setup):
    c, relay = setup
    relay.event({"state": "idle"})
    j = c.post("/v1/refresh-jobs", json={"image_id": image(c), "idempotency_key": "hash-check"}).json()
    relay.event({"job_id": j["id"], "state": "succeeded", "sha256": "wrong"})
    assert c.get("/v1/refresh-jobs/" + j["id"]).json()["error"] == "reported_hash_mismatch"
    j = c.post("/v1/refresh-jobs", json={"image_id": image(c), "idempotency_key": "timeout-key"}).json()
    with relay.db() as db:
        db.execute("UPDATE jobs SET created=? WHERE id=?", (time.time() - 250, j["id"]))
    relay.tick()
    assert c.get("/v1/refresh-jobs/" + j["id"]).json()["state"] == "uncertain"
