interface AccessDeniedProps {
  username?: string | null;
  role?: string | null;
  onReturnToUserFlow: () => void;
}

export function AccessDenied({ username, role, onReturnToUserFlow }: AccessDeniedProps) {
  return (
    <div className="card" style={{ border: '2px solid #303030', padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span className="tag-badge">Access Denied</span>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>403 - Forbidden</h2>
      </div>

      <p style={{ fontSize: '14px', lineHeight: 1.6, marginTop: '12px' }}>
        Your account {username ? <strong>"{username}"</strong> : ''}{' '}
        has standard customer privileges {role ? `(role: ${role})` : ''} and is strictly prohibited from accessing
        station operator configurations, camera controls, or administrative endpoints.
      </p>

      <div className="notice-box" style={{ marginTop: '16px' }}>
        <strong>Security Policy:</strong> Operator and administrator functions require verified staff credentials.
        All API requests are validated server-side using cryptographically signed role tokens.
      </div>

      <button
        type="button"
        className="btn-primary"
        onClick={onReturnToUserFlow}
        style={{ marginTop: '16px' }}
      >
        Return to User Portal
      </button>
    </div>
  );
}
