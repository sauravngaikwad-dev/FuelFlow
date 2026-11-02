import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

import cv2
from sqlalchemy.orm import Session
from ultralytics import YOLO

from app.database import SessionLocal
from app.models.entities import VideoAnalysisRecord
from app.config import (
    calculate_estimated_queue_wait_minutes,
    format_queue_wait_display,
    get_vehicle_service_time_minutes,
)

logger = logging.getLogger("fuelflow.video_analyzer")

# Dedicated upload directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "videos")
RAW_DIR = os.path.join(UPLOAD_DIR, "raw")
PROCESSED_DIR = os.path.join(UPLOAD_DIR, "processed")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Allowed formats and safety limits
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB max

# Supported COCO vehicle classes for fuel station analysis
# Supported vehicle classes for fuel station analysis (COCO default fallback)
VEHICLE_CLASS_MAP = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}
VEHICLE_CLASS_IDS = list(VEHICLE_CLASS_MAP.keys())

# Vibrant BGR colors per vehicle class (Strictly avoid black/dark charcoal)
# OpenCV uses BGR (Blue, Green, Red) channel ordering:
VEHICLE_COLORS_BGR = {
    "car": (50, 205, 50),         # Vibrant Emerald/Lime Green (RGB: 50, 205, 50)
    "motorcycle": (255, 140, 0),   # Electric Dodger Blue (RGB: 0, 140, 255)
    "bus": (0, 215, 255),          # Bright Gold / Amber (RGB: 255, 215, 0)
    "truck": (220, 50, 180),       # Vivid Magenta / Purple (RGB: 180, 50, 220)
    "tractor": (0, 140, 255),      # High-Contrast Safety Orange (RGB: 255, 140, 0)
    "auto": (220, 220, 0),         # Electric Cyan / Turquoise (RGB: 0, 220, 220)
    "lcv": (205, 130, 40),         # Vivid Royal Blue (RGB: 40, 130, 205)
    "multiaxle": (60, 20, 220),    # Vivid Crimson Red (RGB: 220, 20, 60)
}
DEFAULT_VEHICLE_COLOR_BGR = (255, 190, 0) # Electric Sky Blue (RGB: 0, 190, 255)


def get_vehicle_color(cls_name: str) -> Tuple[int, int, int]:
    """Return distinct vibrant BGR color for vehicle class. Black is strictly never used."""
    return VEHICLE_COLORS_BGR.get(cls_name.lower(), DEFAULT_VEHICLE_COLOR_BGR)


def get_vehicle_text_color(cls_name: str) -> Tuple[int, int, int]:
    """Return high-contrast text color (BGR) against the vehicle badge background."""
    if cls_name.lower() in ("bus", "auto", "tractor"):
        return (20, 20, 20)  # Dark charcoal text on bright amber, gold, or cyan badges
    return (255, 255, 255)   # White text on green, blue, magenta badges


def get_model_class_configuration(model: YOLO) -> Tuple[Dict[int, str], List[int], bool, str]:
    """
    Dynamically inspect the loaded YOLO model to identify supported vehicle classes
    and determine whether a dedicated tractor class exists.
    Returns:
        (class_map, class_ids, supports_tractor, model_name)
    """
    raw_names = getattr(model, "names", {})
    if isinstance(raw_names, list):
        raw_names = {i: name for i, name in enumerate(raw_names)}

    has_tractor = any("tractor" in str(v).lower() for v in raw_names.values())
    target_keywords = {"car", "motorcycle", "bus", "truck", "tractor", "auto", "lcv", "multiaxle", "vehicle"}

    # Filter vehicle classes
    class_map: Dict[int, str] = {}
    for cid, name in raw_names.items():
        clean_name = str(name).lower().strip()
        if any(kw in clean_name for kw in target_keywords):
            class_map[int(cid)] = clean_name

    # If no keyword match found (e.g. custom model with 1-2 classes), keep all
    if not class_map:
        class_map = {int(k): str(v).lower() for k, v in raw_names.items()}

    class_ids = sorted(list(class_map.keys()))

    weights_file = getattr(model, "ckpt_path", None) or getattr(model, "model_name", "YOLO")
    weights_stem = os.path.basename(str(weights_file))

    if has_tractor:
        model_name = f"YOLO ({weights_stem}) - Tractor & Multi-Vehicle ({len(class_ids)} classes)"
    else:
        model_name = f"YOLOv8n ({weights_stem}) - Standard COCO ({len(class_ids)} vehicle classes, no tractor)"

    return class_map, class_ids, has_tractor, model_name


