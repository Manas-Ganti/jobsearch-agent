"""Email channel — plain SMTP. Credentials come from the env via config.yaml."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..models import JobPosting
from . import BaseChannel, register_channel
from .render import as_html, as_text, subject

log = logging.getLogger(__name__)


@register_channel("email")
class EmailChannel(BaseChannel):
    def configure(
        self,
        to: str | list[str] = "",
        sender: str = "",
        host: str = "smtp.gmail.com",
        port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
    ) -> None:
        self.to = [to] if isinstance(to, str) else list(to)
        self.to = [addr for addr in self.to if addr]
        self.sender = sender or username
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        if not self.to or not self.password:
            raise ValueError(
                "email channel needs `to` and `password` — set SMTP_PASSWORD in .env"
            )

    def deliver(self, jobs: list[JobPosting]) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject(jobs)
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        msg.set_content(as_text(jobs))
        msg.add_alternative(as_html(jobs), subtype="html")

        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
        log.info("emailed %d jobs to %s", len(jobs), ", ".join(self.to))
