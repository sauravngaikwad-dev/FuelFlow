# FuelFlow Architecture Plan

## 1. System Overview
FuelFlow is an end-to-end fuel-station queue management and recommendation platform.
It connects drivers with real-time station capacity and queue states, while providing operators with a computer-vision analytics pipeline powered by YOLO.

## 2. Core Modules

### A. User Portal
- **Station Discovery:** View real nearby stations registered in the database.
- **Queue Comparison:** Compare verified live vehicle queue counts and estimated wait times.
- **Recommendations:** Ranking algorithm based on distance, verified wait time, and dispenser capacity.
- **Slot Booking:** Real-time reservations within station-configured slot durations and caps.

### B. Operator Dashboard
- **Authentication & RBAC:** Secure token-based access for station managers.
- **Station Management:** Configure queue capacity, pump count, slot duration, and operating hours.
- **Vision Pipeline:**
  - **Live Camera Feed:** RTSP / HTTP stream / direct webcam ingest for real-time queue counting.
  - **Recorded CCTV Video:** Upload offline footage for historical analytics (strictly marked as historical).
- **Queue Analytics:** Real YOLO vehicle detection and tracker metrics (cars, buses, trucks, motorcycles).

## 3. Strict Rules & Data Integrity
1. **Zero Fake Data:** No hardcoded numbers, fake stations, synthetic charts, or simulated inference results. If a station has no camera or no data, "No station data available" or "Live camera disconnected" will be rendered.
2. **Design System:** Strictly three colors:
   - White (`#FFFFFF`)
   - Charcoal (`#303030`)
   - Light Grey (`#E8E8E8`)
3. **Security:** No camera credentials or API secrets exposed in frontend code.

## 4. Phased Implementation Roadmap
- **Phase 1 (Current):** Project skeleton, strict design token foundation, initial layout, API entrypoint, documentation.
- **Phase 2:** Database schema (SQLAlchemy + SQLite), Alembic/Migrations, Operator Auth (JWT + Passlib), Station CRUD.
- **Phase 3:** YOLO detection & tracking engine (Ultralytics) for recorded CCTV video analysis.
- **Phase 4:** Live CCTV stream processing (OpenCV + background worker) & real-time queue state updates.
- **Phase 5:** User module (Station discovery, queue status, recommendation algorithm, slot booking engine).
- **Phase 6:** End-to-end integration, operator dashboard analytics, testing and verification.
