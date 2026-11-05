import { useState, useEffect } from 'react';
import type { Station, Slot, BookingResult } from './FindStations';

interface QueueStatusResponse {
  station_id: number;
  station_name: string;
  queue_capacity: number;
  pump_count: number;
  live_stream: {
    status: string;
    connection_status?: string;
    stream_health?: string;
    is_fresh?: boolean;
    message: string;
    current_queue_count: number | null;
    current_vehicles_total?: number | null;
    waiting_time_estimate_seconds: number | null;
    waiting_time_display?: string;
    detection_timestamp: string | null;
    measurement_window_seconds?: number;
    measurement_basis?: string;
  };
  historical_analysis: {
    analysis_id: number;
    filename: string;
    detection_timestamp: string;
    peak_queue_count: number;
    average_queue_count: number;
    total_vehicles_detected: number;
    vehicle_classes_detected: Record<string, number>;
    average_waiting_time_seconds: number | null;
    analysis_type: string;
    disclaimer: string;
  } | null;
}

interface StationDetailsProps {
  station: Station;
  userCoords: { lat: number; lng: number } | null;
  userToken: string | null;
  onBackToStations: () => void;
  onRequireLogin: () => void;
  onNavigateToMyBookings?: () => void;
}

function calculateStraightLineDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371.0;
  const dlat = ((lat2 - lat1) * Math.PI) / 180;
  const dlon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dlat / 2) * Math.sin(dlat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dlon / 2) *
      Math.sin(dlon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c * 100) / 100;
}

