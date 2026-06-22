from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class UnifiedMessage:
    source: str           # "telegram" or "whatsapp"
    chat_id: str          # Unique chat identifier (string)
    chat_title: str       # Human-readable chat/group name
    message_id: str       # Unique message identifier (string)
    text: str             # Message body text
    timestamp: datetime   # Message datetime (UTC)
    sender_name: Optional[str] = None  # Sender display name
    media_type: Optional[str] = None   # "photo"/"video"/"audio"/"document"/"sticker"/"location"/"contact" or None
    raw: Any = None       # Original platform-specific object
