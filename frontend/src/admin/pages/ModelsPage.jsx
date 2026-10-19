import React, { useEffect, useState } from 'react';
import { Check, KeyRound, Pencil, Save } from 'lucide-react';
import { api } from '../api';

const PROVIDER_ORDER = ['openrouter', 'openai', 'gemini'];

export default function ModelsPage() {
  const [data, setData] = useState(null);
  const [keys, setKeys] = useState({ openrouter: '', openai: '', gemini: '' });
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({});
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const refresh = () =>
    api('/api/admin/models').then((d) => {
      setData(d);
      const next = {};
      Object.entries(d.providers || {}).forEach(([id, p]) => {
        next[id] = p.api_key_masked || '';
      });
      setKeys((prev) => ({ ...prev, ...next }));
    });

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
    api('/api/admin/settings')
      .then((s) => {
        const next = {};
        Object.entries(s.api_keys || {}).forEach(([k, v]) => {
          next[k] = v || '';
        });
        setKeys((prev) => ({ ...prev, ...next }));
      })
      .catch(() => {});
  }, []);

  const activate = async (provider, modelId) => {
    setErr('');
    try {
      const d = await api('/api/admin/models/active', {
        method: 'PUT',
        body: { provider, model_id: modelId },
      });
      setData(d);
      setMsg(`Active model set to ${modelId} on ${provider}.`);
    } catch (e) {
      setErr(e.message);
    }
  };

  const saveKeys = async () => {
    setErr('');
    try {
      await api('/api/admin/models/keys', { method: 'PUT', body: keys });
      setMsg('API keys saved. They are used on the next workbook generation.');
      refresh();
    } catch (e) {
      setErr(e.message);
    }
  };

  const saveItem = async () => {
    if (!editing) return;
    try {
      const d = await api('/api/admin/models/item', {
        method: 'PUT',
        body: {
          provider: editing.provider,
          model_id: editing.model_id,
          ...draft,
        },
      });
      setData(d);
      setEditing(null);
      setMsg('Model details updated.');
    } catch (e) {
      setErr(e.message);
    }
  };

  if (!data) {
    return <div className="admin-page"><p className="lead">Loading models…</p></div>;
  }

  const runtime = data.runtime || {};

  return (
    <div className="admin-page">
      <h1>Image models</h1>
      <p className="lead">
        Choose which service draws the pictures. The next book uses whatever you set as active here.
      </p>

      <div className="admin-card">
        <h2>In use now</h2>
        <p style={{ color: '#cbd5e1' }}>
          <strong>{runtime.provider_name || runtime.provider}</strong>
          {' · '}
          <code>{runtime.model}</code>
          {' · '}
          {runtime.cost_per_call || 'cost varies'}
          {' · '}
          {runtime.api_key_configured ? 'API key ready' : 'API key missing'}
        </p>
        <p style={{ color: '#94a3b8', marginTop: 8, fontSize: '0.9rem' }}>{runtime.description}</p>
      </div>

      <div className="admin-card">
        <h2>
          <KeyRound size={16} style={{ verticalAlign: '-2px', marginRight: 6 }} />
          Provider API keys
        </h2>
        <div className="admin-grid">
          {PROVIDER_ORDER.map((id) => (
            <div key={id}>
              <label className="admin-label">{id} API key</label>
              <input
                className="admin-input"
                type="password"
                value={keys[id] || ''}
                placeholder={`${id} secret`}
                onChange={(e) => setKeys((prev) => ({ ...prev, [id]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="button" className="admin-btn" onClick={saveKeys}>
            Save keys
          </button>
        </div>
      </div>

      <div className="admin-grid">
        {PROVIDER_ORDER.map((pid) => {
          const provider = data.providers?.[pid];
          if (!provider) return null;
          const isActiveProvider = data.active_provider === pid;
          return (
            <div key={pid} className={`provider-card ${isActiveProvider ? 'active-provider' : ''}`}>
              <h3>{provider.name}</h3>
              <p style={{ color: '#94a3b8', fontSize: '0.86rem', marginBottom: 8 }}>{provider.description}</p>
              <div style={{ fontSize: '0.78rem', color: provider.api_key_configured ? '#6ee7b7' : '#fda4af' }}>
                {provider.api_key_configured ? 'Key configured' : 'No key yet'}
              </div>
              {(provider.models || []).map((m) => {
                const active = data.active_provider === pid && data.active_model_id === m.id;
                return (
                  <div key={m.id} className={`model-row ${active ? 'active-model' : ''}`}>
                    <div>
                      <strong style={{ color: '#fff' }}>{m.name}</strong>
                      <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{m.id}</div>
                      <div style={{ marginTop: 6, fontSize: '0.84rem', color: '#cbd5e1' }}>{m.description}</div>
                      <div style={{ marginTop: 6, color: '#a5b4fc', fontWeight: 700, fontSize: '0.82rem' }}>
                        {m.cost_per_call}
                      </div>
                      {m.cost_notes && (
                        <div style={{ color: '#64748b', fontSize: '0.78rem' }}>{m.cost_notes}</div>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <button
                        type="button"
                        className="admin-btn"
                        onClick={() => activate(pid, m.id)}
                        disabled={active}
                      >
                        {active ? <><Check size={14} /> Active</> : 'Use this'}
                      </button>
                      <button
                        type="button"
                        className="admin-btn ghost"
                        onClick={() => {
                          setEditing({ provider: pid, model_id: m.id });
                          setDraft({
                            name: m.name,
                            description: m.description,
                            cost_per_call: m.cost_per_call,
                            cost_notes: m.cost_notes,
                            best_for: m.best_for,
                            endpoint: m.endpoint,
                          });
                        }}
                      >
                        <Pencil size={14} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      {editing && (
        <div className="admin-modal-overlay" onClick={() => setEditing(null)}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Edit {editing.model_id}</h2>
            {['name', 'description', 'cost_per_call', 'cost_notes', 'best_for', 'endpoint'].map((field) => (
              <div key={field} style={{ marginTop: 12 }}>
                <label className="admin-label">{field.replaceAll('_', ' ')}</label>
                {field === 'description' || field === 'cost_notes' ? (
                  <textarea
                    className="admin-textarea"
                    style={{ minHeight: 90 }}
                    value={draft[field] || ''}
                    onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.value }))}
                  />
                ) : (
                  <input
                    className="admin-input"
                    value={draft[field] || ''}
                    onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.value }))}
                  />
                )}
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button type="button" className="admin-btn" onClick={saveItem}>
                <Save size={14} /> Save
              </button>
              <button type="button" className="admin-btn ghost" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {msg && <div className="admin-toast">{msg}</div>}
      {err && <div className="admin-toast err">{err}</div>}
    </div>
  );
}
