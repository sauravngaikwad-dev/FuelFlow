import { useState } from 'react';

interface OperatorAuthProps {
  onAuthSuccess: (token: string, username: string, role: string) => void;
  onSwitchToUserLogin: () => void;
}

export function OperatorAuth({ onAuthSuccess, onSwitchToUserLogin }: OperatorAuthProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setLoading(true);

    try {
      const res = await fetch('http://127.0.0.1:8000/api/auth/operator/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed');
      }

      localStorage.setItem('fuelflow_token', data.access_token);
      localStorage.setItem('fuelflow_user', data.username);
      localStorage.setItem('fuelflow_role', data.role);
      onAuthSuccess(data.access_token, data.username, data.role);
    } catch (err: any) {
      setErrorMessage(err.message || 'Network error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card" style={{ maxWidth: '480px', margin: '0 auto', border: '2px solid #303030' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <span className="tag-badge">Staff Access</span>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Operator & Admin Sign In</h2>
      </div>

      <p style={{ fontSize: '13px', marginBottom: '14px' }}>
        Restricted to verified station operators and system administrators.
      </p>

      <div className="notice-box" style={{ fontSize: '12px', marginBottom: '16px' }}>
        <strong>Security Notice:</strong> Public account registration cannot create operator or admin accounts.
        Operators are provisioned securely by the system administrator.
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
            Operator / Admin Username:
          </label>
          <input
            type="text"
            required
            className="input-field"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. station_manager_1 or admin"
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
            Password:
          </label>
          <input
            type="password"
            required
            className="input-field"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {errorMessage && (
          <div className="notice-box" style={{ border: '2px solid #303030' }}>
            <strong>Authentication Error:</strong> {errorMessage}
          </div>
        )}

        <button
          type="submit"
          className="btn-primary"
          disabled={loading}
          style={{ marginTop: '8px' }}
        >
          {loading ? 'Authenticating...' : 'Sign In as Operator / Admin'}
        </button>
      </form>

      <div style={{ marginTop: '20px', paddingTop: '12px', borderTop: '1px solid #E8E8E8', fontSize: '12px' }}>
        Looking for customer refueling?{' '}
        <button
          type="button"
          onClick={onSwitchToUserLogin}
          style={{
            background: 'none',
            border: 'none',
            textDecoration: 'underline',
            cursor: 'pointer',
            fontWeight: 600,
            color: '#303030',
          }}
        >
          ← Return to User Sign In
        </button>
      </div>
    </div>
  );
}
