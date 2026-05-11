"""
Email sender for personalized PDF reports.
Tries Resend (modern, simple) first; falls back to SMTP if not configured.
"""

import os
import base64
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import requests

log = logging.getLogger("email")

EMAIL_FROM = os.getenv("EMAIL_FROM", "Atlas Reports <reports@example.com>")


def send_report_email(to: str, occupation_title: str, state_name: str,
                      pdf_bytes: bytes, score_pct: float):
    """Send the report PDF via Resend if configured, else SMTP."""
    subject = f"Your AI Vulnerability Report — {occupation_title}"
    html_body = _email_html(occupation_title, state_name, score_pct)
    text_body = _email_text(occupation_title, state_name, score_pct)
    pdf_name = f"AI-Vulnerability-Report-{occupation_title.replace(' ', '-')}.pdf"

    if os.getenv("RESEND_API_KEY"):
        return _send_via_resend(to, subject, html_body, text_body, pdf_bytes, pdf_name)
    elif os.getenv("SMTP_HOST"):
        return _send_via_smtp(to, subject, html_body, text_body, pdf_bytes, pdf_name)
    else:
        # Dev / no-email mode: log and save to disk so the dev can inspect
        log.warning(f"No email backend configured — saving report to disk for {to}")
        out_dir = "data/sent_reports"
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, pdf_name)
        with open(path, "wb") as f:
            f.write(pdf_bytes)
        log.info(f"Report saved to {path}")
        return {"channel": "disk", "path": path}


def _send_via_resend(to, subject, html_body, text_body, pdf_bytes, pdf_name):
    """Send via Resend API."""
    api_key = os.getenv("RESEND_API_KEY")
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "attachments": [{
                "filename": pdf_name,
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            }],
        },
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"Resend API error: {resp.status_code} {resp.text}")
    log.info(f"Sent report to {to} via Resend")
    return {"channel": "resend", "id": resp.json().get("id")}


def _send_via_smtp(to, subject, html_body, text_body, pdf_bytes, pdf_name):
    """Send via SMTP (Gmail / SES / etc.)."""
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    msg = MIMEMultipart("mixed")
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain"))
    alt.attach(MIMEText(html_body, "html"))
    msg.attach(alt)

    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_name)
    msg.attach(pdf_part)

    with smtplib.SMTP(host, port, timeout=20) as s:
        if use_tls:
            s.starttls()
        if user and password:
            s.login(user, password)
        s.sendmail(EMAIL_FROM, [to], msg.as_string())

    log.info(f"Sent report to {to} via SMTP")
    return {"channel": "smtp"}


def _email_html(occ_title, state_name, score_pct):
    return f"""\
<!DOCTYPE html>
<html><body style="font-family:Helvetica,Arial,sans-serif;background:#f4ecd8;margin:0;padding:30px;">
<table cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#0d0c0a;color:#f4ecd8;padding:32px;">
  <tr><td>
    <div style="font-family:Courier,monospace;font-size:10px;letter-spacing:3px;color:#ff4d2e;">/ THE GREAT REPLACEMENT</div>
    <h1 style="font-family:Georgia,serif;font-size:36px;font-weight:normal;letter-spacing:-1px;margin:8px 0 16px 0;">
      Your report is ready.
    </h1>
    <p style="line-height:1.6;color:#d9d1bf;font-size:15px;">
      Attached is your personalized AI Vulnerability Report for
      <strong style="color:#f4ecd8;">{occ_title}</strong> in
      <strong style="color:#f4ecd8;">{state_name}</strong>.
    </p>
    <p style="font-family:Georgia,serif;font-style:italic;font-size:42px;line-height:1;margin:24px 0;color:#ff4d2e;">
      {score_pct}%
    </p>
    <p style="font-family:Courier,monospace;font-size:10px;letter-spacing:2px;color:#8a8576;margin-top:-16px;">
      YOUR 2–5 YEAR VULNERABILITY
    </p>
    <hr style="border:none;border-top:1px solid #2a2820;margin:24px 0;">
    <p style="line-height:1.6;color:#d9d1bf;font-size:14px;">
      Inside the report you'll find a 5-year displacement trajectory, the specific tasks AI is replacing
      in your role, three adjacent safer roles, the highest-leverage skills to learn, and a 90-day pivot plan.
    </p>
    <p style="line-height:1.6;color:#d9d1bf;font-size:14px;">
      A career pivot is rarely fast and never easy &mdash; but it always starts with a clear picture of
      where you are. This report is that picture.
    </p>
    <hr style="border:none;border-top:1px solid #2a2820;margin:24px 0;">
    <p style="font-family:Courier,monospace;font-size:10px;color:#8a8576;letter-spacing:1.5px;">
      THE GREAT REPLACEMENT &middot; ATLAS REPORT v1.0<br>
      Data current as of March 2026 &middot; Tufts University Digital Planet
    </p>
  </td></tr>
</table>
</body></html>
"""


def _email_text(occ_title, state_name, score_pct):
    return f"""\
THE GREAT REPLACEMENT — Your Personalized Report

Attached is your AI Vulnerability Report for {occ_title} in {state_name}.

Your 2-5 year vulnerability score: {score_pct}%

Inside the report:
- 5-year displacement trajectory
- Specific tasks AI is replacing in your role
- Three adjacent safer roles
- The highest-leverage skills to learn
- A 90-day pivot plan

Data current as of March 2026. Sources: Tufts University Digital Planet,
Anthropic Economic Index, McKinsey, Goldman Sachs, Brookings, WEF.
"""