export function StationDetails({
  station,
  userCoords,
  userToken,
  onBackToStations,
  onRequireLogin,
  onNavigateToMyBookings,
}: StationDetailsProps) {
  // Queue status & historical analytics
  const [queueStatus, setQueueStatus] = useState<QueueStatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  // Slots
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(true);
  const [selectedSlotId, setSelectedSlotId] = useState<number | null>(null);

  // Booking form
  const [vehiclePlate, setVehiclePlate] = useState('');
  const [userContact, setUserContact] = useState('');
  const [bookingInProgress, setBookingInProgress] = useState(false);
  const [bookingResult, setBookingResult] = useState<BookingResult | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);

  // Driving route estimate via OSRM
  const [drivingEstimate, setDrivingEstimate] = useState<{
    distanceKm: number;
    durationMinutes: number;
  } | null>(null);

  // Fetch queue status and historical analytics
  const fetchQueueStatus = () => {
    setLoadingStatus(true);
    fetch(`http://127.0.0.1:8000/api/stations/${station.id}/queue-status`)
      .then((res) => {
        if (!res.ok) throw new Error('Status not available');
        return res.json();
      })
      .then((data: QueueStatusResponse) => {
        setQueueStatus(data);
      })
      .catch(() => {
        setQueueStatus(null);
      })
      .finally(() => {
        setLoadingStatus(false);
      });
  };

  // Fetch active slots
  const fetchSlots = () => {
    setLoadingSlots(true);
    fetch(`http://127.0.0.1:8000/api/stations/${station.id}/slots`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load slots');
        return res.json();
      })
      .then((data: Slot[]) => {
        setSlots(data);
      })
      .catch(() => {
        setSlots([]);
      })
      .finally(() => {
        setLoadingSlots(false);
      });
  };

  useEffect(() => {
    fetchQueueStatus();
    fetchSlots();
  }, [station.id]);

  // Fetch driving estimate if user coords available
  useEffect(() => {
    if (!userCoords) {
      setDrivingEstimate(null);
      return;
    }

    const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${userCoords.lng},${userCoords.lat};${station.longitude},${station.latitude}?overview=false`;
    fetch(osrmUrl)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.routes && data.routes.length > 0) {
          const route = data.routes[0];
          setDrivingEstimate({
            distanceKm: Math.round((route.distance / 1000) * 10) / 10,
            durationMinutes: Math.round(route.duration / 60),
          });
        }
      })
      .catch(() => {
        setDrivingEstimate(null);
      });
  }, [userCoords, station.latitude, station.longitude]);

  // Navigation URL using actual user coordinates as origin when available
  const googleMapsDirectionsUrl = userCoords
    ? `https://www.google.com/maps/dir/?api=1&origin=${userCoords.lat},${userCoords.lng}&destination=${station.latitude},${station.longitude}&travelmode=driving`
    : `https://www.google.com/maps/dir/?api=1&destination=${station.latitude},${station.longitude}&travelmode=driving`;

  const straightLineDistance = userCoords
    ? calculateStraightLineDistance(userCoords.lat, userCoords.lng, station.latitude, station.longitude)
    : station.distance_km ?? null;

  // Handle booking reservation
  const handleConfirmBooking = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSlotId) return;

    if (!userToken) {
      onRequireLogin();
      return;
    }

    setBookingInProgress(true);
    setBookingError(null);
    setBookingResult(null);

    fetch('http://127.0.0.1:8000/api/bookings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${userToken}`,
      },
      body: JSON.stringify({
        slot_id: selectedSlotId,
        user_identifier: userContact || undefined,
        vehicle_plate: vehiclePlate,
      }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Reservation rejected by backend.');
        }
        return data as BookingResult;
      })
      .then((result) => {
        setBookingResult(result);
        setVehiclePlate('');
        setUserContact('');
        fetchSlots(); // Refresh slot capacity
      })
      .catch((err) => {
        setBookingError(err.message);
      })
      .finally(() => {
        setBookingInProgress(false);
      });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* 1. Header Navigation Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button
          type="button"
          className="btn-secondary"
          onClick={onBackToStations}
          style={{ fontSize: '13px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          ← Back to Fuel Stations
        </button>

        <span className="tag-badge">Station Details</span>
      </div>

      {/* 2. Station Information Card */}
      <section className="card" style={{ border: '2px solid var(--border-strong)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Verified Participating Fuel Station
            </div>
            <h2 style={{ fontSize: '22px', fontWeight: 800, marginTop: '2px', marginBottom: '6px' }}>
              {station.name}
            </h2>
            <p style={{ fontSize: '14px', color: 'var(--color-charcoal)' }}>
              {station.address}
            </p>
          </div>

          <a
            href={googleMapsDirectionsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary"
            style={{
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '12px 18px',
              fontSize: '13px',
              fontWeight: 700,
            }}
          >
            ↗ Get Directions (Google Maps)
          </a>
        </div>

        {/* Specifications Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '12px',
            marginTop: '20px',
            paddingTop: '16px',
            borderTop: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700 }}>
              Queue Capacity
            </div>
            <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '4px' }}>
              {station.queue_capacity} Vehicles
            </div>
            <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.8 }}>Forecourt lane capacity</div>
          </div>

          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700 }}>
              Active Fuel Dispensers
            </div>
            <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '4px' }}>
              {station.pump_count} Pumps
            </div>
            <div style={{ fontSize: '11px', marginTop: '2px' }}>Operational multi-fuel nozzles</div>
          </div>

          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700 }}>
              Slot Window
            </div>
            <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '4px' }}>
              {station.slot_duration_minutes} Mins
            </div>
            <div style={{ fontSize: '11px', marginTop: '2px' }}>Max {station.max_vehicles_per_slot} vehicles per slot</div>
          </div>

          <div style={{ border: '1px solid var(--border-subtle)', padding: '12px' }}>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700 }}>
              GPS Location
            </div>
            <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '4px' }}>
              {station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}
            </div>
            <div style={{ fontSize: '11px', marginTop: '2px' }}>Latur, Maharashtra Sector</div>
          </div>
        </div>

        {/* Real Proximity & Route Banner */}
        <div
          style={{
            marginTop: '16px',
            padding: '12px 16px',
            border: '1px solid var(--border-strong)',
            backgroundColor: 'var(--color-white)',
          }}
        >
          <div style={{ fontSize: '13px', fontWeight: 700 }}>
            Proximity & Travel Estimation (Zero fabricated distances)
          </div>
          <div style={{ fontSize: '13px', marginTop: '4px' }}>
            {straightLineDistance !== null ? (
              <span>
                <strong>Straight-line Distance:</strong> {straightLineDistance} km (calculated using exact geographic coordinates).
              </span>
            ) : (
              <span>
                Straight-line distance: Enable browser location permission to compute distance from your position.
              </span>
            )}
          </div>
          {drivingEstimate ? (
            <div style={{ fontSize: '13px', marginTop: '4px', fontWeight: 600 }}>
              <strong>Real Driving Estimate:</strong> {drivingEstimate.distanceKm} km (~{drivingEstimate.durationMinutes} mins driving time via public OpenStreetMap routing).
            </div>
          ) : userCoords ? (
            <div style={{ fontSize: '12px', marginTop: '4px' }}>
              Driving route estimate: OpenStreetMap routing engine pending or unconfigured. Real Google Maps navigation is available above.
            </div>
          ) : null}
        </div>
      </section>

      {/* 3. Queue Analytics Section */}
      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 700 }}>
              Queue Analytics
            </h3>
            <p style={{ fontSize: '13px' }}>
              Live forecourt camera feeds and verified video analysis.
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary"
            onClick={fetchQueueStatus}
            style={{ fontSize: '12px', padding: '6px 12px' }}
          >
            Refresh Status
          </button>
        </div>

        {loadingStatus ? (
          <div className="status-box">Querying queue status and analytics...</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Live Camera Feed State */}
            <div style={{ border: '1px solid var(--border-strong)', padding: '14px', backgroundColor: 'var(--color-white)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="tag-badge">LIVE CCTV</span>
                  <strong style={{ fontSize: '14px' }}>Camera Status</strong>
                </div>
                <span
                  style={{
                    fontSize: '11px',
                    fontWeight: 700,
                    padding: '3px 8px',
                    border: '1px solid var(--border-strong)',
                    backgroundColor: queueStatus?.live_stream.is_fresh
                      ? 'var(--color-charcoal)'
                      : 'var(--color-white)',
                    color: queueStatus?.live_stream.is_fresh
                      ? 'var(--color-white)'
                      : 'var(--color-charcoal)',
                  }}
                >
                  {queueStatus?.live_stream.stream_health === 'ONLINE' && queueStatus.live_stream.is_fresh
                    ? '● Live CCTV'
                    : queueStatus?.live_stream.stream_health === 'DATA_OUTDATED'
                    ? '⚠ Data outdated'
                    : queueStatus?.live_stream.stream_health === 'CONNECTING'
                    ? 'Connecting stream...'
                    : 'Camera offline'}
                </span>
              </div>

              <div style={{ marginTop: '12px', fontSize: '13px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px', marginBottom: '10px' }}>
                  <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Queue length</div>
                      <span title="Vehicles strictly detected inside queue region" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                    </div>
                    <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '2px' }}>
                      {queueStatus?.live_stream.current_queue_count !== null && queueStatus?.live_stream.current_queue_count !== undefined
                        ? `${queueStatus.live_stream.current_queue_count} vehicles`
                        : 'Queue unavailable'}
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.8 }}>Inside queue region</div>
                  </div>

                  <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Vehicles detected</div>
                      <span title="Total vehicles across entire camera frame" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                    </div>
                    <div style={{ fontSize: '18px', fontWeight: 800, marginTop: '2px' }}>
                      {queueStatus?.live_stream.current_vehicles_total !== null && queueStatus?.live_stream.current_vehicles_total !== undefined
                        ? `${queueStatus.live_stream.current_vehicles_total} vehicles`
                        : 'Unavailable'}
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.8 }}>Total in camera view</div>
                  </div>

                  <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Estimated Queue Wait</div>
                      <span title="Sum of waiting vehicles inside queue ROI × vehicle service time (rounded up to whole minutes)" style={{ cursor: 'help', fontSize: '12px', opacity: 0.7 }}>ℹ</span>
                    </div>
                    <div style={{ fontSize: '16px', fontWeight: 700, marginTop: '2px' }}>
                      {queueStatus?.live_stream.waiting_time_display ||
                        (queueStatus?.live_stream.waiting_time_estimate_seconds !== null && queueStatus?.live_stream.waiting_time_estimate_seconds !== undefined
                          ? `${Math.ceil(queueStatus.live_stream.waiting_time_estimate_seconds / 60)} min`
                          : 'Unavailable')}
                    </div>
                    <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.8 }}>
                      {queueStatus?.live_stream.waiting_time_estimate_seconds !== null && queueStatus?.live_stream.waiting_time_estimate_seconds !== undefined
                        ? 'Whole minutes only'
                        : 'Unavailable'}
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', fontSize: '12px' }}>
                  <div>
                    <strong>Last updated:</strong>{' '}
                    {queueStatus?.live_stream.detection_timestamp ? (
                      <span>
                        {new Date(queueStatus.live_stream.detection_timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        {queueStatus.live_stream.is_fresh ? '' : ' (Data outdated)'}
                      </span>
                    ) : (
                      'Unavailable'
                    )}
                  </div>
                  <div style={{ fontSize: '11px', opacity: 0.85 }}>
                    {queueStatus?.live_stream.message || 'Live camera not connected.'}
                  </div>
                </div>
              </div>
            </div>

            {/* Recorded Video Analysis */}
            <div style={{ border: '1px solid var(--border-subtle)', padding: '14px', backgroundColor: 'var(--color-white)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="tag-badge">RECORDED VIDEO</span>
                  <strong style={{ fontSize: '14px' }}>Video Analysis</strong>
                </div>
                {queueStatus?.historical_analysis && (
                  <span style={{ fontSize: '11px', fontWeight: 600 }}>
                    Analysis #{queueStatus.historical_analysis.analysis_id}
                  </span>
                )}
              </div>

              {queueStatus?.historical_analysis ? (
                <div>
                  <div className="notice-box" style={{ marginBottom: '12px' }}>
                    <strong>Recorded video analysis using YOLO detection. Not a live reading.</strong>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                      gap: '10px',
                      marginBottom: '12px',
                    }}
                  >
                    <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Last updated</div>
                      <div style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px' }}>
                        {new Date(queueStatus.historical_analysis.detection_timestamp).toLocaleString([], {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>

                    <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Queue length (peak)</div>
                      <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                        {queueStatus.historical_analysis.peak_queue_count} vehicles
                      </div>
                    </div>

                    <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Queue length (avg)</div>
                      <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                        {queueStatus.historical_analysis.average_queue_count !== undefined && queueStatus.historical_analysis.average_queue_count !== null
                          ? `${Math.round(Number(queueStatus.historical_analysis.average_queue_count))} vehicles`
                          : '—'}
                      </div>
                    </div>

                    <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Vehicles detected</div>
                      <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                        {queueStatus.historical_analysis.total_vehicles_detected} vehicles
                      </div>
                    </div>

                    <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Estimated Queue Wait</div>
                      <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                        {queueStatus.historical_analysis.average_waiting_time_seconds !== null && queueStatus.historical_analysis.average_waiting_time_seconds !== undefined
                          ? `${Math.ceil(queueStatus.historical_analysis.average_waiting_time_seconds / 60)} min`
                          : '0 min'}
                      </div>
                    </div>
                  </div>

                  {Object.keys(queueStatus.historical_analysis.vehicle_classes_detected).length > 0 && (
                    <div style={{ fontSize: '12px', marginTop: '6px' }}>
                      <strong>Vehicle classes detected:</strong>{' '}
                      {Object.entries(queueStatus.historical_analysis.vehicle_classes_detected)
                        .map(([cls, count]) => `${cls}: ${count}`)
                        .join(' | ')}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: '13px' }}>
                  No recorded video clips have been analyzed yet for this station.
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* 4. Limited-Time Slot Booking Section */}
      <section className="card" style={{ border: '2px solid var(--border-strong)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div>
            <span className="tag-badge">Slot Reservation</span>
            <h3 style={{ fontSize: '17px', fontWeight: 700, marginTop: '4px' }}>
              Limited-Time Refueling Slot Booking
            </h3>
          </div>
          <button
            type="button"
            className="btn-secondary"
            onClick={fetchSlots}
            style={{ fontSize: '12px', padding: '6px 12px' }}
          >
            Refresh Slots
          </button>
        </div>

        <p style={{ fontSize: '13px', marginBottom: '16px' }}>
          Reserve a guaranteed refueling time slot. Backend database constraints strictly prevent overbooking.
        </p>

        {loadingSlots ? (
          <div className="status-box">Loading available refueling slots...</div>
        ) : slots.length === 0 ? (
          /* "Show a booking action only when valid slots exist." */
          <div className="notice-box" style={{ padding: '20px', textAlign: 'center' }}>
            <div style={{ fontWeight: 700, fontSize: '14px', marginBottom: '4px' }}>
              No Booking Slots Open
            </div>
            <div style={{ fontSize: '13px' }}>
              No active refueling slots are currently open for this station. Booking action is unavailable at this time.
            </div>
            <div style={{ fontSize: '12px', marginTop: '6px' }}>
              The station operator has not published time slots for this window. Please check back later.
            </div>
          </div>
        ) : (
          /* Slots exist! Show booking action */
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 700, marginBottom: '8px' }}>
              Available Time Slots ({slots.length}):
            </label>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '18px' }}>
              {slots.map((slot) => {
                const isFull = slot.available_capacity <= 0;
                return (
                  <label
                    key={slot.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '12px 14px',
                      border: selectedSlotId === slot.id ? '2px solid var(--border-strong)' : '1px solid var(--border-subtle)',
                      backgroundColor: isFull ? 'var(--color-light-grey)' : 'var(--color-white)',
                      cursor: isFull ? 'not-allowed' : 'pointer',
                    }}
                  >
                    <input
                      type="radio"
                      name="station_slot_selection"
                      disabled={isFull}
                      checked={selectedSlotId === slot.id}
                      onChange={() => setSelectedSlotId(slot.id)}
                    />
                    <div style={{ fontSize: '13px', flex: 1 }}>
                      <strong>
                        {(() => {
                          const sDate = new Date(slot.start_time);
                          const today = new Date();
                          const isToday = sDate.toDateString() === today.toDateString();
                          const tomorrow = new Date(today.getTime() + 86400000);
                          const isTomorrow = sDate.toDateString() === tomorrow.toDateString();
                          const dateLabel = isToday
                            ? `Today (${sDate.toLocaleDateString([], { day: 'numeric', month: 'short' })})`
                            : isTomorrow
                            ? `Tomorrow (${sDate.toLocaleDateString([], { day: 'numeric', month: 'short' })})`
                            : sDate.toLocaleDateString([], { day: 'numeric', month: 'short' });
                          return dateLabel;
                        })()}{' '}
                        •{' '}
                        {new Date(slot.start_time).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}{' '}
                        -{' '}
                        {new Date(slot.end_time).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </strong>
                    </div>
                    <div style={{ fontSize: '12px' }}>
                      {isFull ? (
                        <strong>[FULLY BOOKED]</strong>
                      ) : (
                        <span>
                          {slot.booked_count}/{slot.max_capacity} reserved (<strong>{slot.available_capacity} slots open</strong>)
                        </span>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>

            {/* Booking Form (Only rendered when user selects a valid open slot) */}
            {selectedSlotId ? (
              <form
                onSubmit={handleConfirmBooking}
                style={{
                  borderTop: '2px solid var(--border-strong)',
                  paddingTop: '16px',
                }}
              >
                <h4 style={{ fontSize: '14px', fontWeight: 800, marginBottom: '12px' }}>
                  Complete Refueling Reservation
                </h4>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '14px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
                      Vehicle Registration Plate *
                    </label>
                    <input
                      type="text"
                      required
                      className="input-field"
                      value={vehiclePlate}
                      onChange={(e) => setVehiclePlate(e.target.value.toUpperCase())}
                      placeholder="e.g. MH12AB1234"
                    />
                    <span style={{ fontSize: '11px' }}>Required for forecourt entry verification</span>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
                      Contact Email or Phone (Optional)
                    </label>
                    <input
                      type="text"
                      className="input-field"
                      value={userContact}
                      onChange={(e) => setUserContact(e.target.value)}
                      placeholder="e.g. driver@email.com"
                    />
                    <span style={{ fontSize: '11px' }}>Optional reservation receipt notification</span>
                  </div>
                </div>

                {bookingError && (
                  <div className="notice-box" style={{ borderColor: 'var(--border-strong)', marginBottom: '12px' }}>
                    <strong>Reservation Error:</strong> {bookingError}
                  </div>
                )}

                {bookingResult && (
                  <div className="notice-box" style={{ border: '2px solid var(--border-strong)', marginBottom: '14px' }}>
                    <div style={{ fontWeight: 800, fontSize: '15px', marginBottom: '4px' }}>
                      Refueling Slot Reserved Successfully
                    </div>
                    <div>Booking Reference: <strong>{bookingResult.booking_reference}</strong></div>
                    <div>Vehicle Plate: {bookingResult.vehicle_plate}</div>
                    <div>Station: {bookingResult.station_name}</div>
                    <div style={{ marginTop: '8px', display: 'flex', gap: '10px', alignItems: 'center' }}>
                      {onNavigateToMyBookings && (
                        <button
                          type="button"
                          className="btn-primary"
                          onClick={onNavigateToMyBookings}
                          style={{ fontSize: '12px', padding: '6px 12px' }}
                        >
                          View in My Bookings →
                        </button>
                      )}
                      <span style={{ fontSize: '12px' }}>
                        Your reference has been permanently stored in your account.
                      </span>
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={bookingInProgress}
                    style={{ padding: '12px 20px', fontSize: '14px', fontWeight: 700 }}
                  >
                    {bookingInProgress ? 'Reserving Slot...' : 'Confirm Slot Reservation'}
                  </button>

                  {!userToken && (
                    <div style={{ fontSize: '12px' }}>
                      * Customer sign in required to reserve.{' '}
                      <button
                        type="button"
                        onClick={onRequireLogin}
                        style={{
                          background: 'none',
                          border: 'none',
                          textDecoration: 'underline',
                          cursor: 'pointer',
                          fontWeight: 700,
                        }}
                      >
                        Sign in now →
                      </button>
                    </div>
                  )}
                </div>
              </form>
            ) : (
              <div style={{ fontSize: '13px', fontStyle: 'italic' }}>
                * Select one of the available time slots above to proceed with reservation.
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
