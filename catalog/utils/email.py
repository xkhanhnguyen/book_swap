"""
SendGrid email helper for BookSwap.
All emails are plain-text; real names/addresses are never included.
"""


def send_notification_email(to_email, subject, body):
    """Send a plain-text email via SendGrid. Silently skips if key not configured."""
    from django.conf import settings
    api_key = getattr(settings, 'SENDGRID_API_KEY', '')
    if not api_key:
        return
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        message = Mail(
            from_email='noreply@bookswap.app',
            to_emails=to_email,
            subject=subject,
            plain_text_content=body,
        )
        sg.send(message)
    except Exception:
        pass
