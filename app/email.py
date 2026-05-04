"""
email.py — Async email sender for Tax-Ready Invoice.
Supports SMTP (default) or SendGrid (set EMAIL_PROVIDER=sendgrid).
Fails silently with a logged warning — never crashes the app.

Required env vars (SMTP):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL

Optional:
  SENDGRID_API_KEY  (if EMAIL_PROVIDER=sendgrid)
  APP_URL           (for invoice links)
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@tax-ready-invoice.com")
APP_URL    = os.getenv("APP_URL", "https://tax-ready-invoice.onrender.com")
PROVIDER   = os.getenv("EMAIL_PROVIDER", "smtp").lower()


def _render_invoice_email(invoice, user_email: str) -> tuple[str, str]:
    """Returns (subject, html_body) for an invoice email."""
    view_url = f"{APP_URL}/invoice/{invoice.view_token}"
    subject  = f"Invoice {invoice.invoice_number} from {invoice.client.name if hasattr(invoice, 'client') else ''}"

    # Build line items table
    rows = ""
    for item in invoice.line_items:
        rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;">{item.description}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:center;">{item.quantity}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;">{item.unit_price:.2f}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;">{item.line_total:.2f}</td>
        </tr>"""

    # Totals section
    totals = f"""
        <tr><td colspan="3" style="padding:6px 12px;text-align:right;color:#64748b;">Subtotal</td>
            <td style="padding:6px 12px;text-align:right;">{invoice.subtotal:.2f}</td></tr>"""
    if invoice.discount_pct:
        totals += f"""
        <tr><td colspan="3" style="padding:6px 12px;text-align:right;color:#64748b;">Discount ({invoice.discount_pct}%)</td>
            <td style="padding:6px 12px;text-align:right;color:#e24b4a;">-{invoice.discount_amount:.2f}</td></tr>"""
    if invoice.tax_rate:
        totals += f"""
        <tr><td colspan="3" style="padding:6px 12px;text-align:right;color:#64748b;">Tax ({invoice.tax_rate}%)</td>
            <td style="padding:6px 12px;text-align:right;">{invoice.tax_amount:.2f}</td></tr>"""
    totals += f"""
        <tr style="background:#f8fafc;"><td colspan="3" style="padding:10px 12px;text-align:right;font-weight:700;">Total Due</td>
            <td style="padding:10px 12px;text-align:right;font-weight:700;font-size:18px;color:#6366f1;">{invoice.currency} {invoice.total:.2f}</td></tr>"""

    payment_section = ""
    if invoice.payment_note:
        payment_section = f"""
      <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-top:24px;">
        <p style="font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin:0 0 8px;">Payment Details</p>
        <pre style="font-family:monospace;font-size:13px;color:#1e293b;white-space:pre-wrap;margin:0;">{invoice.payment_note}</pre>
      </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',system-ui,sans-serif;">
  <div style="max-width:600px;margin:32px auto;background:#fff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
    <div style="background:#6366f1;padding:28px 32px;display:flex;justify-content:space-between;align-items:center;">
      <div>
        <p style="color:rgba(255,255,255,.7);font-size:11px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 4px;">Invoice</p>
        <p style="color:#fff;font-size:24px;font-weight:700;margin:0;">{invoice.invoice_number}</p>
      </div>
      <div style="text-align:right;">
        <p style="color:#fff;font-size:13px;margin:0;opacity:.85;">Due: {invoice.due_date.strftime('%B %d, %Y')}</p>
        <p style="color:#fff;font-size:20px;font-weight:700;margin:4px 0 0;">{invoice.currency} {invoice.total:.2f}</p>
      </div>
    </div>
    <div style="padding:28px 32px;">
      <p style="color:#1e293b;font-size:15px;margin:0 0 4px;font-weight:600;">Hi {invoice.client.name},</p>
      <p style="color:#64748b;font-size:14px;margin:0 0 24px;">Please find your invoice details below. Payment is due by {invoice.due_date.strftime('%B %d, %Y')}.</p>

      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="border-bottom:2px solid #6366f1;">
            <th style="text-align:left;padding:8px 12px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;">Description</th>
            <th style="text-align:center;padding:8px 12px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;">Qty</th>
            <th style="text-align:right;padding:8px 12px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;">Price</th>
            <th style="text-align:right;padding:8px 12px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;">Total</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
        <tfoot>{totals}</tfoot>
      </table>
      {payment_section}

      <div style="text-align:center;margin-top:32px;">
        <a href="{view_url}"
           style="display:inline-block;background:#6366f1;color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 32px;border-radius:8px;">
          View Invoice Online
        </a>
      </div>

      <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:24px;">
        Sent from <a href="{APP_URL}" style="color:#6366f1;">Tax-Ready Invoice</a>
        &nbsp;&middot;&nbsp; {user_email}
      </p>
    </div>
  </div>
</body></html>"""

    return subject, html


