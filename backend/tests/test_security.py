import pytest
from datetime import datetime, timedelta, timezone
from app.bootstrap_admin import bootstrap_admin
from tests.conftest import TestingSessionLocal

@pytest.fixture(scope="module", autouse=True)
def setup_security_admin():
    """Ensure root admin is present in test database."""
    bootstrap_admin("superadmin", "superadmin@fuelflow.local", "SuperAdminPass123!")

def test_public_user_registration_cannot_escalate_role(client):
    """Verify that public user registration strictly assigns role='user'."""
    reg_payload = {
        "username": "customer_alice",
        "email": "alice@customer.local",
        "password": "PasswordAlice123!"
    }
    response = client.post("/api/auth/user/register", json=reg_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "user"
    assert "access_token" in data


def test_normal_user_blocked_from_operator_login(client):
    """Verify normal customer accounts cannot sign in through operator login route."""
    op_login = client.post("/api/auth/operator/login", json={
        "username": "customer_alice",
        "password": "PasswordAlice123!"
    })
    assert op_login.status_code == 403
    assert "operator or administrator privileges" in op_login.json()["detail"]


def test_unauthenticated_requests_receive_401(client):
    """Verify unauthenticated requests to protected endpoints return 401 Unauthorized."""
    # Station creation requires auth
    res1 = client.post("/api/stations", json={"name": "Test", "address": "Test", "latitude": 0, "longitude": 0})
    assert res1.status_code == 401

    # Camera config requires auth
    res2 = client.post("/api/stations/1/camera", json={"camera_type": "rtsp", "stream_url": "rtsp://..."})
    assert res2.status_code == 401

    # Slot creation requires auth
    res3 = client.post("/api/stations/1/slots", json={"start_time": "2026-10-10T10:00:00Z", "end_time": "2026-10-10T10:15:00Z", "max_capacity": 2})
    assert res3.status_code == 401

    # Booking requires user auth
    res4 = client.post("/api/bookings", json={"slot_id": 1, "vehicle_plate": "MH12XY0001"})
    assert res4.status_code == 401

    # My bookings requires auth
    res5 = client.get("/api/bookings/my-bookings")
    assert res5.status_code == 401


def test_normal_user_blocked_from_operator_endpoints_receive_403(client):
    """Verify that normal users receive 403 Forbidden when attempting to call operator APIs."""
    login_user = client.post("/api/auth/user/login", json={
        "username": "customer_alice",
        "password": "PasswordAlice123!"
    })
    token = login_user.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {token}"}

    # Normal user trying to create station -> 403
    st_res = client.post("/api/stations", json={
        "name": "Malicious Station",
        "address": "Hack Street",
        "latitude": 18.5,
        "longitude": 73.8
    }, headers=user_headers)
    assert st_res.status_code == 403

    # Normal user trying to provision an operator -> 403
    admin_res = client.post("/api/auth/admin/create-operator", json={
        "username": "fake_operator",
        "email": "fake@op.local",
        "password": "FakePassword123!"
    }, headers=user_headers)
    assert admin_res.status_code == 403


def test_admin_can_provision_operators(client):
    """Verify administrator can securely provision operator accounts."""
    admin_login = client.post("/api/auth/operator/login", json={
        "username": "superadmin",
        "password": "SuperAdminPass123!"
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Provision Operator 1
    op1_res = client.post("/api/auth/admin/create-operator", json={
        "username": "station_op_one",
        "email": "op1@station.local",
        "password": "OpPasswordOne123!"
    }, headers=admin_headers)
    assert op1_res.status_code == 201
    assert op1_res.json()["role"] == "operator"

    # Provision Operator 2
    op2_res = client.post("/api/auth/admin/create-operator", json={
        "username": "station_op_two",
        "email": "op2@station.local",
        "password": "OpPasswordTwo123!"
    }, headers=admin_headers)
    assert op2_res.status_code == 201
    assert op2_res.json()["role"] == "operator"


def test_operators_can_only_manage_their_own_stations(client):
    """Verify Operator 2 cannot modify or manage Operator 1's station."""
    # Login Operator 1
    op1_token = client.post("/api/auth/operator/login", json={
        "username": "station_op_one",
        "password": "OpPasswordOne123!"
    }).json()["access_token"]
    op1_headers = {"Authorization": f"Bearer {op1_token}"}

    # Login Operator 2
    op2_token = client.post("/api/auth/operator/login", json={
        "username": "station_op_two",
        "password": "OpPasswordTwo123!"
    }).json()["access_token"]
    op2_headers = {"Authorization": f"Bearer {op2_token}"}

    # Operator 1 creates Station Alpha
    st1 = client.post("/api/stations", json={
        "name": "Station Alpha (Op 1)",
        "address": "North Highway",
        "latitude": 18.6,
        "longitude": 73.9,
        "queue_capacity": 20,
        "pump_count": 4
    }, headers=op1_headers).json()
    st1_id = st1["id"]

    # Operator 2 attempts to UPDATE Station Alpha -> Must fail with 403 Forbidden
    hack_st = client.put(f"/api/stations/{st1_id}", json={
        "name": "Hacked Station Name"
    }, headers=op2_headers)
    assert hack_st.status_code == 403
    assert "permission to manage" in hack_st.json()["detail"]

    # Operator 2 attempts to configure CAMERA on Station Alpha -> Must fail with 403
    hack_cam = client.post(f"/api/stations/{st1_id}/camera", json={
        "camera_type": "rtsp",
        "stream_url": "rtsp://attacker@cam/stream",
        "is_active": True
    }, headers=op2_headers)
    assert hack_cam.status_code == 403

    # Operator 2 attempts to create SLOTS on Station Alpha -> Must fail with 403
    start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=1, minutes=15)).isoformat()
    hack_slot = client.post(f"/api/stations/{st1_id}/slots", json={
        "start_time": start,
        "end_time": end,
        "max_capacity": 4
    }, headers=op2_headers)
    assert hack_slot.status_code == 403


def test_user_booking_ownership_and_isolation(client):
    """Verify Users can view and cancel only their own bookings; cross-user tampering is blocked."""
    # 1. Operator 1 creates valid slot for Station Alpha
    stations = client.get("/api/stations").json()
    station_alpha = [s for s in stations if s["name"] == "Station Alpha (Op 1)"][0]
    st1_id = station_alpha["id"]

    op1_token = client.post("/api/auth/operator/login", json={
        "username": "station_op_one",
        "password": "OpPasswordOne123!"
    }).json()["access_token"]
    op1_headers = {"Authorization": f"Bearer {op1_token}"}

    start = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=15)).isoformat()
    slot = client.post(f"/api/stations/{st1_id}/slots", json={
        "start_time": start,
        "end_time": end,
        "max_capacity": 2
    }, headers=op1_headers).json()
    slot_id = slot["id"]

    # 2. User Alice books slot
    alice_token = client.post("/api/auth/user/login", json={
        "username": "customer_alice",
        "password": "PasswordAlice123!"
    }).json()["access_token"]
    alice_headers = {"Authorization": f"Bearer {alice_token}"}

    b_alice = client.post("/api/bookings", json={
        "slot_id": slot_id,
        "vehicle_plate": "MH12ALICE01"
    }, headers=alice_headers).json()
    alice_ref = b_alice["booking_reference"]

    # 3. Register User Bob
    client.post("/api/auth/user/register", json={
        "username": "customer_bob",
        "email": "bob@customer.local",
        "password": "PasswordBob123!"
    })
    bob_token = client.post("/api/auth/user/login", json={
        "username": "customer_bob",
        "password": "PasswordBob123!"
    }).json()["access_token"]
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    # 4. Bob checks 'my-bookings' -> Must NOT see Alice's booking
    bob_bookings = client.get("/api/bookings/my-bookings", headers=bob_headers).json()
    assert len(bob_bookings) == 0

    # 5. Bob tries to query Alice's booking details directly -> Must receive 403 Forbidden
    bob_spy = client.get(f"/api/bookings/{alice_ref}", headers=bob_headers)
    assert bob_spy.status_code == 403

    # 6. Bob tries to CANCEL Alice's booking -> Must receive 403 Forbidden
    bob_cancel = client.post(f"/api/bookings/{alice_ref}/cancel", headers=bob_headers)
    assert bob_cancel.status_code == 403

    # 7. Alice can view and cancel her own booking
    alice_view = client.get(f"/api/bookings/{alice_ref}", headers=alice_headers)
    assert alice_view.status_code == 200
    assert alice_view.json()["booking_reference"] == alice_ref

    alice_cancel = client.post(f"/api/bookings/{alice_ref}/cancel", headers=alice_headers)
    assert alice_cancel.status_code == 200
    assert alice_cancel.json()["status"] == "CANCELLED"
