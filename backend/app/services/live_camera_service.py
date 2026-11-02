"""
FuelFlow Phase 4: Live CCTV Integration and Real-Time Queue Analytics Service.
Handles genuine camera stream capture (RTSP, HTTP/MJPEG, webcam), frame sampling,
real Ultralytics YOLO vehicle detection & ByteTrack tracking, Queue Region (ROI) filtering,
and live frame encoding for operator dashboard preview.
"""

import re
import math
import time
import json
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Tuple, List

import cv2
import numpy as np
from sqlalchemy.orm import Session

import os
from app.database import SessionLocal
from app.models.entities import CameraConfig, LiveQueueSnapshot
from app.services.video_analyzer import (
    get_yolo_model,
    get_model_class_configuration,
    parse_roi,
    is_in_roi,
    VEHICLE_CLASS_MAP,
    VEHICLE_CLASS_IDS,
    get_vehicle_color,
    get_vehicle_text_color,
)
from app.config import (
    calculate_estimated_queue_wait_minutes,
    format_queue_wait_display,
)

logger = logging.getLogger("fuelflow.live_camera")


def utc_now():
    return datetime.now(timezone.utc)


def mask_stream_url(url: str) -> str:
    """Mask credentials in RTSP/HTTP URLs for logging and client responses."""
    pattern = r"^(https?|rtsp|rtsps)://([^:]+):([^@]+)@(.*)$"
    match = re.match(pattern, url)
    if match:
        scheme, _, _, remainder = match.groups()
        return f"{scheme}://***:***@{remainder}"
    return re.sub(r"(token|key|password|pass)=([^&]+)", r"\1=***", url)


def validate_stream_url(stream_url: str, camera_type: str) -> Tuple[bool, str]:
    """
    Validate camera stream URL for safety and SSRF prevention.
    Rejects disallowed schemes, cloud metadata endpoints, and malformed inputs.
    Supports real CCTV cameras (RTSP, HTTP), local webcams, and sample test video files.
    """
    if not stream_url or not stream_url.strip():
        return False, "Stream URL or camera index cannot be empty."

    clean_url = stream_url.strip()

    # 0. Local video file or sample footage source (for offline stream testing)
    if camera_type in ("file", "sample") or clean_url.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        clean_path = clean_url.replace("file://", "").strip()
        if os.path.exists(clean_path):
            return True, "Valid video file source."
        return False, f"Video file not found at: {clean_path}"

    # 1. Webcam / local device index
    if camera_type == "webcam":
        if clean_url.isdigit() or clean_url.startswith("/dev/video"):
            return True, "Valid webcam source."
        return False, "Webcam source must be a numeric device index (e.g., '0') or device path."

    # 2. Network streams (RTSP or HTTP)
    try:
        parsed = urlparse(clean_url)
    except Exception as e:
        return False, f"Malformed stream URL: {e}"

    scheme = parsed.scheme.lower()
    if camera_type == "rtsp":
        if scheme not in ("rtsp", "rtsps"):
            return False, f"Invalid protocol for RTSP camera: expected 'rtsp://' or 'rtsps://', got '{scheme}://'."
    elif camera_type == "http":
        if scheme not in ("http", "https"):
            return False, f"Invalid protocol for HTTP camera: expected 'http://' or 'https://', got '{scheme}://'."
    else:
        return False, f"Unsupported camera type: {camera_type}."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "Stream URL must include a valid hostname or IP address."

    # SSRF Protection: Block cloud metadata endpoints
    blocked_hosts = {
        "169.254.169.254",
        "metadata.google.internal",
        "100.100.100.200",
        "instance-data",
    }
    if hostname in blocked_hosts:
        return False, "Access to cloud metadata endpoints is strictly blocked for security."

    return True, "Valid stream configuration."


