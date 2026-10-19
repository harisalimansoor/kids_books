import React, { useEffect, useState } from 'react';
import confetti from 'canvas-confetti';
import {
  Download,
  ExternalLink,
  RotateCcw,
  CheckCircle2,
  BookOpen,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileText,
  Layers,
  Maximize2,
  Minimize2,
  X,
} from 'lucide-react';
import EmailGateModal from './EmailGateModal';

export default function SuccessModal({ jobStatus, onReset, onClose, jobId: jobIdProp }) {
  const handleCloseModal = onClose || onReset;
  const [activeTab, setActiveTab] = useState('book'); // 'book', 'pdf', 'questions'
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showAllQuestions, setShowAllQuestions] = useState(true);
  const [emailGateOpen, setEmailGateOpen] = useState(false);

  useEffect(() => {
    // 1. Fire Confetti Cannon
    try {
      const count = 200;
      const defaults = {
        origin: { y: 0.7 },
        colors: ['#6366f1', '#10b981', '#f43f5e', '#f59e0b', '#06b6d4'],
      };

      const fire = (particleRatio, opts) => {
        confetti({
          ...defaults,
          ...opts,
          particleCount: Math.floor(count * particleRatio),
        });
      };

      fire(0.25, { spread: 26, startVelocity: 55 });
      fire(0.2, { spread: 60 });
      fire(0.35, { spread: 100, decay: 0.91, scalar: 0.8 });
      fire(0.1, { spread: 120, startVelocity: 25, decay: 0.92, scalar: 1.2 });
      fire(0.1, { spread: 120, startVelocity: 45 });
    } catch (e) {
      console.warn('Confetti effect failed', e);
    }

    // 2. Play celebratory harmonic synth chime using Web Audio API
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        const ctx = new AudioContext();
        const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
        notes.forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'triangle';
          osc.frequency.value = freq;
          gain.gain.setValueAtTime(0.001, ctx.currentTime + i * 0.1);
          gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + i * 0.1 + 0.05);
          gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.1 + 0.8);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(ctx.currentTime + i * 0.1);
          osc.stop(ctx.currentTime + i * 0.1 + 0.85);
        });
      }
    } catch (e) {
      // Audio autoplay policy fallback
    }
  }, []);

  if (!jobStatus || jobStatus.status !== 'completed') {
    return null;
  }

  const items = jobStatus.items || [];
  const coverUrl = jobStatus.cover_url;
  const pdfUrl = jobStatus.pdf_url;
  const filename = jobStatus.pdf_filename || 'MyInteliBooks_Workbook.pdf';
  const jobId = jobStatus.job_id || jobIdProp;

  const requestPdf = (event) => {
    if (event) event.preventDefault();
    if (!pdfUrl || !jobId) return;
    setEmailGateOpen(true);
  };

  // Construct full book pages sequence:
  // Page 1: Front Cover
  // Pages 2..N+1: Questions
  // Page N+2: Back Cover
  const bookPages = [
    {
      type: 'cover',
      pageNum: 1,
      pageLabel: 'Front cover',
      title: 'Page 1 — Front cover',
      image: coverUrl,
      desc: `${jobStatus.student_name || 'Your child'} is on the cover of this book.`,
    },
    ...items.map((it, idx) => {
      const topicLabel = it.topic_label || it.topic || `Math Question ${idx + 1}`;
      const questionText = it.question || it.question_text || 'Interactive personalized problem';
      const ans = it.correct !== undefined && it.correct !== null && it.correct !== ''
        ? String(it.correct)
        : String(it.correct_answer || it.answer || (Array.isArray(it.options) && it.options[0]) || 'Option A');
      const optionsArr = Array.isArray(it.options) ? it.options : (it.options?.options || []);

      return {
        type: 'question',
        pageNum: idx + 2,
        pageLabel: `Page ${idx + 2}`,
        title: `Page ${idx + 2}: ${topicLabel}`,
        image: it.image_url,
        item: {
          ...it,
          topic_label: topicLabel,
          question: questionText,
          correct: ans,
          options: optionsArr,
        },
      };
    }),
    {
      type: 'backcover',
      pageNum: items.length + 2,
      pageLabel: 'Back cover',
      title: `Page ${items.length + 2} — Back cover`,
      image: '/api/backcover',
      desc: 'The last page of the book.',
    },
  ];

  const currentPage = bookPages[currentPageIndex] || bookPages[0];

  const handlePrevPage = () => {
    setCurrentPageIndex((prev) => (prev > 0 ? prev - 1 : bookPages.length - 1));
  };

  const handleNextPage = () => {
    setCurrentPageIndex((prev) => (prev < bookPages.length - 1 ? prev + 1 : 0));
  };

  return (
    <div className="modal-overlay">
      <div className={`success-dialog ${isFullscreen ? 'dialog-fullscreen' : ''}`}>
        {/* Top-Right Close Cross Icon */}
        <button
          type="button"
          className="btn-dialog-close"
          onClick={handleCloseModal}
          title="Close Window"
          aria-label="Close Window"
        >
          <X size={20} />
        </button>

        {/* Celebration Header */}
        <div className="success-header-decor">
          <div className="celebration-badge">
            <Sparkles size={16} color="#059669" />
            <span>The book is ready</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
            <div>
              <h2 className="success-title">
                {jobStatus.student_name ? `${jobStatus.student_name}'s book is ready` : 'Your book is ready'} 🌟
              </h2>
              <p style={{ color: '#64748b', fontSize: '1.02rem', marginTop: '4px', marginBottom: 0 }}>
                Look through the pages below, then download the PDF to print.
              </p>
            </div>
            {/* Quick Actions */}
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              {pdfUrl && (
                <button
                  type="button"
                  className="btn-download-pdf"
                  style={{ padding: '10px 18px', fontSize: '0.92rem' }}
                  onClick={requestPdf}
                >
                  <Download size={18} />
                  <span>Download the book</span>
                </button>
              )}
              {pdfUrl && (
                <button
                  type="button"
                  className="btn-view-pdf"
                  style={{ padding: '10px 16px', fontSize: '0.92rem' }}
                  onClick={requestPdf}
                >
                  <ExternalLink size={16} />
                  <span>Open PDF</span>
                </button>
              )}
              <button
                type="button"
                className="btn-icon-fullscreen"
                onClick={() => setIsFullscreen(!isFullscreen)}
                title={isFullscreen ? 'Exit Fullscreen' : 'Enlarge Preview'}
              >
                {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              </button>
              <button
                type="button"
                className="btn-header-close"
                onClick={handleCloseModal}
                title="Close Window"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '9px 14px',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                  background: '#f8fafc',
                  color: '#475569',
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                <X size={16} />
                <span>Close</span>
              </button>
            </div>
          </div>
        </div>

        {/* Stats Summary Strip */}
        <div className="stats-summary-strip">
          <div className="stat-strip-item">
            <span className="stat-strip-num">{items.length}</span>
            <span className="stat-strip-label">Questions</span>
          </div>
          <div className="stat-strip-item">
            <span className="stat-strip-num">{bookPages.length}</span>
            <span className="stat-strip-label">Pages in the book</span>
          </div>
          <div className="stat-strip-item">
            <span className="stat-strip-num">A4</span>
            <span className="stat-strip-label">Ready to print</span>
          </div>
          <div className="stat-strip-item">
            <span className="stat-strip-num">{jobStatus.student_name || 'Child'}</span>
            <span className="stat-strip-label">Made for this child</span>
          </div>
        </div>

        {/* Preview Mode Navigation Tabs */}
        <div className="workbook-preview-tabs">
          <button
            type="button"
            className={`preview-tab-btn ${activeTab === 'book' ? 'active' : ''}`}
            onClick={() => setActiveTab('book')}
          >
            <BookOpen size={17} />
            <span>Look through the pages</span>
            <span className="tab-pill-count">{bookPages.length} pages</span>
          </button>

          <button
            type="button"
            className={`preview-tab-btn ${activeTab === 'pdf' ? 'active' : ''}`}
            onClick={() => setActiveTab('pdf')}
          >
            <FileText size={17} />
            <span>See the PDF</span>
          </button>

          <button
            type="button"
            className={`preview-tab-btn ${activeTab === 'questions' ? 'active' : ''}`}
            onClick={() => setActiveTab('questions')}
          >
            <Layers size={17} />
            <span>Questions and answers</span>
          </button>
        </div>

        {/* TAB 1: Page-by-Page Interactive Book Viewer */}
        {activeTab === 'book' && (
          <div className="page-by-page-viewer">
            {/* Viewer Header with Navigation Controls */}
            <div className="viewer-controls-bar">
              <button
                type="button"
                className="viewer-nav-btn"
                onClick={handlePrevPage}
                title="Previous Page"
              >
                <ChevronLeft size={20} />
                <span>Prev</span>
              </button>

              <div className="viewer-page-indicator">
                <span className="current-page-badge">
                  {currentPage.pageLabel}
                </span>
                <span className="page-counter-text">
                  Page <strong>{currentPageIndex + 1}</strong> of <strong>{bookPages.length}</strong>
                </span>
              </div>

              <button
                type="button"
                className="viewer-nav-btn"
                onClick={handleNextPage}
                title="Next Page"
              >
                <span>Next</span>
                <ChevronRight size={20} />
              </button>
            </div>

            {/* Main Stage: Current Page Display */}
            <div className="viewer-stage">
              {currentPage.type === 'cover' && (
                <div className="book-stage-cover">
                  <div className="book-stage-title-row">
                    <span className="page-stage-tag">🌟 Front cover</span>
                    <h3 className="page-stage-title">{currentPage.title}</h3>
                  </div>
                  {currentPage.image ? (
                    <img
                      src={currentPage.image}
                      alt="Front cover"
                      className="stage-cover-img"
                    />
                  ) : (
                    <div className="stage-image-placeholder">
                      <BookOpen size={48} color="var(--theme-color)" />
                      <p>Cover picture</p>
                    </div>
                  )}
                  <p className="stage-caption">{currentPage.desc}</p>
                </div>
              )}

              {currentPage.type === 'question' && (
                <div className="book-stage-question">
                  <div className="book-stage-title-row">
                    <span className="page-stage-tag">🔢 Question Page {currentPage.pageNum - 1}</span>
                    <h3 className="page-stage-title">{currentPage.title}</h3>
                  </div>

                  <div className="question-stage-grid">
                    {/* Scene Illustration Preview */}
                    <div className="question-stage-image-col">
                      {currentPage.image ? (
                        <div className="stage-img-container">
                          <img
                            src={currentPage.image}
                            alt={`Question ${currentPage.pageNum - 1}`}
                            className="stage-question-img"
                          />
                          <span className="stage-img-overlay-badge">
                            🎨 Picture for this question
                          </span>
                        </div>
                      ) : (
                        <div className="stage-image-placeholder">
                          <Sparkles size={40} color="var(--theme-color)" />
                          <p>Picture for this question</p>
                        </div>
                      )}
                    </div>

                    {/* Story & Math Details */}
                    <div className="question-stage-info-col">
                      <div className="stage-meta-row">
                        <span className="q-badge" style={{ background: '#f1f5f9', color: '#1e293b' }}>
                          Topic: {currentPage.item?.topic_label || currentPage.item?.topic || 'Maths'}
                        </span>
                        {currentPage.item?.adult_name && (
                          <span className="q-badge" style={{ background: '#fdf2f8', color: '#db2777' }}>
                            With {currentPage.item.adult_name}
                          </span>
                        )}
                      </div>

                      <div className="stage-story-box">
                        <h4 className="stage-story-heading">The question</h4>
                        <p className="stage-story-text">{currentPage.item?.question || 'A personalised maths question'}</p>
                      </div>

                      {Array.isArray(currentPage.item?.options) && currentPage.item.options.length > 0 && (
                        <div className="stage-options-box">
                          <span className="stage-options-heading">Choices</span>
                          <div className="stage-options-grid">
                            {currentPage.item.options.map((opt, oIdx) => {
                              const isCorrect = String(opt).trim() === String(currentPage.item?.correct || '').trim();
                              return (
                                <div
                                  key={oIdx}
                                  className={`stage-opt-card ${isCorrect ? 'is-correct-opt' : ''}`}
                                >
                                  <span className="opt-letter">
                                    {String.fromCharCode(65 + oIdx)}
                                  </span>
                                  <span className="opt-value">{String(opt)}</span>
                                  {isCorrect && (
                                    <span className="opt-correct-tag">
                                      <CheckCircle2 size={13} /> Correct
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {currentPage.type === 'backcover' && (
                <div className="book-stage-cover">
                  <div className="book-stage-title-row">
                    <span className="page-stage-tag" style={{ background: '#ecfdf5', color: '#059669' }}>
                      🎓 Back cover
                    </span>
                    <h3 className="page-stage-title">{currentPage.title}</h3>
                  </div>
                  {currentPage.image ? (
                    <img
                      src={currentPage.image}
                      alt="Back Cover"
                      className="stage-cover-img"
                    />
                  ) : (
                    <div className="stage-image-placeholder">
                      <BookOpen size={48} color="#10b981" />
                      <p>Workbook Back Cover</p>
                    </div>
                  )}
                  <p className="stage-caption">{currentPage.desc}</p>
                </div>
              )}
            </div>

            {/* Bottom Thumbnail Strip */}
            <div className="viewer-thumbnail-strip">
              {bookPages.map((page, idx) => (
                <button
                  key={idx}
                  type="button"
                  className={`thumbnail-card ${currentPageIndex === idx ? 'active-thumb' : ''}`}
                  onClick={() => setCurrentPageIndex(idx)}
                  title={page.title}
                >
                  {page.image ? (
                    <img src={page.image} alt={page.pageLabel} className="thumbnail-img" />
                  ) : (
                    <div className="thumbnail-fallback">{idx + 1}</div>
                  )}
                  <span className="thumbnail-label">{page.pageLabel}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* TAB 2: Live Embedded PDF Previewer */}
        {activeTab === 'pdf' && (
          <div className="pdf-viewer-tab">
            <div className="pdf-viewer-toolbar">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', color: '#475569' }}>
                <Eye size={17} color="var(--theme-color)" />
                <span>
                  Printable book: <strong>{filename}</strong>
                </span>
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  className="btn-download-pdf"
                  style={{ padding: '8px 16px', fontSize: '0.85rem' }}
                  onClick={requestPdf}
                >
                  <Download size={15} />
                  <span>Download</span>
                </button>
                <button
                  type="button"
                  className="btn-view-pdf"
                  style={{ padding: '8px 14px', fontSize: '0.85rem' }}
                  onClick={requestPdf}
                >
                  <ExternalLink size={15} />
                  <span>Full Screen Tab</span>
                </button>
              </div>
            </div>

            {pdfUrl ? (
              <div className="pdf-iframe-container">
                <iframe
                  src={`${pdfUrl}#toolbar=1&navpanes=1`}
                  className="pdf-preview-iframe"
                  title="PDF Workbook Viewer"
                />
              </div>
            ) : (
              <div className="stage-image-placeholder">PDF not ready yet</div>
            )}
          </div>
        )}

        {/* TAB 3: Questions & Answer Keys */}
        {activeTab === 'questions' && (
          <div className="question-inspector" style={{ marginTop: 0, borderTop: 'none', paddingTop: 0 }}>
            <div
              className="inspector-title"
              style={{ cursor: 'pointer', marginBottom: '14px' }}
              onClick={() => setShowAllQuestions(!showAllQuestions)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <BookOpen size={20} color="var(--theme-color)" />
                <span>Questions and answers ({items.length})</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.88rem', color: 'var(--theme-color)' }}>
                <span>{showAllQuestions ? 'Collapse All' : 'Expand All'}</span>
                {showAllQuestions ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
            </div>

            {showAllQuestions && (
              <div className="questions-preview-list">
                {items.map((it, idx) => (
                  <div key={idx} className="question-preview-item">
                    {it.image_url ? (
                      <img
                        src={it.image_url}
                        alt={`Question ${idx + 1}`}
                        className="question-preview-thumb"
                      />
                    ) : (
                      <div
                        className="question-preview-thumb"
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}
                      >
                        🎨 AI Scene
                      </div>
                    )}

                    <div className="question-preview-content">
                      <div className="question-meta-row">
                        <span className="q-badge">Question {idx + 1}</span>
                        <span className="q-badge" style={{ background: '#f1f5f9', color: '#334155' }}>
                          {it.topic_label || it.topic || `Topic ${idx + 1}`}
                        </span>
                        {it.adult_name && (
                          <span className="q-badge" style={{ background: '#fdf2f8', color: '#db2777' }}>
                            With {it.adult_name}
                          </span>
                        )}
                        <span className="q-correct-badge">
                          <CheckCircle2 size={12} style={{ marginRight: '3px', verticalAlign: '-1px' }} />
                          Correct Answer: {String(it.correct || it.correct_answer || it.answer || '—')}
                        </span>
                      </div>

                      <p className="q-text">{it.question || it.question_text || 'Math practice exercise'}</p>

                      {/* Options */}
                      {Array.isArray(it.options) && it.options.length > 0 && (
                        <div className="q-options-row">
                          {it.options.map((opt, oIdx) => {
                            const optStr = String(opt).trim();
                            const isCorrect = optStr === String(it.correct || '').trim();
                            return (
                              <div
                                key={oIdx}
                                className={`q-opt-pill ${isCorrect ? 'is-correct' : ''}`}
                              >
                                <strong>{String.fromCharCode(65 + oIdx)})</strong> {optStr}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Modal Bottom Actions */}
        <div className="success-footer-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={onReset}
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <RotateCcw size={16} />
            <span>Make another book</span>
          </button>

          <div style={{ display: 'flex', gap: '10px' }}>
            {pdfUrl && (
              <button
                type="button"
                className="btn-download-pdf"
                onClick={requestPdf}
              >
                <Download size={18} />
                <span>Download the book</span>
              </button>
            )}
          </div>
        </div>
      </div>
      <EmailGateModal
        open={emailGateOpen}
        filename={filename}
        jobId={jobId}
        pdfUrl={pdfUrl}
        onClose={() => setEmailGateOpen(false)}
      />
    </div>
  );
}
