from dataclasses import dataclass


@dataclass
class ChatInfo:
    source: str       # "telegram" or "whatsapp"
    chat_id: str      # Platform-specific chat identifier
    chat_title: str = ""  # Human-readable name (may be populated later)
