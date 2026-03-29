from typing import Protocol, List
from model.unifiedMessage import UnifiedMessage
from model.chatInfo import ChatInfo


class MessageSource(Protocol):
    source_name: str

    async def get_target_chats(self) -> List[ChatInfo]:
        """Return the list of chats/groups to monitor."""
        ...

    async def fetch_messages(self, chat: ChatInfo) -> List[UnifiedMessage]:
        """Fetch messages from a chat since the last cursor stored in DB."""
        ...

    def get_message_reference(self, message: UnifiedMessage) -> str:
        """Return a human-readable reference (link or text) for a message."""
        ...

    async def check_health(self) -> bool:
        """Verify the source is available. Return True if healthy."""
        ...
