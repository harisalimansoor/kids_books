import React, { useState, useEffect } from 'react';
import {
  BookOpen, Sparkles, Check, ArrowLeft, ArrowRight, ChevronDown, ChevronUp,
  AlertTriangle, Hash, Plus, X, Trophy, Film, Palette, Utensils, Smile
} from 'lucide-react';
import { HelpTip, RequirementChecklist, FieldFlag, topicHint } from './Guidance';

const QUESTION_PRESETS = [4, 6, 8, 10];

const DEFAULT_FOODS = [
  'Pizza', 'Burger', 'Ice Cream', 'Cupcakes', 'Apples', 'Strawberries',
  'Pancakes', 'Doughnuts', 'Pasta', 'Cookies', 'Sandwiches', 'Popcorn', 'Watermelon'
];

const DEFAULT_HOBBIES = [
  'Gardening', 'Lego & Blocks', 'Painting & Art', 'Drawing', 'Toy Cars',
  'Reading', 'Baking', 'Video Games', 'Board Games', 'Dinosaurs', 'Fishing', 'Music'
];

const DEFAULT_SPORTS = [
  'Football / Soccer', 'Basketball', 'Tennis', 'Swimming', 'Cricket',
  'Gymnastics', 'Cycling', 'Running / Athletics', 'Martial Arts', 'Baseball', 'Roller Skating'
];

const DEFAULT_CHARACTERS = [
  'Spider-Man', 'Batman', 'Elsa (Frozen)', 'Harry Potter', 'Iron Man',
  'Sonic the Hedgehog', 'Super Mario', 'Pikachu', 'Wonder Woman', 'Captain America', 'Barbie'
];

const DEFAULT_CARTOONS = [
  'Paw Patrol', 'Peppa Pig', 'SpongeBob SquarePants', 'Bluey', 'Doraemon',
  'Mickey Mouse', 'Tom & Jerry', 'Pokemon', 'Minions', 'Teen Titans', 'Cocomelon'
];

