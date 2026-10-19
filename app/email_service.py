"""
Feedback email templates, SMTP delivery, IMAP ingest, and due-job processing.
"""

from __future__ import annotations

import email
import imaplib
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Optional

from app.admin_store import (
    get_active_image_runtime,
    iter_job_metadata,
    load_settings,
    upsert_feedback,
)
from app.grade_config import write_job_metadata, read_job_metadata

SUPPORT_EMAIL = "support@myintelibooks.com"


def _now() -> datetime:
    return datetime.now()


def build_feedback_email_html(
    *,
    student_name: str,
    grade_label: str,
    question_count: int,
    topics: list[str],
    feedback_url: str,
    delay_days: int = 2,
) -> str:
    name = (student_name or "your child").strip() or "your child"
    topic_pills = "".join(
        f'<span style="display:inline-block;margin:4px 6px 4px 0;padding:6px 12px;'
        f'border-radius:999px;background:rgba(255,255,255,0.18);color:#fff;'
        f'font-size:12px;font-weight:600;letter-spacing:0.02em;">{_esc(t)}</span>'
        for t in (topics or ["Maths"])
    ) or '<span style="color:#fff;">Maths</span>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>How did { _esc(name) }'s workbook feel?</title>
  <style>
    @keyframes floatBook {{
      0% {{ transform: translateY(0) rotate(-4deg); }}
      50% {{ transform: translateY(-10px) rotate(3deg); }}
      100% {{ transform: translateY(0) rotate(-4deg); }}
    }}
    @keyframes sparkle {{
      0%, 100% {{ opacity: 0.35; transform: scale(0.8); }}
      50% {{ opacity: 1; transform: scale(1.15); }}
    }}
    @keyframes shine {{
      0% {{ background-position: 0% 50%; }}
      100% {{ background-position: 100% 50%; }}
    }}
    @keyframes pulseBtn {{
      0%, 100% {{ box-shadow: 0 12px 30px rgba(99,102,241,0.35); }}
      50% {{ box-shadow: 0 16px 40px rgba(244,63,94,0.4); }}
    }}
    .book {{
      animation: floatBook 4.5s ease-in-out infinite;
      display: inline-block;
      font-size: 56px;
      filter: drop-shadow(0 12px 18px rgba(15,23,42,0.25));
    }}
    .spark {{
      display: inline-block;
      animation: sparkle 1.8s ease-in-out infinite;
    }}
    .cta {{
      animation: pulseBtn 2.4s ease-in-out infinite;
    }}
    @media (prefers-reduced-motion: reduce) {{
      .book, .spark, .cta {{ animation: none !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(180deg,#0f172a 0%,#1e1b4b 55%,#0f172a 100%);padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;">
          <tr>
            <td style="padding:12px 8px 22px 8px;text-align:center;">
              <div class="spark" style="font-size:18px;color:#fbbf24;">✦</div>
              <div style="font-size:13px;letter-spacing:0.28em;text-transform:uppercase;color:#c4b5fd;font-weight:700;">MyInteliBooks</div>
              <div style="font-size:12px;color:#94a3b8;margin-top:4px;">Personalised Learning · Brighter Tomorrows</div>
            </td>
          </tr>
          <tr>
            <td style="background:linear-gradient(135deg,#6366f1 0%,#8b5cf6 45%,#ec4899 100%);border-radius:28px 28px 0 0;padding:36px 32px 28px 32px;text-align:center;">
              <div class="book">📚</div>
              <h1 style="margin:16px 0 8px 0;color:#fff;font-size:30px;line-height:1.25;">
                How did {_esc(name)}'s workbook feel?
              </h1>
              <p style="margin:0;color:rgba(255,255,255,0.9);font-size:16px;line-height:1.55;">
                About {delay_days} days ago we created a personalised {_esc(grade_label)} practice book.
                A 30-second note from you helps us make the next one even better.
              </p>
              <div style="margin-top:18px;">{topic_pills}</div>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff;padding:32px 32px 12px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="33%" style="padding:10px;text-align:center;">
                    <div style="background:#eef2ff;border-radius:18px;padding:16px;">
                      <div style="font-size:22px;font-weight:800;color:#4f46e5;">{int(question_count or 0)}</div>
                      <div style="font-size:12px;color:#64748b;font-weight:600;">Questions</div>
                    </div>
                  </td>
                  <td width="33%" style="padding:10px;text-align:center;">
                    <div style="background:#fdf2f8;border-radius:18px;padding:16px;">
                      <div style="font-size:18px;font-weight:800;color:#db2777;">{_esc(grade_label or "Grade")}</div>
                      <div style="font-size:12px;color:#64748b;font-weight:600;">Year group</div>
                    </div>
                  </td>
                  <td width="33%" style="padding:10px;text-align:center;">
                    <div style="background:#ecfdf5;border-radius:18px;padding:16px;">
                      <div style="font-size:22px;">⭐</div>
                      <div style="font-size:12px;color:#64748b;font-weight:600;">Your voice</div>
                    </div>
                  </td>
                </tr>
              </table>
              <p style="color:#334155;font-size:15px;line-height:1.7;margin:18px 0 8px 0;">
                Did the stories feel like {_esc(name)}? Were the pictures a true likeness?
                Was the maths just-right — or a little too easy / too hard?
              </p>
              <p style="text-align:center;margin:28px 0 8px 0;">
                <a class="cta" href="{_esc(feedback_url)}"
                   style="display:inline-block;background:linear-gradient(90deg,#6366f1,#ec4899);
                   color:#ffffff;text-decoration:none;font-weight:800;font-size:16px;
                   padding:16px 28px;border-radius:999px;letter-spacing:0.02em;">
                  Share feedback in 30 seconds &rarr;
                </a>
              </p>
              <p style="text-align:center;color:#94a3b8;font-size:12px;margin:0 0 18px 0;">
                Opens a beautiful private form. No login needed.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background:#f8fafc;padding:22px 32px 28px 32px;border-radius:0 0 28px 28px;border-top:1px solid #e2e8f0;">
              <p style="margin:0 0 8px 0;color:#0f172a;font-weight:700;font-size:14px;">Prefer to reply by email?</p>
              <p style="margin:0;color:#475569;font-size:13px;line-height:1.6;">
                Just hit reply. This message was sent from
                <a href="mailto:{SUPPORT_EMAIL}" style="color:#6366f1;font-weight:700;">{SUPPORT_EMAIL}</a>
                and your reply comes straight back to the same inbox.
              </p>
              <p style="margin:16px 0 0 0;color:#94a3b8;font-size:11px;">
                You received this because a workbook PDF was downloaded with this email address.
                We only ask once, and we never share your details.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 8px;text-align:center;color:#64748b;font-size:11px;">
              © {datetime.now().year} MyInteliBooks · {SUPPORT_EMAIL}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _esc(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def schedule_feedback_for_job(job_id: str, email_addr: str) -> dict[str, Any]:
    settings = load_settings()
    delay_hours = int(settings.get("feedback_delay_hours") or 48)
    now = _now()
    try:
        meta = read_job_metadata(job_id)
    except FileNotFoundError:
        meta = {"job_id": job_id}
    token = meta.get("feedback_token") or secrets.token_urlsafe(18)
    scheduled = now + timedelta(hours=delay_hours)
    record = {
        "id": token,
        "token": token,
        "job_id": job_id,
        "email": email_addr.strip().lower(),
        "student_name": meta.get("student_name") or "",
        "grade_id": meta.get("grade_id") or "",
        "grade_display": meta.get("grade_display") or meta.get("grade_id") or "",
        "topics": meta.get("selected_topics") or [],
        "question_count": meta.get("total_questions") or meta.get("num_questions") or 0,
        "location": meta.get("location") or "",
        "gender": meta.get("gender") or "",
        "status": "scheduled",
        "created_at": now.isoformat(),
        "scheduled_at": scheduled.isoformat(),
        "sent_at": None,
        "replied_at": None,
        "rating": None,
        "message": "",
        "source": "web_pending",
    }
    write_job_metadata(job_id, {
        "download_email": email_addr.strip().lower(),
        "feedback_token": token,
        "feedback_status": "scheduled",
        "feedback_scheduled_at": scheduled.isoformat(),
        "email_captured_at": now.isoformat(),
    })
    upsert_feedback(record)
    return record


def send_feedback_email(record: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    smtp = settings.get("smtp") or {}
    host = (smtp.get("host") or "").strip()
    if not host:
        raise RuntimeError(
            "SMTP is not configured. Add host/user/password in Admin -> Feedback, "
            "or set SMTP_HOST / SMTP_USER / SMTP_PASSWORD in .env."
        )
    delay_hours = int(settings.get("feedback_delay_hours") or 48)
    delay_days = max(1, round(delay_hours / 24))
    base = (settings.get("public_base_url") or "http://localhost:5173").rstrip("/")
    token = record["token"]
    feedback_url = f"{base}/feedback/{token}"
    html = build_feedback_email_html(
        student_name=record.get("student_name") or "",
        grade_label=record.get("grade_display") or record.get("grade_id") or "your year group",
        question_count=int(record.get("question_count") or 0),
        topics=list(record.get("topics") or []),
        feedback_url=feedback_url,
        delay_days=delay_days,
    )
    name = (record.get("student_name") or "your child").strip()
    text = (
        f"Hi,\n\nHow did {name}'s MyInteliBooks workbook feel?\n\n"
        f"Share a quick note here: {feedback_url}\n\n"
        f"Or just reply to this email — it comes to {SUPPORT_EMAIL}.\n\n"
        "Thank you,\nMyInteliBooks"
    )
    msg = EmailMessage()
    from_email = smtp.get("from_email") or SUPPORT_EMAIL
    from_name = smtp.get("from_name") or "MyInteliBooks"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = record["email"]
    msg["Reply-To"] = settings.get("support_email") or SUPPORT_EMAIL
    msg["Subject"] = f"How did {name}'s workbook feel? 📚"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    port = int(smtp.get("port") or 587)
    user = smtp.get("user") or from_email
    password = smtp.get("password") or ""
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if smtp.get("use_tls", True):
                server.starttls(context=context)
            if user and password:
                server.login(user, password)
            server.send_message(msg)

    now = _now().isoformat()
    updated = {
        **record,
        "status": "sent",
        "sent_at": now,
        "feedback_url": feedback_url,
    }
    upsert_feedback(updated)
    try:
        write_job_metadata(record["job_id"], {
            "feedback_status": "sent",
            "feedback_sent_at": now,
        })
    except Exception:
        pass
    return updated


def process_due_feedback_emails() -> int:
    from app.admin_store import load_feedback

    settings = load_settings()
    smtp = settings.get("smtp") or {}
    # If SMTP is not yet configured, don't spam attempts on scheduled emails
    if not (smtp.get("host") or "").strip():
        try:
            ingest_support_replies()
        except Exception as exc:
            print(f"[FEEDBACK IMAP] {exc}")
        return 0

    sent = 0
    now = _now()
    for record in load_feedback():
        if record.get("status") != "scheduled":
            continue
        scheduled_raw = record.get("scheduled_at") or ""
        try:
            due = datetime.fromisoformat(scheduled_raw)
        except Exception:
            continue
        if due > now:
            continue
        try:
            send_feedback_email(record)
            sent += 1
        except Exception as exc:
            err_msg = str(exc)
            print(f"[FEEDBACK] Failed to send {record.get('token')}: {err_msg}")
            attempts = int(record.get("send_attempts") or 0) + 1
            update_data = {
                **record,
                "last_error": err_msg,
                "send_attempts": attempts,
            }
            if attempts >= 3:
                update_data["status"] = "failed"
            upsert_feedback(update_data)
    try:
        ingest_support_replies()
    except Exception as exc:
        print(f"[FEEDBACK IMAP] {exc}")
    return sent


def _decode_mime_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(chunk))
    return " ".join(out)


def ingest_support_replies() -> int:
    settings = load_settings()
    imap_cfg = settings.get("imap") or {}
    if not imap_cfg.get("enabled"):
        return 0
    host = (imap_cfg.get("host") or "").strip()
    user = (imap_cfg.get("user") or "").strip()
    password = (imap_cfg.get("password") or "").strip()
    if not (host and user and password):
        return 0

    from app.admin_store import load_feedback

    mail = imaplib.IMAP4_SSL(host, int(imap_cfg.get("port") or 993))
    mail.login(user, password)
    mail.select("INBOX")
    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        mail.logout()
        return 0
    ingested = 0
    records = load_feedback()
    by_email = {}
    for rec in records:
        by_email.setdefault((rec.get("email") or "").lower(), []).append(rec)

    for num in (data[0] or b"").split():
        status, msg_data = mail.fetch(num, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        parsed = email.message_from_bytes(raw)
        sender = parseaddr(parsed.get("From", ""))[1].lower()
        subject = _decode_mime_header(parsed.get("Subject", ""))
        body = _extract_text_body(parsed)
        matches = by_email.get(sender) or []
        if not matches:
            upsert_feedback({
                "id": f"imap-{secrets.token_hex(8)}",
                "token": "",
                "job_id": "",
                "email": sender,
                "student_name": "",
                "status": "replied",
                "source": "imap",
                "subject": subject,
                "message": body[:4000],
                "replied_at": _now().isoformat(),
                "created_at": _now().isoformat(),
            })
            ingested += 1
            continue
        target = sorted(matches, key=lambda r: r.get("sent_at") or r.get("created_at") or "", reverse=True)[0]
        upsert_feedback({
            **target,
            "status": "replied",
            "source": "imap",
            "subject": subject,
            "message": (target.get("message") or "") or body[:4000],
            "reply_body": body[:4000],
            "replied_at": _now().isoformat(),
        })
        ingested += 1
    mail.logout()
    return ingested


def _extract_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def get_feedback_by_token(token: str) -> Optional[dict[str, Any]]:
    from app.admin_store import load_feedback

    for rec in load_feedback():
        if rec.get("token") == token:
            return rec
    for meta in iter_job_metadata():
        if meta.get("feedback_token") == token:
            return {
                "token": token,
                "job_id": meta.get("job_id"),
                "email": meta.get("download_email"),
                "student_name": meta.get("student_name"),
                "grade_display": meta.get("grade_display"),
                "status": meta.get("feedback_status") or "scheduled",
            }
    return None
