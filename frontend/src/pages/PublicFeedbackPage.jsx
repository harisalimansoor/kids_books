import React, { useEffect, useState } from 'react';
import { Heart, Send, Sparkles, Star } from 'lucide-react';

export default function PublicFeedbackPage({ token }) {
  const [info, setInfo] = useState(null);
  const [rating, setRating] = useState(5);
  const [message, setMessage] = useState('');
  const [name, setName] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token || token === 'preview') {
      setInfo({
        student_name: 'Ayaan',
        grade_display: 'Grade 1',
        support_email: 'support@myintelibooks.com',
        already_replied: false,
      });
      return;
    }
    fetch(`/api/feedback/${token}`)
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Invalid link');
        setInfo(data);
        if (data.already_replied) setDone(true);
      })
      .catch((e) => setError(e.message));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const res = await fetch(`/api/feedback/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating, message, name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not send feedback');
      setDone(true);
    } catch (err) {
      setError(err.message);
    }
  };

  const child = info?.student_name || 'your child';

  return (
    <div className="fb-page">
      <div className="fb-float book">📚</div>
      <div className="fb-float spark s1">✦</div>
      <div className="fb-float spark s2">✧</div>
      <div className="fb-float spark s3">★</div>

      <div className="fb-card">
        <div className="fb-brand">MyInteliBooks</div>
        {done ? (
          <>
            <div className="fb-heart"><Heart size={36} /></div>
            <h1>Thank you</h1>
            <p>
              Your note about {child}'s workbook is with the team at{' '}
              <a href="mailto:support@myintelibooks.com">support@myintelibooks.com</a>.
              If you want to add more, just reply to that address.
            </p>
          </>
        ) : (
          <form onSubmit={submit}>
            <div className="fb-kicker">
              <Sparkles size={14} /> 30-second feedback
            </div>
            <h1>How did {child}'s workbook feel?</h1>
            <p>
              {info?.grade_display ? `${info.grade_display} · ` : ''}
              A tiny rating helps us make the next book even more personal.
            </p>
            <div className="fb-stars">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  type="button"
                  key={n}
                  className={n <= rating ? 'on' : ''}
                  onClick={() => setRating(n)}
                  aria-label={`${n} stars`}
                >
                  <Star size={28} fill={n <= rating ? '#fbbf24' : 'none'} />
                </button>
              ))}
            </div>
            <input
              className="text-input"
              placeholder="Your name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <textarea
              className="textarea-input"
              placeholder="Stories, pictures, maths level — anything you noticed."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              required
              style={{ marginTop: 12, minHeight: 140 }}
            />
            {error && <p className="form-hint" style={{ color: '#e11d48' }}>{error}</p>}
            <button type="submit" className="btn-primary" style={{ width: '100%', marginTop: 16 }}>
              <Send size={16} /> Send to support@myintelibooks.com
            </button>
            <p className="form-hint" style={{ textAlign: 'center', marginTop: 12 }}>
              Prefer email? Write us at <a href="mailto:support@myintelibooks.com">support@myintelibooks.com</a>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
