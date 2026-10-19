import React from 'react';
import { User, BookOpen, Camera, Sparkles, Check } from 'lucide-react';

const STEPS = [
  { id: 1, label: 'Your Child', hint: 'Name and a few details' },
  { id: 2, label: 'School Year', hint: 'Year and maths topics' },
  { id: 3, label: 'Photos', hint: 'One photo of your child' },
  { id: 4, label: 'Make the Book', hint: 'Check and create' },
];

export default function StepWizard({ currentStep, setStep, isStepValid }) {
  const progressPercent = ((currentStep - 1) / (STEPS.length - 1)) * 100;
  const current = STEPS.find((s) => s.id === currentStep) || STEPS[0];

  return (
    <div className="stepper-wrap">
      <div className="stepper-container">
        <div className="stepper-progress-line">
          <div
            className="stepper-progress-fill"
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {STEPS.map((s) => {
          const IconComponent = s.id === 1 ? User : s.id === 2 ? BookOpen : s.id === 3 ? Camera : Sparkles;
          const isActive = currentStep === s.id;
          const isCompleted = currentStep > s.id;

          return (
            <div
              key={s.id}
              className={`step-item ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
              onClick={() => {
                if (s.id <= currentStep || isStepValid(currentStep)) {
                  setStep(s.id);
                }
              }}
            >
              <div className="step-circle">
                {isCompleted ? <Check size={18} strokeWidth={3} /> : <IconComponent size={18} />}
              </div>
              <span className="step-label">{s.label}</span>
            </div>
          );
        })}
      </div>
      <p className="stepper-now-hint">
        <strong>Step {current.id} of 4 — {current.label}.</strong> {current.hint}.
      </p>
    </div>
  );
}
