import React, { useState } from 'react';
import {
  ShieldCheck,
  Lock,
  Mail,
  Key,
  CheckCircle2,
  AlertCircle,
  Save,
  LogOut,
} from 'lucide-react';
import { api } from '../api';

export default function SecurityPage({ onLogout }) {
  const [email, setEmail] = useState(
    localStorage.getItem('admin_email') || 'admin@myintelibooks.com'
  );
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const handleUpdateCredentials = async (e) => {
    e.preventDefault();
    if (newPassword && newPassword !== confirmPassword) {
      setToast({ type: 'err', msg: 'New password and confirmation do not match.' });
      return;
    }

    setBusy(true);
    setToast(null);

    try {
      const res = await api('/api/admin/auth/change', {
        method: 'POST',
        body: JSON.stringify({
          old_password: oldPassword || undefined,
          email: email.trim(),
          password: newPassword || 'admin123',
        }),
      });

      localStorage.setItem('admin_email', email.trim());
      sessionStorage.setItem('admin_email', email.trim());
      setToast({ type: 'ok', msg: res.message || 'Credentials updated successfully!' });
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setToast({ type: 'err', msg: err.message || 'Update failed' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-page">
      <div className="admin-hero-banner">
        <div className="hero-content">
          <div className="admin-kicker-pill">
            <ShieldCheck size={14} /> Login & access
          </div>
          <h1>Admin email and password</h1>
          <p className="lead" style={{ margin: 0 }}>
            Change the login used after a triple-click on the logo.
          </p>
        </div>

        <button
          type="button"
          className="admin-btn danger"
          onClick={onLogout}
          style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <LogOut size={16} />
          <span>Sign out</span>
        </button>
      </div>

      <div className="admin-card card-glass-glow" style={{ maxWidth: '640px' }}>
        <div className="admin-card-header-bar">
          <h3>Update login</h3>
          <span className="card-pill-tag">Security</span>
        </div>

        {toast && (
          <div
            className={`admin-toast ${toast.type}`}
            style={{ marginBottom: '18px' }}
          >
            {toast.msg}
          </div>
        )}

        <form onSubmit={handleUpdateCredentials}>
          <div style={{ marginBottom: '16px' }}>
            <label className="admin-label">Admin Email</label>
            <input
              type="email"
              required
              className="admin-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@myintelibooks.com"
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label className="admin-label">Current Password (if changing)</label>
            <input
              type="password"
              className="admin-input"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              placeholder="Enter current password (default: admin123)"
            />
          </div>

          <div className="admin-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '20px' }}>
            <div>
              <label className="admin-label">New Password</label>
              <input
                type="password"
                className="admin-input"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="New password (min 4 chars)"
              />
            </div>
            <div>
              <label className="admin-label">Confirm New Password</label>
              <input
                type="password"
                className="admin-input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              type="submit"
              disabled={busy}
              className="admin-btn"
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <Save size={16} />
              <span>{busy ? 'Saving…' : 'Save login'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
