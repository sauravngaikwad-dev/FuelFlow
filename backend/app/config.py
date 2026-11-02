import os
import math
from pathlib import Path
from typing import Dict, Any, Union
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "FuelFlow API"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "127.0.0.1")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/fuelflow.db")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "temporary_insecure_dev_key_replace_in_env")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    UPLOAD_DIR: Path = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
    YOLO_MODEL_PATH: Path = BASE_DIR / os.getenv("YOLO_MODEL_PATH", "models/yolov8n.pt")

    # Configurable Vehicle Service Times in Minutes for Estimated Queue Wait
    # - Bike: 2–3 minutes; use 3 minutes for calculation.
    # - Car: 4–5 minutes; use 5 minutes for calculation.
    # - Tractor: 10 minutes.
    # - Bus: 10 minutes.
    # - Truck: 10 minutes.
    SERVICE_TIME_BIKE_MINUTES: int = int(os.getenv("SERVICE_TIME_BIKE_MINUTES", "3"))
    SERVICE_TIME_CAR_MINUTES: int = int(os.getenv("SERVICE_TIME_CAR_MINUTES", "5"))
    SERVICE_TIME_TRACTOR_MINUTES: int = int(os.getenv("SERVICE_TIME_TRACTOR_MINUTES", "10"))
    SERVICE_TIME_BUS_MINUTES: int = int(os.getenv("SERVICE_TIME_BUS_MINUTES", "10"))
    SERVICE_TIME_TRUCK_MINUTES: int = int(os.getenv("SERVICE_TIME_TRUCK_MINUTES", "10"))
    SERVICE_TIME_DEFAULT_MINUTES: int = int(os.getenv("SERVICE_TIME_DEFAULT_MINUTES", "5"))

settings = Settings()

def _get_configured_service_time(env_var_name: str, default_setting_val: Union[int, float]) -> float:
    """Helper to retrieve configurable vehicle service time in minutes."""
    env_val = os.getenv(env_var_name)
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    return float(default_setting_val)


def get_vehicle_service_time_minutes(cls_name: str) -> float:
    """
    Return service time in minutes for a given vehicle class name.
    Configurable via environment variables or settings:
    - Bike: 2–3 minutes; default 3 minutes.
    - Car: 4–5 minutes; default 5 minutes.
    - Tractor: default 10 minutes.
    - Bus: default 10 minutes.
    - Truck: default 10 minutes.
    """
    norm = cls_name.strip().lower()
    if norm in ("bike", "motorcycle", "bicycle", "two_wheeler", "scooter"):
        return _get_configured_service_time("SERVICE_TIME_BIKE_MINUTES", settings.SERVICE_TIME_BIKE_MINUTES)
    elif norm in ("car", "auto", "three_wheeler", "sedan", "suv"):
        return _get_configured_service_time("SERVICE_TIME_CAR_MINUTES", settings.SERVICE_TIME_CAR_MINUTES)
    elif norm in ("tractor",):
        return _get_configured_service_time("SERVICE_TIME_TRACTOR_MINUTES", settings.SERVICE_TIME_TRACTOR_MINUTES)
    elif norm in ("bus",):
        return _get_configured_service_time("SERVICE_TIME_BUS_MINUTES", settings.SERVICE_TIME_BUS_MINUTES)
    elif norm in ("truck", "lcv", "heavy_vehicle", "van"):
        return _get_configured_service_time("SERVICE_TIME_TRUCK_MINUTES", settings.SERVICE_TIME_TRUCK_MINUTES)
    return _get_configured_service_time("SERVICE_TIME_DEFAULT_MINUTES", settings.SERVICE_TIME_DEFAULT_MINUTES)


def calculate_estimated_queue_wait_minutes(waiting_vehicles: Union[Dict[str, int], list]) -> int:
    """
    Formula: Estimated queue wait = sum of (number of waiting vehicles * service time per vehicle).
    Round the final estimated waiting time up to the next whole minute if necessary (math.ceil).
    Never returns decimal minutes (e.g. returns 6 or 29, never 5.9 or 28.5).
    """
    total_minutes = 0.0
    if isinstance(waiting_vehicles, dict):
        for cls_name, count in waiting_vehicles.items():
            if count and count > 0:
                st = get_vehicle_service_time_minutes(cls_name)
                total_minutes += count * st
    elif isinstance(waiting_vehicles, (list, tuple)):
        for item in waiting_vehicles:
            if isinstance(item, str):
                st = get_vehicle_service_time_minutes(item)
                total_minutes += st
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                cls_name, count = item
                st = get_vehicle_service_time_minutes(cls_name)
                total_minutes += count * st

    if total_minutes <= 0.0:
        return 0
    return int(math.ceil(total_minutes))

def format_queue_wait_display(wait_minutes: Union[int, float, None]) -> str:
    """Format waiting time as whole minutes string (e.g. '6 min' or '29 min', never decimal)."""
    if wait_minutes is None:
        return "Unavailable"
    whole_min = int(math.ceil(wait_minutes))
    return f"{whole_min} min"
