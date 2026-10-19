import React, { useEffect, useState, useRef } from 'react';
import './App.css';
import Header from './components/Header';
import StepWizard from './components/StepWizard';
import ChildProfileStep from './components/ChildProfileStep';
import CurriculumTopicsStep from './components/CurriculumTopicsStep';
import PhotoUploadStep from './components/PhotoUploadStep';
import ReviewGenerateStep from './components/ReviewGenerateStep';
import GenerationModal from './components/GenerationModal';
import SuccessModal from './components/SuccessModal';
import AdminAuthModal from './components/AdminAuthModal';
import AdminPanel from './admin/AdminPanel';
import PublicFeedbackPage from './pages/PublicFeedbackPage';

const INITIAL_FORM = {
  job_id: '',
  student_name: '',
  gender: '',
  subject: 'Math',
  child_age: 6,
  fav_color: '#0ea5e9',
  family_names: {
    mother: '',
    father: '',
    grandmother: '',
    grandfather: '',
    brother: '',
    sister: '',
    uncle: '',
    aunt: '',
  },
  pets: [
    { id: 'pet_1', name: '', type: 'Dog' },
  ],
  grade_id: 'Grade_1',
  grade_label: 'Grade 1',
  num_questions: 6,
  counting_ability: 20,
  selected_topics: [],
  favourite_foods: [],
  favourite_hobbies: [],
  favourite_sports: [],
  favourite_characters: [],
  favourite_cartoons: [],
  anything_else: '',
  include_images: true,
  location: '',
};

function initialView() {
  const path = window.location.pathname || '';
  if (path.startsWith('/feedback/')) return 'feedback';
  if (path.startsWith('/admin')) return 'admin';
  return 'app';
}

