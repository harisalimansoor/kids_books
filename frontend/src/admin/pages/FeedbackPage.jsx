import React, { useEffect, useState } from 'react';
import { Mail, Send, Sparkles } from 'lucide-react';
import { api } from '../api';

export default function FeedbackPage() {
  const [items, setItems] = useState([]);
  const [settings, setSettings] = useState(null);
  const [preview, setPreview] = useState('');
  const [smtp, setSmtp] = useState({ host: '', port: 587, user: '', password: '', from_email: 'support@myintelibooks.com', from_name: 'MyInteliBooks', use_tls: true });
  const [imap, setImap] = useState({ host: '', port: 993, user: 'support@myintelibooks.com', password: '', enabled: false });
  const [delay, setDelay] = useState(48);
  const [baseUrl, setBaseUrl] = useState('http://localhost:5173');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = () => {
    api('/api/admin/feedback').then((d) => setItems(d.items || [])).catch((e) => setErr(e.message));
    api('/api/admin/settings').then((s) => {
      setSettings(s);
      setSmtp({ ...smtp, ...(s.smtp || {}) });
      setImap({ ...imap, ...(s.imap || {}) });
      setDelay(s.feedback_delay_hours || 48);
      setBaseUrl(s.public_base_url || 'http://localhost:5173');
    }).catch((e) => setErr(e.message));
    api('/api/admin/feedback/preview').then((d) => setPreview(d.html || '')).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const saveSettings = async () => {
    try {
      await api('/api/admin/settings', {
        method: 'PUT',
        body: {
          feedback_delay_hours: Number(delay),
          public_base_url: baseUrl,
          support_email: 'support@myintelibooks.com',
          smtp,
          imap,
        },
      });
      setMsg('Feedback mail settings saved.');
    } catch (e) {
      setErr(e.message);
    }
  };

  const sendNow = async (token) => {
    try {
      await api(`/api/admin/feedback/${token}/send-now`, { method: 'POST' });
      setMsg('Feedback email sent.');
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <div className="admin-page">
      <h1>Parent feedback</h1>
      <p className="lead">
        After a parent types their email to download a book, we wait a few days and
        send a short note from <strong>support@myintelibooks.com</strong>.
        Replies show up here.
      </p>

      <div className="admin-grid">
        <div className="admin-card">
          <h2>
            <Mail size={16} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Mail settings
          </h2>
          <label className="admin-label">Delay before feedback email (hours)</label>
          <input className="admin-input" type="number" min="1" value={delay} onChange={(e) => setDelay(e.target.value)} />
          <p style={{ color: '#64748b', fontSize: '0.8rem', margin: '6px 0 12px' }}>
            48 hours = 2 days · 72 hours = 3 days
          </p>
          <label className="admin-label">Public site URL (used in the email button)</label>
          <input className="admin-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          <div className="admin-grid" style={{ marginTop: 12 }}>
            <div>
              <label className="admin-label">SMTP host</label>
              <input className="admin-input" value={smtp.host} onChange={(e) => setSmtp({ ...smtp, host: e.target.value })} />
            </div>
            <div>
              <label className="admin-label">SMTP port</label>
              <input className="admin-input" value={smtp.port} onChange={(e) => setSmtp({ ...smtp, port: Number(e.target.value) })} />
            </div>
            <div>
              <label className="admin-label">SMTP user</label>
              <input className="admin-input" value={smtp.user} onChange={(e) => setSmtp({ ...smtp, user: e.target.value })} />
            </div>
            <div>
              <label className="admin-label">SMTP password</label>
              <input className="admin-input" type="password" value={smtp.password} onChange={(e) => setSmtp({ ...smtp, password: e.target.value })} />
            </div>
          </div>
          <label className="admin-label" style={{ marginTop: 12 }}>From email</label>
          <input className="admin-input" value={smtp.from_email} onChange={(e) => setSmtp({ ...smtp, from_email: e.target.value })} />
          <div style={{ marginTop: 14 }}>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#cbd5e1' }}>
              <input
                type="checkbox"
                checked={!!imap.enabled}
                onChange={(e) => setImap({ ...imap, enabled: e.target.checked })}
              />
              Ingest replies from support@myintelibooks.com via IMAP
            </label>
          </div>
          {imap.enabled && (
            <div className="admin-grid" style={{ marginTop: 10 }}>
              <div>
                <label className="admin-label">IMAP host</label>
                <input className="admin-input" value={imap.host} onChange={(e) => setImap({ ...imap, host: e.target.value })} />
              </div>
              <div>
                <label className="admin-label">IMAP user</label>
                <input className="admin-input" value={imap.user} onChange={(e) => setImap({ ...imap, user: e.target.value })} />
              </div>
              <div>
                <label className="admin-label">IMAP password</label>
                <input className="admin-input" type="password" value={imap.password} onChange={(e) => setImap({ ...imap, password: e.target.value })} />
              </div>
            </div>
          )}
          <button type="button" className="admin-btn" style={{ marginTop: 14 }} onClick={saveSettings}>
            Save mail settings
          </button>
          {settings && (
            <p style={{ color: settings.smtp_configured ? '#6ee7b7' : '#fbbf24', marginTop: 10, fontSize: '0.84rem' }}>
              {settings.smtp_configured
                ? 'SMTP looks configured — due emails will send automatically.'
                : 'Add SMTP details so the 2–3 day follow-up can actually send.'}
            </p>
          )}
        </div>

        <div className="admin-card">
          <h2>
            <Sparkles size={16} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            Email design preview
          </h2>
          <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: 10 }}>
            Motion-friendly HTML with floating book, sparkles, and a gradient CTA.
            Sent from support@myintelibooks.com with Reply-To set to the same inbox.
          </p>
          <div className="fb-hero">
            {preview ? <iframe title="Feedback email preview" srcDoc={preview} /> : <p style={{ padding: 24 }}>Loading preview…</p>}
          </div>
        </div>
      </div>

      <div className="admin-card">
        <h2>Inbox ({items.length})</h2>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Email</th>
                <th>Child</th>
                <th>Grade</th>
                <th>Scheduled / sent</th>
                <th>Reply</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id || it.token}>
                  <td>{it.status}</td>
                  <td>{it.email}</td>
                  <td>{it.student_name}</td>
                  <td>{it.grade_display || it.grade_id}</td>
                  <td>{(it.sent_at || it.scheduled_at || '').slice(0, 16).replace('T', ' ')}</td>
                  <td>
                    {it.rating ? `${it.rating}/5 · ` : ''}
                    {(it.message || it.reply_body || '').slice(0, 80)}
                  </td>
                  <td>
                    {it.status === 'scheduled' && it.token && (
                      <button type="button" className="admin-btn ghost" onClick={() => sendNow(it.token)}>
                        <Send size={14} /> Send now
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {msg && <div className="admin-toast">{msg}</div>}
      {err && <div className="admin-toast err">{err}</div>}
    </div>
  );
}
