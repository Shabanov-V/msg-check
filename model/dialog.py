from typing import Optional
from telethon.tl.types import TypePeer
from model.dialogType import DialogType
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
class Dialog():
    id: int
    peer: TypePeer

    def __init__(self, id: int, peerType: DialogType):
        self.id = id
        if peerType == DialogType.USER:
            self.peer = PeerUser(id)
        elif peerType == DialogType.CHAT:
            self.peer = PeerChat(id)
        elif peerType == DialogType.CHANNEL:
            self.peer = PeerChannel(id)
        

    def __str__(self) -> str:
        return f"Dialog(id={self.id}, peer={self.peer})"
    
    def __repr__(self) -> str:
        return self.__str__()