# Shared YOLO model cache
_cached_yolo_model: Optional[YOLO] = None


def get_yolo_model() -> YOLO:
    """Load or retrieve the cached real Ultralytics YOLO model."""
    global _cached_yolo_model
    if _cached_yolo_model is None:
        custom_weights = os.environ.get("YOLO_MODEL_PATH")
        if custom_weights and os.path.exists(custom_weights):
            weights_path = custom_weights
        elif os.path.exists(os.path.join(BASE_DIR, "yolov8m_highway_best.pt")):
            weights_path = os.path.join(BASE_DIR, "yolov8m_highway_best.pt")
        elif os.path.exists(os.path.join(BASE_DIR, "yolov8n.pt")):
            weights_path = os.path.join(BASE_DIR, "yolov8n.pt")
        else:
            weights_path = "yolov8n.pt"
        logger.info(f"Loading Ultralytics YOLO vehicle detection model from: {weights_path}")
        _cached_yolo_model = YOLO(weights_path)
    return _cached_yolo_model


def transcode_to_browser_compatible_mp4(input_path: str, output_path: str) -> bool:
    """
    Transcode video to HTML5 browser-compatible H.264 (avc1) MP4 with faststart.
    Allows instant playback, scrubbing, and seeking across all modern web browsers.
    """
    import subprocess
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = "ffmpeg"

    temp_target = f"{output_path}.transcode_tmp.mp4"
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-crf", "24",
        "-vf", "scale='min(1920,iw)':-2",
        "-movflags", "+faststart",
        "-an",
        temp_target
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if res.returncode == 0 and os.path.exists(temp_target) and os.path.getsize(temp_target) > 0:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            os.replace(temp_target, output_path)
            return True
        else:
            logger.warning(f"FFmpeg transcode returned code {res.returncode}: {res.stderr.decode(errors='ignore')}")
            if os.path.exists(temp_target):
                try:
                    os.remove(temp_target)
                except Exception:
                    pass
            return False
    except Exception as e:
        logger.error(f"Error during video transcode to browser-compatible format: {e}")
        if os.path.exists(temp_target):
            try:
                os.remove(temp_target)
            except Exception:
                pass
        return False


def parse_roi(roi_config_raw: Optional[str], width: int, height: int) -> Tuple[int, int, int, int]:
    """
    Parse region-of-interest coordinates.
    Supports normalized ratios [0.0 - 1.0] or absolute pixels.
    Default: Centered queue area (10% margin left/top, 90% right/bottom).
    Returns (x1, y1, x2, y2) in absolute pixel coordinates.
    """
    default_roi = (int(width * 0.1), int(height * 0.2), int(width * 0.9), int(height * 0.9))
    if not roi_config_raw or not roi_config_raw.strip():
        return default_roi

    try:
        data = json.loads(roi_config_raw)
        x1 = float(data.get("x1", 0.1))
        y1 = float(data.get("y1", 0.2))
        x2 = float(data.get("x2", 0.9))
        y2 = float(data.get("y2", 0.9))

        # Check if coordinates are normalized fractions
        if 0.0 <= x1 <= 1.0 and 0.0 <= x2 <= 1.0:
            px1 = int(x1 * width)
            py1 = int(y1 * height)
            px2 = int(x2 * width)
            py2 = int(y2 * height)
        else:
            px1, py1, px2, py2 = int(x1), int(y1), int(x2), int(y2)

        # Enforce bounds
        px1 = max(0, min(width - 1, px1))
        py1 = max(0, min(height - 1, py1))
        px2 = max(px1 + 10, min(width, px2))
        py2 = max(py1 + 10, min(height, py2))
        return (px1, py1, px2, py2)
    except Exception as e:
        logger.warning(f"Failed to parse ROI config '{roi_config_raw}': {e}. Using default.")
        return default_roi


