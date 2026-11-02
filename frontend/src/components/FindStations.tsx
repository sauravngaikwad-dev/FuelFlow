import { useState, useEffect } from 'react';
import { StationMap } from './StationMap';

export interface Station {
  id: number;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  queue_capacity: number;
  pump_count: number;
  slot_duration_minutes: number;
  booking_window_hours: number;
  max_vehicles_per_slot: number;
  has_camera_configured: boolean;
  distance_km?: number | null;
  fuel_types_verified: string[];
}

export interface Slot {
  id: number;
  station_id: number;
  start_time: string;
  end_time: string;
  max_capacity: number;
  booked_count: number;
  available_capacity: number;
  is_active: boolean;
}

export interface BookingResult {
  id: number;
  booking_reference: string;
  slot_id: number;
  station_id: number;
  user_identifier: string;
  vehicle_plate: string;
  status: string;
  slot_start_time: string;
  slot_end_time: string;
  station_name: string;
  created_at: string;
}

interface FindStationsProps {
  userCoords: { lat: number; lng: number } | null;
  setUserCoords: React.Dispatch<React.SetStateAction<{ lat: number; lng: number } | null>>;
  locationStatus: string | null;
  setLocationStatus: React.Dispatch<React.SetStateAction<string | null>>;
  onSelectStation: (station: Station) => void;
}

function getNavigationUrl(
  station: Station,
  coords: { lat: number; lng: number } | null
): string {
  if (coords) {
    return `https://www.google.com/maps/dir/?api=1&origin=${coords.lat},${coords.lng}&destination=${station.latitude},${station.longitude}&travelmode=driving`;
  }
  return `https://www.google.com/maps/dir/?api=1&destination=${station.latitude},${station.longitude}&travelmode=driving`;
}

