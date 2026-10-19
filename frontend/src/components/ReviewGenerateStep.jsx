import React from 'react';
import { Sparkles, ArrowLeft, CheckCircle2, User, BookOpen, Camera, Clock, Pencil } from 'lucide-react';
import { roleLabel } from './Guidance';

const PRESET_COLORS = [
  { name: 'Sky Blue', hex: '#0ea5e9' },
  { name: 'Royal Blue', hex: '#2563eb' },
  { name: 'Emerald', hex: '#10b981' },
  { name: 'Sunset', hex: '#f97316' },
  { name: 'Pink', hex: '#ec4899' },
  { name: 'Purple', hex: '#8b5cf6' },
  { name: 'Amber', hex: '#f59e0b' },
  { name: 'Indigo', hex: '#6366f1' },
];

function colourName(value) {
  const raw = (value || '').trim();
  const match = PRESET_COLORS.find(
    (c) => c.hex.toLowerCase() === raw.toLowerCase() || c.name.toLowerCase() === raw.toLowerCase()
  );
  return match ? match.name : raw.startsWith('#') ? 'Custom colour' : raw || 'Sky Blue';
}

function colourHex(value) {
  const raw = (value || '').trim();
  const match = PRESET_COLORS.find(
    (c) => c.hex.toLowerCase() === raw.toLowerCase() || c.name.toLowerCase() === raw.toLowerCase()
  );
  return match ? match.hex : raw.startsWith('#') ? raw : '#0ea5e9';
}

