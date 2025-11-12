"""Email service for sending confirmation emails via AWS SES."""

import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via AWS SES."""

    def __init__(self):
        """Initialize email service."""
        settings = get_settings()
        self.sender_email = settings.sender_email
        self.base_url = settings.base_url
        self.aws_region = settings.email_aws_region

        # Initialize SES client
        self.ses_client = boto3.client('ses', region_name=self.aws_region)

    def send_confirmation_email(
        self,
        recipient_email: str,
        username: str,
        confirmation_token: str
    ) -> bool:
        """
        Send email confirmation link to user.

        Args:
            recipient_email: Email address to send to
            username: Username for personalization
            confirmation_token: Confirmation token for the link

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        confirmation_url = f"{self.base_url}/api/confirm-email?token={confirmation_token}"

        # Email subject
        subject = "Confirm your PutPlace registration"

        # Email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .button:hover {{
                    opacity: 0.9;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #ddd;
                    font-size: 0.9em;
                    color: #666;
                }}
                .warning {{
                    background: #fff3cd;
                    border: 1px solid #ffc107;
                    border-radius: 5px;
                    padding: 15px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to PutPlace!</h1>
                </div>
                <div class="content">
                    <p>Hi {username},</p>

                    <p>Thank you for registering with PutPlace! To complete your registration and activate your account, please confirm your email address by clicking the button below:</p>

                    <div style="text-align: center;">
                        <a href="{confirmation_url}" class="button">Confirm Email Address</a>
                    </div>

                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; background: #fff; padding: 10px; border-radius: 5px;">
                        {confirmation_url}
                    </p>

                    <div class="warning">
                        <strong>⚠️ Important:</strong> This confirmation link will expire in 24 hours. If you don't confirm your email within this time, your registration will be automatically deleted and you'll need to register again.
                    </div>

                    <div class="footer">
                        <p>If you didn't create an account with PutPlace, you can safely ignore this email.</p>
                        <p>This is an automated message, please do not reply to this email.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        # Email body (plain text fallback)
        text_body = f"""
        Welcome to PutPlace!

        Hi {username},

        Thank you for registering with PutPlace! To complete your registration and activate your account, please confirm your email address by clicking the link below:

        {confirmation_url}

        IMPORTANT: This confirmation link will expire in 24 hours. If you don't confirm your email within this time, your registration will be automatically deleted and you'll need to register again.

        If you didn't create an account with PutPlace, you can safely ignore this email.

        This is an automated message, please do not reply to this email.
        """

        try:
            response = self.ses_client.send_email(
                Source=self.sender_email,
                Destination={
                    'ToAddresses': [recipient_email]
                },
                Message={
                    'Subject': {
                        'Data': subject,
                        'Charset': 'UTF-8'
                    },
                    'Body': {
                        'Text': {
                            'Data': text_body,
                            'Charset': 'UTF-8'
                        },
                        'Html': {
                            'Data': html_body,
                            'Charset': 'UTF-8'
                        }
                    }
                }
            )

            logger.info(f"Confirmation email sent to {recipient_email}. Message ID: {response['MessageId']}")
            return True

        except ClientError as e:
            logger.error(f"Failed to send confirmation email to {recipient_email}: {e.response['Error']['Message']}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending confirmation email to {recipient_email}: {str(e)}")
            return False


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
