import React, { useRef, useState } from 'react';
import {
  Camera,
  Upload,
  Trash2,
  ArrowLeft,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Eye,
  RefreshCw,
  X,
  Plus,
} from 'lucide-react';
import { HelpTip, RequirementChecklist, FieldFlag, PhotoTips } from './Guidance';

const PET_TYPES = [
  { label: 'Dog', icon: '🐶' },
  { label: 'Cat', icon: '🐱' },
  { label: 'Bunny', icon: '🐰' },
  { label: 'Bird', icon: '🦜' },
  { label: 'Other', icon: '🐾' },
];

const FAMILY_ROLES = [
  { role: 'user', label: 'Child', required: true, icon: '🧒' },
  { role: 'mother', label: 'Mum', required: false, icon: '👩' },
  { role: 'father', label: 'Dad', required: false, icon: '👨' },
  { role: 'grandmother', label: 'Grandma', required: false, icon: '👵' },
  { role: 'grandfather', label: 'Grandad', required: false, icon: '👴' },
  { role: 'brother', label: 'Brother', required: false, icon: '👦' },
  { role: 'sister', label: 'Sister', required: false, icon: '👧' },
  { role: 'uncle', label: 'Uncle', required: false, icon: '🧑' },
  { role: 'aunt', label: 'Aunt', required: false, icon: '👱‍♀️' },
];

