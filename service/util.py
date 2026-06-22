import re
from html import escape
from typing import Optional
from zoneinfo import ZoneInfo
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from datetime import timedelta
from model.unifiedMessage import UnifiedMessage

# Telegram hard limit on a single message body.
MAX_MESSAGE_LEN = 4096

# Human labels for media-only / media+caption messages.
MEDIA_LABEL = {
    "photo": "\U0001f5bc Photo",
    "video": "\U0001f3ac Video",
    "audio": "\U0001f3a7 Audio",
    "document": "\U0001f4ce Document",
    "sticker": "\U0001f600 Sticker",
    "location": "\U0001f4cd Location",
    "contact": "\U0001f464 Contact",
}

_TAG_RE = re.compile(r'<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9-]*)[^>]*?(/?)\s*>')


class Util:

    _offset = 0

    @staticmethod
    def render_body(text: str, media_type: Optional[str]) -> str:
        """Compose the 💬 body, prefixing a media label when the message carries media.

        Keeps a placeholder visible when a media message has no caption, so the
        report never shows an empty body.
        """
        text = text or ""
        if not media_type:
            return text
        label = MEDIA_LABEL.get(media_type, f"[{media_type}]")
        return f"{label}\n{text}".rstrip() if text.strip() else label

    @staticmethod
    def truncate_html(html: str, max_len: int = MAX_MESSAGE_LEN) -> str:
        """Truncate an HTML string to max_len without leaving broken/unbalanced tags.

        Telegram rejects messages with dangling or unclosed entities, so we drop a
        trailing partial tag and append closing tags for anything left open.
        """
        if html is None or len(html) <= max_len:
            return html or ""

        marker = "\n… [truncated]"
        # Closing tags and the marker count toward the limit, so shrink the slice
        # until body + marker + closing tags all fit. A few passes converge.
        budget = max_len - len(marker)
        for _ in range(5):
            cut = html[:budget]

            # Drop a dangling partial tag ('<' opened but not yet closed).
            last_lt = cut.rfind('<')
            last_gt = cut.rfind('>')
            if last_lt > last_gt:
                cut = cut[:last_lt]

            # Walk tags to find which remain open.
            stack: list = []
            for m in _TAG_RE.finditer(cut):
                closing, name, selfclose = m.group(1), m.group(2).lower(), m.group(3)
                if selfclose:
                    continue
                if closing:
                    if name in stack:
                        while stack and stack.pop() != name:
                            pass
                else:
                    stack.append(name)

            suffix = marker + ''.join(f'</{name}>' for name in reversed(stack))
            result = cut.rstrip() + suffix
            if len(result) <= max_len:
                return result
            budget -= len(result) - max_len

        return result[:max_len]

    @staticmethod
    def reset_offset():
        Util._offset = 0

    @staticmethod
    async def send_message_report(client: TelegramClient, message: UnifiedMessage, output_dialog_id: int, source):
        if message is None:
            return None

        report_text = source.get_message_reference(message)
        report_text = Util.truncate_html(report_text, MAX_MESSAGE_LEN)

        await client.send_message(
            PeerChannel(output_dialog_id),
            report_text,
            parse_mode='html',
            link_preview=False,
            schedule=timedelta(seconds=60 + Util._offset * 60),
        )

        Util._offset += 1

    @staticmethod
    def construct_message_object(message: UnifiedMessage, timezone_name: str = "Europe/Madrid"):
        return {
            'source': message.source,
            'chat_title': message.chat_title,
            'chat_id': message.chat_id,
            'text': message.text,
            'sender_name': message.sender_name,
            'message_id': message.message_id,
            'datetime': message.timestamp.astimezone(ZoneInfo(timezone_name)).isoformat(),
        }

    @staticmethod
    def is_message_in_list(str1: str, str_list: list) -> bool:
        """
        Returns True if str1 matches any string in str_list,
        comparing only letters and ignoring newlines and case.
        Strips HTML tags first.
        """
        if not str1:
            return False

        def clean(s):
            # Strip HTML tags
            s = re.sub(r'<[^>]+>', '', s)
            # Filter only alpha
            return ''.join(filter(str.isalpha, s.replace('\n', ''))).lower()

        str1_clean = clean(str1)
        for s in str_list:
            if clean(s) == str1_clean:
                return True
        return False



