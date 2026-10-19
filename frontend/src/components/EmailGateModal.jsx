import React, { useState } from 'react';
import { Mail, Download, Sparkles, X, CheckCircle2 } from 'lucide-react';

export default function EmailGateModal({ open, filename, jobId, pdfUrl, onClose, onDownloaded }) {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [downloaded, setDownloaded] = useState(false);

  if (!open) return null;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await fetch(`/api/jobs/${jobId}/claim-download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Could not start download');
      const link = document.createElement('a');
      link.href = data.pdf_url || pdfUrl;
      link.download = filename || 'MyInteliBooks_Workbook.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setDownloaded(true);
      if (onDownloaded) onDownloaded();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleClose = () => {
    setDownloaded(false);
    onClose();
  };

  return (
    <div className="modal-overlay" style={{ zIndex: 90 }}>
      <div className="email-gate-card">
        <button
          type="button"
          className="email-gate-close"
          onClick={handleClose}
          title="Close window"
          aria-label="Close"
        >
          <X size={18} />
        </button>

        <div className="email-gate-orb" />

        {downloaded ? (
          <div style={{ textAlign: 'center', padding: '16px 8px 8px' }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: '#ecfdf5',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px auto',
              border: '2px solid #a7f3d0',
            }}>
              <CheckCircle2 size={36} color="#059669" />
            </div>
            <h2 style={{ fontSize: '1.45rem', marginBottom: '8px', color: '#0f172a' }}>
              The book is downloading
            </h2>
            <p style={{ color: '#64748b', fontSize: '0.98rem', lineHeight: '1.5', marginBottom: '24px' }}>
              Check your Downloads folder for the PDF. You can print it at home or take it to a print shop.
            </p>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button
                type="button"
                className="btn-primary"
                onClick={handleClose}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '10px 24px' }}
              >
                <X size={16} />
                <span>Close</span>
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit}>
            <div className="email-gate-kicker">
              <Sparkles size={14} /> Last step before download
            </div>
            <h2>Where should we send a short thank-you later?</h2>
            <p>
              Type your email to start the download of{' '}
              <strong>{filename || 'the maths book PDF'}</strong>.
              In a few days we may send one short message from{' '}
              <strong>support@myintelibooks.com</strong> asking if the book helped.
              We do not send adverts.
            </p>
            <label className="form-label">
              <Mail size={15} /> Your email
            </label>
            <input
              type="email"
              className="text-input"
              required
              autoFocus
              placeholder="you@family.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <span className="form-hint">Used only for this download and one follow-up.</span>
            {error && <p className="form-hint" style={{ color: '#e11d48' }}>{error}</p>}
            <div className="email-gate-actions">
              <button type="button" className="btn-secondary" onClick={handleClose}>Not now</button>
              <button type="submit" className="btn-download-pdf" disabled={busy}>
                <Download size={18} />
                {busy ? 'Preparing…' : 'Download the book'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
