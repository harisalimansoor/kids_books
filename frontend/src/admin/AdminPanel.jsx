import React, { useState } from 'react';
import {
  LayoutDashboard,
  BookOpen,
  Bot,
  Layers,
  BarChart3,
  Activity,
  Smile,
  Mail,
  ShieldCheck,
  ArrowLeft,
  LogOut,
  UserCheck,
} from 'lucide-react';
import DashboardPage from './pages/DashboardPage';
import MasterPromptsPage from './pages/MasterPromptsPage';
import ModelsPage from './pages/ModelsPage';
import StemsPage from './pages/StemsPage';
import PdfAnalyticsPage from './pages/PdfAnalyticsPage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import AssetsExplorerPage from './pages/AssetsExplorerPage';
import FeedbackPage from './pages/FeedbackPage';
import SecurityPage from './pages/SecurityPage';
import './admin.css';

const NAV = [
  { id: 'dashboard', label: 'Overview', icon: LayoutDashboard, hint: 'Books and recent jobs', color: '#818cf8' },
  { id: 'prompts', label: 'Picture Prompts', icon: BookOpen, hint: 'How drawings are written', color: '#f472b6' },
  { id: 'models', label: 'Image Models', icon: Bot, hint: 'Providers and API keys', color: '#38bdf8' },
  { id: 'assets', label: 'Pictures & Icons', icon: Smile, hint: 'Foods, characters, pets', color: '#34d399' },
  { id: 'stems', label: 'Questions', icon: Layers, hint: 'Edit maths questions', color: '#fbbf24' },
  { id: 'pdfs', label: 'Created Books', icon: BarChart3, hint: 'Downloads and grades', color: '#a78bfa' },
  { id: 'diagnostics', label: 'System Check', icon: Activity, hint: 'Storage and connections', color: '#f87171' },
  { id: 'feedback', label: 'Parent Feedback', icon: Mail, hint: 'Emails and replies', color: '#2dd4bf' },
  { id: 'security', label: 'Login & Access', icon: ShieldCheck, hint: 'Email, password, logout', color: '#fb7185' },
];

export default function AdminPanel({ onClose, onLogout }) {
  const [page, setPage] = useState('dashboard');
  const adminEmail = localStorage.getItem('admin_email') || 'admin@myintelibooks.com';

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        {/* Brand Section */}
        <div className="admin-brand">
          <div className="brand-logo-glow-wrapper">
            <img src="/logo.jpg" alt="Logo" className="admin-brand-logo" />
          </div>
          <div>
            <div className="admin-brand-kicker">
              <ShieldCheck size={13} color="#818cf8" />
              <span>Admin Center</span>
            </div>
            <div className="admin-brand-title">MyInteliBooks</div>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="admin-nav">
          {NAV.map((item) => {
            const Icon = item.icon;
            const isActive = page === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`admin-nav-btn ${isActive ? 'active' : ''}`}
                onClick={() => setPage(item.id)}
              >
                <div
                  className="nav-icon-box"
                  style={{
                    color: isActive ? '#fff' : item.color,
                    background: isActive ? item.color : 'rgba(255, 255, 255, 0.05)',
                  }}
                >
                  <Icon size={17} />
                </div>
                <div className="nav-text-box">
                  <strong>{item.label}</strong>
                  <small>{item.hint}</small>
                </div>
              </button>
            );
          })}
        </nav>

        {/* Active Admin Profile Card */}
        <div className="admin-user-badge">
          <div className="user-badge-avatar">
            <UserCheck size={16} color="#818cf8" />
          </div>
          <div className="user-badge-info">
            <span className="user-badge-role">Signed in</span>
            <span className="user-badge-email" title={adminEmail}>
              {adminEmail}
            </span>
          </div>
          <button
            type="button"
            className="user-logout-icon"
            onClick={onLogout}
            title="Sign out"
          >
            <LogOut size={15} />
          </button>
        </div>

        {/* Exit to Creator Button */}
        <button type="button" className="admin-exit" onClick={onClose}>
          <ArrowLeft size={16} />
          <span>Back to book creator</span>
        </button>
      </aside>

      <main className="admin-main">
        {page === 'dashboard' && <DashboardPage onNavigate={setPage} />}
        {page === 'prompts' && <MasterPromptsPage />}
        {page === 'models' && <ModelsPage />}
        {page === 'assets' && <AssetsExplorerPage />}
        {page === 'stems' && <StemsPage />}
        {page === 'pdfs' && <PdfAnalyticsPage />}
        {page === 'diagnostics' && <DiagnosticsPage />}
        {page === 'feedback' && <FeedbackPage />}
        {page === 'security' && <SecurityPage onLogout={onLogout} />}
      </main>
    </div>
  );
}
