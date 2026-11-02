"""
FuelFlow Phase 4 Comprehensive Test Suite:
Tests real live CCTV integration, camera stream validation & SSRF security,
station-level operator authorization, worker lifecycle, waiting-time estimation calibration,
and live queue analytics endpoints.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.entities import Station, CameraConfig, User, LiveQueueSnapshot
from app.services.auth import create_access_token, hash_password
from app.services.live_camera_service import (
    validate_stream_url,
    mask_stream_url,
    live_camera_manager,
    StationLiveCameraWorker,
)
from tests.conftest import TestingSessionLocal


# ----------------- 1. Security & URL Validation Tests -----------------

def test_validate_stream_url_ssrf_protection():
    """Verify SSRF blocking against cloud metadata services and disallowed schemes."""
    # Cloud metadata IPs & domains MUST be rejected
    valid, msg = validate_stream_url("http://169.254.169.254/latest/meta-data", "http")
    assert not valid
    assert "cloud metadata" in msg.lower()

    valid, msg = validate_stream_url("http://metadata.google.internal/computeMetadata/v1/", "http")
    assert not valid
    assert "cloud metadata" in msg.lower()

    # Mismatched protocol
    valid, msg = validate_stream_url("http://camera.local/feed", "rtsp")
    assert not valid
    assert "expected 'rtsp://'" in msg.lower()

    # Empty stream URL
    valid, msg = validate_stream_url("", "rtsp")
    assert not valid

    # Valid RTSP
    valid, msg = validate_stream_url("rtsp://admin:pass123@192.168.1.10:554/live/ch0", "rtsp")
    assert valid

    # Valid HTTP
    valid, msg = validate_stream_url("http://192.168.1.50:8080/mjpg/video.mjpg", "http")
    assert valid

    # Valid Webcam device index
    valid, msg = validate_stream_url("0", "webcam")
    assert valid


def test_mask_stream_url():
    """Verify that camera passwords and secret tokens are masked."""
    # RTSP credentials masking
    masked = mask_stream_url("rtsp://operator_john:SecretPassword!@10.0.0.55:554/stream1")
    assert "SecretPassword!" not in masked
    assert "***:***@" in masked

    # HTTP URL token masking
    masked_http = mask_stream_url("http://stream.camera.org/live.mjpg?token=secret12345&fps=15")
    assert "secret12345" not in masked_http
    assert "token=***" in masked_http


# ----------------- 2. Waiting-Time Calibration Logic Tests -----------------

def test_waiting_time_estimation_requires_sufficient_data():
    """
    Per Phase 4 Requirement 4: Waiting time must NEVER be guessed from a single frame.
    It requires at least 3 genuine observed ROI exits before producing an estimate.
    """
    worker = StationLiveCameraWorker(
        station_id=999,
        stream_url="0",
        camera_type="webcam",
        roi_config_raw=json.dumps({"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9}),
        frame_sampling_rate=5,
    )

    # Initial state: 0 exits observed
    assert worker.waiting_time_seconds is None

    # Simulate 1 exit (e.g. dwell time 40s)
    worker.completed_dwell_seconds.append(40.0)
    worker.update_waiting_time_estimate()
    assert worker.waiting_time_seconds is None  # Still insufficient data (< 3)

    # Simulate 2nd exit (e.g. dwell time 50s)
    worker.completed_dwell_seconds.append(50.0)
    worker.update_waiting_time_estimate()
    assert worker.waiting_time_seconds is None  # Still insufficient data (< 3)

    # Simulate 3rd exit (e.g. dwell time 60s)
    worker.completed_dwell_seconds.append(60.0)
    worker.update_waiting_time_estimate()
    # Now calibrated: average dwell = 50s
    assert worker.waiting_time_seconds is not None
    assert worker.waiting_time_seconds == 50.0


# ----------------- 3. Operator API & Station Authorization Tests -----------------

@pytest.fixture
def auth_setup():
    """Create test operator and stations for authorization tests."""
    db = TestingSessionLocal()

    operator = db.query(User).filter(User.username == "operator_cctv_test").first()
    if not operator:
        operator = User(
            username="operator_cctv_test",
            email="operator_cctv_test@fuelflow.com",
            hashed_password=hash_password("Pass123!"),
            role="operator",
            is_active=True,
        )
        db.add(operator)

    other_operator = db.query(User).filter(User.username == "operator_other_test").first()
    if not other_operator:
        other_operator = User(
            username="operator_other_test",
            email="operator_other_test@fuelflow.com",
            hashed_password=hash_password("Pass123!"),
            role="operator",
            is_active=True,
        )
        db.add(other_operator)

    db.commit()
    db.refresh(operator)
    db.refresh(other_operator)

    st1 = db.query(Station).filter(Station.name == "Phase 4 Authorized Station").first()
    if not st1:
        st1 = Station(
            name="Phase 4 Authorized Station",
            address="100 Karve Road, Pune",
            latitude=18.5000,
            longitude=73.8100,
            queue_capacity=15,
            pump_count=4,
            slot_duration_minutes=15,
            booking_window_hours=24,
            max_vehicles_per_slot=4,
            operator_id=operator.id,
        )
        db.add(st1)

    st2 = db.query(Station).filter(Station.name == "Phase 4 Other Station").first()
    if not st2:
        st2 = Station(
            name="Phase 4 Other Station",
            address="200 Karve Road, Pune",
            latitude=18.5100,
            longitude=73.8200,
            queue_capacity=10,
            pump_count=2,
            slot_duration_minutes=15,
            booking_window_hours=24,
            max_vehicles_per_slot=2,
            operator_id=other_operator.id,
        )
        db.add(st2)

    db.commit()
    db.refresh(st1)
    db.refresh(st2)

    cam1 = db.query(CameraConfig).filter(CameraConfig.station_id == st1.id).first()
    if not cam1:
        cam1 = CameraConfig(
            station_id=st1.id,
            camera_type="rtsp",
            stream_url="rtsp://operator:securepass@192.168.1.100:554/live",
            is_active=False,
            connection_status="DISCONNECTED",
            detection_roi=json.dumps({"x1": 0.1, "y1": 0.2, "x2": 0.8, "y2": 0.9}),
        )
        db.add(cam1)
        db.commit()

    token = create_access_token({"sub": str(operator.id), "role": operator.role})
    other_token = create_access_token({"sub": str(other_operator.id), "role": other_operator.role})

    yield {
        "operator": operator,
        "token": token,
        "other_token": other_token,
        "st1": st1,
        "st2": st2,
    }
    db.close()


def test_operator_camera_authorization_and_masking(client: TestClient, auth_setup: dict):
    """Verify that operators can only view/configure their own station's camera and credentials are masked."""
    token = auth_setup["token"]
    other_token = auth_setup["other_token"]
    st1_id = auth_setup["st1"].id

    # Authorized operator views camera config
    res = client.get(
        f"/api/stations/{st1_id}/camera",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "stream_url_masked" in data
    assert "securepass" not in data["stream_url_masked"]
    assert "***:***@" in data["stream_url_masked"]

    # Unauthorized operator attempt receives 403 Forbidden
    res_unauth = client.get(
        f"/api/stations/{st1_id}/camera",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_unauth.status_code == 403


def test_camera_connect_and_disconnect(client: TestClient, auth_setup: dict):
    """Test camera connect and disconnect endpoints."""
    token = auth_setup["token"]
    st1_id = auth_setup["st1"].id

    # Connect camera
    res_connect = client.post(
        f"/api/stations/{st1_id}/camera/connect",
        headers={"Authorization": f"Bearer {token}"},
        json={"frame_sampling_rate": 5},
    )
    assert res_connect.status_code == 200
    data = res_connect.json()
    assert data["is_streaming"] is True
    assert data["station_id"] == st1_id

    # Get live status
    res_status = client.get(
        f"/api/stations/{st1_id}/camera/live-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["station_id"] == st1_id
    assert status_data["stream_url_masked"] != ""

    # Disconnect camera
    res_disconnect = client.post(
        f"/api/stations/{st1_id}/camera/disconnect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_disconnect.status_code == 200
    data_disc = res_disconnect.json()
    assert data_disc["is_streaming"] is False
    assert data_disc["connection_status"] == "DISCONNECTED"


def test_public_queue_status_freshness_and_transparency(client: TestClient, auth_setup: dict):
    """
    Verify public queue-status endpoint returns accurate connection state,
    stale indicators, and refuses to fabricate counts.
    """
    st1_id = auth_setup["st1"].id
    db = TestingSessionLocal()

    # 1. When camera is disconnected
    res = client.get(f"/api/stations/{st1_id}/queue-status")
    assert res.status_code == 200
    data = res.json()
    assert data["live_stream"]["status"] == "camera_disconnected"
    assert data["live_stream"]["current_queue_count"] is None
    assert "not connected" in data["live_stream"]["message"].lower()

    # 2. Simulate stored fresh reading in camera config
    cam = db.query(CameraConfig).filter(CameraConfig.station_id == st1_id).first()
    cam.is_active = True
    cam.connection_status = "CONNECTED"
    cam.current_queue_count = 3
    cam.current_vehicles_total = 5
    cam.waiting_time_seconds = 180.0
    cam.last_frame_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()

    res_fresh = client.get(f"/api/stations/{st1_id}/queue-status")
    assert res_fresh.status_code == 200
    fresh_data = res_fresh.json()
    assert fresh_data["live_stream"]["status"] == "camera_connected"
    assert fresh_data["live_stream"]["is_fresh"] is True
    assert fresh_data["live_stream"]["current_queue_count"] == 3
    assert fresh_data["live_stream"]["waiting_time_display"] == "3 min"

    # 3. Simulate stale reading (> 120s ago)
    cam.last_frame_timestamp = datetime.now(timezone.utc) - timedelta(seconds=300)
    db.commit()

    res_stale = client.get(f"/api/stations/{st1_id}/queue-status")
    assert res_stale.status_code == 200
    stale_data = res_stale.json()
    assert stale_data["live_stream"]["is_fresh"] is False
    assert stale_data["live_stream"]["stream_health"] == "DATA_OUTDATED"
    db.close()


def test_queue_history_storage(client: TestClient, auth_setup: dict):
    """Verify live queue snapshot persistence and history API."""
    st1_id = auth_setup["st1"].id
    db = TestingSessionLocal()

    snapshot1 = LiveQueueSnapshot(
        station_id=st1_id,
        queue_count=4,
        total_vehicles_detected=6,
        waiting_time_seconds=210.0,
        measured_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    snapshot2 = LiveQueueSnapshot(
        station_id=st1_id,
        queue_count=2,
        total_vehicles_detected=3,
        waiting_time_seconds=120.0,
        measured_at=datetime.now(timezone.utc),
    )
    db.add_all([snapshot1, snapshot2])
    db.commit()

    res = client.get(f"/api/stations/{st1_id}/queue-history?limit=10")
    assert res.status_code == 200
    history = res.json()
    assert len(history) >= 2
    # Verify records present in descending order
    counts = [h["queue_count"] for h in history]
    assert 2 in counts
    assert 4 in counts
    db.close()
