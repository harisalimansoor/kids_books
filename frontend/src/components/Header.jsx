import React, { useRef } from 'react';
import { AlertCircle, CheckCircle2 } from 'lucide-react';

export default function Header({ health, themeColor, onLogoTripleClick }) {
  const tapsRef = useRef([]);

  const handleLogoClick = () => {
    const now = Date.now();
    const recent = tapsRef.current.filter((t) => now - t < 1800);
    recent.push(now);
    tapsRef.current = recent;
    if (recent.length >= 3) {
      tapsRef.current = [];
      onLogoTripleClick?.();
    }
  };

  return (
    <header className="app-header">
      <div className="brand-section">
        <div
          className="brand-icon-wrapper"
          style={{ overflow: 'hidden', padding: 0, background: 'none', cursor: 'pointer' }}
          onClick={handleLogoClick}
          title="MyInteliBooks"
        >
          <img
            src="/logo.jpg"
            alt="MyInteliBooks Logo"
            className="brand-logo-img"
            style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '18px' }}
          />
        </div>
        <div>
          <h1 className="brand-title">MyInteliBooks</h1>
          <p className="brand-subtitle">
            A personalised maths book starring your child
          </p>
        </div>
      </div>

      <div className="header-badges">
        {health?.api_key_configured ? (
          <div className="status-badge" title="Ready to create a book">
            <CheckCircle2 size={14} color="#059669" />
            <span>Ready to create</span>
          </div>
        ) : (
          <div className="status-badge" style={{ color: '#d97706', borderColor: '#fde68a' }} title="A picture key is missing on the server">
            <AlertCircle size={14} color="#d97706" />
            <span>Pictures unavailable</span>
          </div>
        )}

        {themeColor && (
          <div
            className="status-badge"
            style={{ borderColor: themeColor, color: '#334155' }}
            title="Book colour"
          >
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: themeColor,
                display: 'inline-block',
                boxShadow: `0 0 0 2px ${themeColor}33`,
              }}
            />
            <span>Book colour</span>
          </div>
        )}
      </div>
    </header>
  );
}
