from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index, Text
)
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="operator", nullable=False)  # "operator", "admin"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    stations = relationship("Station", back_populates="operator", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")
    video_analyses = relationship("VideoAnalysisRecord", back_populates="operator", cascade="all, delete-orphan")


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    queue_capacity = Column(Integer, nullable=False, default=20)  # Maximum physical queue capacity
    pump_count = Column(Integer, nullable=False, default=4)       # Number of active fuel dispensers
    slot_duration_minutes = Column(Integer, nullable=False, default=15)  # Duration of each booking slot
    booking_window_hours = Column(Integer, nullable=False, default=24)   # Advance booking horizon
    max_vehicles_per_slot = Column(Integer, nullable=False, default=4)   # Max bookings allowed per slot
    operator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    operator = relationship("User", back_populates="stations")
    camera_config = relationship("CameraConfig", back_populates="station", uselist=False, cascade="all, delete-orphan")
    slots = relationship("Slot", back_populates="station", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="station", cascade="all, delete-orphan")
    video_analyses = relationship("VideoAnalysisRecord", back_populates="station", cascade="all, delete-orphan")
    live_snapshots = relationship("LiveQueueSnapshot", back_populates="station", cascade="all, delete-orphan")


class CameraConfig(Base):
    __tablename__ = "camera_configs"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), unique=True, nullable=False)
    camera_name = Column(String(100), default="Main Forecourt Camera", nullable=True)
    camera_type = Column(String(30), nullable=False, default="rtsp")  # "rtsp", "http", "webcam"
    stream_url = Column(String(500), nullable=False)                  # Protected credential string / stream path
    is_active = Column(Boolean, default=False, nullable=False)
    detection_roi = Column(String(500), nullable=True)                # Optional JSON region of interest
    last_heartbeat = Column(DateTime, nullable=True)

    # Phase 4: Live CCTV stream state & analytics
    connection_status = Column(String(50), default="DISCONNECTED", nullable=False)  # DISCONNECTED, CONNECTING, CONNECTED, ERROR, RECONNECTING
    last_error = Column(String(500), nullable=True)
    current_queue_count = Column(Integer, nullable=True)
    current_vehicles_total = Column(Integer, nullable=True)
    waiting_time_seconds = Column(Float, nullable=True)
    last_frame_timestamp = Column(DateTime, nullable=True)
    frame_sampling_rate = Column(Integer, default=5, nullable=False)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationship
    station = relationship("Station", back_populates="camera_config")


class Slot(Base):
    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    max_capacity = Column(Integer, nullable=False)  # Slot cap (e.g. 4 vehicles)
    booked_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationship
    station = relationship("Station", back_populates="slots")
    bookings = relationship("Booking", back_populates="slot", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("station_id", "start_time", name="uq_station_slot_start"),
        Index("ix_slot_station_time", "station_id", "start_time", "end_time"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_reference = Column(String(36), unique=True, index=True, nullable=False)  # Unique reference
    slot_id = Column(Integer, ForeignKey("slots.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_identifier = Column(String(100), nullable=False, index=True)  # Contact phone, email, or username
    vehicle_plate = Column(String(30), nullable=False)
    status = Column(String(20), default="CONFIRMED", nullable=False)   # "CONFIRMED", "CANCELLED", "COMPLETED"
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    slot = relationship("Slot", back_populates="bookings")
    station = relationship("Station", back_populates="bookings")
    user = relationship("User", back_populates="bookings")

    __table_args__ = (
        Index("ix_booking_slot_plate", "slot_id", "vehicle_plate", "status"),
        Index("ix_booking_user_status", "user_id", "status"),
    )


class VideoAnalysisRecord(Base):
    """
    Historical CCTV analysis record strictly representing processed recorded video footage.
    Never represents live queue status.
    """
    __tablename__ = "video_analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True)
    operator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    video_path = Column(String(500), nullable=False)
    processed_video_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=False)
    status = Column(String(30), default="PENDING", nullable=False)  # PENDING, PROCESSING, COMPLETED, FAILED, INSUFFICIENT_DATA
    error_message = Column(Text, nullable=True)

    # ROI Configuration (JSON formatted string: {"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.8})
    roi_config = Column(Text, nullable=True)

    # Video metrics
    fps = Column(Float, default=0.0)
    total_frames = Column(Integer, default=0)
    processed_frames = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)

    # YOLO Inference historical results
    model_name = Column(String(50), default="yolov8n.pt")
    vehicle_classes_detected = Column(Text, default="{}")  # JSON: {"car": 12, "truck": 3, "bus": 1, "motorcycle": 2}
    total_vehicles_detected = Column(Integer, default=0)
    peak_queue_count = Column(Integer, default=0)
    average_queue_count = Column(Float, default=0.0)
    average_waiting_time_seconds = Column(Float, nullable=True)  # In seconds, or None if insufficient tracking
    analytics_timeline = Column(Text, default="[]")  # JSON list of historical second-by-second readings

    created_at = Column(DateTime, default=utc_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    station = relationship("Station", back_populates="video_analyses")
    operator = relationship("User", back_populates="video_analyses")

    __table_args__ = (
        Index("ix_analysis_station_status", "station_id", "status"),
    )


class LiveQueueSnapshot(Base):
    """
    Phase 4: Periodic persisted snapshot of real live CCTV queue measurements.
    Distinguished from recorded-video analysis records.
    """
    __tablename__ = "live_queue_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True)
    queue_count = Column(Integer, nullable=False)
    total_vehicles_detected = Column(Integer, nullable=False)
    waiting_time_seconds = Column(Float, nullable=True)
    measured_at = Column(DateTime, default=utc_now, nullable=False, index=True)

    # Relationship
    station = relationship("Station", back_populates="live_snapshots")

    __table_args__ = (
        Index("ix_live_snapshot_station_time", "station_id", "measured_at"),
    )