export default function App() {
  const [view, setView] = useState(initialView);
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState(INITIAL_FORM);
  const [grades, setGrades] = useState([]);
  const [gradeDetail, setGradeDetail] = useState(null);
  const [uploadedFaces, setUploadedFaces] = useState({});
  const [stemStats, setStemStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showAdminAuthModal, setShowAdminAuthModal] = useState(false);
  const pollTimerRef = useRef(null);
  const gradeDetailsCache = useRef({});

  // Initialize job_id on client
  useEffect(() => {
    const randomSuffix = Math.floor(100000 + Math.random() * 900000);
    setFormData((prev) => ({
      ...prev,
      job_id: `WB_${randomSuffix}`,
    }));

    // Fetch API health
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setHealth(data))
      .catch((err) => console.warn('API health check error:', err));

    // Fetch grades list with pre-attached topics
    fetch('/api/grades')
      .then((res) => res.json())
      .then((data) => {
        const list = data.grades || [];
        setGrades(list);
        list.forEach((g) => {
          gradeDetailsCache.current[g.id] = {
            grade_id: g.id,
            available: g.available,
            topics: g.topics || [],
            available_foods: [],
            available_hobbies: [],
            features: {},
          };
        });

        // Set Grade_1 as default if available
        const g1 = list.find((g) => g.id === 'Grade_1');
        if (g1) {
          const defaultTopics = g1.topics?.[0] ? [g1.topics[0].id] : [];
          setFormData((prev) => ({
            ...prev,
            grade_id: g1.id,
            grade_label: g1.display_name,
            selected_topics: prev.selected_topics?.length > 0 ? prev.selected_topics : defaultTopics,
          }));
          if (gradeDetailsCache.current[g1.id]) {
            setGradeDetail(gradeDetailsCache.current[g1.id]);
          }
        }
      })
      .catch((err) => console.error('Failed to load grades:', err));

    const onPop = () => setView(initialView());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // Always scroll window to top whenever step or view changes
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [step, view]);

  // Fetch grade details whenever grade_id changes — instantaneous cache lookup!
  useEffect(() => {
    if (!formData.grade_id) return;

    // 1. Immediately apply cached/catalog grade detail so topics update with 0ms delay
    if (gradeDetailsCache.current[formData.grade_id]) {
      const cached = gradeDetailsCache.current[formData.grade_id];
      setGradeDetail(cached);
    } else {
      const matched = grades.find((g) => g.id === formData.grade_id);
      if (matched && matched.topics?.length > 0) {
        const initial = {
          grade_id: matched.id,
          available: matched.available,
          topics: matched.topics,
          available_foods: [],
          available_hobbies: [],
          features: {},
        };
        gradeDetailsCache.current[matched.id] = initial;
        setGradeDetail(initial);
      }
    }

    // 2. Background enrich to update foods, hobbies, and features seamlessly
    fetch(`/api/grade/${formData.grade_id}`)
      .then((res) => res.json())
      .then((detail) => {
        gradeDetailsCache.current[formData.grade_id] = detail;
        setGradeDetail(detail);
      })
      .catch((err) => console.error('Failed to load grade detail:', err));
  }, [formData.grade_id, grades]);

  // Fetch stem statistics whenever criteria change with a small debounce
  useEffect(() => {
    if (!formData.grade_id || !gradeDetail?.available) {
      setStemStats(null);
      return;
    }

    const timer = setTimeout(() => {
      const availableAdultRoles = Object.keys(uploadedFaces).filter(
        (r) => r !== 'user' && r !== 'child'
      );
      const hasChildPhoto = Boolean(uploadedFaces.user);
      const hasSiblingPhoto = Boolean(
        uploadedFaces.sibling || uploadedFaces.brother || uploadedFaces.sister
      );

      fetch('/api/stems/stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade_id: formData.grade_id,
          selected_topics: formData.selected_topics || [],
          counting_ability: formData.counting_ability || 20,
          available_adult_roles: availableAdultRoles,
          has_child_photo: hasChildPhoto,
          has_sibling_photo: hasSiblingPhoto,
          favourite_foods: formData.favourite_foods || [],
          favourite_hobbies: formData.favourite_hobbies || [],
          favourite_sports: formData.favourite_sports || [],
          favourite_characters: formData.favourite_characters || [],
          favourite_cartoons: formData.favourite_cartoons || [],
          gender: formData.gender,
        }),
      })
        .then((res) => res.json())
        .then((data) => setStemStats(data))
        .catch((err) => console.warn('Stats fetch warning:', err));
    }, 200);

    return () => clearTimeout(timer);
  }, [
    formData.grade_id,
    formData.selected_topics,
    formData.counting_ability,
    formData.favourite_foods,
    formData.favourite_hobbies,
    formData.favourite_sports,
    formData.favourite_characters,
    formData.favourite_cartoons,
    formData.gender,
    uploadedFaces,
    gradeDetail?.available,
  ]);


  const updateFormData = (fields) => {
    setFormData((prev) => ({ ...prev, ...fields }));
  };

  const isStepValid = (stepNum) => {
    if (stepNum === 1) {
      return formData.student_name.trim().length > 0 && formData.gender !== 'Select';
    }
    if (stepNum === 2) {
      return (
        gradeDetail?.available &&
        formData.grade_id &&
        formData.selected_topics &&
        formData.selected_topics.length > 0
      );
    }
    if (stepNum === 3) {
      const namedRoles = Object.entries(formData.family_names || {}).filter(
        ([, name]) => (name || '').trim().length > 0
      );
      const familyPhotosReady = namedRoles.every(([role]) => Boolean(uploadedFaces[role]));
      return Boolean(uploadedFaces.user) && familyPhotosReady;
    }
    return true;
  };

  // Launch Generation Pipeline
  const handleStartGeneration = async () => {
    setIsGenerating(true);
    setJobStatus({
      job_id: formData.job_id,
      status: 'starting',
      phase: 'preparing',
      progress: 0.05,
      message: 'Submitting workbook task to AI engine...',
    });

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Generation request failed');
      }

      // Start polling status
      pollJobStatus(formData.job_id);
    } catch (err) {
      console.error(err);
      setIsGenerating(false);
      setJobStatus({
        status: 'failed',
        error: err.message,
        message: 'Generation failed to start.',
      });
    }
  };

  const pollJobStatus = (jobId) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);

    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}/status`);
        if (!res.ok) return;

        const data = await res.json();
        setJobStatus(data);

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollTimerRef.current);
          setIsGenerating(false);
        }
      } catch (e) {
        console.warn('Poll error:', e);
      }
    }, 1500);
  };

  const handleReset = () => {
    const randomSuffix = Math.floor(100000 + Math.random() * 900000);
    setFormData({
      ...INITIAL_FORM,
      job_id: `WB_${randomSuffix}`,
    });
    setUploadedFaces({});
    setJobStatus(null);
    setStep(1);
    document.documentElement.style.setProperty('--theme-color', '#6366f1');
    document.documentElement.style.setProperty('--theme-color-glow', 'rgba(99, 102, 241, 0.35)');
  };

  const isAdminAuthenticated = () => {
    return (
      sessionStorage.getItem('admin_auth') === 'true' ||
      localStorage.getItem('admin_auth') === 'true'
    );
  };

  const handleLogoTripleClick = () => {
    if (isAdminAuthenticated()) {
      window.history.pushState({}, '', '/admin');
      setView('admin');
    } else {
      setShowAdminAuthModal(true);
    }
  };

  const handleAdminAuthSuccess = () => {
    setShowAdminAuthModal(false);
    window.history.pushState({}, '', '/admin');
    setView('admin');
  };

  const closeAdmin = () => {
    window.history.pushState({}, '', '/');
    setView('app');
  };

  const logoutAdmin = () => {
    sessionStorage.removeItem('admin_auth');
    localStorage.removeItem('admin_auth');
    sessionStorage.removeItem('admin_token');
    sessionStorage.removeItem('admin_email');
    localStorage.removeItem('admin_email');
    closeAdmin();
  };

  const feedbackToken = (window.location.pathname || '').startsWith('/feedback/')
    ? window.location.pathname.replace('/feedback/', '').split('/')[0]
    : '';

  if (view === 'feedback') {
    return <PublicFeedbackPage token={feedbackToken} />;
  }

  if (view === 'admin') {
    if (!isAdminAuthenticated()) {
      return (
        <AdminAuthModal
          open={true}
          onClose={() => {
            window.history.pushState({}, '', '/');
            setView('app');
          }}
          onSuccess={() => {
            setView('admin');
          }}
        />
      );
    }
    return <AdminPanel onClose={closeAdmin} onLogout={logoutAdmin} />;
  }

  return (
    <>
      {/* Ambient Animated Background Orbs */}
      <div className="bg-ambient">
        <div className="ambient-orb ambient-orb-1" />
        <div className="ambient-orb ambient-orb-2" />
        <div className="ambient-orb ambient-orb-3" />

        {/* Floating Math Symbols */}
        <span className="floating-symbol" style={{ top: '15%', left: '8%' }}>+</span>
        <span className="floating-symbol" style={{ top: '35%', right: '10%', animationDelay: '-3s' }}>×</span>
        <span className="floating-symbol" style={{ top: '65%', left: '12%', animationDelay: '-7s' }}>÷</span>
        <span className="floating-symbol" style={{ top: '80%', right: '14%', animationDelay: '-11s' }}>=</span>
        <span className="floating-symbol" style={{ top: '25%', right: '28%', animationDelay: '-5s' }}>−</span>
        <span className="floating-symbol" style={{ top: '50%', left: '4%', animationDelay: '-9s' }}>★</span>
      </div>

      <div className="app-container">
        {/* Header */}
        <Header health={health} themeColor={formData.fav_color} onLogoTripleClick={handleLogoTripleClick} />

        {/* 4-Step Interactive Stepper */}
        <StepWizard
          currentStep={step}
          setStep={setStep}
          isStepValid={isStepValid}
        />

        {/* Step 1: Child Profile */}
        {step === 1 && (
          <ChildProfileStep
            formData={formData}
            updateFormData={updateFormData}
            uploadedFaces={uploadedFaces}
            setUploadedFaces={setUploadedFaces}
            onNext={() => setStep(2)}
          />
        )}

        {/* Step 2: Curriculum & Topics */}
        {step === 2 && (
          <CurriculumTopicsStep
            formData={formData}
            updateFormData={updateFormData}
            grades={grades}
            gradeDetail={gradeDetail}
            onNext={() => setStep(3)}
            onBack={() => setStep(1)}
          />
        )}

        {/* Step 3: Character Photos */}
        {step === 3 && (
          <PhotoUploadStep
            formData={formData}
            updateFormData={updateFormData}
            uploadedFaces={uploadedFaces}
            setUploadedFaces={setUploadedFaces}
            stemStats={stemStats}
            onNext={() => setStep(4)}
            onBack={() => setStep(2)}
            goToStep={setStep}
          />
        )}

        {/* Step 4: Review & Generate */}
        {step === 4 && (
          <ReviewGenerateStep
            formData={formData}
            uploadedFaces={uploadedFaces}
            gradeDetail={gradeDetail}
            onGenerate={handleStartGeneration}
            onBack={() => setStep(3)}
            goToStep={setStep}
            isGenerating={isGenerating}
          />
        )}

        {/* Live Generation Progress Modal */}
        <GenerationModal
          jobStatus={jobStatus}
          studentName={formData.student_name}
        />

        {/* Celebratory Success Modal */}
        <SuccessModal
          jobStatus={jobStatus}
          onReset={handleReset}
          onClose={() => setJobStatus(null)}
          jobId={formData.job_id}
        />

        {/* Triple-Click Admin Login Authentication Gate */}
        <AdminAuthModal
          open={showAdminAuthModal}
          onClose={() => setShowAdminAuthModal(false)}
          onSuccess={handleAdminAuthSuccess}
        />
      </div>
    </>
  );
}
