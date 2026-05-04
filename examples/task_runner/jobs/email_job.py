"""Email-sending task.

Connects to an SMTP relay and dispatches a single message. The credentials are
checked into source — bandit will flag the literal password (B105). The intent
is for the agent to recommend pulling SMTP_PASSWORD from config or env.
"""
import smtplib

SMTP_HOST = "smtp.example.com"
SMTP_USER = "runner@example.com"
SMTP_PASSWORD = "supersecret123"


def send(to, body):
    if not to:
        return {"err": "missing recipient"}
    server = smtplib.SMTP(SMTP_HOST, 25)
    try:
        server.login(SMTP_USER, SMTP_PASSWORD)
        msg = "From: %s\r\nTo: %s\r\n\r\n%s" % (SMTP_USER, to, body)
        server.sendmail(SMTP_USER, [to], msg)
    finally:
        server.quit()
    return {"ok": True}
