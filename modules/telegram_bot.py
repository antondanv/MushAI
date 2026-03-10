import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv


class TelegramBot:
    def __init__(self):
        load_dotenv()
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.target_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def _send_request(self, request) -> str:
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            if parsed.get("ok"):
                message_id = parsed.get("result", {}).get("message_id")
                return f"Message sent. message_id={message_id}"
            return f"Telegram API error: {parsed}"
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            return f"Telegram API HTTP error: {exc.code}. {details}"
        except Exception as exc:
            return f"Telegram send error: {exc}"

    async def send_telegram_message(self, text: str) -> str:
        if not self.bot_token:
            return "Error: TELEGRAM_BOT_TOKEN is not set."
        if not self.target_chat_id:
            return "Error: TELEGRAM_CHAT_ID is not set and chat_id was not provided."
        if not text or not text.strip():
            return "Error: message text is empty."

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": self.target_chat_id, "text": text}
        ).encode("utf-8")
        request = urllib.request.Request(url=url, data=payload, method="POST")
        return await asyncio.to_thread(self._send_request, request)
