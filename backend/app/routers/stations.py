import re
import math
import time
import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Station, CameraConfig, User, VideoAnalysisRecord, LiveQueueSnapshot
from app.schemas import (
    StationCreateRequest,
    StationUpdateRequest,
    StationResponse,
    CameraConfigUpsertRequest,
    CameraConfigResponse,
    CameraConnectRequest,
    CameraTestRequest,
    CameraTestResponse,
    LiveCameraStatusResponse,
    LiveQueueSnapshotResponse,
)
from app.services.auth import require_role
from app.services.live_camera_service import (
    live_camera_manager,
    validate_stream_url,
    mask_stream_url,
)
from app.config import (
    calculate_estimated_queue_wait_minutes,
    format_queue_wait_display,
)

router = APIRouter(prefix="/api/stations", tags=["Stations"])

def mask_stream_url(url: str) -> str:
    """Mask credentials in RTSP/HTTP URLs to prevent exposing secrets in logs or responses."""
    # Match scheme://user:pass@host...
    pattern = r"^(https?|rtsp)://([^:]+):([^@]+)@(.*)$"
    match = re.match(pattern, url)
    if match:
        scheme, _, _, remainder = match.groups()
        return f"{scheme}://***:***@{remainder}"
    # Mask pure query parameters containing pass/key
    return re.sub(r"(token|key|password|pass)=([^&]+)", r"\1=***", url)


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in kilometers."""
    R = 6371.0  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

@router.get("", response_model=List[StationResponse])
def list_stations(
    search: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Public endpoint: Discover real registered fuel stations.
    Supports optional text search by area/name and distance computation from user coordinates.
    Returns empty list if no stations match or exist.
    """
    query = db.query(Station)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter((Station.name.ilike(term)) | (Station.address.ilike(term)))

    stations = query.all()
    results = []
    for s in stations:
        dist: Optional[float] = None
        if lat is not None and lng is not None:
            dist = calculate_haversine_distance(lat, lng, s.latitude, s.longitude)

        res = StationResponse(
            id=s.id,
            name=s.name,
            address=s.address,
            latitude=s.latitude,
            longitude=s.longitude,
            queue_capacity=s.queue_capacity,
            pump_count=s.pump_count,
            slot_duration_minutes=s.slot_duration_minutes,
            booking_window_hours=s.booking_window_hours,
            max_vehicles_per_slot=s.max_vehicles_per_slot,
            operator_id=s.operator_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            has_camera_configured=(s.camera_config is not None and s.camera_config.is_active),
            distance_km=dist,
            fuel_types_verified=[]
        )
        results.append(res)

    # If user provided location coordinates, sort stations by proximity
    if lat is not None and lng is not None:
        results.sort(key=lambda x: x.distance_km if x.distance_km is not None else float("inf"))

    return results


