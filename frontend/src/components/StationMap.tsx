import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import type { Station } from './FindStations';

export interface RouteEstimate {
  distanceKm: number;
  durationMinutes: number;
  serviceName: string;
}

interface StationMapProps {
  stations: Station[];
  userCoords: { lat: number; lng: number } | null;
  selectedStation: Station | null;
  onSelectStation: (station: Station) => void;
  onRouteChange?: (estimate: RouteEstimate | null) => void;
}

export function StationMap({
  stations,
  userCoords,
  selectedStation,
  onSelectStation,
  onRouteChange,
}: StationMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const routeLayerRef = useRef<L.LayerGroup | null>(null);

  const [routeInfo, setRouteInfo] = useState<string | null>(null);

  // Initialize Leaflet Map once
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) return;

    // Default center (Latur, Maharashtra coords)
    const initialLat = userCoords?.lat ?? (stations[0]?.latitude ?? 18.4088);
    const initialLng = userCoords?.lng ?? (stations[0]?.longitude ?? 76.5604);

    const map = L.map(mapContainerRef.current, {
      center: [initialLat, initialLng],
      zoom: 13,
      zoomControl: true,
    });

    // Real OpenStreetMap Tile Provider
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    markersLayerRef.current = L.layerGroup().addTo(map);
    routeLayerRef.current = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Markers (User + Stations)
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersLayer = markersLayerRef.current;
    if (!map || !markersLayer) return;

    markersLayer.clearLayers();
    const boundsPoints: L.LatLngExpression[] = [];

    // 1. User Location Marker
    if (userCoords) {
      const userIcon = L.divIcon({
        className: 'user-map-marker',
        html: `
          <div style="
            width: 20px;
            height: 20px;
            background-color: #303030;
            border: 3px solid #FFFFFF;
            border-radius: 50%;
            box-shadow: 0 0 0 2px #303030;
          "></div>
        `,
        iconSize: [20, 20],
        iconAnchor: [10, 10],
      });

      const userMarker = L.marker([userCoords.lat, userCoords.lng], { icon: userIcon });
      userMarker.bindPopup(`
        <div style="font-family: inherit; font-size: 13px; color: #303030;">
          <strong>Your Current Location</strong><br/>
          Lat: ${userCoords.lat.toFixed(4)}, Lng: ${userCoords.lng.toFixed(4)}
        </div>
      `);
      markersLayer.addLayer(userMarker);
      boundsPoints.push([userCoords.lat, userCoords.lng]);
    }

    // 2. Station Markers (strictly verified stations only)
    stations.forEach((st) => {
      const isSelected = selectedStation?.id === st.id;
      const markerColor = isSelected ? '#303030' : '#FFFFFF';
      const textColor = isSelected ? '#FFFFFF' : '#303030';
      const borderColor = '#303030';

      const stationIcon = L.divIcon({
        className: 'station-map-marker',
        html: `
          <div style="
            background-color: ${markerColor};
            color: ${textColor};
            border: 2px solid ${borderColor};
            padding: 3px 7px;
            font-size: 11px;
            font-weight: 700;
            white-space: nowrap;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
            display: inline-flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
          ">
            <span>⛽</span>
            <span>${st.name}</span>
          </div>
        `,
        iconSize: [120, 26],
        iconAnchor: [60, 13],
      });

      const marker = L.marker([st.latitude, st.longitude], { icon: stationIcon });
      marker.on('click', () => {
        onSelectStation(st);
      });

      marker.bindPopup(`
        <div style="font-family: inherit; font-size: 13px; color: #303030; line-height: 1.4;">
          <strong>${st.name}</strong><br/>
          ${st.address}<br/>
          ${st.distance_km !== undefined && st.distance_km !== null ? `Straight-line Distance: <strong>${st.distance_km} km</strong><br/>` : ''}
          <div style="margin-top: 6px;">
            <button id="popup-select-${st.id}" style="
              background-color: #303030;
              color: #FFFFFF;
              border: 1px solid #303030;
              padding: 4px 8px;
              font-size: 12px;
              cursor: pointer;
              font-weight: 600;
            ">Select Station</button>
          </div>
        </div>
      `);

      marker.on('popupopen', () => {
        const btn = document.getElementById(`popup-select-${st.id}`);
        if (btn) {
          btn.onclick = () => {
            onSelectStation(st);
            marker.closePopup();
          };
        }
      });

      markersLayer.addLayer(marker);
      boundsPoints.push([st.latitude, st.longitude]);
    });

    // Auto-fit bounds if we have points
    if (boundsPoints.length > 1) {
      map.fitBounds(L.latLngBounds(boundsPoints), { padding: [40, 40], maxZoom: 15 });
    } else if (boundsPoints.length === 1) {
      map.setView(boundsPoints[0], 14);
    }
  }, [stations, userCoords, selectedStation]);

  // Route calculation and polyline rendering
  useEffect(() => {
    const map = mapInstanceRef.current;
    const routeLayer = routeLayerRef.current;
    if (!map || !routeLayer) return;

    routeLayer.clearLayers();
    setRouteInfo(null);
    if (onRouteChange) onRouteChange(null);

    if (!userCoords || !selectedStation) return;

    // Attempt real driving route from public OSRM routing service
    const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${userCoords.lng},${userCoords.lat};${selectedStation.longitude},${selectedStation.latitude}?overview=full&geometries=geojson`;

    let isMounted = true;

    fetch(osrmUrl)
      .then((res) => {
        if (!res.ok) throw new Error(`Routing status ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!isMounted) return;
        if (data.code === 'Ok' && data.routes && data.routes.length > 0) {
          const route = data.routes[0];
          const distKm = Math.round((route.distance / 1000) * 10) / 10;
          const durationMin = Math.max(1, Math.round(route.duration / 60));

          // Draw real driving route polyline in Charcoal (#303030)
          const geojsonLayer = L.geoJSON(route.geometry, {
            style: {
              color: '#303030',
              weight: 4,
              opacity: 0.9,
            },
          });
          routeLayer.addLayer(geojsonLayer);

          const estimate: RouteEstimate = {
            distanceKm: distKm,
            durationMinutes: durationMin,
            serviceName: 'OpenStreetMap OSRM',
          };

          setRouteInfo(`Driving Route: ${distKm} km (~${durationMin} mins via OpenStreetMap/OSRM)`);
          if (onRouteChange) onRouteChange(estimate);
        } else {
          throw new Error('No driving route found');
        }
      })
      .catch(() => {
        if (!isMounted) return;
        // Fallback: draw straight-line dashed connector in Grey (#707070)
        const straightLine = L.polyline(
          [
            [userCoords.lat, userCoords.lng],
            [selectedStation.latitude, selectedStation.longitude],
          ],
          {
            color: '#707070',
            weight: 2,
            dashArray: '6, 6',
          }
        );
        routeLayer.addLayer(straightLine);
        setRouteInfo('External driving routing service unreachable. Displaying straight-line path.');
        if (onRouteChange) onRouteChange(null);
      });

    return () => {
      isMounted = false;
    };
  }, [userCoords, selectedStation]);

  return (
    <div style={{ border: '1px solid var(--border-strong)', marginBottom: '16px' }}>
      <div
        ref={mapContainerRef}
        style={{
          width: '100%',
          height: '340px',
          backgroundColor: 'var(--color-light-grey)',
        }}
      />
      {routeInfo && (
        <div
          style={{
            padding: '8px 12px',
            fontSize: '12px',
            backgroundColor: 'var(--color-white)',
            borderTop: '1px solid var(--border-subtle)',
            fontWeight: 600,
          }}
        >
          {routeInfo}
        </div>
      )}
    </div>
  );
}
