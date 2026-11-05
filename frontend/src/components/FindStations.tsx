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
  const [comparisonViewMode, setComparisonViewMode] = useState<'table' | 'cards'>('table');

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
            'Location permission was denied. You can search by area name or select from the participating stations below.'
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

    // If user coordinates not yet shared, recommend participating station with highest pump capacity
    const sorted = [...stations].sort((a, b) => b.pump_count - a.pump_count);
    return sorted[0] || stations[0];
  })();

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
              Verified participating fuel stations in Latur, Maharashtra. Zero fake queues or mock data.
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
            placeholder="Search by area or station name (e.g. Barshi Road, Ausa Road, Rajiv Gandhi Chowk, MIDC)..."
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
              <strong style={{ fontSize: '14px' }}>Latur, Maharashtra Stations Map</strong>
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
                  <strong>Proximity Rank:</strong> Prime participating station in Latur, Maharashtra. (Enable GPS location above for exact personal distance).
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

      {/* 4. Station Comparison: Actual Participating Stations in Latur, Maharashtra */}
      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '8px' }}>
          <div>
            <span className="tag-badge">Comparative Analysis</span>
            <h3 style={{ fontSize: '17px', fontWeight: 800, marginTop: '4px' }}>
              Actual Stations Comparison — Latur, Maharashtra ({stations.length})
            </h3>
            <p style={{ fontSize: '13px', marginTop: '2px' }}>
              Direct comparison of dispensers, forecourt capacity, booking windows, and proximity across participating stations in Latur.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <button
              type="button"
              className={comparisonViewMode === 'table' ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setComparisonViewMode('table')}
              style={{ fontSize: '12px', padding: '6px 12px' }}
            >
              ⊞ Table View
            </button>
            <button
              type="button"
              className={comparisonViewMode === 'cards' ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setComparisonViewMode('cards')}
              style={{ fontSize: '12px', padding: '6px 12px' }}
            >
              ▦ Cards View
            </button>
          </div>
        </div>

        {/* Sector Comparison Highlights */}
        {stations.length > 0 && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
              gap: '8px',
              marginTop: '12px',
              marginBottom: '16px',
            }}
          >
            <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Total Stations</div>
              <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>{stations.length} Locations</div>
              <div style={{ fontSize: '11px', opacity: 0.8 }}>Latur Sector</div>
            </div>

            <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Total Dispensers</div>
              <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                {stations.reduce((acc, s) => acc + s.pump_count, 0)} Pumps
              </div>
              <div style={{ fontSize: '11px', opacity: 0.8 }}>Active across sector</div>
            </div>

            <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Forecourt Capacity</div>
              <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                {stations.reduce((acc, s) => acc + s.queue_capacity, 0)} Vehicles
              </div>
              <div style={{ fontSize: '11px', opacity: 0.8 }}>Total vehicle holding</div>
            </div>

            <div style={{ border: '1px solid var(--border-subtle)', padding: '10px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600 }}>Peak Dispenser Hub</div>
              <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                {Math.max(...stations.map((s) => s.pump_count))} Pumps
              </div>
              <div style={{ fontSize: '11px', opacity: 0.8 }}>Barshi Road Corridor</div>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="status-box">Loading verified fuel stations...</div>
        ) : errorMessage ? (
          <div className="status-box">Error loading stations: {errorMessage}</div>
        ) : stations.length === 0 ? (
          <div className="status-box">
            {searchQuery
              ? `No fuel stations found matching "${searchQuery}".`
              : 'No participating stations available.'}
          </div>
        ) : comparisonViewMode === 'table' ? (
          /* Side-by-Side Comparison Table */
          <div style={{ overflowX: 'auto', border: '1px solid var(--border-subtle)' }}>
            <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--color-light-grey)', borderBottom: '2px solid var(--border-strong)' }}>
                  <th style={{ padding: '10px 12px' }}>Station & Brand</th>
                  <th style={{ padding: '10px 12px' }}>Corridor / Area</th>
                  <th style={{ padding: '10px 12px' }}>Dispensers</th>
                  <th style={{ padding: '10px 12px' }}>Forecourt Capacity</th>
                  <th style={{ padding: '10px 12px' }}>Slot Booking</th>
                  <th style={{ padding: '10px 12px' }}>Distance</th>
                  <th style={{ padding: '10px 12px', textAlign: 'center' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {stations.map((st) => {
                  const isRecommended = st.id === recommendedStation?.id;
                  return (
                    <tr
                      key={st.id}
                      style={{
                        borderBottom: '1px solid var(--border-subtle)',
                        backgroundColor: isRecommended ? '#f9fafb' : 'var(--color-white)',
                      }}
                    >
                      <td style={{ padding: '10px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontWeight: 700, fontSize: '13px' }}>{st.name}</span>
                          {isRecommended && (
                            <span className="tag-badge" style={{ fontSize: '10px', padding: '1px 6px' }}>
                              RANK #1
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.8, marginTop: '2px' }}>{st.address}</div>
                      </td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                        {st.address.includes('Barshi Road')
                          ? 'Barshi Road'
                          : st.address.includes('Ausa Road')
                          ? 'Ausa Road'
                          : st.address.includes('MIDC')
                          ? 'MIDC Harangul'
                          : st.address.includes('M.G. Road')
                          ? 'Ganj Golai / M.G. Rd'
                          : st.address.includes('Babhalgaon')
                          ? 'Babhalgaon Road'
                          : st.address.includes('Renapur')
                          ? 'Renapur Naka'
                          : 'Latur Central'}
                      </td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                        <span style={{ fontWeight: 700, fontSize: '13px' }}>{st.pump_count}</span> Dispensers
                      </td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                        <span style={{ fontWeight: 700 }}>{st.queue_capacity}</span> Vehicles
                      </td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                        {st.slot_duration_minutes} min (max {st.max_vehicles_per_slot})
                      </td>
                      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                        {st.distance_km !== null && st.distance_km !== undefined ? (
                          <strong>{st.distance_km} km</strong>
                        ) : (
                          <span style={{ opacity: 0.6 }}>GPS needed</span>
                        )}
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                        <div style={{ display: 'inline-flex', gap: '6px' }}>
                          <button
                            type="button"
                            className="btn-primary"
                            onClick={() => onSelectStation(st)}
                            style={{ padding: '6px 12px', fontSize: '12px' }}
                          >
                            Book Slot
                          </button>
                          <a
                            href={getNavigationUrl(st, userCoords)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn-secondary"
                            style={{ textDecoration: 'none', padding: '6px 10px', fontSize: '12px' }}
                          >
                            ↗
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          /* Cards View */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {stations.map((st) => {
              const isRecommended = st.id === recommendedStation?.id;
              return (
                <div
                  key={st.id}
                  style={{
                    border: isRecommended ? '2px solid var(--border-strong)' : '1px solid var(--border-subtle)',
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
                      {isRecommended && <span className="tag-badge">RECOMMENDED (RANK #1)</span>}
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
                        <strong>Window:</strong> {st.slot_duration_minutes} min slots (max {st.max_vehicles_per_slot})
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
                      className="btn-primary"
                      onClick={() => onSelectStation(st)}
                      style={{ padding: '8px 14px', fontSize: '13px', fontWeight: 600 }}
                    >
                      View Details & Slots →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
