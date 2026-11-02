# FuelFlow

Real fuel-station queue management and recommendation platform.

## Architecture
- **Frontend:** React + TypeScript (Vite)
- **Backend:** Python FastAPI
- **Database:** Persistent SQLite (`backend/fuelflow.db`) with Foreign Key enforcement (`PRAGMA foreign_keys=ON`)
- **Authentication & Security:** bcrypt password hashing + JWT token Bearer authentication + RBAC
- **Concurrency & Integrity:** Atomic overbooking prevention at database query level
- **Vision Model:** Real YOLO (Ultralytics) for vehicle detection & tracking (to be wired in subsequent phases)
- **Design System:** Strict 3-color palette:
  - White: `#FFFFFF` (Primary background)
  - Charcoal: `#303030` (Text, navigation, primary buttons)
  - Light Grey: `#E8E8E8` (Cards, borders, secondary surfaces)

---

## Prerequisites
- Node.js (`v18+` or `v24+`)
- Python (`v3.10+` or `v3.14+`)

---

## Setup & Running Guide (Step-by-Step)

### 1. Backend Setup
From the root folder:
```powershell
cd backend

# Activate virtual environment on Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Install requirements:
pip install -r requirements.txt

# Run all automated tests (16 tests covering health, overbooking, RBAC, and ownership):
pytest tests/test_phase2.py tests/test_security.py -v

# Bootstrap Initial Administrator:
python -m app.bootstrap_admin --username admin --email admin@fuelflow.local --password "AdminMasterKey123!"

# Run FastAPI development server:
uvicorn app.main:app --reload --port 8000
```
API endpoints and interactive documentation:
- Health Check: `http://127.0.0.1:8000/api/health`
- Interactive OpenAPI Docs: `http://127.0.0.1:8000/docs`

### 2. Frontend Setup
From the root folder in a second terminal:
```powershell
cd frontend
npm install
npm run dev
```
The application will be accessible at `http://localhost:5173`.

---

## Authentication & Security Architecture
1. **User Sign In vs. Operator Sign In:**
   - Public customer registration (`/api/auth/user/register`) strictly sets `role="user"`. It cannot create operators or admins.
   - Operator login (`/api/auth/operator/login`) strictly rejects non-operator accounts with `HTTP 403 Forbidden`.
   - The root administrator is securely provisioned via `python -m app.bootstrap_admin` and can provision operator accounts via `/api/auth/admin/create-operator`.
2. **Server-Side Role Protection:**
   - Protected endpoints require valid cryptographically signed JWT Bearer tokens.
   - Unauthenticated requests receive `HTTP 401 Unauthorized`.
   - Unauthorized requests (e.g., customer attempting to configure stations or cameras) receive `HTTP 403 Forbidden`.
3. **Station & Booking Ownership Isolation:**
   - Operators can modify and configure cameras/slots only for stations they own.
   - Customer reservations are bound to the authenticated `user_id`. Users can view and cancel only their own bookings.
   - Hiding buttons is not relied upon; all permissions are verified in the database on every request.
4. **Access Denied Page:**
   - An authenticated customer attempting to navigate to operator administration is immediately presented with a clean **403 Forbidden Access Denied** screen in the strict 3-color design.
   - `users`: Operators and Admins with bcrypt password hashes.
   - `stations`: Fuel stations with physical capacity, pump count, and slot configuration.
   - `camera_configs`: Secure camera credentials masked in API responses.
   - `slots`: Time-bound windows with maximum vehicle limits.
   - `bookings`: Slot reservations with atomic anti-overbooking enforcement.
2. **Role-Based Access Control:**
   - Operator endpoints require valid JWT Bearer tokens.
   - Unauthenticated requests are rejected with `401 Unauthorized`.
3. **Atomic Overbooking Prevention:**
   - Slots track `booked_count` vs `max_capacity`.
   - Simultaneous or excess bookings beyond capacity fail with `409 Conflict`.
   - Booking cancellations atomically restore slot availability.
4. **Data Integrity & User-Side Interface:**
   - Navigation: **Find Stations**, **My Bookings**, and **Help**.
   - Zero hardcoded or fake stations. An empty database renders "No station data available".
   - Browser geolocation computes genuine distance (Haversine formula on real coordinates).
   - Live queue status truthfully states "Live data unavailable" when no real camera feed is connected.
   - My Bookings allows looking up real confirmed reservations and canceling slots.
   - Staff operator tools are discreetly preserved and separated from the public user flow.
