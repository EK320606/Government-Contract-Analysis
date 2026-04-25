"""Send the monthly ECF Government Contract Analysis newsletter.

Recipient list lives on Google Drive (CSV file or Google Sheet). The Drive
file is fetched at runtime, parsed, and each row receives the rendered
HTML template via SMTP.

Required environment variables:
    GDRIVE_FILE_ID            Drive file ID of the recipient list
    GOOGLE_SERVICE_ACCOUNT    Path to a service-account JSON key file
    SMTP_HOST                 e.g. smtp.gmail.com
    SMTP_PORT                 e.g. 587
    SMTP_USER                 SMTP username (also the From address)
    SMTP_PASSWORD             SMTP password / app password
    MAIL_FROM_NAME            Display name for the From header
    MAIL_SUBJECT              Optional override; defaults to a dated subject

The recipient file must contain at least an `email` column. An optional
`name` column is used to personalize the greeting.
"""

from __future__ import annotations

import csv
import io
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
TEMPLATE_PATH = Path(__file__).with_name("email_template.html")


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


def fetch_recipients(file_id: str, credentials_path: str) -> list[dict[str, str]]:
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=DRIVE_SCOPES
    )
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    metadata = drive.files().get(fileId=file_id, fields="mimeType,name").execute()
    if metadata["mimeType"] == GOOGLE_SHEET_MIME:
        request = drive.files().export_media(fileId=file_id, mimeType="text/csv")
    else:
        request = drive.files().get_media(fileId=file_id)

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    reader = csv.DictReader(io.StringIO(buffer.read().decode("utf-8-sig")))
    rows = []
    for row in reader:
        normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        email = normalized.get("email")
        if email and "@" in email:
            rows.append(normalized)
    return rows


def render(template: str, recipient: dict[str, str]) -> str:
    name = recipient.get("name") or "there"
    return (
        template
        .replace("{{name}}", name)
        .replace("{{month}}", date.today().strftime("%B %Y"))
    )


def build_message(
    template: str,
    recipient: dict[str, str],
    *,
    sender: str,
    sender_name: str,
    subject: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender))
    msg["To"] = recipient["email"]
    msg["Subject"] = subject
    msg.set_content(
        f"Hi {recipient.get('name') or 'there'},\n\n"
        f"This is the {date.today().strftime('%B %Y')} edition of the ECF "
        "Government Contract Analysis newsletter. View the HTML version in a "
        "modern email client."
    )
    msg.add_alternative(render(template, recipient), subtype="html")
    return msg


def send_all() -> None:
    file_id = required_env("GDRIVE_FILE_ID")
    creds_path = required_env("GOOGLE_SERVICE_ACCOUNT")
    smtp_host = required_env("SMTP_HOST")
    smtp_port = int(required_env("SMTP_PORT"))
    smtp_user = required_env("SMTP_USER")
    smtp_password = required_env("SMTP_PASSWORD")
    sender_name = os.environ.get("MAIL_FROM_NAME", "ECF, LLC")
    subject = os.environ.get(
        "MAIL_SUBJECT",
        f"ECF Government Contract Analysis — {date.today().strftime('%B %Y')}",
    )

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    recipients = fetch_recipients(file_id, creds_path)
    if not recipients:
        sys.exit("No valid recipients found in the Drive file.")

    sent = 0
    failed: list[tuple[str, str]] = []
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        for recipient in recipients:
            message = build_message(
                template,
                recipient,
                sender=smtp_user,
                sender_name=sender_name,
                subject=subject,
            )
            try:
                smtp.send_message(message)
                sent += 1
            except smtplib.SMTPException as exc:
                failed.append((recipient["email"], str(exc)))

    print(f"Sent {sent}/{len(recipients)} messages.")
    for address, error in failed:
        print(f"  failed: {address}: {error}")


if __name__ == "__main__":
    send_all()
