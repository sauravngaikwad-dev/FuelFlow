from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

# ----------------- User and Operator Authentication Schemas -----------------

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: str = Field(..., min_length=5, max_length=120, description="Valid email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password with minimum 8 characters")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip()
        if not clean.isalnum() and "_" not in clean:
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return clean


class UserLoginRequest(BaseModel):
    username: str = Field(..., description="Username or registered email")
    password: str = Field(..., description="User password")


class OperatorLoginRequest(BaseModel):
    username: str = Field(..., description="Operator or Administrator username or email")
    password: str = Field(..., description="Password")


class AdminCreateOperatorRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Operator username")
    email: str = Field(..., min_length=5, max_length=120, description="Operator email")
    password: str = Field(..., min_length=8, max_length=100, description="Temporary password")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip()
        if not clean.isalnum() and "_" not in clean:
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return clean


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user_id: int
    username: str
    role: str


class UserProfileResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


# ----------------- Station Schemas -----------------

class StationCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    address: str = Field(..., min_length=5, max_length=255)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    queue_capacity: int = Field(20, ge=1, le=200, description="Maximum vehicle capacity of queue area")
    pump_count: int = Field(4, ge=1, le=50, description="Active fuel dispensers count")
    slot_duration_minutes: int = Field(15, ge=5, le=120, description="Length of each booking window in minutes")
    booking_window_hours: int = Field(24, ge=1, le=168, description="How many hours ahead users can book")
    max_vehicles_per_slot: int = Field(4, ge=1, le=50, description="Maximum vehicle capacity per slot")


class StationUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    address: Optional[str] = Field(None, min_length=5, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    queue_capacity: Optional[int] = Field(None, ge=1, le=200)
    pump_count: Optional[int] = Field(None, ge=1, le=50)
    slot_duration_minutes: Optional[int] = Field(None, ge=5, le=120)
    booking_window_hours: Optional[int] = Field(None, ge=1, le=168)
    max_vehicles_per_slot: Optional[int] = Field(None, ge=1, le=50)


class StationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    latitude: float
    longitude: float
    queue_capacity: int
    pump_count: int
    slot_duration_minutes: int
    booking_window_hours: int
    max_vehicles_per_slot: int
    operator_id: int
    created_at: datetime
    updated_at: datetime
    has_camera_configured: bool = False
    distance_km: Optional[float] = None
    fuel_types_verified: List[str] = Field(default_factory=list)


# ----------------- Camera Configuration Schemas -----------------

class CameraConfigUpsertRequest(BaseModel):
    camera_name: Optional[str] = Field(None, max_length=100, description="Display name for CCTV camera")
    camera_type: str = Field(..., description="Camera protocol: 'rtsp', 'http', 'webcam', or 'file'")
    stream_url: str = Field(..., min_length=1, max_length=500, description="Stream URL, device index, or test video file")
    is_active: bool = Field(True, description="Enable or disable live ingest")
    detection_roi: Optional[str] = Field(None, max_length=500, description="ROI coordinates in JSON format")
    frame_sampling_rate: Optional[int] = Field(5, ge=1, le=30, description="Process every Nth frame")

    @field_validator("camera_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v_clean = v.lower().strip()
        if v_clean not in ("rtsp", "http", "webcam", "file", "sample"):
            raise ValueError("Supported camera types are 'rtsp', 'http', 'webcam', or 'file'")
        return v_clean


class CameraConfigResponse(BaseModel):
    id: int
    station_id: int
    camera_name: Optional[str] = "Main Forecourt Camera"
    camera_type: str
    is_active: bool
    detection_roi: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    connection_status: str = "DISCONNECTED"
    last_error: Optional[str] = None
    current_queue_count: Optional[int] = None
    current_vehicles_total: Optional[int] = None
    waiting_time_seconds: Optional[float] = None
    last_frame_timestamp: Optional[datetime] = None
    frame_sampling_rate: int = 5
    created_at: datetime
    updated_at: datetime
    # Stream URL is securely masked so sensitive credentials are never leaked
    stream_url_masked: str


class CameraConnectRequest(BaseModel):
    frame_sampling_rate: Optional[int] = Field(5, ge=1, le=30, description="Process every Nth frame to control CPU/GPU load")


class CameraTestRequest(BaseModel):
    camera_type: str = Field(..., description="Camera protocol: 'rtsp', 'http', 'webcam', or 'file'")
    stream_url: str = Field(..., min_length=1, max_length=500, description="Stream URL, device index, or video file path")


class CameraTestResponse(BaseModel):
    success: bool
    message: str
    camera_type: str
    resolution: Optional[str] = None
    fps: Optional[float] = None
    error_detail: Optional[str] = None


class LiveCameraStatusResponse(BaseModel):
    station_id: int
    station_name: Optional[str] = None
    camera_name: Optional[str] = "Main Forecourt Camera"
    camera_type: str
    connection_status: str  # DISCONNECTED, CONNECTING, CONNECTED, ERROR, RECONNECTING
    is_streaming: bool
    last_error: Optional[str] = None
    current_queue_count: Optional[int] = None
    current_vehicles_total: Optional[int] = None
    queue_level: str = "UNAVAILABLE"  # LOW, MODERATE, HIGH, CRITICAL, UNAVAILABLE
    queue_capacity: Optional[int] = None
    waiting_time_seconds: Optional[float] = None
    estimated_queue_wait_minutes: Optional[int] = None
    waiting_time_display: Optional[str] = None
    waiting_time_status: str = "UNAVAILABLE"
    last_frame_timestamp: Optional[datetime] = None
    frame_sampling_rate: int = 5
    measured_fps: Optional[float] = None
    model_name: str = "YOLOv8n (Ultralytics ByteTrack)"
    roi_config: Optional[str] = None
    measurement_window_seconds: int = 60
    stream_url_masked: str
    # Real-time dynamic tracking telemetry
    active_track_ids: List[int] = Field(default_factory=list)
    active_queue_track_ids: List[int] = Field(default_factory=list)
    class_breakdown: Dict[str, int] = Field(default_factory=dict)
    frame_number: Optional[int] = None
    model_classes: List[str] = Field(default_factory=list)
    tractor_detected: bool = False
    model_supports_tractor: bool = False
    cumulative_queue_vehicles_count: Optional[int] = None


class LiveQueueSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    queue_count: int
    total_vehicles_detected: int
    waiting_time_seconds: Optional[float] = None
    measured_at: datetime


# ----------------- Slot Schemas -----------------

class SlotCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    max_capacity: int = Field(..., ge=1, le=100)

    @field_validator("end_time")
    @classmethod
    def validate_times(cls, end_time: datetime, values) -> datetime:
        start_time = values.data.get("start_time")
        if start_time and end_time <= start_time:
            raise ValueError("end_time must be strictly after start_time")
        return end_time


class SlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    start_time: datetime
    end_time: datetime
    max_capacity: int
    booked_count: int
    available_capacity: int
    is_active: bool
    created_at: datetime


# ----------------- Booking Schemas -----------------

class BookingCreateRequest(BaseModel):
    slot_id: int
    vehicle_plate: str = Field(..., min_length=2, max_length=30, description="Vehicle registration plate")
    user_identifier: Optional[str] = Field(None, min_length=3, max_length=100, description="Optional contact override")

    @field_validator("vehicle_plate")
    @classmethod
    def clean_plate(cls, v: str) -> str:
        clean = "".join(v.split()).upper()
        if len(clean) < 2:
            raise ValueError("Vehicle plate is too short")
        return clean


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_reference: str
    slot_id: int
    station_id: int
    user_id: int
    user_identifier: str
    vehicle_plate: str
    status: str
    slot_start_time: datetime
    slot_end_time: datetime
    station_name: str
    created_at: datetime


class BookingCancelRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


# ----------------- Video Analysis Schemas (Phase 3) -----------------

class VideoAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    station_id: int
    operator_id: int
    filename: str
    file_size_bytes: int
    status: str  # PENDING, PROCESSING, COMPLETED, FAILED, INSUFFICIENT_DATA
    error_message: Optional[str] = None
    roi_config: Optional[str] = None
    fps: float
    total_frames: int
    processed_frames: int
    duration_seconds: float
    model_name: str
    vehicle_classes_detected: dict
    total_vehicles_detected: int
    peak_queue_count: int
    average_queue_count: float
    average_waiting_time_seconds: Optional[float] = None
    estimated_queue_wait_minutes: Optional[int] = None
    waiting_time_display: Optional[str] = None
    analytics_timeline: list
    has_processed_video: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    analysis_type: str = "HISTORICAL ANALYSIS"
    disclaimer: str = "HISTORICAL ANALYSIS: Derived strictly from recorded CCTV footage. Not a current live queue reading."
