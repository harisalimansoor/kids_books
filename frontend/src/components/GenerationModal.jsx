import React from 'react';
import { Check, Loader2, Clock } from 'lucide-react';
import { friendlyProgressMessage } from './Guidance';

const PIPELINE_PHASES = [
  {
    key: 'selecting_stems',
    label: 'Choosing the right questions',
    hint: 'Matching the school year, topics, and family you picked',
  },
  {
    key: 'generating_images',
    label: 'Drawing the pictures',
    hint: 'This is the longest step. Please keep this page open.',
  },
  {
    key: 'verifying_mcq',
    label: 'Checking the answers',
    hint: 'Making sure every question has a correct choice',
  },
  {
    key: 'generating_cover',
    label: 'Designing the front cover',
    hint: 'Putting your child on the cover',
  },
  {
    key: 'compiling_pdf',
    label: 'Putting the book together',
    hint: 'Creating the printable PDF',
  },
];

export default function GenerationModal({ jobStatus, studentName }) {
  if (!jobStatus || jobStatus.status === 'completed' || jobStatus.status === 'idle') {
    return null;
  }

  const progress = Math.min(Math.max(jobStatus.progress || 0.05, 0.05), 1.0);
  const percentText = Math.round(progress * 100);
  const currentPhase = jobStatus.phase || 'preparing';
  const displayName = (studentName || 'your child').trim() || 'your child';
  const liveMessage = friendlyProgressMessage(jobStatus.message, displayName);

  const getStepStatus = (phaseKey) => {
    const phaseOrder = [
      'preparing',
      'selecting_stems',
      'generating_images',
      'verifying_mcq',
      'generating_cover',
      'finalizing_cover',
      'compiling_pdf',
      'complete',
    ];
    const mapped = currentPhase === 'finalizing_cover' ? 'generating_cover' : currentPhase;
    const curIdx = phaseOrder.indexOf(mapped);
    const thisIdx = phaseOrder.indexOf(phaseKey);

    if (curIdx > thisIdx) return 'completed';
    if (curIdx === thisIdx || (phaseKey === 'generating_cover' && currentPhase === 'finalizing_cover')) {
      return 'current';
    }
    return 'pending';
  };

  return (
    <div className="modal-overlay">
      <div className="generation-dialog">
        <div className="generation-spinner-box">
          <div className="spinner-outer-ring" />
          <div className="spinner-inner-icon">✨</div>
        </div>

        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.6rem', fontWeight: 800, marginBottom: '6px' }}>
          Making {displayName}'s book
        </h3>
        <p style={{ color: '#64748b', fontSize: '0.94rem' }}>
          Please keep this page open. Pictures usually take about one minute.
        </p>

        <div className="progress-track">
          <div
            className="progress-bar-fill"
            style={{ width: `${percentText}%` }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700, color: 'var(--theme-color)' }}>
          <span>{liveMessage}</span>
          <span>{percentText}%</span>
        </div>

        <div className="pipeline-steps-list">
          {PIPELINE_PHASES.map((step) => {
            const status = getStepStatus(step.key);

            return (
              <div
                key={step.key}
                className={`pipeline-step-row ${status === 'completed' ? 'completed' : status === 'current' ? 'current' : ''}`}
              >
                {status === 'completed' ? (
                  <Check size={16} color="#10b981" strokeWidth={3} />
                ) : status === 'current' ? (
                  <Loader2 size={16} color="var(--theme-color)" className="spin-animation" style={{ animation: 'spinRing 1s linear infinite' }} />
                ) : (
                  <span style={{ width: 16, height: 16, borderRadius: '50%', border: '1.5px solid #cbd5e1', display: 'inline-block' }} />
                )}
                <span className="pipeline-step-copy">
                  <strong>{step.label}</strong>
                  {status === 'current' && <em>{step.hint}</em>}
                </span>
              </div>
            );
          })}
        </div>

        <div className="generation-wait-note">
          <Clock size={15} />
          <span>Do not refresh or close this tab until the book is ready.</span>
        </div>

        {jobStatus.error && (
          <div
            style={{
              marginTop: '20px',
              padding: '12px',
              background: '#fef2f2',
              border: '1px solid #fecdd3',
              borderRadius: '8px',
              color: '#dc2626',
              fontSize: '0.88rem',
            }}
          >
            Something went wrong: {jobStatus.error}
          </div>
        )}
      </div>
    </div>
  );
}
