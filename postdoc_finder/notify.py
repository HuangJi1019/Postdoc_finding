"""Email digest delivery via Gmail SMTP.

Credentials are read only from the environment (GMAIL_ADDRESS,
GMAIL_APP_PASSWORD). Nothing is hardcoded and nothing is logged. Use an app
password generated at https://myaccount.google.com/apppasswords, never the
account password.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from html import escape

from .models import Job

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _row(job: Job) -> str:
    meta_bits = [b for b in (escape(job.institution), escape(job.location)) if b]
    meta = " · ".join(meta_bits)
    deadline = f"<span style='color:#b00'>Deadline: {escape(job.deadline)}</span>" if job.deadline else ""
    matched = ", ".join(escape(m) for m in job.matched[:6])
    snippet = escape(job.summary[:240] + ("…" if len(job.summary) > 240 else ""))
    return f"""
    <div style="margin:0 0 18px;padding:14px 16px;border:1px solid #e3e3e3;border-radius:8px;">
      <div style="font-size:12px;color:#777;margin-bottom:4px;">
        {escape(job.source)} · relevance {job.score:g}
      </div>
      <a href="{escape(job.url)}" style="font-size:16px;font-weight:600;color:#1a4b8c;text-decoration:none;">
        {escape(job.title)}
      </a>
      <div style="font-size:13px;color:#444;margin:4px 0;">{meta}</div>
      {f'<div style="font-size:12px;color:#b00;margin:2px 0;">{deadline}</div>' if deadline else ''}
      <div style="font-size:13px;color:#333;margin:6px 0;">{snippet}</div>
      <div style="font-size:11px;color:#999;">matched: {matched}</div>
    </div>"""


def render_html(jobs: list[Job], max_items: int) -> str:
    shown = jobs[:max_items]
    more = len(jobs) - len(shown)
    rows = "".join(_row(j) for j in shown)
    footer = (
        f"<p style='font-size:12px;color:#999;'>{more} more match(es) not shown.</p>"
        if more > 0
        else ""
    )
    return f"""<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:680px;margin:auto;">
      <h2 style="font-size:18px;">{len(jobs)} new postdoc position(s) — {date.today():%Y-%m-%d}</h2>
      {rows}
      {footer}
      <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
      <p style="font-size:11px;color:#aaa;">Sent by Postdoc Finder. Edit keywords and sources in config.yaml.</p>
    </body></html>"""


def render_text(jobs: list[Job], max_items: int) -> str:
    lines = [f"{len(jobs)} new postdoc position(s) — {date.today():%Y-%m-%d}", ""]
    for j in jobs[:max_items]:
        lines.append(f"[{j.score:g}] {j.title}")
        if j.institution or j.location:
            lines.append(f"    {j.institution} {j.location}".rstrip())
        if j.deadline:
            lines.append(f"    Deadline: {j.deadline}")
        lines.append(f"    {j.url}")
        lines.append("")
    return "\n".join(lines)


def send_digest(jobs: list[Job], max_items: int, recipient: str | None = None) -> None:
    """Send the digest. Raises if credentials are missing or SMTP fails."""
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in the environment")
    to_addr = recipient or os.environ.get("RECIPIENT") or sender

    msg = EmailMessage()
    msg["Subject"] = f"[Postdoc Finder] {len(jobs)} new position(s) — {date.today():%Y-%m-%d}"
    msg["From"] = sender
    msg["To"] = to_addr
    msg.set_content(render_text(jobs, max_items))
    msg.add_alternative(render_html(jobs, max_items), subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(sender, password)
        server.send_message(msg)
