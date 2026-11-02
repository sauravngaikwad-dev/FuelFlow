import { useState } from 'react';

interface UserAuthProps {
  onAuthSuccess: (token: string, username: string, role: string) => void;
  onSwitchToOperatorLogin: () => void;
}

export function UserAuth({ onAuthSuccess, onSwitchToOperatorLogin }: UserAuthProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setLoading(true);

    const endpoint =
      mode === 'register'
        ? 'http://127.0.0.1:8000/api/auth/user/register'
        : 'http://127.0.0.1:8000/api/auth/user/login';

    const payload =
      mode === 'register'
        ? { username, email, password }
        : { username, password };

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
    <div className="card" style={{ maxWidth: '480px', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <span className="tag-badge">Customer Account</span>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>
          {mode === 'login' ? 'User Sign In' : 'Create User Account'}
        </h2>
      </div>

      <p style={{ fontSize: '13px', marginBottom: '16px' }}>
        Sign in to book refueling slots and manage your vehicle reservations.
      </p>

      {/* Mode Toggle */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button
          type="button"
          className={mode === 'login' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => {
            setMode('login');
            setErrorMessage(null);
          }}
          style={{ flex: 1 }}
        >
          Sign In
        </button>
        <button
          type="button"
          className={mode === 'register' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => {
            setMode('register');
            setErrorMessage(null);
          }}
          style={{ flex: 1 }}
        >
          Register
        </button>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
            Username {mode === 'login' ? 'or Email' : ''}:
          </label>
          <input
            type="text"
            required
            className="input-field"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. john_doe"
          />
        </div>

        {mode === 'register' && (
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
              Email Address:
            </label>
            <input
              type="email"
              required
              className="input-field"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. john@example.com"
            />
          </div>
        )}

        <div>
          <label style={{ display: 'block', fontSize: '13px', fontWeight: 600 }}>
            Password (min 8 characters):
          </label>
          <input
            type="password"
            required
            minLength={8}
            className="input-field"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {errorMessage && (
          <div className="notice-box" style={{ border: '1px solid #303030' }}>
            <strong>Error:</strong> {errorMessage}
          </div>
        )}

        <button
          type="submit"
          className="btn-primary"
          disabled={loading}
          style={{ marginTop: '8px' }}
        >
          {loading ? 'Processing...' : mode === 'login' ? 'Sign In as User' : 'Register Customer Account'}
        </button>
      </form>

      <div style={{ marginTop: '20px', paddingTop: '12px', borderTop: '1px solid #E8E8E8', fontSize: '12px' }}>
        Station manager or staff?{' '}
        <button
          type="button"
          onClick={onSwitchToOperatorLogin}
          style={{
            background: 'none',
            border: 'none',
            textDecoration: 'underline',
            cursor: 'pointer',
            fontWeight: 600,
            color: '#303030',
          }}
        >
          Sign in to Operator Portal →
        </button>
      </div>
    </div>
  );
}