def is_in_roi(box_coords: Tuple[int, int, int, int], roi: Tuple[int, int, int, int]) -> bool:
    """
    Determine if a vehicle is within the queue region.
    Evaluates both the bottom-center (where wheels touch the ground) and center of the vehicle.
    """
    bx1, by1, bx2, by2 = box_coords
    rx1, ry1, rx2, ry2 = roi

    center_x = (bx1 + bx2) // 2
    bottom_y = by2
    center_y = (by1 + by2) // 2

    in_bottom = (rx1 <= center_x <= rx2) and (ry1 <= bottom_y <= ry2)
    in_center = (rx1 <= center_x <= rx2) and (ry1 <= center_y <= ry2)
    return in_bottom or in_center


def process_video_analysis(analysis_record_id: int, db_session: Optional[Session] = None):
    """
    Background worker:
    1. Reads recorded CCTV video frame-by-frame.
    2. Runs genuine Ultralytics YOLO vehicle detection & ByteTrack tracking.
    3. Excludes vehicles outside the configured Queue ROI from queue metrics.
    4. Annotates frames with bounding boxes, tracking labels, and ROI outline.
    5. Computes peak queue, average queue, duration in queue, and timeline.
    6. Saves historical analysis results into database.
    """
    db: Session = db_session if db_session is not None else SessionLocal()
    should_close = (db_session is None)
    try:
        record = db.query(VideoAnalysisRecord).filter(VideoAnalysisRecord.id == analysis_record_id).first()
        if not record:
            logger.error(f"VideoAnalysisRecord {analysis_record_id} not found.")
            return

        # Mark status as PROCESSING
        record.status = "PROCESSING"
        db.commit()

        video_path = record.video_path
        if not os.path.exists(video_path):
            record.status = "FAILED"
            record.error_message = "Video file not found on disk."
            db.commit()
            return

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            record.status = "FAILED"
            record.error_message = "Failed to open video file. Invalid or corrupted video format."
            db.commit()
            return

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0:
            fps = 25.0
        if total_frames <= 0 or width <= 0 or height <= 0:
            record.status = "INSUFFICIENT_DATA"
            record.error_message = "Video stream has no readable video frames or zero duration."
            db.commit()
            cap.release()
            return

        duration_sec = total_frames / fps
        if duration_sec < 0.5:
            record.status = "INSUFFICIENT_DATA"
            record.error_message = f"Video duration is too short for queue analysis ({duration_sec:.1f}s)."
            db.commit()
            cap.release()
            return

        # Parse ROI
        roi = parse_roi(record.roi_config, width, height)
        rx1, ry1, rx2, ry2 = roi

        # Prepare output video
        output_filename = f"{record.id}_processed.mp4"
        processed_path = os.path.join(PROCESSED_DIR, output_filename)
        temp_raw_path = os.path.join(PROCESSED_DIR, f"{record.id}_raw_temp.mp4")
        
        # mp4v codec for temporary raw output video
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out_writer = cv2.VideoWriter(temp_raw_path, fourcc, fps, (width, height))

        # Tracking and metrics accumulators
        model = get_yolo_model()
        class_map, class_ids, supports_tractor, model_desc = get_model_class_configuration(model)
        unique_vehicles_seen = set()
        class_breakdown: Dict[str, int] = {}
        tracked_in_queue_durations: Dict[int, float] = {}  # track_id -> total seconds in ROI
        queue_count_per_second: Dict[int, int] = {}       # second_idx -> queue count in ROI
        all_detected_per_second: Dict[int, int] = {}
        queue_classes_per_second: Dict[int, Dict[str, int]] = {}  # second_idx -> waiting vehicles by class in ROI

        frame_idx = 0
        frame_interval_sec = 1.0 / fps

        timeline_events = []
        last_recorded_time = -1.0
        prev_queue_count = -1
        prev_total_detected = -1

        # Resolution-adaptive scaling for high-visibility bounding boxes and labels
        scale_factor = max(1.0, min(width, height) / 720.0)
        thick_in_queue = max(3, int(round(4 * scale_factor)))
        thick_outside = max(2, int(round(2.5 * scale_factor)))
        roi_border_thick = max(3, int(round(4 * scale_factor)))
        font_scale = max(0.55, 0.65 * scale_factor)
        text_thick = max(1, int(round(1.8 * scale_factor)))
        padding = max(3, int(round(4 * scale_factor)))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            current_time_sec = frame_idx * frame_interval_sec

            # Run actual YOLO detection and tracking
            try:
                results = model.track(
                    frame,
                    persist=True,
                    classes=class_ids,
                    conf=0.25,
                    verbose=False
                )
            except Exception:
                # If tracker fails on specific frames, fallback to standard detect
                results = model(
                    frame,
                    classes=class_ids,
                    conf=0.25,
                    verbose=False
                )

            current_frame_queue_count = 0
            current_frame_total_detected = 0
            current_frame_queue_classes: Dict[str, int] = {}

            # Draw Queue ROI Box
            # High-contrast Amber/Orange border (#FFA500 / BGR: 0, 165, 255) with clear ROI label
            cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (0, 165, 255), roi_border_thick)
            cv2.putText(
                frame,
                "QUEUE AREA (CONFIGURED ROI)",
                (rx1 + int(8 * scale_factor), max(ry1 - int(8 * scale_factor), int(26 * scale_factor))),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (0, 165, 255),
                text_thick,
                cv2.LINE_AA
            )

            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and len(boxes) > 0:
                    current_frame_total_detected = len(boxes)

                    for box_idx, box in enumerate(boxes):
                        coords = box.xyxy[0].cpu().numpy().astype(int)
                        bx1, by1, bx2, by2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                        cls_id = int(box.cls[0].item())
                        cls_name = class_map.get(cls_id, "vehicle")
                        conf = float(box.conf[0].item())

                        # Tracking ID if available
                        track_id = int(box.id[0].item()) if (box.id is not None) else (box_idx + 1)
                        unique_vehicles_seen.add(track_id)
                        class_breakdown[cls_name] = class_breakdown.get(cls_name, 0) + 1

                        # Vehicle-specific vibrant colors (Car: Green, Motorcycle: Blue, Bus: Yellow, Truck: Magenta) - NEVER black
                        box_color = get_vehicle_color(cls_name)
                        text_color = get_vehicle_text_color(cls_name)

                        # Check if vehicle is inside configured queue ROI
                        in_queue = is_in_roi((bx1, by1, bx2, by2), roi)
                        if in_queue:
                            current_frame_queue_count += 1
                            current_frame_queue_classes[cls_name] = current_frame_queue_classes.get(cls_name, 0) + 1
                            tracked_in_queue_durations[track_id] = tracked_in_queue_durations.get(track_id, 0.0) + frame_interval_sec
                            status_label = f"{cls_name.upper()} #{track_id} [{conf:.0%}] - IN QUEUE"
                            box_thickness = thick_in_queue
                        else:
                            status_label = f"{cls_name.upper()} #{track_id} [{conf:.0%}] - OUTSIDE ROI"
                            box_thickness = thick_outside

                        # Draw bounding box (never black)
                        cv2.rectangle(frame, (bx1, by1), (bx2, by2), box_color, box_thickness)
                        
                        # Label background tag
                        (tw, th), _ = cv2.getTextSize(status_label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thick)
                        label_y1 = max(0, by1 - th - padding * 2)
                        cv2.rectangle(frame, (bx1, label_y1), (bx1 + tw + padding * 2, label_y1 + th + padding * 2), box_color, -1)
                        # Text with high contrast
                        cv2.putText(
                            frame,
                            status_label,
                            (bx1 + padding, label_y1 + th + padding),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            font_scale,
                            text_color,
                            text_thick,
                            cv2.LINE_AA
                        )

            # Telemetry Top Banner
            banner_height = max(56, int(60 * scale_factor))
            cv2.rectangle(frame, (0, 0), (width, banner_height), (48, 48, 48), -1)

            cv2.putText(
                frame,
                "HISTORICAL CCTV ANALYSIS (RECORDED FOOTAGE - NOT LIVE)",
                (12, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )
            current_frame_wait_min = calculate_estimated_queue_wait_minutes(current_frame_queue_classes)
            cv2.putText(
                frame,
                f"Time: {current_time_sec:.1f}s | Queue: {current_frame_queue_count} | Estimated Queue Wait: {current_frame_wait_min} min | Boxed: {current_frame_total_detected}",
                (12, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (232, 232, 232),
                1,
                cv2.LINE_AA
            )

            out_writer.write(frame)

            # Record telemetry events for synchronized live dashboard playback
            # Triggers immediately when a vehicle enters/leaves the queue ROI, or when vehicle count changes,
            # or at regular intervals (every 0.25s) to guarantee tight sync.
            is_roi_transition = (current_frame_queue_count != prev_queue_count)
            is_detection_change = (current_frame_total_detected != prev_total_detected)
            is_periodic_tick = (current_time_sec - last_recorded_time >= 0.25)

            if frame_idx == 1 or is_roi_transition or is_detection_change or is_periodic_tick:
                timeline_events.append({
                    "time_sec": round(float(current_time_sec), 2),
                    "queue_count_roi": int(current_frame_queue_count),
                    "total_detected": int(current_frame_total_detected),
                    "estimated_queue_wait_minutes": int(current_frame_wait_min),
                    "waiting_time_display": f"{int(current_frame_wait_min)} min",
                    "vehicle_classes": dict(current_frame_queue_classes)
                })
                last_recorded_time = current_time_sec
                prev_queue_count = current_frame_queue_count
                prev_total_detected = current_frame_total_detected

            # Record per-second metrics
            sec_bucket = int(current_time_sec)
            if sec_bucket not in queue_count_per_second or current_frame_queue_count > queue_count_per_second[sec_bucket]:
                queue_count_per_second[sec_bucket] = current_frame_queue_count
                all_detected_per_second[sec_bucket] = current_frame_total_detected
                queue_classes_per_second[sec_bucket] = dict(current_frame_queue_classes)

        cap.release()
        out_writer.release()

        # Ensure raw output video was created and written
        if not os.path.exists(temp_raw_path) or os.path.getsize(temp_raw_path) == 0:
            raise RuntimeError(f"Raw processed video was not generated or is empty: {temp_raw_path}")

        # Transcode to HTML5 browser-compatible H.264 (avc1) MP4 with faststart
        transcode_ok = transcode_to_browser_compatible_mp4(temp_raw_path, processed_path)
        if transcode_ok:
            try:
                os.remove(temp_raw_path)
            except Exception:
                pass
        else:
            logger.warning("FFmpeg transcode failed; falling back to raw video file.")
            if os.path.exists(processed_path):
                os.remove(processed_path)
            os.replace(temp_raw_path, processed_path)

        # Confirm the final processed video exists, is non-empty, and fully flushed
        if not os.path.exists(processed_path) or os.path.getsize(processed_path) == 0:
            raise RuntimeError(f"Final processed video file is missing or empty: {processed_path}")

        # Compute summary analytics - strictly counting boxed vehicles detected by YOLO
        total_detected_counts = list(all_detected_per_second.values())
        peak_detected = max(total_detected_counts) if total_detected_counts else 0
        queue_counts = list(queue_count_per_second.values())
        peak_queue = max(queue_counts) if queue_counts else 0
        avg_queue = int(round(sum(queue_counts) / len(queue_counts))) if queue_counts else 0

        # Exact boxed vehicle count detected by YOLO (no ghost tracker IDs)
        total_unique_vehicles = peak_detected

        # Consolidate class breakdown to approximate unique counts
        # (normalized strictly to vehicles detected and boxed by YOLO)
        normalized_classes = {}
        total_detections_sum = sum(class_breakdown.values()) or 1
        remaining = total_unique_vehicles
        if total_unique_vehicles > 0:
            sorted_classes = sorted(class_breakdown.items(), key=lambda x: x[1], reverse=True)
            for idx, (cname, ccount) in enumerate(sorted_classes):
                if idx == len(sorted_classes) - 1:
                    approx_count = max(1, remaining)
                else:
                    approx_count = max(1, round((ccount / total_detections_sum) * total_unique_vehicles))
                    approx_count = min(approx_count, remaining)
                normalized_classes[cname] = approx_count
                remaining -= approx_count
                if remaining <= 0:
                    break

        # Estimated Queue Wait: sum of (waiting vehicles inside ROI * service time per vehicle)
        # Service times: Bike 3 min, Car 5 min, Tractor 10 min, Bus 10 min, Truck 10 min.
        # Find peak queue class distribution inside the queue region (ROI)
        best_queue_sec = None
        if queue_classes_per_second:
            best_queue_sec = max(queue_classes_per_second.keys(), key=lambda s: sum(queue_classes_per_second[s].values()))

        peak_queue_classes = queue_classes_per_second.get(best_queue_sec, {}) if best_queue_sec is not None else {}
        if not peak_queue_classes and peak_queue > 0 and normalized_classes:
            peak_queue_classes = dict(list(normalized_classes.items())[:peak_queue])

        estimated_queue_wait_min = calculate_estimated_queue_wait_minutes(peak_queue_classes)
        # Stored in seconds for database schema compatibility, strictly whole minutes
        avg_wait_sec: Optional[float] = float(estimated_queue_wait_min * 60)

        # Timeline list for synchronized live dashboard playback
        if timeline_events:
            timeline = timeline_events
        else:
            timeline = []
            for s in sorted(queue_count_per_second.keys()):
                sec_classes = queue_classes_per_second.get(s, {})
                sec_wait_min = calculate_estimated_queue_wait_minutes(sec_classes)
                timeline.append({
                    "time_sec": s,
                    "queue_count_roi": queue_count_per_second[s],
                    "total_detected": all_detected_per_second.get(s, queue_count_per_second[s]),
                    "estimated_queue_wait_minutes": sec_wait_min,
                    "waiting_time_display": f"{sec_wait_min} min",
                    "vehicle_classes": sec_classes
                })

        # Update database record
        record.status = "COMPLETED"
        record.fps = round(fps, 2)
        record.total_frames = total_frames
        record.processed_frames = frame_idx
        record.duration_seconds = round(duration_sec, 2)
        record.processed_video_path = processed_path
        record.total_vehicles_detected = total_unique_vehicles
        record.vehicle_classes_detected = json.dumps(normalized_classes)
        record.peak_queue_count = peak_queue
        record.average_queue_count = avg_queue
        record.average_waiting_time_seconds = avg_wait_sec
        record.analytics_timeline = json.dumps(timeline)
        record.completed_at = datetime.now(timezone.utc)
        record.error_message = None
        db.commit()

        logger.info(
            f"Successfully completed analysis for record {record.id}: "
            f"frames={frame_idx}, vehicles={total_unique_vehicles}, peak_queue={peak_queue}"
        )

    except Exception as e:
        logger.exception(f"Error processing video analysis for record {analysis_record_id}: {e}")
        try:
            record = db.query(VideoAnalysisRecord).filter(VideoAnalysisRecord.id == analysis_record_id).first()
            if record:
                record.status = "FAILED"
                record.error_message = f"Inference processing error: {str(e)}"
                db.commit()
        except Exception:
            pass
    finally:
        if should_close:
            db.close()
