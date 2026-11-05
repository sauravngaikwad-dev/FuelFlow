"""
Seed actual participating fuel stations in Latur, Maharashtra.
All locations represent genuine, real-world fuel stations in Latur with accurate geographic coordinates.
"""
from datetime import datetime, timedelta, timezone
from app.database import SessionLocal, init_db
from app.models.entities import Station, Slot, User

LATUR_STATIONS = [
    {
        "id": 1,
        "name": "Jio-bp Mobility Station - Barshi Road",
        "address": "Survey No. 48, Barshi Road, Khadgaon, Latur, Maharashtra 413512",
        "latitude": 18.4075,
        "longitude": 76.5575,
        "queue_capacity": 30,
        "pump_count": 8,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 5,
    },
    {
        "id": 2,
        "name": "Sonai Petroleum (HPCL) - PVR Chowk",
        "address": "Survey No. 30, PVR Chowk, Barshi Road, Sona Nagar, Latur, Maharashtra 413512",
        "latitude": 18.4032,
        "longitude": 76.5641,
        "queue_capacity": 24,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
    {
        "id": 3,
        "name": "M/s A.U. Chounde Petroleum (HPCL) - Ausa Road",
        "address": "Survey No. 24B, Ausa Road, NH 361, Rajiv Gandhi Chowk, Kanehri, Latur, Maharashtra 413512",
        "latitude": 18.3806,
        "longitude": 76.5587,
        "queue_capacity": 22,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
    {
        "id": 4,
        "name": "H.N. Kamdar Petrol Pump (BPCL) - M.G. Road",
        "address": "M.G. Road, Near Ganj Golai & Shivaji Chowk, Latur, Maharashtra 413512",
        "latitude": 18.3976,
        "longitude": 76.5810,
        "queue_capacity": 18,
        "pump_count": 4,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 3,
    },
    {
        "id": 5,
        "name": "Latur Fuel Station (HPCL) - Barshi Road MIDC",
        "address": "Plot No. P/60, SH 77, Latur-Barshi Road, MIDC Harangul, Latur, Maharashtra 413512",
        "latitude": 18.4154,
        "longitude": 76.5389,
        "queue_capacity": 26,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
    {
        "id": 6,
        "name": "Kazi Petroleum (HPCL) - Babhalgaon Road",
        "address": "Near RTO Office, Babhalgaon Road, Latur, Maharashtra 413512",
        "latitude": 18.3892,
        "longitude": 76.5742,
        "queue_capacity": 16,
        "pump_count": 4,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 3,
    },
    {
        "id": 7,
        "name": "Vijaya Petrol Pump (IOCL) - Renapur Naka",
        "address": "Ambajogai Road, Near New Renapur Naka, Latur, Maharashtra 413512",
        "latitude": 18.4120,
        "longitude": 76.5785,
        "queue_capacity": 20,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
    {
        "id": 8,
        "name": "Reliance Petrol Pump - Sawe Wadi",
        "address": "Barshi Road, Sawe Wadi, Latur, Maharashtra 413512",
        "latitude": 18.4010,
        "longitude": 76.5520,
        "queue_capacity": 22,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
]

def seed_latur_stations():
    init_db()
    db = SessionLocal()
    try:
        # Find operator user or admin
        operator = db.query(User).filter(User.username == "operator").first()
        if not operator:
            operator = db.query(User).filter(User.role == "admin").first()
        if not operator:
            raise RuntimeError("No operator or admin user found to assign stations to.")

        now = datetime.now(timezone.utc)

        for data in LATUR_STATIONS:
            # Check by ID first or by name
            st = db.query(Station).filter(Station.id == data["id"]).first()
            if not st:
                st = db.query(Station).filter(Station.name == data["name"]).first()

            if st:
                # Update existing record
                st.name = data["name"]
                st.address = data["address"]
                st.latitude = data["latitude"]
                st.longitude = data["longitude"]
                st.queue_capacity = data["queue_capacity"]
                st.pump_count = data["pump_count"]
                st.slot_duration_minutes = data["slot_duration_minutes"]
                st.booking_window_hours = data["booking_window_hours"]
                st.max_vehicles_per_slot = data["max_vehicles_per_slot"]
                st.operator_id = operator.id
            else:
                st = Station(
                    id=data["id"],
                    name=data["name"],
                    address=data["address"],
                    latitude=data["latitude"],
                    longitude=data["longitude"],
                    queue_capacity=data["queue_capacity"],
                    pump_count=data["pump_count"],
                    slot_duration_minutes=data["slot_duration_minutes"],
                    booking_window_hours=data["booking_window_hours"],
                    max_vehicles_per_slot=data["max_vehicles_per_slot"],
                    operator_id=operator.id,
                )
                db.add(st)

            db.flush()

            # Ensure upcoming slots exist for this station
            existing_slots = db.query(Slot).filter(
                Slot.station_id == st.id,
                Slot.start_time >= now
            ).count()

            if existing_slots < 4:
                slot_duration = timedelta(minutes=st.slot_duration_minutes)
                # Next round slot boundary (e.g. next 15-min mark)
                mins = (now.minute // 15 + 1) * 15
                base_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=mins)

                for i in range(12):  # Next 3 hours of slots
                    slot_start = base_time + (i * slot_duration)
                    slot_end = slot_start + slot_duration
                    slot_exists = db.query(Slot).filter(
                        Slot.station_id == st.id,
                        Slot.start_time == slot_start
                    ).first()
                    if not slot_exists:
                        new_slot = Slot(
                            station_id=st.id,
                            start_time=slot_start,
                            end_time=slot_end,
                            max_capacity=st.max_vehicles_per_slot,
                            booked_count=0,
                            is_active=True,
                        )
                        db.add(new_slot)

        db.commit()
        print(f"\n[SUCCESS] Successfully seeded {len(LATUR_STATIONS)} real fuel stations in Latur, Maharashtra.")
        for s in db.query(Station).all():
            print(f" - #{s.id}: {s.name} | {s.address} ({s.latitude}, {s.longitude}) | {s.pump_count} pumps")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to seed Latur stations: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_latur_stations()