@router.get("/{station_id}", response_model=StationResponse)
def get_station(station_id: int, db: Session = Depends(get_db)):
    """Public endpoint: Retrieve single station details."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")
    return StationResponse(
        id=station.id,
        name=station.name,
        address=station.address,
        latitude=station.latitude,
        longitude=station.longitude,
        queue_capacity=station.queue_capacity,
        pump_count=station.pump_count,
        slot_duration_minutes=station.slot_duration_minutes,
        booking_window_hours=station.booking_window_hours,
        max_vehicles_per_slot=station.max_vehicles_per_slot,
        operator_id=station.operator_id,
        created_at=station.created_at,
        updated_at=station.updated_at,
        has_camera_configured=(station.camera_config is not None and station.camera_config.is_active)
    )


@router.get("/{station_id}/queue-status")
def get_station_queue_status(station_id: int, db: Session = Depends(get_db)):
    """
    Public endpoint: Retrieve authentic queue status and latest verified CCTV analytics for a station.
    Keeps live camera ingestion strictly distinct from historical recorded-video analysis.
    Evaluates freshness of live camera readings (< 120s = fresh, > 120s = stale).
    If no camera is connected or stream is unavailable, reports camera_disconnected.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    camera = station.camera_config
    worker = live_camera_manager.get_worker(station_id)

    # Determine real live camera status & metrics
    connection_status = "DISCONNECTED"
    current_queue_count = None
    current_vehicles_total = None
    waiting_time_seconds = None
    last_frame_timestamp = None
    is_fresh = False
    stream_health = "OFFLINE"
    message = "Live camera not connected. FuelFlow strictly refuses to fabricate live queue readings."

    if worker and worker.is_running and worker.connection_status == "CONNECTED":
        connection_status = "CONNECTED"
        current_queue_count = worker.current_queue_count
        current_vehicles_total = worker.current_vehicles_total
        waiting_time_seconds = worker.waiting_time_seconds
        last_frame_timestamp = worker.last_frame_time.isoformat() if worker.last_frame_time else None

        # Check freshness: frame received within last 120 seconds
        if worker.last_frame_time:
            age_seconds = (datetime.now(timezone.utc) - worker.last_frame_time).total_seconds()
            if age_seconds <= 120:
                is_fresh = True
                stream_health = "ONLINE"
                message = f"Live stream active. {current_queue_count} vehicles verified in queue ROI ({round(age_seconds)}s ago)."
            else:
                is_fresh = False
                stream_health = "DATA_OUTDATED"
                message = f"Data outdated: Last processed frame was {round(age_seconds)}s ago."
        else:
            stream_health = "CONNECTING"
            message = "Live camera connected, awaiting initial video frames."
    elif camera and camera.is_active:
        connection_status = camera.connection_status
        current_queue_count = camera.current_queue_count
        current_vehicles_total = camera.current_vehicles_total
        waiting_time_seconds = camera.waiting_time_seconds
        if camera.last_frame_timestamp:
            last_frame_timestamp = camera.last_frame_timestamp.isoformat()
            ts = camera.last_frame_timestamp if camera.last_frame_timestamp.tzinfo else camera.last_frame_timestamp.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age <= 120 and camera.connection_status == "CONNECTED":
                is_fresh = True
                stream_health = "ONLINE"
                message = "Live stream active."
            else:
                is_fresh = False
                stream_health = "DATA_OUTDATED"
                message = f"Data outdated: Last frame was {round(age)}s ago."
        else:
            stream_health = "OFFLINE"
            message = f"Camera status: {camera.connection_status}. {camera.last_error or 'Stream inactive'}."

    waiting_time_display = (
        format_queue_wait_display(waiting_time_seconds / 60)
        if waiting_time_seconds is not None
        else "Waiting-time estimate unavailable"
    )

    # Check for latest completed recorded CCTV analysis (Phase 3)
    latest_analysis = (
        db.query(VideoAnalysisRecord)
        .filter(VideoAnalysisRecord.station_id == station_id, VideoAnalysisRecord.status == "COMPLETED")
        .order_by(VideoAnalysisRecord.created_at.desc())
        .first()
    )

    historical_data = None
    if latest_analysis:
        classes = {}
        try:
            if latest_analysis.vehicle_classes_detected:
                classes = json.loads(latest_analysis.vehicle_classes_detected)
        except Exception:
            pass

        hist_wait_sec = latest_analysis.average_waiting_time_seconds
        hist_wait_min = int(math.ceil(hist_wait_sec / 60)) if hist_wait_sec is not None else None
        historical_data = {
            "analysis_id": latest_analysis.id,
            "filename": latest_analysis.filename,
            "detection_timestamp": latest_analysis.completed_at.isoformat() if latest_analysis.completed_at else latest_analysis.created_at.isoformat(),
            "peak_queue_count": latest_analysis.peak_queue_count,
            "average_queue_count": latest_analysis.average_queue_count,
            "total_vehicles_detected": latest_analysis.total_vehicles_detected,
            "vehicle_classes_detected": classes,
            "average_waiting_time_seconds": hist_wait_sec,
            "estimated_queue_wait_minutes": hist_wait_min,
            "waiting_time_display": f"{hist_wait_min} min" if hist_wait_min is not None else "Unavailable",
            "analysis_type": "HISTORICAL RECORDED VIDEO ANALYSIS",
            "disclaimer": "HISTORICAL ANALYSIS: Derived strictly from recorded CCTV video using YOLO detection. Not a current live queue reading."
        }

    return {
        "station_id": station.id,
        "station_name": station.name,
        "queue_capacity": station.queue_capacity,
        "pump_count": station.pump_count,
        "live_stream": {
            "status": "camera_connected" if connection_status == "CONNECTED" else "camera_disconnected",
            "connection_status": connection_status,
            "stream_health": stream_health,
            "is_fresh": is_fresh,
            "message": message,
            "current_queue_count": current_queue_count,
            "current_vehicles_total": current_vehicles_total,
            "waiting_time_estimate_seconds": waiting_time_seconds,
            "waiting_time_display": waiting_time_display,
            "detection_timestamp": last_frame_timestamp,
            "measurement_window_seconds": 60,
            "measurement_basis": "Vehicles detected strictly inside configured Queue ROI over rolling 60s window."
        },
        "historical_analysis": historical_data
    }


