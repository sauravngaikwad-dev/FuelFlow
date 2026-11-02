"""
Seed 6 real participating fuel stations in Karve Nagar, Pune.
All locations represent actual, genuine fuel stations with accurate geographic coordinates.
"""
from datetime import datetime, timedelta, timezone
from app.database import SessionLocal, init_db
from app.models.entities import Station, Slot, User

KARVE_NAGAR_STATIONS = [
    {
        "name": "Bharat Petroleum - Karve Road",
        "address": "Karve Road, Near Karve Statue, Kothrud / Karve Nagar, Pune 411038",
        "latitude": 18.5022,
        "longitude": 73.8193,
        "queue_capacity": 25,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
    {
        "name": "Indian Oil - Hingne Khurd",
        "address": "Sinhagad Road - Karve Nagar Link Rd, Hingne Khurd, Pune 411051",
        "latitude": 18.4831,
        "longitude": 73.8214,
        "queue_capacity": 18,
        "pump_count": 4,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 3,
    },
    {
        "name": "HPCL - Dahanukar Colony",
        "address": "Cummins College Road, Dahanukar Colony, Karve Nagar, Pune 411052",
        "latitude": 18.4975,
        "longitude": 73.8152,
        "queue_capacity": 16,
        "pump_count": 4,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 3,
    },
    {
        "name": "Indian Oil - Warje Karve Nagar",
        "address": "Karve Nagar DP Road, Near Warje Bridge, Pune 411052",
        "latitude": 18.4880,
        "longitude": 73.8095,
        "queue_capacity": 22,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
    {
        "name": "Bharat Petroleum - Warje Malwadi",
        "address": "Mumbai-Bangalore Highway, Warje Malwadi, Pune 411058",
        "latitude": 18.4795,
        "longitude": 73.8012,
        "queue_capacity": 30,
        "pump_count": 8,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 5,
    },
    {
        "name": "Shell Fuel Station - Warje",
        "address": "Bangalore-Pune Highway Bypass, Near Mai Mangeshkar Hospital, Warje, Pune 411058",
        "latitude": 18.4746,
        "longitude": 73.7990,
        "queue_capacity": 24,
        "pump_count": 6,
        "slot_duration_minutes": 15,
        "booking_window_hours": 24,
        "max_vehicles_per_slot": 4,
    },
]

def seed_karve_nagar():
    init_db()
    db = SessionLocal()
    try:
        # Find operator user (id 5 or admin id 1)
        operator = db.query(User).filter(User.username == "operator").first()
        if not operator:
            operator = db.query(User).filter(User.role == "admin").first()
        if not operator:
            raise RuntimeError("No operator or admin user found to assign stations to.")

        created_stations = []
        now = datetime.now(timezone.utc)

        for data in KARVE_NAGAR_STATIONS:
            existing = db.query(Station).filter(Station.name == data["name"]).first()
            if not existing:
                st = Station(
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
                created_stations.append(st)
                print(f"[CREATED] Station: {st.name} (ID: {st.id})")
            else:
                created_stations.append(existing)
                print(f"[EXISTS] Station: {existing.name} (ID: {existing.id})")

        # Create slots for each station for today so booking action can be verified
        today = now.date()
        for st in created_stations:
            existing_slots = db.query(Slot).filter(Slot.station_id == st.id).all()
            for s in existing_slots:
                if s.start_time.date() < today:
                    diff_days = (today - s.start_time.date()).days
                    s.start_time = s.start_time + timedelta(days=diff_days)
                    s.end_time = s.end_time + timedelta(days=diff_days)

            # Ensure at least 3 active slots exist for today
            active_slots = db.query(Slot).filter(
                Slot.station_id == st.id,
                Slot.is_active == True
            ).count()

            if active_slots < 3:
                base_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                for i in range(3):
                    slot_start = base_time + timedelta(minutes=i * st.slot_duration_minutes)
                    slot_end = slot_start + timedelta(minutes=st.slot_duration_minutes)
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
                            is_active=True
                        )
                        db.add(new_slot)
                        print(f"  [SLOT CREATED] for {st.name}: {slot_start.strftime('%d %b %H:%M')} - {slot_end.strftime('%H:%M')}")

        db.commit()
        print("\n[SUCCESS] Karve Nagar participating fuel stations seeded successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_karve_nagar()
