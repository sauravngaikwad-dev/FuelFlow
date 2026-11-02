"""
Tests for FuelFlow AI's Estimated Queue Wait calculation.

Requirements:
- Whole minutes only (never decimal minutes, e.g. 6 min or 29 min, never 5.9 min or 28.5 min).
- Bike: 2–3 minutes; use 3 minutes for calculation.
- Car: 4–5 minutes; use 5 minutes for calculation.
- Tractor: 10 minutes.
- Bus: 10 minutes.
- Truck: 10 minutes.
- Formula: Estimated queue wait = sum of (number of waiting vehicles * service time per vehicle).
- Round the final estimated waiting time up to the next whole minute if necessary (math.ceil).
- Label the result 'Estimated Queue Wait', not 'Measured Wait'.
- Make service times configurable.
- Do not use video duration to calculate waiting time.
- Preserve actual YOLO detections and queue-region filtering.
"""

import os
import math
import pytest
from app.config import (
    settings,
    get_vehicle_service_time_minutes,
    calculate_estimated_queue_wait_minutes,
    format_queue_wait_display,
)
from app.services.live_camera_service import StationLiveCameraWorker


def test_default_vehicle_service_times():
    """Verify default service times per specification: Bike: 3m, Car: 5m, Tractor: 10m, Bus: 10m, Truck: 10m."""
    assert get_vehicle_service_time_minutes("bike") == 3.0
    assert get_vehicle_service_time_minutes("motorcycle") == 3.0
    assert get_vehicle_service_time_minutes("bicycle") == 3.0
    assert get_vehicle_service_time_minutes("two_wheeler") == 3.0
    assert get_vehicle_service_time_minutes("scooter") == 3.0

    assert get_vehicle_service_time_minutes("car") == 5.0
    assert get_vehicle_service_time_minutes("auto") == 5.0
    assert get_vehicle_service_time_minutes("sedan") == 5.0
    assert get_vehicle_service_time_minutes("suv") == 5.0

    assert get_vehicle_service_time_minutes("tractor") == 10.0
    assert get_vehicle_service_time_minutes("bus") == 10.0

    assert get_vehicle_service_time_minutes("truck") == 10.0
    assert get_vehicle_service_time_minutes("lcv") == 10.0
    assert get_vehicle_service_time_minutes("heavy_vehicle") == 10.0


def test_formula_estimated_queue_wait():
    """
    Formula: Estimated queue wait = sum of (number of waiting vehicles * service time per vehicle).
    """
    # 1 bike (3m) + 1 car (5m) = 8 min
    vehicles = {"bike": 1, "car": 1}
    assert calculate_estimated_queue_wait_minutes(vehicles) == 8

    # 3 cars (3*5 = 15m) + 2 bikes (2*3 = 6m) = 21 min
    vehicles_multiple = {"car": 3, "bike": 2}
    assert calculate_estimated_queue_wait_minutes(vehicles_multiple) == 21

    # 1 tractor (10m) + 1 bus (10m) + 1 truck (10m) = 30 min
    heavy_queue = {"tractor": 1, "bus": 1, "truck": 1}
    assert calculate_estimated_queue_wait_minutes(heavy_queue) == 30

    # Empty queue ROI = 0 min
    assert calculate_estimated_queue_wait_minutes({}) == 0
    assert calculate_estimated_queue_wait_minutes({"car": 0, "bike": 0}) == 0


def test_round_up_to_next_whole_minute_never_decimals():
    """
    Round the final estimated waiting time up to the next whole minute if necessary.
    Never display decimal minutes, such as 5.9 min or 28.5 min. Display values like 6 min or 29 min instead.
    """
    assert format_queue_wait_display(5.9) == "6 min"
    assert format_queue_wait_display(28.5) == "29 min"
    assert format_queue_wait_display(0.1) == "1 min"
    assert format_queue_wait_display(6.0) == "6 min"
    assert format_queue_wait_display(29.0) == "29 min"
    assert format_queue_wait_display(0) == "0 min"
    assert format_queue_wait_display(None) == "Unavailable"

    # Ensure no decimals in display for any fractional minutes
    for val in [0.2, 1.3, 5.9, 12.1, 28.5, 99.7]:
        formatted = format_queue_wait_display(val)
        assert "." not in formatted
        assert formatted.endswith(" min")
        expected_whole = int(math.ceil(val))
        assert formatted == f"{expected_whole} min"


def test_service_times_are_configurable(monkeypatch):
    """Verify that service times can be configured via environment variables."""
    # Temporarily override service times via env vars
    monkeypatch.setenv("SERVICE_TIME_BIKE_MINUTES", "4")
    monkeypatch.setenv("SERVICE_TIME_CAR_MINUTES", "6")
    monkeypatch.setenv("SERVICE_TIME_TRACTOR_MINUTES", "15")

    assert get_vehicle_service_time_minutes("bike") == 4.0
    assert get_vehicle_service_time_minutes("car") == 6.0
    assert get_vehicle_service_time_minutes("tractor") == 15.0

    # 2 bikes (2*4=8) + 1 car (1*6=6) + 1 tractor (15) = 29 min
    assert calculate_estimated_queue_wait_minutes({"bike": 2, "car": 1, "tractor": 1}) == 29

    # Fractional service times configuration rounds up to whole minutes:
    # e.g., Bike 2.5 min, Car 3.4 min -> 1 bike + 1 car = 5.9 min -> rounds up to 6 min
    monkeypatch.setenv("SERVICE_TIME_BIKE_MINUTES", "2.5")
    monkeypatch.setenv("SERVICE_TIME_CAR_MINUTES", "3.4")
    total = calculate_estimated_queue_wait_minutes({"bike": 1, "car": 1})
    assert total == 6  # 2.5 + 3.4 = 5.9 -> rounded up to 6
    assert format_queue_wait_display(total) == "6 min"


def test_video_duration_not_used_to_calculate_waiting_time():
    """
    Ensure waiting time is strictly based on vehicles waiting in queue ROI * service times,
    NOT on video playback duration or file length.
    """
    # 3 cars waiting in ROI = 3 * 5 = 15 minutes
    queue_classes = {"car": 3}
    estimated_wait = calculate_estimated_queue_wait_minutes(queue_classes)
    assert estimated_wait == 15

    # Ensure it is not calculated from video duration
    short_video_duration_sec = 10.0
    long_video_duration_sec = 3600.0
    assert estimated_wait != short_video_duration_sec
    assert estimated_wait != long_video_duration_sec
    assert estimated_wait != (short_video_duration_sec / 60.0)


def test_live_worker_estimated_queue_wait_whole_minutes():
    """Verify live camera worker updates estimated queue wait in whole minutes from ROI vehicle counts."""
    worker = StationLiveCameraWorker(
        station_id=1,
        stream_url="0",
        camera_type="webcam",
    )
    # 2 cars and 1 bike inside ROI
    worker.update_waiting_time_estimate({"car": 2, "bike": 1})
    # 2*5 + 1*3 = 13 minutes
    assert worker.estimated_queue_wait_minutes == 13
    assert worker.waiting_time_estimate_seconds == 13 * 60.0

    worker.connection_status = "CONNECTED"
    status = worker.get_telemetry_snapshot()
    assert status["estimated_queue_wait_minutes"] == 13
    assert status["waiting_time_display"] == "13 min"
    assert "." not in status["waiting_time_display"]

    # When queue is empty inside ROI
    worker.update_waiting_time_estimate({})
    assert worker.estimated_queue_wait_minutes == 0
    assert worker.waiting_time_estimate_seconds == 0.0