def _render_reminder_email(invoice, reminder_type: str) -> tuple[str, str]:
    """Payment reminder email — due_soon or overdue."""
    view_url = f"{APP_URL}/invoice/{invoice.view_token}"
    if reminder_type == "overdue":
        subject = f"Payment Overdue: Invoice {invoice.invoice_number} ({invoice.currency} {invoice.total:.2f})"
        urgency = "overdue"
        color   = "#e24b4a"
        msg     = f"Your invoice was due on <strong>{invoice.due_date.strftime('%B %d, %Y')}</strong> and is now overdue."
    else:
        subject = f"Payment Reminder: Invoice {invoice.invoice_number} due in 3 days"
        urgency = "due soon"
        color   = "#f59e0b"
        msg     = f"Your invoice is due on <strong>{invoice.due_date.strftime('%B %d, %Y')}</strong> — in 3 days."

    html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',system-ui,sans-serif;">
  <div style="max-width:560px;margin:32px auto;background:#fff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
    <div style="background:{color};padding:20px 28px;">
      <p style="color:#fff;font-weight:700;font-size:16px;margin:0;">
        Invoice {urgency}: {invoice.invoice_number}
      </p>
    </div>
    <div style="padding:24px 28px;">
      <p style="color:#1e293b;font-size:15px;margin:0 0 12px;">Hi {invoice.client.name},</p>
      <p style="color:#475569;font-size:14px;margin:0 0 20px;">{msg}</p>
      <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:24px;">
        <table style="width:100%;font-size:13px;">
          <tr><td style="color:#64748b;">Invoice #</td><td style="text-align:right;font-weight:600;">{invoice.invoice_number}</td></tr>
          <tr><td style="color:#64748b;">Amount Due</td>
              <td style="text-align:right;font-weight:700;font-size:16px;color:{color};">{invoice.currency} {invoice.total:.2f}</td></tr>
          <tr><td style="color:#64748b;">Due Date</td>
              <td style="text-align:right;color:{'#e24b4a' if reminder_type=='overdue' else '#1e293b'};">{invoice.due_date.strftime('%B %d, %Y')}</td></tr>
        </table>
      </div>
      <div style="text-align:center;">
        <a href="{view_url}"
           style="display:inline-block;background:{color};color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:11px 28px;border-radius:8px;">
          View &amp; Pay Invoice
        </a>
      </div>
    </div>
  </div>
</body></html>"""
    return subject, html


def send_email(to: str, subject: str, html: str, from_name: str = "Tax-Ready Invoice") -> bool:
    """
    Send an HTML email. Returns True on success, False on failure.
    Never raises — errors are logged as warnings.
    """
    if PROVIDER == "sendgrid":
        return _send_sendgrid(to, subject, html, from_name)
    return _send_smtp(to, subject, html, from_name)


def _send_smtp(to: str, subject: str, html: str, from_name: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    pwd  = os.getenv("SMTP_PASS", "")

    if not host or not user:
        logger.warning("Email skipped — SMTP_HOST/SMTP_USER not configured")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{FROM_EMAIL}>"
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(user, pwd)
            server.sendmail(FROM_EMAIL, [to], msg.as_string())
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.warning(f"Email failed to {to}: {e}")
        return False


def _send_sendgrid(to: str, subject: str, html: str, from_name: str) -> bool:
    import urllib.request, json as _json
    api_key = os.getenv("SENDGRID_API_KEY", "")
    if not api_key:
        logger.warning("Email skipped — SENDGRID_API_KEY not set")
        return False
    payload = _json.dumps({
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": FROM_EMAIL, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }).encode()
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 202
    except Exception as e:
        logger.warning(f"SendGrid failed: {e}")
        return False


def send_invoice_email(invoice, user_email: str) -> bool:
    """Send the invoice to the client's email address."""
    if not invoice.client.email:
        logger.warning(f"No client email for invoice {invoice.invoice_number}")
        return False
    subject, html = _render_invoice_email(invoice, user_email)
    return send_email(invoice.client.email, subject, html)


def send_reminder_email(invoice, reminder_type: str = "due_soon") -> bool:
    """Send a payment reminder to the client."""
    if not invoice.client.email:
        return False
    subject, html = _render_reminder_email(invoice, reminder_type)
    return send_email(invoice.client.email, subject, html)
