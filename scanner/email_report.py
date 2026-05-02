"""Build and send the daily top-3 cluster email."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Sequence

from .cluster import Cluster, score_trade


def _fmt_money(n: float) -> str:
    if n >= 1_000_000:
        return f"${n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:,.0f}"


def render_email_html(clusters: Sequence[Cluster]) -> str:
    if not clusters:
        return "<p>No qualifying insider clusters in the last scan window.</p>"

    rows = []
    for rank, c in enumerate(clusters, start=1):
        insider_lines = "".join(
            f"<li>{t.insider_name} — {t.insider_title or 'Insider'}: "
            f"{t.shares:,.0f} sh @ ${t.price:.2f} ({_fmt_money(t.dollar_value)})</li>"
            for t in c.trades
        )
        rows.append(
            f"""
            <div style="padding:16px;border:1px solid #1f2a44;border-radius:12px;
                        background:#0a0f1e;margin-bottom:12px;">
              <div style="font-size:18px;font-weight:700;color:#e2e8f0;">
                #{rank} {c.ticker} — {c.issuer_name}
              </div>
              <div style="color:#94a3b8;margin:4px 0 12px;">
                {c.insider_count} insiders · {_fmt_money(c.total_value)} total ·
                avg ${c.avg_price:.2f}
              </div>
              <ul style="margin:0;padding-left:20px;color:#cbd5e1;">{insider_lines}</ul>
            </div>
            """
        )

    return f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;
                       background:#050816;padding:24px;color:#e2e8f0;">
      <h2 style="color:#818cf8;margin:0 0 16px;">Insider Cluster Buy Scanner</h2>
      <p style="color:#94a3b8;margin:0 0 20px;">
        Top {len(clusters)} cluster buys from the latest SEC Form 4 sweep.
      </p>
      {''.join(rows)}
      <p style="color:#64748b;font-size:12px;margin-top:24px;">
        Source: SEC EDGAR · Not investment advice.
      </p>
    </body></html>
    """


def render_email_text(clusters: Sequence[Cluster]) -> str:
    if not clusters:
        return "No qualifying insider clusters in the last scan window."
    lines = ["Insider Cluster Buy Scanner", "=" * 40, ""]
    for rank, c in enumerate(clusters, start=1):
        lines.append(f"#{rank} {c.ticker} — {c.issuer_name}")
        lines.append(
            f"   {c.insider_count} insiders · {_fmt_money(c.total_value)} · "
            f"avg ${c.avg_price:.2f}"
        )
        for t in c.trades:
            lines.append(
                f"     - {t.insider_name} ({t.insider_title or 'Insider'}): "
                f"{t.shares:,.0f} sh @ ${t.price:.2f}"
            )
        lines.append("")
    return "\n".join(lines)


def send_email(clusters: Sequence[Cluster], *, to: str, subject: str | None = None) -> None:
    """Send via SMTP. Reads creds from env: SMTP_HOST/PORT/USER/PASS/FROM."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    sender = os.environ.get("SMTP_FROM", user)

    ranked = sorted(clusters, key=score_trade, reverse=True)[:3]

    msg = EmailMessage()
    msg["Subject"] = subject or "Insider Cluster Buy Scanner — Top 3"
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(render_email_text(ranked))
    msg.add_alternative(render_email_html(ranked), subtype="html")

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
