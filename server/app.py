"""Single-device image relay. HTTP owns jobs; MQTT only carries control/events."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

FRAME_SIZE = 192000
ACTIVE = ("created", "dispatched", "downloading", "refreshing")
TERMINAL = ("succeeded", "failed", "uncertain")


class Settings:
    def __init__(self):
        self.data = Path(os.environ.get("ELINK_DATA", "server/data"))
        self.app_token = os.environ.get("ELINK_APP_TOKEN", "")
        self.device_token = os.environ.get("ELINK_DEVICE_TOKEN", "")
        self.device_id = os.environ.get("ELINK_DEVICE_ID", "frame-001")
        self.public_url = os.environ.get("ELINK_PUBLIC_URL", "https://127.0.0.1")
        self.mqtt_host = os.environ.get("ELINK_MQTT_HOST", "127.0.0.1")
        self.mqtt_port = int(os.environ.get("ELINK_MQTT_PORT", "1883"))
        self.mqtt_user = os.environ.get("ELINK_MQTT_USER", "elink-api")
        self.mqtt_password = os.environ.get("ELINK_MQTT_PASSWORD", "")
        self.mqtt_enabled = os.environ.get("ELINK_MQTT_ENABLED", "1") == "1"


class Relay:
    def __init__(self, settings: Settings):
        self.s = settings
        settings.data.mkdir(parents=True, exist_ok=True)
        (settings.data / "images").mkdir(exist_ok=True)
        self.db_path = settings.data / "relay.sqlite3"
        self.stop = threading.Event()
        self.client = None
        self.connected = False
        self.topic = f"elink/v1/{settings.device_id}"
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY, sha256 TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, image_id TEXT, idem TEXT UNIQUE,
                    state TEXT, error TEXT, created REAL, updated REAL, expires REAL);
                CREATE TABLE IF NOT EXISTS device(
                    id INTEGER PRIMARY KEY CHECK(id=1), seen REAL DEFAULT 0,
                    online INTEGER DEFAULT 0, busy INTEGER DEFAULT 0,
                    boot_id TEXT DEFAULT '', job_id TEXT DEFAULT '', state TEXT DEFAULT 'offline');
                INSERT OR IGNORE INTO device(id) VALUES(1);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def start(self):
        if not self.s.app_token or not self.s.device_token:
            raise RuntimeError("ELINK_APP_TOKEN and ELINK_DEVICE_TOKEN must be configured")
        if self.s.mqtt_enabled:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="elink-api")
            self.client.username_pw_set(self.s.mqtt_user, self.s.mqtt_password)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = lambda *_: setattr(self, "connected", False)
            self.client.on_message = self.on_message
            self.client.reconnect_delay_set(1, 30)
            self.client.connect_async(self.s.mqtt_host, self.s.mqtt_port, 30)
            self.client.loop_start()
        self.worker = threading.Thread(target=self.maintenance, daemon=True)
        self.worker.start()

    def close(self):
        self.stop.set()
        self.worker.join(timeout=3)
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        if self.connected:
            client.subscribe([(self.topic + "/events", 1), (self.topic + "/presence", 1)])

    def on_message(self, client, userdata, message):
        try:
            body = json.loads(message.payload)
            if len(message.payload) > 4096:
                return
            if message.topic.endswith("/presence"):
                if body.get("online") is False:
                    with self.db() as db:
                        db.execute("UPDATE device SET online=0 WHERE id=1")
                elif not message.retain:
                    self.event(body)
            else:
                self.event(body)
        except (ValueError, TypeError, sqlite3.Error):
            # Invalid device messages must not kill Paho's network thread.
            import logging
            logging.getLogger(__name__).exception("Invalid device event")

    def event(self, body):
        if not isinstance(body, dict):
            return
        now = time.time()
        job_id, state = body.get("job_id", ""), body.get("state", "idle")
        if not isinstance(job_id, str) or not isinstance(state, str):
            return
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE device SET seen=?,online=1,busy=?,boot_id=?,job_id=?,state=? WHERE id=1",
                       (now, int(state in ("downloading", "refreshing", "receiving")),
                        str(body.get("boot_id", ""))[:64], job_id[:64], state[:32]))
            job = db.execute("SELECT jobs.*,images.sha256 FROM jobs JOIN images ON images.id=jobs.image_id WHERE jobs.id=?", (job_id,)).fetchone()
            if not job or job["state"] in ("succeeded", "failed"):
                return
            if state not in ("downloading", "refreshing", "succeeded", "failed", "uncertain"):
                return
            if state == "succeeded" and body.get("sha256") != job["sha256"]:
                state, error = "failed", "reported_hash_mismatch"
            else:
                error = str(body.get("error", ""))[:200]
            rank = {"created": 0, "dispatched": 1, "downloading": 2, "refreshing": 3}
            if state in rank and (job["state"] == "uncertain" or rank[state] < rank.get(job["state"], 0)):
                return
            db.execute("UPDATE jobs SET state=?,error=?,updated=? WHERE id=?", (state, error, now, job_id))

    def tick(self):
        now = time.time()
        with self.db() as db:
            db.execute("UPDATE device SET online=0 WHERE seen<?", (now - 45,))
            db.execute("UPDATE jobs SET state='uncertain',error='device_result_timeout',updated=? WHERE state IN ('created','dispatched','downloading','refreshing') AND created<?", (now, now - 240))
            pending = db.execute("SELECT jobs.*,images.sha256 FROM jobs JOIN images ON images.id=jobs.image_id WHERE state IN ('created','dispatched') AND expires>?", (now,)).fetchall()
            stale = db.execute("SELECT id FROM images WHERE created<? AND id NOT IN (SELECT image_id FROM jobs WHERE state IN ('created','dispatched','downloading','refreshing'))", (now - 7 * 86400,)).fetchall()
            for row in stale:
                (self.s.data / "images" / row["id"]).unlink(missing_ok=True)
                db.execute("DELETE FROM images WHERE id=?", (row["id"],))
        if not self.connected or not self.client:
            return
        for row in pending:
            payload = {"v": 1, "job_id": row["id"], "image_id": row["image_id"],
                       "sha256": row["sha256"], "size": FRAME_SIZE, "expires_at": int(row["expires"]),
                       "issued_at_us": int(row["created"] * 1000000)}
            info = self.client.publish(self.topic + "/command", json.dumps(payload), qos=1, retain=False)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                with self.db() as db:
                    db.execute("UPDATE jobs SET state='dispatched',updated=? WHERE id=? AND state='created'", (now, row["id"]))

    def maintenance(self):
        while not self.stop.wait(3):
            try:
                self.tick()
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Relay maintenance failed")


class NewJob(BaseModel):
    image_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    idempotency_key: str = Field(min_length=8, max_length=100)


def create_app(settings=None):
    relay = Relay(settings or Settings())

    @asynccontextmanager
    async def lifespan(app):
        relay.start()
        yield
        relay.close()

    app = FastAPI(title="Elink MVP", lifespan=lifespan)
    app.state.relay = relay

    def authenticate(token):
        def check(authorization: str = Header(default="")):
            if not token or not hmac.compare_digest(authorization, "Bearer " + token):
                raise HTTPException(401, "unauthorized")
        return check

    app_auth = authenticate(relay.s.app_token)
    device_auth = authenticate(relay.s.device_token)

    @app.get("/health")
    def health():
        return {"ok": True, "mqtt_connected": relay.connected}

    @app.get("/v1/device", dependencies=[Depends(app_auth)])
    def device():
        with relay.db() as db:
            row = dict(db.execute("SELECT * FROM device WHERE id=1").fetchone())
            job = db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 1").fetchone()
        return {"id": relay.s.device_id, "width": 800, "height": 480,
                "online": bool(row["online"] and row["seen"] > time.time() - 45),
                "busy": bool(row["busy"]), "state": row["state"],
                "last_seen": row["seen"], "latest_job": dict(job) if job else None}

    @app.post("/v1/images", dependencies=[Depends(app_auth)], status_code=201)
    async def upload(request: Request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > FRAME_SIZE:
                raise HTTPException(422, "invalid_image_size")
        if len(data) != FRAME_SIZE:
            raise HTTPException(422, "invalid_image_size")
        valid = {0, 1, 2, 3, 5, 6}
        if any((v >> 4) not in valid or (v & 15) not in valid for v in data):
            raise HTTPException(422, "invalid_palette_code")
        image_id = secrets.token_hex(16)
        digest = hashlib.sha256(data).hexdigest()
        path = relay.s.data / "images" / image_id
        path.write_bytes(data)
        with relay.db() as db:
            db.execute("INSERT INTO images VALUES(?,?,?)", (image_id, digest, time.time()))
        return {"image_id": image_id, "sha256": digest, "size": FRAME_SIZE}

    @app.post("/v1/refresh-jobs", dependencies=[Depends(app_auth)], status_code=201)
    def create_job(body: NewJob):
        now = time.time()
        with relay.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM jobs WHERE idem=?", (body.idempotency_key,)).fetchone()
            if prior:
                if prior["image_id"] != body.image_id:
                    raise HTTPException(409, "idempotency_conflict")
                return dict(prior)
            if not db.execute("SELECT 1 FROM images WHERE id=?", (body.image_id,)).fetchone():
                raise HTTPException(404, "image_not_found")
            device = db.execute("SELECT * FROM device WHERE id=1").fetchone()
            if not device["online"] or device["seen"] < now - 45:
                raise HTTPException(409, "device_offline")
            if device["busy"] or db.execute("SELECT 1 FROM jobs WHERE state IN ('created','dispatched','downloading','refreshing')").fetchone():
                raise HTTPException(409, "device_busy")
            if relay.s.mqtt_enabled and not relay.connected:
                raise HTTPException(503, "broker_unavailable")
            job_id = secrets.token_hex(16)
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (job_id, body.image_id, body.idempotency_key, "created", "", now, now, now + 60))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    @app.get("/v1/refresh-jobs/{job_id}", dependencies=[Depends(app_auth)])
    def job(job_id: str):
        with relay.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "job_not_found")
        return dict(row)

    @app.get("/v1/device/images/{image_id}", dependencies=[Depends(device_auth)])
    def download(image_id: str):
        with relay.db() as db:
            image = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
        if not image:
            raise HTTPException(404, "image_not_found")
        return FileResponse(relay.s.data / "images" / image_id, media_type="application/octet-stream",
                            headers={"X-Image-SHA256": image["sha256"], "Cache-Control": "no-store"})

    return app


app = create_app()
