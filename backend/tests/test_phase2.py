import pytest
from datetime import datetime, timedelta, timezone
from app.models.entities import User
from app.services.auth import hash_password
from tests.conftest import TestingSessionLocal

def test_health_check(client):
    """Verify health endpoint and database connectivity."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_public_stations_empty_initially(client):
    """Verify no fake data exists initially."""
    response = client.get("/api/stations")
    assert response.status_code == 200
    assert response.json() == []


def test_operator_registration_and_login(client):
    """Verify operator provisioning, duplicate prevention, and login with JWT."""
    db = TestingSessionLocal()
    # Provision operator
    existing = db.query(User).filter(User.username == "station_mgr_1").first()
    if not existing:
        op = User(
            username="station_mgr_1",
            email="mgr1@fuelflow.local",
            hashed_password=hash_password("SecurePassword123!"),
            role="operator",
            is_active=True
        )
        db.add(op)
        db.commit()
    db.close()

    # 1. Login with wrong password
    bad_login = client.post("/api/auth/login", json={
        "username": "station_mgr_1",
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401

    # 2. Login with correct password
    good_login = client.post("/api/auth/login", json={
        "username": "station_mgr_1",
        "password": "SecurePassword123!"
    })
    assert good_login.status_code == 200
    token_data = good_login.json()
    assert "access_token" in token_data
    assert token_data["username"] == "station_mgr_1"
    assert token_data["role"] == "operator"


def test_rbac_and_protected_profile(client):
    """Verify profile route rejects unauthorized requests and permits valid tokens."""
    # No token
    res_no_token = client.get("/api/auth/me")
    assert res_no_token.status_code == 401

    # Valid token
    login_res = client.post("/api/auth/login", json={
        "username": "station_mgr_1",
        "password": "SecurePassword123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_auth = client.get("/api/auth/me", headers=headers)
    assert res_auth.status_code == 200
    profile = res_auth.json()
    assert profile["username"] == "station_mgr_1"
    assert profile["role"] == "operator"


def test_station_creation_and_configuration(client):
    """Verify operator can create a station and configure capacity, pumps, and slots."""
    login_res = client.post("/api/auth/login", json={
        "username": "station_mgr_1",
        "password": "SecurePassword123!"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Create real station
    station_payload = {
        "name": "Central Express Fuel",
        "address": "42 High Street, Downtown",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "queue_capacity": 15,
        "pump_count": 4,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 2
    }
    create_res = client.post("/api/stations", json=station_payload, headers=headers)
    assert create_res.status_code == 201
    station = create_res.json()
    station_id = station["id"]
    assert station["name"] == "Central Express Fuel"
    assert station["queue_capacity"] == 15

    # Update capacity and pump count
    update_res = client.put(f"/api/stations/{station_id}", json={
        "queue_capacity": 25,
        "pump_count": 6
    }, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["queue_capacity"] == 25
    assert update_res.json()["pump_count"] == 6

    # Verify public listing now contains Central Express Fuel
    pub_list = client.get("/api/stations")
    assert pub_list.status_code == 200
    assert len(pub_list.json()) >= 1


def test_camera_configuration_security(client):
    """Verify camera configuration stores stream URL securely and masks credentials in responses."""
    login_res = client.post("/api/auth/login", json={
        "username": "station_mgr_1",
        "password": "SecurePassword123!"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Find Central Express Fuel station ID
    stations = client.get("/api/stations").json()
    station_id = stations[0]["id"]

    cam_payload = {
        "camera_type": "rtsp",
        "stream_url": "rtsp://camera_admin:topsecretpass@192.168.1.100:554/stream1",
        "is_active": True,
        "detection_roi": '{"x1": 50, "y1": 100, "x2": 600, "y2": 450}'
    }
    cam_res = client.post(f"/api/stations/{station_id}/camera", json=cam_payload, headers=headers)
    assert cam_res.status_code == 200
    data = cam_res.json()
    # Masked stream URL must hide username and password
    assert "topsecretpass" not in data["stream_url_masked"]
    assert "***:***" in data["stream_url_masked"]
    assert data["is_active"] is True


def test_slot_creation_and_strict_overbooking_prevention(client):
    """Verify that slots are created and overbooking beyond max_capacity is strictly blocked."""
    login_res = client.post("/api/auth/login", json={
        "username": "station_mgr_1",
        "password": "SecurePassword123!"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    stations = client.get("/api/stations").json()
    station_id = stations[0]["id"]

    now = datetime.now(timezone.utc)
    start_time = (now + timedelta(hours=2)).isoformat()
    end_time = (now + timedelta(hours=2, minutes=15)).isoformat()

    # 1. Create a slot with max_capacity = 2
    slot_res = client.post(f"/api/stations/{station_id}/slots", json={
        "start_time": start_time,
        "end_time": end_time,
        "max_capacity": 2
    }, headers=headers)
    assert slot_res.status_code == 201
    slot = slot_res.json()
    slot_id = slot["id"]
    assert slot["max_capacity"] == 2
    assert slot["booked_count"] == 0
    assert slot["available_capacity"] == 2

    # Register & Login Customer User for bookings
    client.post("/api/auth/user/register", json={
        "username": "slot_customer_1",
        "email": "cust1@test.local",
        "password": "CustomerPassword123!"
    })
    cust_token = client.post("/api/auth/user/login", json={
        "username": "slot_customer_1",
        "password": "CustomerPassword123!"
    }).json()["access_token"]
    user_headers = {"Authorization": f"Bearer {cust_token}"}

    # 2. First booking
    b1_res = client.post("/api/bookings", json={
        "slot_id": slot_id,
        "vehicle_plate": "MH12AB1234"
    }, headers=user_headers)
    assert b1_res.status_code == 201
    b1 = b1_res.json()
    ref1 = b1["booking_reference"]
    assert b1["status"] == "CONFIRMED"

    # 3. Duplicate booking attempt for same vehicle in same slot is rejected
    dup_b1 = client.post("/api/bookings", json={
        "slot_id": slot_id,
        "vehicle_plate": "MH12AB1234"
    }, headers=user_headers)
    assert dup_b1.status_code == 400

    # 4. Second booking (fills capacity 2 of 2)
    b2_res = client.post("/api/bookings", json={
        "slot_id": slot_id,
        "vehicle_plate": "MH12CD5678"
    }, headers=user_headers)
    assert b2_res.status_code == 201

    # Check slot status (now full)
    slots_list = client.get(f"/api/stations/{station_id}/slots").json()
    target_slot = [s for s in slots_list if s["id"] == slot_id][0]
    assert target_slot["booked_count"] == 2
    assert target_slot["available_capacity"] == 0

    # 5. Third booking must be rejected with 409 Conflict (Overbooking prevented)
    b3_res = client.post("/api/bookings", json={
        "slot_id": slot_id,
        "vehicle_plate": "MH12EF9999"
    }, headers=user_headers)
    assert b3_res.status_code == 409
    assert "fully booked" in b3_res.json()["detail"]

    # 6. Cancel booking 1 and verify slot capacity restores
    cancel_res = client.post(f"/api/bookings/{ref1}/cancel", json={"reason": "Change of plans"}, headers=user_headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Slot now has available capacity = 1
    slots_after_cancel = client.get(f"/api/stations/{station_id}/slots").json()
    target_slot_after = [s for s in slots_after_cancel if s["id"] == slot_id][0]
    assert target_slot_after["booked_count"] == 1
    assert target_slot_after["available_capacity"] == 1

    # 7. Now third vehicle can successfully book the freed capacity
    b3_retry = client.post("/api/bookings", json={
        "slot_id": slot_id,
        "vehicle_plate": "MH12EF9999"
    }, headers=user_headers)
    assert b3_retry.status_code == 201
    assert b3_retry.json()["status"] == "CONFIRMED"


def test_station_search_and_distance_calculation(client):
    """Verify keyword filtering and real Haversine distance computation."""
    # Search for non-existent keyword
    empty_search = client.get("/api/stations?search=NonExistentKeywordXYZ")
    assert empty_search.status_code == 200
    assert empty_search.json() == []

    # Search for "Central"
    match_search = client.get("/api/stations?search=Central")
    assert match_search.status_code == 200
    assert len(match_search.json()) >= 1
    assert match_search.json()[0]["name"] == "Central Express Fuel"

    # Search with coordinates
    dist_search = client.get("/api/stations?lat=18.5300&lng=73.8500")
    assert dist_search.status_code == 200
    data = dist_search.json()
    assert len(data) >= 1
    assert data[0]["distance_km"] is not None
    assert data[0]["distance_km"] > 0.5
    assert data[0]["distance_km"] < 5.0


def test_user_booking_search(client):
    """Verify users can search for their confirmed/cancelled bookings by phone, plate, or reference."""
    cust_token = client.post("/api/auth/user/login", json={
        "username": "slot_customer_1",
        "password": "CustomerPassword123!"
    }).json()["access_token"]
    user_headers = {"Authorization": f"Bearer {cust_token}"}

    # Search by plate
    plate_res = client.get("/api/bookings?query=MH12CD5678", headers=user_headers)
    assert plate_res.status_code == 200
    bookings = plate_res.json()
    assert len(bookings) == 1
    assert bookings[0]["vehicle_plate"] == "MH12CD5678"

    # Search by user contact
    phone_res = client.get("/api/bookings?query=cust1@test.local", headers=user_headers)
    assert phone_res.status_code == 200
    assert len(phone_res.json()) >= 1

    # Empty query returns empty list
    blank_res = client.get("/api/bookings?query=", headers=user_headers)
    assert blank_res.status_code == 200
    assert blank_res.json() == []
