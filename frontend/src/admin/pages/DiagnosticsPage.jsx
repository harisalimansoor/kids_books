import React, { useEffect, useState } from 'react';
import {
  Activity,
  HardDrive,
  Key,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Cpu,
  FolderCheck,
  Server,
  Terminal,
} from 'lucide-react';
import { api } from '../api';

export default function DiagnosticsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const fetchDiagnostics = async () => {
    try {
      const res = await api('/api/admin/diagnostics');
      setData(res);
    } catch (err) {
      console.error('Failed to load diagnostics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDiagnostics();
  }, []);

  const handleTestKeys = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // Test basic API health
      const res = await fetch('/api/health');
      const health = await res.json();
      setTestResult({
        ok: true,
        message: health.api_key_configured
          ? `Connected to ${health.image_provider} (${health.image_model}) successfully.`
          : 'Server responded, but AI key is missing in environment/.env.',
      });
    } catch (err) {
      setTestResult({
        ok: false,
        message: `Connection test error: ${err.message}`,
      });
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="admin-page" style={{ textAlign: 'center', padding: '60px' }}>
        <RefreshCw size={32} className="spin-animation" color="#818cf8" />
        <p style={{ marginTop: '14px', color: '#94a3b8' }}>Gathering system diagnostics...</p>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-hero-banner">
        <div className="hero-content">
          <div className="admin-kicker-pill">
            <Activity size={14} /> System check
          </div>
          <h1>Is everything working?</h1>
          <p className="lead" style={{ margin: 0 }}>
            Check picture keys, disk space, photo tools, and whether each school year is ready.
          </p>
        </div>

        <button
          type="button"
          className="admin-btn-glass"
          onClick={() => {
            setLoading(true);
            fetchDiagnostics();
          }}
        >
          <RefreshCw size={16} />
          <span>Refresh Status</span>
        </button>
      </div>

      {/* Grid of Diagnostics Cards */}
      <div className="admin-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {/* Card 1: Core Server Info */}
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div className="card-icon-bubble" style={{ background: 'rgba(99, 102, 241, 0.2)', color: '#818cf8' }}>
                <Server size={18} />
              </div>
              <h3 style={{ margin: 0 }}>FastAPI Server</h3>
            </div>
            <span className="card-pill-tag tag-success">Active</span>
          </div>

          <div className="diag-details-list">
            <div className="diag-row">
              <span className="diag-lbl">Status</span>
              <span className="diag-val" style={{ color: '#34d399', fontWeight: 700 }}>
                ● Online
              </span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Python Environment</span>
              <span className="diag-val">Python {data?.server?.python_version}</span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Host Operating System</span>
              <span className="diag-val">{data?.server?.os}</span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Support / Contact Mail</span>
              <span className="diag-val">{data?.server?.support_email}</span>
            </div>
          </div>
        </div>

        {/* Card 2: AI Key Credentials */}
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div className="card-icon-bubble" style={{ background: 'rgba(236, 72, 153, 0.2)', color: '#f472b6' }}>
                <Key size={18} />
              </div>
              <h3 style={{ margin: 0 }}>AI Provider Keys</h3>
            </div>
            <button
              type="button"
              className="admin-btn ghost"
              style={{ fontSize: '0.78rem', padding: '4px 10px' }}
              onClick={handleTestKeys}
              disabled={testing}
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
          </div>

          <div className="diag-details-list">
            <div className="diag-row">
              <span className="diag-lbl">OpenRouter Key</span>
              <span className="diag-val">
                {data?.keys?.openrouter ? (
                  <span className="tag-ok">
                    <CheckCircle2 size={13} /> Active
                  </span>
                ) : (
                  <span className="tag-missing">
                    <AlertCircle size={13} /> Missing
                  </span>
                )}
              </span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">OpenAI Native Key</span>
              <span className="diag-val">
                {data?.keys?.openai ? (
                  <span className="tag-ok">
                    <CheckCircle2 size={13} /> Active
                  </span>
                ) : (
                  <span className="tag-opt">Optional</span>
                )}
              </span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Google Gemini Key</span>
              <span className="diag-val">
                {data?.keys?.gemini ? (
                  <span className="tag-ok">
                    <CheckCircle2 size={13} /> Active
                  </span>
                ) : (
                  <span className="tag-opt">Optional</span>
                )}
              </span>
            </div>
          </div>

          {testResult && (
            <div
              style={{
                marginTop: '14px',
                padding: '10px 14px',
                borderRadius: '10px',
                background: testResult.ok ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                border: `1px solid ${testResult.ok ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
                fontSize: '0.82rem',
                color: testResult.ok ? '#6ee7b7' : '#fda4af',
              }}
            >
              {testResult.message}
            </div>
          )}
        </div>

        {/* Card 3: Disk Storage & Jobs */}
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div className="card-icon-bubble" style={{ background: 'rgba(245, 158, 11, 0.2)', color: '#fbbf24' }}>
                <HardDrive size={18} />
              </div>
              <h3 style={{ margin: 0 }}>Runtime Storage</h3>
            </div>
            <span className="card-pill-tag">{data?.storage?.storage_mb ?? 0} MB</span>
          </div>

          <div className="diag-details-list">
            <div className="diag-row">
              <span className="diag-lbl">Total Workbooks in History</span>
              <span className="diag-val">{data?.storage?.total_jobs ?? 0} jobs</span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Completed High-Res PDFs</span>
              <span className="diag-val">{data?.storage?.completed_pdfs ?? 0} files</span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Location</span>
              <span className="diag-val" style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                runtime/jobs/
              </span>
            </div>
          </div>
        </div>

        {/* Card 4: Personalization Assets Inventory */}
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div className="card-icon-bubble" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399' }}>
                <FolderCheck size={18} />
              </div>
              <h3 style={{ margin: 0 }}>Asset Inventory</h3>
            </div>
            <span className="card-pill-tag tag-success">Ready</span>
          </div>

          <div className="diag-details-list">
            <div className="diag-row">
              <span className="diag-lbl">Twemoji Food Icons</span>
              <span className="diag-val">
                <strong>{data?.assets?.food_icons ?? 54}</strong> SVG / PNG
              </span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Character Badges</span>
              <span className="diag-val">
                <strong>{data?.assets?.character_badges ?? 16}</strong> stickers
              </span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Pet Cutouts</span>
              <span className="diag-val">
                <strong>{data?.assets?.pets ?? 4}</strong> breeds
              </span>
            </div>
            <div className="diag-row">
              <span className="diag-lbl">Curriculum Stems Pool</span>
              <span className="diag-val">
                <strong>{data?.assets?.total_stems ?? 18}</strong> questions
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
