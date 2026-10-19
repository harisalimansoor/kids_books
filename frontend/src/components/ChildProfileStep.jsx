import React, { useState, useRef } from 'react';
import { User, ChevronDown, ChevronUp, Palette, Users, ArrowRight, BookOpen, MapPin, Camera, Upload, Trash2, Plus, CheckCircle2, Sparkles } from 'lucide-react';
import { HelpTip, RequirementChecklist, FieldFlag, HowItWorks } from './Guidance';

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

const SUBJECTS = [
  { id: 'Math', name: 'Math', icon: '🔢', disabled: false, note: 'Selected' },
  { id: 'English', name: 'English', icon: '📚', disabled: true, note: 'Coming Soon' },
  { id: 'Science', name: 'Science', icon: '🔬', disabled: true, note: 'Coming Soon' },
  { id: 'General Knowledge', name: 'General Knowledge', icon: '🌍', disabled: true, note: 'Coming Soon' },
];

const PET_TYPES = [
  { label: 'Dog', icon: '🐶' },
  { label: 'Cat', icon: '🐱' },
  { label: 'Bunny', icon: '🐰' },
  { label: 'Bird', icon: '🦜' },
  { label: 'Other', icon: '🐾' },
];

export default function ChildProfileStep({
  formData,
  updateFormData,
  uploadedFaces = {},
  setUploadedFaces = () => {},
  onNext,
}) {
  const [showFamily, setShowFamily] = useState(true);
  const [showPets, setShowPets] = useState(true);
  const [uploadingPet, setUploadingPet] = useState(null);
  // Validation messages stay quiet until the visitor has actually tried the field,
  // so a brand-new page never greets anyone with red warnings.
  const [touched, setTouched] = useState({ name: false, gender: false });
  const petFileInputRefs = useRef({});

  const pets = formData.pets && formData.pets.length > 0
    ? formData.pets
    : [{ id: 'pet_1', name: '', type: 'Dog' }];

  const handlePetNameChange = (petId, name) => {
    const updated = pets.map((p) => (p.id === petId ? { ...p, name } : p));
    if (!updated.some((p) => p.id === petId)) {
      updated.push({ id: petId, name, type: 'Dog' });
    }
    updateFormData({ pets: updated });
  };

  const handlePetTypeChange = (petId, type) => {
    const updated = pets.map((p) => (p.id === petId ? { ...p, type } : p));
    updateFormData({ pets: updated });
  };

  const handleAddSecondPet = () => {
    if (pets.length < 2) {
      updateFormData({
        pets: [...pets, { id: 'pet_2', name: '', type: 'Cat' }],
      });
    }
  };

  const handleRemovePet = async (petId) => {
    const updated = pets.filter((p) => p.id !== petId);
    updateFormData({ pets: updated.length > 0 ? updated : [{ id: 'pet_1', name: '', type: 'Dog' }] });
    if (uploadedFaces[petId]) {
      try {
        if (formData.job_id) {
          await fetch(`/api/jobs/${formData.job_id}/faces/${petId}`, { method: 'DELETE' });
        }
      } catch (e) {
        console.warn(e);
      }
      setUploadedFaces((prev) => {
        const next = { ...prev };
        delete next[petId];
        return next;
      });
    }
  };

  const handlePetPhotoUpload = async (petId, file) => {
    if (!file) return;
    setUploadingPet(petId);
    const localBlobUrl = URL.createObjectURL(file);
    try {
      const data = new FormData();
      data.append('file', file);
      data.append('role', petId);
      if (formData.job_id) data.append('job_id', formData.job_id);
      const res = await fetch('/api/upload-face', { method: 'POST', body: data });
      if (!res.ok) throw new Error('Photo upload failed');
      const result = await res.json();
      setUploadedFaces((prev) => ({
        ...prev,
        [petId]: {
          ...result,
          preview_url: result.preview_url || localBlobUrl,
          local_blob: localBlobUrl,
        },
      }));
    } catch (err) {
      console.error(err);
      alert('Could not upload pet photo. Please try another image file.');
    } finally {
      setUploadingPet(null);
    }
  };

  const handleRemovePetPhoto = async (petId) => {
    try {
      if (formData.job_id) {
        await fetch(`/api/jobs/${formData.job_id}/faces/${petId}`, { method: 'DELETE' });
      }
      setUploadedFaces((prev) => {
        const next = { ...prev };
        delete next[petId];
        return next;
      });
      if (petFileInputRefs.current[petId]) {
        petFileInputRefs.current[petId].value = '';
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleColorSelect = (hex, name) => {
    updateFormData({ fav_color: hex });
    document.documentElement.style.setProperty('--theme-color', hex);
    document.documentElement.style.setProperty('--theme-color-glow', `${hex}40`);
  };

  const handleCustomColor = (e) => {
    const val = e.target.value;
    updateFormData({ fav_color: val });
    if (val.startsWith('#') && (val.length === 4 || val.length === 7)) {
      document.documentElement.style.setProperty('--theme-color', val);
      document.documentElement.style.setProperty('--theme-color-glow', `${val}40`);
    }
  };

  const isValid =
    formData.student_name.trim().length > 0 &&
    Boolean(formData.gender) &&
    formData.gender !== 'Select';

  const familyNameCount = Object.values(formData.family_names || {}).filter(
    (n) => (n || '').trim().length > 0
  ).length;

  const handleNameChange = (e) => {
    const name = e.target.value;
    const updates = { student_name: name };
    // Smart auto-detection if gender hasn't been explicitly chosen yet
    if (!formData.gender) {
      const lower = name.trim().toLowerCase();
      const femaleNames = [
        'alia', 'aaliyah', 'maya', 'emma', 'olivia', 'sophia', 'ava', 'isabella',
        'mia', 'amelia', 'harper', 'evelyn', 'lily', 'emily', 'chloe', 'zara',
        'daisy', 'grace', 'zoe', 'lucy', 'ruby', 'alice', 'ivy', 'ella', 'layla',
        'freya', 'florence', 'hannah', 'sarah', 'fatima', 'aisha', 'anaya', 'leila'
      ];
      const maleNames = [
        'leo', 'oliver', 'jack', 'noah', 'harry', 'george', 'charlie', 'arthur',
        'freddie', 'theo', 'lucas', 'sam', 'liam', 'ethan', 'ali', 'hassan', 'adam'
      ];
      if (femaleNames.includes(lower) || lower.endsWith('ia') || lower.endsWith('lla') || lower.endsWith('ina')) {
        updates.gender = 'Girl';
      } else if (maleNames.includes(lower)) {
        updates.gender = 'Boy';
      }
    }
    updateFormData(updates);
  };

  const matchedPreset = PRESET_COLORS.find(
    (c) =>
      c.hex.toLowerCase() === (formData.fav_color || '').toLowerCase() ||
      c.name.toLowerCase() === (formData.fav_color || '').toLowerCase()
  );
  const activeHex = matchedPreset
    ? matchedPreset.hex
    : formData.fav_color?.startsWith('#')
      ? formData.fav_color
      : '#0ea5e9';
  const activeColorName = matchedPreset
    ? matchedPreset.name
    : formData.fav_color || 'Custom';

  return (
    <div className="step-card">
      <div className="step-title-row">
        <div>
          <h2 className="step-title">
            <User size={26} color="var(--theme-color)" />
            <span>Tell Us About Your Child</span>
          </h2>
          <p className="step-desc">
            Just two things are needed here: your child's name and whether they are a boy or a girl.
            Everything below that is optional.
          </p>
        </div>
        <span className="step-badge">Step 1 of 4</span>
      </div>

      <HowItWorks />

      <div className="form-grid-2">
        {/* Child Name */}
        <div className="form-group">
          <label className="form-label">
            Child's Name <span className="required">*</span>
            <HelpTip text="This name is printed on the book cover and used inside every maths question, so your child reads their own name in each story." />
          </label>
          <input
            type="text"
            className={`text-input ${touched.name && !formData.student_name.trim() ? 'has-error' : ''}`}
            placeholder="e.g. Leo, Oliver, Maya, Hamdan"
            value={formData.student_name}
            onChange={handleNameChange}
            onBlur={() => setTouched((t) => ({ ...t, name: true }))}
            autoFocus
          />
          {touched.name && !formData.student_name.trim() ? (
            <span className="form-hint is-error">Please type your child's first name to continue.</span>
          ) : (
            <span className="form-hint">Printed on the cover and used in every question</span>
          )}
        </div>

        {/* Gender Selection */}
        <div className="form-group">
          <label className="form-label">
            Boy or Girl? <span className="required">*</span>
            <HelpTip text="We use this so the child drawn in the pictures matches your child, and so the stories say 'he' or 'she' correctly." />
          </label>
          <div className="gender-chips">
            {['Boy', 'Girl', 'Other'].map((g) => (
              <button
                type="button"
                key={g}
                className={`gender-chip ${formData.gender === g ? 'selected' : ''}`}
                onClick={() => {
                  setTouched((t) => ({ ...t, gender: true }));
                  updateFormData({ gender: g });
                }}
              >
                <span>{g === 'Boy' ? '👦' : g === 'Girl' ? '👧' : '🌟'}</span>
                <span>{g}</span>
              </button>
            ))}
          </div>
          {formData.gender ? (
            <span className="form-hint is-success">
              The child in the pictures will be drawn as a <strong>{formData.gender.toLowerCase()}</strong>.
            </span>
          ) : (
            <span className="form-hint">Tap one — this keeps the drawings and the stories consistent</span>
          )}
        </div>
      </div>

      <div className="form-group" style={{ marginTop: '4px' }}>
        <label className="form-label">
          <MapPin size={16} />
          <span>Location</span>
          <FieldFlag />
        </label>
        <input
          type="text"
          className="text-input"
          placeholder="e.g. Lahore, Pakistan"
          value={formData.location || ''}
          onChange={(e) => updateFormData({ location: e.target.value })}
        />
        <span className="form-hint">You can leave this empty. It does not change the book.</span>
      </div>

      {/* Subject Selection (Instead of Age) */}
      <div className="form-group" style={{ marginTop: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
          <label className="form-label" style={{ margin: 0 }}>
            <BookOpen size={16} />
            <span>Subject <span className="required">*</span></span>
          </label>
          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
            Maths is ready. English and Science are coming later.
          </span>
        </div>
        <div className="subject-cards">
          {SUBJECTS.map((sub) => {
            const isSelected = (formData.subject || 'Math') === sub.id;
            return (
              <div
                key={sub.id}
                className={`subject-card ${isSelected ? 'selected' : ''} ${sub.disabled ? 'disabled' : ''}`}
                onClick={() => {
                  if (!sub.disabled) {
                    updateFormData({ subject: sub.id });
                  }
                }}
                title={sub.disabled ? `${sub.name} is currently in development` : sub.name}
              >
                <span className="subject-icon">{sub.icon}</span>
                <span className="subject-name">{sub.name}</span>
                <span className={`subject-badge ${isSelected ? 'active' : 'disabled-tag'}`}>
                  {isSelected ? '✓ Selected' : sub.note}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Book Theme & Border Colour Selection (Below Subject) */}
      <div className="form-group" style={{ marginTop: '20px' }}>
        <label className="form-label">
          <Palette size={16} />
          <span>Book Theme & Border Colour</span>
        </label>
        <p style={{ margin: '0 0 10px 0', fontSize: '0.85rem', color: '#64748b' }}>
          Choose your book's primary colour. In the generated PDF, every page will feature a custom border and accents matching your selected colour!
        </p>
        <div className="color-picker-row">
          {PRESET_COLORS.map((c) => (
            <div
              key={c.name}
              className={`color-swatch ${(formData.fav_color || '').toLowerCase() === c.hex.toLowerCase() ||
                  (formData.fav_color || '').toLowerCase() === c.name.toLowerCase()
                  ? 'active'
                  : ''
                }`}
              style={{ backgroundColor: c.hex }}
              title={c.name}
              onClick={() => handleColorSelect(c.hex, c.name)}
            />
          ))}
          <input
            type="text"
            className="color-custom-input"
            placeholder="or hex e.g. #ec4899"
            value={formData.fav_color}
            onChange={handleCustomColor}
          />
        </div>

        {/* Live Book Border Preview Card */}
        <div
          className="book-border-preview-card"
          style={{
            borderColor: activeHex,
            boxShadow: `0 4px 16px ${activeHex}25`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: '6px',
                backgroundColor: activeHex,
                border: '2px solid white',
                boxShadow: '0 2px 4px rgba(0,0,0,0.15)',
                flexShrink: 0,
              }}
            />
            <div>
              <strong style={{ color: '#1e293b', fontSize: '0.92rem' }}>
                Active Book Theme & Border: {activeColorName}
              </strong>
              <p style={{ margin: '2px 0 0 0', fontSize: '0.82rem', color: '#64748b' }}>
                All generated PDF pages will be framed with a clean <strong>{activeColorName}</strong> border and themed headings.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Family Members Accordion */}
      <div className="family-accordion">
        <div className="family-accordion-header" onClick={() => setShowFamily(!showFamily)}>
          <div className="family-accordion-title">
            <Users size={18} color="var(--theme-color)" />
            <span>Family Members in the Stories</span>
            <FieldFlag recommended />
            {familyNameCount > 0 && (
              <span className="interest-count-pill">{familyNameCount} added</span>
            )}
          </div>
          {showFamily ? <ChevronUp size={20} color="#64748b" /> : <ChevronDown size={20} color="#64748b" />}
        </div>

        <div className="section-explainer">
          <span className="section-explainer-icon">💡</span>
          <div>
            <strong>Recommended: add at least one name</strong> — Mum or Dad is enough.
            That person can appear in the stories (for example, “Sarah baked 6 cupcakes”).
            <br />
            You can skip this and the book still works with your child alone.
            <br />
            <span className="section-explainer-note">
              If you type a name, you must upload that person's photo on the next photo page.
            </span>
          </div>
        </div>

        {showFamily && (
          <div className="family-grid">
            <div className="form-group">
              <label className="form-label">Mum's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. Sarah"
                value={formData.family_names.mother || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, mother: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Dad's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. David"
                value={formData.family_names.father || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, father: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Grandma's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. Mary"
                value={formData.family_names.grandmother || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, grandmother: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Grandad's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. John"
                value={formData.family_names.grandfather || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, grandfather: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Brother's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. Noah"
                value={formData.family_names.brother || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, brother: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Sister's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. Emma"
                value={formData.family_names.sister || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, sister: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Uncle's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. Mike"
                value={formData.family_names.uncle || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, uncle: e.target.value }
                })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Aunt's Name</label>
              <input
                type="text"
                className="text-input"
                placeholder="e.g. Jessica"
                value={formData.family_names.aunt || ''}
                onChange={(e) => updateFormData({
                  family_names: { ...formData.family_names, aunt: e.target.value }
                })}
              />
            </div>
          </div>
        )}
      </div>

      {/* Family Pets Section */}
      <div className="family-accordion" style={{ marginTop: '18px' }}>
        <div className="family-accordion-header" onClick={() => setShowPets(!showPets)}>
          <div className="family-accordion-title">
            <span style={{ fontSize: '1.25rem' }}>🐾</span>
            <span>Family Pets</span>
            <FieldFlag />
            <span
              style={{
                fontSize: '0.72rem',
                padding: '3px 9px',
                borderRadius: '999px',
                background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(236, 72, 153, 0.15))',
                color: 'var(--theme-color)',
                fontWeight: 700,
                letterSpacing: '0.3px',
              }}
            >
              Cover & Bottom of Every Page
            </span>
          </div>
          {showPets ? <ChevronUp size={20} color="#64748b" /> : <ChevronDown size={20} color="#64748b" />}
        </div>

        {showPets && (
          <div style={{ marginTop: '16px' }}>
            <p style={{ margin: '0 0 16px 0', fontSize: '0.85rem', color: '#64748b' }}>
              Got a dog or a cat? Add their name and photo and they'll appear on the cover and in the
              corner of every page, cheering your child on. You can skip this completely.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {pets.map((pet, idx) => {
                const petNumber = idx + 1;
                const petRole = pet.id || `pet_${petNumber}`;
                const uploaded = uploadedFaces[petRole];
                const isUploading = uploadingPet === petRole;

                return (
                  <div
                    key={petRole}
                    style={{
                      background: 'white',
                      border: '1.5px solid #e2e8f0',
                      borderRadius: 'var(--radius-md)',
                      padding: '16px',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.03)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '1.2rem' }}>
                          {PET_TYPES.find((t) => t.label === pet.type)?.icon || '🐾'}
                        </span>
                        <strong style={{ fontSize: '0.95rem', color: '#1e293b' }}>
                          Pet {petNumber} {pet.name ? `— “${pet.name}”` : ''}
                        </strong>
                      </div>
                      {petNumber === 2 && (
                        <button
                          type="button"
                          onClick={() => handleRemovePet(petRole)}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: '#ef4444',
                            cursor: 'pointer',
                            fontSize: '0.82rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontWeight: 600,
                          }}
                        >
                          <Trash2 size={14} />
                          <span>Remove Pet 2</span>
                        </button>
                      )}
                    </div>

                    <div className="form-grid-2">
                      {/* Pet Name & Type */}
                      <div>
                        <div className="form-group" style={{ marginBottom: '10px' }}>
                          <label className="form-label" style={{ fontSize: '0.84rem' }}>
                            Pet's Name
                          </label>
                          <input
                            type="text"
                            className="text-input"
                            placeholder="e.g. Buddy, Max, Bella, Milo"
                            value={pet.name || ''}
                            onChange={(e) => handlePetNameChange(petRole, e.target.value)}
                          />
                        </div>

                        <div className="form-group" style={{ margin: 0 }}>
                          <label className="form-label" style={{ fontSize: '0.84rem' }}>
                            Pet Type
                          </label>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {PET_TYPES.map((t) => (
                              <button
                                key={t.label}
                                type="button"
                                onClick={() => handlePetTypeChange(petRole, t.label)}
                                style={{
                                  padding: '5px 10px',
                                  borderRadius: '999px',
                                  fontSize: '0.82rem',
                                  border: (pet.type || 'Dog') === t.label ? '1.5px solid var(--theme-color)' : '1px solid #cbd5e1',
                                  background: (pet.type || 'Dog') === t.label ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(6, 182, 212, 0.1))' : '#f8fafc',
                                  color: (pet.type || 'Dog') === t.label ? 'var(--theme-color)' : '#475569',
                                  fontWeight: (pet.type || 'Dog') === t.label ? 700 : 500,
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '4px',
                                }}
                              >
                                <span>{t.icon}</span>
                                <span>{t.label}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Pet Photo Upload */}
                      <div>
                        <label className="form-label" style={{ fontSize: '0.84rem' }}>
                          Pet Picture
                        </label>
                        <input
                          type="file"
                          accept="image/*,.heic,.heif,.webp,.bmp,.tiff,.tif,.gif,.svg"
                          style={{ display: 'none' }}
                          ref={(el) => (petFileInputRefs.current[petRole] = el)}
                          onChange={(e) => handlePetPhotoUpload(petRole, e.target.files?.[0])}
                        />

                        {uploaded ? (
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '14px',
                              background: '#f0fdf4',
                              border: '1.5px solid #86efac',
                              borderRadius: 'var(--radius-md)',
                              padding: '10px 14px',
                            }}
                          >
                            <img
                              src={uploaded.preview_url || uploaded.local_blob}
                              alt={pet.name || 'Pet'}
                              style={{
                                width: 54,
                                height: 54,
                                borderRadius: '50%',
                                objectFit: 'cover',
                                border: '2px solid white',
                                boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
                                flexShrink: 0,
                              }}
                            />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#16a34a', fontSize: '0.86rem', fontWeight: 700 }}>
                                <CheckCircle2 size={16} />
                                <span>Photo Ready!</span>
                              </div>
                              <p style={{ margin: '2px 0 0 0', fontSize: '0.78rem', color: '#64748b' }}>
                                Appears on cover & inside pages
                              </p>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                              <button
                                type="button"
                                onClick={() => petFileInputRefs.current[petRole]?.click()}
                                style={{
                                  padding: '4px 8px',
                                  fontSize: '0.76rem',
                                  background: 'white',
                                  border: '1px solid #cbd5e1',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                  color: '#334155',
                                  fontWeight: 600,
                                }}
                              >
                                Change
                              </button>
                              <button
                                type="button"
                                onClick={() => handleRemovePetPhoto(petRole)}
                                style={{
                                  padding: '4px 8px',
                                  fontSize: '0.76rem',
                                  background: '#fee2e2',
                                  border: '1px solid #fca5a5',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                  color: '#dc2626',
                                  fontWeight: 600,
                                }}
                              >
                                Remove
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div
                            onClick={() => petFileInputRefs.current[petRole]?.click()}
                            style={{
                              border: '1.5px dashed #cbd5e1',
                              borderRadius: 'var(--radius-md)',
                              padding: '16px',
                              textAlign: 'center',
                              cursor: 'pointer',
                              background: '#f8fafc',
                              transition: 'all 0.2s ease',
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              gap: '6px',
                            }}
                            onMouseOver={(e) => (e.currentTarget.style.borderColor = 'var(--theme-color)')}
                            onMouseOut={(e) => (e.currentTarget.style.borderColor = '#cbd5e1')}
                          >
                            <Camera size={24} color="var(--theme-color)" />
                            <span style={{ fontSize: '0.86rem', fontWeight: 600, color: '#334155' }}>
                              {isUploading ? 'Uploading pet photo...' : 'Click to Upload Pet Picture'}
                            </span>
                            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                              All image formats supported (JPG, PNG, WEBP, HEIC, etc.) · Any clear photo of your pet
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {pets.length < 2 && (
                <button
                  type="button"
                  onClick={handleAddSecondPet}
                  style={{
                    background: 'white',
                    border: '1.5px dashed #94a3b8',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    color: 'var(--theme-color)',
                    fontWeight: 700,
                    fontSize: '0.88rem',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.borderColor = 'var(--theme-color)';
                    e.currentTarget.style.background = 'rgba(99, 102, 241, 0.04)';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.borderColor = '#94a3b8';
                    e.currentTarget.style.background = 'white';
                  }}
                >
                  <Plus size={18} />
                  <span>+ Add a Second Pet (Optional)</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="step-actions has-checklist" style={{ justifyContent: 'space-between' }}>
        <RequirementChecklist
          allDoneText="Great — that's everything we need on this page."
          items={[
            {
              done: formData.student_name.trim().length > 0,
              label: "Type your child's name",
              hint: 'the box at the top of this page',
              fixLabel: 'Go to name',
              onFix: () => {
                setTouched((t) => ({ ...t, name: true }));
                window.scrollTo({ top: 0, behavior: 'smooth' });
              },
            },
            {
              done: Boolean(formData.gender) && formData.gender !== 'Select',
              label: 'Choose Boy, Girl or Other',
              hint: 'so the drawings match your child',
              fixLabel: 'Go to choice',
              onFix: () => {
                setTouched((t) => ({ ...t, gender: true }));
                window.scrollTo({ top: 0, behavior: 'smooth' });
              },
            },
          ]}
        />
        <button
          className="btn-primary"
          onClick={() => {
            window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
            document.documentElement.scrollTop = 0;
            document.body.scrollTop = 0;
            onNext();
          }}
          disabled={!isValid}
          style={{ opacity: isValid ? 1 : 0.5, cursor: isValid ? 'pointer' : 'not-allowed' }}
        >
          <span>Next: Pick the Maths Topics</span>
          <ArrowRight size={18} />
        </button>
      </div>
    </div>
  );
}