export default function PhotoUploadStep({
  formData,
  updateFormData = () => {},
  uploadedFaces,
  setUploadedFaces,
  stemStats,
  onNext,
  onBack,
  onGoToFamily,
  goToStep,
}) {
  const [uploadingRole, setUploadingRole] = useState(null);
  const [previewModalData, setPreviewModalData] = useState(null);
  const [dragOverRole, setDragOverRole] = useState(null);
  const fileInputRefs = useRef({});

  const handleFileChange = async (role, file) => {
    if (!file) return;
    setUploadingRole(role);
    const localBlobUrl = URL.createObjectURL(file);

    try {
      const data = new FormData();
      data.append('file', file);
      data.append('role', role);
      if (formData.job_id) {
        data.append('job_id', formData.job_id);
      }

      const res = await fetch('/api/upload-face', {
        method: 'POST',
        body: data,
      });

      if (!res.ok) {
        throw new Error('Photo upload failed');
      }

      const result = await res.json();
      setUploadedFaces((prev) => ({
        ...prev,
        [role]: {
          ...result,
          preview_url: result.preview_url || localBlobUrl,
          local_blob: localBlobUrl,
        },
      }));

      if (role.startsWith('pet_') && updateFormData) {
        const current = (formData.pets && formData.pets.length > 0)
          ? [...formData.pets]
          : [{ id: 'pet_1', name: '', type: 'Dog' }];
        if (!current.some((p) => p.id === role)) {
          current.push({ id: role, name: '', type: role === 'pet_2' ? 'Cat' : 'Dog' });
          updateFormData({ pets: current });
        }
      }
    } catch (err) {
      console.error(err);
      alert('We could not use that photo. Please try a different picture (JPG or PNG).');
    } finally {
      setUploadingRole(null);
      setDragOverRole(null);
    }
  };

  const handleRemovePhoto = async (role) => {
    try {
      if (formData.job_id) {
        await fetch(`/api/jobs/${formData.job_id}/faces/${role}`, {
          method: 'DELETE',
        });
      }
      setUploadedFaces((prev) => {
        const next = { ...prev };
        delete next[role];
        return next;
      });
      if (fileInputRefs.current[role]) {
        fileInputRefs.current[role].value = '';
      }
      if (previewModalData?.role === role) {
        setPreviewModalData(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handlePetFieldChange = (petId, field, val) => {
    if (!updateFormData) return;
    const current = (formData.pets && formData.pets.length > 0)
      ? [...formData.pets]
      : [{ id: 'pet_1', name: '', type: 'Dog' }];
    const idx = current.findIndex((p) => p.id === petId);
    if (idx >= 0) {
      current[idx] = { ...current[idx], [field]: val };
    } else {
      current.push({ id: petId, name: '', type: 'Dog', [field]: val });
    }
    updateFormData({ pets: current });
  };

  const handleAddSecondPet = () => {
    if (!updateFormData) return;
    const current = (formData.pets && formData.pets.length > 0)
      ? [...formData.pets]
      : [{ id: 'pet_1', name: '', type: 'Dog' }];
    if (current.length < 2) {
      updateFormData({
        pets: [...current, { id: 'pet_2', name: '', type: 'Cat' }],
      });
    }
  };

  const handleRemovePetCard = async (petId) => {
    await handleRemovePhoto(petId);
    if (!updateFormData) return;
    const current = (formData.pets || []).filter((p) => p.id !== petId);
    updateFormData({
      pets: current.length > 0 ? current : [{ id: 'pet_1', name: '', type: 'Dog' }],
    });
  };

  const hasChildPhoto = Boolean(uploadedFaces.user);

  const getRoleEnteredName = (role) => {
    if (role === 'user') {
      return (formData.student_name || '').trim();
    }
    if (role === 'pet_1' || role === 'pet_2') {
      const pet = (formData.pets || []).find((p) => p.id === role);
      return (pet?.name || '').trim();
    }
    return (formData.family_names?.[role] || '').trim();
  };

  const acceptDrop = (role, event) => {
    event.preventDefault();
    event.stopPropagation();
    const file = event.dataTransfer?.files?.[0];
    setDragOverRole(null);
    if (file) handleFileChange(role, file);
  };

  const openPreview = (role, label, enteredName, icon, uploaded) => {
    setPreviewModalData({
      role,
      label,
      enteredName,
      icon,
      url: uploaded.preview_url || uploaded.local_blob,
      width: uploaded.width,
      height: uploaded.height,
      warning: uploaded.warning,
    });
  };

  const enabledFamily = FAMILY_ROLES.filter((r) => Boolean(getRoleEnteredName(r.role)));
  const lockedFamily = FAMILY_ROLES.filter((r) => r.role !== 'user' && !getRoleEnteredName(r.role));
  const namedFamily = enabledFamily.filter((r) => r.role !== 'user');
  const missingFamilyPhotos = namedFamily.filter((r) => !uploadedFaces[r.role]);
  const familyPhotoCount = namedFamily.filter((r) => uploadedFaces[r.role]).length;
  const canContinue = hasChildPhoto && missingFamilyPhotos.length === 0;

  const renderPhotoCard = ({ role, label, icon }) => {
    const enteredName = getRoleEnteredName(role);
    const uploaded = uploadedFaces[role];
    const isUploading = uploadingRole === role;
    const isDragging = dragOverRole === role;
    const required = role === 'user' || Boolean(enteredName);

    return (
      <div
        key={role}
        className={`photo-card ${uploaded ? 'has-photo' : ''} ${required ? 'is-required' : 'is-enabled'} ${isDragging ? 'is-dragover' : ''}`}
      >
        <input
          type="file"
          accept="image/*,.heic,.heif,.webp,.bmp,.tiff,.tif,.gif,.svg"
          style={{ display: 'none' }}
          ref={(el) => (fileInputRefs.current[role] = el)}
          onChange={(e) => handleFileChange(role, e.target.files?.[0])}
        />

        <div className="photo-card-role">
          <span style={{ marginRight: '6px' }}>{icon}</span>
          <span>{label}</span>
        </div>

        {enteredName && (
          <div className="photo-card-name" title={enteredName}>
            “{enteredName}”
          </div>
        )}

        <span className={`photo-card-badge ${required ? 'badge-required' : 'badge-ready'}`}>
          {required ? 'Needed' : 'Nice to have'}
        </span>

        {uploaded ? (
          <>
            <div
              className="photo-preview-wrapper"
              onClick={() => openPreview(role, label, enteredName, icon, uploaded)}
              title="Tap to see the full photo"
            >
              <img
                src={uploaded.preview_url || uploaded.local_blob}
                alt={`${label} (${enteredName})`}
                className="photo-preview-img"
              />
              <div className="preview-overlay-zoom">
                <Eye size={16} />
                <span>Look closer</span>
              </div>
            </div>

            {uploaded.warning ? (
              <span style={{ fontSize: '0.75rem', color: '#d97706', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '6px' }}>
                <AlertCircle size={12} /> This photo is a bit small. A clearer one will look better.
              </span>
            ) : (
              <span style={{ fontSize: '0.75rem', color: '#059669', display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '6px' }}>
                <CheckCircle2 size={12} /> Photo ready
              </span>
            )}

            <div className="photo-actions-row">
              <button
                type="button"
                className="photo-action-btn btn-action-preview"
                onClick={() => openPreview(role, label, enteredName, icon, uploaded)}
              >
                <Eye size={12} />
                <span>Preview</span>
              </button>
              <button
                type="button"
                className="photo-action-btn btn-action-change"
                onClick={() => fileInputRefs.current[role]?.click()}
              >
                <RefreshCw size={11} />
                <span>Change</span>
              </button>
              <button
                type="button"
                className="photo-action-btn btn-action-remove"
                onClick={() => handleRemovePhoto(role)}
              >
                <Trash2 size={12} />
                <span>Remove</span>
              </button>
            </div>
          </>
        ) : (
          <div
            className="upload-dropzone"
            onClick={() => fileInputRefs.current[role]?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOverRole(role);
            }}
            onDragLeave={() => setDragOverRole(null)}
            onDrop={(e) => acceptDrop(role, e)}
          >
            <div className="upload-icon-circle">
              {isUploading ? (
                <span style={{ fontSize: '1rem', animation: 'spinRing 1s linear infinite' }}>⏳</span>
              ) : (
                <Upload size={20} />
              )}
            </div>
            <span className="upload-btn-text">
              {isUploading ? 'Uploading…' : isDragging ? 'Drop the photo here' : 'Click or drop a photo'}
            </span>
            <span className="upload-btn-hint">
              JPG, PNG or phone photos are fine
            </span>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="step-card">
      <div className="step-title-row">
        <div>
          <h2 className="step-title">
            <Camera size={26} color="var(--theme-color)" />
            <span>Add a photo of your child</span>
          </h2>
          <p className="step-desc">
            Upload your child's photo. If you named Mum, Dad or anyone else, upload their photo too.
          </p>
        </div>
        <span className="step-badge">Step 3 of 4</span>
      </div>

      <div className="section-explainer" style={{ marginBottom: 16 }}>
        <span className="section-explainer-icon">💡</span>
        <div>
          <strong>Your child's photo is required.</strong> If you typed a family name
          (Mum, Dad, and so on), upload that person's photo here too — Next stays locked until you do.
          <HelpTip text="A clear, front-facing photo of just one person works best. Sunglasses, hats that hide the face, or group photos make the drawings less accurate." />
        </div>
      </div>

      <PhotoTips />

      <div className="photo-cards-grid">
        {enabledFamily.map(renderPhotoCard)}
      </div>

      {lockedFamily.length > 0 && (
        <div className="family-invite">
          <div>
            <strong>Want family in the pictures too?</strong>
            <p>
              Type their names on the first page, then come back and upload a photo for each name.
              Skip names if you only want your child in the book.
            </p>
          </div>
          <button
            type="button"
            className="locked-card-action"
            onClick={onGoToFamily || (goToStep ? () => goToStep(1) : onBack)}
          >
            Add family names
          </button>
        </div>
      )}

      <div className="optional-panel" style={{ marginTop: 28 }}>
        <div className="optional-panel-header" style={{ cursor: 'default' }}>
          <span style={{ fontSize: '1.2rem' }}>🐾</span>
          <span className="optional-panel-title">
            <span>Family pets</span>
            <FieldFlag />
            <span className="optional-panel-sub">
              Optional. A pet can appear on the cover and in the corner of each page.
            </span>
          </span>
          {((formData.pets && formData.pets.length > 0) ? formData.pets : [{ id: 'pet_1', name: '', type: 'Dog' }]).length < 2 && (
            <button
              type="button"
              onClick={handleAddSecondPet}
              className="locked-card-action"
              style={{ marginLeft: 'auto' }}
            >
              <Plus size={14} />
              Add a second pet
            </button>
          )}
        </div>
        <div className="optional-panel-body">
          <div className="photo-cards-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
            {((formData.pets && formData.pets.length > 0)
              ? formData.pets
              : [{ id: 'pet_1', name: '', type: 'Dog' }]
            ).map((pet, idx) => {
              const role = pet.id || `pet_${idx + 1}`;
              const enteredName = (pet.name || '').trim();
              const petType = pet.type || (idx === 1 ? 'Cat' : 'Dog');
              const typeIcon = PET_TYPES.find((t) => t.label === petType)?.icon || '🐾';
              const label = `Pet ${idx + 1}`;
              const uploaded = uploadedFaces[role];
              const isUploading = uploadingRole === role;

              return (
                <div
                  key={role}
                  className={`photo-card ${uploaded ? 'has-photo' : 'is-enabled'}`}
                  style={{ minHeight: '230px', display: 'flex', flexDirection: 'column' }}
                >
                  <input
                    type="file"
                    accept="image/*,.heic,.heif,.webp,.bmp,.tiff,.tif,.gif,.svg"
                    style={{ display: 'none' }}
                    ref={(el) => (fileInputRefs.current[role] = el)}
                    onChange={(e) => handleFileChange(role, e.target.files?.[0])}
                  />

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <div className="photo-card-role" style={{ margin: 0 }}>
                      <span style={{ marginRight: '6px' }}>{typeIcon}</span>
                      <span>{label}</span>
                    </div>
                    {idx === 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemovePetCard(role)}
                        style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', padding: '2px', display: 'flex' }}
                        title="Remove second pet"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>

                  <div style={{ marginBottom: '8px' }}>
                    <input
                      type="text"
                      className="text-input"
                      placeholder={`Pet's name (e.g. ${idx === 0 ? 'Buddy, Max' : 'Milo, Bella'})`}
                      value={pet.name || ''}
                      onChange={(e) => handlePetFieldChange(role, 'name', e.target.value)}
                      style={{ fontSize: '0.82rem', padding: '5px 8px', borderRadius: '6px', border: '1px solid #cbd5e1', width: '100%', boxSizing: 'border-box' }}
                    />
                  </div>

                  <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '10px' }}>
                    {PET_TYPES.map((t) => (
                      <button
                        key={t.label}
                        type="button"
                        onClick={() => handlePetFieldChange(role, 'type', t.label)}
                        style={{
                          padding: '2px 7px',
                          borderRadius: '999px',
                          border: '1px solid',
                          borderColor: petType === t.label ? 'var(--theme-color)' : '#e2e8f0',
                          background: petType === t.label ? 'rgba(99, 102, 241, 0.08)' : '#f8fafc',
                          color: petType === t.label ? 'var(--theme-color)' : '#64748b',
                          fontSize: '0.74rem',
                          fontWeight: petType === t.label ? 700 : 500,
                          cursor: 'pointer',
                        }}
                      >
                        {t.icon} {t.label}
                      </button>
                    ))}
                  </div>

                  <span className={`photo-card-badge ${uploaded ? 'badge-ready' : 'badge-optional'}`} style={{ marginBottom: '8px' }}>
                    {uploaded ? 'Will appear in the book' : 'Photo is optional'}
                  </span>

                  {uploaded ? (
                    <>
                      <div
                        className="photo-preview-wrapper"
                        onClick={() => openPreview(role, enteredName || label, enteredName || 'Pet', typeIcon, uploaded)}
                      >
                        <img src={uploaded.preview_url || uploaded.local_blob} alt={enteredName || label} className="photo-preview-img" />
                        <div className="preview-overlay-zoom">
                          <Eye size={16} />
                          <span>Look closer</span>
                        </div>
                      </div>
                      <div className="photo-actions-row">
                        <button type="button" className="photo-action-btn btn-action-change" onClick={() => fileInputRefs.current[role]?.click()}>
                          <RefreshCw size={11} />
                          <span>Change</span>
                        </button>
                        <button type="button" className="photo-action-btn btn-action-remove" onClick={() => handleRemovePhoto(role)}>
                          <Trash2 size={12} />
                          <span>Remove</span>
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="upload-dropzone" onClick={() => fileInputRefs.current[role]?.click()}>
                      <div className="upload-icon-circle">
                        {isUploading ? <span style={{ fontSize: '1rem' }}>⏳</span> : <Upload size={20} />}
                      </div>
                      <span className="upload-btn-text">
                        {isUploading ? 'Uploading…' : `Add a ${petType.toLowerCase()} photo`}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {stemStats && (stemStats.ready_count > 0 || stemStats.eligible_count > 0) && (
        <div className="stem-stats-banner">
          <div className="stem-stats-info">
            <CheckCircle2 size={20} color="#10b981" />
            <span>Good news — we have plenty of questions for this book.</span>
          </div>
          <div className="stem-stat-pills">
            {familyPhotoCount > 0 && (
              <div className="stat-pill" style={{ color: '#10b981' }}>
                Family photos will be used in the stories
              </div>
            )}
            {stemStats.matched_interests_count > 0 && (
              <div className="stat-pill" style={{ color: '#f59e0b' }}>
                Favourite foods and hobbies will appear
              </div>
            )}
          </div>
        </div>
      )}

      <div className="step-actions has-checklist">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft size={18} />
          <span>Back</span>
        </button>

        <RequirementChecklist
          allDoneText="All needed photos are ready — you can continue."
          items={[
            {
              done: hasChildPhoto,
              label: "Upload your child's photo",
              hint: 'the first card on this page',
              fixLabel: 'Go to photo',
              onFix: () => fileInputRefs.current.user?.click(),
            },
            ...namedFamily.map((person) => ({
              done: Boolean(uploadedFaces[person.role]),
              label: `Upload ${person.label}'s photo (${getRoleEnteredName(person.role)})`,
              hint: 'you typed this name, so a photo is needed',
              fixLabel: 'Go to photo',
              onFix: () => fileInputRefs.current[person.role]?.click(),
            })),
          ]}
        />

        <button
          className="btn-primary"
          onClick={onNext}
          disabled={!canContinue}
          style={{ opacity: canContinue ? 1 : 0.5, cursor: canContinue ? 'pointer' : 'not-allowed' }}
        >
          <span>Next: Check and create</span>
          <ArrowRight size={18} />
        </button>
      </div>

      {previewModalData && (
        <div className="photo-preview-modal-overlay" onClick={() => setPreviewModalData(null)}>
          <div className="photo-preview-modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="preview-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '1.4rem' }}>{previewModalData.icon}</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#1e293b' }}>
                    {previewModalData.label}{previewModalData.enteredName ? ` — ${previewModalData.enteredName}` : ''}
                  </h3>
                  <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                    This is the photo we will draw from
                  </span>
                </div>
              </div>
              <button type="button" className="preview-modal-close" onClick={() => setPreviewModalData(null)}>
                <X size={18} />
              </button>
            </div>

            <div className="preview-modal-body">
              <img src={previewModalData.url} alt={previewModalData.label} className="preview-modal-img" />
            </div>

            <div className="preview-modal-footer">
              <div style={{ fontSize: '0.82rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={15} color="#10b981" />
                <span>{previewModalData.warning ? 'A clearer photo will look better' : 'This photo looks good'}</span>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ padding: '6px 14px', fontSize: '0.85rem' }}
                  onClick={() => {
                    const role = previewModalData.role;
                    setPreviewModalData(null);
                    fileInputRefs.current[role]?.click();
                  }}
                >
                  <RefreshCw size={13} style={{ marginRight: '4px' }} />
                  Change photo
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  style={{ padding: '6px 16px', fontSize: '0.85rem' }}
                  onClick={() => setPreviewModalData(null)}
                >
                  Use this photo
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
