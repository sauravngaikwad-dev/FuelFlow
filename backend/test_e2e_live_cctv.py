import urllib.request
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_e2e_verification():
    print("--- 1. Authenticate Operator ---")
    from app.services.auth import create_access_token
    token = create_access_token({"sub": "5", "username": "operator", "role": "operator"})
    print(f"Generated Operator JWT token: {token[:20]}...")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    STATION_ID = 2
    print(f"\n--- 2. Save Camera Configuration (Local MP4 Feed for Station {STATION_ID}) ---")
    video_path = "C:/Users/SAURAV GAIKWAD/Downloads/New/traffic_feed.mp4"
    config_payload = json.dumps({
        "camera_name": "Forecourt Test CCTV",
        "camera_type": "file",
        "stream_url": video_path,
        "is_active": True,
        "frame_sampling_rate": 3,
        "detection_roi": json.dumps({"x1": 0.05, "y1": 0.10, "x2": 0.95, "y2": 0.90})
    }).encode('utf-8')

    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera", data=config_payload, headers=headers)
    with urllib.request.urlopen(req) as resp:
        print("Camera config saved:", json.loads(resp.read().decode()))

    print("\n--- 3. Test Probe Stream ---")
    probe_payload = json.dumps({
        "camera_type": "file",
        "stream_url": video_path
    }).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/test", data=probe_payload, headers=headers)
    with urllib.request.urlopen(req) as resp:
        probe_res = json.loads(resp.read().decode())
        print("Probe result:", probe_res)
        assert probe_res["success"] is True

    print("\n--- 4. Connect Camera Worker ---")
    connect_payload = json.dumps({"frame_sampling_rate": 3}).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/connect", data=connect_payload, headers=headers)
    with urllib.request.urlopen(req) as resp:
        print("Connect response:", json.loads(resp.read().decode()))

    print("\n--- 5. Collect Live Telemetry Across 6 Time Intervals ---")
    snapshots = []
    for i in range(6):
        time.sleep(1.5)
        req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/live-status", headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            snapshots.append(data)
            print(f"Sample {i+1}: Status={data.get('connection_status')} | Frame={data.get('frame_number')} | "
                  f"TotalVehicles={data.get('total_vehicles_detected')} | QueueLength={data.get('queue_length')} | "
                  f"ActiveIDs={data.get('active_track_ids')} | ROI_IDs={data.get('active_queue_track_ids')} | "
                  f"Classes={data.get('class_breakdown')} | Tractor={data.get('tractor_detected')}")

    print("\n--- 6. Verify Dynamic Tracking Progression ---")
    frame_numbers = [s.get('frame_number', 0) for s in snapshots]
    print(f"Observed Frame Numbers: {frame_numbers}")
    assert frame_numbers[-1] > frame_numbers[0], "Frames are static! Frame counter must increase."
    print("Frame progression verified: frames are continuously read and analyzed.")

    # Check track IDs
    all_seen_ids = set()
    for s in snapshots:
        all_seen_ids.update(s.get('active_track_ids', []))
    print(f"Total Unique Track IDs Tracked by ByteTrack across samples: {sorted(list(all_seen_ids))}")
    assert len(all_seen_ids) > 0, "No tracking IDs observed!"

    print("\n--- 7. Fetch Snapshot Image ---")
    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/live-snapshot", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        img_bytes = resp.read()
        print(f"Annotated frame snapshot fetched: {len(img_bytes)} bytes (JPEG header check: {img_bytes[:2] == b'\\xff\\xd8'})")

    print("\n--- 8. Disconnect Camera Worker ---")
    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/disconnect", data=b"{}", headers=headers)
    with urllib.request.urlopen(req) as resp:
        disc_res = json.loads(resp.read().decode())
        print("Disconnect response:", disc_res)

    # Verify status is now DISCONNECTED
    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/live-status", headers=headers)
    with urllib.request.urlopen(req) as resp:
        disc_status = json.loads(resp.read().decode())
        print(f"Status after disconnect: {disc_status.get('connection_status')}")
        assert disc_status.get('connection_status') == "DISCONNECTED"

    print("\n--- 9. Error Handling Verification (Invalid Stream URL) ---")
    err_payload = json.dumps({
        "camera_type": "file",
        "stream_url": "C:/invalid/path/nonexistent.mp4"
    }).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/api/stations/{STATION_ID}/camera/test", data=err_payload, headers=headers)
    with urllib.request.urlopen(req) as resp:
        err_res = json.loads(resp.read().decode())
        print("Invalid stream test result:", err_res)
        assert err_res["success"] is False
        assert "not found" in err_res["message"].lower() or "cannot open" in err_res["message"].lower()

    print("\n=== ALL LIVE CCTV TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_e2e_verification()
