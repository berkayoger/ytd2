import smtplib
from email.mime.text import MIMEText


def send_password_reset_email(to_email: str, token: str) -> None:
    """Send password reset link via email."""
    reset_url = f"https://yourdomain.com/reset-password?token={token}"
    subject = "YTD Crypto - Şifre Sıfırlama"
    body = (
        "Merhaba,\n\n"
        "Şifrenizi sıfırlamak için aşağıdaki bağlantıya tıklayın:\n"
        f"{reset_url}\n"
        "Eğer bu talebi siz yapmadıysanız, lütfen dikkate almayın.\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = "noreply@ytdcrypto.com"
    msg["To"] = to_email

    with smtplib.SMTP("smtp.yourmail.com", 587) as server:
        server.starttls()
        server.login("your@email.com", "your-password")
        server.send_message(msg)
