# utils/protocol.py

import json
import struct
import hashlib
from typing import Any

# ── Message Types ──────────────────────────────────────────────────────────
MSG_BASIS_COMPARE  = "BASIS_COMPARE"
MSG_CHSH_RESULT    = "CHSH_RESULT"
MSG_KEY_HASH       = "KEY_HASH"
MSG_READY          = "READY"
MSG_CHAT           = "CHAT"
MSG_ABORT          = "ABORT"
MSG_ERROR_RATE     = "ERROR_RATE"
MSG_IMAGE_HEADER   = "IMAGE_HEADER"    # ← NEW: metadata before image
MSG_IMAGE_CHUNK    = "IMAGE_CHUNK"     # ← NEW: encrypted image chunk
MSG_IMAGE_DONE     = "IMAGE_DONE"      # ← NEW: all chunks sent
MSG_IMAGE_ACK      = "IMAGE_ACK"       # ← NEW: receiver confirms got image

def send_message(sock, msg_type: str, payload: Any):
    """Frame and send a message over TCP."""
    packet        = json.dumps({'type': msg_type, 'payload': payload}).encode('utf-8')
    length_prefix = struct.pack('>I', len(packet))
    sock.sendall(length_prefix + packet)

def receive_message(sock) -> dict:
    """Receive a framed message from TCP."""
    length_bytes = _recv_exact(sock, 4)
    msg_length   = struct.unpack('>I', length_bytes)[0]
    msg_bytes    = _recv_exact(sock, msg_length)
    return json.loads(msg_bytes.decode('utf-8'))

def _recv_exact(sock, num_bytes: int) -> bytes:
    """Read exactly num_bytes from socket."""
    data = b''
    while len(data) < num_bytes:
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data

def hash_key(key: bytes) -> str:
    """SHA-256 hash of key as hex string."""
    return hashlib.sha256(key).hexdigest()