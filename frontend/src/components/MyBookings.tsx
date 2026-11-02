import { useState, useEffect } from 'react';

interface BookingRecord {
  id: number;
  booking_reference: string;
  slot_id: number;
  station_id: number;
  user_id: number;
  user_identifier: string;
  vehicle_plate: string;
  status: string;
  slot_start_time: string;
  slot_end_time: string;
  station_name: string;
  created_at: string;
}

interface MyBookingsProps {
  userToken?: string | null;
  onRequireLogin?: () => void;
}

export function MyBookings({ userToken, onRequireLogin }: MyBookingsProps) {
  const [bookings, setBookings] = useState<BookingRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterQuery, setFilterQuery] = useState('');
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const fetchMyBookings = () => {
    if (!userToken) return;

    setLoading(true);
    setActionMessage(null);

    fetch('http://127.0.0.1:8000/api/bookings/my-bookings', {
      headers: {
        Authorization: `Bearer ${userToken}`,
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load your bookings.`);
        return res.json();
      })
      .then((data: BookingRecord[]) => {
        setBookings(data);
      })
      .catch((err) => {
        setActionMessage(err.message || 'Error loading bookings');
        setBookings([]);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    if (userToken) {
      fetchMyBookings();
    }
  }, [userToken]);

  const handleCancelBooking = (reference: string) => {
    if (!window.confirm(`Are you sure you want to cancel booking ${reference}?`)) {
      return;
    }

    fetch(`http://127.0.0.1:8000/api/bookings/${reference}/cancel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${userToken}`,
      },
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to cancel');
        return data as BookingRecord;
      })
      .then((updated) => {
        setActionMessage(`Booking ${updated.booking_reference} has been cancelled.`);
        setBookings((prev) =>
          prev.map((b) => (b.booking_reference === updated.booking_reference ? updated : b))
        );
      })
      .catch((err) => {
        setActionMessage(`Cancellation error: ${err.message}`);
      });
  };

  if (!userToken) {
    return (
      <div className="card" style={{ maxWidth: '520px', margin: '0 auto', textAlign: 'center' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '8px' }}>
          Customer Sign In Required
        </h2>
        <p style={{ fontSize: '13px', marginBottom: '16px' }}>
          Your bookings are securely protected and associated with your account. Please sign in to view and manage your reservations.
        </p>

        <button type="button" className="btn-primary" onClick={onRequireLogin}>
          Sign In to Access My Bookings
        </button>
      </div>
    );
  }

  // Filter local bookings if user typed a search query
  const displayedBookings = bookings.filter((b) => {
    if (!filterQuery.trim()) return true;
    const term = filterQuery.toLowerCase().trim();
    return (
      b.booking_reference.toLowerCase().includes(term) ||
      b.vehicle_plate.toLowerCase().includes(term) ||
      b.station_name.toLowerCase().includes(term)
    );
  });

  return (
    <div>
      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '4px' }}>
              My Refueling Reservations
            </h2>
            <p style={{ fontSize: '13px' }}>
              All reservations associated with your authenticated account.
            </p>
          </div>
          <button type="button" className="btn-secondary" onClick={fetchMyBookings} style={{ fontSize: '12px' }}>
            Refresh
          </button>
        </div>

        {bookings.length > 0 && (
          <div style={{ marginTop: '14px' }}>
            <input
              type="text"
              className="input-field"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              placeholder="Filter by vehicle plate, reference code, or station name..."
            />
          </div>
        )}

        {actionMessage && (
          <div className="notice-box" style={{ marginTop: '12px' }}>
            {actionMessage}
          </div>
        )}
      </section>

      {/* Bookings List */}
      <section className="card">
        {loading ? (
          <div className="status-box">Loading your reservations...</div>
        ) : bookings.length === 0 ? (
          <div className="status-box">
            You have no slot reservations yet. Visit <strong>Find Stations</strong> to discover stations and reserve a slot.
          </div>
        ) : displayedBookings.length === 0 ? (
          <div className="status-box">
            No bookings match your filter query "{filterQuery}".
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {displayedBookings.map((b) => {
              const isConfirmed = b.status === 'CONFIRMED';
              return (
                <div
                  key={b.id}
                  style={{
                    border: '1px solid #303030',
                    padding: '16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    backgroundColor: isConfirmed ? '#FFFFFF' : '#E8E8E8',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                      <span className="tag-badge">{b.status}</span>
                      <strong style={{ fontSize: '15px' }}>{b.booking_reference}</strong>
                    </div>

                    <div style={{ fontSize: '13px' }}>
                      <strong>Station:</strong> {b.station_name}
                    </div>
                    <div style={{ fontSize: '13px' }}>
                      <strong>Vehicle Plate:</strong> {b.vehicle_plate}
                    </div>
                    <div style={{ fontSize: '13px', marginTop: '2px' }}>
                      <strong>Slot Time:</strong>{' '}
                      {new Date(b.slot_start_time).toLocaleDateString([], { month: 'short', day: 'numeric' })}{' '}
                      {new Date(b.slot_start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                      {new Date(b.slot_end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>

                  {isConfirmed && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleCancelBooking(b.booking_reference)}
                    >
                      Cancel Slot
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
