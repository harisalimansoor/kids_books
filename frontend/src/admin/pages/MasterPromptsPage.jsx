import React, { useEffect, useState } from 'react';
import { Plus, Save, Trash2, Sparkles } from 'lucide-react';
import { api } from '../api';

export default function MasterPromptsPage() {
  const [grades, setGrades] = useState([]);
  const [gradeId, setGradeId] = useState('Grade_1');
  const [list, setList] = useState({ prompts: [], master: null, grade_prompts: [] });
  const [active, setActive] = useState(null);
  const [content, setContent] = useState('');
  const [newName, setNewName] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api('/api/admin/grades')
      .then((d) => {
        setGrades(d.grades || []);
        const first = (d.grades || []).find((g) => g.enabled) || (d.grades || [])[0];
        if (first) setGradeId(first.id);
      })
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!gradeId) return;
    setErr('');
    api(`/api/admin/prompts/${gradeId}`)
      .then((d) => {
        setList(d);
        const pick = d.master?.name || d.prompts?.[0]?.name;
        if (pick) loadPrompt(gradeId, pick);
        else {
          setActive(null);
          setContent('');
        }
      })
      .catch((e) => setErr(e.message));
  }, [gradeId]);

  const loadPrompt = async (gid, name) => {
    try {
      const d = await api(`/api/admin/prompts/${gid}/${name}`);
      setActive(d);
      setContent(d.content || '');
      setMsg('');
    } catch (e) {
      setErr(e.message);
    }
  };

  const save = async () => {
    if (!active) return;
    setSaving(true);
    setErr('');
    try {
      await api(`/api/admin/prompts/${gradeId}/${active.name}`, {
        method: 'PUT',
        body: { content },
      });
      setMsg('Prompt saved.');
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    setErr('');
    try {
      await api(`/api/admin/prompts/${gradeId}`, {
        method: 'POST',
        body: { name, content: `# ${name}\n\n` },
      });
      setNewName('');
      const d = await api(`/api/admin/prompts/${gradeId}`);
      setList(d);
      loadPrompt(gradeId, name.replace(/[^A-Za-z0-9_-]/g, '') || name);
      setMsg('Prompt created.');
    } catch (e) {
      setErr(e.message);
    }
  };

  const remove = async (name) => {
    if (!window.confirm(`Delete prompt “${name}” for ${gradeId}?`)) return;
    try {
      await api(`/api/admin/prompts/${gradeId}/${name}`, { method: 'DELETE' });
      const d = await api(`/api/admin/prompts/${gradeId}`);
      setList(d);
      const pick = d.master?.name || d.prompts?.[0]?.name;
      if (pick) loadPrompt(gradeId, pick);
      else {
        setActive(null);
        setContent('');
      }
      setMsg('Prompt deleted.');
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <div className="admin-page">
      <h1>Picture prompts</h1>
      <p className="lead">
        These instructions tell the AI how to draw each school year — question pictures,
        the front cover, and the last page. Each year stays separate.
      </p>

      <div className="admin-toolbar">
        {grades.map((g) => (
          <button
            key={g.id}
            type="button"
            className={`admin-chip ${gradeId === g.id ? 'active' : ''}`}
            onClick={() => setGradeId(g.id)}
          >
            {g.display_name}
          </button>
        ))}
      </div>

      <div className="admin-grid" style={{ gridTemplateColumns: '280px 1fr', alignItems: 'start' }}>
        <div className="admin-card">
          <h3>
            <Sparkles size={16} style={{ verticalAlign: '-2px', marginRight: 6 }} />
            {gradeId} prompts
          </h3>
          {list.master && (
            <button
              type="button"
              className={`admin-nav-btn ${active?.name === list.master.name ? 'active' : ''}`}
              style={{ marginBottom: 8 }}
              onClick={() => loadPrompt(gradeId, list.master.name)}
            >
              <span>
                <strong>Master · {list.master.name}</strong>
                <small>question scenes</small>
              </span>
            </button>
          )}
          {(list.grade_prompts || []).map((p) => (
            <div key={p.name} style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
              <button
                type="button"
                className={`admin-nav-btn ${active?.name === p.name ? 'active' : ''}`}
                style={{ flex: 1 }}
                onClick={() => loadPrompt(gradeId, p.name)}
              >
                <span>
                  <strong>{p.name}</strong>
                  <small>grade-wise</small>
                </span>
              </button>
              <button type="button" className="admin-btn danger" onClick={() => remove(p.name)} title="Delete">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <div style={{ marginTop: 14 }}>
            <label className="admin-label">Add grade-wise prompt</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className="admin-input"
                placeholder="e.g. recap_page"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <button type="button" className="admin-btn" onClick={create}>
                <Plus size={16} />
              </button>
            </div>
          </div>
        </div>

        <div className="admin-card">
          {active ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
                <div>
                  <h2>{active.is_master ? 'Master prompt' : 'Grade-wise prompt'}: {active.name}</h2>
                  <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
                    Saved to grades/{gradeId}/prompts/{active.filename}
                  </p>
                </div>
                <button type="button" className="admin-btn" onClick={save} disabled={saving}>
                  <Save size={15} style={{ marginRight: 6, verticalAlign: '-2px' }} />
                  {saving ? 'Saving…' : 'Save changes'}
                </button>
              </div>
              <textarea
                className="admin-textarea"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                style={{ minHeight: 520 }}
              />
            </>
          ) : (
            <p style={{ color: '#94a3b8' }}>Select a grade that has prompt files, or add a new one.</p>
          )}
          {msg && <div className="admin-toast">{msg}</div>}
          {err && <div className="admin-toast err">{err}</div>}
        </div>
      </div>
    </div>
  );
}