export default function ReviewGenerateStep({
  formData,
  uploadedFaces,
  gradeDetail,
  onGenerate,
  onBack,
  onEditStep,
  goToStep,
  isGenerating,
}) {
  const selectedTopicsLabels = (gradeDetail?.topics || [])
    .filter((t) => (formData.selected_topics || []).includes(t.id))
    .map((t) => t.label);

  const familyList = Object.entries(formData.family_names || {}).filter(([, name]) => name.trim().length > 0);
  const uploadedRoles = Object.keys(uploadedFaces);
  const childName = (formData.student_name || 'your child').trim() || 'your child';
  const petsReady = (formData.pets || []).filter((p) => (p.name && p.name.trim()) || uploadedFaces[p.id]);
  const edit = onEditStep || goToStep;
  const go = (step) => (edit ? () => edit(step) : undefined);

  return (
    <div className="step-card">
      <div className="step-title-row">
        <div>
          <h2 className="step-title">
            <Sparkles size={26} color="var(--theme-color)" />
            <span>Check this, then we make the book</span>
          </h2>
          <p className="step-desc">
            Look over the details below. If something is wrong, tap Edit. When you are happy, tap the green button.
          </p>
        </div>
        <span className="step-badge">Step 4 of 4</span>
      </div>

      <div className="form-grid-2" style={{ marginBottom: '22px' }}>
        <div className="review-card">
          <div className="review-card-head">
            <User size={20} color="var(--theme-color)" />
            <h3>About {childName}</h3>
            {go(1) && (
              <button type="button" className="review-edit-btn" onClick={go(1)}>
                <Pencil size={12} />
                Edit
              </button>
            )}
          </div>
          <div className="review-row">
            <span className="review-row-label">Child</span>
            <span className="review-row-value">
              {formData.student_name} · {formData.gender}
            </span>
          </div>
          <div className="review-row">
            <span className="review-row-label">Subject</span>
            <span className="review-row-value">{formData.subject || 'Maths'}</span>
          </div>
          {formData.fav_color && (
            <div className="review-row">
              <span className="review-row-label">Book colour</span>
              <span className="review-row-value" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <span
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 4,
                    background: colourHex(formData.fav_color),
                    border: '1px solid #e2e8f0',
                  }}
                />
                {colourName(formData.fav_color)}
              </span>
            </div>
          )}
          {familyList.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Family</span>
              <span className="review-row-value">
                {familyList.map(([role, name]) => `${name} (${roleLabel(role)})`).join(', ')}
              </span>
            </div>
          )}
          {petsReady.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Pets</span>
              <span className="review-row-value">
                {petsReady.map((p) => `${p.name || 'Pet'} (${p.type || 'Pet'})`).join(', ')}
              </span>
            </div>
          )}
          {formData.favourite_foods?.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Foods</span>
              <span className="review-row-value">{formData.favourite_foods.join(', ')}</span>
            </div>
          )}
          {formData.favourite_hobbies?.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Hobbies</span>
              <span className="review-row-value">{formData.favourite_hobbies.join(', ')}</span>
            </div>
          )}
          {formData.favourite_sports?.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Sports</span>
              <span className="review-row-value">{formData.favourite_sports.join(', ')}</span>
            </div>
          )}
          {formData.favourite_characters?.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Characters</span>
              <span className="review-row-value">{formData.favourite_characters.join(', ')}</span>
            </div>
          )}
          {formData.favourite_cartoons?.length > 0 && (
            <div className="review-row">
              <span className="review-row-label">Cartoons</span>
              <span className="review-row-value">{formData.favourite_cartoons.join(', ')}</span>
            </div>
          )}
        </div>

        <div className="review-card">
          <div className="review-card-head">
            <BookOpen size={20} color="var(--theme-color)" />
            <h3>What is in the book</h3>
            {go(2) && (
              <button type="button" className="review-edit-btn" onClick={go(2)}>
                <Pencil size={12} />
                Edit
              </button>
            )}
          </div>
          <div className="review-row">
            <span className="review-row-label">School year</span>
            <span className="review-row-value">{formData.grade_label || formData.grade_id}</span>
          </div>
          <div className="review-row">
            <span className="review-row-label">Questions</span>
            <span className="review-row-value">{formData.num_questions} practice pages</span>
          </div>
          <div className="review-row">
            <span className="review-row-label">Topics</span>
            <span className="review-row-value">
              <span className="review-chips">
                {selectedTopicsLabels.map((lbl) => (
                  <span key={lbl} className="review-chip">{lbl}</span>
                ))}
              </span>
            </span>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: '22px' }}>
        <div className="review-card-head" style={{ borderBottom: 'none', marginBottom: 12, paddingBottom: 0 }}>
          <Camera size={18} color="var(--theme-color)" />
          <h3 style={{ fontSize: '1.02rem' }}>Photos we will use</h3>
          {go(3) && (
            <button type="button" className="review-edit-btn" onClick={go(3)}>
              <Pencil size={12} />
              Change photos
            </button>
          )}
        </div>
        <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
          {uploadedRoles.map((role) => {
            const up = uploadedFaces[role];
            return (
              <div
                key={role}
                style={{
                  background: 'white',
                  border: '1.5px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <img
                  src={up.preview_url}
                  alt={roleLabel(role)}
                  style={{ width: 44, height: 44, borderRadius: '8px', objectFit: 'cover' }}
                />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.86rem' }}>
                    {role === 'user' ? childName : roleLabel(role)}
                  </div>
                  <div style={{ fontSize: '0.74rem', color: '#10b981', display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <CheckCircle2 size={10} /> Photo ready
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="review-final-note">
        <Clock size={18} />
        <span>
          Next we draw the pictures and build a printable PDF. Please keep this page open — it usually takes about one minute.
        </span>
      </div>

      <div className="step-actions" style={{ alignItems: 'center' }}>
        <button className="btn-secondary" onClick={onBack} disabled={isGenerating}>
          <ArrowLeft size={18} />
          <span>Back to photos</span>
        </button>

        <button
          className="btn-magic-generate"
          onClick={onGenerate}
          disabled={isGenerating}
        >
          <Sparkles size={22} />
          <span>{isGenerating ? `Making ${childName}'s book…` : `Create ${childName}'s book`}</span>
        </button>
      </div>
    </div>
  );
}
