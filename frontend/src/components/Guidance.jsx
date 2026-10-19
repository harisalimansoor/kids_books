import React, { useEffect, useId, useRef, useState } from 'react';
import { HelpCircle, Check, Circle, X, Sparkles, Camera, FileDown, Clock, Sun, UserRound, Ban } from 'lucide-react';

export const ROLE_LABELS = {
  user: 'Child',
  child: 'Child',
  mother: 'Mum',
  father: 'Dad',
  grandmother: 'Grandma',
  grandfather: 'Grandad',
  brother: 'Brother',
  sister: 'Sister',
  uncle: 'Uncle',
  aunt: 'Aunt',
  sibling: 'Sibling',
  pet_1: 'Pet 1',
  pet_2: 'Pet 2',
};

export function roleLabel(role) {
  const key = String(role || '').toLowerCase();
  if (ROLE_LABELS[key]) return ROLE_LABELS[key];
  if (key.startsWith('pet_')) return 'Pet';
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Photo';
}

export const TOPIC_HINTS = {
  number_and_place_value: 'Counting and reading numbers',
  addition: 'Putting numbers together',
  subtraction: 'Taking amounts away',
  addition_and_subtraction: 'Adding and taking away',
  multiplication_and_division: 'Sharing and equal groups',
  multiplication: 'Equal groups',
  division: 'Sharing fairly',
  fractions: 'Halves and quarters',
  fractions_and_decimals: 'Parts of a whole, and decimals',
  fractions_decimals_percentages: 'Fractions, decimals and percent',
  money: 'Coins and prices',
  time: 'Clocks and times of day',
  time_and_routines: 'Morning, night, and daily order',
  geometry: 'Shapes',
  geometry_and_spatial_reasoning: 'Shapes and positions',
  measurement: 'Longer, heavier, fuller',
  measurement_and_comparison: 'Bigger, smaller, heavier, lighter',
  statistics: 'Simple charts',
  counting: 'How many?',
  counting_and_cardinality: 'Counting objects one by one',
  counting_1_to_3: 'Counting 1, 2, 3',
  comparison: 'More, less, bigger, smaller',
  size_and_comparison: 'Big and small',
  colours_and_matching: 'Matching colours',
  more_or_fewer: 'Which group has more?',
  shapes: 'Circle, square, triangle',
  shapes_and_space: 'Shapes around us',
  spatial_and_position: 'In, on, under, next to',
  patterns: 'What comes next?',
  patterns_and_geometry: 'Repeating patterns and shapes',
  sorting_and_classifying: 'What belongs together?',
  number_composition: 'How numbers are made (3 and 2 make 5)',
  daily_routines_and_time: 'Morning, afternoon, night',
  doubles_and_sharing: 'Doubles and sharing equally',
};

export function topicHint(topicId) {
  return TOPIC_HINTS[String(topicId || '').toLowerCase()] || '';
}

export function friendlyProgressMessage(raw, studentName) {
  const name = (studentName || 'your child').trim() || 'your child';
  const text = String(raw || '');
  const lower = text.toLowerCase();
  const pair = text.match(/(\d+)\s*\/\s*(\d+)/);

  if (lower.includes('hooray') || lower.includes('complete')) {
    return `${name}'s book is ready.`;
  }
  if (lower.includes('illustration') || lower.includes('image') || lower.includes('drawing')) {
    return pair ? `Drawing picture ${pair[1]} of ${pair[2]}…` : 'Drawing the pictures…';
  }
  if (lower.includes('stem') || lower.includes('filter') || lower.includes('select')) {
    return `Choosing the right questions for ${name}…`;
  }
  if (lower.includes('mcq') || lower.includes('verif') || lower.includes('option')) {
    return 'Checking every answer is correct…';
  }
  if (lower.includes('cover')) {
    return `Designing ${name}'s front cover…`;
  }
  if (lower.includes('pdf') || lower.includes('compil')) {
    return 'Putting the pages into one book…';
  }
  if (lower.includes('initial') || lower.includes('prepar')) {
    return `Getting ${name}'s book started…`;
  }
  return text || `Working on ${name}'s book…`;
}

/**
 * Small "?" button that reveals a plain-language explanation for a field.
 * Click or keyboard to open; closes on outside click or Escape.
 */
