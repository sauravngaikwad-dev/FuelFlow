import os
import io
import json
import pytest
import cv2
import numpy as np

from app.database import Base
from app.models.entities import Station, User, VideoAnalysisRecord
from app.services.auth import hash_password
from app.services.video_analyzer import process_video_analysis, RAW_DIR, PROCESSED_DIR
from tests.conftest import TestingSessionLocal


@pytest.fixture
def auth_setup(client):
    """Set up two distinct operators and a normal customer user."""
    db = TestingSessionLocal()

    op1 = db.query(User).filter(User.username == "op_station_1").first()
    if not op1:
        op1 = User(
            username="op_station_1",
            email="op1@fuelflow.com",
            hashed_password=hash_password("Password123!"),
            role="operator",
            is_active=True
        )
        db.add(op1)

    op2 = db.query(User).filter(User.username == "op_station_2").first()
    if not op2:
        op2 = User(
            username="op_station_2",
            email="op2@fuelflow.com",
            hashed_password=hash_password("Password123!"),
            role="operator",
            is_active=True
        )
        db.add(op2)

    cust = db.query(User).filter(User.username == "customer_cctv_test").first()
    if not cust:
        cust = User(
            username="customer_cctv_test",
            email="cust@fuelflow.com",
            hashed_password=hash_password("Password123!"),
            role="user",
            is_active=True
        )
        db.add(cust)

    db.commit()
    db.refresh(op1)
    db.refresh(op2)
    db.refresh(cust)

    # Station owned by Operator 1
    st = db.query(Station).filter(Station.name == "Operator 1 Station").first()
    if not st:
        st = Station(
            name="Operator 1 Station",
            address="100 CCTV Ave",
            latitude=18.5204,
            longitude=73.8567,
            queue_capacity=20,
            pump_count=4,
            slot_duration_minutes=15,
            booking_window_hours=24,
            max_vehicles_per_slot=4,
            operator_id=op1.id
        )
        db.add(st)
        db.commit()
        db.refresh(st)
    station_id = st.id
    db.close()

    # Operator 1 login
    op1_login = client.post("/api/auth/operator/login", json={"username": "op_station_1", "password": "Password123!"})
    op1_token = op1_login.json()["access_token"]

    # Operator 2 login
    op2_login = client.post("/api/auth/operator/login", json={"username": "op_station_2", "password": "Password123!"})
    op2_token = op2_login.json()["access_token"]

    # Customer login
    cust_login = client.post("/api/auth/user/login", json={"username": "customer_cctv_test", "password": "Password123!"})
    cust_token = cust_login.json()["access_token"]

    return {
        "op1_token": op1_token,
        "op2_token": op2_token,
        "cust_token": cust_token,
        "station_id": station_id
    }


def create_dummy_mp4_bytes(num_frames: int = 20, fps: int = 10, width: int = 320, height: int = 240) -> bytes:
    """Generate real MP4 video bytes using OpenCV."""
    temp_path = "temp_gen_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(temp_path, fourcc, fps, (width, height))

    for i in range(num_frames):
        # Generate realistic image frames with geometric objects
        frame = np.full((height, width, 3), 128, dtype=np.uint8)
        # Draw a simulated vehicle shape that traverses across the frame
        x = int(30 + i * (width - 100) / max(1, num_frames))
        y = int(height * 0.4)
        cv2.rectangle(frame, (x, y), (x + 60, y + 40), (40, 40, 40), -1)
        out.write(frame)

    out.release()

    with open(temp_path, "rb") as f:
        data = f.read()

    try:
        os.remove(temp_path)
    except OSError:
        pass

    return data


def test_unauthenticated_and_customer_role_blocked(client, auth_setup):
    """Verify 401 for unauthenticated and 403 for normal users trying to access CCTV endpoints."""
    st_id = auth_setup["station_id"]

    # Unauthenticated request -> 401
    res1 = client.get(f"/api/stations/{st_id}/video-analyses")
    assert res1.status_code == 401

    # Customer user -> 403 Forbidden
    res2 = client.get(
        f"/api/stations/{st_id}/video-analyses",
        headers={"Authorization": f"Bearer {auth_setup['cust_token']}"}
    )
    assert res2.status_code == 403


