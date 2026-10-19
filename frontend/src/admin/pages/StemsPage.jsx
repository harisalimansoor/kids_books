import React, { useEffect, useState } from 'react';
import { Pencil, Plus, Save, Search, Trash2 } from 'lucide-react';
import { api } from '../api';

export default function StemsPage() {
  const [grades, setGrades] = useState([]);
  const [gradeId, setGradeId] = useState('Grade_1');
  const [topic, setTopic] = useState('');
  const [bank, setBank] = useState('');
  const [companion, setCompanion] = useState('');
  const [category, setCategory] = useState('');
  const [q, setQ] = useState('');
  const [data, setData] = useState({ stems: [], topics: [], companions: [], categories: [], count: 0 });
  const [editor, setEditor] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ question: '', category: 'counting', metaText: '' });
  const [createForm, setCreateForm] = useState({
    stem_id: '',
    topic: 'addition',
    bank: 'fallback',
    category: 'counting',
    question: '',
    correct: '',
  });
  const [find, setFind] = useState('');
  const [replace, setReplace] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    api('/api/admin/grades').then((d) => setGrades(d.grades || [])).catch((e) => setErr(e.message));
  }, []);

  const load = () => {
    const params = new URLSearchParams();
    if (topic) params.set('topic', topic);
    if (bank) params.set('bank', bank);
    if (companion) params.set('companion', companion);
    if (category) params.set('category', category);
    if (q) params.set('q', q);
    const qs = params.toString();
    api(`/api/admin/stems/${gradeId}${qs ? `?${qs}` : ''}`)
      .then(setData)
      .catch((e) => setErr(e.message));
  };

  useEffect(() => {
    if (gradeId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gradeId, topic, bank, companion, category]);

  const openEdit = async (stem) => {
    setErr('');
    try {
      const d = await api(`/api/admin/stems/${gradeId}/${stem.bank}/${stem.topic}/${stem.stem_id}`);
      setEditor(d);
      setForm({
        question: d.question || '',
        category: d.category || (d.meta && d.meta.category) || 'counting',
        metaText: JSON.stringify(d.meta || {}, null, 2),
      });
    } catch (e) {
      setErr(e.message);
    }
  };

  const saveEdit = async () => {
    let meta;
    try {
      meta = JSON.parse(form.metaText);
      meta.category = form.category;
    } catch {
      setErr('meta.json is not valid JSON');
      return;
    }
    try {
      await api(
        `/api/admin/stems/${gradeId}/${editor.bank}/${editor.topic}/${editor.stem_id}`,
        { method: 'PUT', body: { question: form.question, category: form.category, meta } },
      );
      setEditor(null);
      setMsg('Stem updated.');
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const removeOne = async (stem) => {
    if (!window.confirm(`Delete stem ${stem.stem_id}?`)) return;
    try {
      await api(`/api/admin/stems/${gradeId}/${stem.bank}/${stem.topic}/${stem.stem_id}`, {
        method: 'DELETE',
      });
      setMsg('Stem deleted.');
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const removeAll = async () => {
    if (!window.confirm(`Delete ALL question stems for ${gradeId}? This cannot be undone.`)) return;
    try {
      const d = await api(`/api/admin/stems/${gradeId}/bulk-delete`, { method: 'POST' });
      setMsg(`Deleted ${d.deleted} stems.`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const bulkReplace = async () => {
    if (!find) return;
    try {
      const d = await api(`/api/admin/stems/${gradeId}/bulk-replace`, {
        method: 'POST',
        body: { find, replace },
      });
      setMsg(`Updated ${d.updated} stems.`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const create = async () => {
    try {
      await api(`/api/admin/stems/${gradeId}`, {
        method: 'POST',
        body: {
          stem_id: createForm.stem_id,
          topic: createForm.topic,
          bank: createForm.bank,
          category: createForm.category || 'counting',
          question: createForm.question,
          meta: {
            category: createForm.category || 'counting',
            answer: { type: 'other', correct: createForm.correct, options: [] },
          },
        },
      });
      setCreating(false);
      setMsg('Stem created.');
      load();
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <div className="admin-page">
      <h1>Questions</h1>
      <p className="lead">
        Edit one question, or update or delete every question in a school year. Search by topic or wording.
      </p>

      <div className="admin-toolbar">
        {grades.map((g) => (
          <button
            key={g.id}
            type="button"
            className={`admin-chip ${gradeId === g.id ? 'active' : ''}`}
            onClick={() => { setGradeId(g.id); setTopic(''); }}
          >
            {g.display_name}
          </button>
        ))}
      </div>

      <div className="admin-filters">
        <select className="admin-select" style={{ maxWidth: 170 }} value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All Categories</option>
          <option value="counting">Counting & Objects</option>
          <option value="time">Time & Clocks</option>
          <option value="geometry">Geometry & Angles</option>
          <option value="measurement">Measurement</option>
          <option value="fractions">Fractions</option>
          <option value="money">Money</option>
          <option value="statistics">Statistics</option>
          <option value="patterns">Patterns</option>
          <option value="general">General</option>
        </select>
        <select className="admin-select" style={{ maxWidth: 180 }} value={topic} onChange={(e) => setTopic(e.target.value)}>
          <option value="">All topics</option>
          {(data.topics || []).map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select className="admin-select" style={{ maxWidth: 150 }} value={companion} onChange={(e) => setCompanion(e.target.value)}>
          <option value="">All Companions</option>
          <option value="father">Dad</option>
          <option value="mother">Mum</option>
          <option value="sibling">Sibling</option>
          <option value="grandmother">Grandma</option>
          <option value="grandfather">Grandad</option>
        </select>
        <select className="admin-select" style={{ maxWidth: 130 }} value={bank} onChange={(e) => setBank(e.target.value)}>
          <option value="">All banks</option>
          <option value="primary">primary</option>
          <option value="fallback">fallback</option>
        </select>
        <div style={{ display: 'flex', gap: 8, flex: 1, minWidth: 200 }}>
          <input
            className="admin-input"
            placeholder="Search stems, math problems, companions…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
          />
          <button type="button" className="admin-btn" onClick={load}>
            <Search size={16} />
          </button>
        </div>
        <button type="button" className="admin-btn" onClick={() => setCreating(true)}>
          <Plus size={16} /> New stem
        </button>
        <button type="button" className="admin-btn danger" onClick={removeAll}>
          Delete all in grade
        </button>
      </div>

      <div className="admin-card">
        <h3>Find & replace across {gradeId}</h3>
        <div className="admin-grid" style={{ gridTemplateColumns: '1fr 1fr auto' }}>
          <input className="admin-input" placeholder="Find text" value={find} onChange={(e) => setFind(e.target.value)} />
          <input className="admin-input" placeholder="Replace with" value={replace} onChange={(e) => setReplace(e.target.value)} />
          <button type="button" className="admin-btn ghost" onClick={bulkReplace}>Update matching stems</button>
        </div>
      </div>

      <p style={{ color: '#94a3b8', marginBottom: 8 }}>{data.count} stems</p>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Stem</th>
              <th>Companion</th>
              <th>Category</th>
              <th>Topic</th>
              <th>Bank</th>
              <th style={{ minWidth: 320 }}>Core Question</th>
              <th>Answer</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data.stems || []).slice(0, 400).map((s) => (
              <tr key={`${s.bank}-${s.topic}-${s.stem_id}`}>
                <td><code>{s.stem_id}</code></td>
                <td>
                  <span className={`companion-badge comp-${s.companion_role || 'solo'}`}>
                    {s.companion_label || 'Solo'}
                  </span>
                </td>
                <td>
                  <span className={`category-badge cat-${s.category || 'counting'}`}>
                    {(s.category || 'counting').charAt(0).toUpperCase() + (s.category || 'counting').slice(1)}
                  </span>
                </td>
                <td>
                  <div className="stem-topic-badge">{s.topic_label || s.topic}</div>
                  {s.topic_label && s.topic_label !== s.topic && (
                    <span className="stem-topic-sub">{s.topic}</span>
                  )}
                </td>
                <td>{s.bank}</td>
                <td title={s.question || s.core_question}>
                  <div style={{ color: '#e2e8f0', lineHeight: 1.45, fontWeight: 500 }}>
                    {s.core_question || s.question_preview}
                  </div>
                </td>
                <td><strong style={{ color: '#10b981' }}>{s.correct}</strong></td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button type="button" className="admin-btn ghost" onClick={() => openEdit(s)} title="Edit stem">
                    <Pencil size={14} />
                  </button>
                  {' '}
                  <button type="button" className="admin-btn danger" onClick={() => removeOne(s)} title="Delete stem">
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editor && (
        <div className="admin-modal-overlay" onClick={() => setEditor(null)}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Edit {editor.stem_id}</h2>
            <div style={{ marginBottom: 12 }}>
              <label className="admin-label">Category</label>
              <select
                className="admin-select"
                style={{ width: '100%' }}
                value={form.category}
                onChange={(e) => {
                  const newCat = e.target.value;
                  setForm((f) => {
                    let updatedMeta = {};
                    try { updatedMeta = JSON.parse(f.metaText); } catch {}
                    updatedMeta.category = newCat;
                    return {
                      ...f,
                      category: newCat,
                      metaText: JSON.stringify(updatedMeta, null, 2),
                    };
                  });
                }}
              >
                <option value="counting">Counting & Objects</option>
                <option value="time">Time & Clocks</option>
                <option value="geometry">Geometry & Angles</option>
                <option value="measurement">Measurement</option>
                <option value="fractions">Fractions</option>
                <option value="money">Money</option>
                <option value="statistics">Statistics</option>
                <option value="patterns">Patterns</option>
                <option value="general">General</option>
              </select>
            </div>
            <label className="admin-label">Question stem</label>
            <textarea
              className="admin-textarea"
              style={{ minHeight: 140 }}
              value={form.question}
              onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))}
            />
            <label className="admin-label">meta.json</label>
            <textarea
              className="admin-textarea"
              style={{ minHeight: 280 }}
              value={form.metaText}
              onChange={(e) => setForm((f) => ({ ...f, metaText: e.target.value }))}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button type="button" className="admin-btn" onClick={saveEdit}>
                <Save size={14} /> Save stem
              </button>
              <button type="button" className="admin-btn ghost" onClick={() => setEditor(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {creating && (
        <div className="admin-modal-overlay" onClick={() => setCreating(false)}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <h2>New stem in {gradeId}</h2>
            <div className="admin-grid">
              <div>
                <label className="admin-label">Stem id</label>
                <input className="admin-input" value={createForm.stem_id} onChange={(e) => setCreateForm((f) => ({ ...f, stem_id: e.target.value }))} />
              </div>
              <div>
                <label className="admin-label">Category</label>
                <select className="admin-select" value={createForm.category} onChange={(e) => setCreateForm((f) => ({ ...f, category: e.target.value }))}>
                  <option value="counting">Counting & Objects</option>
                  <option value="time">Time & Clocks</option>
                  <option value="geometry">Geometry & Angles</option>
                  <option value="measurement">Measurement</option>
                  <option value="fractions">Fractions</option>
                  <option value="money">Money</option>
                  <option value="statistics">Statistics</option>
                  <option value="patterns">Patterns</option>
                  <option value="general">General</option>
                </select>
              </div>
              <div>
                <label className="admin-label">Topic</label>
                <input className="admin-input" value={createForm.topic} onChange={(e) => setCreateForm((f) => ({ ...f, topic: e.target.value }))} />
              </div>
              <div>
                <label className="admin-label">Bank</label>
                <select className="admin-select" value={createForm.bank} onChange={(e) => setCreateForm((f) => ({ ...f, bank: e.target.value }))}>
                  <option value="fallback">fallback</option>
                  <option value="primary">primary</option>
                </select>
              </div>
              <div>
                <label className="admin-label">Correct answer</label>
                <input className="admin-input" value={createForm.correct} onChange={(e) => setCreateForm((f) => ({ ...f, correct: e.target.value }))} />
              </div>
            </div>
            <label className="admin-label">Question</label>
            <textarea
              className="admin-textarea"
              style={{ minHeight: 120 }}
              value={createForm.question}
              onChange={(e) => setCreateForm((f) => ({ ...f, question: e.target.value }))}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button type="button" className="admin-btn" onClick={create}>Create</button>
              <button type="button" className="admin-btn ghost" onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {msg && <div className="admin-toast">{msg}</div>}
      {err && <div className="admin-toast err">{err}</div>}
    </div>
  );
}
