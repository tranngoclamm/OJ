import logging
import requests
import traceback
from django.conf import settings

TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = settings.TELEGRAM_CHAT_ID

class TelegramLogHandler(logging.Handler):
    def emit(self, record):
        try:
            message = self.format(record)

            text = (
                "🚨 <b>Django ERROR</b>\n"
                f"<b>Level:</b> {record.levelname}\n"
                f"<b>Message:</b> {record.getMessage()}\n"
                f"<b>File:</b> {record.pathname}:{record.lineno}\n"
            )

            if record.exc_info:
                text += "\n<pre>" + "".join(
                    traceback.format_exception(*record.exc_info)
                )[-3500:] + "</pre>"

            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                },
                timeout=5,
            )
        except Exception:
            pass 
