# FuelFlow Database Architecture & Schema Strategy

## 1. Overview & Storage Engine
FuelFlow uses SQLAlchemy 2.x with persistent SQLite storage for the initial local MVP.
- **Database File:** `backend/fuelflow.db` (persisted on disk, excluded from git).
- **Driver / Engine:** SQLite with Foreign Key enforcement (`PRAGMA foreign_keys=ON`) enabled on each connection.
- **Multi-threading:** Configured with `connect_args={"check_same_thread": False}` to handle concurrent FastAPI requests smoothly.

---

## 2. Entity Schemas & Relationships

### `users` (Operators & Administrators)
- **Fields:** `id`, `username`, `email`, `hashed_password` (bcrypt), `role` (`operator`/`admin`), `is_active`, `created_at`.
- **Integrity:** Unique indexes on `username` and `email`.

### `stations` (Fuel Stations)
- **Fields:** `id`, `name`, `address`, `latitude`, `longitude`, `queue_capacity`, `pump_count`, `slot_duration_minutes`, `booking_window_hours`, `max_vehicles_per_slot`, `operator_id`, `created_at`, `updated_at`.
- **Integrity:** Foreign key referencing `users.id` with `CASCADE` delete.

### `camera_configs` (CCTV / IP Camera Feeds)
- **Fields:** `id`, `station_id`, `camera_type` (`rtsp`/`http`/`webcam`), `stream_url` (protected), `is_active`, `detection_roi`, `last_heartbeat`, `created_at`, `updated_at`.
- **Security:** Credential strings in `stream_url` are never exposed in public APIs; masked in responses.

### `slots` (Time-Bound Booking Windows)
- **Fields:** `id`, `station_id`, `start_time`, `end_time`, `max_capacity`, `booked_count`, `is_active`, `created_at`.
- **Integrity:** Unique composite constraint on `(station_id, start_time)` and index on `(station_id, start_time, end_time)`.

### `bookings` (Vehicle Slot Reservations)
- **Fields:** `id`, `booking_reference` (e.g. `FF-XXXXXXXX`), `slot_id`, `station_id`, `user_identifier`, `vehicle_plate`, `status` (`CONFIRMED`/`CANCELLED`/`COMPLETED`), `created_at`, `updated_at`.
- **Overbooking Prevention:** Atomic database condition:
  ```python
  rows_updated = db.query(Slot).filter(
      Slot.id == slot_id,
      Slot.booked_count < Slot.max_capacity,
      Slot.is_active == True
  ).update({Slot.booked_count: Slot.booked_count + 1})
  if rows_updated == 0:
      raise HTTPException(status_code=409, detail="Slot is fully booked.")
  ```

---

## 3. Schema Update & Migration Strategy

### Phase 2 Automatic Initialization
When the FastAPI application starts, `init_db()` is invoked during the lifespan startup event:
```python
Base.metadata.create_all(bind=engine)
```
This safely creates any missing tables and indexes without dropping existing data.

### Development Schema Reset (If Needed)
To perform a complete clean reset during local development:
```powershell
Remove-Item backend\fuelflow.db -ErrorAction SilentlyContinue
# Restarting the backend will re-create pristine schemas
```

### Production Migration Strategy (Alembic)
For production environments with existing production data:
1. Initialize Alembic: `alembic init alembic`
2. Point `alembic.ini` to `env.DATABASE_URL`.
3. Configure `target_metadata = Base.metadata` in `alembic/env.py`.
4. Run migrations with `alembic revision --autogenerate -m "description"` and `alembic upgrade head`.