@router.post("", response_model=StationResponse, status_code=status.HTTP_201_CREATED)
def create_station(
    payload: StationCreateRequest,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """Protected operator endpoint: Register a real fuel station."""
    new_station = Station(
        name=payload.name,
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        queue_capacity=payload.queue_capacity,
        pump_count=payload.pump_count,
        slot_duration_minutes=payload.slot_duration_minutes,
        booking_window_hours=payload.booking_window_hours,
        max_vehicles_per_slot=payload.max_vehicles_per_slot,
        operator_id=current_user.id
    )
    db.add(new_station)
    db.commit()
    db.refresh(new_station)

    return StationResponse(
        id=new_station.id,
        name=new_station.name,
        address=new_station.address,
        latitude=new_station.latitude,
        longitude=new_station.longitude,
        queue_capacity=new_station.queue_capacity,
        pump_count=new_station.pump_count,
        slot_duration_minutes=new_station.slot_duration_minutes,
        booking_window_hours=new_station.booking_window_hours,
        max_vehicles_per_slot=new_station.max_vehicles_per_slot,
        operator_id=new_station.operator_id,
        created_at=new_station.created_at,
        updated_at=new_station.updated_at,
        has_camera_configured=False
    )


@router.put("/{station_id}", response_model=StationResponse)
def update_station(
    station_id: int,
    payload: StationUpdateRequest,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """Protected operator endpoint: Update queue capacity, pump count, or slot durations."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this station."
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(station, field, value)

    db.commit()
    db.refresh(station)

    return StationResponse(
        id=station.id,
        name=station.name,
        address=station.address,
        latitude=station.latitude,
        longitude=station.longitude,
        queue_capacity=station.queue_capacity,
        pump_count=station.pump_count,
        slot_duration_minutes=station.slot_duration_minutes,
        booking_window_hours=station.booking_window_hours,
        max_vehicles_per_slot=station.max_vehicles_per_slot,
        operator_id=station.operator_id,
        created_at=station.created_at,
        updated_at=station.updated_at,
        has_camera_configured=(station.camera_config is not None and station.camera_config.is_active)
    )


@router.post("/{station_id}/camera", response_model=CameraConfigResponse)
def configure_camera(
    station_id: int,
    payload: CameraConfigUpsertRequest,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """Protected operator endpoint: Configure CCTV/IP camera feed securely."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to configure this station's camera."
        )

    # Validate stream URL
    is_valid, validation_msg = validate_stream_url(payload.stream_url, payload.camera_type)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation_msg)

    camera = db.query(CameraConfig).filter(CameraConfig.station_id == station_id).first()
    cam_name = payload.camera_name.strip() if payload.camera_name and payload.camera_name.strip() else f"{station.name} - Cam 1"
    if not camera:
        camera = CameraConfig(
            station_id=station_id,
            camera_name=cam_name,
            camera_type=payload.camera_type,
            stream_url=payload.stream_url,
            is_active=payload.is_active,
            detection_roi=payload.detection_roi,
            frame_sampling_rate=payload.frame_sampling_rate or 5,
        )
        db.add(camera)
    else:
        # If stream URL or ROI changed, stop running worker so it can restart cleanly
        if camera.stream_url != payload.stream_url or camera.detection_roi != payload.detection_roi:
            live_camera_manager.stop_camera(station_id)

        camera.camera_name = cam_name
        camera.camera_type = payload.camera_type
        camera.stream_url = payload.stream_url
        camera.is_active = payload.is_active
        camera.detection_roi = payload.detection_roi
        if payload.frame_sampling_rate:
            camera.frame_sampling_rate = payload.frame_sampling_rate

    db.commit()
    db.refresh(camera)

    return CameraConfigResponse(
        id=camera.id,
        station_id=camera.station_id,
        camera_name=camera.camera_name or f"{station.name} - Cam 1",
        camera_type=camera.camera_type,
        is_active=camera.is_active,
        detection_roi=camera.detection_roi,
        last_heartbeat=camera.last_heartbeat,
        connection_status=camera.connection_status,
        last_error=camera.last_error,
        current_queue_count=camera.current_queue_count,
        current_vehicles_total=camera.current_vehicles_total,
        waiting_time_seconds=camera.waiting_time_seconds,
        last_frame_timestamp=camera.last_frame_timestamp,
        frame_sampling_rate=camera.frame_sampling_rate,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        stream_url_masked=mask_stream_url(camera.stream_url)
    )