class StationLiveCameraWorker:
    """
    Dedicated background worker for a single fuel station's live camera feed.
    Performs frame capture, sampling, YOLO vehicle detection & ByteTrack tracking,
    ROI queue isolation, dwell-time estimation, and MJPEG frame encoding.
    """

    def __init__(
        self,
        station_id: int,
        stream_url: str,
        camera_type: str,
        roi_config_raw: Optional[str] = None,
        frame_sampling_rate: int = 5,
        camera_name: Optional[str] = None,
    ):
        self.station_id = station_id
        self.stream_url = stream_url
        self.camera_type = camera_type
        self.roi_config_raw = roi_config_raw
        self.frame_sampling_rate = max(1, min(30, frame_sampling_rate))
        self.camera_name = camera_name or f"Forecourt Cam (Stn #{station_id})"

        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        # Live telemetry state
        self.connection_status: str = "DISCONNECTED"  # CONNECTING, CONNECTED, ERROR, RECONNECTING, DISCONNECTED
        self.last_error: Optional[str] = None
        self.last_frame_bytes: Optional[bytes] = None
        self.last_frame_timestamp: Optional[datetime] = None
        self.current_queue_count: int = 0
        self.current_vehicles_total: int = 0
        self.measured_fps: float = 0.0
        self.frame_counter: int = 0
        self.active_queue_track_ids: List[int] = []
        self.active_all_track_ids: List[int] = []
        self.class_breakdown: Dict[str, int] = {}
        self.tractor_detected: bool = False
        self.cumulative_seen_roi_ids: set = set()
        self.model_name: str = "YOLO (ByteTrack)"
        self.model_supports_tractor: bool = False
        self.supported_classes: List[str] = []

        # Dwell time tracking per ByteTrack ID: {track_id: {"first_seen": timestamp, "last_seen": timestamp, "in_roi": bool}}
        self.active_tracks: Dict[int, Dict[str, Any]] = {}
        self.completed_dwell_seconds: List[float] = []
        self.waiting_time_estimate_seconds: Optional[float] = None
        self.estimated_queue_wait_minutes: Optional[int] = None

        # Snapshot persistence timer
        self.last_db_persist_time: float = 0.0

    @property
    def waiting_time_seconds(self) -> Optional[float]:
        return self.waiting_time_estimate_seconds

    @property
    def last_frame_time(self) -> Optional[datetime]:
        return self.last_frame_timestamp

    @property
    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive() and not self.stop_event.is_set())

    def get_telemetry_snapshot(self) -> Dict[str, Any]:
        """Return thread-safe snapshot of all real-time tracking metrics."""
        with self.lock:
            return {
                "station_id": self.station_id,
                "camera_name": self.camera_name,
                "camera_type": self.camera_type,
                "connection_status": self.connection_status,
                "last_error": self.last_error,
                "current_queue_count": self.current_queue_count,
                "current_vehicles_total": self.current_vehicles_total,
                "active_track_ids": list(self.active_all_track_ids),
                "active_queue_track_ids": list(self.active_queue_track_ids),
                "class_breakdown": dict(self.class_breakdown),
                "tractor_detected": self.tractor_detected,
                "measured_fps": self.measured_fps,
                "frame_number": self.frame_counter,
                "last_frame_timestamp": self.last_frame_timestamp,
                "waiting_time_seconds": self.waiting_time_estimate_seconds,
                "estimated_queue_wait_minutes": self.estimated_queue_wait_minutes,
                "waiting_time_display": format_queue_wait_display(self.estimated_queue_wait_minutes) if self.connection_status == "CONNECTED" and self.estimated_queue_wait_minutes is not None else "Unavailable",
                "model_name": self.model_name,
                "model_supports_tractor": self.model_supports_tractor,
                "model_classes": list(self.supported_classes),
                "cumulative_queue_vehicles_count": len(self.cumulative_seen_roi_ids),
            }

    def update_waiting_time_estimate(self, queue_class_counts: Optional[Dict[str, int]] = None):
        """
        Formula: Estimated queue wait = sum of (number of waiting vehicles inside ROI * service time per vehicle).
        Round up to next whole minute if necessary (math.ceil). Never decimal minutes.
        Also maintains backwards-compatible dwell exit calibration when queue_class_counts is not provided.
        """
        if queue_class_counts is not None:
            if len(queue_class_counts) > 0 and sum(queue_class_counts.values()) > 0:
                self.estimated_queue_wait_minutes = calculate_estimated_queue_wait_minutes(queue_class_counts)
                self.waiting_time_estimate_seconds = float(self.estimated_queue_wait_minutes * 60)
            else:
                self.estimated_queue_wait_minutes = 0
                self.waiting_time_estimate_seconds = 0.0
        elif len(self.completed_dwell_seconds) >= 3:
            avg_dwell = round(sum(self.completed_dwell_seconds) / len(self.completed_dwell_seconds), 1)
            self.waiting_time_estimate_seconds = avg_dwell
            self.estimated_queue_wait_minutes = int(math.ceil(avg_dwell / 60))
        else:
            self.estimated_queue_wait_minutes = None
            self.waiting_time_estimate_seconds = None

    def start(self):
        """Start the background ingestion and processing thread."""
        if self.thread and self.thread.is_alive():
            logger.warning(f"[Station {self.station_id}] Camera worker is already active.")
            return

        self.stop_event.clear()
        self.connection_status = "CONNECTING"
        self.last_error = None
        self.thread = threading.Thread(
            target=self._run_stream_loop,
            name=f"CameraWorker-Station-{self.station_id}",
            daemon=True,
        )
        self.thread.start()
        logger.info(f"[Station {self.station_id}] Live camera worker started for {mask_stream_url(self.stream_url)}.")

    def stop(self):
        """Signal worker to stop and wait for thread termination."""
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        self.connection_status = "DISCONNECTED"
        self._update_db_status("DISCONNECTED", last_error=None)
        logger.info(f"[Station {self.station_id}] Live camera worker stopped cleanly.")

    def _update_db_status(self, status: str, last_error: Optional[str] = None):
        """Update connection status in database."""
        try:
            with SessionLocal() as db:
                camera = db.query(CameraConfig).filter(CameraConfig.station_id == self.station_id).first()
                if camera:
                    camera.connection_status = status
                    if last_error is not None:
                        camera.last_error = last_error
                    camera.updated_at = utc_now()
                    db.commit()
        except Exception as e:
            logger.warning(f"[Station {self.station_id}] Failed to update DB connection status: {e}")

    def _persist_snapshot(self, queue_count: int, total_vehicles: int, wait_sec: Optional[float]):
        """Persist a periodic measurement snapshot into database."""
        now = utc_now()
        try:
            with SessionLocal() as db:
                # 1. Update CameraConfig live columns
                camera = db.query(CameraConfig).filter(CameraConfig.station_id == self.station_id).first()
                if camera:
                    camera.connection_status = "CONNECTED"
                    camera.current_queue_count = queue_count
                    camera.current_vehicles_total = total_vehicles
                    camera.waiting_time_seconds = wait_sec
                    camera.last_frame_timestamp = now
                    camera.last_heartbeat = now
                    camera.last_error = None

                # 2. Insert periodic LiveQueueSnapshot
                snapshot = LiveQueueSnapshot(
                    station_id=self.station_id,
                    queue_count=queue_count,
                    total_vehicles_detected=total_vehicles,
                    waiting_time_seconds=wait_sec,
                    measured_at=now,
                )
                db.add(snapshot)
                db.commit()
        except Exception as e:
            logger.warning(f"[Station {self.station_id}] Failed to persist live snapshot: {e}")

    def _run_stream_loop(self):
        """Main camera stream capture, YOLO inference, and tracking loop."""
        reconnect_attempts = 0
        max_reconnect_attempts = 5

        while not self.stop_event.is_set():
            # Parse capture target
            source: Any = self.stream_url
            if self.camera_type == "webcam" and self.stream_url.isdigit():
                source = int(self.stream_url)

            logger.info(f"[Station {self.station_id}] Connecting to video source: {mask_stream_url(str(source))}")
            self.connection_status = "CONNECTING"
            self._update_db_status("CONNECTING")

            cap = cv2.VideoCapture(source)

            # Check if camera opened successfully
            if not cap.isOpened():
                err_msg = f"Unable to open stream at {mask_stream_url(self.stream_url)}. Verify stream URL, network access, or RTSP credentials."
                logger.error(f"[Station {self.station_id}] {err_msg}")
                with self.lock:
                    self.connection_status = "ERROR"
                    self.last_error = err_msg
                self._update_db_status("ERROR", last_error=err_msg)

                reconnect_attempts += 1
                if reconnect_attempts >= max_reconnect_attempts or self.stop_event.is_set():
                    logger.info(f"[Station {self.station_id}] Reached maximum reconnection attempts. Pausing worker.")
                    break

                self.connection_status = "RECONNECTING"
                self._update_db_status("RECONNECTING", last_error=err_msg)
                time.sleep(3.0)
                continue

            # Stream connected successfully
            reconnect_attempts = 0
            with self.lock:
                self.connection_status = "CONNECTED"
                self.last_error = None
            self._update_db_status("CONNECTED")
            logger.info(f"[Station {self.station_id}] Camera stream connected. Initiating real YOLO tracking.")

            # Retrieve YOLO model and dynamic class configuration
            try:
                model = get_yolo_model()
                class_map, class_ids, supports_tractor, model_name = get_model_class_configuration(model)
                with self.lock:
                    self.model_name = model_name
                    self.model_supports_tractor = supports_tractor
                    self.supported_classes = list(class_map.values())
            except Exception as e:
                err_msg = f"Failed to load YOLO model: {e}"
                logger.error(err_msg)
                with self.lock:
                    self.connection_status = "ERROR"
                    self.last_error = err_msg
                cap.release()
                break

            is_file_stream = False
            source_str = str(source)
            if os.path.isfile(source_str) or source_str.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
                is_file_stream = True

            frame_counter = 0
            fps_start_time = time.time()
            fps_frame_count = 0
            consecutive_read_errors = 0

            # Last detection results to reuse across sampled frames for smooth overlay
            last_boxes: List[Any] = []
            last_track_ids: List[Optional[int]] = []
            last_classes: List[str] = []
            last_in_roi_flags: List[bool] = []

            while not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    if is_file_stream:
                        # Seamlessly rewind test video file so live CCTV analytics keep running dynamically!
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            time.sleep(0.04)
                            continue
                    else:
                        consecutive_read_errors += 1
                        if consecutive_read_errors <= 15:
                            time.sleep(0.04)
                            continue
                        logger.warning(f"[Station {self.station_id}] Camera stream read failed (>15 consecutive dropped frames).")
                        with self.lock:
                            self.connection_status = "RECONNECTING"
                            self.last_error = "Camera feed lost. Attempting reconnection..."
                        self._update_db_status("RECONNECTING", last_error="Camera feed lost.")
                        break
                else:
                    consecutive_read_errors = 0

                frame_counter += 1
                fps_frame_count += 1
                now_ts = utc_now()
                height, width = frame.shape[:2]
                roi = parse_roi(self.roi_config_raw, width, height)

                # Frame pacing for video file test feeds to avoid rushing ahead of real-time
                if is_file_stream:
                    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
                    time.sleep(1.0 / max(10.0, min(50.0, src_fps)) * 0.75)

                # Process YOLO inference on sampled frames to control CPU/GPU load
                should_run_inference = (frame_counter % self.frame_sampling_rate == 0)

                if should_run_inference:
                    try:
                        results = model.track(
                            frame,
                            persist=True,
                            classes=class_ids,
                            tracker="bytetrack.yaml",
                            verbose=False,
                        )

                        last_boxes = []
                        last_track_ids = []
                        last_classes = []
                        last_in_roi_flags = []
                        queue_count = 0
                        total_vehicles = 0
                        current_frame_track_ids = set()
                        current_queue_track_ids = []
                        class_counts: Dict[str, int] = {}
                        current_queue_classes: Dict[str, int] = {}

                        if results and len(results) > 0 and results[0].boxes is not None:
                            boxes = results[0].boxes
                            for i in range(len(boxes)):
                                xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                                bx1, by1, bx2, by2 = xyxy
                                cls_id = int(boxes.cls[i].item())
                                cls_name = class_map.get(cls_id, "vehicle")
                                class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

                                track_id: Optional[int] = None
                                if boxes.id is not None:
                                    track_id = int(boxes.id[i].item())
                                    current_frame_track_ids.add(track_id)

                                total_vehicles += 1
                                in_queue = is_in_roi((bx1, by1, bx2, by2), roi)
                                if in_queue:
                                    queue_count += 1
                                    current_queue_classes[cls_name] = current_queue_classes.get(cls_name, 0) + 1
                                    if track_id is not None:
                                        current_queue_track_ids.append(track_id)
                                        self.cumulative_seen_roi_ids.add(track_id)

                                # Dwell time tracking for genuine waiting-time estimation
                                if track_id is not None:
                                    now_epoch = time.time()
                                    if track_id not in self.active_tracks:
                                        self.active_tracks[track_id] = {
                                            "first_seen": now_epoch,
                                            "last_seen": now_epoch,
                                            "in_roi": in_queue,
                                            "first_roi_time": now_epoch if in_queue else None,
                                        }
                                    else:
                                        rec = self.active_tracks[track_id]
                                        rec["last_seen"] = now_epoch
                                        if in_queue and rec["first_roi_time"] is None:
                                            rec["first_roi_time"] = now_epoch
                                        rec["in_roi"] = in_queue

                                last_boxes.append((bx1, by1, bx2, by2))
                                last_track_ids.append(track_id)
                                last_classes.append(cls_name)
                                last_in_roi_flags.append(in_queue)

                        # Clean up tracks that have exited the scene (not seen for >8 seconds)
                        now_epoch = time.time()
                        exited_tracks = []
                        for tid, rec in list(self.active_tracks.items()):
                            if now_epoch - rec["last_seen"] > 8.0:
                                # If vehicle resided inside ROI for >2 seconds before exiting, count as completed dwell
                                if rec["first_roi_time"] is not None:
                                    dwell = rec["last_seen"] - rec["first_roi_time"]
                                    if dwell >= 2.0:
                                        self.completed_dwell_seconds.append(dwell)
                                        if len(self.completed_dwell_seconds) > 20:
                                            self.completed_dwell_seconds.pop(0)
                                exited_tracks.append(tid)

                        for tid in exited_tracks:
                            self.active_tracks.pop(tid, None)

                        # Waiting-time estimation: sum of (waiting vehicles * service time per vehicle)
                        self.update_waiting_time_estimate(current_queue_classes)

                        with self.lock:
                            self.current_queue_count = queue_count
                            self.current_vehicles_total = total_vehicles
                            self.active_queue_track_ids = current_queue_track_ids
                            self.active_all_track_ids = sorted(list(current_frame_track_ids))
                            self.class_breakdown = dict(class_counts)
                            self.tractor_detected = (class_counts.get("tractor", 0) > 0)
                            self.last_frame_timestamp = now_ts
                            self.frame_counter = frame_counter

                        # Persist periodic snapshot into DB every ~15 seconds
                        if now_epoch - self.last_db_persist_time >= 15.0:
                            self._persist_snapshot(queue_count, total_vehicles, self.waiting_time_estimate_seconds)
                            self.last_db_persist_time = now_epoch

                    except Exception as e:
                        logger.error(f"[Station {self.station_id}] Inference error: {e}")
                else:
                    with self.lock:
                        self.last_frame_timestamp = now_ts
                        self.frame_counter = frame_counter

                # FPS calculation
                elapsed_fps = time.time() - fps_start_time
                if elapsed_fps >= 1.0:
                    self.measured_fps = round(fps_frame_count / elapsed_fps, 1)
                    fps_frame_count = 0
                    fps_start_time = time.time()

                # Annotate frame with real YOLO overlays & Queue Region
                annotated = frame.copy()

                # Resolution-adaptive scaling for high-visibility bounding boxes and labels
                scale_factor = max(1.0, min(width, height) / 720.0)
                thick_in_queue = max(3, int(round(4 * scale_factor)))
                thick_outside = max(2, int(round(2.5 * scale_factor)))
                roi_border_thick = max(3, int(round(4 * scale_factor)))
                font_scale = max(0.55, 0.65 * scale_factor)
                text_thick = max(1, int(round(1.8 * scale_factor)))
                padding = max(3, int(round(4 * scale_factor)))

                # 1. Draw Queue Region (ROI)
                rx1, ry1, rx2, ry2 = roi
                # High-contrast Amber/Orange rectangle for ROI instead of dark charcoal
                cv2.rectangle(annotated, (rx1, ry1), (rx2, ry2), (0, 165, 255), roi_border_thick)
                cv2.putText(
                    annotated,
                    "QUEUE REGION (ROI)",
                    (rx1 + int(8 * scale_factor), ry1 + int(24 * scale_factor)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 165, 255),
                    text_thick,
                    cv2.LINE_AA,
                )

                # 2. Draw vehicle bounding boxes
                for idx, (bx1, by1, bx2, by2) in enumerate(last_boxes):
                    in_q = last_in_roi_flags[idx] if idx < len(last_in_roi_flags) else False
                    cls_name = last_classes[idx] if idx < len(last_classes) else "vehicle"
                    tid = last_track_ids[idx] if idx < len(last_track_ids) else None

                    # Distinct vibrant color per vehicle type (Car: Green, Motorcycle: Blue, Bus: Yellow, Truck: Magenta) - NEVER black
                    box_color = get_vehicle_color(cls_name)
                    text_color = get_vehicle_text_color(cls_name)
                    box_thickness = thick_in_queue if in_q else thick_outside
                    cv2.rectangle(annotated, (bx1, by1), (bx2, by2), box_color, box_thickness)

                    id_str = f"#{tid} " if tid is not None else ""
                    in_q_str = " [IN QUEUE]" if in_q else ""
                    label = f"{id_str}{cls_name.upper()}{in_q_str}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thick)
                    label_y1 = max(0, by1 - th - padding * 2)
                    cv2.rectangle(annotated, (bx1, label_y1), (bx1 + tw + padding * 2, label_y1 + th + padding * 2), box_color, -1)
                    cv2.putText(
                        annotated,
                        label,
                        (bx1 + padding, label_y1 + th + padding),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale,
                        text_color,
                        text_thick,
                        cv2.LINE_AA,
                    )

                # 3. Top Telemetry Banner
                banner_h = max(36, int(round(36 * scale_factor)))
                cv2.rectangle(annotated, (0, 0), (width, banner_h), (32, 32, 32), -1)

                # Live status pulsing green dot
                dot_r = max(4, int(round(4 * scale_factor)))
                dot_cx = int(round(16 * scale_factor))
                dot_cy = banner_h // 2
                cv2.circle(annotated, (dot_cx, dot_cy), dot_r, (74, 222, 128), -1)

                wait_text = (
                    f"Estimated Queue Wait: {self.estimated_queue_wait_minutes} min"
                    if self.estimated_queue_wait_minutes is not None
                    else "Estimated Queue Wait: Unavailable"
                )
                cam_label = getattr(self, "camera_name", f"Station #{self.station_id}")
                telemetry = (
                    f"LIVE CCTV | {cam_label} | Queue: {self.current_queue_count} | "
                    f"Total: {self.current_vehicles_total} | {self.measured_fps} FPS | {wait_text}"
                )
                cv2.putText(
                    annotated,
                    telemetry,
                    (dot_cx + int(round(12 * scale_factor)), int(round(banner_h * 0.68))),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.46, 0.52 * scale_factor),
                    (255, 255, 255),
                    max(1, int(round(1.2 * scale_factor))),
                    cv2.LINE_AA,
                )

                # Encode frame to JPEG for live MJPEG stream & preview
                success, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if success:
                    with self.lock:
                        self.last_frame_bytes = buffer.tobytes()

                # Brief sleep to avoid 100% spin if camera delivers high rate
                time.sleep(0.01)

            cap.release()
            logger.info(f"[Station {self.station_id}] Camera capture released.")

        with self.lock:
            self.connection_status = "DISCONNECTED"
        self._update_db_status("DISCONNECTED")