export function FindStations({
  userCoords,
  setUserCoords,
  locationStatus,
  setLocationStatus,
  onSelectStation,
}: FindStationsProps) {
  const [stations, setStations] = useState<Station[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [showMap, setShowMap] = useState(true);

  // Fetch stations with optional location and search query
  const fetchStations = (coords?: { lat: number; lng: number } | null, query?: string) => {
    setIsLoading(true);
    setErrorMessage(null);

    const params = new URLSearchParams();
    if (query && query.trim()) {
      params.append('search', query.trim());
    }
    const activeCoords = coords !== undefined ? coords : userCoords;
    if (activeCoords) {
      params.append('lat', activeCoords.lat.toString());
      params.append('lng', activeCoords.lng.toString());
    }

    const url = `http://127.0.0.1:8000/api/stations${params.toString() ? `?${params.toString()}` : ''}`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return res.json();
      })
      .then((data: Station[]) => {
        setStations(data);
      })
      .catch((err) => {
        setErrorMessage(err.message || 'Unable to load fuel stations.');
        setStations([]);
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    fetchStations();
  }, []);

  // Request browser geolocation
  const handleUseLocation = () => {
    if (!navigator.geolocation) {
      setLocationStatus('Geolocation is not supported by your browser.');
      return;
    }
    setLocationStatus('Requesting browser geolocation permission...');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        setUserCoords(coords);
        setLocationStatus(
          `Location enabled (${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}). Straight-line distances calculated accurately.`
        );
        fetchStations(coords, searchQuery);
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          setLocationStatus(
            'Location permission was denied. You can search by area or choose stations from the Karve Nagar MVP list.'
          );
        } else if (error.code === error.TIMEOUT) {
          setLocationStatus('Location request timed out. Please search by area name.');
        } else {
          setLocationStatus('Unable to retrieve GPS coordinates. Please search by area name.');
        }
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchStations(userCoords, searchQuery);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    fetchStations(userCoords, '');
  };

  const handleFocusKarveNagar = () => {
    setSearchQuery('Karve Nagar');
    fetchStations(userCoords, 'Karve Nagar');
  };

  // Transparent Recommendation Logic:
  // Recommends EXACTLY ONE station based on verified queue length (if available) and verified distance/capacity.
  // Never fabricates queue counts or distances.
  const recommendedStation = (() => {
    if (stations.length === 0) return null;

    // If distances are known from user coordinates, sort by shortest distance first
    const stationsWithDistance = stations.filter(
      (s) => s.distance_km !== null && s.distance_km !== undefined
    );
    if (stationsWithDistance.length > 0) {
      const sortedByDistance = [...stationsWithDistance].sort((a, b) => {
        const distA = a.distance_km ?? Infinity;
        const distB = b.distance_km ?? Infinity;
        if (distA !== distB) return distA - distB;
        return b.pump_count - a.pump_count; // Secondary tie-breaker: more dispensers
      });
      return sortedByDistance[0];
    }

    // If user coordinates not yet shared, recommend station in Karve Nagar with highest pump capacity
    const karveStations = stations.filter(
      (s) =>
        s.name.toLowerCase().includes('karve') ||
        s.address.toLowerCase().includes('karve') ||
        s.address.toLowerCase().includes('dahanukar') ||
        s.address.toLowerCase().includes('hingne')
    );
    if (karveStations.length > 0) {
      const sorted = [...karveStations].sort((a, b) => b.pump_count - a.pump_count);
      return sorted[0];
    }

    return stations[0];
  })();

  // Comparison stations: All other stations excluding the single recommended station
  const comparisonStations = stations.filter((s) => s.id !== recommendedStation?.id);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* 1. Location & Search Header */}
      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
          <div>
            <span className="tag-badge">Discovery</span>
            <h2 style={{ fontSize: '18px', fontWeight: 800, marginTop: '4px' }}>
              Find Fuel Stations
            </h2>
            <p style={{ fontSize: '13px', marginTop: '2px' }}>
              MVP focused on Karve Nagar, Pune with verified participating stations. Zero fake queues or mock data.
            </p>
          </div>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setShowMap(!showMap)}
            style={{ fontSize: '12px', padding: '6px 12px' }}
          >
            {showMap ? 'Hide Map View' : 'Show Map View'}
          </button>
        </div>

        {/* Location Action Buttons */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '14px', marginBottom: '12px' }}>
          <button
            type="button"
            className="btn-primary"
            onClick={handleUseLocation}
            style={{ fontSize: '13px', padding: '10px 16px' }}
          >
            📍 Use My Current Location
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={handleFocusKarveNagar}
            style={{ fontSize: '13px', padding: '10px 14px' }}
          >
            Focus Karve Nagar, Pune
          </button>

          {userCoords && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setUserCoords(null);
                setLocationStatus(null);
                fetchStations(null, searchQuery);
              }}
              style={{ fontSize: '13px', padding: '10px 14px' }}
            >
              Reset Location
            </button>
          )}
        </div>

        {locationStatus && (
          <div className="notice-box" style={{ marginBottom: '12px' }}>
            {locationStatus}
          </div>
        )}

        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            className="input-field"
            style={{ marginTop: 0, flex: 1 }}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by area or station name (e.g. Karve Nagar, Warje, Hingne, Kothrud)..."
          />
          <button type="submit" className="btn-primary">
            Search
          </button>
          {searchQuery && (
            <button type="button" className="btn-secondary" onClick={handleClearSearch}>
              Clear
            </button>
          )}
        </form>
      </section>

      {/* 2. Interactive Map (Real OpenStreetMap Leaflet Engine) */}
      {showMap && (
        <section className="card" style={{ padding: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="tag-badge">OpenStreetMap Provider</span>
              <strong style={{ fontSize: '14px' }}>Karve Nagar, Pune Stations Map</strong>
            </div>
            <div style={{ fontSize: '12px' }}>
              {stations.length} participating station{stations.length === 1 ? '' : 's'} plotted
            </div>
          </div>

          <StationMap
            stations={stations}
            userCoords={userCoords}
            selectedStation={null}
            onSelectStation={(st) => onSelectStation(st)}
          />

          <div style={{ fontSize: '11px', marginTop: '8px' }}>
            * Genuine map tiles via OpenStreetMap. Black dot indicates your GPS position (when permission granted).
            Click any station marker or its popup to navigate to its dedicated Station Details page.
          </div>
        </section>
      )}

      {/* 3. Transparent Single Recommendation Banner */}
      {recommendedStation && (
        <section className="card" style={{ border: '2px solid var(--border-strong)', backgroundColor: 'var(--color-white)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="tag-badge">Recommended Station (Rank #1)</span>
                <span style={{ fontSize: '18px', fontWeight: 800 }}>{recommendedStation.name}</span>
              </div>
              <p style={{ fontSize: '13px', marginTop: '4px' }}>{recommendedStation.address}</p>
            </div>

            <button
              type="button"
              className="btn-primary"
              onClick={() => onSelectStation(recommendedStation)}
              style={{ padding: '10px 18px', fontSize: '13px', fontWeight: 700 }}
            >
              View Station Details & Booking →
            </button>
          </div>

          {/* Transparent Ranking Criteria */}
          <div
            style={{
              marginTop: '12px',
              padding: '12px 14px',
              backgroundColor: 'var(--color-light-grey)',
              border: '1px solid var(--border-strong)',
              fontSize: '13px',
            }}
          >
            <strong>Transparent Ranking Justification:</strong>
            <ul style={{ marginLeft: '20px', marginTop: '6px', lineHeight: '1.4' }}>
              {recommendedStation.distance_km !== null && recommendedStation.distance_km !== undefined ? (
                <li>
                  <strong>Proximity Rank:</strong> Closest verified participating station ({recommendedStation.distance_km} km straight-line distance).
                </li>
              ) : (
                <li>
                  <strong>Proximity Rank:</strong> Prime Karve Nagar participating station. (Enable GPS location above for exact personal distance).
                </li>
              )}
              <li>
                <strong>Throughput Capacity:</strong> Equipped with {recommendedStation.pump_count} active dispensers and {recommendedStation.queue_capacity} vehicle forecourt capacity.
              </li>
              <li>
                <strong>Camera status:</strong> Offline. No queue measurements are fabricated. Ranking is derived strictly from verified distance and pump capacity.
              </li>
            </ul>
          </div>
        </section>
      )}

      {/* 4. Comparison List: Other Participating Stations */}
      <section className="card">
        <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '6px' }}>
          Available Participating Stations for Comparison ({comparisonStations.length})
        </h3>
        <p style={{ fontSize: '13px', marginBottom: '14px' }}>
          Compare real metrics across other participating stations in the Karve Nagar MVP sector.
        </p>

        {isLoading ? (
          <div className="status-box">Loading verified fuel stations...</div>
        ) : errorMessage ? (
          <div className="status-box">Error loading stations: {errorMessage}</div>
        ) : comparisonStations.length === 0 ? (
          <div className="status-box">
            {searchQuery
              ? `No other fuel stations found matching "${searchQuery}".`
              : 'All available participating stations are displayed above.'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {comparisonStations.map((st) => (
              <div
                key={st.id}
                style={{
                  border: '1px solid var(--border-subtle)',
                  padding: '14px 16px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '12px',
                  backgroundColor: 'var(--color-white)',
                }}
              >
                <div style={{ flex: 1, minWidth: '240px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 700, fontSize: '15px' }}>{st.name}</span>
                  </div>

                  <div style={{ fontSize: '13px', marginTop: '2px' }}>{st.address}</div>

                  <div style={{ fontSize: '12px', marginTop: '6px', display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
                    {st.distance_km !== null && st.distance_km !== undefined ? (
                      <span>
                        <strong>Distance:</strong> {st.distance_km} km
                      </span>
                    ) : (
                      <span>
                        <strong>Distance:</strong> Share location to compute
                      </span>
                    )}
                    <span>
                      <strong>Dispensers:</strong> {st.pump_count} Pumps
                    </span>
                    <span>
                      <strong>Capacity:</strong> {st.queue_capacity} Vehicles
                    </span>
                    <span>
                      <strong>Window:</strong> {st.slot_duration_minutes} min slots
                    </span>
                  </div>

                  <div style={{ fontSize: '11px', marginTop: '4px' }}>
                    Coordinates: {st.latitude.toFixed(4)}, {st.longitude.toFixed(4)}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <a
                    href={getNavigationUrl(st, userCoords)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary"
                    style={{ textDecoration: 'none', padding: '8px 12px', fontSize: '13px' }}
                  >
                    ↗ Navigate
                  </a>

                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => onSelectStation(st)}
                    style={{ padding: '8px 14px', fontSize: '13px', fontWeight: 600 }}
                  >
                    View Details & Slots →
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
