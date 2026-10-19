import React, { useEffect, useState } from 'react';
import {
  Sparkles,
  BookOpen,
  Bot,
  Layers,
  BarChart3,
  Download,
  CheckCircle2,
  Clock,
  ArrowRight,
  HardDrive,
  Smile,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api';

export default function DashboardPage({ onNavigate }) {
  const [diagnostics, setDiagnostics] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    try {
      const [diagData, jobsData] = await Promise.all([
        api('/api/admin/diagnostics').catch(() => null),
        api('/api/admin/jobs/recent?limit=8').catch(() => ({ jobs: [] })),
      ]);
      if (diagData) setDiagnostics(diagData);
      if (jobsData?.jobs) setRecentJobs(jobsData.jobs);
    } catch (err) {
      console.warn('Dashboard fetch warning:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  return (
    <div className="admin-page">
      {/* Top Banner / Welcome */}
      <div className="admin-hero-banner">
        <div className="hero-content">
          <div className="admin-kicker-pill">
            <Sparkles size={14} /> Admin overview
          </div>
          <h1>Welcome back</h1>
          <p className="lead" style={{ margin: 0 }}>
            See how many books were made, which picture model is on, and the latest jobs.
          </p>
        </div>

        <button
          type="button"
          className="admin-btn-glass"
          onClick={handleRefresh}
          disabled={refreshing}
          title="Refresh stats"
        >
          <RefreshCw size={16} className={refreshing ? 'spin-animation' : ''} />
          <span>{refreshing ? 'Refreshing…' : 'Refresh'}</span>
        </button>
      </div>

      {/* Radiant Metric Stat Cards */}
      <div className="admin-stat-grid">
        {/* Stat 1: Total Workbooks */}
        <div className="admin-vibrant-card card-gradient-indigo">
          <div className="vibrant-card-header">
            <span className="card-kicker">BOOKS MADE</span>
            <div className="card-icon-bubble">
              <BookOpen size={20} color="#818cf8" />
            </div>
          </div>
          <div className="vibrant-num">{diagnostics?.storage?.completed_pdfs ?? 0}</div>
          <div className="vibrant-desc">
            Printable PDFs across {diagnostics?.assets?.grades_count ?? 1} school years
          </div>
          <div className="card-micro-tag" onClick={() => onNavigate?.('pdfs')}>
            <span>View books</span>
            <ArrowRight size={13} />
          </div>
        </div>

        {/* Stat 2: Active AI Model */}
        <div className="admin-vibrant-card card-gradient-fuchsia">
          <div className="vibrant-card-header">
            <span className="card-kicker">PICTURE MODEL</span>
            <div className="card-icon-bubble">
              <Bot size={20} color="#f472b6" />
            </div>
          </div>
          <div className="vibrant-num" style={{ fontSize: '1.45rem', letterSpacing: '-0.02em', lineHeight: 1.2 }}>
            {diagnostics?.active_model?.model_name || 'GPT Image 2'}
          </div>
          <div className="vibrant-desc">
            Provider: <strong>{diagnostics?.active_model?.provider_name || 'OpenRouter'}</strong> · {diagnostics?.active_model?.cost_per_call || '$0.04/call'}
          </div>
          <div className="card-micro-tag" onClick={() => onNavigate?.('models')}>
            <span>Change model</span>
            <ArrowRight size={13} />
          </div>
        </div>

        {/* Stat 3: Personalization Assets */}
        <div className="admin-vibrant-card card-gradient-emerald">
          <div className="vibrant-card-header">
            <span className="card-kicker">PICTURES & ICONS</span>
            <div className="card-icon-bubble">
              <Smile size={20} color="#34d399" />
            </div>
          </div>
          <div className="vibrant-num">
            {(diagnostics?.assets?.food_icons || 54) + (diagnostics?.assets?.character_badges || 16)}
          </div>
          <div className="vibrant-desc">
            {diagnostics?.assets?.food_icons || 54} Food Icons · {diagnostics?.assets?.character_badges || 16} Characters · {diagnostics?.assets?.pets || 4} Pets
          </div>
          <div className="card-micro-tag" onClick={() => onNavigate?.('assets')}>
            <span>Browse pictures</span>
            <ArrowRight size={13} />
          </div>
        </div>

        {/* Stat 4: Stems Bank */}
        <div className="admin-vibrant-card card-gradient-amber">
          <div className="vibrant-card-header">
            <span className="card-kicker">QUESTIONS</span>
            <div className="card-icon-bubble">
              <Layers size={20} color="#fbbf24" />
            </div>
          </div>
          <div className="vibrant-num">{diagnostics?.assets?.total_stems ?? 18}</div>
          <div className="vibrant-desc">
            Ready maths questions across the school years
          </div>
          <div className="card-micro-tag" onClick={() => onNavigate?.('stems')}>
            <span>Edit questions</span>
            <ArrowRight size={13} />
          </div>
        </div>
      </div>

      {/* Quick Launchpad & Health Indicator */}
      <div className="admin-grid-split" style={{ marginTop: '22px' }}>
        {/* Left Column: Quick Action Launchpad */}
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <h3>Quick links</h3>
            <span className="card-pill-tag">Shortcuts</span>
          </div>
          <p style={{ color: '#94a3b8', fontSize: '0.88rem', margin: '0 0 16px 0' }}>
            Jump to the pages you use most.
          </p>

          <div className="launchpad-grid">
            <button
              type="button"
              className="launchpad-btn"
              onClick={() => onNavigate?.('models')}
            >
              <div className="launchpad-icon" style={{ background: 'rgba(99, 102, 241, 0.2)', color: '#818cf8' }}>
                <Bot size={20} />
              </div>
              <div className="launchpad-text">
                <strong>Image models</strong>
                <small>Change the picture engine and API keys</small>
              </div>
              <ArrowRight size={16} className="launchpad-arrow" />
            </button>

            <button
              type="button"
              className="launchpad-btn"
              onClick={() => onNavigate?.('prompts')}
            >
              <div className="launchpad-icon" style={{ background: 'rgba(236, 72, 153, 0.2)', color: '#f472b6' }}>
                <Sparkles size={20} />
              </div>
              <div className="launchpad-text">
                <strong>Picture prompts</strong>
                <small>Edit how the drawings are described</small>
              </div>
              <ArrowRight size={16} className="launchpad-arrow" />
            </button>

            <button
              type="button"
              className="launchpad-btn"
              onClick={() => onNavigate?.('assets')}
            >
              <div className="launchpad-icon" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399' }}>
                <Smile size={20} />
              </div>
              <div className="launchpad-text">
                <strong>Pictures & icons</strong>
                <small>Foods, characters and pet pictures</small>
              </div>
              <ArrowRight size={16} className="launchpad-arrow" />
            </button>

            <button
              type="button"
              className="launchpad-btn"
              onClick={() => onNavigate?.('diagnostics')}
            >
              <div className="launchpad-icon" style={{ background: 'rgba(245, 158, 11, 0.2)', color: '#fbbf24' }}>
                <HardDrive size={20} />
              </div>
              <div className="launchpad-text">
                <strong>System check</strong>
                <small>Storage, keys and server status</small>
              </div>
              <ArrowRight size={16} className="launchpad-arrow" />
            </button>
          </div>
        </div>

        {/* Right Column: AI & Engine Status Overview */}
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <h3>Connections</h3>
            <span className="card-pill-tag tag-success">Online</span>
          </div>

          <div className="pipeline-connectivity-list">
            <div className="connectivity-item">
              <div className="conn-status-dot dot-green" />
              <div className="conn-info">
                <strong>App server</strong>
                <small>Python {diagnostics?.server?.python_version || '3.x'} on {diagnostics?.server?.os || 'System'}</small>
              </div>
              <span className="conn-badge">Online</span>
            </div>

            <div className="connectivity-item">
              <div className={`conn-status-dot ${diagnostics?.keys?.openrouter ? 'dot-green' : 'dot-amber'}`} />
              <div className="conn-info">
                <strong>OpenRouter</strong>
                <small>Used to draw the pictures</small>
              </div>
              <span className={`conn-badge ${diagnostics?.keys?.openrouter ? 'badge-active' : 'badge-warn'}`}>
                {diagnostics?.keys?.openrouter ? 'Configured' : 'No Key'}
              </span>
            </div>

            <div className="connectivity-item">
              <div className={`conn-status-dot ${diagnostics?.server?.rembg_available ? 'dot-green' : 'dot-amber'}`} />
              <div className="conn-info">
                <strong>Photo background tool</strong>
                <small>Cuts the person out of the photo</small>
              </div>
              <span className="conn-badge">
                {diagnostics?.server?.rembg_available ? 'Installed' : 'Pillow Fallback'}
              </span>
            </div>

            <div className="connectivity-item">
              <div className="conn-status-dot dot-green" />
              <div className="conn-info">
                <strong>Saved books & photos</strong>
                <small>{diagnostics?.storage?.storage_mb ?? 0} MB across {diagnostics?.storage?.total_jobs ?? 0} jobs</small>
              </div>
              <span className="conn-badge">Normal</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Workbooks Production Feed */}
      <div className="admin-card card-glass-glow" style={{ marginTop: '22px' }}>
        <div className="admin-card-header-bar">
          <div>
            <h3>Recent books</h3>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: '4px 0 0 0' }}>
              The latest books created by parents.
            </p>
          </div>
          <button
            type="button"
            className="admin-btn ghost"
            style={{ fontSize: '0.82rem', padding: '6px 12px' }}
            onClick={() => onNavigate?.('pdfs')}
          >
            <span>See all books</span>
            <BarChart3 size={14} />
          </button>
        </div>

        {recentJobs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
            <BookOpen size={40} style={{ opacity: 0.4, marginBottom: '8px' }} />
            <p>No books yet. Create one from the book maker.</p>
          </div>
        ) : (
          <div className="admin-table-wrap" style={{ marginTop: '12px' }}>
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Child Name</th>
                  <th>School year</th>
                  <th>Topics</th>
                  <th>Questions</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Download</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((job) => (
                  <tr key={job.job_id}>
                    <td>
                      <strong style={{ color: '#fff' }}>{job.student_name}</strong>
                      <div style={{ fontSize: '0.74rem', color: '#64748b' }}>{job.job_id}</div>
                    </td>
                    <td>
                      <span className="badge-grade">{job.grade_display || job.grade_id || 'Grade 1'}</span>
                    </td>
                    <td>
                      <div style={{ maxWidth: '240px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {job.selected_topics && job.selected_topics.length > 0
                          ? job.selected_topics.join(', ')
                          : 'General Practice'}
                      </div>
                    </td>
                    <td>
                      <strong>{job.total_questions}</strong> pages
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem' }}>
                        <Clock size={13} color="#94a3b8" />
                        <span>{(job.completed_at || '').slice(0, 16).replace('T', ' ')}</span>
                      </div>
                    </td>
                    <td>
                      <span className="badge-status-completed">
                        <CheckCircle2 size={12} />
                        <span>{job.status}</span>
                      </span>
                    </td>
                    <td>
                      {job.has_pdf && job.pdf_url ? (
                        <a
                          href={job.pdf_url}
                          download={job.pdf_filename}
                          className="btn-table-download"
                          title="Download PDF"
                        >
                          <Download size={14} />
                          <span>PDF</span>
                        </a>
                      ) : (
                        <span style={{ color: '#64748b', fontSize: '0.8rem' }}>Processing</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
