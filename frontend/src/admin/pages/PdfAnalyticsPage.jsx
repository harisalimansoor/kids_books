import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api';

const MONTHS = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function Bars({ data }) {
  const entries = Object.entries(data || {});
  const max = Math.max(1, ...entries.map(([, n]) => n));
  if (!entries.length) return <p style={{ color: '#64748b' }}>No data yet.</p>;
  return (
    <div>
      {entries.sort((a, b) => b[1] - a[1]).map(([label, n]) => (
        <div key={label} style={{ marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem' }}>
            <span>{label}</span>
            <strong>{n}</strong>
          </div>
          <div className="admin-bar"><span style={{ width: `${(n / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

export default function PdfAnalyticsPage() {
  const [grades, setGrades] = useState([]);
  const [filters, setFilters] = useState({
    name: '',
    month: '',
    year: '',
    grade: '',
    num_questions: '',
    gender: '',
    location: '',
  });
  const [applied, setApplied] = useState(filters);
  const [data, setData] = useState({ pdfs: [], summary: {}, count: 0 });
  const [err, setErr] = useState('');

  useEffect(() => {
    api('/api/admin/grades').then((d) => setGrades(d.grades || [])).catch(() => {});
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    Object.entries(applied).forEach(([k, v]) => {
      if (v) params.set(k, v);
    });
    api(`/api/admin/pdfs?${params.toString()}`)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [applied]);

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const summary = data.summary || {};
  const years = useMemo(() => {
    const y = new Set((data.pdfs || []).map((p) => p.year).filter(Boolean));
    const now = new Date().getFullYear();
    y.add(now);
    return [...y].sort((a, b) => b - a);
  }, [data.pdfs]);

  return (
    <div className="admin-page">
      <h1>Created books</h1>
      <p className="lead">
        How many books were made, for which school years and topics, and where they came from.
      </p>

      <div className="admin-card">
        <div className="admin-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          <div>
            <label className="admin-label">Name / job</label>
            <input className="admin-input" value={filters.name} onChange={(e) => set('name', e.target.value)} />
          </div>
          <div>
            <label className="admin-label">Month</label>
            <select className="admin-select" value={filters.month} onChange={(e) => set('month', e.target.value)}>
              <option value="">All</option>
              {MONTHS.slice(1).map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="admin-label">Year</label>
            <select className="admin-select" value={filters.year} onChange={(e) => set('year', e.target.value)}>
              <option value="">All</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div>
            <label className="admin-label">Grade</label>
            <select className="admin-select" value={filters.grade} onChange={(e) => set('grade', e.target.value)}>
              <option value="">All</option>
              {grades.map((g) => <option key={g.id} value={g.id}>{g.display_name}</option>)}
            </select>
          </div>
          <div>
            <label className="admin-label"># Questions</label>
            <input className="admin-input" value={filters.num_questions} onChange={(e) => set('num_questions', e.target.value)} />
          </div>
          <div>
            <label className="admin-label">Gender</label>
            <select className="admin-select" value={filters.gender} onChange={(e) => set('gender', e.target.value)}>
              <option value="">All</option>
              <option>Boy</option>
              <option>Girl</option>
              <option>Other</option>
            </select>
          </div>
          <div>
            <label className="admin-label">Location</label>
            <input className="admin-input" value={filters.location} onChange={(e) => set('location', e.target.value)} />
          </div>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <button type="button" className="admin-btn" onClick={() => setApplied({ ...filters })}>Apply filters</button>
          <button
            type="button"
            className="admin-btn ghost"
            onClick={() => {
              const empty = { name: '', month: '', year: '', grade: '', num_questions: '', gender: '', location: '' };
              setFilters(empty);
              setApplied(empty);
            }}
          >
            Reset
          </button>
        </div>
      </div>

      <div className="admin-grid">
        <div className="admin-stat">
          <div className="num">{summary.total_pdfs || 0}</div>
          <div className="lbl">PDFs generated</div>
        </div>
        <div className="admin-stat">
          <div className="num">{summary.most_generated_gender || '—'}</div>
          <div className="lbl">Most generated gender</div>
        </div>
        <div className="admin-stat">
          <div className="num" style={{ fontSize: '1.2rem' }}>{summary.most_generated_location || '—'}</div>
          <div className="lbl">Most generated location</div>
        </div>
        <div className="admin-stat">
          <div className="num">{Object.keys(summary.by_grade || {}).length}</div>
          <div className="lbl">Grades with PDFs</div>
        </div>
      </div>

      <div className="admin-grid" style={{ marginTop: 16 }}>
        <div className="admin-card">
          <h3>PDFs by grade</h3>
          <Bars data={summary.by_grade} />
        </div>
        <div className="admin-card">
          <h3>Questions per generated PDF</h3>
          <Bars data={summary.by_question_count} />
        </div>
        <div className="admin-card">
          <h3>Topics used</h3>
          <Bars data={summary.by_topic} />
        </div>
        <div className="admin-card">
          <h3>Gender mix</h3>
          <Bars data={summary.by_gender} />
        </div>
        <div className="admin-card">
          <h3>Locations</h3>
          <Bars data={summary.by_location} />
        </div>
        <div className="admin-card">
          <h3>By month</h3>
          <Bars data={summary.by_month} />
        </div>
      </div>

      <div className="admin-table-wrap" style={{ marginTop: 16 }}>
        <table className="admin-table">
          <thead>
            <tr>
              <th>Child</th>
              <th>Grade</th>
              <th>Questions</th>
              <th>Topics</th>
              <th>Gender</th>
              <th>Location</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {(data.pdfs || []).map((p) => (
              <tr key={p.job_id}>
                <td>{p.student_name || p.job_id}</td>
                <td>{p.grade_display}</td>
                <td>{p.question_count}</td>
                <td>{(p.topics || []).join(', ')}</td>
                <td>{p.gender}</td>
                <td>{p.location || '—'}</td>
                <td>{(p.created_at || '').slice(0, 16).replace('T', ' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {err && <div className="admin-toast err">{err}</div>}
    </div>
  );
}
