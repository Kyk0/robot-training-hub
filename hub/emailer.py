"""SMTP delivery using the standard library; credentials stay server-side."""

import json
import os
from pathlib import Path
import secrets
import smtplib
import ssl
from email.message import EmailMessage


class Mailer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.path = cfg.data / "smtp.json"

    def settings(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "host": os.getenv("HUB_SMTP_HOST", ""),
            "port": int(os.getenv("HUB_SMTP_PORT", "587")),
            "security": os.getenv("HUB_SMTP_SECURITY", "starttls"),
            "sender": os.getenv("HUB_SMTP_FROM", ""),
            "username": os.getenv("HUB_SMTP_USER", ""),
            "password": os.getenv("HUB_SMTP_PASSWORD", ""),
        }

    def status(self):
        data = self.settings()
        return {
            **{
                k: data.get(k, "")
                for k in ("host", "port", "security", "sender", "username")
            },
            "configured": bool(data.get("host") and data.get("sender")),
            "has_password": bool(data.get("password")),
            "development": self.cfg.development,
        }

    def connect(self, data):
        if not data.get("host") or not data.get("sender"):
            raise RuntimeError("Email is not configured")
        context = ssl.create_default_context()
        if data["security"] == "ssl":
            smtp = smtplib.SMTP_SSL(
                data["host"], data["port"], timeout=15, context=context
            )
        else:
            smtp = smtplib.SMTP(data["host"], data["port"], timeout=15)
        try:
            if data["security"] == "starttls":
                smtp.starttls(context=context)
            if data.get("username"):
                smtp.login(data["username"], data.get("password", ""))
            return smtp
        except Exception:
            smtp.close()
            raise

    def save(self, data):
        if data["host"].lower() == "smtp.gmail.com":
            data["username"] = data.get("username") or data["sender"]
            data["password"] = data.get("password", "").replace(" ", "")
        if not data.get("password"):
            old = self.settings()
            if (old.get("host"), old.get("username")) == (
                data["host"],
                data["username"],
            ):
                data["password"] = old.get("password", "")
        # Validate TLS/login before replacing a working configuration.
        with self.connect(data) as smtp:
            smtp.noop()
        temporary = self.path.with_name("smtp-" + secrets.token_hex(8) + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(data, file)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def send(self, email, subject, content, development_payload=None):
        data = self.settings()
        if not data.get("host") and self.cfg.development:
            folder = self.cfg.data / "mail"
            folder.mkdir(mode=0o700, exist_ok=True)
            path = folder / (secrets.token_hex(16) + ".json")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as file:
                json.dump(
                    {
                        "email": email,
                        "subject": subject,
                        "content": content,
                        **(development_payload or {}),
                    },
                    file,
                )
            return "development"
        message = EmailMessage()
        message["From"] = data["sender"]
        message["To"] = email
        message["Subject"] = subject
        message.set_content(content)
        with self.connect(data) as smtp:
            refused = smtp.send_message(message)
            if refused:
                raise RuntimeError("Recipient was refused")
        return "sent"
