import React, { useEffect, useState } from 'react';
import {
  Smile,
  Sparkles,
  Search,
  CheckCircle2,
  Heart,
  Tag,
  Shield,
  Layers,
  Image as ImageIcon,
} from 'lucide-react';
import { api } from '../api';

export default function AssetsExplorerPage() {
  const [assets, setAssets] = useState({ foods: [], characters: [], pets: [] });
  const [activeTab, setActiveTab] = useState('foods'); // 'foods', 'characters', 'pets'
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api('/api/admin/assets')
      .then((res) => setAssets(res))
      .catch((err) => console.warn('Asset fetch error:', err))
      .finally(() => setLoading(false));
  }, []);

  const filteredFoods = (assets.foods || []).filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()) ||
    f.filename.toLowerCase().includes(search.toLowerCase())
  );

  const filteredChars = (assets.characters || []).filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.filename.toLowerCase().includes(search.toLowerCase())
  );

  const filteredPets = (assets.pets || []).filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.filename.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="admin-page">
      <div className="admin-hero-banner">
        <div className="hero-content">
          <div className="admin-kicker-pill">
            <Smile size={14} /> Pictures used in the books
          </div>
          <h1>Pictures and icons</h1>
          <p className="lead" style={{ margin: 0 }}>
            Food icons, character badges and pet pictures that can appear in a child's book.
          </p>
        </div>

        {/* Search Bar */}
        <div style={{ position: 'relative', minWidth: '240px' }}>
          <Search size={16} color="#94a3b8" style={{ position: 'absolute', left: '12px', top: '12px' }} />
          <input
            type="text"
            className="admin-input"
            style={{ paddingLeft: '36px', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.7)' }}
            placeholder="Search assets..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="admin-filters" style={{ marginBottom: '20px' }}>
        <button
          type="button"
          className={`admin-chip ${activeTab === 'foods' ? 'active' : ''}`}
          onClick={() => setActiveTab('foods')}
        >
          🍓 Twemoji Food Icons ({assets.foods?.length || 54})
        </button>
        <button
          type="button"
          className={`admin-chip ${activeTab === 'characters' ? 'active' : ''}`}
          onClick={() => setActiveTab('characters')}
        >
          🦸 Famous Characters & Cartoons ({assets.characters?.length || 16})
        </button>
        <button
          type="button"
          className={`admin-chip ${activeTab === 'pets' ? 'active' : ''}`}
          onClick={() => setActiveTab('pets')}
        >
          🐕 Pets & Animal Cutouts ({assets.pets?.length || 4})
        </button>
      </div>

      {/* TAB 1: Foods */}
      {activeTab === 'foods' && (
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div>
              <h3>Top-Left Page Food Icon Gallery</h3>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: '4px 0 0 0' }}>
                When a child picks their favourite food, this Twemoji icon replaces the category icon in the top-left banner.
              </p>
            </div>
            <span className="card-pill-tag">{filteredFoods.length} Shown</span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
              gap: '14px',
              marginTop: '16px',
            }}
          >
            {filteredFoods.map((item) => (
              <div key={item.filename} className="asset-card-thumb">
                <div className="asset-thumb-box">
                  <img src={item.url} alt={item.name} className="asset-img" />
                </div>
                <div className="asset-info-name" title={item.name}>
                  {item.name}
                </div>
                <div className="asset-file-tag">{item.filename}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: Characters */}
      {activeTab === 'characters' && (
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div>
              <h3>Top-Right Character Sticker Badges</h3>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: '4px 0 0 0' }}>
                Sticker badges rendered at the top-right garland banner of each question page when a favourite character is chosen.
              </p>
            </div>
            <span className="card-pill-tag">{filteredChars.length} Badges</span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: '16px',
              marginTop: '16px',
            }}
          >
            {filteredChars.map((item) => (
              <div key={item.filename} className="asset-card-thumb" style={{ padding: '16px' }}>
                <div className="asset-thumb-box" style={{ height: '90px', background: 'radial-gradient(circle, rgba(236, 72, 153, 0.15) 0%, transparent 70%)' }}>
                  <img src={item.url} alt={item.name} className="asset-img" style={{ maxHeight: '75px' }} />
                </div>
                <div className="asset-info-name" style={{ fontSize: '0.95rem', marginTop: '10px' }} title={item.name}>
                  {item.name}
                </div>
                <div className="asset-file-tag">{item.filename}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 3: Pets */}
      {activeTab === 'pets' && (
        <div className="admin-card card-glass-glow">
          <div className="admin-card-header-bar">
            <div>
              <h3>Bottom-Right Pet Cutouts</h3>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: '4px 0 0 0' }}>
                Cute transparent pet illustrations appearing at the bottom-right corner of question sheets.
              </p>
            </div>
            <span className="card-pill-tag">{filteredPets.length} Pets</span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: '16px',
              marginTop: '16px',
            }}
          >
            {filteredPets.map((item) => (
              <div key={item.filename} className="asset-card-thumb" style={{ padding: '16px' }}>
                <div className="asset-thumb-box" style={{ height: '90px' }}>
                  <img src={item.url} alt={item.name} className="asset-img" style={{ maxHeight: '75px' }} />
                </div>
                <div className="asset-info-name" style={{ fontSize: '0.95rem', marginTop: '10px' }} title={item.name}>
                  {item.name}
                </div>
                <div className="asset-file-tag">{item.filename}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
