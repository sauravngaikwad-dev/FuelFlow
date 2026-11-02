import { useState, useEffect } from 'react';
import { FindStations, type Station } from './components/FindStations';
import { StationDetails } from './components/StationDetails';
import { MyBookings } from './components/MyBookings';
import { Help } from './components/Help';
import { UserAuth } from './components/UserAuth';
import { OperatorAuth } from './components/OperatorAuth';
import { OperatorPortal } from './components/OperatorPortal';
import { AccessDenied } from './components/AccessDenied';

type PortalType = 'user' | 'operator';
type AppPage =
  | 'find'
  | 'station-details'
  | 'my-bookings'
  | 'help'
  | 'user-login'
  | 'operator-login'
  | 'operator-portal';

interface BackendHealth {
  status: string;
  service: string;
  version: string;
  database: string;
}

export function App() {
  const [activePortal, setActivePortal] = useState<PortalType>('user');
  const [activePage, setActivePage] = useState<AppPage>('find');
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);

  // Global coordinates and location status shared across station discovery and details
  const [userCoords, setUserCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locationStatus, setLocationStatus] = useState<string | null>(null);

  // Auth state
  const [token, setToken] = useState<string | null>(localStorage.getItem('fuelflow_token'));
  const [username, setUsername] = useState<string | null>(localStorage.getItem('fuelflow_user'));
  const [role, setRole] = useState<string | null>(localStorage.getItem('fuelflow_role'));

  // Mobile menu toggle
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Backend Health
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  const checkHealth = () => {
    fetch('http://127.0.0.1:8000/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setBackendHealth(data);
        setBackendError(null);
      })
      .catch((err) => {
        setBackendError(err.message || 'Backend not reachable');
        setBackendHealth(null);
      });
  };

  useEffect(() => {
    checkHealth();
  }, []);

  const handleLoginSuccess = (newToken: string, newUsername: string, newRole: string) => {
    setToken(newToken);
    setUsername(newUsername);
    setRole(newRole);

    if (newRole === 'operator' || newRole === 'admin') {
      setActivePortal('operator');
      setActivePage('operator-portal');
    } else {
      setActivePortal('user');
      setActivePage('find');
    }
    setMobileMenuOpen(false);
  };

  const handleLogout = () => {
    localStorage.removeItem('fuelflow_token');
    localStorage.removeItem('fuelflow_user');
    localStorage.removeItem('fuelflow_role');
    setToken(null);
    setUsername(null);
    setRole(null);
    setActivePortal('user');
    setActivePage('find');
    setMobileMenuOpen(false);
  };

  // Navigating to station details
  const handleSelectStation = (station: Station) => {
    setSelectedStation(station);
    setActivePage('station-details');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const navigateTo = (page: AppPage, portal: PortalType = 'user') => {
    setActivePortal(portal);
    setActivePage(page);
    setMobileMenuOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="app-shell">
      {/* Mobile Top Header */}
      <div className="mobile-topbar">
        <div>
          <strong style={{ fontSize: '17px', letterSpacing: '-0.5px' }}>FuelFlow</strong>
          <span style={{ fontSize: '11px', marginLeft: '6px', opacity: 0.8 }}>
            {activePortal === 'operator' ? 'Staff Portal' : 'User Portal'}
          </span>
        </div>
        <button
          type="button"
          className="hamburger-btn"
          aria-label="Toggle navigation menu"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? '✕' : '☰'}
        </button>
      </div>

      {/* Mobile Overlay Backdrop */}
      <div
        className={`mobile-overlay ${mobileMenuOpen ? 'mobile-open' : ''}`}
        onClick={() => setMobileMenuOpen(false)}
      />

      {/* Compact Sidebar (Desktop sticky & Mobile collapsible drawer) */}
      <aside className={`app-sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}>
        <div>
          {/* Brand Header */}
          <div className="sidebar-header">
            <h1 className="sidebar-brand">FuelFlow</h1>
            <p className="sidebar-tagline">
              Real Fuel-Station Queue Management & Recommendation
            </p>

            {/* Portal Switcher Tabs */}
            <div className="portal-switcher">
              <button
                type="button"
                className={`portal-tab-btn ${activePortal === 'user' ? 'active' : ''}`}
                onClick={() => {
                  setActivePortal('user');
                  if (activePage === 'operator-portal' || activePage === 'operator-login') {
                    setActivePage('find');
                  }
                  setMobileMenuOpen(false);
                }}
              >
                User Portal
              </button>
              <button
                type="button"
                className={`portal-tab-btn ${activePortal === 'operator' ? 'active' : ''}`}
                onClick={() => {
                  setActivePortal('operator');
                  if (token && (role === 'operator' || role === 'admin')) {
                    setActivePage('operator-portal');
                  } else {
                    setActivePage('operator-login');
                  }
                  setMobileMenuOpen(false);
                }}
              >
                Staff Portal
              </button>
            </div>
          </div>

          {/* Navigation Items based on Active Portal */}
          {activePortal === 'user' ? (
            <div>
              <div className="sidebar-section-title">User Navigation</div>
              <nav className="sidebar-nav">
                <button
                  type="button"
                  className={`sidebar-link ${activePage === 'find' ? 'active' : ''}`}
                  onClick={() => navigateTo('find', 'user')}
                >
                  <span>Find Stations</span>
                  <span style={{ fontSize: '11px' }}>Karve Nagar</span>
                </button>

                <button
                  type="button"
                  className={`sidebar-link ${activePage === 'station-details' ? 'active' : ''}`}
                  onClick={() => {
                    if (selectedStation) {
                      navigateTo('station-details', 'user');
                    } else {
                      // Prompt user to pick station
                      navigateTo('find', 'user');
                    }
                  }}
                >
                  <span>Station Details</span>
                  <span style={{ fontSize: '11px' }}>
                    {selectedStation ? 'Selected' : 'Pick'}
                  </span>
                </button>

                <button
                  type="button"
                  className={`sidebar-link ${activePage === 'my-bookings' ? 'active' : ''}`}
                  onClick={() => navigateTo('my-bookings', 'user')}
                >
                  <span>My Bookings</span>
                  <span style={{ fontSize: '11px' }}>Slots</span>
                </button>

                <button
                  type="button"
                  className={`sidebar-link ${activePage === 'help' ? 'active' : ''}`}
                  onClick={() => navigateTo('help', 'user')}
                >
                  <span>Help & Policies</span>
                  <span style={{ fontSize: '11px' }}>Integrity</span>
                </button>
              </nav>
            </div>
          ) : (
            <div>
              <div className="sidebar-section-title">Operator / Admin</div>
              <nav className="sidebar-nav">
                {token && (role === 'operator' || role === 'admin') ? (
                  <button
                    type="button"
                    className={`sidebar-link ${activePage === 'operator-portal' ? 'active' : ''}`}
                    onClick={() => navigateTo('operator-portal', 'operator')}
                  >
                    <span>Operator Dashboard</span>
                    <span style={{ fontSize: '11px' }}>Phase 3 YOLO</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    className={`sidebar-link ${activePage === 'operator-login' ? 'active' : ''}`}
                    onClick={() => navigateTo('operator-login', 'operator')}
                  >
                    <span>Operator Sign In</span>
                    <span style={{ fontSize: '11px' }}>Staff Access</span>
                  </button>
                )}

                <button
                  type="button"
                  className="sidebar-link"
                  onClick={() => navigateTo('find', 'user')}
                >
                  <span>← Return to User Portal</span>
                </button>
              </nav>
            </div>
          )}
        </div>

        {/* Sidebar Footer: Session, Status & Auth */}
        <div className="sidebar-footer">
          {/* User Session Info */}
          <div style={{ marginBottom: '12px' }}>
            {token ? (
              <div style={{ border: '1px solid var(--border-subtle)', padding: '8px 10px' }}>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 700 }}>
                  Active Session
                </div>
                <div style={{ fontSize: '13px', fontWeight: 800, marginTop: '2px' }}>
                  {username}
                </div>
                <div style={{ fontSize: '11px' }}>Role: <strong>{role}</strong></div>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleLogout}
                  style={{ marginTop: '8px', width: '100%', padding: '6px', fontSize: '12px' }}
                >
                  Log Out
                </button>
              </div>
            ) : (
              <div>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => navigateTo('user-login', 'user')}
                  style={{ width: '100%', padding: '8px', fontSize: '12px' }}
                >
                  Sign In (User)
                </button>
              </div>
            )}
          </div>

          {/* System Health Status */}
          <div style={{ fontSize: '11px', lineHeight: '1.4' }}>
            {backendHealth ? (
              <div>
                ● Backend Online (v{backendHealth.version})
              </div>
            ) : (
              <div style={{ color: 'var(--color-charcoal)' }}>
                ○ Backend Disconnected ({backendError || 'Offline'})
              </div>
            )}
            <div style={{ marginTop: '4px', opacity: 0.8 }}>
              FuelFlow &copy; 2026. Zero mock data.
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="app-main-content">
        <div className="main-content-inner">
          {/* Backend Status Alert if Offline */}
          {!backendHealth && (
            <div className="notice-box" style={{ marginBottom: '16px', border: '2px solid var(--border-strong)' }}>
              <strong>System Notice:</strong> FastAPI backend on port 8000 is not reachable ({backendError || 'Offline'}).
              Ensure backend server is running via `uvicorn app.main:app`.
              <button
                type="button"
                className="btn-secondary"
                onClick={checkHealth}
                style={{ marginLeft: '12px', padding: '2px 8px', fontSize: '11px' }}
              >
                Retry
              </button>
            </div>
          )}

          {/* User Portal Views */}
          {activePortal === 'user' && (
            <>
              {activePage === 'find' && (
                <FindStations
                  userCoords={userCoords}
                  setUserCoords={setUserCoords}
                  locationStatus={locationStatus}
                  setLocationStatus={setLocationStatus}
                  onSelectStation={handleSelectStation}
                />
              )}

              {activePage === 'station-details' && (
                selectedStation ? (
                  <StationDetails
                    station={selectedStation}
                    userCoords={userCoords}
                    userToken={token}
                    onBackToStations={() => navigateTo('find', 'user')}
                    onRequireLogin={() => navigateTo('user-login', 'user')}
                    onNavigateToMyBookings={() => navigateTo('my-bookings', 'user')}
                  />
                ) : (
                  <div className="card" style={{ textAlign: 'center', padding: '32px' }}>
                    <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '8px' }}>
                      No Station Selected
                    </h3>
                    <p style={{ fontSize: '13px', marginBottom: '16px' }}>
                      Please select a fuel station to view verified details, queue analytics, and available slots.
                    </p>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => navigateTo('find', 'user')}
                    >
                      ← Go to Find Stations
                    </button>
                  </div>
                )
              )}

              {activePage === 'my-bookings' && (
                <MyBookings
                  userToken={token}
                  onRequireLogin={() => navigateTo('user-login', 'user')}
                />
              )}

              {activePage === 'help' && <Help />}

              {activePage === 'user-login' && (
                <UserAuth
                  onAuthSuccess={handleLoginSuccess}
                  onSwitchToOperatorLogin={() => navigateTo('operator-login', 'operator')}
                />
              )}
            </>
          )}

          {/* Operator / Staff Portal Views */}
          {activePortal === 'operator' && (
            <>
              {activePage === 'operator-login' && (
                <OperatorAuth
                  onAuthSuccess={handleLoginSuccess}
                  onSwitchToUserLogin={() => navigateTo('user-login', 'user')}
                />
              )}

              {activePage === 'operator-portal' && (
                role === 'user' ? (
                  <AccessDenied
                    username={username}
                    role={role}
                    onReturnToUserFlow={() => navigateTo('find', 'user')}
                  />
                ) : (
                  <OperatorPortal
                    token={token}
                    username={username}
                    role={role}
                    onAuthSuccess={handleLoginSuccess}
                    onLogout={handleLogout}
                    onReturnToUserFlow={() => navigateTo('find', 'user')}
                  />
                )
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
