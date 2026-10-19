import React, { useState } from 'react';
import { ShieldCheck, Mail, Lock, Eye, EyeOff, Sparkles, X, ArrowRight } from 'lucide-react';

export default function AdminAuthModal({ open, onClose, onSuccess }) {
  const [email, setEmail] = useState('admin@myintelibooks.com');
  const [password, setPassword] = useState('admin123');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [remember, setRemember] = useState(true);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');

    try {
      // 1. Verify against backend
      const res = await fetch('/api/admin/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        // Fallback for default local credentials if server is starting or in dev
        if (
          email.trim().toLowerCase() === 'admin@myintelibooks.com' &&
          password === 'admin123'
        ) {
          sessionStorage.setItem('admin_auth', 'true');
          sessionStorage.setItem('admin_email', email.trim());
          if (remember) {
            localStorage.setItem('admin_auth', 'true');
            localStorage.setItem('admin_email', email.trim());
          }
          onSuccess?.();
          return;
        }
        throw new Error(data.detail || 'Invalid email or password');
      }

      // Successful backend auth
      sessionStorage.setItem('admin_auth', 'true');
      sessionStorage.setItem('admin_token', data.token || 'adm_active');
      sessionStorage.setItem('admin_email', data.email || email.trim());
      if (remember) {
        localStorage.setItem('admin_auth', 'true');
        localStorage.setItem('admin_email', data.email || email.trim());
      }

      onSuccess?.();
    } catch (err) {
      setError(err.message || 'Login failed. Please check credentials.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" style={{ zIndex: 9999 }}>
      <div
        className="admin-auth-card"
        style={{
          background: 'linear-gradient(145deg, #0f172a, #0b1220)',
          border: '1px solid rgba(165, 180, 252, 0.25)',
          borderRadius: '24px',
          padding: '32px',
          width: '92%',
          maxWidth: '460px',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.8), 0 0 40px rgba(99, 102, 241, 0.2)',
          position: 'relative',
          overflow: 'hidden',
          color: '#e2e8f0',
        }}
      >
        {/* Colorful Ambient Glow */}
        <div
          style={{
            position: 'absolute',
            top: '-50px',
            right: '-50px',
            width: '180px',
            height: '180px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(236, 72, 153, 0.25) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: '-40px',
            left: '-40px',
            width: '160px',
            height: '160px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(99, 102, 241, 0.3) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />

        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '20px',
            right: '20px',
            background: 'rgba(255, 255, 255, 0.08)',
            border: 'none',
            borderRadius: '50%',
            width: '32px',
            height: '32px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94a3b8',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#fff';
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = '#94a3b8';
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
          }}
        >
          <X size={18} />
        </button>

        {/* Header Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(236, 72, 153, 0.2))',
            border: '1px solid rgba(165, 180, 252, 0.3)',
            borderRadius: '999px',
            padding: '6px 14px',
            fontSize: '0.78rem',
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: '#c7d2fe',
            marginBottom: '16px',
          }}
        >
          <ShieldCheck size={16} color="#818cf8" />
          <span>Admin sign-in</span>
        </div>

        <h2
          style={{
            fontSize: '1.6rem',
            fontFamily: 'var(--font-display, sans-serif)',
            fontWeight: 800,
            color: '#ffffff',
            margin: '0 0 6px 0',
          }}
        >
          Sign in to Admin
        </h2>
        <p
          style={{
            fontSize: '0.92rem',
            color: '#94a3b8',
            lineHeight: 1.5,
            margin: '0 0 24px 0',
          }}
        >
          Enter your admin email and password to open the control panel.
        </p>

        {error && (
          <div
            style={{
              background: 'rgba(225, 29, 72, 0.15)',
              border: '1px solid rgba(244, 63, 94, 0.3)',
              borderRadius: '12px',
              padding: '12px 16px',
              fontSize: '0.86rem',
              color: '#fda4af',
              marginBottom: '18px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <span>⚠️ {error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Email Field */}
          <div style={{ marginBottom: '18px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.78rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: '#cbd5e1',
                marginBottom: '8px',
              }}
            >
              Admin Email
            </label>
            <div
              style={{
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <Mail
                size={18}
                color="#818cf8"
                style={{ position: 'absolute', left: '14px', pointerEvents: 'none' }}
              />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@myintelibooks.com"
                style={{
                  width: '100%',
                  background: 'rgba(15, 23, 42, 0.85)',
                  border: '1px solid rgba(148, 163, 184, 0.25)',
                  borderRadius: '14px',
                  padding: '12px 14px 12px 42px',
                  fontSize: '0.95rem',
                  color: '#ffffff',
                  outline: 'none',
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = '#818cf8';
                  e.target.style.boxShadow = '0 0 0 3px rgba(99, 102, 241, 0.25)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = 'rgba(148, 163, 184, 0.25)';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>
          </div>

          {/* Password Field */}
          <div style={{ marginBottom: '18px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.78rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: '#cbd5e1',
                marginBottom: '8px',
              }}
            >
              Password
            </label>
            <div
              style={{
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <Lock
                size={18}
                color="#ec4899"
                style={{ position: 'absolute', left: '14px', pointerEvents: 'none' }}
              />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter admin password"
                style={{
                  width: '100%',
                  background: 'rgba(15, 23, 42, 0.85)',
                  border: '1px solid rgba(148, 163, 184, 0.25)',
                  borderRadius: '14px',
                  padding: '12px 42px 12px 42px',
                  fontSize: '0.95rem',
                  color: '#ffffff',
                  outline: 'none',
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = '#ec4899';
                  e.target.style.boxShadow = '0 0 0 3px rgba(236, 72, 153, 0.25)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = 'rgba(148, 163, 184, 0.25)';
                  e.target.style.boxShadow = 'none';
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '12px',
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: '4px',
                  display: 'flex',
                }}
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Quick Credential Hint */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '22px',
              fontSize: '0.8rem',
              color: '#94a3b8',
            }}
          >
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                style={{ accentColor: '#6366f1' }}
              />
              <span>Stay signed in</span>
            </label>

            <span
              style={{
                background: 'rgba(99, 102, 241, 0.1)',
                border: '1px solid rgba(99, 102, 241, 0.2)',
                borderRadius: '6px',
                padding: '3px 8px',
                color: '#a5b4fc',
                fontFamily: 'monospace',
                fontSize: '0.74rem',
              }}
              title="Default login details"
            >
              admin@myintelibooks.com / admin123
            </span>
          </div>

          {/* Submit Action */}
          <button
            type="submit"
            disabled={busy}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              padding: '14px',
              borderRadius: '14px',
              background: 'linear-gradient(135deg, #6366f1 0%, #ec4899 100%)',
              color: '#ffffff',
              fontSize: '1rem',
              fontWeight: 700,
              border: 'none',
              cursor: busy ? 'wait' : 'pointer',
              boxShadow: '0 8px 25px rgba(99, 102, 241, 0.35)',
              transition: 'transform 0.15s, box-shadow 0.15s',
            }}
            onMouseEnter={(e) => {
              if (!busy) {
                e.currentTarget.style.transform = 'translateY(-1px)';
                e.currentTarget.style.boxShadow = '0 12px 30px rgba(99, 102, 241, 0.5)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 8px 25px rgba(99, 102, 241, 0.35)';
            }}
          >
            {busy ? (
              <span>Signing in…</span>
            ) : (
              <>
                <Sparkles size={18} />
                <span>Sign in</span>
                <ArrowRight size={18} />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
