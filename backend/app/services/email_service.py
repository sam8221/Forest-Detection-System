"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Email Service

Purpose:
    Sends email notifications to Forestry Officers.

Responsibilities:
    - Send alert emails.
    - Send HTML emails.
    - Connect to SMTP server.
    - Raise exceptions when sending fails.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

from app.core.config import get_settings

settings = get_settings()


class EmailService:
    """
    Handles sending emails through SMTP.
    """

    def __init__(self) -> None:
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password
        self.from_email = settings.smtp_from_email

    def send_email(
        self,
        recipient_email: str,
        subject: str,
        html_body: str,
    ) -> None:
        """
        Send one HTML email.
        """

        message = MIMEMultipart("alternative")

        message["Subject"] = subject
        message["From"] = self.from_email
        message["To"] = recipient_email

        message.attach(
            MIMEText(
                html_body,
                "html",
            )
        )

        with smtplib.SMTP(
            self.host,
            self.port,
        ) as smtp:

            smtp.starttls()

            smtp.login(
                self.username,
                self.password,
            )

            smtp.sendmail(
                self.from_email,
                recipient_email,
                message.as_string(),
            )

    def send_alert_email(
        self,
        recipient_name: str,
        recipient_email: str,
        forest_name: str,
        district: str,
        detected_area: float,
        confidence: float,
        priority: str,
    ) -> None:
        """
        Send a professionally formatted deforestation alert email.
        """

        subject = f"🚨 ForestWatch Zambia Alert - {forest_name}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>ForestWatch Zambia Alert</title>
        </head>

        <body style="font-family: Arial, Helvetica, sans-serif;
                     background-color:#f4f4f4;
                     padding:30px;">

            <div style="
                max-width:700px;
                margin:auto;
                background:#ffffff;
                border-radius:8px;
                padding:30px;
                border:1px solid #dddddd;
            ">

                <h2 style="color:#2E7D32;">
                    🌳 ForestWatch Zambia
                </h2>

                <p>
                    Dear <strong>{recipient_name}</strong>,
                </p>

                <p>
                    A potential deforestation event has been detected and
                    requires your attention.
                </p>

                <table style="
                    width:100%;
                    border-collapse:collapse;
                    margin-top:20px;
                    margin-bottom:20px;
                ">

                    <tr>
                        <td><strong>Forest Area</strong></td>
                        <td>{forest_name}</td>
                    </tr>

                    <tr>
                        <td><strong>District</strong></td>
                        <td>{district}</td>
                    </tr>

                    <tr>
                        <td><strong>Estimated Area Lost</strong></td>
                        <td>{detected_area:.2f} hectares</td>
                    </tr>

                    <tr>
                        <td><strong>Confidence Level</strong></td>
                        <td>{confidence:.2f}%</td>
                    </tr>

                    <tr>
                        <td><strong>Priority</strong></td>
                        <td>{priority}</td>
                    </tr>

                </table>

                <p>
                    Please log in to the
                    <strong>ForestWatch Zambia Dashboard</strong>
                    to review this detection and take appropriate action.
                </p>

                <hr>

                <p style="font-size:12px;color:#666666;">
                    This is an automatically generated email from the
                    ForestWatch Zambia System.
                    Please do not reply to this message.
                </p>

            </div>

        </body>
        </html>
        """

        self.send_email(
            recipient_email=recipient_email,
            subject=subject,
            html_body=html_body,
        )