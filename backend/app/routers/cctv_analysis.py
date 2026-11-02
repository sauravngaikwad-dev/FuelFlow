import os
import uuid
import json
import math
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    Request,
    Response,
    Query,
    status
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Station, VideoAnalysisRecord, User
from app.schemas import VideoAnalysisResponse
from app.services.auth import require_role, decode_access_token
from app.config import format_queue_wait_display
from app.services.video_analyzer import (
    RAW_DIR,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    process_video_analysis
)

router = APIRouter(prefix="/api/stations/{station_id}/video-analyses", tags=["CCTV Video Analysis"])

def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters from uploaded filenames."""
    keepcharacters = (' ', '.', '_', '-')
    clean = "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()
    return clean or "recording.mp4"


def format_analysis_response(rec: VideoAnalysisRecord) -> VideoAnalysisResponse:
    """Format a database VideoAnalysisRecord into a clean API response."""
    classes = {}
    try:
        if rec.vehicle_classes_detected:
            classes = json.loads(rec.vehicle_classes_detected)
    except Exception:
        pass

    timeline = []
    try:
        if rec.analytics_timeline:
            timeline = json.loads(rec.analytics_timeline)
    except Exception:
        pass

    has_video = bool(rec.processed_video_path and os.path.exists(rec.processed_video_path))

    return VideoAnalysisResponse(
        id=rec.id,
        station_id=rec.station_id,
        operator_id=rec.operator_id,
        filename=rec.filename,
        file_size_bytes=rec.file_size_bytes,
        status=rec.status,
        error_message=rec.error_message,
        roi_config=rec.roi_config,
        fps=rec.fps,
        total_frames=rec.total_frames,
        processed_frames=rec.processed_frames,
        duration_seconds=rec.duration_seconds,
        model_name=rec.model_name,
        vehicle_classes_detected=classes,
        total_vehicles_detected=rec.total_vehicles_detected,
        peak_queue_count=rec.peak_queue_count,
        average_queue_count=rec.average_queue_count,
        average_waiting_time_seconds=rec.average_waiting_time_seconds,
        estimated_queue_wait_minutes=int(math.ceil(rec.average_waiting_time_seconds / 60)) if rec.average_waiting_time_seconds is not None else None,
        waiting_time_display=format_queue_wait_display(rec.average_waiting_time_seconds / 60) if rec.average_waiting_time_seconds is not None else "Unavailable",
        analytics_timeline=timeline,
        has_processed_video=has_video,
        created_at=rec.created_at,
        completed_at=rec.completed_at,
        analysis_type="HISTORICAL ANALYSIS",
        disclaimer="HISTORICAL ANALYSIS: Derived strictly from recorded CCTV footage. Not a current live queue reading."
    )


@router.post("", response_model=VideoAnalysisResponse, status_code=status.HTTP_201_CREATED)
async def upload_cctv_recording(
    station_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    roi_config: Optional[str] = Form(None),
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint:
    Upload a genuine recorded CCTV video for offline YOLO vehicle detection,
    queue estimation in configured ROI, and historical analytics generation.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    # Authorization: Operator must own this station unless admin
    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to manage CCTV analysis for this station."
        )

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed video formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    clean_name = sanitize_filename(file.filename)
    stored_name = f"{uuid.uuid4().hex[:12]}_{clean_name}"
    raw_path = os.path.join(RAW_DIR, stored_name)

    # Safely stream and write chunks to disk while enforcing max file size
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    with open(raw_path, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_FILE_SIZE_BYTES:
                f.close()
                if os.path.exists(raw_path):
                    os.remove(raw_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Video file exceeds maximum allowable size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                )
            f.write(chunk)

    if bytes_written == 0:
        if os.path.exists(raw_path):
            os.remove(raw_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    # Persist pending record in database
    analysis_record = VideoAnalysisRecord(
        station_id=station_id,
        operator_id=current_user.id,
        filename=clean_name,
        stored_filename=stored_name,
        video_path=raw_path,
        file_size_bytes=bytes_written,
        status="PENDING",
        roi_config=roi_config,
        model_name="yolov8n.pt"
    )
    db.add(analysis_record)
    db.commit()
    db.refresh(analysis_record)

    # Dispatch real YOLO background worker
    background_tasks.add_task(process_video_analysis, analysis_record.id)

    return format_analysis_response(analysis_record)


@router.get("", response_model=List[VideoAnalysisResponse])
def list_station_analyses(
    station_id: int,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint:
    List historical CCTV video analysis reports for this fuel station.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access CCTV analysis for this station."
        )

    records = db.query(VideoAnalysisRecord).filter(
        VideoAnalysisRecord.station_id == station_id
    ).order_by(VideoAnalysisRecord.created_at.desc()).all()

    return [format_analysis_response(r) for r in records]


@router.get("/{analysis_id}", response_model=VideoAnalysisResponse)
def get_analysis_detail(
    station_id: int,
    analysis_id: int,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint:
    Get detailed historical analysis results, peak queue, average wait times, and timeline.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access CCTV analysis for this station."
        )

    record = db.query(VideoAnalysisRecord).filter(
        VideoAnalysisRecord.id == analysis_id,
        VideoAnalysisRecord.station_id == station_id
    ).first()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found.")

    return format_analysis_response(record)


@router.post("/{analysis_id}/reprocess", response_model=VideoAnalysisResponse)
def reprocess_analysis(
    station_id: int,
    analysis_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint:
    Re-trigger YOLO detection and video rendering with latest color palette and scaling.
    """
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access CCTV analysis for this station."
        )

    record = db.query(VideoAnalysisRecord).filter(
        VideoAnalysisRecord.id == analysis_id,
        VideoAnalysisRecord.station_id == station_id
    ).first()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found.")

    if not record.video_path or not os.path.exists(record.video_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original raw video file is missing on disk.")

    record.status = "PENDING"
    record.error_message = None
    db.commit()
    db.refresh(record)

    background_tasks.add_task(process_video_analysis, record.id)
    return format_analysis_response(record)


def get_auth_user_for_video(
    request: Request,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticate user for video streaming via either:
    1. Authorization: Bearer <token> header (standard API & test clients)
    2. ?token=<token> query parameter (HTML5 <video src="..."> tags)
    """
    auth_header = request.headers.get("Authorization")
    raw_token = None
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Authorization header or ?token= query parameter."
        )

    payload = decode_access_token(raw_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated."
        )

    if user.role not in ["operator", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Operator or admin role required."
        )

    return user


def stream_file_with_range_support(path: str, request: Request, filename: str) -> Response:
    """
    Stream media file with full HTTP Range request support (HTTP 206 Partial Content).
    Enables seeking, scrubbing, pausing, and smooth progressive loading in HTML5 <video>.
    If no Range header is sent, returns standard 200 OK.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed video file not found or incomplete."
        )

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    if not range_header:
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            **no_cache_headers,
        }
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=filename,
            headers=headers
        )

    try:
        range_unit, range_spec = range_header.strip().split("=")
        if range_unit.strip().lower() != "bytes":
            return FileResponse(
                path,
                media_type="video/mp4",
                filename=filename,
                headers={"Accept-Ranges": "bytes", **no_cache_headers}
            )

        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0].strip() else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1].strip() else file_size - 1
        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}", **no_cache_headers}
            )

        chunk_size = (end - start) + 1

        def file_iterator():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    chunk = f.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
            **no_cache_headers,
        }
        return StreamingResponse(
            file_iterator(),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers
        )
    except Exception:
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=filename,
            headers={"Accept-Ranges": "bytes", **no_cache_headers}
        )


@router.get("/{analysis_id}/video")
def stream_processed_video(
    station_id: int,
    analysis_id: int,
    request: Request,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Protected operator endpoint:
    Stream the genuine processed video featuring bounding boxes, tracking tags, and ROI overlay.
    Supports Range requests for seeking and pause/resume playback.
    Accepts authentication via Authorization header or ?token= query parameter.
    """
    current_user = get_auth_user_for_video(request, token, db)

    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access CCTV analysis for this station."
        )

    record = db.query(VideoAnalysisRecord).filter(
        VideoAnalysisRecord.id == analysis_id,
        VideoAnalysisRecord.station_id == station_id
    ).first()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found.")

    # Serve processed video if completed, otherwise raw video
    target_path = record.processed_video_path if (record.processed_video_path and os.path.exists(record.processed_video_path)) else record.video_path

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found on server.")

    return stream_file_with_range_support(target_path, request, f"processed_{record.filename}")