class LiveCameraManager:
    """
    Singleton manager tracking all active live camera workers across stations.
    Ensures safe concurrency, station isolation, and zero duplicated workers.
    """

    def __init__(self):
        self._workers: Dict[int, StationLiveCameraWorker] = {}
        self._lock = threading.Lock()

    def start_camera(
        self,
        station_id: int,
        stream_url: str,
        camera_type: str,
        roi_config: Optional[str] = None,
        frame_sampling_rate: int = 5,
        camera_name: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Start live stream worker for a station."""
        valid, msg = validate_stream_url(stream_url, camera_type)
        if not valid:
            return False, msg

        with self._lock:
            existing = self._workers.get(station_id)
            if existing:
                # If already running with same URL, keep running
                if existing.stream_url == stream_url and existing.connection_status in ("CONNECTED", "CONNECTING"):
                    if camera_name:
                        existing.camera_name = camera_name
                    return True, "Camera stream worker is already active."
                # If running with different URL or stopped, stop previous
                existing.stop()

            worker = StationLiveCameraWorker(
                station_id=station_id,
                stream_url=stream_url,
                camera_type=camera_type,
                roi_config_raw=roi_config,
                frame_sampling_rate=frame_sampling_rate,
                camera_name=camera_name,
            )
            self._workers[station_id] = worker
            worker.start()

        return True, f"Live camera worker initiated for Station {station_id}."

    def stop_camera(self, station_id: int) -> Tuple[bool, str]:
        """Stop live stream worker for a station."""
        with self._lock:
            worker = self._workers.pop(station_id, None)
            if worker:
                worker.stop()
                return True, f"Camera worker for Station {station_id} stopped."
            return True, f"No active camera worker found for Station {station_id}."

    def get_worker(self, station_id: int) -> Optional[StationLiveCameraWorker]:
        """Retrieve active worker for a station."""
        with self._lock:
            return self._workers.get(station_id)

    def get_latest_frame(self, station_id: int) -> Optional[bytes]:
        """Retrieve latest processed JPEG frame bytes for a station."""
        worker = self.get_worker(station_id)
        if not worker:
            return None
        with worker.lock:
            return worker.last_frame_bytes

    def test_stream_connection(
        self,
        stream_url: str,
        camera_type: str,
        timeout_seconds: float = 4.0,
    ) -> Dict[str, Any]:
        """
        Quick synchronous probe of a stream to verify reachability and decode a single frame.
        Does not start persistent worker.
        """
        valid, msg = validate_stream_url(stream_url, camera_type)
        if not valid:
            return {
                "success": False,
                "message": msg,
                "camera_type": camera_type,
                "resolution": None,
                "fps": None,
                "error_detail": msg,
            }

        source: Any = stream_url
        if camera_type in ("file", "sample") or os.path.isfile(str(stream_url)):
            source = str(stream_url).replace("file://", "")
        elif camera_type == "webcam" and stream_url.isdigit():
            source = int(stream_url)
        elif camera_type in ("rtsp", "http"):
            # Fast TCP socket pre-check (2.0s timeout) to prevent blocking on offline network endpoints
            try:
                parsed = urlparse(stream_url)
                host = parsed.hostname
                port = parsed.port or (554 if camera_type == "rtsp" else (443 if parsed.scheme == "https" else 80))
                if host:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)
                    sock.connect((host, port))
                    sock.close()
            except Exception as conn_err:
                return {
                    "success": False,
                    "message": f"Connection failed to {mask_stream_url(stream_url)}: Host unreachable ({conn_err}).",
                    "camera_type": camera_type,
                    "resolution": None,
                    "fps": None,
                    "error_detail": str(conn_err),
                }

        try:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                return {
                    "success": False,
                    "message": f"Connection failed to {mask_stream_url(stream_url)}. Verify URL and network credentials.",
                    "camera_type": camera_type,
                    "resolution": None,
                    "fps": None,
                    "error_detail": "cv2.VideoCapture could not open stream.",
                }

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                return {
                    "success": False,
                    "message": "Stream opened, but unable to decode any video frame.",
                    "camera_type": camera_type,
                    "resolution": None,
                    "fps": None,
                    "error_detail": "No frames decoded.",
                }

            height, width = frame.shape[:2]
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            cap.release()

            return {
                "success": True,
                "message": f"Stream verified successfully ({width}x{height} @ {fps:.1f} FPS).",
                "camera_type": camera_type,
                "resolution": f"{width}x{height}",
                "fps": fps,
                "error_detail": None,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error while probing stream: {str(e)}",
                "camera_type": camera_type,
                "resolution": None,
                "fps": None,
                "error_detail": str(e),
            }

    def shutdown_all(self):
        """Stop all workers upon application shutdown."""
        with self._lock:
            for st_id, worker in list(self._workers.items()):
                logger.info(f"Stopping worker for station {st_id} during shutdown...")
                worker.stop()
            self._workers.clear()


# Global Singleton Manager instance
live_camera_manager = LiveCameraManager()
