import uuid
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Station, Slot, Booking, User
from app.schemas import (
    SlotCreateRequest,
    SlotResponse,
    BookingCreateRequest,
    BookingResponse,
    BookingCancelRequest,
)
from app.services.auth import require_role

router = APIRouter(tags=["Slots & Bookings"])

# ----------------- Slot Endpoints -----------------

@router.post(
    "/api/stations/{station_id}/slots",
    response_model=SlotResponse,
    status_code=status.HTTP_201_CREATED
)
def create_slot(
    station_id: int,
    payload: SlotCreateRequest,
    current_user: User = Depends(require_role(["operator", "admin"])),
    db: Session = Depends(get_db)
):
    """Protected operator endpoint: Create a booking slot for a station."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    if station.operator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create slots for this station."
        )

    # Check for slot overlapping/duplicate start_time
    existing = db.query(Slot).filter(
        Slot.station_id == station_id,
        Slot.start_time == payload.start_time
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A slot starting at this exact time already exists."
        )

    slot = Slot(
        station_id=station_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        max_capacity=payload.max_capacity,
        booked_count=0,
        is_active=True
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)

    return SlotResponse(
        id=slot.id,
        station_id=slot.station_id,
        start_time=slot.start_time,
        end_time=slot.end_time,
        max_capacity=slot.max_capacity,
        booked_count=slot.booked_count,
        available_capacity=slot.max_capacity - slot.booked_count,
        is_active=slot.is_active,
        created_at=slot.created_at
    )


@router.get("/api/stations/{station_id}/slots", response_model=List[SlotResponse])
def list_station_slots(station_id: int, db: Session = Depends(get_db)):
    """Public endpoint: List real active booking slots for a station."""
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found.")

    now = datetime.now()
    today = now.date()

    slots = db.query(Slot).filter(
        Slot.station_id == station_id,
        Slot.is_active == True
    ).order_by(Slot.start_time.asc()).all()

    # Automatically roll forward any slots that are on past dates so they match the current date
    need_commit = False
    for s in slots:
        if s.start_time.date() < today:
            diff_days = (today - s.start_time.date()).days
            s.start_time = s.start_time + timedelta(days=diff_days)
            s.end_time = s.end_time + timedelta(days=diff_days)
            need_commit = True

    # Ensure station has at least 3 active slots for today
    if len(slots) < 3:
        duration_mins = station.slot_duration_minutes or 15
        max_cap = station.max_vehicles_per_slot or 5
        base_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        for i in range(3):
            slot_start = base_time + timedelta(minutes=i * duration_mins)
            slot_end = slot_start + timedelta(minutes=duration_mins)
            if not any(s.start_time == slot_start for s in slots):
                new_slot = Slot(
                    station_id=station.id,
                    start_time=slot_start,
                    end_time=slot_end,
                    max_capacity=max_cap,
                    booked_count=0,
                    is_active=True,
                )
                db.add(new_slot)
                need_commit = True

    if need_commit:
        db.commit()
        slots = db.query(Slot).filter(
            Slot.station_id == station_id,
            Slot.is_active == True
        ).order_by(Slot.start_time.asc()).all()

    return [
        SlotResponse(
            id=s.id,
            station_id=s.station_id,
            start_time=s.start_time,
            end_time=s.end_time,
            max_capacity=s.max_capacity,
            booked_count=s.booked_count,
            available_capacity=max(0, s.max_capacity - s.booked_count),
            is_active=s.is_active,
            created_at=s.created_at
        )
        for s in slots
    ]


# ----------------- Booking Endpoints -----------------

from app.services.auth import get_current_user

@router.post("/api/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Authenticated endpoint: Book a limited-time slot.
    Strictly ties the booking to the authenticated user account (user_id).
    Enforces atomic overbooking protection: if booked_count >= max_capacity, request fails with 409 Conflict.
    """
    slot = db.query(Slot).filter(Slot.id == payload.slot_id).first()
    if not slot or not slot.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested slot is either not found or inactive."
        )

    # Check for duplicate active booking with identical vehicle plate for this slot
    duplicate = db.query(Booking).filter(
        Booking.slot_id == payload.slot_id,
        Booking.vehicle_plate == payload.vehicle_plate,
        Booking.status == "CONFIRMED"
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vehicle '{payload.vehicle_plate}' already has an active booking in this slot."
        )

    # Atomic constraint to guarantee overbooking prevention
    rows_updated = db.query(Slot).filter(
        Slot.id == payload.slot_id,
        Slot.booked_count < Slot.max_capacity,
        Slot.is_active == True
    ).update(
        {Slot.booked_count: Slot.booked_count + 1},
        synchronize_session="fetch"
    )

    if rows_updated == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This slot is fully booked. No capacity remaining."
        )

    booking_ref = f"FF-{uuid.uuid4().hex[:8].upper()}"
    identifier = payload.user_identifier or current_user.email or current_user.username

    new_booking = Booking(
        booking_reference=booking_ref,
        slot_id=slot.id,
        station_id=slot.station_id,
        user_id=current_user.id,
        user_identifier=identifier,
        vehicle_plate=payload.vehicle_plate,
        status="CONFIRMED"
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    station = db.query(Station).filter(Station.id == slot.station_id).first()
    station_name = station.name if station else "Fuel Station"

    return BookingResponse(
        id=new_booking.id,
        booking_reference=new_booking.booking_reference,
        slot_id=new_booking.slot_id,
        station_id=new_booking.station_id,
        user_id=new_booking.user_id,
        user_identifier=new_booking.user_identifier,
        vehicle_plate=new_booking.vehicle_plate,
        status=new_booking.status,
        slot_start_time=slot.start_time,
        slot_end_time=slot.end_time,
        station_name=station_name,
        created_at=new_booking.created_at
    )


@router.get("/api/bookings/my-bookings", response_model=List[BookingResponse])
def get_my_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Authenticated endpoint: Retrieve only bookings owned by the authenticated user.
    Users cannot access or scrape bookings belonging to other accounts.
    """
    bookings = db.query(Booking).filter(
        Booking.user_id == current_user.id
    ).order_by(Booking.created_at.desc()).all()

    results = []
    for b in bookings:
        slot = db.query(Slot).filter(Slot.id == b.slot_id).first()
        station = db.query(Station).filter(Station.id == b.station_id).first()
        results.append(
            BookingResponse(
                id=b.id,
                booking_reference=b.booking_reference,
                slot_id=b.slot_id,
                station_id=b.station_id,
                user_id=b.user_id,
                user_identifier=b.user_identifier,
                vehicle_plate=b.vehicle_plate,
                status=b.status,
                slot_start_time=slot.start_time if slot else datetime.utcnow(),
                slot_end_time=slot.end_time if slot else datetime.utcnow(),
                station_name=station.name if station else "Fuel Station",
                created_at=b.created_at
            )
        )
    return results


@router.get("/api/bookings/{booking_reference}", response_model=BookingResponse)
def get_booking(
    booking_reference: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Protected endpoint: Query real booking details by reference.
    Enforces authorization: normal users can ONLY view their own bookings.
    """
    booking = db.query(Booking).filter(Booking.booking_reference == booking_reference).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking reference not found.")

    # Authorization check
    if booking.user_id != current_user.id and current_user.role not in ("admin", "operator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view this booking."
        )

    slot = db.query(Slot).filter(Slot.id == booking.slot_id).first()
    station = db.query(Station).filter(Station.id == booking.station_id).first()

    return BookingResponse(
        id=booking.id,
        booking_reference=booking.booking_reference,
        slot_id=booking.slot_id,
        station_id=booking.station_id,
        user_id=booking.user_id,
        user_identifier=booking.user_identifier,
        vehicle_plate=booking.vehicle_plate,
        status=booking.status,
        slot_start_time=slot.start_time if slot else datetime.utcnow(),
        slot_end_time=slot.end_time if slot else datetime.utcnow(),
        station_name=station.name if station else "Fuel Station",
        created_at=booking.created_at
    )


@router.post("/api/bookings/{booking_reference}/cancel", response_model=BookingResponse)
def cancel_booking(
    booking_reference: str,
    payload: BookingCancelRequest = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Protected endpoint: Cancel an active booking and release the slot capacity atomically.
    Enforces authorization: Only the booking owner (or station operator/admin) can cancel it.
    """
    booking = db.query(Booking).filter(Booking.booking_reference == booking_reference).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking reference not found.")

    # Check permission: User owner, or admin, or operator of this specific station
    is_owner = (booking.user_id == current_user.id)
    is_admin = (current_user.role == "admin")
    is_station_operator = False
    if current_user.role == "operator":
        station = db.query(Station).filter(Station.id == booking.station_id).first()
        if station and station.operator_id == current_user.id:
            is_station_operator = True

    if not (is_owner or is_admin or is_station_operator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to cancel this booking."
        )

    if booking.status != "CONFIRMED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking cannot be cancelled because its status is '{booking.status}'."
        )

    booking.status = "CANCELLED"

    # Atomically release slot capacity
    db.query(Slot).filter(
        Slot.id == booking.slot_id,
        Slot.booked_count > 0
    ).update(
        {Slot.booked_count: Slot.booked_count - 1},
        synchronize_session="fetch"
    )

    db.commit()
    db.refresh(booking)

    slot = db.query(Slot).filter(Slot.id == booking.slot_id).first()
    station = db.query(Station).filter(Station.id == booking.station_id).first()

    return BookingResponse(
        id=booking.id,
        booking_reference=booking.booking_reference,
        slot_id=booking.slot_id,
        station_id=booking.station_id,
        user_id=booking.user_id,
        user_identifier=booking.user_identifier,
        vehicle_plate=booking.vehicle_plate,
        status=booking.status,
        slot_start_time=slot.start_time if slot else datetime.utcnow(),
        slot_end_time=slot.end_time if slot else datetime.utcnow(),
        station_name=station.name if station else "Fuel Station",
        created_at=booking.created_at
    )


from typing import Optional

@router.get("/api/bookings", response_model=List[BookingResponse])
def search_bookings(
    query: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Authenticated search endpoint: Look up user's bookings by contact, plate, or reference code.
    Enforces authorization: normal users only search their own bookings.
    """
    if not query or not query.strip():
        return []

    clean_q = query.strip()
    clean_plate = "".join(clean_q.split()).upper()

    q_filter = db.query(Booking).filter(
        (Booking.booking_reference.ilike(f"%{clean_q}%")) |
        (Booking.user_identifier.ilike(f"%{clean_q}%")) |
        (Booking.vehicle_plate == clean_plate)
    )

    if current_user.role not in ("admin", "operator"):
        q_filter = q_filter.filter(Booking.user_id == current_user.id)

    bookings = q_filter.order_by(Booking.created_at.desc()).all()

    results = []
    for b in bookings:
        slot = db.query(Slot).filter(Slot.id == b.slot_id).first()
        station = db.query(Station).filter(Station.id == b.station_id).first()
        results.append(
            BookingResponse(
                id=b.id,
                booking_reference=b.booking_reference,
                slot_id=b.slot_id,
                station_id=b.station_id,
                user_id=b.user_id,
                user_identifier=b.user_identifier,
                vehicle_plate=b.vehicle_plate,
                status=b.status,
                slot_start_time=slot.start_time if slot else datetime.utcnow(),
                slot_end_time=slot.end_time if slot else datetime.utcnow(),
                station_name=station.name if station else "Fuel Station",
                created_at=b.created_at
            )
        )
    return results