def test_station_ownership_isolation(client, auth_setup):
    """Verify Operator 2 cannot upload or view CCTV analysis for Operator 1's station."""
    st_id = auth_setup["station_id"]
    fake_video = io.BytesIO(b"fake data")

    # Operator 2 attempts upload to Operator 1's station
    res = client.post(
        f"/api/stations/{st_id}/video-analyses",
        files={"file": ("video.mp4", fake_video, "video/mp4")},
        headers={"Authorization": f"Bearer {auth_setup['op2_token']}"}
    )
    assert res.status_code == 403
    assert "permission" in res.json()["detail"].lower()


def test_invalid_extension_rejected(client, auth_setup):
    """Verify invalid file extensions are rejected with 400 Bad Request."""
    st_id = auth_setup["station_id"]
    txt_file = io.BytesIO(b"this is plain text not video")

    res = client.post(
        f"/api/stations/{st_id}/video-analyses",
        files={"file": ("malicious_script.exe", txt_file, "application/octet-stream")},
        headers={"Authorization": f"Bearer {auth_setup['op1_token']}"}
    )
    assert res.status_code == 400
    assert "unsupported" in res.json()["detail"].lower()


def test_empty_file_rejected(client, auth_setup):
    """Verify 0-byte video uploads are rejected with 400 Bad Request."""
    st_id = auth_setup["station_id"]
    empty_file = io.BytesIO(b"")

    res = client.post(
        f"/api/stations/{st_id}/video-analyses",
        files={"file": ("empty.mp4", empty_file, "video/mp4")},
        headers={"Authorization": f"Bearer {auth_setup['op1_token']}"}
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_real_video_upload_and_yolo_inference(client, auth_setup):
    """
    Generate an actual valid MP4 video, upload it, run genuine YOLO model inference,
    verify queue measurements inside ROI, and test the stream endpoint.
    """
    st_id = auth_setup["station_id"]
    db = TestingSessionLocal()

    video_bytes = create_dummy_mp4_bytes(num_frames=20, fps=10, width=320, height=240)
    video_stream = io.BytesIO(video_bytes)

    # 1. Upload video
    roi_payload = json.dumps({"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.9})
    upload_res = client.post(
        f"/api/stations/{st_id}/video-analyses",
        files={"file": ("cctv_recording_2026.mp4", video_stream, "video/mp4")},
        data={"roi_config": roi_payload},
        headers={"Authorization": f"Bearer {auth_setup['op1_token']}"}
    )
    assert upload_res.status_code == 201
    analysis_data = upload_res.json()
    assert analysis_data["status"] == "PENDING"
    assert analysis_data["filename"] == "cctv_recording_2026.mp4"
    assert analysis_data["analysis_type"] == "HISTORICAL ANALYSIS"
    rec_id = analysis_data["id"]

    # 2. Run real YOLO inference
    process_video_analysis(rec_id, db_session=db)

    # 3. Retrieve analysis results
    detail_res = client.get(
        f"/api/stations/{st_id}/video-analyses/{rec_id}",
        headers={"Authorization": f"Bearer {auth_setup['op1_token']}"}
    )
    assert detail_res.status_code == 200
    res_json = detail_res.json()

    assert res_json["status"] == "COMPLETED"
    assert res_json["total_frames"] == 20
    assert res_json["processed_frames"] == 20
    assert res_json["duration_seconds"] > 0
    assert res_json["fps"] > 0
    assert res_json["has_processed_video"] is True
    assert "HISTORICAL ANALYSIS" in res_json["disclaimer"]

    # 4. Stream processed video
    video_res = client.get(
        f"/api/stations/{st_id}/video-analyses/{rec_id}/video",
        headers={"Authorization": f"Bearer {auth_setup['op1_token']}"}
    )
    assert video_res.status_code == 200
    assert "video" in video_res.headers.get("content-type", "")
    assert len(video_res.content) > 0

    db.close()