export default function CurriculumTopicsStep({
  formData,
  updateFormData,
  grades,
  gradeDetail,
  onNext,
  onBack,
}) {
  const [useAllTopics, setUseAllTopics] = useState(false);
  const [customCount, setCustomCount] = useState('');
  // Interests are optional, so the panel starts closed and this page opens short
  // and readable instead of a wall of sixty chips.
  const [showInterests, setShowInterests] = useState(false);

  // Always scroll to top when Curriculum & Topics mounts
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, []);

  const [customInputs, setCustomInputs] = useState({
    favourite_foods: '',
    favourite_hobbies: '',
    favourite_sports: '',
    favourite_characters: '',
    favourite_cartoons: '',
  });

  const [customAddedTags, setCustomAddedTags] = useState({
    favourite_foods: [],
    favourite_hobbies: [],
    favourite_sports: [],
    favourite_characters: [],
    favourite_cartoons: [],
  });

  const selectedGradeObj = grades.find((g) => g.id === formData.grade_id);
  const isAvailable = selectedGradeObj ? selectedGradeObj.available : false;

  // Resolve topics instantly from gradeDetail or selectedGradeObj without network lag
  const activeTopics = (gradeDetail?.grade_id === formData.grade_id && gradeDetail?.topics?.length > 0)
    ? gradeDetail.topics
    : (selectedGradeObj?.topics || []);

  const handleGradeChange = (gradeId) => {
    const sel = grades.find((g) => g.id === gradeId);
    const defaultTopics = sel?.topics?.[0] ? [sel.topics[0].id] : [];
    updateFormData({
      grade_id: gradeId,
      grade_label: sel ? sel.display_name : gradeId,
      selected_topics: defaultTopics,
      favourite_foods: [],
      favourite_hobbies: [],
      favourite_sports: [],
      favourite_characters: [],
      favourite_cartoons: [],
    });
    setUseAllTopics(false);
  };

  const handleTopicToggle = (topicId) => {
    if (useAllTopics) return;
    const current = formData.selected_topics || [];
    if (current.includes(topicId)) {
      updateFormData({ selected_topics: current.filter((t) => t !== topicId) });
    } else {
      updateFormData({ selected_topics: [...current, topicId] });
    }
  };

  const toggleAllTopics = () => {
    if (!useAllTopics) {
      const allIds = (activeTopics || []).map((t) => t.id);
      updateFormData({ selected_topics: allIds });
      setUseAllTopics(true);
    } else {
      updateFormData({ selected_topics: activeTopics?.[0] ? [activeTopics[0].id] : [] });
      setUseAllTopics(false);
    }
  };

  const handleTagToggle = (field, item) => {
    const current = formData[field] || [];
    if (current.includes(item)) {
      updateFormData({ [field]: current.filter((x) => x !== item) });
    } else {
      updateFormData({ [field]: [...current, item] });
    }
  };

  const handleAddCustomTag = (field) => {
    const raw = (customInputs[field] || '').trim();
    if (!raw) return;
    const val = raw.charAt(0).toUpperCase() + raw.slice(1);
    const current = formData[field] || [];
    if (!current.includes(val)) {
      updateFormData({ [field]: [...current, val] });
    }
    setCustomAddedTags((prev) => ({
      ...prev,
      [field]: prev[field].includes(val) ? prev[field] : [...prev[field], val],
    }));
    setCustomInputs((prev) => ({ ...prev, [field]: '' }));
  };

  const handleRemoveCustomTag = (field, tag, e) => {
    e.stopPropagation();
    const current = formData[field] || [];
    updateFormData({ [field]: current.filter((t) => t !== tag) });
    setCustomAddedTags((prev) => ({
      ...prev,
      [field]: prev[field].filter((t) => t !== tag),
    }));
  };

  const handleCustomCountChange = (e) => {
    const val = e.target.value;
    setCustomCount(val);
    const num = parseInt(val, 10);
    if (!isNaN(num) && num >= 1 && num <= 20) {
      updateFormData({ num_questions: num });
    }
  };

  const handlePresetClick = (num) => {
    setCustomCount('');
    updateFormData({ num_questions: num });
  };

  const isCustomActive = customCount !== '' && !QUESTION_PRESETS.includes(formData.num_questions);

  const INTEREST_FIELDS = [
    'favourite_foods',
    'favourite_hobbies',
    'favourite_sports',
    'favourite_characters',
    'favourite_cartoons',
  ];

  const topicCount = (formData.selected_topics || []).length;
  const interestCount = INTEREST_FIELDS.reduce(
    (sum, field) => sum + (formData[field] || []).length,
    0
  );

  const isValid =
    isAvailable &&
    formData.grade_id &&
    formData.selected_topics &&
    formData.selected_topics.length > 0;

  // Build combined options for each category
  const renderCategory = (
    field,
    label,
    icon,
    hint,
    defaultList,
    placeholder
  ) => {
    const apiList = field === 'favourite_foods'
      ? (gradeDetail?.available_foods || [])
      : field === 'favourite_hobbies'
      ? (gradeDetail?.available_hobbies || [])
      : [];

    const mergedPresets = Array.from(new Set([...apiList, ...defaultList]));
    const customList = customAddedTags[field] || [];
    const allOptions = Array.from(new Set([...mergedPresets, ...customList]));
    const selected = formData[field] || [];

    return (
      <div className="interest-section-box">
        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {icon}
          <span>{label}</span>
          {selected.length > 0 && (
            <span className="interest-count-pill">{selected.length}</span>
          )}
        </label>
        <span className="form-hint">{hint}</span>

        <div className="tags-cloud">
          {allOptions.map((item) => {
            const isSel = selected.includes(item);
            const isCustom = customList.includes(item);
            return (
              <div
                key={item}
                className={`tag-pill ${isSel ? 'selected' : ''}`}
                onClick={() => handleTagToggle(field, item)}
              >
                <span>{item}</span>
                {isCustom && (
                  <span
                    className="tag-pill-remove"
                    title="Remove custom tag"
                    onClick={(e) => handleRemoveCustomTag(field, item, e)}
                  >
                    <X size={12} strokeWidth={3} />
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* Custom Input Row */}
        <div className="custom-tag-row">
          <input
            type="text"
            className="custom-tag-input"
            placeholder={placeholder}
            value={customInputs[field]}
            onChange={(e) => setCustomInputs((prev) => ({ ...prev, [field]: e.target.value }))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleAddCustomTag(field);
              }
            }}
          />
          <button
            type="button"
            className="custom-tag-btn"
            onClick={() => handleAddCustomTag(field)}
          >
            <Plus size={14} />
            <span>Add</span>
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="step-card">
      <div className="step-title-row">
        <div>
          <h2 className="step-title">
            <BookOpen size={26} color="var(--theme-color)" />
            <span>What Should the Book Practise?</span>
          </h2>
          <p className="step-desc">
            Pick your child's school year and at least one maths topic. That's all this page needs.
          </p>
        </div>
        <span className="step-badge">Step 2 of 4</span>
      </div>

      <div className="form-grid-2">
        {/* Year Group Selector */}
        <div className="form-group">
          <label className="form-label">
            School Year <span className="required">*</span>
            <HelpTip text="Pick the class your child is in right now. The sums are kept at the right level for that year — Grade 1 stays within 20, for example." />
          </label>
          <select
            className="select-input"
            value={formData.grade_id}
            onChange={(e) => handleGradeChange(e.target.value)}
          >
            <option value="">Select Grade</option>
            {grades.map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
          </select>
          <span className="form-hint">
            Not sure? Choose the year they are in at school now.
          </span>
        </div>

        {/* Number of Questions */}
        <div className="form-group">
          <label className="form-label">
            <Hash size={16} />
            <span>How Many Questions?</span>
            <HelpTip text="Each question gets its own full page with a picture. Six questions makes a book of about eight pages including the covers." />
          </label>
          <div className="number-presets">
            {QUESTION_PRESETS.map((num) => (
              <div
                key={num}
                className={`preset-chip ${formData.num_questions === num && !isCustomActive ? 'selected' : ''}`}
                onClick={() => handlePresetClick(num)}
              >
                {num}{num === 6 ? ' ★' : ''}
              </div>
            ))}
            <div
              className={`preset-chip custom-count-chip ${isCustomActive ? 'selected' : ''}`}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: '80px' }}
            >
              <input
                type="number"
                min="1"
                max="20"
                placeholder="Custom"
                value={customCount}
                onChange={handleCustomCountChange}
                className="custom-count-input"
              />
            </div>
          </div>
          <span className="form-hint">
            6 (the star) is a good first book — one short practice session.
          </span>
        </div>
      </div>

      {/* Grade has no question bank yet — say so instead of showing an empty page */}
      {formData.grade_id && !isAvailable && (
        <div className="req-check" style={{ marginTop: '8px' }}>
          <div className="req-check-head" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={16} />
            <span>We don't have questions for this school year yet.</span>
          </div>
          <span style={{ fontSize: '0.86rem' }}>
            Please choose a different year above. Nursery, Prep, Kindergarten and Grades 1 to 5
            are all ready to use.
          </span>
        </div>
      )}

      {/* Curriculum Topics Selection */}
      {isAvailable && activeTopics.length > 0 && (
        <div className="form-group" style={{ marginTop: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
            <label className="form-label" style={{ margin: 0 }}>
              <span>Maths Topics</span> <span className="required">*</span>
              <HelpTip text="Tick the kinds of sums you want in the book. Tick several and the questions are spread evenly across them." />
              {topicCount > 0 && (
                <span className="interest-count-pill">{topicCount} picked</span>
              )}
            </label>
            <button
              type="button"
              className="toggle-all-btn"
              onClick={toggleAllTopics}
            >
              {useAllTopics ? 'Clear Topics' : 'Select All Topics'}
            </button>
          </div>

          <span className="form-hint" style={{ marginBottom: '10px' }}>
            {topicCount > 0
              ? 'Tap a topic again to remove it.'
              : 'Tap at least one topic to continue.'}
          </span>

          <div className="topics-grid">
            {activeTopics.map((t) => {
              const isSelected = useAllTopics || (formData.selected_topics || []).includes(t.id);
              return (
                <div
                  key={t.id}
                  className={`topic-chip ${isSelected ? 'selected' : ''}`}
                  onClick={() => handleTopicToggle(t.id)}
                >
                  <div className="topic-checkbox">
                    {isSelected && <Check size={12} strokeWidth={3} />}
                  </div>
                  <span className="topic-chip-text">
                    <span>{t.label}</span>
                    {topicHint(t.id) && <span className="topic-chip-hint">{topicHint(t.id)}</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Child Interests: Foods, Hobbies, Sports, Characters, Cartoons */}
      {isAvailable && (
        <div className={`optional-panel ${showInterests ? 'is-open' : ''}`}>
          <button
            type="button"
            className="optional-panel-header"
            onClick={() => setShowInterests((v) => !v)}
            aria-expanded={showInterests}
          >
            <Sparkles size={20} color="var(--theme-color)" style={{ flexShrink: 0 }} />
            <span className="optional-panel-title">
              <span>Things Your Child Loves</span>
              <FieldFlag />
              {interestCount > 0 && (
                <span className="interest-count-pill">{interestCount} picked</span>
              )}
              <span className="optional-panel-sub">
                {interestCount > 0
                  ? 'These now appear in the stories and pictures.'
                  : 'Add favourite foods, sports or cartoons and they appear inside the questions. Skip it and the book still works.'}
              </span>
            </span>
            <span className="optional-panel-spacer" />
            {showInterests
              ? <ChevronUp size={20} color="#64748b" />
              : <ChevronDown size={20} color="#64748b" />}
          </button>

          {showInterests && (
          <div className="optional-panel-body">
          <div className="section-explainer" style={{ marginBottom: '18px' }}>
            <span className="section-explainer-icon">💡</span>
            <div>
              <strong>What this does.</strong> If you tick “Pizza” and “Football”, a question can
              become “Leo shares 8 slices of pizza…” and the picture will be drawn on a football
              pitch. The sums and answers never change — only the story around them.
            </div>
          </div>

          <div className="form-grid-2">
            {/* Foods */}
            {renderCategory(
              'favourite_foods',
              'Favourite Foods',
              <Utensils size={18} color="#f97316" />,
              'Used as the things being counted and shared in the sums.',
              DEFAULT_FOODS,
              '+ Add custom food (e.g. Sushi, Tacos)...'
            )}

            {/* Hobbies & Toys */}
            {renderCategory(
              'favourite_hobbies',
              'Hobbies & Toys',
              <Palette size={18} color="#8b5cf6" />,
              'Sets the scene — a garden, a Lego table, an art corner.',
              DEFAULT_HOBBIES,
              '+ Add custom hobby or toy...'
            )}

            {/* Sports */}
            {renderCategory(
              'favourite_sports',
              'Favourite Sports',
              <Trophy size={18} color="#eab308" />,
              'Puts the questions on a pitch, court or in the pool.',
              DEFAULT_SPORTS,
              '+ Add custom sport (e.g. Karate, Golf)...'
            )}

            {/* Famous Characters */}
            {renderCategory(
              'favourite_characters',
              'Famous Characters',
              <Smile size={18} color="#ec4899" />,
              'Adds a small character badge to the top of each page.',
              DEFAULT_CHARACTERS,
              '+ Add custom character (e.g. Goku, Sonic)...'
            )}

            {/* Cartoons */}
            {renderCategory(
              'favourite_cartoons',
              'Cartoons & Animation',
              <Film size={18} color="#3b82f6" />,
              'Adds a cartoon badge and cartoon-themed toys to the pages.',
              DEFAULT_CARTOONS,
              '+ Add custom cartoon (e.g. Ben 10, Dora)...'
            )}
          </div>

          {/* Extra Notes for AI Pictures */}
          <div className="form-group" style={{ marginTop: '22px', marginBottom: 0 }}>
            <label className="form-label">
              Anything else we should draw?
              <FieldFlag />
              <HelpTip text="A free-text note for the illustrator. Write it the way you would say it out loud, for example 'loves dinosaurs' or 'put the scene in a sunny park'." />
            </label>
            <input
              type="text"
              className="text-input"
              placeholder="e.g. loves dinosaurs, a sunny park, a space rocket"
              value={formData.anything_else}
              onChange={(e) => updateFormData({ anything_else: e.target.value })}
            />
          </div>
          </div>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="step-actions has-checklist">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft size={18} />
          <span>Back</span>
        </button>

        <RequirementChecklist
          allDoneText="Great — ready for the photos."
          items={[
            {
              done: Boolean(formData.grade_id) && isAvailable,
              label: 'Choose a school year we cover',
              hint: 'the dropdown at the top of this page',
            },
            {
              done: topicCount > 0,
              label: 'Tick at least one maths topic',
              hint: 'tap any topic box above',
            },
          ]}
        />

        <button
          className="btn-primary"
          onClick={onNext}
          disabled={!isValid}
          style={{ opacity: isValid ? 1 : 0.5, cursor: isValid ? 'pointer' : 'not-allowed' }}
        >
          <span>Next: Add Photos</span>
          <ArrowRight size={18} />
        </button>
      </div>
    </div>
  );
}