export function HelpTip({ text, label = 'What is this?' }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const tipId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span className="help-tip-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`help-tip-btn ${open ? 'is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        aria-expanded={open}
        aria-controls={tipId}
      >
        <HelpCircle size={15} />
      </button>
      {open && (
        <span className="help-tip-bubble" id={tipId} role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
}

/**
 * Checklist shown beside the "Next" button so a disabled button always
 * explains itself. Items: { done, label, hint, onFix, fixLabel }.
 */
export function RequirementChecklist({ items, allDoneText }) {
  const pending = items.filter((i) => !i.done);

  if (pending.length === 0) {
    return (
      <div className="req-check req-check-done">
        <span className="req-check-icon done">
          <Check size={14} strokeWidth={3} />
        </span>
        <span>{allDoneText || 'All set — you can continue.'}</span>
      </div>
    );
  }

  return (
    <div className="req-check">
      <div className="req-check-head">
        Before you continue, please finish {pending.length === 1 ? 'this' : `these ${pending.length}`}:
      </div>
      <ul className="req-check-list">
        {items.map((item) => (
          <li key={item.label} className={item.done ? 'is-done' : ''}>
            <span className={`req-check-icon ${item.done ? 'done' : ''}`}>
              {item.done ? <Check size={13} strokeWidth={3} /> : <Circle size={9} />}
            </span>
            <span className="req-check-text">
              {item.label}
              {item.hint && !item.done && <em> — {item.hint}</em>}
            </span>
            {!item.done && item.onFix && (
              <button type="button" className="req-check-fix" onClick={item.onFix}>
                {item.fixLabel || 'Fix this'}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Reusable "Optional" / "Required" / "Recommended" chip for section headers. */
export function FieldFlag({ required = false, recommended = false, text }) {
  const kind = required ? 'is-required' : recommended ? 'is-recommended' : 'is-optional';
  return (
    <span className={`field-flag ${kind}`}>
      {text || (required ? 'Required' : recommended ? 'Recommended' : 'Optional')}
    </span>
  );
}

/**
 * First-run explainer on Step 1. Tells a brand-new visitor what this tool
 * makes, what they need to have ready, and how long it takes.
 */
export function HowItWorks() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem('mib_intro_dismissed') === '1';
    } catch {
      return false;
    }
  });

  const hide = () => {
    setDismissed(true);
    try {
      localStorage.setItem('mib_intro_dismissed', '1');
    } catch {
      /* storage blocked — banner simply reappears next visit */
    }
  };

  if (dismissed) {
    return (
      <button type="button" className="how-it-works-reopen" onClick={() => setDismissed(false)}>
        <HelpCircle size={15} />
        <span>How does this work?</span>
      </button>
    );
  }

  return (
    <div className="how-it-works">
      <button type="button" className="how-it-works-close" onClick={hide} aria-label="Hide this introduction">
        <X size={16} />
      </button>

      <div className="how-it-works-head">
        <span className="how-it-works-kicker">
          <Sparkles size={14} />
          <span>New here? Start with this</span>
        </span>
        <h3>We turn your child into the star of their own maths book.</h3>
        <p>
          Answer a few simple questions, upload one photo of your child, and we create a
          printable practice book where your child appears in every picture.
        </p>
      </div>

      <div className="how-it-works-grid">
        <div className="hiw-card">
          <span className="hiw-num">1</span>
          <strong>Tell us about your child</strong>
          <span>Their name, their school year, and what they love — football, pizza, dinosaurs.</span>
        </div>
        <div className="hiw-card">
          <span className="hiw-num">2</span>
          <strong>Upload one clear photo</strong>
          <span>A normal face photo of your child. Family photos are welcome but not required.</span>
        </div>
        <div className="hiw-card">
          <span className="hiw-num">3</span>
          <strong>Download the finished book</strong>
          <span>You get a colourful PDF, ready to print at home or at a print shop.</span>
        </div>
      </div>

      <div className="how-it-works-foot">
        <span className="hiw-foot-item">
          <Camera size={15} />
          <span>You need: <strong>1 photo of your child</strong></span>
        </span>
        <span className="hiw-foot-item">
          <Clock size={15} />
          <span>Takes about <strong>1–2 minutes</strong> to create</span>
        </span>
        <span className="hiw-foot-item">
          <FileDown size={15} />
          <span>You get: <strong>a printable PDF book</strong></span>
        </span>
      </div>
    </div>
  );
}

/** Short photo-quality tips shown on the upload step. */
export function PhotoTips() {
  return (
    <div className="photo-tips" aria-label="How to take a good photo">
      <div className="photo-tip is-good">
        <Sun size={16} />
        <span>Use a bright, clear photo. The face should be easy to see.</span>
      </div>
      <div className="photo-tip is-good">
        <UserRound size={16} />
        <span>Look at the camera. A normal front-facing photo works best.</span>
      </div>
      <div className="photo-tip is-bad">
        <Ban size={16} />
        <span>Avoid dark, blurry, or group photos. One person per picture.</span>
      </div>
    </div>
  );
}