@router.get("/{station_id}/camera", response_model=CameraConfigResponse)
def get_camera_config(
    station_id: int,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """Protected operator endpoint: View camera configuration with masked credentials."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this station's camera configuration."
        )

    camera = db.query(CameraConfig).filter(CameraConfig.station_id == station_id).first()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No camera configured for this station."
        )

    # Check worker for live connection status if active
    worker = live_camera_manager.get_worker(station_id)
    conn_status = worker.connection_status if worker else camera.connection_status
    last_err = worker.last_error if worker else camera.last_error

    return CameraConfigResponse(
        id=camera.id,
        station_id=camera.station_id,
        camera_name=camera.camera_name or f"{station.name} - Cam 1",
        camera_type=camera.camera_type,
        is_active=camera.is_active,
        detection_roi=camera.detection_roi,
        last_heartbeat=camera.last_heartbeat,
        connection_status=conn_status,
        last_error=last_err,
        current_queue_count=camera.current_queue_count,
        current_vehicles_total=camera.current_vehicles_total,
        waiting_time_seconds=camera.waiting_time_seconds,
        last_frame_timestamp=camera.last_frame_timestamp,
        frame_sampling_rate=camera.frame_sampling_rate,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        stream_url_masked=mask_stream_url(camera.stream_url)
    )


@router.post("/{station_id}/camera/connect", response_model=LiveCameraStatusResponse)
def connect_camera(
    station_id: int,
    payload: Optional[CameraConnectRequest] = None,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint: Initiate live camera connection and real-time YOLO tracking.
    Spawns dedicated background worker with frame sampling and Queue ROI isolation.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to control this station's camera."
        )

    camera = station.camera_config
    if not camera or not camera.stream_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No camera stream URL configured for this station. Configure the camera first."
        )

    is_valid, validation_msg = validate_stream_url(camera.stream_url, camera.camera_type)
    if not is_valid:
        camera.connection_status = "ERROR"
        camera.last_error = validation_msg
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation_msg)

    sampling_rate = payload.frame_sampling_rate if payload and payload.frame_sampling_rate else camera.frame_sampling_rate
    cam_name = camera.camera_name or f"{station.name} - Cam 1"

    success, msg = live_camera_manager.start_camera(
        station_id=station_id,
        stream_url=camera.stream_url,
        camera_type=camera.camera_type,
        roi_config=camera.detection_roi,
        frame_sampling_rate=sampling_rate,
        camera_name=cam_name,
    )

    if not success:
        camera.connection_status = "ERROR"
        camera.last_error = msg
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)

    camera.is_active = True
    camera.connection_status = "CONNECTING"
    camera.frame_sampling_rate = sampling_rate
    camera.last_error = None
    db.commit()
    db.refresh(camera)

    return LiveCameraStatusResponse(
        station_id=station_id,
        station_name=station.name,
        camera_name=cam_name,
        camera_type=camera.camera_type,
        connection_status=camera.connection_status,
        is_streaming=True,
        last_error=camera.last_error,
        current_queue_count=camera.current_queue_count,
        current_vehicles_total=camera.current_vehicles_total,
        queue_level="UNAVAILABLE",
        queue_capacity=station.queue_capacity,
        waiting_time_seconds=camera.waiting_time_seconds,
        estimated_queue_wait_minutes=int(math.ceil(camera.waiting_time_seconds / 60)) if camera.waiting_time_seconds is not None else None,
        waiting_time_display=format_queue_wait_display(camera.waiting_time_seconds / 60 if camera.waiting_time_seconds is not None else None),
        waiting_time_status="ESTIMATED" if camera.waiting_time_seconds is not None else "UNAVAILABLE",
        last_frame_timestamp=camera.last_frame_timestamp,
        frame_sampling_rate=camera.frame_sampling_rate,
        measured_fps=None,
        model_name="YOLOv8n (Ultralytics ByteTrack)",
        roi_config=camera.detection_roi,
        measurement_window_seconds=60,
        stream_url_masked=mask_stream_url(camera.stream_url)
    )


@router.post("/{station_id}/camera/disconnect", response_model=LiveCameraStatusResponse)
def disconnect_camera(
    station_id: int,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint: Gracefully stop live stream worker and release video capture resources.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to control this station's camera."
        )

    live_camera_manager.stop_camera(station_id)

    camera = station.camera_config
    if camera:
        camera.is_active = False
        camera.connection_status = "DISCONNECTED"
        camera.last_error = None
        db.commit()
        db.refresh(camera)

    cam_name = (camera.camera_name if camera and camera.camera_name else f"{station.name} - Cam 1")

    return LiveCameraStatusResponse(
        station_id=station_id,
        station_name=station.name,
        camera_name=cam_name,
        camera_type=camera.camera_type if camera else "rtsp",
        connection_status="DISCONNECTED",
        is_streaming=False,
        last_error=None,
        current_queue_count=camera.current_queue_count if camera else None,
        current_vehicles_total=camera.current_vehicles_total if camera else None,
        queue_level="UNAVAILABLE",
        queue_capacity=station.queue_capacity,
        waiting_time_seconds=camera.waiting_time_seconds if camera else None,
        waiting_time_status="UNAVAILABLE",
        last_frame_timestamp=camera.last_frame_timestamp if camera else None,
        frame_sampling_rate=camera.frame_sampling_rate if camera else 5,
        measured_fps=None,
        model_name="YOLOv8n (Ultralytics ByteTrack)",
        roi_config=camera.detection_roi if camera else None,
        measurement_window_seconds=60,
        stream_url_masked=mask_stream_url(camera.stream_url) if camera and camera.stream_url else ""
    )


@router.post("/{station_id}/camera/test", response_model=CameraTestResponse)
def test_camera_stream(
    station_id: int,
    payload: CameraTestRequest,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint: Verify camera reachability and decode a probe frame without starting worker.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to test this station's camera."
        )

    res = live_camera_manager.test_stream_connection(payload.stream_url, payload.camera_type)
    return CameraTestResponse(**res)


@router.get("/{station_id}/camera/live-status", response_model=LiveCameraStatusResponse)
def get_live_camera_status(
    station_id: int,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint: Get real-time telemetry from active worker or database.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this station's live status."
        )

    camera = station.camera_config
    worker = live_camera_manager.get_worker(station_id)

    if worker:
        conn_status = worker.connection_status
        is_streaming = worker.is_running and conn_status == "CONNECTED"
        queue_count = worker.current_queue_count
        vehicles_total = worker.current_vehicles_total
        waiting_time = worker.waiting_time_seconds
        last_error = worker.last_error
        last_frame_ts = worker.last_frame_time
        sampling_rate = worker.frame_sampling_rate
        roi_cfg = worker.roi_config_raw
        cam_type = worker.camera_type
        cam_name = getattr(worker, "camera_name", (camera.camera_name if camera and camera.camera_name else f"{station.name} - Cam 1"))
        masked_url = mask_stream_url(worker.stream_url)
        active_tids = worker.active_all_track_ids
        active_q_tids = worker.active_queue_track_ids
        class_bd = worker.class_breakdown
        frame_no = worker.frame_counter
        model_classes = worker.supported_classes
        tractor_det = worker.tractor_detected
        supports_tractor = worker.model_supports_tractor
        cum_q_count = len(worker.cumulative_seen_roi_ids)
        model_disp = worker.model_name
    elif camera:
        conn_status = camera.connection_status
        is_streaming = camera.is_active and conn_status == "CONNECTED"
        queue_count = camera.current_queue_count
        vehicles_total = camera.current_vehicles_total
        waiting_time = camera.waiting_time_seconds
        last_error = camera.last_error
        last_frame_ts = camera.last_frame_timestamp
        sampling_rate = camera.frame_sampling_rate
        roi_cfg = camera.detection_roi
        cam_type = camera.camera_type
        cam_name = camera.camera_name or f"{station.name} - Cam 1"
        masked_url = mask_stream_url(camera.stream_url)
        active_tids = []
        active_q_tids = []
        class_bd = {}
        frame_no = None
        model_classes = ["car", "motorcycle", "bus", "truck"]
        tractor_det = False
        supports_tractor = False
        cum_q_count = None
        model_disp = "YOLOv8n (Standard COCO)"
    else:
        conn_status = "DISCONNECTED"
        is_streaming = False
        queue_count = None
        vehicles_total = None
        waiting_time = None
        last_error = "No camera configured."
        last_frame_ts = None
        sampling_rate = 5
        roi_cfg = None
        cam_type = "rtsp"
        cam_name = f"{station.name} - Cam 1"
        masked_url = ""
        active_tids = []
        active_q_tids = []
        class_bd = {}
        frame_no = None
        model_classes = ["car", "motorcycle", "bus", "truck"]
        tractor_det = False
        supports_tractor = False
        cum_q_count = None
        model_disp = "YOLOv8n (Standard COCO)"

    def compute_queue_level(count: Optional[int], cap: Optional[int]) -> str:
        if count is None:
            return "UNAVAILABLE"
        c = max(1, cap or 20)
        ratio = count / c
        if ratio <= 0.35:
            return "LOW"
        elif ratio <= 0.70:
            return "MODERATE"
        elif ratio < 1.0:
            return "HIGH"
        else:
            return "CRITICAL"

    return LiveCameraStatusResponse(
        station_id=station_id,
        station_name=station.name,
        camera_name=cam_name,
        camera_type=cam_type,
        connection_status=conn_status,
        is_streaming=is_streaming,
        last_error=last_error,
        current_queue_count=queue_count,
        current_vehicles_total=vehicles_total,
        queue_level=compute_queue_level(queue_count, station.queue_capacity),
        queue_capacity=station.queue_capacity,
        waiting_time_seconds=waiting_time,
        estimated_queue_wait_minutes=worker.estimated_queue_wait_minutes if (worker and worker.estimated_queue_wait_minutes is not None) else (int(math.ceil(waiting_time / 60)) if waiting_time is not None else None),
        waiting_time_display=format_queue_wait_display(worker.estimated_queue_wait_minutes if (worker and worker.estimated_queue_wait_minutes is not None) else (waiting_time / 60 if waiting_time is not None else None)),
        waiting_time_status="ESTIMATED" if waiting_time is not None else "UNAVAILABLE",
        last_frame_timestamp=last_frame_ts,
        frame_sampling_rate=sampling_rate,
        measured_fps=worker.measured_fps if worker else None,
        model_name=model_disp,
        roi_config=roi_cfg,
        measurement_window_seconds=60,
        stream_url_masked=masked_url,
        active_track_ids=active_tids,
        active_queue_track_ids=active_q_tids,
        class_breakdown=class_bd,
        frame_number=frame_no,
        model_classes=model_classes,
        tractor_detected=tractor_det,
        model_supports_tractor=supports_tractor,
        cumulative_queue_vehicles_count=cum_q_count,
    )


def generate_mjpeg_stream(station_id: int):
    """Yield MJPEG multipart chunks of actual YOLO-processed frames."""
    consecutive_misses = 0
    while True:
        worker = live_camera_manager.get_worker(station_id)
        if not worker or not worker.is_running:
            time.sleep(0.4)
            consecutive_misses += 1
            if consecutive_misses > 25:  # 10s wait for worker reconnect
                break
            continue

        consecutive_misses = 0
        frame_bytes = None
        with worker.lock:
            frame_bytes = worker.last_frame_bytes

        if frame_bytes is not None:
            try:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            except GeneratorExit:
                break
            except Exception:
                break
        time.sleep(0.06)  # ~16 FPS delivery


@router.get("/{station_id}/camera/live-feed")
def get_live_camera_feed(
    station_id: int,
    db: Session = Depends(get_db)
):
    """
    Stream real processed video with YOLO overlays (MJPEG multipart stream).
    Displays actual vehicle bounding boxes, Track IDs, Queue ROI outline, and live counter banner.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    worker = live_camera_manager.get_worker(station_id)
    if not worker or not worker.is_running:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Live camera stream is not running for this station. Connect the camera first."
        )

    return StreamingResponse(
        generate_mjpeg_stream(station_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/{station_id}/camera/telemetry-stream")
def get_camera_telemetry_stream(
    station_id: int,
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) endpoint: Pushes real-time vehicle counts, queue occupancy,
    tracking IDs, and detection metadata every 1000ms.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    def event_stream():
        while True:
            worker = live_camera_manager.get_worker(station_id)
            if worker:
                snap = worker.get_telemetry_snapshot()
            else:
                snap = {
                    "station_id": station_id,
                    "connection_status": "DISCONNECTED",
                    "current_queue_count": None,
                    "current_vehicles_total": None,
                    "measured_fps": 0.0,
                    "model_name": "YOLO",
                    "active_track_ids": [],
                    "active_queue_track_ids": [],
                    "class_breakdown": {},
                }
            payload = json.dumps(snap, default=str)
            yield f"data: {payload}\n\n"
            time.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )


@router.get("/{station_id}/camera/live-snapshot")
def get_live_camera_snapshot(station_id: int, db: Session = Depends(get_db)):
    """Retrieve single latest processed JPEG frame with YOLO overlays."""
    frame_bytes = live_camera_manager.get_latest_frame(station_id)
    if not frame_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active live frame available.")
    return Response(content=frame_bytes, media_type="image/jpeg")


@router.get("/{station_id}/queue-history", response_model=List[LiveQueueSnapshotResponse])
def get_station_queue_history(
    station_id: int,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Public / Operator endpoint: Retrieve recent real live queue snapshots stored in database.
    Shows actual measured vehicle counts over time.
    """
    snapshots = (
        db.query(LiveQueueSnapshot)
        .filter(LiveQueueSnapshot.station_id == station_id)
        .order_by(LiveQueueSnapshot.measured_at.desc())
        .limit(limit)
        .all()
    )
    return snapshots
